---
phase: "01"
slug: "first-baseline-only-lock"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-18"
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `01-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.2.0 + hypothesis 6.170.x + time-machine 3.6.0; Node 24 `node:test` for `web/` golden vectors |
| **Config file** | none — Wave 0 installs (`[tool.pytest.ini_options]` in root `pyproject.toml`, `tests/conftest.py` with `--reader`, backend fixture, hypothesis profiles `dev`/`ci`) |
| **Quick run command** | `uv run pytest tests/leakage tests/ledger tests/data -q -x` |
| **Full suite command** | `uv run pytest -q` (+ `TEST_DATABASE_URL=… uv run pytest -m postgres -q`) + `npm test --prefix web` |
| **Estimated runtime** | ~30 seconds (quick), ~90 seconds (full, SQLite) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/leakage tests/ledger tests/data -q -x`
- **After every plan wave:** Run `uv run pytest -q` + `npm test --prefix web` (+ postgres marker when `TEST_DATABASE_URL` is set)
- **Before `/gsd-verify-work`:** Full suite green on SQLite **and** Postgres; meta-test (leaky reader → exit 1) green; rehearsal run green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Requirement-level map (task IDs are filled in by the planner/executor):

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| FOUND-01 | Fresh-clone setup; dirs exist; `nowcast --help` runs | smoke | `uv sync && uv run nowcast --help` ; `uv run pytest tests/test_layout.py -q` | ❌ W0 | ⬜ pending |
| FOUND-03 | Universe parse/validate; disabling drops a company | unit | `uv run pytest tests/data/test_universe.py -q` | ❌ W0 | ⬜ pending |
| FOUND-04 | Settings normalise URL; `alembic upgrade head` on SQLite + PG | integration | `uv run pytest tests/data/test_db.py -q` ; `uv run alembic upgrade head` | ❌ W0 | ⬜ pending |
| FOUND-05 | Fiscal labels ⇄ dates, round-trip property | unit+property | `uv run pytest tests/leakage/test_fiscal.py -q` | ❌ W0 | ⬜ pending |
| PIT-01/02 | Required columns, no defaults; restatement adds a row | integration | `uv run pytest tests/data/test_store.py -q` | ❌ W0 | ⬜ pending |
| PIT-03 | Reader strict `<`, live `ingested_at`, post-condition | unit | `uv run pytest tests/leakage/test_reader.py -q` | ❌ W0 | ⬜ pending |
| PIT-04 | Reveal calendar derivation and status | unit | `uv run pytest tests/data/test_calendar.py -q` | ❌ W0 | ⬜ pending |
| PIT-05 | Breaks from config reach baseline | unit | `uv run pytest tests/nowcaster/test_baseline.py -k breaks -q` | ❌ W0 | ⬜ pending |
| LEAK-01 | Future-perturbation invariance | property | `uv run pytest tests/leakage/test_invariance.py -q` | ❌ W0 | ⬜ pending |
| LEAK-02 | Leaky readers make the suite exit non-zero | meta | `uv run pytest tests/meta -q` | ❌ W0 | ⬜ pending |
| LEAK-03 | IST/UTC boundary, strict `<` at instant | unit | `uv run pytest tests/leakage/test_time_boundaries.py -q` | ❌ W0 | ⬜ pending |
| LEAK-04 | Splitter: train revealed before cutoff | property | `uv run pytest tests/leakage/test_splits.py -q` | ❌ W0 | ⬜ pending |
| DATA-01 | Whole-file reject with all errors; dry-run; idempotent reload | integration | `uv run pytest tests/data/test_seed_loader.py -q` | ❌ W0 | ⬜ pending |
| FEAT-02 | Break method selection + label | unit | `uv run pytest tests/nowcaster/test_baseline.py -k eternal -q` | ❌ W0 | ⬜ pending |
| BASE-01 | Decimal baseline exact; missing quarter → refusal | unit | `uv run pytest tests/nowcaster/test_baseline.py -q` | ❌ W0 | ⬜ pending |
| LEDG-01 | Typed columns == parsed payload | integration | `uv run pytest tests/ledger/test_table.py -q` | ❌ W0 | ⬜ pending |
| LEDG-02 | Golden vectors in Py and JS | unit | `uv run pytest tests/ledger/test_canonical.py -q` ; `npm test --prefix web` | ❌ W0 | ⬜ pending |
| LEDG-03 | Chain links; fork rejected | integration | `uv run pytest tests/ledger/test_chain.py -q` | ❌ W0 | ⬜ pending |
| LEDG-04 | UPDATE/DELETE/REPLACE/TRUNCATE blocked; triggers exist | integration | `uv run pytest tests/ledger/test_triggers.py -q` ; `-m postgres` variant | ❌ W0 | ⬜ pending |
| LEDG-05 | Lock guard refusals; gap record | unit | `uv run pytest tests/ledger/test_lock_guard.py -q` | ❌ W0 | ⬜ pending |
| LEDG-07 | Rules record hash == committed PREREGISTRATION.md | integration | `uv run pytest tests/ledger/test_rules_record.py -q` | ❌ W0 | ⬜ pending |
| LEDG-09 | Export byte-prefix, LF, line == payload | integration | `uv run pytest tests/ledger/test_export.py -q` | ❌ W0 | ⬜ pending |
| LEDG-10 | Proof digest == head hash; upgraded proof confirms | manual + script | `uv run python scripts/ots_explorer_check.py ledger/proofs/<seq>.ots` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Root `pyproject.toml` pytest config + `tests/conftest.py` (backend fixture, `--reader`, hypothesis profiles, PG scratch-schema guard)
- [ ] `tests/fixtures/hash_vectors.json` (accept + reject golden vectors)
- [ ] `tests/leakage/leaky_readers.py`
- [ ] `web/package.json` (`"test": "node --test tests/"`) + `web/tests/canonical.test.ts`
- [ ] Optional `.github/workflows/ci-postgres.yml` (`postgres:17` service)
- [ ] Framework install: `uv sync` (after uv itself is installed)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OTS proof anchored in Bitcoin | LEDG-10 | Needs real time for Bitcoin confirmation; no local Bitcoin node | After the Actions upgrade run reports complete, run `scripts/ots_explorer_check.py` and confirm the merkle root matches on two explorers |
| Live Supabase migration | FOUND-04 | Needs the user's corrected `.env` credentials | `uv run alembic upgrade head` with production `DATABASE_URL`; `uv run nowcast db check` |
| Witness commit on public GitHub | LEDG-09 | Pushes to the user's public repo | Confirm commit URL and file contents on GitHub after the lock run |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
