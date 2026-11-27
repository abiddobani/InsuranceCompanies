"""Build the deep-dive deck on the 20 Canadian life & health insurers in the analysis set.

Primary basis: the ALM framework (MooseDragon/cdn-life-insurer-alm). alm.py reads that repository's processed data and
writes alm.json; every balance-sheet, asset, leverage and capital page here is drawn from it: Canadian business only,
net of reinsurance, "General Account, excl. par / seg fund" (GenAcct), buffer, CSM split, L1/L2/L3 asset taxonomy.
Leadership, corporate structure and partnerships are outside that framework and keep the earlier web research.
Insurers with no OSFI return and no place in the ALM study (Assumption Life, Humania, UV Insurance) keep the earlier
financial-statement pages (the *_fs page builders), labelled as such.

Each insurer gets eight pages: Canadian summary, leadership and pay, corporate structure and entity assessed, assets
and rotation, new money and liabilities, leverage and reinsurance, partnerships, capital and risk.

Every slide is an HTML page (1280 x 720) in the project's dashboard style with inline-SVG charts, printed to PDF
with the preinstalled Playwright Chromium; the .pptx carries native title and source text, the slide body as a
2x image, and the slide's text plus full source URLs in the speaker notes.

Inputs: alm.json (alm.py, run with the ALM repository's uv environment), quant.json (quant.py), research/*.json,
prices.csv. Run from the repository root:
    ALM_REPO=../cdn-life-insurer-alm uv run --project ../cdn-life-insurer-alm python analysis/insurer_deep_dive/alm.py
    python3 analysis/insurer_deep_dive/build_deck.py
"""
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charts import (BLUE, CLASS_COLORS, FOCUS_BG, GREY, GRID, INK, MUTED_BAR, ORANGE, PURPLE, RED, SUB, TEAL,  # noqa: E402
                    esc, grouped_hbar, hbar, line_chart, mix_bar, since_year, stacked_columns, tenure_bars)

HERE = Path(__file__).resolve().parent
OUT_DIR = Path(os.environ.get("DECK_OUT", HERE / "output"))
OUT_DIR.mkdir(parents=True, exist_ok=True)
PDF_OUT = OUT_DIR / "canadian-lh-insurer-deep-dives.pdf"
PPTX_OUT = OUT_DIR / "canadian-lh-insurer-deep-dives.pptx"
NOW = 2026.91  # Nov 27, 2026
TODAY = "Nov 27, 2026"

Q = json.loads((HERE / "quant.json").read_text())
QC = Q["companies"]
PEER = Q["peer_median"]
RES = {}
for p in sorted(Path(os.environ.get("RESEARCH_DIR", HERE / "research")).glob("*.json")):
    try:
        d = json.loads(p.read_text())
        RES[d.get("company_id", p.stem)] = d
    except Exception as e:  # keep building; the coverage page shows the gap
        print("WARN bad research json", p, e)
ORG = {}  # round-2 research: operating entities from the insurer's own site, CEO -> CIO -> all CIO direct reports
for p in sorted((Path(os.environ.get("RESEARCH_DIR", HERE / "research")) / "org").glob("*.json")):
    try:
        d = json.loads(p.read_text())
        ORG[d.get("company_id", p.stem)] = d
    except Exception as e:
        print("WARN bad org json", p, e)
LI = {}  # LinkedIn tenure read from Abid's signed-in browser: research/org/linkedin_tenure.csv overrides start dates
_li = Path(os.environ.get("RESEARCH_DIR", HERE / "research")) / "org" / "linkedin_tenure.csv"
if _li.exists():
    with open(_li) as f:
        for r in csv.DictReader(f):
            LI[(r["company_id"], re.sub(r"\W", "", r["name"].lower()))] = r


def with_li(cid, p):
    """Apply LinkedIn start dates (seat / firm / industry) to a person record when the profile was read."""
    if not p:
        return p
    r = LI.get((cid, re.sub(r"\W", "", str(p.get("name", "")).lower())))
    if not r:
        return p
    q = dict(p)
    for k in ("seat_since", "firm_since", "industry_since"):
        if (r.get(k) or "").strip():
            q[k] = r[k].strip()
    q["tenure_source"] = "LinkedIn"
    if r.get("profile_url"):
        q["sources"] = list(q.get("sources") or []) + [r["profile_url"]]
    if (r.get("title") or "").strip():
        q["li_title"] = r["title"].strip()
    return q


COVERED_BY = {"canada_protection_plan": "Foresters Life"}  # no own balance sheet: underwritten by Foresters Life
PRICES = {}
if (HERE / "prices.csv").exists():
    with open(HERE / "prices.csv") as f:
        for r in csv.DictReader(f):
            PRICES[r["company_id"]] = r

NAMES = {"manulife": "Manulife", "sun_life": "Sun Life", "canada_life": "Canada Life", "ia": "iA Financial Group",
         "desjardins": "Desjardins Insurance", "rbc_life": "RBC Life", "bmo_life": "BMO Life", "beneva": "Beneva",
         "ivari": "ivari", "empire_life": "Empire Life", "equitable_life": "Equitable Life",
         "cooperators_life": "Co-operators Life", "uv_insurance": "UV Insurance", "wawanesa_life": "Wawanesa Life",
         "assumption_life": "Assumption Life", "foresters_life": "Foresters Life",
         "canada_protection_plan": "Canada Protection Plan", "canadian_premier": "Canadian Premier Life",
         "primerica_life": "Primerica Life", "humania": "Humania"}
CLASSES = ["Bonds", "Mortgages (real-estate debt)", "Equity: public", "Equity: private, infra & alts",
           "Equity: commercial real estate", "Cash & short-term"]


# ---------------------------------------------------------------- small helpers
def num(v):
    try:
        if v is None or v == "":
            return None
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def bn(mm, digits=None):
    """C$ millions in; the framework's $MM / $BN out (kept under its old name for the financial-statement pages)."""
    return usd(mm, digits) if num(mm) is not None else "n/d"


PROC = r"search budget|search-budget|this session|firecrawl|earlier-session|earlier session|personal library|library of textbooks|MANDATES\.md|MANDATES file|budget ran out|budget was exhausted"


def scrub(t):
    """Drop research-process remarks (tool budgets, session notes) from text shown in the deck; keep 'unverified' flags."""
    t = str(t or "")
    t = re.sub(r"\b(industry|firm|seat)_since\b", lambda m: m.group(1) + " start year", t)
    t = re.sub(r"\bcomp_total(_cad)?\b", "pay", t)
    t = re.sub(r"\b([a-z_]+)\.json\b", lambda m: f"the {NAMES.get(m.group(1), m.group(1))} section", t)
    if not re.search(PROC, t, re.I):
        return t
    t = re.sub(r"\s*\(([^()]*)\)", lambda m: (" (unverified)" if re.search(r"verif|snippet", m.group(1), re.I) else "")
               if re.search(PROC, m.group(1), re.I) else m.group(0), t)
    t = re.sub(r"[;,]?\s*(and )?(the )?(shared )?(web[- ]?)?search budget (was )?(exhausted|ran out)[^.;]*", "", t, flags=re.I)
    t = re.sub(r"\s*before the (web[- ]?)?search budget ran out", "", t, flags=re.I)
    parts = re.split(r"(?<=[.;])\s+", t)
    t = " ".join(x for x in parts if not re.search(PROC, x, re.I)).strip()
    if re.match(r"^[a-z]", t) or t.count(")") > t.count("("):
        return ""  # what is left is a fragment
    return t


def units(t):
    """Research text to the framework's units: C$2.5bn -> $2.5BN, C$350M -> $350MM (US$ and other currencies keep their prefix)."""
    t = re.sub(r"(?<![A-Z])C\$", "$", str(t))
    t = re.sub(r"(\$\s?\d[\d,.]*)\s?(bn|billion|B)\b", lambda m: m.group(1) + "BN", t)
    t = re.sub(r"(\$\s?\d[\d,.]*)\s?(mm|million|mn|m|M)\b", lambda m: m.group(1) + "MM", t)
    t = re.sub(r"\b(\d[\d.]*)\s?bn\b", r"\1BN", t)
    return re.sub(r"\bGA\b(?! \d{5})", "General Account", t)


def clip(t, n=150):
    t = re.sub(r"\s+", " ", units(scrub(t))).strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def yrs(since):
    s = since_year(since)  # YYYY-MM exact; YYYY assumes a mid-year start
    return None if s is None else max(NOW - s, 0)


def yrs_txt(since):
    y = yrs(since)
    return None if y is None else ("less than a year" if y < 1 else f"{y:.0f} year{'s' if round(y) != 1 else ''}")


def domain(u):
    try:
        h = urlparse(str(u)).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def money(v, cur="CAD", yr=None):
    x = num(v)
    if x is None:
        return None
    sym = {"CAD": "C$", "USD": "US$", "GBP": "£", "EUR": "€"}.get((cur or "CAD").upper(), (cur or "") + " ")
    s = f"{sym}{x / 1e6:,.1f}MM" if x >= 1e5 else f"{sym}{x:,.0f}"
    return s + (f" ({int(yr)})" if num(yr) else "")


def items(lst, n=None):
    out = [x for x in (lst or []) if x not in (None, "", {}, [])]
    return out[:n] if n else out


def txt(x):
    if isinstance(x, dict):
        y = x.get("year") or x.get("date") or ""
        t = x.get("text") or x.get("summary") or ""
        return (f"{y}: " if y and not str(t).startswith(str(y)) else "") + str(t)
    return str(x)


def bullets(lst, n=6, width=150, cls=""):
    lst = [x for x in items(lst) if clip(txt(x), width)][:n]
    if not lst:
        return '<p class="nd">Not publicly disclosed / not found.</p>'
    return f'<ul class="{cls}">' + "".join(f"<li>{esc(clip(txt(x), width))}</li>" for x in lst) + "</ul>"


def card(h2, inner, cap=None, style="", cls=""):
    c = f'<p class="cap">{esc(cap)}</p>' if cap else ""
    h = f"<h2>{esc(h2)}</h2>" if h2 else ""
    return f'<div class="card {cls}" style="{style}">{h}{c}{inner}</div>'


def col(inner, w=None, gap=12):
    st = f"flex:0 0 {w}px;" if w else "flex:1;"
    return f'<div class="col" style="{st}gap:{gap}px">{inner}</div>'


def table(headers, rows, cls="", left=1):
    isl = (lambda i: i in left) if isinstance(left, (set, tuple, list)) else (lambda i: i < left)
    th = "".join(f'<th class="{"l" if isl(i) else ""}">{esc(h)}</th>' for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(f'<td class="{"l" if isl(i) else ""}">{esc(str(v))}</td>'
                                    for i, v in enumerate(r)) + "</tr>" for r in rows)
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def kpi(label, value, sub="", accent=False):
    return (f'<div class="kpi{" acc" if accent else ""}"><span>{esc(label)}</span><b>{esc(units(value))}</b>'
            f'<small>{esc(units(sub))}</small></div>')


SLIDES = []


def slide(title, body, source, tag=None, notes="", cls="", urls=()):
    SLIDES.append(dict(title=title, body=body, source=source, tag=tag, notes=notes, cls=cls, urls=list(urls)))


def collect_urls(obj):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and v.startswith("http"):
                out.append(v)
            else:
                out += collect_urls(v)
    elif isinstance(obj, list):
        for v in obj:
            out += collect_urls(v)
    elif isinstance(obj, str) and obj.startswith("http"):
        out.append(obj)
    return out


def src_line(prefix, urls, n=4):
    ds = []
    for u in urls:
        d = domain(u)
        if d and d not in ds:
            ds.append(d)
    s = prefix
    if ds:
        s += ("; " if s else "") + "web: " + ", ".join(ds[:n]) + (f" +{len(ds) - n} more" if len(ds) > n else "")
    return s


def first_sentence(t):
    t = re.sub(r"\b(Inc|Ltd|Co|Corp|St|No|approx|incl|e\.g|i\.e)\.", lambda m: m.group(0).replace(".", "§"), str(t))
    t = re.split(r"(?<=[a-z0-9\)])\. (?=[A-Z])|; ", t)[0]
    return t.replace("§", ".").rstrip(".")


def short_label(t, n=40):
    return clip(re.sub(r"\s*\([^)]*\)?", "", str(t)), n)


# ---------------------------------------------------------------- research accessors
def R(cid):
    return RES.get(cid, {})


def metric(cid, *keys, exclude=()):
    for m in R(cid).get("metrics", []) or []:
        lab = str(m.get("metric", "")).lower()
        if any(k in lab for k in keys) and not any(x in lab for x in exclude):
            return m
    return None


GENERIC_UNITS = {"", "rating", "people", "headcount", "count", "%", "pct", "fte", "staff", "employees"}


def mfmt(m):
    """Format a research metric for a KPI tile; non-numeric values (ratings) come from unit or note."""
    if not m:
        return None
    v, u = m.get("value"), (m.get("unit") or "").strip()
    x = num(v)
    if x is None:
        first = lambda x: clip(re.split(r"[,;]| / ", x)[0], 18)
        if isinstance(v, str) and v.strip():
            return first(v)
        if u.lower() not in GENERIC_UNITS and not re.search(r"c\$|us\$|\$|\bbn\b|\bmm\b|million|billion|^\w{0,4}$", u, re.I):
            return first(re.sub(r"^rating\s+", "", u, flags=re.I))
        note = str(m.get("note") or "")
        if note and not re.match(r"(not |no |none)", note, re.I):
            return first(re.split(r"[.]", note)[0])
        return None
    ul = u.lower()
    if ul in ("%", "pct", "percent"):
        return f"{x:.1f}%".replace(".0%", "%")
    cur = "US$" if "us" in ul else "€" if "eur" in ul else "C$" if ("c$" in ul or "cad" in ul or "$" in ul) else ""
    if "bn" in ul or "billion" in ul:
        return f"{cur}{x / 1000:,.1f}tn" if x >= 1000 else (f"{cur}{x:,.1f}bn" if x < 100 else f"{cur}{x:,.0f}bn")
    if "mm" in ul or "million" in ul or ul.endswith("m"):
        if x >= 1000:
            b = x / 1000
            return f"{cur}{b:,.2f}bn" if b < 10 else f"{cur}{b:,.1f}bn" if b < 100 else f"{cur}{b:,.0f}bn"
        return f"{cur}{x:,.0f}MM"
    return f"{x:,.0f}" if x >= 100 or x == int(x) else f"{x:,.1f}"


def people(cid, current=True):
    ps = [p for p in (R(cid).get("people") or []) if p.get("name")]
    if current:
        ps = [p for p in ps if not re.search(r"retired|former|predecessor|\(to |until 20|departed|stepped down|outgoing",
                                             f"{p.get('role', '')} {p.get('title', '')}", re.I)
              and not re.match(r"\s*(prior|ex-|previous|interim \(past)", str(p.get("role", "")), re.I)]
    return ps


def tier(p):
    role = str(p.get("role", "")).lower()
    r = role if role.strip() else str(p.get("title", "")).lower()
    if re.search(r"\bneo\b|other|cfo|cro|risk|actuar|chair", role):
        return 4
    if re.search(r"^ceo\b|^president|chief executive", r) and "investment" not in r:
        return 1
    if re.search(r"\bcio\b|chief investment|global head of investments|head of investments", r):
        return 2
    if re.search(r"public|fixed income|liquid|portfolio management|bond", r):
        return 3
    return 4


def ga_mm(cid):
    q = QC.get(cid, {})
    v = num((q.get("landscape") or {}).get("portfolio_cad_mm"))
    if v is None:
        m = metric(cid, "general account", "invested assets", "general fund")
        if m and num(m.get("value")) is not None:
            u = (m.get("unit") or "").lower()
            v = num(m["value"]) * (1000 if "bn" in u else 1)
    return v


def capital(cid):
    """(ratio, label, as_of) preferring the disclosed figure for the main entity."""
    q = QC.get(cid, {})
    for c in q.get("capital_disclosed") or []:
        if num(c.get("total_ratio_pct")) is not None:
            fw = "CARLI" if "CARLI" in str(c.get("framework")) else "LICAT" if "LICAT" in str(c.get("framework")) else "Solvency"
            return num(c["total_ratio_pct"]), fw, f'{c.get("as_at")}, {clip(c.get("entity"), 40)}'
    ls = q.get("landscape") or {}
    if num(ls.get("capital_ratio_pct")) is not None:
        return num(ls["capital_ratio_pct"]), "LICAT", ls.get("capital_ratio_source")
    m = metric(cid, "licat", "carli", "solvency ratio", exclude=("tier 1", "basel", "target"))
    if m and num(m.get("value")) is not None:
        lab = str(m.get("metric")).lower()
        fw = "CARLI" if "carli" in lab or "car" in lab.split() else "LICAT" if "licat" in lab else "Solvency"
        return num(m["value"]), fw, f'{m.get("as_of")} ({clip(m.get("metric"), 40)})'
    return None, None, None


# ---------------------------------------------------------------- ALM framework (primary basis for every Canadian figure)
ALMD = json.loads((HERE / "alm.json").read_text())
AC, AMED = ALMD["companies"], ALMD["peer_median"]
TNAME = {"manulife": "MFC", "sun_life": "SLF", "canada_life": "CLF"}  # the framework's short names for the Big 3
LAB = {"manulife": "MFC", "sun_life": "SLF", "canada_life": "CLF", "ia": "iA", "desjardins": "Desjardins", "rbc_life": "RBC Life",
       "bmo_life": "BMO Life", "beneva": "Beneva", "ivari": "ivari", "empire_life": "Empire Life", "equitable_life": "Equitable",
       "cooperators_life": "Co-operators", "uv_insurance": "UV", "wawanesa_life": "Wawanesa", "assumption_life": "Assumption",
       "foresters_life": "Foresters", "canada_protection_plan": "CPP", "canadian_premier": "Cdn Premier",
       "primerica_life": "Primerica", "humania": "Humania"}
L2_COLORS = {"Public Fixed Income": BLUE, "Private Fixed Income": TEAL, "Public Equity": ORANGE, "Equity": RED,
             "Equity (real estate)": PURPLE, "Cash & Cash Equivalent": "#9fb7d6", "Other / unclassified": GREY}
L2_SHORT = {"Public Fixed Income": "Public fixed income", "Private Fixed Income": "Private fixed income", "Public Equity": "Public equity",
            "Equity": "Private equity and real assets", "Equity (real estate)": "Real estate equity", "Cash & Cash Equivalent": "Cash",
            "Other / unclassified": "Other / unclassified"}
STATUS_TXT = {"study": "ALM study", "built": "Built on ALM rules", "amf": "ALM study, AMF rule", "amf_liab": "ALM study, liabilities only",
              "covered": "Foresters Life brand", "none": "Financial statements only"}
FS_TAG = " · financial-statement basis, outside the ALM study"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def is_licat(b):
    """True for an OSFI LICAT ratio; the AMF basis string reads 'CARLI ... (AMF; not LICAT)'."""
    return str((b or {}).get("cap_basis") or "").startswith("LICAT")


def qdate(p):
    """'2023Q1' -> 'Mar 31, 2023' (calendar quarters; used on the financial-statement pages)."""
    m = re.fullmatch(r"(\d{4})Q([1-4])", str(p or ""))
    return f"{['Mar 31', 'Jun 30', 'Sep 30', 'Dec 31'][int(m.group(2)) - 1]}, {m.group(1)}" if m else str(p or "")


def on_alm(cid):
    return AC.get(cid, {}).get("status") in ("study", "built", "amf", "amf_liab")


def yb(cid, y=2025):
    return (AC.get(cid, {}).get("years") or {}).get(str(y)) or {}


def tn(cid):
    return TNAME.get(cid, NAMES[cid])


def usd(v, d=None):
    """C$ millions in, '$1.2BN' / '$345MM' out (the framework's units; never M or B)."""
    v = num(v)
    if v is None:
        return "n/a"
    sign = "-" if v < 0 else ""
    if abs(v) >= 1000:
        b = abs(v) / 1000
        dd = d if d is not None else (0 if b >= 100 else 1)
        return f"{sign}${b:,.{dd}f}BN"
    return f"{sign}${abs(v):,.0f}MM"


def dfmt(iso):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return f"{MONTHS[int(m.group(2)) - 1]} {int(m.group(3))}, {m.group(1)}" if m else str(iso or "")


def pc(v, d=1, suffix="%"):
    v = num(v)
    return "n/a" if v is None else f"{v:.{d}f}{suffix}"


def peer_vals(key):
    """{cid: fiscal year-end 2025 value} for every insurer on the ALM basis that has the measure."""
    out = {}
    for c in AC:
        v = AC[c].get(key) if key == "alts_share" else yb(c).get(key)
        if on_alm(c) and num(v) is not None:
            out[c] = num(v)
    return out


def peer_hbar(vals, cid, fmt, W=350, rowh=15, label_w=108, right_w=46, color=BLUE, median=None, top=18, tick_target=4):
    """Peers ranked high to low; the section's insurer in colour, RBC Life in lighter blue, peer median as a dashed line (named in the caption)."""
    its = sorted(((LAB[c], v) for c, v in vals.items()), key=lambda x: -x[1])
    return hbar(its, fmt, W=W, rowh=rowh, label_w=label_w, right_w=right_w, focus=LAB[cid], mark="RBC Life", median=median,
                color=color, top=top, tick_target=tick_target)


def rank_txt(vals, cid):
    """'3rd lowest of 14' style position, lowest first."""
    if cid not in vals:
        return ""
    order_ = sorted(vals, key=lambda c: vals[c])
    i = order_.index(cid) + 1
    n = len(order_)
    return f"{i} of {n}, lowest first"


def group_ni(cid):
    m = metric(cid, "net income", "net earnings", "net result", exclude=("core", "underlying"))
    v = mfmt(m) if m else None
    return (v.replace("C$", "$").replace("bn", "BN").replace("tn", "TN") if v else None), m


# ---------------------------------------------------------------- ordering
def order():
    """RBC Life first (the reader's own insurer), then by General Account size on the ALM basis; insurers without an ALM
    balance sheet follow by their financial-statement invested assets. Canada Protection Plan sits after Foresters Life."""
    def size(cid):
        b_ = yb(cid)
        v = num(b_.get("ga")) or ((num(b_.get("fcf")) or 0) + (num(b_.get("csm_total")) or 0))   # liabilities-only view: FCF + CSM
        if v:
            return (0, -v)
        return (1, -(ga_mm(cid) or 0))
    ids = [c for c in NAMES if c not in ("canada_protection_plan", "rbc_life")]
    ids.sort(key=size)
    ids.insert(0, "rbc_life")
    ids.insert(ids.index("foresters_life") + 1, "canada_protection_plan")
    return ids


ORDER = order()


# ---------------------------------------------------------------- page builders
MIX2 = {}  # round-3 research: business mix by geography and by liability type (research/business_mix2.csv)
_m2 = Path(os.environ.get("RESEARCH_DIR", HERE / "research")) / "business_mix2.csv"
if _m2.exists():
    with open(_m2) as f:
        for r_ in csv.DictReader(f):
            d_ = MIX2.setdefault((r_["company_id"], r_["view"].strip().lower()), {"rows": [], "urls": []})
            d_["rows"].append(r_)
            if r_.get("source_url"):
                d_["urls"].append(r_["source_url"])
MIX_COLS = {"geo": [BLUE, TEAL, ORANGE, PURPLE, "#9fb7d6", "#6b8e23", GREY, "#c9a66b"],
            "lia": [BLUE, "#6f9bd1", TEAL, "#7cc3b8", ORANGE, PURPLE, "#d16ba5", RED, GREY]}


def mix_view(cid, view):
    """[(label, pct)], basis. Liability: OSFI LF3 lines + CSM + surplus where filed, else researched. Geography: researched,
    else Canada vs outside Canada from OSFI liabilities."""
    src = COVERED_BY.get(cid) and "foresters_life" or cid
    q = QC.get(src, {})
    m2 = MIX2.get((src, view), {}).get("rows") or []
    if view == "liability" and (q.get("liability_mix") or {}).get("items"):
        lm = q["liability_mix"]
        tot = sum(num(i["amount_cad_mm"]) or 0 for i in lm["items"])
        out = [(i["label"], (num(i["amount_cad_mm"]) or 0) / tot * 100) for i in lm["items"]]
        return out, ("Foresters Life: " if src != cid else "") + f"% of {usd(tot)}; OSFI LF3 P22010 by line (CSM carved out pro rata), CSM, surplus"
    if m2 and view == "geography":
        rows = [(re.sub(r"\s*\(.*?\)", "", x["label"]).strip(), num(x.get("amount_cad_mm")), num(x.get("pct"))) for x in m2]
        neg = any((a or 0) < 0 for _, a, _ in rows)
        pos = [(l, a if a is not None else p) for l, a, p in rows if (a if a is not None else p or 0) > 0]
        tot = sum(v for _, v in pos) or 1
        out = [(clip(l, 34), v / tot * 100) for l, v in pos]
        b = m2[0]
        basis = re.sub(r";\s*pct of [^;]*", "", b.get("basis") or "")
        if neg:
            basis += "; negative corporate segment excluded"
        return out, ("Foresters Life: " if src != cid else "") + clip(basis, 120)
    if m2:  # liability view from annual-report notes (non-OSFI filers)
        lines, csm, sur, inv = [], 0.0, None, 0.0
        for x in m2:
            lab, a = x["label"], num(x.get("amount_cad_mm"))
            if a is None or a <= 0 or "reinsurance contracts held" in lab or (re.search(r"segregat|seg-fund", lab, re.I)
                                                                             and "general fund" not in lab):
                continue
            if lab.startswith("CSM"):
                csm += a
            elif re.search(r"equity|surplus", lab, re.I):
                sur = a
                sur_lab = "Surplus (group, incl. P&C)" if "P&C" in lab else "Surplus"
            elif lab.lower().startswith("investment contract"):
                inv += a
            else:
                short = re.sub(r"^Insurance contract liabilities\s*-?\s*", "", lab)
                short = {"(all lines)": "Insurance contracts, all lines"}.get(short, short)
                short = re.sub(r"^contracts not under PAA.*", "Individual & annuities (non-PAA)", short)
                short = re.sub(r"^contracts under PAA.*", "Group (PAA)", short)
                short = re.sub(r",? general fund.*$| \(.*?\)$", "", short).strip()
                lines.append((clip(short, 34), a))
        icl = sum(a for _, a in lines)
        k = (icl - csm) / icl if icl and csm < icl else 1
        out = [(l, a * k) for l, a in lines] + ([("Investment contracts", inv)] if inv else []) + \
              ([("CSM", csm)] if csm else []) + ([(sur_lab, sur)] if sur else [])
        tot = sum(a for _, a in out) or 1
        out = [(l, a / tot * 100) for l, a in out]
        gaps = [w for w, ok in (("CSM", csm), ("surplus", sur)) if not ok]
        asof = next((m.group(0) for x in m2 for m in [re.search(r"20\d\d-\d\d-\d\d", (x.get("as_of") or "") + (x.get("basis") or ""))] if m), "")
        basis = (f"% of {usd(tot)}; annual-report notes {asof}, general fund (segregated funds excluded), CSM carved out of lines pro rata"
                 + (f"; {' and '.join(gaps)} not disclosed" if gaps else ""))
        return out, ("Foresters Life: " if src != cid else "") + basis
    if view == "geography" and num((q.get("liability_mix") or {}).get("canada_share")) is not None:
        c = num(q["liability_mix"]["canada_share"])
        return [("Canada", c)] + ([("Outside Canada", 100 - c)] if c < 99.5 else []), "Insurance contract liabilities, Canada vs total (OSFI LF3)"
    return [], ""


def mix_html(its, kind):
    if not its:
        return '<p class="nd">Not disclosed.</p>'
    cols = MIX_COLS[kind]
    leg = "".join(f'<div class="lgrow"><i style="background:{cols[i % len(cols)]}"></i><span>{esc(l)}</span><b>{p:.0f}%</b></div>'
                  for i, (l, p) in enumerate(its[:8]))
    return '<div style="flex-shrink:0;height:22px">' + mix_bar(its[:8], colors=cols, W=420, h=22) + f'</div><div class="lg2">{leg}</div>'


def page_summary_fs(cid, n):
    r, q = R(cid), QC.get(cid, {})
    name = NAMES[cid]
    ga = ga_mm(cid)
    cap, fw, cap_asof = capital(cid)
    tiles = []
    ga_src = (q.get("landscape") or {}).get("portfolio_as_of")
    tiles.append(kpi("General Account invested assets (financial statements)", bn(ga) if ga else "n/d",
                     f"as at {ga_src}" if ga_src else "", accent=True))
    tiles.append(kpi(f"Capital ratio ({fw or 'n/d'})", f"{cap:.0f}%" if cap else "n/d",
                     f"as at {clip(cap_asof, 60)}" if cap_asof else "not disclosed", accent=True))
    used = set()
    picks = [("Aggregate AUM / AUMA", ("aum", "assets under management", "auma"), ()),
             ("Total assets", ("total assets",), ()),
             ("Net income", ("net income", "net earnings", "net result"), ("core", "underlying")),
             ("Core / underlying earnings", ("core", "underlying", "adjusted", "base earnings"), ()),
             ("Investment team", ("investment team", "investment professionals", "investments team", "investment specialists", "team headcount", "team size"), ()),
             ("Employees", ("employees", "headcount"), ("investment",)),
             ("Financial leverage", ("leverage",), ()),
             ("Credit rating", ("rating", "financial strength"), ())]
    for lab, keys, exc in picks:
        m = metric(cid, *keys, exclude=exc)
        if m and id(m) not in used:
            used.add(id(m))
            tiles.append(kpi(lab, mfmt(m) or "n/d", clip(f"{m.get('metric')}" + (f" · {m['as_of']}" if m.get("as_of") else ""), 70)))
        else:
            tiles.append(kpi(lab, "n/d", "not found / not disclosed"))
    pr = PRICES.get(cid)
    if pr and pr.get("price"):
        tiles.append(kpi(f"Share price ({pr['ticker']})", pr["price"], clip(f"{pr.get('as_of', '')}" + (" · listed parent" if "parent" in str(pr.get("ticker")) else ""), 48)))
        tiles.append(kpi("Market cap", pr.get("market_cap") or "n/d", clip(pr.get("note") or "insurer", 48)))
    else:
        own = r.get("ownership") or q.get("ownership") or ""
        tiles.append(kpi("Share price", "Not listed", clip(own, 48)))
        tiles.append(kpi("Market cap", "Not listed", ""))
    grid = '<div class="kgrid">' + "".join(tiles[:12]) + "</div>"

    bm = r.get("business_mix") or {}
    geo, geo_basis = mix_view(cid, "geography")
    lia, lia_basis = mix_view(cid, "liability")
    its = geo or lia
    own = clip(r.get("ownership") or q.get("ownership"), 120)
    reg = r.get("regulator") or q.get("regulator") or ""
    profile = (f'<p class="kv one"><b>Ownership</b> {esc(clip(own, 62))}</p><p class="kv one"><b>Regulator</b> {esc(clip(reg, 60))}</p>')
    gaps = items(r.get("gaps"), 3)
    gap_html = card("Not disclosed / gaps", bullets(gaps, 2, 80, "sm") if gaps else '<p class="nd">None flagged.</p>', cls="warn")
    right = col(card("Business mix: geography", mix_html(geo, "geo"), cap=clip(geo_basis, 95), style="flex:0 0 158px")
                + card("Business mix: liabilities by type, incl. CSM and surplus", mix_html(lia, "lia"), cap=clip(lia_basis, 110), style="flex:0 0 180px")
                + card("", profile, style="flex:0 0 58px") + gap_html, w=452)
    body = col(grid, w=724) + right
    title = f"{name}: {bn(ga) if ga else 'undisclosed'} General Account"
    if cap:
        title += f", {fw} {cap:.0f}%"
    if lia:
        top = max([x for x in lia if not x[0].startswith(("CSM", "Surplus"))] or lia, key=lambda x: x[1])
        tl = {"Outside Canada": "business outside Canada", "Insurance, Canada": "Canadian insurance",
              "Participating": "participating business", "Group annuities / PRT": "group annuities / PRT",
              "Individual & annuities": "individual insurance and annuities"}.get(top[0], short_label(top[0]).lower())
        if top[0].startswith("Insurance contracts, all lines"):
            title += f"; insurance contracts are {top[1]:.0f}% of liabilities plus surplus (no split by line published)"
        else:
            title += f"; {tl} is the largest liability ({top[1]:.0f}%)"
    urls = collect_urls({"m": r.get("metrics"), "b": bm}) + [u for u in (MIX2.get((cid, "geography"), {}).get("urls") or [])]
    src = src_line("OSFI LF2/LCQ returns and annual reports (project dataset)", urls)
    notes = "\n".join(f"- {m.get('metric')}: {m.get('value')} {m.get('unit') or ''} ({m.get('as_of')}) {m.get('note') or ''} {m.get('source') or ''}"
                      for m in (r.get("metrics") or []))
    slide(title, body, src, tag=(n, name, "Summary" + FS_TAG), notes=notes, urls=urls)


def lead(cid):
    """CEO, CIO, CIO direct reports and other leaders: round-2 org research when present, else round-1 tiers."""
    o = ORG.get(cid)
    if cid in COVERED_BY and o and not (o.get("cio") or {}).get("name"):
        o = dict(o, cio=(ORG.get("foresters_life") or {}).get("cio"),
                 cio_direct_reports=(ORG.get("foresters_life") or {}).get("cio_direct_reports"))
    if o:
        ok = lambda p: isinstance(p, dict) and p.get("name")
        w = lambda p: with_li(cid, p)
        return dict(ceo=w(o.get("ceo")) if ok(o.get("ceo")) else None, cio=w(o.get("cio")) if ok(o.get("cio")) else None,
                    drs=[w(p) for p in o.get("cio_direct_reports") or [] if ok(p)],
                    others=[w(p) for p in o.get("other_leaders") or [] if ok(p)][:3], src="org")
    ps = people(cid)
    t = {k: [p for p in ps if tier(p) == k] for k in (1, 2, 3, 4)}
    return dict(ceo=(t[1] or [None])[0], cio=(t[2] or [None])[0], drs=t[3], others=t[4][:3], src="r1")


COMP = {}  # round-3: summary compensation table components (research/comp.csv), keyed by normalised name
_cp = Path(os.environ.get("RESEARCH_DIR", HERE / "research")) / "comp.csv"
if _cp.exists():
    with open(_cp) as f:
        for r_ in csv.DictReader(f):
            if num(r_.get("total_sct")):
                COMP[re.sub(r"\W", "", re.sub(r",.*|\(.*", "", r_["name"]).lower())] = r_


def comp_row(p):
    if not p:
        return None
    k = re.sub(r"\W", "", re.sub(r",.*|\(.*", "", str(p.get("name", ""))).lower())
    if k in COMP:
        return COMP[k]
    last = str(p.get("name", "")).split(",")[0].split()[-1:] or [""]
    hits = [v for kk, v in COMP.items() if last[0].lower() and kk.endswith(last[0].lower()) and kk[:3] == k[:3]]
    return hits[0] if len(hits) == 1 else None


def pay(p):
    """Total compensation from the summary compensation table (base, bonus, share- and option-based awards, pension,
    other) where researched; else the round-2 figure."""
    if not p:
        return None
    c = comp_row(p)
    if c:
        return money(c["total_sct"], c.get("currency") or "CAD", c.get("year"))
    return money(p.get("comp_total_cad") or p.get("comp_total"), p.get("comp_currency"), p.get("comp_year"))


def pay_split(p):
    c = comp_row(p)
    if not c:
        return ""
    cur = {"USD": "US$", "CAD": "C$"}.get((c.get("currency") or "CAD").upper(), "")
    eq = (num(c.get("share_based")) or 0) + (num(c.get("option_based")) or 0)
    cash = (num(c.get("annual_incentive")) or 0) + (num(c.get("long_term_incentive_non_equity")) or 0)
    oth = (num(c.get("pension_value")) or 0) + (num(c.get("all_other")) or 0)
    f = lambda v: f"{v / 1e6:.1f}"
    return f"base {f(num(c.get('base_salary')) or 0)} · bonus {f(cash)} · equity {f(eq)} · other {f(oth)} ({cur}MM)"


def person_box(p, role, cls="big"):
    if not p:
        return (f'<div class="pbox {cls} empty"><div class="role">{esc(role)}</div><div class="pname">Not named</div>'
                f'<div class="ptitle">Not identified in public sources</div></div>')
    big = cls == "big"
    comp = pay(p)
    tag = ""
    rl = str(p.get("reporting_line") or "")
    if rl:
        tag = f'<span class="rl {"st" if rl.startswith("stated") else "inf"}">{"reporting line stated" if rl.startswith("stated") else "inferred from title"}</span>'
    split = pay_split(p)
    comp_html = (f'<div class="comp"><span>{esc(split) if split else "Total pay (base + bonus + equity)"}</span><b>{esc(comp)}</b></div>' if comp else
                 '<div class="comp nd"><span>Total pay (base + bonus + equity)</span><b>Not disclosed</b></div>')
    w = 380 if big else (266 if "fn" in cls else 196)
    title_max = 95 if big else (90 if "fn" in cls else 64)
    bars = tenure_bars(p, W=w - 24) if big else tenure_bars(p, W=w - 20, lw=46, rw=60, compact=True)
    inf = " inf" if rl and not rl.startswith("stated") else ""
    return (f'<div class="pbox {cls}{inf}"><div class="role">{esc(clip(role, 40))}{tag}</div>'
            f'<div class="pname">{esc(clip(p.get("name"), 34))}</div><div class="ptitle">{esc(clip(p.get("title"), title_max))}</div>'
            f'{bars}' + (comp_html if big else "") + "</div>")


FUNC_SLOTS = [("public_markets", "Public markets"), ("private_markets", "Private markets / alts"),
              ("direct_lending", "Direct lending / private credit"), ("trading", "Trading"), ("real_assets", "Real assets"),
              ("alm", "ALM / total portfolio")]
FUNC_RX = {"public_markets": r"public|fixed income|liquid|bond|core fi", "private_markets": r"private markets|private equity|alternativ|multi-strat",
           "direct_lending": r"private (debt|credit|placement|fixed)|direct lend|commercial mortgage|mortgage|loan",
           "trading": r"trading|treasury|cash|collateral|execution", "real_assets": r"real (estate|asset)|realty|infra",
           "alm": r"\balm\b|asset.liability|total (fund|portfolio)|asset allocation|portfolio strateg|investment strateg"}
FUNCS = {}  # round-3: research/org/cio_functions.csv
_fc = Path(os.environ.get("RESEARCH_DIR", HERE / "research")) / "org" / "cio_functions.csv"
if _fc.exists():
    with open(_fc) as f:
        for r_ in csv.DictReader(f):
            if (r_.get("name") or "").strip():
                d_ = {k: (v or "").strip() or None for k, v in r_.items()}
                d_["sources"] = [d_["source_url"]] if d_.get("source_url") else []
                FUNCS.setdefault(r_["company_id"], {})[r_["function"].strip()] = d_


def cio_slots(cid, drs):
    """Fill the six function slots under the CIO: researched function heads first, then round-2 direct reports by title."""
    src = "foresters_life" if cid in COVERED_BY else cid
    got = {fn: with_li(cid, p) for fn, p in (FUNCS.get(src) or {}).items() if fn in dict(FUNC_SLOTS)}
    used = {str(p.get("name")).lower() for p in got.values()}
    for p in drs:
        if str(p.get("name")).lower() in used:
            continue
        for fn, _ in FUNC_SLOTS:
            if fn not in got and re.search(FUNC_RX[fn], str(p.get("title")), re.I):
                got[fn] = p
                used.add(str(p.get("name")).lower())
                break
    extra = [p for p in drs if str(p.get("name")).lower() not in used]
    return got, extra


def page_org(cid, n):
    name = NAMES[cid]
    L = lead(cid)
    ceo, cio, drs = L["ceo"], L["cio"], L["drs"]
    via = ""
    if cio and ceo and cio.get("reports_to") and ceo.get("name") and ceo["name"].split()[-1].lower() not in str(cio["reports_to"]).lower() \
            and not re.search(r"\bceo\b|chief executive|president", str(cio["reports_to"]), re.I):
        via = f'<div class="via">CIO reports to {esc(clip(cio["reports_to"], 60))}</div>'
    slot_people, extra = cio_slots(cid, drs)
    boxes = []
    for fn, lab in FUNC_SLOTS:
        p = slot_people.get(fn)
        if p:
            rl = str(p.get("reporting_line") or "")
            tag = "stated" if rl.startswith("stated") else "via asset manager" if rl.startswith("functional") else "inferred" if rl else ""
            boxes.append(person_box(p, lab + (f" · {tag}" if tag else ""), "sm fn"))
        else:
            boxes.append(f'<div class="pbox sm fn empty"><div class="role">{esc(lab)}</div><div class="pname">Not named</div>'
                         f'<div class="ptitle">No public source names this head</div></div>')
    grid = f'<div class="drgrid fn">{"".join(boxes)}</div>'
    named = sum(1 for fn, _ in FUNC_SLOTS if slot_people.get(fn))
    chart = (f'<div class="org"><div class="tier">{person_box(ceo, "CEO")}</div><div class="conn">{via}</div>'
             f'<div class="tier">{person_box(cio, "Chief investment officer")}</div><div class="conn"></div>'
             f'<div class="drlab">Under the CIO, by function ({named} of {len(FUNC_SLOTS)} heads named)</div>{grid}</div>')
    drs = [p for p in slot_people.values() if p]
    oth = "".join(f'<div class="mini"><b>{esc(clip(p.get("title") or p.get("role"), 60))}</b><br>{esc(p.get("name"))}'
                  f'<br><span>{"In seat " + yrs_txt(p.get("seat_since")) if yrs(p.get("seat_since")) is not None else "Seat start n/d"}'
                  f'{" · " + pay(p) if pay(p) else ""}</span></div>' for p in L["others"])
    o = ORG.get(cid) or {}
    srcs = sorted({str(p.get("tenure_source")) for p in [ceo, cio, *drs] if p and p.get("tenure_source")})
    nd = sum(1 for p in [ceo, cio, *drs] if p for k in ("seat_since", "firm_since", "industry_since") if yrs(p.get(k)) is None)
    meta = [f"Tenure dates from: {', '.join(srcs)}" if srcs else "Tenure dates: company bios and press releases",
            f"{nd} tenure dates not found (shown n/d)" if nd else "All tenure dates found"]
    if cid in COVERED_BY:
        meta.insert(0, f"Investments are run by {COVERED_BY[cid]}, which underwrites the business: CIO and team shown are {COVERED_BY[cid]}'s")
    inf = sum(1 for p in drs if not str(p.get("reporting_line", "")).startswith("stated"))
    if drs:
        meta.append(f"Function heads: {len(drs) - inf} with a reporting line to the CIO stated in a source; {inf} inferred from title "
                    f"or sitting in the affiliated asset manager (dashed)")
    if extra:
        meta.append("Also under the CIO: " + ", ".join(f"{p['name']} ({clip(p.get('title'), 40)})" for p in extra[:3]))
    side = col(card("Other leaders (CFO, CRO, asset manager)", oth or '<p class="nd">Not named in public sources.</p>', style="flex:0 0 300px")
               + card("Basis", bullets(meta, 4, 125, "sm")), w=300)
    body = col(card("", chart, cls="orgcard")) + side
    if cio and yrs(cio.get("seat_since")) is not None:
        t2 = f"{name} leadership: {cio['name']} has run investments for {yrs_txt(cio['seat_since'])}"
        if yrs(cio.get("firm_since")) is not None and abs((yrs(cio["firm_since"]) or 0) - (yrs(cio["seat_since"]) or 0)) >= 1:
            t2 += f" ({yrs_txt(cio['firm_since'])} at the firm)"
    elif cio:
        t2 = f"{name} leadership: investments led by {cio['name']}"
    else:
        t2 = f"{name} leadership: no named CIO in public sources"
    t2 += f"; {named} of {len(FUNC_SLOTS)} function heads under the CIO named"
    allp = [p for p in [ceo, cio, *drs, *L["others"]] if p]
    urls = collect_urls(allp)
    notes = "\n".join(f"- {p.get('role') or ''} {p.get('name')}, {p.get('title')} | reports to {p.get('reports_to') or 'n/d'} "
                      f"({p.get('reporting_line') or ''}) | seat {p.get('seat_since')} firm {p.get('firm_since')} industry {p.get('industry_since')} "
                      f"[{p.get('tenure_source') or ''}] | pay {p.get('comp_total_cad') or p.get('comp_total')} {p.get('comp_currency') or ''} "
                      f"{p.get('comp_year') or ''} | prior: {p.get('prior') or ''} | {p.get('note') or ''} | {' '.join(p.get('sources') or [])} {p.get('comp_source') or ''}"
                      for p in allp)
    slide(t2, body, src_line("Bars: years in seat / at the firm (group) / in the industry with start year (month where known, else mid-year). "
                             "Pay: latest proxy circular or annual report", urls, 3), tag=(n, name, "Leadership"), notes=notes, urls=urls)


def entities(cid):
    o = ORG.get(cid) or {}
    oe = o.get("operating_entities") or None
    return oe if oe and items(oe.get("entities")) else None


# Group affiliates that neither appear on the insurer's own entities page nor manage its general account (Abid: e.g.
# RBC Capital Markets is not part of RBC Insurance). Seg-fund sub-advisers are left out for the same reason.
NOT_GA = {"rbc_life": r"Capital Markets|RBC GAM|Global Asset Management",
          "canada_life": r"Power Corp|Power Financial|\bIGM\b|Northleaf|Sagard|Mackenzie|CIT option|CLIML|Irish Life Investment|Setanta|Canada Life Asset Management Ltd",
          "cooperators_life": r"Aviso|\bCFIS\b|Financial Investment Services",
          "desjardins": r"Guardian Capital|Worldsource|Desjardins Investments / Desjardins Funds",
          "assumption_life": r"CI Investments|Fidelity|Templeton|Vanguard|Seg fund shelf",
          "empire_life": r"Fidelity",
          "ia": r"Richardson|Investia|Private Wealth|iA Clarington|iA Auto Finance",
          "bmo_life": r"GIF guarantee|seg-fund portfolios",
          "primerica_life": r"Concert Series|Common Sense Funds|PFSL"}


def not_ga(cid, t):
    rx = NOT_GA.get(cid)
    return bool(rx and re.search(rx, txt(t), re.I))


def ga_managers(cid):
    pm = R(cid).get("pm_structure") or {}
    ents = [e for e in items(pm.get("manager_entities")) if not re.match(r"\s*(not disclosed|see )", str(e), re.I)]
    return [e for e in ents if not not_ga(cid, e)]


def entity_tree(oe, cid):
    es = items(oe.get("entities"))
    names = [e.get("name") for e in es]
    kids = {}
    roots = []
    for e in es:
        par = e.get("parent")
        if par in names and par != e.get("name"):
            kids.setdefault(par, []).append(e)
        else:
            roots.append(e)
    compact = len(es) > 7
    ncol = 1 if len(es) <= 11 else 2 if len(es) <= 36 else 3
    me = NAMES[cid].lower().split()[0]
    rows = []

    def walk(e, d, seen):
        if e.get("name") in seen or len(rows) >= (18 if ncol == 1 else 36 if ncol == 2 else 54):
            return
        seen.add(e.get("name"))
        nm = str(e.get("name")).lower()
        hl = " me" if me in nm and re.search(r"(life|vie|financial security).*(insurance|assurance)|insurance company|assurance company|^(rbc|bmo) life", nm) else ""
        d_ = re.sub(r"^[\w /-]{0,30}pages?:\s*", "", str(e.get("description") or "")).strip(" '\"")
        d_ = "" if re.search(r"^listed|no description|page lists|^brand:", d_, re.I) else d_
        desc = "" if compact or not d_ else f'<span>{esc(clip(d_, 120))}</span>'
        rows.append(f'<div class="ent{hl}" style="margin-left:{d * (26 if ncol == 1 else 12)}px"><b>{esc(clip(e.get("name"), 70))}</b>{desc}</div>')
        for k in kids.get(e.get("name"), []):
            walk(k, d + 1, seen)

    seen = set()
    for r_ in roots:
        walk(r_, 0, seen)
    more = len(es) - len(rows)
    return f'<div class="etree c{ncol}">' + "".join(rows) + (f'<p class="cap">+{more} more entities listed (see notes)</p>' if more > 0 else "") + "</div>"


def page_pm(cid, n):
    r = R(cid)
    name = NAMES[cid]
    pm = r.get("pm_structure") or {}
    oe = entities(cid)
    if oe:
        tree = entity_tree(oe, cid)
        h = f"Operating entities, as listed on {domain(oe.get('source_url'))}"
        cap = clip(f"{oe.get('page_title') or ''}" + (f" · {oe['note']}" if oe.get("note") else ""), 150)
    else:
        tree = '<p class="nd">The insurer\'s website has no page listing its operating entities.</p>'
        if cid in COVERED_BY:
            tree = f'<p class="nd">No entity list on its own site; policies are underwritten by {COVERED_BY[cid]}.</p>'
        h, cap = "Operating entities (insurer's website)", None
    left = col(card(h, tree, cap=cap), w=640)
    gm = (oe or {}).get("ga_manager_statement") or {}
    how = ([f'Website: "{clip(gm.get("text"), 220)}"'] if gm.get("text") else []) + [b for b in items(pm.get("bullets")) if not not_ga(cid, b)]
    if cid in COVERED_BY:
        how = [f"Policies are underwritten by {COVERED_BY[cid]}; its General Account and investment team manage the assets"] + how
    tg = items(r.get("target_allocations"), 3)
    tg_html = table(["Asset class", "Target / stated range"], [[clip(t.get("asset_class"), 28), clip(t.get("target"), 62)] for t in tg],
                    cls="sm wrap") if tg else '<p class="nd">No target allocation disclosed.</p>'
    a_ = AC.get(cid, {})
    if on_alm(cid):
        ent = "".join(f'<p class="kv sm"><b>{esc(k)}</b>{esc(clip(v, 150))}</p>' for k, v in (
            ("Entity", a_.get("entity")), ("Year-end", a_.get("fye")), ("Basis", a_.get("basis")), ("Consolidates", a_.get("consolidates")),
            ("Left out", a_.get("excluded"))) if v)
    elif a_.get("status") == "covered":
        ent = f'<p class="nd">A brand of {COVERED_BY[cid]}: its policies sit in the Foresters Life entity (OSFI 28432). See that section.</p>'
    else:
        ent = ('<p class="nd">Not in the ALM study and files no OSFI return, so there is no Canadian block view. The balance-sheet pages in this section '
               'come from its own financial statements.</p>')
    right = col(card("Entity assessed for the Canadian view (ALM framework)", ent, style="flex:0 0 auto")
                + card("Who manages the General Account", bullets(how, 3, 165, "sm"), style="flex:0 0 auto") + card("Disclosed targets", tg_html))
    mgr = ga_managers(cid)
    if cid in COVERED_BY:
        head = f"a {COVERED_BY[cid]} brand: assets sit in {COVERED_BY[cid]}'s General Account"
    elif oe and mgr:
        head = f"{len(oe['entities'])} operating entities on its site; General Account run by {short_label(mgr[0], 60)}"
    elif oe:
        head = f"{len(oe['entities'])} operating entities on its site; General Account manager not stated there"
    elif mgr:
        head = f"General Account run by {short_label(mgr[0], 60)}; no entity list on its website"
    else:
        head = "no entity list on its website and no stated General Account manager"
    title = f"{name}: " + clip(head, 140)
    urls = collect_urls(oe or {}) + collect_urls(pm) + collect_urls(tg)
    notes = ("Operating entities (" + str((oe or {}).get("source_url")) + "):\n" + "\n".join(
        f"- {e.get('name')} (parent: {e.get('parent')}): {e.get('description') or ''}" for e in items((oe or {}).get("entities")))
             + "\n\n" + (pm.get("summary") or "") + "\n" + "\n".join(f"- {b}" for b in how))
    slide(title, left + right, src_line("Insurer's own website (entities page); company and asset-manager disclosures", urls),
          tag=(n, sname(cid), "Corporate structure"), notes=notes, urls=urls)


PROSE = {"Bonds": "bonds", "Mortgages (real-estate debt)": "mortgages", "Equity: public": "public equity",
         "Equity: private, infra & alts": "private equity & infra", "Equity: commercial real estate": "CRE equity",
         "Cash & short-term": "cash"}
SHORT = {"Bonds": "Bonds", "Mortgages (real-estate debt)": "Mortgages (RE debt)", "Equity: public": "Equity: public",
         "Equity: private, infra & alts": "Equity: private & infra", "Equity: commercial real estate": "Equity: CRE",
         "Cash & short-term": "Cash & short-term"}


def page_holdings_fs(cid, n):
    r, q = R(cid), QC.get(cid, {})
    name = NAMES[cid]
    # the framework reads IFRS 17 periods only, with trends from fiscal year-end 2023
    mh = [x for x in q.get("mix_history") or [] if x["period"] >= "2023Q4" and "17" in str(x.get("basis"))]
    rot = {k: v for k, v in (q.get("rotation_yoy_pp") or {}).items() if k >= "2024Q4"}
    com = items(r.get("rotation_commentary"), 3)
    nd_txt = (f"Underwritten by {COVERED_BY[cid]}: see the {COVERED_BY[cid]} section." if cid in COVERED_BY else
              "No asset-mix history is published for this insurer (no OSFI return, no annual report with an invested-asset breakdown).")
    rows, act, small, avg_rot, big = [], [], False, None, None
    if mh:
        periods = [x["period"] for x in mh]
        periods_lab = [p[:4] for p in periods] if q.get("mix_frequency") == "Annual" else [p.replace("Q", " Q") for p in periods]
        series = {k: [x.get(k) for x in mh] for k in CLASSES}
        brk = None
        for i in range(len(mh) - 1):
            if mh[i]["basis"] != mh[i + 1]["basis"]:
                brk = i
        chart = stacked_columns(periods_lab, series, CLASS_COLORS, W=720, H=228, break_after=brk, label_every=4)
        first, last = mh[0], mh[-1]
        for k in CLASSES:
            a_, b_ = num(first.get(k)), num(last.get(k))
            if not a_ and not b_:
                continue
            a_, b_ = a_ or 0, b_ or 0
            rows.append([k, f"{a_:.1f}%", f"{b_:.1f}%", f"{b_ - a_:+.1f}"])
        if len(mh) > 1 and num(last.get("total_cad_mm")):
            for k in CLASSES:  # share change over the window x closing portfolio
                act.append((SHORT[k], ((num(last.get(k)) or 0) - (num(first.get(k)) or 0)) / 100 * num(last["total_cad_mm"]) / 1000))
        small = bool(act) and max(abs(v) for _, v in act) < 1
        if small:
            act = [(k, v * 1000) for k, v in act]
        act = [(k, v) for k, v in act if abs(v) >= (0.05 if not small else 0.5)]
        clean_rot = list(rot.values())
        avg_rot = sum(clean_rot) / len(clean_rot) if clean_rot else None
        big = max(rows, key=lambda x: abs(float(x[3]))) if rows else None
        p0, p1 = qdate(first["period"]), qdate(last["period"])
        mix_h = f"Invested-asset mix, {p0} to {p1} ({q.get('mix_frequency', '').lower()})"
    else:
        chart = f'<div class="ph" style="height:228px">{esc(nd_txt)}</div>'
        mix_h, p0, p1 = "Invested-asset mix", "Start", "Latest"
    leg = '<div class="lg">' + "".join(f'<span><i style="background:{CLASS_COLORS[k]}"></i>{esc(k)}</span>' for k in CLASSES) + "</div>"
    mix_card = card(mix_h, chart + leg, cap="Share of invested assets by harmonised class; excludes policy loans, derivatives, seg funds and pass-through fund units.",
                    style="flex:0 0 322px")
    com_card = card("What management says about repositioning", bullets(com, 3, 170, "sm"))
    es = q.get("equity_split") or {}
    alda = num(q.get("alda_pct"))
    ahist = [x for x in q.get("alda_history") or [] if num(x.get("pct")) is not None and x["period"] >= "2023Q4"]
    ah = [(x["period"], x["pct"]) for x in ahist]
    if es:
        eq_items = [({"Commercial real estate": "Commercial RE"}.get(k, k), num(v) or 0) for k, v in es["items"].items()]
        eq_html = hbar(eq_items, lambda v: f"{v:.1f}%", W=270, rowh=19, label_w=120, right_w=44, color=ORANGE, top=6)
        eq_html += (f'<div class="alda"><b>ALDA {alda:.1f}%</b> of invested assets<span>private + infra + CRE equity, {esc(es.get("as_of", ""))}</span></div>'
                    if alda is not None else "")
        if len(ah) > 1:
            eq_html += (f'<p class="cap">Same definition on the history (private, infra &amp; alts + CRE equity): {ah[0][1]:.1f}% in '
                        f'{esc(qdate(ah[0][0]))}, {ah[-1][1]:.1f}% in {esc(qdate(ah[-1][0]))}.</p>')
    else:
        eq_html = f'<p class="nd">{esc(nd_txt) if cid in COVERED_BY else "No equity breakdown disclosed."}</p>'
    eq_card = card("Equity split and ALDA, % of invested assets", eq_html, style="flex:0 0 296px")
    bottom = f'<div class="row" style="gap:12px;flex:1;min-height:0">{eq_card}{com_card}</div>'
    tbl = table(["Asset class", p0, p1, "Change, pts"], rows, cls="sm xs") if rows else f'<p class="nd">{esc(nd_txt) if not mh else "n/d"}</p>'
    rot_items = [(k[:4], v) for k, v in sorted(rot.items())]
    rot_chart = hbar(rot_items, lambda v: f"{v:.1f}", W=400, rowh=17, label_w=50, right_w=50, color=ORANGE) if rot_items else '<p class="nd">n/d</p>'
    act_chart = (hbar(act, (lambda v: f"{v:+,.0f}") if small else (lambda v: f"{v:+.1f}"), W=400, rowh=17, label_w=150, right_w=46, color=TEAL)
                 if act else '<p class="nd">n/d</p>')
    left = col(mix_card + bottom)
    right = col(card("Then vs now", tbl, style="flex:0 0 210px") + card("Rotation per year (pts of portfolio)", rot_chart, style="flex:0 0 136px")
                + card(f"Net reallocation since start, {'$MM' if small else '$BN'}", act_chart), w=430)
    if mh:
        title = f"{name}: " + (f"{PROSE.get(big[0], big[0].lower())} {'up' if float(big[3]) > 0 else 'down'} {abs(float(big[3])):.1f} pts since {p0}" if big else "mix history")
        if avg_rot is not None:
            title += f"; the book rotates ~{avg_rot:.1f} pts a year"
        if alda is not None:
            title += f"; ALDA {alda:.0f}% of invested assets"
        src = ("Project portfolio-reallocation series: " + clip(q.get("mix_source") or "OSFI 10Q/LF2 returns and annual reports", 80)
               + ". IFRS 17 periods only. Rotation = half the sum of absolute class-share changes, year-end to year-end; "
                 "net reallocation = share change × closing portfolio")
    else:
        title = f"{name}: " + (f"holdings sit in {COVERED_BY[cid]}'s General Account" if cid in COVERED_BY else "no published portfolio history")
        src = "No OSFI or annual-report series available"
    urls = collect_urls(com)
    notes = "\n".join(f"- {txt(c)} {c.get('source', '') if isinstance(c, dict) else ''}" for c in com)
    slide(title, left + right, src_line(src, urls, 2), tag=(n, name, "Assets and rotation" + FS_TAG), notes=notes, urls=urls)


def page_newmoney_fs(cid, n):
    """New money vs in-force: where the period's net new assets went compared with the in-force mix, next to which
    insurance liabilities grew (OSFI LF3 by line). Net flows only: maturities reinvested inside a class are not visible."""
    q = QC.get(cid, {})
    name = NAMES[cid]
    nm = [w for w in q.get("new_money") or [] if w["start"] >= "2022Q4"]  # IFRS 17 periods only
    nd = (f"Underwritten by {COVERED_BY[cid]}: see the {COVERED_BY[cid]} section." if cid in COVERED_BY else
          "No asset-mix history is published for this insurer.")
    read = []
    if nm:
        base = nm[0]
        series = [("In-force mix at " + qdate(base["start"]), [num(base["inforce_mix"].get(k)) for k in CLASSES])]
        cols = [MUTED_BAR, BLUE, ORANGE]
        seen_w = set()
        for w in nm:
            dt = sum(num(v) or 0 for v in w["delta_cad_mm"].values())
            if (w["start"], w["end"]) in seen_w:
                continue
            seen_w.add((w["start"], w["end"]))
            if dt > 0:
                series.append((f"Net new money, {w['window'][0].lower() + w['window'][1:]} ({qdate(w['start'])} to {qdate(w['end'])})",
                               [(num(w["delta_cad_mm"].get(k)) or 0) / dt * 100 for k in CLASSES]))
        chart = grouped_hbar([SHORT[k] for k in CLASSES], series, cols, fmt=lambda v: f"{v:.0f}%", W=620, rowh=40, label_w=150,
                             xlabel="% of in-force assets (grey) / % of net new money (colour)")
        leg = '<div class="lg">' + "".join(f'<span><i style="background:{cols[i]}"></i>{esc(nme)}</span>' for i, (nme, _) in enumerate(series)) + "</div>"
        def _g(w_):
            return sum(num(v) or 0 for v in w_["delta_cad_mm"].values()) / (num(w_["start_total_cad_mm"]) or 1)
        # headline window: the latest one unless its net new money is under 5% of the book (shares get noisy), then the longest
        w = nm[-1] if _g(nm[-1]) >= 0.05 else max(nm, key=_g)
        dt = sum(num(v) or 0 for v in w["delta_cad_mm"].values())
        if dt > 0:
            tilt = sorted(((k, (num(w["delta_cad_mm"].get(k)) or 0) / dt * 100 - (num(w["inforce_mix"].get(k)) or 0)) for k in CLASSES),
                          key=lambda x: -x[1])
            read.append(f"{w['window']}: net new assets " + usd(dt) + f" ({qdate(w['start'])} to {qdate(w['end'])}), "
                        f"{dt / (num(w['start_total_cad_mm']) or 1) * 100:.0f}% growth on the in-force book")
            if _g(w) < 0.05:
                read.append(f"Caution: net new money was only {_g(w) * 100:.0f}% of the book over the window, so the class shares are "
                            "dominated by a few trades and market moves")
            elif w is not nm[-1] and _g(nm[-1]) > 0:
                read.append(f"{nm[-1]['window']}: net new money was only {_g(nm[-1]) * 100:.0f}% of the book, so its class shares swing "
                            "widely; the headline uses the longer window")
            read.append(f"New money over-weights {PROSE[tilt[0][0]]} by {tilt[0][1]:.0f} pts and under-weights "
                        f"{PROSE[tilt[-1][0]]} by {-tilt[-1][1]:.0f} pts versus the in-force mix")
        else:
            read.append(f"{w['window']}: the portfolio shrank by " + usd(-dt)
                        + f" ({qdate(w['start'])} to {qdate(w['end'])}), so there is no net new money to allocate")
        left_html = chart + leg
    else:
        left_html = f'<div class="ph" style="height:330px">{esc(nd)}</div>'
    read.append("Net of maturities and market moves: a class can show negative new money while reinvesting its own cash flows; "
                "equity and real-estate values also move with markets")
    lg = q.get("liability_growth") or {}
    lines = lg.get("lines") or {}
    if lines:
        dl = [(k, (num(v["current"]) or 0) - (num(v["prior"]) or 0)) for k, v in lines.items()]
        big = max(abs(v) for _, v in dl) if dl else 0
        unit = "$MM" if big < 1000 else "$BN"
        dlv = [(k, v if unit == "$MM" else v / 1000) for k, v in dl]
        lia_chart = hbar(dlv, (lambda v: f"{v:+,.0f}") if unit == "$MM" else (lambda v: f"{v:+,.1f}"), W=470, rowh=26, label_w=160,
                         right_w=50, color=TEAL, xlabel=f"Change in insurance contract liabilities, {unit}")
        rows = [[k, f"{num(v['prior']) / 1000:,.1f}", f"{num(v['current']) / 1000:,.1f}",
                 f"{((num(v['current']) or 0) / num(v['prior']) - 1) * 100:+.0f}%" if num(v["prior"]) and num(v["prior"]) > 0 else "n/m"]
                for k, v in lines.items()]
        tbl = table(["Line", f"FY{lg['fiscal_year'] - 1}", f"FY{lg['fiscal_year']}", "Change"], rows, cls="sm")
        grow = max(dl, key=lambda x: x[1])
        if grow[1] > 0:
            read.insert(1 if len(read) > 1 else 0, f"Fastest-growing liability line in FY{lg['fiscal_year']}: {grow[0].lower()} "
                                                   f"(+{usd(grow[1])}), the new business the new money is backing")
        lia_h = f"Which liabilities grew, FY{lg['fiscal_year']} vs FY{lg['fiscal_year'] - 1}"
    else:
        lv, lb = mix_view(cid, "liability")
        if lv and cid not in COVERED_BY:
            lia_chart = (mix_html(lv, "lia") + f'<p class="cap">Latest year only: {esc(clip(lb, 150))}. Not an OSFI LF3 filer, '
                         'so no prior-year split by line in this dataset.</p>')
        else:
            lia_chart = f'<p class="nd">{esc(nd) if cid in COVERED_BY else "No liability split by line is filed (not an OSFI LF3 filer)."}</p>'
        tbl = '<p class="nd">n/d</p>'
        lia_h = "Liability mix by type (no growth by line available)" if lv and cid not in COVERED_BY else "Which liabilities grew"
    left = col(card("Where net new assets went vs the in-force mix", left_html, style="flex:0 0 372px")
               + card("Reading", bullets(read, 4, 175, "sm")), w=650)
    right = col(card(lia_h, lia_chart, style="flex:0 0 230px") + card("Insurance contract liabilities by line, $BN (policies issued)", tbl))
    if nm and read and read[0].startswith(("Since", "Last")) and "over-weights" in " ".join(read):
        t = f"{name}: " + first_sentence(next(x for x in read if "over-weights" in x)).replace("New money over-weights", "new money over-weights")
    elif nm:
        t = f"{name}: no net new money to allocate in the latest window"
    else:
        t = f"{name}: new money vs in-force not measurable from public data"
    slide(clip(t, 150), left + right, "OSFI LF1/LF2 (assets) and LF3 P22010 (liabilities by line, all regions, policies issued); "
          "iA supplements and annual reports for others. New money = change in $ held by class over the window",
          tag=(n, name, "New money and liabilities" + FS_TAG), notes="\n".join(read))


def page_leverage_fs(cid, n):
    r, q = R(cid), QC.get(cid, {})
    name = NAMES[cid]
    lv = r.get("leverage") or {}
    ga = ga_mm(cid)
    ls = q.get("landscape") or {}
    debt = [d for d in items(lv.get("debt_outstanding")) if "deposit" not in str(d.get("type", "")).lower()]
    group_level = any(re.search(r"group|parent|federation|holdco|lifeco|sagicor|bank", str(d.get("type", "")), re.I) for d in debt)
    debt_tot = sum(num(d.get("amount_cad_mm")) or 0 for d in debt)
    obs = q.get("off_balance_sheet") or []
    repo_osfi = sum(num(o["amount_cad_mm"]) or 0 for o in obs if o.get("level3") == "Repos")
    sl_osfi = sum(num(o["amount_cad_mm"]) or 0 for o in obs if o.get("level3") == "Security Lending")
    deriv = sum(abs(num(o["amount_cad_mm"]) or 0) for o in obs if o.get("level1") == "Derivatives")  # notionals are gross
    grp = lambda d: bool(re.search(r"not (the )?(insurer|DFS|ivari)|group[- ]level|Federation|parent level|^Group\b", str((d or {}).get("text", "")), re.I))
    repo_grp, sl_grp = grp(lv.get("repos")), grp(lv.get("securities_lending"))
    repo = None if repo_grp else (num((lv.get("repos") or {}).get("amount_cad_mm")) or (repo_osfi or None))
    secl = None if sl_grp else (num((lv.get("securities_lending") or {}).get("amount_cad_mm")) or (sl_osfi or None))
    pct = lambda v: f"{v / ga * 100:.1f}% of invested assets" if (v and ga) else ""
    flr = num(lv.get("financial_leverage_ratio_pct"))
    tiles = "".join([
        kpi("Debt & hybrids outstanding", bn(debt_tot) if debt_tot else "n/d", ("issued at group / parent level" if group_level else "senior, sub, LRCN, prefs") if debt_tot else "none disclosed"),
        kpi("Financial leverage ratio", f"{flr:.1f}%" if flr else "n/d", "as disclosed"),
        kpi("Repos", bn(repo, 2) if repo else ("Group only" if repo_grp else "none" if ls.get("repo_pct") == 0 else "n/d"),
            "not separable for the insurer" if repo_grp else pct(repo)),
        kpi("Securities lending", bn(secl, 2) if secl else ("Group only" if sl_grp else "n/d"), "not separable for the insurer" if sl_grp else pct(secl)),
        kpi("Derivative notional", bn(deriv) if deriv else "n/d", pct(deriv) if deriv else "OSFI LF3 (legal entity)"),
    ])
    iss = items(lv.get("issuance"), 6)
    iss_rows = [[str(i.get("date") or "")[:7], clip(i.get("instrument"), 38), f"{num(i.get('amount_cad_mm')):,.0f}" if num(i.get("amount_cad_mm")) else "",
                 f"{num(i.get('coupon_pct')):.3f}%" if num(i.get("coupon_pct")) else "", str(i.get("maturity") or "")[:4],
                 clip(", ".join(re.split(r" \(| / ", b)[0] for b in (i.get("bookrunners") or [])), 44)] for i in iss]
    iss_html = table(["Date", "Instrument", "$MM", "Coupon", "Due", "Bookrunners"], iss_rows, cls="sm", left=2) if iss_rows else '<p class="nd">No 2023-2026 issuance found.</p>'
    dl = [(clip(re.split(r" \(", str(d.get("type")))[0], 21), (num(d.get("amount_cad_mm")) or 0) / 1000) for d in debt if num(d.get("amount_cad_mm"))]
    debt_unit = "$BN"
    if dl and max(abs(v) for _, v in dl) < 1:
        dl, debt_unit = [(k, v * 1000) for k, v in dl], "$MM"
    debt_chart = hbar(dl[:6], (lambda v: f"{v:,.0f}") if debt_unit == "$MM" else (lambda v: f"{v:.1f}"), W=370, rowh=22, label_w=160,
                      right_w=40, color=BLUE) if dl else '<p class="nd">No debt disclosed (mutual / subsidiary funded by parent).</p>'
    dv = {}
    for o in obs:
        if o.get("level1") == "Derivatives":
            dv[o.get("level2")] = dv.get(o.get("level2"), 0) + abs(num(o["amount_cad_mm"]) or 0) / 1000
    dv_unit = "$BN"
    if dv and max(dv.values()) < 1:
        dv, dv_unit = {k: v * 1000 for k, v in dv.items()}, "$MM"
    dv_chart = hbar(sorted(dv.items(), key=lambda x: -x[1]), (lambda v: f"{v:,.0f}") if dv_unit == "$MM" else (lambda v: f"{v:,.1f}"), W=370, rowh=22, label_w=110, right_w=50,
                    color=PURPLE) if dv else '<p class="nd">No derivative notionals in OSFI LF3 for this insurer.</p>'
    struct = [s.get("text") if isinstance(s, dict) else s for s in items(lv.get("structured_indirect"), 5)]
    rp_t = (lv.get("repos") or {}).get("text")
    sl_t = (lv.get("securities_lending") or {}).get("text")
    fund = [x for x in [("Repos: " + rp_t) if rp_t else None, ("Sec lending: " + sl_t) if sl_t else None] if x] + struct
    if cid in COVERED_BY:
        debt_chart = dv_chart = f'<p class="nd">Underwritten by {COVERED_BY[cid]}: see the {COVERED_BY[cid]} section.</p>'
    left = col(f'<div class="kpis">{tiles}</div>' + card("Debt and hybrid issuance, 2023-2026", iss_html, style="flex:0 0 205px")
               + card("Repo, securities lending and structured / indirect lending", bullets(fund, 5, 210, "sm")))
    right = col(card(f"Debt outstanding by type, {debt_unit}", debt_chart, style="flex:0 0 262px") + card(f"Derivative notional by type, {dv_unit}", dv_chart,
                                                                         cap="OSFI LF3 P21110 notionals, main legal entity, latest fiscal year end"), w=400)
    t = f"{name}: "
    bits = []
    if debt_tot:
        bits.append(f"{bn(debt_tot)} of debt and hybrids" + (" at group level" if group_level else ""))
    if repo:
        bits.append(f"repos {pct(repo) or bn(repo, 2)}")
    if deriv and ga:
        bits.append(f"derivative notional {deriv / ga * 100:.0f}% of invested assets")
    if not bits:
        bits.append("little disclosed balance-sheet leverage")
    urls = collect_urls(lv)
    notes = json.dumps(lv, indent=1)[:6000]
    slide(t + ", ".join(bits), left + right, src_line("OSFI LF3 (repos P22030, derivatives P21110); financial statement notes", urls),
          tag=(n, name, "Leverage" + FS_TAG), notes=notes, urls=urls)


def page_partners(cid, n):
    r = R(cid)
    name = NAMES[cid]
    pt = r.get("partnerships") or {}
    uw = items(pt.get("underwriters"), 10)
    dealer = lambda u: clip(re.split(r" / |, | \(", str(u.get("dealer")))[0], 26)
    uw_items = [(dealer(u), num(u.get("deals")) or 1) for u in uw if u.get("dealer")]
    has_counts = any(num(u.get("deals")) for u in uw)
    if uw_items and has_counts:
        uw_html = hbar(sorted(uw_items, key=lambda x: -x[1]), lambda v: f"{v:.0f}", W=380, rowh=22, label_w=150, right_w=30, color=BLUE)
        uw_html += '<p class="cap">Count of lead or co-lead roles found on 2020-2026 debt / equity deals.</p>'
    elif uw:
        uw_html = '<div class="chips">' + "".join(f'<span class="chipx">{esc(clip(u.get("dealer"), 30))}<small>{esc(clip(u.get("role"), 20))}</small></span>' for u in uw) + "</div>"
    else:
        uw_html = '<p class="nd">No public issuance, or dealers not named.</p>'
    deals = sorted(items(pt.get("deals")), key=lambda d: str(d.get("year") or ""), reverse=True)[:7]
    deals_html = ('<table class="sm wrap tl"><tbody>' + "".join(
        f'<tr><td class="l yr">{esc(str(d.get("year") or ""))}</td><td class="l">{esc(clip(d.get("text"), 170))}</td></tr>' for d in deals)
                  + "</tbody></table>") if deals else '<p class="nd">No notable public deals found.</p>'
    spons = items(pt.get("sponsorships"), 5)
    banks = items(pt.get("bank_relationships"), 4)
    left = col(card("Notable deals and transactions, 2020-2026", deals_html, style="flex:0 0 340px") + card("Bank relationships and distribution", bullets(banks, 4, 170)))
    right = col(card("Dealers on the top line", uw_html, style="flex:0 0 300px") + card("Sponsorships and events", bullets(spons, 5, 110)), w=420)
    if uw_items:
        top = sorted(uw_items, key=lambda x: -x[1])[0][0] if has_counts else uw_items[0][0]
        t = f"{name}: {top} {'leads most of' if has_counts else 'appears on'} its issues"
    else:
        t = f"{name}: no dealer-led public issuance"
    if deals:
        t += f"; {len(items(pt.get('deals')))} notable deals since 2020"
    urls = collect_urls(pt)
    notes = json.dumps(pt, indent=1)[:6000]
    slide(t, left + right, src_line("Issuance press releases, prospectus supplements, company news", urls),
          tag=(n, name, "Partnerships"), notes=notes, urls=urls)


def shock_label(f):
    """Put the shock first: 'Public equity -10%' -> '-10% public equity'; 'Rates +50 bp' -> '+50bps interest rates'."""
    f = str(f)
    m = re.search(r"([+-−]\s?\d+(?:\.\d+)?)\s?(%|bps?|bp)", f)
    if not m:
        return clip(f, 34)
    amt = m.group(1).replace(" ", "").replace("−", "-") + ("%" if m.group(2) == "%" else "bps")
    rest = (f[:m.start()] + f[m.end():]).strip(" ,")
    rest = {"Rates": "interest rates"}.get(rest, rest)
    rest = rest[:1].lower() + rest[1:] if rest and not rest[:2].isupper() else rest
    return clip(f"{amt} {rest}", 34)


def page_risk_fs(cid, n):
    r, q = R(cid), QC.get(cid, {})
    name = NAMES[cid]
    rk = r.get("risk") or {}
    hist = q.get("licat_history") or []
    cap, fw, asof = capital(cid)
    if hist:
        pts = [(h["period"][2:4] + h["period"][4:], h["total"]) for h in hist if num(h.get("total"))]
        have = {x for x, _ in pts}
        mpts = [(m["period"][2:4] + m["period"][4:], m["total"]) for m in Q.get("peer_licat_median", [])
                if (m["period"][2:4] + m["period"][4:]) in have]
        chart = line_chart([("OSFI-filer median", MUTED_BAR, mpts), (name, BLUE, pts)], W=520, H=210, ref=100,
                           ref_label="OSFI supervisory target 100%", label_every=4)
        if PEER.get("capital_ratio_pct"):
            pass
        cap_card = card(f"LICAT total ratio, {q.get('licat_entity')}", chart, cap="OSFI LCQ public extract, quarterly. Dashed grey = median of the 13 OSFI-filing peers (main entity each).",
                        style="flex:0 0 300px")
    else:
        disc = q.get("capital_disclosed") or []
        rows = [[clip(d.get("entity"), 40), d.get("as_at") or "", f"{num(d.get('total_ratio_pct')):.0f}%" if num(d.get("total_ratio_pct")) else "n/d",
                 f"{num(d.get('prior_total_ratio_pct')):.0f}%" if num(d.get("prior_total_ratio_pct")) else ""] for d in disc]
        nd_cap = f"Underwritten by {COVERED_BY[cid]}: see the {COVERED_BY[cid]} section." if cid in COVERED_BY else "Not disclosed."
        cap_card = card("Capital ratio as disclosed", table(["Entity", "As at", "Ratio", "Prior"], rows, cls="sm") if rows else f'<p class="nd">{nd_cap}</p>',
                        style="flex:0 0 300px")
    sens = q.get("sensitivities") or []
    s_items = [(shock_label(s["factor"]), num(s.get("ni_impact_cad_mm"))) for s in sens if num(s.get("ni_impact_cad_mm")) is not None]
    if s_items:
        big = max(abs(v) for _, v in s_items)
        f_ = (lambda v: f"{v:+,.0f}") if big >= 10 else (lambda v: f"{v:+,.1f}")
        sens_html = hbar(s_items, f_, W=520, rowh=22, label_w=215, right_w=50, color=RED, xlabel="$MM impact on after-tax net income")
        asof = next((s.get("as_of") for s in sens if s.get("as_of")), "")
        sens_html += f'<p class="cap">As disclosed{(", " + str(asof)) if asof else ""}; immediate shocks, after tax, before management action.</p>'
    else:
        sens_html = bullets(rk.get("sensitivities"), 4, 150)
    ls = q.get("landscape") or {}
    ratios = []
    for lab, k, f in [("Market risk capital, % inv.", "market_cap_pct_inv", "{:.1f}%"), ("Credit risk capital, % inv.", "credit_cap_pct_inv", "{:.1f}%"),
                      ("Return-seeking assets", "risk_assets_pct", "{:.0f}%"), ("Private credit", "private_credit_pct", "{:.0f}%"),
                      ("BBB, % of bonds", "bbb_pct_bonds", "{:.0f}%"), ("Below IG, % of bonds", "below_ig_pct_bonds", "{:.1f}%")]:
        v = num(ls.get(k))
        if v is not None:
            m = PEER.get(k)
            ratios.append([lab, f.format(v), f.format(m) if m is not None else ""])
    rt = table(["Metric", clip(name, 14), "Median"], ratios[:4], cls="sm xs") if ratios else '<p class="nd">n/d (no OSFI capital or bond-quality data)</p>'
    left = col(cap_card + card("Disclosed market sensitivities", sens_html), w=548)
    target = clip(rk.get("capital_target"), 130)
    mid = card("Risk appetite and limits", bullets(rk.get("appetite"), 3, 135, "sm"), style="flex:0 0 290px") + card(
        "Governance", bullets(rk.get("governance"), 3, 120, "sm"))
    rgt = card("Capital target", f'<p class="kv">{esc(target)}</p>' if target else '<p class="nd">Not stated.</p>', style="flex:0 0 122px") + card(
        "Hedging and notable events", bullets(items(rk.get("hedging"), 2) + items(rk.get("events"), 1), 3, 120, "sm"), style="flex:0 0 232px") + card("Risk profile vs peers", rt)
    body = left + col(mid, w=310) + col(rgt)
    t = f"{name}: "
    t += f"{fw} {cap:.0f}%" if cap else "capital ratio not disclosed"
    if target and len(target) < 70:
        t += f" (stated target: {target})"
    eq = next((s for s in sens if "equit" in s["factor"].lower() and "10" in s["factor"]), None)
    if eq and num(eq.get("ni_impact_cad_mm")) is not None and abs(num(eq["ni_impact_cad_mm"])) >= 0.5:
        t += f"; -10% public equity costs {usd(abs(num(eq['ni_impact_cad_mm'])))} of net income"
    elif eq and num(eq.get("ni_impact_cad_mm")) is not None:
        t += "; a 10% equity fall barely touches net income (disclosed)"
    urls = collect_urls(rk)
    notes = json.dumps(rk, indent=1)[:6000]
    slide(t, body, src_line("OSFI LCQ; annual MD&A risk sections; project investment-risk benchmark", urls),
          tag=(n, name, "Capital and risk" + FS_TAG), notes=notes, urls=urls)


# ---------------------------------------------------------------- ALM-basis pages (Canadian business, net of reinsurance)
ALM_SRC = "ALM framework (cdn-life-insurer-alm): OSFI LF1/LF2/LF3/LCQ returns and 2025 annual reports"
BIG3 = ("MFC", "SLF", "CLF")
ALLOC_TXT = {"MFC": "Legal-entity (global) mix applied to the Canadian pool",
             "SLF": "Legal-entity (global) mix applied to the Canadian pool",
             "CLF": "Disclosed Canada non-par mix (Q4 2025 MD&A); bonds split at the entity ratio (est)"}
OTHER_FIN = {"IVA": "funds-withheld reinsurer deposit", "BMO": "mortgage loans on investment property", "IAG": "debentures and similar",
             "BEN": "debt and similar", "SLF": "debt inside the insurer", "CLF": "debt inside the insurer", "EMP": "debt inside the insurer",
             "EQL": "debt inside the insurer"}
RISK_LAB = {"equity": "Equity markets", "rates": "Interest rates", "spreads": "Credit spreads", "real_estate_alts": "Real estate and alternatives"}


def line_shift(ll, y0, y1):
    """A filer moving business between two OSFI lines shows as one line more than doubling while another drops by a
    like amount. Returns (line up, line down) so the two are read together instead of as growth; None otherwise."""
    a0, a1 = ll.get(y0) or {}, ll.get(y1) or {}
    for up in a1:
        u0, u1 = num(a0.get(up)) or 0, num(a1.get(up)) or 0
        if u0 > 0 and u1 - u0 > u0:
            for dn in a1:
                d0, d1 = num(a0.get(dn)) or 0, num(a1.get(dn)) or 0
                if dn != up and d0 > 0 and d0 - d1 > 0.2 * d0 and d0 - d1 > 0.4 * (u1 - u0):
                    return up, dn
    return None


def sname(cid):
    return NAMES[cid] + (f" ({TNAME[cid]})" if cid in TNAME else "")


def page_summary(cid, n):
    a = AC.get(cid, {})
    if not on_alm(cid):
        return page_summary_fs(cid, n)
    r, q, b = R(cid), QC.get(cid, {}), yb(cid)
    t, st, sid = tn(cid), a["status"], a.get("sid")
    liab_only = st == "amf_liab"
    amf = st.startswith("amf")
    date = dfmt(b.get("date"))
    e = (a.get("earn") or {}).get("2025") or {}
    T = [kpi("GenAcct (excl. par / seg fund), est", "n/a" if liab_only else usd(b.get("ga")),
             "no public balance sheet: liability side only" if liab_only else f"at {date}; Canadian business, net of reinsurance", True)]
    if num(b.get("buffer")) is not None:
        T.append(kpi("Buffer, est", pc(b["buffer"]), f"(Surplus + ABL CSM less net derivative liabilities) / GenAcct net of repos; peer median {pc(AMED['buffer'])}", True))
    elif a.get("buffer_note"):
        T.append(kpi("Buffer", "n/m", "net fulfilment cash flows are an asset (term book, heavily reinsured), so there is no liability base to cushion", True))
    elif num(b.get("buffer_memo")) is not None:
        T.append(kpi("Buffer", "n/a", f"AMF filer: no ABL CSM split. Memo on total CSM † {pc(b['buffer_memo'])}, not comparable with peers", True))
    else:
        T.append(kpi("Buffer", "n/a", "needs a balance sheet", True))
    licat = is_licat(b)
    if num(b.get("cap_ratio")) is not None:
        T.append(kpi("Capital ratio (LICAT total)" if licat else "Capital ratio (CARLI, AMF)", pc(b["cap_ratio"]),
                     f"at {date}; peer median {pc(AMED['cap_ratio'])} (LICAT filers)" if licat else f"AMF solvency ratio at {date}; not comparable with LICAT", True))
    else:
        T.append(kpi("Capital ratio", "n/a", "not public for the insurer", True))
    T.append(kpi("Surplus" + (", est" if sid in BIG3 else ""), usd(b.get("surplus")),
                 "n/a without a balance sheet" if liab_only else f"{pc(b.get('surplus_pct'))} of GenAcct" + ("; In Canada equity = assets less liabilities" if sid in BIG3 else "; equity less the part backing other assets")))
    if num(b.get("csm_abl")) is not None:
        es = lambda k: " est" if "est" in str(b.get(k) or "") else ""
        sub = f"ABL {usd(b['csm_abl'])} · seg fund {usd(b.get('seg_csm') or 0)}{es('seg_csm_basis')} · par {usd(b.get('par_csm') or 0)}{es('par_csm_basis')}"
    else:
        sub = "total only: no ABL / seg fund / par split (AMF rule)"
    T.append(kpi("CSM, net of reinsurance", usd(b.get("csm_total")), sub))
    if amf:
        T.append(kpi("Par share", "n/a", "par is not separable in the filings"))
    else:
        T.append(kpi("Par share", pc(b.get("par_share")), f"par block {usd(b.get('par') or 0)}; par / (par + GenAcct); peer median {pc(AMED['par_share'])}"))
    T.append(kpi("Financing / GenAcct", pc(b.get("fin_pct")), "n/a without a balance sheet" if liab_only else
                 (" + ".join(x for x in [f"repos {usd(b['repos'])}" if num(b.get("repos")) else None, f"other financing {usd(b['fin_other'])}" if num(b.get("fin_other")) else None] if x)
                  or "no repos or debt inside the insurer") + f"; peer median {pc(AMED['fin_pct'])}"))
    bsrow = lambda pat: next((x for x in a.get("bs") or [] if pat in x["item"]), None)
    if liab_only:
        rh, icl = bsrow("Reinsurance contract held assets"), bsrow("Insurance contract liabilities, L&H")
        T.append(kpi("Reinsurance held assets", usd(rh["mm"]) if rh else "n/a", "as disclosed; no GenAcct to scale it against"))
        T.append(kpi("Insurance contract liabilities", usd(icl["mm"]) if icl else "n/a", "life and health, as disclosed, incl. par and UL"))
    else:
        T.append(kpi("Reinsurance / GenAcct", pc(b.get("reins_pct")), f"reinsurance held assets {usd(b.get('reins_assets'))}; peer median {pc(AMED['reins_pct'])}"))
    seg = num(b.get("seg_fv"))
    if liab_only:
        segrow = next((x for x in a.get("bs") or [] if "insurance contracts" in x["item"] and x["group"].startswith("Seg")), None)
        T.append(kpi("Seg fund liabilities (insurance)", usd(segrow["mm"]) if segrow else "n/a", "own block, outside GenAcct"))
    else:
        T.append(kpi("Seg fund value", usd(seg) if seg else "none", "own block, outside GenAcct" + (f"; seg fund CSM {usd(b['seg_csm'])} est" if num(b.get("seg_csm")) else "")))
    if num(b.get("ul")):
        T.append(kpi("UL policyholder fund", usd(b["ul"]), "pass-through assets, outside GenAcct"))
    elif num(b.get("inv_contracts")):
        T.append(kpi("Investment contracts", usd(b["inv_contracts"]), "IFRS 9 liabilities, own block"))
    else:
        T.append(kpi("Fulfilment cash flows, est", usd(b.get("fcf")), "BEL + RA net of reinsurance" + ("" if liab_only else " (residual of the block view)")))
    if e:
        isr, nir = num(e.get("isr")), num(e.get("nir"))
        share = f"; insurance is {isr / (isr + nir) * 100:.0f}% of the two" if (isr or 0) > 0 and (nir or 0) > 0 else ""
        T.append(kpi("Insurance service result, fiscal 2025", usd(isr), (f"net investment result {usd(nir)}{share}" if nir is not None else "net investment result n/a")
                     if isr is not None else f"not in the study's earnings panel; net investment result {usd(nir)}"))
        T.append(kpi("Net income, fiscal 2025", usd(e.get("ni")), f"return on equity {pc(e.get('roe'))}; " + ("Canada (OSFI LF2)" if sid in BIG3 else "legal entity (OSFI LF1)")))
    else:
        if len(T) < 10 or "Fulfilment" not in T[-1]:
            T.append(kpi("Fulfilment cash flows, est", usd(b.get("fcf")), "BEL + RA net of reinsurance" + ("" if liab_only else " (residual of the block view)")))
        v, m = group_ni(cid)
        T.append(kpi("Net income (group, as reported)", v or "n/a", clip(f"{m.get('metric')}" + (f" · {m['as_of']}" if m.get("as_of") else ""), 70) if m else "not found"))
    grid = '<div class="kgrid">' + "".join(T[:12]) + "</div>"

    ll = (a.get("liab_line") or {}).get("2025") or {}
    pos = [(k, num(v)) for k, v in ll.items() if num(v) and num(v) > 0]
    neg = [(k, num(v)) for k, v in ll.items() if num(v) and num(v) <= -0.5]
    lia_override = None
    if neg and sum(v for _, v in pos) < 0.05 * -sum(v for _, v in neg):
        lia_override = ('<p class="kv">' + esc("; ".join(f"{k} is a net asset of {usd(-v)}" for k, v in neg) + " after reinsurance held: the insurer cedes more than it holds, "
                        "so there is no liability mix by line to show.") + "</p>")
        lia_h, lia_cap, lia = f"Liabilities by product line, net of reinsurance, {date}", "Insurance contract liabilities by OSFI line, excl. seg funds.", []
    elif pos:
        tot = sum(v for _, v in pos)
        lia = [(k, v / tot * 100) for k, v in pos]
        sh_ = line_shift(a.get("liab_line") or {}, "2024", "2025")
        lia_cap = f"% of {usd(tot)}; insurance contract liabilities by OSFI line, excl. seg funds" + (f"; the 2025 return moves business from {sh_[1].lower()} to {sh_[0].lower()}" if sh_ else "") + (
            "; " + ", ".join(f"{k.lower()} is a net asset ({usd(v)})" for k, v in neg) + ", left out" if neg else "")
        lia_h = f"Liabilities by product line, net of reinsurance, {date}"
    else:
        lia, lb = mix_view(cid, "liability")
        lia_cap = "Consolidated, from annual-report notes: the ALM study holds no product lines for AMF filers."
        lia_h = "Liabilities by type (consolidated, incl. CSM and surplus)"
    rows = []
    for lab, key in [("Buffer, est", "buffer"), ("Capital ratio", "cap_ratio"), ("Par share", "par_share"), ("Financing / GenAcct", "fin_pct"),
                     ("Reinsurance / GenAcct", "reins_pct"), ("Private and alternative assets", "alts_share")]:
        vals = peer_vals(key)
        mine = pc(vals.get(cid)) if not (amf and key in ("buffer", "par_share")) else "n/a"
        if key == "cap_ratio" and amf and cid in vals:
            mine += " †"
        if cid == "rbc_life":
            lic = {c: v for c, v in vals.items() if AC[c]["status"] in ("study", "built")}
            rows.append([lab, mine, pc(AMED.get(key)), rank_txt(lic, cid)])
        else:
            rows.append([lab, mine, pc(vals.get("rbc_life")), pc(AMED.get(key))])
    hdr = ["Fiscal year-end 2025", LAB[cid], "Peer median", "Position"] if cid == "rbc_life" else ["Fiscal year-end 2025", LAB[cid], "RBC Life", "Peer median"]
    peer_cap = None
    own = clip(r.get("ownership") or q.get("ownership"), 64)
    profile = (f'<p class="kv one"><b>Ownership</b> {esc(own)}</p>'
               f'<p class="kv one"><b>Entity</b> {esc(clip(str(a.get("entity")) + " · " + str(a.get("fye")) + " year-end", 68))}</p>')
    right = col(card(lia_h, lia_override or mix_html(lia, "lia"), cap=clip(lia_cap, 150), style="flex:0 0 auto")
                + card("Against RBC Life and the median of OSFI filers" if cid != "rbc_life" else "Against the median of OSFI filers on this basis", table(hdr, rows, cls="sm xs"), cap=peer_cap, style="flex:0 0 auto")
                + card("", profile, style="flex:0 0 auto") + card("Read with care", bullets([clip(("† " if "not LICAT" in f else "") + f.replace("so ABL / seg fund / par CSM and the buffer are n/a", "so no CSM split and no buffer"), 150 if len(a.get("flags") or []) < 3 else 100) for f in a.get("flags") or []], 3, 160, "sm"), cls="warn"), w=452)
    if liab_only:
        title = (f"{t}: liability side only, with {usd(b.get('csm_total'))} of CSM and {usd(b.get('fcf'))} of fulfilment cash flows (est); "
                 "no public balance sheet, so no GenAcct, buffer or capital ratio")
    else:
        title = f"{t}: {usd(b.get('ga'))} GenAcct in Canada"
        if num(b.get("buffer")) is not None:
            d = b["buffer"] - AMED["buffer"]
            if any("buffer are unreliable" in f for f in a.get("flags") or []):
                title += f" with a {b['buffer']:.1f}% buffer (est) that is not reliable, because In Canada assets follow asset territory"
            else:
                title += f" with a {b['buffer']:.1f}% buffer, {'below' if d < -0.5 else 'above' if d > 0.5 else 'in line with'} the {AMED['buffer']:.1f}% peer median"
        elif a.get("buffer_note"):
            title += "; buffer not meaningful because net fulfilment cash flows are an asset"
        elif num(b.get("buffer_memo")) is not None:
            title += f"; buffer n/a under the AMF rule (memo on total CSM † {b['buffer_memo']:.1f}%)"
        if num(b.get("cap_ratio")) is not None:
            title += f"; {'LICAT' if licat else 'CARLI'} {b['cap_ratio']:.1f}%"
            if licat:
                title += f" against a {AMED['cap_ratio']:.1f}% median"
    notes = "Read with care:\n" + "\n".join(f"- {x}" for x in a.get("flags") or []) + "\n\nBlock view at fiscal year-end 2025 (C$MM):\n" + "\n".join(
        f"- [{x['side']}] {x['group']}: {x['item']}: {x['mm']:,.0f} ({x['basis']})" for x in (a.get("bs") or []) if num(x.get("mm")) is not None)
    slide(title, col(grid, w=724) + right, ALM_SRC + f"; fiscal year-end 2025 ({date}). C$, Canadian business, net of reinsurance; est = estimate",
          tag=(n, sname(cid), "Summary, Canadian business"), notes=notes, urls=collect_urls({"m": r.get("metrics")}))


def page_holdings(cid, n):
    a = AC.get(cid, {})
    at = a.get("asset_trend") or {}
    if not on_alm(cid) or not at:
        return page_holdings_fs(cid, n)
    r, b = R(cid), yb(cid)
    t, sid = tn(cid), a.get("sid")
    dates = sorted(at)
    classes = [k for k in L2_COLORS if any(num(at[d].get(k)) for d in dates)]
    series = {L2_SHORT[k]: [num(at[d].get(k)) or 0 for d in dates] for k in classes}
    colors = {L2_SHORT[k]: L2_COLORS[k] for k in classes}
    chart = stacked_columns([dfmt(d) for d in dates], series, colors, W=336, H=236)
    leg = '<div class="lg">' + "".join(f'<span><i style="background:{L2_COLORS[k]}"></i>{esc(L2_SHORT[k])}</span>' for k in classes) + "</div>"
    scope = ("legal entity, all territories" if sid in BIG3 else "consolidated, 2025 annual report (par, UL and US not separable)" if sid == "IAG" else "legal entity = Canada")
    tot = num(at[dates[-1]].get("_total_bn"))
    mix_card = card("Mix by Level 2 class" + (f", {dfmt(dates[0])} to {dfmt(dates[-1])}" if len(dates) > 1 else f" at {dfmt(dates[0])}"), chart + leg,
                    cap=f"Share of invested assets ({usd(tot * 1000) if tot else 'n/a'} at {dfmt(dates[-1])}); {scope}.", style="flex:0 0 362px")
    rows3 = [x for x in (a.get("alloc") or {}).get("l3") or [] if (num(x.get("nonpar")) or 0) > 0]
    pool = sum(num(x["nonpar"]) for x in rows3) or 1
    l3 = sorted(((x["l3"].replace("Other invested (unclassified)", "Other invested").replace("Asset Backed Securities", "Asset-backed securities"),
                  num(x["nonpar"]) / pool * 100) for x in rows3), key=lambda x: -x[1])
    l3 = [x for x in l3 if x[1] >= 0.3][:10]
    l3_chart = hbar(l3, lambda v: f"{v:.0f}%", W=340, rowh=max(20, min(30, 230 // max(len(l3), 1))), label_w=150, right_w=40, color=BLUE, top=18) if l3 else '<p class="nd">No Level 3 allocation.</p>'
    fye = dfmt(b.get("date"))
    l3_card = card(f"Non-par, non-UL pool by Level 3 class, {fye}", l3_chart,
                   cap=f"% of {usd(pool)} (est). " + (ALLOC_TXT.get(sid) or clip((a.get('alloc') or {}).get('basis_note') or '', 110) if sid in BIG3 or sid is None or sid == "IAG"
                                                       else "OSFI LF2 pool less UL policyholder funds and par assets") + ".")
    com = items(r.get("rotation_commentary"), 3)
    left = col(f'<div class="row" style="gap:12px;flex:0 0 334px;min-height:0">{mix_card}{l3_card}</div>'
               + card("What management says about repositioning", bullets(com, 3, 190, "sm")), w=736)
    hdr = ["Level 2 class"] + [dfmt(d) for d in dates] + (["Change, pts"] if len(dates) > 1 else [])
    trows = []
    for k in classes:
        v = [num(at[d].get(k)) or 0 for d in dates]
        trows.append([L2_SHORT[k]] + [f"{x:.1f}%" for x in v] + ([f"{v[-1] - v[0]:+.1f}"] if len(dates) > 1 else []))
    ul = num(at[dates[-1]].get("_ul_bn"))
    alts = peer_vals("alts_share")
    zero = [LAB[c] for c, v in alts.items() if v < 0.05 and c != cid and c != "rbc_life"]
    shown = {c: v for c, v in alts.items() if v >= 0.05 or c in (cid, "rbc_life")}
    alt_chart = peer_hbar(shown, cid, lambda v: f"{v:.0f}%", W=400, rowh=14, label_w=112, right_w=40, color=TEAL, median=AMED.get("alts_share"))
    ac = (a.get("acct") or {}).get(b.get("date")) or {}
    if ac:
        its = [("FVTPL", num(ac.get("fvtpl")) or 0), ("FVOCI", num(ac.get("fvoci")) or 0), ("Amortized cost", num(ac.get("ac")) or 0)]
        acols = [BLUE, ORANGE, GREY]
        ac_html = ('<div style="flex-shrink:0;height:18px">' + mix_bar(its, colors=acols, W=400, h=18) + '</div><div class="lg">' + "".join(
            f'<span><i style="background:{acols[i]}"></i>{esc(l)} {p:.0f}%</span>' for i, (l, p) in enumerate(its)) + "</div>"
                   + (f'<p class="cap">UL policyholder fund of {usd(ul * 1000)} is a pass-through and sits outside GenAcct.</p>' if ul else ""))
    else:
        ac_html = '<p class="nd">Accounting classes are not in the public data for this insurer.</p>'
    right = col(card("Then and now, % of invested assets", table(hdr, trows, cls="sm xs"), style="flex:0 0 auto")
                + card("Private and alternative share of the pool, fiscal year-end 2025", alt_chart,
                       cap=f"Private fixed income plus external and real-asset holdings (est). Dashed: median {AMED['alts_share']:.0f}%." + (f" None at {', '.join(zero)}." if zero else ""), style="flex:0 0 auto")
                + card(f"Accounting class of invested assets, {fye}", ac_html))
    my_alt = num(a.get("alts_share"))
    alt_txt = (f"private and alternative assets are {my_alt:.0f}% of the non-par pool against a {AMED['alts_share']:.0f}% peer median" if my_alt is not None and my_alt >= 0.5
               else "it holds no private or alternative assets (peer median {:.0f}%)".format(AMED["alts_share"]))
    if len(dates) > 1:
        ch = max(((k, (num(at[dates[-1]].get(k)) or 0) - (num(at[dates[0]].get(k)) or 0)) for k in classes), key=lambda x: abs(x[1]))
        if abs(ch[1]) < 0.5:
            top2 = max(classes, key=lambda k: num(at[dates[-1]].get(k)) or 0)
            title = f"{t}: asset mix unchanged since {dfmt(dates[0])}, with {L2_SHORT[top2].lower()} at {num(at[dates[-1]].get(top2)):.0f}%; {alt_txt}"
        else:
            title = f"{t}: {L2_SHORT[ch[0]].lower()} {'up' if ch[1] > 0 else 'down'} {abs(ch[1]):.1f} pts since {dfmt(dates[0])}; {alt_txt}"
    else:
        title = f"{t}: {l3[0][0].lower()} is the largest holding at {l3[0][1]:.0f}% of the pool; {alt_txt}" if l3 else f"{t}: {alt_txt}"
    urls = collect_urls(com)
    notes = "\n".join(f"- {txt(c)} {c.get('source', '') if isinstance(c, dict) else ''}" for c in com)
    slide(title, left + right, src_line("ALM framework: OSFI LF2 invested assets on the L1/L2/L3 taxonomy; block allocation at fiscal year-end 2025 (est); IFRS 17 periods only", urls, 2),
          tag=(n, sname(cid), "Assets and rotation"), notes=notes, urls=urls)


def page_newmoney(cid, n):
    """Net additions by Level 3 class (closing less opening balance, no run-off; est) beside the liabilities that grew."""
    a = AC.get(cid, {})
    nm = a.get("new_money") or []
    if not on_alm(cid) or not nm:
        return page_newmoney_fs(cid, n)
    t, sid = tn(cid), a.get("sid")
    w = nm[0]
    ot, ct = sum(x["open"] for x in w["rows"]), sum(x["close"] for x in w["rows"])
    net = ct - ot
    growth = net / ot if ot else 0
    keep = sorted(w["rows"], key=lambda x: -max(x["open"], x["close"]))[:7]
    short = lambda s_: s_.replace("Other invested (unclassified)", "Other invested").replace("Asset Backed Securities", "Asset-backed securities")
    labs = [short(x["l3"]) for x in keep]
    read, tilt = [], None
    period = f"{dfmt(w['start'])} to {dfmt(w['end'])}"
    if growth >= 0.05:
        series = [(f"Opening mix at {dfmt(w['start'])}", [x["open"] / ot * 100 for x in keep]),
                  (f"Share of net additions, {period}", [(x["close"] - x["open"]) / net * 100 for x in keep])]
        if len(nm) > 1:
            w2 = nm[1]
            o2, c2 = sum(x["open"] for x in w2["rows"]), sum(x["close"] for x in w2["rows"])
            if o2 and (c2 - o2) / o2 >= 0.05:
                by = {x["l3"]: x for x in w2["rows"]}
                series.append((f"Share of net additions, {dfmt(w2['start'])} to {dfmt(w2['end'])}",
                               [((by.get(x["l3"]) or {}).get("close", 0) - (by.get(x["l3"]) or {}).get("open", 0)) / (c2 - o2) * 100 for x in keep]))
        cols = [MUTED_BAR, BLUE, ORANGE]
        chart = grouped_hbar(labs, series, cols, fmt=lambda v: f"{v:.0f}%", W=640, rowh=33 if len(labs) > 5 else 44, label_w=160,
                             xlabel="% of opening invested assets (grey) / % of net additions (colour)")
        chart += '<div class="lg">' + "".join(f'<span><i style="background:{cols[i]}"></i>{esc(nme)}</span>' for i, (nme, _) in enumerate(series)) + "</div>"
        tilt = sorted(((short(x["l3"]), (x["close"] - x["open"]) / net * 100 - x["open"] / ot * 100) for x in keep), key=lambda x: -x[1])
        read.append(f"Net additions of {usd(net)} in the year to {dfmt(w['end'])}, {growth * 100:.0f}% of opening invested assets")
        read.append(f"Additions over-weight {tilt[0][0].lower()} by {tilt[0][1]:.0f} pts and under-weight {tilt[-1][0].lower()} by {-tilt[-1][1]:.0f} pts against the opening mix")
        chart_h = "Where net additions went against the opening mix (Level 3 classes)"
    else:
        its = [(short(x["l3"]), x["close"] - x["open"]) for x in keep]
        chart = hbar(its, lambda v: f"{v:+,.0f}", W=640, rowh=32, label_w=170, right_w=60, color=TEAL, xlabel=f"Change in balance, $MM, {period}")
        read.append(f"Invested assets {'grew' if net >= 0 else 'shrank'} by {usd(abs(net))} ({growth * 100:+.0f}%) in the year to {dfmt(w['end'])}: "
                    "too little net new money to read an allocation, so the chart shows the change in each balance")
        chart_h = "Change in balance by Level 3 class"
    ll = a.get("liab_line") or {}
    yrs_ = [y for y in ("2023", "2024", "2025") if ll.get(y)]
    lines = [k for k in ("Individual insurance", "Individual annuity", "Group insurance", "Group annuity", "Participating")
             if any(abs(num((ll.get(y) or {}).get(k)) or 0) >= 0.5 for y in yrs_)]
    grow = None
    if len(yrs_) >= 2:
        y0, y1 = yrs_[-2], yrs_[-1]
        dl = [(k, (num(ll[y1].get(k)) or 0) - (num(ll[y0].get(k)) or 0)) for k in lines]
        lia_chart = hbar(dl, lambda v: "0" if abs(v) < 0.5 else f"{v:+,.0f}", W=430, rowh=16, label_w=140, right_w=56, color=TEAL, xlabel="Change in fiscal 2025, $MM", tick_target=4)
        sh = line_shift(ll, y0, y1)
        if sh:  # read the two lines together
            both = sum(d for k, d in dl if k in sh)
            grow = max([(k, d) for k, d in dl if k not in sh] + [(f"{sh[0]} and {sh[1].lower()} together", both)], key=lambda x: x[1])
            read.append(f"The fiscal 2025 OSFI return moves business from the {sh[1].lower()} line to {sh[0].lower()}, so the two lines are read together ({'+' if both >= 0 else '-'}{usd(abs(both))} combined)")
        else:
            dl_pos = [(k, d) for k, d in dl if (num(ll[y1].get(k)) or 0) > 0]
            grow = max(dl_pos, key=lambda x: x[1]) if dl_pos else None
        trows = [[k] + [f"{num(ll[y].get(k)) or 0:,.0f}".replace("-0", "0") for y in yrs_] + [f"{d:+,.0f}".replace("-0", "0").replace("+0", "0") if abs(d) < 0.5 else f"{d:+,.0f}"] for (k, d) in dl]
        tbl = table(["Line"] + [dfmt(yb(cid, y).get("date")) or y for y in yrs_] + ["Change"], trows, cls="sm xs")
        if grow and grow[1] > 0:
            if not sh:
                read.append(f"Fastest-growing liability line in fiscal 2025: {grow[0].lower()} (+{usd(grow[1])}), the business the additions back")
    else:
        lia_chart, tbl = '<p class="nd">One year of product lines only.</p>', '<p class="nd">n/a</p>'
    b4, b5 = yb(cid, 2024), yb(cid, 2025)
    crow = []
    for lab, k, bk in [("ABL CSM", "csm_abl", None), ("Seg fund CSM", "seg_csm", "seg_csm_basis"), ("Par CSM", "par_csm", "par_csm_basis"), ("Total CSM", "csm_total", None)]:
        v4, v5 = num(b4.get(k)), num(b5.get(k))
        if v5 is None or (not v5 and not v4):
            continue
        crow.append([lab + (", est" if bk and "est" in str(b5.get(bk) or "") else ""), f"{v4:,.0f}" if v4 is not None else "n/a", f"{v5:,.0f}",
                     f"{(v5 / v4 - 1) * 100:+.0f}%" if v4 else "n/m"])
    nb = a.get("nb_csm") or {}
    nb_txt = f"New business CSM in 2025: {usd(nb['total'])}" + (f" ({usd(nb['total24'])} in 2024)" if nb.get("total24") else "") + f"; {nb.get('note')}." if num(nb.get("total")) else None
    csm_html = table(["CSM, net of reinsurance ($MM)", dfmt(b4.get("date")), dfmt(b5.get("date")), "Change"], crow, cls="sm xs") + (f'<p class="cap">{esc(clip(nb_txt, 100))}</p>' if nb_txt else "")
    read.append("Net additions = closing less opening balance by class, no run-off (est): cash reinvested inside a class does not show, and values move with markets")
    if sid in BIG3:
        read.append("Assets here are the legal entity across all territories; the liabilities are Canada only")
    left = col(card(chart_h, chart, style="flex:0 0 auto") + card("Reading", bullets(read, 6, 190, "sm")), w=670)
    right = col(card("Liabilities by line, net of reinsurance, excl. seg funds ($MM)", tbl, style="flex:0 0 auto")
                + card("Which liabilities grew", lia_chart, style="flex:0 0 auto") + card("CSM by piece", csm_html))
    if tilt:
        title = f"{t}: net additions over-weight {tilt[0][0].lower()} by {tilt[0][1]:.0f} pts and under-weight {tilt[-1][0].lower()} by {-tilt[-1][1]:.0f} pts against the opening mix"
    else:
        title = f"{t}: invested assets {'grew' if net >= 0 else 'shrank'} {abs(growth) * 100:.0f}% in fiscal 2025, too little net new money to read an allocation"
    if grow and grow[1] > 0:
        title += (f"; {grow[0].lower().replace(' together', '')} grew most (+{usd(grow[1])} combined)" if "together" in grow[0]
                  else f"; {grow[0].lower()} liabilities grew most (+{usd(grow[1])})")
    slide(clip(title, 235), left + right, "ALM framework: OSFI LF2 invested assets by Level 3 class and LF3 liabilities by line (Canada, net of reinsurance held); "
          "CSM split per the study. Net additions = closing less opening balance, no run-off (est)", tag=(n, sname(cid), "New money and liabilities"), notes="\n".join(read))


def page_leverage(cid, n):
    a = AC.get(cid, {})
    b = yb(cid)
    if not on_alm(cid) or num(b.get("ga")) is None:
        return page_leverage_fs(cid, n)
    r = R(cid)
    lv = r.get("leverage") or {}
    t, sid = tn(cid), a.get("sid")
    e = (a.get("earn") or {}).get("2025") or {}
    b4 = yb(cid, 2024)
    dl_, da_ = num(b.get("deriv_liab")) or 0, num(b.get("deriv_assets")) or 0
    fin, rein = num(b.get("fin_pct")) or 0, num(b.get("reins_pct")) or 0
    tiles = "".join([
        kpi("Financing / GenAcct", pc(fin), f"peer median {pc(AMED['fin_pct'])}" + (f"; {pc(b4.get('fin_pct'))} a year earlier" if num(b4.get("fin_pct")) is not None else ""), True),
        kpi("Repos", usd(b.get("repos")) if num(b.get("repos")) else "none", "counted as GenAcct financing" if num(b.get("repos")) else "none on the balance sheet"),
        kpi("Other financing", usd(b.get("fin_other")) if num(b.get("fin_other")) else "none", OTHER_FIN.get(sid, "debt and similar inside the insurer") if num(b.get("fin_other")) else "no debt inside the insurer"),
        kpi("Derivative liabilities less assets", usd(dl_ - da_) if (dl_ or da_) else "none", f"liabilities {usd(dl_) if dl_ else 'nil'}, assets {usd(da_) if da_ else 'nil'}"),
        kpi("Reinsurance / GenAcct", pc(rein), f"held assets {usd(b.get('reins_assets'))}; peer median {pc(AMED['reins_pct'])}", True)])
    fv = peer_vals("fin_pct")
    zero = [LAB[c] for c, v in fv.items() if v < 0.05 and c not in (cid, "rbc_life")]
    fin_chart = peer_hbar({c: v for c, v in fv.items() if v >= 0.05 or c in (cid, "rbc_life")}, cid, lambda v: f"{v:.1f}%", W=350, rowh=14, label_w=108, right_w=44,
                          color=BLUE, median=AMED.get("fin_pct"))
    rv = peer_vals("reins_pct")
    re_chart = peer_hbar(rv, cid, lambda v: f"{v:.0f}%", W=350, rowh=13, label_w=108, right_w=40, color=TEAL, median=AMED.get("reins_pct"))
    dv = (a.get("deriv") or {})
    dper = max(dv) if dv else None
    if dper:
        d_ = sorted(dv[dper].items(), key=lambda x: -x[1])
        big = max(v for _, v in d_)
        d_ = [(k.replace(" / n/s", "").replace("Fixed Income", "Rates and FX"), v / 1000 if big >= 1000 else v) for k, v in d_]
        dv_chart = hbar(d_[:4], (lambda v: f"{v:,.1f}") if big >= 1000 else (lambda v: f"{v:,.0f}"), W=350, rowh=17, label_w=176, right_w=44, color=PURPLE, top=18, tick_target=3)
        dv_h = f"Derivative notional by type, {'$BN' if big >= 1000 else '$MM'}"
        dv_cap = "Gross notionals at fiscal year-end 2025" + ("; legal entity, all territories." if sid in BIG3 else "; consolidated." if sid == "IAG" else "; legal entity.")
    else:
        dv_chart, dv_h, dv_cap = '<p class="nd">No derivative notionals filed.</p>', "Derivative notional by type", None
    kv = []
    tot_r, aff = num(e.get("reins_total_lf3")), num(e.get("reins_affil_lf3"))
    if tot_r and aff is not None and abs(tot_r) > 1:
        scope_r = ", legal entity, all territories" if sid in BIG3 else ""
        kv.append(("With affiliates", f"{aff / tot_r * 100:.0f}% of reinsurance held ({usd(aff)} of {usd(tot_r)}{scope_r})" if abs(aff) >= 0.5
                   else f"none of the {usd(tot_r)} of reinsurance held"))
    if (num(e.get("reins_collateral")) or 0) >= 0.5 and tot_r:
        kv.append(("Collateral held", usd(e.get("reins_collateral"))))
    rc = a.get("reins_ceded") or {}
    if num(rc.get("total")) is not None and rc["total"] >= 0.05:
        by = [f"{k.lower()} {v:.0f}%" for k, v in sorted((rc.get("by_line") or {}).items(), key=lambda x: -(x[1] or 0)) if num(v) and v >= 0.5][:3]
        kv.append(("Liabilities ceded", f"{rc['total']:.1f}% of issued insurance liabilities" + (f": {', '.join(by)}" if by else "")))
    pl = a.get("pledged") or {}
    PL = {"derivatives": "derivatives", "securities_lending": "securities lending", "repos": "repos", "reinsurance": "reinsurance", "regulatory_trust": "regulatory trusts", "other": "other"}
    if pl:
        kv.append(("Assets pledged", "; ".join(f"{PL.get(k, k)} {usd(v)}" for k, v in sorted(pl.items(), key=lambda x: -x[1]) if v >= 0.5) + (" (group)" if sid in BIG3 else "")))
    else:
        kv.append(("Assets pledged", "not disclosed for the insurer"))
    kv_html = "".join(f'<p class="kv sm"><b>{esc(k)}</b>{esc(clip(v, 170))}</p>' for k, v in kv)
    debt = [d for d in items(lv.get("debt_outstanding")) if "deposit" not in str(d.get("type", "")).lower()]
    debt_tot = sum(num(d.get("amount_cad_mm")) or 0 for d in debt)
    iss = items(lv.get("issuance"), 5)
    iss_rows = [[str(i.get("date") or "")[:7], clip(i.get("instrument"), 30), f"{num(i.get('amount_cad_mm')):,.0f}" if num(i.get("amount_cad_mm")) else "",
                 f"{num(i.get('coupon_pct')):.2f}%" if num(i.get("coupon_pct")) else ""] for i in iss]
    iss_html = (table(["Date", "Instrument", "$MM", "Coupon"], iss_rows, cls="sm xs", left=2) if iss_rows else '<p class="nd">No 2023-2026 issuance found.</p>')
    iss_cap = (f"{usd(debt_tot)} of debt and hybrids outstanding above or at the insurer, as disclosed." if debt_tot else "No debt disclosed at or above the insurer (mutual, or funded by its parent).")
    struct = [s.get("text") if isinstance(s, dict) else s for s in items(lv.get("structured_indirect"), 3)]
    rp_t, sl_t = (lv.get("repos") or {}).get("text"), (lv.get("securities_lending") or {}).get("text")
    fund = [x for x in [("Repos: " + rp_t) if rp_t else None, ("Securities lending: " + sl_t) if sl_t else None] if x] + struct
    c1 = col(card("Financing / GenAcct against peers", fin_chart, cap=f"Dashed line: peer median {AMED['fin_pct']:.1f}%." + (f" Nil at {', '.join(zero)}." if zero else ""), style="flex:0 0 auto") + card("Pledged assets and reinsurance counterparties", kv_html), w=376)
    c2 = col(card("Reinsurance held / GenAcct against peers", re_chart, cap=f"Dashed line: peer median {AMED['reins_pct']:.0f}%.", style="flex:0 0 auto") + card(dv_h, dv_chart, cap=dv_cap), w=376)
    c3 = col(card("Debt and hybrids issued by the group or parent (memo, outside GenAcct)", iss_html, cap=iss_cap, style="flex:0 0 auto")
             + card("Repo, securities lending and structured funding, as disclosed", bullets(fund, 3 if len(iss_rows) >= 5 else 4, 140, "sm")))
    body = f'<div class="col" style="flex:1;gap:12px"><div class="kpis">{tiles}</div><div class="row" style="gap:14px;flex:1;min-height:0">{c1}{c2}{c3}</div></div>'
    if fin >= 0.05:
        parts = [x for x in [f"repos {usd(b.get('repos'))}" if num(b.get("repos")) else None, f"other {usd(b.get('fin_other'))}" if num(b.get("fin_other")) else None] if x]
        title = f"{t}: financing is {fin:.1f}% of GenAcct ({', '.join(parts)}) against a {AMED['fin_pct']:.1f}% peer median"
    else:
        title = f"{t}: no financing inside the General Account"
    title += f"; reinsurance held is {rein:.0f}% of GenAcct (median {AMED['reins_pct']:.0f}%)"
    if tot_r and aff is not None and abs(tot_r) > 1 and aff / tot_r > 0.89:
        title += f", {aff / tot_r * 100:.0f}% of the " + ("legal entity's cessions" if sid in BIG3 else "cessions") + " with affiliates"
    urls = collect_urls(lv)
    slide(title, body, src_line("ALM framework: block view at fiscal year-end 2025 (OSFI LF1/LF3, annual reports); issuance from company releases", urls, 3),
          tag=(n, sname(cid), "Leverage and reinsurance"), notes=json.dumps(lv, indent=1)[:6000], urls=urls)


def to_per(iso, oct_fye):
    y, m = int(iso[:4]), int(iso[5:7])
    q = ({1: 1, 4: 2, 7: 3, 10: 4} if oct_fye else {3: 1, 6: 2, 9: 3, 12: 4}).get(m)
    return f"{y}Q{q}" if q else None


def amf_sens(rows):
    """Pivot an AMF filer's sensitivity rows (as worded in its report) into shock x measure."""
    out = {}
    for x in rows:
        it = re.sub(r",\s*2025$", "", x["item"])
        m = re.split(r" - |: ", it, maxsplit=1)
        if len(m) < 2 or num(x.get("amount")) is None:
            continue
        shock, meas = m[0].strip(), m[1].lower()
        k = ("ratio" if "ratio" in meas else "csm" if "csm" in meas else "eq" if ("equity" in meas and "net income" not in meas) or "oci" in meas
             else "ni" if re.search(r"net income|net surplus|fair value", meas) else None)
        if k:
            out.setdefault(shock, {})[k] = num(x["amount"])
            if "net income and equity" in meas:
                out[shock]["eq"] = num(x["amount"])
    return out


def page_risk(cid, n):
    a = AC.get(cid, {})
    if not on_alm(cid):
        return page_risk_fs(cid, n)
    r, b = R(cid), yb(cid)
    rk = r.get("risk") or {}
    t, sid, st = tn(cid), a.get("sid"), a["status"]
    name = NAMES[cid]
    oct_fye = sid in ("RBC", "BMO")
    hist = {to_per(d, oct_fye): (d, v) for d, v in (a.get("licat_hist") or {}).items() if to_per(d, oct_fye)}
    hist = {p: x for p, x in hist.items() if p >= "2023Q4" and num(x[1])}
    licat = is_licat(b)
    if hist:
        pts = sorted((p, num(v)) for p, (d, v) in hist.items())
        med = [(m_["per"], m_["med_total"]) for m_ in AMED["licat_series"] if m_["per"] in hist and num(m_.get("med_total"))]
        dd = {p: dfmt(d) for p, (d, v) in hist.items()}
        chart = line_chart([("Peer median", MUTED_BAR, med), (name, BLUE, pts)], W=520, H=206, ref=100, ref_label="OSFI supervisory target 100%", label_every=4,
                           xfmt=lambda p: dd.get(p, p))
        cap_card = card(f"LICAT total ratio, {dfmt(hist[pts[0][0]][0])} to {dfmt(hist[pts[-1][0]][0])}", chart,
                        cap="OSFI LCQ, quarterly, legal entity" + (" (all territories)" if sid in BIG3 else "") + ". Dashed grey = median of the eight all-Canada OSFI filers in the ALM study.",
                        style="flex:0 0 306px")
    else:
        crow = [[clip(x["item"], 62), (f"{x['amount']:,.1f}%" if "%" in x["units"] else f"{x['amount']:+.1f} pts" if "pct" in x["units"] else f"{x['amount']:,.0f}")]
                for x in (a.get("cap_rows") or []) if num(x.get("amount")) is not None and re.search(r"solvency ratio|leverage ratio|available capital|base solvency", x["item"], re.I)][:7]
        cap_card = card("Capital position as disclosed (AMF basis; $MM unless a ratio)", table(["Item", "Fiscal 2025"], crow, cls="sm xs wrap") if crow else
                        '<p class="nd">The capital ratio of the insurer is not public.</p>', cap="CARLI is the AMF's ratio and is not comparable with LICAT.", style="flex:0 0 306px")
    srows, s_cap = [], None
    fm = lambda v: "" if num(v) is None else f"{num(v):+,.0f}"
    if a.get("sens"):
        for s in a["sens"]:
            eq = s.get("equity") if num(s.get("equity")) is not None else s.get("oci")
            if all(num(s.get(k)) is None for k in ("net_income", "csm")) and num(eq) is None:
                continue
            srows.append([RISK_LAB.get(s["risk"], s["risk"]), clip(s["shock"], 26), fm(s.get("net_income")), fm(eq) + (" OCI" if num(s.get("equity")) is None and num(s.get("oci")) is not None else ""),
                          fm(s.get("csm")), f"{num(s['licat_pts']):+.1f} pts" if num(s.get("licat_pts")) is not None else ""])
        grp = "group" in str(a["sens"][0].get("basis"))
        s_cap = ("Group consolidated disclosure, not the Canadian entity" if grp else "Legal-entity disclosure") + "; $MM. Each row uses the insurer's own shock definition, so rows are not added together or compared one for one with peers."
        if not srows:
            s_cap = "Only balance-sheet changes are disclosed (liabilities and assets move together); no net income, equity or CSM effect is published."
    elif a.get("sens_rows"):
        pv = amf_sens(a["sens_rows"])
        down = [k for k in pv if re.search(r"decrease|deterioration|-\d|adverse|−", k)] or list(pv)
        for k in down[:7]:
            x = pv[k]
            srows.append(["", clip(k, 46), fm(x.get("ni")), fm(x.get("eq")), fm(x.get("csm")), f"{x['ratio']:+.1f} pts" if num(x.get("ratio")) is not None else ""])
        s_cap = "Consolidated disclosure; $MM. Each row uses the insurer's own shock definition, so rows are not added together or compared one for one with peers."
    if srows:
        hdr = ["Risk", "Shock", "Net income", "Equity", "CSM", "Capital ratio"]
        if not any(x[0] for x in srows):
            hdr, srows = hdr[1:], [x[1:] for x in srows]
        sens_html = table(hdr, srows, cls="sm xs", left=2 if len(hdr) == 6 else 1)
    else:
        sens_html = '<p class="nd">No market sensitivities are public for this insurer' + (" (OSFI returns only, no notes)." if st == "built" or sid == "COP" else ".") + "</p>"
    cp = a.get("cap") or {}
    if cp.get("mix"):
        mm_ = AMED["licat_medians"]["mix"]
        crow = [[lab, usd(cp.get(k)) if num(cp.get(k)) else "nil", pc(cp["mix"].get(mk)), pc(mm_.get(mk))] for lab, k, mk in
                [("Credit", "credit", "credit"), ("Market", "market", "market"), ("Insurance", "insurance", "insurance"),
                 ("Seg fund guarantees", "seg_risk", "seg"), ("Operational", "operational", "operational")]]
        f125 = num(cp.get("free125"))
        req_html = table(["Risk", "Required", "Share", "Median share"], crow, cls="sm xs") + (
            f'<p class="kv sm" style="margin-top:6px"><b>Base solvency buffer</b>{usd(cp.get("bsb"))} after a {usd(cp.get("div_credit"))} diversification credit</p>'
            f'<p class="kv sm"><b>Capital above 125%</b>{usd(f125)} · above 100%: {usd(cp.get("free100"))}</p>')
        req_cap = "OSFI LCQ at fiscal year-end 2025, legal entity" + (" (all territories)" if sid in BIG3 else "") + "; shares before diversification."
    else:
        comp = [[re.sub(r"BSB component - ", "", x["item"]), f"{x['amount']:,.0f}"] for x in (a.get("cap_rows") or []) if "BSB component" in x["item"] and num(x.get("amount")) is not None]
        req_html = table(["Risk (AMF base solvency buffer)", "$MM"], comp, cls="sm xs") if comp else '<p class="nd">Required capital by risk is not public for this insurer.</p>'
        req_cap = "CARLI components as disclosed, consolidated." if comp else None
    left = col(cap_card + card("Disclosed sensitivities, downside shocks", sens_html, cap=s_cap), w=548)
    target = clip(rk.get("capital_target"), 130)
    mid = col(card("Required capital by risk", req_html, cap=req_cap, style="flex:0 0 306px") + card("Risk appetite and limits", bullets(rk.get("appetite"), 3, 135, "sm")), w=318)
    rgt = col(card("Capital target", f'<p class="kv">{esc(target)}</p>' if target else '<p class="nd">Not stated.</p>', style="flex:0 0 124px")
              + card("Hedging and notable events", bullets(items(rk.get("hedging"), 2) + items(rk.get("events"), 1), 3, 120, "sm"), style="flex:0 0 216px")
              + card("Governance", bullets(rk.get("governance"), 2, 120, "sm")))
    cr = num(b.get("cap_ratio"))
    if cr is not None and licat:
        title = f"{t}: LICAT {cr:.1f}% against a {AMED['cap_ratio']:.1f}% peer median"
        if num(cp.get("free125")) is not None:
            title += f", {usd(cp['free125'])} above 125%"
    elif cr is not None:
        title = f"{t}: CARLI {cr:.1f}% (AMF basis, not comparable with LICAT)"
    else:
        title = f"{t}: capital ratio not public for the insurer"
    # a group-wide disclosure is shown in the table but does not lead the page: it is not the Canadian entity
    eqs = next((s for s in a.get("sens") or [] if s["risk"] == "equity" and num(s.get("net_income")) is not None and "group" not in str(s.get("basis"))), None)
    if eqs:
        v = num(eqs["net_income"])
        title += f"; a {eqs['shock'].replace('-', '')} equity fall {'costs ' + usd(abs(v)) + ' of net income' if abs(v) >= 0.5 else 'barely touches net income'}" + (
            " (group disclosure)" if "group" in str(eqs.get("basis")) else "")
    elif cp.get("mix"):
        top = max(("credit", "market", "insurance", "seg", "operational"), key=lambda k: num(cp["mix"].get(k)) or 0)
        title += f"; {top.replace('seg', 'seg fund guarantee')} risk is {num(cp['mix'][top]):.0f}% of required capital"
    urls = collect_urls(rk)
    notes = "\n".join(f"- {s['risk']} {s['shock']} ({s['basis']}): {s.get('applied_to')}" for s in a.get("sens") or []) + "\n\n" + json.dumps(rk, indent=1)[:5000]
    slide(title, left + mid + rgt, src_line("ALM framework: OSFI LCQ capital returns; sensitivities as worded in each insurer's 2025 report; risk appetite from MD&A", urls, 3),
          tag=(n, sname(cid), "Capital and risk"), notes=notes, urls=urls)


# ---------------------------------------------------------------- opening pages
def opening():
    n_alm = sum(1 for c in ORDER if on_alm(c))
    slide("Canadian life & health insurers: deep dives on the Canadian business of the top 20", '<p class="lead">Rebuilt on the ALM framework. Every balance-sheet, '
          'asset, leverage and capital figure is for the Canadian business, net of reinsurance, on one definition of the General Account (excl. par / seg fund), '
          'so the 20 insurers can be read side by side. Per insurer: the Canadian summary, leadership and pay, corporate structure and the entity assessed, '
          'assets and rotation, new money against liabilities, leverage and reinsurance, partnerships, and capital and risk.</p><p class="cap" style="margin-top:18px">'
          f'Prepared {TODAY}. Anchor: fiscal year-end 2025 (Oct 31, 2025 for RBC Life and BMO Life; Dec 31, 2025 for the others), with fiscal 2023 to 2025 trends and the '
          'latest OSFI quarter on trend pages. C$ throughout, in $MM and $BN. Public data only; every estimate is marked est.</p>', "Insurance Firms project", cls="title")

    # what the basis covers
    rows = []
    for i, cid in enumerate(ORDER, 1):
        a, b = AC.get(cid, {}), yb(cid)
        st = a.get("status")
        ent = a.get("entity") or ("Policies sit in Foresters Life (OSFI 28432)" if st == "covered" else "Group financial statements; no OSFI return")
        buf = pc(b.get("buffer")) if num(b.get("buffer")) is not None else ("n/m" if a.get("buffer_note") else f"† {pc(b.get('buffer_memo'))}" if num(b.get("buffer_memo")) is not None else "n/a")
        capv = pc(b.get("cap_ratio")) + ("" if is_licat(b) else " †") if num(b.get("cap_ratio")) is not None else "n/a"
        amf_ = str(st).startswith("amf")
        rows.append([f"{i}. {sname(cid)}", STATUS_TXT.get(st, ""), clip(ent, 58), dfmt(b.get("date")) if b else "", usd(b.get("ga")) if num(b.get("ga")) else "n/a", buf, capv,
                     "n/a" if amf_ or not b else pc(b.get("par_share")), pc(b.get("fin_pct")) if b else "n/a", pc(b.get("reins_pct"), 0) if b else "n/a"])
    slide(f"{n_alm} of the 20 insurers are now on one Canadian basis; Assumption Life, Humania and UV Insurance file no OSFI return and stay on their own financial statements",
          col(card("", table(["Insurer (section order)", "Basis", "Entity assessed", "Year-end", "GenAcct, est", "Buffer, est", "Capital ratio", "Par share", "Financing", "Reinsurance"],
                             rows, cls="sm uni2", left={0, 1, 2}),
                   cap="GenAcct = General Account, excl. par / seg fund. Buffer = (Surplus + ABL CSM less net derivative liabilities) / GenAcct net of repos. Financing and reinsurance held are % of GenAcct. "
                       "† AMF filers: CARLI instead of LICAT, and a memo buffer on total CSM that is not comparable. n/m: net fulfilment cash flows are an asset. "
                       "Built on ALM rules = OSFI filer outside the ALM study, built for this deck with the study's all-Canada rules and not reviewed there.")),
          ALM_SRC + "; fiscal year-end 2025")

    # RBC Life first, against peers
    bv, cv, fv, av = peer_vals("buffer"), {c: v for c, v in peer_vals("cap_ratio").items() if is_licat(yb(c))}, peer_vals("fin_pct"), peer_vals("alts_share")
    ch = lambda vals, fmt, color, key: peer_hbar(vals, "rbc_life", fmt, W=262, rowh=30 if len(vals) <= 13 else 27, label_w=92, right_w=44, color=color, median=AMED.get(key), top=20, tick_target=3)
    body = (col(card("Buffer, est", ch(bv, lambda v: f"{v:.0f}%", BLUE, "buffer"), cap=f"(Surplus + ABL CSM less net derivative liabilities) / GenAcct net of repos. Peer median {AMED['buffer']:.1f}%. MFC's figure is not reliable: its In Canada assets follow asset territory."), w=289)
            + col(card("LICAT total ratio", ch(cv, lambda v: f"{v:.0f}%", BLUE, "cap_ratio"), cap=f"OSFI filers only; legal entity. Peer median {AMED['cap_ratio']:.1f}%."), w=289)
            + col(card("Financing / GenAcct", ch({c: v for c, v in fv.items()}, lambda v: f"{v:.1f}%", BLUE, "fin_pct"), cap=f"Repos plus other financing inside the insurer. Peer median {AMED['fin_pct']:.1f}%."), w=289)
            + col(card("Private and alternative assets", ch(av, lambda v: f"{v:.0f}%", BLUE, "alts_share"), cap=f"% of the non-par, non-UL pool (est). Peer median {AMED['alts_share']:.0f}%.")))
    rb = yb("rbc_life")
    hi_fin = max(fv, key=lambda c: fv[c]) == "rbc_life"
    slide(f"RBC Life holds a {rb['buffer']:.1f}% buffer against a {AMED['buffer']:.1f}% peer median and LICAT of {rb['cap_ratio']:.1f}% against {AMED['cap_ratio']:.1f}%, "
          f"and funds {rb['fin_pct']:.1f}% of its General Account with repos" + (", the most of any insurer here" if hi_fin else ""),
          body, ALM_SRC + "; fiscal year-end 2025 (RBC Life and BMO Life Oct 31, 2025; others Dec 31, 2025). Dashed line = peer median")

    ra = AC["rbc_life"]
    e5 = ra["earn"]["2025"]
    b4 = yb("rbc_life", 2024)
    ll5, ll4 = ra["liab_line"]["2025"], ra["liab_line"]["2024"]
    lt = sum(v for v in ll5.values() if v and v > 0)
    prt = ll5["Group annuity"] / lt * 100
    ul = ra.get("ul") or {}
    cp = ra.get("cap") or {}
    good = [f"Investment risk is low: private and alternative assets are {ra['alts_share']:.0f}% of the non-par pool, against {AC['manulife']['alts_share']:.0f}% at MFC, "
            f"{AC['canada_life']['alts_share']:.0f}% at CLF and {AC['sun_life']['alts_share']:.0f}% at SLF (est)",
            f"The liabilities are long and can carry illiquid assets: group annuities are {prt:.0f}% of insurance liabilities excl. seg funds and grew {usd(ll5['Group annuity'] - ll4['Group annuity'])} in fiscal 2025",
            f"Earnings lean on spread, not underwriting: the net investment result was {usd(e5['nir'])} against an insurance service result of {usd(e5['isr'])}",
            f"Reinsurance held is modest at {rb['reins_pct']:.1f}% of GenAcct against a {AMED['reins_pct']:.1f}% median, and all of it is with an affiliate"]
    bad = [f"The cushion is thin: buffer {rb['buffer']:.1f}% against a {AMED['buffer']:.1f}% median, and LICAT {rb['cap_ratio']:.1f}% leaves {usd(cp.get('free125'))} above 125%",
           f"Repos fund {rb['fin_pct']:.1f}% of GenAcct ({pc(b4.get('fin_pct'))} a year earlier). After repo collateral, liquid and unencumbered assets are {ul.get('liquid_unenc', 0):.0f}% of the pool",
           f"The margin that backs the General Account is shrinking: ABL CSM fell {(1 - rb['csm_abl'] / b4['csm_abl']) * 100:.0f}% in fiscal 2025 to {usd(rb['csm_abl'])}, while growth came in group annuities and group insurance, which add little CSM",
           "Sensitivities, duration and the surplus portfolio are not public for the legal entity, so outsiders cannot size its rate and spread risk"]
    todo = [f"Test how much private credit fits inside the {usd(cp.get('free125'))} of capital above 125% LICAT: the liabilities would carry more than the {ra['alts_share']:.0f}% held today",
            "Set an encumbrance and liquidity limit for repo funding, since it is the one funding source no other peer leans on",
            "Rebuild ABL CSM through individual insurance and annuity sales, or accept a thinner buffer as group annuities grow",
            "Publish, or at least prepare, entity-level sensitivities on the peers' shock definitions so the comparison can be closed"]
    slide("RBC Life pairs low investment risk and long liabilities with a below-median capital cushion and the heaviest repo funding; room for more private credit is the open question",
          col(card("Where the position is sound", bullets(good, 4, 230, "lg"))) + col(card("Where it is exposed", bullets(bad, 4, 240, "lg")))
          + col(card("What could be done about it", bullets(todo, 4, 230, "lg"), cap="Options to test, drawn from the ALM study's findings; not recommendations on internal limits, which are outside public data."), w=372),
          ALM_SRC + "; ALM study findings BI-01 to BI-05. est = estimate")

    # who manages the money + CIO tenure
    rows = []
    for cid in ORDER:
        cio = lead(cid)["cio"]
        ents = [short_label(e, 40) for e in ga_managers(cid)[:2]]
        if cid == "canada_protection_plan":
            ents = ["Foresters Life (underwriter)"]
        rows.append([NAMES[cid], clip(", ".join(ents) or "not disclosed", 70),
                     short_label(cio["name"], 30) if cio else "not named", f"{yrs(cio.get('seat_since')):.0f}y" if cio and yrs(cio.get("seat_since")) is not None else "",
                     f"{yrs(cio.get('firm_since')):.0f}y" if cio and yrs(cio.get("firm_since")) is not None else "",
                     money(cio.get("comp_total_cad") or cio.get("comp_total"), cio.get("comp_currency"), cio.get("comp_year")) or "n/d" if cio else ""])
    slide("Who runs the money: affiliated asset managers at the large groups, in-house teams or parents' managers elsewhere",
          col(table(["Insurer", "General Account manager(s)", "Most senior investment officer", "In seat", "At firm", "Latest pay"], rows, cls="sm uni", left={0, 1, 2})),
          "Web research: company leadership pages, proxy circulars, annual reports (see each insurer's leadership page)")

    # coverage heatmap
    alm_lvl = lambda c: {"study": 3, "built": 3, "amf": 1, "amf_liab": 1}.get(AC.get(c, {}).get("status"), 0)
    secs = [("Canada block view", alm_lvl),
            ("Assets (L3)", lambda c: 3 if on_alm(c) and len(AC[c].get("asset_trend") or {}) > 1 else 1 if (on_alm(c) and AC[c].get("asset_trend")) or QC.get(c, {}).get("mix_history") else 0),
            ("New money", lambda c: 3 if on_alm(c) and AC[c].get("new_money") else 1 if QC.get(c, {}).get("new_money") else 0),
            ("Leverage", lambda c: 3 if num(yb(c).get("fin_pct")) is not None else 1 if (R(c).get("leverage") or {}).get("debt_outstanding") else 0),
            ("Capital", lambda c: 3 if (AC.get(c, {}).get("cap") or {}).get("mix") else 1 if capital(c)[0] else 0),
            ("Sensitivities", lambda c: 3 if any(num(s.get("net_income")) is not None for s in AC.get(c, {}).get("sens") or []) or AC.get(c, {}).get("sens_rows") else 1 if QC.get(c, {}).get("sensitivities") else 0),
            ("Org chart", lambda c: (lambda L: 3 if (L["ceo"] and L["cio"] and L["drs"]) else 1 if (L["ceo"] or L["cio"]) else 0)(lead(c))),
            ("Pay", lambda c: (lambda L: 3 if (pay(L["ceo"]) and pay(L["cio"])) else 1 if (pay(L["ceo"]) or pay(L["cio"])) else 0)(lead(c))),
            ("Partnerships", lambda c: sum(len((R(c).get("partnerships") or {}).get(k) or []) for k in ("underwriters", "deals", "sponsorships")))]
    th = "".join(f"<th>{esc(s)}</th>" for s, _ in secs)
    trs = []
    for cid in ORDER:
        cells = []
        for s, f in secs:
            try:
                v = f(cid)
            except Exception:
                v = 0
            lvl = 0 if v == 0 else 1 if v < 3 else 2
            cells.append(f'<td class="h{lvl}">{"●" if lvl else "–"}</td>')
        trs.append(f'<tr><td class="l">{esc(NAMES[cid])}</td>{"".join(cells)}</tr>')
    heat = f'<table class="heat"><thead><tr><th class="l">Insurer</th>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table>'
    legend = ('<p class="cap">Dark blue ● full view on the Canadian basis (or, for people pages, CEO, CIO and direct reports named and both paid figures disclosed) · teal ● partial: AMF rule, '
              'consolidated or financial-statement figures only · – not public. The AMF and FCNB filers publish no return with Canadian blocks, and OSFI-only filers publish no notes, so no sensitivities.</p>')
    slide("The Canadian view is complete for the OSFI filers and thins out for the Quebec and New Brunswick insurers: read their gaps as findings, not omissions",
          col(card("What the public record supports, by insurer and page", heat + legend)), "ALM framework data layer and web research; count of sourced data points per page")


def closing():
    rows = [["Basis", "Canadian business only, net of reinsurance, IFRS 17 periods only. OSFI filers: LF3 In Canada schedule for groups with foreign business, legal entity for all-Canada filers. "
                      "Fiscal year-end anchor: Oct 31, 2025 (RBC Life, BMO Life), Dec 31, 2025 (others)"],
            ["GenAcct and blocks", "General Account, excl. par / seg fund; separate blocks for reinsurance, UL policyholder fund, seg funds, par, investment contracts and other assets. Every block balances; "
                                   "fulfilment cash flows are the residual (est)"],
            ["Buffer and ratios", "Buffer = (Surplus + ABL CSM less net derivative liabilities) / (GenAcct less repos less derivative assets). Par share = par / (par + GenAcct). "
                                  "Financing and reinsurance held are % of GenAcct. AMF filers: total CSM only, buffer n/a, memo buffer † on total CSM"],
            ["CSM split", "ABL CSM, seg fund CSM and par CSM. Seg fund CSM from the gap between the balance-sheet CSM and the LICAT CSM line where not disclosed (est); par CSM pro rata where not disclosed (est)"],
            ["Assets", "OSFI LF2 invested assets on the L1 / L2 / L3 taxonomy; the non-par, non-UL pool at fiscal year-end 2025 is allocated by block (est). MFC and SLF follow the global mix; "
                       "CLF uses its disclosed Canada column. Net additions = closing less opening balance by class, no run-off (est)"],
            ["Capital and sensitivities", "OSFI LCQ (LICAT total, required capital by risk, capital above 125% and 100%). Sensitivities as worded in each insurer's 2025 report; never combined across risks or re-based to a common shock"],
            ["Insurers outside the study", "Canadian Premier and Primerica Life Canada: built here from the study's OSFI panel on its all-Canada rules, not reviewed in the study. Assumption Life, Humania and UV Insurance: "
                                           "no OSFI return, so their pages stay on financial statements (earlier method). Canada Protection Plan is a Foresters Life brand"],
            ["People, structure, partnerships", "Unchanged from the earlier deck (the ALM framework does not cover them): operating entities from each insurer's own website, tenure from LinkedIn where read, "
                                                "pay from proxy circulars, dealers from pricing releases"]]
    slide("Method and sources", col(card("How each figure was built", table(["Item", "Source and method"], rows, cls="wrap roomy2", left=2))),
          "Insurance Firms project; ALM framework: MooseDragon/cdn-life-insurer-alm; code in analysis/insurer_deep_dive")


# ---------------------------------------------------------------- build
opening()
for n, cid in enumerate(ORDER, 1):
    page_summary(cid, n)
    page_org(cid, n)
    page_pm(cid, n)
    page_holdings(cid, n)
    page_newmoney(cid, n)
    page_leverage(cid, n)
    page_partners(cid, n)
    page_risk(cid, n)
closing()

CSS = f"""
@page {{ size: 1280px 720px; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #fff; }}
body {{ font-family: Inter, "Helvetica Neue", Arial, sans-serif; color: {INK}; font-size: 12.5px; line-height: 1.4; }}
.slide {{ position: relative; width: 1280px; height: 720px; padding: 22px 44px 0; overflow: hidden; break-after: page; }}
.slide:last-child {{ break-after: auto; }}
.tag {{ font-size: 11px; color: {SUB}; letter-spacing: .02em; height: 16px; }}
.tag b {{ color: {BLUE}; font-weight: 700; }}
.tag .pill {{ display: inline-block; background: {FOCUS_BG}; color: {BLUE}; border-radius: 10px; padding: 0 8px; margin-left: 6px; font-weight: 600; }}
h1 {{ font-family: Georgia, "Liberation Serif", "DejaVu Serif", serif; font-weight: 400; font-size: 22px; line-height: 1.22; margin: 4px 0 0; max-width: 1190px; height: 56px; overflow: hidden; }}
.slide.title h1 {{ font-size: 40px; max-width: 1000px; margin-top: 140px; height: auto; }}
.body {{ position: absolute; top: 104px; left: 44px; width: 1192px; height: 562px; display: flex; gap: 14px; align-items: stretch; }}
.slide.title .body {{ top: 300px; height: 300px; display: block; }}
.foot {{ position: absolute; left: 44px; right: 44px; bottom: 14px; display: flex; justify-content: space-between; gap: 30px; font-size: 10px; color: {SUB}; line-height: 1.3; }}
.col {{ display: flex; flex-direction: column; min-width: 0; }}
.col > .card {{ flex-shrink: 0; }}
.col > .card:last-child {{ flex-grow: 1; }}
.row {{ display: flex; min-width: 0; }}
.card {{ background: #fff; border: 1px solid #e1e4e8; border-radius: 6px; padding: 10px 13px; display: flex; flex-direction: column; gap: 5px; min-width: 0; overflow: hidden; }}
.card.warn {{ background: #fff8ee; border-color: #f0d9b5; }}
.card h2 {{ font-size: 13px; font-weight: 600; margin: 0; }}
.cap {{ font-size: 10.5px; color: {SUB}; line-height: 1.35; margin: 0; }}
.lead {{ font-size: 15px; line-height: 1.45; margin: 6px 0 0; }}
.lead.sm {{ font-size: 13px; }}
.nd {{ color: {SUB}; font-style: italic; margin: 2px 0; }}
ul {{ margin: 2px 0 0; padding-left: 16px; }}
li {{ margin: 0 0 5px; font-size: 12.5px; line-height: 1.38; }}
ul.sm li {{ font-size: 11.5px; margin-bottom: 3px; }}
.kgrid {{ display: grid; grid-template-columns: repeat(3, 1fr); grid-auto-rows: 1fr; gap: 10px; height: 100%; }}
.kpis {{ display: flex; gap: 10px; }}
.kpi {{ flex: 1; border: 1px solid #e1e4e8; border-radius: 6px; padding: 9px 12px; min-width: 0; }}
.kpi span {{ font-size: 11px; color: {SUB}; display: block; }}
.kpi b {{ display: block; font-size: 23px; font-weight: 600; margin: 3px 0 1px; letter-spacing: -0.01em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.kgrid .kpi b {{ font-size: 25px; }}
.kpi.acc b {{ color: {BLUE}; }}
.kpi small {{ font-size: 10.5px; color: {SUB}; display: block; line-height: 1.3; }}
.lg2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2px 16px; margin-top: 5px; }}
.lg2 .lgrow {{ font-size: 11px; }}
.lgcol {{ display: flex; flex-direction: column; gap: 3px; margin-top: 8px; }}
.lgrow {{ display: flex; align-items: center; gap: 7px; font-size: 12px; }}
.lgrow i {{ width: 10px; height: 10px; border-radius: 3px; flex: 0 0 10px; }}
.lgrow span {{ flex: 1; }}
.lg {{ display: flex; flex-wrap: wrap; gap: 3px 14px; font-size: 11px; }}
.lg i {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px; vertical-align: -1px; margin-right: 5px; }}
.kv {{ margin: 0 0 4px; font-size: 12.5px; }}
.kv.sm {{ font-size: 11.5px; margin: 0 0 3px; line-height: 1.35; }}
table.roomy2 td {{ padding: 6px 9px; font-size: 12px; }}
table.uni2 td {{ padding: 2.5px 6px; font-size: 11.5px; }}
ul.lg li {{ font-size: 14.5px; line-height: 1.45; margin-bottom: 14px; }}
.kv.one {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin: 0 0 2px; font-size: 11.5px; }}
.kv b {{ color: {SUB}; font-weight: 600; margin-right: 6px; }}
table {{ border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; font-size: 12px; }}
th {{ font-weight: 600; color: {SUB}; text-align: right; border-bottom: 1px solid #9aa0a8; padding: 4px 6px; font-size: 10.5px; vertical-align: bottom; }}
td {{ text-align: right; padding: 4px 6px; border-bottom: 1px solid {GRID}; white-space: nowrap; vertical-align: top; }}
th.l, td.l {{ text-align: left; }}
table.sm td {{ font-size: 11.5px; padding: 3px 6px; }}
table.xs td {{ padding: 1.5px 6px; }}
table.wrap td {{ white-space: normal; }}
table.roomy td {{ padding: 8px 9px; font-size: 13px; }}
table.uni td {{ padding: 4.5px 6px; font-size: 11.5px; }}
table.tl td.yr {{ color: {BLUE}; font-weight: 700; width: 44px; }}
table.heat td {{ text-align: center; padding: 2.5px 6px; font-size: 12px; }}
table.heat td.l {{ text-align: left; }}
table.heat th {{ text-align: center; }}
td.h2 {{ color: {BLUE}; background: #eef4fb; }}
td.h1 {{ color: {TEAL}; background: #f2f8f7; }}
td.h2, td.h1 {{ font-size: 15px !important; line-height: 1; }}
td.h0 {{ color: #b0b5bd; }}
.org {{ position: relative; display: flex; flex-direction: column; align-items: center; height: 100%; justify-content: flex-start; }}
.orgcard {{ padding: 10px 12px; }}
.pbox.big {{ width: 380px; height: 140px; overflow: hidden; }}
.pbox.big .ptitle {{ max-height: 15px; white-space: nowrap; text-overflow: ellipsis; }}
.pbox.sm {{ width: 196px; height: 104px; overflow: hidden; padding: 6px 9px; border-left-width: 3px; }}
.pbox.sm .pname {{ font-size: 13px; line-height: 1.2; }}
.pbox.sm .ptitle {{ font-size: 10px; max-height: 26px; margin-bottom: 1px; line-height: 1.28; }}
.pbox.sm .role {{ font-size: 8.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.pbox.sm.more {{ border-left-color: {MUTED_BAR}; }}
.pbox.wide {{ width: 812px; height: auto; }}
.pbox.big.empty {{ width: 380px; }}
.drgrid {{ display: flex; flex-wrap: wrap; gap: 8px; width: 812px; height: 216px; align-content: flex-start; justify-content: center; }}
.drgrid.fn {{ width: 814px; }}
.pbox.sm.fn {{ width: 266px; }}
.drlab {{ font-size: 10.5px; color: {SUB}; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; margin-bottom: 5px; }}
.via {{ position: absolute; left: 10px; top: -1px; font-size: 10.5px; color: {ORANGE}; font-weight: 600; white-space: nowrap; }}
.rl {{ float: right; font-size: 8px; font-weight: 600; text-transform: none; letter-spacing: 0; padding: 0 4px; border-radius: 6px; }}
.rl.st {{ background: #eef4fb; color: {BLUE}; }}
.rl.inf {{ background: #f3f3f3; color: {SUB}; }}
.pbox.sm .rl {{ display: none; }}
.pbox.sm.inf {{ border-left-style: dashed; }}
.etree {{ display: flex; flex-direction: column; gap: 5px; }}
.etree > * {{ flex-shrink: 0; }}
.etree.c2, .etree.c3 {{ display: block; column-gap: 10px; }}
.etree.c2 {{ column-count: 2; }}
.etree.c3 {{ column-count: 3; }}
.etree.c2 .ent, .etree.c3 .ent {{ break-inside: avoid; margin-bottom: 4px; padding: 2px 7px; font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.etree.c3 .ent {{ font-size: 10px; }}
.ent {{ border: 1px solid #d6dae0; border-left: 4px solid {TEAL}; border-radius: 5px; padding: 4px 9px; font-size: 12px; background: #fff; }}
.ent.me {{ border-left-color: {BLUE}; background: {FOCUS_BG}; }}
.ent span {{ display: block; color: {SUB}; font-size: 10.5px; line-height: 1.3; }}
.alda {{ margin: 4px 0 2px; font-size: 12px; }}
.alda b {{ color: {RED}; font-size: 15px; margin-right: 4px; }}
.alda span {{ display: block; font-size: 10px; color: {SUB}; }}
.row > .card {{ min-width: 0; }}
.row > .card:last-child {{ flex: 1; }}
.ph {{ display: flex; align-items: center; justify-content: center; background: #f7f8fa; border-radius: 5px; color: {SUB}; font-style: italic; padding: 20px; text-align: center; }}
.tier {{ display: flex; gap: 12px; justify-content: center; }}
.conn {{ position: relative; width: 2px; height: 12px; background: {MUTED_BAR}; }}
.pbox {{ border: 1px solid #d6dae0; border-left: 4px solid {BLUE}; border-radius: 6px; padding: 7px 11px; background: #fff; }}
.pbox.empty {{ border-left-color: {MUTED_BAR}; width: 300px; color: {SUB}; }}
.pbox .role {{ font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: {BLUE}; font-weight: 700; }}
.pbox .pname {{ font-size: 15px; font-weight: 600; }}
.pbox .ptitle {{ font-size: 11px; color: {SUB}; line-height: 1.3; margin-bottom: 3px; max-height: 29px; overflow: hidden; }}
.pbox .prior {{ font-size: 10px; color: {SUB}; line-height: 1.25; max-height: 26px; overflow: hidden; }}
.comp {{ display: flex; justify-content: space-between; align-items: baseline; border-top: 1px solid {GRID}; margin-top: 3px; padding-top: 2px; }}
.comp span {{ font-size: 10px; color: {SUB}; }}
.comp b {{ font-size: 13px; color: {INK}; }}
.comp.nd b {{ color: {SUB}; font-weight: 500; font-style: italic; }}
.mini {{ border-left: 3px solid {TEAL}; padding: 2px 8px; margin-bottom: 7px; font-size: 12px; }}
.mini span {{ color: {SUB}; font-size: 11px; }}
.tree {{ display: flex; flex-direction: column; align-items: center; padding: 6px 0; }}
.node {{ border: 1px solid #d6dae0; border-top: 4px solid {TEAL}; border-radius: 6px; padding: 8px 10px; width: 180px; text-align: center; font-size: 12px; background: #fff; }}
.node.top {{ border-top-color: {BLUE}; width: 320px; }}
.node.top span {{ display: block; color: {SUB}; font-size: 11px; }}
.vline {{ width: 2px; height: 14px; background: {MUTED_BAR}; }}
.hl {{ height: 2px; background: {MUTED_BAR}; }}
.kids {{ display: flex; gap: 10px; width: 100%; border-top: 2px solid {MUTED_BAR}; padding-top: 12px; }}
.kids .node {{ position: relative; flex: 1; width: auto; }}
.kids .node::before {{ content: ''; position: absolute; top: -14px; left: 50%; width: 2px; height: 12px; background: {MUTED_BAR}; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.chipx {{ border: 1px solid #cfd5dd; border-radius: 4px; padding: 3px 7px; font-size: 12px; font-weight: 600; }}
.chipx small {{ display: block; font-weight: 400; color: {SUB}; font-size: 10px; }}
svg {{ max-width: 100%; height: auto; }}
svg text {{ font-family: Inter, "Helvetica Neue", Arial, sans-serif; fill: {INK}; }}
svg text.tk {{ font-size: 10px; fill: {SUB}; }}
svg text.lb {{ font-size: 11.5px; }}
svg text.vl {{ font-size: 11px; }}
svg text.sg {{ font-size: 10px; fill: #fff; font-weight: 600; }}
"""

pages = []
for i, s in enumerate(SLIDES, 1):
    tag = ""
    if s["tag"]:
        k, nm, sec = s["tag"]
        tag = f'<b>{k:02d} · {esc(nm)}</b><span class="pill">{esc(sec)}</span>'
    pages.append(f'<section class="slide {s["cls"]}"><div class="tag">{tag}</div><h1>{esc(s["title"])}</h1>'
                 f'<div class="body" data-shot="{i:03d}">{s["body"]}</div>'
                 f'<div class="foot"><span>{esc(clip(s["source"], 230))}</span><span>{i} / {len(SLIDES)}</span></div></section>')
DOC = (f'<!doctype html><html><head><meta charset="utf-8"><title>Canadian L&H insurer deep dives</title><style>{CSS}</style>'
       f'</head><body>{"".join(pages)}</body></html>')

NODE = """
const { chromium } = require('playwright');
(async () => {
  const [html, pdf, shots] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2 });
  await p.goto('file://' + html);
  await p.evaluate(() => document.fonts.ready);
  const over = await p.evaluate(() => [...document.querySelectorAll('.body')].map((b, i) => {
    const bad = [...b.querySelectorAll('.card, .kgrid, .org')].filter(c => c.scrollHeight > c.clientHeight + 2 || c.getBoundingClientRect().bottom > b.getBoundingClientRect().bottom + 2);
    return bad.length ? (i + 1) + ':' + bad.map(c => ((c.querySelector('h2') || {}).textContent || c.className).slice(0, 18) + '+' + (c.scrollHeight - c.clientHeight)).join('|') : null; }).filter(Boolean));
  console.log('OVERFLOW', JSON.stringify(over));
  await p.pdf({ path: pdf, width: '1280px', height: '720px', printBackground: true, preferCSSPageSize: true,
                margin: { top: 0, right: 0, bottom: 0, left: 0 } });
  if (shots !== '-') {
    for (const el of await p.$$('section.slide')) {
      const i = await (await el.$('[data-shot]')).getAttribute('data-shot');
      await el.screenshot({ path: shots + '/' + i + '.png' });
    }
  }
  await b.close();
})();
"""

with tempfile.TemporaryDirectory() as tmp:
    html_path = os.path.join(tmp, "deck.html")
    js_path = os.path.join(tmp, "print.js")
    shots = os.environ.get("SHOTS") or os.path.join(tmp, "shots")
    os.makedirs(shots, exist_ok=True)
    Path(html_path).write_text(DOC, encoding="utf-8")
    Path(js_path).write_text(NODE)
    if os.environ.get("KEEP_HTML"):
        Path(os.environ["KEEP_HTML"]).write_text(DOC, encoding="utf-8")
    subprocess.run(["node", js_path, html_path, str(PDF_OUT), "-" if os.environ.get("PDF_ONLY") else shots], check=True)
    if os.environ.get("PDF_ONLY"):
        print("wrote", PDF_OUT, "slides:", len(SLIDES))
        sys.exit(0)

    # pptx: each slide is the full rendered page as an image, with the title as native (hidden-behind) text for search,
    # and the slide's research detail plus full source URLs in the speaker notes
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    PX = 1 / 96
    for i, s in enumerate(SLIDES, 1):
        sl = prs.slides.add_slide(prs.slide_layouts[6])
        png = os.path.join(shots, f"{i:03d}.png")
        # 256-colour palette PNG: the flat dashboard palette survives intact at about 40% of the file size
        Image.open(png).convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(png, optimize=True)
        sl.shapes.add_picture(png, 0, 0, width=prs.slide_width, height=prs.slide_height)
        # native title over the rendered title so it can be edited and searched
        cover = sl.shapes.add_shape(1, Inches(40 * PX), Inches(38 * PX), Inches(1200 * PX), Inches(62 * PX))
        cover.fill.solid()
        cover.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        cover.line.fill.background()
        is_title = s["cls"] == "title"
        if is_title:
            sl.shapes._spTree.remove(cover._element)
        else:
            tf = cover.text_frame
            tf.word_wrap = True
            tf.margin_left = Inches(4 * PX)
            tf.margin_top = tf.margin_bottom = 0
            tf.vertical_anchor = MSO_ANCHOR.TOP
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT
            r = p.add_run()
            r.text = s["title"]
            r.font.name, r.font.size = "Georgia", Pt(16.5)
            r.font.color.rgb = RGBColor(0x1F, 0x23, 0x29)
        notes = s["title"] + "\n\nSource: " + s["source"] + "\n\n" + (s.get("notes") or "")
        if s["urls"]:
            notes += "\n\nSources:\n" + "\n".join(dict.fromkeys(s["urls"]))
        sl.notes_slide.notes_text_frame.text = notes[:20000]
    prs.save(PPTX_OUT)
print("wrote", PDF_OUT, "and", PPTX_OUT, "slides:", len(SLIDES))
