"""LEAK-03 (conversion half): IST/UTC boundaries and the late/early bounds of date-only events.

No test reads the wall clock: every instant is a literal.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from calledit_data.calendar.fiscal import FiscalQuarter
from calledit_data.calendar.reveal import earliest_plausible_reveal, event_early_bound
from calledit_data.calendar.tz import (
    IST,
    date_eod_ist_utc,
    date_start_ist_utc,
    ist_date,
    to_ist,
    to_utc,
)

D = date(2026, 11, 5)
Q3FY27 = FiscalQuarter.parse("Q3FY27")


def test_ist_is_fixed_plus_0530() -> None:
    assert IST.utcoffset(None) == timedelta(hours=5, minutes=30)
    assert IST.dst(None) is None


def test_just_after_ist_midnight_is_previous_utc_day() -> None:
    local = datetime(2027, 1, 2, 0, 15, tzinfo=IST)
    assert to_utc(local) == datetime(2027, 1, 1, 18, 45, tzinfo=UTC)
    assert to_utc(local).tzinfo is UTC
    assert ist_date(datetime(2027, 1, 1, 18, 45, tzinfo=UTC)) == date(2027, 1, 2)
    assert ist_date(datetime(2027, 1, 1, 18, 29, 59, tzinfo=UTC)) == date(2027, 1, 1)


def test_late_bound_is_end_of_ist_day() -> None:
    assert date_eod_ist_utc(D) == datetime(2026, 11, 5, 18, 29, 59, tzinfo=UTC)


def test_early_bound_is_start_of_ist_day() -> None:
    assert date_start_ist_utc(D) == datetime(2026, 11, 4, 18, 30, 0, tzinfo=UTC)


def test_event_early_bound_for_date_only_event() -> None:
    stored = datetime(2026, 11, 5, 18, 29, 59, tzinfo=UTC)
    assert event_early_bound(stored, "rule:date_eod_ist") == datetime(
        2026, 11, 4, 18, 30, 0, tzinfo=UTC
    )


def test_event_early_bound_for_exchange_timestamp_is_unchanged() -> None:
    stored = datetime(2026, 11, 5, 12, 47, tzinfo=UTC)
    assert event_early_bound(stored, "exchange_timestamp") == stored
    in_ist = stored.astimezone(IST)
    assert event_early_bound(in_ist, "exchange_timestamp") == stored
    assert event_early_bound(in_ist, "exchange_timestamp").tzinfo is UTC


def test_event_early_bound_refuses_a_rule_value_that_is_not_eod() -> None:
    with pytest.raises(ValueError, match="23:59:59 IST"):
        event_early_bound(datetime(2026, 11, 5, 12, 0, tzinfo=UTC), "rule:date_eod_ist")


def test_event_early_bound_refuses_unknown_basis() -> None:
    with pytest.raises(ValueError, match="unknown availability_basis"):
        event_early_bound(datetime(2026, 11, 5, 12, 0, tzinfo=UTC), "rule:guess")


def test_rule_basis_row_is_not_visible_to_a_cutoff_earlier_that_day() -> None:
    available_at = date_eod_ist_utc(D)
    cutoff = to_utc(datetime(2026, 11, 5, 18, 0, tzinfo=IST))
    assert not available_at < cutoff
    # ...and it is visible from the next IST day on.
    next_day = to_utc(datetime(2026, 11, 6, 0, 0, tzinfo=IST))
    assert available_at < next_day


def test_deadline_uses_early_bound_so_a_same_day_lock_is_late() -> None:
    # A date-only reveal on D: a lock at D 18:00 IST is after the early bound (refused/VOID).
    early = event_early_bound(date_eod_ist_utc(D), "rule:date_eod_ist")
    lock = to_utc(datetime(2026, 11, 5, 18, 0, tzinfo=IST))
    assert lock >= early
    # The day before at 23:59:59 IST is still before the deadline.
    assert to_utc(datetime(2026, 11, 4, 23, 59, 59, tzinfo=IST)) < early


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (1, datetime(2026, 12, 31, 18, 30, tzinfo=UTC)),  # DMART
        (2, datetime(2027, 1, 1, 18, 30, tzinfo=UTC)),  # TITAN
        (7, datetime(2027, 1, 6, 18, 30, tzinfo=UTC)),  # ETERNAL
        (0, datetime(2026, 12, 30, 18, 30, tzinfo=UTC)),
    ],
)
def test_earliest_plausible_reveal_q3fy27(offset: int, expected: datetime) -> None:
    got = earliest_plausible_reveal(Q3FY27, offset)
    assert got == expected
    assert got.tzinfo is UTC
    assert to_ist(got).hour == 0 and to_ist(got).minute == 0


@pytest.mark.parametrize("offset", [-1, 1.0, True, "1"])
def test_earliest_plausible_reveal_rejects_bad_offsets(offset: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        earliest_plausible_reveal(Q3FY27, offset)  # type: ignore[arg-type]


NAIVE = datetime(2026, 11, 5, 12, 0)


@pytest.mark.parametrize(
    "call",
    [
        lambda: to_utc(NAIVE),
        lambda: to_ist(NAIVE),
        lambda: ist_date(NAIVE),
        lambda: event_early_bound(NAIVE, "exchange_timestamp"),
        lambda: event_early_bound(NAIVE, "rule:date_eod_ist"),
    ],
    ids=["to_utc", "to_ist", "ist_date", "early_bound_exchange", "early_bound_rule"],
)
def test_naive_input_raises(call: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match="naive"):
        call()


@pytest.mark.parametrize("fn", [date_eod_ist_utc, date_start_ist_utc])
def test_date_bounds_reject_datetimes(fn: Callable[[date], datetime]) -> None:
    with pytest.raises(TypeError):
        fn(datetime(2026, 11, 5, 12, 0, tzinfo=UTC))
    with pytest.raises(TypeError):
        fn(NAIVE)


def _sample_instants() -> list[datetime]:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime(2027, 12, 31, 23, 59, 59, tzinfo=UTC)
    step = (end - start) / 49
    # Irregular minute/second offsets so the samples land at varied times of day.
    return [start + step * i + timedelta(minutes=37 * i, seconds=11 * i) for i in range(50)]


def test_ist_matches_zoneinfo() -> None:
    assert importlib.util.find_spec("tzdata") is not None, "tzdata must be installed"
    kolkata = ZoneInfo("Asia/Kolkata")
    samples = _sample_instants()
    assert len(samples) == 50
    for instant in samples:
        ours = instant.astimezone(IST)
        theirs = instant.astimezone(kolkata)
        assert ours.utcoffset() == theirs.utcoffset(), instant.isoformat()
        assert ours.replace(tzinfo=None) == theirs.replace(tzinfo=None), instant.isoformat()
        # And the IST-midnight bounds agree for that instant's IST date.
        day = theirs.date()
        assert date_start_ist_utc(day) == datetime.combine(
            day, datetime.min.time(), kolkata
        ).astimezone(UTC)
