"""Balance-sheet context per insurer, read from the MooseDragon/cdn-life-insurer-alm repo (the project's primary framework).

Usage: python3 alm_context.py <path to cdn-life-insurer-alm> > data/alm_context.json
Stdlib only. Nothing is estimated here: every figure is copied from the repo's processed files
(data/processed/peer_summary_2025q4.csv, icl_by_line_2025q4.csv, universe_2025q4.csv, dfs_liabilities_2025q4.csv)
and keeps the repo's definitions (docs/METHODOLOGY.md sections 7 and 9):
  GenAcct  = General Account excl. par / seg fund, Canadian business, net of reinsurance
  Buffer   = (Surplus + ABL CSM - net derivative liabilities) / (GenAcct - repos - derivative assets)
  Core mix = four non-par lines excl. seg funds (individual insurance, individual annuity, group insurance, group annuity), net
"""
import csv, json, os, sys

REPO = sys.argv[1]
P = lambda f: os.path.join(REPO, "data", "processed", f)
rows = lambda f: list(csv.DictReader(open(P(f), encoding="utf-8")))

# deck id -> repo short ID (docs/DATA.md entity register)
SHORT = {"rbc_life": "RBC", "bmo_life": "BMO", "manulife": "MFC", "sun_life": "SLF", "canada_life": "CLF", "ia": "IAG",
         "desjardins": "DFS", "beneva": "BEN", "empire_life": "EMP", "ivari": "IVA", "equitable_life": "EQL",
         "cooperators_life": "COP", "foresters_life": "IOF", "wawanesa_life": "WAW", "canada_protection_plan": "IOF"}
# OSFI filers outside the repo's peer views: headline figures from the repo's universe file
UNIVERSE = {"primerica_life": "28419", "canadian_premier": "28358"}
LINES = ["Individual insurance", "Individual annuity", "Group insurance", "Group annuity"]

def f(x):
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None

summ = {r["short_id"]: r for r in rows("peer_summary_2025q4.csv")}
icl = {}
for r in rows("icl_by_line_2025q4.csv"):
    icl.setdefault(r["entity"], {})[r["product_line"]] = f(r["net_k"])
uni = {r["id"]: r for r in rows("universe_2025q4.csv")}
dfs = {r["item"].strip(): f(r["amount_k"]) for r in rows("dfs_liabilities_2025q4.csv")}

out = {}
for did, sid in SHORT.items():
    s = summ[sid]
    bn = lambda k: None if f(s[k]) is None else round(f(s[k]) / 1e6, 2)
    o = {"short_id": sid, "tier": s["tier"], "regulator": s["regulator"], "period_end_date": s["period_end_date"],
         "basis": "ALM repo peer view (peer_summary_2025q4.csv)",
         "genacct_bn": bn("genacct_k"), "par_bn": bn("par_account_k"), "seg_bn": bn("seg_funds_k"),
         "surplus_bn": bn("surplus_k"), "csm_abl_bn": bn("csm_abl_k"), "repos_bn": bn("repos_k"),
         "buffer_pct": f(s["buffer_pct"]), "capital_pct": f(s["capital_ratio_pct"]), "capital_basis": s["capital_ratio_basis"],
         "financing_pct": f(s["financing_pct"]), "reinsurance_pct": f(s["reinsurance_pct"]), "par_pct": f(s["par_pct"])}
    if sid in icl:
        core = {k: icl[sid].get(k) or 0.0 for k in LINES}
        tot = sum(core.values())
        o["core_total_bn"] = round(tot / 1e6, 2)
        o["core_mix_pct"] = {k: round(100 * v / tot, 1) for k, v in core.items()}
    if sid == "DFS":
        o["basis"] = "ALM repo liabilities view only (dfs_liabilities_2025q4.csv): no public stand-alone balance sheet (L42)"
        o["fcf_est_bn"] = round(dfs["FCF: BEL + RA incl. par and UL ph liability, net of reinsurance (ESTIMATE)"] / 1e6, 2)
        o["icl_bn"] = round(dfs["Insurance contract liabilities, L&H (net of acquisition cash flow asset)"] / 1e6, 2)
        o["csm_total_bn"] = round(dfs["CSM, total (net of reinsurance; ABL / seg fund / par split not available for an AMF filer)"] / 1e6, 2)
    if did == "canada_protection_plan":
        o["note"] = "Figures are Foresters Life (IOF), which underwrites Canada Protection Plan policies"
    out[did] = o

for did, eid in UNIVERSE.items():
    u = uni[eid]
    bn = lambda k: None if f(u[k]) is None else round(f(u[k]) / 1e6, 2)
    out[did] = {"short_id": None, "tier": "Non-Big 3, outside the peer views", "regulator": "OSFI", "period_end_date": "2025-12-31",
                "basis": "OSFI headline figures from the ALM repo's universe file (universe_2025q4.csv); no peer view built",
                "entity": u["entity"], "total_assets_bn": bn("total_assets"), "investments_bn": bn("investments"),
                "seg_bn": bn("segfund_net_assets"), "equity_bn": bn("total_equity"), "icl_bn": bn("icl"),
                "capital_pct": f(u["licat_total_pct"]), "capital_basis": "LICAT total"}

for did in ("assumption_life", "humania", "uv_insurance"):
    out[did] = {"short_id": None, "tier": "Outside the ALM repo", "regulator": {"assumption_life": "New Brunswick (not in OSFI open data)"}.get(did, "AMF"),
                "basis": "Not in the ALM repo: no OSFI returns and no peer view built"}

# ranks among insurers in this deck that have the figure (Canada Protection Plan repeats Foresters Life and is left out)
def rank(key):
    have = sorted([(v[key], k) for k, v in out.items() if v.get(key) is not None and k != "canada_protection_plan"], reverse=True)
    for i, (_, k) in enumerate(have):
        out[k][key + "_rank"] = [i + 1, len(have)]
    if "canada_protection_plan" in out and "foresters_life" in out and out["foresters_life"].get(key + "_rank"):
        out["canada_protection_plan"][key + "_rank"] = out["foresters_life"][key + "_rank"]

for k in ("genacct_bn", "buffer_pct"):
    rank(k)
# capital ratio rank among LICAT filers only (CARLI is not comparable: AUD-D10)
lic = sorted([(v["capital_pct"], k) for k, v in out.items() if v.get("capital_pct") is not None and v.get("capital_basis") == "LICAT total" and k != "canada_protection_plan"], reverse=True)
for i, (_, k) in enumerate(lic):
    out[k]["capital_pct_rank"] = [i + 1, len(lic)]
out["canada_protection_plan"]["capital_pct_rank"] = out["foresters_life"]["capital_pct_rank"]

json.dump(out, sys.stdout, indent=1, sort_keys=True)
