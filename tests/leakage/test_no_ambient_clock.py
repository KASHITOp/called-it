"""PIT-03 / LEAK-01, enforced statically: the clock and the read path have one door each.

1. No module under ``data/src`` or ``nowcaster/src`` may read the wall clock, except
   ``nowcaster/src/nowcaster/clock.py``. Time is always passed in explicitly, so every "as of"
   in the system is a visible argument.
2. ``baseline.py`` and ``splits.py`` read data only through ``PointInTimeReader``: they import
   neither ``sqlalchemy`` nor ``calledit_data.db`` (nor the store writer), and nothing under
   ``data/src`` may import ``nowcaster`` (the data layer never depends on the model layer).

Both scanners walk the ``ast`` and match on node structure, so docstrings, comments and string
literals that merely mention ``datetime.now`` never trip them. Each scanner has a self-check
that proves it detects a planted violation.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

DATA_SRC = REPO_ROOT / "data" / "src"
NOWCASTER_SRC = REPO_ROOT / "nowcaster" / "src"
CLOCK_MODULE = NOWCASTER_SRC / "nowcaster" / "clock.py"

# Resolved dotted names that read the wall clock.
AMBIENT_CLOCK = frozenset(
    {
        "datetime.datetime.now",
        "datetime.datetime.utcnow",
        "datetime.datetime.today",
        "datetime.date.today",
        "time.time",
        "time.time_ns",
    }
)

# Modules baseline.py and splits.py must not import (the PointInTimeReader is the only door).
READ_PATH_BYPASS = ("sqlalchemy", "calledit_data.db", "calledit_data.store", "sqlite3", "psycopg")


def source_files(*roots: Path) -> list[Path]:
    return sorted(p for root in roots for p in root.rglob("*.py"))


# --- scanner 1: ambient clock -------------------------------------------------------------


def _alias_table(tree: ast.AST) -> dict[str, str]:
    """Map each locally bound name to the dotted name it stands for (datetime/time only)."""
    table: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {"datetime", "time"}:
                    table[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module in {"datetime", "time"}:
            for alias in node.names:
                table[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return table


def _dotted(node: ast.expr, table: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return table.get(node.id)
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value, table)
        return None if base is None else f"{base}.{node.attr}"
    return None


def ambient_clock_uses(source: str) -> list[tuple[int, str]]:
    """Every reference (call or bare reference) to a wall-clock reader, as (line, name)."""
    tree = ast.parse(source)
    table = _alias_table(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute | ast.Name):
            name = _dotted(node, table)
            if name in AMBIENT_CLOCK:
                found.append((node.lineno, name))
    return sorted(set(found))


# --- scanner 2: imports -------------------------------------------------------------------


def imported_modules(source: str) -> list[tuple[int, str]]:
    """Every module a file imports, as (line, dotted name); ``from a import b`` yields a.b too."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.lineno, node.module))
            found += [(node.lineno, f"{node.module}.{alias.name}") for alias in node.names]
    return found


def imports_matching(source: str, prefixes: tuple[str, ...]) -> list[tuple[int, str]]:
    return [
        (line, name)
        for line, name in imported_modules(source)
        if any(name == p or name.startswith(p + ".") for p in prefixes)
    ]


# --- the real checks ----------------------------------------------------------------------


def test_source_trees_are_found() -> None:
    """Guards the scans below against passing vacuously on an empty tree."""
    files = source_files(DATA_SRC, NOWCASTER_SRC)
    assert len(files) >= 20
    assert CLOCK_MODULE in files
    assert (NOWCASTER_SRC / "nowcaster" / "baseline.py") in files
    assert (NOWCASTER_SRC / "nowcaster" / "splits.py") in files


def test_no_module_reads_the_wall_clock_except_clock_py() -> None:
    offenders = {
        f"{path.relative_to(REPO_ROOT).as_posix()}:{line} {name}"
        for path in source_files(DATA_SRC, NOWCASTER_SRC)
        if path != CLOCK_MODULE
        for line, name in ambient_clock_uses(path.read_text(encoding="utf-8"))
    }
    assert not offenders, f"ambient clock reads outside clock.py: {sorted(offenders)}"


def test_clock_py_is_the_one_place_that_reads_the_clock() -> None:
    """The exemption is real, not vestigial: if clock.py stops reading it, update this test."""
    assert ambient_clock_uses(CLOCK_MODULE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("module", ["baseline.py", "splits.py"])
def test_model_facing_modules_do_not_bypass_the_reader(module: str) -> None:
    source = (NOWCASTER_SRC / "nowcaster" / module).read_text(encoding="utf-8")
    assert imports_matching(source, READ_PATH_BYPASS) == []


def test_calledit_data_never_imports_nowcaster() -> None:
    offenders = {
        f"{path.relative_to(REPO_ROOT).as_posix()}:{line} {name}"
        for path in source_files(DATA_SRC)
        for line, name in imports_matching(path.read_text(encoding="utf-8"), ("nowcaster",))
    }
    assert not offenders, f"calledit_data must not depend on nowcaster: {sorted(offenders)}"


# --- scanner self-checks: each one must detect a planted violation ------------------------


@pytest.mark.parametrize(
    "source, expected",
    [
        ("from datetime import datetime\nx = datetime.now()\n", "datetime.datetime.now"),
        ("import datetime\nx = datetime.datetime.utcnow()\n", "datetime.datetime.utcnow"),
        ("import datetime as dt\nx = dt.date.today()\n", "datetime.date.today"),
        ("from datetime import date as D\nx = D.today()\n", "datetime.date.today"),
        ("import time\nx = time.time()\n", "time.time"),
        ("import time as t\nx = t.time_ns()\n", "time.time_ns"),
        ("from time import time\nx = time()\n", "time.time"),
        (
            "from datetime import datetime\nf = dict(default=datetime.utcnow)\n",
            "datetime.datetime.utcnow",
        ),
    ],
    ids=[
        "from-import",
        "module",
        "module-alias",
        "class-alias",
        "time",
        "time-alias",
        "bare",
        "reference",
    ],
)
def test_clock_scanner_detects_planted_violations(source: str, expected: str) -> None:
    assert expected in {name for _, name in ambient_clock_uses(source)}


def test_clock_scanner_ignores_docstrings_comments_strings_and_other_names() -> None:
    source = '''
"""Never call datetime.now() or time.time() here."""
from datetime import UTC, datetime

# datetime.now() is forbidden; use the injected instant instead.
NOTE = "datetime.utcnow() and date.today() are banned"


class Clock:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=UTC)


def f(clock: Clock, other) -> object:
    return clock.now(), other.time(), datetime.fromisoformat("2026-01-01T00:00:00+00:00")
'''
    assert ambient_clock_uses(source) == []


@pytest.mark.parametrize(
    "source, prefix",
    [
        ("import sqlalchemy\n", "sqlalchemy"),
        ("import sqlalchemy as sa\n", "sqlalchemy"),
        ("from sqlalchemy.engine import Engine\n", "sqlalchemy"),
        ("from calledit_data.db.schema import observations\n", "calledit_data.db"),
        ("from calledit_data import db\n", "calledit_data.db"),
        ("import calledit_data.db.engine\n", "calledit_data.db"),
        ("from calledit_data.store.writer import insert_observations\n", "calledit_data.store"),
        ("import nowcaster.baseline\n", "nowcaster"),
        ("from nowcaster import splits\n", "nowcaster"),
    ],
    ids=[
        "sqlalchemy",
        "sqlalchemy-alias",
        "sqlalchemy-from",
        "db-from",
        "db-name",
        "db-dotted",
        "store",
        "nowcaster-dotted",
        "nowcaster-from",
    ],
)
def test_import_scanner_detects_planted_violations(source: str, prefix: str) -> None:
    assert imports_matching(source, (prefix,)), source


def test_import_scanner_ignores_allowed_imports_and_text() -> None:
    source = '''
"""Mentions sqlalchemy and calledit_data.db and nowcaster in prose only."""
from calledit_data.pit.reader import PointInTimeReader
from calledit_data.calendar.fiscal import FiscalQuarter
import calledit_data_extras
NOTE = "import sqlalchemy"
'''
    assert imports_matching(source, (*READ_PATH_BYPASS, "nowcaster")) == []
