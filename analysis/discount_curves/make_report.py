"""Print the discount curve comparison as a landscape PDF (dashboard-style HTML and inline SVG).

    python3 analysis/discount_curves/make_report.py [out.pdf]

Reads the CSVs written by build.py (analysis/discount_curves/out), writes report.html next to them and prints it with
the preinstalled Playwright Chromium (node). Charts are static for print; the interactive version is the dashboard.
"""
import csv
import html
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "out")
PDF = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(HERE, "insurer-discount-curves-FY2025.pdf")

C_RBC, C_MED, C_OTHER, C_GRID, C_INK, C_MUTED, C_BAND = "#0051a5", "#1f1f1f", "#b9bec7", "#e6e8ec", "#1f2329", "#5d6470", "#dde2ea"
S1, S2, S3 = "#257de0", "#f47230", "#00b894"   # categorical slots 1 to 3 (validated all-pairs)
DATES = {"2025-10-31": "Oct 31, 2025", "2025-12-31": "Dec 31, 2025", "2024-10-31": "Oct 31, 2024", "2024-12-31": "Dec 31, 2024",
         "2023-12-31": "Dec 31, 2023", "2026-07-31": "Jul 31, 2026", "2026-06-30": "Jun 30, 2026"}
AR_IDS = {"IAG", "DFS", "BEN", "ASL"}
KEYLINE = "MFC = Manulife, SLF = Sun Life, CLF = Canada Life. e = estimate."


def read(name):
    with open(os.path.join(OUTDIR, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def f2(v, est=False, dash="—"):
    v = num(v)
    return dash if v is None else f"{v:.2f}" + ("<sup>e</sup>" if est else "")


def bn(v):
    v = num(v)
    if v is None or abs(v) < 0.005:
        return "—"
    return f"{v:,.1f}" if abs(v) >= 0.95 else f"{v:.2f}"


def esc(s):
    return html.escape(str(s))


# ------------------------------------------------------------------------------------------------ SVG helpers
class Plot:
    def __init__(self, w, h, x0, x1, y0, y1, ml=46, mr=16, mt=10, mb=30):
        self.w, self.h, self.x0, self.x1, self.y0, self.y1 = w, h, x0, x1, y0, y1
        self.ml, self.mr, self.mt, self.mb = ml, mr, mt, mb
        self.parts = []

    def x(self, v):
        return self.ml + (v - self.x0) / (self.x1 - self.x0) * (self.w - self.ml - self.mr)

    def y(self, v):
        return self.h - self.mb - (v - self.y0) / (self.y1 - self.y0) * (self.h - self.mt - self.mb)

    def grid_y(self, ticks, fmt="{:.1f}%"):
        for t in ticks:
            self.parts.append(f'<line x1="{self.ml}" x2="{self.w - self.mr}" y1="{self.y(t):.1f}" y2="{self.y(t):.1f}" stroke="{C_GRID}"/>'
                              f'<text x="{self.ml - 6}" y="{self.y(t) + 3.5:.1f}" text-anchor="end" class="tk">{fmt.format(t)}</text>')

    def axis_x(self, ticks, labels=None, title=None):
        yb = self.h - self.mb
        self.parts.append(f'<line x1="{self.ml}" x2="{self.w - self.mr}" y1="{yb}" y2="{yb}" stroke="#8a909b"/>')
        for i, t in enumerate(ticks):
            lab = labels[i] if labels else t
            self.parts.append(f'<text x="{self.x(t):.1f}" y="{yb + 14}" text-anchor="middle" class="tk">{lab}</text>')
        if title:
            self.parts.append(f'<text x="{(self.ml + self.w - self.mr) / 2:.1f}" y="{self.h - 2}" text-anchor="middle" class="tk">{title}</text>')

    def grid_x(self, ticks, fmt="{:.1f}%"):
        for t in ticks:
            self.parts.append(f'<line x1="{self.x(t):.1f}" x2="{self.x(t):.1f}" y1="{self.mt}" y2="{self.h - self.mb}" stroke="{C_GRID}"/>'
                              f'<text x="{self.x(t):.1f}" y="{self.h - self.mb + 14}" text-anchor="middle" class="tk">{fmt.format(t)}</text>')

    def line(self, pts, color, width=2, dash=None, opacity=1):
        pts = [(a, b) for a, b in pts if b is not None]
        if len(pts) < 2:
            return
        dpath = " ".join(f"{'M' if i == 0 else 'L'}{self.x(a):.1f},{self.y(b):.1f}" for i, (a, b) in enumerate(pts))
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<path d="{dpath}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"{da} opacity="{opacity}"/>')

    def band(self, lo, hi, color=C_BAND):
        pts = [(a, b) for a, b in hi] + [(a, b) for a, b in reversed(lo)]
        self.parts.append('<polygon points="' + " ".join(f"{self.x(a):.1f},{self.y(b):.1f}" for a, b in pts) + f'" fill="{color}"/>')

    def dot(self, xv, yv, color, r=4.5, ring=True, hollow=False):
        fill = "#fff" if hollow else color
        st = f' stroke="{color}" stroke-width="2"' if hollow else (' stroke="#fff" stroke-width="2"' if ring else "")
        self.parts.append(f'<circle cx="{self.x(xv):.1f}" cy="{self.y(yv):.1f}" r="{r}" fill="{fill}"{st}/>')

    def text(self, xv, yv, s, cls="lb", anchor="start", dx=0, dy=0, color=None, bold=False):
        st = (f' fill="{color}"' if color else "") + (' font-weight="600"' if bold else "")
        self.parts.append(f'<text x="{self.x(xv) + dx:.1f}" y="{self.y(yv) + dy:.1f}" text-anchor="{anchor}" class="{cls}"{st}>{s}</text>')

    def raw(self, s):
        self.parts.append(s)

    def svg(self):
        return f'<svg viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" role="img">' + "".join(self.parts) + "</svg>"


def legend(items):
    out = []
    for kind, color, label in items:
        if kind == "line":
            sw = f'<span class="sw" style="background:{color}"></span>'
        elif kind == "dash":
            sw = f'<span class="sw" style="background:repeating-linear-gradient(90deg,{color} 0 5px,transparent 5px 8px)"></span>'
        elif kind == "band":
            sw = f'<span class="sw" style="background:{color};height:10px"></span>'
        elif kind == "ring":
            sw = f'<span class="dt" style="background:#fff;border:2px solid {color};box-sizing:border-box"></span>'
        else:
            sw = f'<span class="dt" style="background:{color}"></span>'
        out.append(f'<span class="lg">{sw}{esc(label)}</span>')
    return '<div class="legend">' + "".join(out) + "</div>"


def table(headers, rows, cls=""):
    """headers: list of (label, align). rows: list of (cells, row_class)."""
    th = "".join(f'<th class="{a}">{h}</th>' for h, a in headers)
    body = ""
    for cells, rc in rows:
        body += f'<tr class="{rc}">' + "".join(f'<td class="{headers[i][1]}">{c}</td>' for i, c in enumerate(cells)) + "</tr>"
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def rowcls(r):
    return "rbc" if r.get("id") == "RBC" else ("med" if r.get("id") == "MEDIAN" else "")


def as_at(r):
    return DATES.get(r.get("as_at", ""), r.get("as_at", ""))


# ------------------------------------------------------------------------------------------------ data
head = read("headline_fy2025.csv")
H = {r["id"]: r for r in head}
byline = read("by_line_fy2025.csv")
band = read("band.csv")
ref = read("reference_curve_check.csv")
ann = read("curves_annual_fy2025.csv")
ult = read("ultimates_and_basis.csv")
buckets = read("liquidity_buckets_fy2025.csv")
par = read("par_fy2025.csv")
mix = read("premium_vs_asset_mix.csv")
trend = read("trend.csv")
f2s = read("rbc_forward_to_spot.csv")
wtd = {r["id"]: r for r in read("weighted_premium_fy2025.csv")}

rbc, med = H["RBC"], H["MEDIAN"]
peers = [r for r in head if r["id"] not in ("RBC", "MEDIAN")]
lp30 = sorted(num(r["lp_30y"]) for r in peers)
REF25 = {}
for r in ref:
    if r["pair"] == "fy2025":
        REF25.setdefault(r["reference"], {})[int(r["tenor"])] = r
ref_order = ["BMO Life (ALM repo basis)", "TD Life", "CIBC Life", "Median of the three", "RBC Life seg fund curve, spot (est)"]
p30 = {k: num(v[30]["rbc_premium"]) for k, v in REF25.items()}
lo30, hi30 = min(p30["TD Life"], p30["CIBC Life"]), p30["BMO Life (ALM repo basis)"]
medlp = {t: num(med[f"lp_{t}y"]) for t in (5, 10, 20, 30)}
n_peers = len(peers)
T24 = {(r["pair"], int(r["tenor"])): r for r in trend}

pages = []


def page(title, sub, body, note=KEYLINE):
    pages.append(f'<section class="page"><h1>{title}</h1><p class="sub">{sub}</p>{body}<div class="foot"><span>{note}</span></div></section>')


# ------------------------------------------------------------------------------------------------ 1. summary
tiles = [
    ("RBC Life, 30-year spot rate", f'{num(rbc["dr_30y"]):.2f}%', "Oct 31, 2025. Est: compounded from the 1-year forwards it files (5.09% as filed)", True),
    ("Peer median, 30-year rate on the same date", f'{num(med["aligned_30y"]):.2f}%', f'{n_peers} peers restated to Oct 31, 2025 ({num(med["dr_30y"]):.2f}% as filed at Dec 31)', False),
    ("RBC Life, 30-year illiquidity premium", f'{hi30:.2f}%', f"Est, over BMO Life's Oct 31 risk-free curve. {lo30:.2f}% to {p30['TD Life']:.2f}% over the other two Oct 31 filers", True),
    ("Peer median, 30-year premium", f'{medlp[30]:.2f}%', f"Range {lp30[0]:.2f}% to {lp30[-1]:.2f}% (Primerica to MFC), each over its own risk-free curve", False),
]
tile_html = '<div class="tiles">' + "".join(
    f'<div class="tile"><div class="tl">{a}</div><div class="tv{" rbcv" if hl else ""}">{b}</div><div class="tn">{c}</div></div>' for a, b, c, hl in tiles) + "</div>"
t24, t26 = T24[("fy2024", 30)], T24[("mid2026", 30)]
gap_bmo = hi30 - medlp[30]
gap_lo = lo30 - medlp[30]
findings = f"""
<div class="cols2">
<div>
<h2>What the comparison shows</h2>
<ul class="fx">
<li><b>RBC Life carries the highest long-end premium in the peer set.</b> Its 30-year premium is {hi30:.2f}% over BMO Life's same-date risk-free curve, against a peer median of {medlp[30]:.2f}%. Only MFC ({num(H['MFC']['lp_30y']):.2f}%) and iA ({num(H['IAG']['lp_30y']):.2f}%, est) come close. At 20 years RBC Life is {num(rbc['lp_20y']):.2f}% against a peer high of 1.72%.</li>
<li><b>The size of the gap depends on the Oct 31 risk-free curve.</b> BMO Life's curve is the lowest of the three Oct 31 filers at 30 years (3.26%, TD Life 3.57%, CIBC Life 3.75%). On those two, RBC Life's premium is {p30['TD Life']:.2f}% and {lo30:.2f}%. The gap to the peer median is {gap_lo * 100:.0f} to {gap_bmo * 100:.0f} bp.</li>
<li><b>The premium is concentrated at 15 to 40 years.</b> At 10 years it is {num(REF25['CIBC Life'][10]['rbc_premium']):.2f}% to {num(rbc['lp_10y']):.2f}%, against a peer range of 0.77% to 1.56% (median {medlp[10]:.2f}%). Beyond about 50 years its curve sits below peers: ultimate forward rate 4.10% against 5.15% for most peers.</li>
<li><b>The same curve applies to every non-par line.</b> RBC Life files one curve for individual insurance, annuities, group and reinsurance. Pension risk transfer (group annuity, $7.6BN, 41% of its non-par liabilities) is discounted at the same rates. CLF, SLF and BMO Life file lower premiums for annuities than RBC Life at every tenor above 5 years.</li>
<li><b>The premium widened in fiscal 2025.</b> RBC Life's 30-year premium was {num(t24['rbc_premium']):.2f}% at Oct 31, 2024, {hi30:.2f}% at Oct 31, 2025 and {num(t26['rbc_premium']):.2f}% at Jul 31, 2026 (est, BMO basis). The peer median fell from 1.78% (Dec 2023) to {medlp[30]:.2f}%.</li>
<li><b>Asset mix does not explain it.</b> Private fixed income is 19% of RBC Life's non-par General Account, against 25% at MFC, 37% at CLF and 48% at SLF (est), and government bonds are 40%.</li>
</ul>
</div>
<div>
<h2>What changed from the October version</h2>
<ul class="fx small">
<li><b>One date.</b> RBC Life and BMO Life report at Oct 31, the others at Dec 31. Peer curves are restated to Oct 31 (own premium plus the Oct 31 risk-free curve). The October version measured RBC Life against a Dec 31 risk-free curve, which is 0.77 points higher at 30 years, and showed a premium of 1.72%.</li>
<li><b>One basis.</b> Spot rates throughout. RBC Life's filed forwards are compounded to spot by the ALM repo's method (limitation L17), with the filer wording that supports each insurer's basis.</li>
<li><b>Liabilities, not revenue, for size.</b> Tables are ordered by insurance contract liabilities in Canada, net of reinsurance, by product line.</li>
<li><b>Canadian business, non-par General Account first.</b> Par and segregated funds are shown separately. Par keeps the dividend scale rate method, with the filed par curve beside it.</li>
<li><b>New pages:</b> ultimate assumptions, most against least illiquid curves, premium against asset mix.</li>
<li><b>Dropped:</b> the stylised liability value. Its dollar effect needs liability cash flows that are not public (see next steps).</li>
</ul>
<h2 style="margin-top:14px">Directional read for the CIO</h2>
<p class="small">A top-down curve passes the yield of the reference asset portfolio, net of credit, into the liability. The higher the premium, the lower the liability and the higher the yield the assets must earn to cover its accretion. RBC Life's curve asks for roughly 2.0% to 2.5% over risk-free at 20 to 30 years, where most PRT cash flows fall. This is a read of public filings, not a valuation.</p>
</div>
</div>"""
page("Peer discount curves and illiquidity premiums",
     "IFRS 17 discount curves for Canadian business, most illiquid bucket, fiscal 2025 year end (RBC Life and BMO Life at Oct 31, 2025; others at Dec 31, 2025). "
     "Rebuilt on the cdn-life-insurer-alm framework: spot basis, one date, premium over risk-free, liabilities by line. Rates in %.",
     tile_html + findings)

# ------------------------------------------------------------------------------------------------ 2. basis
fs = [r for r in f2s if r["pair"] == "fy2025"]
P = Plot(430, 320, 0, 80, 1.5, 7.5, mr=84)
P.grid_y([2, 3, 4, 5, 6, 7], "{:.0f}%")
P.axis_x([1, 10, 20, 30, 40, 50, 60, 70, 80], title="Year")
P.line([(int(r["tenor"]), num(r["filed_forward"])) for r in fs], C_OTHER, 2)
P.line([(int(r["tenor"]), num(r["spot_step"])) for r in fs], C_RBC, 1.5, dash="4 3")
P.line([(int(r["tenor"]), num(r["spot_linear"])) for r in fs], C_RBC, 2.5)
for r in fs:
    if r["filed_node"] == "Y":
        P.dot(int(r["tenor"]), num(r["filed_forward"]), "#8a909b", r=3.5)
P.text(20, 7.27, "As filed: 7.27% at 20 years", dx=8, dy=-2)
P.text(70, 1.90, "1.90% at 70", anchor="middle", dy=14)
P.text(80, num(fs[-1]["spot_linear"]), "Spot 4.23%", dx=6, dy=-3, color=C_RBC, bold=True)
P.text(80, 4.10, "Filed 4.10%", dx=6, dy=12)
P.text(30, 5.75, "5.75% at 30 years", dx=4, dy=-10, color=C_RBC, bold=True)
rows = []
for r in ult:
    note = r["basis_note"]
    if note.startswith("no curve-basis wording"):
        note = "No basis wording located in the filings held; smooth shape"
    rows.append(([esc(r["insurer"]), esc(r["basis_evidence"]).replace(" (not stated by filer)", ", not stated"), esc(note), f2(r["hump_max_less_ultimate"]), f2(r["min_beyond_30y"])], rowcls(r)))
tb = table([("Insurer", "l"), ("Basis", "l"), ("Evidence", "l wrap"), ("Peak less<br>ultimate", "r"), ("Lowest rate<br>past 30y", "r")], rows, "tight")
page("Step 1: one basis. RBC Life files forward rates; peers file spot rates",
     "RBC Life's filed curve peaks at 7.27% at 20 years, falls to 1.90% at 70 and returns to 4.10% at 80: the shape of 1-year forward rates. Compounded to spot it reads 5.75% at 30 years. "
     "The ALM repo treats this as an agreed workaround (limitation L17), still to be confirmed internally.",
     '<div class="split"><div class="c35">' + legend([("line", C_OTHER, "RBC Life, as filed (1-year forwards)"), ("line", C_RBC, "Spot, forwards linear between filed points (base, est)"),
                                                     ("dash", C_RBC, "Spot, step forwards (sensitivity)")]) + P.svg() +
     '<p class="small">Annual compounding: (1 + spot<sub>T</sub>)<sup>T</sup> = product of (1 + forward<sub>t</sub>). The two interpolations differ by 1 bp at 30 years (5.75% and 5.74%) and by up to 0.5 points at 15 to 25 years. '
     'RBC Life\'s own annual report shows the same filed values as "current discount yields" with no spot or forward label. Wawanesa Life is the precedent: its financial statements show a forward-shaped curve and its OSFI filing the spot equivalent.</p></div>'
     '<div class="c65">' + tb + '<p class="small">Peak less ultimate: highest rate on the curve the insurer reports, less its ultimate rate, in points. A large peak with a trough before the ultimate marks a forward curve. '
     "MFC's 30-year point (6.10%) is confirmed as spot by its annual report.</p></div></div>")

# ------------------------------------------------------------------------------------------------ 3. date and reference curve
P = Plot(500, 320, 0, 30, 2.0, 4.4, mr=92)
P.grid_y([2.0, 2.5, 3.0, 3.5, 4.0], "{:.1f}%")
P.axis_x([1, 5, 10, 20, 30], title="Year")
nodes = [1, 2, 5, 10, 20, 30]
dec_rf = {10: num(T24[("fy2025", 10)]["peer_median_risk_free"]), 30: num(T24[("fy2025", 30)]["peer_median_risk_free"])}
curv = read("curves.csv")
decmed = {}
for t in nodes:
    vals = sorted(num(r["risk_free"]) for r in curv if r["pair"] == "fy2025" and r["line"] == "Individual insurance" and int(r["tenor"]) == t
                  and r["as_at"] == "2025-12-31" and num(r["risk_free"]) is not None)
    decmed[t] = (vals[len(vals) // 2] + vals[(len(vals) - 1) // 2]) / 2
P.line([(t, decmed[t]) for t in nodes], C_MED, 2, dash="5 3")
styles = {"BMO Life (ALM repo basis)": (C_RBC, 2.5, None), "TD Life": (S2, 2, None), "CIBC Life": (S3, 2, None), "RBC Life seg fund curve, spot (est)": ("#8a909b", 1.5, "3 3")}
for k, (col, wd, da) in styles.items():
    P.line([(t, num(REF25[k][t]["risk_free"])) for t in nodes], col, wd, dash=da)
P.text(30, decmed[30], "Peers, Dec 31", dx=6, dy=4, bold=True)
P.text(30, 3.75, "CIBC Life", dx=6, dy=4)
P.text(30, 3.57, "TD Life", dx=6, dy=4)
P.text(30, 3.26, "BMO Life", dx=6, dy=11, color=C_RBC, bold=True)
P.text(30, 3.29, "RBC seg (est)", dx=6, dy=-3)
rows = []
for k in ref_order:
    v = REF25[k]
    rows.append(([esc(k), f2(v[10]["risk_free"]), f2(v[30]["risk_free"]), f2(v[10]["rbc_premium"], True), f2(v[20]["rbc_premium"], True), f2(v[30]["rbc_premium"], True),
                  f'{(num(v[30]["rbc_premium"]) - medlp[30]) * 100:+.0f}', f'{num(v[30]["risk_free"]) + medlp[30]:.2f}'], "rbc" if k.startswith("BMO") else ""))
rows.append((["Peer median premium (own risk-free)", "", "", f2(medlp[10]), f2(medlp[20]), f2(medlp[30]), "", ""], "med"))
tb = table([("Oct 31, 2025 risk-free reference", "l"), ("Risk-free<br>10y", "r"), ("Risk-free<br>30y", "r"), ("RBC premium<br>10y", "r"), ("RBC premium<br>20y", "r"),
            ("RBC premium<br>30y", "r"), ("Gap to peer<br>median, 30y (bp)", "r"), ("Peer median 30y<br>rate at Oct 31", "r")], rows)
page("Step 2: one date. Oct 31 risk-free curves sit 0.3 to 0.8 points below Dec 31 curves at 30 years",
     "RBC Life files no risk-free curve, so its premium needs a reference. The ALM repo uses BMO Life's curve at the same Oct 31 date and restates Dec 31 peers to Oct 31 on it (own premium plus BMO's risk-free). "
     "Two other Oct 31 filers, TD Life and CIBC Life, show how much the answer depends on that choice.",
     '<div class="split"><div class="c40">' + legend([("line", C_RBC, "BMO Life, Oct 31 (ALM repo basis)"), ("line", S2, "TD Life, Oct 31"), ("line", S3, "CIBC Life, Oct 31"),
                                                     ("dash", "#8a909b", "RBC Life seg fund curve, spot (est)"), ("dash", C_MED, "Peer median, Dec 31")]) + P.svg() + "</div>"
     '<div class="c60">' + tb +
     '<ul class="fx small" style="margin-top:10px"><li><b>Baseline: BMO Life (ALM repo).</b> RBC Life\'s own segregated fund curve, converted to spot the same way, reads 3.29% at 30 years. '
     "Seg fund curves sit close to risk-free, so this supports BMO's 3.26% as a proxy for RBC Life's own risk-free level.</li>"
     "<li><b>BMO Life's fiscal Q4 2025 curve is low against the other two.</b> It is 31 bp below TD Life and 49 bp below CIBC Life at 30 years, and its ultimate was filed at 3.46% that quarter (3.65% before and after). "
     "If peers' Dec 31 risk-free curves are closer in kind to TD's or CIBC's, restating them on BMO's curve understates their Oct 31 rates.</li>"
     f"<li><b>Conclusion holds on all three.</b> RBC Life's 30-year premium is {lo30:.2f}% to {hi30:.2f}%, against a peer median of {medlp[30]:.2f}% and a peer high of {lp30[-1]:.2f}% (MFC). "
     "On the CIBC curve RBC Life is second to MFC at 30 years and first at 20 years.</li></ul></div></div>",
     "Risk-free curves as filed in OSFI LF2 (Canada, most illiquid bucket schedule). TD Life and CIBC Life are outside the peer set and used only as same-date references. e = estimate.")


# ------------------------------------------------------------------------------------------------ 4. band
def band_chart(line, w=500, h=330, ymax=6.2):
    rows = [r for r in band if r["pair"] == "fy2025" and r["line"] == line]
    P = Plot(w, h, 0, 30, 2.0, ymax, mr=84)
    P.grid_y([2, 3, 4, 5, 6], "{:.0f}%")
    P.axis_x([1, 5, 10, 15, 20, 25, 30], title="Year")
    P.band([(int(r["tenor"]), num(r["peer_min"])) for r in rows], [(int(r["tenor"]), num(r["peer_max"])) for r in rows])
    P.line([(int(r["tenor"]), num(r["peer_median_as_filed"])) for r in rows], "#8a909b", 1.5, dash="4 3")
    P.line([(int(r["tenor"]), num(r["peer_median"])) for r in rows], C_MED, 2)
    P.line([(int(r["tenor"]), num(r["rbc_spot"])) for r in rows], C_RBC, 2.5)
    last = rows[-1]
    P.text(30, num(last["rbc_spot"]), "RBC Life", dx=6, dy=4, color=C_RBC, bold=True)
    P.text(30, num(last["peer_median"]), "Peer median", dx=6, dy=4, bold=True)
    P.text(30, num(last["peer_median_as_filed"]), "As filed, Dec 31", dx=6, dy=4)
    return P.svg(), rows


svg_ii, rows_ii = band_chart("Individual insurance")
svg_ga, rows_ga = band_chart("Group annuity")


def band_table(rows):
    out = []
    for t in (1, 5, 10, 20, 30):
        r = next(x for x in rows if int(x["tenor"]) == t)
        out.append(([f"{t}", f2(r["rbc_spot"], True), f2(r["peer_median"], True), f2(r["peer_min"], True), f2(r["peer_max"], True),
                     f'{(num(r["rbc_spot"]) - num(r["peer_median"])) * 100:+.0f}', f'{(num(r["rbc_spot"]) - num(r["peer_max"])) * 100:+.0f}'], ""))
    return table([("Year", "l"), ("RBC Life<br>spot", "r"), ("Peer<br>median", "r"), ("Peer<br>low", "r"), ("Peer<br>high", "r"), ("RBC less<br>median (bp)", "r"), ("RBC less<br>high (bp)", "r")], out, "tight")


lg = legend([("line", C_RBC, "RBC Life, spot (est)"), ("line", C_MED, "Peer median, restated to Oct 31"), ("band", C_BAND, "Peer range, restated to Oct 31"), ("dash", "#8a909b", "Peer median as filed, Dec 31")])
page("Like for like: RBC Life's curve is above every OSFI-filing peer from about year 12 to year 30",
     "Years 1 to 30, spot rates at Oct 31, 2025. Peers are OSFI filers only, restated from Dec 31 to Oct 31 by keeping each peer's filed premium and replacing its risk-free curve with BMO Life's Oct 31 curve "
     "(ALM repo method). On the TD Life or CIBC Life curve the peer band is 31 or 49 bp higher at 30 years and MFC's 30-year rate reaches RBC Life's.",
     lg + '<div class="split"><div class="c50"><h3>Individual insurance (12 peers)</h3>' + svg_ii + band_table(rows_ii) + "</div>"
     '<div class="c50"><h3>Group annuity, which includes pension risk transfer (6 peers)</h3>' + svg_ga + band_table(rows_ga) + "</div></div>"
     '<p class="small">RBC Life files the same curve for both lines. Group annuity peers: ' + ", ".join(
         {"SLF": "SLF", "CLF": "CLF", "MFC": "MFC", "EMP": "Empire Life", "COP": "Co-operators Life", "IOF": "Foresters Life"}.get(x, x) for x in rows_ga[0]["peers"].split("|")) +
     ". BMO Life filed no group annuity curve at Oct 31, 2025; at Jun 30, 2026 its group annuity curve equals its individual annuity curve.</p>")

# ------------------------------------------------------------------------------------------------ 5. headline table + dot chart
order = [r for r in head if r["id"] != "MEDIAN"]
n = len(order) + 1
rh = 23
P = Plot(330, 40 + n * rh, 0.4, 2.8, 0, 1, ml=112, mr=14, mt=6, mb=26)
P.grid_x([0.5, 1.0, 1.5, 2.0, 2.5])
for i, r in enumerate([med] + order):
    yy = P.mt + rh * i + rh / 2
    isr, ism = r["id"] == "RBC", r["id"] == "MEDIAN"
    if isr:
        P.raw(f'<rect x="0" y="{yy - rh / 2 + 1:.1f}" width="{P.w}" height="{rh - 2}" fill="#e6eef8"/>')
    nm = r["insurer"]
    P.raw(f'<text x="{P.ml - 8}" y="{yy + 4:.1f}" text-anchor="end" class="lb"{" font-weight=\"600\"" if isr or ism else ""}{f" fill=\"{C_RBC}\"" if isr else ""}>{esc(nm)}</text>')
    a, b = num(r["lp_10y"]), num(r["lp_30y"])
    P.raw(f'<line x1="{P.x(min(a, b)):.1f}" x2="{P.x(max(a, b)):.1f}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#c9ced6" stroke-width="2"/>')
    if isr:
        P.raw(f'<line x1="{P.x(lo30):.1f}" x2="{P.x(hi30):.1f}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{S1}" stroke-width="7" opacity="0.35" stroke-linecap="round"/>')
    est = r["id"] in AR_IDS or isr
    P.raw(f'<circle cx="{P.x(a):.1f}" cy="{yy:.1f}" r="4.5" fill="{"#fff" if est else S2}" stroke="{S2 if est else "#fff"}" stroke-width="2"/>')
    P.raw(f'<circle cx="{P.x(b):.1f}" cy="{yy:.1f}" r="4.5" fill="{"#fff" if est else S1}" stroke="{S1 if est else "#fff"}" stroke-width="2"/>')
dot_svg = P.svg()
rows = []
for r in [med] + order:
    est = r["id"] in AR_IDS or r["id"] == "RBC"
    ism = r["id"] == "MEDIAN"
    rows.append(([esc(r["insurer"]), "" if ism else as_at(r)[:6], "" if ism else bn(r["nonpar_liabilities_bn"]),
                  f2(r["dr_10y"], r["id"] == "RBC"), f2(r["dr_30y"], r["id"] == "RBC"), f2(r["dr_80y"], r["id"] == "RBC"),
                  f2(r["lp_5y"], est), f2(r["lp_10y"], est), f2(r["lp_20y"], est), f2(r["lp_30y"], est), f2(r["lp_80y"], est and r["id"] != "RBC"),
                  f2(r["aligned_30y"], r["id"] != "BMO"), "" if ism else esc(r["approach"]).replace("where asset-backed; bottom-up otherwise", "(asset-backed)").replace(" (Fiera IFRS 17 curve)", "")], rowcls(r)))
tb = table([("Insurer", "l"), ("As at", "l"), ("Non-par<br>liabilities<br>($BN)", "r"), ("Rate<br>10y", "r"), ("Rate<br>30y", "r"), ("Rate<br>80y", "r"),
            ("Prem.<br>5y", "r"), ("Prem.<br>10y", "r"), ("Prem.<br>20y", "r"), ("Prem.<br>30y", "r"), ("Prem.<br>ult.", "r"), ("30y rate<br>at Oct 31", "r"), ("Approach", "l")], rows, "tight")
page("Illiquidity premium by tenor, individual insurance",
     "Premium over each insurer's own risk-free curve, most illiquid bucket, Canada. Rows run from the largest non-par book to the smallest (insurance contract liabilities in Canada, net of reinsurance, excluding par and segregated funds). "
     f"Peer median is of {n_peers} peers, RBC Life excluded.",
     '<div class="split"><div class="c30">' + legend([("dot", S2, "10 years"), ("dot", S1, "30 years"), ("ring", S1, "Estimate"), ("band", "#b9d3f3", "RBC 30y range by reference")]) + dot_svg + "</div>"
     '<div class="c70">' + tb + "</div></div>"
     '<p class="small">Estimates: RBC Life (spot from forwards; premium over BMO Life\'s Oct 31 risk-free curve, not filed beyond 30 years) and the four annual-report insurers '
     "(iA, Desjardins, Beneva, Assumption Life: one all-products curve; premium over the median Dec 31 risk-free curve of the OSFI filers). "
     "Primerica's non-par book is a net asset. Approach is the insurer's own description where the ALM repo captured it; blank cells read \"not captured\".</p>")


# ------------------------------------------------------------------------------------------------ 6-8. by product pages
def product_page(line, title, sub):
    rows = [r for r in ann if r["line"] == line]
    ids = []
    for r in rows:
        if r["id"] not in ids:
            ids.append(r["id"])
    P = Plot(470, 380, 0, 80, 2.5, 6.5, mr=78)
    P.grid_y([3, 4, 5, 6], "{:.0f}%")
    P.axis_x([1, 10, 20, 30, 40, 50, 60, 70, 80], title="Year")
    for sid in ids:
        if sid in ("RBC", "MEDIAN"):
            continue
        pts = [(int(r["tenor"]), num(r["rate"])) for r in rows if r["id"] == sid]
        P.line(pts, C_OTHER, 1.2, dash="4 3" if sid in AR_IDS else None)
    mp = [(int(r["tenor"]), num(r["rate"])) for r in rows if r["id"] == "MEDIAN"]
    rp = [(int(r["tenor"]), num(r["rate"])) for r in rows if r["id"] == "RBC"]
    P.line(mp, C_MED, 2.2)
    P.line(rp, C_RBC, 2.5)
    P.text(80, mp[-1][1], "Peer median", dx=6, dy=4, bold=True)
    P.text(80, rp[-1][1], "RBC Life", dx=6, dy=4, color=C_RBC, bold=True)
    bl = [r for r in byline if r["line"] == line]
    medr = next(r for r in bl if r["id"] == "MEDIAN")
    body = sorted([r for r in bl if r["id"] != "MEDIAN"], key=lambda r: (-(num(r["liabilities_bn"]) if num(r["liabilities_bn"]) is not None else -99), r["insurer"]))
    trs = []
    for r in [medr] + body:
        isr, ism = r["id"] == "RBC", r["id"] == "MEDIAN"
        est = isr or r["id"] in AR_IDS
        trs.append(([esc(r["insurer"]), esc(r["as_at"]) if ism else as_at(r)[:6], "" if ism else bn(r["liabilities_bn"])] +
                    [f2(r[f"dr_{t}y"], isr) for t in (5, 10, 20, 30, 80)] + [f2(r["lp_10y"], est), f2(r["lp_30y"], est), f2(r["aligned_30y"], r["id"] != "BMO")], rowcls(r)))
    tb = table([("Insurer", "l"), ("As at", "l"), ("Line<br>liabilities<br>($BN)", "r"), ("Rate<br>5y", "r"), ("Rate<br>10y", "r"), ("Rate<br>20y", "r"), ("Rate<br>30y", "r"), ("Rate<br>80y", "r"),
                ("Prem.<br>10y", "r"), ("Prem.<br>30y", "r"), ("30y rate<br>at Oct 31", "r")], trs, "tight")
    page(title, sub, '<div class="split"><div class="c40">' + legend([("line", C_RBC, "RBC Life (Oct 31, spot est)"), ("line", C_MED, "Peer median"), ("line", C_OTHER, "OSFI filer"),
                                                                     ("dash", C_OTHER, "Annual report (all products)")]) + P.svg() +
         '<p class="small">Chart: spot curves as filed at each insurer\'s own year end, years 1 to 80. RBC Life and BMO Life are two months earlier than the others; the table\'s last column puts the 30-year rate on Oct 31 for everyone.</p></div>'
         '<div class="c60">' + tb + "</div></div>")


liab_note = ("Rows run from the largest book in the line to the smallest: insurance contract liabilities in Canada for the line, net of reinsurance (OSFI LF3). "
             "Annual-report insurers publish one curve for all products and no split of liabilities by line, so they sit at the bottom.")
product_page("Individual insurance", "Individual insurance: discount rates", "Non-participating individual insurance, Canada, most illiquid bucket. " + liab_note)
product_page("Individual annuity", "Individual annuities: discount rates", "Non-participating individual annuities, excluding segregated funds with guarantees. " + liab_note)
product_page("Group annuity", "Group annuities and pension risk transfer: discount rates",
             "Non-participating group annuities, excluding segregated funds with guarantees. Fewer insurers file this curve. " + liab_note)

# ------------------------------------------------------------------------------------------------ 9. premium by product line
ids = [r["id"] for r in order]
BL = {(r["id"], r["line"]): r for r in byline}
P = Plot(330, 40 + n * rh, 0.4, 2.8, 0, 1, ml=112, mr=14, mt=6, mb=26)
P.grid_x([0.5, 1.0, 1.5, 2.0, 2.5])
series = [("Individual insurance", S1), ("Individual annuity", S2), ("Group annuity", S3)]
for i, sid in enumerate(["MEDIAN"] + ids):
    yy = P.mt + rh * i + rh / 2
    isr = sid == "RBC"
    if isr:
        P.raw(f'<rect x="0" y="{yy - rh / 2 + 1:.1f}" width="{P.w}" height="{rh - 2}" fill="#e6eef8"/>')
    nm = "Peer median" if sid == "MEDIAN" else H[sid]["insurer"]
    P.raw(f'<text x="{P.ml - 8}" y="{yy + 4:.1f}" text-anchor="end" class="lb"{" font-weight=\"600\"" if isr or sid == "MEDIAN" else ""}{f" fill=\"{C_RBC}\"" if isr else ""}>{esc(nm)}</text>')
    vals = [(num(BL[(sid, ln)]["lp_30y"]), col) for ln, col in series if (sid, ln) in BL and num(BL[(sid, ln)]["lp_30y"]) is not None]
    if vals:
        xs = [v for v, _ in vals]
        P.raw(f'<line x1="{P.x(min(xs)):.1f}" x2="{P.x(max(xs)):.1f}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#c9ced6" stroke-width="2"/>')
    seen = {}
    for v, col in vals:  # coincident dots are nudged vertically so each line stays visible
        k = round(v, 2)
        off = seen.get(k, 0)
        seen[k] = off + 1
        P.raw(f'<circle cx="{P.x(v):.1f}" cy="{yy + (off - (len([1 for x, _ in vals if round(x, 2) == k]) - 1) / 2) * 5:.1f}" r="4" fill="{col}" stroke="#fff" stroke-width="1.5"/>')
rows = []
for sid in ["MEDIAN"] + ids:
    r0 = med if sid == "MEDIAN" else H[sid]
    est = sid in AR_IDS or sid == "RBC"
    cells = [esc(r0["insurer"])]
    for ln in ("Individual insurance", "Individual annuity", "Group insurance", "Group annuity"):
        b = BL.get((sid, ln))
        cells.append(f2(b["lp_30y"], est) if b else "—")
        cells.append("" if sid == "MEDIAN" else (bn(b["liabilities_bn"]) if b and sid not in AR_IDS else "—"))
    w = wtd.get(sid)
    cells.append(f2(w["weighted_premium_30y"], est) if w else "")
    b = BL.get((sid, "Seg funds (individual)"))
    cells.append(f2(b["lp_30y"], sid == "RBC") if b else "—")
    rows.append((cells, "rbc" if sid == "RBC" else ("med" if sid == "MEDIAN" else "")))
tb = table([("Insurer", "l"), ("Individual<br>insurance", "r"), ("$BN", "r dim"), ("Individual<br>annuity", "r"), ("$BN", "r dim"), ("Group<br>insurance", "r"), ("$BN", "r dim"),
            ("Group<br>annuity", "r"), ("$BN", "r dim"), ("Liability-<br>weighted<br>non-par", "r"), ("Seg funds<br>(separate)", "r")], rows, "tight")
page("Illiquidity premium by product line, 30 years",
     "Premium over the risk-free curve, %, with the liabilities each curve discounts ($BN, Canada, net of reinsurance). MFC, Empire Life, Co-operators Life, Foresters Life, ivari, Wawanesa Life and RBC Life file one premium for every non-par line; "
     "CLF, SLF, BMO Life and Equitable Life differentiate. Same row order as the previous table.",
     '<div class="split"><div class="c30">' + legend([("dot", S1, "Individual insurance"), ("dot", S2, "Individual annuity"), ("dot", S3, "Group annuity")]) + P.svg() + "</div>"
     '<div class="c70">' + tb + "</div></div>"
     '<p class="small">Liability-weighted: each non-par line\'s 30-year premium weighted by its net liabilities, over the lines with a filed curve. BMO Life filed no group annuity curve at Oct 31, 2025 ($6.1BN of liabilities); '
     "with its annuity premium applied its weighted premium would be 1.65%. Segregated fund guarantees are shown separately and are not in the weighted figure; negative values are as filed (ivari, Primerica). "
     "RBC Life's seg fund figure is its seg curve converted to spot, less BMO Life's risk-free rate.</p>")

# ------------------------------------------------------------------------------------------------ 10. par
prow = [r for r in par]
P = Plot(360, 40 + len(prow) * 24, 4.2, 6.8, 0, 1, ml=112, mr=14, mt=6, mb=26)
P.grid_x([4.5, 5.0, 5.5, 6.0, 6.5])
for i, r in enumerate(prow):
    yy = P.mt + 24 * i + 12
    isr = r["id"] == "RBC"
    if isr:
        P.raw(f'<rect x="0" y="{yy - 11:.1f}" width="{P.w}" height="22" fill="#e6eef8"/>')
    P.raw(f'<text x="{P.ml - 8}" y="{yy + 4:.1f}" text-anchor="end" class="lb"{" font-weight=\"600\" fill=\"" + C_RBC + "\"" if isr else ""}>{esc(r["insurer"])}</text>')
    a, b = num(r["filed_30y"]), num(r["dividend_scale_rate"])
    if a is not None and b is not None:
        P.raw(f'<line x1="{P.x(a):.1f}" x2="{P.x(b):.1f}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#c9ced6" stroke-width="2"/>')
    if a is not None:
        P.raw(f'<circle cx="{P.x(a):.1f}" cy="{yy:.1f}" r="4.5" fill="{S1}" stroke="#fff" stroke-width="2"/>')
    if b is not None:
        P.raw(f'<circle cx="{P.x(b):.1f}" cy="{yy:.1f}" r="4.5" fill="{S2}" stroke="#fff" stroke-width="2"/>')
rows = []
for r in prow:
    isr = r["id"] == "RBC"
    estp = r["risk_free_basis"].startswith("est")
    rows.append(([esc(r["insurer"]), bn(r["par_liabilities_bn"]), f2(r["dividend_scale_rate"]), f2(r["par_premium_30y"], estp), esc(r["filed_curve"]).replace(" (annual report)", " (AR)"),
                  f2(r["filed_10y"], isr), f2(r["filed_20y"], isr), f2(r["filed_30y"], isr), f2(r["filed_80y"], isr), f2(r["filed_premium_30y"], isr or r["id"] in AR_IDS),
                  "—" if num(r["gap_bp_30y"]) is None else f'{num(r["gap_bp_30y"]):+.0f}'], rowcls(r)))
tb = table([("Insurer", "l"), ("Par<br>liabilities<br>($BN)", "r"), ("Dividend<br>scale rate<br>2025", "r"), ("Premium<br>over 30y<br>risk-free", "r"), ("Filed curve", "l"),
            ("Filed<br>10y", "r"), ("Filed<br>20y", "r"), ("Filed<br>30y", "r"), ("Filed<br>80y", "r"), ("Filed<br>premium<br>30y", "r"), ("Scale less<br>filed 30y<br>(bp)", "r")], rows, "tight")
page("Participating account: dividend scale interest rate against the filed par curve",
     "Par is shown separately from the non-par General Account. As before, the dividend scale interest rate for 2025 is taken as the par discount rate, flat at every tenor; the par curve each insurer files is beside it. "
     "Rows run from the largest par book to the smallest (OSFI LF3 par liabilities in Canada, net of reinsurance; iA from its published par account size).",
     '<div class="split"><div class="c35">' + legend([("dot", S1, "Filed par curve, 30 years"), ("dot", S2, "Dividend scale interest rate")]) + P.svg() + "</div>"
     '<div class="c65">' + tb + "</div></div>"
     '<p class="small">The dividend scale rate is one rate for the year, so its premium is measured at one date for everyone: over the insurer\'s own Dec 31 risk-free rate at 30 years, or the Dec 31 median of the OSFI filers where it files none (e). '
     "Equitable Life files its par curve flat at 6.42%, in line with its scale rate. RBC Life's par curve was a flat 5.4% until fiscal Q4 2025 and now has the forward shape of its other lines; the spot equivalent is shown. "
     "The ALM repo has no par discount method, so this page keeps the earlier one. Dividend scale rates: PolicyAdvisor table, RBC Life and Equitable Life confirmed on their own sites. ivari, Wawanesa Life and Beneva publish no scale rate.</p>")

# ------------------------------------------------------------------------------------------------ 11. ultimates and liquidity buckets
rows = []
for r in ult:
    isr = r["id"] == "RBC"
    rows.append(([esc(r["insurer"]), f2(r["ultimate_risk_free"]), f2(r["ultimate_premium"]), f2(r["ultimate_rate"]) + ("*" if isr else ""),
                  esc(r["sensitivity_treatment"].replace("not in the ALM repo's sensitivity set", "not captured"))], rowcls(r)))
tb1 = table([("Insurer", "l"), ("Ultimate<br>risk-free", "r"), ("Ultimate<br>premium", "r"), ("Ultimate<br>rate", "r"), ("Held constant in the disclosed rate sensitivity", "l wrap")], rows, "tight")
bk = {}
for r in buckets:
    bk.setdefault(r["id"], {"insurer": r["insurer"], "source": r["source"]})[int(r["tenor"])] = r
rows = []
for sid in ("IAG", "DFS", "BEN", "ASL", "EQL", "EMP", "CLF", "MFC"):
    b = bk[sid]
    kind = {"EMP": "range across portfolios", "CLF": "range across products, group level", "MFC": "illiquid vs somewhat liquid"}.get(sid, "most vs least illiquid")
    rows.append(([esc(b["insurer"]), kind, f2(b[10]["most"]), f2(b[10]["least"]), f2(b[10]["spread"]), f2(b[30]["most"]), f2(b[30]["least"]), f2(b[30]["spread"])], ""))
tb2 = table([("Insurer", "l"), ("What is disclosed", "l"), ("10y<br>high", "r"), ("10y<br>low", "r"), ("10y<br>spread", "r"), ("30y<br>high", "r"), ("30y<br>low", "r"), ("30y<br>spread", "r")], rows, "tight")
page("Ultimate assumptions and the spread between liquidity buckets",
     "Left: what each insurer assumes beyond the observable period (year 80 in OSFI filings, year 70 in annual reports), individual insurance. Right: how far the most illiquid curve sits above the least illiquid one, where an annual report shows both.",
     '<div class="split"><div class="c55"><h3>Ultimate rates</h3>' + tb1 +
     '<p class="small">* RBC Life files an ultimate forward rate of 4.10% with no split; its 80-year spot rate is 4.23% (est). Most filers use 3.65% risk-free plus 1.50% premium (5.15%). '
     "MFC (3.40% + 1.00%), SLF (3.45% + 1.50%), BMO Life, Canadian Premier and Primerica are lower. Sun Life discloses that a 10 bp cut in the ultimate risk-free rate costs $50MM of net income and $25MM of CSM (group level).</p></div>"
     '<div class="c45"><h3>Most against least illiquid curve, Dec 31, 2025</h3>' + tb2 +
     '<p class="small">OSFI collects only the most illiquid bucket, so every premium in this document is the top of each insurer\'s range. Where both ends are published the spread is 0.2 to 1.5 points at 30 years: '
     "liabilities in less illiquid buckets carry less premium than the tables show. RBC Life publishes one curve. Beneva's least illiquid curve is above its most illiquid curve at 1 year, as published.</p></div></div>")

# ------------------------------------------------------------------------------------------------ 12. asset mix and trend
P = Plot(480, 340, -3, 55, 0.5, 2.8, ml=48, mr=20, mb=36)
P.grid_y([0.5, 1.0, 1.5, 2.0, 2.5], "{:.1f}%")
P.axis_x([0, 10, 20, 30, 40, 50], labels=["0%", "10%", "20%", "30%", "40%", "50%"], title="Private fixed income, % of non-par General Account")
lab_off = {"RBC": (9, 4), "MFC": (8, 4), "SLF": (-8, 4), "CLF": (8, 4), "EQL": (8, 4), "BMO": (-2, -9), "EMP": (8, 0), "IVA": (8, 8), "COP": (8, 4), "IOF": (8, 12), "WAW": (8, -2)}
for r in mix:
    xv, yv = num(r["private_fixed_income_pct"]), num(r["weighted_premium_30y"])
    isr = r["id"] == "RBC"
    if isr:
        P.raw(f'<line x1="{P.x(xv):.1f}" x2="{P.x(xv):.1f}" y1="{P.y(lo30):.1f}" y2="{P.y(hi30):.1f}" stroke="{C_RBC}" stroke-width="7" opacity="0.3" stroke-linecap="round"/>')
    P.dot(xv, yv, C_RBC if isr else "#7d8590", r=5.5 if isr else 4.5, hollow=(r["estimate"] == "Y" and not isr))
    dx, dy = lab_off.get(r["id"], (8, 4))
    P.text(xv, yv, esc(r["insurer"]), dx=dx, dy=dy, anchor="end" if dx < 0 else "start", color=C_RBC if isr else None, bold=isr)
sc_svg = P.svg()


def trend_chart(t, ymin, ymax, ticks):
    P = Plot(430, 170, -0.3, 3.3, ymin, ymax, ml=44, mr=64, mt=8, mb=24)
    P.grid_y(ticks, "{:.1f}%")
    pairs = ["fy2023", "fy2024", "fy2025", "mid2026"]
    P.axis_x([0, 1, 2, 3], labels=["Dec 2023", "Oct / Dec 2024", "Oct / Dec 2025", "Jun / Jul 2026"])
    rr = [T24[(p, t)] for p in pairs]
    P.band([(i, num(r["peer_min"])) for i, r in enumerate(rr)], [(i, num(r["peer_max"])) for i, r in enumerate(rr)])
    P.line([(i, num(r["peer_median"])) for i, r in enumerate(rr)], C_MED, 2)
    P.line([(i, num(r["rbc_premium_vs_td"])) for i, r in enumerate(rr)], C_RBC, 1.5, dash="4 3")
    P.line([(i, num(r["rbc_premium"])) for i, r in enumerate(rr)], C_RBC, 2.5)
    for i, r in enumerate(rr):
        a, m = num(r["rbc_premium"]), num(r["peer_median"])
        up = a is None or a >= m
        if a is not None:
            P.dot(i, a, C_RBC, r=4)
            P.text(i, a, f"{a:.2f}", anchor="middle", dy=-9 if up else 16, color=C_RBC, bold=True)
        P.dot(i, m, C_MED, r=3.5)
        P.text(i, m, f"{m:.2f}", anchor="middle", dy=16 if up else -9)
    a, m = num(rr[-1]["rbc_premium"]), num(rr[-1]["peer_median"])
    close = abs(a - m) < 0.35 * (ymax - ymin) / 2.3
    P.text(3, a, "RBC Life", dx=12, dy=(-2 if a >= m else 12) if close else 4, color=C_RBC, bold=True)
    P.text(3, m, "Peer median", dx=12, dy=(12 if a >= m else -2) if close else 4, bold=True)
    return P.svg()


page("Does the asset mix support the premium, and how has it moved?",
     "Left: 30-year premium (liability-weighted across non-par lines) against the share of private fixed income in the non-par General Account, from the ALM repo's asset allocation by block. "
     "Right: premiums at fiscal year ends, individual insurance, OSFI filers.",
     '<div class="split"><div class="c50"><h3>Premium against private fixed income share, fiscal 2025</h3>' +
     legend([("dot", C_RBC, "RBC Life (bar: range by risk-free reference)"), ("dot", "#7d8590", "Peer, entity = Canada"), ("ring", "#7d8590", "Peer, asset mix estimated")]) + sc_svg +
     '<p class="small">No relationship across peers: SLF and CLF hold the most private fixed income and file premiums at or below the median; RBC Life and MFC file the highest premiums with 19% and 25%. '
     "A top-down premium can also come from public corporate spread, so this is a prompt for the question, not an answer. MFC and SLF use the global mix (ALM repo rule); CLF and Equitable Life are part estimated. "
     "The four annual-report insurers, Canadian Premier and Primerica are not in the ALM repo's allocation set.</p></div>"
     '<div class="c50"><h3>30-year premium</h3>' + legend([("line", C_RBC, "RBC Life, over BMO Life risk-free (est)"), ("dash", C_RBC, "RBC Life, over TD Life risk-free (est)"), ("line", C_MED, "Peer median"), ("band", C_BAND, "Peer range")]) +
     trend_chart(30, 0.5, 2.8, [0.5, 1.0, 1.5, 2.0, 2.5]) + "<h3>10-year premium</h3>" + trend_chart(10, 0.5, 2.3, [0.5, 1.0, 1.5, 2.0]) +
     '<p class="small">RBC Life began filing in fiscal 2024. Peer premiums narrowed after 2023 while RBC Life\'s 30-year premium rose by about 0.5 to 0.7 points in fiscal 2025. '
     "At 10 years RBC Life has stayed inside the peer range except at Oct 31, 2025 on the BMO curve.</p></div></div>")

# ------------------------------------------------------------------------------------------------ 13. method
nc = read("not_covered.csv")
page("Method, sources, limitations and next steps",
     "The cdn-life-insurer-alm repository is the primary framework. The earlier method is used only where the repository is silent, and each such use is named below.",
     f"""<div class="cols3 small">
<div><h2>Method (ALM repo)</h2><ul class="fx">
<li><b>Scope.</b> Canadian business, legal entities as in the ALM repo. Non-par General Account lines first; par and segregated funds separately. Peer set: the project's 20 insurers. Blumont, TD Life and CIBC Life are in the ALM repo but outside the peer set; the last two serve only as Oct 31 risk-free references.</li>
<li><b>Source.</b> OSFI LF2, "Risk free rates and liquidity premium by line of business", Canada, most illiquid bucket only, from the repo's cleaned OSFI panel. Each filer reports a discount rate or a premium over its own risk-free curve; the other is derived.</li>
<li><b>Basis.</b> Spot. RBC Life's 1-year forwards are compounded annually, linear between filed points (L17). Checks: 30-year spot 5.75%, step 5.74%, premium 2.49% (1.78% in 2024), equal to the repo's figures.</li>
<li><b>Date.</b> Periods by date. Dec 31 curves are restated to Oct 31 for years 1 to 30: own premium plus BMO Life's Oct 31 risk-free curve (repo script curve_band). Ultimate rates are not restated.</li>
<li><b>Premium.</b> Over the filer's own risk-free curve. RBC Life: over BMO Life's same-date curve (est).</li>
<li><b>Size.</b> Insurance contract liabilities in Canada by line, net of reinsurance (repo file icl_by_line; Canadian Premier and Primerica computed here from the same OSFI LF3 codes).</li>
</ul></div>
<div><h2>Fallbacks to the earlier method</h2><ul class="fx">
<li><b>Annual-report insurers.</b> iA and Desjardins curves come from the ALM repo's filings panel; Beneva and Assumption Life from the earlier analysis (Beneva checked against the repo's copy of its annual report). They publish one curve for all products and no risk-free curve; premiums are over the median Dec 31 risk-free curve of the OSFI filers (est).</li>
<li><b>Par.</b> Dividend scale interest rate as the par discount rate, as agreed in October.</li>
<li><b>Not covered.</b> {"; ".join(esc(r["insurer"]) + ": " + esc(r["status"]) for r in nc)}.</li></ul>
<h2>Limitations</h2><ul class="fx">
<li>RBC Life's forward basis is inferred from the curve's shape and is not confirmed (L17).</li>
<li>Risk-free curves differ between insurers by up to 0.5 points on one date (Oct 31: 3.26% to 3.75% at 30 years). Premiums over own risk-free are not strictly comparable; total rates on one date are the firmer comparison.</li>
<li>OSFI collects only the most illiquid bucket. Liabilities in other buckets carry lower premiums.</li>
<li>Liabilities by line include CSM and are a size measure, not the cash flows discounted on each curve.</li>
<li>BMO Life's curves are from BMO Life Assurance Company; its liabilities by line from BMO Life Insurance Company (as in the ALM repo).</li>
</ul></div>
<div><h2>Next steps</h2><ul class="fx">
<li><b>Confirm internally</b> whether RBC Life's filed curve is forward rates, and the risk-free curve and illiquidity premium behind it. Non-public.</li>
<li><b>Size the effect.</b> Fulfilment cash flows, CSM and LICAT on a peer-median premium need liability cash flows by line. Non-public; modelling stage. Directional read: a lower premium raises the liability, most for PRT cash flows at 15 to 40 years.</li>
<li><b>Yield hurdle.</b> Compare the premium by tenor with the net yield of the assets backing each line (ALM repo next steps 1 to 3: allocation by product line, duration and key-rate gaps). Non-public.</li>
<li><b>Risk-free basis.</b> Ask why BMO Life's Oct 31, 2025 risk-free curve sits below TD Life's and CIBC Life's, and log the reference-curve sensitivity in the ALM repo's limitations register.</li>
<li><b>Refresh</b> at fiscal 2026 year end (RBC Life and BMO Life: Oct 31, 2026).</li></ul>
<h2>Files</h2><p>Code and data: analysis/discount_curves in abiddobani/InsuranceCompanies (build.py, make_report.py, out/*.csv). Interactive version: the "Insurer discount curves" dashboard.</p></div>
</div>""", "Sources: OSFI open data and 2025 annual reports, via MooseDragon/cdn-life-insurer-alm. " + KEYLINE)

# ------------------------------------------------------------------------------------------------ assemble
CSS = """
@page { size: 11in 8.5in; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: Inter, 'Helvetica Neue', Arial, sans-serif; color: #1f2329; font-size: 11px; line-height: 1.4; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.page { width: 11in; height: 8.5in; padding: 0.42in 0.5in 0.5in; position: relative; page-break-after: always; overflow: hidden; }
h1 { font-size: 19px; margin: 0 0 4px; letter-spacing: -0.2px; }
h2 { font-size: 13px; margin: 0 0 6px; }
h3 { font-size: 11.5px; margin: 0 0 4px; }
.sub { color: #5d6470; margin: 0 0 12px; max-width: 9.6in; font-size: 11px; }
.small { font-size: 10px; color: #444b55; }
p.small { margin: 8px 0 0; }
.tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.tile { border: 1px solid #dfe3e8; border-radius: 8px; padding: 10px 14px; }
.tl { font-size: 11px; color: #444b55; } .tv { font-size: 26px; font-weight: 700; margin: 2px 0; } .rbcv { color: #0051a5; } .tn { font-size: 9.5px; color: #5d6470; }
.cols2 { display: grid; grid-template-columns: 1.15fr 1fr; gap: 28px; }
.cols3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 22px; }
ul.fx { margin: 0; padding-left: 16px; } ul.fx li { margin-bottom: 6px; }
.split { display: flex; gap: 22px; align-items: flex-start; }
.c30 { width: 31%; } .c35 { width: 36%; } .c40 { width: 43%; } .c45 { width: 44%; } .c50 { width: 50%; } .c55 { width: 56%; } .c60 { width: 57%; } .c65 { width: 64%; } .c70 { width: 69%; }
svg { max-width: 100%; height: auto; display: block; }
.tk { font-size: 9.5px; fill: #5d6470; } .lb { font-size: 10px; fill: #1f2329; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 14px; margin: 0 0 6px; font-size: 10px; color: #444b55; }
.lg { display: inline-flex; align-items: center; gap: 5px; } .sw { width: 18px; height: 3px; display: inline-block; border-radius: 2px; } .dt { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
table { border-collapse: collapse; width: 100%; font-size: 10px; font-variant-numeric: tabular-nums; }
th { font-weight: 600; color: #444b55; border-bottom: 1.5px solid #8a909b; padding: 3px 5px; vertical-align: bottom; line-height: 1.2; font-size: 9.5px; }
td { padding: 3.2px 5px; border-bottom: 1px solid #e6e8ec; white-space: nowrap; }
td.wrap { white-space: normal; font-size: 9.2px; line-height: 1.25; color: #444b55; }
.l { text-align: left; } .r { text-align: right; } td.dim { color: #7a818c; }
tr.rbc td { background: #e6eef8; color: #0051a5; font-weight: 600; } tr.rbc td.wrap { font-weight: 400; }
tr.med td { font-weight: 700; border-bottom: 1.5px solid #8a909b; }
sup { font-size: 7px; color: #7a818c; font-weight: 400; }
.foot { position: absolute; left: 0.5in; right: 0.5in; bottom: 0.24in; font-size: 8.5px; color: #7a818c; display: flex; justify-content: space-between; border-top: 1px solid #e6e8ec; padding-top: 4px; }
"""
total = len(pages)
doc = "<!doctype html><html><head><meta charset='utf-8'><title>Peer discount curves and illiquidity premiums, fiscal 2025</title><style>" + CSS + "</style></head><body>"
for i, pg in enumerate(pages, 1):
    doc += pg.replace('<div class="foot"><span>', '<div class="foot"><span>').replace("</span></div></section>",
                                                                                       f"</span><span>Peer discount curves, fiscal 2025 &nbsp; {i} / {total}</span></div></section>")
doc += "</body></html>"
htm = os.path.join(OUTDIR, "report.html")
with open(htm, "w", encoding="utf-8") as fh:
    fh.write(doc)
js = f"""
const {{ chromium }} = require('playwright');
(async () => {{
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('file://{htm}'); await p.pdf({{ path: '{PDF}', width: '11in', height: '8.5in', printBackground: true }});
  await b.close();
}})();
"""
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
subprocess.run(["node", fh.name], check=True, env={**os.environ, "NODE_PATH": subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()})
os.unlink(fh.name)
print(PDF, total, "pages")
