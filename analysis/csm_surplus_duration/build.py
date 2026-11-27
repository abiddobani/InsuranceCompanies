"""CSM and surplus portfolio durations, rebuilt on the cdn-life-insurer-alm study (fiscal 2025 year-ends).

    uv run --project <ALM_REPO> python analysis/csm_surplus_duration/build.py <ALM_REPO>

<ALM_REPO> is a checkout of MooseDragon/cdn-life-insurer-alm (branch main). Every size, block and split comes from
that repo's signed-off outputs and rules; this script only adds the duration layer, which the repo lists as a
next step (README "Next steps" 2 and 3) and which is therefore an estimate throughout.

Rules taken from the ALM repo (docs/METHODOLOGY.md, LIMITATIONS.md, research/):
  - Scope: Canada only, General Account excl. par / seg fund / UL policyholder funds, net of reinsurance.
  - CSM in the General Account is ABL CSM only (CSM excl. par and seg funds); AMF filers: total CSM only (memo).
  - Surplus = equity less "Shareholders' Equity - other" (methodology section 4).
  - L04: assets are not split ABL / CSM / surplus by any filer. Approved workaround: waterfall B (ABL backed by
    fixed income and mortgages; CSM pro rata to the ABL mix; surplus = residual, equity / real estate / others
    first), A where disclosed, C (CSM backed like surplus) as a sensitivity.
  - "A where disclosed": Foresters' segment table; FVOCI + amortized-cost book where the repo's test holds
    (research/synthetic_rbc_benchmark.md 7.6: RBC Life 1.02, Blumont 1.21).
  - CSM run-off: weighted average years, band midpoints, open band at start + 5 (scripts/deck2/build_deck2_data.py).
  - Sensitivities are quoted as disclosed, one risk at a time, never combined.
Outputs: results.csv, portfolio_breakdown.csv, class_durations.csv, csm_runoff.csv, fvoci.csv, oci_history.csv,
sensitivities.csv, changes_vs_v1.csv, parameters.csv, coverage.csv (also copied to dashboard/).
"""
import io
import json
import pathlib
import shutil
import statistics
import sys

import numpy as np
import pandas as pd

from disclosed_inputs import AMF, FORESTERS_SEGMENTS, LIMITS, NOT_REBUILT, V1_ID

HERE = pathlib.Path(__file__).resolve().parent
ALM = pathlib.Path(sys.argv[1]).resolve()
P = ALM / "data/processed"

Y = 0.0425      # flat yield for the band-to-duration conversion (same as the earlier version)
TAX = 0.265     # gross-up for sensitivities disclosed net of tax (ivari: 25.75% as stated)
PERIOD = "2025Q4"
FOCUS = "RBC"

PEERS = ["RBC", "BMO", "MFC", "SLF", "CLF", "EMP", "IVA", "EQL", "COP", "IOF", "WAW", "BLU", "IAG", "BEN", "DFS"]
NAME = {"RBC": "RBC Life", "BMO": "BMO Life", "MFC": "Manulife", "SLF": "Sun Life", "CLF": "Canada Life",
        "EMP": "Empire Life", "IVA": "ivari", "EQL": "Equitable", "COP": "Co-operators Life", "IOF": "Foresters Life",
        "WAW": "Wawanesa Life", "BLU": "Blumont", "IAG": "iA", "BEN": "Beneva", "DFS": "Desjardins"}
OSFI = {"RBC": "28395", "BMO": "28344", "MFC": "28397", "SLF": "28429", "CLF": "28386", "EMP": "28375",
        "IVA": "28414", "EQL": "28377", "COP": "28368", "IOF": "28432", "WAW": "28434", "BLU": "143611"}
OCT = {"RBC", "BMO"}
AMF_IDS = {"IAG", "BEN", "DFS"}
BIG3 = {"MFC", "SLF", "CLF"}

CLASSES = ["Cash and short term", "Government bonds", "Corporate bonds", "Commercial mortgages",
           "Private placements and loans", "Common shares", "Preferred shares", "Real estate", "Others"]
FI = CLASSES[:5]
NONFI = CLASSES[5:]
L3_TO_CLASS = {
    "Cash": "Cash and short term", "Cash Equivalent": "Cash and short term",
    "Government Bonds": "Government bonds",
    "Corporate Bonds": "Corporate bonds", "Asset Backed Securities": "Corporate bonds",
    "Commercial Mortgages": "Commercial mortgages",
    "Illiquid Term Loan": "Private placements and loans", "Private Liquid Loans": "Private placements and loans",
    "Consumer Loans": "Private placements and loans", "Infrastructure Debt": "Private placements and loans",
    "Other Private Debt": "Private placements and loans", "Structured Products": "Private placements and loans",
    "Co-Investments": "Private placements and loans",
    "Common Shares": "Common shares", "Preferred Shares": "Preferred shares",
    "Real Estate Equity": "Real estate",
    "Other Private Equity": "Others", "Infrastructure Equity": "Others", "Other invested (unclassified)": "Others",
}
CASH_D = 0.25


# ----------------------------------------------------------------------------------------------- helpers
def moddur(m, y=Y):
    """Modified duration of a par bullet bond with annual coupon y and term m years."""
    return (1 - (1 + y) ** -m) / y if m > 0 else 0.0


def band_duration(bands, open_add):
    """bands: list of (start, end or None, amount). Closed bands at the midpoint, open band at start + open_add."""
    tot = sum(a for _, _, a in bands)
    if not tot:
        return None
    d = 0.0
    for s, e, a in bands:
        term = (s + e) / 2 if e is not None else s + open_add
        d += a * moddur(term)
    return d / tot


def lbh(bands, kind):
    """(low, base, high) duration for a band table. Bonds and private placements: open band at start + 5 / 10 / 15.
    Mortgages and loans: start + 2.5 / 5 / 10."""
    adds = (5, 10, 15) if kind == "bond" else (2.5, 5, 10)
    return tuple(band_duration(bands, a) for a in adds)


def wal(bands):
    """ALM repo rule for CSM run-off: band midpoints, open band at start + 5."""
    tot = sum(abs(a) for _, _, a in bands)
    return sum(abs(a) * ((s + e) / 2 if e is not None else s + 5) for s, e, a in bands) / tot


def r(x, n=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


# ----------------------------------------------------------------------------------------------- inputs
summ = pd.read_csv(P / "peer_summary_2025q4.csv").set_index("short_id")
alloc = pd.read_csv(P / "deck2_block_allocation_2025fye.csv")
mb = pd.read_csv(P / "deck2_maturity_bands.csv")
mb = mb[mb.band != "Total"]
ro = pd.read_csv(P / "deck2_csm_runoff.csv")
ro = ro[ro.band != "Total"]
sens = pd.read_csv(P / "deck2_sensitivities.csv")
sens = sens[sens.as_of.astype(str).str.startswith("2025")]
deck = json.loads((ALM / "deck/alm_peer_deck_v2.json").read_text())
osfi = pd.read_parquet(P / "osfi_long.parquet")
for c in ("dpa", "id", "per"):
    osfi[c] = osfi[c].astype(str)
osfi = osfi[osfi.id.isin(list(OSFI.values()) + ["28350"])]
fil = pd.read_csv(P / "filings_all_long.csv", low_memory=False)


def ov(sid, per, code, entity=None):
    x = osfi[(osfi.id == (entity or OSFI[sid])) & (osfi.per == per) & (osfi.dpa == code)].value_num
    return float(x.iloc[0]) / 1000 if len(x) else np.nan


def mm(sid, col):
    v = summ.loc[sid, col]
    return None if pd.isna(v) else float(v) / 1000


def bands_of(sid, pick):
    d = mb[mb.peer == sid]
    d = d[pick(d)]
    g = d.groupby(["band_start_yr", "band_end_yr"], dropna=False).value_mm.sum().reset_index()
    return [(float(s), None if pd.isna(e) else float(e), float(a)) for s, e, a in g.itertuples(index=False)]


def sens_avg(sid, measure, contains, shock_bp):
    """Average absolute size of the up and down shock for one disclosed component (C$MM as disclosed)."""
    d = sens[(sens.peer == sid) & (sens.risk == "rates") & (sens.measure == measure)
             & sens.shock.astype(str).str.contains(f"{shock_bp} bps")]
    d = d[d.notes.astype(str).str.contains(contains, regex=False) | d.applied_to.astype(str).str.contains(contains, regex=False)]
    return float(d.value_mm.abs().mean()) if len(d) else None


# ------------------------------------------------------------------------- 1. class durations (whole book)
class_rows = []       # one row per peer x class x book
book = {}             # book[sid][class] = (low, base, high, basis)
surplus_fi = {}       # surplus_fi[sid] = (low, base, high, basis)  duration of surplus-type / FVOCI fixed income


def put(sid, classes, lo_ba_hi, basis, bookname="whole book", source=""):
    for c in classes:
        if bookname == "whole book":
            book.setdefault(sid, {})[c] = (*lo_ba_hi, basis)
        class_rows.append(dict(peer=sid, company=NAME[sid], book=bookname, asset_class=c, duration_low=r(lo_ba_hi[0]),
                               duration=r(lo_ba_hi[1]), duration_high=r(lo_ba_hi[2]), basis=basis, source=source))


st = lambda s: (lambda d: d.asset_type.astype(str).str.startswith(s))
SRC_MB = "ALM repo data/processed/deck2_maturity_bands.csv"

# Manulife (group note 4(h); Canada follows the global mix by the repo's rule)
put("MFC", ["Government bonds"], lbh(bands_of("MFC", lambda d: d.asset_type.str.contains("government and agency")), "bond"),
    "maturity bands (group)", source=SRC_MB + " (MFC FS note 4(h))")
put("MFC", ["Corporate bonds"], lbh(bands_of("MFC", lambda d: d.asset_type.str.contains("Corporate|asset-backed")), "bond"),
    "maturity bands (group)", source=SRC_MB)
put("MFC", ["Commercial mortgages"], lbh(bands_of("MFC", st("Mortgages")), "loan"), "maturity bands (group)", source=SRC_MB)
put("MFC", ["Private placements and loans"], lbh(bands_of("MFC", st("Private placements")), "bond"), "maturity bands (group)", source=SRC_MB)
# Sun Life (group note 6.A.iv)
tot = lambda d: d.accounting_class == "total"
put("SLF", ["Government bonds", "Corporate bonds"], lbh(bands_of("SLF", lambda d: (d.asset_type == "Debt securities") & tot(d)), "bond"),
    "maturity bands (group)", source=SRC_MB + " (SLF FS note 6.A.iv)")
put("SLF", ["Commercial mortgages"], lbh(bands_of("SLF", lambda d: (d.asset_type == "Mortgages") & tot(d)), "loan"), "maturity bands (group)", source=SRC_MB)
put("SLF", ["Private placements and loans"], lbh(bands_of("SLF", lambda d: (d.asset_type == "Loans") & tot(d)), "bond"), "maturity bands (group)", source=SRC_MB)
# Canada Life (Lifeco group note 6(b); bands stop at "over 5 years")
put("CLF", ["Government bonds", "Corporate bonds", "Private placements and loans"], lbh(bands_of("CLF", lambda d: d.asset_type == "Bonds"), "bond"),
    "maturity bands (Lifeco group; open band over 5 years)", source=SRC_MB + " (Lifeco FS note 6(b))")
put("CLF", ["Commercial mortgages"], lbh(bands_of("CLF", st("Mortgage loans")), "loan"), "maturity bands (Lifeco group; open band over 5 years)", source=SRC_MB)
# Equitable (bands stop at "over 5 years")
put("EQL", ["Government bonds"], lbh(bands_of("EQL", lambda d: d.asset_type.str.contains("Government of Canada|Provincial")), "bond"),
    "maturity bands (open band over 5 years)", source=SRC_MB + " (Equitable AR note 4(b))")
put("EQL", ["Corporate bonds"], lbh(bands_of("EQL", lambda d: d.asset_type.str.contains("Corporate")), "bond"), "maturity bands (open band over 5 years)", source=SRC_MB)
put("EQL", ["Commercial mortgages"], lbh(bands_of("EQL", st("Mortgages")), "loan"), "maturity bands (open band over 5 years)", source=SRC_MB)
put("EQL", ["Private placements and loans"], lbh(bands_of("EQL", st("Private placements")), "bond"), "maturity bands (open band over 5 years)", source=SRC_MB)
# ivari
put("IVA", ["Government bonds"], lbh(bands_of("IVA", lambda d: d.asset_type.str.contains("Government")), "bond"), "maturity bands", source=SRC_MB + " (ivari FS)")
put("IVA", ["Corporate bonds", "Private placements and loans"], lbh(bands_of("IVA", lambda d: d.asset_type.str.contains("Corporate")), "bond"), "maturity bands", source=SRC_MB)
put("IVA", ["Commercial mortgages"], lbh(bands_of("IVA", lambda d: d.asset_type.str.contains("Corporate")), "bond"), "maturity bands (corporate bonds; ivari holds no mortgages)", source=SRC_MB)

# Empire: band estimate kept as a check; base is the disclosed sensitivity of debt instruments
emp_b = bands_of("EMP", st("Bonds"))
emp_fv = sum(a for _, _, a in emp_b) / 1000  # C$MM (source in thousands, value_mm already in MM for other peers)
if emp_fv < 100:
    emp_fv = sum(a for _, _, a in emp_b)
emp_band = lbh(emp_b, "bond")
emp_s = sens_avg("EMP", "net_income", "component: financial assets (debt instruments)", 50)
emp_d = emp_s / (1 - TAX) / 0.005 / emp_fv
put("EMP", FI[1:], (emp_d, emp_d, emp_d), "disclosed sensitivity of debt instruments (net of tax, 26.5% assumed)",
    source=f"Empire 2025 FS note 24.2 via ALM repo deck2_sensitivities.csv: +/-50 bps on debt instruments, average C${emp_s:.0f}MM, on bonds at fair value C${emp_fv:,.0f}MM")
put("EMP", ["All bonds"], emp_band, "maturity bands (check)", bookname="check", source=SRC_MB)

# BMO Life: disclosed sensitivity of financial instruments (FVTPL bonds; includes derivatives)
bmo_b = bands_of("BMO", st("Bonds"))
bmo_fv = sum(a for _, _, a in bmo_b)
bmo_s = sens_avg("BMO", "net_income", "component row only: financial instruments", 50)
bmo_d = bmo_s / (1 - TAX) / 0.005 / bmo_fv
bmo_band = lbh(bmo_b, "bond")
put("BMO", FI[1:], (bmo_band[1], bmo_d, bmo_d), "disclosed sensitivity of financial instruments (net of tax, 26.5% assumed; includes derivatives); low case = bond maturity bands alone",
    source=f"BMO Life 2025 FS via ALM repo deck2_sensitivities.csv: +/-50 bps on financial instruments, average C${bmo_s:.0f}MM, on FVTPL bonds C${bmo_fv:,.0f}MM")
put("BMO", ["All bonds"], lbh(bmo_b, "bond"), "maturity bands (check; open band over 5 years)", bookname="check", source=SRC_MB)
bmo_oci = float(sens[(sens.peer == "BMO") & (sens.measure == "oci")].value_mm.abs().mean())
bmo_fvoci = ov("BMO", PERIOD, "P2101247916")          # FVOCI bonds; the rest of the FVOCI book is short-term paper
d_lo, d_hi = bmo_oci / 0.005 / bmo_fvoci, bmo_oci / (1 - TAX) / 0.005 / bmo_fvoci
surplus_fi["BMO"] = (d_lo, d_lo, d_hi, "disclosed OCI sensitivity of FVOCI investments over FVOCI bonds (tax basis not stated; high case = 26.5% gross-up)")
class_rows.append(dict(peer="BMO", company=NAME["BMO"], book="FVOCI book", asset_class="Bonds", duration_low=r(d_lo), duration=r(d_lo), duration_high=r(d_hi),
                       basis=surplus_fi["BMO"][3],
                       source=f"BMO Life 2025 FS: 50 bps moves OCI by about C${bmo_oci:.1f}MM; FVOCI bonds C${bmo_fvoci:,.0f}MM (OSFI LF2)"))

# Wawanesa: disclosed sensitivity of non-participating financial instruments
waw_cf = [x for x in bands_of("WAW", st("Fixed income")) if not np.isnan(x[0])]
waw_s = sens_avg("WAW", "net_income", "Financial instruments: non-participating", 100)

# iA and Beneva: maturity tables from their 2025 annual reports (disclosed_inputs.py)
for sid in ("IAG", "BEN"):
    a = AMF[sid]
    put(sid, ["Government bonds", "Corporate bonds"] + (["Private placements and loans"] if "private_debt" not in a else []),
        lbh(a["bonds"], "bond"), "maturity bands (consolidated)", source=a["bonds_source"])
    if "private_debt" in a:
        put(sid, ["Private placements and loans"], lbh(a["private_debt"], "bond"), "maturity bands (consolidated)", source=a["bonds_source"])
    put(sid, ["Commercial mortgages"], lbh(a["loans"], "loan"), "maturity bands (consolidated)", source=a["bonds_source"])
# Beneva: OCI sensitivity of the FVOCI bonds
b = AMF["BEN"]
d_hi = b["oci_per_1pct"] / (1 - TAX) / 0.01 / b["fvoci_bonds"]
d_lo = b["oci_per_1pct"] / 0.01 / b["fvoci_bonds"]
surplus_fi["BEN"] = (d_lo, d_hi, d_hi, "disclosed OCI sensitivity of FVOCI bonds (tax basis not legible in the report; 26.5% gross-up assumed, low case = none)")
class_rows.append(dict(peer="BEN", company=NAME["BEN"], book="FVOCI book", asset_class="Fixed income", duration_low=r(d_lo), duration=r(d_hi),
                       duration_high=r(d_hi), basis=surplus_fi["BEN"][3], source=b["oci_source"]))
# Sun Life: FVOCI debt maturity bands (company states FVOCI fixed income backs surplus, investment contracts and CSM)
slf_f = lbh(bands_of("SLF", lambda d: (d.asset_type == "Debt securities") & (d.accounting_class == "FVOCI")), "bond")
surplus_fi["SLF"] = (*slf_f, "maturity bands of FVOCI debt securities (group)")
class_rows.append(dict(peer="SLF", company=NAME["SLF"], book="FVOCI book", asset_class="Fixed income", duration_low=r(slf_f[0]), duration=r(slf_f[1]),
                       duration_high=r(slf_f[2]), basis=surplus_fi["SLF"][3],
                       source=SRC_MB + "; SLF 2025 FS note 6: FVOCI fixed income is 'held primarily backing surplus, investment contracts and CSM liabilities'"))
# Foresters: disclosed sensitivities by segment
fs = FORESTERS_SEGMENTS
iof_ins = statistics.mean(fs["insurance_fi_per_1pct"]) / 0.01 / fs["Insurance"]["bonds"]
iof_sur = statistics.mean(fs["surplus_fi_per_1pct"]) / 0.01 / fs["Surplus"]["bonds"]
put("IOF", FI[1:], (iof_ins, iof_ins, iof_ins), "disclosed sensitivity of instruments backing insurance liabilities (pre-tax balance-sheet change)", source=fs["source"])
surplus_fi["IOF"] = (iof_sur, iof_sur, iof_sur, "disclosed sensitivity of surplus financial instruments (pre-tax balance-sheet change)")
class_rows.append(dict(peer="IOF", company=NAME["IOF"], book="Surplus segment", asset_class="Bonds", duration_low=r(iof_sur), duration=r(iof_sur),
                       duration_high=r(iof_sur), basis=surplus_fi["IOF"][3], source=fs["source"]))


# ---------------------------------------------------------- 2. realised OCI sensitivity (OSFI LF1, quarterly)
# OCI on FVOCI bonds each quarter (OSFI LF1, year-to-date lines de-cumulated, assumed net of tax) over the average
# FVOCI bond book, against the change in the Government of Canada 5-year benchmark yield between the same dates.
_txt = (HERE / "boc_benchmark_yields.csv").read_text(encoding="utf-8-sig").split('"OBSERVATIONS"')[1].strip()
BOC = pd.read_csv(io.StringIO(_txt), parse_dates=["date"]).set_index("date").ffill()
BOC.columns = [c.split(".")[2] for c in BOC.columns]


def qend(per, octf):
    yr, q = int(per[:4]), int(per[-1])
    return pd.Timestamp(yr, {1: 1, 2: 4, 3: 7, 4: 10}[q] if octf else q * 3, 1) + pd.offsets.MonthEnd(0)


def y5(per, octf):
    d = qend(per, octf)
    x = BOC[BOC.index <= d]
    return float(x["5YR"].iloc[-1]) if len(x) and (d - x.index[-1]).days < 7 else np.nan


QTRS = [f"{y}Q{q}" for y in (2023, 2024, 2025, 2026) for q in (1, 2, 3, 4)]
oci_rows, realised = [], {}
for sid in ("RBC", "BMO", "SLF", "CLF", "COP", "BLU"):
    octf = sid in OCT
    ytd = {q: ov(sid, q, "P2004214001") for q in QTRS}
    bookv = {q: ov(sid, q, "P2101247916") for q in QTRS}
    eq = {q: ov(sid, q, "P2000469901") for q in QTRS}
    pts = []
    for i, q in enumerate(QTRS):
        if i == 0 or np.isnan(ytd[q]):
            continue
        prev, label, note = QTRS[i - 1], q, ""
        flow = ytd[q] if q.endswith("Q1") else ytd[q] - ytd[prev]
        if sid == "RBC" and q.startswith("2024"):
            # RBC Life's fiscal 2024 interim OCI lines do not de-cumulate (first IFRS 17 / IFRS 9 year): the full year is one observation
            if not q.endswith("Q4"):
                continue
            flow, prev, label, note = ytd[q], "2023Q4", "FY2024", "full fiscal year (interim lines unusable)"
        dy = y5(q, octf) - y5(prev, octf)
        avg = np.nanmean([bookv[q], bookv[prev]]) if not (np.isnan(bookv[q]) and np.isnan(bookv[prev])) else np.nan
        ok = not (np.isnan(flow) or np.isnan(dy) or np.isnan(avg) or avg <= 0)
        ret = flow / (1 - TAX) / avg if ok else np.nan
        imp = -ret / (dy / 100) if ok and abs(dy) >= 0.2 else np.nan
        oci_rows.append(dict(peer=sid, company=NAME[sid], quarter=label, period_end=qend(q, octf).date().isoformat(), note=note,
                             oci_fvoci_bonds_mm=r(flow, 1), fvoci_bonds_mm=r(bookv[q], 0), equity_mm=r(eq[q], 0),
                             oci_pct_of_equity=r(100 * flow / eq[q], 2) if eq[q] and not np.isnan(flow) else None,
                             change_5y_yield_pts=r(dy, 2), oci_return_pretax_pct=r(100 * ret, 2), implied_duration=r(imp, 1)))
        if ok:
            pts.append((dy / 100, ret, label))
    if len(pts) >= 4:
        fit = lambda p: -sum(x * y_ for x, y_, _ in p) / sum(x * x for x, _, _ in p)
        slope = fit(pts)
        ss = sum(y_ * y_ for _, y_, _ in pts)
        r2 = 1 - sum((y_ + slope * x) ** 2 for x, y_, _ in pts) / ss if ss else np.nan
        qonly = [p for p in pts if not p[2].startswith("FY")]
        realised[sid] = dict(slope=slope, n=len(pts), r2=r2, recent=fit(qonly), n_recent=len(qonly),
                             annual=next((-y_ / x for x, y_, l_ in pts if l_.startswith("FY")), None))

# peer evidence on surplus-type fixed income (disclosed only)
evidence = {k: v[1] for k, v in surplus_fi.items()}
PEER_SURPLUS_D = statistics.median(evidence.values())   # BMO Life, Beneva, Sun Life, Foresters
PEER_LO, PEER_HI = min(evidence.values()), max(evidence.values())

# RBC Life: realised OCI sensitivity of its own FVOCI bond book. Base = all clean observations (fiscal 2024 as one
# full-year point, then quarterly); low = the quarters since November 2024 alone; high = fiscal 2024 alone.
x = realised["RBC"]
surplus_fi["RBC"] = (min(x["recent"], x["slope"]), x["slope"], max(x["annual"], PEER_SURPLUS_D),
                     f"realised OCI sensitivity of the FVOCI bond book, OSFI LF1 against the 5-year Canada yield, {x['n']} observations, R2 {x['r2']:.2f} (est, low confidence); "
                     f"low = the {x['n_recent']} quarters since Nov 2024 alone, high = fiscal 2024 alone")
class_rows.append(dict(peer="RBC", company=NAME["RBC"], book="FVOCI and amortized cost book", asset_class="Fixed income",
                       duration_low=r(surplus_fi["RBC"][0]), duration=r(x["slope"]), duration_high=r(surplus_fi["RBC"][2]), basis=surplus_fi["RBC"][3],
                       source="OSFI LF1 P2004214001 (OCI on FVOCI bonds), LF2 P2101247916 (FVOCI bonds); Bank of Canada benchmark bond yields (boc_benchmark_yields.csv)"))
xb = realised.get("BLU")
surplus_fi["BLU"] = (PEER_LO, PEER_SURPLUS_D, max(PEER_HI, xb["slope"]) if xb else PEER_HI,
                     "median of disclosed peer surplus-type books (est; no public financial statements, book is mostly amortized cost); high = realised OCI sensitivity of its small FVOCI bond holding")
class_rows.append(dict(peer="BLU", company=NAME["BLU"], book="FVOCI and amortized cost book", asset_class="Fixed income", duration_low=r(PEER_LO),
                       duration=r(PEER_SURPLUS_D), duration_high=r(surplus_fi["BLU"][2]), basis=surplus_fi["BLU"][3], source="BMO Life, Sun Life, Foresters, Beneva (this file); OSFI LF1 / LF2"))
x = realised["COP"]
surplus_fi["COP"] = (min(x["slope"], x["recent"], PEER_LO), x["slope"], max(x["slope"], PEER_HI),
                     f"realised OCI sensitivity of the FVOCI bond book, OSFI LF1 against the 5-year Canada yield, {x['n']} quarters, R2 {x['r2']:.2f} (est); range = disclosed peer surplus books")
class_rows.append(dict(peer="COP", company=NAME["COP"], book="FVOCI book", asset_class="Fixed income", duration_low=r(surplus_fi["COP"][0]),
                       duration=r(x["slope"]), duration_high=r(surplus_fi["COP"][2]), basis=surplus_fi["COP"][3], source="OSFI LF1 / LF2; Bank of Canada benchmark bond yields"))

# ------------------------------------------------------------------------------ 3. asset mixes
mix_b = {}   # non-par General Account by class (C$MM), waterfall input
for sid in OSFI:
    a = alloc[alloc.peer == sid].assign(c=lambda d: d.l3.map(L3_TO_CLASS))
    v = a.groupby("c").nonpar_seg_ga_k.sum().reindex(CLASSES).fillna(0)
    mix_b[sid] = v / v.sum() * mm(sid, "genacct_k")
for sid, co in (("IAG", "iA Financial Group"), ("BEN", "Beneva")):
    x = fil[(fil.company == co) & (fil.period == "FY2025") & (fil.metric_group == "assets") & fil.l3.isin(L3_TO_CLASS)
            & ~fil.l2.isin(["Encumbered Assets"]) & (fil.block != "Mixed (see block rows)")]
    x = x[(x.nesting == "leaf") | (sid == "BEN")]
    x = x[~x.source_item.astype(str).str.startswith("Derivatives")]
    v = x.assign(c=x.l3.map(L3_TO_CLASS)).groupby("c").amount.sum().reindex(CLASSES).fillna(0)
    mix_b[sid] = v / v.sum() * mm(sid, "genacct_k")

# peer-median whole-book durations for peers with no maturity or sensitivity data (RBC, Co-operators, Blumont)
med = {}
for c in FI[1:]:
    vals = [book[s][c] for s in book if c in book[s]]
    med[c] = tuple(statistics.median(v[i] for v in vals) for i in range(3))
for sid in ("RBC", "COP", "BLU"):
    for c in FI[1:]:
        put(sid, [c], med[c], "peer median by class (est; no public maturity table or sensitivity)", source="median of the peers with whole-book data in this file")
# Wawanesa: disclosed sensitivity of non-participating financial instruments over its non-par bonds; the other
# bound is a Macaulay estimate from its table of undiscounted contractual cash flows (open band at 5 + 10 years)
_w = alloc[(alloc.peer == "WAW") & alloc.l3.isin(["Government Bonds", "Corporate Bonds"])]
waw_fi = float(_w.nonpar_seg_ga_k.sum() + _w.ul_ph_fund_k.sum()) / 1000
waw_lo, waw_d = waw_s / 0.01 / waw_fi, waw_s / (1 - TAX) / 0.01 / waw_fi
_t = lambda s_, e_: (s_ + e_) / 2 if e_ is not None else s_ + 10
waw_cf_d = sum(a_ * _t(s_, e_) / (1 + Y) ** _t(s_, e_) for s_, e_, a_ in waw_cf) / sum(a_ / (1 + Y) ** _t(s_, e_) for s_, e_, a_ in waw_cf) / (1 + Y)
put("WAW", FI[1:], (min(waw_lo, waw_cf_d), waw_d, max(waw_d, waw_cf_d)),
    "disclosed sensitivity of non-participating financial instruments (net of tax, 26.5% assumed); low case = no gross-up or the contractual cash-flow table",
    source=f"Wawanesa Life 2025 FS via ALM repo deck2_sensitivities.csv: +/-100 bps, average C${waw_s:.1f}MM, on non-par bonds C${waw_fi:,.0f}MM (ALM repo block allocation); cash-flow table gives {waw_cf_d:.1f} years")
for sid in book:
    book[sid]["Cash and short term"] = (CASH_D, CASH_D, CASH_D, "assumed 0.25 years")


def fvoci_book(sid, per=PERIOD):
    """FVOCI (col 16) + amortized cost (col 36) holdings by class, OSFI LF2 page 21.012, C$MM."""
    x = osfi[(osfi.id == OSFI[sid]) & (osfi.per == per) & osfi.dpa.str.startswith("P21012")]
    x = x.assign(row=x.dpa.str.slice(6, 9), col=x.dpa.str.slice(9, 11))
    x = x[x.col.isin(["16", "36"])]
    g = lambda rows, cols=("16", "36"): float(x[x.row.isin(rows) & x.col.isin(cols)].value_num.sum()) / 1000
    out = pd.Series(0.0, index=CLASSES)
    out["Cash and short term"] = g(["010"])
    bonds = g(["479"])
    corp = g(["210", "230"])
    priv = g(["410", "430"])
    out["Corporate bonds"] = corp
    out["Private placements and loans"] = priv
    out["Government bonds"] = bonds - corp - priv
    out["Commercial mortgages"] = g(["500"])
    out["Preferred shares"] = g(["599"])
    out["Common shares"] = g(["679"]) - g(["599"])
    out["Real estate"] = g(["750"])
    total = g(["889"])
    out["Others"] = total - out.sum()
    return out, g(["889"], ("16",)), g(["889"], ("36",))


# ------------------------------------------------------------------------------ 4. portfolios
def waterfall(G, S, C, pooled=False):
    """ALM repo L04. B: surplus takes non-fixed-income first, then fixed income pro rata; CSM pro rata to what is left
    (the ABL mix). C (pooled=True): CSM is backed like surplus, so CSM and surplus share one pool."""
    take = S + C if pooled else S
    n = float(G[NONFI].sum())
    s = pd.Series(0.0, index=CLASSES)
    nf = min(take, n)
    if n:
        s[NONFI] = G[NONFI] / n * nf
    s[FI] = G[FI] / G[FI].sum() * (take - nf)
    if pooled:
        return s * (S / take), s * (C / take)
    rest = G - s
    return s, rest / rest.sum() * C


def dur_of(port, dmap, k):
    """Portfolio duration: weights x class durations. dmap[class] = (low, base, high, basis)."""
    tot = float(port.sum())
    return sum(port[c] * (dmap[c][k] if c in dmap else 0.0) for c in CLASSES) / tot if tot else None


res, bd, test_rows = [], [], []
for sid in PEERS:
    row = dict(peer=sid, company=NAME[sid], focus=sid == FOCUS, regulator="AMF" if sid in AMF_IDS else "OSFI",
               period_end="2025-10-31" if sid in OCT else "2025-12-31",
               scope="Canada (OSFI In Canada)" if sid in BIG3 else ("consolidated, carve-outs per ALM repo" if sid in AMF_IDS else "legal entity (all Canada)"))
    csm_abl, csm_tot = mm(sid, "csm_abl_k"), mm(sid, "csm_total_k")
    row.update(csm_total_mm=r(csm_tot, 0), csm_abl_mm=r(csm_abl, 0), csm_seg_mm=r(mm(sid, "seg_csm_k"), 0), csm_par_mm=r(mm(sid, "par_csm_memo_k"), 0),
               csm_split_basis="total CSM only (AMF rule)" if sid in AMF_IDS else f"seg {summ.loc[sid, 'seg_csm_basis']}, par {summ.loc[sid, 'par_csm_basis']}",
               surplus_mm=r(mm(sid, "surplus_k"), 0), genacct_mm=r(mm(sid, "genacct_k"), 0), repos_mm=r(mm(sid, "repos_k"), 0),
               buffer_pct=r(summ.loc[sid, "buffer_pct"], 1), capital_ratio_pct=r(summ.loc[sid, "capital_ratio_pct"], 1))
    C = csm_abl if csm_abl is not None else csm_tot
    S = mm(sid, "surplus_k")
    row["csm_in_portfolio_mm"] = r(C, 0)
    row["csm_in_portfolio_basis"] = "ABL CSM (General Account)" if csm_abl is not None else "total CSM, not split (memo, not comparable)"

    # FVOCI designation test (ALM repo research/synthetic_rbc_benchmark.md 7.6)
    ratio = None
    if sid in OSFI:
        fb, fv, ac = fvoci_book(sid)
        eq, t1 = ov(sid, PERIOD, "P2000469901"), ov(sid, PERIOD, "D2040010025")
        ratio = (fv + ac) / (eq + t1) if (fv + ac) else 0.0
        row.update(fvoci_ac_mm=r(fv + ac, 0), equity_mm=r(eq, 0), csm_tier1_mm=r(t1, 0), designation_ratio=r(ratio, 2))

    if S is None:   # Desjardins: no public balance sheet
        row.update(basis="liability side only (no public balance sheet; ALM repo L42)", csm_portfolio_duration=None, surplus_portfolio_duration=None)
        res.append(row)
        continue

    G = mix_b[sid]
    dmap_book = book.get(sid, {})
    # surplus fixed income: disclosed surplus-type duration where there is one, otherwise the whole-book class durations
    dmap_sur = dict(dmap_book)
    if sid in surplus_fi:
        for c in FI[1:]:
            dmap_sur[c] = surplus_fi[sid]
    else:   # no surplus-specific evidence: whole-book durations (an upper bound); low case = disclosed peer surplus books
        for c in FI[1:]:
            lo_, ba_, hi_, bs_ = dmap_book[c]
            dmap_sur[c] = (min(lo_, PEER_SURPLUS_D), ba_, hi_, bs_ + "; low case = median of disclosed peer surplus books")
    row["nonfi_to_surplus"] = r(float(G[NONFI].sum()) / S, 2)
    sB, cB = waterfall(G, S, C)
    sC, cC = waterfall(G, S, C, pooled=True)
    dmap_csm_b = dmap_sur if sid == "SLF" else dmap_book   # Sun Life states its FVOCI fixed income backs CSM
    alt = dict(csm_b=[dur_of(cB, dmap_csm_b, k) for k in range(3)], sur_b=[dur_of(sB, dmap_sur, k) for k in range(3)],
               csm_c=dur_of(cC, dmap_sur, 1), sur_c=dur_of(sC, dmap_sur, 1))

    if sid in ("RBC", "BLU", "IOF"):
        if sid == "IOF":
            seg = pd.Series(0.0, index=CLASSES)
            f = fs["Surplus"]
            gshare = float(G["Government bonds"] / (G["Government bonds"] + G["Corporate bonds"]))
            seg["Cash and short term"] = f["cash"] + f["short_term"]
            seg["Government bonds"] = f["bonds"] * gshare
            seg["Corporate bonds"] = f["bonds"] * (1 - gshare)
            seg["Common shares"] = f["stocks"]
            seg["Preferred shares"] = f["preferred"]
            seg["Others"] = f["other_invested"]
            basis = "A: disclosed segment table (assets supporting surplus, FLIC 2025 FS)"
        else:
            seg = fb.copy()
            basis = f"A: FVOCI and amortized cost book (designation test {ratio:.2f} of equity + Tier 1 CSM)"
        T = float(seg.sum())
        cA = seg.copy() * 0
        cA[FI] = seg[FI] / seg[FI].sum() * C          # CSM assets pro rata to the segment's fixed income
        sA = seg - cA
        dm = {c: surplus_fi[sid] for c in FI[1:]}
        dm["Cash and short term"] = (CASH_D,) * 3 + ("assumed 0.25 years",)
        csm_d = [dur_of(cA, dm, k) for k in range(3)]
        sur_d = [dur_of(sA, dm, k) for k in range(3)]
        ports = (("CSM", cA, dm), ("Surplus", sA, dm))
        row.update(basis=basis, surplus_portfolio_mm=r(float(sA.sum()), 0), segment_total_mm=r(T, 0),
                   note_size=f"Segment C${T:,.0f}MM less ABL CSM; compares with ALM repo Surplus C${S:,.0f}MM"
                             + (f" and reported equity C${eq:,.0f}MM" if sid in OSFI else ""))
    else:
        csm_d, sur_d = list(alt["csm_b"]), alt["sur_b"]
        if sid == "SLF":   # high case: strict waterfall, CSM at the whole-book mix
            csm_d[2] = dur_of(cB, dmap_book, 1)
        ports = (("CSM", cB, dmap_csm_b), ("Surplus", sB, dmap_sur))
        n = float(G[NONFI].sum())
        basis = "B: waterfall on the non-par General Account mix"
        if sid in AMF_IDS:
            basis += " (pool incl. par and UL, not separable; memo)"
        row.update(basis=basis, surplus_portfolio_mm=r(S, 0), segment_total_mm=None,
                   note_size="Non-fixed-income assets exceed Surplus; the excess backs liabilities" if n > S else "")
    for pname, port, dm in ports:
        tot = float(port.sum())
        for c in CLASSES:
            if port[c] > 0.05:
                d = dm[c] if c in dm else (0.0, 0.0, 0.0, "no rate duration assigned (equity, real estate, others)")
                bd.append(dict(peer=sid, company=NAME[sid], portfolio=pname, asset_class=c, amount_mm=r(port[c], 1), weight=r(port[c] / tot, 4),
                               duration=r(d[1]), contribution=r(port[c] / tot * d[1], 3), duration_low=r(d[0]), duration_high=r(d[2]), duration_basis=d[3]))
    sp = ports[1][1]
    row.update(csm_portfolio_duration=r(csm_d[1]), csm_portfolio_duration_low=r(csm_d[0]), csm_portfolio_duration_high=r(csm_d[2]),
               surplus_portfolio_duration=r(sur_d[1]), surplus_portfolio_duration_low=r(sur_d[0]), surplus_portfolio_duration_high=r(sur_d[2]),
               surplus_fi_share=r(float(sp[FI].sum() / sp.sum()), 3),
               surplus_fi_duration=r(surplus_fi[sid][1]) if sid in surplus_fi else r(dur_of(sp[FI].reindex(CLASSES).fillna(0), dmap_sur, 1)),
               surplus_fi_duration_basis=surplus_fi[sid][3] if sid in surplus_fi else "whole-book class durations (waterfall default; likely an upper bound for surplus)",
               whole_book_fi_duration=r(dur_of(G[FI].reindex(CLASSES).fillna(0), dmap_book, 1)),
               whole_book_basis="; ".join(sorted({dmap_book[c][3] for c in FI[1:] if c in dmap_book})),
               csm_duration_waterfall_b=r(alt["csm_b"][1]), surplus_duration_waterfall_b=r(alt["sur_b"][1]),
               csm_duration_option_c=r(alt["csm_c"]), surplus_duration_option_c=r(alt["sur_c"]))
    res.append(row)

# ------------------------------------------------------------------------------ 5. CSM run-off (ALM repo rule)
rel = deck["csm_release"]
runoff_rows, wal_by = [], {}
for rs in deck["runoff_summary"]:
    wal_by[rs["peer"]] = (rs["wal"], rs["scope"] + ", " + rs["contract"].replace("_", " "), "disclosed schedule")
    d = ro[ro.peer == rs["peer"]]
for sid in ("IAG", "BEN", "DFS"):
    a = AMF[sid]
    wal_by[sid] = (wal(a["csm_bands"]), a["csm_scope"], "disclosed schedule")
k_cal = statistics.median(wal_by[s][0] * rel[s]["2025"] / 100 for s in wal_by if s in rel)
for sid in PEERS:
    rr = rel.get(sid, {}).get("2025")
    if sid not in wal_by and rr:
        wal_by[sid] = (k_cal / (rr / 100), "legal entity", f"estimated from the 2025 release rate (WAL x release rate = {k_cal:.2f}, peer median)")
for sid in PEERS:
    if sid in wal_by:
        w, scope, basis = wal_by[sid]
        runoff_rows.append(dict(peer=sid, company=NAME[sid], csm_runoff_wal_years=r(w), scope=scope, basis=basis,
                                release_rate_2025_pct=r(rel.get(sid, {}).get("2025"), 1)))
ro_out = ro.assign(company=ro.peer.map(NAME))[["peer", "company", "entity_basis", "as_of", "segment_line", "contract_type", "band", "band_start_yr",
                                                 "band_end_yr", "value_mm", "source_file", "line_ref"]]
for sid in ("IAG", "BEN", "DFS"):
    for s, e, a in AMF[sid]["csm_bands"]:
        ro_out = pd.concat([ro_out, pd.DataFrame([dict(peer=sid, company=NAME[sid], entity_basis=AMF[sid]["csm_scope"], as_of="2025-12-31", segment_line="",
                                                        contract_type="net" if sid != "DFS" else "insurance_issued", band=f"{s:g}-{e:g}" if e else f"over {s:g}",
                                                        band_start_yr=s, band_end_yr=e, value_mm=a, source_file=AMF[sid]["csm_source"], line_ref="")])])
for row in res:
    w = wal_by.get(row["peer"])
    row.update(csm_runoff_wal=r(w[0]) if w else None, csm_runoff_scope=w[1] if w else None, csm_runoff_basis=w[2] if w else None,
               csm_release_rate_pct=r(rel.get(row["peer"], {}).get("2025"), 1))
    row["duration_gap_csm"] = r(row["csm_portfolio_duration"] - w[0]) if (w and row.get("csm_portfolio_duration") is not None) else None

# ------------------------------------------------------------------------------ 6. disclosed sensitivities
sens_rows = []
keep = sens[(sens.risk == "rates")]
for sid in PEERS:
    d = keep[keep.peer == sid]
    for _, x in d.iterrows():
        sens_rows.append(dict(peer=sid, company=NAME[sid], entity_basis=x.entity_basis, as_of=x.as_of, shock=x.shock, measure=x.measure,
                              value_mm=x.value_mm, component=str(x.notes)[:160], definition=str(x.applied_to)[:400], source_file=x.source_file,
                              line_ref=x.line_ref))
for sid in ("IAG", "BEN", "DFS"):
    for s in AMF[sid]["sens"]:
        sens_rows.append(dict(peer=sid, company=NAME[sid], entity_basis=s["basis"], as_of="2025-12-31", shock=s["shock"], measure=s["measure"],
                              value_mm=s["value"], component=s.get("component", "total"), definition=s["definition"], source_file=s["source"], line_ref=""))


def total_sens(sid, measure):
    """Disclosed total for a 50 bps fall (or the nearest disclosed shock), as printed. Component rows are not summed."""
    d = keep[(keep.peer == sid) & (keep.measure == measure) & (keep.shock_direction == "down")]
    d = d[~d.notes.astype(str).str.contains("component", case=False) & ~d.shock.astype(str).str.contains("UFR|UIR")]
    d = d[~d.notes.astype(str).str.contains("Financial instruments|Insurance contracts|Reinsurance contracts|Insurance and reinsurance", regex=True)]
    for bp in ("-50", "-100"):
        x = d[d.shock.astype(str).str.startswith(bp)]
        if len(x):
            return float(x.value_mm.iloc[0]), f"{bp} bps"
    return None, None


for row in res:
    sid = row["peer"]
    if sid in AMF_IDS:
        tt = {s["measure"]: s for s in AMF[sid]["sens"] if s.get("component", "total") == "total" and s["shock"].startswith("-")}
        row.update(sens_shock=next(iter(tt.values()))["shock"] if tt else None, sens_equity_mm=tt.get("equity", {}).get("value"),
                   sens_net_income_mm=tt.get("net_income", {}).get("value"), sens_oci_mm=tt.get("oci", {}).get("value"),
                   sens_csm_mm=tt.get("csm", {}).get("value"), sens_basis=AMF[sid]["sens"][0]["basis"] if AMF[sid]["sens"] else None)
        continue
    e, sh = total_sens(sid, "equity")
    ni, sh2 = total_sens(sid, "net_income")
    oc, sh3 = total_sens(sid, "oci")
    cs, sh4 = total_sens(sid, "csm")
    if sid == "MFC":
        e, sh = total_sens(sid, "tci")
    b = keep[keep.peer == sid].entity_basis
    row.update(sens_shock=sh or sh2 or sh3 or sh4, sens_equity_mm=e, sens_net_income_mm=ni, sens_oci_mm=oc, sens_csm_mm=cs,
               sens_basis=b.iloc[0] if len(b) else "not disclosed")

# Directional check, one risk only: the disclosed net change in equity for a parallel rate move, before tax, expressed
# as years on the CSM and surplus portfolios together. Positive = equity gains when rates fall. Component rows of the
# same rate shock are netted where the filer gives no total; nothing is combined across risks.
NET_EQUITY = {   # (change for a rise, change for a fall, shock in bps, tax rate, scope)
    "RBC": (-10.0, 5.0, 100, TAX, "RBC Insurance segment of the bank (net income; includes non-Canadian business)"),
    "BMO": (771.906 - 769.580, -858.250 + 852.710, 50, TAX, "legal entity; financial instruments net of insurance contracts"),
    "EMP": (-44.0, 36.0, 50, TAX, "legal entity (includes par and segregated fund guarantees)"),
    "IVA": (-42.7, 34.8, 50, 0.2575, "legal entity"),
    "EQL": (-1.2, -2.8, 50, TAX, "legal entity (includes par)"),
    "IOF": (-23.345 - 12.452 + 30.428, 26.804 + 14.193 - 36.925, 100, 0.0, "legal entity; instruments net of insurance contract liabilities, before tax"),
    "WAW": (61.527 - 75.673, -75.587 + 91.525, 100, TAX, "legal entity (includes par); financial instruments net of insurance contracts"),
    "IAG": (None, -25.0, 50, TAX, "iA consolidated"),
    "BEN": (None, 3.3 + 75.9, 100, TAX, "Beneva consolidated (includes P&C); net income plus OCI"),
}
for row in res:
    ne = NET_EQUITY.get(row["peer"])
    base_ = (row.get("csm_in_portfolio_mm") or 0) + (row.get("surplus_portfolio_mm") or 0)
    if ne and base_:
        up, down, bp, tax, scope = ne
        chg_ = (down - up) / 2 if up is not None else down
        row.update(net_equity_duration_check=r(chg_ / (1 - tax) / (bp / 1e4) / base_, 1), net_equity_check_scope=scope)

# ------------------------------------------------------------------------------ 7. FVOCI and OCI
fv_rows = []
for sid in PEERS:
    lim = LIMITS.get(sid, {})
    base = dict(peer=sid, company=NAME[sid], focus=sid == FOCUS, limits_statement=lim.get("text", "Not disclosed."), limits_source=lim.get("source", ""))
    if sid in OSFI:
        for per in ("2024Q4", PERIOD):
            fb, fv, ac = fvoci_book(sid, per)
            inv = ov(sid, per, "P2101288940")
            eq, t1 = ov(sid, per, "P2000469901"), ov(sid, per, "D2040010025")
            rec = dict(base, fiscal_year=per[:4], source="OSFI LF2 page 21.012 (col 16 FVOCI, col 36 amortized cost), legal entity", investments_mm=r(inv, 0),
                       fvoci_mm=r(fv, 0), amortized_cost_mm=r(ac, 0), fvoci_ac_pct_of_investments=r(100 * (fv + ac) / inv, 1), equity_mm=r(eq, 0),
                       csm_tier1_mm=r(t1, 0), designation_ratio=r((fv + ac) / (eq + t1), 2) if (fv + ac) else 0.0)
            for c in CLASSES:
                rec["mix_" + c.lower().replace(" ", "_")] = r(100 * fb[c] / (fv + ac), 1) if (fv + ac) else None
            fx = float(fb[FI[1:]].sum())
            rec["fvoci_ac_fixed_income_mm"] = r(fx, 0)
            if per == PERIOD:
                rec.update(aoci_fvoci_mm=r(ov(sid, per, "P2004270001"), 1), oci_fvoci_bonds_fy_mm=r(ov(sid, per, "P2004214001"), 1),
                           oci_fvoci_loans_fy_mm=r(ov(sid, per, "P2004211001"), 1), oci_reclassified_fy_mm=r(ov(sid, per, "P2004221001"), 1))
                q = [o for o in oci_rows if o["peer"] == sid and o["oci_fvoci_bonds_mm"] is not None and "Q" in o["quarter"]]
                if q:
                    worst = min(q, key=lambda o: o["oci_fvoci_bonds_mm"])
                    rec.update(worst_quarter=worst["quarter"], worst_quarter_oci_mm=worst["oci_fvoci_bonds_mm"], worst_quarter_pct_of_equity=worst["oci_pct_of_equity"])
                if sid in realised:
                    rec.update(realised_duration=r(realised[sid]["slope"], 1), realised_observations=realised[sid]["n"], realised_r2=r(realised[sid]["r2"], 2))
                dsf = surplus_fi.get(sid)
                fvoci_fi = float(osfi[(osfi.id == OSFI[sid]) & (osfi.per == per) & osfi.dpa.isin(["P2101247916", "P2101250016"])].value_num.sum()) / 1000
                rec["fvoci_fixed_income_mm"] = r(fvoci_fi, 0)
                if dsf and fvoci_fi and sid != "MFC":
                    rec.update(est_oci_per_50bp_rise_pretax_mm=r(-fvoci_fi * dsf[1] * 0.005, 0), est_oci_low_mm=r(-fvoci_fi * dsf[0] * 0.005, 0),
                               est_oci_high_mm=r(-fvoci_fi * dsf[2] * 0.005, 0), est_duration=r(dsf[1]), est_basis=dsf[3])
                d = keep[(keep.peer == sid) & (keep.measure == "oci")]
                if len(d):
                    rec["disclosed_oci_sensitivity"] = "; ".join(f"{x.shock}: {x.value_mm:+,.0f}" if abs(x.value_mm) >= 20 else f"{x.shock}: {x.value_mm:+,.1f}" for x in d.itertuples()) \
                        + f" (C$MM, {d.entity_basis.iloc[0]})"
                else:
                    rec["disclosed_oci_sensitivity"] = "None disclosed" if (fv + ac) else "No FVOCI or amortized cost assets: rate moves go through net income"
                rec["note"] = lim.get("note", "")
            fv_rows.append(rec)
    else:
        a = AMF[sid]
        rec = dict(base, fiscal_year="2025", source=a.get("fvoci_source", "not published"), **a.get("fvoci", {}))
        rec["disclosed_oci_sensitivity"] = a.get("oci_text", "None disclosed")
        rec["note"] = lim.get("note", "")
        if sid == "BEN":
            dsf = surplus_fi["BEN"]
            rec.update(est_duration=r(dsf[1]), est_basis=dsf[3])
        fv_rows.append(rec)

# ------------------------------------------------------------------------------ 8. change against the earlier version
v1 = pd.read_csv(HERE / "v1_results_2026-10-29.csv").set_index("company_id")
chg = []
for row in res:
    old = v1.loc[V1_ID[row["peer"]]] if row["peer"] in V1_ID else None
    def o(col):
        return None if old is None or pd.isna(old[col]) else float(old[col])
    rec = dict(peer=row["peer"], company=row["company"], focus=row["focus"],
               csm_size_v1_mm=o("csm_net_cad_mm"), csm_size_v2_mm=row["csm_in_portfolio_mm"],
               surplus_size_v1_mm=o("surplus_cad_mm"), surplus_size_v2_mm=row.get("surplus_portfolio_mm"),
               csm_duration_v1=o("csm_portfolio_duration"), csm_duration_v2=row.get("csm_portfolio_duration"),
               surplus_duration_v1=o("surplus_portfolio_duration"), surplus_duration_v2=row.get("surplus_portfolio_duration"),
               csm_runoff_v1=o("csm_runoff_duration"), csm_runoff_v2=row.get("csm_runoff_wal"),
               basis_v1=None if old is None else old["pool_basis"], basis_v2=row.get("basis"))
    for k in ("csm_duration", "surplus_duration", "csm_runoff"):
        a, b_ = rec[k + "_v1"], rec[k + "_v2"]
        rec[k + "_change"] = r(b_ - a) if (a is not None and b_ is not None) else None
    drivers = []
    if old is None:
        drivers.append("New: in the ALM repo's peer set, not in the earlier version")
    else:
        if rec["csm_size_v1_mm"] and rec["csm_size_v2_mm"] and abs(rec["csm_size_v2_mm"] / rec["csm_size_v1_mm"] - 1) > 0.15:
            drivers.append("CSM is now the Canadian General Account piece (ABL CSM) instead of total net CSM" if row["peer"] not in AMF_IDS
                           else "CSM after the ALM repo's carve-outs")
        if rec["surplus_size_v1_mm"] and rec["surplus_size_v2_mm"] and abs(rec["surplus_size_v2_mm"] / rec["surplus_size_v1_mm"] - 1) > 0.15:
            drivers.append("Surplus is now the ALM repo's Canadian General Account Surplus instead of group or entity equity less goodwill")
        if "waterfall" in (row.get("basis") or "") and "FVOCI" in str(old["pool_basis"]):
            drivers.append("FVOCI designation dropped as the pool (fails the ALM repo's test); waterfall on the non-par General Account instead")
        if row["peer"] in surplus_fi:
            drivers.append("Surplus fixed-income duration now from " + surplus_fi[row["peer"]][3].split(" (")[0])
        if "disclosed sensitivity" in (row.get("whole_book_basis") or ""):
            drivers.append("Whole-book duration from the disclosed asset sensitivity instead of maturity buckets or a liability-mix proxy")
        if rec["csm_runoff_change"] is not None:
            drivers.append("CSM run-off on the ALM repo's rule (weighted average years, open band at start + 5), undiscounted")
    rec["material"] = any(abs(rec[k]) >= 1.0 for k in ("csm_duration_change", "surplus_duration_change") if rec[k] is not None)
    rec["drivers"] = "; ".join(drivers)
    chg.append(rec)

coverage = [dict(company=NAME[s], status="rebuilt", note=("AMF filer: total CSM only, pool incl. par and UL (memo)" if s in ("IAG", "BEN") else
                                                           "liability side only" if s == "DFS" else
                                                           "in the ALM repo's peer set; not on the project's 20-company list" if s == "BLU" else "")) for s in PEERS]
coverage += [dict(company=k, status="not rebuilt", note=v) for k, v in NOT_REBUILT.items()]

params = [
    dict(parameter="Flat yield for band-to-duration conversion", value=f"{Y:.2%}", note="Modified duration of a par bond at each band's representative term; unchanged from the earlier version"),
    dict(parameter="Closed maturity bands", value="midpoint", note="e.g. 1 to 5 years = 3 years"),
    dict(parameter="Open band, bonds and private placements", value="start + 10 years (range + 5 to + 15)", note="Low case is the ALM repo's CSM convention (start + 5). Empire's disclosed sensitivity (11.1 years) sits within 0.5 years of its band estimate at + 10"),
    dict(parameter="Open band, mortgages and loans", value="start + 5 years (range + 2.5 to + 10)", note=""),
    dict(parameter="Cash and short term", value="0.25 years", note="assumed"),
    dict(parameter="Equity, preferred shares, real estate, others", value="0", note="no rate duration assigned"),
    dict(parameter="Tax gross-up for sensitivities disclosed net of tax", value=f"{TAX:.1%}", note="assumed; the report's own basis is quoted in sensitivities.csv"),
    dict(parameter="CSM run-off", value="weighted average years, band midpoints, open band at start + 5", note="ALM repo scripts/deck2/build_deck2_data.py; undiscounted"),
    dict(parameter="Median duration of disclosed surplus-type fixed income", value=f"{PEER_SURPLUS_D:.1f} years (range {PEER_LO:.1f} to {PEER_HI:.1f})",
         note="; ".join(f"{NAME[k]} {v:.1f}" for k, v in evidence.items())),
    dict(parameter="Realised OCI sensitivity", value="regression through the origin of pre-tax OCI return on the change in the 5-year Canada yield",
         note="; ".join(f"{NAME[k]} {v['slope']:.1f} years ({v['n']} observations, R2 {v['r2']:.2f})" for k, v in realised.items())),
    dict(parameter="Run-off estimate without a schedule", value=f"WAL = {k_cal:.2f} / release rate", note="peer median of WAL x release rate; Co-operators, Wawanesa, Blumont"),
    dict(parameter="ALM repo commit", value=(ALM / ".git/HEAD").read_text().strip()[:40], note="MooseDragon/cdn-life-insurer-alm, branch main"),
]

RES_COLS = ["peer", "company", "focus", "regulator", "period_end", "scope", "basis", "csm_total_mm", "csm_abl_mm", "csm_seg_mm", "csm_par_mm", "csm_split_basis",
            "csm_in_portfolio_mm", "csm_in_portfolio_basis", "surplus_mm", "surplus_portfolio_mm", "segment_total_mm", "note_size", "genacct_mm", "repos_mm",
            "buffer_pct", "capital_ratio_pct", "csm_portfolio_duration", "csm_portfolio_duration_low", "csm_portfolio_duration_high", "csm_runoff_wal",
            "csm_runoff_scope", "csm_runoff_basis", "csm_release_rate_pct", "duration_gap_csm", "surplus_portfolio_duration", "surplus_portfolio_duration_low",
            "surplus_portfolio_duration_high", "surplus_fi_share", "nonfi_to_surplus", "surplus_fi_duration", "surplus_fi_duration_basis", "whole_book_fi_duration", "whole_book_basis",
            "csm_duration_waterfall_b", "surplus_duration_waterfall_b", "csm_duration_option_c", "surplus_duration_option_c", "fvoci_ac_mm", "equity_mm",
            "csm_tier1_mm", "designation_ratio", "sens_shock", "sens_equity_mm", "sens_net_income_mm", "sens_oci_mm", "sens_csm_mm", "sens_basis",
            "net_equity_duration_check", "net_equity_check_scope"]
out = {
    "results.csv": pd.DataFrame(res).reindex(columns=RES_COLS),
    "portfolio_breakdown.csv": pd.DataFrame(bd),
    "class_durations.csv": pd.DataFrame(class_rows).assign(key=lambda d: d.peer + "|" + d.book + "|" + d.asset_class),
    "csm_runoff.csv": ro_out,
    "csm_runoff_summary.csv": pd.DataFrame(runoff_rows),
    "fvoci.csv": pd.DataFrame(fv_rows).assign(key=lambda d: d.peer + "-" + d.fiscal_year.astype(str)),
    "oci_history.csv": pd.DataFrame(oci_rows),
    "sensitivities.csv": pd.DataFrame(sens_rows).assign(key=lambda d: d.peer + "-" + d.groupby("peer").cumcount().add(1).astype(str)),
    "changes_vs_v1.csv": pd.DataFrame(chg),
    "coverage.csv": pd.DataFrame(coverage),
    "parameters.csv": pd.DataFrame(params),
}
(HERE / "dashboard").mkdir(exist_ok=True)
for name, df in out.items():
    df.to_csv(HERE / name, index=False)
    shutil.copy(HERE / name, HERE / "dashboard" / name)

pd.set_option("display.width", 260)
pd.set_option("display.max_columns", 40)
t = out["results.csv"]
print(t[["peer", "basis", "csm_in_portfolio_mm", "surplus_portfolio_mm", "csm_portfolio_duration", "csm_portfolio_duration_low", "csm_portfolio_duration_high",
         "csm_runoff_wal", "surplus_portfolio_duration", "surplus_portfolio_duration_low", "surplus_portfolio_duration_high", "surplus_fi_share", "nonfi_to_surplus", "surplus_fi_duration", "whole_book_fi_duration", "net_equity_duration_check"]].assign(basis=lambda d: d.basis.str[:12]).to_string(index=False))
print(t[["peer", "csm_duration_waterfall_b", "surplus_duration_waterfall_b", "csm_duration_option_c", "surplus_duration_option_c", "designation_ratio",
         "sens_shock", "sens_equity_mm", "sens_net_income_mm", "sens_oci_mm", "sens_csm_mm"]].to_string(index=False))
print(out["parameters.csv"].to_string(index=False))
print(out["changes_vs_v1.csv"][["peer", "csm_duration_v1", "csm_duration_v2", "surplus_duration_v1", "surplus_duration_v2", "csm_runoff_v1", "csm_runoff_v2", "material"]].to_string(index=False))
