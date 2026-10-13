from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.auth.service import auth_service
from src.auth.deps import get_current_user
from src.db.models import User
from src.core.audit import audit_service

router = APIRouter(prefix="/auth", tags=["Authentication"])

class OTPRequest(BaseModel):
    email: EmailStr

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str

class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/request-otp")
def request_otp(payload: OTPRequest, db: Session = Depends(get_db)):
    result = auth_service.generate_and_send_otp(db, str(payload.email))
    audit_service.log(
        user_email=str(payload.email),
        role="anonymous",
        action="auth:otp_requested",
        resource="auth",
        details={"result": "dispatched"}
    )
    return result

@router.post("/verify-otp")
def verify_otp(payload: OTPVerifyRequest, response: Response, request: Request, db: Session = Depends(get_db)):
    try:
        data, user = auth_service.verify_otp_and_login(db, str(payload.email), payload.otp)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Set httpOnly cookie for refresh token
    response.set_cookie(
        key="refresh_token",
        value=data["refresh_token"],
        httponly=True,
        max_age=7 * 24 * 3600,
        samesite="lax",
        secure=False  # Allow local HTTP development
    )
    # Set access token cookie as well for easy browser access
    response.set_cookie(
        key="access_token",
        value=data["access_token"],
        httponly=True,
        max_age=3600,
        samesite="lax",
        secure=False
    )

    client_ip = request.client.host if request.client else "127.0.0.1"
    audit_service.log(
        user_email=user.email,
        role=user.role,
        action="auth:login_success",
        resource="auth",
        ip_address=client_ip
    )

    return data

@router.post("/refresh")
def refresh_token(request: Request, payload: Optional[RefreshRequest] = None, db: Session = Depends(get_db)):
    token = None
    if payload and payload.refresh_token:
        token = payload.refresh_token
    elif "refresh_token" in request.cookies:
        token = request.cookies.get("refresh_token")

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token.")

    try:
        return auth_service.refresh_access_token(db, token)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

@router.post("/logout")
def logout(response: Response, current_user: User = Depends(get_current_user)):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    audit_service.log(
        user_email=current_user.email,
        role=current_user.role,
        action="auth:logout",
        resource="auth"
    )
    return {"message": "Signed out successfully."}

@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return current_user.to_dict()
