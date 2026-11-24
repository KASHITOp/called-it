# 01-12 Summary: live rules record (seq 0)

## Go-live decision

The user replied, verbatim: `go-live-rules`.

## Result

Seq 0, the live rules record, was written by the lock workflow on GitHub Actions and
committed to public `main` by `github-actions[bot]`.

| Item | Value |
|---|---|
| Successful run | https://github.com/KASHITOp/called-it/actions/runs/45501818235 |
| Rules commit | `24efa7c` (`ledger: rules live head seq 0`) |
| Stamp commit | `3739196` (`ledger: stamp live seq 0`) |
| seq 0 hash | `c480a9aa620de46995ac4833e26d4f64f48fa10078558cafe5a47d8f82633643` |
| recorded_at | `2026-11-24T22:32:26Z` |
| rules_id | `prereg-v1` |
| prev_hash | 64 zeros |
| document_sha256 | `b6d961bc6cc3522e392349018549c1f5c24f1b3e61a093897e1da7766c4091b3` |
| universe_sha256 | `ad2d7c1fa8eeadeb49796d863af56768204705f26752da5932ae411bca8a6c5d` |
| document_git_commit | `8a3cce7a6dc75628737a659a1cbc682d386296b7` |

## Verified after `git pull --ff-only`

- `ledger/ledger.jsonl` has exactly 1 line: record_kind `rules`, seq 0, prev_hash 64 zeros.
- `document_sha256` and `universe_sha256` equal the SHA-256 of `PREREGISTRATION.md` and
  `config/universe.toml` as committed at `document_git_commit`.
- `nowcast ledger head --ledger-dir ledger` prints `seq=0 hash=c480a9aa...3643`, the SHA-256
  of the line's exact bytes.
- `ledger/proofs/0.ots` file digest equals the seq 0 hash; `scripts/ots_explorer_check.py`
  exits 2 (pending): no Bitcoin attestation yet, as expected at this point.
- Both new commits are authored by `github-actions[bot]`.
- Local `main` equals `origin/main` at `3739196`.

## What happened on the way (not hidden)

1. Run 45475002224 (first live dispatch, on `1e07044`) never started. GitHub left it `queued`
   with no jobs and rejected cancel (a contradictory "completed" message), force-cancel
   (HTTP 409) and delete (HTTP 403), and the browser cancel also failed. It is still `queued`
   and is a harmless ghost. Nothing live had been written (checked: no `ledger/` on main, no
   runner commits, live `calledit` schema absent).
2. A duplicate-rules guard was missing: a second `rules` run with identical hashes would have
   appended a duplicate record. Commit `3803dc4` refuses it inside the writer-lock
   transaction, with three tests.
3. Run 45492469491 (second dispatch, on `3803dc4`) failed at "Migrate and self-check the
   database", before any write. Cause: the runner variable `LEDGER_DIR` also filled the
   settings field `ledger_dir`, which live refuses to override. Rehearsal allows the override
   so it passed there. Commit `8a3cce7` renamed the variable to `LOCK_LEDGER` and added a test
   against settings-name collisions.
4. Run 45501818235 (third dispatch, on `8a3cce7`) succeeded. Each dispatch needed the
   user's explicit approval; none was repeated on my own.

`document_git_commit` is `8a3cce7`, the head the run executed on, not the freeze commit
`96b0e60`. The hashed files are byte-identical at both commits (the blob check above).

## Open items

- The OpenTimestamps proof is pending. Run the `upgrade` action later; the Bitcoin attestation
  usually takes hours. The explorer cross-check has so far run only on synthetic proofs.
- Ghost run 45475002224 stays queued; it is not part of the ledger.
- Plan 01-13 (first live call) is next and is a non-autonomous plan.
