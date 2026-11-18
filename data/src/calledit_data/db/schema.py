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
