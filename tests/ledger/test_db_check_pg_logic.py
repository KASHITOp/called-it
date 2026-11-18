"""The Postgres branch of ``nowcast db check``, driven by a scripted fake connection.

Real Postgres is exercised by tests/postgres (the Supabase scratch schema locally, postgres:17
in CI). These tests pin the decision logic itself so it runs everywhere: every way a weakened
database can look must produce a FAIL line and a failed report, and the output must stay free of
URL parts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from calledit_data.db.check import DbCheckReport, _check_postgres
from calledit_data.db.schema import PG_PROTECTED_TABLES, PG_REQUIRED_TRIGGERS

SCHEMA = "calledit_test_0123456789ab"


class _Result:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one(self):
        assert len(self._rows) == 1
        return self._rows[0][0] if isinstance(self._rows[0], tuple) else self._rows[0]


@dataclass
class FakeConnection:
    triggers: dict[str, str] = field(default_factory=dict)
    role: str = "origin"
    rls: dict[str, bool] = field(default_factory=dict)
    roles_present: set[str] = field(default_factory=lambda: {"anon", "authenticated"})
    usage: set[str] = field(default_factory=set)
    explode: bool = False

    def execute(self, clause, params=None) -> _Result:
        if self.explode:
            raise ConnectionError("boom host=db.example.invalid")
        sql = str(clause)
        params = params or {}
        if "FROM pg_trigger" in sql:
            assert params["schema"] == SCHEMA
            return _Result(list(self.triggers.items()))
        if "session_replication_role" in sql:
            return _Result([(self.role,)])
        if "relrowsecurity" in sql:
            table = params["table"]
            return _Result([(self.rls[table],)] if table in self.rls else [])
        if "FROM pg_roles" in sql:
            return _Result([(params["role"] in self.roles_present,)])
        if "has_schema_privilege" in sql:
            return _Result([(params["role"] in self.usage,)])
        raise AssertionError(f"unexpected SQL: {sql}")


def healthy() -> FakeConnection:
    return FakeConnection(
        triggers=dict.fromkeys(PG_REQUIRED_TRIGGERS, "A"),
        rls=dict.fromkeys(PG_PROTECTED_TABLES, True),
    )


def run(conn: FakeConnection) -> DbCheckReport:
    report = DbCheckReport()
    _check_postgres(conn, SCHEMA, report)  # type: ignore[arg-type]
    return report


def test_required_triggers_cover_every_table_and_both_kinds() -> None:
    assert PG_PROTECTED_TABLES == ("predictions", "series", "observations", "reveal_events")
    assert len(PG_REQUIRED_TRIGGERS) == 8
    assert "predictions_no_update_delete" in PG_REQUIRED_TRIGGERS
    assert "reveal_events_no_truncate" in PG_REQUIRED_TRIGGERS


def test_healthy_database_is_ok() -> None:
    report = run(healthy())
    assert report.ok
    assert "replication_role: ok" in report.lines
    assert "anon_usage: ok" in report.lines
    assert len(report.lines) == 8 + 1 + 4 + 2
    assert all(line.endswith(": ok") for line in report.lines)


def test_extra_unrelated_triggers_are_ignored() -> None:
    conn = healthy()
    conn.triggers["something_else"] = "O"
    assert run(conn).ok


def test_missing_trigger_fails_and_names_it() -> None:
    conn = healthy()
    del conn.triggers["observations_no_truncate"]
    report = run(conn)
    assert not report.ok
    assert any(line.startswith("trigger observations_no_truncate: FAIL") for line in report.lines)


@pytest.mark.parametrize("state", ["O", "D", "R"])
def test_trigger_not_enable_always_fails(state: str) -> None:
    conn = healthy()
    conn.triggers["predictions_no_update_delete"] = state
    report = run(conn)
    assert not report.ok
    failing = [line for line in report.lines if "FAIL" in line]
    assert len(failing) == 1
    assert failing[0].startswith("trigger predictions_no_update_delete: FAIL")


def test_replica_role_fails() -> None:
    conn = healthy()
    conn.role = "replica"
    report = run(conn)
    assert not report.ok
    assert any(line.startswith("replication_role: FAIL") for line in report.lines)


def test_rls_off_fails_for_that_table_only() -> None:
    conn = healthy()
    conn.rls["series"] = False
    report = run(conn)
    assert not report.ok
    assert [line for line in report.lines if "FAIL" in line] == ["rls series: FAIL (RLS is off)"]


def test_missing_table_fails() -> None:
    conn = healthy()
    del conn.rls["reveal_events"]
    report = run(conn)
    assert not report.ok
    assert "rls reveal_events: FAIL (table missing)" in report.lines


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_exposed_schema_fails(role: str) -> None:
    conn = healthy()
    conn.usage.add(role)
    report = run(conn)
    assert not report.ok
    assert any(line.startswith(f"{role}_usage: FAIL") for line in report.lines)


def test_vanilla_postgres_without_supabase_roles_is_ok() -> None:
    conn = healthy()
    conn.roles_present = set()
    report = run(conn)
    assert report.ok
    assert "anon_usage: ok (no anon role on this server)" in report.lines


def test_query_error_prints_the_class_name_only() -> None:
    report = run(FakeConnection(explode=True))
    assert not report.ok
    assert report.lines == ["postgresql checks: FAILED (ConnectionError)"]
    assert "example.invalid" not in "\n".join(report.lines)
