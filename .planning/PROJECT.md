# CALLED IT. — Earnings Nowcaster

## What This Is

CALLED IT. predicts the quarterly consolidated revenue of Indian listed consumer companies (starting with Avenue Supermarts, Eternal and Titan) *before* the numbers are disclosed, using only public alternative data: Google Trends, GST collections and, as history builds up, forward-collected signals such as Play Store ranks and job postings. Every prediction is timestamped, SHA-256 hashed and written to an append-only ledger, then graded against the actual reported number. It is a portfolio piece for a buy-side/quant finance career, where rigour and honesty matter more than features, and it is Project 1 of a 3-project sprint (Nowcaster → Nifty Volatility Surface Engine → AI Indian Markets Terminal) that shares this monorepo.

## Core Value

**Provably honest predictions:** every call is made with only the data that was public at the time (no lookahead), locked with a verifiable hash before the reveal, never edited, and graded in public against a naive baseline, even when the baseline wins.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Monorepo scaffold (`/data`, `/nowcaster`, `/web`, `/tests`, `/.github/workflows`) that later projects can reuse
- [ ] Company universe in a config file (DMART, ETERNAL, TITAN; stretch TRENT, FSN), swappable without code changes
- [ ] Availability-dated store: every data point carries `period_date` and `available_at`
- [ ] Leakage guard: features for quarter Q use only rows with `available_at < reveal_date(Q)`, plus unit tests that fail on any leak (the most important test in the repo)
- [ ] Historical collectors: quarterly revenue, Google Trends (weekly), GST collections (national + state-wise), each with a seed-CSV fallback
- [ ] Forward collectors (Play Store rank, job postings) logging daily from now on, flagged "forward-collected"
- [ ] Baseline model: same-quarter-last-year × (1 + trailing YoY growth)
- [ ] Walk-forward (expanding window) backtest with a printed results table (MAPE, directional accuracy, per company and overall)
- [ ] Main model: YoY-growth regression (ridge first, then gradient boosting) on 5–8 features, with train-vs-test error printed and an 80% interval
- [ ] Versioned models; honest model-vs-baseline comparison
- [ ] Append-only prediction ledger with SHA-256 hashes, enforced in code and by a DB trigger
- [ ] Weekly locked nowcasts plus a final "official call" before each reveal; `nowcast predict` and `nowcast grade` CLI
- [ ] Grades table: error %, inside-interval, beat-baseline
- [ ] Read-only FastAPI API
- [ ] Next.js + Tailwind frontend ("CALLED IT." broadsheet): front page, The Record, scoreboard, methodology, disclaimer
- [ ] GitHub Actions cron for daily collectors and weekly locks; Vercel deploy
- [ ] README with how to run it, methodology and honest limitations
- [ ] One command to set up, one command to run everything

### Out of Scope

- Buy/sell signals or trade recommendations — research/educational only, never investment advice
- Synthesised or faked data presented as real — if a source fails we fall back to manual CSVs and say so
- Random train/test splits — walk-forward only, because random splits leak the future
- Historical Play Store / job-posting backfill — not freely available; these are collected forward from now and used only once enough history exists
- Fighting anti-scraping or breaching a source's terms — fall back to a manual seed CSV instead
- Predicting profit, EPS or margins — revenue only for v1, since the signals map to demand
- Large feature sets / deep models — 12–16 quarters per company can't support them without overfitting
- Editing or deleting predictions — the ledger is append-only by design

## Context

- **Live quarter:** today is 2026-11-17. Q2 FY27 has already been reported, so the first live, locked edition is **Q3 FY27 (Oct–Dec 2026)**, with reveals around Jan–Feb 2027. Earlier quarters (including Q3 FY26) exist only as walk-forward backtest results, clearly labelled as such.
- **Indian fiscal labels:** FY runs Apr–Mar. Q1 = Apr–Jun, Q2 = Jul–Sep, Q3 = Oct–Dec, Q4 = Jan–Mar. Q3 FY27 = Oct–Dec 2026. Revenue is in ₹ crore.
- **Reveal date = earliest public revenue disclosure.** DMART publishes a standalone revenue update shortly after quarter-end, and Titan publishes a quarterly business update with growth %, both before the board results. `reveal_date(Q)` is the earliest of these disclosures and the formal results filing. Features must be available strictly before it, and every prediction must be locked before it. The data stores both `business_update_date` and `results_date` so we can audit this.
- **Revenue basis:** consolidated revenue from operations (Titan incl. CaratLane, Eternal incl. Blinkit). Where an early disclosure is standalone (e.g. DMART's update), it counts as the reveal for timing, but grading uses consolidated revenue from the results filing.
- **Eternal structural break:** Blinkit's switch to an inventory-led model in 2025 inflated consolidated revenue for accounting reasons rather than demand. The company config carries a structural-break marker; quarters whose YoY comparison straddles the break are excluded from fitting and flagged. This is reported openly as a limitation in the backtest and UI.
- **Data available historically (backtest-eligible):** quarterly revenue (results filings), Google Trends (weekly, multi-year), monthly GST collections (national + state-wise, published early the following month). GST `available_at` = publication date, not month-end.
- **Forward-collected only:** Play Store ranks, job-posting counts. Logged daily from now, used as features only after enough history exists, and labelled "forward-collected" in the UI.
- **GST features:** national total YoY plus the YoY of the state(s) that make up most of each company's sales (set per company in config, e.g. Maharashtra for DMART).
- **Sample size:** about 12–16 quarters per company, which is why features are capped at roughly 5–8 and train vs test error is always printed.
- **Ledger cadence:** a locked nowcast every week during the quarter as data arrives. Every one is graded, and the last one before the reveal is the headline "official call". This shows how the estimate converged.
- **Frontend direction (Phase 6, built with the Hallmark plugin):** a salmon-pink financial broadsheet. Black ink, signal-red accent, visible column grid lines. Heavy condensed serif for big numbers, typewriter mono for hashes and timestamps, clean sans for body. Front page "VOL. 1 · Q3 FY27 EDITION": each company's revenue call as a headline with a countdown to its reveal date. "The Record": an archive of past editions, with each prediction card showing its SHA-256 hash like a serial number and a "verify" button that recomputes it client-side. Results day: rubber-stamp animation, red "CALLED IT" or grey "MISSED (by X%)". "MODEL vs BASELINE" boxing-match scoreboard (if the baseline is winning, say so proudly). A methodology page that explains lookahead bias in plain English. Dry humorous microcopy ("This model has been wrong 3 times. We printed all 3."). Footer: "Research only. Not investment advice. Barely advice at all." Data comes from the FastAPI read API.
- **Future reuse:** `/data` (ingestion + availability-dated store) is shared infrastructure for the Volatility Surface Engine and the AI Indian Markets Terminal.

## Constraints

- **No lookahead bias**: `available_at < reveal_date(Q)` for every feature row, walk-forward splits only, and leakage tests that fail on any violation — this is the credibility of the whole project
- **Tech stack**: Python 3.11+, uv, pandas, scikit-learn, pytrends, httpx, pydantic, typer, pytest — the user specified these
- **Storage**: Postgres (Supabase) in production, SQLite for local dev, switched by one config flag — easy local runs, real DB in deployment
- **Frontend**: Next.js + Tailwind in `web/`, deployed on Vercel, reading from a small read-only FastAPI API
- **Scheduling**: GitHub Actions cron for daily collectors — free and visible
- **Data ethics**: respect robots.txt and terms of service, and fall back to manual seed CSVs in `data/seed/` with exact download instructions — no fighting blocks
- **Data honesty**: never synthesise data and present it as real; report source failures plainly
- **Immutability**: the predictions table is append-only, enforced in application code and by a DB trigger (on both Postgres and SQLite)
- **Simplicity**: one command to set up the backend, one to run everything
- **Process**: build in phases; after each phase, show runnable commands plus output and wait for the user's "go"; complete, paste-ready files only; run tests before calling a phase done
- **Compliance**: research/educational only; no buy/sell calls anywhere in the product

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| First live edition is Q3 FY27, not Q3 FY26 | Q3 FY26 and Q2 FY27 are already reported, so only Q3 FY27 can be honestly called in advance | — Pending |
| Reveal date = earliest public revenue disclosure | Business updates (DMART, Titan) reveal revenue before board results; locking after them would be meaningless | — Pending |
| Predict consolidated revenue from operations | It's the number the market reacts to; includes CaratLane and Blinkit | — Pending |
| Weekly locked nowcasts + final official call | Shows convergence and leaves a richer graded record; headline = last lock before reveal | — Pending |
| Eternal kept, structural break flagged and excluded from fitting | Blinkit's inventory-model shift is an accounting jump, not demand; hiding it would be dishonest | — Pending |
| GST features: national + key states per company | More company-relevant signal while staying inside the 5–8 feature budget | — Pending |
| Baseline must exist first, and every model is reported against it | Honesty is the brand; a model that doesn't beat naive is reported as such | — Pending |
| Monorepo from day one | Later sprint projects reuse `/data` and the repo | — Pending |
| Append-only ledger enforced in code + DB trigger | Two layers make the "never edited" claim credible; the hash makes it verifiable | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-11-17 after initialization*
