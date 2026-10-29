# CSM and surplus portfolio durations

Estimated duration of the assets backing each peer's contractual service margin (CSM) and surplus, by asset
class, with each insurer's fair-value-through-OCI (FVOCI) exposure and what it says about OCI or FVOCI limits.
Fiscal 2025 year-end data (RBC Life and BMO Life: October 31; everyone else December 31).

```
python3 osfi_extract.py      # OSFI LF1/LF2/LF3/LCA/LCQ data points -> osfi_inputs.csv (needs the OSFI files in ../../data)
python3 build.py             # -> results.csv, portfolio_breakdown.csv, csm_runoff.csv, class_durations.csv, fvoci.csv, parameters.csv
python3 make_pdf.py path/to/d3.min.js /mnt/project-files/csm-surplus-duration/csm-surplus-durations.pdf
```

`disclosed_inputs.py` holds the hand-entered figures from annual reports, with the page or note for each.

## Why everything here is an estimate

No peer reports which assets back its CSM or its surplus, or the duration of either. Under IFRS 17 the CSM is
measured at locked-in rates, so the assets behind it, and behind surplus, are the insurer's accounting rate
exposure. The model builds the two portfolios from what is published and labels every figure as disclosed or
estimated.

## Method

1. **Class durations.** Each debt maturity bucket in the notes is given a representative term (parameters.csv)
   and converted to the modified duration of a par bond at a flat 4.25% yield. Equity, real estate and
   alternatives carry no rate duration. Cash is 0.25 years. Where an insurer publishes no maturity table, bonds
   take a liability-mix proxy from OSFI LF3 P22010 lines (individual insurance 13, individual annuities 8, group
   insurance 5, group annuities 10, par 12 years).
2. **CSM run-off duration.** The disclosed CSM recognition schedule is spread evenly within each bucket; the
   open-ended last bucket decays geometrically from the last full bucket's yearly level (ratio capped at 0.97).
   The Macaulay duration of that stream at 4.25% is the CSM run-off duration. Without a schedule, a geometric
   run-off at the 2025 release rate (CSM recognised over CSM before release) is used and scaled by 0.984, the
   median ratio of the two methods across the five insurers where both can be computed.
3. **Pool.** CSM portfolio plus surplus portfolio = net CSM (issued less reinsurance held) + equity less goodwill
   and intangibles. Where the insurer separates these assets (FVOCI and amortized cost designation at Sun Life,
   Canada Life, BMO, Co-operators, Canadian Premier, Assumption and RBC Life; Beneva's assets outside the matching
   portfolio), the pool takes that mix; a shortfall is filled at general-account weights. Elsewhere the pool
   mirrors the general account (../portfolio_composition). Manulife designates liability-backing debt at FVOCI
   with the IFRS 17 OCI option, so its FVOCI book is not a surplus proxy. Designated fixed income with no
   maturity data takes the peer median of 5.0 years (Sun Life FVOCI debt and Foresters surplus).
4. **Split.** Surplus takes the pool's equity, real estate and alternatives first; the CSM portfolio takes fixed
   income; remaining fixed income is shared pro rata.
5. **Check.** Where the insurer publishes the after-tax rate sensitivity of total equity, the implied net
   duration of the pool is sensitivity / (1 − 26.5%) / shock / pool. Near zero means the CSM and surplus assets
   are hedged or matched on an IFRS basis.

## FVOCI and OCI limits

FVOCI amounts come from OSFI LF2 P21012 (column 16 FVOCI, 36 amortized cost) for OSFI filers and from the notes
for Sun Life, Beneva and Assumption. AOCI on FVOCI assets is from LF2 P70042 (Manulife: group figure from the
consolidated financial statements). OCI rate sensitivities are quoted as disclosed. Where none is disclosed, an
after-tax OCI change for a 50bp fall is estimated as FVOCI fixed income × pool fixed-income duration × 0.5% ×
(1 − 26.5%). No peer publishes a numeric OCI or FVOCI limit; the `disclosed_limits` column quotes what each says.

## Caveats

- Desjardins publishes no equity for its life subsidiary, so its surplus portfolio is not sized.
- Canada Protection Plan is part of Foresters Life. UV and Humania publish summary statements only (no CSM).
- RBC Life publishes no maturity table and no rate sensitivity: its pool is the FVOCI and amortized cost book from
  OSFI returns, at the peer FVOCI duration. Its positive AOCI on FVOCI debt suggests a short or recently bought
  book, consistent with that assumption.
