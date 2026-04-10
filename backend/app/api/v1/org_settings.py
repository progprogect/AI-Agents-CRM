"""Organization settings API — LLM API keys management."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.tenant import TenantContext, require_role, get_tenant_context
from app.storage.postgres_secrets import get_postgres_secrets_manager

logger = logging.getLogger(__name__)

router = APIRouter()

SUPPORTED_PROVIDERS = {"openai", "google"}


def _mask_key(key: str) -> str:
    """Return a masked version of an API key for display."""
    if len(key) <= 8:
        return "***"
    return key[:4] + "..." + key[-4:]


class SetLLMKeyRequest(BaseModel):
    provider: str = Field(..., description="LLM provider: openai | google")
    key: str = Field(..., min_length=4, description="API key (plain text, stored encrypted)")


class LLMKeyStatus(BaseModel):
    provider: str
    is_set: bool
    masked_key: Optional[str] = None


@router.get("/org/llm-keys", response_model=list[LLMKeyStatus])
async def list_llm_keys(
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List which LLM API keys are configured for the current organization."""
    if not ctx.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No organization context.")

    secrets = get_postgres_secrets_manager()
    result = []
    for provider in sorted(SUPPORTED_PROVIDERS):
        key = await secrets.get_org_llm_key(ctx.org_id, provider)
        result.append(LLMKeyStatus(
            provider=provider,
            is_set=key is not None,
            masked_key=_mask_key(key) if key else None,
        ))
    return result


@router.put("/org/llm-keys", status_code=status.HTTP_204_NO_CONTENT)
async def set_llm_key(
    body: SetLLMKeyRequest,
    ctx: TenantContext = require_role("owner"),
):
    """Save (or update) an LLM API key for the current organization. Only owners can do this."""
    if body.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider '{body.provider}'. Supported: {', '.join(sorted(SUPPORTED_PROVIDERS))}",
        )
    if not ctx.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No organization context.")

    secrets = get_postgres_secrets_manager()
    try:
        await secrets.save_org_llm_key(ctx.org_id, body.provider, body.key.strip())
    except Exception as e:
        logger.error(f"Failed to save LLM key for org {ctx.org_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save API key.",
        )


@router.delete("/org/llm-keys/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_key(
    provider: str,
    ctx: TenantContext = require_role("owner"),
):
    """Remove an LLM API key for the current organization. Only owners can do this."""
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider '{provider}'.",
        )
    if not ctx.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No organization context.")

    secrets = get_postgres_secrets_manager()
    await secrets.delete_org_llm_key(ctx.org_id, provider)
