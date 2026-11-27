"""Peer landscape summary deck on the cdn-life-insurer-alm framework.

One deck that summarises the eight peer analyses rebuilt on MooseDragon/cdn-life-insurer-alm:
discount curves, portfolio composition, investment risk, portfolio reallocations, CSM and surplus
durations, street wallet, org charts and insurer deep dives. It reads only the result tables in
inputs/ (copied from each analysis by collect_inputs.py) and recomputes nothing but medians,
ranks and differences of those tables.

Every slide is an HTML page (1280 x 720) with inline-SVG charts, printed to PDF with the
preinstalled Playwright Chromium. The .pptx carries the same slides: native title and source text,
the slide body as a 2x image.

    python3 analysis/summary_deck_alm/collect_inputs.py     # only to refresh inputs/
    python3 analysis/summary_deck_alm/build_deck.py

KEEP_HTML=path also saves the HTML. The build prints OVERFLOW [...] with any slide whose body
overflows; it should be empty.
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from charts import (BLUE, C1, C2, C3, C4, C5, C6, FADED, FOCUS, FOCUS_BG, GRID, INK, MARK, MUTED, OTHER, REF, RISK,
                    SEQ, SUB, b, band_lines, card, dotpair, dotstrip, esc, hbar, isnum, label, legend, ranges,
                    scatter, side, stacked, table)

HERE = Path(__file__).resolve().parent
IN = HERE / "inputs"
PDF_OUT = HERE / "peer-landscape-summary-alm.pdf"
PPTX_OUT = HERE / "peer-landscape-summary-alm.pptx"

# ---------------------------------------------------------------- names (ALM study short names)
NAME = {"RBC": "RBC Life", "BMO": "BMO Life", "MFC": "MFC", "SLF": "SLF", "CLF": "CLF", "EMP": "Empire Life",
        "IVA": "ivari", "EQL": "Equitable", "COP": "Co-operators Life", "IOF": "Foresters Life", "WAW": "Wawanesa Life",
        "BLU": "BLU", "IAG": "iA", "BEN": "Beneva", "DFS": "Desjardins", "CPL": "Canadian Premier",
        "PRI": "Primerica Life", "ASL": "Assumption Life", "HUM": "Humania", "UV": "UV Insurance",
        "CPP": "Canada Protection Plan"}
LONG_ID = {"rbc_life": "RBC", "bmo_life": "BMO", "manulife": "MFC", "sun_life": "SLF", "canada_life": "CLF",
           "empire_life": "EMP", "ivari": "IVA", "equitable_life": "EQL", "cooperators_life": "COP",
           "foresters_life": "IOF", "wawanesa_life": "WAW", "blumont": "BLU", "ia": "IAG", "beneva": "BEN",
           "desjardins": "DFS", "canadian_premier": "CPL", "primerica_life": "PRI", "assumption_life": "ASL",
           "humania": "HUM", "uv_insurance": "UV", "canada_protection_plan": "CPP"}
OSFI12 = ["RBC", "BMO", "MFC", "SLF", "CLF", "EMP", "IVA", "EQL", "COP", "IOF", "WAW", "BLU"]
ALLCAN9 = ["RBC", "BMO", "EMP", "IVA", "EQL", "COP", "IOF", "WAW", "BLU"]
BIG3 = ["MFC", "SLF", "CLF"]
nm = lambda i: NAME[LONG_ID.get(i, i)]
sid = lambda i: LONG_ID.get(i, i)


def rd(path, **kw):
    return pd.read_csv(IN / path, **kw)


def dt(s, year=True):
    """2025-10-31 -> Oct 31, 2025 (periods are shown by date, not by quarter label)."""
    t = pd.Timestamp(s)
    return f"{t:%b} {t.day}, {t.year}" if year else f"{t:%b} {t.day}"


def money(mm, d=1):
    """$MM / $BN, the study's units."""
    if abs(mm) >= 1000:
        return f"${mm / 1000:,.{d}f}BN"
    return f"${mm:,.0f}MM"


pct0 = lambda v: f"{v:.0f}%"
pct1 = lambda v: f"{v:.1f}%"
pct2 = lambda v: f"{v:.2f}%"
yrs = lambda v: f"{v:.1f}y"
def sgn(v, f="{:+,.0f}"):
    """Signed number with a true minus sign; a value that rounds to zero is shown unsigned."""
    t = f.format(v)
    if not any(ch in "123456789" for ch in t):
        return t.lstrip("+-")
    return t.replace("-", "−")


WORD = {7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}

# ---------------------------------------------------------------- data
MAN = json.loads((IN / "MANIFEST.json").read_text())
INFO = json.loads((IN / "investment_risk/build_info.json").read_text())
LS = rd("investment_risk/landscape.csv").set_index("id")
STATS = rd("investment_risk/peer_stats.csv").set_index("metric")
FACT = rd("investment_risk/facts.csv").set_index("key").value
LMIX = rd("investment_risk/licat_mix.csv")
LTR = rd("investment_risk/licat_trend.csv")
SENS = rd("investment_risk/sensitivities.csv")
CAPP = rd("investment_risk/rbc_capital_path.csv")
OUTS = rd("investment_risk/outside_study.csv")
DC = rd("discount_curves/headline_fy2025.csv").set_index("id")
BAND = rd("discount_curves/band.csv")
REFC = rd("discount_curves/reference_curve_check.csv")
PARC = rd("discount_curves/par_fy2025.csv").set_index("id")
ULT = rd("discount_curves/ultimates_and_basis.csv").set_index("id")
CTR = rd("discount_curves/trend.csv")
PEERS = rd("portfolio_composition/peers.csv")
PEERS["sid"] = PEERS.insurer.map(sid)
PEERS = PEERS.set_index("sid")
L3 = rd("portfolio_composition/block_mix_l3.csv")
L3["sid"] = L3.insurer.map(sid)
LIAB = rd("portfolio_composition/liabilities_by_line.csv")
BASIS = rd("portfolio_composition/basis_effect.csv").set_index("insurer")
CHG = rd("portfolio_reallocation/changes.csv")
CTX = rd("portfolio_reallocation/context.csv")
MIX = rd("portfolio_reallocation/mix_by_date.csv")
WAL = rd("street_wallet/wallet_by_insurer.csv")
WAL["sid"] = WAL.company_id.map(sid)
WAL = WAL.set_index("sid")
WDR = rd("street_wallet/wallet_by_driver.csv")
DUR = rd("csm_surplus_duration/results.csv").set_index("peer")
FVO = rd("csm_surplus_duration/fvoci.csv")
FVO = FVO[FVO.fiscal_year == 2025].set_index("peer")
DD = json.loads((IN / "insurer_deep_dive/alm.json").read_text())
DDC = {sid(k): v for k, v in DD["companies"].items()}
ORG = {sid(k): v for k, v in json.loads((IN / "org_charts/functions.json").read_text())["insurers"].items()}

rbc = LS.loc["RBC"]
A = PEERS[PEERS.tier == "A"]                     # ALM study view, OSFI returns (12)
A_oth = A.drop(index="RBC")
st = lambda m: STATS.loc[m]
ALM_COMMIT = INFO.get("alm_commit", INFO.get("commit", ""))[:7] if isinstance(INFO, dict) else ""

# ---- discount curves
dc_rbc, dc_med = DC.loc["RBC"], DC.loc["MEDIAN"]
dc_peers = DC.drop(index=["MEDIAN", "RBC"])
ref25 = REFC[(REFC.pair == "fy2025") & (REFC.tenor == 30)].set_index("reference")
ref_lo, ref_hi = ref25.rbc_premium.min(), ref25.rbc_premium.max()
band25 = BAND[(BAND.pair == "fy2025") & (BAND.line == "Individual insurance")].sort_values("tenor")
above = band25[band25.rbc_spot > band25.peer_max].tenor
first_above = int(above.min())
assert set(range(first_above, 31)) <= set(above), "RBC spot is not above the peer range through year 30"
ctr30 = CTR[CTR.tenor == 30].set_index("pair")

# ---- portfolio
rbc_p = A.loc["RBC"]
l3g = (L3[(L3.block == "GenAcct") & L3.sid.isin(OSFI12)]
       .pivot_table(index="l3", columns="sid", values="pct_of_block", aggfunc="sum").fillna(0))
l3_med = l3g.drop(columns="RBC").median(axis=1)
big3_priv = A.loc[BIG3, "pct_private_fixed_income"]

# ---- reallocation
rb = MIX[(MIX.short_id == "RBC") & MIX.scope.str.startswith("Non-par")]
rb_sh = rb.pivot_table(index="period_end_date", columns="level3", values="share_pct")
rb_mm = rb.pivot_table(index="period_end_date", columns="level3", values="amount_mm")
rb_tot = rb.groupby("period_end_date").block_total_mm.first()
d0, dfy, d1 = rb_sh.index[0], "2025-10-31", rb_sh.index[-1]
priv = (CHG[CHG.level2 == "Private Fixed Income"].groupby("short_id")
        .agg(first=("first_share_pct", "sum"), last=("last_share_pct", "sum"), chg=("change_pp", "sum"),
             fd=("first_date", "first"), ld=("last_date", "first")))
n_up = int((priv.chg > 0.05).sum())
ctx_rbc = CTX[CTX.short_id == "RBC"].set_index("period_end_date")
repo_chg = ctx_rbc.loc["2025-10-31", "repos_mm"] - ctx_rbc.loc["2024-10-31", "repos_mm"]
csm_chg = ctx_rbc.loc["2025-10-31", "abl_csm_mm"] - ctx_rbc.loc["2024-10-31", "abl_csm_mm"]
sur_chg = ctx_rbc.loc["2025-10-31", "surplus_mm"] - ctx_rbc.loc["2024-10-31", "surplus_mm"]
ll = DDC["RBC"]["liab_line"]
liab_chg = {k: ll["2025"][k] - ll["2024"][k] for k in ("Group annuity", "Individual insurance", "Group insurance", "Individual annuity")}
asset_chg = (rb_mm.loc["2025-10-31"] - rb_mm.loc["2024-10-31"])
earn = DDC["RBC"]["earn"]["2025"]
isr_share = {k: (v.get("earn") or {}).get("2025", {}).get("isr_share") for k, v in DDC.items()}
isr_peers = pd.Series({k: v for k, v in isr_share.items() if v is not None and k != "RBC"})

# ---- durations, wallet, org
dur_rbc = DUR.loc["RBC"]
wal_rbc = WAL.loc["RBC"]
wal20 = WAL[WAL.on_list_of_20 == 1]
wal_tot, wal_assets = wal20.cost_total_cad_mm.sum(), wal20.canadian_general_account_cad_mm.sum()
wal_bps_all = wal_tot / wal_assets * 1e4          # both in $MM
assert 1 < wal_bps_all < 20, wal_bps_all
seats = {k: sum(1 for s in v["seats"] if s["cert"] != "-") for k, v in ORG.items()}
seat_med = pd.Series({k: v for k, v in seats.items() if k != "RBC"}).median()

ORD = {1: "lowest", 2: "second-lowest", 3: "third-lowest", 4: "fourth-lowest"}
ORDH = {1: "highest", 2: "second-highest", 3: "third-highest", 4: "fourth-highest", 5: "fifth-highest"}
SLIDES = []


def slide(title, body, source, cls="", fill=False):
    SLIDES.append(dict(title=title, body=body, source=source, cls=cls, fill=fill))


SRC_ALM = (f"cdn-life-insurer-alm study (commit {ALM_COMMIT}): OSFI LF1 / LF2 / LF3 / LCQ returns and 2025 annual reports")
FYE = "Fiscal 2025 year-ends: RBC Life and BMO Life Oct 31, 2025; others Dec 31, 2025"

# ================================================================= 1. Title
kpis = [
    ("LICAT total ratio", pct1(rbc.licat_pct), f"median of the eight other all-Canada filers {st('licat_pct')['median']:.1f}%"),
    ("Buffer, % of General Account", pct1(rbc.buffer_pct), f"median of the eleven other OSFI peers {st('buffer_pct')['median']:.1f}%"),
    ("30-year illiquidity premium (est)", pct2(dc_rbc.lp_30y), f"peer median {dc_med.lp_30y:.2f}%; {ref_lo:.2f}% to {ref_hi:.2f}% by reference curve"),
    ("Private fixed income, % of General Account", pct1(rbc_p.pct_private_fixed_income), f"peer median {A_oth.pct_private_fixed_income.median():.1f}%; Big 3 {big3_priv.min():.0f}% to {big3_priv.max():.0f}% (est)"),
    ("Repos, % of General Account", pct1(rbc.repos_ga), f"{rbc.repos_ga_fy24:.1f}% a year earlier; {int(FACT['osfi_peers_nil_repos'])} of 11 OSFI peers report none"),
]
slide("Canadian life insurers: peer landscape on the ALM framework",
      '<div style="display:flex;flex-direction:column;gap:18px;width:100%">'
      '<p class="lead">RBC Life against its Canadian peers, rebuilt on the cdn-life-insurer-alm study: discount curves, portfolio '
      'composition and reallocation, investment risk, CSM and surplus durations, street wallet, and who runs the ALM chain.</p>'
      '<div class="kpis">' + "".join(f'<div class="kpi"><span>{esc(a)}</span><b>{esc(v)}</b><small>{esc(s)}</small></div>' for a, v, s in kpis) + "</div>"
      f'<p class="cap" style="font-size:12px;max-width:1080px">Canadian business only, net of reinsurance; General Account excl. par / seg fund (GenAcct); IFRS 17 periods only. '
      f'{FYE}. Public data only; every estimate is marked est. $MM and $BN are Canadian dollars. '
      f'<span class="chip">{MARK}RBC Life</span> is coloured, outlined and bold in every chart and table; peers are grey; a dashed line is the peer median. '
      'Prepared Nov 27, 2026; replaces the Oct 28, 2026 deck for the Canadian insurers.</p></div>',
      f"Source: the eight peer analyses rebuilt on the {SRC_ALM}. Short names follow the study: MFC (Manulife), SLF (Sun Life), CLF (Canada Life), BLU (Blumont Annuity).",
      cls="title")

# ================================================================= 2. Executive summary
cap_rank = int(st("licat_pct")["rank_from_low"])
liq = st("liquid_unenc")
ex = [
    ("Capital", pct1(rbc.licat_pct), f"LICAT total ratio, {ORD[cap_rank]} of 9 all-Canada filers",
     f"{rbc.pts_above_floor:.0f} points and {money(rbc.free125_mm)} above the study's 125% floor (peer median {st('licat_pct')['median']:.1f}%). "
     f"Buffer {rbc.buffer_pct:.1f}% of the General Account against {st('buffer_pct')['median']:.1f}%."),
    ("Liabilities and discount curve", pct2(dc_rbc.lp_30y), "30-year illiquidity premium (est), peer median " + pct2(dc_med.lp_30y),
     f"Individual insurance and group annuities are {rbc_p.long_liab_pct:.0f}% of non-par liabilities (median {A_oth.long_liab_pct.median():.0f}%). "
     f"The premium is {ref_lo:.2f}% on the least favourable reference curve; the ultimate rate is {ULT.loc['RBC', 'ultimate_rate']:.2f}% against 5.15% at most peers."),
    ("Asset mix", pct1(rbc_p.pct_private_fixed_income), f"private fixed income, % of General Account (median {A_oth.pct_private_fixed_income.median():.1f}%)",
     f"Government bonds are {l3g.loc['Government Bonds', 'RBC']:.0f}% (median {l3_med['Government Bonds']:.0f}%). Illiquid assets are {rbc_p.illiquid_pct:.0f}% "
     f"against {A.loc['MFC', 'illiquid_pct']:.0f}% to {A.loc['SLF', 'illiquid_pct']:.0f}% at the Big 3 (est). Since Oct 31, 2025 the mix has rotated from government bonds into credit."),
    ("Funding and liquidity", pct1(rbc.repos_ga), f"of the General Account funded by repos ({rbc.repos_ga_fy24:.1f}% a year earlier)",
     f"After repo collateral, liquid assets are {liq['rbc']:.0f}% of invested assets against a median of {liq['median']:.0f}%. "
     f"In fiscal 2025 repos (+{money(repo_chg)}) and group annuities (+{money(liab_chg['Group annuity'])}) funded the growth."),
    ("CSM and surplus portfolios", yrs(dur_rbc.csm_portfolio_duration), f"estimated duration of assets backing the CSM ({dur_rbc.csm_portfolio_duration_low:.1f} to {dur_rbc.csm_portfolio_duration_high:.1f})",
     f"Against a CSM run-off of {dur_rbc.csm_runoff_wal:.1f} years. Surplus portfolio {dur_rbc.surplus_portfolio_duration:.1f} years "
     f"({dur_rbc.surplus_portfolio_duration_low:.1f} to {dur_rbc.surplus_portfolio_duration_high:.1f}). {FVO.loc['RBC', 'fvoci_ac_pct_of_investments']:.0f}% of investments are at FVOCI or amortized cost; no peer publishes a numeric OCI limit."),
    ("Execution and people", f"${wal_rbc.cost_total_cad_mm:.1f}MM",
     f"estimated annual street wallet ({wal_rbc.cost_low_cad_mm:.1f} to {wal_rbc.cost_high_cad_mm:.1f}), {wal_rbc.cost_bps_of_canadian_general_account:.1f} bps",
     f"The 20 insurers on the list pay an estimated ${wal_tot:.0f}MM a year, {wal_bps_all:.1f} bps of Canadian invested assets. "
     f"RBC Life names {seats['RBC']} of six ALM-chain seats publicly; peers name a median of {seat_med:.0f}."),
]
slide("RBC Life runs a low-risk asset book on long liabilities, with a thinner capital cushion and more repo funding than any peer",
      '<div class="grid6">' + "".join(
          f'<div class="card"><h2>{esc(h)}</h2><div class="num">{esc(n)}</div><small>{esc(s)}</small><p>{esc(t)}</p></div>'
          for h, n, s, t in ex) + "</div>",
      f"Source: slides 5 to 25. {FYE}. Medians exclude RBC Life; each slide names its peer set. est = estimate.", fill=True)

# ================================================================= 3. What changed
old_new = [
    ("Scope", "Legal entity, whole general fund, incl. par, UL policyholder funds and foreign operations",
     "Canadian business, net of reinsurance; General Account excl. par / seg fund, with par, seg fund and UL policyholder funds as separate blocks"),
    ("Periods", "Year-end 2025 with history back to 2020 (IFRS 4 bridged to IFRS 17)",
     "IFRS 17 only, read by date: Dec 31, 2023 (RBC Life and BMO Life from fiscal 2024) to the latest filed quarter; anchor is the fiscal 2025 year-end"),
    ("Peer set", "20 insurers on the project list, one basis for all",
     "The study's 15 insurers (12 OSFI filers incl. BLU, plus iA, Beneva, Desjardins); the other names on the list stay on side tables or their own statements"),
    ("Liabilities", "Assets read on their own", "Assets read against liabilities by product line, CSM, Surplus, repo funding and LICAT"),
    ("Sensitivities", "Scaled to common shocks and added into one earnings-at-risk figure",
     "One risk at a time, each insurer's own shock, never combined or rescaled"),
    ("Internal figures", "An internal earnings limit shown beside peers", "None. RBC internal figures stay out of peer documents"),
    ("Modelling", "Stylised dollar effects (liability on each curve, market-drift split)",
     "Not shown. Anything that needs modelling is a next step with a directional read"),
]
moved = [
    ("LICAT peer median", "159% (17 insurers, mixed regimes)", f"{st('licat_pct')['median']:.1f}% (eight all-Canada filers)"),
    ("30-year premium", "1.72%, at the median", f"{dc_rbc.lp_30y:.2f}% (est) vs {dc_med.lp_30y:.2f}%"),
    ("Equity-type assets", "14.7% of portfolio (equity, real estate, private equity)", f"{rbc_p.non_fixed_income_pct:.1f}% of General Account (non-fixed-income)"),
    ("Repos", "14.1% of portfolio", f"{rbc.repos_ga:.1f}% of General Account"),
    ("Liquid assets", "77% (weighted)", f"{liq['rbc']:.1f}% after repo collateral"),
    ("Energy bonds", "37.6%, 3.5x the median", f"{rbc.energy_util:.1f}% with utilities vs {st('energy_util')['median']:.1f}%"),
    ("Street wallet", "$8.6MM, 5-year average", f"${wal_rbc.cost_total_cad_mm:.1f}MM, fiscal 2025 run rate"),
]
slide("Every section now reads the Canadian business on the ALM study's General Account, so most October figures have moved",
      card("What changed against the October 28 deck", table(["", "October 28 deck", "This deck (ALM framework)"], old_new, left=3, cls="wrap roomy"), style="flex:1.75")
      + card("RBC Life readings that moved", table(["Measure", "October", "Now"], moved, left=3, cls="wrap roomy"),
             f"The fall in equity-type assets is scope: public equity is {BASIS.loc['RBC', 'entity_public_equity_pct']:.1f}% of the entity pool and {BASIS.loc['RBC', 'genacct_public_equity_pct']:.1f}% of the General Account, because "
             + money(DDC["RBC"]["years"]["2025"]["ul"]) + " of common shares are held for universal life policyholders.", style="flex:1"),
      f"Source: READMEs of the eight rebuilt analyses; {SRC_ALM}. October figures from the Oct 28, 2026 summary deck and the Oct 29, 2026 street wallet estimate.")

# ================================================================= 4. Coverage
# From each analysis' README and coverage table: F = ALM study basis, P = partial, estimated or another stated basis, N = not covered
COLS = ["Discount curves", "Portfolio mix", "Reallocation", "Investment risk", "CSM and surplus durations", "Street wallet", "Deep dive", "Org chart"]
COV = {
    "RBC": "FFFFFFFF", "BMO": "FFFFFFFF", "MFC": "FFFFFFFF", "SLF": "FFFFFFFF", "CLF": "FFFFFFFF", "EMP": "FFFFFFFF",
    "IVA": "FFFFFFFF", "EQL": "FFFFFFFF", "COP": "FFFFFFFF", "IOF": "FFFFFFFF", "WAW": "FFFFFFFF",
    "BLU": "NFFFFPNN", "IAG": "PPPPPPPF", "BEN": "PPPPPPPF", "DFS": "PNNPPPPF",
    "CPL": "FPPPNPPF", "PRI": "FPPPNPPF", "ASL": "PPPPNPPF", "HUM": "NPPPNPPF", "UV": "NPPNNPPF", "CPP": "NNNNNNPF",
}
NOTE = {"RBC": "ALM study, OSFI", "BMO": "ALM study, OSFI", "MFC": "ALM study, OSFI; Canada follows the global mix (est)",
        "SLF": "ALM study, OSFI; Canada follows the global mix (est)", "CLF": "ALM study, OSFI; disclosed Canada column",
        "EMP": "ALM study, OSFI", "IVA": "ALM study, OSFI", "EQL": "ALM study, OSFI; par and UL split est",
        "COP": "ALM study, OSFI", "IOF": "ALM study, OSFI; includes Canada Protection Plan", "WAW": "ALM study, OSFI",
        "BLU": "ALM study, OSFI; not on the project's list of 20", "IAG": "ALM study, AMF filer: company filings, total CSM only",
        "BEN": "ALM study, AMF filer: company filings, total CSM only", "DFS": "ALM study, liabilities only: no public balance sheet",
        "CPL": "Outside the study: OSFI returns on its rules", "PRI": "Outside the study: OSFI returns on its rules",
        "ASL": "Outside the study: own annual report", "HUM": "Outside the study: summary statements",
        "UV": "Outside the study: summary statements", "CPP": "A Foresters Life brand, no separate filing"}
SYM = {"F": f'<span class="dotf"></span>', "P": '<span class="dotp"></span>', "N": '<span class="dotn">–</span>'}
order_cov = ["RBC", "BMO", "MFC", "SLF", "CLF", "EMP", "IVA", "EQL", "COP", "IOF", "WAW", "BLU", "IAG", "BEN", "DFS", "CPL", "PRI", "ASL", "HUM", "UV", "CPP"]
cov_rows = [[esc(label(NAME[k])), esc(NOTE[k])] + [SYM[c] for c in COV[k]] for k in order_cov]
n_full = [sum(1 for k in order_cov if COV[k][j] == "F") for j in range(len(COLS))]
cov_rows.append(["Insurers on the full method", ""] + [str(n) for n in n_full])
cov_html = table(["Insurer", "Basis"] + COLS, cov_rows, left=2, cls="cov", raw=True)
cov_html = cov_html.replace("<tr><td class=\"l\">Insurers on the full method", "<tr class=\"cnt\"><td class=\"l\">Insurers on the full method")
n_everywhere = sum(1 for k in order_cov if set(COV[k]) == {"F"})
assert n_everywhere == 11
slide("Coverage differs by section: eleven insurers carry the full method everywhere, iA and Beneva a partial one, and five smaller insurers sit outside the study",
      card("What each section covers, by insurer", cov_html,
           '<span class="dotf"></span> the section\'s full method on the ALM study basis &nbsp; <span class="dotp"></span> partial: estimated, group-level, liabilities only, or the earlier annual-report inputs '
           '&nbsp; <span class="dotn">–</span> not covered. Org charts use public sources and one layout for all 20 insurers on the list.', style="flex:1"),
      "Source: coverage tables and READMEs of the eight analyses. Adding a peer to the ALM study, or giving it a short name, is the study owner's decision; Canadian Premier and Primerica Life were built on its rules but not reviewed there.")

# ================================================================= 5. Peer set
size = {k: (PEERS.loc[k, "genacct_mm"] if k in PEERS.index and isnum(PEERS.loc[k, "genacct_mm"]) else None) for k in order_cov if k != "CPP"}
size_items = sorted([(NAME[k], v / 1000) for k, v in size.items() if v], key=lambda t: -t[1]) + [("Desjardins", None)]
size_rank = [n for n, _ in size_items].index(FOCUS) + 1
outside = {NAME[k] for k in ("CPL", "PRI", "ASL", "HUM", "UV", "IAG", "BEN")}
groups = [
    ("Bank-owned", "OSFI; Oct 31 year-end", f"{MARK}RBC Life, BMO Life", "Whole entity is Canadian business"),
    ("Big 3", "OSFI; Dec 31", "MFC, SLF, CLF", "OSFI In Canada schedule; LICAT covers the whole legal entity"),
    ("Non-Big 3, OSFI", "OSFI; Dec 31", "Empire Life, ivari, Equitable, Co-operators Life, Foresters Life (incl. Canada Protection Plan), Wawanesa Life, BLU", "Whole entity is Canadian business"),
    ("Non-Big 3, AMF", "AMF; Dec 31", "iA, Beneva, Desjardins", "Company filings (est); CARLI, not LICAT; Desjardins liabilities only"),
    ("Outside the study", "OSFI, AMF, FCNB", "Canadian Premier, Primerica Life, Assumption Life, Humania, UV Insurance", "Side tables: OSFI returns on the study's rules, or own statements"),
]
grp_html = table(["Group", "Regulator; year-end", "Insurers", "How the Canadian view is built"], groups, left=4, cls="wrap roomy")
grp_html = grp_html.replace("<tr><td class=\"l\">Bank-owned", "<tr class=\"rbc\"><td class=\"l\">Bank-owned")
slide(f"RBC Life is the {ORDH[size_rank].replace('highest', 'largest')} Canadian General Account at {money(rbc.genacct_bn * 1000)}, the largest outside the Big 3 and iA",
      card("General Account excl. par / seg fund, $BN",
           hbar(size_items, lambda v: f"${v:,.1f}BN" if v >= 1 else f"${v * 1000:,.0f}MM", W=520, rowh=23, label_w=128, right_w=70,
                tick_fmt=lambda v: f"{v:.0f}", faded=outside, notes={"Desjardins": "no public balance sheet"}),
           "Fiscal 2025 year-ends. Lighter bars are not ALM study views from OSFI returns: AMF filers from company filings (est), and insurers outside the study at their own reported scope.", style="flex:0 0 552px")
      + card("Peer set by group", grp_html,
             "The study's 15 insurers are the first four groups. Medians in this deck are of the other peers, RBC Life excluded; entity LICAT measures use the eight other all-Canada filers.", style="flex:1"),
      f"Source: {SRC_ALM}; portfolio composition analysis (peers.csv). UV Insurance, Assumption Life and Humania are invested assets as reported.")

# ================================================================= 6. RBC Life profile
strip_rows = []
for m, r in STATS[STATS.strip == 1].sort_values("order").iterrows():
    ids = ALLCAN9 if "all-Canada" in r.peer_set else OSFI12
    vals = [LS.loc[i, m] for i in ids if i != "RBC"]
    f = (lambda d, u: (lambda v: f"{v:.{d}f}{u}"))(int(r.decimals), "%")
    kind = "all-Canada filers" if "all-Canada" in r.peer_set else "OSFI peers"
    hint = f"{r.group}; the {WORD.get(len([v for v in vals if isnum(v)]), len(vals))} other {kind}" + (f"; {r.hint}" if isinstance(r.hint, str) else "")
    strip_rows.append(dict(metric=r.label.replace(", % of", ", % of"), hint=hint, values=vals, median=r["median"], focus=r.rbc, fmt=f))
prof_side = side([
    f"{b('Low on risk taken.')} Market and credit risk capital are both {ORD[int(st('market_cap_ga')['rank_from_low'])]} of nine all-Canada filers, and equity-type assets excluding UL pass-through are {rbc.eq_ex_ul:.1f}% of invested assets (median {st('eq_ex_ul')['median']:.1f}%).",
    f"{b('High on private credit, for a mid-size book.')} Private credit and mortgages are {rbc.private_credit:.1f}% of invested assets against {st('private_credit')['median']:.1f}%.",
    f"{b('An outlier on funding.')} Repos fund {rbc.repos_ga:.1f}% of the General Account; the median is nil. That pulls liquid assets after collateral to {liq['rbc']:.1f}%.",
    f"{b('Thin on cushion.')} LICAT {rbc.licat_pct:.1f}% and a {rbc.buffer_pct:.1f}% buffer are both below the peer medians.",
], w=300)
slide("RBC Life sits at the low end on market and credit risk, at the low end on capital, and alone at the top on repo funding",
      card("Where RBC Life sits on each measure",
           dotstrip(strip_rows, W=840, rowh=41, label_w=330),
           "Each row is one measure on its own scale, lowest to highest. Grey dots are the other peers, the tick is their median, the blue dot is RBC Life.", style="flex:1")
      + prof_side,
      f"Source: investment risk benchmark (peer_stats.csv, landscape.csv) on the {SRC_ALM}. {FYE}.")

# ================================================================= 7. Liabilities
LINES = ["Individual insurance", "Group annuity", "Individual annuity", "Group insurance"]
LCOL = [C1, C2, C3, C4]
lb = LIAB.copy()
lb["sid"] = lb.insurer.map(sid)
lpv = lb[lb.product_line.isin(LINES)].pivot_table(index="sid", columns="product_line", values="pct_of_nonpar", aggfunc="sum")
liab_rows = []
for k in A.sort_values("long_liab_pct", ascending=False).index:
    if k not in lpv.index:
        continue
    liab_rows.append(dict(name=NAME[k], vals=[lpv.loc[k, l] for l in LINES], sub=money(A.loc[k, "nonpar_icl_mm"]),
                          total_label=f"{A.loc[k, 'long_liab_pct']:.0f}%"))
isr_med = isr_peers.median()
liab_side = side([
    f"{b('Long liabilities.')} Individual insurance and group annuities (pension risk transfer) are {rbc_p.long_liab_pct:.0f}% of RBC Life's non-par liabilities, against a median of {A_oth.long_liab_pct.median():.0f}%. Group annuities alone are {rbc_p.liab_group_annuity_pct:.0f}% and grew {money(liab_chg['Group annuity'])} in fiscal 2025.",
    f"{b('A shrinking margin.')} ABL CSM fell {abs(csm_chg) / ctx_rbc.loc['2024-10-31', 'abl_csm_mm'] * 100:.0f}% in fiscal 2025 to {money(ctx_rbc.loc['2025-10-31', 'abl_csm_mm'])}; CSM is {rbc_p.csm_pct_genacct:.1f}% of the General Account (median {A_oth.csm_pct_genacct.median():.1f}%). The growth came in group annuities while the CSM fell.",
    f"{b('Earnings lean on spread.')} The insurance service result was {money(earn['isr'])} against a net investment result of {money(earn['nir'])}: {earn['isr_share']:.0f}% of the two, against a median of {isr_med:.0f}% for the {len(isr_peers)} peers with both lines.",
    "Long, illiquid liabilities can carry illiquid assets, so the liability side does not limit RBC Life's asset mix. Slide 12 sets the two against each other.",
], w=318)
slide(f"RBC Life's liabilities are long: individual insurance and group annuities are {rbc_p.long_liab_pct:.0f}% of the non-par book, against a {A_oth.long_liab_pct.median():.0f}% peer median",
      card("Non-par insurance liabilities by product line, % of total",
           legend(list(zip(["Individual insurance", "Group annuity (PRT)", "Individual annuity", "Group insurance"], LCOL)))
           + stacked(liab_rows, LCOL, W=826, rowh=34, label_w=206, right_w=52, sub_w=138, dark_text=(3,)),
           "Canada, net of reinsurance, excluding par and seg funds. Sorted by the long share (individual insurance plus group annuity), shown at right. Amount is the non-par total.", style="flex:1")
      + liab_side,
      f"Source: portfolio composition analysis (liabilities_by_line.csv: OSFI LF3 Canada column); deep dive data layer (earnings, CSM) on the {SRC_ALM}. {FYE}. iA, Beneva and Desjardins file no OSFI product lines.")

# ================================================================= 8. Discount curve premium
prem_items = sorted([(NAME[k], r.lp_30y) for k, r in DC.drop(index="MEDIAN").iterrows()], key=lambda t: -t[1])
est_prem = {NAME[k] for k in ("ASL", "BEN", "DFS", "IAG")}
REF_LAB = {"BMO Life (ALM repo basis)": "BMO Life (the study's basis)", "TD Life": "TD Life", "CIBC Life": "CIBC Life",
           "RBC Life seg fund curve, spot (est)": "RBC Life's own seg fund curve (est)"}
ref_rows = [[REF_LAB[k], pct2(ref25.loc[k, "risk_free"]), pct2(ref25.loc[k, "rbc_premium"])] for k in REF_LAB]
tr_rows = []
for p, lab in (("fy2024", "Fiscal 2024 year-ends"), ("fy2025", "Fiscal 2025 year-ends"), ("mid2026", "Jul 31 / Jun 30, 2026")):
    r = ctr30.loc[p]
    tr_rows.append([lab, pct2(r.rbc_premium), pct2(r.rbc_premium_vs_td), pct2(r.peer_median)])
max_peer = dc_peers.lp_30y.max()
slide(f"RBC Life's 30-year illiquidity premium is {dc_rbc.lp_30y:.2f}% (est) against a {dc_med.lp_30y:.2f}% peer median, and still {ref_lo:.2f}% on the least favourable reference curve",
      card("30-year illiquidity premium, non-par most illiquid curve",
           hbar(prem_items, pct2, W=560, rowh=24, label_w=132, right_w=82, vmin=0, vmax=2.5, tick_fmt=lambda v: f"{v:.1f}%", faded=est_prem,
                refs=[(dc_med.lp_30y, f"Peer median {dc_med.lp_30y:.2f}%", REF)], notes={FOCUS: "est", **{n: "est" for n in est_prem}}),
           "Premium over the insurer's own risk-free curve. RBC Life files no risk-free curve: its premium is measured over BMO Life's at the same Oct 31 date. Lighter bars: one all-products curve from the annual report, over the median OSFI risk-free curve.", style="flex:0 0 594px")
      + '<div style="flex:1;display:flex;flex-direction:column;gap:12px;min-width:0">'
      + card("The answer depends on the risk-free curve chosen", table(["Oct 31, 2025 reference", "30y risk-free", "RBC Life premium"], ref_rows, left=1, cls="roomy"),
             f"BMO Life's risk-free curve is the lowest of the three October filers, which widens RBC Life's measured premium by up to about {ref_hi - ref_lo:.1f} points. The highest peer premium is {max_peer:.2f}% (MFC).")
      + card("The lead over peers is recent", table(["", "RBC Life (est)", "vs TD Life", "Peer median"], tr_rows, left=1, cls="roomy"),
             "30-year premium. RBC Life adopted IFRS 17 on Nov 1, 2023, so its series starts at Oct 31, 2024.")
      + f'<p class="note">RBC Life files one-year forward rates; the study compounds them to spot (limitation L17), so the {dc_rbc.dr_30y:.2f}% spot rate and the premium are estimates. A higher discount curve means lower liabilities. What it is worth in dollars needs liability cash flows and is a next step.</p></div>',
      f"Source: discount curve analysis (headline_fy2025.csv, reference_curve_check.csv, trend.csv) on the {SRC_ALM}: OSFI LF2 curves; annual reports for iA, Desjardins, Beneva and Assumption Life. {len(dc_peers)} peers; Humania, UV Insurance and BLU are not in this section.")

# ================================================================= 9. Curve shape and par
xs = band25.tenor.tolist()
curve_svg = band_lines(xs, [("Peer median", band25.peer_median.tolist(), REF, 2), ("RBC Life (est)", band25.rbc_spot.tolist(), BLUE, 2.8)],
                       band=(band25.peer_min.tolist(), band25.peer_max.tolist(), "peer range"), W=640, H=312, xlab="Tenor (years)",
                       xticks=[1, 5, 10, 15, 20, 25, 30], step=0.5, right=118)
b30 = band25[band25.tenor == 30].iloc[0]
ult_ids = ("RBC", "MFC", "BMO", "SLF", "CLF")
ult_html = table([label(NAME[k]) for k in ult_ids] + ["Most other OSFI filers"],
                 [[pct2(ULT.loc[k, "ultimate_rate"]) for k in ult_ids] + ["5.15%"]], left=0, cls="ult", raw=True)
par = PARC[PARC.gap_bp_30y.notna()].sort_values("gap_bp_30y", ascending=False)
par_rows = [[label(NAME[k]), pct2(r.dividend_scale_rate), pct2(r.filed_30y), sgn(r.gap_bp_30y) + " bp",
             money(r.par_liabilities_bn * 1000) if isnum(r.par_liabilities_bn) else "n/d"] for k, r in par.iterrows()]
slide(f"RBC Life's curve runs above the whole peer range from year {first_above} to year 30, then falls to a {ULT.loc['RBC', 'ultimate_rate']:.2f}% ultimate rate against 5.15% at most peers",
      '<div style="flex:0 0 674px;display:flex;flex-direction:column;gap:12px;min-width:0">'
      + card(f"Individual insurance discount curve, spot rates at {dt('2025-10-31')}",
             curve_svg,
             f"Years 1 to 30. Peers at Dec 31, 2025 are restated to Oct 31: own premium plus BMO Life's Oct 31 risk-free curve (est). {int(b30.n_peers)} OSFI peers. At 30 years RBC Life is {b30.rbc_spot:.2f}% against a median of {b30.peer_median:.2f}%.")
      + card("Ultimate rate", ult_html,
             "RBC Life's is the filed ultimate forward rate. Its curve is high in the middle and low at the end.")
      + "</div>"
      + card("Par: dividend scale rate against the filed par curve at 30 years",
             table(["Insurer", "Dividend scale", "Filed 30y", "Gap", "Par liabilities"], par_rows, left=1, cls="roomy"),
             "The study is silent on par discounting; the dividend scale interest rate is kept as the par reference. RBC Life's par block is small. n/d = not disclosed.", style="flex:1"),
      f"Source: discount curve analysis (band.csv, ultimates_and_basis.csv, par_fy2025.csv) on the {SRC_ALM}. OSFI LF2 most illiquid curves; RBC Life spot from filed one-year forwards (est).")

# ================================================================= 10. Portfolio mix, Level 2
L2 = [("pct_public_fixed_income", "Public fixed income", C1), ("pct_private_fixed_income", "Private fixed income", C2),
      ("pct_public_equity", "Public equity", C3), ("pct_external_equity", "Real estate, private equity, infrastructure", C4),
      ("pct_external_debt", "External private debt", C5), ("pct_cash", "Cash and short term", C6),
      ("pct_other_unclassified", "Other invested (unclassified)", OTHER)]
TIER = {"A": "", "B": "AMF filings, est", "C": "outside the study", "D": "annual report"}
mix_rows = []
for k, r in PEERS[PEERS.tier != "E"].sort_values(["tier", "genacct_mm"], ascending=[True, False]).iterrows():
    mix_rows.append(dict(name=NAME[k], vals=[r[c] for c, _, _ in L2],
                         sub=money(r.genacct_mm) + ("  " + TIER[r.tier] if TIER[r.tier] else ("  est" if r.mix_est is True or str(r.mix_est) == "True" else ""))))
slide(f"RBC Life holds {rbc_p.pct_public_fixed_income:.0f}% public bonds and {rbc_p.pct_private_fixed_income:.0f}% private fixed income; the Big 3 hold {big3_priv.min():.0f}% to {big3_priv.max():.0f}% private (est)",
      card("General Account excl. par / seg fund by Level 2 asset class, % of total",
           legend([(t, c) for _, t, c in L2])
           + stacked(mix_rows, [c for _, _, c in L2], W=1160, rowh=22, label_w=300, right_w=4, sub_w=132, min_label_w=26, dark_text=(3, 4)),
           "The 12 OSFI peers on the ALM study view come first, largest General Account first; then AMF filers from company filings, OSFI filers outside the study, and three insurers on their annual reports (par and UL not separable). "
           "MFC and SLF Canada follow the global mix and CLF uses its disclosed Canada column (est). OSFI returns have no alternatives line, so alternatives sit in Other invested and common shares for OSFI filers. "
           "Desjardins publishes no asset mix (study limitation L42).", style="flex:1"),
      f"Source: portfolio composition analysis (peers.csv) on the {SRC_ALM}. {FYE}. UL policyholder funds, par and seg fund assets are outside these figures.")

# ================================================================= 11. Level 3 heat table
L3_ORDER = ["Government Bonds", "Corporate Bonds", "Illiquid Term Loan", "Commercial Mortgages", "Common Shares", "Preferred Shares",
            "Real Estate Equity", "Cash Equivalent", "Other invested (unclassified)"]
L3_LAB = {"Illiquid Term Loan": "Private placements (illiquid term loans)", "Cash Equivalent": "Cash and short term"}
heat_cols = ["RBC"] + [k for k in A.sort_values("genacct_mm", ascending=False).index if k != "RBC"]


def heat(v):
    i = 0 if v < 2 else 1 if v < 10 else 2 if v < 20 else 3 if v < 35 else 4
    return f'<td style="background:{SEQ[i]}">{v:.1f}</td>'


heat_rows = []
for l in L3_ORDER:
    cells = "".join(heat(l3g.loc[l, k]) for k in heat_cols)
    heat_rows.append(f'<tr><td class="l">{esc(L3_LAB.get(l, l))}</td>{cells}<td class="medc">{l3_med[l]:.1f}</td></tr>')
heat_html = ('<table class="heat"><thead><tr><th class="l">% of General Account</th>'
             + "".join(f'<th class="{"rbc" if k == "RBC" else ""}">{esc(label(NAME[k]))}</th>' for k in heat_cols)
             + '<th>Median of the other 11</th></tr></thead><tbody>' + "".join(heat_rows) + "</tbody></table>")
gov_rank = int((l3g.loc["Government Bonds"] > l3g.loc["Government Bonds", "RBC"]).sum() + 1)
slide(f"Government bonds are {l3g.loc['Government Bonds', 'RBC']:.0f}% of RBC Life's General Account against a {l3_med['Government Bonds']:.0f}% median; private placements and mortgages together are {rbc_p.pct_private_fixed_income:.0f}%",
      '<div style="flex:1;display:flex;flex-direction:column;gap:12px;min-width:0">'
      + card("General Account excl. par / seg fund by Level 3 class, the 12 OSFI peers on the ALM study view", heat_html,
             "Darker = larger share. Largest General Account first after RBC Life. MFC, SLF and CLF are estimates (global mix, or the disclosed Canada column); Equitable's par and UL split is an estimate.")
      + f'<p class="note">{b("Reading RBC Life.")} Its government bond share is the {ORDH[gov_rank]} of the 12, and repos fund {rbc.repos_ga:.1f}% of the General Account (slide 19). It reports no directly owned real estate and '
        f'{l3g.loc["Other invested (unclassified)", "RBC"]:.1f}% in other invested assets, where externally managed funds would sit (study limitation L21). Common shares are {l3g.loc["Common Shares", "RBC"]:.1f}% once '
        f'{money(DDC["RBC"]["years"]["2025"]["ul"])} of UL policyholder funds are removed.</p></div>',
      f"Source: portfolio composition analysis (block_mix_l3.csv) on the {SRC_ALM}. {FYE}. Asset taxonomy Level 3 as defined in the study; OSFI LF2 investment lines.")

# ================================================================= 12. Assets against liabilities
fit_pts = [(NAME[k], r.long_liab_pct, r.illiquid_pct) for k, r in A.iterrows()]
POS = {"RBC Life": "a", "ivari": "b", "Foresters Life": "l", "BLU": "r", "Empire Life": "b", "Equitable": "a", "BMO Life": "br",
       "MFC": "a", "SLF": "a", "CLF": "a", "Co-operators Life": "b", "Wawanesa Life": "a"}
fit_side = side([
    f"{b('RBC Life.')} {rbc_p.long_liab_pct:.0f}% long liabilities are backed with {rbc_p.illiquid_pct:.0f}% illiquid assets (private fixed income plus other invested assets). The medians are {A_oth.long_liab_pct.median():.0f}% and {A_oth.illiquid_pct.median():.0f}%.",
    f"{b('The Big 3')} hold {A.loc['MFC', 'illiquid_pct']:.0f}% (MFC), {A.loc['CLF', 'illiquid_pct']:.0f}% (CLF) and {A.loc['SLF', 'illiquid_pct']:.0f}% (SLF) illiquid on shorter liability books (est).",
    f"{b('Surplus.')} RBC Life's non-fixed-income assets are {rbc_p.non_fi_to_surplus_x:.1f}x its Surplus (median {A_oth.non_fi_to_surplus_x.median():.1f}x), so equity-type assets sit comfortably inside Surplus on the study's default waterfall.",
    "This is a directional read. How much more private credit the liabilities and the 125% LICAT floor allow is the study's modelling stage, not started.",
], w=330)
slide(f"RBC Life backs {rbc_p.long_liab_pct:.0f}% long liabilities with {rbc_p.illiquid_pct:.0f}% illiquid assets; SLF and CLF run {A.loc['CLF', 'illiquid_pct']:.0f}% to {A.loc['SLF', 'illiquid_pct']:.0f}% on shorter books (est)",
      card("Illiquid assets against long liabilities, the 12 OSFI peers",
           scatter(fit_pts, (50, 105), (0, 60), pct0, pct0, "Individual insurance plus group annuity, % of non-par liabilities",
                   "Illiquid assets, % of General Account", A_oth.long_liab_pct.median(), A_oth.illiquid_pct.median(), POS, W=820, H=462,
                   faded={"MFC", "SLF", "CLF"}),
           "Each dot is one insurer at its fiscal 2025 year-end. Dashed lines are the medians of the other eleven. Lighter dots are the Big 3, whose Canadian asset mix is an estimate.", style="flex:1")
      + fit_side,
      f"Source: portfolio composition analysis (peers.csv) on the {SRC_ALM}. Illiquid = private fixed income, external equity and debt, and other invested assets. Which assets back Surplus is the study's default waterfall, not a disclosure (L04).")

# ================================================================= 13. RBC Life reallocation
dates = rb_sh.index.tolist()
xi = list(range(len(dates)))
re_lines = [("Government bonds", rb_sh["Government Bonds"].tolist(), C1, 2.4), ("Corporate bonds", rb_sh["Corporate Bonds"].tolist(), C2, 2.4),
            ("Private placements", rb_sh["Illiquid Term Loan"].tolist(), C3, 2.4), ("Commercial mortgages", rb_sh["Commercial Mortgages"].tolist(), C4, 2.4)]
est_i = dates.index("2026-01-31")
re_svg = band_lines(xi, re_lines, W=640, H=392, yfmt=pct0, step=10, y0=0, y1=50, xticks=[i for i in xi if i % 2 == 0], right=176,
                    xtick_fmt=lambda i: f"{pd.Timestamp(dates[i]):%b %Y}", est_from=est_i - 0.5)
RL = [("Cash Equivalent", "Short-term investments"), ("Government Bonds", "Government bonds"), ("Corporate Bonds", "Corporate bonds"),
      ("Illiquid Term Loan", "Private placements"), ("Commercial Mortgages", "Commercial mortgages"), ("Common Shares", "Common shares"),
      ("Others", "Others (unclassified)")]
re_rows = [[lab, pct1(rb_sh.loc[d0, k]), pct1(rb_sh.loc[dfy, k]), pct1(rb_sh.loc[d1, k]), sgn(rb_sh.loc[d1, k] - rb_sh.loc[d0, k], "{:+.1f}"),
            sgn(rb_mm.loc[d1, k] - rb_mm.loc[d0, k])] for k, lab in RL]
re_rows.append(["Non-par General Account", money(rb_tot[d0]), money(rb_tot[dfy]), money(rb_tot[d1]), "", sgn(rb_tot[d1] - rb_tot[d0])])
gov_peak = rb_sh["Government Bonds"].max()
gov_back = gov_peak - rb_sh.loc[d1, "Government Bonds"]
slide(f"RBC Life built government bonds to {gov_peak:.0f}% through fiscal 2025, then rotated {gov_back:.0f} points back into corporates and private placements in fiscal 2026 (est)",
      card("RBC Life: the four largest classes, % of the non-par General Account", re_svg,
           f"Each filed date, {dt(d0)} to {dt(d1)}. Fiscal 2026 points use the Oct 31, 2025 block share of the invested pool (est).", style="flex:0 0 674px")
      + '<div style="flex:1;display:flex;flex-direction:column;gap:12px;min-width:0">'
      + card("Level 3: start, fiscal 2025 year-end and latest",
             table(["", dt(d0), dt(dfy), dt(d1) + " (est)", "Change, pts", "Change, $MM"], re_rows, left=1).replace("<tr><td class=\"l\">Non-par General Account", "<tr class=\"tot\"><td class=\"l\">Non-par General Account"))
      + f'<p class="note">Private placements rose from {pct1(rb_sh.loc[d0, "Illiquid Term Loan"])} to {pct1(rb_sh.loc[d1, "Illiquid Term Loan"])} ({money(rb_mm.loc[d0, "Illiquid Term Loan"])} to {money(rb_mm.loc[d1, "Illiquid Term Loan"])}) and short-term investments ran down to nil. '
        "Shares are at balance-sheet value and move with prices as well as trades; the split between the two needs modelling and is a next step.</p></div>",
      f"Source: portfolio reallocation analysis (mix_by_date.csv) on the {SRC_ALM}: OSFI LF1 / LF2 by filed date, the study's block allocation (BI-04) extended to every date. History starts with IFRS 17: RBC Life's first IFRS 17 return is Jan 31, 2024.")

# ================================================================= 14. Peer reallocation and funding
priv_items = [(NAME[k], r.chg) for k, r in priv.sort_values("chg", ascending=False).iterrows()]
priv_rank = [n for n, _ in priv_items].index(FOCUS) + 1
uses = [("Government bonds", asset_chg["Government Bonds"]), ("Private placements", asset_chg["Illiquid Term Loan"]),
        ("Corporate bonds", asset_chg["Corporate Bonds"]), ("Short-term investments", asset_chg["Cash Equivalent"])]
srcs = [("Repos", repo_chg), ("Group annuity (PRT)", liab_chg["Group annuity"]), ("Individual insurance", liab_chg["Individual insurance"]),
        ("Surplus", sur_chg), ("ABL CSM", csm_chg)]
fmm = lambda v: sgn(v) if v else "0"
ga_chg = ctx_rbc.loc["2025-10-31", "genacct_mm"] - ctx_rbc.loc["2024-10-31", "genacct_mm"]
slide(f"Private fixed income rose at {n_up} of 12 OSFI peers; RBC Life's {sgn(priv.loc['RBC', 'chg'], '{:+.1f}')} points is the {ORDH[priv_rank].replace('highest', 'largest')} move, and its fiscal 2025 growth was funded by repos and PRT",
      card("Change in private fixed income share of the non-par General Account, percentage points",
           hbar(priv_items, lambda v: sgn(v, "{:+.1f}"), W=520, rowh=30, label_w=132, right_w=110, vmin=-4, vmax=8, ntick=6, tick_fmt=lambda v: sgn(v),
                faded={"MFC", "SLF", "Equitable"}, notes={"Equitable": "low reliability", "MFC": "est", "SLF": "est", "CLF": "to Dec 2025"}),
           f"First IFRS 17 date (Dec 31, 2023; RBC Life Jan 31, 2024; BMO Life Apr 30, 2024) to the latest filed quarter (Jun 30 or Jul 31, 2026). "
           "Equitable's non-par mix is a residual after a par account that is 74% of its pool.", style="flex:0 0 552px")
      + '<div style="flex:1;display:flex;flex-direction:column;gap:12px;min-width:0">'
      + card(f"RBC Life, fiscal 2025: what grew, $MM",
             hbar(uses, fmm, W=560, rowh=25, label_w=170, right_w=70, vmin=-600, vmax=1800, tick_fmt=lambda v: f"{v:,.0f}".replace("-", "−")))
      + card("RBC Life, fiscal 2025: what funded it, $MM",
             hbar(srcs, fmm, W=560, rowh=25, label_w=170, right_w=70, vmin=-600, vmax=1800, tick_fmt=lambda v: f"{v:,.0f}".replace("-", "−")),
             f"Oct 31, 2024 to Oct 31, 2025. The General Account grew {money(ga_chg)}. Repos rose {money(repo_chg)} while government bonds rose {money(asset_chg['Government Bonds'])}: "
             f"the rise in repo funding equals about {repo_chg / asset_chg['Government Bonds'] * 100:.0f}% of the growth in government bonds. "
             f"LICAT stayed between {LTR.rbc.iloc[1:].min():.0f}% and {LTR.rbc.iloc[1:].max():.0f}% throughout.")
      + "</div>",
      f"Source: portfolio reallocation analysis (changes.csv, context.csv, mix_by_date.csv) and deep dive data layer (liabilities by line) on the {SRC_ALM}. Liabilities net of reinsurance, excl. par and seg funds.")

# ================================================================= 15. Capital
cap_items = sorted([(NAME[k], LS.loc[k, "capital_ratio_pct"]) for k in LS.index if isnum(LS.loc[k, "capital_ratio_pct"])], key=lambda t: -t[1])
cap_faded = {NAME[k] for k in BIG3 + ["IAG", "BEN"]}
buf_items = sorted([(NAME[k], LS.loc[k, "buffer_pct"]) for k in OSFI12], key=lambda t: -t[1])
lic_med, buf_med = st("licat_pct")["median"], st("buffer_pct")["median"]
slide(f"RBC Life's LICAT ratio of {rbc.licat_pct:.1f}% is {rbc.pts_above_floor:.0f} points above the study's 125% floor and {ORD[cap_rank]} of nine all-Canada filers; its buffer is {rbc.buffer_pct:.1f}% against {buf_med:.1f}%",
      card("Capital ratio, %",
           hbar(cap_items, pct1, W=560, rowh=27, label_w=132, right_w=84, vmin=0, vmax=220, tick_fmt=pct0, faded=cap_faded,
                refs=[(125, "125% floor", RISK), (lic_med, f"Median {lic_med:.1f}%", REF)], notes={"iA": "CARLI", "Beneva": "CARLI"}),
           "LICAT total ratio (OSFI). Lighter bars are left out of the median: MFC, SLF and CLF file for entities that include foreign business; iA and Beneva report the AMF's CARLI ratio. "
           "The 125% floor is the study's assumption, not a filed target.", style="flex:1")
      + card("Buffer, % of the General Account",
             hbar(buf_items, pct1, W=540, rowh=27, label_w=132, right_w=96, vmin=0, vmax=50, tick_fmt=pct0, faded={"MFC"},
                  refs=[(buf_med, f"Median {buf_med:.1f}%", REF)], notes={"MFC": "not reliable"}),
             "(Surplus + ABL CSM less net derivative liabilities) / (General Account less repos and derivative assets), Canada. The 12 OSFI peers; iA and Beneva report total CSM only, so no buffer. "
             "MFC's In Canada assets follow asset territory (L43).", style="flex:1"),
      f"Source: investment risk benchmark (landscape.csv, peer_stats.csv) on the {SRC_ALM}: OSFI LCQ and the study's peer summary. {FYE}.")

# ================================================================= 16. LICAT trend and capital path
tr = LTR[LTR["median"].notna()]
tx = list(range(len(LTR)))
lic_svg = band_lines(tx, [("Median of eight", LTR["median"].tolist(), REF, 2), ("RBC Life", LTR.rbc.tolist(), BLUE, 2.8)],
                     band=(LTR.low.tolist(), LTR.high.tolist(), "range of the eight other all-Canada filers"), W=700, H=392, yfmt=pct0, step=20, y0=100, y1=220,
                     xticks=[i for i in tx if i % 2 == 0], xtick_fmt=lambda i: LTR.rbc_date[i].replace(", 20", " '"), right=126,
                     refs=[(125, "125% floor", RISK)])
since = LTR.iloc[1:]
cp_rows = [[r.date.replace(" ", " "), pct1(r.licat_pct), money(r.required_capital_mm), money(r.free125_mm), money(r.parent_injection_mm) if r.parent_injection_mm else "nil",
            money(r.net_income_mm)] for r in CAPP.itertuples()]
assert CAPP.note.str.lower().tolist() == ["fiscal year", "fiscal year", "nine months"]
slide(f"The gap to peers is structural: RBC Life has held {since.rbc.min():.0f}% to {since.rbc.max():.0f}% since adopting IFRS 17 while the peer median stayed near {tr['median'].iloc[1:].median():.0f}%",
      card("LICAT total ratio by date, RBC Life against the eight other all-Canada filers", lic_svg,
           f"RBC Life's date is on the axis (fiscal quarter-ends); peers are at the following calendar quarter-end. {LTR.rbc_date.iloc[0]} is RBC Life's last IFRS 4 quarter. The peer median is not yet available for {LTR.rbc_date.iloc[-1]}.", style="flex:0 0 734px")
      + '<div style="flex:1;display:flex;flex-direction:column;gap:12px;min-width:0">'
      + card("RBC Life capital path", table(["", "LICAT", "Required capital", "Above 125%", "Parent capital", "Net income"], cp_rows, left=1, cls="wrap"),
             "Required capital is the base solvency buffer. Above 125% = capital resources less 125% of required capital. Net income is for the fiscal year, and for nine months at Jul 31, 2026.")
      + f'<p class="note">Required capital grew {money(CAPP.required_capital_mm.iloc[-1] - CAPP.required_capital_mm.iloc[0])} in under two years as the book grew. The ratio was held by parent capital ({money(CAPP.parent_injection_mm.sum())} over fiscal 2024 and 2025) and retained income; no dividends were paid. '
        f"BMO Life, the other bank-owned peer, is at {LS.loc['BMO', 'licat_pct']:.1f}%.</p></div>",
      f"Source: investment risk benchmark (licat_trend.csv, rbc_capital_path.csv) on the {SRC_ALM}: OSFI LCQ. One entity per insurer.")

# ================================================================= 17. Risk capital
rc_rows = [dict(name=NAME[k], market=LS.loc[k, "market_cap_ga"], credit=LS.loc[k, "credit_cap_ga"]) for k in
           sorted(ALLCAN9, key=lambda k: -LS.loc[k, "market_cap_ga"])]
COMP = ["Insurance", "Market", "Credit", "Segregated fund guarantees", "Operational", "Participating and other"]
CCOL = [C1, C2, C3, C4, C5, C6]
lm = LMIX.pivot_table(index="id", columns="component", values="share_pct", aggfunc="sum")
lm_rows = [dict(name=NAME[k], vals=[lm.loc[k, c] if c in lm.columns else 0 for c in COMP]) for k in ALLCAN9 + BIG3 if k in lm.index]
mk, cr = st("market_cap_ga"), st("credit_cap_ga")
slide(f"RBC Life carries the {ORD[int(mk['rank_from_low'])]} market and credit risk capital of nine all-Canada filers: {mk['rbc']:.2f}% and {cr['rbc']:.2f}% of its General Account (medians {mk['median']:.2f}% and {cr['median']:.2f}%)",
      card("Market and credit risk capital, % of own General Account",
           legend([("Market risk", C2), ("Credit risk", C3), ("Dashed lines: median of the eight others, in the same colour", "dash")])
           + dotpair(rc_rows, [("market", C2), ("credit", C3)], pct0, W=540, rowh=31, label_w=136, step=5,
                     medians=[(st("market_cap_ga")["median"], C2), (st("credit_cap_ga")["median"], C3)]),
           "LICAT required capital for non-par business, all-Canada filers only (entity = Canadian business). Equitable and Co-operators Life hold large par and UL books, so their non-par General Account is a small base. "
           f"Medians: market {mk['median']:.2f}%, credit {cr['median']:.2f}%. BMO Life's two values are close ({LS.loc['BMO', 'market_cap_ga']:.2f}% and {LS.loc['BMO', 'credit_cap_ga']:.2f}%) and overlap.", style="flex:0 0 574px")
      + card("LICAT required capital by risk, % of the total before diversification",
             legend(list(zip(COMP, CCOL)))
             + stacked(lm_rows, CCOL, W=570, rowh=28, label_w=132, min_label_w=24, dark_text=(3, 4)),
             f"Insurance risk is {LS.loc['RBC', 'ins_share']:.0f}% of RBC Life's credit, market and insurance capital (median {st('ins_share')['median']:.0f}%): asset risk is not what uses its capital. "
             f"Net investment result is {st('nir_cm')['rbc']:.0f}% of credit and market capital (median {st('nir_cm')['median']:.0f}%). MFC, SLF and CLF are whole legal entities.", style="flex:1"),
      f"Source: investment risk benchmark (landscape.csv, licat_mix.csv, peer_stats.csv) on the {SRC_ALM}: OSFI LCQ. {FYE}.")

# ================================================================= 18. Credit
en_rows = [dict(name=NAME[k], vals=[LS.loc[k, "energy"], LS.loc[k, "utilities"], 100 - LS.loc[k, "energy_util"]],
                total_label=f"{LS.loc[k, 'energy_util']:.1f}%") for k in sorted(OSFI12, key=lambda k: -LS.loc[k, "energy_util"])]
cm = lambda m, f: [st(m)["label"].split(",")[0], f(st(m)["rbc"]), f(st(m)["median"]), f"{int(st(m)['rank_from_low'])} of {int(st(m)['n'])} from the lowest"]
cred_rows = [
    ["Below investment grade, % of bonds", pct2(st("below_ig_bonds")["rbc"]), pct2(st("below_ig_bonds")["median"]), f"{int(st('below_ig_bonds')['rank_from_low'])} of {int(st('below_ig_bonds')['n'])} from the lowest"],
    ["Private credit and mortgages, % of invested", pct1(st("private_credit")["rbc"]), pct1(st("private_credit")["median"]), f"{int(st('private_credit')['rank_from_high'])} of {int(st('private_credit')['n'])} from the highest"],
    ["Credit risk capital, % of own General Account", pct2(cr["rbc"]), pct2(cr["median"]), f"{int(cr['rank_from_low'])} of {int(cr['n'])} from the lowest"],
    ["Expected credit loss allowance, bps of invested", f"{st('ecl_bps')['rbc']:.1f}", f"{st('ecl_bps')['median']:.1f}", f"{int(st('ecl_bps')['rank_from_low'])} of {int(st('ecl_bps')['n'])} from the lowest"],
    ["Energy, % of corporate bonds", pct1(st("energy")["rbc"]), pct1(st("energy")["median"]), "highest of 12"],
    ["Energy + utilities, % of corporate bonds", pct1(st("energy_util")["rbc"]), pct1(st("energy_util")["median"]), f"{int(st('energy_util')['rank_from_high'])} of {int(st('energy_util')['n'])} from the highest"],
    ["Reinsurance assets, % of General Account", pct1(st("reins_pct")["rbc"]), pct1(st("reins_pct")["median"]), f"{int(st('reins_pct')['rank_from_low'])} of {int(st('reins_pct')['n'])} from the lowest"],
]
slide(f"Credit quality is clean at {st('below_ig_bonds')['rbc']:.2f}% of bonds below investment grade; the {rbc.energy:.1f}% energy reading is a sector-coding question once utilities are added (median {st('energy_util')['median']:.1f}%)",
      card("Energy and utilities, % of corporate bonds",
           legend([("Energy", C1), ("Utilities", C2), ("All other sectors", FADED)])
           + stacked(en_rows, [C1, C2, FADED], W=560, rowh=28, label_w=132, right_w=56, min_label_w=26, dark_text=(2,),
                     seg_fmt=lambda v: f"{v:.0f}%"),
           f"The 12 OSFI peers, sorted by the two sectors together (shown at right). RBC Life files no Utilities line and puts {FACT['rbc_sector_other']:.0f}% in Other, so its utilities are coded elsewhere.", style="flex:0 0 594px")
      + '<div style="flex:1;display:flex;flex-direction:column;gap:12px;min-width:0">'
      + card("Credit measures, RBC Life against the other OSFI peers", table(["Measure", "RBC Life", "Median", "Rank"], cred_rows, left=1, cls="roomy"))
      + f'<p class="note">RBC Life takes its credit risk in private placements and mortgages, not in rating: private credit is high for a book of its size while below-investment-grade holdings are close to nil. '
        f'All of its reinsurance held is with an affiliate ({LS.loc["RBC", "reins_affil_pct"]:.0f}%), against {LS.loc["SLF", "reins_affil_pct"]:.0f}% at SLF and {LS.loc["CLF", "reins_affil_pct"]:.0f}% at CLF.</p></div>',
      f"Source: investment risk benchmark (landscape.csv, peer_stats.csv, facts.csv) on the {SRC_ALM}: OSFI LF3 bonds by issuer sector and rating. {FYE}.")

# ================================================================= 19. Funding and liquidity
repo_items = sorted([(NAME[k], LS.loc[k, "repos_ga"]) for k in LS.index if isnum(LS.loc[k, "repos_ga"])], key=lambda t: -t[1])
liq_items = sorted([(NAME[k], LS.loc[k, "liquid_unenc"]) for k in OSFI12 if isnum(LS.loc[k, "liquid_unenc"])], key=lambda t: -t[1])
slide(f"Repos fund {rbc.repos_ga:.1f}% of RBC Life's General Account, up from {rbc.repos_ga_fy24:.1f}%; after collateral, liquid assets are {liq['rbc']:.0f}% of invested assets against an {liq['median']:.0f}% median",
      card("Repos, % of the General Account",
           hbar(repo_items, pct1, W=540, rowh=26, label_w=132, right_w=70, vmin=0, vmax=20, tick_fmt=pct0, faded={"iA", "Beneva"}),
           f"Fiscal 2025 year-ends. RBC Life: {money(rbc.repos_mm)} at Oct 31, 2025, {money(FACT['rbc_repos_mm_fy24'])} a year earlier. Lighter bars are AMF filers on consolidated filings. "
           "OSFI filers report repos at fiscal year-ends only, so the 2026 balance is not yet visible.", style="flex:1")
      + card("Liquid assets after repo collateral, % of invested assets",
             hbar(liq_items, pct1, W=540, rowh=26, label_w=132, right_w=70, vmin=0, vmax=100, tick_fmt=pct0, faded={"MFC", "SLF", "CLF"},
                  refs=[(liq["median"], f"Median {liq['median']:.1f}%", REF)]),
             f"Cash, public bonds and listed shares outside UL policyholder funds, less bonds out as repo collateral. Before collateral RBC Life is at {rbc.liquid_ex_ul:.1f}%. "
             "BMO Life is not shown: the benchmark carries no value for it. MFC, SLF and CLF are whole legal entities.", style="flex:1"),
      f"Source: investment risk benchmark (landscape.csv, peer_stats.csv, facts.csv) on the {SRC_ALM}: OSFI LF3 (repos sit in other liabilities, limitation L29), LF2. An encumbrance and liquidity limit framework needs non-public data and is a next step.")

# ================================================================= 20. Sensitivities
sv = SENS.copy()
sv["sid"] = sv.id


def sens_cell(k, risk):
    r = sv[(sv.sid == k) & (sv.risk == risk)]
    if r.empty:
        return ["–", "–", "–", "–"]
    r = r.iloc[0]
    f = lambda v: "n/d" if not isnum(v) else "nil" if v == 0 else sgn(v, "{:+,.0f}") if abs(v) >= 10 or float(v).is_integer() else sgn(v, "{:+.1f}")
    return [r.shock, f(r.net_income_mm), f(r.csm_mm), f(r.ni_bps)]


SB = {"RBC": "RBC Insurance group, proxy (est)", "BMO": "Legal entity", "MFC": "Group", "SLF": "Group", "CLF": "Lifeco group",
      "EMP": "Legal entity", "IVA": "Legal entity", "EQL": "Legal entity", "IOF": "Legal entity", "WAW": "Legal entity",
      "IAG": "Group", "BEN": "Group, incl. P&C", "DFS": "Life and health segment"}
sens_rows = [[label(NAME[k]), SB[k]] + sens_cell(k, "Interest rates") + sens_cell(k, "Public equity") for k in SB]
sens_html = ('<table class="sens"><thead><tr><th class="l" rowspan="2">Insurer</th><th class="l" rowspan="2">Reporting basis</th>'
             '<th colspan="4" class="grp">Interest rates, parallel fall</th><th colspan="4" class="grp">Public equity, fall</th></tr>'
             '<tr><th>Shock</th><th>Net income, $MM</th><th>CSM, $MM</th><th>Net income, bps of invested</th>'
             '<th>Shock</th><th>Net income, $MM</th><th>CSM, $MM</th><th>Net income, bps of invested</th></tr></thead><tbody>'
             + "".join(f'<tr class="{"rbc" if r[0].endswith(FOCUS) else ""}">' + "".join(f'<td class="{"l" if i < 2 else ""}">{esc(str(v))}</td>' for i, v in enumerate(r)) + "</tr>" for r in sens_rows)
             + "</tbody></table>")
rs = sv[sv.sid == "RBC"].set_index("risk")
smm = lambda v: ("+" if v > 0 else "−") + f"${abs(v):.0f}MM"
slide(f"RBC Life publishes no sensitivities; the RBC Insurance group proxy shows {smm(rs.loc['Interest rates', 'net_income_mm'])} of net income for a 100 bps fall in rates and {smm(rs.loc['Public equity', 'net_income_mm'])} for a 10% equity fall (est)",
      card("Published sensitivities, one risk at a time, each insurer's own shock", sens_html,
           "As printed in each insurer's fiscal 2025 report. Shocks differ and are not rescaled; risks are never added together. Basis points divide by invested assets on the same reporting basis as the sensitivity. "
           "Group figures (MFC, SLF, CLF, iA) include business outside the Canadian entity. n/d = not published; Foresters Life publishes changes in assets and liabilities only. Co-operators Life and BLU publish none.", style="flex:1"),
      f"Source: investment risk benchmark (sensitivities.csv) on the {SRC_ALM} (deck2_sensitivities.csv); iA, Beneva and Desjardins as disclosed in their 2025 reports. RBC Life: RBC 2025 annual report, Note 15 (RBC Insurance group). Sensitivities on one shock set are a next step.")

# ================================================================= 21. CSM and surplus durations
dord = [k for k in OSFI12 + ["IAG", "BEN"] if k in DUR.index]
csm_rows = [dict(name=NAME[k], low=DUR.loc[k, "csm_portfolio_duration_low"], base=DUR.loc[k, "csm_portfolio_duration"],
                 high=DUR.loc[k, "csm_portfolio_duration_high"], tick=DUR.loc[k, "csm_runoff_wal"], faded=k in ("IAG", "BEN"),
                 note="memo" if k in ("IAG", "BEN") else "") for k in sorted(dord, key=lambda k: -DUR.loc[k, "csm_portfolio_duration"])]
sur_rows = [dict(name=NAME[k], low=DUR.loc[k, "surplus_portfolio_duration_low"], base=DUR.loc[k, "surplus_portfolio_duration"],
                 high=DUR.loc[k, "surplus_portfolio_duration_high"], faded=k in ("IAG", "BEN"),
                 note="memo" if k in ("IAG", "BEN") else "") for k in sorted(dord, key=lambda k: -DUR.loc[k, "surplus_portfolio_duration"])]
zero_sur = [NAME[k] for k in dord if DUR.loc[k, "surplus_portfolio_duration"] == 0]
slide(f"Assets backing RBC Life's CSM run about {dur_rbc.csm_portfolio_duration:.1f} years ({dur_rbc.csm_portfolio_duration_low:.1f} to {dur_rbc.csm_portfolio_duration_high:.1f}, est) against a {dur_rbc.csm_runoff_wal:.1f}-year CSM run-off; its surplus portfolio is {dur_rbc.surplus_portfolio_duration:.1f} years",
      card("CSM portfolio: estimated asset duration, years",
           legend([("Low to high case", MUTED), ("Base case", "#7c838e"), ("CSM run-off, weighted average years", "diamond")])
           + ranges(csm_rows, yrs, W=560, rowh=27, label_w=132, right_w=84, vmax=18),
           f"RBC Life's base case assigns its FVOCI and amortized cost book to CSM and Surplus (the study's designation test, {dur_rbc.designation_ratio:.2f}x). On the default waterfall its CSM assets would be {dur_rbc.csm_duration_waterfall_b:.1f} years. "
           "iA and Beneva are memo rows: total CSM and a pool that includes par.", style="flex:1")
      + card("Surplus portfolio: estimated asset duration, years",
             ranges(sur_rows, yrs, W=540, rowh=27, label_w=132, right_w=84, vmax=12),
             f"Equity, real estate and other assets carry zero rate duration. Where non-fixed-income assets exceed Surplus on the waterfall the surplus duration is nil: {', '.join(zero_sur)}. "
             "The choice of assignment rule moves the answer more than the gap between most peers; only Foresters Life publishes the assets supporting surplus.", style="flex:1"),
      f"Source: CSM and surplus duration analysis (results.csv, csm_runoff_summary.csv) on the {SRC_ALM}. Every duration is an estimate with a low and a high case; RBC Life's rests on eight observations of OCI on FVOCI bonds against the 5-year Canada yield. RBC Life's run-off is the RBC group schedule.")

# ================================================================= 22. FVOCI and OCI
fv_items = sorted([(NAME[k], FVO.loc[k, "fvoci_ac_pct_of_investments"]) for k in OSFI12 if k in FVO.index and isnum(FVO.loc[k, "fvoci_ac_pct_of_investments"])], key=lambda t: -t[1])
fv_allcan = sorted([FVO.loc[k, "fvoci_ac_pct_of_investments"] for k in ALLCAN9], reverse=True)
fv_rank = fv_allcan.index(FVO.loc["RBC", "fvoci_ac_pct_of_investments"]) + 1
oci_rows = []
for k in OSFI12:
    r = FVO.loc[k]
    if not isnum(r.worst_quarter_pct_of_equity):
        continue
    oci_rows.append([label(NAME[k]), money(r.fvoci_mm + r.amortized_cost_mm), f"{r.designation_ratio:.2f}x", f"{r.realised_duration:.1f}y" if isnum(r.realised_duration) else "n/d",
                     sgn(r.worst_quarter_pct_of_equity, "{:+.2f}") + "%"])
fr = FVO.loc["RBC"]
slide(f"RBC Life carries {fr.fvoci_ac_pct_of_investments:.0f}% of investments at FVOCI or amortized cost, the {ORDH[fv_rank]} of nine all-Canada filers; no peer publishes a numeric OCI limit",
      card("FVOCI and amortized cost assets, % of investments",
           hbar(fv_items, pct1, W=520, rowh=27, label_w=132, right_w=64, vmin=0, vmax=60, tick_fmt=pct0, faded={"MFC", "SLF", "CLF"}),
           "Legal entity, OSFI LF2, fiscal 2025 year-ends. Empire Life, ivari, Equitable, Foresters Life and Wawanesa Life carry everything at fair value through profit or loss. MFC, SLF and CLF are whole legal entities.", style="flex:0 0 552px")
      + '<div style="flex:1;display:flex;flex-direction:column;gap:12px;min-width:0">'
      + card("OCI exposure where a FVOCI book exists",
             table(["Insurer", "FVOCI + amortized cost", "vs equity + Tier 1 CSM", "Realised duration", "Worst quarter OCI, % of equity"], oci_rows, left=1, cls="roomy"),
             "Realised duration = sensitivity of OCI on FVOCI bonds to the 5-year Canada yield since IFRS 17 (est). Worst quarter is OCI on FVOCI bonds.")
      + f'<p class="note">{b("Limits.")} None of the 15 insurers publishes a numeric OCI or FVOCI limit. RBC states that market risk is managed through asset/liability management to stay within the Bank\'s risk appetite; BMO Life says its risk appetite is defined in quantitative terms without giving them; '
        f'Foresters Life publishes asset-class limits (common shares 10%, preferred shares 15% of invested assets). RBC Life\'s FVOCI and amortized cost book ({money(fr.fvoci_mm + fr.amortized_cost_mm)}) is {fr.designation_ratio:.2f}x its equity plus Tier 1 CSM, which is why the study reads it as the book backing CSM and Surplus.</p></div>',
      f"Source: CSM and surplus duration analysis (fvoci.csv) on the {SRC_ALM}: OSFI LF1 / LF2, Bank of Canada benchmark yields, limits statements from 2025 annual reports.")

# ================================================================= 23. Street wallet
wl = WAL.sort_values("cost_total_cad_mm", ascending=False)
WN = {k: NAME[k] for k in wl.index}
w_items = [(WN[k], r.cost_total_cad_mm) for k, r in wl.iterrows() if r.cost_total_cad_mm >= 1.5 and r.on_list_of_20 == 1]
w_whisk = {WN[k]: (r.cost_low_cad_mm, r.cost_high_cad_mm) for k, r in wl.iterrows()}
small = wl[(wl.cost_total_cad_mm < 1.5) & (wl.on_list_of_20 == 1)]
bps_items = sorted([(WN[k], r.cost_bps_of_canadian_general_account) for k, r in wl.iterrows() if r.on_list_of_20 == 1 and k != "DFS"], key=lambda t: -t[1])
drv = WDR[WDR.company_id == "rbc_life"].sort_values("cost_cad_mm", ascending=False)
drv_rows = [[r.driver, f"${r.cost_cad_mm:.1f}MM", f"{r.share_pct:.0f}%"] for r in drv.itertuples() if r.cost_cad_mm >= 0.1]
w_faded = {NAME[k] for k in ("IAG", "BEN", "DFS", "UV", "ASL", "HUM", "CPL", "PRI")}
slide(f"RBC Life pays the street an estimated ${wal_rbc.cost_total_cad_mm:.1f}MM a year ({wal_rbc.cost_low_cad_mm:.1f} to {wal_rbc.cost_high_cad_mm:.1f}), {wal_rbc.cost_bps_of_canadian_general_account:.1f} bps of its Canadian invested assets against {wal_bps_all:.1f} bps across the 20 insurers on the list",
      card("Estimated annual execution cost, $MM (est)",
           hbar(w_items, lambda v: f"${v:.1f}MM", W=420, rowh=27, label_w=128, right_w=72, vmin=0, vmax=90, tick_fmt=lambda v: f"{v:.0f}", whisk=w_whisk, faded=w_faded),
           f"Fiscal 2025 run rate with the low and high case as the line. {len(small)} insurers below $1.5MM are not drawn ({', '.join(WN[k] for k in small.index)}); together ${small.cost_total_cad_mm.sum():.1f}MM. "
           "Desjardins is priced at the peer median and is indicative only.", style="flex:0 0 450px")
      + card("Cost, bps of Canadian invested assets (est)",
             hbar(bps_items, lambda v: f"{v:.1f}", W=310, rowh=20.5, label_w=128, right_w=40, vmin=0, vmax=14, tick_fmt=lambda v: f"{v:.0f}", faded=w_faded,
                  refs=[(wal_bps_all, f"All 20: {wal_bps_all:.1f} bps", REF)]),
             "Asset base = non-par General Account, par block and UL policyholder funds. Canada Protection Plan is inside Foresters Life.", style="flex:0 0 340px")
      + '<div style="flex:1;display:flex;flex-direction:column;gap:12px;min-width:0">'
      + card("RBC Life by driver", table(["Driver", "Cost", "Share"], drv_rows, left=1, cls="wrap"))
      + f'<p class="note">The ALM study has no turnover or cost method; it supplies the scope and the balance sheets. RBC Life publishes no cash flow statement, so its active trading rate is a proxy built from its liability mix and the range is wide. '
        f'The October estimate was ${wal_rbc.october_cost_cad_mm:.1f}MM on the whole entity as a five-year average; most of the fall is scope.</p></div>',
      f"Source: street wallet analysis (wallet_by_insurer.csv, wallet_by_driver.csv) on the {SRC_ALM}. Canadian scope; seg fund assets excluded. Lighter bars: insurers outside OSFI data or the study, on earlier inputs. The Big 3 use group turnover ratios on Canadian assets.")

# ================================================================= 24. Who runs the ALM chain
seat_order = ["RBC", "BMO", "SLF", "MFC", "CLF", "IAG", "BEN", "DFS", "EMP", "IVA", "COP", "EQL", "IOF", "CPP", "WAW", "PRI", "CPL", "ASL", "HUM", "UV"]
seat_items = sorted([(NAME[k], seats[k]) for k in seat_order], key=lambda t: -t[1])
alm_named = [k for k, v in ORG.items() if any(s["fn"] == "ALM" and s["cert"] != "-" for s in v["seats"])]
alm_in_inv = [k for k in ("BMO", "MFC", "SLF", "IAG", "IVA") if k in alm_named]
assert set(alm_named) == set(alm_in_inv) | {"IOF", "CPP"}, alm_named
aa_named = [k for k, v in ORG.items() if any(s["fn"] == "Appointed Actuary" and s["cert"] != "-" for s in v["seats"])]
exec_inv = [NAME[k] for k in seat_order if ORG[k].get("inv_seat") == "Executive team"]
org_side = side([
    f"{b('RBC Life.')} Only the Chief Investment Officer is named on a public page. No public source names a Head of ALM, Chief Actuary, CFO or CRO for RBC Insurance, and RBC Life's own statements, which would carry the Appointed Actuary's opinion, are not public.",
    f"{b('ALM lead.')} Named at {len(alm_named)} of 20. Where the seat is visible it sits inside the investment organisation ({', '.join(NAME[k] for k in alm_in_inv)}); at Foresters Life, and so Canada Protection Plan, the Global CFO owns investments and ALM.",
    f"{b('Appointed Actuary.')} Named at {len(aa_named)} of 20, from the signed opinions in annual reports.",
    f"{b('Investment lead.')} On the top executive team at {len(exec_inv)} insurers: {', '.join(exec_inv)}.",
    f"{b('Deep dives.')} The companion deck gives each of the 20 insurers the same eight pages on the Canadian basis, including who manages the General Account, leadership tenure and pay, and partnerships.",
], w=420)
slide(f"RBC Life names {seats['RBC']} of six ALM-chain seats publicly; peers name a median of {seat_med:.0f}",
      card("Seats named publicly, of six",
           hbar(seat_items, lambda v: f"{v:.0f}", W=700, rowh=23, label_w=170, right_w=40, vmin=0, vmax=6, tick_fmt=lambda v: f"{v:.0f}", ntick=6,
                refs=[(seat_med, f"Median of the other 19: {seat_med:.0f}", REF)]),
           "The six seats: investments, ALM, Chief Actuary, Appointed Actuary, finance, risk. Canada Protection Plan shares Foresters Life's seats.", style="flex:1")
      + org_side,
      "Source: org chart deck (functions.json), public sources only: insurers' own pages, filings and circulars, LinkedIn (read Nov 6, 2026), trade press; leadership pages re-read Nov 27, 2026. Deep dive deck, 167 slides. RBC internal information is not used.")

# ================================================================= 25. Scorecard
SC = [("GenAcct, $BN", lambda k: LS.loc[k, "genacct_bn"], lambda v: f"{v:.1f}", True),
      ("Capital ratio", lambda k: LS.loc[k, "capital_ratio_pct"], pct0, True),
      ("Buffer", lambda k: LS.loc[k, "buffer_pct"], pct0, True),
      ("30y premium", lambda k: DC.loc[k, "lp_30y"] if k in DC.index else None, pct2, True),
      ("Illiquid assets", lambda k: PEERS.loc[k, "illiquid_pct"] if k in PEERS.index else None, pct0, True),
      ("Repos / GenAcct", lambda k: LS.loc[k, "repos_ga"], pct0, True),
      ("Liquid after collateral", lambda k: LS.loc[k, "liquid_unenc"], pct0, True),
      ("CSM asset duration", lambda k: DUR.loc[k, "csm_portfolio_duration"] if k in DUR.index else None, yrs, True),
      ("Wallet, bps", lambda k: WAL.loc[k, "cost_bps_of_canadian_general_account"] if k in WAL.index and k != "DFS" else None, lambda v: f"{v:.1f}", True),
      ("Seats named", lambda k: seats.get(k), lambda v: f"{v:.0f}", True)]
sc_ids = ["RBC", "BMO", "MFC", "SLF", "CLF", "IAG", "BEN", "DFS", "EMP", "IVA", "BLU", "COP", "EQL", "IOF", "WAW"]
sc_vals = {h: pd.Series({k: (f(k) if isnum(f(k)) else float("nan")) for k in sc_ids}, dtype=float) for h, f, _, _ in SC}


def third_of(v, s):
    """Third by rank: share of the other insurers with a strictly lower value (ties at the bottom stay at the bottom)."""
    s = s.dropna()
    share = (s < v).sum() / (len(s) - 1)
    return 3 if share >= 2 / 3 else 2 if share >= 1 / 3 else 1


def balls(v, s):
    if not isnum(v):
        return '<span class="na">–</span>'
    n = third_of(v, s)
    return '<span class="balls">' + "●" * n + '<span class="off">' + "●" * (3 - n) + "</span></span>"


sc_rows = []
for k in sc_ids:
    cells = [esc(label(NAME[k]))]
    for h, f, fm, _ in SC:
        v = sc_vals[h][k]
        cells.append(balls(v, sc_vals[h]) + (f" {esc(fm(v))}" if isnum(v) else ""))
    sc_rows.append(cells)
sc_html = table(["Insurer"] + [h for h, _, _, _ in SC], sc_rows, left=1, cls="score", raw=True)
third = lambda h: third_of(sc_vals[h]["RBC"], sc_vals[h])
assert third("Capital ratio") == 1 and third("Liquid after collateral") == 1 and third("30y premium") == 3 and third("Repos / GenAcct") == 3, "scorecard title no longer holds"
slide("Scorecard: among the study's 15 insurers RBC Life is in the bottom third on capital ratio and liquidity and the top third on illiquidity premium and repo funding",
      card("The study's 15 insurers, bank-owned and Big 3 first, then largest General Account first", sc_html,
           "●●● = top third of the insurers with the measure by rank, ● = bottom third; a position, not a judgement of good or bad. – = not public or not covered. MFC's buffer is not reliable (L43). "
           "iA and Beneva: CARLI ratio, premium and mix from company filings (est), CSM duration on total CSM (memo). MFC, SLF and CLF capital ratios are whole legal entities.", style="flex:1"),
      "Source: slides 5, 8, 12, 15, 19, 21, 23 and 24. Each measure keeps the basis and peer set of its own section; see the coverage table on slide 4.")

# ================================================================= 26. Synthesis
syn = [
    ("Where the position is sound", [
        f"Asset risk is low: market and credit capital are {ORD[int(mk['rank_from_low'])]} of nine all-Canada filers, and {st('below_ig_bonds')['rbc']:.2f}% of bonds are below investment grade",
        f"The liabilities are long and can carry illiquid assets: individual insurance and group annuities are {rbc_p.long_liab_pct:.0f}% of the non-par book",
        f"The book earns spread: a 30-year premium of {ref_lo:.2f}% to {ref_hi:.2f}% (est) against a {dc_med.lp_30y:.2f}% median, with {l3g.loc['Government Bonds', 'RBC']:.0f}% in government bonds",
        f"Execution is cheap: an estimated {wal_rbc.cost_bps_of_canadian_general_account:.1f} bps a year against {wal_bps_all:.1f} bps across the list",
    ], ""),
    ("Where it is exposed", [
        f"The cushion is thin: LICAT {rbc.licat_pct:.1f}% leaves {money(rbc.free125_mm)} above 125%, and the buffer is {rbc.buffer_pct:.1f}% against {buf_med:.1f}%",
        f"Repos fund {rbc.repos_ga:.1f}% of the General Account; no other OSFI peer is above {LS.loc['SLF', 'repos_ga']:.1f}%, and liquid assets after collateral are {liq['rbc']:.0f}%",
        f"ABL CSM fell {abs(csm_chg) / ctx_rbc.loc['2024-10-31', 'abl_csm_mm'] * 100:.0f}% in fiscal 2025 while the growth came in group annuities",
        f"The curve depends on a reference choice, and CSM assets look short ({dur_rbc.csm_portfolio_duration:.1f} years against a {dur_rbc.csm_runoff_wal:.1f}-year run-off, est)",
        "Outsiders cannot see entity-level sensitivities, duration or five of six ALM seats",
    ], "warn"),
    ("What could be done", [
        "Test how much private credit fits inside the capital above 125% LICAT: the study's modelling stage, not started",
        "Set an encumbrance and liquidity limit framework for repos, derivatives and collateral",
        "Continue the fiscal 2026 rotation from government bonds into corporate bonds and private placements within those limits",
        "Prepare entity-level sensitivities on one shock set, and asset and liability key-rate durations, so the comparison can be closed",
        "Confirm the risk-free curve behind the illiquidity premium before relying on its size",
    ], ""),
]
slide("For RBC Life: long liabilities and low asset-risk capital point to room for more private credit; the open questions are funding, liquidity and a thin cushion",
      '<div style="display:flex;gap:16px;width:100%;height:100%">' + "".join(
          f'<div class="card syn {c}" style="flex:1"><h2>{esc(h)}</h2><ul>' + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul></div>" for h, items, c in syn)
      + "</div>",
      "Source: slides 5 to 25 and the ALM study's findings BI-01 to BI-05 and next steps. The options are drawn from public data; they are not recommendations on internal limits, which are outside it.", fill=True)

# ================================================================= 27. Method
dd_med = DD["peer_median"]
AN = {"discount_curves": "discount curves", "portfolio_composition": "portfolio composition", "investment_risk": "investment risk",
      "portfolio_reallocation": "reallocations", "street_wallet": "street wallet", "csm_surplus_duration": "CSM and surplus durations",
      "insurer_deep_dive": "deep dives", "org_charts": "org charts"}
meth_l = [
    ("Basis", "Canadian business, net of reinsurance; General Account excl. par / seg fund, with par, seg fund and UL policyholder funds separate. MFC and SLF Canada follow the global asset mix and CLF uses its disclosed Canada column. Public data only; no RBC internal figures."),
    ("Dates", "Fiscal 2025 year-ends: Oct 31, 2025 for RBC Life and BMO Life, Dec 31, 2025 for the others. History is IFRS 17 only, so it starts Dec 31, 2023 (Jan 31, 2024 for RBC Life, Apr 30, 2024 for BMO Life). The street wallet is a fiscal 2025 run rate, not a multi-year average."),
    ("Medians differ by section", f"Medians exclude RBC Life. LICAT measures use the eight other all-Canada filers ({lic_med:.1f}%); balance-sheet measures the eleven other OSFI peers (buffer {buf_med:.1f}%); curve premiums 16 peers. "
                                  f"The deep dive deck shows {dd_med['cap_ratio']:.1f}% and {dd_med['buffer']:.1f}% because its medians also take the Big 3 entities, Canadian Premier and Primerica Life."),
    ("Small differences between sections", f"RBC Life's General Account is {money(rbc.genacct_bn * 1000)} in the study's peer summary and {money(rb_tot[dfy])} as the invested pool in the block allocation. "
                                           f"Private fixed income is {rbc_p.pct_private_fixed_income:.1f}% of the General Account and {rbc.private_credit:.1f}% of invested assets."),
]
meth_r = [
    ("Estimates", f"RBC Life's spot curve and premium (forwards compounded to spot; premium over BMO Life's risk-free curve, {ref_lo:.2f}% to {ref_hi:.2f}% by reference). Seg fund and par CSM splits. Every duration. Every street wallet figure. "
                  "Big 3 Canadian asset mixes. RBC Life's sensitivities are the RBC Insurance group's."),
    ("Not covered", "Desjardins publishes no stand-alone balance sheet or asset mix. Humania and UV Insurance publish no curve. Canada Protection Plan sits inside Foresters Life. BLU is in the study but not on the project's list of 20 and has no deep dive or org chart. "
                    "Assumption Life, Canadian Premier, Primerica Life, Humania and UV Insurance have no CSM or surplus duration."),
    ("Left to next steps", "Dollar effect of the discount curve, the market-drift split of reallocations, private credit capacity within LICAT 125%, common-shock sensitivities, key-rate durations and the assets backing Surplus all need non-public data or modelling."),
    ("Reproducibility", "This deck recomputes nothing but medians, ranks and differences. It reads the result tables of the eight analyses, each an open pull request on abiddobani/InsuranceCompanies ("
                        + ", ".join(f"{AN[k]} #{v['pull_request']}" for k, v in sorted(MAN.items(), key=lambda t: t[1]["pull_request"])) + ")."),
]
mkh = lambda items: "".join(f"<h3>{esc(h)}</h3><p>{esc(t)}</p>" for h, t in items)
slide("Method, coverage and caveats",
      f'<div class="card meth" style="flex:1">{mkh(meth_l)}</div><div class="card meth" style="flex:1">{mkh(meth_r)}</div>',
      f"Framework: MooseDragon/cdn-life-insurer-alm (commit {ALM_COMMIT}), README standing rules, docs/METHODOLOGY.md and LIMITATIONS.md. Code: abiddobani/InsuranceCompanies, analysis/summary_deck_alm.", fill=True)

# ---------------------------------------------------------------- HTML document
CSS = f"""
@page {{ size: 1280px 720px; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #fff; }}
body {{ font-family: Inter, "Helvetica Neue", Arial, "Liberation Sans", sans-serif; color: {INK}; font-size: 12.5px; line-height: 1.4; }}
.slide {{ position: relative; width: 1280px; height: 720px; padding: 28px 44px 0; overflow: hidden; break-after: page; }}
.slide:last-child {{ break-after: auto; }}
h1 {{ font-family: Georgia, "Liberation Serif", "DejaVu Serif", serif; font-weight: 400; font-size: 23.5px; line-height: 1.22; margin: 0; max-width: 1180px; letter-spacing: -0.005em; }}
.slide.title h1 {{ font-size: 40px; max-width: 1000px; margin-top: 96px; }}
.body {{ position: absolute; top: 104px; left: 44px; width: 1192px; height: 556px; display: flex; gap: 16px; align-items: flex-start; }}
.body.fill {{ align-items: stretch; }}
.slide.title .body {{ top: 250px; height: 410px; }}
.foot {{ position: absolute; left: 44px; right: 44px; bottom: 14px; display: flex; justify-content: space-between; gap: 30px; font-size: 10px; color: {SUB}; line-height: 1.35; }}
.foot .pg {{ flex: 0 0 auto; }}
.card {{ background: #fff; border: 1px solid #e1e4e8; border-radius: 6px; padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; min-width: 0; }}
.card.warn {{ background: #fff8ee; border-color: #f0d9b5; }}
.card h2 {{ font-size: 14px; font-weight: 600; margin: 0; }}
.card h3 {{ font-size: 13px; font-weight: 600; margin: 6px 0 0; }}
.card.meth p {{ margin: 3px 0 10px; font-size: 13.5px; line-height: 1.5; }}
.card.meth h3 {{ font-size: 14.5px; }}
.cap {{ font-size: 11px; color: {SUB}; line-height: 1.4; margin: 0; }}
.note {{ font-size: 12.5px; line-height: 1.45; margin: 0; }}
.lead {{ font-size: 18px; line-height: 1.4; margin: 0; max-width: 1040px; color: {INK}; }}
.side {{ display: flex; flex-direction: column; gap: 11px; font-size: 13px; line-height: 1.45; min-width: 0; }}
.side p {{ margin: 0; }}
ul {{ margin: 4px 0 0; padding-left: 18px; }}
li {{ margin: 0 0 7px; }}
.grid6 {{ display: grid; grid-template-columns: repeat(3, 1fr); grid-auto-rows: 1fr; gap: 14px; width: 100%; height: 100%; }}
.grid6 .card {{ gap: 3px; padding: 16px 18px; }}
.grid6 .card h2 {{ font-size: 16px; }}
.grid6 .num {{ font-size: 44px; font-weight: 600; color: {INK}; letter-spacing: -0.01em; line-height: 1.15; margin-top: 4px; }}
.grid6 small {{ font-size: 12.5px; color: {SUB}; margin-bottom: 10px; }}
.grid6 p {{ margin: 0; font-size: 15px; line-height: 1.5; }}
.card.syn {{ padding: 18px 20px; }}
.card.syn ul {{ padding-left: 20px; margin-top: 12px; }}
.card.syn ul li {{ font-size: 16px; line-height: 1.45; margin-bottom: 20px; }}
.card.syn h2 {{ font-size: 18px; }}
.lg {{ display: flex; flex-wrap: wrap; gap: 3px 14px; font-size: 11px; color: {INK}; margin: 0; }}
.lg i {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px; vertical-align: -1px; margin-right: 5px; }}
.lg i.dash {{ width: 18px; height: 0; border-radius: 0; vertical-align: 3px; border-top: 2px dashed {REF}; }}
.lg i.diamond {{ transform: rotate(45deg) scale(0.8); border-radius: 1px; }}
.chip {{ display: inline-block; border: 1.5px solid {INK}; border-radius: 4px; padding: 0 5px; font-weight: 700; color: {INK}; background: {FOCUS_BG}; }}
.kpis {{ display: flex; gap: 12px; }}
.kpi {{ flex: 1; border: 1px solid #e1e4e8; border-radius: 6px; padding: 12px 14px; }}
.kpi span {{ font-size: 12px; color: {SUB}; display: block; min-height: 34px; }}
.kpi b {{ display: block; font-size: 30px; font-weight: 600; margin: 4px 0 4px; letter-spacing: -0.01em; }}
.kpi small {{ font-size: 11.5px; color: {SUB}; display: block; line-height: 1.35; }}
table {{ border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; font-size: 12px; }}
th {{ font-weight: 600; color: {SUB}; text-align: right; border-bottom: 1px solid #9aa0a8; padding: 5px 7px; font-size: 11px; vertical-align: bottom; }}
td {{ text-align: right; padding: 5px 7px; border-bottom: 1px solid {GRID}; white-space: nowrap; vertical-align: middle; }}
th.l, td.l {{ text-align: left; }}
table.wrap td {{ white-space: normal; vertical-align: top; }}
table.roomy td {{ padding: 7px 8px; }}
table.roomy.wrap td {{ padding: 8px 9px; line-height: 1.38; }}
tr.rbc td {{ background: {FOCUS_BG}; font-weight: 700; }}
tr.med td, tr.tot td {{ font-weight: 700; border-top: 1px solid #9aa0a8; }}
table.cov td, table.cov th {{ padding: 1.6px 6px; text-align: center; font-size: 11px; line-height: 1.3; }}
table.cov td.l, table.cov th.l {{ text-align: left; }}
table.cov td:nth-child(2) {{ color: {SUB}; font-weight: 400; font-size: 10.5px; }}
table.cov tr.cnt td {{ font-weight: 700; border-top: 1px solid #9aa0a8; border-bottom: 0; }}
.dotf, .dotp {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; vertical-align: -1px; }}
.dotf {{ background: {BLUE}; }}
.dotp {{ background: #fff; border: 2.5px solid #7fa8d6; }}
.dotn {{ color: {SUB}; }}
table.score td {{ padding: 5.6px 7px; font-size: 12px; text-align: left; }}
table.score th {{ text-align: left; }}
.balls {{ color: {REF}; letter-spacing: 1px; font-size: 10px; margin-right: 3px; }}
tr.rbc .balls {{ color: {BLUE}; }}
.balls .off {{ color: #d5d9df; }}
.na {{ color: {SUB}; }}
table.heat td {{ text-align: center; padding: 10px 5px; border-bottom: 2px solid #fff; border-right: 2px solid #fff; font-size: 12.5px; }}
table.heat th {{ text-align: center; font-size: 10.5px; padding: 5px 3px; }}
table.heat th.rbc {{ color: {INK}; font-weight: 700; }}
table.heat td.l {{ text-align: left; background: #fff; }}
table.heat td.medc {{ font-weight: 700; background: #fff; }}
table.heat td:nth-child(2) {{ font-weight: 700; outline: 1.6px solid {INK}; outline-offset: -2px; }}
table.sens td {{ padding: 6.2px 8px; font-size: 12.5px; }}
table.sens th.grp {{ text-align: center; color: {INK}; border-bottom: 1px solid {GRID}; }}
table.sens td:nth-child(3), table.sens td:nth-child(7) {{ border-left: 1px solid #c9ccd2; }}
svg text {{ font-family: Inter, "Helvetica Neue", Arial, sans-serif; fill: {INK}; }}
svg text.tk {{ font-size: 10.5px; fill: {SUB}; }}
svg text.lb {{ font-size: 12px; }}
svg text.sl {{ font-size: 11px; fill: {INK}; }}
svg text.vl {{ font-size: 11.5px; }}
svg text.sg {{ font-size: 10.5px; fill: #fff; font-weight: 600; }}
svg text.sgd {{ font-size: 10.5px; fill: {INK}; font-weight: 600; }}
svg text.halo {{ paint-order: stroke; stroke: #fff; stroke-width: 3.5px; stroke-linejoin: round; }}
table.ult th, table.ult td {{ text-align: center; }}
table.ult th:first-child {{ color: {INK}; font-weight: 700; }}
table.ult td:first-child {{ background: {FOCUS_BG}; font-weight: 700; }}
"""

pages = []
for i, s in enumerate(SLIDES, start=1):
    pages.append(f'<section class="slide {s["cls"]}"><h1>{esc(s["title"])}</h1><div class="body {"fill" if s["fill"] else ""}" data-shot="{i:02d}">{s["body"]}</div>'
                 f'<div class="foot"><span>{esc(s["source"])}</span><span class="pg">{i} / {len(SLIDES)}</span></div></section>')
DOC = f'<!doctype html><html><head><meta charset="utf-8"><title>Peer landscape on the ALM framework</title><style>{CSS}</style></head><body>{"".join(pages)}</body></html>'

NODE = """
const { chromium } = require('playwright');
(async () => {
  const [html, pdf, shots] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2 });
  await p.goto('file://' + html);
  await p.evaluate(() => document.fonts.ready);
  const over = await p.evaluate(() => [...document.querySelectorAll('.slide')].map((s, i) => {
    const body = s.querySelector('.body'), foot = s.querySelector('.foot'), h1 = s.querySelector('h1');
    const bb = body.getBoundingClientRect(), fb = foot.getBoundingClientRect(), hb = h1.getBoundingClientRect();
    let bottom = 0, right = 0;
    body.querySelectorAll('*').forEach(e => { const r = e.getBoundingClientRect(); if (r.width && r.height) { bottom = Math.max(bottom, r.bottom); right = Math.max(right, r.right); } });
    const issues = [];
    if (bottom > fb.top - 4) issues.push('body runs into the footer by ' + Math.round(bottom - fb.top + 4) + 'px');
    if (right > bb.right + 1) issues.push('body is ' + Math.round(right - bb.right) + 'px too wide');
    if (hb.bottom > bb.top - 2) issues.push('title runs into the body by ' + Math.round(hb.bottom - bb.top + 2) + 'px');
    if (fb.height > 30) issues.push('footer too tall');
    return issues.length ? (i + 1) + ': ' + issues.join('; ') : null;
  }).filter(Boolean));
  console.log('OVERFLOW ' + JSON.stringify(over));
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
    Path(html_path).write_text(DOC, encoding="utf-8")
    Path(js_path).write_text(NODE)
    env = dict(os.environ)
    env.setdefault("NODE_PATH", "/opt/node-tools/node_modules")
    subprocess.run(["node", js_path, html_path, str(PDF_OUT), shots], check=True, env=env)
    if os.environ.get("KEEP_HTML"):
        shutil.copy(html_path, os.environ["KEEP_HTML"])

    # ------------------------------------------------------------ pptx: native title and source, body as image
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    PX = 1 / 96
    for i, s in enumerate(SLIDES, start=1):
        sl = prs.slides.add_slide(prs.slide_layouts[6])
        is_title = s["cls"] == "title"
        tb = sl.shapes.add_textbox(Inches(44 * PX), Inches((124 if is_title else 28) * PX), Inches(1180 * PX), Inches((110 if is_title else 70) * PX))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = MSO_ANCHOR.TOP
        r = tf.paragraphs[0].add_run()
        r.text = s["title"]
        r.font.name, r.font.size, r.font.bold = "Georgia", Pt(30 if is_title else 17), False
        r.font.color.rgb = RGBColor(0x1F, 0x23, 0x29)
        top = 250 if is_title else 104
        sl.shapes.add_picture(os.path.join(shots, f"{i:02d}.png"), Inches(44 * PX), Inches(top * PX), width=Inches(1192 * PX))
        ft = sl.shapes.add_textbox(Inches(44 * PX), Inches(672 * PX), Inches(1120 * PX), Inches(36 * PX))
        ft.text_frame.word_wrap = True
        ft.text_frame.margin_left = ft.text_frame.margin_right = ft.text_frame.margin_top = 0
        r = ft.text_frame.paragraphs[0].add_run()
        r.text = s["source"]
        r.font.name, r.font.size = "Arial", Pt(7.5)
        r.font.color.rgb = RGBColor(0x5D, 0x64, 0x70)
        pg = sl.shapes.add_textbox(Inches(1180 * PX), Inches(672 * PX), Inches(56 * PX), Inches(30 * PX))
        pg.text_frame.paragraphs[0].alignment = PP_ALIGN.RIGHT
        r = pg.text_frame.paragraphs[0].add_run()
        r.text = f"{i} / {len(SLIDES)}"
        r.font.name, r.font.size = "Arial", Pt(7.5)
        r.font.color.rgb = RGBColor(0x5D, 0x64, 0x70)
    prs.save(PPTX_OUT)
assert max(len(s["title"]) for s in SLIDES) <= 165, "a title is too long for two lines in the pptx"
print("wrote", PDF_OUT.name, "and", PPTX_OUT.name, "slides:", len(SLIDES))
