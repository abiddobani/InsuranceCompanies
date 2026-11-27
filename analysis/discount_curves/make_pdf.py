"""Print the by-product discount curve landscape (dashboard tab "By product line") as a landscape PDF.

    python3 analysis/discount_curves/make_pdf.py [period] [out.pdf]

Reads the CSVs written by build.py, draws the charts as inline SVG and prints with the preinstalled Playwright
Chromium (node). Defaults: year end 2025, analysis/discount_curves/discount_curve_landscape.pdf.
"""
import csv
import html
import os
import statistics
import subprocess
import sys
import tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.join(HERE, "dashboard")
PERIOD = sys.argv[1] if len(sys.argv) > 1 else "2025Q4"
OUT = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(HERE, "discount_curve_landscape.pdf")

RBC, MED = "RBC Life", "Peer median"
C_RBC, C_MED, C_OTHER, C_GRID, C_INK, C_MUTED = "#0051a5", "#1f1f1f", "#b9bec7", "#e6e8ec", "#1f2329", "#5d6470"
C_PROD = {"ann": "#d97a1e", "life": "#2a9d8f", "par": "#8e5bb5"}
TENORS = [5, 10, 20, 30, 80]


def read(name):
    with open(os.path.join(DASH, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def label(p):
    return f"Q{p[-1]} {p[:4]}"


def as_at(r):
    return ("Fiscal " if r["as_at"].startswith("Oct") else "") + label(r["period"])


def mm(v):
    v = num(v)
    return "—" if v is None else f"{v:,.0f}" if v >= 100 else f"{v:.1f}"


def f2(v):
    v = num(v)
    return "—" if v is None else f"{v:.2f}"


def by_size(rows, key, tie):
    def k(r):
        s, t = num(r.get(key)), num(r.get(tie))
        return (r["company"] != MED, -(s if s is not None else -1), -(t if t is not None else -1e9))
    return sorted(rows, key=k)


esc = html.escape

points = [r for r in read("product_points.csv")]
curves = read("product_curves.csv")
par = [r for r in read("par_vs_dividend_rate.csv") if r["view"] == "Year end 2025"]
source_of = {(r["company"], r["period"], r["product"]): r["source"] for r in points}


# ---------- SVG helpers ----------
def axes(W, H, m, x0, x1, y0, y1, xticks, yticks, xfmt=str, yfmt=lambda v: f"{v:.1f}%"):
    sx = lambda v: m[3] + (v - x0) / (x1 - x0) * (W - m[1] - m[3])
    sy = lambda v: H - m[2] - (v - y0) / (y1 - y0) * (H - m[0] - m[2])
    g = []
    for t in yticks:
        g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="{C_GRID}"/>')
        g.append(f'<text x="{m[3] - 6}" y="{sy(t) + 3.5:.1f}" text-anchor="end" class="tk">{yfmt(t)}</text>')
    for t in xticks:
        g.append(f'<text x="{sx(t):.1f}" y="{H - m[2] + 14}" text-anchor="middle" class="tk">{xfmt(t)}</text>')
    g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{H - m[2]}" y2="{H - m[2]}" stroke="{C_MUTED}"/>')
    return sx, sy, g


def nice(lo, hi, step):
    import math
    return math.floor(lo / step) * step, math.ceil(hi / step) * step


def curve_chart(product, W=520, H=420):
    rows = [r for r in curves if r["period"] == PERIOD and r["product"] == product]
    series = defaultdict(list)
    for r in rows:
        series[r["company"]].append((int(r["tenor"]), float(r["dr"])))
    vals = [v for s in series.values() for _, v in s]
    y0, y1 = nice(min(vals) - 0.1, max(vals) + 0.1, 0.5)
    m = (12, 92, 24, 44)
    sx, sy, g = axes(W, H, m, 0, 80, y0, y1, [1, 10, 20, 30, 40, 50, 60, 70, 80],
                     [y0 + i * 0.5 for i in range(int((y1 - y0) / 0.5) + 1)])
    order = sorted(series, key=lambda c: (c == MED, c == RBC))
    labels = []
    for c in order:
        pts = sorted(series[c])
        d = " ".join(f"{'M' if i == 0 else 'L'}{sx(t):.1f},{sy(v):.1f}" for i, (t, v) in enumerate(pts))
        ar = source_of.get((c, PERIOD, product), "").startswith("Annual report")
        col, w = (C_RBC, 2.6) if c == RBC else (C_MED, 2.2) if c == MED else (C_OTHER, 1.2)
        dash = ' stroke-dasharray="4 3"' if ar and c not in (RBC, MED) else ""
        g.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{w}"{dash}/>')
        if c in (RBC, MED):
            labels.append([sy(pts[-1][1]), c, col])
    labels.sort()
    for i in range(1, len(labels)):
        if labels[i][0] - labels[i - 1][0] < 12:
            labels[i][0] = labels[i - 1][0] + 12
    for y, c, col in labels:
        g.append(f'<text x="{W - m[1] + 6}" y="{y + 4:.1f}" class="lb" fill="{col}">{esc(c)}</text>')
    g.append(f'<text x="{(W - m[1] + m[3]) / 2}" y="{H - 2}" text-anchor="middle" class="tk">Tenor (years)</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}">{"".join(g)}</svg>'


def dot_chart(rows, fields, W=470, rowh=20, fmt=lambda v: f"{v:.1f}%", step=0.5, legend=None):
    rows = [r for r in rows if any(num(r.get(f)) is not None for f, _, _ in fields)]
    vals = [num(r.get(f)) for r in rows for f, _, _ in fields if num(r.get(f)) is not None]
    x0, x1 = nice(min(vals) - 0.05, max(vals) + 0.05, step)
    H = len(rows) * rowh + 40
    m = (8, 16, 26, 118)
    sx = lambda v: m[3] + (v - x0) / (x1 - x0) * (W - m[1] - m[3])
    g = []
    t = x0
    while t <= x1 + 1e-9:
        g.append(f'<line x1="{sx(t):.1f}" x2="{sx(t):.1f}" y1="{m[0]}" y2="{H - m[2]}" stroke="{C_GRID}"/>')
        g.append(f'<text x="{sx(t):.1f}" y="{H - m[2] + 13}" text-anchor="middle" class="tk">{fmt(t)}</text>')
        t += step
    for i, r in enumerate(rows):
        y = m[0] + i * rowh + rowh / 2
        c = r["company"]
        col = C_RBC if c == RBC else C_MED if c == MED else C_INK
        wt = ' font-weight="700"' if c in (RBC, MED) else ""
        if c == RBC:
            g.append(f'<rect x="0" y="{y - rowh / 2:.1f}" width="{W}" height="{rowh}" fill="#e8f0fa"/>')
        g.append(f'<text x="{m[3] - 8}" y="{y + 4:.1f}" text-anchor="end" class="lb" fill="{col}"{wt}>{esc(c)}</text>')
        vs = [(num(r.get(f)), colr, nm) for f, colr, nm in fields if num(r.get(f)) is not None]
        if len(vs) > 1:
            lo, hi = min(v for v, _, _ in vs), max(v for v, _, _ in vs)
            g.append(f'<line x1="{sx(lo):.1f}" x2="{sx(hi):.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="#c9ccd2" stroke-width="2"/>')
        for v, colr, _ in vs:
            g.append(f'<circle cx="{sx(v):.1f}" cy="{y:.1f}" r="4.6" fill="{colr}" stroke="#fff" stroke-width="1"/>')
    return f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}">{"".join(g)}</svg>'


def timeline_chart(product, metric, title, W=316, H=225):
    osfi = [r for r in points if r["product"] == product and r["company"] != MED
            and not r["source"].startswith("Annual report")]
    by_p = defaultdict(list)
    for r in osfi:
        if num(r[metric]) is not None:
            by_p[r["period"]].append((r["company"], num(r[metric])))
    periods = sorted((p for p in by_p if len(by_p[p]) >= 4), key=lambda p: (p[:4], p[-1]))
    lo = [min(v for _, v in by_p[p]) for p in periods]
    hi = [max(v for _, v in by_p[p]) for p in periods]
    md = [statistics.median(v for _, v in by_p[p]) for p in periods]
    rb = [next((v for c, v in by_p[p] if c == RBC), None) for p in periods]
    y0, y1 = nice(min(lo) - 0.05, max(hi) + 0.05, 0.5)
    m = (22, 10, 22, 40)
    sx, sy, g = axes(W, H, m, 0, len(periods) - 1, y0, y1, [], [y0 + i * 0.5 for i in range(int((y1 - y0) / 0.5) + 1)])
    for i, p in enumerate(periods):
        if p.endswith("Q4"):
            g.append(f'<text x="{sx(i):.1f}" y="{H - m[2] + 13}" text-anchor="middle" class="tk">{label(p)}</text>')
    band = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(hi)) + " " + \
        " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in reversed(list(enumerate(lo))))
    g.append(f'<polygon points="{band}" fill="#dfe3e9"/>')
    if PERIOD in periods:
        x = sx(periods.index(PERIOD))
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{m[0]}" y2="{H - m[2]}" stroke="{C_MUTED}" stroke-dasharray="2 3"/>')
    line = lambda vs: " ".join(f"{'M' if i == 0 or vs[i - 1] is None else 'L'}{sx(i):.1f},{sy(v):.1f}"
                               for i, v in enumerate(vs) if v is not None)
    g.append(f'<path d="{line(md)}" fill="none" stroke="{C_MED}" stroke-width="2"/>')
    g.append(f'<path d="{line(rb)}" fill="none" stroke="{C_RBC}" stroke-width="2.6"/>')
    g.append(f'<text x="{m[3]}" y="13" class="lb" font-weight="700">{esc(title)}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}">{"".join(g)}</svg>'


# ---------- tables ----------
def table(headers, rows, left=2):
    th = "".join(f'<th class="{"l" if i < left else ""}">{esc(h)}</th>' for i, h in enumerate(headers))
    body = []
    for cells, company in rows:
        cls = ' class="rbc"' if company == RBC else ' class="med"' if company == MED else ""
        body.append(f"<tr{cls}>" + "".join(f'<td class="{"l" if i < left else ""}">{esc(str(c))}</td>'
                                           for i, c in enumerate(cells)) + "</tr>")
    return f'<table><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def product_table(product, size_head):
    sel = by_size([r for r in points if r["period"] == PERIOD and r["product"] == product], "size_mm", "dr_30y")
    rows = []
    for r in sel:
        med = r["company"] == MED
        rows.append(([r["company"], r["source"] if med else as_at(r), "" if med else mm(r["size_mm"])]
                     + [f2(r[f"dr_{t}y"]) for t in TENORS], r["company"]))
    return table(["Insurer", "As at", size_head] + [f"{t}y rate" for t in TENORS], rows)


LEGEND_CURVES = (f'<div class="lg"><span><i style="background:{C_MED}"></i>Peer median</span>'
                 f'<span><i style="background:{C_RBC}"></i>RBC Life</span>'
                 f'<span><i style="background:{C_OTHER}"></i>OSFI filer</span>'
                 f'<span><i class="dash"></i>Annual report (all products)</span></div>')
SIZE_NOTE = ("Rows run from the largest portfolio to the smallest. Assets by product line are not published, so size is the "
             "line's insurance revenue in Canada for fiscal 2025 (OSFI LF3); annual-report insurers do not split revenue "
             "by line and sit at the bottom.")


def product_page(title, product, cap, size_head="Line revenue ($MM)", note=SIZE_NOTE, legend=LEGEND_CURVES):
    return f"""<section class="page"><h2>{esc(title)}</h2><p class="cap">{esc(cap)} {esc(note)}</p>
<div class="two"><div>{legend}{curve_chart(product)}</div><div>{product_table(product, size_head)}</div></div></section>"""


# premiums by product, one row per insurer (annuities: individual, else group)
lp = {}
for r in points:
    if r["period"] != PERIOD:
        continue
    d = lp.setdefault(r["company"], dict(company=r["company"], period=r["period"], as_at=r["as_at"], ann_from="",
                                         size_all_lines_mm=r["size_all_lines_mm"]))
    pre = {"Individual life": "life", "Participating": "par"}.get(r["product"])
    if r["product"] == "Individual annuity" or (r["product"] == "Group annuity" and d["ann_from"] != "Individual annuity"):
        pre = "ann"
        d["ann_from"] = r["product"]
    if pre:
        for t in TENORS:
            d[f"{pre}_{t}y"] = r[f"lp_{t}y"]
lp_rows = by_size(list(lp.values()), "size_all_lines_mm", "life_30y")
lp_table = table(["Insurer", "As at", "All-lines revenue ($MM)"] + [f"{p} {t}y" for p in ("Ann.", "Life", "Par") for t in TENORS],
                 [([r["company"], "Median" if r["company"] == MED else as_at(r), "" if r["company"] == MED else mm(r["size_all_lines_mm"])]
                   + [f2(r.get(f"{p}_{t}y")) for p in ("ann", "life", "par") for t in TENORS], r["company"]) for r in lp_rows])

par_rows = by_size(par, "par_account_mm", "dsir_less_flat_bp")
par_table = table(["Insurer", "Curve", "As at", "Par account ($MM)"] + [f"{t}y rate" for t in TENORS] + ["Flat-equiv.", "Dividend scale", "Gap (bp)"],
                  [([r["company"], r["curve"], as_at(r) if r["period"] else "", mm(r["par_account_mm"])]
                    + [f2(r[f"dr_{t}y"]) for t in TENORS] + [f2(r["flat_equivalent"]), f2(r["dsir"]),
                       "—" if num(r["dsir_less_flat_bp"]) is None else f'{num(r["dsir_less_flat_bp"]):+.0f}'], r["company"]) for r in par_rows],
                  left=3)

pct_rows = [r for r in points if r["period"] == PERIOD]
med_life = next(r for r in pct_rows if r["company"] == MED and r["product"] == "Individual life")
rbc_life = next(r for r in pct_rows if r["company"] == RBC and r["product"] == "Individual life")

CSS = f"""
@page {{ size: Letter landscape; margin: 0.45in 0.5in; }}
* {{ box-sizing: border-box; }}
body {{ font-family: "Helvetica Neue", Arial, sans-serif; color: {C_INK}; font-size: 10.5px; margin: 0; }}
.page {{ page-break-after: always; }}
.page:last-child {{ page-break-after: auto; }}
h1 {{ font-size: 24px; margin: 0 0 4px; }}
h2 {{ font-size: 16px; margin: 0 0 4px; }}
.cap {{ color: {C_MUTED}; margin: 0 0 10px; font-size: 9.5px; line-height: 1.4; max-width: 9.6in; }}
.two {{ display: flex; gap: 22px; align-items: flex-start; }}
.two > div:first-child {{ flex: 0 0 auto; }}
.two > div:last-child {{ flex: 1; }}
table {{ border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }}
th {{ font-weight: 600; color: {C_MUTED}; text-align: right; border-bottom: 1px solid #9aa0a8; padding: 4px 6px; font-size: 9.5px; }}
td {{ text-align: right; padding: 4.2px 6px; border-bottom: 1px solid {C_GRID}; white-space: nowrap; }}
.l {{ text-align: left; }}
tr.rbc td {{ background: #e8f0fa; color: {C_RBC}; font-weight: 700; }}
tr.med td {{ font-weight: 700; border-bottom: 1px solid #9aa0a8; }}
.wide table {{ font-size: 9.4px; }}
.wide td, .wide th {{ padding: 3.6px 4px; }}
svg text.tk {{ font-size: 9px; fill: {C_MUTED}; }}
svg text.lb {{ font-size: 10px; }}
.lg {{ display: flex; gap: 14px; margin: 0 0 4px; color: {C_MUTED}; flex-wrap: wrap; }}
.lg i {{ display: inline-block; width: 16px; height: 3px; vertical-align: middle; margin-right: 5px; }}
.lg i.dot {{ width: 9px; height: 9px; border-radius: 50%; }}
.lg i.dash {{ background: repeating-linear-gradient(90deg, {C_OTHER} 0 4px, transparent 4px 7px); }}
.kpis {{ display: flex; gap: 14px; margin: 16px 0; }}
.kpi {{ border: 1px solid {C_GRID}; border-radius: 6px; padding: 10px 14px; flex: 1; }}
.kpi b {{ display: block; font-size: 20px; margin-top: 3px; }}
.kpi.rbc b {{ color: {C_RBC}; }}
ul.notes {{ padding-left: 16px; line-height: 1.5; margin: 6px 0; max-width: 9.6in; }}
.three {{ display: flex; gap: 16px; }}
"""

prod_dot_legend = "".join(f'<span><i class="dot" style="background:{C_PROD[k]}"></i>{n}</span>'
                          for k, n in (("ann", "Annuities"), ("life", "Individual life"), ("par", "Participating")))
par_dot_legend = (f'<span><i class="dot" style="background:{C_MED}"></i>Flat-equivalent par discount rate</span>'
                  f'<span><i class="dot" style="background:#c0392b"></i>Dividend scale interest rate</span>')

pages = [f"""<section class="page">
<h1>Insurer discount curves by product line</h1>
<p class="cap" style="font-size:11px">Most illiquid IFRS 17 discount curves of Canadian life insurers, as at {label(PERIOD)} (year end; BMO Life and RBC Life at their October fiscal year end). Rates are spot, in %, from OSFI's LF2 return, or from annual reports for iA, Desjardins, Beneva and Assumption Life. RBC Life is highlighted throughout.</p>
<div class="kpis">
<div class="kpi rbc">RBC Life, individual life 30y rate<b>{f2(rbc_life['dr_30y'])}%</b></div>
<div class="kpi">Peer median, individual life 30y rate<b>{f2(med_life['dr_30y'])}%</b></div>
<div class="kpi rbc">RBC Life, individual life 30y premium<b>{f2(rbc_life['lp_30y'])}%</b></div>
<div class="kpi">Peer median, individual life 30y premium<b>{f2(med_life['lp_30y'])}%</b></div>
</div>
<h2>Method notes</h2>
<ul class="notes">
<li>OSFI collects only the most illiquid bucket. Each filer reports either a total discount rate or a liquidity premium over its own risk-free curve; the other is derived. Insurers with no risk-free curve (RBC Life and the annual-report insurers) have premiums measured against the median risk-free curve of the other OSFI filers.</li>
<li>RBC Life files rates with the shape of one-year forward rates; they are compounded to spot rates. This is an interpretation, not stated by OSFI.</li>
<li>Annual-report insurers publish one curve for all products, so they appear under every product. Their curves end at 70 years, so their 80-year point is the ultimate rate.</li>
<li>Par: each insurer's dividend scale interest rate (DSIR) for the year is used as its par discount rate, flat at every tenor; the par premium is the DSIR less the risk-free curve. Insurers without a published DSIR (ivari, Wawanesa Life, Beneva) are left out of par. The par curves insurers actually file are compared with the DSIR on a later page.</li>
<li>Tables are ordered by portfolio size. No public source gives assets by product line, so annuity and individual life tables use the line's insurance revenue in Canada for fiscal 2025 (OSFI LF3). Par uses par account size as published for advisors (PolicyAdvisor 2026; Co-operators from its own par account report). The premiums table uses insurance revenue in Canada across all lines.</li>
<li>Humania and UV Insurance publish only summary statements, with no discount curve. Canada Protection Plan is a Foresters business.</li>
</ul>
<p class="cap" style="margin-top:12px">Source data and code: analysis/discount_curves on branch claude/project-thread-w0w2ty. Interactive version: the "Insurer discount curves" dashboard.</p>
</section>""",
         product_page("Individual annuities: discount rates", "Individual annuity",
                      "Non-participating individual annuities, excluding segregated funds with guarantees."),
         product_page("Group annuities: discount rates", "Group annuity",
                      "Non-participating group annuities, excluding segregated funds with guarantees. Fewer insurers file a group annuity curve."),
         product_page("Individual life: discount rates", "Individual life", "Non-participating individual insurance."),
         product_page("Par account: dividend scale interest rate as the discount rate", "Participating",
                      "Each insurer's par account is discounted at its published dividend scale interest rate for 2025, flat at every tenor.",
                      size_head="Par account ($MM)",
                      note="Rows run from the largest par account to the smallest. Desjardins, Foresters and Assumption Life do not publish their par account size.",
                      legend=f'<div class="lg"><span><i style="background:{C_MED}"></i>Peer median</span><span><i style="background:{C_RBC}"></i>RBC Life</span><span><i style="background:{C_OTHER}"></i>Other insurers</span></div>'),
         f"""<section class="page wide"><h2>Par discount rates against the dividend scale interest rate</h2>
<p class="cap">The par curves insurers actually file, at year end 2025, beside the 2025 dividend scale interest rate they credit participating policyholders. The flat-equivalent rate is the single rate giving the same stylised liability value as the curve (payments falling 4% a year for 80 years). Gap is dividend rate less flat-equivalent, in basis points. Rows run from the largest par account to the smallest. Dividend rates from PolicyAdvisor's 2022 to 2026 table, with RBC Life and Equitable Life confirmed on their own sites.</p>
<div class="two"><div><div class="lg">{par_dot_legend}</div>{dot_chart(par_rows, [("flat_equivalent", C_MED, "Flat"), ("dsir", "#c0392b", "DSIR")], W=400, step=0.5)}</div><div>{par_table}</div></div></section>""",
         f"""<section class="page wide"><h2>Illiquidity premiums by product, 30 years</h2>
<p class="cap">Premium over the risk-free curve, %. Annuities use the individual annuity curve, or the group curve where that is all an insurer files. Par premiums are the dividend scale rate less the risk-free curve. Where dots overlap, the insurer uses the same premium for those products (RBC Life's annuity and life premiums coincide). Insurers without their own risk-free curve (RBC Life and the annual-report insurers) are measured against the peer median risk-free curve. Rows run from the largest insurer to the smallest by insurance revenue in Canada across all lines (OSFI LF3); annual-report insurers sit at the bottom.</p>
<div class="lg">{prod_dot_legend}</div>{dot_chart(lp_rows, [("ann_30y", C_PROD["ann"], "Annuities"), ("life_30y", C_PROD["life"], "Life"), ("par_30y", C_PROD["par"], "Par")], W=980, rowh=21)}
</section>""",
         f"""<section class="page wide"><h2>Illiquidity premiums by product: table</h2>
<p class="cap">Premium over the risk-free curve, %, at 5, 10, 20, 30 and 80 years. Same order as the previous page.</p>{lp_table}</section>""",
         f"""<section class="page"><h2>RBC Life against the peer group over time</h2>
<p class="cap">OSFI filers only, so every quarter compares like with like. The shaded band runs from the lowest to the highest insurer; the dotted line marks {label(PERIOD)}. RBC Life's rates are derived from the forward rates it files; its par line is its dividend scale rate.</p>
<div class="lg"><span><i style="background:{C_RBC}"></i>RBC Life</span><span><i style="background:{C_MED}"></i>Peer median</span><span><i style="background:#dfe3e9;height:9px"></i>Peer range</span></div>
<div class="three">{timeline_chart("Individual annuity", "dr_30y", "Individual annuities, 30y rate")}{timeline_chart("Individual life", "dr_30y", "Individual life, 30y rate")}{timeline_chart("Participating", "dr_30y", "Par, discount rate (DSIR)")}</div>
<div class="three">{timeline_chart("Individual annuity", "lp_30y", "Individual annuities, 30y premium")}{timeline_chart("Individual life", "lp_30y", "Individual life, 30y premium")}{timeline_chart("Individual life", "dr_80y", "Individual life, 80y rate")}</div>
</section>"""]

doc = f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>{"".join(pages)}</body></html>'
with tempfile.TemporaryDirectory() as tmp:
    page = os.path.join(tmp, "report.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(doc)
    js = os.path.join(tmp, "print.js")
    with open(js, "w") as f:
        f.write(f"""const {{ chromium }} = require('playwright');
(async () => {{ const b = await chromium.launch(); const p = await b.newPage();
await p.goto('file://{page}'); await p.pdf({{ path: {OUT!r}, format: 'Letter', landscape: true, preferCSSPageSize: true, printBackground: true,
displayHeaderFooter: true, headerTemplate: '<span></span>',
footerTemplate: '<div style="font-size:7px;color:#5d6470;width:100%;padding:0 0.5in;display:flex;justify-content:space-between"><span>Insurer discount curves by product line, {label(PERIOD)}</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>',
margin: {{ top: '0.45in', bottom: '0.5in', left: '0.5in', right: '0.5in' }} }}); await b.close(); }})();""")
    subprocess.run(["node", js], check=True, env={**os.environ, "NODE_PATH": subprocess.run(
        ["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()})
    if os.environ.get("KEEP_HTML"):
        import shutil
        shutil.copy(page, os.environ["KEEP_HTML"])
print("wrote", OUT)
