"""UTC datetime utilities for consistent timezone handling.

This module provides centralized utilities for working with UTC datetime
to ensure all timestamps are timezone-aware and properly serialized with 'Z' suffix.
"""

import logging
from datetime import date, datetime, time, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime.
    
    Returns:
        datetime: Current UTC time with timezone info (timezone.utc)
    
    Example:
        >>> dt = utc_now()
        >>> dt.tzinfo
        datetime.timezone.utc
    """
    return datetime.now(timezone.utc)


def to_utc_iso_string(dt: Optional[datetime]) -> Optional[str]:
    """Serialize datetime to ISO 8601 string with 'Z' suffix for UTC.
    
    Ensures that UTC datetime objects are serialized with 'Z' suffix
    to make timezone explicit for frontend parsing.
    
    Args:
        dt: Datetime object to serialize. Can be None.
    
    Returns:
        ISO 8601 string with 'Z' suffix if UTC, or None if dt is None.
        For naive datetime (without timezone), assumes UTC and adds 'Z'.
        For timezone-aware datetime, converts to UTC and adds 'Z'.
    
    Example:
        >>> dt = datetime.now(timezone.utc)
        >>> to_utc_iso_string(dt)
        '2024-01-15T10:00:00Z'
        
        >>> naive_dt = datetime(2024, 1, 15, 10, 0, 0)
        >>> to_utc_iso_string(naive_dt)
        '2024-01-15T10:00:00Z'
    """
    if dt is None:
        return None
    
    # If datetime is naive (no timezone), assume UTC
    if dt.tzinfo is None:
        # Create timezone-aware version assuming UTC
        dt_utc = dt.replace(tzinfo=timezone.utc)
    else:
        # Convert to UTC if not already
        dt_utc = dt.astimezone(timezone.utc)
    
    # Format with 'Z' suffix for UTC
    iso_string = dt_utc.isoformat()
    
    # Replace '+00:00' with 'Z' if present (more explicit)
    if iso_string.endswith('+00:00'):
        iso_string = iso_string[:-6] + 'Z'
    elif not iso_string.endswith('Z'):
        # If somehow doesn't have 'Z' or '+00:00', add 'Z'
        iso_string = iso_string + 'Z'
    
    return iso_string


def parse_utc_datetime(iso_string: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 string as UTC datetime.
    
    Safely parses ISO strings with or without 'Z' suffix,
    always interpreting as UTC for backward compatibility.
    
    Args:
        iso_string: ISO 8601 datetime string. Can be None.
    
    Returns:
        timezone-aware datetime in UTC, or None if iso_string is None.
        Raises ValueError if string cannot be parsed.
    
    Example:
        >>> parse_utc_datetime('2024-01-15T10:00:00Z')
        datetime.datetime(2024, 1, 15, 10, 0, tzinfo=datetime.timezone.utc)
        
        >>> parse_utc_datetime('2024-01-15T10:00:00')
        datetime.datetime(2024, 1, 15, 10, 0, tzinfo=datetime.timezone.utc)
        
        >>> parse_utc_datetime('2024-01-15T10:00:00+00:00')
        datetime.datetime(2024, 1, 15, 10, 0, tzinfo=datetime.timezone.utc)
    """
    if iso_string is None:
        return None
    
    if not isinstance(iso_string, str):
        raise ValueError(f"Expected string, got {type(iso_string)}")
    
    # Normalize the string: replace 'Z' with '+00:00' for fromisoformat
    normalized = iso_string.replace('Z', '+00:00')
    
    try:
        # Parse ISO string
        dt = datetime.fromisoformat(normalized)
        
        # Ensure timezone-aware (assume UTC if naive)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            # Convert to UTC if in different timezone
            dt = dt.astimezone(timezone.utc)
        
        return dt
    except ValueError as e:
        logger.warning(
            f"Failed to parse datetime string '{iso_string}': {e}",
            extra={"iso_string": iso_string}
        )
        raise ValueError(f"Invalid datetime string: {iso_string}") from e


def parse_query_datetime(value: Optional[str], *, end_of_day: bool = False) -> Optional[datetime]:
    """Parse admin list filter: ``YYYY-MM-DD`` (UTC day bounds) or full ISO 8601.

    For date-only strings: start of UTC day, or end of UTC day if ``end_of_day``.
    """
    if value is None or not str(value).strip():
        return None
    s = str(value).strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            d = date.fromisoformat(s)
        except ValueError as e:
            raise ValueError(f"Invalid date: {value}") from e
        if end_of_day:
            return datetime.combine(d, time(23, 59, 59, 999999, tzinfo=timezone.utc))
        return datetime.combine(d, time(0, 0, 0, tzinfo=timezone.utc))
    return parse_utc_datetime(s)
