"""The lock: baseline per enabled company -> chained prediction or gap record (LEDG-05).

``run_lock`` is the only writer of prediction and gap records. It has no parameter, option,
environment variable or config key that sets the lock time: the caller passes ``now`` (the CLI
reads the clock exactly once, in ``nowcaster.clock``) and that single instant is both ``as_of``
and ``locked_at`` for every company in the run.

Per company, in sorted ticker order, each in its own transaction:

- a ``BaselineResult`` is appended as a ``prediction`` record (D-12, interval ``none``);
- a ``BaselineRefusal`` is appended as a ``gap`` record, never imputed (D-08).

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
from calledit_data.calendar.reveal import earliest_plausible_reveal
from calledit_data.db.engine import make_engine
from calledit_data.db.settings import Settings
from calledit_data.pit.reader import PointInTimeReader
from sqlalchemy.engine import make_url

from nowcaster.baseline import BaselineRefusal, BaselineResult, compute_baseline
from nowcaster.exit_codes import EXIT_ENV, EXIT_OK, EXIT_PARTIAL, EXIT_REFUSED
from nowcaster.ledger.canonical import CanonicalError
from nowcaster.ledger.chain import AppendedRecord, Builder, ForkError, RecordError, append_record
from nowcaster.ledger.records import (
    LOCK_KINDS,
    TypedColumns,
    build_gap_payload,
    build_prediction_payload,
    gap_typed_columns,
    prediction_typed_columns,
)
from nowcaster.rules import current_run_id, latest_rules_record
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


def _execute(
    settings: Settings, quarter: FiscalQuarter, kind: str, now: datetime, report: LockReport
) -> None:
    try:
        universe: Universe = load_universe(settings.universe_path)
    except UniverseError as exc:
        raise LockRefused(f"universe config refused: {exc}") from None
    companies = sorted(universe.enabled(), key=lambda c: c.ticker)
    if not companies:
        raise LockRefused("no enabled company in the universe config")
    if _sqlite_store_missing(settings):
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
        for company in companies:
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
