"""Password hashing and verification for admin users."""

import logging
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(password: str) -> str:
    """Hash a plain password. Returns bcrypt hash."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain password against a hash. Returns True if match."""
    if not hashed:
        return False
    try:
        return pwd_context.verify(plain, hashed)
    except Exception as e:
        logger.warning(f"Password verify error: {e}")
        return False
