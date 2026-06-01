"""VK (ВКонтакте) Callback API webhook endpoint."""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.dependencies import CommonDependencies
from app.services.channel_binding_service import ChannelBindingService
from app.services.vk_service import VKService
from app.storage.resolver import get_secrets_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def get_vk_service(deps: CommonDependencies = Depends()) -> VKService:
    from app.config import get_settings
    settings = get_settings()
    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.db, secrets_manager)
    return VKService(binding_service, deps.db, settings)


@router.post("/vk/webhook/{binding_id}")
async def handle_vk_webhook(
    binding_id: str,
    request: Request,
    vk_service: VKService = Depends(get_vk_service),
):
    """Handle VK Callback API events.

    VK expects one of:
    - The confirmation_code string (for 'confirmation' type)
    - The literal string 'ok' (for all other events)

    Both must be returned as plain text, not JSON.
    """
    try:
        UUID(binding_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid binding ID format",
        )

    try:
        body = await request.body()
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("VK webhook: invalid JSON for binding %s: %s", binding_id, exc)
        return Response(content="ok", media_type="text/plain")

    logger.info(
        "VK webhook event: binding=%s type=%s",
        binding_id,
        payload.get("type", "unknown"),
    )

    try:
        from app.services.webhook_event_store import add_webhook_event
        add_webhook_event("vk_webhook", payload)
    except Exception:
        pass

    try:
        response_text = await vk_service.handle_webhook_event(payload, binding_id)
    except Exception as exc:
        logger.exception("VK webhook handler error (binding=%s): %s", binding_id, exc)
        response_text = "ok"

    # VK strictly requires plain text response, not JSON
    return Response(content=response_text, media_type="text/plain")
