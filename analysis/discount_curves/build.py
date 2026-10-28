"""Discount curve landscape across the 20-company peer set.

Inputs
  data/osfi/discount_curves.csv          OSFI LF2 IFRS 17 curves (most illiquid bucket) for OSFI-regulated insurers
  analysis/discount_curves/disclosed_curves.csv
                                         least / most illiquid curves hand-copied from the annual reports of the
                                         AMF / FCNB-regulated insurers that publish them

Outputs (analysis/discount_curves/)
  curves_normalised.csv   one row per company, period, region, line of business and tenor, with the risk-free rate,
                          discount rate and illiquidity premium side by side, and how each was obtained
  landscape_2025q4.csv    one row per company: headline curve points, illiquidity premiums and the liability value
                          implied by its curve against the peer median, at year end 2025
  landscape_latest.csv    the same for each OSFI insurer's latest quarter
  dashboard/*.csv         the sources the landscape dashboard draws

Conventions
  - OSFI reports only the most illiquid bucket. For annual-report curves we compare the most illiquid curve too.
  - An insurer files either a discount rate (page P35055) or a liquidity premium over its own risk-free curve
    (page P35035). The missing one is derived: DR = RFR + LP, or LP = DR - RFR.
  - RBC Life files no risk-free curve, and its "discount rates" hump to 7%+ at 20 years and fall to 1.3% at 70 before
    jumping to 4.10% at 80. That is the shape of one-year forward rates grading to an ultimate forward, so we treat
    them as forwards and derive spot rates by compounding (forwards interpolated linearly between reported tenors).
    This is our interpretation, not something OSFI states.
  - Insurers that publish no risk-free curve (RBC Life, the annual-report insurers) get an estimated illiquidity
    premium over the peer median risk-free curve for the same quarter.
  - 2023Q1 is left out: see SKIP_PERIODS.
  - BMO Life and RBC Life file on an October fiscal year, so their "Q4" is 31 October, two months before the others.
"""
import csv
import os
import statistics
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))

# Entity whose curves stand for each group (the main Canadian operating life company)
PRIMARY = {
    "bmo_life": "BMO Life Assurance Company",
    "canada_life": "The Canada Life Assurance Company",
    "canadian_premier": "Canadian Premier Life Insurance Company",
    "cooperators_life": "Co-operators Life Insurance Company",
    "empire_life": "The Empire Life Insurance Company",
    "equitable_life": "The Equitable Life Insurance Company of Canada",
    "foresters_life": "Foresters Life Insurance Company",
    "ivari": "ivari",
    "manulife": "The Manufacturers Life Insurance Company",
    "primerica_life": "Primerica Life Insurance Company of Canada",
    "rbc_life": "RBC Life Insurance Company",
    "sun_life": "Sun Life Assurance Company of Canada",
    "wawanesa_life": "The Wawanesa Life Insurance Company",
}
NAMES = {
    "bmo_life": "BMO Life", "canada_life": "Canada Life", "canadian_premier": "Canadian Premier",
    "cooperators_life": "Co-operators Life", "empire_life": "Empire Life", "equitable_life": "Equitable Life",
    "foresters_life": "Foresters Life", "ivari": "ivari", "manulife": "Manulife", "primerica_life": "Primerica Life",
    "rbc_life": "RBC Life", "sun_life": "Sun Life", "wawanesa_life": "Wawanesa Life",
    "ia": "iA Financial", "desjardins": "Desjardins", "beneva": "Beneva", "assumption_life": "Assumption Life",
}
NOT_DISCLOSED = {
    "humania": ("Humania", "AMF", "Publishes only summary consolidated statements (LS Mutual Management); no discount curve"),
    "uv_insurance": ("UV Insurance", "AMF", "Annual report carries summary statements only; full statements on request"),
    "canada_protection_plan": ("Canada Protection Plan", "OSFI",
                               "A Foresters business with no separate filing; covered by Foresters Life"),
}
OCT_FY = {"bmo_life", "rbc_life"}
# 2023Q1, the first IFRS 17 quarter: most insurers filed premiums as fractions (0.0178 for 1.78%), which OSFI's open
# data rounds to 0.01 or 0.02, and Wawanesa filed its risk-free rates in basis points. Not recoverable, so skipped.
SKIP_PERIODS = {"2023Q1"}
FORWARD_FILERS = {"rbc_life"}
LOB_SHORT = {
    "Non-Participating, Individual, Insurance": "Individual insurance",
    "Non-Participating, Individual, Annuity (Excluding Segregated Fund with Guarantees)": "Individual annuity",
    "Non-Participating, Individual, Segregated Fund with Guarantees": "Individual seg fund",
    "Non-Participating, Group, Insurance": "Group insurance",
    "Non-Participating, Group, Annuity (Excluding Segregated Fund with Guarantees)": "Group annuity",
    "Non-Participating, Group, Segregated Fund with Guarantees": "Group seg fund",
    "Participating": "Participating",
    "Reinsurance": "Reinsurance",
}
HEADLINE = "Individual insurance"
GRID = list(range(1, 81))
KEY_TENORS = [1, 5, 10, 20, 30, 70]


def period_key(p):
    return int(p[:4]) * 10 + int(p[-1])


def interp_curve(points):
    """Annual curve 1..80 from {tenor: rate}, linear between points and flat outside."""
    ts = sorted(points)
    return np.interp(GRID, ts, [points[t] for t in ts])


def forwards_to_spot(points):
    f = interp_curve(points) / 100
    spot = np.cumprod(1 + f) ** (1 / np.arange(1, 81)) - 1
    return {t: round(float(spot[t - 1] * 100), 2) for t in points}


def flat_curve(points):
    """For a curve that is one roughly flat rate (range within 1 point once its most deviant point is set aside),
    the points within half a point of its median; None if the curve is not flat."""
    med = statistics.median(points.values())
    rest = sorted(points.values(), key=lambda v: abs(v - med))[:-1]
    if len(points) < 5 or max(rest) - min(rest) > 1.0:
        return None
    return {t: v for t, v in points.items() if abs(v - med) <= 0.5}


# Stylised long-dated life liability: annual payments falling 4% a year for 80 years
CF = 0.96 ** np.arange(80)


def pv(points):
    r = interp_curve(points) / 100
    return float((CF / (1 + r) ** np.arange(1, 81)).sum())


def flat_equivalent(points):
    """The single rate that gives the stylised liability the same value as the curve."""
    target, lo, hi = pv(points), 0.0, 0.2
    for _ in range(60):
        mid = (lo + hi) / 2
        if (CF / (1 + mid) ** np.arange(1, 81)).sum() > target:
            lo = mid
        else:
            hi = mid
    return round(mid * 100, 2)


def duration(points):
    r = interp_curve(points) / 100
    df = CF / (1 + r) ** np.arange(1, 81)
    return float((df * np.arange(1, 81)).sum() / df.sum())


def load_osfi():
    rfr = {}
    vals = defaultdict(dict)  # (cid, p, region, lob, tenor) -> {kind: value}
    with open(os.path.join(ROOT, "data/osfi/discount_curves.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cid = r["company_id"]
            if PRIMARY.get(cid) != r["entity"]:
                continue
            p = f'{r["fiscal_year"]}Q{r["quarter"][-1]}'
            if p in SKIP_PERIODS:
                continue
            t = int(r["tenor_years"])
            v = float(r["rate_pct"])
            if r["curve"] == "Risk Free Rates":
                rfr[(cid, p, r["region"], t)] = v
                continue
            lob, kind = r["curve"].rsplit(", ", 1)
            vals[(cid, p, r["region"], LOB_SHORT[lob], t)][kind] = v
    return rfr, vals


def main():
    rfr, vals = load_osfi()

    # Peer median risk-free curve per quarter (calendar-year filers only), used where an insurer gives none
    by_q = defaultdict(list)
    for (cid, p, reg, t), v in rfr.items():
        if cid not in OCT_FY:
            by_q[(p, reg, t)].append(v)
    med_rfr = {k: round(statistics.median(v), 2) for k, v in by_q.items()}
    # October filers' latest quarter can run past the others': fall back to the latest earlier peer quarter
    peer_periods = sorted({p for p, _, _ in med_rfr}, key=period_key)

    def peer_rfr(p, reg, t):
        for q in reversed([q for q in peer_periods if period_key(q) <= period_key(p)]):
            if (q, reg, t) in med_rfr:
                return med_rfr[(q, reg, t)]
        return None

    # RBC files forwards: convert each curve to spot before anything else
    anomalies = []
    rbc_curves = defaultdict(dict)
    for (cid, p, reg, lob, t), kv in vals.items():
        if cid in FORWARD_FILERS and "Discount Rates" in kv:
            rbc_curves[(cid, p, reg, lob)][t] = kv["Discount Rates"]
    for key, pts in rbc_curves.items():
        flat = flat_curve(pts)
        if flat is not None:
            # One roughly flat rate (RBC's par line until fiscal Q4 2025) reads the same as spot or forward: keep it
            # as filed, but drop stray points that break the flat line (its 70-year value) and log them
            for t in set(pts) - set(flat):
                anomalies.append(dict(company_id=key[0], period=key[1], region=key[2], lob=key[3], tenor=t,
                                      filed=pts[t], reason="breaks an otherwise flat curve; dropped"))
                del vals[key + (t,)]
            continue
        for t, s in forwards_to_spot(pts).items():
            vals[key + (t,)]["Discount Rates (forward)"] = vals[key + (t,)].pop("Discount Rates")
            vals[key + (t,)]["Discount Rates"] = s

    rows = []
    for (cid, p, reg, lob, t), kv in sorted(vals.items()):
        own = rfr.get((cid, p, reg, t))
        base = own if own is not None else peer_rfr(p, reg, t)
        if "Discount Rates" in kv:
            dr = kv["Discount Rates"]
            dr_basis = "derived spot from reported forwards" if "Discount Rates (forward)" in kv else "reported"
            lp = round(dr - base, 2) if base is not None else None
            lp_basis = "DR - own RFR" if own is not None else "DR - peer median RFR (estimate)"
        else:
            lp = kv["Liquidity Premium"]
            lp_basis = "reported"
            dr = round(own + lp, 2) if own is not None else None
            dr_basis = "own RFR + LP"
        rows.append(dict(company_id=cid, company=NAMES[cid], source="OSFI LF2", regulator="OSFI", period=p,
                         period_end=("Oct FY " if cid in OCT_FY else "") + p, region=reg, bucket="most_illiquid",
                         lob=lob, tenor=t, rfr=own, dr=dr, lp=lp, dr_basis=dr_basis, lp_basis=lp_basis,
                         dr_filed_forward=kv.get("Discount Rates (forward)")))

    with open(os.path.join(HERE, "disclosed_curves.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            p = r["as_at"][:4] + "Q4"
            t = 70 if r["tenor"] == "ult" else int(r["tenor"])
            dr = float(r["rate_pct"])
            base = peer_rfr(p, r["region"], t)
            rows.append(dict(company_id=r["company_id"], company=NAMES[r["company_id"]], source="Annual report",
                             regulator="FCNB" if r["company_id"] == "assumption_life" else "AMF", period=p,
                             period_end=r["as_at"], region=r["region"], bucket=r["bucket"], lob="All products",
                             tenor=t, rfr=None, dr=dr, lp=round(dr - base, 2) if base is not None else None,
                             dr_basis="reported" + (" (ultimate, placed at 70y)" if r["tenor"] == "ult" else ""),
                             lp_basis="DR - peer median RFR (estimate)", dr_filed_forward=None))

    fields = list(rows[0])
    with open(os.path.join(HERE, "curves_normalised.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # Headline curve per company and period: Canada, most illiquid, individual insurance (or all products)
    head = defaultdict(dict)
    head_lp = defaultdict(dict)
    for r in rows:
        if r["region"] == "Canada" and r["bucket"] == "most_illiquid" and r["lob"] in (HEADLINE, "All products") \
                and r["dr"] is not None:
            head[(r["company_id"], r["period"])][r["tenor"]] = r["dr"]
            if r["lp"] is not None:
                head_lp[(r["company_id"], r["period"])][r["tenor"]] = r["lp"]

    def landscape(period_of):
        sel = {cid: period_of(cid) for cid in NAMES}
        sel = {cid: p for cid, p in sel.items() if p and (cid, p) in head}
        med = {t: statistics.median(interp_curve(head[(c, p)])[t - 1] for c, p in sel.items()) for t in GRID}
        med_pts = {t: round(med[t], 3) for t in GRID}
        pv_med = pv(med_pts)
        out = []
        for cid, p in sel.items():
            pts = head[(cid, p)]
            lps = head_lp.get((cid, p), {})
            full = interp_curve(pts)
            pv_c = pv(pts)
            ult_rfr = rfr.get((cid, p, "Canada", 80)) or rfr.get((cid, p, "Canada", 70))
            out.append(dict(
                company_id=cid, company=NAMES[cid],
                regulator="OSFI" if cid in PRIMARY else ("FCNB" if cid == "assumption_life" else "AMF"),
                source="OSFI LF2" if cid in PRIMARY else "Annual report", period=p,
                as_at=("Oct FY " if cid in OCT_FY else "") + p,
                **{f"dr_{t}y": round(float(full[t - 1]), 2) for t in KEY_TENORS},
                **{f"lp_{t}y": (round(float(np.interp(t, sorted(lps), [lps[k] for k in sorted(lps)])), 2)
                                if lps else None) for t in KEY_TENORS},
                ult_rfr=ult_rfr,
                lp_basis=("estimate vs peer median RFR" if cid not in PRIMARY or cid in FORWARD_FILERS
                          else "own RFR"),
                duration=round(duration(pts), 1),
                liability_vs_median_pct=round((pv_c / pv_med - 1) * 100, 2),
                liability_vs_median_per_10bn_mm=round((pv_c / pv_med - 1) * 10000, 0),
            ))
        out.sort(key=lambda r: r["dr_30y"], reverse=True)
        return out, med_pts

    ye, med_ye = landscape(lambda cid: "2025Q4")
    latest_p = {cid: max((p for c, p in head if c == cid), key=period_key) for cid in PRIMARY}
    latest, med_latest = landscape(lambda cid: latest_p.get(cid))

    for name, data in (("landscape_2025q4.csv", ye), ("landscape_latest.csv", latest)):
        with open(os.path.join(HERE, name), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows(data)

    # Time series of 10y and 30y discount rate and premium on the headline curve
    series = defaultdict(list)
    for (cid, p), pts in sorted(head.items(), key=lambda kv: (kv[0][0], period_key(kv[0][1]))):
        full = interp_curve(pts)
        lps = head_lp.get((cid, p), {})
        series[cid].append(dict(period=p, dr10=round(float(full[9]), 2), dr30=round(float(full[29]), 2),
                                lp10=lps.get(10), lp30=lps.get(30)))

    # Lines of business at year end 2025: 30-year discount rate and premium by line, per OSFI insurer
    lob_tab = defaultdict(dict)
    for r in rows:
        if r["source"] == "OSFI LF2" and r["period"] == "2025Q4" and r["region"] == "Canada" and r["tenor"] == 30:
            lob_tab[r["company_id"]][r["lob"]] = dict(dr=r["dr"], lp=r["lp"])

    # Dashboard sources (analysis/discount_curves/dashboard/)
    dash_dir = os.path.join(HERE, "dashboard")
    os.makedirs(dash_dir, exist_ok=True)

    def write(name, data, fields=None):
        with open(os.path.join(dash_dir, name), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields or list(data[0]))
            w.writeheader()
            w.writerows(data)

    write("landscape_2025q4.csv", ye)
    write("landscape_latest.csv", latest)

    # Headline curve at year end 2025 on an annual grid, flagged where the point was reported
    annual = []
    for r in ye:
        pts = head[(r["company_id"], "2025Q4")]
        full = interp_curve(pts)
        for t in GRID:
            annual.append(dict(company=r["company"], source=r["source"], tenor=t, dr=round(float(full[t - 1]), 3),
                               reported="yes" if t in pts else "no"))
    write("curves_2025q4.csv", annual)

    write("premium_history.csv", [
        dict(company=NAMES[cid], source="OSFI LF2" if cid in PRIMARY else "Annual report",
             period=x["period"], dr_10y=x["dr10"], lp_10y=x["lp10"], dr_30y=x["dr30"], lp_30y=x["lp30"])
        for cid, xs in series.items() for x in xs if x["period"] != "2023Q1"])

    write("lines_2025q4.csv", [
        dict(company=NAMES[cid], line=lob, dr_30y=v["dr"], lp_30y=v["lp"])
        for cid, lobs in lob_tab.items() for lob, v in sorted(lobs.items())])

    write("risk_free_2025q4.csv", [
        dict(company=NAMES[cid], rfr_1y=rfr.get((cid, "2025Q4", "Canada", 1)),
             rfr_10y=rfr.get((cid, "2025Q4", "Canada", 10)), rfr_30y=rfr.get((cid, "2025Q4", "Canada", 30)),
             rfr_ultimate=rfr.get((cid, "2025Q4", "Canada", 80)),
             dr_ultimate=next(r["dr_70y"] for r in ye if r["company_id"] == cid),
             lp_ultimate=next(r["lp_70y"] for r in ye if r["company_id"] == cid))
        for cid in PRIMARY if (cid, "2025Q4", "Canada", 30) in rfr])

    coverage = []
    for cid in sorted(set(NAMES) | set(NOT_DISCLOSED), key=lambda c: (NAMES.get(c) or NOT_DISCLOSED[c][0]).lower()):
        if cid in PRIMARY:
            note = "Main operating entity: " + PRIMARY[cid]
            if cid in OCT_FY:
                note += "; October fiscal year"
            if cid in FORWARD_FILERS:
                note += "; files forward rates, converted to spot"
            coverage.append(dict(company=NAMES[cid], regulator="OSFI", curve_source="OSFI LF2, quarterly",
                                 periods=f"2023Q2 to {latest_p[cid]}", note=note))
        elif cid in NAMES:
            coverage.append(dict(company=NAMES[cid], regulator="FCNB" if cid == "assumption_life" else "AMF",
                                 curve_source="Annual report, year end", periods="2024, 2025",
                                 note="Least and most illiquid curves, all products"))
        else:
            name, reg, why = NOT_DISCLOSED[cid]
            coverage.append(dict(company=name, regulator=reg, curve_source="None", periods="", note=why))
    write("coverage.csv", coverage)

    # By product line, every quarter: annuities (individual, group), individual life, participating.
    # Annual-report insurers publish one set of curves for all products, so they appear under every product.
    products = {"Individual annuity": "Individual annuity", "Group annuity": "Group annuity",
                "Individual insurance": "Individual life", "Participating": "Participating"}
    prod_curves = defaultdict(dict)  # (company_id, period, product) -> {tenor: (dr, lp)}
    for r in rows:
        if r["region"] != "Canada" or r["bucket"] != "most_illiquid" or r["dr"] is None:
            continue
        targets = list(products.values()) if r["lob"] == "All products" else (
            [products[r["lob"]]] if r["lob"] in products else [])
        for prod in targets:
            prod_curves[(r["company_id"], r["period"], prod)][r["tenor"]] = (r["dr"], r["lp"])

    # Par: Abid asked (2026-10-28) to use each insurer's dividend scale interest rate (DSIR) as its par discount
    # rate, flat at every tenor, in place of the filed par curve; the premium is the DSIR less the risk-free curve.
    # The filed par curves are kept for the comparison in par_vs_dividend_rate.csv.
    dsir = {}
    with open(os.path.join(HERE, "dsir.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dsir[r["company_id"]] = r
    filed_par = {k: prod_curves.pop(k) for k in [k for k in prod_curves if k[2] == "Participating"]}
    PAR_TENORS = [1, 2, 5, 10, 20, 30, 60, 70, 80]
    calendar_periods = {k[1] for k in prod_curves if k[0] in PRIMARY and k[0] not in OCT_FY}
    for cid in dsir:
        # The DSIR is public every year, so insurers without quarterly filings get every calendar quarter
        own = {k[1] for k in prod_curves if k[0] == cid}
        for p in (own if cid in PRIMARY else calendar_periods):
            d = float(dsir[cid][f"dsir_{p[:4]}"])
            pts = {}
            for t in PAR_TENORS:
                base = rfr.get((cid, p, "Canada", t), peer_rfr(p, "Canada", t))
                pts[t] = (d, round(d - base, 2) if base is not None else None)
            prod_curves[(cid, p, "Participating")] = pts

    def at(pts, t, i):
        ts = [k for k in sorted(pts) if pts[k][i] is not None]
        return round(float(np.interp(t, ts, [pts[k][i] for k in ts])), 2) if ts else None

    PT = [5, 10, 20, 30, 80]  # tenors shown; beyond an annual-report curve's last tenor (70) its ultimate rate holds
    points, curve_rows = [], []
    for (cid, p, prod), pts in sorted(prod_curves.items(), key=lambda kv: (NAMES[kv[0][0]], period_key(kv[0][1]), kv[0][2])):
        ult = max(pts)
        rec = dict(company=NAMES[cid], source=f"Dividend scale interest rate {p[:4]}" if prod == "Participating" else
                   "OSFI LF2" if cid in PRIMARY else "Annual report, all products",
                   period=p, as_at=("Oct FY " if cid in OCT_FY else "") + p, product=prod)
        rec.update({f"dr_{t}y": at(pts, t, 0) for t in PT})
        rec.update({f"lp_{t}y": at(pts, t, 1) for t in PT})
        rec["last_tenor"] = ult
        rec["lp_basis"] = "Own risk-free curve" if (cid, p, "Canada", 30) in rfr else \
            "Peer median risk-free (estimate)"
        points.append(rec)
        for t in sorted(set(pts) | {80}):
            dr = pts[t][0] if t in pts else pts[ult][0]
            curve_rows.append(dict(company=NAMES[cid], period=p, product=prod, tenor=t, dr=dr))

    # Peer median per product and quarter: of each metric, and of the curve on a common tenor grid
    MED_GRID = [1, 2, 5, 10, 15, 20, 30, 60, 70, 80]
    groups = defaultdict(list)
    for rec in points:
        groups[(rec["period"], rec["product"])].append(rec)
    for (p, prod), recs in sorted(groups.items(), key=lambda kv: (period_key(kv[0][0]), kv[0][1])):
        med = dict(company="Peer median", source=f"Median of {len(recs)} insurers", period=p, as_at=p, product=prod)
        for k in [f"{m}_{t}y" for m in ("dr", "lp") for t in PT]:
            vals = [rec[k] for rec in recs if rec[k] is not None]
            med[k] = round(statistics.median(vals), 2) if vals else None
        med["last_tenor"] = ""
        med["lp_basis"] = ""
        points.append(med)
        cids = [cid for cid in NAMES if any(rec["company"] == NAMES[cid] for rec in recs)]
        grids = [interp_curve({t: v[0] for t, v in prod_curves[(cid, p, prod)].items()}) for cid in cids]
        for t in MED_GRID:
            curve_rows.append(dict(company="Peer median", period=p, product=prod, tenor=t,
                                   dr=round(statistics.median(g[t - 1] for g in grids), 3)))
    write("product_points.csv", points)
    with open(os.path.join(HERE, "anomalies.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["company_id", "period", "region", "lob", "tenor", "filed", "reason"])
        w.writeheader()
        w.writerows(anomalies)
    write("product_curves.csv", curve_rows)

    # Par: each insurer's par discount curve against the dividend scale interest rate it credits policyholders
    par_rows = []
    for label, period_of, year in (("Year end 2025", lambda cid: "2025Q4", "2025"),
                                    ("Latest quarter", lambda cid: latest_p.get(cid), "2026")):
        for cid in NAMES:
            p = period_of(cid)
            pts = filed_par.get((cid, p, "Participating")) if p else None
            if not pts:
                if cid in dsir and label == "Year end 2025":
                    par_rows.append(dict(view=label, company=NAMES[cid], period="", as_at="", curve="No par curve filed",
                                         **{f"dr_{t}y": None for t in PT}, flat_equivalent=None,
                                         dsir=float(dsir[cid]["dsir_" + year]), dsir_less_flat_bp=None))
                continue
            curve = {t: v[0] for t, v in pts.items()}
            fe = flat_equivalent(curve)
            d = float(dsir[cid]["dsir_" + year]) if cid in dsir else None
            par_rows.append(dict(
                view=label, company=NAMES[cid], period=p, as_at=("Oct FY " if cid in OCT_FY else "") + p,
                curve="Par curve (OSFI)" if cid in PRIMARY else "All-products curve (annual report)",
                **{f"dr_{t}y": at(pts, t, 0) for t in PT}, flat_equivalent=fe,
                dsir=d, dsir_less_flat_bp=round((d - fe) * 100) if d is not None else None))
    write("par_vs_dividend_rate.csv", par_rows)

    print(f"{len(rows)} curve points; {len(ye)} companies at 2025Q4; {len(latest)} at latest")


if __name__ == "__main__":
    main()
