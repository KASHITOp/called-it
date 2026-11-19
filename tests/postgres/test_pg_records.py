"""Real-builder typed-column parity on Postgres (LEDG-01).

The rules record, the prediction records and one gap record are built by the real
``build_prediction_payload`` / ``build_gap_payload`` and appended by ``run_lock`` into a guarded
``calledit_test_<hex>`` scratch schema (a Supabase scratch schema locally, the postgres:17
service in CI). Every typed column must equal the parsed payload.

Data is the SYNTHETIC fixture with one DMART quarter removed, so DMART gets a gap record while
ETERNAL and TITAN get predictions. Nothing here touches the live ``calledit`` schema.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
import time_machine
from calledit_data.calendar.fiscal import FiscalQuarter
from calledit_data.db.schema import predictions
from calledit_data.seed.loader import SeedCompanyRules, load_seed
from nowcaster.exit_codes import EXIT_PARTIAL
from nowcaster.lock import run_lock
from nowcaster.rules import append_rules_record
from nowcaster.universe import load_universe

from tests.conftest import REPO_ROOT
from tests.postgres.conftest import ScratchDb

pytestmark = pytest.mark.postgres

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "seed_fixture_SYNTHETIC.csv"
UNIVERSE_SOURCE = REPO_ROOT / "config" / "universe.toml"
SEED_TIME = datetime(2026, 11, 28, 3, 0, 0, tzinfo=UTC)
RULES_TIME = datetime(2026, 11, 28, 3, 30, 0, tzinfo=UTC)
LOCK_TIME = datetime(2026, 11, 28, 4, 0, 0, tzinfo=UTC)
LOCKED_AT = "2026-11-28T04:00:00Z"


def _rows(scratch: ScratchDb) -> list[sa.Row]:
    with scratch.engine.connect() as conn:
        return list(conn.execute(sa.select(predictions).order_by(predictions.c.seq)))


def test_typed_columns_equal_the_payload_for_real_prediction_and_gap_records(
    fresh_scratch: ScratchDb, tmp_path: Path
) -> None:
    prereg = tmp_path / "PREREGISTRATION.md"
    prereg.write_bytes(b"# Preregistration (postgres test fixture)\n")
    universe_path = tmp_path / "universe.toml"
    universe_path.write_bytes(UNIVERSE_SOURCE.read_bytes())
    lines = FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [ln for ln in lines if not (ln.startswith("DMART,") and ",Q4FY25," in ln)]
    assert len(kept) == len(lines) - 1
    seed = tmp_path / "seed_trimmed_SYNTHETIC.csv"
    seed.write_text("".join(kept), encoding="utf-8", newline="")

    settings = fresh_scratch.settings.model_copy(
        update={"prereg_path": prereg, "universe_path": universe_path}
    )
    loaded = load_universe(universe_path)
    rules = {
        c.ticker: SeedCompanyRules(isin=c.isin, has_business_update=c.has_business_update)
        for c in loaded.companies
    }
    load_seed(fresh_scratch.engine, seed, rules, settings, now=SEED_TIME, dry_run=False)
    appended_rules = append_rules_record(settings, None, None, RULES_TIME, False)
    assert appended_rules.appended is not None

    with time_machine.travel(LOCK_TIME, tick=False):
        report = run_lock(settings, FiscalQuarter.parse("Q3FY27"), "dispatch", now=LOCK_TIME)
    assert report.exit_code == EXIT_PARTIAL, report.message
    assert report.gaps == ["DMART"]

    rows = _rows(fresh_scratch)
    assert [r.record_kind for r in rows] == ["rules", "gap", "prediction", "prediction"]
    kinds_seen: set[str] = set()
    for row in rows[1:]:
        payload = json.loads(row.payload_canonical)
        kinds_seen.add(payload["record_kind"])
        assert row.record_kind == payload["record_kind"]
        assert row.ticker == payload["ticker"]
        assert row.fiscal_quarter == payload["fiscal_quarter"] == "Q3FY27"
        assert row.model_version == payload["model_version"]
        if row.record_kind == "prediction":
            for column, field in (
                (row.predicted_revenue_cr, "point_inr_cr"),
                (row.baseline_cr, "baseline_inr_cr"),
            ):
                assert column == Decimal(payload[field])
                assert column.as_tuple().exponent == -2  # NUMERIC scale kept
            assert payload["lo80_inr_cr"] == payload["hi80_inr_cr"] == "none"
            assert row.low_cr is None and row.high_cr is None
            assert (
                row.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") == payload["locked_at"] == LOCKED_AT
            )
            assert (
                hashlib.sha256(row.feature_snapshot.encode("ascii")).hexdigest()
                == payload["feature_snapshot_sha256"]
            )
        else:
            assert (row.predicted_revenue_cr, row.low_cr, row.high_cr, row.baseline_cr) == (
                None,
                None,
                None,
                None,
            )
            assert row.feature_snapshot is None
            assert row.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") == payload["attempted_at"]
            assert payload["reason_code"] == "missing_seed_quarter"
            assert payload["missing_quarters"] == "Q4FY25"
    assert kinds_seen == {"gap", "prediction"}  # both builders were exercised
