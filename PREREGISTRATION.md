# CALLED IT. - Preregistration (rules version 1)

This document is hashed (SHA-256 of its exact bytes) into the "rules" record at seq 0 of the
append-only ledger before any prediction is locked. It describes what the code does. If the
code and this text ever disagree, the disagreement is a bug to be reported, and the fix is a
new rules record, never a silent edit.

## 1. Purpose and scope

- CALLED IT. predicts the quarterly consolidated revenue of Indian listed consumer companies
  before the numbers are disclosed, using only data that was public at the lock instant.
- It is a revenue nowcast only. It is a research and educational project.
- It is not investment advice. It makes no buy or sell calls, no price targets and no
  recommendations of any kind, and nothing in the product may be read as one.
- Phase 1 locks one baseline-only call per company for Q3 FY27. A baseline is deliberately
  naive. It is the yardstick that later models must beat, in public, even when it wins.

## 2. Universe

- DMART (Avenue Supermarts Ltd, ISIN INE192R01011), ETERNAL (Eternal Ltd, ISIN INE758T01015)
  and TITAN (Titan Company Ltd, ISIN INE280A01028). ETERNAL was listed as ZOMATO until
  2025-04-08.
- The ISINs are as printed in each company's filing header and recorded in
  config/universe.toml. A live lock is refused unless every enabled company has its ISIN
  marked as confirmed there.
- Why these three: they are large, listed, consumer-facing companies with public quarterly
  consolidated results and a business update or shareholder letter close to the quarter end.
- Survivorship and hindsight caveat: the universe was chosen in November 2026 by someone who
  already knows these companies are listed, large and still trading. It is not a random or
  complete sample, and results on it say nothing about companies that were delisted, were
  never selected, or are too small to follow.
- The universe changes only through a new rules record (section 12).

## 3. Target

- The target is consolidated "Revenue from operations" in INR crore, as first reported in the
  company's own results filing for that quarter. It is never total income and never any
  adjusted revenue (for Eternal, never "Adjusted Revenue").
- Grading uses the first-reported figure. Later restatements are shown but never re-grade.
- DMART and ETERNAL: the figure is the printed consolidated revenue from operations.
- TITAN: Titan prints no single "revenue from operations" subtotal. The recorded figure is the
  consolidated "Sale of products/services" plus "Other operating revenues", exactly as printed
  in that quarter's results. It INCLUDES gold-ingot and bullion sales, as reported, and the
  figure is never adjusted to remove them.
- TITAN is noisy against a 3% band. Bullion and gold-ingot sales can swing a quarter's reported
  revenue by more than the band for reasons unrelated to the jewellery business, so a TITAN
  call can be missed or called by bullion movements alone. This is accepted and stated here,
  not corrected.

## 4. Data availability

- Every figure carries an availability time, `available_at`. A value is usable at a lock
  instant `as_of` only if `available_at < as_of` (strictly earlier) and, in live mode, it was
  also ingested no later than `as_of`.
- `exchange_timestamp`: the exchange dissemination time, to the minute, when the filing shows
  it.
- `rule:date_eod_ist`: when only a date is known, the value becomes available at D 23:59:59
  IST. This is the late bound and errs late, so it can never leak.
- For deadlines, VOID rules and cutoffs, a date-only event uses the early bound D 00:00 IST.
  Each direction errs safe.
- A "usable quarter" means: its value has `available_at < as_of` through the point-in-time
  reader, and its seed row is verified. A quarter that was merely revealed but is not yet
  available in the store is not usable.
- All times are stored in UTC. IST is used only for display and for the two bounds above.
- Every read goes through one point-in-time reader. A post-condition re-checks every returned
  row and aborts if any row was not knowable at `as_of`. Leakage tests, including deliberately
  leaky readers that the suite must catch, run in the repository.
- If two vintages of the same period share the latest `available_at` and carry different
  values, nothing can order them. The read is refused (section 5), never resolved by picking
  one, in every mode.

## 5. Baseline-v1 (model_version `baseline-sqly@1.0.0`)

Inputs and window:
- For a target quarter Q, the window is the eight quarters Q-8 .. Q-1, and SQLY is the same
  quarter last year, Q-4. For Q3 FY27 the window is Q3 FY25 .. Q2 FY27 and SQLY is Q3 FY26.
- Each window quarter uses the latest vintage known at `as_of`: the vintage with the latest
  `available_at` below `as_of`. Restatements published before the lock are therefore used.
- All eight window quarters must be usable: present, available, and verified. Nothing is ever
  imputed, estimated or interpolated.

Arithmetic (all `Decimal`, no binary floating point, precision 28, ROUND_HALF_EVEN):
- Normal method `ttm_yoy`: g = sum(Q-4 .. Q-1) / sum(Q-8 .. Q-5) - 1.
- Break method `break_single_pair`: see section 6. g = value(Q-1) / value(Q-5) - 1.
- point = value(SQLY) x (1 + g), using the unrounded g, then rounded once to 0.01 INR crore.
- The growth shown and stored is g at 6 decimal places. It is display only; the point comes
  from the unrounded g.
- A baseline has no out-of-sample residuals, so its interval is none: `lo80_inr_cr` and
  `hi80_inr_cr` are `none` and `interval_label` is "none (baseline-only, no out-of-sample
  residuals yet)".

When a company is refused, a visible gap record is appended and the reason code is one of
exactly these four. They are checked in this order of precedence per company:
- `tied_available_at`: two vintages of one period in the company's revenue series share the
  latest `available_at` with different values. The baseline refuses and never picks one, in
  live and in backtest mode. `missing_quarters` lists the tied window quarters (or the tied
  period dates if they are outside the window). Equal values at the same `available_at` are not
  a conflict.
- `missing_seed_quarter`: at least one window quarter has no usable value. This outranks
  `unverified_seed_quarter`. `missing_quarters` lists every affected window quarter.
- `unverified_seed_quarter`: every window quarter is present but at least one comes from a seed
  row that is not verified (any source other than a verified seed row counts as unverified).
- `invalid_base_sum`: the growth denominator is zero or negative: the prior-window sum
  sum(Q-8 .. Q-5) for `ttm_yoy`, or value(Q-5) for `break_single_pair`. Nothing is divided.
  `missing_quarters` lists the denominator quarters. This is NOT a check that components add up
  to a stated total; no such check exists in the code.

## 6. Eternal treatment (the Blinkit break)

- From Q1 FY26 Eternal moved its quick-commerce business from a marketplace model to owning
  inventory, which changes how revenue is reported. The preregistered break range is
  `start_q` = Q2 FY26 to `end_q` = Q3 FY26, as set in config/universe.toml
  (break id `eternal-blinkit-inventory`, confirmed by the user on 24 Nov 2026).
- Citations (Eternal shareholder letters, https://b.zmtcdn.com/investor-relations/): the Q1 FY26
  letter (21 Jul 2025) says about 3% of NOV was on own inventory and the transition would run
  over the next 2-3 quarters, so Q1 FY26 is the last pre-break quarter. The Q2 FY26 letter
  (16 Oct 2025) says about 80% of NOV was on own inventory in Q2 FY26, heading to about 90%.
  The Q3 FY26 letter (21 Jan 2026) says about 90%, not expected to increase meaningfully from
  there.
- Classification of a quarter against a range: "pre" if before `start_q`, "in" if from `start_q`
  to `end_q` inclusive, "post" if after `end_q`.
- The break method is used when any window quarter is "in" a range that applies to the company,
  or when the window mixes "pre" and "post" quarters.
- The break method uses the single pair (Q-1, Q-5): g = value(Q-1) / value(Q-5) - 1. The pair
  is always (Q-1, Q-5). `pair_status` says how good it is: `post_break` if both quarters are
  after every applicable range, otherwise `least_straddling`. Only `pair_status` tells the two
  apart. The normal method has `pair_status` = `none`.
- Expected for Q3 FY27: the window contains "in" quarters (Q2 FY26, Q3 FY26), so the method is
  `break_single_pair` on the pair (Q2 FY27, Q2 FY26). Q2 FY26 is inside the break, so
  `pair_status` = `least_straddling`.
- Every Eternal record carries this hashed label, verbatim:
  low confidence: post-break comparables limited
  The code re-adds the label if the configuration is ever edited to drop it.
- This treatment is a preregistered choice, not a claim that the pair is comparable. It is the
  least-bad pair available and it is flagged as low confidence for that reason.

## 7. Structural-break flag

- Every prediction records `breaks_in_window`: the sorted ids of the applicable breaks that
  touch the eight-quarter window, joined by "|", or `none`. A date break touches the window if
  its date lies between the first day of the first window quarter and the last day of the last
  one. A range break touches it if the ranges overlap.
- The frozen GST 2.0 statement, verbatim:
  GST 2.0 (22 Sep 2025) is flagged, not adjusted; treatment decided in Phase 3 and recorded as a dated amendment.
- The baseline arithmetic ignores GST 2.0. Only the flag is recorded.
- The per-company `gst_states` lists in config/universe.toml are provisional. They are outside
  this freeze and are re-derived in Phase 3 before any model lock; any change is a dated
  amendment.
- ANY edit to config/universe.toml, including `gst_states` or a note, changes `universe_sha256`.
  After such an edit `nowcast predict` refuses to lock until a new rules record naming the
  new bytes has been appended (section 12). A refusal of this kind is expected, not a fault.

## 8. Locks, deadlines and the official call

The lock instant:
- The lock time is read from the clock exactly once per run. That single instant is `as_of`,
  `data_cutoff` and `locked_at` for every company in the run. There is no option, setting or
  environment variable that sets the lock time, so no command can lock at a past time.
- The point-in-time reader runs in live mode at that instant: only rows with `available_at`
  strictly before it and `ingested_at` at or before it are visible.

Deadlines (earliest plausible reveal = quarter end plus N days at 00:00 IST):
- DMART N = 1, TITAN N = 2, ETERNAL N = 7.
- The quarter must be live for the company: period start <= now < earliest plausible reveal.
  A lock at or after the earliest plausible reveal is refused, and `predict` for an already
  revealed quarter is refused.
- A stored reveal event whose early bound (D 00:00 IST for a date-only event) is at or before
  now refuses that company's lock.
- If the actual `reveal_at` turns out to be earlier than the deadline allowed for, any lock at
  or after the actual `reveal_at` is VOID at grading. That is derived state; the ledger is
  never changed, and a VOID lock is shown greyed out, never hidden.

What is refused, by its real name. Per-company guard refusals append nothing and are printed
as "REFUSED <name>":
- `quarter_not_started`: now is before the quarter's period start.
- `past_earliest_plausible_reveal`: now is at or after the company's earliest plausible reveal.
- `reveal_event_known`: a stored reveal event for the company and quarter has an early bound at
  or before now.
- `invalid_reveal_event`: a stored reveal event cannot be interpreted.
Whole-run refusals append nothing:
- No rules record exists in the ledger. Seq 0 must be the rules record that hashes this
  document, so nothing can be locked before the rules exist.
- `lock_before_rules`: now is earlier than the latest rules record. A lock cannot predate the
  rules it is bound to.
- The rules are stale: this document or config/universe.toml has changed since the latest rules
  record (`document_sha256` or `universe_sha256` differs). A new rules record is required.
- Live only: not running in GitHub Actions on `refs/heads/main`, or any enabled company's ISIN
  or any applicable break is not confirmed, or the live database self-check fails.
- Every enabled company was refused by the guard.
Baseline refusals (section 5) append a gap record instead: `tied_available_at`,
`missing_seed_quarter`, `unverified_seed_quarter`, `invalid_base_sum`.

Exit codes of `nowcast predict`:
- 0: every enabled company was locked with a prediction record.
- 3: at least one record was appended, but some company got a gap record or was refused by the
  guard. The records that were appended are real and stay in the chain.
- 4: nothing was appended because the guard refused (not live, past deadline, missing or stale
  rules, `lock_before_rules`, or the live context is not confirmed).
- 5: the environment failed: the database is unreachable or unusable. There is never a silent
  fallback to a local database.

Repeated locks and the official call:
- A repeated `predict` for the same ticker and quarter is allowed. It appends a new, later
  ledger entry. Earlier entries are never overwritten, edited or deleted.
- The official call for a company and quarter is the last valid lock: the last lock that is
  not VOID and was made before `reveal_at`. It is derived when needed and never stored as a
  flag.
- If a company has no valid lock before its reveal, it shows "NO OFFICIAL CALL", and that
  counts as a published miss, never a silent omission.
- Live locks run only from the GitHub Actions workflow on `main`.
- Only prediction and gap records enter the ledger. A guard refusal appends nothing, so a
  company that was refused simply has no record for that run; a gap record is the visible
  trace of a baseline refusal.

## 9. Grading

- error = (predicted - actual) / actual, stored signed.
- CALLED IT means |error| <= 3% against the first-reported actual. A model call must also have
  the actual inside its 80% interval. A baseline-only call needs only the 3%. Anything else is
  MISSED.
- MISSED shows |error| and a direction: over (predicted above actual) or under (below).
- Compare unrounded Decimals, and display at 2 decimal places. An error of exactly 3% is
  inside the band; anything larger in absolute value is not, however it is displayed.
- Beat baseline means |model error| < |baseline error| on the same company's official call for
  the same quarter. A tie is not beaten. For a baseline-only official call it is N/A.
- Inside-interval is N/A for baseline-only calls, because they have no interval.
- Grading always uses first-reported consolidated revenue from operations. Restatements never
  re-grade.
- Headline scoring and the headline error use official calls only. Every other lock is still
  graded and kept in the convergence history.
- The 3% band is not widened for any company. See section 3 for why TITAN is noisy against it.

## 10. Ledger spec `calledit-ledger-v1`

Canonicalisation:
- A value is a string, a list of values, or a dictionary whose keys match `^[a-z][a-z0-9_]*$`.
  Numbers, booleans and null are never used; every number is written as a string.
- String characters are printable ASCII 0x20 to 0x7E, excluding the double quote and the
  backslash, so nothing is ever escaped and Python and JavaScript produce identical bytes.
- Encoding: JSON with sorted keys at every level, compact separators (a comma and a colon,
  no spaces), ASCII only, no NaN. List order is preserved.
- Money has 2 decimals and ratios 6 decimals, rounded ROUND_HALF_EVEN (zero is `0.00`).
  Timestamps are `YYYY-MM-DDTHH:MM:SSZ` in UTC with whole seconds, dates are `YYYY-MM-DD`,
  integers are base 10 with no leading zeros. An absent value is the literal `none`.

Hash chain:
- `hash` = SHA-256 of the UTF-8 bytes of `payload_canonical`. `prev_hash` is a field inside the
  payload. The genesis record (seq 0) has a `prev_hash` of 64 zeros.
- Each line of `ledger.jsonl` is exactly one `payload_canonical`. Each record's feature
  snapshot is stored in `ledger/snapshots/<seq>.json`; its SHA-256 is the
  `feature_snapshot_sha256` field.

Record kinds: `rules`, `prediction` and `gap`. `annotation` and `universe_change` are reserved
and unused. `lock_kind` is one of `dispatch`, `weekly`, `final`.

Exact field lists, in declaration order (the canonical form sorts them):
- fields of rules: scheme, seq, record_kind, rules_id, document_path, document_sha256, document_git_commit, universe_path, universe_sha256, recorded_at, run_id, prev_hash
- fields of prediction: scheme, seq, record_kind, ticker, isin, fiscal_quarter, target, point_inr_cr, lo80_inr_cr, hi80_inr_cr, interval_label, baseline_inr_cr, baseline_method, pair_status, growth, model_version, labels, breaks_in_window, feature_snapshot_sha256, data_cutoff, locked_at, earliest_plausible_reveal, lock_kind, rules_seq, rules_hash, universe_sha256, code_git_sha, run_id, prev_hash
- fields of gap: scheme, seq, record_kind, ticker, isin, fiscal_quarter, reason_code, missing_quarters, attempted_at, model_version, lock_kind, rules_seq, rules_hash, universe_sha256, code_git_sha, run_id, prev_hash

Field meanings that matter: `target` is `rev_ops_consolidated_inr_cr`; `baseline_method` is
`ttm_yoy` or `break_single_pair`; `labels` and `breaks_in_window` are lists joined by "|" (or
`none`); `rules_seq` and `rules_hash` bind a record to the rules record it was made under;
`universe_sha256` is the hash of the exact config/universe.toml bytes; `data_cutoff` equals
`locked_at` and is the `as_of` of every read.

System of record:
- The system of record is a Postgres database (Supabase) in a private schema not exposed
  through the public data API, with row-level security on and append-only triggers on every
  ledger and store table. On SQLite (local development only) the same triggers exist.
- The honest limit: the table owner or a superuser can disable a trigger or drop a table. That
  is why the ledger is also exported to a git-committed file and timestamped by external
  witnesses (section 11), which an owner cannot rewrite after the fact.

## 11. Witnesses and verification

- Each lock run exports `ledger.jsonl` and commits it to `main`. The commit time and the
  GitHub Actions run log are independent witnesses of when each head existed.
- The head hash is stamped with OpenTimestamps. The proof of the chain head lives at
  `ledger/proofs/<seq>.ots`.
- A proof counts as verified only when all three conditions are met: `ots upgrade` reports the timestamp
  complete; `ots --no-bitcoin verify -d <head_hash> ledger/proofs/<seq>.ots` prints the Bitcoin
  block height and merkle root; and `scripts/ots_explorer_check.py` confirms that merkle root on
  two independent block explorers (blockstream.info and mempool.space) with a block time
  earlier than the reveal.
- Fully trust-minimised verification requires your own Bitcoin node. The explorer check trusts
  those two explorers; the project says so plainly.
- `ots` runs only on the Linux runner in GitHub Actions.

## 12. Change policy

- This document, config/universe.toml and the code are bound to every lock through
  `rules_seq`, `rules_hash`, `universe_sha256` and `code_git_sha`.
- Every change to the rules, the universe or the preregistered data is a new, visible rules
  record. Nothing is ever edited in place and no ledger entry is ever changed or deleted.
- A lock is refused if this document or the universe configuration changed since the latest
  rules record. Writing the new rules record is the only way to proceed, and its hash is public.
- Amendments carry a date. The GST 2.0 treatment (section 7) and the provisional `gst_states`
  lists are the two items already known to be amended later.
