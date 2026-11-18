"""IST/UTC conversions and the two bounds for a date-only event (LEAK-03).

India Standard Time is a fixed UTC+05:30 offset with no DST anywhere in the data range,
so ``IST`` needs no tz database. ``tests/leakage/test_time_boundaries.py`` checks that it
agrees with ``ZoneInfo("Asia/Kolkata")``.

Every function rejects naive datetimes: comparing a naive and an aware instant, or treating
a naive value as UTC when it was IST, is a lookahead bug (threat T-01-10).

Date-only events get two bounds, and each direction errs safe:

- ``date_eod_ist_utc(D)`` is the **late** bound ``D 23:59:59 IST``. It is the availability
  rule (D-24): a value disclosed on day D is never treated as known before the day is over.
- ``date_start_ist_utc(D)`` is the **early** bound ``D 00:00:00 IST``. It is the deadline
  rule (D-27): lock deadlines, VOID rules and data cutoffs assume the event happened as
  early as it could have on that day.

Pure functions: no I/O and no wall clock.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")

_EOD = time(23, 59, 59)
_START = time(0, 0, 0)


def _require_aware(dt: object, fn: str) -> datetime:
    if not isinstance(dt, datetime):
        raise TypeError(f"{fn} requires a datetime (got {type(dt).__name__})")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{fn} rejects naive datetimes; attach a timezone first")
    return dt


def _require_date(d: object, fn: str) -> date:
    # datetime is a subclass of date; a datetime here would silently drop its time and zone.
    if type(d) is not date:
        raise TypeError(f"{fn} requires a date, not {type(d).__name__}")
    return d


def to_utc(dt: datetime) -> datetime:
    """Return the same instant in UTC. Naive input raises ``ValueError``."""
    return _require_aware(dt, "to_utc").astimezone(UTC)


def to_ist(dt: datetime) -> datetime:
    """Return the same instant as IST wall-clock time (display only; store UTC)."""
    return _require_aware(dt, "to_ist").astimezone(IST)


def date_eod_ist_utc(d: date) -> datetime:
    """Late bound for a date-only event: ``D 23:59:59 IST`` as UTC (availability, D-24)."""
    return datetime.combine(_require_date(d, "date_eod_ist_utc"), _EOD, IST).astimezone(UTC)


def date_start_ist_utc(d: date) -> datetime:
    """Early bound for a date-only event: ``D 00:00:00 IST`` as UTC (deadlines, D-27)."""
    return datetime.combine(_require_date(d, "date_start_ist_utc"), _START, IST).astimezone(UTC)


def ist_date(dt: datetime) -> date:
    """The IST calendar date of an aware instant."""
    return _require_aware(dt, "ist_date").astimezone(IST).date()
