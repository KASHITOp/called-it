"""Seed loader: ``data/seed/quarterly_revenue.csv`` into the point-in-time store (DATA-01).

Each CSV row becomes:

- one observation on series ``rev.consolidated.<TICKER>`` with ``period_date = period_end``,
  ``value = Decimal(revenue_cr)`` and ``available_at`` taken from ``results_date``:
  ``YYYY-MM-DD`` with basis ``rule:date_eod_ist`` is ``D 23:59:59 IST`` (the late bound,
  D-24); ``YYYY-MM-DDTHH:MM+05:30`` with basis ``exchange_timestamp`` is that instant;
- for ``first_reported`` rows only, a ``results`` reveal event at the same instant and, when
  ``business_update_at`` is present, a ``business_update`` reveal event.

Validation (D-25) covers the whole file before anything is written, and every error is
reported as ``(row, column, reason)``. Rows are numbered as in a spreadsheet: the header is
row 1, and row 0 means the file as a whole. Any error means nothing is inserted, and the
write itself is one transaction, because a partial load into an insert-only store would be
permanent.

Rehearsal and live loads (T-01-17) accept only ``data/seed/quarterly_revenue.csv``, require
every row to be verified (D-22) and refuse ``.invalid`` hosts, so the synthetic test fixture
can never reach a real database. Live writes also need the GitHub Actions main-branch context.

The file may carry a UTF-8 BOM and CRLF line endings (a spreadsheet export); both are read
transparently. Fully blank rows are ignored.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import sqlalchemy as sa

from calledit_data.calendar.fiscal import FiscalQuarter
from calledit_data.calendar.reveal import AVAILABILITY_BASES
from calledit_data.calendar.tz import date_eod_ist_utc, ist_date, to_utc
from calledit_data.db.settings import Settings, require_live_write_context
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
BASIS = "consolidated"
LINE_ITEM = "Revenue from operations"
UNITS_IN_FILING = ("crore", "lakh", "million")
VINTAGES = ("first_reported", "restated")
STRICT_ENVS = ("rehearsal", "live")

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

    @property
    def exact(self) -> bool:
        return self.basis == "exchange_timestamp"


@dataclass
class _Facts:
    """What cross-row checks need from one row (filled in as far as the row parsed)."""

    row: int
    ticker: str
    quarter: str
    vintage: str
    results_raw: str
    results: _Instant | None


def _ledger_safe(value: str, *, allow_space: bool) -> bool:
    low = 0x20 if allow_space else 0x21
    return all(low <= ord(ch) <= 0x7E and ch not in '"\\' for ch in value)


class _RowCheck:
    """Collects the errors for one CSV row."""

    def __init__(self, row: int, record: Mapping[str, str], now: datetime) -> None:
        self.row = row
        self.record = record
        self.now = now
        self.errors: list[SeedRowError] = []

    @property
    def failed(self) -> bool:
        return bool(self.errors)

    def get(self, column: str) -> str:
        return self.record.get(column) or ""

    def error(self, column: str, reason: str) -> None:
        self.errors.append(SeedRowError(self.row, column, reason))

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
            if day > ist_date(self.now):
                self.error(value_col, "is in the future")
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
        value = to_utc(stamp)
        if value > self.now:
            self.error(value_col, "is in the future")
            return None
        return _Instant(value, basis, stamp.date())

    def url(self, column: str, *, forbid_synthetic: bool) -> str | None:
        value = self.get(column)
        if not _ledger_safe(value, allow_space=False):
            self.error(
                column,
                "must be printable ASCII without spaces, double quotes or backslashes "
                "(it enters canonical ledger snapshots)",
            )
            return None
        try:
            split = urlsplit(value)
            host = split.hostname
        except ValueError:
            self.error(column, "is not a valid URL")
            return None
        if split.scheme != "https":
            self.error(column, "must be an https URL")
            return None
        if not host:
            self.error(column, "has no host")
            return None
        if "#" in value:
            self.error(column, "must not contain a fragment (#); put the page in page_ref")
            return None
        if forbid_synthetic and (host == "invalid" or host.endswith(".invalid")):
            self.error(column, f"synthetic host {host} is refused in rehearsal and live loads")
            return None
        return value


def _check_row(
    check: _RowCheck,
    rules: Mapping[str, SeedCompanyRules],
    *,
    require_verified: bool,
    forbid_synthetic: bool,
) -> tuple[SeedRow | None, _Facts]:
    ticker = check.get("ticker")
    company = rules.get(ticker)
    if company is None:
        check.error("ticker", f"unknown ticker {ticker!r} (not in the universe config)")
    elif check.get("isin") != company.isin:
        check.error("isin", f"must equal the universe ISIN {company.isin}")

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
    if quarter is not None and period_end is not None and period_end != quarter.end:
        check.error(
            "period_end", f"must equal the {quarter.label} quarter end {quarter.end.isoformat()}"
        )

    if check.get("basis") != BASIS:
        check.error("basis", f"must be {BASIS} (the target is consolidated revenue)")
    if check.get("line_item") != LINE_ITEM:
        check.error(
            "line_item",
            f"must be '{LINE_ITEM}' (never total income or adjusted revenue, D-13)",
        )
    if check.get("unit_in_filing") not in UNITS_IN_FILING:
        check.error("unit_in_filing", f"must be one of {', '.join(UNITS_IN_FILING)}")

    revenue: Decimal | None = None
    raw_revenue = check.get("revenue_cr")
    if _REVENUE_RE.fullmatch(raw_revenue) is None:
        check.error(
            "revenue_cr",
            "must be INR crore with exactly 2 decimals and no separators, e.g. 12345.60",
        )
    elif Decimal(raw_revenue) <= 0:
        check.error("revenue_cr", "must be positive")
    else:
        revenue = Decimal(raw_revenue)

    vintage = check.get("vintage")
    if vintage not in VINTAGES:
        check.error("vintage", "must be first_reported or restated")

    results = check.instant("results_date", "results_at_basis")
    if results is not None and quarter is not None and results.ist_date <= quarter.end:
        check.error("results_date", "must fall after the quarter end")
        results_ok = False
    else:
        results_ok = results is not None

    business_update = _check_business_update(
        check,
        company,
        ticker,
        quarter,
        vintage,
        results if results_ok else None,
        forbid_synthetic=forbid_synthetic,
    )

    source_url = ""
    if not check.get("source_url"):
        check.error("source_url", "required (cite the filing or IR document)")
    else:
        source_url = check.url("source_url", forbid_synthetic=forbid_synthetic) or ""
    page_ref = check.get("page_ref")
    if page_ref and (not _ledger_safe(page_ref, allow_space=True) or page_ref != page_ref.strip()):
        check.error(
            "page_ref",
            "must be printable ASCII without double quotes, backslashes or edge spaces",
        )

    verified = check.get("verified")
    if verified not in ("Y", "N"):
        check.error("verified", "must be Y or N")
    elif verified == "N" and require_verified:
        check.error("verified", "unverified row (verified = N) is refused for this load (D-22)")

    facts = _Facts(
        check.row,
        ticker,
        label,
        vintage,
        check.get("results_date"),
        results if results_ok else None,
    )
    if check.failed:
        return None, facts
    assert quarter is not None and period_end is not None and revenue is not None
    assert results is not None

    source_ref = f"{source_url}#{page_ref}" if page_ref else source_url
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
    return SeedRow(check.row, ticker, quarter.label, observation, tuple(events)), facts


def _check_business_update(
    check: _RowCheck,
    company: SeedCompanyRules | None,
    ticker: str,
    quarter: FiscalQuarter | None,
    vintage: str,
    results: _Instant | None,
    *,
    forbid_synthetic: bool,
) -> _Instant | None:
    """Validate the business-update columns (D-24); return the instant when there is one."""
    raw = check.get("business_update_at")
    if not raw:
        if company is not None and company.has_business_update and vintage == "first_reported":
            check.error(
                "business_update_at",
                f"required for {ticker} first_reported rows (its reveal is the business update)",
            )
            return None
        for column in ("business_update_basis", "business_update_url"):
            if check.get(column):
                check.error(column, "set only together with business_update_at")
                return None
        return None
    if company is not None and not company.has_business_update:
        check.error(
            "business_update_at", f"{ticker} has no business update (has_business_update = false)"
        )
        return None
    if vintage == "restated":
        check.error("business_update_at", "restated rows never carry a business update")
        return None
    update = check.instant("business_update_at", "business_update_basis")
    if update is not None:
        if quarter is not None and update.ist_date <= quarter.end:
            check.error("business_update_at", "must fall after the quarter end")
            update = None
        elif results is not None:
            late = (
                update.value > results.value
                if update.exact and results.exact
                else update.ist_date > results.ist_date
            )
            if late:
                check.error("business_update_at", "must be on or before the results")
                update = None
    if check.get("business_update_url"):
        check.url("business_update_url", forbid_synthetic=forbid_synthetic)
    return update


def _cross_row_checks(facts: list[_Facts]) -> list[SeedRowError]:
    """Duplicates, one first_reported per quarter, and restated rows that follow one."""
    errors: list[SeedRowError] = []
    seen: dict[tuple[str, str, str, str], int] = {}
    first: dict[tuple[str, str], _Facts] = {}
    duplicate_rows: set[int] = set()
    for f in facts:
        if not (f.ticker and f.quarter and f.vintage and f.results_raw):
            continue
        key = (f.ticker, f.quarter, f.vintage, f.results_raw)
        if key in seen:
            errors.append(
                SeedRowError(
                    f.row,
                    "results_date",
                    f"duplicates row {seen[key]} (same ticker, fiscal_quarter, vintage, "
                    "results_date)",
                )
            )
            duplicate_rows.add(f.row)
            continue
        seen[key] = f.row
        if f.vintage == "first_reported":
            earlier = first.get((f.ticker, f.quarter))
            if earlier is not None:
                errors.append(
                    SeedRowError(
                        f.row,
                        "vintage",
                        f"a second first_reported row for {f.ticker} {f.quarter} "
                        f"(row {earlier.row}); later values are vintage restated",
                    )
                )
            else:
                first[(f.ticker, f.quarter)] = f
    for f in facts:
        if f.vintage != "restated" or f.row in duplicate_rows or not f.ticker or not f.quarter:
            continue
        original = first.get((f.ticker, f.quarter))
        if original is None:
            errors.append(
                SeedRowError(
                    f.row,
                    "vintage",
                    f"restated row has no first_reported row for {f.ticker} {f.quarter}",
                )
            )
        elif (
            f.results is not None
            and original.results is not None
            and not f.results.value > original.results.value
        ):
            errors.append(
                SeedRowError(
                    f.row,
                    "results_date",
                    f"a restatement must become available after the first report (row "
                    f"{original.row})",
                )
            )
    return errors


def _read_records(path: Path) -> tuple[tuple[str, ...], list[dict]]:
    with open(path, "rb") as handle:
        data = handle.read()
    text = data.decode("utf-8-sig")  # tolerate a spreadsheet BOM
    reader = csv.DictReader(io.StringIO(text, newline=""))
    records = list(reader)
    return tuple(reader.fieldnames or ()), records


def parse_seed_csv(
    path: Path,
    rules: Mapping[str, SeedCompanyRules],
    *,
    require_verified: bool,
    now: datetime,
    forbid_synthetic: bool = False,
) -> SeedParseResult:
    """Parse and validate the whole file; never writes anything."""
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise SeedError("now must be a tz-aware datetime")
    now = to_utc(now)
    result = SeedParseResult()
    try:
        header, records = _read_records(path)
    except UnicodeDecodeError:
        result.errors.append(SeedRowError(0, "file", "is not valid UTF-8"))
        return result
    except csv.Error as exc:
        result.errors.append(SeedRowError(0, "file", f"is not valid CSV ({exc})"))
        return result
    if header != COLUMNS:
        result.errors.append(SeedRowError(1, "header", "must be exactly: " + ",".join(COLUMNS)))
        return result
    facts: list[_Facts] = []
    candidates: list[SeedRow] = []
    for index, record in enumerate(records, start=2):
        values = list(record.values())
        if None not in record and all(v == "" for v in values):
            continue  # a blank spreadsheet row carries no data
        result.rows_seen += 1
        if None in record or any(v is None for v in values):
            count = len(COLUMNS) + len(record.get(None) or ()) - sum(v is None for v in values)
            result.errors.append(
                SeedRowError(index, "row", f"has {count} fields, expected {len(COLUMNS)}")
            )
            continue
        check = _RowCheck(index, record, now)
        row, row_facts = _check_row(
            check, rules, require_verified=require_verified, forbid_synthetic=forbid_synthetic
        )
        result.errors.extend(check.errors)
        facts.append(row_facts)
        if row is not None:
            candidates.append(row)
    cross = _cross_row_checks(facts)
    result.errors.extend(cross)
    result.errors.sort(key=lambda e: e.row)  # stable: keeps each row's column order
    bad_rows = {e.row for e in cross}
    result.rows = [row for row in candidates if row.row not in bad_rows]
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


def _is_canonical(path: Path) -> bool:
    return Path(path).resolve() == (Path.cwd() / CANONICAL_SEED_PATH).resolve()


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
    """Validate ``path`` and, unless ``dry_run``, insert it in one transaction.

    ``engine`` may be ``None`` for a dry run: validation never touches the database.
    """
    strict = settings.calledit_env in STRICT_ENVS
    if strict:
        if not _is_canonical(path):
            raise SeedError(
                f"CALLEDIT_ENV={settings.calledit_env} loads only "
                f"{CANONICAL_SEED_PATH.as_posix()} (got {Path(path).as_posix()})"
            )
        require_verified = True
    if settings.calledit_env == "live" and not dry_run:
        require_live_write_context(settings)
    parsed = parse_seed_csv(
        path, rules, require_verified=require_verified, now=now, forbid_synthetic=strict
    )
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
        obs = insert_observations(conn, [row.observation for row in parsed.rows], to_utc(now))
        events = insert_reveal_events(
            conn, [event for row in parsed.rows for event in row.events], to_utc(now)
        )
    return LoadReport(obs, events, parsed.rows_seen, (), dry_run)
