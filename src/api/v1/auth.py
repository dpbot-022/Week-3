import secrets
from fastapi import APIRouter, Request, Response, BackgroundTasks, HTTPException, status, Depends
from src.core.config import settings
from src.core.logging import logger
from src.schemas.auth_models import (
    OTPRequest,
    OTPVerifyRequest,
    OTPResponse,
    TokenResponse,
    UserResponse,
    MessageResponse
)
from src.auth.store import auth_store, UserRecord
from src.auth.jwt_handler import create_access_token, create_refresh_token
from src.auth.email_service import email_service, SMTPConfigurationError, SMTPDeliveryError
from src.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication & Passwordless OTP"])

@router.post("/request-otp", response_model=OTPResponse)
async def request_otp(
    payload: OTPRequest,
    request: Request,
    background_tasks: BackgroundTasks
):
    """Sends a 6-digit OTP code to the requested email. Responses are strictly identical for new and existing users."""
    email = payload.email.strip().lower()
    client_ip = request.client.host if request.client else "127.0.0.1"

    # 1. Production SMTP readiness check
    if settings.APP_ENV == "production":
        if not settings.SMTP_HOST:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Email delivery service is unconfigured in production environment."
            )

    # 2. Rate limiting (cooldown, email frequency, IP frequency)
    allowed, rate_err = auth_store.check_rate_limits(email=email, ip=client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=rate_err or "Rate limit exceeded. Please wait before retrying."
        )

    # 3. Generate cryptographically random 6-digit code
    code = f"{secrets.randbelow(1000000):06d}"

    # 4. Store HMAC-SHA256 hash (never plain text)
    auth_store.save_otp(email=email, code=code)

    # 5. Dispatch email in background with retry bounds
    background_tasks.add_task(email_service.send_otp_email, email, code)

    return OTPResponse(
        message="If this email is valid, a verification code has been sent.",
        cooldown_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS
    )

@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(payload: OTPVerifyRequest, response: Response):
    """Verifies a 6-digit OTP code, creates account if new, and issues access + refresh tokens."""
    email = payload.email.strip().lower()
    code = payload.code.strip()

    valid, err_msg = auth_store.verify_otp(email=email, code=code)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg or "Invalid verification code."
        )

    # User retrieval or account creation
    user = auth_store.get_or_create_user(email)
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token()
    auth_store.create_refresh_token_family(user.id, refresh_token)

    # Set httpOnly refresh cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=(settings.APP_ENV == "production"),
        samesite="lax",
        path="/api/v1/auth",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse(**user.to_dict())
    )

@router.post("/refresh", response_model=TokenResponse)
async def refresh_session(request: Request, response: Response):
    """Rotates refresh token and issues a new access token. Revokes family if reuse is detected."""
    old_refresh_token = request.cookies.get("refresh_token")
    if not old_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: No refresh token present."
        )

    new_refresh_token = create_refresh_token()
    user_id, err_msg = auth_store.rotate_refresh_token(old_refresh_token, new_refresh_token)
    if not user_id:
        response.delete_cookie(key="refresh_token", path="/api/v1/auth")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err_msg or "Invalid or expired session. Please sign in again."
        )

    user = auth_store.get_user_by_id(user_id)
    if not user:
        response.delete_cookie(key="refresh_token", path="/api/v1/auth")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account associated with session not found."
        )

    access_token = create_access_token(user.id)

    # Rotate cookie with new refresh token
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=(settings.APP_ENV == "production"),
        samesite="lax",
        path="/api/v1/auth",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse(**user.to_dict())
    )

@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, response: Response):
    """Revokes refresh token family and clears the session cookie."""
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        auth_store.revoke_refresh_token(refresh_token)

    response.delete_cookie(key="refresh_token", path="/api/v1/auth")
    return MessageResponse(message="Successfully signed out.")

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: UserRecord = Depends(get_current_user)
):
    """Returns the authenticated user context (id, email, created_at)."""
    return UserResponse(**current_user.to_dict())
