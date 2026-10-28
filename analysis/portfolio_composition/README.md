# Peer portfolio composition

Latest general-account portfolio of each peer insurer, mapped onto the CIO taxonomy
(Level 1 internally / externally managed, Level 2 asset class, Level 3 sub-class, plus
off-balance-sheet items). Dashboard: https://claude.ai/artifact/FDNcqTW6SYHq7aRg1dp6gE

Run `python3 analysis/portfolio_composition/build.py` (needs only `data/osfi/*_core.csv.gz`
and `disclosed_portfolios.csv`).

| File | What it holds |
| --- | --- |
| `disclosed_portfolios.csv` | Hand-entered figures (C$ millions) from Manulife, Sun Life, Great-West Lifeco, iA, Assumption, Beneva, Humania and UV filings, with the source and arithmetic for each line. Rows starting `EXCLUDED:` record what was taken out. |
| `build.py` | Maps OSFI LF2 P21012 / LF1 P20002 lines for the other OSFI filers, merges the disclosed figures, and writes the outputs below. |
| `portfolio_composition_long.csv` | One row per insurer and Level 3 bucket: amount and share of portfolio. |
| `portfolio_composition_pct.csv` | The same as one row per insurer, shares in %. |
| `off_balance_sheet.csv` | Derivative notionals and repos (OSFI LF3 fiscal 2025, legal entity) plus iA and Manulife note disclosures. |
| `coverage_notes.csv` | As-of date, source, par share of liabilities, exclusions and caveats per insurer. |

Scope: general account only. Excluded where the source allows: segregated funds, participating
accounts (only Canada Life via Lifeco's segment split and Assumption via note 4 disclose par assets by
class), pass-through fund units backing UL, asset-manager client AUM, Manulife Bank loans and
mortgages, own-use property, investments in subsidiaries. Derivative assets are left off the balance
sheet and shown as notionals instead.

Mapping choices to know:
- Level 1 is assigned by asset class: real estate, infrastructure and private equity sit under
  externally managed because no peer discloses who manages its holdings.
- Private placements / private corporate bonds map to Illiquid Term Loans; iA's sub-investment-grade
  corporate loans to Private Liquid Loans. OSFI has no ABS line, so ABS sit in corporate bonds for OSFI
  filers. Policy & Other Loans and Other / Unclassified are additions to the taxonomy.
- Canada Life = Great-West Lifeco's Canada non-par, Europe and Capital & Risk Solutions segments; its
  bond split uses the OSFI Canada Life Assurance mix and its stock split Lifeco's public/private ratio.
- Beneva includes its P&C business (not separable). Desjardins Insurance is not charted: its life
  portfolio is not published apart from Desjardins Group. Canada Protection Plan is part of Foresters.
