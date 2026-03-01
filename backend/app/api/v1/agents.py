"""Agents API endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from app.api.auth import require_admin
from app.api.exceptions import AgentNotFoundError, InvalidAgentConfigError
from app.api.schemas import AgentIDValidator
from app.dependencies import CommonDependencies
from app.models.agent_config import AgentConfig
from app.services.rag_service import get_rag_service

logger = logging.getLogger(__name__)

router = APIRouter()


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
    _admin: str = require_admin(),
):
    """Create a new agent."""
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
        # Ensure agent_id matches
        if agent_config.agent_id != request.agent_id:
            raise InvalidAgentConfigError(
                "Agent ID in config must match agent_id in request",
                validation_errors={"agent_id_mismatch": True},
            )

        # RAG: allow empty sources - user can add documents via RAG page after creation
    except Exception as e:
        if isinstance(e, InvalidAgentConfigError):
            raise
        raise InvalidAgentConfigError(
            f"Invalid agent configuration: {str(e)}",
            validation_errors={"parse_error": str(e)},
        )

    # Create agent in DynamoDB
    agent_data = await deps.dynamodb.create_agent(request.agent_id, request.config)

    # Index RAG documents if enabled
    if agent_config.rag.enabled and agent_config.rag.sources:
        try:
            rag_service = get_rag_service()
            index_name = agent_config.rag.vector_store.get(
                "index_name", f"agent_{request.agent_id}_documents"
            )

            # Prepare documents for indexing
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
                    extra={
                        "agent_id": request.agent_id,
                        "success_count": success_count,
                        "failed_count": failed_count,
                    },
                )

                if failed_count > 0:
                    logger.warning(
                        f"Some RAG documents failed to index for agent {request.agent_id}",
                        extra={"agent_id": request.agent_id, "failed_count": failed_count},
                    )
        except Exception as e:
            logger.error(
                f"Failed to index RAG documents for agent {request.agent_id}: {str(e)}",
                exc_info=True,
                extra={"agent_id": request.agent_id},
            )
            # Don't fail agent creation if RAG indexing fails
            # Agent will be created but RAG won't work until documents are indexed manually
            # In production, you might want to mark agent as "needs_indexing" or retry

    return AgentResponse(**agent_data)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    deps: CommonDependencies = Depends(),
):
    """Get agent by ID."""
    agent = await deps.dynamodb.get_agent(agent_id)
    if not agent:
        raise AgentNotFoundError(agent_id)
    return AgentResponse(**agent)


@router.get("/", response_model=list[AgentResponse])
async def list_agents(
    active_only: bool = Query(default=True, description="Filter only active agents"),
    deps: CommonDependencies = Depends(),
):
    """List all agents."""
    agents = await deps.dynamodb.list_agents(active_only=active_only)
    return [AgentResponse(**agent) for agent in agents]


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    config: dict[str, Any],
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Update agent configuration."""
    # Get existing agent
    existing = await deps.dynamodb.get_agent(agent_id)
    if not existing:
        raise AgentNotFoundError(agent_id)

    # Merge configs
    updated_config = {**existing.get("config", {}), **config}

    # Validate updated configuration
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

    agent_data = await deps.dynamodb.create_agent(agent_id, updated_config)
    return AgentResponse(**agent_data)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Delete agent (soft delete by setting is_active=False)."""
    existing = await deps.dynamodb.get_agent(agent_id)
    if not existing:
        raise AgentNotFoundError(agent_id)

    # Soft delete - update is_active status atomically
    updated = await deps.dynamodb.update_agent_status(agent_id, is_active=False)
    if not updated:
        raise AgentNotFoundError(agent_id)

    return None

