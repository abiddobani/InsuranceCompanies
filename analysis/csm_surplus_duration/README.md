# CSM and surplus portfolio durations (cdn-life-insurer-alm basis)

Estimated duration of the assets backing each Canadian life insurer's CSM and Surplus, by asset class, with FVOCI / OCI
exposure and stated limits. Fiscal 2025 year-ends (RBC Life and BMO Life October 31, 2025; others December 31, 2025).

This version replaces the one of 2026-10-29 (branch `claude/project-thread-a82jf2`). Blocks, sizes, rules and most inputs
now come from [MooseDragon/cdn-life-insurer-alm](https://github.com/MooseDragon/cdn-life-insurer-alm), the project's primary
framework. That study lists asset duration and surplus duration as next steps (non-public), so the duration layer here is an
estimate throughout and is reported with a low and a high case.

## Rebuild

```
git clone https://github.com/MooseDragon/cdn-life-insurer-alm ../cdn-life-insurer-alm   # branch main
cd ../cdn-life-insurer-alm && uv sync && cd -
uv run --project ../cdn-life-insurer-alm python analysis/csm_surplus_duration/build.py ../cdn-life-insurer-alm
python3 analysis/csm_surplus_duration/make_pdf.py path/to/d3.min.js      # d3 v7; prints dashboard/index.html
```

`build.py` writes the CSVs here and copies them to `dashboard/`. `boc_benchmark_yields.csv` is the Bank of Canada Valet
download of benchmark bond yields (series `BD.CDN.2YR/5YR/10YR/LONG.DQ.YLD`) used for the OCI regressions.
`disclosed_inputs.py` holds the few disclosures the study's processed files do not carry (iA, Beneva and Desjardins
maturity and CSM tables, Foresters' segment table, limits statements). `v1_results_2026-10-29.csv` is the earlier result
set, kept for the comparison.

## Method

1. **Blocks and sizes** (study): Canada only, General Account excluding par, segregated funds and UL policyholder funds, net
   of reinsurance. CSM in the General Account = CSM excluding segregated fund and par CSM. Surplus = equity less
   "Shareholders' Equity - other". iA and Beneva: total CSM, pool includes par (memo). Desjardins: liabilities only.
2. **Assigning assets** (study limitation L04, approved rule): A where disclosed, otherwise waterfall B, C as a sensitivity.
   - A: Foresters (table of assets supporting surplus); RBC Life and Blumont (FVOCI + amortized cost book at 1.02x and
     1.21x equity plus Tier 1 CSM, the study's designation test).
   - B: liabilities take fixed income; CSM pro rata to that mix; Surplus takes equity, real estate and other assets first,
     then fixed income.
   - C: as B with the CSM pooled with Surplus.
3. **Durations**, by evidence: disclosed asset sensitivity (Empire, BMO Life, Wawanesa, Foresters; OCI sensitivity of FVOCI
   bonds at BMO Life and Beneva); maturity tables at the modified duration of a par bond at 4.25%, open band at start + 10
   years (range + 5 to + 15); realised sensitivity of OCI on FVOCI bonds to the 5-year Canada yield (RBC Life, Co-operators
   Life); peer medians where nothing is published. Equity, preferred shares, real estate and others carry zero.
4. **Surplus fixed income**: the insurer's own surplus-type book where there is one; otherwise whole-book durations (upper
   bound) with the median of disclosed surplus books as the low case.
5. **CSM run-off**: the study's rule (weighted average years, band midpoints, open band at start + 5, undiscounted).
6. **Checks**: disclosed rate sensitivities quoted as printed, one risk at a time; the net change in equity for a rate move
   expressed as years on the two portfolios (directional).

## Files

| File | Content |
|---|---|
| `results.csv` | One row per insurer: sizes, durations (base, low, high), bases A / B / C, run-off, sensitivities |
| `portfolio_breakdown.csv` | CSM and surplus portfolios by asset class with duration and contribution |
| `class_durations.csv` | Duration by insurer, book and asset class with basis and source |
| `csm_runoff.csv`, `csm_runoff_summary.csv` | Run-off schedules and weighted average years |
| `fvoci.csv` | FVOCI and amortized cost books (fiscal 2024, 2025), AOCI, OCI, estimated and disclosed sensitivity, limits |
| `oci_history.csv` | OCI on FVOCI bonds by period against the 5-year Canada yield |
| `sensitivities.csv` | Rate sensitivities as disclosed |
| `changes_vs_v1.csv` | Earlier against new, with drivers |
| `coverage.csv`, `parameters.csv` | Coverage against the project's insurer list; assumptions |
| `dashboard/` | Dashboard page and its data; `csm-surplus-durations.pdf` is its print |

## Limits of the estimate

- Only Foresters publishes the assets supporting surplus. Everything else is assigned by rule.
- The choice of A, B or C moves the answer more than the gap between most peers; read the base case with its alternatives.
- RBC Life publishes no maturity table for the entity. Its fixed-income duration (4.1 years, range 1.9 to 4.9) rests on
  eight OCI observations.
- Manulife and Sun Life use the group asset mix and maturity tables; Canada Life uses Lifeco's maturity table.
- Assumption Life, Canadian Premier, Primerica, Humania and UV Insurance are outside the study's peer set and were not
  rebuilt. Blumont is in the study and is included.
- Key-rate durations, hedges and an asset and liability projection need non-public data.
