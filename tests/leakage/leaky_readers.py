"""Four deliberately leaky ``PointInTimeReader`` subclasses.

They exist ONLY to prove the leakage suite can fail (ROADMAP success criterion 3, LEAK-02):
``pytest tests/leakage --reader=<variant>`` must exit with code 1 for every one of them, and
``tests/meta`` asserts exactly that. Each reader is wrong in exactly one way.

They must never be imported by ``src/`` code. Nothing under ``data/src`` or ``nowcaster/src``
may reference this module, and the production reader is untouched: the leaks live entirely in
these subclasses' overrides of the ``_row_filter`` and ``_postcondition`` hooks.
"""

from __future__ import annotations

import sqlalchemy as sa
from calledit_data.pit.reader import Observation, PointInTimeReader, RevealEvent

_TIME_COLUMN = {"observations": "available_at", "reveal_events": "event_at"}


def _known_at(table: sa.Table) -> sa.ColumnElement:
    return table.c[_TIME_COLUMN[table.name]]


class LeakyLEReader(PointInTimeReader):
    """Off-by-one: ``available_at <= as_of`` instead of ``<``. A row at exactly T leaks."""

    def _row_filter(self, table: sa.Table) -> sa.ColumnElement[bool]:
        clause = _known_at(table) <= self.as_of
        if self.mode == "live":
            clause = sa.and_(clause, table.c.ingested_at <= self.as_of)
        return clause

    def _postcondition(self, rows: tuple[Observation, ...] | tuple[RevealEvent, ...]) -> None:
        return None  # the relaxed post-condition (<=) can never fire on the relaxed filter


class NoFilterReader(PointInTimeReader):
    """No availability filter at all: every row ever stored is returned."""

    def _row_filter(self, table: sa.Table) -> sa.ColumnElement[bool]:
        return sa.true()

    def _postcondition(self, rows: tuple[Observation, ...] | tuple[RevealEvent, ...]) -> None:
        return None


class PeriodFilterReader(PointInTimeReader):
    """Filters on the period instead of the availability: ``period_date < as_of.date()``.

    A quarter that has ended is treated as known, although its filing may come weeks later.
    """

    def _row_filter(self, table: sa.Table) -> sa.ColumnElement[bool]:
        if table.name == "observations":
            return table.c.period_date < self.as_of.date()
        return sa.true()

    def _postcondition(self, rows: tuple[Observation, ...] | tuple[RevealEvent, ...]) -> None:
        return None


class IgnoreIngestedReader(PointInTimeReader):
    """Live mode that ignores ``ingested_at``: a value loaded after the instant leaks in."""

    def _row_filter(self, table: sa.Table) -> sa.ColumnElement[bool]:
        return _known_at(table) < self.as_of

    def _postcondition(self, rows: tuple[Observation, ...] | tuple[RevealEvent, ...]) -> None:
        # Checks available_at only, so a live row ingested after as_of passes unnoticed.
        offending = [row for row in rows if not row.known_at < self.as_of]
        if offending:
            raise AssertionError(f"{len(offending)} row(s) not available at as_of")


LEAKY_READERS: dict[str, type[PointInTimeReader]] = {
    "leaky-le": LeakyLEReader,
    "leaky-nofilter": NoFilterReader,
    "leaky-period": PeriodFilterReader,
    "leaky-ingested": IgnoreIngestedReader,
}
