"""Display-grade datasets for the dashboard and the PDF report.

Reads out/data.json (written by build.py) and writes one wide, rounded JSON table per chart or table to
dashboard/datasets/. Percentages are rounded to one decimal and $MM to whole numbers so that every printed
figure equals its cell. Nothing is estimated here: all estimates are made, and tagged, in build.py.
"""
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "dashboard" / "datasets"
OUT.mkdir(parents=True, exist_ok=True)
d = json.loads((HERE / "out" / "data.json").read_text())

SHORT = {"IOF": "Foresters Life", "IAG": "iA Financial Group", "BLU": "Blumont Annuity", "DFS": "Desjardins Insurance"}
CODE = {"canadian_premier": "CPL", "primerica_life": "PRI", "uv_insurance": "UV", "assumption_life": "ASL", "humania": "HUM"}
GROUP_ORDER = ["Bank-owned", "Big 3", "Quebec (AMF)", "Mid-size", "Small"]


def r1(x):
    return None if x is None else round(float(x), 1)


def r0(x):
    return None if x is None else int(round(float(x)))


def key(s):
    return (s.lower().replace(" / ", "_").replace("(", "").replace(")", "").replace("&", "and")
            .replace("-", "_").replace(" ", "_"))


peers_in = d["peers"]
name = {p["insurer"]: SHORT.get(p["insurer"], p["insurer_name"]) for p in peers_in}
order = {p["insurer"]: (GROUP_ORDER.index(p["group"]), -(p["genacct_mm"] or 0)) for p in peers_in}
order["RBC"] = (0, -1e12)
CLASSES = d["meta"]["classes"]
CK = [key(c) for c in CLASSES]

# ---------------------------------------------------------------- peers
peers = []
for p in sorted(peers_in, key=lambda p: order[p["insurer"]]):
    tot = (p["genacct_mm"] or 0) + (p["par_mm"] or 0) + (p["ul_mm"] or 0)
    has_mix = p["tier"] != "E"
    row = {
        "insurer": p["insurer"], "code": CODE.get(p["insurer"], p["insurer"]), "insurer_name": name[p["insurer"]],
        "group": p["group"], "tier": p["tier"], "basis": p["tier_label"], "period_end": p["period_end"],
        "on_canonical_list": "yes" if p["on_canonical_list"] else "no",
        "estimate": "est" if p.get("mix_est") else "",
        "has_mix": "yes" if has_mix else "no",
        "genacct_mm": r0(p["genacct_mm"]) if has_mix or p["genacct_mm"] else None,
        "genacct_bn": r1((p["genacct_mm"] or 0) / 1000) if p["genacct_mm"] else None,
        "par_mm": r0(p["par_mm"] or 0), "ul_mm": r0(p["ul_mm"] or 0),
        "blocks_total_bn": r1(tot / 1000) if tot else None,
        "genacct_share_pct": r1(100 * (p["genacct_mm"] or 0) / tot) if tot else None,
        "par_share_pct": r1(100 * (p["par_mm"] or 0) / tot) if tot else None,
        "ul_share_pct": r1(100 * (p["ul_mm"] or 0) / tot) if tot else None,
    }
    for c, k in zip(CLASSES, CK):
        row["pct_" + k] = r1(p.get("pct_" + k)) if has_mix else None
    for f in ["pct_internally_managed", "pct_externally_managed", "pct_unclassified", "illiquid_pct", "non_fixed_income_pct",
              "fcf_pct_genacct", "csm_pct_genacct", "surplus_pct_genacct", "financing_pct_genacct", "long_liab_pct",
              "liab_individual_insurance_pct", "liab_individual_annuity_pct", "liab_group_insurance_pct",
              "liab_group_annuity_pct", "non_fi_to_surplus_x", "buffer_pct", "capital_ratio_pct"]:
        row[f] = r1(p.get(f))
    row["capital_ratio_basis"] = p.get("capital_ratio_basis") or ""
    row["csm_basis"] = p.get("csm_split") or ""
    row["mix_source"] = p.get("mix_basis") or ""
    peers.append(row)

# ---------------------------------------------------------------- Level 3 tables (wide)
def wide(block):
    rows = {}
    for m in d["mix"]:
        if m["block"] != block:
            continue
        r = rows.setdefault(m["insurer"], {"insurer": m["insurer"], "insurer_name": name[m["insurer"]], "amount_mm": 0.0,
                                           "source": m["basis"]})
        r["amount_mm"] += m["amount_mm"]
        r[key(m["l3"])] = r.get(key(m["l3"]), 0) + m["pct_of_block"]
    used = [l for l in d["meta"]["l3"] if any(key(l) in r for r in rows.values())]
    out = []
    for i in sorted(rows, key=lambda i: order[i]):
        r = rows[i]
        o = {"insurer": i, "insurer_name": r["insurer_name"], "amount_mm": r0(r["amount_mm"])}
        for l in used:
            o[key(l)] = r1(r.get(key(l), 0.0))
        o["source"] = r["source"]
        out.append(o)
    return out, used


genacct_l3, used_ga = wide("GenAcct")
par_l3, used_par = wide("Par")
par_l3 = [r for r in par_l3 if r["amount_mm"] > 0]

block_classes = []
for block in ["Par", "UL policyholder funds"]:
    rows = {}
    for m in d["mix"]:
        if m["block"] != block:
            continue
        r = rows.setdefault(m["insurer"], {c: 0.0 for c in CK} | {"amount": 0.0, "source": m["basis"]})
        r[key(m["asset_class"])] += m["pct_of_block"]
        r["amount"] += m["amount_mm"]
    for i in sorted(rows, key=lambda i: order[i]):
        r = rows[i]
        if r["amount"] <= 0:
            continue
        o = {"row": f"{name[i]} | {block}", "insurer": i, "insurer_name": name[i], "block": block, "amount_mm": r0(r["amount"]),
             "amount_bn": r1(r["amount"] / 1000),
             "estimate": "est" if r["source"].startswith("est") or "part est" in r["source"] else ""}
        for c in CK:
            o["pct_" + c] = r1(r[c])
        o["source"] = r["source"]
        block_classes.append(o)

# ---------------------------------------------------------------- liabilities
liab = []
by = {}
for l in d["liab"]:
    by.setdefault(l["insurer"], {})[l["product_line"]] = l
for i in sorted(by, key=lambda i: order[i]):
    p = next(p for p in peers if p["insurer"] == i)
    lines = by[i]
    tot = sum(v["net_icl_mm"] for k, v in lines.items() if k != "Participating")
    o = {"insurer": i, "insurer_name": name[i], "nonpar_icl_mm": r0(tot)}
    for ln in d["meta"]["lines"]:
        o[key(ln) + "_pct"] = r1(lines[ln].get("pct_of_nonpar")) if ln in lines else None
    o["long_liab_pct"] = p["long_liab_pct"]
    o["participating_mm"] = r0(lines["Participating"]["net_icl_mm"]) if "Participating" in lines else 0
    o["source"] = lines["Individual insurance"]["basis"]
    liab.append(o)

# ---------------------------------------------------------------- basis effect, accounting, trend
basis = []
for b in sorted(d["basis_effect"], key=lambda b: order[b["insurer"]]):
    basis.append({"insurer": b["insurer"], "insurer_name": name[b["insurer"]],
                  "entity_pool_mm": r0(b["entity_pool_mm"]), "genacct_mm": r0(b["genacct_mm"]),
                  "entity_public_equity_pct": r1(b["entity_public_equity_pct"]),
                  "genacct_public_equity_pct": r1(b["genacct_public_equity_pct"]),
                  "public_equity_change_pts": r1(r1(b["genacct_public_equity_pct"]) - r1(b["entity_public_equity_pct"])),
                  "entity_private_fi_pct": r1(b["entity_private_fi_pct"]),
                  "genacct_private_fi_pct": r1(b["genacct_private_fi_pct"]),
                  "estimate": next(p["estimate"] for p in peers if p["insurer"] == b["insurer"])})

acct = {}
for a in d["acct"]:
    acct.setdefault(a["insurer"], {"insurer": a["insurer"], "insurer_name": name[a["insurer"]]})[key(a["accounting_class"]) + "_pct"] = r1(a["pct"])
accounting = [acct[i] for i in sorted(acct, key=lambda i: order[i])]

tr = {}
for t in d["trend"]:
    tr.setdefault(t["insurer"], {}).setdefault(t["date"], {})[t["asset_class"]] = t["pct"]
trend = []
TCLS = ["Public Fixed Income", "Private Fixed Income", "Public Equity", "Cash & Cash Equivalent", "Other / unclassified"]
for i in sorted(tr, key=lambda i: order[i]):
    dates = sorted(tr[i])
    a, b = dates[0], dates[-1]
    o = {"insurer": i, "insurer_name": name[i], "from_date": a, "to_date": b}
    for c in TCLS:
        k = key(c)
        o[k + "_to_pct"] = r1(tr[i][b].get(c, 0))
        o[k + "_change_pts"] = r1(r1(tr[i][b].get(c, 0)) - r1(tr[i][a].get(c, 0)))
    trend.append(o)

# ---------------------------------------------------------------- off balance sheet, look-through
ob = {}
OBK = {("Encumbered Assets", "Repos"): "repos_mm", ("Encumbered Assets", "Security Lending"): "securities_lending_mm",
       ("Fixed Income", "Linear"): "fixed_income_linear_notional_mm", ("Fixed Income", "Non-Linear"): "fixed_income_non_linear_notional_mm",
       ("Equity", "Linear and non-linear (not split)"): "equity_notional_mm"}
for o in d["offbs"]:
    r = ob.setdefault(o["insurer"], {"insurer": o["insurer"], "insurer_name": name[o["insurer"]]})
    r[OBK[(o["l2"], o["l3"])]] = r0(o["amount_mm"])
offbs = []
for i in sorted(ob, key=lambda i: order[i]):
    r = ob[i]
    p = next(p for p in peers if p["insurer"] == i)
    row = {"insurer": i, "insurer_name": r["insurer_name"]}
    for k in OBK.values():
        row[k] = r.get(k)
    fin = (row["repos_mm"] or 0) + (row["securities_lending_mm"] or 0)
    row["repos_pct_genacct"] = r1(100 * (row["repos_mm"] or 0) / p["genacct_mm"]) if p["genacct_mm"] else None
    row["derivative_scope"] = "global entity" if i in ("MFC", "SLF", "CLF") else "entity"
    if any(row[k] for k in OBK.values()):
        offbs.append(row)

lk = {}
for l in d["lookthrough"]:
    r = lk.setdefault(l["insurer"], {"insurer": l["insurer"], "insurer_name": name[l["insurer"]], "scope": l["scope"],
                                     "reported_invested_mm": r0(l["reported_invested_mm"])})
    r[key(l["l3"])] = r1(r.get(key(l["l3"]), 0) + l["pct_of_reported"])
used_lk = [l for l in d["meta"]["l3"] if any(key(l) in r for r in lk.values())]
look = []
for i in sorted(lk, key=lambda i: order[i]):
    r = lk[i]
    o = {"insurer": i, "insurer_name": r["insurer_name"], "reported_invested_mm": r["reported_invested_mm"]}
    for l in used_lk:
        o[key(l)] = r.get(key(l))
    o["scope"] = r["scope"]
    look.append(o)

coverage = [{"insurer": p["insurer"], "insurer_name": p["insurer_name"] if p["insurer"] != "IOF" else "Foresters Life (incl. Canada Protection Plan)",
             "period_end": p["period_end"], "basis": p["basis"], "on_canonical_list": p["on_canonical_list"],
             "estimate": p["estimate"], "mix_source": p["mix_source"] or "Not published: Desjardins Financial Security files with the AMF and the group report does not split the life insurer's assets"}
            for p in peers]

# ---------------------------------------------------------------- write
TABLES = {"peers": peers, "genacct_l3": genacct_l3, "par_l3": par_l3, "block_classes": block_classes, "liabilities": liab,
          "basis_effect": basis, "accounting": accounting, "trend": trend, "off_balance_sheet": offbs,
          "lookthrough": look, "coverage": coverage}
for k, v in TABLES.items():
    (OUT / f"{k}.json").write_text(json.dumps(v, indent=1, ensure_ascii=False) + "\n")
(OUT / "_columns.json").write_text(json.dumps({"genacct_l3": [[key(l), l] for l in used_ga], "par_l3": [[key(l), l] for l in used_par],
                                                 "lookthrough": [[key(l), l] for l in used_lk], "classes": [[k, c] for k, c in zip(CK, CLASSES)]}, indent=1) + "\n")

if __name__ == "__main__":
    m = [p for p in peers if p["has_mix"] == "yes"]
    for f in ["pct_public_fixed_income", "pct_private_fixed_income", "non_fixed_income_pct", "illiquid_pct", "surplus_pct_genacct", "non_fi_to_surplus_x"]:
        vals = [p[f] for p in m if p["insurer"] != "RBC" and p[f] is not None]
        rbc = next(p[f] for p in m if p["insurer"] == "RBC")
        rank = 1 + sum(1 for v in vals if v > rbc)
        print(f, "RBC", rbc, "median", round(statistics.median(vals), 1), "n", len(vals), "rank from top", rank, "of", len(vals) + 1)
    for k, v in TABLES.items():
        print(k, len(v), list(v[0].keys()))
