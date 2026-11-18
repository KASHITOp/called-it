"""The naive baseline: same quarter last year, grown by trailing-twelve-month YoY (BASE-01).

Rules (user-settled, D-04..D-08; frozen into PREREGISTRATION.md and hashed at seq 0):

- For target quarter Q the eight needed quarters are Q-8..Q-1. SQLY (same quarter last year)
  is Q-4. TTM growth is ``g = sum(Q-4..Q-1) / sum(Q-8..Q-5) - 1`` and the point estimate is
  ``SQLY x (1 + g)``, computed in exact ``Decimal`` (prec 28, ROUND_HALF_EVEN) from the
  UNROUNDED ``g`` and quantised once, to 0.01 INR crore.
- A quarter is usable only if the point-in-time reader returns its consolidated-revenue
  observation (so ``available_at < as_of``) and the observation is a verified seed row
  (``source_kind == "seed_csv"``). The latest vintage the reader returns is used (D-05).
- Any needed quarter that is missing or unverified makes the company REFUSED, listing every
  affected quarter. Nothing is imputed, interpolated or carried forward (D-08).
- Break-aware (D-06): if a quarter-range break puts any window quarter inside the range, or
  the window straddles it, TTM growth is replaced by a single YoY pair ``(t, t-4)``: the
  latest pair with both quarters after the break, else the most recent pair (Q-1, Q-5)
  (``least_straddling``). Whenever any pair is post-break, (Q-1, Q-5) is one, so both
  branches pick (Q-1, Q-5); ``pair_status`` is what tells them apart.
- A date break (GST 2.0) is only reported in ``breaks_in_window``; it never changes the
  arithmetic (D-07).
- Eternal's result always carries the label ``ETERNAL_LABEL`` (D-06).
- A non-positive denominator is refused (``invalid_base_sum``), never divided.

This module reads data only through ``PointInTimeReader`` (no SQL, no engine) and never reads
the clock: the instant is ``reader.as_of``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any

from calledit_data.calendar.fiscal import FiscalQuarter
from calledit_data.pit.reader import Observation, PointInTimeReader

from nowcaster.ledger.canonical import (
    canonicalize,
    format_date,
    format_money,
    format_ratio,
    format_ts,
    sha256_hex,
)
from nowcaster.universe import Break, Company

MODEL_VERSION = "baseline-sqly@1.0.0"
SNAPSHOT_SCHEME = "calledit-snapshot-v1"
ETERNAL_TICKER = "ETERNAL"
ETERNAL_LABEL = "low confidence: post-break comparables limited"

METHOD_TTM = "ttm_yoy"
METHOD_PAIR = "break_single_pair"
PAIR_NONE = "none"
PAIR_POST_BREAK = "post_break"
PAIR_LEAST_STRADDLING = "least_straddling"

REASON_MISSING = "missing_seed_quarter"
REASON_UNVERIFIED = "unverified_seed_quarter"
REASON_INVALID_BASE = "invalid_base_sum"

VERIFIED_SOURCE_KIND = "seed_csv"
UNVERIFIED_SOURCE_KIND = "seed_csv_unverified"

WINDOW_QUARTERS = 8
_CENT = Decimal("0.01")
_NONE = "none"
_JOIN = "|"


@dataclass(frozen=True)
class BaselineResult:
    ticker: str
    fiscal_quarter: str
    as_of: datetime
    method: str
    pair_status: str
    point: Decimal
    growth: Decimal
    growth_str: str
    sqly_quarter: str
    window_quarters: tuple[str, ...]
    pair: tuple[str, str] | None
    labels: tuple[str, ...]
    breaks_in_window: tuple[str, ...]
    inputs: tuple[Observation, ...]
    snapshot: dict[str, Any]
    snapshot_canonical: str
    snapshot_sha256: str


@dataclass(frozen=True)
class BaselineRefusal:
    ticker: str
    fiscal_quarter: str
    as_of: datetime
    reason_code: str
    missing_quarters: tuple[str, ...]


def window_for(quarter: FiscalQuarter) -> tuple[FiscalQuarter, ...]:
    """The eight needed quarters Q-8..Q-1, oldest first."""
    return tuple(quarter.shift(-k) for k in range(WINDOW_QUARTERS, 0, -1))


def _joined(values: Sequence[str]) -> str:
    return _JOIN.join(values) if values else _NONE


def _breaks_in_window(
    ticker: str, breaks: Sequence[Break], window: tuple[FiscalQuarter, ...]
) -> tuple[str, ...]:
    first, last = window[0], window[-1]
    found: set[str] = set()
    for brk in breaks:
        if not brk.applies(ticker):
            continue
        if brk.kind == "date":
            assert brk.effective is not None
            if first.start <= brk.effective <= last.end:
                found.add(brk.id)
        else:
            start, end = brk.start_quarter, brk.end_quarter
            assert start is not None and end is not None
            if start <= last and end >= first:
                found.add(brk.id)
    return tuple(sorted(found))


def _break_status(quarter: FiscalQuarter, brk: Break) -> str:
    start, end = brk.start_quarter, brk.end_quarter
    assert start is not None and end is not None
    if quarter < start:
        return "pre"
    if quarter > end:
        return "post"
    return "in"


def _uses_break_method(window: tuple[FiscalQuarter, ...], ranges: Sequence[Break]) -> bool:
    """D-06: a quarter inside a break range, or a window that mixes pre and post."""
    for brk in ranges:
        statuses = {_break_status(q, brk) for q in window}
        if "in" in statuses or {"pre", "post"} <= statuses:
            return True
    return False


def _is_post_post(t: FiscalQuarter, base: FiscalQuarter, ranges: Sequence[Break]) -> bool:
    return all(_break_status(q, brk) == "post" for brk in ranges for q in (t, base))


def _input_row(label: str, obs: Observation) -> dict[str, str]:
    return {
        "fiscal_quarter": label,
        "period_date": format_date(obs.period_date),
        "value_inr_cr": format_money(obs.value),
        "available_at": format_ts(obs.available_at),
        "availability_basis": obs.availability_basis,
        "vintage": obs.vintage,
        "source_ref": obs.source_ref,
        "content_hash": obs.content_hash,
    }


def _labels_for(company: Company) -> tuple[str, ...]:
    labels = company.labels
    # D-06: Eternal's result must never lose its label, even if the config is edited.
    if company.ticker == ETERNAL_TICKER and ETERNAL_LABEL not in labels:
        labels = (*labels, ETERNAL_LABEL)
    return labels


def compute_baseline(
    company: Company,
    quarter: FiscalQuarter,
    reader: PointInTimeReader,
    breaks: Sequence[Break],
) -> BaselineResult | BaselineRefusal:
    """The baseline for ``company`` and target ``quarter`` as knowable at ``reader.as_of``."""
    ticker = company.ticker
    as_of = reader.as_of
    window = window_for(quarter)
    labels_of_window = tuple(q.label for q in window)

    by_period = {obs.period_date: obs for obs in reader.series(f"rev.consolidated.{ticker}")}
    missing: list[str] = []
    unverified: list[str] = []
    usable: dict[FiscalQuarter, Observation] = {}
    for q in window:
        obs = by_period.get(q.end)
        if obs is None:
            missing.append(q.label)
            continue
        if type(obs.value) is not Decimal:
            raise TypeError(
                f"{ticker} {q.label}: observation value must be a Decimal "
                f"(got {type(obs.value).__name__}); the baseline has no binary-float path"
            )
        if obs.source_kind != VERIFIED_SOURCE_KIND:
            unverified.append(q.label)
            continue
        usable[q] = obs
    if missing or unverified:
        refused = set(missing) | set(unverified)
        return BaselineRefusal(
            ticker=ticker,
            fiscal_quarter=quarter.label,
            as_of=as_of,
            reason_code=REASON_MISSING if missing else REASON_UNVERIFIED,
            missing_quarters=tuple(label for label in labels_of_window if label in refused),
        )

    value = {q: usable[q].value for q in window}
    sqly_q = quarter.shift(-4)
    ranges = tuple(b for b in breaks if b.applies(ticker) and b.kind == "quarter_range")

    method = METHOD_TTM
    pair_status = PAIR_NONE
    pair: tuple[FiscalQuarter, FiscalQuarter] | None = None
    sum_recent: Decimal | None = None
    sum_prior: Decimal | None = None

    if _uses_break_method(window, ranges):
        method = METHOD_PAIR
        pair_status = PAIR_LEAST_STRADDLING
        pair = (quarter.shift(-1), quarter.shift(-5))
        for k in range(1, 5):
            t, base = quarter.shift(-k), quarter.shift(-k - 4)
            if _is_post_post(t, base, ranges):
                pair, pair_status = (t, base), PAIR_POST_BREAK
                break

    with localcontext() as ctx:
        ctx.prec = 28
        ctx.rounding = ROUND_HALF_EVEN
        if pair is None:
            sum_recent = sum((value[q] for q in window[4:]), Decimal(0))
            sum_prior = sum((value[q] for q in window[:4]), Decimal(0))
            numerator, denominator = sum_recent, sum_prior
            denominator_quarters = labels_of_window[:4]
        else:
            numerator, denominator = value[pair[0]], value[pair[1]]
            denominator_quarters = (pair[1].label,)
        if denominator <= 0:
            return BaselineRefusal(
                ticker=ticker,
                fiscal_quarter=quarter.label,
                as_of=as_of,
                reason_code=REASON_INVALID_BASE,
                missing_quarters=tuple(denominator_quarters),
            )
        growth = numerator / denominator - 1
        point = (value[sqly_q] * (1 + growth)).quantize(_CENT, rounding=ROUND_HALF_EVEN)

    labels = _labels_for(company)
    breaks_found = _breaks_in_window(ticker, breaks, window)
    inputs = tuple(usable[q] for q in window)  # window order is period_date order
    growth_str = format_ratio(growth)
    snapshot: dict[str, Any] = {
        "scheme": SNAPSHOT_SCHEME,
        "ticker": ticker,
        "fiscal_quarter": quarter.label,
        "as_of": format_ts(as_of),
        "model_version": MODEL_VERSION,
        "method": method,
        "sqly_quarter": sqly_q.label,
        "window_quarters": _joined(labels_of_window),
        "pair_t": _NONE if pair is None else pair[0].label,
        "pair_base": _NONE if pair is None else pair[1].label,
        "pair_status": pair_status,
        "sum_recent_inr_cr": _NONE if sum_recent is None else format_money(sum_recent),
        "sum_prior_inr_cr": _NONE if sum_prior is None else format_money(sum_prior),
        "growth": growth_str,
        "point_inr_cr": format_money(point),
        "labels": _joined(labels),
        "breaks_in_window": _joined(breaks_found),
        "inputs": [_input_row(q.label, usable[q]) for q in window],
    }
    canonical = canonicalize(snapshot)
    return BaselineResult(
        ticker=ticker,
        fiscal_quarter=quarter.label,
        as_of=as_of,
        method=method,
        pair_status=pair_status,
        point=point,
        growth=growth,
        growth_str=growth_str,
        sqly_quarter=sqly_q.label,
        window_quarters=labels_of_window,
        pair=None if pair is None else (pair[0].label, pair[1].label),
        labels=labels,
        breaks_in_window=breaks_found,
        inputs=inputs,
        snapshot=snapshot,
        snapshot_canonical=canonical,
        snapshot_sha256=sha256_hex(canonical),
    )
