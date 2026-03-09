"""Telegram webhook API endpoints."""

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.auth import require_admin
from app.dependencies import CommonDependencies
from app.services.channel_binding_service import ChannelBindingService
from app.services.telegram_service import TelegramService
from app.storage.resolver import get_secrets_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def get_telegram_service(
    deps: CommonDependencies = Depends(),
) -> TelegramService:
    """Get Telegram service instance."""
    from app.config import get_settings

    settings = get_settings()
    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)
    return TelegramService(binding_service, deps.dynamodb, settings)


@router.post("/telegram/webhook/{binding_id}")
async def handle_webhook(
    binding_id: str,
    request: Request,
    telegram_service: TelegramService = Depends(get_telegram_service),
):
    """Handle Telegram webhook events (POST request for incoming messages)."""
    # Validate UUID format
    try:
        UUID(binding_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid binding ID format",
        )

    # Get request body
    try:
        body = await request.body()
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Telegram webhook payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    logger.info(
        "Telegram webhook event received",
        extra={"binding_id": binding_id, "payload_keys": list(payload.keys())},
    )

    # Store event for testing/debugging (optional)
    try:
        from app.services.webhook_event_store import add_webhook_event

        add_webhook_event("telegram_webhook", payload)
    except Exception as e:
        logger.debug(f"Failed to store webhook event: {e}")

    # Handle webhook event
    try:
        await telegram_service.handle_webhook_event(payload, binding_id)
    except Exception as e:
        logger.error(f"Error handling Telegram webhook event: {e}", exc_info=True)
        # Return 200 to prevent Telegram from retrying
        # Log the error for investigation
        return {"status": "error", "message": "Event processing failed"}

    return {"status": "ok"}


@router.post("/telegram/webhook/{binding_id}/set")
async def set_webhook(
    binding_id: str,
    deps: CommonDependencies = Depends(),
    telegram_service: TelegramService = Depends(get_telegram_service),
    _admin: str = require_admin(),
):
    """Set Telegram webhook URL for a binding."""
    # Validate UUID format
    try:
        UUID(binding_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid binding ID format",
        )

    # Get binding to verify it exists
    from app.services.channel_binding_service import ChannelBindingService
    from app.storage.resolver import get_secrets_manager

    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)
    binding = await binding_service.get_binding(binding_id)

    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Binding {binding_id} not found",
        )

    if binding.channel_type != "telegram":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Binding {binding_id} is not a Telegram binding",
        )

    # Construct webhook URL from configured app_url
    from app.config import get_settings

    settings = get_settings()
    base_url = settings.app_url.rstrip("/") if settings.app_url else ""
    webhook_url = f"{base_url}/api/v1/telegram/webhook/{binding_id}"

    # Set webhook via Telegram API
    success = await telegram_service.set_webhook(binding_id, webhook_url)

    if success:
        return {
            "status": "ok",
            "message": "Webhook set successfully",
            "webhook_url": webhook_url,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set webhook. Check logs for details.",
        )


@router.get("/telegram/webhook/{binding_id}/status")
async def get_webhook_status(
    binding_id: str,
    deps: CommonDependencies = Depends(),
    telegram_service: TelegramService = Depends(get_telegram_service),
    _admin: str = require_admin(),
):
    """Get Telegram webhook status for a binding."""
    # Validate UUID format
    try:
        UUID(binding_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid binding ID format",
        )

    # Get binding to verify it exists
    from app.services.channel_binding_service import ChannelBindingService
    from app.storage.resolver import get_secrets_manager

    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)
    binding = await binding_service.get_binding(binding_id)

    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Binding {binding_id} not found",
        )

    if binding.channel_type != "telegram":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Binding {binding_id} is not a Telegram binding",
        )

    # Get webhook info from Telegram API
    import httpx

    bot_token = await binding_service.get_access_token(binding_id)
    url = f"{telegram_service.TELEGRAM_API_BASE_URL}{bot_token}/getWebhookInfo"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)

            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to get webhook info: {response.text}",
                )

            result = response.json()

            if result.get("ok"):
                webhook_info = result.get("result", {})
                from app.config import get_settings as _get_settings
                _s = _get_settings()
                _base = _s.app_url.rstrip("/") if _s.app_url else ""
                return {
                    "status": "ok",
                    "webhook_info": webhook_info,
                    "expected_url": f"{_base}/api/v1/telegram/webhook/{binding_id}",
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Telegram API error: {result.get('description', 'Unknown error')}",
                )
    except Exception as e:
        logger.error(f"Error getting webhook status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get webhook status: {str(e)}",
        )
