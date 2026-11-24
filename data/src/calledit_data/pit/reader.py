"""``PointInTimeReader``: the only model-facing read path into the store (PIT-03).

Every read is anchored at an explicit, tz-aware UTC ``as_of``:

- ``backtest`` mode returns rows with ``available_at < as_of`` (strict: a row available at
  exactly ``as_of`` is not yet known).
- ``live`` mode additionally requires ``ingested_at <= as_of``, so a value loaded after the
  instant cannot leak into a call made at that instant.

``reveal_events`` applies the same rule to ``event_at``.

After the SQL filter, a post-condition re-checks every fetched row in Python and raises
``LeakageError`` if any row violates the rule. The two hooks ``_row_filter`` and
``_postcondition`` are overridable on purpose: the deliberately leaky readers of the leakage
meta-test subclass them, and the suite must catch every one.

Revisions (D-05): of several vintages of the same ``period_date`` known at ``as_of``, the
latest ``available_at`` wins. Two vintages that share the latest ``available_at`` but carry
different values are a tie that cannot be ordered by anything public: ``series`` raises
``TiedVintageError`` and never picks one (decision of 24 Nov 2026, in every mode). Identical
values at the same ``available_at`` are not a conflict; the lower-level order
``(ingested_at, content_hash)`` then only keeps the result deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

import sqlalchemy as sa

from calledit_data.db.schema import observations, reveal_events, series

Mode = Literal["backtest", "live"]
MODES: tuple[str, ...] = ("backtest", "live")


class LeakageError(AssertionError):
    """A read returned a row that was not knowable at ``as_of``."""


class TiedVintageError(ValueError):
    """Two vintages of one period share the latest ``available_at`` with different values."""

    def __init__(self, series_key: str, period_dates: tuple[date, ...]) -> None:
        self.series_key = series_key
        self.period_dates = period_dates
        super().__init__(
            f"{series_key}: tied available_at with different values for "
            + ", ".join(d.isoformat() for d in period_dates)
        )


@dataclass(frozen=True)
class Observation:
    obs_id: int
    series_key: str
    period_date: date
    value: Decimal
    available_at: datetime
    availability_basis: str
    ingested_at: datetime
    vintage: str
    source_ref: str
    source_kind: str
    content_hash: str

    @property
    def known_at(self) -> datetime:
        return self.available_at


@dataclass(frozen=True)
class RevealEvent:
    ticker: str
    fiscal_quarter: str
    event_kind: str
    event_at: datetime
    availability_basis: str
    source_ref: str
    ingested_at: datetime
    content_hash: str

    @property
    def known_at(self) -> datetime:
        return self.event_at


_TIME_COLUMN = {"observations": "available_at", "reveal_events": "event_at"}


class PointInTimeReader:
    """Read the store as it was knowable at ``as_of``."""

    def __init__(self, engine: sa.Engine, as_of: datetime, mode: Mode) -> None:
        if not isinstance(as_of, datetime):
            raise TypeError(f"as_of must be a datetime (got {type(as_of).__name__})")
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be tz-aware UTC (naive datetimes are rejected)")
        if as_of.utcoffset() != timedelta(0):
            raise ValueError("as_of must be expressed in UTC (offset +00:00)")
        if mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)} (got {mode!r})")
        self._engine = engine
        self._as_of = as_of
        self._mode: Mode = mode

    @property
    def as_of(self) -> datetime:
        return self._as_of

    @property
    def mode(self) -> Mode:
        return self._mode

    # --- overridable hooks -------------------------------------------------------------

    def _row_filter(self, table: sa.Table) -> sa.ColumnElement[bool]:
        """SQL clause selecting the rows knowable at ``as_of``."""
        clause = table.c[_TIME_COLUMN[table.name]] < self._as_of
        if self._mode == "live":
            clause = sa.and_(clause, table.c.ingested_at <= self._as_of)
        return clause

    def _postcondition(self, rows: tuple[Observation, ...] | tuple[RevealEvent, ...]) -> None:
        """Raise ``LeakageError`` if any fetched row was not knowable at ``as_of``."""
        offending = sorted(
            row.content_hash
            for row in rows
            if not row.known_at < self._as_of
            or (self._mode == "live" and not row.ingested_at <= self._as_of)
        )
        if offending:
            raise LeakageError(
                f"{len(offending)} row(s) not knowable at as_of "
                f"{self._as_of.isoformat()} ({self._mode}): {', '.join(offending)}"
            )

    # --- reads -------------------------------------------------------------------------

    def series(self, series_key: str) -> tuple[Observation, ...]:
        """Latest vintage per ``period_date`` known at ``as_of``, sorted by ``period_date``."""
        query = (
            sa.select(
                observations.c.obs_id,
                series.c.series_key,
                observations.c.period_date,
                observations.c.value,
                observations.c.available_at,
                observations.c.availability_basis,
                observations.c.ingested_at,
                observations.c.vintage,
                observations.c.source_ref,
                observations.c.source_kind,
                observations.c.content_hash,
            )
            .select_from(observations.join(series, observations.c.series_id == series.c.series_id))
            .where(series.c.series_key == series_key)
            .where(self._row_filter(observations))
        )
        with self._engine.connect() as conn:
            fetched = tuple(Observation(**row._mapping) for row in conn.execute(query))
        self._postcondition(fetched)
        latest: dict[date, Observation] = {}
        for obs in fetched:
            current = latest.get(obs.period_date)
            if current is None or _vintage_key(obs) > _vintage_key(current):
                latest[obs.period_date] = obs
        tied = sorted(
            {
                obs.period_date
                for obs in fetched
                if obs.available_at == latest[obs.period_date].available_at
                and obs.value != latest[obs.period_date].value
            }
        )
        if tied:
            raise TiedVintageError(series_key, tuple(tied))
        return tuple(latest[d] for d in sorted(latest))

    def reveal_events(self, ticker: str, fiscal_quarter_label: str) -> tuple[RevealEvent, ...]:
        """Reveal events for one company and quarter known at ``as_of``, in time order."""
        query = (
            sa.select(
                reveal_events.c.ticker,
                reveal_events.c.fiscal_quarter,
                reveal_events.c.event_kind,
                reveal_events.c.event_at,
                reveal_events.c.availability_basis,
                reveal_events.c.source_ref,
                reveal_events.c.ingested_at,
                reveal_events.c.content_hash,
            )
            .where(reveal_events.c.ticker == ticker)
            .where(reveal_events.c.fiscal_quarter == fiscal_quarter_label)
            .where(self._row_filter(reveal_events))
        )
        with self._engine.connect() as conn:
            fetched = tuple(RevealEvent(**row._mapping) for row in conn.execute(query))
        self._postcondition(fetched)
        return tuple(sorted(fetched, key=lambda e: (e.event_at, e.ingested_at, e.content_hash)))


def _vintage_key(obs: Observation) -> tuple[datetime, datetime, str]:
    return (obs.available_at, obs.ingested_at, obs.content_hash)
