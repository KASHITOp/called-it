"""FOUND-05: fiscal-quarter labels, boundaries and integer arithmetic."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from calledit_data.calendar.fiscal import FY_MAX, FY_MIN, FiscalQuarter
from hypothesis import given, settings
from hypothesis import strategies as st

Q3FY27 = FiscalQuarter(fy=2027, q=3)


def test_worked_example_q3fy27() -> None:
    assert FiscalQuarter.parse("Q3FY27") == Q3FY27
    assert Q3FY27.label == "Q3FY27"
    assert Q3FY27.start == date(2026, 10, 1)
    assert Q3FY27.end == date(2026, 12, 31)


def test_fy27_spans_april_to_march() -> None:
    assert FiscalQuarter(2027, 1).start == date(2026, 4, 1)
    assert FiscalQuarter(2027, 1).end == date(2026, 6, 30)
    assert FiscalQuarter(2027, 2).start == date(2026, 7, 1)
    assert FiscalQuarter(2027, 2).end == date(2026, 9, 30)
    assert FiscalQuarter(2027, 4).start == date(2027, 1, 1)
    assert FiscalQuarter(2027, 4).end == date(2027, 3, 31)


def test_quarter_boundaries_are_exact() -> None:
    assert FiscalQuarter.containing(date(2026, 12, 31)) == Q3FY27
    assert FiscalQuarter.containing(date(2027, 1, 1)) == FiscalQuarter.parse("Q4FY27")
    assert FiscalQuarter.parse("Q4FY27").end == date(2027, 3, 31)
    assert FiscalQuarter.parse("Q1FY28").start == date(2027, 4, 1)
    assert FiscalQuarter.containing(date(2027, 3, 31)) == FiscalQuarter.parse("Q4FY27")
    assert FiscalQuarter.containing(date(2027, 4, 1)) == FiscalQuarter.parse("Q1FY28")
    assert FiscalQuarter.containing(date(2026, 9, 30)) == FiscalQuarter.parse("Q2FY27")
    assert FiscalQuarter.containing(date(2026, 10, 1)) == Q3FY27


def test_leap_year_february_quarter_end() -> None:
    assert FiscalQuarter.parse("Q4FY28").end == date(2028, 3, 31)
    assert FiscalQuarter.containing(date(2028, 2, 29)) == FiscalQuarter.parse("Q4FY28")


def test_shift_minus_four_is_same_quarter_last_fy() -> None:
    assert FiscalQuarter.parse("Q1FY27").shift(-4) == FiscalQuarter.parse("Q1FY26")
    assert Q3FY27.shift(-4) == FiscalQuarter.parse("Q3FY26")
    assert Q3FY27.shift(1) == FiscalQuarter.parse("Q4FY27")
    assert Q3FY27.shift(2) == FiscalQuarter.parse("Q1FY28")
    assert FiscalQuarter.parse("Q1FY27").shift(-1) == FiscalQuarter.parse("Q4FY26")
    assert Q3FY27.shift(0) == Q3FY27


def test_ordering_is_chronological() -> None:
    assert FiscalQuarter.parse("Q4FY26") < FiscalQuarter.parse("Q1FY27") < Q3FY27
    assert sorted([Q3FY27, FiscalQuarter(2026, 4), FiscalQuarter(2027, 1)]) == [
        FiscalQuarter(2026, 4),
        FiscalQuarter(2027, 1),
        Q3FY27,
    ]


def test_period_start_utc_is_start_midnight_ist() -> None:
    assert Q3FY27.period_start_utc == datetime(2026, 9, 30, 18, 30, tzinfo=UTC)


@pytest.mark.parametrize("label", ["q3 fy27", "Q3 FY27", "q3fy27", "Q3fy27", "Q3 fY27"])
def test_parse_is_case_insensitive_with_one_optional_space(label: str) -> None:
    quarter = FiscalQuarter.parse(label)
    assert quarter == Q3FY27
    assert quarter.label == "Q3FY27"
    assert quarter.label.isascii()


@pytest.mark.parametrize(
    "label",
    [
        "",
        " ",
        "Q5FY27",
        "Q0FY27",
        "Q3FY",
        "Q3FY2027",
        "Q3FY7",
        "Q 3FY27",
        "Q3  FY27",
        "Q3\tFY27",
        " Q3FY27",
        "Q3FY27 ",
        "Q3FY27\n",
        "Q3FY٢٧",  # Arabic-Indic digits
        "Q٣FY27",  # Arabic-Indic three
        "Q3FY२७",  # Devanagari digits
        "Q3FY２７",  # full-width digits
        "Ｑ3FY27",  # full-width Q
        "FY27Q3",
        "Q3-FY27",
        "3QFY27",
    ],
)
def test_parse_rejects_malformed_labels(label: str) -> None:
    with pytest.raises(ValueError, match="not a fiscal quarter label"):
        FiscalQuarter.parse(label)


@pytest.mark.parametrize("value", [None, 327, b"Q3FY27", Q3FY27])
def test_parse_rejects_non_strings(value: object) -> None:
    with pytest.raises(ValueError, match="not a fiscal quarter label"):
        FiscalQuarter.parse(value)  # type: ignore[arg-type]


def test_bad_label_appears_in_error() -> None:
    with pytest.raises(ValueError, match="Q5FY27"):
        FiscalQuarter.parse("Q5FY27")


@pytest.mark.parametrize(("fy", "q"), [(1999, 1), (2100, 1), (2027, 0), (2027, 5)])
def test_out_of_range_construction_raises(fy: int, q: int) -> None:
    with pytest.raises(ValueError):
        FiscalQuarter(fy=fy, q=q)


@pytest.mark.parametrize(("fy", "q"), [(2027.0, 3), (2027, 3.0), (True, 1), ("2027", 3)])
def test_non_integer_fields_raise(fy: object, q: object) -> None:
    with pytest.raises(TypeError):
        FiscalQuarter(fy=fy, q=q)  # type: ignore[arg-type]


@pytest.mark.parametrize("n", [1.0, True, "1"])
def test_shift_is_integer_only(n: object) -> None:
    with pytest.raises(TypeError):
        Q3FY27.shift(n)  # type: ignore[arg-type]


def test_shift_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        FiscalQuarter(FY_MIN, 1).shift(-1)
    with pytest.raises(ValueError):
        FiscalQuarter(FY_MAX, 4).shift(1)


def test_containing_rejects_datetime() -> None:
    with pytest.raises(TypeError):
        FiscalQuarter.containing(datetime(2026, 12, 31, 20, 0, tzinfo=UTC))  # type: ignore[arg-type]


def test_frozen() -> None:
    with pytest.raises(AttributeError):
        Q3FY27.q = 4  # type: ignore[misc]


_INDEX_MIN = FY_MIN * 4
_INDEX_MAX = FY_MAX * 4 + 3


@st.composite
def _quarter_and_shift(draw: st.DrawFn) -> tuple[FiscalQuarter, int]:
    index = draw(st.integers(min_value=_INDEX_MIN, max_value=_INDEX_MAX))
    n = draw(
        st.integers(
            min_value=max(-40, _INDEX_MIN - index),
            max_value=min(40, _INDEX_MAX - index),
        )
    )
    fy, r = divmod(index, 4)
    return FiscalQuarter(fy=fy, q=r + 1), n


@settings(max_examples=200)
@given(_quarter_and_shift())
def test_roundtrip_properties(case: tuple[FiscalQuarter, int]) -> None:
    quarter, n = case
    assert FiscalQuarter.parse(quarter.label) == quarter
    assert FiscalQuarter.parse(quarter.label.lower()) == quarter
    assert quarter.shift(n).shift(-n) == quarter
    assert FiscalQuarter.containing(quarter.start) == quarter
    assert FiscalQuarter.containing(quarter.end) == quarter
    if quarter < FiscalQuarter(FY_MAX, 4):
        assert quarter.shift(1).start.toordinal() == quarter.end.toordinal() + 1
    if quarter.fy > FY_MIN:
        last_year = quarter.shift(-4)
        assert (last_year.fy, last_year.q) == (quarter.fy - 1, quarter.q)
