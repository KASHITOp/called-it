# Project Research Summary

**Project:** CALLED IT. — Earnings Nowcaster
**Domain:** Alt-data quarterly revenue nowcasting for Indian listed consumer companies (DMART, ETERNAL, TITAN), with a hash-locked, append-only public prediction ledger
**Researched:** 2026-11-17
**Confidence:** MEDIUM-HIGH (library and tooling facts HIGH; data-source behaviour and Indian disclosure timing MEDIUM; SEBI/regulatory LOW-MEDIUM)

## Executive Summary

CALLED IT. is a point-in-time forecasting system, and the forecasting is the easy part. Credible practice (ALFRED vintages, GDPNow, Metaculus track records) rests on three properties: every input is stored with the instant it became public (`available_at`), every forecast is frozen before the reveal in a form a third party can verify, and every forecast is graded against a naive benchmark, including when the benchmark wins. With 12-16 quarters per company (about 40-60 pooled rows), model sophistication counts for very little and is easily read as overfitting. Ridge on 5-8 scale-free features, with intervals from walk-forward split-conformal residuals, is the right level. A quant reviewer will judge the project on the leakage tests, the reveal calendar, the ledger, and how honestly the backtest and live results are kept apart.

Recommended approach: a uv workspace on Python 3.12 (not 3.11, because numpy 2.5 needs at least 3.12). SQLAlchemy 2.1 Core and Alembic run on both SQLite and Supabase Postgres, with insert-only triggers on both and tests proving the triggers fire. Use a bitemporal observation store that only a `PointInTimeReader(as_of)` can read. Use a canonical JSON ledger (sorted keys, decimal strings, RFC 3339 UTC) with a `prev_hash` chain, golden test vectors shared by pytest and JS, and OpenTimestamps anchoring. The frontend is Next.js 16.4 with TypeScript 6 (not 7), statically exported, with an optional read-only FastAPI. Historical revenue and reveal dates must come from a hand-curated seed CSV with source URLs, because NSE and BSE return Akamai 403s. Trends history comes from manual CSV exports, and live pulls use trendspyg (pytrends was archived in April 2025). GST comes from the GSTN Excel files.

The dominant risk is the calendar. Today is 2026-11-17. DMART's Q3 FY27 business update is expected around 1-5 Jan 2027 (Q3 FY26's came on 5 Jan 2026, and DMART often files 2-3 days after quarter-end), and its date is not announced in advance. That leaves about 6 weekly locks, with the official call locked by about 31 Dec 2026 and spanning the New Year holiday, when GitHub cron delays and Supabase pauses are likely. Three data traps would silently make the record dishonest:
- Google Trends rescales to the peak of the requested window, so a single modern backfill leaks future information.
- GST collections for month M cover transactions from M-1, and GST 2.0 (22 Sep 2025) breaks the series. Oct 2026 printed +22.9% YoY, mostly a base effect.
- Using `results_date` instead of the earlier business-update date as the reveal makes the backtest look 2-4 weeks better informed than any real forecaster could have been.

Eternal's Blinkit inventory-model shift is a multi-quarter structural break that also distorts the baseline.

## Key Findings

### Recommended Stack

Versions were checked against PyPI and npm on 2026-11-17 (see STACK.md).

**Core technologies:**
- **Python 3.12 + uv 0.13 workspace:** one lockfile, and later projects (volsurface, terminal) add members without restructuring.
- **pandas 3.1, scikit-learn 1.9, pydantic 2.14, typer, httpx:** pandas 3 has Copy-on-Write on by default, so chained assignment silently does nothing. Use `.loc` everywhere.
- **SQLAlchemy 2.1 Core + Alembic 1.20 + psycopg 3.3:** one code path for both backends, with triggers defined in migrations. Supabase needs the session pooler (5432) from GitHub Actions and the transaction pooler (6543, prepared statements off) from Vercel.
- **Models:** `RidgeCV` (official), then `HistGradientBoostingRegressor` with tiny-data settings (`min_samples_leaf` 3-5, `max_depth` 2). No LightGBM, XGBoost or MAPIE. Use a custom splitter keyed on `reveal_at`, not `TimeSeriesSplit`.
- **Next.js 16.4.6 + React 19.3 + Tailwind 4.3 (CSS-first `@theme`) + TypeScript 6.0.3.**
- **GitHub Actions cron**, which runs in UTC, can be delayed, and is disabled after 60 days of repo inactivity.
- **Data sources:**
  - trendspyg 1.9 for live Trends pulls, with manual Trends CSVs for history.
  - GSTN `.xlsx` files for GST. They are overwritten in place, so snapshot them with a SHA-256.
  - A seed CSV for revenue and reveal dates.
  - Apple App Store RSS (India) for app rank.
  - Company careers pages (only where robots.txt allows) for jobs. No Naukri, no LinkedIn, no JobSpy.

### Expected Features

**Must have (table stakes, v1 before the first Q3 FY27 lock):**
- Point-in-time store, a gateway reader, and a reveal calendar with **timestamps** (`business_update_at`, `results_at`, `reveal_at = min`) and expected/confirmed status.
- Leakage tests that include a deliberate-leak test, which must fail.
- Provenance and structural-break markers (GST 2.0, Blinkit), plus feature snapshots for each lock.
- Trends pulled per as-of window and vintaged.
- The naive baseline and a walk-forward backtest with skill metrics.
- 80% intervals with their empirical coverage and n.
- Model versioning and a frozen model, plus a reproducible CLI.
- The canonical, hash-chained, append-only ledger: grading rules published in advance, automatic VOID for post-reveal locks, gaps shown for missed weeks, annotation rows instead of edits, an export, and a verifier.
- OpenTimestamps anchoring for every lock. Without it, "provably" overclaims.
- Site: front page, strict LIVE/BACKTEST separation, record, scoreboard, methodology, SEBI-safe disclaimer, data-freshness status, client-side WebCrypto verify.

**Should have (differentiators, v1.x during Q3 FY27):**
- GDPNow-style convergence chart, once 3+ weekly locks exist.
- "What the model saw" panel.
- "What moved the nowcast" ridge contribution breakdown.
- Error by weeks before reveal.
- CI badge for the leakage tests.
- Interval score.
- "Wrong count" honesty microcopy, computed from the grades table.

**Defer (v2+):**
- GBM as a locked challenger model.
- Forward-collected features (app rank, jobs) in the model. Only after 4+ quarters of history, and only under a new model version.
- Trends vintage diff view.
- Manually entered, cited consensus figures.
- TRENT and FSN, added through `universe_change` ledger rows.

**Anti-features (never build):**
- Buy/sell framing, or beat/miss versus the Street.
- Scraped consensus.
- A blended backtest+live accuracy number.
- Re-scoring past calls with newer models.
- Edits, deletes or backfilled locks.
- Tuning sliders.
- Synthetic filler data.

### Architecture Approach

The system is a Python package pipeline writing to a bitemporal store, an append-only ledger, and derived grading state. A static JSON export feeds the Next.js broadsheet, and FastAPI provides the same contract as an optional live transport.

**Major components:**
1. **`pitdata` store and reader:** a `series`/`observations` schema with `period_date`, `available_at` and `availability_basis`, plus insert-only triggers. Nothing reads observations except through `PointInTimeReader(as_of)`.
2. **Collectors:** one module per source, each returning typed `ObservationIn` records with a seed-CSV fallback. Every run is logged in `collector_runs`, and failures are visible, never silent gaps.
3. **Feature builder + baseline + walk-forward harness:** features use an explicit `as_of`, are scale-free (log YoY), are horizon-matched (partial-quarter features in training as well as live), and carry their lineage.
4. **Model registry:** joblib artefacts, with the version, feature list, hyperparameters, training-row IDs and git SHA all inside the hashed payload.
5. **Ledger:** canonical spec v1, `prev_hash` chain, triggers that also guard against REPLACE and TRUNCATE, a lock guard, OTS proofs, and a `ledger.jsonl` witness committed to git.
6. **Grading as derived state:** the official call is the last *valid* lock before `reveal_at`. There is no mutable `is_official` flag, and grading uses the first-reported actual.
7. **Read API + static export, and the web app:** `canonical.ts` is tested against the shared golden vectors.

### Critical Pitfalls

1. **Trends is not point-in-time.** Store every fetch as a vintage. For the backtest, request windows that end at the as-of date, use only scale-invariant features, and measure the noise across repeated fetches. Label the backtest "pseudo-real-time". Search brand terms or topics ("Tanishq", "Zomato", "Blinkit", "DMart"), never "Titan" or "Eternal".
2. **GST month offset and the regime break.** Q3 maps to the Nov, Dec and Jan collections, and at most about 2 of those 3 months are ever public before a reveal. Build totals from CGST+SGST+IGST excluding cess, and add a 2025-09 regime marker. Decide the GST 2.0 treatment (stacked two-year growth is preferred) **before the first live lock**.
3. **Wrong reveal instant.** Business updates are not pre-announced. Use `earliest_plausible_reveal = quarter_end + N` (DMART N=1, Titan/Trent/Nykaa N=2, Eternal N=7) and lock before it. Every historical DMART and Titan quarter needs a `business_update_at` with a filing URL. Compare timestamps in UTC, because an IST filing at 00:15 falls on the previous UTC day.
4. **Hash does not verify in the browser.** Python and JS differ on float formatting and key order. Use decimal strings, sorted keys, and golden vectors run in both test suites in CI. Add a hash chain and OTS so the self-reported clock and any trigger bypass become detectable.
5. **Small-sample overfitting and Eternal's break.** Use per-company intercepts, keep preprocessing inside each fold, log experiments, and label intervals with n. Eternal's Q3 FY27 call should carry a "low confidence: post-break comparables limited" label.
6. **Missed final lock.** Holiday cron delays or a paused Supabase project mean no first edition. Run the final lock redundantly, at least 48h before the earliest plausible reveal, with a heartbeat alert and a dry run in mid-December.
7. Also covered in PITFALLS.md: mixing standalone and consolidated revenue, price effects (Titan/gold, GST pass-through, Diwali shifting into Q3 FY27), survivorship in the hand-picked universe, and SEBI research-analyst boundaries.

## Disagreements Between Sources (resolve explicitly)

1. **App rank signal: Play Store (PROJECT.md) vs Apple App Store RSS (STACK.md).** STACK.md and PITFALLS.md agree that the Play Store has no public, ToS-clean chart rank. Its installs bucket barely moves, and scrapers are unofficial and stale. Apple's India top-free RSS was verified live and is official. **Recommendation:** use Apple RSS rank plus `userRatingCount` as the "app rank" signal. Optionally collect Play app-detail metadata (rating count, score) once a day with a failure flag, but never scrape Play charts. Update PROJECT.md's wording from "Play Store rank" to "app-store rank (Apple RSS) + Play ratings count". The user needs to confirm this.
2. **Build order: ledger before the model (ARCHITECTURE.md, FEATURES.md) vs the user's stated order (model in Phase 4, ledger in Phase 5).** The research argues for getting the ledger live with **baseline-only locks** as soon as the baseline exists, because each week without a lock is one less convergence point and only about 6 remain. **Recommendation:** keep the user's seven-phase structure, but run Phase 5 straight after the Phase 3 baseline, before or in parallel with Phase 4. In practice that means swapping 4 and 5. Phase 7's lock cron then needs a minimal manual or early-cron slice running from about week 3. Separately, STACK.md and PITFALLS.md want the forward collectors' daily cron live in Phase 2, not Phase 7, because forward data lost on any day can never be recovered.
3. **Minor: DMART reveal date.** Estimates range from 2-3 days after quarter-end (PITFALLS.md) to 2-5 Jan (STACK.md and ARCHITECTURE.md, which cite Q3 FY26 on 5 Jan). Treat 1 Jan 2027 IST as the earliest plausible reveal. The official DMART lock goes in on or before 30-31 Dec, so December GST (published about 1 Jan) is likely unavailable. Say this openly.

## Implications for Roadmap

The time budget sets the plan. Today is 17 Nov 2026, the final DMART lock is due about 30-31 Dec 2026, and the reveal is expected about 1-5 Jan 2027. Phases 1-3 plus the ledger and baseline locks must be done by about 1 Dec to get 4+ live weekly locks. The main model should join by mid-December or not at all for Q3, with baseline-only official calls as an acceptable and honest fallback. The web app can come after the first locks, because the ledger plus its git witness are the evidence and the site only displays them.

Suggested order, mapped to the user's 7 phases:

### Phase 1: Scaffold, config, schema, store, leakage test (target: about 24 Nov)
**Rationale:** everything depends on availability-dated types, and the leakage test is the most important test in the repo.
**Delivers:**
- uv workspace and monorepo dirs.
- `universe.toml`, including per-company `earliest_plausible_reveal` offsets and break markers.
- Fiscal and reveal calendar types (UTC timestamps).
- SQLAlchemy Core schema plus Alembic triggers on SQLite and Postgres.
- `PointInTimeReader`.
- Leakage suite on synthetic data, including the deliberate-leak test that must fail, plus IST/UTC boundary tests.
- CI on both backends.

**Avoids:** pitfalls 3, 8 and 11 (filtering on `period_date`, trusting triggers without testing them).

### Phase 2: Collectors, seed fallbacks, forward collectors (target: about 1 Dec, with forward cron live early)
**Rationale:** forward data is lost every day it isn't collected, and every model input comes from here.
**Delivers:**
- Seed CSV of revenue and reveal dates with source URLs, consolidated basis, and `business_update_at`.
- GSTN Excel snapshots with month M available on 1 M+1.
- Trends manual-CSV seed plus vintaged trendspyg pulls.
- Apple RSS rank and ratings collectors.
- Careers-page counts where allowed.
- `collector_runs`, and a minimal `collect-daily.yml` pulled forward from Phase 7.

**Avoids:** pitfalls 1, 2, 5 and 9.

### Phase 3: Features, baseline, walk-forward backtest
**Delivers:**
- As-of feature builder with lineage, horizon-matched to the lock dates.
- GST 2.0 and Blinkit break handling.
- Baseline.
- Reveal-keyed expanding-window harness and backtest table.

**Avoids:** pitfalls 1, 2, 4, 6 and 7. **Decision gate:** the GST 2.0 treatment and the Eternal treatment are frozen and written down here.

### Phase 4 (recommended: do the user's Phase 5 first or in parallel): Ledger, hashing, grading, append-only
**Rationale:** baseline-only locks can start about 1 Dec. That buys 4-5 extra convergence points and proves the ledger before the reveal.
**Delivers:**
- Canonical spec v1 and golden vectors.
- Hash chain and OTS anchoring.
- REPLACE/TRUNCATE guards.
- Lock guard and automatic VOID.
- Grading rules published in advance, with grading as derived state.
- `predict`/`grade`/`verify` CLI.
- Weekly lock workflow (minimal) and `ledger.jsonl` git witness.

**Avoids:** pitfalls 10, 11 and 13.

### Phase 5 (user's Phase 4): Main model and versioning
**Delivers:**
- RidgeCV with per-company intercepts.
- Split-conformal 80% intervals with coverage and n.
- Model registry, with the model joining the weekly locks under its own `model_version`, frozen before mid-December.
- Model-vs-baseline report. Publish it even if the baseline wins.

**Avoids:** pitfall 7. Freeze the model before the first model lock.

### Phase 6: FastAPI and Next.js
**Delivers:**
- Read-only API and static export.
- Broadsheet pages with LIVE/BACKTEST separation, methodology, disclaimer and freshness.
- `canonical.ts` with vitest on the shared vectors.
- WebCrypto verify UX.

**Avoids:** pitfall 12 (SEBI framing, cherry-picking). Target: live before about 20 Dec.

### Phase 7: Cron, deploy, README
**Delivers:**
- Hardened and redundant cron (daily collect, weekly lock, redundant final lock, daily grade).
- Heartbeat alert and a Supabase keep-alive.
- Vercel deploy.
- CI that verifies the ledger against the published export.
- README covering limitations and survivorship.

**Must include:** a dry run of the final lock by about 15 Dec. **Avoids:** pitfalls 13 and 14.

### Phase Ordering Rationale
- Dependency chain: calendar types → PIT store → leakage tests → collectors → features/baseline → ledger → model → API/web → ops.
- Two deviations from the user's order, both driven by the clock:
  - Forward-collector cron moves from Phase 7 to Phase 2.
  - Ledger and baseline locks move ahead of, or run in parallel with, the main model.
- If the user keeps the strict order, the roadmap should at least make "baseline lock in the ledger by about 1 Dec" an explicit milestone.

### Research Flags

Phases likely needing `--research-phase`:
- **Phase 2:** GSTN Excel layout and definition restatement, per-company careers ATS endpoints, trendspyg reliability from Actions IPs, and exact historical business-update timestamps from filings.
- **Phase 3:** choosing the GST 2.0 regime treatment and the Eternal break handling (few clean post-break rows).
- **Phase 4 (ledger):** OpenTimestamps client and upgrade flow, Postgres trigger-bypass coverage on Supabase.

Phases with standard patterns (skip research): Phase 1 (uv, SQLAlchemy, Alembic), Phase 5 (sklearn ridge and conformal are well documented), Phase 6 (Next.js static export, FastAPI), Phase 7 (Actions and Vercel, apart from holiday-scheduling hardening).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Versions read from the registries on 2026-11-17. NSE/BSE 403s and Apple RSS were live-probed. Actions-IP behaviour is unverified (MEDIUM). |
| Features | MEDIUM | Forecast-evaluation and PIT methods are HIGH. Competitor details and India calendar facts are MEDIUM. |
| Architecture | MEDIUM-HIGH | Hash spec and SQLite triggers were checked by running code. Platform facts are MEDIUM. |
| Pitfalls | MEDIUM | Corporate events cross-checked across secondary sources. Tooling gotchas HIGH. SEBI LOW-MEDIUM (not legal advice). |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address
- **Exact DMART and Titan business-update timestamps for every historical quarter.** Verify them from filings while building the seed CSV. This is the foundation of the reveal calendar.
- **GST 2.0 definition change:** whether prior-year bases are restated, and how cess is treated. Verify against the GSTN files.
- **Eternal figures** (Blinkit's inventory share, the Hyperpure decline). Verify against the shareholder letters.
- **Trends access:** whether trendspyg works from GitHub runners, and whether official Trends API alpha access can be granted. Apply now.
- **Revenue basis:** consolidated vs standalone for each company's target, and the first-reported vs restated policy.
- **User confirmation needed:** the app-rank source swap, the build-order change, and the GST 2.0 treatment.
- **Supabase free-tier pause behaviour over the New Year holiday.**

## Sources

### Primary (HIGH confidence)
- PyPI and npm registries (versions, 2026-11-17).
- Live probes: nseindia.com and api.bseindia.com (Akamai 403), Apple RSS `rss.marketingtools.apple.com/api/v2/in/...`, gst.gov.in/download/gststatistics.
- Official docs: SQLite and Postgres triggers, GitHub Actions schedule, Supabase poolers, Next.js 16.4, sklearn.

### Secondary (MEDIUM confidence)
- Business Today: DMART Q3 FY26 update (5 Jan 2026) and results (10 Jan 2026).
- BSE filing PDFs and Bajaj Broking (DMART timing).
- Business Standard, IndBiz, Upstox and Deccan Herald (GST 2.0, Oct 2026 +22.9%).
- Inc42, YourStory and Indian Startup News (Eternal/Blinkit).
- ALFRED, GDPNow and Metaculus methodology.

### Tertiary (LOW confidence)
- Third-party Play chart forks.
- Careers-page ATS availability.
- SEBI RA/finfluencer interpretation.
- trendspyg longevity (single maintainer).

---
*Research completed: 2026-11-17*
*Ready for roadmap: yes*
