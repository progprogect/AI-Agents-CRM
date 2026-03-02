"""OTP service — generation, storage, and verification using Redis."""

import hashlib
import logging
import secrets

from app.config import get_settings
from app.storage.redis import get_redis_client

logger = logging.getLogger(__name__)

OTP_PREFIX = "otp:"
RATE_PREFIX = "rate_otp:"


def _hash_code(code: str) -> str:
    """SHA-256 hash of OTP code."""
    return hashlib.sha256(code.encode()).hexdigest()


def get_super_admin_emails() -> list[str]:
    """Return the list of super admin emails from env vars (ALLOWED_ADMIN_EMAILS)."""
    settings = get_settings()
    raw = settings.allowed_admin_emails or ""
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


async def is_allowed_email(email: str) -> bool:
    """Check whether the given email may log in.

    Priority:
    1. Super admins from ALLOWED_ADMIN_EMAILS env var — always allowed.
    2. If env var is not configured — dev mode, allow all.
    3. Otherwise check admin_users table in PostgreSQL.
    """
    email = email.strip().lower()
    super_admins = get_super_admin_emails()

    if email in super_admins:
        return True

    if not super_admins:
        # No list configured — dev mode, allow all
        return True

    # Check the database for regular users
    try:
        from app.storage.postgres import get_pool
        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT 1 FROM admin_users WHERE email=$1 AND is_active=true",
            email,
        )
        return row is not None
    except Exception as e:
        logger.error(f"DB check for allowed email failed: {e}", exc_info=True)
        return False


async def check_rate_limit(email: str) -> bool:
    """Return True if the request is within rate limits, False if exceeded."""
    settings = get_settings()
    redis = get_redis_client()
    key = f"{RATE_PREFIX}{email.lower()}"
    ttl = settings.otp_ttl_minutes * 60

    try:
        count_str = await redis.get(key)
        count = int(count_str) if count_str else 0

        if count >= settings.otp_rate_limit:
            return False

        if count == 0:
            await redis.set(key, "1", ttl=ttl)
        else:
            await redis.incr(key)
        return True
    except Exception as e:
        logger.error(f"Rate limit check error for {email}: {e}", exc_info=True)
        return True  # On Redis error, allow request


async def create_otp(email: str) -> str:
    """Generate a 6-digit OTP, store its hash in Redis, and return the plain code."""
    settings = get_settings()
    redis = get_redis_client()
    code = f"{secrets.randbelow(1_000_000):06d}"
    key = f"{OTP_PREFIX}{email.lower()}"
    ttl = settings.otp_ttl_minutes * 60
    await redis.set(key, _hash_code(code), ttl=ttl)
    logger.info(f"OTP created for {email}")
    return code


async def verify_otp(email: str, code: str) -> bool:
    """Verify the OTP code. Deletes the key on success (one-time use)."""
    redis = get_redis_client()
    key = f"{OTP_PREFIX}{email.lower()}"

    try:
        stored_hash = await redis.get(key)
        if not stored_hash:
            logger.warning(f"OTP verify: no active code found for {email}")
            return False

        if stored_hash != _hash_code(code):
            logger.warning(f"OTP verify: invalid code for {email}")
            return False

        await redis.delete(key)
        logger.info(f"OTP verified successfully for {email}")
        return True
    except Exception as e:
        logger.error(f"OTP verification error for {email}: {e}", exc_info=True)
        return False
