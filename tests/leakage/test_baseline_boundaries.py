"""LEAK-01/LEAK-03 at the baseline boundary: rows at or after the cutoff change nothing.

A clean store is built from the SYNTHETIC seed fixture. A second store gets the same rows plus
sentinel rows (value 999999999.99) placed exactly where each deliberately leaky reader goes
wrong. ``compute_baseline`` at the cutoff must return the same point and the same canonical
snapshot on both, and no input may carry the sentinel value.

The sentinels are all restatements of DMART Q2FY27 that would WIN the latest-vintage rule if
a reader let them through, so a leaky reader changes the baseline instead of hiding.

Run with ``--reader=<variant>`` to prove each leaky reader turns this file red. Every value
here is SYNTHETIC test data.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from calledit_data.calendar.fiscal import FiscalQuarter
from calledit_data.pit.reader import PointInTimeReader
from calledit_data.store.writer import ObservationIn
from nowcaster.baseline import BaselineRefusal, BaselineResult, compute_baseline
from nowcaster.universe import Universe, load_universe

from tests.conftest import REPO_ROOT
from tests.leakage.store_helpers import (
    SENTINEL,
    add_observations,
    count_rows,
    fresh_store,
    load_fixture,
)

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "seed_fixture_SYNTHETIC.csv"
UNIVERSE: Universe = load_universe(REPO_ROOT / "config" / "universe.toml")
TARGET = FiscalQuarter.parse("Q3FY27")
T = datetime(2026, 11, 28, 4, 0, 0, tzinfo=UTC)
LOADED = datetime(2026, 11, 1, 0, 0, 0, tzinfo=UTC)
KEY = "rev.consolidated.DMART"
ONE_SECOND = timedelta(seconds=1)


def _sentinel(available_at: datetime, ref: str) -> ObservationIn:
    return ObservationIn(
        series_key=KEY,
        period_date=date(2026, 9, 30),  # DMART Q2FY27, a window quarter
        value=SENTINEL,
        available_at=available_at,
        availability_basis="exchange_timestamp",
        source_ref=f"https://example.invalid/synthetic-sentinel#{ref}",
        vintage="restated",
        source_kind="seed_csv",
    )


# Each one is wrong for exactly one leaky reader (and harmless to the correct reader).
AT_T = _sentinel(T, "at-t")  # leaky-le: available_at == as_of
T_PLUS_1S = _sentinel(T + ONE_SECOND, "t-plus-1s")  # leaky-nofilter
FAR_FUTURE = _sentinel(T + timedelta(days=30), "far-future")  # leaky-nofilter, leaky-period
# leaky-period: its period_date (2026-09-30) is before T's date although it is filed after T.
KNOWN_BUT_NOT_INGESTED = _sentinel(T - timedelta(days=1), "ingested-late")  # leaky-ingested
INGESTED_AFTER_T = T + ONE_SECOND


def _stores(mode: str) -> tuple:
    clean, dirty = fresh_store(), fresh_store()
    for engine in (clean, dirty):
        load_fixture(engine, FIXTURE, UNIVERSE, now=T, ingested_at=LOADED)
    add_observations(dirty, [AT_T, T_PLUS_1S, FAR_FUTURE], LOADED)
    if mode == "live":
        # available before T, but only loaded after T: invisible to a live call made at T.
        add_observations(dirty, [KNOWN_BUT_NOT_INGESTED], INGESTED_AFTER_T)
    return clean, dirty


def _baseline(reader: PointInTimeReader) -> BaselineResult:
    company = UNIVERSE.company("DMART")
    outcome = compute_baseline(company, TARGET, reader, UNIVERSE.breaks_for("DMART"))
    assert not isinstance(outcome, BaselineRefusal), outcome
    return outcome


def _values(result: BaselineResult) -> Sequence[Decimal]:
    return [obs.value for obs in result.inputs]


@pytest.mark.parametrize("mode", ["backtest", "live"])
def test_rows_at_or_after_the_cutoff_do_not_change_the_baseline(
    mode: str, reader_cls: type[PointInTimeReader]
) -> None:
    clean, dirty = _stores(mode)
    # The premise: the sentinels really are in the dirty store.
    extra = 4 if mode == "live" else 3
    assert count_rows(dirty, KEY) == count_rows(clean, KEY) + extra

    expected = _baseline(PointInTimeReader(clean, T, mode))  # type: ignore[arg-type]
    actual = _baseline(reader_cls(dirty, T, mode))  # type: ignore[arg-type]

    assert SENTINEL not in _values(actual)
    assert actual.point == expected.point
    assert actual.snapshot_canonical == expected.snapshot_canonical
    assert actual.snapshot_sha256 == expected.snapshot_sha256


@pytest.mark.parametrize(
    "sentinel",
    [AT_T, T_PLUS_1S, FAR_FUTURE],
    ids=["exactly-at-T", "T-plus-1s", "period-before-T-filed-after-T"],
)
def test_each_sentinel_alone_is_invisible_at_the_cutoff(
    sentinel: ObservationIn, reader_cls: type[PointInTimeReader]
) -> None:
    clean, dirty = fresh_store(), fresh_store()
    for engine in (clean, dirty):
        load_fixture(engine, FIXTURE, UNIVERSE, now=T, ingested_at=LOADED)
    add_observations(dirty, [sentinel], LOADED)
    expected = _baseline(PointInTimeReader(clean, T, "backtest"))
    actual = _baseline(reader_cls(dirty, T, "backtest"))
    assert SENTINEL not in _values(actual)
    assert actual.snapshot_canonical == expected.snapshot_canonical


def test_row_available_before_T_but_ingested_after_T_is_invisible_live(
    reader_cls: type[PointInTimeReader],
) -> None:
    clean, dirty = fresh_store(), fresh_store()
    for engine in (clean, dirty):
        load_fixture(engine, FIXTURE, UNIVERSE, now=T, ingested_at=LOADED)
    add_observations(dirty, [KNOWN_BUT_NOT_INGESTED], INGESTED_AFTER_T)
    expected = _baseline(PointInTimeReader(clean, T, "live"))
    actual = _baseline(reader_cls(dirty, T, "live"))
    assert SENTINEL not in _values(actual)
    assert actual.snapshot_canonical == expected.snapshot_canonical
    # The same row IS knowable in a backtest at T (ingestion time is not part of that rule).
    backtest = _baseline(PointInTimeReader(dirty, T, "backtest"))
    assert SENTINEL in _values(backtest)


def test_the_fixture_baseline_is_the_hand_computed_one(reader_cls: type[PointInTimeReader]) -> None:
    """Sanity: the clean DMART point matches test_baseline_e2e's hand computation."""
    clean = fresh_store()
    load_fixture(clean, FIXTURE, UNIVERSE, now=T, ingested_at=LOADED)
    result = _baseline(reader_cls(clean, T, "backtest"))  # type: ignore[arg-type]
    assert result.point == Decimal("10809.85")
