"""The lock: baseline per enabled company -> chained prediction or gap record (LEDG-05).

``run_lock`` is the only writer of prediction and gap records. It has no parameter, option,
environment variable or config key that sets the lock time: the caller passes ``now`` (the CLI
reads the clock exactly once, in ``nowcaster.clock``) and that single instant is both ``as_of``
and ``locked_at`` for every company in the run.

Order of checks (any failure before the first append appends nothing):

1. live only: GitHub Actions on ``refs/heads/main``, a confirmed universe (ISINs and breaks),
   and the Postgres self-check (``run_db_check``);
2. a rules record exists, still matches the files on disk, and is not later than ``now``
   (``lock_before_rules``; decision of 24 Nov 2026);
3. per company, on UTC instants: the quarter is live (``period_start <= now < earliest
   plausible reveal``) and no stored reveal event has an early bound ``<= now`` (D-14, D-27);
4. if every company was refused, stop with ``EXIT_REFUSED``.

Then, per company in sorted ticker order, each in its own transaction:

- a ``BaselineResult`` is appended as a ``prediction`` record (D-12, interval ``none``);
- a ``BaselineRefusal`` is appended as a ``gap`` record, never imputed (D-08).

A repeated lock for the same company and quarter appends a new, later record; earlier records
are never overwritten or edited, and the official call is the last valid lock (decision of
24 Nov 2026).

Exit codes are documented in ``nowcaster.exit_codes`` (D-17).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

import sqlalchemy as sa
from calledit_data.calendar.fiscal import FiscalQuarter
from calledit_data.calendar.reveal import earliest_plausible_reveal, event_early_bound
from calledit_data.db.check import run_db_check
from calledit_data.db.engine import make_engine
from calledit_data.db.settings import LiveContextError, Settings, require_live_write_context
from calledit_data.pit.reader import PointInTimeReader
from sqlalchemy.engine import make_url

from nowcaster.baseline import BaselineRefusal, BaselineResult, compute_baseline
from nowcaster.exit_codes import EXIT_ENV, EXIT_OK, EXIT_PARTIAL, EXIT_REFUSED
from nowcaster.ledger.canonical import CanonicalError, format_ts
from nowcaster.ledger.chain import AppendedRecord, Builder, ForkError, RecordError, append_record
from nowcaster.ledger.records import (
    LOCK_KINDS,
    TypedColumns,
    build_gap_payload,
    build_prediction_payload,
    gap_typed_columns,
    prediction_typed_columns,
)
from nowcaster.rules import RulesError, current_run_id, latest_rules_record, stale_fields
from nowcaster.universe import Company, Universe, UniverseError, load_universe

LockKind = Literal["dispatch", "weekly", "final"]
_GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")


class LockRefused(RuntimeError):
    """The whole run is refused before anything is appended (fixed, non-secret message)."""

    def __init__(self, message: str, exit_code: int = EXIT_REFUSED) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class CompanyOutcome:
    ticker: str
    status: Literal["locked", "gap", "refused"]
    detail: str
    seq: int | None = None
    hash: str | None = None

    def line(self) -> str:
        if self.status == "locked":
            return f"{self.ticker} LOCKED seq={self.seq} hash={self.hash}"
        if self.status == "gap":
            return f"{self.ticker} GAP seq={self.seq} {self.detail}"
        return f"{self.ticker} REFUSED {self.detail}"


@dataclass
class LockReport:
    exit_code: int
    appended: list[AppendedRecord] = field(default_factory=list)
    refused: dict[str, str] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)
    outcomes: list[CompanyOutcome] = field(default_factory=list)
    message: str = ""


def _check_now(now: datetime) -> None:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("now must be a tz-aware UTC datetime")
    if now.microsecond != 0:
        raise ValueError("now must be truncated to the second")


def _code_git_sha(settings: Settings) -> str:
    """``GITHUB_SHA`` or ``git rev-parse HEAD``; ``none`` outside live when neither exists."""
    sha = os.environ.get("GITHUB_SHA", "").strip()
    if _GIT_SHA_RE.fullmatch(sha):
        return sha
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        sha = result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        sha = ""
    if _GIT_SHA_RE.fullmatch(sha):
        return sha
    if settings.calledit_env == "live":
        raise LockRefused("cannot determine the code commit (GITHUB_SHA or git HEAD)")
    return "none"


def _sqlite_store_missing(settings: Settings) -> bool:
    if settings.backend != "sqlite":
        return False
    database = make_url(settings.database_url.get_secret_value()).database or ""
    return database in ("", ":memory:") or not os.path.isfile(database)


def _prediction_builder(
    result: BaselineResult,
    company: Company,
    quarter: FiscalQuarter,
    epr: datetime,
    kind: str,
    rules_seq: int,
    rules_hash: str,
    universe_sha256: str,
    code_sha: str,
    run_id: str,
) -> Builder:
    def build(seq: int, prev_hash: str) -> tuple[dict, TypedColumns]:
        payload = build_prediction_payload(
            seq,
            prev_hash,
            result,
            company,
            quarter,
            epr,
            kind,
            rules_seq,
            rules_hash,
            universe_sha256,
            code_sha,
            run_id,
        )
        return payload, prediction_typed_columns(result)

    return build


def _gap_builder(
    refusal: BaselineRefusal,
    company: Company,
    kind: str,
    rules_seq: int,
    rules_hash: str,
    universe_sha256: str,
    code_sha: str,
    run_id: str,
) -> Builder:
    def build(seq: int, prev_hash: str) -> tuple[dict, TypedColumns]:
        payload = build_gap_payload(
            seq,
            prev_hash,
            refusal,
            company,
            kind,
            rules_seq,
            rules_hash,
            universe_sha256,
            code_sha,
            run_id,
        )
        return payload, gap_typed_columns(refusal)

    return build


def _guard(
    engine: sa.Engine, company: Company, quarter: FiscalQuarter, now: datetime
) -> str | None:
    """Why ``company`` may not be locked for ``quarter`` at ``now``, or ``None`` (D-14, D-27).

    All comparisons are on UTC instants:

    - the quarter must be live: ``period_start(Q) <= now < earliest_plausible_reveal`` (Open Q6);
    - no stored reveal event for (company, quarter) may have an early bound ``<= now``.

    A date-only event is stored at its late bound ``D 23:59:59 IST`` (D-24), so during day D the
    point-in-time reader at ``now`` does not return it yet, although its early bound
    ``D 00:00 IST`` has passed. The event check therefore reads through a reader anchored one
    day later, which sees every event whose late bound is within a day, and then compares the
    early bound with ``now`` itself. This reader is used only to refuse, never to build features.
    """
    epr = earliest_plausible_reveal(quarter, company.reveal_offset_days)
    if now < quarter.period_start_utc:
        return f"quarter_not_started: {quarter.label} starts {format_ts(quarter.period_start_utc)}"
    if now >= epr:
        return f"past_earliest_plausible_reveal: {format_ts(epr)}"
    horizon = PointInTimeReader(engine, now + timedelta(days=1), "backtest")
    for event in horizon.reveal_events(company.ticker, quarter.label):
        try:
            bound = event_early_bound(event.event_at, event.availability_basis)
        except ValueError:
            return f"invalid_reveal_event: {event.event_kind} cannot be interpreted"
        if bound <= now:
            return (
                f"reveal_event_known: {event.event_kind} early bound "
                f"{format_ts(bound.replace(microsecond=0))}"
            )
    return None


def _execute(
    settings: Settings, quarter: FiscalQuarter, kind: str, now: datetime, report: LockReport
) -> None:
    live = settings.calledit_env == "live"
    if live:
        try:
            require_live_write_context(settings)
        except LiveContextError as exc:
            raise LockRefused(str(exc)) from None
    try:
        universe: Universe = load_universe(settings.universe_path)
    except UniverseError as exc:
        raise LockRefused(f"universe config refused: {exc}") from None
    companies = sorted(universe.enabled(), key=lambda c: c.ticker)
    if not companies:
        raise LockRefused("no enabled company in the universe config")
    if live:
        problems = universe.unconfirmed()  # live locks hash ISINs and breaks permanently
        if problems:
            raise LockRefused(
                "live lock refused, unconfirmed universe values: " + "; ".join(problems)
            )
        if not run_db_check(settings).ok:
            raise LockRefused(
                "live database self-check failed; run: uv run nowcast db check", EXIT_ENV
            )
    elif _sqlite_store_missing(settings):
        raise LockRefused(
            "no local database to write to; run: uv run alembic upgrade head", EXIT_ENV
        )
    code_sha = _code_git_sha(settings)
    run_id = current_run_id()

    engine = make_engine(settings)
    try:
        with engine.connect() as conn:
            rules = latest_rules_record(conn)
        if rules is None:
            raise LockRefused("no rules record in the ledger; run: uv run nowcast rules first")
        try:
            stale = stale_fields(settings, rules, universe.universe_sha256)
        except RulesError as exc:
            raise LockRefused(str(exc)) from None
        if stale:
            raise LockRefused(
                f"{' and '.join(stale)} changed since rules record seq {rules.seq}; "
                "run: uv run nowcast rules (a new, visible rules record) before locking"
            )

        if now < rules.recorded_at:
            raise LockRefused(
                f"lock_before_rules: now {format_ts(now.replace(microsecond=0))} is earlier than "
                f"rules record seq {rules.seq} ({format_ts(rules.recorded_at.replace(microsecond=0))}); "
                "a lock cannot predate the rules it is bound to"
            )

        # Pass 1: the guard, per company, on UTC instants. Nothing is appended yet.
        lockable: list[Company] = []
        for company in companies:
            reason = _guard(engine, company, quarter, now)
            if reason is None:
                lockable.append(company)
                continue
            report.refused[company.ticker] = reason
            report.outcomes.append(CompanyOutcome(company.ticker, "refused", reason))
        if not lockable:
            raise LockRefused(
                "every enabled company was refused by the lock guard; nothing appended"
            )

        # Pass 2: baseline -> prediction or gap, one transaction per company.
        for company in lockable:
            ticker = company.ticker
            epr = earliest_plausible_reveal(quarter, company.reveal_offset_days)
            reader = PointInTimeReader(engine, now, "live")
            outcome = compute_baseline(company, quarter, reader, universe.breaks_for(ticker))
            if isinstance(outcome, BaselineResult):
                appended = append_record(
                    engine,
                    _prediction_builder(
                        outcome,
                        company,
                        quarter,
                        epr,
                        kind,
                        rules.seq,
                        rules.hash,
                        universe.universe_sha256,
                        code_sha,
                        run_id,
                    ),
                )
                report.appended.append(appended)
                report.outcomes.append(
                    CompanyOutcome(ticker, "locked", "", appended.seq, appended.hash)
                )
            else:
                appended = append_record(
                    engine,
                    _gap_builder(
                        outcome,
                        company,
                        kind,
                        rules.seq,
                        rules.hash,
                        universe.universe_sha256,
                        code_sha,
                        run_id,
                    ),
                )
                report.appended.append(appended)
                report.gaps.append(ticker)
                detail = f"{outcome.reason_code}: {', '.join(outcome.missing_quarters)}"
                report.outcomes.append(
                    CompanyOutcome(ticker, "gap", detail, appended.seq, appended.hash)
                )
    finally:
        engine.dispose()
        report.outcomes.sort(key=lambda o: o.ticker)

    if not report.appended:
        report.exit_code = EXIT_REFUSED
    elif report.refused or report.gaps:
        report.exit_code = EXIT_PARTIAL
    else:
        report.exit_code = EXIT_OK


def run_lock(
    settings: Settings, quarter: FiscalQuarter, kind: LockKind, *, now: datetime
) -> LockReport:
    """Lock every enabled company for ``quarter`` at ``now`` (the one and only lock instant)."""
    _check_now(now)
    if kind not in LOCK_KINDS:
        raise ValueError(f"kind must be one of {', '.join(LOCK_KINDS)}")
    report = LockReport(exit_code=EXIT_ENV)
    try:
        _execute(settings, quarter, kind, now, report)
    except LockRefused as exc:
        report.exit_code = exc.exit_code
        report.message = str(exc)
    except sa.exc.SQLAlchemyError as exc:
        report.exit_code = EXIT_ENV
        report.message = f"database failure ({type(exc).__name__}); no SQLite fallback (D-17)"
    except (ForkError, RecordError, CanonicalError) as exc:
        report.exit_code = EXIT_ENV
        report.message = f"ledger append failed ({type(exc).__name__}): {exc}"
    return report
