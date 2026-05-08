"""PostgreSQL repository for user_reminders."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

import asyncpg

from app.models.user_reminder import UserReminder
from app.storage.postgres import get_pool
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


def _row_to_reminder(row: asyncpg.Record) -> UserReminder:
    spec = row["schedule_spec"]
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except json.JSONDecodeError:
            spec = {}
    if not isinstance(spec, dict):
        spec = {}
    return UserReminder(
        reminder_id=str(row["reminder_id"]),
        agent_id=row["agent_id"],
        binding_id=row["binding_id"],
        external_user_id=row["external_user_id"],
        category=row["category"],
        schedule_kind=row["schedule_kind"],
        schedule_spec=spec,
        user_note=row["user_note"] or "",
        status=row["status"],
        next_fire_at=row["next_fire_at"],
        last_fired_at=row["last_fired_at"],
        recurring_fires_done=int(row["recurring_fires_done"] or 0),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        cancelled_at=row["cancelled_at"],
    )


async def create_reminder(
    *,
    agent_id: str,
    binding_id: str,
    external_user_id: str,
    category: str,
    schedule_kind: str,
    schedule_spec: dict[str, Any],
    user_note: str,
    next_fire_at: datetime,
) -> UserReminder:
    reminder_id = str(uuid.uuid4())
    now = utc_now()
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO user_reminders (
                reminder_id, agent_id, binding_id, external_user_id,
                category, schedule_kind, schedule_spec, user_note, status,
                next_fire_at, created_at, updated_at
            )
            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7::jsonb, $8, 'active', $9, $10, $11)
            RETURNING *
            """,
            reminder_id,
            agent_id,
            binding_id,
            external_user_id,
            category,
            schedule_kind,
            json.dumps(schedule_spec),
            user_note,
            next_fire_at,
            now,
            now,
        )
    assert row is not None
    return _row_to_reminder(row)


async def get_reminder(reminder_id: str) -> Optional[UserReminder]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM user_reminders WHERE reminder_id = $1::uuid",
            reminder_id,
        )
    return _row_to_reminder(row) if row else None


async def count_active_for_user(binding_id: str, external_user_id: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        n = await conn.fetchval(
            """
            SELECT COUNT(*)::int FROM user_reminders
            WHERE binding_id = $1 AND external_user_id = $2 AND status = 'active'
            """,
            binding_id,
            external_user_id,
        )
    return int(n or 0)


async def list_active_for_user(binding_id: str, external_user_id: str) -> list[UserReminder]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM user_reminders
            WHERE binding_id = $1 AND external_user_id = $2 AND status = 'active'
            ORDER BY next_fire_at ASC
            """,
            binding_id,
            external_user_id,
        )
    return [_row_to_reminder(r) for r in rows]


async def update_next_fire(
    reminder_id: str,
    next_fire_at: datetime,
    *,
    last_fired_at: Optional[datetime] = None,
) -> None:
    now = utc_now()
    pool = await get_pool()
    async with pool.acquire() as conn:
        if last_fired_at is not None:
            await conn.execute(
                """
                UPDATE user_reminders
                SET next_fire_at = $2, last_fired_at = $3, updated_at = $4
                WHERE reminder_id = $1::uuid AND status = 'active'
                """,
                reminder_id,
                next_fire_at,
                last_fired_at,
                now,
            )
        else:
            await conn.execute(
                """
                UPDATE user_reminders
                SET next_fire_at = $2, updated_at = $3
                WHERE reminder_id = $1::uuid AND status = 'active'
                """,
                reminder_id,
                next_fire_at,
                now,
            )


async def bump_recurring_fire(
    reminder_id: str,
    *,
    next_fire_at: datetime,
    last_fired_at: datetime,
    fires_done: int,
) -> None:
    now = utc_now()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE user_reminders
            SET next_fire_at = $2,
                last_fired_at = $3,
                recurring_fires_done = $4,
                updated_at = $5
            WHERE reminder_id = $1::uuid AND status = 'active'
            """,
            reminder_id,
            next_fire_at,
            last_fired_at,
            fires_done,
            now,
        )


async def complete_reminder(reminder_id: str) -> None:
    now = utc_now()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE user_reminders
            SET status = 'completed', updated_at = $2, last_fired_at = COALESCE(last_fired_at, $2)
            WHERE reminder_id = $1::uuid
            """,
            reminder_id,
            now,
        )


async def cancel_reminder(reminder_id: str, binding_id: str, external_user_id: str) -> bool:
    """Returns True if a row was updated."""
    now = utc_now()
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE user_reminders
            SET status = 'cancelled', cancelled_at = $4, updated_at = $4
            WHERE reminder_id = $1::uuid AND binding_id = $2 AND external_user_id = $3
              AND status = 'active'
            """,
            reminder_id,
            binding_id,
            external_user_id,
            now,
        )
    # asyncpg returns 'UPDATE N'
    try:
        n = int(str(result).split()[-1])
    except (ValueError, IndexError):
        n = 0
    return n > 0
