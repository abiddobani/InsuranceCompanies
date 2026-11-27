# Research brief: deep-dive deck on the top 20 Canadian life & health insurers

Abid (a CIO-seat investment professional) wants a PowerPoint deck with one section per insurer. The deck builder
(another Claude) already has the quantitative OSFI/annual-report data in this repo: general-account invested
assets and asset mix history, LICAT ratios, repo and derivative notionals from OSFI returns, market sensitivities.
**Your job is the web research that data cannot give**, written as one JSON file per insurer.

Today is 2026-11-03. Use the latest public disclosure (Q2 or Q3 2026 quarterlies, FY2025 annual reports, 2026
proxy circulars which disclose 2025 pay). Every number needs an as-of date and a source URL. **Never invent a
figure, name, date or pay amount.** If you cannot find something, set it to null and say in `gaps` what you looked
for and why it is unavailable (e.g. "mutual, no proxy circular; compensation not disclosed"). Private, mutual and
bank-owned insurers will have many gaps: that is expected and is itself useful information. Mark anything you
infer (not read) with `"inferred": true` or "(inferred)" in the note.

Tools: WebSearch / WebFetch / Firecrawl search+scrape all work; `curl` with an honest descriptive user agent also
reaches most insurer sites (sec.gov needs `User-Agent: "Abid Dobani abid.dobani@gmail.com"`, manulife.com may 403 to
curl; use WebFetch there). Don't spoof browser user agents. Bigdata.com credits are exhausted; don't use it. Skip
share prices (the deck builder pulls quotes itself). Repo data you may read for context:
`data/companies.csv`, `data/document_index.csv` (links to every annual report / MD&A / circular already indexed),
`analysis/*/README.md`. LinkedIn usually blocks fetches; use search-result snippets, company leadership pages,
press releases ("appointed", "joins"), proxy circular bios, Insurance Portal / Benefits Canada / Canadian
Underwriter / Investment Executive coverage, and conference speaker bios.

## What to collect per insurer

1. **Key metrics** (latest): total assets; general-account invested assets as the company discloses them;
   aggregate AUM/AUMA (incl. asset-management arm, seg funds); net income and core/underlying earnings (FY2025 and
   latest LTM or YTD); capital ratio as disclosed (LICAT/CARLI/MCCSR-equivalent, plus internal target range if
   stated); financial leverage ratio; credit ratings (AM Best/S&P/Moody's/DBRS/Fitch, FSR or issuer); size of the
   investments team (headcount of investment professionals, from the asset manager's site or reports, say what it
   counts); employees total; ownership; listed ticker of the insurer or its parent.
2. **Business mix**: the split the company itself reports (segments by earnings, or insurance revenue/premiums by
   line: individual life, group benefits, individual wealth/annuities, group retirement/PRT, international). Give
   percentages and the basis.
3. **Org chart** CEO -> CIO (or most senior investment officer) -> head of public markets / fixed income (and, if
   easy, head of private markets/alternatives and the CRO). For each person: name, title, year started in current
   seat, year joined the firm (group), year started in the industry (first finance/insurance job), prior firms
   (short), most recent disclosed total compensation with the year it relates to and source (proxy circular
   summary compensation table; for bank-owned subs it is usually not disclosed; say so). Note where the CIO sits
   (insurer vs asset-management affiliate) and who they report to.
4. **Portfolio-management construct**: who manages the general account (in-house team, affiliated asset manager
   such as SLC Management / Manulife Investment Management / Canada Life Investment Management / Mackenzie /
   Sagard / Northleaf / iA Global Asset Management / Desjardins Global Asset Management, parent bank's asset
   manager, or outsourced/sub-advised mandates and named external managers), the legal/organisational structure,
   any recent changes, and fee or service arrangements if disclosed.
5. **Portfolio rotation commentary**: anything the company says about repositioning the portfolio (e.g. growing
   private credit, cutting real estate, shifting to alternatives, PRT-driven duration), with year. The builder
   already has the numeric mix history; you provide the narrative and any disclosed target allocations.
6. **Leverage and funding**: debt outstanding by type (senior, subordinated, LRCNs, preferred shares, hybrid) with
   amounts and as-of; issuance in 2023-2026 (date, instrument, amount, coupon, maturity); disclosed securities
   lending (amount lent, collateral), repurchase agreements / reverse repos (FS notes "securities sold under
   repurchase agreements"), collateral pledged; structured products / indirect lending exposure (CLOs, ABS, fund
   finance / NAV / subscription lines, significant risk transfer, private ABF, reinsurance sidecars, funding
   agreements, FHLB-style borrowings), with amounts where disclosed.
7. **Partnerships with banks/sponsors**: lead/co-lead bookrunners on their debt or equity issues (from pricing
   press releases or prospectus supplements: name the dealers); bancassurance/distribution deals; notable public
   M&A, reinsurance and asset-management transactions (2020-2026) and advisers if named; strategic partnerships with
   asset managers or sponsors (e.g. stakes in PE/private credit firms, joint ventures); sponsorships (golf
   tournaments, sports, arts, naming rights, conferences). Keep each to one line with year and source.
8. **Risk constructs**: risk appetite framework headline (what limits they describe), risk governance (CRO, board
   risk committee, three lines), internal capital target / operating range, key market sensitivities they disclose
   (equity -10%/-25%, rates ±50bp, spreads, real estate/alternatives), hedging programs (e.g. seg-fund dynamic
   hedging, macro hedges), notable risk events or regulatory actions, ORSA/stress testing notes.

## Output

Write `analysis/insurer_deep_dive/research/<company_id>.json` (company_id from `data/companies.csv`) with this
shape. Keep strings short (deck bullets, max ~140 chars each); put detail in `notes`.

```json
{
  "company_id": "sun_life",
  "name": "Sun Life Financial",
  "as_of": "2026-06-30",
  "ownership": "Public (TSX/NYSE: SLF)",
  "regulator": "OSFI",
  "metrics": [
    {"metric": "Total assets", "value": 371.2, "unit": "C$bn", "as_of": "2026-06-30", "source": "url", "note": ""}
  ],
  "business_mix": {"basis": "Underlying net income by segment, FY2025", "as_of": "2025-12-31", "source": "url",
                    "items": [{"label": "Canada", "pct": 35.0}]},
  "people": [
    {"role": "CEO", "name": "", "title": "", "reports_to": "Board", "entity": "Sun Life Financial Inc.",
     "seat_since": 2021, "firm_since": 1998, "industry_since": 1989, "prior": "",
     "comp_total_cad": 12345678, "comp_currency": "CAD", "comp_year": 2025, "comp_source": "url",
     "sources": ["url"], "note": ""}
  ],
  "pm_structure": {"summary": "", "manager_entities": [""], "bullets": [""], "sources": ["url"]},
  "rotation_commentary": [{"year": 2025, "text": "", "source": "url"}],
  "target_allocations": [{"asset_class": "", "target": "", "source": "url"}],
  "leverage": {
    "debt_outstanding": [{"type": "Senior debentures", "amount_cad_mm": 0, "as_of": "", "source": "url"}],
    "financial_leverage_ratio_pct": null,
    "issuance": [{"date": "2025-05-14", "instrument": "", "amount_cad_mm": 0, "coupon_pct": null, "maturity": "", "bookrunners": [""], "source": "url"}],
    "securities_lending": {"amount_cad_mm": null, "as_of": "", "text": "", "source": ""},
    "repos": {"amount_cad_mm": null, "as_of": "", "text": "", "source": ""},
    "structured_indirect": [{"text": "", "amount_cad_mm": null, "source": ""}]
  },
  "partnerships": {
    "underwriters": [{"dealer": "", "role": "lead / co-lead", "deals": 0, "note": "", "source": ""}],
    "deals": [{"year": 2024, "text": "", "source": ""}],
    "sponsorships": [{"year": 2025, "text": "", "source": ""}],
    "bank_relationships": [{"text": "", "source": ""}]
  },
  "risk": {"appetite": [""], "governance": [""], "capital_target": "", "sensitivities": [""], "hedging": [""], "events": [""], "sources": ["url"]},
  "gaps": [""],
  "notes": ""
}
```

Validate the JSON with `python3 -m json.tool` before finishing. Your final message: one line per insurer saying how
complete the file is and the biggest gaps. Do not edit any other repo files and do not commit.
