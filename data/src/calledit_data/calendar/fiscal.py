"""Indian fiscal quarters (FOUND-05).

The Indian financial year FYnn runs from 1 April of year 20nn-1 to 31 March of year 20nn.
Q1 is Apr-Jun, Q2 Jul-Sep, Q3 Oct-Dec and Q4 Jan-Mar, so Q3FY27 is 2026-10-01..2026-12-31
and FY27 is 2026-04-01..2027-03-31.

Labels parse case-insensitively with at most one ASCII space between the parts
(``"q3 fy27"`` == ``"Q3FY27"``) and always render as the canonical ASCII ``Q3FY27``. The two
year digits map to FY2000-FY2099; anything else raises ``ValueError``. No default quarter is
ever returned.

Arithmetic is integer-only. Pure functions: no I/O and no wall clock.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from calledit_data.calendar.tz import IST

FY_MIN = 2000
FY_MAX = 2099

# [0-9] and re.ASCII: Python's \d would accept non-ASCII digits such as Devanagari numerals.
# A literal optional space, not \s, so tabs and newlines are rejected.
_LABEL_RE = re.compile(r"Q([1-4]) ?FY([0-9]{2})", re.IGNORECASE | re.ASCII)

# First month of each quarter. Q1-Q3 fall in calendar year fy-1, Q4 in calendar year fy.
_QUARTER_START_MONTH = {1: 4, 2: 7, 3: 10, 4: 1}


def _check_int(value: object, name: str) -> int:
    if type(value) is not int:  # rejects bool, float, Decimal, str
        raise TypeError(f"{name} must be an int (got {type(value).__name__})")
    return value


@dataclass(frozen=True, order=True)
class FiscalQuarter:
    """A fiscal quarter. ``fy`` is the full ending year (FY27 -> 2027), ``q`` is 1-4.

    Field order (fy, q) makes the generated ordering chronological.
    """

    fy: int
    q: int

    def __post_init__(self) -> None:
        _check_int(self.fy, "fy")
        _check_int(self.q, "q")
        if not FY_MIN <= self.fy <= FY_MAX:
            raise ValueError(f"fiscal year {self.fy} outside FY{FY_MIN}-FY{FY_MAX}")
        if not 1 <= self.q <= 4:
            raise ValueError(f"quarter {self.q} outside 1-4")

    @classmethod
    def parse(cls, label: str) -> FiscalQuarter:
        """Parse ``Q3FY27`` (case-insensitive, one optional space). Anything else raises."""
        if type(label) is not str:
            raise ValueError(f"not a fiscal quarter label: {label!r}")
        match = _LABEL_RE.fullmatch(label)
        if match is None:
            raise ValueError(f"not a fiscal quarter label: {label!r} (expected e.g. 'Q3FY27')")
        return cls(fy=FY_MIN + int(match.group(2)), q=int(match.group(1)))

    @classmethod
    def containing(cls, d: date) -> FiscalQuarter:
        """The quarter that contains calendar date ``d``."""
        if type(d) is not date:
            raise TypeError(f"containing() requires a date, not {type(d).__name__}")
        if d.month >= 4:
            return cls(fy=d.year + 1, q=(d.month - 4) // 3 + 1)
        return cls(fy=d.year, q=4)

    @property
    def label(self) -> str:
        return f"Q{self.q}FY{self.fy % 100:02d}"

    @property
    def start(self) -> date:
        month = _QUARTER_START_MONTH[self.q]
        year = self.fy if self.q == 4 else self.fy - 1
        return date(year, month, 1)

    @property
    def end(self) -> date:
        first = self.start
        month = first.month + 2
        return date(first.year, month, calendar.monthrange(first.year, month)[1])

    @property
    def period_start_utc(self) -> datetime:
        """The first instant of the quarter (start date 00:00 IST), as UTC."""
        return datetime.combine(self.start, time(0, 0, 0), IST).astimezone(UTC)

    def shift(self, n: int) -> FiscalQuarter:
        """The quarter ``n`` quarters later (negative: earlier). ``shift(-4)`` is t-4."""
        _check_int(n, "n")
        fy, index = divmod(self.fy * 4 + (self.q - 1) + n, 4)
        return FiscalQuarter(fy=fy, q=index + 1)

    def __str__(self) -> str:
        return self.label
