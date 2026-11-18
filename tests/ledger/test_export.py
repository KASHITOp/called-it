"""LEDG-09: ledger.jsonl export is verified, append-only (byte-prefix) and atomic."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from calledit_data.db.engine import make_engine
from calledit_data.db.settings import Settings
from nowcaster.ledger.chain import append_record
from nowcaster.ledger.export import ExportError, export_ledger

from tests.conftest import sqlite_url
from tests.ledger.helpers import append_rules, prediction_builder, rules_builder


def _lines(path: Path) -> list[bytes]:
    data = path.read_bytes()
    assert data.endswith(b"\n")
    return data.split(b"\n")[:-1]


def test_second_export_appends_exactly_one_line(migrated_sqlite: sa.Engine, tmp_path: Path) -> None:
    out = tmp_path / "ledger"
    append_rules(migrated_sqlite, 1)
    first = export_ledger(migrated_sqlite, out)
    old = (out / "ledger.jsonl").read_bytes()
    assert (first.records, first.appended_lines) == (1, 1)

    append_record(migrated_sqlite, rules_builder(note="second"))
    second = export_ledger(migrated_sqlite, out)
    new = (out / "ledger.jsonl").read_bytes()
    assert (second.records, second.appended_lines, second.head_seq) == (2, 1, 1)
    assert new.startswith(old) and len(_lines(out / "ledger.jsonl")) == 2
    assert hashlib.sha256(_lines(out / "ledger.jsonl")[1]).hexdigest() == second.head_hash


def test_re_export_without_new_records_is_a_no_op(
    migrated_sqlite: sa.Engine, tmp_path: Path
) -> None:
    out = tmp_path / "ledger"
    append_rules(migrated_sqlite, 2)
    export_ledger(migrated_sqlite, out)
    before = (out / "ledger.jsonl").read_bytes()
    report = export_ledger(migrated_sqlite, out)
    assert report.appended_lines == 0
    assert (out / "ledger.jsonl").read_bytes() == before


def test_format_is_lf_ascii_one_record_per_line(migrated_sqlite: sa.Engine, tmp_path: Path) -> None:
    out = tmp_path / "ledger"
    records = append_rules(migrated_sqlite, 3)
    export_ledger(migrated_sqlite, out)
    data = (out / "ledger.jsonl").read_bytes()
    data.decode("ascii")
    assert b"\r" not in data
    lines = _lines(out / "ledger.jsonl")
    assert [line.decode("ascii") for line in lines] == [r.payload_canonical for r in records]
    for line in lines:
        assert line == line.rstrip()
    assert not list(out.glob("*.tmp"))


@pytest.mark.parametrize(
    "tamper",
    [
        lambda b: b.replace(b'"seq":"0"', b'"seq":"9"'),
        lambda b: b[:-1],
        lambda b: b + b"extra\n",
        lambda b: b.replace(b"\n", b"\r\n"),
    ],
    ids=["edited-byte", "truncated", "foreign-line", "crlf"],
)
def test_non_prefix_ledger_file_aborts_without_writing(
    migrated_sqlite: sa.Engine, tmp_path: Path, tamper
) -> None:
    out = tmp_path / "ledger"
    append_rules(migrated_sqlite, 2)
    export_ledger(migrated_sqlite, out)
    path = out / "ledger.jsonl"
    tampered = tamper(path.read_bytes())
    path.write_bytes(tampered)
    with pytest.raises(ExportError, match="byte-prefix"):
        export_ledger(migrated_sqlite, out)
    assert path.read_bytes() == tampered


def test_empty_ledger_fails_and_creates_nothing(migrated_sqlite: sa.Engine, tmp_path: Path) -> None:
    out = tmp_path / "ledger"
    with pytest.raises(ExportError, match="empty"):
        export_ledger(migrated_sqlite, out)
    assert not (out / "ledger.jsonl").exists()


def test_snapshot_bytes_are_written_exactly(migrated_sqlite: sa.Engine, tmp_path: Path) -> None:
    out = tmp_path / "ledger"
    append_rules(migrated_sqlite, 1)
    append_record(migrated_sqlite, prediction_builder({"b": ["2"], "a": "1"}))
    report = export_ledger(migrated_sqlite, out)
    assert report.snapshots_written == 1
    assert (out / "snapshots" / "1.json").read_bytes() == b'{"a":"1","b":["2"]}'
    assert not (out / "snapshots" / "0.json").exists()


# --- broken chains: bypass the triggers on a throwaway copy -------------------------------


@pytest.fixture
def throwaway_copy(migrated_sqlite: sa.Engine, tmp_path: Path) -> Iterator[tuple[Path, sa.Engine]]:
    append_rules(migrated_sqlite, 3)
    source_path = Path(migrated_sqlite.url.database)
    copy_path = tmp_path / "throwaway.db"
    with sqlite3.connect(source_path) as src, sqlite3.connect(copy_path) as dst:
        src.backup(dst)
    # Strip the append-only triggers by editing sqlite_master directly (the way a tamperer
    # would), then reopen so the schema change takes effect.
    raw = sqlite3.connect(copy_path)
    raw.execute("PRAGMA writable_schema=ON")
    raw.execute("DELETE FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'predictions'")
    raw.commit()
    raw.execute("PRAGMA writable_schema=OFF")
    raw.close()
    settings = Settings(_env_file=None, database_url=sqlite_url(copy_path), calledit_env="test")
    engine = make_engine(settings)
    with engine.connect() as conn:
        left = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'trigger'"
        ).scalar_one()
    assert left == 0
    try:
        yield copy_path, engine
    finally:
        engine.dispose()


TAMPERS = {
    "payload-edited": "UPDATE predictions SET payload_canonical = "
    'replace(payload_canonical, \'"run_id":"local"\', \'"run_id":"forged"\') WHERE seq = 1',
    "gap": "DELETE FROM predictions WHERE seq = 1",
    "relinked": "UPDATE predictions SET prev_hash = '" + "9" * 64 + "' WHERE seq = 1",
}


@pytest.mark.parametrize("statement", list(TAMPERS.values()), ids=list(TAMPERS))
def test_export_refuses_a_broken_chain(
    throwaway_copy: tuple[Path, sa.Engine], tmp_path: Path, statement: str
) -> None:
    _copy_path, engine = throwaway_copy
    with engine.begin() as conn:
        assert conn.exec_driver_sql(statement).rowcount == 1
    out = tmp_path / "copy-ledger"
    with pytest.raises(ExportError, match="seq") as info:
        export_ledger(engine, out)
    message = str(info.value)
    assert "run_id" not in message and "document_sha256" not in message
    assert not (out / "ledger.jsonl").exists()
