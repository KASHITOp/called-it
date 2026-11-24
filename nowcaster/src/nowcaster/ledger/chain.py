"""Single-writer append to the hash chain.

The app exposes no update or delete function anywhere. Integrity is enforced twice:
here (head check -> ``ForkError``) and in the DB (UNIQUE seq/hash/prev_hash plus the
append-only triggers).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields

import sqlalchemy as sa
from calledit_data.db.schema import predictions

from nowcaster.ledger.canonical import (
    GENESIS_PREV_HASH,
    SCHEME,
    canonicalize,
    format_int,
    format_ts,
    sha256_hex,
)
from nowcaster.ledger.records import TypedColumns

Builder = Callable[[int, str], tuple[dict, TypedColumns]]


class ForkError(RuntimeError):
    """The record does not extend the current head (stale or forged prev_hash)."""


class RecordError(ValueError):
    """The builder returned a payload inconsistent with its seq or typed columns."""


@dataclass(frozen=True)
class HeadRecord:
    seq: int
    hash: str


@dataclass(frozen=True)
class AppendedRecord:
    seq: int
    hash: str
    prev_hash: str
    record_kind: str
    payload_canonical: str


def read_head(conn: sa.Connection) -> HeadRecord | None:
    row = conn.execute(
        sa.select(predictions.c.seq, predictions.c.hash).order_by(predictions.c.seq.desc()).limit(1)
    ).first()
    if row is None:
        return None
    return HeadRecord(seq=row.seq, hash=row.hash)


# Arbitrary constant key for the Postgres transaction-scoped advisory lock ("CALLEDIT").
_PG_LEDGER_LOCK_KEY = 0x43414C4C4544


def _take_writer_lock(conn: sa.Connection) -> None:
    """Serialise writers so the head read and the insert see the same chain.

    SQLite: pysqlite (legacy transaction control) only begins a transaction before DML, so
    the head SELECT would run unlocked; ``BEGIN IMMEDIATE`` takes the write lock first.
    Postgres: a transaction-scoped advisory lock. UNIQUE(seq/hash/prev_hash) still backs
    this up at the DB level on both backends.
    """
    if conn.dialect.name == "sqlite":
        conn.exec_driver_sql("BEGIN IMMEDIATE")
    elif conn.dialect.name == "postgresql":
        conn.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": _PG_LEDGER_LOCK_KEY})


def next_position(head: HeadRecord | None) -> tuple[int, str]:
    """(seq, prev_hash) for the record that would extend ``head``."""
    if head is None:
        return 0, GENESIS_PREV_HASH
    return head.seq + 1, head.hash


def _check_payload(payload: dict, typed: TypedColumns, seq: int, expected_prev: str) -> None:
    if payload.get("prev_hash") != expected_prev:
        raise ForkError(
            f"refusing append at seq {seq}: prev_hash does not equal the current head hash"
        )
    if payload.get("seq") != format_int(seq):
        raise RecordError(f"payload seq does not equal the next seq {seq}")
    if payload.get("scheme") != SCHEME:
        raise RecordError(f"payload scheme must be {SCHEME}")
    if payload.get("record_kind") != typed.record_kind:
        raise RecordError("payload record_kind does not equal the typed column")
    stamp_field = {"rules": "recorded_at", "gap": "attempted_at"}.get(
        typed.record_kind, "locked_at"
    )
    if stamp_field in payload and payload[stamp_field] != format_ts(typed.created_at):
        raise RecordError(f"payload {stamp_field} does not equal the typed created_at")


def append_record(
    engine: sa.Engine,
    build: Builder,
    guard: Callable[[sa.Connection], None] | None = None,
) -> AppendedRecord:
    """Append one record in one transaction: read head, build, verify link, hash, insert.

    ``guard`` runs inside the same transaction, after the writer lock is taken and before
    anything is built; it refuses by raising, so a check-then-write race is impossible.
    """
    with engine.begin() as conn:
        _take_writer_lock(conn)
        if guard is not None:
            guard(conn)
        head = read_head(conn)
        seq, expected_prev = next_position(head)
        payload, typed = build(seq, expected_prev)
        _check_payload(payload, typed, seq, expected_prev)
        payload_canonical = canonicalize(payload)
        digest = sha256_hex(payload_canonical)
        values = {f.name: getattr(typed, f.name) for f in fields(typed)}
        values.update(
            seq=seq,
            payload_canonical=payload_canonical,
            hash=digest,
            prev_hash=expected_prev,
        )
        conn.execute(sa.insert(predictions).values(**values))
    return AppendedRecord(
        seq=seq,
        hash=digest,
        prev_hash=expected_prev,
        record_kind=typed.record_kind,
        payload_canonical=payload_canonical,
    )
