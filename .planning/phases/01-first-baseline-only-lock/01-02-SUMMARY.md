---
phase: 01-first-baseline-only-lock
plan: "02"
subsystem: ledger
tags: [walking-skeleton, sqlite, alembic, sqlalchemy-core, hash-chain, canonical-json, golden-vectors, node-test, append-only]

# Dependency graph
requires:
  - phase: 01-01
    provides: "uv workspace manifests with the approved exact pins, .gitattributes for hashed paths"
provides:
  - "uv.lock (first resolution: 42 packages; direct deps = exactly the approved pins)"
  - "calledit_data.db: Settings/get_settings/require_live_write_context/LiveContextError, make_engine, UTCDateTime, DecimalText, metadata/predictions, run_db_check/DbCheckReport"
  - "Alembic 0001_ledger: predictions + SQLite triggers predictions_no_update/_no_delete/_no_replace; PG forbid_mutation(), predictions_no_update_delete, predictions_no_truncate, ENABLE ALWAYS, RLS, anon/authenticated revokes"
  - "nowcaster.ledger: calledit-ledger-v1 canonical (SCHEME, GENESIS_PREV_HASH, validate, canonicalize, sha256_hex, format_money/ratio/ts/date/int), records (build_rules_payload, TypedColumns), chain (read_head, append_record, ForkError, RecordError), export (export_ledger, ExportReport, ExportError)"
  - "nowcaster.clock.now_utc (sole wall-clock reader), nowcaster.rules.append_rules_record"
  - "CLI: nowcast db check [--connect-only], nowcast rules [--document] [--universe] [--dry-run], nowcast ledger export [--out]"
  - "tests/fixtures/hash_vectors.json (18 accept, 20 reject, 27 formatting) shared by pytest and node --test"
  - "web/src/lib/canonical.ts (validate, canonicalize, sha256Hex) for the Phase 5 browser verifier"
affects: [01-03, 01-04, 01-05, 01-06, 01-07, 01-08, 01-10, 01-11, 01-12, 01-13, phase-02-verifier, phase-05-browser-verify]

# Actuals (#2632): chars/4 over the realized diff
actuals:
  tokens: 27836   # 111342 chars of hand-written files / 4; uv.lock (182197 chars, generated) excluded. Including uv.lock: 73385
  tasks: 3
  commits: 4      # MEASURED: git rev-list --count 71a119f..HEAD (before the SUMMARY commit)
plan_head_before: 71a119fb21c3fa34e585655df1947549b5d53473
plan_head_after: 892f2174a89a4f8c7e4f8e0884deb308544b8aff

# Tech tracking
tech-stack:
  added:
    - "Installed for the first time (approved pins): sqlalchemy 2.1.9, alembic 1.20.1, psycopg[binary] 3.3.9, pydantic 2.14.3, pydantic-settings 2.16.3, tzdata 2026.6, typer 0.29.1, pytest 9.2.0, hypothesis 6.170.15, time-machine 3.6.0, ruff 0.17.5, opentimestamps 0.5.0"
    - "Managed CPython 3.12.16 (uv)"
    - "Node 24.21 native type stripping for web/ tests (zero npm dependencies)"
  patterns:
    - "All-string calledit-ledger-v1 payloads; hash the stored payload_canonical, never a re-serialised dict"
    - "Hand-written Alembic migrations, frozen column types, no batch mode; dialect-branched trigger DDL behind a regex-validated schema identifier"
    - "Fixed, value-free error messages plus exception class names wherever a DB URL could leak"
    - "Single-writer append: BEGIN IMMEDIATE (SQLite) / pg_advisory_xact_lock (PG) around read-head-then-insert, backed by UNIQUE(seq/hash/prev_hash)"
    - "Tests run in a scrubbed env and a temp cwd so a developer .env (live Supabase URL) is never read"

key-files:
  created:
    - alembic.ini
    - data/migrations/env.py
    - data/migrations/script.py.mako
    - data/migrations/versions/0001_ledger.py
    - data/src/calledit_data/db/settings.py
    - data/src/calledit_data/db/engine.py
    - data/src/calledit_data/db/types.py
    - data/src/calledit_data/db/schema.py
    - data/src/calledit_data/db/check.py
    - nowcaster/src/nowcaster/clock.py
    - nowcaster/src/nowcaster/cli.py
    - nowcaster/src/nowcaster/rules.py
    - nowcaster/src/nowcaster/ledger/canonical.py
    - nowcaster/src/nowcaster/ledger/records.py
    - nowcaster/src/nowcaster/ledger/chain.py
    - nowcaster/src/nowcaster/ledger/export.py
    - tests/conftest.py
    - tests/test_layout.py
    - tests/ledger/helpers.py
    - tests/ledger/test_skeleton_e2e.py
    - tests/ledger/test_canonical.py
    - tests/ledger/test_chain.py
    - tests/ledger/test_triggers_sqlite.py
    - tests/ledger/test_table.py
    - tests/ledger/test_export.py
    - tests/ledger/test_migrations.py
    - tests/fixtures/hash_vectors.json
    - web/package.json
    - web/src/lib/canonical.ts
    - web/tests/canonical.test.ts
    - uv.lock
    - .github/workflows/.gitkeep
  modified:
    - pyproject.toml

key-decisions:
  - "calledit-ledger-v1 rules field set frozen as: scheme, seq, record_kind, rules_id, document_path, document_sha256, document_git_commit, universe_path, universe_sha256, recorded_at, run_id, prev_hash (one-way at the first live write, 01-12)"
  - "Non-live dev on Postgres defaults to schema calledit_dev; CALLEDIT_ENV=test on Postgres must name calledit_test_<hex> explicitly"
  - "DATABASE_URL is cross-checked with urllib.parse.urlsplit because SQLAlchemy make_url is lenient with unencoded '@', '#', '/' and brackets in passwords"
  - "nowcast db check reports FAIL on Postgres without --connect-only until Plan 01-08 adds the PG trigger/RLS checks (no false OK)"
  - "0001_ledger downgrade raises: the ledger table is never dropped by a migration"
  - "ledger.jsonl must be a whole-line byte-prefix of the new export; a file cut mid-line is refused, not silently completed"

patterns-established:
  - "Golden vectors: Python generates, both languages verify, an independent probe hash anchors the generator"
  - "Mutation tests match on the 'append-only' message via sqlalchemy.exc.DBAPIError, never on the backend exception class"

requirements-completed: [FOUND-01, FOUND-04, LEDG-01, LEDG-02, LEDG-03, LEDG-04, LEDG-09]

coverage:
  - id: D1
    description: "Fresh clone: uv sync --locked, alembic upgrade head, nowcast db check -> result: OK on SQLite"
    requirement: "FOUND-01"
    verification:
      - kind: other
        ref: "git clone . build/fresh-clone && uv --directory build/fresh-clone sync --locked && ... run alembic upgrade head && ... run nowcast db check (UV_PYTHON=3.12.16, see Deviation 1) -> backend: sqlite ... result: OK, exit 0; 144 passed inside the clone"
        status: pass
    human_judgment: false
  - id: D2
    description: "One config flag switches SQLite/Postgres; live refuses SQLite; schema identifiers validated at the boundary"
    requirement: "FOUND-04"
    verification:
      - kind: test
        ref: "tests/ledger/test_skeleton_e2e.py::test_live_with_sqlite_is_refused, ::test_schema_rules_refuse, ::test_schema_rules_accept, ::test_bad_url_refusal_never_echoes_the_url"
        status: pass
    human_judgment: false
  - id: D3
    description: "predictions table with typed columns that equal the canonical payload"
    requirement: "LEDG-01"
    verification:
      - kind: test
        ref: "tests/ledger/test_table.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "Python and JS agree on every accept vector and reject every reject vector; probe hash 3274e090...d99e in both"
    requirement: "LEDG-02"
    verification:
      - kind: test
        ref: "uv run pytest tests/ledger/test_canonical.py (68 passed); npm test --prefix web (# pass 41, # fail 0, no node_modules)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Fork rejection in the app (ForkError) and at the DB (UNIQUE prev_hash/seq, replace guard)"
    requirement: "LEDG-03"
    verification:
      - kind: test
        ref: "tests/ledger/test_chain.py"
        status: pass
    human_judgment: false
  - id: D6
    description: "Six SQLite mutation forms blocked with recursive_triggers=OFF; triggers survive a second upgrade; no batch mode"
    requirement: "LEDG-04"
    verification:
      - kind: test
        ref: "tests/ledger/test_triggers_sqlite.py (6 parametrized ids), tests/ledger/test_migrations.py"
        status: pass
    human_judgment: false
  - id: D7
    description: "ledger.jsonl export: verified chain, whole-line byte-prefix, atomic, empty refusal, LF only"
    requirement: "LEDG-09"
    verification:
      - kind: test
        ref: "tests/ledger/test_export.py"
        status: pass
    human_judgment: false

# Metrics
duration: ~42m
completed: 2026-11-18
status: complete
---

# Phase 1 Plan 02: Walking Skeleton and calledit-ledger-v1 Hash Contract Summary

**A `rules` record now goes end to end on SQLite. `nowcast rules` appends it to an append-only `predictions` table, hash-chained under `calledit-ledger-v1`, and `nowcast ledger export` writes it as one LF line whose SHA-256 equals the stored hash. 65 shared golden vectors pin the hash contract in Python and in a zero-dependency TypeScript twin.**

## Performance

- **Duration:** about 42 minutes
- **Started:** 2026-11-18T14:18:58Z
- **Completed:** 2026-11-18T15:00:22Z
- **Tasks:** 3/3 (Task 1 tracer, Tasks 2 and 3 TDD)
- **Files:** 33 created, 1 modified (plus the generated uv.lock)

## Accomplishments

- **First `uv sync` and committed `uv.lock`.** The lock resolves 42 packages. The direct dependencies are exactly the pins approved in 01-01, and everything else is transitive. `uv sync --locked` reproduces the lock in a fresh clone.
- **DB layer (`calledit_data.db`).**
  - `Settings` holds `DATABASE_URL` as a `SecretStr` with inputs hidden from validation errors. Every error message is fixed and contains no part of the URL. The validator rewrites `postgres://` and `postgresql://` to `postgresql+psycopg://`.
  - Environment guards: `live` refuses SQLite (D-17) and always uses `calledit`. `rehearsal` always uses `calledit_rehearsal`. dev/test on Postgres must use `calledit_(dev|ci|test_<hex>)`. Only `live` may name `calledit`. Only non-live envs may override the ledger dir.
  - `make_engine` sets the SQLite pragmas (`foreign_keys`, `recursive_triggers`, WAL) on every connection, and on Postgres maps tables to the effective schema.
  - `UTCDateTime` and `DecimalText` are strict types: naive datetimes and float money are rejected.
- **Migration 0001.** It creates `predictions` (LEDG-01 columns, with no CHECK on `record_kind`).
  - SQLite: three `RAISE(ABORT, 'calledit: predictions is append-only (<op>)')` triggers. The `BEFORE INSERT` replace guard keys on seq, hash or prev_hash.
  - Postgres: `forbid_mutation()` plus row and TRUNCATE triggers, both `ENABLE ALWAYS`, then RLS and the guarded anon/authenticated `REVOKE`s. The Postgres branch is written but not yet run; Plan 01-08 exercises it.
  - Downgrade raises, so no migration can ever drop the ledger.
- **Ledger package.**
  - Canonicaliser and format helpers (ROUND_HALF_EVEN; negative zero normalised to `0.00`).
  - Rules builder with a frozen 12-field set.
  - Single-writer `append_record`: it takes the write lock first, raises `ForkError` on a stale or zero `prev_hash` and `RecordError` on seq or kind mismatches.
  - `export_ledger`: it re-verifies the whole chain (seq contiguity, hash, links, canonical re-encoding, snapshot hashes) and enforces the whole-line byte-prefix rule before an atomic write.
- **CLI:** `nowcast db check | rules | ledger export`. Every failure exits non-zero with a fixed message.
- **JS twin:** `web/src/lib/canonical.ts` runs under `node --test` with Node 24 type stripping and has no npm dependencies.

## Task Commits

1. **Task 1: Tracer (fresh clone to exported rules record)**: `ced118d` (feat)
2. **Task 2: Golden vectors shared by Python and JS**: `de08c8a` (test, RED: the vectors file was missing, so collection failed) and `f5d527e` (feat, GREEN)
3. **Task 3: Ledger integrity suite**: `892f217` (test, plus the export.py fix that the suite exposed)

**Plan metadata:** the docs(01-02) commit that adds this SUMMARY.

## Verification (exact output)

- `uv run pytest -q` reports **`144 passed in 11.99s`** (the same in the fresh clone: `144 passed in 12.68s`).
- `uv run pytest tests/ledger -q` reports `136 passed in 11.37s`.
- `npm test --prefix web` reports `ℹ pass 41`, `ℹ fail 0`, and no `node_modules` directory exists.
- Fresh-clone chain: `uv sync --locked`, then `alembic upgrade head`, then `nowcast db check`. It prints `backend: sqlite`, `triggers: ok (...)` and `result: OK`, and exits 0. No postgresql host is printed.
- `uv run nowcast --help` lists `rules`, `db` and `ledger`.
- Acceptance greps:
  - `hide_input_in_errors=True` appears 1 time in settings.py.
  - `recursive_triggers=ON` appears 2 times in engine.py (at least 1 is required).
  - The probe hash appears 1 time in hash_vectors.json.
  - The non-ASCII byte grep finds 0 matches.
  - `git ls-files uv.lock` prints `uv.lock`.
- `uv run ruff check .` reports `All checks passed!`.

## TDD Gate Compliance

- Task 2 RED (`de08c8a`): `test_canonical.py` was committed before `hash_vectors.json` existed, and collection failed with FileNotFoundError. GREEN (`f5d527e`): 68 Python tests and 41 JS tests pass.
- Task 3 had no separate RED commit, because it writes tests against Task 1 code that already existed. The suite did fail once, on `test_non_prefix_ledger_file_aborts_without_writing[truncated]`. The fix to `export.py` went into the same commit as the tests (`892f217`).

## Decisions Made

See `key-decisions` in the frontmatter. The most consequential: the rules field set and the ledger-line format are now pinned by vectors in two languages. They become one-way at the first live write (01-12).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] uv could not resolve its managed Python 3.12 inside the agent sandbox**
- **Found during:** Task 1 (first `uv sync`) and the fresh-clone verify
- **Issue:** uv failed with `Missing expected target directory for Python minor version link` on the `cpython-3.12-windows-x86_64-none` junction. The junction is valid (Git Bash follows it and the interpreter runs), so this is uv's junction read failing in the sandbox. It is not a project defect.
- **Fix:** The first venv was created by pointing `--python` at the patch install. After that, plain `uv sync` works because it reuses `.venv`. The fresh-clone verify set `UV_PYTHON=3.12.16` (an exact patch request, which skips the minor-version link). The lock, the manifests and `.python-version` are unchanged.
- **Follow-up:** On the user's normal shell (and on Linux CI) a bare `uv --directory build/fresh-clone sync --locked` should work. If it does not, `uv python install --reinstall 3.12` re-creates the link.

**2. [Rule 1 - Bug] `make_url` accepted malformed Postgres URLs**
- **Found during:** Task 1 tests
- **Issue:** SQLAlchemy's `make_url` parsed `user:pw@[bad-host` and an unencoded `@` in a password into *some* host. That defeats the "does not parse (percent-encoding)" message from RESEARCH Pitfall 1.
- **Fix:** The URL is now also split with `urllib.parse.urlsplit`. The hostnames must agree and the port must parse; otherwise validation raises the fixed message. Three parametrized tests check that the secret never appears in the error.
- **Files:** data/src/calledit_data/db/settings.py, tests/ledger/test_skeleton_e2e.py
- **Commit:** ced118d

**3. [Rule 2 - Missing critical] The head read was outside a write lock**
- **Found during:** Task 1
- **Issue:** SQLAlchemy 2.1's pysqlite dialect still uses legacy transaction control, which only issues BEGIN before DML. The head `SELECT` in `append_record` therefore ran unlocked.
- **Fix:** `append_record` now takes the write lock first: `BEGIN IMMEDIATE` on SQLite and `pg_advisory_xact_lock` on Postgres. The DB UNIQUE constraints remain the backstop.
- **Commit:** ced118d

**4. [Rule 1 - Bug] Export would silently "complete" a ledger.jsonl cut mid-line**
- **Found during:** Task 3 (`test_export.py[truncated]`)
- **Issue:** A file missing its final newline is still a byte-prefix of the new bytes.
- **Fix:** The existing file must now be a *whole-line* byte-prefix (empty, or ending in LF).
- **Commit:** 892f217

**5. [Minor - test design] `find_spec("data")` is checked in an isolated interpreter**
- **Issue:** With `--import-mode=prepend` and `tests/__init__.py`, pytest puts the repo root on `sys.path`. The bare `data/` directory then resolves in-process as a namespace package.
- **Fix:** `test_layout.py` asserts `find_spec("data") is None` in a `python -I` subprocess, which reflects the installed environment, and also asserts that `data/__init__.py` does not exist.
- **Commit:** ced118d

**6. [Minor - scope] Extra files and tests beyond the plan's file list**
- Added `tests/ledger/helpers.py`, which holds shared builders and raw-insert helpers for the Task 3 tests.
- Added settings schema-rule tests to `test_skeleton_e2e.py`.
- Added a `fileConfig` call in `env.py`, so `alembic upgrade head` prints its progress.
- The root `pyproject.toml` change is only the `--import-mode=prepend` addopts.

---

**Total deviations:** 6 (2 bugs and 1 missing-critical item auto-fixed, 1 environment blocker worked around, 2 minor).
**Impact on plan:** No scope change. Every fix tightens the integrity or secrecy guarantees.

## Known Stubs

| File | Line | Reason |
|------|------|--------|
| data/src/calledit_data/db/check.py | 76 | On Postgres, `nowcast db check` (without `--connect-only`) reports `triggers: postgresql checks not implemented yet` and `result: FAIL`. This is deliberate: the plan assigns the PG trigger, RLS and replication-role checks to Plan 01-08, and it must not report a false OK. It is recorded in `.planning/WINDOWS.md`. |

## Threat Flags

None. No new network endpoints or auth paths. The Postgres DDL branch was in the plan's threat model (T-01-09), and it interpolates only the regex-validated schema name.

## Issues Encountered

None beyond the deviations above. `.env` was never opened, read or printed. Tests scrub `DATABASE_URL`, `CALLEDIT_*` and `GITHUB_*` and run in a temp cwd, so the main checkout's `.env` cannot influence them.

## Next Phase Readiness

- Plans 01-03 onward can import the binding interfaces listed under `provides`.
- Plan 01-08 must still:
  - run the Postgres branch of 0001 against a scratch schema,
  - add the PG trigger, RLS and replication-role checks to `run_db_check` (replacing the Known Stub),
  - exercise the `%`-bearing PL/pgSQL through psycopg.
- On a Windows dev shell with no `.venv`, the fresh-clone verify may need `UV_PYTHON=3.12.16` (Deviation 1).

---
*Phase: 01-first-baseline-only-lock*
*Completed: 2026-11-18*

## Self-Check: PASSED

- FOUND: alembic.ini, 0001_ledger.py, settings.py, chain.py, export.py, hash_vectors.json, canonical.ts, uv.lock
- FOUND: commits ced118d, de08c8a, f5d527e, 892f217 are ancestors of HEAD
