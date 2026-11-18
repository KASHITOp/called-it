"""PIT-01 / PIT-02: the store is insert-only, explicit about time, and idempotent.

All values here are synthetic test data.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from calledit_data.db.schema import STORE_SQLITE_TRIGGERS, observations, reveal_events, series
from calledit_data.seed import loader as seed_loader
from calledit_data.seed.loader import SeedCompanyRules, load_seed
from calledit_data.store.writer import (
    ObservationIn,
    RevealEventIn,
    StoreError,
    ensure_series,
    insert_observations,
    insert_reveal_events,
)

from tests.conftest import REPO_ROOT

KEY = "rev.consolidated.DMART"
T_AVAIL = datetime(2026, 10, 11, 12, 0, 0, tzinfo=UTC)
T_INGEST = datetime(2026, 11, 18, 6, 0, 0, tzinfo=UTC)
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "seed_fixture_SYNTHETIC.csv"

OBS = ObservationIn(
    series_key=KEY,
    period_date=date(2026, 9, 30),
    value=Decimal("10700.00"),
    available_at=T_AVAIL,
    availability_basis="exchange_timestamp",
    source_ref="https://example.invalid/synthetic-fixture#p8",
    vintage="first_reported",
    source_kind="seed_csv",
)
EVENT = RevealEventIn(
    ticker="DMART",
    fiscal_quarter="Q2FY27",
    event_kind="results",
    event_at=T_AVAIL,
    availability_basis="exchange_timestamp",
    source_ref="https://example.invalid/synthetic-fixture#p8",
)
RULES = {
    "DMART": SeedCompanyRules("INE192R01011", True),
    "ETERNAL": SeedCompanyRules("INE758T01015", False),
    "TITAN": SeedCompanyRules("INE280A01028", True),
}


def _series(conn: sa.Connection) -> int:
    return ensure_series(
        conn, KEY, "seed_csv", "revenue", "DMART", "inr_crore", "quarterly", "manual_seed"
    )


def _write(engine: sa.Engine, rows: list[ObservationIn], ingested_at: datetime = T_INGEST) -> int:
    with engine.begin() as conn:
        _series(conn)
        return insert_observations(conn, rows, ingested_at)


def _counts(engine: sa.Engine) -> tuple[int, int, int]:
    with engine.connect() as conn:
        return tuple(
            conn.execute(sa.select(sa.func.count()).select_from(t)).scalar_one()
            for t in (series, observations, reveal_events)
        )


def _raw_rows(engine: sa.Engine, table: str) -> list[tuple]:
    with engine.connect() as conn:
        return list(conn.exec_driver_sql(f"SELECT * FROM {table} ORDER BY 1"))


# --- PIT-01: explicit, complete rows ----------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        {"available_at": None},
        {"availability_basis": ""},
        {"availability_basis": None},
        {"source_ref": ""},
        {"source_ref": None},
        {"available_at": datetime(2026, 10, 11, 12, 0, 0)},  # naive
        {"value": 10700.0},  # float
        {"value": Decimal("NaN")},
        {"availability_basis": "guess"},
        {"vintage": "final"},
        {"source_kind": "scraped"},
        # A rule:date_eod_ist value must be D 23:59:59 IST.
        {"availability_basis": "rule:date_eod_ist"},
    ],
    ids=lambda c: next(iter(c)) + "=" + repr(next(iter(c.values()))),
)
def test_incomplete_or_untyped_observation_is_rejected(
    migrated_sqlite: sa.Engine, change: dict
) -> None:
    with pytest.raises(StoreError):
        _write(migrated_sqlite, [replace(OBS, **change)])
    assert _counts(migrated_sqlite) == (0, 0, 0)


@pytest.mark.parametrize("ingested_at", [None, datetime(2026, 11, 18, 6, 0, 0)])
def test_missing_or_naive_ingested_at_is_rejected(
    migrated_sqlite: sa.Engine, ingested_at: datetime | None
) -> None:
    with pytest.raises(StoreError, match="ingested_at"):
        _write(migrated_sqlite, [OBS], ingested_at)  # type: ignore[arg-type]
    with pytest.raises(StoreError, match="ingested_at"), migrated_sqlite.begin() as conn:
        insert_reveal_events(conn, [EVENT], ingested_at)  # type: ignore[arg-type]


def test_event_with_naive_or_sub_second_time_is_rejected(migrated_sqlite: sa.Engine) -> None:
    for bad in (datetime(2026, 10, 11, 12, 0, 0), T_AVAIL + timedelta(microseconds=1)):
        with pytest.raises(StoreError), migrated_sqlite.begin() as conn:
            insert_reveal_events(conn, [replace(EVENT, event_at=bad)], T_INGEST)


def test_db_has_no_server_defaults_and_requires_the_time_columns(
    migrated_sqlite: sa.Engine,
) -> None:
    with migrated_sqlite.connect() as conn:
        ddl = " ".join(
            conn.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type = 'table' "
                "AND name IN ('series', 'observations', 'reveal_events')"
            ).scalars()
        )
    assert "DEFAULT" not in ddl.upper()
    with migrated_sqlite.begin() as conn:
        series_id = _series(conn)
    base = {
        "series_id": series_id,
        "period_date": "2026-09-30",
        "value": "10700.000000",
        "available_at": "2026-10-11T12:00:00.000000Z",
        "availability_basis": "exchange_timestamp",
        "ingested_at": "2026-11-18T06:00:00.000000Z",
        "vintage": "first_reported",
        "source_ref": "https://example.invalid/synthetic-fixture",
        "source_kind": "seed_csv",
        "content_hash": "x" * 64,
    }
    for column in ("available_at", "availability_basis", "source_ref", "ingested_at"):
        values = {k: v for k, v in base.items() if k != column}
        cols = ", ".join(values)
        marks = ", ".join(f":{k}" for k in values)
        insert = sa.text(f"INSERT INTO observations ({cols}) VALUES ({marks})")
        with (
            pytest.raises(sa.exc.IntegrityError, match="NOT NULL"),
            migrated_sqlite.begin() as conn,
        ):
            conn.execute(insert, values)


# --- idempotency and revisions ----------------------------------------------------------


def test_reinserting_identical_rows_inserts_nothing(migrated_sqlite: sa.Engine) -> None:
    assert _write(migrated_sqlite, [OBS]) == 1
    # A later ingestion of the same content is the same row (ingested_at is not hashed).
    assert _write(migrated_sqlite, [OBS], T_INGEST + timedelta(days=1)) == 0
    assert _write(migrated_sqlite, [OBS, OBS]) == 0
    with migrated_sqlite.begin() as conn:
        assert insert_reveal_events(conn, [EVENT, EVENT], T_INGEST) == 1
        assert insert_reveal_events(conn, [EVENT], T_INGEST) == 0
    assert _counts(migrated_sqlite) == (1, 1, 1)


def test_restatement_adds_row_and_keeps_original(migrated_sqlite: sa.Engine) -> None:
    assert _write(migrated_sqlite, [OBS]) == 1
    original = _raw_rows(migrated_sqlite, "observations")
    restated = replace(
        OBS,
        value=Decimal("10750.00"),
        available_at=T_AVAIL + timedelta(days=90),
        vintage="restated",
    )
    assert _write(migrated_sqlite, [OBS, restated], T_INGEST + timedelta(days=100)) == 1
    after = _raw_rows(migrated_sqlite, "observations")
    assert len(after) == 2
    assert after[0] == original[0]  # byte-identical first-reported row
    assert after[1][3] == "10750.000000"


def test_two_vintages_with_different_available_at_are_both_stored(
    migrated_sqlite: sa.Engine,
) -> None:
    later = replace(OBS, available_at=T_AVAIL + timedelta(hours=1))
    assert _write(migrated_sqlite, [OBS, later]) == 2


def test_existing_series_with_different_metadata_is_refused(migrated_sqlite: sa.Engine) -> None:
    with migrated_sqlite.begin() as conn:
        first = _series(conn)
        assert _series(conn) == first
    with pytest.raises(StoreError, match="different unit"), migrated_sqlite.begin() as conn:
        ensure_series(
            conn, KEY, "seed_csv", "revenue", "DMART", "inr_lakh", "quarterly", "manual_seed"
        )


def test_unknown_series_is_refused(migrated_sqlite: sa.Engine) -> None:
    with pytest.raises(StoreError, match="unknown series"), migrated_sqlite.begin() as conn:
        insert_observations(conn, [OBS], T_INGEST)


# --- PIT-02: append-only at the DB --------------------------------------------------------


@pytest.fixture
def loaded(migrated_sqlite: sa.Engine) -> sa.Engine:
    _write(migrated_sqlite, [OBS])
    with migrated_sqlite.begin() as conn:
        insert_reveal_events(conn, [EVENT], T_INGEST)
    return migrated_sqlite


@pytest.fixture(params=["recursive_triggers_on", "recursive_triggers_off"])
def conn(loaded: sa.Engine, request: pytest.FixtureRequest) -> Iterator[sa.Connection]:
    with loaded.connect() as connection:
        if request.param == "recursive_triggers_off":
            connection.exec_driver_sql("PRAGMA recursive_triggers=OFF")
        try:
            yield connection
        finally:
            connection.rollback()
            connection.exec_driver_sql("PRAGMA recursive_triggers=ON")


OBS_COLS = (
    "obs_id, series_id, period_date, value, available_at, availability_basis, ingested_at, "
    "vintage, source_ref, source_kind, content_hash"
)
EVENT_COLS = (
    "event_id, ticker, fiscal_quarter, event_kind, event_at, availability_basis, source_ref, "
    "ingested_at, content_hash"
)

MUTATIONS = {
    "observations-update": "UPDATE observations SET value = '1.000000'",
    "observations-delete": "DELETE FROM observations",
    "observations-insert-or-replace": (
        f"INSERT OR REPLACE INTO observations ({OBS_COLS}) SELECT 1, series_id, period_date, "
        "'1.000000', available_at, availability_basis, ingested_at, vintage, source_ref, "
        "source_kind, 'forged' FROM observations"
    ),
    "observations-replace-same-unique-key": (
        f"REPLACE INTO observations ({OBS_COLS}) SELECT 99, series_id, period_date, value, "
        "available_at, availability_basis, ingested_at, vintage, source_ref, source_kind, "
        "content_hash FROM observations"
    ),
    "reveal_events-update": "UPDATE reveal_events SET event_at = '2026-01-01T00:00:00.000000Z'",
    "reveal_events-delete": "DELETE FROM reveal_events",
    "reveal_events-insert-or-replace": (
        f"INSERT OR REPLACE INTO reveal_events ({EVENT_COLS}) SELECT 1, ticker, fiscal_quarter, "
        "event_kind, '2026-01-01T00:00:00.000000Z', availability_basis, source_ref, "
        "ingested_at, 'forged' FROM reveal_events"
    ),
    "series-update": "UPDATE series SET unit = 'inr_lakh'",
    "series-delete": "DELETE FROM series",
    "series-insert-or-replace": (
        "INSERT OR REPLACE INTO series (series_id, series_key, source, metric, entity, unit, "
        "frequency, collection_mode) VALUES (1, 'forged', 's', 'm', 'e', 'u', 'f', 'c')"
    ),
}


@pytest.mark.parametrize("statement", list(MUTATIONS.values()), ids=list(MUTATIONS))
def test_mutation_is_blocked(conn: sa.Connection, statement: str) -> None:
    before = [_snapshot(conn, t) for t in ("series", "observations", "reveal_events")]
    with pytest.raises(sa.exc.DBAPIError, match="append-only"):
        conn.exec_driver_sql(statement)
    conn.rollback()
    assert [_snapshot(conn, t) for t in ("series", "observations", "reveal_events")] == before


def _snapshot(conn: sa.Connection, table: str) -> list[tuple]:
    return list(conn.exec_driver_sql(f"SELECT * FROM {table} ORDER BY 1"))


def test_store_triggers_exist(migrated_sqlite: sa.Engine) -> None:
    with migrated_sqlite.connect() as connection:
        names = set(
            connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            ).scalars()
        )
    assert set(STORE_SQLITE_TRIGGERS) <= names


# --- one transaction ----------------------------------------------------------------------


def test_failed_load_leaves_store_unchanged(migrated_sqlite: sa.Engine) -> None:
    good = [OBS, replace(OBS, period_date=date(2026, 6, 30), available_at=T_AVAIL - timedelta(90))]
    bad_last = replace(OBS, period_date=date(2026, 3, 31), available_at=datetime(2026, 4, 1))
    with pytest.raises(StoreError), migrated_sqlite.begin() as conn:
        _series(conn)
        assert insert_observations(conn, good, T_INGEST) == 2
        insert_observations(conn, [bad_last], T_INGEST)  # the last row fails
    assert _counts(migrated_sqlite) == (0, 0, 0)


def test_seed_load_failing_mid_write_leaves_store_unchanged(
    migrated_sqlite: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from calledit_data.db.settings import get_settings

    def boom(*_args: object, **_kwargs: object) -> int:
        raise RuntimeError("interrupted after the observations were inserted")

    monkeypatch.setattr(seed_loader, "insert_reveal_events", boom)
    with pytest.raises(RuntimeError, match="interrupted"):
        load_seed(
            migrated_sqlite,
            FIXTURE,
            RULES,
            get_settings(),
            now=T_INGEST,
            dry_run=False,
        )
    assert _counts(migrated_sqlite) == (0, 0, 0)
