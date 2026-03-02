"""CRM API — stage management and conversation CRM stage updates."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.auth import require_admin
from app.dependencies import CommonDependencies
from app.models.crm import CreateCRMStageRequest, CRMStage, UpdateCRMStageRequest
from app.storage.postgres_crm import PostgresCRMStorage

logger = logging.getLogger(__name__)

router = APIRouter()

_crm_storage = PostgresCRMStorage()


# ── Stages CRUD ───────────────────────────────────────────────────────────────

@router.get("/stages", response_model=list[CRMStage])
async def list_stages(_admin: str = require_admin()):
    """Return all CRM stages ordered by position."""
    return await _crm_storage.list_stages()


@router.post("/stages", response_model=CRMStage, status_code=status.HTTP_201_CREATED)
async def create_stage(body: CreateCRMStageRequest, _admin: str = require_admin()):
    """Create a new CRM stage."""
    return await _crm_storage.create_stage(name=body.name, color=body.color)


@router.put("/stages/{stage_id}", response_model=CRMStage)
async def update_stage(
    stage_id: str,
    body: UpdateCRMStageRequest,
    _admin: str = require_admin(),
):
    """Update a CRM stage (name, color, position)."""
    existing = await _crm_storage.get_stage(stage_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Stage not found")

    updated = await _crm_storage.update_stage(
        stage_id=stage_id,
        name=body.name,
        color=body.color,
        position=body.position,
    )
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update stage")
    return updated


@router.delete("/stages/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stage(stage_id: str, _admin: str = require_admin()):
    """Delete a CRM stage. Fails if it is a default stage or has conversations."""
    existing = await _crm_storage.get_stage(stage_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Stage not found")
    if existing.is_default:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a default system stage",
        )
    deleted = await _crm_storage.delete_stage(stage_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stage has conversations assigned — reassign them first",
        )


# ── Conversation CRM stage update ─────────────────────────────────────────────

class UpdateCRMStageBody(BaseModel):
    crm_stage_id: str


@router.patch(
    "/conversations/{conversation_id}/crm-stage",
    response_model=dict,
)
async def update_conversation_crm_stage(
    conversation_id: str,
    body: UpdateCRMStageBody,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Assign a CRM stage to a conversation."""
    stage = await _crm_storage.get_stage(body.crm_stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail="CRM stage not found")

    updated = await deps.dynamodb.update_conversation(
        conversation_id=conversation_id,
        crm_stage_id=body.crm_stage_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        from app.api.admin_websocket import get_admin_broadcast_manager
        broadcast_manager = get_admin_broadcast_manager()
        await broadcast_manager.broadcast_conversation_update(updated)
    except Exception as exc:
        logger.warning(f"Failed to broadcast crm stage update: {exc}")

    return {
        "conversation_id": conversation_id,
        "crm_stage_id": body.crm_stage_id,
        "stage_name": stage.name,
        "message": "CRM stage updated successfully",
    }
