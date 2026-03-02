"""Admin authentication endpoints — Email OTP flow."""

import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.config import get_settings
from app.services.email_service import send_otp_email
from app.services.otp_service import (
    check_rate_limit,
    create_otp,
    is_allowed_email,
    verify_otp,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Request / Response schemas ---

class RequestOTPBody(BaseModel):
    email: EmailStr


class VerifyOTPBody(BaseModel):
    email: EmailStr
    code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Helpers ---

def _create_jwt(email: str) -> str:
    """Create a signed JWT for the given email."""
    settings = get_settings()
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not configured")

    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expires_hours),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


# --- Endpoints ---

@router.post("/request-otp", status_code=status.HTTP_200_OK)
async def request_otp(body: RequestOTPBody) -> dict:
    """Step 1: Request OTP email. Returns 200 regardless to avoid email enumeration."""
    email = body.email.lower()

    if not is_allowed_email(email):
        # Return 200 to avoid email enumeration — do not reveal which emails are allowed
        logger.warning(f"OTP requested for non-allowed email: {email}")
        return {"message": "If this email is registered, a code has been sent."}

    within_limit = await check_rate_limit(email)
    if not within_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait before requesting a new code.",
        )

    code = await create_otp(email)
    await send_otp_email(email, code)

    return {"message": "If this email is registered, a code has been sent."}


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp_endpoint(body: VerifyOTPBody) -> TokenResponse:
    """Step 2: Verify OTP and return a JWT access token."""
    email = body.email.lower()
    code = body.code.strip()

    valid = await verify_otp(email, code)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired code.",
        )

    try:
        token = _create_jwt(email)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service is not configured.",
        )

    return TokenResponse(access_token=token)
