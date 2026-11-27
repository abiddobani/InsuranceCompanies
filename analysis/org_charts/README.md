# Insurer org charts: who runs the ALM chain

Version 2 (27 November 2026). Three slides per insurer for the 20-company set, built with pptxgenjs, in the same layout for every company:

1. the org chart from the top executive, three levels deep, with the ALM-chain seats tagged in blue (investments, ALM, actuarial, finance, risk);
2. the investment team from the CIO or investment lead down;
3. the ALM chain: six fixed seats (investments, ALM, Chief Actuary, Appointed Actuary, finance, risk) set against the balance sheet they manage and the insurer's own words on ALM governance.

The deck opens with the key finding, a how-to-read page and a 20-row seat matrix, and closes with what changed since version 1 (6 November 2026) and the limits.

## Lens

`MooseDragon/cdn-life-insurer-alm` is the project's primary framework for Canadian life insurers. This deck takes from it:

- the order: RBC Life first, then bank-owned, Big 3 and non-Big 3 by General Account size; insurers with no peer view in the repo come last;
- the balance-sheet figures on slide 3 (General Account excl. par / seg fund, LICAT, buffer, par and seg fund blocks, financing, core liabilities by line), copied from the repo's processed files with its definitions and its fiscal 2025 year-end dates;
- the Appointed Actuary names and ALM governance statements, read from the annual reports and statements the repo holds;
- the house style: brand palette from `style/brand_style.py`, action titles, dates rather than quarter labels, $BN, inference labelled, public data only.

Where the repo is silent (who reports to whom), the version 1 method stands: hierarchy from the insurer's own pages first, LinkedIn for tenure and for teams below the CIO, trade press last.

## Files

- `data/<id>.txt`: sourced people per insurer (L1 top executive, L2 direct reports, L3 under each L2), each with a certainty grade and source keys.
- `make_inv.py`: writes `data/inv/<id>.txt` (investment teams) from the LinkedIn read of 2026-11-06 plus public sources.
- `alm_context.py`: `python3 alm_context.py <path to cdn-life-insurer-alm> > data/alm_context.json`. Stdlib only; copies figures from the repo, estimates nothing.
- `make_functions.py`: writes `data/functions.json`, the six seats, action title, lead and governance statements per insurer, each with source keys.
- `parse.js`: parses and validates the people files.
- `build_deck.js`: `NODE_PATH=<node_modules with pptxgenjs> PPTX_SKILL_DIR=<pptx skill> node build_deck.js out.pptx`. Counts used in titles are computed from the data and asserted before the file is written.

## Certainty

**H** = named with that title on the insurer's own site, filing, circular or release;
**M** = confirmed on the person's LinkedIn profile, recent trade press, or a filing that later evidence may have overtaken;
**L** = LinkedIn search snippet not confirmed on the profile, aggregator (TheOrg, ZoomInfo, MarketScreener), undated or conflicting.
A trailing `~` on a person means the reporting line is inferred from the title (dashed card / italic).
On slide 3 a grey seat is one that exists, or is required by law, but has nobody named publicly.

Anchor rule: level 1 is the insurer's own top executive; for subsidiaries without their own CEO
(Co-operators Life, Foresters Life, CPP, Wawanesa Life) level 1 is the group CEO and the subtitle says who runs the insurer.
Full sources and overflow names are in each slide's speaker notes.

## Limits

- LinkedIn was last read on 6 November 2026. Leadership pages were re-read on 27 November 2026; sunlife.com, manulife.com and bmo.com block automated reads and were checked through filings, releases and search.
- Assumption Life, Humania and UV Insurance are outside the ALM repo (no OSFI returns), so their slide 3 has no balance-sheet band. Primerica Life Canada and Canadian Premier Life show OSFI headline figures only; Desjardins shows the repo's liabilities view.
- RBC Life's CFO, CRO, Chief Actuary, Appointed Actuary and Head of ALM are on no public page. RBC internal information is not used.
