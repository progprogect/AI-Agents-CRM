"""Email service using Resend API."""

import asyncio
import logging
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


async def send_otp_email(to: str, code: str) -> bool:
    """Send OTP code via Resend API. Returns True on success."""
    settings = get_settings()

    if not settings.resend_api_key:
        logger.warning("RESEND_API_KEY not configured — email not sent (code logged instead)")
        logger.info(f"OTP code for {to}: {code}")
        return False

    def _send() -> dict:
        import resend  # type: ignore
        resend.api_key = settings.resend_api_key
        return resend.Emails.send({
            "from": settings.email_from,
            "to": to,
            "subject": "Your login code",
            "html": (
                "<div style='font-family:sans-serif;max-width:480px;margin:0 auto'>"
                "<h2 style='font-size:20px;margin-bottom:8px'>Admin Login</h2>"
                "<p style='color:#443C3C;margin-bottom:16px'>Your one-time login code:</p>"
                f"<div style='font-size:36px;font-weight:700;letter-spacing:8px;"
                f"color:#251D1C;padding:16px 24px;background:#EEEAE7;"
                f"border-radius:4px;display:inline-block'>{code}</div>"
                "<p style='color:#9A9590;font-size:13px;margin-top:16px'>"
                "Valid for 10 minutes. Do not share this code.</p>"
                "</div>"
            ),
        })

    try:
        result = await asyncio.to_thread(_send)
        logger.info(f"OTP email sent to {to}, id={result.get('id')}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email to {to}: {e}", exc_info=True)
        return False
