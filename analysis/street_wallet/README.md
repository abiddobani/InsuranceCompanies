# Street wallet by insurer, 2021-2025

Estimate of what each peer pays the street each year to execute general-account trading:
traded notional x a market-standard one-way friction cost, by product. Write-up: the Claude Doc
"Annual street wallet by insurer, 2021-2025" (https://claude.ai/artifact/W9iQnyFEy1geS9hoCEd2rT).

    python3 analysis/street_wallet/build.py

Inputs: holdings from `analysis/portfolio_reallocation/` (mix_history, detail_ifrs17, bond_quality),
gross investment flows hand-entered from cash flow statements (`disclosed_flows.csv`), OSFI LF3
page P21110 derivative notionals (`data/osfi/LF3_core.csv.gz`, main legal entity only), and iA and
Beneva derivative notes (`other_derivatives.csv`). Cost and turnover assumptions are constants at
the top of `build.py` and written to `assumptions.csv`.

Outputs: `wallet_by_insurer.csv` (5-year average, C$ mm and bps of invested assets, low-high
range), `wallet_by_year.csv` (by insurer and year, traded volume by class).
