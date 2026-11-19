"""LEAK-04: walk-forward folds are keyed on reveal instants, never on row position.

A training row must have been revealed AND labelled strictly before the fold's ``as_of``;
the target never trains itself; a target with too few eligible rows yields no fold.
All calendars here are SYNTHETIC.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime, timedelta

import nowcaster.splits as splits_module
import pytest
from calledit_data.calendar.fiscal import FiscalQuarter
from hypothesis import given
from hypothesis import strategies as st
from nowcaster.splits import Fold, expanding_window_folds

TICKERS = ("AAA", "BBB", "CCC")
FIRST = FiscalQuarter.parse("Q1FY24")
QUARTERS = tuple(FIRST.shift(i) for i in range(12))
ORIGIN = datetime(2024, 1, 1, tzinfo=UTC)


def reveal_of(_: str, quarter: FiscalQuarter) -> datetime:
    """Every ticker reveals the same quarter at the same instant, 10 days after quarter end."""
    return datetime(quarter.end.year, quarter.end.month, quarter.end.day, tzinfo=UTC) + timedelta(
        days=10
    )


def label_of(ticker: str, quarter: FiscalQuarter) -> datetime:
    return reveal_of(ticker, quarter) + timedelta(hours=1)


ALL_ROWS = [(t, q) for t in TICKERS for q in QUARTERS]


def folds(min_train: int = 4) -> list[Fold]:
    return list(expanding_window_folds(ALL_ROWS, reveal_of, label_of, min_train))


def test_training_rows_revealed_strictly_before_cutoff() -> None:
    result = folds()
    assert result, "the fixed calendar must produce folds"
    for fold in result:
        assert fold.as_of == reveal_of(*fold.target)
        for ticker, quarter in fold.train:
            assert reveal_of(ticker, quarter) < fold.as_of
            assert label_of(ticker, quarter) < fold.as_of


def test_target_never_in_own_train_set() -> None:
    for fold in folds():
        assert fold.target not in fold.train
        assert len(set(fold.train)) == len(fold.train)


def test_row_revealed_exactly_at_the_cutoff_is_excluded() -> None:
    """Peers of the same quarter share the target's reveal instant, so they cannot train it."""
    target = ("BBB", QUARTERS[5])
    fold = next(f for f in folds() if f.target == target)
    assert ("AAA", QUARTERS[5]) not in fold.train
    assert ("CCC", QUARTERS[5]) not in fold.train
    assert {q for _, q in fold.train} == set(QUARTERS[:5])  # exactly the earlier quarters


def test_reveal_exactly_at_the_cutoff_is_excluded_even_when_the_label_is_early() -> None:
    """Isolates the reveal condition: the label is long public, only the reveal ties the cutoff."""
    q1, q2 = QUARTERS[0], QUARTERS[1]
    as_of = reveal_of("AAA", q2)

    def reveal(ticker: str, quarter: FiscalQuarter) -> datetime:
        return as_of if (ticker, quarter) == ("CCC", q1) else reveal_of(ticker, quarter)

    def early_label(ticker: str, quarter: FiscalQuarter) -> datetime:
        return datetime(2000, 1, 1, tzinfo=UTC)

    rows = [("AAA", q2), ("BBB", q1), ("CCC", q1)]
    (fold,) = [
        f for f in expanding_window_folds(rows, reveal, early_label, 1) if f.target == ("AAA", q2)
    ]
    assert fold.train == (("BBB", q1),)


def test_label_available_exactly_at_the_cutoff_is_excluded() -> None:
    # CCC Q1 reveals early but its label lands exactly at AAA Q2's as_of.
    q1, q2 = QUARTERS[0], QUARTERS[1]
    as_of = reveal_of("AAA", q2)

    def label(ticker: str, quarter: FiscalQuarter) -> datetime:
        return as_of if (ticker, quarter) == ("CCC", q1) else label_of(ticker, quarter)

    rows = [("AAA", q2), ("BBB", q1), ("CCC", q1)]
    (fold,) = [
        f for f in expanding_window_folds(rows, reveal_of, label, 1) if f.target == ("AAA", q2)
    ]
    assert fold.train == (("BBB", q1),)


def test_target_with_only_three_eligible_rows_yields_no_fold() -> None:
    # In quarter index 1 each target has exactly the 3 quarter-0 rows eligible.
    result = folds(min_train=4)
    targets = {f.target for f in result}
    for ticker in TICKERS:
        assert (ticker, QUARTERS[0]) not in targets  # 0 eligible
        assert (ticker, QUARTERS[1]) not in targets  # 3 eligible
        assert (ticker, QUARTERS[2]) in targets  # 6 eligible
    assert len(result) == 3 * (len(QUARTERS) - 2)
    # with min_train=3 the 3-row targets do get a fold, and it has exactly 3 training rows
    relaxed = {f.target: f for f in folds(min_train=3)}
    assert len(relaxed[("AAA", QUARTERS[1])].train) == 3


def test_folds_are_ordered_by_as_of_then_ticker_then_quarter() -> None:
    result = folds()
    keys = [(f.as_of, f.target[0], f.target[1]) for f in result]
    assert keys == sorted(keys)
    same_instant = [f.target[0] for f in result if f.as_of == result[0].as_of]
    assert same_instant == sorted(same_instant) and len(same_instant) == 3


def test_input_order_does_not_change_the_folds() -> None:
    forward = folds()
    backward = list(expanding_window_folds(ALL_ROWS[::-1], reveal_of, label_of, 4))
    assert forward == backward


def test_target_with_unknown_reveal_gets_no_fold_and_never_trains() -> None:
    unrevealed = ("AAA", QUARTERS[6])

    def reveal(ticker: str, quarter: FiscalQuarter) -> datetime | None:
        return None if (ticker, quarter) == unrevealed else reveal_of(ticker, quarter)

    result = list(expanding_window_folds(ALL_ROWS, reveal, label_of, 4))
    assert unrevealed not in {f.target for f in result}
    assert all(unrevealed not in f.train for f in result)


def test_unlabelled_row_never_trains() -> None:
    unlabelled = ("BBB", QUARTERS[3])

    def label(ticker: str, quarter: FiscalQuarter) -> datetime | None:
        return None if (ticker, quarter) == unlabelled else label_of(ticker, quarter)

    result = list(expanding_window_folds(ALL_ROWS, reveal_of, label, 4))
    assert unlabelled in {f.target for f in result}  # it can still be predicted
    assert all(unlabelled not in f.train for f in result)


def test_naive_datetimes_and_bad_min_train_are_refused() -> None:
    naive = datetime(2024, 1, 1)
    with pytest.raises(ValueError, match="tz-aware"):
        list(expanding_window_folds(ALL_ROWS, lambda t, q: naive, label_of, 1))
    for bad in (0, -1, 2.0, True):
        with pytest.raises(ValueError, match="min_train"):
            list(expanding_window_folds(ALL_ROWS, reveal_of, label_of, bad))  # type: ignore[arg-type]


def test_splitter_uses_no_row_index_split() -> None:
    """LEAK-04 forbids sklearn's index-based splitters; the module must not even import them."""
    tree = ast.parse(inspect.getsource(splits_module))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    imported = {
        alias.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for alias in n.names
    } | {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert "TimeSeriesSplit" not in names | imported
    assert not any(m.startswith("sklearn") for m in imported)


# --- the property over random calendars ---------------------------------------------------

_instant = st.one_of(
    st.none(), st.integers(0, 30).map(lambda h: ORIGIN + timedelta(hours=h))
)  # a small range, so ties at the cutoff are common


@st.composite
def calendars(draw: st.DrawFn) -> tuple[dict, dict, int]:
    reveal: dict = {}
    label: dict = {}
    for ticker in ("A", "B", "C", "D"):
        for i in range(draw(st.integers(0, 8))):
            quarter = FIRST.shift(i)
            reveal[(ticker, quarter)] = draw(_instant)
            label[(ticker, quarter)] = draw(_instant)
    return reveal, label, draw(st.integers(1, 6))


@given(calendars())
def test_fold_invariants_hold_on_random_calendars(
    calendar: tuple[dict, dict, int],
) -> None:
    reveal, label, min_train = calendar
    rows = list(reveal)
    result = list(
        expanding_window_folds(
            rows, lambda t, q: reveal[(t, q)], lambda t, q: label[(t, q)], min_train
        )
    )
    # Oracle: brute force over every ordered pair.
    expected = {}
    for target in rows:
        cutoff = reveal[target]
        if cutoff is None:
            continue
        eligible = {
            r
            for r in rows
            if r != target
            and reveal[r] is not None
            and label[r] is not None
            and reveal[r] < cutoff
            and label[r] < cutoff
        }
        if len(eligible) >= min_train:
            expected[target] = eligible
    assert {f.target for f in result} == set(expected)
    for fold in result:
        assert fold.as_of == reveal[fold.target]
        assert fold.target not in fold.train
        assert set(fold.train) == expected[fold.target]
        assert len(fold.train) >= min_train
        for row in fold.train:
            assert reveal[row] is not None and reveal[row] < fold.as_of
            assert label[row] is not None and label[row] < fold.as_of
    keys = [(f.as_of, f.target[0], f.target[1]) for f in result]
    assert keys == sorted(keys)
