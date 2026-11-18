"""``calledit-ledger-v1``: the canonical payload encoding and its SHA-256.

Rules (frozen at the first live write; the JS twin is ``web/src/lib/canonical.ts``):

1. A value is a ``str``, a ``list`` of values, or a ``dict`` whose keys match
   ``^[a-z][a-z0-9_]*$``. Numbers, booleans and null are never allowed.
2. String characters are printable ASCII 0x20-0x7E, excluding double quote and backslash,
   so JSON never needs to escape anything and Python and JS emit identical bytes.
3. Encoding: ``json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True,
   allow_nan=False)``. Keys sort by code point at every level; list order is preserved.
4. ``hash = sha256(utf8(payload_canonical)).hexdigest()``. ``prev_hash`` is a field inside
   the payload; the genesis record (seq 0) has 64 zeros.
5. Formatting: money 2 dp and ratios 6 dp with ROUND_HALF_EVEN (zero is ``0.00``),
   timestamps ``YYYY-MM-DDTHH:MM:SSZ`` (UTC, whole seconds), dates ``YYYY-MM-DD``,
   integers base-10 with no leading zeros. Absent values are the literal ``none``.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any

SCHEME = "calledit-ledger-v1"
GENESIS_PREV_HASH = "0" * 64

_KEY_RE = re.compile(r"[a-z][a-z0-9_]*")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_MONEY_QUANTUM = Decimal("0.01")
_RATIO_QUANTUM = Decimal("0.000001")


class CanonicalError(ValueError):
    """A value is outside the calledit-ledger-v1 domain."""


def _allowed_char(ch: str) -> bool:
    code = ord(ch)
    return 0x20 <= code <= 0x7E and ch not in ('"', "\\")


def validate(value: Any, path: str = "$") -> None:
    """Raise ``CanonicalError`` unless ``value`` is inside the calledit-ledger-v1 domain."""
    if type(value) is str:
        bad = sorted({f"0x{ord(c):02X}" for c in value if not _allowed_char(c)})
        if bad:
            raise CanonicalError(f"{path}: disallowed character(s) {', '.join(bad)}")
    elif type(value) is list:
        for index, item in enumerate(value):
            validate(item, f"{path}[{index}]")
    elif type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or _KEY_RE.fullmatch(key) is None:
                raise CanonicalError(f"{path}: key must match ^[a-z][a-z0-9_]*$")
            validate(item, f"{path}.{key}")
    else:
        raise CanonicalError(f"{path}: {type(value).__name__} not allowed (strings only)")


def canonicalize(value: Any) -> str:
    validate(value)
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def sha256_hex(text: str) -> str:
    if type(text) is not str:
        raise CanonicalError("sha256_hex takes the canonical string")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_hex64(value: Any) -> bool:
    return type(value) is str and _HEX64_RE.fullmatch(value) is not None


def _require_decimal(value: Any, fn: str) -> Decimal:
    if type(value) is not Decimal:
        raise CanonicalError(f"{fn} requires a Decimal (got {type(value).__name__})")
    if not value.is_finite():
        raise CanonicalError(f"{fn} requires a finite Decimal")
    return value


def _format_decimal(value: Decimal, quantum: Decimal) -> str:
    with localcontext() as ctx:
        ctx.prec = 28
        ctx.rounding = ROUND_HALF_EVEN
        quantised = value.quantize(quantum)
    if quantised.is_zero():
        quantised = quantised.copy_abs()
    return format(quantised, "f")


def format_money(value: Decimal) -> str:
    """Rupee crore amount, 2 dp, ROUND_HALF_EVEN (0.125 -> 0.12, 0.135 -> 0.14)."""
    return _format_decimal(_require_decimal(value, "format_money"), _MONEY_QUANTUM)


def format_ratio(value: Decimal) -> str:
    """Ratio such as YoY growth, 6 dp, ROUND_HALF_EVEN."""
    return _format_decimal(_require_decimal(value, "format_ratio"), _RATIO_QUANTUM)


def format_ts(value: datetime) -> str:
    """UTC instant as ``YYYY-MM-DDTHH:MM:SSZ``. Naive or sub-second values are refused."""
    if not isinstance(value, datetime):
        raise CanonicalError(f"format_ts requires a datetime (got {type(value).__name__})")
    if value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalError("format_ts refuses a naive datetime")
    if value.microsecond != 0:
        raise CanonicalError("format_ts refuses sub-second precision (truncate first)")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_date(value: date) -> str:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise CanonicalError(f"format_date requires a date (got {type(value).__name__})")
    return value.isoformat()


def format_int(value: int) -> str:
    if type(value) is not int:
        raise CanonicalError(f"format_int requires an int (got {type(value).__name__})")
    return str(value)
