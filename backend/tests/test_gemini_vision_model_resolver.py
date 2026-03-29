"""Tests for resolve_vision_model_id (RAG + inbound chat images)."""

import unittest

from app.utils.gemini_model_ids import (
    GEMINI_VISION_DEFAULT,
    OPENAI_VISION_MODEL_ID,
    resolve_vision_model_id,
)


class TestResolveVisionModelId(unittest.TestCase):
    def test_none_config_is_openai_default(self) -> None:
        self.assertEqual(resolve_vision_model_id(None), OPENAI_VISION_MODEL_ID)

    def test_openai_vision_provider_gpt4o(self) -> None:
        cfg = {
            "rag": {"vision_provider": "openai"},
            "llm": {"provider": "openai"},
        }
        self.assertEqual(resolve_vision_model_id(cfg), OPENAI_VISION_MODEL_ID)

    def test_google_without_vision_model_default_gemini_31(self) -> None:
        cfg = {
            "rag": {"vision_provider": "google_ai_studio"},
            "llm": {"provider": "google_ai_studio"},
        }
        self.assertEqual(resolve_vision_model_id(cfg), GEMINI_VISION_DEFAULT)

    def test_google_with_explicit_vision_model(self) -> None:
        cfg = {
            "rag": {
                "vision_provider": "google_ai_studio",
                "vision_model": "gemini-3.1-pro-preview",
            },
            "llm": {"provider": "google_ai_studio"},
        }
        self.assertEqual(resolve_vision_model_id(cfg), "gemini-3.1-pro-preview")

    def test_rag_vision_provider_overrides_llm_for_provider_resolution(self) -> None:
        """Vision path uses rag.vision_provider first (see _get_vision_provider)."""
        cfg = {
            "rag": {
                "vision_provider": "google_ai_studio",
                "vision_model": "gemini-3-flash-preview",
            },
            "llm": {"provider": "openai"},
        }
        self.assertEqual(resolve_vision_model_id(cfg), "gemini-3-flash-preview")

    def test_nested_ragconfig_object_in_dict(self) -> None:
        """Resolver reads vision_model from Pydantic RAGConfig nested in dict."""
        from app.models.agent_config import RAGConfig

        rag = RAGConfig(
            vision_provider="google_ai_studio",
            vision_model="gemini-3.1-pro-preview",
        )
        cfg = {"rag": rag, "llm": {"provider": "google_ai_studio"}}
        self.assertEqual(resolve_vision_model_id(cfg), "gemini-3.1-pro-preview")


if __name__ == "__main__":
    unittest.main()
