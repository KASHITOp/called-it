"""Shared setup for the lock tests: a migrated temp store, the SYNTHETIC seed fixture, a temp
preregistration and a temp copy of the universe config, all addressed through the
CALLEDIT_PREREG_PATH / CALLEDIT_UNIVERSE_PATH settings (never a hidden time or path option).

Everything here is synthetic test data: no real prediction is ever locked by these tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
import time_machine
from calledit_data.db.schema import predictions
from nowcaster.cli import app
from typer.testing import CliRunner, Result

from tests.conftest import REPO_ROOT

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "seed_fixture_SYNTHETIC.csv"
UNIVERSE_SOURCE = REPO_ROOT / "config" / "universe.toml"

SEED_TIME = datetime(2026, 11, 28, 3, 0, 0, tzinfo=UTC)
RULES_TIME = datetime(2026, 11, 28, 3, 30, 0, tzinfo=UTC)
LOCK_TIME = datetime(2026, 11, 28, 4, 0, 0, tzinfo=UTC)

PREREG_BYTES = b"# Preregistration (test fixture)\n\nbaseline-sqly@1.0.0\n"


@dataclass
class LockEnv:
    engine: sa.Engine
    runner: CliRunner
    prereg: Path
    universe: Path

    def invoke(self, args: list[str], at: datetime) -> Result:
        with time_machine.travel(at, tick=False):
            return self.runner.invoke(app, args)

    def load_seed(self, csv: Path = FIXTURE) -> None:
        result = self.invoke(["seed", "load", "--csv", str(csv)], SEED_TIME)
        assert result.exit_code == 0, result.output

    def rules(self, at: datetime = RULES_TIME) -> Result:
        return self.invoke(["rules"], at)

    def predict(self, quarter: str = "Q3FY27", at: datetime = LOCK_TIME, *extra: str) -> Result:
        return self.invoke(["predict", "--quarter", quarter, *extra], at)

    def rows(self) -> list[dict[str, Any]]:
        """Every ledger row: the typed columns plus the parsed payload under ``payload``."""
        with self.engine.connect() as conn:
            fetched = conn.execute(sa.select(predictions).order_by(predictions.c.seq)).all()
        return [{**row._mapping, "payload": json.loads(row.payload_canonical)} for row in fetched]

    def count(self) -> int:
        with self.engine.connect() as conn:
            return conn.execute(sa.select(sa.func.count()).select_from(predictions)).scalar_one()
