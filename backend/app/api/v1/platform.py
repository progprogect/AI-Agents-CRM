"""Platform admin endpoints — organization management (platform admins only)."""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.api.tenant import TenantContext, require_platform_admin, get_tenant_context
from app.storage.postgres import get_pool
from app.services.otp_service import get_super_admin_emails
from app.services.password_service import hash_password

logger = logging.getLogger(__name__)

router = APIRouter()


def _slugify(name: str) -> str:
    """Create a URL-safe slug from an organization name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = slug.strip("-")
    return slug[:100] or "org"


class CreateOrgRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=100)
    # First owner email (will be added to organization_members as owner)
    owner_email: EmailStr
    owner_password: Optional[str] = Field(None, min_length=8)


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    is_active: bool
    created_by: str
    created_at: str


class PatchOrgRequest(BaseModel):
    is_active: Optional[bool] = None
    name: Optional[str] = Field(None, max_length=255)


class OrgMemberResponse(BaseModel):
    email: str
    role: str
    invited_by: Optional[str]
    is_active: bool
    created_at: str


@router.post("/platform/orgs", response_model=OrgResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: CreateOrgRequest,
    ctx: TenantContext = require_platform_admin(),
):
    """Create a new organization and its first owner. Platform admin only."""
    pool = await get_pool()
    slug = _slugify(body.slug or body.name)

    # Ensure slug uniqueness
    existing_slug = await pool.fetchrow("SELECT id FROM organizations WHERE slug = $1", slug)
    if existing_slug:
        slug = f"{slug}-{slug[:4]}"

    async with pool.acquire() as conn:
        async with conn.transaction():
            org = await conn.fetchrow(
                """
                INSERT INTO organizations (name, slug, is_active, created_by)
                VALUES ($1, $2, TRUE, $3)
                RETURNING id, name, slug, is_active, created_by, created_at
                """,
                body.name,
                slug,
                ctx.user_email,
            )

            # Add owner to organization_members
            await conn.execute(
                """
                INSERT INTO organization_members (organization_id, email, role, invited_by, is_active)
                VALUES ($1, $2, 'owner', $3, TRUE)
                ON CONFLICT (organization_id, email) DO UPDATE SET role = 'owner', is_active = TRUE
                """,
                org["id"],
                body.owner_email.lower(),
                ctx.user_email,
            )

            # Ensure the owner has an admin_users record
            super_admins = get_super_admin_emails()
            if body.owner_email.lower() not in super_admins:
                pw_hash = hash_password(body.owner_password) if body.owner_password else None
                await conn.execute(
                    """
                    INSERT INTO admin_users (email, created_by, password_hash, is_active)
                    VALUES ($1, $2, $3, TRUE)
                    ON CONFLICT (email) DO UPDATE SET is_active = TRUE
                    """,
                    body.owner_email.lower(),
                    ctx.user_email,
                    pw_hash,
                )

    logger.info(f"Created org '{body.name}' (slug={slug}) by {ctx.user_email}")
    return OrgResponse(
        id=str(org["id"]),
        name=org["name"],
        slug=org["slug"],
        is_active=org["is_active"],
        created_by=org["created_by"],
        created_at=org["created_at"].isoformat(),
    )


@router.get("/platform/orgs", response_model=list[OrgResponse])
async def list_organizations(
    ctx: TenantContext = require_platform_admin(),
):
    """List all organizations. Platform admin only."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id, name, slug, is_active, created_by, created_at FROM organizations ORDER BY created_at DESC"
    )
    return [
        OrgResponse(
            id=str(r["id"]),
            name=r["name"],
            slug=r["slug"],
            is_active=r["is_active"],
            created_by=r["created_by"],
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]


@router.patch("/platform/orgs/{org_id}", response_model=OrgResponse)
async def patch_organization(
    org_id: str,
    body: PatchOrgRequest,
    ctx: TenantContext = require_platform_admin(),
):
    """Update organization name or active status. Platform admin only."""
    pool = await get_pool()
    org = await pool.fetchrow("SELECT * FROM organizations WHERE id = $1::uuid", org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    updates = []
    params = []
    i = 1
    if body.is_active is not None:
        updates.append(f"is_active = ${i}")
        params.append(body.is_active)
        i += 1
    if body.name is not None:
        updates.append(f"name = ${i}")
        params.append(body.name)
        i += 1
    if not updates:
        return OrgResponse(
            id=str(org["id"]),
            name=org["name"],
            slug=org["slug"],
            is_active=org["is_active"],
            created_by=org["created_by"],
            created_at=org["created_at"].isoformat(),
        )

    params.append(org_id)
    await pool.execute(
        f"UPDATE organizations SET {', '.join(updates)} WHERE id = ${ i}::uuid",
        *params,
    )
    updated = await pool.fetchrow("SELECT * FROM organizations WHERE id = $1::uuid", org_id)
    return OrgResponse(
        id=str(updated["id"]),
        name=updated["name"],
        slug=updated["slug"],
        is_active=updated["is_active"],
        created_by=updated["created_by"],
        created_at=updated["created_at"].isoformat(),
    )


@router.get("/platform/orgs/{org_id}/members", response_model=list[OrgMemberResponse])
async def list_org_members(
    org_id: str,
    ctx: TenantContext = require_platform_admin(),
):
    """List members of a specific organization. Platform admin only."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT email, role, invited_by, is_active, created_at
        FROM organization_members
        WHERE organization_id = $1::uuid
        ORDER BY created_at ASC
        """,
        org_id,
    )
    return [
        OrgMemberResponse(
            email=r["email"],
            role=r["role"],
            invited_by=r["invited_by"],
            is_active=r["is_active"],
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]
