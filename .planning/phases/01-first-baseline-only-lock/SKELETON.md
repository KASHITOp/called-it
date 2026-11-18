# Walking Skeleton — CALLED IT. Earnings Nowcaster

**Phase:** 1
**Generated:** 2026-11-18

## Capability Proven End-to-End

On a fresh clone, one command (`uv sync`) installs the workspace, `uv run alembic upgrade head` creates the append-only ledger table, `uv run nowcast rules` appends a SHA-256 hash-chained `rules` record, and `uv run nowcast ledger export` writes it as one canonical line in `ledger.jsonl` whose hash the Python and JS (`npm test --prefix web`) golden-vector tests both reproduce. Plan 01-02 proves this on SQLite. Plans 01-03..01-13 grow it, one vertical slice at a time, into the live Q3 FY27 baseline-only lock on Supabase. That lock is witnessed by a GitHub commit and an OpenTimestamps proof.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Runtime and packaging | Python 3.12 (`.python-version`), uv workspace: a non-package root (`[tool.uv] package = false`) plus members `data/` (dist `calledit-data`, import `calledit_data`) and `nowcaster/` (dist `called-it-nowcaster`, import `nowcaster`, `module-name = "nowcaster"`). `src/` layout, `uv_build` backend | One `uv sync`, one `uv.lock`. The vol-surface engine and the terminal (projects 2 and 3) add members later. Calling the import package `calledit_data` instead of `data` avoids name collisions (CLAUDE.md) |
| Data layer | SQLAlchemy 2.1 **Core** (no ORM) + hand-written Alembic migrations (no batch mode) in `data/migrations/`. Root `alembic.ini` | One code path for SQLite and Postgres. Triggers live in the migrations, so both backends get them. Batch mode would silently drop the triggers |
| Storage switch | `DATABASE_URL` (pydantic-settings, `SecretStr`, `hide_input_in_errors`). The default is `sqlite:///data/local.db`. `CALLEDIT_ENV` is one of `dev`, `test`, `rehearsal` or `live`. The Postgres schema is `calledit` (live), `calledit_rehearsal`, or `calledit_test_<hex>`/`calledit_dev`/`calledit_ci` | FOUND-04 one flag. Live refuses SQLite (D-17). A non-live run can never target the `calledit` schema (D-21) |
| System of record | Supabase Postgres, private schema `calledit`, RLS on with no policies, REVOKE from anon/authenticated. Each schema has the `forbid_mutation()` row and TRUNCATE triggers, set to `ENABLE ALWAYS`. SQLite is for dev and tests only (D-16) | Not exposed through PostgREST. The triggers survive `session_replication_role=replica` |
| Time | All instants are tz-aware UTC (`UTCDateTime` TypeDecorator: fixed-width ISO text on SQLite, `timestamptz` on PG). IST is a fixed `+05:30` offset (`tzdata` installed for parity tests). `nowcaster/clock.py::now_utc()` is the only ambient clock | Leakage needs instant comparisons, never date comparisons |
| Point-in-time store | Insert-only `series` / `observations` / `reveal_events`. Every row carries `period_date`, `available_at`, `ingested_at`, `availability_basis`, `source_ref`, `content_hash`. The only model-facing read path is `calledit_data.pit.PointInTimeReader(engine, as_of, mode)` (strict `<`; live mode adds `ingested_at <= as_of`) | PIT-01..03; the leakage suite targets this single gate |
| Hash contract | `calledit-ledger-v1`: every payload value is a printable-ASCII string, list or dict. Keys match `^[a-z][a-z0-9_]*$`. `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=True)`. Money is 2 dp and ratios 6 dp (`ROUND_HALF_EVEN`). Timestamps are `YYYY-MM-DDTHH:MM:SSZ`. `prev_hash` sits inside the payload (genesis = 64 zeros). hash = SHA-256 of the stored `payload_canonical` | Python and JS produce identical bytes, with no number-formatting divergence. Golden vectors live in `tests/fixtures/hash_vectors.json` |
| Ledger file | `ledger/ledger.jsonl`: each line is exactly one record's `payload_canonical`, LF-terminated. `ledger/snapshots/<seq>.json` holds the canonical feature snapshots. `ledger/proofs/<seq>.ots` holds the OTS proof of the head line's bytes. `.gitattributes` marks hashed files `-text` and `*.ots` binary | The git witness, the OTS proof and the future browser verifier all check the same bytes |
| Record kinds | `rules` (seq 0 = PREREGISTRATION.md hash), `prediction`, `gap` (refused lock, D-08). `annotation` and `universe_change` are reserved. There is no DB CHECK on `record_kind`: a future kind must never need a table rebuild, because a rebuild would drop the triggers | A single hash chain covers all three kinds |
| User interface (Phase 1) | Typer CLI `nowcast` (`db check`, `rules`, `ledger export`, `ledger head`, `universe`, `calendar`, `seed load`, `baseline`, `predict`), plus a JS verifier in `web/src/lib/canonical.ts` tested with Node 24 `node --test` (no npm dependencies) | There are no HTTP routes or web pages in Phase 1. The JS canonicaliser is the contract Phase 5's browser "verify" button reuses |
| Auth | No end-user auth exists in Phase 1. The DB credential lives only in the git-ignored `.env` and the GitHub secret `DATABASE_URL`, and is never printed | ASVS L1. Only Actions writes to the live schema |
| Deployment | GitHub Actions `workflow_dispatch` workflow `.github/workflows/lock.yml` on `ubuntu-24.04`. Actions `rules`, `predict`, `stamp` and `upgrade`; modes `rehearsal` (default) and `live`. `concurrency: ledger`. It commits the witness to `main`. CI is `.github/workflows/ci-postgres.yml` (SQLite job + `postgres:17` service job + `ots` import smoke) | The run log is a server-side timestamp. The `ots` CLI crashes on Windows, so stamping runs on Linux only |
| Directory layout | `config/universe.toml`, `data/` (member + `seed/` + `migrations/`), `nowcaster/` (member), `tests/` (root test tree: `ledger/`, `data/`, `leakage/`, `meta/`, `nowcaster/`, `postgres/`, `fixtures/`), `web/`, `scripts/`, `ledger/`, `.github/workflows/` | FOUND-01 monorepo dirs |
| Git | Default branch `main` (D-28). Origin is `https://github.com/KASHITOp/called-it.git` (D-01). The ruleset on `main` blocks force-push and deletion | Witness URLs use `main` |

## Stack Touched in Phase 1

- [x] Project scaffold: uv workspace, build backend, ruff lint, pytest + hypothesis + time-machine, `node --test` (Plans 01-01, 01-02)
- [x] Routing: no HTTP routing in Phase 1. Its role is filled by the `nowcast` CLI command tree, which is the real user surface (01-02 onward)
- [x] Database: a real write (`rules` / `prediction` / `gap` appends, seed observations) and a real read (`PointInTimeReader`, export). Both run on SQLite (01-02, 01-04) and on Postgres (01-08: Supabase scratch schema + CI `postgres:17`)
- [x] UI: the CLI commands, plus the JS golden-vector verifier in `web/` (01-02)
- [x] Deployment: GitHub Actions dispatch workflow runs the rehearsal (01-11), then live seq 0 (01-12) and the first live lock (01-13) on the public repo

## Out of Scope (Deferred to Later Slices)

- Forward collectors (Apple RSS rank, Play details, careers pages), `collector_runs`, daily cron, weekly-lock cron, heartbeat, daily `ots upgrade` cron, `nowcast official`, the standalone `scripts/verify_ledger.py` (Phase 2: DATA-04..08, LEDG-06, LEDG-11, OPS-02, OPS-03)
- GST and Trends collectors, the feature builder, the walk-forward backtest, the GST 2.0 treatment (Phase 3: DATA-02, DATA-03, FEAT-01, FEAT-03, BACK-01/02, LEAK-05)
- Ridge/GBM, intervals, the model registry, `nowcast grade`, the `grades` table (Phase 4)
- FastAPI, static export, the Next.js broadsheet, Vercel (Phase 5)
- Seed history before Q3 FY25 (12-16 quarters), filled in Phase 2 per D-23
- pandas, which Phase 1 does not install. Baseline maths is exact `Decimal` over typed rows

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- Phase 2: the record runs itself. Forward collectors write into the same PIT store, and weekly locks reuse `nowcast predict` plus `lock.yml` on cron. A verifier recomputes the `calledit-ledger-v1` chain from `ledger/ledger.jsonl`
- Phase 3: real signals. GST/Trends collectors write observations through the same store writer. Features read only through `PointInTimeReader`. The backtest reuses `nowcaster/splits.py`. The GST 2.0 rules record is appended to the same chain
- Phase 4: ridge joins the ledger under its own `model_version`, in the same prediction field set (interval fields already exist). Grading follows the PREREGISTRATION rules
- Phase 5: FastAPI and the static export read the same tables. The browser verify reuses `web/src/lib/canonical.ts` and `tests/fixtures/hash_vectors.json`
- Phase 6: explanation panels render `ledger/snapshots/<seq>.json`. `nowcast run-all` chains the existing commands against a sandbox DB
