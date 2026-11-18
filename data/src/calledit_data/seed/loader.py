"""Seed loader: ``data/seed/quarterly_revenue.csv`` into the point-in-time store (DATA-01).

Each CSV row becomes:

- one observation on series ``rev.consolidated.<TICKER>`` with ``period_date = period_end``,
  ``value = Decimal(revenue_cr)`` and ``available_at`` taken from ``results_date``:
  ``YYYY-MM-DD`` with basis ``rule:date_eod_ist`` is ``D 23:59:59 IST`` (the late bound,
  D-24); ``YYYY-MM-DDTHH:MM+05:30`` with basis ``exchange_timestamp`` is that instant;
- for ``first_reported`` rows only, a ``results`` reveal event at the same instant and, when
  ``business_update_at`` is present, a ``business_update`` reveal event.

The whole file is parsed and validated before anything is written, and every error is
reported as ``(row, column, reason)``. Rows are numbered as in a spreadsheet: the header is
row 1. Any error means nothing is inserted (D-25). The write is one transaction.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa

from calledit_data.calendar.fiscal import FiscalQuarter
from calledit_data.calendar.reveal import AVAILABILITY_BASES
from calledit_data.calendar.tz import date_eod_ist_utc, to_utc
from calledit_data.db.settings import Settings
from calledit_data.store.writer import (
    ObservationIn,
    RevealEventIn,
    ensure_series,
    insert_observations,
    insert_reveal_events,
)

CANONICAL_SEED_PATH = Path("data/seed/quarterly_revenue.csv")

COLUMNS: tuple[str, ...] = (
    "ticker",
    "isin",
    "fiscal_quarter",
    "period_end",
    "basis",
    "line_item",
    "unit_in_filing",
    "revenue_cr",
    "results_date",
    "results_at_basis",
    "business_update_at",
    "business_update_basis",
    "business_update_url",
    "source_url",
    "page_ref",
    "vintage",
    "verified",
    "notes",
)

SERIES_PREFIX = "rev.consolidated."

_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)
_STAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}\+05:30", re.ASCII)
_REVENUE_RE = re.compile(r"(0|[1-9][0-9]{0,11})\.[0-9]{2}", re.ASCII)


class SeedError(ValueError):
    """The seed load was refused before validation (wrong path, wrong context)."""


@dataclass(frozen=True)
class SeedCompanyRules:
    """What the universe says about one ticker, for validating its seed rows."""

    isin: str
    has_business_update: bool


@dataclass(frozen=True)
class SeedRowError:
    row: int
    column: str
    reason: str

    def __str__(self) -> str:
        return f"row {self.row}, column {self.column}: {self.reason}"


@dataclass(frozen=True)
class SeedRow:
    row: int
    ticker: str
    fiscal_quarter: str
    observation: ObservationIn
    events: tuple[RevealEventIn, ...]


@dataclass
class SeedParseResult:
    rows: list[SeedRow] = field(default_factory=list)
    errors: list[SeedRowError] = field(default_factory=list)
    rows_seen: int = 0


@dataclass(frozen=True)
class LoadReport:
    observations_inserted: int
    events_inserted: int
    rows_seen: int
    errors: tuple[SeedRowError, ...]
    dry_run: bool

    @property
    def ok(self) -> bool:
        return not self.errors


def series_key_for(ticker: str) -> str:
    return SERIES_PREFIX + ticker


@dataclass(frozen=True)
class _Instant:
    value: datetime  # UTC
    basis: str
    ist_date: date


class _RowCheck:
    """Collects the errors for one CSV row."""

    def __init__(self, row: int, record: Mapping[str, str], errors: list[SeedRowError]) -> None:
        self.row = row
        self.record = record
        self.errors = errors
        self.failed = False

    def get(self, column: str) -> str:
        return self.record.get(column) or ""

    def error(self, column: str, reason: str) -> None:
        self.errors.append(SeedRowError(self.row, column, reason))
        self.failed = True

    def instant(self, value_col: str, basis_col: str) -> _Instant | None:
        raw = self.get(value_col)
        basis = self.get(basis_col)
        if basis not in AVAILABILITY_BASES:
            self.error(basis_col, f"must be one of {', '.join(AVAILABILITY_BASES)}")
            return None
        if basis == "rule:date_eod_ist":
            if _DATE_RE.fullmatch(raw) is None:
                self.error(value_col, "basis rule:date_eod_ist needs a date YYYY-MM-DD")
                return None
            try:
                day = date.fromisoformat(raw)
            except ValueError:
                self.error(value_col, f"not a real date: {raw!r}")
                return None
            return _Instant(date_eod_ist_utc(day), basis, day)
        if _STAMP_RE.fullmatch(raw) is None:
            self.error(value_col, "basis exchange_timestamp needs YYYY-MM-DDTHH:MM+05:30")
            return None
        try:
            stamp = datetime.fromisoformat(raw)
        except ValueError:
            self.error(value_col, f"not a real timestamp: {raw!r}")
            return None
        return _Instant(to_utc(stamp), basis, stamp.date())


def _source_ref(url: str, page_ref: str) -> str:
    return f"{url}#{page_ref}" if page_ref else url


def _check_row(
    check: _RowCheck,
    rules: Mapping[str, SeedCompanyRules],
    *,
    require_verified: bool,
) -> SeedRow | None:
    ticker = check.get("ticker")
    if ticker not in rules:
        check.error("ticker", f"unknown ticker {ticker!r} (not in the universe config)")

    quarter: FiscalQuarter | None = None
    label = check.get("fiscal_quarter")
    try:
        quarter = FiscalQuarter.parse(label)
    except ValueError:
        check.error("fiscal_quarter", f"not a fiscal quarter label: {label!r}")
    if quarter is not None and quarter.label != label:
        check.error("fiscal_quarter", f"must be written canonically as {quarter.label}")
        quarter = None

    period_end: date | None = None
    raw_end = check.get("period_end")
    if _DATE_RE.fullmatch(raw_end) is None:
        check.error("period_end", "must be a date YYYY-MM-DD")
    else:
        try:
            period_end = date.fromisoformat(raw_end)
        except ValueError:
            check.error("period_end", f"not a real date: {raw_end!r}")

    revenue: Decimal | None = None
    raw_revenue = check.get("revenue_cr")
    if _REVENUE_RE.fullmatch(raw_revenue) is None:
        check.error("revenue_cr", "must be INR crore with exactly 2 decimals, e.g. 12345.60")
    else:
        revenue = Decimal(raw_revenue)

    results = check.instant("results_date", "results_at_basis")

    business_update: _Instant | None = None
    if check.get("business_update_at"):
        business_update = check.instant("business_update_at", "business_update_basis")

    source_url = check.get("source_url")
    if not source_url:
        check.error("source_url", "required")
    page_ref = check.get("page_ref")

    vintage = check.get("vintage")
    if vintage not in ("first_reported", "restated"):
        check.error("vintage", "must be first_reported or restated")

    verified = check.get("verified")
    if verified not in ("Y", "N"):
        check.error("verified", "must be Y or N")
    elif verified == "N" and require_verified:
        check.error("verified", "unverified row (verified = N) refused for this load")

    if check.failed:
        return None
    assert quarter is not None and period_end is not None and revenue is not None
    assert results is not None

    source_ref = _source_ref(source_url, page_ref)
    observation = ObservationIn(
        series_key=series_key_for(ticker),
        period_date=period_end,
        value=revenue,
        available_at=results.value,
        availability_basis=results.basis,
        source_ref=source_ref,
        vintage=vintage,
        source_kind="seed_csv" if verified == "Y" else "seed_csv_unverified",
    )
    events: list[RevealEventIn] = []
    if vintage == "first_reported":
        events.append(
            RevealEventIn(
                ticker=ticker,
                fiscal_quarter=quarter.label,
                event_kind="results",
                event_at=results.value,
                availability_basis=results.basis,
                source_ref=source_ref,
            )
        )
        if business_update is not None:
            events.append(
                RevealEventIn(
                    ticker=ticker,
                    fiscal_quarter=quarter.label,
                    event_kind="business_update",
                    event_at=business_update.value,
                    availability_basis=business_update.basis,
                    source_ref=check.get("business_update_url") or source_ref,
                )
            )
    return SeedRow(check.row, ticker, quarter.label, observation, tuple(events))


def parse_seed_csv(
    path: Path,
    rules: Mapping[str, SeedCompanyRules],
    *,
    require_verified: bool,
    now: datetime,
) -> SeedParseResult:
    """Parse and validate the whole file; never writes anything."""
    result = SeedParseResult()
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = tuple(reader.fieldnames or ())
        if header != COLUMNS:
            result.errors.append(SeedRowError(1, "header", "must be exactly: " + ",".join(COLUMNS)))
            return result
        for index, record in enumerate(reader, start=2):
            result.rows_seen += 1
            check = _RowCheck(index, record, result.errors)
            row = _check_row(check, rules, require_verified=require_verified)
            if row is not None:
                result.rows.append(row)
    _ = now
    return result


# Arbitrary constant key for the Postgres transaction-scoped advisory lock ("SEED").
_PG_SEED_LOCK_KEY = 0x53454544


def _take_write_lock(conn: sa.Connection) -> None:
    """Serialise loaders so the existing-hash read and the inserts see the same store.

    SQLite: ``BEGIN IMMEDIATE`` (pysqlite would otherwise begin only at the first INSERT).
    Postgres: a transaction-scoped advisory lock. The UNIQUE keys and replace triggers still
    back this up at the DB level.
    """
    if conn.dialect.name == "sqlite":
        conn.exec_driver_sql("BEGIN IMMEDIATE")
    elif conn.dialect.name == "postgresql":
        conn.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": _PG_SEED_LOCK_KEY})


def load_seed(
    engine: sa.Engine | None,
    path: Path,
    rules: Mapping[str, SeedCompanyRules],
    settings: Settings,
    *,
    now: datetime,
    dry_run: bool,
    require_verified: bool = False,
) -> LoadReport:
    """Validate ``path`` and, unless ``dry_run``, insert it in one transaction."""
    _ = settings
    parsed = parse_seed_csv(path, rules, require_verified=require_verified, now=now)
    if parsed.errors or dry_run:
        return LoadReport(0, 0, parsed.rows_seen, tuple(parsed.errors), dry_run)
    if engine is None:
        raise SeedError("a database engine is required for a non-dry-run load")
    with engine.begin() as conn:
        _take_write_lock(conn)
        for ticker in sorted({row.ticker for row in parsed.rows}):
            ensure_series(
                conn,
                series_key_for(ticker),
                source="seed_csv",
                metric="revenue_from_operations_consolidated",
                entity=ticker,
                unit="inr_crore",
                frequency="quarterly",
                collection_mode="manual_seed",
            )
        obs = insert_observations(conn, [row.observation for row in parsed.rows], now)
        events = insert_reveal_events(
            conn, [event for row in parsed.rows for event in row.events], now
        )
    return LoadReport(obs, events, parsed.rows_seen, (), dry_run)
