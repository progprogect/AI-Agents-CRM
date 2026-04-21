"""Unit tests for the questionnaire service + Telegram callback contract.

The service is exercised against a fake in-memory repository so that FSM
transitions, append-only writes and completion signals are verified without a
real Postgres / Redis instance.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.questionnaire import (
    QuestionnaireField,
    QuestionnaireResponse,
    QuestionnaireSubmission,
    QuestionnaireTemplate,
    SubmissionSource,
    SubmissionStatus,
)
from app.services import questionnaire_service as qs
from app.services.telegram_questionnaire_flow import (
    CB_ANSWER_PREFIX,
    CB_CANCEL,
    CB_EDIT_FIELD_PREFIX,
    CB_EDIT_MENU,
    CB_SKIP,
    CB_START,
    is_questionnaire_callback,
)


@pytest.fixture
def template() -> QuestionnaireTemplate:
    return QuestionnaireTemplate(
        agent_id="a1",
        welcome_message="hi",
        fields=[
            QuestionnaireField(key="name", label="Имя", question="Как вас зовут?"),
            QuestionnaireField(
                key="role", label="Роль", question="Кто вы?",
                quick_replies=["Клиент", "Сотрудник"],
            ),
        ],
    )


class _FakeRepo:
    """In-memory replacement for ``app.storage.postgres_questionnaire``."""

    def __init__(self) -> None:
        self.submissions: list[QuestionnaireSubmission] = []
        self.responses: list[QuestionnaireResponse] = []

    async def start_submission(
        self,
        *,
        agent_id: str,
        external_user_id: str,
        channel: str = "telegram",
        conversation_id: Optional[str] = None,
        source: SubmissionSource = SubmissionSource.FILL,
    ) -> QuestionnaireSubmission:
        sub = QuestionnaireSubmission(
            submission_id=f"sub-{len(self.submissions) + 1}",
            agent_id=agent_id,
            external_user_id=external_user_id,
            channel=channel,
            conversation_id=conversation_id,
            status=SubmissionStatus.IN_PROGRESS,
            source=source,
            started_at=datetime.utcnow(),
        )
        self.submissions.append(sub)
        return sub

    async def complete_submission(self, submission_id: str) -> None:
        for s in self.submissions:
            if s.submission_id == submission_id:
                s.status = SubmissionStatus.COMPLETED

    async def cancel_submission(self, submission_id: str) -> None:
        for s in self.submissions:
            if s.submission_id == submission_id and s.status == SubmissionStatus.IN_PROGRESS:
                s.status = SubmissionStatus.CANCELLED

    async def append_response(
        self,
        *,
        submission_id: str,
        agent_id: str,
        external_user_id: str,
        field_key: str,
        value: str,
    ) -> QuestionnaireResponse:
        resp = QuestionnaireResponse(
            response_id=f"r-{len(self.responses) + 1}",
            submission_id=submission_id,
            agent_id=agent_id,
            external_user_id=external_user_id,
            field_key=field_key,
            value=value,
            created_at=datetime.utcnow(),
        )
        self.responses.append(resp)
        return resp

    async def get_latest_values(self, agent_id: str, external_user_id: str) -> dict[str, str]:
        latest: dict[str, str] = {}
        for r in self.responses:
            if r.agent_id == agent_id and r.external_user_id == external_user_id:
                latest[r.field_key] = r.value
        return latest


def _patch_repo(fake: _FakeRepo):
    return patch(
        "app.services.questionnaire_service.repo",
        new=fake,
    )


@pytest.mark.asyncio
async def test_fill_flow_creates_response_per_field_and_completes(template):
    fake = _FakeRepo()
    with _patch_repo(fake), patch(
        "app.services.questionnaire_service.save_fsm", new=AsyncMock()
    ):
        state, sub = await qs.start_fill(
            binding_id="b1", agent_id="a1", external_user_id="u1"
        )
        assert state.mode == qs.FsmMode.FILL and state.cursor == 0

        state, done = await qs.submit_answer(
            state=state, agent_id="a1", template=template, value="Alice"
        )
        assert not done and state.cursor == 1

        state, done = await qs.submit_answer(
            state=state, agent_id="a1", template=template, value="Клиент"
        )
        assert done is True
        assert state.mode == qs.FsmMode.MENU
        assert state.submission_id is None

    assert [r.value for r in fake.responses] == ["Alice", "Клиент"]
    assert fake.submissions[0].status == SubmissionStatus.COMPLETED


@pytest.mark.asyncio
async def test_edit_single_field_appends_new_row_without_overwrite(template):
    fake = _FakeRepo()
    # Pre-seed: user completed the full fill earlier.
    await fake.start_submission(agent_id="a1", external_user_id="u1")
    await fake.append_response(
        submission_id=fake.submissions[0].submission_id,
        agent_id="a1",
        external_user_id="u1",
        field_key="name",
        value="Alice",
    )

    with _patch_repo(fake), patch(
        "app.services.questionnaire_service.save_fsm", new=AsyncMock()
    ):
        state = qs.FsmState(binding_id="b1", external_user_id="u1", mode=qs.FsmMode.MENU)
        state, _sub = await qs.start_edit_field(
            state=state, agent_id="a1", field_key="name"
        )
        assert state.mode == qs.FsmMode.EDIT_FIELD

        state, done = await qs.submit_answer(
            state=state, agent_id="a1", template=template, value="Alicia"
        )
        assert done is True and state.mode == qs.FsmMode.EDIT_MENU

    # Two rows exist; latest is "Alicia" but old "Alice" remains in history.
    name_rows = [r for r in fake.responses if r.field_key == "name"]
    assert [r.value for r in name_rows] == ["Alice", "Alicia"]
    latest = await fake.get_latest_values("a1", "u1")
    assert latest["name"] == "Alicia"


@pytest.mark.asyncio
async def test_skip_non_required_advances_without_response(template):
    fake = _FakeRepo()
    # Make the first field optional.
    tpl = QuestionnaireTemplate(
        agent_id="a1",
        fields=[
            QuestionnaireField(key="nick", label="Ник", question="?", required=False),
            QuestionnaireField(key="name", label="Имя", question="?", required=True),
        ],
    )
    with _patch_repo(fake), patch(
        "app.services.questionnaire_service.save_fsm", new=AsyncMock()
    ):
        state, _ = await qs.start_fill(binding_id="b", agent_id="a1", external_user_id="u")
        state, done = await qs.skip_current(state=state, template=tpl)
        assert not done and state.cursor == 1

        state, done = await qs.submit_answer(
            state=state, agent_id="a1", template=tpl, value="Bob"
        )
        assert done is True

    assert [r.field_key for r in fake.responses] == ["name"]


@pytest.mark.asyncio
async def test_cancel_marks_submission_cancelled():
    fake = _FakeRepo()
    await fake.start_submission(agent_id="a1", external_user_id="u1")
    with _patch_repo(fake), patch(
        "app.services.questionnaire_service.clear_fsm", new=AsyncMock()
    ):
        state = qs.FsmState(
            binding_id="b",
            external_user_id="u1",
            mode=qs.FsmMode.FILL,
            submission_id=fake.submissions[0].submission_id,
        )
        await qs.cancel(state)
    assert fake.submissions[0].status == SubmissionStatus.CANCELLED


def test_callback_prefix_guard() -> None:
    assert is_questionnaire_callback("q:s")
    assert is_questionnaire_callback("q:a:2")
    assert not is_questionnaire_callback("pay_plan:x")
    assert not is_questionnaire_callback("")


@pytest.mark.asyncio
async def test_handle_user_message_short_circuits_on_active_fsm(template):
    """When FSM is in FILL mode, free text is routed to questionnaire flow
    and the agent pipeline (which lives in telegram_service) is skipped.

    This test mocks load_fsm / get_template_or_empty / submit_answer so the
    contract of ``handle_user_message`` can be validated without touching
    Telegram / Redis / Postgres.
    """
    from app.models.channel_binding import ChannelBinding, ChannelType
    from app.services.telegram_questionnaire_flow import handle_user_message

    fake_state = qs.FsmState(
        binding_id="b1",
        external_user_id="u1",
        mode=qs.FsmMode.FILL,
        cursor=0,
        submission_id="sub-1",
    )
    binding = ChannelBinding(
        binding_id="b1",
        agent_id="a1",
        channel_type=ChannelType.TELEGRAM,
        channel_account_id="999",
        metadata={},
    )

    submit_calls: list[str] = []

    async def fake_submit(**kwargs):
        submit_calls.append(kwargs["value"])
        new_state = kwargs["state"]
        new_state.cursor += 1
        return new_state, False

    with patch(
        "app.services.telegram_questionnaire_flow.qs.load_fsm",
        new=AsyncMock(return_value=fake_state),
    ), patch(
        "app.services.telegram_questionnaire_flow.qs.get_template_or_empty",
        new=AsyncMock(return_value=template),
    ), patch(
        "app.services.telegram_questionnaire_flow.qs.submit_answer",
        side_effect=fake_submit,
    ), patch(
        "app.services.telegram_questionnaire_flow._send", new=AsyncMock()
    ):
        consumed = await handle_user_message(
            db=MagicMock(),
            chat_id="u1",
            binding=binding,
            bot_token="t",
            text="Alice",
        )
    assert consumed is True
    assert submit_calls == ["Alice"]


@pytest.mark.asyncio
async def test_handle_user_message_ignores_when_no_fsm():
    from app.models.channel_binding import ChannelBinding, ChannelType
    from app.services.telegram_questionnaire_flow import handle_user_message

    binding = ChannelBinding(
        binding_id="b1",
        agent_id="a1",
        channel_type=ChannelType.TELEGRAM,
        channel_account_id="999",
        metadata={},
    )
    with patch(
        "app.services.telegram_questionnaire_flow.qs.load_fsm",
        new=AsyncMock(return_value=None),
    ):
        consumed = await handle_user_message(
            db=MagicMock(),
            chat_id="u1",
            binding=binding,
            bot_token="t",
            text="hi",
        )
    assert consumed is False


def test_callback_data_stays_within_telegram_limit() -> None:
    # Worst-case callback strings we generate.
    worst = [
        f"{CB_EDIT_FIELD_PREFIX}{'x' * 30}",  # 30-char field_key (our schema max)
        f"{CB_ANSWER_PREFIX}{7}",
        CB_START,
        CB_EDIT_MENU,
        CB_CANCEL,
        CB_SKIP,
    ]
    for cb in worst:
        assert len(cb.encode("utf-8")) <= 64, cb
