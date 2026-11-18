"""LEDG-04 and FOUND-04 on real Postgres (a guarded Supabase scratch schema locally, the
postgres:17 service in CI).

Every test that touches a database is marked ``postgres`` and uses a ``calledit_test_<hex>``
scratch schema from ``tests/postgres/conftest.py``. The two tests without that mark need no
database: they pin the scratch-schema guard, and compare the SQLite twin of the round trip.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from calledit_data.db.schema import observations, predictions, reveal_events, series
from nowcaster.ledger.canonical import (
    GENESIS_PREV_HASH,
    SCHEME,
    canonicalize,
    format_int,
    format_money,
    format_ts,
    sha256_hex,
)
from nowcaster.ledger.chain import Builder, ForkError, append_record
from nowcaster.ledger.export import export_ledger
from nowcaster.ledger.records import TypedColumns

from tests.ledger.helpers import T0, append_rules, raw_insert, rules_builder, stale_builder
from tests.postgres.conftest import (
    REFUSED_NAMES,
    ScratchDb,
    ScratchSchemaError,
    assert_scratch_schema,
)

postgres = pytest.mark.postgres

HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


# --- the guard (no database) ------------------------------------------------------------


@pytest.mark.parametrize("name", REFUSED_NAMES)
def test_assert_scratch_schema_refuses_protected_and_malformed_names(name: str) -> None:
    with pytest.raises(ScratchSchemaError):
        assert_scratch_schema(name)


def test_assert_scratch_schema_refuses_calledit_and_calledit_rehearsal() -> None:
    for protected in ("calledit", "calledit_rehearsal"):
        with pytest.raises(ScratchSchemaError):
            assert_scratch_schema(protected)


@pytest.mark.parametrize(
    "name", ["calledit_test_0123abcd", "calledit_test_" + "f" * 32, "calledit_test_0123456789ab"]
)
def test_assert_scratch_schema_accepts_scratch_names(name: str) -> None:
    assert assert_scratch_schema(name) == name


def test_assert_scratch_schema_refuses_non_strings() -> None:
    for bad in (None, 7, b"calledit_test_0123abcd"):
        with pytest.raises(ScratchSchemaError):
            assert_scratch_schema(bad)  # type: ignore[arg-type]


# --- shared helpers ---------------------------------------------------------------------

COLUMNS = "seq, record_kind, created_at, payload_canonical, hash, prev_hash"


def forged_values(seq: int = 0, hash_: str = HEX_A, prev_hash: str = HEX_B) -> str:
    return f"({seq}, 'rules', '2026-11-28T06:00:00Z', '{{}}', '{hash_}', '{prev_hash}')"


def snapshot(scratch: ScratchDb) -> list[tuple]:
    with scratch.engine.connect() as conn:
        return [
            tuple(row)
            for row in conn.exec_driver_sql(
                "SELECT seq, record_kind, payload_canonical, hash, prev_hash "
                f"FROM {scratch.q('predictions')} ORDER BY seq"
            )
        ]


def assert_blocked(scratch: ScratchDb, statement: str) -> None:
    before = snapshot(scratch)
    with scratch.engine.connect() as conn:
        with pytest.raises(sa.exc.DBAPIError, match="append-only"):
            conn.exec_driver_sql(statement)
        conn.rollback()
    assert snapshot(scratch) == before


@pytest.fixture(scope="module")
def seeded(pg_scratch: ScratchDb) -> ScratchDb:
    """The shared scratch schema with at least two ledger rows in it."""
    if pg_scratch.head() is None:
        append_rules(pg_scratch.engine, 2)
    assert len(snapshot(pg_scratch)) >= 2
    return pg_scratch


# --- append, export, verify -------------------------------------------------------------


@postgres
def test_append_three_records_export_and_verify_hashes(fresh_scratch: ScratchDb, tmp_path: Path):
    records = append_rules(fresh_scratch.engine, 3)
    assert [r.seq for r in records] == [0, 1, 2]
    assert records[0].prev_hash == GENESIS_PREV_HASH
    assert records[1].prev_hash == records[0].hash
    assert records[2].prev_hash == records[1].hash

    report = export_ledger(fresh_scratch.engine, tmp_path)
    assert (report.records, report.head_seq, report.head_hash) == (3, 2, records[2].hash)

    lines = (tmp_path / "ledger.jsonl").read_bytes().decode("ascii").split("\n")
    assert lines[-1] == "" and len(lines) == 4
    expected_prev = GENESIS_PREV_HASH
    for index, line in enumerate(lines[:-1]):
        payload = json.loads(line)
        assert canonicalize(payload) == line
        assert sha256_hex(line) == records[index].hash
        assert payload["prev_hash"] == expected_prev
        expected_prev = sha256_hex(line)


@postgres
def test_concurrent_append_record_calls_serialise_into_one_chain(
    fresh_scratch: ScratchDb, tmp_path: Path
):
    barrier = threading.Barrier(3)

    def worker(index: int) -> int:
        barrier.wait(timeout=60)
        record = append_record(
            fresh_scratch.engine, rules_builder(T0 + timedelta(minutes=index), note=f"w{index}")
        )
        return record.seq

    with ThreadPoolExecutor(max_workers=3) as pool:
        seqs = sorted(pool.map(worker, range(3)))
    assert seqs == [0, 1, 2]
    report = export_ledger(fresh_scratch.engine, tmp_path)  # verifies the whole chain
    assert report.records == 3


# --- LEDG-04: every bypass form is refused ----------------------------------------------

MUTATIONS = {
    "update": "UPDATE {t} SET record_kind = 'forged'",
    "delete": "DELETE FROM {t}",
    "truncate": "TRUNCATE {t}",
    "upsert": (
        f"INSERT INTO {{t}} ({COLUMNS}) VALUES {forged_values()} "
        "ON CONFLICT (seq) DO UPDATE SET record_kind = 'forged'"
    ),
    "merge-update": (
        "MERGE INTO {t} AS t USING (SELECT 0 AS seq) AS v ON t.seq = v.seq "
        "WHEN MATCHED THEN UPDATE SET record_kind = 'forged'"
    ),
    "merge-delete": (
        "MERGE INTO {t} AS t USING (SELECT 0 AS seq) AS v ON t.seq = v.seq WHEN MATCHED THEN DELETE"
    ),
}


@postgres
@pytest.mark.parametrize("statement", list(MUTATIONS.values()), ids=list(MUTATIONS))
def test_mutation_is_blocked(seeded: ScratchDb, statement: str) -> None:
    assert_blocked(seeded, statement.replace("{t}", seeded.q("predictions")))


@postgres
def test_truncate_empty_is_still_refused(fresh_scratch: ScratchDb) -> None:
    assert snapshot(fresh_scratch) == []
    assert_blocked(fresh_scratch, f"TRUNCATE {fresh_scratch.q('predictions')}")
    assert snapshot(fresh_scratch) == []


@postgres
def test_truncate_cascade_and_multi_table_forms_are_refused(seeded: ScratchDb) -> None:
    assert_blocked(seeded, f"TRUNCATE {seeded.q('predictions')} RESTART IDENTITY CASCADE")
    assert_blocked(seeded, f"TRUNCATE {seeded.q('predictions')}, {seeded.q('observations')}")


@postgres
def test_triggers_are_enable_always(seeded: ScratchDb) -> None:
    with seeded.engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT c.relname, t.tgname, t.tgenabled FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND NOT t.tgisinternal"
            ),
            {"schema": seeded.schema},
        ).all()
    by_name = {row[1]: str(row[2]) for row in rows}
    assert len(by_name) == 8
    assert set(by_name.values()) == {"A"}


@postgres
def test_replica_role_cannot_bypass_the_triggers(seeded: ScratchDb, capsys) -> None:
    """SET session_replication_role = replica must not skip an append-only trigger.

    Either the SET is denied (a hosted role without the privilege) or, if it succeeds, the
    ENABLE ALWAYS triggers still fire. The outcome is printed so the run records which one.
    """
    before = snapshot(seeded)
    with seeded.engine.connect() as conn:
        try:
            try:
                conn.exec_driver_sql("SET session_replication_role = replica")
            except sa.exc.DBAPIError as exc:
                assert "permission denied" in str(exc).lower()
                outcome = "SET denied by role privileges (permission denied)"
            else:
                assert conn.exec_driver_sql("SHOW session_replication_role").scalar_one() == (
                    "replica"
                )
                with pytest.raises(sa.exc.DBAPIError, match="append-only"):
                    conn.exec_driver_sql(
                        f"UPDATE {seeded.q('predictions')} SET record_kind = 'forged'"
                    )
                outcome = "SET allowed; UPDATE still refused (ENABLE ALWAYS)"
        finally:
            conn.rollback()
            conn.exec_driver_sql("RESET session_replication_role")
            conn.commit()
    with capsys.disabled():
        print(f"\nreplica_role outcome: {outcome}")
    assert snapshot(seeded) == before


# --- forks and races --------------------------------------------------------------------


@postgres
def test_fork_with_duplicate_prev_hash_is_rejected(fresh_scratch: ScratchDb) -> None:
    records = append_rules(fresh_scratch.engine, 2)
    before = snapshot(fresh_scratch)
    # Raw INSERT of a second child of record 0: seq 2 but prev_hash = hash of record 0.
    with fresh_scratch.engine.connect() as conn:
        with pytest.raises(sa.exc.IntegrityError, match="uq_predictions_prev_hash"):
            raw_insert(conn, seq=2, hash_=HEX_C, prev_hash=records[0].hash)
        conn.rollback()
        # A duplicate hash is refused too.
        with pytest.raises(sa.exc.IntegrityError, match="uq_predictions_hash"):
            raw_insert(conn, seq=2, hash_=records[1].hash, prev_hash=HEX_C)
        conn.rollback()
    assert snapshot(fresh_scratch) == before
    # The application layer refuses a stale writer before the database is reached.
    with pytest.raises(ForkError):
        append_record(fresh_scratch.engine, stale_builder(rules_builder(), records[0].hash))
    assert snapshot(fresh_scratch) == before


RACES = {
    "same-seq": ((1, HEX_A, HEX_B), (1, HEX_C, "d" * 64), "predictions_pkey"),
    "same-prev-hash": ((1, HEX_A, HEX_B), (2, HEX_C, HEX_B), "uq_predictions_prev_hash"),
}


@postgres
@pytest.mark.parametrize("race", list(RACES.values()), ids=list(RACES))
def test_seq_race_has_exactly_one_winner(fresh_scratch: ScratchDb, race) -> None:
    """Two writers race the same position on separate connections: the loser is rejected."""
    first, second, constraint = race
    append_rules(fresh_scratch.engine, 1)
    barrier = threading.Barrier(2)

    def writer(values: tuple[int, str, str]) -> str:
        seq, hash_, prev_hash = values
        barrier.wait(timeout=60)
        try:
            with fresh_scratch.engine.begin() as conn:
                raw_insert(conn, seq=seq, hash_=hash_, prev_hash=prev_hash)
        except sa.exc.IntegrityError as exc:
            assert constraint in str(exc)
            return "rejected"
        return "won"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(writer, (first, second)))
    assert outcomes == ["rejected", "won"]
    assert len(snapshot(fresh_scratch)) == 2


# --- typed columns equal the payload ----------------------------------------------------

RULES_HASH = sha256_hex("rules")
UNIVERSE_HASH = sha256_hex("universe")
LOCKED_AT = datetime(2026, 11, 28, 4, 0, 0, tzinfo=UTC)
SNAPSHOT_TEXT = canonicalize({"series": ["rev.consolidated.DMART"], "rows": ["1", "2"]})


def prediction_builder() -> Builder:
    """A prediction-shaped record: the field set of the 01-07 interface, hand-built."""

    def build(seq: int, prev_hash: str) -> tuple[dict, TypedColumns]:
        payload = {
            "scheme": SCHEME,
            "seq": format_int(seq),
            "record_kind": "prediction",
            "ticker": "DMART",
            "isin": "INE192R01011",
            "fiscal_quarter": "Q3FY27",
            "target": "rev_ops_consolidated_inr_cr",
            "point_inr_cr": format_money(Decimal(110)),
            "lo80_inr_cr": "none",
            "hi80_inr_cr": "none",
            "interval_label": "none (baseline-only, no out-of-sample residuals yet)",
            "baseline_inr_cr": format_money(Decimal(110)),
            "baseline_method": "same-quarter-last-year-growth",
            "pair_status": "paired",
            "growth": "0.052300",
            "model_version": "baseline-sqly@1.0.0",
            "labels": "none",
            "breaks_in_window": "none",
            "feature_snapshot_sha256": sha256_hex(SNAPSHOT_TEXT),
            "data_cutoff": format_ts(LOCKED_AT),
            "locked_at": format_ts(LOCKED_AT),
            "earliest_plausible_reveal": "2026-12-31T18:30:00Z",
            "lock_kind": "dispatch",
            "rules_seq": "0",
            "rules_hash": RULES_HASH,
            "universe_sha256": UNIVERSE_HASH,
            "code_git_sha": "none",
            "run_id": "local",
            "prev_hash": prev_hash,
        }
        typed = TypedColumns(
            record_kind="prediction",
            created_at=LOCKED_AT,
            ticker="DMART",
            fiscal_quarter="Q3FY27",
            model_version="baseline-sqly@1.0.0",
            predicted_revenue_cr=Decimal("110.00"),
            baseline_cr=Decimal("110.00"),
            feature_snapshot=SNAPSHOT_TEXT,
        )
        return payload, typed

    return build


def gap_builder() -> Builder:
    """A gap-shaped record (a refused lock, D-08): all money columns NULL."""

    def build(seq: int, prev_hash: str) -> tuple[dict, TypedColumns]:
        payload = {
            "scheme": SCHEME,
            "seq": format_int(seq),
            "record_kind": "gap",
            "ticker": "TITAN",
            "isin": "INE280A01028",
            "fiscal_quarter": "Q3FY27",
            "reason_code": "missing_seed_quarter",
            "missing_quarters": "Q3FY26|Q4FY26",
            "attempted_at": format_ts(LOCKED_AT),
            "model_version": "baseline-sqly@1.0.0",
            "lock_kind": "dispatch",
            "rules_seq": "0",
            "rules_hash": RULES_HASH,
            "universe_sha256": UNIVERSE_HASH,
            "code_git_sha": "none",
            "run_id": "local",
            "prev_hash": prev_hash,
        }
        typed = TypedColumns(
            record_kind="gap",
            created_at=LOCKED_AT,
            ticker="TITAN",
            fiscal_quarter="Q3FY27",
            model_version="baseline-sqly@1.0.0",
        )
        return payload, typed

    return build


MONEY_COLUMNS = (
    ("predicted_revenue_cr", "point_inr_cr"),
    ("low_cr", "lo80_inr_cr"),
    ("high_cr", "hi80_inr_cr"),
    ("baseline_cr", "baseline_inr_cr"),
)


@postgres
@pytest.mark.parametrize("kind", ["prediction", "gap"])
def test_typed_columns_match_payload(pg_scratch: ScratchDb, kind: str) -> None:
    builder = prediction_builder() if kind == "prediction" else gap_builder()
    record = append_record(pg_scratch.engine, builder)
    with pg_scratch.engine.connect() as conn:
        row = conn.execute(sa.select(predictions).where(predictions.c.seq == record.seq)).one()
        raw = conn.execute(
            sa.text(
                "SELECT predicted_revenue_cr::text, low_cr::text, high_cr::text, "
                "baseline_cr::text, pg_typeof(predicted_revenue_cr)::text, "
                f"pg_typeof(created_at)::text FROM {pg_scratch.q('predictions')} "
                "WHERE seq = :seq"
            ),
            {"seq": record.seq},
        ).one()
    payload = json.loads(row.payload_canonical)
    assert row.payload_canonical == record.payload_canonical
    assert sha256_hex(row.payload_canonical) == row.hash == record.hash
    assert row.record_kind == payload["record_kind"] == kind
    assert (row.ticker, row.fiscal_quarter) == (payload["ticker"], payload["fiscal_quarter"])
    assert row.model_version == payload["model_version"]
    assert raw[4] == "numeric" and raw[5] == "timestamp with time zone"

    for index, (column, key) in enumerate(MONEY_COLUMNS):
        typed_value, raw_text = getattr(row, column), raw[index]
        text = payload.get(key, "none")
        if text == "none":
            assert typed_value is None and raw_text is None, column
        else:
            assert typed_value == Decimal(text), column
            assert raw_text == text, f"{column}: NUMERIC text {raw_text!r} != payload {text!r}"

    stamp = payload["locked_at"] if kind == "prediction" else payload["attempted_at"]
    assert row.created_at == datetime.strptime(stamp, TS_FORMAT).replace(tzinfo=UTC)
    assert row.created_at.utcoffset() == timedelta(0)

    if kind == "prediction":
        assert Decimal(payload["point_inr_cr"]) == Decimal("110.00")
        assert str(row.predicted_revenue_cr) == "110.00" == payload["point_inr_cr"]
        assert payload["lo80_inr_cr"] == payload["hi80_inr_cr"] == "none"
        assert sha256_hex(row.feature_snapshot) == payload["feature_snapshot_sha256"]
    else:
        assert all(getattr(row, column) is None for column, _ in MONEY_COLUMNS)
        assert row.feature_snapshot is None


# --- UTCDateTime and money round trips --------------------------------------------------

MICRO = datetime(2026, 11, 28, 6, 30, 15, 123456, tzinfo=UTC)
EXACT = Decimal("12345678901234.123456")


def round_trip(engine: sa.Engine, tag: str) -> tuple[datetime, Decimal]:
    """Write a microsecond instant and a 6 dp amount, and read them back through the app types."""
    with engine.begin() as conn:
        conn.execute(
            sa.insert(reveal_events).values(
                ticker="DMART",
                fiscal_quarter="Q3FY27",
                event_kind="results",
                event_at=MICRO,
                availability_basis="exchange_timestamp",
                source_ref=f"roundtrip-{tag}",
                ingested_at=MICRO,
                content_hash=sha256_hex(f"roundtrip-{tag}"),
            )
        )
        series_id = conn.execute(
            sa.insert(series).values(
                series_key=f"roundtrip.{tag}",
                source="test",
                metric="m",
                entity="e",
                unit="inr_cr",
                frequency="quarterly",
                collection_mode="seed",
            )
        ).inserted_primary_key[0]
        conn.execute(
            sa.insert(observations).values(
                series_id=series_id,
                period_date=date(2026, 9, 30),
                value=EXACT,
                available_at=MICRO,
                availability_basis="exchange_timestamp",
                ingested_at=MICRO,
                vintage="first_reported",
                source_ref="roundtrip",
                source_kind="seed_csv",
                content_hash=sha256_hex(f"obs-{tag}"),
            )
        )
    with engine.connect() as conn:
        event_at = conn.execute(
            sa.select(reveal_events.c.event_at).where(
                reveal_events.c.content_hash == sha256_hex(f"roundtrip-{tag}")
            )
        ).scalar_one()
        value = conn.execute(
            sa.select(observations.c.value).where(
                observations.c.content_hash == sha256_hex(f"obs-{tag}")
            )
        ).scalar_one()
    return event_at, value


@postgres
def test_utc_datetime_and_money_round_trip_exactly(pg_scratch: ScratchDb) -> None:
    event_at, value = round_trip(pg_scratch.engine, "pg")
    assert event_at == MICRO and event_at.microsecond == 123456
    assert event_at.utcoffset() == timedelta(0)
    assert value == EXACT and isinstance(value, Decimal)
    with pg_scratch.engine.connect() as conn:
        stored = conn.execute(
            sa.text(
                f"SELECT event_at::text FROM {pg_scratch.q('reveal_events')} "
                "WHERE content_hash = :h"
            ),
            {"h": sha256_hex("roundtrip-pg")},
        ).scalar_one()
    assert ".123456" in stored


def test_utc_datetime_and_money_round_trip_identically_on_sqlite(
    migrated_sqlite: sa.Engine,
) -> None:
    event_at, value = round_trip(migrated_sqlite, "sqlite")
    assert event_at == MICRO and event_at.microsecond == 123456
    assert event_at.utcoffset() == timedelta(0)
    assert value == EXACT and isinstance(value, Decimal)
