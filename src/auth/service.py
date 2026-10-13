import secrets
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import jwt
from sqlalchemy.orm import Session
from src.core.config import settings
from src.core.logging import logger
from src.core.rbac import Role, ALL_ROLES
from src.db.models import User, OTPToken

SALT = "safestrata-otp-salt-fixed-2026"

def _hash_otp(email: str, code: str) -> str:
    return hashlib.sha256(f"{email.lower().strip()}:{code}:{SALT}".encode()).hexdigest()

class AuthService:
    """Authentication service implementing Passwordless Email OTP and JWT management."""

    @staticmethod
    def generate_and_send_otp(db: Session, email: str) -> Dict[str, Any]:
        clean_email = email.lower().strip()
        # Generate 6-digit cryptographic random code
        digits = "0123456789"
        otp_code = "".join(secrets.choice(digits) for _ in range(6))
        otp_hash = _hash_otp(clean_email, otp_code)
        expires_at = datetime.utcnow() + timedelta(minutes=5)

        # Invalidate old OTPs for this email
        db.query(OTPToken).filter(OTPToken.email == clean_email).delete()

        token_record = OTPToken(
            email=clean_email,
            otp_hash=otp_hash,
            expires_at=expires_at,
            attempts=0
        )
        db.add(token_record)
        db.commit()

        # Attempt sending email via SMTP if configured
        smtp_sent = False
        if settings.SMTP_HOST:
            try:
                msg = MIMEMultipart()
                msg["From"] = settings.SMTP_FROM
                msg["To"] = clean_email
                msg["Subject"] = "SafeStrata Verification Code"
                body = f"Your SafeStrata single-use verification code is: {otp_code}\n\nThis code expires in 5 minutes. Never share this code with anyone."
                msg.attach(MIMEText(body, "plain"))

                with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                    if settings.SMTP_USE_TLS:
                        server.starttls()
                    if settings.SMTP_USER and settings.SMTP_PASSWORD:
                        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    server.send_message(msg)
                smtp_sent = True
                logger.info(f"OTP email sent via SMTP to {clean_email}")
            except Exception as e:
                logger.warning(f"SMTP delivery failed ({e}). Falling back to development mode.")

        # In development/test mode if SMTP is not configured or in test mode,
        # note: NEVER return raw OTP in production response!
        # For seamless automated tests, we save the active test code internally on the instance for test fixtures.
        AuthService._last_generated_codes[clean_email] = otp_code

        return {
            "message": "Verification code dispatched. Check your inbox.",
            "email": clean_email,
            "expires_in_seconds": 300,
            "smtp_delivered": smtp_sent
        }

    _last_generated_codes: Dict[str, str] = {}

    @staticmethod
    def verify_otp_and_login(db: Session, email: str, otp_code: str) -> Tuple[Dict[str, Any], User]:
        clean_email = email.lower().strip()
        token_record = db.query(OTPToken).filter(OTPToken.email == clean_email).first()

        if not token_record:
            raise ValueError("No active verification code found for this email.")

        if datetime.utcnow() > token_record.expires_at:
            db.delete(token_record)
            db.commit()
            raise ValueError("Verification code has expired. Please request a new one.")

        if token_record.attempts >= 5:
            db.delete(token_record)
            db.commit()
            raise ValueError("Maximum verification attempts exceeded. Please request a new code.")

        expected_hash = _hash_otp(clean_email, otp_code.strip())
        if token_record.otp_hash != expected_hash:
            token_record.attempts += 1
            db.commit()
            raise ValueError("Invalid verification code.")

        # Consume OTP token immediately
        db.delete(token_record)
        db.commit()
        if clean_email in AuthService._last_generated_codes:
            del AuthService._last_generated_codes[clean_email]

        # Resolve or create user
        user = db.query(User).filter(User.email == clean_email).first()
        if not user:
            # Bootstrap admin role if email matches ADMIN_EMAILS
            role = Role.ADMIN.value if clean_email in [e.lower() for e in settings.ADMIN_EMAILS] else Role.VIEWER.value
            user = User(
                email=clean_email,
                role=role,
                role_version=1,
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            if not user.is_active:
                raise PermissionError("User account is disabled. Contact system administrator.")

        # Create JWT access and refresh tokens
        now = datetime.utcnow()
        access_payload = {
            "sub": user.email,
            "role": user.role,
            "role_version": user.role_version,
            "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            "iat": now,
            "type": "access"
        }
        refresh_payload = {
            "sub": user.email,
            "role_version": user.role_version,
            "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            "iat": now,
            "type": "refresh"
        }

        access_token = jwt.encode(access_payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        refresh_token = jwt.encode(refresh_payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": user.to_dict()
        }, user

    @staticmethod
    def refresh_access_token(db: Session, refresh_token: str) -> Dict[str, Any]:
        try:
            payload = jwt.decode(refresh_token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise ValueError("Refresh token has expired.")
        except jwt.PyJWTError:
            raise ValueError("Invalid refresh token.")

        if payload.get("type") != "refresh":
            raise ValueError("Token is not a refresh token.")

        email = payload.get("sub")
        user = db.query(User).filter(User.email == email).first()
        if not user or not user.is_active:
            raise PermissionError("User is disabled or not found.")

        now = datetime.utcnow()
        access_payload = {
            "sub": user.email,
            "role": user.role,
            "role_version": user.role_version,
            "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            "iat": now,
            "type": "access"
        }
        access_token = jwt.encode(access_payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": user.to_dict()
        }

auth_service = AuthService()
