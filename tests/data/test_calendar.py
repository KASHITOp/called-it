"""PIT-04: the reveal calendar is derived from stored events read through the PIT gate.

Stored date-only events keep their late bound (D 23:59:59 IST, D-24); ``reveal_at`` is the
early bound (D 00:00 IST, D-27). All events here are SYNTHETIC test data.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from calledit_data.calendar.fiscal import FiscalQuarter
from calledit_data.calendar.reveal import RevealCalendar, reveal_calendar
from calledit_data.calendar.tz import date_eod_ist_utc
from calledit_data.pit.reader import PointInTimeReader
from calledit_data.store.writer import RevealEventIn, insert_reveal_events
from nowcaster.cli import app
from typer.testing import CliRunner

from tests.conftest import REPO_ROOT

URL = "https://example.invalid/synthetic-fixture"
INGESTED = datetime(2026, 10, 20, 0, 0, 0, tzinfo=UTC)
AS_OF = datetime(2026, 11, 28, 0, 0, 0, tzinfo=UTC)
Q2 = FiscalQuarter.parse("Q2FY27")
Q3 = FiscalQuarter.parse("Q3FY27")


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


def bu(day: date, quarter: str = "Q2FY27", ticker: str = "DMART") -> RevealEventIn:
    return RevealEventIn(
        ticker, quarter, "business_update", date_eod_ist_utc(day), "rule:date_eod_ist", URL
    )


def results(when: datetime, quarter: str = "Q2FY27", ticker: str = "DMART") -> RevealEventIn:
    return RevealEventIn(ticker, quarter, "results", when, "exchange_timestamp", URL)


def results_date_only(day: date, quarter: str = "Q2FY27") -> RevealEventIn:
    return RevealEventIn(
        "DMART", quarter, "results", date_eod_ist_utc(day), "rule:date_eod_ist", URL
    )


def store(engine: sa.Engine, events: list[RevealEventIn], ingested_at: datetime = INGESTED) -> None:
    with engine.begin() as conn:
        insert_reveal_events(conn, events, ingested_at)


def cal(engine: sa.Engine, quarter: FiscalQuarter = Q2, as_of: datetime = AS_OF) -> RevealCalendar:
    reader = PointInTimeReader(engine, as_of, "live")
    return reveal_calendar(reader, "DMART", quarter, 1)


def test_confirmed_quarter_uses_the_early_bound(migrated_sqlite: sa.Engine) -> None:
    store(migrated_sqlite, [bu(date(2026, 10, 3)), results(_ts("2026-10-11T12:00:00Z"))])
    c = cal(migrated_sqlite)
    assert c.status == "confirmed"
    assert c.business_update_at == _ts("2026-10-03T18:29:59Z")  # as stored (late bound)
    assert c.results_at == _ts("2026-10-11T12:00:00Z")
    assert c.reveal_at == _ts("2026-10-02T18:30:00Z")  # 2026-10-03 00:00 IST (D-27)
    assert c.earliest_plausible_reveal == _ts("2026-09-30T18:30:00Z")


def test_event_after_as_of_is_not_visible(migrated_sqlite: sa.Engine) -> None:
    early_ingest = _ts("2026-10-01T00:00:00Z")
    events = [bu(date(2026, 10, 3)), results(_ts("2026-10-11T12:00:00Z"))]
    store(migrated_sqlite, events, early_ingest)
    mid = cal(migrated_sqlite, as_of=_ts("2026-10-05T00:00:00Z"))
    assert mid.status == "confirmed"
    assert mid.results_at is None
    assert mid.business_update_at == _ts("2026-10-03T18:29:59Z")
    # A date-only event is known only once its late bound has passed (strict <).
    early = cal(migrated_sqlite, as_of=_ts("2026-10-03T18:29:59Z"))
    assert early.status == "expected"
    assert early.reveal_at is None
    assert early.business_update_at is None


def test_event_ingested_after_as_of_is_not_visible_in_live_mode(
    migrated_sqlite: sa.Engine,
) -> None:
    store(migrated_sqlite, [results(_ts("2026-10-11T12:00:00Z"))])
    assert cal(migrated_sqlite, as_of=_ts("2026-10-19T00:00:00Z")).status == "expected"
    assert cal(migrated_sqlite, as_of=INGESTED).status == "confirmed"


def test_quarter_without_events_is_expected(migrated_sqlite: sa.Engine) -> None:
    store(migrated_sqlite, [bu(date(2026, 10, 3)), results(_ts("2026-10-11T12:00:00Z"))])
    c = cal(migrated_sqlite, Q3)
    assert c.status == "expected"
    assert c.reveal_at is None
    assert c.business_update_at is None
    assert c.results_at is None
    assert c.earliest_plausible_reveal == _ts("2026-12-31T18:30:00Z")


def test_same_ist_date_business_update_and_results(migrated_sqlite: sa.Engine) -> None:
    store(migrated_sqlite, [bu(date(2026, 10, 11)), results(_ts("2026-10-11T12:00:00Z"))])
    c = cal(migrated_sqlite)
    # The date-only business update's early bound (00:00 IST) precedes the exact results time.
    assert c.reveal_at == _ts("2026-10-10T18:30:00Z")
    assert c.results_at == _ts("2026-10-11T12:00:00Z")


def test_exact_results_before_date_only_business_update(migrated_sqlite: sa.Engine) -> None:
    store(migrated_sqlite, [results(_ts("2026-10-02T12:00:00Z")), bu(date(2026, 10, 3))])
    assert cal(migrated_sqlite).reveal_at == _ts("2026-10-02T12:00:00Z")


def test_date_only_results_reveal_at_is_start_of_day(migrated_sqlite: sa.Engine) -> None:
    store(migrated_sqlite, [results_date_only(date(2026, 10, 11))])
    c = cal(migrated_sqlite)
    assert c.results_at == _ts("2026-10-11T18:29:59Z")
    assert c.reveal_at == _ts("2026-10-10T18:30:00Z")


def test_other_company_and_quarter_events_are_ignored(migrated_sqlite: sa.Engine) -> None:
    store(
        migrated_sqlite,
        [
            results(_ts("2026-10-11T12:00:00Z"), ticker="TITAN"),
            results(_ts("2026-07-11T12:00:00Z"), quarter="Q1FY27"),
        ],
    )
    assert cal(migrated_sqlite).status == "expected"


def test_reveal_calendar_rejects_bad_arguments(migrated_sqlite: sa.Engine) -> None:
    reader = PointInTimeReader(migrated_sqlite, AS_OF, "live")
    with pytest.raises(TypeError):
        reveal_calendar(reader, "DMART", "Q2FY27", 1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        reveal_calendar(reader, "DMART", Q2, -1)


# --- the CLI ------------------------------------------------------------------------------


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("CALLEDIT_UNIVERSE_PATH", str(REPO_ROOT / "config" / "universe.toml"))
    return CliRunner()


def _block(output: str, ticker: str) -> str:
    return output.split(f"company {ticker}\n", 1)[1].split("company ", 1)[0]


def test_cli_calendar_reads_stored_events(migrated_sqlite: sa.Engine, runner: CliRunner) -> None:
    fixture = REPO_ROOT / "tests" / "fixtures" / "seed_fixture_SYNTHETIC.csv"
    loaded = runner.invoke(app, ["seed", "load", "--csv", str(fixture)])
    assert loaded.exit_code == 0, loaded.output
    result = runner.invoke(app, ["calendar", "--quarter", "Q2FY27"])
    assert result.exit_code == 0, result.output
    dmart = _block(result.output, "DMART")
    assert "business_update_at: 2026-10-03T18:29:59Z" in dmart
    assert "results_at: 2026-10-11T12:00:00Z" in dmart
    assert "reveal_at: 2026-10-02T18:30:00Z" in dmart
    assert "status: confirmed" in dmart
    eternal = _block(result.output, "ETERNAL")
    assert "business_update_at: none" in eternal
    assert "status: confirmed" in eternal
    q3 = runner.invoke(app, ["calendar", "--quarter", "Q3FY27"])
    assert q3.exit_code == 0, q3.output
    assert "status: expected" in _block(q3.output, "DMART")
    assert "2026-12-31T18:30:00Z" in q3.output
    assert "no reveal events stored" not in q3.output


def test_cli_calendar_without_a_store(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(app, ["calendar", "--quarter", "Q3FY27"])
    assert result.exit_code == 0, result.output
    assert "no reveal events stored" in result.output
    assert "status: expected" in result.output
    assert "2026-12-31T18:30:00Z" in result.output
    assert not (Path.cwd() / "data" / "local.db").exists()  # the calendar never creates a DB
