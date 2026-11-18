"""The point-in-time store triggers and ``nowcast db check`` on real Postgres (FOUND-04, PIT-02).

Runs against guarded ``calledit_test_<hex>`` scratch schemas only (see conftest.py). The
``check_scratch`` schema is shared by the db-check tests; each test that weakens it restores it
in a ``finally`` block, so the tests do not depend on their order.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic import command
from calledit_data.db.check import run_db_check
from calledit_data.db.schema import PG_REQUIRED_TRIGGERS
from calledit_data.store.writer import (
    ObservationIn,
    RevealEventIn,
    ensure_series,
    insert_observations,
    insert_reveal_events,
)
from nowcaster.cli import app
from sqlalchemy.engine import make_url
from typer.testing import CliRunner

from tests.conftest import alembic_config
from tests.postgres.conftest import ScratchDb, ScratchFactory

postgres = pytest.mark.postgres

INGESTED = datetime(2026, 11, 20, 3, 0, 0, tzinfo=UTC)
AVAILABLE = datetime(2026, 10, 11, 12, 0, 0, tzinfo=UTC)
runner = CliRunner()


def seed_store(scratch: ScratchDb) -> None:
    """One series, one observation and one reveal event, written through the real writer."""
    with scratch.engine.begin() as conn:
        ensure_series(
            conn,
            "rev.consolidated.DMART",
            "seed_csv",
            "revenue_from_operations",
            "DMART",
            "inr_cr",
            "quarterly",
            "seed",
        )
        insert_observations(
            conn,
            [
                ObservationIn(
                    series_key="rev.consolidated.DMART",
                    period_date=date(2026, 9, 30),
                    value=Decimal("15872.940000"),
                    available_at=AVAILABLE,
                    availability_basis="exchange_timestamp",
                    source_ref="https://example.invalid/results.pdf",
                    vintage="first_reported",
                    source_kind="seed_csv",
                )
            ],
            INGESTED,
        )
        insert_reveal_events(
            conn,
            [
                RevealEventIn(
                    ticker="DMART",
                    fiscal_quarter="Q2FY27",
                    event_kind="results",
                    event_at=AVAILABLE,
                    availability_basis="exchange_timestamp",
                    source_ref="https://example.invalid/results.pdf",
                )
            ],
            INGESTED,
        )


def count(scratch: ScratchDb, table: str) -> int:
    with scratch.engine.connect() as conn:
        return conn.exec_driver_sql(f"SELECT count(*) FROM {scratch.q(table)}").scalar_one()


@pytest.fixture(scope="module")
def store(pg_scratch: ScratchDb) -> ScratchDb:
    seed_store(pg_scratch)
    assert count(pg_scratch, "series") >= 1
    assert count(pg_scratch, "observations") >= 1
    assert count(pg_scratch, "reveal_events") >= 1
    return pg_scratch


@pytest.fixture(scope="module")
def check_scratch(pg_scratch_factory: ScratchFactory) -> ScratchDb:
    return pg_scratch_factory.create()


STORE_MUTATIONS = {
    "observations-update": "UPDATE {t} SET vintage = 'forged'",
    "observations-delete": "DELETE FROM {t}",
    "observations-truncate": "TRUNCATE {t}",
    "reveal_events-update": "UPDATE {t} SET event_kind = 'forged'",
    "reveal_events-delete": "DELETE FROM {t}",
    "reveal_events-truncate": "TRUNCATE {t}",
    "series-update": "UPDATE {t} SET unit = 'forged'",
    "series-delete": "DELETE FROM {t}",
    # series is referenced by observations: CASCADE keeps Postgres from raising the FK error first.
    "series-truncate": "TRUNCATE {t} CASCADE",
}


@postgres
@pytest.mark.parametrize("case", list(STORE_MUTATIONS), ids=list(STORE_MUTATIONS))
def test_store_mutation_is_refused(store: ScratchDb, case: str) -> None:
    table = case.split("-", 1)[0]
    statement = STORE_MUTATIONS[case].replace("{t}", store.q(table))
    before = count(store, table)
    with store.engine.connect() as conn:
        with pytest.raises(sa.exc.DBAPIError, match="append-only"):
            conn.exec_driver_sql(statement)
        conn.rollback()
    assert count(store, table) == before >= 1


@postgres
def test_restating_a_value_adds_a_row_and_keeps_the_original(store: ScratchDb) -> None:
    with store.engine.begin() as conn:
        inserted = insert_observations(
            conn,
            [
                ObservationIn(
                    series_key="rev.consolidated.DMART",
                    period_date=date(2026, 9, 30),
                    value=Decimal("15900.000000"),
                    available_at=datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC),
                    availability_basis="exchange_timestamp",
                    source_ref="https://example.invalid/restated.pdf",
                    vintage="restated",
                    source_kind="seed_csv",
                )
            ],
            INGESTED,
        )
    assert inserted == 1
    with store.engine.connect() as conn:
        values = sorted(
            conn.exec_driver_sql(
                f"SELECT value::text FROM {store.q('observations')} WHERE period_date = '2026-09-30'"
            ).scalars()
        )
    assert "15872.940000" in values and "15900.000000" in values


@contextmanager
def weakened(scratch: ScratchDb, weaken: str, *restore: str) -> Iterator[None]:
    """Apply owner-level DDL that weakens the schema, and always put it back."""
    with scratch.engine.begin() as conn:
        conn.exec_driver_sql(weaken)
    try:
        yield
    finally:
        with scratch.engine.begin() as conn:
            for statement in restore:
                conn.exec_driver_sql(statement)


def check_lines(scratch: ScratchDb) -> tuple[bool, list[str]]:
    report = run_db_check(scratch.settings)
    return report.ok, report.lines


@postgres
def test_run_db_check_is_ok_on_a_fresh_scratch_schema(fresh_scratch: ScratchDb) -> None:
    ok, lines = check_lines(fresh_scratch)
    assert ok, lines
    assert "backend: postgresql" in lines
    assert "connect: ok" in lines
    assert lines[-1] == "result: OK"
    for name in PG_REQUIRED_TRIGGERS:
        assert f"trigger {name}: ok" in lines
    assert "replication_role: ok" in lines
    assert all(f"rls {t}: ok" in lines for t in ("predictions", "series", "observations"))
    assert "rls reveal_events: ok" in lines
    assert not [line for line in lines if "FAIL" in line]


@postgres
def test_db_check_fails_on_disabled_trigger(check_scratch: ScratchDb) -> None:
    """The owner may DISABLE a trigger (the honest limit, Pitfall 11); db check must notice."""
    table = check_scratch.q("predictions")
    with weakened(
        check_scratch,
        f"ALTER TABLE {table} DISABLE TRIGGER predictions_no_update_delete",
        f"ALTER TABLE {table} ENABLE ALWAYS TRIGGER predictions_no_update_delete",
    ):
        ok, lines = check_lines(check_scratch)
        assert not ok
        failing = [line for line in lines if "FAIL" in line]
        assert len(failing) == 1 and failing[0].startswith(
            "trigger predictions_no_update_delete: FAIL"
        ), lines
        assert lines[-1] == "result: FAIL"
    ok, lines = check_lines(check_scratch)
    assert ok, lines


@postgres
def test_db_check_fails_on_origin_only_trigger(check_scratch: ScratchDb) -> None:
    """ENABLE (not ALWAYS) would let session_replication_role=replica skip the trigger."""
    table = check_scratch.q("observations")
    with weakened(
        check_scratch,
        f"ALTER TABLE {table} ENABLE TRIGGER observations_no_truncate",
        f"ALTER TABLE {table} ENABLE ALWAYS TRIGGER observations_no_truncate",
    ):
        ok, lines = check_lines(check_scratch)
        assert not ok
        assert any(line.startswith("trigger observations_no_truncate: FAIL") for line in lines)
    assert check_lines(check_scratch)[0]


@postgres
def test_db_check_fails_on_missing_trigger(check_scratch: ScratchDb) -> None:
    table = check_scratch.q("reveal_events")
    function = check_scratch.q("forbid_mutation")
    with weakened(
        check_scratch,
        f"DROP TRIGGER reveal_events_no_truncate ON {table}",
        f"CREATE TRIGGER reveal_events_no_truncate BEFORE TRUNCATE ON {table} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION {function}()",
        f"ALTER TABLE {table} ENABLE ALWAYS TRIGGER reveal_events_no_truncate",
    ):
        ok, lines = check_lines(check_scratch)
        assert not ok
        assert any(line.startswith("trigger reveal_events_no_truncate: FAIL") for line in lines)
    assert check_lines(check_scratch)[0]


@postgres
def test_db_check_fails_when_rls_is_off(check_scratch: ScratchDb) -> None:
    table = check_scratch.q("series")
    with weakened(
        check_scratch,
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
    ):
        ok, lines = check_lines(check_scratch)
        assert not ok
        assert any(line.startswith("rls series: FAIL") for line in lines)
    assert check_lines(check_scratch)[0]


@postgres
def test_second_alembic_upgrade_is_a_no_op_and_keeps_enable_always(
    check_scratch: ScratchDb,
) -> None:
    cfg = alembic_config()
    with check_scratch.engine.connect() as conn:
        cfg.attributes["connection"] = conn
        cfg.attributes["schema"] = check_scratch.schema
        command.upgrade(cfg, "head")
        conn.commit()
    with check_scratch.engine.connect() as conn:
        version = conn.exec_driver_sql(
            f"SELECT version_num FROM {check_scratch.q('alembic_version')}"
        ).scalar_one()
        states = conn.execute(
            sa.text(
                "SELECT t.tgenabled FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND NOT t.tgisinternal"
            ),
            {"schema": check_scratch.schema},
        ).scalars()
        states = [str(state) for state in states]
    assert version == "0002"
    assert states == ["A"] * 8
    assert check_lines(check_scratch)[0]


@postgres
def test_cli_db_check_prints_ok_without_any_url_part(
    fresh_scratch: ScratchDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = fresh_scratch.settings.database_url.get_secret_value()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("CALLEDIT_ENV", "test")
    monkeypatch.setenv("CALLEDIT_DB_SCHEMA", fresh_scratch.schema)
    result = runner.invoke(app, ["db", "check"])
    assert result.exit_code == 0, result.output
    assert "backend: postgresql" in result.output
    assert f"schema: {fresh_scratch.schema}" in result.output
    assert "result: OK" in result.output
    parsed = make_url(url)
    assert url not in result.output
    for part in (parsed.host, parsed.password):
        if part:
            assert part not in result.output
    assert "supabase.com" not in result.output
