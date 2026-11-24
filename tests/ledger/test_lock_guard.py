"""The lock guard (LEDG-05, D-14, D-27): deadlines, the live-quarter rule, reveal events, gaps,
exit codes, the absence of any time override, and the live context.

Everything runs on a temp SQLite store with the SYNTHETIC seed fixture. Live-context tests build
a live ``Settings`` pointing at an unreachable local port: they can never reach a real database
(the guard refuses before any connection, or the connection fails and the exit is 5).
"""

from __future__ import annotations

import ast
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
import typer
from calledit_data.calendar.fiscal import FiscalQuarter
from calledit_data.db import check as check_module
from calledit_data.db.check import DbCheckReport
from calledit_data.db.settings import Settings
from calledit_data.store.writer import RevealEventIn
from nowcaster.cli import app
from nowcaster.exit_codes import EXIT_ENV, EXIT_OK, EXIT_PARTIAL, EXIT_REFUSED
from nowcaster.lock import run_lock

from nowcaster import lock as lock_module
from tests.leakage.store_helpers import add_events
from tests.ledger.lock_helpers import FIXTURE, LOCK_TIME, RULES_TIME, SEED_TIME, LockEnv

DMART_EPR = datetime(2026, 12, 31, 18, 30, 0, tzinfo=UTC)  # 2027-01-01 00:00 IST
TITAN_EPR = datetime(2027, 1, 1, 18, 30, 0, tzinfo=UTC)  # 2027-01-02 00:00 IST
ETERNAL_EPR = datetime(2027, 1, 6, 18, 30, 0, tzinfo=UTC)  # 2027-01-07 00:00 IST
NOT_LIVE_HOST_URL = "postgresql://u:p@127.0.0.1:1/postgres"


def _ready(lock_env: LockEnv) -> LockEnv:
    lock_env.load_seed()
    assert lock_env.rules().exit_code == 0
    assert lock_env.count() == 1
    return lock_env


def _tickers(lock_env: LockEnv) -> list[str]:
    return [r["payload"]["ticker"] for r in lock_env.rows()[1:]]


# --- deadlines and the live-quarter rule --------------------------------------------------


def test_q2fy27_refused_and_nothing_appended(lock_env: LockEnv) -> None:
    _ready(lock_env)
    result = lock_env.predict("Q2FY27")
    assert result.exit_code == EXIT_REFUSED, result.output
    assert result.output.count("REFUSED past_earliest_plausible_reveal") == 3
    assert lock_env.count() == 1  # only the rules record


def test_a_lock_earlier_than_the_rules_record_is_refused(lock_env: LockEnv) -> None:
    _ready(lock_env)  # the rules record is created at RULES_TIME
    result = lock_env.predict("Q3FY27", RULES_TIME - timedelta(minutes=1))
    assert result.exit_code == EXIT_REFUSED, result.output
    assert "lock_before_rules" in result.output
    assert lock_env.count() == 1  # only the rules record


def test_a_repeated_lock_appends_later_records_and_never_edits_earlier_ones(
    lock_env: LockEnv,
) -> None:
    _ready(lock_env)
    first = lock_env.predict("Q3FY27", LOCK_TIME)
    assert first.exit_code in (EXIT_OK, EXIT_PARTIAL), first.output
    before = [(r["seq"], r["hash"], r["payload_canonical"]) for r in lock_env.rows()]
    second = lock_env.predict("Q3FY27", LOCK_TIME + timedelta(days=1))
    assert second.exit_code == first.exit_code, second.output
    after = lock_env.rows()
    assert len(after) == 2 * len(before) - 1  # the rules record is not repeated
    assert [(r["seq"], r["hash"], r["payload_canonical"]) for r in after[: len(before)]] == before
    assert [r["seq"] for r in after] == list(range(len(after)))


def test_quarter_that_has_not_started_is_refused(lock_env: LockEnv) -> None:
    _ready(lock_env)
    result = lock_env.predict("Q4FY27")
    assert result.exit_code == EXIT_REFUSED, result.output
    assert result.output.count("REFUSED quarter_not_started") == 3
    assert lock_env.count() == 1


def test_the_live_quarter_starts_at_00_00_ist_on_its_first_day(lock_env: LockEnv) -> None:
    lock_env.load_seed()  # ingested on 28 Nov, i.e. after the instants probed below
    # The rules record must predate the probed instants, or lock_before_rules fires first.
    assert lock_env.rules(datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)).exit_code == 0
    start = datetime(2026, 9, 30, 18, 30, 0, tzinfo=UTC)  # 2026-10-01 00:00 IST
    before = lock_env.predict("Q3FY27", start - timedelta(seconds=1))
    assert before.exit_code == EXIT_REFUSED, before.output
    assert before.output.count("REFUSED quarter_not_started") == 3
    assert lock_env.count() == 1
    # At the first instant the guard passes. The seed was ingested later (live mode hides it),
    # so every company is a visible gap rather than a refusal.
    at_start = lock_env.predict("Q3FY27", start)
    assert at_start.exit_code == EXIT_PARTIAL, at_start.output
    assert at_start.output.count(" GAP seq=") == 3


def test_deadline_is_exclusive_at_earliest_plausible_reveal(lock_env: LockEnv) -> None:
    _ready(lock_env)
    just_before = DMART_EPR - timedelta(seconds=1)  # 2026-12-31T18:29:59Z
    ok = lock_env.predict("Q3FY27", just_before)
    assert ok.exit_code == EXIT_OK, ok.output
    assert _tickers(lock_env) == ["DMART", "ETERNAL", "TITAN"]
    assert lock_env.rows()[1]["payload"]["locked_at"] == "2026-12-31T18:29:59Z"


def test_dmart_is_refused_at_its_deadline_while_the_others_still_lock(lock_env: LockEnv) -> None:
    _ready(lock_env)
    result = lock_env.predict("Q3FY27", DMART_EPR)  # 2026-12-31T18:30:00Z
    assert result.exit_code == EXIT_PARTIAL, result.output
    assert "DMART REFUSED past_earliest_plausible_reveal" in result.output
    assert _tickers(lock_env) == ["ETERNAL", "TITAN"]
    assert lock_env.count() == 3


def test_every_company_past_its_deadline_is_refused_with_exit_4(lock_env: LockEnv) -> None:
    _ready(lock_env)
    result = lock_env.predict("Q3FY27", ETERNAL_EPR)  # 2027-01-06T18:30:00Z
    assert result.exit_code == EXIT_REFUSED, result.output
    assert result.output.count("REFUSED past_earliest_plausible_reveal") == 3
    assert lock_env.count() == 1


def test_each_company_has_its_own_deadline(lock_env: LockEnv) -> None:
    _ready(lock_env)
    result = lock_env.predict("Q3FY27", TITAN_EPR)  # DMART and TITAN past, ETERNAL still open
    assert result.exit_code == EXIT_PARTIAL, result.output
    assert _tickers(lock_env) == ["ETERNAL"]


# --- reveal events (D-27) -----------------------------------------------------------------


def _event(kind: str, at: datetime, basis: str = "exchange_timestamp") -> RevealEventIn:
    return RevealEventIn(
        ticker="DMART",
        fiscal_quarter="Q3FY27",
        event_kind=kind,
        event_at=at,
        availability_basis=basis,
        source_ref="https://example.invalid/synthetic-fixture",
    )


def test_a_known_reveal_event_refuses_only_its_company(lock_env: LockEnv) -> None:
    _ready(lock_env)
    add_events(
        lock_env.engine,
        [_event("business_update", datetime(2026, 11, 28, 2, 0, tzinfo=UTC))],
        SEED_TIME,
    )
    result = lock_env.predict()
    assert result.exit_code == EXIT_PARTIAL, result.output
    assert "DMART REFUSED reveal_event_known" in result.output
    assert _tickers(lock_env) == ["ETERNAL", "TITAN"]


def test_a_same_day_date_only_event_refuses_by_its_early_bound(lock_env: LockEnv) -> None:
    """D-27: a date-only event stored as D 23:59:59 IST counts from D 00:00 IST. At 09:30 IST on
    D the stored late bound is still in the future, so the point-in-time reader hides the
    event; the guard must still refuse."""
    _ready(lock_env)
    late_bound = datetime(2026, 11, 28, 18, 29, 59, tzinfo=UTC)  # 2026-11-28 23:59:59 IST
    assert late_bound > LOCK_TIME
    add_events(lock_env.engine, [_event("results", late_bound, "rule:date_eod_ist")], SEED_TIME)
    result = lock_env.predict()  # 2026-11-28T04:00:00Z = 09:30 IST on the same day
    assert result.exit_code == EXIT_PARTIAL, result.output
    assert "DMART REFUSED reveal_event_known" in result.output
    assert _tickers(lock_env) == ["ETERNAL", "TITAN"]


def test_a_reveal_event_that_is_still_in_the_future_does_not_refuse(lock_env: LockEnv) -> None:
    _ready(lock_env)
    add_events(
        lock_env.engine, [_event("results", datetime(2026, 11, 28, 20, 0, tzinfo=UTC))], SEED_TIME
    )
    result = lock_env.predict()
    assert result.exit_code == EXIT_OK, result.output
    assert _tickers(lock_env) == ["DMART", "ETERNAL", "TITAN"]


# --- gaps (D-08) --------------------------------------------------------------------------


def test_a_removed_quarter_gaps_one_company_and_locks_the_rest(
    lock_env: LockEnv, tmp_path: Path
) -> None:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [ln for ln in lines if not (ln.startswith("DMART,") and ",Q4FY25," in ln)]
    trimmed = tmp_path / "seed_trimmed_SYNTHETIC.csv"
    trimmed.write_text("".join(kept), encoding="utf-8", newline="")
    lock_env.load_seed(trimmed)
    assert lock_env.rules().exit_code == 0
    result = lock_env.predict()
    assert result.exit_code == EXIT_PARTIAL, result.output
    rows = lock_env.rows()[1:]
    assert [r["record_kind"] for r in rows] == ["gap", "prediction", "prediction"]
    assert rows[0]["payload"]["reason_code"] == "missing_seed_quarter"
    assert rows[0]["payload"]["missing_quarters"] == "Q4FY25"


def test_every_company_gapping_appends_three_gap_records_and_exits_3(lock_env: LockEnv) -> None:
    assert lock_env.rules().exit_code == 0  # no seed loaded: nothing is knowable
    result = lock_env.predict()
    assert result.exit_code == EXIT_PARTIAL, result.output
    rows = lock_env.rows()[1:]
    assert [r["record_kind"] for r in rows] == ["gap", "gap", "gap"]
    assert {r["payload"]["reason_code"] for r in rows} == {"missing_seed_quarter"}
    assert result.output.count(" GAP seq=") == 3


# --- no way to choose the lock time -------------------------------------------------------

_TIME_NAME = re.compile(r"as.?of|locked.?at|clock|frozen")
_TIME_WORD = re.compile(r"now|date|time|at")


def test_predict_has_no_time_override_option() -> None:
    command = typer.main.get_command(app).commands["predict"]  # type: ignore[attr-defined]
    names = {p.name for p in command.params if p.name}
    opts = {o.lstrip("-") for p in command.params for o in getattr(p, "opts", [])}
    assert names == {"quarter", "kind"}
    assert opts == {"quarter", "kind"}
    for name in names | opts:
        assert _TIME_WORD.fullmatch(name) is None, name
        assert _TIME_NAME.search(name) is None, name


def test_no_setting_or_environment_variable_selects_the_lock_time() -> None:
    for name in Settings.model_fields:
        assert _TIME_NAME.search(name) is None, name
        assert name not in {"now", "date", "time", "at"}, name


_ALLOWED_ENV = {"GITHUB_ACTIONS", "GITHUB_REF", "GITHUB_SHA", "GITHUB_RUN_ID"}


def _env_reads(source: str) -> list[str | None]:
    """Every environment read in ``source``: the literal name, or None when it is dynamic."""
    found: list[str | None] = []

    def literal(node: ast.expr) -> str | None:
        return (
            node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None
        )

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            target = ast.unparse(node.func.value)
            if (target == "os.environ" and node.func.attr in {"get", "pop", "setdefault"}) or (
                target == "os" and node.func.attr in {"getenv", "putenv"}
            ):
                found.append(literal(node.args[0]) if node.args else None)
        elif isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ":
            found.append(literal(node.slice))
        elif isinstance(node, ast.Attribute) and ast.unparse(node) == "os.environ":
            pass
    return found


def test_lock_reads_no_environment_variable_but_the_github_ones() -> None:
    source = Path(lock_module.__file__).read_text(encoding="utf-8")
    reads = _env_reads(source)
    assert reads, "the scanner found no environment read in lock.py; it is broken"
    assert set(reads) <= _ALLOWED_ENV, reads


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('import os\nx = os.environ.get("GITHUB_SHA")\n', ["GITHUB_SHA"]),
        ('import os\nx = os.environ["LOCK_AT"]\n', ["LOCK_AT"]),
        ('import os\nx = os.getenv("NOW")\n', ["NOW"]),
        ("import os\nx = os.environ.get(name)\n", [None]),
    ],
)
def test_env_scanner_detects_planted_reads(source: str, expected: list[str | None]) -> None:
    assert _env_reads(source) == expected


# --- environment failures (D-17) ----------------------------------------------------------


def _settings(lock_env: LockEnv, **overrides: object) -> Settings:
    return Settings(_env_file=None, universe_path=lock_env.universe, **overrides)  # type: ignore[arg-type]


def test_a_missing_local_database_is_exit_5_and_is_not_created(
    lock_env: LockEnv, tmp_path: Path
) -> None:
    absent = tmp_path / "absent.db"
    settings = _settings(
        lock_env, database_url=f"sqlite:///{absent.as_posix()}", calledit_env="test"
    )
    report = run_lock(settings, FiscalQuarter.parse("Q3FY27"), "dispatch", now=LOCK_TIME)
    assert report.exit_code == EXIT_ENV
    assert not absent.exists()
    assert report.appended == []


def test_an_unmigrated_database_is_exit_5_with_no_fallback(
    lock_env: LockEnv, tmp_path: Path
) -> None:
    bare = tmp_path / "bare.db"
    sqlite3.connect(bare).close()
    settings = _settings(lock_env, database_url=f"sqlite:///{bare.as_posix()}", calledit_env="test")
    report = run_lock(settings, FiscalQuarter.parse("Q3FY27"), "dispatch", now=LOCK_TIME)
    assert report.exit_code == EXIT_ENV
    assert "OperationalError" in report.message
    assert report.appended == []


# --- live context -------------------------------------------------------------------------


def _live_universe(lock_env: LockEnv, *, isins: bool, breaks: bool, disable: str = "") -> Path:
    text = lock_env.universe.read_text(encoding="utf-8")
    if isins:
        text = re.sub(r"(?m)^isin_confirmed = false$", "isin_confirmed = true", text)
    else:
        # the shipped ISINs are all confirmed now, so un-confirm one explicitly
        text = text.replace(
            'isin = "INE758T01015"\nisin_confirmed = true',
            'isin = "INE758T01015"\nisin_confirmed = false',
            1,
        )
        assert 'isin = "INE758T01015"\nisin_confirmed = false' in text
    if breaks:
        text = re.sub(r"(?m)^confirmed = false$", "confirmed = true", text)
    else:
        # the shipped Eternal break is confirmed now, so un-confirm it explicitly
        anchor = 'id = "eternal-blinkit-inventory"'
        head, tail = text.split(anchor, 1)
        assert "confirmed = true" in tail
        text = head + anchor + tail.replace("confirmed = true", "confirmed = false", 1)
    if disable:
        pattern = rf'(ticker = "{disable}"(?:.|\n)*?)enabled = true'
        text = re.sub(pattern, r"\1enabled = false", text, count=1)
    path = lock_env.universe.with_name(f"live-{isins}-{breaks}-{disable or 'none'}.toml")
    path.write_bytes(text.encode("utf-8"))
    return path


def _live_settings(universe: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=NOT_LIVE_HOST_URL,
        calledit_env="live",
        universe_path=universe,
    )


def _run_live(settings: Settings) -> lock_module.LockReport:
    return run_lock(settings, FiscalQuarter.parse("Q3FY27"), "dispatch", now=LOCK_TIME)


def test_live_requires_actions_main_and_confirmed_universe(
    lock_env: LockEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    confirmed = _live_universe(lock_env, isins=True, breaks=True)
    unconfirmed_isin = _live_universe(lock_env, isins=False, breaks=True)
    unconfirmed_break = _live_universe(lock_env, isins=True, breaks=False)

    # 1. not inside GitHub Actions
    report = _run_live(_live_settings(confirmed))
    assert report.exit_code == EXIT_REFUSED and "GitHub Actions" in report.message

    # 2. inside Actions but not on main
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feature")
    report = _run_live(_live_settings(confirmed))
    assert report.exit_code == EXIT_REFUSED and "refs/heads/main" in report.message

    # 3. on main, but an enabled company's ISIN is unconfirmed
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    report = _run_live(_live_settings(unconfirmed_isin))
    assert report.exit_code == EXIT_REFUSED and "isin_confirmed" in report.message

    # 4. on main, ISINs confirmed, but an applicable break is unconfirmed
    report = _run_live(_live_settings(unconfirmed_break))
    assert report.exit_code == EXIT_REFUSED and "eternal-blinkit-inventory" in report.message
    assert report.appended == []


def test_live_ignores_unconfirmed_values_of_disabled_companies(
    lock_env: LockEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    seen: list[str] = []

    def failing_check(settings: Settings, **_: object) -> DbCheckReport:
        seen.append("db_check")
        return DbCheckReport(lines=["result: FAIL"], ok=False)

    monkeypatch.setattr(lock_module, "run_db_check", failing_check)
    universe = _live_universe(lock_env, isins=True, breaks=False, disable="ETERNAL")
    report = _run_live(_live_settings(universe))
    # past the confirmation check (ETERNAL, the only unconfirmed break's company, is disabled),
    # so the run reached the live database self-check, which failed: environment, not refusal.
    assert seen == ["db_check"]
    assert report.exit_code == EXIT_ENV
    assert "self-check" in report.message
    assert report.appended == []


def test_live_database_self_check_failure_is_an_environment_error(
    lock_env: LockEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setattr(
        lock_module, "run_db_check", lambda settings, **_: DbCheckReport(lines=[], ok=False)
    )
    report = _run_live(_live_settings(_live_universe(lock_env, isins=True, breaks=True)))
    assert report.exit_code == EXIT_ENV
    assert report.appended == []


def test_live_unreachable_database_is_exit_5_and_never_falls_back_to_sqlite(
    lock_env: LockEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real ``run_db_check`` runs; its engine is swapped for one that cannot connect, so the
    test never opens a network connection (a refused TCP connect takes minutes on Windows)."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    unreachable = sa.create_engine(
        "sqlite:///" + (lock_env.universe.parent / "no" / "x.db").as_posix()
    )
    monkeypatch.setattr(check_module, "make_engine", lambda settings: unreachable)
    settings = _live_settings(_live_universe(lock_env, isins=True, breaks=True))
    assert settings.backend == "postgresql"
    report = _run_live(settings)
    assert report.exit_code == EXIT_ENV
    assert "self-check" in report.message
    assert report.appended == []
    assert lock_env.count() == 0  # the local SQLite store was never written
