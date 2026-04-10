"""Telegram bot commands management.

Provides:
- TELEGRAM_BOT_COMMANDS  — catalog of supported bot commands (extend here to add new ones)
- sync_telegram_commands — calls setMyCommands to update the bot menu in Telegram
- get_commands_status    — returns catalog merged with enabled flags from binding metadata
- handle_restart         — /restart command: close current conversation, open a new one
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

import httpx

from app.models.channel_binding import ChannelBinding
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

# ---------------------------------------------------------------------------
# Command catalog — add new commands here to make them available in the UI
# ---------------------------------------------------------------------------

TELEGRAM_BOT_COMMANDS: list[dict[str, str]] = [
    {
        "key": "restart",
        "command": "restart",
        "description": "Начать новый чат",
    },
]


# ---------------------------------------------------------------------------
# Telegram API helpers
# ---------------------------------------------------------------------------

async def sync_telegram_commands(bot_token: str, enabled_commands: dict[str, bool]) -> None:
    """Push the current enabled command list to Telegram setMyCommands.

    Telegram displays the commands as a menu button inside the chat.
    If no commands are enabled, the menu button is removed (empty list).

    Args:
        bot_token: The bot's access token.
        enabled_commands: Mapping of command key → enabled flag,
            e.g. ``{"restart": True}``.
    """
    commands_payload = [
        {"command": cmd["command"], "description": cmd["description"]}
        for cmd in TELEGRAM_BOT_COMMANDS
        if enabled_commands.get(cmd["key"], False)
    ]

    url = f"{TELEGRAM_API_BASE}{bot_token}/setMyCommands"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"commands": commands_payload})
            data = resp.json()
            if not data.get("ok"):
                logger.warning(
                    "setMyCommands returned not-ok: %s",
                    data,
                )
            else:
                logger.info(
                    "setMyCommands: %d command(s) registered for bot",
                    len(commands_payload),
                )
    except Exception as exc:
        logger.error("setMyCommands API call failed: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Status helper used by the GET /commands endpoint
# ---------------------------------------------------------------------------

def get_commands_status(binding: ChannelBinding) -> list[dict[str, Any]]:
    """Return the command catalog annotated with per-binding enabled flags."""
    enabled: dict[str, bool] = binding.metadata.get("telegram_commands", {})
    return [
        {
            "key": cmd["key"],
            "command": f"/{cmd['command']}",
            "description": cmd["description"],
            "enabled": bool(enabled.get(cmd["key"], False)),
        }
        for cmd in TELEGRAM_BOT_COMMANDS
    ]


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def handle_restart(
    dynamodb: Any,
    chat_id: str,
    binding: ChannelBinding,
    bot_token: str,
) -> None:
    """Handle /restart command: close the current conversation and start a new one.

    Steps:
    1. Find the current open conversation for this chat_id (external_user_id).
    2. Close it (CLOSED status).
    3. Create a fresh conversation.
    4. Send a confirmation message to the user.
    """
    try:
        # Find existing conversation for this user
        existing_conversations = await dynamodb.list_conversations(
            agent_id=binding.agent_id,
            external_user_id=chat_id,
            status=ConversationStatus.AI_ACTIVE,
        )

        # Close all active conversations for this chat_id
        for conv in (existing_conversations or []):
            await dynamodb.update_conversation(
                conversation_id=conv.conversation_id,
                status=ConversationStatus.CLOSED,
                closed_at=utc_now(),
            )
            logger.info(
                "Closed conversation %s for chat_id=%s via /restart",
                conv.conversation_id,
                chat_id,
            )

        # Create a new conversation
        new_conv_id = str(uuid.uuid4())
        new_conversation = Conversation(
            conversation_id=new_conv_id,
            agent_id=binding.agent_id,
            channel="telegram",
            external_user_id=chat_id,
            status=ConversationStatus.AI_ACTIVE,
            marketing_status=MarketingStatus.NEW,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        await dynamodb.create_conversation(new_conversation)
        logger.info(
            "Created new conversation %s for chat_id=%s via /restart",
            new_conv_id,
            chat_id,
        )

        # Send confirmation to the user in Telegram
        await _send_telegram_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text="✅ Чат перезапущен. Начнём сначала!",
        )

    except Exception as exc:
        logger.error(
            "handle_restart failed for chat_id=%s binding=%s: %s",
            chat_id,
            binding.binding_id,
            exc,
            exc_info=True,
        )


async def _send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    """Send a plain text message to a Telegram chat."""
    url = f"{TELEGRAM_API_BASE}{bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"chat_id": chat_id, "text": text})
            data = resp.json()
            if not data.get("ok"):
                logger.warning("sendMessage returned not-ok: %s", data)
    except Exception as exc:
        logger.error("sendMessage failed for chat_id=%s: %s", chat_id, exc)


# ---------------------------------------------------------------------------
# Dispatcher — called from telegram_service.py
# ---------------------------------------------------------------------------

COMMAND_HANDLERS: dict[str, Any] = {
    "restart": handle_restart,
}


async def dispatch_command(
    command: str,
    chat_id: str,
    binding: ChannelBinding,
    bot_token: str,
    dynamodb: Any,
) -> bool:
    """Try to handle a bot command.  Returns True if command was handled.

    Args:
        command: Raw command text, e.g. ``"/restart"`` or ``"/restart@mybot"``.
        chat_id: Telegram chat_id (string).
        binding: The ChannelBinding for this bot.
        bot_token: Bot access token.
        dynamodb: Database client.

    Returns:
        True if the command was recognised and handled; False otherwise.
    """
    # Strip the "/" prefix and any "@botname" suffix
    cmd_key = command.lstrip("/").split("@")[0].lower()

    enabled: dict[str, bool] = binding.metadata.get("telegram_commands", {})
    if not enabled.get(cmd_key, False):
        return False  # command disabled or unknown — let agent handle as text

    handler = COMMAND_HANDLERS.get(cmd_key)
    if handler is None:
        return False

    logger.info(
        "Dispatching bot command /%s for chat_id=%s binding=%s",
        cmd_key,
        chat_id,
        binding.binding_id,
    )
    await handler(
        dynamodb=dynamodb,
        chat_id=chat_id,
        binding=binding,
        bot_token=bot_token,
    )
    return True
