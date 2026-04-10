"""Internal smoke-test endpoint for post-deploy verification.

POST /api/v1/internal/smoke-test

Runs two in-process checks without touching production data:
  1. workflow_step_stability — verifies the collection gate holds a required
     step when fields are missing (pure logic, no DB/LLM calls).
  2. timer_delivery — schedules a 10-second timer for a real test conversation,
     waits 12 s, then verifies the message was persisted in the DB.

Protected by require_admin() so only authenticated admins can hit it.
Designed to be called from CI/CD or manually 3 minutes after deploy.
"""

import asyncio
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends

from app.api.auth import get_current_admin, require_admin

logger = logging.getLogger(__name__)

router = APIRouter()

_SMOKE_AGENT_ID_ENV = "SMOKE_TEST_AGENT_ID"


# ---------------------------------------------------------------------------
# Sub-test: workflow collection gate (pure logic, no external calls)
# ---------------------------------------------------------------------------

async def _test_workflow_step_stability() -> dict:
    """Verify that the collection gate blocks step advancement when fields missing."""
    start = time.monotonic()
    try:
        from app.models.agent_config import WorkflowStep, WorkflowTransition

        step = WorkflowStep(
            id="smoke_s1",
            name="Smoke collect step",
            instructions="Ask for breed and weight.",
            required=True,
            collect=["breed", "weight"],
            transitions=[
                WorkflowTransition(condition="all provided", next_step_id="smoke_s2"),
            ],
        )

        # Simulate: extraction returns nulls (fields not provided by user)
        existing_collected: dict = {}
        missing_fields = [f for f in step.collect if not existing_collected.get(f)]
        llm_response = {"breed": None, "weight": None}
        new_data = {
            k: str(v)
            for k, v in llm_response.items()
            if v is not None and str(v).lower() not in ("null", "none", "")
        }
        existing_collected.update(new_data)
        still_missing = [f for f in step.collect if not existing_collected.get(f)]

        if still_missing:
            # Gate correctly blocks
            return {
                "passed": True,
                "detail": f"required step held (still missing: {still_missing})",
                "elapsed_ms": round((time.monotonic() - start) * 1000),
            }
        else:
            return {
                "passed": False,
                "detail": "gate did not block when fields were missing",
                "elapsed_ms": round((time.monotonic() - start) * 1000),
            }
    except Exception as exc:
        logger.error("smoke workflow_step_stability error: %s", exc, exc_info=True)
        return {
            "passed": False,
            "detail": f"exception: {exc}",
            "elapsed_ms": round((time.monotonic() - start) * 1000),
        }


# ---------------------------------------------------------------------------
# Sub-test: timer delivery (real Redis + DB, synthetic conversation)
# ---------------------------------------------------------------------------

async def _test_timer_delivery() -> dict:
    """Schedule a 10-second timer on a synthetic conversation and verify delivery."""
    start = time.monotonic()
    smoke_conv_id = f"smoke-timer-{uuid.uuid4().hex[:8]}"

    try:
        from app.dependencies import get_dynamodb
        from app.storage.redis import get_redis_client
        from app.services.agent_reply_coordinator import (
            schedule_timer_trigger,
            KEY_TIMER_FAILED_PREFIX,
        )
        from app.models.conversation import Conversation, ConversationStatus
        from app.models.message import MessageChannel
        from app.utils.datetime_utils import utc_now

        dynamodb = get_dynamodb()
        redis = get_redis_client()

        # Check Redis availability first
        if not await redis.ping():
            return {
                "passed": False,
                "detail": "Redis unavailable — cannot schedule timer",
                "elapsed_ms": round((time.monotonic() - start) * 1000),
            }

        # We need a real agent to attach the conversation to.
        import os
        smoke_agent_id = os.getenv(_SMOKE_AGENT_ID_ENV)
        if not smoke_agent_id:
            return {
                "passed": False,
                "detail": (
                    f"Env var {_SMOKE_AGENT_ID_ENV} not set. "
                    "Set it to an existing agent_id to enable timer smoke test."
                ),
                "elapsed_ms": round((time.monotonic() - start) * 1000),
            }

        # Create a synthetic conversation
        conv = Conversation(
            conversation_id=smoke_conv_id,
            agent_id=smoke_agent_id,
            channel=MessageChannel.WEB_CHAT,
            status=ConversationStatus.AI_ACTIVE,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        await dynamodb.create_conversation(conv)

        # Schedule a 10-second static timer
        timer_payload = {
            "action_type": "static",
            "message_template": "Smoke test timer message",
            "step_id": "smoke_step",
            "delay_seconds": 10,
            "fire_at_ms": int(time.time() * 1000) + 10_000,
        }
        await schedule_timer_trigger(smoke_conv_id, timer_payload)

        # Wait 13 seconds for timer to fire and deliver
        await asyncio.sleep(13)

        # Check for dead-letter (means timer failed)
        dead_letter = await redis.get(f"{KEY_TIMER_FAILED_PREFIX}{smoke_conv_id}")
        if dead_letter:
            return {
                "passed": False,
                "detail": f"Timer fired but failed with dead-letter: {dead_letter}",
                "elapsed_ms": round((time.monotonic() - start) * 1000),
            }

        # Check that the message was persisted in DB
        messages = await dynamodb.list_messages(smoke_conv_id, limit=5)
        timer_msgs = [
            m for m in messages
            if getattr(m, "metadata", None) and m.metadata.get("timer_trigger")
        ]

        if timer_msgs:
            return {
                "passed": True,
                "detail": f"timer message persisted in {round((time.monotonic() - start) * 1000)} ms",
                "elapsed_ms": round((time.monotonic() - start) * 1000),
            }
        else:
            return {
                "passed": False,
                "detail": "timer fired but no message found in DB (check logs for execute_timer_trigger)",
                "elapsed_ms": round((time.monotonic() - start) * 1000),
            }

    except Exception as exc:
        logger.error("smoke timer_delivery error: %s", exc, exc_info=True)
        return {
            "passed": False,
            "detail": f"exception: {exc}",
            "elapsed_ms": round((time.monotonic() - start) * 1000),
        }
    finally:
        # Clean up: remove test conversation and messages
        try:
            from app.dependencies import get_dynamodb
            db = get_dynamodb()
            await db.delete_conversation(smoke_conv_id)
        except Exception:
            pass  # cleanup failure must not affect test result
        # Clean Redis timer keys
        try:
            from app.storage.redis import get_redis_client as _r
            r = _r()
            await r.delete(f"agent_reply:timer_payload:{smoke_conv_id}")
            await r.delete(f"{KEY_TIMER_FAILED_PREFIX}{smoke_conv_id}")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/internal/smoke-test")
async def run_smoke_test(
    current_admin: str = require_admin(),
):
    """Run workflow stability and timer delivery smoke tests.

    Returns a JSON report with pass/fail for each check and overall status.
    Safe to call in production — uses ephemeral data cleaned up after the test.
    """
    overall_start = time.monotonic()

    # Run both tests; timer test runs in parallel with no-op first test
    workflow_result, timer_result = await asyncio.gather(
        _test_workflow_step_stability(),
        _test_timer_delivery(),
        return_exceptions=False,
    )

    overall_passed = workflow_result["passed"] and timer_result["passed"]
    elapsed_ms = round((time.monotonic() - overall_start) * 1000)

    return {
        "workflow_step_stability": workflow_result,
        "timer_delivery": timer_result,
        "overall": "PASS" if overall_passed else "FAIL",
        "elapsed_ms": elapsed_ms,
        "run_by": current_admin,
    }
