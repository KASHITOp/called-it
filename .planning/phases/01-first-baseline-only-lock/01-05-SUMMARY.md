---
phase: 01-first-baseline-only-lock
plan: "05"
subsystem: baseline
status: complete
tags: [baseline, decimal, point-in-time, break-aware, snapshot, sha256, typer, hypothesis]

requires:
  - phase: 01-02
    provides: "calledit-ledger-v1 canonicalize/sha256_hex/format_*, now_utc, nowcast CLI"
  - phase: 01-03
    provides: "FiscalQuarter.shift, Universe/Company/Break with breaks_for and labels"
  - phase: 01-04
    provides: "PointInTimeReader, seed loader, SYNTHETIC fixture CSV, _open_store"
provides:
  - "nowcaster.baseline: MODEL_VERSION (baseline-sqly@1.0.0), compute_baseline, BaselineResult, BaselineRefusal, window_for, ETERNAL_LABEL and method/pair_status/reason-code constants"
  - "Snapshot scheme calledit-snapshot-v1 (strings only, obs_id excluded) with snapshot_canonical and snapshot_sha256"
  - "CLI: nowcast baseline --quarter LABEL (read-only; no as-of override; live reader at now_utc)"
affects: [01-06, 01-07, 01-10, phase-03-backtest]

actuals:
  tokens: 10080   # 40,300 chars of added lines (git diff 696a353..HEAD, before the SUMMARY commit) / 4
  tasks: 2
  commits: 2      # MEASURED: git rev-list --count 696a353..HEAD before the SUMMARY commit
plan_head_before: 696a353ebe0f3db691e7b4ec3dd7032e1fa56735
plan_head_after: 1a8acb190d166e0e2790154d13c52e9fd56d0bb5

tech-stack:
  added: []
  patterns:
    - "Decimal-only money path under localcontext(prec 28, ROUND_HALF_EVEN); the point comes from unrounded growth, growth_str is display only"
    - "Refuse, never impute: any missing/unverified window quarter returns a BaselineRefusal listing every affected quarter in window order"
    - "baseline.py reads data only through PointInTimeReader and never touches the clock (as_of is reader.as_of)"
    - "FakeReader(PointInTimeReader) subclass lets arithmetic tests run without a DB"

key-files:
  created:
    - nowcaster/src/nowcaster/baseline.py
    - tests/nowcaster/__init__.py
    - tests/nowcaster/test_baseline_e2e.py
    - tests/nowcaster/test_baseline.py
  modified:
    - nowcaster/src/nowcaster/cli.py

key-decisions:
  - "Snapshot list-like fields (window_quarters, labels, breaks_in_window) are '|'-joined strings ('none' when empty), because the interface says snapshot values are strings or lists of string-valued dicts; only inputs is a list of dicts. Plan 01-07/01-10 must use the same encoding."
  - "All eight Q-8..Q-1 quarters must be usable for BOTH methods; snapshot inputs are all eight in period order, including for break_single_pair"
  - "Any source_kind other than seed_csv counts as unverified (not just seed_csv_unverified)"
  - "A non-positive denominator (prior-window sum, or the pair base) is refused with reason_code invalid_base_sum and the denominator quarters listed; PREREGISTRATION (Plan 01-10) must list this third reason code"
  - "With several quarter-range breaks on a ticker, a pair is post_break only if both quarters are after EVERY range; the break method triggers if ANY range contains a window quarter or the window straddles it"
  - "ETERNAL always carries ETERNAL_LABEL: if the config's labels ever lose it, baseline.py re-adds it (a result can never omit it)"

patterns-established:
  - "CLI preview with no store prints REFUSED missing_seed_quarter with all eight quarters for every enabled company and exits 0"

requirements-completed: [BASE-01, FEAT-02, PIT-05]

duration: 40min
completed: 2026-11-19
---

# Phase 1 Plan 05: Point-in-time baseline Summary

**Exact-Decimal, break-aware SQLY x (1+TTM growth) baseline from the point-in-time store with a canonical snapshot hash, a read-only `nowcast baseline --quarter` preview, and honest refusals instead of imputation.**

## Performance

- **Tasks:** 2 of 2, each committed separately
- **Files:** 1 module + CLI command + 2 test modules

## Accomplishments

- `compute_baseline` implements D-04..D-08 exactly: window Q-8..Q-1, SQLY = Q-4, `g = sum(Q-4..Q-1)/sum(Q-8..Q-5) - 1`, point quantized once to 0.01 ROUND_HALF_EVEN from unrounded g; growth_str is 6 dp for display only.
- Break-aware D-06: quarter-range breaks pick the single pair (Q-1, Q-5) with `pair_status` `post_break` or `least_straddling`; a window fully after (or fully before) the range stays `ttm_yoy`. The GST 2.0 date break only appears in `breaks_in_window` (D-07).
- Refusals (D-08): `missing_seed_quarter`, `unverified_seed_quarter`, plus `invalid_base_sum` for the zero-denominator edge flagged in the plan. No imputation path exists.
- `nowcast baseline --quarter Q3FY27` prints method, window, pair, pair_status, sqly, point, growth, labels, breaks and snapshot sha256 per enabled company, or `REFUSED <reason>: <quarters>`. It opens no write transaction (test asserts all table row counts unchanged) and creates no SQLite file when none exists.
- Snapshot is byte-identical across runs on the same store and as_of and independent of `obs_id`.

## Task Commits

1. **Task 1 (tracer): PIT store to compute_baseline to CLI** - `1c55cbb` (feat)
2. **Task 2: break-aware tests, labels, refusals, vintage** - `1a8acb1` (test)

## Verification

- `uv run pytest -q`: **429 passed** (baseline 390; +39 in tests/nowcaster)
- `uv run pytest tests/nowcaster -q`: 39 passed; `-k "eternal or breaks"`: 9 passed, 30 deselected
- `uv run ruff check .`: All checks passed; `uv sync --locked` clean
- `grep -c "baseline-sqly@1.0.0"` = 1; `grep -cE "float\("` = 0
- `uv run nowcast baseline --quarter Q3FY27` with no local DB: `REFUSED missing_seed_quarter: Q3FY25, ... Q2FY27` for DMART, ETERNAL, TITAN, exit 0

## Deviations from Plan

### Auto-fixed / judgement calls

**1. [Rule 2 - Missing critical functionality] Zero/negative denominator refusal**
- **Found during:** Task 1 (flagged assumption BASE-01)
- **Fix:** `invalid_base_sum` BaselineRefusal instead of ZeroDivisionError; covered by two tests (TTM prior sum and pair base)
- **Files modified:** nowcaster/src/nowcaster/baseline.py, tests/nowcaster/test_baseline.py

**2. [Rule 2 - Missing critical functionality] ETERNAL label guard**
- **Issue:** the plan prohibition says no Eternal result may omit the label, but labels came only from config
- **Fix:** baseline re-adds ETERNAL_LABEL if config lacks it (`test_eternal_label_survives_a_config_edit_that_drops_it`)

**3. Task ordering: break-method code landed in the Task 1 commit**
- The full `compute_baseline` (including the D-06 pair logic) was written as one unit, so commit 1c55cbb already contains the break method and Task 2's commit adds only its tests (which passed on first run apart from one wrong expectation in my own multi-range test, corrected). The strict RED-then-GREEN split for Task 2 was therefore not observed.

**Total deviations:** 3 (2 added safety behaviours, 1 process). No impact on the settled rules.

## Known Stubs

None. Tests use clearly labelled SYNTHETIC fixtures; the real seed CSV is still header-only (Plan 01-09).

## Issues Encountered

None blocking. `ruff format --check .` reports two pre-existing planning markdown files (code blocks in 01-RESEARCH.md and ARCHITECTURE.md); not touched, not in scope.

## Notes for downstream plans

- 01-06: `baseline.py` imports only calledit_data.pit.reader, calledit_data.calendar.fiscal, nowcaster.universe, nowcaster.ledger.canonical, plus stdlib; the import-boundary test can enforce that.
- 01-07: lock the `BaselineResult.snapshot_canonical` / `snapshot_sha256` as `feature_snapshot_sha256`; do not re-derive.
- 01-10: PREREGISTRATION must state that both break branches select (Q-1, Q-5), that `pair_status` distinguishes them, the `invalid_base_sum` reason code, the joined-string snapshot encoding, and the multi-range post-for-every-break rule. Overlapping-range behaviour is covered by one test but remains for the verifier's judgement.

## Self-Check: PASSED

- baseline.py, test_baseline.py, test_baseline_e2e.py, tests/nowcaster/__init__.py exist
- Commits 1c55cbb and 1a8acb1 are ancestors of HEAD
