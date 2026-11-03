"""Build the deep-dive deck on the 20 Canadian life & health insurers in the analysis set.

Each insurer gets seven pages: summary and business mix, leadership org chart, portfolio-management construct,
portfolio holdings over time, leverage and funding, bank/sponsor partnerships, and risk constructs.

Every slide is an HTML page (1280 x 720) in the project's dashboard style with inline-SVG charts, printed to PDF
with the preinstalled Playwright Chromium; the .pptx carries native title and source text, the slide body as a
2x image, and the slide's text plus full source URLs in the speaker notes.

Inputs: quant.json (python3 analysis/insurer_deep_dive/quant.py), research/<company_id>.json (web research),
prices.csv (share prices). Run from the repository root:
    python3 analysis/insurer_deep_dive/quant.py
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
NOW = 2026.84  # 3 Nov 2026
TODAY = "3 Nov 2026"

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
    v = num(mm)
    if v is None:
        return "n/d"
    b = v / 1000
    if abs(b) < 1 and digits is None:
        return f"C${v:,.0f}MM"
    d = digits if digits is not None else (0 if b >= 100 else 1)
    return f"C${b:,.{d}f}bn"


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


def clip(t, n=150):
    t = re.sub(r"\s+", " ", scrub(t)).strip()
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
    return (f'<div class="kpi{" acc" if accent else ""}"><span>{esc(label)}</span><b>{esc(value)}</b>'
            f'<small>{esc(sub)}</small></div>')


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
    return clip(re.split(r" \(", str(t))[0], n)


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


# ---------------------------------------------------------------- ordering
def order():
    def size(cid):
        v = ga_mm(cid)
        return v if v is not None else -1
    ids = [c for c in NAMES if c != "canada_protection_plan"]
    ids.sort(key=lambda c: -size(c))
    # Canada Protection Plan sits right after Foresters Life, which underwrites it
    i = ids.index("foresters_life")
    ids.insert(i + 1, "canada_protection_plan")
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
        return out, ("Foresters Life: " if src != cid else "") + f"% of C${tot / 1000:,.1f}bn; OSFI LF3 P22010 by line (CSM carved out pro rata), CSM, surplus"
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
        basis = (f"% of C${tot / 1000:,.1f}bn; annual-report notes {asof}, general fund (segregated funds excluded), CSM carved out of lines pro rata"
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


def page_summary(cid, n):
    r, q = R(cid), QC.get(cid, {})
    name = NAMES[cid]
    ga = ga_mm(cid)
    cap, fw, cap_asof = capital(cid)
    tiles = []
    ga_src = (q.get("landscape") or {}).get("portfolio_as_of")
    tiles.append(kpi("General-account invested assets", bn(ga) if ga else "n/d",
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
    title = f"{name}: {bn(ga) if ga else 'undisclosed'} general account"
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
    slide(title, body, src, tag=(n, name, "Summary"), notes=notes, urls=urls)


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
        how = [f"Policies are underwritten by {COVERED_BY[cid]}; its general account and investment team manage the assets"] + how
    tg = items(r.get("target_allocations"), 4)
    tg_html = table(["Asset class", "Target / stated range"], [[clip(t.get("asset_class"), 30), clip(t.get("target"), 70)] for t in tg],
                    cls="sm wrap") if tg else '<p class="nd">No target allocation disclosed.</p>'
    right = col(card("Who manages the general account", bullets(how, 6, 165, "sm"), style="flex:0 0 318px")
                + card("Disclosed targets", tg_html))
    mgr = ga_managers(cid)
    if cid in COVERED_BY:
        head = f"a {COVERED_BY[cid]} brand: assets sit in {COVERED_BY[cid]}'s general account"
    elif oe and mgr:
        head = f"{len(oe['entities'])} operating entities on its site; general account run by {short_label(mgr[0], 60)}"
    elif oe:
        head = f"{len(oe['entities'])} operating entities on its site; general-account manager not stated there"
    elif mgr:
        head = f"general account run by {short_label(mgr[0], 60)}; no entity list on its website"
    else:
        head = "no entity list on its website and no stated general-account manager"
    title = f"{name}: " + clip(head, 140)
    urls = collect_urls(oe or {}) + collect_urls(pm) + collect_urls(tg)
    notes = ("Operating entities (" + str((oe or {}).get("source_url")) + "):\n" + "\n".join(
        f"- {e.get('name')} (parent: {e.get('parent')}): {e.get('description') or ''}" for e in items((oe or {}).get("entities")))
             + "\n\n" + (pm.get("summary") or "") + "\n" + "\n".join(f"- {b}" for b in how))
    slide(title, left + right, src_line("Insurer's own website (entities page); company and asset-manager disclosures", urls),
          tag=(n, name, "Corporate structure"), notes=notes, urls=urls)


PROSE = {"Bonds": "bonds", "Mortgages (real-estate debt)": "mortgages", "Equity: public": "public equity",
         "Equity: private, infra & alts": "private equity & infra", "Equity: commercial real estate": "CRE equity",
         "Cash & short-term": "cash"}
SHORT = {"Bonds": "Bonds", "Mortgages (real-estate debt)": "Mortgages (RE debt)", "Equity: public": "Equity: public",
         "Equity: private, infra & alts": "Equity: private & infra", "Equity: commercial real estate": "Equity: CRE",
         "Cash & short-term": "Cash & short-term"}


def page_holdings(cid, n):
    r, q = R(cid), QC.get(cid, {})
    name = NAMES[cid]
    mh = q.get("mix_history") or []
    rot = q.get("rotation_yoy_pp") or {}
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
        cum = {c["asset_class"]: c for c in q.get("cumulative") or []}
        for k in CLASSES:
            c = cum.get(k)
            if c and num(c.get("reallocation_cad_mm")) is not None:
                act.append((SHORT[k], num(c["reallocation_cad_mm"]) / 1000))
        small = bool(act) and max(abs(v) for _, v in act) < 1
        if small:
            act = [(k, v * 1000) for k, v in act]
        act = [(k, v) for k, v in act if abs(v) >= (0.05 if not small else 0.5)]
        clean_rot = [v for k, v in rot.items() if not k.startswith("2023")] or list(rot.values())
        avg_rot = sum(clean_rot) / len(clean_rot) if clean_rot else None
        big = max(rows, key=lambda x: abs(float(x[3]))) if rows else None
        mix_h = f"Invested-asset mix, {first['period']} to {last['period']} ({q.get('mix_frequency', '').lower()})"
        p0, p1 = first["period"], last["period"]
    else:
        chart = f'<div class="ph" style="height:228px">{esc(nd_txt)}</div>'
        mix_h, p0, p1 = "Invested-asset mix", "Start", "Latest"
    leg = '<div class="lg">' + "".join(f'<span><i style="background:{CLASS_COLORS[k]}"></i>{esc(k)}</span>' for k in CLASSES) + "</div>"
    mix_card = card(mix_h, chart + leg, cap="Share of invested assets by harmonised class; excludes policy loans, derivatives, seg funds and pass-through fund units.",
                    style="flex:0 0 322px")
    com_card = card("What management says about repositioning", bullets(com, 3, 170, "sm"))
    es = q.get("equity_split") or {}
    alda = num(q.get("alda_pct"))
    ah = [(x["period"][2:4] + x["period"][4:], x["pct"]) for x in q.get("alda_history") or [] if num(x.get("pct")) is not None]
    if es:
        eq_items = [({"Commercial real estate": "Commercial RE"}.get(k, k), num(v) or 0) for k, v in es["items"].items()]
        eq_html = hbar(eq_items, lambda v: f"{v:.1f}%", W=270, rowh=19, label_w=120, right_w=44, color=ORANGE, top=6)
        eq_html += (f'<div class="alda"><b>ALDA {alda:.1f}%</b> of GA<span>private + infra + CRE equity, {esc(es.get("as_of", ""))}</span></div>'
                    if alda is not None else "")
        if len(ah) > 2:
            eq_html += (f'<p class="cap">Same definition on the history (private, infra &amp; alts + CRE equity): {ah[0][1]:.1f}% in '
                        f'{esc(q["alda_history"][0]["period"])}, {ah[-1][1]:.1f}% in {esc(q["alda_history"][-1]["period"])}.</p>')
    else:
        eq_html = f'<p class="nd">{esc(nd_txt) if cid in COVERED_BY else "No equity breakdown disclosed."}</p>'
    eq_card = card("Equity split and ALDA, % of GA", eq_html, style="flex:0 0 296px")
    bottom = f'<div class="row" style="gap:12px;flex:1;min-height:0">{eq_card}{com_card}</div>'
    tbl = table(["Asset class", p0, p1, "Δ pp"], rows, cls="sm xs") if rows else f'<p class="nd">{esc(nd_txt) if not mh else "n/d"}</p>'
    rot_items = [(k[:4], v) for k, v in sorted(rot.items())]
    rot_chart = hbar(rot_items, lambda v: f"{v:.1f}pp", W=400, rowh=17, label_w=50, right_w=50, color=ORANGE) if rot_items else '<p class="nd">n/d</p>'
    act_chart = (hbar(act, (lambda v: f"{v:+,.0f}") if small else (lambda v: f"{v:+.1f}"), W=400, rowh=17, label_w=150, right_w=46, color=TEAL)
                 if act else '<p class="nd">n/d</p>')
    left = col(mix_card + bottom)
    right = col(card("Then vs now", tbl, style="flex:0 0 196px") + card("Rotation per year (pp of portfolio)", rot_chart, style="flex:0 0 150px")
                + card(f"Net reallocation since start, {'C$MM' if small else 'C$bn'}", act_chart), w=430)
    if mh:
        title = f"{name}: " + (f"{PROSE.get(big[0], big[0].lower())} {'up' if float(big[3]) > 0 else 'down'} {abs(float(big[3])):.1f}pp since {p0}" if big else "mix history")
        if avg_rot is not None:
            title += f"; the book rotates ~{avg_rot:.1f}pp a year"
        if alda is not None:
            title += f"; ALDA {alda:.0f}% of GA"
        src = ("Project portfolio-reallocation series: " + clip(q.get("mix_source") or "OSFI 10Q/LF2 returns and annual reports", 80)
               + ". Rotation = half the sum of absolute class-share changes Q4 to Q4 (2023 includes the IFRS 17 basis change); "
                 "net reallocation = share change × portfolio, net of the IFRS 17 restatement")
    else:
        title = f"{name}: " + (f"holdings sit in {COVERED_BY[cid]}'s general account" if cid in COVERED_BY else "no published portfolio history")
        src = "No OSFI or annual-report series available"
    urls = collect_urls(com)
    notes = "\n".join(f"- {txt(c)} {c.get('source', '') if isinstance(c, dict) else ''}" for c in com)
    slide(title, left + right, src_line(src, urls, 2), tag=(n, name, "Holdings rotation"), notes=notes, urls=urls)


def page_newmoney(cid, n):
    """New money vs in-force: where the period's net new assets went compared with the in-force mix, next to which
    insurance liabilities grew (OSFI LF3 by line). Net flows only: maturities reinvested inside a class are not visible."""
    q = QC.get(cid, {})
    name = NAMES[cid]
    nm = q.get("new_money") or []
    nd = (f"Underwritten by {COVERED_BY[cid]}: see the {COVERED_BY[cid]} section." if cid in COVERED_BY else
          "No asset-mix history is published for this insurer.")
    read = []
    if nm:
        base = nm[0]
        series = [("In-force mix at " + base["start"], [num(base["inforce_mix"].get(k)) for k in CLASSES])]
        cols = [MUTED_BAR, BLUE, ORANGE]
        for w in nm:
            dt = sum(num(v) or 0 for v in w["delta_cad_mm"].values())
            if dt > 0:
                series.append((f"Net new money, {w['window'][0].lower() + w['window'][1:]} ({w['start']} to {w['end']})",
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
            read.append(f"{w['window']}: net new assets " + (f"C${dt / 1000:,.1f}bn" if dt >= 1000 else f"C${dt:,.0f}MM") + f" ({w['start']} to {w['end']}), "
                        f"{dt / (num(w['start_total_cad_mm']) or 1) * 100:.0f}% growth on the in-force book")
            if _g(w) < 0.05:
                read.append(f"Caution: net new money was only {_g(w) * 100:.0f}% of the book over the window, so the class shares are "
                            "dominated by a few trades and market moves")
            elif w is not nm[-1] and _g(nm[-1]) > 0:
                read.append(f"{nm[-1]['window']}: net new money was only {_g(nm[-1]) * 100:.0f}% of the book, so its class shares swing "
                            "widely; the headline uses the longer window")
            read.append(f"New money over-weights {PROSE[tilt[0][0]]} by {tilt[0][1]:+.0f}pp and under-weights "
                        f"{PROSE[tilt[-1][0]]} by {tilt[-1][1]:+.0f}pp versus the in-force mix")
        else:
            read.append(f"{w['window']}: the portfolio shrank by " + (f"C${-dt / 1000:,.1f}bn" if -dt >= 1000 else f"C${-dt:,.0f}MM")
                        + f" ({w['start']} to {w['end']}), so there is no net new money to allocate")
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
        unit = "C$MM" if big < 1000 else "C$bn"
        dlv = [(k, v if unit == "C$MM" else v / 1000) for k, v in dl]
        lia_chart = hbar(dlv, (lambda v: f"{v:+,.0f}") if unit == "C$MM" else (lambda v: f"{v:+,.1f}"), W=470, rowh=26, label_w=160,
                         right_w=50, color=TEAL, xlabel=f"Change in insurance contract liabilities, {unit}")
        rows = [[k, f"{num(v['prior']) / 1000:,.1f}", f"{num(v['current']) / 1000:,.1f}",
                 f"{((num(v['current']) or 0) / num(v['prior']) - 1) * 100:+.0f}%" if num(v["prior"]) and num(v["prior"]) > 0 else "n/m"]
                for k, v in lines.items()]
        tbl = table(["Line", f"FY{lg['fiscal_year'] - 1}", f"FY{lg['fiscal_year']}", "Change"], rows, cls="sm")
        grow = max(dl, key=lambda x: x[1])
        if grow[1] > 0:
            read.insert(1 if len(read) > 1 else 0, f"Fastest-growing liability line in FY{lg['fiscal_year']}: {grow[0].lower()} "
                                                   f"(+C${grow[1]:,.0f}MM), the new business the new money is backing")
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
    right = col(card(lia_h, lia_chart, style="flex:0 0 230px") + card("Insurance contract liabilities by line, C$bn (policies issued)", tbl))
    if nm and read and read[0].startswith(("Since", "Last")) and "over-weights" in " ".join(read):
        t = f"{name}: " + first_sentence(next(x for x in read if "over-weights" in x)).replace("New money over-weights", "new money over-weights")
    elif nm:
        t = f"{name}: no net new money to allocate in the latest window"
    else:
        t = f"{name}: new money vs in-force not measurable from public data"
    slide(clip(t, 150), left + right, "OSFI LF1/LF2 (assets) and LF3 P22010 (liabilities by line, all regions, policies issued); "
          "iA supplements and annual reports for others. New money = change in C$ held by class over the window",
          tag=(n, name, "New money vs in-force"), notes="\n".join(read))


def page_leverage(cid, n):
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
    pct = lambda v: f"{v / ga * 100:.1f}% of GA" if (v and ga) else ""
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
    iss_html = table(["Date", "Instrument", "C$MM", "Coupon", "Due", "Bookrunners"], iss_rows, cls="sm", left=2) if iss_rows else '<p class="nd">No 2023-2026 issuance found.</p>'
    dl = [(clip(re.split(r" \(", str(d.get("type")))[0], 21), (num(d.get("amount_cad_mm")) or 0) / 1000) for d in debt if num(d.get("amount_cad_mm"))]
    debt_unit = "C$bn"
    if dl and max(abs(v) for _, v in dl) < 1:
        dl, debt_unit = [(k, v * 1000) for k, v in dl], "C$MM"
    debt_chart = hbar(dl[:6], (lambda v: f"{v:,.0f}") if debt_unit == "C$MM" else (lambda v: f"{v:.1f}"), W=370, rowh=22, label_w=160,
                      right_w=40, color=BLUE) if dl else '<p class="nd">No debt disclosed (mutual / subsidiary funded by parent).</p>'
    dv = {}
    for o in obs:
        if o.get("level1") == "Derivatives":
            dv[o.get("level2")] = dv.get(o.get("level2"), 0) + abs(num(o["amount_cad_mm"]) or 0) / 1000
    dv_unit = "C$bn"
    if dv and max(dv.values()) < 1:
        dv, dv_unit = {k: v * 1000 for k, v in dv.items()}, "C$MM"
    dv_chart = hbar(sorted(dv.items(), key=lambda x: -x[1]), (lambda v: f"{v:,.0f}") if dv_unit == "C$MM" else (lambda v: f"{v:,.1f}"), W=370, rowh=22, label_w=110, right_w=50,
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
        bits.append(f"derivative notional {deriv / ga * 100:.0f}% of GA")
    if not bits:
        bits.append("little disclosed balance-sheet leverage")
    urls = collect_urls(lv)
    notes = json.dumps(lv, indent=1)[:6000]
    slide(t + ", ".join(bits), left + right, src_line("OSFI LF3 (repos P22030, derivatives P21110); financial statement notes", urls),
          tag=(n, name, "Leverage"), notes=notes, urls=urls)


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


def page_risk(cid, n):
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
        sens_html = hbar(s_items, f_, W=520, rowh=22, label_w=215, right_w=50, color=RED, xlabel="C$MM P&L impact (after-tax net income)")
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
        t += f"; -10% public equity costs C${abs(num(eq['ni_impact_cad_mm'])):,.0f}MM of net income"
    elif eq and num(eq.get("ni_impact_cad_mm")) is not None:
        t += "; a 10% equity fall barely touches net income (disclosed)"
    urls = collect_urls(rk)
    notes = json.dumps(rk, indent=1)[:6000]
    slide(t, body, src_line("OSFI LCQ; annual MD&A risk sections; project investment-risk benchmark", urls),
          tag=(n, name, "Risk constructs"), notes=notes, urls=urls)


# ---------------------------------------------------------------- opening pages
def opening():
    slide("Canadian life & health insurers: deep dives on the top 20", f'<p class="lead">Per insurer: key metrics and business mix, '
          f'leadership from CEO to CIO and every CIO direct report with tenure and pay, corporate structure from each insurer\'s own entity disclosure, holdings rotation, '
          f'leverage and funding, bank and sponsor partnerships, and risk constructs.</p><p class="cap" style="margin-top:18px">'
          f'Prepared {TODAY}. Data: OSFI regulatory returns, annual reports and quarterly filings already in the project dataset, '
          f'plus web research (company sites, proxy circulars, press releases). Figures carry their own as-of dates; gaps are flagged, '
          f'not estimated.</p>', "Insurance Firms project", cls="title")

    # universe table
    rows = []
    for i, cid in enumerate(ORDER, 1):
        q, r = QC.get(cid, {}), R(cid)
        cap, fw, _ = capital(cid)
        pm = ga_managers(cid)
        if cid == "canada_protection_plan":
            pm = ["Foresters Life (underwriter)"]
        own = short_label(q.get("ownership"), 44)
        pr = PRICES.get(cid)
        rows.append([f"{i}. {NAMES[cid]}", own, str(q.get("regulator")).split(";")[0].split(" (")[0],
                     bn(ga_mm(cid)) if ga_mm(cid) else "n/d", f"{cap:.0f}% {fw}" if cap else "n/d",
                     short_label(pm[0], 40) if pm else "not disclosed", f"{pr['ticker']} {pr['price']}" if pr and pr.get("price") else ""])
    slide("The universe: three groups hold most general-account assets, and only Manulife, Sun Life and iA are listed in their own right",
          col(table(["Insurer (section order)", "Ownership", "Regulator", "GA invested", "Capital ratio", "Main GA manager", "Listed (price)"],
                    rows, cls="sm uni", left={0, 1, 2, 5})), "OSFI LF2/LCQ; annual reports; web research; TSX/NYSE closes 2 Nov 2026 (EODData, Nasdaq)")

    # size and capital
    sz = [(NAMES[c], ga_mm(c) / 1000) for c in ORDER if ga_mm(c)]
    sz.sort(key=lambda x: -x[1])
    cp = [(NAMES[c], capital(c)[0]) for c in ORDER if capital(c)[0]]
    cp.sort(key=lambda x: -x[1])
    med_cap = sorted(v for _, v in cp)[len(cp) // 2] if cp else None
    body = col(card("General-account invested assets, C$bn", hbar(sz, lambda v: f"{v:,.0f}" if v >= 10 else f"{v:,.1f}", W=560, rowh=24,
                                                                  label_w=160, right_w=50, color=BLUE, focus="RBC Life")))
    body += col(card("Capital ratio, latest disclosed (LICAT / CARLI / solvency)", hbar(cp, lambda v: f"{v:.0f}%", W=560, rowh=24, label_w=160,
                                                                                       right_w=50, color=TEAL, median=med_cap, focus="RBC Life",
                                                                                       median_label=f"Median {med_cap:.0f}%" if med_cap else None)))
    big3 = sum(v for nme, v in sz[:3])
    slide(f"Manulife, Sun Life and Canada Life hold {big3 / sum(v for _, v in sz) * 100:.0f}% of the 20 insurers' general-account assets; "
          f"smaller mutuals run the highest capital ratios", body,
          "OSFI LF2 P21012 / annual reports (GA invested assets); OSFI LCQ and company disclosures (capital)")

    # who manages the money + CIO tenure
    rows = []
    for cid in ORDER:
        r = R(cid)
        cio = lead(cid)["cio"]
        ents = [short_label(e, 40) for e in ga_managers(cid)[:2]]
        if cid == "canada_protection_plan":
            ents = ["Foresters Life (underwriter)"]
        rows.append([NAMES[cid], clip(", ".join(ents) or "not disclosed", 70),
                     short_label(cio["name"], 30) if cio else "not named", f"{yrs(cio.get('seat_since')):.0f}y" if cio and yrs(cio.get("seat_since")) is not None else "",
                     f"{yrs(cio.get('firm_since')):.0f}y" if cio and yrs(cio.get("firm_since")) is not None else "",
                     money(cio.get("comp_total_cad") or cio.get("comp_total"), cio.get("comp_currency"), cio.get("comp_year")) or "n/d" if cio else ""])
    slide("Who runs the money: affiliated asset managers at the large groups, in-house teams or parents' managers elsewhere",
          col(table(["Insurer", "General-account manager(s)", "Most senior investment officer", "In seat", "At firm", "Latest pay"], rows, cls="sm uni", left={0, 1, 2})),
          "Web research: company leadership pages, proxy circulars, annual reports (see each insurer's leadership page)")

    # coverage heatmap
    secs = [("Metrics", lambda c: len(R(c).get("metrics") or [])), ("Mix", lambda c: len((R(c).get("business_mix") or {}).get("items") or [])),
            ("Org chart", lambda c: (lambda L: 3 if (L["ceo"] and L["cio"] and L["drs"]) else 1 if (L["ceo"] or L["cio"]) else 0)(lead(c))),
            ("Pay", lambda c: (lambda L: 3 if (pay(L["ceo"]) and pay(L["cio"])) else 1 if (pay(L["ceo"]) or pay(L["cio"])) else 0)(lead(c))),
            ("PM construct", lambda c: len((R(c).get("pm_structure") or {}).get("bullets") or [])),
            ("Holdings history", lambda c: len(QC.get(c, {}).get("mix_history") or [])),
            ("Leverage", lambda c: len((R(c).get("leverage") or {}).get("debt_outstanding") or []) + len(QC.get(c, {}).get("off_balance_sheet") or [])),
            ("Partnerships", lambda c: sum(len((R(c).get("partnerships") or {}).get(k) or []) for k in ("underwriters", "deals", "sponsorships"))),
            ("Risk", lambda c: len(QC.get(c, {}).get("sensitivities") or []) + sum(len((R(c).get("risk") or {}).get(k) or []) for k in ("appetite", "sensitivities")))]
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
    legend = ('<p class="cap">Dark blue ● well covered (3+ sourced points; org chart = CEO, CIO and at least one CIO direct report named; pay = CEO and CIO pay disclosed) · teal ● partial · – not publicly disclosed or not found. Mutuals, fraternals and bank-owned '
              'subsidiaries publish far less: no proxy circular, no investor presentation, often a single annual statement.</p>')
    slide("Disclosure depth falls off sharply outside the listed groups: read the smaller insurers' gaps as findings, not omissions",
          col(card("What the public record supports, by insurer and page", heat + legend)), "Count of sourced data points per page")


def closing():
    rows = [["GA invested assets", "OSFI LF2 P21012 col 40 (OSFI filers, latest quarter); annual reports for AMF/FCNB filers"],
            ["Capital ratios", "OSFI LCQ public extract D10100 (total ratio, main legal entity); company disclosures for others"],
            ["Holdings history", "OSFI 10Q (IFRS 4, 2020-22) and LF2 (IFRS 17, 2023-) harmonised into 6 classes; annual reports for AMF/FCNB"],
            ["Rotation", "Half the sum of absolute class-share changes, Q4 to Q4; 2023 includes the IFRS 17 change of basis"],
            ["Repos / derivatives", "OSFI LF3 P22030 row 280 (repos) and P21110 notionals, legal entity, latest fiscal year end"],
            ["Sensitivities", "Company MD&A / FS notes, after-tax NI as bps of invested assets (project investment-risk benchmark)"],
            ["Corporate structure", "Only the operating entities each insurer lists on its own website (entities / our-companies page)"],
            ["People and pay", "Tenure from LinkedIn experience sections where read, else company bios and appointment releases; "
                               "pay from proxy circular summary compensation tables; CIO direct reports from team pages and releases"],
            ["Partnerships", "Pricing press releases and prospectus supplements for dealers; company news for deals and sponsorships"]]
    slide("Method and sources", col(card("How each figure was built", table(["Item", "Source and method"], rows, cls="wrap roomy"))),
          "Insurance Firms project; code in analysis/insurer_deep_dive")


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
