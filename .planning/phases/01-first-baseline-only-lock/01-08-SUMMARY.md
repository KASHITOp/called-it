---
phase: 01-first-baseline-only-lock
plan: "08"
subsystem: postgres
status: complete
tags: [postgres, supabase, triggers, rls, scratch-schema, ci]

requires:
  - phase: 01-02
    provides: "ledger table, append-only triggers, db check, Alembic 0001"
  - phase: 01-04
    provides: "series/observations/reveal_events, Alembic 0002"
provides:
  - "nowcast db check on Postgres: 8 triggers ENABLE ALWAYS, replication role, RLS on 4 tables, anon/authenticated schema privileges"
  - "Guarded scratch-schema test fixtures (calledit_test_<hex> only) and 35 postgres-marked tests"
  - ".github/workflows/ci-postgres.yml: sqlite, postgres:17 and ots-smoke jobs"
affects: [01-11, 01-12, 01-13]

key-files:
  created:
    - tests/postgres/conftest.py
    - tests/postgres/test_pg_ledger.py
    - tests/postgres/test_pg_store_and_check.py
    - tests/ledger/test_db_check_pg_logic.py
    - .github/workflows/ci-postgres.yml
  modified:
    - data/src/calledit_data/db/check.py
    - data/src/calledit_data/db/schema.py

requirements-completed: [FOUND-04, LEDG-04]
plan_head_before: 2e5c659aa8636531d22fdbb9e4c3216617b634f3
---

# Plan 01-08 summary: the ledger and store on real Postgres

## What was verified live (Supabase, user-authorised, scratch schemas only)

- `CALLEDIT_ENV=rehearsal nowcast db check --connect-only`: `connect: ok`, `result: OK`, no host or user in output.
- `CALLEDIT_REQUIRE_PG=1 pytest tests/postgres -m postgres`: 35 tests, 0 skips. UPDATE, DELETE, TRUNCATE, upsert and MERGE are refused on predictions, observations and reveal_events. `replica_role outcome: SET allowed; UPDATE still refused (ENABLE ALWAYS)`.
- `alembic upgrade head` on the `calledit_rehearsal` schema ran 0001 and 0002; a second run was a no-op.
- Full `nowcast db check` on `calledit_rehearsal`: all 8 triggers ok, replication_role ok, RLS ok on 4 tables, anon_usage ok, authenticated_usage ok, `result: OK`.
- `tests/postgres/test_pg_ledger.py -k assert_scratch_schema`: 19 passed with no database.

## Deviations

1. **Task 1 checkpoint:** the first `.env` URL failed the strict RFC 3986 check in settings (brackets in the userinfo). The user fixed it; the check was not weakened.
2. **Test bug fixed:** `test_db_check_fails_on_disabled_trigger` counted the trailing `result: FAIL` line as a second failure. The product was correct; the test now excludes the last line.
3. Extra check line `authenticated_usage` beyond the plan's `anon_usage`.
4. In the main checkout a plain `pytest` falls back to `.env` and runs the postgres tests; use `-m "not postgres"` to avoid that.

## Not verified

- `.github/workflows/ci-postgres.yml` has not run on GitHub and its YAML was not parsed (Plan 01-11 publishes the repo and exercises it).
- Live Postgres run covered the rehearsal schema and scratch schemas, not the production `calledit` schema.

## Tests

`uv run pytest -q -m "not postgres"`: 463 passed. `uv run ruff check .`: all checks passed.
