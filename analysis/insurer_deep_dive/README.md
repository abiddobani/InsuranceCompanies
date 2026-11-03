# Deep dives on the 20 Canadian life & health insurers

One deck (PowerPoint and PDF, 146 slides) with the same seven-page section, in the same fixed layout, for every insurer in the
analysis set (empty slots say not disclosed rather than changing the layout):

1. Summary: general-account invested assets, capital ratio, AUM, total assets, earnings, investment team, employees,
   financial leverage, credit rating, share price (insurer or listed parent), business mix, disclosure gaps
2. Leadership: CEO → CIO → every named CIO direct report (up to 8 boxes; dashed = reporting line inferred from title),
   with years in seat / at the firm / in the industry and the most recent disclosed pay (year), plus CFO, CRO and the
   affiliated asset manager's head
3. Corporate structure: only the operating entities the insurer lists on its own website, plus who manages the general
   account (group affiliates that are neither listed nor GA managers, e.g. RBC Capital Markets for RBC Life, are left out)
4. Holdings rotation: invested-asset mix 2020-2026 (6 harmonised classes), then vs now, rotation per year, net
   reallocation, and management's own repositioning commentary
5. Leverage: debt and hybrids, issuance 2023-2026 with bookrunners, repos, securities lending, derivative notionals,
   structured / indirect lending
6. Partnerships: dealers on the top line, notable deals 2020-2026, bank and distribution relationships, sponsorships
7. Risk constructs: LICAT history vs the OSFI-filer median, disclosed market sensitivities, risk appetite,
   governance, capital target, hedging, risk profile vs peers

Canada Protection Plan is underwritten by Foresters Life: its section keeps all seven pages, with the investment pages
pointing to Foresters. Five overview pages open the deck (universe, size and capital, who runs the money,
disclosure coverage).

## Rebuild

From the repository root (needs python-pptx, pandas, Pillow and the preinstalled Playwright Chromium):

```
python3 analysis/insurer_deep_dive/quant.py
python3 analysis/insurer_deep_dive/build_deck.py
```

Outputs land in `analysis/insurer_deep_dive/output/`. `DECK_OUT`, `SHOTS`, `KEEP_HTML`, `RESEARCH_DIR` and
`PDF_ONLY` environment variables redirect outputs or inputs. The build prints `OVERFLOW [...]` with any slide whose
cards overflow; it should be empty.

| File | What it holds |
| --- | --- |
| `quant.py` | Pulls the quantitative facts per insurer from the earlier analyses (portfolio reallocation, composition, investment risk, street wallet) and OSFI data into `quant.json` |
| `research/<company_id>.json` | Web research per insurer, every figure with an as-of date and source URL; `research/BRIEF.md` is the research brief |
| `research/org/<company_id>.json` | Round-2 research: operating entities from the insurer's own site, CEO, CIO, all CIO direct reports, CFO/CRO; `research/BRIEF_ORG.md` is the brief |
| `linkedin_names.py` | Lists everyone on the leadership pages (`research/org/linkedin_names.csv`) for a LinkedIn tenure pass; a filled `research/org/linkedin_tenure.csv` (company_id, name, seat_since, firm_since, industry_since as YYYY-MM, title, profile_url) overrides the public-source dates at build time |
| `prices.csv` | Share prices (TSX closes 2 Nov 2026 from EODData; NYSE PRI from Nasdaq) |
| `charts.py` | Inline-SVG chart helpers in the project's dashboard style |
| `build_deck.py` | Builds the HTML slides, prints the PDF with Chromium and writes the .pptx |

## How the .pptx is built

Each slide is the rendered page as an image (Abid prefers the dashboard-style graphics to native chart objects), with
the title as native text on top, and the slide's underlying research (all bullets, every number with its source)
plus the full source URLs in the speaker notes.

## Choices to know

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
