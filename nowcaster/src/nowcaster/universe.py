"""The company universe: ``config/universe.toml`` loaded into strict pydantic models.

FOUND-03: one config file decides which companies are locked. ``Universe.enabled()`` is the
only list the lock iterates, so ``enabled = false`` drops a company with no code change.
PIT-05 (config half): structural breaks are declared here, as a quarter range for Eternal's
Blinkit inventory transition (D-06) and as a date for GST 2.0 (D-07).

``universe_sha256`` is the SHA-256 of the exact file bytes that were parsed, so every rules
and prediction record that carries it pins the config (threat T-01-11).

Validation is strict: unknown keys are refused, ints and bools are never coerced from
strings, and every string must be inside the calledit-ledger-v1 charset because these values
end up in hashed payloads.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal

from calledit_data.calendar.fiscal import FiscalQuarter
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from nowcaster.ledger.canonical import CanonicalError, validate

SCHEMA_VERSION = "universe-1"
WILDCARD = "*"

_TICKER_RE = re.compile(r"[A-Z][A-Z0-9]{1,15}", re.ASCII)
_ISIN_RE = re.compile(r"IN[A-Z0-9]{9}[0-9]", re.ASCII)
_STATE_RE = re.compile(r"[A-Z]{2}", re.ASCII)
_APPLE_ID_RE = re.compile(r"[1-9][0-9]{5,11}", re.ASCII)
_PLAY_ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+", re.ASCII)
_BREAK_ID_RE = re.compile(r"[a-z0-9][a-z0-9.-]{0,63}", re.ASCII)
_ISO_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)


class UniverseError(ValueError):
    """The universe config cannot be read or does not validate."""


def _ledger_safe(value: str) -> str:
    try:
        validate(value)
    except CanonicalError as exc:
        raise ValueError(f"not ledger-safe text ({exc})") from None
    if not value.strip():
        raise ValueError("must not be empty")
    if value != value.strip():
        raise ValueError("must not have leading or trailing whitespace")
    return value


def _matching(pattern: re.Pattern[str], what: str) -> Any:
    def check(value: str) -> str:
        if pattern.fullmatch(value) is None:
            raise ValueError(f"{what} must match ^{pattern.pattern}$ (got {value!r})")
        return value

    return check


def _isin_check_digit_ok(isin: str) -> bool:
    """ISO 6166 check digit: letters -> 10..35, then the Luhn algorithm over the digits."""
    digits = "".join(str(int(ch, 36)) for ch in isin[:-1])
    total = 0
    for index, ch in enumerate(reversed(digits)):
        value = int(ch)
        if index % 2 == 0:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return (10 - total % 10) % 10 == int(isin[-1])


def _check_isin(value: str) -> str:
    _matching(_ISIN_RE, "isin")(value)
    if not _isin_check_digit_ok(value):
        raise ValueError(f"isin {value!r} fails the ISO 6166 check digit")
    return value


def _strict_date(value: Any) -> date:
    """A TOML date (``2025-09-22``) or a ``"YYYY-MM-DD"`` string; nothing else."""
    if type(value) is date:
        return value
    if type(value) is str and _ISO_DATE_RE.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError(f"expected a YYYY-MM-DD date (got {value!r})")


def _canonical_quarter(value: str) -> str:
    quarter = FiscalQuarter.parse(value)
    if quarter.label != value:
        raise ValueError(f"write the quarter as {quarter.label!r} (got {value!r})")
    return value


def _https(value: str) -> str:
    if not value.startswith("https://") or len(value) <= len("https://"):
        raise ValueError(f"source_url must be https (got {value!r})")
    return value


Text = Annotated[StrictStr, AfterValidator(_ledger_safe)]
Ticker = Annotated[StrictStr, AfterValidator(_matching(_TICKER_RE, "ticker"))]
Isin = Annotated[StrictStr, AfterValidator(_check_isin)]
StateCode = Annotated[StrictStr, AfterValidator(_matching(_STATE_RE, "gst state"))]
AppleId = Annotated[StrictStr, AfterValidator(_matching(_APPLE_ID_RE, "apple app id"))]
PlayId = Annotated[StrictStr, AfterValidator(_matching(_PLAY_ID_RE, "play package id"))]
BreakId = Annotated[StrictStr, AfterValidator(_matching(_BREAK_ID_RE, "break id"))]
QuarterLabel = Annotated[StrictStr, AfterValidator(_canonical_quarter)]
HttpsUrl = Annotated[Text, AfterValidator(_https)]
StrictDate = Annotated[date, BeforeValidator(_strict_date)]


def _unique(values: tuple[str, ...], what: str) -> tuple[str, ...]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for value in values:
        (repeated if value in seen else seen).add(value)
    dupes = sorted(repeated)
    if dupes:
        raise ValueError(f"duplicate {what}: {', '.join(dupes)}")
    return values


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SymbolHistory(_Model):
    """A former exchange symbol, valid up to and including ``until`` (ZOMATO -> ETERNAL)."""

    symbol: Ticker
    until: StrictDate


class Company(_Model):
    ticker: Ticker
    isin: Isin
    isin_confirmed: StrictBool
    name: Text
    enabled: StrictBool
    revenue_basis: Literal["consolidated_revenue_from_operations"]
    reveal_offset_days: Annotated[StrictInt, Field(ge=0, le=30)]
    has_business_update: StrictBool
    gst_states: tuple[StateCode, ...]
    gst_states_basis: Text
    trends_terms: tuple[Text, ...]
    apple_app_ids: tuple[AppleId, ...]
    play_package_ids: tuple[PlayId, ...]
    labels: tuple[Text, ...]
    symbol_history: tuple[SymbolHistory, ...] = ()
    break_ids: tuple[BreakId, ...]

    @field_validator(
        "gst_states", "trends_terms", "apple_app_ids", "play_package_ids", "labels", "break_ids"
    )
    @classmethod
    def _no_duplicates(cls, value: tuple[str, ...], info: ValidationInfo) -> tuple[str, ...]:
        return _unique(value, info.field_name or "values")


class Break(_Model):
    id: BreakId
    kind: Literal["quarter_range", "date"]
    applies_to: Annotated[tuple[StrictStr, ...], Field(min_length=1)]
    start_q: QuarterLabel | None = None
    end_q: QuarterLabel | None = None
    effective: StrictDate | None = None
    source_url: HttpsUrl
    source_note: Text
    confirmed: StrictBool

    @field_validator("applies_to")
    @classmethod
    def _check_applies_to(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _unique(value, "applies_to")
        if WILDCARD in value and len(value) != 1:
            raise ValueError("applies_to with '*' must not list tickers as well")
        for item in value:
            if item != WILDCARD and _TICKER_RE.fullmatch(item) is None:
                raise ValueError(f"applies_to entries are tickers or '*' (got {item!r})")
        return value

    @model_validator(mode="after")
    def _check_kind(self) -> Break:
        if self.kind == "quarter_range":
            if self.start_q is None or self.end_q is None:
                raise ValueError(f"break {self.id}: quarter_range needs start_q and end_q")
            if self.effective is not None:
                raise ValueError(f"break {self.id}: quarter_range takes no effective date")
            if FiscalQuarter.parse(self.start_q) > FiscalQuarter.parse(self.end_q):
                raise ValueError(
                    f"break {self.id}: start_q {self.start_q} is after end_q {self.end_q}"
                )
        else:
            if self.effective is None:
                raise ValueError(f"break {self.id}: a date break needs effective")
            if self.start_q is not None or self.end_q is not None:
                raise ValueError(f"break {self.id}: a date break takes no start_q/end_q")
        return self

    @property
    def start_quarter(self) -> FiscalQuarter | None:
        return None if self.start_q is None else FiscalQuarter.parse(self.start_q)

    @property
    def end_quarter(self) -> FiscalQuarter | None:
        return None if self.end_q is None else FiscalQuarter.parse(self.end_q)

    def applies(self, ticker: str) -> bool:
        return WILDCARD in self.applies_to or ticker in self.applies_to


class Universe(_Model):
    schema_version: Literal["universe-1"]
    basis_note: Text
    companies: Annotated[tuple[Company, ...], Field(min_length=1)]
    breaks: tuple[Break, ...] = ()
    universe_sha256: Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def _check_references(self) -> Universe:
        _unique(tuple(c.ticker for c in self.companies), "ticker")
        _unique(tuple(c.isin for c in self.companies), "isin")
        _unique(tuple(b.id for b in self.breaks), "break id")
        tickers = {c.ticker for c in self.companies}
        by_id = {b.id: b for b in self.breaks}
        for brk in self.breaks:
            unknown = sorted(set(brk.applies_to) - tickers - {WILDCARD})
            if unknown:
                raise ValueError(f"break {brk.id} applies to unknown ticker(s): {unknown}")
        for company in self.companies:
            for break_id in company.break_ids:
                brk = by_id.get(break_id)
                if brk is None:
                    raise ValueError(f"{company.ticker}: unknown break id {break_id!r}")
                if not brk.applies(company.ticker):
                    raise ValueError(
                        f"{company.ticker}: break {break_id} does not apply to it (applies_to)"
                    )
            # The reverse direction: a break that applies must be listed, so no company can
            # silently miss one.
            missing = [b.id for b in self.breaks if b.applies(company.ticker)]
            missing = [b for b in missing if b not in company.break_ids]
            if missing:
                raise ValueError(f"{company.ticker}: break_ids is missing {missing}")
        return self

    def enabled(self) -> tuple[Company, ...]:
        """The companies the lock iterates, in config order."""
        return tuple(c for c in self.companies if c.enabled)

    def unconfirmed(self) -> tuple[str, ...]:
        """Unconfirmed values that a live write would hash permanently (T-01-28).

        Only enabled companies count: an ISIN with ``isin_confirmed = false``, and every break
        with ``confirmed = false`` that applies to an enabled company. Sorted, de-duplicated.
        """
        problems: set[str] = set()
        for company in self.enabled():
            if not company.isin_confirmed:
                problems.add(f"{company.ticker}: isin_confirmed is false")
            for brk in self.breaks_for(company.ticker):
                if not brk.confirmed:
                    problems.add(
                        f"break {brk.id} (applies to {company.ticker}): confirmed is false"
                    )
        return tuple(sorted(problems))

    def company(self, ticker: str) -> Company:
        for company in self.companies:
            if company.ticker == ticker:
                return company
        raise KeyError(f"unknown ticker {ticker!r}")

    def breaks_for(self, ticker: str) -> tuple[Break, ...]:
        """The breaks the company lists, in the order of ``company.break_ids``."""
        by_id = {b.id: b for b in self.breaks}
        return tuple(by_id[b] for b in self.company(ticker).break_ids)


def parse_universe(data: bytes) -> Universe:
    """Validate universe TOML bytes. ``universe_sha256`` is the SHA-256 of ``data``."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise UniverseError("universe config is not valid UTF-8") from None
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise UniverseError(f"universe config is not valid TOML: {exc}") from None
    if "universe_sha256" in raw:
        raise UniverseError("universe_sha256 is computed from the file bytes, never written")
    raw["universe_sha256"] = hashlib.sha256(data).hexdigest()
    try:
        return Universe.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'universe'}: {err['msg']}"
            for err in exc.errors()
        )
        raise UniverseError(f"universe config does not validate: {problems}") from None


def load_universe(path: Path) -> Universe:
    """Read ``path`` once and validate those exact bytes."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        raise UniverseError(f"universe config not readable: {Path(path).as_posix()}") from None
    return parse_universe(data)
