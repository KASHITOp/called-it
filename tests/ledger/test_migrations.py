"""Migrations: triggers exist after upgrade, survive a second upgrade, and no migration file
uses Alembic batch mode (which would silently drop them on SQLite)."""

from __future__ import annotations

import re

import pytest
import sqlalchemy as sa
from alembic import command
from calledit_data.db.schema import PREDICTIONS_SQLITE_TRIGGERS

from tests.conftest import REPO_ROOT, alembic_config

MIGRATIONS_DIR = REPO_ROOT / "data" / "migrations"

# Built by concatenation so this file never matches its own scan.
FORBIDDEN = [
    re.compile("batch" + "_alter_table"),
    re.compile(r"\bbatch" + r"_op\b"),
    re.compile("render_as" + r"_batch\s*=\s*True"),
]


def _triggers(engine: sa.Engine) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'predictions'"
            ).scalars()
        )


def _version(engine: sa.Engine) -> str:
    with engine.connect() as conn:
        return conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()


def test_triggers_exist_after_upgrade(migrated_sqlite: sa.Engine) -> None:
    assert set(PREDICTIONS_SQLITE_TRIGGERS) <= _triggers(migrated_sqlite)
    assert _version(migrated_sqlite) == "0001"


def test_second_upgrade_is_a_no_op(migrated_sqlite: sa.Engine) -> None:
    command.upgrade(alembic_config(), "head")
    assert set(PREDICTIONS_SQLITE_TRIGGERS) <= _triggers(migrated_sqlite)
    assert _version(migrated_sqlite) == "0001"


def test_downgrade_is_refused_and_keeps_the_ledger(migrated_sqlite: sa.Engine) -> None:
    with pytest.raises(RuntimeError, match="append-only"):
        command.downgrade(alembic_config(), "base")
    assert set(PREDICTIONS_SQLITE_TRIGGERS) <= _triggers(migrated_sqlite)
    assert _version(migrated_sqlite) == "0001"


def test_no_migration_uses_batch_mode() -> None:
    files = [p for p in MIGRATIONS_DIR.rglob("*") if p.suffix in {".py", ".mako"}]
    assert any(p.name == "0001_ledger.py" for p in files)
    offenders = [
        f"{p.relative_to(REPO_ROOT).as_posix()}: {pattern.pattern}"
        for p in files
        for pattern in FORBIDDEN
        if pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_scan_patterns_would_catch_batch_mode() -> None:
    sample = "with op." + "batch_alter_table('predictions') as " + "batch_op:\n"
    sample += "context.configure(render_as_" + "batch=True)\n"
    assert all(pattern.search(sample) for pattern in FORBIDDEN)
