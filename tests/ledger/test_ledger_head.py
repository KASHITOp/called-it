"""The head helper writes exactly the bytes OpenTimestamps must stamp (LEDG-10, T-01-45)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from nowcaster.cli import app
from nowcaster.ledger.canonical import canonicalize, sha256_hex
from nowcaster.ledger.head import HeadError, read_head_line, write_head_bytes
from typer.testing import CliRunner

runner = CliRunner()


def _line(seq: int, prev: str) -> str:
    return canonicalize({"scheme": "calledit-ledger-v1", "seq": str(seq), "prev_hash": prev})


@pytest.fixture
def ledger_dir(tmp_path: Path) -> Path:
    lines = [_line(0, "0" * 64)]
    lines.append(_line(1, sha256_hex(lines[0])))
    (tmp_path / "ledger.jsonl").write_bytes(("\n".join(lines) + "\n").encode("ascii"))
    return tmp_path


def test_read_head_line_returns_last_line_without_newline(ledger_dir: Path) -> None:
    head = read_head_line(ledger_dir)
    assert head.seq == 1
    assert not head.line_bytes.endswith(b"\n")
    assert head.hash == hashlib.sha256(head.line_bytes).hexdigest()


def test_written_file_digest_equals_printed_hash_and_has_no_newline(
    ledger_dir: Path, tmp_path: Path
) -> None:
    out = tmp_path / "stamp" / "1"
    result = runner.invoke(
        app, ["ledger", "head", "--ledger-dir", str(ledger_dir), "--write-bytes", str(out)]
    )
    assert result.exit_code == 0, result.output
    written = out.read_bytes()
    assert not written.endswith(b"\n")
    assert result.output.strip() == f"seq=1 hash={hashlib.sha256(written).hexdigest()}"


def test_write_head_bytes_refuses_to_overwrite(ledger_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "already"
    out.write_bytes(b"x")
    with pytest.raises(HeadError, match="overwrite"):
        write_head_bytes(ledger_dir, out)
    assert out.read_bytes() == b"x"


def test_missing_empty_and_truncated_ledgers_are_refused(tmp_path: Path) -> None:
    with pytest.raises(HeadError):
        read_head_line(tmp_path)
    (tmp_path / "ledger.jsonl").write_bytes(b"")
    with pytest.raises(HeadError):
        read_head_line(tmp_path)
    (tmp_path / "ledger.jsonl").write_bytes(_line(0, "0" * 64).encode("ascii"))  # no newline
    with pytest.raises(HeadError):
        read_head_line(tmp_path)


def test_a_head_whose_seq_does_not_match_its_position_is_refused(tmp_path: Path) -> None:
    (tmp_path / "ledger.jsonl").write_bytes((_line(5, "0" * 64) + "\n").encode("ascii"))
    with pytest.raises(HeadError, match="expected 0"):
        read_head_line(tmp_path)
