"""Point-in-time store: ``series``, ``observations``, ``reveal_events`` (PIT-01, PIT-02).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-18

Hand-written, never batch mode (a SQLite batch rebuild silently drops triggers). Column types
are frozen here, not imported from the app.

No column has a server default. ``available_at`` and ``ingested_at`` are always set by the
writer (``calledit_data.store.writer``), so a missing timestamp is a NOT NULL failure, never a
silently invented ``CURRENT_TIMESTAMP``.

SQLite triggers, each raising ``calledit: <table> is append-only (<op>)``:

- ``observations_no_update``, ``observations_no_delete``, ``observations_no_replace``
- ``reveal_events_no_update``, ``reveal_events_no_delete``, ``reveal_events_no_replace``
- ``series_no_update``, ``series_no_delete``, ``series_no_replace``

The replace guards are ``BEFORE INSERT ... WHEN EXISTS`` a row colliding on any UNIQUE key, so
``INSERT OR REPLACE`` is refused even on a connection with ``recursive_triggers=OFF``. A brand
new row never collides, so new series and new vintages can still be added.

Postgres: the ``forbid_mutation()`` function from 0001 is reused. Each table gets
``<t>_no_update_delete`` (row) and ``<t>_no_truncate`` (statement), both ``ENABLE ALWAYS``,
then RLS with no policies and the guarded anon/authenticated ``REVOKE`` (D-16).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from calledit_data.db.settings import validate_schema_identifier

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("series", "observations", "reveal_events")


def _schema() -> str | None:
    if op.get_bind().dialect.name != "postgresql":
        return None
    schema = context.config.attributes.get("calledit_schema")
    if schema is None:
        raise RuntimeError("0002_pit_store: no postgresql schema resolved")
    return validate_schema_identifier(schema)


def _create_tables(is_pg: bool, schema: str | None) -> None:
    value = sa.Numeric(20, 6) if is_pg else sa.String(40)
    instant = sa.DateTime(timezone=True) if is_pg else sa.String(27)
    series_fk = f"{schema}.series.series_id" if schema else "series.series_id"

    op.create_table(
        "series",
        sa.Column("series_id", sa.Integer, primary_key=True),
        sa.Column("series_key", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("metric", sa.Text, nullable=False),
        sa.Column("entity", sa.Text, nullable=False),
        sa.Column("unit", sa.Text, nullable=False),
        sa.Column("frequency", sa.Text, nullable=False),
        sa.Column("collection_mode", sa.Text, nullable=False),
        sa.UniqueConstraint("series_key", name="uq_series_series_key"),
        schema=schema,
    )
    op.create_table(
        "observations",
        sa.Column("obs_id", sa.Integer, primary_key=True),
        sa.Column(
            "series_id",
            sa.Integer,
            sa.ForeignKey(series_fk, name="fk_observations_series"),
            nullable=False,
        ),
        sa.Column("period_date", sa.Date, nullable=False),
        sa.Column("value", value, nullable=False),
        sa.Column("available_at", instant, nullable=False),
        sa.Column("availability_basis", sa.Text, nullable=False),
        sa.Column("ingested_at", instant, nullable=False),
        sa.Column("vintage", sa.Text, nullable=False),
        sa.Column("source_ref", sa.Text, nullable=False),
        sa.Column("source_kind", sa.Text, nullable=False),
        sa.Column("content_hash", sa.Text, nullable=False),
        sa.UniqueConstraint(
            "series_id",
            "period_date",
            "available_at",
            "content_hash",
            name="uq_observations_vintage",
        ),
        schema=schema,
    )
    op.create_index(
        "ix_observations_series_available",
        "observations",
        ["series_id", "available_at", "period_date"],
        schema=schema,
    )
    op.create_table(
        "reveal_events",
        sa.Column("event_id", sa.Integer, primary_key=True),
        sa.Column("ticker", sa.Text, nullable=False),
        sa.Column("fiscal_quarter", sa.Text, nullable=False),
        sa.Column("event_kind", sa.Text, nullable=False),
        sa.Column("event_at", instant, nullable=False),
        sa.Column("availability_basis", sa.Text, nullable=False),
        sa.Column("source_ref", sa.Text, nullable=False),
        sa.Column("ingested_at", instant, nullable=False),
        sa.Column("content_hash", sa.Text, nullable=False),
        sa.UniqueConstraint("content_hash", name="uq_reveal_events_content_hash"),
        schema=schema,
    )


# Every UNIQUE key of each table: a colliding INSERT is a REPLACE attempt.
_COLLISION = {
    "series": "series_id = NEW.series_id OR series_key = NEW.series_key",
    "observations": (
        "obs_id = NEW.obs_id OR (series_id = NEW.series_id AND period_date = NEW.period_date "
        "AND available_at = NEW.available_at AND content_hash = NEW.content_hash)"
    ),
    "reveal_events": "event_id = NEW.event_id OR content_hash = NEW.content_hash",
}


# Frozen trigger names, spelled out so they can be grepped and so this revision never
# changes meaning if TABLES is reordered: (table, update, delete, replace).
_SQLITE_TRIGGERS = (
    ("series", "series_no_update", "series_no_delete", "series_no_replace"),
    (
        "observations",
        "observations_no_update",
        "observations_no_delete",
        "observations_no_replace",
    ),
    (
        "reveal_events",
        "reveal_events_no_update",
        "reveal_events_no_delete",
        "reveal_events_no_replace",
    ),
)


def _sqlite_triggers() -> None:
    for table, no_update, no_delete, no_replace in _SQLITE_TRIGGERS:
        op.execute(
            f"CREATE TRIGGER {no_update} BEFORE UPDATE ON {table} "
            f"BEGIN SELECT RAISE(ABORT, 'calledit: {table} is append-only (update)'); END"
        )
        op.execute(
            f"CREATE TRIGGER {no_delete} BEFORE DELETE ON {table} "
            f"BEGIN SELECT RAISE(ABORT, 'calledit: {table} is append-only (delete)'); END"
        )
        op.execute(
            f"CREATE TRIGGER {no_replace} BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} WHERE {_COLLISION[table]}) "
            f"BEGIN SELECT RAISE(ABORT, 'calledit: {table} is append-only (replace)'); END"
        )


def _postgres_triggers(s: str) -> None:
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON {s}.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION {s}.forbid_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {s}.{table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION {s}.forbid_mutation()"
        )
        op.execute(f"ALTER TABLE {s}.{table} ENABLE ALWAYS TRIGGER {table}_no_update_delete")
        op.execute(f"ALTER TABLE {s}.{table} ENABLE ALWAYS TRIGGER {table}_no_truncate")
        op.execute(f"ALTER TABLE {s}.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $do$ BEGIN "
            "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN "
            f"REVOKE ALL ON TABLE {s}.{table} FROM anon; "
            "END IF; "
            "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN "
            f"REVOKE ALL ON TABLE {s}.{table} FROM authenticated; "
            "END IF; "
            "END $do$"
        )


def upgrade() -> None:
    is_pg = op.get_bind().dialect.name == "postgresql"
    schema = _schema()
    _create_tables(is_pg, schema)
    if is_pg:
        assert schema is not None
        _postgres_triggers(schema)
    else:
        _sqlite_triggers()


def downgrade() -> None:
    raise RuntimeError("0002_pit_store cannot be downgraded: the store is append-only")
