"""LEAK-01: the future-perturbation invariance property (the flagship leakage test).

For a random store and a random cutoff T, change only what is NOT knowable at T and the
baseline at T must not move by a byte:

- backtest mode: rows with ``available_at >= T`` may be mutated (value -> 999999999.99),
  deleted, or joined by new rows, including rows at exactly T and at T + 1 s. Rows known
  before T may have only their ``ingested_at`` changed (the reader must not care in backtest).
- live mode: additionally, rows with ``ingested_at > T`` are fair game.

``compute_baseline`` must then return an identical point and a byte-identical canonical
snapshot, or an identical refusal. A reader that consults any information from after T makes
this fail. The explicit ``@example`` cases make each deliberately leaky reader fail
deterministically, without depending on hypothesis finding the case.

Ties (decision of 24 Nov 2026): two visible vintages of one period with the SAME
``available_at`` and different values are refused (``TiedVintageError``, reason
``tied_available_at``), never ordered by ``ingested_at``. The strategy therefore never shares an
``available_at`` between restatements; the refusal itself is covered in test_reader.py.

All values are SYNTHETIC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from calledit_data.calendar.fiscal import FiscalQuarter
from calledit_data.pit.reader import PointInTimeReader
from calledit_data.store.writer import ObservationIn
from hypothesis import example, given
from hypothesis import strategies as st
from nowcaster.baseline import BaselineRefusal, BaselineResult, compute_baseline
from nowcaster.universe import Universe, load_universe

from tests.conftest import REPO_ROOT
from tests.leakage.store_helpers import SENTINEL, add_stamped, fresh_store

UNIVERSE: Universe = load_universe(REPO_ROOT / "config" / "universe.toml")
TICKERS = tuple(c.ticker for c in UNIVERSE.enabled())
TARGET = FiscalQuarter.parse("Q3FY27")
DAY = 86_400
CUTOFF_ORIGIN = datetime(2026, 10, 1, tzinfo=UTC)
BASIS = "exchange_timestamp"
ACTIONS = ("keep", "mutate", "delete", "reingest")


@dataclass(frozen=True)
class RowSpec:
    q_idx: int  # 0 = oldest of the n quarters before the target
    value: Decimal
    available_at: datetime
    ingested_at: datetime
    vintage: str
    action: str  # what the perturbed store does to this row, when it may


@dataclass(frozen=True)
class NewSpec:
    q_idx: int
    kind: str  # "future": available_at >= T; "late_ingest": known before T, loaded after T
    offset_s: int
    vintage: str


@dataclass(frozen=True)
class Case:
    ticker: str
    n_prior: int
    cutoff: datetime
    rows: tuple[RowSpec, ...]
    new_rows: tuple[NewSpec, ...]


def _quarter(case: Case, q_idx: int) -> FiscalQuarter:
    return TARGET.shift(-(case.n_prior - q_idx))


def _money() -> st.SearchStrategy[Decimal]:
    return st.decimals(
        min_value=Decimal("1000.00"),
        max_value=Decimal("50000.00"),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    )


@st.composite
def cases(draw: st.DrawFn) -> Case:
    ticker = draw(st.sampled_from(TICKERS))
    n_prior = draw(st.integers(min_value=8, max_value=16))
    case_shell = Case(ticker, n_prior, CUTOFF_ORIGIN, (), ())
    rows: list[RowSpec] = []
    for q_idx in range(n_prior):
        period_end = datetime.combine(_quarter(case_shell, q_idx).end, time(), UTC)
        available = period_end + timedelta(seconds=draw(st.integers(3 * DAY, 60 * DAY)))
        ingested = available + timedelta(seconds=draw(st.integers(0, 30 * DAY)))
        rows.append(
            RowSpec(
                q_idx,
                draw(_money()),
                available,
                ingested,
                "first_reported",
                draw(st.sampled_from(ACTIONS)),
            )
        )
    restatements = draw(
        st.lists(
            st.tuples(
                st.integers(0, n_prior - 1),  # quarter
                st.integers(1, 120),  # days after the first report; unique per quarter
                _money(),
                st.integers(0, 30 * DAY),  # ingestion lag
                st.sampled_from(ACTIONS),
            ),
            max_size=6,
            unique_by=lambda t: (t[0], t[1]),
        )
    )
    for q_idx, days, value, lag, action in restatements:
        first = rows[q_idx].available_at
        available = first + timedelta(days=days)
        rows.append(
            RowSpec(q_idx, value, available, available + timedelta(seconds=lag), "restated", action)
        )
    # Anchor the cutoff on the latest first report (or any first report, one time in four), so
    # most examples have a complete window (a baseline) and the rest refuse; offsets of 0 and
    # +-1 s sit exactly on the boundary.
    first_reports = [r.available_at for r in rows]
    anchor = max(first_reports)
    if draw(st.integers(0, 3)) == 0:
        anchor = draw(st.sampled_from(first_reports))
    cutoff = anchor + timedelta(
        seconds=draw(st.one_of(st.sampled_from((0, 1, -1)), st.integers(-10 * DAY, 40 * DAY)))
    )
    new_rows = draw(
        st.lists(
            st.builds(
                NewSpec,
                q_idx=st.integers(0, n_prior - 1),
                kind=st.sampled_from(("future", "late_ingest")),
                offset_s=st.one_of(st.sampled_from((0, 1, 2)), st.integers(0, 120 * DAY)),
                vintage=st.just("restated"),
            ),
            max_size=4,
        )
    )
    return Case(ticker, n_prior, cutoff, tuple(rows), tuple(new_rows))


def _series_key(case: Case) -> str:
    return f"rev.consolidated.{case.ticker}"


def _obs(case: Case, q_idx: int, value: Decimal, available: datetime, vintage: str, ref: str):
    return ObservationIn(
        series_key=_series_key(case),
        period_date=_quarter(case, q_idx).end,
        value=value,
        available_at=available,
        availability_basis=BASIS,
        source_ref=f"https://example.invalid/synthetic-property#{ref}",
        vintage=vintage,
        source_kind="seed_csv",
    )


def _original(case: Case) -> sa.Engine:
    engine = fresh_store()
    stamped = [
        (_obs(case, r.q_idx, r.value, r.available_at, r.vintage, str(i)), r.ingested_at)
        for i, r in enumerate(case.rows)
    ]
    add_stamped(engine, stamped)
    return engine


def _perturbed(case: Case, mode: str) -> sa.Engine:
    """Same rows, except that anything not knowable at the cutoff is mutated or removed."""
    cutoff = case.cutoff
    engine = fresh_store()
    stamped: list[tuple[ObservationIn, datetime]] = []
    for i, r in enumerate(case.rows):
        future = r.available_at >= cutoff
        late = mode == "live" and r.ingested_at > cutoff
        ingested = r.ingested_at
        value = r.value
        if future or late:
            if r.action == "delete":
                continue
            if r.action == "mutate":
                value = SENTINEL
        elif mode == "backtest" and r.action == "reingest":
            ingested = r.ingested_at + timedelta(days=7)  # invisible to a backtest reader
        stamped.append((_obs(case, r.q_idx, value, r.available_at, r.vintage, str(i)), ingested))
    for j, new in enumerate(case.new_rows):
        if new.kind == "future":
            available = cutoff + timedelta(seconds=new.offset_s)
            ingested = available
        elif mode == "live":  # known before the cutoff but only loaded after it
            available = cutoff - timedelta(seconds=new.offset_s + 1)
            ingested = cutoff + timedelta(seconds=1 + new.offset_s)
        else:
            continue  # in backtest mode that row WOULD be visible, so it is not a perturbation
        stamped.append(
            (_obs(case, new.q_idx, SENTINEL, available, new.vintage, f"new{j}"), ingested)
        )
    add_stamped(engine, stamped)
    return engine


def _outcome(engine: sa.Engine, case: Case, reader_cls: type[PointInTimeReader], mode: str):
    reader = reader_cls(engine, case.cutoff, mode)  # type: ignore[arg-type]
    company = UNIVERSE.company(case.ticker)
    return compute_baseline(company, TARGET, reader, UNIVERSE.breaks_for(case.ticker))


def _comparable(outcome: BaselineResult | BaselineRefusal) -> tuple:
    if isinstance(outcome, BaselineRefusal):
        return ("refused", outcome)
    return ("ok", outcome.point, outcome.snapshot_canonical, outcome.snapshot_sha256)


# --- explicit cases: each makes one leaky reader fail without any randomness ---------------

_T = datetime(2026, 12, 1, 0, 0, 0, tzinfo=UTC)


def _example_case(*new_rows: NewSpec, ticker: str = "DMART") -> Case:
    """Eight fully known quarters (a clean baseline at T) plus the given perturbations."""
    shell = Case(ticker, 8, _T, (), ())
    rows = []
    for q_idx in range(8):
        available = datetime.combine(_quarter(shell, q_idx).end, time(), UTC) + timedelta(days=10)
        rows.append(
            RowSpec(
                q_idx,
                Decimal(10_000 + 100 * q_idx),
                available,
                available + timedelta(days=1),
                "first_reported",
                "keep",
            )
        )
    return Case(ticker, 8, _T, tuple(rows), tuple(new_rows))


EXACTLY_AT_T = _example_case(NewSpec(7, "future", 0, "restated"))  # leaky-le
FAR_FUTURE = _example_case(NewSpec(7, "future", 400 * DAY, "restated"))  # leaky-nofilter
PERIOD_BEFORE_T_FILED_AFTER = _example_case(NewSpec(7, "future", 1, "restated"))  # leaky-period
INGESTED_AFTER_T = _example_case(NewSpec(7, "late_ingest", 0, "restated"))  # leaky-ingested


@pytest.mark.parametrize("mode", ["backtest", "live"])
@example(case=EXACTLY_AT_T)
@example(case=FAR_FUTURE)
@example(case=PERIOD_BEFORE_T_FILED_AFTER)
@example(case=INGESTED_AFTER_T)
@given(case=cases())
def test_future_perturbation_invariance(
    case: Case, mode: str, reader_cls: type[PointInTimeReader]
) -> None:
    original, perturbed = _original(case), _perturbed(case, mode)
    try:
        before = _outcome(original, case, reader_cls, mode)
        after = _outcome(perturbed, case, reader_cls, mode)
    finally:
        original.dispose()
        perturbed.dispose()
    assert _comparable(after) == _comparable(before)
    if isinstance(after, BaselineResult):
        assert SENTINEL not in [obs.value for obs in after.inputs]


def test_the_examples_really_perturb_the_store() -> None:
    """Guard against a vacuous property: each explicit case adds a visible-to-leaky row."""
    for case, mode in (
        (EXACTLY_AT_T, "backtest"),
        (FAR_FUTURE, "backtest"),
        (PERIOD_BEFORE_T_FILED_AFTER, "backtest"),
        (INGESTED_AFTER_T, "live"),
    ):
        original, perturbed = _original(case), _perturbed(case, mode)
        with original.connect() as a, perturbed.connect() as b:
            count = "SELECT COUNT(*) FROM observations"
            assert b.execute(sa.text(count)).scalar_one() == (
                a.execute(sa.text(count)).scalar_one() + 1
            )
        clean = _outcome(original, case, PointInTimeReader, mode)
        assert isinstance(clean, BaselineResult), clean


def test_invariance_distinguishes_a_perturbation_that_is_knowable() -> None:
    """Control: a row available BEFORE T does change the baseline, so the property can fail."""
    case = _example_case()
    original = _original(case)
    stamped = [
        (
            _obs(case, 7, SENTINEL, _T - timedelta(days=1), "restated", "visible"),
            _T - timedelta(days=1),
        )
    ]
    other = _original(case)
    add_stamped(other, stamped)
    a = _outcome(original, case, PointInTimeReader, "backtest")
    b = _outcome(other, case, PointInTimeReader, "backtest")
    assert isinstance(a, BaselineResult) and isinstance(b, BaselineResult)
    assert a.point != b.point
    assert a.snapshot_canonical != b.snapshot_canonical
