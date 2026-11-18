# Roadmap: CALLED IT. — Earnings Nowcaster

## Overview

The plan works backwards from one fixed date. A baseline-only Q3 FY27 call for DMART, ETERNAL and TITAN must be locked in an append-only, hash-chained ledger, witnessed by git and OpenTimestamps, by about 1 Dec 2026. Each missed week is one fewer convergence point, and none can be backfilled. Phase 1 is therefore the smallest vertical slice that produces that lock, and it contains every [CRITICAL] requirement and nothing else. Phase 2 then makes the record run unattended: daily forward collection (a lost day can never be recovered), weekly locks, a verifier, and a redundant final pre-reveal lock with a dry run. Phase 3 adds real GST and Trends signals and an honest walk-forward backtest. Phase 4 freezes the ridge model into the weekly locks by mid-December under its own `model_version`. Baseline-only official calls are the accepted fallback. Phase 5 puts the broadsheet live on Vercel before about 20 Dec, and it updates itself from then on. Phase 6 finishes each call's story (convergence, what the model saw, what moved it, results-day stamp) and hands over a one-command pipeline and an honest README.

## Live Calendar (Q3 FY27)

These are external dates that set the phase order. Earliest plausible reveals use the config offsets from research (quarter end + N days: DMART +1, TITAN +2, ETERNAL +7) and are treated as 00:00 IST. Phase 1 confirms the offsets in `PIT-04` config.

| When | Event | Owning phase |
|------|-------|--------------|
| on or before 1 Dec 2026 | First baseline-only lock (ledger + git witness + OTS proof) | 1 |
| by ~3 Dec 2026 | First scheduled daily forward-collection run | 2 |
| by ~8 Dec 2026 | First unattended weekly lock | 2 |
| well before mid-Dec 2026 | Final-lock dry run (OPS-02) | 2 |
| by ~15 Dec 2026 | Ridge frozen and locked weekly under its own `model_version` | 4 |
| before ~20 Dec 2026 | Broadsheet live on Vercel | 5 |
| by 29 Dec 2026 18:30 UTC (30 Dec 00:00 IST) | Latest DMART official-call lock (>= 48h before 1 Jan 2027 IST) | 2 (automation) |
| by 30 Dec 2026 18:30 UTC (31 Dec 00:00 IST) | Latest TITAN official-call lock (>= 48h before 2 Jan 2027 IST) | 2 (automation) |
| by 4 Jan 2027 18:30 UTC (5 Jan 00:00 IST) | Latest ETERNAL official-call lock (>= 48h before 7 Jan 2027 IST) | 2 (automation) |
| ~1-5 Jan 2027 | DMART business update (its reveal) | - |
| ~10 Jan 2027 | DMART results filing, first real grade and first live stamp | 4 (grading), 6 (stamp) |

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: First Baseline-Only Lock** - Critical path. Scaffold, point-in-time store, leakage guard, seed revenue, baseline and ledger, ending in a hash-locked, git- and OTS-witnessed Q3 FY27 call by 1 Dec 2026
- [ ] **Phase 2: The Record Runs Itself** - Daily forward collectors, weekly locks, a ledger verifier, a redundant final lock and CI, all running unattended on GitHub Actions
- [ ] **Phase 3: Real Signals & Honest Backtest** - GST and Trends history with honest availability, a 5-8 feature builder, and a walk-forward baseline backtest kept apart from the live record
- [ ] **Phase 4: Main Model Joins the Ledger** - Frozen, versioned ridge with 80% intervals, locked weekly by mid-December, graded by the published rules, and reported against the baseline whichever wins
- [ ] **Phase 5: The Broadsheet Goes Live** - Read-only API, static export and the salmon-pink broadsheet on Vercel before ~20 Dec, refreshed automatically by cron
- [ ] **Phase 6: Results Day, Explanations & Handover** - Convergence chart, what-the-model-saw and what-moved-it panels, results-day stamps, a one-command pipeline and an honest README

## Phase Details

> Command names in the success criteria are indicative. Plan-phase sets the exact CLI, but every criterion must stay a runnable command or URL with observable output, so the user can check it at the end-of-phase review.

### Phase 1: First Baseline-Only Lock
**Goal**: On or before 1 Dec 2026, a baseline-only Q3 FY27 revenue call for DMART, ETERNAL and TITAN is locked in an append-only, hash-chained ledger and witnessed by a GitHub commit and an OpenTimestamps proof. The call uses only data that was public at the lock instant, and the phase includes everything that cannot be changed once a lock exists.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: FOUND-01, FOUND-03, FOUND-04, FOUND-05, PIT-01, PIT-02, PIT-03, PIT-04, PIT-05, LEAK-01, LEAK-02, LEAK-03, LEAK-04, DATA-01, FEAT-02, BASE-01, LEDG-01, LEDG-02, LEDG-03, LEDG-04, LEDG-05, LEDG-07, LEDG-09, LEDG-10
**Success Criteria** (what must be TRUE):
  1. **Setup and config.** On a fresh clone, one setup command (e.g. `uv sync`) installs the Python 3.12 uv workspace with `/data`, `/nowcaster`, `/web`, `/tests` and `/.github/workflows`. `uv run alembic upgrade head` succeeds with `DATABASE_URL` pointing at SQLite and at Supabase Postgres. `uv run nowcast universe` lists DMART, ETERNAL and TITAN from the config file with their reveal offsets, GST states, Trends terms, app IDs and structural breaks (Eternal/Blinkit, GST 2.0 from 22 Sep 2025). Disabling a company in that file drops it from the next lock without any code change.
  2. **Leakage suite passes.** `uv run pytest tests/leakage` passes. It covers:
     - fiscal-label tests (Q3 FY27 = 1 Oct-31 Dec 2026)
     - the property-based test that changing or adding rows with `available_at >= cutoff` leaves the features bit-identical
     - IST/UTC boundary tests (an IST filing just after midnight) and strict `<` at the cutoff instant
     - the walk-forward split test, which checks that every training row was revealed before the test quarter's cutoff

     All model-facing reads go through `PointInTimeReader(as_of)`.
  3. **Leakage suite catches leaks.** Running the same leakage suite against the deliberately leaky reader fails with a non-zero exit, which proves the suite can catch a leak.
  4. **Seed data and reveal calendar.** `uv run nowcast seed load` validates `data/seed/quarterly_revenue.csv` and rejects bad rows with a clear message. The CSV ships with exact fill-in instructions and filing URLs, and contains at least the quarters the Q3 FY27 baseline needs. Every row is stored insert-only with `period_date`, `available_at`, `ingested_at`, source and availability basis, so loading a restated figure adds a new row. `uv run nowcast calendar --quarter Q3FY27` prints each company's `business_update_at`, `results_at`, `reveal_at`, status and earliest plausible reveal (DMART 1 Jan 2027 IST).
  5. **The ledger and the first lock.**
     - **Integrity tests.** `uv run pytest tests/ledger` passes on both SQLite and Postgres. The `calledit-ledger-v1` golden vectors match, a forked chain is rejected, and UPDATE, DELETE, REPLACE and TRUNCATE on `predictions` each fail at the DB trigger. `npm test` in `web/` passes the same golden vectors in JS.
     - **Rules frozen first.** The grading rules and the frozen Eternal break treatment are committed, and their SHA-256 is recorded in the ledger before any prediction. The GST 2.0 treatment is deliberately left open here; it is decided in Phase 3 (FEAT-03).
     - **The lock.** On or before 1 Dec 2026, `uv run nowcast predict --quarter Q3FY27` locks one baseline-only prediction per company: same quarter last year x (1 + trailing YoY), with the Eternal treatment applied and a `feature_snapshot` recorded. It appends the lock to `ledger.jsonl`, pushes that commit to GitHub, and saves an OpenTimestamps proof. Within a day the proof upgrades to a Bitcoin attestation that `ots verify` accepts.
     - **Late and backfilled locks refused.** `uv run nowcast predict --quarter Q2FY27` (already revealed) is rejected or recorded VOID, and no command can backfill a lock at a past time.
**Plans**: 1/13 plans executed

Plans:
**Wave 1**
- [x] 01-01-PLAN.md — Workspace manifests, .gitattributes, branch main, then the uv install + package-legitimacy gate

**Wave 2** *(blocked on Wave 1 completion)*
- [ ] 01-02-PLAN.md — Walking skeleton: hash-chained rules record on SQLite exported to ledger.jsonl; Python/JS golden vectors; ledger integrity

**Wave 3** *(blocked on Wave 2 completion)*
- [ ] 01-03-PLAN.md — Fiscal calendar, IST/UTC bounds, config/universe.toml; `nowcast universe` and `nowcast calendar`

**Wave 4** *(blocked on Wave 3 completion)*
- [ ] 01-04-PLAN.md — Insert-only point-in-time store, PointInTimeReader, whole-file seed loader, reveal calendar from events

**Wave 5** *(blocked on Wave 4 completion)*
- [ ] 01-05-PLAN.md — Baseline-v1 (Decimal TTM, break-aware Eternal method, breaks_in_window, refusals); `nowcast baseline`
- [ ] 01-08-PLAN.md — Postgres parity: .env fix gate, Supabase scratch-schema trigger tests, db check, ci-postgres.yml

**Wave 6** *(blocked on Wave 5 completion)*
- [ ] 01-06-PLAN.md — Leakage suite: --reader switch, leaky readers, invariance property, meta-test, splitter, clock/import guards
- [ ] 01-07-PLAN.md — `nowcast predict`: prediction/gap records, lock guard, exit codes, rules freshness
- [ ] 01-09-PLAN.md — Seed history drafted from company IR documents (verified = N) + Eternal break-range citation

**Wave 7** *(blocked on Wave 6 completion)*
- [ ] 01-10-PLAN.md — PREREGISTRATION.md, then the freeze checkpoint (user verifies seed, confirms Eternal range/ISINs, approves rules)

**Wave 8** *(blocked on Wave 7 completion)*
- [ ] 01-11-PLAN.md — Secret + publish gate, first push, ruleset, green CI, lock.yml, full dress rehearsal, discard

**Wave 9** *(blocked on Wave 8 completion)*
- [ ] 01-12-PLAN.md — Go-live gate and live seq 0 rules record, committed to main and OTS-stamped

**Wave 10** *(blocked on Wave 9 completion)*
- [ ] 01-13-PLAN.md — Go-live gate and first live Q3 FY27 baseline-only lock; OTS upgrade and D-26 verification; phase evidence sweep

### Phase 2: The Record Runs Itself
**Goal**: Forward-only signals build up every day from the first lock onward (a lost day can never be recovered). Weekly locks, ledger verification and the redundant final pre-reveal lock run unattended on GitHub Actions, so the Q3 FY27 official calls are made even if the developer is away over the New Year.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: DATA-04, DATA-05, DATA-06, DATA-07, DATA-08, LEDG-06, LEDG-11, OPS-02, OPS-03
**Success Criteria** (what must be TRUE):
  1. **Forward collectors.** `uv run nowcast collect --forward` stores today's Apple App Store India chart rank and rating count (official RSS), the Play app-details snapshot (rating count, score) and the careers-site open-role counts for each company, with every row flagged `forward-collected`.
     - `uv run nowcast runs` lists each run's source, status, row count and error.
     - A source that robots.txt or its terms disallow shows as `unavailable`.
     - A failing source shows `failed` with its error, falling back to its seed CSV where one exists.
     - No synthetic row is ever written.
  2. **Daily cron.** The daily collection workflow has run on its GitHub Actions schedule (first scheduled run by ~3 Dec 2026) and on every day since, visible as runs in the Actions tab with matching `collector_runs` entries.
  3. **Weekly locks and the verifier.** The weekly lock workflow fires on schedule (first unattended lock by ~8 Dec 2026), locks every enabled company, commits `ledger.jsonl` and anchors it with OpenTimestamps. It then runs the standalone verifier (e.g. `python scripts/verify_ledger.py ledger.jsonl`), which prints PASS for every hash and the chain, and FAIL if any byte of any record is altered. `uv run nowcast official --quarter Q3FY27` shows each company's official call, derived as the last valid lock before `reveal_at` rather than stored as a flag.
  4. **Redundant final lock.** The final pre-reveal lock is scheduled on two independent triggers at least 48h before each earliest plausible reveal (DMART by 29 Dec 2026 18:30 UTC, TITAN by 30 Dec 18:30 UTC, ETERNAL by 4 Jan 2027 18:30 UTC). A dry run in this phase, well before mid-December, fires both triggers against a scratch ledger without touching the live one. A deliberately failed run raises the heartbeat alert.
  5. **CI.** Every push runs the full test suite in CI, including the leakage and trigger tests, against both SQLite and a Postgres service, and both jobs are green.
**Plans**: TBD

### Phase 3: Real Signals & Honest Backtest
**Goal**: GST and Google Trends history is collected with honest availability timestamps and turned into a small, horizon-matched, scale-free feature set. A walk-forward backtest measures the baseline's pseudo-real-time accuracy and keeps the results apart from the live record. Target ~10 Dec 2026, so the model can be frozen by mid-December.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: DATA-02, DATA-03, DATA-09, FEAT-01, FEAT-03, LEAK-05, BACK-01, BACK-02
**Success Criteria** (what must be TRUE):
  1. **GST.** `uv run nowcast collect gst` downloads the GSTN statistics `.xlsx` files and records a SHA-256 snapshot of each. It stores national and per-company key-state collections (CGST+SGST+IGST, excluding cess) with `available_at` set to the publication time. Re-running on an unchanged file adds no rows, and a changed file is stored as a new vintage.
  2. **Trends and sources.** `uv run nowcast collect trends` loads the manual Trends CSVs from `data/seed/` (download instructions included, brand terms such as "DMart", "Tanishq" and "Blinkit"), and stores each live trendspyg pull as an immutable vintage. `data/SOURCES.md` documents every source with its terms status, availability basis and fallback: revenue seed, GST, Trends, Apple RSS, Play details and careers sites.
  3. **Features.** `uv run nowcast features --ticker DMART --as-of 2026-12-01` prints 5-8 scale-free features (Trends YoY change, GST national YoY, GST key-state YoY, seasonality, break flags) with the IDs of the source rows behind each value. A test proves training rows are built at the same offset before reveal as live locks.
  4. **Backtest.** `uv run nowcast backtest` prints an expanding-window walk-forward table of MAPE and directional accuracy for the baseline, per company and overall. Quarters whose comparison straddles the Eternal break are flagged and excluded. Results are stored labelled BACKTEST, and a test proves no BACKTEST row can ever enter the `predictions` ledger.
  5. **GST 2.0 treatment decided and frozen.** After inspecting the downloaded GSTN files (component definitions, cess exclusion, restated Sep/Oct 2025 bases), the GST 2.0 treatment is written down with its reasoning, committed, and its SHA-256 appended to the ledger as a rules record. This happens before the first model lock (~15 Dec 2026), and the GST features in criterion 3 use exactly that frozen treatment.
**Plans**: TBD

### Phase 4: Main Model Joins the Ledger
**Goal**: By mid-December 2026, a frozen, versioned ridge model with honest 80% intervals joins the weekly locks under its own `model_version`. Its live calls are graded by the rules published in Phase 1, and its record against the baseline is published whichever wins. If the model is not ready in time, baseline-only official calls are the accepted fallback.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: MODL-01, MODL-02, MODL-03, MODL-04, MODL-05, MODL-06, LEDG-08
**Success Criteria** (what must be TRUE):
  1. **Model comparison.** `uv run nowcast backtest --models baseline,ridge,gbm` prints MAPE and directional accuracy side by side for all three, per company and overall. It also prints train vs test error for ridge (pooled, per-company intercepts) and HistGradientBoosting.
  2. **Intervals.** Every model prediction carries a point estimate and an 80% interval from walk-forward residuals, and the backtest reports the interval's empirical coverage and n (e.g. "80% interval: 74% covered, n=38").
  3. **Freeze and lock.** `uv run nowcast model freeze ridge` records a `model_version` that includes a hash of the feature definitions. Editing any feature definition changes that version, and a lock with an unfrozen or changed model, or with no frozen GST 2.0 treatment in the ledger, is refused. The scheduled weekly lock on or before ~15 Dec 2026 then writes ridge predictions under that version alongside the baseline.
  4. **Model-vs-baseline report.** `reports/model_vs_baseline.md` is generated and committed, and it states plainly which wins per company and overall, including when the baseline wins.
  5. **Grading.** `uv run nowcast grade` fills the `grades` table (error %, inside-interval, beat-baseline) for every prediction that has actuals, following the rules hashed in Phase 1. Today it reports 0 graded and N awaiting actuals, and fixture tests cover every rule.
**Plans**: TBD

### Phase 5: The Broadsheet Goes Live
**Goal**: Before ~20 Dec 2026, anyone can open the "CALLED IT." broadsheet on Vercel, see each live Q3 FY27 call with its interval and a countdown to its reveal, check any call's hash in their own browser, and compare model against baseline with LIVE and BACKTEST kept strictly apart. The site refreshes itself after every scheduled collection, lock and grading run.
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: API-01, API-02, WEB-01, WEB-02, WEB-04, WEB-05, WEB-06, WEB-07, WEB-09, WEB-10, OPS-01, OPS-04
**Success Criteria** (what must be TRUE):
  1. **API and export.** `uv run nowcast api` serves read-only endpoints for editions, predictions, grades, scoreboard, backtest and data freshness, and any write method returns 405. `uv run nowcast export` writes a static JSON export identical to those responses.
  2. **Front page.** The Vercel URL shows the salmon-pink broadsheet front page "VOL. 1 · Q3 FY27 EDITION", built with the Hallmark plugin. Each company's live call appears as a headline with its 80% interval (or a clear baseline-only label) and a countdown to its reveal, and the microcopy is computed from real data. The "Barely advice at all." research-only disclaimer is in the footer of every page.
  3. **The Record.** Every locked prediction shows its SHA-256 printed like a serial number next to its actual (or "awaiting"). Clicking "verify" recomputes the hash in the browser and shows a match, and a tampered export shows a mismatch.
  4. **Scoreboard, methodology and freshness.** The MODEL vs BASELINE scoreboard (which says so proudly if the baseline is winning), the methodology page (lookahead bias, reveal calendar and ledger in plain English) and the data-freshness and collector-failure status are all live. LIVE and BACKTEST numbers are never mixed or blended anywhere, and forward-collected signals are flagged.
  5. **Self-updating.** Scheduled GitHub Actions now run daily collection for every source, weekly locks and daily grading. Each run commits a regenerated export, so a new scheduled lock shows on the live site with no manual step.
**Plans**: TBD
**UI hint**: yes

### Phase 6: Results Day, Explanations & Handover
**Goal**: Each call tells its full story: how the weekly nowcasts converged, what the model saw, what moved it, and, on results day, whether it was CALLED IT or MISSED. Anyone can rerun the whole pipeline with one command and read its honest limitations. The explanations go live before the first reveal (~1 Jan 2027), and the stamps work before DMART's results filing (~10 Jan 2027).
**Mode:** mvp
**Depends on**: Phase 5
**Requirements**: WEB-03, WEB-08, WEB-11, WEB-12, FOUND-02, OPS-05
**Success Criteria** (what must be TRUE):
  1. **Convergence chart.** Each company's chart shows its weekly locks moving toward the official call, with gaps shown for any missed week. It is live before the first reveal (~1 Jan 2027).
  2. **Explanation panels.** Every locked call has a "What the model saw" panel showing its exact `feature_snapshot`, which matches the hashed payload. It also has a "What moved it" breakdown of each signal's ridge contribution (coef x value). Baseline-only locks say plainly that they have no model contribution.
  3. **Results-day stamp.** A graded call shows the rubber-stamp animation: red "CALLED IT" or grey "MISSED (by X%)". This is verified now with fixture grades in component tests, and on the live site once DMART's first real grade lands (~10 Jan 2027).
  4. **One-command pipeline.** `uv run nowcast run-all` runs collect, features, backtest, lock, grade and export end to end against a local sandbox database, and never touches the live ledger.
  5. **README.** The README explains what CALLED IT. is, how to set it up and run it, and the methodology. It also states the honest limitations: sample size, Trends reconstruction, structural breaks and survivorship in the hand-picked universe.
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. First Baseline-Only Lock | 1/13 | In Progress | - |
| 2. The Record Runs Itself | 0/TBD | Not started | - |
| 3. Real Signals & Honest Backtest | 0/TBD | Not started | - |
| 4. Main Model Joins the Ledger | 0/TBD | Not started | - |
| 5. The Broadsheet Goes Live | 0/TBD | Not started | - |
| 6. Results Day, Explanations & Handover | 0/TBD | Not started | - |
