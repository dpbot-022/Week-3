import jwt
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from src.core.config import settings

def create_access_token(user_id: str) -> str:
    """Creates a short-lived, pinned HS256 JWT access token with required claims (exp, iat, iss, aud, sub, jti)."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: Dict[str, Any] = {
        "sub": user_id,
        "jti": str(uuid.uuid4()),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp())
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str) -> Dict[str, Any]:
    """Decodes and strictly validates HS256 access token claims (exp, iat, iss, aud, sub, jti)."""
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        issuer=settings.JWT_ISSUER,
        audience=settings.JWT_AUDIENCE,
        options={
            "require": ["exp", "iat", "iss", "aud", "sub", "jti"],
            "verify_signature": True,
            "verify_exp": True,
            "verify_iat": True,
            "verify_iss": True,
            "verify_aud": True
        }
    )

def create_refresh_token() -> str:
    """Generates a cryptographically strong, URL-safe random string for refresh tokens."""
    return secrets.token_urlsafe(48)
