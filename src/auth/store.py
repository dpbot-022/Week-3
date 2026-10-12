import hmac
import hashlib
import time
import uuid
import threading
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timezone, timedelta
from src.core.config import settings
from src.core.logging import logger

class UserRecord:
    def __init__(self, user_id: str, email: str, created_at: Optional[datetime] = None):
        self.id = user_id
        self.email = email.strip().lower()
        self.created_at = created_at or datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "created_at": self.created_at.isoformat()
        }

class OTPRecord:
    def __init__(self, email: str, code_hash: str, expires_at: datetime):
        self.email = email.strip().lower()
        self.code_hash = code_hash
        self.created_at = datetime.now(timezone.utc)
        self.expires_at = expires_at
        self.attempts = 0
        self.last_sent_at = datetime.now(timezone.utc)

class RefreshTokenRecord:
    def __init__(self, family_id: str, token_hash: str, user_id: str, expires_at: datetime):
        self.family_id = family_id
        self.token_hash = token_hash
        self.user_id = user_id
        self.expires_at = expires_at
        self.is_revoked = False
        self.created_at = datetime.now(timezone.utc)

class AuthStore:
    def __init__(self):
        self._lock = threading.Lock()
        self.users_by_id: Dict[str, UserRecord] = {}
        self.users_by_email: Dict[str, UserRecord] = {}
        self.otps: Dict[str, OTPRecord] = {}  # email -> OTPRecord
        self.refresh_tokens: Dict[str, RefreshTokenRecord] = {}  # token_hash -> RefreshTokenRecord
        self.refresh_families: Dict[str, List[str]] = {}  # family_id -> list of token_hashes
        self.email_request_history: Dict[str, List[float]] = {}  # email -> list of timestamps
        self.ip_request_history: Dict[str, List[float]] = {}  # ip -> list of timestamps

    # -------------------------------------------------------------
    # User Management
    # -------------------------------------------------------------
    def get_or_create_user(self, email: str) -> UserRecord:
        normalized_email = email.strip().lower()
        with self._lock:
            if normalized_email in self.users_by_email:
                return self.users_by_email[normalized_email]
            user_id = str(uuid.uuid4())
            user = UserRecord(user_id=user_id, email=normalized_email)
            self.users_by_id[user_id] = user
            self.users_by_email[normalized_email] = user
            return user

    def get_user_by_id(self, user_id: str) -> Optional[UserRecord]:
        with self._lock:
            return self.users_by_id.get(user_id)

    def get_user_by_email(self, email: str) -> Optional[UserRecord]:
        normalized_email = email.strip().lower()
        with self._lock:
            return self.users_by_email.get(normalized_email)

    # -------------------------------------------------------------
    # Rate Limiting & Cooldown
    # -------------------------------------------------------------
    def check_rate_limits(self, email: str, ip: str) -> Tuple[bool, Optional[str]]:
        normalized_email = email.strip().lower()
        now = time.time()
        with self._lock:
            # 1. 60s Resend cooldown per email
            if normalized_email in self.otps:
                last_sent = self.otps[normalized_email].last_sent_at.timestamp()
                remaining_cooldown = int(settings.OTP_RESEND_COOLDOWN_SECONDS - (now - last_sent))
                if remaining_cooldown > 0:
                    return False, f"Please wait {remaining_cooldown} seconds before requesting a new code."

            # 2. Rate limit per email: max 3 requests per 5 minutes
            email_history = [t for t in self.email_request_history.get(normalized_email, []) if now - t < 300]
            if len(email_history) >= 3:
                return False, "Too many verification requests for this email. Please wait a few minutes."

            # 3. Rate limit per IP: max 5 requests per 60 seconds
            ip_history = [t for t in self.ip_request_history.get(ip, []) if now - t < 60]
            if len(ip_history) >= 5:
                return False, "Too many requests from this IP address. Please slow down."

            # Record timestamps
            email_history.append(now)
            self.email_request_history[normalized_email] = email_history
            ip_history.append(now)
            self.ip_request_history[ip] = ip_history
            return True, None

    # -------------------------------------------------------------
    # OTP Storage & Verification (HMAC-SHA256 Peppered)
    # -------------------------------------------------------------
    @staticmethod
    def hash_code(code: str) -> str:
        return hmac.new(
            settings.OTP_PEPPER.encode("utf-8"),
            code.strip().encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    def save_otp(self, email: str, code: str) -> None:
        normalized_email = email.strip().lower()
        code_hash = self.hash_code(code)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
        with self._lock:
            # Storing a new OTP automatically invalidates any earlier code
            self.otps[normalized_email] = OTPRecord(
                email=normalized_email,
                code_hash=code_hash,
                expires_at=expires_at
            )

    def verify_otp(self, email: str, code: str) -> Tuple[bool, Optional[str]]:
        normalized_email = email.strip().lower()
        candidate_hash = self.hash_code(code)
        now = datetime.now(timezone.utc)

        with self._lock:
            record = self.otps.get(normalized_email)
            if not record:
                return False, "No active verification code found. Please request a new one."

            if now > record.expires_at:
                del self.otps[normalized_email]
                return False, "Verification code has expired. Please request a new code."

            if record.attempts >= settings.OTP_MAX_ATTEMPTS:
                del self.otps[normalized_email]
                return False, "Maximum verification attempts exceeded. Code has been invalidated. Please request a new code."

            # Secure constant-time hash comparison
            if hmac.compare_digest(candidate_hash, record.code_hash):
                # Single use: remove code immediately
                del self.otps[normalized_email]
                return True, None
            else:
                record.attempts += 1
                attempts_left = settings.OTP_MAX_ATTEMPTS - record.attempts
                if attempts_left <= 0:
                    del self.otps[normalized_email]
                    return False, "Maximum verification attempts exceeded. Code has been invalidated. Please request a new code."
                return False, f"Invalid verification code. {attempts_left} attempts remaining."

    # -------------------------------------------------------------
    # Refresh Token Family & Reuse Detection
    # -------------------------------------------------------------
    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_refresh_token_family(self, user_id: str, refresh_token: str) -> str:
        family_id = str(uuid.uuid4())
        token_hash = self.hash_token(refresh_token)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

        record = RefreshTokenRecord(
            family_id=family_id,
            token_hash=token_hash,
            user_id=user_id,
            expires_at=expires_at
        )
        with self._lock:
            self.refresh_tokens[token_hash] = record
            self.refresh_families[family_id] = [token_hash]
        return family_id

    def rotate_refresh_token(self, old_refresh_token: str, new_refresh_token: str) -> Tuple[Optional[str], Optional[str]]:
        old_hash = self.hash_token(old_refresh_token)
        new_hash = self.hash_token(new_refresh_token)
        now = datetime.now(timezone.utc)

        with self._lock:
            record = self.refresh_tokens.get(old_hash)
            if not record:
                return None, "Invalid or unrecognized refresh token."

            family_id = record.family_id

            # REUSE DETECTION: If a previously revoked token in the family is presented, revoke the entire family!
            if record.is_revoked:
                logger.warning(f"SECURITY ALERT: Refresh token reuse detected for family {family_id}! Revoking family.")
                for th in self.refresh_families.get(family_id, []):
                    if th in self.refresh_tokens:
                        self.refresh_tokens[th].is_revoked = True
                return None, "Security notice: Refresh token reuse detected. Session has been revoked."

            if now > record.expires_at:
                return None, "Refresh token has expired. Please sign in again."

            # Mark old token as revoked (used)
            record.is_revoked = True

            # Register new rotated token under the same family
            expires_at = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
            new_record = RefreshTokenRecord(
                family_id=family_id,
                token_hash=new_hash,
                user_id=record.user_id,
                expires_at=expires_at
            )
            self.refresh_tokens[new_hash] = new_record
            self.refresh_families[family_id].append(new_hash)

            return record.user_id, None

    def revoke_refresh_token(self, refresh_token: str) -> None:
        token_hash = self.hash_token(refresh_token)
        with self._lock:
            record = self.refresh_tokens.get(token_hash)
            if record:
                family_id = record.family_id
                for th in self.refresh_families.get(family_id, []):
                    if th in self.refresh_tokens:
                        self.refresh_tokens[th].is_revoked = True

auth_store = AuthStore()
