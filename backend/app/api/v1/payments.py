"""Payment API endpoints.

Provides CRUD for payment settings, plans, subscription management,
transaction history, and refunds.  All endpoints require admin auth.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.auth import require_admin
from app.dependencies import CommonDependencies
from app.models.payment import (
    FeatureGates,
    PaymentPlan,
    PaymentProvider,
    PaymentSettings,
    PaywallMessages,
    SubscriptionStatus,
    activate_subscription,
    create_payment_plan,
    delete_payment_plan,
    get_payment_plan,
    get_payment_settings,
    get_subscription,
    get_transaction,
    list_payment_plans,
    list_subscriptions,
    list_transactions,
    update_payment_plan,
    update_subscription,
    update_transaction_status,
    upsert_payment_settings,
)
from app.services.payment.guard import invalidate_cache
from app.utils.datetime_utils import to_utc_iso_string, utc_now

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request / response schemas ─────────────────────────────────────────────────


class FeatureGatesRequest(BaseModel):
    voice: bool = False
    images: bool = False


class PaywallMessagesRequest(BaseModel):
    voice: str = "Голосовые сообщения доступны по подписке."
    images: str = "Анализ изображений доступен по подписке."
    limit_reached: str = "Вы исчерпали лимит бесплатных сообщений. Выберите план подписки."


class UpsertPaymentSettingsRequest(BaseModel):
    enabled: bool = False
    provider: str = "telegram_native"
    free_messages: int = Field(default=10, ge=0)
    grace_messages: int = Field(default=3, ge=0)
    sandbox_mode: bool = False
    payment_title: Optional[str] = None
    payment_description: Optional[str] = None
    invoice_resend_hours: int = Field(default=24, ge=1)
    support_contact: Optional[str] = None
    # Paid features (migration 014)
    feature_gates: Optional[FeatureGatesRequest] = None
    paywall_messages: Optional[PaywallMessagesRequest] = None
    free_message_limit_enabled: bool = False


class SetPaymentTokenRequest(BaseModel):
    token: Optional[str] = None
    token_sandbox: Optional[str] = None


class CreatePlanRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    duration_days: int = Field(..., ge=1)
    price_amount: int = Field(..., ge=1)
    currency: str = Field(default="RUB", max_length=10)
    messages_limit: Optional[int] = Field(default=None, ge=1)
    sort_order: int = 0


class UpdatePlanRequest(BaseModel):
    name: Optional[str] = None
    duration_days: Optional[int] = Field(default=None, ge=1)
    price_amount: Optional[int] = Field(default=None, ge=1)
    currency: Optional[str] = None
    messages_limit: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class UpdateSubscriptionRequest(BaseModel):
    status: Optional[str] = None
    expires_at: Optional[datetime] = None
    messages_limit: Optional[int] = None
    messages_used: Optional[int] = None
    manual_override: Optional[bool] = None
    notes: Optional[str] = None
    feature_overrides: Optional[dict[str, bool]] = None


class SimulateSandboxPaymentRequest(BaseModel):
    external_user_id: str
    plan_id: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _settings_to_dict(s: PaymentSettings) -> dict:
    return {
        "setting_id": s.setting_id,
        "binding_id": s.binding_id,
        "enabled": s.enabled,
        "provider": s.provider.value if hasattr(s.provider, "value") else s.provider,
        "free_messages": s.free_messages,
        "grace_messages": s.grace_messages,
        "sandbox_mode": s.sandbox_mode,
        "has_live_token": bool(s.provider_secret_name),
        "has_sandbox_token": bool(s.sandbox_secret_name),
        "payment_title": s.payment_title,
        "payment_description": s.payment_description,
        "invoice_resend_hours": s.invoice_resend_hours,
        "support_contact": s.support_contact,
        # Paid features (migration 014)
        "feature_gates": s.feature_gates.model_dump(),
        "paywall_messages": s.paywall_messages.model_dump(),
        "free_message_limit_enabled": s.free_message_limit_enabled,
        "created_at": to_utc_iso_string(s.created_at),
        "updated_at": to_utc_iso_string(s.updated_at),
    }


def _plan_to_dict(p: PaymentPlan) -> dict:
    return {
        "plan_id": p.plan_id,
        "binding_id": p.binding_id,
        "name": p.name,
        "duration_days": p.duration_days,
        "price_amount": p.price_amount,
        "currency": p.currency,
        "messages_limit": p.messages_limit,
        "is_active": p.is_active,
        "sort_order": p.sort_order,
        "created_at": to_utc_iso_string(p.created_at),
    }


def _sub_to_dict(s: Any) -> dict:
    return {
        "sub_id": s.sub_id,
        "binding_id": s.binding_id,
        "external_user_id": s.external_user_id,
        "status": s.status.value if hasattr(s.status, "value") else s.status,
        "plan_id": s.plan_id,
        "expires_at": to_utc_iso_string(s.expires_at) if s.expires_at else None,
        "messages_used": s.messages_used,
        "messages_limit": s.messages_limit,
        "period_started_at": to_utc_iso_string(s.period_started_at) if s.period_started_at else None,
        "invoice_sent_at": to_utc_iso_string(s.invoice_sent_at) if s.invoice_sent_at else None,
        "grace_messages_used": s.grace_messages_used,
        "manual_override": s.manual_override,
        "notes": s.notes,
        "feature_overrides": s.feature_overrides,
        "created_at": to_utc_iso_string(s.created_at),
        "updated_at": to_utc_iso_string(s.updated_at),
    }


def _txn_to_dict(t: Any) -> dict:
    return {
        "txn_id": t.txn_id,
        "sub_id": t.sub_id,
        "binding_id": t.binding_id,
        "external_user_id": t.external_user_id,
        "provider": t.provider.value if hasattr(t.provider, "value") else t.provider,
        "provider_charge_id": t.provider_charge_id,
        "plan_id": t.plan_id,
        "amount": t.amount,
        "currency": t.currency,
        "status": t.status.value if hasattr(t.status, "value") else t.status,
        "created_at": to_utc_iso_string(t.created_at),
    }


# ── Payment settings ───────────────────────────────────────────────────────────


@router.get("/channel-bindings/{binding_id}/payment-settings")
async def get_payment_settings_endpoint(
    binding_id: str,
    _admin: str = require_admin(),
):
    settings = await get_payment_settings(binding_id)
    if not settings:
        return {
            "binding_id": binding_id,
            "enabled": False,
            "provider": "telegram_native",
            "free_messages": 10,
            "grace_messages": 3,
            "sandbox_mode": False,
            "has_live_token": False,
            "has_sandbox_token": False,
        }
    return _settings_to_dict(settings)


@router.put("/channel-bindings/{binding_id}/payment-settings")
async def upsert_payment_settings_endpoint(
    binding_id: str,
    request: UpsertPaymentSettingsRequest,
    _admin: str = require_admin(),
):
    existing = await get_payment_settings(binding_id)
    now = utc_now()

    # Merge feature_gates / paywall_messages with existing values (keep defaults if not provided)
    existing_gates = existing.feature_gates if existing else FeatureGates()
    existing_paywall = existing.paywall_messages if existing else PaywallMessages()

    if request.feature_gates is not None:
        new_gates = FeatureGates(**request.feature_gates.model_dump())
    else:
        new_gates = existing_gates

    if request.paywall_messages is not None:
        new_paywall = PaywallMessages(**request.paywall_messages.model_dump())
    else:
        new_paywall = existing_paywall

    settings = PaymentSettings(
        setting_id=existing.setting_id if existing else str(uuid.uuid4()),
        binding_id=binding_id,
        enabled=request.enabled,
        provider=PaymentProvider(request.provider),
        free_messages=request.free_messages,
        grace_messages=request.grace_messages,
        sandbox_mode=request.sandbox_mode,
        provider_secret_name=existing.provider_secret_name if existing else None,
        sandbox_secret_name=existing.sandbox_secret_name if existing else None,
        payment_title=request.payment_title or "Подписка",
        payment_description=request.payment_description or "Доступ к чат-боту",
        invoice_resend_hours=request.invoice_resend_hours,
        support_contact=request.support_contact,
        feature_gates=new_gates,
        paywall_messages=new_paywall,
        free_message_limit_enabled=request.free_message_limit_enabled,
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )
    saved = await upsert_payment_settings(settings)
    return _settings_to_dict(saved)


@router.put("/channel-bindings/{binding_id}/payment-token")
async def set_payment_token_endpoint(
    binding_id: str,
    request: SetPaymentTokenRequest,
    _admin: str = require_admin(),
):
    """Store provider tokens in Secrets Manager; update secret_name pointers in settings."""
    from app.storage.resolver import get_secrets_manager

    sm = get_secrets_manager()
    settings = await get_payment_settings(binding_id)
    if not settings:
        settings = PaymentSettings(binding_id=binding_id)

    if request.token is not None:
        secret_name = await sm.store_payment_token(binding_id, request.token, sandbox=False)
        settings.provider_secret_name = secret_name

    if request.token_sandbox is not None:
        secret_name_sb = await sm.store_payment_token(binding_id, request.token_sandbox, sandbox=True)
        settings.sandbox_secret_name = secret_name_sb

    settings.updated_at = utc_now()
    saved = await upsert_payment_settings(settings)
    return {"ok": True, "has_live_token": bool(saved.provider_secret_name), "has_sandbox_token": bool(saved.sandbox_secret_name)}


# ── Plans ─────────────────────────────────────────────────────────────────────


@router.get("/channel-bindings/{binding_id}/payment-plans")
async def list_payment_plans_endpoint(
    binding_id: str,
    active_only: bool = Query(default=True),
    _admin: str = require_admin(),
):
    plans = await list_payment_plans(binding_id, active_only=active_only)
    return [_plan_to_dict(p) for p in plans]


@router.post("/channel-bindings/{binding_id}/payment-plans", status_code=201)
async def create_payment_plan_endpoint(
    binding_id: str,
    request: CreatePlanRequest,
    _admin: str = require_admin(),
):
    plan = PaymentPlan(
        binding_id=binding_id,
        name=request.name,
        duration_days=request.duration_days,
        price_amount=request.price_amount,
        currency=request.currency,
        messages_limit=request.messages_limit,
        sort_order=request.sort_order,
    )
    created = await create_payment_plan(plan)
    return _plan_to_dict(created)


@router.put("/channel-bindings/{binding_id}/payment-plans/{plan_id}")
async def update_payment_plan_endpoint(
    binding_id: str,
    plan_id: str,
    request: UpdatePlanRequest,
    _admin: str = require_admin(),
):
    plan = await get_payment_plan(plan_id)
    if not plan or plan.binding_id != binding_id:
        raise HTTPException(status_code=404, detail="Plan not found")

    patch = {k: v for k, v in request.model_dump().items() if v is not None}
    updated = await update_payment_plan(plan_id, **patch)
    return _plan_to_dict(updated)


@router.delete("/channel-bindings/{binding_id}/payment-plans/{plan_id}", status_code=204)
async def delete_payment_plan_endpoint(
    binding_id: str,
    plan_id: str,
    _admin: str = require_admin(),
):
    plan = await get_payment_plan(plan_id)
    if not plan or plan.binding_id != binding_id:
        raise HTTPException(status_code=404, detail="Plan not found")
    await delete_payment_plan(plan_id)


# ── Subscriptions ─────────────────────────────────────────────────────────────


@router.get("/channel-bindings/{binding_id}/subscriptions")
async def list_subscriptions_endpoint(
    binding_id: str,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: str = require_admin(),
):
    subs = await list_subscriptions(binding_id, status=status_filter, limit=limit, offset=offset)
    return [_sub_to_dict(s) for s in subs]


@router.get("/channel-bindings/{binding_id}/subscriptions/{external_user_id}")
async def get_subscription_endpoint(
    binding_id: str,
    external_user_id: str,
    _admin: str = require_admin(),
):
    sub = await get_subscription(binding_id, external_user_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return _sub_to_dict(sub)


@router.put("/channel-bindings/{binding_id}/subscriptions/{external_user_id}")
async def update_subscription_endpoint(
    binding_id: str,
    external_user_id: str,
    request: UpdateSubscriptionRequest,
    _admin: str = require_admin(),
):
    from app.models.payment import get_or_create_subscription
    sub = await get_or_create_subscription(binding_id, external_user_id)

    patch: dict = {}
    if request.status is not None:
        patch["status"] = request.status
    if request.expires_at is not None:
        patch["expires_at"] = request.expires_at
    if request.messages_limit is not None:
        patch["messages_limit"] = request.messages_limit
    if request.messages_used is not None:
        patch["messages_used"] = request.messages_used
    if request.manual_override is not None:
        patch["manual_override"] = request.manual_override
    if request.notes is not None:
        patch["notes"] = request.notes
    if request.feature_overrides is not None:
        patch["feature_overrides"] = request.feature_overrides

    if patch:
        await update_subscription(sub.sub_id, **patch)
        await invalidate_cache(binding_id, external_user_id)

    updated = await get_subscription(binding_id, external_user_id)
    return _sub_to_dict(updated)


@router.post("/channel-bindings/{binding_id}/subscriptions/{external_user_id}/reset")
async def reset_subscription_counter_endpoint(
    binding_id: str,
    external_user_id: str,
    _admin: str = require_admin(),
):
    from app.models.payment import get_or_create_subscription
    sub = await get_or_create_subscription(binding_id, external_user_id)
    await update_subscription(sub.sub_id, messages_used=0, grace_messages_used=0, invoice_sent_at=None)
    await invalidate_cache(binding_id, external_user_id)
    return {"ok": True}


# ── Transactions ──────────────────────────────────────────────────────────────


@router.get("/channel-bindings/{binding_id}/transactions")
async def list_transactions_endpoint(
    binding_id: str,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    _admin: str = require_admin(),
):
    txns = await list_transactions(binding_id, limit=limit, offset=offset)
    return [_txn_to_dict(t) for t in txns]


@router.post("/channel-bindings/{binding_id}/sandbox/simulate-payment", status_code=200)
async def simulate_sandbox_payment_endpoint(
    binding_id: str,
    request: SimulateSandboxPaymentRequest,
    _admin: str = require_admin(),
):
    """Simulate a successful payment in sandbox mode (no real provider needed).

    Only works when payment is enabled and sandbox_mode=True.
    Activates the specified plan for the given user immediately.
    """
    settings = await get_payment_settings(binding_id)
    if not settings or not settings.enabled:
        raise HTTPException(status_code=400, detail="Payment not enabled for this binding")
    if not settings.sandbox_mode:
        raise HTTPException(status_code=400, detail="Sandbox mode is not enabled")

    plan = await get_payment_plan(request.plan_id)
    if not plan or plan.binding_id != binding_id:
        raise HTTPException(status_code=404, detail="Plan not found")

    activated = await activate_subscription(binding_id, request.external_user_id, plan)
    await invalidate_cache(binding_id, request.external_user_id)

    return {
        "ok": True,
        "sub": _sub_to_dict(activated),
    }


@router.post("/transactions/{txn_id}/refund")
async def refund_transaction_endpoint(
    txn_id: str,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    txn = await get_transaction(txn_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.status == "refunded":
        raise HTTPException(status_code=409, detail="Already refunded")
    if not txn.provider_charge_id:
        raise HTTPException(status_code=400, detail="No charge_id to refund")

    # Get bot token for Telegram refund
    try:
        from app.models.payment import get_payment_settings as gps
        from app.services.channel_binding_service import ChannelBindingService
        from app.services.payment.factory import get_payment_provider
        from app.storage.resolver import get_secrets_manager

        binding_service = ChannelBindingService(deps.db, get_secrets_manager())
        binding = await binding_service.get_binding(txn.binding_id)
        if not binding:
            raise HTTPException(status_code=404, detail="Binding not found")

        bot_token = await binding_service.get_access_token(txn.binding_id)
        settings = await gps(txn.binding_id)
        if not settings:
            raise HTTPException(status_code=400, detail="Payment not configured")

        provider = get_payment_provider(settings)
        ok = await provider.refund(bot_token, txn.external_user_id, txn.provider_charge_id)

        if ok:
            await update_transaction_status(txn_id, "refunded")
            return {"ok": True}
        else:
            raise HTTPException(status_code=502, detail="Refund failed at provider")

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Refund error for txn %s: %s", txn_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
