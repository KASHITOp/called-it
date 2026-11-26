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
- `ledger/proofs/3.ots` is committed. Its digest equals the head hash. The explorer check
  exits 2: pending, no Bitcoin attestation yet.
- Local `main` equals `origin/main` at `aeaee5f`; the working tree is clean.

## State of the proofs

- `proofs/0.ots` (seq 0): complete and cross-checked on blockstream.info and mempool.space
  (earliest block 977426, 2026-11-24T22:47:58Z), done in Plan 01-12/01-13 prep by the live
  `upgrade` action (run 45794350803, commit `bbee6ad`).
- `proofs/3.ots` (head after the lock): pending. Per the user's instruction the OTS upgrade has not
  been run since the lock.

## Open items

- Run the live `upgrade` action in a few hours (the user said so). Then the Plan 01-13 must-have
  "proof 3 complete and passing the explorer check, block time before 2026-12-31T18:30:00Z"
  can be closed. Only the head proof (3) covers seq 1-3; there are no proofs for seq 1 and 2 by
  design.
- Ghost run 45475002224 is still queued on GitHub; it is not part of the ledger.
- The plan's final must-have, `nowcast predict --quarter Q2FY27` on a dev DB exiting 4 with
  nothing appended, was not re-run in this session; it was covered by the lock-guard tests in
  earlier plans.
- Phase 1 close-out (evidence sweep) remains after the upgrade check.
