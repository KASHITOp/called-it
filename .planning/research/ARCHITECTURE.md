# Architecture Research

**Domain:** Alternative-data revenue nowcaster: point-in-time data store, walk-forward modelling, append-only hashed prediction ledger, read-only API and static broadsheet frontend
**Researched:** 2026-11-17
**Confidence:** MEDIUM-HIGH overall. The ledger hash spec and the SQLite trigger behaviour were checked by running code locally (HIGH). Platform facts (Supabase, Vercel, GitHub Actions) come from web search cross-checked against official docs (MEDIUM). Modelling and leakage design rests on established practice and first-principles reasoning (MEDIUM).

---

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  SCHEDULER (GitHub Actions cron, UTC)       concurrency group: "ledger"      │
│  collect-daily.yml   lock-weekly.yml   grade-daily.yml   export-site.yml  ci │
└───────┬──────────────────┬─────────────────┬─────────────────┬───────────────┘
        │ runs             │ runs            │ runs            │ runs
┌───────▼──────────┐ ┌─────▼─────────────────▼──────┐ ┌────────▼───────────────┐
│ /data  (pitdata) │ │ /nowcaster  (nowcaster)       │ │ nowcaster.export        │
│  collectors/     │ │  features/  (PIT feature API) │ │  calls FastAPI app      │
│  seed CSV loader │ │  models/    (baseline, ridge, │ │  in-process, writes     │
│  store/ (write)  │ │             gbm, registry)    │ │  every GET response as  │
│  pit/  (read     │ │  backtest/  (walk-forward)    │ │  JSON + ledger.jsonl    │
│   as_of view)    │ │  ledger/    (canonical+hash,  │ └────────┬───────────────┘
│  calendar/ (IN   │ │             append, verify)   │          │ git commit
│   fiscal, IST)   │ │  grading/                     │          ▼
│  db/ (engine,    │ │  api/  (FastAPI, GET only)    │ ┌────────────────────────┐
│   UTC types,     │ │  cli/  (typer: nowcast ...)   │ │ /web  (Next.js, Vercel)│
│   migrations)    │ └──────────────┬────────────────┘ │  data adapter:         │
└───────┬──────────┘                │                  │  static JSON (default) │
        │ writes observations       │ reads PIT view;  │  or live API (flag)    │
        │ (insert-only)             │ appends ledger   │  verify = WebCrypto    │
┌───────▼───────────────────────────▼──────────────┐   │  SHA-256 in browser    │
│  DATABASE  (one flag: SQLite local / Postgres prod on Supabase)               │
│  series · observations (bitemporal) · reveals(view) · model_versions         │
│  feature_snapshots · predictions (append-only, hash-chained) · grades        │
│  backtest_runs · backtest_predictions (never mixed with the live ledger)     │
└───────────────────────────────────────────────────────────────────────────────┘
```

**Arrows go one way.** Collectors write observations. The nowcaster reads observations through a point-in-time (PIT) view and only writes to `feature_snapshots`, `predictions`, `grades` and the backtest tables. The API only reads. The website only reads, either from exported JSON files or from the API. Nothing downstream ever writes upstream.

### Component Responsibilities

| Component | Owns | Implementation |
|-----------|------|----------------|
| `pitdata.db` | Engine creation from one setting; the `UTCDateTime` type; migrations; dialect-specific triggers | SQLAlchemy 2.x Core, Alembic (`render_as_batch=True` for SQLite), pydantic-settings |
| `pitdata.calendar` | Indian fiscal quarters (`Q3FY27` ⇄ dates), IST⇄UTC, period-end conventions | Pure functions, no I/O. Shared with the vol engine and the terminal |
| `pitdata.store` | Insert-only writes to `series` / `observations`; idempotent re-ingest; revisions stored as new rows | Repository class with no update or delete methods |
| `pitdata.pit` | `PointInTimeReader(as_of, mode)`: the **only** read path for modelling code | SQL filter `available_at < as_of`, then latest vintage per (series, period) |
| `pitdata.collectors` | One module per source (results/revenue, GST, Trends, Play Store, jobs). Each returns typed `ObservationIn` records with `available_at` and `availability_basis`; seed-CSV fallback | httpx, pytrends (archived, see PITFALLS), pydantic models |
| `nowcaster.universe` | Company config (tickers, GST states, Trends terms, structural breaks, reveal sources) | `config/universe.toml`, validated with pydantic |
| `nowcaster.features` | `build_features(company, quarter, as_of, reader) -> FeatureVector` with lineage | Pure function over a reader |
| `nowcaster.models` | Baseline, ridge, GBM specs; `ModelSpec.fit/predict/interval`; registry | scikit-learn Pipelines, refit per fold |
| `nowcaster.backtest` | Walk-forward harness, fold generation, metrics, results table | Plain Python loops, which are easy to audit |
| `nowcaster.ledger` | Canonical payload, SHA-256, hash chain, append, `verify` | stdlib `json`, `hashlib`, `decimal` |
| `nowcaster.grading` | Reveal detection, official-call derivation, grade rows | Reads observations and predictions; inserts grades |
| `nowcaster.api` | Read-only REST surface; it is also the schema for the static export | FastAPI with pydantic response models, GET only, read-only DB role |
| `nowcaster.export` | Calls every API route in-process and writes `web/public/data/v1/**.json` plus `ledger.jsonl` | `fastapi.testclient` / httpx ASGITransport |
| `nowcaster.cli` | `nowcast collect / backtest / predict / grade / verify / export / serve` | typer |
| `/web` | Broadsheet UI; client-side hash verification; countdowns | Next.js + Tailwind; TS types generated from OpenAPI |

---

## Recommended Project Structure

```
called-it/
├── pyproject.toml                 # uv workspace root: members = ["data", "nowcaster"]
├── uv.lock
├── Makefile / justfile            # `make setup` (uv sync + migrate + seed), `make all`
├── .env.example                   # DB_BACKEND=sqlite|postgres, DATABASE_URL=...
├── data/                          # workspace member, package `pitdata` (shared infra)
│   ├── pyproject.toml
│   ├── seed/                      # manual fallback CSVs + README with exact download steps
│   │   ├── revenue_quarterly.csv  #   includes business_update_at, results_at columns
│   │   ├── gst_monthly.csv        #   includes press_release_date column
│   │   └── trends_weekly/         #   one file per pull (vintage), never overwritten
│   ├── migrations/                # Alembic env + versions (dialect-aware trigger DDL)
│   └── src/pitdata/
│       ├── db/        engine.py, types.py (UTCDateTime, DecimalText), schema.py
│       ├── calendar/  fiscal.py, tz.py
│       ├── store/     writer.py, models.py (ObservationIn, Series)
│       ├── pit/       reader.py (PointInTimeReader), errors.py (LeakageError)
│       └── collectors/ base.py, results.py, gst.py, trends.py, playstore.py, jobs.py
├── nowcaster/                     # workspace member, package `nowcaster`
│   ├── pyproject.toml
│   ├── config/universe.toml       # DMART, ETERNAL, TITAN (+ stretch), swappable
│   ├── models/                    # registry artifacts: <model_version>/{spec.json,coef.json,model.joblib}
│   └── src/nowcaster/
│       ├── universe.py
│       ├── features/  builder.py, definitions.py (5–8 named features), snapshot.py
│       ├── models/    baseline.py, ridge.py, gbm.py, intervals.py, registry.py
│       ├── backtest/  harness.py, folds.py, metrics.py, report.py
│       ├── ledger/    canonical.py, chain.py, append.py, verify.py
│       ├── grading/   reveals.py, grade.py
│       ├── api/       app.py, routes/, schemas.py
│       ├── export/    static.py
│       └── cli.py
├── tests/                         # single root test tree (requirement)
│   ├── conftest.py                # backend fixture: parametrised sqlite + postgres
│   ├── fixtures/
│   │   ├── hash_vectors.json      # golden vectors, ALSO consumed by web tests
│   │   └── synthetic_store.py     # hypothesis strategies for observations
│   ├── leakage/                   # the most important tests in the repo
│   ├── ledger/                    # triggers, chain, canonicalisation, REPLACE bypass
│   ├── data/                      # calendar, store idempotency, collectors (recorded HTTP)
│   ├── nowcaster/                 # features, baseline, harness, grading
│   └── api/                       # read-only guarantees, schema snapshot
├── web/
│   ├── package.json
│   ├── public/data/v1/            # GENERATED by export (committed by Actions)
│   ├── src/lib/data.ts            # adapter: static | api
│   ├── src/lib/canonical.ts       # JS twin of ledger/canonical.py
│   ├── src/lib/api-types.ts       # generated from openapi.json
│   └── tests/canonical.test.ts    # reads ../tests/fixtures/hash_vectors.json
└── .github/workflows/
    ├── ci.yml                     # pytest on sqlite AND postgres service; web tests
    ├── collect-daily.yml
    ├── lock-weekly.yml
    ├── grade-daily.yml            # cheap, idempotent; active during reveal windows
    └── export-site.yml            # reusable workflow, called at the end of the others
```

### Structure Rationale

- **`data/` is its own package (`pitdata`) with no import of `nowcaster`.** The vol surface engine and the markets terminal depend on `pitdata` and never on `nowcaster`. Enforce this with an import-linter contract or a test that greps imports.
- **uv workspace** (one lockfile, several members). You get one `uv sync` for setup, and each later project adds a member (`volsurface/`, `terminal/`) without restructuring. MEDIUM confidence; this is standard uv usage.
- **The API lives inside `nowcaster`** for now. When project 3 needs a combined API, promote it to a top-level `api/` member that mounts routers from each project. Don't build that yet.
- **The root `/tests` tree** follows the stated layout. The `hash_vectors.json` fixture sits at the root because both pytest and vitest consume it. That shared file is what keeps the Python and browser hash implementations from drifting.
- **`web/public/data/` is generated and committed.** This makes the public git history a second, independently timestamped witness of the ledger (see Pattern 6).

---

## Architectural Patterns

### Pattern 1: Bitemporal "availability-dated" observation store

**What:** One long, narrow fact table. Each row carries three time axes:

| Column | Meaning | Who sets it |
|--------|---------|-------------|
| `period_date` | The period the value describes (valid time). Convention: **last calendar day of the period**, with frequency on the series | Collector |
| `available_at` | The earliest moment the public could have known this value (knowledge time). UTC instant | Collector, from a filing/press-release timestamp or a documented conservative rule |
| `ingested_at` | When *we* recorded it (transaction time) | DB default / writer, never the collector |

Revisions and restatements are **new rows** with a later `available_at`. Nothing is updated.

**Schema (portable DDL, Postgres types shown; SQLite via SQLAlchemy type decorators):**

```sql
CREATE TABLE series (
  series_id      INTEGER PRIMARY KEY,           -- identity on PG
  series_key     TEXT NOT NULL UNIQUE,          -- 'gst.collections.state.MH', 'rev.consolidated.DMART'
  source         TEXT NOT NULL,                 -- 'nse_filing' | 'gst_council' | 'google_trends' | ...
  metric         TEXT NOT NULL,
  entity         TEXT,                          -- ticker, state code, search term
  unit           TEXT NOT NULL,                 -- 'INR_cr' | 'index_0_100' | 'rank'
  frequency      TEXT NOT NULL,                 -- 'D' | 'W' | 'M' | 'Q'
  collection_mode TEXT NOT NULL,                -- 'historical' | 'forward_collected'
  attributes     JSONB / TEXT(json)             -- extensible dims (later: strike, expiry, tenor)
);

CREATE TABLE observations (
  obs_id            BIGINT PRIMARY KEY,
  series_id         INTEGER NOT NULL REFERENCES series,
  period_date       DATE NOT NULL,
  value             NUMERIC(20,6),              -- SQLite: stored via DecimalText (TEXT) type
  available_at      TIMESTAMPTZ NOT NULL,       -- SQLite: fixed-width 'YYYY-MM-DDTHH:MM:SS.ffffffZ'
  availability_basis TEXT NOT NULL,             -- 'exchange_timestamp' | 'press_release_date' | 'rule:+5d' | 'pull_time'
  ingested_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  vintage_label     TEXT,                       -- e.g. Trends pull id, 'restated_in_Q3FY27_filing'
  source_ref        TEXT NOT NULL,              -- URL / filing id / seed file + row
  source_kind       TEXT NOT NULL,              -- 'api' | 'scrape' | 'seed_csv' | 'manual'
  content_hash      TEXT NOT NULL,              -- sha256(series_key|period|value|available_at) for idempotency
  UNIQUE (series_id, period_date, available_at, content_hash)
);
CREATE INDEX ix_obs_pit ON observations (series_id, available_at, period_date);
```

Observations get the same insert-only triggers as the ledger. That is cheap, and it means the store itself can be called immutable.

**Revenue and reveal modelling (this project):**
- `rev.consolidated.<T>`: consolidated revenue from operations. `available_at` = results-filing timestamp.
- `rev.update.<T>`: DMART's standalone revenue update and Titan's growth-% business update. These are separate series because they are a different basis. `available_at` = update filing timestamp.
- `reveal_at(T, Q)` is a **view**: `MIN(available_at)` over both series for (T, period_date=Q end). Keep `business_update_at` and `results_at` side by side for auditing.
- A comparative restatement of last year's quarter, printed in this year's filing, is a new row for the old `period_date` with the new filing's `available_at`.

**Read path (the leakage gate):**

```python
class PointInTimeReader:
    def __init__(self, engine, as_of: datetime, mode: Literal["backtest", "live"]):
        assert as_of.tzinfo is not None and as_of.utcoffset() == timedelta(0)
        ...
    def series(self, series_key: str, start: date | None = None) -> pd.DataFrame:
        # SQL: WHERE series_key = :k AND available_at < :as_of
        #      [live mode adds: AND ingested_at <= :as_of]
        # pandas: sort by available_at, keep last row per period_date (latest vintage as-of)
        # post-condition (always on): assert (df.available_at < self.as_of).all()
```

- **`backtest` mode** ignores `ingested_at`, because history was reconstructed later.
- **`live` mode** also requires `ingested_at <= as_of`. This proves the lock used only data the system actually had at lock time.
- Do the "latest vintage" step in pandas, not with `DISTINCT ON`. It stays portable across SQLite and Postgres, the data volume is tiny, and it is easy to test.

**Reuse:** the vol surface engine and the terminal reuse `series`, the three-time-axis convention, `PointInTimeReader`, `calendar` and `UTCDateTime`. High-volume option-chain snapshots should go in a **sibling table** with the same temporal columns rather than this narrow table. Reuse the conventions and the reader interface, not the physical table.

**Trade-offs:** The long format makes pivots slightly clumsy, but it gives one leakage gate for every source, which is the point. Storing full vintages (each Trends pull) grows storage, which is negligible at this scale.

### Pattern 2: Leakage-safe feature builder with explicit `as_of`

**What:** Features are a pure function of `(company, quarter, as_of, reader)`. There is no global "now", no `datetime.utcnow()` inside feature code, and no direct DB access. The reader is constructed with `as_of`, so future rows are physically unreachable.

```python
@dataclass(frozen=True)
class FeatureVector:
    company: str; quarter: str; as_of: datetime
    values: dict[str, float]                  # 5–8 named features
    lineage: tuple[ObsRef, ...]               # (obs_id, series_key, period_date, available_at, value)
    def __post_init__(self):
        bad = [r for r in self.lineage if r.available_at >= self.as_of]
        if bad: raise LeakageError(bad)       # second, independent guard

def build_features(company: Company, quarter: FiscalQuarter, as_of: datetime,
                   reader: PointInTimeReader) -> FeatureVector: ...
```

**Rules the builder must follow:**
1. **Strict `<`.** A row with `available_at == as_of` is excluded. Make this a named test.
2. **Horizon-matched features.** A weekly lock mid-quarter sees only part of the quarter: some weeks of Trends, perhaps one month of GST. Define features as "QTD as of `as_of`" (for example the YoY of available months' GST, and `months_available` as an explicit input or a model-per-horizon). Training rows for past quarters must be built at the **same relative offset** (for example `reveal_at(q) - Δ`). Otherwise the model trains on full-quarter features and predicts from partial ones.
3. **Label availability cutoff.** The baseline's "trailing YoY" and any lagged-revenue feature may only use quarters whose `reveal_at < as_of`. Concrete trap: an October lock for Q3 FY27 does **not** have Q2 FY27 actuals for every company yet, because results arrive in late Oct or Nov.
4. **Trends re-normalisation.** Google rescales 0–100 to the peak of the *requested window*. A backfill pulled today over 2021–2026 bakes the future peak into every past value. Pull Trends with `timeframe = <start> <as_of date>` per cutoff, or build only scale-free features (ratios or YoY inside a single pull window that ends before `as_of`), and record each pull as a vintage. Label backtests that use one modern pull as "pseudo-real-time" (MEDIUM confidence that sampling noise exists; HIGH that window-peak normalisation exists).
5. **Conservative availability rules.** If a historical GST press-release date can't be found, use a documented rule that errs late (for example `period_end + N days`, with N set to the observed maximum) and tag `availability_basis='rule:...'`.

**Feature snapshot JSON** is persisted per prediction and hashed with the ledger canonicaliser:

```json
{"as_of":"2026-11-23T03:30:00Z","company":"DMART","quarter":"Q3FY27","feature_set":"fs-v1",
 "values":{"gst_nat_yoy":"0.084120","gst_mh_yoy":"0.071003","trends_qtd_yoy":"0.052000", "...":"..."},
 "lineage":[{"obs_id":"10423","series_key":"gst.collections.state.MH","period_date":"2026-10-31",
             "available_at":"2026-11-01T11:30:00Z","value":"31245.000000"}]}
```

### Pattern 3: Leakage tests that fail on leaks, and a test that proves they can fail

Put these under `tests/leakage/`. Run them on both backends.

| # | Test | Mechanism |
|---|------|-----------|
| L1 | **Future-perturbation invariance** (the flagship test) | Hypothesis generates a random store and a random cutoff `T`. Build features at `T`. Then randomly add, mutate or delete **only** rows with `available_at >= T`, including absurd sentinel values (`9.99e11`). Rebuild and assert the result is **bit-identical**. This catches leaks you never thought of. |
| L2 | Sentinel future rows | Fixture inserts, for every series, a row at `available_at = T` (boundary) and `T + 1s` with a sentinel value. Assert no feature value and no lineage entry references them. |
| L3 | Lineage assertion | For every `FeatureVector` in a full backtest: `max(lineage.available_at) < as_of`. |
| L4 | Revision correctness | Value v1 available before T, revised to v2 after T: features use v1. Both available before T: features use the later vintage. |
| L5 | Label leakage in folds | For every fold, `max(reveal_at of training targets) < fold.as_of`, and the target quarter is not in its own training set. |
| L6 | Fit leakage | Perturb the test row's features and assert the fitted Pipeline parameters (scaler means, coefficients) don't change. |
| L7 | Time-zone boundary | An IST filing at 00:15 IST on 2 Jan is 18:45 UTC on 1 Jan. Assert the ordering against a cutoff expressed in UTC. |
| L8 | Lock guard | `nowcast predict --lock` refuses (non-zero exit) for (T, Q) when `reveal_at(T,Q) <= now` or any `rev.*` row exists for Q. |
| L9 | **Mutation check: the tests can fail** | A fixture provides a deliberately leaky reader (`<=` instead of `<`, or no filter at all). Run L1–L3 against it, marked `xfail(strict=True)`. If the leaky reader ever *passes*, the suite goes red. |
| L10 | No ambient clock | A static test (AST or grep) that `features/`, `models/` and `backtest/` never call `datetime.now`, `utcnow`, `date.today` or `time.time`. Freeze the clock with `time-machine` elsewhere. |

### Pattern 4: Walk-forward (expanding-window) harness

**Folds are calendar-quarter based and pooled across companies:**

```python
for target_q in eval_quarters:                       # chronological, first after min_train
    for co in universe:
        as_of = cutoff_policy(co, target_q)          # 'official': reveal_at - 1 day; or horizon h
        train = [(c, q) for c in universe for q in quarters
                 if reveal_at(c, q) < as_of and not excluded(c, q)]   # Eternal break rule here
        X_tr = [build_features(c, q, cutoff_policy(c, q), reader_at(cutoff_policy(c, q))) for c,q in train]
        X_te = build_features(co, target_q, as_of, reader_at(as_of))
        for spec in (baseline, ridge, gbm):
            m = spec.fit(X_tr, y_tr)                 # fresh Pipeline every fold
            record(run_id, spec.version, co, target_q, as_of, m.predict(X_te), m.interval(X_te))
```

- **Pooled beats per-company here.** With 12–16 quarters per company, a YoY target loses 4 quarters to the lag, leaving about 8–12 targets per company. Early folds would train per-company models on 4–6 points. Use **one pooled ridge on YoY growth with company one-hot intercepts**, with features standardised within company (fit inside the Pipeline). Report per-company models only as a comparison row. GBM on about 30 pooled rows is a stretch: keep it shallow (depth 2, strong regularisation) and expect it to lose to ridge, which is fine and honest.
- **`min_train`**: start evaluating once at least about 12 pooled training rows exist. Print the number of eval folds per company in the results table (it will be small, around 6–10, so say so).
- **Hyperparameters** (ridge `alpha`): either fix and document a value, or choose it by an *inner* time-ordered CV on the training rows only. Never tune on eval folds.
- **80% interval**: empirical quantiles (10th/90th) of the model's *prior out-of-sample* residuals, pooled across companies and expressed in growth space, which is a simple split-conformal style interval. Before enough residuals exist, fall back to in-sample residuals and flag it. Report realised coverage.
- **Horizon curve (differentiator, cheap):** run the harness at several `cutoff_policy` offsets (13 weeks before reveal down to 1 day) to show error versus horizon. This mirrors the weekly live locks.
- **Backtest output goes to `backtest_runs` / `backtest_predictions`, never to `predictions`.** Each run stores `run_id`, git SHA, model versions, `cutoff_policy` and a "pseudo-real-time" flag.

### Pattern 5: Model registry and versioning

- **`model_version` format:** `<family>-<target>@<semver>+fs.<feature_set_hash8>`, for example `ridge-yoy@1.0.0+fs.3f9a2c1e`. Use `baseline-sqly@1.0.0` for the naive model. Bump semver on any spec or hyperparameter change. The feature-set hash is the SHA-256 of the canonical feature-definitions JSON, so changing a feature definition changes the version automatically.
- **`model_versions` table (insert-only):** `model_version`, `spec_json` (family, hyperparams, feature list, target transform, interval method), `feature_set_hash`, `git_sha`, `trained_through` (latest label quarter), `created_at`, `artifact_sha256`.
- **Artifacts:** for ridge, publish `coef.json` (coefficients, intercepts, scaler params). It is transparent, diffable and shows well on the methodology page. `joblib` only for GBM, with its SHA-256 recorded. Live locks **refit** on all labels available at `as_of` using the registered *spec*. The fitted artifact for that lock is identified by `feature_snapshot_sha256` + `model_version` + `trained_through`.

### Pattern 6: Append-only ledger with browser-verifiable hashes

**Exact canonicalisation spec, `calledit-ledger-v1`.** This spec was verified by running it: Python `json.dumps` and browser-style `JSON.stringify` + `crypto.subtle.digest` produced the identical SHA-256 `a1f29bf6…de50` for a test payload.

1. Payload is a flat JSON object. **Every value is a string.** There are no JSON numbers, booleans or nulls, which removes all float-formatting divergence between Python and JS (the problem RFC 8785 exists to solve). Every field is always present; there are no optional fields.
2. Allowed characters in values: printable ASCII `0x20–0x7E`, excluding `"` and `\`. Validate at append time and reject anything else. Escaping is then identical in both languages.
3. Keys are sorted by code point and serialised with no whitespace. Python: `json.dumps(p, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`. JS: `JSON.stringify(Object.fromEntries(Object.keys(p).sort().map(k => [k, p[k]])))`.
4. Bytes are UTF-8, which is ASCII here. Hash is SHA-256 as **lowercase hex**, 64 characters.
5. **Money:** ₹ crore, exactly 2 decimal places, `Decimal.quantize(Decimal("0.01"), ROUND_HALF_EVEN)`, no thousands separators, no `+`, `-` for negatives, `"0.00"` for zero. Never build from `repr(float)`: go `float → Decimal(str(x))` once, then quantize.
6. **Ratios/growth:** 6 decimal places, same rounding.
7. **Timestamps:** UTC, `YYYY-MM-DDTHH:MM:SSZ`, second precision. Truncate `locked_at` to whole seconds *before* storing so the DB value equals the hashed string. **The browser must never re-format timestamps**: `Date.toISOString()` emits `.000Z` and would break the hash. JS uses the stored strings verbatim.
8. **Dates:** `YYYY-MM-DD`. **Quarter:** `Q3FY27`. **Integers** (seq): base-10 string with no leading zeros.
9. **Chain:** `prev_hash` = hash of the row with `seq - 1`. The genesis row uses 64 `0`s.

**Payload fields (v1):** `scheme, seq, ticker, fiscal_quarter, target` (`"rev_ops_consolidated_inr_cr"`), `point_inr_cr, lo80_inr_cr, hi80_inr_cr, baseline_inr_cr` (the baseline is locked alongside the model so it can't be computed retroactively), `model_version, feature_snapshot_sha256, data_cutoff, locked_at, lock_kind` (`"weekly"` | `"final"`), `prev_hash`.

**Table:** `predictions(seq PK, payload_canonical TEXT, hash TEXT UNIQUE, prev_hash TEXT UNIQUE, ...structured columns mirroring payload...)`. `UNIQUE(prev_hash)` makes a **fork in the chain impossible at the DB level** on both backends. Store `payload_canonical` (the exact hashed text) *and* typed columns. A verify test asserts that they agree.

**Triggers:**

```sql
-- Postgres
CREATE FUNCTION calledit.forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'calledit: % is append-only (op=%)', TG_TABLE_NAME, TG_OP; END $$;
CREATE TRIGGER predictions_no_update_delete BEFORE UPDATE OR DELETE ON calledit.predictions
  FOR EACH ROW EXECUTE FUNCTION calledit.forbid_mutation();
CREATE TRIGGER predictions_no_truncate BEFORE TRUNCATE ON calledit.predictions
  FOR EACH STATEMENT EXECUTE FUNCTION calledit.forbid_mutation();   -- TRUNCATE skips row DELETE triggers
REVOKE UPDATE, DELETE, TRUNCATE ON calledit.predictions FROM calledit_writer;  -- third layer: privileges
GRANT SELECT ON ALL TABLES IN SCHEMA calledit TO calledit_reader;              -- API role

-- SQLite
CREATE TRIGGER predictions_no_update BEFORE UPDATE ON predictions
  BEGIN SELECT RAISE(ABORT, 'calledit: predictions is append-only'); END;
CREATE TRIGGER predictions_no_delete BEFORE DELETE ON predictions
  BEGIN SELECT RAISE(ABORT, 'calledit: predictions is append-only'); END;
-- REQUIRED: INSERT OR REPLACE bypasses the DELETE trigger unless PRAGMA recursive_triggers=ON
CREATE TRIGGER predictions_no_replace BEFORE INSERT ON predictions
  WHEN EXISTS (SELECT 1 FROM predictions WHERE seq = NEW.seq OR hash = NEW.hash OR prev_hash = NEW.prev_hash)
  BEGIN SELECT RAISE(ABORT, 'calledit: predictions is append-only (replace blocked)'); END;
```

(Verified locally on SQLite 3.50.4: without the third trigger, `INSERT OR REPLACE` silently overwrote a locked row.) Apply the same trigger set to `grades`, `model_versions`, `feature_snapshots` and `observations`.

**An honest limit worth printing on the methodology page:** the DB owner can drop triggers. The credible guarantees are the hash chain plus **external witnesses**. Every lock run commits `web/public/data/ledger.jsonl` and the chain head to the public GitHub repo, and the Actions run log records the server-side time. Verification by `nowcast verify` and by the browser checks the chain against that published file. OpenTimestamps anchoring is a cheap optional extra.

**Browser verify flow:** fetch the entry (structured fields + `payload_canonical` + `hash` + `prev_hash`) → rebuild the canonical string from the fields with `canonical.ts` → assert it equals `payload_canonical` → `crypto.subtle.digest('SHA-256', utf8)` → compare to `hash` → check `prev_hash` against the previous entry → show every step on the card, with the canonical string in typewriter mono. WebCrypto needs a secure context (HTTPS or localhost), which Vercel provides.

### Pattern 7: Lock cadence, official call and grading as derived state

- **Weekly lock:** `lock-weekly.yml` runs Monday about 03:37 UTC (09:07 IST; use an odd minute to avoid top-of-hour cron congestion). Steps: collectors, then `nowcast predict --lock --kind weekly` for each (company, live quarter) whose reveal hasn't happened, then export, then commit. It runs under `concurrency: {group: ledger, cancel-in-progress: false}` so two writers can never race the chain.
- **Final lock:** config holds `expected_reveal_window` per company (DMART's business update lands about 2–5 days after quarter end; Q3 FY26's was early Jan 2026). A `--kind final` lock is scheduled at least 48h before the *earliest* expected reveal.
- **"Official call" is derived, never a stored flag** (the ledger can't be updated): it is the last prediction with `locked_at < reveal_at` for (company, quarter). If a reveal comes earlier than expected, the official call automatically becomes the last lock before it, which is honest by construction.
- **Post-reveal locks are void:** the lock guard (L8) should prevent them. If one slips through, grading marks it `void_post_reveal` rather than hiding it.
- **Grading:** `grade-daily.yml` checks for a new `rev.consolidated` row. For each ungraded prediction of that (company, quarter), it inserts an append-only `grades` row: `prediction_seq, actual_obs_id, actual_inr_cr, error_pct, abs_error_pct, inside_80, baseline_error_pct, beat_baseline, is_official (derived at grade time), graded_at`. Grade against the **first-published consolidated value**. Later restatements are shown, but they don't re-grade.
- **Timing reality for Q3 FY27:** about 6 weekly locks remain before 31 Dec 2026, and DMART's reveal comes about 2–5 Jan 2027. December GST (published about 1 Jan) will likely **not** be available before DMART's reveal. The horizon-matched backtest must reflect that.

### Pattern 8: One API contract, two transports (static export by default)

**Recommendation: ship the static JSON export as the production data path. Keep FastAPI as the single source of the read model.**

- `nowcast export` imports the FastAPI `app` and calls every GET route **in-process** (`TestClient`). It writes each response body to `web/public/data/v1/<route>.json`, plus `ledger.jsonl` and `openapi.json`. The static files *are* API responses, with identical schemas.
- `web/src/lib/data.ts` reads `NEXT_PUBLIC_DATA_MODE=static|api`. Static mode fetches `/data/v1/...json`; API mode fetches `${API_URL}/v1/...`. TS types are generated from `openapi.json` (openapi-typescript).
- **Why static wins here:** data changes at most daily. The site keeps working when Supabase's free tier pauses (after about 1 week of low activity) or the DB is down. There's no CORS, no cold starts, and no secrets on Vercel. Each daily export commit also counts as repo activity, which keeps the 60-day scheduled-workflow auto-disable from triggering. The committed export is the external ledger witness from Pattern 6.
- **Optional live API:** Vercel supports FastAPI zero-config as a Python Function (Python 3.12 default; entrypoint via `[tool.vercel] entrypoint` in pyproject). Deploy it as a *separate* Vercel project rooted at `nowcaster/` for a public `/v1` with a read-only DB role, but only after static is working. Alternatives (Render, Fly) add another platform for no gain.

**Read-only API surface (GET only; any other method returns 405; DB session uses `calledit_reader` / SQLite `mode=ro` URI):**
`/v1/meta` (sources, freshness, forward-collected status, failures) · `/v1/universe` · `/v1/editions/current` · `/v1/editions/{fq}` · `/v1/predictions?ticker=&fq=` · `/v1/predictions/{seq}` · `/v1/ledger/head` · `/v1/ledger/spec` (canonicalisation rules as data) · `/v1/grades` · `/v1/scoreboard` · `/v1/backtests/latest` · `/v1/models/{model_version}`.

### Pattern 9: Dual backend behind one flag

- `DB_BACKEND=sqlite|postgres` (pydantic-settings), with `DATABASE_URL` required for Postgres and defaulting to `sqlite:///data/local.db`.
- **`UTCDateTime` TypeDecorator:** rejects naive datetimes on write, attaches UTC on read, and stores SQLite values as fixed-width ISO text so lexicographic comparison equals chronological comparison. Postgres uses `timestamptz`.
- **`DecimalText` for money on SQLite:** SQLite has no decimal type, and NUMERIC affinity turns values into floats.
- SQLite pragmas on connect: `foreign_keys=ON`, `journal_mode=WAL`.
- **Supabase specifics:** GitHub Actions runners are IPv4-only and Supabase's direct connection string is IPv6. Use the **Session pooler** string (port 5432, user `postgres.<ref>`) from Actions. Put tables in a dedicated `calledit` schema that is **not exposed** through Supabase's auto-generated Data API, or enable RLS on every table. Otherwise the anon key could read or write via PostgREST.
- CI runs the full suite twice: SQLite, and a `postgres:16` service container. Trigger tests are parametrised over both.

---

## Data Flow

### Collection (daily, `collect-daily.yml`)

```
source (filing / GST release / Trends / Play Store / jobs)
   → collector.fetch()        (respect robots/ToS; on failure → seed CSV, record failure in meta)
   → ObservationIn[] with available_at + availability_basis + source_ref
   → store.insert()           (idempotent via content_hash; revisions become new rows)
   → observations             (insert-only triggers)
```

### Prediction lock (weekly + final, `lock-weekly.yml`)

```
now (UTC, truncated to second) ─► lock guard (reveal_at(T,Q) > now? no rev.* row for Q?)
   → PointInTimeReader(as_of=now, mode="live")
   → build_features(T, Q, as_of)  → FeatureVector + lineage → feature_snapshots (hash)
   → training set: quarters with reveal_at < as_of, horizon-matched features
   → fit registered spec (model + baseline) → point, lo80, hi80, baseline
   → canonical payload (prev_hash = head) → sha256 → INSERT predictions (single txn)
   → export → git commit (public witness)
```

### Grading (`grade-daily.yml`)

```
new rev.consolidated observation → reveals view updates
   → for each ungraded prediction (T, Q): derive is_official, compute errors vs actual & baseline
   → INSERT grades → export → commit
```

### Read (site)

```
Browser → Vercel static page → /data/v1/*.json (committed export)
        → "verify" button → canonical.ts + crypto.subtle.digest → compare hash & chain
(optional) Browser → API_URL/v1/* → FastAPI (GET-only, reader role) → DB
```

### Backtest (local / CI, on demand)

```
backtest config → fold generator → per fold: PIT reader at fold cutoff → features → fit → predict
   → backtest_predictions (run_id) → metrics (MAPE, directional acc., coverage, beat-baseline)
   → printed table + /v1/backtests/latest export, labelled "BACKTEST (pseudo-real-time)"
```

---

## Suggested Build Order

The dependency chain: calendar and DB types → PIT store and reader → leakage tests → collectors → features and baseline → harness → ledger → models → grading → API/export → web → ops. Two timing constraints shape it.

1. **Forward collectors lose data every day they aren't running.** Ship the store, the forward collectors and their cron early.
2. **The Q3 FY27 locks must start soon (only about 6 weeks remain).** Get the ledger live with **baseline-only locks** before the main model is finished. The main model joins the ledger under its own `model_version` once its backtest beats or honestly fails to beat the baseline.

| # | Phase | Delivers | Depends on |
|---|-------|----------|------------|
| 1 | Scaffold + DB foundation | uv workspace, `pitdata.db` (flag, `UTCDateTime`, `DecimalText`), Alembic, fiscal calendar, CI on SQLite + Postgres, universe config | — |
| 2 | PIT store + leakage harness | `series`/`observations`, insert-only triggers, `PointInTimeReader`, `tests/leakage/` L1–L4, L7, L9, L10 on **synthetic** data | 1 |
| 3 | Collectors + forward cron | Revenue/reveal (incl. business-update series), GST (with release dates), Trends (vintaged pulls), Play Store + jobs forward; seed CSVs; `collect-daily.yml` live | 2 |
| 4 | Features + baseline + walk-forward | Feature builder with lineage, baseline, harness, L5/L6, backtest table | 3 |
| 5 | Ledger + predict/grade CLI + weekly lock | Canonical v1 spec, golden vectors, triggers incl. REPLACE guard, chain, `verify`, lock guard L8, grading, `lock-weekly.yml`, **baseline locks start** | 4 (can start in parallel with 4 once the baseline exists) |
| 6 | Main model + registry + intervals | Ridge (then GBM), `model_versions`, intervals with coverage, model-vs-baseline report; main model added to weekly locks | 4, 5 |
| 7 | Read API + static export | FastAPI GET-only, OpenAPI, `nowcast export`, `export-site.yml`, ledger.jsonl witness commits | 5 (6 for scoreboard content) |
| 8 | Web broadsheet | Next.js pages, data adapter, `canonical.ts` + vitest on shared vectors, verify UX, Vercel deploy | 7 |
| 9 | Hardening + README | Optional live API on Vercel, verify-ledger in CI against the published export, one-command run, limitations | all |

---

## Scaling Considerations

Scale here means more series, more companies and later projects, not users. The site is static.

| Scale | Adjustments |
|-------|-------------|
| 3–5 companies, ~20 series (now) | Everything above. pandas in memory, SQLite locally, Supabase free tier |
| 20–50 companies, hundreds of series | Index `(series_id, available_at, period_date)` already covers it; cache reader pulls per fold; Supabase Pro to avoid pausing |
| Vol surface engine (intraday option chains) | Sibling table(s) with same temporal columns, partitioned by date on Postgres; Parquet snapshots for bulk history; reuse the `PointInTimeReader` interface, not the narrow table |

**What breaks first:** Google Trends rate limits (429s) and source changes, not the DB. Next is Supabase free-tier pausing if crons stop. The static site insulates the public view from both.

---

## Anti-Patterns

### Anti-Pattern 1: Filtering by `period_date` instead of `available_at`
**What people do:** `WHERE period_date < quarter_start` or "use data up to month-end".
**Why it's wrong:** GST for October is published in early November, and results come weeks after quarter-end. Filtering on the period leaks data that wasn't public yet.
**Do this instead:** Read only through `PointInTimeReader(as_of)`. Enforce L10 (no ambient clock) and an import rule that `features/` can't import the DB engine.

### Anti-Pattern 2: Full-quarter features in training, partial-quarter features live
**What people do:** Train on complete-quarter aggregates, then predict mid-quarter from 6 weeks of data.
**Why it's wrong:** Distribution shift makes the backtest look better than live. This is a quiet form of lookahead.
**Do this instead:** Use a horizon-matched `cutoff_policy` for training rows, and run the backtest at the same horizons as the live locks.

### Anti-Pattern 3: Mixing backtest rows into the ledger
**What people do:** Insert backtest predictions into `predictions` with a past `locked_at`.
**Why it's wrong:** It destroys the core claim. The ledger must contain only calls made before their reveal.
**Do this instead:** Use separate `backtest_*` tables, label them everywhere, and never hash-chain them.

### Anti-Pattern 4: Hashing floats or re-formatted timestamps
**What people do:** `json.dumps({"point": 19876.5})` in Python and `JSON.stringify` in JS, or recomputing `toISOString()` in the browser.
**Why it's wrong:** `19876.5` vs `19876.50`, `1e16` vs `10000000000000000`, and `.000Z` all produce different bytes, so verification fails on the public page.
**Do this instead:** All-string payloads under the v1 spec, verbatim strings in JS, and shared golden vectors tested in both languages.

### Anti-Pattern 5: A mutable "is_official" flag or retroactive baseline
**What people do:** `UPDATE predictions SET is_official = true`, or compute the baseline at grading time.
**Why it's wrong:** It needs UPDATE on an append-only table, and a baseline computed after the fact can use later data.
**Do this instead:** Derive official status at read or grade time, and lock `baseline_inr_cr` inside every payload.

### Anti-Pattern 6: Trusting the trigger alone
**What people do:** Claim immutability because a trigger exists.
**Why it's wrong:** Owners can drop triggers, and SQLite `INSERT OR REPLACE` bypasses DELETE triggers by default (verified).
**Do this instead:** Layer the defences: app has no update/delete paths, triggers (including the REPLACE guard), privileges, `UNIQUE(prev_hash)`, hash chain, and a public git witness plus `verify` in CI.

### Anti-Pattern 7: Live API as the only data path for the site
**What people do:** Next.js fetches Supabase or FastAPI at request time.
**Why it's wrong:** Free-tier pausing, cold starts and CORS issues mean "The Record" goes blank exactly when someone checks it.
**Do this instead:** Make static export the default, keep the API optional, and use the same schema for both.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Supabase Postgres | SQLAlchemy via **Session pooler** from Actions (IPv4) | Free tier pauses after ~1 week of low activity, so daily collector writes keep it alive; use a non-exposed schema or RLS |
| GitHub Actions | cron (UTC), `concurrency: ledger`, secrets for `DATABASE_URL` | Public repos: schedules auto-disable after 60 days of no repo activity; daily export commits prevent it; add `workflow_dispatch` to every workflow |
| Vercel | Git-push deploys of `/web` (root directory = `web`) | Static data from `public/data`; optional second project for FastAPI (Python runtime, zero-config) |
| Google Trends | pytrends (archived Apr 2025) behind a `TrendsClient` interface | Swap-able for the alpha official API or trendspyg; vintaged pulls; seed CSV fallback |
| NSE/BSE filings, GST releases | httpx collectors + seed CSVs | `available_at` from filing/release timestamps; conservative rules when unknown |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `pitdata` ↔ `nowcaster` | Direct Python import, one-way (`nowcaster → pitdata`) | Enforce with import-linter; `pitdata` must not know companies or models |
| `features` ↔ DB | Only via `PointInTimeReader` | No engine/session imports in `features/`, `models/`, `backtest/` |
| `ledger` ↔ everything | `ledger.append(payload)` is the sole writer to `predictions` | Single transaction: read head → build payload → insert; DB uniqueness catches races |
| `api` ↔ DB | Read-only role / SQLite `mode=ro` | No POST/PUT/PATCH/DELETE routes; a test asserts this from `app.routes` |
| `export` ↔ `web` | Files in `web/public/data/v1` + `openapi.json` | TS types generated; schema snapshot test fails on unannounced contract changes |
| Python ↔ JS hashing | `tests/fixtures/hash_vectors.json` | Both test suites must pass on the same vectors; include edge cases (zero, negative, rounding half-even, max seq) |

---

## Sources

- Local verification (HIGH): Python 3 `json.dumps(sort_keys, separators, ensure_ascii)` and Node WebCrypto `crypto.subtle.digest` produced identical SHA-256 for the v1 payload. `Date.toISOString()` adds `.000Z`. SQLite 3.50.4: `INSERT OR REPLACE` bypasses BEFORE DELETE triggers unless `recursive_triggers=ON`, and a BEFORE INSERT existence guard blocks it.
- [RFC 8785: JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785): number serialisation follows ECMAScript, which is the reason for the all-string payload choice (MEDIUM)
- [MDN: SubtleCrypto.digest()](https://developer.mozilla.org/docs/Web/API/SubtleCrypto/digest), [caniuse secure-context](https://caniuse.com/mdn-api_subtlecrypto_secure_context_required): secure context required (MEDIUM)
- [PostgreSQL trigger definition docs](https://www.postgresql.org/docs/19/trigger-definition.html), [Neon: BEFORE TRUNCATE trigger](https://neon.com/postgresql/triggers/before-truncate-trigger), [django-pgtrigger cookbook](https://django-pgtrigger.readthedocs.io/en/4.8.0/cookbook/): TRUNCATE bypasses row triggers and needs a statement-level guard (MEDIUM)
- [Supabase: Project pausing](https://supabase.com/docs/guides/platform/free-project-pausing), [Supabase pricing](https://supabase.com/pricing): free tier pauses after ~1 week of inactivity (MEDIUM)
- [Supabase: IPv4/IPv6 compatibility](https://supabase.com/docs/guides/troubleshooting/supabase--your-network-ipv4-and-ipv6-compatibility-cHe3BP), [Supabase: Connecting to Postgres](https://supabase.com/docs/guides/database/connecting-to-postgres): GitHub Actions is IPv4-only, so use the session pooler (MEDIUM)
- [Vercel: Zero-config backends](https://vercel.com/blog/zero-config-backends-on-vercel-ai-cloud), [Vercel FastAPI guide](https://vercel.com/kb/guide/ship-a-fastapi-app-on-vercel), [Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python) (MEDIUM)
- [GitHub Docs: Disable and enable workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows): 60-day auto-disable for public repos (MEDIUM)
- [Google Trends API (alpha) announcement](https://developers.google.com/search/blog/2025/07/trends-api), [SerpApi: Trends 0–100 explained](https://serpapi.com/blog/google-trends-numbers-from-0-to-100-what-is-it.md): window-relative normalisation and sampling (MEDIUM/LOW for sampling magnitude)
- [pytrends archived (secondary reports)](https://apiserpent.com/blog/pytrends-dead-google-trends-data-2026): archived 17 Apr 2025 (LOW-MEDIUM; confirm on GitHub)
- [Business Today: DMART Q3 FY26 business update (5 Jan 2026)](https://www.businesstoday.in/markets/stocks/story/avenue-supermarts-q3-revenue-rises-13-despite-cautious-sentiment-margin-pressures-509380-2026-01-05), [Business Today: Q3 results (10 Jan 2026)](https://www.businesstoday.in/latest/corporate/story/d-mart-q3-results-standalone-net-profit-rises-176-yoy-to-rs-923-crore-revenue-up-132-510319-2026-01-10): reveal precedes results by about a week (MEDIUM)
- Training knowledge, not re-verified this session (flag as MEDIUM): uv workspaces, SQLAlchemy TypeDecorator / Alembic batch mode, Hypothesis, scikit-learn Pipeline, Supabase Data API exposure of the `public` schema

---
*Architecture research for: alternative-data revenue nowcaster with point-in-time store and verifiable append-only ledger*
*Researched: 2026-11-17*
