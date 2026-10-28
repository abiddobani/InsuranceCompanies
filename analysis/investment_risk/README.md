# Peer investment risk benchmark

Market, credit and liquidity risk metrics for the 20 peer insurers, framed on R. Doff,
"Investment risks: market, credit and liquidity risk" (Risk Management for Insurers, Risk.net).
Dashboard: https://claude.ai/artifact/MjKSsVboZFSHyjnsvnV9s5 (RBC Life highlighted).

Run `python3 analysis/investment_risk/build.py` (needs `data/osfi/*_core.csv.gz`, the portfolio
composition outputs in `analysis/portfolio_composition/`, and the three hand-entered files below).

| File | What it holds |
| --- | --- |
| `disclosed_sensitivities.csv` | Rate, spread, equity and alternatives sensitivities (net income C$MM, capital ratio points) from YE2025 MD&As and FS notes, with source, tax basis, denominator and any scaling |
| `disclosed_bond_ratings.csv` | Bond rating splits published at YE2025 |
| `disclosed_liquidity.csv` | The two published liquid-asset totals (Manulife, Great-West Lifeco) |
| `build.py` | Computes OSFI metrics and writes `dashboard/` |
| `dashboard/landscape.csv` | One row per insurer with every headline metric |
| `dashboard/osfi_metrics.csv` | OSFI-derived detail: LICAT credit/market/insurance capital, bond mix, ECL, mortgage arrears, sector concentration |
| `dashboard/sensitivities.csv` | Disclosed sensitivities normalised to bps of invested assets |
| `dashboard/bond_ratings.csv`, `liquidity_tiers.csv`, `sector_mix.csv`, `coverage.csv` | Chart data |
| `dashboard/index.html` | The dashboard page as published |

Choices to know:
- OSFI measures are fiscal 2025 Q4 (October year end for RBC Life and BMO Life), legal entity, and
  LICAT credit and market capital cover non-participating products only.
- Sensitivities are as disclosed; shocks other than ±50 bp / −10% are scaled linearly and flagged
  (Beneva and Desjardins equity −15%, Beneva, Desjardins, Foresters and Wawanesa rates ±100 bp).
  Foresters' rate figures are derived from its liability and asset changes (pre-tax). Big-four
  figures are group-wide (Canada Life = Great-West Lifeco incl. Empower).
- Co-operators General's annual report covers the P&C company, so it is not used for Co-operators Life.
- Liquidity weights (cash 100%, govt 95%, public corporates 85%, ABS and shares 70%, mortgages 50%,
  private debt 40%, RE/PE 20%, policy loans 0%) are illustrative, after Doff's weighted liquidity ratio.
- RBC Life, BMO Life, ivari, Co-operators Life, Canadian Premier and Primerica publish no
  sensitivities; Canada Protection Plan reports inside Foresters.
