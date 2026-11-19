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
from calledit_data.pit.reader import PointInTimeReader
from hypothesis import settings as hypothesis_settings

from tests.leakage.leaky_readers import LEAKY_READERS

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
    "GITHUB_SHA",
)


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _SCRUBBED_ENV:
        monkeypatch.delenv(name, raising=False)
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)


# Hypothesis profiles. `ci` is derandomised so the meta-test's subprocess runs are reproducible;
# `dev` keeps hypothesis random so local runs keep exploring. `--hypothesis-profile` overrides.
hypothesis_settings.register_profile("dev", deadline=None, max_examples=60)
hypothesis_settings.register_profile("ci", derandomize=True, deadline=None, max_examples=60)
hypothesis_settings.load_profile("dev")

READER_CHOICES = ("correct", *LEAKY_READERS)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--reader",
        action="store",
        default="correct",
        choices=READER_CHOICES,
        help=(
            "Which PointInTimeReader the leakage suite exercises. 'correct' is the production "
            "reader; the leaky-* variants are deliberately wrong and must turn the suite red "
            "(tests/meta proves it)."
        ),
    )


@pytest.fixture(scope="session")
def reader_cls(request: pytest.FixtureRequest) -> type[PointInTimeReader]:
    """The reader class under test: production by default, a leaky subclass via --reader."""
    name = request.config.getoption("--reader")
    if name == "correct":
        return PointInTimeReader
    return LEAKY_READERS[name]


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
