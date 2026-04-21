"""PostgreSQL repository for the questionnaire feature.

Tables: questionnaire_templates, questionnaire_submissions, questionnaire_responses.

Responses are append-only: every answer becomes a new row and the latest row per
``(agent_id, external_user_id, field_key)`` is the current value.  Nothing is
overwritten, so the admin UI can always show the full history of a field.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, NamedTuple, Optional

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

# Whitelist for ORDER BY in list_submissions (avoid dynamic SQL injection).
_SUBMISSION_SORT_SQL: dict[str, str] = {
    "started_at_desc": "s.started_at DESC",
    "started_at_asc": "s.started_at ASC",
    "completed_at_desc": "s.completed_at DESC NULLS LAST",
    "completed_at_asc": "s.completed_at ASC NULLS LAST",
}

_FIELD_KEY_FILTER_RE = re.compile(r"^[a-z][a-z0-9_]{0,29}$")


class SubmissionListEntry(NamedTuple):
    submission: QuestionnaireSubmission
    answers_count: int
    field_snapshot: dict[str, str]


def escape_ilike_pattern(user_fragment: str) -> str:
    """Escape ``%``, ``_``, ``\\`` for use inside ILIKE ... ESCAPE '\\'."""
    return (
        user_fragment.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _normalize_submission_sort(sort: Optional[str]) -> str:
    key = (sort or "started_at_desc").strip()
    if key not in _SUBMISSION_SORT_SQL:
        return "started_at_desc"
    return key


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


def _snapshot_dict_from_cell(raw: Any) -> dict[str, str]:
    """Normalise JSONB / JSON / str from ``jsonb_object_agg`` into ``dict[str, str]``."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        key = str(k)
        if v is None:
            out[key] = ""
        elif isinstance(v, str):
            out[key] = v
        else:
            out[key] = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
    return out


async def list_submissions(
    agent_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
    status: Optional[SubmissionStatus] = None,
    started_from: Optional[datetime] = None,
    started_to: Optional[datetime] = None,
    field_key: Optional[str] = None,
    value_search: Optional[str] = None,
    sort: Optional[str] = None,
    include_field_snapshot: bool = False,
) -> list[SubmissionListEntry]:
    """List submissions with ``answers_count`` in one query (no N+1).

    Optional ``field_key`` / ``value_search`` filter by **latest** value per
    ``(submission_id, field_key)`` within each session (append-only history).

    ``field_key`` must match ``^[a-z][a-z0-9_]{0,29}$`` or callers must validate;
    invalid keys result in an empty list.

    When ``include_field_snapshot`` is True, each row includes ``field_snapshot``:
    latest value per ``field_key`` within that submission (same semantics as filters).
    """
    fk = (field_key or "").strip() or None
    vs = (value_search or "").strip() or None
    if fk is not None and not _FIELD_KEY_FILTER_RE.match(fk):
        return []

    sort_key = _normalize_submission_sort(sort)
    order_sql = _SUBMISSION_SORT_SQL[sort_key]

    where_parts = ["s.agent_id = $1"]
    params: list[Any] = [agent_id]
    idx = 2

    if status:
        where_parts.append(f"s.status = ${idx}")
        params.append(status.value)
        idx += 1
    if started_from:
        where_parts.append(f"s.started_at >= ${idx}")
        params.append(started_from)
        idx += 1
    if started_to:
        where_parts.append(f"s.started_at <= ${idx}")
        params.append(started_to)
        idx += 1

    # Filter by latest-in-session values using CTE scoped to this agent.
    if fk is not None and vs is not None:
        pattern = f"%{escape_ilike_pattern(vs)}%"
        where_parts.append(
            "EXISTS (SELECT 1 FROM latest l WHERE l.submission_id = s.submission_id "
            f"AND l.field_key = ${idx} AND l.value ILIKE ${idx + 1} ESCAPE E'\\\\')"
        )
        params.extend([fk, pattern])
        idx += 2
    elif fk is not None:
        where_parts.append(
            f"EXISTS (SELECT 1 FROM latest l WHERE l.submission_id = s.submission_id "
            f"AND l.field_key = ${idx})"
        )
        params.append(fk)
        idx += 1
    elif vs is not None:
        pattern = f"%{escape_ilike_pattern(vs)}%"
        where_parts.append(
            "EXISTS (SELECT 1 FROM latest l WHERE l.submission_id = s.submission_id "
            f"AND l.value ILIKE ${idx} ESCAPE E'\\\\')"
        )
        params.append(pattern)
        idx += 1

    params.extend([limit, offset])
    lim_idx, off_idx = idx, idx + 1

    if include_field_snapshot:
        snapshot_sql = """
        , COALESCE(fs.snapshot, '{}'::jsonb) AS field_snapshot
        """
        snapshot_join = """
        LEFT JOIN LATERAL (
            SELECT jsonb_object_agg(l.field_key, to_jsonb(l.value)) AS snapshot
            FROM latest l
            WHERE l.submission_id = s.submission_id
        ) fs ON true
        """
    else:
        snapshot_sql = ""
        snapshot_join = ""

    sql = f"""
        WITH latest AS (
            SELECT DISTINCT ON (submission_id, field_key)
                submission_id, field_key, value
            FROM questionnaire_responses
            WHERE agent_id = $1
            ORDER BY submission_id, field_key, created_at DESC
        )
        SELECT s.*, COALESCE(rc.total, 0)::int AS answers_count
        {snapshot_sql}
        FROM questionnaire_submissions s
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::int AS total
            FROM questionnaire_responses r
            WHERE r.submission_id = s.submission_id
        ) rc ON true
        {snapshot_join}
        WHERE {" AND ".join(where_parts)}
        ORDER BY {order_sql}
        LIMIT ${lim_idx} OFFSET ${off_idx}
    """

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)

    out: list[SubmissionListEntry] = []
    for r in rows:
        sub = _submission_from_row(r)
        cnt = int(r["answers_count"])
        snap = _snapshot_dict_from_cell(r["field_snapshot"]) if include_field_snapshot else {}
        out.append(SubmissionListEntry(submission=sub, answers_count=cnt, field_snapshot=snap))
    return out


async def list_distinct_response_field_keys(agent_id: str) -> list[str]:
    """Distinct ``field_key`` values ever stored for this agent (incl. removed template fields)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT field_key
            FROM questionnaire_responses
            WHERE agent_id = $1
            ORDER BY field_key ASC
            """,
            agent_id,
        )
    return [str(r["field_key"]) for r in rows]


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
