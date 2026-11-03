"""Assemble the quantitative facts per insurer for the deep-dive deck from the project's earlier analyses.

Inputs (all already in the repo):
  analysis/investment_risk/dashboard/landscape.csv, osfi_metrics.csv, sensitivities.csv, liquidity_tiers.csv
  analysis/portfolio_reallocation/mix_history.csv, cumulative.csv
  analysis/portfolio_composition/off_balance_sheet.csv
  analysis/street_wallet/wallet_by_insurer.csv
  data/osfi/licat_ratios.csv, data/capital_ratios.csv, data/companies.csv

Output: analysis/insurer_deep_dive/quant.json (one record per company_id).
Run from the repository root: python3 analysis/insurer_deep_dive/quant.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
A = ROOT / "analysis"
OUT = Path(__file__).resolve().parent / "quant.json"

CO = pd.read_csv(ROOT / "data/companies.csv")
LS = pd.read_csv(A / "investment_risk/dashboard/landscape.csv")
OM = pd.read_csv(A / "investment_risk/dashboard/osfi_metrics.csv")
SENS = pd.read_csv(A / "investment_risk/dashboard/sensitivities.csv")
LIQ = pd.read_csv(A / "investment_risk/dashboard/liquidity_tiers.csv")
MIX = pd.read_csv(A / "portfolio_reallocation/mix_history.csv")
CUM = pd.read_csv(A / "portfolio_reallocation/cumulative.csv")
OBS = pd.read_csv(A / "portfolio_composition/off_balance_sheet.csv")
WAL = pd.read_csv(A / "street_wallet/wallet_by_insurer.csv")
LIC = pd.read_csv(ROOT / "data/osfi/licat_ratios.csv", skiprows=[1])
CAP = pd.read_csv(ROOT / "data/capital_ratios.csv")
LIAB = pd.read_csv(A / "csm_surplus_duration/osfi_inputs.csv")
CSMS = pd.read_csv(A / "csm_surplus_duration/results.csv")
import gzip
import csv as _csv
OSFI_ENT = {}
for _, x in pd.read_csv(A / "investment_risk/dashboard/osfi_metrics.csv").iterrows():
    OSFI_ENT[x.company_id] = x.entity
LF3_ROWS = {"025": "Individual life", "055": "Individual annuities", "125": "Group benefits", "155": "Group annuities / PRT",
            "510": "Participating"}
LF3 = {}  # (entity, fy) -> {line: [current, prior]} summed over all regions, policies issued, C$MM
with gzip.open(ROOT / "data/osfi/LF3_core.csv.gz", "rt") as f:
    for x in _csv.DictReader(f):
        a = x["address"]
        if x["quarter"] != "Q4" or not a.startswith("P22010") or a[6:9] not in LF3_ROWS or not x["value"]:
            continue
        col = a[-2:]
        if col[1] not in "13":
            continue
        d = LF3.setdefault((x["entity"], int(x["fiscal_year"])), {}).setdefault(LF3_ROWS[a[6:9]], [0.0, 0.0])
        d[0 if col[1] == "1" else 1] += float(x["value"]) / 1000
LINES = [("Individual life", "liab_ind_ins"), ("Individual annuities", "liab_ind_ann"), ("Group benefits", "liab_grp_ins"),
         ("Group annuities / PRT", "liab_grp_ann"), ("Participating", "liab_par")]

TOT = [c for c in LIC.columns if c.startswith("Total Ratio")][0]
CORE = [c for c in LIC.columns if c.startswith("Core Ratio")][0]
# Abid's view: real estate is shown as debt only (mortgages); equity is split public / private & infra / commercial real
# estate. The OSFI and annual-report history supports these six classes; infra is separable only in the latest disclosure.
RENAME = {"Mortgages & loans": "Mortgages (real-estate debt)", "Equities": "Equity: public",
          "Other invested assets": "Equity: private, infra & alts", "Real estate": "Equity: commercial real estate"}
CLASSES = ["Bonds", "Mortgages (real-estate debt)", "Equity: public", "Equity: private, infra & alts",
           "Equity: commercial real estate", "Cash & short-term"]
ALDA = ["Equity: private, infra & alts", "Equity: commercial real estate"]
PCL = pd.read_csv(A / "portfolio_composition/portfolio_composition_long.csv")
EQ_SPLIT = {"Public": ("Common Shares", "Preferred Shares"), "Private": ("Other Private Equity",),
            "Infrastructure": ("Infrastructure Equity",), "Commercial real estate": ("Real Estate Equity",)}
MIX["asset_class"] = MIX.asset_class.replace(RENAME)
CUM["asset_class"] = CUM.asset_class.replace(RENAME)



def clean(v):
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) else round(float(v), 4)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


def rec(row, cols):
    return {c: clean(row[c]) for c in cols if c in row}


def period_key(fy, q):
    return f"{int(fy)}{q}"


out = {}
for _, c in CO.iterrows():
    cid = c.company_id
    r = {"company_id": cid, "company": c.company, "regulator": c.prudential_regulator, "ownership": c.ownership,
         "ticker": None if pd.isna(c.listed_parent_ticker) else c.listed_parent_ticker}

    # ---- landscape metrics
    ls = LS[LS.company_id == cid]
    if len(ls):
        r["landscape"] = rec(ls.iloc[0], [k for k in LS.columns if k not in ("company_id", "company", "is_focus")])
    om = OM[OM.company_id == cid]
    if len(om):
        r["osfi"] = rec(om.iloc[0], [k for k in OM.columns if k not in ("company_id", "company")])
    lq = LIQ[LIQ.company_id == cid]
    r["liquidity_tiers"] = [{"tier": t, "pct": clean(p)} for t, p in zip(lq.tier, lq.pct)]

    # ---- capital: OSFI quarterly history for the primary entity, plus disclosed ratios
    ent = om.entity.iloc[0] if len(om) else None
    hist = []
    if ent is not None:
        h = LIC[(LIC.company_id == cid) & (LIC.entity == ent)].copy()
        h = h[pd.to_numeric(h[TOT], errors="coerce").notna()]
        for _, x in h.iterrows():
            hist.append({"period": period_key(x.fiscal_year, x.quarter), "total": clean(float(x[TOT])),
                         "core": clean(pd.to_numeric(x[CORE], errors="coerce"))})
    r["licat_entity"] = ent
    r["licat_history"] = hist
    cap = CAP[CAP.company_id == cid]
    r["capital_disclosed"] = [rec(x, ["entity", "as_at", "framework", "total_ratio_pct", "prior_as_at",
                                      "prior_total_ratio_pct", "internal_target_disclosed", "source_url", "note"])
                              for _, x in cap.iterrows()]

    # ---- portfolio mix history (6 harmonised classes)
    mh = MIX[MIX.company_id == cid]
    if len(mh):
        piv = mh.pivot_table(index=["period", "period_end", "basis"], columns="asset_class", values="share_pct",
                             aggfunc="sum").reset_index().sort_values("period")
        tot = mh.groupby("period").total_cad_mm.first()
        r["mix_frequency"] = mh.frequency.iloc[0]
        r["mix_source"] = mh.source.iloc[-1]
        r["mix_history"] = [dict(period=x.period, period_end=x.period_end, basis=x.basis,
                                 total_cad_mm=clean(tot.get(x.period)),
                                 **{k: clean(x.get(k, np.nan)) for k in CLASSES}) for _, x in piv.iterrows()]
        # rotation: half the sum of absolute share changes year over year (Q4 to Q4, or annual points)
        ann = piv[piv.period.str.endswith("Q4")].set_index("period")[[k for k in CLASSES if k in piv]]
        turn = (ann.diff().abs().sum(axis=1) / 2).iloc[1:]
        r["rotation_yoy_pp"] = {k: clean(v) for k, v in turn.items()}
        r["alda_history"] = [{"period": x.period, "pct": clean(sum((x.get(k) or 0) for k in ALDA if k in piv))} for _, x in piv.iterrows()]
    cu = CUM[CUM.company_id == cid]
    r["cumulative"] = [rec(x, ["asset_class", "start_period", "end_period", "start_share_pct", "end_share_pct",
                               "total_change_pp", "ifrs17_switch_pp", "event_pp", "reallocation_pp", "market_drift_pp",
                               "active_pp", "reallocation_cad_mm", "start_total_cad_mm", "end_total_cad_mm"])
                       for _, x in cu.iterrows()]

    # ---- latest equity split (public / private / infra / CRE) and ALDA from the portfolio-composition disclosure
    pc = PCL[PCL.company_id == cid]
    if len(pc):
        r["equity_split"] = {"as_of": pc.as_of.iloc[0], "total_cad_mm": clean(pc.amount_cad_mm.sum()),
                             "items": {k: clean(pc[pc.level3.isin(v)].pct_of_portfolio.sum() * 100) for k, v in EQ_SPLIT.items()}}
        r["alda_pct"] = clean(sum(r["equity_split"]["items"][k] for k in ("Private", "Infrastructure", "Commercial real estate")))

    # ---- liabilities by type (OSFI LF3 P22010, policies issued, C$000 -> C$MM), CSM carved out pro rata, plus CSM and surplus
    cs = CSMS[CSMS.company_id == cid]
    csm = clean(cs.csm_net_cad_mm.iloc[0]) if len(cs) else None
    surplus = clean(cs.surplus_cad_mm.iloc[0]) if len(cs) else None
    r["csm_cad_mm"], r["surplus_cad_mm"] = csm, surplus
    lb = LIAB[LIAB.company_id == cid]
    if len(lb):
        x = lb.iloc[0]
        parts = [(lab, max(float(x[k]) / 1000, 0) if pd.notna(x[k]) else 0.0) for lab, k in LINES]
        canada, total = float(x.liab_total_canada) / 1000, float(x.liab_grand_total) / 1000
        if total - canada > 0.01 * total:
            parts.append(("Outside Canada", total - canada))
        liab = sum(v for _, v in parts)
        cut = min(csm or 0, liab)
        parts = [(lab, v * (1 - cut / liab) if liab else v) for lab, v in parts]
        if csm:
            parts.append(("CSM", cut))
        if surplus:
            parts.append(("Surplus", surplus))
        r["liability_mix"] = {"basis": "Insurance contract liabilities by line (OSFI LF3 P22010, policies issued; CSM shown "
                                       "separately, carved out pro rata), plus CSM and surplus (equity less goodwill and intangibles)",
                              "items": [{"label": l, "amount_cad_mm": clean(v)} for l, v in parts if v > 0],
                              "canada_share": clean(canada / total * 100) if total else None}

    # ---- new money vs in-force: where net new assets went vs the in-force mix, and which liabilities grew
    if len(mh):
        tot = mh.groupby("period").total_cad_mm.first()
        amt = mh.pivot_table(index="period", columns="asset_class", values="amount_cad_mm", aggfunc="sum").sort_index()
        bas = mh.groupby("period").basis.first()
        per = list(amt.index)
        i17 = [p for p in per if bas[p] == "IFRS 17"]
        wins = []
        if len(i17) >= 2:
            wins.append(("Since IFRS 17", i17[0], i17[-1]))
        step = 4 if mh.frequency.iloc[0] == "Quarterly" else 1
        if len(per) > step and bas[per[-1 - step]] == bas[per[-1]]:
            wins.append(("Last 12 months", per[-1 - step], per[-1]))
        nm = []
        for lab, a0, a1 in wins:
            d = (amt.loc[a1] - amt.loc[a0]).fillna(0)
            nm.append({"window": lab, "start": a0, "end": a1, "start_total_cad_mm": clean(tot[a0]), "end_total_cad_mm": clean(tot[a1]),
                       "inforce_mix": {k: clean(amt.loc[a0].get(k, 0) / tot[a0] * 100) for k in CLASSES},
                       "delta_cad_mm": {k: clean(d.get(k, 0)) for k in CLASSES}})
        r["new_money"] = nm
    ent = OSFI_ENT.get(cid)
    fys = sorted(fy for (e, fy) in LF3 if e == ent)
    if fys:
        fy = fys[-1]
        r["liability_growth"] = {"fiscal_year": fy, "lines": {k: {"current": clean(v[0]), "prior": clean(v[1])} for k, v in LF3[(ent, fy)].items()}}

    # ---- leverage-type off-balance-sheet positions
    ob = OBS[OBS.company_id == cid]
    r["off_balance_sheet"] = [rec(x, ["as_of", "source", "level1", "level2", "level3", "amount_cad_mm",
                                      "pct_of_portfolio"]) for _, x in ob.iterrows()]

    # ---- trading turnover (street wallet)
    w = WAL[WAL.company_id == cid]
    if len(w):
        r["turnover"] = rec(w.iloc[0], ["years", "avg_invested_assets_cad_mm", "avg_gross_turnover_pct",
                                        "turnover_source", "cost_total_cad_mm", "cost_bps_of_assets"])

    # ---- disclosed sensitivities
    s = SENS[SENS.company_id == cid]
    r["sensitivities"] = [rec(x, ["factor", "as_of", "ni_impact_cad_mm", "ni_bps_invested", "licat_pts", "tax_basis",
                                  "source", "note"]) for _, x in s.iterrows()]
    out[cid] = r

# peer medians for context lines on the per-insurer pages
med = {k: clean(LS[k].median()) for k in LS.select_dtypes("number").columns if k != "is_focus"}
by_p = {}
for v in out.values():
    for h in v["licat_history"]:
        if h["total"] is not None:
            by_p.setdefault(h["period"], []).append(h["total"])
med_licat = [{"period": k, "total": clean(float(np.median(v))), "n": len(v)} for k, v in sorted(by_p.items()) if len(v) >= 5]
OUT.write_text(json.dumps({"peer_median": med, "peer_licat_median": med_licat, "companies": out}, indent=1))
print("wrote", OUT, len(out), "companies")
