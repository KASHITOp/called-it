"""The head of the exported ledger and the exact bytes that get timestamped (LEDG-10).

The OpenTimestamps proof must be over the head line's ``payload_canonical`` bytes with no
trailing newline, so the proof's file digest equals the head hash that the ledger itself
records. ``write_head_bytes`` writes exactly those bytes and refuses to overwrite a file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from nowcaster.ledger.canonical import sha256_hex
from nowcaster.ledger.export import LEDGER_FILE


class HeadError(RuntimeError):
    """The exported ledger is missing, empty or malformed; nothing was written."""


@dataclass(frozen=True)
class HeadLine:
    seq: int
    hash: str
    line_bytes: bytes


def read_head_line(ledger_dir: Path) -> HeadLine:
    """Return the last line of ``ledger.jsonl``: its seq, sha256 and exact bytes (no newline)."""
    path = Path(ledger_dir) / LEDGER_FILE
    if not path.is_file():
        raise HeadError(f"{LEDGER_FILE} not found in the ledger directory")
    data = path.read_bytes()
    if not data or not data.endswith(b"\n"):
        raise HeadError(f"{LEDGER_FILE} is empty or does not end with a newline")
    lines = data.split(b"\n")[:-1]
    line = lines[-1]
    try:
        payload = json.loads(line)
        seq = int(payload["seq"])
    except (ValueError, KeyError, TypeError):
        raise HeadError(f"the last line of {LEDGER_FILE} is not a ledger payload") from None
    if seq != len(lines) - 1:
        raise HeadError(f"the last line of {LEDGER_FILE} has seq {seq}, expected {len(lines) - 1}")
    return HeadLine(seq=seq, hash=sha256_hex(line.decode("ascii")), line_bytes=line)


def write_head_bytes(ledger_dir: Path, path: Path) -> HeadLine:
    """Write the head line's exact bytes (no newline) to ``path``; refuse if it exists."""
    head = read_head_line(ledger_dir)
    target = Path(path)
    if target.exists():
        raise HeadError("refusing to overwrite an existing file")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(head.line_bytes)
    return head
