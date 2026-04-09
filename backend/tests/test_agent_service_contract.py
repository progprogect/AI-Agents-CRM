"""Contract tests for AgentService and AgentChain workflow integration."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.chains.agent_chain import AgentChain, _graph_cache
from app.models.agent_config import (
    AgentConfig,
    EscalationConfig,
    ModerationConfig,
    ProfileConfig,
    PromptsConfig,
    RAGConfig,
    WorkflowConfig,
    WorkflowStep,
    WorkflowTimerTrigger,
    WorkflowTransition,
)
from app.models.conversation import Conversation, ConversationStatus
from app.models.escalation import EscalationDecision, EscalationType
from app.models.message import MessageChannel
from app.services.agent_service import AgentService
from app.services.llm_factory import LLMFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_agent_config(**kwargs) -> AgentConfig:
    data = dict(
        agent_id="test-agent",
        project="test-proj",
        profile=ProfileConfig(agent_display_name="Agent", company_display_name="Co"),
        prompts=PromptsConfig(
            system={
                "persona": "You are {agent_display_name} at {company_display_name} ({specialty}).",
                "hard_rules": "",
                "goal": "",
            }
        ),
        rag=RAGConfig(enabled=False),
        escalation=EscalationConfig(enabled=False),
        moderation=ModerationConfig(enabled=False),
    )
    data.update(kwargs)
    return AgentConfig(**data)


def _make_agent_service(cfg, db, mod=None, esc=None, rag=None, channel_sender=None):
    """Build an AgentService with mocked dependencies."""
    if mod is None:
        mod = MagicMock()
        mod.check_pre_moderation = AsyncMock(return_value=(False, None))
        mod.check_post_moderation = AsyncMock(return_value=(False, None))
    if esc is None:
        esc = MagicMock()
        esc.detect_escalation = AsyncMock(
            return_value=EscalationDecision(
                needs_escalation=False,
                escalation_type=EscalationType.NONE,
                confidence=1.0,
                reason="ok",
                suggested_action="continue",
            )
        )
    if rag is None:
        rag = MagicMock()

    return AgentService(
        agent_config=cfg,
        llm_factory=MagicMock(spec=LLMFactory),
        escalation_service=esc,
        moderation_service=mod,
        rag_service=rag,
        dynamodb=db,
        channel_sender=channel_sender,
    )


def _mock_db(response_text="Hello"):
    db = MagicMock()
    db.get_conversation = AsyncMock(
        return_value=Conversation(
            conversation_id="c1",
            agent_id="a1",
            channel=MessageChannel.WEB_CHAT,
            status=ConversationStatus.AI_ACTIVE,
        )
    )
    db.create_message = AsyncMock()
    db.update_conversation = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# AgentService contract tests — graph integration
# ---------------------------------------------------------------------------

class TestAgentServiceContract(unittest.IsolatedAsyncioTestCase):
    """AgentService delegates to AgentChain.generate_response which is now the graph."""

    async def test_successful_response_contract(self) -> None:
        """Result dict has the expected keys on success."""
        cfg = _minimal_agent_config()
        db = _mock_db()
        svc = _make_agent_service(cfg, db)

        # Replace agent_chain with a mock that returns graph-style result
        chain = MagicMock()
        chain.generate_response = AsyncMock(
            return_value={
                "response": "Hello!",
                "escalate": False,
                "rag_context_used": False,
                "rag_media_url": None,
                "rag_media_type": None,
                "pending_timer": None,
            }
        )
        svc.agent_chain = chain

        out = await svc.process_message("hi", "c1", conversation_history=[])
        self.assertEqual(out["response"], "Hello!")
        self.assertFalse(out["escalate"])
        self.assertIn("agent_message_id", out)
        self.assertIn("agent_message_timestamp", out)

    async def test_escalation_from_graph_updates_db(self) -> None:
        """When graph returns escalate=True, conversation is updated to NEEDS_HUMAN."""
        cfg = _minimal_agent_config()
        db = _mock_db()
        svc = _make_agent_service(cfg, db)

        chain = MagicMock()
        chain.generate_response = AsyncMock(
            return_value={
                "response": None,
                "escalate": True,
                "escalation_reason": "user wants human",
                "escalation_type": "booking",
            }
        )
        svc.agent_chain = chain

        out = await svc.process_message("hi", "c1")
        self.assertTrue(out["escalate"])
        db.update_conversation.assert_called_once()
        call_kwargs = db.update_conversation.call_args.kwargs
        self.assertEqual(call_kwargs["status"], ConversationStatus.NEEDS_HUMAN)

    async def test_stale_reply_aborts_early(self) -> None:
        """If is_reply_stale returns True immediately, the graph is never called."""
        cfg = _minimal_agent_config()
        db = _mock_db()
        svc = _make_agent_service(cfg, db)

        chain = MagicMock()
        chain.generate_response = AsyncMock(return_value={"response": "should not reach"})
        svc.agent_chain = chain

        out = await svc.process_message(
            "hi", "c1",
            is_reply_stale=AsyncMock(return_value=True),
        )
        self.assertTrue(out.get("aborted"))
        chain.generate_response.assert_not_called()


# ---------------------------------------------------------------------------
# WorkflowConfig model tests
# ---------------------------------------------------------------------------

class TestWorkflowConfigModels(unittest.TestCase):
    def test_default_workflow_disabled(self) -> None:
        cfg = _minimal_agent_config()
        self.assertFalse(cfg.workflow.enabled)
        self.assertEqual(cfg.workflow.steps, [])

    def test_workflow_round_trip(self) -> None:
        cfg = _minimal_agent_config(
            workflow=WorkflowConfig(
                enabled=True,
                start_step_id="s1",
                steps=[
                    WorkflowStep(
                        id="s1",
                        name="Greeting",
                        instructions="Greet the user",
                        transitions=[
                            WorkflowTransition(
                                condition="user replied",
                                next_step_id="s2",
                                is_forced=True,
                            )
                        ],
                        timer_trigger=WorkflowTimerTrigger(
                            delay_seconds=3600,
                            message_template="Still need help?",
                        ),
                    )
                ],
            )
        )
        self.assertTrue(cfg.workflow.enabled)
        self.assertEqual(len(cfg.workflow.steps), 1)
        step = cfg.workflow.steps[0]
        self.assertEqual(step.id, "s1")
        self.assertTrue(step.transitions[0].is_forced)
        self.assertEqual(step.timer_trigger.delay_seconds, 3600)

    def test_from_dict_with_workflow(self) -> None:
        data = {
            "agent_id": "a1",
            "project": "p1",
            "profile": {"agent_display_name": "A", "company_display_name": "C"},
            "workflow": {
                "enabled": True,
                "start_step_id": "s1",
                "steps": [
                    {
                        "id": "s1",
                        "name": "Step 1",
                        "instructions": "Do something",
                    }
                ],
            },
        }
        cfg = AgentConfig.from_dict(data)
        self.assertTrue(cfg.workflow.enabled)
        self.assertEqual(cfg.workflow.steps[0].id, "s1")

    def test_from_dict_without_workflow_is_backward_compat(self) -> None:
        data = {
            "agent_id": "a2",
            "project": "p2",
            "profile": {"agent_display_name": "A", "company_display_name": "C"},
        }
        cfg = AgentConfig.from_dict(data)
        self.assertFalse(cfg.workflow.enabled)


# ---------------------------------------------------------------------------
# AgentChain graph cache tests
# ---------------------------------------------------------------------------

class TestAgentChainGraphCache(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        _graph_cache.clear()

    def tearDown(self) -> None:
        _graph_cache.clear()

    def test_same_config_returns_same_graph_key(self) -> None:
        from app.chains.agent_chain import _graph_cache_key
        cfg = _minimal_agent_config()
        key1 = _graph_cache_key(cfg.agent_id, cfg.workflow)
        key2 = _graph_cache_key(cfg.agent_id, cfg.workflow)
        self.assertEqual(key1, key2)

    def test_different_workflow_gives_different_key(self) -> None:
        from app.chains.agent_chain import _graph_cache_key
        cfg1 = _minimal_agent_config()
        cfg2 = _minimal_agent_config(
            workflow=WorkflowConfig(enabled=True, start_step_id="s1", steps=[])
        )
        self.assertNotEqual(
            _graph_cache_key(cfg1.agent_id, cfg1.workflow),
            _graph_cache_key(cfg2.agent_id, cfg2.workflow),
        )


# ---------------------------------------------------------------------------
# Timer trigger scheduling tests
# ---------------------------------------------------------------------------

class TestTimerTriggerScheduling(unittest.IsolatedAsyncioTestCase):
    async def test_pending_timer_in_result_triggers_schedule(self) -> None:
        """If graph returns pending_timer, AgentService calls schedule_timer_trigger."""
        cfg = _minimal_agent_config()
        db = _mock_db()
        svc = _make_agent_service(cfg, db)

        timer_payload = {
            "delay_seconds": 600,
            "message_template": "Still there?",
            "step_id": "s2",
            "fire_at_ms": 9999999999,
        }
        chain = MagicMock()
        chain.generate_response = AsyncMock(
            return_value={
                "response": "OK",
                "escalate": False,
                "rag_context_used": False,
                "rag_media_url": None,
                "rag_media_type": None,
                "pending_timer": timer_payload,
            }
        )
        svc.agent_chain = chain

        # schedule_timer_trigger is imported lazily inside process_message;
        # patch it at the coordinator module level so the import finds the mock.
        with patch(
            "app.services.agent_reply_coordinator.schedule_timer_trigger",
            new=AsyncMock(),
        ):
            # Also patch at the coordinator to intercept the lazy import
            import app.services.agent_reply_coordinator as coordinator_module
            schedule_mock = AsyncMock()
            original_fn = getattr(coordinator_module, "schedule_timer_trigger", None)
            coordinator_module.schedule_timer_trigger = schedule_mock
            try:
                await svc.process_message("hi", "c1")
                schedule_mock.assert_called_once_with("c1", timer_payload)
            finally:
                if original_fn is not None:
                    coordinator_module.schedule_timer_trigger = original_fn


if __name__ == "__main__":
    unittest.main()
