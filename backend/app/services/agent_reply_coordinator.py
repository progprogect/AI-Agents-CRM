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
KEY_TIMER_FAILED_PREFIX = "agent_reply:timer_failed:"
LOCK_TTL_SECONDS = 120
TIMER_DEAD_LETTER_TTL = 86400  # 24 h


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
            if result.get("quick_replies"):
                ws_payload["quick_replies"] = result["quick_replies"]
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

        # Build base system prompt from agent config fields
        # (mirrors AgentChain._build_base_system_prompt without heavy sections like
        #  escalation rules and examples that are not needed for a timer message).
        base_prompt = ""
        try:
            sys_dict: dict = agent_config.prompts.system or {}
            profile = agent_config.profile
            persona = sys_dict.get("persona", "")
            if persona:
                try:
                    persona = persona.format(
                        agent_display_name=getattr(profile, "agent_display_name", ""),
                        doctor_display_name=getattr(profile, "agent_display_name", ""),
                        company_display_name=getattr(profile, "company_display_name", ""),
                        specialty=getattr(profile, "specialty", "") or "",
                    )
                except (KeyError, IndexError, ValueError):
                    pass  # persona template has unknown/malformed placeholders — use as-is
            hard_rules = sys_dict.get("hard_rules", "")
            goal = sys_dict.get("goal", "")
            parts = [p for p in [persona, hard_rules, goal] if p.strip()]
            base_prompt = "\n\n".join(parts)
        except Exception:
            pass

        system_content = (
            f"{base_prompt}\n\n"
            "--- КОНТЕКСТ ---\n"
            "Ты уже ведёшь разговор с пользователем (история сообщений ниже). "
            "Тебе нужно написать следующее сообщение-продолжение в этот диалог.\n"
            "Не начинай с приветствия — разговор уже идёт.\n\n"
            "--- ЗАДАЧА ---\n"
            f"{prompt_instruction}\n\n"
            "Напиши только текст сообщения. Без пояснений и предисловий."
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

    # Guard: discard timer if the agent's workflow was changed after scheduling.
    stored_hash = timer.get("config_hash")
    if stored_hash:
        from app.chains.agent_chain import workflow_config_hash
        if stored_hash != workflow_config_hash(agent_config.workflow):
            logger.info(
                "Timer for %s discarded: workflow changed since scheduling",
                conversation_id,
                extra={"conversation_id": conversation_id},
            )
            await redis.delete(f"agent_reply:timer_payload:{conversation_id}")
            return

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

            # Guard: discard timer if the conversation has already moved past the
            # step that originally scheduled it (e.g. user replied mid-timer).
            timer_step = timer.get("step_id")
            checkpoint_step = state_snapshot.values.get("current_step_id")
            if timer_step and checkpoint_step and timer_step != checkpoint_step:
                logger.info(
                    "Timer for %s discarded: conversation moved from step '%s' to '%s'",
                    conversation_id,
                    timer_step,
                    checkpoint_step,
                    extra={"conversation_id": conversation_id},
                )
                await redis.delete(f"agent_reply:timer_payload:{conversation_id}")
                return
    except Exception as exc:
        logger.warning(
            "Timer trigger: could not load checkpointer state for %s: %s",
            conversation_id,
            exc,
            extra={"conversation_id": conversation_id},
        )

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

        # Without conversation history the LLM has no context for a follow-up
        # message and tends to generate a generic greeting instead. Skip the
        # timer and clean up so it doesn't linger in Redis.
        if not conversation_history:
            logger.warning(
                "Timer trigger action_type=agent skipped for %s: conversation history is empty"
                " (checkpointer unavailable or new conversation). "
                "A static message_template would fire regardless.",
                conversation_id,
                extra={"conversation_id": conversation_id},
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
        role=MessageRole.AGENT,
        content=message_text,
        channel=conversation.channel,
        timestamp=utc_now(),
        metadata={"timer_trigger": True, "step_id": timer.get("step_id")},
    )
    try:
        await dynamodb.create_message(timer_msg)
    except Exception as exc:
        logger.warning("Timer trigger: could not persist message for %s: %s", conversation_id, exc)

    # Send via channel sender — pass message_id so WebChatSender can include it in WS payload
    try:
        await channel_sender.send_message(
            conversation_id=conversation_id,
            message_text=message_text,
            message_id=timer_msg.message_id,
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

    # Timer trigger queue is handled by run_timer_poll_loop / _poll_timers_once.


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
                    # Write dead-letter entry so failures are observable and
                    # can be replayed manually or via monitoring.
                    import json as _dl_json
                    _dl_redis = get_redis_client()
                    try:
                        await _dl_redis.set(
                            f"{KEY_TIMER_FAILED_PREFIX}{cid}",
                            _dl_json.dumps({"error": str(exc), "ts": time.time()}),
                            ttl=TIMER_DEAD_LETTER_TTL,
                        )
                    except Exception:
                        pass  # dead-letter write failure must never re-raise

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


# ---------------------------------------------------------------------------
# Auto-step: time-triggered follow-up actions (independent of user activity)
# ---------------------------------------------------------------------------

KEY_AUTO_DUE = "agent_reply:auto_step_due"
KEY_AUTO_PAY = "agent_reply:auto_step_payload:"  # + "{conv_id}:{auto_step_id}"
KEY_AUTO_IDX = "agent_reply:auto_step_idx:"      # SET per conversation — active members
AUTO_STEP_LOCK_PREFIX = "agent_reply:auto_step_lock:"
AUTO_STEP_DEAD_LETTER_TTL = 86400  # 24 h


async def schedule_auto_step(
    conversation_id: str,
    auto_step: dict,
    config_hash: str,
    fire_at_ms: int,
) -> None:
    """Schedule a single auto-step to fire at ``fire_at_ms``."""
    redis = get_redis_client()
    if not await redis.ping():
        logger.warning(
            "Redis unavailable; auto-step %s not scheduled for %s",
            auto_step.get("id"),
            conversation_id,
        )
        return
    import json as _json

    auto_step_id = auto_step["id"]
    member = f"{conversation_id}:{auto_step_id}"
    payload = _json.dumps({**auto_step, "config_hash": config_hash, "conversation_id": conversation_id})
    ttl = auto_step.get("delay_seconds", 3600) * 2 + 300

    await redis.set(f"{KEY_AUTO_PAY}{member}", payload, ttl=ttl)
    await redis.zadd(KEY_AUTO_DUE, {member: float(fire_at_ms)})
    # Track active members per conversation for bulk cancellation.
    await redis.sadd(f"{KEY_AUTO_IDX}{conversation_id}", member)
    logger.info(
        "Auto-step %s scheduled for %s at %d ms",
        auto_step_id,
        conversation_id,
        fire_at_ms,
        extra={"conversation_id": conversation_id},
    )


async def cancel_all_auto_steps(conversation_id: str) -> None:
    """Cancel every pending auto-step for *conversation_id* (e.g. on step transition)."""
    redis = get_redis_client()
    try:
        if not await redis.ping():
            return
        idx_key = f"{KEY_AUTO_IDX}{conversation_id}"
        members = await redis.smembers(idx_key)
        if members:
            await redis.zrem(KEY_AUTO_DUE, *members)
            for m in members:
                await redis.delete(f"{KEY_AUTO_PAY}{m}")
        await redis.delete(idx_key)
    except Exception as exc:
        logger.debug("cancel_all_auto_steps error for %s: %s", conversation_id, exc)


async def _evaluate_auto_step_condition(
    condition: str,
    agent_config: "Any",
    conversation_history: list[dict],
    conversation_id: str,
) -> bool:
    """Return True if the LLM evaluates the condition as satisfied (yes)."""
    try:
        from app.services.llm_factory import get_llm_factory
        from langchain_core.messages import HumanMessage as _HM, SystemMessage as _SM

        llm = await get_llm_factory().get_chat_model(agent_config)
        history_text = "\n".join(
            f"{t.get('role', 'user').upper()}: {t.get('content', '')}"
            for t in conversation_history[-10:]
        )
        system = (
            "You are evaluating whether a condition is true based on the conversation so far.\n"
            "Reply with exactly one word: YES or NO.\n\n"
            f"Condition: {condition}\n\n"
            f"Conversation:\n{history_text}"
        )
        result = await llm.ainvoke([_SM(content=system), _HM(content="Is the condition true?")])
        text = result.content if hasattr(result, "content") else str(result)
        if isinstance(text, list):
            text = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in text)
        return "yes" in str(text).strip().lower()
    except Exception as exc:
        logger.warning(
            "Auto-step condition evaluation failed for %s: %s — defaulting to True",
            conversation_id,
            exc,
        )
        return True  # fail-open: send message if condition check fails


async def execute_auto_step_trigger(member: str) -> None:
    """Fire a scheduled auto-step for the given ZSET member ``{conv_id}:{auto_step_id}``."""
    import json as _json
    from app.dependencies import get_dynamodb

    redis = get_redis_client()
    dynamodb = get_dynamodb()
    settings = get_settings()

    raw = await redis.get(f"{KEY_AUTO_PAY}{member}")
    if not raw:
        logger.warning("Auto-step payload missing for member %s; skipping", member)
        return
    try:
        payload = _json.loads(raw)
    except Exception as exc:
        logger.error("Failed to parse auto-step payload for %s: %s", member, exc)
        return

    conversation_id: str = payload.get("conversation_id", member.split(":")[0])
    auto_step_id: str = payload.get("id", member.split(":", 1)[-1])

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

    # Guard: discard if workflow was changed after scheduling.
    stored_hash = payload.get("config_hash")
    if stored_hash:
        from app.chains.agent_chain import workflow_config_hash
        if stored_hash != workflow_config_hash(agent_config.workflow):
            logger.info(
                "Auto-step %s for %s discarded: workflow changed since scheduling",
                auto_step_id,
                conversation_id,
                extra={"conversation_id": conversation_id},
            )
            await redis.delete(f"{KEY_AUTO_PAY}{member}")
            return

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

    action_type = payload.get("action_type", "static")

    # Load conversation state for variable substitution and LLM context.
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
        logger.warning(
            "Auto-step: could not load checkpointer state for %s: %s",
            conversation_id,
            exc,
            extra={"conversation_id": conversation_id},
        )

    # Optional condition check.
    condition = payload.get("condition")
    if condition:
        should_send = await _evaluate_auto_step_condition(
            condition, agent_config, conversation_history, conversation_id
        )
        if not should_send:
            logger.info(
                "Auto-step %s for %s skipped: condition not met",
                auto_step_id,
                conversation_id,
                extra={"conversation_id": conversation_id},
            )
            await redis.delete(f"{KEY_AUTO_PAY}{member}")
            try:
                await redis.srem(f"{KEY_AUTO_IDX}{conversation_id}", member)
            except Exception:
                pass
            # Schedule next auto-steps in chain even when this one is skipped.
            await _schedule_chained_auto_steps(
                conversation_id, auto_step_id, agent_config, stored_hash or ""
            )
            return

    if action_type == "agent":
        message_text = await _generate_agent_timer_message(
            agent_config=agent_config,
            prompt_instruction=payload.get("prompt", ""),
            conversation_history=conversation_history,
            conversation_id=conversation_id,
        )
    else:
        message_text = payload.get("message_template", "")
        for k, v in collected.items():
            message_text = message_text.replace(f"{{{k}}}", str(v))

    if not message_text:
        logger.info(
            "Auto-step %s for %s produced empty message; skipping send",
            auto_step_id,
            conversation_id,
        )
    else:
        import uuid as _uuid
        from app.models.message import Message, MessageRole
        from app.utils.datetime_utils import utc_now

        msg = Message(
            message_id=str(_uuid.uuid4()),
            conversation_id=conversation_id,
            agent_id=conversation.agent_id,
            role=MessageRole.AGENT,
            content=message_text,
            channel=conversation.channel,
            timestamp=utc_now(),
            metadata={"auto_step_trigger": True, "auto_step_id": auto_step_id},
        )
        try:
            await dynamodb.create_message(msg)
        except Exception as exc:
            logger.warning("Auto-step: could not persist message for %s: %s", conversation_id, exc)

        try:
            await channel_sender.send_message(
                conversation_id=conversation_id,
                message_text=message_text,
                message_id=msg.message_id,
            )
            logger.info(
                "Auto-step %s (%s) sent for conversation %s",
                auto_step_id,
                action_type,
                conversation_id,
                extra={"conversation_id": conversation_id},
            )
        except Exception as exc:
            logger.error(
                "Auto-step send failed for %s: %s",
                conversation_id,
                exc,
                exc_info=True,
                extra={"conversation_id": conversation_id},
            )

    await redis.delete(f"{KEY_AUTO_PAY}{member}")
    # Remove from conversation index.
    try:
        await redis.srem(f"{KEY_AUTO_IDX}{conversation_id}", member)
    except Exception:
        pass

    # Schedule the next auto-steps in the chain (sourced from this auto-step).
    await _schedule_chained_auto_steps(
        conversation_id, auto_step_id, agent_config, stored_hash or ""
    )


async def _schedule_chained_auto_steps(
    conversation_id: str,
    fired_auto_step_id: str,
    agent_config: "Any",
    config_hash: str,
) -> None:
    """Schedule any auto-steps whose source_id matches the just-fired auto-step."""
    next_steps = [
        a for a in agent_config.workflow.auto_steps
        if a.source_id == fired_auto_step_id
    ]
    for nxt in next_steps:
        fire_at_ms = int(time.time() * 1000) + nxt.delay_seconds * 1000
        await schedule_auto_step(
            conversation_id,
            auto_step=nxt.model_dump(),
            config_hash=config_hash,
            fire_at_ms=fire_at_ms,
        )


async def _poll_auto_steps_once() -> None:
    """Poll the auto-step ZSET and fire any due triggers."""
    redis = get_redis_client()
    if not await redis.ping():
        return

    now_ms = int(time.time() * 1000)

    try:
        due_members = await redis.zrangebyscore(KEY_AUTO_DUE, "-inf", now_ms, num=50)
    except Exception as exc:
        logger.debug("auto-step poll zrangebyscore: %s", exc)
        return

    for member in due_members:
        lock_key = f"{AUTO_STEP_LOCK_PREFIX}{member}"
        acquired = await redis.set_nx_ex(lock_key, "1", LOCK_TTL_SECONDS)
        if not acquired:
            continue

        try:
            score = await redis.zscore(KEY_AUTO_DUE, member)
            if score is None or score > now_ms:
                continue

            await redis.zrem(KEY_AUTO_DUE, member)

            async def _run_auto(m: str) -> None:
                try:
                    await execute_auto_step_trigger(m)
                except Exception as exc:
                    logger.error(
                        "Auto-step task failed for %s: %s",
                        m,
                        exc,
                        exc_info=True,
                    )
                    import json as _dl_json
                    _dl_redis = get_redis_client()
                    try:
                        await _dl_redis.set(
                            f"agent_reply:auto_step_failed:{m}",
                            _dl_json.dumps({"error": str(exc), "ts": time.time()}),
                            ttl=AUTO_STEP_DEAD_LETTER_TTL,
                        )
                    except Exception:
                        pass

            asyncio.create_task(_run_auto(member))
        finally:
            await redis.delete(lock_key)


async def run_auto_step_poll_loop(shutdown: asyncio.Event) -> None:
    """Poll the auto-step queue every 5 s, started unconditionally at application startup."""
    logger.info("Auto-step poll loop started")
    while True:
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=5.0)
            break
        except asyncio.TimeoutError:
            await _poll_auto_steps_once()
    logger.info("Auto-step poll loop stopped")


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
