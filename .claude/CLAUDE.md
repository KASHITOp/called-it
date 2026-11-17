<!-- GSD:project-start source:PROJECT.md -->

## Project

**CALLED IT. — Earnings Nowcaster**

CALLED IT. predicts the quarterly consolidated revenue of Indian listed consumer companies (starting with Avenue Supermarts, Eternal and Titan) *before* the numbers are disclosed, using only public alternative data: Google Trends, GST collections and, as history builds up, forward-collected signals such as Play Store ranks and job postings. Every prediction is timestamped, SHA-256 hashed and written to an append-only ledger, then graded against the actual reported number. It is a portfolio piece for a buy-side/quant finance career, where rigour and honesty matter more than features, and it is Project 1 of a 3-project sprint (Nowcaster → Nifty Volatility Surface Engine → AI Indian Markets Terminal) that shares this monorepo.

**Core Value:** **Provably honest predictions:** every call is made with only the data that was public at the time (no lookahead), locked with a verifiable hash before the reveal, never edited, and graded in public against a naive baseline, even when the baseline wins.

### Constraints

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

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## TL;DR: Decisions the Roadmap Should Encode

## Recommended Stack

### Core Technologies

| Technology | Version (verified 2026-11-17) | Purpose | Why Recommended | Confidence |
|---|---|---|---|---|
| Python | **3.12** (pin via `.python-version`) | Runtime | numpy 2.5.x requires >=3.12. Vercel Python defaults to 3.12. sklearn 1.9, pandas 3.1, SQLAlchemy 2.1 and FastAPI 0.163 all require >=3.11. 3.12 has the widest wheel coverage today. | HIGH |
| uv | 0.13.8 | Env, lockfile, workspaces, script runner | User-fixed. A single `uv.lock` across the workspace gives one-command setup (`uv sync`). `astral-sh/setup-uv@v10` caches it in CI. | HIGH |
| pandas | 3.1.1 | Time-series frames, feature building | User-fixed. **pandas 3.x has Copy-on-Write on by default and a new default `str` dtype.** Chained assignment silently does nothing, so write `df.loc[...] = ...` everywhere. | HIGH |
| numpy | 2.5.x | Numerics | Pulled in by pandas and sklearn. | HIGH |
| scikit-learn | 1.9.1 | Ridge, HistGradientBoosting, QuantileRegressor, metrics | User-fixed. Covers ridge, GBM and quantile loss with no extra dependency. | HIGH |
| pydantic | 2.14.3 | Data contracts (company config, observations, ledger payloads, API schemas) | User-fixed. Shared by FastAPI. Gives strict validation of `available_at` and `period_date` at ingestion boundaries. | HIGH |
| pydantic-settings | 2.16.3 | The single config flag (`DATABASE_URL`, `CALLEDIT_ENV`) | Reads env and `.env`. This is the "one config flag" switch between SQLite and Postgres. | HIGH |
| typer | 0.29.1 | `nowcast predict / grade / collect / backtest` CLI | User-fixed. | HIGH |
| httpx | 0.28.1 | HTTP for collectors | User-fixed. Still the latest release (Dec 2024) and stable. Set explicit timeouts and a descriptive User-Agent. | HIGH |
| SQLAlchemy (Core) | 2.1.9 | Dialect-portable SQL over SQLite and Postgres | One code path for both backends: paramstyle, types, `insert()`/`select()`, reflection. Alembic autogenerates from the same `MetaData`. 2.1 makes greenlet opt-in (`asyncio` extra only), which is lighter for a sync codebase. | HIGH |
| Alembic | 1.20.1 | Migrations (tables + triggers) | The standard SQLAlchemy migration tool. Triggers live in migrations, so they exist on both backends. | HIGH |
| psycopg (v3) | 3.3.9 (`psycopg[binary]`) | Postgres driver | SQLAlchemy URL `postgresql+psycopg://`. Supports `prepare_threshold=None`, which the Supabase transaction pooler needs. | HIGH |
| Supabase Postgres | managed (PG 15/17) | Production DB | User-fixed. Use the **Session pooler (port 5432, IPv4)** from GitHub Actions and the **Transaction pooler (6543) with prepared statements disabled** from Vercel functions. The direct host is IPv6-only. | MEDIUM-HIGH |
| SQLite | stdlib `sqlite3` | Local dev and test DB | User-fixed. Zero setup. Supports `BEFORE UPDATE/DELETE` triggers with `RAISE(ABORT, ...)`. | HIGH |
| FastAPI | 0.163.1 | Read-only JSON API | User-fixed. Deploys to Vercel with zero config: it detects `app` and runs on Python 3.12. | HIGH |
| uvicorn | 0.54.0 | Local ASGI server | `uv run uvicorn nowcaster.api:app --reload` | HIGH |
| pytest | 9.2.0 | Tests, including the leakage-guard suite | User-fixed. | HIGH |
| Next.js | **16.4.6** (released 2026-11-09; 16.4 line released 2026-10-06) | Frontend | User-fixed. App Router + Server Components; Turbopack is the default. Cache Components are recommended in 16.4 and enabled in new `create-next-app` projects. Requires Node >=20.9; use Node 26 LTS. | HIGH |
| React | 19.3.1 | UI runtime | Bundled with Next 16.4. | HIGH |
| Tailwind CSS | **4.3.5** + `@tailwindcss/postcss` 4.3.5 | Styling (broadsheet grid, salmon palette) | User-fixed. v4 is CSS-first: `@import "tailwindcss";` plus `@theme { --color-salmon: ...; --font-display: ... }`, with no `tailwind.config.js`. | HIGH |
| TypeScript | **6.0.3** (not 7.0.2) | Frontend types | TS 7 (Go-native) has no stable JS compiler API. Next's `next build` needs `experimental.useTypeScriptCli` to use it. TS 6 works with zero flags. | HIGH |
| GitHub Actions | `actions/checkout@v7`, `astral-sh/setup-uv@v10`, `actions/setup-node@v7` | Daily collector and weekly lock cron | User-fixed. Free and publicly visible, which is itself evidence of the lock times. | HIGH |

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---|---|---|---|---|
| trendspyg | 1.9.0 | Google Trends interest-over-time (pytrends-compatible `compat.request.TrendReq`) | Weekly live Trends pulls. Use `engine="http"` in CI (no Chrome), `cache="disk"`, and stop on `RateLimitError`: don't retry, back off for over 35 minutes. | MEDIUM |
| pytrends | 4.9.2 (archived) | Only as a pluggable `TrendsSource` implementation, if the user insists | Not recommended as primary. It is archived, unpatched against 429s, and untested on pandas 3. | HIGH (on status) |
| openpyxl | 3.1.5 | `pd.read_excel` engine for GSTN `.xlsx` | GST state-wise and gross/net files. | HIGH |
| pdfplumber | 0.11.10 | Table extraction from PDFs | GSTN state-wise PDF releases, and company results PDFs if ever needed. Prefer the xlsx when one exists. | MEDIUM |
| tenacity | 9.2.1 | Retries with exponential backoff | Wrap collectors. **Never retry a 403 or a captcha page.** Only retry 5xx errors and timeouts. | HIGH |
| google-play-scraper | 1.2.7 (last release 2024-06, repo last pushed 2024-08) | Play app details (score, ratings count, installs bucket) | Optional forward signal. One request per app per day. Treat it as fragile: it uses undocumented endpoints. | MEDIUM |
| (stdlib) `hashlib`, `json`, `zoneinfo`, `tomllib` | stdlib | SHA-256 ledger hashes, canonical JSON, IST handling, company universe in TOML | Use `tomllib` for `companies.toml` (no YAML dependency) and `zoneinfo("Asia/Kolkata")` for display. Store UTC. | HIGH |
| rfc8785 | 0.1.4 | RFC 8785 JSON Canonicalization Scheme (JCS) | Optional. See the hashing note below. The simpler path is to hash a canonical string where every number is pre-formatted as a decimal string. | MEDIUM |
| hypothesis | 6.170.x | Property-based tests | Leakage guard: "for any random reveal date and any feature query, no row has `available_at >= reveal_date`". | HIGH |
| time-machine | 3.6.0 | Freezing "now" in tests | Lock or grade logic around reveal dates. It is faster and more correct than freezegun. | HIGH |
| respx | 0.23.1 | Mocking httpx | Collector tests with recorded fixtures, so tests never hit live sources. | HIGH |
| pytest-cov | 7.1.0 | Coverage | Optional. | HIGH |
| pandera | 0.36.0 | DataFrame schema checks | Optional. Assert feature frames have the expected columns, dtypes and no NaNs before fitting. | MEDIUM |
| statsmodels | 0.15.0 | OLS diagnostics | **Defer.** sklearn is enough for v1. Add it only if the methodology page needs coefficient standard errors. | MEDIUM |
| canonicalize (npm) | 5.1.0 | JCS on the client | Only if you pick the RFC 8785 route. Otherwise the browser just SHA-256s the exact stored canonical string with Web Crypto (`crypto.subtle.digest`), and needs no library. | MEDIUM |

### Development Tools

| Tool | Version | Purpose | Notes |
|---|---|---|---|
| ruff | 0.17.5 | Lint + format | One tool replaces flake8, isort and black. Configure it at the workspace root. |
| mypy | 2.4.1 | Type checking (optional) | `ty` (0.0.104) is still beta, so don't adopt it yet. |
| pre-commit | 4.7.0 | Hooks | Optional. Ruff and the trailing-whitespace hook are enough. |
| Node.js | 26 LTS | Frontend toolchain | Next 16 requires >=20.9. |
| ESLint | 10.x + `eslint-config-next` 16.4.6 | Frontend lint | Next 16 removed `next lint`, so call `eslint` directly. (MEDIUM: verify at scaffold time.) |
| Supabase CLI | latest | Optional local Postgres parity | Not needed for v1. SQLite covers local dev. Run the trigger tests against a real Postgres in CI, either as a Supabase branch or a `postgres:17` service container. |

## Data-Source Verdicts (Questions 1-4)

### 1. Google Trends

| Option | Status (late 2026) | Verdict |
|---|---|---|
| **pytrends** | Archived 2025-04-17, read-only. Last release 4.9.2 (2023-04-13). `trending_searches` returns 404 and other calls 429 under load. | **Do not use as primary.** (HIGH) |
| **trendspyg 1.9.0** | Maintained (release 2026-10-01, MIT). Has a pytrends-compatible `TrendReq` shim. `engine="http"` / `"auto"` / `"browser"` (Chrome). Raises `RateLimitError` on 429, with a documented recovery of about 35 minutes. | **Use for live weekly pulls.** (MEDIUM: one project, a single maintainer, and it still rides Google's unofficial endpoints.) |
| **Official Google Trends API (alpha)** | Announced 2025-07-24. Access is application-gated and limited. Offers about 5 years of consistently scaled data. | **Apply now, don't depend on it.** If access is granted, it is the best source: consistent scaling makes vintages comparable. (MEDIUM) |
| SerpApi (`serpapi` 1.2.0) / Apify actors | Paid, and avoids IP 429s. | Not for v1. Cost and a third-party dependency for a portfolio piece. (MEDIUM) |
| **Manual CSV export from trends.google.com** | Always works. | **Mandatory for the historical backfill.** One export per term over a 5-year window (which gives weekly granularity; longer windows return monthly). Commit to `data/seed/trends/` with exact download instructions. (HIGH) |
- Every Trends pull is a **vintage**: values are rescaled 0-100 per request and Google samples them. Store `(term, geo, week, value, pulled_at, request_window)`, and set `available_at = pulled_at` for live pulls.
- For the backtest, CSV-exported history is "data as seen today", not point-in-time. Document this as a known (small) limitation on the methodology page. Do not pretend the backfill is point-in-time.
- Expect Google to 429 GitHub-hosted runner IPs, since these are shared Azure ranges. Design the weekly collector so a 429 is a **logged, visible failure that falls back to the last good vintage**, never a silent gap. (MEDIUM: community reports, not verified from Actions.)

### 2. Indian Quarterly Results (revenue, results dates, business-update dates)

| Source | Live probe 2026-11-17 | Terms / ethics | Verdict |
|---|---|---|---|
| **NSE** (`nseindia.com`, `/api/corporate-announcements`) | Homepage returned **403, `Server: AkamaiGHost`**. The API path returned a 301 to `nseindia.in`. Community libraries (nselib, jugaad-data, nsepython) work by juggling cookies, which is the anti-bot fight the project rules out. | Akamai Bot Manager. Cloud and datacenter IPs are widely reported as blocked. | **Do not automate.** Use it manually in a browser to find filing PDFs. (HIGH) |
| **BSE** (`api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w`) | **Akamai "Access Denied" (403)**, even for `robots.txt`. The unofficial `bse` PyPI wrapper is 3.3.4 (Oct 2026). | BSE sells announcement data commercially. The endpoint is undocumented. | **Do not automate in CI.** At most, an *optional, local, manually run* "check for new filing" helper. Defer it. (HIGH on the block; MEDIUM on whether it works from Indian residential IPs.) |
| **screener.in** | — | Terms grant "personal, non-commercial transitory viewing only" and forbid copying or public display of its materials. | **Do not scrape, and do not cite as the data source.** Use it for manual cross-checking only. (HIGH) |
| **Company IR pages** (DMart investor relations, Titan quarterly business updates, Eternal shareholder letters) | Not probed individually. | Public disclosure documents. Downloading a handful of PDFs by hand is clearly fine. | **Primary human source for the seed CSV.** (MEDIUM) |
- DMART's quarterly standalone revenue update typically lands **within 2-4 days of quarter-end**. For Q3 FY27 that means about **2-5 Jan 2027**, so the "official call" lock must happen around **31 Dec 2026**.
- Titan's quarterly business update lands in the **first week after quarter-end**.
- Board meetings for results need only a few working days' prior intimation under SEBI LODR Reg 29, so `results_date` becomes known late. Store it as a nullable field that is filled when it is announced.

### 3. GST Collections

| Item | Finding | Confidence |
|---|---|---|
| Publication location | **`https://www.gst.gov.in/download/gststatistics`**: per-FY `.xlsx` files for FY2017-18 to FY2026-27. These include `statewise_GST_collection_YYYY-YY.xlsx`, `GSTR-3B-*.xlsx`, `GSTR-1-*.xlsx`, `Settlement-of-IGST-to-State-*.xlsx`, `ewb-data-*.xlsx`, and from FY2026-27 a new `Gross_Net_Tax_collection.xlsx`. | HIGH (fetched) |
| Cadence | Monthly provisional data is released on the **1st of the following month**. October 2026 data was released on 2026-11-01: gross ₹2,31,290 cr, +22.9% YoY; net ₹2,03,356 cr. | HIGH |
| History | The Finance Ministry **stopped its formal monthly press release in July 2024**, which also dropped the state-wise breakup from the release. The data kept coming via GSTN and "provisional government data" to media, plus the gst.gov.in Excel files. PIB is therefore **not** a reliable primary source for 2024-2026. | HIGH (on the July 2024 change); MEDIUM (on the exact current channel) |
| Format | `.xlsx` (one sheet per FY, with months as columns). GSTN also posts a state-wise PDF with each release. | HIGH |
| **Definition change** | The October 2026 components (CGST 42,935 + SGST 51,340 + IGST 1,37,015 = 2,31,290) **exclude compensation cess**. The October 2025 base is quoted as ₹1,88,125 cr, whereas October 2025 was reported *at the time* as about ₹1.96 lakh cr. GST 2.0 rate rationalisation (22 Sept 2025) changed both the definitions and the rates. | MEDIUM |
- **The Excel files are overwritten in place.** Each month's update rewrites the FY file, so there are no historical vintages. Build a `gst_snapshots` table that stores the raw file's SHA-256, `fetched_at`, and the parsed rows. Set `available_at` for month M to **the 1st of month M+1 (IST)** for backfill, and to the actual fetch time for live pulls.
- Build features from a **consistent component definition**: CGST+SGST+IGST excluding cess, computed from the components and never taken from headline figures. Add a config-level **structural-break marker at Sept/Oct 2025** (GST 2.0). YoY comparisons straddling it (Oct 2025 – Sep 2026) are distorted by rate cuts and base effects, which is the same treatment as Eternal's Blinkit break.
- Use `pd.read_excel(engine="openpyxl")`, plus a seed copy of each FY file in `data/seed/gst/` and a SHA-256 manifest.

### 4. Play Store Rank and Job Postings (forward-collected)

| Option | Finding | Verdict |
|---|---|---|
| **Apple App Store RSS** (`https://rss.marketingtools.apple.com/api/v2/in/apps/top-free/100/apps.json`) | **Verified live for country `in`.** It is Apple's official marketing feed, returns JSON, and needs no key. | **Use as the "app rank" signal.** Record the rank of Zomato, Blinkit, District, Tanishq, CaratLane and DMart Ready (absent = rank > 100). Also record `itunes.apple.com/lookup?id=...&country=in` → `userRatingCount` as a daily engagement proxy. (HIGH) |
| **google-play-scraper 1.2.7** | Stale (last release Jun 2024, 74 open issues). Play's web top charts are not reliably exposed. Play's `robots.txt` disallows `/store/xhr` and `/apps` but not `/store/apps/details`. | **Optional.** Use `app()` for details only (score, ratings, installs bucket), once per app per day, with a failure flag. **No chart-rank scraping.** (MEDIUM) |
| gplay-scraper / play-store-scraper-ng | Third-party forks that claim to offer top charts. | Unverified. Do not adopt. (LOW) |
| **Naukri** | Naukri's terms page itself returned 403 to an automated fetch. Its job search runs through internal APIs behind bot protection. | **Do not scrape.** (HIGH) |
| **LinkedIn / python-jobspy 1.4.1** | JobSpy scrapes LinkedIn, Indeed and Naukri. LinkedIn's User Agreement prohibits scraping. | **Do not use.** It contradicts the project's data-ethics constraint. (HIGH) |
| **Company careers pages** (each company's own site / ATS) | ATS platforms vary per company (unknown, needs phase research). Some ATS vendors expose public JSON job boards meant for embedding. | **Use if `robots.txt` allows it**: count open roles once per day. If not, mark the signal "not collected" and move on. Because it is forward-only and not a v1 feature, the downside is small. (LOW-MEDIUM) |

## DB Layer Design (Question 5)

- SQLite: on connect, run `PRAGMA foreign_keys=ON; PRAGMA recursive_triggers=ON; PRAGMA journal_mode=WAL;`
- Postgres from Vercel (transaction pooler, 6543): `connect_args={"prepare_threshold": None}` and `poolclass=NullPool`.
- Postgres from GitHub Actions: use the Session pooler on port 5432 (IPv4).
- **SQLite `INSERT OR REPLACE` deletes the conflicting row without firing DELETE triggers unless `PRAGMA recursive_triggers=ON`.** Set the pragma on every connection, never use REPLACE, and add a test that tries it and expects failure.
- **Alembic SQLite "batch" mode (`render_as_batch=True`) recreates the table (copy, then drop, then rename), which silently drops its triggers.** Never batch-alter `predictions`. Any migration that touches it must re-create the triggers. Add a test that queries `sqlite_master` / `pg_trigger` to assert the triggers exist after `alembic upgrade head`.
- **The table owner or a superuser can `ALTER TABLE ... DISABLE TRIGGER` or `DROP TABLE`.** Defence in depth:
- **Supabase exposes the `public` schema via its auto-generated Data API (PostgREST).** Put tables in a dedicated schema (e.g. `calledit`) that is not exposed, or enable RLS with no policies. Otherwise the anon key could read or write the ledger. (MEDIUM-HIGH)
- **Datetimes:** SQLite has no timezone type. Store **UTC ISO-8601** consistently: a custom `TypeDecorator` that asserts tz-aware input, normalises to UTC, and returns aware datetimes. A naive or aware mismatch in an `available_at < reveal_at` comparison is a leakage bug.

## Monorepo Layout (Question 6)

- **Do not name the import package `data`.** It is a generic top-level name that collides easily (stray `data.py`, test fixtures, other libraries). Keep the *directory* `data/` and use `calledit_data` as the import name. (HIGH)
- Use `src/` layout in both members so tests import the installed package, not the working tree.
- CLI entry point in `nowcaster/pyproject.toml`: `[project.scripts] nowcast = "nowcaster.cli:app"`.
- One-command setup is `uv sync`. One-command run is `uv run nowcast run-all` (collect, then features, predict and grade where due), plus `npm --prefix web run dev`.
- **Vercel deploys of the FastAPI service from inside a uv workspace need care.** Vercel's Python builder resolves dependencies from `pyproject.toml` or `requirements.txt` at the project root and won't understand `{ workspace = true }` sources. Plan a build step (`uv export --package called-it-nowcaster --no-hashes -o requirements.txt`), or a thin `api/index.py` at a Vercel project root. **Flag for phase research.** (MEDIUM)

## Models and Intervals (Question 7)

| Choice | Recommendation | Why | Confidence |
|---|---|---|---|
| Main model #1 | `sklearn.linear_model.RidgeCV` on standardised features (in a `Pipeline` with `StandardScaler`), target = YoY revenue growth | Stable at n≈40, interpretable coefficients for the methodology page | HIGH |
| Main model #2 | `sklearn.ensemble.HistGradientBoostingRegressor(max_depth=2, min_samples_leaf=3–5, learning_rate=0.05, max_iter≈100–200, l2_regularization=1.0, early_stopping=False)` | Native NaN handling (useful when forward-collected features are missing in early quarters), quantile loss built in, no extra dependency. **Defaults are wrong for tiny data:** `min_samples_leaf=20` would build near-stumps, and early stopping is auto-off below 10k rows anyway. | HIGH |
| LightGBM 4.7.0 | **Do not add** | Same algorithm family, so no accuracy gain at n≈40. It adds a native dependency and its own small-data parameter traps (`min_data_in_leaf=20` default). | HIGH |
| XGBoost 3.4 | **Do not add** | Requires Python >=3.12 (fine), but brings nothing here. | HIGH |
| 80% interval | **Walk-forward split-conformal.** Collect the model's *out-of-sample* residuals from all prior walk-forward folds, and set the interval to point ± the empirical 10th/90th residual quantiles (on growth, then mapped to ₹ crore). Report empirical coverage in the grades table. | Honest, model-agnostic, and computed only from data available before the call, so there is no leakage. With few residuals early on, widen conservatively or label the interval "insufficient history". | HIGH |
| Quantile models (alternative/cross-check) | `HistGradientBoostingRegressor(loss="quantile", quantile=0.1/0.9)` or `sklearn.linear_model.QuantileRegressor` | Use as a secondary check. Fitting two extra quantile models on about 40 rows is noisy, and the bounds can cross. | MEDIUM |
| MAPIE 1.6.0 | **Defer** | Its time-series conformal tools are overkill. A hand-rolled residual-quantile approach is about 20 lines and easier to explain on the methodology page. | MEDIUM |
| Splitter | **Custom quarter-aligned expanding-window splitter** keyed on `reveal_date`, not `TimeSeriesSplit` | `TimeSeriesSplit` splits on row index and knows nothing about availability dates or per-company reveal dates. | HIGH |
| Model versioning | `joblib` (ships with sklearn) for artefacts. Record `model_version`, sklearn version, feature list, hyperparameters, training-row IDs and the code git SHA **inside the hashed ledger payload**. | Makes each call reproducible and auditable. | HIGH |

## Installation

# Workspace root (virtual): dev tooling

# data package

# optional forward signal

# nowcaster package

# Frontend

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|---|---|---|
| trendspyg (behind a `TrendsSource` interface) | pytrends 4.9.2 | Only if trendspyg breaks and pytrends happens to work. Both live behind the same interface, so switching is config only. |
| trendspyg | Official Google Trends API (alpha) | **Switch the moment access is granted.** Consistent scaling fixes the vintage problem. |
| Manual seed CSV for results | `bse` 3.3.4 wrapper run locally | If a local run from an Indian IP works politely (one request per symbol per day) and BSE's terms allow it. Never in CI. |
| SQLAlchemy Core | Plain `psycopg` + `sqlite3` | A single-backend project. Dual-backend makes this a false economy. |
| SQLAlchemy Core | SQLAlchemy ORM / SQLModel | Rich object graphs with mutable state, which is the opposite of this domain. |
| Alembic | Supabase CLI migrations | Postgres-only projects. Here migrations must also run on SQLite. |
| sklearn HistGradientBoosting | `GradientBoostingRegressor` (exact, non-histogram) | Equivalent at n≈40, but it lacks native NaN handling. Pick HGB. |
| Residual-quantile conformal | MAPIE | When there are hundreds of out-of-sample points and multiple conformal schemes worth comparing. |
| Apple RSS rank | Paid app-intelligence (Sensor Tower, data.ai) | Never for this project: cost and licensing. |
| FastAPI on Vercel Python functions | FastAPI on Render/Fly/Railway | If Vercel's uv-workspace packaging proves painful, or cold starts annoy. Also note that Supabase free projects pause after about 7 days of inactivity; the daily cron keeps them warm. |
| Next.js 16.4 Server Components | Static export of JSON from the weekly job | Only if the API layer is dropped. It is user-fixed, so it stays. |

## What NOT to Use

| Avoid | Why | Use Instead |
|---|---|---|
| pytrends as primary | Archived Apr 2025, 429s unpatched, `trending_searches` 404s, untested on pandas 3 | trendspyg + manual CSV backfill |
| nselib / jugaad-data / nsepython / NseKit against nseindia.com | They work by defeating Akamai cookie gating, which violates the project's "no fighting blocks" rule, and they break unpredictably | Seed CSV from filing PDFs |
| Scraping screener.in | Its terms limit use to "personal, non-commercial transitory viewing" and prohibit copying or public display | Exchange filings and IR PDFs (manual cross-check only) |
| python-jobspy, LinkedIn or Naukri scraping | ToS violations. LinkedIn actively litigates scraping. | Company careers pages, or skip the signal |
| Play Store chart-rank scrapers | No official web chart endpoint, fragile RPC, ToS grey zone | Apple App Store RSS (official) |
| PIB press releases as the GST source | The monthly release stopped in July 2024, so coverage is spotty | gst.gov.in statistics `.xlsx` |
| Headline GST totals across Sept 2025 | Cess exclusion and GST 2.0 changed the definition, and bases were restated | Component-built series + a structural-break flag |
| LightGBM / XGBoost / deep models | No benefit at n≈40, and extra overfitting surface | RidgeCV → HistGradientBoosting with tiny-data settings |
| `sklearn.model_selection.TimeSeriesSplit` / random CV | Ignores `available_at` and reveal dates; random CV leaks the future | Custom reveal-date-aware expanding-window splitter |
| `df.to_sql(..., if_exists="replace")` | Drops and recreates tables, destroying triggers and history | Explicit SQLAlchemy `insert()` |
| SQLite `INSERT OR REPLACE` / Alembic batch on ledger tables | Bypasses delete triggers / silently drops triggers | Plain INSERT; trigger-existence tests |
| TypeScript 7.0.x | No stable compiler API; needs `experimental.useTypeScriptCli` in Next | TypeScript 6.0.3 |
| Tailwind v3-style `tailwind.config.js` | v4 is CSS-first, and the v3 config pattern is legacy | `@theme` tokens in `globals.css` |
| Supabase direct connection host from CI | IPv6-only; GitHub-hosted runners may lack IPv6 | Session pooler (5432) |
| Tables in Supabase `public` schema without RLS | Exposed via the Data API with the anon key | Private schema or RLS-on with no policies |

## Stack Patterns by Variant

- Run the weekly Trends pull locally via `uv run nowcast collect trends`, or rely on the manual CSV refresh.
- Because the ledger records which feature vintage each lock used, a missing week is visible, not hidden.
- Add a `GoogleTrendsOfficialSource` implementation and re-pull the 5-year history once. Keep the CSV backfill as the historical vintage for previously locked calls.
- Deploy FastAPI on a container host (Render or Fly) from the workspace with `uv sync --package called-it-nowcaster`. The Next.js frontend stays on Vercel.

## Version Compatibility

| Package A | Compatible With | Notes |
|---|---|---|
| numpy 2.5.x | Python >=3.12 only | On 3.11, uv would silently resolve numpy 2.4.x. Pin 3.12 to avoid split behaviour between dev and Vercel. |
| pandas 3.1.1 | numpy >=2.0.2 | CoW default; new `str` dtype. Check any pytrends code paths, since it was written for pandas 1.x. |
| scikit-learn 1.9.1 | Python >=3.11, numpy >=1.24 | — |
| SQLAlchemy 2.1.9 | Python >=3.11; psycopg 3.3 via `postgresql+psycopg://` | greenlet only with the `asyncio` extra; it is not needed here. |
| Alembic 1.20.1 | SQLAlchemy 2.1 | Use `render_as_batch=True` for SQLite **except** on ledger tables. |
| FastAPI 0.163.1 | pydantic 2.14, Python >=3.11 | — |
| pydantic-settings 2.16.3 | Python >=3.11 | — |
| Next.js 16.4.6 | React ^19, Node >=20.9 | TS 7 needs `experimental.useTypeScriptCli`; TS 6.0.3 works out of the box. |
| Tailwind 4.3.5 | `@tailwindcss/postcss` 4.3.5 | Must match versions. |
| Vercel Python runtime | Python 3.12 (default), 3.13, 3.14 | Pin with `.python-version`. |
| trendspyg 1.9.0 | Python >=3.8; Chrome only for `engine="browser"` | Use `engine="http"` in CI. |

## Sources

- **PyPI JSON API** (`pypi.org/pypi/<pkg>/json`), queried 2026-11-17: all Python versions, release dates and `requires_python` values (numpy 2.5 >=3.12; sklearn 1.9.1; pandas 3.1.1; SQLAlchemy 2.1.9; Alembic 1.20.1; FastAPI 0.163.1; pydantic 2.14.3; typer 0.29.1; httpx 0.28.1; pytest 9.2.0; psycopg 3.3.9; trendspyg 1.9.0; pytrends 4.9.2; google-play-scraper 1.2.7; bse 3.3.4; LightGBM 4.7.0; MAPIE 1.6.0; uv 0.13.8). HIGH
- **npm registry**, queried 2026-11-17: next 16.4.6 (peer react ^19, node >=20.9), react 19.3.1, tailwindcss 4.3.5, typescript 5.9.3 / 6.0.3 / 7.0.2. HIGH
- **GitHub API**: pytrends `archived: true`; trendspyg pushed 2026-10-01; google-play-scraper last pushed 2024-08-05; setup-uv v10.3.3, checkout v7.0.1, setup-node v7.1.0. HIGH
- **Live probes, 2026-11-17**:
- https://www.gst.gov.in/download/gststatistics: file inventory FY2017-18 to FY2026-27 (fetched). HIGH
- https://newsonair.gov.in/indias-gross-gst-collections-rise-23-to-%e2%82%b92-31-lakh-crore-in-oct/ and https://www.deccanherald.com/business/gst-mop-up-grows-23-to-over-rs-231-lakh-crore-in-october-2026-4203190: October 2026 GST release on 2026-11-01. HIGH
- https://theprint.in/economy/embarrassment-of-riches-govt-halts-monthly-gst-releases-as-high-collections-creating-resentment/2156852 and https://www.businesstoday.in/latest/economy/story/eyebrows-raised-after-centre-stops-release-of-monthly-gst-data-435599-2024-07-03: monthly press release halted July 2024. HIGH
- https://developers.google.com/search/blog/2025/07/trends-api and https://developers.google.com/search/apis/trends: official Trends API alpha (application-gated). HIGH
- https://github.com/flack0x/trendspyg: engines, the 429 `RateLimitError` behaviour, the pytrends compat shim. MEDIUM
- https://dev.to/esteban_ortega/pytrends-is-dead-heres-how-to-get-google-trends-data-in-2026-1a18 and https://apiserpent.com/blog/pytrends-dead-google-trends-data-2026: pytrends failure modes. MEDIUM (vendor-adjacent)
- https://www.screener.in/guides/terms/: licence terms ("personal, non-commercial transitory viewing only"). HIGH
- https://supabase.com/docs/guides/database/connecting-to-postgres: direct vs session vs transaction pooler, prepared statements. HIGH
- https://supabase.com/docs/guides/platform/free-project-pausing: free-tier pause after about 1 week of inactivity. HIGH
- https://nextjs.org/blog/next-16-4: 16.4 features, Cache Components. HIGH. Next.js TypeScript docs: TS 7 and `experimental.useTypeScriptCli`. MEDIUM (via search excerpt)
- https://vercel.com/docs/frameworks/backend/fastapi and https://vercel.com/docs/functions/runtimes/python: zero-config FastAPI, default Python 3.12. HIGH
- https://docs.astral.sh/uv/concepts/projects/workspaces: virtual root, `tool.uv.sources` workspace deps. HIGH
- https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor: quantile loss, `min_samples_leaf` guidance for small data, early-stopping threshold. HIGH
- SQLite docs (REPLACE conflict resolution vs `recursive_triggers`; `RAISE(ABORT)` in triggers) and PostgreSQL docs (`BEFORE TRUNCATE` statement triggers): from established documentation knowledge, not re-fetched this session. HIGH
- Indian disclosure timing (DMART update about 2-4 days after quarter-end; Titan business update in the first week; LODR Reg 29 intimation): domain knowledge, not re-verified this session. MEDIUM. **Verify when building the seed CSV.**

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-fast` for a trivial task inline, with no subagents and no PLAN.md
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
