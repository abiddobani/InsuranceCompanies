# Research brief, round 2: corporate hierarchy and investment leadership

Abid (SVP & CIO, RBC Insurance) reviewed the first deep-dive deck and gave three rules for the leadership and
structure pages. Your job is to redo that research for your insurers, to these rules, and write one JSON per insurer.
Today is 2026-11-03.

## Abid's rules

1. **Corporate hierarchy: only the insurer's own website's operating-entities disclosure.** Find the page on the
   insurer's (or its insurance arm's) own website that lists its operating / legal entities: typically "About us >
   Our companies", "Legal entities", "Corporate structure", "Who we are", a footer "legal" page, or an "underwritten
   by / issued by" disclosure page. List exactly the entities that page shows, with the parent/child structure the page
   gives and the page's own one-line description of each. Do NOT add group affiliates from elsewhere. Example of the
   error he flagged: RBC Capital Markets is not part of RBC Insurance, so it must not appear in the RBC Life structure
   just because the bank owns both. If the site has no such page, set `operating_entities` to null and record in
   `gaps` which pages you checked. If the page names who manages the general account (an in-house team or an
   affiliated asset manager that the page itself lists), capture that sentence.
2. **Tenure from LinkedIn.** Abid wants time in seat / at the company / in the industry from each person's LinkedIn
   experience section. LinkedIn returns HTTP 999 to direct fetches from this environment, so do not fetch
   linkedin.com and do not spoof user agents. Try web searches like `"<name>" <company> linkedin` whose result
   snippets sometimes show the experience lines; otherwise use company bios, press releases ("appointed", "joins"),
   proxy circular bios, MarketScreener insider "experience" pages, conference bios. For each date record
   `tenure_source` = "linkedin snippet" / "company bio" / "press release" / "proxy" / etc. Never guess a year; null it.
   Use YYYY-MM where the month is known.
3. **Under the CIO, show ALL direct reports.** Identify the most senior investment officer for the insurer's general
   account (the person accountable for the insurer's portfolio, wherever they sit), then everyone who reports directly
   to them: heads of public fixed income, private credit / private placements, mortgages, real estate, equities,
   alternatives, ALM / portfolio management, investment risk, trading, investment operations, etc. Use team pages of
   the insurer or its affiliated asset manager, press releases that say "reporting to", conference bios, and annual
   reports. Mark each with `reporting_line`: "stated" (a source says they report to the CIO) or "inferred from title"
   (e.g. "Head of Fixed Income, <insurer> Investments" on the CIO's team page). If the CIO is unnamed, say so and leave
   the list empty. Five to ten direct reports is normal for a large insurer; small insurers may have one or two.

Start from the first-round file `analysis/insurer_deep_dive/research/<company_id>.json` (people already found,
with pay and sources); re-verify and extend it. Keep pay figures from there (compensation fields) unless you find a
newer disclosure. `data/companies.csv` has each insurer's website. Bigdata.com and Firecrawl are out of credits; do
not use them. `curl` with an honest descriptive user agent works on most insurer sites.

## Output

Write `analysis/insurer_deep_dive/research/org/<company_id>.json` (create the folder if needed), validate it with
`python3 -m json.tool`, and do not edit any other file or commit.

```json
{
  "company_id": "rbc_life",
  "operating_entities": {
    "source_url": "https://...", "page_title": "", "retrieved": "2026-11-03",
    "entities": [
      {"name": "RBC Insurance", "parent": null, "description": "as the page describes it"},
      {"name": "RBC Life Insurance Company", "parent": "RBC Insurance", "description": ""}
    ],
    "ga_manager_statement": {"text": "", "source": ""},
    "note": ""
  },
  "ceo":  {PERSON},
  "cio":  {PERSON},
  "cio_direct_reports": [{PERSON, "reporting_line": "stated | inferred from title"}],
  "other_leaders": [{PERSON}],
  "gaps": ["what you looked for and could not find"],
  "notes": ""
}
```

PERSON = `{"name": "", "title": "", "entity": "", "reports_to": "", "seat_since": "YYYY or YYYY-MM",
"firm_since": "", "industry_since": "", "prior": "short list of prior firms", "tenure_source": "",
"comp_total": null, "comp_currency": "CAD", "comp_year": null, "comp_source": "", "sources": ["url"], "note": ""}`.
`other_leaders` = CFO and CRO only (and the head of the affiliated asset manager if different from the CIO), max 3.

Final message: one line per insurer saying what the entities page is, how many CIO direct reports you found
(stated vs inferred), and how many tenure dates are still null.
