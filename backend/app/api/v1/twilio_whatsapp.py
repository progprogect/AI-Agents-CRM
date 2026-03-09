"""Twilio WhatsApp webhook endpoint."""

import logging

from fastapi import APIRouter, Depends, Request, Response

from app.dependencies import CommonDependencies
from app.services.twilio_service import TwilioWhatsAppService
from app.services.webhook_event_store import add_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/twilio/whatsapp/webhook")
async def twilio_whatsapp_webhook(
    request: Request,
    deps: CommonDependencies = Depends(),
):
    """Receive incoming WhatsApp messages forwarded by Twilio.

    Twilio sends application/x-www-form-urlencoded POST requests.
    Optionally validates X-Twilio-Signature if the binding's auth token is available.

    Twilio expects a 200 OK response (optionally with TwiML body).
    We return an empty TwiML response — the AI reply is sent via the REST API,
    not via TwiML, to keep the architecture consistent with the Meta flow.
    """
    from app.services.channel_binding_service import ChannelBindingService
    from app.storage.resolver import get_secrets_manager

    form_data = dict(await request.form())

    # Store raw event for debugging (mirrors whatsapp.py behaviour)
    add_webhook_event("twilio_whatsapp", form_data)

    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)
    twilio_service = TwilioWhatsAppService(deps.dynamodb)

    # Optional signature validation — log only, never block.
    # Rejecting on signature mismatch is unsafe behind a reverse-proxy (Railway, nginx)
    # because request.url is the internal URL (http://) while Twilio signs the public
    # HTTPS URL, causing permanent HMAC mismatch that silently drops all messages.
    twilio_signature = request.headers.get("X-Twilio-Signature", "")
    if twilio_signature:
        to_number = form_data.get("To", "").replace("whatsapp:", "")
        try:
            binding = await twilio_service._find_binding_by_to_number(
                binding_service, to_number
            )
            if binding:
                auth_token = await binding_service.get_access_token(binding.binding_id)
                valid = twilio_service.validate_signature(
                    auth_token, str(request.url), form_data, twilio_signature
                )
                if not valid:
                    logger.warning(
                        "Twilio webhook signature mismatch (processing anyway — "
                        "expected when behind a reverse-proxy)"
                    )
        except Exception as sig_err:
            logger.warning(f"Twilio signature check skipped: {sig_err}")

    logger.info(
        f"Twilio webhook received: From={form_data.get('From', '-')} "
        f"To={form_data.get('To', '-')} "
        f"Body={form_data.get('Body', '')[:60]!r}"
    )

    # Process message
    try:
        await twilio_service.handle_webhook(form_data, binding_service)
    except Exception as exc:
        logger.error(f"Twilio webhook processing error: {exc}", exc_info=True)

    # Empty TwiML — the AI reply is sent via REST API asynchronously
    return Response(content="<?xml version='1.0' encoding='UTF-8'?><Response/>", media_type="text/xml")
