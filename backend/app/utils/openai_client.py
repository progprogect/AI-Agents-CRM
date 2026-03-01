"""OpenAI client wrapper and LLM factory with multi-provider support."""

import logging
from functools import lru_cache
from typing import Optional

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from openai import AsyncOpenAI, OpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from app.config import Settings, get_settings
from app.models.agent_config import AgentConfig, EmbeddingsConfig
from app.storage.secrets import SecretsManager, get_secrets_manager
from app.storage.postgres_secrets import PostgresSecretsManager, get_postgres_secrets_manager
from app.utils.llm_provider import (
    create_chat_model,
    create_embeddings as create_embeddings_model,
    _get_google_api_key_sync,
)

logger = logging.getLogger(__name__)


class OpenAIClientWrapper:
    """OpenAI client wrapper with retry and error handling."""

    def __init__(self, api_key: str, settings: Settings):
        """Initialize OpenAI client."""
        # Ensure API key is clean (no JSON artifacts)
        api_key = api_key.strip().strip('"').strip("'")
        if api_key.startswith('{') and api_key.endswith('}'):
            try:
                import json
                parsed = json.loads(api_key)
                if isinstance(parsed, dict):
                    for key in ["OPENAI_API_KEY", "openai_api_key", "api_key", "value"]:
                        if key in parsed:
                            api_key = parsed[key]
                            break
            except Exception as e:
                logger.error(f"Error extracting from JSON in __init__: {e}")
                pass
        api_key = api_key.strip().strip('"').strip("'")
        self.api_key = api_key
        self.settings = settings
        self._async_client: Optional[AsyncOpenAI] = None
        self._sync_client: Optional[OpenAI] = None

    @property
    def async_client(self) -> AsyncOpenAI:
        """Get async OpenAI client."""
        if self._async_client is None:
            # Ensure api_key is a clean string, not JSON
            api_key = self.api_key
            if isinstance(api_key, str):
                api_key = api_key.strip().strip('"').strip("'")
                # If it looks like JSON, try to extract the actual key
                if api_key.startswith('{') and api_key.endswith('}'):
                    try:
                        import json
                        parsed = json.loads(api_key)
                        if isinstance(parsed, dict):
                            for key in ["OPENAI_API_KEY", "openai_api_key", "api_key", "value"]:
                                if key in parsed and isinstance(parsed[key], str):
                                    api_key = parsed[key]
                                    break
                    except Exception as e:
                        logger.error(f"Error extracting from JSON in async_client: {e}")
                        pass
                api_key = api_key.strip().strip('"').strip("'")
            self._async_client = AsyncOpenAI(api_key=api_key, timeout=self.settings.openai_timeout)
        return self._async_client

    @property
    def sync_client(self) -> OpenAI:
        """Get sync OpenAI client."""
        if self._sync_client is None:
            # Ensure api_key is a clean string, not JSON
            api_key = self.api_key
            if isinstance(api_key, str):
                api_key = api_key.strip().strip('"').strip("'")
                # If it looks like JSON, try to extract the actual key
                if api_key.startswith('{') and api_key.endswith('}'):
                    try:
                        import json
                        parsed = json.loads(api_key)
                        if isinstance(parsed, dict):
                            for key in ["OPENAI_API_KEY", "openai_api_key", "api_key", "value"]:
                                if key in parsed and isinstance(parsed[key], str):
                                    api_key = parsed[key]
                                    break
                    except Exception:
                        pass
                api_key = api_key.strip().strip('"').strip("'")
            self._sync_client = OpenAI(api_key=api_key, timeout=self.settings.openai_timeout)
        return self._sync_client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    async def create_chat_completion(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ):
        """Create chat completion with retry."""
        model_name = model or self.settings.openai_model
        max_tokens_value = max_tokens or self.settings.openai_max_tokens
        
        # Use correct parameter based on model
        if requires_max_completion_tokens(model_name):
            kwargs["max_completion_tokens"] = max_tokens_value
        else:
            kwargs["max_tokens"] = max_tokens_value
        
        return await self.async_client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature or self.settings.openai_temperature,
            **kwargs,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    async def create_embedding(
        self,
        text: str,
        model: Optional[str] = None,
        dimensions: Optional[int] = None,
    ):
        """Create embedding with retry."""
        kwargs = {}
        if dimensions:
            kwargs["dimensions"] = dimensions

        return await self.async_client.embeddings.create(
            model=model or self.settings.openai_embedding_model,
            input=text,
            **kwargs,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    async def moderate(self, input_text: str):
        """Moderate content with retry."""
        return await self.async_client.moderations.create(input=input_text)


class LLMFactory:
    """Factory for creating LLM clients (OpenAI, Google AI Studio) and embeddings."""

    def __init__(self, settings: Settings, secrets_manager: SecretsManager):
        """Initialize LLM factory."""
        self.settings = settings
        self.secrets_manager = secrets_manager
        self._clients: dict[str, OpenAIClientWrapper] = {}
        self._embeddings_cache: dict[tuple[str, str], Embeddings] = {}

    def _clean_api_key(self, api_key: str) -> str:
        """Clean API key from any JSON artifacts."""
        api_key = api_key.strip().strip('"').strip("'")
        if api_key.startswith('{') and api_key.endswith('}'):
            try:
                import json
                parsed = json.loads(api_key)
                if isinstance(parsed, dict):
                    for key in ["OPENAI_API_KEY", "openai_api_key", "api_key", "value"]:
                        if key in parsed:
                            api_key = parsed[key]
                            break
            except Exception as e:
                logger.error(f"Error extracting from JSON: {e}")
                pass
        api_key = api_key.strip().strip('"').strip("'")
        return api_key

    async def get_client(self, agent_id: Optional[str] = None) -> OpenAIClientWrapper:
        """Get OpenAI client for agent (cached per agent)."""
        cache_key = agent_id or "default"

        if cache_key not in self._clients:
            # Get API key from settings or Secrets Manager
            api_key = self.settings.openai_api_key
            if not api_key:
                try:
                    api_key = await self.secrets_manager.get_openai_api_key()
                except Exception as e:
                    logger.error(f"Failed to get API key from Secrets Manager: {e}")
                    raise RuntimeError(
                        "OpenAI API key not found in settings or Secrets Manager"
                    ) from e

            # Clean API key before creating client
            api_key = self._clean_api_key(api_key)
            self._clients[cache_key] = OpenAIClientWrapper(api_key, self.settings)

        return self._clients[cache_key]

    async def get_chat_model(self, agent_config: AgentConfig) -> BaseChatModel:
        """Get chat model (OpenAI or Google) for agent config."""
        openai_key = self.settings.openai_api_key
        if not openai_key:
            try:
                openai_key = await self.secrets_manager.get_openai_api_key()
            except Exception as e:
                logger.error(f"Failed to get OpenAI API key: {e}")
                raise RuntimeError("OpenAI API key not found") from e
        openai_key = self._clean_api_key(openai_key)

        google_key = _get_google_api_key_sync(self.settings)

        return create_chat_model(
            agent_config=agent_config,
            openai_api_key=openai_key,
            google_api_key=google_key,
        )

    async def get_embeddings(self, embeddings_config: EmbeddingsConfig) -> Embeddings:
        """Get embeddings model (OpenAI or Google), cached by (provider, model)."""
        cache_key = (embeddings_config.provider or "openai", embeddings_config.model or "text-embedding-3-small")
        if cache_key in self._embeddings_cache:
            return self._embeddings_cache[cache_key]

        openai_key = self.settings.openai_api_key
        if not openai_key:
            try:
                openai_key = await self.secrets_manager.get_openai_api_key()
            except Exception as e:
                logger.error(f"Failed to get OpenAI API key for embeddings: {e}")
                raise RuntimeError("OpenAI API key not found") from e
        openai_key = self._clean_api_key(openai_key)

        google_key = _get_google_api_key_sync(self.settings)

        embeddings = create_embeddings_model(
            embeddings_config=embeddings_config,
            openai_api_key=openai_key,
            google_api_key=google_key,
        )
        self._embeddings_cache[cache_key] = embeddings
        return embeddings

    def clear_cache(self, agent_id: Optional[str] = None) -> None:
        """Clear cached clients and embeddings."""
        if agent_id:
            self._clients.pop(agent_id, None)
        else:
            self._clients.clear()
            self._embeddings_cache.clear()


@lru_cache()
def get_llm_factory() -> LLMFactory:
    """Get cached LLM factory instance."""
    settings = get_settings()
    if settings.database_backend == "postgres":
        secrets_manager = get_postgres_secrets_manager()
    else:
        secrets_manager = get_secrets_manager()
    return LLMFactory(settings, secrets_manager)






