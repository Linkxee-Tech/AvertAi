from typing import Optional
from pydantic import BaseModel, Field


class OTPRequest(BaseModel):
    phone: str = Field(..., examples=["+254700000213"])


class OTPResponse(BaseModel):
    message: str
    dev_hint_code: Optional[str] = None  # only populated when ENV=development and no SMS provider configured


class OTPVerifyRequest(BaseModel):
    phone: str
    code: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DashboardLoginRequest(BaseModel):
    email: str
    password: str
    totp_code: Optional[str] = None  # 2FA authenticator code, required on the login call once password is verified
