"""LEDG-04 on SQLite: the six-form bypass matrix, run with recursive_triggers explicitly OFF
so the BEFORE INSERT replace guard (not the pragma) is what blocks REPLACE."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from calledit_data.db.schema import PREDICTIONS_SQLITE_TRIGGERS

from tests.ledger.helpers import append_rules

COLUMNS = "seq, record_kind, created_at, payload_canonical, hash, prev_hash"
ROW0_FORGED = f"0, 'rules', '2026-11-28T06:00:00.000000Z', '{{}}', '{'a' * 64}', '{'b' * 64}'"

MUTATIONS = {
    "update": "UPDATE predictions SET record_kind = 'forged'",
    "delete-no-where": "DELETE FROM predictions",
    "insert-or-replace": f"INSERT OR REPLACE INTO predictions ({COLUMNS}) VALUES ({ROW0_FORGED})",
    "replace": f"REPLACE INTO predictions ({COLUMNS}) VALUES ({ROW0_FORGED})",
    "update-or-replace": "UPDATE OR REPLACE predictions SET seq = 0 WHERE seq = 1",
    "insert-on-conflict-do-update": (
        f"INSERT INTO predictions ({COLUMNS}) VALUES ({ROW0_FORGED}) "
        "ON CONFLICT(seq) DO UPDATE SET record_kind = 'forged'"
    ),
}


@pytest.fixture
def pragma_off_conn(migrated_sqlite: sa.Engine) -> Iterator[sa.Connection]:
    append_rules(migrated_sqlite, 2)
    with migrated_sqlite.connect() as conn:
        conn.exec_driver_sql("PRAGMA recursive_triggers=OFF")
        assert conn.exec_driver_sql("PRAGMA recursive_triggers").scalar_one() == 0
        try:
            yield conn
        finally:
            conn.rollback()
            conn.exec_driver_sql("PRAGMA recursive_triggers=ON")


def _snapshot(conn: sa.Connection) -> list[tuple]:
    return list(
        conn.exec_driver_sql(
            "SELECT seq, record_kind, payload_canonical, hash, prev_hash FROM predictions "
            "ORDER BY seq"
        )
    )


@pytest.mark.parametrize("statement", list(MUTATIONS.values()), ids=list(MUTATIONS))
def test_mutation_is_blocked(pragma_off_conn: sa.Connection, statement: str) -> None:
    before = _snapshot(pragma_off_conn)
    assert len(before) == 2
    with pytest.raises(sa.exc.DBAPIError, match="append-only"):
        pragma_off_conn.exec_driver_sql(statement)
    pragma_off_conn.rollback()
    assert _snapshot(pragma_off_conn) == before


def test_new_connections_get_the_pragmas(migrated_sqlite: sa.Engine) -> None:
    with migrated_sqlite.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA recursive_triggers").scalar_one() == 1
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() == "wal"


def test_delete_on_empty_table_deletes_nothing_and_keeps_triggers(
    migrated_sqlite: sa.Engine,
) -> None:
    with migrated_sqlite.begin() as conn:
        result = conn.exec_driver_sql("DELETE FROM predictions")
        assert result.rowcount == 0
    with migrated_sqlite.connect() as conn:
        names = set(
            conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'predictions'"
            ).scalars()
        )
    assert set(PREDICTIONS_SQLITE_TRIGGERS) <= names
