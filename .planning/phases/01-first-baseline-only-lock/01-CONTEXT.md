# Phase 1: First Baseline-Only Lock - Context

**Gathered:** 2026-11-18
**Status:** Ready for planning

<domain>
## Phase Boundary

On or before 1 Dec 2026 (target ~28 Nov), a baseline-only Q3 FY27 consolidated-revenue call for DMART, ETERNAL and TITAN is locked in an append-only, hash-chained ledger on Supabase Postgres, exported to `ledger.jsonl`, committed to the public GitHub repo and anchored with OpenTimestamps. The phase delivers everything that cannot change once a lock exists: uv workspace scaffold, company config, fiscal/IST calendar, point-in-time store and `PointInTimeReader`, leakage suite (including the deliberately leaky reader), seed revenue + reveal calendar, baseline-v1, the `calledit-ledger-v1` ledger with triggers on SQLite and Postgres, the preregistered rules, and the first lock. Requirements: FOUND-01, FOUND-03, FOUND-04, FOUND-05, PIT-01..05, LEAK-01..04, DATA-01, FEAT-02, BASE-01, LEDG-01..05, LEDG-07, LEDG-09, LEDG-10.

Not in this phase: GST/Trends signals, the GST 2.0 treatment (FEAT-03, Phase 3), forward collectors and cron (Phase 2), model, API, web UI (beyond the JS golden-vector test in `web/`).

</domain>

<decisions>
## Implementation Decisions

### Setup facts (from the user)
- **D-01:** GitHub remote is `https://github.com/KASHITOp/called-it.git` (public). Add it as `origin`. `gh` CLI is already authenticated.
- **D-02:** `.env` already exists with `DATABASE_URL` (Supabase **session pooler**). Never overwrite it, never commit it, never print its value. Add a `.env.example` with a placeholder only.
- **D-03:** Run `git check-ignore .env` before the first push and confirm it is ignored. Note: at session start `git status` showed `.gitignore` as **untracked** (`?? .gitignore`), so the plan must commit `.gitignore` before anything else is pushed.

### Baseline-v1 (frozen into PREREGISTRATION.md)
- **D-04:** Baseline = revenue(same quarter last year) × (1 + g), where g is **TTM YoY**: the sum of the last 4 revealed quarters ÷ the sum of the 4 quarters before them, − 1. "Revealed" means `reveal_at < as_of`. For the Q3 FY27 lock: same-quarter-last-year = Q3 FY26, TTM = (Q3 FY26..Q2 FY27) ÷ (Q3 FY25..Q2 FY26). — **Reversibility:** one-way — hashed into the ledger before the first lock; changing it means a new, visible rules record and a new baseline version.
- **D-05:** Baseline inputs use the **latest vintage known at as_of** (`available_at < as_of`), so restatements published before the lock are used. Grading still uses first-reported actuals (D-13). — **Reversibility:** one-way — part of the frozen baseline definition.
- **D-06:** **Eternal break treatment (FEAT-02).** The break is declared in config as a quarter **range**, pinned from Eternal's filings or shareholder letters with the source cited in config. If any quarter in the TTM window falls inside or straddles the break range, the baseline instead uses the single-quarter YoY of the latest quarter pair (t, t−4) where both quarters are post-break. If no such pair exists, it uses the least-straddling pair. Proposed definition: the most recent revealed pair, i.e. the one with the latest base quarter. Show it to the user in PREREGISTRATION.md before the freeze. Eternal's call always carries a hashed label `"low confidence: post-break comparables limited"`. — **Reversibility:** one-way — FEAT-02 requires its SHA-256 in the ledger before the first lock.
- **D-07:** **GST 2.0 and the baseline:** flag it, don't adjust it. The baseline maths ignores GST 2.0, but each lock's hashed payload records when its TTM window straddles the GST 2.0 marker (22 Sep 2025), e.g. a `breaks_in_window` field. The GST 2.0 *feature* treatment stays open until FEAT-03 (Phase 3), and PREREGISTRATION.md must say "GST 2.0 treatment: deferred to FEAT-03" explicitly.
- **D-08:** **Missing-quarter rule.** If any seed quarter needed for a company's lock is missing (or unverified, see D-22), that company's lock is **refused and recorded as a visible gap**. Nothing is ever imputed, estimated or interpolated. — **Reversibility:** one-way — a preregistered rule.

### Grading rules (LEDG-07, frozen into PREREGISTRATION.md)
- **D-09:** **CALLED IT** = |error| ≤ 3% against the first-reported actual. A model call must *also* have the actual inside its 80% interval. A baseline-only call needs only |error| ≤ 3%. Anything else is **MISSED**. — **Reversibility:** one-way — hashed before the first lock.
- **D-10:** error = (predicted − actual) / actual, stored **signed**. The stamp compares |error|. "MISSED (by X%)" shows |error| plus a direction: **over** or **under**.
- **D-11:** **Beat baseline** = |model error| < |baseline error| on the same company's official call for the same quarter. A **tie is NOT beaten**. For baseline-only official calls, beat-baseline is N/A.
- **D-12:** **Interval for baseline-only locks:** none. `low_cr` and `high_cr` are null, and the payload labels the interval as "none (baseline-only, no out-of-sample residuals yet)". The inside-interval grade is N/A.
- **D-13:** Grading always uses the **first-reported** consolidated revenue from operations in the results filing, as reported (never Eternal's "adjusted revenue"). Later restatements are shown but never re-grade.
- **D-14:** **Lock deadline.** A lock at or after `earliest_plausible_reveal` (config: quarter end + N days at 00:00 IST, with DMART +1, TITAN +2, ETERNAL +7) is **refused**. If the actual `reveal_at` turns out to be even earlier, any lock at or after it is marked **VOID at grading**. That is derived state, so the predictions row is never mutated, and the lock is shown greyed out, never hidden. The official call is the last non-VOID lock before `reveal_at`, derived and never a flag. `predict --quarter Q2FY27` (already revealed) is refused. No command can lock at a past time.
- **D-15:** **Headline scoring uses official calls only.** The stamp and the headline MAPE use each company's official call. Every weekly lock is still graded and kept in the convergence history. A company with no valid lock before its reveal shows **"NO OFFICIAL CALL"** and counts as a published miss, never a silent omission.

### Ledger home & witnesses
- **D-16:** **System of record:** Supabase Postgres `predictions` in a private `calledit` schema, not exposed through PostgREST, with RLS on and no anon policies, guarded by the append-only triggers. Every lock exports `ledger.jsonl`, which is committed to git and OTS-stamped as the public witness. SQLite is for local dev and tests only. — **Reversibility:** costly — moving the system of record later means migrating a hash-chained ledger and re-explaining provenance.
- **D-17:** **Fail loudly.** If Supabase is unreachable at lock time (for example a free-tier pause), the lock fails with a non-zero exit and a visible alert (a failed Actions run). It **never** silently falls back to SQLite.
- **D-18:** **Lock runner:** a GitHub Actions `workflow_dispatch` workflow runs `nowcast predict`, exports and commits `ledger.jsonl`, and stamps OTS. Its run log is an extra server-side timestamp witness. The user adds `DATABASE_URL` as a repo secret themselves, and plans must give the exact steps without ever echoing the value.
- **D-19:** **Preregistration:** a single committed `PREREGISTRATION.md` covering the universe, baseline-v1 (D-04..D-08), the Eternal treatment, the grading rules (D-09..D-15), the official-call and deadline rules, the missing-quarter rule, and "GST 2.0: deferred to FEAT-03". Its SHA-256 goes into a **rules** record at **seq 0** of the ledger hash chain, OTS-stamped before any prediction. Any later change is a new, visible rules record and never an edit.
- **D-20:** **OTS details.** Stamp the **chain head hash** (the latest record's hash), not the whole file. Because every record links to the one before, the head covers the full history. Proofs live at `ledger/proofs/<seq>.ots`, committed alongside `ledger.jsonl`. Pending proofs are upgraded with `ots upgrade` until Bitcoin confirms them. In Phase 2 that runs in each daily cron. In Phase 1 the upgrade is run manually or by dispatch so the success criterion ("within a day, `ots verify` accepts") is met.
- **D-21:** **Timing.** First run a full dress rehearsal of the dispatch workflow against a **scratch** Supabase schema and a scratch ledger file, then discard it. The rehearsal must never write to the live `calledit` schema or the published `ledger.jsonl`. The live lock targets **~28 Nov 2026**, about 3 days of slack before the 1 Dec deadline for a failed run or a slow OTS confirmation.

### Seed CSV sourcing (DATA-01)
- **D-22:** **I draft, the user verifies.** Claude drafts each row from company IR documents and filing PDFs, using single manual-equivalent fetches only. There is no NSE/BSE API automation, per the data-ethics constraint. Where only an exchange PDF exists, the user opens it. Every row cites its `source_url`, plus a page reference where helpful. The CSV has a `verified` column that the user ticks after checking each row against the PDF. Loading into the live (Supabase) database requires every row to be verified. A validate/dry-run mode reports problems without inserting. An unverified required quarter is treated as missing (D-08).
- **D-23:** **Depth.** By the ~28 Nov lock there are 8 verified quarters per company, Q3 FY25..Q2 FY27, which is exactly what TTM needs, so about 24 rows plus the Eternal break-range citation. The full 12-16 quarter history is filled in during Phase 2, in time for the Phase 3 backtest.
- **D-24:** **Timestamp precision.** Use the exchange dissemination time to the minute when the filing or announcement shows it (`availability_basis = 'exchange_timestamp'`). Otherwise use the filing date at 23:59:59 IST (`availability_basis = 'rule:date_eod_ist'`), which errs late and so can never leak. Store in UTC. DMART and Titan rows need `business_update_at`. Eternal has no business update, so its reveal is the results filing.
- **D-25:** **Bad rows reject the whole file.** If any row is invalid (missing URL, impossible date, non-decimal revenue, period_end not matching fiscal_quarter, unverified for a live load), `nowcast seed load` aborts, lists every error (row number, column, reason) and inserts nothing. Because the store is insert-only, a partial load would be permanent.

### Claude's Discretion
- Config file format and name (research suggests `universe.toml` via `tomllib`) and the import package name (`calledit_data`, not `data`).
- Ledger file path: `ledger/ledger.jsonl`, next to `ledger/proofs/`. Phase 5 export can copy or serve it for the web.
- Rules-record schema inside the chain (e.g. `record_kind: rules | prediction`), as long as it is seq 0 and hash-chained.
- Exact decimal rounding for the 3% comparison (compare unrounded `Decimal`s, display at 2 dp), written into PREREGISTRATION.md.
- Leaky-reader test design, CLI output formatting, and how the rehearsal is isolated (scratch schema name, no-commit branch or flag).
- The exact name of the `breaks_in_window` payload field.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project scope and requirements
- `.planning/ROADMAP.md` §"Phase 1: First Baseline-Only Lock" — goal, 5 success criteria, live calendar and reveal offsets
- `.planning/REQUIREMENTS.md` — FOUND/PIT/LEAK/DATA-01/FEAT-02/BASE-01/LEDG requirement text; FEAT-03 (GST 2.0 deferral)
- `.planning/PROJECT.md` — core value, constraints, revenue basis, Eternal break context
- `.planning/STATE.md` — Phase 1 blockers and research flags (OTS client and upgrade flow, Postgres trigger-bypass on Supabase)
- `.claude/CLAUDE.md` — tech stack versions, DB-layer gotchas (SQLite `recursive_triggers`, Alembic batch drops triggers, Supabase poolers and PostgREST exposure), data-source verdicts

### Research
- `.planning/research/ARCHITECTURE.md` — `calledit-ledger-v1` canonical spec and payload fields, the `UNIQUE(prev_hash)` fork guard, the trigger set (incl. the REPLACE guard), the observation schema and `availability_basis`, official-call and grading as derived state, the `model_version` format (`baseline-sqly@1.0.0`)
- `.planning/research/PITFALLS.md` — Pitfall 3 (reveal instant, IST/UTC), Pitfall 4 (Eternal break range, ZOMATO→ETERNAL rename on 2025-04-09, ISIN keys), Pitfall 10 (hash canonicalisation), Pitfall 11 (trigger bypasses: TRUNCATE, DISABLE TRIGGER, RLS), Pitfall 12 (preregistration, SEBI framing)
- `.planning/research/STACK.md` — pinned versions and alternatives
- `.planning/research/FEATURES.md` — table-stakes ledger features (VOID, gaps, annotation rows)
- `.planning/research/SUMMARY.md` — synthesis and the build-order rationale

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None. The repo is greenfield: only `.planning/`, `.claude/CLAUDE.md`, `.gitignore` (untracked) and `.env` exist.

### Established Patterns
- No code patterns exist yet. Conventions in `.claude/CLAUDE.md` apply: `src/` layout, SQLAlchemy Core rather than the ORM, `df.loc` under pandas 3 Copy-on-Write, UTC storage with a tz-asserting `TypeDecorator`, plain INSERT only, never REPLACE or `to_sql(if_exists="replace")`.

### Integration Points
- Supabase Postgres via `DATABASE_URL` in `.env` (session pooler, port 5432). The same URL becomes the Actions repo secret.
- The GitHub remote `origin` is the public witness for `ledger.jsonl` and `ledger/proofs/`.
- `web/` exists in Phase 1 only for the JS golden-vector test (`npm test`).

</code_context>

<specifics>
## Specific Ideas

- The user explicitly wants "fail loudly, never fall back silently" wherever a guarantee is at stake: Supabase being unreachable, a missing seed quarter, a bad seed row.
- MISSED stamps show a direction ("MISSED (by 4.2%, over)").
- Eternal's call is always visibly labelled low confidence. Showing the limitation is preferred over hiding it.
- Fiscal-quarter worked example for tests: Q3 FY27 = 1 Oct–31 Dec 2026; DMART earliest plausible reveal = 1 Jan 2027 00:00 IST.

</specifics>

<deferred>
## Deferred Ideas

- **Supabase reachability heartbeat:** the weekly-lock heartbeat checks Supabase is reachable a day before each final lock. This is a user requirement for Phase 2 (OPS-02).
- **Daily `ots upgrade` in cron:** Phase 2 (daily collection workflow). In Phase 1 it is run manually or by dispatch.
- **Seed history back to ~Q3 FY23 (12-16 quarters):** filled during Phase 2, ready for the Phase 3 backtest (BACK-01).
- **GST 2.0 treatment:** Phase 3 (FEAT-03), frozen before the first model lock (~15 Dec).

</deferred>

---

*Phase: 01-first-baseline-only-lock*
*Context gathered: 2026-11-18*
