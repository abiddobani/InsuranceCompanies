# Peer portfolio reallocations, 2020 to 2026

Quarterly time series of how the 20 peers' general-account invested assets moved between asset
classes from Q1 2020 to Q2 2026, with RBC Life highlighted.

- Dashboard: "Peer portfolio reallocations" (claude.ai artifact https://claude.ai/artifact/WZDe2ntgXmU3SW1qFVWRK7)
- PDF: `peer-portfolio-reallocations.pdf` (A4 landscape, every dashboard view plus an appendix with each peer's mix)

## Run

    python3 analysis/portfolio_reallocation/build.py [--refresh-market]
    python3 analysis/portfolio_reallocation/make_pdf.py path/to/d3.min.js

`build.py` writes the CSVs below into this folder and `dashboard/`. `--refresh-market` re-downloads
the Bank of Canada long yield and USD/CAD (Valet) and the S&P/TSX composite (Yahoo Finance) into
`market_context.csv`; without it the cached file is used. `make_pdf.py` runs `dashboard/index.html`
against a stand-in for the dashboard runtime and prints it with the preinstalled Playwright Chromium.

## Sources

| Peers | Frequency | Source |
| --- | --- | --- |
| Manulife, Sun Life, Canada Life, RBC Life, BMO Life, ivari, Empire, Equitable, Co-operators, Wawanesa, Foresters (incl. Canada Protection Plan), Canadian Premier, Primerica | Quarterly | OSFI 10Q page P20010 (IFRS 4, to 2022 or calendar 2023Q3) and LF1/LF2 (IFRS 17, from 2023), via `data/osfi/portfolio_mix.csv` and the LF2 P21012 investment schedule |
| iA Financial Group | Quarterly | iA supplementary information packages, "Invested Assets" sheets (`docs/ia`) |
| Beneva, Assumption Life, Humania, UV Insurance | Yearly | Annual report statements of financial position and investment notes (`annual_points.csv`) |
| Desjardins Insurance | n/a | No stand-alone life-company investment breakdown is published |

RBC Life and BMO Life have an October year end: fiscal Q1 (31 January) is placed in calendar Q4 of
the prior year, so their IFRS 17 switch falls between calendar 2023Q3 and 2023Q4.

## Method

- Classes: cash and short-term, bonds, mortgages and loans, equities, real estate, other invested
  assets, mapped to Level 2 of the CIO taxonomy used in `analysis/portfolio_composition`. From 2023,
  OSFI LF2 detail maps to Level 3 (`detail_ifrs17.csv`).
- Left out on both bases: policy loans (IFRS 17 moved them out of invested assets), derivative
  assets, segregated funds, pass-through fund units and investments in subsidiaries.
- Reallocation (C$) = (change in share - break) x invested assets at the end of the period, so it
  is money moved relative to holding the mix constant. Growth = prior share x change in total.
- IFRS 17 switch, using the same balance-sheet date restated (`ifrs17_bridge.csv`):
  restatement under 1% counts the switch quarter as reallocation; 1% or more (Manulife, Sun Life,
  Canada Life, BMO Life, ivari) keeps the quarter out of totals; iA and Beneva restated by class,
  so only that class-level restatement is removed.
- Corporate events (UV's purchase of the BMO Life block, 2025) and quarters where invested assets
  moved more than 15% are kept out of totals and listed in `flags.csv`.
- Market drift (estimate): bonds repriced at -10 x change in the long Canada yield, equities with the
  S&P/TSX composite, other classes held flat; the rest is "active". Canadian proxies are rough for
  the US- and Asia-heavy Manulife and Sun Life books.

## Files

`mix_history.csv`, `changes.csv`, `cumulative.csv`, `detail_ifrs17.csv`, `flags.csv`,
`ifrs17_bridge.csv`, `ifrs17_bridge_by_class.csv`, `coverage.csv`, `bond_quality.csv`,
`market_context.csv`, `annual_points.csv` (hand-entered annual report figures with page sources).

## Caveats

OSFI legal-entity returns include the participating account and, for Manulife, Sun Life and
Canada Life, foreign branches and subsidiaries, so C$ amounts also move with exchange rates.
iA, Beneva and UV equities include private equity. Primerica's first LF2 return shows 13.7% of
bonds below investment grade and every later return close to zero, which looks like a filing
classification change.
