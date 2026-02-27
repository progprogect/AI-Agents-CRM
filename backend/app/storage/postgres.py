"""PostgreSQL client - Railway-compatible storage layer."""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Optional

import asyncpg

from app.config import Settings, get_settings
from app.models.channel_binding import ChannelBinding, ChannelType
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.instagram_user_profile import InstagramUserProfile
from app.models.message import Message, MessageRole
from app.utils.datetime_utils import parse_utc_datetime, to_utc_iso_string, utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Get or create connection pool."""
    global _pool
    if _pool is None:
        settings = get_settings()
        url = settings.get_database_url()
        if not url:
            raise RuntimeError("DATABASE_URL or DATABASE_PUBLIC_URL must be set for PostgreSQL backend")
        _pool = await asyncpg.create_pool(url, min_size=1, max_size=10, command_timeout=60)
    return _pool


async def close_pool() -> None:
    """Close connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _parse_json(val: Any) -> Any:
    """Parse JSON from DB."""
    if val is None:
        return {}
    if isinstance(val, str):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return {}
    return val if isinstance(val, (dict, list)) else {}


def _row_to_conv(row: asyncpg.Record) -> dict:
    """Convert DB row to conversation dict."""
    d = dict(row)
    for k in ("created_at", "updated_at", "closed_at"):
        if d.get(k) and isinstance(d[k], datetime):
            d[k] = to_utc_iso_string(d[k])
    if "marketing_status" not in d or d["marketing_status"] is None:
        d["marketing_status"] = MarketingStatus.NEW.value
    return d


def _row_to_msg(row: asyncpg.Record) -> dict:
    """Convert DB row to message dict."""
    d = dict(row)
    # Keep datetime as-is for Message model; parse if string from JSON
    if "metadata" in d and isinstance(d["metadata"], str):
        d["metadata"] = _parse_json(d["metadata"])
    return d


def _row_to_binding(row: asyncpg.Record) -> dict:
    """Convert DB row to channel binding dict."""
    d = dict(row)
    for k in ("created_at", "updated_at"):
        if d.get(k) and isinstance(d[k], datetime):
            d[k] = to_utc_iso_string(d[k])
    if "metadata" in d and isinstance(d["metadata"], str):
        d["metadata"] = _parse_json(d["metadata"])
    if d.get("channel_username") == "":
        d["channel_username"] = None
    return d


def _row_to_notification_config(row: asyncpg.Record) -> dict:
    """Convert DB row to notification config dict."""
    d = dict(row)
    for k in ("created_at", "updated_at"):
        if d.get(k) and isinstance(d[k], datetime):
            d[k] = to_utc_iso_string(d[k])
    return d


class PostgreSQLClient:
    """PostgreSQL client with DynamoDBClient-compatible API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.message_ttl_seconds = settings.message_ttl_hours * 3600

    def _calculate_ttl(self, base_time: datetime) -> int:
        return int((base_time + timedelta(seconds=self.message_ttl_seconds)).timestamp())

    def _calculate_profile_ttl(self, base_time: datetime) -> int:
        return int((base_time + timedelta(days=5)).timestamp())

    # Conversation operations
    async def create_conversation(self, conversation: Conversation) -> Conversation:
        ttl = self._calculate_ttl(conversation.created_at)
        ms = get_enum_value(conversation.marketing_status) or MarketingStatus.NEW.value
        ch = get_enum_value(conversation.channel) or "web_chat"
        st = get_enum_value(conversation.status) or ConversationStatus.AI_ACTIVE.value

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO conversations (
                        conversation_id, agent_id, channel, external_conversation_id, external_user_id,
                        status, created_at, updated_at, closed_at, handoff_reason, request_type, ttl,
                        external_user_name, external_user_username, external_user_profile_pic,
                        marketing_status, rejection_reason
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                    ON CONFLICT (conversation_id) DO UPDATE SET
                        updated_at = EXCLUDED.updated_at
                    """,
                    conversation.conversation_id,
                    conversation.agent_id,
                    ch,
                    conversation.external_conversation_id,
                    conversation.external_user_id,
                    st,
                    conversation.created_at,
                    conversation.updated_at,
                    conversation.closed_at,
                    conversation.handoff_reason,
                    conversation.request_type,
                    ttl,
                    conversation.external_user_name,
                    conversation.external_user_username,
                    conversation.external_user_profile_pic,
                    ms,
                    conversation.rejection_reason,
                )
        return conversation

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM conversations WHERE conversation_id = $1",
                conversation_id,
            )
        if not row:
            return None
        return Conversation(**_row_to_conv(row))

    async def update_conversation(
        self,
        conversation_id: str,
        status: Optional[ConversationStatus] = None,
        handoff_reason: Optional[str] = None,
        request_type: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[Conversation]:
        old = await self.get_conversation(conversation_id)
        old_status = get_enum_value(old.status) if old else None

        updates = []
        params = []
        i = 1
        if status:
            updates.append(f"status = ${i}")
            params.append(status.value)
            i += 1
        if handoff_reason is not None:
            updates.append(f"handoff_reason = ${i}")
            params.append(handoff_reason)
            i += 1
        if request_type is not None:
            updates.append(f"request_type = ${i}")
            params.append(request_type)
            i += 1
        for k, v in kwargs.items():
            updates.append(f'"{k}" = ${i}')
            params.append(v)
            i += 1
        if not updates:
            return await self.get_conversation(conversation_id)

        updates.append(f"updated_at = ${i}")
        params.append(utc_now())
        i += 1
        params.append(conversation_id)

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE conversations SET {', '.join(updates)} WHERE conversation_id = ${i}",
                *params,
            )

        updated = await self.get_conversation(conversation_id)
        if updated:
            try:
                from app.api.admin_websocket import get_admin_broadcast_manager
                from app.models.conversation import ConversationStatus

                broadcast_manager = get_admin_broadcast_manager()
                if (
                    status
                    and status == ConversationStatus.NEEDS_HUMAN
                    and (old_status is None or old_status != ConversationStatus.NEEDS_HUMAN.value)
                ):
                    await broadcast_manager.broadcast_new_escalation(
                        updated, handoff_reason
                    )
                    try:
                        from app.services.notification_service import NotificationService
                        from app.services.telegram_service import TelegramService
                        from app.storage.postgres_secrets import get_postgres_secrets_manager
                        from app.config import get_settings
                        from app.services.channel_binding_service import ChannelBindingService

                        secrets_manager = get_postgres_secrets_manager()
                        settings = get_settings()
                        channel_binding_service = ChannelBindingService(self, secrets_manager)
                        telegram_service = TelegramService(
                            channel_binding_service=channel_binding_service,
                            dynamodb=self,
                            settings=settings,
                        )
                        notification_service = NotificationService(
                            dynamodb=self,
                            secrets_manager=secrets_manager,
                            telegram_service=telegram_service,
                        )
                        agent_data = await self.get_agent(updated.agent_id)
                        agent_display_name = "Unknown Agent"
                        if agent_data and "config" in agent_data:
                            from app.models.agent_config import AgentConfig
                            agent_config = AgentConfig.from_dict(agent_data["config"])
                            agent_display_name = agent_config.profile.agent_display_name
                        asyncio.create_task(
                            notification_service.send_escalation_notification(
                                conversation=updated,
                                escalation_reason=handoff_reason or "Escalation required",
                                agent_display_name=agent_display_name,
                            )
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send escalation notifications: {e}", exc_info=True)
                else:
                    await broadcast_manager.broadcast_conversation_update(updated)
            except Exception as e:
                logger.warning(f"Failed to broadcast: {e}", exc_info=True)
        return updated

    async def list_conversations(
        self,
        agent_id: Optional[str] = None,
        status: Optional[ConversationStatus] = None,
        marketing_status: Optional[str] = None,
        limit: int = 100,
    ) -> list[Conversation]:
        where = []
        params = []
        i = 1
        if agent_id:
            where.append(f"agent_id = ${i}")
            params.append(agent_id)
            i += 1
        if status:
            where.append(f"status = ${i}")
            params.append(status.value)
            i += 1
        if marketing_status:
            where.append(f"marketing_status = ${i}")
            params.append(marketing_status)
            i += 1
        params.append(limit)
        clause = " AND ".join(where) if where else "TRUE"
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM conversations WHERE {clause} ORDER BY created_at DESC LIMIT ${i}",
                *params,
            )
        return [Conversation(**_row_to_conv(r)) for r in rows]

    # Message operations
    async def create_message(self, message: Message) -> Message:
        ttl = self._calculate_ttl(message.timestamp)
        ch = get_enum_value(message.channel) or "web_chat"
        role = get_enum_value(message.role)
        meta = json.dumps(message.metadata) if message.metadata else "{}"

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO messages (
                    conversation_id, message_id, agent_id, role, content, channel,
                    external_message_id, external_user_id, timestamp, metadata, ttl
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                message.conversation_id,
                message.message_id,
                message.agent_id,
                role,
                message.content,
                ch,
                message.external_message_id,
                message.external_user_id,
                message.timestamp,
                meta,
                ttl,
            )
        return message

    async def get_message(self, conversation_id: str, message_id: str) -> Optional[Message]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM messages WHERE conversation_id = $1 AND message_id = $2",
                conversation_id,
                message_id,
            )
        if not row:
            return None
        return Message(**_row_to_msg(row))

    async def list_messages(
        self,
        conversation_id: str,
        limit: int = 100,
        reverse: bool = True,
    ) -> list[Message]:
        pool = await get_pool()
        order = "DESC" if reverse else "ASC"
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM messages WHERE conversation_id = $1 ORDER BY timestamp {order} LIMIT $2",
                conversation_id,
                limit,
            )
        items = [Message(**_row_to_msg(r)) for r in rows]
        def _ts(m: Message):
            t = m.timestamp
            if isinstance(t, datetime):
                return t
            if isinstance(t, str):
                try:
                    return parse_utc_datetime(t)
                except (ValueError, AttributeError):
                    return utc_now()
            return utc_now()
        items.sort(key=_ts)
        if reverse:
            items.reverse()
        return items

    # Agent operations
    async def create_agent(self, agent_id: str, config: dict[str, Any]) -> dict[str, Any]:
        config_json = json.dumps(config)
        now = utc_now()
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agents (agent_id, config, is_active, created_at, updated_at)
                VALUES ($1, $2::jsonb, TRUE, $3, $4)
                ON CONFLICT (agent_id) DO UPDATE SET
                    config = EXCLUDED.config, updated_at = EXCLUDED.updated_at
                """,
                agent_id,
                config_json,
                now,
                now,
            )
        return {
            "agent_id": agent_id,
            "config": config,
            "created_at": to_utc_iso_string(now),
            "updated_at": to_utc_iso_string(now),
            "is_active": True,
        }

    async def get_agent(self, agent_id: str) -> Optional[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM agents WHERE agent_id = $1", agent_id)
        if not row:
            return None
        d = dict(row)
        if "config" in d:
            cfg = d["config"]
            d["config"] = cfg if isinstance(cfg, dict) else json.loads(cfg) if cfg else {}
        for k in ("created_at", "updated_at"):
            if d.get(k) and isinstance(d[k], datetime):
                d[k] = to_utc_iso_string(d[k])
        return d

    async def update_agent_status(
        self, agent_id: str, is_active: bool
    ) -> Optional[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE agents SET is_active = $1, updated_at = $2 WHERE agent_id = $3",
                is_active,
                utc_now(),
                agent_id,
            )
        return await self.get_agent(agent_id)

    async def list_agents(self, active_only: bool = True) -> list[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if active_only:
                rows = await conn.fetch("SELECT * FROM agents WHERE is_active = TRUE")
            else:
                rows = await conn.fetch("SELECT * FROM agents")
        result = []
        for r in rows:
            d = dict(r)
            cfg = d.get("config")
            d["config"] = cfg if isinstance(cfg, dict) else json.loads(cfg) if cfg else {}
            for k in ("created_at", "updated_at"):
                if d.get(k) and isinstance(d[k], datetime):
                    d[k] = to_utc_iso_string(d[k])
            result.append(d)
        return result

    # Channel binding operations
    async def create_channel_binding(self, binding: ChannelBinding) -> ChannelBinding:
        ch = get_enum_value(binding.channel_type)
        meta = json.dumps(binding.metadata) if binding.metadata else "{}"
        enc_token = binding.encrypted_access_token

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO channel_bindings (
                    binding_id, agent_id, channel_type, channel_account_id, channel_username,
                    secret_name, encrypted_access_token, is_active, is_verified,
                    created_at, updated_at, created_by, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb)
                """,
                binding.binding_id,
                binding.agent_id,
                ch,
                binding.channel_account_id,
                binding.channel_username,
                binding.secret_name,
                enc_token,
                binding.is_active,
                binding.is_verified,
                binding.created_at,
                binding.updated_at,
                binding.created_by,
                meta,
            )
        return binding

    async def get_channel_binding(self, binding_id: str) -> Optional[ChannelBinding]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM channel_bindings WHERE binding_id = $1",
                binding_id,
            )
        if not row:
            return None
        d = _row_to_binding(row)
        d.pop("encrypted_access_token", None)
        return ChannelBinding(**d)

    async def get_channel_bindings_by_agent(
        self,
        agent_id: str,
        channel_type: Optional[str] = None,
        active_only: bool = True,
    ) -> list[ChannelBinding]:
        where = ["agent_id = $1"]
        params = [agent_id]
        if channel_type:
            where.append("channel_type = $2")
            params.append(channel_type)
        if active_only:
            where.append("is_active = TRUE")
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM channel_bindings WHERE {' AND '.join(where)}",
                *params,
            )
        result = []
        for r in rows:
            d = _row_to_binding(r)
            d.pop("encrypted_access_token", None)
            try:
                result.append(ChannelBinding(**d))
            except Exception as e:
                logger.error(f"Failed to create ChannelBinding: {e}", exc_info=True)
        return result

    async def get_channel_binding_by_account_id(
        self, channel_type: str, account_id: str
    ) -> Optional[ChannelBinding]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM channel_bindings WHERE channel_type = $1 AND channel_account_id = $2",
                channel_type,
                account_id,
            )
        if not rows:
            return None
        active = [r for r in rows if r.get("is_active", True)]
        r = active[0] if active else rows[0]
        d = _row_to_binding(r)
        d.pop("encrypted_access_token", None)
        return ChannelBinding(**d)

    async def update_channel_binding(
        self, binding_id: str, **kwargs: Any
    ) -> Optional[ChannelBinding]:
        if not kwargs:
            return await self.get_channel_binding(binding_id)
        kwargs["updated_at"] = utc_now()
        sets = []
        params = []
        for i, (k, v) in enumerate(kwargs.items(), 1):
            if k == "channel_type":
                v = get_enum_value(v)
            sets.append(f'"{k}" = ${i}')
            params.append(v)
        params.append(binding_id)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE channel_bindings SET {', '.join(sets)} WHERE binding_id = ${len(params)}",
                *params,
            )
        return await self.get_channel_binding(binding_id)

    async def delete_channel_binding(self, binding_id: str) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM channel_bindings WHERE binding_id = $1", binding_id)

    # Notification config operations
    async def create_notification_config(
        self, config: "NotificationConfig"
    ) -> "NotificationConfig":
        from app.models.notification_config import NotificationConfig

        nt = get_enum_value(config.notification_type)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO notification_configs (
                    config_id, notification_type, bot_token_secret_name, encrypted_bot_token,
                    chat_id, is_active, description, created_at, updated_at, created_by
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                config.config_id,
                nt,
                config.bot_token_secret_name,
                config.encrypted_bot_token,
                config.chat_id,
                config.is_active,
                config.description,
                config.created_at,
                config.updated_at,
                config.created_by,
            )
        return config

    async def get_notification_config(
        self, config_id: str
    ) -> Optional["NotificationConfig"]:
        from app.models.notification_config import NotificationConfig

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM notification_configs WHERE config_id = $1",
                config_id,
            )
        if not row:
            return None
        return NotificationConfig(**_row_to_notification_config(row))

    async def list_notification_configs(
        self, active_only: bool = False
    ) -> list["NotificationConfig"]:
        from app.models.notification_config import NotificationConfig

        pool = await get_pool()
        async with pool.acquire() as conn:
            if active_only:
                rows = await conn.fetch("SELECT * FROM notification_configs WHERE is_active = TRUE")
            else:
                rows = await conn.fetch("SELECT * FROM notification_configs")
        return [NotificationConfig(**_row_to_notification_config(r)) for r in rows]

    async def update_notification_config(
        self, config_id: str, **kwargs: Any
    ) -> Optional["NotificationConfig"]:
        from app.models.notification_config import NotificationConfig

        if not kwargs:
            return await self.get_notification_config(config_id)
        kwargs["updated_at"] = utc_now()
        sets = []
        params = []
        for i, (k, v) in enumerate(kwargs.items(), 1):
            if k == "notification_type":
                v = get_enum_value(v)
            sets.append(f'"{k}" = ${i}')
            params.append(v)
        params.append(config_id)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE notification_configs SET {', '.join(sets)} WHERE config_id = ${len(params)}",
                *params,
            )
        return await self.get_notification_config(config_id)

    async def delete_notification_config(self, config_id: str) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM notification_configs WHERE config_id = $1",
                config_id,
            )

    # Audit log operations
    async def create_audit_log(
        self,
        admin_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        log_id = f"{resource_type}_{resource_id}_{int(time.time())}"
        meta = json.dumps(metadata or {})
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_logs (log_id, admin_id, action, resource_type, resource_id, timestamp, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                log_id,
                admin_id,
                action,
                resource_type,
                resource_id,
                utc_now(),
                meta,
            )
        return {
            "log_id": log_id,
            "admin_id": admin_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "timestamp": to_utc_iso_string(utc_now()),
            "metadata": metadata or {},
        }

    async def list_audit_logs(
        self,
        admin_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        sort_desc: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        where = []
        params = []
        i = 1
        if admin_id:
            where.append(f"admin_id = ${i}")
            params.append(admin_id)
            i += 1
        if resource_type:
            where.append(f"resource_type = ${i}")
            params.append(resource_type)
            i += 1
        if action:
            where.append(f"action = ${i}")
            params.append(action)
            i += 1
        params.append(limit * 2)
        clause = " AND ".join(where) if where else "TRUE"
        order = "DESC" if sort_desc else "ASC"
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM audit_logs WHERE {clause} ORDER BY timestamp {order} LIMIT ${i}",
                *params,
            )
        items = []
        for r in rows:
            d = dict(r)
            if "metadata" in d and isinstance(d["metadata"], str):
                d["metadata"] = _parse_json(d["metadata"])
            if "timestamp" in d and isinstance(d["timestamp"], datetime):
                d["timestamp"] = to_utc_iso_string(d["timestamp"])
            items.append(d)
        if start_date or end_date:
            from datetime import timezone
            tz = timezone.utc
            filtered = []
            for it in items:
                ts = parse_utc_datetime(it.get("timestamp", "")) if isinstance(it.get("timestamp"), str) else it.get("timestamp")
                if ts and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=tz)
                if start_date and ts and ts < (start_date.replace(tzinfo=tz) if start_date.tzinfo is None else start_date):
                    continue
                if end_date and ts and ts > (end_date.replace(tzinfo=tz) if end_date.tzinfo is None else end_date):
                    continue
                filtered.append(it)
            items = filtered
        return items[:limit]

    # Instagram profile operations
    async def create_or_update_instagram_profile(
        self, profile: InstagramUserProfile
    ) -> InstagramUserProfile:
        ttl = self._calculate_profile_ttl(profile.updated_at)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO instagram_profiles (external_user_id, name, username, profile_pic, updated_at, ttl)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (external_user_id) DO UPDATE SET
                    name = EXCLUDED.name, username = EXCLUDED.username, profile_pic = EXCLUDED.profile_pic,
                    updated_at = EXCLUDED.updated_at, ttl = EXCLUDED.ttl
                """,
                profile.external_user_id,
                profile.name,
                profile.username,
                profile.profile_pic,
                profile.updated_at,
                ttl,
            )
        return profile

    async def get_instagram_profile(self, external_user_id: str) -> Optional[InstagramUserProfile]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM instagram_profiles WHERE external_user_id = $1",
                external_user_id,
            )
        if not row:
            return None
        d = dict(row)
        if d.get("updated_at") and isinstance(d["updated_at"], datetime):
            d["updated_at"] = to_utc_iso_string(d["updated_at"])
        return InstagramUserProfile(**d)


@lru_cache()
def get_postgres_client() -> PostgreSQLClient:
    settings = get_settings()
    return PostgreSQLClient(settings)
