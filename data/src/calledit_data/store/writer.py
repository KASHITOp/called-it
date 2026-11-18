"""Insert-only writer for the point-in-time store (PIT-01, PIT-02).

There is no update or delete path here, and the DB triggers from migration 0002 refuse both
anyway. Re-running a load is idempotent: every row carries a ``content_hash`` over its
identifying fields, and only rows whose hash is absent are inserted. A restated value (a
different value, ``available_at``, source or vintage) has a different hash and becomes a new
row; the original is never touched.

Only plain ``insert()`` is used: no ``ON CONFLICT``, ``OR IGNORE`` or ``REPLACE`` (CLAUDE.md).
``ingested_at`` is always a parameter: this package never reads the wall clock.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import sqlalchemy as sa

from calledit_data.calendar.reveal import AVAILABILITY_BASES, event_early_bound
from calledit_data.db.schema import observations, reveal_events, series

VINTAGES = ("first_reported", "restated")
SOURCE_KINDS = ("seed_csv", "seed_csv_unverified")
EVENT_KINDS = ("business_update", "results")

_TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
_VALUE_QUANTUM = Decimal("0.000001")


class StoreError(ValueError):
    """A row cannot be written to the point-in-time store."""


@dataclass(frozen=True)
class ObservationIn:
    """One observation to write. ``ingested_at`` is supplied per insert call."""

    series_key: str
    period_date: date
    value: Decimal
    available_at: datetime
    availability_basis: str
    source_ref: str
    vintage: str
    source_kind: str


@dataclass(frozen=True)
class RevealEventIn:
    """One reveal event (a business update or a results filing) to write."""

    ticker: str
    fiscal_quarter: str
    event_kind: str
    event_at: datetime
    availability_basis: str
    source_ref: str


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise StoreError(f"{name} is required (got {value!r})")
    return value


def _require_utc_instant(value: object, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise StoreError(f"{name} is required and must be a datetime (got {value!r})")
    if value.tzinfo is None or value.utcoffset() is None:
        raise StoreError(f"{name} must be tz-aware (naive datetimes are rejected)")
    return value.astimezone(UTC)


def _require_basis(value: object, instant: datetime, name: str) -> str:
    basis = _require_text(value, "availability_basis")
    if basis not in AVAILABILITY_BASES:
        raise StoreError(f"availability_basis must be one of {', '.join(AVAILABILITY_BASES)}")
    try:
        event_early_bound(instant, basis)  # a rule:date_eod_ist value must be D 23:59:59 IST
    except ValueError as exc:
        raise StoreError(f"{name} does not match its availability_basis ({exc})") from None
    return basis


def _ts(value: datetime) -> str:
    return value.astimezone(UTC).strftime(_TS_FORMAT)


def _sha256(parts: Sequence[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _check_observation(row: ObservationIn) -> tuple[ObservationIn, Decimal]:
    if not isinstance(row, ObservationIn):
        raise StoreError(f"expected an ObservationIn (got {type(row).__name__})")
    _require_text(row.series_key, "series_key")
    if type(row.period_date) is not date:
        raise StoreError(f"period_date must be a date (got {row.period_date!r})")
    if not isinstance(row.value, Decimal):
        raise StoreError(
            f"value must be a Decimal (got {type(row.value).__name__}; floats are rejected)"
        )
    if not row.value.is_finite():
        raise StoreError("value must be a finite Decimal")
    available_at = _require_utc_instant(row.available_at, "available_at")
    _require_basis(row.availability_basis, available_at, "available_at")
    _require_text(row.source_ref, "source_ref")
    if row.vintage not in VINTAGES:
        raise StoreError(f"vintage must be one of {', '.join(VINTAGES)}")
    if row.source_kind not in SOURCE_KINDS:
        raise StoreError(f"source_kind must be one of {', '.join(SOURCE_KINDS)}")
    return row, row.value.quantize(_VALUE_QUANTUM)


def observation_content_hash(row: ObservationIn) -> str:
    """SHA-256 over the identifying fields; ``ingested_at`` is deliberately excluded."""
    row, value = _check_observation(row)
    return _sha256(
        (
            row.series_key,
            row.period_date.isoformat(),
            format(value, "f"),
            _ts(row.available_at),
            row.availability_basis,
            row.source_ref,
            row.vintage,
            row.source_kind,
        )
    )


def _check_event(row: RevealEventIn) -> RevealEventIn:
    if not isinstance(row, RevealEventIn):
        raise StoreError(f"expected a RevealEventIn (got {type(row).__name__})")
    _require_text(row.ticker, "ticker")
    _require_text(row.fiscal_quarter, "fiscal_quarter")
    if row.event_kind not in EVENT_KINDS:
        raise StoreError(f"event_kind must be one of {', '.join(EVENT_KINDS)}")
    event_at = _require_utc_instant(row.event_at, "event_at")
    if event_at.microsecond != 0:
        raise StoreError("event_at must be a whole second")
    _require_basis(row.availability_basis, event_at, "event_at")
    _require_text(row.source_ref, "source_ref")
    return row


def reveal_event_content_hash(row: RevealEventIn) -> str:
    row = _check_event(row)
    return _sha256(
        (
            row.ticker,
            row.fiscal_quarter,
            row.event_kind,
            _ts(row.event_at),
            row.availability_basis,
            row.source_ref,
        )
    )


def _require_ingested_at(ingested_at: object) -> datetime:
    return _require_utc_instant(ingested_at, "ingested_at")


def ensure_series(
    conn: sa.Connection,
    series_key: str,
    source: str,
    metric: str,
    entity: str,
    unit: str,
    frequency: str,
    collection_mode: str,
) -> int:
    """Return the id of ``series_key``, inserting it if absent.

    An existing series with different metadata raises: series rows are immutable.
    """
    fields = {
        "source": source,
        "metric": metric,
        "entity": entity,
        "unit": unit,
        "frequency": frequency,
        "collection_mode": collection_mode,
    }
    _require_text(series_key, "series_key")
    for name, value in fields.items():
        _require_text(value, name)
    existing = conn.execute(sa.select(series).where(series.c.series_key == series_key)).first()
    if existing is not None:
        mapping = existing._mapping
        changed = [name for name, value in fields.items() if mapping[name] != value]
        if changed:
            raise StoreError(
                f"series {series_key} already exists with different {', '.join(changed)}"
            )
        return int(mapping["series_id"])
    result = conn.execute(sa.insert(series).values(series_key=series_key, **fields))
    return int(result.inserted_primary_key[0])


def insert_observations(
    conn: sa.Connection, rows: Sequence[ObservationIn], ingested_at: datetime
) -> int:
    """Insert every row whose content_hash is absent; return the number inserted.

    Every row is validated before anything is written. Each row's series must exist
    (see ``ensure_series``).
    """
    stamp = _require_ingested_at(ingested_at)
    hashed = [(row, observation_content_hash(row)) for row in rows]
    keys = sorted({row.series_key for row, _ in hashed})
    if not keys:
        return 0
    ids = {
        r.series_key: int(r.series_id)
        for r in conn.execute(
            sa.select(series.c.series_key, series.c.series_id).where(series.c.series_key.in_(keys))
        )
    }
    missing = [key for key in keys if key not in ids]
    if missing:
        raise StoreError(f"unknown series: {', '.join(missing)} (call ensure_series first)")
    existing = set(
        conn.execute(
            sa.select(observations.c.content_hash).where(
                observations.c.series_id.in_(sorted(ids.values()))
            )
        ).scalars()
    )
    inserted = 0
    for row, digest in hashed:
        if digest in existing:
            continue
        existing.add(digest)
        conn.execute(
            sa.insert(observations).values(
                series_id=ids[row.series_key],
                period_date=row.period_date,
                value=row.value,
                available_at=row.available_at,
                availability_basis=row.availability_basis,
                ingested_at=stamp,
                vintage=row.vintage,
                source_ref=row.source_ref,
                source_kind=row.source_kind,
                content_hash=digest,
            )
        )
        inserted += 1
    return inserted


def insert_reveal_events(
    conn: sa.Connection, rows: Sequence[RevealEventIn], ingested_at: datetime
) -> int:
    """Insert every event whose content_hash is absent; return the number inserted."""
    stamp = _require_ingested_at(ingested_at)
    hashed = [(row, reveal_event_content_hash(row)) for row in rows]
    if not hashed:
        return 0
    digests = sorted({digest for _, digest in hashed})
    existing = set(
        conn.execute(
            sa.select(reveal_events.c.content_hash).where(reveal_events.c.content_hash.in_(digests))
        ).scalars()
    )
    inserted = 0
    for row, digest in hashed:
        if digest in existing:
            continue
        existing.add(digest)
        conn.execute(
            sa.insert(reveal_events).values(
                ticker=row.ticker,
                fiscal_quarter=row.fiscal_quarter,
                event_kind=row.event_kind,
                event_at=row.event_at,
                availability_basis=row.availability_basis,
                source_ref=row.source_ref,
                ingested_at=stamp,
                content_hash=digest,
            )
        )
        inserted += 1
    return inserted


__all__ = [
    "EVENT_KINDS",
    "SOURCE_KINDS",
    "VINTAGES",
    "ObservationIn",
    "RevealEventIn",
    "StoreError",
    "ensure_series",
    "insert_observations",
    "insert_reveal_events",
    "observation_content_hash",
    "reveal_event_content_hash",
]
