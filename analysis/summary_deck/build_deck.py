"""Build the peer landscape summary deck (PowerPoint) from the three analyses.

Run from the repository root after the three build scripts:
    python3 analysis/discount_curves/build.py
    python3 analysis/portfolio_composition/build.py
    python3 analysis/investment_risk/build.py
    python3 analysis/summary_deck/build_deck.py
then export to PDF with LibreOffice (see README.md).

Follows the financial-analysis plugin's competitive-analysis standards: insight titles,
real chart objects, 14pt minimum text, sources on every slide, RBC Life highlighted.
"""
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION, XL_MARKER_STYLE, XL_TICK_LABEL_POSITION
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[2]
A = ROOT / "analysis"
OUT = Path(__file__).resolve().parent / "peer-landscape-summary.pptx"

NAVY = RGBColor(0x1F, 0x3A, 0x5F)
GRAY = RGBColor(0x9A, 0xA5, 0xB1)
DARK = RGBColor(0x33, 0x33, 0x33)
MUTED = RGBColor(0x6B, 0x72, 0x80)
ACCENT = RGBColor(0xD9, 0x82, 0x2B)
ACCENT_TINT = RGBColor(0xFB, 0xEB, 0xD9)
HEADER = RGBColor(0xE6, 0xE8, 0xEB)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
STACK = [NAVY, RGBColor(0x4A, 0x6F, 0x9C), RGBColor(0x8F, 0xAE, 0xD1), ACCENT, GRAY]
FONT = "Arial"
FOCUS = "RBC Life"
MARK = "▸ "

# ---------------------------------------------------------------- data
LS = pd.read_csv(A / "investment_risk/dashboard/landscape.csv")
EAR = pd.read_csv(A / "investment_risk/dashboard/earnings_at_risk.csv")
DC = pd.read_csv(A / "discount_curves/landscape_2025q4.csv")
PP = pd.read_csv(A / "discount_curves/dashboard/product_points.csv")
PAR = pd.read_csv(A / "discount_curves/dashboard/par_vs_dividend_rate.csv")
PC = pd.read_csv(A / "portfolio_composition/portfolio_composition_pct.csv")
OBS = pd.read_csv(A / "portfolio_composition/off_balance_sheet.csv")

SHORT = {
    "iA Financial Group": "iA Financial", "iA Financial": "iA Financial",
    "Foresters Life (incl. Canada Protection Plan)": "Foresters Life",
    "Canadian Premier Life": "Canadian Premier", "Canadian Premier": "Canadian Premier",
    "Desjardins Insurance": "Desjardins",
}


def short(name):
    return SHORT.get(name, name)


def label(name):
    n = short(name)
    return MARK + n if n == FOCUS else n


LS["name"] = LS.company.map(short)
rbc = LS[LS.company_id == "rbc_life"].iloc[0]
med = LS.select_dtypes("number").median()


def rank_desc(col, value=None):
    s = LS[col].dropna()
    v = rbc[col] if value is None else value
    return int((s > v).sum() + 1), len(s)


# Discount curves (headline: most illiquid, individual non-par, YE2025)
DC["name"] = DC.company.map(short)
dc_rbc = DC[DC.company_id == "rbc_life"].iloc[0]
TENORS = [1, 5, 10, 20, 30, 70]
il = PP[(PP.period == "2025Q4") & (PP["product"] == "Individual life")].set_index("company")

# Portfolio Level 2 groups
L2 = {
    "Public fixed income": ["Asset Backed Securities", "Corporate Bonds", "Government Bonds", "Bonds (issuer n/d)"],
    "Public equity": ["Common Shares", "Preferred Shares"],
    "Private fixed income": ["Commercial Mortgages", "Illiquid Term Loans", "Private Liquid Loans", "Co-Investments",
                             "Policy & Other Loans"],
    "Alternatives (RE, infra, PE, private debt)": ["Real Estate Equity", "Infrastructure Equity", "Other Private Equity",
                                                  "Infrastructure Debt", "Structured Products", "Other Private Debt"],
    "Cash and other": ["Cash", "Other / Unclassified"],
}
for k, cols in L2.items():
    PC[k] = PC[cols].sum(axis=1)
PC["name"] = PC.company.map(short)

# Off balance sheet, % of portfolio
obs = OBS.copy()
obs["kind"] = obs.level2.where(obs.level1 == "Derivatives", "Repos").where(obs.level1 == "Derivatives", "Repos")
rep = obs[obs.level3 == "Repos"].groupby("company").amount_cad_mm.sum()

# ---------------------------------------------------------------- pptx helpers
prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]
PAGE = [0]


def run_fmt(run, size, bold=False, color=DARK, italic=False):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color


def textbox(slide, x, y, w, h, paras, size=16, color=DARK, bold=False, align=PP_ALIGN.LEFT,
            anchor=MSO_ANCHOR.TOP, bullet=False, space=6):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    for i, p in enumerate(paras if isinstance(paras, list) else [paras]):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = align
        para.space_after = Pt(space)
        parts = p if isinstance(p, list) else [(p, bold)]
        if bullet:
            parts = [("•  ", False)] + parts
        for txt, b in parts:
            r = para.add_run()
            r.text = txt
            run_fmt(r, size, b, color)
    return tb


def new_slide(title, source=None):
    s = prs.slides.add_slide(BLANK)
    PAGE[0] += 1
    textbox(s, 0.5, 0.3, 12.3, 1.15, title, size=28, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE, space=0)
    line = s.shapes.add_connector(1, Inches(0.5), Inches(1.5), Inches(12.83), Inches(1.5))
    line.line.color.rgb = GRAY
    line.line.width = Pt(1)
    if source:
        textbox(s, 0.5, 6.78, 11.4, 0.6, source, size=14, color=MUTED, space=0)
    textbox(s, 12.0, 6.95, 0.83, 0.4, str(PAGE[0]), size=14, color=MUTED, align=PP_ALIGN.RIGHT, space=0)
    return s


def style_axis(axis, size=14, fmt=None, visible_grid=False):
    axis.tick_labels.font.size = Pt(size)
    axis.tick_labels.font.name = FONT
    axis.tick_labels.font.color.rgb = DARK
    axis.has_major_gridlines = visible_grid
    if visible_grid:
        axis.major_gridlines.format.line.color.rgb = HEADER
    axis.format.line.color.rgb = GRAY
    if fmt:
        axis.tick_labels.number_format = fmt
        axis.tick_labels.number_format_is_linked = False


def bar_chart(slide, x, y, w, h, cats, values, fmt='0.0', highlight=None, horizontal=True, series_name="Value",
              label_size=14, color=NAVY, axis_fmt=None, gap=40, vmin=None, vmax=None):
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series(series_name, values)
    kind = XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED
    gf = slide.shapes.add_chart(kind, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    ch = gf.chart
    ch.has_legend = False
    ch.has_title = False
    ch.font.name = FONT
    ch.font.size = Pt(14)
    plot = ch.plots[0]
    plot.gap_width = gap
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format = fmt
    dl.number_format_is_linked = False
    dl.font.size = Pt(label_size)
    dl.font.name = FONT
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    ser = plot.series[0]
    ser.format.fill.solid()
    ser.format.fill.fore_color.rgb = color
    ser.invert_if_negative = False
    sdl = ser.data_labels
    sdl.show_value = True
    sdl.number_format = fmt
    sdl.number_format_is_linked = False
    sdl.font.size = Pt(label_size)
    sdl.font.name = FONT
    sdl.position = XL_LABEL_POSITION.OUTSIDE_END
    for i, c in enumerate(cats):
        if highlight and c.endswith(highlight):
            pt = ser.points[i]
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = ACCENT
            pt.data_label.font.bold = True
            pt.data_label.font.size = Pt(label_size)
            pt.data_label.number_format = fmt
            pt.data_label.position = XL_LABEL_POSITION.OUTSIDE_END
    ca, va = ch.category_axis, ch.value_axis
    style_axis(ca)
    style_axis(va, fmt=axis_fmt or fmt, visible_grid=True)
    ca.tick_label_position = XL_TICK_LABEL_POSITION.LOW
    if horizontal:
        ca.reverse_order = True
    va.visible = False
    if vmin is not None:
        va.minimum_scale = vmin
    if vmax is not None:
        va.maximum_scale = vmax
    return ch


def legend_bottom(ch, size=14):
    ch.has_legend = True
    ch.legend.position = XL_LEGEND_POSITION.BOTTOM
    ch.legend.include_in_layout = False
    ch.legend.font.size = Pt(size)
    ch.legend.font.name = FONT


def table(slide, x, y, w, rows, col_w, row_h=0.36, size=14, focus_col=0, align=None, header_wrap=True):
    nr, nc = len(rows), len(rows[0])
    gt = slide.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(w), Inches(row_h * nr))
    t = gt.table
    for j, cw in enumerate(col_w):
        t.columns[j].width = Inches(cw)
    for i in range(nr):
        t.rows[i].height = Inches(row_h)
        is_focus = i > 0 and focus_col < nc and str(rows[i][focus_col]).replace(MARK, "") == FOCUS
        for j in range(nc):
            cell = t.cell(i, j)
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = HEADER if i == 0 else (ACCENT_TINT if is_focus else WHITE)
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            a = (align[j] if align else ("l" if j == 0 else "r"))
            p.alignment = {"l": PP_ALIGN.LEFT, "r": PP_ALIGN.RIGHT, "c": PP_ALIGN.CENTER}[a]
            r = p.add_run()
            r.text = str(rows[i][j])
            run_fmt(r, size, bold=(i == 0 or is_focus), color=DARK)
    return t


def fmt(v, f="{:.1f}", na="n/d"):
    return na if pd.isna(v) else f.format(v)


def balls(v, s, higher=True):
    """Harvey-ball rating by tercile within the peer distribution s."""
    if pd.isna(v):
        return "–"
    s = s.dropna()
    q1, q2 = s.quantile(1 / 3), s.quantile(2 / 3)
    n = 3 if v >= q2 else (2 if v >= q1 else 1)
    if not higher:
        n = 4 - n
    return "●" * n + "○" * (3 - n)


# ---------------------------------------------------------------- numbers used in titles
cap_rank, cap_n = rank_desc("capital_ratio_pct")
cap_low_rank = cap_n - cap_rank + 1
repo_rank, repo_n = rank_desc("repo_pct")
pc_rank, pc_n = rank_desc("private_credit_pct")
size_rank, size_n = rank_desc("portfolio_cad_mm")
repos_sorted = LS[["name", "repo_pct"]].dropna().sort_values("repo_pct", ascending=False)
next_repo = repos_sorted.iloc[1]
liab = DC.set_index("name").liability_vs_median_per_10bn_mm
liab_pct = DC.set_index("name").liability_vs_median_pct
par_ye = PAR[(PAR.view == "Year end 2025") & PAR.dsir_less_flat_bp.notna()].copy()
par_ye["name"] = par_ye.company.map(short)
par_gap_rbc = int(par_ye.set_index("name").loc[FOCUS, "dsir_less_flat_bp"])
par_pos = par_ye[par_ye.dsir_less_flat_bp > 0].dsir_less_flat_bp
ear = EAR.copy()
ear["name"] = ear.company.map(short)
ear = ear.sort_values("total_cad_mm", ascending=False)
ear_med = ear.total_cad_mm.median()
limit_25 = 35 * 25 / 28  # Abid's C$35MM earnings limit on ~C$28Bn, pro-rated to C$25Bn
rbc_il, med_il = il.loc["RBC Life"], il.loc["Peer median"]

SRC_IR = "Source: OSFI LCQ (LICAT) and LF2/LF3 returns, FY2025 Q4 (RBC Life, BMO Life: Oct 2025); AMF/annual reports for iA, Beneva, Assumption, Humania. Analysis: analysis/investment_risk."

# ================================================================= 1. Title
s = prs.slides.add_slide(BLANK)
PAGE[0] += 1
bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
bg.fill.solid(); bg.fill.fore_color.rgb = NAVY; bg.line.fill.background()
textbox(s, 0.8, 2.0, 11.7, 1.6, "Canadian life & health insurers: peer investment landscape", size=40, bold=True,
        color=WHITE)
textbox(s, 0.8, 3.6, 11.7, 1.4, ["RBC Life against 19 peers: discount curves, portfolio composition and "
                                 "investment risk (market, credit, liquidity)"], size=20, color=WHITE)
textbox(s, 0.8, 5.6, 11.7, 1.0, ["Data as at year end 2025 and the latest 2026 filings. Prepared 28 October 2026.",
                                 "Built with the financial-analysis plugin's competitive-analysis framework."],
        size=16, color=RGBColor(0xC8, 0xD3, 0xE0), space=2)

# ================================================================= 2. Executive summary
s = new_slide("RBC Life runs a high-quality but thinly capitalised book, with two concentrations peers do not have",
              "Source: analyses on the following slides; peer medians exclude no insurer. Scale: C$ general-account "
              "invested assets at each insurer's latest filing.")
pts = [
    [("Scale and capital. ", True), (f"RBC Life is the {size_rank}th largest general account (C${rbc.portfolio_cad_mm/1e3:.1f}Bn of {size_n}) "
      f"but its {rbc.capital_ratio_pct:.0f}% LICAT ratio is the {['', '', 'second', 'third', 'fourth'][cap_low_rank]}-lowest of {cap_n}, "
      f"{med.capital_ratio_pct - rbc.capital_ratio_pct:.0f} points under the {med.capital_ratio_pct:.0f}% median.", False)],
    [("Discount curve. ", True), (f"Its IFRS 17 curve values liabilities {abs(liab_pct[FOCUS]):.2f}% below the peer median "
      f"(C${abs(liab[FOCUS]):.0f}MM per C$10Bn), inside a C${liab.max() - liab.min():.0f}MM range from iA (most generous) "
      f"to Primerica (most conservative).", False)],
    [("Portfolio mix. ", True), (f"Public bonds dominate ({PC.set_index('name').loc[FOCUS, 'Public fixed income']:.0f}%), "
      f"private credit is {rbc.private_credit_pct:.1f}% ({pc_rank}th highest of {pc_n}) and alternatives are small "
      f"({PC.set_index('name').loc[FOCUS, 'Alternatives (RE, infra, PE, private debt)']:.1f}%).", False)],
    [("Concentrations. ", True), (f"{rbc.energy_pct_corp:.1f}% of corporate bonds are coded Energy (median {med.energy_pct_corp:.1f}%) "
      f"and repos fund {rbc.repo_pct:.1f}% of the portfolio, about {rbc.repo_pct / next_repo.repo_pct:.0f}x the next peer.", False)],
    [("Par and disclosure. ", True), (f"RBC's filed par curve sits {par_gap_rbc} bp under its dividend scale rate, the widest gap; "
      f"it publishes no market sensitivities, while disclosing peers lose C${ear.total_cad_mm.min():.0f}–{ear.total_cad_mm.max():.0f}MM "
      f"on a C$25Bn book in moderate shocks.", False)],
]
textbox(s, 0.6, 1.75, 12.1, 5.0, pts, size=17, bullet=True, space=14)

# ================================================================= 3. Peer map (tiers + coverage)
s = new_slide("Twenty insurers in five strategic groups; RBC Life competes with BMO Life as the bank-owned pair",
              "Source: OSFI, AMF and FCNB registers; general-account size from the portfolio composition analysis "
              "(latest filing, C$Bn). Coverage gaps listed on the method slide.")
size = PC.set_index("name").portfolio_cad_mm / 1e3
tiers = [
    ("Big three groups", "Listed, global, OSFI", ["Manulife", "Sun Life", "Canada Life"]),
    ("Quebec and mutual leaders", "AMF; iA listed, Desjardins and Beneva cooperative/mutual", ["iA Financial", "Desjardins", "Beneva"]),
    ("Bank-owned", "OSFI, October fiscal year", ["RBC Life", "BMO Life"]),
    ("Mid-size", "OSFI; stock, mutual and Sagicor-owned", ["ivari", "Empire Life", "Equitable Life", "Co-operators Life", "Wawanesa Life"]),
    ("Niche and small", "OSFI, AMF, FCNB; fraternal, mutual, distribution-led", ["Foresters Life", "Canadian Premier", "Primerica Life",
                                                                             "Assumption Life", "UV Insurance", "Humania"]),
]
rows = [["Group", "Ownership / regulator", "Insurers (general account, C$Bn)"]]
for g, o, names in tiers:
    rows.append([g, o, ";  ".join(f"{n} {size[n]:.1f}" if n in size and pd.notna(size[n]) else f"{n} n/d" for n in names)])
t = table(s, 0.5, 1.75, 12.3, rows, [2.6, 3.6, 6.1], row_h=0.66, align=["l", "l", "l"])
for i, (g, o, names) in enumerate(tiers, start=1):
    if FOCUS in names:
        for j in range(3):
            t.cell(i, j).fill.fore_color.rgb = ACCENT_TINT
            for r in t.cell(i, j).text_frame.paragraphs[0].runs:
                r.font.bold = True
textbox(s, 0.5, 6.3, 12.3, 0.45, "Canada Protection Plan reports inside Foresters Life; Desjardins' life portfolio is not "
        "published apart from Desjardins Group (n/d).", size=14, color=MUTED)

# ================================================================= 4. Positioning: risk-taking vs capital
s = new_slide("Positioning: RBC Life takes median-level investment risk on a below-median capital buffer",
              "Source: LICAT total ratio (OSFI LCQ FY2025 Q4; CARLI/solvency ratio for iA, Beneva, Assumption, Humania); "
              "return-seeking = equity, real estate, PE + private credit, % of general account. UV and Desjardins: no ratio.")
pos = LS.dropna(subset=["capital_ratio_pct", "risk_assets_pct", "private_credit_pct"]).copy()
pos["x"] = pos.risk_assets_pct + pos.private_credit_pct
cd = XyChartData()
others = cd.add_series("Peers")
for _, r in pos[pos.company_id != "rbc_life"].iterrows():
    others.add_data_point(r.x, r.capital_ratio_pct)
foc = cd.add_series("RBC Life")
foc.add_data_point(rbc.risk_assets_pct + rbc.private_credit_pct, rbc.capital_ratio_pct)
mx, my = pos.x.median(), pos.capital_ratio_pct.median()
vline = cd.add_series("Median return-seeking")
vline.add_data_point(mx, 120); vline.add_data_point(mx, 215)
hline = cd.add_series("Median capital ratio")
hline.add_data_point(0, my); hline.add_data_point(65, my)
gf = s.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER, Inches(0.5), Inches(1.65), Inches(8.6), Inches(5.1), cd)
ch = gf.chart
ch.has_title = False
ch.has_legend = False
ch.font.name = FONT; ch.font.size = Pt(14)
names_o = pos[pos.company_id != "rbc_life"].name.tolist()
LABEL_POS = {"Wawanesa Life": XL_LABEL_POSITION.ABOVE, "Assumption Life": XL_LABEL_POSITION.RIGHT,
             "Canadian Premier": XL_LABEL_POSITION.LEFT, "iA Financial": XL_LABEL_POSITION.LEFT,
             "ivari": XL_LABEL_POSITION.BELOW, "BMO Life": XL_LABEL_POSITION.LEFT,
             "Co-operators Life": XL_LABEL_POSITION.BELOW, "Equitable Life": XL_LABEL_POSITION.ABOVE,
             "Empire Life": XL_LABEL_POSITION.LEFT}
for i, ser in enumerate(ch.series):
    if i in (0, 1):
        ser.format.line.fill.background()
        ser.marker.style = XL_MARKER_STYLE.CIRCLE
        ser.marker.size = 9 if i == 0 else 13
        ser.marker.format.fill.solid()
        ser.marker.format.fill.fore_color.rgb = NAVY if i == 0 else ACCENT
        ser.marker.format.line.fill.background()
        labels = names_o if i == 0 else ["RBC Life"]
        for k, lab in enumerate(labels):
            dl = ser.points[k].data_label
            dl.has_text_frame = True
            dl.text_frame.text = lab
            dl.position = LABEL_POS.get(lab, XL_LABEL_POSITION.RIGHT)
            for p in dl.text_frame.paragraphs:
                for r in p.runs:
                    run_fmt(r, 12 if i == 0 else 14, bold=(i == 1), color=DARK if i == 0 else ACCENT)
    else:
        ser.marker.style = XL_MARKER_STYLE.NONE
        ser.format.line.color.rgb = GRAY
        ser.format.line.width = Pt(1.25)
        ser.format.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        ser.smooth = False
va, ca = ch.value_axis, ch.category_axis
va.minimum_scale, va.maximum_scale = 120, 215
ca.minimum_scale, ca.maximum_scale = 0, 65
style_axis(va, fmt='0"%"', visible_grid=False)
style_axis(ca, fmt='0"%"')
va.has_title = ca.has_title = True
va.axis_title.text_frame.text = "LICAT / solvency ratio"
ca.axis_title.text_frame.text = "Return-seeking assets, % of general account"
for ax in (va, ca):
    for p in ax.axis_title.text_frame.paragraphs:
        for r in p.runs:
            run_fmt(r, 14, color=DARK)
textbox(s, 9.3, 1.8, 3.6, 4.8, [
    [("Reading the map", True)],
    f"Dashed lines are peer medians: {mx:.0f}% return-seeking assets and a {my:.0f}% capital ratio.",
    f"RBC Life: {rbc.risk_assets_pct + rbc.private_credit_pct:.0f}% return-seeking, {rbc.capital_ratio_pct:.0f}% capital ratio. "
    "It sits with the big three and ivari in the lower half: similar risk appetite, thinner buffer.",
    "Equitable Life takes the most risk (equities 36%) but holds a 159% ratio; Foresters and Primerica hold the most capital.",
], size=14, space=10)

# ================================================================= 5. RBC Life profile (target)
s = new_slide("RBC Life profile: fifth-largest book, investment-grade bonds, the lowest disclosure in the peer set",
              "Source: OSFI LCQ, LF2, LF3 (RBC Life Insurance Company, legal entity, FY to 31 Oct 2025; portfolio at "
              "31 Jul 2026); par account size: PolicyAdvisor 2026. n/d = not disclosed.")
rows = [["Metric", "RBC Life", "Peer median"],
        ["General account (C$Bn)", f"{rbc.portfolio_cad_mm/1e3:.1f}", f"{med.portfolio_cad_mm/1e3:.1f}"],
        ["LICAT total ratio", f"{rbc.capital_ratio_pct:.0f}%", f"{med.capital_ratio_pct:.0f}%"],
        ["Market risk capital, % invested", f"{rbc.market_cap_pct_inv:.1f}%", f"{med.market_cap_pct_inv:.1f}%"],
        ["Credit risk capital, % invested", f"{rbc.credit_cap_pct_inv:.1f}%", f"{med.credit_cap_pct_inv:.1f}%"],
        ["Equity, RE and PE, % portfolio", f"{rbc.risk_assets_pct:.1f}%", f"{med.risk_assets_pct:.1f}%"],
        ["Private credit, % portfolio", f"{rbc.private_credit_pct:.1f}%", f"{med.private_credit_pct:.1f}%"],
        ["Below investment grade, % bonds", f"{rbc.below_ig_pct_bonds:.2f}%", f"{med.below_ig_pct_bonds:.2f}%"],
        ["Liquidity-weighted assets", f"{rbc.weighted_liquidity_pct:.1f}%", f"{med.weighted_liquidity_pct:.1f}%"],
        ["Individual life 30y premium", f"{rbc_il.lp_30y:.2f}%", f"{med_il.lp_30y:.2f}%"],
        ["Market sensitivities", "n/d", "10 of 20 disclose"]]
table(s, 0.5, 1.75, 6.3, rows, [3.5, 1.4, 1.4], row_h=0.43, focus_col=99)
rows = [["Category", "Assessment"],
        ["Business", "Royal Bank of Canada's life insurer: individual life, living benefits, annuities (group and individual)."],
        ["Strengths", "99.9% investment-grade bonds; 31.6% government bonds; near-zero credit losses (ECL 0.7 bp)."],
        ["Weaknesses", f"LICAT {rbc.capital_ratio_pct:.0f}% vs {med.capital_ratio_pct:.0f}% median; 37.6% Energy coding; "
                       "repos 14.1% of portfolio; no sensitivities published."],
        ["Posture", "Long-duration public bonds plus private placements (11.7%); little real estate or PE; "
                    "derivative and repo overlay for ALM."]]
table(s, 7.1, 1.75, 5.73, rows, [1.45, 4.28], row_h=0.95, focus_col=99, align=["l", "l"])

# ================================================================= 6. Discount curves: liability vs median
s = new_slide(f"Discount curves: RBC Life is at the peer median; iA to Primerica spans C${liab.max() - liab.min():.0f}MM "
              "of liability per C$10Bn",
              "Source: OSFI LF2 P35035–P35065 (most illiquid curve, individual non-par), Q4 2025; iA, Desjardins, Beneva, "
              "Assumption 2025 annual reports. Stylised liability: payments falling 4%/yr over 80 years. Analysis: analysis/discount_curves.")
d = DC.sort_values("liability_vs_median_per_10bn_mm")
bar_chart(s, 0.5, 1.65, 8.3, 5.1, [label(n) for n in d.name], d.liability_vs_median_per_10bn_mm.round(0).tolist(),
          fmt='+0;-0;0', highlight=FOCUS, series_name="C$MM per C$10Bn")
textbox(s, 9.0, 1.8, 3.85, 4.8, [
    [("Liability vs peer median, C$MM per C$10Bn", True)],
    "Negative = higher discount rates, smaller liability (more generous). Positive = more conservative.",
    f"RBC Life: {liab[FOCUS]:+.0f} ({liab_pct[FOCUS]:+.2f}%). Its forward-shaped curve is above the median at 20–30 years "
    f"(30y premium {dc_rbc.lp_30y:.2f}%) and below it at 10 and 70+ years, which nets out.",
    "Manulife carries the highest 30y premium (2.05%) but the lowest ultimate risk-free rate (3.40%).",
], size=14, space=10)

# ================================================================= 7. RBC curve vs peer range + product table
s = new_slide("RBC Life's curve runs above the peer median at 20–30 years and below it at the long end",
              "Source: as previous slide; product lines from OSFI LF2 by line of business, Q4 2025. RBC Life rates "
              "are filed as one-year forwards and converted to spot (interpretation, not stated by OSFI).")
cd = CategoryChartData()
cd.categories = [f"{t}y" for t in TENORS]
cols = [f"dr_{t}y" for t in TENORS]
peers_dc = DC[DC.company_id != "rbc_life"]
cd.add_series("Peer high", peers_dc[cols].max().round(2).tolist())
cd.add_series("Peer median", DC[cols].median().round(2).tolist())
cd.add_series("Peer low", peers_dc[cols].min().round(2).tolist())
cd.add_series("RBC Life", dc_rbc[cols].astype(float).round(2).tolist())
gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(0.5), Inches(1.65), Inches(6.6), Inches(5.0), cd)
ch = gf.chart
ch.has_title = False
ch.font.name = FONT; ch.font.size = Pt(14)
for ser, colr, wdt, dash in zip(ch.series, [GRAY, NAVY, GRAY, ACCENT], [1.5, 2.5, 1.5, 3.0],
                                [MSO_LINE_DASH_STYLE.DASH, None, MSO_LINE_DASH_STYLE.DASH, None]):
    ser.format.line.color.rgb = colr
    ser.format.line.width = Pt(wdt)
    if dash:
        ser.format.line.dash_style = dash
    ser.smooth = False
    ser.marker.style = XL_MARKER_STYLE.CIRCLE
    ser.marker.size = 6
    ser.marker.format.fill.solid(); ser.marker.format.fill.fore_color.rgb = colr
    ser.marker.format.line.fill.background()
style_axis(ch.category_axis)
style_axis(ch.value_axis, fmt='0.0"%"', visible_grid=True)
ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 2.5, 6.5
legend_bottom(ch)
rows = [["Product, 30y", "RBC rate", "Median", "RBC prem.", "Median"]]
for prod in ["Individual life", "Individual annuity", "Group annuity"]:
    pr = PP[(PP.period == "2025Q4") & (PP["product"] == prod)].set_index("company")
    rows.append([prod, f"{pr.loc['RBC Life', 'dr_30y']:.2f}%", f"{pr.loc['Peer median', 'dr_30y']:.2f}%",
                 f"{pr.loc['RBC Life', 'lp_30y']:.2f}%", f"{pr.loc['Peer median', 'lp_30y']:.2f}%"])
table(s, 7.3, 1.8, 5.53, rows, [1.97, 0.9, 0.9, 0.9, 0.86], row_h=0.5, focus_col=99)
textbox(s, 7.3, 4.0, 5.53, 2.6, [
    "RBC files the same curve for all non-par lines, so its 30y rate (5.75%) and premium (1.72%) exceed the "
    "median for every product.",
    f"At 80 years RBC's spot rate is {rbc_il.dr_80y:.2f}% against a {med_il.dr_80y:.2f}% median; its filed ultimate "
    "forward is 4.10%.",
], size=14, bullet=True, space=10)

# ================================================================= 8. Par vs DSIR
s = new_slide(f"Par: dividend scale rates run {par_pos.min():.0f}–{par_pos.max():.0f} bp above filed par curves; "
              f"RBC Life's {par_gap_rbc} bp gap is the widest",
              "Source: OSFI LF2 par curves (flat-equivalent rate on the stylised liability), Q4 2025; annual-report curves "
              "for iA, Desjardins, Assumption; dividend scale interest rates 2025: PolicyAdvisor, RBC and Equitable sites.")
p = par_ye.sort_values("dsir_less_flat_bp", ascending=False)
cd = CategoryChartData()
cd.categories = [label(n) for n in p.name]
cd.add_series("Filed par curve, flat-equivalent", p.flat_equivalent.round(2).tolist())
cd.add_series("Dividend scale interest rate", p.dsir.round(2).tolist())
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.5), Inches(1.65), Inches(8.3), Inches(5.1), cd)
ch = gf.chart
ch.has_title = False
ch.font.name = FONT; ch.font.size = Pt(14)
pl = ch.plots[0]; pl.gap_width = 50; pl.overlap = -10
pl.has_data_labels = True
pl.data_labels.number_format = '0.00'; pl.data_labels.number_format_is_linked = False
pl.data_labels.font.size = Pt(12); pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
for ser, colr in zip(ch.series, [GRAY, NAVY]):
    ser.format.fill.solid(); ser.format.fill.fore_color.rgb = colr
style_axis(ch.category_axis); ch.category_axis.reverse_order = True
style_axis(ch.value_axis, fmt='0.0', visible_grid=True)
ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 0, 7.5
ch.value_axis.visible = False
legend_bottom(ch)
rows = [["Insurer", "Gap, bp", "Par acct C$MM"]]
for _, r in p.iterrows():
    rows.append([label(r["name"]), f"{r.dsir_less_flat_bp:+.0f}", fmt(r.par_account_mm, "{:,.0f}")])
table(s, 9.0, 1.7, 3.83, rows, [1.85, 0.9, 1.08], row_h=0.36, size=14)
textbox(s, 9.0, 1.7 + 0.36 * len(rows) + 0.15, 3.83, 1.0, "RBC's par account is small (C$51MM), so the gap matters "
        "more for disclosure than for its balance sheet.", size=14, color=MUTED)

# ================================================================= 9. Portfolio mix
s = new_slide(f"Portfolio: RBC Life is {PC.set_index('name').loc[FOCUS, 'Public fixed income']:.0f}% public bonds with "
              "few alternatives; big three and Equitable lean on private assets",
              "Source: OSFI LF2 P21012/LF1 (OSFI filers, mid-2026); Q2 2026 supplements for Manulife, Sun Life, Great-West "
              "Lifeco, iA; 2025 annual reports for Beneva, UV, Humania, Assumption. General account only; Desjardins not published.")
pcs = PC.sort_values("portfolio_cad_mm", ascending=False)
cd = CategoryChartData()
cd.categories = [label(n) for n in pcs.name]
for k in L2:
    cd.add_series(k, (pcs[k] / 100).round(4).tolist())
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_STACKED_100, Inches(0.5), Inches(1.6), Inches(12.3), Inches(5.2), cd)
ch = gf.chart
ch.has_title = False
ch.font.name = FONT; ch.font.size = Pt(14)
pl = ch.plots[0]; pl.gap_width = 35; pl.overlap = 100
for si, (ser, colr) in enumerate(zip(ch.series, STACK)):
    ser.format.fill.solid(); ser.format.fill.fore_color.rgb = colr
    ser.format.line.color.rgb = WHITE
    vals = (pcs[list(L2)[si]]).tolist()
    for i, v in enumerate(vals):
        if v >= 9:
            dl = ser.points[i].data_label
            dl.has_text_frame = True
            dl.text_frame.text = f"{v:.0f}%"
            dl.position = XL_LABEL_POSITION.CENTER
            for r in dl.text_frame.paragraphs[0].runs:
                run_fmt(r, 12, bold=cd.categories[i].label.startswith(MARK),
                        color=WHITE if si in (0, 1, 3) else DARK)
style_axis(ch.category_axis, size=13); ch.category_axis.reverse_order = True
style_axis(ch.value_axis, fmt='0%', visible_grid=True)
ch.value_axis.visible = False
legend_bottom(ch)

# ================================================================= 10. Sub-class detail
s = new_slide("RBC Life overweights government bonds and public equity, and holds the least cash of the larger peers",
              "Source: as previous slide; % of general account. Peer median across the 18 charted insurers. "
              "Private placements are mapped to illiquid term loans.")
sub = ["Corporate Bonds", "Government Bonds", "Asset Backed Securities", "Common Shares", "Preferred Shares",
       "Commercial Mortgages", "Illiquid Term Loans", "Policy & Other Loans", "Cash", "Real Estate Equity",
       "Infrastructure Equity", "Other Private Equity"]
comp = ["RBC Life", "BMO Life", "Canada Life", "iA Financial", "Empire Life", "Sun Life", "Manulife"]
pcx = PC.set_index("name")
medsub = PC[sub].median()
rows = [["% of general account"] + [MARK + "RBC Life", "Median"] + comp[1:]]
for c in sub:
    rows.append([c.replace("Illiquid Term Loans", "Private placements / term loans")] +
                [f"{pcx.loc['RBC Life', c]:.1f}", f"{medsub[c]:.1f}"] + [f"{pcx.loc[n, c]:.1f}" for n in comp[1:]])
t = table(s, 0.5, 1.7, 12.3, rows, [3.5] + [1.1] * 8, row_h=0.37, size=14)
for i in range(len(rows)):
    c = t.cell(i, 1)
    c.fill.fore_color.rgb = ACCENT_TINT
    for r in c.text_frame.paragraphs[0].runs:
        r.font.bold = True

# ================================================================= 11. Off-balance-sheet
s = new_slide(f"RBC Life funds {rbc.repo_pct:.1f}% of its portfolio with repos, about "
              f"{rbc.repo_pct / next_repo.repo_pct:.0f}x the next peer ({next_repo['name']}, {next_repo.repo_pct:.1f}%)",
              "Source: OSFI LF3 P21110 derivative notionals and P22030 row 280 repos, FY2025 (legal entity); iA and "
              "Manulife financial statement notes. Securities lending and ISN are not disclosed by any peer.")
ob = LS.dropna(subset=["derivative_notional_pct"]).sort_values("derivative_notional_pct", ascending=False)
cd = CategoryChartData()
cd.categories = [label(n) for n in ob.name]
cd.add_series("Derivative notional, % of portfolio", ob.derivative_notional_pct.round(1).tolist())
cd.add_series("Repos, % of portfolio", ob.repo_pct.fillna(0).round(1).tolist())
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.5), Inches(1.65), Inches(8.3), Inches(5.1), cd)
ch = gf.chart
ch.has_title = False
ch.font.name = FONT; ch.font.size = Pt(14)
pl = ch.plots[0]; pl.gap_width = 50; pl.overlap = -10
pl.has_data_labels = True
pl.data_labels.number_format = '0.0'; pl.data_labels.number_format_is_linked = False
pl.data_labels.font.size = Pt(12); pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
for ser, colr in zip(ch.series, [GRAY, NAVY]):
    ser.format.fill.solid(); ser.format.fill.fore_color.rgb = colr
rp = ch.series[1].points[list(ob.name).index(FOCUS)]
rp.format.fill.solid(); rp.format.fill.fore_color.rgb = ACCENT
style_axis(ch.category_axis); ch.category_axis.reverse_order = True
style_axis(ch.value_axis, fmt='0', visible_grid=True)
ch.value_axis.visible = False
ch.value_axis.maximum_scale = 140
legend_bottom(ch)
rbc_obs = OBS[OBS.company_id == "rbc_life"]
OBS_LABEL = {("Encumbered Assets", "Repos"): "Repos", ("Currency", "FX forwards, futures, swaps, options"): "FX derivatives",
             ("Equity", "Linear and non-linear (not split)"): "Equity derivatives",
             ("Fixed Income", "Linear"): "Rate derivatives, linear", ("Fixed Income", "Non-Linear"): "Rate derivatives, non-linear"}
textbox(s, 9.0, 1.8, 3.85, 4.8, [
    [("RBC Life, 31 Oct 2025 (C$MM)", True)],
    *[f"{OBS_LABEL.get((r.level2, r.level3), r.level3)}: {r.amount_cad_mm:,.0f} ({r.pct_of_portfolio * 100:.1f}%)"
      for _, r in rbc_obs.iterrows()],
    "Repos add leverage and a collateral call in a rate spike. Only iA (5.0%), Sun Life (1.4%) and Manulife (0.3%) "
    "report any.",
], size=14, space=8)

# ================================================================= 12. Capital
lic = LS.dropna(subset=["capital_ratio_pct"]).sort_values("capital_ratio_pct", ascending=False)
s = new_slide(f"Capital: RBC Life's {rbc.capital_ratio_pct:.0f}% LICAT ratio is the third-lowest of {cap_n}, "
              f"{med.capital_ratio_pct - rbc.capital_ratio_pct:.0f} points below the {med.capital_ratio_pct:.0f}% median",
              SRC_IR)
bar_chart(s, 0.5, 1.65, 7.0, 5.1, [label(n) for n in lic.name], lic.capital_ratio_pct.round(0).tolist(), fmt='0"%"',
          highlight=FOCUS, series_name="Capital ratio", vmin=0, vmax=240)
osfi = LS.dropna(subset=["market_cap_pct_inv"]).sort_values("portfolio_cad_mm", ascending=False)
rows = [["LICAT capital, % invested", "Market", "Credit"]]
for _, r in osfi.iterrows():
    rows.append([label(r["name"]), f"{r.market_cap_pct_inv:.1f}", f"{r.credit_cap_pct_inv:.1f}"])
rows.append(["Median", f"{med.market_cap_pct_inv:.1f}", f"{med.credit_cap_pct_inv:.1f}"])
table(s, 7.8, 1.65, 5.03, rows, [2.83, 1.1, 1.1], row_h=0.335, size=14)

# ================================================================= 13. Credit
en = LS.dropna(subset=["energy_pct_corp"]).sort_values("energy_pct_corp", ascending=False)
s = new_slide(f"Credit: RBC Life's bonds are 99.9% investment grade, but {rbc.energy_pct_corp:.1f}% of its corporates "
              f"are coded Energy, {rbc.energy_pct_corp / med.energy_pct_corp:.1f}x the median",
              "Source: OSFI LF3 P21030 bonds by issuer sector (FY2025 Q4); LF2 P21020 ECL; LF3 P21050 problem mortgages; "
              "rating splits from YE2025 annual reports. RBC files no Utilities line, so the Energy share may reflect coding.")
bar_chart(s, 0.5, 1.65, 6.6, 5.1, [label(n) for n in en.name], en.energy_pct_corp.round(1).tolist(), fmt='0.0"%"',
          highlight=FOCUS, series_name="Energy, % corporate bonds", vmin=0, vmax=45)
rows = [["Credit metric", "RBC Life", "Median"],
        ["Below investment grade, % bonds", f"{rbc.below_ig_pct_bonds:.2f}", f"{med.below_ig_pct_bonds:.2f}"],
        ["BBB, % bonds", fmt(rbc.bbb_pct_bonds), f"{med.bbb_pct_bonds:.1f}"],
        ["Private credit, % portfolio", f"{rbc.private_credit_pct:.1f}", f"{med.private_credit_pct:.1f}"],
        ["ECL allowance, bp invested", f"{rbc.ecl_bps_inv:.1f}", f"{med.ecl_bps_inv:.1f}"],
        ["Problem mortgages, %", f"{rbc.mortgage_problem_pct:.2f}", f"{med.mortgage_problem_pct:.2f}"],
        ["Largest sector, % corporates", f"{rbc.top_sector} {rbc.top_sector_pct:.1f}", f"{med.top_sector_pct:.1f}"],
        ["LICAT credit capital, % inv.", f"{rbc.credit_cap_pct_inv:.2f}", f"{med.credit_cap_pct_inv:.2f}"]]
table(s, 7.3, 1.7, 5.53, rows, [3.13, 1.3, 1.1], row_h=0.45, focus_col=99)
textbox(s, 7.3, 5.45, 5.53, 1.2, "Manulife carries the most credit risk (4.0% below IG, 19 bp ECL); Sun Life the most "
        "problem mortgages (1.2%).", size=14, color=MUTED)

# ================================================================= 14. Liquidity
lq = LS.dropna(subset=["weighted_liquidity_pct"]).sort_values("weighted_liquidity_pct", ascending=False)
s = new_slide(f"Liquidity: RBC Life's liquidity-weighted assets ({rbc.weighted_liquidity_pct:.0f}%) sit at the "
              f"median ({med.weighted_liquidity_pct:.0f}%); the big three run the least liquid books",
              "Source: latest general-account mix (portfolio composition analysis). Weights after Doff's weighted "
              "liquidity ratio (illustrative): cash 100%, govt 95%, public corporates 85%, ABS and shares 70%, "
              "mortgages 50%, private debt 40%, RE/PE 20%, policy loans 0%.")
bar_chart(s, 0.5, 1.65, 7.6, 5.1, [label(n) for n in lq.name], lq.weighted_liquidity_pct.round(1).tolist(),
          fmt='0.0"%"', highlight=FOCUS, series_name="Liquidity-weighted assets", vmin=0, vmax=100)
textbox(s, 8.4, 1.8, 4.45, 4.8, [
    [("RBC Life vs median", True)],
    f"Cash and government bonds (tier 1): {rbc.liquid_tier1_pct:.1f}% vs {med.liquid_tier1_pct:.1f}%.",
    f"All public, liquid assets (tiers 1–2): {rbc.liquid_tier12_pct:.1f}% vs {med.liquid_tier12_pct:.1f}%.",
    f"The weighted ratio ignores funding: the {rbc.repo_pct:.1f}% repo book draws on the same government "
    "bonds that make up RBC's liquid tier.",
    "Only Manulife (60%) and Great-West Lifeco (51%) publish their own liquid-asset measure.",
], size=14, space=10)

# ================================================================= 15. Earnings at risk
s = new_slide(f"Market risk: moderate shocks cost disclosing peers C${ear.total_cad_mm.min():.0f}–"
              f"{ear.total_cad_mm.max():.0f}MM on a C$25Bn book; RBC Life publishes no sensitivities",
              "Source: YE2025 MD&A and FS sensitivity notes, scaled to C$25Bn of invested assets; ±100 bp and −15% shocks "
              "scaled linearly; undiversified sum, gains count as zero. Detail: analysis/investment_risk/disclosed_sensitivities.csv.")
cd = CategoryChartData()
cd.categories = [f"{n} ({t:,.0f})" for n, t in zip(ear.name, ear.total_cad_mm)]
for col, nm in [("rates_cad_mm", "Rates ±50 bp (worse)"), ("spreads_cad_mm", "Spreads +50 bp"),
                ("equity_cad_mm", "Equity −10%"), ("alts_cad_mm", "Alternatives −10%")]:
    cd.add_series(nm, ear[col].fillna(0).round(1).tolist())
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_STACKED, Inches(0.5), Inches(1.65), Inches(8.3), Inches(5.1), cd)
ch = gf.chart
ch.has_title = False
ch.font.name = FONT; ch.font.size = Pt(14)
pl = ch.plots[0]; pl.gap_width = 45; pl.overlap = 100
for ser, colr in zip(ch.series, [NAVY, RGBColor(0x8F, 0xAE, 0xD1), GRAY, ACCENT]):
    ser.format.fill.solid(); ser.format.fill.fore_color.rgb = colr
style_axis(ch.category_axis); ch.category_axis.reverse_order = True
style_axis(ch.value_axis, fmt='0', visible_grid=True)
ch.value_axis.maximum_scale = 400
legend_bottom(ch)
textbox(s, 9.0, 1.8, 3.85, 4.8, [
    [("Earnings at risk, C$MM (total in brackets)", True)],
    "After tax where disclosed; Wawanesa and Empire as disclosed, Foresters pre-tax.",
    f"Peer median C${ear_med:.0f}MM. Equity and alternatives drive the large groups; rates drive Wawanesa, Empire "
    "and Foresters.",
    f"For reference: a C$35MM earnings limit on C$28Bn is about C${limit_25:.0f}MM on C$25Bn. Only Assumption Life's "
    "disclosed shocks fit inside it.",
    "RBC Life, BMO Life, ivari, Co-operators, Canadian Premier and Primerica publish no sensitivities.",
], size=14, space=10)

# ================================================================= 16-17. Scorecard
sc = LS.merge(DC[["company_id", "liability_vs_median_pct"]], on="company_id", how="left")
sc = sc.merge(EAR[["company_id", "total_cad_mm"]], on="company_id", how="left")
sc = sc.sort_values("portfolio_cad_mm", ascending=False, na_position="last")
dims = [("portfolio_cad_mm", "Scale C$Bn", lambda v: f"{v/1e3:.1f}", True),
        ("capital_ratio_pct", "Capital ratio", lambda v: f"{v:.0f}%", True),
        ("liability_vs_median_pct", "Curve vs median", lambda v: f"{v:+.1f}%", True),
        ("risk_assets_pct", "Equity, RE, PE", lambda v: f"{v:.0f}%", True),
        ("private_credit_pct", "Private credit", lambda v: f"{v:.0f}%", True),
        ("weighted_liquidity_pct", "Liquidity", lambda v: f"{v:.0f}%", True),
        ("total_cad_mm", "EaR C$MM", lambda v: f"{v:.0f}", True)]


def score_rows(df):
    rows = [["Insurer"] + [d[1] for d in dims]]
    for _, r in df.iterrows():
        row = [label(r["name"])]
        for col, _, f, hi in dims:
            v = r[col]
            row.append("–" if pd.isna(v) else f"{balls(v, sc[col], hi)} {f(v)}")
        rows.append(row)
    return rows


for part, chunk, ttl in [
    (1, sc.iloc[:10], "Scorecard (1/2): among the ten largest books, only Canada Life and ivari hold less "
                      "capital than RBC Life"),
    (2, sc.iloc[10:], "Scorecard (2/2): smaller peers hold more capital and liquidity; Wawanesa Life carries "
                      "the most earnings at risk (C$336MM)"),
]:
    s = new_slide(ttl, "●●● = top third of peers on that metric (highest value), ●○○ = bottom third. Curve vs median: "
                       "liability on own curve vs peer median (negative = more generous). EaR: earnings at risk on C$25Bn "
                       "(slide 15). – = not available.")
    table(s, 0.5, 1.65, 12.3, score_rows(chunk), [2.55, 1.45, 1.45, 1.5, 1.35, 1.35, 1.3, 1.35],
          row_h=0.46, size=14, align=["l"] + ["c"] * 7)

# ================================================================= 18. Strategic context (M&A)
s = new_slide("Consolidation is reshaping the tail of the peer set; bank-owned insurers are pruning non-core blocks",
              "Source: Insurance Portal (9 Jun 2025); Sagicor press release (3 Oct 2023); Beneva and Canada Life "
              "announcements (Jan 2020); Insurance Business (Foresters/CPP). Deal multiples not disclosed (n/d).")
rows = [["Acquirer", "Target", "Date", "Deal value", "Multiple", "Rationale"],
        ["UV Insurance", "~200k BMO Life policies (incl. ~15k par)", "Jun 2025", "~C$50MM premiums", "n/d",
         "Assumption reinsurance; doubled UV's members, assets +35%"],
        ["Sagicor Financial", "ivari (from Wilton Re)", "Oct 2023", "C$375MM", "n/d",
         "Canadian platform for a TSX-listed Caribbean group"],
        ["SSQ + La Capitale", "Merger, now Beneva", "Jan 2020", "n/a (mutual)", "n/a",
         "Scale: Canada's largest mutual insurer"],
        ["Great-West Life", "London Life, Canada Life amalgamated", "Jan 2020", "n/a (internal)", "n/a",
         "One Canada Life brand and balance sheet"],
        ["Foresters Financial", "Canada Protection Plan", "2017", "n/d", "n/d",
         "No-medical / simplified issue distribution"]]
table(s, 0.5, 1.7, 12.3, rows, [2.1, 2.9, 1.15, 1.85, 1.1, 3.2], row_h=0.66, size=14,
      align=["l", "l", "l", "r", "r", "l"])
textbox(s, 0.5, 5.85, 12.3, 0.8, "For RBC Life: BMO's 2025 sale shows a bank-owned insurer exiting a closed block, "
        "a route to release capital if the 132% LICAT ratio becomes binding.", size=14, color=DARK)

# ================================================================= 19. Where advantage sits (moat)
s = new_slide("Scale is the clearest durable investment advantage: the big three originate private assets peers cannot",
              "Assessment based on the metrics in this deck: private credit and alternatives shares (scale), "
              "par and annuity in-force (switching costs), brand and bank distribution (intangibles).")
rows = [["Group", "Scale economies", "Switching costs", "Intangible assets", "Network effects"],
        ["Big three", "Strong: 19–38% private credit, own origination", "Strong: large par and annuity in-force",
         "Strong: global brands", "Weak"],
        ["iA, Desjardins, Beneva", "Moderate: 15.5% private credit at iA", "Moderate", "Strong in Quebec", "Weak"],
        [MARK + "Bank-owned (RBC, BMO)", "Moderate: RBC 19.4% private credit; BMO 2.8%", "Weak: small par (C$51MM at RBC)",
         "Strong: bank brand and branch distribution", "Weak"],
        ["Mid-size", "Weak: rely on public markets and equities", "Moderate: Equitable par 42% of liabilities",
         "Moderate", "Weak"],
        ["Niche and small", "Weak: 0–22% private assets", "Weak", "Niche distribution (Primerica, CPP)", "Weak"]]
t = table(s, 0.5, 1.7, 12.3, rows, [2.6, 2.9, 2.5, 2.7, 1.6], row_h=0.72, size=14, align=["l"] * 5)
textbox(s, 0.5, 6.3, 12.3, 0.5, "Network effects do not apply to investment portfolios; rated Weak throughout.",
        size=14, color=MUTED)

# ================================================================= 20. Synthesis for RBC Life
lic_h = pd.read_csv(ROOT / "data/osfi/licat_ratios.csv", skiprows=[1])
lic_h = lic_h[lic_h.company_id == "rbc_life"]
tot_col = [c for c in lic_h.columns if c.startswith("Total Ratio")][0]
lic_h = lic_h.set_index(lic_h.fiscal_year.astype(str) + lic_h.quarter)[tot_col].astype(float)
ph = pd.read_csv(A / "discount_curves/dashboard/premium_history.csv")
gap_now = (ph[(ph.company == "RBC Life") & (ph.period == "2026Q3")].lp_30y.iloc[0] - ph[ph.period == "2026Q3"].lp_30y.median()) * 100
TRAJ = (f"RBC Life's LICAT ratio has held at {lic_h.loc['2024Q1':].min():.0f}–{lic_h.loc['2024Q1':].max():.0f}% since fiscal 2024 "
        f"({lic_h['2026Q3']:.1f}% at fiscal Q3 2026), so the capital gap to peers is structural, not cyclical. Its 30y premium "
        f"lead over the median narrowed from +35 bp at YE2025 to {gap_now:+.0f} bp at Q3 2026.")
s = new_slide("For RBC Life: defend the clean credit book, fix the capital buffer, and explain the two concentrations",
              "Source: synthesis of slides 2–19. Quantified signposts are proposals for monitoring, not targets set by RBC Life.")
cols3 = [
    ("Durable advantages", ["99.9% investment-grade bonds; ECL 0.7 bp", "Discount curve at the peer median: "
                            "reserves neither aggressive nor conservative", "Bank brand and distribution (intangible)"]),
    ("Structural vulnerabilities", [f"LICAT {rbc.capital_ratio_pct:.0f}%, third-lowest; 27 points under median",
                                    f"Repos {rbc.repo_pct:.1f}% of portfolio; Energy {rbc.energy_pct_corp:.1f}% of corporates",
                                    "No sensitivities published; par curve 177 bp under DSIR"]),
    ("Signposts to watch", ["LICAT ratio below 125%", "Repos above 15% of portfolio or Energy above 40% of "
                            "corporates", "30y premium more than 50 bp above the peer median (+35 bp at YE2025)"]),
]
for i, (hdr, items) in enumerate(cols3):
    x = 0.5 + i * 4.15
    box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(1.75), Inches(3.95), Inches(3.75))
    box.shadow.inherit = False
    box.fill.solid(); box.fill.fore_color.rgb = ACCENT_TINT if i == 1 else RGBColor(0xF3, 0xF4, 0xF6)
    box.line.fill.background()
    textbox(s, x + 0.15, 1.85, 3.65, 0.6, hdr, size=20, bold=True, color=NAVY)
    textbox(s, x + 0.15, 2.5, 3.65, 3.0, items, size=16, bullet=True, space=12)
textbox(s, 0.5, 5.7, 12.3, 1.0, [[("Trajectory. ", True), (TRAJ, False)]], size=16)

# ================================================================= 21. Method and coverage
s = new_slide("Method, coverage and caveats",
              "Code and data: abiddobani/InsuranceCompanies, analysis/discount_curves, analysis/portfolio_composition, "
              "analysis/investment_risk, analysis/summary_deck.")
textbox(s, 0.5, 1.7, 6.0, 5.0, [
    [("Discount curves", True)],
    "Most illiquid curve (OSFI LF2 collects only that bucket); premiums for RBC Life and annual-report insurers "
    "measured over the median OSFI risk-free curve. 2023Q1 excluded (unit errors).",
    "Par: dividend scale interest rate used as the par rate; ivari, Wawanesa, Beneva have none.",
    [("Portfolio composition", True)],
    "General account only; par excluded only for Canada Life and Assumption (the only peers that split it). "
    "Beneva includes P&C. Level 1 assigned by asset class.",
], size=14, space=8)
textbox(s, 6.8, 1.7, 6.0, 5.0, [
    [("Investment risk", True)],
    "LICAT market and credit capital cover non-par only, legal entity. Big-three sensitivities are group-wide "
    "(Canada Life = Great-West Lifeco incl. Empower). Liquidity weights are illustrative.",
    [("Gaps", True)],
    "Humania and UV: no curve. Desjardins: no portfolio or capital ratio. Canada Protection Plan sits in Foresters. "
    "RBC's forward-rate reading and Energy coding are unconfirmed.",
    "All figures re-run on 28 Oct 2026; outputs match the earlier dashboards exactly.",
], size=14, space=8)

prs.save(OUT)
print("wrote", OUT, "slides:", len(prs.slides))
