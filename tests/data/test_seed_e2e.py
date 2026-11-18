"""Tracer: the SYNTHETIC fixture CSV -> insert-only store -> PointInTimeReader.

The fixture is synthetic test data (source_url https://example.invalid/synthetic-fixture,
notes 'SYNTHETIC TEST FIXTURE - not real data'); it is never real history.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from calledit_data.db.schema import observations, reveal_events
from calledit_data.pit.reader import PointInTimeReader
from nowcaster.cli import app
from typer.testing import CliRunner

from tests.conftest import REPO_ROOT

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "seed_fixture_SYNTHETIC.csv"
UNIVERSE = REPO_ROOT / "config" / "universe.toml"

# DMART Q2FY27 results in the fixture: 2026-10-11T17:30+05:30 = 2026-10-11T12:00:00Z.
DMART_Q2FY27_RESULTS = datetime(2026, 10, 11, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("CALLEDIT_UNIVERSE_PATH", str(UNIVERSE))
    return CliRunner()


def _count(engine: sa.Engine, table: sa.Table) -> int:
    with engine.connect() as conn:
        return conn.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()


def test_fixture_is_labelled_synthetic() -> None:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()[1:]
    assert len(lines) == 24
    for line in lines:
        assert "https://example.invalid/synthetic-fixture" in line
        assert line.endswith("SYNTHETIC TEST FIXTURE - not real data")


def test_csv_to_reader_end_to_end(migrated_sqlite: sa.Engine, runner: CliRunner) -> None:
    dry = runner.invoke(app, ["seed", "load", "--dry-run", "--csv", str(FIXTURE)])
    assert dry.exit_code == 0, dry.output
    assert "24 rows seen, 0 observations inserted" in dry.output
    assert _count(migrated_sqlite, observations) == 0

    real = runner.invoke(app, ["seed", "load", "--csv", str(FIXTURE)])
    assert real.exit_code == 0, real.output
    assert "24 rows seen, 24 observations inserted" in real.output
    assert _count(migrated_sqlite, observations) == 24
    # 24 results events + 16 business updates (DMART and TITAN only).
    assert _count(migrated_sqlite, reveal_events) == 40

    reader = PointInTimeReader(migrated_sqlite, datetime(2026, 11, 28, tzinfo=UTC), "backtest")
    rows = reader.series("rev.consolidated.DMART")
    assert len(rows) == 8
    assert [r.period_date for r in rows] == sorted(r.period_date for r in rows)
    assert rows[-1].period_date.isoformat() == "2026-09-30"
    assert all(r.source_kind == "seed_csv" for r in rows)

    before = PointInTimeReader(
        migrated_sqlite, DMART_Q2FY27_RESULTS - timedelta(seconds=1), "backtest"
    )
    assert len(before.series("rev.consolidated.DMART")) == 7
    at = PointInTimeReader(migrated_sqlite, DMART_Q2FY27_RESULTS, "backtest")
    assert len(at.series("rev.consolidated.DMART")) == 7  # strict <: not yet known


def test_reload_is_idempotent(migrated_sqlite: sa.Engine, runner: CliRunner) -> None:
    first = runner.invoke(app, ["seed", "load", "--csv", str(FIXTURE)])
    assert first.exit_code == 0, first.output
    second = runner.invoke(app, ["seed", "load", "--csv", str(FIXTURE)])
    assert second.exit_code == 0, second.output
    assert "0 observations inserted, 0 reveal events inserted" in second.output
    assert _count(migrated_sqlite, observations) == 24
