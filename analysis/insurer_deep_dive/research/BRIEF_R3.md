# Research brief, round 3 (2026-11-03)

Abid (SVP & CIO, RBC Insurance) reviewed the deep-dive deck again. Three research tasks come out of it; each analyst
gets one. Shared rules: every figure needs an as-of date and a source URL; never invent a name, date or number (null
it and say why in `note`); mark inferences "(inferred)". Bigdata.com and Firecrawl are out of credits; LinkedIn
blocks fetches (HTTP 999) so do not fetch it. sec.gov needs `User-Agent: "Abid Dobani abid.dobani@gmail.com"`;
otherwise use an honest descriptive user agent and do not spoof browsers. Existing research to start from:
`analysis/insurer_deep_dive/research/<company_id>.json` (round 1) and `research/org/<company_id>.json` (round 2);
`data/companies.csv` and `data/document_index.csv` list sites and indexed annual reports / circulars. Write only
your output file, validate it, do not commit.

## Task A: compensation, total inclusive of base and equity

Abid wants total compensation inclusive of base salary and equity awards, not cash pay alone. For every person in
`research/org/*.json` (ceo, cio, cio_direct_reports, other_leaders) who is a named executive officer with a summary
compensation table (proxy circular / management information circular / 10-K proxy), plus Neil McLaughlin (RBC
Group Head, Wealth Management & Insurance) for context, record the latest year's summary-compensation-table
components. Listed issuers in scope: Manulife (MFC), Sun Life (SLF), Great-West Lifeco (GWO, for Canada Life),
iA Financial (IAG), E-L Financial (ELF, for Empire Life; check also Empire Life's own disclosure), Sagicor (SFC, for
ivari), Primerica (PRI), Royal Bank (RY), Bank of Montreal (BMO). Replace aggregator figures (e.g. Yahoo) with the
circular's table. Output `analysis/insurer_deep_dive/research/comp.csv`, columns:
`company_id,name,title,year,currency,base_salary,share_based,option_based,annual_incentive,long_term_incentive_non_equity,pension_value,all_other,total_sct,total_direct_comp,source_url,page,note`
(`total_sct` = the table's "total compensation"; `total_direct_comp` only if the circular states it). One row per
person; amounts in whole currency units.

## Task B: CIO direct reports by function

Abid: "direct reports [to the CIO] would generally be head of public markets, private markets, trading, direct
lending etc." For each of the 20 insurers, name whoever leads each of these functions **for that insurer's general
account**, including where the function sits in an affiliated asset manager (e.g. SLC Management for Sun Life,
Manulife Investment Management for Manulife, iA Global Asset Management for iA, Addenda for Co-operators, DGAM for
Desjardins, Empire Life Investments for Empire Life), and say whether a source states they report to the CIO
(`reporting_line` = "stated" / "inferred from title" / "functional (sits in affiliated asset manager)").
Functions: `public_markets` (public fixed income / public markets), `private_markets` (private markets /
alternatives / private equity), `direct_lending` (private credit, private placements, direct / commercial lending,
mortgages), `trading` (trading desk, execution, treasury / cash & collateral), `real_assets` (real estate,
infrastructure), `alm` (ALM / portfolio strategy / total fund management). Reuse round-2 names where they fit; the
round-2 notes and gaps also list names deliberately left out (e.g. Manulife Investment Management's public and
private markets CIOs) that do fit here. Output `analysis/insurer_deep_dive/research/org/cio_functions.csv`, columns:
`company_id,function,name,title,entity,reporting_line,seat_since,firm_since,industry_since,tenure_source,source_url,note`
(dates YYYY or YYYY-MM). One row per insurer and function; leave name blank and explain in note when not public.

## Task C: business mix, two views

Abid wants two business-mix views per insurer: **geography** and **type of insurance liability including CSM and
surplus**. The builder already has, for the 13 OSFI filers, OSFI LF3 insurance-contract liabilities by line
(individual insurance, individual annuity, group insurance, group annuity, participating, Canada vs total) and CSM
and surplus (`analysis/csm_surplus_duration/osfi_inputs.csv`, `results.csv`). You fill the rest:
1. Geography for all 20: the split the company reports (insurance revenue, premiums, core/underlying earnings or
   liabilities by region / country; say which). Domestic-only insurers: confirm 100% Canada and cite it (Quebec /
   rest-of-Canada split if they report it).
2. Liability type for the six non-OSFI filers (iA, Beneva, Desjardins Financial Security, UV, Humania, Assumption
   Life): insurance contract liabilities (and investment contract liabilities) by product line, plus CSM and total
   equity / surplus, from the latest annual report notes. Canada Protection Plan: note it uses Foresters Life's.
Output `analysis/insurer_deep_dive/research/business_mix2.csv`, columns:
`company_id,view,label,amount_cad_mm,pct,basis,as_of,source_url,note` (view = geography | liability).
