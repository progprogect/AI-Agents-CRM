"""Password hashing and verification for admin users."""

import base64
import hashlib
import hmac
import logging
import secrets

logger = logging.getLogger(__name__)

_PBKDF2_SCHEME = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 390000


def hash_password(password: str) -> str:
    """Hash password using pbkdf2_sha256.

    Format: pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>
    """
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
    )
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    hash_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"{_PBKDF2_SCHEME}${_PBKDF2_ITERATIONS}${salt_b64}${hash_b64}"


def _verify_pbkdf2(plain: str, hashed: str) -> bool:
    parts = hashed.split("$")
    if len(parts) != 4 or parts[0] != _PBKDF2_SCHEME:
        return False
    try:
        iterations = int(parts[1])
        salt = base64.urlsafe_b64decode(parts[2].encode("ascii"))
        expected = base64.urlsafe_b64decode(parts[3].encode("ascii"))
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against current pbkdf2 or legacy bcrypt hashes."""
    if not hashed:
        return False

    if hashed.startswith(f"{_PBKDF2_SCHEME}$"):
        return _verify_pbkdf2(plain, hashed)

    # Legacy fallback for existing bcrypt hashes.
    if hashed.startswith("$2"):
        try:
            from passlib.context import CryptContext

            legacy_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            return legacy_context.verify(plain, hashed)
        except Exception as e:
            logger.warning(f"Legacy bcrypt verify error: {e}")
            return False

    try:
        return _verify_pbkdf2(plain, hashed)
    except Exception as e:
        logger.warning(f"Password verify error: {e}")
        return False
