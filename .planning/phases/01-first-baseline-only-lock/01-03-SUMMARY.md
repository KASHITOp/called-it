---
phase: 01-first-baseline-only-lock
plan: "03"
subsystem: calendar-and-universe
tags: [fiscal-calendar, ist-utc, leakage, pydantic, tomllib, typer, hypothesis, config]

# Dependency graph
requires:
  - phase: 01-02
    provides: "nowcast CLI skeleton, Settings.universe_path, calledit-ledger-v1 canonical.validate/format_ts, tests/conftest.py scrubbed-env fixture"
provides:
  - "calledit_data.calendar.fiscal.FiscalQuarter (parse, label, start, end, shift, containing, period_start_utc; total ordering; integer-only)"
  - "calledit_data.calendar.tz: IST fixed +05:30, to_utc, to_ist, ist_date, date_eod_ist_utc (late bound, D-24), date_start_ist_utc (early bound, D-27)"
  - "calledit_data.calendar.reveal: earliest_plausible_reveal (D-14), event_early_bound (D-27), AVAILABILITY_BASES"
  - "config/universe.toml (universe-1): DMART, ETERNAL, TITAN; breaks eternal-blinkit-inventory (Q1FY26..Q3FY26, unconfirmed) and gst2.0 (2025-09-22)"
  - "nowcaster.universe: load_universe, parse_universe, Universe (enabled, company, breaks_for, universe_sha256), Company, Break, SymbolHistory, UniverseError"
  - "CLI: nowcast universe, nowcast calendar --quarter LABEL"
affects: [01-04, 01-05, 01-06, 01-07, 01-09, 01-10, phase-03-feat-01, phase-03-feat-03]

# Actuals (#2632): chars/4 over the realized diff
actuals:
  tokens: 13532   # (48548 chars of new files + 5581 chars of cli.py diff) / 4
  tasks: 2
  commits: 2      # MEASURED: git rev-list --count 4d1c8a4..HEAD before the SUMMARY commit
plan_head_before: 4d1c8a4af3816c14325f643a43643d731f9bf201
plan_head_after: 004f224004fafa0a33e127d02f96c94a86e4b4ed

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Calendar code is pure: no I/O, no wall clock, naive datetimes rejected at every entry point"
    - "Date-only events carry two bounds: late (D 23:59:59 IST) for availability, early (D 00:00:00 IST) for deadlines, VOID and cutoffs"
    - "Config is hashed as exact bytes (universe_sha256) before parsing; the hash can never be written into the file"
    - "Strict pydantic config models: extra=forbid, Strict* types (no string-to-int/bool coercion), every string inside the ledger charset"
    - "Label parsing is ASCII-only ([0-9], literal optional space): Unicode digits and whitespace are refused"

key-files:
  created:
    - data/src/calledit_data/calendar/__init__.py
    - data/src/calledit_data/calendar/fiscal.py
    - data/src/calledit_data/calendar/tz.py
    - data/src/calledit_data/calendar/reveal.py
    - config/universe.toml
    - nowcaster/src/nowcaster/universe.py
    - tests/leakage/__init__.py
    - tests/leakage/test_fiscal.py
    - tests/leakage/test_time_boundaries.py
    - tests/data/__init__.py
    - tests/data/test_universe.py
  modified:
    - nowcaster/src/nowcaster/cli.py
    - .planning/WINDOWS.md

key-decisions:
  - "FiscalQuarter.fy holds the full ending year (FY27 -> 2027); the range is FY2000-FY2099, and shifting outside it raises instead of wrapping"
  - "ISINs must pass the ISO 6166 (Luhn) check digit as well as the IN-prefix regex. All three configured ISINs pass, but that does not confirm them: isin_confirmed stays false for ETERNAL and TITAN"
  - "Break references are checked in both directions: every break_id must exist and apply to the company, and every break that applies (including '*') must be listed in that company's break_ids"
  - "Quarter labels in the config must be canonical ('Q1FY26'); the CLI accepts any case and one optional space"
  - "event_early_bound refuses a rule:date_eod_ist value that is not exactly D 23:59:59 IST, rather than guessing which day was meant"
  - "nowcast calendar exits 2 on a bad label (usage error) and exits 1 on an invalid universe config"

patterns-established:
  - "tests/leakage/ holds the time-boundary suites. Plan 01-04 adds the leaky-reader meta tests next to them"
  - "Universe-invalidity tests mutate a temp copy of the real config by an anchored text replacement, so each case differs from the committed file by one edit"

requirements-completed: [FOUND-03, FOUND-05, PIT-04, PIT-05, LEAK-03]

coverage:
  - id: D1
    description: "nowcast calendar --quarter Q3FY27 prints DMART 2026-12-31T18:30:00Z, TITAN 2027-01-01T18:30:00Z, ETERNAL 2027-01-06T18:30:00Z (earliest-plausible part of PIT-04)"
    requirement: "PIT-04"
    verification:
      - kind: other
        ref: "uv run nowcast calendar --quarter Q3FY27 | grep -c 2026-12-31T18:30:00Z -> 1 (exit 0)"
        status: pass
      - kind: unit
        ref: "tests/data/test_universe.py#test_cli_calendar_q3fy27; tests/leakage/test_time_boundaries.py#test_earliest_plausible_reveal_q3fy27"
        status: pass
    human_judgment: false
  - id: D2
    description: "One config file controls the universe; enabled = false drops a company from Universe.enabled() and from the calendar, with no code change, and changes universe_sha256"
    requirement: "FOUND-03"
    verification:
      - kind: unit
        ref: "tests/data/test_universe.py#test_disabling_company_drops_it_from_enabled; #test_cli_calendar_skips_disabled; #test_cli_universe_lists_everything"
        status: pass
    human_judgment: false
  - id: D3
    description: "Fiscal quarters: Q3FY27 = 2026-10-01..2026-12-31, FY27 = 2026-04-01..2027-03-31, exact boundaries, shift(-4), strict parse, a 200-example round-trip property"
    requirement: "FOUND-05"
    verification:
      - kind: unit
        ref: "tests/leakage/test_fiscal.py (all, incl. test_roundtrip_properties: 200 passing examples)"
        status: pass
    human_judgment: false
  - id: D4
    description: "IST/UTC conversion and the late/early bounds for date-only events; IST agrees with ZoneInfo('Asia/Kolkata') (conversion half of LEAK-03)"
    requirement: "LEAK-03"
    verification:
      - kind: unit
        ref: "tests/leakage/test_time_boundaries.py (incl. test_ist_matches_zoneinfo, test_rule_basis_row_is_not_visible_to_a_cutoff_earlier_that_day)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Structural breaks declared in config (config half of PIT-05): eternal-blinkit-inventory as a quarter range and gst2.0 as a date, validated and printed by nowcast universe"
    requirement: "PIT-05"
    verification:
      - kind: unit
        ref: "tests/data/test_universe.py#test_repo_config_values; #test_invalid_configs_fail_to_load[start_q_after_end_q|date_break_without_effective|unknown_break_id|missing_applicable_break]"
        status: pass
    human_judgment: false
  - id: D6
    description: "Values in the config that need the user's confirmation: ETERNAL/TITAN ISINs, the Eternal break range Q1FY26..Q3FY26 (RESEARCH A7), and the provisional GST state lists"
    verification: []
    human_judgment: true
    rationale: "The facts come from filings and shareholder letters that no test can check. They are flagged unconfirmed (isin_confirmed=false, confirmed=false) for the user to settle at Plan 01-10, and Plan 01-09 pins the Eternal range"

# Metrics
duration: ~79m wall clock (includes a transient API network interruption and resume)
completed: 2026-11-18
status: complete
---

# Phase 1 Plan 03: Fiscal Calendar, IST Rules and Company Universe Summary

**Indian fiscal quarters, fixed-offset IST, and the late and early bounds for date-only events are now pure, tested functions. `config/universe.toml` drives two commands: `nowcast universe` lists the companies and breaks with a SHA-256 of the file bytes, and `nowcast calendar --quarter Q3FY27` prints DMART's earliest plausible reveal as 2026-12-31T18:30:00Z, TITAN's as 2027-01-01T18:30:00Z and ETERNAL's as 2027-01-06T18:30:00Z.**

## Performance

- **Duration:** about 79 minutes of wall clock. This includes a transient API network interruption (ENOTFOUND) after the CLI commands were written. The run then resumed in the same worktree and no work was lost.
- **Started:** 2026-11-18T15:09:36Z
- **Completed:** 2026-11-18T16:29:30Z
- **Tasks:** 2/2 (Task 1 tracer, Task 2 TDD)
- **Files:** 11 created, 2 modified (`cli.py` and `.planning/WINDOWS.md`)

## Accomplishments

- **`calledit_data.calendar`** (pure functions, with no I/O and no wall clock)
  - `FiscalQuarter(fy, q)` is a frozen, chronologically ordered dataclass. It supports `parse`, `label`, `start`, `end`, `shift`, `containing` and `period_start_utc`, and all arithmetic is integer-only.
  - Parsing is ASCII-strict and case-insensitive, allows one optional space, and covers FY2000-2099. Every other input raises `ValueError` naming the label.
  - `IST` is `timezone(+05:30, "IST")`. `to_utc`, `to_ist` and `ist_date` reject naive datetimes.
  - `date_eod_ist_utc` gives the late bound (availability, D-24) and `date_start_ist_utc` the early bound (deadlines, D-27). Both reject `datetime` instances, so a time and zone can never be silently dropped.
  - `earliest_plausible_reveal(q, n)` is quarter end + n days at 00:00 IST, as UTC (D-14).
  - `event_early_bound` returns an `exchange_timestamp` unchanged. For `rule:date_eod_ist` it returns the IST date at 00:00 IST.
- **`config/universe.toml`** is LF-only ASCII and committed `-text`. It holds the three companies with exactly the planned fields and values.
  - ETERNAL carries the hashed label `low confidence: post-break comparables limited` and `symbol_history` ZOMATO until 2025-04-08.
  - `play_package_ids` is empty for every company, because none has been verified.
  - Breaks: `eternal-blinkit-inventory` (quarter_range Q1FY26..Q3FY26, `confirmed = false`) and `gst2.0` (date 2025-09-22, applies to `*`, `confirmed = true`).
- **`nowcaster.universe`** uses strict pydantic v2 models (`extra="forbid"`, frozen).
  - `universe_sha256` is the SHA-256 of the exact bytes read. The file is parsed with `tomllib.loads(bytes.decode("utf-8"))`.
  - Validation covers: ticker and ISIN regexes plus the ISIN check digit; offsets 0-30; https source URLs; canonical quarter labels with `start_q <= end_q`; kind-specific break fields; and the ledger charset on every string.
  - Break references are checked in both directions (see key-decisions).
- **CLI**
  - `nowcast universe` prints every company (disabled ones marked `disabled`) with all fields, then every break, then `universe_sha256`.
  - `nowcast calendar --quarter` prints one block per enabled company: `business_update_at`, `results_at` and `reveal_at` (all `none`), `status: expected`, and the earliest plausible reveal in UTC and IST.
  - Neither command takes an as-of override.

## Task Commits

1. **Task 1: Tracer, from config/universe.toml through the fiscal and reveal rules to `nowcast universe` and `nowcast calendar`:** `057ffe4` (feat)
2. **Task 2: Fiscal, IST/UTC-boundary and universe tests:** `004f224` (test)

**Plan metadata:** the docs(01-03) commit that adds this SUMMARY and the WINDOWS.md entry.

## Verification (exact output)

- `uv run nowcast calendar --quarter Q3FY27 | grep -c "2026-12-31T18:30:00Z"` prints `1` and exits 0. The output also contains `2027-01-01T18:30:00Z` (TITAN) and `2027-01-06T18:30:00Z` (ETERNAL).
- `uv run nowcast calendar --quarter Q3FY` prints `calendar: refused: not a fiscal quarter label: 'Q3FY' (expected e.g. 'Q3FY27')` and exits 2.
- `uv run nowcast universe` exits 0. Its output contains DMART, ETERNAL, TITAN, `eternal-blinkit-inventory`, `gst2.0`, `2025-09-22`, `Q1FY26`, `confirmed: false` and `universe_sha256: 75ad6a39...963e`.
- `grep -c "low confidence: post-break comparables limited" config/universe.toml` prints `1`. `grep -c $'\r' config/universe.toml` prints `0`.
- `uv run pytest tests/leakage/test_fiscal.py tests/leakage/test_time_boundaries.py tests/data/test_universe.py -q` reports **`111 passed in 4.03s`**.
- The hypothesis statistics for `test_roundtrip_properties` show `200 passing, 0 failing, and 0 invalid test cases`.
- `uv run pytest -q` reports **`255 passed in 10.04s`**. The baseline was 144, so this plan adds 111 tests.
- `uv run ruff check .` reports **`All checks passed!`**. `ruff format --check` flags only two pre-existing planning markdown files (01-RESEARCH.md and ARCHITECTURE.md), which this plan did not touch.

## TDD Gate Compliance

Task 2 writes tests against Task 1 code that already existed, as the plan orders, so there is no separate RED commit (the same as 01-02 Task 3). The first run had 2 failures among 111 tests. Both came from a test-helper bug: the replacement anchor contained the text being replaced. Once that was fixed, everything passed. The suite exposed no defect in `fiscal.py` or `universe.py`.

## Decisions Made

See `key-decisions` in the frontmatter. The universe file bytes and the D-14/D-24/D-27 rules feed the seq-0 rules record (Plan 01-07/01-12), so changing them after that point needs a new rules record.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The plan's parse regex would accept non-ASCII digits and tabs**
- **Found during:** Task 1
- **Issue:** The plan's regex `(?i)^Q([1-4])\s?FY(\d{2})$` contradicts its own behaviour spec. In Python, `\d` matches Devanagari or full-width digits, `\s` matches tabs and newlines, and `$` matches before a trailing newline.
- **Fix:** `re.fullmatch` with `Q([1-4]) ?FY([0-9]{2})` and `re.IGNORECASE | re.ASCII`. Tests reject Arabic-Indic, Devanagari and full-width digits, tabs, double spaces and trailing newlines.
- **Files:** data/src/calledit_data/calendar/fiscal.py
- **Commit:** 057ffe4

**2. [Rule 2 - Missing critical] Config validation went further than the plan's list**
- **Found during:** Task 1 (threat T-01-12, tampering with hashed identifiers)
- **Additions:**
  - the ISIN ISO 6166 check digit;
  - the reverse break check (an applicable break must be listed) and `applies_to` checks against known tickers;
  - canonical quarter spelling in the config;
  - `Strict*` types, so `"1"` and `"true"` are not coerced;
  - the ledger charset on every string, not only labels;
  - unique ISINs and break ids;
  - a refusal if the file itself contains a `universe_sha256` key.
- **Why:** These values are hashed into ledger records. A typo, or a silently coerced value, would be permanent.
- **Files:** nowcaster/src/nowcaster/universe.py
- **Commit:** 057ffe4

**3. [Rule 2 - Missing critical] Guards in the time helpers**
- `event_early_bound` refuses a `rule:date_eod_ist` value that is not exactly 23:59:59 IST, because that means the basis and the value disagree.
- The date-bound helpers and `FiscalQuarter.containing` reject `datetime` instances, which are a subclass of `date` and would lose their time and zone.
- **Commit:** 057ffe4

**4. [Minor - scope] Small additions beyond the interface block**
- New helpers: `to_ist`, `ist_date`, `AVAILABILITY_BASES`, `parse_universe(bytes)`, `UniverseError`, `Break.applies`, `Break.start_quarter`/`end_quarter` and `SymbolHistory`.
- `nowcast calendar` also prints a header line with the quarter and its dates, plus `universe_sha256`.
- Task 2 added CliRunner tests for both commands to `tests/data/test_universe.py`.

**5. [Environment] The run was interrupted and resumed**
- A transient API network error (ENOTFOUND) cut off the first run after the Task 1 code was written but before any commit. On resume, the branch check was re-run (branch `worktree-agent-a898198527297aea1`, base `4d1c8a4`), the uncommitted files were reviewed, and work continued. Nothing was lost.

---

**Total deviations:** 5 (1 bug, 2 missing-critical items, 1 minor scope addition, 1 environment event).
**Impact on plan:** No scope change. The fixes tighten the guarantees around hashed config and timestamps.

## Known Stubs

| File | Line | Reason |
|------|------|--------|
| nowcaster/src/nowcaster/cli.py | 170 | `nowcast calendar` prints `business_update_at: none`, `results_at: none`, `reveal_at: none` and `status: expected` for every company. The plan specifies this, because no reveal events are stored before Plan 01-04, which must replace the literals with stored events. The entry is recorded in `.planning/WINDOWS.md` (id 2). It does not block this plan's goal: the earliest-plausible reveal, which governs the Q3FY27 lock, is fully wired. |

## Threat Flags

None. There are no new network endpoints, auth paths or schema changes. The only new file read is `config/universe.toml` via `Settings.universe_path`, which already existed (T-01-11). The threat-register mitigations are in place:
- T-01-10: naive datetimes are rejected and boundary tests exist.
- T-01-11: `universe_sha256` is computed over the exact bytes, and the file is `-text` and LF-only.
- T-01-12: the confirmed flags stay false.
- T-01-SC: no new dependencies.

## Flagged Assumption (PIT-05 edge probe)

The breaks are declared and validated here, including the `*` wildcard and per-company references. This plan does not cover a break range touching the TTM window at one end, or a company with no applicable breaks (`breaks_in_window = "none"`). Plan 01-05 owns those cases and they remain open for the verifier.

## Issues Encountered

None beyond the deviations above. `.env` was never opened. Tests run in the scrubbed temp-cwd fixture and point `CALLEDIT_UNIVERSE_PATH` at the repo config explicitly.

## User Setup Required

None. The user confirms the ISINs, the Eternal break range and the GST state lists at Plan 01-10.

## Next Phase Readiness

- Plans 01-04 to 01-07 can import `FiscalQuarter`, the tz helpers, `earliest_plausible_reveal`, `event_early_bound` and `load_universe` as listed under `provides`.
- Plan 01-04 must store reveal events and wire them into `nowcast calendar` (WINDOWS id 2).
- Plan 01-07 must refuse live locks while `isin_confirmed` or a break's `confirmed` is false.
- STATE.md, ROADMAP.md and REQUIREMENTS.md were not touched. The orchestrator owns those writes after the wave.

---
*Phase: 01-first-baseline-only-lock*
*Completed: 2026-11-18*

## Self-Check: PASSED

- FOUND: data/src/calledit_data/calendar/{fiscal,tz,reveal}.py, config/universe.toml, nowcaster/src/nowcaster/universe.py, tests/leakage/test_fiscal.py, tests/leakage/test_time_boundaries.py, tests/data/test_universe.py
- FOUND: commits 057ffe4 and 004f224 on this branch (`git log 4d1c8a4..HEAD`)
- Every acceptance criterion was re-run and passed (see Verification)
