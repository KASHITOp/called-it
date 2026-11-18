"""Alembic environment for CALLED IT.

Migrations in this directory are HAND-WRITTEN. They must never use Alembic batch mode
(batch operations or render-as-batch): on SQLite a batch rebuild copies, drops and renames
the table, which silently drops the append-only triggers on the ledger tables
(CLAUDE.md "DB Layer Design"). ``target_metadata`` is None, so autogenerate is off.

The URL comes only from ``calledit_data.db.settings.get_settings()`` and is never logged.
A failed connect exits with a fixed message plus the exception class name (Pitfall 9).
Tests may pass an open connection via ``config.attributes["connection"]``.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig

from alembic import context
from calledit_data.db.engine import make_engine
from calledit_data.db.settings import get_settings, validate_schema_identifier
from sqlalchemy import text

config = context.config
if config.config_file_name is not None and "connection" not in config.attributes:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _run(connection, schema: str | None) -> None:
    if connection.dialect.name == "postgresql":
        if schema is None:
            sys.exit("alembic: no postgresql schema resolved; refusing to migrate")
        schema = validate_schema_identifier(schema)
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        connection.commit()
    else:
        schema = None
    config.attributes["calledit_schema"] = schema
    context.configure(
        connection=connection,
        target_metadata=None,
        version_table_schema=schema,
        render_as_batch=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        schema = config.attributes.get("schema")
        if schema is None and connection.dialect.name == "postgresql":
            schema = get_settings().effective_schema
        _run(connection, schema)
        return

    try:
        settings = get_settings()
    except Exception as exc:  # noqa: BLE001 - never echo the URL
        sys.exit(
            f"alembic: settings are invalid ({type(exc).__name__}); run: uv run nowcast db check"
        )
    engine = make_engine(settings)
    try:
        try:
            connection = engine.connect()
        except Exception as exc:  # noqa: BLE001 - fixed message, class name only
            sys.exit(f"alembic: could not connect to the database ({type(exc).__name__})")
        with connection:
            _run(connection, settings.effective_schema)
    finally:
        engine.dispose()


if context.is_offline_mode():
    sys.exit("alembic: offline (--sql) mode is not supported; migrations run online only")
run_migrations_online()
