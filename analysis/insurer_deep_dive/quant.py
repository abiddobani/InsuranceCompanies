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

TOT = [c for c in LIC.columns if c.startswith("Total Ratio")][0]
CORE = [c for c in LIC.columns if c.startswith("Core Ratio")][0]
CLASSES = ["Bonds", "Mortgages & loans", "Equities", "Real estate", "Other invested assets", "Cash & short-term"]


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
    cu = CUM[CUM.company_id == cid]
    r["cumulative"] = [rec(x, ["asset_class", "start_period", "end_period", "start_share_pct", "end_share_pct",
                               "total_change_pp", "ifrs17_switch_pp", "event_pp", "reallocation_pp", "market_drift_pp",
                               "active_pp", "reallocation_cad_mm", "start_total_cad_mm", "end_total_cad_mm"])
                       for _, x in cu.iterrows()]

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
