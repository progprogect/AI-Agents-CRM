"""Tests for Telegram bot command metadata (supportproject / feedback)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.bot_commands_service import (
    CONFIGURABLE_COMMAND_KEYS,
    configured_reply_text,
    effective_menu_description,
    get_commands_status,
)


def test_configurable_keys_contains_expected() -> None:
    assert "supportproject" in CONFIGURABLE_COMMAND_KEYS
    assert "feedback" in CONFIGURABLE_COMMAND_KEYS


def test_effective_menu_description_override() -> None:
    binding = SimpleNamespace(
        metadata={
            "telegram_command_settings": {
                "feedback": {"menu_description": "Напишите нам"},
            }
        }
    )
    assert effective_menu_description(binding, "feedback") == "Напишите нам"


def test_effective_menu_description_default_from_catalog() -> None:
    binding = SimpleNamespace(metadata={})
    desc = effective_menu_description(binding, "feedback")
    assert "Обратная" in desc or "связь" in desc.lower()


def test_configured_reply_text_custom_message() -> None:
    binding = SimpleNamespace(
        metadata={
            "telegram_command_settings": {
                "supportproject": {"message": "Спасибо что поддерживаете нас!"},
            }
        }
    )
    assert configured_reply_text(binding, "supportproject").startswith("Спасибо")


def test_configured_reply_text_fallback_when_empty() -> None:
    binding = SimpleNamespace(metadata={})
    t = configured_reply_text(binding, "feedback").lower()
    assert "не настроен" in t or "админ" in t


def test_get_commands_status_includes_custom_fields() -> None:
    binding = SimpleNamespace(
        metadata={
            "telegram_commands": {"feedback": True},
            "telegram_command_settings": {
                "feedback": {"menu_description": "X", "message": "Y"},
            },
        }
    )
    rows = get_commands_status(binding)
    fb = next(r for r in rows if r["key"] == "feedback")
    assert fb["supports_custom_content"] is True
    assert fb["menu_description"] == "X"
    assert fb["message"] == "Y"
    assert fb["enabled"] is True
