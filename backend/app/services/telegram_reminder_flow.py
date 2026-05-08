"""Telegram UI + callbacks for user reminders wizard."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from zoneinfo import ZoneInfo

from app.models.channel_binding import ChannelBinding
from app.services import reminder_wizard_service as rw
from app.services.reminder_wizard_service import WizardMode, WizardState
from app.storage import postgres_user_reminders as ur_repo
from app.services.reminder_time_parse import parse_user_datetime_moscow
from app.services.user_reminder_scheduler import dequeue_user_reminder, enqueue_user_reminder
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

MAX_ACTIVE_REMINDERS_PER_USER = 10

# callback_data — prefix r:
CB_CANCEL_WIZARD = "r:z"
CB_LIST = "r:l"
CB_SKIP_NOTE = "r:s"

CB_CAT_V = "r:c:v"
CB_CAT_T = "r:c:t"
CB_CAT_F = "r:c:f"
CB_CAT_O = "r:c:o"

CB_KIND_ONCE = "r:k:o"
CB_KIND_REC = "r:k:r"

CB_ONCE_1H = "r:p:1"
CB_ONCE_TOM = "r:p:2"
CB_ONCE_7D = "r:p:3"
CB_ONCE_CUSTOM = "r:p:9"

CB_REC_D = "r:q:1"
CB_REC_W = "r:q:2"
CB_REC_3D = "r:q:3"

CB_CANCEL_IDX_PREFIX = "r:i:"

CATEGORY_MAP = {
    CB_CAT_V: "vaccination",
    CB_CAT_T: "treatment",
    CB_CAT_F: "food_order",
    CB_CAT_O: "other",
}

LABEL_RU = {
    "vaccination": "Прививка",
    "treatment": "Обработка",
    "food_order": "Заказ корма",
    "other": "Другое",
}


def is_reminder_callback(data: str) -> bool:
    return bool(data) and data.startswith("r:")


def _fmt_short_msk(dt: datetime) -> str:
    """Показать то же мгновение в МСК для пользователя."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M МСК")


CUSTOM_TIME_HELP_TEXT = (
    "Напиши одним сообщением, когда напомнить.\n\n"
    "Время и дату воспринимаю как московские (МСК) — как обычные часы в Москве.\n\n"
    "Примеры формата:\n"
    "• 25.05.2026 14:30 или 25.05.2026 в 14:30\n"
    "• только дату: 25.05.2026 — тогда возьму 10:00 МСК\n"
    "• по-русски: завтра в 15:00, 15 мая в 10 утра, через 3 дня в 12:00\n\n"
    "Если что-то не так распознается — переформулируй, и попробуем ещё раз 😊"
)

CUSTOM_TIME_ERR_EMPTY = (
    "Пока не вижу дату и время 😊 Напиши одним сообщением, например: "
    "25.05.2026 14:30 или «завтра в 15:00». Всё время считаю по московскому (МСК)."
)

CUSTOM_TIME_ERR_UNPARSED = (
    "Не получилось разобрать формат — давай ещё раз, спокойно и по шагам 🙂 "
    "Можно так: 25.05.2026 14:30, или своими словами: «через 2 дня в 10 утра». "
    "Дата и время всегда в московском времени (МСК)."
)

CUSTOM_TIME_ERR_PAST = (
    "Это время уже прошло относительно «сейчас». Выбери момент в будущем — "
    "например «завтра в 12:00» или конкретную дату. Всё по МСК."
)


async def _send_custom_time_prompt(bot_token: str, chat_id: str) -> None:
    await _send(
        bot_token,
        chat_id,
        CUSTOM_TIME_HELP_TEXT,
        inline_keyboard=[
            [{"text": "Отмена", "callback_data": CB_CANCEL_WIZARD}],
        ],
    )


def next_fire_once_1h() -> datetime:
    return utc_now() + timedelta(hours=1)


def next_fire_tomorrow_10_moscow() -> datetime:
    msk = ZoneInfo("Europe/Moscow")
    now_local = datetime.now(msk)
    target = now_local.replace(hour=10, minute=0, second=0, microsecond=0)
    if target <= now_local:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc)


def next_fire_plus_days(days: int) -> datetime:
    return utc_now() + timedelta(days=days)


async def _send(
    bot_token: str,
    chat_id: str,
    text: str,
    *,
    inline_keyboard: Optional[list[list[dict[str, str]]]] = None,
) -> None:
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if inline_keyboard:
        payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
    url = f"{TELEGRAM_API_BASE}{bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            if not data.get("ok"):
                logger.warning("reminder flow sendMessage not ok: %s", data)
    except Exception as exc:
        logger.error("reminder flow send failed: %s", exc, exc_info=True)


def _main_keyboard() -> list[list[dict[str, str]]]:
    return [
        [
            {"text": "Прививка", "callback_data": CB_CAT_V},
            {"text": "Обработка", "callback_data": CB_CAT_T},
        ],
        [
            {"text": "Заказ корма", "callback_data": CB_CAT_F},
            {"text": "Другое", "callback_data": CB_CAT_O},
        ],
        [
            {"text": "Мои напоминания", "callback_data": CB_LIST},
            {"text": "Отмена", "callback_data": CB_CANCEL_WIZARD},
        ],
    ]


async def handle_command_entry(
    *,
    db: Any,
    chat_id: str,
    binding: ChannelBinding,
    bot_token: str,
) -> None:
    """Entry from /reminders — block if questionnaire is filling."""
    try:
        from app.services.questionnaire_service import load_fsm as q_load_fsm

        qst = await q_load_fsm(binding.binding_id, chat_id)
        if qst is not None and qst.mode.value in ("fill", "edit_field"):
            await _send(
                bot_token,
                chat_id,
                "Сначала завершите анкету или отмените её (/questionnaire — отмена в меню), "
                "потом можно настроить напоминания.",
            )
            return
    except Exception as exc:
        logger.debug("reminder entry questionnaire check: %s", exc)

    await rw.open_menu(binding.binding_id, chat_id)
    intro = (
        "Напоминания 🔔\n\n"
        "Если хочешь, чтобы я напомнила тебе о чём-то важном — давай настроим это вместе 😊\n"
        "Выбери тему кнопкой ниже, потом — разовое или регулярное напоминание и удобное время. "
        "На последнем шаге можешь своими словами написать, о чём именно не забыть — это попадёт в напоминание.\n\n"
        "О чём тебе напомнить? Выбери тип:"
    )
    await _send(
        bot_token,
        chat_id,
        intro,
        inline_keyboard=_main_keyboard(),
    )


async def handle_callback_query(
    *,
    db: Any,
    query: dict[str, Any],
    binding: ChannelBinding,
    bot_token: str,
) -> None:
    data = str(query.get("data") or "")
    chat_id = str((query.get("from") or {}).get("id", ""))
    if not chat_id:
        return

    if data == CB_CANCEL_WIZARD:
        await rw.clear_wizard(binding.binding_id, chat_id)
        await _send(
            bot_token,
            chat_id,
            "Хорошо 😊 Настройку напоминания закрыла.\n\n"
            "Можем продолжить общение — чем я могу тебе помочь?",
        )
        return

    if data == CB_LIST:
        rows = await ur_repo.list_active_for_user(binding.binding_id, chat_id)
        if not rows:
            await _send(bot_token, chat_id, "Активных напоминаний нет.")
            return
        lines = []
        ids: list[str] = []
        for i, r in enumerate(rows[:8]):
            label = LABEL_RU.get(r.category, r.category)
            lines.append(f"{i + 1}. {label} — {_fmt_short_msk(r.next_fire_at)}")
            ids.append(r.reminder_id)
        st = await rw.load_wizard(binding.binding_id, chat_id) or WizardState(
            binding_id=binding.binding_id,
            external_user_id=chat_id,
            mode=WizardMode.LIST_PICK_CANCEL,
        )
        st.mode = WizardMode.LIST_PICK_CANCEL
        st.list_reminder_ids = ids
        await rw.save_wizard(st)
        kb: list[list[dict[str, str]]] = []
        for i in range(len(ids)):
            kb.append(
                [{"text": f"Отменить №{i + 1}", "callback_data": f"{CB_CANCEL_IDX_PREFIX}{i}"}]
            )
        kb.append([{"text": "Закрыть", "callback_data": CB_CANCEL_WIZARD}])
        await _send(
            bot_token,
            chat_id,
            "Ваши напоминания:\n\n" + "\n".join(lines) + "\n\nНажмите, чтобы отменить:",
            inline_keyboard=kb,
        )
        return

    if data.startswith(CB_CANCEL_IDX_PREFIX):
        idx_s = data[len(CB_CANCEL_IDX_PREFIX) :]
        try:
            idx = int(idx_s)
        except ValueError:
            return
        st = await rw.load_wizard(binding.binding_id, chat_id)
        if (
            st is None
            or st.mode != WizardMode.LIST_PICK_CANCEL
            or idx < 0
            or idx >= len(st.list_reminder_ids)
        ):
            await _send(bot_token, chat_id, "Список устарел. Откройте «Мои напоминания» снова.")
            return
        rid = st.list_reminder_ids[idx]
        ok = await ur_repo.cancel_reminder(rid, binding.binding_id, chat_id)
        if ok:
            await dequeue_user_reminder(rid)
        await rw.clear_wizard(binding.binding_id, chat_id)
        await _send(
            bot_token,
            chat_id,
            "Напоминание отменено." if ok else "Не удалось отменить (уже удалено?).",
        )
        return

    st = await rw.load_wizard(binding.binding_id, chat_id)
    if st is None:
        await rw.open_menu(binding.binding_id, chat_id)
        st = await rw.load_wizard(binding.binding_id, chat_id)

    if data in CATEGORY_MAP:
        if st:
            st.category = CATEGORY_MAP[data]
            st.mode = WizardMode.SCHEDULE_KIND
            st.schedule_kind = None
            await rw.save_wizard(st)
        cat_label = LABEL_RU.get(st.category if st else "", "")
        await _send(
            bot_token,
            chat_id,
            f"Тип: {cat_label}\n\nРазовое или регулярное?",
            inline_keyboard=[
                [
                    {"text": "Разовое", "callback_data": CB_KIND_ONCE},
                    {"text": "Регулярное", "callback_data": CB_KIND_REC},
                ],
                [{"text": "Назад", "callback_data": CB_CANCEL_WIZARD}],
            ],
        )
        return

    if data in (CB_KIND_ONCE, CB_KIND_REC):
        if not st or not st.category:
            await handle_command_entry(db=db, chat_id=chat_id, binding=binding, bot_token=bot_token)
            return
        st.schedule_kind = "once" if data == CB_KIND_ONCE else "recurring"
        if st.schedule_kind == "once":
            st.mode = WizardMode.ONCE_PRESET
        else:
            st.mode = WizardMode.RECURRING_PRESET
        await rw.save_wizard(st)
        if st.schedule_kind == "once":
            await _send(
                bot_token,
                chat_id,
                "Когда напомнить?",
                inline_keyboard=[
                    [
                        {"text": "Через 1 час", "callback_data": CB_ONCE_1H},
                        {"text": "Завтра 10:00 (МСК)", "callback_data": CB_ONCE_TOM},
                    ],
                    [{"text": "Через 7 дней", "callback_data": CB_ONCE_7D}],
                    [{"text": "Своё время (текстом)", "callback_data": CB_ONCE_CUSTOM}],
                    [{"text": "Отмена", "callback_data": CB_CANCEL_WIZARD}],
                ],
            )
        else:
            await _send(
                bot_token,
                chat_id,
                "Как часто?",
                inline_keyboard=[
                    [
                        {"text": "Каждый день", "callback_data": CB_REC_D},
                        {"text": "Раз в неделю", "callback_data": CB_REC_W},
                    ],
                    [{"text": "Раз в 3 дня", "callback_data": CB_REC_3D}],
                    [{"text": "Отмена", "callback_data": CB_CANCEL_WIZARD}],
                ],
            )
        return

    once_map = {
        CB_ONCE_1H: (next_fire_once_1h, {"preset": "1h"}),
        CB_ONCE_TOM: (next_fire_tomorrow_10_moscow, {"preset": "tomorrow_10_msk"}),
        CB_ONCE_7D: (lambda: next_fire_plus_days(7), {"preset": "7d"}),
    }
    if data in once_map:
        if not st or not st.category or st.schedule_kind != "once":
            await handle_command_entry(db=db, chat_id=chat_id, binding=binding, bot_token=bot_token)
            return
        nf_fn, spec_extra = once_map[data]
        next_fire = nf_fn()
        st.mode = WizardMode.NOTE
        st.next_fire_iso = next_fire.isoformat()
        st.pending_schedule_spec = spec_extra if isinstance(spec_extra, dict) else {}
        await rw.save_wizard(st)
        await _send(
            bot_token,
            chat_id,
            "Напишите, о чём напомнить (или нажмите «Пропустить»).",
            inline_keyboard=[
                [{"text": "Пропустить", "callback_data": CB_SKIP_NOTE}],
                [{"text": "Отмена", "callback_data": CB_CANCEL_WIZARD}],
            ],
        )
        return

    if data == CB_ONCE_CUSTOM:
        if not st or not st.category or st.schedule_kind != "once":
            await handle_command_entry(db=db, chat_id=chat_id, binding=binding, bot_token=bot_token)
            return
        st.mode = WizardMode.ONCE_CUSTOM_TIME
        await rw.save_wizard(st)
        await _send_custom_time_prompt(bot_token, chat_id)
        return

    rec_map = {
        CB_REC_D: 86400,
        CB_REC_W: 604800,
        CB_REC_3D: 259200,
    }
    if data in rec_map:
        if not st or not st.category or st.schedule_kind != "recurring":
            await handle_command_entry(db=db, chat_id=chat_id, binding=binding, bot_token=bot_token)
            return
        interval = rec_map[data]
        next_fire = utc_now() + timedelta(seconds=interval)
        st.mode = WizardMode.NOTE
        st.next_fire_iso = next_fire.isoformat()
        st.pending_schedule_spec = {"interval_seconds": interval}
        await rw.save_wizard(st)
        await _send(
            bot_token,
            chat_id,
            "Напишите, о чём напомнить (или нажмите «Пропустить»).",
            inline_keyboard=[
                [{"text": "Пропустить", "callback_data": CB_SKIP_NOTE}],
                [{"text": "Отмена", "callback_data": CB_CANCEL_WIZARD}],
            ],
        )
        return

    if data == CB_SKIP_NOTE:
        await _finalize_reminder(
            db=db,
            binding=binding,
            chat_id=chat_id,
            bot_token=bot_token,
            user_note="",
        )
        return


async def handle_user_message(
    *,
    db: Any,
    chat_id: str,
    binding: ChannelBinding,
    bot_token: str,
    text: str,
) -> None:
    st = await rw.load_wizard(binding.binding_id, chat_id)
    if st is None:
        return
    if st.mode == WizardMode.ONCE_CUSTOM_TIME:
        utc_dt, err = parse_user_datetime_moscow(text.strip())
        if err == "empty":
            await _send(bot_token, chat_id, CUSTOM_TIME_ERR_EMPTY)
            return
        if err == "unparsed":
            await _send(bot_token, chat_id, CUSTOM_TIME_ERR_UNPARSED)
            return
        if err == "past":
            await _send(bot_token, chat_id, CUSTOM_TIME_ERR_PAST)
            return
        if utc_dt is None:
            await _send(bot_token, chat_id, CUSTOM_TIME_ERR_UNPARSED)
            return
        st.mode = WizardMode.NOTE
        st.next_fire_iso = utc_dt.isoformat()
        raw_note = text.strip()
        st.pending_schedule_spec = {"preset": "custom_text", "user_input": raw_note[:500]}
        await rw.save_wizard(st)
        await _send(
            bot_token,
            chat_id,
            f"Отлично, напомню {_fmt_short_msk(utc_dt)} 🙂\n\n"
            "Напишите, о чём напомнить (или нажмите «Пропустить»).",
            inline_keyboard=[
                [{"text": "Пропустить", "callback_data": CB_SKIP_NOTE}],
                [{"text": "Отмена", "callback_data": CB_CANCEL_WIZARD}],
            ],
        )
        return
    if st.mode != WizardMode.NOTE:
        return
    await _finalize_reminder(
        db=db,
        binding=binding,
        chat_id=chat_id,
        bot_token=bot_token,
        user_note=text.strip()[:2000],
    )


async def _finalize_reminder(
    *,
    db: Any,
    binding: ChannelBinding,
    chat_id: str,
    bot_token: str,
    user_note: str,
) -> None:
    st = await rw.load_wizard(binding.binding_id, chat_id)
    if st is None or st.mode != WizardMode.NOTE:
        await _send(bot_token, chat_id, "Сессия устарела. Начните снова: /reminders")
        await rw.clear_wizard(binding.binding_id, chat_id)
        return

    next_iso = st.next_fire_iso
    spec_extra = st.pending_schedule_spec or {}
    cat = st.category
    skind = st.schedule_kind
    if not next_iso or not cat or not skind:
        await rw.clear_wizard(binding.binding_id, chat_id)
        await _send(bot_token, chat_id, "Не удалось сохранить. Попробуйте снова.")
        return

    if await ur_repo.count_active_for_user(binding.binding_id, chat_id) >= MAX_ACTIVE_REMINDERS_PER_USER:
        await rw.clear_wizard(binding.binding_id, chat_id)
        await _send(
            bot_token,
            chat_id,
            f"Слишком много активных напоминаний (макс. {MAX_ACTIVE_REMINDERS_PER_USER}). "
            "Отмените лишние в «Мои напоминания».",
        )
        return

    next_fire = datetime.fromisoformat(next_iso.replace("Z", "+00:00"))
    if next_fire.tzinfo is None:
        next_fire = next_fire.replace(tzinfo=timezone.utc)

    if skind == "once":
        spec_dict = spec_extra if isinstance(spec_extra, dict) else {}
        reminder = await ur_repo.create_reminder(
            agent_id=binding.agent_id,
            binding_id=binding.binding_id,
            external_user_id=chat_id,
            category=cat,
            schedule_kind="once",
            schedule_spec=spec_dict,
            user_note=user_note,
            next_fire_at=next_fire,
        )
    else:
        interval = int((spec_extra or {}).get("interval_seconds") or 86400)
        reminder = await ur_repo.create_reminder(
            agent_id=binding.agent_id,
            binding_id=binding.binding_id,
            external_user_id=chat_id,
            category=cat,
            schedule_kind="recurring",
            schedule_spec={"interval_seconds": interval},
            user_note=user_note,
            next_fire_at=next_fire,
        )

    await enqueue_user_reminder(reminder.reminder_id, reminder.next_fire_at)
    await rw.clear_wizard(binding.binding_id, chat_id)
    await _send(
        bot_token,
        chat_id,
        "Готово! ✨\n\n"
        f"Напоминание «{LABEL_RU.get(cat, cat)}» настроено — ближайшее: {_fmt_short_msk(reminder.next_fire_at)}.\n\n"
        "Можем продолжить общение 😊 Чем я могу тебе помочь?",
    )
