"""Payment system models: settings, plans, subscriptions, transactions."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.utils.datetime_utils import utc_now


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PaymentProvider(str, Enum):
    TELEGRAM_NATIVE = "telegram_native"
    EXTERNAL_LINK = "external_link"


class SubscriptionStatus(str, Enum):
    FREE = "free"
    ACTIVE = "active"
    EXPIRED = "expired"
    MANUAL = "manual"


class TransactionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class FeatureGates(BaseModel):
    """Per-feature payment gates. When True, the feature requires an active subscription."""

    voice: bool = False
    images: bool = False


class PaywallMessages(BaseModel):
    """Custom paywall messages shown when a user hits a feature gate."""

    voice: str = "Голосовые сообщения доступны по подписке."
    images: str = "Анализ изображений доступен по подписке."
    limit_reached: str = "Вы исчерпали лимит бесплатных сообщений. Выберите план подписки."


class PaymentSettings(BaseModel):
    setting_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    binding_id: str
    enabled: bool = False
    provider: PaymentProvider = PaymentProvider.TELEGRAM_NATIVE
    free_messages: int = 10
    grace_messages: int = 3
    sandbox_mode: bool = False
    provider_secret_name: Optional[str] = None
    sandbox_secret_name: Optional[str] = None
    payment_title: str = "Подписка"
    payment_description: str = "Доступ к чат-боту"
    invoice_resend_hours: int = 24
    support_contact: Optional[str] = None
    # Paid features (migration 014)
    feature_gates: FeatureGates = Field(default_factory=FeatureGates)
    paywall_messages: PaywallMessages = Field(default_factory=PaywallMessages)
    free_message_limit_enabled: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PaymentPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    binding_id: str
    name: str
    duration_days: int
    price_amount: int  # smallest currency unit
    currency: str = "RUB"
    messages_limit: Optional[int] = None  # None = unlimited
    is_active: bool = True
    sort_order: int = 0
    created_at: datetime = Field(default_factory=utc_now)


class UserSubscription(BaseModel):
    sub_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    binding_id: str
    external_user_id: str
    status: SubscriptionStatus = SubscriptionStatus.FREE
    plan_id: Optional[str] = None
    expires_at: Optional[datetime] = None
    messages_used: int = 0
    messages_limit: Optional[int] = None
    period_started_at: Optional[datetime] = None
    invoice_sent_at: Optional[datetime] = None
    grace_messages_used: int = 0
    manual_override: bool = False
    notes: Optional[str] = None
    # Per-user feature access overrides (migration 014)
    feature_overrides: Optional[dict[str, bool]] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PaymentTransaction(BaseModel):
    txn_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sub_id: str
    binding_id: str
    external_user_id: str
    provider: PaymentProvider
    provider_charge_id: Optional[str] = None
    plan_id: Optional[str] = None
    amount: Optional[int] = None
    currency: Optional[str] = None
    status: TransactionStatus = TransactionStatus.PENDING
    invoice_payload: Optional[str] = None
    raw_payload: Optional[dict] = None
    created_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Invoice payload signing helpers
# ---------------------------------------------------------------------------


def make_invoice_payload(
    binding_id: str, user_id: str, plan_id: str, secret_key: str
) -> str:
    """Create a signed payload string for Telegram invoice verification."""
    raw = f"{binding_id}:{user_id}:{plan_id}"
    sig = hmac.new(secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]  # type: ignore[attr-defined]
    return f"{raw}:{sig}"


def verify_invoice_payload(
    payload: str, secret_key: str
) -> Optional[tuple[str, str, str]]:
    """Verify signed payload.  Returns (binding_id, user_id, plan_id) or None."""
    try:
        *parts, sig = payload.split(":")
        if len(parts) != 3:
            return None
        raw = ":".join(parts)
        expected = hmac.new(secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]  # type: ignore[attr-defined]
        if not hmac.compare_digest(sig, expected):
            return None
        binding_id, user_id, plan_id = parts
        return binding_id, user_id, plan_id
    except Exception:
        return None


# ---------------------------------------------------------------------------
# PostgreSQL CRUD
# ---------------------------------------------------------------------------


async def get_payment_settings(binding_id: str) -> Optional[PaymentSettings]:
    from app.storage.postgres import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM payment_settings WHERE binding_id = $1", binding_id
        )
    if not row:
        return None
    return PaymentSettings(**_row_to_dict(row))


async def upsert_payment_settings(settings: PaymentSettings) -> PaymentSettings:
    from app.storage.postgres import get_pool

    feature_gates_json = json.dumps(settings.feature_gates.model_dump())
    paywall_messages_json = json.dumps(settings.paywall_messages.model_dump())

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO payment_settings (
                setting_id, binding_id, enabled, provider, free_messages, grace_messages,
                sandbox_mode, provider_secret_name, sandbox_secret_name,
                payment_title, payment_description, invoice_resend_hours, support_contact,
                feature_gates, paywall_messages, free_message_limit_enabled,
                created_at, updated_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
            ON CONFLICT (binding_id) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                provider = EXCLUDED.provider,
                free_messages = EXCLUDED.free_messages,
                grace_messages = EXCLUDED.grace_messages,
                sandbox_mode = EXCLUDED.sandbox_mode,
                provider_secret_name = EXCLUDED.provider_secret_name,
                sandbox_secret_name = EXCLUDED.sandbox_secret_name,
                payment_title = EXCLUDED.payment_title,
                payment_description = EXCLUDED.payment_description,
                invoice_resend_hours = EXCLUDED.invoice_resend_hours,
                support_contact = EXCLUDED.support_contact,
                feature_gates = EXCLUDED.feature_gates,
                paywall_messages = EXCLUDED.paywall_messages,
                free_message_limit_enabled = EXCLUDED.free_message_limit_enabled,
                updated_at = NOW()
            """,
            settings.setting_id, settings.binding_id, settings.enabled,
            settings.provider.value if hasattr(settings.provider, 'value') else settings.provider,
            settings.free_messages, settings.grace_messages,
            settings.sandbox_mode, settings.provider_secret_name, settings.sandbox_secret_name,
            settings.payment_title, settings.payment_description, settings.invoice_resend_hours,
            settings.support_contact,
            feature_gates_json, paywall_messages_json, settings.free_message_limit_enabled,
            settings.created_at, settings.updated_at,
        )
    return settings


# ── Plans ─────────────────────────────────────────────────────────────────────


async def list_payment_plans(
    binding_id: str, active_only: bool = True
) -> list[PaymentPlan]:
    from app.storage.postgres import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        if active_only:
            rows = await conn.fetch(
                "SELECT * FROM payment_plans WHERE binding_id = $1 AND is_active ORDER BY sort_order, created_at",
                binding_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM payment_plans WHERE binding_id = $1 ORDER BY sort_order, created_at",
                binding_id,
            )
    return [PaymentPlan(**_row_to_dict(r)) for r in rows]


async def get_payment_plan(plan_id: str) -> Optional[PaymentPlan]:
    from app.storage.postgres import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM payment_plans WHERE plan_id = $1", plan_id
        )
    return PaymentPlan(**_row_to_dict(row)) if row else None


async def create_payment_plan(plan: PaymentPlan) -> PaymentPlan:
    from app.storage.postgres import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO payment_plans
                (plan_id, binding_id, name, duration_days, price_amount, currency,
                 messages_limit, is_active, sort_order, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            """,
            plan.plan_id, plan.binding_id, plan.name, plan.duration_days,
            plan.price_amount, plan.currency, plan.messages_limit,
            plan.is_active, plan.sort_order, plan.created_at,
        )
    return plan


async def update_payment_plan(plan_id: str, **kwargs) -> Optional[PaymentPlan]:
    from app.storage.postgres import get_pool

    if not kwargs:
        return await get_payment_plan(plan_id)
    sets = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(kwargs))
    params = list(kwargs.values())
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE payment_plans SET {sets} WHERE plan_id = $1",
            plan_id, *params,
        )
    return await get_payment_plan(plan_id)


async def delete_payment_plan(plan_id: str) -> None:
    from app.storage.postgres import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE payment_plans SET is_active = FALSE WHERE plan_id = $1", plan_id
        )


# ── Subscriptions ─────────────────────────────────────────────────────────────


async def get_subscription(
    binding_id: str, external_user_id: str
) -> Optional[UserSubscription]:
    from app.storage.postgres import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM user_subscriptions WHERE binding_id = $1 AND external_user_id = $2",
            binding_id, external_user_id,
        )
    return UserSubscription(**_row_to_dict(row)) if row else None


async def get_or_create_subscription(
    binding_id: str, external_user_id: str
) -> UserSubscription:
    sub = await get_subscription(binding_id, external_user_id)
    if sub:
        return sub

    new_sub = UserSubscription(
        binding_id=binding_id,
        external_user_id=external_user_id,
    )
    from app.storage.postgres import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_subscriptions
                (sub_id, binding_id, external_user_id, status, messages_used,
                 grace_messages_used, manual_override, created_at, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (binding_id, external_user_id) DO NOTHING
            """,
            new_sub.sub_id, binding_id, external_user_id, "free",
            0, 0, False, new_sub.created_at, new_sub.updated_at,
        )
    # Re-fetch (another worker may have created it concurrently)
    return (await get_subscription(binding_id, external_user_id)) or new_sub


async def increment_messages(sub_id: str) -> None:
    from app.storage.postgres import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE user_subscriptions SET messages_used = messages_used + 1, updated_at = NOW() WHERE sub_id = $1",
            sub_id,
        )


async def increment_grace_messages(sub_id: str) -> None:
    from app.storage.postgres import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE user_subscriptions SET grace_messages_used = grace_messages_used + 1, updated_at = NOW() WHERE sub_id = $1",
            sub_id,
        )


async def set_invoice_sent(sub_id: str) -> None:
    from app.storage.postgres import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            # Reset grace_messages_used so the user gets a fresh reminder cycle
            # each time a new invoice keyboard is sent (including after throttle re-sends).
            "UPDATE user_subscriptions SET invoice_sent_at = NOW(), grace_messages_used = 0, updated_at = NOW() WHERE sub_id = $1",
            sub_id,
        )


async def activate_subscription(
    binding_id: str, external_user_id: str, plan: PaymentPlan
) -> UserSubscription:
    from app.storage.postgres import get_pool
    from datetime import timedelta

    sub = await get_or_create_subscription(binding_id, external_user_id)
    expires_at = utc_now() + timedelta(days=plan.duration_days)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE user_subscriptions SET
                status = 'active',
                plan_id = $2,
                expires_at = $3,
                messages_used = 0,
                messages_limit = $4,
                period_started_at = NOW(),
                invoice_sent_at = NULL,
                grace_messages_used = 0,
                updated_at = NOW()
            WHERE sub_id = $1
            """,
            sub.sub_id, plan.plan_id, expires_at, plan.messages_limit,
        )
    return (await get_subscription(binding_id, external_user_id)) or sub


async def update_subscription(sub_id: str, **kwargs) -> None:
    from app.storage.postgres import get_pool

    if not kwargs:
        return
    kwargs["updated_at"] = utc_now()
    # Serialize JSONB fields
    if "feature_overrides" in kwargs and isinstance(kwargs["feature_overrides"], dict):
        kwargs["feature_overrides"] = json.dumps(kwargs["feature_overrides"])
    sets = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(kwargs))
    params = list(kwargs.values())
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE user_subscriptions SET {sets} WHERE sub_id = $1",
            sub_id, *params,
        )


async def list_subscriptions(
    binding_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[UserSubscription]:
    from app.storage.postgres import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch(
                "SELECT * FROM user_subscriptions WHERE binding_id = $1 AND status = $2 ORDER BY updated_at DESC LIMIT $3 OFFSET $4",
                binding_id, status, limit, offset,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM user_subscriptions WHERE binding_id = $1 ORDER BY updated_at DESC LIMIT $2 OFFSET $3",
                binding_id, limit, offset,
            )
    return [UserSubscription(**_row_to_dict(r)) for r in rows]


# ── Transactions ──────────────────────────────────────────────────────────────


async def create_transaction_idempotent(
    sub_id: str,
    binding_id: str,
    external_user_id: str,
    provider: str,
    plan_id: Optional[str],
    charge_id: str,
    amount: Optional[int],
    currency: Optional[str],
    invoice_payload: Optional[str],
    raw_payload: Optional[dict],
) -> bool:
    """Insert transaction; returns True if newly created, False if duplicate (idempotent)."""
    import json as _json
    from app.storage.postgres import get_pool

    txn_id = str(uuid.uuid4())
    raw_json = _json.dumps(raw_payload) if raw_payload else None
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            INSERT INTO payment_transactions
                (txn_id, sub_id, binding_id, external_user_id, provider,
                 provider_charge_id, plan_id, amount, currency, status,
                 invoice_payload, raw_payload, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'completed',$10,$11,NOW())
            ON CONFLICT (provider_charge_id) DO NOTHING
            """,
            txn_id, sub_id, binding_id, external_user_id, provider,
            charge_id, plan_id, amount, currency,
            invoice_payload, raw_json,
        )
    return result != "INSERT 0 0"


async def list_transactions(
    binding_id: str, limit: int = 100, offset: int = 0
) -> list[PaymentTransaction]:
    from app.storage.postgres import get_pool
    import json as _json

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM payment_transactions WHERE binding_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            binding_id, limit, offset,
        )
    result = []
    for r in rows:
        d = _row_to_dict(r)
        if d.get("raw_payload") and isinstance(d["raw_payload"], str):
            d["raw_payload"] = _json.loads(d["raw_payload"])
        result.append(PaymentTransaction(**d))
    return result


async def get_transaction(txn_id: str) -> Optional[PaymentTransaction]:
    from app.storage.postgres import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM payment_transactions WHERE txn_id = $1", txn_id
        )
    return PaymentTransaction(**_row_to_dict(row)) if row else None


async def update_transaction_status(txn_id: str, status: str) -> None:
    from app.storage.postgres import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE payment_transactions SET status = $2 WHERE txn_id = $1",
            txn_id, status,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_dict(row) -> dict:
    import uuid as _uuid
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime) and v.tzinfo is None:
            d[k] = v.replace(tzinfo=timezone.utc)
        elif isinstance(v, _uuid.UUID):
            # asyncpg returns UUID columns as uuid.UUID objects; Pydantic models expect str
            d[k] = str(v)
        elif isinstance(v, str) and k in (
            "feature_gates", "paywall_messages", "feature_overrides", "raw_payload"
        ):
            try:
                d[k] = json.loads(v)
            except (ValueError, TypeError):
                pass
    return d
