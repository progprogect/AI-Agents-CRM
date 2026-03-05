"""Instagram webhook API endpoints."""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.config import get_settings
from app.dependencies import CommonDependencies
from app.services.channel_binding_service import ChannelBindingService
from app.services.instagram_service import InstagramService
from app.storage.resolver import get_secrets_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def get_instagram_service(
    deps: CommonDependencies = Depends(),
) -> InstagramService:
    """Get Instagram service instance."""
    settings = get_settings()
    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)
    return InstagramService(binding_service, deps.dynamodb, settings)


async def _get_instagram_verify_token() -> str:
    """Read Instagram verify token: DB takes priority over env var."""
    from app.storage.postgres_secrets import get_postgres_secrets_manager
    mgr = get_postgres_secrets_manager()
    db_token = await mgr.get_global_setting("instagram_verify_token")
    if db_token:
        return db_token
    settings = get_settings()
    return settings.instagram_webhook_verify_token or ""


async def _get_instagram_app_secret() -> str:
    """Read Instagram app secret: DB takes priority over env var."""
    from app.storage.postgres_secrets import get_postgres_secrets_manager
    mgr = get_postgres_secrets_manager()
    db_secret = await mgr.get_global_setting("instagram_app_secret")
    if db_secret:
        return db_secret
    settings = get_settings()
    return settings.instagram_app_secret or ""


@router.get("/instagram/webhook")
async def verify_webhook(
    mode: str = Query(..., alias="hub.mode", description="Webhook verification mode"),
    token: str = Query(..., alias="hub.verify_token", description="Verification token"),
    challenge: str = Query(..., alias="hub.challenge", description="Challenge string"),
):
    """
    Verify Instagram webhook (GET request for webhook setup).

    Meta/Facebook sends GET request with:
    - hub.mode=subscribe
    - hub.verify_token=<your_token>
    - hub.challenge=<random_string>

    Server MUST return HTTP 200 with challenge string as plain text response body.
    Instagram requires EXACT challenge string, nothing else.
    """
    logger.info(f"Webhook verification request: mode={mode}, challenge={challenge}")

    verify_token = await _get_instagram_verify_token()
    if not verify_token:
        logger.warning("Instagram verify token not configured")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instagram not configured. Set verify token in Channel Settings.",
        )

    if mode == "subscribe" and token == verify_token:
        logger.info("Instagram webhook verified successfully")
        return PlainTextResponse(content=challenge, status_code=200)

    logger.warning(f"Instagram webhook verification failed: mode={mode}, token mismatch")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Webhook verification failed",
    )


@router.post("/instagram/webhook")
async def handle_webhook(
    request: Request,
    instagram_service: InstagramService = Depends(get_instagram_service),
    x_hub_signature_256: str | None = Header(
        None, alias="X-Hub-Signature-256", description="Webhook signature"
    ),
):
    """Handle Instagram webhook events (POST request for incoming messages)."""
    # Get request body
    body = await request.body()

    # Verify webhook signature if app secret is configured (DB takes priority over env var)
    app_secret = await _get_instagram_app_secret()
    if app_secret and x_hub_signature_256:
        if not instagram_service.verify_webhook_signature(body, x_hub_signature_256):
            logger.warning("Instagram webhook signature verification failed")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid webhook signature",
            )

    # Parse JSON payload
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse Instagram webhook payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    logger.info(
        "Instagram webhook event received",
        extra={"payload_keys": list(payload.keys())},
    )

    try:
        from app.services.webhook_event_store import add_webhook_event
        add_webhook_event("instagram_webhook", payload)
    except Exception as store_exc:
        logger.debug(f"Instagram: could not store event: {store_exc}")

    # Handle webhook event asynchronously
    # Note: In production, you might want to use a background task queue
    try:
        await instagram_service.handle_webhook_event(payload)
    except Exception as e:
        logger.error(f"Error handling webhook event: {e}", exc_info=True)
        # Return 200 to prevent Instagram from retrying
        # Log the error for investigation
        return {"status": "error", "message": "Event processing failed"}

    return {"status": "ok"}

