"""Telegram bot commands management.

Provides:
- TELEGRAM_BOT_COMMANDS  — catalog of supported bot commands (extend here to add new ones)
- sync_telegram_commands — calls setMyCommands to update the bot menu in Telegram
- get_commands_status    — returns catalog merged with enabled flags from binding metadata
- handle_restart         — /restart command: close current conversation, open a new one

Binding metadata (optional):
- ``telegram_commands``: ``{command_key: bool}`` — toggles for menu entries.
- ``telegram_command_settings``: ``{command_key: {"menu_description": str, "message": str}}``
  — custom menu label (Telegram, max 256 chars) and reply text for configurable commands.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.models.channel_binding import ChannelBinding
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.services.channel_binding_service import ChannelBindingService
from app.services.telegram_service import TelegramService
from app.storage.resolver import get_secrets_manager
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

# Keys that use telegram_command_settings[].message / menu_description
CONFIGURABLE_COMMAND_KEYS = frozenset({"supportproject", "feedback"})

TELEGRAM_MENU_DESCRIPTION_MAX = 256
TELEGRAM_COMMAND_MESSAGE_MAX = 4096

# ---------------------------------------------------------------------------
# Command catalog — add new commands here to make them available in the UI
# ---------------------------------------------------------------------------

TELEGRAM_BOT_COMMANDS: list[dict[str, str]] = [
    {
        "key": "restart",
        "command": "restart",
        "description": "Начать новый чат",
    },
    {
        "key": "paysupport",
        "command": "paysupport",
        "description": "Вопросы по оплате",
    },
    {
        "key": "questionnaire",
        "command": "questionnaire",
        "description": "Моя анкета",
    },
    {
        "key": "reminders",
        "command": "reminders",
        "description": "Напоминания",
    },
    {
        "key": "supportproject",
        "command": "supportproject",
        "description": "Поддержать проект",
    },
    {
        "key": "feedback",
        "command": "feedback",
        "description": "Обратная связь",
    },
]


def _catalog_by_key() -> dict[str, dict[str, str]]:
    return {c["key"]: c for c in TELEGRAM_BOT_COMMANDS}


def _command_settings_map(binding: ChannelBinding) -> dict[str, Any]:
    raw = binding.metadata.get("telegram_command_settings")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(k, str) and isinstance(v, dict):
            out[k] = v
    return out


def effective_menu_description(binding: ChannelBinding, cmd_key: str) -> str:
    """Menu text sent to Telegram setMyCommands (catalog default or admin override)."""
    catalog = _catalog_by_key().get(cmd_key) or {}
    default = (catalog.get("description") or "").strip()
    settings = _command_settings_map(binding).get(cmd_key) or {}
    override = settings.get("menu_description") if isinstance(settings, dict) else None
    if isinstance(override, str) and override.strip():
        return override.strip()[:TELEGRAM_MENU_DESCRIPTION_MAX]
    return default[:TELEGRAM_MENU_DESCRIPTION_MAX]


async def sync_telegram_commands(bot_token: str, binding: ChannelBinding) -> None:
    """Push the current enabled command list to Telegram setMyCommands.

    Telegram displays the commands as a menu button inside the chat.
    If no commands are enabled, the menu button is removed (empty list).

    Args:
        bot_token: The bot's access token.
        binding: Channel binding (metadata enables commands and optional menu labels).
    """
    enabled_commands: dict[str, bool] = binding.metadata.get("telegram_commands", {})
    commands_payload = []
    for cmd in TELEGRAM_BOT_COMMANDS:
        if not enabled_commands.get(cmd["key"], False):
            continue
        desc = effective_menu_description(binding, cmd["key"])
        if not desc:
            desc = cmd["description"]
        commands_payload.append({"command": cmd["command"], "description": desc})

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
    """Return the command catalog annotated with per-binding enabled flags and settings."""
    enabled: dict[str, bool] = binding.metadata.get("telegram_commands", {})
    settings_map = _command_settings_map(binding)
    rows: list[dict[str, Any]] = []
    for cmd in TELEGRAM_BOT_COMMANDS:
        key = cmd["key"]
        st = settings_map.get(key) if isinstance(settings_map.get(key), dict) else {}
        menu_override = (
            (st.get("menu_description") or "").strip()
            if isinstance(st.get("menu_description"), str)
            else ""
        )
        message_val = st.get("message") if isinstance(st, dict) else None
        message_str = message_val.strip() if isinstance(message_val, str) else ""
        row: dict[str, Any] = {
            "key": key,
            "command": f"/{cmd['command']}",
            "description": effective_menu_description(binding, key),
            "default_description": cmd["description"],
            "enabled": bool(enabled.get(key, False)),
            "supports_custom_content": key in CONFIGURABLE_COMMAND_KEYS,
        }
        if key in CONFIGURABLE_COMMAND_KEYS:
            row["menu_description"] = menu_override or None
            row["message"] = message_str
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def handle_restart(
    db: Any,
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
        # Find existing active conversations for this user.
        # list_conversations does not support external_user_id filtering,
        # so we fetch by agent_id + status and filter client-side — same
        # pattern as _find_or_create_conversation in telegram_service.py.
        all_conversations = await db.list_conversations(
            agent_id=binding.agent_id,
            status=ConversationStatus.AI_ACTIVE,
            limit=200,
        )
        existing_conversations = [
            c for c in (all_conversations or [])
            if c.external_user_id == chat_id
        ]

        # Close all active conversations for this chat_id and cancel any
        # pending timers / auto-steps so they don't fire on the closed conv.
        for conv in existing_conversations:
            await db.update_conversation(
                conversation_id=conv.conversation_id,
                status=ConversationStatus.CLOSED,
                closed_at=utc_now(),
            )
            logger.info(
                "Closed conversation %s for chat_id=%s via /restart",
                conv.conversation_id,
                chat_id,
            )
            try:
                from app.services.agent_reply_coordinator import cancel_all_auto_steps
                from app.storage.redis import get_redis_client
                redis = get_redis_client()
                await redis.delete(f"agent_reply:timer_payload:{conv.conversation_id}")
                await cancel_all_auto_steps(conv.conversation_id)
            except Exception as exc:
                logger.warning(
                    "Could not cancel timers for conversation %s during /restart: %s",
                    conv.conversation_id,
                    exc,
                )

        try:
            from app.services.reminder_wizard_service import clear_wizard as clear_reminder_wizard
            await clear_reminder_wizard(binding.binding_id, chat_id)
        except Exception as exc:
            logger.debug(
                "Could not clear reminder wizard FSM during /restart for chat_id=%s: %s",
                chat_id,
                exc,
            )

        try:
            from app.services.questionnaire_service import clear_fsm as clear_questionnaire_fsm
            await clear_questionnaire_fsm(binding.binding_id, chat_id)
        except Exception as exc:
            logger.debug(
                "Could not clear questionnaire FSM during /restart for chat_id=%s: %s",
                chat_id,
                exc,
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
        await db.create_conversation(new_conversation)
        logger.info(
            "Created new conversation %s for chat_id=%s via /restart",
            new_conv_id,
            chat_id,
        )

        # Send welcome message: use agent-configured restart_welcome template if set,
        # otherwise fall back to the built-in default greeting.
        _DEFAULT_RESTART_WELCOME = (
            "Привет! Я Татьяна, твой личный помощник с любыми вопросами о питомце 🐾\n\n"
            "Пиши текстом, отправляй голосовые или загружай фото - я пойму и помогу разобраться.\n\n"
            "Скажи, у тебя кошка 🐈 или собака 🐩?"
        )
        welcome_text = _DEFAULT_RESTART_WELCOME
        agent_data = None
        try:
            agent_data = await db.get_agent(binding.agent_id)
            if agent_data and "config" in agent_data:
                custom = (
                    agent_data["config"]
                    .get("prompts", {})
                    .get("templates", {})
                    .get("restart_welcome", "")
                    .strip()
                )
                if custom:
                    welcome_text = custom
                video_note_file_id = (
                    agent_data["config"]
                    .get("prompts", {})
                    .get("templates", {})
                    .get("intro_video_note_file_id", "")
                    .strip()
                )
            else:
                video_note_file_id = ""
        except Exception as exc:
            logger.debug("Could not load restart_welcome template: %s", exc)
            video_note_file_id = ""

        # Intro video note first, then pause, then welcome text (same Telegram path as workflow auto-steps).
        if video_note_file_id:
            try:
                logger.info(
                    "Sending intro video note binding=%s agent=%s chat_id=%s",
                    binding.binding_id,
                    binding.agent_id,
                    chat_id,
                )
                secrets_manager = get_secrets_manager()
                binding_svc = ChannelBindingService(db, secrets_manager)
                telegram_svc = TelegramService(binding_svc, db, get_settings())
                result = await telegram_svc.send_message(
                    binding.binding_id,
                    chat_id,
                    "",
                    media_url=video_note_file_id,
                    media_type="video_note",
                )
                if isinstance(result, dict) and result.get("ok"):
                    logger.info(
                        "Intro video note sent binding=%s chat_id=%s",
                        binding.binding_id,
                        chat_id,
                    )
                else:
                    logger.warning(
                        "Intro video note: Telegram did not return ok binding=%s chat_id=%s result=%s",
                        binding.binding_id,
                        chat_id,
                        result,
                    )
            except Exception as exc:
                logger.warning(
                    "Intro video note failed binding=%s chat_id=%s: %s",
                    binding.binding_id,
                    chat_id,
                    exc,
                    exc_info=True,
                )
            await asyncio.sleep(3)

        await _send_telegram_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=welcome_text,
        )

    except Exception as exc:
        logger.error(
            "handle_restart failed for chat_id=%s binding=%s: %s",
            chat_id,
            binding.binding_id,
            exc,
            exc_info=True,
        )


async def handle_reminders(
    db: Any,
    chat_id: str,
    binding: ChannelBinding,
    bot_token: str,
) -> None:
    try:
        from app.services.telegram_reminder_flow import handle_command_entry
        await handle_command_entry(
            db=db, chat_id=chat_id, binding=binding, bot_token=bot_token
        )
    except Exception as exc:
        logger.error(
            "handle_reminders failed for chat_id=%s: %s",
            chat_id,
            exc,
            exc_info=True,
        )


async def handle_questionnaire(
    db: Any,
    chat_id: str,
    binding: ChannelBinding,
    bot_token: str,
) -> None:
    """Open the questionnaire main menu for the user."""
    try:
        from app.services.telegram_questionnaire_flow import handle_command as q_handle
        await q_handle(db=db, chat_id=chat_id, binding=binding, bot_token=bot_token)
    except Exception as exc:
        logger.error(
            "handle_questionnaire failed for chat_id=%s: %s",
            chat_id,
            exc,
            exc_info=True,
        )


async def handle_paysupport(
    db: Any,
    chat_id: str,
    binding: ChannelBinding,
    bot_token: str,
) -> None:
    """Handle /paysupport command: send payment support contact info."""
    try:
        from app.models.payment import get_payment_settings
        pay_settings = await get_payment_settings(binding.binding_id)
        contact = (pay_settings.support_contact if pay_settings else None) or "поддержку сервиса"
        await _send_telegram_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=(
                f"По вопросам оплаты напишите на {contact}. "
                "В письме укажите дату и сумму платежа — это ускорит проверку. 🙏"
            ),
        )
    except Exception as exc:
        logger.error("handle_paysupport failed for chat_id=%s: %s", chat_id, exc, exc_info=True)


_SUPPORT_PROJECT_PAYMENT_URL = (
    "https://qr.nspk.ru/AS1A00389H5IVAVP8GAA7G2Q5KM6946D"
    "?type=01&bank=100000000008&crc=3A25"
)
_SUPPORT_PROJECT_PAYMENT_URL_HTML_HREF = _SUPPORT_PROJECT_PAYMENT_URL.replace("&", "&amp;")

DEFAULT_SUPPORT_PROJECT_MESSAGE_HTML = (
    "Привет! Сейчас этот бот для тебя полностью бесплатный — мы рады помогать тебе и питомцу 🐾\n\n"
    "Если захочешь поддержать проект, нам будет очень приятно: это только по твоему желанию. "
    "Оплатить можно через QR (НСПК) — достаточно нажать на ссылку ниже.\n\n"
    f'<a href="{_SUPPORT_PROJECT_PAYMENT_URL_HTML_HREF}">Оплатить по QR-коду</a>'
)

DEFAULT_FEEDBACK_MESSAGE_HTML = (
    "Если нужно связаться со мной напрямую — напиши на почту, отвечу, как только смогу:\n\n"
    '<a href="mailto:Naumkina.t@inbox.ru">Naumkina.t@inbox.ru</a>'
)

_FALLBACK_CONFIGURED_COMMAND_TEXT = (
    "Текст этой команды ещё не настроен в админ-панели. "
    "Загляни позже или напиши нам в обычном чате — мы рядом 🙂"
)


def _has_custom_command_message(binding: ChannelBinding, cmd_key: str) -> bool:
    settings = _command_settings_map(binding).get(cmd_key) or {}
    raw = settings.get("message") if isinstance(settings, dict) else None
    return isinstance(raw, str) and bool(raw.strip())


def configured_reply_text(binding: ChannelBinding, cmd_key: str) -> str:
    """Resolved message body for supportproject / feedback (admin text or built-in default)."""
    settings = _command_settings_map(binding).get(cmd_key) or {}
    raw = settings.get("message") if isinstance(settings, dict) else None
    if isinstance(raw, str) and raw.strip():
        return raw.strip()[:TELEGRAM_COMMAND_MESSAGE_MAX]
    if cmd_key == "supportproject":
        return DEFAULT_SUPPORT_PROJECT_MESSAGE_HTML
    if cmd_key == "feedback":
        return DEFAULT_FEEDBACK_MESSAGE_HTML
    return _FALLBACK_CONFIGURED_COMMAND_TEXT


async def handle_supportproject(
    db: Any,
    chat_id: str,
    binding: ChannelBinding,
    bot_token: str,
) -> None:
    try:
        custom = _has_custom_command_message(binding, "supportproject")
        await _send_telegram_message(
            bot_token,
            chat_id,
            configured_reply_text(binding, "supportproject"),
            parse_mode=None if custom else "HTML",
        )
    except Exception as exc:
        logger.error(
            "handle_supportproject failed for chat_id=%s: %s",
            chat_id,
            exc,
            exc_info=True,
        )


async def handle_feedback(
    db: Any,
    chat_id: str,
    binding: ChannelBinding,
    bot_token: str,
) -> None:
    try:
        custom = _has_custom_command_message(binding, "feedback")
        await _send_telegram_message(
            bot_token,
            chat_id,
            configured_reply_text(binding, "feedback"),
            parse_mode=None if custom else "HTML",
        )
    except Exception as exc:
        logger.error(
            "handle_feedback failed for chat_id=%s: %s",
            chat_id,
            exc,
            exc_info=True,
        )


async def _send_telegram_message(
    bot_token: str,
    chat_id: str,
    text: str,
    *,
    parse_mode: Optional[str] = None,
) -> None:
    """Send a message to a Telegram chat (optionally HTML for default templates)."""
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    url = f"{TELEGRAM_API_BASE}{bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
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
    "paysupport": handle_paysupport,
    "questionnaire": handle_questionnaire,
    "reminders": handle_reminders,
    "supportproject": handle_supportproject,
    "feedback": handle_feedback,
}


async def dispatch_command(
    command: str,
    chat_id: str,
    binding: ChannelBinding,
    bot_token: str,
    db: Any,
) -> bool:
    """Try to handle a bot command.  Returns True if command was handled.

    Args:
        command: Raw command text, e.g. ``"/restart"`` or ``"/restart@mybot"``.
        chat_id: Telegram chat_id (string).
        binding: The ChannelBinding for this bot.
        bot_token: Bot access token.
        db: Database client.

    Returns:
        True if the command was recognised and handled; False otherwise.
    """
    # Strip the "/" prefix and any "@botname" suffix
    cmd_key = command.lstrip("/").split("@")[0].lower()

    # /start is a Telegram system command always sent when a user first opens the bot
    # or presses the Start button. Treat it as /restart unconditionally — no need to
    # configure it in telegram_commands.
    if cmd_key == "start":
        cmd_key = "restart"

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
        db=db,
        chat_id=chat_id,
        binding=binding,
        bot_token=bot_token,
    )
    return True
