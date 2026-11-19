"""Documented process exit codes for ``nowcast predict`` (D-17, Open Q6).

``EXIT_OK`` (0)
    Every enabled company was locked with a prediction record.
``EXIT_PARTIAL`` (3)
    At least one record was appended, but some company got a gap record (missing or unverified
    seed quarter, D-08) or was refused by the lock guard (deadline, reveal event, D-14/D-27).
    The records that were appended are real and stay in the chain.
``EXIT_REFUSED`` (4)
    Nothing was appended because the guard refused: the quarter is not live, every company is
    past its deadline, the rules record is missing or stale, or the live context is not
    GitHub Actions on main with a confirmed universe.
``EXIT_ENV`` (5)
    The environment failed: the database is unreachable or unusable (no silent SQLite
    fallback, D-17), or the live database self-check failed.

Code 1 is left to the interpreter (uncaught error) and 2 to the command-line parser.
"""

from __future__ import annotations

EXIT_OK = 0
EXIT_PARTIAL = 3
EXIT_REFUSED = 4
EXIT_ENV = 5

EXIT_CODE_HELP = (
    "Exit codes: 0 every enabled company locked; "
    "3 some records appended but a company got a gap or was refused; "
    "4 nothing appended because the lock guard refused; "
    "5 environment or database failure."
)
