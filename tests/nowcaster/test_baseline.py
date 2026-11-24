"""Baseline rules D-04..D-08 (BASE-01, FEAT-02, PIT-05).

All values are SYNTHETIC test numbers, never real history. Most tests drive
``compute_baseline`` through ``FakeReader``, a ``PointInTimeReader`` whose ``series`` returns
fixed observations, so the arithmetic is tested without a database; the vintage test uses a
real migrated store.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from calledit_data.calendar.fiscal import FiscalQuarter
from calledit_data.pit.reader import Observation, PointInTimeReader, TiedVintageError
from calledit_data.store.writer import ObservationIn, ensure_series, insert_observations
from hypothesis import given
from hypothesis import strategies as st
from nowcaster.baseline import (
    ETERNAL_LABEL,
    MODEL_VERSION,
    BaselineRefusal,
    BaselineResult,
    compute_baseline,
)
from nowcaster.universe import Break, Universe, load_universe

from tests.conftest import REPO_ROOT

UNIVERSE: Universe = load_universe(REPO_ROOT / "config" / "universe.toml")
TARGET = FiscalQuarter.parse("Q3FY27")
AS_OF = datetime(2026, 11, 28, 4, 0, 0, tzinfo=UTC)
PLAIN = tuple(Decimal(1000 + 10 * i) for i in range(8))  # Q-8..Q-1, SYNTHETIC


class FakeReader(PointInTimeReader):
    """Returns the given observations as if they were the reader's output."""

    def __init__(self, rows: Sequence[Observation], as_of: datetime = AS_OF) -> None:
        super().__init__(sa.create_engine("sqlite://"), as_of, "live")
        self._rows = tuple(rows)

    def series(self, series_key: str) -> tuple[Observation, ...]:
        return self._rows


def _obs(
    ticker: str,
    quarter: FiscalQuarter,
    value: Any,
    *,
    source_kind: str = "seed_csv",
    obs_id: int = 1,
) -> Observation:
    return Observation(
        obs_id=obs_id,
        series_key=f"rev.consolidated.{ticker}",
        period_date=quarter.end,
        value=value,
        available_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
        availability_basis="exchange_timestamp",
        ingested_at=datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC),
        vintage="first_reported",
        source_ref="https://example.invalid/synthetic-fixture#p1",
        source_kind=source_kind,
        content_hash=f"{quarter.label}-{value}".encode().hex().ljust(64, "0")[:64],
    )


def _window(target: FiscalQuarter = TARGET) -> tuple[FiscalQuarter, ...]:
    return tuple(target.shift(-k) for k in range(8, 0, -1))


def _reader(
    ticker: str,
    values: Sequence[Any] = PLAIN,
    target: FiscalQuarter = TARGET,
    *,
    drop: Sequence[str] = (),
    unverified: Sequence[str] = (),
    first_obs_id: int = 1,
    as_of: datetime = AS_OF,
) -> FakeReader:
    rows = [
        _obs(
            ticker,
            q,
            v,
            source_kind="seed_csv_unverified" if q.label in unverified else "seed_csv",
            obs_id=first_obs_id + i,
        )
        for i, (q, v) in enumerate(zip(_window(target), values, strict=True))
        if q.label not in drop
    ]
    return FakeReader(rows, as_of)


def _range_break(start_q: str, end_q: str, applies_to: str = "ETERNAL") -> Break:
    return Break(
        id="eternal-blinkit-inventory",
        kind="quarter_range",
        applies_to=(applies_to,),
        start_q=start_q,
        end_q=end_q,
        source_url="https://example.invalid/synthetic-fixture",
        source_note="SYNTHETIC TEST BREAK",
        confirmed=False,
    )


def _date_break(break_id: str, effective: date) -> Break:
    return Break(
        id=break_id,
        kind="date",
        applies_to=("*",),
        effective=effective,
        source_url="https://example.invalid/synthetic-fixture",
        source_note="SYNTHETIC TEST BREAK",
        confirmed=True,
    )


def _ok(outcome: BaselineResult | BaselineRefusal) -> BaselineResult:
    assert isinstance(outcome, BaselineResult), outcome
    return outcome


def _eternal(
    start_q: str,
    end_q: str,
    values: Sequence[Decimal] = PLAIN,
    target: FiscalQuarter = TARGET,
) -> BaselineResult:
    company = UNIVERSE.company("ETERNAL")
    return _ok(
        compute_baseline(
            company, target, _reader("ETERNAL", values, target), [_range_break(start_q, end_q)]
        )
    )


# --- TTM arithmetic -----------------------------------------------------------------------


def test_ttm_exact() -> None:
    # prior (Q-8..Q-5) = 400, recent (Q-4..Q-1) = 440, SQLY = Q-4 = 100: g = 0.1.
    values = [Decimal(100)] * 4 + [Decimal(100), Decimal(110), Decimal(110), Decimal(120)]
    result = _ok(compute_baseline(UNIVERSE.company("DMART"), TARGET, _reader("DMART", values), []))
    assert result.method == "ttm_yoy"
    assert result.pair_status == "none"
    assert result.pair is None
    assert result.growth == Decimal("0.1")
    assert result.growth_str == "0.100000"
    assert result.point == Decimal("110.00")
    assert result.snapshot["point_inr_cr"] == "110.00"
    assert result.snapshot["sum_recent_inr_cr"] == "440.00"
    assert result.snapshot["sum_prior_inr_cr"] == "400.00"
    assert result.snapshot["pair_t"] == "none"
    assert result.sqly_quarter == "Q3FY26"
    assert result.window_quarters == tuple(q.label for q in _window())


def test_half_even_ties() -> None:
    company = UNIVERSE.company("DMART")
    # 100 x (400.5 / 400) = 100.125 exactly: the tie rounds to the even cent, 100.12.
    down = [Decimal(100)] * 4 + [Decimal(100), Decimal(100), Decimal(100), Decimal("100.5")]
    assert _ok(compute_baseline(company, TARGET, _reader("DMART", down), [])).point == Decimal(
        "100.12"
    )
    # 100 x (2002.7 / 2000) = 100.135 exactly: the tie rounds to the even cent, 100.14.
    up = [Decimal(500)] * 4 + [Decimal(100), Decimal("700.9"), Decimal("600.9"), Decimal("600.9")]
    assert _ok(compute_baseline(company, TARGET, _reader("DMART", up), [])).point == Decimal(
        "100.14"
    )


def test_negative_growth() -> None:
    values = [Decimal(100)] * 4 + [Decimal(100), Decimal(90), Decimal(80), Decimal(90)]
    result = _ok(compute_baseline(UNIVERSE.company("DMART"), TARGET, _reader("DMART", values), []))
    assert result.growth == Decimal("-0.1")
    assert result.point == Decimal("90.00")
    assert result.growth_str == "-0.100000"


def test_point_uses_unrounded_growth() -> None:
    # g = 1 / 3,000,000: rounded to 6 dp it is 0.000000, so a rounded g would give 300000.00.
    values = [Decimal(750000)] * 4 + [
        Decimal(300000),
        Decimal(900000),
        Decimal(900000),
        Decimal(900001),
    ]
    result = _ok(compute_baseline(UNIVERSE.company("DMART"), TARGET, _reader("DMART", values), []))
    assert result.growth_str == "0.000000"
    assert result.point == Decimal("300000.10")


def test_no_float_path() -> None:
    values = [*PLAIN[:-1], 1070.0]
    with pytest.raises(TypeError, match="Decimal"):
        compute_baseline(UNIVERSE.company("DMART"), TARGET, _reader("DMART", values), [])


# --- refusals (D-08, T-01-18) -------------------------------------------------------------


def test_missing_quarter_refused() -> None:
    outcome = compute_baseline(
        UNIVERSE.company("DMART"), TARGET, _reader("DMART", drop=["Q4FY25"]), []
    )
    assert outcome == BaselineRefusal("DMART", "Q3FY27", AS_OF, "missing_seed_quarter", ("Q4FY25",))


def test_every_missing_quarter_is_listed_in_window_order() -> None:
    outcome = compute_baseline(
        UNIVERSE.company("DMART"),
        TARGET,
        _reader("DMART", drop=["Q2FY27", "Q3FY25"], unverified=["Q1FY26"]),
        [],
    )
    assert isinstance(outcome, BaselineRefusal)
    assert outcome.reason_code == "missing_seed_quarter"  # missing outranks unverified
    assert outcome.missing_quarters == ("Q3FY25", "Q1FY26", "Q2FY27")


def test_unverified_quarter_refused() -> None:
    outcome = compute_baseline(
        UNIVERSE.company("TITAN"), TARGET, _reader("TITAN", unverified=["Q2FY26"]), []
    )
    assert outcome == BaselineRefusal(
        "TITAN", "Q3FY27", AS_OF, "unverified_seed_quarter", ("Q2FY26",)
    )


def test_empty_series_refuses_all_eight() -> None:
    outcome = compute_baseline(UNIVERSE.company("DMART"), TARGET, FakeReader([]), [])
    assert isinstance(outcome, BaselineRefusal)
    assert outcome.missing_quarters == tuple(q.label for q in _window())


class TiedReader(FakeReader):
    """A reader whose store holds two different values at the latest available_at (a tie)."""

    def series(self, series_key: str) -> tuple[Observation, ...]:
        raise TiedVintageError(series_key, (FiscalQuarter.parse("Q1FY26").end,))


def test_tied_available_at_is_refused_with_its_own_reason() -> None:
    outcome = compute_baseline(UNIVERSE.company("DMART"), TARGET, TiedReader([]), [])
    assert outcome == BaselineRefusal("DMART", "Q3FY27", AS_OF, "tied_available_at", ("Q1FY26",))


def test_zero_base_sum_is_refused_not_raised() -> None:
    values = [Decimal(0)] * 4 + list(PLAIN[4:])
    outcome = compute_baseline(UNIVERSE.company("DMART"), TARGET, _reader("DMART", values), [])
    assert isinstance(outcome, BaselineRefusal)
    assert outcome.reason_code == "invalid_base_sum"
    assert outcome.missing_quarters == ("Q3FY25", "Q4FY25", "Q1FY26", "Q2FY26")


def test_zero_pair_base_is_refused_not_raised() -> None:
    values = list(PLAIN)
    values[3] = Decimal(0)  # Q-5 = Q2FY26, the base of the least-straddling pair
    outcome = compute_baseline(
        UNIVERSE.company("ETERNAL"),
        TARGET,
        _reader("ETERNAL", values),
        [_range_break("Q1FY26", "Q3FY26")],
    )
    assert isinstance(outcome, BaselineRefusal)
    assert outcome.reason_code == "invalid_base_sum"
    assert outcome.missing_quarters == ("Q2FY26",)


# --- break-aware method (D-06) ------------------------------------------------------------


def test_eternal_break_least_straddling() -> None:
    result = _eternal("Q1FY26", "Q3FY26")
    assert result.method == "break_single_pair"
    assert result.pair == ("Q2FY27", "Q2FY26")
    assert result.pair_status == "least_straddling"
    # SQLY = Q3FY26 = PLAIN[4]; rev(Q2FY27) = PLAIN[7]; rev(Q2FY26) = PLAIN[3].
    expected = (PLAIN[4] * (PLAIN[7] / PLAIN[3])).quantize(Decimal("0.01"))
    assert result.point == expected
    assert result.snapshot["pair_t"] == "Q2FY27"
    assert result.snapshot["pair_base"] == "Q2FY26"
    assert result.snapshot["sum_recent_inr_cr"] == "none"
    assert result.snapshot["sum_prior_inr_cr"] == "none"


def test_eternal_break_post_post_pair() -> None:
    result = _eternal("Q3FY25", "Q4FY25")
    assert result.method == "break_single_pair"
    assert result.pair == ("Q2FY27", "Q2FY26")
    assert result.pair_status == "post_break"
    assert result.snapshot["pair_status"] == "post_break"


def test_eternal_window_fully_post_uses_ttm() -> None:
    result = _eternal("Q1FY25", "Q2FY25")
    assert result.method == "ttm_yoy"
    assert result.pair_status == "none"
    assert result.pair is None


def test_break_entirely_after_window_uses_ttm() -> None:
    result = _eternal("Q1FY28", "Q4FY28")
    assert result.method == "ttm_yoy"


@pytest.mark.parametrize(
    ("start_q", "end_q", "status"),
    [
        ("Q3FY25", "Q3FY25", "post_break"),  # range is exactly the oldest window quarter
        ("Q2FY27", "Q2FY27", "least_straddling"),  # range is exactly Q-1
        ("Q4FY24", "Q2FY25", "ttm_yoy"),  # range ends the quarter before the window starts
        ("Q3FY27", "Q4FY27", "ttm_yoy"),  # range starts at the target quarter: all pre
    ],
)
def test_break_boundary_placements(start_q: str, end_q: str, status: str) -> None:
    result = _eternal(start_q, end_q)
    observed = "ttm_yoy" if result.method == "ttm_yoy" else result.pair_status
    assert observed == status


@given(
    start_index=st.integers(min_value=-6, max_value=12),
    length=st.integers(min_value=1, max_value=8),
)
def test_pair_is_always_q_minus_1(start_index: int, length: int) -> None:
    start = TARGET.shift(start_index - 8)  # starts anywhere from before the window to after it
    end = start.shift(length - 1)
    result = _eternal(start.label, end.label)
    last, first = TARGET.shift(-1), TARGET.shift(-8)
    outside = start > last or end < first
    if outside:
        assert result.method == "ttm_yoy"
        return
    assert result.method == "break_single_pair"
    assert result.pair == (TARGET.shift(-1).label, TARGET.shift(-5).label)
    # (Q-1, Q-5) is post-post exactly when the range ended before Q-5.
    assert (result.pair_status == "post_break") == (end < TARGET.shift(-5))


def test_multiple_ranges_require_post_for_every_break() -> None:
    company = UNIVERSE.company("ETERNAL")
    # Q-1 = Q2FY27 is post both ranges, but Q-5 = Q2FY26 is pre the second range (Q1FY27):
    # a pair counts as post-break only when both quarters are post EVERY range.
    second = _range_break("Q1FY27", "Q1FY27").model_copy(update={"id": "second-break"})
    result = _ok(
        compute_baseline(
            company, TARGET, _reader("ETERNAL"), [_range_break("Q3FY25", "Q4FY25"), second]
        )
    )
    assert result.method == "break_single_pair"
    assert result.pair_status == "least_straddling"
    assert result.breaks_in_window == ("eternal-blinkit-inventory", "second-break")


# --- labels (D-06) ------------------------------------------------------------------------


@pytest.mark.parametrize(("start_q", "end_q"), [("Q1FY26", "Q3FY26"), ("Q1FY25", "Q2FY25")])
def test_eternal_label_always_present(start_q: str, end_q: str) -> None:
    result = _eternal(start_q, end_q)  # one break method result, one ttm_yoy result
    assert ETERNAL_LABEL in result.labels
    assert result.snapshot["labels"] == ETERNAL_LABEL
    assert ETERNAL_LABEL == "low confidence: post-break comparables limited"


def test_eternal_label_survives_a_config_edit_that_drops_it() -> None:
    stripped = UNIVERSE.company("ETERNAL").model_copy(update={"labels": ()})
    result = _ok(compute_baseline(stripped, TARGET, _reader("ETERNAL"), []))
    assert result.labels == (ETERNAL_LABEL,)


def test_other_companies_carry_no_label() -> None:
    for ticker in ("DMART", "TITAN"):
        result = _ok(compute_baseline(UNIVERSE.company(ticker), TARGET, _reader(ticker), []))
        assert result.labels == ()
        assert result.snapshot["labels"] == "none"


# --- breaks_in_window (D-07) --------------------------------------------------------------


def test_breaks_in_window() -> None:
    for ticker, expected in (
        ("DMART", ("gst2.0",)),
        ("ETERNAL", ("eternal-blinkit-inventory", "gst2.0")),
        ("TITAN", ("gst2.0",)),
    ):
        company = UNIVERSE.company(ticker)
        result = _ok(
            compute_baseline(company, TARGET, _reader(ticker), UNIVERSE.breaks_for(ticker))
        )
        assert result.breaks_in_window == expected
        assert result.snapshot["breaks_in_window"] == "|".join(expected)


def test_no_break_in_a_late_window() -> None:
    late = FiscalQuarter.parse("Q3FY29")  # window Q3FY27..Q2FY29, entirely after Sep 2025
    company = UNIVERSE.company("ETERNAL")
    result = _ok(
        compute_baseline(
            company, late, _reader("ETERNAL", target=late), UNIVERSE.breaks_for("ETERNAL")
        )
    )
    assert result.breaks_in_window == ()
    assert result.snapshot["breaks_in_window"] == "none"
    assert result.method == "ttm_yoy"


def test_date_break_on_window_edges() -> None:
    company = UNIVERSE.company("DMART")
    first_day, last_day = _window()[0].start, _window()[-1].end
    edges = {
        "first-day": (first_day, True),
        "day-before": (date.fromordinal(first_day.toordinal() - 1), False),
        "last-day": (last_day, True),
        "day-after": (date.fromordinal(last_day.toordinal() + 1), False),
    }
    for name, (effective, inside) in edges.items():
        found = _ok(
            compute_baseline(company, TARGET, _reader("DMART"), [_date_break("edge", effective)])
        ).breaks_in_window
        assert (found == ("edge",)) == inside, name


def test_date_break_never_changes_the_arithmetic() -> None:
    company = UNIVERSE.company("DMART")
    plain = _ok(compute_baseline(company, TARGET, _reader("DMART"), []))
    with_gst = _ok(compute_baseline(company, TARGET, _reader("DMART"), UNIVERSE.breaks))
    assert with_gst.breaks_in_window == ("gst2.0",)
    assert (with_gst.point, with_gst.growth, with_gst.method) == (
        plain.point,
        plain.growth,
        plain.method,
    )


def test_breaks_of_other_tickers_are_ignored() -> None:
    result = _ok(
        compute_baseline(
            UNIVERSE.company("DMART"),
            TARGET,
            _reader("DMART"),
            [_range_break("Q1FY26", "Q3FY26", applies_to="ETERNAL")],
        )
    )
    assert result.method == "ttm_yoy"
    assert result.breaks_in_window == ()


# --- snapshot -----------------------------------------------------------------------------


SNAPSHOT_KEYS = {
    "scheme",
    "ticker",
    "fiscal_quarter",
    "as_of",
    "model_version",
    "method",
    "sqly_quarter",
    "window_quarters",
    "pair_t",
    "pair_base",
    "pair_status",
    "sum_recent_inr_cr",
    "sum_prior_inr_cr",
    "growth",
    "point_inr_cr",
    "labels",
    "breaks_in_window",
    "inputs",
}


def test_snapshot_shape_and_obs_id_exclusion() -> None:
    company = UNIVERSE.company("DMART")
    a = _ok(compute_baseline(company, TARGET, _reader("DMART", first_obs_id=1), []))
    b = _ok(compute_baseline(company, TARGET, _reader("DMART", first_obs_id=900), []))
    assert set(a.snapshot) == SNAPSHOT_KEYS
    assert a.snapshot["scheme"] == "calledit-snapshot-v1"
    assert a.snapshot["model_version"] == MODEL_VERSION == "baseline-sqly@1.0.0"
    assert a.snapshot["as_of"] == "2026-11-28T04:00:00Z"
    assert [row["fiscal_quarter"] for row in a.snapshot["inputs"]] == list(a.window_quarters)
    assert all("obs_id" not in row for row in a.snapshot["inputs"])
    assert a.snapshot_canonical == b.snapshot_canonical  # store-dependent ids never enter it
    assert a.snapshot_sha256 == b.snapshot_sha256
    assert len(a.snapshot_sha256) == 64


def test_snapshot_changes_with_as_of_and_values() -> None:
    company = UNIVERSE.company("DMART")
    base = _ok(compute_baseline(company, TARGET, _reader("DMART"), []))
    other_values = [*PLAIN[:-1], Decimal(1071)]
    changed = _ok(compute_baseline(company, TARGET, _reader("DMART", other_values), []))
    assert base.snapshot_sha256 != changed.snapshot_sha256
    later = _reader("DMART", as_of=datetime(2026, 11, 29, 4, 0, 0, tzinfo=UTC))
    assert base.snapshot_sha256 != _ok(compute_baseline(company, TARGET, later, [])).snapshot_sha256


# --- latest vintage before as_of (D-05), real store ---------------------------------------

KEY = "rev.consolidated.DMART"


def test_latest_vintage_before_as_of(migrated_sqlite: sa.Engine) -> None:
    window = _window()
    original = {q: Decimal(10000 + 100 * i) for i, q in enumerate(window)}
    available = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    rows = [
        ObservationIn(
            series_key=KEY,
            period_date=q.end,
            value=v,
            available_at=available,
            availability_basis="exchange_timestamp",
            source_ref="https://example.invalid/synthetic-fixture#p1",
            vintage="first_reported",
            source_kind="seed_csv",
        )
        for q, v in original.items()
    ]
    sqly = TARGET.shift(-4)  # Q3FY26, restated up by 50
    restated = replace(
        rows[4],
        value=original[sqly] + 50,
        available_at=datetime(2026, 11, 20, 0, 0, 0, tzinfo=UTC),
        vintage="restated",
    )
    with migrated_sqlite.begin() as conn:
        ensure_series(
            conn, KEY, "seed_csv", "revenue", "DMART", "inr_crore", "quarterly", "manual_seed"
        )
        insert_observations(conn, rows, datetime(2026, 1, 2, tzinfo=UTC))
        insert_observations(conn, [restated], datetime(2026, 11, 20, 1, 0, 0, tzinfo=UTC))

    company = UNIVERSE.company("DMART")

    def point_for(values: Mapping[FiscalQuarter, Decimal]) -> Decimal:
        recent = sum((values[q] for q in window[4:]), Decimal(0))
        prior = sum((values[q] for q in window[:4]), Decimal(0))
        return (values[sqly] * (recent / prior)).quantize(Decimal("0.01"))

    before = PointInTimeReader(migrated_sqlite, datetime(2026, 11, 15, tzinfo=UTC), "live")
    after = PointInTimeReader(migrated_sqlite, datetime(2026, 11, 28, tzinfo=UTC), "live")
    assert _ok(compute_baseline(company, TARGET, before, [])).point == point_for(original)
    assert _ok(compute_baseline(company, TARGET, after, [])).point == point_for(
        {**original, sqly: original[sqly] + 50}
    )
    used = {i.vintage for i in _ok(compute_baseline(company, TARGET, after, [])).inputs}
    assert used == {"first_reported", "restated"}
