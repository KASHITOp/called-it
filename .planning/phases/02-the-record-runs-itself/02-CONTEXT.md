# Phase 2: The Record Runs Itself - Context

**Gathered:** 2026-11-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Forward-only signals build up daily from the first lock onward, and weekly locks, ledger verification, proof upgrades and the redundant final pre-reveal lock run unattended on GitHub Actions, so the Q3 FY27 official calls exist even if the developer is away over the New Year. Covers DATA-04..08, LEDG-06, LEDG-11, OPS-02, OPS-03. It adds no model, no GST/Trends signals and no frontend.

</domain>

<decisions>
## Implementation Decisions

Carried forward from Phase 1 (not re-asked): official call = last valid lock (D-31, PREREGISTRATION section 8); fail loudly (Phase 1 D-17); lock runner is `lock.yml` on `main` with concurrency group `ledger` (Phase 1 D-18); early-bound reveal at `D 00:00 IST` (Phase 1 D-27); never backfill a lock at a past time (Phase 1 D-14); `ci-postgres.yml` already runs the `-m postgres` suite (Phase 1 D-29). Decision numbers below are Phase 2's own.

### Unattended live locks
- **D-01:** A `schedule` trigger on the lock workflow runs `predict` live on `main` with no human `confirm_live`. It runs only if the repo variable `LOCKS_ENABLED` is `true`; otherwise it exits cleanly without writing. The switch pauses every unattended lock without a code change. — **Reversibility:** costly — the schedule and the live-write authority are encoded in the workflow, and PREREGISTRATION section 8 states how live locks run (the Actions workflow on `main`).
- **D-02:** Weekly lock fires **Tuesday 06:00 UTC** (11:30 IST). First scheduled run is 1 Dec if the switch is enabled by then, otherwise 8 Dec 2026. Expect GitHub cron lateness of 5-60 minutes; `locked_at` is always the real clock time.
- **D-03:** Before appending, an unattended lock runs `scripts/verify_ledger.py` on the current ledger and aborts on FAIL, and it also refuses if the rules hash has drifted from seq 0. After appending it re-verifies the new head. It does not run the full test suite on the runner.
- **D-04:** A skipped or failed scheduled lock is never caught up and never backfilled. The watchdog raises an alert and the next scheduled lock proceeds normally. No retries inside a failed lock run.

### Redundant final lock and alerts
- **D-05:** The final pre-reveal lock has **two independent GitHub Actions cron triggers** in separate workflow files, each safe to run alone (the second sees the first and appends a later lock). Both must fall at least 48h before each earliest plausible reveal: DMART by 29 Dec 2026 18:30 UTC, TITAN by 30 Dec 18:30 UTC, ETERNAL by 4 Jan 2027 18:30 UTC. Exact times are the planner's call, e.g. about 72h and 52h before. Both are on GitHub, so a GitHub-wide cron outage is a shared risk to state plainly. — **Reversibility:** costly — dates and cron expressions are encoded in two workflow files.
- **D-06:** A **daily watchdog workflow** checks that every expected lock exists by its deadline and that the last collector run succeeded. On any failure it fails the run and opens or updates a GitHub issue; GitHub emails the owner on both. No external pager and no extra secret.
- **D-07:** The same daily run does a real Supabase query each day, which also keeps the free project from pausing and gives a 1-2 day warning before each final lock. Unreachable means loud failure (Phase 1 D-17), never a local fallback.
- **D-08:** The dry run happens by about 12 Dec, well before mid-December, using the existing lock.yml **rehearsal mode** (scratch Supabase schema plus scratch ledger dir): fire both final-lock triggers by dispatch, run one deliberate failure to confirm the watchdog opens an issue, then discard everything. It must never touch the live ledger.
- **D-09 (watchdog also upgrades proofs):** The daily watchdog automatically upgrades any pending `.ots` proof. It commits upgraded proofs as `github-actions[bot]`, then runs `scripts/ots_explorer_check.py` on each completed proof (before the reveal bound for its head), and alerts through the same issue if a proof is still pending **48h** after its commit, or if the explorer check fails. A pending proof younger than 48h is not an alert. This replaces the manual `upgrade` dispatch from Phase 1 as the routine path; `ots` runs on the Linux runner only. Upgrade commits touch only `ledger/proofs/*.ots`, never `ledger.jsonl`, and share the `ledger` concurrency group so they never race a lock.

### Forward collectors
- **D-10:** Daily collection runs at **02:00 UTC** (07:30 IST). A row belongs to the IST date of the fetch; `available_at` is the real fetch time, so there is no lookahead. Every row is flagged `forward-collected`.
- **D-11:** Careers open-roles: at build time, read each company's careers URL, `robots.txt` and terms. Collect only where allowed; the rest are recorded `unavailable` with the reason. No Naukri, LinkedIn or JobSpy.
- **D-12:** Forward data is stored as insert-only rows in the point-in-time store in Supabase. No daily git export. Each lock's `feature_snapshot` hash pins what it saw.
- **D-13:** A failing source retries 5xx and timeouts up to 3 times with backoff (never 403 or captcha), then records `collector_runs` status `failed` with the error and writes **no** rows. Nothing is carried forward and nothing is synthetic.
- **D-14:** Sources stay as already researched: Apple App Store RSS top-free (India) rank plus `itunes.apple.com/lookup` rating count, Play `app()` details once per app per day with a failure flag, no Play chart scraping. One request per app per day with a descriptive User-Agent.

### Verifier and official call
- **D-15:** `scripts/verify_ledger.py` is a single **stdlib-only** file that re-implements `calledit-ledger-v1` canonicalisation and is tested against the golden vectors. The JS vectors in `web/` remain the second implementation. It does not import `nowcaster`.
- **D-16:** The verifier checks: every line hash and `prev_hash`, seq continuity, each `feature_snapshot` file's SHA-256, `rules_hash` equal to the seq 0 hash, and each `.ots` file's digest equal to its head hash. Offline; explorer checks stay in `ots_explorer_check.py`.
- **D-17:** `nowcast official` derives, per company and quarter, the **last prediction record that is not VOID, locked before `reveal_at` (and before the earliest plausible reveal)**, bound to a valid rules record via its `rules_seq` / `rules_hash` (seq 0 today, not hardcoded, so a future visible rules amendment does not break it). A later gap or refusal never voids an earlier valid prediction; it is shown as a note. No valid lock means "NO OFFICIAL CALL". Derived on read, never stored as a flag. This follows PREREGISTRATION section 8; the `rules_seq` binding and treating a gap record as not a lock are Phase 2 implementation choices consistent with it, to be stated in the docs. — **Reversibility:** one-way — it defines how locked calls are scored.
- **D-18:** Verification runs before and after every lock, in CI on every push, and in the daily watchdog on the public `main` ledger. Any FAIL opens or updates the alert issue.

### Claude's Discretion
- Exact cron minutes for the two final-lock triggers (within the 48h rule), workflow file names, issue labels and titles, `collector_runs` column layout, retry backoff numbers, the Supabase health-query text.
- How `nowcast runs` and `nowcast official` format their output.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Rules and ledger
- `PREREGISTRATION.md` sections 8, 10, 11, 12 - locks, official call, ledger spec, witnesses, change policy
- `.planning/phases/01-first-baseline-only-lock/01-CONTEXT.md` - D-14, D-17, D-18, D-20, D-26, D-27, D-31 (carried forward)
- `.planning/phases/01-first-baseline-only-lock/01-13-SUMMARY.md` - live state, proof status, run history
- `.planning/ROADMAP.md` Phase 2 - goal and 5 success criteria
- `.planning/REQUIREMENTS.md` - DATA-04..08, LEDG-06, LEDG-11, OPS-02, OPS-03

### Workflows and scripts
- `.github/workflows/lock.yml` - lock runner, concurrency group `ledger`, live guards, `LOCK_LEDGER` naming rule
- `.github/workflows/ci-postgres.yml` - Postgres CI
- `scripts/ots_explorer_check.py` - explorer cross-check, exit 0 / 1 / 2
- `tests/scripts/test_lock_workflow.py` - structural guards on the workflow (extend, do not weaken)

### Research
- `.planning/research/` and the Technology Stack section in `.claude/CLAUDE.md` - data-source verdicts for Apple RSS, Play, careers, tenacity, respx

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `nowcaster/src/nowcaster/ledger/chain.py` `append_record(engine, build, guard)`: writer lock plus guard hook for unattended-run checks.
- `nowcaster/src/nowcaster/ledger/head.py`, `nowcast ledger head`: head hash read.
- `data/src/calledit_data/pit` and `store`: insert-only point-in-time store and `PointInTimeReader` for forward observations.
- `scripts/ots_explorer_check.py`: reusable by the watchdog.
- `data/src/calledit_data/db/settings.py`: live vs dev vs rehearsal resolution (`effective_ledger_dir`).

### Established Patterns
- Live runs only on `refs/heads/main` with `CALLEDIT_ENV=live`; the runner commits as `github-actions[bot]`; git witness commit first, then the OTS stamp commit.
- Runner variable names must not collide with Settings field names (a failed live run proved it; a collision test exists).
- Mocked HTTP in collector tests (respx); never hit live sources in tests.

### Integration Points
- New workflows: daily collect, weekly lock, two final-lock triggers, watchdog.
- New code: collectors under `data/`, `collector_runs` table and migration, `nowcast collect --forward`, `nowcast runs`, `nowcast official`, `scripts/verify_ledger.py`.

</code_context>

<specifics>
## Specific Ideas

- Ghost run 45475002224 stays queued on GitHub and is not part of the ledger; build nothing that depends on it.
- The watchdog must detect a run that never fired (a missing lock), which failure emails alone cannot.

</specifics>

<deferred>
## Deferred Ideas

- Seed history back to about Q3 FY23 (12-16 quarters): later phase, ready for the Phase 3 backtest (BACK-01).
- Daily grading and the export commit (OPS-01): Phase 5. Grading (LEDG-08): Phase 4.
- GST 2.0 treatment: Phase 3 (FEAT-03), frozen before the first model lock.
- Considered and not chosen: daily git export of forward data, an external scheduler or pager, paid Supabase.

</deferred>

---

*Phase: 02-the-record-runs-itself*
*Context gathered: 2026-11-26*
