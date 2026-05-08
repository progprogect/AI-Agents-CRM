"""Parse user-written date/time for reminders (interpreted in Europe/Moscow)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import dateparser

logger = logging.getLogger(__name__)

MSK = ZoneInfo("Europe/Moscow")


def parse_user_datetime_moscow(text: str, *, now_utc: Optional[datetime] = None) -> tuple[Optional[datetime], Optional[str]]:
    """Parse free-form Russian / numeric datetime as Moscow local time → UTC.

    Returns ``(utc_datetime, None)`` on success, or ``(None, error_code)`` where
    error_code is ``empty`` | ``unparsed`` | ``past``.
    """
    raw = (text or "").strip()
    if len(raw) < 3:
        return None, "empty"

    now_utc = now_utc or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    # DD.MM.YYYY HH:MM or DD.MM.YYYY, HH:MM
    m = re.match(
        r"^(\d{1,2})\.(\d{1,2})\.(\d{4})\s*(?:[,в]\s*)?(\d{1,2})[:.](\d{2})\s*$",
        raw,
        re.I,
    )
    if m:
        d, mo, y, h, mi = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))
        try:
            dt_msk = datetime(y, mo, d, h, mi, 0, tzinfo=MSK)
            utc_dt = dt_msk.astimezone(timezone.utc)
            if utc_dt <= now_utc - timedelta(seconds=30):
                return None, "past"
            return utc_dt, None
        except ValueError:
            pass

    # DD.MM.YYYY without time → 10:00 МСК (как «утром» по умолчанию)
    m_date = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})\s*$", raw)
    if m_date:
        d, mo, y = int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3))
        try:
            dt_msk = datetime(y, mo, d, 10, 0, 0, tzinfo=MSK)
            utc_dt = dt_msk.astimezone(timezone.utc)
            if utc_dt <= now_utc - timedelta(seconds=30):
                return None, "past"
            return utc_dt, None
        except ValueError:
            pass

    try:
        now_msk = now_utc.astimezone(MSK)
        dp_settings = {
            "TIMEZONE": "Europe/Moscow",
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
            "RELATIVE_BASE": now_msk.replace(tzinfo=None),
        }

        parsed = dateparser.parse(raw, languages=["ru", "en"], settings=dp_settings)
        if parsed is None:
            return None, "unparsed"

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=MSK)

        utc_dt = parsed.astimezone(timezone.utc)

        if utc_dt <= now_utc - timedelta(seconds=30):
            return None, "past"

        return utc_dt, None
    except Exception as exc:
        logger.debug("dateparser failed for %r: %s", raw, exc)
        return None, "unparsed"
