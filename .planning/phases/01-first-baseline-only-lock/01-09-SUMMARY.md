---
phase: 01-first-baseline-only-lock
plan: "09"
subsystem: seed-data
status: complete
tags: [seed, data-honesty, provenance, eternal-break, ir-documents]

requires:
  - phase: 01-04
    provides: "seed loader, quarterly_revenue.csv header and fill-in rules"
  - phase: 01-05
    provides: "baseline preview with the break-aware pair rule"
provides:
  - "data/seed/quarterly_revenue.csv: 24 drafted first_reported rows (DMART, TITAN, ETERNAL, Q3FY25..Q2FY27), all verified = N"
  - "data/seed/drafting_log.md: provenance for every row plus the Eternal break range reasoning"
  - "config/universe.toml: eternal-blinkit-inventory break pinned to Eternal shareholder letters (confirmed = false)"
  - "data/seed/README.md: Rows awaiting the user section"
affects: [01-10]

actuals:
  commits: 3
plan_head_before: 447c7289059af585466dbc4bd44a9c932bec4cf4

key-files:
  modified:
    - data/seed/quarterly_revenue.csv
    - data/seed/README.md
    - config/universe.toml
    - tests/data/test_seed_loader.py
    - tests/data/test_universe.py
  created:
    - data/seed/drafting_log.md

key-decisions:
  - "Every figure was read in this session from a company document (DMart api.dmartindia.com PDFs, Titan titancompany.in PDFs, Eternal b.zmtcdn.com shareholder letters); nothing from memory, news or aggregators"
  - "Titan revenue_cr = Sale of products/services + Other operating revenues (the filing prints no subtotal), checked against printed Total income every quarter; bullion kept as reported (D-13)"
  - "No exchange dissemination time is printed in any document, so every instant uses rule:date_eod_ist with the letter date"
  - "Eternal break proposed as Q1FY26..Q3FY26 with primary quotes; confirmed stays false"

requirements-completed: [DATA-01, FEAT-02]
---

# Plan 01-09 summary: drafted seed history and the Eternal break citation

## What was done

- **Task 1 (DMART, commit d714a7c).** 8 consolidated "Revenue from operations" rows (crore, two decimals), results date from the "Outcome of Board Meeting" letter and business-update date from the "Company Update" letter. Every figure cross-checked against the next filing's prior-quarter column.
- **Task 2 (TITAN, commit de8b047).** 8 rows. Revenue is the sum of the two printed lines under "Revenue from operations", each sum reconciled to printed Total income. Group gold-ingot sales (inside revenue from operations as reported) are recorded in each row's notes.
- **Task 3 (ETERNAL, commit 053bbe8).** 8 rows from Annexure D of the quarterly shareholder letters, each confirmed by three routes (letter, company results Excel, next letter's comparative). Break range pinned. Seed-state tests updated.

## Per company: sourced vs awaiting

| Company | Sourced | Awaiting the user |
|---|---|---|
| DMART | Q3FY25..Q2FY27 (8) | none |
| TITAN | Q3FY25..Q2FY27 (8) | none |
| ETERNAL | Q3FY25..Q2FY27 (8) | none |

All 24 rows are `verified = N`. The Q3FY25 Titan split, Q3FY26 DMart (image tables) and every Eternal row (image tables) are flagged in `drafting_log.md` / README for first-pass verification.

## Eternal break range (proposal, confirmed = false)

`eternal-blinkit-inventory`: start_q **Q1FY26**, end_q **Q3FY26**. Primary citation: Q1FY26 shareholder letter (https://b.zmtcdn.com/investor-relations/Eternal_Shareholders_Letter_Q1FY26_Results.pdf), "We will be gradually transitioning our quick commerce business from a marketplace model to inventory ownership over the next 2-3 quarters" and "In Q1FY26, about 3% of our NOV was already on our own inventory". End from the Q2FY26 letter (about 80% of NOV, heading to about 90%) and the Q3FY26 letter (about 90%, not expected to increase meaningfully). Implied Q3FY27 method: `break_single_pair`, pair (Q2FY27, Q2FY26), status `least_straddling`.

## Verification

- `nowcast seed load --dry-run`: 24 rows seen, 0 errors.
- Dev DB (`build/dev/seed-check.db`, deleted afterwards): load inserted 24 observations and 40 reveal events; `nowcast baseline --quarter Q3FY27` gives REFUSED unverified_seed_quarter for DMART, ETERNAL and TITAN (all 8 quarters each).
- `grep -ciE "nseindia.com/api|api.bseindia.com|screener.in" data/seed/quarterly_revenue.csv` = 0; `grep -c inc42.com config/universe.toml` = 0.
- `uv run pytest -q -m "not postgres"`: 575 passed, 36 deselected. `ruff check .`: All checks passed. `ruff format --check .`: only two pre-existing `.planning/*.md` files (not Python) are listed.

## Deviations

- **Tests changed (Rule 3).** Five tests assumed a header-only canonical CSV and the inc42 source URL. They now check header/LF and that the dry run is clean (dev) or only unverified-row errors (rehearsal), and use the new URL for the http-downgrade mutation. No validator or guard was weakened.
- **Source host.** Eternal serves its IR documents from `b.zmtcdn.com/investor-relations/` (linked from eternal.com); its `robots.txt` was not separately fetched. eternal.com itself has none (404). Flagged in the log.
- **Tools.** Local `pdftotext` (already installed) read the downloaded PDFs; the fetch tool's OCR read image tables. No dependency was added.

## Issues for the user

- Verify every row against its `source_url` before Plan 01-10 sets `verified = Y`; begin with Titan Q3FY25, DMart Q3FY26 and all Eternal rows.
- The Titan business-update PDFs carry growth percentages, not consolidated revenue; only their dates are used.
