"""Shared fixtures. Every test runs in its own temp cwd with a scrubbed environment, so a
developer's ``.env`` (which may hold the live Supabase URL) is never read by tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from calledit_data.db.engine import make_engine
from calledit_data.db.settings import get_settings

REPO_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_SCRUBBED_ENV = (
    "DATABASE_URL",
    "CALLEDIT_ENV",
    "CALLEDIT_DB_SCHEMA",
    "CALLEDIT_LEDGER_DIR",
    "CALLEDIT_PREREG_PATH",
    "CALLEDIT_UNIVERSE_PATH",
    "GITHUB_ACTIONS",
    "GITHUB_REF",
    "GITHUB_RUN_ID",
)


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _SCRUBBED_ENV:
        monkeypatch.delenv(name, raising=False)
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)


def alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@pytest.fixture
def migrated_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sa.Engine]:
    """A temp SQLite file migrated to head; DATABASE_URL and CALLEDIT_ENV=test point at it."""
    monkeypatch.setenv("DATABASE_URL", sqlite_url(tmp_path / "ledger-test.db"))
    monkeypatch.setenv("CALLEDIT_ENV", "test")
    command.upgrade(alembic_config(), "head")
    engine = make_engine(get_settings())
    try:
        yield engine
    finally:
        engine.dispose()
