"""Poll Redis ZSET for due Telegram user reminders; fire LLM message + Telegram send."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import timedelta

from app.config import get_settings
from app.models.agent_config import AgentConfig
from app.services.questionnaire_service import get_current_values
from app.services.reminder_message_generator import generate_reminder_message
from app.services.telegram_service import TelegramService
from app.storage import postgres_user_reminders as ur_repo
from app.storage.redis import get_redis_client
from app.storage.resolver import get_secrets_manager
from app.services.channel_binding_service import ChannelBindingService
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

KEY_USER_REMINDER_DUE = "telegram_user_reminder:due"
USER_REMINDER_LOCK_PREFIX = "telegram_user_reminder:lock:"
USER_REMINDER_DEAD_LETTER_PREFIX = "telegram_user_reminder:failed:"
LOCK_TTL_SECONDS = 120
DEAD_LETTER_TTL = 86400


def _fire_ms(dt: Any) -> float:
    return float(dt.timestamp() * 1000)


async def enqueue_user_reminder(reminder_id: str, next_fire_at: Any) -> None:
    """Add or update this reminder in the due queue (score = next_fire_at epoch ms)."""
    redis = get_redis_client()
    if not await redis.ping():
        logger.warning("Redis unavailable; cannot enqueue reminder %s", reminder_id)
        return
    ms = _fire_ms(next_fire_at)
    try:
        await redis.zadd(KEY_USER_REMINDER_DUE, {reminder_id: ms})
    except Exception as exc:
        logger.warning("enqueue_user_reminder failed %s: %s", reminder_id, exc)


async def dequeue_user_reminder(reminder_id: str) -> None:
    redis = get_redis_client()
    try:
        await redis.zrem(KEY_USER_REMINDER_DUE, reminder_id)
    except Exception as exc:
        logger.debug("dequeue_user_reminder %s: %s", reminder_id, exc)


async def execute_user_reminder_fire(reminder_id: str) -> None:
    """Generate reminder text, send Telegram, reschedule or complete."""
    from app.dependencies import get_db

    db = get_db()
    settings = get_settings()

    row = await ur_repo.get_reminder(reminder_id)
    if row is None or row.status != "active":
        await dequeue_user_reminder(reminder_id)
        return

    next_fire_backup = row.next_fire_at
    now = utc_now()
    if row.next_fire_at > now + timedelta(seconds=30):
        # Stale queue entry — re-sync score from DB
        await enqueue_user_reminder(reminder_id, row.next_fire_at)
        return

    agent_data = await db.get_agent(row.agent_id)
    if not agent_data or "config" not in agent_data:
        logger.warning("No agent config for reminder %s", reminder_id)
        await dequeue_user_reminder(reminder_id)
        return

    agent_config = AgentConfig.from_dict(agent_data["config"])
    qvals = await get_current_values(row.agent_id, row.external_user_id)

    text = await generate_reminder_message(
        agent_config,
        category=row.category,
        user_note=row.user_note,
        questionnaire_values=qvals,
    )

    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(db, secrets_manager)
    telegram_svc = TelegramService(binding_service, db, settings)

    try:
        await telegram_svc.send_message(
            row.binding_id,
            row.external_user_id,
            text,
        )
    except Exception as exc:
        logger.error(
            "User reminder Telegram send failed %s: %s",
            reminder_id,
            exc,
            exc_info=True,
        )
        redis = get_redis_client()
        try:
            await redis.set(
                f"{USER_REMINDER_DEAD_LETTER_PREFIX}{reminder_id}",
                json.dumps({"error": str(exc), "ts": time.time()}),
                ttl=DEAD_LETTER_TTL,
            )
        except Exception:
            pass
        await enqueue_user_reminder(reminder_id, next_fire_backup)
        return

    spec = row.schedule_spec or {}
    if row.schedule_kind == "once":
        await ur_repo.complete_reminder(reminder_id)
        await dequeue_user_reminder(reminder_id)
        logger.info(
            "User reminder %s completed (once)",
            reminder_id,
            extra={"reminder_id": reminder_id},
        )
        return

    # recurring
    interval = int(spec.get("interval_seconds") or 86400)
    max_fires = spec.get("max_fires")
    new_count = row.recurring_fires_done + 1
    if max_fires is not None and int(max_fires) <= new_count:
        await ur_repo.complete_reminder(reminder_id)
        await dequeue_user_reminder(reminder_id)
        logger.info(
            "User reminder %s completed (recurring max reached)",
            reminder_id,
        )
        return

    next_fire = now + timedelta(seconds=interval)
    await ur_repo.bump_recurring_fire(
        reminder_id,
        next_fire_at=next_fire,
        last_fired_at=now,
        fires_done=new_count,
    )
    await enqueue_user_reminder(reminder_id, next_fire)
    logger.info(
        "User reminder %s fired; next at %s",
        reminder_id,
        next_fire.isoformat(),
    )


async def _poll_user_reminders_once() -> None:
    redis = get_redis_client()
    if not await redis.ping():
        return

    now_ms = int(time.time() * 1000)
    try:
        due = await redis.zrangebyscore(KEY_USER_REMINDER_DUE, "-inf", float(now_ms), num=30)
    except Exception as exc:
        logger.debug("user reminder poll zrangebyscore: %s", exc)
        return

    for reminder_id in due:
        lock_key = f"{USER_REMINDER_LOCK_PREFIX}{reminder_id}"
        acquired = await redis.set_nx_ex(lock_key, "1", LOCK_TTL_SECONDS)
        if not acquired:
            continue

        try:
            score = await redis.zscore(KEY_USER_REMINDER_DUE, reminder_id)
            if score is None or score > now_ms:
                continue

            await redis.zrem(KEY_USER_REMINDER_DUE, reminder_id)

            async def _run(rid: str) -> None:
                try:
                    await execute_user_reminder_fire(rid)
                except Exception as exc:
                    logger.error(
                        "User reminder task failed for %s: %s",
                        rid,
                        exc,
                        exc_info=True,
                    )
                    try:
                        _r = get_redis_client()
                        await _r.set(
                            f"{USER_REMINDER_DEAD_LETTER_PREFIX}{rid}",
                            json.dumps({"error": str(exc), "ts": time.time()}),
                            ttl=DEAD_LETTER_TTL,
                        )
                    except Exception:
                        pass

            asyncio.create_task(_run(reminder_id))
        finally:
            await redis.delete(lock_key)


async def run_user_reminder_poll_loop(shutdown: asyncio.Event) -> None:
    logger.info("User reminder poll loop started")
    while True:
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=5.0)
            break
        except asyncio.TimeoutError:
            await _poll_user_reminders_once()
    logger.info("User reminder poll loop stopped")
