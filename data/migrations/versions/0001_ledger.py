"""Ledger table ``predictions`` with append-only triggers (LEDG-01, LEDG-04).

Revision ID: 0001
Revises:
Create Date: 2026-11-18

Hand-written. Column types are frozen here (not imported from the app) so this revision
never changes meaning when the app's types evolve.

SQLite: three triggers, each raising ``calledit: predictions is append-only (<op>)``:
``predictions_no_update`` (BEFORE UPDATE), ``predictions_no_delete`` (BEFORE DELETE) and
``predictions_no_replace`` (BEFORE INSERT when a row with the same seq, hash or prev_hash
exists). The replace guard blocks INSERT OR REPLACE even on a connection with
``recursive_triggers=OFF``.

Postgres: ``<schema>.forbid_mutation()`` plus a row trigger (UPDATE OR DELETE) and a
statement trigger (TRUNCATE), both ``ENABLE ALWAYS`` so they survive
``session_replication_role=replica``. RLS is enabled with no policies, and anon /
authenticated lose all access when those Supabase roles exist (D-16).

The schema identifier is re-validated by regex before any f-string DDL (T-01-09).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from calledit_data.db.settings import validate_schema_identifier

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "predictions"


def _schema() -> str | None:
    if op.get_bind().dialect.name != "postgresql":
        return None
    schema = context.config.attributes.get("calledit_schema")
    if schema is None:
        raise RuntimeError("0001_ledger: no postgresql schema resolved")
    return validate_schema_identifier(schema)


def _columns(is_pg: bool) -> list[sa.Column]:
    money = sa.Numeric(20, 2) if is_pg else sa.String(40)
    instant = sa.DateTime(timezone=True) if is_pg else sa.String(27)
    return [
        sa.Column("seq", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("record_kind", sa.Text, nullable=False),
        sa.Column("ticker", sa.Text, nullable=True),
        sa.Column("fiscal_quarter", sa.Text, nullable=True),
        sa.Column("model_version", sa.Text, nullable=True),
        sa.Column("predicted_revenue_cr", money, nullable=True),
        sa.Column("low_cr", money, nullable=True),
        sa.Column("high_cr", money, nullable=True),
        sa.Column("baseline_cr", money, nullable=True),
        sa.Column("feature_snapshot", sa.Text, nullable=True),
        sa.Column("created_at", instant, nullable=False),
        sa.Column("payload_canonical", sa.Text, nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("hash", name="uq_predictions_hash"),
        sa.UniqueConstraint("prev_hash", name="uq_predictions_prev_hash"),
    ]


def _sqlite_triggers() -> None:
    op.execute(
        "CREATE TRIGGER predictions_no_update BEFORE UPDATE ON predictions "
        "BEGIN SELECT RAISE(ABORT, 'calledit: predictions is append-only (update)'); END"
    )
    op.execute(
        "CREATE TRIGGER predictions_no_delete BEFORE DELETE ON predictions "
        "BEGIN SELECT RAISE(ABORT, 'calledit: predictions is append-only (delete)'); END"
    )
    op.execute(
        "CREATE TRIGGER predictions_no_replace BEFORE INSERT ON predictions "
        "WHEN EXISTS (SELECT 1 FROM predictions WHERE seq = NEW.seq "
        "OR hash = NEW.hash OR prev_hash = NEW.prev_hash) "
        "BEGIN SELECT RAISE(ABORT, 'calledit: predictions is append-only (replace)'); END"
    )


def _postgres_triggers(s: str) -> None:
    op.execute(
        f"CREATE OR REPLACE FUNCTION {s}.forbid_mutation() RETURNS trigger "
        "LANGUAGE plpgsql SET search_path = '' AS $fn$ "
        "BEGIN RAISE EXCEPTION 'calledit: % is append-only (op=%)', TG_TABLE_NAME, TG_OP; END "
        "$fn$"
    )
    op.execute(
        f"CREATE TRIGGER predictions_no_update_delete BEFORE UPDATE OR DELETE ON {s}.{TABLE} "
        f"FOR EACH ROW EXECUTE FUNCTION {s}.forbid_mutation()"
    )
    op.execute(
        f"CREATE TRIGGER predictions_no_truncate BEFORE TRUNCATE ON {s}.{TABLE} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION {s}.forbid_mutation()"
    )
    op.execute(f"ALTER TABLE {s}.{TABLE} ENABLE ALWAYS TRIGGER predictions_no_update_delete")
    op.execute(f"ALTER TABLE {s}.{TABLE} ENABLE ALWAYS TRIGGER predictions_no_truncate")
    op.execute(f"ALTER TABLE {s}.{TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(
        "DO $do$ BEGIN "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN "
        f"REVOKE ALL ON TABLE {s}.{TABLE} FROM anon; "
        f"REVOKE USAGE ON SCHEMA {s} FROM anon; "
        "END IF; "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN "
        f"REVOKE ALL ON TABLE {s}.{TABLE} FROM authenticated; "
        f"REVOKE USAGE ON SCHEMA {s} FROM authenticated; "
        "END IF; "
        "END $do$"
    )


def upgrade() -> None:
    is_pg = op.get_bind().dialect.name == "postgresql"
    schema = _schema()
    op.create_table(TABLE, *_columns(is_pg), schema=schema)
    if is_pg:
        assert schema is not None
        _postgres_triggers(schema)
    else:
        _sqlite_triggers()


def downgrade() -> None:
    raise RuntimeError("0001_ledger cannot be downgraded: the ledger is append-only")
