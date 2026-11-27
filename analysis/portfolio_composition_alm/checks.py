"""Consistency checks on the built tables. Run after build.py and make_datasets.py; exits non-zero on a failure."""
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALM = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parents[2] / "cdn-life-insurer-alm"
ds = lambda k: json.loads((HERE / "dashboard" / "datasets" / f"{k}.json").read_text())
fails = []


def check(ok, msg):
    if not ok:
        fails.append(msg)


peers = ds("peers")
cls = [k for k in peers[0] if k.startswith("pct_") and k not in ("pct_internally_managed", "pct_externally_managed", "pct_unclassified")]
for p in peers:
    if p["has_mix"] != "yes":
        continue
    check(abs(sum(p[c] for c in cls) - 100) <= 0.4, f"{p['insurer']}: class shares sum to {sum(p[c] for c in cls):.1f}")
    check(abs(p["pct_internally_managed"] + p["pct_externally_managed"] + p["pct_unclassified"] - 100) <= 0.3, f"{p['insurer']}: Level 1 shares")
    if p["fcf_pct_genacct"] is not None:
        tot = p["fcf_pct_genacct"] + p["csm_pct_genacct"] + p["surplus_pct_genacct"] + p["financing_pct_genacct"]
        check(60 <= tot <= 101, f"{p['insurer']}: funding stack sums to {tot:.1f}% of GenAcct")
for r in ds("genacct_l3") + ds("par_l3"):
    s = sum(v for k, v in r.items() if k not in ("insurer", "insurer_name", "amount_mm", "source"))
    check(abs(s - 100) <= 0.6, f"{r['insurer']}: Level 3 shares sum to {s:.1f}")
for r in ds("liabilities"):
    s = sum(r[k] or 0 for k in r if k.endswith("_pct") and k != "long_liab_pct")
    check(abs(s - 100) <= 0.3, f"{r['insurer']}: product lines sum to {s:.1f}")
for r in ds("accounting"):
    check(abs(r["fvtpl_pct"] + r["fvoci_pct"] + r["amortized_cost_pct"] - 100) <= 0.3, f"{r['insurer']}: accounting classes")

# Tie the General Account back to the ALM study's own peer summary.
summ = {r["short_id"]: r for r in csv.DictReader(open(ALM / "data" / "processed" / "peer_summary_2025q4.csv"))}
for p in peers:
    if p["tier"] == "A":
        check(abs(p["genacct_mm"] - float(summ[p["insurer"]]["genacct_k"]) / 1e3) <= 1, f"{p['insurer']}: GenAcct differs from the ALM peer summary")

# No figure the ALM repo tags as user-provided may reach a peer document.
blob = (HERE / "out" / "data.json").read_text() + "".join(p.read_text() for p in (HERE / "dashboard" / "datasets").glob("*.json"))
check("user_provided" not in blob and "private repo" not in blob, "a user-provided source tag reached the outputs")

print("\n".join(fails) if fails else f"all checks pass ({len(peers)} insurers)")
sys.exit(1 if fails else 0)
