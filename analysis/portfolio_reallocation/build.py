#!/usr/bin/env python3
"""Quarterly portfolio reallocation time series for the 20-insurer peer set.

Builds one harmonized general-account asset mix per insurer and quarter from
Q1 2020 to the latest filing, then measures reallocations as changes in
percentage share and in C$ by asset class, and flags the quarters where a
series break (the IFRS 4 -> IFRS 17 / IFRS 9 switch) or a corporate event
explains the change instead of a portfolio decision.

Sources (all already in the repository):
  OSFI filers   data/osfi/portfolio_mix.csv (IFRS 4 10Q return to 2022, IFRS 17
                LF1/LF2 from 2023; October year ends switch a year later),
                data/osfi/LF2_core.csv.gz page P21012 column 40 and LF1 page
                P20002 for the IFRS 17 sub-class detail, LF1 column 03 (prior
                period restated) for the same-date IFRS 4 vs IFRS 17 bridge.
  iA            Quarterly supplementary packages in docs/ia (rolling nine
                quarter packages for 2020, supplemental information packages
                from Q4 2022; the 2023 packages restate 2022 on IFRS 17).
  Beneva, Assumption Life, Humania, UV Insurance
                Year-end statements of financial position (annual_points.csv,
                hand-entered with the page reference for each figure).
  Market        Bank of Canada Valet: long-term Government of Canada benchmark
                yield and USD/CAD; S&P/TSX composite monthly closes (Yahoo
                Finance). Month-end values cached in market_context.csv and
                refetched with --refresh-market. Used for context and for the
                market-drift estimate (see market_drift).

Harmonized classes (both accounting bases), with the CIO taxonomy's Level 2:
  Cash & short-term     Cash & Cash Equivalents
  Bonds                 Fixed Income (public bonds and private placements; the
                        IFRS 4 return does not split them, so they stay together
                        in the history view and are split in the IFRS 17 detail)
  Mortgages & loans     Private Fixed Income
  Equities              Public Equity (common and preferred shares; iA, Beneva
                        and UV include private equity held as shares)
  Real estate           Externally Managed Equity (investment property)
  Other invested assets Externally Managed Equity (other loans, limited
                        partnerships, associates and joint ventures)
Excluded throughout: policy loans (IFRS 17 moved them into insurance contract
balances, so keeping them on the IFRS 4 side would create a false outflow),
derivative assets, segregated funds, pass-through fund units, subsidiaries.

Writes CSVs next to this script and into dashboard/ for the dashboard and PDF.

Usage: python3 analysis/portfolio_reallocation/build.py [--refresh-market]
"""
import collections
import csv
import glob
import gzip
import json
import os
import re
import sys
import urllib.request
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OSFI = os.path.join(ROOT, "data", "osfi")
DASH = os.path.join(HERE, "dashboard")
FIRST = "2020Q1"
LAST = "2026Q2"
FOCUS = "rbc_life"

CLASSES = [
    ("Cash & short-term", "Cash & Cash Equivalents"),
    ("Bonds", "Public & Private Fixed Income"),
    ("Mortgages & loans", "Private Fixed Income"),
    ("Equities", "Public Equity"),
    ("Real estate", "External Equity"),
    ("Other invested assets", "External Equity"),
]
CLASS_NAMES = [c for c, _ in CLASSES]
LEVEL2 = dict(CLASSES)

COMPANIES = collections.OrderedDict([
    ("manulife", "Manulife"),
    ("sun_life", "Sun Life"),
    ("canada_life", "Canada Life"),
    ("ia", "iA Financial Group"),
    ("rbc_life", "RBC Life"),
    ("bmo_life", "BMO Life"),
    ("beneva", "Beneva"),
    ("ivari", "ivari"),
    ("empire_life", "Empire Life"),
    ("equitable_life", "Equitable Life"),
    ("cooperators_life", "Co-operators Life"),
    ("uv_insurance", "UV Insurance"),
    ("wawanesa_life", "Wawanesa Life"),
    ("assumption_life", "Assumption Life"),
    ("foresters_life", "Foresters Life (incl. Canada Protection Plan)"),
    ("canadian_premier", "Canadian Premier Life"),
    ("humania", "Humania"),
    ("primerica_life", "Primerica Life"),
    ("desjardins", "Desjardins Insurance"),
    ("peer_median", "Peer median (quarterly filers, excl. RBC Life)"),
])
# OSFI legal entity used per company (the main insurer; holding companies and
# smaller sister entities are left out so nothing is counted twice).
OSFI_ENTITY = {
    "manulife": "The Manufacturers Life Insurance Company",
    "sun_life": "Sun Life Assurance Company of Canada",
    "canada_life": "The Canada Life Assurance Company",
    "rbc_life": "RBC Life Insurance Company",
    "bmo_life": "BMO Life Assurance Company",
    "ivari": "ivari",
    "empire_life": "The Empire Life Insurance Company",
    "equitable_life": "The Equitable Life Insurance Company of Canada",
    "cooperators_life": "Co-operators Life Insurance Company",
    "wawanesa_life": "The Wawanesa Life Insurance Company",
    "foresters_life": "Foresters Life Insurance Company",
    "canadian_premier": "Canadian Premier Life Insurance Company",
    "primerica_life": "Primerica Life Insurance Company of Canada",
}
OCT_YEAR_END = {"bmo_life", "rbc_life"}

# LF2 P21012 rows (column 40) and LF1 P20002 rows (column 01) -> Level 3 for
# the IFRS 17 detail view; same mapping as analysis/portfolio_composition.
LF2_ROWS = {
    "010": "Cash",
    "045": "Government Bonds", "050": "Government Bonds", "055": "Government Bonds",
    "065": "Government Bonds", "140": "Government Bonds", "160": "Government Bonds",
    "210": "Corporate Bonds", "230": "Corporate Bonds",
    "410": "Illiquid Term Loans", "430": "Illiquid Term Loans",
    "500": "Commercial Mortgages",
    "520": "Preferred Shares", "560": "Preferred Shares",
    "659": "Common Shares",
    "810": "Policy & Other Loans",
    "820": "Other Private Equity",
}
LF2_BELOW_IG = {"050", "065", "160", "230", "430"}
LF1_ROWS = {"010": "Cash", "110": "Real Estate Equity", "080": "Other Private Equity"}
LEVEL3 = collections.OrderedDict([
    ("Government Bonds", ("Internally Managed", "Public Fixed Income")),
    ("Corporate Bonds", ("Internally Managed", "Public Fixed Income")),
    ("Bonds (issuer n/d)", ("Internally Managed", "Public Fixed Income")),
    ("Illiquid Term Loans", ("Internally Managed", "Private Fixed Income")),
    ("Commercial Mortgages", ("Internally Managed", "Private Fixed Income")),
    ("Private Liquid Loans", ("Internally Managed", "Private Fixed Income")),
    ("Policy & Other Loans", ("Internally Managed", "Private Fixed Income")),
    ("Common Shares", ("Internally Managed", "Public Equity")),
    ("Preferred Shares", ("Internally Managed", "Public Equity")),
    ("Cash", ("Internally Managed", "Cash & Cash Equivalents")),
    ("Real Estate Equity", ("Externally Managed", "Equity")),
    ("Other Private Equity", ("Externally Managed", "Equity")),
    ("Other / Unclassified", ("Other", "Other")),
])

# Known corporate events that move a portfolio without being an allocation
# choice. cal quarter -> note. Size jumps above JUMP are also flagged.
EVENTS = {
    ("uv_insurance", "2025Q4"): "Acquired about 200,000 BMO Life policies (assumption reinsurance, June 2025): "
                                "the bond increase is mostly assets transferred with the block.",
    ("bmo_life", "2025Q2"): "Transferred about 200,000 policies to UV Insurance (assumption reinsurance, June 2025).",
}
JUMP = 0.15
BOND_DURATION = 10.0  # assumed modified duration of insurers' bond holdings (years)

QUARTER_END = {"Q1": "03-31", "Q2": "06-30", "Q3": "09-30", "Q4": "12-31"}
QUARTER_END_OCT = {"Q1": "01-31", "Q2": "04-30", "Q3": "07-31", "Q4": "10-31"}
USER_AGENT = "InsuranceCompanies-dataset/1.0 (+https://github.com/abiddobani/InsuranceCompanies)"


def cal_quarter(cid, fy, q):
    """Fiscal quarter -> calendar quarter label. October year ends: fiscal Q1 ends
    31 January and is placed in the calendar quarter ending one month earlier."""
    fy = int(fy)
    if cid not in OCT_YEAR_END:
        return f"{fy}{q}"
    return {"Q1": f"{fy - 1}Q4", "Q2": f"{fy}Q1", "Q3": f"{fy}Q2", "Q4": f"{fy}Q3"}[q]


def period_end(cid, fy, q):
    return f"{fy}-{(QUARTER_END_OCT if cid in OCT_YEAR_END else QUARTER_END)[q]}"


def qkey(label):
    return int(label[:4]) * 4 + int(label[5]) - 1


def qlabel(k):
    return f"{k // 4}Q{k % 4 + 1}"


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def read_gz(name):
    with gzip.open(os.path.join(OSFI, name), "rt", newline="") as f:
        yield from csv.DictReader(f)


def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})


# ---------------------------------------------------------------- OSFI history

def osfi_history():
    """{cid: {cal_q: (basis, period_end, {class: C$ mm})}} from portfolio_mix.csv."""
    out = collections.defaultdict(dict)
    with open(os.path.join(OSFI, "portfolio_mix.csv"), newline="") as f:
        for r in csv.DictReader(f):
            cid = r["company_id"]
            if OSFI_ENTITY.get(cid) != r["entity"]:
                continue
            g = lambda k: num(r[k + "_cad_000"]) / 1000.0
            mix = {
                "Cash & short-term": g("cash") + g("short_term_investments"),
                "Bonds": g("bonds"),
                "Mortgages & loans": g("mortgages"),
                "Equities": g("preferred_shares") + g("common_shares"),
                "Real estate": g("investment_properties"),
                "Other invested assets": g("other_loans_and_invested_assets"),
            }
            cq = cal_quarter(cid, r["fiscal_year"], r["quarter"])
            # Keep IFRS 17 where a quarter was filed on both bases.
            prev = out[cid].get(cq)
            if prev and prev[0] == "IFRS 17" and r["basis"] == "IFRS 4":
                continue
            out[cid][cq] = (r["basis"], period_end(cid, r["fiscal_year"], r["quarter"]), mix,
                            g("policy_loans"))
    return out


def osfi_detail():
    """IFRS 17 Level 3 detail per OSFI filer and quarter, plus below-IG bond share."""
    lf2 = collections.defaultdict(lambda: collections.defaultdict(dict))
    want = {v: k for k, v in OSFI_ENTITY.items()}
    for r in read_gz("LF2_core.csv.gz"):
        a = r["address"]
        if r["entity"] in want and a.startswith("P21012") and a.endswith("40") and r["value"]:
            lf2[want[r["entity"]]][(r["fiscal_year"], r["quarter"])][a[6:9]] = float(r["value"])
    lf1 = collections.defaultdict(lambda: collections.defaultdict(dict))
    for r in read_gz("LF1_core.csv.gz"):
        a = r["address"]
        if r["entity"] in want and a.startswith("P20002") and a.endswith("01") and r["value"]:
            lf1[want[r["entity"]]][(r["fiscal_year"], r["quarter"])][a[6:9]] = float(r["value"])
    rows = []
    for cid, periods in lf2.items():
        for (fy, q), v in periods.items():
            l3 = collections.Counter()
            for row, name in LF2_ROWS.items():
                l3[name] += v.get(row, 0.0) / 1000.0
            for row, name in LF1_ROWS.items():
                l3[name] += lf1[cid][(fy, q)].get(row, 0.0) / 1000.0
            bonds = sum(v.get(r_, 0.0) for r_ in ("045", "050", "055", "065", "140", "160",
                                                   "210", "230", "410", "430"))
            big = sum(v.get(r_, 0.0) for r_ in LF2_BELOW_IG)
            rows.append((cid, cal_quarter(cid, fy, q), period_end(cid, fy, q), dict(l3),
                         big / bonds if bonds else None))
    return rows


def osfi_bridge():
    """Same-date IFRS 4 vs IFRS 17 totals: LF1 column 03 (prior period restated) in
    the first IFRS 17 quarter against the last IFRS 4 return. Policy loans are
    left out of both sides; derivative assets and subsidiaries too."""
    want = {v: k for k, v in OSFI_ENTITY.items()}
    first = {}
    for r in read_gz("LF1_core.csv.gz"):
        if r["entity"] not in want:
            continue
        cid = want[r["entity"]]
        p = (int(r["fiscal_year"]), r["quarter"])
        first.setdefault(cid, {})
        first[cid].setdefault(p, {})[r["address"]] = num(r["value"])
    subs = collections.defaultdict(dict)
    for r in read_gz("LF2_core.csv.gz"):
        if r["entity"] in want and r["address"] == "P2101266940":
            subs[want[r["entity"]]][(int(r["fiscal_year"]), r["quarter"])] = num(r["value"])
    out = {}
    for cid, periods in first.items():
        p0 = min(periods)
        v = periods[p0]
        if p0[1] != "Q1":
            continue
        restated = sum(v.get(a, 0.0) for a in ("P2000201003", "P2000207003", "P2000208003", "P2000211003"))
        restated -= subs[cid].get(p0, 0.0)  # restated subsidiaries not filed; current quarter used
        out[cid] = restated / 1000.0
    return out


# ---------------------------------------------------------------- iA packages

def ia_packages():
    """{cal_q: {basis: {class or detail key: C$ mm}}} from every iA package.
    Later packages overwrite earlier ones for the same quarter and basis."""
    import openpyxl
    warnings.filterwarnings("ignore")
    files = []
    for f in glob.glob(os.path.join(ROOT, "docs", "ia", "*", "*.xlsx")):
        if os.path.getsize(f) < 2048:
            continue  # Git LFS pointer, file not pulled
        try:
            wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        except Exception:
            continue
        if "Invested Assets" not in wb.sheetnames:
            continue
        files.append((f, wb))

    def pub_key(cols):
        return max(qkey(f"{y}{q}") for y, q in cols.values())

    parsed = []
    for f, wb in files:
        ws = wb["Invested Assets"]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        cols, section, seen = {}, "", set()
        data = collections.defaultdict(dict)
        last_pub = None
        for i, r in enumerate(rows):
            if sum(1 for c in r if isinstance(c, str) and re.fullmatch(r"Q[1-4]", c.strip())) >= 4:
                yr, y, cols = rows[i - 1], None, {}
                for j, c in enumerate(r):
                    if j < len(yr) and isinstance(yr[j], (int, float)) and yr[j] > 2000:
                        y = int(yr[j])
                    if isinstance(c, str) and re.fullmatch(r"Q[1-4]", c.strip()) and y:
                        cols[j] = (y, c.strip())
                continue
            lab = next((c for c in r if isinstance(c, str) and c.strip()), None)
            if not lab or not cols:
                continue
            lab = re.sub(r"\s+", " ", lab).strip().rstrip("0123456789").strip()
            vals = {(y, q): r[j] for j, (y, q) in cols.items() if j < len(r) and isinstance(r[j], (int, float))}
            if not vals:
                section = lab
                continue
            key = f"{section}|{lab}"
            if key in seen:
                continue
            seen.add(key)
            for (y, q), v in vals.items():
                data[f"{y}Q{q[1]}"][key] = v
        if data:
            # The publication quarter is the latest quarter carrying a book value.
            book = [k for k, d in data.items() if any(s.endswith("|Book value of investment portfolio") and d[s]
                                                    for s in d)]
            last_pub = max(book, key=qkey) if book else None
        parsed.append((last_pub, f, data))
    parsed.sort(key=lambda t: (qkey(t[0]) if t[0] else -1))

    out = collections.defaultdict(dict)
    for pub, f, data in parsed:
        if not pub:
            continue
        basis_pub = "IFRS 17" if qkey(pub) >= qkey("2023Q1") else "IFRS 4"
        for cq, d in data.items():
            if qkey(cq) > qkey(pub):
                continue
            total = next((d[k] for k in d if k.endswith("|Book value of investment portfolio")), None)
            if not total:
                continue
            scale = 1e6 if total > 1e7 else 1.0
            total = total / scale

            def get(*labels, section=None):
                for k, v in d.items():
                    s, l = k.split("|", 1)
                    if l in labels and (section is None or section in s):
                        if basis_pub == "IFRS 4" and abs(v) <= 1.0:
                            return v * total  # IFRS 4 packages give shares of the book value
                        return v / (1e6 if abs(v) > 1e5 else 1.0)
                return None

            cat = "asset category"
            mix = {
                "Cash & short-term": get("Cash and short-term investments", section=cat),
                "Bonds": get("Bonds", section=cat),
                "Mortgages & loans": get("Mortgages and other loans", "Loans (including mortgages)", section=cat),
                "Equities": get("Stocks", section=cat),
                "Real estate": get("Real estate", "Investment properties", section=cat),
                "Other invested assets": get("Other", section=cat),
            }
            if any(v is None for v in mix.values()):
                continue
            rec = {"mix": mix, "policy_loans": get("Policy loans", section=cat) or 0.0, "total_reported": total,
                   "source": os.path.relpath(f, ROOT)}
            if basis_pub == "IFRS 17":
                det = {
                    "Government Bonds": (get("Governments", section="issuer") or 0) + (get("Municipalities", section="issuer") or 0),
                    "Corporate Bonds": get("Corporates – Public issues", "Corporates - Public issues", section="issuer"),
                    "Illiquid Term Loans": get("Corporates – Private issues", "Corporates - Private issues", section="issuer"),
                    "Commercial Mortgages": get("Book value of mortgages", section="Loans"),
                    "Private Liquid Loans": get("Book value of corporate loans", section="Loans"),
                    "Policy & Other Loans": get("Book value of car loans and other loans", section="Loans"),
                    "Common Shares": get("Public equity", section="Stocks"),
                    "Other Private Equity": get("Private equity and infrastructure", section="Stocks"),
                    "Real Estate Equity": mix["Real estate"],
                    "Cash": mix["Cash & short-term"],
                }
                if all(det.get(k) is not None for k in ("Corporate Bonds", "Illiquid Term Loans", "Common Shares")):
                    if det["Commercial Mortgages"] is None:
                        det["Commercial Mortgages"] = mix["Mortgages & loans"]
                    det = {k: (v or 0.0) for k, v in det.items()}
                    det["Other / Unclassified"] = max(sum(mix.values()) - sum(det.values()), 0.0)
                    rec["detail"] = det
            out[cq][basis_pub] = rec
    return out


# ---------------------------------------------------------------- annual peers

def annual_points():
    """{cid: {year: (basis, {class: C$ mm}, source)}} from annual_points.csv."""
    out = collections.defaultdict(dict)
    with open(os.path.join(HERE, "annual_points.csv"), newline="") as f:
        for r in csv.DictReader(f):
            d = out[r["company_id"]].setdefault((r["year"], r["basis"]), {"mix": collections.Counter(), "source": r["source"]})
            if r["class"] in CLASS_NAMES:
                d["mix"][r["class"]] += float(r["amount_cad_mm"])
    return out


# ---------------------------------------------------------------- market data

def market_context(refresh):
    """Month-end long Canada yield, USD/CAD and S&P/TSX composite level, cached in
    market_context.csv (Bank of Canada Valet; S&P/TSX monthly closes from Yahoo Finance)."""
    path = os.path.join(HERE, "market_context.csv")
    cols = ["month", "long_canada_yield_pct", "usdcad", "tsx_close"]
    if os.path.exists(path) and not refresh:
        with open(path, newline="") as f:
            return list(csv.DictReader(f))
    obs = collections.defaultdict(dict)
    for col, sid in {"long_canada_yield_pct": "BD.CDN.LONG.DQ.YLD", "usdcad": "FXUSDCAD"}.items():
        url = f"https://www.bankofcanada.ca/valet/observations/{sid}/json?start_date=2019-10-01"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            for o in json.load(resp)["observations"]:
                if sid in o and o[sid].get("v"):
                    obs[o["d"][:7]][col] = float(o[sid]["v"])  # last business day wins
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPTSE?interval=1mo&range=10y"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        res = json.load(resp)["chart"]["result"][0]
    import datetime
    for t, v in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]):
        m = (datetime.datetime.fromtimestamp(t, datetime.timezone.utc) - datetime.timedelta(hours=6)).strftime("%Y-%m")
        if v and m >= "2019-10":
            obs[m]["tsx_close"] = round(v, 2)
    today = datetime.date.today().strftime("%Y-%m")
    rows = [{"month": m, **obs[m]} for m in sorted(obs) if m < today]
    write_csv(path, rows, cols)
    return [{k: str(v) for k, v in r.items()} for r in rows]


def market_returns(market):
    """{month: (long yield %, TSX level)} for the drift estimate."""
    out = {}
    for r in market:
        if r.get("long_canada_yield_pct") and r.get("tsx_close"):
            out[r["month"]] = (float(r["long_canada_yield_pct"]), float(r["tsx_close"]))
    return out


def market_drift(shares, end_a, end_b, mkt):
    """Change in each class's share (pp) that market prices alone would cause between two
    balance dates if nothing were traded: bonds reprice with the long Canada yield at an
    assumed BOND_DURATION, equities with the S&P/TSX composite, everything else held flat."""
    a, b = mkt.get(end_a[:7]), mkt.get(end_b[:7])
    if not a or not b:
        return None
    r = {c: 0.0 for c in CLASS_NAMES}
    r["Bonds"] = -BOND_DURATION * (b[0] - a[0]) / 100.0
    r["Equities"] = b[1] / a[1] - 1.0
    grown = {c: shares[c] * (1 + r[c]) for c in CLASS_NAMES}
    tot = sum(grown.values())
    return {c: 100 * (grown[c] / tot - shares[c]) for c in CLASS_NAMES} if tot else None


# ---------------------------------------------------------------- assembly

def main():
    refresh = "--refresh-market" in sys.argv
    hist = osfi_history()
    detail_rows = osfi_detail()
    bridge_osfi = osfi_bridge()
    ia = ia_packages()
    annual = annual_points()
    market = market_context(refresh)
    mkt = market_returns(market)

    # series[cid] = list of dicts {period, period_end, basis, freq, mix, source}
    series = collections.defaultdict(list)
    for cid, periods in hist.items():
        for cq, (basis, end, mix, _pl) in periods.items():
            if qkey(FIRST) <= qkey(cq) <= qkey(LAST):
                series[cid].append({"period": cq, "period_end": end, "basis": basis, "freq": "Quarterly",
                                    "mix": mix, "source": "OSFI " + ("10Q return" if basis == "IFRS 4" else "LF1/LF2 returns")
                                    + f", {OSFI_ENTITY[cid]}"})
    for cq, by in ia.items():
        if qkey(cq) < qkey(FIRST):
            continue
        basis = "IFRS 17" if qkey(cq) >= qkey("2023Q1") else "IFRS 4"
        rec = by.get(basis)
        if rec:
            series["ia"].append({"period": cq, "period_end": f"{cq[:4]}-{QUARTER_END['Q' + cq[5]]}", "basis": basis,
                                 "freq": "Quarterly", "mix": rec["mix"], "source": "iA supplementary package: "
                                 + os.path.basename(rec["source"])})
    for cid, pts in annual.items():
        years = collections.defaultdict(dict)
        for (y, basis), d in pts.items():
            years[y][basis] = d
        for y, by in years.items():
            basis = "IFRS 17" if int(y) >= 2022 and "IFRS 17" in by else ("IFRS 4" if "IFRS 4" in by else "IFRS 17")
            # 2021 on IFRS 17 exists only as the restated transition balance; use the
            # IFRS 4 figure where the insurer published one so the break sits at 2022/2023.
            if y == "2021" and "IFRS 4" in by:
                basis = "IFRS 4"
            if y == "2022" and "IFRS 4" in by:
                basis = "IFRS 4"
            d = by[basis]
            series[cid].append({"period": f"{y}Q4", "period_end": f"{y}-12-31", "basis": basis, "freq": "Annual",
                                "mix": dict(d["mix"]), "source": d["source"]})

    mix_rows, change_rows, cum_rows, flag_rows = [], [], [], []
    latest, pts_by = {}, {}
    for cid in COMPANIES:
        pts = sorted(series.get(cid, []), key=lambda p: qkey(p["period"]))
        if not pts:
            continue
        pts_by[cid] = pts
        latest[cid] = pts[-1]["period"]
        for p in pts:
            p["mix"] = {c: max(p["mix"].get(c, 0.0) or 0.0, 0.0) for c in CLASS_NAMES}
            p["total"] = sum(p["mix"].values())
            for c in CLASS_NAMES:
                mix_rows.append({
                    "company_id": cid, "company": COMPANIES[cid], "focus": int(cid == FOCUS),
                    "period": p["period"], "period_end": p["period_end"], "basis": p["basis"],
                    "frequency": p["freq"], "asset_class": c, "level2": LEVEL2[c],
                    "amount_cad_mm": p["mix"][c], "share_pct": 100 * p["mix"][c] / p["total"] if p["total"] else 0.0,
                    "total_cad_mm": p["total"], "source": p["source"],
                })

    # Same-date bridge across the accounting switch: the last IFRS 4 balance against
    # the same date restated on IFRS 17 / IFRS 9 (by class where the insurer shows it).
    bridge_rows, restate_pct, restate_shares = [], {}, {}
    for cid, pts in pts_by.items():
        last4 = [p for p in pts if p["basis"] == "IFRS 4"]
        if not last4:
            continue
        p4 = last4[-1]
        restated, src, by_class = None, "", None
        if cid in bridge_osfi:
            restated, src = bridge_osfi[cid], "OSFI LF1 prior period restated (first IFRS 17 quarter)"
        elif cid == "ia" and "IFRS 17" in ia.get(p4["period"], {}):
            rec = ia[p4["period"]]["IFRS 17"]
            restated, src, by_class = sum(rec["mix"].values()), "iA 2023 package, 2022 restated", rec["mix"]
        elif cid in annual:
            d = annual[cid].get((p4["period"][:4], "IFRS 17"))
            if d:
                restated, src, by_class = sum(d["mix"].values()), d["source"], dict(d["mix"])
        if restated is None:
            continue
        restate_pct[cid] = 100 * (restated / p4["total"] - 1) if p4["total"] else 0.0
        if by_class:
            restate_shares[cid] = {c: by_class.get(c, 0.0) / restated for c in CLASS_NAMES}
        if cid in hist:
            pl = hist[cid].get(p4["period"], (None, None, None, 0.0))[3]
        else:
            pl = ia[p4["period"]]["IFRS 4"]["policy_loans"] if cid == "ia" else None
        bridge_rows.append({"company_id": cid, "company": COMPANIES[cid], "focus": int(cid == FOCUS),
                            "date": p4["period_end"], "period": p4["period"], "ifrs4_cad_mm": p4["total"],
                            "ifrs17_restated_cad_mm": restated, "restatement_pct": restate_pct[cid],
                            "policy_loans_removed_cad_mm": pl, "source": src,
                            "treatment": ("restated by class" if by_class else
                                          "restatement under 1%: switch quarter counted" if abs(restate_pct[cid]) < 1
                                          else "switch quarter excluded")})
        if by_class:
            for c in CLASS_NAMES:
                s4 = p4["mix"][c] / p4["total"]
                bridge_rows[-1][f"ifrs4_share_{c}"] = 100 * s4
                bridge_rows[-1][f"ifrs17_share_{c}"] = 100 * restate_shares[cid][c]

    for cid, pts in pts_by.items():
        # quarter-on-quarter (or year-on-year for annual filers) changes
        for a, b in zip(pts, pts[1:]):
            gap = qkey(b["period"]) - qkey(a["period"])
            flag, note, mode = "", "", ""
            size = (b["total"] / a["total"] - 1) if a["total"] else 0.0
            if a["basis"] != b["basis"]:
                flag = "IFRS 17 switch"
                rp = restate_pct.get(cid)
                note = f"{a['period']} is the last IFRS 4 filing and {b['period']} the first on IFRS 17 / IFRS 9."
                if cid in restate_shares:
                    mode = "class"
                    note += (f" The insurer restated the {a['period']} balance by class ({rp:+.1f}% in total), so the "
                             "restatement is taken out class by class and the rest counts as reallocation.")
                elif rp is not None and abs(rp) < 1:
                    mode = "count"
                    note += (f" Restating the same date moved invested assets by only {rp:+.1f}%, so the quarter's "
                             "change is counted as reallocation (classification between the two returns may still differ).")
                else:
                    mode = "exclude"
                    note += ((f" Restating the same date moved invested assets by {rp:+.1f}%" if rp is not None
                              else " No same-date restatement is available") +
                             ", so the quarter is kept out of the reallocation totals.")
                if abs(size) > JUMP and gap <= 1:
                    note += f" Invested assets moved {size:+.0%} in the quarter."
            ev = EVENTS.get((cid, b["period"]))
            if ev:
                flag, note, mode = (flag + "; " if flag else "") + "Corporate event", (note + " " if note else "") + ev, "exclude"
            elif abs(size) > JUMP and not flag and gap <= 1:
                flag, mode = "Size jump", "exclude"
                note = (f"Invested assets moved {size:+.0%} in one quarter, which points to a block transfer, "
                        "reinsurance deal or capital move; kept out of the reallocation totals.")
            if flag:
                flag_rows.append({"company_id": cid, "company": COMPANIES[cid], "focus": int(cid == FOCUS),
                                  "from_period": a["period"], "period": b["period"], "flag": flag, "note": note,
                                  "total_change_pct": 100 * size, "treatment": mode})
            drift = None
            if mode != "exclude" and a["total"]:
                drift = market_drift({c: a["mix"][c] / a["total"] for c in CLASS_NAMES}, a["period_end"], b["period_end"], mkt)
            for c in CLASS_NAMES:
                sa = a["mix"][c] / a["total"] if a["total"] else 0.0
                sb = b["mix"][c] / b["total"] if b["total"] else 0.0
                d_pp = 100 * (sb - sa)
                if mode == "class":
                    brk_pp = 100 * (restate_shares[cid][c] - sa)
                elif mode == "exclude":
                    brk_pp = d_pp
                else:
                    brk_pp = 0.0
                change_rows.append({
                    "company_id": cid, "company": COMPANIES[cid], "focus": int(cid == FOCUS),
                    "from_period": a["period"], "period": b["period"], "months": 3 * gap,
                    "asset_class": c, "level2": LEVEL2[c],
                    "share_change_pp": d_pp,
                    "break_pp": brk_pp,
                    "reallocation_pp": d_pp - brk_pp,
                    "market_drift_pp": drift[c] if drift else 0.0,
                    "active_pp": d_pp - brk_pp - (drift[c] if drift else 0.0),
                    "amount_change_cad_mm": b["mix"][c] - a["mix"][c],
                    "reallocation_cad_mm": (d_pp - brk_pp) / 100 * b["total"],
                    "growth_cad_mm": sa * (b["total"] - a["total"]),
                    "flag": flag,
                })
        # cumulative change from the first to the latest filing
        first_p, last_p = pts[0], pts[-1]
        for c in CLASS_NAMES:
            share = lambda p: 100 * p["mix"][c] / p["total"] if p["total"] else 0.0
            ch = [r for r in change_rows if r["company_id"] == cid and r["asset_class"] == c]
            sw = sum(r["break_pp"] for r in ch if r["flag"].startswith("IFRS 17") and "event" not in r["flag"])
            ev = sum(r["break_pp"] for r in ch if r["flag"] and not (r["flag"].startswith("IFRS 17") and "event" not in r["flag"]))
            total_pp = share(last_p) - share(first_p)
            cum_rows.append({
                "company_id": cid, "company": COMPANIES[cid], "focus": int(cid == FOCUS),
                "asset_class": c, "level2": LEVEL2[c],
                "start_period": first_p["period"], "end_period": last_p["period"], "frequency": first_p["freq"],
                "start_share_pct": share(first_p), "end_share_pct": share(last_p),
                "total_change_pp": total_pp, "ifrs17_switch_pp": sw, "event_pp": ev,
                "reallocation_pp": total_pp - sw - ev,
                "market_drift_pp": sum(r["market_drift_pp"] for r in ch),
                "active_pp": sum(r["active_pp"] for r in ch),
                "start_amount_cad_mm": first_p["mix"][c], "end_amount_cad_mm": last_p["mix"][c],
                "amount_change_cad_mm": last_p["mix"][c] - first_p["mix"][c],
                "reallocation_cad_mm": sum(r["reallocation_cad_mm"] for r in ch),
                "start_total_cad_mm": first_p["total"], "end_total_cad_mm": last_p["total"],
            })

    # Peer median share by class for each quarter (quarterly filers other than RBC Life)
    by_pq = collections.defaultdict(list)
    for r in mix_rows:
        if r["frequency"] == "Quarterly" and r["company_id"] != FOCUS:
            by_pq[(r["period"], r["asset_class"])].append(r["share_pct"])
    for (p, c), v in sorted(by_pq.items(), key=lambda t: (qkey(t[0][0]), CLASS_NAMES.index(t[0][1]))):
        v = sorted(v)
        med = v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2
        mix_rows.append({"company_id": "peer_median", "company": COMPANIES["peer_median"], "focus": 0, "period": p,
                         "period_end": "", "basis": "", "frequency": "Quarterly", "asset_class": c,
                         "level2": LEVEL2[c], "amount_cad_mm": "", "share_pct": med, "total_cad_mm": "",
                         "source": f"Median of {len(v)} quarterly filers"})

    # IFRS 17 sub-class detail: OSFI filers plus iA
    det_rows, quality_rows = [], []
    for cid, cq, end, l3, big in detail_rows:
        if qkey(cq) > qkey(LAST):
            continue
        tot = sum(l3.values())
        for k, v in l3.items():
            l1, l2 = LEVEL3[k]
            det_rows.append({"company_id": cid, "company": COMPANIES[cid], "focus": int(cid == FOCUS), "period": cq,
                             "level1": l1, "level2": l2, "level3": k, "amount_cad_mm": v,
                             "share_pct": 100 * v / tot if tot else 0.0})
        if big is not None:
            quality_rows.append({"company_id": cid, "company": COMPANIES[cid], "focus": int(cid == FOCUS), "period": cq,
                                 "below_ig_share_of_bonds_pct": 100 * big})
    for cq, by in ia.items():
        rec = by.get("IFRS 17")
        if rec and "detail" in rec and qkey("2023Q1") <= qkey(cq) <= qkey(LAST):
            tot = sum(rec["detail"].values())
            for k, v in rec["detail"].items():
                l1, l2 = LEVEL3[k]
                det_rows.append({"company_id": "ia", "company": COMPANIES["ia"], "focus": 0, "period": cq,
                                 "level1": l1, "level2": l2, "level3": k, "amount_cad_mm": v,
                                 "share_pct": 100 * v / tot if tot else 0.0})
    det_rows.sort(key=lambda r: (list(COMPANIES).index(r["company_id"]), qkey(r["period"]), list(LEVEL3).index(r["level3"])))
    quality_rows.sort(key=lambda r: (list(COMPANIES).index(r["company_id"]), qkey(r["period"])))

    coverage = []
    for cid, name in COMPANIES.items():
        pts = sorted(series.get(cid, []), key=lambda p: qkey(p["period"]))
        if not pts:
            coverage.append({"company_id": cid, "company": name, "focus": 0, "frequency": "None", "first": "", "last": "",
                             "points": 0, "source": "Not available",
                             "note": "Desjardins Group publishes no stand-alone investment breakdown for its life insurer; "
                                     "life assets are combined with the caisse network and P&C."})
            continue
        coverage.append({"company_id": cid, "company": name, "focus": int(cid == FOCUS), "frequency": pts[0]["freq"],
                         "first": pts[0]["period"], "last": pts[-1]["period"], "points": len(pts),
                         "source": pts[-1]["source"], "note": NOTES.get(cid, OSFI_NOTE if cid in OSFI_ENTITY else "")})

    mix_rows.sort(key=lambda r: (list(COMPANIES).index(r["company_id"]), qkey(r["period"]), CLASS_NAMES.index(r["asset_class"])))
    F_MIX = ["company_id", "company", "focus", "period", "period_end", "basis", "frequency", "asset_class", "level2",
             "amount_cad_mm", "share_pct", "total_cad_mm", "source"]
    F_CH = ["company_id", "company", "focus", "from_period", "period", "months", "asset_class", "level2",
            "share_change_pp", "break_pp", "reallocation_pp", "market_drift_pp", "active_pp", "amount_change_cad_mm", "reallocation_cad_mm",
            "growth_cad_mm", "flag"]
    F_CUM = ["company_id", "company", "focus", "asset_class", "level2", "start_period", "end_period", "frequency",
             "start_share_pct", "end_share_pct", "total_change_pp", "ifrs17_switch_pp", "event_pp",
             "reallocation_pp", "market_drift_pp", "active_pp", "start_amount_cad_mm", "end_amount_cad_mm", "amount_change_cad_mm",
             "reallocation_cad_mm", "start_total_cad_mm", "end_total_cad_mm"]
    F_DET = ["company_id", "company", "focus", "period", "level1", "level2", "level3", "amount_cad_mm", "share_pct"]
    F_FLAG = ["company_id", "company", "focus", "from_period", "period", "flag", "treatment", "note",
              "total_change_pct"]
    F_BR = ["company_id", "company", "focus", "date", "period", "ifrs4_cad_mm", "ifrs17_restated_cad_mm",
            "restatement_pct", "treatment", "policy_loans_removed_cad_mm", "source"]
    F_BRC = ["company_id", "company", "asset_class", "ifrs4_share_pct", "ifrs17_restated_share_pct", "difference_pp"]
    bridge_class = [{"company_id": r["company_id"], "company": r["company"], "asset_class": c,
                     "ifrs4_share_pct": r[f"ifrs4_share_{c}"], "ifrs17_restated_share_pct": r[f"ifrs17_share_{c}"],
                     "difference_pp": r[f"ifrs17_share_{c}"] - r[f"ifrs4_share_{c}"]}
                    for r in bridge_rows if f"ifrs4_share_{CLASS_NAMES[0]}" in r for c in CLASS_NAMES]
    F_COV = ["company_id", "company", "focus", "frequency", "first", "last", "points", "source", "note"]
    F_Q = ["company_id", "company", "focus", "period", "below_ig_share_of_bonds_pct"]
    for d in (HERE, DASH):
        write_csv(os.path.join(d, "mix_history.csv"), mix_rows, F_MIX)
        write_csv(os.path.join(d, "changes.csv"), change_rows, F_CH)
        write_csv(os.path.join(d, "cumulative.csv"), cum_rows, F_CUM)
        write_csv(os.path.join(d, "detail_ifrs17.csv"), det_rows, F_DET)
        write_csv(os.path.join(d, "flags.csv"), flag_rows, F_FLAG)
        write_csv(os.path.join(d, "ifrs17_bridge.csv"), bridge_rows, F_BR)
        write_csv(os.path.join(d, "ifrs17_bridge_by_class.csv"), bridge_class, F_BRC)
        write_csv(os.path.join(d, "coverage.csv"), coverage, F_COV)
        write_csv(os.path.join(d, "bond_quality.csv"), quality_rows, F_Q)
    mq = [dict(r, period=f"{r['month'][:4]}Q{(int(r['month'][5:]) - 1) // 3 + 1}") for r in market
          if int(r["month"][5:]) % 3 == 0 and qkey(FIRST) - 1 <= qkey(f"{r['month'][:4]}Q{int(r['month'][5:]) // 3}") <= qkey(LAST)]
    write_csv(os.path.join(DASH, "market_context.csv"), mq, ["period", "month", "long_canada_yield_pct", "usdcad", "tsx_close"])
    print(f"mix_history: {len(mix_rows)} rows, {len(latest)} insurers; changes: {len(change_rows)}; "
          f"detail: {len(det_rows)}; flags: {len(flag_rows)}; bridge: {len(bridge_rows)}")
    for cid, q in latest.items():
        print(f"  {cid:18s} {len([p for p in series[cid]]):3d} points, latest {q}")


OSFI_NOTE = ("OSFI legal-entity return. Includes the participating account and, for Manulife, Sun Life and Canada "
             "Life, foreign branches and subsidiaries consolidated into the Canadian insurer (C$ moves with FX). "
             "Bonds include private placements; mortgages include residential; equities include those backing "
             "universal life accounts.")
NOTES = {
    "ia": "Consolidated invested assets from iA's quarterly packages. Equities include private equity and "
          "infrastructure held as shares; Other includes derivative assets (not separable before 2023); "
          "Mortgages & loans include car loans. Policy loans excluded.",
    "beneva": "Year-end consolidated statement of financial position (includes P&C). Mutual funds excluded "
              "(mostly pass-through UL and savings funds); equity securities include investments in private companies.",
    "assumption_life": "Year-end note 4 (IFRS 17 from 2022 restated). Pass-through investment fund units excluded; "
                       "participating account included.",
    "humania": "Year-end summary statement of financial position (IFRS 17 from the 1 January 2022 transition balance).",
    "uv_insurance": "Year-end summary statement of financial position, 2024 and 2025 only. 2025 includes the BMO Life block.",
    "peer_median": "Median share of each class across the quarterly filers other than RBC Life (OSFI filers and iA).",
}

if __name__ == "__main__":
    main()
