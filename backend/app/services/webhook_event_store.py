"""In-memory store for recent webhook events (for testing/debugging)."""

import json
import logging
from datetime import datetime

from app.utils.datetime_utils import to_utc_iso_string, utc_now
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Store recent webhook events (last 100)
_recent_events: List[Dict[str, Any]] = []
_max_events = 100


def add_webhook_event(event_type: str, payload: Dict[str, Any]) -> None:
    """Add a webhook event to the store."""
    global _recent_events
    
    # Extract useful information from payload for easier access
    extracted_info = {}
    if event_type == "twilio_whatsapp":
        # Twilio sends form-encoded: From=whatsapp:+375..., To=whatsapp:+141..., Body=...
        raw_from = payload.get("From", "")
        raw_to = payload.get("To", "")
        body = payload.get("Body", "")
        message_sid = payload.get("MessageSid", "")
        if raw_from.startswith("whatsapp:"):
            extracted_info["sender_phone"] = raw_from.replace("whatsapp:", "").lstrip("+")
        if raw_to.startswith("whatsapp:"):
            extracted_info["phone_number_id"] = raw_to.replace("whatsapp:", "")
            extracted_info["display_phone"] = raw_to.replace("whatsapp:", "")
        if body:
            extracted_info["message_text"] = body
            extracted_info["message_type"] = "text"
        if message_sid:
            extracted_info["message_id"] = message_sid
        extracted_info["provider"] = "twilio"
    elif event_type == "instagram_webhook":
        entries = payload.get("entry", [])
        for entry in entries:
            messaging = entry.get("messaging", [])
            for msg_event in messaging:
                # Determine event type
                # IMPORTANT: Check for sender/recipient FIRST, as message_edit events may not have them
                event_type_name = "unknown"
                if "sender" in msg_event and "recipient" in msg_event:
                    # If sender and recipient exist, treat as message (even if message_edit is also present)
                    event_type_name = "message"
                elif "message" in msg_event:
                    event_type_name = "message"
                elif "message_edit" in msg_event:
                    event_type_name = "message_edit"
                elif "message_reaction" in msg_event:
                    event_type_name = "message_reaction"
                elif "message_unsend" in msg_event:
                    event_type_name = "message_unsend"
                
                extracted_info["event_type"] = event_type_name
                
                # Extract num_edit for message_edit events to understand if it's a new message
                if event_type_name == "message_edit":
                    edit_data = msg_event.get("message_edit", {})
                    num_edit = edit_data.get("num_edit", -1)
                    extracted_info["num_edit"] = num_edit
                    if num_edit == 0:
                        extracted_info["note"] = "message_edit with num_edit=0 (may be a new message, but no sender/recipient IDs)"
                    else:
                        extracted_info["note"] = "message_edit event - no sender/recipient IDs available"
                
                # Only extract IDs for message events (not message_edit, etc.)
                if event_type_name == "message":
                    sender = msg_event.get("sender", {})
                    recipient = msg_event.get("recipient", {})
                    message_data = msg_event.get("message", {})
                    
                    if sender.get("id"):
                        extracted_info["sender_id"] = sender.get("id")
                    if recipient.get("id"):
                        extracted_info["recipient_id"] = recipient.get("id")
                    if message_data.get("text"):
                        extracted_info["message_text"] = message_data.get("text")
                    if message_data.get("mid"):
                        extracted_info["message_id"] = message_data.get("mid")
                    if message_data.get("is_echo"):
                        extracted_info["is_echo"] = message_data.get("is_echo")
                    if message_data.get("is_self"):
                        extracted_info["is_self"] = message_data.get("is_self")
                # Note: message_edit handling moved above (before checking event_type_name == "message")
                
                break  # Only process first messaging event
            break  # Only process first entry
    
    event = {
        "id": f"webhook_{utc_now().timestamp()}",
        "type": event_type,
        "payload": payload,
        "extracted": extracted_info,  # Add extracted info for easier access
        "timestamp": to_utc_iso_string(utc_now()),
    }
    
    _recent_events.append(event)
    
    # Keep only last N events
    if len(_recent_events) > _max_events:
        _recent_events = _recent_events[-_max_events:]
    
    logger.info(
        f"Webhook event stored: {event_type} (total events: {len(_recent_events)})"
        + (f", sender_id={extracted_info.get('sender_id')}" if extracted_info.get("sender_id") else "")
    )


def get_recent_events(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent webhook events."""
    return _recent_events[-limit:]


def get_event_by_id(event_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific event by ID."""
    for event in _recent_events:
        if event["id"] == event_id:
            return event
    return None


def clear_events() -> int:
    """Clear all stored events. Returns number of cleared events."""
    global _recent_events
    count = len(_recent_events)
    _recent_events = []
    logger.info(f"Cleared {count} webhook events")
    return count

