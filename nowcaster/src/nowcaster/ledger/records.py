"""Record builders for calledit-ledger-v1.

Record kinds: ``rules`` (seq 0 = PREREGISTRATION.md hash; later rules changes), ``prediction``
and ``gap`` (a refused lock, D-08). ``annotation`` and ``universe_change`` are reserved. New
kinds may be added by a later rules record without changing the canonicalisation.

Every builder emits a fixed, non-empty field set; absent values are the literal ``none``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from nowcaster.ledger.canonical import (
    SCHEME,
    CanonicalError,
    format_int,
    format_ts,
    is_hex64,
    validate,
)

RECORD_KINDS = ("rules", "prediction", "gap")
RESERVED_RECORD_KINDS = ("annotation", "universe_change")

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
