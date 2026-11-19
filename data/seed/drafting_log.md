# Drafting log for `quarterly_revenue.csv`

Provenance of every drafted value (plan 01-09, D-22). Claude drafted; the user verifies (every row
is `verified = N`). Fetch date for everything below: 2026-11-19 (IST/UTC date of the session).
Only company-owned hosts were fetched. No exchange endpoint and no third-party financial-data
aggregator page was touched. Fetched content was treated as data; no fetched page contained instructions aimed at
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

## ETERNAL (Eternal Ltd, formerly Zomato Ltd), ISIN INE758T01015

robots.txt decision: `https://www.eternal.com/robots.txt` returned HTTP 404 (none published, so no
restrictions); `https://www.eternal.com/investor-relations/results` was read once to find the
document links. The shareholder-letter PDFs and results Excel files are served from Eternal's own
investor-relations storage, `b.zmtcdn.com/investor-relations/` (linked from that page; the host's
`robots.txt` was not separately fetched, and each file was downloaded once with a plain GET).

Eternal's P&L statement is Annexure D (consolidated) of each quarterly shareholder letter. The
tables are images in the PDFs, so two independent routes were used for each figure:

1. the figure in the letter itself, from the PDF text layer where present (Q4FY25, Q1FY26, Q2FY26,
   Q3FY26, Q1FY27, Q2FY27) or the fetch tool's OCR query of Annexure D (Q3FY25, Q4FY26);
2. the company's own results Excel for that quarter ("Reconciliation appendix", row "Revenue from
   operations", in INR 100 crore, i.e. billions, 2 decimals), and the next letters' comparative columns.

All three agree for every quarter. Line copied is "I. Revenue from operations", consolidated, as
Ind AS first reported; not "Adjusted Revenue" (D-13). Whole crore as printed, so `.00`.

| Quarter | Revenue from operations (crore) | Letter date (results date used) | Evidence |
|---|---|---|---|
| Q3FY25 | 5,405 | 20 Jan 2025 | OCR of Annexure D (Q3FY25 letter); Excel 54.05; Q4FY25/Q3FY26 letters comparative |
| Q4FY25 | 5,833 | 1 May 2025 | Q4FY25 letter text layer; Excel 58.33; Q1FY26 letter comparative |
| Q1FY26 | 7,167 | 21 Jul 2025 | Q1FY26 letter text layer; Excel 71.67; Q2FY26 letter comparative |
| Q2FY26 | 13,590 | 16 Oct 2025 | Q2FY26 letter text layer; Excel 135.90; Q3FY26 letter comparative |
| Q3FY26 | 16,315 | 21 Jan 2026 | Q3FY26 letter text layer; Excel 163.15; Q4FY26 letter comparative |
| Q4FY26 | 17,292 | 28 Apr 2026 | OCR of Annexure D (Q4FY26 letter, "Refer note 11"); Excel 172.92; Q1FY27 letter comparative |
| Q1FY27 | 20,211 | 22 Jul 2026 | Q1FY27 letter text layer ("20,2 11"); Excel 202.11; Q2FY27 letter comparative |
| Q2FY27 | 24,138 | 21 Oct 2026 | Q2FY27 letter text layer; Excel 241.38 |

Timestamps: the letter date is used with `rule:date_eod_ist`; the letters carry no exchange
dissemination time. Eternal publishes no business update, so the three business-update columns are
empty. `page_ref` is empty because the statement is on image pages whose numbers were not fixed from
a text layer (it is "Annexure D" of each letter). Filings before 9 Apr 2025 were issued as Zomato Ltd
(same ISIN), so the Q3FY25 letter (Jan 2025) was issued under the Zomato name.

The Q4FY26 letter is hosted twice on the IR page under two file names
(`Eternal_Shareholders_Letter_Q4FY26_Results.pdf`, `Eternal_Limited_Shareholders_Letter_Q4FY26_Results.pdf`);
both files are byte-for-byte the same size, and the first is cited.

## Eternal break range

Break id `eternal-blinkit-inventory` (config/universe.toml). Proposed, still `confirmed = false`
(the user confirms at Plan 01-10). Primary citation: Eternal's own shareholder letters (the old
inc42 secondary source is removed).

- `start_q` = **Q1FY26**. Q1FY26 shareholder letter (21 Jul 2025):
  https://b.zmtcdn.com/investor-relations/Eternal_Shareholders_Letter_Q1FY26_Results.pdf
  Quote: "We will be gradually transitioning our quick commerce business from a marketplace model to
  inventory ownership over the next 2-3 quarters." and "In Q1FY26, about 3% of our NOV was already
  on our own inventory (which was also the reason quick commerce Revenue grew faster than NOV...)".
  The consolidated note in the same letter (note 8/9 to the results) says the Group "has initiated
  transition from its marketplace model to a combination of marketplace and inventory-led model"
  in the quarter ended 30 June 2025. So Q1FY26 is the first quarter whose reported revenue includes
  inventory-led Blinkit sales (small, about 3% of NOV). Q4FY25 and earlier are pure marketplace
  ("the quick commerce business operated as a pure marketplace until Q4FY25", Q2FY26 letter).
- `end_q` = **Q3FY26**. Q2FY26 letter (16 Oct 2025): "in Q2FY26 about 80% of the NOV was on our own
  inventory which is expected to go to a steady state number of about 90% in the next quarter".
  Q3FY26 letter (21 Jan 2026): "In Q3FY26, about 90% of our NOV was on our own inventory, and as
  mentioned in our last letter, we don't expect this number to increase meaningfully from here."
  The share therefore moved materially through Q3FY26 (3% to 80% to 90%) and is steady from Q4FY26.
  The Q1FY27 letter says the difference "reflects the business model shift to inventory ownership"
  for Q1FY27 versus Q1FY26, which is a base-effect comparison, not a still-moving share.
- Hyperpure offset (Pitfall 4): the same notes say Hyperpure's B2B supplies revenue falls as
  non-restaurant B2B buyers become sellers on Blinkit, so the break lowers one segment while raising
  another. The consolidated total is what the baseline uses.

Implied Q3FY27 method under the Plan 01-05 rule: the TTM window Q3FY25..Q2FY27 contains Q1FY26..Q3FY26,
so the break method triggers (`break_single_pair`). The pair is (Q-1, Q-5) = (Q2FY27, Q2FY26). Q2FY26 is
inside the break range (not after it), so no pair is `post_break` and the status is
`least_straddling` (checked against `nowcaster/src/nowcaster/baseline.py`, lines 226-234). Q2FY27 vs
Q2FY26 compares about 90% own-inventory revenue with about 80%, which is the smallest straddle in the
window. This is why ETERNAL carries the low-confidence label.
