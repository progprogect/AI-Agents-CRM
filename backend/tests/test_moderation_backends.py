"""Tests for moderation backends and ModerationConfig defaults."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.agent_config import AgentConfig, ModerationConfig, ProfileConfig


def _minimal_agent_config(
    moderation: ModerationConfig,
) -> AgentConfig:
    return AgentConfig(
        agent_id="a1",
        project="p1",
        profile=ProfileConfig(
            agent_display_name="A",
            company_display_name="C",
        ),
        moderation=moderation,
    )


class TestModerationConfigDefaults(unittest.TestCase):
    def test_openai_default_model(self) -> None:
        m2 = ModerationConfig.model_validate({"provider": "openai", "enabled": True})
        self.assertEqual(m2.model, "omni-moderation-latest")

    def test_google_default_model(self) -> None:
        m = ModerationConfig.model_validate({"provider": "google_ai_studio", "enabled": True})
        self.assertEqual(m.model, "gemini-2.0-flash")


class TestGeminiJsonToResult(unittest.TestCase):
    def test_maps_to_result(self) -> None:
        from app.services.moderation_backends import _gemini_json_to_result

        data = {
            "flagged": True,
            "category_scores": {
                "hate": 0.9,
                "harassment": 0.0,
                "sexual": 0.0,
                "self-harm": 0.0,
                "violence": 0.0,
            },
        }
        r = _gemini_json_to_result(data)
        self.assertTrue(r.flagged)
        self.assertTrue(r.category_scores.get("hate", 0) > 0.5)


class TestModerateOpenAI(unittest.IsolatedAsyncioTestCase):
    async def test_passes_model_to_client(self) -> None:
        from app.services.moderation_backends import moderate_openai

        mod = ModerationConfig.model_validate({"provider": "openai", "model": "omni-moderation-latest"})
        agent_cfg = _minimal_agent_config(mod)

        mock_resp = MagicMock()
        mock_resp.results = [
            MagicMock(
                flagged=False,
                categories=MagicMock(model_dump=lambda: {"hate": False}),
                category_scores=MagicMock(
                    model_dump=lambda: {"hate": 0.0},
                    hate=0.0,
                ),
            )
        ]

        mock_client = MagicMock()
        mock_client.moderate = AsyncMock(return_value=mock_resp)

        mock_factory = MagicMock()
        mock_factory.get_client = AsyncMock(return_value=mock_client)

        await moderate_openai("hello", agent_cfg, mock_factory)

        mock_client.moderate.assert_awaited_once()
        call_args = mock_client.moderate.call_args
        self.assertEqual(call_args[0][0], "hello")
        self.assertEqual(call_args[1].get("model"), "omni-moderation-latest")


if __name__ == "__main__":
    unittest.main()
