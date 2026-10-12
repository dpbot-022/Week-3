from pydantic import EmailStr, Field
from src.schemas.models import StrictBaseModel

class OTPRequest(StrictBaseModel):
    email: EmailStr

class OTPVerifyRequest(StrictBaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")

class UserResponse(StrictBaseModel):
    id: str
    email: str
    created_at: str

class TokenResponse(StrictBaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15 minutes
    user: UserResponse

class OTPResponse(StrictBaseModel):
    message: str = "If this email is valid, a verification code has been sent."
    cooldown_seconds: int = 60

class MessageResponse(StrictBaseModel):
    message: str
