"""The only module allowed to read the wall clock.

The CLI layer calls ``now_utc()`` once per command and passes the instant down; domain code
never reads the clock itself, so every timestamp in a payload is explicit and testable.
"""

from __future__ import annotations

from datetime import UTC, datetime


def now_utc() -> datetime:
    """Current instant, tz-aware UTC, truncated to whole seconds."""
    return datetime.now(UTC).replace(microsecond=0)
