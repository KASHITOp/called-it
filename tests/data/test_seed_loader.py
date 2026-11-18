"""DATA-01 / D-25: whole-file seed validation. Every error is listed and nothing is inserted.

Every CSV here is SYNTHETIC test data (https://example.invalid or clearly fake values).
"""

from __future__ import annotations

import csv
import io
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from calledit_data.db.schema import observations, reveal_events
from calledit_data.db.settings import LiveContextError, Settings, get_settings
from calledit_data.seed.loader import (
    CANONICAL_SEED_PATH,
    COLUMNS,
    SeedCompanyRules,
    SeedError,
    load_seed,
    parse_seed_csv,
)
from nowcaster.cli import app
from typer.testing import CliRunner

from tests.conftest import REPO_ROOT

NOW = datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "seed_fixture_SYNTHETIC.csv"
CANONICAL = REPO_ROOT / "data" / "seed" / "quarterly_revenue.csv"
RULES = {
    "DMART": SeedCompanyRules("INE192R01011", True),
    "ETERNAL": SeedCompanyRules("INE758T01015", False),
    "TITAN": SeedCompanyRules("INE280A01028", True),
}
URL = "https://example.invalid/synthetic-fixture"
HEADER = ",".join(COLUMNS)


def dmart(**changes: str) -> dict[str, str]:
    row = {
        "ticker": "DMART",
        "isin": "INE192R01011",
        "fiscal_quarter": "Q2FY27",
        "period_end": "2026-09-30",
        "basis": "consolidated",
        "line_item": "Revenue from operations",
        "unit_in_filing": "crore",
        "revenue_cr": "10700.00",
        "results_date": "2026-10-11T17:30+05:30",
        "results_at_basis": "exchange_timestamp",
        "business_update_at": "2026-10-03",
        "business_update_basis": "rule:date_eod_ist",
        "business_update_url": URL,
        "source_url": URL,
        "page_ref": "p8",
        "vintage": "first_reported",
        "verified": "Y",
        "notes": "SYNTHETIC TEST FIXTURE - not real data",
    }
    row.update(changes)
    return row


def eternal(**changes: str) -> dict[str, str]:
    base = dmart(
        ticker="ETERNAL",
        isin="INE758T01015",
        business_update_at="",
        business_update_basis="",
        business_update_url="",
    )
    base.update(changes)
    return base


def quarter(label: str, end: str, results: str) -> dict[str, str]:
    return {"fiscal_quarter": label, "period_end": end, "results_date": results}


Q1FY27 = quarter("Q1FY27", "2026-06-30", "2026-07-11T17:30+05:30") | {
    "business_update_at": "2026-07-03"
}
Q4FY26 = quarter("Q4FY26", "2026-03-31", "2026-05-11T17:30+05:30") | {
    "business_update_at": "2026-04-03"
}
Q3FY26 = quarter("Q3FY26", "2025-12-31", "2026-01-11T17:30+05:30") | {
    "business_update_at": "2026-01-03"
}
Q2FY26 = quarter("Q2FY26", "2025-09-30", "2025-10-11T17:30+05:30") | {
    "business_update_at": "2025-10-03"
}


def write_csv(path: Path, rows: list[dict[str, str]], *, newline: str = "\n") -> Path:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(COLUMNS), lineterminator=newline)
    writer.writeheader()
    writer.writerows(rows)
    path.write_bytes(buffer.getvalue().encode("utf-8"))
    return path


def parse(path: Path, *, require_verified: bool = False, **kwargs: object):
    return parse_seed_csv(path, RULES, require_verified=require_verified, now=NOW, **kwargs)


def errors_of(path: Path, **kwargs: object) -> list[tuple[int, str]]:
    return [(e.row, e.column) for e in parse(path, **kwargs).errors]


def settings_for(env: str, db: Path | None = None) -> Settings:
    if env == "live":
        return Settings(
            _env_file=None,
            database_url="postgresql+psycopg://user:secret@localhost:5432/postgres",
            calledit_env="live",
        )
    url = f"sqlite:///{(db or Path('unused.db')).as_posix()}"
    return Settings(_env_file=None, database_url=url, calledit_env=env)


def _count(engine: sa.Engine, table: sa.Table) -> int:
    with engine.connect() as conn:
        return conn.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()


# --- D-25: whole file, every error ------------------------------------------------------


def test_bad_file_lists_every_error_and_inserts_nothing(
    migrated_sqlite: sa.Engine, tmp_path: Path
) -> None:
    path = write_csv(
        tmp_path / "bad.csv",
        [
            dmart(source_url="http://example.invalid/synthetic-fixture"),
            dmart(**(Q1FY27 | {"period_end": "2026-06-29"})),
            dmart(**Q4FY26, revenue_cr="12,345.6"),
            dmart(**(Q3FY26 | {"results_date": "2025-12-30T17:30+05:30"})),
            dmart(**(Q2FY26 | {"results_date": "2025-10-11"})),
            dmart(ticker="RELIANCE", isin="INE002A01018"),
        ],
    )
    report = load_seed(migrated_sqlite, path, RULES, get_settings(), now=NOW, dry_run=False)
    found = [(e.row, e.column) for e in report.errors]
    assert found == [
        (2, "source_url"),
        (3, "period_end"),
        (4, "revenue_cr"),
        (5, "results_date"),
        (6, "results_date"),
        (7, "ticker"),
    ], [str(e) for e in report.errors]
    assert report.observations_inserted == 0
    assert report.rows_seen == 6
    assert _count(migrated_sqlite, observations) == 0
    assert _count(migrated_sqlite, reveal_events) == 0


def test_good_file_parses_cleanly(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "good.csv", [dmart(), dmart(**Q1FY27), eternal()])
    result = parse(path)
    assert result.errors == []
    assert len(result.rows) == 3
    assert result.rows[0].observation.available_at == datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
    bu = next(e for e in result.rows[0].events if e.event_kind == "business_update")
    assert bu.event_at == datetime(2026, 10, 3, 18, 29, 59, tzinfo=UTC)
    assert result.rows[0].observation.source_ref == URL + "#p8"
    assert [e.event_kind for e in result.rows[2].events] == ["results"]


def test_fixture_parses_cleanly_in_dev() -> None:
    result = parse(FIXTURE)
    assert result.errors == []
    assert result.rows_seen == 24


@pytest.mark.parametrize(
    ("changes", "column"),
    [
        ({"isin": "INE002A01018"}, "isin"),
        ({"verified": "y"}, "verified"),
        ({"verified": ""}, "verified"),
        ({"basis": "standalone"}, "basis"),
        ({"line_item": "Total income"}, "line_item"),
        ({"unit_in_filing": "rupees"}, "unit_in_filing"),
        ({"revenue_cr": "10700"}, "revenue_cr"),
        ({"revenue_cr": "0.00"}, "revenue_cr"),
        ({"revenue_cr": "-10.00"}, "revenue_cr"),
        ({"fiscal_quarter": "q2fy27"}, "fiscal_quarter"),
        ({"fiscal_quarter": "Q5FY27"}, "fiscal_quarter"),
        ({"period_end": "2026-09-31"}, "period_end"),
        ({"results_date": "2026-11-19T10:00+05:30"}, "results_date"),  # after now
        ({"results_date": "2026-10-11T17:30Z"}, "results_date"),
        ({"results_at_basis": "guess"}, "results_at_basis"),
        (
            {
                "results_date": "2026-10-11",
                "results_at_basis": "rule:date_eod_ist",
                "business_update_at": "2026-10-12",
            },
            "business_update_at",
        ),  # after results
        ({"business_update_at": "2026-09-30"}, "business_update_at"),  # not after period end
        ({"business_update_basis": ""}, "business_update_basis"),
        ({"business_update_url": "http://example.invalid/x"}, "business_update_url"),
        ({"business_update_at": ""}, "business_update_at"),  # DMART first_reported needs it
        ({"source_url": ""}, "source_url"),
        ({"source_url": "https://"}, "source_url"),
        ({"source_url": "https://example.invalid/a#frag"}, "source_url"),
        ({"source_url": 'https://example.invalid/a"b'}, "source_url"),
        ({"source_url": "https://example.invalid/a\\b"}, "source_url"),
        ({"source_url": "https://example.invalid/café"}, "source_url"),
        ({"page_ref": 'p "8"'}, "page_ref"),
        ({"page_ref": "p\\8"}, "page_ref"),
        ({"page_ref": "p§8"}, "page_ref"),
        ({"vintage": "final"}, "vintage"),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_single_fault_is_one_error(tmp_path: Path, changes: dict, column: str) -> None:
    path = write_csv(tmp_path / "one.csv", [dmart(**changes)])
    assert errors_of(path) == [(2, column)], [str(e) for e in parse(path).errors]


def test_eternal_with_business_update_is_an_error(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "e.csv",
        [eternal(business_update_at="2026-10-03", business_update_basis="rule:date_eod_ist")],
    )
    assert errors_of(path) == [(2, "business_update_at")]


def test_business_update_fields_without_a_date_are_an_error(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "e.csv", [eternal(business_update_basis="rule:date_eod_ist")])
    assert errors_of(path) == [(2, "business_update_basis")]


def test_duplicate_row_is_an_error(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "dup.csv", [dmart(), dmart(page_ref="p9")])
    assert (3, "results_date") in errors_of(path)


def test_second_first_reported_for_a_quarter_is_an_error(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "two.csv",
        [dmart(), dmart(results_date="2026-10-12T17:30+05:30", revenue_cr="10701.00")],
    )
    assert errors_of(path) == [(3, "vintage")]


def test_restated_row_needs_a_first_reported_row_before_it(tmp_path: Path) -> None:
    restated = dmart(
        vintage="restated",
        revenue_cr="10750.00",
        results_date="2026-11-10T17:30+05:30",
        business_update_at="",
        business_update_basis="",
        business_update_url="",
    )
    alone = write_csv(tmp_path / "alone.csv", [restated])
    assert errors_of(alone) == [(2, "vintage")]
    early = write_csv(
        tmp_path / "early.csv", [dmart(), restated | {"results_date": "2026-10-10T17:30+05:30"}]
    )
    assert errors_of(early) == [(3, "results_date")]
    ok = write_csv(tmp_path / "ok.csv", [dmart(), restated])
    result = parse(ok)
    assert result.errors == []
    assert result.rows[1].events == ()  # restated rows never create reveal events
    assert result.rows[1].observation.vintage == "restated"


def test_wrong_header_is_one_error(tmp_path: Path) -> None:
    path = tmp_path / "h.csv"
    path.write_bytes(HEADER.replace("revenue_cr", "revenue").encode() + b"\n")
    assert errors_of(path) == [(1, "header")]


def test_row_with_extra_or_missing_fields_is_an_error(tmp_path: Path) -> None:
    good = write_csv(tmp_path / "g.csv", [dmart()]).read_text(encoding="utf-8")
    header, row = good.splitlines()
    path = tmp_path / "f.csv"
    path.write_bytes(f"{header}\n{row},extra\n{row.rsplit(',', 2)[0]}\n".encode())
    assert errors_of(path) == [(2, "row"), (3, "row")]


def test_not_utf8_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "latin1.csv"
    path.write_bytes(HEADER.encode() + b"\nDMART,\xe9\n")
    assert errors_of(path) == [(0, "file")]


# --- DATA-01 edges: BOM, CRLF, blank line, quoted comma ----------------------------------


def test_utf8_bom_is_accepted(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "bom.csv", [dmart()])
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    result = parse(path)
    assert result.errors == []
    assert len(result.rows) == 1


def test_crlf_line_endings_are_accepted(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "crlf.csv", [dmart(), eternal()], newline="\r\n")
    assert b"\r\n" in path.read_bytes()
    result = parse(path)
    assert result.errors == []
    assert result.rows[0].observation.source_ref == URL + "#p8"  # no stray \r


def test_trailing_blank_line_and_quoted_comma_in_notes(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "q.csv", [dmart(notes="SYNTHETIC, quoted, with commas")])
    path.write_bytes(path.read_bytes() + b"\n")
    result = parse(path)
    assert result.errors == []
    assert result.rows_seen == 1


# --- verification and environments (D-22, T-01-17) -------------------------------------


def test_unverified_row_loads_in_dev(migrated_sqlite: sa.Engine, tmp_path: Path) -> None:
    path = write_csv(tmp_path / "u.csv", [dmart(verified="N")])
    report = load_seed(migrated_sqlite, path, RULES, get_settings(), now=NOW, dry_run=False)
    assert report.errors == ()
    assert report.observations_inserted == 1
    with migrated_sqlite.connect() as conn:
        kind = conn.execute(sa.select(observations.c.source_kind)).scalar_one()
    assert kind == "seed_csv_unverified"


def test_unverified_row_is_refused_with_require_verified(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "u.csv", [dmart(verified="N")])
    report = load_seed(
        None, path, RULES, get_settings(), now=NOW, dry_run=True, require_verified=True
    )
    assert [(e.row, e.column) for e in report.errors] == [(2, "verified")]


def _canonical_copy(rows: list[dict[str, str]] | None = None, source: Path | None = None) -> Path:
    target = Path.cwd() / CANONICAL_SEED_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    if source is not None:
        shutil.copyfile(source, target)
    else:
        write_csv(target, rows or [])
    return CANONICAL_SEED_PATH


SYNTHETIC_LOOKING_REAL = "https://ir.example.com/synthetic-q2fy27.pdf"  # not .invalid


def test_rehearsal_forces_verified(tmp_path: Path) -> None:
    path = _canonical_copy(
        [
            dmart(
                verified="N",
                source_url=SYNTHETIC_LOOKING_REAL,
                business_update_url=SYNTHETIC_LOOKING_REAL,
            )
        ]
    )
    report = load_seed(None, path, RULES, settings_for("rehearsal"), now=NOW, dry_run=True)
    assert [(e.row, e.column) for e in report.errors] == [(2, "verified")]


def test_rehearsal_refuses_synthetic_fixture(tmp_path: Path) -> None:
    # At its own path, the fixture is refused outright.
    with pytest.raises(SeedError, match="quarterly_revenue.csv"):
        load_seed(None, FIXTURE, RULES, settings_for("rehearsal"), now=NOW, dry_run=True)
    # Copied over the canonical path, every row is refused by its example.invalid host(s).
    path = _canonical_copy(source=FIXTURE)
    report = load_seed(None, path, RULES, settings_for("rehearsal"), now=NOW, dry_run=True)
    assert {e.row for e in report.errors if e.column == "source_url"} == set(range(2, 26))
    assert {e.column for e in report.errors} == {"source_url", "business_update_url"}
    assert report.observations_inserted == 0


@pytest.mark.parametrize("env", ["rehearsal", "live"])
def test_non_canonical_path_is_refused(tmp_path: Path, env: str) -> None:
    path = write_csv(tmp_path / "other.csv", [dmart()])
    with pytest.raises(SeedError, match="quarterly_revenue.csv"):
        load_seed(None, path, RULES, settings_for(env), now=NOW, dry_run=True)


def test_live_write_outside_github_actions_is_refused() -> None:
    path = _canonical_copy([])
    with pytest.raises(LiveContextError):
        load_seed(None, path, RULES, settings_for("live"), now=NOW, dry_run=False)


def test_dev_allows_example_invalid_hosts() -> None:
    assert parse(FIXTURE).errors == []
    forbidden = parse(FIXTURE, forbid_synthetic=True).errors
    assert {e.row for e in forbidden if e.column == "source_url"} == set(range(2, 26))
    # DMART and TITAN rows also cite an example.invalid business update.
    assert len([e for e in forbidden if e.column == "business_update_url"]) == 16


# --- the canonical file -----------------------------------------------------------------


def test_canonical_csv_is_header_only_lf() -> None:
    data = CANONICAL.read_bytes()
    assert data == (HEADER + "\n").encode("ascii")
    assert len(COLUMNS) == 18


# These copy the committed file into the temp cwd rather than chdir to the repo root, so a
# developer's .env is never read (tests/conftest.py).


@pytest.mark.parametrize("env", ["dev", "rehearsal"])
def test_canonical_csv_dry_runs_with_zero_rows(env: str) -> None:
    path = _canonical_copy(source=CANONICAL)
    report = load_seed(None, path, RULES, settings_for(env), now=NOW, dry_run=True)
    assert report.errors == ()
    assert report.rows_seen == 0


def test_cli_dry_run_on_canonical_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALLEDIT_UNIVERSE_PATH", str(REPO_ROOT / "config" / "universe.toml"))
    _canonical_copy(source=CANONICAL)
    result = CliRunner().invoke(app, ["seed", "load", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "0 rows seen" in result.output


def test_cli_lists_every_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALLEDIT_UNIVERSE_PATH", str(REPO_ROOT / "config" / "universe.toml"))
    path = write_csv(
        tmp_path / "bad.csv", [dmart(revenue_cr="1"), dmart(**Q1FY27, verified="maybe")]
    )
    result = CliRunner().invoke(app, ["seed", "load", "--dry-run", "--csv", str(path)])
    assert result.exit_code == 1
    assert "row 2, column revenue_cr" in result.output
    assert "row 3, column verified" in result.output
    assert "2 error(s)" in result.output
