"""Reveal-time rules: the earliest plausible reveal (D-14) and the event early bound (D-27).

``earliest_plausible_reveal(Q, n)`` is quarter end + ``n`` days at 00:00 IST, as UTC. A lock
at or after it is refused (D-14). Offsets live in ``config/universe.toml``
(DMART +1, TITAN +2, ETERNAL +7).

``event_early_bound`` turns a stored reveal event into the instant used for deadlines, VOID
rules and backtest cutoffs:

- ``exchange_timestamp``: the stored dissemination time, unchanged.
- ``rule:date_eod_ist``: the stored value is the late bound ``D 23:59:59 IST`` (D-24); the
  early bound is that IST date at ``00:00:00 IST`` (D-27).

These are pure functions with no I/O and no wall clock, except ``reveal_calendar``, which reads
stored events only through the point-in-time reader it is given.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any, Literal, Protocol

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


RevealStatus = Literal["expected", "confirmed"]


@dataclass(frozen=True)
class RevealCalendar:
    """One company's reveal calendar for one quarter, as knowable at the reader's as_of.

    ``business_update_at`` and ``results_at`` are the earliest known event of each kind,
    shown as stored (the late bound for a date-only event). ``reveal_at`` is the earliest
    early bound of all known events (D-27), or ``None`` while the quarter is ``expected``.
    """

    business_update_at: datetime | None
    results_at: datetime | None
    reveal_at: datetime | None
    status: RevealStatus
    earliest_plausible_reveal: datetime


class _EventReader(Protocol):
    def reveal_events(self, ticker: str, fiscal_quarter_label: str) -> tuple[Any, ...]: ...


def reveal_calendar(
    reader: _EventReader, ticker: str, quarter: FiscalQuarter, offset_days: int
) -> RevealCalendar:
    """Derive the calendar from stored reveal events read through the PIT gate (PIT-04).

    The reader decides what is known: an event counts only once its stored ``event_at`` is
    before ``as_of`` (and, in live mode, it was ingested by then).
    """
    epr = earliest_plausible_reveal(quarter, offset_days)  # also validates the arguments
    events = reader.reveal_events(ticker, quarter.label)
    earliest: dict[str, tuple[datetime, datetime]] = {}
    for event in events:
        bound = event_early_bound(event.event_at, event.availability_basis)
        current = earliest.get(event.event_kind)
        if current is None or (bound, event.event_at) < current:
            earliest[event.event_kind] = (bound, event.event_at)
    bounds = [bound for bound, _ in earliest.values()]
    return RevealCalendar(
        business_update_at=earliest["business_update"][1]
        if "business_update" in earliest
        else None,
        results_at=earliest["results"][1] if "results" in earliest else None,
        reveal_at=min(bounds) if bounds else None,
        status="confirmed" if earliest else "expected",
        earliest_plausible_reveal=epr,
    )
