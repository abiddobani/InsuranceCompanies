# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Render the ALM-basis peer portfolio reallocation report (HTML with inline SVG, then PDF).

    uv run analysis/portfolio_reallocation_alm/make_report.py [out.pdf]

Reads report_data.json (written by build.py), writes report.html next to this script and prints it
to A4 landscape with the preinstalled Playwright Chromium (node). Presentation follows the ALM repo's
standing rules: RBC Life first, dates not quarter labels, $MM / $BN, short names MFC / SLF / CLF / BLU,
estimates marked, sources on every page.
"""
import datetime as dt
import html
import json
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = json.loads((HERE / "report_data.json").read_text())
M = D["meta"]
L3, L2, L2O, NAMES = M["l3"], M["l2"], M["l2_order"], M["names"]
S = D["series"]
FOCUS = "RBC"
ORDER = ["RBC", "MFC", "SLF", "CLF", "BMO", "BLU", "EMP", "IVA", "EQL", "COP", "IOF", "WAW"]
QPEERS = [p for p in ORDER if p not in ("RBC", "CLF")]  # quarterly peers used for medians
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "peer-portfolio-reallocations-alm.pdf"

# validated categorical palette (dataviz reference palette, light mode, fixed order)
C = {"Public Fixed Income": "#257de0", "Private Fixed Income": "#f47230", "Public Equity": "#00b894",
     "Real Estate Equity": "#f2a600", "Others (unclassified)": "#ee7fac", "Cash & Cash Equivalent": "#008a17"}
ALT_C = {"Illiquid Term Loan": "#257de0", "Commercial Mortgages": "#f47230", "Real Estate Equity": "#00b894", "Others": "#f2a600"}
ALT_NAME = {"Illiquid Term Loan": "Private placements", "Commercial Mortgages": "Mortgages",
            "Real Estate Equity": "Real estate", "Others": "Others (est)"}
L3_NAME = {"Cash Equivalent": "Short-term investments", "Government Bonds": "Government bonds", "Corporate Bonds": "Corporate bonds (public)",
           "Illiquid Term Loan": "Private placements (illiquid term loans)", "Commercial Mortgages": "Commercial mortgages",
           "Common Shares": "Common shares", "Preferred Shares": "Preferred shares", "Real Estate Equity": "Real estate equity",
           "Others": "Others (unclassified)"}
L3_SHORT = {"Cash Equivalent": "Short-term", "Government Bonds": "Gov't bonds", "Corporate Bonds": "Corp. bonds",
            "Illiquid Term Loan": "Private plac.", "Commercial Mortgages": "Mortgages", "Common Shares": "Common",
            "Preferred Shares": "Preferred", "Real Estate Equity": "Real estate", "Others": "Others"}
INK, INK2, GRID, AXIS, BLUE, GREY = "#191919", "#666666", "#e7e7e7", "#c2c2c2", "#257de0", "#b9bec7"
RELIAB = {"RBC": "High", "BMO": "High", "IVA": "High", "BLU": "High", "IOF": "High", "CLF": "High (annual)",
          "EMP": "Medium", "MFC": "Medium", "SLF": "Medium", "WAW": "Medium", "COP": "Medium", "EQL": "Low"}


def e(s):
    return html.escape(str(s))


def dfmt(s, short=False):
    d = dt.date.fromisoformat(s)
    return d.strftime("%b %-d, %Y") if not short else d.strftime("%b %Y")


def dnum(s):
    d = dt.date.fromisoformat(s)
    return d.year + (d.timetuple().tm_yday - 1) / 365.25


def money(k, digits=1):
    """C$ thousands -> $MM / $BN."""
    mm = k / 1e3
    if abs(mm) >= 1000:
        return f"${mm / 1e3:,.{digits}f}BN"
    return f"${mm:,.0f}MM"


def sgn(x, d=1):
    if round(x, d) == 0:
        return f"{0:.{d}f}"
    return f"{x:+,.{d}f}".replace("-", "−")


def mag(x, d=1):
    return f"{abs(x):,.{d}f}"


def l2sh(sh):
    o = {k: 0.0 for k in L2O}
    for k in L3:
        o[L2[k]] += sh[k]
    return o


def alts(r, keys=None):
    return 100 * sum(r["shares"][k] for k in (keys or M["alts"]))


def rec(sid, date):
    return next(r for r in S[sid] if r["date"] == date)


# ------------------------------------------------------------------ chart helpers (inline SVG)
def svg(w, h, body):
    return f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" font-family="Inter, Helvetica Neue, Arial, sans-serif">{body}</svg>'


def txt(x, y, s, size=10, fill=INK2, anchor="start", weight=400, extra=""):
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" font-weight="{weight}" {extra}>{e(s)}</text>'


def legend(items, line=False):
    out = []
    for name, col in items:
        key = (f'<span class="lk" style="background:{col}"></span>' if not line else
               f'<span class="ll" style="border-color:{col}"></span>')
        out.append(f'<span class="li">{key}{e(name)}</span>')
    return '<div class="legend">' + "".join(out) + "</div>"


def stacked_columns(recs, w=560, h=300, label_last=True, tick_every=1, small=False):
    """100% stacked columns by level 2, one column per date, 2px surface gaps."""
    ml, mr, mt, mb = (30, 150 if label_last else 8, 8, 40) if not small else (30, 6, 6, 22)
    pw, ph = w - ml - mr, h - mt - mb
    n = len(recs)
    band = pw / n
    bw = min(24 if not small else 12, band - 4)
    b = []
    ends = []
    for t in (0, 25, 50, 75, 100):
        y = mt + ph * (1 - t / 100)
        b.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        if not small or t in (0, 50, 100):
            b.append(txt(ml - 5, y + 3, f"{t}%", 9 if not small else 8, INK2, "end"))
    for i, r in enumerate(recs):
        x = ml + band * i + (band - bw) / 2
        sh = l2sh(r["shares"])
        acc = 0.0
        for k in L2O:
            v = sh[k] * 100
            if v <= 0.05:
                continue
            y1 = mt + ph * (1 - (acc + v) / 100)
            hh = max(ph * v / 100 - 2, 0.6)
            b.append(f'<rect x="{x:.1f}" y="{y1 + 1:.1f}" width="{bw:.1f}" height="{hh:.1f}" fill="{C[k]}" rx="1"/>')
            if label_last and i == n - 1 and v >= 1.5:
                ends.append([y1 + ph * v / 200 + 3.5, f"{k.replace(' (unclassified)', '')} {v:.1f}%", x + bw + 8])
            acc += v
        if i % tick_every == 0 or i == n - 1:
            d = dt.date.fromisoformat(r["date"])
            lab = d.strftime("%b") if not small else d.strftime("%y")
            if small:
                lab = "'" + lab if d.month in (10, 12) else ""
            b.append(txt(x + bw / 2, mt + ph + 13, lab, 9 if not small else 8, INK2, "middle"))
            if not small:
                b.append(txt(x + bw / 2, mt + ph + 24, d.strftime("%Y"), 8.5, INK2, "middle"))
                if r.get("blocks_est"):
                    b.append(txt(x + bw / 2, mt + ph + 35, "est", 8, INK2, "middle"))
    ends.sort(key=lambda z: -z[0])
    for j in range(1, len(ends)):
        ends[j][0] = min(ends[j][0], ends[j - 1][0] - 13)
    for y, s_, x_ in ends:
        b.append(txt(x_, y, s_, 10, INK))
    return svg(w, h, "".join(b))


def hbar_pair(rows, w=470, h=None, unit="$MM", rng=None, col=BLUE, labw=190, highlight=None):
    """Horizontal diverging bars from a zero line. rows: (label, value)."""
    rh = 24
    h = h or (len(rows) * rh + 30)
    ml, mr, mt = labw, 66, 6
    pw = w - ml - mr
    lo, hi = rng or (min(min(v for _, v in rows), 0), max(max(v for _, v in rows), 0))
    scale = pw / ((hi - lo) or 1)
    zero = ml + -lo * scale
    b = [f'<line x1="{zero:.1f}" x2="{zero:.1f}" y1="{mt}" y2="{mt + len(rows) * rh}" stroke="{AXIS}" stroke-width="1"/>']
    for i, (lab, v) in enumerate(rows):
        y = mt + i * rh + 5
        bw_ = abs(v) * scale
        x = zero if v >= 0 else zero - bw_
        c = col if (highlight is None or lab in highlight) else GREY
        b.append(f'<rect x="{x:.1f}" y="{y}" width="{max(bw_, 0.8):.1f}" height="14" fill="{c}" rx="2"/>')
        b.append(txt(ml - 8, y + 11, lab, 10.5, INK, "end"))
        s = (("+" if v >= 0 else "−") + "$" + mag(v, 0) + "MM") if unit == "$MM" else sgn(v, 1)
        b.append(txt(zero + (bw_ if v >= 0 else 0) + 5, y + 11, s, 10, INK))
    return svg(w, h, "".join(b))


def div_color(v, mx):
    """Diverging blue (up) / red (down) with a neutral gray midpoint."""
    t = max(-1.0, min(1.0, v / mx))
    base = (239, 239, 239)
    pole = (37, 125, 224) if t > 0 else (220, 60, 61)
    a = abs(t) ** 0.8
    rgb = tuple(round(base[i] + (pole[i] - base[i]) * a) for i in range(3))
    return "#%02x%02x%02x" % rgb, ("#ffffff" if a > 0.62 else INK)


def heat_table(cols, rows, mx, first_cols, last_cols=(), note_col=None):
    """rows: dict(label, cells{col: value}, pre[list], post[list], focus)."""
    th = "".join(f"<th class='l'>{e(c)}</th>" for c in first_cols) + "".join(f"<th>{e(c)}</th>" for c in cols) + "".join(f"<th>{e(c)}</th>" for c in last_cols)
    out = [f"<table class='heat'><thead><tr>{th}</tr></thead><tbody>"]
    for r in rows:
        tds = "".join(f"<td class='l'>{c}</td>" for c in r["pre"])
        for c in cols:
            v = r["cells"].get(c)
            if v is None:
                tds += "<td class='c na'>n/a</td>"
            else:
                bg, fg = div_color(v, mx)
                tds += f"<td class='c'><span class='cell' style='background:{bg};color:{fg}'>{sgn(v)}</span></td>"
        tds += "".join(f"<td class='c'>{c}</td>" for c in r.get("post", []))
        out.append(f"<tr class='{'focus' if r.get('focus') else ''}'>{tds}</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def small_multiple_lines(panels, w=330, h=170):
    """panels: list of (title, rbc[(x,y)], med[(x,y)], lo[(x,y)], hi[(x,y)])."""
    out = []
    for title, rbc, med, lo, hi in panels:
        ml, mr, mt, mb = 30, 46, 8, 20
        pw, ph = w - ml - mr, h - mt - mb
        xs = [p[0] for p in rbc + med]
        x0, x1 = min(xs), max(xs)
        ys = [p[1] for p in rbc + lo + hi + med]
        y1 = max(ys) * 1.12 or 1
        step = next(s for s in (0.5, 1, 2, 5, 10, 20, 25, 50) if y1 / s <= 4.5)
        X = lambda x: ml + pw * (x - x0) / (x1 - x0)
        Y = lambda y: mt + ph * (1 - y / y1)
        b = []
        t = 0
        while t <= y1:
            b.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="{GRID}" stroke-width="1"/>')
            b.append(txt(ml - 5, Y(t) + 3, f"{t:g}%", 8.5, INK2, "end"))
            t += step
        for yr in (2024, 2025, 2026):
            if x0 <= yr <= x1:
                b.append(txt(X(yr), mt + ph + 13, str(yr), 8.5, INK2, "middle"))
                b.append(f'<line x1="{X(yr):.1f}" x2="{X(yr):.1f}" y1="{mt + ph}" y2="{mt + ph + 3}" stroke="{AXIS}"/>')
        band = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in hi) + " " + " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in reversed(lo))
        b.append(f'<polygon points="{band}" fill="#8a9099" opacity="0.14"/>')
        b.append('<polyline points="' + " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in med) + f'" fill="none" stroke="#7b818a" stroke-width="1.5" stroke-linejoin="round"/>')
        b.append('<polyline points="' + " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in rbc) + f'" fill="none" stroke="{BLUE}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        ex, ey = rbc[-1]
        b.append(f'<circle cx="{X(ex):.1f}" cy="{Y(ey):.1f}" r="4" fill="{BLUE}" stroke="#fff" stroke-width="2"/>')
        mx_, my_ = med[-1]
        ly_r, ly_m = Y(ey) + 3.5, Y(my_) + 3.5
        if abs(ly_r - ly_m) < 11:
            ly_r, ly_m = (ly_r - 6, ly_m + 6) if ey >= my_ else (ly_r + 6, ly_m - 6)
        b.append(txt(X(ex) + 7, ly_r, f"{ey:.1f}%", 10, INK, weight=600))
        b.append(txt(X(mx_) + 7, ly_m, f"{my_:.1f}%", 9.5, INK2))
        out.append(f"<div class='sm'><div class='smt'>{e(title)}</div>{svg(w, h, ''.join(b))}</div>")
    return "<div class='smgrid'>" + "".join(out) + "</div>"


def dumbbell(rows, w=500, labw=120, unit="%"):
    """rows: (label, first, last, focus). Hollow dot = first date, filled = latest."""
    rh = 24
    h = len(rows) * rh + 34
    ml, mr, mt = labw, 62, 6
    pw = w - ml - mr
    mx = max(max(a, b) for _, a, b, _ in rows) * 1.05
    step = 10 if mx > 30 else 5
    X = lambda v: ml + pw * v / mx
    b = []
    t = 0
    while t <= mx:
        b.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{mt}" y2="{mt + len(rows) * rh}" stroke="{GRID}"/>')
        b.append(txt(X(t), mt + len(rows) * rh + 13, f"{t}%", 9, INK2, "middle"))
        t += step
    for i, (lab, a, z, focus) in enumerate(rows):
        y = mt + i * rh + 12
        col = BLUE if focus else "#7b818a"
        b.append(txt(ml - 10, y + 3.5, lab, 10.5, INK, "end", 700 if focus else 400))
        b.append(f'<line x1="{X(a):.1f}" x2="{X(z):.1f}" y1="{y}" y2="{y}" stroke="{col}" stroke-width="2"/>')
        b.append(f'<circle cx="{X(a):.1f}" cy="{y}" r="4" fill="#fff" stroke="{col}" stroke-width="2"/>')
        b.append(f'<circle cx="{X(z):.1f}" cy="{y}" r="4.5" fill="{col}" stroke="#fff" stroke-width="1.5"/>')
        b.append(txt(X(max(a, z)) + 9, y + 3.5, f"{z:.1f}% ({sgn(z - a)})", 10, INK, weight=600 if focus else 400))
    return svg(w, h, "".join(b))


def stacked_hbars(rows, keys, colors, w=470, labw=120):
    rh = 24
    h = len(rows) * rh + 34
    ml, mr, mt = labw, 46, 6
    pw = w - ml - mr
    mx = max(sum(v.values()) for _, v, _ in rows) * 1.05
    step = 10 if mx > 30 else 5
    X = lambda v: ml + pw * v / mx
    b = []
    t = 0
    while t <= mx:
        b.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{mt}" y2="{mt + len(rows) * rh}" stroke="{GRID}"/>')
        b.append(txt(X(t), mt + len(rows) * rh + 13, f"{t}%", 9, INK2, "middle"))
        t += step
    for i, (lab, vals, focus) in enumerate(rows):
        y = mt + i * rh + 5
        acc = 0.0
        b.append(txt(ml - 10, y + 11, lab, 10.5, INK, "end", 700 if focus else 400))
        for k in keys:
            v = vals[k]
            if v > 0.05:
                b.append(f'<rect x="{X(acc) + 1:.1f}" y="{y}" width="{max(pw * v / mx - 2, 0.6):.1f}" height="14" fill="{colors[k]}" rx="1"/>')
            acc += v
        b.append(txt(X(acc) + 6, y + 11, f"{acc:.1f}%", 10, INK, weight=600 if focus else 400))
    return svg(w, h, "".join(b))


def lines_money(series, w=520, h=250):
    """series: list of (name, color, [(x, $BN)]) with end labels."""
    ml, mr, mt, mb = 28, 52, 8, 22
    pw, ph = w - ml - mr, h - mt - mb
    xs = [p[0] for _, _, pts in series for p in pts]
    x0, x1 = min(xs), max(xs)
    y1 = max(p[1] for _, _, pts in series for p in pts) * 1.1
    step = next(s for s in (0.5, 1, 2, 5) if y1 / s <= 6)
    X = lambda x: ml + pw * (x - x0) / (x1 - x0)
    Y = lambda y: mt + ph * (1 - y / y1)
    b = []
    t = 0
    while t <= y1:
        b.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="{GRID}"/>')
        b.append(txt(ml - 5, Y(t) + 3, f"{t:g}", 9, INK2, "end"))
        t += step
    for yr in (2024, 2025, 2026):
        b.append(txt(X(yr), mt + ph + 14, f"Jan {yr}", 9, INK2, "middle"))
        b.append(f'<line x1="{X(yr):.1f}" x2="{X(yr):.1f}" y1="{mt + ph}" y2="{mt + ph + 3}" stroke="{AXIS}"/>')
    ends = sorted(((Y(pts[-1][1]), name) for name, _, pts in series))
    pos = {}
    last = -99
    for y, name in ends:
        y = max(y, last + 12)
        pos[name] = y
        last = y
    for name, col, pts in series:
        b.append('<polyline points="' + " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in pts) + f'" fill="none" stroke="{col}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        ex, ey = pts[-1]
        b.append(f'<circle cx="{X(ex):.1f}" cy="{Y(ey):.1f}" r="4" fill="{col}" stroke="#fff" stroke-width="2"/>')
        b.append(txt(X(ex) + 9, pos[name] + 3.5, f"${ey:.1f}BN", 10, INK))
    return svg(w, h, "".join(b))


# ------------------------------------------------------------------ numbers
R = S["RBC"]
r0, rN = R[0], R[-1]
rFY24, rFY25 = rec("RBC", "2024-10-31"), rec("RBC", "2025-10-31")
fundR = {f["date"]: f for f in D["fund"]["RBC"] if f["genacct_k"]}
iclR = D["icl"]["RBC"]
AMT = lambda r, k: r["shares"][k] * r["ga_k"]
prov = lambda r: r["gov_detail"]["Provincial"]


def peer_stat(fn, date_idx):
    vals = []
    for p in QPEERS:
        rs = S[p]
        r = rs[date_idx] if date_idx < 0 else rs[min(date_idx, len(rs) - 1)]
        vals.append(fn(r))
    return statistics.median(vals)


pages = []


def page(title, kicker, body, foot):
    n = len(pages) + 1
    pages.append(f"""<section class="page"><header><div class="kick">{e(kicker)}</div><h1>{title}</h1></header>
<div class="body">{body}</div><footer><div class="src">{foot}</div><div class="pn">Peer portfolio reallocations, ALM basis &nbsp;|&nbsp; {n}</div></footer></section>""")


SRC = ("Sources: OSFI LF1 / LF2 / LF3 / LCQ returns (open.canada.ca) through the cdn-life-insurer-alm study views "
       f"(commit {M['alm_commit']}); company filings where stated. ")
BASIS = ("Canadian business; General Account excl. par / seg fund and UL policyholder funds; share of invested assets at balance-sheet value. "
         "est = estimate.")

# ---- page 1: headline
d_alt = alts(rN) - alts(r0)
l2a, l2z = l2sh(r0["shares"]), l2sh(rN["shares"])
med_alt_z = peer_stat(alts, -1)
big3 = [alts(S[p][-1]) for p in ("MFC", "SLF", "CLF")]
tiles = [
    ("Non-par General Account", f"{money(r0['ga_k'])} → {money(rN['ga_k'])}", f"{dfmt(r0['date'])} to {dfmt(rN['date'])} (latest est)"),
    ("Government bonds", f"{100 * r0['shares']['Government Bonds']:.1f}% → {100 * rFY25['shares']['Government Bonds']:.1f}% → {100 * rN['shares']['Government Bonds']:.1f}%",
     f"start, {dfmt(rFY25['date'])} peak, latest"),
    ("Private placements", f"{100 * r0['shares']['Illiquid Term Loan']:.1f}% → {100 * rN['shares']['Illiquid Term Loan']:.1f}%",
     f"{money(AMT(r0, 'Illiquid Term Loan'))} to {money(AMT(rN, 'Illiquid Term Loan'))}"),
    ("Alternatives incl. Others", f"{alts(r0):.1f}% → {alts(rN):.1f}%", f"quarterly peer median {med_alt_z:.1f}%; Big 3 {min(big3):.0f}–{max(big3):.0f}% (est)"),
    ("Repo funding", f"{money(fundR['2024-10-31']['repos_k'])} → {money(fundR['2025-10-31']['repos_k'])}",
     f"Oct 31, 2024 to Oct 31, 2025; {fundR['2025-10-31']['financing_pct']:.0f}% of the General Account"),
]
tile_html = "".join(f"<div class='tile'><div class='tl'>{e(a)}</div><div class='tv'>{e(b)}</div><div class='ts'>{e(c)}</div></div>" for a, b, c in tiles)
ga_grow = fundR["2025-10-31"]["genacct_k"] - fundR["2024-10-31"]["genacct_k"]
repo_grow = fundR["2025-10-31"]["repos_k"] - fundR["2024-10-31"]["repos_k"]
prt_grow = iclR["2025"]["lines"]["Group annuity"] - iclR["2024"]["lines"]["Group annuity"]
gov_grow = AMT(rFY25, "Government Bonds") - AMT(rFY24, "Government Bonds")
_l25 = iclR["2025"]["lines"]
long_sh = 100 * (_l25["Group annuity"] + _l25["Individual insurance"]) / sum(_l25.values())
body = f"""
<p class="lede big">RBC Life grew its non-par General Account by {money(rN['ga_k'] - r0['ga_k'])} in two and a half years and moved it in two steps:
first out of cash and corporate bonds into repo-funded provincial bonds, then, from November 2025, back out of government bonds into
corporate bonds and private placements. Its alternatives share rose {sgn(d_alt)} pts to {alts(rN):.1f}%, still about half of the Big 3.</p>
<div class="tiles">{tile_html}</div>
<div class="cols2 p1">
<div><h3>What RBC Life did, against peers</h3>
<ul>
<li><b>Fiscal 2024 and 2025: growth went into government bonds.</b> Short-term investments ran down from {100 * r0['shares']['Cash Equivalent']:.1f}% to {100 * rFY25['shares']['Cash Equivalent']:.1f}%
and public corporates from {100 * r0['shares']['Corporate Bonds']:.1f}% to {100 * rFY25['shares']['Corporate Bonds']:.1f}%; provincial bonds grew from {money(prov(r0))} to {money(prov(rFY25))}.
In fiscal 2025 the General Account grew {money(ga_grow)}; repos supplied {money(repo_grow)} of it and PRT (group annuity) liabilities {money(prt_grow)}.</li>
<li><b>Fiscal 2026 to date: rotation into credit.</b> Government bonds fell {mag(100 * (rN['shares']['Government Bonds'] - rFY25['shares']['Government Bonds']))} pts in nine months;
corporates rose {sgn(100 * (rN['shares']['Corporate Bonds'] - rFY25['shares']['Corporate Bonds']))} pts and private placements {sgn(100 * (rN['shares']['Illiquid Term Loan'] - rFY25['shares']['Illiquid Term Loan']))} pts to {money(AMT(rN, 'Illiquid Term Loan'))} (est).</li>
<li><b>Most peers moved the same way.</b> Private fixed income rose at {sum(1 for p in ORDER if l2sh(S[p][-1]['shares'])['Private Fixed Income'] - l2sh(S[p][0]['shares'])['Private Fixed Income'] > 0.002)} of 12 OSFI peers;
RBC Life's {sgn(100 * (l2z['Private Fixed Income'] - l2a['Private Fixed Income']))} pts compares with BLU {sgn(100 * (l2sh(S['BLU'][-1]['shares'])['Private Fixed Income'] - l2sh(S['BLU'][0]['shares'])['Private Fixed Income']))}, CLF {sgn(100 * (l2sh(S['CLF'][-1]['shares'])['Private Fixed Income'] - l2sh(S['CLF'][0]['shares'])['Private Fixed Income']))} and SLF {sgn(100 * (l2sh(S['SLF'][-1]['shares'])['Private Fixed Income'] - l2sh(S['SLF'][0]['shares'])['Private Fixed Income']))} (est).</li>
<li><b>Why it matters.</b> RBC Life's liabilities are long and illiquid (PRT and individual insurance are {long_sh:.0f}% of its core Canadian liabilities), so they can carry more private assets than the {alts(rN):.0f}% held.
The binding limits are funding and liquidity, not LICAT: the ratio stayed between {min(r['licat'] for r in R):.0f}% and {max(r['licat'] for r in R):.0f}% throughout while repos grew to {fundR['2025-10-31']['financing_pct']:.0f}% of the General Account.</li>
<li><b>What can be done.</b> Continue the fiscal 2026 rotation from repo-funded provincials into private placements and mortgages, with a stated repo and encumbrance limit. Sizing it needs the ALM study's modelling stage (private credit capacity within LICAT 125%).</li>
</ul></div>
<div><h3>What changed from the October report</h3>
<table class="plain">
<tr><th></th><th>Earlier report (Oct 29, 2026)</th><th>This report (ALM framework)</th></tr>
<tr><td>Scope</td><td>Legal entity, incl. par, UL funds and foreign operations</td><td>Canadian business; General Account excl. par / seg fund; UL policyholder funds out</td></tr>
<tr><td>Classes</td><td>6 harmonised classes</td><td>ALM taxonomy level 1 / 2 / 3; alternatives as defined Nov 15, 2026</td></tr>
<tr><td>Window</td><td>Q1 2020 to Q2 2026, bridging IFRS 4 to IFRS 17</td><td>IFRS 17 only: Dec 31, 2023 (RBC Life, BMO Life Jan 31, 2024) to latest</td></tr>
<tr><td>Market effect</td><td>Modelled market-drift split</td><td>Not modelled (ALM rule: modelling goes to next steps); directional read only</td></tr>
<tr><td>Context</td><td>Asset side only</td><td>Liability mix by product line, repo funding, LICAT and buffer beside the asset moves</td></tr>
<tr><td>Peers</td><td>20 insurers on one basis</td><td>12 OSFI peers on the full method; iA, Beneva and five small insurers on a coarser, labelled basis; Desjardins n/a</td></tr>
</table>
<p class="note">RBC Life equities, 12.5% in the earlier report, are {100 * l2z['Public Equity']:.1f}% here: {money(rN['ul_k'])} of its common shares are UL policyholder funds, which the ALM basis removes.</p>
</div></div>"""
page(f"RBC Life shifted from repo-funded government bonds toward private credit; alternatives are {alts(rN):.0f}% against {min(big3):.0f}–{max(big3):.0f}% at the Big 3",
     "Peer portfolio reallocations, ALM basis", body,
     SRC + BASIS + " 2026 block sizes are held at their fiscal 2025 year-end share of the invested pool (est). PRT and individual insurance share: OSFI LF3 product lines net of reinsurance, Oct 31, 2025.")

# ---- page 2: RBC mix over time
rows_l3 = []
for k in L3:
    a, m, z = 100 * r0["shares"][k], 100 * rFY25["shares"][k], 100 * rN["shares"][k]
    if max(a, m, z) < 0.05:
        continue
    bg, fg = div_color(z - a, 6)
    rows_l3.append(f"<tr><td class='l'><span class='sw' style='background:{C[L2[k]]}'></span>{e(L3_NAME[k].replace(' (illiquid term loans)', '').replace(' (public)', ''))}</td><td>{a:.1f}%</td><td>{m:.1f}%</td><td>{z:.1f}%</td>"
                   f"<td><span class='cell' style='background:{bg};color:{fg}'>{sgn(z - a)}</span></td><td>{AMT(r0, k) / 1e3:,.0f}</td><td>{AMT(rN, k) / 1e3:,.0f}</td><td>{sgn((AMT(rN, k) - AMT(r0, k)) / 1e3, 0)}</td></tr>")
rows_l3.append(f"<tr class='tot'><td class='l'>Non-par / seg General Account</td><td>100%</td><td>100%</td><td>100%</td><td></td><td>{r0['ga_k'] / 1e3:,.0f}</td><td>{rN['ga_k'] / 1e3:,.0f}</td><td>{sgn((rN['ga_k'] - r0['ga_k']) / 1e3, 0)}</td></tr>")
body = f"""<div class="cols2 wide-left">
<div class="card"><div class="ct">RBC Life: non-par / seg General Account by level 2, each filed date</div>
<div class="cs">Share of invested assets. Fiscal quarters end Jan 31, Apr 30, Jul 31 and Oct 31. Columns marked est use the Oct 31, 2025 block sizes.</div>
{legend([(k.replace(' (unclassified)', ''), C[k]) for k in L2O])}
{stacked_columns(R, w=456, h=380)}</div>
<div class="card"><div class="ct">Level 3: start, fiscal 2025 year-end and latest</div>
<div class="cs">Share (%), change in percentage points, and $MM. Private placements = illiquid term loans in the ALM taxonomy; corporate bonds are public issues.</div>
<table class="num"><thead><tr><th class='l'>Level 3</th><th>{dfmt(r0['date'], True)}</th><th>{dfmt(rFY25['date'], True)}</th><th>{dfmt(rN['date'], True)}</th><th>Change, pts</th><th>$MM start</th><th>$MM latest</th><th>$MM change</th></tr></thead>
<tbody>{''.join(rows_l3)}</tbody></table>
<p class="note">Government bonds are {money(rN['gov_detail']['Provincial'])} provincial, {money(rN['gov_detail']['Federal'])} federal and {money(rN['gov_detail']['Municipal and public authority'])} municipal at the entity level.
RBC Life holds no directly owned real estate; any real estate funds sit in Others or common shares (ALM limitation L21).
UL policyholder funds of {money(rN['ul_k'])} and the par account of {money(rFY25['par_k'])} (Oct 31, 2025) are outside these figures.</p></div></div>"""
page(f"RBC Life: cash and corporates fell through fiscal 2025 as government bonds reached {100 * rFY25['shares']['Government Bonds']:.0f}%; fiscal 2026 has reversed half of that into credit",
     "RBC Life, mix over time", body, SRC + BASIS + " $MM = share × block size from the ALM study views; the Jul 31, 2026 block size is an estimate.")

# ---- page 3: RBC what funded the change (fiscal 2025) and $ lines
asset_rows = [(L3_NAME[k].replace(" (illiquid term loans)", "").replace(" (public)", ""), (AMT(rFY25, k) - AMT(rFY24, k)) / 1e3) for k in L3
              if max(AMT(rFY25, k), AMT(rFY24, k)) > 5e3]
f24, f25 = fundR["2024-10-31"], fundR["2025-10-31"]
slf_f = next(f for f in D["fund"]["SLF"] if f["date"] == "2025-12-31")
liab_rows = [("Repos (financing)", (f25["repos_k"] - f24["repos_k"]) / 1e3)]
for ln, nm in (("Group annuity", "Group annuity (PRT)"), ("Individual insurance", "Individual insurance"),
               ("Group insurance", "Group insurance"), ("Individual annuity", "Individual annuity")):
    liab_rows.append((nm, (iclR["2025"]["lines"][ln] - iclR["2024"]["lines"][ln]) / 1e3))
liab_rows += [("ABL CSM", (f25["csm_abl_k"] - f24["csm_abl_k"]) / 1e3), ("Surplus", (f25["surplus_k"] - f24["surplus_k"]) / 1e3)]
_all = [v for _, v in asset_rows + liab_rows]
rng = (min(_all + [0]), max(_all))
ser = [("Government bonds", "#257de0", [(dnum(r["date"]), AMT(r, "Government Bonds") / 1e6) for r in R]),
       ("Corporate bonds", "#f47230", [(dnum(r["date"]), AMT(r, "Corporate Bonds") / 1e6) for r in R]),
       ("Private placements", "#00b894", [(dnum(r["date"]), AMT(r, "Illiquid Term Loan") / 1e6) for r in R]),
       ("Mortgages", "#f2a600", [(dnum(r["date"]), AMT(r, "Commercial Mortgages") / 1e6) for r in R])]
body = f"""<div class="cols3">
<div class="card"><div class="ct">Assets: change in fiscal 2025, $MM</div><div class="cs">Non-par / seg General Account by level 3, Oct 31, 2024 to Oct 31, 2025.</div>
{hbar_pair(asset_rows, w=316, rng=rng, labw=130)}</div>
<div class="card"><div class="ct">Liabilities and funding: change in fiscal 2025, $MM</div><div class="cs">Same dates and scale. Product lines are liabilities net of reinsurance, excluding par and seg funds.</div>
{hbar_pair(liab_rows, w=316, rng=rng, labw=130, col="#7b818a", highlight=None)}</div>
<div class="card"><div class="ct">RBC Life: the four largest classes, $BN</div><div class="cs">Each filed date; the last three points use estimated block sizes.</div>
{legend([(n, c) for n, c, _ in ser], line=True)}
{lines_money(ser, w=316, h=250)}</div></div>
<div class="cols2"><div><ul>
<li>Fiscal 2025 growth of {money(ga_grow)} was funded mainly by <b>repos ({money(repo_grow)})</b> and <b>PRT ({money(prt_grow)})</b>. Government bonds rose {money(gov_grow)},
so most of the bond growth was financed, not backed by new insurance liabilities. Repos reached {f25['financing_pct']:.1f}% of the General Account ({f24['financing_pct']:.1f}% a year earlier); among the 12 OSFI peers only SLF also reports repos ({money(slf_f['repos_k'])} at Dec 31, 2025).</li>
<li>ABL CSM fell {money(f24['csm_abl_k'] - f25['csm_abl_k'])} to {money(f25['csm_abl_k'])} and the buffer from {f24['buffer_pct']:.1f}% to {f25['buffer_pct']:.1f}%, while LICAT eased from {f24['capital_ratio_pct']:.0f}% to {f25['capital_ratio_pct']:.0f}%, above the 125% floor in the ALM study's question. The reallocation was not capital-constrained.</li>
</ul></div><div><ul>
<li>Since Oct 31, 2025 government bonds are down {money(AMT(rFY25, 'Government Bonds') - AMT(rN, 'Government Bonds'))} and corporate bonds, private placements and mortgages are up
{money(AMT(rN, 'Corporate Bonds') + AMT(rN, 'Illiquid Term Loan') + AMT(rN, 'Commercial Mortgages') - AMT(rFY25, 'Corporate Bonds') - AMT(rFY25, 'Illiquid Term Loan') - AMT(rFY25, 'Commercial Mortgages'))} (est).
Repo balances for 2026 are filed only at the October year-end, so whether the repo book also shrank is not yet visible.</li>
<li>Directional read on market effects: {r0['acct']['FVTPL']:.0f}% of RBC Life's invested assets are carried at fair value through profit or loss and {r0['acct']['FVOCI']:.0f}% through OCI, so share changes include price moves; a split between trading and repricing needs modelling and is left to next steps.</li>
</ul></div></div>"""
page("In fiscal 2025 RBC Life's bond growth was financed: repos and PRT funded it, and government bonds absorbed it",
     "RBC Life, assets against liabilities and funding", body,
     SRC + BASIS + " Repos: OSFI LF3 P2203028001 (fiscal year-ends). Product lines: OSFI LF3 Canada column, net of reinsurance (ALM icl_by_line). CSM, Surplus, buffer: ALM study views.")

# ---- page 4: peer heatmap level 2
hrows = []
for p in ORDER:
    a, z = S[p][0], S[p][-1]
    da, dz = l2sh(a["shares"]), l2sh(z["shares"])
    par = next((f["par_pct"] for f in reversed(D["fund"].get(p, [])) if f["par_pct"] is not None), 0) or 0
    basis = {"MFC": "Entity (global) mix", "SLF": "Entity (global) mix; par at fact-sheet mix", "CLF": "Disclosed Canada non-par (annual)",
             "EQL": "Par at fact-sheet mix; residual is 26% of pool", "EMP": "Par at fact-sheet mix", "COP": "Par at pool mix", "WAW": "Par at pool mix",
             "IOF": "Par at pool mix", "RBC": "Par about 1%", "BMO": "No par from 2025", "IVA": "No par block", "BLU": "No par; single PRT book"}[p]
    hrows.append(dict(focus=p == FOCUS, pre=[f"<b>{e(NAMES[p])}</b>" if p == FOCUS else e(NAMES[p]), f"{dfmt(a['date'], True)} → {dfmt(z['date'], True)}", money(z["ga_k"])],
                      cells={k.replace(" (unclassified)", "").replace("Cash & Cash Equivalent", "Short-term").replace(" Equity", " equity").replace("Fixed Income", "fixed income"): 100 * (dz[k] - da[k]) for k in L2O},
                      post=[f"{par:.0f}%", RELIAB[p], f"<span class='sm-l'>{e(basis)}</span>"]))
cols = [k.replace(" (unclassified)", "").replace("Cash & Cash Equivalent", "Short-term").replace(" Equity", " equity").replace("Fixed Income", "fixed income") for k in L2O]
med = {c: statistics.median(r["cells"][c] for r in hrows if not r["focus"]) for c in cols}
hrows.append(dict(pre=["<i>Peer median (11)</i>", "", ""], cells=med, post=["", "", ""]))
body = f"""<div class="card"><div class="ct">Change in share of the non-par / seg General Account by level 2, first to latest date (percentage points)</div>
<div class="cs">Blue = share rose, red = share fell. Reliability reflects how much of the entity's invested pool is par: where par is large the non-par mix is a residual after removing par at a held mix (est).</div>
{heat_table(cols, hrows, 8, ["Insurer", "Dates", "Block size, latest"], ["Par share", "Reliability", "Basis"])}</div>
<div class="cols2"><div><ul>
<li><b>RBC Life is one of {sum(1 for r in hrows[:-1] if r['cells']['Public fixed income'] > 0)} peers whose public fixed income share rose.</b> The peer median fell {mag(med['Public fixed income'])} pts; the common peer move was out of public bonds into private fixed income and equity.</li>
<li><b>Largest private fixed income builders:</b> BLU {sgn(hrows[5]['cells']['Private fixed income'])} pts (private placements, with below-investment-grade bonds up from {S['BLU'][0]['below_ig_pct']:.0f}% to {S['BLU'][-1]['below_ig_pct']:.0f}% of bonds), RBC Life {sgn(hrows[0]['cells']['Private fixed income'])}, CLF {sgn(hrows[3]['cells']['Private fixed income'])} (disclosed Canada non-par), SLF {sgn(hrows[2]['cells']['Private fixed income'])} and Empire Life {sgn(hrows[6]['cells']['Private fixed income'])}.</li>
</ul></div><div><ul>
<li><b>MFC</b> cut public fixed income {mag(hrows[1]['cells']['Public fixed income'])} pts for public equity ({sgn(hrows[1]['cells']['Public equity'])}); this is the global entity mix applied to Canada and includes exchange-rate moves.</li>
<li><b>ivari</b> built short-term investments ({sgn(hrows[7]['cells']['Short-term'])} pts) out of government bonds; <b>Wawanesa Life</b> cut government bonds {mag(100 * (S['WAW'][-1]['shares']['Government Bonds'] - S['WAW'][0]['shares']['Government Bonds']))} pts; preferred shares appeared in 2026 and Others rose to {100 * S['WAW'][-1]['shares']['Others']:.0f}%.
<b>Equitable</b>'s figures are low reliability: its non-par book is 26% of the pool, so small par moves show up magnified.</li>
</ul></div></div>"""
page("Peers moved out of public bonds into private credit and equity; RBC Life built private credit without giving up public fixed income",
     "Peer comparison, level 2", body, SRC + BASIS + " Par mixes: public par fact sheets at fiscal 2025 year-end (SLF, Empire Life, Equitable), held for all dates (est); CLF from Lifeco MD&A. Peer median excludes RBC Life.")

# ---- page 5: alternatives
drows = sorted([(NAMES[p], alts(S[p][0]), alts(S[p][-1]), p == FOCUS) for p in ORDER], key=lambda x: -x[2])
_ah = [r[0] for r in drows if r[2] > alts(rN)]
ahead_n, ahead = len(_ah), ", ".join(_ah[:-1]) + " and " + _ah[-1]
crow = sorted([(NAMES[p], {k: 100 * S[p][-1]["shares"][k] for k in M["alts"]}, p == FOCUS) for p in ORDER], key=lambda x: -sum(x[1].values()))
body = f"""<div class="cols2">
<div class="card"><div class="ct">Alternatives incl. Others, share of the non-par / seg General Account</div>
<div class="cs">Hollow dot = first date, filled dot = latest date; label = latest share and change in points.</div>
{dumbbell(drows, w=478)}</div>
<div class="card"><div class="ct">What the alternatives are, latest date</div>
<div class="cs">Private placements, direct-lending mortgages, real estate and Others (unclassified other invested assets, read as likely externally managed, est).</div>
{legend([(ALT_NAME[k], ALT_C[k]) for k in M['alts']])}
{stacked_hbars(crow, M['alts'], ALT_C, w=478)}</div></div>
<ul class="two">
<li><b>RBC Life {alts(r0):.1f}% to {alts(rN):.1f}%</b>, {['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth'][ahead_n]} of 12 by size of share, behind {ahead}. All of the rise is private placements ({100 * r0['shares']['Illiquid Term Loan']:.1f}% to {100 * rN['shares']['Illiquid Term Loan']:.1f}%); mortgages were flat at {100 * rN['shares']['Commercial Mortgages']:.1f}% and Others fell.</li>
<li><b>The gap to the Big 3 did not close:</b> SLF {alts(S['SLF'][-1]):.0f}%, CLF {alts(S['CLF'][-1]):.0f}%, MFC {alts(S['MFC'][-1]):.0f}% (est). Their private placement books alone ({100 * S['SLF'][-1]['shares']['Illiquid Term Loan']:.0f}% and {100 * S['CLF'][-1]['shares']['Illiquid Term Loan']:.0f}% at SLF and CLF) are larger than RBC Life's whole alternatives share.</li>
<li><b>Externally managed assets are the least visible bucket.</b> Only directly owned real estate is filed; fund holdings sit in Others or common shares. RBC Life shows nil real estate and {100 * rN['shares']['Others']:.1f}% Others.</li>
<li><b>Why it matters:</b> the ALM study's question is how far RBC Life should move into alternatives within LICAT 125%. The run rate of the last nine months, about {sgn((alts(rN) - alts(rFY25)) / 3, 1)} pts a quarter, would at that pace take roughly {max((alts(S['MFC'][-1]) - alts(rN)) / max((alts(rN) - alts(rFY25)) / 3, 0.01) / 4, 0):.0f} years to reach MFC's level.</li>
</ul>"""
page(f"RBC Life's alternatives share rose {mag(d_alt)} pts to {alts(rN):.0f}%, all in private placements; the Big 3 stayed at {min(big3):.0f}–{max(big3):.0f}%",
     "Alternatives (definition confirmed Nov 15, 2026)", body,
     SRC + BASIS + " Alternatives = illiquid term loans + commercial mortgages + externally managed (visible: real estate) + Others (est). MFC and SLF: entity mix (est). CLF: Dec 31, 2023 to Dec 31, 2025.")

# ---- page 6: RBC vs peer range, level 2 small multiples
decd = sorted({r["date"] for p in QPEERS for r in S[p] if M["fy"][p] == "dec"})
byper = {}
for p in QPEERS:
    for r in S[p]:
        byper.setdefault(r["per"], []).append(l2sh(r["shares"]))
perdate = {r["per"]: r["date"] for r in S["MFC"]}
panels = []
for k in L2O:
    rbc = [(dnum(r["date"]), 100 * l2sh(r["shares"])[k]) for r in R]
    med_, lo_, hi_ = [], [], []
    for per in sorted(perdate):
        vals = sorted(100 * x[k] for x in byper[per])
        q = statistics.quantiles(vals, n=4)
        x = dnum(perdate[per])
        med_.append((x, statistics.median(vals)))
        lo_.append((x, q[0]))
        hi_.append((x, q[2]))
    panels.append((k.replace(" (unclassified)", " (unclassified)"), rbc, med_, lo_, hi_))
body = f"""<div class="card"><div class="ct">RBC Life against the peer range, share of the non-par / seg General Account by level 2</div>
<div class="cs">Blue = RBC Life at its fiscal quarter-ends; grey line = median of the 10 quarterly OSFI peers (CLF is annual and left out); band = middle half of those peers. BMO Life is placed with the December filers one month earlier than its own dates.</div>
{legend([("RBC Life", BLUE), ("Peer median", "#7b818a")], line=True)}
{small_multiple_lines(panels)}</div>
<ul class="two">
<li>RBC Life's <b>private fixed income</b> is above the middle half of peers throughout and widening ({panels[1][1][0][1]:.1f}% to {panels[1][1][-1][1]:.1f}% against a median of {panels[1][2][-1][1]:.1f}%).</li>
<li><b>Public equity</b> held near {panels[2][1][0][1]:.1f}% to {panels[2][1][-1][1]:.1f}% while the peer median rose to {panels[2][2][-1][1]:.1f}% in 2026. RBC Life backs its long liabilities with fixed income, not equity.</li>
<li><b>Short-term investments</b> went from the top of the peer range to nil; liquidity is now carried through the repo programme and LF1 cash ({money(rN['lf1_cash_k'])} at the latest date).</li>
<li><b>Real estate</b>: none directly owned at RBC Life; the peer median is also near nil, with the Big 3, Equitable and BMO Life the holders.</li>
</ul>"""
page("Against the peer range RBC Life is high and rising in private fixed income and now holds no short-term investments",
     "RBC Life against the peer range", body, SRC + BASIS + " Peer statistics include estimates for peers with a par block (see reliability on the peer comparison page).")

# ---- page 7: level 3 heatmap + credit quality / accounting class
h3 = []
for p in ORDER:
    a, z = S[p][0], S[p][-1]
    h3.append(dict(focus=p == FOCUS, pre=[f"<b>{e(NAMES[p])}</b>" if p == FOCUS else e(NAMES[p])],
                   cells={L3_SHORT[k]: 100 * (z["shares"][k] - a["shares"][k]) for k in L3},
                   post=[f"{a['below_ig_pct']:.1f}% → {z['below_ig_pct']:.1f}%",
                         f"{a['acct']['FVOCI']:.0f}% → {z['acct']['FVOCI']:.0f}%", f"{a['acct']['Amortized cost']:.0f}% → {z['acct']['Amortized cost']:.0f}%"]))
c3 = [L3_SHORT[k] for k in L3]
body = f"""<div class="card"><div class="ct">Change in share by level 3, first to latest date (percentage points), with credit quality and accounting class</div>
<div class="cs">Level 3 columns: non-par / seg General Account. Right-hand columns: whole entity as filed (below-investment-grade share of bonds; FVOCI and amortized-cost share of invested assets), first → latest.</div>
{heat_table(c3, h3, 8, ["Insurer"], ["Below IG, % of bonds", "FVOCI", "Amortized cost"])}</div>
<div class="cols2"><div><ul>
<li><b>RBC Life:</b> government bonds {sgn(h3[0]['cells']["Gov't bonds"])} pts net (after a {sgn(100 * (rFY25['shares']['Government Bonds'] - r0['shares']['Government Bonds']))} pts rise to Oct 31, 2025), private placements {sgn(h3[0]['cells']['Private plac.'])}, short-term {sgn(h3[0]['cells']['Short-term'])}. Below-investment-grade bonds stayed at about 0.1%, so the move into private credit was investment grade.</li>
<li><b>BLU</b> is the peer taking credit risk: government bonds {sgn(h3[5]['cells']["Gov't bonds"])} pts, private placements {sgn(h3[5]['cells']['Private plac.'])}, below-investment-grade bonds {S['BLU'][0]['below_ig_pct']:.0f}% to {S['BLU'][-1]['below_ig_pct']:.0f}%.</li>
</ul></div><div><ul>
<li><b>Accounting class moved little</b> except at MFC, where FVOCI fell from {S['MFC'][0]['acct']['FVOCI']:.0f}% to {S['MFC'][-1]['acct']['FVOCI']:.0f}% of invested assets. RBC Life kept about {rN['acct']['FVOCI']:.0f}% at FVOCI, so its OCI exposure grew only with the book.</li>
<li><b>Co-operators Life</b> and <b>Foresters Life</b> swapped government for corporate bonds, most of it in the first half of 2026 (government bonds {sgn(h3[9]['cells']["Gov't bonds"])} and {sgn(h3[10]['cells']["Gov't bonds"])} pts over the whole period).</li>
</ul></div></div>"""
page("At level 3 the moves are government-to-credit switches; only BLU added below-investment-grade risk",
     "Level 3 findings", body, SRC + BASIS + " Below-IG and accounting class: OSFI LF2 investment schedule, legal entity (includes par, UL funds and, for the Big 3, foreign operations).")

# ---- page 8: liability and funding context across peers
lrows = []
lines = ["Individual insurance", "Individual annuity", "Group insurance", "Group annuity"]
for p in ORDER:
    i = D["icl"].get(p, {})
    ys = [y for y in sorted(i) if sum(i[y]["lines"].values()) > 0]
    a, z = i[ys[0]], i[ys[-1]]
    ta, tz = sum(a["lines"].values()), sum(z["lines"].values())
    f = [x for x in D["fund"][p] if x["genacct_k"]]
    f0 = next(x for x in f if x["date"] == a["date"]) if any(x["date"] == a["date"] for x in f) else f[0]
    f1 = next(x for x in f if x["date"] == z["date"])
    ser_ = S[p]
    cells = {ln + ", pts": 100 * (z["lines"][ln] / tz - a["lines"][ln] / ta) for ln in lines}
    lrows.append(dict(focus=p == FOCUS, pre=[f"<b>{e(NAMES[p])}</b>" if p == FOCUS else e(NAMES[p]), f"{dfmt(a['date'], True)} → {dfmt(z['date'], True)}",
                                             f"{money(ta)} → {money(tz)}", f"{100 * z['lines']['Group annuity'] / tz:.0f}%"],
                      cells=cells,
                      post=[f"{f0['financing_pct']:.1f}% → {f1['financing_pct']:.1f}%", f"{f0['buffer_pct']:.1f}% → {f1['buffer_pct']:.1f}%",
                            f"{ser_[0]['licat']:.0f}% → {ser_[-1]['licat']:.0f}%"]))
body = f"""<div class="card"><div class="ct">Liability mix, funding and capital beside the asset moves (fiscal year-ends for liabilities, funding and buffer; first to latest filed date for LICAT)</div>
<div class="cs">Core liabilities = the four non-par product lines excluding seg funds, net of reinsurance: what the General Account backs. Mix change in percentage points of core liabilities.</div>
{heat_table([ln + ", pts" for ln in lines], lrows, 8, ["Insurer", "Year-ends", "Core liabilities", "Group annuity share, latest"], ["Financing / General Account", "Buffer", "LICAT total"])}</div>
<ul class="two">
<li><b>RBC Life and BMO Life are the PRT growers</b> among diversified peers (group annuity {sgn(lrows[0]['cells']['Group annuity, pts'])} and {sgn(lrows[4]['cells']['Group annuity, pts'])} pts of core liabilities in one year). BMO Life backed its growth with government bonds and short-term investments; RBC Life with government bonds first, private placements later.</li>
<li><b>SLF</b> grew group annuities {sgn(lrows[2]['cells']['Group annuity, pts'])} pts and holds {100 * S['SLF'][-1]['shares']['Illiquid Term Loan']:.0f}% in private placements (est): the peer whose asset mix most reflects a long, illiquid book.</li>
<li><b>Only RBC Life increased financing materially</b> ({lrows[0]['post'][0]}); ivari's 13% is a funds-withheld reinsurance deposit, not repos. Financing leverages the General Account, so RBC Life's mix shares are of a larger, partly borrowed asset base.</li>
<li><b>Capital was not the constraint for anyone:</b> LICAT moved by a few points at most peers; RBC Life's buffer fell with its ABL CSM, not with asset risk.</li>
</ul>"""
page("Liabilities explain part of the moves: RBC Life and BMO Life grew PRT; only RBC Life also grew repo funding",
     "Liability, funding and capital context", body,
     SRC + "Product lines: OSFI LF3 Canada column (ALM icl_by_line). Financing, buffer: ALM study views (Big 3 Canada estimates; MFC equity basis unreliable, L43). LICAT: OSFI LCQ, legal entity. RBC Life and BMO Life have no IFRS 17 year-end before Oct 31, 2024. Foresters Life product lines are as filed.")

# ---- page 9: peers outside the full method
ia0, iaN = D["iag"][0], D["iag"][-1]
ia_keys = ["Government Bonds", "Corporate Bonds", "Illiquid Term Loan", "Private Liquid Loans", "Commercial Mortgages", "Consumer Loans",
           "Common Shares", "Other Private Equity", "Real Estate Equity", "Others", "Cash Equivalent"]
ia_name = {**L3_NAME, "Private Liquid Loans": "Corporate loans", "Consumer Loans": "Car and other loans", "Illiquid Term Loan": "Private placements",
           "Other Private Equity": "Private equity and infrastructure", "Commercial Mortgages": "Mortgages (insured and uninsured)", "Common Shares": "Public equity",
           "Cash Equivalent": "Cash and short-term"}
ia_rows = ""
for k in ia_keys:
    a, z = 100 * ia0["shares"].get(k, 0), 100 * iaN["shares"].get(k, 0)
    bg, fg = div_color(z - a, 6)
    ia_rows += f"<tr><td class='l'>{e(ia_name[k])}</td><td>{a:.1f}%</td><td>{z:.1f}%</td><td><span class='cell' style='background:{bg};color:{fg}'>{sgn(z - a)}</span></td></tr>"
coarse = ["Bonds", "Mortgages & loans", "Equities", "Real estate", "Other invested assets", "Cash & short-term"]
co_rows = ""
for cid, nm in (("beneva", "Beneva (incl. P&C)"), ("uv_insurance", "UV Insurance"), ("assumption_life", "Assumption Life"), ("humania", "Humania")):
    pts = D["annual"][cid]
    a, z = pts[0], pts[-1]
    tds = ""
    for k in coarse:
        dv = 100 * (z["shares"].get(k, 0) - a["shares"].get(k, 0))
        bg, fg = div_color(dv, 8)
        tds += f"<td><span class='cell' style='background:{bg};color:{fg}'>{sgn(dv)}</span></td>"
    co_rows += f"<tr><td class='l'>{e(nm)}</td><td>{a['date'][:4]} → {z['date'][:4]}</td><td>${z['total_mm']:,.0f}MM</td>{tds}</tr>"
os_rows = ""
for sid in ("CPL", "PRI"):
    rs = D["outside"][sid]
    a, z = rs[0], rs[-1]
    da, dz = l2sh(a["shares"]), l2sh(z["shares"])
    tds = ""
    for k in L2O:
        dv = 100 * (dz[k] - da[k])
        bg, fg = div_color(dv, 8)
        tds += f"<td><span class='cell' style='background:{bg};color:{fg}'>{sgn(dv)}</span></td>"
    os_rows += f"<tr><td class='l'>{e(NAMES[sid])}</td><td>{dfmt(a['date'], True)} → {dfmt(z['date'], True)}</td><td>{money(z['ga_k'])}</td>{tds}</tr>"
body = f"""<div class="cols2 narrow-left">
<div class="card"><div class="ct">iA: total invested assets, {dfmt(ia0['date'])} to {dfmt(iaN['date'])}</div>
<div class="cs">AMF filer: consolidated, including US operations, par and UL (not separable, ALM rule). ${ia0['total_mm'] / 1e3:,.1f}BN to ${iaN['total_mm'] / 1e3:,.1f}BN. Source: iA supplementary information packages.</div>
<table class="num"><thead><tr><th class='l'>Level 3</th><th>{dfmt(ia0['date'], True)}</th><th>{dfmt(iaN['date'], True)}</th><th>Change, pts</th></tr></thead><tbody>{ia_rows}</tbody></table>
<p class="note">iA moved from government bonds into public equity and private equity and infrastructure, and opened a corporate loan book in 2025 (all BB or lower, ALM deck v3).
The Q1 2024 package moved about 4 pts from private to public corporate issues in one quarter, which reads as a reclassification rather than trading.</p></div>
<div>
<div class="card"><div class="ct">Insurers outside OSFI data: yearly, coarser classes (percentage-point change)</div>
<div class="cs">Annual report balance sheets; the ALM repo has no data for these insurers, so the earlier project method is used. Whole company, including par.</div>
<table class="num tight"><thead><tr><th class='l'>Insurer</th><th>Year-ends</th><th>Invested, latest</th>{''.join(f'<th>{e(k)}</th>' for k in coarse)}</tr></thead><tbody>{co_rows}</tbody></table></div>
<div class="card"><div class="ct">OSFI filers outside the ALM study's peer universe (level 2, percentage-point change)</div>
<div class="cs">Creditor and niche insurers, not in the ALM regression set. Entity invested pool, same level 3 mapping; no block view.</div>
<table class="num tight"><thead><tr><th class='l'>Insurer</th><th>Dates</th><th>Invested, latest</th>{''.join(f'<th>{e(k.replace(" (unclassified)", "").replace("Cash & Cash Equivalent", "Short-term"))}</th>' for k in L2O)}</tr></thead><tbody>{os_rows}</tbody></table>
<p class="note"><b>Primerica Life</b> holds only public bonds; within them government bonds fell {mag(100 * (D['outside']['PRI'][-1]['shares']['Government Bonds'] - D['outside']['PRI'][0]['shares']['Government Bonds']))} pts in favour of corporates. <b>Canadian Premier Life</b> raised common shares from {100 * D['outside']['CPL'][0]['shares']['Common Shares']:.0f}% to {100 * D['outside']['CPL'][-1]['shares']['Common Shares']:.0f}% as its invested pool shrank.</p>
<p class="note"><b>Desjardins:</b> no stand-alone life-company balance sheet is published (ALM limitation L42), so no asset mix. <b>Canada Protection Plan</b> is inside Foresters Life.
<b>UV Insurance</b>'s 2025 figures include the block bought from BMO Life. <b>BLU</b> (Blumont) is an ALM study peer that is not on the project's list of 20 insurers; it is shown because it is the pure PRT comparator.</p></div>
</div></div>"""
page("iA and the smaller insurers: shown on a coarser basis because the ALM method needs OSFI block data they do not file",
     "Insurers outside the full method", body, SRC + "iA: supplementary information packages (Invested assets). Beneva, UV Insurance, Assumption Life, Humania: annual reports, statements of financial position. Not on the non-par / seg General Account basis; not comparable with the 12 OSFI peers.")

# ---- pages 10: appendix small multiples per peer
cards = ""
for p in ORDER:
    rs = S[p]
    note = {"CLF": "annual, disclosed", "EQL": "low reliability", "MFC": "entity mix, est", "SLF": "entity mix, est"}.get(p, "")
    cards += (f"<div class='mini'><div class='smt'>{e(NAMES[p])} <span class='mut'>{money(rs[-1]['ga_k'])}{', ' + note if note else ''}</span></div>"
              f"{stacked_columns(rs, w=250, h=150, label_last=False, small=True)}</div>")
body = f"""<div class="card"><div class="ct">Each peer's non-par / seg General Account by level 2, every filed date</div>
<div class="cs">Share of invested assets, 0 to 100%. Year marks sit at each fiscal year-end. Block size at the latest date beside each name.</div>
{legend([(k.replace(' (unclassified)', ''), C[k]) for k in L2O])}
<div class="minigrid">{cards}</div></div>"""
page("Appendix: every peer's mix over time", "Appendix", body, SRC + BASIS + " CLF: three year-ends (Dec 31, 2023 chain-linked, est). BMO Life from Apr 30, 2024 (its first IFRS 17 return files an incomplete UL line).")

# ---- page 11: method and limitations
brk = M["clf_break_pp"]
body = f"""<div class="cols3 text">
<div><h3>Method (ALM repo rules applied)</h3>
<ul>
<li><b>Basis.</b> Canadian business; General Account excl. par / seg fund; UL policyholder funds, par and seg fund blocks outside it (METHODOLOGY s.3, 4a).</li>
<li><b>Periods.</b> IFRS 17 only: December filers from Dec 31, 2023; RBC Life and BMO Life from their first IFRS 17 quarter, Jan 31, 2024 (s.1, L53). Shown by date.</li>
<li><b>Taxonomy.</b> OSFI LF2 investment lines mapped to level 3 as the study's build_osfi_assets.py; investment property from LF1 between year-ends. LF1 cash is outside the invested pool, as in the study's block allocation.</li>
<li><b>Blocks.</b> The study's fiscal 2025 block allocation (BI-04) extended to every filed date: pool by level 3, less UL funds (LF2 index-linked lines), less par, residual = non-par / seg General Account. At Oct 31 / Dec 31, 2025 the result equals the study's file for all 12 OSFI peers (largest difference 0.0 pts).</li>
<li><b>Big 3.</b> MFC and SLF: Canada follows the entity (global) mix. CLF: disclosed Canada non-par mix (Lifeco MD&A), annual.</li>
<li><b>Reallocation.</b> Change in share between dates; $MM = share × block size from the study views.</li>
</ul></div>
<div><h3>Estimates and limitations</h3>
<ul>
<li><b>Par mix held.</b> Par is removed at the fiscal 2025 fact-sheet mix (SLF, Empire Life, Equitable; RBC Life target mix) or at the pool mix (MFC, Co-operators Life, Wawanesa Life, Foresters Life) for every date. A real change in a par account's mix shows up as a non-par move. Equitable (par 74% of the pool) is low reliability.</li>
<li><b>2026 dates.</b> The study views end at fiscal 2025; later block sizes hold their year-end share of the pool (est).</li>
<li><b>CLF basis break.</b> Lifeco re-presented the table in 2025 (insurance contracts only). Dec 31, 2023 is chain-linked; at Dec 31, 2024 the re-presentation moved mortgages {sgn(brk['Commercial Mortgages'])} pts and stocks {sgn(brk['Common Shares'] + brk['Others'])} pts.</li>
<li><b>MFC, SLF.</b> Entity mixes include foreign operations and exchange-rate moves (L03, L43).</li>
<li><b>RBC Life Apr 30, 2026.</b> UL lines not filed that quarter; interpolated between neighbours (est).</li>
<li><b>BMO Life.</b> Starts Apr 30, 2024; its par block was transferred in fiscal 2025 (L51).</li>
<li><b>Market effects.</b> Shares are at balance-sheet value, so they move with prices as well as trades. Not modelled.</li>
<li><b>Hidden alternatives.</b> Fund holdings sit in Others or common shares (L07, L21).</li>
</ul></div>
<div><h3>Next steps</h3>
<ul>
<li>Collect historical par fact sheets (CLF, SLF, Equitable, Empire Life) to replace the held par mix.</li>
<li>Build fiscal 2026 study views when the October and December 2026 year-end returns are filed, so 2026 block sizes and repos are reported, not estimated.</li>
<li>Split trading from repricing (needs modelling: rates, spreads and equity returns by class).</li>
<li>Read RBC Life's fiscal 2026 rotation against its Oct 31, 2026 repo balance and PRT volumes.</li>
<li>Private credit capacity within LICAT 125% (the ALM study's modelling stage).</li>
</ul>
<h3>Files</h3>
<p class="note">Code and data: abiddobani/InsuranceCompanies, analysis/portfolio_reallocation_alm (build.py, make_report.py, mix_by_date.csv, changes.csv, context.csv, regression_check.csv).
Framework: MooseDragon/cdn-life-insurer-alm at commit {M['alm_commit']}. RBC internal figures are not used; public data only.</p>
<p class="note">Par sources: {e('; '.join(v for k, v in M['par_sources'].items() if k != 'RBC'))}; Great-West Lifeco 2025 annual report and Q4 2024 MD&A (assets supporting insurance contract liabilities).</p></div></div>"""
page("Method, estimates and limitations", "Method", body, SRC + BASIS)

CSS = """
@page { size: A4 landscape; margin: 9mm 10mm; }
* { box-sizing: border-box; }
html, body { margin: 0; background: #fff; color: #191919; font-family: Inter, "Helvetica Neue", Arial, "Liberation Sans", sans-serif; font-size: 11.6px; line-height: 1.42; }
.page { width: 1046px; height: 724px; page-break-after: always; break-after: page; display: flex; flex-direction: column; overflow: hidden; }
.page:last-child { page-break-after: auto; break-after: auto; }
header { border-bottom: 1px solid #e7e7e7; padding-bottom: 7px; margin-bottom: 9px; }
.kick { font-size: 10px; letter-spacing: .06em; text-transform: uppercase; color: #666; margin-bottom: 2px; }
h1 { font-size: 18.5px; line-height: 1.22; font-weight: 650; margin: 0; letter-spacing: -0.005em; }
h3 { font-size: 12px; margin: 0 0 5px; font-weight: 650; }
.body { flex: 1; display: flex; flex-direction: column; gap: 9px; min-height: 0; }
footer { border-top: 1px solid #e7e7e7; padding-top: 5px; display: flex; gap: 16px; justify-content: space-between; align-items: flex-start; }
.src { font-size: 8.3px; color: #666; line-height: 1.32; flex: 1; }
.pn { font-size: 8.5px; color: #666; white-space: nowrap; }
.lede { font-size: 13px; line-height: 1.45; margin: 0; max-width: 1000px; }
.tiles { display: grid; grid-template-columns: repeat(5, 1fr); gap: 9px; }
.tile { border: 1px solid #e7e7e7; border-radius: 6px; padding: 8px 10px; }
.tl { font-size: 10px; color: #666; }
.tv { font-size: 16px; font-weight: 650; margin: 2px 0 1px; white-space: nowrap; }
.ts { font-size: 9px; color: #666; line-height: 1.3; }
.cols2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.cols2.wide-left { grid-template-columns: 480px 1fr; }
.cols2.narrow-left { grid-template-columns: 390px 1fr; }
.cols2 > *, .cols3 > * { min-width: 0; }
table.tight .cell { min-width: 38px; padding: 2px 3px; }
table.tight th, table.tight td { padding: 4px 3px; }
.p1 li { font-size: 12.2px; line-height: 1.45; margin-bottom: 7px; }
.p1 table.plain th, .p1 table.plain td { font-size: 10.8px; padding: 5px 6px 5px 0; }
.lede.big { font-size: 14.5px; }
.tiles { margin: 4px 0; }
.cols3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
.cols3.text { gap: 18px; }
.card { border: 1px solid #e7e7e7; border-radius: 6px; padding: 9px 11px; margin-bottom: 0; }
.card + .card { margin-top: 9px; }
.ct { font-size: 12px; font-weight: 650; }
.cs { font-size: 9.5px; color: #666; margin: 1px 0 5px; line-height: 1.35; }
ul { margin: 0; padding-left: 15px; }
li { margin-bottom: 4px; }
ul.two { columns: 2; column-gap: 22px; }
ul.two li { break-inside: avoid; }
.note { font-size: 9.5px; color: #666; margin: 6px 0 0; line-height: 1.4; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 9.5px; color: #666; margin-bottom: 4px; }
.li { display: inline-flex; align-items: center; gap: 4px; }
.lk { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
.ll { width: 14px; height: 0; border-top: 2px solid; display: inline-block; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
table.num th, table.num td, table.heat th, table.heat td { padding: 4px 5px; text-align: right; font-size: 10px; border-bottom: 1px solid #f0f0f0; white-space: nowrap; }
table.num th, table.heat th { color: #666; font-weight: 500; font-size: 9px; border-bottom: 1px solid #c2c2c2; white-space: normal; vertical-align: bottom; line-height: 1.2; }
td.l, th.l { text-align: left !important; }
td.c { text-align: center !important; }
table.heat td.na { color: #999; }
table.heat tr.focus td { background: #f3f8fe; }
tr.tot td { font-weight: 650; border-top: 1px solid #c2c2c2; }
.cell { display: inline-block; min-width: 44px; padding: 2px 5px; border-radius: 3px; text-align: center; }
.sw { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 5px; }
.sm-l { font-size: 8.8px; color: #666; white-space: normal; display: inline-block; max-width: 190px; text-align: left; line-height: 1.2; }
table.plain th, table.plain td { text-align: left; vertical-align: top; padding: 3px 6px 3px 0; font-size: 9.8px; border-bottom: 1px solid #f0f0f0; line-height: 1.3; }
table.plain th { color: #666; font-weight: 500; font-size: 9px; }
table.plain td:first-child { font-weight: 650; white-space: nowrap; }
.smgrid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px 10px; }
.smt { font-size: 10.5px; font-weight: 650; margin-bottom: 1px; }
.mut { font-weight: 400; color: #666; font-size: 9px; }
.minigrid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px 8px; }
"""
doc = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Peer portfolio reallocations, ALM basis</title><style>{CSS}</style></head><body>{''.join(pages)}</body></html>"
(HERE / "report.html").write_text(doc)

js = """
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1123, height: 794 } });
  await p.goto('file://' + process.argv[2]);
  await p.pdf({ path: process.argv[3], format: 'A4', landscape: true, printBackground: true, preferCSSPageSize: true });
  const over = await p.evaluate(() => [...document.querySelectorAll('.page')].map((s, i) => [i + 1, s.scrollHeight, s.clientHeight]).filter(x => x[1] > x[2] + 1));
  console.log('pages overflowing:', JSON.stringify(over));
  await b.close();
})();
"""
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
    f.write(js)
env = {"NODE_PATH": subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()}
import os
r = subprocess.run(["node", f.name, str(HERE / "report.html"), str(OUT)], capture_output=True, text=True, env={**os.environ, **env})
print(r.stdout, r.stderr[-800:])
print("wrote", OUT)
