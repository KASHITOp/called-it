# 01-11 Summary: publish and dress rehearsal

Status: complete. Approval (user, 24 Nov 2026): "Approved: publish ... Everything under .planning/ and the rest of tracked files may be public; nothing else needs excluding."

## Done
- Added `nowcaster.ledger.head`, `nowcast ledger head [--write-bytes]`, `scripts/preflight_publish.py` (placeholder-host allowlist plus a check that the real `.env` secret appears nowhere in tracked files or history), `.github/workflows/lock.yml`, `scripts/ots_explorer_check.py`, `calledit_data.db.scratch` with `nowcast db drop-scratch`.
- First preflight found 25 placeholder-looking lines; stopped, user approved an allowlist; the real host, user and password were absent from files and history. The unpushed tip commit was amended to drop a fake host from history. Second preflight: clean.
- Pushed `main` to https://github.com/KASHITOp/called-it (default branch main). Ruleset `protect-main` (deletion, non_fast_forward) active. ci-postgres green (SQLite, Postgres 17, ots-smoke).

## Rehearsal (calledit_rehearsal schema and rehearsal-ledger branch only)
- rules: https://github.com/KASHITOp/called-it/actions/runs/45450854674 (1 rules line, proofs/0.ots)
- predict: https://github.com/KASHITOp/called-it/actions/runs/45451678659 (4 lines, snapshots 1..3, proofs/3.ots)
- upgrade: https://github.com/KASHITOp/called-it/actions/runs/45451945178 (green; proofs still pending, unchanged)
- Payloads equal the 01-10 preview: DMART 21031.59 (ttm_yoy), ETERNAL 28978.03 (break_single_pair, least_straddling, low-confidence label), TITAN 35298.09 (ttm_yoy). Every line has gst2.0 in breaks_in_window.
- Isolation: `git ls-tree origin/main ledger/` empty; live schema `calledit` does not exist (false); logs contain no `supabase.com`.
- Discarded: `calledit_rehearsal` dropped, `rehearsal-ledger` branch deleted.

## Not verified
- A completed (Bitcoin-attested) proof and the explorer check against real explorers: proofs were pending; the checker is tested on synthetic proofs only.
