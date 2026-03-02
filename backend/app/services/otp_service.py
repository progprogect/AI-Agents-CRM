"""OTP service — generation, storage, and verification using Redis."""

import hashlib
import logging
import secrets
from typing import Optional

from app.config import get_settings
from app.storage.redis import get_redis_client

logger = logging.getLogger(__name__)

OTP_PREFIX = "otp:"
RATE_PREFIX = "rate_otp:"


def _hash_code(code: str) -> str:
    """SHA-256 hash of OTP code."""
    return hashlib.sha256(code.encode()).hexdigest()


def get_allowed_emails() -> list[str]:
    """Return the list of allowed admin emails from config."""
    settings = get_settings()
    raw = settings.allowed_admin_emails or ""
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


def is_allowed_email(email: str) -> bool:
    """Check whether the given email is in the allowed admin list."""
    allowed = get_allowed_emails()
    if not allowed:
        # No list configured — allow all (dev mode)
        return True
    return email.strip().lower() in allowed


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

        # Increment and set TTL only on first request in window
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

        # One-time use — delete immediately after success
        await redis.delete(key)
        logger.info(f"OTP verified successfully for {email}")
        return True
    except Exception as e:
        logger.error(f"OTP verification error for {email}: {e}", exc_info=True)
        return False
