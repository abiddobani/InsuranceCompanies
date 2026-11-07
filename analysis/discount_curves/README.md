# Discount curve landscape

How the 20 peer insurers' IFRS 17 discount curves and illiquidity premiums compare. Run `python3 analysis/discount_curves/build.py` from the repository root to rebuild every output.

| File | What it holds |
| --- | --- |
| `build.py` | Normalises OSFI LF2 curves, adds the annual-report curves, works out premiums and the liability each curve implies, and writes the files below |
| `make_pdf.py` | Prints the by-product pages (tables, curve charts, par vs dividend rate, premiums, RBC Life over time) as a landscape PDF: `python3 analysis/discount_curves/make_pdf.py [period] [out.pdf]` |
| `disclosed_curves.csv` | Least and most illiquid curves copied from the 2025 annual reports of iA, Desjardins, Beneva and Assumption Life (year ends 2024 and 2025), with the document and page |
| `curves_normalised.csv` | Every curve point (company, quarter, region, line of business, tenor) with the risk-free rate, discount rate and illiquidity premium side by side, and how each was obtained |
| `landscape_2025q4.csv` | One row per insurer at year end 2025: headline curve at 1, 5, 10, 20, 30 and 70 years, premiums at the same tenors, ultimate risk-free rate, and the liability on its curve vs the peer median |
| `landscape_latest.csv` | The same for each OSFI filer at its latest quarter |
| `dashboard/product_points.csv` | By insurer, quarter and product (individual annuity, group annuity, individual life, par): spot discount rate and illiquidity premium at 5, 10, 20, 30 and 80 years, with a peer median row per product and quarter |
| `dashboard/product_curves.csv` | The same curves at their published tenors, plus the peer median curve |
| `dsir.csv` | Dividend scale interest rates 2022 to 2026 for the par writers, from PolicyAdvisor's table (RBC Life and Equitable Life confirmed on their own sites) |
| `dashboard/par_vs_dividend_rate.csv` | Each filed par curve (5, 10, 20, 30 and 80 years, flat-equivalent rate) beside the insurer's dividend scale interest rate |
| `par_account_size.csv` | Par account size by insurer ($MM) as published for advisers (PolicyAdvisor 2026; Co-operators from its own par account report), with alternative figures noted |
| `anomalies.csv` | Filed curve points dropped as errors, with the reason |
| `dashboard/*.csv` | The other sources of the landscape dashboard |

Method, in short:

- The headline curve is the most illiquid curve for Canadian non-participating individual insurance. OSFI's LF2 return collects only the most illiquid bucket, so the annual-report curves used are the most illiquid ones too (they cover all products).
- Each OSFI filer reports either a discount rate (LF2 page P35055) or a liquidity premium over its own risk-free curve (P35035); the other is derived. Insurers with no risk-free curve (RBC Life, the annual-report insurers) get an estimated premium over the median risk-free curve of the other OSFI filers for the same quarter.
- RBC Life's filed rates have the shape of one-year forward rates (above 7% at 20 years, below 2% at 70, 4.10% at 80). They are treated as forwards and compounded to spot rates. This is an interpretation; OSFI does not state it.
- Liability vs median: present value of a stylised liability (payments falling 4% a year for 80 years) on each curve against the peer median curve.
- 2023Q1 is excluded: most insurers filed premiums as fractions that OSFI's open data rounds to 0.01 or 0.02, and Wawanesa filed risk-free rates in basis points.
- BMO Life and RBC Life file on an October fiscal year.
- By product: annual-report insurers publish one curve for all products, so they appear under every product. Points are shown at 5, 10, 20, 30 and 80 years; annual-report curves end at 70 years, so their 80-year point is their ultimate rate. RBC Life's 80-year point is the spot rate derived from its forwards; its filed ultimate forward rate is 4.10%.
- RBC Life's par line was one flat rate (about 5.4%) at every tenor until fiscal Q4 2025, repeated unchanged across 2024Q3-Q4 and 2025Q1-Q3, with stray 70-year values (3.38%, 3.60%) that are dropped and logged in anomalies.csv. Flat curves are used as filed; from fiscal Q4 2025 the par line has the same forward shape as RBC's other lines and is converted to spot.
- Par (by product files): each insurer's dividend scale interest rate for the year, flat at every tenor, replaces the filed par curve; the par premium is that rate less the risk-free curve. Insurers with no published dividend scale (ivari, Wawanesa Life, Beneva) are left out of par. The filed par curves remain in curves_normalised.csv and par_vs_dividend_rate.csv.
- Portfolio size (orders the product tables): no public source gives assets or liabilities by product line, so annuity and individual life tables use the line's insurance revenue in Canada for the fiscal year (OSFI LF3 page P45015, row 099; the latest year for quarters after it). Par tables use the par account size in par_account_size.csv. The premiums table uses insurance revenue in Canada across all lines. Annual-report insurers have no revenue split by line and sort last.
- Flat-equivalent rate: the single rate that gives the stylised liability the same value as the curve.
- Not covered: Humania and UV Insurance publish only summary financial statements; Canada Protection Plan is a Foresters business.
