"""Telegram-specific flow for the questionnaire feature.

Responsibilities:
- Render the main menu (fill / edit / view) via inline keyboards.
- Render one field prompt at a time with optional quick-reply inline buttons.
- React to callback_query values with the ``q:*`` prefix.
- Interpret free-text messages as the answer to the field under the cursor.

State lives in Redis (see ``questionnaire_service``); this module only formats
messages and decides what to do next given a state + user input.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.models.channel_binding import ChannelBinding
from app.models.questionnaire import QuestionnaireField, QuestionnaireTemplate
from app.services import questionnaire_service as qs
from app.services.questionnaire_service import FsmMode, FsmState

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

# ── callback_data schema ───────────────────────────────────────────────────
#
# Telegram caps callback_data at 64 bytes.  We use very short prefixes and the
# field_key (≤30 chars, ASCII) or a quick-reply index.
#
# q:s            — start fill
# q:e            — open edit menu
# q:ef:<key>     — start editing a single field
# q:a:<idx>      — user picked quick-reply #idx on the current pending field
# q:skip         — skip current field (non-required)
# q:cancel       — cancel the session
# q:view         — show current values
# q:back         — return to the main menu

CB_START = "q:s"
CB_EDIT_MENU = "q:e"
CB_EDIT_FIELD_PREFIX = "q:ef:"
CB_ANSWER_PREFIX = "q:a:"
CB_SKIP = "q:skip"
CB_CANCEL = "q:cancel"
CB_VIEW = "q:view"
CB_BACK = "q:back"


def is_questionnaire_callback(data: str) -> bool:
    return bool(data) and data.startswith("q:")


# ── Telegram helpers ───────────────────────────────────────────────────────


async def _send(
    bot_token: str,
    chat_id: str,
    text: str,
    *,
    inline_keyboard: Optional[list[list[dict]]] = None,
) -> None:
    body: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if inline_keyboard:
        body["reply_markup"] = {"inline_keyboard": inline_keyboard}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{TELEGRAM_API_BASE}{bot_token}/sendMessage", json=body
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning("questionnaire sendMessage not-ok: %s", data)
    except Exception as exc:
        logger.error("questionnaire sendMessage failed: %s", exc)


# ── Rendering ──────────────────────────────────────────────────────────────


def _render_menu(template: QuestionnaireTemplate, has_values: bool) -> tuple[str, list[list[dict]]]:
    greeting = template.welcome_message.strip() or (
        "Привет! Это небольшая анкета, чтобы я лучше понимал ваш запрос. "
        "Отвечайте на вопросы, каждый ответ сохраняется автоматически."
    )
    buttons: list[list[dict]] = []
    if has_values:
        buttons.append([{"text": "✏️ Редактировать анкету", "callback_data": CB_EDIT_MENU}])
        buttons.append([{"text": "🔁 Пройти заново", "callback_data": CB_START}])
        buttons.append([{"text": "👀 Посмотреть мои ответы", "callback_data": CB_VIEW}])
    else:
        buttons.append([{"text": "📝 Заполнить анкету", "callback_data": CB_START}])
    buttons.append([{"text": "✖️ Отмена", "callback_data": CB_CANCEL}])
    return greeting, buttons


def _render_field_prompt(
    template: QuestionnaireTemplate,
    field: QuestionnaireField,
    *,
    progress: Optional[str] = None,
    allow_skip: bool = True,
) -> tuple[str, list[list[dict]]]:
    header = progress + "\n\n" if progress else ""
    text = f"{header}{field.question}".strip()
    if not field.required:
        text += "\n\n_необязательное поле_"

    buttons: list[list[dict]] = []
    # Quick replies as inline buttons, one per row for legibility.
    for idx, qr in enumerate(field.quick_replies):
        buttons.append([{"text": qr, "callback_data": f"{CB_ANSWER_PREFIX}{idx}"}])

    footer_row: list[dict] = []
    if allow_skip and not field.required:
        footer_row.append({"text": "⏭ Пропустить", "callback_data": CB_SKIP})
    footer_row.append({"text": "✖️ Отмена", "callback_data": CB_CANCEL})
    buttons.append(footer_row)
    return text, buttons


def _render_edit_menu(
    template: QuestionnaireTemplate, values: dict[str, str]
) -> tuple[str, list[list[dict]]]:
    lines = ["Выберите, что отредактировать:"]
    buttons: list[list[dict]] = []
    for f in template.fields:
        current = values.get(f.key)
        label = f.label
        if current:
            short = current if len(current) <= 30 else current[:27] + "…"
            label = f"{f.label}: {short}"
        buttons.append([{"text": label, "callback_data": f"{CB_EDIT_FIELD_PREFIX}{f.key}"}])
    buttons.append([{"text": "🔁 Пройти заново", "callback_data": CB_START}])
    buttons.append([{"text": "⬅ Назад", "callback_data": CB_BACK}])
    buttons.append([{"text": "✖️ Отмена", "callback_data": CB_CANCEL}])
    return "\n".join(lines), buttons


def _render_values(template: QuestionnaireTemplate, values: dict[str, str]) -> str:
    if not values:
        return "Анкета пока пустая."
    lines = ["Ваши ответы сейчас:"]
    for f in template.fields:
        if f.key in values:
            lines.append(f"• {f.label}: {values[f.key]}")
    # Include values whose field was removed from the template so nothing is hidden.
    known_keys = {f.key for f in template.fields}
    extras = [k for k in values.keys() if k not in known_keys]
    if extras:
        lines.append("")
        lines.append("Устаревшие поля:")
        for k in extras:
            lines.append(f"• {k}: {values[k]}")
    return "\n".join(lines)


# ── Public entry points ────────────────────────────────────────────────────


async def handle_command(
    *,
    db: Any,
    chat_id: str,
    binding: ChannelBinding,
    bot_token: str,
) -> None:
    """Telegram /questionnaire command — opens the main menu."""
    template = await qs.get_template_or_empty(binding.agent_id)
    if not template.fields:
        await _send(
            bot_token,
            chat_id,
            "Анкета ещё не настроена администратором. Вернитесь позже.",
        )
        return

    values = await qs.get_current_values(binding.agent_id, chat_id)
    await qs.open_menu(binding.binding_id, chat_id)
    text, keyboard = _render_menu(template, has_values=bool(values))
    await _send(bot_token, chat_id, text, inline_keyboard=keyboard)


async def handle_callback_query(
    *,
    db: Any,
    query: dict[str, Any],
    binding: ChannelBinding,
    bot_token: str,
) -> None:
    data: str = query.get("data", "")
    from_user = query.get("from") or {}
    chat_id = str(from_user.get("id", ""))

    if not chat_id or not data:
        return

    # answerCallbackQuery is always called by telegram_service._handle_callback_query
    # before routing here, so we do NOT repeat it.

    state = await qs.load_fsm(binding.binding_id, chat_id)
    template = await qs.get_template_or_empty(binding.agent_id)

    if data == CB_CANCEL:
        if state:
            await qs.cancel(state)
        await _send(bot_token, chat_id, "Сессия анкеты завершена. Можно вернуться командой /questionnaire.")
        return

    if data == CB_BACK or (data == CB_VIEW and not state):
        # Re-open main menu (from edit menu, or when viewing after a cold start)
        if not template.fields:
            await _send(bot_token, chat_id, "Анкета ещё не настроена администратором.")
            return
        values = await qs.get_current_values(binding.agent_id, chat_id)
        state = await qs.open_menu(binding.binding_id, chat_id)
        text, keyboard = _render_menu(template, has_values=bool(values))
        await _send(bot_token, chat_id, text, inline_keyboard=keyboard)
        return

    if data == CB_VIEW:
        values = await qs.get_current_values(binding.agent_id, chat_id)
        await _send(bot_token, chat_id, _render_values(template, values))
        # Keep the user in the main menu so they can act next.
        text, keyboard = _render_menu(template, has_values=bool(values))
        await _send(bot_token, chat_id, text, inline_keyboard=keyboard)
        return

    if data == CB_START:
        if not template.fields:
            await _send(bot_token, chat_id, "Анкета ещё не настроена администратором.")
            return
        new_state, _ = await qs.start_fill(
            binding_id=binding.binding_id,
            agent_id=binding.agent_id,
            external_user_id=chat_id,
            channel="telegram",
        )
        await _ask_current_field(bot_token, chat_id, template, new_state)
        return

    if data == CB_EDIT_MENU:
        values = await qs.get_current_values(binding.agent_id, chat_id)
        if not state:
            state = await qs.open_menu(binding.binding_id, chat_id)
        state = await qs.switch_to_edit_menu(state)
        text, keyboard = _render_edit_menu(template, values)
        await _send(bot_token, chat_id, text, inline_keyboard=keyboard)
        return

    if data.startswith(CB_EDIT_FIELD_PREFIX):
        field_key = data[len(CB_EDIT_FIELD_PREFIX):]
        field = qs.find_field(template, field_key)
        if not field:
            await _send(bot_token, chat_id, "Это поле больше не доступно для редактирования.")
            return
        if not state:
            state = await qs.open_menu(binding.binding_id, chat_id)
        new_state, _ = await qs.start_edit_field(
            state=state,
            agent_id=binding.agent_id,
            field_key=field_key,
            channel="telegram",
        )
        text, keyboard = _render_field_prompt(template, field, allow_skip=False)
        await _send(bot_token, chat_id, text, inline_keyboard=keyboard)
        return

    if data == CB_SKIP:
        if not state or state.mode != FsmMode.FILL:
            return
        new_state, completed = await qs.skip_current(state=state, template=template)
        if completed:
            await _finish_message(bot_token, chat_id, template, binding.agent_id)
        else:
            await _ask_current_field(bot_token, chat_id, template, new_state)
        return

    if data.startswith(CB_ANSWER_PREFIX):
        # User tapped a quick-reply inline button.
        if not state:
            return
        field = _current_field(template, state)
        if not field:
            return
        try:
            idx = int(data[len(CB_ANSWER_PREFIX):])
        except ValueError:
            return
        if idx < 0 or idx >= len(field.quick_replies):
            return
        value = field.quick_replies[idx]
        await _apply_answer(bot_token, chat_id, binding.agent_id, template, state, value)
        return


async def handle_user_message(
    *,
    db: Any,
    chat_id: str,
    binding: ChannelBinding,
    bot_token: str,
    text: str,
) -> bool:
    """Route a free-text message as the answer for the current field.

    Returns True if the message was consumed by the questionnaire flow and
    the agent pipeline should be skipped.  False when there is no active FSM
    or the FSM is idle/menu (caller keeps normal processing).
    """
    state = await qs.load_fsm(binding.binding_id, chat_id)
    if not state or state.mode not in (FsmMode.FILL, FsmMode.EDIT_FIELD):
        return False

    template = await qs.get_template_or_empty(binding.agent_id)
    value = (text or "").strip()
    if not value:
        return True  # silently ignore empty input but stay in FSM

    await _apply_answer(bot_token, chat_id, binding.agent_id, template, state, value)
    return True


# ── Internals ──────────────────────────────────────────────────────────────


def _current_field(template: QuestionnaireTemplate, state: FsmState) -> Optional[QuestionnaireField]:
    if state.mode == FsmMode.FILL:
        if 0 <= state.cursor < len(template.fields):
            return template.fields[state.cursor]
        return None
    if state.mode == FsmMode.EDIT_FIELD and state.pending_field_key:
        return qs.find_field(template, state.pending_field_key)
    return None


async def _ask_current_field(
    bot_token: str,
    chat_id: str,
    template: QuestionnaireTemplate,
    state: FsmState,
) -> None:
    field = _current_field(template, state)
    if not field:
        await _send(bot_token, chat_id, "Не удалось определить следующий вопрос анкеты.")
        return
    progress = None
    if state.mode == FsmMode.FILL and template.fields:
        progress = f"Шаг {state.cursor + 1} из {len(template.fields)}"
    text, keyboard = _render_field_prompt(
        template,
        field,
        progress=progress,
        allow_skip=(state.mode == FsmMode.FILL),
    )
    await _send(bot_token, chat_id, text, inline_keyboard=keyboard)


async def _apply_answer(
    bot_token: str,
    chat_id: str,
    agent_id: str,
    template: QuestionnaireTemplate,
    state: FsmState,
    value: str,
) -> None:
    try:
        new_state, completed = await qs.submit_answer(
            state=state, agent_id=agent_id, template=template, value=value
        )
    except Exception as exc:
        logger.error("submit_answer failed: %s", exc, exc_info=True)
        await _send(bot_token, chat_id, "Не удалось сохранить ответ. Попробуйте ещё раз.")
        return

    if new_state.mode == FsmMode.FILL:
        await _ask_current_field(bot_token, chat_id, template, new_state)
        return

    if new_state.mode == FsmMode.EDIT_MENU:
        # Single-field edit complete → bring the user back to the edit menu.
        values = await qs.get_current_values(agent_id, chat_id)
        text, keyboard = _render_edit_menu(template, values)
        await _send(bot_token, chat_id, "Готово, сохранил.", inline_keyboard=None)
        await _send(bot_token, chat_id, text, inline_keyboard=keyboard)
        return

    if completed and new_state.mode == FsmMode.MENU:
        await _finish_message(bot_token, chat_id, template, agent_id)


async def _finish_message(
    bot_token: str,
    chat_id: str,
    template: QuestionnaireTemplate,
    agent_id: str,
) -> None:
    values = await qs.get_current_values(agent_id, chat_id)
    summary = _render_values(template, values)
    base_text = (template.completion_message.strip() or "Спасибо, анкета сохранена!")
    buttons: list[list[dict]] = [
        [{"text": "✏️ Редактировать", "callback_data": CB_EDIT_MENU}],
        [{"text": "✖️ Закрыть", "callback_data": CB_CANCEL}],
    ]
    await _send(
        bot_token,
        chat_id,
        f"{base_text}\n\n{summary}",
        inline_keyboard=buttons,
    )
