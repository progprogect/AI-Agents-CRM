"""WhatsApp Cloud API webhook endpoints."""

import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.dependencies import CommonDependencies
from app.services.channel_binding_service import ChannelBindingService
from app.storage.resolver import get_secrets_manager

logger = logging.getLogger(__name__)

router = APIRouter()

_WHATSAPP_VERIFY_TOKEN_KEY = "whatsapp_verify_token"
_WHATSAPP_APP_SECRET_KEY = "whatsapp_app_secret"


async def _get_whatsapp_settings() -> dict[str, str | None]:
    """Read WhatsApp settings: DB takes priority, env var is the fallback."""
    from app.config import get_settings
    settings = get_settings()

    verify_token: str | None = None
    app_secret: str | None = None

    # Try DB first (UI-configured values)
    if settings.secret_encryption_key:
        try:
            from app.storage.postgres_secrets import get_postgres_secrets_manager
            mgr = get_postgres_secrets_manager()
            verify_token = await mgr.get_global_setting(_WHATSAPP_VERIFY_TOKEN_KEY)
            app_secret = await mgr.get_global_setting(_WHATSAPP_APP_SECRET_KEY)
        except Exception as exc:
            logger.warning(f"WhatsApp: could not read DB settings: {exc}")

    # Fall back to env vars (WHATSAPP_VERIFY_TOKEN / WHATSAPP_APP_SECRET)
    if not verify_token:
        verify_token = settings.whatsapp_verify_token or None
    if not app_secret:
        app_secret = settings.whatsapp_app_secret or None

    return {"verify_token": verify_token, "app_secret": app_secret}


@router.get("/whatsapp/webhook")
async def verify_webhook(
    mode: str = Query(..., alias="hub.mode"),
    token: str = Query(..., alias="hub.verify_token"),
    challenge: str = Query(..., alias="hub.challenge"),
):
    """
    Verify WhatsApp webhook (Meta sends GET during webhook configuration).

    Meta sends:
      - hub.mode=subscribe
      - hub.verify_token=<token set in Meta Console>
      - hub.challenge=<random string to echo back>
    """
    logger.info(f"WhatsApp webhook verification: mode={mode}")

    settings = await _get_whatsapp_settings()
    verify_token = settings.get("verify_token")

    if not verify_token:
        logger.warning("WhatsApp verify token not configured — rejecting verification")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="WhatsApp not configured. Set verify token in Channel Settings.",
        )

    if mode == "subscribe" and token == verify_token:
        logger.info("WhatsApp webhook verified successfully")
        return PlainTextResponse(content=challenge, status_code=200)

    logger.warning("WhatsApp webhook verification failed: token mismatch")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Webhook verification failed",
    )


@router.post("/whatsapp/webhook")
async def handle_webhook(
    request: Request,
    deps: CommonDependencies = Depends(),
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
):
    """Handle incoming WhatsApp Cloud API events."""
    body = await request.body()

    # Optionally verify signature
    settings = await _get_whatsapp_settings()
    app_secret = settings.get("app_secret")
    if app_secret and x_hub_signature_256:
        expected = "sha256=" + hmac.new(
            app_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, x_hub_signature_256):
            logger.warning("WhatsApp webhook signature verification failed")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid webhook signature",
            )

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        return {"status": "ok"}

    logger.info(
        "WhatsApp webhook event received",
        extra={"payload_keys": list(payload.keys())},
    )

    # Route each entry to the matching channel binding
    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)

    try:
        from app.services.whatsapp_service import WhatsAppService
        from app.config import get_settings
        wa_service = WhatsAppService(binding_service, deps.dynamodb, get_settings())
        await wa_service.handle_webhook_event(payload)
    except Exception as exc:
        logger.error(f"WhatsApp webhook handling error: {exc}", exc_info=True)

    # Always return 200 so Meta doesn't retry
    return {"status": "ok"}
