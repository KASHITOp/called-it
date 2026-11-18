"""Table definitions (SQLAlchemy Core). Tables use ``schema=None``; on Postgres the engine's
``schema_translate_map`` routes them to the validated effective schema.

The DDL itself lives in hand-written Alembic migrations (``data/migrations``); this module is
the query-side description and must stay in step with them.
"""

from __future__ import annotations

import sqlalchemy as sa

from calledit_data.db.types import DecimalText, UTCDateTime

metadata = sa.MetaData()

# The single hash-chained ledger table (LEDG-01). Every record kind (rules, prediction, gap)
# lives here. There is deliberately no CHECK on record_kind: a new kind must never need a
# table rebuild, because a SQLite rebuild silently drops the append-only triggers.
predictions = sa.Table(
    "predictions",
    metadata,
    sa.Column("seq", sa.Integer, primary_key=True, autoincrement=False),
    sa.Column("record_kind", sa.Text, nullable=False),
    sa.Column("ticker", sa.Text, nullable=True),
    sa.Column("fiscal_quarter", sa.Text, nullable=True),
    sa.Column("model_version", sa.Text, nullable=True),
    sa.Column("predicted_revenue_cr", DecimalText(2), nullable=True),
    sa.Column("low_cr", DecimalText(2), nullable=True),
    sa.Column("high_cr", DecimalText(2), nullable=True),
    sa.Column("baseline_cr", DecimalText(2), nullable=True),
    sa.Column("feature_snapshot", sa.Text, nullable=True),
    sa.Column("created_at", UTCDateTime(), nullable=False),
    sa.Column("payload_canonical", sa.Text, nullable=False),
    sa.Column("hash", sa.String(64), nullable=False, unique=True),
    sa.Column("prev_hash", sa.String(64), nullable=False, unique=True),
    schema=None,
)

PREDICTIONS_SQLITE_TRIGGERS = (
    "predictions_no_update",
    "predictions_no_delete",
    "predictions_no_replace",
)

# --- Point-in-time store (PIT-01, PIT-02). Insert-only at the DB (0002 triggers) and in code
# (calledit_data.store.writer has no update or delete path). No column has a server default:
# available_at and ingested_at are always set explicitly by the writer.

series = sa.Table(
    "series",
    metadata,
    sa.Column("series_id", sa.Integer, primary_key=True),
    sa.Column("series_key", sa.Text, nullable=False, unique=True),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("metric", sa.Text, nullable=False),
    sa.Column("entity", sa.Text, nullable=False),
    sa.Column("unit", sa.Text, nullable=False),
    sa.Column("frequency", sa.Text, nullable=False),
    sa.Column("collection_mode", sa.Text, nullable=False),
    schema=None,
)

observations = sa.Table(
    "observations",
    metadata,
    sa.Column("obs_id", sa.Integer, primary_key=True),
    sa.Column("series_id", sa.Integer, sa.ForeignKey("series.series_id"), nullable=False),
    sa.Column("period_date", sa.Date, nullable=False),
    sa.Column("value", DecimalText(6), nullable=False),
    sa.Column("available_at", UTCDateTime(), nullable=False),
    sa.Column("availability_basis", sa.Text, nullable=False),
    sa.Column("ingested_at", UTCDateTime(), nullable=False),
    sa.Column("vintage", sa.Text, nullable=False),
    sa.Column("source_ref", sa.Text, nullable=False),
    sa.Column("source_kind", sa.Text, nullable=False),
    sa.Column("content_hash", sa.Text, nullable=False),
    sa.UniqueConstraint(
        "series_id", "period_date", "available_at", "content_hash", name="uq_observations_vintage"
    ),
    sa.Index("ix_observations_series_available", "series_id", "available_at", "period_date"),
    schema=None,
)

reveal_events = sa.Table(
    "reveal_events",
    metadata,
    sa.Column("event_id", sa.Integer, primary_key=True),
    sa.Column("ticker", sa.Text, nullable=False),
    sa.Column("fiscal_quarter", sa.Text, nullable=False),
    sa.Column("event_kind", sa.Text, nullable=False),
    sa.Column("event_at", UTCDateTime(), nullable=False),
    sa.Column("availability_basis", sa.Text, nullable=False),
    sa.Column("source_ref", sa.Text, nullable=False),
    sa.Column("ingested_at", UTCDateTime(), nullable=False),
    sa.Column("content_hash", sa.Text, nullable=False, unique=True),
    schema=None,
)

STORE_TABLES = ("series", "observations", "reveal_events")

STORE_SQLITE_TRIGGERS = (
    "series_no_update",
    "series_no_delete",
    "series_no_replace",
    "observations_no_update",
    "observations_no_delete",
    "observations_no_replace",
    "reveal_events_no_update",
    "reveal_events_no_delete",
    "reveal_events_no_replace",
)

# Postgres: every ledger/store table carries a row trigger (UPDATE OR DELETE) and a statement
# trigger (TRUNCATE), both ENABLE ALWAYS (0001, 0002). ``nowcast db check`` asserts them.
PG_PROTECTED_TABLES = ("predictions", *STORE_TABLES)
PG_REQUIRED_TRIGGERS = tuple(
    f"{table}_{suffix}"
    for table in PG_PROTECTED_TABLES
    for suffix in ("no_update_delete", "no_truncate")
)
