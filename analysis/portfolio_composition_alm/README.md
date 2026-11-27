# Peer portfolio composition on the ALM study basis

Rebuild of the October 28 peer portfolio composition for the Canadian life insurers, using
[MooseDragon/cdn-life-insurer-alm](https://github.com/MooseDragon/cdn-life-insurer-alm) as the primary framework
(study commit `9e8d671`). It replaces the whole-general-fund comparison in `analysis/portfolio_composition/`
(branch `claude/project-thread-lhi6ne`).

- Dashboard: https://claude.ai/artifact/6zcGEVLxj8VvYdYdH5DBBF
- PDF: `report/peer-portfolio-composition-alm-basis.pdf` (14 pages, same charts as the dashboard)

## What follows the ALM study

| Rule from the study | How it is applied here |
|---|---|
| General Account (GenAcct) excluding par, UL policyholder funds and seg funds; those blocks shown separately | `out/block_mix_l3.csv` has one mix per block; every peer comparison is on GenAcct |
| Canadian business, net of reinsurance | OSFI Canada columns; Manulife and Sun Life Canada follow the global mix (est); Canada Life uses its disclosed Canada column |
| Periods by date | Fiscal 2025 year-ends: Oct 31, 2025 (RBC Life, BMO Life), Dec 31, 2025 (others) |
| Level 1, 2, 3 asset taxonomy | `TAX` in `build.py`; private placements stay in Illiquid Term Loan |
| Mark every estimate | `mix_est` and the `basis` text on every row; `est` tags on every chart and table |
| Public data only; RBC internal figures stay out of peer documents | `frow()` refuses any row the study tags `user_provided`; `checks.py` fails if such a tag reaches the outputs |
| Sensitivities never combined; default waterfall is directional | The Surplus comparison is labelled directional; nothing is combined |

## Coverage

| Basis | Insurers |
|---|---|
| ALM study view, OSFI returns | RBC Life, BMO Life, Manulife, Sun Life, Canada Life, Empire Life, ivari, Equitable Life, Co-operators Life, Foresters Life (incl. Canada Protection Plan), Wawanesa Life, Blumont Annuity (in the study's peer set, not on the standing list) |
| ALM study view, AMF filers from company filings | iA Financial Group, Beneva (both est) |
| ALM method applied to OSFI returns, outside the study's peer set | Canadian Premier Life, Primerica Life |
| Earlier annual-report method, because the study is silent | UV Insurance, Assumption Life, Humania |
| No public asset mix | Desjardins Insurance (liability side only, study limitation L42) |

## Rebuild

The ALM repo must be checked out next to this one (`../cdn-life-insurer-alm`). Python runs through that repo's uv environment.

```
uv run --project ../cdn-life-insurer-alm python analysis/portfolio_composition_alm/build.py   # out/*.csv, out/data.json
python3 analysis/portfolio_composition_alm/make_datasets.py                                    # dashboard/datasets/*.json
python3 analysis/portfolio_composition_alm/checks.py                                           # consistency checks
cd analysis/portfolio_composition_alm && node report/render.js                                 # the PDF (needs Playwright)
```

`dashboard/index.html` and `dashboard/charts.js` are the dashboard page. `report/render.js` renders the same page to PDF with a
small stand-in for the dashboard runtime, so the two cannot drift apart. To republish the dashboard, upload the files in
`dashboard/datasets/`, record their ids in `dashboard/published.json` and run `dashboard/make_store.py`.

## Files

- `build.py`: reads the study's processed data and writes the analysis tables in `out/`.
- `inputs/annual_report_fallback.csv`: annual-report figures for the three insurers the study does not cover.
- `out/`: long, unrounded tables (block mix at Level 3, peers, liabilities by line, basis effect, trend, accounting class,
  off-balance-sheet, filings look-through).
- `make_datasets.py`: wide, rounded tables for display, one per chart or table.
- `checks.py`: shares sum to 100, GenAcct ties to the study's peer summary, no user-provided figure in the outputs.

## Known limits

- The OSFI returns separate nine Level 3 categories, so alternatives sit in "other invested" and common shares for OSFI filers
  (study limitations L07, L21). The look-through table reads company filings at each company's reported scope, which is wider
  than GenAcct.
- For Sun Life and Equitable the study's residual method leaves no common shares in GenAcct; both are tagged est.
- Manulife's Surplus is not reliable on public data (L43). iA and Beneva report total CSM only.
- Which assets back Surplus is the study's default waterfall, not a disclosure (L04).
- Internal securitization notes are not public for any insurer.
