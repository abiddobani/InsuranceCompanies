# Insurer org charts (3 levels from the CEO)

Two slides per insurer for the 20-company set, built with pptxgenjs: the org chart from the top executive, then the investment team from the CIO down.

- `data/<id>.txt` – sourced people per insurer (L1 CEO, L2 direct reports, L3 under each L2), each with a certainty grade and source keys.
- `make_inv.py` – writes `data/inv/<id>.txt` (investment teams) from LinkedIn findings of 2026-11-06 plus public sources.
- `parse.js` – parses and validates the data files.
- `build_deck.js` – `NODE_PATH=<node_modules with pptxgenjs> PPTX_SKILL_DIR=<pptx skill> node build_deck.js out.pptx`

Certainty: **H** = named with that title on the insurer's own site, filing, circular or release;
**M** = confirmed on the person's LinkedIn profile, recent trade press, or a company page seen only via search;
**L** = LinkedIn search snippet not confirmed on the profile, aggregator (TheOrg, ZoomInfo, MarketScreener), undated or conflicting.
A trailing `~` on a person means the reporting line is inferred from the title (dashed card / italic).

Anchor rule: level 1 is the insurer's own top executive; for subsidiaries without their own CEO
(Co-operators Life, Foresters Life, CPP, Wawanesa Life) level 1 is the group CEO and the subtitle says who runs the insurer.
Full sources and overflow names are in each slide's speaker notes.
