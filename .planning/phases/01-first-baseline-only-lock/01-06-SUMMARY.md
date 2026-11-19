---
phase: 01-first-baseline-only-lock
plan: "06"
subsystem: leakage-suite
status: complete
tags: [leakage, hypothesis, meta-test, splitter, ast-guard, point-in-time, walk-forward]

requires:
  - phase: 01-04
    provides: "PointInTimeReader with overridable _row_filter/_postcondition hooks, store writer, seed loader"
  - phase: 01-05
    provides: "compute_baseline, BaselineResult/BaselineRefusal, snapshot_canonical"
provides:
  - "pytest option --reader {correct, leaky-le, leaky-nofilter, leaky-period, leaky-ingested}, session fixture reader_cls, hypothesis profiles dev and ci"
  - "tests/leakage/leaky_readers.py: LeakyLEReader, NoFilterReader, PeriodFilterReader, IgnoreIngestedReader (+ LEAKY_READERS map)"
  - "tests/leakage/test_invariance.py: future-perturbation invariance property (backtest and live)"
  - "tests/meta/test_leakage_suite_catches_leaks.py: subprocess proof that every leaky reader makes the suite exit with code exactly 1"
  - "nowcaster.splits: Fold, expanding_window_folds (reveal-keyed expanding window)"
  - "tests/leakage/test_no_ambient_clock.py: AST bans on wall-clock reads and read-path bypass, with scanner self-checks"
  - "tests/leakage/store_helpers.py: in-memory SQLite store builders shared by the leakage tests"
affects: [01-07, 01-10, phase-03-backtest]

actuals:
  tokens: 14015   # 56,059 chars of added lines (git diff a0854e1..HEAD, before the SUMMARY commit) / 4
  tasks: 3
  commits: 3      # MEASURED: git rev-list --count a0854e1..HEAD before the SUMMARY commit
plan_head_before: a0854e1bdde60e655aea1ac467f33a0a6114712b
plan_head_after: 24011af82f27c729dd138dd5e94176890b105b5d

tech-stack:
  added: []
  patterns:
    - "One switch (--reader) runs the whole leakage suite against any reader; leaky readers are test-only subclasses overriding the reader's two hooks"
    - "A leakage test is only credible if a subprocess meta-test proves it can fail, asserting returncode == 1 (never != 0)"
    - "Hypothesis stores are built inside the test body (in-memory SQLite via metadata.create_all and the production writer), not in function-scoped fixtures"
    - "AST scanners match node structure and resolve import aliases, each with a planted-violation self-check"

key-files:
  created:
    - tests/leakage/leaky_readers.py
    - tests/leakage/store_helpers.py
    - tests/leakage/test_baseline_boundaries.py
    - tests/leakage/test_invariance.py
    - tests/leakage/test_splits.py
    - tests/leakage/test_no_ambient_clock.py
    - tests/meta/__init__.py
    - tests/meta/test_leakage_suite_catches_leaks.py
    - nowcaster/src/nowcaster/splits.py
  modified:
    - tests/conftest.py
    - tests/leakage/test_reader.py

key-decisions:
  - "test_reader.py builds readers through a make_reader factory fixture over reader_cls; the two post-condition tests monkeypatch the production reader's _row_filter and so deliberately use PointInTimeReader directly (a leaky subclass overrides the hook, so the patch would not reach it)"
  - "The meta-test subprocess uses absolute paths, an empty temp cwd and a scrubbed DATABASE_URL/CALLEDIT_ENV, so a developer .env at the repo root is never read; pyproject rootdir is still found from the absolute argument"
  - "Restatements in the invariance strategy never share an available_at, because exact ties between visible vintages are ordered by ingested_at (then content_hash) even in backtest mode"
  - "splits.py is a pure function over callables; a target whose reveal is None gets no fold, and a training row needs BOTH a reveal and a label strictly before as_of"
  - "The ambient-clock scanner flags any reference (not just calls) to datetime.now/utcnow/today, date.today, time.time/time_ns, resolving 'import ... as' and 'from ... import ... as' aliases"

patterns-established:
  - "Leaky readers return wrong rows rather than raising, so detection is by assertion on the baseline, not by an exception"
  - "Strategy anchors the random cutoff on the latest first report (offsets 0, +-1 s and +-days), giving about 40% complete windows and the rest refusals"

requirements-completed: [LEAK-01, LEAK-02, LEAK-03, LEAK-04, PIT-03]

duration: ~2h wall clock
completed: 2026-11-19
---

# Phase 1 Plan 06: Leakage suite, leaky readers, meta-test and reveal-keyed splitter Summary

**`uv run pytest tests/leakage` passes on the real reader and goes red (exit code exactly 1) on each of four deliberately leaky readers; a subprocess meta-test proves that, a hypothesis invariance property shows rows from after the cutoff cannot move the baseline by a byte, and a reveal-keyed splitter plus AST guards close LEAK-04 and the single-read-path half of PIT-03.**

## Performance

- **Duration:** about 2 hours of wall clock
- **Tasks:** 3/3 (Task 1 tracer, Tasks 2 and 3 TDD-style)
- **Files:** 9 created, 2 modified (11 touched)
- **Meta-test time:** `uv run pytest tests/meta -q` took **55.00 s** (7 passed) against the 180 s budget

## Accomplishments

- **`--reader` switch.** `tests/conftest.py` registers `--reader` (default `correct`) and a session `reader_cls` fixture. It also registers the hypothesis profiles `dev` (random) and `ci` (derandomised); pytest's `--hypothesis-profile` overrides the default.
- **Four leaky readers**, each wrong in exactly one way, none importable from `src/`:
  - `LeakyLEReader`: `available_at <= as_of`.
  - `NoFilterReader`: no availability filter.
  - `PeriodFilterReader`: `period_date < as_of.date()`.
  - `IgnoreIngestedReader`: live mode ignores `ingested_at`.
- **Baseline-boundary tests.** Sentinel restatements (value 999999999.99) at exactly T, T+1 s and T+30 days, plus a live row known before T but ingested after T, must leave `compute_baseline`'s point and canonical snapshot byte-identical to a clean store. The tests also assert that the sentinels are physically present in the dirty store, so they cannot pass vacuously.
- **Invariance property** (`test_future_perturbation_invariance`, backtest and live):
  - **Random store:** 8 to 16 quarters, restatements, any of DMART/ETERNAL/TITAN (so the break method is exercised too), and a cutoff anchored on the latest first report.
  - **Perturbation:** rows not knowable at T are kept, mutated to the sentinel or deleted. New rows are added at T, T+1 s and later. In live mode, rows with `ingested_at > T` are perturbed as well.
  - **Backtest-only extra:** `ingested_at` of known rows is shifted by 7 days.
  - **Check:** equal point and canonical snapshot, or an identical refusal.
  - **Explicit cases:** four `@example` cases, one per leaky reader, make detection deterministic.
  - **Control:** a test shows that a row known before T does change the baseline, so the property can fail.
- **Meta-test.** Each of the four variants runs `tests/leakage` in a subprocess and must exit with `returncode == 1`. The correct reader is the control and must exit 0. A further test shows an unknown `--reader` gives exit code 4, which the assertions would reject as "not caught".
- **`nowcaster.splits`.** `Fold` and `expanding_window_folds(targets, reveal_at_early, label_available_at, min_train)`.
  - **Training rule:** a training row needs both its reveal and its label strictly before `fold.as_of`, which is the target's early-bound reveal.
  - **Folds:** none is yielded below `min_train` or for an unrevealed target.
  - **Order:** by `(as_of, ticker, quarter)`.
  - **Independence:** the module imports no `sqlalchemy`, no `calledit_data.db` and no sklearn.
- **Static guards.** AST scans over `data/src` and `nowcaster/src`, with alias resolution and 19 planted-violation or clean-code self-checks:
  - no wall-clock read outside `clock.py`;
  - `baseline.py` and `splits.py` import none of sqlalchemy, `calledit_data.db`, `calledit_data.store`, sqlite3 or psycopg;
  - `calledit_data` never imports `nowcaster`.

## Task Commits

1. **Task 1 (tracer): `--reader` switch, leaky readers, baseline-boundary tests** - `519fe2d` (feat)
2. **Task 2: invariance property and the meta-test** - `dc99ac6` (test)
3. **Task 3: splitter and static guards** - `24011af` (feat)

## Verification (exact output)

- `uv run pytest -q -m "not postgres"`: **`519 passed, 35 deselected in 81.52s (0:01:21)`** (baseline 463; +56).
- `uv run ruff check .`: **`All checks passed!`**. `uv run ruff format --check .` reports only the two pre-existing planning markdown files noted in 01-05. `uv sync --locked`: clean.
- `uv run pytest tests/leakage tests/meta -q`: `155 passed in 73.07s`.
- Tracer gate (re-run end to end after Task 1): `uv run pytest tests/leakage -q` gave 106 passed, and each leaky variant gave exit 1.
- Leaky runs of `tests/leakage -q --reader=<v>` after all three tasks (exit code is 1 for every variant):
  - leaky-le: `8 failed, 140 passed`.
  - leaky-nofilter: `14 failed, 134 passed`.
  - leaky-period: `14 failed, 134 passed`.
  - leaky-ingested: `4 failed, 144 passed`.
- Boundary tests alone: leaky-le 3 failed, leaky-nofilter 6, leaky-period 6, leaky-ingested 2 (live only).
- Invariance test with `--hypothesis-profile=ci`: `4 passed`. Under the random `dev` profile it passed 3 of 3 repeat runs. Each leaky variant fails it (leaky-ingested in live mode only).
- Mutation checks on `splits.py`:
  - Changing the reveal `<` to `<=` is caught by `test_reveal_exactly_at_the_cutoff_is_excluded_even_when_the_label_is_early` and by the property.
  - Changing the label `<` to `<=` is caught by `test_label_available_exactly_at_the_cutoff_is_excluded` and by the property.
  - The file was restored byte-for-byte and re-tested.
- Acceptance greps and counts:
  - 4 leaky reader classes, 4 `@example` decorators, and `returncode == 1` asserted.
  - `test_training_rows_revealed_strictly_before_cutoff` and `test_target_never_in_own_train_set` exist.
  - A scanner self-check exists in `test_no_ambient_clock.py`.

## TDD Gate Compliance

Task 2 and Task 3 followed the project's established pattern for this phase (tests written against code that already exists or in the same commit as the code they test), so there is no separate RED commit. The substitute for a RED commit is stronger evidence that the tests can fail:

- every leaky reader was run against the new tests and failed;
- two mutations of `splits.py` were run and caught;
- the scanner self-checks plant real violations.

The first mutation run showed that the fixed-calendar test did not isolate the reveal condition (the label condition excluded the tied peer by itself), so `test_reveal_exactly_at_the_cutoff_is_excluded_even_when_the_label_is_early` was added.

## Deviations from Plan

### Auto-fixed / judgement calls

**1. [Rule 3 - Blocking] Hypothesis cutoff strategy produced almost only refusals**
- **Found during:** Task 2, checking that the property was not vacuous.
- **Issue:** A cutoff drawn from a plain integer range sat before the Q-1 filing in about 90% of examples, so nearly every example was a `missing_seed_quarter` refusal and the numeric path was barely exercised.
- **Fix:** The cutoff is anchored on the latest first report (or any first report, one time in four) plus an offset that is 0 or +-1 s about half the time, otherwise up to -10 or +40 days. About 40% of examples now produce a baseline. A measuring script was run in the scratchpad and is not committed.
- **Files:** tests/leakage/test_invariance.py

**2. [Rule 2 - Missing critical] Meta-test subprocess isolates the environment**
- **Issue:** The plan's command used relative `tests/leakage` with the repo root as cwd, so a developer `.env` there would be read by `get_settings()`.
- **Fix:** The command uses the absolute suite path with an empty temp cwd and a scrubbed `DATABASE_URL`/`CALLEDIT_ENV`; `-m "not postgres"` is also passed. The argument list is otherwise the plan's.
- **Files:** tests/meta/test_leakage_suite_catches_leaks.py

**3. [Rule 2 - Missing critical] Guard against vacuous tests**
- **Added:**
  - `test_the_examples_really_perturb_the_store` and `test_invariance_distinguishes_a_perturbation_that_is_knowable` in the invariance file;
  - the premise assertion on stored sentinel rows in the boundary tests;
  - `test_source_trees_are_found` and `test_clock_py_is_the_one_place_that_reads_the_clock` for the AST scans;
  - an exit-code-4 test in the meta-test.

**4. [Minor] The post-condition tests in test_reader.py keep using the production reader**
- **Why:** they monkeypatch `PointInTimeReader._row_filter`, and a leaky subclass overrides that hook, so the patch cannot reach it. Every other existing test now runs through `reader_cls`. Nothing was removed.

**5. [Minor] The meta-test also runs a control and a usage-error test**
- Beyond the five tests the plan names (4 variants plus the control): `test_every_leaky_variant_is_covered` and `test_a_usage_error_is_not_counted_as_caught`, giving 7 tests in the file.

**6. [Minor] `store_helpers.py` added**
- It holds the in-memory store builders shared by the boundary and invariance tests. It is not listed in the plan's `files_modified`.

**Total deviations:** 6, none changing a settled rule or the plan's scope.

## Known Stubs

None. Every value in the tests is SYNTHETIC and labelled; the real seed CSV is still header-only (Plan 01-09).

## Threat Flags

None. No new endpoints, auth paths or schema. Mitigations delivered:
- T-01-21: the subprocess meta-test with `returncode == 1` plus deterministic `@example` boundary cases.
- T-01-22: the AST ban on ambient clock reads, with self-checks.
- T-01-23: the AST import-boundary test for `baseline.py` and `splits.py`.
- T-01-SC: no new dependencies (`hypothesis` was approved in 01-01).

## Flagged Assumptions (edge probes) for the verifier

- **LEAK-01:**
  - Covered: `ingested_at`-only changes in backtest (perturbation action `reingest`); a restatement at exactly T (`@example`, and boundary offsets 0 and 1 s); a store where nothing is known at T (the refusal must be identical).
  - **Open:** when two visible vintages of one period share the same `available_at` but differ in value, the winner is chosen by `ingested_at` and then content hash, even in backtest mode. So ingestion time can influence a backtest in that tie. The strategy avoids such ties and `test_reader.py` pins the tie-break, but the behaviour itself is a design question for D-05, and Plan 01-10 should decide whether a tie should be refused instead.
- **LEAK-02:**
  - Covered: a leaky reader that raises instead of returning wrong rows would also count as "caught" only if pytest exited 1, and exit codes 2 to 5 are rejected.
  - **Open:** the four leaky readers all return wrong rows; no variant raises, so the "raises instead of returns" edge is untested by a concrete variant.
- **LEAK-03:** the IST/UTC year-boundary and date-only cases remain in `test_time_boundaries.py` and `test_reader.py`; this plan adds the boundary sentinels at T exactly and T+1 s. The Windows-without-tzdata edge was not exercised in this plan.
- **LEAK-04:** `expanding_window_folds` is not yet used by any model code (Phase 3). Its strictness is proven on synthetic calendars only; wiring it to the real reveal calendar and label times is a Phase 3 task.

## Issues Encountered

None blocking. `ruff format` on this Windows host initially rewrote `tests/conftest.py` with CRLF when edited through a Python text write; this was caught from the 147-line diff and the file was normalised back to LF before the first commit. All new files are LF.

## Next Phase Readiness

- Plan 01-07 can lock `BaselineResult.snapshot_sha256` knowing the snapshot is invariant under future rows.
- Plan 01-10 (PREREGISTRATION) can cite `--reader` plus the meta-test as the evidence for "no lookahead".
- Phase 3 must feed `expanding_window_folds` from the real reveal calendar.
- STATE.md and ROADMAP.md were not touched (the orchestrator owns them). No `.env` was read, and no database file was left in the worktree.

---
*Phase: 01-first-baseline-only-lock*
*Completed: 2026-11-19*

## Self-Check: PASSED

- FOUND: leaky_readers.py, store_helpers.py, test_baseline_boundaries.py, test_invariance.py, test_splits.py, test_no_ambient_clock.py, tests/meta/__init__.py, tests/meta/test_leakage_suite_catches_leaks.py, nowcaster/src/nowcaster/splits.py
- FOUND: commits 519fe2d, dc99ac6, 24011af are ancestors of HEAD
