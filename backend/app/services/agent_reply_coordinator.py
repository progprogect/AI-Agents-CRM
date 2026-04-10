"""Debounced agent replies: Redis-backed version + due queue + multi-worker safety."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal

from app.config import get_settings
from app.models.conversation import ConversationStatus
from app.models.message import MessageChannel
from app.services.agent_service import create_agent_service
from app.services.conversation_service import build_conversation_history_for_agent
from app.storage.redis import get_redis_client
from app.utils.datetime_utils import to_utc_iso_string, utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

KEY_VER_PREFIX = "agent_reply:ver:"
KEY_LAST_INPUT_PREFIX = "agent_reply:last_input:"
KEY_LAST_PLAIN_PREFIX = "agent_reply:last_plain:"
KEY_DUE = "agent_reply:due"
KEY_LOCK_PREFIX = "agent_reply:lock:"
KEY_TIMER_DUE = "agent_reply:timer_due"
KEY_TIMER_LOCK_PREFIX = "agent_reply:timer_lock:"
LOCK_TTL_SECONDS = 120


def _last_input_ttl_seconds(debounce_seconds: int) -> int:
    return max(300, debounce_seconds * 3)


NotifyResult = Literal["disabled", "scheduled", "fallback"]


async def notify_user_message_saved(
    conversation_id: str,
    *,
    agent_user_message: str,
    last_user_plain_content: str,
) -> NotifyResult:
    """
    Bump reply version, store last user texts for the worker, schedule fire in due ZSET.

    Returns:
        disabled — debounce is 0; caller runs the synchronous agent path.
        scheduled — Redis updated; poll loop will run the agent.
        fallback — Redis unavailable; caller should run process_message immediately.
    """
    settings = get_settings()
    debounce = settings.agent_reply_debounce_seconds
    if debounce <= 0:
        return "disabled"

    redis = get_redis_client()
    if not await redis.ping():
        logger.warning(
            "Redis unavailable for agent reply debounce; falling back to immediate reply",
            extra={"conversation_id": conversation_id},
        )
        return "fallback"

    ttl = _last_input_ttl_seconds(debounce)
    ver_key = f"{KEY_VER_PREFIX}{conversation_id}"
    fire_at_ms = int(time.time() * 1000) + debounce * 1000

    try:
        await redis.incr(ver_key)
        await redis.set(f"{KEY_LAST_INPUT_PREFIX}{conversation_id}", agent_user_message, ttl=ttl)
        await redis.set(
            f"{KEY_LAST_PLAIN_PREFIX}{conversation_id}",
            last_user_plain_content,
            ttl=ttl,
        )
        await redis.zadd(KEY_DUE, {conversation_id: float(fire_at_ms)})
        # Cancel any pending workflow timer — user has responded, inactivity timer no longer relevant.
        await redis.zrem(KEY_TIMER_DUE, conversation_id)
        await redis.delete(f"agent_reply:timer_payload:{conversation_id}")
    except Exception as exc:
        logger.warning(
            "Redis error scheduling debounced reply: %s; falling back to immediate reply",
            exc,
            extra={"conversation_id": conversation_id},
            exc_info=True,
        )
        return "fallback"

    return "scheduled"


async def cancel_timer_trigger(conversation_id: str) -> None:
    """Cancel any pending workflow timer for *conversation_id* (user replied before timer fired)."""
    redis = get_redis_client()
    try:
        if not await redis.ping():
            return
        await redis.zrem(KEY_TIMER_DUE, conversation_id)
        await redis.delete(f"agent_reply:timer_payload:{conversation_id}")
    except Exception as exc:
        logger.debug("cancel_timer_trigger error for %s: %s", conversation_id, exc)


async def _current_reply_version(redis, conversation_id: str) -> int:
    v = await redis.get(f"{KEY_VER_PREFIX}{conversation_id}")
    try:
        return int(v or 0)
    except ValueError:
        return 0


async def execute_agent_reply(conversation_id: str, expected_version: int) -> None:
    """Load context and run the agent once; skip if conversation state or version is stale."""
    from app.dependencies import get_dynamodb

    dynamodb = get_dynamodb()
    settings = get_settings()
    redis = get_redis_client()

    conversation = await dynamodb.get_conversation(conversation_id)
    if not conversation:
        logger.debug("execute_agent_reply: conversation missing %s", conversation_id)
        return

    status_value = get_enum_value(conversation.status)
    if status_value == ConversationStatus.CLOSED.value:
        return
    if status_value in (
        ConversationStatus.NEEDS_HUMAN.value,
        ConversationStatus.HUMAN_ACTIVE.value,
    ):
        return

    if await _current_reply_version(redis, conversation_id) != expected_version:
        return

    agent_input = await redis.get(f"{KEY_LAST_INPUT_PREFIX}{conversation_id}")
    plain = await redis.get(f"{KEY_LAST_PLAIN_PREFIX}{conversation_id}")
    if not agent_input:
        agent_input = plain or ""
    if not plain:
        plain = agent_input

    if not agent_input.strip() and not plain.strip():
        msgs = await dynamodb.list_messages(conversation_id, limit=50, reverse=True)
        for m in msgs:
            if get_enum_value(m.role) == "user":
                plain = m.content
                agent_input = m.content
                break

    if not agent_input.strip():
        logger.warning(
            "execute_agent_reply: empty user message for %s",
            conversation_id,
        )
        return

    last_plain_for_history = plain.strip() if plain else agent_input.strip()
    conversation_history = await build_conversation_history_for_agent(
        dynamodb,
        conversation_id,
        last_plain_for_history,
        agent_context_reset_at=conversation.agent_context_reset_at,
    )

    agent_data = await dynamodb.get_agent(conversation.agent_id)
    if not agent_data or "config" not in agent_data:
        logger.error("execute_agent_reply: agent %s missing", conversation.agent_id)
        return

    from app.models.agent_config import AgentConfig
    from app.services.channel_binding_service import ChannelBindingService
    from app.services.channel_sender import get_channel_sender
    from app.services.instagram_service import InstagramService
    from app.services.telegram_service import TelegramService
    from app.storage.resolver import get_secrets_manager

    agent_config = AgentConfig.from_dict(agent_data["config"])
    conversation_channel = get_enum_value(conversation.channel)

    instagram_service = None
    telegram_service = None
    if conversation_channel != MessageChannel.WEB_CHAT.value:
        secrets_manager = get_secrets_manager()
        binding_service = ChannelBindingService(dynamodb, secrets_manager)
        if conversation_channel == MessageChannel.INSTAGRAM.value:
            instagram_service = InstagramService(binding_service, dynamodb, settings)
        elif conversation_channel == MessageChannel.TELEGRAM.value:
            telegram_service = TelegramService(binding_service, dynamodb, settings)

    channel_enum = (
        MessageChannel(conversation_channel)
        if isinstance(conversation_channel, str)
        else conversation.channel
    )
    channel_sender = get_channel_sender(
        channel_enum, dynamodb, instagram_service, telegram_service
    )

    async def is_reply_stale() -> bool:
        cur = await _current_reply_version(redis, conversation_id)
        return cur != expected_version

    agent_service = create_agent_service(agent_config, dynamodb, channel_sender)
    try:
        result = await agent_service.process_message(
            user_message=agent_input,
            conversation_id=conversation_id,
            conversation_history=conversation_history,
            is_reply_stale=is_reply_stale,
        )
    except Exception as exc:
        logger.error(
            "execute_agent_reply failed for %s: %s",
            conversation_id,
            exc,
            exc_info=True,
        )
        return

    if result.get("aborted"):
        return

    if get_enum_value(conversation.channel) == MessageChannel.WEB_CHAT.value:
        from app.api.websocket import connection_manager

        if result.get("escalate"):
            await connection_manager.send_message(
                conversation_id,
                {
                    "type": "handoff",
                    "conversation_id": conversation_id,
                    "reason": result.get("escalation_reason", "Escalation required"),
                    "status": ConversationStatus.NEEDS_HUMAN.value,
                    "timestamp": None,
                },
            )
            return

        agent_response = result.get("response")
        agent_message_id = result.get("agent_message_id")
        agent_message_timestamp = result.get("agent_message_timestamp")
        if agent_response and agent_message_id:
            timestamp = agent_message_timestamp or to_utc_iso_string(utc_now())
            ws_payload: dict = {
                "type": "message",
                "message_id": agent_message_id,
                "role": "agent",
                "content": agent_response,
                "timestamp": timestamp,
            }
            if result.get("rag_media_url"):
                ws_payload["media_url"] = result["rag_media_url"]
                ws_payload["media_type"] = result.get("rag_media_type")
            await connection_manager.send_message(conversation_id, ws_payload)
    elif result.get("escalate"):
        return

    if not result.get("escalate"):
        conv_after = await dynamodb.get_conversation(conversation_id)
        if conv_after and get_enum_value(conv_after.status) != ConversationStatus.AI_ACTIVE.value:
            await dynamodb.update_conversation(
                conversation_id=conversation_id,
                status=ConversationStatus.AI_ACTIVE,
            )


async def schedule_timer_trigger(conversation_id: str, pending_timer: dict) -> None:
    """Add a workflow timer trigger to the Redis timer ZSET.

    pending_timer must contain:
      fire_at_ms  – absolute epoch millisecond when to fire
      delay_seconds, message_template, step_id – forwarded to execute_timer_trigger
    """
    redis = get_redis_client()
    if not await redis.ping():
        logger.warning(
            "Redis unavailable; timer trigger not scheduled for %s",
            conversation_id,
            extra={"conversation_id": conversation_id},
        )
        return
    fire_at_ms = pending_timer.get("fire_at_ms", int(time.time() * 1000) + pending_timer.get("delay_seconds", 0) * 1000)
    import json as _json
    payload = _json.dumps(pending_timer)
    await redis.set(f"agent_reply:timer_payload:{conversation_id}", payload, ttl=int(pending_timer.get("delay_seconds", 3600)) * 2 + 300)
    await redis.zadd(KEY_TIMER_DUE, {conversation_id: float(fire_at_ms)})
    logger.info(
        "Timer trigger scheduled for %s at %d ms",
        conversation_id,
        fire_at_ms,
        extra={"conversation_id": conversation_id},
    )


async def _generate_agent_timer_message(
    agent_config: "Any",
    prompt_instruction: str,
    conversation_history: list[dict],
    conversation_id: str,
) -> str:
    """Call the LLM to generate a proactive timer message.

    The LLM is given the agent's base system prompt + the timer prompt instruction
    as a system message, plus the last N conversation turns as context.
    """
    try:
        from app.services.llm_factory import get_llm_factory
        from langchain_core.messages import HumanMessage as _HumanMessage, SystemMessage as _SystemMessage

        llm = await get_llm_factory().get_chat_model(agent_config)

        # Build system context from agent base system prompt.
        base_prompt = ""
        try:
            base_prompt = getattr(getattr(agent_config, "prompts", None), "system_prompt", "") or ""
        except Exception:
            pass

        system_content = (
            f"{base_prompt}\n\n"
            "--- TIMER TRIGGER ---\n"
            f"{prompt_instruction}\n\n"
            "Write only the message text. Do not add any explanations or preamble."
        ).strip()

        messages = [_SystemMessage(content=system_content)]
        for turn in conversation_history[-10:]:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ("assistant", "ai"):
                from langchain_core.messages import AIMessage as _AIMessage
                messages.append(_AIMessage(content=content))
            else:
                messages.append(_HumanMessage(content=content))

        result = await llm.ainvoke(messages)
        text = result.content if hasattr(result, "content") else str(result)
        if isinstance(text, list):
            text = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in text)
        return str(text).strip()
    except Exception as exc:
        logger.error(
            "Timer trigger LLM generation failed for %s: %s",
            conversation_id,
            exc,
            exc_info=True,
        )
        return ""


async def execute_timer_trigger(conversation_id: str) -> None:
    """Fire a scheduled workflow timer trigger for a conversation."""
    import json as _json
    from app.dependencies import get_dynamodb

    redis = get_redis_client()
    dynamodb = get_dynamodb()
    settings = get_settings()

    # Load timer payload from Redis
    raw = await redis.get(f"agent_reply:timer_payload:{conversation_id}")
    if not raw:
        logger.warning("Timer payload missing for %s; skipping", conversation_id, extra={"conversation_id": conversation_id})
        return
    try:
        timer = _json.loads(raw)
    except Exception as exc:
        logger.error("Failed to parse timer payload for %s: %s", conversation_id, exc)
        return

    conversation = await dynamodb.get_conversation(conversation_id)
    if not conversation:
        return
    status_value = get_enum_value(conversation.status)
    if status_value in (ConversationStatus.CLOSED.value, ConversationStatus.NEEDS_HUMAN.value, ConversationStatus.HUMAN_ACTIVE.value):
        return

    agent_data = await dynamodb.get_agent(conversation.agent_id)
    if not agent_data or "config" not in agent_data:
        return

    from app.models.agent_config import AgentConfig
    from app.services.channel_binding_service import ChannelBindingService
    from app.services.channel_sender import get_channel_sender
    from app.services.instagram_service import InstagramService
    from app.services.telegram_service import TelegramService
    from app.storage.resolver import get_secrets_manager

    agent_config = AgentConfig.from_dict(agent_data["config"])
    conversation_channel = get_enum_value(conversation.channel)

    instagram_service = None
    telegram_service = None
    if conversation_channel != MessageChannel.WEB_CHAT.value:
        secrets_manager = get_secrets_manager()
        binding_service = ChannelBindingService(dynamodb, secrets_manager)
        if conversation_channel == MessageChannel.INSTAGRAM.value:
            instagram_service = InstagramService(binding_service, dynamodb, settings)
        elif conversation_channel == MessageChannel.TELEGRAM.value:
            telegram_service = TelegramService(binding_service, dynamodb, settings)

    from app.models.message import MessageChannel as MC
    channel_enum = MC(conversation_channel) if conversation_channel else MC.WEB_CHAT
    channel_sender = get_channel_sender(channel_enum, dynamodb, instagram_service, telegram_service)

    action_type = timer.get("action_type", "static")

    # Load LangGraph state for variable substitution and conversation context.
    collected: dict = {}
    conversation_history: list[dict] = []
    try:
        from app.storage.postgres_checkpointer import get_checkpointer
        checkpointer = get_checkpointer()
        state_snapshot = await checkpointer.aget({"configurable": {"thread_id": conversation_id}})
        if state_snapshot:
            collected = state_snapshot.values.get("collected") or {}
            raw_messages = state_snapshot.values.get("messages") or []
            for m in raw_messages[-20:]:
                role = type(m).__name__.lower().replace("message", "").replace("ai", "assistant").replace("human", "user")
                text = getattr(m, "content", "")
                if isinstance(text, list):
                    text = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in text)
                if text:
                    conversation_history.append({"role": role, "content": str(text)})
    except Exception as exc:
        logger.debug("Timer trigger: could not load checkpointer state for %s: %s", conversation_id, exc)

    if action_type == "agent":
        # Generate a proactive message via LLM using conversation context + prompt instruction.
        prompt_instruction = timer.get("prompt", "")
        if not prompt_instruction:
            logger.warning(
                "Timer trigger action_type=agent but no prompt for %s; skipping",
                conversation_id,
            )
            await redis.delete(f"agent_reply:timer_payload:{conversation_id}")
            return

        message_text = await _generate_agent_timer_message(
            agent_config=agent_config,
            prompt_instruction=prompt_instruction,
            conversation_history=conversation_history,
            conversation_id=conversation_id,
        )
    else:
        # Static: substitute {variable} placeholders from collected fields.
        message_text = timer.get("message_template", "")
        for k, v in collected.items():
            message_text = message_text.replace(f"{{{k}}}", str(v))

    if not message_text:
        logger.info(
            "Timer trigger produced empty message for %s; skipping",
            conversation_id,
        )
        await redis.delete(f"agent_reply:timer_payload:{conversation_id}")
        return

    # Persist the timer message in the DB and send via channel.
    import uuid as _uuid
    from app.models.message import Message, MessageRole
    timer_msg = Message(
        message_id=str(_uuid.uuid4()),
        conversation_id=conversation_id,
        agent_id=conversation.agent_id,
        role=MessageRole.ASSISTANT,
        content=message_text,
        channel=conversation.channel,
        timestamp=utc_now(),
        metadata={"timer_trigger": True, "step_id": timer.get("step_id")},
    )
    try:
        await dynamodb.create_message(timer_msg)
    except Exception as exc:
        logger.warning("Timer trigger: could not persist message for %s: %s", conversation_id, exc)

    # Send via channel sender
    try:
        await channel_sender.send_message(
            conversation_id=conversation_id,
            message_text=message_text,
        )
        logger.info(
            "Timer trigger (%s) message sent for conversation %s",
            action_type,
            conversation_id,
            extra={"conversation_id": conversation_id},
        )
    except Exception as exc:
        logger.error(
            "Timer trigger send failed for %s: %s",
            conversation_id,
            exc,
            exc_info=True,
            extra={"conversation_id": conversation_id},
        )

    # Clean up payload key
    await redis.delete(f"agent_reply:timer_payload:{conversation_id}")


async def _poll_due_once() -> None:
    settings = get_settings()
    if settings.agent_reply_debounce_seconds <= 0:
        return

    redis = get_redis_client()
    if not await redis.ping():
        return

    now_ms = int(time.time() * 1000)

    # --- Poll reply debounce queue ---
    try:
        due = await redis.zrangebyscore(KEY_DUE, "-inf", now_ms, num=50)
    except Exception as exc:
        logger.debug("agent_reply poll zrangebyscore: %s", exc)
        due = []

    for conversation_id in due:
        lock_key = f"{KEY_LOCK_PREFIX}{conversation_id}"
        acquired = await redis.set_nx_ex(lock_key, "1", LOCK_TTL_SECONDS)
        if not acquired:
            continue

        try:
            score = await redis.zscore(KEY_DUE, conversation_id)
            if score is None or score > now_ms:
                continue

            expected_version = await _current_reply_version(redis, conversation_id)
            if expected_version <= 0:
                await redis.zrem(KEY_DUE, conversation_id)
                continue

            await redis.zrem(KEY_DUE, conversation_id)

            async def _run(cid: str, ver: int) -> None:
                try:
                    await execute_agent_reply(cid, ver)
                except Exception as exc:
                    logger.error(
                        "Debounced agent reply task failed: %s",
                        exc,
                        extra={"conversation_id": cid},
                        exc_info=True,
                    )

            asyncio.create_task(_run(conversation_id, expected_version))
        finally:
            await redis.delete(lock_key)

    # --- Poll timer trigger queue ---
    try:
        timer_due = await redis.zrangebyscore(KEY_TIMER_DUE, "-inf", now_ms, num=50)
    except Exception as exc:
        logger.debug("agent_reply timer poll zrangebyscore: %s", exc)
        timer_due = []

    for conversation_id in timer_due:
        lock_key = f"{KEY_TIMER_LOCK_PREFIX}{conversation_id}"
        acquired = await redis.set_nx_ex(lock_key, "1", LOCK_TTL_SECONDS)
        if not acquired:
            continue

        try:
            score = await redis.zscore(KEY_TIMER_DUE, conversation_id)
            if score is None or score > now_ms:
                continue

            await redis.zrem(KEY_TIMER_DUE, conversation_id)

            async def _run_timer(cid: str) -> None:
                try:
                    await execute_timer_trigger(cid)
                except Exception as exc:
                    logger.error(
                        "Timer trigger task failed for %s: %s",
                        cid,
                        exc,
                        exc_info=True,
                        extra={"conversation_id": cid},
                    )

            asyncio.create_task(_run_timer(conversation_id))
        finally:
            await redis.delete(lock_key)


async def _poll_timers_once() -> None:
    """Poll the workflow timer ZSET and fire any due triggers."""
    redis = get_redis_client()
    if not await redis.ping():
        return

    now_ms = int(time.time() * 1000)

    try:
        timer_due = await redis.zrangebyscore(KEY_TIMER_DUE, "-inf", now_ms, num=50)
    except Exception as exc:
        logger.debug("timer poll zrangebyscore: %s", exc)
        return

    for conversation_id in timer_due:
        lock_key = f"{KEY_TIMER_LOCK_PREFIX}{conversation_id}"
        acquired = await redis.set_nx_ex(lock_key, "1", LOCK_TTL_SECONDS)
        if not acquired:
            continue

        try:
            score = await redis.zscore(KEY_TIMER_DUE, conversation_id)
            if score is None or score > now_ms:
                continue

            await redis.zrem(KEY_TIMER_DUE, conversation_id)

            async def _run_timer(cid: str) -> None:
                try:
                    await execute_timer_trigger(cid)
                except Exception as exc:
                    logger.error(
                        "Timer trigger task failed for %s: %s",
                        cid,
                        exc,
                        exc_info=True,
                        extra={"conversation_id": cid},
                    )

            asyncio.create_task(_run_timer(conversation_id))
        finally:
            await redis.delete(lock_key)


async def run_timer_poll_loop(shutdown: asyncio.Event) -> None:
    """Poll the workflow timer queue every 5 s, independent of debounce setting.

    Started unconditionally at application startup so inactivity timers always
    fire even when debounce is disabled.
    """
    logger.info("Workflow timer poll loop started")
    while True:
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=5.0)
            break
        except asyncio.TimeoutError:
            await _poll_timers_once()
    logger.info("Workflow timer poll loop stopped")


async def run_debounce_poll_loop(shutdown: asyncio.Event) -> None:
    """Poll Redis debounce due set periodically until shutdown is set."""
    settings = get_settings()
    if settings.agent_reply_debounce_seconds <= 0:
        return

    logger.info(
        "Agent reply debounce poll loop started (%ss)",
        settings.agent_reply_debounce_seconds,
    )
    while True:
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=0.5)
            break
        except asyncio.TimeoutError:
            await _poll_due_once()
    logger.info("Agent reply debounce poll loop stopped")
