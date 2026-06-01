"""Max messenger Bot API webhook endpoint."""

import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import CommonDependencies
from app.services.channel_binding_service import ChannelBindingService
from app.services.max_service import MaxService
from app.storage.resolver import get_secrets_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def get_max_service(deps: CommonDependencies = Depends()) -> MaxService:
    from app.config import get_settings
    settings = get_settings()
    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.db, secrets_manager)
    return MaxService(binding_service, deps.db, settings)


@router.post("/max/webhook/{binding_id}")
async def handle_max_webhook(
    binding_id: str,
    request: Request,
    max_service: MaxService = Depends(get_max_service),
):
    """Handle Max Bot API webhook events.

    Max verifies requests by matching the X-Max-Bot-Api-Secret header
    against the secret stored in binding.metadata.webhook_secret.
    """
    try:
        UUID(binding_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid binding ID format",
        )

    received_secret: Optional[str] = request.headers.get("X-Max-Bot-Api-Secret")

    try:
        body = await request.body()
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Max webhook: invalid JSON for binding %s: %s", binding_id, exc)
        return {"status": "ok"}

    logger.info(
        "Max webhook event: binding=%s update_type=%s",
        binding_id,
        payload.get("update_type", "unknown"),
    )

    try:
        from app.services.webhook_event_store import add_webhook_event
        add_webhook_event("max_webhook", payload)
    except Exception:
        pass

    try:
        await max_service.handle_webhook_event(payload, binding_id, received_secret=received_secret)
    except Exception as exc:
        logger.exception("Max webhook handler error (binding=%s): %s", binding_id, exc)

    return {"status": "ok"}
