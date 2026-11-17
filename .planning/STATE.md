---
gsd_state_version: "1.0"
current_phase: 1
current_phase_name: First Baseline-Only Lock
status: planning
stopped_at: Phase 1 context gathered
last_updated: "2026-11-17T23:18:18.623Z"
last_activity: 2026-11-17
last_activity_desc: Roadmap approved (6 phases, 66/66 v1 requirements mapped, all 24 [CRITICAL] in Phase 1); GST 2.0 treatment moved to Phase 3 as FEAT-03
state_head: 7dedf17a7ae8fd0346448821481c1b063a5e2a43
progress:
  total_phases: 6
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-11-17)

**Core value:** Provably honest predictions: every call uses only data public at the time, is locked with a verifiable hash before the reveal, is never edited, and is graded in public against a naive baseline, even when the baseline wins.
**Current focus:** Phase 1 — First Baseline-Only Lock (critical path; the lock is due on or before 1 Dec 2026)

## Current Position

Phase: 1 of 6 (First Baseline-Only Lock)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-11-17 — Roadmap approved (6 phases, 66/66 v1 requirements mapped, all 24 [CRITICAL] in Phase 1); GST 2.0 treatment moved to Phase 3 as FEAT-03

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: -
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: -
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in the PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: Phase 1 holds every [CRITICAL] requirement (24) and nothing else. It ends with the first baseline-only lock, git- and OTS-witnessed, by 1 Dec 2026.
- Roadmap: the ledger comes before the main model. Forward-collector cron and weekly-lock automation sit in Phase 2, because missed days and weeks can never be recovered or backfilled.
- Roadmap: FEAT-02 freezes only the Eternal break treatment in Phase 1. The GST 2.0 treatment (FEAT-03) is decided in Phase 3 after seeing the GSTN files, and frozen in the ledger before the first model lock (~15 Dec). User decision, 2026-11-17.
- Roadmap: the OPS-02 final-lock dry run and OPS-03 CI land in Phase 2, well ahead of the mid-December deadline. OPS-01 consolidates all cron and the export commit in Phase 5.
- Roadmap: if ridge is not frozen by ~15 Dec, baseline-only official calls are the accepted fallback.
- Requirements: the app-rank signal is Apple RSS rank plus Play app details, with no Play chart scraping.

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1] The DATA-01 seed CSV has to be curated by hand from exchange filings, because NSE and BSE block automated access. It needs at least the quarters the Q3 FY27 baseline uses, with `business_update_at` timestamps and source URLs. It gates the first lock, so start now. The full 12-16 quarter history can be finished in time for the Phase 3 backtest.
- [Phase 1] The repo has no GitHub remote yet, and the LEDG-09 witness needs one. A Supabase project is also needed for the Postgres trigger tests and the production ledger. Decide where the canonical ledger lives before the first lock.
- [Phase 1] Research flag: the OpenTimestamps client and upgrade flow, and Postgres trigger-bypass coverage on Supabase.
- [Phase 1] The baseline-v1 definition (the trailing-YoY window) and the Eternal treatment must be written down before the lock. Eternal's call should carry a "low confidence" label.
- [Phase 2] Research flag: per-company careers-site endpoints and robots.txt.
- [Phase 2] Holiday risks: GitHub cron delays and a Supabase free-tier pause over the New Year.
- [Phase 2] GitHub disables cron after 60 days of repo inactivity.
- [Phase 3] The GST 2.0 treatment (FEAT-03) must be frozen before the first model lock (~15 Dec), so Phase 3 cannot slip past that.
- [Phase 3] Research flag: the GSTN Excel layout and restatements. Also check whether trendspyg works from Actions IPs, and apply for official Trends API alpha access now.

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-11-17T23:18:18.291Z
Stopped at: Phase 1 context gathered
Resume file: .planning/phases/01-first-baseline-only-lock/01-CONTEXT.md
