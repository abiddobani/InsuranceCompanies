# Deep dives on the 20 Canadian life & health insurers

One deck (PowerPoint and PDF, 167 slides) with the same eight-page section for every insurer in the analysis set.

**Basis (from Nov 27, 2026): the ALM framework in `MooseDragon/cdn-life-insurer-alm` is the primary method.** Every
balance-sheet, asset, leverage and capital figure is for the Canadian business, net of reinsurance, on the framework's
block view: General Account excl. par / seg fund (GenAcct), fulfilment cash flows as the residual (est), CSM split into
ABL / seg fund / par, Surplus, and the buffer = (Surplus + ABL CSM less net derivative liabilities) / (GenAcct less
repos less derivative assets). Anchor is fiscal year-end 2025 (Oct 31, 2025 for RBC Life and BMO Life, Dec 31, 2025
for the others), IFRS 17 periods only, $MM / $BN, every estimate marked est. The earlier financial-statement method is
kept only where the framework has no data.

| Basis | Insurers | What the pages use |
| --- | --- | --- |
| ALM study | RBC Life, BMO Life, MFC, SLF, CLF, Empire Life, ivari, Equitable Life, Co-operators Life, Foresters Life, Wawanesa Life | The study's peer summary, block view, L1/L2/L3 asset panel, LF3 lines, LICAT and sensitivities |
| ALM study, AMF rule | iA Financial Group, Beneva | Total CSM only, buffer n/a (memo buffer † on total CSM), CARLI instead of LICAT |
| ALM study, liabilities only | Desjardins Insurance | No public balance sheet for Desjardins Financial Security: CSM and fulfilment cash flows only |
| Built on ALM rules | Canadian Premier Life, Primerica Life | Not in the study: built in `alm.py` from the study's OSFI panel on its all-Canada rules (template: the repo's `scripts/build_iof_genacct.py`). Not reviewed in the study and no short ID assigned |
| Financial statements only | Assumption Life, Humania, UV Insurance | No OSFI return: earlier method, pages tagged "financial-statement basis, outside the ALM study" |
| Brand | Canada Protection Plan | Underwritten by Foresters Life: investment pages point to Foresters |

Sections run RBC Life first (the reader's own insurer), then by GenAcct size. Six opening pages: title, basis and
universe table, RBC Life against peers, RBC Life position (sound / exposed / what could be done), who runs the money,
and disclosure coverage. One method page closes the deck.

Pages per insurer:

1. Summary, Canadian business: GenAcct, buffer, capital ratio, Surplus, CSM by piece, par share, financing and
   reinsurance held as % of GenAcct, seg fund and UL blocks, insurance service result and net income, liabilities by
   OSFI product line, a table against RBC Life and the peer median, and the framework's "read with care" flags
2. Leadership: CEO, CIO and six fixed function slots under the CIO, with tenure and total pay (unchanged method)
3. Corporate structure: operating entities from the insurer's own website, who manages the General Account, and the
   entity the ALM framework assesses (what it consolidates and leaves out)
4. Assets and rotation: Level 2 mix at fiscal year-ends 2024 and 2025 and the latest OSFI quarter, the non-par, non-UL
   pool by Level 3 class, private and alternative share against peers, accounting class (FVTPL / FVOCI / amortized cost)
5. New money and liabilities: net additions by Level 3 class (closing less opening balance, no run-off, est) against
   the opening mix, liabilities by line net of reinsurance, and CSM by piece
6. Leverage and reinsurance: financing / GenAcct and reinsurance held / GenAcct against peers, pledged assets,
   affiliate share of reinsurance, derivative notionals, group debt as a memo
7. Partnerships: dealers, notable deals, bank and distribution relationships (unchanged method)
8. Capital and risk: LICAT total ratio by date against the median of the all-Canada OSFI filers, required capital by
   risk with capital above 125% and 100%, sensitivities as worded in each insurer's report (never combined across
   risks or re-based to a common shock), risk appetite, governance

## Rebuild

From the repository root, with a checkout of `MooseDragon/cdn-life-insurer-alm` beside it (the data layer runs inside
that repo's uv environment, as its CLAUDE.md requires; the deck build needs python-pptx, pandas, Pillow and the
preinstalled Playwright Chromium):

```
ALM_REPO=../cdn-life-insurer-alm uv run --project ../cdn-life-insurer-alm python analysis/insurer_deep_dive/alm.py
python3 analysis/insurer_deep_dive/quant.py        # only if the earlier analyses changed
python3 analysis/insurer_deep_dive/build_deck.py
```

`alm.py` reads the ALM repo's processed data and deck JSON (read only) and writes `alm.json` ($MM). Outputs land in
`analysis/insurer_deep_dive/output/`. `DECK_OUT`, `SHOTS`, `KEEP_HTML`, `RESEARCH_DIR` and `PDF_ONLY` environment
variables redirect outputs or inputs. The build prints `OVERFLOW [...]` with any slide whose cards overflow; it
should be empty. `alm.json` was built from the ALM repo at commit 9e8d671.

| File | What it holds |
| --- | --- |
| `alm.py` | Data layer on the ALM framework: one record per insurer with the block view for fiscal 2023 to 2025, asset panel, net additions, liabilities by line, capital, sensitivities and the framework's flags, written to `alm.json` |
| `quant.py` | Pulls the quantitative facts per insurer from the earlier analyses (portfolio reallocation, composition, investment risk, street wallet) and OSFI data into `quant.json` |
| `research/<company_id>.json` | Web research per insurer, every figure with an as-of date and source URL; `research/BRIEF.md` is the research brief |
| `research/org/<company_id>.json` | Round-2 research: operating entities from the insurer's own site, CEO, CIO, all CIO direct reports, CFO/CRO; `research/BRIEF_ORG.md` is the brief |
| `research/comp.csv` | Round 3: summary-compensation-table components (base, share- and option-based, annual and long-term incentive, pension, other, total) per named executive, with circular page; `research/BRIEF_R3.md` is the brief |
| `research/org/cio_functions.csv` | Round 3: who leads each of the six functions for the general account, including inside an affiliated asset manager, and whether the reporting line is stated |
| `research/business_mix2.csv` | Round 3: geography split as each insurer reports it, and liability lines, CSM and surplus for the six non-OSFI filers |
| `linkedin_names.py` | Lists everyone on the leadership pages (`research/org/linkedin_names.csv`) for a LinkedIn tenure pass; a filled `research/org/linkedin_tenure.csv` (company_id, name, seat_since, firm_since, industry_since as YYYY-MM, title, profile_url) overrides the public-source dates at build time |
| `prices.csv` | Share prices (TSX closes 2 Nov 2026 from EODData; NYSE PRI from Nasdaq) |
| `charts.py` | Inline-SVG chart helpers in the project's dashboard style |
| `build_deck.py` | Builds the HTML slides, prints the PDF with Chromium and writes the .pptx |

## How the .pptx is built

Each slide is the rendered page as an image (Abid prefers the dashboard-style graphics to native chart objects), with
the title as native text on top, and the slide's underlying research (all bullets, every number with its source)
plus the full source URLs in the speaker notes.

## Choices to know

- MFC and SLF: the Canadian asset mix follows the legal-entity (global) mix; CLF uses its disclosed Canada column.
  Their asset trend, derivative notionals, LICAT and affiliate share of reinsurance are the legal entity across all
  territories and are labelled so. MFC's buffer is flagged as not reliable (In Canada assets follow asset territory).
- AMF filers (iA, Beneva, Desjardins) are left out of the buffer and LICAT medians; CARLI is shown but not compared.
- Primerica Life: net fulfilment cash flows are an asset (term book, heavily reinsured), so the buffer is n/m and it
  is left out of the buffer median.
- Group-wide sensitivities (RBC, MFC, SLF, CLF) are shown in the table and labelled as group disclosure; they do not
  lead the page title because they are not the Canadian entity.
- Equitable Life: the fiscal 2025 OSFI return moves business from the participating line to individual insurance, so
  the page reads the two lines together.
- Net additions follow the repo's new-money method: closing less opening balance by Level 3 class, no run-off. When
  net additions are under 5% of opening assets the page shows the change in each balance instead of an allocation.
- RBC Life comes first and is marked on every peer chart. The "what could be done" list is drawn from the ALM
  study's public findings; RBC internal figures are not used anywhere.
- Financial-statement pages (insurers outside the study) show IFRS 17 periods from fiscal year-end 2023 only.

The points below apply to the pages that keep the earlier method (people, structure, partnerships and the
financial-statement fallback pages):

- Capital ratio on summary pages is the disclosed figure for the main entity (Sun Life shows SLF Inc. 145%; the risk
  page charts the OSFI LCQ series for Sun Life Assurance Company of Canada). AMF filers show CARLI, Assumption its
  FCNB solvency ratio.
- Tenure uses the start month where a source gives it, else a mid-year start (seat since 2025 shows as 1y in Nov 2026).
  LinkedIn blocks this cloud environment (HTTP 999), so dates come from company bios, releases and filings until the
  LinkedIn file is filled.
- Group-level debt, repos and securities lending (Desjardins Federation, Lifeco, Sagicor) are labelled group level;
  Desjardins deposits are excluded from debt.
- Derivative notionals are OSFI LF3 P21110 gross notionals for the main legal entity (absolute values).
- Rotation per year = half the sum of absolute class-share changes Q4 to Q4; 2023 includes the IFRS 17 basis change
  and is excluded from the average quoted in titles.
- Research notes about tool limits are stripped from slide text; items the researchers could not verify carry
  "(unverified)" or "inferred".
- ALDA = private, infrastructure and alternatives equity plus commercial real estate equity. Mortgages are shown as
  real-estate debt. Infrastructure equity is a separate line only where the latest disclosure splits it (portfolio
  composition dataset); the 2020-2026 history keeps private, infra and alts together.
- New money = change in C$ held per class over the window (net of maturities, market moves and FX), so it shows
  direction, not gross purchases. When net new money is under 5% of the book, the headline uses the longer window and
  the page carries a caution.
- Liabilities by type: OSFI LF3 P22010 lines for the 13 OSFI filers (Canada lines plus "Outside Canada"), CSM carved
  out of the lines pro rata, plus surplus; annual-report notes for iA, Beneva, Desjardins, UV, Humania and Assumption
  (segregated funds excluded). UV and Humania publish no CSM; Desjardins Financial Security publishes no surplus.
- Geography for Manulife, Sun Life and Canada Life is earnings by reporting segment (negative corporate segment
  excluded), which includes an asset-management segment, as those insurers report it.
