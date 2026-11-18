---
phase: 01-first-baseline-only-lock
plan: "01"
subsystem: infra
tags: [uv, uv-workspace, pyproject, gitattributes, supply-chain, python-3.12]

# Dependency graph
requires: []
provides:
  - "uv workspace root `called-it` (package = false) with members `data` (calledit-data) and `nowcaster` (called-it-nowcaster)"
  - "Exact == pins for every direct dependency, approved by the user at the package-legitimacy gate"
  - "Dependency groups: `dev` (default) and `ots` (non-default, Linux CI only)"
  - "Console script entry `nowcast = \"nowcaster.cli:app\"` (module arrives in Plan 01-02)"
  - "pytest config (testpaths tests, --strict-markers, markers postgres/slow) and ruff config (py312, line-length 100)"
  - ".gitattributes freezing byte-stable hashed paths (-text) and *.ots as binary, committed before any hashed file exists"
  - "Extended .gitignore (keeps .env rules) and a non-secret .env.example"
  - "Local default branch renamed to main (D-28)"
affects: [01-02, 01-08, 01-09, 01-10, 01-11, ledger, ots-witness, seed-data]

# Actuals (#2632): chars/4 over the realized diff (2436 chars across the 7 changed files)
actuals:
  tokens: 609
  tasks: 2
  commits: 2  # MEASURED: git rev-list --count 45f93e9..HEAD (1 task commit 64a42f0 + the orchestrator's merge commit 6d81731)
plan_head_before: 45f93e9c42d81d9d0451c823716d4d54efbfc9ab
plan_head_after: 6d81731980799207c2bd1cdceb191f47de94b72a

# Tech tracking
tech-stack:
  added:
    - "uv 0.13.9 (installed by the user; toolchain only, nothing synced yet)"
    - "Pinned (declared, not yet installed): sqlalchemy 2.1.9, alembic 1.20.1, psycopg[binary] 3.3.9, pydantic 2.14.3, pydantic-settings 2.16.3, tzdata 2026.6, typer 0.29.1"
    - "Pinned dev group: pytest 9.2.0, hypothesis 6.170.15, time-machine 3.6.0, ruff 0.17.5, opentimestamps 0.5.0"
    - "Pinned ots group: opentimestamps-client 0.8.0"
    - "Build backend: uv_build >=0.13.9,<0.14"
  patterns:
    - "Virtual uv workspace root with `{ workspace = true }` sources; import names calledit_data and nowcaster (never a top-level `data` package)"
    - "Every direct dependency pinned with ==; new packages pass a human package-legitimacy gate before the first install"
    - "Hashed artefacts are byte-stable via .gitattributes -text / binary, set before the files exist"

key-files:
  created:
    - pyproject.toml
    - data/pyproject.toml
    - nowcaster/pyproject.toml
    - .python-version
    - .gitattributes
    - .env.example
  modified:
    - .gitignore

key-decisions:
  - "User approved the exact pinned package set on 2026-11-18 (reply: \"approved\"); no package dropped or changed"
  - "ots group kept out of default-groups because the ots CLI crashes on Windows; it installs only via `uv sync --group ots` on the Linux runner"
  - "pandas, numpy, scikit-learn and httpx deliberately not declared in Phase 1; they arrive with the phases that use them"

patterns-established:
  - "Package-legitimacy gate: exact pins reviewed by a human against PyPI before any `uv sync`"
  - "Byte-stable hashed files: .gitattributes rules precede every hashed artefact"

requirements-completed: [FOUND-01]

coverage:
  - id: D1
    description: "Workspace manifests (root + two members) with exact pins, dependency groups, nowcast script, pytest and ruff config"
    requirement: "FOUND-01"
    verification:
      - kind: other
        ref: "grep -c '==' data/pyproject.toml (6); grep -c 'module-name = \"nowcaster\"' nowcaster/pyproject.toml (1); grep -c 'opentimestamps-client==0.8.0' pyproject.toml (1); no default-groups lists ots; TOML parses"
        status: pass
    human_judgment: false
  - id: D2
    description: ".gitattributes marks the 5 hashed paths -text and *.ots binary, committed before any hashed file exists"
    requirement: "FOUND-01"
    verification:
      - kind: other
        ref: "git check-attr text -- PREREGISTRATION.md config/universe.toml ledger/ledger.jsonl data/seed/quarterly_revenue.csv tests/fixtures/hash_vectors.json (5x text: unset); git check-attr binary -- ledger/proofs/0.ots (binary: set)"
        status: pass
    human_judgment: false
  - id: D3
    description: ".env stays ignored and untracked; .env.example holds only a non-secret example URL"
    requirement: "FOUND-01"
    verification:
      - kind: other
        ref: "git check-ignore -q .env && test -z \"$(git ls-files .env)\""
        status: pass
    human_judgment: false
  - id: D4
    description: "Local default branch is main (D-28)"
    requirement: "FOUND-01"
    verification:
      - kind: other
        ref: "git branch --show-current in C:/called-it prints main (run by the orchestrator after `git branch -m master main`)"
        status: pass
    human_judgment: false
  - id: D5
    description: "uv installed and the pinned package set approved at the package-legitimacy gate"
    requirement: "FOUND-01"
    verification:
      - kind: manual_procedural
        ref: "uv --version -> uv 0.13.9 (6b2d39dcc 2026-11-17); user reply \"approved\" on 2026-11-18; orchestrator HTTP 200 on pypi.org/pypi/<pkg>/<ver>/json for every pin"
        status: pass
    human_judgment: true
    rationale: "Package legitimacy is a human supply-chain judgement (blocking-human gate); it was given by the user and is recorded here"

# Metrics
duration: ~2h10m wall clock (including the human gate wait)
completed: 2026-11-18
status: complete
---

# Phase 1 Plan 01: Workspace Manifests and Package-Legitimacy Gate Summary

**A uv workspace (`called-it` root, `calledit-data` and `called-it-nowcaster` members) with 14 exact pins that the user approved. `.gitattributes` makes the hashed paths byte-stable before any of them exist, and the local branch is now `main`. Nothing is installed yet. Plan 01-02 runs the first `uv sync`.**

## Performance

- **Duration:** about 2h10m wall clock, most of it waiting at the blocking-human gate
- **Started:** 2026-11-18T12:03:55Z (Task 1 commit time; the plan started shortly before)
- **Completed:** 2026-11-18T14:14:40Z
- **Tasks:** 2/2 (Task 1 auto, Task 2 checkpoint:human-verify with gate="blocking-human")
- **Files modified:** 7 (6 created, 1 modified)

## Accomplishments

- Wrote the root `pyproject.toml`. It is a non-package uv workspace with members `data` and `nowcaster`, workspace sources, a `dev` group (installed by default) and an `ots` group (not installed by default). It also holds the pytest settings (markers `postgres` and `slow`) and the ruff settings.
- Wrote `data/pyproject.toml` (`calledit-data`) with 6 exact pins and the `uv_build` backend.
- Wrote `nowcaster/pyproject.toml` (`called-it-nowcaster`) with the `nowcast` script and `module-name = "nowcaster"`.
- `.gitattributes` freezes PREREGISTRATION.md, config/universe.toml, ledger/**, data/seed/*.csv and tests/fixtures/hash_vectors.json as `-text`, and `*.ots` as `binary`. It was committed before any hashed file exists (mitigates T-01-02).
- `.gitignore` is extended and still starts with `.env`, `.env.*`, `!.env.example`. `.env.example` holds only a placeholder URL. `.env` was never opened (mitigates T-01-01).
- Package-legitimacy gate passed (mitigates T-01-SC):
  - The user replied **"approved"** on 2026-11-18 to the exact set: SQLAlchemy 2.1.9, alembic 1.20.1, psycopg[binary] 3.3.9, pydantic 2.14.3, pydantic-settings 2.16.3, tzdata 2026.6, typer 0.29.1, pytest 9.2.0, hypothesis 6.170.15, time-machine 3.6.0, ruff 0.17.5, opentimestamps 0.5.0, opentimestamps-client 0.8.0 (ots group), uv_build >=0.13.9,<0.14.
  - The orchestrator confirmed that every exact version exists on PyPI (HTTP 200 on `pypi.org/pypi/<pkg>/<ver>/json`).
  - The committed manifests were re-checked against the approved list, and every pin matches.

## Task Commits

1. **Task 1: Workspace manifests, byte-stable git attributes, branch main** - `64a42f0` (chore). It was merged into main as `6d81731`.
2. **Task 2: Install uv and approve the pinned package set (package-legitimacy gate)** has no commit. It is a human gate with no file changes, and uv was installed by the user. `uv --version` printed `uv 0.13.9 (6b2d39dcc 2026-11-17 x86_64-pc-windows-msvc)`.

**Plan metadata:** recorded in the commit that adds this SUMMARY (docs(01-01)).

## Files Created/Modified

- `pyproject.toml`: workspace root (package = false), workspace sources, `dev` and `ots` groups, pytest and ruff config
- `data/pyproject.toml`: calledit-data manifest (sqlalchemy, alembic, psycopg[binary], pydantic, pydantic-settings, tzdata)
- `nowcaster/pyproject.toml`: called-it-nowcaster manifest (calledit-data, typer, pydantic) with the `nowcast` script
- `.python-version`: `3.12`
- `.gitattributes`: `-text` rules for the hashed paths and `*.ots binary`
- `.gitignore`: keeps the three `.env` rules and adds the db, venv, cache, `*.ots.bak` and `web/node_modules/` ignores
- `.env.example`: a non-secret `DATABASE_URL` placeholder for the Supabase session pooler

## Task 1 Verification Results (all PASS)

- `git check-attr text` prints `text: unset` for all 5 hashed paths (PREREGISTRATION.md, config/universe.toml, ledger/ledger.jsonl, data/seed/quarterly_revenue.csv, tests/fixtures/hash_vectors.json).
- `git check-attr binary -- ledger/proofs/0.ots` prints `binary: set`.
- `git check-ignore -q .env` exits 0, and `git ls-files .env` is empty (ignored and untracked).
- The plan greps pass:
  - `grep -c '==' data/pyproject.toml` returns 6.
  - `module-name = "nowcaster"` appears once.
  - `opentimestamps-client==0.8.0` appears once.
  - No `default-groups` lists `ots`.
- All three TOML manifests parse.
- `git ls-files --eol` shows `i/lf w/lf` for the committed text files.
- `git branch --show-current` in C:/called-it prints `main`. This was checked after the orchestrator renamed the branch (see Deviation 1).

## Decisions Made

- The user approved the pinned set unchanged on 2026-11-18. No package was dropped or substituted.
- The `ots` group stays out of `default-groups`, so the Windows dev setup never installs the ots CLI, which crashes there (RESEARCH Pitfall 2).
- No pandas, numpy, scikit-learn or httpx in Phase 1 (RESEARCH line 120).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] D-28 branch rename deferred out of the worktree, then done by the orchestrator**
- **Found during:** Task 1
- **Issue:** The executor runs in an isolated agent worktree on the branch `worktree-agent-*`. Running `git branch -M main` there would rename the agent branch, not the repo's default branch. The worktree commit guards also forbid committing on `main`.
- **Fix:** The executor deferred the rename. Once the Task 1 commit had been merged, the orchestrator ran `git branch -m master main` in C:/called-it.
- **Verification:** `git branch --show-current` in C:/called-it prints `main`. **Resolved.**
- **Committed in:** n/a. This is a ref rename with no file changes.

**2. [Minor - hygiene] .gitignore line endings normalized CRLF to LF**
- **Found during:** Task 1
- **Issue:** The existing `.gitignore` had CRLF line endings.
- **Fix:** The file was rewritten with LF endings while it was being extended. The three original lines are unchanged.
- **Verification:** `git ls-files --eol .gitignore` prints `i/lf w/lf`, and the file still starts with `.env`, `.env.*`, `!.env.example`.
- **Committed in:** 64a42f0 (part of the Task 1 commit)

---

**Total deviations:** 2 (1 blocking-ordering issue resolved by the orchestrator, 1 cosmetic normalization)
**Impact on plan:** None on scope. The branch outcome required by D-28 holds, and no hashed file existed when the line endings changed.

## Issues Encountered

None beyond the deviations above.

## User Setup Required

All done by the user:
- **uv installed:** `uv 0.13.9`.
- **Supabase password rotated and `.env` fixed** (DATABASE_URL and TEST_DATABASE_URL). This was parallel step (b) of the plan objective. The executor never opened, read or printed `.env`.
- Still open for later plans: (c) `gh secret set DATABASE_URL --repo KASHITOp/called-it` (Plan 01-11) and (d) checking the seed rows against the filing PDFs (Plans 01-09 and 01-10).

## Next Phase Readiness

- Plan 01-02 can run the first `uv sync`. It will resolve and lock exactly the approved pins plus their transitive dependencies into `uv.lock`, and CI will then enforce that lock with `uv sync --locked`.
- Plan 01-08 Task 1 should not need to pause for the DB password, because the rotation and the `.env` fix are already done.
- No blockers.

---
*Phase: 01-first-baseline-only-lock*
*Completed: 2026-11-18*

## Self-Check: PASSED

- FOUND: pyproject.toml, data/pyproject.toml, nowcaster/pyproject.toml, .python-version, .gitattributes, .gitignore, .env.example
- FOUND: commit 64a42f0 is an ancestor of HEAD (merged as 6d81731)
