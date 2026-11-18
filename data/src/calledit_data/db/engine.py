"""Engine factory. The URL is never logged or printed."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from calledit_data.db.settings import Settings

SQLITE_PRAGMAS = (
    "PRAGMA foreign_keys=ON",
    # recursive_triggers=ON makes INSERT OR REPLACE fire the DELETE trigger, so a REPLACE
    # can never silently overwrite a ledger row (CLAUDE.md "DB Layer Design").
    "PRAGMA recursive_triggers=ON",
    "PRAGMA journal_mode=WAL",
)


def _sqlite_engine(settings: Settings) -> Engine:
    url = make_url(settings.database_url.get_secret_value())
    database = url.database or ""
    if database and database != ":memory:" and not database.startswith("file:"):
        Path(database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            for pragma in SQLITE_PRAGMAS:
                cursor.execute(pragma)
        finally:
            cursor.close()

    return engine


def make_engine(settings: Settings) -> Engine:
    """Return an engine for the configured backend.

    SQLite: pragmas on every connection. Postgres: app tables are defined with
    ``schema=None`` and translated to the validated effective schema.
    """
    if settings.backend == "sqlite":
        return _sqlite_engine(settings)
    url = make_url(settings.database_url.get_secret_value())
    engine = create_engine(
        url,
        poolclass=NullPool,
        connect_args={"prepare_threshold": None},
        hide_parameters=True,
    )
    return engine.execution_options(schema_translate_map={None: settings.effective_schema})
