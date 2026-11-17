# Feature Research

**Domain:** Alternative-data revenue nowcaster with a public, hash-verified prediction ledger (Indian listed consumer companies)
**Researched:** 2026-11-17
**Confidence:** MEDIUM overall. Forecast-evaluation and point-in-time methodology are HIGH (long-established practice: ALFRED vintages, GDPNow, Metaculus track records). Competitor product details are MEDIUM/LOW (mostly vendor marketing). India-specific calendar and regulatory points are MEDIUM.

---

## How to read this document

The product has four layers. Each one is judged separately by a quant or buy-side reviewer, and a weakness in a lower layer cancels out polish in a higher one:

```
Data layer (point-in-time)  ->  Model/backtest layer  ->  Ledger  ->  Public frontend
"what did you know, when"       "is it better than naive"  "can I check it"  "can I read it in 30s"
```

Comparable products, and what each one teaches:

| Product | What it is | Lesson for CALLED IT. |
|---------|-----------|------------------------|
| **Estimize** | Crowdsourced EPS/revenue estimates, compared with Wall Street consensus | Selling point is accuracy *relative to a benchmark*, with a per-estimator accuracy score. Its claims are mostly self-reported, and reviewers treat them that way. |
| **YipitData / M Science** | Paid KPI and revenue estimates built from transaction/web panels | Says it calibrates against reported results, publishes methodology, and "flags and explains misses". The buy-side expects misses to be explained. |
| **Thinknum** | Scraped datasets (job listings, app ranks, pricing) shown as daily time series | Raw signal history with daily capture dates. This is the "forward-collected" layer the project is building. |
| **Atlanta Fed GDPNow** | Public macro nowcast, updated as data arrives | The reference design: a running estimate, a convergence chart, a contribution breakdown per update, a full downloadable track record, and "no judgment used to adjust". This is the closest model for the weekly-lock design. |
| **ALFRED (St. Louis Fed)** | Vintage archive of economic data | The standard for point-in-time data: every revision kept, users model "with data that was actually available". Where a release date can't be found, ALFRED falls back to first-seen date. Copy that fallback rule and disclose it. |
| **Metaculus / Manifold track-record pages** | Public forecasting scoreboards | Calibration plots, scores against naive references (a constant 50% gives Brier 0.25), filters by question type. Scores are always shown relative to a naive reference. |
| **OpenTimestamps** | Free Bitcoin-anchored timestamp proofs for hashes | A hash proves *content*, not *time*. An independent anchor proves the hash existed by a given time. |

**Key finding:** every credible comparable reports skill *relative to a naive or consensus benchmark* and keeps the full record, misses included. None of the free ones also proves *when* each forecast was made. GDPNow and Metaculus rely on institutional trust, and Estimize and Yipit rely on their own word. If CALLED IT. combines GDPNow-style convergence, Metaculus-style relative scoring and cryptographic proof of time, it has a real niche. Without external time anchoring, the "provably honest" claim does not hold up.

---

## Feature Landscape

### Table Stakes (a quant reviewer dismisses the project without these)

#### A. Data / feature layer

| # | Feature | Why Expected | Complexity | Notes |
|---|---------|--------------|------------|-------|
| D1 | **Every row is bitemporal:** `period_date`, `available_at`, `retrieved_at`, `source`, `source_ref` (URL/filename), `provenance` (`live_fetch` / `seed_csv` / `forward_collected`) | Point-in-time is the central claim. `available_at` alone can't separate "published then" from "we downloaded it later". | MEDIUM | `retrieved_at` is set by the system and can't be passed in by the caller. Store UTC; display IST. |
| D2 | **Never overwrite. Each fetch is a new vintage.** | ALFRED practice. Sources revise (GST corrections, restated revenue, Google Trends resampling). Overwriting quietly brings later knowledge into old rows. | MEDIUM | Unique key `(series, period_date, vintage/retrieved_at)`. The "latest vintage as-of t" view is a query, not a mutation. |
| D3 | **One gateway function, `as_of(series, t)`, used for all feature reads** | One place to enforce `available_at < t`. Leakage tests target this function. | LOW | Model code must not be able to query raw tables. Enforce with module boundaries plus a test that greps for direct table access. |
| D4 | **`available_at` rules per source, documented and conservative** | Reviewers check the lag assumptions first. | LOW | GST: press release/portal publication timestamp (not month-end). Trends: week-end + 1 day at minimum. Revenue: exchange filing timestamp. If the date is unknown, use a documented conservative lag and mark the row `available_at_estimated=true` (ALFRED does the same). |
| D5 | **Reveal calendar table:** per company and quarter, `business_update_at`, `results_at`, `reveal_at = min(...)`, and a status of `expected` or `confirmed` | Locks and features are both measured against it. The reveal decides whether a call counts. | MEDIUM | **Store a timestamp, not a date.** DMART filing at 18:30 IST means a 10:00 lock the same day is valid. Exchange (NSE/BSE) dissemination time is the authoritative timestamp. Business-update dates are not announced in advance, so future reveals are always `expected`. |
| D6 | **Leakage test suite** (already in PROJECT.md as the most important test) | Credibility. | MEDIUM | Tests: (a) a synthetic future row injected must never appear in features; (b) for every backtest prediction, max(`available_at`) of the features used is < `reveal_at`; (c) every weekly backtest nowcast at date w uses only rows with `available_at < w`; (d) the Trends normalisation-window test (D7). Run in CI and show a badge on the site. |
| D7 | **Google Trends vintage honesty** | Trends is normalised to 0–100 *over the requested window*, and values change between downloads because of sampling. A series downloaded today for 2022–2026 contains future information (the max is set by later weeks). This is a subtle lookahead that a sharp reviewer will catch. | MEDIUM | For the backtest, request each quarter's Trends with `timeframe` ending at that quarter's as-of date and store it as a vintage labelled `reconstructed`. From now on, snapshot every weekly pull as `captured_live`. Use YoY *ratios within one pull*, never across pulls. State in the methodology that reconstructed Trends vintages are not exactly what was visible at the time, because of resampling. |
| D8 | **Provenance shown to users:** live fetch, seed CSV, forward-collected | Data-honesty constraint. Silent fallback to CSV reads as faked data. | LOW | Each seed CSV has a sidecar with download instructions and date. Collector failures go to a `source_health` table. |
| D9 | **Structural-break markers on targets *and features*** | Eternal/Blinkit is already flagged. **GST 2.0 rate rationalisation (effective 22 Sep 2025) is a feature-side break:** GST collection YoY from Oct 2025 to Sep 2026 compares post-cut with pre-cut rates (collections fell while consumption rose). Without a marker, the GST features carry the wrong sign for exactly the most recent training quarters. | MEDIUM | Config-driven `breaks: [{series, date, reason}]`. Options: exclude straddling quarters, add a dummy, or switch to a rate-neutral proxy. For Q3 FY27 the GST YoY is post-cut vs post-cut and therefore clean again. Say so on the site. |
| D10 | **Feature snapshot stored with every prediction** | "What did the model see?" has to be answerable after the fact, forever. | LOW | Store the feature vector plus the `(series, period_date, vintage)` references, and include its hash in the ledger payload (L3). |

#### B. Modelling / backtest layer

| # | Feature | Why Expected | Complexity | Notes |
|---|---------|--------------|------------|-------|
| M1 | **Naive baseline built first, reported next to every number** | Quarterly revenue of large consumer companies is very predictable. Naive seasonal models often land at single-digit MAPE. A MAPE with no baseline next to it tells the reader nothing. | LOW | Primary: SQLY × (1 + trailing YoY). Also show plain seasonal naive (SQLY × 1) as a sanity floor. It costs nothing and protects against a baseline that has been accidentally weakened. |
| M2 | **Walk-forward with an expanding window only, and a stated minimum training size** | Random splits leak the future. Reviewers check this second, after D4. | LOW | Print the fold table: train quarters, test quarter, as-of timestamp. |
| M3 | **Relative skill metrics, not just MAPE** | This is how GDPNow, Metaculus and Estimize all present results. | LOW | Per company and pooled: MAPE (model and baseline), **skill = 1 − MAE_model / MAE_baseline**, head-to-head win rate, and **n test quarters printed next to every metric**. |
| M4 | **Directional accuracy, defined so it isn't trivial** | "Direction of YoY growth" is close to 100% for growing companies and meaningless. A reviewer who sees "92% directional accuracy" with no definition stops reading. | LOW | Define it as **direction of the surprise relative to the baseline**: `sign(pred − baseline) == sign(actual − baseline)`. Optionally add the sign of YoY growth *acceleration* compared with last quarter. Publish the definition next to the number. |
| M5 | **80% interval plus empirical coverage, with uncertainty** | A point estimate without an interval looks amateur. An interval that is never checked is decoration. | MEDIUM | With 12–16 quarters, use empirical quantiles of walk-forward residuals (split-conformal style), not ridge's parametric SE. Report "inside interval: 9/12 (75%), target 80%" with a binomial CI, and say plainly that n is too small to call it well-calibrated or not. |
| M6 | **Train-vs-test error printed** | Shows overfitting. Already in PROJECT.md. | LOW | If train error is much lower than test error, show a warning in the backtest output. |
| M7 | **Model version ID stored on every prediction** | Every graded number must trace back to exact code. | LOW | `model_version = hash(git SHA + model config + feature list + training cutoff)`. Keep a `models` registry table that is also append-only. |
| M8 | **Model frozen before the quarter's first live lock** | Swapping models mid-quarter, or switching to whichever looks best, is a form of p-hacking. | LOW | Pre-register: "Q3 FY27 live model = v1.2, committed at <hash>." Any later version runs as a *challenger* that is also locked and graded, never as a quiet replacement. |
| M9 | **Weekly backtest nowcasts too, not only final calls** | Otherwise the live convergence chart has nothing historical to compare against. | MEDIUM | This is cheap once D3 exists: run `as_of(week_t)` for each week of each backtest quarter. It also gives the most honest test of the weekly cadence. |
| M10 | **Reproducible backtest: one command, same table** | "Run it yourself" is the strongest trust signal for a portfolio piece. | LOW | Pin dependencies with `uv.lock`, use fixed seeds, and work offline from stored vintages and seed CSVs. Print a hash of the results table in the README so a re-run can be compared. |

#### C. Ledger

| # | Feature | Why Expected | Complexity | Notes |
|---|---------|--------------|------------|-------|
| L1 | **Append-only, enforced in code and by a DB trigger on Postgres and SQLite** | Already decided. | MEDIUM | Block UPDATE and DELETE. Note that a DB owner can drop a trigger, so the trigger protects against accidents and does not *prove* anything to outsiders. L4 provides the proof. |
| L2 | **Canonical serialisation spec, published** | The hash is only verifiable if a third party can rebuild the exact bytes. Floating-point and key-order differences between Python and JS are the usual cause of a broken "verify" button. | MEDIUM | JSON with sorted keys, no whitespace, UTF-8. **Numbers encoded as decimal strings** (e.g. `"12345.60"` ₹ crore, 2 dp). Timestamps as RFC 3339 UTC with `Z`. Include a `schema_version` field. Golden test vectors shared by the pytest and JS test suites. |
| L3 | **Payload contents** | Everything needed to grade and audit without trusting the DB. | LOW | `seq`, `prev_hash`, `company`, `fiscal_quarter`, `lock_type` (`weekly` / `official`), `point`, `lo80`, `hi80`, `baseline_point`, `model_version`, `feature_snapshot_hash`, `created_at`, `expected_reveal_at`, `schema_version`. |
| L4 | **Proof of time independent of the operator** | **This is the gap reviewers will push on: "You control the database and the clock, so what stops you writing a row in February with a December `created_at`?"** A SHA-256 hash proves the content hasn't changed. It says nothing about when the row was written. | MEDIUM | Do at least two of the following for every lock: (a) **OpenTimestamps** proof (free, Bitcoin-anchored, verifiable without trusting the operator; store the `.ots` file and upgrade it after confirmation); (b) commit the ledger export to the public repo *and* save the ledger page to the Internet Archive (the Wayback snapshot time is set by their server); (c) post the hash publicly somewhere with a server-set timestamp. Note that git commit dates can be set by the author and prove nothing on their own. |
| L5 | **Hash chain (`prev_hash`)** | Detects deleted or reordered rows. Without it, a row can be quietly dropped. | LOW | Each payload includes the previous row's hash. Optionally publish a Merkle or chain head per edition. |
| L6 | **Grades in a separate append-only table that references the prediction hash** | Grading must not alter the prediction row. | LOW | `actual`, `actual_source` (filing URL), `actual_filed_at`, `error_pct`, `inside_80`, `beat_baseline`, `grader_version`. |
| L7 | **Grading rules published before the first live lock** | Rules written after outcomes are known invite suspicion. | LOW | Basis: consolidated revenue from operations, **as first reported** (later restatements are noted but don't change the grade). Policy for standalone business updates (they set the timing; grading waits for the consolidated figure). Rounding. Hash the rules document into the first ledger row. |
| L8 | **Locks after the reveal are automatically void** | Reveal dates for business updates aren't known in advance. If DMART files earlier than expected, a lock made after the filing must not count. | LOW | At grading time: `created_at >= reveal_at` → status `VOID (post-reveal)`, still shown publicly. "Official call" means the last *valid* lock. |
| L9 | **Missed locks shown, never backfilled** | If the cron fails one week, a gap is honest and a backfilled lock is fraud. | LOW | Expected lock schedule per quarter. The UI shows "Week 6: no lock (collector failure, see log)". |
| L10 | **Corrections are new rows** | Errors will happen (wrong unit, wrong basis). | LOW | `annotation` / `supersedes` row type that references the original hash. The original stays visible. |
| L11 | **Full public export plus a standalone verifier script** | The verify button runs on the site that makes the claim, so it can't be the only check. | LOW | `ledger.jsonl` download plus a roughly 30-line `verify_ledger.py` (stdlib only) that checks every hash, the chain, and the OTS proofs. |

#### D. Public frontend

| # | Feature | Why Expected | Complexity | Notes |
|---|---------|--------------|------------|-------|
| F1 | **Front page with live calls:** per company, the current point and 80% interval, the baseline, the time of the last lock, its hash prefix, and a countdown to the expected reveal | This is the product. | MEDIUM | The countdown says "expected ~2 Jan (unconfirmed)" until the date is confirmed. Never show false precision about a reveal time. |
| F2 | **LIVE and BACKTEST labelled everywhere and never mixed into one headline number** | Mixing them is the most common way public track records mislead, and reviewers know it. | LOW | Separate scoreboard tabs. The headline scoreboard is LIVE only, even when that means n = 0 for weeks ("No live results yet. First reveal in 46 days."). |
| F3 | **The Record:** archive of every lock, including weekly, void and missed ones | The "we printed all 3" promise. | MEDIUM | Each card shows the hash, a verify button, the grade, a link to the source filing and the OTS status. Filters by company, quarter and lock type. |
| F4 | **Scoreboard against the baseline** | Core value. | LOW | MAE each, skill score, wins and losses, n, and coverage. If the baseline is winning, show that as the top headline. |
| F5 | **Methodology page** | Reviewers read this before anything else. | LOW (writing-heavy) | Lookahead bias in plain English, `available_at` rules (D4), Trends normalisation caveat (D7), structural breaks (D9), baseline definition, metric definitions (M4), grading rules (L7), how to verify (L2/L4/L11), limitations including small n. |
| F6 | **Disclaimer** | Compliance, and it keeps the project clearly separate from research-analyst activity under SEBI rules. | LOW | "Research and education only. No recommendations, price targets or trading signals." In the footer and on every call card. |
| F7 | **Data freshness and source status** | A stale site that looks live destroys trust. | LOW | "Collectors last ran: 2026-11-17 06:00 IST. GST: OK. Trends: OK. Play Store: forward-collected, day 1 of history." |
| F8 | **Fast and static-first, readable on mobile** | People share these links on phones. | LOW | ISR or static generation from the read API. Nothing on the site needs real-time data. |

### Differentiators (what makes this stand out as a portfolio piece)

| # | Feature | Value Proposition | Complexity | Notes |
|---|---------|-------------------|------------|-------|
| X1 | **Convergence chart per call (GDPNow-style)** | Shows the weekly locks with interval bands narrowing towards the reveal, the baseline as a flat line, and the actual figure stamped on reveal day. It shows the nowcasting idea in one picture. | MEDIUM | Needs M9 for backtest examples and L3 weekly locks for live ones. |
| X2 | **"What moved the nowcast" contribution breakdown per weekly lock** | GDPNow's most-cited feature. For example: "+0.9 pp this week: Maharashtra GST (Oct print, published 1 Nov)." It turns a black box into a story. | MEDIUM | Ridge makes this exact (coefficient × Δfeature). For gradient boosting, use SHAP deltas or stick to ridge for this panel. |
| X3 | **"What the model saw" panel** | Every feature value behind a call, each with `available_at` and vintage. It makes the absence of lookahead visible instead of something the reader has to take on trust. | LOW | Read from D10 snapshots. |
| X4 | **Client-side verify plus OTS status badge** | Recomputes SHA-256 in the browser (WebCrypto) from the displayed canonical payload, and shows "anchored in Bitcoin block N" when the proof is upgraded. Reviewers can try it themselves. | MEDIUM | Depends on L2 golden vectors. Show the exact bytes being hashed in a collapsible panel. |
| X5 | **Weekly backtest convergence** | Answers "do the weekly updates actually improve accuracy as the quarter goes on?" with an error-by-weeks-before-reveal curve. Few amateur projects test their own cadence. | MEDIUM | Builds on M9. If error doesn't fall as the reveal approaches, say so. That is a real finding. |
| X6 | **Challenger models graded side by side** | Model v2 runs as a locked challenger next to the frozen v1 and both are graded. Shows model iteration without changing the record. | LOW (given M7/M8) | Scoreboard rows: Baseline / v1 (official) / v2 (challenger). |
| X7 | **Honesty microcopy and a "wrong count"** | "This model has been wrong 3 times. We printed all 3." Gives the project a recognisable voice. | LOW | Must be computed from the grades table, never hard-coded. |
| X8 | **Public CI badge for the leakage tests** | Shows leakage protection as a running test, not a claim. | LOW | Link to the GitHub Actions run. |
| X9 | **Vintage diff view for Google Trends** | Shows how much Trends values move between pulls, which supports the D7 caveat and shows understanding of the data. | MEDIUM | Nice-to-have. Data comes from D2 for free. |
| X10 | **Interval score / pinball loss alongside coverage** | Rewards narrow and correct intervals together. Shows awareness of proper scoring rules (the forecasting-community norm). | LOW | One extra column. Keep MAPE as the main number for readability. |

### Anti-Features (deliberately NOT built)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Buy/sell signals, price targets, "implied stock move", "beat/miss vs Street" trade framing | It's what an investor audience "wants" | Breaks the compliance constraint and the SEBI research-analyst boundary, and turns a measurement project into a tipping service | Report revenue error only. The disclaimer appears everywhere. |
| **Scraped sell-side consensus** to compare with "the Street" | The buy-side cares about consensus, not naive baselines | No free licensed source. Scraping aggregators breaches ToS (a data-ethics constraint). A comparison that silently relies on stale consensus is misleading | Naive baseline is the official benchmark. A possible v2 adds *manually entered* consensus figures from cited press articles, clearly labelled. |
| One blended accuracy number (backtest + live) | Bigger n, better-looking headline | The standard way track records mislead. A reviewer who spots it stops trusting everything else | F2: always separate. |
| Re-scoring past live calls with a newer model ("v3 would have called it") | Makes the record look better | Hindsight. Breaks the core value | X6 challengers only score going forward. Backtests of new models are labelled BACKTEST. |
| Editing or deleting predictions, including "fixing typos" | Errors happen | Kills the ledger's whole claim | L10 annotation rows. |
| Backfilling missed weekly locks | Tidy convergence chart | Fabrication | L9: show the gap. |
| Large feature sets, deep nets, LLM sentiment features | Looks sophisticated | 12–16 quarters can't support them. A reviewer reads complexity on tiny n as overfitting | 5–8 features, ridge first, with the reasoning written in the methodology page. |
| Crowd predictions / user accounts (Estimize-style) | Engagement | Different product. Adds auth, moderation and abuse risk, and dilutes the "one model, one record" story | None for v1. The share link to a call card is the social feature. |
| Blockchain token, smart contract or own chain for the ledger | "Immutable" buzz | Overkill and costly, and reads as a gimmick to finance reviewers | OpenTimestamps gives the same time-proof property for free (L4). |
| Real-time or intraday updating, live websockets | Feels "live" | The data is weekly or monthly. Real-time updates would be fake freshness | Static or ISR pages, weekly locks, F7 freshness indicator. |
| Adding or removing companies without a record | Drop the ones the model does badly on | Survivorship and cherry-picking, which reviewers will suspect | Universe changes are written to the ledger as `universe_change` rows with a reason. Eternal stays, flagged. |
| Interactive "tune the model" sliders or what-if UI | Engagement | Invites garden-of-forking-paths criticism. Nothing tuned on the site is graded | Static methodology plus the reproducible CLI (M10). |
| False precision (₹ 12,345.67 cr headline, reveal countdown to the second for unconfirmed dates) | Looks exact | Signals naivety about the uncertainty | Store full precision. Display ₹ cr rounded with the interval. "Expected ~date" until confirmed. |
| Synthetic or "filled" data when a source fails | Keeps the pipeline green | Breaks the data-honesty constraint | Seed CSV fallback, labelled (D8). Otherwise the feature is missing and that is reported. |

---

## What makes a quant/buy-side reviewer trust it, or dismiss it

### Trust signals (ordered by how quickly a reviewer checks them)

1. **Baseline next to every number**, and the site openly reports when the baseline wins (M1, M3, F4).
2. **LIVE separated from BACKTEST**, n printed everywhere, and live n honestly small (F2).
3. **Point-in-time you can inspect**: `available_at` on every feature row, a "what the model saw" panel, and a leakage-test CI badge (D1, D6, X3, X8).
4. **Time proof that doesn't depend on the operator**: OTS-anchored hashes, a public export and a standalone verifier (L4, L11).
5. **Rules committed before outcomes**: grading rules, reveal-date definition and the frozen model version are all hashed into the ledger before the first reveal (L7, M8).
6. **Failures visible**: void locks, missed locks, source outages and the wrong-count (L8, L9, F7, X7).
7. **Known traps named**: Trends normalisation lookahead, GST 2.0 break, Blinkit break, small-n coverage (D7, D9, M5).
8. **Restraint**: few features, a simple model, and a written explanation of why.
9. **Reproducibility**: one command regenerates the backtest table, with a hash to compare against (M10).

### Dismissal triggers (any one of these ends the review)

| Trigger | Why it's fatal | Prevented by |
|---------|----------------|--------------|
| Excellent backtest (e.g. MAPE ~1%, R² 0.95) on 12 quarters with no baseline | Reads as overfitting or leakage | M1, M3, M6 |
| Trends pulled once today and used across the whole backtest | Normalisation-window lookahead | D7 |
| Features dated to the results date when DMART/Titan business updates came earlier | Leakage through the reveal definition | D5, D6 |
| "SHA-256 verified" with no independent time anchor | "You control the clock" | L4 |
| Undefined or trivial "directional accuracy" | Shows the author doesn't understand the metric | M4 |
| Backtest and live merged into one accuracy number | Classic track-record inflation | F2 |
| Model or universe changed mid-stream with no record | Forking paths / survivorship | M8, X6, universe rows |
| Buy/sell language, "alpha", "AI-powered" marketing | Compliance problem and lack of seriousness | F6, anti-features |
| Verify button fails on a card | The core claim visibly breaks | L2 golden vectors tested in CI on both Python and JS |

---

## Feature Dependencies

```
D1 bitemporal rows
  └──> D2 vintages ──> D7 Trends vintage honesty ──> X9 vintage diff
  └──> D3 as_of() gateway ──> D6 leakage tests ──> X8 CI badge
            │
            ├──> M2 walk-forward ──> M1 baseline ──> M3 skill metrics ──> F4 scoreboard
            │                              └──> M4 directional def
            ├──> M9 weekly backtest nowcasts ──> X5 convergence-by-horizon
            │                                └──> X1 convergence chart
            └──> D10 feature snapshot ──> X3 "what the model saw"
                                      └──> X2 contribution breakdown (needs ridge)
D4 available_at rules ──> D3
D5 reveal calendar (timestamps) ──> D6, L8 void rule, F1 countdown
D9 structural breaks ──> M2 (fold exclusion), F5 methodology

M5 empirical intervals ──requires──> M2 residuals
M7 model version ──> M8 freeze ──> X6 challengers

L2 canonical serialisation ──> L3 payload ──> L5 hash chain ──> L1 append-only storage
                                    │                └──> L11 export + verifier
                                    ├──> L4 OTS anchoring ──> X4 OTS badge
                                    └──> X4 client-side verify (needs L2 golden vectors)
L3 ──requires──> M7 model_version, D10 snapshot hash, M1 baseline_point
L6 grades ──requires──> L3, D5 (reveal_at, actual source)
L7 grading rules ──must precede──> first live lock
L8 void rule ──requires──> D5 timestamped reveals
F2 LIVE/BACKTEST separation ──conflicts──> any blended headline metric
X6 challengers ──conflicts──> silent model replacement
```

### Dependency Notes

- **The ledger payload (L3) needs model versioning, feature snapshots and the baseline to exist first.** Build model versioning and the baseline before the first lock. The ledger schema can't change after the first live row without a `schema_version` bump, so design L2/L3 carefully once.
- **L7 (grading rules) and M8 (model freeze) have a hard deadline: before the first Q3 FY27 live lock.** Today is 17 Nov 2026 and the earliest reveal (DMART business update) is expected around 1–3 Jan 2027, so roughly 6–7 weekly locks are possible. Every week lost to building means one fewer convergence point.
- **The void rule (L8) depends on timestamp-precision reveals (D5).** Date-only reveals make same-day locks ambiguous.
- **The reveal timing problem drives the official-call rule.** DMART's update typically arrives within days of quarter-end. December GST (published ~1 Jan) may arrive *after* DMART's reveal. The official call for DMART must therefore be defined as the last valid lock before `reveal_at`. Accept that DMART's official call will usually miss the last month's GST print, and say so.
- **X2 contribution breakdown favours keeping ridge as the official model.** Gradient boosting can be a challenger (X6) without breaking X2.
- **D7 conflicts with a naive "download all Trends once" collector.** The historical collector must make one request per as-of date, which takes longer and hits pytrends rate limits harder. Cache aggressively and fall back to a seed CSV.

---

## MVP Definition

### Launch With (v1 — must be live before the first Q3 FY27 lock)

- [ ] D1–D6, D8, D9, D10: point-in-time store, gateway, reveal calendar with timestamps, leakage tests, provenance, break markers (GST 2.0 + Blinkit), feature snapshots. *Every credibility claim rests on these.*
- [ ] D7: Trends pulled per as-of window for the backtest and snapshotted weekly going forward. *Catches the most likely reviewer question.*
- [ ] M1–M8, M10: baseline, walk-forward, skill metrics, non-trivial directional definition, empirical 80% intervals plus coverage with n, train/test, versioning, frozen model, reproducible CLI.
- [ ] L1–L3, L5–L11: canonical append-only hash-chained ledger, grades, pre-published rules, void/missed/annotation handling, export plus verifier.
- [ ] L4 (minimum: OpenTimestamps for every lock, plus a public git export). *Without it, "provably" is overclaiming.*
- [ ] F1–F8: front page, LIVE/BACKTEST separation, Record, scoreboard, methodology, disclaimer, freshness, static-first.
- [ ] X4 client-side verify (already in PROJECT.md) and X7 microcopy computed from data.

### Add After Validation (v1.x — during Q3 FY27, before the reveals)

- [ ] X1 convergence chart. *Trigger: 3+ live weekly locks exist.*
- [ ] X3 "what the model saw" panel. *Trigger: once snapshots are flowing.*
- [ ] M9 + X5 weekly backtest nowcasts and error-by-horizon. *Trigger: once the backtest is stable. Strong methodology content.*
- [ ] X8 CI badge, X10 interval score.
- [ ] X2 contribution breakdown. *Trigger: ridge confirmed as the official model.*

### Future Consideration (v2+)

- [ ] X6 challenger models (gradient boosting as a locked challenger). *Defer until v1 has graded results to compare against.*
- [ ] Forward-collected features (Play Store, jobs) entering the model. *Only after 4+ quarters of captured history, announced via a new model version.*
- [ ] X9 Trends vintage diff view.
- [ ] Manually entered, cited consensus comparison.
- [ ] Universe expansion (TRENT, FSN) through `universe_change` ledger rows.

---

## Feature Prioritization Matrix

| Feature | User (reviewer) Value | Implementation Cost | Priority |
|---------|----------------------|---------------------|----------|
| D1–D3 bitemporal store + `as_of` gateway | HIGH | MEDIUM | P1 |
| D5 timestamped reveal calendar | HIGH | MEDIUM | P1 |
| D6 leakage tests | HIGH | MEDIUM | P1 |
| D7 Trends vintage honesty | HIGH | MEDIUM | P1 |
| D9 structural breaks (incl. GST 2.0) | HIGH | MEDIUM | P1 |
| M1/M3 baseline + skill metrics | HIGH | LOW | P1 |
| M4 non-trivial directional accuracy | HIGH | LOW | P1 |
| M5 empirical intervals + coverage | HIGH | MEDIUM | P1 |
| M7/M8 versioning + freeze | HIGH | LOW | P1 |
| L2 canonical serialisation + golden vectors | HIGH | MEDIUM | P1 |
| L4 OpenTimestamps anchoring | HIGH | MEDIUM | P1 |
| L5 hash chain | MEDIUM | LOW | P1 |
| L7/L8/L9 rules, void, missed | HIGH | LOW | P1 |
| L11 export + standalone verifier | HIGH | LOW | P1 |
| F1–F6 core pages | HIGH | MEDIUM | P1 |
| X4 client-side verify | HIGH | MEDIUM | P1 |
| X1 convergence chart | HIGH | MEDIUM | P2 |
| X3 what-the-model-saw | HIGH | LOW | P2 |
| M9/X5 weekly backtest + horizon curve | MEDIUM | MEDIUM | P2 |
| X2 contribution breakdown | MEDIUM | MEDIUM | P2 |
| X8 CI badge, X10 interval score | MEDIUM | LOW | P2 |
| X6 challengers | MEDIUM | LOW | P3 |
| X9 vintage diff | LOW | MEDIUM | P3 |

---

## Competitor Feature Analysis

| Feature | Estimize | YipitData / M Science | GDPNow | Metaculus | Our Approach |
|---------|----------|-----------------------|--------|-----------|--------------|
| Benchmark | Wall St consensus | Consensus | Blue Chip / WSJ survey (in papers) | Naive priors / community | Naive seasonal baseline (honest, free), shown first |
| Track record | Self-reported accuracy claims | Case studies; "flag and explain misses" | Full downloadable history + error chart | Public track-record page, calibration plots | Full ledger incl. weekly, void and missed locks |
| Running updates | Estimates revised until report | Data refreshed through the quarter | Updated after each data release | Forecasts updated over time | Weekly locked nowcasts + official call |
| Explanation of moves | Little | Analyst notes (paid) | Subcomponent contributions per update | Comments | Contribution breakdown (X2) |
| Point-in-time proof | None public | Not public | Institutional trust | Platform trust | Bitemporal store + feature snapshots + OTS-anchored hashes |
| Uncertainty | Distribution of estimates | Varies | Point only on headline | Full distributions + calibration | 80% interval + empirical coverage with n |
| Verifiability by a third party | No | No | Partial (data files) | Partial (API) | Full: export + stdlib verifier + Bitcoin anchor |

---

## Sources

- Estimize accuracy claims and academic comparisons: [IR Magazine](https://irmagazine.com/reporting/estimize-offers-new-approach-consensus-estimates), [FactSet Estimize datafeed](https://insight.factset.com/resources/at-a-glance-estimize-us-equities-estimates-datafeed), [Bliss (USD) via Wayback](https://webcf.waybackmachine.org/web/20210811085050/http://com.estimize.public.s3.amazonaws.com/papers/Barbara%20Bliss%20-%20University%20of%20San%20Diego%20-%20The%20Value%20of%20Crowdsourcing%20-%20Estimize%20-%20July.pdf) (MEDIUM, mostly self-reported)
- YipitData methodology and positioning: [YipitData public investors](https://www.yipitdata.com/public-investors), [YipitData datafeeds](https://www.yipitdata.com/platform/datafeeds), [Sacra](https://sacra.com/c/yipitdata/) (LOW–MEDIUM, vendor/secondary)
- Thinknum datasets: [Datarade](https://datarade.ai/data-providers/thinknum), [Thinknum job listings](https://blog.thinknum.com/job-listings) (MEDIUM)
- GDPNow design and track record: [Atlanta Fed GDPNow](https://www.atlantafed.org/cqer/research/gdpnow.), [GDPNow FAQs](https://www.atlantafed.org/cqer/research/gdpnow/tab_FAQs), [Macroblog "GDPNow and then"](https://www.atlantafed.org/blogs/macroblog/2016/05/16/gdpnow-and-then) (HIGH)
- ALFRED vintages and release-date fallback: [Using the ALFRED Database](https://www.stlouisfed.org/open-vault/2021/august/using-the-alfred-database), [Data Revisions with FRED](https://www.stlouisfed.org/publications/page-one-economics/2022/08/01/data-revisions-with-fred), [ALFRED help](https://alfred.stlouisfed.org/help) (HIGH)
- Forecast track-record conventions: [Metaculus 20,000 predictions analysis](https://www.metaculus.com/news/2016/10/15/prediction-analysis/), [Exploring Metaculus's AI track record](https://forum.effectivealtruism.org/posts/e9htD7txe8RDdcehm/exploring-metaculus-s-ai-track-record) (MEDIUM–HIGH)
- OpenTimestamps: [opentimestamps.org](https://opentimestamps.org/), [Wikipedia](https://en.wikipedia.org/wiki/OpenTimestamps), [IETF draft Bitcoin-anchored temporal proof](https://datatracker.ietf.org/doc/html/draft-fassbender-scitt-time-anchor-07) (HIGH)
- Google Trends sampling and inconsistency: [arXiv 2504.07032 Restoring the Forecasting Power of Google Trends](https://arxiv.org/html/2504.07032v1), [EDML 2020 paper](https://imada.sdu.dk/Research/EDML/2020/EDML20_paper_5.pdf), [Supermetrics on Trends discrepancies](https://docs.supermetrics.com/docs/about-discrepancies-in-google-trends-data) (HIGH for the phenomenon). The 0–100 normalisation over the query window is documented Google Trends behaviour (HIGH).
- GST 2.0 rate rationalisation (22 Sep 2025) effect on collections: [Business Standard Oct 2025 net revenue](https://www.business-standard.com/economy/news/gst-net-revenues-inch-up-0-6-in-october-refunds-jump-nearly-40-125110100861_1.html), [Business Standard first full month of GST 2.0](https://www.business-standard.com/amp/economy/news/tax-turbulence-revenues-take-a-hit-in-first-full-month-of-gst-2-0-125120101323_1.html), [DSIJ Dec 2025](https://www.dsij.in/blog/market-blogs-4/gst-collections-grow-6-1-in-december-2025-as-rate-cut-impact-plays-out-125), [Deccan Herald Sep 2025](https://www.deccanherald.com/business/gst-collections-rise-by-9-pc-to-rs-189-lakh-crore-in-september-3749576) (MEDIUM; check exact figures against PIB/GSTN)
- Domain knowledge, not independently verified this session (MEDIUM): typical DMART/Titan business-update timing; SEBI Research Analyst regulations as the boundary for recommendations; GitHub commit dates being author-set; Python/JS float serialisation mismatches in hash verification.

---
*Feature research for: alternative-data revenue nowcasting + public prediction ledger*
*Researched: 2026-11-17*
