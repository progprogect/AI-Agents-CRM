"""Image processor service for RAG semantic descriptions (OpenAI GPT-4V or Gemini)."""

import json
import logging
from typing import Any, Optional

from langchain_core.messages import HumanMessage

from app.prompts.image_description import (
    INITIAL_DESCRIPTION_PROMPT,
    get_comparative_prompt,
)
from app.prompts.user_attachment_vision import CHAT_USER_IMAGE_PROMPT
from app.services.llm_factory import LLMFactory, get_llm_factory
from app.utils.gemini_model_ids import resolve_vision_model_id
from app.utils.llm_provider import _get_vision_provider

logger = logging.getLogger(__name__)

# Max completion tokens for vision calls (OpenAI + Gemini image understanding).
VISION_MAX_OUTPUT_TOKENS = 1000


class ImageProcessorService:
    """Service for describing images for RAG indexing (OpenAI or Gemini)."""

    def __init__(self, llm_factory: LLMFactory):
        self.llm_factory = llm_factory

    async def _call_vision(
        self,
        content: list[dict] | str,
        agent_id: Optional[str] = None,
        agent_config: Optional[dict[str, Any]] = None,
        max_tokens: int = VISION_MAX_OUTPUT_TOKENS,
    ) -> str:
        """Call vision model (OpenAI or Gemini) and return text response."""
        vision_provider = _get_vision_provider(agent_config) if agent_config else "openai"
        model_id = resolve_vision_model_id(agent_config)

        if vision_provider == "google_ai_studio":
            from langchain_google_genai import ChatGoogleGenerativeAI
            from app.utils.llm_provider import _get_google_api_key_sync
            from app.config import get_settings

            settings = get_settings()
            google_key = _get_google_api_key_sync(settings)
            if not google_key:
                raise RuntimeError("Google AI Studio API key not found for vision")
            llm = ChatGoogleGenerativeAI(
                model=model_id,
                google_api_key=google_key,
                max_output_tokens=max_tokens,
            )
            msg = HumanMessage(content=content)
            response = await llm.ainvoke([msg])
            return (response.content or "").strip() if hasattr(response, "content") else str(response).strip()

        # OpenAI
        client = await self.llm_factory.get_client(agent_id)
        messages = [{"role": "user", "content": content}]
        response = await client.async_client.chat.completions.create(
            model=model_id,
            messages=messages,
            max_tokens=max_tokens,
        )
        return (response.choices[0].message.content or "").strip()

    async def describe_image(
        self,
        image_url: str,
        agent_id: Optional[str] = None,
        agent_config: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Get initial semantic description of an image.

        Returns the description text in English.
        """
        content = [
            {"type": "text", "text": INITIAL_DESCRIPTION_PROMPT},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
        try:
            return await self._call_vision(content, agent_id, agent_config, max_tokens=VISION_MAX_OUTPUT_TOKENS)
        except Exception as e:
            logger.error(f"Vision describe_image failed: {e}", exc_info=True)
            raise

    async def describe_image_for_chat_context(
        self,
        image_url: str,
        agent_id: Optional[str] = None,
        agent_config: Optional[dict[str, Any]] = None,
    ) -> str:
        """Short description of a user-uploaded image for text-only chat context."""
        content = [
            {"type": "text", "text": CHAT_USER_IMAGE_PROMPT},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
        try:
            return await self._call_vision(content, agent_id, agent_config, max_tokens=VISION_MAX_OUTPUT_TOKENS)
        except Exception as e:
            logger.error(f"Vision describe_image_for_chat_context failed: {e}", exc_info=True)
            raise

    async def describe_images_comparatively(
        self,
        image_descriptions: list[dict],
        agent_id: Optional[str] = None,
        agent_config: Optional[dict[str, Any]] = None,
    ) -> dict[str, str]:
        """
        Add distinguishing details for similar images.

        image_descriptions: list of {"id": str, "description": str}
        Returns: {document_id: "distinguishing details", ...}
        """
        if len(image_descriptions) < 2:
            return {}

        prompt = get_comparative_prompt(image_descriptions)
        labels = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"][: len(image_descriptions)]
        id_by_label = {labels[i]: image_descriptions[i]["id"] for i in range(len(image_descriptions))}

        try:
            text = await self._call_vision(prompt, agent_id, agent_config, max_tokens=VISION_MAX_OUTPUT_TOKENS)
            if not text:
                return {}
            text = text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            data = json.loads(text)
            return {id_by_label[k]: str(v) for k, v in data.items() if k in id_by_label}
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Comparative description parse failed: {e}")
            return {}
        except Exception as e:
            logger.error(f"Vision describe_images_comparatively failed: {e}", exc_info=True)
            raise


def get_image_processor_service() -> ImageProcessorService:
    """Get image processor service instance."""
    return ImageProcessorService(get_llm_factory())
