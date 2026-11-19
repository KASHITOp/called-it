---
phase: 01-first-baseline-only-lock
plan: "07"
subsystem: lock
status: complete
tags: [lock, predict, ledger, guard, rules-record, exit-codes, live-context, typer]

requires:
  - phase: 01-02
    provides: "calledit-ledger-v1 canonical, append_record, rules record, nowcast CLI, now_utc"
  - phase: 01-05
    provides: "compute_baseline, BaselineResult/BaselineRefusal, snapshot_canonical/snapshot_sha256"
  - phase: 01-08
    provides: "run_db_check Postgres self-check, pg_scratch/fresh_scratch fixtures"
provides:
  - "nowcaster.exit_codes: EXIT_OK 0, EXIT_PARTIAL 3, EXIT_REFUSED 4, EXIT_ENV 5, EXIT_CODE_HELP"
  - "nowcaster.lock: run_lock(settings, quarter, kind, *, now) -> LockReport, LockRefused, CompanyOutcome"
  - "nowcaster.ledger.records: build_prediction_payload (29 fields), build_gap_payload (17 fields), prediction_typed_columns, gap_typed_columns, PREDICTION_FIELDS, GAP_FIELDS, INTERVAL_LABEL, LOCK_KINDS"
  - "nowcaster.rules: latest_rules_record, RulesHead, stale_fields, live provenance checks, current_run_id"
  - "nowcaster.universe.Universe.unconfirmed()"
  - "CLI: nowcast predict --quarter LABEL [--kind dispatch|weekly|final]; nowcast rules prints RULES seq=<n> hash=<h>"
  - "tests/ledger/lock_helpers.py + conftest.py: lock_env fixture (temp SQLite, temp prereg and universe through settings paths)"
affects: [01-09, 01-10, 01-11, 01-12, 01-13, phase-02, phase-04]

actuals:
  tokens: 19602   # 78,407 chars of added lines (git diff 01381d4..HEAD, before the SUMMARY commit) / 4
  tasks: 3
  commits: 3      # MEASURED: git rev-list --count 01381d4978c47ec514ff190d37291246194e7a14..HEAD before the SUMMARY commit
plan_head_before: 01381d4978c47ec514ff190d37291246194e7a14
plan_head_after: 83482e31e355c7e6ab8dd288551a172d5b9333a4

tech-stack:
  added: []
  patterns:
    - "One captured instant: the CLI reads now_utc() once; run_lock has no time parameter other than that value, and no option, setting or env var selects it"
    - "Two-pass lock: guard every company first (no writes), stop with exit 4 if all are refused, then baseline -> prediction or gap, one transaction per company"
    - "Fixed, value-free messages: SQLAlchemy failures report the exception class only"
    - "Lock tests run against a temp SQLite store with the SYNTHETIC fixture; live-context tests stub the database engine and never open a network connection"

key-files:
  created:
    - nowcaster/src/nowcaster/lock.py
    - nowcaster/src/nowcaster/exit_codes.py
    - tests/ledger/lock_helpers.py
    - tests/ledger/conftest.py
    - tests/ledger/test_predict_e2e.py
    - tests/ledger/test_lock_guard.py
    - tests/ledger/test_rules_record.py
    - tests/postgres/test_pg_records.py
  modified:
    - nowcaster/src/nowcaster/ledger/records.py
    - nowcaster/src/nowcaster/ledger/chain.py
    - nowcaster/src/nowcaster/rules.py
    - nowcaster/src/nowcaster/universe.py
    - nowcaster/src/nowcaster/cli.py
    - tests/conftest.py

key-decisions:
  - "Prediction and gap field sets frozen as listed in the plan interfaces (29 and 17 fields); a test pins the exact order of PREDICTION_FIELDS and GAP_FIELDS. They become one-way at the first live lock (01-10/01-13)."
  - "data_cutoff equals locked_at equals now: every input row had available_at < that instant."
  - "labels and breaks_in_window are sorted '|'-joined strings or none; missing_quarters keeps window order (oldest first), because lexical order of Qn FYyy labels is not chronological."
  - "Exit 3 whenever at least one record was appended and any company got a gap or a refusal; exit 4 only when nothing was appended; a run where every company gaps is exit 3 (gap records are appended)."
  - "A refused company writes no record (only a gap, i.e. missing or unverified data, does); the CLI prints REFUSED <reason> for it."
  - "Live rules, like live predict, also require a confirmed universe (must_have), and live rules check provenance on dry-run too; only the Actions/main context check is skipped for dry-run."
  - "A second `predict` for the same quarter and kind is not refused (weekly locks repeat by design; the official call is derived later, D-15)."

patterns-established:
  - "CLI line per company: `<TICKER> LOCKED seq=<n> hash=<h>`, `<TICKER> GAP seq=<n> <reason>: <quarters>`, `<TICKER> REFUSED <reason>: <detail>`; run-level refusals go to stderr as `predict: <message>`"

requirements-completed: [LEDG-05, LEDG-07, LEDG-01, LEDG-03, FOUND-03]

duration: ~2h
completed: 2026-11-19
---

# Phase 1 Plan 07: The lock Summary

**`nowcast predict --quarter Q3FY27` appends one chained, snapshot-backed baseline prediction (or a visible gap) per enabled company at a single captured instant, and refuses every late, premature, drifted-rules or unconfirmed-live lock with exit codes 0/3/4/5.**

## Accomplishments

- **Tracer (Task 1):** `run_lock` takes the head rules record, runs `compute_baseline` per enabled company in sorted ticker order on a live-mode reader at `now`, and appends a `prediction` (D-12: interval `none`, `interval_label`, `model_version baseline-sqly@1.0.0`, labels, breaks, snapshot sha256, earliest_plausible_reveal, rules_seq/hash, universe_sha256, code_git_sha, run_id) or a `gap` (D-08) in its own transaction. `ledger export` then writes 4 lines and `snapshots/1..3.json`, each hashing to its payload's `feature_snapshot_sha256`. Typed columns equal the parsed payload.
- **Guard (Task 2):** per company, on UTC instants, `period_start(Q) <= now < earliest_plausible_reveal` and no stored reveal event with an early bound `<= now` (D-27). Boundary seconds are tested (DMART locks at 18:29:59Z, refused at 18:30:00Z while ETERNAL and TITAN lock, exit 3; all refused at 2027-01-06T18:30:00Z, exit 4, nothing appended). Q2FY27 and Q4FY27 are refused. Live demands GitHub Actions on `refs/heads/main`, every enabled ISIN and applicable break confirmed, and a passing `run_db_check` (FAIL gives exit 5). A DB failure is exit 5 with no SQLite fallback and no local file creation.
- **Rules freshness (Task 3):** `predict` compares the preregistration bytes and universe bytes with the latest rules record and refuses (exit 4, naming `document_sha256` / `universe_sha256`) until a new rules record exists. Disabling ETERNAL then running `rules` makes the next lock cover only DMART and TITAN (exit 0). Live `rules` requires tracked, HEAD-equal, LF-only files and a confirmed universe, and refuses `--document`/`--universe`; `document_git_commit` equals `git rev-parse HEAD` (tested in a temp git repo).
- **LEDG-05 prohibition tested:** `predict` has exactly `--quarter` and `--kind`; no Settings field matches a time name; an AST scan shows `lock.py` reads no environment variable other than the four GitHub ones (with scanner self-checks).

## Task Commits

1. **Task 1 (tracer): predict from rules record to chained predictions** - `bdf2f26` (feat)
2. **Task 2: lock guard, live-quarter rule, reveal events, live context** - `89e7f2a` (feat)
3. **Task 3: rules-record freshness and live provenance** - `83482e3` (feat)

## Verification

- `uv run pytest -q -m "not postgres"`: **575 passed, 36 deselected** (baseline 519 passed, 35 deselected; +56: 11 e2e, 25 guard, 20 rules; +1 deselected postgres test)
- `uv run ruff check .`: All checks passed
- `uv sync --locked`: clean (no dependency added)
- `uv run pytest tests/ledger/test_predict_e2e.py -q`: 11 passed; `tests/ledger/test_lock_guard.py`: 25 passed; `tests/ledger/test_rules_record.py`: 20 passed
- `grep -c "none (baseline-only, no out-of-sample residuals yet)" nowcaster/src/nowcaster/ledger/records.py` = 1
- `uv run nowcast predict --help` lists `--quarter`, `--kind` (and `--help`) and exit codes 0, 3, 4, 5
- `uv run pytest tests/postgres/test_pg_records.py --collect-only -m postgres`: 1 test collected (NOT executed, see Deviations 1)

## Deviations from Plan

### Not run

**1. Postgres acceptance run not executed**
- **Plan:** `CALLEDIT_REQUIRE_PG=1 uv run pytest tests/postgres/test_pg_records.py -m postgres -q -rs` must pass with 0 skipped.
- **Why not:** the orchestrator forbade running postgres-marked tests (the suite falls back to the repo-root `.env`, which may hold the live Supabase URL), and the worktree has no `.env`. I wrote `tests/postgres/test_pg_records.py` (real `run_lock` plus real builders on a `fresh_scratch` schema, one gap and two predictions, NUMERIC scale, NULL money columns, snapshot sha256) and confirmed it collects and ruff-checks, but it has never run. The Task 1 acceptance criterion for Postgres is therefore OPEN until it is run on the Supabase scratch schema or on postgres:17 in CI (Plan 01-11).

### Auto-fixed / judgement calls

**2. [Rule 2 - Missing critical functionality] Reveal-event guard also covers same-day date-only events**
- **Found during:** Task 2 design (D-27).
- **Issue:** the live `PointInTimeReader` returns an event only when `event_at < as_of`. A date-only event is stored at its late bound `D 23:59:59 IST`, so during day D (after `D 00:00 IST`, its early bound) the reader hides it, and a lock-time guard built on the live reader would let the lock through.
- **Fix:** the guard reads events through a reader anchored one day after `now` (backtest mode, used only to refuse, never to build features) and compares each event's early bound with `now` itself. A future event (early bound after now) does not refuse. Tests: `test_a_same_day_date_only_event_refuses_by_its_early_bound`, `test_a_reveal_event_that_is_still_in_the_future_does_not_refuse`.
- **Files modified:** nowcaster/src/nowcaster/lock.py

**3. [Rule 2] Chain stamp check covers gap records**
- `append_record._check_payload` compared only `recorded_at` (rules) and `locked_at` (everything else). Gap payloads carry `attempted_at`, so it was unchecked. It is now compared with the typed `created_at`. Files: nowcaster/src/nowcaster/ledger/chain.py (one line).

**4. Live unreachable-database test uses a stubbed engine**
- A real connection attempt to a closed local port took 130 s on Windows. The test swaps the engine inside `calledit_data.db.check` for one that cannot connect, so the real `run_db_check` still reports `connect: FAILED` and `run_lock` returns exit 5, with no network use.

**5. Live `rules` also demands a confirmed universe, and the Actions/main check moved to the start**
- The must_have says "predict and rules refuse unless ... isin_confirmed ... confirmed", but the task action only listed git provenance for rules. I followed the must_have via the shared `Universe.unconfirmed()`. `require_live_write_context` now runs before any file is read (still skipped for `--dry-run`).

**6. Output format**
- CLI lines carry the ticker as a prefix (`DMART LOCKED seq=1 hash=...`) so one line per company is attributable. `GITHUB_SHA` was added to the test environment scrub list.

**7. TDD order**
- Task 2: RED observed first (12 of 25 failing), then GREEN. Tasks 1 and 3: the implementation was written before its tests, so the strict RED-then-GREEN split was not observed; the Task 3 tests nevertheless assert the refusal paths directly.

**Total deviations:** 7 (3 added safety behaviours, 1 unrun acceptance check, 3 process or format).

## Open Questions for the Verifier

- **LEDG-05 edge (flagged assumption):** two locks in the same second get the same `locked_at` and different `seq`; a run straddling a company's deadline uses the once-captured `now` for every company. Both are by design and untested beyond the boundary-second tests.
- A repeated `predict` for the same (quarter, kind) appends again; nothing refuses a duplicate or a lock earlier than the latest rules record's `recorded_at`.
- `code_git_sha` is `none` for local, non-git runs; live refuses without a real commit.
- The `predict` quarter is not checked against the ledger's existing locks (no "already locked" notion), consistent with weekly locks (D-15).

## Known Stubs

None. All tests use the SYNTHETIC fixture; no real prediction was locked, no real database was contacted, and no `.env` was read.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: subprocess | nowcaster/src/nowcaster/rules.py | live provenance runs `git ls-files` and `git cat-file` with fixed arguments and the settings-configured file path, as argv (no shell) |

## Self-Check: PASSED

- lock.py, exit_codes.py, lock_helpers.py, conftest.py, test_predict_e2e.py, test_lock_guard.py, test_rules_record.py, test_pg_records.py exist
- Commits bdf2f26, 89e7f2a and 83482e3 are ancestors of HEAD
