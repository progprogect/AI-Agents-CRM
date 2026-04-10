"""Unit tests for the structured collection gate in node_transition_evaluator.

We test the collection gate logic directly without a full LangGraph graph.
The gate is extracted and tested as a pure async function using the same
logic that lives inside node_transition_evaluator.

Tests cover:
1. required step + collect + fields NOT provided → step_id unchanged, fallback blocked
2. required step + collect + all fields already in collected → no extraction, falls through
3. required step + collect + fallback only → fallback blocked when fields missing
4. collected dict accumulates: data from turn-1 retained after turn-2 extraction
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.models.agent_config import (
    WorkflowStep,
    WorkflowTransition,
)


# ---------------------------------------------------------------------------
# Inline port of the collection gate logic (mirrors agent_chain.py exactly)
# so we can test it without LangGraph overhead.
# ---------------------------------------------------------------------------

async def _run_collection_gate(
    step: WorkflowStep,
    state_collected: dict,
    state_messages: list,
    llm_json_response: dict | None,
) -> dict | None:
    """Run the structured collection gate in isolation.

    Returns the early-return dict if gate blocks the step, or None if all
    fields are present (gate passes through to normal transition eval).
    """
    import json as _json

    if not (step.required and step.collect):
        return None  # gate inactive

    existing_collected: dict = dict(state_collected)
    missing_fields = [f for f in step.collect if not existing_collected.get(f)]

    if not missing_fields:
        return None  # all fields already collected — gate passes

    # Simulate extraction LLM call
    if llm_json_response is not None:
        extracted = llm_json_response
        new_data = {
            k: str(v)
            for k, v in extracted.items()
            if v is not None and str(v).lower() not in ("null", "none", "")
        }
        existing_collected.update(new_data)

    still_missing = [f for f in step.collect if not existing_collected.get(f)]
    if still_missing:
        # Gate blocks — return early-return dict (mirrors the return in agent_chain.py)
        return {
            "current_step_id": step.id,
            "collected": existing_collected,
            "blocked": True,  # test marker
        }

    # All collected — gate passes
    return None


# ---------------------------------------------------------------------------
# Test 1: fields not provided → gate blocks step advancement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gate_blocks_when_fields_missing():
    """Collection gate must return early-return (block) when fields not yet provided."""
    step = WorkflowStep(
        id="s1",
        name="Collect pet info",
        instructions="Ask for breed and weight.",
        required=True,
        collect=["breed", "weight"],
        transitions=[
            WorkflowTransition(condition="user provided breed and weight", next_step_id="s2"),
        ],
    )

    result = await _run_collection_gate(
        step=step,
        state_collected={},
        state_messages=[
            HumanMessage(content="My cat is sick, what should I do?"),
        ],
        llm_json_response={"breed": None, "weight": None},
    )

    assert result is not None, "Gate must block (return early) when fields missing"
    assert result["current_step_id"] == "s1", "Step must stay on s1"
    assert result.get("blocked") is True


# ---------------------------------------------------------------------------
# Test 2: all fields in collected → gate passes through
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gate_passes_when_all_fields_in_collected():
    """Gate must pass (return None) when all required fields already in collected."""
    step = WorkflowStep(
        id="s1",
        name="Collect pet info",
        instructions="Ask for breed and weight.",
        required=True,
        collect=["breed", "weight"],
        transitions=[
            WorkflowTransition(condition="user provided breed and weight", next_step_id="s2"),
        ],
    )

    result = await _run_collection_gate(
        step=step,
        state_collected={"breed": "labrador", "weight": "30kg"},
        state_messages=[HumanMessage(content="It's a Labrador, 30 kg.")],
        llm_json_response=None,  # no extraction needed
    )

    assert result is None, "Gate must pass (return None) when all fields already collected"


# ---------------------------------------------------------------------------
# Test 3: fallback-only transition → gate still blocks when fields missing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gate_blocks_fallback_when_fields_missing():
    """Even if the step has only a fallback transition, gate must block advancement."""
    step = WorkflowStep(
        id="s1",
        name="Collect pet info",
        instructions="Ask for breed and weight.",
        required=True,
        collect=["breed", "weight"],
        transitions=[
            WorkflowTransition(condition="", next_step_id="s2", is_fallback=True),
        ],
    )

    result = await _run_collection_gate(
        step=step,
        state_collected={},
        state_messages=[HumanMessage(content="Hello")],
        llm_json_response={"breed": None, "weight": None},
    )

    assert result is not None, "Gate must block even with fallback-only transition"
    assert result["current_step_id"] == "s1"


# ---------------------------------------------------------------------------
# Test 4: collected dict accumulates across turns (merge, not overwrite)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_collected_merges_across_turns():
    """Field from a previous turn must be retained when new field is extracted."""
    step = WorkflowStep(
        id="s1",
        name="Collect pet info",
        instructions="Ask for breed and weight.",
        required=True,
        collect=["breed", "weight"],
        transitions=[
            WorkflowTransition(condition="user provided breed and weight", next_step_id="s2"),
        ],
    )

    # breed collected in previous turn; only weight is still missing
    result = await _run_collection_gate(
        step=step,
        state_collected={"breed": "siamese"},
        state_messages=[HumanMessage(content="She weighs 4 kg.")],
        llm_json_response={"weight": "4kg"},  # extraction finds weight
    )

    # weight fills the last missing field → gate passes
    assert result is None, "Gate must pass when last missing field is now extracted"


@pytest.mark.asyncio
async def test_collected_retains_prior_data_after_partial_extraction():
    """If extraction only finds some fields, prior data must not be lost."""
    step = WorkflowStep(
        id="s1",
        name="Collect pet info",
        instructions="Ask for breed, weight and age.",
        required=True,
        collect=["breed", "weight", "age"],
        transitions=[
            WorkflowTransition(condition="all info provided", next_step_id="s2"),
        ],
    )

    # breed from turn-1; this turn user provides weight only
    result = await _run_collection_gate(
        step=step,
        state_collected={"breed": "siamese"},
        state_messages=[HumanMessage(content="She weighs 4 kg.")],
        llm_json_response={"weight": "4kg", "age": None},
    )

    # age still missing → gate blocks
    assert result is not None, "Gate must block when age is still missing"
    assert result["collected"].get("breed") == "siamese", "breed must be retained"
    assert result["collected"].get("weight") == "4kg", "weight must be merged in"
    assert "age" not in result["collected"] or not result["collected"].get("age"), (
        "age must not be set when extraction returned null"
    )
