"""Tests for WorkflowAutoStep.schedule_anchor (on_step_enter / on_step_exit)."""

import pytest
from pydantic import ValidationError

from app.models.agent_config import (
    WorkflowAutoStep,
    WorkflowConfig,
    WorkflowStep,
    WorkflowTransition,
)


def _step(sid: str, name: str, transitions: list | None = None) -> WorkflowStep:
    return WorkflowStep(
        id=sid,
        name=name,
        instructions="x",
        collect=[],
        required=False,
        transitions=transitions or [],
        timer_trigger=None,
        quick_replies=[],
    )


def test_on_step_exit_requires_step_id() -> None:
    wf = WorkflowConfig(
        enabled=True,
        start_step_id="step_a",
        steps=[
            _step("step_a", "A", [WorkflowTransition(condition="", next_step_id="step_b")]),
            _step("step_b", "B", []),
        ],
        auto_steps=[
            WorkflowAutoStep(
                id="auto_exit",
                name="After leave A",
                source_id="step_a",
                schedule_anchor="on_step_exit",
                delay_seconds=10,
                action_type="static",
                message_template="bye",
            ),
            WorkflowAutoStep(
                id="auto_enter",
                name="After enter B",
                source_id="step_b",
                schedule_anchor="on_step_enter",
                delay_seconds=20,
                action_type="static",
                message_template="hi",
            ),
        ],
    )
    assert len(wf.auto_steps) == 2


def test_on_step_exit_rejects_unknown_source() -> None:
    with pytest.raises(ValidationError) as exc:
        WorkflowConfig(
            enabled=True,
            start_step_id="step_a",
            steps=[
                _step("step_a", "A"),
                _step("step_b", "B", []),
            ],
            auto_steps=[
                WorkflowAutoStep(
                    id="bad",
                    name="bad",
                    source_id="no_such_step",
                    schedule_anchor="on_step_exit",
                    delay_seconds=1,
                    action_type="static",
                    message_template="x",
                ),
            ],
        )
    assert "on_step_exit" in str(exc.value).lower() or "step" in str(exc.value).lower()


def test_on_step_exit_rejects_auto_step_source_id() -> None:
    with pytest.raises(ValidationError):
        WorkflowConfig(
            enabled=True,
            start_step_id="step_a",
            steps=[
                _step("step_a", "A"),
                _step("step_b", "B", []),
            ],
            auto_steps=[
                WorkflowAutoStep(
                    id="auto_chain",
                    name="chain",
                    source_id="step_a",
                    delay_seconds=5,
                    action_type="static",
                    message_template="a",
                ),
                WorkflowAutoStep(
                    id="bad_exit",
                    name="bad",
                    source_id="auto_chain",
                    schedule_anchor="on_step_exit",
                    delay_seconds=1,
                    action_type="static",
                    message_template="x",
                ),
            ],
        )


def test_legacy_auto_step_without_schedule_anchor_defaults_to_enter() -> None:
    """JSON without schedule_anchor must parse as on_step_enter."""
    raw = {
        "enabled": True,
        "start_step_id": "s1",
        "steps": [
            {
                "id": "s1",
                "name": "One",
                "instructions": "i",
                "collect": [],
                "required": False,
                "transitions": [],
                "timer_trigger": None,
                "quick_replies": [],
            },
        ],
        "auto_steps": [
            {
                "id": "a1",
                "name": "Follow",
                "source_id": "s1",
                "delay_seconds": 60,
                "action_type": "static",
                "message_template": "m",
                "prompt": "",
                "condition": None,
            },
        ],
    }
    wf = WorkflowConfig.model_validate(raw)
    assert wf.auto_steps[0].schedule_anchor == "on_step_enter"
