"""Admin API for the questionnaire feature.

Endpoints (all under ``/api/v1/admin``):

- ``GET  /agents/{agent_id}/questionnaire``                — template
- ``PUT  /agents/{agent_id}/questionnaire``                — upsert template
- ``GET  /agents/{agent_id}/questionnaire/submissions``    — list fill/edit sessions
- ``GET  /agents/{agent_id}/questionnaire/response-field-keys`` — distinct field keys ever answered
- ``GET  /questionnaires/submissions/{submission_id}``     — single session + answers
- ``GET  /agents/{agent_id}/questionnaire/user/{external_user_id}``
      — latest values + full history for one user
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

from app.api.auth import require_admin
from app.models.questionnaire import (
    QuestionnaireField,
    QuestionnaireResponse,
    QuestionnaireSubmission,
    QuestionnaireTemplate,
    SubmissionStatus,
)
from app.storage import postgres_questionnaire as repo
from app.utils.datetime_utils import parse_query_datetime

logger = logging.getLogger(__name__)

router = APIRouter()

_FIELD_KEY_QUERY_RE = re.compile(r"^[a-z][a-z0-9_]{0,29}$")
_SUBMISSION_SORT_VALUES = frozenset(
    ("started_at_desc", "started_at_asc", "completed_at_desc", "completed_at_asc")
)
_VALUE_SEARCH_MAX_LEN = 200


# ── Request / response payloads ────────────────────────────────────────────


class UpsertQuestionnaireRequest(BaseModel):
    welcome_message: str = Field(default="", max_length=2000)
    completion_message: str = Field(default="", max_length=2000)
    fields: list[QuestionnaireField] = Field(default_factory=list)


class QuestionnaireResponsePayload(BaseModel):
    template: QuestionnaireTemplate
    submissions_count: int


class SubmissionListItem(BaseModel):
    submission: QuestionnaireSubmission
    answers_count: int


class SubmissionDetail(BaseModel):
    submission: QuestionnaireSubmission
    responses: list[QuestionnaireResponse]


class UserQuestionnaireDetail(BaseModel):
    external_user_id: str
    latest_values: dict[str, str]
    history: list[QuestionnaireResponse]


# ── Routes ─────────────────────────────────────────────────────────────────


@router.get("/agents/{agent_id}/questionnaire", response_model=QuestionnaireResponsePayload)
async def get_questionnaire(
    agent_id: str,
    _admin: str = require_admin(),
) -> QuestionnaireResponsePayload:
    tpl = await repo.get_template(agent_id)
    if tpl is None:
        tpl = QuestionnaireTemplate(agent_id=agent_id, welcome_message="", fields=[])
    count = await repo.count_submissions(agent_id)
    return QuestionnaireResponsePayload(template=tpl, submissions_count=count)


@router.put("/agents/{agent_id}/questionnaire", response_model=QuestionnaireTemplate)
async def put_questionnaire(
    agent_id: str,
    body: UpsertQuestionnaireRequest,
    _admin: str = require_admin(),
) -> QuestionnaireTemplate:
    try:
        tpl = QuestionnaireTemplate(
            agent_id=agent_id,
            welcome_message=body.welcome_message,
            completion_message=body.completion_message,
            fields=body.fields,
        )
    except ValidationError as exc:
        # Strip ``input`` / ``ctx`` / ``url`` so FastAPI can JSON-serialise the
        # 422 body regardless of the installed Pydantic / FastAPI version.
        clean = [
            {k: v for k, v in e.items() if k not in ("input", "ctx", "url")}
            for e in exc.errors()
        ]
        raise HTTPException(status_code=422, detail=clean) from exc
    return await repo.upsert_template(tpl)


@router.get(
    "/agents/{agent_id}/questionnaire/submissions",
    response_model=list[SubmissionListItem],
)
async def list_questionnaire_submissions(
    agent_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    started_from: Optional[str] = Query(default=None),
    started_to: Optional[str] = Query(default=None),
    field_key: Optional[str] = Query(
        default=None,
        description="Filter by this template field key (latest value in session).",
    ),
    value_search: Optional[str] = Query(
        default=None,
        description="Case-insensitive substring match on latest field value(s).",
    ),
    sort: str = Query(
        default="started_at_desc",
        description="started_at_desc | started_at_asc | completed_at_desc | completed_at_asc",
    ),
    _admin: str = require_admin(),
) -> list[SubmissionListItem]:
    status_enum: Optional[SubmissionStatus] = None
    if status:
        try:
            status_enum = SubmissionStatus(status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status}") from exc

    if sort not in _SUBMISSION_SORT_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown sort: {sort}. Allowed: {', '.join(sorted(_SUBMISSION_SORT_VALUES))}",
        )

    fk = (field_key or "").strip() or None
    if fk is not None and not _FIELD_KEY_QUERY_RE.match(fk):
        raise HTTPException(
            status_code=400,
            detail="field_key must match ^[a-z][a-z0-9_]{0,29}$",
        )

    vs = (value_search or "").strip() or None
    if vs is not None and len(vs) > _VALUE_SEARCH_MAX_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"value_search too long (max {_VALUE_SEARCH_MAX_LEN} characters)",
        )

    try:
        dt_from: Optional[datetime] = parse_query_datetime(started_from, end_of_day=False)
        dt_to: Optional[datetime] = parse_query_datetime(started_to, end_of_day=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows = await repo.list_submissions(
        agent_id,
        limit=limit,
        offset=offset,
        status=status_enum,
        started_from=dt_from,
        started_to=dt_to,
        field_key=fk,
        value_search=vs,
        sort=sort,
    )

    return [SubmissionListItem(submission=e.submission, answers_count=e.answers_count) for e in rows]


@router.get(
    "/agents/{agent_id}/questionnaire/response-field-keys",
    response_model=list[str],
)
async def list_response_field_keys(
    agent_id: str,
    _admin: str = require_admin(),
) -> list[str]:
    """Distinct ``field_key`` values from stored responses (includes keys no longer on the template)."""
    return await repo.list_distinct_response_field_keys(agent_id)


@router.get(
    "/questionnaires/submissions/{submission_id}",
    response_model=SubmissionDetail,
)
async def get_submission_detail(
    submission_id: str,
    _admin: str = require_admin(),
) -> SubmissionDetail:
    sub = await repo.get_submission(submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    responses = await repo.list_responses_by_submission(submission_id)
    return SubmissionDetail(submission=sub, responses=responses)


@router.get(
    "/agents/{agent_id}/questionnaire/user/{external_user_id}",
    response_model=UserQuestionnaireDetail,
)
async def get_user_questionnaire(
    agent_id: str,
    external_user_id: str,
    _admin: str = require_admin(),
) -> UserQuestionnaireDetail:
    latest = await repo.get_latest_values(agent_id, external_user_id)
    history = await repo.list_user_responses(agent_id, external_user_id)
    return UserQuestionnaireDetail(
        external_user_id=external_user_id,
        latest_values=latest,
        history=history,
    )
