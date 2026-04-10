"""Tenant context — multitenancy support for FastAPI endpoints.

Every authenticated request carries a TenantContext that identifies:
- which organization the user belongs to (org_id)
- the user's role within that org (owner | admin | member)
- whether the user is a platform-level admin (no org scope, sees everything)

Usage:
    @router.get("/agents")
    async def list_agents(ctx: TenantContext = Depends(get_tenant_context)):
        ...

    @router.delete("/agents/{id}")
    async def delete_agent(ctx: TenantContext = require_role("owner", "admin")):
        ...
"""

import logging
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import get_settings

logger = logging.getLogger(__name__)

_security = HTTPBearer(auto_error=False)

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


class TenantContext:
    """Resolved tenant / user context attached to every authenticated request."""

    def __init__(
        self,
        user_email: str,
        org_id: Optional[str],
        role: Optional[str],
        is_platform_admin: bool,
    ):
        self.user_email = user_email
        self.org_id = org_id
        self.role = role
        self.is_platform_admin = is_platform_admin

    def effective_org_id(self) -> str:
        """Return org_id for query filtering; raises 403 if not available."""
        if self.is_platform_admin and not self.org_id:
            # Platform admins querying without an org scope: callers must handle this.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Platform admin must specify an org_id for this operation.",
            )
        if not self.org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No organization associated with this account.",
            )
        return self.org_id


async def get_tenant_context(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> TenantContext:
    """Decode JWT and build TenantContext. Raises 401/403 on invalid tokens."""
    settings = get_settings()

    if not credentials:
        if settings.debug:
            return TenantContext(
                user_email="admin_user",
                org_id=DEFAULT_ORG_ID,
                role="owner",
                is_platform_admin=True,
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # 1. Validate via JWT
    if settings.jwt_secret_key:
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
            return TenantContext(
                user_email=payload.get("sub", "unknown"),
                org_id=payload.get("org_id"),
                role=payload.get("role"),
                is_platform_admin=payload.get("is_platform_admin", False),
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError:
            pass

    # 2. Static ADMIN_TOKEN fallback (dev / backward compat)
    admin_token = getattr(settings, "admin_token", None)
    if admin_token and token == admin_token:
        return TenantContext(
            user_email="admin_user",
            org_id=DEFAULT_ORG_ID,
            role="owner",
            is_platform_admin=True,
        )

    # 3. Debug mode — no token configured
    if not settings.jwt_secret_key and not admin_token and settings.debug:
        return TenantContext(
            user_email="admin_user",
            org_id=DEFAULT_ORG_ID,
            role="owner",
            is_platform_admin=True,
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid authentication credentials",
    )


def require_role(*allowed_roles: str):
    """Dependency factory: allow access only when user has one of the given roles.

    Platform admins bypass role checks — they can access everything.
    Deny-by-default: if org_id is missing and user is not platform_admin → 403.
    """

    async def _dep(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if ctx.is_platform_admin:
            return ctx
        if not ctx.org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No organization associated with this account.",
            )
        if ctx.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {', '.join(allowed_roles)}.",
            )
        return ctx

    return Depends(_dep)


def require_any_org_member():
    """Dependency: any authenticated org member (owner, admin, member)."""
    return require_role("owner", "admin", "member")


def require_platform_admin():
    """Dependency: only platform admins (from ALLOWED_ADMIN_EMAILS)."""

    async def _dep(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if not ctx.is_platform_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Platform admin access required.",
            )
        return ctx

    return Depends(_dep)
