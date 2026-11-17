# Phase 1: First Baseline-Only Lock - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-11-18
**Phase:** 01-first-baseline-only-lock
**Areas discussed:** Baseline + Eternal break, Grading rules, Ledger home & witnesses, Seed CSV sourcing

**Setup info supplied with area selection:** the public GitHub remote `KASHITOp/called-it` (add as origin, gh authenticated); `.env` holds the Supabase session-pooler `DATABASE_URL`, never to be overwritten, committed or printed; add `.env.example`; run `git check-ignore .env` before the first push.

---

## Baseline + Eternal break

| Option | Description | Selected |
|--------|-------------|----------|
| TTM YoY | Last 4 revealed quarters vs the prior 4; smooths festival shifts; ~9 seed rows/company | ✓ |
| Latest quarter YoY | Most recent quarter vs a year earlier; noisy | |
| Same-quarter YoY | Q3 FY26's own YoY carried forward; stale | |

| Option | Description | Selected |
|--------|-------------|----------|
| Post-break window | Fall back to latest post-break pair (else least-straddling); always a low-confidence label | ✓ |
| Unadjusted + label | Same formula, label only; likely forecasts triple-digit growth | |
| Skip Eternal in lock 1 | Disable until researched; late convergence record | |

| Option | Description | Selected |
|--------|-------------|----------|
| Latest known at as_of | Most recent vintage with available_at < as_of | ✓ |
| Always first-reported | Ignore later restatements in inputs | |

| Option | Description | Selected |
|--------|-------------|----------|
| Baseline ignores GST 2.0 | Only Eternal adjusts the baseline | |
| Flag but don't adjust | Payload records that the TTM window straddles GST 2.0 | ✓ |

**Notes:** the user added a frozen rule: if any seed quarter needed for a lock is missing, refuse that company's lock and record a visible gap, never impute. The Eternal break range is pinned from filings with the source cited in config.

---

## Grading rules

| Option | Description | Selected |
|--------|-------------|----------|
| \|error\| ≤ 3% | Plus inside the 80% interval for model calls | ✓ |
| \|error\| ≤ 5% | More forgiving | |
| Inside 80% interval only | Baseline-only calls could never be stamped | |

| Option | Description | Selected |
|--------|-------------|----------|
| None, labelled | low/high null, interval grade N/A | ✓ |
| Seed-error band | In-sample band from ~5 quarters | |

| Option | Description | Selected |
|--------|-------------|----------|
| Plausible-reveal cutoff | Refuse at/after earliest plausible reveal; VOID after an earlier actual reveal | ✓ |
| Actual reveal only | Accept up to disclosure, VOID afterwards | |

| Option | Description | Selected |
|--------|-------------|----------|
| Official calls only | Headline uses official calls; NO OFFICIAL CALL counts as a miss | ✓ |
| Official + all-locks average | Two numbers per company | |

**Notes:** the user froze the following. Error = (pred − actual)/actual, stored signed. MISSED shows |error| plus over/under. Beat baseline = |model err| < |baseline err| on the official call, and a tie is NOT beaten. Always first-reported actual.

---

## Ledger home & witnesses

| Option | Description | Selected |
|--------|-------------|----------|
| Supabase + jsonl witness | Supabase canonical, ledger.jsonl committed + OTS | ✓ |
| Git jsonl canonical | File is the record, DB a mirror | |

| Option | Description | Selected |
|--------|-------------|----------|
| Actions workflow_dispatch | Server-side timestamp witness; DATABASE_URL secret | ✓ |
| Local dev machine | Fewer moving parts | |
| Local, Actions in Phase 2 | Local first lock, dispatch later | |

| Option | Description | Selected |
|--------|-------------|----------|
| One PREREGISTRATION.md | One doc, rules record at seq 0 | ✓ |
| Separate rule files | One rules record per file | |

| Option | Description | Selected |
|--------|-------------|----------|
| Rehearse, then lock ~28 Nov | Scratch dress rehearsal, ~3 days slack | ✓ |
| Lock as soon as ready | No rehearsal | |
| Lock exactly 1 Dec | No slack | |

**Notes:** if Supabase is unreachable, fail loudly and never fall back to SQLite. A heartbeat should check Supabase reachability a day before each final lock (Phase 2). OTS stamps the chain head hash; proofs live at `ledger/proofs/<seq>.ots` alongside ledger.jsonl; pending proofs are upgraded in each daily cron.

---

## Seed CSV sourcing

| Option | Description | Selected |
|--------|-------------|----------|
| I draft, you verify | Claude drafts from IR/filings, user ticks `verified` | ✓ |
| You fill it by hand | Template + instructions only | |
| I draft, no extra column | Spot-check only | |

| Option | Description | Selected |
|--------|-------------|----------|
| 8 now, 16 by Phase 3 | Q3 FY25..Q2 FY27 for the lock | ✓ |
| Full 16 now | Doubles critical-path verification | |

| Option | Description | Selected |
|--------|-------------|----------|
| Minute if shown, else EOD | exchange_timestamp or rule:date_eod_ist | ✓ |
| Date-only, EOD rule | Uniform, less precise | |
| Minute required | Blocks rows without exact time | |

| Option | Description | Selected |
|--------|-------------|----------|
| Reject whole file | Abort, list all errors, insert nothing | ✓ |
| Load good, report bad | Partial loads become permanent | |

---

## Claude's Discretion

- Config format/name, import package name, `ledger/ledger.jsonl` path, rules-record schema, decimal rounding for the 3% test, leaky-reader test design, CLI output, rehearsal isolation mechanism, `breaks_in_window` field name.

## Deferred Ideas

- Supabase reachability heartbeat before final locks → Phase 2 (OPS-02)
- Daily `ots upgrade` cron → Phase 2
- Seed history back to ~Q3 FY23 → Phase 2, for the Phase 3 backtest
- GST 2.0 treatment → Phase 3 (FEAT-03)
