"""Twilio WhatsApp webhook endpoint."""

import logging

from fastapi import APIRouter, Depends, Request, Response

from app.dependencies import CommonDependencies
from app.services.twilio_service import TwilioWhatsAppService
from app.services.webhook_event_store import webhook_event_store

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
    await webhook_event_store.store(
        channel="twilio_whatsapp",
        event_type="incoming_message",
        payload=form_data,
    )

    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)
    twilio_service = TwilioWhatsAppService(deps.dynamodb)

    # Optional signature validation.
    # We validate only when we can resolve the binding's auth token, which requires
    # knowing the To number first — extracted from form_data.
    twilio_signature = request.headers.get("X-Twilio-Signature", "")
    to_number = form_data.get("To", "").replace("whatsapp:", "")

    if twilio_signature and to_number:
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
                        "Twilio webhook signature validation failed — rejecting request"
                    )
                    return Response(status_code=403)
        except Exception as sig_err:
            # Don't block delivery if signature check itself errors
            logger.warning(f"Twilio signature check error (skipping): {sig_err}")

    # Process message
    try:
        await twilio_service.handle_webhook(form_data, binding_service)
    except Exception as exc:
        logger.error(f"Twilio webhook processing error: {exc}", exc_info=True)
        # Still return 200 so Twilio doesn't retry indefinitely

    # Empty TwiML — the AI reply is sent via REST API asynchronously
    return Response(content="<?xml version='1.0' encoding='UTF-8'?><Response/>", media_type="text/xml")
