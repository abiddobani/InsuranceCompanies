"""Build the peer landscape summary deck in the style of the standalone analysis PDFs.

Every slide is an HTML page (1280 x 720) drawn with the same cards, palette and inline-SVG charts as
the discount curve, portfolio composition and investment risk dashboards, printed to PDF with the
preinstalled Playwright Chromium. The .pptx carries the same slides: native title and source text,
and the slide body as a high-resolution image (the charts are not editable chart objects).

Run from the repository root after the three build scripts:
    python3 analysis/discount_curves/build.py
    python3 analysis/portfolio_composition/build.py
    python3 analysis/investment_risk/build.py
    python3 analysis/summary_deck/build_deck.py
"""
import html
import math
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[2]
A = ROOT / "analysis"
HERE = Path(__file__).resolve().parent
PDF_OUT = HERE / "peer-landscape-summary.pdf"
PPTX_OUT = HERE / "peer-landscape-summary.pptx"

esc = html.escape
FOCUS = "RBC Life"
MARK = "▸ "  # small right-pointing triangle, as in the dashboards

# dashboard palette and tokens
BLUE, ORANGE, TEAL, RED, PURPLE, OLIVE, PINK, GREY = ("#1f5fa8", "#e09a2c", "#3a9d8f", "#c4524d",
                                                      "#8a7fb8", "#6b8e23", "#d16ba5", "#7f7f7f")
PALETTE = [BLUE, ORANGE, TEAL, RED, PURPLE, OLIVE, PINK, GREY]
MUTED_BAR, GRID, AXIS, REF, INK, SUB, FOCUS_BG = "#b9bec7", "#eceef1", "#9aa1ab", "#3b4048", "#1f2329", "#5d6470", "#e8f0fa"

# ---------------------------------------------------------------- data
LS = pd.read_csv(A / "investment_risk/dashboard/landscape.csv")
EAR = pd.read_csv(A / "investment_risk/dashboard/earnings_at_risk.csv")
DC = pd.read_csv(A / "discount_curves/landscape_2025q4.csv")
PP = pd.read_csv(A / "discount_curves/dashboard/product_points.csv")
PCV = pd.read_csv(A / "discount_curves/dashboard/product_curves.csv")
PAR = pd.read_csv(A / "discount_curves/dashboard/par_vs_dividend_rate.csv")
PH = pd.read_csv(A / "discount_curves/dashboard/premium_history.csv")
PC = pd.read_csv(A / "portfolio_composition/portfolio_composition_pct.csv")
OBS = pd.read_csv(A / "portfolio_composition/off_balance_sheet.csv")
LIC_H = pd.read_csv(ROOT / "data/osfi/licat_ratios.csv", skiprows=[1])

SHORT = {"iA Financial Group": "iA Financial", "Foresters Life (incl. Canada Protection Plan)": "Foresters Life",
         "Canadian Premier Life": "Canadian Premier", "Desjardins Insurance": "Desjardins"}
short = lambda n: SHORT.get(n, n)
label = lambda n: (MARK + short(n)) if short(n) == FOCUS else short(n)

LS["name"] = LS.company.map(short)
DC["name"] = DC.company.map(short)
PC["name"] = PC.company.map(short)
EAR["name"] = EAR.company.map(short)
rbc = LS[LS.company_id == "rbc_life"].iloc[0]
med = LS.select_dtypes("number").median()
dc_rbc = DC[DC.company_id == "rbc_life"].iloc[0]


def rank_desc(col):
    s = LS[col].dropna()
    return int((s > rbc[col]).sum() + 1), len(s)


L2 = {
    "Public fixed income": ["Asset Backed Securities", "Corporate Bonds", "Government Bonds", "Bonds (issuer n/d)"],
    "Public equity": ["Common Shares", "Preferred Shares"],
    "Private fixed income": ["Commercial Mortgages", "Illiquid Term Loans", "Private Liquid Loans", "Co-Investments",
                             "Policy & Other Loans"],
    "Alternatives (real estate, infra, PE, private debt)": ["Real Estate Equity", "Infrastructure Equity",
                                                           "Other Private Equity", "Infrastructure Debt",
                                                           "Structured Products", "Other Private Debt"],
    "Cash and other": ["Cash", "Other / Unclassified"],
}
for k, cols in L2.items():
    PC[k] = PC[cols].sum(axis=1)
pcx = PC.set_index("name")

il = PP[(PP.period == "2025Q4") & (PP["product"] == "Individual life")].set_index("company")
rbc_il, med_il = il.loc["RBC Life"], il.loc["Peer median"]
liab = DC.set_index("name").liability_vs_median_per_10bn_mm
liab_pct = DC.set_index("name").liability_vs_median_pct
par_ye = PAR[(PAR.view == "Year end 2025") & PAR.dsir_less_flat_bp.notna()].copy()
par_ye["name"] = par_ye.company.map(short)
par_gap_rbc = int(par_ye.set_index("name").loc[FOCUS, "dsir_less_flat_bp"])
par_pos = par_ye[par_ye.dsir_less_flat_bp > 0].dsir_less_flat_bp
ear = EAR.sort_values("total_cad_mm", ascending=False)
ear_med = ear.total_cad_mm.median()
limit_25 = 35 * 25 / 28
cap_rank, cap_n = rank_desc("capital_ratio_pct")
cap_low = cap_n - cap_rank + 1
size_rank, size_n = rank_desc("portfolio_cad_mm")
pc_rank, pc_n = rank_desc("private_credit_pct")
repos_sorted = LS[["name", "repo_pct"]].dropna().sort_values("repo_pct", ascending=False)
next_repo = repos_sorted.iloc[1]
lic_rbc = LIC_H[LIC_H.company_id == "rbc_life"]
tot_col = [c for c in lic_rbc.columns if c.startswith("Total Ratio")][0]
lic_rbc = lic_rbc.set_index(lic_rbc.fiscal_year.astype(str) + lic_rbc.quarter)[tot_col].astype(float)
gap_now = (PH[(PH.company == "RBC Life") & (PH.period == "2026Q3")].lp_30y.iloc[0]
           - PH[PH.period == "2026Q3"].lp_30y.median()) * 100
ORDINAL = {1: "lowest", 2: "second-lowest", 3: "third-lowest", 4: "fourth-lowest"}


def fv(v, f="{:.1f}", na="n/d"):
    return na if pd.isna(v) else f.format(v)


# ---------------------------------------------------------------- SVG helpers
def nice_step(span, target=5):
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def ticks_for(lo, hi, target=5):
    step = nice_step(hi - lo, target)
    t0 = math.floor(lo / step) * step
    out = []
    t = t0
    while t <= hi + 1e-9:
        out.append(round(t, 6))
        t += step
    return out


def svg(W, H, parts):
    return (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">'
            + "".join(parts) + "</svg>")


def hbar(items, fmt, W=818, rowh=23, label_w=130, right_w=64, vmin=None, vmax=None, median=None,
         median_label=None, color=BLUE, tick_fmt=None, top=20):
    """Horizontal bars, one per insurer. Peers muted, RBC Life coloured and outlined, median as a dashed line."""
    vals = [v for _, v in items]
    lo = min(0, min(vals)) if vmin is None else vmin
    hi = max(vals) if vmax is None else vmax
    tk = ticks_for(lo, hi)
    lo, hi = min(lo, tk[0]), max(hi, tk[-1])
    x0, x1 = label_w, W - right_w
    sx = lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)
    H = top + len(items) * rowh + 6
    g = []
    for t in tk:
        g.append(f'<line x1="{sx(t):.1f}" x2="{sx(t):.1f}" y1="{top - 4}" y2="{H - 6}" stroke="{GRID}"/>')
        g.append(f'<text x="{sx(t):.1f}" y="{top - 8}" text-anchor="middle" class="tk">{(tick_fmt or fmt)(t)}</text>')
    if lo < 0:
        g.append(f'<line x1="{sx(0):.1f}" x2="{sx(0):.1f}" y1="{top - 4}" y2="{H - 6}" stroke="{AXIS}"/>')
    for i, (name, v) in enumerate(items):
        y = top + i * rowh
        foc = name == FOCUS
        bh = rowh - 7
        xa, xb = sorted((sx(0 if lo <= 0 <= hi else lo), sx(v)))
        fill = color if foc else MUTED_BAR
        stroke = f' stroke="{INK}" stroke-width="1.6"' if foc else ""
        g.append(f'<rect x="{xa:.1f}" y="{y + 3}" width="{max(xb - xa, 0.5):.1f}" height="{bh}" rx="2" fill="{fill}"{stroke}/>')
        wt = ' font-weight="700"' if foc else ""
        g.append(f'<text x="{label_w - 10}" y="{y + rowh / 2 + 4:.1f}" text-anchor="end" class="lb"{wt}>{esc(label(name))}</text>')
        if v >= 0:
            g.append(f'<text x="{xb + 6:.1f}" y="{y + rowh / 2 + 4:.1f}" class="vl"{wt}>{esc(fmt(v))}</text>')
        else:
            g.append(f'<text x="{xa - 6:.1f}" y="{y + rowh / 2 + 4:.1f}" text-anchor="end" class="vl"{wt}>{esc(fmt(v))}</text>')
    if median is not None:
        x = sx(median)
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top - 4}" y2="{H - 6}" stroke="{REF}" stroke-dasharray="4 3" stroke-width="1.4"/>')
        g.append(f'<text x="{x + 6:.1f}" y="{H - 10}" class="tk" fill="{REF}" font-weight="600">{esc(median_label or "Peer median " + fmt(median))}</text>')
    return svg(W, H, g)


def dotstrip(rows, W=820, rowh=46, label_w=270, right_w=22):
    """One metric per row on its own scale: grey dots for peers, a tick for the median, a coloured dot for RBC Life."""
    g = []
    x0, x1 = label_w + 48, W - right_w - 48
    for i, r in enumerate(rows):
        y = 10 + i * rowh
        vals = [v for _, v in r["values"]]
        lo, hi = min(vals), max(vals)
        if hi == lo:
            hi = lo + 1
        sx = lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)
        cy = y + 18
        g.append(f'<text x="0" y="{y + 14}" class="lb" font-weight="600">{esc(r["metric"])}</text>')
        if r.get("hint"):
            g.append(f'<text x="0" y="{y + 29}" class="tk">{esc(r["hint"])}</text>')
        g.append(f'<line x1="{x0}" x2="{x1}" y1="{cy}" y2="{cy}" stroke="{GRID}" stroke-width="2"/>')
        g.append(f'<text x="{x0 - 8}" y="{cy + 4}" text-anchor="end" class="tk">{esc(r["fmt"](lo))}</text>')
        g.append(f'<text x="{x1 + 8}" y="{cy + 4}" class="tk">{esc(r["fmt"](hi))}</text>')
        for name, v in r["values"]:
            if name != FOCUS:
                g.append(f'<circle cx="{sx(v):.1f}" cy="{cy}" r="5" fill="{MUTED_BAR}" fill-opacity="0.85"/>')
        if r.get("median") is not None:
            x = sx(r["median"])
            g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{cy - 9}" y2="{cy + 9}" stroke="{REF}" stroke-width="2"/>')
        fx = r.get("focus")
        if fx is not None:
            g.append(f'<circle cx="{sx(fx):.1f}" cy="{cy}" r="6.5" fill="{BLUE}" stroke="{INK}" stroke-width="1.5"/>')
            g.append(f'<text x="{label_w - 8}" y="{y + 14}" text-anchor="end" class="lb" font-weight="700" fill="{BLUE}">{esc(r["fmt"](fx))}</text>')
        else:
            g.append(f'<text x="{label_w - 8}" y="{y + 14}" text-anchor="end" class="tk">not disclosed</text>')
    return svg(W, 10 + len(rows) * rowh, g)


def scatter(pts, xr, yr, xfmt, yfmt, xlab, ylab, mx, my, pos, W=820, H=478):
    m = (14, 24, 48, 64)
    sx = lambda v: m[3] + (v - xr[0]) / (xr[1] - xr[0]) * (W - m[1] - m[3])
    sy = lambda v: H - m[2] - (v - yr[0]) / (yr[1] - yr[0]) * (H - m[0] - m[2])
    g = []
    for t in ticks_for(*yr):
        g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="{GRID}"/>')
        g.append(f'<text x="{m[3] - 8}" y="{sy(t) + 4:.1f}" text-anchor="end" class="tk">{yfmt(t)}</text>')
    for t in ticks_for(*xr):
        g.append(f'<line x1="{sx(t):.1f}" x2="{sx(t):.1f}" y1="{m[0]}" y2="{H - m[2]}" stroke="{GRID}"/>')
        g.append(f'<text x="{sx(t):.1f}" y="{H - m[2] + 16}" text-anchor="middle" class="tk">{xfmt(t)}</text>')
    g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{H - m[2]}" y2="{H - m[2]}" stroke="{AXIS}"/>')
    g.append(f'<line x1="{m[3]}" x2="{m[3]}" y1="{m[0]}" y2="{H - m[2]}" stroke="{AXIS}"/>')
    g.append(f'<line x1="{sx(mx):.1f}" x2="{sx(mx):.1f}" y1="{m[0]}" y2="{H - m[2]}" stroke="{REF}" stroke-dasharray="4 3"/>')
    g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{sy(my):.1f}" y2="{sy(my):.1f}" stroke="{REF}" stroke-dasharray="4 3"/>')
    g.append(f'<text x="{sx(mx) + 5:.1f}" y="{m[0] + 12}" class="tk" fill="{REF}">Median {xfmt(mx)}</text>')
    g.append(f'<text x="{m[3] + 6}" y="{sy(my) - 5:.1f}" class="tk" fill="{REF}">Median {yfmt(my)}</text>')
    g.append(f'<text x="{(m[3] + W - m[1]) / 2}" y="{H - 6}" text-anchor="middle" class="tk" fill="{INK}">{esc(xlab)}</text>')
    g.append(f'<text transform="translate(14,{(m[0] + H - m[2]) / 2}) rotate(-90)" text-anchor="middle" class="tk" fill="{INK}">{esc(ylab)}</text>')
    for name, x, y in pts:
        foc = name == FOCUS
        cx, cy = sx(x), sy(y)
        p = pos.get(name, "r")
        dx, dy, anc = {"r": (10, 4, "start"), "l": (-10, 4, "end"), "a": (0, -10, "middle"), "b": (0, 16, "middle")}[p]
        if foc:
            g.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7.5" fill="{BLUE}" stroke="{INK}" stroke-width="1.6"/>')
            g.append(f'<text x="{cx + dx:.1f}" y="{cy + dy:.1f}" text-anchor="{anc}" class="lb" font-weight="700" fill="{BLUE}">{esc(MARK + name)}</text>')
        else:
            g.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5.5" fill="{GREY}" fill-opacity="0.8"/>')
            g.append(f'<text x="{cx + dx:.1f}" y="{cy + dy:.1f}" text-anchor="{anc}" class="sl">{esc(name)}</text>')
    return svg(W, H, g)


def curves(series, annual, W=760, H=440):
    vals = [v for s in series.values() for _, v in s]
    step = 0.5
    y0, y1 = math.floor((min(vals) - 0.1) / step) * step, math.ceil((max(vals) + 0.1) / step) * step
    m = (14, 96, 30, 48)
    sx = lambda v: m[3] + v / 80 * (W - m[1] - m[3])
    sy = lambda v: H - m[2] - (v - y0) / (y1 - y0) * (H - m[0] - m[2])
    g = []
    t = y0
    while t <= y1 + 1e-9:
        g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="{GRID}"/>')
        g.append(f'<text x="{m[3] - 8}" y="{sy(t) + 4:.1f}" text-anchor="end" class="tk">{t:.1f}%</text>')
        t += step
    for x in (1, 10, 20, 30, 40, 50, 60, 70, 80):
        g.append(f'<text x="{sx(x):.1f}" y="{H - m[2] + 16}" text-anchor="middle" class="tk">{x}</text>')
    g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{H - m[2]}" y2="{H - m[2]}" stroke="{AXIS}"/>')
    g.append(f'<text x="{(m[3] + W - m[1]) / 2}" y="{H - 4}" text-anchor="middle" class="tk" fill="{INK}">Tenor (years)</text>')
    order = sorted(series, key=lambda c: (c == "Peer median", c == FOCUS))
    ends = []
    for c in order:
        pts = sorted(series[c])
        d = " ".join(f"{'M' if i == 0 else 'L'}{sx(t):.1f},{sy(v):.1f}" for i, (t, v) in enumerate(pts))
        col, w = (BLUE, 2.8) if c == FOCUS else (REF, 2.2) if c == "Peer median" else (MUTED_BAR, 1.3)
        dash = ' stroke-dasharray="4 3"' if c in annual and c not in (FOCUS, "Peer median") else ""
        g.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{w}"{dash}/>')
        if c in (FOCUS, "Peer median"):
            ends.append([sy(pts[-1][1]), c, col])
    ends.sort()
    for i in range(1, len(ends)):
        if ends[i][0] - ends[i - 1][0] < 14:
            ends[i][0] = ends[i - 1][0] + 14
    for y, c, col in ends:
        g.append(f'<text x="{W - m[1] + 8}" y="{y + 4:.1f}" class="lb" font-weight="700" fill="{col}">{esc(c)}</text>')
    return svg(W, H, g)


def dotpair(rows, fields, fmt, W=480, rowh=27, label_w=132, step=0.5):
    vals = [v for r in rows for f, _ in fields for v in [r.get(f)] if v is not None and not pd.isna(v)]
    x0v, x1v = math.floor((min(vals) - 0.1) / step) * step, math.ceil((max(vals) + 0.1) / step) * step
    top, right = 22, 24
    sx = lambda v: label_w + (v - x0v) / (x1v - x0v) * (W - right - label_w)
    H = top + len(rows) * rowh + 6
    g = []
    t = x0v
    while t <= x1v + 1e-9:
        g.append(f'<line x1="{sx(t):.1f}" x2="{sx(t):.1f}" y1="{top - 4}" y2="{H - 6}" stroke="{GRID}"/>')
        g.append(f'<text x="{sx(t):.1f}" y="{top - 8}" text-anchor="middle" class="tk">{fmt(t)}</text>')
        t += step
    for i, r in enumerate(rows):
        y = top + i * rowh + rowh / 2
        foc = r["name"] == FOCUS
        if foc:
            g.append(f'<rect x="0" y="{y - rowh / 2:.1f}" width="{W}" height="{rowh}" fill="{FOCUS_BG}" rx="3"/>')
        wt = ' font-weight="700"' if foc else ""
        g.append(f'<text x="{label_w - 10}" y="{y + 4:.1f}" text-anchor="end" class="lb"{wt}>{esc(label(r["name"]))}</text>')
        vs = [(r[f], c) for f, c in fields if r.get(f) is not None and not pd.isna(r.get(f))]
        if len(vs) > 1:
            lo, hi = min(v for v, _ in vs), max(v for v, _ in vs)
            g.append(f'<line x1="{sx(lo):.1f}" x2="{sx(hi):.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="#c9ccd2" stroke-width="2.5"/>')
        for v, c in vs:
            g.append(f'<circle cx="{sx(v):.1f}" cy="{y:.1f}" r="5.5" fill="{c}" stroke="{INK if foc else "#fff"}" stroke-width="{1.4 if foc else 1}"/>')
    return svg(W, H, g)


def stacked(rows, colors, W=1160, rowh=26, label_w=200, right_w=0, pct=True, limit=None, limit_label=None,
            seg_fmt=None, min_label_w=30, tick_fmt=None, top=22, sub_w=0):
    """Stacked bars; rows = dicts(name, sub, vals, total). pct=True normalises each row to 100%."""
    x0, x1 = label_w, W - right_w
    if pct:
        hi = 100
        tk = [0, 25, 50, 75, 100]
    else:
        hi = max((r.get("total") or 0) for r in rows)
        tk = ticks_for(0, hi)
        hi = max(hi, tk[-1])
    sx = lambda v: x0 + v / hi * (x1 - x0)
    H = top + len(rows) * rowh + (18 if limit else 4)
    g = []
    for t in tk:
        g.append(f'<line x1="{sx(t):.1f}" x2="{sx(t):.1f}" y1="{top - 4}" y2="{H - (18 if limit else 4)}" stroke="{GRID}"/>')
        g.append(f'<text x="{sx(t):.1f}" y="{top - 8}" text-anchor="middle" class="tk">{(tick_fmt or (lambda v: f"{v:.0f}%"))(t)}</text>')
    for i, r in enumerate(rows):
        y = top + i * rowh
        bh = rowh - 7
        foc = r["name"] == FOCUS
        wt = ' font-weight="700"' if foc else ""
        ly = y + rowh / 2 + 4
        g.append(f'<text x="0" y="{ly:.1f}" class="lb"{wt}>{esc(label(r["name"]))}</text>')
        if r.get("sub"):
            g.append(f'<text x="{sub_w}" y="{ly:.1f}" class="tk" font-size="9.5px">{esc(r["sub"])}</text>')
        vals = r["vals"]
        if r.get("none"):
            g.append(f'<rect x="{x0}" y="{y + 3}" width="{sx(hi * 0.08) - x0:.1f}" height="{bh}" rx="3" fill="none" stroke="{BLUE}" stroke-dasharray="3 3"/>')
            g.append(f'<text x="{x1 + 10}" y="{ly:.1f}" class="lb" fill="{SUB}">Not disclosed</text>')
            continue
        tot = sum(v for v in vals if v) or 1
        acc = 0.0
        for v, col in zip(vals, colors):
            if not v or v <= 0:
                continue
            w = (v / tot * 100 if pct else v)
            xa, xb = sx(acc), sx(acc + w)
            g.append(f'<rect x="{xa:.1f}" y="{y + 3}" width="{max(xb - xa - 1, 0.5):.1f}" height="{bh}" rx="2" fill="{col}"/>')
            if xb - xa >= min_label_w:
                txt = seg_fmt(v) if seg_fmt else f"{v:.0f}%"
                g.append(f'<text x="{(xa + xb) / 2:.1f}" y="{ly - 0.5:.1f}" text-anchor="middle" class="sg">{esc(txt)}</text>')
            acc += w
        if foc:
            g.append(f'<rect x="{x0 - 2.5:.1f}" y="{y + 0.5}" width="{sx(acc) - x0 + 4:.1f}" height="{bh + 5}" rx="4" fill="none" stroke="{INK}" stroke-width="1.8"/>')
        if r.get("total_label"):
            g.append(f'<text x="{x1 + 10}" y="{ly:.1f}" class="lb" font-weight="700">{esc(r["total_label"])}</text>')
    if limit is not None:
        x = sx(limit)
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top - 4}" y2="{H - 16}" stroke="{REF}" stroke-dasharray="4 3" stroke-width="1.4"/>')
        g.append(f'<text x="{x + 6:.1f}" y="{H - 4}" class="tk" fill="{REF}" font-weight="600">{esc(limit_label)}</text>')
    return svg(W, H, g)


def legend(items):
    return '<div class="lg">' + "".join(f'<span><i style="background:{c}"></i>{esc(t)}</span>' for t, c in items) + "</div>"


def table(headers, rows, left=1, cls="", focus_col=0):
    th = "".join(f'<th class="{"l" if i < left else ""}">{esc(h)}</th>' for i, h in enumerate(headers))
    body = []
    for r in rows:
        key = str(r[focus_col]).replace(MARK, "") if focus_col < len(r) else ""
        c = ' class="rbc"' if key == FOCUS else ' class="med"' if key in ("Median", "Peer median") else ""
        body.append(f"<tr{c}>" + "".join(f'<td class="{"l" if i < left else ""}">{esc(str(v))}</td>' for i, v in enumerate(r)) + "</tr>")
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def card(h2, inner, cap=None, style=""):
    c = f'<p class="cap">{cap}</p>' if cap else ""
    return f'<div class="card" style="{style}"><h2>{esc(h2)}</h2>{c}{inner}</div>'


def side(paras, w=330):
    return f'<div class="side" style="flex:0 0 {w}px">' + "".join(f"<p>{p}</p>" for p in paras) + "</div>"


def b(t):
    return f"<b>{esc(t)}</b>"


SLIDES = []


def slide(title, body, source, cls=""):
    SLIDES.append(dict(title=title, body=body, source=source, cls=cls))


def balls(v, s, higher=True):
    if pd.isna(v):
        return "–"
    s = s.dropna()
    q1, q2 = s.quantile(1 / 3), s.quantile(2 / 3)
    n = 3 if v >= q2 else (2 if v >= q1 else 1)
    if not higher:
        n = 4 - n
    return "●" * n + "○" * (3 - n)


pct1 = lambda v: f"{v:.1f}%"
pct0 = lambda v: f"{v:.0f}%"

# ================================================================= 1. Title
kpis = [
    ("RBC Life LICAT ratio", f"{rbc.capital_ratio_pct:.0f}%", f"peer median {med.capital_ratio_pct:.0f}%", True),
    ("Liability on its discount curve vs peer median", f"{liab_pct[FOCUS]:+.2f}%", f"C${liab[FOCUS]:+.0f}MM per C$10Bn", True),
    ("Private credit, % of general account", f"{rbc.private_credit_pct:.1f}%", f"peer median {med.private_credit_pct:.1f}%", True),
    ("Repos, % of portfolio", f"{rbc.repo_pct:.1f}%", f"next peer {next_repo['name']} {next_repo.repo_pct:.1f}%", True),
]
slide("Canadian life & health insurers: peer investment landscape",
      f'<div style="display:flex;flex-direction:column;gap:22px;width:100%">'
      f'<p class="lead">RBC Life against 19 peers: IFRS 17 discount curves, general-account portfolio composition and '
      f'investment risk (market, credit and liquidity).</p>'
      f'<div class="kpis">' + "".join(f'<div class="kpi rbc"><span>{esc(t)}</span><b>{esc(v)}</b><small>{esc(s)}</small></div>' for t, v, s, _ in kpis) + "</div>"
      f'<p class="cap" style="font-size:12px">Data as at year end 2025 and the latest 2026 filings (OSFI, AMF and annual reports). Prepared 28 October 2026 '
      f'with the financial-analysis plugin\'s competitive-analysis framework. <span class="chip">{MARK}RBC Life</span> is coloured, outlined and bold in every chart and table; '
      f'peers are grey and the dashed line or tick is the peer median.</p></div>',
      "Source: the three analyses in abiddobani/InsuranceCompanies (analysis/discount_curves, analysis/portfolio_composition, analysis/investment_risk), re-run 28 Oct 2026.",
      cls="title")

# ================================================================= 2. Executive summary
pts = [
    ("Scale and capital.", f"RBC Life is the {size_rank}th largest general account (C${rbc.portfolio_cad_mm / 1e3:.1f}Bn of {size_n}) but its "
     f"{rbc.capital_ratio_pct:.0f}% LICAT ratio is the {ORDINAL[cap_low]} of {cap_n}, {med.capital_ratio_pct - rbc.capital_ratio_pct:.0f} points under the {med.capital_ratio_pct:.0f}% median."),
    ("Discount curve.", f"Its IFRS 17 curve values liabilities {abs(liab_pct[FOCUS]):.2f}% below the peer median (C${abs(liab[FOCUS]):.0f}MM per C$10Bn), "
     f"inside a C${liab.max() - liab.min():.0f}MM range from iA (most generous) to Primerica (most conservative)."),
    ("Portfolio mix.", f"Public bonds dominate ({pcx.loc[FOCUS, 'Public fixed income']:.0f}%), private credit is {rbc.private_credit_pct:.1f}% "
     f"({pc_rank}th highest of {pc_n}) and alternatives are small ({pcx.loc[FOCUS, 'Alternatives (real estate, infra, PE, private debt)']:.1f}%)."),
    ("Concentrations.", f"{rbc.energy_pct_corp:.1f}% of corporate bonds are coded Energy (median {med.energy_pct_corp:.1f}%) and repos fund "
     f"{rbc.repo_pct:.1f}% of the portfolio, about {rbc.repo_pct / next_repo.repo_pct:.0f}x the next peer."),
    ("Par and disclosure.", f"RBC's filed par curve sits {par_gap_rbc} bp under its dividend scale rate, the widest gap; it publishes no market "
     f"sensitivities, while disclosing peers lose C${ear.total_cad_mm.min():.0f}–{ear.total_cad_mm.max():.0f}MM on a C$25Bn book in moderate shocks."),
]
big = [f"{rbc.capital_ratio_pct:.0f}%", f"{liab_pct[FOCUS]:+.2f}%", f"{pcx.loc[FOCUS, 'Public fixed income']:.0f}%", f"{rbc.energy_pct_corp:.1f}%", f"{par_gap_rbc} bp"]
sub_k = [f"LICAT ratio, {ORDINAL[cap_low]} of {cap_n}", "liability vs peer median curve", "of the general account in public bonds",
         "of corporate bonds coded Energy", "par curve below its dividend scale rate"]
slide("RBC Life runs a high-quality but thinly capitalised book, with two concentrations peers do not have",
      '<div class="grid5">' + "".join(f'<div class="card"><h2>{esc(h)}</h2><b class="num">{esc(n)}</b><small>{esc(k)}</small><p>{esc(t)}</p></div>'
                                      for (h, t), n, k in zip(pts, big, sub_k)) + "</div>",
      "Source: slides 3 to 20. Peer medians are taken across every insurer with the metric; scale is C$ general-account invested assets at each insurer's latest filing.")

# ================================================================= 3. Peer groups
size = pcx.portfolio_cad_mm / 1e3
tiers = [
    ("Big three groups", "Listed, global, OSFI", ["Manulife", "Sun Life", "Canada Life"]),
    ("Quebec and mutual leaders", "AMF; iA listed, Desjardins and Beneva cooperative / mutual", ["iA Financial", "Desjardins", "Beneva"]),
    ("Bank-owned", "OSFI, October fiscal year", ["RBC Life", "BMO Life"]),
    ("Mid-size", "OSFI; stock, mutual and Sagicor-owned", ["ivari", "Empire Life", "Equitable Life", "Co-operators Life", "Wawanesa Life"]),
    ("Niche and small", "OSFI, AMF, FCNB; fraternal, mutual, distribution-led",
     ["Foresters Life", "Canadian Premier", "Primerica Life", "Assumption Life", "UV Insurance", "Humania"]),
]
sz = LS.dropna(subset=["portfolio_cad_mm"]).sort_values("portfolio_cad_mm", ascending=False)
rows = []
for g, o, names in tiers:
    cells = "  ·  ".join((f"{label(n)} {size[n]:.1f}" if n in size.index and pd.notna(size[n]) else f"{n} n/d") for n in names)
    rows.append([g, o, cells])
tier_rows = "".join(
    f'<tr class="{"rbc" if "RBC Life" in names else ""}"><td class="l"><b>{esc(g)}</b></td><td class="l">{esc(o)}</td><td class="l">{esc(c)}</td></tr>'
    for (g, o, names), (_, _, c) in zip(tiers, rows))
slide("Twenty insurers in five strategic groups; RBC Life competes with BMO Life as the bank-owned pair",
      card("Peer set by ownership and regulator",
           f'<table class="roomy wrap big"><thead><tr><th class="l">Group</th><th class="l">Ownership / regulator</th><th class="l">Insurers (general account, C$Bn)</th></tr></thead><tbody>{tier_rows}</tbody></table>',
           "General-account size at each insurer's latest filing. Canada Protection Plan reports inside Foresters Life; Desjardins' life portfolio is not published apart from Desjardins Group (n/d).",
           style="flex:1")
      + card("General account, C$Bn", hbar([(n, v / 1e3) for n, v in zip(sz.name, sz.portfolio_cad_mm)], lambda v: f"{v:,.1f}" if v < 100 else f"{v:,.0f}",
                                            W=380, rowh=23, label_w=118, right_w=50, vmin=0),
             "Latest filing; Desjardins not published.", style="flex:0 0 412px"),
      "Source: OSFI, AMF and FCNB registers; general-account size from the portfolio composition analysis (mid-2026 for OSFI filers and listed groups, December 2025 for annual reporters).")

# ================================================================= 4. Positioning
pos = LS.dropna(subset=["capital_ratio_pct", "risk_assets_pct", "private_credit_pct"]).copy()
pos["x"] = pos.risk_assets_pct + pos.private_credit_pct
mx, my = pos.x.median(), pos.capital_ratio_pct.median()
POS = {"Wawanesa Life": "a", "Assumption Life": "r", "Canadian Premier": "l", "iA Financial": "l", "ivari": "b",
       "BMO Life": "l", "Co-operators Life": "b", "Equitable Life": "a", "Empire Life": "l", "Primerica Life": "r"}
sc_svg = scatter([(r["name"], r.x, r.capital_ratio_pct) for _, r in pos.iterrows()], (0, 65), (120, 215),
                 pct0, pct0, "Return-seeking assets (equity, real estate, PE and private credit), % of general account",
                 "LICAT / solvency ratio", mx, my, POS)
slide("Positioning: RBC Life takes median-level investment risk on a below-median capital buffer",
      card("Risk appetite against capital strength", sc_svg,
           "Each dot is one insurer at its latest capital ratio and general-account mix. Dashed lines are the peer medians.")
      + side([f"{b('Reading the map.')} The medians are {mx:.0f}% return-seeking assets and a {my:.0f}% capital ratio.",
              f"{b('RBC Life')} sits at {rbc.risk_assets_pct + rbc.private_credit_pct:.0f}% return-seeking assets and a {rbc.capital_ratio_pct:.0f}% ratio, "
              "in the lower-right quadrant with the big three and ivari: a similar risk appetite on a thinner buffer.",
              "Equitable Life takes the most risk (equities 36% of its book) but holds a 159% ratio; Foresters and Primerica hold the most capital on the least risk."]),
      "Source: LICAT total ratio from OSFI LCQ FY2025 Q4 (CARLI / solvency ratio for iA, Beneva, Assumption, Humania); asset mix from the portfolio composition analysis. UV Insurance and Desjardins publish no ratio.")

# ================================================================= 5. RBC profile
metric_rows = []
for col, name, hint, f, hi in [
    ("portfolio_cad_mm", "General account, C$Bn", None, lambda v: f"{v / 1e3:.1f}", True),
    ("capital_ratio_pct", "LICAT / solvency ratio", "higher is stronger", pct0, True),
    ("market_cap_pct_inv", "LICAT market capital, % invested", None, pct1, True),
    ("credit_cap_pct_inv", "LICAT credit capital, % invested", None, lambda v: f"{v:.2f}%", True),
    ("risk_assets_pct", "Equity, real estate, PE, % portfolio", None, pct1, True),
    ("private_credit_pct", "Private credit, % portfolio", None, pct1, True),
    ("below_ig_pct_bonds", "Below investment grade, % bonds", None, lambda v: f"{v:.2f}%", True),
    ("energy_pct_corp", "Energy, % corporate bonds", None, pct1, True),
    ("weighted_liquidity_pct", "Liquidity-weighted assets, %", "higher is more liquid", pct1, True),
    ("repo_pct", "Repos, % portfolio", None, pct1, True),
]:
    s = LS[["name", col]].dropna()
    metric_rows.append(dict(metric=name, hint=hint, values=list(zip(s.name, s[col])), fmt=f,
                            focus=None if pd.isna(rbc[col]) else rbc[col], median=s[col].median()))
metric_rows.append(dict(metric="Individual life 30y illiquidity premium", hint=None, fmt=lambda v: f"{v:.2f}%",
                        values=[(c, v) for c, v in il.lp_30y.items() if c != "Peer median"], focus=rbc_il.lp_30y, median=med_il.lp_30y))
qual = [["Business", "Royal Bank of Canada's life insurer: individual life, living benefits, group and individual annuities."],
        ["Strengths", "99.9% investment-grade bonds; 31.6% government bonds; near-zero credit losses (ECL 0.7 bp of invested assets)."],
        ["Weaknesses", f"LICAT {rbc.capital_ratio_pct:.0f}% vs {med.capital_ratio_pct:.0f}% median; 37.6% Energy coding; repos 14.1% of portfolio; no sensitivities published."],
        ["Posture", "Long-duration public bonds plus private placements (11.7%); little real estate or PE; derivative and repo overlay for ALM."]]
slide("RBC Life profile: fifth-largest book, investment-grade bonds, the thinnest disclosure in the peer set",
      card("Where RBC Life sits on each metric", dotstrip(metric_rows, W=800, rowh=44, label_w=300),
           "Each row is one metric on its own scale, from the lowest peer to the highest. Grey dots are the other peers, the tick is the peer median and the coloured dot is RBC Life.", style="flex:1")
      + f'<div class="side" style="flex:0 0 330px"><div class="card">{table(["Category", "Assessment"], qual, left=2, cls="roomy wrap big")}</div></div>',
      "Source: OSFI LCQ, LF2, LF3 for RBC Life Insurance Company (legal entity, fiscal year to 31 Oct 2025; portfolio at 31 Jul 2026); peers as on later slides. Metrics RBC Life does not publish are marked.")

# ================================================================= 6. Discount curves: liability vs median
d = DC.sort_values("liability_vs_median_per_10bn_mm")
slide(f"Discount curves: RBC Life is at the peer median; iA to Primerica spans C${liab.max() - liab.min():.0f}MM of liability per C$10Bn",
      card("Liability on each insurer's curve against the peer median curve, C$MM per C$10Bn",
           hbar([(n, v) for n, v in zip(d.name, d.liability_vs_median_per_10bn_mm)], lambda v: f"{v:+.0f}", W=820, rowh=25.5),
           "Negative = higher discount rates and a smaller liability (more generous); positive = more conservative. Stylised liability: payments falling 4% a year for 80 years.")
      + side([f"{b('RBC Life:')} {liab[FOCUS]:+.0f} ({liab_pct[FOCUS]:+.2f}%). Its forward-shaped curve runs above the median at 20 to 30 years "
              f"(30y premium {dc_rbc.lp_30y:.2f}%) and below it at 10 and 70+ years, which nets out.",
              f"{b('Manulife')} carries the highest 30y premium (2.05%) but the lowest ultimate risk-free rate (3.40%).",
              f"{b('Primerica, BMO Life, Equitable and Sun Life')} discount most conservatively, each more than C$280MM per C$10Bn above the median."]),
      "Source: OSFI LF2 pages P35035 to P35065 (most illiquid curve, individual non-par), Q4 2025; iA, Desjardins, Beneva and Assumption Life 2025 annual reports. Analysis: analysis/discount_curves.")

# ================================================================= 7. Curve shape and products
cv = PCV[(PCV.period == "2025Q4") & (PCV["product"] == "Individual life")]
series = {c: list(zip(g.tenor, g.dr)) for c, g in cv.groupby("company")}
annual = {"iA Financial", "Desjardins", "Beneva", "Assumption Life"}
prod_rows = []
for prod in ["Individual life", "Individual annuity", "Group annuity"]:
    pr = PP[(PP.period == "2025Q4") & (PP["product"] == prod)].set_index("company")
    prod_rows.append([prod, f"{pr.loc['RBC Life', 'dr_30y']:.2f}%", f"{pr.loc['Peer median', 'dr_30y']:.2f}%",
                      f"{pr.loc['RBC Life', 'lp_30y']:.2f}%", f"{pr.loc['Peer median', 'lp_30y']:.2f}%"])
slide("RBC Life's curve runs above the peer median at 20 to 30 years and below it at the long end",
      card("Individual life discount curves, year end 2025, spot rates",
           legend([("RBC Life", BLUE), ("Peer median", REF), ("OSFI filer", MUTED_BAR)]) +
           '<div class="lg"><span><i class="dash"></i>Annual report (one curve for all products)</span></div>' + curves(series, annual, W=770, H=420),
           "Most illiquid curve for non-participating individual insurance. RBC Life files rates with the shape of one-year forwards; they are compounded to spot (an interpretation, not stated by OSFI).")
      + f'<div class="side" style="flex:0 0 372px"><div class="card"><h2>30-year rate and premium by product</h2>'
        f'{table(["Product", "RBC rate", "Median", "RBC prem.", "Median"], prod_rows, left=1, cls="roomy tight")}</div>'
        f'<p>RBC files one curve for all its non-par lines, so its 30y rate ({rbc_il.dr_30y:.2f}%) and premium ({rbc_il.lp_30y:.2f}%) exceed the median for every product.</p>'
        f'<p>At 80 years RBC\'s spot rate is {rbc_il.dr_80y:.2f}% against a {med_il.dr_80y:.2f}% median; its filed ultimate forward rate is 4.10%.</p></div>',
      "Source: OSFI LF2 by line of business, Q4 2025 (fiscal Q4 2025 for RBC Life and BMO Life); annual reports for iA, Desjardins, Beneva and Assumption Life. Premiums for insurers without their own risk-free curve are measured over the median OSFI risk-free curve.")

# ================================================================= 8. Par vs DSIR
p = par_ye.sort_values("dsir_less_flat_bp", ascending=False)
par_rows = [dict(name=r["name"], flat=r.flat_equivalent, dsir=r.dsir) for _, r in p.iterrows()]
par_tbl = [[label(r["name"]), f"{r.flat_equivalent:.2f}%", f"{r.dsir:.2f}%", f"{r.dsir_less_flat_bp:+.0f}", fv(r.par_account_mm, "{:,.0f}")] for _, r in p.iterrows()]
slide(f"Par: dividend scale rates run {par_pos.min():.0f} to {par_pos.max():.0f} bp above filed par curves; RBC Life's {par_gap_rbc} bp gap is the widest",
      card("Filed par discount rate (flat-equivalent) against the 2025 dividend scale interest rate",
           legend([("Flat-equivalent par discount rate", REF), ("Dividend scale interest rate", RED)]) +
           dotpair(par_rows, [("flat", REF), ("dsir", RED)], lambda v: f"{v:.1f}%", W=560, rowh=37),
           "The flat-equivalent rate is the single rate giving the stylised liability the same value as the filed par curve. Ordered by the gap.")
      + f'<div class="side" style="flex:0 0 420px"><div class="card">{table(["Insurer", "Flat-equiv.", "DSIR", "Gap, bp", "Par account C$MM"], par_tbl, cls="roomy")}</div>'
        f'<p class="cap" style="font-size:11.5px">Equitable Life discounts par at its dividend scale rate (gap −2 bp). RBC\'s par account is small (C$51MM), so its gap matters more for disclosure than for its balance sheet. ivari, Wawanesa Life and Beneva publish no dividend scale rate.</p></div>',
      "Source: OSFI LF2 par curves, Q4 2025; annual-report curves for iA, Desjardins and Assumption Life; dividend scale interest rates 2025 from PolicyAdvisor's table, RBC Life and Equitable Life confirmed on their own sites; par account sizes from PolicyAdvisor 2026 and Co-operators' par report.")

# ================================================================= 9. Portfolio mix
pcs = PC.sort_values("portfolio_cad_mm", ascending=False)
pc_colors = [BLUE, ORANGE, TEAL, PINK, GREY]


def size_label(v, asof):
    d = pd.Timestamp(asof)
    s = f"C${v / 1e3:.0f}bn" if v >= 20000 else f"C${v / 1e3:.1f}bn" if v >= 1000 else f"C${v:.0f}MM"
    return f"{s} · {d.strftime('%b %Y')}"


pc_rows = [dict(name=r["name"], sub=size_label(r.portfolio_cad_mm, r.as_of), vals=[r[k] for k in L2]) for _, r in pcs.iterrows()]
slide(f"Portfolio: RBC Life is {pcx.loc[FOCUS, 'Public fixed income']:.0f}% public bonds with few alternatives; the big three and Equitable lean on private assets",
      card("Portfolio mix, % of general account", legend(list(zip(L2.keys(), pc_colors))) +
           stacked(pc_rows, pc_colors, W=1160, rowh=24.5, label_w=290, sub_w=138),
           "Largest portfolio first. General account only; segregated funds, asset-manager AUM, pass-through funds backing universal life, bank-funded loans and own-use property are excluded. Segments under about 5% are unlabelled; the next slide gives the sub-class detail.", style="flex:1"),
      "Source: OSFI LF2 P21012 / LF1 (OSFI filers, mid-2026); Q2 2026 supplements for Manulife, Sun Life, Great-West Lifeco and iA; 2025 annual reports for Beneva, UV, Humania and Assumption Life. Desjardins' life portfolio is not published. Analysis: analysis/portfolio_composition.")

# ================================================================= 10. Sub-class heatmap
sub = ["Corporate Bonds", "Government Bonds", "Asset Backed Securities", "Common Shares", "Preferred Shares", "Commercial Mortgages",
       "Illiquid Term Loans", "Policy & Other Loans", "Cash", "Real Estate Equity", "Infrastructure Equity", "Other Private Equity"]
comp = ["RBC Life", "BMO Life", "Canada Life", "iA Financial", "Empire Life", "Sun Life", "Manulife", "Equitable Life", "ivari"]
medsub = PC[sub].median()
vmax = max(pcx.loc[comp, sub].values.max(), 1)


def heat(v, bold=False):
    a = 0.06 + 0.62 * (v / vmax) if v > 0 else 0
    fg = "#fff" if a > 0.42 else INK
    return f'<td style="background:rgba(31,95,168,{a:.2f});color:{fg};{"font-weight:700" if bold else ""}">{v:.1f}</td>'


hm = ['<table class="heat"><thead><tr><th class="l">% of general account</th>' +
      "".join(f'<th class="{"rbc" if c == FOCUS else ""}">{esc(label(c))}</th>' for c in comp) + '<th>Median</th></tr></thead><tbody>']
for c in sub:
    nm = c.replace("Illiquid Term Loans", "Private placements / term loans")
    hm.append(f'<tr><td class="l">{esc(nm)}</td>' + "".join(heat(pcx.loc[n, c], n == FOCUS) for n in comp) + f'<td>{medsub[c]:.1f}</td></tr>')
hm.append("</tbody></table>")
slide("RBC Life overweights government bonds and public equity, and holds the least cash of the larger peers",
      card("Sub-class detail, % of general account (darker = larger share)", "".join(hm),
           "Nine largest peers with a sub-class split, RBC Life first. Median across all 18 charted insurers. Private placements are mapped to illiquid term loans; OSFI filers' ABS sit inside corporate bonds.", style="flex:1"),
      "Source: as previous slide. UV Insurance and Humania publish only summary statements and are not shown.")

# ================================================================= 11. Off balance sheet
ob = LS.dropna(subset=["derivative_notional_pct"]).sort_values("derivative_notional_pct", ascending=False)
rp = LS.dropna(subset=["repo_pct"]).sort_values("repo_pct", ascending=False)
rbc_obs = OBS[OBS.company_id == "rbc_life"]
OBS_LABEL = {("Encumbered Assets", "Repos"): "Repos", ("Currency", "FX forwards, futures, swaps, options"): "FX derivatives",
             ("Equity", "Linear and non-linear (not split)"): "Equity derivatives", ("Fixed Income", "Linear"): "Rate derivatives, linear",
             ("Fixed Income", "Non-Linear"): "Rate derivatives, non-linear"}
slide(f"RBC Life funds {rbc.repo_pct:.1f}% of its portfolio with repos, about {rbc.repo_pct / next_repo.repo_pct:.0f}x the next peer ({next_repo['name']}, {next_repo.repo_pct:.1f}%)",
      card("Repos, % of portfolio", hbar([(n, v) for n, v in zip(rp.name, rp.repo_pct)], pct1, W=400, rowh=36, label_w=120, right_w=56),
           "Securities sold under repurchase agreements at fiscal year end 2025.", style="flex:0 0 430px")
      + card("Derivative notional, % of portfolio", hbar([(n, v) for n, v in zip(ob.name, ob.derivative_notional_pct)], pct0, W=400, rowh=36, label_w=120, right_w=56),
             "All derivative notionals (currency, equity, rates, credit) over the general account.", style="flex:0 0 430px")
      + side([b("RBC Life, 31 Oct 2025 (C$MM)")] +
             [f"{OBS_LABEL.get((r.level2, r.level3), r.level3)}: {r.amount_cad_mm:,.0f} ({r.pct_of_portfolio * 100:.1f}%)" for _, r in rbc_obs.iterrows()] +
             ["Repos add leverage and a collateral call in a rate spike. Only iA (5.0%), Sun Life (1.4%) and Manulife (0.3%) report any; the other OSFI filers report none.",
              "Securities lending and ISN are not disclosed by any peer."], w=270),
      "Source: OSFI LF3 P21110 derivative notionals and P22030 row 280 repos, fiscal 2025 (legal entity); iA and Manulife financial statement notes. Annual-report insurers are not covered.")

# ================================================================= 12. Capital
lic = LS.dropna(subset=["capital_ratio_pct"]).sort_values("capital_ratio_pct", ascending=False)
osfi = LS.dropna(subset=["market_cap_pct_inv"]).sort_values("portfolio_cad_mm", ascending=False)
cap_rows = [dict(name=r["name"], mkt=r.market_cap_pct_inv, crd=r.credit_cap_pct_inv) for _, r in osfi.iterrows()]
slide(f"Capital: RBC Life's {rbc.capital_ratio_pct:.0f}% LICAT ratio is the {ORDINAL[cap_low]} of {cap_n}, {med.capital_ratio_pct - rbc.capital_ratio_pct:.0f} points below the {med.capital_ratio_pct:.0f}% median",
      card("Total capital ratio, %", hbar([(n, v) for n, v in zip(lic.name, lic.capital_ratio_pct)], pct0, W=600, rowh=24, vmin=0, vmax=230, median=med.capital_ratio_pct),
           "LICAT total ratio for OSFI filers; CARLI solvency ratio for iA, Beneva and Humania; Assumption Life's own solvency ratio.", style="flex:0 0 630px")
      + card("LICAT risk capital, % of invested assets", legend([("Market risk", BLUE), ("Credit risk", ORANGE)]) +
             dotpair(cap_rows, [("mkt", BLUE), ("crd", ORANGE)], pct0, W=480, rowh=27, label_w=124, step=2),
             "Non-participating business only, legal entity, fiscal 2025 Q4. Largest book first.", style="flex:1"),
      "Source: OSFI LCQ (LICAT summary and components D3000010077 / D5000010057), FY2025 Q4 (RBC Life, BMO Life: Oct 2025); AMF and annual reports for iA, Beneva, Assumption and Humania. Analysis: analysis/investment_risk.")

# ================================================================= 13. Credit
en = LS.dropna(subset=["energy_pct_corp"]).sort_values("energy_pct_corp", ascending=False)
credit_tbl = [["Below investment grade, % bonds", f"{rbc.below_ig_pct_bonds:.2f}", f"{med.below_ig_pct_bonds:.2f}"],
              ["BBB, % bonds", fv(rbc.bbb_pct_bonds), f"{med.bbb_pct_bonds:.1f}"],
              ["Private credit, % portfolio", f"{rbc.private_credit_pct:.1f}", f"{med.private_credit_pct:.1f}"],
              ["ECL allowance, bp of invested assets", f"{rbc.ecl_bps_inv:.1f}", f"{med.ecl_bps_inv:.1f}"],
              ["Problem mortgages, % of mortgages", f"{rbc.mortgage_problem_pct:.2f}", f"{med.mortgage_problem_pct:.2f}"],
              ["Largest sector, % corporate bonds", f"{rbc.top_sector} {rbc.top_sector_pct:.1f}", f"{med.top_sector_pct:.1f}"],
              ["LICAT credit capital, % invested", f"{rbc.credit_cap_pct_inv:.2f}", f"{med.credit_cap_pct_inv:.2f}"]]
slide(f"Credit: RBC Life's bonds are 99.9% investment grade, but {rbc.energy_pct_corp:.1f}% of its corporates are coded Energy, {rbc.energy_pct_corp / med.energy_pct_corp:.1f}x the median",
      card("Energy issuers, % of corporate bonds", hbar([(n, v) for n, v in zip(en.name, en.energy_pct_corp)], pct1, W=600, rowh=31, vmin=0, vmax=45, median=med.energy_pct_corp),
           "OSFI filers only (LF3 bonds by issuer sector). RBC Life files no Utilities line, so part of its Energy share may be sector coding.", style="flex:0 0 630px")
      + f'<div class="side" style="flex:1"><div class="card"><h2>Credit metrics, RBC Life against the peer median</h2>{table(["Metric", "RBC Life", "Median"], credit_tbl, cls="roomy big", focus_col=9)}</div>'
        f'<p>Manulife carries the most credit risk (4.0% below investment grade, 19 bp ECL); Sun Life the most problem mortgages (1.2%). RBC Life\'s private credit is almost all private placements and commercial mortgages.</p></div>',
      "Source: OSFI LF3 P21030 bonds by issuer sector and P21050 problem mortgages, LF2 P21020 expected credit losses (FY2025 Q4); rating splits from year-end 2025 annual reports (RBC Life publishes none).")

# ================================================================= 14. Liquidity
lq = LS.dropna(subset=["weighted_liquidity_pct"]).sort_values("weighted_liquidity_pct", ascending=False)
lq_rows = [dict(name=r["name"], vals=[r.liquid_tier1_pct, r.liquid_tier12_pct - r.liquid_tier1_pct, 100 - r.liquid_tier12_pct],
                total_label=f"{r.weighted_liquidity_pct:.0f}%") for _, r in lq.iterrows()]
slide(f"Liquidity: RBC Life's liquidity-weighted assets ({rbc.weighted_liquidity_pct:.0f}%) sit at the median ({med.weighted_liquidity_pct:.0f}%); the big three run the least liquid books",
      card("Liquidity tiers, % of general account, with the liquidity-weighted ratio at right",
           legend([("Cash and government bonds", BLUE), ("Other public bonds and shares", TEAL), ("Mortgages, private loans, real estate, PE", MUTED_BAR)]) +
           stacked(lq_rows, [BLUE, TEAL, MUTED_BAR], W=800, rowh=24, label_w=140, right_w=60),
           "Most liquid first by the weighted ratio. Weights after Doff's weighted liquidity ratio (illustrative): cash 100%, government bonds 95%, public corporates 85%, ABS and shares 70%, mortgages 50%, private debt 40%, real estate and PE 20%, policy loans 0%.")
      + side([f"{b('RBC Life vs median.')} Cash and government bonds (tier 1): {rbc.liquid_tier1_pct:.1f}% vs {med.liquid_tier1_pct:.1f}%. "
              f"All public, liquid assets: {rbc.liquid_tier12_pct:.1f}% vs {med.liquid_tier12_pct:.1f}%.",
              f"The weighted ratio ignores funding: the {rbc.repo_pct:.1f}% repo book draws on the same government bonds that make up RBC's liquid tier.",
              "Only Manulife (60%) and Great-West Lifeco (51%) publish their own liquid-asset measure."]),
      "Source: latest general-account mix from the portfolio composition analysis; tier weights from R. Doff, Investment risks: market, credit and liquidity risk (Risk.net).")

# ================================================================= 15. Earnings at risk
ear_rows = [dict(name=FOCUS, vals=[], none=True)] + [
    dict(name=r["name"], vals=[r.rates_cad_mm, r.spreads_cad_mm, r.equity_cad_mm, r.alts_cad_mm], total=r.total_cad_mm,
         total_label=f"C${r.total_cad_mm:,.0f}MM") for _, r in ear.iterrows()]
for r in ear_rows[1:]:
    r["vals"] = [0 if pd.isna(v) else v for v in r["vals"]]
slide(f"Market risk: moderate shocks cost disclosing peers C${ear.total_cad_mm.min():.0f} to {ear.total_cad_mm.max():.0f}MM on a C$25Bn book; RBC Life publishes no sensitivities",
      card("Earnings at risk on a C$25Bn portfolio",
           legend([("Rates (worse of ±50 bp)", BLUE), ("Credit spreads +50 bp", ORANGE), ("Public equity −10%", TEAL), ("Real estate and alternatives −10%", RED)]) +
           stacked(ear_rows, [BLUE, ORANGE, TEAL, RED], W=820, rowh=33, label_w=130, right_w=90, pct=False, limit=limit_25,
                   limit_label=f"Limit C${limit_25:.0f}MM", tick_fmt=lambda v: f"C${v:.0f}MM", min_label_w=1e9),
           "Each peer's disclosed net income loss under each shock, divided by its invested assets and multiplied by C$25Bn, then added up. Undiversified: shocks are applied one at a time and a gain counts as zero. Fewer than four parts means the factor is not disclosed.")
      + side([f"{b('Peer median')} C${ear_med:.0f}MM. Equity and alternatives drive the large groups; rates drive Wawanesa, Empire and Foresters.",
              f"The dashed line is a C$35MM earnings limit on C$28Bn, pro-rated to C${limit_25:.0f}MM on C$25Bn. Only Assumption Life's disclosed shocks fit inside it.",
              "After tax where disclosed; Empire and Wawanesa report profit or loss without saying, Foresters' figures are pre-tax and derived from its notes.",
              "RBC Life, BMO Life, ivari, Co-operators Life, Canadian Premier and Primerica publish no sensitivities."]),
      "Source: year-end 2025 MD&A and financial statement sensitivity notes, scaled to C$25Bn of invested assets; ±100 bp and −15% shocks scaled linearly. Detail: analysis/investment_risk/disclosed_sensitivities.csv.")

# ================================================================= 16-17. Scorecard
sc = LS.merge(DC[["company_id", "liability_vs_median_pct"]], on="company_id", how="left")
sc = sc.merge(EAR[["company_id", "total_cad_mm"]], on="company_id", how="left")
sc = sc.sort_values("portfolio_cad_mm", ascending=False, na_position="last")
dims = [("portfolio_cad_mm", "Scale, C$Bn", lambda v: f"{v / 1e3:.1f}"), ("capital_ratio_pct", "Capital ratio", pct0),
        ("liability_vs_median_pct", "Curve vs median", lambda v: f"{v:+.1f}%"), ("risk_assets_pct", "Equity, RE, PE", pct0),
        ("private_credit_pct", "Private credit", pct0), ("weighted_liquidity_pct", "Liquidity", pct0),
        ("total_cad_mm", "EaR, C$MM", lambda v: f"{v:.0f}")]


def score_rows(df):
    out = []
    for _, r in df.iterrows():
        out.append([label(r["name"])] + ["–" if pd.isna(r[c]) else f"{balls(r[c], sc[c])} {f(r[c])}" for c, _, f in dims])
    return out


SC_NOTE = ("●●● = top third of peers on that metric by value, ●○○ = bottom third; a rating is a position, not a judgement. Curve vs median: liability on own "
           "curve against the peer median (negative = more generous). EaR: undiversified earnings at risk on C$25Bn (slide 15). – = not available.")
for chunk, ttl in [(sc.iloc[:10], "Scorecard (1/2): among the ten largest books, only Canada Life and ivari hold less capital than RBC Life"),
                   (sc.iloc[10:], "Scorecard (2/2): smaller peers hold more capital and liquidity; Wawanesa Life carries the most earnings at risk (C$336MM)")]:
    slide(ttl, card("Peer scorecard, largest general account first",
                    table(["Insurer"] + [d[1] for d in dims], score_rows(chunk), cls="roomy score"), SC_NOTE, style="flex:1"),
          "Source: slides 6, 9, 12, 14 and 15; capital ratios as on slide 12.")

# ================================================================= 18. Strategic context
deals = [["UV Insurance", "~200k BMO Life policies (incl. ~15k par)", "Jun 2025", "~C$50MM premiums", "n/d", "Assumption reinsurance; doubled UV's members, assets +35%"],
         ["Sagicor Financial", "ivari (from Wilton Re)", "Oct 2023", "C$375MM", "n/d", "Canadian platform for a TSX-listed Caribbean group"],
         ["SSQ + La Capitale", "Merger, now Beneva", "Jan 2020", "n/a (mutual)", "n/a", "Scale: Canada's largest mutual insurer"],
         ["Great-West Life", "London Life, Canada Life amalgamated", "Jan 2020", "n/a (internal)", "n/a", "One Canada Life brand and balance sheet"],
         ["Foresters Financial", "Canada Protection Plan", "2017", "n/d", "n/d", "No-medical / simplified issue distribution"]]
slide("Consolidation is reshaping the tail of the peer set; bank-owned insurers are pruning non-core blocks",
      card("Transactions among the peer set", table(["Acquirer", "Target", "Date", "Deal value", "Multiple", "Rationale"], deals, left=6, cls="roomy wrap big", focus_col=9),
           "Deal multiples are not disclosed for any of these transactions (n/d).", style="flex:1")
      + side([f"{b('For RBC Life.')} BMO's 2025 sale shows a bank-owned insurer exiting a closed block, a route to release capital if the {rbc.capital_ratio_pct:.0f}% LICAT ratio becomes binding.",
              "UV Insurance's assets grew 35% on the block; its general account is now C$2.4Bn, larger than Wawanesa Life's.",
              "Sagicor's purchase of ivari added a Canadian book that now runs the highest public-equity share in the peer set (34%)."]),
      "Source: Insurance Portal (9 Jun 2025); Sagicor press release (3 Oct 2023); Beneva and Canada Life announcements (Jan 2020); Insurance Business (Foresters and CPP).")

# ================================================================= 19. Moat
moat = [["Big three", "Strong: 19 to 38% private credit, own origination", "Strong: large par and annuity in-force", "Strong: global brands", "Weak"],
        ["iA, Desjardins, Beneva", "Moderate: 15.5% private credit at iA", "Moderate", "Strong in Quebec", "Weak"],
        [MARK + "Bank-owned (RBC, BMO)", "Moderate: RBC 19.4% private credit; BMO 2.8%", "Weak: small par (C$51MM at RBC)", "Strong: bank brand and branch distribution", "Weak"],
        ["Mid-size", "Weak: rely on public markets and equities", "Moderate: Equitable par 42% of liabilities", "Moderate", "Weak"],
        ["Niche and small", "Weak: 0 to 22% private assets", "Weak", "Niche distribution (Primerica, CPP)", "Weak"]]
moat_html = table(["Group", "Scale economies", "Switching costs", "Intangible assets", "Network effects"], moat, left=5, cls="roomy wrap big", focus_col=9)
moat_html = moat_html.replace(f'<tr><td class="l">{esc(MARK)}Bank-owned', f'<tr class="rbc"><td class="l">{esc(MARK)}Bank-owned')
slide("Scale is the clearest durable investment advantage: the big three originate private assets peers cannot",
      card("Moat assessment by strategic group", moat_html,
           "Rated on the metrics in this deck: private credit and alternatives shares (scale), par and annuity in-force (switching costs), brand and bank distribution (intangibles). Network effects do not apply to investment portfolios and are rated Weak throughout.", style="flex:1"),
      "Source: slides 3, 8, 9 and 12. The ratings are assessments built on disclosed metrics, not disclosed figures.")

# ================================================================= 20. Synthesis
def tline(series, signpost, W=560, H=170):
    """Small line chart by quarter: series = {name: [(q, v)]}, drawn in order; RBC Life coloured."""
    qs = sorted({q for s in series.values() for q, _ in s})
    vals = [v for s in series.values() for _, v in s] + [signpost]
    y0, y1 = math.floor(min(vals) / 10) * 10 - 5, math.ceil(max(vals) / 10) * 10 + 5
    m = (10, 150, 24, 40)
    sx = lambda q: m[3] + qs.index(q) / (len(qs) - 1) * (W - m[1] - m[3])
    sy = lambda v: H - m[2] - (v - y0) / (y1 - y0) * (H - m[0] - m[2])
    g = []
    for t in range(int(y0 + 5), int(y1), 10):
        g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="{GRID}"/>')
        g.append(f'<text x="{m[3] - 6}" y="{sy(t) + 4:.1f}" text-anchor="end" class="tk">{t}%</text>')
    for q in qs:
        if q.endswith("Q4"):
            g.append(f'<text x="{sx(q):.1f}" y="{H - m[2] + 14}" text-anchor="middle" class="tk">Q4 {q[:4]}</text>')
    g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{sy(signpost):.1f}" y2="{sy(signpost):.1f}" stroke="{RED}" stroke-dasharray="4 3"/>')
    g.append(f'<text x="{W - m[1] + 8}" y="{sy(signpost) + 4:.1f}" class="tk" fill="{RED}">Signpost {signpost}%</text>')
    for name, pts in series.items():
        col, w = (BLUE, 2.8) if name == FOCUS else (REF, 2)
        d = " ".join(f"{'M' if i == 0 else 'L'}{sx(q):.1f},{sy(v):.1f}" for i, (q, v) in enumerate(pts))
        g.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{w}"/>')
        g.append(f'<text x="{W - m[1] + 8}" y="{sy(pts[-1][1]) + 4:.1f}" class="lb" font-weight="700" fill="{col}">{esc(name)} {pts[-1][1]:.0f}%</text>')
    return svg(W, H, g)


lh = LIC_H[LIC_H.company_id != "industry_total"].copy()
lh["q"] = lh.fiscal_year.astype(str) + lh.quarter
lh[tot_col] = pd.to_numeric(lh[tot_col], errors="coerce")
bsb_col = [c for c in lh.columns if c.startswith("Base Solvency Buffer")][0]
lh[bsb_col] = pd.to_numeric(lh[bsb_col], errors="coerce")
lh = lh.sort_values(bsb_col, ascending=False).drop_duplicates(["company_id", "q"])   # one entity per insurer
lh = lh[lh.q >= "2023Q4"]
cnt = lh.groupby("q").company_id.nunique()
med_q = lh[lh.q.isin(cnt[cnt >= 10].index)].groupby("q")[tot_col].median().sort_index()
rbc_q = lh[lh.company_id == "rbc_life"].set_index("q")[tot_col].sort_index()
traj_svg = tline({"OSFI peer median": list(med_q.items()), FOCUS: list(rbc_q.items())}, 125)
cols3 = [("Durable advantages", ["99.9% investment-grade bonds; ECL 0.7 bp", "Discount curve at the peer median: reserves neither aggressive nor conservative",
                                 "Bank brand and distribution (intangible)"], ""),
         ("Structural vulnerabilities", [f"LICAT {rbc.capital_ratio_pct:.0f}%, {ORDINAL[cap_low]}; {med.capital_ratio_pct - rbc.capital_ratio_pct:.0f} points under median",
                                        f"Repos {rbc.repo_pct:.1f}% of portfolio; Energy {rbc.energy_pct_corp:.1f}% of corporates",
                                        f"No sensitivities published; par curve {par_gap_rbc} bp under DSIR"], "warn"),
         ("Signposts to watch", ["LICAT ratio below 125%", "Repos above 15% of portfolio or Energy above 40% of corporates",
                                 "30y premium more than 50 bp above the peer median (+35 bp at YE2025)"], "")]
traj = (f"RBC Life's LICAT ratio has held at {lic_rbc.loc['2024Q1':].min():.0f} to {lic_rbc.loc['2024Q1':].max():.0f}% since fiscal 2024 "
        f"({lic_rbc['2026Q3']:.1f}% at fiscal Q3 2026), so the capital gap to peers is structural, not cyclical. Its 30y premium lead over the median "
        f"narrowed from +35 bp at year end 2025 to {gap_now:+.0f} bp at Q3 2026.")
slide("For RBC Life: defend the clean credit book, fix the capital buffer, and explain the two concentrations",
      '<div style="display:flex;flex-direction:column;gap:14px;width:100%;height:100%"><div style="display:flex;gap:16px;flex:1">' +
      "".join(f'<div class="card {c}" style="flex:1"><h2>{esc(h)}</h2><ul>' + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul></div>" for h, items, c in cols3) +
      f'</div><div class="card"><h2>Trajectory: LICAT total ratio by quarter, RBC Life against the OSFI peer median</h2>'
      f'<div style="display:flex;gap:18px;align-items:center"><p style="margin:0;font-size:14px;line-height:1.5;flex:1">{esc(traj)}</p>{traj_svg}</div></div></div>',
      "Source: synthesis of slides 2 to 19; LICAT history from OSFI LCQ (one entity per insurer, fiscal quarters; RBC Life's fiscal Q3 2026 ends July 2026). Quantified signposts are proposals for monitoring, not targets set by RBC Life.")

# ================================================================= 21. Method
meth_l = [("Discount curves", "Most illiquid curve (OSFI LF2 collects only that bucket); premiums for RBC Life and annual-report insurers measured over the median OSFI risk-free curve. 2023Q1 excluded (unit errors)."),
          ("Par", "Dividend scale interest rate used as the par discount rate; ivari, Wawanesa Life and Beneva publish none."),
          ("Portfolio composition", "General account only; par excluded only for Canada Life and Assumption Life (the only peers that split it). Beneva includes P&C. Level 1 assigned by asset class.")]
meth_r = [("Investment risk", "LICAT market and credit capital cover non-par business only, legal entity. Big-three sensitivities are group-wide (Canada Life = Great-West Lifeco incl. Empower). Liquidity weights are illustrative."),
          ("Gaps", "Humania and UV publish no curve. Desjardins publishes no portfolio or capital ratio. Canada Protection Plan sits in Foresters. RBC's forward-rate reading and Energy coding are unconfirmed."),
          ("Reproducibility", "All figures re-run on 28 Oct 2026 from the scripts in the repository; outputs match the earlier dashboards exactly.")]
mk = lambda items: "".join(f"<h3>{esc(h)}</h3><p>{esc(t)}</p>" for h, t in items)
slide("Method, coverage and caveats",
      f'<div class="card meth" style="flex:1">{mk(meth_l)}</div><div class="card meth" style="flex:1">{mk(meth_r)}</div>',
      "Code and data: abiddobani/InsuranceCompanies, analysis/discount_curves, analysis/portfolio_composition, analysis/investment_risk, analysis/summary_deck.")

# ---------------------------------------------------------------- HTML document
CSS = f"""
@page {{ size: 1280px 720px; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #fff; }}
body {{ font-family: Inter, "Helvetica Neue", Arial, "Liberation Sans", sans-serif; color: {INK}; font-size: 12.5px; line-height: 1.4; }}
.slide {{ position: relative; width: 1280px; height: 720px; padding: 30px 44px 0; overflow: hidden; break-after: page; }}
.slide:last-child {{ break-after: auto; }}
h1 {{ font-family: Georgia, "Liberation Serif", "DejaVu Serif", serif; font-weight: 400; font-size: 25px; line-height: 1.22; margin: 0; max-width: 1160px; letter-spacing: -0.005em; }}
.slide.title h1 {{ font-size: 40px; max-width: 1000px; margin-top: 120px; }}
.body {{ position: absolute; top: 108px; left: 44px; width: 1192px; height: 552px; display: flex; gap: 16px; align-items: flex-start; }}
.body.fill {{ align-items: stretch; }}
.slide.title .body {{ top: 290px; height: 370px; }}
.foot {{ position: absolute; left: 44px; right: 44px; bottom: 16px; display: flex; justify-content: space-between; gap: 30px; font-size: 10.5px; color: {SUB}; line-height: 1.35; }}
.foot .pg {{ flex: 0 0 auto; }}
.card {{ background: #fff; border: 1px solid #e1e4e8; border-radius: 6px; padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; min-width: 0; }}
.card.warn {{ background: #fff8ee; border-color: #f0d9b5; }}
.card h2 {{ font-size: 14px; font-weight: 600; margin: 0; }}
.card h3 {{ font-size: 13px; font-weight: 600; margin: 6px 0 0; }}
.card.meth p {{ margin: 3px 0 12px; font-size: 14px; line-height: 1.5; }}
.card.meth h3 {{ font-size: 14.5px; }}
.cap {{ font-size: 11px; color: {SUB}; line-height: 1.4; margin: 0; }}
.lead {{ font-size: 18px; line-height: 1.4; margin: 0; max-width: 1000px; color: {INK}; }}
.side {{ display: flex; flex-direction: column; gap: 10px; font-size: 12.5px; line-height: 1.45; min-width: 0; }}
.side p {{ margin: 0; }}
.side .card {{ margin-bottom: 2px; }}
ul {{ margin: 4px 0 0; padding-left: 18px; }}
li {{ margin: 0 0 7px; }}
.grid5 {{ display: grid; grid-template-columns: repeat(3, 1fr); grid-auto-rows: 1fr; gap: 14px; width: 100%; height: 100%; }}
.grid5 .card {{ gap: 2px; padding: 14px 16px; }}
.grid5 .card h2 {{ font-size: 15px; }}
.grid5 .num {{ font-size: 38px; font-weight: 600; color: {BLUE}; letter-spacing: -0.01em; line-height: 1.15; margin-top: 4px; }}
.grid5 small {{ font-size: 11.5px; color: {SUB}; margin-bottom: 6px; }}
.grid5 p {{ margin: 0; font-size: 14px; line-height: 1.5; }}
.card ul li {{ font-size: 14.5px; line-height: 1.45; margin-bottom: 12px; }}
.lg {{ display: flex; flex-wrap: wrap; gap: 3px 14px; font-size: 11px; color: {INK}; margin: 0; }}
.lg i {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px; vertical-align: -1px; margin-right: 5px; }}
.lg i.dash {{ width: 18px; height: 2px; border-radius: 0; vertical-align: 2px; background: repeating-linear-gradient(90deg, {MUTED_BAR} 0 4px, transparent 4px 7px); }}
.chip {{ display: inline-block; border: 1.5px solid {INK}; border-radius: 4px; padding: 0 5px; font-weight: 700; color: {BLUE}; }}
.kpis {{ display: flex; gap: 14px; }}
.kpi {{ flex: 1; border: 1px solid #e1e4e8; border-radius: 6px; padding: 12px 14px; }}
.kpi span {{ font-size: 12px; color: {SUB}; display: block; min-height: 34px; }}
.kpi b {{ display: block; font-size: 30px; font-weight: 600; margin: 4px 0 2px; letter-spacing: -0.01em; }}
.kpi.rbc b {{ color: {BLUE}; }}
.kpi small {{ font-size: 11.5px; color: {SUB}; }}
table {{ border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; font-size: 12px; }}
th {{ font-weight: 600; color: {SUB}; text-align: right; border-bottom: 1px solid #9aa0a8; padding: 5px 7px; font-size: 11px; vertical-align: bottom; }}
td {{ text-align: right; padding: 5px 7px; border-bottom: 1px solid {GRID}; white-space: nowrap; vertical-align: middle; }}
th.l, td.l {{ text-align: left; }}
table.wrap td {{ white-space: normal; }}
table.roomy td {{ padding: 7px 8px; }}
table.roomy.wrap td {{ padding: 8px 9px; line-height: 1.35; }}
table.big {{ font-size: 13px; }}
table.big td {{ padding: 11px 9px; }}
tr.rbc td {{ background: {FOCUS_BG}; font-weight: 700; }}
tr.med td {{ font-weight: 700; border-bottom: 1px solid #9aa0a8; }}
table.tight td, table.tight th {{ padding: 7px 5px; }}
table.score td {{ padding: 10px 8px; font-size: 13px; }}
table.score td:not(.l) {{ text-align: center; }}
table.score th:not(.l) {{ text-align: center; }}
table.heat td {{ text-align: center; padding: 9px 6px; border-bottom: 1px solid #fff; font-size: 12.5px; }}
table.heat th {{ text-align: center; }}
table.heat th.rbc {{ color: {BLUE}; font-weight: 700; }}
table.heat td.l {{ text-align: left; background: #fff; }}
svg text {{ font-family: Inter, "Helvetica Neue", Arial, sans-serif; fill: {INK}; }}
svg text.tk {{ font-size: 10.5px; fill: {SUB}; }}
svg text.lb {{ font-size: 12px; }}
svg text.sl {{ font-size: 11px; fill: {INK}; }}
svg text.vl {{ font-size: 11.5px; }}
svg text.sg {{ font-size: 10.5px; fill: #fff; font-weight: 600; }}
"""

pages = []
for i, s in enumerate(SLIDES, start=1):
    pages.append(f'<section class="slide {s["cls"]}"><h1>{esc(s["title"])}</h1><div class="body" data-shot="{i:02d}">{s["body"]}</div>'
                 f'<div class="foot"><span>{esc(s["source"])}</span><span class="pg">{i} / {len(SLIDES)}</span></div></section>')
DOC = f'<!doctype html><html><head><meta charset="utf-8"><title>Peer investment landscape</title><style>{CSS}</style></head><body>{"".join(pages)}</body></html>'

NODE = """
const { chromium } = require('playwright');
(async () => {
  const [html, pdf, shots] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2 });
  await p.goto('file://' + html);
  await p.evaluate(() => document.fonts.ready);
  await p.pdf({ path: pdf, width: '1280px', height: '720px', printBackground: true, preferCSSPageSize: true,
                margin: { top: 0, right: 0, bottom: 0, left: 0 } });
  for (const el of await p.$$('[data-shot]')) {
    await el.screenshot({ path: shots + '/' + (await el.getAttribute('data-shot')) + '.png' });
  }
  await b.close();
})();
"""

with tempfile.TemporaryDirectory() as tmp:
    html_path = os.path.join(tmp, "deck.html")
    js_path = os.path.join(tmp, "print.js")
    shots = os.path.join(tmp, "shots")
    os.makedirs(shots)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(DOC)
    with open(js_path, "w") as f:
        f.write(NODE)
    subprocess.run(["node", js_path, html_path, str(PDF_OUT), shots], check=True)
    if os.environ.get("KEEP_HTML"):
        import shutil
        shutil.copy(html_path, os.environ["KEEP_HTML"])

    # ---------------------------------------------------------------- pptx: native title and source, body as image
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    PX = 1 / 96  # CSS px to inches at the slide's 1280 px width
    for i, s in enumerate(SLIDES, start=1):
        sl = prs.slides.add_slide(prs.slide_layouts[6])
        is_title = s["cls"] == "title"
        tb = sl.shapes.add_textbox(Inches(44 * PX), Inches((150 if is_title else 30) * PX), Inches(1160 * PX), Inches((110 if is_title else 70) * PX))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = MSO_ANCHOR.TOP
        r = tf.paragraphs[0].add_run()
        r.text = s["title"]
        r.font.name, r.font.size, r.font.bold = "Georgia", Pt(30 if is_title else 19), False
        r.font.color.rgb = RGBColor(0x1F, 0x23, 0x29)
        top = 290 if is_title else 108
        sl.shapes.add_picture(os.path.join(shots, f"{i:02d}.png"), Inches(44 * PX), Inches(top * PX), width=Inches(1192 * PX))
        ft = sl.shapes.add_textbox(Inches(44 * PX), Inches(676 * PX), Inches(1120 * PX), Inches(30 * PX))
        ft.text_frame.word_wrap = True
        ft.text_frame.margin_left = ft.text_frame.margin_right = ft.text_frame.margin_top = 0
        r = ft.text_frame.paragraphs[0].add_run()
        r.text = s["source"]
        r.font.name, r.font.size = "Arial", Pt(8)
        r.font.color.rgb = RGBColor(0x5D, 0x64, 0x70)
        pg = sl.shapes.add_textbox(Inches(1180 * PX), Inches(676 * PX), Inches(56 * PX), Inches(30 * PX))
        pg.text_frame.paragraphs[0].alignment = PP_ALIGN.RIGHT
        r = pg.text_frame.paragraphs[0].add_run()
        r.text = f"{i} / {len(SLIDES)}"
        r.font.name, r.font.size = "Arial", Pt(8)
        r.font.color.rgb = RGBColor(0x5D, 0x64, 0x70)
    prs.save(PPTX_OUT)
print("wrote", PDF_OUT, "and", PPTX_OUT, "slides:", len(SLIDES))
