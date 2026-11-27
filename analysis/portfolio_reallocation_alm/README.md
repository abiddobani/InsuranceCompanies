# Peer portfolio reallocations, ALM basis

How Canadian life insurers' general-account asset mixes moved between Dec 31, 2023 and mid-2026, rebuilt on the
methods of [MooseDragon/cdn-life-insurer-alm](https://github.com/MooseDragon/cdn-life-insurer-alm) (the project's
primary framework). It replaces the earlier `analysis/portfolio_reallocation` method (branch
`claude/project-thread-kegfre`) for the Canadian insurers.

Output: `peer-portfolio-reallocations-alm.pdf` (11 pages, A4 landscape).

## What changed from the earlier analysis

| | Earlier | This |
|---|---|---|
| Scope | Legal entity, incl. par, UL funds, foreign operations | Canadian business; General Account excl. par / seg fund; UL policyholder funds out |
| Classes | 6 harmonised classes | ALM taxonomy level 1 / 2 / 3; alternatives as confirmed in the ALM repo on Nov 15, 2026 |
| Window | Q1 2020 to Q2 2026 (IFRS 4 bridged to IFRS 17) | IFRS 17 only: Dec 31, 2023 (RBC Life, BMO Life: Jan 31, 2024) to latest filed date |
| Market effect | Modelled market-drift split | Not modelled (ALM rule: modelling goes to next steps) |
| Context | Assets only | Liability mix by product line, repo funding, LICAT and buffer |

## Method

1. **Invested pool by level 3.** OSFI LF2 investment lines mapped to level 3 exactly as the ALM repo's
   `scripts/build_osfi_assets.py`. Investment property is filed in LF2 only at fiscal year-end, so LF1 line
   `P2000211001` is used between year-ends. LF1 cash is outside the pool, as in the ALM block allocation.
2. **Blocks.** The ALM repo's fiscal 2025 block allocation (`scripts/deck2/block_allocation.py`, finding BI-04) is
   extended to every filed date: pool, less UL policyholder funds (LF2 index-linked lines), less the par account,
   residual = non-par / seg General Account. Block sizes come from the ALM `peer_summary_<period>.csv` views.
3. **Par mix.** Par is removed at the public par fact-sheet mix where one is on hand (SLF, Empire Life, Equitable;
   RBC Life target mix), otherwise at the pool mix. The fiscal 2025 mix is held for every date (est).
4. **Big 3.** MFC and SLF Canada follow the entity (global) mix. CLF uses the Canada non-par mix disclosed in the
   Great-West Lifeco MD&A (annual). Lifeco re-presented that table in 2025, so Dec 31, 2023 is chain-linked (est).
5. **Reallocation.** Change in share between dates (percentage points) and share × block size ($MM).
6. **Outside the ALM data.** iA (quarterly level 3 from its supplementary information packages), Beneva, UV
   Insurance, Assumption Life and Humania (annual, coarser classes) use the earlier project inputs in `inputs/`.
   Canadian Premier Life and Primerica Life use the OSFI pool without a block view. Desjardins publishes no
   stand-alone balance sheet.

Check: at Oct 31 / Dec 31, 2025 the rebuilt non-par level 3 shares equal the ALM repo's
`deck2_block_allocation_2025fye.csv` for all 12 OSFI peers (`regression_check.csv`, largest difference 0.0 pts).

## Rebuild

Needs a checkout of the ALM repo with its processed data (`data/processed/`), and `uv`.

```
uv run analysis/portfolio_reallocation_alm/build.py --alm ../cdn-life-insurer-alm
uv run analysis/portfolio_reallocation_alm/make_report.py
```

`build.py` writes `mix_by_date.csv`, `changes.csv`, `context.csv`, `regression_check.csv` and `report_data.json`.
`make_report.py` writes `report.html` and prints the PDF with Playwright Chromium (node).

## Files

| File | Content |
|---|---|
| `mix_by_date.csv` | Share and $ by insurer, date, level 3 (non-par / seg General Account; entity pool for reference) |
| `changes.csv` | First-to-latest change by insurer and level 3 |
| `context.csv` | Block sizes, repos, financing, buffer, LICAT, CSM, Surplus by insurer and date |
| `regression_check.csv` | Comparison with the ALM repo's fiscal 2025 block allocation |
| `inputs/` | iA quarterly level 3 and annual points for insurers outside OSFI data (earlier method) |

## Estimates and limitations

- Par mix is held at fiscal 2025, so a real change in a par account's mix appears as a non-par move. Equitable
  (par 74% of the pool) is low reliability.
- 2026 block sizes hold their fiscal 2025 year-end share of the pool; the ALM views end at fiscal 2025.
- MFC and SLF mixes include foreign operations and exchange-rate moves.
- RBC Life did not file UL lines at Apr 30, 2026; that quarter is interpolated.
- BMO Life starts at Apr 30, 2024: its first IFRS 17 return (Jan 31, 2024) files an incomplete UL line.
- Shares are at balance-sheet value and move with prices as well as trades.
- BLU (Blumont) is an ALM study peer that is not on the project's list of 20 insurers; it is kept as the pure
  PRT comparator.
- Public data only. No RBC internal figures.
