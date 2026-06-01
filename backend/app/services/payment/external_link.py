"""External-link payment provider (Stripe, custom URL).

Works across any channel: sends a text message with a payment URL.
pre_checkout / refund are not supported natively (handled outside the bot).
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.models.payment import PaymentPlan, PaymentSettings
from app.services.payment.base import AbstractPaymentProvider

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


class ExternalLinkProvider(AbstractPaymentProvider):

    async def get_payment_message(
        self,
        plans: list[PaymentPlan],
        settings: PaymentSettings,
    ) -> tuple[str, list[dict]]:
        """Build payment text and button list — channel-agnostic.

        Returns:
            (text, buttons) where buttons is a list of {"name": str, "url": str | None, "plan_id": str}
            Callers use this to build native keyboard for their channel (VK openlink, Max link, etc.)
        """
        if not plans:
            return settings.payment_title, []

        lines = [f"{settings.payment_title}\n{settings.payment_description}\n"]
        for p in plans:
            limit_text = f", {p.messages_limit} сообщений" if p.messages_limit else ""
            lines.append(f"• {p.name}: {_format_price(p.price_amount, p.currency)}{limit_text}")
        text = "\n".join(lines) + "\n\nВыберите план для оплаты:"

        buttons = []
        for p in plans:
            pay_url = await self._get_checkout_url(settings, p)
            buttons.append({"name": p.name, "url": pay_url, "plan_id": p.plan_id})

        return text, buttons

    async def send_plans_keyboard(
        self,
        bot_token: str,
        chat_id: str,
        plans: list[PaymentPlan],
        settings: PaymentSettings,
    ) -> None:
        """Show available plans via Telegram inline keyboard with external URL buttons."""
        if not plans:
            return

        text, pay_buttons = await self.get_payment_message(plans, settings)
        # Re-add markdown formatting for Telegram
        lines = text.split("\n")
        if lines:
            lines[0] = f"*{settings.payment_title}*"
        text = "\n".join(lines)

        inline_buttons = []
        for btn in pay_buttons:
            if btn["url"]:
                inline_buttons.append([{"text": btn["name"], "url": btn["url"]}])
            else:
                inline_buttons.append([{"text": btn["name"], "callback_data": f"pay_plan:{btn['plan_id']}"}])

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{TELEGRAM_API_BASE}{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "reply_markup": {"inline_keyboard": inline_buttons},
                },
            )
            if resp.status_code != 200:
                logger.warning("external link send_plans_keyboard failed: %s", resp.text)

    async def send_invoice(
        self,
        bot_token: str,
        chat_id: str,
        plan: PaymentPlan,
        payload: str,
        settings: PaymentSettings,
    ) -> None:
        """Send payment URL as a text message via Telegram."""
        pay_url = await self._get_checkout_url(settings, plan)
        if not pay_url:
            logger.warning("No checkout URL available for plan %s", plan.plan_id)
            return

        text = (
            f"*{plan.name}* — {_format_price(plan.price_amount, plan.currency)}\n"
            f"Для оплаты перейдите по ссылке:\n{pay_url}"
        )

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{TELEGRAM_API_BASE}{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False,
                },
            )
            if resp.status_code != 200:
                logger.warning("external link sendMessage failed: %s", resp.text)

    async def answer_pre_checkout(
        self,
        bot_token: str,
        query_id: str,
        ok: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """No-op for external link provider."""

    async def refund(self, bot_token: str, user_id: str, charge_id: str) -> bool:
        """Refunds must be issued manually via the external payment provider."""
        logger.info(
            "Refund requested for charge %s (external provider — process manually)", charge_id
        )
        return False

    async def _get_checkout_url(
        self, settings: PaymentSettings, plan: PaymentPlan
    ) -> Optional[str]:
        """Return a pre-built checkout URL if configured in settings."""
        # The URL template would be stored in the provider token secret as JSON:
        # {"checkout_url_template": "https://buy.stripe.com/xxx?plan={plan_id}"}
        secret_name = (
            settings.sandbox_secret_name
            if settings.sandbox_mode
            else settings.provider_secret_name
        )
        if not secret_name:
            return None
        try:
            from app.storage.resolver import get_secrets_manager
            sm = get_secrets_manager()
            import json as _json
            token_raw = await sm.get_payment_token(secret_name)
            data = _json.loads(token_raw) if token_raw.startswith("{") else {"url": token_raw}
            template = data.get("checkout_url_template") or data.get("url", "")
            if template:
                return template.replace("{plan_id}", plan.plan_id)
        except Exception as exc:
            logger.debug("Could not load checkout URL: %s", exc)
        return None


def _format_price(amount: int, currency: str) -> str:
    major = amount / 100
    symbols = {"RUB": "₽", "USD": "$", "EUR": "€"}
    sym = symbols.get(currency, currency)
    return f"{major:.0f} {sym}"
