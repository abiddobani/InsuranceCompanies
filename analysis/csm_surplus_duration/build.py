"""Estimate the duration of the assets backing each peer's CSM and surplus, by asset class.

Inputs: disclosed_inputs.py (hand-entered fiscal 2025 notes), osfi_inputs.csv (osfi_extract.py) and the
general-account mixes in ../portfolio_composition/portfolio_composition_pct.csv.
Outputs (this folder): results.csv, portfolio_breakdown.csv, csm_runoff.csv, class_durations.csv, fvoci.csv.

Method, in short (README.md has the long version):
1. Class durations. Debt maturity buckets are mapped to a representative term and converted to the modified
   duration of a par bond yielding Y. Equity, real estate and alternatives carry no rate duration.
2. CSM run-off duration. The disclosed CSM recognition schedule is spread evenly within each bucket, the open-ended
   last bucket decays geometrically from the last full bucket's annual level, and the Macaulay duration of that
   stream is taken at Y. Without a schedule, a geometric run-off at the 2025 release rate (CSM recognised over
   opening CSM) is used, scaled by the peer calibration factor.
3. Pool. The CSM and surplus portfolios together ("the pool") equal net CSM plus equity less goodwill and
   intangibles. Where the insurer separates these assets (FVOCI/amortized cost designation, or a non-matching
   portfolio), the pool takes that disclosed mix; otherwise it mirrors the general account.
4. Split. Surplus takes the pool's equity, real estate and alternatives first; the CSM portfolio takes fixed income;
   remaining fixed income is shared pro rata.
5. Check. The disclosed rate sensitivity of total equity gives the net duration of the pool on an IFRS basis.
"""
import csv, math, pathlib, statistics, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from disclosed_inputs import COMPANIES, TAX  # noqa: E402

Y = 0.0425  # flat yield for bucket durations and CSM discounting, near YE2025 Canadian mid/long yields
FOCUS = "rbc_life"
ORDER = ["rbc_life", "manulife", "sun_life", "canada_life", "ia", "desjardins", "beneva", "empire_life",
         "equitable_life", "bmo_life", "ivari", "cooperators_life", "primerica_life", "foresters_life",
         "canada_protection_plan", "wawanesa_life", "assumption_life", "canadian_premier", "uv_insurance", "humania"]
FI = ["Government bonds", "Corporate bonds", "Private debt", "Mortgages & loans", "Cash"]
NONFI = ["Public equity", "Real estate & alternatives"]
CLASSES = FI + NONFI

# Representative term (years) for each bucket label used in the filings.
REP = {"<=1": 0.5, "1-2": 1.5, "2-3": 2.5, "3-4": 3.5, "4-5": 4.5, "1-3": 2.0, "3-5": 4.0, "1-5": 3.0,
       "2-5": 3.5, "5-10": 7.5, "6-10": 8.0, ">10": 20.0, "10-20": 15.0, ">20": 27.0,
       ">5gov": 20.0, ">5corp": 10.0, ">5mort": 7.0, ">5pp": 9.0}
CASH_D = 0.25
# Liability-mix proxy: bond duration that would match each OSFI LF3 line (used only when no maturity data exist).
LINE_D = {"liab_ind_ins": 13.0, "liab_ind_ann": 8.0, "liab_grp_ins": 5.0, "liab_grp_ann": 10.0, "liab_par": 12.0}


def moddur(m, y=Y):
    """Modified duration of a par bullet bond with annual coupon y and term m."""
    return (1 - (1 + y) ** -m) / y if m > 0 else 0.0


def bucket_duration(buckets):
    tot = sum(a for _, a in buckets)
    return sum(a * moddur(REP[k]) for k, a in buckets) / tot if tot else None


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def runoff_from_buckets(buckets):
    """Annual CSM release vector (years 1..n) from bucketed amounts."""
    spans = {"<=1": (0, 1), "1-2": (1, 2), "2-3": (2, 3), "3-4": (3, 4), "4-5": (4, 5), "1-3": (1, 3), "3-5": (3, 5),
             "1-5": (1, 5), "2-5": (2, 5), "5-10": (5, 10), "10-20": (10, 20)}
    rel = [0.0] * 120
    last_level, last_end = None, 0
    for k, a in buckets:
        if k in spans:
            s, e = spans[k]
            for t in range(s, e):
                rel[t] += a / (e - s)
            last_level, last_end = a / (e - s), e
        else:  # open-ended tail: geometric decay from the last full bucket's annual level
            q = min(a / (a + last_level), 0.97) if last_level else 0.9
            lvl = last_level * q
            t = last_end
            while t < 120 and lvl > 1e-9:
                rel[t] += lvl
                lvl *= q
                t += 1
            scale = a / sum(rel[last_end:]) if sum(rel[last_end:]) else 0  # keep the bucket total exact
            for t in range(last_end, 120):
                rel[t] *= scale
    return rel


def runoff_geometric(r, n=120):
    return [r * (1 - r) ** t for t in range(n)]


def macaulay(rel, y=Y):
    pv = [a / (1 + y) ** (t + 0.5) for t, a in enumerate(rel)]
    return sum((t + 0.5) * p for t, p in enumerate(pv)) / sum(pv)


def load_osfi():
    with open(HERE / "osfi_inputs.csv") as fh:
        return {r["company_id"]: {k: (num(v) if k not in ("company_id", "entity") else v) for k, v in r.items()}
                for r in csv.DictReader(fh)}


def load_ga():
    """General-account mix (C$MM) by our classes from the portfolio composition analysis."""
    path = HERE.parent / "portfolio_composition" / "portfolio_composition_pct.csv"
    m = {"Government bonds": ["Government Bonds"],
         "Corporate bonds": ["Corporate Bonds", "Asset Backed Securities", "Bonds (issuer n/d)"],
         "Private debt": ["Illiquid Term Loans", "Private Liquid Loans", "Infrastructure Debt", "Structured Products",
                          "Other Private Debt"],
         "Mortgages & loans": ["Commercial Mortgages", "Policy & Other Loans"],
         "Cash": ["Cash"],
         "Public equity": ["Common Shares", "Preferred Shares"],
         "Real estate & alternatives": ["Real Estate Equity", "Infrastructure Equity", "Other Private Equity",
                                        "Co-Investments", "Other / Unclassified"]}
    out = {}
    with open(path) as fh:
        for r in csv.DictReader(fh):
            tot = float(r["portfolio_cad_mm"])
            out[r["company_id"]] = dict(as_of=r["as_of"], total=tot,
                                        mix={c: sum(float(r[k] or 0) for k in ks) / 100 * tot for c, ks in m.items()})
    return out


def main():
    osfi, ga = load_osfi(), load_ga()
    rows, breakdown, runoffs, classdur, fvoci_rows = [], [], [], [], []

    # ---- pass 1: CSM run-off durations where schedules are disclosed, to calibrate the release-rate proxy
    calib = []
    for cid, c in COMPANIES.items():
        cs = c.get("csm") or {}
        o = osfi.get(cid)
        if cs.get("buckets") and o and o.get("csm_recognised_canada") and o.get("csm_remaining_issued"):
            r = o["csm_recognised_canada"] / (o["csm_remaining_issued"] + o["csm_recognised_canada"])
            calib.append(macaulay(runoff_from_buckets(cs["buckets"])) / macaulay(runoff_geometric(r)))
    k_cal = statistics.median(calib) if calib else 1.0

    # ---- peer evidence on surplus / FVOCI fixed-income durations (for pools with no maturity data)
    pool_fi_peer = []
    for cid, c in COMPANIES.items():
        if c.get("pool_bonds"):
            pool_fi_peer.append(bucket_duration(c["pool_bonds"]["buckets"]))
        sfd = c.get("surplus_fi_duration")
        if sfd and sfd.get("dd_per_1pct"):
            eq = c["equity"]
            base = eq["shareholders"] - eq.get("goodwill", 0) - eq.get("intangibles", 0)
            pool_fi_peer.append(sfd["dd_per_1pct"] / base / 0.01)
    peer_pool_fi_d = statistics.median(pool_fi_peer)

    for cid in ORDER:
        c = COMPANIES[cid]
        o = osfi.get(cid) or {}
        name = c["name"]
        notes = []
        if cid == "canada_protection_plan":
            rows.append(dict(company_id=cid, company=name, regulator=c["regulator"], status="covered by Foresters Life",
                             notes=c["note"]))
            continue

        # ---------- CSM size and run-off duration
        cs = c.get("csm") or {}
        csm_net, csm_d, csm_basis, csm_src = None, None, "not disclosed", ""
        rel = None
        if cs.get("buckets"):
            rel = runoff_from_buckets(cs["buckets"])
            csm_net, csm_basis, csm_src = cs["net"], "disclosed schedule", cs["source"]
        elif cs.get("proxy"):
            p = cs["proxy"]
            r = p["recognised"] / (p["remaining"] + p["recognised"])
            rel = runoff_geometric(r)
            csm_net, csm_basis, csm_src = cs["net"], "estimated from release rate", cs["source"]
        elif o.get("csm_remaining_issued"):
            iss, rei, rec = o["csm_remaining_issued"], o.get("csm_remaining_reins") or 0, o.get("csm_recognised_canada")
            csm_net = (iss - rei) / 1000
            csm_src = (f"OSFI LF3 P35085 remaining CSM issued {iss/1000:,.0f} less reinsurance held {rei/1000:,.0f}; "
                       f"LF3 P45015 CSM recognised {rec/1000:,.0f}" if rec else "OSFI LF3 P35085")
            if rec:
                rel = runoff_geometric(rec / (iss + rec))
                csm_basis = "estimated from release rate"
        if rel is not None:
            csm_d = macaulay(rel)
            if csm_basis == "estimated from release rate":
                csm_d *= k_cal
            tot = sum(rel)
            runoffs.append(dict(company_id=cid, company=name, basis=csm_basis,
                                **{f"y{t+1}": round(rel[t] / tot, 5) for t in range(40)},
                                y41plus=round(sum(rel[40:]) / tot, 5)))

        # ---------- surplus size
        eq = c.get("equity")
        surplus, eq_src = None, ""
        if eq and not eq.get("osfi"):
            surplus = eq["shareholders"] - eq.get("goodwill", 0) - eq.get("intangibles", 0)
            eq_src = eq["source"]
        elif o.get("total_equity") is not None:
            surplus = (o["total_equity"] - (o.get("goodwill") or 0) - (o.get("intangibles") or 0)) / 1000
            eq_src = "OSFI LF1 total equity less goodwill and intangibles"
        if c.get("equity_note"):
            notes.append(c["equity_note"])

        # ---------- class durations
        cd, cd_src = {}, {}
        b = c.get("bonds")
        if b and b.get("by_issuer"):
            for cls, bk in b["by_issuer"].items():
                cd[cls] = bucket_duration(bk)
                cd_src[cls] = "disclosed maturities"
        elif b:
            cd["Government bonds"] = cd["Corporate bonds"] = bucket_duration(b["buckets"])
            cd_src["Government bonds"] = cd_src["Corporate bonds"] = "disclosed maturities"
        for key, cls in (("mortgages", "Mortgages & loans"), ("private_debt", "Private debt")):
            if c.get(key):
                cd[cls] = bucket_duration(c[key]["buckets"])
                cd_src[cls] = "disclosed maturities"
        if cid == "manulife":
            cd_src["Mortgages & loans"] += " (MD&A: commercial mortgages 3.9y Canada, 5.3y U.S.)"
        sens = c.get("sens") or {}
        # asset-implied bond duration where the asset leg of the rate sensitivity is published
        bonds_bsv = (o.get("bonds_bsv") or 0) / 1000
        if not cd.get("Government bonds"):
            if sens.get("assets_after_tax") and bonds_bsv:
                d = sens["assets_after_tax"] / (1 - TAX) / bonds_bsv / (abs(sens["shock_bp"]) / 1e4)
                cd["Government bonds"] = cd["Corporate bonds"] = d
                cd_src["Government bonds"] = cd_src["Corporate bonds"] = "implied by disclosed asset sensitivity"
            elif sens.get("assets_pre_tax") and bonds_bsv:
                d = sens["assets_pre_tax"] / bonds_bsv / (abs(sens["shock_bp"]) / 1e4)
                cd["Government bonds"] = cd["Corporate bonds"] = d
                cd_src["Government bonds"] = cd_src["Corporate bonds"] = "implied by disclosed asset sensitivity"
            elif o.get("liab_total_canada"):
                tot = sum(o.get(k) or 0 for k in LINE_D)
                if tot > 0:
                    d = sum((o.get(k) or 0) * v for k, v in LINE_D.items()) / tot
                    cd["Government bonds"] = cd["Corporate bonds"] = d
                    cd_src["Government bonds"] = cd_src["Corporate bonds"] = "proxy from liability mix (OSFI LF3)"
            if not cd.get("Government bonds"):
                cd["Government bonds"] = cd["Corporate bonds"] = 10.0
                cd_src["Government bonds"] = cd_src["Corporate bonds"] = "peer default (10y)"
        for cls in ("Private debt", "Mortgages & loans"):
            if cls not in cd:
                cd[cls] = min(cd["Corporate bonds"], 6.0) if cls == "Mortgages & loans" else cd["Corporate bonds"]
                cd_src[cls] = "assumed (no maturity table)"
        cd["Cash"], cd_src["Cash"] = CASH_D, "assumed"
        for cls in NONFI:
            cd[cls], cd_src[cls] = 0.0, "no rate duration"

        # ---------- pool composition
        pool_size = (csm_net or 0) + (surplus or 0) if surplus is not None else None
        pool_mix, pool_basis, pool_src = None, None, ""
        pool_fill = {}
        pool_fi_d = None
        if c.get("pool"):
            pool_mix = dict(c["pool"]["holdings"])
            pool_basis = c["pool"]["basis"]
            pool_src = c["pool"]["source"] + ". " + c["pool"]["note"]
            if c.get("pool_bonds"):
                pool_fi_d = bucket_duration(c["pool_bonds"]["buckets"])
        elif (c.get("pool_from_osfi") or cid in ("rbc_life", "bmo_life", "cooperators_life", "canadian_premier",
                                                  "primerica_life")) and o.get("total_inv_fvoci") is not None:
            g = lambda k: ((o.get(k) or 0)) / 1000  # noqa: E731
            pool_mix = {"Corporate bonds": g("bonds_fvoci") + g("bonds_amortized"),
                        "Mortgages & loans": g("mortgages_fvoci") + g("mortgages_amortized") + g("other_loans_fvoci")
                        + g("other_loans_amortized"),
                        "Cash": g("short_term_fvoci") + g("short_term_amortized"),
                        "Public equity": g("common_fvoci") + g("preferred_fvoci"),
                        "Real estate & alternatives": g("other_invested_fvoci") + g("other_invested_amortized")}
            pool_basis = "FVOCI and amortized cost designation"
            pool_src = ("OSFI LF2 P21012 columns 16 (FVOCI) and 36 (amortized cost); bonds not split by issuer at "
                        "this level, so shown as corporate bonds")
            if cid == "primerica_life":
                pool_basis = "FVOCI designation (whole bond book)"
                notes.append("Primerica Life Canada holds its whole bond book at FVOCI, so FVOCI does not single out "
                             "surplus; its insurance liabilities are largely reinsured.")
        if pool_mix and pool_size:
            have = sum(pool_mix.values())
            if have > pool_size * 1.02:  # more designated assets than CSM + surplus: trim fixed income pro rata
                excess = have - pool_size
                fi_tot = sum(pool_mix.get(k, 0) for k in FI)
                for k in FI:
                    if pool_mix.get(k):
                        pool_mix[k] -= excess * pool_mix[k] / fi_tot
                notes.append(f"Designated pool ({have:,.0f}) exceeds CSM + surplus; fixed income trimmed pro rata.")
            elif have < pool_size * 0.98 and cid in ga:  # shortfall: fill at general-account weights
                short = pool_size - have
                gm, gtot = ga[cid]["mix"], ga[cid]["total"]
                for k in CLASSES:
                    pool_fill[k] = short * gm[k] / gtot
                notes.append(f"Designated assets cover {have/pool_size:.0%} of CSM + surplus; the remaining "
                             f"{short:,.0f} is assumed to sit in general-account assets at general-account weights.")
            if not pool_fi_d and pool_basis and "FVOCI" in pool_basis and cid not in ("assumption_life",):
                pool_fi_d = peer_pool_fi_d
                pool_src += f". No maturity split for these bonds: duration set to the peer surplus/FVOCI median ({peer_pool_fi_d:.1f}y)"
        elif pool_size and cid in ga:
            gm, tot = ga[cid]["mix"], ga[cid]["total"]
            pool_mix = {k: v / tot * pool_size for k, v in gm.items()}
            pool_basis = "General-account mix (assumed)"
            pool_src = (c.get("pool_note", "") + f" General-account mix as at {ga[cid]['as_of']} from the portfolio "
                        "composition analysis.").strip()
        elif pool_size and c.get("ga"):
            gg = c["ga"]
            tot = sum(gg.values())
            pool_mix = {"Corporate bonds": gg["bonds"] / tot * pool_size, "Cash": gg["cash"] / tot * pool_size,
                        "Public equity": gg["equity"] / tot * pool_size,
                        "Real estate & alternatives": gg["alts"] / tot * pool_size,
                        "Mortgages & loans": gg["loans"] / tot * pool_size}
            pool_basis = "General-account mix (assumed)"
            pool_src = "Summary balance sheet"
        sfd = c.get("surplus_fi_duration")
        if sfd and surplus:
            pool_fi_d = sfd["dd_per_1pct"] / surplus / 0.01
            pool_src = (pool_src + " " if pool_src else "") + sfd["source"]

        # class durations inside the pool (fixed income may differ from the general account)
        pdur = dict(cd)
        if pool_fi_d:
            for k in ("Government bonds", "Corporate bonds"):
                pdur[k] = pool_fi_d
            for k in ("Private debt", "Mortgages & loans"):
                pdur[k] = min(cd[k], pool_fi_d) if c.get("pool_bonds") is None else cd[k]
        if c.get("pool") and c["pool"].get("holdings") and cid == "sun_life":
            # FVOCI/AC mortgages and loans: use their own buckets
            pdur["Mortgages & loans"] = bucket_duration([("<=1", 506), ("2-5", 1064), ("6-10", 134), (">10", 0)])
            pdur["Private debt"] = bucket_duration([("<=1", 346), ("2-5", 1717), ("6-10", 446), (">10", 73)])
        if pool_fill:
            for k in CLASSES:
                a, b2 = pool_mix.get(k, 0), pool_fill.get(k, 0)
                if a + b2 > 0:
                    pdur[k] = (a * pdur[k] + b2 * cd[k]) / (a + b2)
                pool_mix[k] = a + b2
        for cls in CLASSES:
            classdur.append(dict(company_id=cid, company=name, asset_class=cls,
                                 general_account_duration=round(cd[cls], 2),
                                 pool_duration=round(pdur[cls], 2), basis=cd_src.get(cls, "")))

        # ---------- split pool into surplus and CSM portfolios
        port = {"CSM": {}, "Surplus": {}}
        if pool_mix and surplus is not None:
            nonfi = {k: pool_mix.get(k, 0) for k in NONFI}
            nf_tot = sum(nonfi.values())
            to_surplus_nf = min(nf_tot, surplus)
            for k in NONFI:
                port["Surplus"][k] = nonfi[k] * (to_surplus_nf / nf_tot if nf_tot else 0)
                port["CSM"][k] = nonfi[k] - port["Surplus"][k]
            fi = {k: pool_mix.get(k, 0) for k in FI}
            fi_tot = sum(fi.values())
            s_left = max(surplus - to_surplus_nf, 0)
            c_left = max((csm_net or 0) - sum(port["CSM"].values()), 0)
            share_s = s_left / (s_left + c_left) if (s_left + c_left) else 0
            for k in FI:
                port["Surplus"][k] = fi[k] * share_s
                port["CSM"][k] = fi[k] * (1 - share_s)
        durs = {}
        for pname, mix in port.items():
            tot = sum(mix.values())
            if tot <= 0:
                durs[pname] = None
                continue
            durs[pname] = sum(mix[k] * pdur[k] for k in mix) / tot
            for k in CLASSES:
                amt = mix.get(k, 0)
                if amt > 0.0005:
                    breakdown.append(dict(company_id=cid, company=name, portfolio=pname, asset_class=k,
                                          amount_cad_mm=round(amt, 1), weight=round(amt / tot, 4),
                                          duration=round(pdur[k], 2), contribution=round(amt / tot * pdur[k], 3),
                                          duration_basis=cd_src.get(k, "") if not pool_fi_d or k not in
                                          ("Government bonds", "Corporate bonds") else "pool-specific estimate"))

        # ---------- implied net duration of the pool from the equity rate sensitivity
        net_d = None
        if sens and pool_size:
            shock = abs(sens["shock_bp"]) / 1e4
            if sens.get("net_after_tax") is not None:
                net_d = sens["net_after_tax"] / (1 - TAX) / shock / pool_size
            elif sens.get("assets_pre_tax") is not None:
                net_d = (sens["assets_pre_tax"] + sens["liabs_pre_tax"]) / shock / pool_size
        ga_bond_d = None
        if cd.get("Government bonds"):
            gm = ga.get(cid, {}).get("mix")
            if gm:
                fi_amt = sum(gm[k] for k in FI)
                ga_bond_d = sum(gm[k] * cd[k] for k in FI) / fi_amt if fi_amt else None

        rows.append(dict(
            company_id=cid, company=name, regulator=c["regulator"], focus=cid == FOCUS,
            csm_net_cad_mm=round(csm_net, 1) if csm_net else None,
            csm_runoff_duration=round(csm_d, 2) if csm_d else None, csm_basis=csm_basis, csm_source=csm_src,
            surplus_cad_mm=round(surplus, 1) if surplus is not None else None, surplus_source=eq_src,
            pool_basis=pool_basis, pool_source=pool_src,
            csm_portfolio_duration=round(durs.get("CSM"), 2) if durs.get("CSM") else None,
            surplus_portfolio_duration=round(durs.get("Surplus"), 2) if durs.get("Surplus") is not None and port["Surplus"] else None,
            surplus_fi_share=round(sum(port["Surplus"].get(k, 0) for k in FI) / surplus, 3) if surplus and port["Surplus"] else None,
            general_account_fi_duration=round(ga_bond_d, 2) if ga_bond_d else None,
            implied_net_pool_duration=round(net_d, 2) if net_d is not None else None,
            sensitivity_source=sens.get("source", ""),
            duration_gap_csm=round(durs["CSM"] - csm_d, 2) if durs.get("CSM") and csm_d else None,
            notes=" ".join(notes + ([c["note"]] if c.get("note") else [])),
        ))

        # ---------- FVOCI exposure
        f = c.get("fvoci") or {}
        fr = dict(company_id=cid, company=name, focus=cid == FOCUS)
        if o.get("total_inv_fvoci") is not None:
            g = lambda k: (o.get(k) or 0) / 1000  # noqa: E731
            fr.update(source_fvoci="OSFI LF2 P21012 (FVOCI col 16, amortized cost col 36), fiscal 2025 Q4",
                      fvoci_bonds=g("bonds_fvoci"), fvoci_mortgages_loans=g("mortgages_fvoci") + g("other_loans_fvoci"),
                      fvoci_equities=g("common_fvoci") + g("preferred_fvoci"), fvoci_total=g("total_inv_fvoci"),
                      amortized_cost_total=g("total_inv_amortized"), invested_total=g("total_inv_bsv"),
                      aoci_fvoci=(g("aoci_fvoci_recycling") + g("aoci_fvoci_no_recycling")),
                      oci_fvoci_bonds_2025=g("oci_fvoci_bonds_chg"))
        elif o:
            fr.update(source_fvoci="OSFI LF2 P21012: no FVOCI holdings reported", fvoci_total=0.0,
                      invested_total=(o.get("total_inv_bsv") or 0) / 1000)
        fr.update(oci_rate_sensitivity=f.get("oci_sens", ""), disclosed_limits=f.get("limits", "Not disclosed."),
                  source_sensitivity=f.get("source", ""))
        if cid == "manulife":
            fr["note"] = "FVOCI also backs insurance liabilities (IFRS 17 OCI option), so it is not a surplus measure."
            # OSFI AOCI is the Canadian legal entity only; the FS figure is the group FVOCI reserve
            fr.update(aoci_fvoci=-16513.0, source_aoci="MFC 2025 FS consolidated statement of changes in equity")
        # estimated after-tax OCI for a 50bp fall where nothing is disclosed: FVOCI fixed income x duration
        fi = (fr.get("fvoci_bonds") or 0) + (fr.get("fvoci_mortgages_loans") or 0)
        if fi and not f.get("oci_sens"):
            d_est = pool_fi_d or peer_pool_fi_d
            fr.update(oci_per_50bp_estimated=round(fi * d_est * 0.005 * (1 - TAX), 1), oci_estimate_duration=round(d_est, 2))
        if cid == "beneva":
            fr.update(source_fvoci="Beneva 2025 AR note 5", fvoci_bonds=2536.8, fvoci_equities=822.6,
                      fvoci_total=3359.4, amortized_cost_total=1526.1, invested_total=18872.8)
        if cid == "assumption_life":
            fr.update(source_fvoci="Assumption 2025 AR note 4", fvoci_bonds=55.7, fvoci_equities=64.6,
                      fvoci_total=120.3, amortized_cost_total=115.5, invested_total=1250.4)
        if cid == "sun_life":
            fr.update(source_fvoci="SLF 2025 FS note 6 (consolidated)", fvoci_bonds=13019, fvoci_mortgages_loans=499 + 2234,
                      fvoci_total=13019 + 499 + 2234, amortized_cost_total=1205 + 348, invested_total=182574)
        fvoci_rows.append(fr)

    def write(name, data):
        keys = []
        for d in data:
            for k in d:
                if k not in keys:
                    keys.append(k)
        with open(HERE / name, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            for d in data:
                w.writerow({k: (round(v, 1) if isinstance(v, float) and k.startswith(("fvoci", "amort", "invest", "aoci", "oci_fvoci")) else v)
                            for k, v in d.items()})
    write("results.csv", rows)
    write("portfolio_breakdown.csv", breakdown)
    write("csm_runoff.csv", runoffs)
    write("class_durations.csv", classdur)
    write("fvoci.csv", fvoci_rows)
    with open(HERE / "parameters.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["parameter", "value", "note"])
        w.writerow(["yield", Y, "flat yield for bucket durations and CSM discounting"])
        w.writerow(["tax_rate", TAX, "gross-up for after-tax sensitivities"])
        w.writerow(["release_rate_calibration", round(k_cal, 3),
                    f"median ratio of schedule-based to release-rate CSM duration across {len(calib)} insurers"])
        w.writerow(["peer_pool_fi_duration", round(peer_pool_fi_d, 2),
                    "median of Sun Life FVOCI debt and Foresters surplus fixed-income durations"])
        for k, v in REP.items():
            w.writerow([f"bucket_{k}", v, f"representative term; duration {moddur(v):.2f}"])
        for k, v in LINE_D.items():
            w.writerow([k, v, "liability-mix proxy duration"])
    print(f"calibration {k_cal:.3f} from {len(calib)}; peer pool FI duration {peer_pool_fi_d:.2f}")
    for r in rows:
        print(f"{r['company'][:18]:18s} csm={r.get('csm_net_cad_mm')!s:>8} Dcsm={r.get('csm_runoff_duration')!s:>6} "
              f"surplus={r.get('surplus_cad_mm')!s:>8} D_CSMp={r.get('csm_portfolio_duration')!s:>6} "
              f"D_Sur={r.get('surplus_portfolio_duration')!s:>6} net={r.get('implied_net_pool_duration')!s:>6} "
              f"pool={r.get('pool_basis')}")


if __name__ == "__main__":
    main()
