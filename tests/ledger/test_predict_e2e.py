"""Tracer: rules record -> `nowcast predict` -> chained predictions -> exported snapshots.

All data is the SYNTHETIC fixture (``SYNTHETIC TEST FIXTURE - not real data``) in a temp SQLite
store; no real prediction is locked. The hand-computed DMART point (10809.85) is the same
number as ``tests/nowcaster/test_baseline_e2e.py``.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from nowcaster.baseline import ETERNAL_LABEL, MODEL_VERSION
from nowcaster.cli import app
from nowcaster.exit_codes import EXIT_OK, EXIT_PARTIAL, EXIT_REFUSED
from nowcaster.ledger.records import (
    GAP_FIELDS,
    INTERVAL_LABEL,
    PREDICTION_FIELDS,
)

from tests.ledger.lock_helpers import FIXTURE, LOCK_TIME, PREREG_BYTES, LockEnv

LOCKED_AT = "2026-11-28T04:00:00Z"


def test_predict_appends_chained_predictions_after_the_rules_record(lock_env: LockEnv) -> None:
    lock_env.load_seed()
    assert lock_env.rules().exit_code == 0
    result = lock_env.predict()
    assert result.exit_code == EXIT_OK, result.output
    assert result.output.count(" LOCKED seq=") == 3

    rows = lock_env.rows()
    assert [r["seq"] for r in rows] == [0, 1, 2, 3]
    assert [r["record_kind"] for r in rows] == ["rules", "prediction", "prediction", "prediction"]
    assert [r["payload"]["ticker"] for r in rows[1:]] == ["DMART", "ETERNAL", "TITAN"]

    rules_hash = rows[0]["hash"]
    for previous, row in itertools.pairwise(rows):
        payload = row["payload"]
        assert payload["prev_hash"] == previous["hash"] == row["prev_hash"]
        assert payload["rules_hash"] == rules_hash
        assert payload["rules_seq"] == "0"
        assert payload["locked_at"] == payload["data_cutoff"] == LOCKED_AT
        assert sorted(payload) == sorted(PREDICTION_FIELDS)
        assert payload["scheme"] == "calledit-ledger-v1"
        assert payload["target"] == "rev_ops_consolidated_inr_cr"
        assert payload["lo80_inr_cr"] == payload["hi80_inr_cr"] == "none"
        assert payload["interval_label"] == INTERVAL_LABEL
        assert payload["model_version"] == MODEL_VERSION == "baseline-sqly@1.0.0"
        assert payload["lock_kind"] == "dispatch"
        assert payload["baseline_inr_cr"] == payload["point_inr_cr"]
        assert "gst2.0" in payload["breaks_in_window"].split("|")
        assert (
            payload["universe_sha256"] == hashlib.sha256(lock_env.universe.read_bytes()).hexdigest()
        )
        assert payload["run_id"] == "local"
        assert payload["code_git_sha"] == "none" or re.fullmatch(
            r"[0-9a-f]{40}", payload["code_git_sha"]
        )

    dmart, eternal, titan = (r["payload"] for r in rows[1:])
    assert dmart["point_inr_cr"] == "10809.85"
    assert dmart["baseline_method"] == "ttm_yoy" and dmart["pair_status"] == "none"
    assert dmart["labels"] == "none"
    assert dmart["earliest_plausible_reveal"] == "2026-12-31T18:30:00Z"  # 2027-01-01 00:00 IST
    assert eternal["baseline_method"] == "break_single_pair"
    assert ETERNAL_LABEL in eternal["labels"].split("|")
    assert titan["earliest_plausible_reveal"] == "2027-01-01T18:30:00Z"  # 2027-01-02 00:00 IST


def test_export_writes_ledger_and_snapshots_that_match_the_payload_hashes(
    lock_env: LockEnv, tmp_path: Path
) -> None:
    lock_env.load_seed()
    assert lock_env.rules().exit_code == 0
    assert lock_env.predict().exit_code == EXIT_OK
    out = tmp_path / "exported"
    exported = lock_env.invoke(["ledger", "export", "--out", str(out)], LOCK_TIME)
    assert exported.exit_code == 0, exported.output

    lines = (out / "ledger.jsonl").read_bytes().split(b"\n")
    assert lines.pop() == b""
    assert len(lines) == 4
    rows = lock_env.rows()
    for seq in (1, 2, 3):
        snapshot = (out / "snapshots" / f"{seq}.json").read_bytes()
        assert (
            hashlib.sha256(snapshot).hexdigest() == rows[seq]["payload"]["feature_snapshot_sha256"]
        )
        assert json.loads(snapshot)["ticker"] == rows[seq]["payload"]["ticker"]
    assert not (out / "snapshots" / "0.json").exists()


def test_typed_columns_equal_the_parsed_payload(lock_env: LockEnv) -> None:
    lock_env.load_seed()
    assert lock_env.rules().exit_code == 0
    assert lock_env.predict().exit_code == EXIT_OK
    for row in lock_env.rows()[1:]:
        payload = row["payload"]
        assert row["ticker"] == payload["ticker"]
        assert row["fiscal_quarter"] == payload["fiscal_quarter"] == "Q3FY27"
        assert row["model_version"] == payload["model_version"]
        assert row["predicted_revenue_cr"] == Decimal(payload["point_inr_cr"])
        assert row["baseline_cr"] == Decimal(payload["baseline_inr_cr"])
        assert row["low_cr"] is None and row["high_cr"] is None
        assert row["created_at"].isoformat() == "2026-11-28T04:00:00+00:00"
        assert (
            hashlib.sha256(row["feature_snapshot"].encode("ascii")).hexdigest()
            == payload["feature_snapshot_sha256"]
        )


def test_gap_record_has_null_money_columns_and_the_documented_fields(
    lock_env: LockEnv, tmp_path: Path
) -> None:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [ln for ln in lines if not ln.startswith("DMART,") or ",Q4FY25," not in ln]
    assert len(kept) == len(lines) - 1
    trimmed = tmp_path / "seed_trimmed_SYNTHETIC.csv"
    trimmed.write_text("".join(kept), encoding="utf-8", newline="")
    lock_env.load_seed(trimmed)
    assert lock_env.rules().exit_code == 0

    result = lock_env.predict()
    assert result.exit_code == EXIT_PARTIAL, result.output
    assert "DMART GAP seq=1 missing_seed_quarter: Q4FY25" in result.output
    rows = lock_env.rows()
    assert [r["record_kind"] for r in rows] == ["rules", "gap", "prediction", "prediction"]

    gap = rows[1]
    payload = gap["payload"]
    assert sorted(payload) == sorted(GAP_FIELDS)
    assert payload["ticker"] == "DMART" and payload["fiscal_quarter"] == "Q3FY27"
    assert payload["reason_code"] == "missing_seed_quarter"
    assert payload["missing_quarters"] == "Q4FY25"
    assert payload["attempted_at"] == LOCKED_AT
    assert payload["model_version"] == MODEL_VERSION
    assert payload["rules_hash"] == rows[0]["hash"] and payload["prev_hash"] == rows[0]["hash"]
    assert gap["created_at"].isoformat() == "2026-11-28T04:00:00+00:00"
    assert (gap["predicted_revenue_cr"], gap["low_cr"], gap["high_cr"], gap["baseline_cr"]) == (
        None,
        None,
        None,
        None,
    )
    assert gap["feature_snapshot"] is None
    assert (gap["ticker"], gap["fiscal_quarter"], gap["model_version"]) == (
        "DMART",
        "Q3FY27",
        MODEL_VERSION,
    )
    # the next company's prediction chains after the gap record
    assert rows[2]["payload"]["prev_hash"] == gap["hash"]


def test_predict_without_a_rules_record_is_refused(lock_env: LockEnv) -> None:
    lock_env.load_seed()
    result = lock_env.predict()
    assert result.exit_code == EXIT_REFUSED
    assert "rules record" in result.output
    assert lock_env.count() == 0


def test_predict_help_lists_the_exit_codes_and_only_two_options() -> None:
    from typer.testing import CliRunner

    result = CliRunner().invoke(app, ["predict", "--help"])
    assert result.exit_code == 0
    for code in ("0 every", "3 some", "4 nothing", "5 environment"):
        assert code in " ".join(result.output.split()), code
    options = set(re.findall(r"--[a-z-]+", result.output)) - {"--help"}
    assert options == {"--quarter", "--kind"}


def test_the_frozen_v1_field_sets() -> None:
    """The prediction and gap field sets become one-way at the first live lock (01-10)."""
    prediction = [
        *("scheme", "seq", "record_kind", "ticker", "isin", "fiscal_quarter", "target"),
        *("point_inr_cr", "lo80_inr_cr", "hi80_inr_cr", "interval_label", "baseline_inr_cr"),
        *("baseline_method", "pair_status", "growth", "model_version", "labels"),
        *("breaks_in_window", "feature_snapshot_sha256", "data_cutoff", "locked_at"),
        *("earliest_plausible_reveal", "lock_kind", "rules_seq", "rules_hash"),
        *("universe_sha256", "code_git_sha", "run_id", "prev_hash"),
    ]
    gap = [
        *("scheme", "seq", "record_kind", "ticker", "isin", "fiscal_quarter", "reason_code"),
        *("missing_quarters", "attempted_at", "model_version", "lock_kind", "rules_seq"),
        *("rules_hash", "universe_sha256", "code_git_sha", "run_id", "prev_hash"),
    ]
    assert list(PREDICTION_FIELDS) == prediction
    assert list(GAP_FIELDS) == gap


@pytest.mark.parametrize("kind", ["dispatch", "weekly", "final"])
def test_lock_kind_is_recorded(lock_env: LockEnv, kind: str) -> None:
    lock_env.load_seed()
    assert lock_env.rules().exit_code == 0
    assert lock_env.predict("Q3FY27", LOCK_TIME, "--kind", kind).exit_code == EXIT_OK
    assert {r["payload"]["lock_kind"] for r in lock_env.rows()[1:]} == {kind}


def test_prereg_bytes_constant_is_what_the_rules_record_hashes(lock_env: LockEnv) -> None:
    assert lock_env.rules().exit_code == 0
    payload = lock_env.rows()[0]["payload"]
    assert payload["document_sha256"] == hashlib.sha256(PREREG_BYTES).hexdigest()
