#!/usr/bin/env python3
"""Peer investment risk benchmark, rebuilt on the cdn-life-insurer-alm repo.

    uv run --project <alm-repo> python analysis/investment_risk_alm/build.py <alm-repo>

Reads the ALM repo's committed outputs (nothing is re-derived that the repo already
publishes) and writes the dashboard datasets to analysis/investment_risk_alm/dashboard/.
The ALM repo's rules apply throughout: Canadian business, net of reinsurance, General
Account excluding par, segregated funds and UL policyholder funds; RBC Life first; periods
by date; estimates marked est; sensitivities one risk at a time, never combined, each
insurer's own shock kept.

Three small hand-entered files sit beside this script for what the repo does not hold:
fallback_sensitivities.csv (iA, Beneva, Desjardins, as disclosed), sensitivity_denominators.csv
(group invested assets for group-level sensitivities) and outside_study.csv (project-list
insurers outside the repo's peer set).
"""
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "dashboard")
R = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.abspath(os.path.join(HERE, "..", "..", "..", "cdn-life-insurer-alm"))

NAMES = {"RBC": "RBC Life", "BMO": "BMO Life", "MFC": "Manulife", "SLF": "Sun Life", "CLF": "Canada Life",
         "EMP": "Empire Life", "IVA": "ivari", "EQL": "Equitable Life", "COP": "Co-operators Life",
         "IOF": "Foresters Life", "WAW": "Wawanesa Life", "BLU": "Blumont", "IAG": "iA Financial Group",
         "BEN": "Beneva", "DFS": "Desjardins Insurance"}
OSFI = ["RBC", "BMO", "MFC", "SLF", "CLF", "EMP", "IVA", "EQL", "COP", "IOF", "WAW", "BLU"]
BIG3 = ["MFC", "SLF", "CLF"]
ALL_CANADA = [p for p in OSFI if p not in BIG3]          # nine filers whose legal entity is all Canada
AMF = ["IAG", "BEN", "DFS"]
ORDER = OSFI + AMF
OSFI_IDS = {"RBC": "28395", "BMO": "28350", "MFC": "28397", "SLF": "28429", "CLF": "28386", "EMP": "28375",
            "IVA": "28414", "EQL": "28377", "COP": "28368", "IOF": "28432", "WAW": "28434", "BLU": "143611"}
FLOOR = 125.0                                             # the ALM study's capital floor (assumed, not a filed target)


def rj(*p):
    with open(os.path.join(R, *p), encoding="utf-8") as f:
        return json.load(f)


def rc(*p):
    return pd.read_csv(os.path.join(R, *p))


def num(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)


def rnd(v, n=2):
    v = num(v)
    return None if v is None else round(v, n)


def write(name, rows, cols=None):
    df = pd.DataFrame(rows)
    if cols:
        df = df[cols]
    df.to_csv(os.path.join(OUT, name), index=False)
    print(f"{name}: {len(df)} rows")
    return df


def main():
    os.makedirs(OUT, exist_ok=True)
    commit = subprocess.run(["git", "-C", R, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()

    ps = rc("data", "processed", "peer_summary_2025q4.csv").set_index("short_id")
    ps24 = rc("data", "processed", "peer_summary_2024q4.csv").set_index("short_id")
    lic = rc("research", "licat_required_capital_2025q4.csv").set_index("short_id")
    review = {p["id"]: p for p in rj("deck", "peer_risk_review_2025q4.json")["peers"]}
    v2 = rj("deck", "alm_peer_deck_v2.json")
    ld = rj("deck", "licat_deck_data.json")
    d3 = rj("deck", "deck3_data.json")
    alloc = rc("data", "processed", "deck2_block_allocation_2025fye.csv")
    osfi = pd.read_parquet(os.path.join(R, "data", "processed", "osfi_long.parquet"))
    osfi["id"] = osfi.id.astype(str)
    universe = rc("data", "processed", "universe_2025q4.csv")

    # --- below-investment-grade bonds, OSFI LF2 (the repo holds the codes; the ratio is computed here) ---
    big_codes = ["P2101205040", "P2101206540", "P2101216040", "P2101223040", "P2101243040"]
    below_ig = {}
    for p, i in OSFI_IDS.items():
        x = osfi[(osfi.id == i) & (osfi.per == "2025Q4")]
        bonds = x.loc[x.dpa == "P2101247940", "value_num"].sum()
        below_ig[p] = 100 * x.loc[x.dpa.isin(big_codes), "value_num"].sum() / bonds if bonds else None

    # --- alternatives including Others, the deck v3 definition, on the non-par General Account ---
    alt_l3 = ["Commercial Mortgages", "Illiquid Term Loan", "Real Estate Equity", "Other invested (unclassified)"]
    tot = alloc.groupby("peer").nonpar_seg_ga_k.sum()
    alts = (alloc[alloc.l3.isin(alt_l3)].groupby("peer").nonpar_seg_ga_k.sum() / tot * 100).to_dict()
    for p, v in d3["alts_incl_others"].items():           # must tie to the repo's own figures where it publishes them
        assert abs(alts[p] - v) < 0.6, (p, alts[p], v)
        alts[p] = v

    # --- landscape: one row per insurer ---
    land = []
    for p in ORDER:
        s = ps.loc[p]
        r = {"id": p, "company": NAMES[p], "tier": s.tier, "regulator": s.regulator,
             "scope": "Entity includes foreign business" if p in BIG3 else ("AMF filer" if p in AMF else "All-Canada filer"),
             "period": "Oct 31, 2025" if p in ("RBC", "BMO") else "Dec 31, 2025",
             "genacct_bn": rnd(s.genacct_k / 1e6, 2), "capital_ratio_pct": rnd(s.capital_ratio_pct, 1),
             "capital_basis": "LICAT total" if p in OSFI else ("CARLI solvency ratio (AMF)" if num(s.capital_ratio_pct) else "Not public"),
             "buffer_pct": rnd(s.buffer_pct, 1),
             "repos_ga": rnd(100 * s.repos_k / s.genacct_k, 1) if num(s.genacct_k) else None,
             "repos_ga_fy24": rnd(100 * ps24.loc[p].repos_k / ps24.loc[p].genacct_k, 1) if num(ps24.loc[p].genacct_k) else None,
             "repos_mm": rnd(s.repos_k / 1e3, 0),
             "financing_pct": rnd(s.financing_pct, 1), "reins_pct": rnd(s.reinsurance_pct, 1)}
        if p in OSFI:
            c, rv, ul = lic.loc[p], review[p], v2["ul"][p]
            earn = v2["earn"][p]["2025"]
            acct = v2["acct"][p]["2025-10-31" if p in ("RBC", "BMO") else "2025-12-31"]
            r.update({
                "invested_bn": rnd(rv.get("invested_bn"), 3), "licat_pct": rnd(c.total_ratio, 1), "core_pct": rnd(c.core_ratio, 1),
                "pts_above_floor": rnd(c.total_ratio - FLOOR, 1), "free125_mm": rnd(c.free_capital_at_125 / 1e3, 0),
                "bsb_mm": rnd(c.bsb / 1e3, 0),
                "ins_share": rnd(rv.get("ins_share"), 1), "market_cap_inv": rnd(rv.get("mkt_inv"), 2), "credit_cap_inv": rnd(rv.get("cr_inv"), 2),
                "market_cap_ga": rnd(rv.get("mkt_ga"), 2) if p in ALL_CANADA else None,
                "credit_cap_ga": rnd(rv.get("cr_ga"), 2) if p in ALL_CANADA else None,
                "nir_cm": rnd(c.nir_to_credit_market_risk_pct, 1), "ni_bsb": rnd(c.net_income_to_avg_bsb_pct, 1),
                "ul_bn": rnd(ul.get("ul_bn"), 2), "eq_gross": rnd(ul.get("eq_gross"), 1), "eq_ex_ul": rnd(ul.get("eq_ex"), 1),
                "eq_est": "est" if ul.get("est") else "",
                "alts_incl_others": rnd(alts[p], 1), "private_credit": rnd(rv.get("private_credit"), 1),
                "below_ig_bonds": rnd(below_ig[p], 2), "ecl_bps": rnd(earn.get("ecl_bps"), 1) if (num(earn.get("ecl_bps")) or 0) >= 0 else None,
                "energy": rnd(rv.get("energy"), 1), "utilities": rnd(rv.get("utilities"), 1), "energy_util": rnd(rv.get("energy_util"), 1),
                "sector_other": rnd(v2["sectors"][p].get("Other"), 1),
                "liquid_ex_ul": rnd(ul.get("liquid_ex_ul"), 1), "liquid_unenc": rnd(ul.get("liquid_unenc"), 1),
                "reins_affil_pct": rnd(100 * earn["reins_affil_lf3"] / earn["reins_total_lf3"], 0) if earn.get("reins_total_lf3") else None,
                "prt_share": rnd(rv.get("prt_share"), 1),
                "fvtpl": rnd(acct["fvtpl"], 1), "fvoci": rnd(acct["fvoci"], 1), "amortised_cost": rnd(acct["ac"], 1),
            })
        land.append(r)
    land_df = write("landscape.csv", land)
    L = land_df.set_index("id")

    # --- RBC Life against the median of the other peers, on the ALM repo's two peer sets ---
    metrics = [
        # key, label, unit, decimals, group, set, hint
        ("licat_pct", "LICAT total ratio", "%", 1, "Capital", "ac", "higher is stronger"),
        ("buffer_pct", "Buffer, % of General Account", "%", 1, "Capital", "osfi", "higher is stronger"),
        ("market_cap_ga", "Market risk capital, % of own General Account", "%", 2, "Market", "ac", ""),
        ("eq_ex_ul", "Equity-type assets excl. UL pass-through, % of invested", "%", 1, "Market", "osfi", ""),
        ("alts_incl_others", "Alternatives incl. Others, % of non-par General Account", "%", 1, "Market", "osfi", ""),
        ("credit_cap_ga", "Credit risk capital, % of own General Account", "%", 2, "Credit", "ac", ""),
        ("private_credit", "Private credit and mortgages, % of invested", "%", 1, "Credit", "osfi", ""),
        ("below_ig_bonds", "Below investment grade, % of bonds", "%", 2, "Credit", "osfi", ""),
        ("energy_util", "Energy + utilities, % of corporate bonds", "%", 1, "Credit", "osfi", ""),
        ("liquid_unenc", "Liquid assets after repo collateral, % of invested", "%", 1, "Liquidity", "osfi", "higher is more liquid"),
        ("repos_ga", "Repos, % of General Account", "%", 1, "Liquidity", "osfi", ""),
        ("nir_cm", "Net investment result, % of credit + market capital", "%", 1, "Return", "ac", ""),
        # shown in tables and bar charts only
        ("ins_share", "Insurance risk, % of credit + market + insurance capital", "%", 1, "Capital", "ac", ""),
        ("ni_bsb", "Net income, % of required capital", "%", 1, "Return", "ac", ""),
        ("market_cap_inv", "Market risk capital, % of entity invested assets", "%", 2, "Market", "osfi", ""),
        ("credit_cap_inv", "Credit risk capital, % of entity invested assets", "%", 2, "Credit", "osfi", ""),
        ("eq_gross", "Equity-type assets incl. UL pass-through, % of invested", "%", 1, "Market", "osfi", ""),
        ("liquid_ex_ul", "Liquid assets before repo collateral, % of invested", "%", 1, "Liquidity", "osfi", ""),
        ("ecl_bps", "Expected credit loss allowance, bps of invested", " bps", 1, "Credit", "osfi", ""),
        ("financing_pct", "Repos and other financing, % of General Account", "%", 1, "Liquidity", "osfi", ""),
        ("free125_mm", "Free capital above the 125% floor, C$MM", "", 0, "Capital", "ac", ""),
        ("pts_above_floor", "LICAT points above the 125% floor", " pts", 1, "Capital", "ac", ""),
        ("energy", "Energy, % of corporate bonds", "%", 1, "Credit", "osfi", ""),
        ("fvoci", "FVOCI, % of invested assets", "%", 1, "Market", "osfi", ""),
        ("reins_pct", "Reinsurance assets, % of General Account", "%", 1, "Credit", "osfi", ""),
    ]
    stats = []
    for i, (key, label, unit, dec, group, st, hint) in enumerate(metrics):
        others = [p for p in (ALL_CANADA if st == "ac" else OSFI) if p != "RBC"]
        vals = [num(L.loc[p, key]) for p in others]
        vals = [v for v in vals if v is not None]
        rbc = num(L.loc["RBC", key])
        field = vals + ([rbc] if rbc is not None else [])
        stats.append({"metric": key, "label": label, "unit": unit, "decimals": dec, "group": group, "hint": hint,
                      "peer_set": "the eight other all-Canada filers" if st == "ac" else "the eleven other OSFI peers",
                      "rbc": rbc, "median": rnd(float(np.median(vals)), dec) if vals else None,
                      "n_others": len(vals), "n": len(field),
                      "rank_from_high": (1 + sum(v > rbc for v in vals)) if rbc is not None else None,
                      "rank_from_low": (1 + sum(v < rbc for v in vals)) if rbc is not None else None,
                      "strip": 1 if i < 12 else 0, "order": i})
    write("peer_stats.csv", stats)
    S = {s["metric"]: s for s in stats}
    assert abs(S["licat_pct"]["median"] - ld["medians"]["ratio"]) < 0.06            # ties to the repo's LICAT deck
    assert abs(S["ni_bsb"]["median"] - ld["medians"]["ni_bsb"]) < 0.06

    # --- LICAT required capital by category (share of the gross requirement before the diversification credit) ---
    comp = [("credit", "Credit", "credit_risk"), ("market", "Market", "market_risk"), ("insurance", "Insurance", "insurance_risk"),
            ("seg", "Segregated fund guarantees", "seg_guarantee_risk"), ("operational", "Operational", "operational_risk"),
            ("par", "Participating and other", "other_in_F_par_etc")]
    mix = []
    for p in OSFI:
        for k, label, col in comp:
            mix.append({"id": p, "company": NAMES[p], "component": label, "share_pct": rnd(ld["cur"][p]["mix6"][k], 1),
                        "amount_mm": rnd(max(num(lic.loc[p, col]) or 0, 0) / 1e3, 0),
                        "scope": L.loc[p, "scope"]})
    write("licat_mix.csv", mix)

    # --- non-par General Account asset mix, the repo's block allocation at Level 3 ---
    am = []
    for p in OSFI:
        a = alloc[alloc.peer == p]
        t = a.nonpar_seg_ga_k.sum()
        for _, x in a.iterrows():
            am.append({"id": p, "company": NAMES[p], "l1": x.l1, "l2": x.l2, "l3": x.l3,
                       "nonpar_mm": rnd(x.nonpar_seg_ga_k / 1e3, 0), "share_pct": rnd(100 * x.nonpar_seg_ga_k / t, 1),
                       "basis": v2["alloc"][p]["basis_note"]})
    write("asset_mix.csv", am)

    # --- sensitivities, one risk at a time, each insurer's own shock ---
    den = pd.read_csv(os.path.join(HERE, "sensitivity_denominators.csv")).set_index("id")
    risk_label = {"rates": "Interest rates", "spreads": "Credit spreads", "equity": "Public equity", "real_estate_alts": "Real estate and alternatives"}
    standard = {"rates": "−50 bps", "spreads": "+50 bps", "equity": "−10%", "real_estate_alts": "−10%"}

    def shock_label(risk, shock):
        t = str(shock).split(" ")
        return (t[0] + (" bps" if risk in ("rates", "spreads") else "")).replace("-", "−")

    def denom(p, basis):
        if p == "RBC":
            return num(L.loc["RBC", "invested_bn"]) * 1e3, "RBC Life invested assets (est: the numerator is the RBC Insurance group)"
        if basis.startswith("group") and p in den.index:
            return float(den.loc[p, "invested_mm"]), den.loc[p, "label"]
        if p in OSFI and not basis.startswith("group"):
            return num(L.loc[p, "invested_bn"]) * 1e3, "Legal-entity invested assets (OSFI)"
        return None, ""

    licat_bounds = {}
    for x in ld["sens_pub"]:
        if x.get("bound"):
            licat_bounds[(x["peer"], x["risk"], x["shock"].split(" ")[0])] = "0 to +1" if x["bound_sign"] > 0 else "0 to −1"
    sens = []
    for x in v2["sens_summary"]:
        p, risk = x["peer"], x["risk"]
        basis = "RBC Insurance group, used as a proxy for RBC Life" if p == "RBC" else ("Group consolidated" if x["basis"].startswith("group") else "Legal entity")
        d, dl = denom(p, x["basis"])
        ni, csm, pts = num(x.get("net_income")), num(x.get("csm")), num(x.get("licat_pts"))
        key = (p, risk, str(x["shock"]).split(" ")[0])
        text = licat_bounds.get(key, "" if pts is None else f"{pts:+g}".replace("-", "−"))
        note = x["applied_to"].split(";")[0][:200]
        if ni is None and csm is None:
            note = "Publishes changes in liabilities and assets only, not net income. " + note
        sens.append({"id": p, "company": NAMES[p], "risk": risk_label[risk], "shock": shock_label(risk, x["shock"]),
                     "standard_shock": 1 if shock_label(risk, x["shock"]) == standard[risk] else 0,
                     "net_income_mm": rnd(ni, 1), "csm_mm": rnd(csm, 1), "oci_mm": rnd(x.get("oci"), 1),
                     "capital_pts": rnd(pts, 1), "capital_text": text,
                     "capital_basis": "" if not text else ("LICAT total" + (" (bound, as published)" if key in licat_bounds else "")),
                     "basis": basis, "denominator_mm": rnd(d, 0), "denominator": dl,
                     "ni_bps": rnd(1e4 * ni / d, 1) if (ni is not None and d) else None,
                     "csm_bps": rnd(1e4 * csm / d, 1) if (csm is not None and d) else None,
                     "source": "ALM repo, deck2_sensitivities.csv (insurer's fiscal 2025 report)", "definition": note})
    fb = pd.read_csv(os.path.join(HERE, "fallback_sensitivities.csv"))
    for _, x in fb.iterrows():
        d, dl = denom(x.id, "group")
        ni = num(x.net_income_mm)
        sens.append({"id": x.id, "company": NAMES[x.id], "risk": risk_label[x.risk], "shock": shock_label(x.risk, x.shock),
                     "standard_shock": 1 if shock_label(x.risk, x.shock) == standard[x.risk] else 0,
                     "net_income_mm": rnd(ni, 1), "csm_mm": rnd(x.csm_mm, 1), "oci_mm": rnd(x.oci_mm, 1),
                     "capital_pts": rnd(x.capital_pts, 1), "capital_text": x.capital_text if isinstance(x.capital_text, str) else "",
                     "capital_basis": "CARLI solvency ratio (AMF)" if isinstance(x.capital_text, str) else "",
                     "basis": x.basis[0].upper() + x.basis[1:], "denominator_mm": rnd(d, 0), "denominator": dl,
                     "ni_bps": rnd(1e4 * ni / d, 1) if (ni is not None and d) else None, "csm_bps": None,
                     "source": x.source + " (not in the ALM repo; carried from the earlier benchmark)", "definition": x.definition})
    rk = list(risk_label.values())
    sens.sort(key=lambda r: (rk.index(r["risk"]), ORDER.index(r["id"])))
    write("sensitivities.csv", sens)

    # --- corporate bond sectors, OSFI LF3 (public and private combined) ---
    sec_name = {"Energy": "Energy", "Utilities": "Utilities", "Financial": "Financials", "Industrial": "Industrials",
                "Communications/Telecommunications)": "Communications", "Consumer Non-Cyclical/(Staples)": "Consumer staples",
                "Consumer Cyclical/(Discretionary)": "Consumer discretionary", "Diversified/(Health Care)": "Health care and diversified",
                "Basic Materials/(Materials)": "Materials", "Technology/(Information Technology)": "Technology", "Other": "Other"}
    secs = []
    for p in OSFI:
        for raw, clean in sec_name.items():
            v = v2["sectors"][p].get(raw)
            secs.append({"id": p, "company": NAMES[p], "sector": clean, "pct": rnd(v, 1)})
    write("sectors.csv", secs)

    # --- encumbrance: repos (OSFI and annual reports) and pledged assets where a note is published ---
    purpose = {"repos": "Repos", "securities_lending": "Securities lending", "derivatives": "Derivatives collateral",
               "reinsurance": "Reinsurance", "regulatory_trust": "Regulatory and trust", "other": "Other"}
    pledged_basis = {"MFC": "Manulife consolidated", "SLF": "Sun Life group", "CLF": "Great-West Lifeco group", "EMP": "Legal entity",
                     "EQL": "Legal entity", "IVA": "Legal entity", "WAW": "Legal entity"}
    enc = [{"id": "RBC", "company": NAMES["RBC"], "purpose": "Repos", "value_mm": rnd(ps.loc["RBC"].repos_k / 1e3, 0),
            "basis": "Legal entity, OSFI LF3; no pledged-asset note is published"}]
    for p in OSFI:
        for k, label in purpose.items():
            v = v2["pledged_summary"].get(p, {}).get(k)
            if v:
                enc.append({"id": p, "company": NAMES[p], "purpose": label, "value_mm": rnd(v, 0), "basis": pledged_basis[p]})
    for p in ("IAG", "BEN"):
        enc.append({"id": p, "company": NAMES[p], "purpose": "Repos", "value_mm": rnd(ps.loc[p].repos_k / 1e3, 0),
                    "basis": "Group consolidated, annual report"})
    write("encumbrance.csv", enc)

    # --- LICAT trend: RBC Life against the other all-Canada filers ---
    trend = [{"per": x["per"], "rbc_date": x["rbc_date"], "peer_date": x["peer_date"], "rbc": x["rbc_total"],
              "median": rnd(x["med_total"], 1), "low": x["min_total"], "high": x["max_total"], "n_peers": x["n_total"]}
             for x in ld["series"]]
    write("licat_trend.csv", trend)

    path = [{"date": k, "licat_pct": rnd(x["ratio"], 1), "core_pct": rnd(x["core"], 1), "required_capital_mm": rnd(x["bsb"], 0),
             "free125_mm": rnd(x["free125"], 0), "parent_injection_mm": x["injection"], "dividends_mm": x["dividends"],
             "net_income_mm": rnd(x["ni"], 0), "note": "Nine months" if "note" in x else "Fiscal year"}
            for k, x in ld["capital_path"].items()]
    write("rbc_capital_path.csv", path)

    rot = d3["rbc_rotation_fy26"]
    write("rbc_rotation.csv", [
        {"asset": "Government bonds", "change_mm": rnd(rot["gov"], 0)},
        {"asset": "Public investment-grade corporates", "change_mm": rnd(rot["pub_ig"], 0)},
        {"asset": "Private investment-grade corporates", "change_mm": rnd(rot["priv_ig"], 0)},
        {"asset": "Mortgages", "change_mm": rnd(rot["mort"], 0)}])

    # --- scalar facts the page's sentences draw ---
    rbc, rbc24 = ps.loc["RBC"], ps24.loc["RBC"]
    nil_repos = sum(1 for p in OSFI if p != "RBC" and not num(L.loc[p, "repos_ga"]))
    facts = {
        "floor_pct": FLOOR, "rbc_licat": L.loc["RBC", "licat_pct"], "rbc_pts_above_floor": L.loc["RBC", "pts_above_floor"],
        "rbc_free125_mm": L.loc["RBC", "free125_mm"], "rbc_genacct_bn": L.loc["RBC", "genacct_bn"],
        "rbc_repos_mm": rnd(rbc.repos_k / 1e3, 0), "rbc_repos_mm_fy24": rnd(rbc24.repos_k / 1e3, 0),
        "rbc_repos_ga": L.loc["RBC", "repos_ga"], "rbc_repos_ga_fy24": L.loc["RBC", "repos_ga_fy24"],
        "slf_repos_ga": L.loc["SLF", "repos_ga"], "osfi_peers_nil_repos": nil_repos,
        "rbc_liquid_ex_ul": L.loc["RBC", "liquid_ex_ul"], "rbc_liquid_unenc": L.loc["RBC", "liquid_unenc"],
        "rbc_eq_gross": L.loc["RBC", "eq_gross"], "rbc_eq_ex_ul": L.loc["RBC", "eq_ex_ul"], "rbc_ul_bn": L.loc["RBC", "ul_bn"],
        "rbc_energy": L.loc["RBC", "energy"], "rbc_sector_other": float(int(L.loc["RBC", "sector_other"] + 0.5)),
        "rbc_gov_bond_fall_mm": rnd(-rot["gov"], 0),
        "rbc_market_cap_ga": L.loc["RBC", "market_cap_ga"], "rbc_market_cap_inv": L.loc["RBC", "market_cap_inv"],
        "rbc_injection_fy24_mm": ld["capital_path"]["Oct 31, 2024"]["injection"],
        "rbc_injection_fy25_mm": ld["capital_path"]["Oct 31, 2025"]["injection"],
        "rbc_licat_jul26": rnd(ld["capital_path"]["Jul 31, 2026"]["ratio"], 1),
        "rbc_other_liab_oct25_mm": rnd(rot["other_liab_oct25"], 0), "rbc_other_liab_jul26_mm": rnd(rot["other_liab_jul26"], 0),
        "rbc_alts": L.loc["RBC", "alts_incl_others"], "rbc_fvtpl": L.loc["RBC", "fvtpl"], "rbc_fvoci": L.loc["RBC", "fvoci"],
        "rbc_reins_affil_pct": L.loc["RBC", "reins_affil_pct"], "bmo_licat": L.loc["BMO", "licat_pct"],
        "rbc_ni_bsb": L.loc["RBC", "ni_bsb"], "bmo_ni_bsb_ex_gain": rnd(d3["bmo_ex_gain"]["ni_bsb"], 1),
        "n_all_canada": len(ALL_CANADA), "n_osfi": len(OSFI), "n_peers": len(ORDER),
    }
    write("facts.csv", [{"key": k, "value": (None if v is None else float(v))} for k, v in facts.items()])

    # --- what changed against the earlier benchmark (earlier figures are the earlier dashboard's own) ---
    f = facts
    changes = [
        {"topic": "Equity, real estate and private equity", "earlier": "14.7% of the portfolio",
         "now": f"{f['rbc_eq_ex_ul']:.1f}% of invested assets",
         "why": f"The earlier figure included C${f['rbc_ul_bn']:.2f}BN of equities held for universal life policyholders. Their return passes through to policyholders, so the ALM repo removes them."},
        {"topic": "Liquid assets", "earlier": "78.5% public and liquid", "now": f"{f['rbc_liquid_unenc']:.1f}% after repo collateral",
         "why": f"C${f['rbc_repos_mm'] / 1e3:.1f}BN of bonds are out as repo collateral and cannot be sold. The peer median is {S['liquid_unenc']['median']:.0f}%."},
        {"topic": "Repo funding", "earlier": "14.1% of the portfolio", "now": f"{f['rbc_repos_ga']:.1f}% of own General Account",
         "why": f"Measured against the non-par General Account it funds. It was {f['rbc_repos_ga_fy24']:.1f}% a year earlier; Sun Life is at {f['slf_repos_ga']:.1f}% and the other {f['osfi_peers_nil_repos']} OSFI peers report none."},
        {"topic": "Energy bonds", "earlier": "37.6% read as a concentration", "now": "37.6%, a sector coding question",
         "why": f"RBC Life files no Utilities line and puts {f['rbc_sector_other']:.0f}% in Other. Energy and utilities together are {L.loc['RBC', 'energy_util']:.1f}% against a peer median of {S['energy_util']['median']:.1f}%."},
        {"topic": "Market risk capital", "earlier": f"{f['rbc_market_cap_inv']:.2f}% of invested assets, near the median",
         "now": f"{f['rbc_market_cap_ga']:.2f}% of own General Account",
         "why": f"On its own General Account RBC Life ranks {S['market_cap_ga']['rank_from_low']} from the lowest of {S['market_cap_ga']['n']} all-Canada filers (median {S['market_cap_ga']['median']:.2f}%)."},
        {"topic": "BMO Life capital ratio", "earlier": "134.1%", "now": f"{f['bmo_licat']:.1f}%",
         "why": "Corrected to the fiscal 2025 Q4 OSFI filing."},
        {"topic": "Earnings at risk", "earlier": "One total per insurer, against a limit", "now": "Removed",
         "why": "The ALM repo never adds sensitivities across risks, the total mixed group and entity figures and pre-tax and after-tax figures, and an internal limit does not belong in a peer document."},
        {"topic": "Sensitivities", "earlier": "Scaled to ±50 bps and −10%; RBC Life shown as not disclosed",
         "now": "Each insurer's own shock; RBC Insurance group figures used as a proxy",
         "why": "Scaling assumed linear behaviour. RBC's annual report (Note 15) gives a −100 bps rate and a −10% equity sensitivity for the insurance group."},
        {"topic": "Liquidity weights and time buckets", "earlier": "Illustrative haircuts by asset class (Doff)", "now": "Removed",
         "why": "The weights were illustrative. The repo measures liquidity as liquid assets net of collateral, repos and other financing against the General Account."},
        {"topic": "Peer set", "earlier": "20 insurers on the project list", "now": f"{f['n_peers']:.0f} insurers in the ALM study",
         "why": "The repo's set adds Blumont (pension risk transfer). Six project-list names sit outside it and are listed on the Method tab."},
    ]
    write("changes.csv", changes)

    # --- coverage map ---
    items = ["LICAT capital by category", "General Account and buffer", "Asset mix by block", "Bond sectors", "Repos and financing",
             "Pledged assets", "Rate sensitivity", "Spread sensitivity", "Equity sensitivity", "Real estate and alternatives sensitivity"]
    sens_have = {(r["id"], r["risk"]): r for r in sens}
    sens_item = {"Rate sensitivity": "Interest rates", "Spread sensitivity": "Credit spreads", "Equity sensitivity": "Public equity",
                 "Real estate and alternatives sensitivity": "Real estate and alternatives"}
    cov = []
    for p in ORDER:
        for it in items:
            if it in sens_item:
                r = sens_have.get((p, sens_item[it]))
                if r is None:
                    st = "Not available"
                elif p == "RBC":
                    st = "Estimate or proxy"
                elif r["net_income_mm"] is None and r["csm_mm"] is None:
                    st = "Not available"
                else:
                    st = "Insurer disclosure"
            elif it == "Pledged assets":
                st = "Insurer disclosure" if p in v2["pledged_summary"] else "Not available"
            elif it == "General Account and buffer":
                st = "Regulatory filing" if p in OSFI else ("Estimate or proxy" if p in ("IAG", "BEN") else "Not available")
            elif it == "Repos and financing":
                st = "Regulatory filing" if p in OSFI else ("Insurer disclosure" if p in ("IAG", "BEN") else "Not available")
            elif it == "Asset mix by block":
                st = ("Estimate or proxy" if p in ("MFC", "SLF") else "Regulatory filing") if p in OSFI else "Not available"
            else:
                st = "Regulatory filing" if p in OSFI else "Not available"
            cov.append({"id": p, "company": NAMES[p], "item": it, "status": st})
    write("coverage.csv", cov)

    # --- project-list insurers outside the ALM study ---
    out = pd.read_csv(os.path.join(HERE, "outside_study.csv"))
    uni = {"Canadian Premier Life": "Canadian Premier Life Insurance Company", "Primerica Life": "Primerica Life Insurance Company of Canada"}
    rows = []
    for _, x in out.iterrows():
        r = {"company": x.company, "regulator": x.regulator, "capital_ratio_pct": num(x.capital_ratio_pct), "capital_basis": x.capital_basis,
             "market_cap_inv": None, "credit_cap_inv": None, "ins_share": None, "note": x.note}
        if x.company in uni:
            u = universe[universe.entity == uni[x.company]].iloc[0]
            cmi = u.credit_risk_nonpar + u.market_risk_nonpar + u.insurance_risk_nonpar
            r.update({"capital_ratio_pct": rnd(u.licat_total_pct, 1), "market_cap_inv": rnd(100 * u.market_risk_nonpar / u.investments, 2),
                      "credit_cap_inv": rnd(100 * u.credit_risk_nonpar / u.investments, 2), "ins_share": rnd(100 * u.insurance_risk_nonpar / cmi, 1)})
        rows.append(r)
    write("outside_study.csv", rows)

    with open(os.path.join(OUT, "build_info.json"), "w", encoding="utf-8") as fh:
        json.dump({"alm_repo": "MooseDragon/cdn-life-insurer-alm", "alm_commit": commit, "period": "fiscal 2025 year end"}, fh, indent=1)
    print("ALM repo commit", commit)


if __name__ == "__main__":
    main()
