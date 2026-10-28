# Discount curve landscape

How the 20 peer insurers' IFRS 17 discount curves and illiquidity premiums compare. Run `python3 analysis/discount_curves/build.py` from the repository root to rebuild every output.

| File | What it holds |
| --- | --- |
| `build.py` | Normalises OSFI LF2 curves, adds the annual-report curves, works out premiums and the liability each curve implies, and writes the files below |
| `disclosed_curves.csv` | Least and most illiquid curves copied from the 2025 annual reports of iA, Desjardins, Beneva and Assumption Life (year ends 2024 and 2025), with the document and page |
| `curves_normalised.csv` | Every curve point (company, quarter, region, line of business, tenor) with the risk-free rate, discount rate and illiquidity premium side by side, and how each was obtained |
| `landscape_2025q4.csv` | One row per insurer at year end 2025: headline curve at 1, 5, 10, 20, 30 and 70 years, premiums at the same tenors, ultimate risk-free rate, and the liability on its curve vs the peer median |
| `landscape_latest.csv` | The same for each OSFI filer at its latest quarter |
| `dashboard/product_points.csv` | By insurer, quarter and product (individual annuity, group annuity, individual life, par): discount rate and illiquidity premium at 5, 10, 30 years and ultimate, with a peer median row per product and quarter |
| `dashboard/product_curves.csv` | The same curves at their published tenors, plus the peer median curve |
| `dashboard/*.csv` | The other sources of the landscape dashboard |

Method, in short:

- The headline curve is the most illiquid curve for Canadian non-participating individual insurance. OSFI's LF2 return collects only the most illiquid bucket, so the annual-report curves used are the most illiquid ones too (they cover all products).
- Each OSFI filer reports either a discount rate (LF2 page P35055) or a liquidity premium over its own risk-free curve (P35035); the other is derived. Insurers with no risk-free curve (RBC Life, the annual-report insurers) get an estimated premium over the median risk-free curve of the other OSFI filers for the same quarter.
- RBC Life's filed rates have the shape of one-year forward rates (above 7% at 20 years, below 2% at 70, 4.10% at 80). They are treated as forwards and compounded to spot rates. This is an interpretation; OSFI does not state it.
- Liability vs median: present value of a stylised liability (payments falling 4% a year for 80 years) on each curve against the peer median curve.
- 2023Q1 is excluded: most insurers filed premiums as fractions that OSFI's open data rounds to 0.01 or 0.02, and Wawanesa filed risk-free rates in basis points.
- BMO Life and RBC Life file on an October fiscal year.
- By product: annual-report insurers publish one curve for all products, so they appear under every product. RBC Life's ultimate rate is its filed 80-year forward rate, since its spot curve is still converging at 80 years.
- Not covered: Humania and UV Insurance publish only summary financial statements; Canada Protection Plan is a Foresters business.
