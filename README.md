# Insurance Companies

The Canadian life and health insurance companies to use in all analysis in this project.

| Company | Notes |
| --- | --- |
| Assumption Life | |
| Beneva | Formed by the merger of SSQ Insurance and La Capitale |
| BMO Life Assurance Company | |
| Canada Life | Amalgamation of Great-West Life, London Life, and Canada Life [[1]][redhelm] [[2]][lsm] |
| Canada Protection Plan | |
| Canadian Premier Life Insurance Company | |
| Co-operators Life Insurance Company | |
| Desjardins Insurance | [[1]][wiki] |
| Empire Life Insurance Company | |
| Equitable Life Insurance Company of Canada | |
| Foresters Life Insurance Company | |
| Humania Insurance | |
| iA Financial Group | Industrial Alliance [[1]][ishoprates] [[2]][wiki] |
| ivari | |
| Manulife Financial | Includes former brands like Standard Life and Maritime Life [[1]][nomedical] [[2]][lsm] |
| Primerica Life Insurance | |
| RBC Life Insurance | |
| Sun Life Financial | [[1]][wiki] [[2]][lsm] |
| UV Insurance | |
| Wawanesa Life | |

[nomedical]: https://nomedicallifeinsurance.ca/life-insurance-companies-in-canada-infographic-who-owns-whom/
[lsm]: https://lsminsurance.ca/canadian-life-insurance-companies/
[redhelm]: https://redhelm.ca/directory-for-canadian-life-health-insurance-companies/
[wiki]: https://en.wikipedia.org/wiki/List_of_insurance_companies_in_Canada
[ishoprates]: https://ishoprates.ca/insurance/life/companies

## Dataset

Work in progress: an aggregated dataset of investor relations documents, OSFI regulatory data, and capital disclosures for the companies above, covering fiscal 2023 through 2026 year to date.

| Path | What it holds |
| --- | --- |
| `data/companies.csv` | The 20 companies with their OSFI legal entities, prudential regulator (OSFI, AMF, FCNB), ownership, listed parent, and where each publishes its reports |
| `data/osfi_regulated_life_insurers.csv` | All 63 OSFI-regulated life insurers and fraternal benefit societies (OSFI "Who we regulate", Oct 2026), each tagged `core`, `candidate`, `reinsurer`, `foreign_branch` or `exclude` |
| `data/capital_ratios.csv` | Latest LICAT / CARLI ratios, available capital and base solvency buffer per company, with the source document |
| `sources/ir_documents.csv` | Index of investor relations documents (annual reports, MD&A, financial statements, supplementary packages, presentations, LICAT disclosures). `found_via` is `ir_page` or `search` when the link was seen, `pattern` when it follows the issuer's URL scheme but was not checked |
| `sources/seed_pages.csv` | Each company's reports pages, for the crawler |
| `sources/osfi_datasets.csv` | OSFI open data resources (LF1, LF2, LF3, LCA, LCQ returns, data dictionary) and guidance |
| `scripts/download_documents.py` | Downloads every indexed document into `docs/<company>/<year>/` and writes `data/document_index.csv`; `--crawl` also discovers links on the seed pages with a headless browser |
| `scripts/fetch_osfi.py` | Downloads OSFI life insurer open data into `osfi/raw/` and extracts the core companies from 2023 on into `data/osfi/` |
| `docs/<company>/<year>/` | The downloaded documents (stored with Git LFS; run `git lfs pull` after cloning) |
| `data/document_index.csv` | One row per document URL tried: status (`ok`, `duplicate`, `http_404`, `http_403`, ...), local path, size and SHA-256 |
| `data/osfi/<RETURN>_core.csv.gz` | Every OSFI data point for the core companies' entities and the industry totals, fiscal 2023 on (LF1, LF2, LF3, LCA, LCQ) |
| `data/osfi/balance_sheet_assets.csv` | LF1 asset lines (current period) per entity and quarter, $000s |
| `data/osfi/invested_assets.csv` | LF2 investment schedule at balance sheet value per entity and quarter, $000s: bonds by issuer type and investment grade vs below, mortgages, preferred and common shares, other loans, other invested assets |
| `data/osfi/licat_ratios.csv` | LCQ LICAT summary per entity and quarter: total and core ratio (%), available capital, surplus allowance, eligible deposits, base solvency buffer and its components ($000s) |
| `data/osfi/discount_curves.csv` | LF2 IFRS 17 discount curves, long format: risk-free rates, liquidity premiums and discount rates by line of business (par, non-par individual and group insurance, annuities, seg funds, reinsurance), Canada and U.S.A., tenors 1 to 80 years (%) |
| `scripts/fetch_sec.py` | Downloads SEC EDGAR 40-F and 6-K filings for issuers whose sites refuse the script (Manulife; Bank of Montreal for BMO Life). Needs `SEC_CONTACT=<email>`; `--retag` re-reads downloaded filings to tag their fiscal quarter |
| `scripts/coverage_summary.py` | Writes `COVERAGE.md` and `data/coverage_summary.csv`: per company, OSFI quarters available and which fiscal quarters have documents |
| `data/osfi/entities_seen.csv` | Every OSFI entity name and the company it was mapped to |

Notes:

- Five of the 20 are not OSFI-regulated, so OSFI data does not cover them: iA, Desjardins, Beneva, Humania and UV report to Quebec's AMF (CARLI), and Assumption Life to New Brunswick's FCNB.
- OSFI's annual LICAT extract (LCA) only carries contractual service margin lines, but the quarterly extract (LCQ) has the full LICAT summary for every OSFI-regulated entity; it matches Empire Life's Q2 2026 MD&A to the $MM. AMF- and FCNB-regulated companies' ratios come from their own disclosures.
- OSFI data point addresses are a 5-digit page, 3-digit row and 2-digit column (e.g. LF2 `P2101247940`: page 21012, row 479, column 40).
- Manulife's site and bmo.com refuse the download script, so their documents come from SEC EDGAR instead. BMO Life publishes no reports of its own; BMO Financial Group reports it within Wealth Management, and its OSFI data covers the life company itself.
- Canada Protection Plan is a Foresters business with no separate financials; ivari is owned by Sagicor Financial and publishes no company financial statements.

To build the files: `python3 scripts/fetch_osfi.py`, `python3 scripts/download_documents.py --crawl`, `SEC_CONTACT=<email> python3 scripts/fetch_sec.py`, then `python3 scripts/coverage_summary.py`. Both need open internet access.
