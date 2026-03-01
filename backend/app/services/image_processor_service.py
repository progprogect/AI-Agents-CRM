"""Image processor service using GPT-4V for RAG semantic descriptions."""

import json
import logging
from typing import Optional

from app.config import get_settings
from app.prompts.image_description import (
    INITIAL_DESCRIPTION_PROMPT,
    get_comparative_prompt,
)
from app.services.llm_factory import LLMFactory, get_llm_factory

logger = logging.getLogger(__name__)

# GPT-4V model for vision
VISION_MODEL = "gpt-4o"


class ImageProcessorService:
    """Service for describing images with GPT-4V for RAG indexing."""

    def __init__(self, llm_factory: LLMFactory):
        self.llm_factory = llm_factory

    async def describe_image(self, image_url: str, agent_id: Optional[str] = None) -> str:
        """
        Get initial semantic description of an image using GPT-4V.

        Returns the description text in English.
        """
        client = await self.llm_factory.get_client(agent_id)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": INITIAL_DESCRIPTION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url},
                    },
                ],
            }
        ]
        try:
            response = await client.async_client.chat.completions.create(
                model=VISION_MODEL,
                messages=messages,
                max_tokens=300,
            )
            text = response.choices[0].message.content or ""
            return text.strip()
        except Exception as e:
            logger.error(f"GPT-4V describe_image failed: {e}", exc_info=True)
            raise

    async def describe_images_comparatively(
        self,
        image_descriptions: list[dict],
        agent_id: Optional[str] = None,
    ) -> dict[str, str]:
        """
        Add distinguishing details for similar images.

        image_descriptions: list of {"id": str, "description": str}
        Returns: {document_id: "distinguishing details", ...}
        """
        if len(image_descriptions) < 2:
            return {}

        client = await self.llm_factory.get_client(agent_id)
        prompt = get_comparative_prompt(image_descriptions)
        labels = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"][: len(image_descriptions)]
        id_by_label = {labels[i]: image_descriptions[i]["id"] for i in range(len(image_descriptions))}

        try:
            response = await client.async_client.chat.completions.create(
                model=VISION_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            text = response.choices[0].message.content or "{}"
            # Extract JSON from response (may be wrapped in markdown)
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
            logger.error(f"GPT-4V describe_images_comparatively failed: {e}", exc_info=True)
            raise


def get_image_processor_service() -> ImageProcessorService:
    """Get image processor service instance."""
    return ImageProcessorService(get_llm_factory())
