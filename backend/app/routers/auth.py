import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, OTPCode
from app.core.config import get_settings
from app.core.security import (
    create_access_token, create_refresh_token, decode_token,
    hash_password, verify_password,
)
from app.core.deps import get_current_user
from app.services.rate_limiter import is_rate_limited
from app.services.comms_service import send_sms
from app.schemas.auth import (
    OTPRequest, OTPResponse, OTPVerifyRequest, TokenResponse,
    RefreshRequest, AccessTokenResponse, DashboardLoginRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/otp", response_model=OTPResponse)
def request_otp(payload: OTPRequest, request: Request, db: Session = Depends(get_db)):
    if is_rate_limited(f"otp:{payload.phone}", settings.OTP_RATE_LIMIT_PER_HOUR, 3600):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many OTP requests — try again later")

    # Hardcoded OTP to save SMS charges for hackathon demonstration
    code = "123456"
    expires = datetime.utcnow() + timedelta(minutes=5)

    existing = db.query(OTPCode).filter(OTPCode.phone == payload.phone).first()
    if existing:
        existing.code, existing.expires_at, existing.attempts = code, expires, 0
    else:
        db.add(OTPCode(phone=payload.phone, code=code, expires_at=expires, attempts=0))
    db.commit()

    # Do not call send_sms here to avoid actual billing during testing
    return {"message": "OTP sent", "dev_hint_code": code}


@router.post("/verify", response_model=TokenResponse)
def verify_otp(payload: OTPVerifyRequest, db: Session = Depends(get_db)):
    record = db.query(OTPCode).filter(OTPCode.phone == payload.phone).first()
    if not record or record.expires_at < datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OTP expired or not found — request a new one")
    if record.attempts >= 5:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many incorrect attempts")
    if record.code != payload.code:
        record.attempts += 1
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect code")

    db.delete(record)

    user = db.query(User).filter(User.phone == payload.phone).first()
    if not user:
        user = User(phone=payload.phone, role="user", status="Active")
        db.add(user)
        db.flush()
    user.last_active = datetime.utcnow()
    db.commit()

    return {
        "access_token": create_access_token(user.id, user.role),
        "refresh_token": create_refresh_token(user.id, user.role),
        "token_type": "bearer",
    }


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    data = decode_token(payload.refresh_token)
    if not data or data.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    user = db.query(User).filter(User.id == data["sub"]).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return {"access_token": create_access_token(user.id, user.role), "token_type": "bearer"}


@router.post("/login", response_model=TokenResponse)
def dashboard_login(payload: DashboardLoginRequest, db: Session = Depends(get_db)):
    """Email + password + 2FA authenticator-code login for the Admin Web
    Dashboard (separate from the mobile app's phone-OTP flow)."""
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not payload.totp_code:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "2FA code required")
    # Production: verify payload.totp_code against a TOTP secret (pyotp) stored per-admin.
    # Demo acceptance: any 6-digit code, matching the frontend's demo 2FA screen.
    if len(payload.totp_code) != 6 or not payload.totp_code.isdigit():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid 2FA code")
    user.last_active = datetime.utcnow()
    db.commit()
    return {
        "access_token": create_access_token(user.id, user.role),
        "refresh_token": create_refresh_token(user.id, user.role),
        "token_type": "bearer",
    }
