"""Questionnaire runtime service.

Owns:
- The user-scoped finite-state-machine kept in Redis (fill / edit menu / edit field).
- Creation of submissions and appending responses via the postgres repository.
- Merging the latest values so callers (Telegram flow, agent prompt) can use them.

Key design choice: the FSM key is scoped to ``(binding_id, external_user_id)``
so that ``/restart`` on the agent conversation does not accidentally kill an
ongoing questionnaire session.  ``handle_restart`` still clears it explicitly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.models.questionnaire import (
    QuestionnaireField,
    QuestionnaireSubmission,
    QuestionnaireTemplate,
    SubmissionSource,
)
from app.storage import postgres_questionnaire as repo
from app.storage.redis import get_redis_client

logger = logging.getLogger(__name__)


FSM_KEY_PREFIX = "questionnaire_fsm:"
FSM_TTL_SECONDS = 30 * 60  # 30 min; each action refreshes it


class FsmMode(str, Enum):
    IDLE = "idle"
    MENU = "menu"
    FILL = "fill"
    EDIT_MENU = "edit_menu"
    EDIT_FIELD = "edit_field"


@dataclass
class FsmState:
    """In-memory representation of the Redis-backed FSM row."""

    binding_id: str
    external_user_id: str
    mode: FsmMode
    cursor: int = 0  # index inside template.fields for FILL
    submission_id: Optional[str] = None
    pending_field_key: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "cursor": self.cursor,
            "submission_id": self.submission_id,
            "pending_field_key": self.pending_field_key,
        }

    @classmethod
    def from_dict(cls, binding_id: str, external_user_id: str, data: dict) -> "FsmState":
        return cls(
            binding_id=binding_id,
            external_user_id=external_user_id,
            mode=FsmMode(data.get("mode", FsmMode.IDLE.value)),
            cursor=int(data.get("cursor", 0)),
            submission_id=data.get("submission_id"),
            pending_field_key=data.get("pending_field_key"),
        )


def _fsm_key(binding_id: str, external_user_id: str) -> str:
    return f"{FSM_KEY_PREFIX}{binding_id}:{external_user_id}"


async def load_fsm(binding_id: str, external_user_id: str) -> Optional[FsmState]:
    redis = get_redis_client()
    try:
        data = await redis.get_json(_fsm_key(binding_id, external_user_id))
    except Exception as exc:
        logger.debug("questionnaire FSM load error: %s", exc)
        return None
    if not data:
        return None
    return FsmState.from_dict(binding_id, external_user_id, data)


async def save_fsm(state: FsmState) -> None:
    redis = get_redis_client()
    try:
        await redis.set_json(
            _fsm_key(state.binding_id, state.external_user_id),
            state.to_dict(),
            ttl=FSM_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning("questionnaire FSM save error: %s", exc)


async def clear_fsm(binding_id: str, external_user_id: str) -> None:
    redis = get_redis_client()
    try:
        await redis.delete(_fsm_key(binding_id, external_user_id))
    except Exception as exc:
        logger.debug("questionnaire FSM clear error: %s", exc)


# ── Template convenience ────────────────────────────────────────────────────


async def get_template_or_empty(agent_id: str) -> QuestionnaireTemplate:
    tpl = await repo.get_template(agent_id)
    if tpl is not None:
        return tpl
    return QuestionnaireTemplate(agent_id=agent_id, welcome_message="", fields=[])


def find_field(template: QuestionnaireTemplate, key: str) -> Optional[QuestionnaireField]:
    for f in template.fields:
        if f.key == key:
            return f
    return None


# ── FSM transitions ─────────────────────────────────────────────────────────


async def open_menu(binding_id: str, external_user_id: str) -> FsmState:
    """Enter the top-level questionnaire menu.  Does not create a submission."""
    state = FsmState(
        binding_id=binding_id,
        external_user_id=external_user_id,
        mode=FsmMode.MENU,
    )
    await save_fsm(state)
    return state


async def start_fill(
    *,
    binding_id: str,
    agent_id: str,
    external_user_id: str,
    channel: str = "telegram",
    conversation_id: Optional[str] = None,
) -> tuple[FsmState, QuestionnaireSubmission]:
    submission = await repo.start_submission(
        agent_id=agent_id,
        external_user_id=external_user_id,
        channel=channel,
        conversation_id=conversation_id,
        source=SubmissionSource.FILL,
    )
    state = FsmState(
        binding_id=binding_id,
        external_user_id=external_user_id,
        mode=FsmMode.FILL,
        cursor=0,
        submission_id=submission.submission_id,
    )
    await save_fsm(state)
    return state, submission


async def start_edit_field(
    *,
    state: FsmState,
    agent_id: str,
    field_key: str,
    channel: str = "telegram",
    conversation_id: Optional[str] = None,
) -> tuple[FsmState, QuestionnaireSubmission]:
    submission = await repo.start_submission(
        agent_id=agent_id,
        external_user_id=state.external_user_id,
        channel=channel,
        conversation_id=conversation_id,
        source=SubmissionSource.EDIT,
    )
    state.mode = FsmMode.EDIT_FIELD
    state.submission_id = submission.submission_id
    state.pending_field_key = field_key
    state.cursor = 0
    await save_fsm(state)
    return state, submission


async def switch_to_edit_menu(state: FsmState) -> FsmState:
    state.mode = FsmMode.EDIT_MENU
    state.pending_field_key = None
    state.cursor = 0
    await save_fsm(state)
    return state


async def submit_answer(
    *,
    state: FsmState,
    agent_id: str,
    template: QuestionnaireTemplate,
    value: str,
) -> tuple[FsmState, bool]:
    """Append a response and advance FSM.  Returns (new_state, completed_flag).

    ``completed_flag`` is True if this answer finished the active flow (either
    the last field of FILL mode or the single field of EDIT_FIELD mode).
    """
    if not state.submission_id:
        raise RuntimeError("submit_answer called without an active submission")

    value = (value or "").strip()
    if not value:
        return state, False

    if state.mode == FsmMode.FILL:
        if state.cursor < 0 or state.cursor >= len(template.fields):
            raise RuntimeError("FILL cursor out of range")
        field = template.fields[state.cursor]
        await repo.append_response(
            submission_id=state.submission_id,
            agent_id=agent_id,
            external_user_id=state.external_user_id,
            field_key=field.key,
            value=value,
        )
        state.cursor += 1
        if state.cursor >= len(template.fields):
            await repo.complete_submission(state.submission_id)
            state.mode = FsmMode.MENU
            state.submission_id = None
            state.cursor = 0
            await save_fsm(state)
            return state, True
        await save_fsm(state)
        return state, False

    if state.mode == FsmMode.EDIT_FIELD:
        if not state.pending_field_key:
            raise RuntimeError("EDIT_FIELD without pending_field_key")
        await repo.append_response(
            submission_id=state.submission_id,
            agent_id=agent_id,
            external_user_id=state.external_user_id,
            field_key=state.pending_field_key,
            value=value,
        )
        await repo.complete_submission(state.submission_id)
        state.mode = FsmMode.EDIT_MENU
        state.submission_id = None
        state.pending_field_key = None
        state.cursor = 0
        await save_fsm(state)
        return state, True

    raise RuntimeError(f"submit_answer in unexpected mode: {state.mode}")


async def skip_current(
    *,
    state: FsmState,
    template: QuestionnaireTemplate,
) -> tuple[FsmState, bool]:
    """Skip the current non-required field; returns (new_state, completed_flag)."""
    if state.mode != FsmMode.FILL:
        return state, False
    if state.cursor < 0 or state.cursor >= len(template.fields):
        return state, False
    field = template.fields[state.cursor]
    if field.required:
        return state, False
    state.cursor += 1
    if state.cursor >= len(template.fields):
        if state.submission_id:
            await repo.complete_submission(state.submission_id)
        state.mode = FsmMode.MENU
        state.submission_id = None
        state.cursor = 0
        await save_fsm(state)
        return state, True
    await save_fsm(state)
    return state, False


async def cancel(state: FsmState) -> FsmState:
    """Cancel the active session.  Keeps completed responses untouched."""
    if state.submission_id:
        try:
            await repo.cancel_submission(state.submission_id)
        except Exception as exc:
            logger.debug("cancel_submission failed: %s", exc)
    await clear_fsm(state.binding_id, state.external_user_id)
    state.mode = FsmMode.IDLE
    state.submission_id = None
    state.pending_field_key = None
    state.cursor = 0
    return state


# ── Queries ─────────────────────────────────────────────────────────────────


async def get_current_values(agent_id: str, external_user_id: str) -> dict[str, str]:
    """Most recent value per field_key; empty dict when user has no history."""
    try:
        return await repo.get_latest_values(agent_id, external_user_id)
    except Exception as exc:
        logger.debug("get_current_values error: %s", exc)
        return {}


async def write_workflow_field(
    *,
    agent_id: str,
    external_user_id: str,
    field_key: str,
    value: str,
    conversation_id: Optional[str] = None,
) -> None:
    """Write a single field value on behalf of the workflow engine.

    Creates a short-lived completed submission so the existing append-only
    schema (submission_id NOT NULL) is satisfied.  Safe to call without any
    active FSM session.  Errors are swallowed: the workflow must stay
    functional even when the questionnaire storage is unavailable.
    """
    try:
        submission = await repo.start_submission(
            agent_id=agent_id,
            external_user_id=external_user_id,
            channel="workflow",
            conversation_id=conversation_id,
            source=SubmissionSource.FILL,
        )
        await repo.append_response(
            submission_id=submission.submission_id,
            agent_id=agent_id,
            external_user_id=external_user_id,
            field_key=field_key,
            value=value,
        )
        await repo.complete_submission(submission.submission_id)
    except Exception as exc:
        logger.warning(
            "write_workflow_field failed for agent=%s field=%s: %s",
            agent_id, field_key, exc,
        )


def format_values_for_prompt(
    values: dict[str, str],
    template: Optional[QuestionnaireTemplate] = None,
) -> str:
    """Render ``key: value`` lines using template labels when available."""
    if not values:
        return ""
    label_by_key: dict[str, str] = {}
    if template:
        for f in template.fields:
            label_by_key[f.key] = f.label
    lines = []
    for key, value in values.items():
        label = label_by_key.get(key, key)
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)
