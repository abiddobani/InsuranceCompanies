# Peer discount curves and illiquidity premiums, fiscal 2025

How RBC Life's IFRS 17 discount curve and illiquidity premium compare with the other Canadian life insurers, rebuilt on the method and data of the ALM study in `MooseDragon/cdn-life-insurer-alm` (the project's primary framework). It replaces the October 2026 version on branch `claude/project-thread-w0w2ty`.

- Report: `insurer-discount-curves-FY2025.pdf` (13 pages)
- Dashboard: https://claude.ai/artifact/GgTPjfU7vmsaoW1EAGnKRC (private)

## What changed against the October version

| Topic | October version | This version (ALM study rules) |
|---|---|---|
| Basis | RBC Life's forwards compounded to spot, flagged as unconfirmed | Same conversion, now the study's documented rule (LIMITATIONS L17): annual compounding, straight line between filed points, step interpolation as the sensitivity. Peer curves checked as spot against each insurer's own statements |
| Dates | Oct 31 and Dec 31 curves compared as filed | Read by date. Dec 31 peers restated to Oct 31 as own premium plus BMO Life's Oct 31 risk-free curve, years 1 to 30 (`scripts/deck3/curve_band.py`) |
| RBC Life premium | Over a Dec 31 peer median risk-free curve: 1.72% at 30 years | Over BMO Life's risk-free curve at the same Oct 31 date: 2.49% (est). Cross-checks: 2.18% over TD Life, 2.00% over CIBC Life |
| Scope | Legal entity curves | Canadian business, non-par general account first; par and segregated funds separately; liabilities by line from OSFI LF3 |
| Dollar effect | Stylised liability priced on each curve | Dropped. Needs liability cash flows, so it is a next step with a directional read |
| Par | Dividend scale interest rate as the par rate | Kept (the study is silent on par discounting), premium now measured at Dec 31 for every insurer |

## Headline results (fiscal 2025 year ends)

- RBC Life 30-year spot rate 5.75% (est); peer median restated to Oct 31, 2025 is 4.58% (est).
- RBC Life 30-year premium 2.49% (est) against a peer median of 1.32% across 16 peers (range 0.72% Primerica to 2.05% MFC).
- BMO Life's Oct 31, 2025 risk-free curve (3.26% at 30 years) sits below TD Life's (3.57%) and CIBC Life's (3.75%) at the same date. On those references RBC Life's premium is 2.18% and 2.00%. RBC Life's own segregated fund curve converted to spot (3.29%, est) supports the BMO level. The finding holds on every reference; its size depends on the reference.
- RBC Life's ultimate rate is 4.10% (filed forward) against 5.15% for most peers, so its curve is high in the middle and low at the end.

## Run

The build reads the ALM study repo, checked out beside this one, and uses that repo's uv environment.

```
cd InsuranceCompanies
uv run --project ../cdn-life-insurer-alm python analysis/discount_curves/build.py ../cdn-life-insurer-alm
python3 analysis/discount_curves/make_report.py
```

`build.py` ends with checks that tie its figures to the study's own (L17: 5.75%, 5.74%, 2.49%, 1.78%; and `data/processed/curve_band_2025.csv`). `make_report.py` writes `out/report.html` and prints it to PDF with Playwright (Node).

## Files

| File | What it holds |
|---|---|
| `build.py` | Builds every table in `out/` from the study's OSFI panel (`osfi_long.parquet`), filings panel and liabilities by line |
| `make_report.py` | HTML and inline SVG report, printed to PDF |
| `inputs/dsir.csv`, `inputs/par_account_size.csv` | Dividend scale interest rates and par account sizes, carried from the October version |
| `inputs/disclosed_curves_fallback.csv` | Beneva and Assumption Life annual-report curves, which the study's filings panel does not hold |
| `out/headline_fy2025.csv` | One row per insurer: rates, premiums, premium basis, restated 30-year rate |
| `out/band.csv` | RBC Life against the peer median and range, by date, line and tenor |
| `out/reference_curve_check.csv` | BMO Life, TD Life, CIBC Life risk-free curves and RBC Life's premium over each |
| `out/by_line_fy2025.csv`, `out/curves_annual_fy2025.csv` | Curves and premiums by product line |
| `out/par_fy2025.csv` | Dividend scale rate against the filed par curve |
| `out/ultimates_and_basis.csv`, `out/liquidity_buckets_fy2025.csv` | Ultimate rates, basis evidence, most and least illiquid curves |
| `out/trend.csv`, `out/premium_vs_asset_mix.csv`, `out/weighted_premium_fy2025.csv` | Premium through time, against the asset mix, and liability-weighted |
| `out/curves.csv`, `out/rbc_forward_to_spot.csv`, `out/not_covered.csv` | Full curve panel, the forward to spot conversion, insurers with no published curve |

## Rules followed (from the study's README)

Public data only. Canadian business. Periods by date (RBC Life and BMO Life at Oct 31, others at Dec 31). Every estimate marked. Sensitivities never combined across risks. Anything that needs modelling goes to next steps with a directional read. Short names MFC, SLF, CLF; $MM and $BN.

## Limitations

- RBC Life's spot curve, its premium and every restated peer figure are estimates. RBC Life files no risk-free curve and no curve basis statement.
- The date restatement leans on one insurer's risk-free curve (BMO Life). In fiscal 2025 that curve was the lowest of the three October filers, which widens RBC Life's measured premium by up to about 0.5 points at 30 years.
- iA, Desjardins, Beneva and Assumption Life publish one most illiquid curve for all products and no risk-free curve; their premiums are over the median Dec 31 risk-free curve of the OSFI filers.
- Humania, UV Insurance and Canada Protection Plan publish no curve.
- No dollar effect on liabilities, CSM or earnings: that needs liability cash flows by line.
