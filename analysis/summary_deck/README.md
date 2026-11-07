# Peer landscape summary deck

One deck (PDF, with a matching .pptx) summarising the three peer analyses for RBC Life against the other 19
insurers in the analysis set: discount curves, portfolio composition and investment risk. Built on the
financial-analysis plugin's competitive-analysis framework (insight titles, peer scorecard, strategic context,
synthesis) and drawn in the same style as the standalone analysis PDFs: HTML cards and inline-SVG charts in the
dashboard palette, RBC Life coloured, outlined and bold, peers grey, the peer median as a dashed line or tick.

Rebuild from the repository root:

```
python3 analysis/discount_curves/build.py
python3 analysis/portfolio_composition/build.py
python3 analysis/investment_risk/build.py
python3 analysis/summary_deck/build_deck.py      # writes the PDF and the .pptx
```

| File | What it holds |
| --- | --- |
| `build_deck.py` | Reads the outputs of the three analyses, lays out 21 slides (1280 x 720) as HTML, prints them to PDF with the preinstalled Playwright Chromium, and writes the .pptx. Every number in a title is computed. `KEEP_HTML=path` also saves the HTML. |
| `peer-landscape-summary.pdf` | The deck |
| `peer-landscape-summary.pptx` | The same slides for PowerPoint: title and source line are native text, the slide body is a 2x image, so the charts are not editable chart objects |

Choices to know:
- Peer medians are across every insurer with the metric; ranks count only insurers with data.
- Scorecard balls are terciles of the peer distribution (●●● = top third by value), not a judgement of good or bad.
- The C$35MM earnings limit on slide 15 is the CIO framing used elsewhere in the project, pro-rated to C$25Bn.
- Deal facts on slide 18 come from press coverage (Insurance Portal, Sagicor, Insurance Business); multiples are not disclosed.
- The moat table (slide 19) and the signposts (slide 20) are assessments built on the deck's metrics, not disclosed figures.
