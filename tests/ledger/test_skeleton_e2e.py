"""Walking Skeleton: fresh DB -> rules record -> ledger.jsonl whose hash matches the DB."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from calledit_data.db.settings import Settings
from nowcaster.cli import app
from pydantic import ValidationError
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def rules_inputs(tmp_path: Path) -> tuple[Path, Path]:
    doc = tmp_path / "PREREGISTRATION.md"
    doc.write_bytes(b"# Preregistration (test)\n\nbaseline-v1\n")
    universe = tmp_path / "universe.toml"
    universe.write_bytes(b"[companies.DMART]\nenabled = true\n")
    return doc, universe


def test_rules_record_exports_to_matching_ledger_line(
    migrated_sqlite: sa.Engine, rules_inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    doc, universe = rules_inputs
    result = runner.invoke(app, ["rules", "--document", str(doc), "--universe", str(universe)])
    assert result.exit_code == 0, result.output

    out = tmp_path / "ledger"
    result = runner.invoke(app, ["ledger", "export", "--out", str(out)])
    assert result.exit_code == 0, result.output

    data = (out / "ledger.jsonl").read_bytes()
    assert data.endswith(b"\n") and b"\r" not in data
    lines = data.split(b"\n")[:-1]
    assert len(lines) == 1
    line = lines[0]

    with migrated_sqlite.connect() as conn:
        stored_hash, stored_canonical = conn.execute(
            sa.text("SELECT hash, payload_canonical FROM predictions WHERE seq = 0")
        ).one()
    assert hashlib.sha256(line).hexdigest() == stored_hash
    assert line.decode("ascii") == stored_canonical

    payload = json.loads(line)
    assert payload["record_kind"] == "rules"
    assert payload["seq"] == "0"
    assert payload["prev_hash"] == "0" * 64
    assert payload["scheme"] == "calledit-ledger-v1"
    assert payload["document_sha256"] == hashlib.sha256(doc.read_bytes()).hexdigest()
    assert payload["universe_sha256"] == hashlib.sha256(universe.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE predictions SET ticker = 'X'",
        "DELETE FROM predictions",
        "INSERT OR REPLACE INTO predictions SELECT * FROM predictions",
    ],
    ids=["update", "delete", "insert-or-replace"],
)
def test_raw_mutations_are_refused(
    migrated_sqlite: sa.Engine, rules_inputs: tuple[Path, Path], statement: str
) -> None:
    doc, universe = rules_inputs
    assert (
        runner.invoke(app, ["rules", "--document", str(doc), "--universe", str(universe)]).exit_code
        == 0
    )
    with pytest.raises(sa.exc.DBAPIError, match="append-only"), migrated_sqlite.begin() as conn:
        conn.exec_driver_sql(statement)


def test_db_check_reports_ok(migrated_sqlite: sa.Engine) -> None:
    result = runner.invoke(app, ["db", "check"])
    assert result.exit_code == 0, result.output
    assert "backend: sqlite" in result.output
    assert "result: OK" in result.output
    assert "postgresql" not in result.output


def test_dry_run_appends_nothing(
    migrated_sqlite: sa.Engine, rules_inputs: tuple[Path, Path]
) -> None:
    doc, universe = rules_inputs
    result = runner.invoke(
        app, ["rules", "--document", str(doc), "--universe", str(universe), "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert '"record_kind":"rules"' in result.output
    with migrated_sqlite.connect() as conn:
        assert conn.execute(sa.text("SELECT COUNT(*) FROM predictions")).scalar_one() == 0


def test_live_with_sqlite_is_refused() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="sqlite:///x.db", calledit_env="live")


@pytest.mark.parametrize(
    "secret",
    [
        "postgresql://user:hunter2-secret@[HOST/postgres",
        "postgresql://postgres.ref:[hunter2#x/y]@pooler.example.com:5432/postgres",
        "postgresql://postgres.ref:" + "hunter2" + "@x@pooler.example.com:5432/postgres",
    ],
    ids=["bracket-host", "bracketed-password", "unencoded-at"],
)
def test_bad_url_refusal_never_echoes_the_url(secret: str) -> None:
    with pytest.raises(ValidationError) as info:
        Settings(_env_file=None, database_url=secret, calledit_env="dev")
    assert "hunter2" not in str(info.value)
    assert "percent-encoding" in str(info.value)


def test_good_postgres_url_is_normalised_to_psycopg() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgres://u:p%40ss@pooler.example.com:5432/postgres",
        calledit_env="dev",
    )
    assert settings.backend == "postgresql"
    assert settings.database_url.get_secret_value().startswith("postgresql+psycopg://")
    assert settings.effective_schema == "calledit_dev"


PG_URL = "postgresql://u:p@pooler.example.com:5432/postgres"


@pytest.mark.parametrize(
    ("env", "schema"),
    [
        ("dev", "Calledit_dev"),
        ("dev", "calledit-dev"),
        ("dev", "1calledit"),
        ("dev", "calledit_dev\n"),
        ("dev", "a" * 64),
        ("dev", "calledit"),
        ("test", "calledit"),
        ("rehearsal", "calledit"),
        ("dev", "public"),
        ("test", "calledit_test_xyz"),
        ("live", "calledit_dev"),
        ("rehearsal", "calledit_dev"),
    ],
)
def test_schema_rules_refuse(env: str, schema: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=PG_URL, calledit_env=env, db_schema=schema)


@pytest.mark.parametrize(
    ("env", "schema", "expected"),
    [
        ("live", None, "calledit"),
        ("live", "calledit", "calledit"),
        ("rehearsal", None, "calledit_rehearsal"),
        ("dev", None, "calledit_dev"),
        ("dev", "calledit_ci", "calledit_ci"),
        ("test", "calledit_test_0123abcd", "calledit_test_0123abcd"),
    ],
)
def test_schema_rules_accept(env: str, schema: str | None, expected: str) -> None:
    settings = Settings(_env_file=None, database_url=PG_URL, calledit_env=env, db_schema=schema)
    assert settings.effective_schema == expected


def test_live_ledger_dir_cannot_be_overridden() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=PG_URL, calledit_env="live", ledger_dir="elsewhere")
    assert Settings(
        _env_file=None, database_url=PG_URL, calledit_env="live"
    ).effective_ledger_dir == Path("ledger")
