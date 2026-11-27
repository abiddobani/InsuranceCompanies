"""Peer discount curve and illiquidity premium comparison, rebuilt on the cdn-life-insurer-alm framework.

Run from the repository root with the ALM repo's uv environment:

    uv run --project ../cdn-life-insurer-alm python analysis/discount_curves/build.py [path/to/cdn-life-insurer-alm]

Inputs (ALM repo, read only)
  data/processed/osfi_long.parquet        OSFI returns; LF2 'RISK FREE RATES and LIQUIDITY PREMIUM BY LINE OF BUSINESS'
                                          (label grammar as scripts/build_osfi_discount_curves.py)
  data/processed/icl_by_line_<fy>q4.csv   insurance contract liabilities in Canada by product line, net of reinsurance
  data/processed/filings_all_long.csv     curve disclosures in annual reports (metric_group = curve)
  data/processed/dfs_curves_2025q4.csv    Desjardins least / most illiquid curves
  deck/alm_peer_deck_v2.json              non-par General Account asset mix by peer (alloc)
Inputs (this repo, fallback where the ALM repo is silent)
  inputs/disclosed_curves_fallback.csv    Beneva and Assumption Life curves from their 2025 annual reports
  inputs/dsir.csv                         dividend scale interest rates (par)
  inputs/par_account_size.csv             par account sizes for insurers with no OSFI par line

ALM repo rules applied (docs: README standing rules, LIMITATIONS L17, docs/DATA.md section 5, scripts/deck3)
  - Canadian business only; non-par General Account lines, with par and seg funds shown separately.
  - Periods by date. RBC Life and BMO Life report at Oct 31; the others at Dec 31.
  - Curves compared on one confirmed basis (spot). RBC Life files 1-year forward rates; they are compounded to spot
    (annual compounding, forwards linear between filed nodes; step as sensitivity): scripts/deck3/rbc_forward_to_spot.py.
  - Premium = discount rate less the filer's own risk-free rate. RBC Life files no risk-free curve; its premium is
    measured against BMO Life's risk-free curve at the same Oct 31 date.
  - Date alignment (scripts/deck3/curve_band.py): Dec 31 peer curves are restated to Oct 31 by keeping each peer's
    premium and replacing its risk-free curve with BMO Life's Oct 31 curve. Years 1 to 30 only.
  - Every estimate is marked (basis columns). Sensitivities are not combined across risks.
"""
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ALM = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else (HERE.parents[2] / "cdn-life-insurer-alm")
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

NODES = [1, 2, 5, 10, 20, 30, 60, 70, 80]
BAND_NODES = [1, 2, 5, 10, 20, 30]
KEY = [1, 5, 10, 20, 30, 80]
GRID = np.arange(1, 81)

# Canonical peer set (README of this repo). OSFI ids and short ids as in the ALM repo (scripts/osfi_common.py).
OSFI = {
    "RBC": ("28395", "RBC Life", 10), "BMO": ("28344", "BMO Life", 10), "MFC": ("28397", "MFC", 12),
    "SLF": ("28429", "SLF", 12), "CLF": ("28386", "CLF", 12), "EMP": ("28375", "Empire Life", 12),
    "IVA": ("28414", "ivari", 12), "EQL": ("28377", "Equitable Life", 12), "COP": ("28368", "Co-operators Life", 12),
    "IOF": ("28432", "Foresters Life", 12), "WAW": ("28434", "Wawanesa Life", 12),
    "CPL": ("28358", "Canadian Premier", 12), "PRI": ("28419", "Primerica Life", 12),
}
# Oct 31 filers outside the peer set: used only as same-date risk-free reference curves
ANCHORS = {"TD": ("28431", "TD Life"), "CIBC": ("28352", "CIBC Life")}
AR = {"IAG": "iA Financial", "DFS": "Desjardins", "BEN": "Beneva", "ASL": "Assumption Life"}
NAMES = {**{k: v[1] for k, v in OSFI.items()}, **AR}
LONG = {"RBC": "RBC Life Insurance Company", "BMO": "BMO Life Assurance Company", "MFC": "The Manufacturers Life Insurance Company",
        "SLF": "Sun Life Assurance Company of Canada", "CLF": "The Canada Life Assurance Company",
        "EMP": "The Empire Life Insurance Company", "IVA": "ivari", "EQL": "The Equitable Life Insurance Company of Canada",
        "COP": "Co-operators Life Insurance Company", "IOF": "Foresters Life Insurance Company (incl. Canada Protection Plan)",
        "WAW": "The Wawanesa Life Insurance Company", "CPL": "Canadian Premier Life Insurance Company",
        "PRI": "Primerica Life Insurance Company of Canada", "IAG": "iA Financial Group (Canadian products)",
        "DFS": "Desjardins Financial Security Life Assurance Company", "BEN": "Beneva", "ASL": "Assumption Life"}
OCT = {s for s, v in OSFI.items() if v[2] == 10}
NO_CURVE = [("Humania", "publishes summary statements only; no discount curve"),
            ("UV Insurance", "publishes summary statements only; no discount curve"),
            ("Canada Protection Plan", "a Foresters business with no separate filing; covered by Foresters Life")]

LINES = {
    "Non-Participating, Individual, Insurance": "Individual insurance",
    "Non-Participating, Individual, Annuity (Excluding Segregated Fund with Guarantees)": "Individual annuity",
    "Non-Participating, Group, Insurance": "Group insurance",
    "Non-Participating, Group, Annuity (Excluding Segregated Fund with Guarantees)": "Group annuity",
    "Participating": "Participating",
    "Non-Participating, Individual, Segregated Fund with Guarantees": "Seg funds (individual)",
}
NONPAR = ["Individual insurance", "Individual annuity", "Group insurance", "Group annuity"]
HEAD = "Individual insurance"
PAT = re.compile(r"RISK FREE RATES and LIQUIDITY PREMIUM BY LINE OF BUSINESS - (CANADA|U\.S\.A\.), Discount Rates applied to "
                 r"the estimates of the future cash flows, - Most Illiquid Bucket only, Year (\d+) \(%\), (.+)$")

# Fiscal year ends compared, as (label, period for Oct filers, period for Dec filers, Oct date, Dec date)
PAIRS = [("fy2023", None, "2023Q4", None, "2023-12-31"),
         ("fy2024", "2024Q4", "2024Q4", "2024-10-31", "2024-12-31"),
         ("fy2025", "2025Q4", "2025Q4", "2025-10-31", "2025-12-31"),
         ("mid2026", "2026Q3", "2026Q2", "2026-07-31", "2026-06-30")]

# Curve basis evidence: the filer's own wording where the ALM repo located it (docs/DATA.md section 5 and filings panels)
BASIS = {
    "RBC": ("forward (est)", "RBC AR 2025 Note 15 p.215: 'current discount yields' 4.3 / 6.0 / 7.3 / 5.1 / 4.1 at 5 / 10 / 20 / 30 years / "
                             "ultimate, equal to the OSFI filing; no spot or forward word. Shape is forward (ALM repo L17)"),
    "CLF": ("spot (filer wording)", "Lifeco AR 2025 p.97: 'spot rates used by the Company to discount liability'; OSFI 30y 5.52 vs disclosed upper end 5.5"),
    "MFC": ("spot (filer wording)", "Manulife AR 2025 Note 12(III): 'spot rates', Canada CAD illiquid 3.85 / 4.94 / 5.36 / 6.10 / 4.40 = OSFI filing"),
    "SLF": ("spot (consistent)", "Sun Life FS 2025 p.69: weighted average CAD curve 30y 5.13, ultimate 4.95; OSFI lines 5.07 to 5.25, ultimate 4.95"),
    "EMP": ("spot (consistent)", "Empire AR 2025 p.54: upper end of range 4.13 / 4.86 / 5.60 / 5.54 / 5.15 = OSFI filing"),
    "EQL": ("spot (consistent)", "Equitable AR 2025 p.42: risk-free plus liquidity premium by year = OSFI filing"),
    "WAW": ("spot in OSFI; forward in FS", "Wawanesa Life FS 2025 p.32 shows 4.72 / 5.87 / 5.82 / 4.91 at 5 / 10 / 20 / 30 years (forward shape); "
                                           "its OSFI filing is 4.12 / 4.83 / 5.41 / 5.38, the spot equivalent"),
}
APPROACH = {
    "RBC": ("top-down", "RBC AR 2025 Note 15"), "CLF": ("top-down where asset-backed; bottom-up otherwise", "Lifeco AR 2025"),
    "SLF": ("bottom-up", "Sun Life FS 2025"), "EMP": ("top-down", "Empire AR 2025"), "EQL": ("bottom-up", "Equitable AR 2025"),
    "WAW": ("bottom-up (Fiera IFRS 17 curve)", "Wawanesa Life FS 2025"), "IOF": ("bottom-up", "Foresters Life FS 2025"),
    "IAG": ("hybrid", "iA AR 2025 Note 14"), "DFS": ("top-down", "Desjardins AR 2025 Note 16"),
}
# What each insurer holds constant in its disclosed interest rate sensitivities (ALM repo docs/METHODOLOGY.md, quotes there)
SENS = {
    "RBC": "ultimate risk-free rate held constant (100 bp parallel shift)",
    "SLF": "ultimate risk-free rate and ultimate liquidity premium held constant; a 10 bp cut in the ultimate risk-free rate is disclosed separately",
    "CLF": "ultimate investment rate not shocked; ultimate illiquidity premium held constant in the spread test",
    "EMP": "ultimate risk-free rate and ultimate illiquidity premium held constant",
    "MFC": "not stated", "EQL": "not stated", "IVA": "not stated",
}


def f(x):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), 3)


def interp(nodes, grid=GRID):
    """Annual curve from {tenor: rate}: linear between nodes, flat outside (ALM repo curve_band convention)."""
    ts = sorted(nodes)
    return np.interp(grid, ts, [nodes[t] for t in ts])


def fwd_to_spot(nodes, method="linear"):
    """1-year forwards at filed nodes -> annual spot curve, annual compounding (ALM repo rbc_forward_to_spot)."""
    ts = sorted(nodes)
    if method == "linear":
        fw = np.interp(GRID, ts, [nodes[t] for t in ts])
    else:
        fw = np.array([nodes[max(t for t in ts if t <= y)] for y in GRID])
    return (np.cumprod(1 + fw / 100) ** (1 / GRID) - 1) * 100


# ----------------------------------------------------------------------------------------------------------------
# 1. OSFI curves
# ----------------------------------------------------------------------------------------------------------------
d = pd.read_parquet(ALM / "data/processed/osfi_long.parquet", columns=["id", "dpa", "per", "label", "value_num", "src"])
d["id"] = d.id.astype(str)
c = d[(d.src == "lf2") & d.label.str.contains("RISK FREE RATES and LIQUIDITY PREMIUM", na=False)].copy()
p = c.label.str.extract(PAT)
assert p[0].notna().all(), "unparsed curve labels"
c["region"], c["tenor"], c["bucket"] = p[0], p[1].astype(int), p[2].str.strip()
c = c[(c.region == "CANADA") & c.value_num.notna() & ~c.label.str.contains("prior", case=False)]
ids = {v[0]: k for k, v in {**OSFI, **ANCHORS}.items()}
c = c[c.id.isin(ids)].copy()
c["sid"] = c.id.map(ids)


def measure(bucket):
    if bucket == "Risk Free Rates":
        return "rf", None
    for suf, m in ((", Liquidity Premium", "lp"), (", Discount Rates", "dr")):
        if bucket.endswith(suf):
            return m, LINES.get(bucket[: -len(suf)])
    return None, None


c[["m", "line"]] = c.bucket.apply(lambda b: pd.Series(measure(b)))
c = c[c.m.notna() & ((c.m == "rf") | c.line.notna())].drop_duplicates(["sid", "per", "m", "line", "tenor"])


def nodes(sid, per, m, line=None):
    x = c[(c.sid == sid) & (c.per == per) & (c.m == m)]
    x = x[x.line == line] if line else x
    return {int(t): float(v) for t, v in zip(x.tenor, x.value_num)}


def osfi_curve(sid, per, line):
    """Filed curve for one line. Returns dict(rf, lp, dr, filed, basis) of {tenor: rate}, or None if not filed.
    DR = RF + LP or LP = DR - RF, over the filer's own risk-free curve."""
    rf, lp, dr = nodes(sid, per, "rf"), nodes(sid, per, "lp", line), nodes(sid, per, "dr", line)
    if not lp and not dr:
        return None
    if sid == "RBC":
        flat = max(dr.values()) - min(v for t, v in dr.items() if t != 70) <= 1.0 and line == "Participating"
        if flat:  # RBC par before fiscal Q4 2025: one flat rate, used as filed (stray 70y point ignored)
            body = {t: v for t, v in dr.items() if abs(v - np.median(list(dr.values()))) <= 0.5}
            return dict(rf={}, lp={}, dr=body, filed=dr, basis="spot (flat rate as filed)")
        spot = fwd_to_spot(dr)
        return dict(rf={}, lp={}, dr={t: float(spot[t - 1]) for t in NODES}, filed=dr, basis="spot from filed 1-year forwards (est)",
                    grid=spot, grid_step=fwd_to_spot(dr, "step"))
    if dr and len(dr) >= 6:
        out_lp = {t: dr[t] - rf[t] for t in dr if t in rf}
        return dict(rf=rf, lp=out_lp, dr=dr, filed=dr, basis="spot as filed")
    out_dr = {t: rf[t] + lp[t] for t in lp if t in rf}
    return dict(rf=rf, lp=lp, dr=out_dr, filed=lp, basis="spot (risk-free plus filed premium)")


# ----------------------------------------------------------------------------------------------------------------
# 2. Annual-report curves (insurers not filing with OSFI)
# ----------------------------------------------------------------------------------------------------------------
ar = {}  # (sid, date, bucket) -> {tenor: rate}
fl = pd.read_csv(ALM / "data/processed/filings_all_long.csv", low_memory=False)
fl = fl[fl.metric_group == "curve"]
for _, r in fl[(fl.company == "iA Financial Group") & (fl.scope == "canada_segment")].iterrows():
    m = re.match(r"(Least|Most) illiquid curve - (\d+) year", str(r.source_item))
    if m and pd.notna(r.amount):
        ar.setdefault(("IAG", str(r.as_of_date)[:10], m.group(1).lower()), {})[int(m.group(2))] = float(r.amount)
for _, r in fl[fl.company == "Desjardins"].iterrows():
    m = re.match(r"(Least|Most) illiquid - (\d+) year", str(r.source_item))
    if m and pd.notna(r.amount):
        ar.setdefault(("DFS", str(r.as_of_date)[:10], m.group(1).lower()), {})[int(m.group(2))] = float(r.amount)
with open(HERE / "inputs/disclosed_curves_fallback.csv", encoding="utf-8") as fh:
    for r in csv.DictReader(fh):
        sid = {"beneva": "BEN", "assumption_life": "ASL"}[r["company_id"]]
        t = 70 if r["tenor"] == "ult" else int(r["tenor"])
        ar.setdefault((sid, r["as_at"], r["bucket"].split("_")[0]), {})[t] = float(r["rate_pct"])
AR_SOURCE = {"IAG": "iA AR 2025 Note 14 p.175 (ALM repo filings panel)", "DFS": "Desjardins AR 2025 Note 16 p.222 (ALM repo filings panel)",
             "BEN": "Beneva AR 2025 p.50 (earlier analysis; checked against the ALM repo's copy)", "ASL": "Assumption Life AR 2025 p.54 (earlier analysis)"}
for (sid, dt, b), pts in ar.items():
    assert {1, 5, 10, 20, 30, 70} <= set(pts), (sid, dt, b, pts)

# ----------------------------------------------------------------------------------------------------------------
# 3. Assemble curves per fiscal year end
# ----------------------------------------------------------------------------------------------------------------
curves = {}   # (pair, sid, line) -> dict
rf_med = {}   # pair -> {tenor: median risk-free of Dec 31 OSFI peers}
for tag, per_oct, per_dec, d_oct, d_dec in PAIRS:
    dec = [s for s in OSFI if s not in OCT]
    rfs = {s: nodes(s, per_dec, "rf") for s in dec}
    rf_med[tag] = {t: float(np.median([r[t] for r in rfs.values() if t in r])) for t in NODES}
    for sid in OSFI:
        per = per_oct if sid in OCT else per_dec
        if per is None:
            continue
        for line in LINES.values():
            cv = osfi_curve(sid, per, line)
            if cv:
                cv.update(as_at=d_oct if sid in OCT else d_dec, source="OSFI LF2", period=per)
                curves[(tag, sid, line)] = cv
    for sid in AR:
        pts = ar.get((sid, d_dec, "most"))
        if not pts:
            continue
        g = interp(pts)
        med = interp(rf_med[tag])
        dr = {**{t: pts[t] for t in pts if t != 70}, 70: pts[70], 80: pts[70]}
        cv = dict(rf={}, dr=dr, filed=pts, lp={t: float(dr[t] - med[t - 1]) for t in dr}, basis="spot (annual report, most illiquid curve)",
                  lp_basis="est: over the median Dec 31 risk-free curve of the OSFI filers", as_at=d_dec, source=AR_SOURCE[sid], period=tag)
        for line in NONPAR + ["Participating"]:  # annual-report insurers publish one curve for all products
            curves[(tag, sid, line)] = cv

# RBC premium: over BMO Life's same-date risk-free curve (ALM repo L17); alternatives kept for the reference check
anchor_rows = []
for tag, per_oct, per_dec, d_oct, d_dec in PAIRS:
    if per_oct is None:
        continue
    refs = {"BMO Life (ALM repo basis)": nodes("BMO", per_oct, "rf"), "TD Life": nodes("TD", per_oct, "rf"), "CIBC Life": nodes("CIBC", per_oct, "rf")}
    refs = {k: v for k, v in refs.items() if len(v) >= 6}
    if len(refs) == 3:
        refs["Median of the three"] = {t: float(np.median([v[t] for v in refs.values() if t in v])) for t in BAND_NODES}
    # RBC's own seg fund curve, forwards to spot: near risk-free, a cross-check on the level of the reference curve
    seg = nodes("RBC", per_oct, "dr", "Seg funds (individual)")
    segspot = fwd_to_spot(seg) if seg else None
    rbc = curves.get((tag, "RBC", HEAD))
    for name, rf in refs.items():
        for t in BAND_NODES:
            anchor_rows.append(dict(pair=tag, as_at=d_oct, reference=name, tenor=t, risk_free=f(rf.get(t)),
                                    rbc_spot=f(rbc["dr"][t]) if rbc else None,
                                    rbc_premium=f(rbc["dr"][t] - rf[t]) if rbc and t in rf else None))
    if segspot is not None:
        for t in BAND_NODES:
            anchor_rows.append(dict(pair=tag, as_at=d_oct, reference="RBC Life seg fund curve, spot (est)", tenor=t, risk_free=f(segspot[t - 1]),
                                    rbc_spot=f(rbc["dr"][t]), rbc_premium=f(rbc["dr"][t] - segspot[t - 1])))
    bmo_rf = refs["BMO Life (ALM repo basis)"]
    for line in LINES.values():
        cv = curves.get((tag, "RBC", line))
        if cv:
            cv["lp"] = {t: cv["dr"][t] - bmo_rf[t] for t in cv["dr"] if t in bmo_rf and t <= 30}
            cv["lp_basis"] = "est: over BMO Life's risk-free curve at the same Oct 31 date (ALM repo L17)"
pd.DataFrame(anchor_rows).to_csv(OUT / "reference_curve_check.csv", index=False)

# Oct 31 alignment for Dec 31 peers (years 1 to 30): BMO Oct 31 risk-free + the peer's own premium
for tag, per_oct, per_dec, d_oct, d_dec in PAIRS:
    if per_oct is None:
        continue
    bmo_rf = nodes("BMO", per_oct, "rf")
    for (tg, sid, line), cv in curves.items():
        if tg != tag:
            continue
        if sid in OCT:
            cv["aligned"] = {t: cv["dr"][t] for t in BAND_NODES if t in cv["dr"]}
        else:
            cv["aligned"] = {t: bmo_rf[t] + cv["lp"][t] for t in BAND_NODES if t in cv["lp"] and t in bmo_rf}

# ----------------------------------------------------------------------------------------------------------------
# 4. Liabilities by line, net of reinsurance (ALM repo icl_by_line; same OSFI LF3 codes for the two filers it omits)
# ----------------------------------------------------------------------------------------------------------------
icl = pd.read_csv(ALM / "data/processed/icl_by_line_2025q4.csv")
size = {(r.entity, r.product_line): r.net_k / 1e6 for r in icl.itertuples()}
size_basis = {s: "ALM repo icl_by_line_2025q4.csv (OSFI LF3 P2201, Canada, net of reinsurance)" for s in icl.entity.unique()}
LF3 = [("Individual insurance", "P2201002501", "P2201003501"), ("Individual annuity", "P2201005501", "P2201006501"),
       ("Group insurance", "P2201012501", "P2201013501"), ("Group annuity", "P2201015501", "P2201016501"),
       ("Participating", "P2201051001", "P2201053001")]
for sid in ("CPL", "PRI"):
    r = d[(d.id == OSFI[sid][0]) & (d.per == "2025Q4") & ~d.label.str.contains("prior", case=False, na=False)].drop_duplicates("dpa").set_index("dpa").value_num
    g = lambda k: float(r.get(k, 0) or 0)
    bs = g("P3507518001") - g("P3507545901")
    sign = 1 if abs(g("P2201086901") - bs) <= abs(-g("P2201086901") - bs) else -1
    for line, iss, rei in LF3:
        if g(iss) or g(rei):
            size[(sid, line)] = (g(iss) - sign * g(rei)) / 1e6
    size[(sid, "Segregated funds (insurance contracts)")] = g("P3507537001") / 1e6
    if g("P3507537001") and (sid, "Individual annuity") in size:
        size[(sid, "Individual annuity")] -= g("P3507537001") / 1e6
    size_basis[sid] = "OSFI LF3 P2201 Canada column, net of reinsurance, same codes as the ALM repo (computed here)"
SEGKEY = "Segregated funds (insurance contracts)"


def liab(sid, line):
    v = size.get((sid, SEGKEY if line.startswith("Seg") else line))
    return None if v is None or not np.isfinite(v) or abs(v) < 0.0005 else float(v)


def nonpar_total(sid):
    vals = [liab(sid, ln) for ln in NONPAR]
    return sum(v for v in vals if v) if any(vals) else None


# ----------------------------------------------------------------------------------------------------------------
# 5. Outputs
# ----------------------------------------------------------------------------------------------------------------
ORDER = sorted(list(OSFI) + list(AR), key=lambda s: (-(nonpar_total(s) or -1), NAMES[s]))

# 5a. every curve point
rows = []
for (tag, sid, line), cv in curves.items():
    for t in sorted(cv["dr"]):
        rows.append(dict(pair=tag, id=sid, insurer=NAMES[sid], as_at=cv["as_at"], line=line, tenor=t, discount_rate=f(cv["dr"][t]),
                         as_filed=f(cv["filed"].get(t if t != 80 or 80 in cv["filed"] else 70)), risk_free=f(cv["rf"].get(t)),
                         premium=f(cv["lp"].get(t)), aligned_oct31=f(cv.get("aligned", {}).get(t)), basis=cv["basis"],
                         premium_basis=cv.get("lp_basis", "over the filer's own risk-free curve"), source=cv["source"]))
pd.DataFrame(rows).to_csv(OUT / "curves.csv", index=False)

# 5b. headline table, fiscal 2025
rows = []
for sid in ORDER:
    cv = curves.get(("fy2025", sid, HEAD))
    if not cv:
        continue
    r = dict(id=sid, insurer=NAMES[sid], entity=LONG[sid], as_at=cv["as_at"], source=cv["source"], nonpar_liabilities_bn=f(nonpar_total(sid)),
             line_liabilities_bn=f(liab(sid, HEAD)))
    for t in KEY:
        r[f"dr_{t}y"] = f(cv["dr"].get(t))
    for t in KEY:
        r[f"lp_{t}y"] = f(cv["lp"].get(t))
    r["rf_30y"] = f(cv["rf"].get(30))
    r["aligned_30y"] = f(cv.get("aligned", {}).get(30))
    r["aligned_10y"] = f(cv.get("aligned", {}).get(10))
    r["basis"] = cv["basis"]
    r["premium_basis"] = cv.get("lp_basis", "over the filer's own risk-free curve")
    r["approach"], r["approach_source"] = APPROACH.get(sid, ("not captured", ""))
    rows.append(r)
head = pd.DataFrame(rows)
peers = head[head.id != "RBC"]
med = {"id": "MEDIAN", "insurer": "Peer median", "entity": f"Median of {len(peers)} peers (RBC Life excluded)"}
for col in head.columns:
    if col.startswith(("dr_", "lp_", "rf_", "aligned_")):
        med[col] = f(peers[col].median())
head = pd.concat([pd.DataFrame([med]), head], ignore_index=True)
head.to_csv(OUT / "headline_fy2025.csv", index=False)

# 5c. by product line, fiscal 2025 (30-year and 10-year points), with liability-weighted non-par premium
rows = []
for sid in ORDER:
    for line in LINES.values():
        cv = curves.get(("fy2025", sid, line))
        if not cv:
            continue
        r = dict(id=sid, insurer=NAMES[sid], as_at=cv["as_at"], line=line, liabilities_bn=f(liab(sid, line)), basis=cv["basis"],
                 premium_basis=cv.get("lp_basis", "over the filer's own risk-free curve"),
                 all_products_curve="Y" if sid in AR else "N")
        for t in KEY:
            r[f"dr_{t}y"] = f(cv["dr"].get(t))
        for t in KEY:
            r[f"lp_{t}y"] = f(cv["lp"].get(t))
        r["aligned_30y"] = f(cv.get("aligned", {}).get(30))
        rows.append(r)
byline = pd.DataFrame(rows)
for line in LINES.values():
    x = byline[(byline.line == line) & (byline.id != "RBC")]
    if line in ("Participating", "Seg funds (individual)"):
        x = x[x.all_products_curve == "N"]
    m = dict(id="MEDIAN", insurer="Peer median", line=line, as_at=f"Median of {len(x)} peers")
    for col in byline.columns:
        if col.startswith(("dr_", "lp_", "aligned_")):
            m[col] = f(x[col].median())
    byline = pd.concat([byline, pd.DataFrame([m])], ignore_index=True)
byline.to_csv(OUT / "by_line_fy2025.csv", index=False)

rows = []
for sid in ORDER:
    num = den = 0.0
    used = []
    for line in NONPAR:
        cv, w = curves.get(("fy2025", sid, line)), liab(sid, line)
        if cv and w and cv["lp"].get(30) is not None and sid not in AR:
            num += w * cv["lp"][30]
            den += w
            used.append(line)
    cv = curves.get(("fy2025", sid, HEAD))
    if cv is None:
        continue
    rows.append(dict(id=sid, insurer=NAMES[sid], nonpar_liabilities_bn=f(nonpar_total(sid)),
                     weighted_premium_30y=f(num / den) if den else f(cv["lp"].get(30)),
                     weighting="liability-weighted over " + ", ".join(used) if den else "single all-products curve (no liability split by line)",
                     **{f"share_{ln.lower().replace(' ', '_')}": f((liab(sid, ln) or 0) / nonpar_total(sid)) if nonpar_total(sid) else None for ln in NONPAR}))
weighted = pd.DataFrame(rows)
weighted.to_csv(OUT / "weighted_premium_fy2025.csv", index=False)

# 5d. like-for-like band, years 1 to 30 (ALM repo curve_band), for each line and pair
rows = []
for tag, per_oct, per_dec, d_oct, d_dec in PAIRS:
    if per_oct is None:
        continue
    for line in NONPAR + ["Participating"]:
        rbc = curves.get((tag, "RBC", line))
        A, F, used = [], [], []
        for sid in ORDER:
            cv = curves.get((tag, sid, line))
            if sid == "RBC" or not cv or len(cv.get("aligned", {})) < 6:
                continue
            if line == "Participating" and sid in AR:
                continue
            A.append(np.interp(np.arange(1, 31), BAND_NODES, [cv["aligned"][t] for t in BAND_NODES]))
            F.append(interp(cv["dr"], np.arange(1, 31)))
            used.append(sid)
        if not A:
            continue
        A, F = np.array(A), np.array(F)
        for i, t in enumerate(range(1, 31)):
            rows.append(dict(pair=tag, rbc_date=d_oct, peer_date=d_dec, line=line, tenor=t,
                             rbc_spot=f(rbc["grid"][i]) if rbc and "grid" in rbc else (f(interp(rbc["dr"], [t])[0]) if rbc else None),
                             rbc_spot_step=f(rbc["grid_step"][i]) if rbc and "grid_step" in rbc else None,
                             rbc_filed_forward=f(np.interp(t, sorted(rbc["filed"]), [rbc["filed"][k] for k in sorted(rbc["filed"])])) if rbc and "grid" in rbc else None,
                             peer_median=f(np.median(A[:, i])), peer_min=f(A[:, i].min()), peer_max=f(A[:, i].max()),
                             peer_median_as_filed=f(np.median(F[:, i])), n_peers=len(used), peers="|".join(used)))
band = pd.DataFrame(rows)
band.to_csv(OUT / "band.csv", index=False)

# 5e. full annual curves 1 to 80 as filed (spot), fiscal 2025, for the curve charts
rows = []
for line in NONPAR + ["Participating"]:
    G = []
    for sid in ORDER:
        cv = curves.get(("fy2025", sid, line))
        if not cv or (line == "Participating" and sid in AR):
            continue
        g = cv["grid"] if "grid" in cv else interp(cv["dr"])
        if sid != "RBC":
            G.append(g)
        for t in GRID:
            rows.append(dict(line=line, id=sid, insurer=NAMES[sid], tenor=int(t), rate=f(g[t - 1]), kind="annual report" if sid in AR else "OSFI filer"))
    Gm = np.median(np.array(G), axis=0)
    for t in GRID:
        rows.append(dict(line=line, id="MEDIAN", insurer="Peer median", tenor=int(t), rate=f(Gm[t - 1]), kind="median"))
pd.DataFrame(rows).to_csv(OUT / "curves_annual_fy2025.csv", index=False)

# 5f. ultimate assumptions (year 80; annual-report insurers at year 70)
rows = []
for sid in ORDER:
    cv = curves.get(("fy2025", sid, HEAD))
    if not cv:
        continue
    filed_ult = cv["filed"].get(80, cv["filed"].get(70))
    shape = cv["filed"] if sid == "RBC" or sid in AR else cv["dr"]   # the curve as the filer reports it
    rows.append(dict(id=sid, insurer=NAMES[sid], ultimate_risk_free=f(cv["rf"].get(80)),
                     ultimate_premium=f(cv["lp"].get(80)) if sid in OSFI and sid != "RBC" else None,
                     ultimate_rate=f(cv["rf"][80] + cv["lp"][80]) if sid in OSFI and sid != "RBC" else f(filed_ult),
                     ultimate_note="filed ultimate forward rate; split not filed" if sid == "RBC" else ("annual report, year 70; split not disclosed" if sid in AR else ""),
                     spot_80y=f(cv["dr"].get(80)), approach=APPROACH.get(sid, ("not captured", ""))[0],
                     approach_source=APPROACH.get(sid, ("", ""))[1], sensitivity_treatment=SENS.get(sid, "not in the ALM repo's sensitivity set"),
                     basis_evidence=BASIS.get(sid, ("spot (not stated by filer)", "no curve-basis wording located; shape consistent with spot"))[0],
                     basis_note=BASIS.get(sid, ("", "no curve-basis wording located in the ALM repo's filings; smooth shape, consistent with spot"))[1],
                     hump_max_less_ultimate=f(max(shape.values()) - shape.get(80, shape.get(70))),
                     min_beyond_30y=f(min([v for t, v in shape.items() if t > 30] or [np.nan]))))
pd.DataFrame(rows).to_csv(OUT / "ultimates_and_basis.csv", index=False)

# 5g. most vs least illiquid curves where disclosed
rows = []
for sid in AR:
    mo, le = ar.get((sid, "2025-12-31", "most")), ar.get((sid, "2025-12-31", "least"))
    for t in (1, 5, 10, 20, 30, 70):
        rows.append(dict(id=sid, insurer=NAMES[sid], tenor=t, most=mo[t], least=le[t], spread=f(mo[t] - le[t]), source=AR_SOURCE[sid]))
eq = fl[(fl.company.str.startswith("The Equitable")) & (fl.period == "FY2025")]
for t in (1, 5, 10, 20, 30, 70):
    g = lambda k: float(eq[eq.source_item == f"{k} - Year {t}"].amount.iloc[0])
    rfv, mo, le = g("Risk-free rate"), g("Liquidity premium, most illiquid"), g("Liquidity premium, least illiquid")
    rows.append(dict(id="EQL", insurer=NAMES["EQL"], tenor=t, most=f(rfv + mo), least=f(rfv + le), spread=f(mo - le), source="Equitable AR 2025 p.42 (ALM repo filings panel)"))
mf = fl[(fl.company == "Manulife") & (fl.scope == "canada_segment") & (fl.period == "FY2025")]
for t, lab in ((1, "1 year"), (5, "5 years"), (10, "10 years"), (20, "20 years"), (30, "30 years"), (70, "Ultimate")):
    g = lambda k: float(mf[mf.source_item == f"Spot discount rate, Canada CAD {k}, {lab}"].amount.iloc[0])
    rows.append(dict(id="MFC", insurer=NAMES["MFC"], tenor=t, most=g("Illiquid"), least=g("Somewhat liquid"), spread=f(g("Illiquid") - g("Somewhat liquid")),
                     source="Manulife AR 2025 Note 12(III): illiquid vs somewhat liquid (ALM repo filings panel)"))
em = fl[(fl.company.str.startswith("The Empire")) & (fl.period == "FY2025")]
for t, lab in ((1, "1 year"), (5, "5 years"), (10, "10 years"), (20, "20 years"), (30, "30 years"), (70, "Ultimate (year 70)")):
    g = lambda k: float(em[em.source_item == f"Discount rate range, portfolio duration {lab} - {k}"].amount.iloc[0])
    rows.append(dict(id="EMP", insurer=NAMES["EMP"], tenor=t, most=g("upper"), least=g("lower"), spread=f(g("upper") - g("lower")),
                     source="Empire AR 2025 p.54: upper and lower end of range across portfolios (ALM repo filings panel)"))
lc = fl[(fl.company == "Great-West Lifeco") & (fl.period == "FY2025")]
for t in (1, 5, 10, 20, 30):
    g = lambda k: float(lc[lc.source_item == f"Spot discount rate, CAD, Year {t}, {k} end of range"].amount.iloc[0])
    rows.append(dict(id="CLF", insurer=NAMES["CLF"], tenor=t, most=g("upper"), least=g("lower"), spread=f(g("upper") - g("lower")),
                     source="Lifeco AR 2025 p.97: CAD spot rate range across products, group level (ALM repo filings panel)"))
pd.DataFrame(rows).to_csv(OUT / "liquidity_buckets_fy2025.csv", index=False)

# 5h. par: dividend scale interest rate as the discount rate (earlier method; the ALM repo has no par discount method)
dsir = {r["company_id"]: r for r in csv.DictReader(open(HERE / "inputs/dsir.csv", encoding="utf-8"))}
parsz = {r["company_id"]: r for r in csv.DictReader(open(HERE / "inputs/par_account_size.csv", encoding="utf-8"))}
OLD = {"RBC": "rbc_life", "MFC": "manulife", "SLF": "sun_life", "CLF": "canada_life", "EMP": "empire_life", "EQL": "equitable_life",
       "COP": "cooperators_life", "IOF": "foresters_life", "IAG": "ia", "DFS": "desjardins", "ASL": "assumption_life"}
rows = []
for sid in ORDER:
    cv = curves.get(("fy2025", sid, "Participating"))
    ds = dsir.get(OLD.get(sid, ""), {}).get("dsir_2025")
    ds = float(ds) if ds else None
    if not cv and ds is None:
        continue
    own_par = sid in OSFI and cv is not None
    # The dividend scale rate is one flat rate for the year, so the par premium is measured at one date for everyone:
    # own Dec 31 risk-free where filed, otherwise the Dec 31 median of the OSFI filers (Oct 31 filers included).
    own_rf = cv["rf"].get(30) if cv and cv["rf"] and sid not in OCT else None
    rf30 = own_rf if own_rf is not None else rf_med["fy2025"][30]
    par_bn, par_src = liab(sid, "Participating"), "OSFI LF3 par liabilities, net (ALM repo)"
    if par_bn is None:
        v = parsz.get(OLD.get(sid, ""), {}).get("par_account_mm")
        par_bn, par_src = (float(v) / 1e3, "par account size published for advisors (earlier analysis)") if v else (None, "not published")
    rows.append(dict(id=sid, insurer=NAMES[sid], as_at=cv["as_at"] if cv else "2025-12-31", par_liabilities_bn=f(par_bn), par_size_source=par_src,
                     dividend_scale_rate=ds, risk_free_30y=f(rf30),
                     risk_free_basis="own Dec 31 risk-free" if own_rf is not None else "est: median Dec 31 risk-free of the OSFI filers",
                     par_premium_30y=f(ds - rf30) if ds is not None else None,
                     filed_curve="par curve (OSFI)" if own_par else ("all-products curve (annual report)" if cv else "no par curve filed"),
                     **{f"filed_{t}y": f(cv["dr"].get(t)) if cv else None for t in KEY},
                     filed_premium_30y=f(cv["lp"].get(30)) if cv else None,
                     gap_bp_30y=f((ds - cv["dr"][30]) * 100) if cv and ds is not None else None,
                     basis=cv["basis"] if cv else ""))
par = pd.DataFrame(rows).sort_values("par_liabilities_bn", ascending=False, na_position="last")
par.to_csv(OUT / "par_fy2025.csv", index=False)

# 5i. premium against the asset mix: private fixed income share of the non-par General Account (ALM repo deck v2 alloc)
alloc = json.load(open(ALM / "deck/alm_peer_deck_v2.json"))["alloc"]
rows = []
for sid, v in alloc.items():
    if sid not in OSFI:
        continue
    tot = sum(a["nonpar"] for a in v["l3"].values())
    priv = sum(a["nonpar"] for a in v["l3"].values() if a["l2"] == "Private Fixed Income")
    gov = v["l3"].get("Government Bonds", {}).get("nonpar", 0.0)
    w = weighted[weighted.id == sid].iloc[0]
    hd = head[head.id == sid].iloc[0]
    rows.append(dict(id=sid, insurer=NAMES[sid], nonpar_assets_bn=f(tot / 1e3), private_fixed_income_pct=f(100 * priv / tot),
                     government_bonds_pct=f(100 * gov / tot), premium_30y=f(hd.lp_30y), weighted_premium_30y=f(w.weighted_premium_30y),
                     premium_10y=f(hd.lp_10y), mix_basis=v.get("basis_note", ""),
                     estimate="Y" if "global" in v.get("basis_note", "") or "est" in v.get("basis_note", "") else "N"))
pd.DataFrame(rows).to_csv(OUT / "premium_vs_asset_mix.csv", index=False)

# 5j. trend at fiscal year ends: 30-year and 10-year premium, individual insurance
rows = []
for tag, per_oct, per_dec, d_oct, d_dec in PAIRS:
    for t in (10, 30):
        vals = {sid: curves[(tag, sid, HEAD)]["lp"].get(t) for sid in ORDER if sid != "RBC" and sid in OSFI and (tag, sid, HEAD) in curves}
        vals = {k: v for k, v in vals.items() if v is not None}
        rbc = curves.get((tag, "RBC", HEAD))
        rows.append(dict(pair=tag, peer_date=d_dec, rbc_date=d_oct, tenor=t, peer_median=f(np.median(list(vals.values()))),
                         peer_min=f(min(vals.values())), peer_max=f(max(vals.values())), n_peers=len(vals),
                         rbc_premium=f(rbc["lp"].get(t)) if rbc else None, rbc_spot=f(rbc["dr"].get(t)) if rbc else None,
                         rbc_filed_forward=f(rbc["filed"].get(t)) if rbc else None,
                         bmo_risk_free=f(nodes("BMO", per_oct, "rf").get(t)) if per_oct else None,
                         td_risk_free=f(nodes("TD", per_oct, "rf").get(t)) if per_oct else None,
                         rbc_premium_vs_td=f(rbc["dr"][t] - nodes("TD", per_oct, "rf")[t]) if rbc else None,
                         peer_median_risk_free=f(rf_med[tag][t]), peer_median_rate=f(np.median([curves[(tag, s, HEAD)]["dr"][t] for s in vals]))))
pd.DataFrame(rows).to_csv(OUT / "trend.csv", index=False)

# 5k. RBC forward to spot, all nodes (base and step), fiscal 2024 and 2025
rows = []
for tag in ("fy2024", "fy2025", "mid2026"):
    cv = curves.get((tag, "RBC", HEAD))
    for t in GRID:
        rows.append(dict(pair=tag, as_at=cv["as_at"], tenor=int(t), filed_forward=f(interp(cv["filed"])[t - 1]),
                         filed_node="Y" if int(t) in cv["filed"] else "N", spot_linear=f(cv["grid"][t - 1]), spot_step=f(cv["grid_step"][t - 1])))
pd.DataFrame(rows).to_csv(OUT / "rbc_forward_to_spot.csv", index=False)

pd.DataFrame([dict(insurer=n, status=s) for n, s in NO_CURVE]).to_csv(OUT / "not_covered.csv", index=False)

# ----------------------------------------------------------------------------------------------------------------
# 6. Checks against the ALM repo's own figures
# ----------------------------------------------------------------------------------------------------------------
rbc25 = curves[("fy2025", "RBC", HEAD)]
assert abs(rbc25["dr"][30] - 5.75) < 0.006, rbc25["dr"][30]              # LIMITATIONS L17: 30y spot 5.75%
assert abs(rbc25["grid_step"][29] - 5.74) < 0.006                         # L17: 5.74% step
assert abs(rbc25["lp"][30] - 2.49) < 0.006, rbc25["lp"][30]              # L17: 2.49% vs BMO risk-free
assert abs(curves[("fy2024", "RBC", HEAD)]["lp"][30] - 1.78) < 0.006      # L17: 2024 1.78%
cb = pd.read_csv(ALM / "data/processed/curve_band_2025.csv")
mine = band[(band.pair == "fy2025") & (band.line == HEAD)].set_index("tenor")
assert np.allclose(cb[cb.pair == "fy2025"].set_index("tenor").rbc_spot, mine.rbc_spot, atol=0.002)
print("checks against ALM repo L17 and curve_band_2025.csv: ok")
print(head[["insurer", "as_at", "nonpar_liabilities_bn", "dr_10y", "dr_30y", "dr_80y", "lp_10y", "lp_30y", "lp_80y", "aligned_30y"]].to_string(index=False))
print(pd.read_csv(OUT / "reference_curve_check.csv").query("pair=='fy2025' and tenor in (10, 30)").to_string(index=False))
