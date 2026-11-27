# Peer investment risk benchmark, on the ALM repo's methods

Market, credit and liquidity risk of RBC Life against Canadian life insurer peers at fiscal 2025
year end (RBC Life and BMO Life Oct 31, 2025; the others Dec 31, 2025), rebuilt on
[MooseDragon/cdn-life-insurer-alm](https://github.com/MooseDragon/cdn-life-insurer-alm)
(commit `9e8d671`). It replaces the earlier benchmark in `analysis/investment_risk/` on branch
`claude/project-thread-rj3u0x`, which used the Doff framework.

- Dashboard: https://claude.ai/artifact/MjKSsVboZFSHyjnsvnV9s5
- PDF: `peer-investment-risk-benchmark.pdf` (22 pages, every dashboard tab)

## What the ALM repo changes

| Topic | Earlier benchmark | Now |
|---|---|---|
| Basis | Whole balance sheet | Canadian business, net of reinsurance, General Account excluding par, segregated funds and UL policyholder funds |
| Risk framework | Doff categories, illustrative liquidity weights | LICAT required capital by category, the repo's liquidity and funding measures |
| Sensitivities | Scaled to common shocks and summed into one earnings at risk figure | One risk at a time, each insurer's own shock, never combined or rescaled |
| Peer set | 20 project-list insurers | The repo's 15: 12 OSFI filers (including Blumont) plus iA, Beneva and Desjardins |
| Internal figures | Earnings limit shown | None. RBC internal figures stay out of peer documents |

`dashboard/changes.csv` lists the readings that moved and why.

## Rebuild

```
# 1. datasets, from a checkout of the ALM repo (uses its uv environment)
uv run --project <alm-repo> python analysis/investment_risk_alm/build.py <alm-repo>

# 2. PDF, from the dashboard page and the datasets (needs node with Playwright, and d3 v7)
python3 analysis/investment_risk_alm/make_pdf.py path/to/d3.min.js
```

`build.py` only reads outputs the ALM repo has committed. It asserts that its medians and the
alternatives share tie to the repo's own decks, and stops if they do not. `make_pdf.py` runs the
dashboard page unchanged against a stand-in for the dashboard runtime and fails if anything on
the page is left undrawn.

## Files

| File | What it holds |
|---|---|
| `build.py` | Builds every dataset in `dashboard/` from the ALM repo |
| `make_pdf.py` | Prints all dashboard tabs to the PDF |
| `fallback_sensitivities.csv` | iA, Beneva and Desjardins sensitivities as disclosed (the repo has none for AMF filers) |
| `sensitivity_denominators.csv` | Group invested assets behind group-level sensitivities |
| `outside_study.csv` | Project-list insurers that are not in the ALM repo's peer set |
| `dashboard/index.html` | The dashboard page |
| `dashboard/landscape.csv` | One row per insurer, every measure |
| `dashboard/peer_stats.csv` | RBC Life, median of the other peers and rank, per measure |
| `dashboard/facts.csv` | Single RBC Life figures quoted in the text |
| `dashboard/licat_mix.csv` | LICAT required capital by category |
| `dashboard/asset_mix.csv` | Non-par General Account asset mix |
| `dashboard/sensitivities.csv` | Published sensitivities, per risk, own shock |
| `dashboard/sectors.csv` | Corporate bonds by sector |
| `dashboard/encumbrance.csv` | Repos and pledged assets |
| `dashboard/licat_trend.csv` | LICAT ratio by quarter |
| `dashboard/rbc_capital_path.csv` | RBC Life capital, injections and income over three dates |
| `dashboard/rbc_rotation.csv` | RBC Life fiscal 2026 asset rotation |
| `dashboard/changes.csv` | What changed against the earlier benchmark |
| `dashboard/coverage.csv` | Source quality per insurer and measure |
| `dashboard/outside_study.csv` | The six names outside the study, with what is available |
| `dashboard/build_info.json` | ALM repo commit the datasets were built from |

## Choices and fallbacks

- **125% floor.** The capital floor is the ALM study's assumption, not a filed target.
- **Medians.** Medians are of the other peers, RBC Life excluded, as in the repo's decks. LICAT
  entity measures use the eight other all-Canada filers.
- **Big 3 entities.** Manulife, Sun Life and Canada Life file LICAT for entities that include
  foreign business. They are shown faded and left out of LICAT medians.
- **RBC Life sensitivities.** RBC Life publishes none. The RBC Insurance group figures in RBC's
  annual report (Note 15) are used as a proxy and marked est.
- **AMF filers.** The repo holds no sensitivities for iA, Beneva and Desjardins, so their
  disclosed figures are carried from the earlier benchmark, unscaled.
- **Outside the study.** Canadian Premier Life, Primerica Life, Assumption Life, Humania,
  UV Insurance and Canada Protection Plan are not in the repo's peer set. They appear only in a
  small table on the Method tab.
- **Sensitivities in basis points.** Each is divided by invested assets on the same reporting
  basis as the sensitivity (group over group, entity over entity) so sizes can be compared
  without rescaling the shock.
- **Public data only.** OSFI and AMF filings and the insurers' own published reports.
