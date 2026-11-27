# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "pyarrow>=17", "numpy>=2"]
# ///
"""Peer portfolio reallocations on the ALM framework (cdn-life-insurer-alm).

Rebuilds the reallocation time series on the methods, definitions and data of the
MooseDragon/cdn-life-insurer-alm repository (the project's primary framework from 2026-11-27):

  basis      Canadian business; General Account excl. par / seg fund (docs/METHODOLOGY.md s.3, 4a);
             UL policyholder funds, par and seg fund blocks outside it; IFRS 17 periods only (s.1).
  taxonomy   Level 1 / 2 / 3 asset taxonomy (docs/METHODOLOGY.md, Asset taxonomy); OSFI LF2 line mapping
             as scripts/build_osfi_assets.py; alternatives as confirmed 2026-11-15 (research/deck_v3_storyline.md).
  blocks     scripts/deck2/block_allocation.py, extended from the fiscal 2025 year-end to every filed date:
             LF2 pool by level 3, less UL policyholder funds (LF2 index-linked lines), less par
             (public par fact sheets where on hand, else the pool mix); the residual is the
             non-par / seg General Account. MFC and SLF: Canada follows the entity (global) mix.
             CLF: its disclosed Canada non-par mix (Lifeco MD&A).
  dates      by date, not quarter label; RBC Life and BMO Life have an October year-end.

Where the ALM repo is silent (insurers outside its peer universe; AMF filers' asset detail over time) the
earlier project method is used and labelled: inputs/ia_level3_quarterly.csv and inputs/annual_points.csv.

Usage (uv only):
    uv run analysis/portfolio_reallocation_alm/build.py --alm ../cdn-life-insurer-alm
Writes mix_by_date.csv, changes.csv, context.csv, regression_check.csv and report_data.json next to this script.
"""
import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- peers (ALM repo short IDs, fixed)
OSFI = {  # short id: (OSFI id, fiscal year-end, display name)
    "RBC": ("28395", "oct", "RBC Life"),
    "MFC": ("28397", "dec", "MFC"),
    "SLF": ("28429", "dec", "SLF"),
    "CLF": ("28386", "dec", "CLF"),
    "BMO": ("28344", "oct", "BMO Life"),
    "BLU": ("143611", "dec", "BLU"),
    "EMP": ("28375", "dec", "Empire Life"),
    "IVA": ("28414", "dec", "ivari"),
    "EQL": ("28377", "dec", "Equitable"),
    "COP": ("28368", "dec", "Co-operators Life"),
    "IOF": ("28432", "dec", "Foresters Life"),
    "WAW": ("28434", "dec", "Wawanesa Life"),
}
OUTSIDE_OSFI = {  # on the project's insurer list, outside the ALM study's peer universe; OSFI pool method, entity = Canada
    "CPL": ("28358", "dec", "Canadian Premier Life"),
    "PRI": ("28419", "dec", "Primerica Life"),
}
BIG3 = {"MFC", "SLF", "CLF"}
FOCUS = "RBC"
START = {"oct": "2024Q1", "dec": "2023Q4"}  # first IFRS 17 period used by the ALM study (METHODOLOGY s.1, L53)
# BMO Life's first IFRS 17 return (Jan 31, 2024) shows $372MM of index-linked (UL) assets against $1,204MM a quarter
# later with common shares unchanged, so the UL line looks incomplete as filed; its series starts Apr 30, 2024.
START_OVERRIDE = {"BMO": "2024Q2"}

# ---------------------------------------------------------------- taxonomy
L3 = ["Cash Equivalent", "Government Bonds", "Corporate Bonds", "Illiquid Term Loan", "Commercial Mortgages",
      "Common Shares", "Preferred Shares", "Real Estate Equity", "Others"]
L2 = {"Cash Equivalent": "Cash & Cash Equivalent", "Government Bonds": "Public Fixed Income",
      "Corporate Bonds": "Public Fixed Income", "Illiquid Term Loan": "Private Fixed Income",
      "Commercial Mortgages": "Private Fixed Income", "Common Shares": "Public Equity",
      "Preferred Shares": "Public Equity", "Real Estate Equity": "Real Estate Equity",
      "Others": "Others (unclassified)"}
L2_ORDER = ["Public Fixed Income", "Private Fixed Income", "Public Equity", "Real Estate Equity",
            "Others (unclassified)", "Cash & Cash Equivalent"]
L1 = {k: ("Externally Managed" if k == "Real Estate Equity" else "Unclassified" if k == "Others" else "Internally Managed")
      for k in L3}
# Alternatives (user 2026-11-15): private placements + direct lending mortgages + externally managed; "Others" counts (est).
ALTS = ["Illiquid Term Loan", "Commercial Mortgages", "Real Estate Equity", "Others"]
ALTS_VISIBLE = ["Illiquid Term Loan", "Commercial Mortgages", "Real Estate Equity"]

# OSFI LF2 investment schedule, balance-sheet value (column 40), mapped as scripts/build_osfi_assets.py INV_LINES.
LINES = {"P2101201040": "Cash Equivalent",
         "P2101204540": "Government Bonds", "P2101205040": "Government Bonds", "P2101205540": "Government Bonds",
         "P2101206540": "Government Bonds", "P2101214040": "Government Bonds", "P2101216040": "Government Bonds",
         "P2101221040": "Corporate Bonds", "P2101223040": "Corporate Bonds",
         "P2101241040": "Illiquid Term Loan", "P2101243040": "Illiquid Term Loan",
         "P2101250040": "Commercial Mortgages",
         "P2101252040": "Preferred Shares", "P2101256040": "Preferred Shares",
         "P2101265940": "Common Shares",
         "P2101281040": "Others", "P2101282040": "Others", "P2101266940": "Others",
         "P2108008966": "Real Estate Equity"}
DETAIL = {"P2101204540": "Federal", "P2101205040": "Federal", "P2101205540": "Provincial", "P2101206540": "Provincial",
          "P2101214040": "Municipal and public authority", "P2101216040": "Municipal and public authority"}
BELOW_IG = ["P2101205040", "P2101206540", "P2101216040", "P2101223040", "P2101243040"]
BONDS_TOTAL = "P2101247940"
POOL_TOTAL = "P2101288940"
LF1_INV_PROPERTY = "P2000211001"
UL = {"st": "P2101201070", "bonds": "P2101247970", "mort": "P2101250070", "pref": "P2101259970",
      "common": "P2101265970", "shares": "P2101267970", "other": "P2101282070", "total": "P2101288970"}
CLASS_SUFFIX = {"11": "FVTPL", "16": "FVOCI", "21": "FVTPL", "31": "FVTPL", "36": "Amortized cost"}
LICAT_TOTAL = "D1010010020"

# Par account mixes, fiscal 2025 year-end: values copied from scripts/deck2/block_allocation.py (ALM repo, BI-04).
PAR_MIX = {
    "EQL": ("Equitable par fund asset mix, Dec 31, 2025", "disclosed",
            {"Cash Equivalent": 52234, "Government Bonds": 247256, "Corporate Bonds": 665925, "Illiquid Term Loan": 388009,
             "Commercial Mortgages": 271758, "Preferred Shares": 151095, "Common Shares": 578384,
             "Others": 60830 + 2976 + 331503, "Real Estate Equity": 394371}),
    "SLF": ("Sun Life Participating Account fact sheet, Dec 31, 2025; public bonds split at the pool ratio (est)",
            "disclosed, part est",
            {"Cash Equivalent": 523.19, "_public_bonds": 9357.89, "Illiquid Term Loan": 3691.51,
             "Commercial Mortgages": 2399.55, "Common Shares": 4702.37, "Real Estate Equity": 3497.12, "Others": 937.40}),
    "EMP": ("Empire quarterly par account summary, Dec 31, 2025; bonds split at the pool ratio (est)",
            "disclosed, part est",
            {"Cash Equivalent": 8.2, "_public_bonds": 61.9, "Common Shares": 16.8, "Preferred Shares": 12.3, "Others": 0.8}),
    "RBC": ("RBC Growth Insurance par account guide (01/2021): target mix, not actual (est); about 1% of the book",
            "est (target)",
            {"Government Bonds": 5, "Corporate Bonds": 30, "Commercial Mortgages": 10, "Illiquid Term Loan": 5,
             "Common Shares": 50}),
}
EQL_TRAD_PAR_2025 = 3157470.0  # Traditional par account, Dec 31, 2025 (par fund fact sheet; LIMITATIONS L58)

# Canada Life: assets supporting insurance contract liabilities, non-participating, Canada column ($MM).
# 2025 and restated 2024: Great-West Lifeco 2025 annual report MD&A (p. 58). 2023 and 2024 as first reported
# (insurance and investment contract liabilities): Lifeco Q4 2024 MD&A. The basis changed in 2025, so the
# 2023 point is chain-linked to the restated basis (est) and the break is reported.
CLF_NONPAR = {
    "2025-12-31": dict(basis="restated", bonds=23072, mort=3533, stocks=3422, ip=573),
    "2024-12-31": dict(basis="restated", bonds=23553, mort=3727, stocks=3206, ip=742),
    "2024-12-31_old": dict(basis="as first reported", bonds=22522, mort=4085, stocks=2698, ip=728),
    "2023-12-31_old": dict(basis="as first reported", bonds=21408, mort=4244, stocks=2782, ip=644),
}
CLF_PUBLIC_STOCK_SHARE = 2618 / (2618 + 1330)  # public share of Canada non-par stocks, 2025 (block_allocation.py)


def per_date(fy, per):
    y, q = int(per[:4]), int(per[-1])
    if fy == "oct":
        return {1: f"{y}-01-31", 2: f"{y}-04-30", 3: f"{y}-07-31", 4: f"{y}-10-31"}[q]
    return {1: f"{y}-03-31", 2: f"{y}-06-30", 3: f"{y}-09-30", 4: f"{y}-12-31"}[q]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alm", required=True, help="path to a checkout of MooseDragon/cdn-life-insurer-alm")
    a = ap.parse_args()
    alm = Path(a.alm).resolve()
    P = alm / "data" / "processed"
    try:
        commit = subprocess.run(["git", "-C", str(alm), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception:
        commit = ""

    o = pd.read_parquet(P / "osfi_long.parquet", columns=["id", "per", "dpa", "value_num", "src", "label"])
    ids = {v[0] for v in {**OSFI, **OUTSIDE_OSFI}.values()}
    o = o[o.id.isin(ids)].drop_duplicates(["id", "per", "dpa"])
    V = o.set_index(["id", "per", "dpa"]).value_num

    def v(eid, per, code, default=np.nan):
        try:
            x = float(V.loc[(eid, per, code)])
            return default if np.isnan(x) else x
        except KeyError:
            return default

    summ = {}
    for f in sorted(P.glob("peer_summary_*.csv")):
        per = f.stem.split("_")[-1].upper()
        summ[per] = pd.read_csv(f).set_index("short_id")

    def periods(eid, fy, sid=None):
        first = START_OVERRIDE.get(sid, START[fy])
        return sorted(p for p in o[(o.id == eid) & (o.dpa == POOL_TOTAL)].per.unique() if p >= first)

    # ------------------------------------------------------------ pool by level 3, each filed date
    def pool(eid, per):
        gross = pd.Series(0.0, index=L3)
        for dpa, k in LINES.items():
            gross[k] += v(eid, per, dpa, 0.0)
        if gross["Real Estate Equity"] == 0:  # LF2 investment property schedule is annual; LF1 carries the same line quarterly
            gross["Real Estate Equity"] = v(eid, per, LF1_INV_PROPERTY, 0.0)
        ul = {k: v(eid, per, c) for k, c in UL.items()}
        return gross, ul

    def ul_by_l3(gross, ul):
        """UL policyholder funds by level 3 (LF2 index-linked lines), as scripts/build_bs_view.py / block_allocation.py."""
        u = pd.Series(0.0, index=L3)
        g = {k: (0.0 if np.isnan(x) else x) for k, x in ul.items()}
        u["Cash Equivalent"] += g["st"]
        gc = gross[["Government Bonds", "Corporate Bonds"]]
        if gc.sum() > 0:
            u[gc.index] += g["bonds"] * gc / gc.sum()
        u["Commercial Mortgages"] += g["mort"]
        shares = g["shares"] if g["shares"] else g["pref"] + g["common"]
        pref = min(g["pref"], gross["Preferred Shares"]) if g["pref"] <= gross["Preferred Shares"] else 0.0  # RBC-A5 reclass
        u["Preferred Shares"] += pref
        u["Common Shares"] += shares - pref
        u["Others"] += g["other"]
        resid = g["total"] - u.sum()
        if abs(resid) > 1:
            u["Others"] += resid
        return u

    rows, ctx, notes, checks = [], [], {}, []
    series = {}  # sid -> list of dict(date, per, shares(L3), ga_k, basis flags)

    def build_osfi(sid, eid, fy, with_blocks=True):
        out = []
        pers = periods(eid, fy, sid)
        raw = {p: pool(eid, p) for p in pers}
        # UL lines missing in a quarter that neighbours report: interpolate (est), else hold the last filed value
        has_ul = [p for p in pers if not np.isnan(raw[p][1]["total"])]
        ul_l3, ul_est = {}, {}
        for i, p in enumerate(pers):
            gross, ul = raw[p]
            if p in has_ul or not has_ul:
                ul_l3[p] = ul_by_l3(gross, ul)
                ul_est[p] = False
        for i, p in enumerate(pers):
            if p in ul_l3:
                continue
            prev = [q for q in pers[:i] if q in has_ul]
            nxt = [q for q in pers[i + 1:] if q in has_ul]
            if prev and nxt:
                ul_l3[p] = (ul_l3[prev[-1]] + ul_l3[nxt[0]]) / 2
            else:
                ul_l3[p] = ul_l3[(prev or nxt)[-1 if prev else 0]]
            ul_est[p] = True
        ref = "2025Q4"
        for p in pers:
            gross = raw[p][0]
            exul = (gross - ul_l3[p]).clip(lower=0)
            m_sh = exul / exul.sum()
            date = per_date(fy, p)
            rec = dict(sid=sid, per=p, date=date, pool_gross_k=float(gross.sum()), ul_k=float(ul_l3[p].sum()),
                       pool_exul_k=float(exul.sum()), ul_est=ul_est[p], pool_sh=m_sh)
            rec["below_ig_pct"] = 100 * sum(v(eid, p, c, 0.0) for c in BELOW_IG) / v(eid, p, BONDS_TOTAL) if v(eid, p, BONDS_TOTAL, 0) else np.nan
            rec["gov_detail"] = {}
            for dpa, name in DETAIL.items():
                rec["gov_detail"][name] = rec["gov_detail"].get(name, 0.0) + v(eid, p, dpa, 0.0)
            # accounting class, entity pool (incl. UL and par): LF2 class columns of the same lines
            ac = {"FVTPL": 0.0, "FVOCI": 0.0, "Amortized cost": 0.0}
            for dpa in LINES:
                if dpa == "P2108008966":
                    continue
                for suf, name in CLASS_SUFFIX.items():
                    ac[name] += v(eid, p, dpa[:-2] + suf, 0.0)
            t = sum(ac.values())
            rec["acct"] = {k: (100 * x / t if t else np.nan) for k, x in ac.items()}
            rec["lf1_cash_k"] = v(eid, p, "P2000201001", 0.0)
            rec["licat"] = v(eid, p, LICAT_TOTAL)
            checks.append(dict(sid=sid, per=p, check="LF2 leaf lines (ex investment property) = LF2 total investments",
                               computed=float(gross.sum() - gross["Real Estate Equity"]), reported=v(eid, p, POOL_TOTAL),
                               diff_pct=100 * (float(gross.sum() - gross["Real Estate Equity"]) / v(eid, p, POOL_TOTAL) - 1)))
            if not with_blocks:
                rec.update(ga_k=float(exul.sum()), par_k=0.0, shares=m_sh, blocks_est=False, par_basis="none",
                           basis="entity pool excl. UL policyholder funds (outside the ALM study; no block view)")
                out.append(rec)
                continue
            # block sizes: study views to fiscal 2025 year-end; later dates hold the year-end ratio to the pool (est)
            if p in summ and sid in summ[p].index and not np.isnan(summ[p].loc[sid, "genacct_k"]):
                s = summ[p].loc[sid]
                par = 0.0 if np.isnan(s.par_account_k) else float(s.par_account_k)
                segb = 0.0 if np.isnan(s.seg_backing_assets_k) else max(float(s.seg_backing_assets_k), 0.0)
                ga = float(s.genacct_k)
                blocks_est = False
                rec["_ratio"] = (par / exul.sum(), (ga + segb) / exul.sum(), ga)
            else:
                rpar, rga, _ = last_ratio[0]
                par, ga, segb, blocks_est = rpar * exul.sum(), rga * exul.sum(), 0.0, True
            if "_ratio" in rec:
                last_ratio[0] = rec.pop("_ratio")
            total = ga + segb + par
            ul_extra = pd.Series(0.0, index=L3)
            if sid in PAR_MIX:
                w = dict(PAR_MIX[sid][2])
                if "_public_bonds" in w:
                    pb = w.pop("_public_bonds")
                    g_, c_ = m_sh["Government Bonds"], m_sh["Corporate Bonds"]
                    w["Government Bonds"], w["Corporate Bonds"] = pb * g_ / (g_ + c_), pb * c_ / (g_ + c_)
                par_sh = pd.Series(w).reindex(L3).fillna(0)
                par_sh = par_sh / par_sh.sum()
                par_basis = PAR_MIX[sid][1] + ", fiscal 2025 mix held"
            else:
                par_sh, par_basis = m_sh, ("est (pool mix)" if par > 0 else "none")
            if sid == "EQL":  # LIMITATIONS L58: Participating UL sits in the OSFI par line; split out (est)
                trad = par * EQL_TRAD_PAR_2025 / float(summ[ref].loc["EQL", "par_account_k"])
                ul_x, par = par - trad, trad
                avail = (m_sh * total - par_sh * par).clip(lower=0)
                c = min(avail["Common Shares"], ul_x)
                ul_extra["Common Shares"] = c
                b = avail[["Government Bonds", "Corporate Bonds"]]
                ul_extra[b.index] += b / b.sum() * (ul_x - c)
            resid = (m_sh * total - par_sh * par - ul_extra)
            neg = float(resid[resid < 0].sum())
            resid = resid.clip(lower=0)
            sh = resid / resid.sum()
            rec.update(ga_k=ga + segb, par_k=float(par), shares=sh, blocks_est=blocks_est, par_basis=par_basis,
                       neg_clipped_k=neg, nonpar_share_of_pool=float((ga + segb) / total),
                       basis=("entity (global) mix applied to Canada (ALM user rule); includes exchange-rate moves"
                              if sid in ("MFC", "SLF") else "entity = Canada"))
            out.append(rec)
        return out

    last_ratio = [None]
    for sid, (eid, fy, name) in OSFI.items():
        last_ratio[0] = None
        series[sid] = build_osfi(sid, eid, fy)
    outside = {}
    for sid, (eid, fy, name) in OUTSIDE_OSFI.items():
        outside[sid] = build_osfi(sid, eid, fy, with_blocks=False)

    # ------------------------------------------------------------ CLF: disclosed Canada non-par mix (annual)
    def clf_shares(d, m_sh):
        b = m_sh[["Government Bonds", "Corporate Bonds", "Illiquid Term Loan"]]
        b = b / b.sum() * d["bonds"]
        pub = d["stocks"] * CLF_PUBLIC_STOCK_SHARE
        w = pd.Series({"Government Bonds": b["Government Bonds"], "Corporate Bonds": b["Corporate Bonds"],
                       "Illiquid Term Loan": b["Illiquid Term Loan"], "Commercial Mortgages": d["mort"],
                       "Common Shares": pub, "Others": d["stocks"] - pub, "Real Estate Equity": d["ip"]}).reindex(L3).fillna(0)
        return w / w.sum()

    clf_pool = {r["date"]: r for r in series["CLF"]}
    clf_entity = series["CLF"]
    s25 = clf_shares(CLF_NONPAR["2025-12-31"], clf_pool["2025-12-31"]["pool_sh"])
    s24 = clf_shares(CLF_NONPAR["2024-12-31"], clf_pool["2024-12-31"]["pool_sh"])
    s24o = clf_shares(CLF_NONPAR["2024-12-31_old"], clf_pool["2024-12-31"]["pool_sh"])
    s23o = clf_shares(CLF_NONPAR["2023-12-31_old"], clf_pool["2023-12-31"]["pool_sh"])
    s23 = (s24 - (s24o - s23o)).clip(lower=0)
    s23 = s23 / s23.sum()
    clf = []
    for date, sh, est in (("2023-12-31", s23, True), ("2024-12-31", s24, False), ("2025-12-31", s25, False)):
        r = dict(clf_pool[date])
        r.update(shares=sh, par_basis="disclosed Canada non-par mix (Lifeco MD&A)", chain_linked=est,
                 basis="disclosed Canada non-par mix; bonds split government / corporate / private at the entity ratio (est)"
                       + ("; Dec 31, 2023 chain-linked to the 2025 presentation (est)" if est else ""))
        clf.append(r)
    series["CLF"] = clf
    clf_break = {k: float(x) for k, x in (100 * (s24 - s24o)).items()}

    # ------------------------------------------------------------ regression check against the ALM repo (fiscal 2025 YE)
    ba = pd.read_csv(P / "deck2_block_allocation_2025fye.csv")
    ba["l3n"] = ba.l3.replace({"Other invested (unclassified)": "Others"})
    for sid in OSFI:
        mine = [r for r in series[sid] if r["per"] == "2025Q4"]
        if not mine:
            continue
        t = ba[ba.peer == sid].groupby("l3n").nonpar_seg_ga_k.sum()
        t = (100 * t / t.sum()).reindex(L3).fillna(0)
        d = (100 * mine[0]["shares"] - t).abs().max()
        checks.append(dict(sid=sid, per="2025Q4", check="non-par / seg GA level 3 shares vs ALM deck2_block_allocation_2025fye.csv (max abs diff, pp)",
                           computed=float(d), reported=0.0, diff_pct=float(d)))

    # ------------------------------------------------------------ tidy outputs
    def add_rows(sid, name, recs, scope):
        for r in recs:
            for k in L3:
                rows.append(dict(short_id=sid, insurer=name, scope=scope, period_end_date=r["date"], fiscal_period=r["per"],
                                 level1=L1[k], level2=L2[k], level3=k, share_pct=round(100 * float(r["shares"][k]), 4),
                                 amount_mm=round(float(r["shares"][k]) * r["ga_k"] / 1e3, 1),
                                 block_total_mm=round(r["ga_k"] / 1e3, 1),
                                 pool_share_pct=round(100 * float(r["pool_sh"][k]), 4),
                                 estimate="est" if (r.get("blocks_est") or r.get("ul_est") or r.get("chain_linked") or sid in BIG3 or r.get("par_k", 0) > 0) else "",
                                 par_basis=r.get("par_basis", ""), basis=r.get("basis", "")))

    for sid, (eid, fy, name) in OSFI.items():
        add_rows(sid, name, series[sid], "Non-par / seg General Account (ALM block method)")
    for sid, (eid, fy, name) in OUTSIDE_OSFI.items():
        add_rows(sid, name, outside[sid], "Entity pool excl. UL policyholder funds (outside the ALM study)")
    mix = pd.DataFrame(rows)
    mix.to_csv(HERE / "mix_by_date.csv", index=False)

    def l2_of(sh):
        s = pd.Series({k: 0.0 for k in L2_ORDER})
        for k in L3:
            s[L2[k]] += float(sh[k])
        return s

    def change(recs):
        a, b = recs[0], recs[-1]
        d3 = 100 * (b["shares"] - a["shares"])
        d2 = 100 * (l2_of(b["shares"]) - l2_of(a["shares"]))
        return a, b, d3, d2

    ch = []
    for sid, (eid, fy, name) in OSFI.items():
        a, b, d3, d2 = change(series[sid])
        for k in L3:
            ch.append(dict(short_id=sid, insurer=name, first_date=a["date"], last_date=b["date"], level2=L2[k], level3=k,
                           first_share_pct=round(100 * float(a["shares"][k]), 2), last_share_pct=round(100 * float(b["shares"][k]), 2),
                           change_pp=round(float(d3[k]), 2),
                           first_mm=round(float(a["shares"][k]) * a["ga_k"] / 1e3, 1), last_mm=round(float(b["shares"][k]) * b["ga_k"] / 1e3, 1),
                           reallocated_mm=round(float(d3[k]) / 100 * b["ga_k"] / 1e3, 1)))
    pd.DataFrame(ch).to_csv(HERE / "changes.csv", index=False)
    pd.DataFrame(checks).to_csv(HERE / "regression_check.csv", index=False)

    # ------------------------------------------------------------ liability, funding and capital context (ALM study views)
    lines = ["Individual insurance", "Individual annuity", "Group insurance", "Group annuity"]
    icl = {}
    for y in (2023, 2024, 2025):
        f = P / f"icl_by_line_{y}q4.csv"
        if f.exists():
            d = pd.read_csv(f)
            for sid in d.entity.unique():
                x = d[d.entity == sid].set_index("product_line")
                icl.setdefault(sid, {})[str(y)] = dict(
                    date=str(x.period_end_date.iloc[0]),
                    lines={ln: (float(x.loc[ln, "net_k"]) if ln in x.index else 0.0) for ln in lines},
                    par=float(x.loc["Participating", "net_k"]) if "Participating" in x.index else 0.0)
    fund = {}
    for per, s in summ.items():
        for sid in s.index:
            r = s.loc[sid]
            fy = OSFI[sid][1] if sid in OSFI else "dec"
            fund.setdefault(sid, []).append(dict(
                per=per, date=per_date(fy, per), genacct_k=r.genacct_k, repos_k=r.repos_k, financing_pct=r.financing_pct,
                buffer_pct=r.buffer_pct, capital_ratio_pct=r.capital_ratio_pct, csm_abl_k=r.csm_abl_k, surplus_k=r.surplus_k,
                par_pct=r.par_pct))
            ctx.append(dict(short_id=sid, period_end_date=per_date(fy, per), fiscal_period=per, genacct_mm=r.genacct_k / 1e3,
                            repos_mm=r.repos_k / 1e3, financing_pct_of_genacct=r.financing_pct, buffer_pct=r.buffer_pct,
                            capital_ratio_pct=r.capital_ratio_pct, abl_csm_mm=r.csm_abl_k / 1e3, surplus_mm=r.surplus_k / 1e3,
                            par_share_pct=r.par_pct))
    pd.DataFrame(ctx).sort_values(["short_id", "fiscal_period"]).to_csv(HERE / "context.csv", index=False)

    # ------------------------------------------------------------ peers outside OSFI data (earlier method, labelled)
    ia = pd.read_csv(HERE / "inputs" / "ia_level3_quarterly.csv")
    ia_map = {"Government Bonds": "Government Bonds", "Corporate Bonds": "Corporate Bonds", "Illiquid Term Loans": "Illiquid Term Loan",
              "Commercial Mortgages": "Commercial Mortgages", "Private Liquid Loans": "Private Liquid Loans",
              "Policy & Other Loans": "Consumer Loans", "Common Shares": "Common Shares", "Cash": "Cash Equivalent",
              "Real Estate Equity": "Real Estate Equity", "Other Private Equity": "Other Private Equity",
              "Other / Unclassified": "Others"}
    ia["l3"] = ia.level3.map(ia_map)
    iag = []
    for per, g in ia.groupby("period"):
        tot = g.amount_cad_mm.sum()
        iag.append(dict(per=per, date=per_date("dec", per), total_mm=float(tot),
                        shares={k: float(x) / tot for k, x in g.groupby("l3").amount_cad_mm.sum().items()}))
    ann = pd.read_csv(HERE / "inputs" / "annual_points.csv")
    annual = {}
    for (cid, yr), g in ann.groupby(["company_id", "year"]):
        tot = g.amount_cad_mm.sum()
        annual.setdefault(cid, []).append(dict(date=f"{yr}-12-31", total_mm=float(tot),
                                               shares={r["class"]: float(r.amount_cad_mm) / tot for _, r in g.iterrows()}))

    # ------------------------------------------------------------ JSON for the report
    def clean(x):
        if isinstance(x, dict):
            return {k: clean(val) for k, val in x.items()}
        if isinstance(x, (list, tuple)):
            return [clean(val) for val in x]
        if isinstance(x, pd.Series):
            return {k: clean(val) for k, val in x.items()}
        if isinstance(x, (float, np.floating)):
            return None if not np.isfinite(x) else round(float(x), 5)
        if isinstance(x, (np.integer,)):
            return int(x)
        if isinstance(x, np.bool_):
            return bool(x)
        return x

    out = dict(
        meta=dict(alm_commit=commit, focus=FOCUS, l3=L3, l2=L2, l2_order=L2_ORDER, l1=L1, alts=ALTS, alts_visible=ALTS_VISIBLE,
                  names={**{k: val[2] for k, val in OSFI.items()}, **{k: val[2] for k, val in OUTSIDE_OSFI.items()},
                         "IAG": "iA", "BEN": "Beneva", "DFS": "Desjardins"},
                  fy={k: val[1] for k, val in {**OSFI, **OUTSIDE_OSFI}.items()},
                  par_sources={k: val[0] for k, val in PAR_MIX.items()}, clf_break_pp=clf_break,
                  clf_inputs=CLF_NONPAR),
        series=series, clf_entity=clf_entity, outside=outside, icl=icl, fund=fund, iag=iag, annual=annual,
        checks=checks)
    (HERE / "report_data.json").write_text(json.dumps(clean(out), indent=1))
    print("wrote", len(mix), "mix rows;", len(ch), "change rows")
    ck = pd.DataFrame(checks)
    print(ck[ck.check.str.startswith("non-par")][["sid", "computed"]].round(2).to_string(index=False))
    t = ck[ck.check.str.startswith("LF2 leaf")]
    print("LF2 leaf tie-out: max abs diff %", t.diff_pct.abs().max().round(3), "rows", len(t))


if __name__ == "__main__":
    main()
