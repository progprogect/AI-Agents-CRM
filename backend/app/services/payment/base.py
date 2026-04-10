"""Abstract payment provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.models.payment import PaymentPlan, PaymentSettings


class AbstractPaymentProvider(ABC):
    """All payment providers must implement this interface."""

    @abstractmethod
    async def send_plans_keyboard(
        self,
        bot_token: str,
        chat_id: str,
        plans: list[PaymentPlan],
        settings: PaymentSettings,
    ) -> None:
        """Send a message with an inline keyboard listing available plans.

        The user taps a plan → provider sends the actual invoice.
        """

    @abstractmethod
    async def send_invoice(
        self,
        bot_token: str,
        chat_id: str,
        plan: PaymentPlan,
        payload: str,
        settings: PaymentSettings,
    ) -> None:
        """Send a payment invoice for a specific plan."""

    @abstractmethod
    async def answer_pre_checkout(
        self,
        bot_token: str,
        query_id: str,
        ok: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """Respond to a pre_checkout_query from Telegram (must be within 10 s)."""

    @abstractmethod
    async def refund(
        self,
        bot_token: str,
        user_id: str,
        charge_id: str,
    ) -> bool:
        """Issue a refund.  Returns True on success."""
