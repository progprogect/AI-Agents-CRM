"""Admin authentication endpoints — Email OTP flow + user management."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.config import get_settings
from app.api.auth import get_current_admin, require_super_admin
from app.services.email_service import send_otp_email
from app.services.password_service import hash_password, verify_password
from app.services.otp_service import (
    check_rate_limit,
    create_otp,
    get_super_admin_emails,
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


class LoginPasswordBody(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    email: str
    is_super_admin: bool


class AdminUserResponse(BaseModel):
    email: str
    created_by: str
    is_active: bool
    created_at: Optional[str]


class InviteUserBody(BaseModel):
    email: EmailStr
    password: Optional[str] = None  # Optional: if set, user can login with password


# --- Helpers ---

def _create_jwt(email: str) -> str:
    """Create a signed JWT for the given email, including is_super_admin flag."""
    settings = get_settings()
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not configured")

    now = datetime.now(timezone.utc)
    super_admins = get_super_admin_emails()
    payload = {
        "sub": email,
        "is_super_admin": email.lower() in super_admins,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expires_hours),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


# --- Auth endpoints (public) ---

@router.post("/request-otp", status_code=status.HTTP_200_OK)
async def request_otp(body: RequestOTPBody) -> dict:
    """Step 1: Request OTP email. Returns 200 regardless to avoid email enumeration."""
    email = body.email.lower()

    if not await is_allowed_email(email):
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


@router.post("/login-password", response_model=TokenResponse)
async def login_with_password(body: LoginPasswordBody) -> TokenResponse:
    """Login with email + password. Only for users who have a password set (regular admins)."""
    email = body.email.lower()
    password = body.password

    # Super admins (from env) cannot use password — only OTP
    if email in get_super_admin_emails():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Use email code to sign in.",
        )

    try:
        from app.storage.postgres import get_pool
        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT password_hash FROM admin_users WHERE email=$1 AND is_active=true",
            email,
        )
    except Exception as e:
        logger.error(f"DB error during password login: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error.",
        )

    if not row or not row["password_hash"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not verify_password(password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    try:
        token = _create_jwt(email)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service is not configured.",
        )

    return TokenResponse(access_token=token)


# --- Me endpoint (requires auth) ---

@router.get("/me", response_model=MeResponse)
async def get_me(current_user: str = Depends(get_current_admin)) -> MeResponse:
    """Return current user info decoded from JWT."""
    super_admins = get_super_admin_emails()
    return MeResponse(
        email=current_user,
        is_super_admin=current_user.lower() in super_admins if super_admins else True,
    )


# --- User management endpoints (super admin only) ---

@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    current_user: str = Depends(require_super_admin),
) -> list[AdminUserResponse]:
    """List all regular admin users (excludes super admins from env)."""
    from app.storage.postgres import get_pool
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT email, created_by, is_active, created_at FROM admin_users WHERE is_active = TRUE ORDER BY created_at DESC"
    )
    return [
        AdminUserResponse(
            email=row["email"],
            created_by=row["created_by"],
            is_active=row["is_active"],
            created_at=row["created_at"].isoformat() if row["created_at"] else None,
        )
        for row in rows
    ]


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def invite_user(
    body: InviteUserBody,
    current_user: str = Depends(require_super_admin),
) -> dict:
    """Add a new regular admin user."""
    email = body.email.lower()

    # Cannot add super admin emails
    if email in get_super_admin_emails():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already a super admin.",
        )

    from app.storage.postgres import get_pool
    pool = await get_pool()

    if body.password and len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters.",
        )
    password_hash_val = hash_password(body.password) if body.password else None

    # Check if user exists
    existing = await pool.fetchrow(
        "SELECT id, is_active FROM admin_users WHERE email=$1", email
    )
    if existing:
        if existing["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already exists.",
            )
        # Inactive user (legacy from soft delete): delete and re-add
        await pool.execute("DELETE FROM admin_users WHERE email=$1", email)

    await pool.execute(
        "INSERT INTO admin_users (email, created_by, password_hash) VALUES ($1, $2, $3)",
        email, current_user, password_hash_val,
    )

    logger.info(f"User {email} added by super admin {current_user}")
    return {"message": f"User {email} added successfully."}


@router.delete("/users/{email}", status_code=status.HTTP_200_OK)
async def remove_user(
    email: str,
    current_user: str = Depends(require_super_admin),
) -> dict:
    """Permanently remove a regular admin user (hard delete)."""
    email = email.lower()

    # Cannot remove yourself
    if email == current_user.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own account.",
        )

    # Cannot remove super admins
    if email in get_super_admin_emails():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Super admin accounts cannot be removed here.",
        )

    from app.storage.postgres import get_pool
    pool = await get_pool()
    result = await pool.execute(
        "DELETE FROM admin_users WHERE email=$1", email
    )

    if result == "DELETE 0":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    logger.info(f"User {email} removed by super admin {current_user}")
    return {"message": f"User {email} removed successfully."}
