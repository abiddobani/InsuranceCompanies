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
| `scripts/fetch_osfi.py` | Downloads OSFI life insurer open data into `osfi/raw/` and extracts the core companies from 2023 on into `data/osfi/`, including a pivot of LF1 balance sheet assets (investment mix) per entity and quarter |

Notes:

- Five of the 20 are not OSFI-regulated, so OSFI data does not cover them: iA, Desjardins, Beneva, Humania and UV report to Quebec's AMF (CARLI), and Assumption Life to New Brunswick's FCNB.
- OSFI's public LICAT extract (LCA) only carries contractual service margin lines, so LICAT ratios come from each company's own disclosures.
- Canada Protection Plan is a Foresters business with no separate financials; ivari is owned by Sagicor Financial and publishes no company financial statements.

To build the files: `python3 scripts/fetch_osfi.py` and `python3 scripts/download_documents.py --crawl`. Both need open internet access.
