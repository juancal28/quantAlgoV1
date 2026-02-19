"""Market hours utilities using exchange_calendars (NYSE / XNYS)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import exchange_calendars as xcals
import pandas as pd

_calendar: Optional[xcals.ExchangeCalendar] = None


def _get_calendar() -> xcals.ExchangeCalendar:
    """Lazy-load the NYSE calendar to avoid slow startup."""
    global _calendar
    if _calendar is None:
        _calendar = xcals.get_calendar("XNYS")
    return _calendar


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def is_market_open() -> bool:
    """Return True if the NYSE is currently in a regular trading session."""
    cal = _get_calendar()
    now = _now_utc()
    return cal.is_open_on_minute(now, ignore_breaks=True)


def minutes_until_close() -> int:
    """Minutes until the current or next session close.

    Returns 0 if the market is closed and there is no current session.
    """
    cal = _get_calendar()
    now = _now_utc()

    if cal.is_open_on_minute(now, ignore_breaks=True):
        # Find the session this minute belongs to
        session = cal.minute_to_session(now)
        close_time = cal.session_close(session)
        delta = close_time - now
        return max(int(delta.total_seconds() // 60), 0)

    return 0


def next_market_open() -> datetime:
    """Return the UTC datetime of the next market open."""
    cal = _get_calendar()
    now = _now_utc()

    # Get the next session date
    try:
        next_session = cal.next_open(now)
    except ValueError:
        # If now is exactly on an open, advance slightly
        next_session = cal.next_open(now + pd.Timedelta(minutes=1))

    return next_session.to_pydatetime().replace(tzinfo=timezone.utc)


def is_pre_market() -> bool:
    """Return True if we are in the 30-minute window before market open."""
    cal = _get_calendar()
    now = _now_utc()

    if cal.is_open_on_minute(now, ignore_breaks=True):
        return False

    try:
        next_open = cal.next_open(now)
    except ValueError:
        return False

    delta = next_open - now
    return pd.Timedelta(0) < delta <= pd.Timedelta(minutes=30)
