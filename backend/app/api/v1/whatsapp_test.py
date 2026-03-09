"""WhatsApp API testing endpoints — supports both Meta Cloud API and Twilio providers."""

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import require_admin
from app.dependencies import CommonDependencies
from app.models.channel_binding import ChannelType
from app.services.channel_binding_service import ChannelBindingService
from app.storage.resolver import get_secrets_manager

logger = logging.getLogger(__name__)

router = APIRouter()

GRAPH_API_BASE = "https://graph.facebook.com/v18.0"
TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


class WhatsAppTestSendRequest(BaseModel):
    """Request to send a WhatsApp test message."""
    binding_id: str
    to: str           # recipient phone, international format without +, e.g. 375255092206
    message_text: str


class WhatsAppTestSendResponse(BaseModel):
    """Response from WhatsApp test send."""
    success: bool
    status_code: int
    response_data: dict[str, Any]
    phone_number_id: str | None = None
    provider: str | None = None
    error: str | None = None


@router.get("/whatsapp-test/bindings")
async def list_whatsapp_bindings(
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Return all active WhatsApp channel bindings for the test UI."""
    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)

    all_agents = await deps.dynamodb.list_agents()
    results = []
    for agent in all_agents:
        agent_id = agent.get("agent_id") or agent.get("pk", "")
        if not agent_id:
            continue
        bindings = await binding_service.get_bindings_by_agent(
            agent_id=agent_id,
            channel_type="whatsapp",
            active_only=False,
        )
        for b in bindings:
            meta = b.metadata or {}
            provider = meta.get("provider", "meta")
            results.append({
                "binding_id": b.binding_id,
                "agent_id": b.agent_id,
                "phone_number_id": b.channel_account_id,
                "display_name": b.channel_username or b.channel_account_id,
                "is_active": b.is_active,
                "is_verified": b.is_verified,
                "provider": provider,
            })

    return {"bindings": results}


@router.post("/whatsapp-test/send", response_model=WhatsAppTestSendResponse)
async def send_whatsapp_test_message(
    request: WhatsAppTestSendRequest,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Send a WhatsApp test message using a stored channel binding.

    Automatically detects provider (meta/twilio) from binding metadata
    and routes to the appropriate API.
    """
    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)

    binding = await binding_service.get_binding(request.binding_id)
    if not binding:
        raise HTTPException(status_code=404, detail="WhatsApp binding not found")
    if binding.channel_type != ChannelType.WHATSAPP:
        raise HTTPException(status_code=400, detail="Binding is not a WhatsApp binding")

    meta = binding.metadata or {}
    provider = meta.get("provider", "meta")

    try:
        access_token = await binding_service.get_access_token(request.binding_id)
    except Exception as e:
        logger.error(f"Failed to retrieve access token: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve access token: {e}")

    if provider == "twilio":
        return await _send_via_twilio(binding, access_token, request, meta)
    else:
        return await _send_via_meta(binding, access_token, request)


async def _send_via_twilio(
    binding: Any,
    auth_token: str,
    request: WhatsAppTestSendRequest,
    meta: dict,
) -> WhatsAppTestSendResponse:
    """Send via Twilio Programmable Messaging API."""
    account_sid = meta.get("account_sid", "")
    from_number = binding.channel_account_id  # stored as the Twilio WhatsApp from-number

    if not account_sid:
        return WhatsAppTestSendResponse(
            success=False,
            status_code=0,
            response_data={},
            phone_number_id=from_number,
            provider="twilio",
            error="Twilio binding is missing account_sid in metadata",
        )

    to_number = request.to.lstrip("+")
    from_addr = f"whatsapp:{from_number}" if not from_number.startswith("whatsapp:") else from_number
    to_addr = f"whatsapp:+{to_number}"

    url = f"{TWILIO_API_BASE}/Accounts/{account_sid}/Messages.json"
    logger.info(f"Twilio test send: from={from_addr} to={to_addr} account={account_sid}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                data={"From": from_addr, "To": to_addr, "Body": request.message_text},
                auth=(account_sid, auth_token),
            )
            response_data = response.json() if response.content else {}
            logger.info(f"Twilio send response: {response.status_code} {response_data}")

            if response.is_success:
                return WhatsAppTestSendResponse(
                    success=True,
                    status_code=response.status_code,
                    response_data=response_data,
                    phone_number_id=from_number,
                    provider="twilio",
                )
            else:
                error_msg = response_data.get("message", response_data.get("error_message", "Unknown error"))
                error_code = response_data.get("code", "")
                return WhatsAppTestSendResponse(
                    success=False,
                    status_code=response.status_code,
                    response_data=response_data,
                    phone_number_id=from_number,
                    provider="twilio",
                    error=f"Twilio error {error_code}: {error_msg}",
                )
    except Exception as e:
        logger.exception(f"Twilio test send exception: {e}")
        return WhatsAppTestSendResponse(
            success=False,
            status_code=0,
            response_data={},
            phone_number_id=from_number,
            provider="twilio",
            error=str(e),
        )


async def _send_via_meta(
    binding: Any,
    access_token: str,
    request: WhatsAppTestSendRequest,
) -> WhatsAppTestSendResponse:
    """Send via Meta WhatsApp Cloud API."""
    phone_number_id = binding.channel_account_id
    url = f"{GRAPH_API_BASE}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": request.to.lstrip("+"),
        "type": "text",
        "text": {"preview_url": False, "body": request.message_text},
    }
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    logger.info(f"Meta test send: phone_number_id={phone_number_id} to={request.to}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response_data = response.json() if response.content else {}
            logger.info(f"Meta send response: {response.status_code} {response_data}")

            if response.is_success:
                return WhatsAppTestSendResponse(
                    success=True,
                    status_code=response.status_code,
                    response_data=response_data,
                    phone_number_id=phone_number_id,
                    provider="meta",
                )
            else:
                error_info = response_data.get("error", {})
                error_msg = error_info.get("message", "Unknown error")
                error_code = error_info.get("code", "")
                return WhatsAppTestSendResponse(
                    success=False,
                    status_code=response.status_code,
                    response_data=response_data,
                    phone_number_id=phone_number_id,
                    provider="meta",
                    error=f"Error {error_code}: {error_msg}",
                )
    except Exception as e:
        logger.exception(f"Meta test send exception: {e}")
        return WhatsAppTestSendResponse(
            success=False,
            status_code=0,
            response_data={},
            phone_number_id=phone_number_id,
            provider="meta",
            error=str(e),
        )
