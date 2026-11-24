"""Guarded ``DROP SCHEMA`` for rehearsal and test schemas only (D-21).

The live ``calledit`` schema, ``public`` and anything else can never be dropped through here:
the name is checked against a closed pattern before any connection is used.
"""

from __future__ import annotations

import re

import sqlalchemy as sa

SCRATCH_RE = re.compile(r"calledit_(rehearsal|test_[0-9a-f]{8,32})")


class ScratchGuardError(ValueError):
    """The schema name is not a rehearsal or test scratch schema."""


def check_scratch_name(name: str) -> str:
    if not isinstance(name, str) or SCRATCH_RE.fullmatch(name) is None:
        raise ScratchGuardError("only calledit_rehearsal and calledit_test_<hex> can be dropped")
    return name


def drop_scratch_schema(engine: sa.Engine, name: str) -> None:
    """``DROP SCHEMA <name> CASCADE`` for a guarded scratch schema (Postgres)."""
    check_scratch_name(name)  # before any connection is made
    if engine.dialect.name != "postgresql":
        raise ScratchGuardError("drop-scratch needs a postgresql engine")
    with engine.begin() as conn:
        conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
