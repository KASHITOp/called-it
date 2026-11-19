"""PIT-03 and the strict-cutoff half of LEAK-03: ``PointInTimeReader`` only returns rows
knowable at ``as_of``.

Plan 01-06 re-parametrises this file over the ``reader_cls`` fixture: ``--reader=<variant>``
swaps in a deliberately leaky reader, which must fail this file, so every reader is built
through the ``make_reader`` factory fixture. The two post-condition tests monkeypatch the
production reader itself and deliberately use ``PointInTimeReader`` directly.

All values are synthetic test data.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa
from calledit_data.calendar.tz import IST
from calledit_data.pit.reader import LeakageError, PointInTimeReader
from calledit_data.store.writer import (
    ObservationIn,
    RevealEventIn,
    ensure_series,
    insert_observations,
    insert_reveal_events,
    observation_content_hash,
)

KEY = "rev.consolidated.DMART"
AS_OF = datetime(2026, 11, 28, 6, 0, 0, tzinfo=UTC)
INGESTED = datetime(2026, 11, 1, 0, 0, 0, tzinfo=UTC)
ONE_US = timedelta(microseconds=1)

BASE = ObservationIn(
    series_key=KEY,
    period_date=date(2026, 9, 30),
    value=Decimal("10700.00"),
    available_at=AS_OF - timedelta(days=30),
    availability_basis="exchange_timestamp",
    source_ref="https://example.invalid/synthetic-fixture#p8",
    vintage="first_reported",
    source_kind="seed_csv",
)


ReaderFactory = Callable[..., PointInTimeReader]


@pytest.fixture
def make_reader(reader_cls: type[PointInTimeReader]) -> ReaderFactory:
    """Build ``reader_cls(engine, as_of, mode)``: production by default, leaky via --reader."""

    def build(engine: sa.Engine, as_of: datetime, mode: str = "backtest") -> PointInTimeReader:
        return reader_cls(engine, as_of, mode)  # type: ignore[arg-type]

    return build


def store(engine: sa.Engine, rows: list[ObservationIn], ingested_at: datetime = INGESTED) -> None:
    with engine.begin() as conn:
        ensure_series(
            conn, KEY, "seed_csv", "revenue", "DMART", "inr_crore", "quarterly", "manual_seed"
        )
        insert_observations(conn, rows, ingested_at)


def at(when: datetime, **changes: object) -> ObservationIn:
    return replace(BASE, available_at=when, **changes)


# --- the strict cutoff --------------------------------------------------------------------


def test_row_at_exact_cutoff_is_excluded(
    migrated_sqlite: sa.Engine, make_reader: ReaderFactory
) -> None:
    store(migrated_sqlite, [at(AS_OF)])
    assert make_reader(migrated_sqlite, AS_OF).series(KEY) == ()


def test_row_one_microsecond_before_cutoff_is_included(
    migrated_sqlite: sa.Engine, make_reader: ReaderFactory
) -> None:
    store(migrated_sqlite, [at(AS_OF - ONE_US)])
    rows = make_reader(migrated_sqlite, AS_OF).series(KEY)
    assert len(rows) == 1
    assert rows[0].available_at == AS_OF - ONE_US


def test_ist_filing_after_midnight_boundary(
    migrated_sqlite: sa.Engine, make_reader: ReaderFactory
) -> None:
    filing = datetime(2027, 1, 2, 0, 15, tzinfo=IST)
    assert filing.astimezone(UTC) == datetime(2027, 1, 1, 18, 45, tzinfo=UTC)
    store(migrated_sqlite, [at(filing, period_date=date(2026, 12, 31))], ingested_at=filing)
    cutoff = datetime(2027, 1, 1, 18, 45, 0, tzinfo=UTC)
    assert make_reader(migrated_sqlite, cutoff).series(KEY) == ()
    assert len(make_reader(migrated_sqlite, cutoff + timedelta(seconds=1)).series(KEY)) == 1


@pytest.mark.parametrize(
    "as_of",
    [
        datetime(2026, 11, 28, 6, 0, 0),
        datetime(2026, 11, 28, 11, 30, 0, tzinfo=IST),
        datetime(2026, 11, 28, 6, 0, 0, tzinfo=timezone(timedelta(hours=-5))),
        "2026-11-28T06:00:00Z",
    ],
    ids=["naive", "ist-offset", "negative-offset", "string"],
)
def test_as_of_must_be_aware_utc(
    migrated_sqlite: sa.Engine, as_of: object, make_reader: ReaderFactory
) -> None:
    with pytest.raises((TypeError, ValueError)):
        make_reader(migrated_sqlite, as_of)  # type: ignore[arg-type]


def test_unknown_mode_is_refused(migrated_sqlite: sa.Engine, make_reader: ReaderFactory) -> None:
    with pytest.raises(ValueError, match="mode"):
        make_reader(migrated_sqlite, AS_OF, "lookahead")


def test_empty_store_returns_empty_tuple(
    migrated_sqlite: sa.Engine, make_reader: ReaderFactory
) -> None:
    reader = make_reader(migrated_sqlite, AS_OF)
    assert reader.series(KEY) == ()
    assert reader.series("rev.consolidated.NOBODY") == ()
    assert reader.reveal_events("DMART", "Q2FY27") == ()


def test_series_with_nothing_before_as_of_returns_empty_tuple(
    migrated_sqlite: sa.Engine, make_reader: ReaderFactory
) -> None:
    store(migrated_sqlite, [at(AS_OF + timedelta(days=1))])
    assert make_reader(migrated_sqlite, AS_OF).series(KEY) == ()


# --- vintages (D-05) ----------------------------------------------------------------------


def test_later_vintage_before_as_of_wins(
    migrated_sqlite: sa.Engine, make_reader: ReaderFactory
) -> None:
    v1 = at(AS_OF - timedelta(days=30))
    v2 = at(AS_OF - timedelta(days=5), value=Decimal("10750.00"), vintage="restated")
    store(migrated_sqlite, [v2, v1])
    rows = make_reader(migrated_sqlite, AS_OF).series(KEY)
    assert [r.value for r in rows] == [Decimal("10750.000000")]
    assert rows[0].vintage == "restated"


def test_vintage_after_as_of_is_ignored(
    migrated_sqlite: sa.Engine, make_reader: ReaderFactory
) -> None:
    v1 = at(AS_OF - timedelta(days=30))
    v2 = at(AS_OF + timedelta(days=5), value=Decimal("10750.00"), vintage="restated")
    store(migrated_sqlite, [v1, v2])
    rows = make_reader(migrated_sqlite, AS_OF).series(KEY)
    assert [r.value for r in rows] == [Decimal("10700.000000")]
    assert rows[0].vintage == "first_reported"


def test_exact_ties_break_by_content_hash_deterministically(
    migrated_sqlite: sa.Engine, make_reader: ReaderFactory
) -> None:
    when = AS_OF - timedelta(days=3)
    tied = [
        at(when, value=Decimal("10701.00"), source_ref="https://example.invalid/a"),
        at(when, value=Decimal("10702.00"), source_ref="https://example.invalid/b"),
        at(when, value=Decimal("10703.00"), source_ref="https://example.invalid/c"),
    ]
    expected = max(tied, key=observation_content_hash)
    # Insert in an order where the winner is neither first nor last by obs_id.
    store(migrated_sqlite, sorted(tied, key=observation_content_hash)[::2][::-1])
    store(migrated_sqlite, tied)
    reads = [make_reader(migrated_sqlite, AS_OF).series(KEY) for _ in range(3)]
    assert reads[0] == reads[1] == reads[2]
    assert len(reads[0]) == 1
    assert reads[0][0].content_hash == observation_content_hash(expected)


def test_output_is_sorted_by_period_and_stable(
    migrated_sqlite: sa.Engine, make_reader: ReaderFactory
) -> None:
    periods = [date(2026, 6, 30), date(2025, 12, 31), date(2026, 9, 30), date(2026, 3, 31)]
    store(
        migrated_sqlite,
        [at(AS_OF - timedelta(days=10 + i), period_date=p) for i, p in enumerate(periods)],
    )
    first = make_reader(migrated_sqlite, AS_OF).series(KEY)
    assert [r.period_date for r in first] == sorted(periods)
    assert make_reader(migrated_sqlite, AS_OF).series(KEY) == first


# --- live mode ----------------------------------------------------------------------------


def test_live_mode_excludes_rows_ingested_after_as_of(
    migrated_sqlite: sa.Engine, make_reader: ReaderFactory
) -> None:
    store(migrated_sqlite, [at(AS_OF - timedelta(days=30))], ingested_at=AS_OF + ONE_US)
    assert make_reader(migrated_sqlite, AS_OF, "live").series(KEY) == ()
    assert len(make_reader(migrated_sqlite, AS_OF, "backtest").series(KEY)) == 1


def test_live_mode_includes_rows_ingested_exactly_at_as_of(
    migrated_sqlite: sa.Engine, make_reader: ReaderFactory
) -> None:
    store(migrated_sqlite, [at(AS_OF - timedelta(days=30))], ingested_at=AS_OF)
    assert len(make_reader(migrated_sqlite, AS_OF, "live").series(KEY)) == 1


# --- reveal events ------------------------------------------------------------------------


def _event(when: datetime, kind: str = "results") -> RevealEventIn:
    return RevealEventIn(
        ticker="DMART",
        fiscal_quarter="Q2FY27",
        event_kind=kind,
        event_at=when,
        availability_basis="exchange_timestamp",
        source_ref="https://example.invalid/synthetic-fixture",
    )


def test_reveal_events_use_the_same_strict_cutoff(
    migrated_sqlite: sa.Engine, make_reader: ReaderFactory
) -> None:
    with migrated_sqlite.begin() as conn:
        insert_reveal_events(
            conn,
            [_event(AS_OF, "results"), _event(AS_OF - timedelta(seconds=1), "business_update")],
            INGESTED,
        )
    events = make_reader(migrated_sqlite, AS_OF).reveal_events("DMART", "Q2FY27")
    assert [e.event_kind for e in events] == ["business_update"]
    assert make_reader(migrated_sqlite, AS_OF).reveal_events("DMART", "Q3FY27") == ()


# --- the post-condition -------------------------------------------------------------------


def test_postcondition_catches_a_leaky_filter(
    migrated_sqlite: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    leaked = at(AS_OF + timedelta(days=1), period_date=date(2026, 12, 31))
    store(migrated_sqlite, [at(AS_OF - timedelta(days=30)), leaked])
    with migrated_sqlite.begin() as conn:
        insert_reveal_events(conn, [_event(AS_OF)], INGESTED)
    monkeypatch.setattr(PointInTimeReader, "_row_filter", lambda self, table: sa.true())
    reader = PointInTimeReader(migrated_sqlite, AS_OF, "backtest")
    with pytest.raises(LeakageError, match=observation_content_hash(leaked)):
        reader.series(KEY)
    with pytest.raises(LeakageError):
        reader.reveal_events("DMART", "Q2FY27")


def test_postcondition_catches_live_ingestion_leak(
    migrated_sqlite: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    store(migrated_sqlite, [at(AS_OF - timedelta(days=30))], ingested_at=AS_OF + ONE_US)
    monkeypatch.setattr(
        PointInTimeReader,
        "_row_filter",
        lambda self, table: table.c.available_at < self.as_of,
    )
    with pytest.raises(LeakageError):
        PointInTimeReader(migrated_sqlite, AS_OF, "live").series(KEY)


def test_leakage_error_is_an_assertion_error() -> None:
    assert issubclass(LeakageError, AssertionError)
