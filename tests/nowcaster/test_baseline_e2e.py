"""Tracer: SYNTHETIC fixture CSV -> store -> PointInTimeReader -> compute_baseline -> CLI.

The fixture is synthetic test data (``SYNTHETIC TEST FIXTURE - not real data``); the numbers
asserted here are hand-computed from it and are never real history.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
import time_machine
from nowcaster.cli import app
from typer.testing import CliRunner

from tests.conftest import REPO_ROOT

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "seed_fixture_SYNTHETIC.csv"
UNIVERSE = REPO_ROOT / "config" / "universe.toml"
LOCK_DAY = datetime(2026, 11, 28, 4, 0, 0, tzinfo=UTC)
CENT = Decimal("0.01")


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("CALLEDIT_UNIVERSE_PATH", str(UNIVERSE))
    return CliRunner()


def _blocks(output: str) -> dict[str, dict[str, str]]:
    """``company X`` blocks of the CLI output as {ticker: {key: value}}."""
    blocks: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in output.splitlines():
        if line.startswith("company "):
            current = blocks.setdefault(line.split()[1], {})
        elif current is not None and line.startswith("  "):
            key, _, rest = line.strip().partition(": ")
            current[key.split(" ")[0]] = rest
    return blocks


def _row_counts(engine: sa.Engine) -> dict[str, int]:
    with engine.connect() as conn:
        tables = sa.inspect(conn).get_table_names()
        return {t: conn.exec_driver_sql(f'SELECT COUNT(*) FROM "{t}"').scalar_one() for t in tables}


def _load_fixture(runner: CliRunner) -> None:
    with time_machine.travel(LOCK_DAY, tick=False):
        loaded = runner.invoke(app, ["seed", "load", "--csv", str(FIXTURE)])
    assert loaded.exit_code == 0, loaded.output


def _baseline(runner: CliRunner) -> str:
    with time_machine.travel(LOCK_DAY, tick=False):
        result = runner.invoke(app, ["baseline", "--quarter", "Q3FY27"])
    assert result.exit_code == 0, result.output
    return result.output


def test_dmart_ttm_baseline_matches_hand_computation(
    migrated_sqlite: sa.Engine, runner: CliRunner
) -> None:
    _load_fixture(runner)
    before = _row_counts(migrated_sqlite)
    out = _baseline(runner)
    assert _row_counts(migrated_sqlite) == before  # read-only: nothing written anywhere

    # Fixture DMART revenue (INR crore): Q3FY25..Q2FY26 = 10000, 10100, 10200, 10300 (prior);
    # Q3FY26..Q2FY27 = 10400, 10500, 10600, 10700 (recent). SQLY = Q3FY26 = 10400.
    prior = Decimal(10000) + Decimal(10100) + Decimal(10200) + Decimal(10300)
    recent = Decimal(10400) + Decimal(10500) + Decimal(10600) + Decimal(10700)
    assert (prior, recent) == (Decimal(40600), Decimal(42200))
    growth = recent / prior - 1  # 1600 / 40600, unrounded
    expected = (Decimal(10400) * (1 + growth)).quantize(CENT, rounding=ROUND_HALF_EVEN)
    assert expected == Decimal("10809.85")

    dmart = _blocks(out)["DMART"]
    assert dmart["method"] == "ttm_yoy"
    assert dmart["pair_status"] == "none"
    assert dmart["sqly"] == "Q3FY26"
    assert dmart["window"] == "Q3FY25..Q2FY27"
    assert Decimal(dmart["point_inr_cr"]) == expected
    assert dmart["growth"] == "0.039409"
    assert dmart["labels"] == "none"
    assert dmart["breaks_in_window"] == "gst2.0"
    assert len(dmart["snapshot_sha256"]) == 64


def test_eternal_and_titan_blocks(migrated_sqlite: sa.Engine, runner: CliRunner) -> None:
    _load_fixture(runner)
    blocks = _blocks(_baseline(runner))
    assert set(blocks) == {"DMART", "ETERNAL", "TITAN"}

    titan = blocks["TITAN"]
    assert titan["method"] == "ttm_yoy"
    titan_point = (Decimal(24000) * (Decimal(102000) / Decimal(86000))).quantize(CENT)
    assert Decimal(titan["point_inr_cr"]) == titan_point

    # ETERNAL break range Q1FY26..Q3FY26 puts window quarters in-range and leaves no
    # post-post pair, so the single pair (Q2FY27, Q2FY26) is used, least straddling.
    eternal = blocks["ETERNAL"]
    assert eternal["method"] == "break_single_pair"
    assert eternal["pair"] == "(Q2FY27, Q2FY26)"
    assert eternal["pair_status"] == "least_straddling"
    eternal_point = (Decimal(7000) * (Decimal(8500) / Decimal(6500))).quantize(CENT)
    assert Decimal(eternal["point_inr_cr"]) == eternal_point
    assert eternal["labels"] == "low confidence: post-break comparables limited"
    assert eternal["breaks_in_window"] == "eternal-blinkit-inventory, gst2.0"


def test_snapshot_hash_is_deterministic_across_runs(
    migrated_sqlite: sa.Engine, runner: CliRunner
) -> None:
    _load_fixture(runner)
    first = _blocks(_baseline(runner))
    second = _blocks(_baseline(runner))
    for ticker in ("DMART", "ETERNAL", "TITAN"):
        assert first[ticker]["snapshot_sha256"] == second[ticker]["snapshot_sha256"]
    assert len({b["snapshot_sha256"] for b in first.values()}) == 3


def test_empty_store_refuses_every_company_and_exits_zero(
    migrated_sqlite: sa.Engine, runner: CliRunner
) -> None:
    out = _baseline(runner)
    assert out.count("REFUSED missing_seed_quarter") == 3
    assert set(_blocks(out)) == {"DMART", "ETERNAL", "TITAN"}
    assert "Q3FY25, Q4FY25, Q1FY26, Q2FY26, Q3FY26, Q4FY26, Q1FY27, Q2FY27" in out


def test_missing_database_refuses_without_creating_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, runner: CliRunner
) -> None:
    db = tmp_path / "absent.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("CALLEDIT_ENV", "test")
    out = _baseline(runner)
    assert out.count("REFUSED missing_seed_quarter") == 3
    assert not db.exists()


def test_bad_quarter_label_exits_2(runner: CliRunner) -> None:
    result = runner.invoke(app, ["baseline", "--quarter", "nonsense"])
    assert result.exit_code == 2
