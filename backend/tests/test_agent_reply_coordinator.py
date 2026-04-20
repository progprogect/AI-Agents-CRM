"""Tests for debounced agent reply scheduling (Redis notify + stale abort)."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.agent_reply_coordinator import notify_user_message_saved


class TestNotifyUserMessageSaved(unittest.IsolatedAsyncioTestCase):
    async def test_returns_disabled_when_debounce_zero(self) -> None:
        with patch("app.services.agent_reply_coordinator.get_settings") as gs:
            m = MagicMock()
            m.agent_reply_debounce_seconds = 0
            gs.return_value = m
            r = await notify_user_message_saved(
                "c1",
                agent_user_message="hello",
                last_user_plain_content="hello",
            )
            self.assertEqual(r, "disabled")

    async def test_returns_fallback_when_redis_ping_fails(self) -> None:
        with patch("app.services.agent_reply_coordinator.get_settings") as gs:
            m = MagicMock()
            m.agent_reply_debounce_seconds = 30
            gs.return_value = m
            with patch(
                "app.services.agent_reply_coordinator.get_redis_client"
            ) as gr:
                rc = MagicMock()
                rc.ping = AsyncMock(return_value=False)
                gr.return_value = rc
                r = await notify_user_message_saved(
                    "c1",
                    agent_user_message="hello",
                    last_user_plain_content="hello",
                )
                self.assertEqual(r, "fallback")

    async def test_returns_scheduled_when_redis_ok(self) -> None:
        with patch("app.services.agent_reply_coordinator.get_settings") as gs:
            m = MagicMock()
            m.agent_reply_debounce_seconds = 30
            gs.return_value = m
            with patch(
                "app.services.agent_reply_coordinator.get_redis_client"
            ) as gr:
                rc = MagicMock()
                rc.ping = AsyncMock(return_value=True)
                rc.incr = AsyncMock(return_value=1)
                rc.set = AsyncMock(return_value=True)
                rc.zadd = AsyncMock(return_value=1)
                rc.zrem = AsyncMock(return_value=1)
                rc.delete = AsyncMock(return_value=1)
                gr.return_value = rc
                r = await notify_user_message_saved(
                    "c1",
                    agent_user_message="hello",
                    last_user_plain_content="hello",
                )
                self.assertEqual(r, "scheduled")
                rc.incr.assert_awaited()
                rc.zadd.assert_awaited()


class TestProcessMessageStale(unittest.IsolatedAsyncioTestCase):
    async def test_aborted_when_stale_before_rag(self) -> None:
        from app.models.agent_config import AgentConfig
        from app.services.agent_service import AgentService

        cfg_dict = {
            "agent_id": "a1",
            "project": "test",
            "profile": {
                "agent_display_name": "A",
                "company_display_name": "C",
            },
            "moderation": {"enabled": False},
            "rag": {"enabled": False},
        }
        agent_config = AgentConfig.from_dict(cfg_dict)

        db = MagicMock()
        db.update_conversation = AsyncMock()

        esc = MagicMock()
        esc.detect_escalation = AsyncMock(
            return_value=MagicMock(needs_escalation=False)
        )
        mod = MagicMock()
        mod.check_pre_moderation = AsyncMock(return_value=(False, None))
        mod.check_post_moderation = AsyncMock(return_value=(False, None))
        rag = MagicMock()

        svc = AgentService(
            agent_config=agent_config,
            llm_factory=MagicMock(),
            escalation_service=esc,
            moderation_service=mod,
            rag_service=rag,
            db=db,
            channel_sender=None,
        )
        stale = AsyncMock(return_value=True)
        result = await svc.process_message(
            "hi",
            "conv-1",
            conversation_history=[],
            is_reply_stale=stale,
        )
        self.assertTrue(result.get("aborted"))
        self.assertIsNone(result.get("response"))


class TestEscalationDisabled(unittest.IsolatedAsyncioTestCase):
    async def test_detect_escalation_not_called_when_escalation_disabled(self) -> None:
        from app.models.agent_config import AgentConfig
        from app.services.agent_service import AgentService

        cfg_dict = {
            "agent_id": "a1",
            "project": "test",
            "profile": {
                "agent_display_name": "A",
                "company_display_name": "C",
            },
            "moderation": {"enabled": False},
            "rag": {"enabled": False},
            "escalation": {"enabled": False},
        }
        agent_config = AgentConfig.from_dict(cfg_dict)

        db = MagicMock()
        db.update_conversation = AsyncMock()
        db.get_conversation = AsyncMock(return_value=None)

        esc = MagicMock()
        esc.detect_escalation = AsyncMock(
            return_value=MagicMock(needs_escalation=False)
        )
        mod = MagicMock()
        mod.check_pre_moderation = AsyncMock(return_value=(False, None))
        mod.check_post_moderation = AsyncMock(return_value=(False, None))
        rag = MagicMock()

        svc = AgentService(
            agent_config=agent_config,
            llm_factory=MagicMock(),
            escalation_service=esc,
            moderation_service=mod,
            rag_service=rag,
            db=db,
            channel_sender=None,
        )
        # generate_response now returns a dict (graph result contract)
        svc.agent_chain.generate_response = AsyncMock(
            return_value={
                "response": "Hello",
                "escalate": False,
                "rag_context_used": False,
                "rag_media_url": None,
                "rag_media_type": None,
                "pending_timer": None,
            }
        )

        result = await svc.process_message(
            "hi",
            "conv-1",
            conversation_history=[],
            is_reply_stale=None,
        )
        esc.detect_escalation.assert_not_called()
        self.assertEqual(result.get("response"), "Hello")


if __name__ == "__main__":
    unittest.main()
