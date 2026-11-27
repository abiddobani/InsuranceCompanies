"""Peer portfolio composition on the ALM framework (fiscal 2025 year-ends).

Rebuilds the peer general-account composition on the methods, definitions and data of
MooseDragon/cdn-life-insurer-alm (the project's primary framework from 2026-11-27):
  * Canadian business only; General Account excl. par / seg fund / UL policyholder funds ("GenAcct");
  * each asset block shown against the liabilities it backs (product lines net of reinsurance, ABL CSM,
    Surplus, financing);
  * level 1 and 2 for the overview, level 3 for findings; estimates tagged.

Inputs (read only): a checkout of the ALM repo (--alm, default ../cdn-life-insurer-alm relative to this
repo) and inputs/annual_report_fallback.csv (three insurers the ALM repo does not cover).
Outputs: out/*.csv and out/data.json (feeds the dashboard and the PDF).

Run with the ALM repo's environment:
    uv run --project ../cdn-life-insurer-alm python analysis/portfolio_composition_alm/build.py
Units: C$ millions unless a column says otherwise.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--alm", default=str(HERE.parents[2] / "cdn-life-insurer-alm"))
ARGS = ap.parse_args()
ALM = Path(ARGS.alm)
P = ALM / "data" / "processed"
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

# --------------------------------------------------------------------------------------------------
# Universe. Short IDs are the ALM repo's fixed IDs; insurers outside the repo keep a slug (no new IDs).
# tier: A = ALM study view (OSFI filer, full block view)   B = ALM study view (AMF filer, filings)
#       C = ALM method applied to OSFI returns (outside the study's peer set)
#       D = annual-report figures on the earlier method (ALM repo silent)   E = no public asset mix
# --------------------------------------------------------------------------------------------------
PEERS = [
    # key, display name, tier, group, period end, on Abid's canonical list
    ("RBC", "RBC Life", "A", "Bank-owned", "2025-10-31", True),
    ("BMO", "BMO Life", "A", "Bank-owned", "2025-10-31", True),
    ("MFC", "Manulife", "A", "Big 3", "2025-12-31", True),
    ("SLF", "Sun Life", "A", "Big 3", "2025-12-31", True),
    ("CLF", "Canada Life", "A", "Big 3", "2025-12-31", True),
    ("IAG", "iA Financial Group", "B", "Quebec (AMF)", "2025-12-31", True),
    ("BEN", "Beneva", "B", "Quebec (AMF)", "2025-12-31", True),
    ("DFS", "Desjardins Insurance", "E", "Quebec (AMF)", "2025-12-31", True),
    ("EMP", "Empire Life", "A", "Mid-size", "2025-12-31", True),
    ("IVA", "ivari", "A", "Mid-size", "2025-12-31", True),
    ("EQL", "Equitable Life", "A", "Mid-size", "2025-12-31", True),
    ("COP", "Co-operators Life", "A", "Mid-size", "2025-12-31", True),
    ("IOF", "Foresters Life (incl. Canada Protection Plan)", "A", "Mid-size", "2025-12-31", True),
    ("WAW", "Wawanesa Life", "A", "Mid-size", "2025-12-31", True),
    ("BLU", "Blumont Annuity", "A", "Mid-size", "2025-12-31", False),
    ("canadian_premier", "Canadian Premier Life", "C", "Small", "2025-12-31", True),
    ("primerica_life", "Primerica Life", "C", "Small", "2025-12-31", True),
    ("uv_insurance", "UV Insurance", "D", "Small", "2025-12-31", True),
    ("assumption_life", "Assumption Life", "D", "Small", "2025-12-31", True),
    ("humania", "Humania", "D", "Small", "2025-12-31", True),
]
NAME = {k: n for k, n, *_ in PEERS}
TIER = {k: t for k, _, t, *_ in PEERS}
TIER_LABEL = {
    "A": "ALM study view (OSFI returns)",
    "B": "ALM study view (AMF filer, company filings)",
    "C": "ALM method on OSFI returns (outside the study's peer set)",
    "D": "Annual report, earlier method (ALM repo silent)",
    "E": "No public asset mix (liabilities only)",
}
OSFI_ID = {"canadian_premier": 28358, "primerica_life": 28419}

# Taxonomy (ALM repo docs/METHODOLOGY.md, Asset taxonomy). l2_chart = the seven overview classes.
TAX = [
    # l3 key, L1, L2, overview class
    ("Government Bonds", "Internally Managed", "Public Fixed Income", "Public fixed income"),
    ("Corporate Bonds", "Internally Managed", "Public Fixed Income", "Public fixed income"),
    ("Asset Backed Securities", "Internally Managed", "Public Fixed Income", "Public fixed income"),
    ("Bonds (issuer not disclosed)", "Internally Managed", "Public Fixed Income", "Public fixed income"),
    ("Commercial Mortgages", "Internally Managed", "Private Fixed Income", "Private fixed income"),
    ("Illiquid Term Loan", "Internally Managed", "Private Fixed Income", "Private fixed income"),
    ("Private Liquid Loans", "Internally Managed", "Private Fixed Income", "Private fixed income"),
    ("Consumer Loans", "Internally Managed", "Private Fixed Income", "Private fixed income"),
    ("Reverse Mortgages", "Internally Managed", "Private Fixed Income", "Private fixed income"),
    ("Loans (type not disclosed)", "Internally Managed", "Private Fixed Income", "Private fixed income"),
    ("Common Shares", "Internally Managed", "Public Equity", "Public equity"),
    ("Preferred Shares", "Internally Managed", "Public Equity", "Public equity"),
    ("Pooled Fund Units", "Internally Managed", "Equity", "Public equity"),
    ("Cash Equivalent", "Internally Managed", "Cash & Cash Equivalent", "Cash"),
    ("Real Estate Equity", "Externally Managed", "Equity", "External equity"),
    ("Infrastructure Equity", "Externally Managed", "Equity", "External equity"),
    ("Other Private Equity", "Externally Managed", "Equity", "External equity"),
    ("Infrastructure Debt", "Externally Managed", "Debt", "External debt"),
    ("Structured Products", "Externally Managed", "Debt", "External debt"),
    ("Other Private Debt", "Externally Managed", "Debt", "External debt"),
    ("Other invested (unclassified)", "Unclassified", "Other / unclassified", "Other / unclassified"),
]
L3S = [t[0] for t in TAX]
L1_OF = {t[0]: t[1] for t in TAX}
L2_OF = {t[0]: t[2] for t in TAX}
CLS_OF = {t[0]: t[3] for t in TAX}
CLASSES = ["Public fixed income", "Private fixed income", "Public equity", "Cash", "External equity",
           "External debt", "Other / unclassified"]
ILLIQUID = ["Commercial Mortgages", "Illiquid Term Loan", "Private Liquid Loans", "Consumer Loans", "Reverse Mortgages",
            "Loans (type not disclosed)", "Real Estate Equity", "Infrastructure Equity", "Other Private Equity",
            "Infrastructure Debt", "Structured Products", "Other Private Debt", "Other invested (unclassified)"]
NON_FI = ["Common Shares", "Preferred Shares", "Pooled Fund Units", "Real Estate Equity", "Infrastructure Equity",
          "Other Private Equity", "Other invested (unclassified)"]
LINES = ["Individual insurance", "Individual annuity", "Group insurance", "Group annuity"]


def mm(k):
    return None if k is None or (isinstance(k, float) and np.isnan(k)) else float(k) / 1e3


def clean(x):
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else round(float(x), 4)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


# --------------------------------------------------------------------------------------------------
# ALM repo inputs
# --------------------------------------------------------------------------------------------------
summ = pd.read_csv(P / "peer_summary_2025q4.csv").set_index("short_id")
alloc = pd.read_csv(P / "deck2_block_allocation_2025fye.csv")
icl = pd.read_csv(P / "icl_by_line_2025q4.csv")
pool = pd.read_csv(P / "bs_pool_l3_2025q4.csv")
assets = pd.read_csv(P / "osfi_assets_long.csv", low_memory=False)
filings = pd.read_csv(P / "filings_all_long.csv", low_memory=False)
deck = json.loads((ALM / "deck" / "alm_peer_deck_v2.json").read_text())
osfi = pd.read_parquet(P / "osfi_long.parquet", columns=["id", "dpa", "per", "label", "value_num"])
alm_commit = subprocess.run(["git", "-C", str(ALM), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()

POOL_ID = {28395: "RBC", 28397: "MFC", 28429: "SLF", 28386: "CLF", 28344: "BMO", 28414: "IVA", 28377: "EQL",
           28368: "COP", 28432: "IOF", 28434: "WAW", 143611: "BLU", 28375: "EMP"}
STUDY_A = [k for k, _, t, *_ in PEERS if t == "A"]

mix_rows = []      # insurer, block, l3, amount_mm, basis
peer_rows = {}     # insurer -> dict
notes = {}         # insurer -> list of basis notes


def add_mix(key, block, series, basis):
    for l3, v in series.items():
        if v and abs(v) > 1e-9:
            assert l3 in L1_OF, l3
            mix_rows.append(dict(insurer=key, block=block, l3=l3, amount_mm=float(v), basis=basis))


# ---------- Tier A: the study's block allocation (scripts/deck2/block_allocation.py) ----------
BASIS_A = {"MFC": "est: Canada assumed to follow the entity (global) mix (ALM study rule)",
           "SLF": "est: Canada assumed to follow the entity (global) mix (ALM study rule)",
           "CLF": "disclosed Canada non-par mix (Canada Life Q4 2025 MD&A); bond split gov / corp / private at the entity ratio (est)",
           "EQL": "OSFI pool less par (fact sheet) and Participating UL linked accounts (est)"}
for s in STUDY_A:
    a = alloc[alloc.peer == s].set_index("l3")
    r = summ.loc[s]
    g = lambda c: mm(r[c]) if c in r and not pd.isna(r[c]) else None
    ga_basis = BASIS_A.get(s, "OSFI LF2 pool less UL index-linked lines and par; entity = Canada")
    add_mix(s, "GenAcct", a.nonpar_seg_ga_k / 1e3, ga_basis)
    if a.par_k.sum() > 0:
        add_mix(s, "Par", a.par_k / 1e3, a.par_basis.iloc[0] + ": " + a.par_source.iloc[0])
    if a.ul_ph_fund_k.sum() > 0:
        add_mix(s, "UL policyholder funds", a.ul_ph_fund_k / 1e3,
                "OSFI LF2 index-linked lines" if s != "EQL" else "est: Participating UL linked accounts split out of the par block")
    par_mm, ul_mm = a.par_k.sum() / 1e3, a.ul_ph_fund_k.sum() / 1e3
    peer_rows[s] = dict(
        genacct_mm=g("genacct_k"), par_mm=par_mm, ul_mm=ul_mm, seg_backing_mm=max(g("seg_backing_assets_k") or 0, 0),
        seg_fund_value_mm=g("seg_fund_value_k"), reinsurance_assets_mm=g("reinsurance_assets_k"),
        fcf_mm=g("fcf_k"), csm_abl_mm=g("csm_abl_k"), csm_total_mm=g("csm_total_k"), csm_split="split",
        surplus_mm=g("surplus_k"), repos_mm=g("repos_k"), financing_other_mm=g("financing_other_k"),
        derivative_liab_mm=g("derivative_liab_k"), derivative_assets_mm=g("derivative_assets_k"),
        buffer_pct=g("buffer_pct") * 1e3 if g("buffer_pct") is not None else None,
        capital_ratio_pct=float(r.capital_ratio_pct), capital_ratio_basis=r.capital_ratio_basis,
        mix_basis=ga_basis, mix_est=s in ("MFC", "SLF", "CLF", "EQL"),
        clipped_mm=float(a.residual_negative_clipped_k.iloc[0]) / 1e3,
    )

# ---------- Tier B: AMF filers from the study's harmonised filings (consolidated pool, est) ----------
def frow(company, startswith, period="FY2025", scope=None, exact=False):
    """One figure from the ALM repo's harmonised filings. Public sources only: rows the repo tags as
    user-provided (RBC Life internal figures, 'private repo only') are refused, per the repo's standing rule
    that RBC internal figures stay out of peer documents."""
    x = filings[(filings.company == company) & (filings.period == period) & filings.source_item.astype(str).str.startswith(startswith)]
    if scope:
        x = x[x.scope == scope]
    if exact:
        x = x[x.source_item == startswith]
    assert len(x) >= 1 and x.amount.nunique() == 1, (company, startswith, len(x))
    assert not (x.basis.astype(str).str.contains("user_provided") | x.source_doc.astype(str).str.startswith("user,")).any(), \
        ("user-provided figure refused", company, startswith)
    return float(x.amount.iloc[0])


IAG = "iA Financial Group"
ia = pd.Series({
    "Government Bonds": frow(IAG, "Governments (bonds)") + frow(IAG, "Municipalities (bonds)"),
    "Corporate Bonds": frow(IAG, "Corporates - Public issues"),
    "Illiquid Term Loan": frow(IAG, "Corporates - Private issues"),
    "Asset Backed Securities": frow(IAG, "Mortgages - Securitized and insured") + frow(IAG, "Mortgages - Insured"),
    "Commercial Mortgages": frow(IAG, "Mortgages - Uninsured"),
    "Private Liquid Loans": frow(IAG, "Book value of corporate loans"),
    "Consumer Loans": frow(IAG, "Book value of car loans"),
    "Common Shares": frow(IAG, "Stocks by category - Common") + frow(IAG, "Stocks by category - Market indices"),
    "Preferred Shares": frow(IAG, "Stocks by category - Preferred"),
    "Pooled Fund Units": frow(IAG, "Stocks by category - Investment fund units"),
    "Cash Equivalent": frow(IAG, "Cash and short-term investments"),
})
iag_view = pd.read_csv(P / "iag_genacct_bs_2025q4.csv")
ben_view = pd.read_csv(P / "ben_genacct_bs_2025q4.csv")
ia["Real Estate Equity"] = float(iag_view[iag_view.item.str.contains("of which: investment properties")].amount_k.iloc[0]) / 1e3
BEN = "Beneva"
ben = pd.Series({
    "Cash Equivalent": frow(BEN, "Note 5 - Cash and cash equivalents"),
    "Government Bonds": frow(BEN, "Note 5 - Bonds - Canada, Quebec") + frow(BEN, "Note 5 - Bonds - Municipalities"),
    "Corporate Bonds": frow(BEN, "Note 5 - Bonds - Corporate"),
    "Infrastructure Debt": frow(BEN, "Note 5 - Debt securities - Private debt") + frow(BEN, "Look-through - Investments in private companies - Private debt"),
    "Common Shares": frow(BEN, "Note 5 - Equity securities - Common shares"),
    "Preferred Shares": frow(BEN, "Note 5 - Equity securities - Preferred shares"),
    "Infrastructure Equity": frow(BEN, "Look-through - Investments in private companies - Infrastructure"),
    "Real Estate Equity": frow(BEN, "Look-through - Investments in private companies - Real estate") + frow(BEN, "Note 5 - Investment properties"),
    "Other Private Equity": frow(BEN, "Look-through - Investments in private companies - Other") + frow(BEN, "Note 5 - Investments in a joint venture"),
    "Pooled Fund Units": frow(BEN, "Block - Mutual funds not identified as policyholder-linked"),
    "Asset Backed Securities": frow(BEN, "Note 5 - Loans - Residential mortgages"),
    "Commercial Mortgages": frow(BEN, "Note 5 - Loans - Non-residential mortgages"),
    "Illiquid Term Loan": frow(BEN, "Note 5 - Loans - Other"),
})
ben_linked = frow(BEN, "Block - Mutual funds held for policyholder-linked")
ben_total_inv = frow(BEN, "Balance sheet - Total investments")
ben_deriv = frow(BEN, "Balance sheet - Derivative financial instruments (asset)")
assert abs(ben.sum() + ben_linked + ben_deriv - ben_total_inv) < 1.0, (ben.sum(), ben_linked, ben_deriv, ben_total_inv)


def view_amt(view, pattern, side=None):
    x = view[view.item.str.contains(pattern, regex=False)]
    if side:
        x = x[x.side == side]
    assert len(x) == 1, (pattern, len(x))
    return float(x.amount_k.iloc[0]) / 1e3


for s, pool_mix, view, basis in (
    ("IAG", ia, iag_view, "est: consolidated invested assets by class (iA 2025 annual report), assumed to hold for the Canadian "
                           "General Account; par and UL backing not separable; US Operations and investment-contract backing carved out by amount"),
    ("BEN", ben, ben_view, "est: Beneva Group consolidated note 5 less policyholder-linked mutual funds, assumed to hold after the P&C "
                           "carve-out; par and UL not separable beyond the linked funds"),
):
    r = summ.loc[s]
    ga = mm(r.genacct_k)
    add_mix(s, "GenAcct", pool_mix / pool_mix.sum() * ga, basis)
    peer_rows[s] = dict(
        genacct_mm=ga, par_mm=None, ul_mm=(ben_linked if s == "BEN" else None), seg_backing_mm=0.0,
        seg_fund_value_mm=mm(r.seg_fund_value_k), reinsurance_assets_mm=mm(r.reinsurance_assets_k), fcf_mm=mm(r.fcf_k),
        csm_abl_mm=None, csm_total_mm=mm(r.csm_total_k), csm_split="total only (AMF filer)", surplus_mm=mm(r.surplus_k),
        repos_mm=mm(r.repos_k), financing_other_mm=mm(r.financing_other_k), derivative_liab_mm=mm(r.derivative_liab_k),
        derivative_assets_mm=mm(r.derivative_assets_k), buffer_pct=None, capital_ratio_pct=float(r.capital_ratio_pct),
        capital_ratio_basis=r.capital_ratio_basis, mix_basis=basis, mix_est=True, clipped_mm=0.0,
        pool_reported_mm=float(pool_mix.sum()),
    )
r = summ.loc["DFS"]
peer_rows["DFS"] = dict(genacct_mm=None, fcf_mm=mm(r.fcf_k), csm_total_mm=mm(r.csm_total_k), csm_split="total only (AMF filer)",
                        mix_basis="No stand-alone balance sheet or invested-asset mix is public for Desjardins Financial Security (ALM limitation L42)",
                        capital_ratio_basis=r.capital_ratio_basis)

# ---------- Tier C: ALM method applied to two more OSFI filers ----------
O25 = osfi[(osfi.per == "2025Q4") & ~osfi.label.str.contains("prior", case=False, na=False)].drop_duplicates(["id", "dpa"])


def oval(i, code):
    x = O25[(O25.id.astype(str) == str(i)) & (O25.dpa == code)].value_num
    return float(x.iloc[0]) if len(x) and pd.notna(x.iloc[0]) else 0.0


def norm_l3(l3):
    if not isinstance(l3, str) or l3.startswith("(no L3"):
        return "Other invested (unclassified)"
    if l3.startswith("Real Estate"):
        return "Real Estate Equity"
    return l3


for s, i in OSFI_ID.items():
    x = assets[(assets.id == i) & (assets.period == "2025Q4") & (assets.line_kind == "invested_asset")]
    m = x.assign(l3n=x.l3.map(norm_l3)).groupby("l3n").amount.sum() / 1e3
    assert abs(m.sum() - oval(i, "P2000207001") / 1e3) < 0.5, (s, m.sum())
    ul = oval(i, "P2101288970") / 1e3
    par_icl = oval(i, "P2201051001") / 1e3
    assert ul == 0 and abs(par_icl) < 1, (s, ul, par_icl)   # neither files UL index-linked or par lines
    ga = (oval(i, "P2000207001") + oval(i, "P2000201001") + oval(i, "P2000202001") + oval(i, "P2000210001")) / 1e3
    basis = "OSFI LF2 investments by class (no UL or par lines filed); entity = Canada; not a signed-off study view"
    add_mix(s, "GenAcct", m / m.sum() * ga, basis)
    lic = oval(i, "D1010010020")
    peer_rows[s] = dict(genacct_mm=ga, par_mm=0.0, ul_mm=0.0, seg_backing_mm=0.0, seg_fund_value_mm=oval(i, "P2000216001") / 1e3,
                        reinsurance_assets_mm=oval(i, "P2000218001") / 1e3, csm_split="not built", mix_basis=basis, mix_est=True,
                        capital_ratio_pct=lic or None, capital_ratio_basis="LICAT total", clipped_mm=0.0,
                        genacct_note="investments + cash + accrued income + derivative assets (LF1); liabilities view not built")

# ---------- Tier D: annual-report figures carried from the earlier method ----------
fb = pd.read_csv(HERE / "inputs" / "annual_report_fallback.csv")
FB_MAP = {"Cash": "Cash Equivalent", "Bonds (issuer n/d)": "Bonds (issuer not disclosed)", "Policy & Other Loans": "Loans (type not disclosed)"}
for s in ("uv_insurance", "assumption_life", "humania"):
    x = fb[(fb.company_id == s) & ~fb.level3.str.startswith("EXCLUDED")]
    m = x.assign(l3=x.level3.replace(FB_MAP)).groupby("l3").amount_cad_mm.sum()
    src = x.source.iloc[0]
    excl = fb[(fb.company_id == s) & fb.level3.str.startswith("EXCLUDED")]
    basis = f"{src}; consolidated general fund" + ("; par and pass-through fund units excluded (note 4)" if s == "assumption_life"
                                                    else "; par and UL backing not separable (summary statements)")
    add_mix(s, "GenAcct", m, basis)
    peer_rows[s] = dict(genacct_mm=float(m.sum()), mix_basis=basis, mix_est=s != "assumption_life", csm_split="not built", clipped_mm=0.0,
                        par_mm=float(excl[excl.level3.str.contains("Participating")].amount_cad_mm.sum()) or None,
                        ul_mm=float(excl[excl.level3.str.contains("Pass-through")].amount_cad_mm.sum()) or None,
                        genacct_note="invested assets as reported; liabilities view not built (not in the ALM repo)")

# --------------------------------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------------------------------
mix = pd.DataFrame(mix_rows)
mix["l1"] = mix.l3.map(L1_OF)
mix["l2"] = mix.l3.map(L2_OF)
mix["asset_class"] = mix.l3.map(CLS_OF)
mix["pct_of_block"] = 100 * mix.amount_mm / mix.groupby(["insurer", "block"]).amount_mm.transform("sum")
mix["insurer_name"] = mix.insurer.map(NAME)
mix["l3_order"] = mix.l3.map({k: i for i, k in enumerate(L3S)})
mix = mix.sort_values(["insurer", "block", "l3_order"])
chk = mix.groupby(["insurer", "block"]).pct_of_block.sum()
assert ((chk - 100).abs() < 1e-6).all()

ga = mix[mix.block == "GenAcct"]
ga_l3 = ga.pivot_table(index="insurer", columns="l3", values="pct_of_block", aggfunc="sum").reindex(columns=L3S).fillna(0.0)
ga_cls = ga.pivot_table(index="insurer", columns="asset_class", values="pct_of_block", aggfunc="sum").reindex(columns=CLASSES).fillna(0.0)
ga_l1 = ga.pivot_table(index="insurer", columns="l1", values="pct_of_block", aggfunc="sum").fillna(0.0)

# liabilities by line (non-par, excl. seg funds, net of reinsurance), Tier A from the study; Tier C from LF3 directly
liab_rows = []
for s in STUDY_A:
    src = deck["liab_by_line"][s]["2025"]      # includes the study's Equitable Participating UL reclass (est)
    for ln in LINES:
        v = src.get(ln)
        liab_rows.append(dict(insurer=s, product_line=ln, net_icl_mm=v if v is not None else 0.0,
                              basis="est (Participating UL moved from par to individual insurance)" if s == "EQL" and ln == "Individual insurance"
                              else "OSFI LF3 Canada column, net of reinsurance, excl. seg funds"))
    liab_rows.append(dict(insurer=s, product_line="Participating", net_icl_mm=src.get("Participating") or 0.0, basis="memo: outside GenAcct"))
LINE_CODES = [("Individual insurance", "P2201002501", "P2201003501"), ("Individual annuity", "P2201005501", "P2201006501"),
              ("Group insurance", "P2201012501", "P2201013501"), ("Group annuity", "P2201015501", "P2201016501")]
for s, i in OSFI_ID.items():
    bs_net = oval(i, "P3507518001") - oval(i, "P3507545901")
    tot = oval(i, "P2201086901")
    sign = 1 if abs(tot - bs_net) < 1000 else -1
    assert abs(sign * tot - bs_net) < 1000, (s, tot, bs_net)
    lines_tot = oval(i, "P2201081901")
    incl_seg = abs(lines_tot - oval(i, "P3507538901") + oval(i, "P3507517001")) < 50_000
    seg = oval(i, "P3507537001") if incl_seg else 0.0
    if s == "primerica_life":
        continue   # term insurer: its non-seg insurance contracts are a net asset and seg funds sit in the individual line; mix not meaningful
    for ln, a, b in LINE_CODES:
        net = oval(i, a) - sign * oval(i, b) - (seg if ln == "Individual annuity" else 0.0)
        liab_rows.append(dict(insurer=s, product_line=ln, net_icl_mm=net / 1e3,
                              basis="OSFI LF3 Canada column, net of reinsurance (ALM method; not a signed-off study view)"))
liab = pd.DataFrame(liab_rows)
liab["insurer_name"] = liab.insurer.map(NAME)
core = liab[liab.product_line.isin(LINES)]
core_tot = core.groupby("insurer").net_icl_mm.sum()
liab["pct_of_nonpar"] = np.where(liab.product_line.isin(LINES), 100 * liab.net_icl_mm / liab.insurer.map(core_tot), np.nan)

# peer table
rows = []
for k, name, tier, group, ped, canon in PEERS:
    d = dict(insurer=k, insurer_name=name, group=group, tier=tier, tier_label=TIER_LABEL[tier], period_end=ped, on_canonical_list=canon)
    d.update(peer_rows.get(k, {}))
    if k in ga_cls.index:
        for c in CLASSES:
            d["pct_" + c.lower().replace(" / ", "_").replace(" ", "_")] = ga_cls.loc[k, c]
        d["pct_internally_managed"] = ga_l1.loc[k].get("Internally Managed", 0.0)
        d["pct_externally_managed"] = ga_l1.loc[k].get("Externally Managed", 0.0)
        d["pct_unclassified"] = ga_l1.loc[k].get("Unclassified", 0.0)
        d["illiquid_pct"] = float(ga_l3.loc[k, ILLIQUID].sum())
        d["non_fixed_income_pct"] = float(ga_l3.loc[k, NON_FI].sum())
    if k in core_tot.index and core_tot[k] > 0:
        c = core[core.insurer == k].set_index("product_line").net_icl_mm
        d["nonpar_icl_mm"] = float(core_tot[k])
        d["long_liab_pct"] = 100 * float(c["Individual insurance"] + c["Group annuity"]) / float(core_tot[k])
        for ln in LINES:
            d["liab_" + ln.lower().replace(" ", "_") + "_pct"] = 100 * float(c[ln]) / float(core_tot[k])
    gacct = d.get("genacct_mm")
    if gacct and d.get("surplus_mm") is not None:
        d["surplus_pct_genacct"] = 100 * d["surplus_mm"] / gacct
        d["csm_pct_genacct"] = 100 * (d["csm_abl_mm"] if d.get("csm_abl_mm") is not None else d["csm_total_mm"]) / gacct
        d["financing_pct_genacct"] = 100 * ((d.get("repos_mm") or 0) + (d.get("financing_other_mm") or 0)) / gacct
        d["repos_pct_genacct"] = 100 * (d.get("repos_mm") or 0) / gacct
        d["fcf_pct_genacct"] = 100 * d["fcf_mm"] / gacct
        d["derivative_liab_pct_genacct"] = 100 * (d.get("derivative_liab_mm") or 0) / gacct
        d["non_fi_to_surplus_x"] = d["non_fixed_income_pct"] / d["surplus_pct_genacct"] if d["surplus_pct_genacct"] else None
    own = sum(v for v in (gacct, d.get("par_mm"), d.get("ul_mm"), d.get("seg_backing_mm")) if v)
    if own and tier in ("A", "B"):
        d["own_assets_mm"] = own
        d["genacct_share_of_own_pct"] = 100 * gacct / own
    rows.append(d)
peers = pd.DataFrame(rows)

# basis effect: entity pool as filed (incl. par and UL; global for the Big 3) vs the GenAcct mix
eff = []
for i, s in POOL_ID.items():
    p = pool[(pool.id == i) & ~pool.l3.astype(str).str.startswith("Less")]
    g = p.assign(l3n=p.l3.map(norm_l3)).groupby("l3n").amount.sum()
    g = 100 * g / g.sum()
    pe = float(g.get("Common Shares", 0) + g.get("Preferred Shares", 0))
    pf = float(g.get("Commercial Mortgages", 0) + g.get("Illiquid Term Loan", 0))
    eff.append(dict(insurer=s, insurer_name=NAME[s],
                    entity_public_equity_pct=pe, genacct_public_equity_pct=float(ga_cls.loc[s, "Public equity"]),
                    entity_private_fi_pct=pf, genacct_private_fi_pct=float(ga_cls.loc[s, "Private fixed income"]),
                    entity_real_estate_pct=float(g.get("Real Estate Equity", 0)), genacct_real_estate_pct=float(ga_l3.loc[s, "Real Estate Equity"]),
                    entity_pool_mm=float(p.amount.sum()) / 1e3, genacct_mm=peer_rows[s]["genacct_mm"]))
eff = pd.DataFrame(eff)
eff["public_equity_change_pts"] = eff.genacct_public_equity_pct - eff.entity_public_equity_pct

# trend (entity, ex-UL, incl. par), accounting class: the study's deck data
PERIOD_END = {k: ped for k, n, t, g, ped, c in PEERS}
tr_rows, ac_rows = [], []
TR_CLS = ["Public Fixed Income", "Private Fixed Income", "Public Equity", "Cash & Cash Equivalent", "Other / unclassified"]
for s in STUDY_A:
    for date, v in sorted(deck["asset_trend"].get(s, {}).items()):
        for c in TR_CLS:
            tr_rows.append(dict(insurer=s, insurer_name=NAME[s], date=date, asset_class=c, pct=v.get(c) or 0.0, invested_ex_ul_bn=v["_total_bn"]))
    a = deck["acct"].get(s, {}).get(PERIOD_END[s])
    if a:
        for c, lab in (("fvtpl", "FVTPL"), ("fvoci", "FVOCI"), ("ac", "Amortized cost")):
            ac_rows.append(dict(insurer=s, insurer_name=NAME[s], accounting_class=lab, pct=a[c]))
trend = pd.DataFrame(tr_rows)
acct = pd.DataFrame(ac_rows)

# off-balance-sheet: repos, derivative notional (OSFI LF3 P2111, total notional columns), securities lending (filings)
ob = []
dn = assets[(assets.period == "2025Q4") & (assets.line_kind == "derivative_notional") & assets.dpa.str.endswith("07") & assets.l2.notna()]
DER_ID = dict(POOL_ID)
DER_ID.pop(28344)
DER_ID[28350] = "BMO"     # consolidated BMO Life Insurance Company, as the study's liability views
DER_ID.update({v: k for k, v in OSFI_ID.items()})
for i, s in DER_ID.items():
    x = dn[dn.id == i]
    inv = oval(i, "P2000207001") / 1e3
    for (l2, l3), v in x.assign(l3=x.l3.fillna("Linear and non-linear (not split)")).groupby(["l2", "l3"]).amount.sum().items():
        ob.append(dict(insurer=s, l1="Derivatives", l2=l2, l3=l3, amount_mm=v / 1e3, pct_of_entity_investments=100 * v / 1e3 / inv if inv else None,
                       scope="legal entity (global for Manulife, Sun Life, Canada Life)", source="OSFI LF3 P2111 gross notional"))
for s in STUDY_A + ["IAG", "BEN"]:
    v = peer_rows[s].get("repos_mm") or 0.0
    ob.append(dict(insurer=s, l1="Asset Financing", l2="Encumbered Assets", l3="Repos", amount_mm=v,
                   pct_of_genacct=100 * v / peer_rows[s]["genacct_mm"], scope="Canadian General Account",
                   source="OSFI LF3 P2203028001" if s in STUDY_A else "annual report"))
SEC_LEND = {"MFC": ("Manulife", "Securities lending: securities lent", 1, "consolidated"),
            "SLF": ("Sun Life", "Securities lent (carrying value)", 1, "consolidated"),
            "CLF": ("Great-West Lifeco", "Loaned securities (fair value", 1, "Lifeco consolidated"),
            "IAG": (IAG, "Securities loaned (carrying value", 1, "consolidated"),
            "BEN": (BEN, "Asset financing - Securities loaned", 1, "consolidated"),
            "EMP": ("The Empire Life Insurance Company", "Securities loaned - general funds", 1e-3, "entity, general funds"),
            "EQL": ("The Equitable Life Insurance Company of Canada", "Securities loaned (fair value)", 1e-3, "entity"),
            "WAW": ("The Wawanesa Life Insurance Company", "Securities on loan (fair value)", 1e-3, "entity")}
for s, (co, item, scale, scope) in SEC_LEND.items():
    ob.append(dict(insurer=s, l1="Asset Financing", l2="Encumbered Assets", l3="Security Lending", amount_mm=frow(co, item) * scale,
                   scope=scope, source="2025 financial statements"))
offbs = pd.DataFrame(ob)
offbs["insurer_name"] = offbs.insurer.map(NAME)

# look-through: alternatives and private assets in the companies' own 2025 filings (company-reported scope)
LT = []


def lt(s, scope, total, items):
    for cat, v, item in items:
        LT.append(dict(insurer=s, insurer_name=NAME[s], scope=scope, reported_invested_mm=total, l3=cat, amount_mm=v,
                       pct_of_reported=100 * v / total, source_item=item))


M = "Manulife"
lt("MFC", "MFC consolidated (global; incl. par and Manulife Bank)", frow(M, "Total invested assets", scope="consolidated"), [
    ("Asset Backed Securities", frow(M, "Debt securities: Mortgage / asset-backed"), "MBS / ABS"),
    ("Illiquid Term Loan", frow(M, "Private placements") + frow(M, "Leveraged leases"), "private placements, leveraged leases"),
    ("Commercial Mortgages", sum(frow(M, "Mortgages: " + x) for x in ("Commercial - Retail", "Commercial - Office", "Commercial - Multi-family",
                                                                  "Commercial - Industrial", "Commercial - Other", "Agricultural")), "commercial and agricultural mortgages"),
    ("Real Estate Equity", frow(M, "Real estate: Investment property") + frow(M, "Real estate: Own use"), "real estate (incl. own use 2,631)"),
    ("Infrastructure Equity", frow(M, "ALDA: Infrastructure"), "ALDA infrastructure"),
    ("Other Private Equity", frow(M, "ALDA: Private equity") + frow(M, "ALDA: Timber") + frow(M, "ALDA: Energy") + frow(M, "ALDA: Various other"),
     "ALDA private equity, timber and agriculture, energy, other"),
])
S = "Sun Life"
lt("SLF", "SLF consolidated (global; incl. par)", frow(S, "General fund invested assets: Total invested assets"), [
    ("Asset Backed Securities", frow(S, "Asset-backed securities") + frow(S, "Mortgages (commercial): insured"), "ABS; insured mortgages"),
    ("Illiquid Term Loan", frow(S, "Total loans (private placement loans)"), "private placement loans"),
    ("Commercial Mortgages", frow(S, "Mortgages (commercial): non-insured"), "non-insured mortgages"),
    ("Real Estate Equity", frow(S, "General fund invested assets: Investment properties"), "investment properties"),
    ("Other Private Equity", frow(S, "Other financial invested assets excluding CLOs"), "limited partnerships and funds (not split by type)"),
    ("Structured Products", frow(S, "Other financial invested assets - assets related to CLOs"), "CLO assets"),
])
G = "Great-West Lifeco"
gseg = filings[(filings.company == G) & (filings.scope == "canada_segment") & (filings.period == "FY2025")]
gv = lambda sw: float(gseg[gseg.source_item.astype(str).str.startswith(sw)].amount.iloc[0])
lt("CLF", "Lifeco Canada segment (incl. par)", gv("Invested assets, Canada: Total invested assets"), [
    ("Asset Backed Securities", gv("Invested assets, Canada: Mortgage loans: single-family"), "single-family residential mortgages"),
    ("Commercial Mortgages", gv("Invested assets, Canada: Mortgage loans: commercial") + gv("Invested assets, Canada: Mortgage loans: multi-family"),
     "commercial and multi-family mortgages (insured share not split)"),
    ("Reverse Mortgages", gv("Invested assets, Canada: Mortgage loans: equity release"), "equity release mortgages"),
    ("Real Estate Equity", gv("Invested assets, Canada: Investment properties"), "investment properties"),
])
lt("IAG", "iA consolidated (incl. US, par and UL backing)", float(ia.sum()), [
    ("Asset Backed Securities", ia["Asset Backed Securities"], "securitized and insured mortgages"),
    ("Illiquid Term Loan", ia["Illiquid Term Loan"], "private bond issues"),
    ("Commercial Mortgages", ia["Commercial Mortgages"], "uninsured mortgages"),
    ("Private Liquid Loans", ia["Private Liquid Loans"], "corporate loans"),
    ("Consumer Loans", ia["Consumer Loans"], "car loans and other loans"),
    ("Real Estate Equity", ia["Real Estate Equity"], "investment properties"),
])
lt("BEN", "Beneva consolidated ex policyholder-linked funds (incl. P&C)", float(ben.sum()), [
    ("Asset Backed Securities", ben["Asset Backed Securities"], "residential mortgages"),
    ("Illiquid Term Loan", ben["Illiquid Term Loan"], "other loans"),
    ("Commercial Mortgages", ben["Commercial Mortgages"], "non-residential mortgages"),
    ("Real Estate Equity", ben["Real Estate Equity"], "real estate in private companies; investment properties"),
    ("Infrastructure Equity", ben["Infrastructure Equity"], "infrastructure equity in private companies"),
    ("Other Private Equity", ben["Other Private Equity"], "other private companies; joint venture and associates"),
    ("Infrastructure Debt", ben["Infrastructure Debt"], "private debt (ALM repo maps it to infrastructure debt)"),
])
R = "RBC Life Insurance Company"
rbc_tot = (frow(R, "LF2 Total investments (balance sheet value)") - frow(R, "LF2 Bonds used to back index-linked") - frow(R, "LF2 Shares used to back index-linked")) / 1e3
lt("RBC", "RBC Life entity, ex UL policyholder funds (incl. par, about 1%); OSFI returns only", rbc_tot, [
    ("Illiquid Term Loan", (frow(R, "LF2 Bonds and debentures: Corporate - private (investment grade)") + frow(R, "LF2 Bonds and debentures: Corporate - private (below")) / 1e3,
     "private corporate bonds (OSFI LF2)"),
    ("Commercial Mortgages", frow(R, "LF2 Mortgage loans: total") / 1e3, "mortgage loans (OSFI LF2)"),
    ("Other invested (unclassified)", frow(R, "LF2 Other invested assets (amortized cost)") / 1e3, "OSFI other invested assets (amortized cost; type not public)"),
])
Q = "The Equitable Life Insurance Company of Canada"
lt("EQL", "Equitable entity (incl. par and Participating UL)", frow(Q, "Total invested assets", exact=True) / 1e3, [
    ("Illiquid Term Loan", frow(Q, "Private placements", exact=True) / 1e3, "private placements"),
    ("Commercial Mortgages", frow(Q, "Mortgages", exact=True) / 1e3, "mortgages"),
    ("Real Estate Equity", frow(Q, "Investment property", exact=True) / 1e3, "investment property"),
    ("Other Private Equity", frow(Q, "Equities - Level 3 limited-partnership units") / 1e3, "limited-partnership units: private equity and infrastructure (not split)"),
])
E = "The Empire Life Insurance Company"
lt("EMP", "Empire entity (incl. par)", frow(E, "Investments (balance sheet line)") / 1e3 + frow(E, "Investment in associates") / 1e3, [
    ("Commercial Mortgages", frow(E, "Mortgages", exact=True) / 1e3, "mortgages"),
    ("Private Liquid Loans", frow(E, "Loans", exact=True) / 1e3, "loans"),
    ("Other Private Equity", frow(E, "Investment in associates") / 1e3, "associates and joint venture"),
])
W = "The Wawanesa Life Insurance Company"
lt("WAW", "Wawanesa entity (incl. par)", frow(W, "Investments including securities on loan") / 1e3, [
    ("Pooled Fund Units", frow(W, "Stocks - Common (incl. units in equity pooled funds)") / 1e3,
     "common stocks incl. units in equity pooled funds (OSFI files them as other invested assets)"),
])
look = pd.DataFrame(LT)

# --------------------------------------------------------------------------------------------------
# Write
# --------------------------------------------------------------------------------------------------
mix_out = mix[["insurer", "insurer_name", "block", "l1", "l2", "l3", "asset_class", "amount_mm", "pct_of_block", "basis"]]
mix_out.to_csv(OUT / "block_mix_l3.csv", index=False, float_format="%.4f")
cls_long = (ga.groupby(["insurer", "insurer_name", "asset_class"]).agg(amount_mm=("amount_mm", "sum"), pct_of_genacct=("pct_of_block", "sum")).reset_index())
cls_long.to_csv(OUT / "genacct_mix_l2.csv", index=False, float_format="%.4f")
peers.to_csv(OUT / "peers.csv", index=False, float_format="%.4f")
liab[["insurer", "insurer_name", "product_line", "net_icl_mm", "pct_of_nonpar", "basis"]].to_csv(OUT / "liabilities_by_line.csv", index=False, float_format="%.4f")
eff.to_csv(OUT / "basis_effect.csv", index=False, float_format="%.4f")
trend.to_csv(OUT / "trend_l2_entity.csv", index=False, float_format="%.4f")
acct.to_csv(OUT / "accounting_class.csv", index=False, float_format="%.4f")
offbs.to_csv(OUT / "off_balance_sheet.csv", index=False, float_format="%.4f")
look.to_csv(OUT / "lookthrough_filings.csv", index=False, float_format="%.4f")

data = dict(
    meta=dict(alm_repo="MooseDragon/cdn-life-insurer-alm", alm_commit=alm_commit, anchor="fiscal 2025 year-ends (RBC Life, BMO Life Oct 31, 2025; others Dec 31, 2025)",
              classes=CLASSES, l3=L3S, l1_of=L1_OF, l2_of=L2_OF, class_of=CLS_OF, lines=LINES, tier_label=TIER_LABEL),
    peers=json.loads(peers.to_json(orient="records")),
    mix=json.loads(mix_out.to_json(orient="records")),
    liab=json.loads(liab.to_json(orient="records")),
    basis_effect=json.loads(eff.to_json(orient="records")),
    trend=json.loads(trend.to_json(orient="records")),
    acct=json.loads(acct.to_json(orient="records")),
    offbs=json.loads(offbs.to_json(orient="records")),
    lookthrough=json.loads(look.to_json(orient="records")),
    runoff=deck.get("runoff_summary", []),
)
(OUT / "data.json").write_text(json.dumps(clean(data), indent=1))

pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 200)
print("ALM commit", alm_commit)
print(ga_cls.round(1).assign(GenAcct_mm=pd.Series({k: v.get("genacct_mm") for k, v in peer_rows.items()}).round(0)).to_string())
print(ga_l3.round(1).T.to_string())
show = ["insurer", "genacct_mm", "par_mm", "ul_mm", "fcf_pct_genacct", "csm_pct_genacct", "surplus_pct_genacct", "financing_pct_genacct",
        "long_liab_pct", "illiquid_pct", "non_fixed_income_pct", "non_fi_to_surplus_x", "buffer_pct", "capital_ratio_pct"]
print(peers[show].round(1).to_string())
print(eff.round(1).to_string())
print(liab.pivot_table(index="insurer", columns="product_line", values="net_icl_mm").round(0).to_string())
print(look.pivot_table(index=["insurer", "scope"], columns="l3", values="pct_of_reported").round(1).to_string())
print(offbs.pivot_table(index="insurer", columns=["l1", "l3"], values="amount_mm", aggfunc="sum").round(0).to_string())
