"""Agents API endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from app.api.auth import require_admin
from app.api.tenant import TenantContext, get_tenant_context, require_role
from app.api.exceptions import AgentNotFoundError, InvalidAgentConfigError
from app.api.schemas import AgentIDValidator
from app.dependencies import CommonDependencies
from app.models.agent_config import AgentConfig
from app.services.rag_service import get_rag_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _merge_agent_config(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge incoming config onto existing. Top-level shallow merge; `escalation` dict is deep-merged
    so a partial PUT like {\"escalation\": {\"enabled\": false}} does not drop detect_contact, etc.
    """
    merged = {**existing, **incoming}
    if "escalation" in incoming and isinstance(incoming.get("escalation"), dict):
        old_esc = existing.get("escalation")
        if isinstance(old_esc, dict):
            merged["escalation"] = {**old_esc, **incoming["escalation"]}
        else:
            merged["escalation"] = dict(incoming["escalation"])
    return merged


class CreateAgentRequest(BaseModel, AgentIDValidator):
    """Request to create an agent."""

    agent_id: str = Field(..., description="Agent ID")
    config: dict[str, Any] = Field(..., description="Agent configuration")


class AgentResponse(BaseModel):
    """Agent response model."""

    agent_id: str
    config: dict[str, Any]
    created_at: str
    updated_at: str
    is_active: bool


@router.post(
    "/",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent(
    request: CreateAgentRequest,
    deps: CommonDependencies = Depends(),
    ctx: TenantContext = require_role("owner", "admin"),
):
    """Create a new agent."""
    org_id = ctx.org_id

    # Check if agent already exists
    existing_agent = await deps.dynamodb.get_agent(request.agent_id)
    if existing_agent:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent with ID '{request.agent_id}' already exists",
        )

    # Validate agent configuration
    try:
        agent_config = AgentConfig.from_dict(request.config)
        if agent_config.agent_id != request.agent_id:
            raise InvalidAgentConfigError(
                "Agent ID in config must match agent_id in request",
                validation_errors={"agent_id_mismatch": True},
            )
    except Exception as e:
        if isinstance(e, InvalidAgentConfigError):
            raise
        raise InvalidAgentConfigError(
            f"Invalid agent configuration: {str(e)}",
            validation_errors={"parse_error": str(e)},
        )

    agent_data = await deps.dynamodb.create_agent(
        request.agent_id, request.config, organization_id=org_id
    )

    # Index RAG documents if enabled
    if agent_config.rag.enabled and agent_config.rag.sources:
        try:
            rag_service = get_rag_service()
            index_name = agent_config.rag.vector_store.get(
                "index_name", f"agent_{request.agent_id}_documents"
            )
            documents = []
            for source in agent_config.rag.sources:
                if source.get("content"):
                    documents.append({
                        "id": source.get("id", f"doc_{len(documents)}"),
                        "title": source.get("title", "Untitled"),
                        "content": source.get("content", ""),
                    })

            if documents:
                success_count, failed_count = await rag_service.index_documents(
                    agent_id=request.agent_id,
                    documents=documents,
                    index_name=index_name,
                    agent_config=agent_config,
                )
                logger.info(
                    f"Indexed {success_count} RAG documents for agent {request.agent_id}, "
                    f"{failed_count} failed",
                )
        except Exception as e:
            logger.error(
                f"Failed to index RAG documents for agent {request.agent_id}: {str(e)}",
                exc_info=True,
            )

    return AgentResponse(**agent_data)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    deps: CommonDependencies = Depends(),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get agent by ID. Enforces org isolation."""
    org_id = None if ctx.is_platform_admin else ctx.org_id
    agent = await deps.dynamodb.get_agent(agent_id, organization_id=org_id)
    if not agent:
        raise AgentNotFoundError(agent_id)
    return AgentResponse(**agent)


@router.get("/", response_model=list[AgentResponse])
async def list_agents(
    active_only: bool = Query(default=True, description="Filter only active agents"),
    deps: CommonDependencies = Depends(),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List agents for the current organization."""
    org_id = None if ctx.is_platform_admin else ctx.org_id
    agents = await deps.dynamodb.list_agents(active_only=active_only, organization_id=org_id)
    return [AgentResponse(**agent) for agent in agents]


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    config: dict[str, Any],
    deps: CommonDependencies = Depends(),
    ctx: TenantContext = require_role("owner", "admin"),
):
    """Update agent configuration."""
    org_id = None if ctx.is_platform_admin else ctx.org_id
    existing = await deps.dynamodb.get_agent(agent_id, organization_id=org_id)
    if not existing:
        raise AgentNotFoundError(agent_id)

    updated_config = _merge_agent_config(existing.get("config", {}) or {}, config)

    try:
        agent_config = AgentConfig.from_dict(updated_config)
        if agent_config.agent_id != agent_id:
            raise InvalidAgentConfigError(
                "Cannot change agent_id",
                validation_errors={"agent_id_immutable": True},
            )
    except Exception as e:
        if isinstance(e, InvalidAgentConfigError):
            raise
        raise InvalidAgentConfigError(
            f"Invalid agent configuration: {str(e)}",
            validation_errors={"parse_error": str(e)},
        )

    agent_data = await deps.dynamodb.create_agent(agent_id, updated_config, organization_id=org_id)
    return AgentResponse(**agent_data)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    deps: CommonDependencies = Depends(),
    ctx: TenantContext = require_role("owner", "admin"),
):
    """Delete agent (soft delete by setting is_active=False)."""
    org_id = None if ctx.is_platform_admin else ctx.org_id
    existing = await deps.dynamodb.get_agent(agent_id, organization_id=org_id)
    if not existing:
        raise AgentNotFoundError(agent_id)

    updated = await deps.dynamodb.update_agent_status(
        agent_id, is_active=False, organization_id=org_id
    )
    if not updated:
        raise AgentNotFoundError(agent_id)

    return None
