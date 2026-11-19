"""Reveal-keyed expanding-window walk-forward folds (LEAK-04).

``sklearn``'s ``TimeSeriesSplit`` cuts by row index and knows nothing about when a quarter's
number became public, so it cannot be used here. A fold is built the way a live call would
see the world: the target quarter's data cutoff is its early-bound reveal instant
(``as_of = reveal_at_early(target)``, D-27), and a quarter may train the model only if it was
already "usable" at that instant, meaning both

- its own early-bound reveal is strictly before ``as_of``, and
- its label (the reported number) became available strictly before ``as_of``.

Both comparisons are strict ``<``: a quarter revealed at exactly ``as_of`` is not yet known.
The target never trains itself, and peers of the same quarter train only if they were revealed
strictly earlier. A target with fewer than ``min_train`` eligible rows yields no fold at all,
rather than a fold with a short training set. A target whose reveal is unknown (``None``) has
no cutoff and so no fold.

This module is a pure function over callables: it reads no data source (no SQL, no engine),
never reads the clock, and imports neither ``sqlalchemy`` nor ``calledit_data.db``. The
callers pass in point-in-time lookups obtained through ``PointInTimeReader``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime

from calledit_data.calendar.fiscal import FiscalQuarter

Row = tuple[str, FiscalQuarter]
RevealLookup = Callable[[str, FiscalQuarter], datetime | None]


@dataclass(frozen=True)
class Fold:
    """One walk-forward step: predict ``target`` using only ``train``, as of ``as_of``."""

    target: Row
    as_of: datetime
    train: tuple[Row, ...]


def _require_aware(value: datetime, what: str, row: Row) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{what} for {row[0]} {row[1].label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{what} for {row[0]} {row[1].label} must be tz-aware (naive rejected)")
    return value


def expanding_window_folds(
    targets: Iterable[Row],
    reveal_at_early: RevealLookup,
    label_available_at: RevealLookup,
    min_train: int,
) -> Iterator[Fold]:
    """Yield the folds, ordered by ``(as_of, ticker, fiscal_quarter)``.

    ``targets`` is every (ticker, quarter) that may appear as a target or as training data.
    ``reveal_at_early(ticker, quarter)`` is the quarter's early-bound reveal instant, and
    ``label_available_at(ticker, quarter)`` the instant its reported number became public;
    either may return ``None`` for "not known" (never revealed, never reported).
    """
    if type(min_train) is not int or min_train < 1:
        raise ValueError(f"min_train must be an int >= 1 (got {min_train!r})")
    rows = sorted(set(targets), key=lambda r: (r[0], r[1]))

    reveal: dict[Row, datetime] = {}
    label: dict[Row, datetime] = {}
    for row in rows:
        revealed = reveal_at_early(row[0], row[1])
        if revealed is not None:
            reveal[row] = _require_aware(revealed, "reveal_at_early", row)
        labelled = label_available_at(row[0], row[1])
        if labelled is not None:
            label[row] = _require_aware(labelled, "label_available_at", row)

    folds: list[Fold] = []
    for target in rows:
        as_of = reveal.get(target)
        if as_of is None:
            continue
        eligible = [
            row
            for row in rows
            if row != target
            and row in reveal
            and row in label
            and reveal[row] < as_of
            and label[row] < as_of
        ]
        if len(eligible) < min_train:
            continue
        eligible.sort(key=lambda r: (reveal[r], r[0], r[1]))
        folds.append(Fold(target=target, as_of=as_of, train=tuple(eligible)))
    folds.sort(key=lambda f: (f.as_of, f.target[0], f.target[1]))
    yield from folds


__all__ = ["Fold", "RevealLookup", "Row", "expanding_window_folds"]
