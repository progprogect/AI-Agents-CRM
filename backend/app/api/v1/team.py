"""Team management endpoints — invite/manage members within an organization."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.api.tenant import TenantContext, require_role, get_tenant_context
from app.services.otp_service import get_super_admin_emails
from app.services.password_service import hash_password
from app.storage.postgres import get_pool

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_ROLES = {"owner", "admin", "member"}


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="member", description="Role: owner | admin | member")
    password: Optional[str] = Field(None, min_length=8, description="Optional password for login")


class PatchMemberRequest(BaseModel):
    role: str = Field(..., description="New role: owner | admin | member")


class TeamMemberResponse(BaseModel):
    email: str
    role: str
    invited_by: Optional[str]
    is_active: bool
    created_at: str


@router.get("/team/members", response_model=list[TeamMemberResponse])
async def list_members(
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List all members of the current organization."""
    if not ctx.org_id:
        raise HTTPException(status_code=403, detail="No organization context.")

    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT email, role, invited_by, is_active, created_at
        FROM organization_members
        WHERE organization_id = $1::uuid AND is_active = TRUE
        ORDER BY created_at ASC
        """,
        ctx.org_id,
    )
    return [
        TeamMemberResponse(
            email=r["email"],
            role=r["role"],
            invited_by=r["invited_by"],
            is_active=r["is_active"],
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]


@router.post("/team/members", status_code=status.HTTP_201_CREATED)
async def invite_member(
    body: InviteMemberRequest,
    ctx: TenantContext = require_role("owner", "admin"),
):
    """Invite a new member to the current organization. owners and admins only."""
    if not ctx.org_id:
        raise HTTPException(status_code=403, detail="No organization context.")

    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{body.role}'. Valid: {', '.join(sorted(VALID_ROLES))}",
        )

    # Only owners can invite other owners
    if body.role == "owner" and ctx.role != "owner" and not ctx.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can invite other owners.",
        )

    email = body.email.lower()
    pool = await get_pool()

    # Upsert org member
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                "SELECT is_active FROM organization_members WHERE organization_id = $1::uuid AND email = $2",
                ctx.org_id,
                email,
            )
            if existing and existing["is_active"]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"User '{email}' is already a member of this organization.",
                )

            await conn.execute(
                """
                INSERT INTO organization_members (organization_id, email, role, invited_by, is_active)
                VALUES ($1::uuid, $2, $3, $4, TRUE)
                ON CONFLICT (organization_id, email) DO UPDATE SET
                    role = EXCLUDED.role,
                    invited_by = EXCLUDED.invited_by,
                    is_active = TRUE
                """,
                ctx.org_id,
                email,
                body.role,
                ctx.user_email,
            )

            # Ensure admin_users record exists
            super_admins = get_super_admin_emails()
            if email not in super_admins:
                pw_hash = hash_password(body.password) if body.password else None
                await conn.execute(
                    """
                    INSERT INTO admin_users (email, created_by, password_hash, is_active)
                    VALUES ($1, $2, $3, TRUE)
                    ON CONFLICT (email) DO UPDATE SET is_active = TRUE
                    """,
                    email,
                    ctx.user_email,
                    pw_hash,
                )

    logger.info(f"Invited {email} as {body.role} to org {ctx.org_id} by {ctx.user_email}")
    return {"message": f"User '{email}' invited as '{body.role}'."}


@router.patch("/team/members/{email}", response_model=TeamMemberResponse)
async def update_member_role(
    email: str,
    body: PatchMemberRequest,
    ctx: TenantContext = require_role("owner"),
):
    """Change a member's role. Only owners can do this."""
    if not ctx.org_id:
        raise HTTPException(status_code=403, detail="No organization context.")

    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{body.role}'.",
        )

    email = email.lower()
    if email == ctx.user_email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own role.",
        )

    pool = await get_pool()
    member = await pool.fetchrow(
        "SELECT * FROM organization_members WHERE organization_id = $1::uuid AND email = $2",
        ctx.org_id,
        email,
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")

    await pool.execute(
        "UPDATE organization_members SET role = $1 WHERE organization_id = $2::uuid AND email = $3",
        body.role,
        ctx.org_id,
        email,
    )

    updated = await pool.fetchrow(
        "SELECT * FROM organization_members WHERE organization_id = $1::uuid AND email = $2",
        ctx.org_id,
        email,
    )
    return TeamMemberResponse(
        email=updated["email"],
        role=updated["role"],
        invited_by=updated["invited_by"],
        is_active=updated["is_active"],
        created_at=updated["created_at"].isoformat(),
    )


@router.delete("/team/members/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    email: str,
    ctx: TenantContext = require_role("owner", "admin"),
):
    """Deactivate (soft-delete) a member from the organization."""
    if not ctx.org_id:
        raise HTTPException(status_code=403, detail="No organization context.")

    email = email.lower()
    if email == ctx.user_email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove yourself.",
        )

    pool = await get_pool()
    member = await pool.fetchrow(
        "SELECT role FROM organization_members WHERE organization_id = $1::uuid AND email = $2 AND is_active = TRUE",
        ctx.org_id,
        email,
    )
    if not member:
        raise HTTPException(status_code=404, detail="Active member not found.")

    # Admins cannot remove owners
    if member["role"] == "owner" and ctx.role == "admin" and not ctx.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot remove owners.",
        )

    await pool.execute(
        "UPDATE organization_members SET is_active = FALSE WHERE organization_id = $1::uuid AND email = $2",
        ctx.org_id,
        email,
    )
    logger.info(f"Removed member {email} from org {ctx.org_id} by {ctx.user_email}")
