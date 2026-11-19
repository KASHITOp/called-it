# Seed data: `quarterly_revenue.csv`

This folder holds the hand-curated quarterly revenue history that the point-in-time store is
seeded from (DATA-01). `quarterly_revenue.csv` ships with only its header row. Claude drafts the
rows and you verify them (D-22).

Research and educational use only. Nothing here is a buy or sell recommendation.

## Purpose and the data-ethics rule

Every row is one quarter's **consolidated revenue from operations**, copied from a public
company disclosure, plus the instants when that number and the quarter's first reveal became
public. The loader turns each row into a timestamped, insert-only observation and the matching
reveal events. A model can only read them through `PointInTimeReader`, so no call ever sees a
number before it was public.

Rules for collecting the data (CLAUDE.md, data ethics):

- **No NSE or BSE automation.** No scripts, no API wrappers, no cookie juggling. The exchanges
  sit behind bot protection, and fighting it is out of bounds.
- **No screener.in.** Its terms allow personal viewing only. Do not copy from it and do not cite
  it, not even for a cross-check that ends up in this file.
- **Use company investor-relations (IR) pages first.** Single, manual-equivalent downloads of
  the published PDFs are fine.
- **When only an exchange PDF exists, you open it yourself** in a browser and copy from it.
- **Never invent, estimate or interpolate a value.** A quarter you cannot source stays
  missing. The lock then records a visible gap (D-08).

## Where to find each company's numbers

The pages below are starting points. Confirm each URL when you use it, and cite the PDF itself
(not the listing page) in `source_url`.

| Ticker | Company | Where to look | Reveal event |
|---|---|---|---|
| DMART | Avenue Supermarts Ltd | The DMart investor-relations page (dmartindia.com): quarterly results PDFs and the **quarterly business update** (standalone revenue update, usually 2-4 days after quarter end) | Business update first, then results |
| TITAN | Titan Company Ltd | The Titan investors page (titancompany.in): quarterly results, investor presentations and the **quarterly business update** (first week after quarter end) | Business update first, then results |
| ETERNAL | Eternal Ltd (formerly Zomato Ltd, symbol ZOMATO until 2025-04-08) | The Eternal investor-relations page: the quarterly **shareholder letter** and the results PDF | Results only (no business update) |

## Which line to copy

- Copy **consolidated** "**Revenue from operations**" for the quarter, **as first reported**
  in that quarter's results filing.
- Use the **consolidated** column, never standalone (`basis` must be `consolidated`).
- **Never total income.** Titan's press releases headline "total income", which adds other
  income. That is the wrong line.
- **Never Eternal's "adjusted revenue"** or any other non-GAAP figure (D-13). Use the
  consolidated statement of profit and loss.
- Take the quarter column (three months ended), not year-to-date or the full-year column.
- `line_item` must be exactly `Revenue from operations`.

## Unit conversion

`revenue_cr` is always **INR crore with exactly two decimals** and no thousands separators,
for example `12345.60`. Record the unit the filing used in `unit_in_filing` (`crore`, `lakh`
or `million`) and convert:

- 1 crore = 100 lakh = 10 million
- lakh to crore: divide by 100 (`1234560.00` lakh is `12345.60` crore)
- million to crore: divide by 10 (`123456.0` million is `12345.60` crore)

If the converted value has more than two decimals, stop and ask. Do not round silently.

## Timestamps: `results_date` and `business_update_at`

Each instant needs a basis column that says how precise it is (D-24):

| Basis | Format | Use when | Stored as |
|---|---|---|---|
| `exchange_timestamp` | `YYYY-MM-DDTHH:MM+05:30` | The exchange filing shows the **dissemination time** (the time the announcement was published to the market) | That instant, in UTC |
| `rule:date_eod_ist` | `YYYY-MM-DD` | You only know the filing **date** | `D 23:59:59 IST`, in UTC (errs late, so it can never leak) |

- Read the dissemination time from the exchange announcement page or the PDF's exchange
  stamp. **Never use the board-meeting conclusion time.** The meeting ends before the
  results are disseminated, so using it would mark the number public too early.
- The format must match the basis. A date-only value with `exchange_timestamp`, or a
  timestamp with `rule:date_eod_ist`, is an error.
- For deadlines and the calendar's `reveal_at`, a date-only event counts from the **start** of
  that IST day (`D 00:00 IST`, D-27). Each direction errs safe.
- `results_date` must fall after the quarter end and not in the future. `business_update_at`
  must fall after the quarter end and on or before the results.

## Required business updates

- **DMART and TITAN** `first_reported` rows **must** have `business_update_at`,
  `business_update_basis` and, ideally, `business_update_url` (the business-update PDF). For
  these companies the business update is the quarter's first reveal (D-24).
- **ETERNAL** rows leave all three business-update columns empty. Its reveal is the results
  filing.
- `restated` rows leave the business-update columns empty.

## Restated rows

A later filing sometimes restates an earlier quarter. **Never edit the original row.** Add a
new row instead:

- same `ticker` and `fiscal_quarter`, `vintage` = `restated`;
- `results_date` = when the restated figure became public (it must be later than the first
  report);
- `source_url` = the filing that contains the restated figure.

The store keeps both. A baseline uses the latest vintage known at its as-of instant (D-05),
and grading always uses the first-reported number (D-13). Each ticker and quarter has exactly
one `first_reported` row.

## The `verified` column

- Claude drafts each row with `verified` = `N`.
- **You** set it to `Y` only after opening the cited PDF and checking every field against it:
  the revenue figure and unit, the consolidated column, the line item, and both timestamps.
- Rehearsal and live loads refuse any `N` row (D-22). An unverified quarter counts as
  **missing**: that company's lock is refused and the ledger records a gap (D-08).

## Column reference

`ticker,isin,fiscal_quarter,period_end,basis,line_item,unit_in_filing,revenue_cr,results_date,results_at_basis,business_update_at,business_update_basis,business_update_url,source_url,page_ref,vintage,verified,notes`

| Column | Rule |
|---|---|
| `ticker` | DMART, ETERNAL or TITAN (as in `config/universe.toml`) |
| `isin` | Must equal the ISIN in `config/universe.toml` |
| `fiscal_quarter` | Canonical label, e.g. `Q2FY27` |
| `period_end` | The quarter's last day, e.g. `2026-09-30` for Q2FY27 |
| `basis` | `consolidated` |
| `line_item` | `Revenue from operations` |
| `unit_in_filing` | `crore`, `lakh` or `million` |
| `revenue_cr` | INR crore, two decimals, e.g. `12345.60` |
| `results_date`, `results_at_basis` | See Timestamps |
| `business_update_at`, `business_update_basis`, `business_update_url` | See Required business updates |
| `source_url` | `https://` link to the PDF. Printable ASCII only: no spaces, double quotes, backslashes or `#` |
| `page_ref` | Optional page reference, e.g. `p7`. Printable ASCII, no double quotes or backslashes |
| `vintage` | `first_reported` or `restated` |
| `verified` | `Y` or `N` |
| `notes` | Free text. It is not stored |

`source_url` and `page_ref` enter the canonical ledger snapshots, which is why their characters
are restricted. Rehearsal and live loads also refuse `.invalid` hosts, so the synthetic test
fixture (`tests/fixtures/seed_fixture_SYNTHETIC.csv`) can never reach a real database.

## Depth target

By the lock (target about 28 Nov 2026) the file needs **8 verified quarters per company,
Q3FY25 to Q2FY27** (D-23): 24 `first_reported` rows, which is exactly what the baseline's
TTM windows need. The longer 12-16 quarter history is added in Phase 2.

## Checking the file

From the repo root:

```bash
uv run nowcast seed load --dry-run
```

This validates the **whole file** and inserts nothing. Every problem is listed as
`row N, column X: reason` (the header is row 1, as in a spreadsheet), and any error means the
real load inserts nothing at all (D-25). When the dry run is clean, load it:

```bash
uv run nowcast seed load
```

Re-running the load on an unchanged file inserts 0 rows. Add `--require-verified` to treat
every `N` row as an error locally, the way rehearsal and live do.

The file is committed with `-text` (`.gitattributes`), so keep LF line endings. The loader
accepts a UTF-8 BOM or CRLF from a spreadsheet export, but commit the file as plain UTF-8 with
LF.

## Rows awaiting the user

Claude could not source these from a company IR document in this session, so there is no row for
them. Until you add and verify them, `nowcast baseline` and the lock refuse that company
(`missing_seed_quarter`). Provenance for every drafted row is in `drafting_log.md`.

- DMART: none awaiting. All 8 quarters (Q3FY25 to Q2FY27) are drafted with `verified = N`.
  Open each `source_url` and check the consolidated "Revenue from operations" before setting `Y`.
  Q3FY26 has no `page_ref` because its tables are images in the PDF.
- TITAN: none awaiting. All 8 quarters are drafted with `verified = N`. Titan prints no single
  "Revenue from operations" total, only "Sale of products/services" plus "Other operating
  revenues"; the CSV figure is their sum (whole crore). Add the two lines yourself when you
  verify, and check the Q3FY25 split first (see `drafting_log.md`).
- ETERNAL: none awaiting. All 8 quarters are drafted with `verified = N`. The Annexure D tables are
  images in the shareholder-letter PDFs, so open each `source_url` and read "I. Revenue from
  operations" off the page (no `page_ref` recorded). The `eternal-blinkit-inventory` break range in
  `config/universe.toml` (Q1FY26 to Q3FY26) is a proposal with primary citations and stays
  `confirmed = false` until you confirm it.
