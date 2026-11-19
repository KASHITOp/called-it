"""Throwaway point-in-time stores for the leakage tests.

``fresh_store`` builds an in-memory SQLite store from the table metadata (no triggers: these
stores exist only to be read, and the append-only triggers are tested elsewhere). Everything
goes in through the production writer, so a row is validated exactly as it would be live.

All values written here are SYNTHETIC test data.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from calledit_data.db.schema import metadata
from calledit_data.seed.loader import SeedCompanyRules, parse_seed_csv
from calledit_data.store.writer import (
    ObservationIn,
    RevealEventIn,
    ensure_series,
    insert_observations,
    insert_reveal_events,
)
from nowcaster.universe import Universe
from sqlalchemy.pool import StaticPool

SENTINEL = Decimal("999999999.99")


def fresh_store() -> sa.Engine:
    """An empty in-memory SQLite store (one shared connection, so it survives re-connects)."""
    engine = sa.create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    metadata.create_all(engine)
    return engine


def add_observations(
    engine: sa.Engine, rows: Sequence[ObservationIn], ingested_at: datetime
) -> None:
    """Insert ``rows`` (all stamped ``ingested_at``), creating their series first."""
    with engine.begin() as conn:
        for key in sorted({row.series_key for row in rows}):
            ticker = key.rsplit(".", 1)[-1]
            ensure_series(
                conn,
                key,
                source="seed_csv",
                metric="revenue_from_operations_consolidated",
                entity=ticker,
                unit="inr_crore",
                frequency="quarterly",
                collection_mode="manual_seed",
            )
        insert_observations(conn, rows, ingested_at)


def add_events(engine: sa.Engine, rows: Iterable[RevealEventIn], ingested_at: datetime) -> None:
    with engine.begin() as conn:
        insert_reveal_events(conn, list(rows), ingested_at)


def load_fixture(
    engine: sa.Engine, csv_path: Path, universe: Universe, now: datetime, ingested_at: datetime
) -> None:
    """Load the SYNTHETIC seed CSV into ``engine`` through the production parser and writer."""
    rules = {
        c.ticker: SeedCompanyRules(isin=c.isin, has_business_update=c.has_business_update)
        for c in universe.companies
    }
    parsed = parse_seed_csv(csv_path, rules, require_verified=False, now=now)
    assert not parsed.errors, parsed.errors
    add_observations(engine, [row.observation for row in parsed.rows], ingested_at)
    add_events(engine, [event for row in parsed.rows for event in row.events], ingested_at)


def count_rows(engine: sa.Engine, series_key: str) -> int:
    """Raw row count of a series, ignoring any reader (used to prove a sentinel is stored)."""
    with engine.connect() as conn:
        return int(
            conn.execute(
                sa.text(
                    "SELECT COUNT(*) FROM observations o JOIN series s "
                    "ON o.series_id = s.series_id WHERE s.series_key = :k"
                ),
                {"k": series_key},
            ).scalar_one()
        )
