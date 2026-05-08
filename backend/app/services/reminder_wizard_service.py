"""Redis-backed wizard state for /reminders Telegram flow."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.storage.redis import get_redis_client

logger = logging.getLogger(__name__)

FSM_KEY_PREFIX = "reminder_wizard_fsm:"
FSM_TTL_SECONDS = 30 * 60


class WizardMode(str, Enum):
    IDLE = "idle"
    MENU = "menu"
    SCHEDULE_KIND = "schedule_kind"
    ONCE_PRESET = "once_preset"
    RECURRING_PRESET = "recurring_preset"
    NOTE = "note"
    LIST_PICK_CANCEL = "list_pick_cancel"


@dataclass
class WizardState:
    binding_id: str
    external_user_id: str
    mode: WizardMode
    category: Optional[str] = None
    schedule_kind: Optional[str] = None
    list_reminder_ids: list[str] = field(default_factory=list)
    next_fire_iso: Optional[str] = None
    pending_schedule_spec: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "category": self.category,
            "schedule_kind": self.schedule_kind,
            "list_reminder_ids": self.list_reminder_ids,
            "next_fire_iso": self.next_fire_iso,
            "pending_schedule_spec": self.pending_schedule_spec,
        }

    @classmethod
    def from_dict(cls, binding_id: str, external_user_id: str, data: dict) -> "WizardState":
        ids = data.get("list_reminder_ids") or []
        if not isinstance(ids, list):
            ids = []
        ps = data.get("pending_schedule_spec")
        if ps is not None and not isinstance(ps, dict):
            ps = None
        return cls(
            binding_id=binding_id,
            external_user_id=external_user_id,
            mode=WizardMode(data.get("mode", WizardMode.IDLE.value)),
            category=data.get("category"),
            schedule_kind=data.get("schedule_kind"),
            list_reminder_ids=[str(x) for x in ids],
            next_fire_iso=data.get("next_fire_iso"),
            pending_schedule_spec=ps,
        )


def _key(binding_id: str, external_user_id: str) -> str:
    return f"{FSM_KEY_PREFIX}{binding_id}:{external_user_id}"


async def load_wizard(binding_id: str, external_user_id: str) -> Optional[WizardState]:
    redis = get_redis_client()
    try:
        data = await redis.get_json(_key(binding_id, external_user_id))
    except Exception as exc:
        logger.debug("reminder wizard load error: %s", exc)
        return None
    if not data:
        return None
    return WizardState.from_dict(binding_id, external_user_id, data)


async def save_wizard(state: WizardState) -> None:
    redis = get_redis_client()
    try:
        await redis.set_json(
            _key(state.binding_id, state.external_user_id),
            state.to_dict(),
            ttl=FSM_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning("reminder wizard save error: %s", exc)


async def clear_wizard(binding_id: str, external_user_id: str) -> None:
    redis = get_redis_client()
    try:
        await redis.delete(_key(binding_id, external_user_id))
    except Exception as exc:
        logger.debug("reminder wizard clear error: %s", exc)


async def open_menu(binding_id: str, external_user_id: str) -> WizardState:
    st = WizardState(
        binding_id=binding_id,
        external_user_id=external_user_id,
        mode=WizardMode.MENU,
    )
    await save_wizard(st)
    return st
