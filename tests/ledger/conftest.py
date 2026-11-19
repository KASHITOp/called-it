"""Fixtures for the lock tests (see ``lock_helpers``)."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from typer.testing import CliRunner

from tests.ledger.lock_helpers import PREREG_BYTES, UNIVERSE_SOURCE, LockEnv


@pytest.fixture
def lock_env(
    migrated_sqlite: sa.Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> LockEnv:
    """A migrated temp SQLite store with temp preregistration and universe files configured.

    The SYNTHETIC seed is not loaded yet: call ``lock_env.load_seed()`` where a test needs it.
    """
    prereg = tmp_path / "PREREGISTRATION.md"
    prereg.write_bytes(PREREG_BYTES)
    universe = tmp_path / "universe.toml"
    universe.write_bytes(UNIVERSE_SOURCE.read_bytes())
    monkeypatch.setenv("CALLEDIT_PREREG_PATH", str(prereg))
    monkeypatch.setenv("CALLEDIT_UNIVERSE_PATH", str(universe))
    return LockEnv(engine=migrated_sqlite, runner=CliRunner(), prereg=prereg, universe=universe)
