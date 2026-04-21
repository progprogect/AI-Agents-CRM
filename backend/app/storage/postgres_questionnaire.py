"""PostgreSQL repository for the questionnaire feature.

Tables: questionnaire_templates, questionnaire_submissions, questionnaire_responses.

Responses are append-only: every answer becomes a new row and the latest row per
``(agent_id, external_user_id, field_key)`` is the current value.  Nothing is
overwritten, so the admin UI can always show the full history of a field.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

import asyncpg

from app.models.questionnaire import (
    QuestionnaireField,
    QuestionnaireResponse,
    QuestionnaireSubmission,
    QuestionnaireTemplate,
    SubmissionSource,
    SubmissionStatus,
)
from app.storage.postgres import get_pool
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


def _template_from_row(row: asyncpg.Record) -> QuestionnaireTemplate:
    raw_fields = row["fields"]
    if isinstance(raw_fields, str):
        try:
            raw_fields = json.loads(raw_fields)
        except json.JSONDecodeError:
            raw_fields = []
    return QuestionnaireTemplate(
        agent_id=row["agent_id"],
        welcome_message=row["welcome_message"] or "",
        completion_message=row["completion_message"] or "",
        fields=[QuestionnaireField(**f) for f in (raw_fields or [])],
        updated_at=row["updated_at"],
    )


def _submission_from_row(row: asyncpg.Record) -> QuestionnaireSubmission:
    return QuestionnaireSubmission(
        submission_id=str(row["submission_id"]),
        agent_id=row["agent_id"],
        external_user_id=row["external_user_id"],
        channel=row["channel"],
        conversation_id=str(row["conversation_id"]) if row["conversation_id"] else None,
        status=SubmissionStatus(row["status"]),
        source=SubmissionSource(row["source"]),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        cancelled_at=row["cancelled_at"],
    )


def _response_from_row(row: asyncpg.Record) -> QuestionnaireResponse:
    return QuestionnaireResponse(
        response_id=str(row["response_id"]),
        submission_id=str(row["submission_id"]),
        agent_id=row["agent_id"],
        external_user_id=row["external_user_id"],
        field_key=row["field_key"],
        value=row["value"],
        created_at=row["created_at"],
    )


# ── Templates ──────────────────────────────────────────────────────────────


async def get_template(agent_id: str) -> Optional[QuestionnaireTemplate]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT agent_id, welcome_message, completion_message, fields, updated_at "
            "FROM questionnaire_templates WHERE agent_id = $1",
            agent_id,
        )
    if not row:
        return None
    return _template_from_row(row)


async def upsert_template(template: QuestionnaireTemplate) -> QuestionnaireTemplate:
    pool = await get_pool()
    fields_json = json.dumps([f.model_dump() for f in template.fields])
    now = utc_now()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO questionnaire_templates (agent_id, welcome_message, completion_message, fields, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            ON CONFLICT (agent_id) DO UPDATE SET
                welcome_message = EXCLUDED.welcome_message,
                completion_message = EXCLUDED.completion_message,
                fields = EXCLUDED.fields,
                updated_at = EXCLUDED.updated_at
            """,
            template.agent_id,
            template.welcome_message,
            template.completion_message,
            fields_json,
            now,
        )
    template.updated_at = now
    return template


# ── Submissions ────────────────────────────────────────────────────────────


async def start_submission(
    *,
    agent_id: str,
    external_user_id: str,
    channel: str = "telegram",
    conversation_id: Optional[str] = None,
    source: SubmissionSource = SubmissionSource.FILL,
) -> QuestionnaireSubmission:
    sub_id = str(uuid.uuid4())
    started = utc_now()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO questionnaire_submissions (
                submission_id, agent_id, external_user_id, channel,
                conversation_id, status, source, started_at
            ) VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8)
            """,
            sub_id,
            agent_id,
            external_user_id,
            channel,
            conversation_id,
            SubmissionStatus.IN_PROGRESS.value,
            source.value,
            started,
        )
    return QuestionnaireSubmission(
        submission_id=sub_id,
        agent_id=agent_id,
        external_user_id=external_user_id,
        channel=channel,
        conversation_id=conversation_id,
        status=SubmissionStatus.IN_PROGRESS,
        source=source,
        started_at=started,
    )


async def get_submission(submission_id: str) -> Optional[QuestionnaireSubmission]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM questionnaire_submissions WHERE submission_id = $1::uuid",
            submission_id,
        )
    return _submission_from_row(row) if row else None


async def complete_submission(submission_id: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE questionnaire_submissions
            SET status = $1, completed_at = $2
            WHERE submission_id = $3::uuid
            """,
            SubmissionStatus.COMPLETED.value,
            utc_now(),
            submission_id,
        )


async def cancel_submission(submission_id: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE questionnaire_submissions
            SET status = $1, cancelled_at = $2
            WHERE submission_id = $3::uuid AND status = 'in_progress'
            """,
            SubmissionStatus.CANCELLED.value,
            utc_now(),
            submission_id,
        )


async def list_submissions(
    agent_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
    status: Optional[SubmissionStatus] = None,
    started_from: Optional[datetime] = None,
    started_to: Optional[datetime] = None,
) -> list[QuestionnaireSubmission]:
    where = ["agent_id = $1"]
    params: list[Any] = [agent_id]
    idx = 2
    if status:
        where.append(f"status = ${idx}")
        params.append(status.value)
        idx += 1
    if started_from:
        where.append(f"started_at >= ${idx}")
        params.append(started_from)
        idx += 1
    if started_to:
        where.append(f"started_at <= ${idx}")
        params.append(started_to)
        idx += 1
    params.extend([limit, offset])
    sql = (
        "SELECT * FROM questionnaire_submissions WHERE "
        + " AND ".join(where)
        + f" ORDER BY started_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
    )
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [_submission_from_row(r) for r in rows]


# ── Responses ──────────────────────────────────────────────────────────────


async def append_response(
    *,
    submission_id: str,
    agent_id: str,
    external_user_id: str,
    field_key: str,
    value: str,
) -> QuestionnaireResponse:
    resp_id = str(uuid.uuid4())
    created = utc_now()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO questionnaire_responses (
                response_id, submission_id, agent_id, external_user_id,
                field_key, value, created_at
            ) VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7)
            """,
            resp_id,
            submission_id,
            agent_id,
            external_user_id,
            field_key,
            value,
            created,
        )
    return QuestionnaireResponse(
        response_id=resp_id,
        submission_id=submission_id,
        agent_id=agent_id,
        external_user_id=external_user_id,
        field_key=field_key,
        value=value,
        created_at=created,
    )


async def get_latest_values(agent_id: str, external_user_id: str) -> dict[str, str]:
    """Return the most recent value per field_key for this user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (field_key) field_key, value
            FROM questionnaire_responses
            WHERE agent_id = $1 AND external_user_id = $2
            ORDER BY field_key, created_at DESC
            """,
            agent_id,
            external_user_id,
        )
    return {r["field_key"]: r["value"] for r in rows}


async def list_responses_by_submission(submission_id: str) -> list[QuestionnaireResponse]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM questionnaire_responses
            WHERE submission_id = $1::uuid
            ORDER BY created_at ASC
            """,
            submission_id,
        )
    return [_response_from_row(r) for r in rows]


async def list_user_responses(
    agent_id: str, external_user_id: str
) -> list[QuestionnaireResponse]:
    """Full history of a single user's answers across all submissions."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM questionnaire_responses
            WHERE agent_id = $1 AND external_user_id = $2
            ORDER BY created_at ASC
            """,
            agent_id,
            external_user_id,
        )
    return [_response_from_row(r) for r in rows]


async def count_submissions(agent_id: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT COUNT(*) FROM questionnaire_submissions WHERE agent_id = $1",
            agent_id,
        )
    return int(val or 0)
