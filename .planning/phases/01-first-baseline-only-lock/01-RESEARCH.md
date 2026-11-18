# Phase 1: First Baseline-Only Lock - Research

**Researched:** 2026-11-18
**Domain:** Point-in-time data store, leakage-proof baseline, append-only hash-chained ledger on SQLite + Supabase Postgres, git + OpenTimestamps witnessing via GitHub Actions
**Confidence:** MEDIUM-HIGH (OpenTimestamps, SQLite trigger behaviour, cross-language hashing and Windows pitfalls were verified by running code this session; Postgres/Supabase trigger behaviour is CITED from docs but not executed; Linux `ots` CLI behaviour on the Actions runner is ASSUMED until the D-21 rehearsal)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Setup facts (from the user)
- **D-01:** GitHub remote is `https://github.com/KASHITOp/called-it.git` (public). Add it as `origin`. `gh` CLI is already authenticated.
- **D-02:** `.env` already exists with `DATABASE_URL` (Supabase **session pooler**). Never overwrite it, never commit it, never print its value. Add a `.env.example` with a placeholder only.
- **D-03:** Run `git check-ignore .env` before the first push and confirm it is ignored. Note: at session start `git status` showed `.gitignore` as **untracked** (`?? .gitignore`), so the plan must commit `.gitignore` before anything else is pushed.

#### Baseline-v1 (frozen into PREREGISTRATION.md)
- **D-04:** Baseline = revenue(same quarter last year) × (1 + g), where g is **TTM YoY**: the sum of the last 4 revealed quarters ÷ the sum of the 4 quarters before them, − 1. "Revealed" means `reveal_at < as_of`. For the Q3 FY27 lock: same-quarter-last-year = Q3 FY26, TTM = (Q3 FY26..Q2 FY27) ÷ (Q3 FY25..Q2 FY26). — **Reversibility:** one-way — hashed into the ledger before the first lock; changing it means a new, visible rules record and a new baseline version.
- **D-05:** Baseline inputs use the **latest vintage known at as_of** (`available_at < as_of`), so restatements published before the lock are used. Grading still uses first-reported actuals (D-13). — **Reversibility:** one-way — part of the frozen baseline definition.
- **D-06:** **Eternal break treatment (FEAT-02).** The break is declared in config as a quarter **range**, pinned from Eternal's filings or shareholder letters with the source cited in config. If any quarter in the TTM window falls inside or straddles the break range, the baseline instead uses the single-quarter YoY of the latest quarter pair (t, t−4) where both quarters are post-break. If no such pair exists, it uses the least-straddling pair. Proposed definition: the most recent revealed pair, i.e. the one with the latest base quarter. Show it to the user in PREREGISTRATION.md before the freeze. Eternal's call always carries a hashed label `"low confidence: post-break comparables limited"`. — **Reversibility:** one-way — FEAT-02 requires its SHA-256 in the ledger before the first lock.
- **D-07:** **GST 2.0 and the baseline:** flag it, don't adjust it. The baseline maths ignores GST 2.0, but each lock's hashed payload records when its TTM window straddles the GST 2.0 marker (22 Sep 2025), e.g. a `breaks_in_window` field. The GST 2.0 *feature* treatment stays open until FEAT-03 (Phase 3), and PREREGISTRATION.md must say "GST 2.0 treatment: deferred to FEAT-03" explicitly.
- **D-08:** **Missing-quarter rule.** If any seed quarter needed for a company's lock is missing (or unverified, see D-22), that company's lock is **refused and recorded as a visible gap**. Nothing is ever imputed, estimated or interpolated. — **Reversibility:** one-way — a preregistered rule.

#### Grading rules (LEDG-07, frozen into PREREGISTRATION.md)
- **D-09:** **CALLED IT** = |error| ≤ 3% against the first-reported actual. A model call must *also* have the actual inside its 80% interval. A baseline-only call needs only |error| ≤ 3%. Anything else is **MISSED**. — **Reversibility:** one-way — hashed before the first lock.
- **D-10:** error = (predicted − actual) / actual, stored **signed**. The stamp compares |error|. "MISSED (by X%)" shows |error| plus a direction: **over** or **under**.
- **D-11:** **Beat baseline** = |model error| < |baseline error| on the same company's official call for the same quarter. A **tie is NOT beaten**. For baseline-only official calls, beat-baseline is N/A.
- **D-12:** **Interval for baseline-only locks:** none. `low_cr` and `high_cr` are null, and the payload labels the interval as "none (baseline-only, no out-of-sample residuals yet)". The inside-interval grade is N/A.
- **D-13:** Grading always uses the **first-reported** consolidated revenue from operations in the results filing, as reported (never Eternal's "adjusted revenue"). Later restatements are shown but never re-grade.
- **D-14:** **Lock deadline.** A lock at or after `earliest_plausible_reveal` (config: quarter end + N days at 00:00 IST, with DMART +1, TITAN +2, ETERNAL +7) is **refused**. If the actual `reveal_at` turns out to be even earlier, any lock at or after it is marked **VOID at grading**. That is derived state, so the predictions row is never mutated, and the lock is shown greyed out, never hidden. The official call is the last non-VOID lock before `reveal_at`, derived and never a flag. `predict --quarter Q2FY27` (already revealed) is refused. No command can lock at a past time.
- **D-15:** **Headline scoring uses official calls only.** The stamp and the headline MAPE use each company's official call. Every weekly lock is still graded and kept in the convergence history. A company with no valid lock before its reveal shows **"NO OFFICIAL CALL"** and counts as a published miss, never a silent omission.

#### Ledger home & witnesses
- **D-16:** **System of record:** Supabase Postgres `predictions` in a private `calledit` schema, not exposed through PostgREST, with RLS on and no anon policies, guarded by the append-only triggers. Every lock exports `ledger.jsonl`, which is committed to git and OTS-stamped as the public witness. SQLite is for local dev and tests only. — **Reversibility:** costly — moving the system of record later means migrating a hash-chained ledger and re-explaining provenance.
- **D-17:** **Fail loudly.** If Supabase is unreachable at lock time (for example a free-tier pause), the lock fails with a non-zero exit and a visible alert (a failed Actions run). It **never** silently falls back to SQLite.
- **D-18:** **Lock runner:** a GitHub Actions `workflow_dispatch` workflow runs `nowcast predict`, exports and commits `ledger.jsonl`, and stamps OTS. Its run log is an extra server-side timestamp witness. The user adds `DATABASE_URL` as a repo secret themselves, and plans must give the exact steps without ever echoing the value.
- **D-19:** **Preregistration:** a single committed `PREREGISTRATION.md` covering the universe, baseline-v1 (D-04..D-08), the Eternal treatment, the grading rules (D-09..D-15), the official-call and deadline rules, the missing-quarter rule, and "GST 2.0: deferred to FEAT-03". Its SHA-256 goes into a **rules** record at **seq 0** of the ledger hash chain, OTS-stamped before any prediction. Any later change is a new, visible rules record and never an edit.
- **D-20:** **OTS details.** Stamp the **chain head hash** (the latest record's hash), not the whole file. Because every record links to the one before, the head covers the full history. Proofs live at `ledger/proofs/<seq>.ots`, committed alongside `ledger.jsonl`. Pending proofs are upgraded with `ots upgrade` until Bitcoin confirms them. In Phase 2 that runs in each daily cron. In Phase 1 the upgrade is run manually or by dispatch so the success criterion ("within a day, `ots verify` accepts") is met.
- **D-21:** **Timing.** First run a full dress rehearsal of the dispatch workflow against a **scratch** Supabase schema and a scratch ledger file, then discard it. The rehearsal must never write to the live `calledit` schema or the published `ledger.jsonl`. The live lock targets **~28 Nov 2026**, about 3 days of slack before the 1 Dec deadline for a failed run or a slow OTS confirmation.

#### Seed CSV sourcing (DATA-01)
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

### Deferred Ideas (OUT OF SCOPE)
- **Supabase reachability heartbeat:** the weekly-lock heartbeat checks Supabase is reachable a day before each final lock. This is a user requirement for Phase 2 (OPS-02).
- **Daily `ots upgrade` in cron:** Phase 2 (daily collection workflow). In Phase 1 it is run manually or by dispatch.
- **Seed history back to ~Q3 FY23 (12-16 quarters):** filled during Phase 2, ready for the Phase 3 backtest (BACK-01).
- **GST 2.0 treatment:** Phase 3 (FEAT-03), frozen before the first model lock (~15 Dec).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description (abridged from REQUIREMENTS.md) | Research Support |
|----|-------------|------------------|
| FOUND-01 | One-command backend setup (uv workspace, Py 3.12, `/data` `/nowcaster` `/web` `/tests` `/.github/workflows`) | §Standard Stack, §Pattern 1 (workspace layout), §Environment Availability (uv not installed yet) |
| FOUND-03 | Company add/remove/disable via one config file | §Pattern 2 (`config/universe.toml`, pydantic-validated), verified Apple app IDs |
| FOUND-04 | SQLite/Postgres switch via `DATABASE_URL`, Alembic migrations | §Pattern 3 (settings + engine + schema translate), Pitfalls 1, 5, 9 |
| FOUND-05 | Indian fiscal labels ⇄ dates, unit-tested | §Pattern 4, §Code Examples (fiscal) |
| PIT-01 | `period_date`, `available_at`, `ingested_at`, source, availability basis on every row | §Pattern 5 (observations schema), UTCDateTime |
| PIT-02 | Insert-only store, revisions as new rows | §Pattern 5 + §Pattern 8 (triggers applied to `observations` too) |
| PIT-03 | Single `PointInTimeReader(as_of)` (strict `<`; live adds `ingested_at <= as_of`) | §Pattern 6, §Code Examples |
| PIT-04 | Reveal calendar: `business_update_at`, `results_at`, `reveal_at = min`, status, earliest plausible reveal | §Pattern 5 (`reveal_events`), Pitfall 3 (early vs late bound) |
| PIT-05 | Structural breaks (Eternal range, GST 2.0 22 Sep 2025) in config | §Pattern 2, §Pattern 7 |
| LEAK-01 | Property test: perturbing rows with `available_at >= cutoff` leaves outputs bit-identical | §Pattern 9 (hypothesis), Pitfall 7 |
| LEAK-02 | Leaky reader makes the suite fail | §Pattern 9 (`--reader` option + subprocess meta-test asserting exit code 1) |
| LEAK-03 | IST/UTC boundary + strict `<` tests | §Pattern 4, §Code Examples, Pitfall 4 (Windows tzdata) |
| LEAK-04 | Reveal-keyed expanding-window splitter + test | §Pattern 9 (splitter), §Validation map |
| DATA-01 | Seed CSV with validation + fill-in instructions | §Pattern 5, §Pattern 10 (seed loader), Pitfalls 3, 11 |
| FEAT-02 | Eternal break treatment frozen, SHA-256 in ledger before first lock | §Pattern 7, §Pattern 11 (rules record seq 0) |
| BASE-01 | Baseline = SQLY × (1 + TTM YoY), break-aware, PIT-only | §Pattern 7, §Code Examples (Decimal) |
| LEDG-01 | `predictions` table columns | §Pattern 8 (table DDL) |
| LEDG-02 | `calledit-ledger-v1` canonical spec + golden vectors in Python and JS | §Pattern 8, verified Python⇄Node hash equality |
| LEDG-03 | Hash chain; fork rejected | §Pattern 8 (`UNIQUE(prev_hash)` + app head check) |
| LEDG-04 | Triggers blocking UPDATE/DELETE/REPLACE/TRUNCATE on both backends, tested | §Pattern 8, verified SQLite bypass matrix, PG `ENABLE ALWAYS` |
| LEDG-05 | `nowcast predict --quarter Q3FY27` locks; late/backfilled locks refused; gaps visible | §Pattern 11 (lock guard), §Pattern 12 (workflow) |
| LEDG-07 | Grading rules published and hashed before first lock | §Pattern 11 (PREREGISTRATION.md → rules record) |
| LEDG-09 | Each lock run commits `ledger.jsonl` to GitHub | §Pattern 12 |
| LEDG-10 | OpenTimestamps anchoring, proofs stored and upgraded | §Pattern 13 (verified OTS behaviour), Pitfall 2 (Windows crash), Open Question 1 (`ots verify` needs a Bitcoin node) |
</phase_requirements>

## Summary

Phase 1 is a greenfield walking skeleton whose real product is a set of **one-way doors**: the canonical hash spec, the record kinds and field sets, the baseline-v1 definition, the grading rules, the Eternal break range, the reveal offsets, the ledger file format, line endings of every hashed file, the Supabase schema name and the git default branch. Every one of these becomes permanent the moment seq 0 is written to Supabase and pushed to the public repo, so the plan must freeze them deliberately and in order: scaffold → store/reader → leakage suite → ledger + triggers + golden vectors → seed CSV (verified by the user) → PREREGISTRATION.md review → rehearsal → rules record (seq 0) → live lock (~28 Nov) → OTS upgrade.

Three findings this session change how the plan should be built. **(1) The `ots` CLI crashes on Windows at import** (python-bitcoinlib loads OpenSSL via ctypes and finds none), so stamping and upgrading must run on the ubuntu Actions runner (which D-18 already requires). The `opentimestamps` *library* imports fine on Windows, and all four public calendars accepted a test stamp from this machine. **(2) `ots verify` exits 1 unless it can reach a local Bitcoin Core node.** The success criterion "`ots verify` accepts" therefore needs either a node or an honest substitute: `ots --no-bitcoin verify` prints the block height and merkle root, which a small script cross-checks against two independent block explorers (both endpoints verified live). This needs user confirmation. **(3) The current `.env` is not usable as written.** It has no `DATABASE_URL=` key, and the URL does not parse. The password portion contains URL-reserved characters/brackets that are not percent-encoded. The user must fix it (D-02 forbids the plan from overwriting it).

The rest of the design is well-trodden. Use SQLAlchemy Core and hand-written Alembic migrations, with trigger DDL per dialect. SQLite needs the extra BEFORE INSERT REPLACE guard; its bypass matrix was verified this session on SQLite 3.50.4. Postgres needs a `BEFORE TRUNCATE` statement trigger and `ENABLE ALWAYS` so that `session_replication_role=replica` cannot skip the triggers. Payloads contain only strings and are serialised by `json.dumps(sort_keys, compact)`; this session verified that Python, Node 24 WebCrypto and the OTS file digest all produce the same SHA-256. Hypothesis drives the future-perturbation invariance test, and a subprocess meta-test proves the leaky readers make the suite fail with pytest exit code 1.

**Primary recommendation:** Build the ledger so that **each line of `ledger/ledger.jsonl` is exactly a record's `payload_canonical`**, with `prev_hash` inside the payload and hash = SHA-256 of the line bytes. Then the git witness, the OTS proof (stamp a file containing exactly the head line, so the OTS digest equals the head hash) and the future browser verifier all check the same bytes. Freeze `.gitattributes` (`-text` on hashed files) *before* the first hashed file is committed.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Fiscal calendar, IST/UTC conversion | `calledit_data` library (pure functions) | — | Shared by the later vol-engine and terminal; no I/O |
| Observation store + reveal events (insert-only) | Database (SQLite dev / Supabase PG prod) | `calledit_data.store` writer | Immutability is enforced at the DB (triggers) and in code (no update/delete paths) |
| Point-in-time read gate | `calledit_data.pit` (`PointInTimeReader`) | Database (SQL filter) | The only read path for model-facing code; the post-condition assert lives in Python |
| Company universe + breaks + reveal offsets | Config file (`config/universe.toml`) | `nowcaster.universe` (pydantic) | FOUND-03: edit config, no code change |
| Baseline-v1 computation | `nowcaster.baseline` (pure, Decimal) | — | Deterministic, recomputable from the hashed snapshot |
| Canonicalisation + hashing | `nowcaster.ledger.canonical` (Python) + `web/src/lib/canonical.ts` (JS) | `tests/fixtures/hash_vectors.json` | Shared golden vectors stop drift |
| Ledger append + chain + lock guard | `nowcaster.ledger` + `nowcaster.lock` | Database (UNIQUE + triggers) | One writer; the DB rejects forks and mutations |
| Lock execution, witness commit, OTS stamping/upgrade | GitHub Actions (ubuntu runner, `workflow_dispatch`) | git remote (public repo), OTS calendars | Server-side timestamp; the `ots` CLI cannot run on Windows |
| Seed data curation | Human (user verifies PDFs) | `nowcast seed load --dry-run` validator | Data ethics: no exchange automation |
| JS golden-vector check | `web/` (Node built-in test runner) | — | Phase 5 reuses `canonical.ts` in the browser |

## Standard Stack

### Core (Phase 1 only — install nothing that Phase 1 does not use)

| Library | Version (PyPI, checked 2026-11-18) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12 (via `.python-version`; uv-managed) | Runtime | numpy 2.5.5 requires `>=3.12` [VERIFIED: PyPI JSON `requires_python`]; project decision in CLAUDE.md |
| uv | 0.13.9 (released 2026-11-17) | Workspace, lockfile, `uv sync`, `uv run` | User-fixed [VERIFIED: PyPI JSON] |
| uv_build | `>=0.13.9,<0.14` | Build backend for members | Upper bound recommended by uv docs [CITED: docs.astral.sh/uv/concepts/build-backend] |
| SQLAlchemy (Core) | 2.1.9 | Dialect-portable DDL/DML | One code path for SQLite + PG [VERIFIED: PyPI JSON, py>=3.11] |
| Alembic | 1.20.1 | Migrations incl. triggers | [VERIFIED: PyPI JSON] |
| psycopg (`psycopg[binary]`) | 3.3.9 | Postgres driver (`postgresql+psycopg://`) | cp312 win_amd64 + manylinux wheels exist [VERIFIED: PyPI file list] |
| pydantic | 2.14.3 | Config, seed-row and payload validation | [VERIFIED: PyPI JSON] |
| pydantic-settings | 2.16.3 | `DATABASE_URL`, `CALLEDIT_ENV`, `CALLEDIT_DB_SCHEMA` | [VERIFIED: PyPI JSON] |
| typer | 0.29.1 | `nowcast` CLI | User-fixed [VERIFIED: PyPI JSON] |
| tzdata | 2026.6 | IANA tz database on Windows | A clean Windows venv has **no** tz database: `zoneinfo.ZoneInfo('Asia/Kolkata')` raised `ZoneInfoNotFoundError` this session [VERIFIED: local run] |
| stdlib `hashlib`, `json`, `decimal`, `csv`, `tomllib`, `datetime` | stdlib | SHA-256, canonical JSON, money, CSV, config, time | No dependency needed |

### Testing

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.2.0 | Test runner | All tests [VERIFIED: PyPI JSON] |
| hypothesis | 6.170.15 | Property tests (LEAK-01, fiscal round-trips, splitter) | [VERIFIED: PyPI JSON] |
| time-machine | 3.6.0 | Freeze "now" for lock-guard tests | Has a cp312 win_amd64 wheel [VERIFIED: PyPI file list] |
| Node built-in `node:test` + global WebCrypto | Node 24.21.0 (installed) | JS golden-vector test, no npm dependencies | Ran a `.test.ts` file with native type stripping this session and got the Python hash [VERIFIED: local run] |

### OTS (CI-only dependency group)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| opentimestamps-client | 0.8.0 (2026-10-27, requires py>=3.11) | `ots stamp / upgrade / verify / info` | **Linux Actions runner only.** Put it in a non-default dependency group `ots`, so `uv sync` on Windows does not need it [VERIFIED: PyPI JSON; crash on Windows verified locally] |
| opentimestamps | 0.5.0 (pulled in by the client) | Proof parsing for the explorer cross-check script | Imports fine on Windows [VERIFIED: local run] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| All-string payload + `json.dumps` | `rfc8785` (JCS) | Not needed: no numbers, booleans or nulls means no JCS number rules apply. That is one fewer dependency on both sides |
| pandas in the reader | Typed rows (frozen dataclasses with `Decimal`) | Phase 1 needs exact Decimal equality for "bit-identical" and hashing; floats in a DataFrame would break both. Add a `.to_frame()` helper in Phase 3 |
| vitest for `web/` | `node --test` | vitest arrives with Next.js in Phase 5; Node 24 runs TS tests natively today with zero installs |
| `ots` CLI for stamping | `opentimestamps` library (`RemoteCalendar.submit`) | Fallback only, if the CLI fails on the runner. A library stamp from Windows was verified this session, but upgrade logic would have to be re-implemented, so keep the CLI as primary |
| Bitcoin Core node for `ots verify` | Explorer cross-check (blockstream.info + mempool.space Esplora APIs) | A node is the only trust-minimised verify. Explorers are "trust two third parties". See Open Question 1 |
| Supabase scratch schema for PG tests | `postgres:17` service container in a CI workflow | No Docker on this machine. The CI container is the cleaner option and Phase 2 (OPS-03) needs it anyway |

**Installation (root `pyproject.toml` drives it; one command after uv is installed):**
```bash
# one-time on Windows (official installer) if uv is missing:
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv sync            # installs Python 3.12 (managed), both members, dev group
uv sync --group ots   # CI runner only
```

## Package Legitimacy Audit

Ran `gsd-tools query package-legitimacy check --ecosystem pypi …` on 2026-11-18. The seam rated **every** package `SUS` for the reasons `too-new` and `unknown-downloads`. Its `publishedAt` signal is the *latest release* date (for example SQLAlchemy `2026-11-16`), not project age, and it has no PyPI download counts. The project ages and source repos below come from the PyPI JSON first-upload dates.

| Package | Registry | Age (first upload) | Downloads | Source Repo | Verdict (seam) | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| sqlalchemy | PyPI | 2006-02-14 (344 releases) | n/a (seam) | github.com/sqlalchemy/sqlalchemy | SUS | Flagged — one consolidated `checkpoint:human-verify` |
| alembic | PyPI | 2011-11-30 | n/a | github.com/sqlalchemy/alembic | SUS | Flagged (same checkpoint) |
| psycopg | PyPI | 2021-08-30 | n/a | github.com/psycopg/psycopg | SUS | Flagged |
| pydantic | PyPI | 2017-05-03 | n/a | github.com/pydantic/pydantic | SUS | Flagged |
| pydantic-settings | PyPI | 2019-08-19 | n/a | github.com/pydantic/pydantic-settings | SUS | Flagged |
| typer | PyPI | 2019-12-20 | n/a | github.com/fastapi/typer | SUS | Flagged |
| pytest | PyPI | 2010-11-25 | n/a | github.com/pytest-dev/pytest | SUS | Flagged |
| hypothesis | PyPI | 2013-03-10 | n/a | github.com/HypothesisWorks/hypothesis | SUS | Flagged |
| time-machine | PyPI | 2020-05-04 | n/a | github.com/adamchainz/time-machine | SUS | Flagged |
| tzdata | PyPI | 2016-08-20 | n/a | github.com/python/tzdata | SUS | Flagged |
| ruff | PyPI | 2022-08-27 | n/a | github.com/astral-sh/ruff | SUS | Flagged (dev only) |
| opentimestamps-client | PyPI | 2017-08-26 | n/a | github.com/opentimestamps/opentimestamps-client | SUS | Flagged; CI-only group |
| opentimestamps | PyPI | 2017-08-26 | n/a | github.com/opentimestamps/python-opentimestamps | SUS | Flagged (transitive) |
| pandas | PyPI | 2009-12-25 | n/a | github.com/pandas-dev/pandas | SUS | **Not needed in Phase 1** (recommend not installing) |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** all of the above, every one because of the seam's latest-release-date heuristic. None of the packages is new, and no postinstall scripts apply (PyPI). **Recommendation:** add **one** `checkpoint:human-verify` before the first `uv sync`. In it, the user reviews the pinned dependency list in the root and member `pyproject.toml` files against this table. After that, `uv sync --locked` in CI enforces the reviewed lockfile hashes.
*The package names come from CLAUDE.md's project stack (verified against PyPI in project research) and from the official `opentimestamps` GitHub organisation.*

## Architecture Patterns

### System Architecture Diagram

```
 human (user)                         GitHub Actions (ubuntu, workflow_dispatch, concurrency: ledger)
 ───────────                          ───────────────────────────────────────────────────────────────
 filing PDFs ──► data/seed/            checkout ─► uv sync --locked --group ots
 quarterly_revenue.csv (verified=Y)      │
        │                                ▼
        ▼                             nowcast db check ──(fail: missing/disabled trigger,
 nowcast seed load [--dry-run]           │               replica role, wrong schema) ──► exit≠0
   validate whole file ─(any error)─► abort, list errors, insert nothing
        │ ok                             ▼
        ▼                             nowcast predict --quarter Q3FY27
 ┌──────────────── DATABASE (SQLite dev │ Supabase PG prod, schema calledit) ───────────────┐
 │ series · observations (insert-only) · reveal_events (insert-only)                          │
 │            │                                                                               │
 │            ▼ SELECT … WHERE available_at < :as_of [AND ingested_at <= :as_of]              │
 │      PointInTimeReader(as_of=locked_at) ──► latest vintage per period ──► assert < as_of   │
 │            │                                                                               │
 │            ▼                                                                               │
 │  lock guard: as_of < earliest_plausible_reveal? no reveal_event ≤ as_of? quarter live?     │
 │    │ refuse → gap record (D-08) / non-zero exit (D-14)                                     │
 │    ▼ pass                                                                                  │
 │  baseline_v1(ticker, Q, reader, universe)  ──► (point, growth, method, snapshot)           │
 │    │  break-aware (D-06), flags breaks_in_window (D-07)                                    │
 │    ▼                                                                                       │
 │  canonical payload (prev_hash = head.hash) ─► sha256 ─► INSERT predictions (1 txn)         │
 │  triggers: no UPDATE/DELETE/TRUNCATE/REPLACE · UNIQUE(seq), UNIQUE(hash), UNIQUE(prev_hash)│
 └────────────────────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
 nowcast ledger export ─► ledger/ledger.jsonl (one payload_canonical per line, LF)
        │                  ledger/snapshots/<seq>.json ; assert old file is a byte-prefix
        ▼
 write head line bytes to <tmp>/<seq> ─► ots stamp ─► mv → ledger/proofs/<seq>.ots (pending)
        │                                   (≥2 of 4 calendars must answer, else exit 1)
        ▼
 git commit + push to origin/main ──► public witness (commit + Actions run log)
        ⋮  (hours later, second dispatch: action=upgrade)
 ots upgrade ledger/proofs/<seq>.ots ─► rm *.bak ─► commit ─► explorer cross-check / ots verify
```

### Recommended Project Structure

```
called-it/
├── pyproject.toml            # root: name "called-it", [tool.uv] package=false, deps on both members, dev + ots groups
├── uv.lock
├── .python-version           # 3.12
├── .gitattributes            # -text on hashed files, binary on *.ots  (commit BEFORE any hashed file)
├── .env.example              # DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres (placeholder)
├── PREREGISTRATION.md        # frozen rules (D-19); hashed into seq 0
├── alembic.ini
├── config/universe.toml      # FOUND-03 single config file
├── data/                     # workspace member "calledit-data" → import calledit_data
│   ├── pyproject.toml
│   ├── seed/quarterly_revenue.csv, seed/README.md (fill-in instructions)
│   ├── migrations/ (env.py, versions/0001_*.py …)   # hand-written, no batch mode
│   └── src/calledit_data/ db/ (settings, engine, types) · calendar/ (fiscal, tz) · store/ · pit/ · seed/
├── nowcaster/                # workspace member "called-it-nowcaster" → import nowcaster
│   ├── pyproject.toml        # [tool.uv.build-backend] module-name = "nowcaster"; [project.scripts] nowcast
│   └── src/nowcaster/ universe.py · baseline.py · splits.py · ledger/ (canonical, chain, export) · lock.py · cli.py
├── ledger/ledger.jsonl, ledger/snapshots/<seq>.json, ledger/proofs/<seq>.ots
├── scripts/ots_explorer_check.py
├── tests/ conftest.py · fixtures/hash_vectors.json · leakage/ · ledger/ · data/ · meta/
├── web/ package.json ("test": "node --test") · src/lib/canonical.ts · tests/canonical.test.ts
└── .github/workflows/lock.yml   (and optionally ci-postgres.yml)
```

### Pattern 1: uv workspace with a non-package root

**What:** The root `pyproject.toml` is a project with `[tool.uv] package = false` that depends on both members through `[tool.uv.sources] x = { workspace = true }`. Plain `uv sync` at the root then installs both members (editable) plus the `dev` group. uv docs say `uv sync` "operate[s] on the workspace root by default" and that "Dependencies between workspace members are editable" [CITED: docs.astral.sh/uv/concepts/projects/workspaces]. Making the root depend on both members avoids relying on virtual-root semantics.
**Gotcha:** uv_build infers the module name from the project name ("lowercased and dots and dashes are replaced with underscores") [CITED: docs.astral.sh/uv/concepts/build-backend]. `called-it-nowcaster` would therefore look for `src/called_it_nowcaster/`. Set `[tool.uv.build-backend] module-name = "nowcaster"`. `calledit-data` maps to `calledit_data` without any setting.
**`[dependency-groups]`:** `dev = [pytest, hypothesis, time-machine, ruff]`. `ots = ["opentimestamps-client==0.8.0"]` is not in default groups, so it installs only with `uv sync --group ots`.

### Pattern 2: Universe config (`config/universe.toml`, `tomllib` + pydantic)

Fields per company (FOUND-03 list): `ticker`, `isin`, `name`, `enabled`, `revenue_basis = "consolidated_revenue_from_operations"`, `reveal_offset_days`, `has_business_update`, `gst_states`, `trends_terms`, `apple_app_ids`, `play_package_ids`, `breaks = [...]`. Global breaks hold the GST 2.0 marker (`effective = 2025-09-22`). The Eternal break is `{id, start_q, end_q, source_url, source_note}`, a quarter **range** (D-06).
- Reveal offsets are locked as DMART +1, TITAN +2, ETERNAL +7 (D-14).
- Apple App Store IDs, from the official iTunes Search API with `country=in`: Zomato `434613896`, Blinkit `960335206`, District `6670536058`, Tanishq `1494086207`, CaratLane `990574630`, DMart Ready `1121933197`. In each case the seller name matched the company or its subsidiary [VERIFIED: itunes.apple.com/search, 2026-11-18].
- ISINs: DMART `INE192R01011` [CITED: Kotak/IDFC approved-securities lists]. Eternal `INE758T01015` and Titan `INE280A01028` are [ASSUMED]; the user verifies them from a filing header.
- `nowcast universe` prints all of these, including disabled companies marked `disabled`. `predict` iterates `enabled` companies only.
- Hash the config's bytes (`universe_sha256`) into every prediction payload, so a later edit (for example disabling a company) is visible in the chain.

### Pattern 3: One flag, two backends, schema isolation

- `Settings` (pydantic-settings, `.env`): `database_url` (default `sqlite:///data/local.db`), `calledit_env ∈ {dev, test, rehearsal, live}`, `db_schema` (PG only; default `calledit`; rehearsal `calledit_rehearsal`; tests `calledit_test_<hex>`). Validate the identifier with `^[a-z_][a-z0-9_]{0,62}$`.
- **Normalise the URL scheme** in a validator: `postgresql://` and `postgres://` become `postgresql+psycopg://`. Whether SQLAlchemy 2.1's default PG driver is psycopg2 or psycopg is unverified [ASSUMED]; being explicit removes the question.
- **Live guard (D-17):** `calledit_env=live` requires a postgres URL and refuses SQLite. Any connection failure must raise and exit non-zero; never fall back.
- App tables are defined with `schema=None`. On PG, the engine uses `execution_options(schema_translate_map={None: settings.db_schema})`. Migrations call `op.create_table(..., schema=S)` explicitly. Raw trigger SQL is formatted with the validated identifier. Alembic uses `version_table_schema=S`. Alembic's own multi-tenant recipe is described as "interim" and relies on `set search_path` plus a "non-supported SQLAlchemy workaround" [CITED: alembic.sqlalchemy.org/en/latest/cookbook.html]. Prefer explicit qualification, which also avoids depending on `search_path` behaviour through the pooler.
- SQLite `connect` event: `PRAGMA foreign_keys=ON; PRAGMA recursive_triggers=ON; PRAGMA journal_mode=WAL` (CLAUDE.md).

### Pattern 4: Fiscal calendar and time (pure functions)

- `FiscalQuarter(fy: int, q: int)`. Label `Q{q}FY{fy%100:02d}`. Parse is case-insensitive and allows an optional space ("Q3 FY27"). Accept 2000–2099 only.
- Q1 = Apr–Jun, Q2 = Jul–Sep, Q3 = Oct–Dec, Q4 = Jan–Mar. FY27 runs from 1 Apr 2026 to 31 Mar 2027 (PROJECT.md). `shift(n)` gives quarter arithmetic, and `t−4` is the same quarter one FY earlier.
- **IST as a fixed offset:** `IST = timezone(timedelta(hours=5, minutes=30), "IST")`. India has had no DST in the data range, and this needs no tz database. Keep `tzdata` installed anyway, and add a test that it agrees with `ZoneInfo("Asia/Kolkata")`.
- `earliest_plausible_reveal(company, Q) = datetime.combine(period_end(Q) + offset_days, time(0,0), IST).astimezone(UTC)`. For DMART Q3FY27 that is `2026-12-31T18:30:00Z` (matches ROADMAP "29 Dec 2026 18:30 UTC (30 Dec 00:00 IST)" arithmetic: 1 Jan 00:00 IST = 31 Dec 18:30 UTC).
- Feature/domain code never calls `datetime.now()`. The CLI layer gets `now_utc()` once, truncates it to whole seconds and passes it down. Add a static test (AST/grep) that bans `datetime.now`, `utcnow`, `date.today` and `time.time` outside `nowcaster/clock.py`.

### Pattern 5: Store schema (insert-only)

- `series(series_id PK, series_key UNIQUE, source, metric, entity, unit, frequency, collection_mode)`
- `observations(obs_id PK, series_id FK, period_date DATE, value DecimalText/NUMERIC(20,2), available_at UTCDateTime NOT NULL (no default), availability_basis TEXT NOT NULL, ingested_at UTCDateTime NOT NULL (set by writer, never server_default), vintage TEXT ('first_reported'|'restated'), source_ref TEXT NOT NULL, source_kind TEXT, content_hash TEXT NOT NULL, UNIQUE(series_id, period_date, available_at, content_hash))`
- `reveal_events(event_id PK, ticker, fiscal_quarter, event_kind ('business_update'|'results'), event_at, availability_basis, source_ref, ingested_at, content_hash UNIQUE)`
- A `reveal_calendar(ticker, Q)` function derives `business_update_at`, `results_at`, `reveal_at = min(...)`, status `confirmed` if any event exists (else `expected`) and `earliest_plausible_reveal` from config. It reads events through the PIT gate (an event is known only once `event_at < as_of`).
- Seed rows map to series `rev.consolidated.<TICKER>` (value at `results_at`) plus reveal events. The availability-basis strings are locked as `'exchange_timestamp'` and `'rule:date_eod_ist'` [VERIFIED: 01-CONTEXT.md:72 — "`availability_basis = 'exchange_timestamp'`" … "`availability_basis = 'rule:date_eod_ist'`"].
- Idempotent re-load: compute `content_hash` per row, insert only rows whose hash is absent, all in **one transaction**. Use no `ON CONFLICT`/`OR IGNORE` dialect branches. A restated figure (different value or `available_at`) is a new row.

### Pattern 6: `PointInTimeReader`

- Constructor asserts that `as_of` is tz-aware with UTC offset 0. `mode ∈ {"backtest", "live"}`.
- SQL: `available_at < :as_of`, plus `ingested_at <= :as_of` in live mode. Then, in Python, take the latest vintage per `period_date`. Sort key `(available_at, ingested_at, obs_id)` and take the last.
- **Post-condition (always on):** every returned row has `available_at < as_of`. On failure raise `LeakageError`.
- Return `tuple[Observation, ...]` (frozen dataclass, `Decimal` values), never floats.

### Pattern 7: Baseline-v1 (Decimal, break-aware)

- Inputs for target Q: SQLY = Q.shift(−4). Window A (recent) = Q.shift(−4..−1). Window B (prior) = Q.shift(−8..−5). For Q3FY27 these are A = Q3FY26..Q2FY27 and B = Q3FY25..Q2FY26, exactly D-04.
- **Usable quarter (recommend this precise wording for PREREGISTRATION):** a quarter's consolidated revenue observation exists with `available_at < as_of` (PIT reader), and its seed row is verified. D-04's "`reveal_at < as_of`" is necessary but not sufficient. For DMART and Titan, `reveal_at` is the *business update*, while the consolidated value only exists at `results_at`, which can be weeks later. Any needed quarter that is not usable means the lock is refused, with a gap record (D-08).
- Growth: `g = sum(A)/sum(B) − 1`, computed under `decimal.localcontext(prec=28, rounding=ROUND_HALF_EVEN)`. Point = `quantize(SQLY × (1+g), Decimal("0.01"), ROUND_HALF_EVEN)`. The payload carries `g` quantised to 6 dp *for display only*. State in PREREGISTRATION that the point is computed from unrounded `g`.
- Break-aware (D-06): classify each quarter as `pre`, `in` or `post` relative to the break range. If any of the 8 window quarters is `in`, or the window mixes pre and post, use a single pair: the latest pair (t, t−4) with both quarters `post` and both usable. Otherwise use the "least-straddling" pair, which is the most recent usable pair (D-06's proposed definition). Then g = rev(t)/rev(t−4) − 1. **Expectation to show the user:** if the range ends at or after Q3FY26, no fully post-break pair exists for the Q3FY27 lock, so Eternal falls to (Q2FY27, Q2FY26). That is still partly distorted, because Q2FY26 was about 80% inventory-led per secondary reporting [CITED: inc42.com, yourstory.com], which is why the low-confidence label is needed.
- Labels: the Eternal label is locked as `"low confidence: post-break comparables limited"` [VERIFIED: 01-CONTEXT.md:26 — "carries a hashed label `\"low confidence: post-break comparables limited\"`"].
- `breaks_in_window` (D-07): a sorted, `|`-joined list of break IDs whose effective date falls inside the span of the 8 window quarters (for example `gst2.0`, or `eternal-blinkit-inventory|gst2.0`). Use `none` if there are none. For the Q3FY27 window (Oct 2024–Sep 2026), GST 2.0 (22 Sep 2025) is inside, so every company's payload will carry it.
- `model_version = "baseline-sqly@1.0.0"` [VERIFIED: .planning/research/ARCHITECTURE.md:289 — "Use `baseline-sqly@1.0.0` for the naive model"].

### Pattern 8: Ledger — `calledit-ledger-v1`

**Canonicalisation (extends ARCHITECTURE.md Pattern 6 to nested snapshots):**
1. A value is a `str`, a `list` of values, or a `dict` with `str` keys. No numbers, booleans or nulls, ever. Keys match `^[a-z][a-z0-9_]*$`.
2. String characters must be printable ASCII `0x20–0x7E`, excluding `"` and `\`. Reject anything else (so `₹` is rejected and units live in field names such as `_inr_cr`).
3. Python: `json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)`. JS: a recursive serialiser that sorts keys and uses `JSON.stringify` on strings. With rule 2, neither side escapes anything, so the bytes are identical.
4. `hash = sha256(utf8(payload_canonical)).hexdigest()` (lowercase, 64 chars). `prev_hash` is a **field inside the payload**. Genesis (seq 0) is 64 `0`s.
5. Money: 2 dp, `ROUND_HALF_EVEN`, `-` for negatives, `"0.00"` for zero. Ratios: 6 dp. Timestamps: `YYYY-MM-DDTHH:MM:SSZ`, truncated to the second *before* storing. Dates: `YYYY-MM-DD`. Quarter: `Q3FY27`. Integers: base-10, no leading zeros. Absent values: the literal `"none"`.

**Verified this session:** for `{"prev_hash":"0"*64,"scheme":"calledit-ledger-v1","seq":"0","test":"researcher-probe-2026-11-18"}`, Python `json.dumps(sort_keys, compact)` and a Node 24 `canonical.ts` (run with `node --test`, WebCrypto) both produced `3274e09024a2561fb06caa533f7727a9e67ae6c7c5e3bfe8fe849233d2c5d99e`. `ots stamp`-equivalent `DetachedTimestampFile.from_fd(OpSHA256(), fd)` over a file containing exactly those bytes reported the same `file_digest` [VERIFIED: local run].

**Record kinds (one-way: name the set now):** `rules` (seq 0, and later FEAT-03), `prediction`, and `gap` (refused lock, D-08). Reserve `annotation` and `universe_change` for later. The spec should say that new kinds may be added by a later rules record without changing the canonicalisation.

**Proposed field sets** (names are Claude's discretion; freeze them in the spec doc):
- `rules`: `scheme, seq, record_kind, rules_id ("prereg-v1"), document_path ("PREREGISTRATION.md"), document_sha256, document_git_commit, universe_sha256, recorded_at, prev_hash`
- `prediction`: `scheme, seq, record_kind, ticker, isin, fiscal_quarter, target ("rev_ops_consolidated_inr_cr"), point_inr_cr, lo80_inr_cr ("none"), hi80_inr_cr ("none"), interval_label, baseline_inr_cr, baseline_method ("ttm_yoy"|"break_single_pair"), growth, model_version, labels, breaks_in_window, feature_snapshot_sha256, data_cutoff, locked_at, earliest_plausible_reveal, lock_kind, rules_seq, rules_hash, universe_sha256, code_git_sha, run_id, prev_hash`
- `gap`: `scheme, seq, record_kind, ticker, fiscal_quarter, reason_code ("missing_seed_quarter"|"unverified_seed_quarter"), missing_quarters, attempted_at, rules_hash, prev_hash`
- The interval label is locked as "none (baseline-only, no out-of-sample residuals yet)" [VERIFIED: 01-CONTEXT.md:34 — `the payload labels the interval as "none (baseline-only, no out-of-sample residuals yet)"`]. It is valid under rule 2 (ASCII, no quote or backslash).
- Include the interval, `model_version` and rules fields **now**, so Phase 4 model locks reuse v1 without a scheme bump.

**`predictions` table (LEDG-01; every record kind lives in this single chain table):** `seq INTEGER PK`, `record_kind`, `ticker NULL`, `fiscal_quarter NULL`, `predicted_revenue_cr NULL`, `low_cr NULL`, `high_cr NULL`, `baseline_cr NULL`, `model_version NULL`, `feature_snapshot TEXT NULL` (canonical snapshot), `created_at` (equals `locked_at`/`recorded_at`), `payload_canonical TEXT NOT NULL`, `hash CHAR(64) UNIQUE NOT NULL`, `prev_hash CHAR(64) UNIQUE NOT NULL`. Add CHECKs that tie record_kind to non-null columns. A test asserts the typed columns equal the parsed payload.
- **Fork rejection (LEDG-03):** the app reads the head inside the transaction and refuses any `prev_hash` that is not the head's hash. Independently, `UNIQUE(prev_hash)` makes a second child of any record impossible at the DB level, on both backends.

**Triggers — SQLite** (bypass matrix verified on 3.50.4 this session):

| Operation | No triggers' REPLACE guard, `recursive_triggers=OFF` | `recursive_triggers=ON` | With BEFORE INSERT replace guard |
|---|---|---|---|
| `UPDATE` | blocked (update trigger) | blocked | blocked |
| `DELETE FROM p` (SQLite's TRUNCATE-equivalent) | blocked | blocked | blocked |
| `INSERT OR REPLACE` / `REPLACE` | **SUCCEEDED, row overwritten** | blocked (delete trigger fires) | blocked |
| `INSERT … ON CONFLICT DO UPDATE` | blocked (update trigger) | blocked | blocked |
| `UPDATE OR REPLACE` | blocked | blocked | blocked |

Errors surface as `sqlite3.IntegrityError` carrying the RAISE message [VERIFIED: local run]. Ship all three triggers *and* set the pragma: defence in depth. SQLite has no `TRUNCATE` statement, so the LEDG-04 "TRUNCATE" test on SQLite is `DELETE FROM predictions` with no `WHERE`.

**Triggers — Postgres:**
- `BEFORE UPDATE OR DELETE … FOR EACH ROW` plus `BEFORE TRUNCATE … FOR EACH STATEMENT`. PG docs: "Triggers on `TRUNCATE` may only be defined at statement level, not per-row" [CITED: postgresql.org/docs/current/trigger-definition.html, v18.7].
- `INSERT … ON CONFLICT DO UPDATE` fires BEFORE UPDATE row triggers ("row-level `BEFORE` `INSERT` and then `BEFORE` `UPDATE` triggers"), so the update trigger blocks upserts. `MERGE` fires the underlying UPDATE/DELETE triggers [CITED: same page].
- Then `ALTER TABLE … ENABLE ALWAYS TRIGGER <each>`: "triggers configured as `ENABLE ALWAYS` will fire regardless of the current replication role" [CITED: postgresql.org/docs/current/sql-altertable.html]. That closes the `SET session_replication_role = replica` bypass. The table owner can still `DISABLE TRIGGER` or `DROP`. That is the honest limit; the external witnesses cover it.
- `nowcast db check` asserts every expected trigger exists and `pg_trigger.tgenabled = 'A'` (SQLite: rows in `sqlite_master` with `type='trigger'`), and that `current_setting('session_replication_role') = 'origin'`. Refuse to lock otherwise.
- Supabase: custom schemas are not exposed by default; exposing one requires adding it under "Exposed schemas" plus `USAGE`/`ALL` grants to `anon, authenticated, service_role` [CITED: supabase.com/docs/guides/api/using-custom-schemas]. In addition: `ENABLE ROW LEVEL SECURITY` with no policies, and `REVOKE ALL … FROM anon, authenticated` **inside a `DO` block that checks `pg_roles`**, because those roles do not exist on a vanilla `postgres:17` CI container.
- Apply the same trigger set to `observations` and `reveal_events` (PIT-02).

### Pattern 9: Leakage suite, leaky readers, splitter

- `tests/conftest.py` adds `--reader={correct,leaky-le,leaky-nofilter,leaky-period,leaky-ingested}` (default `correct`). A fixture `reader_cls` returns the chosen class. `tests/leakage/leaky_readers.py` holds the deliberately wrong readers: `<=` instead of `<`, no filter, filtering on `period_date`, and live mode ignoring `ingested_at`.
- **LEAK-01 property:** in hypothesis, build an in-memory SQLite store *inside the test body*. Function-scoped fixtures plus `@given` trigger hypothesis's `function_scoped_fixture` health check [ASSUMED]. Generate random observations and a random cutoff `T`. Compute `baseline_v1` and the canonical snapshot at `T`. Then add, mutate or remove (simulated in a fresh store) only rows with `available_at >= T`, including sentinel values, rows at exactly `T` and rows at `T+1s`. Recompute and assert the canonical snapshot string and the Decimal point are **byte-identical**. Add explicit `@example`s for the boundary rows, so each leaky reader is caught deterministically rather than by luck.
- Hypothesis profile: `deadline=None` (DB-backed examples on Windows are slow), plus `derandomize=True` for CI and the meta-test. Choose `max_examples` so the suite stays under 30 s.
- **LEAK-02 meta-test** (`tests/meta/test_leakage_suite_catches_leaks.py`, outside `tests/leakage` so it doesn't recurse): for each leaky variant, `subprocess.run([sys.executable, "-m", "pytest", "tests/leakage", f"--reader={v}", "-q", "-p", "no:cacheprovider"])` and assert `returncode == 1`. pytest exit code 1 means "tests failed". 2/3/4/5 mean interrupted, internal, usage or no tests, and must not count as "caught". Success criterion 3 is then also runnable by hand: `uv run pytest tests/leakage --reader=leaky-le` exits non-zero.
- **LEAK-03:** `2027-01-02 00:15 IST == 2027-01-01T18:45:00Z`. A row at exactly `as_of` is excluded and a row at `as_of − 1µs` is included. A date-only rule row (`D 23:59:59 IST`) is not visible to a lock at `D 18:00 IST`.
- **LEAK-04 splitter** (`nowcaster/splits.py`): `expanding_window_folds(targets, reveal_at, cutoff_policy, min_train)`. Train = `(c, q)` with `reveal_at(c, q) < fold.as_of` and value `available_at < fold.as_of`. The target is never in its own train set, and folds are chronological. A property test asserts these over random calendars. Do not use `TimeSeriesSplit` (CLAUDE.md).

### Pattern 10: Seed loader

- CSV columns: the DATA-01 set `ticker, fiscal_quarter, period_end, results_date, business_update_at, revenue_cr, source_url`, plus `isin, basis, line_item, unit_in_filing, results_at_basis, business_update_basis, business_update_url, page_ref, vintage, verified, notes`.
- `results_date` / `business_update_at` accept `YYYY-MM-DD` (basis `rule:date_eod_ist`) or `YYYY-MM-DDTHH:MM+05:30` (basis `exchange_timestamp`). The declared basis must match the format.
- Validate the **whole file** with pydantic per row and collect every error as `(row, column, reason)` (D-25). Checks: `period_end == fiscal_quarter.end`, revenue matches `^\d+\.\d{2}$`, `source_url` is https, dates are plausible (results after period end and before now), and `verified ∈ {Y, N}`. Live/rehearsal loads require all `Y`. `--dry-run` reports and inserts nothing.
- `data/seed/README.md` explains where to find each company's results PDF (company IR page first, exchange PDF opened by the user). It covers which line to copy ("Revenue from operations", consolidated column, as first reported), unit conversion to ₹ crore, how to read the dissemination time, and what `verified` means.

### Pattern 11: Rules record and the lock

- PREREGISTRATION.md contains: the universe and its rationale (survivorship disclosed), baseline-v1 with the exact Decimal procedure, the "usable quarter" definition, the Eternal break range with a citation and the resulting method, the D-07 flag, the missing-quarter rule, grading D-09..D-15 ("compare unrounded Decimals, display at 2 dp"), the official-call/VOID/deadline rules and offsets, the record kinds, the canonical spec reference, "GST 2.0 treatment: deferred to FEAT-03", and the research-only disclaimer.
- Ordering: commit PREREGISTRATION.md (`-text` in `.gitattributes`). Dispatch `action=rules`, which appends seq 0 with `document_sha256` of the committed blob and `document_git_commit`, exports, OTS-stamps and commits. Ideally do this a day before the predictions, so its Bitcoin attestation predates them. The prediction payloads carry `rules_hash`, so they prove they followed the rules record either way.
- **Lock guard (D-14), all on UTC instants:**
  - refuse if `now >= earliest_plausible_reveal(c, Q)`;
  - refuse if any reveal event for `(c, Q)` is known at `now`;
  - refuse unless Q is live: `period_start(Q) <= now < earliest_plausible_reveal`. This rejects `Q2FY27` and far-future quarters. The rule is a recommendation and needs user confirmation;
  - refuse if the rules record is missing, or `universe_sha256`/`document_sha256` changed since it was recorded without a new rules record;
  - in `live`, refuse unless `GITHUB_ACTIONS == "true"` and the ref is the default branch. Record `run_id`.
- **No past-time locks:** the CLI has **no** `--as-of` or `--locked-at` flag for `predict`. `locked_at = as_of = now` truncated to the second.

### Pattern 12: Lock workflow (`.github/workflows/lock.yml`)

- Trigger: `workflow_dispatch` with inputs `action: rules|predict|upgrade` and `mode: rehearsal|live`. `concurrency: {group: ledger, cancel-in-progress: false}`. `permissions: contents: write`. Use `actions/checkout@v7` (`fetch-depth: 0`) and `astral-sh/setup-uv@v10` (versions per CLAUDE.md). `uv sync --locked --group ots`.
- `env: DATABASE_URL: ${{ secrets.DATABASE_URL }}`. `CALLEDIT_ENV` and `CALLEDIT_DB_SCHEMA` are derived from `mode`. A rehearsal writes to `calledit_rehearsal` and `build/rehearsal/ledger/`. It never commits to `main`; it either uploads an artifact, or pushes to a `rehearsal/<run_id>` branch that is then deleted to prove push permissions.
- `workflow_dispatch` only works once the workflow file is on the **default branch**, so push it before the rehearsal [ASSUMED: GitHub behaviour].
- Commit step: `git config user.name "github-actions[bot]"` … `git add ledger/ && git commit -m "ledger: …" && git push`. Before committing, assert the previous `ledger.jsonl` is a byte-prefix of the new one.
- Secret setup for the user (value never echoed): `gh secret set DATABASE_URL` and paste at the hidden prompt, or `gh secret set -f .env` once `.env` is dotenv-formatted. Both flags exist in gh 2.101.0 (`-f, --env-file file  Load secret names and values from a dotenv-formatted file`) [VERIFIED: `gh secret set --help`].

### Pattern 13: OpenTimestamps flow (verified facts)

- **Stamp:** `ots stamp FILE` hashes the file with SHA-256 (`DetachedTimestampFile.from_fd(OpSHA256(), fd)`). It appends a 16-byte random nonce and writes `FILE + '.ots'`, opened with `'xb'`, so an existing proof is never overwritten. Default calendars are `a.pool.opentimestamps.org`, `b.pool.opentimestamps.org`, `a.pool.eternitywall.com` and `ots.btc.catallaxy.com`. `-m` defaults to `"2"` (at least 2 calendars must answer) and `--timeout` to 5 s [VERIFIED: read installed `otsclient/cmds.py` and `args.py` 0.8.0]. All 4 calendars accepted a test submission from this Windows machine [VERIFIED: local run].
- **Recipe for D-20:** write the head record's `payload_canonical` bytes (no newline) to `$RUNNER_TEMP/<seq>`, run `ots stamp $RUNNER_TEMP/<seq>`, then move `$RUNNER_TEMP/<seq>.ots` to `ledger/proofs/<seq>.ots`. The proof's digest **equals the head hash**, so anyone can run `ots verify -d <head_hash> ledger/proofs/<seq>.ots`. The `-d DIGEST` option ("Verify a (hex-encoded) digest rather than a file") exists on `verify` only, not on `stamp` [VERIFIED: args.py].
- **Upgrade:** `ots upgrade f.ots` renames the old file to `f.ots.bak` and **exits 1 if `.bak` already exists**. It exits 1 with "Failed! Timestamp not complete" while still pending, and exits 0 with "Success! Timestamp complete" [VERIFIED: cmds.py]. The workflow must delete `*.ots.bak` (and gitignore them) and treat exit 1 as "still pending", not as a failure.
- **Verify:** `ots verify` returns success only after a local Bitcoin node confirms the block header. With no node it logs "Could not connect to local Bitcoin node" and exits 1. With `--no-bitcoin` it logs "To verify manually, check that Bitcoin block %d has merkleroot %s" (merkle root in explorer display byte order via `b2lx`) and still exits 1 [VERIFIED: cmds.py `verify_timestamp`]. The README states "to _verify_ timestamps you need a local Bitcoin Core node (a pruned node is fine)" [CITED: github.com/opentimestamps/opentimestamps-client].
- **Explorer cross-check:** `scripts/ots_explorer_check.py` uses `opentimestamps` to deserialize the proof, check `file_digest == head_hash`, and read each `BitcoinBlockHeaderAttestation(height)`'s message (byte-reversed). It fetches `/api/block-height/{h}` then `/api/block/{hash}` `merkle_root` from **both** `blockstream.info` and `mempool.space`. Both returned identical merkle roots for block 358391 this session [VERIFIED: curl]. The script also asserts block time < `earliest_plausible_reveal`.

### Anti-Patterns to Avoid
- **Hashing a dict on the fly instead of the stored string:** store `payload_canonical`, and hash and export exactly it.
- **`server_default=func.now()` / SQLite `CURRENT_TIMESTAMP` on timestamp columns:** these produce naive text with a space separator that breaks `UTCDateTime` ordering. The writer sets `ingested_at`.
- **Alembic batch mode or `render_as_batch=True` on ledger/store tables:** the table rebuild silently drops triggers (CLAUDE.md). Migrations are hand-written. Add a grep test that bans `batch_alter_table` on these tables.
- **Asserting the exception class across backends:** SQLite raises `IntegrityError`, PG raises a `RaiseException` (P0001) wrapped by SQLAlchemy. Assert `pytest.raises(sqlalchemy.exc.DBAPIError, match="append-only")`.
- **Any `--as-of` on live `predict`**, a `--force` that skips the guard, or a SQLite fallback in live mode.
- **pandas/float anywhere in the baseline → payload path.**

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SHA-256 | anything | `hashlib.sha256` / `crypto.subtle.digest` | Standard, and verified identical |
| JSON serialisation | a custom string builder in Python | `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=True, allow_nan=False)` after a type/charset validation pass | Escaping edge cases |
| Bitcoin timestamping | your own calendar protocol | `ots` CLI (stamp/upgrade) + `opentimestamps` lib (parse) | Proof format, merkle paths, calendar quirks |
| Money rounding | float maths | `decimal.Decimal.quantize(…, ROUND_HALF_EVEN)` in a fixed `localcontext` | Reproducibility |
| Migrations | ad-hoc DDL scripts | Alembic (hand-written revisions, `op.execute` for triggers) | Ordered, re-runnable, version table |
| Settings / `.env` | `os.environ` parsing | pydantic-settings | Validation, `.env` support |
| Property testing | random loops | hypothesis | Shrinking, `@example`, profiles |
| Clock freezing | monkeypatching `datetime` | time-machine | Correct C-level patching |
| CSV parsing | `str.split(",")` | `csv.DictReader(open(p, newline="", encoding="utf-8"))` | Quotes, CRLF |
| tz conversion | manual `+5:30` string maths | `datetime` + fixed-offset `timezone` (and `tzdata` for `zoneinfo`) | Boundary correctness |

**Key insight:** the only code that *should* be hand-written here is the domain logic: the canonical validator, the baseline, the lock guard and the splitter. Every primitive under it has a standard implementation that a sceptical reviewer will trust more.

## Common Pitfalls

### Pitfall 1: `.env` cannot be parsed as-is (BLOCKER for the Postgres criteria)
**What goes wrong:** pydantic-settings and python-dotenv ignore lines without `KEY=`, so `DATABASE_URL` silently falls back to the SQLite default. Even with a key, the URL fails to parse: `urlsplit` returned no host or port, because the password contains unencoded reserved characters and square brackets.
**Why it happens:** the Supabase UI shows `[YOUR-PASSWORD]` as a placeholder, and the brackets plus special characters were pasted literally.
**How to avoid:** the user (not the plan; D-02) edits `.env` to `DATABASE_URL=postgresql+psycopg://postgres.<ref>:<percent-encoded password>@<pooler-host>:5432/postgres`, with no brackets. Percent-encode the password with `urllib.parse.quote(pw, safe="")`, or rotate it to one without reserved characters. Add `nowcast db check`, which reports "no DATABASE_URL key found", "URL does not parse (password probably needs percent-encoding)" or "connected, schema X, triggers OK" **without printing any part of the URL**. The same corrected value becomes the GitHub secret.
**Warning signs:** `nowcast db check` says sqlite when the user expected postgres.

### Pitfall 2: `ots` CLI crashes on Windows
**What goes wrong:** `ots …` raises `TypeError: LoadLibrary() argument 1 must be str, not None` at import (`bitcoin/core/key.py` → `ctypes.util.find_library('ssl')` returns None on Windows) [VERIFIED: local run, opentimestamps-client 0.8.0 / python-bitcoinlib 0.12.2, Python 3.13 venv]. This also breaks `ots upgrade` and `ots verify` locally.
**How to avoid:** stamp, upgrade and verify only on the ubuntu runner (D-18). Keep `opentimestamps-client` in the CI-only `ots` group. Local scripts use only the `opentimestamps` library, which imports fine. Linux behaviour (OpenSSL 3 on ubuntu-24.04) is [ASSUMED]. The D-21 rehearsal is the falsification test; the fallback is a library-based stamper.

### Pitfall 3: A late-erring timestamp is safe for availability but leaky as a reveal cutoff
**What goes wrong:** D-24's `rule:date_eod_ist` (23:59:59 IST) is safe for *value availability*. Used as `reveal_at`, though, it is **late**. A lock between the real filing (for example 18:00 IST) and 23:59:59 would not be VOIDed at grading (D-14), and a backtest test-quarter cutoff `reveal_at − Δ` could see data published after the real reveal.
**How to avoid (keeps D-24's storage intact):** store the event with its basis. Derive `reveal_at_earliest` (date-only events at `D 00:00:00 IST`, exact timestamps as-is) and use it for VOID, the lock guard and backtest test cutoffs. Use the stored late value for training-row availability. This needs user confirmation (Open Question 3). It doesn't affect the Q3FY27 lock itself, because no Q3FY27 reveal event exists yet and `earliest_plausible_reveal` governs.
**Warning signs:** a single `reveal_at` column used both as "data available" and as "deadline".

### Pitfall 4: Windows-specific byte and time traps
- Python text-mode `open(p, "w")` on Windows writes `\r\n`, which would corrupt `ledger.jsonl` and the hashed files. Always use `open(p, "w", encoding="utf-8", newline="\n")` or binary mode.
- This repo already commits CRLF. `.planning/ROADMAP.md`'s blob has 150 `\r` (repo-level `core.autocrlf=false`, system-level `true`) [VERIFIED: git]. A hashed `PREREGISTRATION.md` checked out differently on the runner would change its SHA-256. Add `.gitattributes` **before** creating any hashed file: `PREREGISTRATION.md -text`, `config/universe.toml -text`, `ledger/** -text`, `*.ots binary`, `data/seed/*.csv -text`. Add a test that the working-tree bytes equal `git cat-file blob HEAD:<path>`.
- `zoneinfo` without `tzdata` fails in a clean venv on Windows [VERIFIED].

### Pitfall 5: Supabase/Postgres trigger bypasses and roles
- TRUNCATE needs a statement trigger. `session_replication_role=replica` skips normally enabled triggers, so use `ENABLE ALWAYS`. The owner can `DISABLE` or `DROP`, so publish that limit and rely on the witnesses.
- `anon`/`authenticated` roles don't exist on vanilla Postgres, so guard REVOKEs in a `DO` block.
- PG tests: no Docker locally. Either use a Supabase scratch schema `calledit_test_<hex>`, with a hard guard that refuses unless the name starts with `calledit_test_` (`DROP SCHEMA … CASCADE` must never be able to target `calledit` or `calledit_rehearsal`), or add a minimal `ci-postgres.yml` with a `postgres:17` service now. Recommend the CI container, since Phase 2 OPS-03 needs it anyway. Keep the scratch-schema path as the local option.

### Pitfall 6: Weekly re-runs and repeated locks
Every `predict` run appends records; nothing is ever deleted. Rehearsal must not touch `calledit`. Re-running a live lock by mistake creates an extra visible lock, which is honest but noisy. Workflow inputs should require typing `mode: live` explicitly, and the rehearsal must be the default.

### Pitfall 7: Non-deterministic outputs break "bit-identical"
Ties in latest-vintage selection, dict ordering in snapshots, set iteration and `Decimal` context drift all produce false positives in LEAK-01. Sort with a total key, use a fixed `localcontext`, and canonicalise snapshots with the ledger canonicaliser.

### Pitfall 8: OTS operational traps
`.ots.bak` collisions, treating "pending" exit 1 as failure, stamping a file with a trailing newline (the digest no longer equals the head hash), and git normalising the binary `.ots` file (mark it `binary`).

### Pitfall 9: Secrets in logs
GitHub masks the secret string, but not derived pieces such as a URL-decoded password, the host, or psycopg error text that echoes connection parameters. Never log URL components. Catch connection errors and print a fixed message plus the exception *class*.

### Pitfall 10: Default branch and witness URLs
The local branch is `master`, and the GitHub repo is empty with no default branch yet [VERIFIED: `gh repo view`]. The first push sets the default branch, and witness links include it. Decide `main` vs `master` before the first push (`git branch -M main` is recommended) and add a ruleset that blocks force-push and deletion.

### Pitfall 11: Seed unit and basis errors
Filings may report in ₹ lakh or ₹ million rather than ₹ crore [ASSUMED for specific companies and years]. Titan's press releases highlight "total income", and Eternal shows "adjusted revenue". The CSV records `unit_in_filing` and `line_item`, and the user verifies each row against the consolidated "Revenue from operations" line. Never use the board-meeting *conclusion* time as the dissemination time; it is earlier than public availability.

## Code Examples

### Canonicaliser (Python)
```python
# nowcaster/ledger/canonical.py — spec calledit-ledger-v1 (all-string JSON)
import hashlib, json, re
_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
def _check(v, path="$"):
    if isinstance(v, str):
        bad = [c for c in v if not (0x20 <= ord(c) <= 0x7E) or c in '"\\']
        if bad: raise ValueError(f"{path}: disallowed character(s) {bad!r}")
    elif isinstance(v, list):
        for i, x in enumerate(v): _check(x, f"{path}[{i}]")
    elif isinstance(v, dict):
        for k, x in v.items():
            if not isinstance(k, str) or not _KEY.match(k): raise ValueError(f"{path}: bad key {k!r}")
            _check(x, f"{path}.{k}")
    else:
        raise TypeError(f"{path}: {type(v).__name__} not allowed (strings only)")
def canonicalize(v) -> str:
    _check(v)
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
```

### Canonicaliser (TypeScript, Node 24 `node --test`, also usable in the browser later)
```typescript
// web/src/lib/canonical.ts — verified to reproduce the Python hash this session
export type Canon = string | Canon[] | { [k: string]: Canon };
export function canonicalize(v: Canon): string {
  if (typeof v === "string") return JSON.stringify(v);
  if (Array.isArray(v)) return "[" + v.map(canonicalize).join(",") + "]";
  const keys = Object.keys(v).sort();
  return "{" + keys.map((k) => JSON.stringify(k) + ":" + canonicalize(v[k])).join(",") + "}";
}
export async function sha256Hex(s: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
}
// (add the same charset/key validation as Python; golden "must reject" vectors test it)
```

### UTC TypeDecorator
```python
# calledit_data/db/types.py
from datetime import datetime, timezone
import sqlalchemy as sa
class UTCDateTime(sa.types.TypeDecorator):
    impl = sa.String(27); cache_ok = True          # SQLite: fixed-width 'YYYY-MM-DDTHH:MM:SS.ffffffZ'
    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(sa.DateTime(timezone=True) if dialect.name == "postgresql" else sa.String(27))
    def process_bind_param(self, v, dialect):
        if v is None: return None
        if v.tzinfo is None or v.utcoffset() is None: raise ValueError("naive datetime rejected")
        v = v.astimezone(timezone.utc)
        return v if dialect.name == "postgresql" else v.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    def process_result_value(self, v, dialect):
        if v is None: return None
        if isinstance(v, str): return datetime.strptime(v, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)
```

### Trigger migration (dialect-branched)
```python
# data/migrations/versions/0002_append_only_triggers.py (excerpt)
def upgrade():
    bind = op.get_bind()
    for t in ("predictions", "observations", "reveal_events"):
        if bind.dialect.name == "sqlite":
            op.execute(f"CREATE TRIGGER {t}_no_update BEFORE UPDATE ON {t} BEGIN SELECT RAISE(ABORT, 'calledit: {t} is append-only (update)'); END;")
            op.execute(f"CREATE TRIGGER {t}_no_delete BEFORE DELETE ON {t} BEGIN SELECT RAISE(ABORT, 'calledit: {t} is append-only (delete)'); END;")
            # + {t}_no_replace BEFORE INSERT … WHEN EXISTS(conflict on any UNIQUE key) … RAISE(ABORT, '… (replace blocked)')
        else:
            s = schema_name()   # validated identifier, e.g. calledit
            op.execute(f"CREATE TRIGGER {t}_no_update_delete BEFORE UPDATE OR DELETE ON {s}.{t} FOR EACH ROW EXECUTE FUNCTION {s}.forbid_mutation()")
            op.execute(f"CREATE TRIGGER {t}_no_truncate BEFORE TRUNCATE ON {s}.{t} FOR EACH STATEMENT EXECUTE FUNCTION {s}.forbid_mutation()")
            op.execute(f"ALTER TABLE {s}.{t} ENABLE ALWAYS TRIGGER {t}_no_update_delete")
            op.execute(f"ALTER TABLE {s}.{t} ENABLE ALWAYS TRIGGER {t}_no_truncate")
            op.execute(f"ALTER TABLE {s}.{t} ENABLE ROW LEVEL SECURITY")
```

### Leaky-reader meta-test
```python
# tests/meta/test_leakage_suite_catches_leaks.py
import subprocess, sys, pytest
@pytest.mark.parametrize("variant", ["leaky-le", "leaky-nofilter", "leaky-period", "leaky-ingested"])
def test_suite_fails_on_leaky_reader(variant):
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/leakage", f"--reader={variant}",
                        "-q", "-p", "no:cacheprovider", "--hypothesis-profile=ci"], capture_output=True, text=True)
    assert r.returncode == 1, f"expected test failures (exit 1), got {r.returncode}\n{r.stdout[-2000:]}"
```

### Baseline core (Decimal)
```python
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
CENT, SIX = Decimal("0.01"), Decimal("0.000001")
def ttm_baseline(sqly: Decimal, recent4: list[Decimal], prior4: list[Decimal]) -> tuple[Decimal, Decimal]:
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 28, ROUND_HALF_EVEN
        g = sum(recent4) / sum(prior4) - 1
        point = (sqly * (1 + g)).quantize(CENT, rounding=ROUND_HALF_EVEN)
        return point, g.quantize(SIX, rounding=ROUND_HALF_EVEN)   # g quantised for display only
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pytrends | trendspyg / official Trends API alpha | pytrends archived Apr 2025 (project research) | Not Phase 1 |
| opentimestamps-client 0.7.x | 0.8.0 (2026-10-27): `--timeout` now applies to `upgrade`; `--wait` always waits; calendar redirect/whitelist fixes | 2026-10-27 [CITED: release-notes.md] | Pin 0.8.0 |
| vitest/jest for a tiny TS test | Node ≥23.6 native type stripping + `node:test` | Node 23/24 | Zero-dependency `web/` test in Phase 1 [VERIFIED on Node 24.21.0] |
| javascript-opentimestamps (`ots-cli.js`) | Python client + explorer cross-check | npm `opentimestamps` last published 0.4.9, `time.modified` 2022-05-12, depends on deprecated `request` [VERIFIED: npm view] | Don't adopt the JS client |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ots` CLI (0.8.0, python-bitcoinlib 0.12.2) imports and works on GitHub's ubuntu runner (OpenSSL 3) | Pattern 13, Pitfall 2 | Stamping fails in the live run. Mitigated by the rehearsal and a library-based stamper fallback |
| A2 | `workflow_dispatch` only runs once the workflow file is on the default branch | Pattern 12 | Rehearsal can't be triggered; push the workflow first |
| A3 | SQLAlchemy 2.1's default driver for `postgresql://` (psycopg2 vs psycopg) | Pattern 3 | None if the URL is normalised to `postgresql+psycopg://` |
| A4 | ISINs: Eternal `INE758T01015`, Titan `INE280A01028` | Pattern 2 | A wrong identifier gets hashed into the payload (one-way); the user verifies from the filing header |
| A5 | Hypothesis raises a `function_scoped_fixture` health check for `@given` + function fixtures | Pattern 9 | Minor; build stores inside the test body regardless |
| A6 | Some filings use ₹ lakh / ₹ million units | Pitfall 11 | Wrong revenue; the `unit_in_filing` column and user verification catch it |
| A7 | Eternal break range: roughly Q1 FY26 → Q3 FY26 (transition started around Q1/Q2 FY26, ~80% inventory-led by Q2 FY26, ~90% by Q3 FY26 per secondary sources) | Pattern 7 | This determines Eternal's method; it must be pinned from the shareholder letter (D-06) |
| A8 | Supabase's `postgres` role can create schemas, functions, triggers and `ENABLE ALWAYS` (as table owner) through the session pooler | Pattern 8 | Migrations fail on Supabase; detected by `alembic upgrade head` in the rehearsal |
| A9 | OTS Bitcoin confirmation lands within a few hours (README: "a few hours") | Pattern 13 | Upgrade needs another dispatch the next day; the 3-day slack covers it |
| A10 | Proposed lock-guard "live quarter" rule (`period_start <= now < earliest_plausible_reveal`) | Pattern 11 | Over- or under-restrictive; needs user confirmation since it is a preregistered rule |

## Open Questions (RESOLVED)

1. **What counts as "`ots verify` accepts" (success criterion 5)?**
   - What we know: the Python `ots verify` exits 0 only with a reachable Bitcoin Core node [VERIFIED: cmds.py]. No node is available; a pruned node still needs a full initial sync. The JS client is unmaintained since 2022.
   - Recommendation: the criterion is met by (a) `ots upgrade` reporting "Success! Timestamp complete", (b) `ots --no-bitcoin verify -d <head_hash> ledger/proofs/<seq>.ots` printing block height and merkle root, and (c) `scripts/ots_explorer_check.py` confirming that merkle root on two independent explorers and that block time < reveal. Optionally (d) the user drops the files into the opentimestamps.org web verifier [ASSUMED available]. State on the methodology page that full trust-minimised verification needs a node. **The user confirms this reading.** **RESOLVED (2026-11-18): D-26** in 01-CONTEXT.md, which adopts (a)+(b)+(c) and the Bitcoin-node statement. Implemented in Plans 01-10, 01-11, 01-12 and 01-13.
2. **Eternal break range (start_q, end_q) and its citation.** It needs the primary shareholder letters (eternal IR). The plan should include a task where Claude drafts the range plus citation from the letters and the user confirms it, before PREREGISTRATION is frozen. **RESOLVED (2026-11-18):** Plan 01-09 Task 3 drafts the range and citation from the shareholder letters, and the user confirms them at the Plan 01-10 freeze checkpoint before PREREGISTRATION is frozen.
3. **Reveal early-bound derivation (Pitfall 3).** Should VOID and cutoffs use `D 00:00 IST` for date-only events? Recommended: yes, written into PREREGISTRATION. **RESOLVED (2026-11-18): D-27.**
4. **Default branch `main` or `master`.** This must be settled before the first push (witness URLs). **RESOLVED (2026-11-18): D-28** (`main`, renamed in Plan 01-01).
5. **Postgres test target:** a CI `postgres:17` service now, or a Supabase scratch schema locally (or both)? Recommended: both, with the scratch-schema guard. **RESOLVED (2026-11-18): D-29** (both; Plan 01-08).
6. **Live-quarter rule (A10)** and whether a run that locks some companies and records gaps for others should exit 0 or non-zero. Recommended: a distinct non-zero code (for example 3) after committing whatever was appended, so the Actions run is visibly red. **RESOLVED (2026-11-18):** the user adopted the recommendation through the orchestrator: the live-quarter rule, plus exit code 3 for a partial lock. Implemented in Plan 01-07 (`nowcaster/exit_codes.py`) and preregistered in Plan 01-10.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | FOUND-01 | ✗ | — | Install via the official PowerShell installer (`irm https://astral.sh/uv/install.ps1 \| iex`) or winget. **Blocking until installed** |
| Python 3.12 | runtime | ✗ (3.13.15 present) | — | `uv` downloads a managed 3.12 automatically from `.python-version` |
| Node.js / npm | `web/` golden vectors | ✓ | 24.21.0 / 11.19.0 | — (Node 26 LTS is for Phase 5 per CLAUDE.md; 24 is enough for `node --test`) |
| git | witness | ✓ | 2.53.0.windows.2 | — |
| gh CLI | remote, secrets | ✓ authenticated (account KASHITOp) | 2.101.0 | — |
| GitHub repo `KASHITOp/called-it` | LEDG-09 | ✓ exists, PUBLIC, **empty**, no default branch | — | `git remote add origin …` then first push |
| `.gitignore` committed / `.env` ignored | D-03 | ✓ `.gitignore` tracked (commit 09d4aab); `git check-ignore .env` → ignored | — | D-03's "untracked" note is already resolved |
| `.env` `DATABASE_URL` | FOUND-04, lock | ✗ **malformed** (no `KEY=`; URL does not parse) | — | The user edits it (Pitfall 1). **Blocking for Postgres criteria** |
| Supabase reachability | lock, PG tests | not probed (deliberately; the URL is malformed) | — | `nowcast db check` after the fix |
| `ots` CLI | LEDG-10 | ✗ on Windows (crashes at import) | client 0.8.0 | Run on the Actions ubuntu runner |
| OTS calendars (4) | LEDG-10 | ✓ all 4 accepted a test stamp | — | `-m 2` tolerates 2 outages |
| Block explorers (blockstream.info, mempool.space) | verify cross-check | ✓ both answered, identical merkle root | Esplora API | — |
| Docker / psql / local Postgres | PG trigger tests | ✗ | — | CI `postgres:17` service or a Supabase scratch schema |
| SQLite | dev/tests | ✓ (Python-bundled) | 3.50.4 | — |
| Bitcoin Core node | literal `ots verify` | ✗ | — | Explorer cross-check (Open Question 1) |

**Missing dependencies with no fallback:** uv must be installed, and `.env` must be fixed by the user.
**Missing with fallback:** Python 3.12 (uv-managed), `ots` (Actions), Postgres (CI container or scratch schema), Bitcoin node (explorers).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.2.0 + hypothesis 6.170.15 + time-machine 3.6.0; Node 24 `node:test` for `web/` |
| Config file | none yet; `[tool.pytest.ini_options]` in the root `pyproject.toml` (`testpaths=["tests"]`, `--strict-markers`, marker `postgres`), plus `tests/conftest.py` with `--reader`, the backend fixture and hypothesis profiles (`dev`, `ci`: `derandomize=True, deadline=None`) |
| Quick run command | `uv run pytest tests/leakage tests/ledger tests/data -q -x` |
| Full suite command | `uv run pytest -q` (+ `TEST_DATABASE_URL=… uv run pytest -m postgres -q`) + `npm test --prefix web` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FOUND-01 | Fresh-clone setup; dirs exist; `nowcast --help` runs | smoke | `uv sync && uv run nowcast --help` + `uv run pytest tests/test_layout.py -q` | ❌ Wave 0 |
| FOUND-03 | Universe parse/validate; disabling drops a company from lock targets | unit | `uv run pytest tests/data/test_universe.py -q` | ❌ Wave 0 |
| FOUND-04 | Settings normalise the URL; `alembic upgrade head` on SQLite + PG; live refuses SQLite | integration | `uv run pytest tests/data/test_db.py -q` ; `uv run alembic upgrade head` | ❌ Wave 0 |
| FOUND-05 | Fiscal labels ⇄ dates, round-trip property | unit+property | `uv run pytest tests/leakage/test_fiscal.py -q` | ❌ Wave 0 |
| PIT-01/02 | Required columns, no defaults; restatement adds a row; triggers on observations | integration | `uv run pytest tests/data/test_store.py -q` | ❌ Wave 0 |
| PIT-03 | Reader strict `<`, live `ingested_at`, post-condition | unit | `uv run pytest tests/leakage/test_reader.py -q` | ❌ Wave 0 |
| PIT-04 | Calendar derivation, status, earliest plausible (DMART 2026-12-31T18:30Z) | unit | `uv run pytest tests/data/test_calendar.py -q` ; `uv run nowcast calendar --quarter Q3FY27` | ❌ Wave 0 |
| PIT-05 | Breaks from config reach baseline (`breaks_in_window`) | unit | `uv run pytest tests/nowcaster/test_baseline.py -k breaks -q` | ❌ Wave 0 |
| LEAK-01 | Future-perturbation invariance | property | `uv run pytest tests/leakage/test_invariance.py -q` | ❌ Wave 0 |
| LEAK-02 | Leaky readers make the suite exit 1 | meta | `uv run pytest tests/meta -q` ; manual: `uv run pytest tests/leakage --reader=leaky-le` (expect exit 1) | ❌ Wave 0 |
| LEAK-03 | IST/UTC boundary, strict `<` at the instant | unit | `uv run pytest tests/leakage/test_time_boundaries.py -q` | ❌ Wave 0 |
| LEAK-04 | Splitter: train revealed before cutoff, target excluded | property | `uv run pytest tests/leakage/test_splits.py -q` | ❌ Wave 0 |
| DATA-01 | Whole-file reject with all errors; dry-run inserts nothing; live requires verified; idempotent reload | integration | `uv run pytest tests/data/test_seed_loader.py -q` ; `uv run nowcast seed load --dry-run` | ❌ Wave 0 |
| FEAT-02 | Break method selection (TTM vs pair vs least-straddling) + label | unit | `uv run pytest tests/nowcaster/test_baseline.py -k eternal -q` | ❌ Wave 0 |
| BASE-01 | Decimal baseline exact on fixtures; missing quarter → refusal | unit | `uv run pytest tests/nowcaster/test_baseline.py -q` | ❌ Wave 0 |
| LEDG-01 | Typed columns == parsed payload | integration | `uv run pytest tests/ledger/test_table.py -q` | ❌ Wave 0 |
| LEDG-02 | Golden vectors (accept + reject) in Py and JS | unit | `uv run pytest tests/ledger/test_canonical.py -q` ; `npm test --prefix web` | ❌ Wave 0 |
| LEDG-03 | Chain links; fork rejected by app and by `UNIQUE(prev_hash)` | integration | `uv run pytest tests/ledger/test_chain.py -q` | ❌ Wave 0 |
| LEDG-04 | UPDATE/DELETE/REPLACE/upsert/TRUNCATE(-equivalent) blocked; triggers exist after `upgrade head`; PG `tgenabled='A'` | integration | `uv run pytest tests/ledger/test_triggers.py -q` ; `TEST_DATABASE_URL=… uv run pytest tests/ledger -m postgres -q` | ❌ Wave 0 |
| LEDG-05 | Guard refuses Q2FY27, at or after the deadline, no `--as-of`; gap record on a missing quarter | unit (time-machine) | `uv run pytest tests/ledger/test_lock_guard.py -q` | ❌ Wave 0 |
| LEDG-07 | Rules record seq 0 hash == sha256 of the committed PREREGISTRATION.md blob | integration | `uv run pytest tests/ledger/test_rules_record.py -q` | ❌ Wave 0 |
| LEDG-09 | Export: each line == `payload_canonical`, LF, old file a byte-prefix | integration | `uv run pytest tests/ledger/test_export.py -q` | ❌ Wave 0 |
| LEDG-10 | Proof digest == head hash; upgraded proof confirms | manual + script | Actions run log; `uv run python scripts/ots_explorer_check.py ledger/proofs/<seq>.ots` | ❌ Wave 0 (manual-only for the Bitcoin step: needs real time to pass) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/leakage tests/ledger tests/data -q -x` (< 30 s target)
- **Per wave merge:** `uv run pytest -q` + `npm test --prefix web` (+ the postgres marker when `TEST_DATABASE_URL` is set)
- **Phase gate:** full suite green on SQLite **and** Postgres; the meta-test green; rehearsal run green; then the live lock

### Wave 0 Gaps
- [ ] Root `pyproject.toml` pytest config + `tests/conftest.py` (backend fixture, `--reader`, hypothesis profiles, PG scratch-schema guard)
- [ ] `tests/fixtures/hash_vectors.json` (≥10 accept vectors: genesis rules, prediction with `"none"` interval, zero, negative growth, half-even cases such as `0.125`→`0.12` and `0.135`→`0.14`, large money, nested snapshot with arrays, an IST-midnight-derived UTC timestamp; plus reject vectors: `₹`, `"`, `\`, control character, number, null, boolean, uppercase key)
- [ ] `tests/leakage/leaky_readers.py`
- [ ] `web/package.json` (`"test": "node --test tests/"`) + `web/tests/canonical.test.ts` reading `../tests/fixtures/hash_vectors.json`
- [ ] Optional `.github/workflows/ci-postgres.yml` (`postgres:17` service) if chosen in Open Question 5
- [ ] Framework install: `uv sync` (after uv itself is installed)

## Security Domain

`security_enforcement: true`, ASVS level 1, block on high (`.planning/config.json`).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | yes | One-way data flow; single writer; ledger integrity via chain + external witnesses |
| V2 Authentication | no (no user auth in Phase 1) | — |
| V3 Session Management | no | — |
| V4 Access Control | yes | Private `calledit` schema (not exposed), RLS on with no policies, REVOKE from anon/authenticated, `contents: write` only on the lock workflow, dispatch limited to repo writers, branch ruleset blocking force-push |
| V5 Input Validation | yes | pydantic for seed rows, config and settings; canonical charset validator; schema-identifier regex before any DDL formatting |
| V6 Cryptography | yes | `hashlib` SHA-256 / WebCrypto; OpenTimestamps; nothing custom |
| V7 Error Handling & Logging | yes | Never log `DATABASE_URL` or its parts; fixed error messages; fail loudly (D-17) |
| V10 Malicious Code / supply chain | yes | `uv.lock` + `uv sync --locked` in CI, pinned `opentimestamps-client==0.8.0`, official actions (consider SHA pinning), no `pull_request_target` |
| V14 Configuration | yes | Secrets only in GitHub encrypted secrets and the git-ignored `.env`; `.env.example` placeholder only |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Backdated or forged ledger row inserted by a DB-credential holder | Tampering / Repudiation | Hash chain + `UNIQUE(prev_hash)` + git commit + Actions log + OTS anchor; live writes only from Actions |
| `INSERT OR REPLACE` / TRUNCATE / replica-role trigger bypass | Tampering | REPLACE guard + `recursive_triggers`; TRUNCATE statement trigger; `ENABLE ALWAYS`; `db check` self-test |
| Anon key writes via PostgREST | Elevation / Tampering | Unexposed schema + RLS + REVOKE |
| SQL injection through the schema name in raw DDL | Tampering | Identifier regex + SQLAlchemy identifier quoting; no user-controlled SQL |
| Secret leakage in logs | Information disclosure | No URL logging; GH masking; error class only |
| Cherry-picked or repeated locks | Repudiation (of honesty) | Every run appended and visible; deterministic baseline; rehearsal isolated in its own schema; official call derived |
| Force-push rewriting the witness | Tampering | Ruleset: no force-push or deletion on the default branch; OTS proofs independent of git |
| Prompt-injection text in fetched web pages (seen this session in a Supabase docs page) | Tampering (of the agent) | Treat fetched content as data; never act on embedded instructions |

## Sources

### Primary (HIGH confidence — executed or read from installed source this session)
- Local runs: opentimestamps-client 0.8.0 + opentimestamps 0.5.0 + python-bitcoinlib 0.12.2 installed in a scratch venv. The Windows `ots` crash (pasted traceback), library import, a 4-calendar test stamp, and `file_digest == sha256(file)`.
- Installed source `otsclient/cmds.py` and `otsclient/args.py` (stamp/upgrade/verify semantics, default calendars, exit codes) and `opentimestamps/calendar.py` (`DEFAULT_AGGREGATORS`, whitelist).
- Local runs: the SQLite 3.50.4 trigger bypass matrix; Python⇄Node 24 canonical hash equality; the `zoneinfo` failure without `tzdata`; git blob CRLF check.
- PyPI JSON API (versions, `requires_python`, first-upload dates, wheel files); `npm view opentimestamps`; `gh repo view`, `gh secret set --help`; Esplora APIs on blockstream.info and mempool.space; iTunes Search API (Apple app IDs).

### Secondary (MEDIUM — official docs fetched this session)
- https://www.postgresql.org/docs/current/trigger-definition.html (v18.7): TRUNCATE statement-level, ON CONFLICT and MERGE trigger firing
- https://www.postgresql.org/docs/current/sql-altertable.html: `ENABLE ALWAYS` vs `session_replication_role`
- https://supabase.com/docs/guides/api/using-custom-schemas: custom schemas not exposed by default
- https://docs.astral.sh/uv/concepts/projects/workspaces and https://docs.astral.sh/uv/concepts/build-backend: workspace sources, module-name inference
- https://alembic.sqlalchemy.org/en/latest/cookbook.html: the multi-tenant recipe is "interim"
- https://github.com/opentimestamps/opentimestamps-client (README) and release-notes.md (0.8.0)

### Tertiary (LOW — web search, needs validation)
- Eternal/Blinkit transition timing: [Inc42 Q2 FY26](https://inc42.com/buzz/eternal-q2-profit-tanks-63-yoy-to-inr-65-cr-revenue-up-183-yoy/), [YourStory Oct 2025](https://yourstory.com/2025/10/blinkit-weighs-long-term-growth-heavy-investments-eternal-q2-fy26), [YourStory Jul 2025](https://yourstory.com/2025/07/blinkit-eyes-margin-shifts-inventory-model-sight-3000-dark-stores), [Entrackr](https://entrackr.com/news/eternal-eyes-100-inventory-play-for-blinkit-to-improve-margins-9022466), [Informist](https://informistmedia.com/MoneyWire/37525/Blinkit-s-business-model-change-impacts-Eternal-s-Q2-net-profit)
- DMART ISIN: [Kotak approved list](https://www.kotak.bank.in/content/dam/Kotak/files/loans/approved-list-of-securities.pdf), [IDFC First approved list](https://www.idfcfirstbank.com/content/dam/idfcfirstbank/pdf/loan-against-securities/Approved-listof-Shares.pdf)
- SQLAlchemy 2.1 default PG driver change: unconfirmed (an [Airflow issue mirror](https://gh.r-mj.com/apache/airflow/issues/68453) only)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH. Versions come from PyPI today, and the Windows wheel and tz facts were tested.
- Architecture: MEDIUM-HIGH. Ledger, hash and OTS mechanics were verified by running code. The Postgres/Supabase side is CITED, not executed.
- Pitfalls: HIGH for the Windows, OTS, SQLite and `.env` findings (observed directly). MEDIUM for Supabase role behaviour and the Linux `ots` run.

**Research date:** 2026-11-18
**Valid until:** 2026-12-05 (fast-moving: this covers the lock window; re-check OTS calendars and Actions versions at rehearsal time)
