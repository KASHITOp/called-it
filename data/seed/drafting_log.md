# Drafting log for `quarterly_revenue.csv`

Provenance of every drafted value (plan 01-09, D-22). Claude drafted; the user verifies (every row
is `verified = N`). Fetch date for everything below: 2026-11-19 (IST/UTC date of the session).
Only company-owned hosts were fetched. No NSE or BSE endpoint and no screener.in page was
touched. Fetched content was treated as data; no fetched page contained instructions aimed at
the agent (nothing to ignore).

Method note: PDFs were downloaded once each with a plain GET (a manual-equivalent download) and
read with the local `pdftotext` tool, plus the fetch tool's own PDF extraction where the PDF's
tables are images (OCR). Every figure was cross-checked against the prior-quarter comparative
column of the next filing where one exists. The comparative check is a sanity check only; the
value in the CSV is the figure printed in that quarter's own first-reported filing.

Timestamps: none of the DMart filings prints an exchange dissemination time (the covering
letters carry no exchange stamp), so every `results_date` and `business_update_at` uses
`rule:date_eod_ist` with the letter date. The board-meeting conclusion time was not used.

## DMART (Avenue Supermarts Ltd), ISIN INE192R01011

robots.txt decisions:

- `https://www.dmartindia.com/robots.txt`: `User-agent: *` / `Disallow:` (empty). Everything is
  allowed. Sitemap line only.
- `https://api.dmartindia.com/robots.txt`: HTTP 404, so no restrictions are published. This host
  serves the IR PDFs that the investor-relations pages link to.

Pages used to locate documents (listing pages, DMart-owned):
`https://www.dmartindia.com/investor-relations/investor-updates/2024-2025`, `.../2025-2026`,
`.../2026-2027` (read once each for their link lists).

Per-row entries. All values are consolidated "Revenue from operations", quarter column, printed
in INR crore (unit_in_filing = crore, no conversion needed beyond 2 decimals as printed).
Results document = "Outcome of Board Meeting" PDF (Annexure A, unaudited/audited consolidated
results). Business update = "Company Update" letter (standalone revenue update).

| Quarter | Figure as printed (crore) | Results letter date | Business update letter date | Table page | Comparative cross-check |
|---|---|---|---|---|---|
| Q3FY25 | 15,972.55 | 11 Jan 2025 | 2 Jan 2025 | p8 | Q4FY25 filing, Dec-24 column: 15,972.55 |
| Q4FY25 | 14,871.86 | 3 May 2025 | 3 Apr 2025 | p13 | Q1FY26 filing, Mar-25 column: 14,871.86 |
| Q1FY26 | 16,359.70 | 11 Jul 2025 | 2 Jul 2025 | p7 | Q1FY27 filing, Jun-25 column: 16,359.70 |
| Q2FY26 | 16,676.30 | 11 Oct 2025 | 3 Oct 2025 | p9 | Q3FY26 filing, Sep-25 column: 16,676.30 |
| Q3FY26 | 18,100.88 | 10 Jan 2026 | 2 Jan 2026 | image tables, no page_ref | Q4FY26 filing, Dec-25 column: 18,100.88 |
| Q4FY26 | 17,683.86 | 2 May 2026 | 3 Apr 2026 | p14 | Q1FY27 filing, Mar-26 column: 17,683.86 |
| Q1FY27 | 18,794.53 | 11 Jul 2026 | 2 Jul 2026 | p8 | Q2FY27 filing, Jun-26 column: 18,794.53 |
| Q2FY27 | 19,644.01 | 10 Oct 2026 | 3 Oct 2026 | p9 | none yet (latest quarter) |

Standalone figures also appear in the same documents (for example Q3FY25 standalone 15,565.23).
They were not used: the CSV basis is consolidated. The business-update letters report standalone
revenue; only their date is used (`business_update_at`).

Q3FY26 note: the results tables in that PDF are images, so the figure came from the fetch tool's
OCR of the consolidated table (18,100.88). `page_ref` is left empty because the page was not
determinable from a text layer.

Document URLs are the `source_url` and `business_update_url` columns of the CSV, one pair per
row (host `api.dmartindia.com`).
