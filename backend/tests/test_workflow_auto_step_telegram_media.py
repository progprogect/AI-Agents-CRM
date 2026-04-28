"""WorkflowAutoStep Telegram attachment validation."""

import pytest
from pydantic import ValidationError

from app.models.agent_config import WorkflowAutoStep, WorkflowConfig, WorkflowStep


def _minimal_step(step_id: str = "s1") -> WorkflowStep:
    return WorkflowStep(
        id=step_id,
        name="S",
        instructions="i",
        collect=[],
        required=False,
        transitions=[],
        timer_trigger=None,
        quick_replies=[],
    )


def test_auto_step_telegram_defaults_none() -> None:
    a = WorkflowAutoStep(
        id="a1",
        name="A",
        source_id="s1",
        delay_seconds=10,
        action_type="static",
        message_template="hi",
    )
    assert a.telegram_attachment_type == "none"
    assert a.telegram_video_url is None
    assert a.telegram_video_note_file_id is None


def test_auto_step_video_url_requires_url() -> None:
    with pytest.raises(ValidationError):
        WorkflowAutoStep(
            id="a1",
            name="A",
            source_id="s1",
            delay_seconds=10,
            action_type="static",
            message_template="hi",
            telegram_attachment_type="video_url",
            telegram_video_url="",
        )


def test_auto_step_video_note_requires_file_id() -> None:
    with pytest.raises(ValidationError):
        WorkflowAutoStep(
            id="a1",
            name="A",
            source_id="s1",
            delay_seconds=10,
            action_type="static",
            message_template="hi",
            telegram_attachment_type="video_note",
            telegram_video_note_file_id="",
        )


def test_workflow_config_accepts_valid_telegram_attachments() -> None:
    wf = WorkflowConfig(
        enabled=True,
        start_step_id="s1",
        steps=[_minimal_step()],
        auto_steps=[
            WorkflowAutoStep(
                id="a1",
                name="A",
                source_id="s1",
                delay_seconds=10,
                action_type="static",
                message_template="x",
                telegram_attachment_type="video_url",
                telegram_video_url="https://example.com/v.mp4",
            ),
            WorkflowAutoStep(
                id="a2",
                name="B",
                source_id="s1",
                delay_seconds=10,
                action_type="static",
                message_template="",
                telegram_attachment_type="video_note",
                telegram_video_note_file_id="AgACAgIAAxkBAAAB",
            ),
        ],
    )
    assert len(wf.auto_steps) == 2
