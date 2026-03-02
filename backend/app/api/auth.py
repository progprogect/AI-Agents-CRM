"""Authentication and authorization utilities."""

import logging
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import get_settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


async def get_current_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Authenticate admin via JWT (primary) or static ADMIN_TOKEN (fallback/dev)."""
    settings = get_settings()

    if not credentials:
        # No token at all
        admin_token = getattr(settings, "admin_token", None)
        if not admin_token:
            # Dev mode: no auth configured — allow access
            return "admin_user"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # 1. Try JWT verification
    if settings.jwt_secret_key:
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=["HS256"],
            )
            email: str = payload.get("sub", "admin_user")
            return email
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError:
            pass  # Not a valid JWT — try static token fallback

    # 2. Fallback: static ADMIN_TOKEN (backward compat / dev mode)
    admin_token = getattr(settings, "admin_token", None)
    if admin_token and token == admin_token:
        return "admin_user"

    # 3. Dev mode: no token configured — allow access
    if not settings.jwt_secret_key and not admin_token:
        return "admin_user"

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid authentication credentials",
    )


def require_admin():
    """Dependency to require admin authentication."""
    return Depends(get_current_admin)
