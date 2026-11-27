"""List every person on the leadership pages (CEO, CIO, CIO direct reports, other leaders) for the LinkedIn tenure pass.

Writes research/org/linkedin_names.csv; the pass fills research/org/linkedin_tenure.csv with the same company_id and
name plus seat_since / firm_since / industry_since (YYYY-MM where shown), title and profile_url, which build_deck.py
applies on top of the public-source dates. Run from the repository root.
"""
import csv
import json
from pathlib import Path

ORG = Path(__file__).resolve().parent / "research" / "org"
rows = []
for p in sorted(ORG.glob("*.json")):
    d = json.loads(p.read_text())
    cid = d.get("company_id", p.stem)
    for slot, people in [("CEO", [d.get("ceo")]), ("CIO", [d.get("cio")]), ("CIO direct report", d.get("cio_direct_reports") or []),
                         ("Other leader", d.get("other_leaders") or [])]:
        for x in people:
            if isinstance(x, dict) and x.get("name"):
                rows.append(dict(company_id=cid, slot=slot, name=x["name"], title=x.get("title") or "", entity=x.get("entity") or "",
                                 seat_since=x.get("seat_since") or "", firm_since=x.get("firm_since") or "",
                                 industry_since=x.get("industry_since") or "", current_source=x.get("tenure_source") or ""))
with open(ORG / "linkedin_names.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["company_id"])
    w.writeheader()
    w.writerows(rows)
print("wrote", ORG / "linkedin_names.csv", len(rows), "people")
