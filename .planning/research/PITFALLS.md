# Pitfalls Research

**Domain:** Alt-data quarterly revenue nowcasting for Indian listed consumer companies (DMART, ETERNAL, TITAN; stretch TRENT, NYKAA/FSN) with a hash-locked, append-only public prediction ledger
**Researched:** 2026-11-17
**Confidence:** MEDIUM overall. Data-source behaviour and the corporate events (Blinkit, GST 2.0, rename, disclosure timing) were cross-checked across several secondary sources. Tooling gotchas (SQLite and Postgres triggers, JS and Python serialisation) are documented behaviour, so HIGH. Regulatory (SEBI) is LOW-MEDIUM: these are not legal conclusions.

> **How to read this:** each critical pitfall has warning signs, a prevention strategy and a phase. Phases: **P1** scaffold/config/schema/store/leakage test · **P2** collectors + seed fallbacks + forward collectors · **P3** features + baseline + walk-forward · **P4** main model + versioning · **P5** ledger + hashing + grading + append-only · **P6** FastAPI + Next.js · **P7** cron, deploy, README.

---

## Critical Pitfalls

### Pitfall 1: Google Trends history is not point-in-time. Every fetch rescales and resamples it.

**What goes wrong:**
Each Trends request returns a fresh random sample of searches. That sample is normalised so the peak inside the *requested window* = 100 and then rounded to integers. Two consequences:
1. **Normalisation leak.** If the backtest fetches 2021–2026 in one call today, the peak that defines "100" may be a week *after* the as-of date (e.g. Diwali 2025). Every earlier value is then scaled using future information. Level features ("Trends index = 63") leak. Ratio features from one fetch (log YoY = log(x_t / x_{t-52})) cancel the scale factor. They still carry the rounding error, which is large when values are small (a value of 4 vs 5 is a 25% jump).
2. **Vintage drift.** Google samples a different subset each time, and changed its sampling method in July 2022 (post-change values come out systematically higher). There are also logged "data collection improvement" breaks (2016-01-01, 2022-01-01). Repeated identical pulls have been measured to differ by up to ~230% of the mean on thin series. So the values a backtest sees in 2026 are *not* the values anyone could have seen in 2023. That makes the backtest "pseudo-real-time" at best.

There are two more traps. Trends returns weekly data only for windows under about 5 years, and monthly beyond that. Here 12–16 quarters of training plus a 1-year YoY lag is right at that limit. Stitching windows with overlap rescaling brings in its own error. The most recent week is flagged `isPartial` and changes on the next fetch.

**Why it happens:**
People treat Trends like a database with fixed history. Really it is a sampled, re-normalised query result with no vintages.

**How to avoid:**
- **Store every raw fetch as an immutable vintage**: `(term, geo, timeframe, fetched_at, payload_hash, values)`. `available_at = fetched_at`. Never overwrite.
- **Live:** features for a lock come only from a vintage fetched before the lock, with `timeframe_end ≤ lock time`. Drop rows with `isPartial = true`.
- **Backtest:** for each as-of date, request a window that *ends at the as-of date* so the peak comes only from the past. Cache these per as-of date. Use only scale-invariant features (log YoY, or z-score within the window). Label all backtest Trends features "current-vintage reconstruction, not true point-in-time" in the README and the methodology page.
- **Measure the noise:** fetch the same request 3–5 times on different days and use the mean. Report the across-fetch spread as a known noise floor. If a feature's YoY signal is smaller than its fetch-to-fetch noise, drop it.
- **Use Knowledge Graph *topics*, not raw strings, where they exist.** "Titan" is ambiguous: the June 2023 Titan submersible, "Attack on Titan", the moon. "Eternal" is a generic word. Use brand terms or topics: "Tanishq", "CaratLane", "Zomato", "Blinkit", "DMart", "Zudio", "Westside", "Nykaa". Use geo=IN.
- Record the term list in config and freeze it before the first live lock (see Pitfall 11).

**Warning signs:**
- Backtest MAPE improves when you refetch Trends (a sign the noise is fitting).
- A feature built from a raw level instead of a ratio.
- A single-window fetch spanning the whole backtest.
- Spikes that line up with news events rather than sales (submersible, IPO, controversies, outages).

**Phase to address:** P1 (vintage schema: `fetched_at`, `timeframe_end`, `is_partial`), P2 (collector stores vintages; as-of-windowed backfill), P3 (scale-invariant features only; noise-floor check).

---

### Pitfall 2: Getting the GST month wrong, and treating GST as a clean demand proxy in 2025–2027

**What goes wrong:**
- **One-month shift.** "GST collections for month M" are cash collected in M, which mostly covers transactions of M-1 (returns filed by the 20th of M). They are published around the 1st of M+1. For Q3 (Oct–Dec), the matching collections are Nov, Dec and Jan. Jan collections (Dec transactions) are published about Feb 1, after every company's reveal. DMART reports about Jan 2–3 and Titan in the first week of January. So **at most about 2 of the 3 quarter months of GST are ever available before the reveal**, and for DMART the December-collections print (Jan 1) lands about 1–2 days before the reveal. Mapping "Oct–Dec collections → Q3" is a silent off-by-one.
- **GST 2.0 regime break (effective 22 Sep 2025).** Slabs were cut to 5%/18% plus a 40% sin slab. Compensation cess was removed for most goods in Sep 2025 and for tobacco from 1 Feb 2026. Collections stopped tracking consumption: rates fell while volumes rose. Supplies were postponed in Sep 2025, which pushed down Oct–Nov 2025 collections. Then **Oct 2026 gross GST printed +22.9% YoY** (imports +42%, domestic +16%), mostly a base effect. A model trained on pre-2025 GST→revenue relationships will treat that as a demand boom and extrapolate it into the **live Q3 FY27 quarter**.
- **Series composition.** "Gross incl. cess", "gross excl. cess", "net of refunds" and "domestic vs imports IGST" behave very differently. Import IGST is not domestic consumption.
- **Publication fragility and revisions.** The monthly PIB press release stopped after June 2024. Figures then went to journalists "informally" and later to the GST portal, with state-wise tables appearing only sometimes. State-wise reporting appears again in 2026 coverage, but the format and publication channel have changed more than once. Early figures are provisional and are sometimes revised in later releases.

**Why it happens:**
GST looks like a ready-made monthly consumption index. People skip the institutional details: payment timing, rate changes, cess, imports.

**How to avoid:**
- Store `collection_month`, `transaction_month = collection_month - 1` and `available_at` (the real publication instant of the source you actually used: PDF posting time or wire-story time) as separate fields. Attribute GST to quarters by **transaction month** in the feature code, with a unit test.
- Use **gross domestic GST excluding cess** (and the key-state equivalents) as the canonical series. Keep imports and cess out.
- Add a config-driven **regime marker** at 2025-09 (the same mechanism as the Eternal structural break). Options, in order of preference: (a) a two-year stacked growth feature, (b) a regime dummy, (c) dropping GST features from quarters whose YoY straddles Sep 2025, flagged in the UI. Decide before the first live lock and write the decision into the methodology page.
- Keep every release as a vintage, as with Trends. If a later release revises a month, the old value stays for backtests whose as-of date falls before the revision.
- Seed CSV with the exact source URL and retrieval date for each month.

**Warning signs:**
- A Q3 feature that uses December collections and was "available" on Jan 1 for a DMART reveal on Jan 2. That is technically allowed but fragile, so check the timestamps.
- The model's Q3 FY27 DMART call shows +25–30% growth when the baseline shows about +15%.
- GST and revenue YoY correlations that flip sign after 2025-09.

**Phase to address:** P1 (schema fields), P2 (collector + seed with per-row source), P3 (transaction-month attribution + regime handling + tests).

---

### Pitfall 3: Wrong reveal instant. Business updates arrive days after quarter-end and are not pre-announced.

**What goes wrong:**
- DMART files a standalone revenue update about **2–3 days after quarter-end** (e.g. Q2 FY26 on 3 Oct 2025, Q1 FY25 on 2 Jul 2024). Titan's business update comes in the first week or so. **Trent** (e.g. 4 Jul 2025, about 6 Oct 2025) and **Nykaa** (about 5 Oct 2026, as growth ranges) also issue pre-results updates. Eternal has no business update, so its reveal is the results filing (about 3 weeks after quarter-end).
- Board meeting dates for results are announced in advance; **business-update dates are not**. Setting the lock deadline to the "expected" DMART date risks a lock that lands after the reveal.
- Date-only comparisons are a problem. Updates often go out in the evening IST. A lock at 22:00 IST on the reveal date is "same date" in IST but may already be after the reveal.
- Using `results_date` as the reveal for DMART or Titan makes historical backtests look 2–4 weeks better-informed than any real forecaster could have been.
- For DMART, the Q3 quarter has almost no in-quarter data by the deadline (see Pitfall 2). Its "nowcast" is mostly baseline plus Oct–Nov signals. That is fine if it is said openly.

**Why it happens:**
"Results day" is the habit. Indian companies' voluntary updates are easy to miss, and their timing changes.

**How to avoid:**
- Store `business_update_at` and `results_at` as **UTC instants** (from the NSE/BSE announcement timestamp, IST converted to UTC). `reveal_at = min(...)`.
- For **live** quarters, use a conservative config value `earliest_plausible_reveal = quarter_end + N days` per company (DMART: N = 1, Titan/Trent/Nykaa: N = 2, Eternal: 7). The official call must lock before it. Weekly locks continue only up to that deadline.
- The leakage guard compares instants: `available_at < reveal_at`. Never compare dates. Add a test with a reveal at 18:00 IST and a feature at 20:00 IST on the same calendar date.
- Backtest: fill `business_update_at` from the archived filings for every historical quarter. If an update date can't be confirmed, use `quarter_end + 1 day` (conservative) and flag it.

**Warning signs:**
- `reveal_date` stored as `DATE`.
- No `business_update_at` column, or nulls for DMART or Titan.
- The DMART backtest uses December GST or late-December Trends with no timestamp check.

**Phase to address:** P1 (schema + guard on instants + IST boundary tests), P2 (collect update timestamps), P5 (lock deadline enforcement), P7 (cron must fire before the deadline, see Pitfall 13).

---

### Pitfall 4: Eternal's break is spread over several quarters. Both the model and the baseline are distorted.

**What goes wrong:**
Blinkit moved from marketplace (commission revenue) to inventory-led (gross sales revenue) gradually through 2025. About 80% of Blinkit's NOV was inventory-led by Q2 FY26, when consolidated revenue printed about ₹13,590 cr (+183% YoY). The company itself said YoY was not like-for-like. At the same time **Hyperpure revenue fell about 31%**, because supplies to Blinkit stopped being external sales. So the break has offsetting parts and covers several quarters.
- YoY comparisons straddle the transition for roughly Q4 FY25 → Q2 FY27. **The live Q3 FY27 quarter compares against a Q3 FY26 that was only partly inventory-led**, so it may still be distorted.
- If you drop straddling quarters, Eternal has about 0–2 clean post-break training rows. The pre-break relationship between search interest and take-rate revenue does not carry over to revenue tied to gross order value.
- **The naive baseline is also broken.** "Same quarter last year × (1 + trailing YoY)" with a trailing YoY of +150–180% forecasts nonsense. If the model gets a break correction and the baseline doesn't, the model-vs-baseline result is rigged.
- Rename: the company is Eternal Ltd from 20 Mar 2025, and the NSE/BSE symbol changed ZOMATO → ETERNAL on 9 Apr 2025 (ISIN unchanged). Any collector keyed on symbol loses history before April 2025. Trends for "Eternal" is useless.

**Why it happens:**
A single "break date" flag feels enough. Accounting transitions usually run over several quarters, and they affect the baseline too.

**How to avoid:**
- Config: `structural_break: {start_q, end_q, reason}`, a *range* rather than one date, and a list of affected quarters, each with `exclude_from_fit` and `flag_in_ui`.
- Apply **the same break treatment to the baseline**. Options: the baseline uses the trailing YoY from the last clean quarter pair, or it is marked "not meaningful" for those quarters. Either way, the scoreboard shows Eternal's break quarters separately and never mixes them into the headline average without saying so.
- Key every company on ISIN or a stable internal ID with a `symbol_history` table. Trends terms for Eternal: Zomato, Blinkit, District.
- Think about labelling the Eternal Q3 FY27 call "low confidence: post-break comparables limited". Showing a wide interval honestly is better than hiding it.
- Grade on **reported revenue from operations**, not the "adjusted revenue" Eternal sometimes shows. Record which number was used.

**Warning signs:**
- The Eternal baseline forecast for Q3 FY27 is above about ₹30k cr or shows triple-digit growth.
- The pooled model's coefficients move sharply when Eternal is removed.
- Collector returns empty history for symbol ETERNAL before April 2025.

**Phase to address:** P1 (break config as a range, ISIN keys), P3 (break-aware baseline + tests), P4 (fit exclusion), P6 (UI flags).

---

### Pitfall 5: Mixing revenue definitions: standalone vs consolidated, revenue vs total income, first-reported vs restated

**What goes wrong:**
- **DMART:** the update is standalone. Results give both. Consolidated adds DMart Ready / Avenue E-Commerce and other subsidiaries and runs a few percent above standalone. Mixing standalone history (easier to scrape from updates) with consolidated targets creates a fake level shift.
- **Titan:** press releases highlight "total income" and segment growth that "excludes bullion and digi-gold". Reported consolidated revenue includes **bullion/digi-gold sales**, which are lumpy and not demand-driven. Aggregator sites often show total income, which includes other income.
- **Trent:** the update is standalone. Star (Trent Hypermarket) and the Zara JV are equity-accounted, so they are not in consolidated revenue at all.
- **Nykaa:** updates give *ranges* ("late twenties"), and revenue is a mix of inventory-led and marketplace.
- **Restatements:** the prior-year comparative column in a later filing can differ from what was first reported (reclassifications, Ind AS changes, mergers). If the training target takes the denominator from a restated figure published *after* the as-of date, that is leakage. If grading uses a restated actual, the grade changes after the fact.

**Why it happens:**
"Revenue" seems like one number. Most free sources mix definitions without saying so.

**How to avoid:**
- One canonical target in config: `consolidated_revenue_from_operations` in ₹ crore. Every revenue row carries `basis` (standalone/consolidated), `line_item`, `source_filing_url`, `available_at` and `vintage` (first-reported vs restated-in-filing-X).
- **Grade against the first-reported consolidated figure** in the results filing for Q, frozen at grading time.
- For YoY targets, use the comparative column *from the same filing* (like-for-like, as the company reports it). In backtests, only use it at or after that filing's `available_at`.
- Seed CSV: hand-entered from filings, about 16 rows × 3–5 companies, one source URL per row. This is small enough to do by hand and avoids NSE scraping entirely (Pitfall 9).
- Titan: add gold price YoY as a candidate feature (Pitfall 6). Track bullion separately where it is disclosed.

**Warning signs:**
- DMART YoY shows a one-quarter jump of about 2–4% with no business reason.
- Titan revenue in the seed differs from the filing by the "other income" amount.
- A grade that changes after the next quarter's filing.

**Phase to address:** P1 (schema fields), P2 (seed CSV with provenance), P5 (grade freezes the actual + its source).

---

### Pitfall 6: Price effects disguised as demand: Titan/gold, GST pass-through, festival calendar shifts

**What goes wrong:**
- **Titan:** rupee revenue follows the gold price. Gold rose strongly through 2025–26. Titan reported jewellery growth of about 19–21% (Q1–Q2 FY26) up to about 41–46% (Q3–Q4 FY26), while buyer growth was roughly flat for three quarters. Coin sales doubled. Trends measures *interest and volume*, not *value*, so a Trends-only model badly under-predicts in a gold rally. The July 2024 customs duty cut (15% → 6%) also moved prices and demand timing in Q2 FY25.
- **GST pass-through:** revenue is net of GST. After the Sep 2025 rate cuts, DMART's realised price per unit depends on whether MRPs were cut. Volume signals and rupee revenue drift apart.
- **Festival calendar:** Navratri began 22 Sep 2025 (Q2 FY26, the same day as GST 2.0), with Diwali around 20–21 Oct 2025 (Q3 FY26). In 2026 Navratri starts in October and Diwali is in early November, both in Q3 FY27. The number of wedding-season auspicious days also changes from year to year. YoY comparisons of Q2 and Q3 pick up calendar shifts that look like demand changes.

**How to avoid:**
- Candidate features (within the 5–8 cap): **gold price YoY** for Titan (daily public rates, with `available_at`), and a **festival-days-in-quarter** count from a fixed public calendar (known in advance, so no leakage risk).
- Check feature choices against the cap before the first live lock (Pitfall 11).

**Warning signs:** Titan residuals that line up with gold price YoY. Big Q2/Q3 residuals in years when Navratri crossed a quarter boundary.

**Phase to address:** P2 (gold and festival collectors/seeds), P3 (features), P4 (residual diagnostics).

---

### Pitfall 7: Small-sample overfitting and a test set that has been looked at too many times

**What goes wrong:**
- 12–16 quarters minus 4 for the YoY lag leaves 8–12 targets per company. An expanding window that needs about 6 training rows leaves **2–6 out-of-sample points per company**. A 0.5-pp MAPE gap between the model and the baseline tells you nothing.
- **Forking paths:** trying 20 feature sets, terms or alphas and reporting the one with the best walk-forward MAPE turns the walk-forward into a training set.
- **Hidden leakage inside folds:** a `StandardScaler` or imputer fitted on all data, or hyperparameters (ridge alpha, GBM depth) picked using the whole backtest. Features picked because full-sample correlations looked good is the biggest one, and the `available_at` guard can't catch it.
- **Gradient boosting** on about 40 pooled rows memorises the data and can't extrapolate beyond the training range. That matters a lot with Oct 2026 GST at +23% YoY.
- **Per-company vs pooled:** per-company ridge with 6 features on 8 rows is close to interpolation. Pooling without per-company intercepts mixes DMART's about 15% growth level with Eternal's, so the model ends up predicting company identity.
- **80% intervals from 4–6 residuals** are meaningless. Split-conformal with n residuals needs the ⌈(n+1)·0.8⌉-th order statistic, and for n < 4 that is undefined or infinite. Reported "coverage" of 3/4 has a 95% CI of roughly 19–99%.
- **Weekly locks are not independent.** 12 correlated weekly locks per quarter scored as 12 grades inflates the apparent sample size.
- **Directional accuracy is trivial.** These are growth companies, so YoY revenue is almost always positive and "direction" is about 100% right by default.

**How to avoid:**
- **Pooled model on log YoY growth with per-company intercepts** (one-hot or demeaned), standardised *within each training fold*, all inside one sklearn `Pipeline`. Ridge with alpha fixed in advance, or picked by nested time-series CV inside the training window only.
- GBM only as a documented comparison, with strong constraints (depth ≤ 2, ≥ 5 samples per leaf). Ridge stays the headline unless GBM wins under the frozen protocol.
- Intervals: pool out-of-sample residuals across companies **in log-growth space** (scale-free). Use split-conformal with explicit n. Show "interval based on n=…" next to every interval. Report empirical coverage with a binomial (Wilson) CI.
- Define **directional accuracy as acceleration vs baseline**: did the model correctly call whether growth beats the trailing-growth assumption? Report sign-of-YoY only as a footnote, if at all.
- The scoreboard counts **official calls only**. Weekly locks feed the convergence chart and are graded, but are not counted as independent wins.
- Print train vs test error for every config. Keep a `experiments.log` (appended) of every config ever run on the backtest and show the count in the README ("we tried 7 configurations; this is #4").
- Drop the COVID-affected YoY quarters (FY21–FY22 bases) from fitting if the history reaches back that far. Flag them, as with breaks.

**Warning signs:** train MAPE far below test MAPE. Results that change a lot with ±1 quarter of initial window. Features ranked by full-sample correlation in a notebook. Intervals that look suspiciously narrow.

**Phase to address:** P3 (protocol, baseline, metric definitions, experiments log), P4 (pooled ridge pipeline, conformal intervals with n shown, GBM guardrails).

---

### Pitfall 8: A leakage test that only checks the obvious path

**What goes wrong:**
A test that asserts `max(feature.available_at) < reveal_at` passes while leakage gets in through:
- Trends normalisation (Pitfall 1) and restated revenue denominators (Pitfall 5).
- Scalers, imputers or hyperparameters fitted on the full sample (Pitfall 7).
- The baseline's "trailing YoY" taken from a quarter whose results weren't out yet at the as-of date.
- **Backfilled `available_at` values that are guesses.** A seed CSV row with no publication date defaults to `period_end`, which is too early.
- Break markers or exclusion decisions that use hindsight in the backtest.
- `datetime.now()` (naive, IST on a Windows dev box) compared with UTC timestamps.

**How to avoid:**
- **Future-perturbation invariance test** (the strongest single test): for each backtest quarter Q, randomise or corrupt every stored row with `available_at ≥ reveal_at(Q)`. Then rerun the full pipeline (features → scaler → model → baseline → interval) and assert that Q's prediction is **bit-identical**. This catches leaks you haven't thought of.
- A schema rule: `available_at` NOT NULL with no default. Seed loaders must supply it or fail. Conservative rule for unknown dates: `available_at = period_end + publication_lag_max` from per-source config.
- Ban naive datetimes: a pydantic validator rejects tz-naive values, and a lint/test greps for `datetime.now()` / `utcnow()`.
- One `as_of(t)` data-access function. Feature code can only read data through it.

**Warning signs:** the leakage test file has fewer than about 5 tests. No test builds a deliberate leak and checks that it is caught. Seed CSVs with no `available_at` column.

**Phase to address:** P1 (as_of API, schema constraints, invariance test skeleton), then extended in P3 and P4 to cover the full pipeline.

---

### Pitfall 9: Brittle data sources and terms-of-service problems

**What goes wrong:**
- **pytrends** is unofficial and its repo was **archived on 17 Apr 2025** (last release 4.9.2, Apr 2023). It hits frequent 429s, and they are much worse from cloud and GitHub Actions IPs. Google's official Trends API (alpha announced 24 Jul 2025) is application-only with no SLA. A daily GitHub Actions Trends job will fail often.
- **NSE** website: cookie and session checks, reported blocking of cloud and overseas IPs, and **Terms of Use that prohibit automated or systematic data collection**. A collector that "works locally" fails in CI, and fighting this breaks the project's own data-ethics rule.
- **GST:** no stable API. PDFs and tables on the GST portal change format, and the release channel changed in mid-2024.
- **Play Store:** there is no public "rank" for an app. Top charts are regional and categorised, and the installs bucket ("10Cr+") hardly ever changes. Scraper libraries are unofficial, and Google's terms restrict automated access. Rating or review counts are the realistic proxy.
- **Job sites:** Naukri, LinkedIn and Indeed prohibit scraping. Company career pages (often Workday, Greenhouse or Lever JSON feeds) are more defensible, but posting counts tell you about hiring, not quarterly revenue.

**How to avoid:**
- Every collector has three modes: `live` → `cached vintage` → `seed CSV`. Failures are **reported** ("Trends fetch failed 2026-11-20; using vintage from 2026-11-13") and stored in a `collector_runs` table that the UI shows. Never quietly fill gaps by interpolation.
- Trends: few terms (≤ 5 per request, one comparison anchor), exponential backoff with jitter, a 1 request per 30–60 s budget, and weekly rather than daily cadence (the data is weekly anyway). Treat the manual CSV export from trends.google.com as the documented fallback. Apply for the official API alpha but don't depend on it.
- Revenue: **hand-maintained seed from filings** (BSE/NSE PDF links per row). No NSE scraping in CI. For the 3–5 live reveals a quarter, a human entering the number with the filing URL is fine and more credible.
- Check robots.txt and ToS per source and record the outcome in `data/seed/SOURCES.md` before writing any collector.
- Forward collectors: be realistic. Data logged from Nov 2026 gives **no YoY feature until late 2027 and no fitted coefficient until about FY29**. The roadmap must not promise them as v1 model inputs. Show them as "collecting" panels only.

**Warning signs:** a CI collector job red more than 20% of the time. Collectors with no failure state. A roadmap item saying "add Play Store feature to model" before 5+ quarters of history exist.

**Phase to address:** P2 (fallback chain, collector_runs, SOURCES.md), P7 (cron behaviour on failure).

---

### Pitfall 10: The hash doesn't verify in the browser (Python and JS serialisation mismatch)

**What goes wrong:**
The "verify" button recomputes SHA-256 in JS and fails on valid records, or passes on tampered ones because both sides hash something other than the displayed values. Common causes:
- **Floats:** Python `json.dumps(1.0)` → `"1.0"`, JS `JSON.stringify(1.0)` → `"1"`. Also `1e16` vs `10000000000000000`, `-0`, and NaN (Python writes invalid `NaN`, JS writes `null`). Postgres `numeric` → Python `Decimal`, which isn't JSON-serialisable by default.
- **Key order:** Python `sort_keys=True` vs JS insertion order.
- **Whitespace:** Python's default `", "` / `": "` separators vs JS's compact output.
- **Unicode:** `ensure_ascii=True` escapes `₹` as `₹`. NFC vs NFD normalisation.
- **Timestamps:** Python `isoformat()` → `2026-11-17T04:30:00+00:00` (with microseconds when present), JS `toISOString()` → `2026-11-17T04:30:00.000Z`. Postgres `timestamptz` comes back at microsecond precision, while SQLite returns whatever string was stored. A round trip through FastAPI changes the format, so the hash changes.
- `crypto.subtle` exists only in secure contexts (HTTPS or localhost).

**How to avoid:**
- Build **one canonical payload string** at lock time and **store it verbatim** (`payload_canonical TEXT`) next to `sha256`. Hash the UTF-8 bytes of that exact string. The browser verifies `sha256(payload_canonical) == sha256`, *and* re-derives the displayed fields from the parsed payload so that what's shown is what was hashed.
- Canonical rules (written down in METHODOLOGY): RFC 8785 (JCS) style, meaning sorted keys, no whitespace and UTF-8 with no ASCII escaping. **All numbers as fixed-precision decimal strings** (`"16218.79"`, ₹ crore, 2 dp). Timestamps as strings `YYYY-MM-DDTHH:MM:SSZ` (UTC, second precision). Include a `schema_version` field.
- **Golden-vector test**: a fixtures file of 10+ payloads (including ₹, a large number, a zero, a negative growth and a midnight-IST timestamp) hashed by Python in pytest *and* by the actual frontend verify function in a JS test (vitest/node). CI fails if they differ.

**Warning signs:** verify fails only on some records. Hash computed from a dict instead of a stored string. Floats anywhere in the payload.

**Phase to address:** P5 (canonical format, stored payload, Python golden vectors), P6 (JS verify + cross-language test in CI).

---

### Pitfall 11: The clock is self-reported and append-only can be bypassed. The record isn't provable.

**What goes wrong:**
- `created_at` comes from a DB or app clock the owner controls. Anyone with DB credentials can insert a backdated row after the reveal with a hash that verifies. **A hash proves integrity, not time.**
- Git commit dates are forgeable (`GIT_COMMITTER_DATE`), and force-pushes rewrite history.
- **Append-only bypass paths:**
  - Postgres: `TRUNCATE` does **not** fire row-level DELETE triggers. `ALTER TABLE … DISABLE TRIGGER` and `SET session_replication_role = replica` skip triggers, and Supabase's `postgres` and service roles can do both. A `DROP` + recreate also gets around it.
  - SQLite: `INSERT OR REPLACE` / `REPLACE` deletes the conflicting row, and **DELETE triggers fire only if `PRAGMA recursive_triggers` is on**. Triggers can be dropped. ORM "batch" migrations (e.g. Alembic on SQLite) rebuild the table and quietly drop the triggers.
- **Supabase exposes tables through PostgREST.** If RLS is off, the public anon key (often shipped to the frontend) allows anyone to **INSERT** forged predictions.
- **Selective locking:** running `nowcast predict` several times and keeping the best-looking one, or skipping a week when the model looks off. That is cherry-picking even with a perfect hash.
- Grades written by `UPDATE` on predictions, which either fails the trigger or tempts someone to weaken it.

**How to avoid:**
- **Hash chain:** each row stores `prev_hash`, and `sha256` covers `prev_hash + payload_canonical`. Deleting, reordering or inserting a row in the middle breaks the chain, and the UI verifies the whole chain.
- **External time anchoring (layered, cheap):**
  1. After every lock, the GitHub Actions job commits the chain head (`ledger/HEAD.txt`: seq, hash, utc) to the public repo. GitHub's push event and Actions run logs are third-party timestamps. Protect the branch: no force-push.
  2. **OpenTimestamps** on the chain head (`ots stamp`; the Bitcoin attestation confirms within about hours). Commit the `.ots` proof and upgrade it in the next run. Free, with independent verification.
  3. Optional: a Wayback Machine "Save Page Now" of the public API's ledger endpoint after each official call.
  The Record shows, per prediction, "anchored at <time> ≤ reveal at <time>".
- **Lock-slot uniqueness:** `UNIQUE(company, quarter, lock_week)`. Only the cron identity writes to the ledger. Manual runs go to a `drafts` table that is never shown as a call, or every run is logged and shown.
- Triggers: BEFORE UPDATE/DELETE row triggers **and** a BEFORE TRUNCATE statement trigger on Postgres. Revoke UPDATE/DELETE/TRUNCATE from the app role and use a separate least-privilege role for writes. On SQLite, set `PRAGMA recursive_triggers = ON` in every connection, never use `OR REPLACE` on the ledger, and test that REPLACE/UPDATE/DELETE all raise.
- Startup self-check: confirm the triggers exist and are enabled (`pg_trigger.tgenabled`, `sqlite_master`) and refuse to lock if not. Test that migrations keep the triggers.
- Supabase: **RLS enabled on every table, no anon policies.** The frontend never talks to Supabase directly, only to the read-only FastAPI.
- Grades go in a separate `grades` table (append-only too), referencing `prediction_id` and storing the frozen actual and its filing URL.
- Pre-registration: before the first live lock, hash and anchor a `PREREGISTRATION.md` covering the universe, features, Trends terms, model spec, interval method, official-call rule and scoring metrics. Changing any of these later creates a new, visible model version.

**Warning signs:** the ledger has no `prev_hash`. Anchoring is manual. The app's DB role can TRUNCATE. A lock with no matching Actions run. The anon key appears in the `web/` bundle.

**Phase to address:** P1 (roles and DB layout), P5 (chain, triggers incl. TRUNCATE, recursive_triggers, slot uniqueness, grades table, self-check), P7 (anchoring in cron, branch protection, preregistration anchored before Q3 FY27 first lock).

---

### Pitfall 12: Presentation: cherry-picking, hiding baseline wins, and sounding like investment advice

**What goes wrong:**
- Backtest results shown with the same styling as live calls read as a track record. The "CALLED IT" stamp on backtest cards is misleading.
- A headline MAPE that quietly leaves out Eternal's break quarters or the COVID bases. Showing only the official call when the weekly locks were worse. Reporting the metric where the model happens to win.
- "Called it" thresholds picked after the fact (e.g. inside interval *or* within 3%, whichever looks better).
- **SEBI:** the RA Regulations (amended Dec 2024) and the 2024–25 finfluencer and educational-content rules cover anyone giving research reports or recommendations on listed securities without registration. That includes performance claims and indirect recommendations. Pure revenue nowcasts with no price, rating or trade framing are lower risk, but these all move the product toward "research report": stock price charts, "the stock may react", "beat or miss vs consensus" framing, ticker-led social posts, paid tiers, or performance claims. (Not legal advice. Confidence LOW-MEDIUM.)

**How to avoid:**
- Visibly separate **LIVE** (hash-anchored before reveal) from **BACKTEST** (reconstructed, pseudo-real-time) with labels, styling and separate scoreboards. The stamp only appears on live grades.
- Fix in advance (in preregistration): the "CALLED IT" rule (e.g. inside the 80% interval and |error| ≤ X%), the official-call rule, and the headline metric set (MAPE, acceleration hit-rate, interval coverage with n). Always show model *and* baseline side by side, per company and pooled, including quarters where the baseline wins. Show excluded quarters greyed out with the reason, not removed.
- No share prices, no price targets, no buy/sell/hold or "bullish/bearish" words, no consensus-beat framing, no monetisation. A disclaimer in the footer and on every API response (`"disclaimer"` field): research and educational only, not investment advice, not SEBI-registered, revenue estimates only. Keep the jokey line, but next to it put a plain, formal disclaimer.

**Warning signs:** a UI mock with a stock chart. The stamp on backtest cards. Scoreboard numbers that don't match the backtest table printed by the CLI.

**Phase to address:** P3 (metric definitions), P6 (labels, scoreboard, disclaimer, methodology), P7 (README limitations).

---

### Pitfall 13: Scheduling and deploy failures that silently miss a lock

**What goes wrong:**
GitHub Actions `schedule` runs in **UTC**, can be delayed (sometimes by hours at busy times such as the top of the hour) or skipped. Scheduled workflows in public repos are **disabled automatically after 60 days without repo activity**. Supabase free-tier projects pause after a period of inactivity. A missed final lock before DMART's Jan 2–3 reveal (during the New Year holiday) means no official call for the first edition.

**How to avoid:**
- Schedule locks at off-peak minutes (e.g. `17 2 * * *`). Run the final-call job **several times** in the 48 h before `earliest_plausible_reveal`. Each run is idempotent through the slot uniqueness constraint.
- A `workflow_dispatch` manual trigger plus a documented manual fallback. A heartbeat check that opens a GitHub issue if a lock is missing 24 h before a deadline. The daily collector commits (HEAD/vintage digests) keep the repo active.
- All cron expressions documented with their IST equivalent.

**Phase to address:** P7.

---

### Pitfall 14: Survivorship and selection in the company universe

**What goes wrong:**
DMART, Eternal, Titan, Trent and Nykaa are well-known growth names picked in 2026 *with hindsight*, and because their alt-data signals are strong (consumer brands with high search volume). A backtest on them overstates how well "alt-data nowcasting of Indian consumer companies" works in general. Adding stretch names after seeing which ones the model does well on makes it worse.

**How to avoid:** state the selection criteria and the hindsight problem on the methodology page. Fix the universe in preregistration. Add stretch companies only as new, pre-registered versions, and report them whether they help or hurt the aggregate.

**Phase to address:** P1 (config + rationale), P7 (README).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Overwrite Trends/GST rows on refetch | Simple upsert | Destroys point-in-time history; backtests become irreproducible | Never |
| `reveal_date` as DATE | Easy to enter | IST/UTC same-day leaks; wrong deadline handling | Never; use UTC instants |
| Hashing `json.dumps(dict)` on the fly | No extra column | Verify breaks whenever serialisation drifts | Never; store the canonical string |
| One-window Trends backfill | 1 request instead of N | Normalisation leak | Only for exploratory notebooks, never features |
| Manual revenue entry instead of a scraper | Avoids NSE ToS/blocks | A few minutes of human work per reveal | **Always acceptable** (preferred) |
| Single global ridge alpha, not tuned | No nested CV | Slightly suboptimal fit | Acceptable and preferred at this sample size if fixed in preregistration |
| Grading writes into predictions row | One table | Breaks append-only or forces trigger exceptions | Never |
| SQLite in prod "for now" | One less service | No roles, weaker triggers, no TRUNCATE guard | Only local dev |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Google Trends (pytrends/forks) | Daily fetch from CI; many terms per request; raw levels | Weekly, ≤ 5 terms, backoff, vintages, as-of windows, manual-CSV fallback |
| GST portal | Collection month = activity month; gross incl. imports and cess | Transaction month = collection month − 1; domestic gross ex-cess; regime marker 2025-09 |
| NSE/BSE filings | Scraping APIs from CI; symbol-keyed history | Hand-entered seed with filing URL; ISIN keys; symbol_history (ZOMATO→ETERNAL 2025-04-09) |
| Supabase | Anon key in frontend, RLS off; relying on triggers vs superuser | RLS on, no anon policies, least-privilege writer role, TRUNCATE trigger, startup trigger check |
| GitHub Actions | Assuming exact cron time; repo-inactivity disable | Redundant runs, idempotent slots, heartbeat issue, keep-alive commits |
| Web Crypto | Using on http non-localhost; hashing re-serialised JSON | HTTPS (Vercel); hash stored canonical string bytes via TextEncoder |
| OpenTimestamps | Stamping and never upgrading the `.ots` | Upgrade pending proofs in next cron run; commit upgraded proof |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| As-of-windowed Trends backfill | 429 storms; multi-hour jobs | Cache per (term, window_end); backfill once locally, commit vintages to seed | ~10 terms × 16 as-of dates = 160+ requests |
| Re-running full walk-forward on every API call | Slow API | Precompute backtest tables in P3/P4; API reads results only | Immediately on serverless cold starts |
| Free-tier sleep (Supabase/host for FastAPI) | First request times out on results day | Keep-alive from cron; static JSON snapshot fallback for the frontend | After ~days of inactivity |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Ledger writable via Supabase REST (RLS off) | Anyone inserts forged predictions | RLS on; only FastAPI (read) and cron writer role (insert) |
| DB credentials in Actions logs or `web/` env | Ledger forgery, history wipe | GitHub encrypted secrets; mask; never `NEXT_PUBLIC_` for DB |
| Writer role has TRUNCATE/ALTER | Bypasses row triggers | Revoke; separate migration role used only manually |
| Force-push allowed on main | Rewrites anchor history | Branch protection: no force-push, no deletion |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Backtest cards styled like live calls | Reader believes a track record exists | LIVE vs BACKTEST labels, separate scoreboard, no stamp on backtests |
| Interval shown without n | False precision | "80% interval · based on 9 out-of-sample residuals" |
| Countdown to an expected reveal date | Implies a known date; lock may miss early disclosure | Countdown to *lock deadline* (earliest plausible reveal) |
| Verify button that only says "OK" | Not convincing to a sceptic | Show the canonical string, the computed hash, prev_hash link and the anchor proof |
| Hiding source failures | Undermines honesty brand | "Data health" strip with last successful fetch per source |

## "Looks Done But Isn't" Checklist

- [ ] **Leakage guard:** has a future-perturbation invariance test over the *full pipeline*, not just a filter test. Compares UTC instants, not dates.
- [ ] **Trends collector:** stores vintages with `fetched_at`, drops `isPartial`, uses as-of windows in backtests.
- [ ] **GST features:** a transaction-month attribution test exists; the 2025-09 regime is handled and documented.
- [ ] **Reveal data:** `business_update_at` filled for every historical DMART/Titan/Trent/Nykaa quarter, with a filing URL.
- [ ] **Eternal:** break is a quarter *range*; the baseline is break-aware; symbol history covers ZOMATO.
- [ ] **Revenue seed:** every row has basis, line item, filing URL and `available_at`. Grade uses first-reported consolidated revenue from operations.
- [ ] **Intervals:** n shown; coverage reported with a binomial CI.
- [ ] **Ledger:** hash chain, stored canonical payload, Python↔JS golden vectors in CI, TRUNCATE trigger, `recursive_triggers=ON`, slot uniqueness, trigger self-check, RLS on.
- [ ] **Anchoring:** chain head committed + OTS-stamped by cron after each lock; preregistration anchored before the first Q3 FY27 lock.
- [ ] **Cron:** final-call job runs redundantly before DMART's `earliest_plausible_reveal` (about Jan 1, 2027 IST); a heartbeat alert exists.
- [ ] **UI:** no stock prices or buy/sell language; disclaimer in footer and API; baseline wins shown.
- [ ] **Forward collectors:** visibly "collecting", not feeding the model.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Discovered a leak after publishing backtest | MEDIUM | Fix, rerun, publish both old and new tables with a changelog entry. Never silently replace |
| Missed a weekly lock | LOW | Leave the gap; show "no lock (cron failure)" in The Record |
| Missed the official call | MEDIUM | Last weekly lock becomes official only if that rule was pre-registered; otherwise mark "no official call" |
| Hash verify mismatch on old records | HIGH if payload not stored | If canonical string stored: fix JS. If not: records can't be verified, so say so publicly and add a schema version |
| Wrong reveal (lock after disclosure) | MEDIUM | Mark the prediction "invalid: locked after reveal", keep it in the ledger, exclude it from scoring, explain |
| Source blocked mid-quarter | LOW | Fall back to seed or manual CSV; record in collector_runs; show in data health strip |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 Trends point-in-time | P1, P2, P3 | Vintage table populated; repeat-fetch noise report; no level features |
| 2 GST month and regime | P1, P2, P3 | Unit test: Q3 uses Nov/Dec/Jan collections ∩ available_at; regime flag visible |
| 3 Reveal instant | P1, P2, P5, P7 | Same-day IST/UTC test; `business_update_at` non-null for update-issuing companies |
| 4 Eternal break and baseline | P1, P3, P4, P6 | Baseline Eternal forecast sane; break quarters separate in scoreboard |
| 5 Revenue definitions | P1, P2, P5 | Seed provenance columns; grade freezes first-reported figure |
| 6 Price and calendar effects | P2, P3, P4 | Titan residual vs gold YoY check |
| 7 Small-sample overfitting | P3, P4 | Pipeline-in-fold; experiments.log; intervals show n; acceleration metric |
| 8 Weak leakage test | P1 → P4 | Invariance test passes; deliberate-leak test fails as expected |
| 9 Source fragility and ToS | P2, P7 | SOURCES.md; collector_runs; CI red rate < 20% |
| 10 Hash canonicalisation | P5, P6 | Cross-language golden-vector CI job |
| 11 Clock and append-only | P1, P5, P7 | Bypass tests (TRUNCATE, REPLACE, DISABLE TRIGGER); anchor present per lock |
| 12 Presentation and SEBI | P3, P6, P7 | UI review against checklist; disclaimer in API |
| 13 Cron misses | P7 | Heartbeat alert fires in a dry run |
| 14 Survivorship | P1, P7 | Preregistered universe + methodology text |

## Sources

Confidence: MEDIUM = cross-checked across ≥2 independent sources; LOW = single or secondary source; HIGH = official docs or well-known documented behaviour.
- Google Trends sampling and inconsistency: [EDML20 paper](https://imada.sdu.dk/Research/EDML/2020/EDML20_paper_5.pdf), [gtrendr variance notes](https://gtrendr.readthedocs.io/en/latest/google-variance/), [Supermetrics discrepancies doc](https://docs.supermetrics.com/docs/about-discrepancies-in-google-trends-data), [Restoring the Forecasting Power of Google Trends (arXiv 2025)](https://arxiv.org/html/2504.07032v1), [UPV simulation study](https://riunet.upv.es/bitstream/10251/189564/1/CebrianDomenech%20-%20Simulating%20the%20inconsistencies%20of%20Google%20Trends%20data.pdf): MEDIUM
- pytrends archived / official Trends API alpha: [DEV: pytrends is dead](https://dev.to/esteban_ortega/pytrends-is-dead-heres-how-to-get-google-trends-data-in-2026-1a18), [ScrapeBadger](https://scrapebadger.com/blog/does-google-trends-have-an-api-what-to-use-in-2026): MEDIUM
- GST 2.0 and collections: [Business Standard: first full month of GST 2.0](https://www.business-standard.com/amp/economy/news/tax-turbulence-revenues-take-a-hit-in-first-full-month-of-gst-2-0-125120101323_1.html), [IndBiz Oct 2025](https://indbiz.gov.in/gst-collections-up-4-6-in-october-to-%e2%82%b91-96-lakh-crore-despite-recent-rate-cuts), [Upstox Oct 2026 +22.9%](https://upstox.com/news/business-news/tax/gst-mop-up-rises-22-9-to-rs-2-31-lakh-crore-in-october-second-highest-ever/article-202786/), [Deccan Herald Oct 2026](https://www.deccanherald.com/business/gst-mop-up-grows-23-to-over-rs-231-lakh-crore-in-october-2026-4203190): MEDIUM
- GST press release discontinuation: [ThePrint](https://theprint.in/economy/embarrassment-of-riches-govt-halts-monthly-gst-releases-as-high-collections-creating-resentment/2156852), [Business Today](https://www.businesstoday.in/latest/economy/story/eyebrows-raised-after-centre-stops-release-of-monthly-gst-data-435599-2024-07-03), [Rajya Sabha answer](https://rsdebate.nic.in/bitstream/123456789/750655/1/PQ_265_06082024_U1668_p318_p318.pdf): MEDIUM
- Compensation cess end: [Informist](https://informistmedia.com/MoneyWire/41781/Excise-Duty-Govt-levies-excise-duty-on-cigarettes-from-Feb-1-ends-GST-compensation-cess), [Business Standard](https://www.business-standard.com/industry/news/gst-tobacco-cess-excise-revenue-sin-products-126010100596_1.html): MEDIUM
- Eternal / Blinkit: [Inc42 Blinkit Q2 FY26](https://inc42.com/buzz/blinkit-q2-fy26-adjusted-ebitda-loss-declines-4-qoq-to-inr-156-cr/), [Indian Startup News](https://indianstartupnews.com/news/eternals-revenue-jumps-183-to-rs-13590-crore-in-q2-fy26-profit-falls-63-to-rs-65-crore-10572805), [Inc42 Hyperpure](https://inc42.com/?p=535421), [YourStory](https://yourstory.com/2025/10/blinkit-weighs-long-term-growth-heavy-investments-eternal-q2-fy26): MEDIUM (verify exact figures against the shareholder letter)
- Rename/symbol: [Angel One](https://www.angelone.in/news/share-market/zomato-to-trade-as-eternal-stock-exchange-from-april-9-2025), [NSE intimation](https://nsearchives.nseindia.com/corporate/ZOMATO_20032025184851_ZomatoNamechnageintimationsIGNED.pdf): MEDIUM-HIGH
- DMART update timing: [BSE filing PDF](https://bseindia.com/xml-data/corpfiling/AttachHis/546875a8-96cf-42ce-935d-44131e500d4b.pdf), [Bajaj Broking Q2 FY26](https://www.bajajbroking.in/share-market-news/dmart-q2-fy2025-26-results-revenue-at-rs-16218-79-crore): MEDIUM
- Titan updates / gold: [GJEPC Q1 FY26](https://gjepc.org/solitaire/titans-jewellery-division-posts-19-growth-in-q1-fy26-international-business-hits-profit-milestone/), [FPJ Q4 FY26](https://www.freepressjournal.in/business/titan-reports-46-revenue-growth-in-q4-fy26-jewellery-division-shines-amid-high-gold-prices), [Tata World Q3 FY25 customs duty](https://www.tataworld.com/news/openinside/titan-q3-fy2024-25): MEDIUM
- Trent / Nykaa updates: [Retail Insight Network](https://www.retail-insight-network.com/newsletters/trent-q2-standalone-revenue-rises-23), [Kotak Neo Trent Q1 FY27](https://www.kotakneo.com/news/stocks/trent-shares-fall-q1-business-update-revenue-growth-july-2026/), [Kotak Neo Nykaa Q2 FY27](https://www.kotakneo.com/news/stocks/nykaa-q2-fy-2026-27-results-update-late-20s-revenue-growth-fashion-business-accelerates/): MEDIUM
- NSE access/ToS: [NSE Terms of Use](https://www.nseindia.com/nse-terms-of-use), [Unofficed forum on cloud blocking](https://forum.unofficed.com/t/update-nsepython-not-working-in-aws-google-cloud-and-webservers/670): MEDIUM (ToS) / LOW (blocking specifics)
- SEBI: [Taxmann on finfluencer rules](https://www.taxmann.com/post/blog/analysis-sebis-new-regulations-on-finfluencers-protecting-investors-from-unregistered-advisors/), [Legal500](https://www.legal500.com/developments/thought-leadership/securities-law-update-sebi-imposes-restrictions-on-intermediaries-and-finfluencers/): LOW-MEDIUM; not legal advice; check primary SEBI circulars
- SQLite REPLACE/trigger behaviour: [SQLite ON CONFLICT docs](https://sqlite.org/lang_conflict.html): HIGH. Postgres TRUNCATE not firing row triggers, `session_replication_role`: PostgreSQL docs (CREATE TRIGGER): HIGH (known behaviour, not re-fetched this session)
- OpenTimestamps: [opentimestamps.org](https://opentimestamps.org/), [Peter Todd: git integration](https://petertodd.org/2016/opentimestamps-git-integration), [git-ots](https://pypi.org/project/git-ots/): MEDIUM
- JS vs Python number/JSON serialisation, RFC 8785 JCS, Web Crypto secure-context requirement, GitHub Actions schedule delays / 60-day inactivity disable: documented platform behaviour (training knowledge, not re-fetched): MEDIUM-HIGH. Festival dates for 2026 (Navratri in Oct, Diwali early Nov): MEDIUM, verify against a published calendar before encoding.

---
*Pitfalls research for: Indian consumer-company alt-data revenue nowcasting with a public hash-locked ledger*
*Researched: 2026-11-17*
