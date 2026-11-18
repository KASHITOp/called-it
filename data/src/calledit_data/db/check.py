"""``nowcast db check``: report the backend and ledger health without leaking the URL.

Never prints a Postgres host, user, password or any other URL component. A failed connect
prints a fixed message plus only the exception class name (RESEARCH Pitfall 1 and 9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import make_url

from calledit_data.db.engine import make_engine
from calledit_data.db.schema import (
    PG_PROTECTED_TABLES,
    PG_REQUIRED_TRIGGERS,
    PREDICTIONS_SQLITE_TRIGGERS,
    STORE_SQLITE_TRIGGERS,
)
from calledit_data.db.settings import Settings

# The ledger triggers (0001) and the point-in-time store triggers (0002).
REQUIRED_SQLITE_TRIGGERS = PREDICTIONS_SQLITE_TRIGGERS + STORE_SQLITE_TRIGGERS
REQUIRED_PG_TRIGGERS = PG_REQUIRED_TRIGGERS


@dataclass
class DbCheckReport:
    lines: list[str] = field(default_factory=list)
    ok: bool = True


def env_file_lines(env_file: Path = Path(".env")) -> list[str]:
    """Report whether .env exists and has a DATABASE_URL key, never reading the value out."""
    present = env_file.is_file()
    has_key = False
    if present:
        with env_file.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.lstrip().startswith("DATABASE_URL="):
                    has_key = True
                    break
    return [
        f".env present: {'yes' if present else 'no'}",
        f"DATABASE_URL key in .env: {'yes' if has_key else 'no'}",
    ]


def run_db_check(settings: Settings, *, connect_only: bool = False) -> DbCheckReport:
    report = DbCheckReport()
    backend = settings.backend
    report.lines.append(f"backend: {backend}")
    if backend == "sqlite":
        database = make_url(settings.database_url.get_secret_value()).database or ":memory:"
        report.lines.append(f"sqlite path: {database}")
    report.lines.append(f"env: {settings.calledit_env}")
    report.lines.extend(env_file_lines())
    report.lines.append(f"schema: {settings.effective_schema or 'n/a'}")

    engine = make_engine(settings)
    try:
        try:
            connection = engine.connect()
        except Exception as exc:  # noqa: BLE001 - fixed message, class name only
            report.lines.append(f"connect: FAILED ({type(exc).__name__})")
            report.ok = False
            report.lines.append("result: FAIL")
            return report
        with connection:
            report.lines.append("connect: ok")
            if not connect_only:
                _check_triggers(connection, backend, settings.effective_schema, report)
    finally:
        engine.dispose()

    report.lines.append(f"result: {'OK' if report.ok else 'FAIL'}")
    return report


def _check_triggers(
    connection: sa.Connection, backend: str, schema: str | None, report: DbCheckReport
) -> None:
    if backend == "postgresql":
        assert schema is not None
        _check_postgres(connection, schema, report)
        return
    rows = connection.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type = 'trigger'")
    ).scalars()
    present = set(rows)
    missing = [name for name in REQUIRED_SQLITE_TRIGGERS if name not in present]
    if missing:
        report.lines.append(
            "triggers: MISSING " + ", ".join(missing) + " (run: uv run alembic upgrade head)"
        )
        report.ok = False
    else:
        report.lines.append("triggers: ok (" + ", ".join(REQUIRED_SQLITE_TRIGGERS) + ")")


def _line(report: DbCheckReport, name: str, passed: bool, detail: str = "") -> None:
    report.lines.append(f"{name}: {'ok' if passed else 'FAIL'}{detail}")
    if not passed:
        report.ok = False


def _check_postgres(connection: sa.Connection, schema: str, report: DbCheckReport) -> None:
    """Postgres self-check (T-01-29, T-01-30).

    Every append-only trigger must exist and be ENABLE ALWAYS (``tgenabled = 'A'``), so that
    ``SET session_replication_role = replica`` cannot skip it. The session role must be
    ``origin``. Row level security must be on for every ledger and store table. The Supabase
    ``anon`` and ``authenticated`` roles must have no USAGE on the schema (D-16).

    Output is one ``name: ok|FAIL`` line per check. The schema name is the only identifier
    printed; a failed query prints the exception class only (never a URL part).
    """
    try:
        trigger_rows = connection.execute(
            sa.text(
                "SELECT t.tgname, t.tgenabled FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND NOT t.tgisinternal"
            ),
            {"schema": schema},
        ).all()
        enabled = {row[0]: str(row[1]) for row in trigger_rows}
        for name in REQUIRED_PG_TRIGGERS:
            if name not in enabled:
                _line(
                    report, f"trigger {name}", False, " (missing; run: uv run alembic upgrade head)"
                )
            elif enabled[name] != "A":
                _line(
                    report,
                    f"trigger {name}",
                    False,
                    " (not ENABLE ALWAYS; it was disabled or altered)",
                )
            else:
                _line(report, f"trigger {name}", True)

        role = connection.execute(sa.text("SELECT current_setting('session_replication_role')"))
        role_value = role.scalar_one()
        _line(
            report,
            "replication_role",
            role_value == "origin",
            "" if role_value == "origin" else f" (is {role_value!r}, must be 'origin')",
        )

        for table in PG_PROTECTED_TABLES:
            row = connection.execute(
                sa.text(
                    "SELECT c.relrowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = :schema AND c.relname = :table AND c.relkind = 'r'"
                ),
                {"schema": schema, "table": table},
            ).first()
            if row is None:
                _line(report, f"rls {table}", False, " (table missing)")
            else:
                _line(report, f"rls {table}", bool(row[0]), "" if row[0] else " (RLS is off)")

        for check_name, role_name in (
            ("anon_usage", "anon"),
            ("authenticated_usage", "authenticated"),
        ):
            exists = connection.execute(
                sa.text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :role)"),
                {"role": role_name},
            ).scalar_one()
            if not exists:
                _line(report, check_name, True, f" (no {role_name} role on this server)")
                continue
            usage = connection.execute(
                sa.text("SELECT has_schema_privilege(:role, :schema, 'USAGE')"),
                {"role": role_name, "schema": schema},
            ).scalar_one()
            _line(
                report,
                check_name,
                not usage,
                "" if not usage else f" ({role_name} has USAGE on the schema)",
            )
    except Exception as exc:  # noqa: BLE001 - fixed message, class name only
        report.lines.append(f"postgresql checks: FAILED ({type(exc).__name__})")
        report.ok = False
