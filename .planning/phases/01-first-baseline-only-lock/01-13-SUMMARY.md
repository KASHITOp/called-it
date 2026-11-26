# 01-13 Summary: first live baseline-only lock (Q3 FY27)

## Go-live decision

The user replied, verbatim: `go-live-lock`, with the rule: exactly one live predict dispatch for
Q3FY27 (lock_kind dispatch); stop and show on any failure, gap or refusal; stop if queued past
15 minutes; do not run the OTS upgrade yet.

## Result

One workflow_dispatch on `main`: `action=predict mode=live quarter=Q3FY27 confirm_live=LIVE`
(the workflow passes `--kind dispatch`). Run: https://github.com/KASHITOp/called-it/actions/runs/45795798090
(success, every step green, no gap, no refusal). Dispatched 2026-11-26 about 09:51 UTC, started within
seconds.

| Commit | Author | Message |
|---|---|---|
| `8e9758c` | github-actions[bot] | ledger: predict live head seq 3 (run 45795798090) |
| `aeaee5f` | github-actions[bot] | ledger: stamp live seq 3 (run 45795798090) |

| seq | ticker | point_inr_cr | baseline_method | pair_status | labels | earliest_plausible_reveal | hash |
|---|---|---|---|---|---|---|---|
| 0 | (rules, prereg-v1) | | | | | | `c480a9aa620de46995ac4833e26d4f64f48fa10078558cafe5a47d8f82633643` |
| 1 | DMART | 21031.59 | ttm_yoy | none | none | 2026-12-31T18:30:00Z | `2fa038fa1043f8d762ef1aaa7b26758ad6e1b52e628ebef05ed1514eb08df7a1` |
| 2 | ETERNAL | 28978.03 | break_single_pair | least_straddling | low confidence: post-break comparables limited | 2027-01-06T18:30:00Z | `5cd878944c014da83015c292389983a7ca74d4a9fbf2f13783319296de3388cb` |
| 3 | TITAN | 35298.09 | ttm_yoy | none | none | 2027-01-01T18:30:00Z | `5ce23711442c7b7f77c67919d50aea4c30cca77e4fa7c7786aad274332ef7ed2` |

All three were locked at `2026-11-26T09:51:33Z`. Head: seq 3, hash `5ce23711...ef7ed2`.

## Verified after `git pull --ff-only`

One-off Python check of the pulled `ledger/ledger.jsonl` (4 lines): output `ALL OK: True`.
- Every line's SHA-256 is its record hash, and each `prev_hash` equals the previous line's hash
  (seq 0 has 64 zeros); `seq` equals the line index.
- Every prediction has `rules_hash` equal to the seq 0 hash, `model_version` `baseline-sqly@1.0.0`,
  `lo80_inr_cr` / `hi80_inr_cr` `none`, `lock_kind` `dispatch`, and `locked_at` earlier than its
  `earliest_plausible_reveal`.
- Points equal the dry run and the Plan 01-10 preview: 21031.59 / 28978.03 / 35298.09.
- ETERNAL carries the label `low confidence: post-break comparables limited`, with method
  `break_single_pair` and pair status `least_straddling`, as in PREREGISTRATION section 6.
- `ledger/snapshots/1.json`, `2.json`, `3.json` are committed; the SHA-256 of each file equals the
  record's `feature_snapshot_sha256`.
- `ledger/proofs/3.ots` is committed. Its digest equals the head hash. At lock time the explorer
  check exited 2 (pending). It was upgraded later; see "Proof 3 completed" below.
- Local `main` equals `origin/main` at `aeaee5f`; the working tree is clean.

## State of the proofs

- `proofs/0.ots` (seq 0): complete and cross-checked on blockstream.info and mempool.space
  (earliest block 977426, 2026-11-24T22:47:58Z; further attestations in blocks 977449 and 977468),
  done by the live `upgrade` action (run 45794350803, commit `bbee6ad`).
- `proofs/3.ots` (head after the lock): complete, see below.

## Proof 3 completed

The user approved one live `upgrade` dispatch after CI was green on `c5d4c51`
(`ci-postgres` run 45799697623). Run 45819685139 succeeded and committed `b8815cb`
(`ledger: upgrade proofs live (run 45819685139)`, github-actions[bot]).

`uv run python scripts/ots_explorer_check.py ledger/proofs/3.ots --digest 5ce23711442c7b7f77c67919d50aea4c30cca77e4fa7c7786aad274332ef7ed2 --before 2026-12-31T18:30:00Z` exits 0:

| Check | Result |
|---|---|
| Proof digest equals head hash | PASS |
| Bitcoin block height | 977669 |
| Block time | 2026-11-26T10:42:05Z (about 51 minutes after the lock at 09:51:33Z) |
| Proof merkle root | `230b6509d29188bf73fabdfd8c2a2a8638bcfcdb263291a5fe79b1f3f31c6932` |
| blockstream.info merkle root | PASS (matches) |
| mempool.space merkle root | PASS (matches) |
| Block time before 2026-12-31T18:30:00Z | PASS on both explorers |

The head proof covers seq 1-3 through the hash chain: each line's hash depends on every earlier line.
Trust note (D-26): two independent explorers, not your own Bitcoin node.

## Q2FY27 refusal check (ROADMAP criterion 5, "Late and backfilled locks refused")

Run on a throwaway SQLite DB (`build/dev/q2-check.db`, gitignored) with `CALLEDIT_ENV=dev` and a
scratch ledger dir, never the live schema or `ledger/`:

- `alembic upgrade head`, `nowcast seed load --dry-run --require-verified` (24 rows seen, 0 inserted),
  `nowcast seed load --require-verified` (24 observations, 40 reveal events), `nowcast rules` (scratch seq 0).
- `nowcast predict --quarter Q2FY27`: DMART, ETERNAL and TITAN all `REFUSED past_earliest_plausible_reveal`
  (2026-09-30T18:30Z, 2026-10-06T18:30Z, 2026-10-01T18:30Z). Message: "every enabled company was refused by the lock guard; nothing appended". **Exit 4.**
- The scratch DB held only its own rules record; no prediction was appended.
- Live `ledger/ledger.jsonl` SHA-256 identical before and after.

## Phase evidence sweep (2026-11-26, on main at `b8815cb`)

| Check | Result |
|---|---|
| `uv run pytest -q -m "not postgres"` | 651 passed, 36 deselected (the Postgres tests) |
| Postgres tests | Not re-run locally (no live credentials by design). `ci-postgres` run 45799697623 on `c5d4c51`: success (b8815cb changed only ledger data) |
| `uv run pytest tests/leakage -q` | 151 passed |
| `uv run pytest tests/leakage -q --reader=leaky-le` | 8 failed, 143 passed, exit 1 (the suite catches the leak) |
| `npm test --prefix web` | 41 passed, 0 failed (JS golden vectors) |
| `nowcast universe` | DMART, ETERNAL, TITAN; Eternal break Q2FY26 to Q3FY26; GST 2.0 break 2025-09-22; universe_sha256 `ad2d7c1f...a8a6c5d` |
| `nowcast calendar --quarter Q3FY27` | earliest plausible reveals: DMART 2026-12-31T18:30Z, TITAN 2027-01-01T18:30Z, ETERNAL 2027-01-06T18:30Z |
| `nowcast ledger head --ledger-dir ledger` | `seq=3 hash=5ce23711...ef7ed2` |
| Proof 0 / proof 3 explorer checks | both exit 0 |

## Open items

- Ghost run 45475002224 is still queued on GitHub; it is not part of the ledger and cannot be removed.
- No `01-10-SUMMARY.md` exists (plan 01-10 produced PREREGISTRATION.md, committed in `3fe21cb` and
  earlier). Not backfilled here.
- The Postgres suite was verified through CI, not re-run locally in this sweep.
