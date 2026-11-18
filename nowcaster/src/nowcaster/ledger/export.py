"""Export the chain to ``ledger.jsonl`` (the public git/OTS witness).

Format: one record's ``payload_canonical`` per line, in seq order, LF-terminated, ASCII,
no CR, no trailing whitespace. ``snapshots/<seq>.json`` holds each record's exact
feature-snapshot bytes (no trailing newline).

Nothing is written unless every check passes: the chain is contiguous from seq 0, every
hash equals sha256(payload_canonical), every prev_hash links, and any existing
``ledger.jsonl`` is a byte-prefix of the new bytes (history is only ever extended).
Refusal messages name the seq and hash only, never payload contents.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import sqlalchemy as sa
from calledit_data.db.schema import predictions

from nowcaster.ledger.canonical import (
    GENESIS_PREV_HASH,
    CanonicalError,
    canonicalize,
    sha256_hex,
)

LEDGER_FILE = "ledger.jsonl"
SNAPSHOT_DIR = "snapshots"


class ExportError(RuntimeError):
    """The chain or the existing ledger file failed verification; nothing was written."""


@dataclass(frozen=True)
class ExportReport:
    path: Path
    records: int
    appended_lines: int
    head_seq: int
    head_hash: str
    snapshots_written: int


def _verify_rows(rows: list) -> None:
    expected_prev = GENESIS_PREV_HASH
    for index, row in enumerate(rows):
        if row.seq != index:
            raise ExportError(
                f"chain broken at seq {row.seq}: expected seq {index} (gap or reordering)"
            )
        if sha256_hex(row.payload_canonical) != row.hash:
            raise ExportError(
                f"chain broken at seq {row.seq}: stored hash {row.hash} "
                "does not equal sha256(payload_canonical)"
            )
        if row.prev_hash != expected_prev:
            raise ExportError(
                f"chain broken at seq {row.seq}: prev_hash does not equal the hash of seq {index - 1}"
            )
        try:
            payload = json.loads(row.payload_canonical)
            recanonical = canonicalize(payload)
        except (ValueError, CanonicalError):
            raise ExportError(
                f"chain broken at seq {row.seq}: payload_canonical is not calledit-ledger-v1"
            ) from None
        if recanonical != row.payload_canonical:
            raise ExportError(f"chain broken at seq {row.seq}: payload_canonical is not canonical")
        if payload.get("seq") != str(row.seq) or payload.get("prev_hash") != row.prev_hash:
            raise ExportError(
                f"chain broken at seq {row.seq}: payload seq/prev_hash disagree with the columns"
            )
        if row.feature_snapshot is not None:
            declared = payload.get("feature_snapshot_sha256")
            if declared is not None and declared != sha256_hex(row.feature_snapshot):
                raise ExportError(
                    f"chain broken at seq {row.seq}: feature_snapshot does not match its hash"
                )
        expected_prev = row.hash


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def export_ledger(engine: sa.Engine, out_dir: Path) -> ExportReport:
    with engine.connect() as conn:
        rows = conn.execute(
            sa.select(
                predictions.c.seq,
                predictions.c.hash,
                predictions.c.prev_hash,
                predictions.c.payload_canonical,
                predictions.c.feature_snapshot,
            ).order_by(predictions.c.seq)
        ).all()
    if not rows:
        raise ExportError("ledger is empty: nothing to export")
    _verify_rows(rows)

    new_bytes = b"".join(row.payload_canonical.encode("ascii") + b"\n" for row in rows)
    out_dir = Path(out_dir)
    ledger_path = out_dir / LEDGER_FILE
    old_lines = 0
    old_bytes: bytes | None = None
    if ledger_path.exists():
        old_bytes = ledger_path.read_bytes()
        if not new_bytes.startswith(old_bytes):
            raise ExportError(
                f"{LEDGER_FILE} on disk is not a byte-prefix of the verified chain; "
                "refusing to rewrite history"
            )
        old_lines = old_bytes.count(b"\n")

    snapshot_writes: list[tuple[Path, bytes]] = []
    for row in rows:
        if row.feature_snapshot is None:
            continue
        snap_path = out_dir / SNAPSHOT_DIR / f"{row.seq}.json"
        snap_bytes = row.feature_snapshot.encode("ascii")
        if snap_path.exists():
            if snap_path.read_bytes() != snap_bytes:
                raise ExportError(
                    f"{SNAPSHOT_DIR}/{row.seq}.json on disk differs from the stored snapshot"
                )
            continue
        snapshot_writes.append((snap_path, snap_bytes))

    out_dir.mkdir(parents=True, exist_ok=True)
    for snap_path, snap_bytes in snapshot_writes:
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(snap_path, snap_bytes)
    if new_bytes != old_bytes:
        _atomic_write(ledger_path, new_bytes)

    head = rows[-1]
    return ExportReport(
        path=ledger_path,
        records=len(rows),
        appended_lines=len(rows) - old_lines,
        head_seq=head.seq,
        head_hash=head.hash,
        snapshots_written=len(snapshot_writes),
    )
