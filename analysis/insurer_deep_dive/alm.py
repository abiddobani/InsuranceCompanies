"""Canada-basis data layer for the deep-dive deck, built on the cdn-life-insurer-alm repository.

The ALM repository (MooseDragon/cdn-life-insurer-alm) is the project's primary framework for assessing Canadian life
insurers. This script reads its processed data and writes alm.json, keyed by the deck's company ids, on the repo's
definitions: Canadian business only, net of reinsurance, "General Account, excl. par / seg fund" (GenAcct), CSM split
three ways, Surplus, buffer, par share, financing / GenAcct, reinsurance / GenAcct, and the L1/L2/L3 asset taxonomy.

Four kinds of view come out:
  study   the 11 OSFI filers in the ALM study that are on the project's insurer list (repo outputs, unchanged)
  built   Canadian Premier Life and Primerica Life Canada: OSFI filers outside the study, built here from the repo's
          OSFI panel with the rules of its simple all-Canada scripts (build_iof_genacct.py). Not reviewed in the study.
  amf     iA and Beneva (AMF rule: total CSM only, buffer n/a, memo buffer on total CSM); Desjardins liabilities only
  none    Assumption Life, Humania, UV Insurance: no OSFI return and outside the study (the deck keeps their
          financial-statement figures from quant.json and says so); Canada Protection Plan is a Foresters Life brand

Run with the ALM repository's uv environment (it needs pandas and pyarrow):
    ALM_REPO=/path/to/cdn-life-insurer-alm uv run --project $ALM_REPO python analysis/insurer_deep_dive/alm.py
"""
import json
import math
import os
import subprocess
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ALM = Path(os.environ.get("ALM_REPO", HERE.parents[2] / "cdn-life-insurer-alm"))
P = ALM / "data" / "processed"

SID = {"rbc_life": "RBC", "bmo_life": "BMO", "manulife": "MFC", "sun_life": "SLF", "canada_life": "CLF",
       "empire_life": "EMP", "ivari": "IVA", "equitable_life": "EQL", "cooperators_life": "COP",
       "foresters_life": "IOF", "wawanesa_life": "WAW", "ia": "IAG", "beneva": "BEN", "desjardins": "DFS"}
BUILT = {"canadian_premier": ("28358", "Canadian Premier Life Insurance Company"),
         "primerica_life": ("28419", "Primerica Life Insurance Company of Canada")}
OSFI_ID = {"RBC": 28395, "BMO": 28350, "MFC": 28397, "SLF": 28429, "CLF": 28386, "EMP": 28375, "IVA": 28414,
           "EQL": 28377, "COP": 28368, "IOF": 28432, "WAW": 28434}

# Entity register and peer playbook of the ALM repository (docs/DATA.md, docs/METHODOLOGY.md), shortened.
ENTITY = {
    "RBC": dict(entity="RBC Life Insurance Company (OSFI 28395)", fye="Oct 31", basis="All Canada; equity from OSFI LF1",
                consolidates="No OSFI-filing subsidiaries", excluded="Other RBC Insurance entities (e.g. reinsurance) are outside scope",
                flags=["Repos are large and count as GenAcct financing", "Seg fund and par CSM are estimates (LICAT gap; pro rata)",
                       "UL policyholder fund partly filed as preferred shares"]),
    "BMO": dict(entity="BMO Life Insurance Company (OSFI 28350)", fye="Oct 31", basis="Audited consolidated FS = OSFI LF1; reported equity",
                consolidates="BMO Life Assurance Company (OSFI 28344)", excluded="Effectively all Canada (about $4MM outside Canada)",
                flags=["Par block shown only when it is 1% or more (2024 yes, 2025 no)", "Mortgage loans on investment property count as financing"]),
    "MFC": dict(entity="The Manufacturers Life Insurance Company (OSFI 28397)", fye="Dec 31", basis="OSFI LF3 In Canada schedule; equity = assets less liabilities (est)",
                consolidates="Manulife Assurance Company of Canada (OSFI 132948)", excluded="US (John Hancock) and Asia: excluded by the In Canada schedule; Manulife Bank kept in Other",
                flags=["In Canada assets follow asset territory, so Surplus and the buffer are unreliable", "Asset mix follows the global mix", "Seg fund and par CSM are estimates"]),
    "SLF": dict(entity="Sun Life Assurance Company of Canada (OSFI 28429)", fye="Dec 31", basis="OSFI LF3 In Canada schedule; equity = assets less liabilities",
                consolidates="Sun Life Insurance (Canada) Limited (OSFI 28430; PRT business)", excluded="US and Asia: excluded by the In Canada schedule",
                flags=["Asset mix follows the global mix", "Closed-block and Clarica par CSM are estimates", "Preferred shares (debt) sit in Surplus"]),
    "CLF": dict(entity="The Canada Life Assurance Company (OSFI 28386)", fye="Dec 31", basis="OSFI LF3 In Canada schedule; equity = assets less liabilities",
                consolidates="The Canada Life Insurance Company of Canada (OSFI 28353)", excluded="Europe, Capital and Risk Solutions, and the US retained par block: excluded; Empower is not under this entity",
                flags=["Asset mix uses the disclosed Canada column", "Seg fund BEL + RA is an estimate (no Canada guarantee line filed)", "Preferred shares (debt) sit in Surplus"]),
    "EMP": dict(entity="The Empire Life Insurance Company (OSFI 28375)", fye="Dec 31", basis="All Canada; OSFI LF1 equity plus non-controlling interests",
                consolidates="No OSFI-filing subsidiaries", excluded="Nothing: all Canada, OSFI totals = audited FS",
                flags=["Seg fund CSM = Wealth Management CSM x 96.5% (2024 LICAT gap)", "Par CSM estimated within Individual"]),
    "IVA": dict(entity="ivari (OSFI 28414)", fye="Dec 31", basis="All Canada; OSFI LF1 equity",
                consolidates="No OSFI-filing subsidiaries", excluded="Nothing: all Canada, OSFI totals = audited FS",
                flags=["Funds-withheld reinsurer deposit counts as reinsurance-linked financing", "Par under 1% stays in fulfilment cash flows", "Retained deficit"]),
    "EQL": dict(entity="The Equitable Life Insurance Company of Canada (OSFI 28377)", fye="Dec 31", basis="All Canada; non-par policyholders' equity (mutual)",
                consolidates="No OSFI-filing subsidiaries", excluded="Nothing: all Canada, OSFI totals = audited FS",
                flags=["Par block is about three times GenAcct: a structural outlier", "Par CSM is an estimate"]),
    "COP": dict(entity="Co-operators Life Insurance Company (OSFI 28368), consolidated", fye="Dec 31", basis="All Canada; OSFI only (no public financial statements)",
                consolidates="No OSFI-filing subsidiaries", excluded="Co-operators General (P&C) is a sister company, not consolidated",
                flags=["OSFI-only limits: no notes, no sensitivities", "Seg fund CSM is an estimate (LICAT gap)"]),
    "IOF": dict(entity="Foresters Life Insurance Company (OSFI 28432), consolidated", fye="Dec 31", basis="All Canada; OSFI LF1 shareholders' equity",
                consolidates="Its own subsidiary", excluded="Nothing: all Canada, OSFI totals = audited FS",
                flags=["In-force non-par block is 100% quota-share coinsured to the parent, so reinsurance exceeds GenAcct", "Seg fund CSM is an estimate (LICAT gap)"]),
    "WAW": dict(entity="The Wawanesa Life Insurance Company (OSFI 28434)", fye="Dec 31", basis="All Canada; OSFI LF1 shareholders' equity",
                consolidates="No OSFI-filing subsidiaries", excluded="Nothing: all Canada, OSFI totals = audited FS",
                flags=["Annuity and seg fund CSM are disclosed together, so seg fund BEL + RA is approximate"]),
    "IAG": dict(entity="iA Financial Corporation, consolidated (AMF)", fye="Dec 31", basis="Audited FS with the US Operations carved out",
                consolidates="iA Insurance and all subsidiaries", excluded="US Operations (capital allocated to the US by proxy); iA P&C is not carved out",
                flags=["AMF filer: total CSM only, so ABL / seg fund / par CSM and the buffer are n/a", "Par and UL are not separable",
                       "Capital ratio is CARLI (AMF), not LICAT"]),
    "BEN": dict(entity="Beneva Group Inc., consolidated (AMF)", fye="Dec 31", basis="Audited FS with P&C and policyholder-linked funds carved out",
                consolidates="Beneva Inc. and all subsidiaries", excluded="P&C (capital allocated by proxy) and policyholder-linked funds",
                flags=["AMF filer: total CSM only, so ABL / seg fund / par CSM and the buffer are n/a", "Gore Mutual amalgamated on Jan 1, 2026 (affects fiscal 2026)",
                       "Capital ratio is the AMF solvency ratio, not LICAT"]),
    "DFS": dict(entity="Desjardins Financial Security (AMF)", fye="Dec 31", basis="No public balance sheet: liability side only",
                consolidates="n/a", excluded="Assets, equity, par, UL, financing and the capital ratio are not public",
                flags=["Excluded from the buffer and leverage measures", "AMF filer: total CSM only"]),
}
LINES = ["Individual insurance", "Individual annuity", "Group insurance", "Group annuity", "Participating"]


def f(x):
    try:
        x = float(x)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def mm(x):
    x = f(x)
    return None if x is None else round(x / 1000.0, 3)


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, float):
        return None if math.isnan(o) else round(o, 4)
    if hasattr(o, "item"):
        return clean(o.item())
    return o


V2 = json.loads((ALM / "deck" / "alm_peer_deck_v2.json").read_text())
D3 = json.loads((ALM / "deck" / "deck3_data.json").read_text())
LC = json.loads((ALM / "deck" / "licat_deck_data.json").read_text())
LS = json.loads((ALM / "deck" / "licat_story_data.json").read_text())
SUMM = {y: pd.read_csv(P / f"peer_summary_{y}q4.csv").set_index("short_id") for y in (2023, 2024, 2025)}
ASSETS = pd.read_csv(P / "osfi_assets_long.csv", low_memory=False)
FIL = pd.read_csv(P / "filings_all_long.csv", low_memory=False)
OSFI = pd.read_parquet(P / "osfi_long.parquet", columns=["id", "dpa", "per", "label", "value_num", "entity"])


# ---------------------------------------------------------------- shared pieces
def year_block(row):
    """One fiscal year-end on the repo's summary definitions ($MM)."""
    g = lambda k: mm(row.get(k))
    b = dict(date=str(row.get("period_end_date")), ga=g("genacct_k"), fcf=g("fcf_k"), surplus=g("surplus_k"),
             csm_abl=g("csm_abl_k"), seg_csm=g("seg_csm_k"), par_csm=g("par_csm_memo_k"), csm_total=g("csm_total_k"),
             seg_csm_basis=row.get("seg_csm_basis"), par_csm_basis=row.get("par_csm_basis"),
             repos=g("repos_k"), fin_other=g("financing_other_k"), deriv_liab=g("derivative_liab_k"), deriv_assets=g("derivative_assets_k"),
             ul=g("ul_ph_fund_k"), seg_fv=g("seg_fund_value_k"), seg_bel_ra=g("seg_bel_ra_k"), par=g("par_account_k"),
             inv_contracts=g("investment_contracts_k"), reins_assets=g("reinsurance_assets_k"),
             buffer=f(row.get("buffer_pct")), buffer_memo=f(row.get("buffer_total_csm_pct")), surplus_pct=f(row.get("surplus_pct")),
             fin_pct=f(row.get("financing_pct")), reins_pct=f(row.get("reinsurance_pct")), par_share=f(row.get("par_pct")),
             cap_ratio=f(row.get("capital_ratio_pct")), cap_basis=row.get("capital_ratio_basis"))
    for k in ("seg_csm_basis", "par_csm_basis", "cap_basis"):
        if not isinstance(b[k], str):
            b[k] = None
    return b


def per_date(per):
    """Period-end date of a calendar-year filer's quarter label (2025Q4 -> 2025-12-31)."""
    return f"{per[:4]}-" + {"Q1": "03-31", "Q2": "06-30", "Q3": "09-30", "Q4": "12-31"}[per[-2:]]


def asset_panel(osfi_id):
    """L3 balances by period from the repo's OSFI asset panel ($MM), plus accounting class and derivative notionals."""
    a = ASSETS[ASSETS.id == int(osfi_id)]
    out = {}
    for per, x in a.groupby("period"):
        inv = x[x.line_kind == "invested_asset_class"].copy()
        inv["l3"] = inv.l3.fillna("Other invested (unclassified)")
        inv["l2"] = inv.l2.fillna("Other / unclassified")
        inv["l1"] = inv.l1.fillna("Internally Managed")
        l3 = inv.groupby(["l1", "l2", "l3"]).amount.sum()
        acct = inv.groupby("accounting_class").amount.sum()
        dn = x[(x.line_kind == "derivative_notional") & x.source_item.str.contains("Total Notional Amount") & x.l2.notna()]
        ul = x[(x.line_kind == "index_linked_memo") & x.source_item.str.startswith("Total Investments")].amount.sum()
        date = x.period_end_date.dropna().iloc[0] if x.period_end_date.notna().any() else per_date(per)
        out[per] = dict(date=str(date), total=mm(inv.amount.sum()), ul=mm(ul),
                        l3=[dict(l1=k[0], l2=k[1], l3=k[2], mm=mm(v)) for k, v in l3.items() if v],
                        acct={str(k): mm(v) for k, v in acct.items()},
                        deriv={f"{k[0]} / {k[1]}": mm(v) for k, v in dn.groupby(["l2", dn.l3.fillna("n/s")]).amount.sum().items()})
    return out


def new_money(panel):
    """Additions by L3 class = closing balance less opening balance (no run-off; est). Fiscal 2024 to 2025, then to the latest quarter."""
    pers = sorted(panel)
    out = []
    for a, b in zip(pers, pers[1:]):
        if a[-2:] != "Q4":
            continue
        o = {r["l3"]: r for r in panel[a]["l3"]}
        c = {r["l3"]: r for r in panel[b]["l3"]}
        rows = []
        for k in sorted(set(o) | set(c)):
            r = c.get(k) or o.get(k)
            rows.append(dict(l3=k, l2=r["l2"], open=(o.get(k) or {}).get("mm") or 0.0, close=(c.get(k) or {}).get("mm") or 0.0))
        out.append(dict(start=panel[a]["date"], end=panel[b]["date"], open_total=panel[a]["total"], close_total=panel[b]["total"], rows=rows))
    return out


def licat_hist_generic(osfi_id):
    x = OSFI[(OSFI.id == str(osfi_id)) & (OSFI.dpa == "D1010010020") & ~OSFI.label.str.contains("prior", case=False)]
    return {per_date(p): f(v) for p, v in x.drop_duplicates("per").set_index("per").value_num.items() if f(v)}


# ---------------------------------------------------------------- study peers
def study(sid):
    c = dict(sid=sid, status="study", **ENTITY[sid])
    c["years"] = {}
    for y in (2023, 2024, 2025):
        if sid in SUMM[y].index and f(SUMM[y].loc[sid].get("genacct_k")) is not None:
            c["years"][str(y)] = year_block(SUMM[y].loc[sid])
    bs = pd.read_csv(P / f"{sid.lower()}_genacct_bs_2025q4.csv")
    c["bs"] = [dict(side=r.side, group=r.group, item=r["item"], mm=mm(r.amount_k), basis=r.basis) for _, r in bs.iterrows()
               if f(r.amount_k) is not None]
    c["liab_line"] = V2["liab_by_line"].get(sid) or {}
    c["rev_line"] = V2["revenue_by_line"].get(sid) or {}
    c["earn"] = V2["earn"].get(sid) or {}
    c["asset_trend"] = V2["asset_trend"].get(sid) or {}
    al = V2["alloc"].get(sid) or {}
    c["alloc"] = dict(l3=[dict(l3=k, **v) for k, v in (al.get("l3") or {}).items()], par_basis=al.get("par_basis"), basis_note=al.get("basis_note"))
    c["acct"] = V2["acct"].get(sid) or {}
    c["licat_hist"] = V2["licat_hist"].get(sid) or {}
    c["cap"] = LC["cur"].get(sid) or {}
    c["cap_prev"] = {k: (LC["prev"].get(sid) or {}).get(k) for k in ("ratio", "core", "bsb", "free125")}
    c["per100"] = LS["per100"].get(sid)
    c["sens"] = [s for s in V2["sens_summary"] if s["peer"] == sid]
    c["curve"] = V2["curves"].get(sid) or {}
    c["pledged"] = V2["pledged_summary"].get(sid)
    c["ul"] = V2["ul"].get(sid) or {}
    c["reins_ceded"] = V2["reins_ceded"].get(sid)
    c["csm_roll"] = D3["csm_roll"].get(sid)
    c["nb_csm"] = D3["nb_csm"].get(sid)
    c["csm_release"] = V2["csm_release"].get(sid)
    c["maturity"] = next((m for m in V2["maturity_summary"] if m["peer"] == sid), None)
    c["runoff"] = next((m for m in V2["runoff_summary"] if m["peer"] == sid), None)
    panel = asset_panel(OSFI_ID[sid])
    c["panel_basis"] = "legal entity, all territories (OSFI LF2)" if sid in ("MFC", "SLF", "CLF") else "legal entity (OSFI LF2)"
    c["new_money"] = new_money(panel)
    c["deriv"] = {p: v["deriv"] for p, v in panel.items() if v["deriv"]}
    return c


# ---------------------------------------------------------------- OSFI filers outside the study, on the repo's rules
def built(osfi_id, legal):
    c = dict(sid=None, status="built", entity=f"{legal} (OSFI {osfi_id})", fye="Dec 31", basis="All Canada; OSFI LF1 shareholders' equity",
             consolidates="No OSFI-filing subsidiaries", excluded="Nothing: LF3 In Canada totals equal LF1 totals",
             flags=["Outside the ALM study: built for this deck from the study's OSFI panel on its all-Canada rules, not reviewed there",
                    "OSFI only: no notes, so no sensitivities, pledged assets or affiliated reinsurance split"])
    c["years"], c["liab_line"], c["earn"] = {}, {}, {}
    rev = {}
    licat_gap = {}
    for y in (2023, 2024, 2025):
        per = f"{y}Q4"
        d = OSFI[(OSFI.id == osfi_id) & (OSFI.per == per) & ~OSFI.label.str.contains("prior", case=False)].drop_duplicates("dpa")
        r = d.set_index("dpa").value_num
        lab = d.set_index("dpa").label
        v = lambda k: float(r.get(k, 0) or 0)
        A = dict(cash=v("P3507501001"), accrued=v("P3507502001"), investments=v("P3507507001"), deriv_a=v("P3507510001"),
                 seg=v("P3507516001"), ica=v("P3507517001"), reins_a=v("P3507518001"))
        total = v("P3507519901")
        other_assets = total - sum(A.values())
        L = dict(icl_ex_seg=v("P3507535001"), seg_guar=v("P3507536001"), seg_ins=v("P3507537001"), reins_l=v("P3507545901"), ic=v("P3507547001"))
        total_l = v("P3507559901")
        other_liab = total_l - sum(L.values())
        se, par_eq, equity = v("P2000459901"), v("P2000442001"), v("P2000469901")
        # all Canada: LF3 In Canada totals equal LF1 totals to within 0.5% (Canadian Premier 2024 has $1MM outside Canada)
        assert abs(total - v("P2000299901")) < 0.005 * total and abs(total_l + equity - total) < 0.005 * total, (osfi_id, per)
        csm_total = v("P3508529999") - v("P3508539999")
        # seg fund CSM: LF3 CSM less the LICAT CSM line while the old LICAT form (CSM "other than" seg funds) is filed; the
        # latest old-form ratio to total CSM is held afterwards (the repo's seg_csm.py rule)
        lca = v("D2040010025") - v("D2040010015")
        old_form = "other than" in str(lab.get("D2040010025", "")).lower()
        if L["seg_ins"] and old_form and csm_total:
            licat_gap[y] = max(csm_total - lca, 0.0) / csm_total
        seg_csm = (licat_gap[max(licat_gap)] * csm_total) if (L["seg_ins"] and licat_gap) else 0.0
        seg_basis = None if not L["seg_ins"] else ("est (LICAT gap)" if y in licat_gap else "est (LICAT gap ratio of the last old-form year held)")
        par_icl = v("P2201051001") - v("P2201053001")
        par_assets = par_icl + par_eq
        ul = v("P2101288970")
        repos, deriv_l = v("P2203028001"), v("P2000407001")
        genacct = A["investments"] + A["cash"] + A["accrued"] - par_assets - L["ic"] - ul
        se_other = other_assets + A["deriv_a"] - (other_liab - repos - deriv_l)
        surplus = se - se_other + A["deriv_a"] - deriv_l      # derivative lines sit in GenAcct, as in the repo scripts
        csm_abl = csm_total - seg_csm                           # par under 1% of GenAcct stays in FCF (repo precedent)
        buffer = (surplus + csm_abl - (deriv_l - A["deriv_a"])) / (genacct - repos - A["deriv_a"]) * 100
        fcf = genacct - csm_abl - seg_csm - surplus - repos
        # the residual must equal the filed lines: ICL ex seg + seg guarantee line - insurance contract assets - CSM - net reinsurance
        assert abs(fcf - (L["icl_ex_seg"] + L["seg_guar"] - A["ica"] - csm_total - A["reins_a"] + L["reins_l"])) < 0.005 * total, (osfi_id, per)
        if fcf < 0:   # net fulfilment cash flows are an asset (term book, heavily reinsured): the buffer has no liability base to cushion
            buffer = None
            c["buffer_note"] = "n/m: fulfilment cash flows net of reinsurance are a net asset, so Surplus plus CSM exceeds GenAcct"
        reins_net = A["reins_a"] - L["reins_l"]
        c["years"][str(y)] = dict(
            date=f"{y}-12-31", ga=mm(genacct), fcf=mm(fcf), surplus=mm(surplus), csm_abl=mm(csm_abl),
            seg_csm=mm(seg_csm), par_csm=0.0, csm_total=mm(csm_total), seg_csm_basis=seg_basis, par_csm_basis=None, repos=mm(repos), fin_other=0.0,
            deriv_liab=mm(deriv_l), deriv_assets=mm(A["deriv_a"]), ul=mm(ul), seg_fv=mm(A["seg"]), seg_bel_ra=mm(L["seg_guar"] - seg_csm) if L["seg_ins"] else None,
            par=mm(par_assets), inv_contracts=mm(L["ic"]), reins_assets=mm(A["reins_a"]), reins_liab=mm(L["reins_l"]), ins_contract_assets=mm(A["ica"]),
            buffer=buffer, buffer_memo=None, surplus_pct=surplus / genacct * 100, fin_pct=repos / genacct * 100,
            reins_pct=A["reins_a"] / genacct * 100, par_share=par_assets / (par_assets + genacct) * 100 if par_assets > 0 else 0.0,
            cap_ratio=v("D1010010020"), cap_basis="LICAT total", total_assets=mm(total), equity=mm(se))
        # liabilities by line, net of reinsurance held; seg fund insurance liabilities taken out of the line that carries them
        lines = {"Individual insurance": v("P2201002501") - v("P2201003501"), "Individual annuity": v("P2201005501") - v("P2201006501"),
                 "Group insurance": v("P2201012501") - v("P2201013501"), "Group annuity": v("P2201015501") - v("P2201016501"),
                 "Participating": par_icl}
        if L["seg_ins"]:
            host = "Individual annuity" if lines["Individual annuity"] >= L["seg_ins"] else "Individual insurance"
            lines[host] -= L["seg_ins"] + L["seg_guar"]
            c["seg_line_host"] = host
        if y >= 2024:   # 2023 lines are filed on a different row layout for these two filers
            c["liab_line"][str(y)] = {k: mm(x) for k, x in lines.items()}
        ins_rev = v("P2002201001") + v("P2002202001") + v("P2002203001")
        isr = v("P2002219901")
        nir = v("P2002239901")
        ni = v("P2002299901") or v("P2002251001")
        if y >= 2024:
            c["earn"][str(y)] = dict(ins_rev=mm(ins_rev), isr=mm(isr), nir=mm(nir), ni=mm(ni), equity=mm(se),
                                     roe=ni / se * 100 if se else None, reins_held_assets=mm(A["reins_a"]), invested=mm(A["investments"]))
        if y == 2025:
            bsb = v("D1010010360")
            comp = dict(credit=v("D3000010077"), market=v("D5000010057"), insurance=v("D6000010257"),
                        seg_risk=v("D1010010240") or v("D1010010280"), operational=v("D1010010340"))
            tot = sum(comp.values()) or 1
            avail = v("D1010010040") + v("D1010010050")
            res = avail + v("D1010010060") + v("D1010010070")
            c["cap"] = dict(ratio=v("D1010010020"), core=v("D1010010010"), bsb=mm(bsb), resources=mm(res),
                            free125=mm(res - 1.25 * bsb), free100=mm(res - bsb), div_credit=mm(v("D1010010310")),
                            mix={k.replace("seg_risk", "seg"): x / tot * 100 for k, x in comp.items()}, **{k: mm(x) for k, x in comp.items()})
            c["bs"] = [dict(side="asset", group="General Account", item="General Account assets (investments, cash, accrued income)", mm=mm(genacct), basis="est"),
                       dict(side="asset", group="Reinsurance", item="Reinsurance contract held assets", mm=mm(A["reins_a"]), basis="disclosed"),
                       dict(side="asset", group="Segregated funds", item="Segregated funds net assets", mm=mm(A["seg"]), basis="disclosed"),
                       dict(side="asset", group="Other assets", item="Insurance contract assets and other assets", mm=mm(A["ica"] + other_assets + A["deriv_a"]), basis="disclosed")]
    c["rev_line"] = rev
    c["licat_hist"] = licat_hist_generic(osfi_id)
    panel = asset_panel(osfi_id)
    c["panel"] = panel
    c["new_money"] = new_money(panel)
    c["asset_trend"] = {}
    for per, pv in panel.items():
        tot = sum(r["mm"] for r in pv["l3"]) or 1
        t = {}
        for r in pv["l3"]:
            t[r["l2"]] = t.get(r["l2"], 0) + r["mm"] / tot * 100
        t.update(_total_bn=tot / 1000, _ul_bn=(pv["ul"] or 0) / 1000)
        c["asset_trend"][pv["date"]] = t
    last = panel.get("2025Q4") or {}
    c["alloc"] = dict(l3=[dict(l3=r["l3"], l2=r["l2"], l1=r["l1"], nonpar=r["mm"], par=0.0, ul=0.0) for r in last.get("l3", [])],
                      par_basis=None, basis_note="OSFI LF2 invested assets, legal entity (no par, UL or seg assets in the pool)")
    c["acct"] = {pv["date"]: {k2: (pv["acct"].get(k1) or 0) / (sum(pv["acct"].values()) or 1) * 100
                              for k1, k2 in (("FVTPL", "fvtpl"), ("FVOCI", "fvoci"), ("Amortized cost", "ac"))} for pv in panel.values()}
    c["deriv"] = {p: v["deriv"] for p, v in panel.items() if v["deriv"]}
    c["sens"], c["curve"], c["pledged"], c["ul"] = [], {}, None, {}
    del c["panel"]
    return c


# ---------------------------------------------------------------- AMF filers
def amf(sid, company):
    c = dict(sid=sid, status="amf" if sid != "DFS" else "amf_liab", **ENTITY[sid])
    c["years"] = {}
    for y in (2023, 2024, 2025):
        if sid in SUMM[y].index:
            b = year_block(SUMM[y].loc[sid])
            if b["ga"] is not None or b["csm_total"] is not None:
                c["years"][str(y)] = b
    fn = P / (f"{sid.lower()}_genacct_bs_2025q4.csv" if sid != "DFS" else "dfs_liabilities_2025q4.csv")
    bs = pd.read_csv(fn)
    c["bs"] = [dict(side=(r.get("side") if isinstance(r.get("side"), str) else "liability"), group=r.group, item=r["item"], mm=mm(r.amount_k), basis=r.basis)
               for _, r in bs.iterrows() if f(r.amount_k) is not None]
    x = FIL[(FIL.company == company) & (FIL.period == "FY2025")]
    a = x[x.metric_group.eq("assets") & x.nesting.eq("leaf") & x.l3.notna() & x.amount.notna()]
    dn = a[a.l1.eq("Derivatives")]
    a = a[a.l1.ne("Derivatives")]
    if sid != "IAG":   # the repo maps only iA's invested assets to L3; Beneva's leaves are fund units and Desjardins has no DFS-only mix
        a = a.iloc[0:0]
    c["deriv"] = {"2025Q4": {f"{k[0]} / {k[1]}": float(v) for k, v in dn.groupby(["l2", "l3"]).amount.sum().items()}} if len(dn) and sid == "IAG" else {}
    l3 = a.groupby(["l1", "l2", "l3"], dropna=False).amount.sum()
    c["alloc"] = dict(l3=[dict(l1=k[0] if isinstance(k[0], str) else "Internally Managed", l2=k[1], l3=k[2], nonpar=float(v), par=0.0, ul=0.0) for k, v in l3.items() if v],
                      par_basis=None, basis_note="Consolidated invested assets from the 2025 annual report on the L3 taxonomy; par, UL and US assets are not separable")
    tot = sum(r["nonpar"] for r in c["alloc"]["l3"]) or 1
    t = {}
    for r in c["alloc"]["l3"]:
        t[r["l2"]] = t.get(r["l2"], 0) + r["nonpar"] / tot * 100
    t["_total_bn"] = tot / 1000
    c["asset_trend"] = {"2025-12-31": t} if c["alloc"]["l3"] else {}
    c["sens_rows"] = [dict(item=str(r.source_item), amount=f(r.amount), units=str(r.units)) for _, r in x[x.metric_group.eq("sensitivity")].iterrows()]
    c["cap_rows"] = [dict(item=str(r.source_item), amount=f(r.amount), units=str(r.units)) for _, r in x[x.metric_group.isin(["capital", "leverage"])].iterrows()]
    c["liab_line"], c["rev_line"], c["earn"], c["acct"], c["licat_hist"], c["new_money"] = {}, {}, {}, {}, {}, []
    c["sens"], c["curve"], c["pledged"], c["ul"] = [], {}, None, {}
    return c


# ---------------------------------------------------------------- assemble
OUT = {}
for cid, sid in SID.items():
    OUT[cid] = study(sid) if sid in OSFI_ID else amf(sid, {"IAG": "iA Financial Group", "BEN": "Beneva", "DFS": "Desjardins"}[sid])
for cid, (oid, legal) in BUILT.items():
    OUT[cid] = built(oid, legal)
OUT["canada_protection_plan"] = dict(sid=None, status="covered", covered_by="foresters_life")
for cid in ("assumption_life", "humania", "uv_insurance"):
    OUT[cid] = dict(sid=None, status="none")


def alts_share(c):
    """Private fixed income plus externally managed and real-asset holdings, % of the non-par, non-UL pool (L3 taxonomy)."""
    rows = (c.get("alloc") or {}).get("l3") or []
    tot = sum(max(r.get("nonpar") or 0, 0) for r in rows)
    if not tot:
        return None
    alt = sum(max(r.get("nonpar") or 0, 0) for r in rows
              if r.get("l2") == "Private Fixed Income" or str(r.get("l1")).startswith("Externally")
              or any(w in str(r.get("l3")) for w in ("Real Estate", "Infrastructure", "Private Equity", "Other PE")))
    return alt / tot * 100


for c in OUT.values():
    if c.get("alloc"):
        c["alts_share"] = alts_share(c)


def med(vals):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def y25(c, k):
    return ((c.get("years") or {}).get("2025") or {}).get(k)


MED = {k: med(y25(c, k) for c in OUT.values() if c.get("status") in ("study", "built"))
       for k in ("buffer", "cap_ratio", "fin_pct", "reins_pct", "par_share", "surplus_pct")}
MED["alts_share"] = med(c.get("alts_share") for c in OUT.values() if c.get("status") in ("study", "built"))
MED["licat_series"] = LC["series"]
MED["licat_medians"] = LC["medians"]
MED["per100"] = LS["per100_med"]

try:
    commit = subprocess.run(["git", "-C", str(ALM), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
except Exception:
    commit = ""
doc = dict(meta=dict(source="MooseDragon/cdn-life-insurer-alm", commit=commit, anchor="fiscal year-end 2025 (Oct 31, 2025 for RBC Life and BMO Life; Dec 31, 2025 for the others)",
                     units="C$ millions unless stated"), companies=OUT, peer_median=MED)
(HERE / "alm.json").write_text(json.dumps(clean(doc), indent=1))
print("wrote", HERE / "alm.json", {k: v.get("status") for k, v in OUT.items()})
for cid, c in OUT.items():
    b = (c.get("years") or {}).get("2025")
    if b:
        print(f"{cid:18s} GenAcct {b['ga'] or 0:>10,.0f}  buffer {b['buffer'] if b['buffer'] is not None else float('nan'):6.1f}  "
              f"memo {b['buffer_memo'] if b['buffer_memo'] is not None else float('nan'):6.1f}  cap {b['cap_ratio'] or float('nan'):6.1f}  "
              f"fin {b['fin_pct'] if b['fin_pct'] is not None else float('nan'):5.1f}  reins {b['reins_pct'] if b['reins_pct'] is not None else float('nan'):6.1f}  "
              f"alts {c.get('alts_share') if c.get('alts_share') is not None else float('nan'):5.1f}")
print("medians", {k: (round(v, 1) if isinstance(v, float) else None) for k, v in MED.items() if k in ("buffer", "cap_ratio", "fin_pct", "reins_pct", "par_share", "alts_share")})
