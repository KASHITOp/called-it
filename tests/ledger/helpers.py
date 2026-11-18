"""Builders and raw-insert helpers shared by the ledger tests."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import sqlalchemy as sa
from calledit_data.db.schema import predictions
from nowcaster.ledger.canonical import SCHEME, canonicalize, format_ts, sha256_hex
from nowcaster.ledger.chain import AppendedRecord, Builder, append_record
from nowcaster.ledger.records import TypedColumns, build_rules_payload, rules_typed_columns

T0 = datetime(2026, 11, 28, 6, 0, 0, tzinfo=UTC)


def rules_builder(recorded_at: datetime = T0, note: str = "a") -> Builder:
    digest = hashlib.sha256(note.encode("ascii")).hexdigest()

    def build(seq: int, prev_hash: str) -> tuple[dict, TypedColumns]:
        payload = build_rules_payload(
            seq=seq,
            prev_hash=prev_hash,
            rules_id="prereg-v1",
            document_path="PREREGISTRATION.md",
            document_sha256=digest,
            document_git_commit="none",
            universe_path="config/universe.toml",
            universe_sha256=digest,
            recorded_at=recorded_at,
            run_id="local",
        )
        return payload, rules_typed_columns(recorded_at)

    return build


def append_rules(engine: sa.Engine, count: int) -> list[AppendedRecord]:
    return [
        append_record(engine, rules_builder(T0 + timedelta(minutes=i), note=f"n{i}"))
        for i in range(count)
    ]


def prediction_builder(snapshot: dict, locked_at: datetime = T0) -> Builder:
    snapshot_text = canonicalize(snapshot)

    def build(seq: int, prev_hash: str) -> tuple[dict, TypedColumns]:
        payload = {
            "scheme": SCHEME,
            "seq": str(seq),
            "record_kind": "prediction",
            "ticker": "DMART",
            "fiscal_quarter": "Q3FY27",
            "point_inr_cr": "18123.45",
            "baseline_inr_cr": "18123.45",
            "lo80_inr_cr": "none",
            "hi80_inr_cr": "none",
            "model_version": "baseline-sqly@1.0.0",
            "feature_snapshot_sha256": sha256_hex(snapshot_text),
            "locked_at": format_ts(locked_at),
            "prev_hash": prev_hash,
        }
        typed = TypedColumns(
            record_kind="prediction",
            created_at=locked_at,
            ticker="DMART",
            fiscal_quarter="Q3FY27",
            model_version="baseline-sqly@1.0.0",
            predicted_revenue_cr=Decimal("18123.45"),
            baseline_cr=Decimal("18123.45"),
            feature_snapshot=snapshot_text,
        )
        return payload, typed

    return build


def stale_builder(build: Builder, prev_hash: str) -> Builder:
    """Wrap ``build`` so it always claims ``prev_hash`` (a forked / stale writer)."""

    def wrapped(seq: int, _current: str) -> tuple[dict, TypedColumns]:
        return build(seq, prev_hash)

    return wrapped


def raw_insert(
    conn: sa.Connection, *, seq: int, hash_: str, prev_hash: str, payload: str = "{}"
) -> None:
    conn.execute(
        sa.insert(predictions).values(
            seq=seq,
            record_kind="rules",
            created_at=T0,
            payload_canonical=payload,
            hash=hash_,
            prev_hash=prev_hash,
        )
    )


Mutation = Callable[[sa.Connection], None]
