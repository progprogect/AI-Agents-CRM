"""PaymentService: high-level operations used by channel handlers."""

from __future__ import annotations

import logging
from typing import Optional

from app.models.payment import (
    PaymentPlan,
    PaymentSettings,
    UserSubscription,
    activate_subscription,
    create_transaction_idempotent,
    get_payment_plan,
    get_payment_settings,
    list_payment_plans,
    make_invoice_payload,
    set_invoice_sent,
    verify_invoice_payload,
)
from app.services.payment.factory import get_payment_provider
from app.services.payment.guard import invalidate_cache

logger = logging.getLogger(__name__)


class PaymentService:
    """Orchestrates invoice sending and subscription activation."""

    def __init__(self, binding_id: str, bot_token: str, secret_key: str):
        self.binding_id = binding_id
        self.bot_token = bot_token
        self.secret_key = secret_key

    async def send_plans_keyboard(
        self,
        chat_id: str,
        settings: Optional[PaymentSettings] = None,
    ) -> None:
        """Send plan selection keyboard to user and mark invoice_sent_at."""
        if settings is None:
            settings = await get_payment_settings(self.binding_id)
        if not settings:
            return

        plans = await list_payment_plans(self.binding_id)
        if not plans:
            logger.warning("No active payment plans for binding %s", self.binding_id)
            return

        provider = get_payment_provider(settings)
        await provider.send_plans_keyboard(self.bot_token, chat_id, plans, settings)

        from app.models.payment import get_or_create_subscription
        sub = await get_or_create_subscription(self.binding_id, chat_id)
        await set_invoice_sent(sub.sub_id)
        await invalidate_cache(self.binding_id, chat_id)

    async def send_invoice_for_plan(
        self,
        chat_id: str,
        plan_id: str,
        settings: Optional[PaymentSettings] = None,
    ) -> None:
        """Send a direct invoice for a specific plan (called from callback_query handler)."""
        if settings is None:
            settings = await get_payment_settings(self.binding_id)
        if not settings:
            return

        plan = await get_payment_plan(plan_id)
        if not plan:
            logger.warning("Plan %s not found", plan_id)
            return

        payload_str = make_invoice_payload(
            self.binding_id, chat_id, plan_id, self.secret_key
        )
        provider = get_payment_provider(settings)
        await provider.send_invoice(self.bot_token, chat_id, plan, payload_str, settings)

    async def handle_successful_payment(
        self,
        payment_data: dict,
        chat_id: str,
    ) -> Optional[UserSubscription]:
        """Process a Telegram successful_payment update.

        Returns the activated UserSubscription, or None if duplicate/invalid.
        """
        charge_id: str = payment_data.get("telegram_payment_charge_id", "")
        payload_str: str = payment_data.get("invoice_payload", "")

        # Verify signed payload
        result = verify_invoice_payload(payload_str, self.secret_key)
        if not result:
            logger.warning(
                "Invalid invoice_payload from chat_id=%s payload=%s",
                chat_id,
                payload_str,
            )
            return None

        b_id, user_id, plan_id = result

        plan = await get_payment_plan(plan_id)
        if not plan:
            logger.error("Plan %s from payload not found", plan_id)
            return None

        from app.models.payment import get_or_create_subscription
        sub = await get_or_create_subscription(self.binding_id, chat_id)

        created = await create_transaction_idempotent(
            sub_id=sub.sub_id,
            binding_id=self.binding_id,
            external_user_id=chat_id,
            provider="telegram_native",
            plan_id=plan_id,
            charge_id=charge_id,
            amount=payment_data.get("total_amount"),
            currency=payment_data.get("currency"),
            invoice_payload=payload_str,
            raw_payload=payment_data,
        )

        if not created:
            logger.info("Duplicate successful_payment charge_id=%s; skipping", charge_id)
            return None

        activated = await activate_subscription(self.binding_id, chat_id, plan)
        await invalidate_cache(self.binding_id, chat_id)
        logger.info(
            "Subscription activated for user %s via plan %s (charge %s)",
            chat_id,
            plan_id,
            charge_id,
        )
        return activated

    async def answer_pre_checkout(
        self,
        bot_token: str,
        query_id: str,
        payload_str: str,
    ) -> None:
        """Verify payload and answer pre_checkout_query."""
        result = verify_invoice_payload(payload_str, self.secret_key)
        ok = result is not None
        if not ok:
            logger.warning("Pre-checkout: invalid payload %s", payload_str)

        settings = await get_payment_settings(self.binding_id)
        if not settings:
            return
        provider = get_payment_provider(settings)
        await provider.answer_pre_checkout(
            bot_token=bot_token,
            query_id=query_id,
            ok=ok,
            error_message="Ошибка подтверждения платежа" if not ok else None,
        )
