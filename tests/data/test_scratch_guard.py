"""Only scratch schemas can be dropped, and the refusal happens before any connection."""

from __future__ import annotations

import pytest
from calledit_data.db.scratch import ScratchGuardError, check_scratch_name, drop_scratch_schema
from nowcaster.cli import app
from typer.testing import CliRunner


class _NeverUsedEngine:
    """Any attribute access fails the test: the guard must refuse first."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"engine.{name} was touched before the guard refused")


@pytest.mark.parametrize(
    "name",
    ["calledit", "public", "calledit_rehearsal2", "calledit_dev", "calledit_ci", "x; DROP", ""],
)
def test_other_schemas_are_refused_without_connecting(name: str) -> None:
    with pytest.raises(ScratchGuardError):
        drop_scratch_schema(_NeverUsedEngine(), name)  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["calledit_rehearsal", "calledit_test_0123abcd"])
def test_scratch_names_are_accepted_by_the_name_check(name: str) -> None:
    assert check_scratch_name(name) == name


def test_cli_refuses_live_and_non_scratch(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("CALLEDIT_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    result = runner.invoke(app, ["db", "drop-scratch", "--schema", "calledit"])
    assert result.exit_code != 0 and "refused" in result.output + str(result.exception)
