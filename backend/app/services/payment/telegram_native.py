"""Telegram-native payment provider (YooKassa / Telegram Stars).

For YooKassa: currency is RUB/USD/etc, provider_token required.
For Stars:    currency is XTR, no provider_token, digital goods only,
              no pre_checkout_query step.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.models.payment import PaymentPlan, PaymentSettings
from app.services.payment.base import AbstractPaymentProvider

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


class TelegramNativeProvider(AbstractPaymentProvider):

    async def send_plans_keyboard(
        self,
        bot_token: str,
        chat_id: str,
        plans: list[PaymentPlan],
        settings: PaymentSettings,
    ) -> None:
        """Send a message with inline buttons, one per plan."""
        if not plans:
            return

        text = (
            f"*{settings.payment_title}*\n{settings.payment_description}\n\n"
            "Выберите план подписки:"
        )

        buttons = [
            [
                {
                    "text": f"{p.name} — {_format_price(p.price_amount, p.currency)}",
                    "callback_data": f"pay_plan:{p.plan_id}",
                }
            ]
            for p in plans
        ]

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{TELEGRAM_API_BASE}{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "reply_markup": {"inline_keyboard": buttons},
                },
            )
            if resp.status_code != 200:
                logger.warning(
                    "send_plans_keyboard failed for chat %s: %s", chat_id, resp.text
                )

    async def send_invoice(
        self,
        bot_token: str,
        chat_id: str,
        plan: PaymentPlan,
        payload: str,
        settings: PaymentSettings,
    ) -> None:
        """Send a Telegram invoice for the selected plan."""
        body: dict = {
            "chat_id": chat_id,
            "title": settings.payment_title,
            "description": f"{plan.name}: {settings.payment_description}",
            "payload": payload,
            "currency": plan.currency,
            "prices": [{"label": plan.name, "amount": plan.price_amount}],
        }

        # Stars (XTR) does not use a provider_token
        if plan.currency != "XTR":
            secret_name = (
                settings.sandbox_secret_name
                if settings.sandbox_mode
                else settings.provider_secret_name
            )
            if not secret_name:
                logger.error("No payment provider_secret_name configured for binding %s", settings.binding_id)
                return
            from app.storage.resolver import get_secrets_manager
            sm = get_secrets_manager()
            body["provider_token"] = await sm.get_payment_token(secret_name)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{TELEGRAM_API_BASE}{bot_token}/sendInvoice",
                json=body,
            )
            if resp.status_code != 200:
                logger.warning("sendInvoice failed for chat %s: %s", chat_id, resp.text)

    async def answer_pre_checkout(
        self,
        bot_token: str,
        query_id: str,
        ok: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        body: dict = {"pre_checkout_query_id": query_id, "ok": ok}
        if not ok and error_message:
            body["error_message"] = error_message
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{TELEGRAM_API_BASE}{bot_token}/answerPreCheckoutQuery",
                json=body,
            )
            if resp.status_code != 200:
                logger.warning("answerPreCheckoutQuery failed: %s", resp.text)

    async def refund(self, bot_token: str, user_id: str, charge_id: str) -> bool:
        """Refund a Stars payment via Telegram API."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{TELEGRAM_API_BASE}{bot_token}/refundStarPayment",
                json={"user_id": user_id, "telegram_payment_charge_id": charge_id},
            )
        ok = resp.status_code == 200 and resp.json().get("result") is True
        if not ok:
            logger.warning("refundStarPayment failed for user %s charge %s: %s", user_id, charge_id, resp.text)
        return ok


def _format_price(amount: int, currency: str) -> str:
    if currency == "XTR":
        return f"{amount} ★"
    major = amount / 100
    symbols = {"RUB": "₽", "USD": "$", "EUR": "€"}
    sym = symbols.get(currency, currency)
    return f"{major:.0f} {sym}"
