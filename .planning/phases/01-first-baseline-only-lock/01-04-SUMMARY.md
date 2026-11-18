---
phase: 01-first-baseline-only-lock
plan: "04"
subsystem: point-in-time-store
tags: [pit-store, append-only, sqlite-triggers, postgres-triggers, alembic, point-in-time-reader, leakage, seed-loader, reveal-calendar, typer]

# Dependency graph
requires:
  - phase: 01-02
    provides: "UTCDateTime/DecimalText, make_engine (SQLite pragmas), Settings/require_live_write_context, 0001 forbid_mutation(), nowcast CLI, now_utc"
  - phase: 01-03
    provides: "FiscalQuarter, IST/date_eod_ist_utc, earliest_plausible_reveal, event_early_bound, AVAILABILITY_BASES, load_universe"
provides:
  - "Alembic 0002_pit_store: series, observations, reveal_events; SQLite <t>_no_update/_no_delete/_no_replace for all three; PG <t>_no_update_delete/_no_truncate ENABLE ALWAYS + RLS + guarded REVOKE"
  - "calledit_data.db.schema: series, observations, reveal_events, STORE_TABLES, STORE_SQLITE_TRIGGERS"
  - "calledit_data.store.writer: ObservationIn, RevealEventIn, StoreError, ensure_series, insert_observations, insert_reveal_events, observation_content_hash, reveal_event_content_hash, VINTAGES, SOURCE_KINDS, EVENT_KINDS"
  - "calledit_data.pit.reader: PointInTimeReader(engine, as_of, mode) with hooks _row_filter/_postcondition; Observation, RevealEvent, LeakageError(AssertionError), MODES"
  - "calledit_data.seed.loader: parse_seed_csv, load_seed, SeedCompanyRules, SeedParseResult, SeedRow, SeedRowError, LoadReport, SeedError, COLUMNS, CANONICAL_SEED_PATH, series_key_for"
  - "calledit_data.calendar.reveal: reveal_calendar, RevealCalendar"
  - "CLI: nowcast seed load [--csv] [--dry-run] [--require-verified]; nowcast calendar now reads stored events with a live reader"
  - "data/seed/quarterly_revenue.csv (18-column header only, LF) and data/seed/README.md (fill-in instructions)"
  - "tests/fixtures/seed_fixture_SYNTHETIC.csv (24 synthetic rows, example.invalid)"
affects: [01-05, 01-06, 01-07, 01-08, 01-09, 01-10, 01-12, phase-03-backtest]

# Actuals (#2632): chars/4 over the realized diff
actuals:
  tokens: 32680   # 130721 chars of added lines (git diff 2795f62..HEAD, before the SUMMARY commit) / 4
  tasks: 3
  commits: 4      # MEASURED: git rev-list --count 2795f62..HEAD before the SUMMARY commit
plan_head_before: 2795f62960cb15f114b62179b1ad7ff3a41c97cb
plan_head_after: 8aa296adbae60ccd0b34857fadce730609ae3e77

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Insert-only store: content_hash over identifying fields (ingested_at excluded) gives idempotent reloads with plain insert() only"
    - "Replace guards are BEFORE INSERT WHEN EXISTS on every UNIQUE key, so INSERT OR REPLACE fails even with recursive_triggers=OFF"
    - "Reads go only through PointInTimeReader: strict available_at < as_of, live adds ingested_at <= as_of, and an always-on Python post-condition"
    - "Latest vintage by the total order (available_at, ingested_at, content_hash), never obs_id"
    - "Whole-file validation with cascade suppression: each fault reports exactly one (row, column, reason)"
    - "Strict envs (rehearsal/live) pin the input path, force verified rows and refuse .invalid hosts"
    - "Read-only CLI commands never create a SQLite file (existence check before make_engine)"

key-files:
  created:
    - data/migrations/versions/0002_pit_store.py
    - data/src/calledit_data/store/__init__.py
    - data/src/calledit_data/store/writer.py
    - data/src/calledit_data/pit/__init__.py
    - data/src/calledit_data/pit/reader.py
    - data/src/calledit_data/seed/__init__.py
    - data/src/calledit_data/seed/loader.py
    - data/seed/quarterly_revenue.csv
    - data/seed/README.md
    - tests/fixtures/seed_fixture_SYNTHETIC.csv
    - tests/data/test_seed_e2e.py
    - tests/data/test_store.py
    - tests/data/test_seed_loader.py
    - tests/data/test_calendar.py
    - tests/leakage/test_reader.py
  modified:
    - data/src/calledit_data/db/schema.py
    - data/src/calledit_data/db/check.py
    - data/src/calledit_data/calendar/reveal.py
    - nowcaster/src/nowcaster/cli.py
    - tests/ledger/test_migrations.py
    - tests/ledger/test_export.py
    - .planning/WINDOWS.md

key-decisions:
  - "Observation content_hash = sha256 of series_key|period_date|value(6dp)|available_at(%Y-%m-%dT%H:%M:%S.%fZ)|availability_basis|source_ref|vintage|source_kind; ingested_at is excluded so a reload is a no-op"
  - "series also gets series_no_replace (the plan listed only no_update/no_delete); it fires only on a colliding key, so new series are still insertable"
  - "Seed row numbers count the header as row 1 (spreadsheet numbering); row 0 means the file as a whole"
  - "Date-only results/business-update dates may be today's IST date (D 23:59:59 IST is in the future, and the reader hides it until then); exact timestamps must be <= now"
  - "A UTF-8 BOM and CRLF are accepted (spreadsheet exports); fully blank rows are skipped and not counted"
  - "Extra integrity rules beyond the plan: revenue > 0 with at most 12 integer digits and no leading zeros; source_url has no fragment; one first_reported row per ticker and quarter; a restated row needs a first_reported row and a later availability; restated rows carry no business update; business_update_basis/url require business_update_at"
  - "business_update_url is optional; the business_update event cites it when present, else the row's source_ref"
  - "Rehearsal/live refuse any .invalid host in source_url and business_update_url"
  - "nowcast calendar uses a live reader at now_utc(); a missing SQLite file or a DB without the store prints 'note: no reveal events stored ...' and falls back to the earliest-plausible view; a read error exits 1 with the class name only"
  - "nowcast db check now requires the 9 store triggers as well as the 3 ledger triggers on SQLite"

patterns-established:
  - "tests/leakage/test_reader.py builds every reader through make_reader(engine, as_of, mode), so Plan 01-06 can re-parametrise it over the leaky readers"
  - "Tests that need the canonical seed CSV copy it into the temp cwd instead of chdir to the repo root, so a developer .env is never read"

requirements-completed: [PIT-01, PIT-02, PIT-03, PIT-04, DATA-01, LEAK-03]

coverage:
  - id: D1
    description: "CSV -> insert-only store -> PointInTimeReader: dry-run inserts 0; a real load inserts 24 observations and 40 reveal events; DMART reads 8 rows at 2026-11-28 and 7 before (and at) its Q2FY27 results instant; reload inserts 0"
    requirement: "DATA-01"
    verification:
      - kind: integration
        ref: "tests/data/test_seed_e2e.py#test_csv_to_reader_end_to_end; #test_reload_is_idempotent"
        status: pass
      - kind: other
        ref: "uv run alembic upgrade head && uv run nowcast seed load --dry-run --csv tests/fixtures/seed_fixture_SYNTHETIC.csv -> '24 rows seen, 0 observations inserted, 0 reveal events inserted'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every observation carries period_date, available_at, ingested_at, availability_basis and source_ref with no server defaults; missing, naive or float inputs are rejected; NOT NULL at the DB"
    requirement: "PIT-01"
    verification:
      - kind: unit
        ref: "tests/data/test_store.py#test_incomplete_or_untyped_observation_is_rejected; #test_missing_or_naive_ingested_at_is_rejected; #test_db_has_no_server_defaults_and_requires_the_time_columns"
        status: pass
    human_judgment: false
  - id: D3
    description: "UPDATE, DELETE and INSERT OR REPLACE on observations, reveal_events and series fail with 'append-only' (recursive_triggers on and off); restatements add a row and leave the original byte-identical; failed loads leave the store unchanged"
    requirement: "PIT-02"
    verification:
      - kind: unit
        ref: "tests/data/test_store.py#test_mutation_is_blocked (20 parametrised cases); #test_restatement_adds_row_and_keeps_original; #test_failed_load_leaves_store_unchanged; #test_seed_load_failing_mid_write_leaves_store_unchanged"
        status: pass
    human_judgment: false
  - id: D4
    description: "PointInTimeReader: strict available_at < as_of, live ingested_at <= as_of, LeakageError post-condition, D-05 latest vintage with a content_hash tie-break, () for empty results, stable sorted output"
    requirement: "PIT-03"
    verification:
      - kind: unit
        ref: "tests/leakage/test_reader.py (all; incl. test_row_at_exact_cutoff_is_excluded, test_live_mode_excludes_rows_ingested_after_as_of, test_postcondition_catches_a_leaky_filter)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Strict cutoff and IST boundary: a row at exactly as_of is excluded, 1 microsecond earlier is included; a 2027-01-02 00:15 IST filing is invisible at 2027-01-01T18:45:00Z and visible 1 s later"
    requirement: "LEAK-03"
    verification:
      - kind: unit
        ref: "tests/leakage/test_reader.py#test_row_at_exact_cutoff_is_excluded; #test_row_one_microsecond_before_cutoff_is_included; #test_ist_filing_after_midnight_boundary"
        status: pass
    human_judgment: false
  - id: D6
    description: "nowcast calendar derives business_update_at, results_at, early-bound reveal_at, status and earliest_plausible_reveal from events read through the PIT gate"
    requirement: "PIT-04"
    verification:
      - kind: unit
        ref: "tests/data/test_calendar.py (all, incl. test_confirmed_quarter_uses_the_early_bound, test_cli_calendar_reads_stored_events)"
        status: pass
      - kind: other
        ref: "uv run nowcast calendar --quarter Q3FY27 -> exit 0, DMART earliest_plausible_reveal 2026-12-31T18:30:00Z"
        status: pass
    human_judgment: false
  - id: D7
    description: "Whole-file seed validation: a 6-fault file lists exactly 6 errors and inserts nothing; rehearsal/live refuse the synthetic fixture, other paths and unverified rows; the header-only canonical CSV dry-runs with 0 rows"
    requirement: "DATA-01"
    verification:
      - kind: unit
        ref: "tests/data/test_seed_loader.py (57 tests, incl. test_bad_file_lists_every_error_and_inserts_nothing, test_rehearsal_refuses_synthetic_fixture, test_utf8_bom_is_accepted, test_crlf_line_endings_are_accepted)"
        status: pass
      - kind: other
        ref: "uv run nowcast seed load --dry-run -> '0 rows seen, 0 observations inserted, 0 reveal events inserted'"
        status: pass
    human_judgment: false
  - id: D8
    description: "data/seed/README.md gives correct, followable fill-in instructions (sources per company, which line, units, timestamps, verified)"
    requirement: "DATA-01"
    verification:
      - kind: other
        ref: "grep: 'Revenue from operations' x3, 'rule:date_eod_ist' x2, 'exchange_timestamp' x2, 'verified' x7; 167 lines"
        status: pass
    human_judgment: true
    rationale: "The IR page locations are starting points that were not fetched in this plan, and only a human can judge whether the instructions match the actual filings. Plan 01-09/01-10 exercise them on real rows."
  - id: D9
    description: "Postgres branch of 0002 (triggers, ENABLE ALWAYS, RLS, REVOKE) is written but not executed"
    requirement: "PIT-02"
    verification: []
    human_judgment: true
    rationale: "No Postgres in this environment; Plan 01-08 runs the PG branch and the PG trigger checks."

# Metrics
duration: ~4h wall clock (16:35Z-20:36Z), including an API rate-limit stop and resume
completed: 2026-11-18
status: complete
---

# Phase 1 Plan 04: Point-in-Time Store, Reader and Seed Loader Summary

**A seed CSV now loads in one transaction into an insert-only store: `series`, `observations` and `reveal_events`, each with append-only triggers on SQLite and Postgres. The only way back out is `PointInTimeReader(as_of)`, which enforces a strict `available_at < as_of` (plus `ingested_at <= as_of` in live mode) and raises `LeakageError` if its own post-condition fails. `nowcast calendar` now derives early-bound reveals from the stored events.**

## Performance

- **Duration:** about 4 hours of wall clock (2026-11-18T16:35Z to 20:36Z). This includes an API rate-limit stop after the Task 1 code was written but before its first commit. The run resumed in the same worktree and no work was lost.
- **Tasks:** 3/3 (Task 1 tracer, Tasks 2 and 3 TDD)
- **Files:** 15 created, 7 modified

## Accomplishments

- **Migration 0002** (hand-written, no batch mode, downgrade raises).
  - Creates `series`, `observations` (DecimalText(6) value, `UNIQUE(series_id, period_date, available_at, content_hash)`, index on `(series_id, available_at, period_date)`) and `reveal_events` (`content_hash` UNIQUE).
  - No column has a server default.
  - SQLite: 9 triggers (`<t>_no_update`, `<t>_no_delete`, `<t>_no_replace` on all three tables).
  - Postgres: reuses `forbid_mutation()` from 0001 and adds `<t>_no_update_delete` and `<t>_no_truncate`, both `ENABLE ALWAYS`, plus RLS and the guarded anon/authenticated `REVOKE`.
- **Writer** (`calledit_data.store.writer`).
  - Validation: every row is checked before anything is written. Naive datetimes, floats, unknown bases, vintages and source kinds are refused, and a `rule:date_eod_ist` value that is not exactly 23:59:59 IST is refused.
  - Idempotency: the `content_hash` excludes `ingested_at`, so reloading the same content inserts nothing. Only plain `insert()` is used.
  - Clock: `ingested_at` is always a parameter; the writer never reads the wall clock.
- **Reader** (`calledit_data.pit.reader`).
  - `as_of` must be an aware datetime with a zero UTC offset.
  - The `_row_filter` and `_postcondition` hooks are overridable, ready for the leaky readers in Plan 01-06.
  - The latest vintage is chosen by `(available_at, ingested_at, content_hash)`.
  - `series()` returns a tuple sorted by period; `reveal_events()` applies the same gate to `event_at`.
- **Seed loader and `nowcast seed load`.**
  - Every D-25 rule plus the cross-row rules is checked over the whole file, and each fault yields exactly one `(row, column, reason)`.
  - The load is one transaction under `BEGIN IMMEDIATE` (SQLite) or an advisory lock (PG).
  - Rehearsal and live accept only `data/seed/quarterly_revenue.csv`, force every row to be verified and refuse `.invalid` hosts. A live write also requires the GitHub Actions main-branch context.
- **Reveal calendar.**
  - `reveal_calendar(reader, ticker, quarter, offset_days)` takes the earliest event of each kind as stored, and `reveal_at` is the minimum early bound (D-27).
  - `nowcast calendar` uses a live reader at `now_utc()` and never creates a database file. This closes WINDOWS id 2, which is now marked fixed.
- **Seed files.** `data/seed/quarterly_revenue.csv` holds the exact 18-column header (LF). `data/seed/README.md` (167 lines) gives the fill-in instructions.
- **`nowcast db check`** now requires the store triggers too, so a database that stopped at 0001 reports FAIL.

## Task Commits

1. **Task 1: Tracer, CSV through the store to the reader**: `7865495` (feat)
2. **Task 2: Store and reader guarantees**: `197dbbd` (test)
3. **Task 3: Seed validation, README and calendar**: `ec9ea82` (test, RED) and `8aa296a` (feat, GREEN)

**Plan metadata:** the docs(01-04) commit that adds this SUMMARY and the WINDOWS.md update.

## Verification (exact output)

- `uv run pytest -q`: **`390 passed in 33.40s`** (the baseline was 255, so this plan adds 135 tests).
- `uv run ruff check .`: **`All checks passed!`**. `ruff format` reports every touched file formatted.
- `uv run pytest tests/data tests/leakage -q`: `246 passed in 13.10s`.
- Task 1 verify: `uv run pytest tests/data/test_seed_e2e.py -q` gives `3 passed`. `uv run alembic upgrade head && uv run nowcast seed load --dry-run --csv tests/fixtures/seed_fixture_SYNTHETIC.csv` prints `seed load (dry run: nothing inserted): 24 rows seen, 0 observations inserted, 0 reveal events inserted`.
- Task 2 verify: `uv run pytest tests/data/test_store.py tests/leakage/test_reader.py -q` gives `64 passed`.
- Task 3 verify: `uv run pytest tests/data/test_seed_loader.py tests/data/test_calendar.py -q` gives `68 passed`. `uv run nowcast seed load --dry-run` prints `seed load (dry run: nothing inserted): 0 rows seen, 0 observations inserted, 0 reveal events inserted`.
- `uv run nowcast calendar --quarter Q3FY27` exits 0, and the DMART earliest plausible reveal is `2026-12-31T18:30:00Z`.
- `uv run nowcast db check` prints `triggers: ok (...12 names...)` and `result: OK`.
- Acceptance greps:
  - `server_default` in schema.py: 0.
  - `observations_no_replace` in 0002: 2.
  - `head -1 data/seed/quarterly_revenue.csv` prints the 18-column header.
  - The README contains all 4 required strings.
  - All named tests exist.

## TDD Gate Compliance

- **Task 2:** the tests were written against the Task 1 code, as the plan orders, so there is no separate RED commit (the same as 01-02 and 01-03). All 64 passed on the first run, and the suite exposed no defect in `writer.py` or `reader.py`.
- **Task 3:** RED `ec9ea82`. Collection failed (`ImportError: RevealCalendar`), and 37 of 57 loader tests failed. GREEN `8aa296a`: 68 passed. The first GREEN run exposed three bugs in the new tests themselves, which were fixed in the GREEN commit:
  - duplicate keyword arguments in row builders;
  - two CLI rows that were genuine duplicates, which the loader rightly flagged;
  - a calendar test that ingested its events after `as_of` under a live reader.

## Decisions Made

See `key-decisions` in the frontmatter. The most consequential is the observation `content_hash` field list and format. It decides idempotency, and Plan 01-07's snapshots cite these hashes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing ledger tests assumed the ledger was the only migration and the only trigger set**
- **Found during:** Task 1 (full suite)
- **Issue:** `test_migrations.py` pinned the head revision at `0001`, and the `test_export.py` throwaway fixture asserted that zero triggers remained after stripping only the `predictions` triggers.
- **Fix:** The head revision is now `0002`, and the fixture counts only `predictions` triggers. Both tests keep their intent.
- **Commit:** 7865495

**2. [Rule 2 - Missing critical] `db check` would have reported OK without the store triggers**
- **Fix:** `REQUIRED_SQLITE_TRIGGERS` = ledger plus store triggers. A database at 0001 now reports `MISSING ... (run: uv run alembic upgrade head)`.
- **Commit:** 7865495

**3. [Rule 2 - Missing critical] `series_no_replace` added**
- **Issue:** The plan gave `series` only no_update and no_delete. With `recursive_triggers=OFF`, `INSERT OR REPLACE` could then silently swap a series row.
- **Fix:** A conditional replace guard. It fires only on a colliding `series_id` or `series_key`, so new series can still be inserted.
- **Tests:** `series-insert-or-replace` is in the mutation matrix.
- **Commit:** 7865495

**4. [Rule 2 - Missing critical] Validation went further than the plan's list** (threats T-01-14, T-01-15, T-01-16)
- **Rules added:** see key-decisions (positive and bounded revenue, no URL fragment, one first_reported per quarter, restated-row rules, business-update field coupling, `.invalid` refused in `business_update_url` too).
- **Why:** These rows become permanent in an insert-only store, so a bad row cannot be corrected later.
- **Commits:** ec9ea82, 8aa296a

**5. [Rule 2 - Missing critical] A write lock on the seed load**
- **Fix:** `BEGIN IMMEDIATE` on SQLite and `pg_advisory_xact_lock` on Postgres around the existing-hash read and the inserts, mirroring `append_record`. The UNIQUE keys and replace triggers remain the backstop.
- **Commit:** 7865495

**6. [Minor - deliberate interpretation] BOM and CRLF are accepted rather than refused**
- **Issue:** The plan's read call says `encoding="utf-8"`, and its flagged DATA-01 edge asks for BOM and CRLF tests.
- **Fix:** The file is read as `utf-8-sig`, so a spreadsheet export loads, and both cases are tested. The canonical file itself stays LF without a BOM, and a test asserts its exact bytes.

**7. [Minor - test safety] Canonical-CSV tests do not chdir to the repo root**
- **Why:** In the main checkout, `get_settings()` would then read the developer `.env`, which may hold the live URL. The tests copy the committed file into the temp cwd instead.

**8. [Minor - scope] Small additions**
- New helpers: `observation_content_hash`, `reveal_event_content_hash`, `StoreError`, `series_key_for`, `COLUMNS`, `CANONICAL_SEED_PATH` and `LoadReport.dry_run/ok`.
- A `forbid_synthetic` keyword on `parse_seed_csv`.
- An `as_of:` line in the `nowcast calendar` output, and the `(early bound, D-27)` suffix on `reveal_at`.

**9. [Environment] The run was interrupted and resumed**
- An API rate limit stopped the first run before any commit. On resume, the branch and base check was re-run (base `2795f62`), the uncommitted files were reviewed, and work continued.

---

**Total deviations:** 9 (1 bug, 4 missing-critical items, 3 minor, 1 environment event).
**Impact on plan:** No scope change. Every addition tightens immutability, leakage or data-honesty guarantees.

## Known Stubs

None that block the plan goal. `data/seed/quarterly_revenue.csv` is deliberately header-only; Plan 01-09 drafts the real rows and the user verifies them (D-22). WINDOWS id 2 (the calendar stub from 01-03) is now **fixed**.

## Threat Flags

None. There are no new network endpoints or auth paths. The new schema surfaces were in the plan's threat model, and their mitigations are in place:
- T-01-13: triggers and a writer with no update path.
- T-01-14: whole-file validation and one transaction.
- T-01-15: the late bound, basis/format matching, the strict `<` and the post-condition.
- T-01-16: a ledger-safe charset for `source_url` and `page_ref`.
- T-01-17: the canonical path, verified rows and `.invalid` refusal in strict envs.
- T-01-SC: no new dependencies.

## Flagged Assumptions (edge probes)

- **PIT-04:**
  - A same-day business update and results are covered by `test_same_ist_date_business_update_and_results`.
  - A date-only early bound before an exact event is covered by `test_same_ist_date...` and `test_exact_results_before_date_only_business_update`.
  - An event ingested after the lock is excluded by the live reader (`test_event_ingested_after_as_of_is_not_visible_in_live_mode`).
  - Open for the verifier: a date-only event becomes *visible* only after its late bound, so between `D 00:00 IST` and `D 23:59:59 IST` the calendar still shows `expected`. That is intended, because only known events count, but the lock guard must keep using `earliest_plausible_reveal`.
- **DATA-01:**
  - BOM, CRLF, a trailing blank line and a quoted comma are covered by tests.
  - A restated row with no first_reported row is an error.

## Issues Encountered

None beyond the deviations. `.env` was never opened. The tracer verify ran `alembic upgrade head` against the worktree's gitignored `data/local.db`, which was removed before hand-off.

## User Setup Required

None.

## Next Phase Readiness

- Plan 01-05 (baseline) reads `PointInTimeReader.series("rev.consolidated.<T>")`. Plan 01-06 subclasses `_row_filter`/`_postcondition` and swaps `make_reader` in `tests/leakage/test_reader.py`.
- Plan 01-08 must run the Postgres branch of 0002 and add the PG store-trigger checks to `db check`.
- Plan 01-09 fills `data/seed/quarterly_revenue.csv` following the README.
- STATE.md and ROADMAP.md were not touched. The orchestrator owns those writes.

---
*Phase: 01-first-baseline-only-lock*
*Completed: 2026-11-18*

## Self-Check: PASSED

- FOUND: 0002_pit_store.py, store/writer.py, pit/reader.py, seed/loader.py, data/seed/quarterly_revenue.csv, data/seed/README.md, tests/fixtures/seed_fixture_SYNTHETIC.csv, and the 5 new test files
- FOUND: commits 7865495, 197dbbd, ec9ea82, 8aa296a are ancestors of HEAD
