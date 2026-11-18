"""Reveal-time rules: the earliest plausible reveal (D-14) and the event early bound (D-27).

``earliest_plausible_reveal(Q, n)`` is quarter end + ``n`` days at 00:00 IST, as UTC. A lock
at or after it is refused (D-14). Offsets live in ``config/universe.toml``
(DMART +1, TITAN +2, ETERNAL +7).

``event_early_bound`` turns a stored reveal event into the instant used for deadlines, VOID
rules and backtest cutoffs:

- ``exchange_timestamp``: the stored dissemination time, unchanged.
- ``rule:date_eod_ist``: the stored value is the late bound ``D 23:59:59 IST`` (D-24); the
  early bound is that IST date at ``00:00:00 IST`` (D-27).

Pure functions: no I/O and no wall clock.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Literal

from calledit_data.calendar.fiscal import FiscalQuarter
from calledit_data.calendar.tz import IST, date_start_ist_utc, to_utc

AvailabilityBasis = Literal["exchange_timestamp", "rule:date_eod_ist"]
AVAILABILITY_BASES: tuple[str, ...] = ("exchange_timestamp", "rule:date_eod_ist")

_EOD = time(23, 59, 59)


def earliest_plausible_reveal(quarter: FiscalQuarter, offset_days: int) -> datetime:
    """``quarter.end + offset_days`` at 00:00 IST, as UTC (D-14)."""
    if not isinstance(quarter, FiscalQuarter):
        raise TypeError(f"quarter must be a FiscalQuarter (got {type(quarter).__name__})")
    if type(offset_days) is not int:
        raise TypeError(f"offset_days must be an int (got {type(offset_days).__name__})")
    if offset_days < 0:
        raise ValueError("offset_days must be >= 0")
    day = quarter.end + timedelta(days=offset_days)
    return datetime.combine(day, time(0, 0, 0), IST).astimezone(UTC)


def event_early_bound(event_at_utc: datetime, availability_basis: str) -> datetime:
    """The early bound of a stored reveal event, as UTC (D-27).

    A ``rule:date_eod_ist`` value must be exactly ``D 23:59:59 IST``; anything else means the
    basis and the value disagree, and raises rather than guessing.
    """
    event = to_utc(event_at_utc)
    if availability_basis == "exchange_timestamp":
        return event
    if availability_basis == "rule:date_eod_ist":
        local = event.astimezone(IST)
        if local.timetz().replace(tzinfo=None) != _EOD:
            raise ValueError(
                "rule:date_eod_ist events must be stored as D 23:59:59 IST "
                f"(got {local.isoformat()})"
            )
        return date_start_ist_utc(local.date())
    raise ValueError(
        f"unknown availability_basis {availability_basis!r} "
        f"(expected one of {', '.join(AVAILABILITY_BASES)})"
    )
