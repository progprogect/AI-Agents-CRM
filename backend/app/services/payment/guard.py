"""PaymentGuard: checks whether a user may interact with the bot.

Enforces free-message limits, subscription status, grace period,
and invoice throttling. Uses Redis for low-latency caching.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from app.models.payment import (
    PaymentSettings,
    UserSubscription,
    get_or_create_subscription,
    get_payment_settings,
    increment_grace_messages,
    increment_messages,
    set_invoice_sent,
    update_subscription,
)
from app.storage.redis import get_redis_client

logger = logging.getLogger(__name__)

CACHE_TTL = 60  # seconds


class GuardResult(str, Enum):
    ALLOW = "allow"
    BLOCK_SEND_INVOICE = "block_invoice"
    GRACE = "grace"
    PENDING_HARD = "pending_hard"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_sub(sub: UserSubscription) -> str:
    d = sub.model_dump()
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return json.dumps(d)


def _deserialize_sub(raw: str) -> UserSubscription:
    d = json.loads(raw)
    for k in ("expires_at", "period_started_at", "invoice_sent_at", "created_at", "updated_at"):
        if d.get(k):
            d[k] = datetime.fromisoformat(d[k])
    return UserSubscription(**d)


async def check(
    binding_id: str,
    external_user_id: str,
    settings: Optional[PaymentSettings] = None,
) -> GuardResult:
    """Return the appropriate GuardResult for this user's current subscription state."""

    # Load settings (may be cached by caller)
    if settings is None:
        settings = await get_payment_settings(binding_id)

    if not settings or not settings.enabled:
        return GuardResult.ALLOW

    redis = get_redis_client()
    cache_key = f"pay_sub:{binding_id}:{external_user_id}"

    # ── Try cache ────────────────────────────────────────────────────────────
    try:
        cached = await redis.get(cache_key)
        if cached:
            sub = _deserialize_sub(cached)
        else:
            sub = await get_or_create_subscription(binding_id, external_user_id)
            await redis.set(cache_key, _serialize_sub(sub), ttl=CACHE_TTL)
    except Exception as exc:
        logger.warning("PaymentGuard cache error, falling back to DB: %s", exc)
        sub = await get_or_create_subscription(binding_id, external_user_id)

    # ── Manual override ──────────────────────────────────────────────────────
    if sub.manual_override:
        return GuardResult.ALLOW

    now = _utcnow()

    # ── Active subscription ──────────────────────────────────────────────────
    if sub.status == "active":
        if sub.expires_at is not None:
            # Normalise to UTC-aware before comparing (handle naive DB datetimes).
            exp = sub.expires_at if sub.expires_at.tzinfo else sub.expires_at.replace(tzinfo=timezone.utc)
            expired: bool = exp < now
        else:
            expired = False

        if expired:
            await update_subscription(sub.sub_id, status="expired")
            await _invalidate(cache_key)
            # fall through to block logic below
        else:
            within_msg_limit = (
                sub.messages_limit is None
                or sub.messages_used < sub.messages_limit
            )
            if within_msg_limit:
                await increment_messages(sub.sub_id)
                await _invalidate(cache_key)
                return GuardResult.ALLOW
            # message limit exhausted → fall through

    # ── Free tier ────────────────────────────────────────────────────────────
    if sub.status == "free" and sub.messages_used < settings.free_messages:
        await increment_messages(sub.sub_id)
        await _invalidate(cache_key)
        return GuardResult.ALLOW

    # ── Grace period + throttle ───────────────────────────────────────────────
    # If an invoice was already sent and the re-send throttle has NOT expired:
    #   • still within grace limit → remind the user (GRACE)
    #   • grace exhausted         → stay silent (PENDING_HARD)
    # If the throttle HAS expired (or no invoice was ever sent):
    #   → send a fresh invoice (BLOCK_SEND_INVOICE)
    if sub.invoice_sent_at:
        sent_at = sub.invoice_sent_at
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        hours_since = (now - sent_at).total_seconds() / 3600

        if hours_since < settings.invoice_resend_hours:
            # Within throttle window: use grace messages or go silent
            if sub.grace_messages_used < settings.grace_messages:
                await increment_grace_messages(sub.sub_id)
                return GuardResult.GRACE
            return GuardResult.PENDING_HARD
        # Throttle window expired → fall through to re-send invoice

    return GuardResult.BLOCK_SEND_INVOICE


async def invalidate_cache(binding_id: str, external_user_id: str) -> None:
    """Invalidate cached subscription for this user (call after any subscription change)."""
    redis = get_redis_client()
    cache_key = f"pay_sub:{binding_id}:{external_user_id}"
    await _invalidate(cache_key)


async def _invalidate(cache_key: str) -> None:
    try:
        redis = get_redis_client()
        await redis.delete(cache_key)
    except Exception as exc:
        logger.debug("Redis cache invalidation error: %s", exc)
