# Street wallet by insurer, rebuilt on the ALM framework

Estimate of what each Canadian life insurer pays the street each year to execute its Canadian
general account: traded volume x a one-way friction cost by product, plus derivative roll costs and
repo dealer margin. Every figure is an estimate.

Write-up: the Claude Doc "Annual street wallet by insurer: ALM framework rebuild"
(https://claude.ai/artifact/XCZncmbCQqEg1GveWYWxWL). The October 2026 estimate
(`analysis/street_wallet/` on branch `claude/project-thread-kegfre`, doc
https://claude.ai/artifact/W9iQnyFEy1geS9hoCEd2rT) is kept for comparison.

## Run

The model reads the ALM repo (MooseDragon/cdn-life-insurer-alm) from a local clone and uses its uv
environment:

    cd <alm repo> && uv sync
    cd <this repo>
    uv run --project <alm repo> python analysis/street_wallet_alm/build.py --alm <alm repo>

It writes the CSVs below next to `build.py` and, when `/mnt/project-files/street-wallet/` exists, to
`/mnt/project-files/street-wallet/alm-rebuild/`.

## What the ALM repo supplies

The repo has no turnover or execution cost method. It supplies the scope, the balance sheets and the
reasons a book trades.

| Used for | ALM repo source |
|---|---|
| Scope: Canadian business only, net of reinsurance, general account excl. par / seg fund with the par block and UL policyholder funds separate, seg fund assets out | `README.md` standing rules, `docs/METHODOLOGY.md` |
| Holdings by block on the Level 1 to 3 taxonomy, fiscal 2025 year-end (12 OSFI filers) | `data/processed/deck2_block_allocation_2025fye.csv` |
| iA (US carved out), Beneva (P&C carved out), Desjardins size, repo balances | `data/processed/peer_summary_2025q4.csv`, `filings_all_long.csv` |
| Bonds maturing within a year and a duration proxy | `data/processed/deck2_maturity_bands.csv` |
| Yearly change in holdings by asset class; class detail | `data/processed/osfi_long.parquet`, LF2 page 21012 |
| Liability mix by product line, to pick turnover proxies the way `research/synthetic_rbc_benchmark.md` picks pure-play peers | `data/processed/icl_by_line_2025q4.csv` |
| Derivative notionals by type and term; repos | `osfi_long.parquet`, LF3 pages 21110 and 22030 |
| Gross purchases and sales, BMO Life and ivari | cash flow statements under `data/raw/` (figures in `inputs/added_flows.csv`) |

## Where the October method still fills gaps (`inputs/`)

- `disclosed_flows_october.csv`: gross investment flows from cash flow statements. Group ratios are
  applied to Canadian assets for the Big 3.
- `other_derivatives.csv`: derivative notes for iA and Beneva, which do not file with OSFI.
- `fallback_holdings.csv`: holdings for Assumption Life, Humania, UV Insurance and Beneva's class
  mix, which are outside OSFI and outside the ALM repo.
- `october_wallet_by_insurer.csv`, `october_wallet_by_year.csv`: the October results, for the
  comparison columns.
- The derivative roll and cost schedule and the flat costs for below-investment-grade bonds and
  shares are constants at the top of `build.py`.

## Drivers

1. Reinvesting maturities: bonds maturing within a year, bought once.
2. New money and rotation: absolute yearly change in each public asset class at OSFI year-ends.
3. Active trading and ALM rebalancing: gross purchases and sales from the cash flow statement, less
   short-term rolls, maturities, private originations and the changes in 2. Insurers with no cash
   flow statement (RBC Life, Co-operators Life) use a liability-mix proxy: individual insurance at
   ivari's rate, annuities at the rate implied by BMO Life, par at Equitable Life's.
4. Money market rolls.
5. UL policyholder fund flows, at ivari's observed fund turnover.
6. Repo funding: dealer margin on the average repo balance.
7. Hedging derivatives: notional by type and term x roll frequency x cost.

Bond costs scale with each insurer's bond duration (half bid-offer in yield x duration).

## Outputs

| File | Contents |
|---|---|
| `wallet_by_insurer.csv` | One row per insurer: Canadian asset base by block, turnover basis, wallet by product, low and high, bps, October comparison, Big 3 whole-entity memo |
| `wallet_by_driver.csv` | Wallet by insurer and driver |
| `wallet_by_block.csv` | Securities cost by block (non-par general account, par, UL funds) |
| `wallet_detail.csv` | Holdings, traded volume and cost by insurer, block and asset class |
| `turnover_calibration.csv` | From gross flows to the active rate, for the 12 insurers with cash flow statements |
| `assumptions.csv` | Every cost and turnover assumption with its basis |

## Limits

- A run rate on fiscal 2025 year-end balance sheets, not a 2021 to 2025 average: the ALM repo holds
  IFRS 17 data only (from fiscal 2023; fiscal 2024 for RBC Life and BMO Life).
- RBC Life publishes no cash flow statement, so its active rate is a proxy and its range is wide.
- Short-term paper is assumed to roll three times a year. BMO Life's active rate is sensitive to it.
- iA, Wawanesa Life and Foresters Life show gross flows above 100% of assets and are capped.
- The Big 3 use group cash flow ratios and entity-wide derivative notionals scaled to the Canadian
  share of investments.
- Desjardins is priced at the peer median bps and is indicative only.
- Public data only. RBC internal figures are not used.
