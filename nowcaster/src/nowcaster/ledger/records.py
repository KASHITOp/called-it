"""Record builders for calledit-ledger-v1.

Record kinds: ``rules`` (seq 0 = PREREGISTRATION.md hash; later rules changes), ``prediction``
and ``gap`` (a refused lock, D-08). ``annotation`` and ``universe_change`` are reserved. New
kinds may be added by a later rules record without changing the canonicalisation.

Every builder emits a fixed, non-empty field set; absent values are the literal ``none``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from calledit_data.calendar.fiscal import FiscalQuarter

from nowcaster.baseline import MODEL_VERSION, BaselineRefusal, BaselineResult
from nowcaster.ledger.canonical import (
    SCHEME,
    CanonicalError,
    format_int,
    format_money,
    format_ts,
    is_hex64,
    validate,
)
from nowcaster.universe import Company

RECORD_KINDS = ("rules", "prediction", "gap")
RESERVED_RECORD_KINDS = ("annotation", "universe_change")
LOCK_KINDS = ("dispatch", "weekly", "final")
TARGET = "rev_ops_consolidated_inr_cr"
INTERVAL_LABEL = "none (baseline-only, no out-of-sample residuals yet)"
_NONE = "none"
_JOIN = "|"
_GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")

RULES_FIELDS = (
    "scheme",
    "seq",
    "record_kind",
    "rules_id",
    "document_path",
    "document_sha256",
    "document_git_commit",
    "universe_path",
    "universe_sha256",
    "recorded_at",
    "run_id",
    "prev_hash",
)

PREDICTION_FIELDS = (
    "scheme",
    "seq",
    "record_kind",
    "ticker",
    "isin",
    "fiscal_quarter",
    "target",
    "point_inr_cr",
    "lo80_inr_cr",
    "hi80_inr_cr",
    "interval_label",
    "baseline_inr_cr",
    "baseline_method",
    "pair_status",
    "growth",
    "model_version",
    "labels",
    "breaks_in_window",
    "feature_snapshot_sha256",
    "data_cutoff",
    "locked_at",
    "earliest_plausible_reveal",
    "lock_kind",
    "rules_seq",
    "rules_hash",
    "universe_sha256",
    "code_git_sha",
    "run_id",
    "prev_hash",
)

GAP_FIELDS = (
    "scheme",
    "seq",
    "record_kind",
    "ticker",
    "isin",
    "fiscal_quarter",
    "reason_code",
    "missing_quarters",
    "attempted_at",
    "model_version",
    "lock_kind",
    "rules_seq",
    "rules_hash",
    "universe_sha256",
    "code_git_sha",
    "run_id",
    "prev_hash",
)


@dataclass(frozen=True)
class TypedColumns:
    """The typed (queryable) columns stored next to ``payload_canonical``.

    They must always equal what the canonical payload says (asserted in tests).
    """

    record_kind: str
    created_at: datetime
    ticker: str | None = None
    fiscal_quarter: str | None = None
    model_version: str | None = None
    predicted_revenue_cr: Decimal | None = None
    low_cr: Decimal | None = None
    high_cr: Decimal | None = None
    baseline_cr: Decimal | None = None
    feature_snapshot: str | None = None


def build_rules_payload(
    seq: int,
    prev_hash: str,
    rules_id: str,
    document_path: str,
    document_sha256: str,
    document_git_commit: str,
    universe_path: str,
    universe_sha256: str,
    recorded_at: datetime,
    run_id: str,
) -> dict[str, str]:
    for name, digest in (
        ("prev_hash", prev_hash),
        ("document_sha256", document_sha256),
        ("universe_sha256", universe_sha256),
    ):
        if not is_hex64(digest):
            raise CanonicalError(f"{name} must be 64 lower-case hex characters")
    for name, text in (
        ("rules_id", rules_id),
        ("document_path", document_path),
        ("document_git_commit", document_git_commit),
        ("universe_path", universe_path),
        ("run_id", run_id),
    ):
        if type(text) is not str or not text:
            raise CanonicalError(f"{name} must be a non-empty string")
    payload = {
        "scheme": SCHEME,
        "seq": format_int(seq),
        "record_kind": "rules",
        "rules_id": rules_id,
        "document_path": document_path,
        "document_sha256": document_sha256,
        "document_git_commit": document_git_commit,
        "universe_path": universe_path,
        "universe_sha256": universe_sha256,
        "recorded_at": format_ts(recorded_at),
        "run_id": run_id,
        "prev_hash": prev_hash,
    }
    assert tuple(payload) == RULES_FIELDS
    validate(payload)
    return payload


def rules_typed_columns(recorded_at: datetime) -> TypedColumns:
    return TypedColumns(record_kind="rules", created_at=recorded_at)


def _joined(values: Sequence[str], *, ordered: bool = False) -> str:
    """``|``-joined values (sorted unless ``ordered``), or the literal ``none`` when empty."""
    items = list(values) if ordered else sorted(values)
    for item in items:
        if _JOIN in item:
            raise CanonicalError(f"value {item!r} contains the list separator {_JOIN!r}")
    return _JOIN.join(items) if items else _NONE


def _check_provenance(
    lock_kind: str,
    rules_seq: int,
    rules_hash: str,
    universe_sha256: str,
    code_git_sha: str,
    run_id: str,
    prev_hash: str,
) -> None:
    if lock_kind not in LOCK_KINDS:
        raise CanonicalError(f"lock_kind must be one of {', '.join(LOCK_KINDS)}")
    if type(rules_seq) is not int or rules_seq < 0:
        raise CanonicalError("rules_seq must be a non-negative int")
    for name, digest in (
        ("prev_hash", prev_hash),
        ("rules_hash", rules_hash),
        ("universe_sha256", universe_sha256),
    ):
        if not is_hex64(digest):
            raise CanonicalError(f"{name} must be 64 lower-case hex characters")
    if code_git_sha != _NONE and _GIT_SHA_RE.fullmatch(code_git_sha) is None:
        raise CanonicalError("code_git_sha must be 40 lower-case hex characters or 'none'")
    if type(run_id) is not str or not run_id:
        raise CanonicalError("run_id must be a non-empty string")


def build_prediction_payload(
    seq: int,
    prev_hash: str,
    result: BaselineResult,
    company: Company,
    quarter: FiscalQuarter,
    earliest_plausible_reveal: datetime,
    kind: str,
    rules_seq: int,
    rules_hash: str,
    universe_sha256: str,
    code_git_sha: str,
    run_id: str,
) -> dict[str, str]:
    """A baseline-only prediction record (LEDG-01, D-12).

    ``locked_at`` and ``data_cutoff`` are both the lock instant ``result.as_of``: every input
    row had ``available_at < data_cutoff``. The interval fields are the literal ``none`` with
    ``INTERVAL_LABEL`` (a baseline has no out-of-sample residuals yet); ``model_version`` and
    the rules fields are included now so a Phase 4 model lock needs no scheme bump.
    """
    _check_provenance(kind, rules_seq, rules_hash, universe_sha256, code_git_sha, run_id, prev_hash)
    if result.ticker != company.ticker or result.fiscal_quarter != quarter.label:
        raise CanonicalError("result does not belong to this company and quarter")
    point = format_money(result.point)
    payload = {
        "scheme": SCHEME,
        "seq": format_int(seq),
        "record_kind": "prediction",
        "ticker": company.ticker,
        "isin": company.isin,
        "fiscal_quarter": quarter.label,
        "target": TARGET,
        "point_inr_cr": point,
        "lo80_inr_cr": _NONE,
        "hi80_inr_cr": _NONE,
        "interval_label": INTERVAL_LABEL,
        "baseline_inr_cr": point,
        "baseline_method": result.method,
        "pair_status": result.pair_status,
        "growth": result.growth_str,
        "model_version": MODEL_VERSION,
        "labels": _joined(result.labels),
        "breaks_in_window": _joined(result.breaks_in_window),
        "feature_snapshot_sha256": result.snapshot_sha256,
        "data_cutoff": format_ts(result.as_of),
        "locked_at": format_ts(result.as_of),
        "earliest_plausible_reveal": format_ts(earliest_plausible_reveal),
        "lock_kind": kind,
        "rules_seq": format_int(rules_seq),
        "rules_hash": rules_hash,
        "universe_sha256": universe_sha256,
        "code_git_sha": code_git_sha,
        "run_id": run_id,
        "prev_hash": prev_hash,
    }
    assert tuple(payload) == PREDICTION_FIELDS
    validate(payload)
    return payload


def prediction_typed_columns(result: BaselineResult) -> TypedColumns:
    """Typed columns of a prediction: money as the exact Decimal, no interval (D-12)."""
    return TypedColumns(
        record_kind="prediction",
        created_at=result.as_of,
        ticker=result.ticker,
        fiscal_quarter=result.fiscal_quarter,
        model_version=MODEL_VERSION,
        predicted_revenue_cr=result.point,
        low_cr=None,
        high_cr=None,
        baseline_cr=result.point,
        feature_snapshot=result.snapshot_canonical,
    )


def build_gap_payload(
    seq: int,
    prev_hash: str,
    refusal: BaselineRefusal,
    company: Company,
    kind: str,
    rules_seq: int,
    rules_hash: str,
    universe_sha256: str,
    code_git_sha: str,
    run_id: str,
) -> dict[str, str]:
    """A visible gap (D-08): the company could not be locked, and why. Nothing is imputed."""
    _check_provenance(kind, rules_seq, rules_hash, universe_sha256, code_git_sha, run_id, prev_hash)
    if refusal.ticker != company.ticker:
        raise CanonicalError("refusal does not belong to this company")
    payload = {
        "scheme": SCHEME,
        "seq": format_int(seq),
        "record_kind": "gap",
        "ticker": company.ticker,
        "isin": company.isin,
        "fiscal_quarter": refusal.fiscal_quarter,
        "reason_code": refusal.reason_code,
        "missing_quarters": _joined(refusal.missing_quarters, ordered=True),
        "attempted_at": format_ts(refusal.as_of),
        "model_version": MODEL_VERSION,
        "lock_kind": kind,
        "rules_seq": format_int(rules_seq),
        "rules_hash": rules_hash,
        "universe_sha256": universe_sha256,
        "code_git_sha": code_git_sha,
        "run_id": run_id,
        "prev_hash": prev_hash,
    }
    assert tuple(payload) == GAP_FIELDS
    validate(payload)
    return payload


def gap_typed_columns(refusal: BaselineRefusal) -> TypedColumns:
    """Typed columns of a gap: every money column is NULL."""
    return TypedColumns(
        record_kind="gap",
        created_at=refusal.as_of,
        ticker=refusal.ticker,
        fiscal_quarter=refusal.fiscal_quarter,
        model_version=MODEL_VERSION,
    )
