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
from calledit_data.db.schema import PREDICTIONS_SQLITE_TRIGGERS
from calledit_data.db.settings import Settings


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
                _check_triggers(connection, backend, report)
    finally:
        engine.dispose()

    report.lines.append(f"result: {'OK' if report.ok else 'FAIL'}")
    return report


def _check_triggers(connection: sa.Connection, backend: str, report: DbCheckReport) -> None:
    if backend != "sqlite":
        # The Postgres trigger, RLS and replication-role checks arrive in Plan 01-08.
        report.lines.append("triggers: postgresql checks not implemented yet (use --connect-only)")
        report.ok = False
        return
    rows = connection.execute(
        sa.text(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'predictions'"
        )
    ).scalars()
    present = set(rows)
    missing = [name for name in PREDICTIONS_SQLITE_TRIGGERS if name not in present]
    if missing:
        report.lines.append(
            "triggers: MISSING " + ", ".join(missing) + " (run: uv run alembic upgrade head)"
        )
        report.ok = False
    else:
        report.lines.append("triggers: ok (" + ", ".join(PREDICTIONS_SQLITE_TRIGGERS) + ")")
