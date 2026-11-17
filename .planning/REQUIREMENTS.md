# Requirements: CALLED IT. — Earnings Nowcaster

**Defined:** 2026-11-17
**Core Value:** Provably honest predictions: every call is made with only the data that was public at the time (no lookahead), locked with a verifiable hash before the reveal, never edited, and graded in public against a naive baseline, even when the baseline wins.

## v1 Requirements

Requirements for the first live edition (Q3 FY27). Each maps to one roadmap phase.

**[CRITICAL]** = needed for the first baseline-only lock (target ~1 Dec 2026), or impossible to add after a lock has happened. Everything else can land after that lock.

### Foundation

- [ ] **FOUND-01**: [CRITICAL] Developer can set up the whole backend with one command (uv workspace, Python 3.12, monorepo dirs `/data`, `/nowcaster`, `/web`, `/tests`, `/.github/workflows`)
- [ ] **FOUND-02**: Developer can run the full pipeline (collect → features → backtest → lock → grade → export) with one command
- [ ] **FOUND-03**: [CRITICAL] Developer can add, remove or disable a company by editing one config file (ticker, ISIN, revenue basis, reveal offset, GST states, Trends terms, app IDs, structural breaks) with no code changes
- [ ] **FOUND-04**: [CRITICAL] Developer can switch storage between SQLite (local) and Postgres/Supabase with one config flag (`DATABASE_URL`), with migrations managed by Alembic
- [ ] **FOUND-05**: [CRITICAL] System converts between Indian fiscal labels and dates correctly (e.g. Q3 FY27 = Oct–Dec 2026), covered by unit tests

### Point-in-Time Store

- [ ] **PIT-01**: [CRITICAL] Every stored data point carries `period_date`, `available_at` (UTC timestamp), `ingested_at`, source and availability basis
- [ ] **PIT-02**: [CRITICAL] Revisions and restatements are stored as new rows, never by overwriting; the store is insert-only
- [ ] **PIT-03**: [CRITICAL] All model-facing reads go through a single `PointInTimeReader(as_of)` that returns only rows with `available_at < as_of` (and, in live mode, `ingested_at <= as_of`)
- [ ] **PIT-04**: [CRITICAL] Reveal calendar stores `business_update_at` and `results_at` per company-quarter, with `reveal_at` = the earliest of the two, plus expected/confirmed status and a config-driven earliest plausible reveal for live quarters
- [ ] **PIT-05**: [CRITICAL] Structural breaks (Eternal/Blinkit inventory shift, GST 2.0 from 22 Sep 2025) are declared in config and available to features, baseline and reporting

### Leakage Guard

- [ ] **LEAK-01**: [CRITICAL] A test changes or adds only rows with `available_at >= cutoff` and asserts features for that cutoff come out bit-identical (property-based)
- [ ] **LEAK-02**: [CRITICAL] A deliberately leaky reader is run through the leakage suite and the suite must fail, proving the tests can catch a leak
- [ ] **LEAK-03**: [CRITICAL] Tests cover IST/UTC boundaries (e.g. an IST filing just after midnight) and strict `<` at the cutoff instant
- [ ] **LEAK-04**: [CRITICAL] Backtests use only expanding-window walk-forward splits keyed on reveal timestamps; a test asserts every training row was revealed before the test quarter's cutoff
- [ ] **LEAK-05**: Training feature rows are built at the same offset before reveal as live locks (no full-quarter features in training when live sees a partial quarter)

### Data Collection

- [ ] **DATA-01**: [CRITICAL] Quarterly revenue history (consolidated revenue from operations, ₹ crore) loads from `data/seed/quarterly_revenue.csv` (ticker, fiscal_quarter, period_end, results_date, business_update_at, revenue_cr, source_url), validated on load, with exact instructions for filling it from exchange filings
- [ ] **DATA-02**: GST collector downloads the GSTN statistics `.xlsx` files, snapshots each download with a SHA-256, and stores national and per-company key-state collections (CGST+SGST+IGST, excluding cess) with `available_at` = publication time
- [ ] **DATA-03**: Google Trends history loads from manual CSV exports in `data/seed/` (with download instructions), and live weekly pulls via trendspyg are stored as immutable vintages
- [ ] **DATA-04**: Every collector run is logged (`collector_runs`: source, status, rows, error), and on failure falls back to the seed CSV and reports the failure plainly; no synthetic data is ever produced
- [ ] **DATA-05**: Forward collector logs Apple App Store India chart rank and rating count (official RSS) daily for each company's app, flagged "forward-collected"
- [ ] **DATA-06**: Forward collector logs a daily Play Store app-details snapshot (rating count, score) with a visible failure flag; no chart scraping
- [ ] **DATA-07**: Forward collector logs daily open-role counts from each company's own careers page where robots.txt and terms allow, otherwise marks the source as unavailable
- [ ] **DATA-08**: Forward collectors run daily via GitHub Actions cron from Phase 2 onward
- [ ] **DATA-09**: `data/SOURCES.md` documents every source, its terms status, availability basis and fallback

### Features, Baseline & Backtest

- [ ] **FEAT-01**: Feature builder produces 5–8 scale-free features per company-quarter from an explicit `as_of` (Trends YoY change, GST national YoY, GST key-state YoY, seasonality dummies, break flags), with lineage of the source rows used
- [ ] **FEAT-02**: [CRITICAL] The Eternal break treatment is chosen, written down and frozen before the first baseline lock; the GST 2.0 treatment likewise before the first model lock
- [ ] **BASE-01**: [CRITICAL] Baseline predicts revenue = same quarter last year × (1 + trailing YoY growth), using only data available before the cutoff, with the same break treatment as the model
- [ ] **BACK-01**: Walk-forward backtest prints a results table of MAPE and directional accuracy (direction of surprise vs baseline), per company and overall, for baseline and model
- [ ] **BACK-02**: Backtest results are stored and labelled BACKTEST (pseudo-real-time), never mixed into live ledger records

### Main Model

- [ ] **MODL-01**: Ridge regression (pooled, per-company intercepts) predicts YoY revenue growth from the features
- [ ] **MODL-02**: Gradient boosting (HistGradientBoosting, tiny-data settings) is run as a comparison
- [ ] **MODL-03**: Train vs test error is printed for every model to expose overfitting
- [ ] **MODL-04**: Every prediction has a point estimate plus an 80% interval from walk-forward residuals, with empirical coverage and n reported
- [ ] **MODL-05**: Models are versioned (`model_version` includes a hash of the feature definitions) and frozen before they lock live predictions
- [ ] **MODL-06**: A model-vs-baseline report is produced and published even when the baseline wins

### Prediction Ledger

- [ ] **LEDG-01**: [CRITICAL] `predictions` table stores id, ticker, fiscal_quarter, predicted_revenue_cr, low_cr, high_cr, baseline_cr, model_version, feature_snapshot (JSON), created_at, canonical payload, sha256 hash and prev_hash
- [ ] **LEDG-02**: [CRITICAL] Hash = SHA-256 of a canonical payload (spec `calledit-ledger-v1`: sorted keys, decimal strings, UTC timestamps), with golden test vectors that both Python and JS tests check
- [ ] **LEDG-03**: [CRITICAL] Each prediction includes the previous prediction's hash (hash chain), and a fork in the chain is rejected
- [ ] **LEDG-04**: [CRITICAL] Ledger is append-only, enforced in application code and by DB triggers that block UPDATE, DELETE, REPLACE and TRUNCATE on both SQLite and Postgres, with tests proving each trigger fires
- [ ] **LEDG-05**: [CRITICAL] `nowcast predict --quarter Q3FY27` locks a prediction per company; locks attempted at or after `reveal_at` are rejected (or recorded VOID), and missed weekly locks show as gaps, never backfilled
- [ ] **LEDG-06**: Weekly locks run on a schedule during the quarter; the official call is derived as the last valid lock before `reveal_at` (not a mutable flag)
- [ ] **LEDG-07**: [CRITICAL] Grading rules are published and hashed into the ledger before the first live lock
- [ ] **LEDG-08**: `nowcast grade` fills a `grades` table for every prediction that now has actuals: error %, inside-interval yes/no, beat-baseline yes/no
- [ ] **LEDG-09**: [CRITICAL] Each lock run commits `ledger.jsonl` to the GitHub repo as an outside timestamp witness
- [ ] **LEDG-10**: [CRITICAL] Each lock is anchored with OpenTimestamps, and the proofs are stored and upgraded once they are confirmed in Bitcoin
- [ ] **LEDG-11**: A standalone verifier script recomputes every hash and the chain from the public export and reports pass/fail

### API & Frontend

- [ ] **API-01**: Read-only FastAPI exposes editions, predictions, grades, scoreboard, backtest and data-freshness endpoints
- [ ] **API-02**: A static JSON export of the API responses is generated for the Vercel site
- [ ] **WEB-01**: Front page "VOL. 1 · Q3 FY27 EDITION" shows each company's live call as a big headline with its 80% interval and a countdown to its reveal
- [ ] **WEB-02**: "The Record" archive shows every past prediction vs actual, with its SHA-256 printed like a serial number and a "verify" button that recomputes it in the browser
- [ ] **WEB-03**: Graded calls show a rubber-stamp animation: red "CALLED IT" or grey "MISSED (by X%)"
- [ ] **WEB-04**: "MODEL vs BASELINE" boxing-match scoreboard, which says so proudly when the baseline is winning
- [ ] **WEB-05**: Methodology page explains lookahead bias, the reveal calendar and the ledger in plain English
- [ ] **WEB-06**: Footer disclaimer: research/educational only, not investment advice, no buy/sell calls ("Barely advice at all.")
- [ ] **WEB-07**: LIVE and BACKTEST results are visually and numerically separate everywhere, and forward-collected signals are flagged
- [ ] **WEB-08**: Convergence chart shows how the weekly nowcasts moved toward the official call
- [ ] **WEB-09**: Site shows data freshness and collector failures
- [ ] **WEB-10**: Salmon-pink broadsheet design (built with the Hallmark plugin) with dry humorous microcopy computed from real data
- [ ] **WEB-11**: "What the model saw" panel shows the exact feature_snapshot behind each locked call
- [ ] **WEB-12**: "What moved it" breakdown shows each signal's ridge contribution (coef × value) for each lock

### Operations

- [ ] **OPS-01**: GitHub Actions cron runs daily collection, weekly locks and daily grading, and commits the export
- [ ] **OPS-02**: The final pre-reveal lock runs redundantly at least 48h before each earliest plausible reveal, with a heartbeat alert on failure and a dry run by mid-December
- [ ] **OPS-03**: CI runs the full test suite (including leakage and trigger tests) on SQLite and Postgres
- [ ] **OPS-04**: The frontend is deployed on Vercel
- [ ] **OPS-05**: README covers what it is, how to run it, methodology and honest limitations (sample size, Trends reconstruction, breaks, survivorship)

## v2 Requirements

Deferred to a future release. Tracked but not in the current roadmap.

### Explainability

- **EXPL-01**: Error by horizon (weeks before reveal)
- **EXPL-02**: Interval score and a CI badge for the leakage suite

### Expansion

- **EXPN-01**: Forward-collected signals (app rank, jobs) enter the model once 4+ quarters of history exist, under a new model version
- **EXPN-02**: Gradient boosting runs as a locked challenger in the ledger
- **EXPN-03**: TRENT and FSN are added to the universe via ledger-recorded universe changes
- **EXPN-04**: Trends vintage diff view

## Out of Scope

| Feature | Reason |
|---------|--------|
| Buy/sell signals, beat/miss vs Street | Research/educational only; SEBI research-analyst boundary |
| Scraped analyst consensus | Terms risk and unverifiable provenance |
| Play Store chart-rank scraping | No ToS-clean public source; Apple RSS used instead |
| Naukri/LinkedIn/aggregator job scraping | Terms forbid it; company careers pages only |
| Blending backtest and live accuracy into one number | Hides the difference between pseudo-real-time and real calls |
| Re-scoring past calls with newer models | Defeats the point of a locked record |
| Editing, deleting or backfilling predictions | Append-only by design |
| Synthetic or filler data | Never presented as real; failures are reported instead |
| Profit/EPS/margin prediction | Revenue only; the signals map to demand |
| Random train/test splits | Leak the future |
| Model tuning sliders on the site | Invite cherry-picking |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FOUND-01 | Phase 1 | Pending |
| FOUND-02 | Phase 6 | Pending |
| FOUND-03 | Phase 1 | Pending |
| FOUND-04 | Phase 1 | Pending |
| FOUND-05 | Phase 1 | Pending |
| PIT-01 | Phase 1 | Pending |
| PIT-02 | Phase 1 | Pending |
| PIT-03 | Phase 1 | Pending |
| PIT-04 | Phase 1 | Pending |
| PIT-05 | Phase 1 | Pending |
| LEAK-01 | Phase 1 | Pending |
| LEAK-02 | Phase 1 | Pending |
| LEAK-03 | Phase 1 | Pending |
| LEAK-04 | Phase 1 | Pending |
| LEAK-05 | Phase 3 | Pending |
| DATA-01 | Phase 1 | Pending |
| DATA-02 | Phase 3 | Pending |
| DATA-03 | Phase 3 | Pending |
| DATA-04 | Phase 2 | Pending |
| DATA-05 | Phase 2 | Pending |
| DATA-06 | Phase 2 | Pending |
| DATA-07 | Phase 2 | Pending |
| DATA-08 | Phase 2 | Pending |
| DATA-09 | Phase 3 | Pending |
| FEAT-01 | Phase 3 | Pending |
| FEAT-02 | Phase 1 | Pending |
| BASE-01 | Phase 1 | Pending |
| BACK-01 | Phase 3 | Pending |
| BACK-02 | Phase 3 | Pending |
| MODL-01 | Phase 4 | Pending |
| MODL-02 | Phase 4 | Pending |
| MODL-03 | Phase 4 | Pending |
| MODL-04 | Phase 4 | Pending |
| MODL-05 | Phase 4 | Pending |
| MODL-06 | Phase 4 | Pending |
| LEDG-01 | Phase 1 | Pending |
| LEDG-02 | Phase 1 | Pending |
| LEDG-03 | Phase 1 | Pending |
| LEDG-04 | Phase 1 | Pending |
| LEDG-05 | Phase 1 | Pending |
| LEDG-06 | Phase 2 | Pending |
| LEDG-07 | Phase 1 | Pending |
| LEDG-08 | Phase 4 | Pending |
| LEDG-09 | Phase 1 | Pending |
| LEDG-10 | Phase 1 | Pending |
| LEDG-11 | Phase 2 | Pending |
| API-01 | Phase 5 | Pending |
| API-02 | Phase 5 | Pending |
| WEB-01 | Phase 5 | Pending |
| WEB-02 | Phase 5 | Pending |
| WEB-03 | Phase 6 | Pending |
| WEB-04 | Phase 5 | Pending |
| WEB-05 | Phase 5 | Pending |
| WEB-06 | Phase 5 | Pending |
| WEB-07 | Phase 5 | Pending |
| WEB-08 | Phase 6 | Pending |
| WEB-09 | Phase 5 | Pending |
| WEB-10 | Phase 5 | Pending |
| WEB-11 | Phase 6 | Pending |
| WEB-12 | Phase 6 | Pending |
| OPS-01 | Phase 5 | Pending |
| OPS-02 | Phase 2 | Pending |
| OPS-03 | Phase 2 | Pending |
| OPS-04 | Phase 5 | Pending |
| OPS-05 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 65 total (24 [CRITICAL], all in Phase 1)
- Mapped to phases: 65
- Unmapped: 0 ✓
- Per phase: Phase 1: 24 · Phase 2: 9 · Phase 3: 7 · Phase 4: 7 · Phase 5: 12 · Phase 6: 6

---
*Requirements defined: 2026-11-17*
*Last updated: 2026-11-17 after roadmap creation (traceability mapped to 6 phases)*
