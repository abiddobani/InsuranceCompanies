# Peer landscape summary deck

One PowerPoint deck (and its PDF) summarising the three peer analyses for RBC Life against the other 19
insurers in the analysis set: discount curves, portfolio composition and investment risk. Built with the
financial-analysis plugin's competitive-analysis framework (insight titles, native chart objects, sources on
every slide, peer scorecard, strategic context and synthesis).

Rebuild from the repository root:

```
python3 analysis/discount_curves/build.py
python3 analysis/portfolio_composition/build.py
python3 analysis/investment_risk/build.py
python3 analysis/summary_deck/build_deck.py
soffice --headless --convert-to pdf --outdir analysis/summary_deck analysis/summary_deck/peer-landscape-summary.pptx
```

| File | What it holds |
| --- | --- |
| `build_deck.py` | Reads the outputs of the three analyses and writes the deck; every number in a title is computed |
| `peer-landscape-summary.pptx` | The deck (21 slides, editable charts) |
| `peer-landscape-summary.pdf` | PDF export of the deck |

Choices to know:
- Peer medians are across every insurer with the metric; ranks count only insurers with data.
- Scorecard balls are terciles of the peer distribution (●●● = top third by value), not a judgement of good or bad.
- The C$35MM earnings limit on slide 15 is the CIO framing used elsewhere in the project, pro-rated to C$25Bn.
- Deal facts on slide 18 come from press coverage (Insurance Portal, Sagicor, Insurance Business); multiples are not disclosed.
- The moat table (slide 19) and the signposts (slide 20) are assessments built on the deck's metrics, not disclosed figures.
