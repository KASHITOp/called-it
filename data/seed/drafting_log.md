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

## TITAN (Titan Company Ltd), ISIN INE280A01028

robots.txt decision: `https://www.titancompany.in/robots.txt` (fetched 2026-11-19) allows `User-agent: *`
everywhere except `/core/`, `/profiles/`, admin, search, user-login and similar Drupal system
paths. The quarterly-results page `/investors/investor-relations/quarterly-results` and the PDFs
under `/sites/default/files/` are not disallowed, so they were read.

Documents were located from the quarterly-results page (its PDF link list), then each PDF was
downloaded once and read with `pdftotext -raw` (the layout mode scrambles Titan's column order,
so raw order was used). One web search (title and excerpt only) was used to find the results page
URL; no figure comes from the search excerpt.

Revenue basis: the consolidated statement prints "I. Revenue from operations" as a header with two
lines under it ("Sale of products/ services" and "Other operating revenues") and no subtotal. The
CSV figure is their sum, in whole crore (the filing is in whole crore, so `.00`). Other income
(and, in Q2FY27, "Fair value change of put option liability over NCI", 671) is excluded. Each
sum was checked against the printed Total income: sale + other operating + other income
(+ the 671 item in Q2FY27) equals Total income in every quarter. This is Revenue from operations
and not Total income (Pitfall 6). Titan's press-release headline "Total income excludes
bullion and digi-gold", but the statement's revenue from operations includes them; the CSV keeps
the statement as reported (D-13). The Group gold-ingot amount per the filing's own note is in each
row's notes.

| Quarter | Sale of products/services | Other operating revenues | Sum used (crore) | Total income printed | Group gold-ingot note | Results date | Business update date | Table page |
|---|---|---|---|---|---|---|---|---|
| Q3FY25 | 17,550 | 190 | 17,740 | 17,868 | 145 | 4 Feb 2025 | 6 Jan 2025 | p12 |
| Q4FY25 | 13,897 | 1,019 | 14,916 | 15,032 | 983 | 8 May 2025 | 7 Apr 2025 | p17 |
| Q1FY26 | 14,814 | 1,709 | 16,523 | 16,628 | 1,662 | 7 Aug 2025 | 7 Jul 2025 | p14 |
| Q2FY26 | 16,461 | 2,264 | 18,725 | 18,837 | 2,188 | 3 Nov 2025 | 7 Oct 2025 | p15 |
| Q3FY26 | 24,915 | 501 | 25,416 | 25,567 | 469 | 10 Feb 2026 | 6 Jan 2026 | p14 |
| Q4FY26 | 20,607 | 6,313 | 26,920 | 27,104 | 6,249 | 8 May 2026 | 7 Apr 2026 | p20 |
| Q1FY27 | 20,787 | 569 | 21,356 | 21,502 | 749 (incl digi-gold) | 7 Aug 2026 | 6 Jul 2026 | p9 |
| Q2FY27 | 20,337 | 277 | 20,614 | 21,430 | 226 (incl digi-gold) | 5 Nov 2026 | 6 Oct 2026 | p10 |

Comparative cross-checks (the next filing's prior-quarter column agrees): Q3FY25 against the
Q3FY26 filing (17,550 / 190); Q4FY25 against the Q4FY26 filing (13,897 / 1,019); Q1FY26 against
the Q1FY27 filing (14,814 / 1,709); Q2FY26 against the Q2FY27 filing (16,461 / 2,264); Q3FY26
against the Q4FY26 filing (24,915 / 501); Q4FY26 against the Q1FY27 filing (20,607 / 6,313);
Q1FY27 against the Q2FY27 filing (20,787 / 569). Q2FY27 is the latest quarter.

Row-by-row URLs are the `source_url` (results) and `business_update_url` (Quarterly Update)
columns. Caveats for the user:

- The Q3FY25 first-report layer of the PDF has a scrambled OCR text layer (labels shifted by one
  row); the split 17,550 / 190 / 128 was resolved by the Q3FY26 comparative column and by the
  arithmetic against Total income 17,868. Re-check this one against the printed page first.
- Results dates are the date printed on the results statement or covering letter. No exchange
  dissemination time is printed, so the basis is `rule:date_eod_ist`. For Q3FY25 (4 Feb 2025),
  Q4FY25 (8 May 2025) and Q3FY26 (10 Feb 2026) the downloaded PDF is the results statement
  without the covering letter, so the date is the statement and auditor's report date.
- The Quarterly Update letters are standalone growth updates. They carry no consolidated revenue
  figure; only their letter date is used.
