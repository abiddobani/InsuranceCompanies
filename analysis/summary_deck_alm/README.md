# Peer landscape summary deck on the ALM framework

One 27-slide deck that summarises the eight peer analyses rebuilt on
[MooseDragon/cdn-life-insurer-alm](https://github.com/MooseDragon/cdn-life-insurer-alm), with RBC Life as the focus.
It replaces the October 28, 2026 summary deck (`analysis/summary_deck`, 21 slides, three analyses) for the Canadian
insurers.

| Output | What it is |
|---|---|
| `peer-landscape-summary-alm.pdf` | The deck, 27 pages, 16:9 |
| `peer-landscape-summary-alm.pptx` | The same slides: native title and source text, slide body as a 2x image |

## Rebuild

```
git fetch origin
python3 analysis/summary_deck_alm/collect_inputs.py    # only to refresh inputs/ from the analysis branches
python3 analysis/summary_deck_alm/build_deck.py
```

Needs pandas, python-pptx and Node with Playwright Chromium. The build prints `OVERFLOW []`; anything inside the
brackets is a slide whose body runs past its frame. `KEEP_HTML=path` also saves the HTML.

## Where the figures come from

The deck recomputes nothing but medians, ranks and differences. `collect_inputs.py` copies the result tables of each
analysis from its branch into `inputs/` and records the commit in `inputs/MANIFEST.json`.

| Section | Slides | Analysis folder | Pull request |
|---|---|---|---|
| Discount curves and illiquidity premium | 8, 9 | `analysis/discount_curves` | #8 |
| Portfolio composition and liabilities by line | 5, 7, 10 to 12 | `analysis/portfolio_composition_alm` | #7 |
| Portfolio reallocations | 13, 14 | `analysis/portfolio_reallocation_alm` | #3 |
| Investment risk: capital, credit, funding, liquidity, sensitivities | 6, 15 to 20 | `analysis/investment_risk_alm` | #6 |
| CSM and surplus durations, FVOCI and OCI | 21, 22 | `analysis/csm_surplus_duration` | #9 |
| Street wallet | 23 | `analysis/street_wallet_alm` | #4 |
| Org charts and deep dives | 24 | `analysis/org_charts`, `analysis/insurer_deep_dive` | #5, #10 |

Slides 1 to 4 are the title, executive summary, what changed against October, and the coverage table; 25 to 27 are
the scorecard, the synthesis for RBC Life and the method page.

## Basis, following the ALM study's standing rules

- Canadian business only, net of reinsurance. General Account excl. par / seg fund; par, seg fund and UL
  policyholder funds are separate blocks. MFC and SLF Canada follow the global asset mix and CLF uses its disclosed
  Canada column (est).
- IFRS 17 periods only, shown by date. Fiscal 2025 year-ends are Oct 31, 2025 for RBC Life and BMO Life and
  Dec 31, 2025 for the others. History starts Dec 31, 2023 (Jan 31, 2024 for RBC Life). The street wallet is a
  fiscal 2025 run rate.
- Public data only. RBC internal figures are not used, so the October deck's internal earnings limit and the summed
  earnings-at-risk figure are gone. Sensitivities are shown one risk at a time on each insurer's own shock.
- Anything that needs modelling (dollar effect of the curve, market-drift split of reallocations, private credit
  capacity within LICAT 125%) is listed as a next step with a directional read only.
- Every estimate is marked est. Units are $MM and $BN. Short names follow the study: MFC, SLF, CLF, BLU.

## Where coverage or basis differs between sections

Slide 4 is the full table. In short:

- Eleven insurers carry the full method in every section: RBC Life, BMO Life, MFC, SLF, CLF, Empire Life, ivari,
  Equitable, Co-operators Life, Foresters Life, Wawanesa Life.
- BLU is in the study's peer set but not on the project's list of 20: no curve, deep dive or org chart.
- iA and Beneva are AMF filers on company filings (est): CARLI instead of LICAT, total CSM only, no buffer.
  Desjardins is liabilities only.
- Canadian Premier and Primerica Life are OSFI filers outside the study, built on its rules. Assumption Life,
  Humania and UV Insurance stay on their own statements. Canada Protection Plan sits inside Foresters Life.
- Medians exclude RBC Life and differ by section: LICAT measures use the eight other all-Canada filers (156.9%),
  balance-sheet measures the eleven other OSFI peers (buffer 23.8%), curve premiums 16 peers. The deep dive deck
  shows 153.0% and 24.7% because its medians also take the Big 3 entities, Canadian Premier and Primerica Life.
- RBC Life's 30-year illiquidity premium is 2.49% (est) over BMO Life's risk-free curve, the study's basis, and
  2.00% to 2.18% over the CIBC Life or TD Life curves. The deck states the range wherever the premium appears.

## Design

HTML and inline SVG, printed with Chromium, in the style of the project dashboards. RBC Life is coloured, outlined
and bold; peers are grey; lighter grey marks a peer on a different basis; a dashed line is the peer median.
Categorical colours are the dataviz reference palette in a fixed order. `charts.py` holds the chart helpers.
Title claims that depend on the data are computed or asserted in `build_deck.py`, so the build fails if a refreshed
input no longer supports a title.
