"""Tests for Moscow-local reminder datetime parsing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.reminder_time_parse import parse_user_datetime_moscow


def test_numeric_date_time_moscow() -> None:
    now = datetime(2026, 5, 7, 10, 0, 0, tzinfo=timezone.utc)
    utc, err = parse_user_datetime_moscow("25.05.2026 14:30", now_utc=now)
    assert err is None
    assert utc is not None
    # 14:30 MSK May = UTC+3 → 11:30 UTC
    assert utc.hour == 11 and utc.minute == 30


def test_numeric_date_time_with_v() -> None:
    now = datetime(2026, 5, 7, 10, 0, 0, tzinfo=timezone.utc)
    utc, err = parse_user_datetime_moscow("25.05.2026 в 14:30", now_utc=now)
    assert err is None
    assert utc is not None
    assert utc.hour == 11 and utc.minute == 30


def test_date_only_defaults_10_msk() -> None:
    now = datetime(2026, 5, 7, 10, 0, 0, tzinfo=timezone.utc)
    utc, err = parse_user_datetime_moscow("25.05.2026", now_utc=now)
    assert err is None
    assert utc is not None
    assert utc.hour == 7 and utc.minute == 0  # 10:00 MSK → 07:00 UTC


def test_empty_short_input() -> None:
    utc, err = parse_user_datetime_moscow("", now_utc=datetime.now(timezone.utc))
    assert utc is None and err == "empty"


def test_gibberish_unparsed() -> None:
    utc, err = parse_user_datetime_moscow(
        "ыфвафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафывафыva",
        now_utc=datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert utc is None and err == "unparsed"


def test_past_datetime() -> None:
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    utc, err = parse_user_datetime_moscow("01.01.2020 10:00", now_utc=now)
    assert utc is None and err == "past"


@pytest.mark.parametrize(
    "phrase",
    [
        "завтра в 15:00",
        "15 мая 2026 в 10:00",
        "через 3 дня в 12:00",
    ],
)
def test_russian_phrases_future(phrase: str) -> None:
    now = datetime(2026, 5, 7, 8, 0, 0, tzinfo=timezone.utc)
    utc, err = parse_user_datetime_moscow(phrase, now_utc=now)
    assert err is None, f"phrase={phrase!r} err={err}"
    assert utc is not None
    assert utc > now - timedelta(seconds=60)
