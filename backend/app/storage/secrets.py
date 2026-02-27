"""AWS Secrets Manager client."""

import json
import logging
from datetime import datetime
from functools import lru_cache
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class SecretsManager:
    """AWS Secrets Manager client wrapper."""

    def __init__(self, settings: Settings):
        """Initialize Secrets Manager client."""
        self.settings = settings
        self.client = boto3.client(
            "secretsmanager",
            region_name=settings.secrets_manager_region or settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        self._cache: dict[str, str] = {}

    async def get_secret(
        self, 
        secret_name: str, 
        use_cache: bool = True,
        json_key: Optional[str] = None
    ) -> str:
        """Get secret value from Secrets Manager.
        
        Args:
            secret_name: Name of the secret in AWS Secrets Manager
            use_cache: Whether to use cached value if available
            json_key: If secret is JSON, extract value by this key. 
                     If None, uses auto-detection for common keys.
        
        Returns:
            Secret value as string. If JSON and json_key is provided, returns value at that key.
        """
        # Build cache key that includes json_key to avoid conflicts
        cache_key = f"{secret_name}:{json_key}" if json_key else secret_name
        
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            secret_value = response["SecretString"]

            # Try to parse as JSON
            try:
                secret_data = json.loads(secret_value)
                if isinstance(secret_data, dict):
                    # If json_key is specified, extract value by that key
                    if json_key:
                        if json_key not in secret_data:
                            raise ValueError(
                                f"Key '{json_key}' not found in secret {secret_name}. "
                                f"Available keys: {list(secret_data.keys())}"
                            )
                        extracted_value = secret_data[json_key]
                        if not isinstance(extracted_value, str):
                            raise ValueError(
                                f"Value at key '{json_key}' in secret {secret_name} is not a string. "
                                f"Got: {type(extracted_value).__name__}"
                            )
                        secret_value = extracted_value
                    else:
                        # Auto-detect: try common keys for API keys
                        for key in ["api_key", "OPENAI_API_KEY", "openai_api_key", "value", "access_token"]:
                            if key in secret_data:
                                extracted_value = secret_data[key]
                                # Ensure extracted value is a string
                                if isinstance(extracted_value, str):
                                    secret_value = extracted_value
                                    break
                                elif isinstance(extracted_value, dict):
                                    # If it's still a dict, try to find string value
                                    for v in extracted_value.values():
                                        if isinstance(v, str):
                                            secret_value = v
                                            break
                                    break
            except json.JSONDecodeError:
                # Not JSON, use as-is
                pass

            # Clean up whitespace
            secret_value = secret_value.strip().strip('"').strip("'")
            
            # Validate that we extracted a string value (not JSON)
            if secret_value.startswith('{') and secret_value.endswith('}'):
                # Last attempt: try to extract any string value from the JSON
                try:
                    parsed = json.loads(secret_value)
                    if isinstance(parsed, dict):
                        # Get the first string value we find
                        for v in parsed.values():
                            if isinstance(v, str):
                                secret_value = v.strip()
                                break
                        # If still JSON, raise error
                        if secret_value.startswith('{'):
                            raise ValueError(
                                f"Failed to extract string value from JSON secret {secret_name}. "
                                f"Expected plain value or JSON with extractable string value. "
                                f"Use json_key parameter to specify which key to extract."
                            )
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"Error extracting from JSON: {e}")
                    raise ValueError(
                        f"Secret {secret_name} appears to be malformed JSON. "
                        f"Expected plain value or JSON with extractable string value. "
                        f"Use json_key parameter to specify which key to extract."
                    ) from e

            # Final cleanup
            secret_value = secret_value.strip().strip('"').strip("'")

            # Cache the extracted value
            if use_cache:
                self._cache[cache_key] = secret_value

            return secret_value

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                raise ValueError(f"Secret {secret_name} not found") from e
            raise RuntimeError(f"Failed to retrieve secret {secret_name}: {e}") from e

    async def get_openai_api_key(self) -> str:
        """Get OpenAI API key from Secrets Manager."""
        # Clear cache to ensure fresh retrieval
        self.clear_cache(self.settings.secrets_manager_openai_key_name)
        
        # Get secret - get_secret() already handles JSON extraction
        api_key = await self.get_secret(self.settings.secrets_manager_openai_key_name)
        
        # Final cleanup
        api_key = api_key.strip().strip('"').strip("'")
        
        # Validate that it looks like an API key (starts with sk-)
        if not api_key.startswith('sk-'):
            logger.error(f"Invalid API key format! First 50 chars: {repr(api_key[:50])}")
            raise ValueError(
                f"Invalid API key format: key does not start with 'sk-'. "
                f"Got: {api_key[:50]}..." if len(api_key) > 50 else f"Got: {api_key}"
            )
        
        return api_key

    def clear_cache(self, secret_name: Optional[str] = None, json_key: Optional[str] = None) -> None:
        """Clear cached secrets.
        
        Args:
            secret_name: If provided, clear cache for this secret only.
                        If None, clear all cache.
            json_key: If provided with secret_name, clear cache for specific json_key.
                     If None with secret_name, clear all cache entries for that secret.
        """
        if secret_name:
            if json_key:
                # Clear specific cache entry
                cache_key = f"{secret_name}:{json_key}"
                self._cache.pop(cache_key, None)
            else:
                # Clear all cache entries for this secret (with or without json_key)
                keys_to_remove = [
                    key for key in self._cache.keys()
                    if key == secret_name or key.startswith(f"{secret_name}:")
                ]
                for key in keys_to_remove:
                    self._cache.pop(key, None)
        else:
            # Clear all cache
            self._cache.clear()

    async def create_channel_token_secret(
        self,
        binding_id: str,
        channel_type: str,
        access_token: str,
        metadata: dict,
    ) -> str:
        """Create secret for channel access token."""
        secret_name = f"doctor-agent/channels/{channel_type}/{binding_id}/access-token"
        secret_value = json.dumps(
            {
                "access_token": access_token,
                **metadata,
            }
        )

        try:
            self.client.create_secret(
                Name=secret_name,
                SecretString=secret_value,
                Description=f"Access token for {channel_type} channel binding {binding_id}",
            )
            # Clear cache for this secret (in case it was cached before)
            self.clear_cache(secret_name)
            logger.info(f"Created channel token secret: {secret_name}")
            return secret_name
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceExistsException":
                # Secret already exists, update it instead
                logger.warning(f"Secret {secret_name} already exists, updating...")
                self.client.update_secret(
                    SecretId=secret_name,
                    SecretString=secret_value,
                )
                # Clear cache for this secret after update
                self.clear_cache(secret_name)
                return secret_name
            raise RuntimeError(f"Failed to create channel token secret: {e}") from e

    async def get_channel_token(self, secret_name: str) -> str:
        """Get channel access token from secret.
        
        Channel tokens are stored as JSON: {"access_token": "...", **metadata}
        This method uses get_secret() with json_key="access_token" for consistency.
        """
        try:
            # Use get_secret with json_key parameter for consistent JSON extraction
            return await self.get_secret(secret_name, use_cache=False, json_key="access_token")
        except ValueError as e:
            logger.error(f"Failed to get channel token from {secret_name}: {e}")
            raise
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                raise ValueError(f"Secret {secret_name} not found") from e
            raise RuntimeError(f"Failed to retrieve channel token from {secret_name}: {e}") from e

    async def create_notification_token_secret(
        self,
        config_id: str,
        bot_token: str,
    ) -> str:
        """Create secret for notification bot token."""
        secret_name = f"doctor-agent/notifications/{config_id}/bot-token"
        secret_value = json.dumps(
            {
                "bot_token": bot_token,
                "created_at": datetime.now().isoformat(),
            }
        )

        try:
            self.client.create_secret(
                Name=secret_name,
                SecretString=secret_value,
                Description=f"Bot token for notification config {config_id}",
            )
            # Clear cache for this secret (in case it was cached before)
            self.clear_cache(secret_name)
            logger.info(f"Created notification token secret: {secret_name}")
            return secret_name
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceExistsException":
                # Secret already exists, update it instead
                logger.warning(
                    f"Secret {secret_name} already exists, updating..."
                )
                self.client.update_secret(
                    SecretId=secret_name,
                    SecretString=secret_value,
                )
                # Clear cache for this secret after update
                self.clear_cache(secret_name)
                return secret_name
            raise RuntimeError(
                f"Failed to create notification token secret: {e}"
            ) from e

    async def get_notification_bot_token(self, secret_name: str) -> str:
        """Get notification bot token from secret.

        Notification tokens are stored as JSON: {"bot_token": "...", "created_at": "..."}
        This method uses get_secret() with json_key="bot_token" for consistency.
        """
        try:
            # Use get_secret with json_key parameter for consistent JSON extraction
            return await self.get_secret(
                secret_name, use_cache=False, json_key="bot_token"
            )
        except ValueError as e:
            logger.error(
                f"Failed to get notification bot token from {secret_name}: {e}"
            )
            raise
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                raise ValueError(f"Secret {secret_name} not found") from e
            raise RuntimeError(
                f"Failed to retrieve notification bot token from {secret_name}: {e}"
            ) from e

    async def update_notification_token_secret(
        self,
        secret_name: str,
        bot_token: str,
        created_at: Optional[str] = None,
    ) -> None:
        """Update notification bot token in secret."""
        secret_value = json.dumps(
            {
                "bot_token": bot_token,
                **({"created_at": created_at} if created_at else {}),
            }
        )
        try:
            self.client.update_secret(
                SecretId=secret_name,
                SecretString=secret_value,
            )
            # Clear cache for this secret
            self.clear_cache(secret_name)
            logger.info(f"Updated notification token secret: {secret_name}")
        except ClientError as e:
            raise RuntimeError(f"Failed to update notification token secret: {e}") from e

    async def update_channel_token(
        self,
        secret_name: str,
        access_token: str,
        metadata: dict,
    ) -> None:
        """Update channel token in secret."""
        secret_value = json.dumps(
            {
                "access_token": access_token,
                **metadata,
            }
        )
        try:
            self.client.update_secret(
                SecretId=secret_name,
                SecretString=secret_value,
            )
            # Clear cache for this secret
            self.clear_cache(secret_name)
            logger.info(f"Updated channel token secret: {secret_name}")
        except ClientError as e:
            raise RuntimeError(f"Failed to update channel token secret: {e}") from e

    async def delete_channel_token_secret(self, secret_name: str) -> None:
        """Delete channel token secret."""
        try:
            self.client.delete_secret(
                SecretId=secret_name,
                ForceDeleteWithoutRecovery=True,
            )
            # Clear cache for this secret
            self.clear_cache(secret_name)
            logger.info(f"Deleted channel token secret: {secret_name}")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                # Secret doesn't exist, that's fine
                logger.warning(f"Secret {secret_name} not found, skipping deletion")
                return
            raise RuntimeError(f"Failed to delete channel token secret: {e}") from e

    async def delete_notification_token_secret(self, secret_name: str) -> None:
        """Delete notification bot token secret."""
        try:
            self.client.delete_secret(
                SecretId=secret_name,
                ForceDeleteWithoutRecovery=True,
            )
            self.clear_cache(secret_name)
            logger.info(f"Deleted notification token secret: {secret_name}")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                logger.warning(f"Secret {secret_name} not found, skipping deletion")
                return
            raise RuntimeError(f"Failed to delete notification token secret: {e}") from e


@lru_cache()
def get_secrets_manager() -> SecretsManager:
    """Get cached Secrets Manager instance."""
    settings = get_settings()
    return SecretsManager(settings)




