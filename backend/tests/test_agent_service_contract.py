"""Contract tests for AgentService (orchestration, ATTACH_MEDIA, escalation short-circuit)."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from app.chains.agent_chain import AgentChain
from app.models.agent_config import (
    AgentConfig,
    EscalationConfig,
    ModerationConfig,
    ProfileConfig,
    PromptsConfig,
    RAGConfig,
)
from app.models.conversation import Conversation, ConversationStatus
from app.models.escalation import EscalationDecision, EscalationType
from app.models.message import MessageChannel
from app.services.agent_service import AgentService
from app.services.llm_factory import LLMFactory


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


class TestAgentServiceContract(unittest.IsolatedAsyncioTestCase):
    async def test_strips_attach_media_marker(self) -> None:
        cfg = _minimal_agent_config()
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
        mod = MagicMock()
        mod.check_pre_moderation = AsyncMock(return_value=(False, None))
        mod.check_post_moderation = AsyncMock(return_value=(False, None))
        rag = MagicMock()
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

        svc = AgentService(
            agent_config=cfg,
            llm_factory=MagicMock(spec=LLMFactory),
            escalation_service=esc,
            moderation_service=mod,
            rag_service=rag,
            dynamodb=db,
            channel_sender=None,
        )
        chain = MagicMock()
        chain.generate_response = AsyncMock(return_value="Hello " + AgentChain.ATTACH_MEDIA_MARKER)
        svc.agent_chain = chain

        out = await svc.process_message("hi", "c1", conversation_history=[])
        self.assertNotIn(AgentChain.ATTACH_MEDIA_MARKER, out["response"])
        self.assertEqual(out["response"].strip(), "Hello")

    async def test_escalation_short_circuits_before_llm(self) -> None:
        cfg = _minimal_agent_config(escalation=EscalationConfig(enabled=True))
        esc = MagicMock()
        esc.detect_escalation = AsyncMock(
            return_value=EscalationDecision(
                needs_escalation=True,
                escalation_type=EscalationType.BOOKING,
                confidence=0.9,
                reason="user asked human",
                suggested_action="handoff",
            )
        )
        mod = MagicMock()
        mod.check_pre_moderation = AsyncMock(return_value=(False, None))
        rag = MagicMock()
        db = MagicMock()
        db.update_conversation = AsyncMock()

        svc = AgentService(
            agent_config=cfg,
            llm_factory=MagicMock(spec=LLMFactory),
            escalation_service=esc,
            moderation_service=mod,
            rag_service=rag,
            dynamodb=db,
            channel_sender=None,
        )
        chain = MagicMock()
        chain.generate_response = AsyncMock(return_value="should not run")
        svc.agent_chain = chain

        out = await svc.process_message("hi", "c1", conversation_history=[])
        self.assertTrue(out.get("escalate"))
        chain.generate_response.assert_not_called()


if __name__ == "__main__":
    unittest.main()
