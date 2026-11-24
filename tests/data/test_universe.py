"""FOUND-03 / PIT-05 (config half): the universe config and its strict loader."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest
from nowcaster.cli import app
from nowcaster.universe import UniverseError, load_universe, parse_universe
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIVERSE_PATH = REPO_ROOT / "config" / "universe.toml"


def _text() -> str:
    return UNIVERSE_PATH.read_bytes().decode("utf-8")


def _replace_after(text: str, anchor: str, old: str, new: str) -> str:
    """Replace the first ``old`` that follows ``anchor`` (anchor must exist exactly once)."""
    assert text.count(anchor) == 1, anchor
    head, tail = text.split(anchor, 1)
    assert old in tail, old
    return head + anchor + tail.replace(old, new, 1)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "universe.toml"
    path.write_bytes(text.encode("utf-8"))
    return path


def test_repo_config_loads_with_three_tickers_in_order() -> None:
    universe = load_universe(UNIVERSE_PATH)
    assert [c.ticker for c in universe.companies] == ["DMART", "ETERNAL", "TITAN"]
    assert [c.ticker for c in universe.enabled()] == ["DMART", "ETERNAL", "TITAN"]
    assert universe.schema_version == "universe-1"


def test_repo_config_values() -> None:
    universe = load_universe(UNIVERSE_PATH)
    offsets = {c.ticker: c.reveal_offset_days for c in universe.companies}
    assert offsets == {"DMART": 1, "ETERNAL": 7, "TITAN": 2}
    dmart, eternal, titan = (universe.company(t) for t in ("DMART", "ETERNAL", "TITAN"))
    assert dmart.isin == "INE192R01011" and dmart.isin_confirmed is True
    assert eternal.isin == "INE758T01015" and eternal.isin_confirmed is True
    assert titan.isin == "INE280A01028" and titan.isin_confirmed is True
    assert eternal.has_business_update is False
    assert dmart.has_business_update is True and titan.has_business_update is True
    assert eternal.labels == ("low confidence: post-break comparables limited",)
    assert eternal.trends_terms == ("Zomato", "Blinkit", "District")
    assert eternal.symbol_history[0].symbol == "ZOMATO"
    assert eternal.symbol_history[0].until == date(2025, 4, 8)
    assert all(c.play_package_ids == () for c in universe.companies)
    assert all(
        c.revenue_basis == "consolidated_revenue_from_operations" for c in universe.companies
    )

    eternal_breaks = universe.breaks_for("ETERNAL")
    assert [b.id for b in eternal_breaks] == ["eternal-blinkit-inventory", "gst2.0"]
    blinkit = eternal_breaks[0]
    assert blinkit.kind == "quarter_range"
    assert (blinkit.start_q, blinkit.end_q) == ("Q2FY26", "Q3FY26")
    assert blinkit.confirmed is True
    gst = universe.breaks_for("DMART")[0]
    assert gst.id == "gst2.0" and gst.kind == "date"
    assert gst.effective == date(2025, 9, 22)
    assert gst.applies_to == ("*",)
    assert [b.id for b in universe.breaks_for("TITAN")] == ["gst2.0"]


def test_universe_sha256_is_sha256_of_exact_file_bytes() -> None:
    universe = load_universe(UNIVERSE_PATH)
    assert universe.universe_sha256 == hashlib.sha256(UNIVERSE_PATH.read_bytes()).hexdigest()


def test_repo_config_is_lf_only_ascii() -> None:
    data = UNIVERSE_PATH.read_bytes()
    assert b"\r" not in data
    assert data.isascii()


def test_loading_twice_is_equal() -> None:
    first = load_universe(UNIVERSE_PATH)
    second = load_universe(UNIVERSE_PATH)
    assert first == second
    assert first.universe_sha256 == second.universe_sha256


def test_disabling_company_drops_it_from_enabled(tmp_path: Path) -> None:
    original = load_universe(UNIVERSE_PATH)
    text = _replace_after(_text(), 'ticker = "ETERNAL"', "enabled = true", "enabled = false")
    edited = load_universe(_write(tmp_path, text))
    assert [c.ticker for c in edited.enabled()] == ["DMART", "TITAN"]
    # Still listed (the CLI marks it disabled), just not locked.
    assert [c.ticker for c in edited.companies] == ["DMART", "ETERNAL", "TITAN"]
    assert edited.company("ETERNAL").enabled is False
    assert edited.universe_sha256 != original.universe_sha256


def test_unknown_ticker_lookup_raises() -> None:
    with pytest.raises(KeyError):
        load_universe(UNIVERSE_PATH).company("RELIANCE")


# The last line of ETERNAL's block: TITAN's ticker line is the first one after it.
_BEFORE_TITAN = 'break_ids = ["eternal-blinkit-inventory", "gst2.0"]'

_BAD_EDITS = {
    "duplicate_ticker": (_BEFORE_TITAN, 'ticker = "TITAN"', 'ticker = "DMART"'),
    "bad_isin_format": ('ticker = "DMART"', "INE192R01011", "US0378331005"),
    "bad_isin_check_digit": ('ticker = "DMART"', "INE192R01011", "INE192R01012"),
    "unknown_break_id": ('ticker = "TITAN"', 'break_ids = ["gst2.0"]', 'break_ids = ["gst3.0"]'),
    "missing_applicable_break": ('ticker = "TITAN"', 'break_ids = ["gst2.0"]', "break_ids = []"),
    "start_q_after_end_q": (
        'id = "eternal-blinkit-inventory"',
        'start_q = "Q2FY26"',
        'start_q = "Q4FY26"',
    ),
    "non_canonical_quarter": (
        'id = "eternal-blinkit-inventory"',
        'start_q = "Q2FY26"',
        'start_q = "q1 fy26"',
    ),
    "http_source_url": (
        'id = "eternal-blinkit-inventory"',
        "https://b.zmtcdn.com",
        "http://b.zmtcdn.com",
    ),
    "label_with_double_quote": (
        'ticker = "ETERNAL"',
        'labels = ["low confidence: post-break comparables limited"]',
        "labels = ['low \"confidence\"']",
    ),
    "unknown_key": ('ticker = "DMART"', 'name = "Avenue', 'colour = "red"\nname = "Avenue'),
    "reveal_offset_31": ('ticker = "DMART"', "reveal_offset_days = 1", "reveal_offset_days = 31"),
    "offset_as_string": ('ticker = "DMART"', "reveal_offset_days = 1", 'reveal_offset_days = "1"'),
    "enabled_as_string": ('ticker = "DMART"', "enabled = true", 'enabled = "true"'),
    "lowercase_ticker": (_BEFORE_TITAN, 'ticker = "TITAN"', 'ticker = "titan"'),
    "date_break_without_effective": ('id = "gst2.0"', "effective = 2025-09-22\n", ""),
    "wrong_schema_version": ("schema_version", '"universe-1"', '"universe-2"'),
    "non_ascii_name": (
        'ticker = "TITAN"',
        'name = "Titan Company Ltd"',
        'name = "Titan Company Lté"',
    ),
}


@pytest.mark.parametrize("case", sorted(_BAD_EDITS))
def test_invalid_configs_fail_to_load(tmp_path: Path, case: str) -> None:
    anchor, old, new = _BAD_EDITS[case]
    text = _replace_after(_text(), anchor, old, new)
    with pytest.raises(UniverseError):
        load_universe(_write(tmp_path, text))


def test_universe_sha256_key_in_file_is_refused() -> None:
    data = UNIVERSE_PATH.read_bytes().replace(
        b'schema_version = "universe-1"',
        b'schema_version = "universe-1"\nuniverse_sha256 = "' + b"0" * 64 + b'"',
    )
    with pytest.raises(UniverseError, match="computed from the file bytes"):
        parse_universe(data)


def test_unreadable_and_undecodable_configs_raise(tmp_path: Path) -> None:
    with pytest.raises(UniverseError, match="not readable"):
        load_universe(tmp_path / "missing.toml")
    with pytest.raises(UniverseError, match="UTF-8"):
        parse_universe(b"\xff\xfe")
    with pytest.raises(UniverseError, match="TOML"):
        parse_universe(b"schema_version = ")


# --- CLI ------------------------------------------------------------------------------------


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("CALLEDIT_UNIVERSE_PATH", str(UNIVERSE_PATH))
    return CliRunner()


def test_cli_calendar_q3fy27(runner: CliRunner) -> None:
    result = runner.invoke(app, ["calendar", "--quarter", "Q3FY27"])
    assert result.exit_code == 0, result.output
    out = result.output
    assert out.count("2026-12-31T18:30:00Z") == 1  # DMART
    assert "2027-01-01T18:30:00Z" in out  # TITAN
    assert "2027-01-06T18:30:00Z" in out  # ETERNAL
    assert "2027-01-01 00:00:00 IST" in out
    assert out.count("status: expected") == 3
    assert out.count("reveal_at: none") == 3


def test_cli_calendar_accepts_lowercase_label(runner: CliRunner) -> None:
    result = runner.invoke(app, ["calendar", "--quarter", "q3 fy27"])
    assert result.exit_code == 0, result.output
    assert "quarter: Q3FY27 (2026-10-01..2026-12-31)" in result.output


def test_cli_calendar_bad_label_exits_non_zero(runner: CliRunner) -> None:
    result = runner.invoke(app, ["calendar", "--quarter", "Q3FY"])
    assert result.exit_code != 0
    assert "Q3FY" in result.output


def test_cli_calendar_skips_disabled(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = _replace_after(_text(), 'ticker = "ETERNAL"', "enabled = true", "enabled = false")
    monkeypatch.setenv("CALLEDIT_UNIVERSE_PATH", str(_write(tmp_path, text)))
    result = runner.invoke(app, ["calendar", "--quarter", "Q3FY27"])
    assert result.exit_code == 0, result.output
    assert "company ETERNAL" not in result.output
    assert "company DMART" in result.output and "company TITAN" in result.output


def test_cli_universe_lists_everything(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = runner.invoke(app, ["universe"])
    assert result.exit_code == 0, result.output
    out = result.output
    for needle in (
        "company DMART (enabled)",
        "company ETERNAL (enabled)",
        "company TITAN (enabled)",
        "break eternal-blinkit-inventory",
        "break gst2.0",
        "2025-09-22",
        "Q1FY26",
        "confirmed: true",
        "isin_confirmed: true",
        "ZOMATO until 2025-04-08",
        "universe_sha256: " + hashlib.sha256(UNIVERSE_PATH.read_bytes()).hexdigest(),
    ):
        assert needle in out, needle

    text = _replace_after(_text(), 'ticker = "TITAN"', "enabled = true", "enabled = false")
    monkeypatch.setenv("CALLEDIT_UNIVERSE_PATH", str(_write(tmp_path, text)))
    result = runner.invoke(app, ["universe"])
    assert result.exit_code == 0, result.output
    assert "company TITAN (disabled)" in result.output


def test_cli_universe_invalid_config_exits_non_zero(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = _replace_after(
        _text(), 'ticker = "DMART"', "reveal_offset_days = 1", "reveal_offset_days = 31"
    )
    monkeypatch.setenv("CALLEDIT_UNIVERSE_PATH", str(_write(tmp_path, text)))
    result = runner.invoke(app, ["universe"])
    assert result.exit_code == 1
    assert "refused" in result.output
