"""Portable column types.

- ``UTCDateTime``: tz-aware UTC instants. SQLite stores fixed-width ISO text
  (``%Y-%m-%dT%H:%M:%S.%fZ``) so text order equals time order; Postgres uses timestamptz.
  Naive datetimes are rejected: a naive/aware mix in ``available_at < reveal_at`` is a
  leakage bug.
- ``DecimalText(scale)``: exact decimals. SQLite stores TEXT quantised to ``scale``;
  Postgres uses ``NUMERIC(20, scale)``. Values always come back as ``Decimal``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any

import sqlalchemy as sa

_SQLITE_TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class UTCDateTime(sa.types.TypeDecorator):
    impl = sa.String(27)
    cache_ok = True

    def load_dialect_impl(self, dialect: sa.Dialect) -> sa.types.TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(sa.DateTime(timezone=True))
        return dialect.type_descriptor(sa.String(27))

    def process_bind_param(self, value: Any, dialect: sa.Dialect) -> Any:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError("UTCDateTime requires a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("naive datetime rejected (UTCDateTime needs tz-aware input)")
        value = value.astimezone(UTC)
        if dialect.name == "postgresql":
            return value
        return value.strftime(_SQLITE_TS_FORMAT)

    def process_result_value(self, value: Any, dialect: sa.Dialect) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, str):
            return datetime.strptime(value, _SQLITE_TS_FORMAT).replace(tzinfo=UTC)
        if value.tzinfo is None:
            raise ValueError("database returned a naive timestamp")
        return value.astimezone(UTC)


class DecimalText(sa.types.TypeDecorator):
    impl = sa.String(40)
    cache_ok = True

    def __init__(self, scale: int) -> None:
        super().__init__()
        if not isinstance(scale, int) or isinstance(scale, bool) or not 0 <= scale <= 10:
            raise ValueError("DecimalText scale must be an int in 0..10")
        self.scale = scale

    def _quantise(self, value: Decimal) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 28
            ctx.rounding = ROUND_HALF_EVEN
            quantised = value.quantize(Decimal(1).scaleb(-self.scale))
        if quantised.is_zero():
            quantised = quantised.copy_abs()
        return quantised

    def load_dialect_impl(self, dialect: sa.Dialect) -> sa.types.TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(sa.Numeric(20, self.scale, asdecimal=True))
        return dialect.type_descriptor(sa.String(40))

    def process_bind_param(self, value: Any, dialect: sa.Dialect) -> Any:
        if value is None:
            return None
        if not isinstance(value, Decimal):
            raise TypeError("DecimalText requires a Decimal (floats and ints are rejected)")
        if not value.is_finite():
            raise ValueError("DecimalText requires a finite Decimal")
        quantised = self._quantise(value)
        if dialect.name == "postgresql":
            return quantised
        return format(quantised, "f")

    def process_result_value(self, value: Any, dialect: sa.Dialect) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, float):
            raise TypeError("database returned a float for a DecimalText column")
        return self._quantise(Decimal(value))
