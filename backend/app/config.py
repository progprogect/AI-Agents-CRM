"""Application configuration."""

from functools import lru_cache
from typing import Annotated, Optional, Union

from pydantic import AliasChoices, BeforeValidator, Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_parse_none_str=True,  # Treat empty strings as None
        populate_by_name=True,  # Allow both field name and alias
    )

    # Application
    app_name: str = Field(default="Agent API", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    environment: str = Field(default="development", description="Environment")
    debug: bool = Field(default=False, description="Debug mode")

    # OpenAI
    openai_api_key: Optional[str] = Field(
        default=None, description="OpenAI API key (from Secrets Manager in prod)"
    )
    openai_model: str = Field(
        default="gpt-4o-mini", description="OpenAI model for chat"
    )
    openai_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    openai_max_tokens: int = Field(default=600, ge=1, le=4096)
    openai_timeout: int = Field(default=30, description="OpenAI API timeout in seconds")

    # OpenAI Embeddings
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", description="OpenAI embedding model"
    )
    openai_embedding_dimensions: int = Field(
        default=1536, description="Embedding dimensions"
    )

    # Google AI Studio (Gemini)
    google_ai_studio_api_key: Optional[str] = Field(
        default=None,
        description="Google AI Studio API key",
        validation_alias=AliasChoices("GOOGLE_AI_STUDIO_API", "Google_AI_Studio_API"),
    )

    # Database (PostgreSQL for Railway)
    database_url: Optional[str] = Field(
        default=None,
        description="PostgreSQL connection URL (DATABASE_URL or DATABASE_PUBLIC_URL)",
        alias="DATABASE_URL",
    )
    database_public_url: Optional[str] = Field(
        default=None,
        description="PostgreSQL public URL for migrations",
        alias="DATABASE_PUBLIC_URL",
    )
    database_backend: str = Field(
        default="postgres",
        description="Storage backend: postgres | dynamodb",
    )
    secret_encryption_key: Optional[str] = Field(
        default=None,
        description="Fernet key for encrypting channel/notification tokens (32 bytes base64)",
        alias="SECRET_ENCRYPTION_KEY",
    )

    def get_database_url(self) -> Optional[str]:
        """Get database URL (DATABASE_URL or DATABASE_PUBLIC_URL fallback)."""
        return self.database_url or self.database_public_url

    # AWS (optional, for dynamodb backend)
    aws_region: str = Field(default="us-east-1", description="AWS region")
    aws_access_key_id: Optional[str] = Field(default=None, description="AWS access key")
    aws_secret_access_key: Optional[str] = Field(
        default=None, description="AWS secret key"
    )

    # DynamoDB
    dynamodb_table_conversations: str = Field(
        default="doctor-agent-conversations", description="Conversations table name"
    )
    dynamodb_table_messages: str = Field(
        default="doctor-agent-messages", description="Messages table name"
    )
    dynamodb_table_agents: str = Field(
        default="doctor-agent-agents", description="Agents table name"
    )
    dynamodb_table_audit_logs: str = Field(
        default="doctor-agent-audit-logs", description="Audit logs table name"
    )
    dynamodb_table_channel_bindings: str = Field(
        default="doctor-agent-channel-bindings", description="Channel bindings table name"
    )
    dynamodb_table_instagram_profiles: str = Field(
        default="doctor-agent-instagram-profiles", description="Instagram user profiles table name"
    )
    dynamodb_table_notification_configs: str = Field(
        default="doctor-agent-notification-configs", description="Notification configs table name"
    )
    dynamodb_endpoint_url: Optional[str] = Field(
        default=None, description="DynamoDB endpoint URL (for local development)"
    )

    # OpenSearch
    opensearch_endpoint: Optional[str] = Field(
        default=None, description="OpenSearch endpoint URL"
    )
    opensearch_use_ssl: bool = Field(default=True, description="Use SSL for OpenSearch")
    opensearch_verify_certs: bool = Field(
        default=True, description="Verify SSL certificates"
    )
    opensearch_username: Optional[str] = Field(
        default=None, description="OpenSearch username"
    )
    opensearch_password: Optional[str] = Field(
        default=None, description="OpenSearch password"
    )

    # Redis
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    redis_ssl: bool = Field(default=False, description="Use SSL for Redis")

    # Secrets Manager
    secrets_manager_region: Optional[str] = Field(
        default=None, description="Secrets Manager region"
    )
    secrets_manager_openai_key_name: str = Field(
        default="doctor-agent/openai-api-key",
        description="OpenAI API key secret name",
    )

    # Message TTL
    message_ttl_hours: int = Field(
        default=48, description="Message TTL in hours"
    )

    # CORS
    # Use Optional[str] with explicit alias to prevent pydantic-settings from auto-parsing as JSON
    # Then convert to list[str] using computed_field to prevent pydantic-settings from trying to parse it
    cors_origins_env: Optional[str] = Field(
        default=None,
        description="CORS origins from environment (will be parsed to list)",
        alias="CORS_ORIGINS",  # Explicit alias to map CORS_ORIGINS env var to this field
    )
    
    @computed_field
    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS origins from environment string to list.
        
        This is a computed field, so pydantic-settings will not try to read it from environment.
        """
        import json
        
        v = self.cors_origins_env
        
        if v is None:
            return ["http://localhost:3000"]  # Default value
        
        # If it's a string, parse it
        if isinstance(v, str):
            # Handle empty string
            if not v.strip():
                return ["http://localhost:3000"]  # Default value
            
            # Try to parse as JSON first (in case it's a JSON string)
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except (json.JSONDecodeError, ValueError):
                pass
            
            # Split by comma and strip whitespace
            origins = [origin.strip() for origin in v.split(",") if origin.strip()]
            # Handle wildcard
            if "*" in origins:
                return ["*"]
            else:
                return origins if origins else ["http://localhost:3000"]  # Default value
        
        # Fallback to default
        return ["http://localhost:3000"]

    # WebSocket
    websocket_ping_interval: int = Field(
        default=25, description="WebSocket ping interval in seconds"
    )
    websocket_ping_timeout: int = Field(
        default=5, description="WebSocket ping timeout in seconds"
    )

    # Security
    admin_token: Optional[str] = Field(
        default=None, description="Admin authentication token"
    )
    rate_limit_per_minute: int = Field(
        default=60, description="Rate limit per minute per IP"
    )

    # Cloudinary (RAG file storage)
    cloudinary_cloud_name: Optional[str] = Field(
        default=None, description="Cloudinary cloud name", alias="CLOUDINARY_CLOUD_NAME"
    )
    cloudinary_api_key: Optional[str] = Field(
        default=None, description="Cloudinary API key", alias="CLOUDINARY_API_KEY"
    )
    cloudinary_api_secret: Optional[str] = Field(
        default=None, description="Cloudinary API secret", alias="CLOUDINARY_API_SECRET"
    )
    cloudinary_folder: str = Field(
        default="rag", description="Cloudinary base folder for RAG", alias="CLOUDINARY_FOLDER"
    )

    # Instagram
    instagram_webhook_verify_token: Optional[str] = Field(
        default=None, description="Token for Instagram webhook verification"
    )
    instagram_app_secret: Optional[str] = Field(
        default=None, description="Instagram app secret for webhook signature verification"
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

