# Phase 2: The Record Runs Itself - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 02-CONTEXT.md.

**Date:** 2026-11-26
**Phase:** 2 - The Record Runs Itself
**Areas discussed:** Unattended live locks, Redundant final lock + alerts, Forward collectors, Verifier + official call

---

## Unattended live locks
- Live authority: **Cron + kill switch** (alt: cron only; environment approval).
- Cadence: **Tuesday 06:00 UTC** (alt: Monday 00:30 UTC; Sunday 18:30 UTC).
- Guard rails: **Verifier PASS first** (alt: verifier + full tests; existing guards only).
- Missed week: **No catch-up, alert** (alt: auto-retry same day; manual only).

## Redundant final lock + alerts
- Triggers: **Two GitHub crons** (alt: GitHub + external scheduler; GitHub + local task).
- Alerts: **Watchdog + issue** (alt: failure emails only; issue + external ping).
- Supabase: **Daily check in watchdog** (alt: targeted pre-lock check; paid tier).
- Dry run: **Rehearsal mode** (alt: fork repo; dispatch only).

## Forward collectors
- Careers: **Probe, then collect where allowed** (alt: skip; public ATS only).
- Storage: **Supabase + hashed at lock** (alt: daily git export; git only).
- Failure: **Retry then fail** (chosen over the recommended "failed run, no rows"; no rows are written either way).
- Daily time: **02:00 UTC, IST date** (alt: 18:45 UTC; twice daily).

## Verifier + official call
- Verifier: **Stdlib-only standalone** (alt: imports nowcaster; Python + JS).
- Scope: **Chain + snapshots + proofs** (alt: chain only; plus explorers).
- Official call: **Last valid prediction**, user-worded: not VOID, before reveal, bound via rules_seq/rules_hash, a gap never voids it.
- Gates: **Every lock, push and daily** (alt: lock + push; lock only).

## User addition (end of discussion)
- The daily watchdog automatically upgrades pending `.ots` proofs, commits as github-actions[bot], runs the explorer check, and alerts if a proof is still pending after 48h (D-09).
- Other candidate areas (seed backfill to Q3 FY23, grading/export commit) deferred to their later phases.

## Claude's Discretion
Cron minutes within the 48h rule, file and label names, collector_runs columns, backoff numbers, CLI output formats.

## Deferred Ideas
Seed backfill to Q3 FY23 (Phase 3); grading/export commit (Phases 4-5).
