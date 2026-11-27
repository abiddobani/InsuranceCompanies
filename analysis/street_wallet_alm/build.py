#!/usr/bin/env python3
"""Street wallet by insurer, rebuilt on the cdn-life-insurer-alm framework.

    uv run --project <alm repo> python analysis/street_wallet_alm/build.py --alm <alm repo>

What the street earns each year from executing each insurer's Canadian general-account
business: traded volume x one-way friction cost, plus repo and derivative costs.

The ALM repo (MooseDragon/cdn-life-insurer-alm) supplies the scope and the data:
  scope     Canadian business only; General Account excl. par / seg fund, with the par block and
            universal life policyholder funds shown separately; seg fund assets left out
            (docs/METHODOLOGY.md sections 1-4a; README standing rules).
  holdings  data/processed/deck2_block_allocation_2025fye.csv (asset allocation by block and
            taxonomy level 3, fiscal 2025 year-ends), peer_summary_2025q4.csv (iA, Beneva,
            Desjardins; repos), osfi_long.parquet LF2 P21012 (class detail, yearly changes).
  drivers   deck2_maturity_bands.csv (bonds maturing within a year; duration proxy),
            icl_by_line_2025q4.csv (liability mix, used to pick turnover proxies the way
            research/synthetic_rbc_benchmark.md picks pure-play peers), LF3 P21110 (derivative
            notionals), LF3 P2203028001 (repos), cash flow statements in data/raw (BMO Life, ivari).

Where the repo is silent the October method fills in (inputs/): group cash flow statement ratios
for the Big 3, iA, Beneva and Assumption, derivative notes for iA and Beneva, holdings for the
insurers outside OSFI and outside the repo, and the friction-cost schedule.

Every figure is an estimate. Units: C$ millions unless stated.
"""
import argparse
import csv
import os
import statistics
from collections import defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
INP = os.path.join(HERE, "inputs")
SHARE = "/mnt/project-files/street-wallet/"

# ---------------------------------------------------------------------------- assumptions
ST_ROLLS = 3.0            # short-term paper in investing cash flows rolls 3 times a year
MM_BPS = 0.5              # one-way cost per roll, bps of principal
CAP = 1.0                 # gross flows above 100% of invested assets are money-market rolls (October rule)
MORTGAGE_MATURITY = 0.10  # where no maturity table
UL_FUND_TURNOVER = None   # set from ivari's fund flows
UL_FUND_BPS = 5.0         # exchange-traded and pooled fund units, one-way
REPO_MARGIN_BPS = 3.0     # dealer margin on repo funding, bps a year on the balance
# Bonds: half bid-offer in yield (bp) x duration of the insurer's bond book = one-way cost in price.
HALF_SPREAD_YIELD_BP = {"fed": 0.25, "prov": 0.5, "muni": 0.75, "corp_ig": 1.25, "abs": 1.0}
FLAT_BPS = {"corp_hy": 35.0, "common": 10.0, "pref": 25.0}
# Relative weight of each public class in the active (switch and rebalancing) volume. October weights.
ACTIVE_WEIGHT = {"fed": 1.5, "prov": 1.5, "muni": 1.5, "corp_ig": 1.0, "corp_hy": 1.0, "abs": 1.0, "common": 1.0, "pref": 0.5}
PUBLIC = list(ACTIVE_WEIGHT)
PRIVATE = ["priv", "mortgages", "real_estate", "other"]
BOND_CLASSES = ["fed", "prov", "muni", "corp_ig", "corp_hy", "abs", "priv"]
BUCKET = {"fed": "Rates", "prov": "Rates", "muni": "Rates", "st": "Rates", "corp_ig": "Corporate bonds", "corp_hy": "Corporate bonds",
          "abs": "Corporate bonds", "common": "Equities", "pref": "Equities", "ul": "Equities"}
BUCKETS = ["Rates", "Corporate bonds", "Equities", "FX", "Rates & credit derivatives", "Equity derivatives", "Repo funding"]
RANGE = {"Rates": (0.5, 1.7), "Corporate bonds": (0.67, 1.67), "Equities": (0.6, 1.5), "FX": (0.5, 2.0),
         "Rates & credit derivatives": (0.5, 2.0), "Equity derivatives": (0.5, 2.0), "Repo funding": (0.5, 2.0)}
YIELD = 0.045  # for the maturity-to-duration conversion

# Derivatives (October schedule): traded notional a year per unit outstanding and one-way cost in
# bps, by remaining term (<1y, 1-5y, >5y).
SWAP_TURN = (1.1, 1 / 3 + 0.1, 0.2)
DERIVATIVES = {
    "ir_swaps": ("Interest rate swaps", SWAP_TURN, (0.125, 0.75, 3.0), "Rates & credit derivatives"),
    "ir_forwards": ("Bond forwards and FRAs", (4, 4, 4), (1.0, 1.0, 1.0), "Rates & credit derivatives"),
    "ir_futures": ("Interest rate and bond futures", (4, 4, 4), (0.25, 0.25, 0.25), "Rates & credit derivatives"),
    "ir_options": ("Interest rate options and swaptions", (1, 1 / 3, 0.1), (5.0, 5.0, 5.0), "Rates & credit derivatives"),
    "credit": ("Credit default swaps", (2, 2, 2), (2.0, 2.0, 2.0), "Rates & credit derivatives"),
    "fx_forwards": ("FX spot and forwards", (4, 4, 4), (1.5, 1.5, 1.5), "FX"),
    "fx_futures": ("FX futures", (4, 4, 4), (0.5, 0.5, 0.5), "FX"),
    "fx_swaps": ("FX and cross-currency swaps", SWAP_TURN, (2.0, 5.0, 10.0), "FX"),
    "fx_options": ("FX options", (1, 1 / 3, 0.1), (10.0, 10.0, 10.0), "FX"),
    "equity_futures": ("Equity index futures", (4, 4, 4), (0.5, 0.5, 0.5), "Equity derivatives"),
    "equity_options": ("Equity options", (1, 1 / 3, 0.1), (10.0, 10.0, 10.0), "Equity derivatives"),
    "equity_swaps": ("Equity swaps", (1, 1 / 3, 0.1), (5.0, 5.0, 5.0), "Equity derivatives"),
    "equity_otc": ("Equity-related contracts (OSFI, type not split)", (1, 1 / 3, 0.1), (8.0, 8.0, 8.0), "Equity derivatives"),
    "commodities_other": ("Commodity and other contracts", (1, 1 / 3, 0.1), (5.0, 5.0, 5.0), "Rates & credit derivatives"),
}
LF3_ROWS = {"010": "ir_forwards", "020": "ir_futures", "030": "ir_swaps", "040": "ir_options", "050": "ir_options",
            "210": "fx_forwards", "220": "fx_futures", "230": "fx_swaps", "240": "fx_options",
            "310": "equity_otc", "325": "credit", "330": "commodities_other"}
SHORT_DATED = {"ir_forwards", "ir_futures", "fx_forwards", "fx_futures", "equity_futures", "ir_options", "fx_options",
               "equity_options", "equity_otc", "credit", "commodities_other"}

# ---------------------------------------------------------------------------- peers
# key: (ALM repo short id, name, on Abid's list of 20, OSFI id, basis, gross-flow source)
PEERS = {
    "rbc_life": ("RBC", "RBC Life", 1, "28395", "block", None),
    "manulife": ("MFC", "Manulife (Canada)", 1, "28397", "block", "october"),
    "sun_life": ("SLF", "Sun Life (Canada)", 1, "28429", "block", "october"),
    "canada_life": ("CLF", "Canada Life (Canada)", 1, "28386", "block", "october"),
    "ia": ("IAG", "iA Financial Group", 1, None, "repo_fs", "october"),
    "desjardins": ("DFS", "Desjardins Insurance", 1, None, "liabilities", None),
    "bmo_life": ("BMO", "BMO Life", 1, "28350", "block", "added"),
    "beneva": ("BEN", "Beneva", 1, None, "repo_fs", "october"),
    "ivari": ("IVA", "ivari", 1, "28414", "block", "added"),
    "empire_life": ("EMP", "Empire Life", 1, "28375", "block", "october"),
    "equitable_life": ("EQL", "Equitable Life", 1, "28377", "block", "october"),
    "cooperators_life": ("COP", "Co-operators Life", 1, "28368", "block", None),
    "uv_insurance": ("UV", "UV Insurance", 1, None, "october", None),
    "wawanesa_life": ("WAW", "Wawanesa Life", 1, "28434", "block", "october"),
    "assumption_life": ("ASL", "Assumption Life", 1, None, "october", "october"),
    "foresters_life": ("IOF", "Foresters Life (incl. Canada Protection Plan)", 1, "28432", "block", "october"),
    "canadian_premier": ("CPL", "Canadian Premier Life", 1, "28358", "lf2", None),
    "primerica_life": ("PRI", "Primerica Life", 1, "28419", "lf2", None),
    "humania": ("HUM", "Humania", 1, None, "october", None),
    "blumont": ("BLU", "Blumont Annuity (memo, not on the list of 20)", 0, "143611", "block", None),
}
FOCUS = "rbc_life"
OCT_YE = {"rbc_life", "bmo_life"}
# Short-term paper (over three months at purchase) sits inside the purchases and sales lines of
# these insurers' cash flow statements, so its rolls are taken out before the residual. Manulife
# reconciles its cash flows to cash and short-term securities, Lifeco's maturity table already
# carries short-term bonds, ivari's bond line excludes them, and the others hold almost none.
ST_STRIP = {"sun_life", "bmo_life", "foresters_life"}
BIG3 = {"manulife", "sun_life", "canada_life"}
LINES = {"Individual insurance": "ind", "Individual annuity": "ann", "Group annuity": "ann", "Group insurance": "grp", "Participating": "par"}


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def dur(t):
    """Modified duration of a par bond of maturity t at YIELD."""
    return (1 - (1 + YIELD) ** -t) / YIELD / (1 + YIELD) if t > 0 else 0.0


# ---------------------------------------------------------------------------- ALM repo data
class Alm:
    def __init__(self, root):
        self.root = root
        p = os.path.join(root, "data", "processed")
        o = pd.read_parquet(os.path.join(p, "osfi_long.parquet"), columns=["id", "per", "dpa", "value_num"])
        self.osfi = o[o.dpa.str.startswith(("P21012", "P21110", "P22030"))].copy()
        self.block = pd.read_csv(os.path.join(p, "deck2_block_allocation_2025fye.csv"))
        self.bands = pd.read_csv(os.path.join(p, "deck2_maturity_bands.csv"))
        self.summary = {y: pd.read_csv(os.path.join(p, f"peer_summary_{y}q4.csv")).set_index("short_id") for y in (2024, 2025)}
        self.icl = pd.read_csv(os.path.join(p, "icl_by_line_2025q4.csv"))
        self.filings = pd.read_csv(os.path.join(p, "filings_all_long.csv"), low_memory=False)
        self._lf2 = {}

    def lf2(self, oid, per):
        """Holdings by class at a period end (entity, balance sheet value less index-linked), C$ mm."""
        if (oid, per) in self._lf2:
            return self._lf2[(oid, per)]
        x = self.osfi[(self.osfi.id == oid) & (self.osfi.per == per) & self.osfi.dpa.str.startswith("P21012")]
        if x.empty:
            self._lf2[(oid, per)] = None
            return None
        v = {d[6:11]: n / 1000 for d, n in zip(x.dpa, x.value_num)}
        g = lambda row, col="40": v.get(row + col, 0.0)
        h = {"st": g("010"), "fed": g("045") + g("050"), "prov": g("055") + g("065"), "muni": g("140") + g("160"),
             "corp_ig": g("210"), "corp_hy": g("230"), "priv": g("410") + g("430"), "mortgages": g("500"),
             "pref": g("599"), "common": g("659"), "other": g("810") + g("820"), "abs": 0.0, "real_estate": 0.0}
        h["total_investments"] = g("889")
        # index-linked (universal life policyholder fund) assets come out of bonds and shares
        il_bonds, il_shares, il_total = g("479", "70"), g("679", "70"), g("889", "70")
        bonds = sum(h[k] for k in ("fed", "prov", "muni", "corp_ig", "corp_hy", "priv"))
        if bonds and il_bonds:
            for k in ("fed", "prov", "muni", "corp_ig", "corp_hy", "priv"):
                h[k] *= max(1 - il_bonds / bonds, 0)
        take = min(il_shares, h["common"])
        h["common"] -= take
        h["pref"] = max(h["pref"] - (il_shares - take), 0)
        h["ul"] = il_total
        h["ga"] = sum(h[k] for k in ["st"] + PUBLIC + PRIVATE)
        self._lf2[(oid, per)] = h
        return h

    def block_holdings(self, short, oid):
        """Canadian holdings by block and class at the fiscal 2025 year-end (repo block allocation)."""
        b = self.block[self.block.peer == short]
        e = self.lf2(oid, "2025Q4")
        gov = {k: e[k] for k in ("fed", "prov", "muni")}
        gs = sum(gov.values()) or 1
        corp = {k: e[k] for k in ("corp_ig", "corp_hy")}
        cs = sum(corp.values()) or 1
        out = {}
        for blk, col in (("nonpar", "nonpar_seg_ga_k"), ("par", "par_k"), ("ul", "ul_ph_fund_k")):
            h = defaultdict(float)
            for l3, a in zip(b.l3, b[col]):
                a = a / 1000
                if l3 == "Government Bonds":
                    for k in gov:
                        h[k] += a * gov[k] / gs
                elif l3 == "Corporate Bonds":
                    for k in corp:
                        h[k] += a * corp[k] / cs
                else:
                    h[{"Cash Equivalent": "st", "Commercial Mortgages": "mortgages", "Illiquid Term Loan": "priv", "Common Shares": "common",
                       "Preferred Shares": "pref", "Real Estate Equity": "real_estate"}.get(l3, "other")] += a
            out[blk] = dict(h)
        return out

    def maturity(self, short):
        """(share of bonds maturing within a year, share of mortgages, bond duration proxy) or None."""
        b = self.bands[(self.bands.peer == short) & (self.bands.band != "Total")].copy()
        if b.empty:
            return None
        t = b.asset_type.str.lower()
        is_total_row = t.str.contains("all issuers|total")
        bond = b[(t.str.contains("bond|debt securities|fixed income")) & ~is_total_row & ~t.str.contains("mortgage")]
        if short == "SLF":
            bond = b[t == "debt securities"]
            bond = bond[bond.accounting_class.str.lower().str.contains("total") | (bond.accounting_class.nunique() == 1)] if bond.accounting_class.str.lower().str.contains("total").any() else bond
        mort = b[t.str.contains("mortgage") & ~t.str.contains("total|asset-backed")]
        if short == "SLF" and mort.accounting_class.str.lower().str.contains("total").any():
            mort = mort[mort.accounting_class.str.lower().str.contains("total")]

        def stats(x):
            x = x[x.band_start_yr.notna()]
            tot = x.value_mm.sum()
            if not tot:
                return None, None
            lt1 = x[x.band_end_yr <= 1].value_mm.sum() / tot
            d = 0.0
            for s, e, v in zip(x.band_start_yr, x.band_end_yr, x.value_mm):
                mid = (s + e) / 2 if pd.notna(e) else (20.0 if s >= 10 else 15.0 if s >= 5 else s + 5)
                d += dur(mid) * v
            return lt1, d / tot
        m_b, d_b = stats(bond)
        m_m, _ = stats(mort)
        return m_b, m_m, d_b

    def liability_mix(self, short):
        x = self.icl[self.icl.entity == short]
        mix = defaultdict(float)
        for line, v in zip(x.product_line, x.net_k):
            if line in LINES and v > 0:
                mix[LINES[line]] += v
        s = sum(mix.values())
        return {k: v / s for k, v in mix.items()} if s else None

    def derivatives(self, oid):
        """Average over the filed years of (cost, traded notional, notional) / entity investments, by contract."""
        out = defaultdict(list)
        years = []
        for per in ("2023Q4", "2024Q4", "2025Q4"):
            x = self.osfi[(self.osfi.id == oid) & (self.osfi.per == per) & self.osfi.dpa.str.startswith("P21110")]
            h = self.lf2(oid, per)
            if x.empty or not h:
                continue
            years.append(per[:4])
            v = {d[6:11]: n / 1000 for d, n in zip(x.dpa, x.value_num)}
            agg = defaultdict(lambda: [0.0, 0.0, 0.0])
            for row, c in LF3_ROWS.items():
                tot = abs(v.get(row + "07", 0.0))
                if not tot:
                    continue
                b = [abs(v.get(row + k, 0.0)) for k in ("27", "32", "37")]
                b = [y * tot / sum(b) for y in b] if sum(b) else ([tot, 0, 0] if c in SHORT_DATED else [0, 0, tot])
                for i in range(3):
                    agg[c][i] += b[i]
            for c in DERIVATIVES:
                b = agg.get(c, [0, 0, 0])
                _, turn, bps, _ = DERIVATIVES[c]
                a = h["total_investments"]
                out[c].append((sum(b[i] * turn[i] * bps[i] for i in range(3)) / 1e4 / a, sum(b[i] * turn[i] for i in range(3)) / a, sum(b) / a))
        return {c: tuple(statistics.mean(x[i] for x in v) for i in range(3)) for c, v in out.items()}, years

    def repos(self, short):
        v = [num(self.summary[y].repos_k.get(short)) / 1000 for y in (2024, 2025) if short in self.summary[y].index]
        v = [x for x in v if x == x]
        return statistics.mean(v) if v else 0.0


# ---------------------------------------------------------------------------- turnover
def entity_changes(alm, key, oid):
    """Yearly |change| by class / average holdings, from LF2 year-ends; averages of the flow years."""
    years = [("2024Q4", "2025Q4")] if key in OCT_YE else [("2023Q4", "2024Q4"), ("2024Q4", "2025Q4")]
    rates, stshare = defaultdict(list), []
    for a, b in years:
        h0, h1 = alm.lf2(oid, a), alm.lf2(oid, b)
        if not h0 or not h1:
            continue
        for k in PUBLIC + PRIVATE:
            if k in ("common", "pref"):
                continue  # equity balances move with markets; left to the active rate
            avg = (h0[k] + h1[k]) / 2
            rates[k].append(min(abs(h1[k] - h0[k]) / avg, 1.0) if avg > 1 else 0.0)
        qs = [alm.lf2(oid, f"{b[:4]}Q{q}") for q in (1, 2, 3, 4)] + [h0]
        qs = [q for q in qs if q]
        stshare.append(statistics.mean(q["st"] for q in qs) / statistics.mean(q["ga"] for q in qs))
    return {k: statistics.mean(v) for k, v in rates.items()}, (statistics.mean(stshare) if stshare else 0.0)


def gross_flows(alm):
    """Average gross turnover (purchases + sales and maturities) / invested assets by insurer."""
    g = defaultdict(list)
    for r in read(os.path.join(INP, "october_wallet_by_year.csv")):
        if r["turnover_source"] == "disclosed":
            g[r["company_id"]].append((int(r["year"]), num(r["gross_turnover_pct"]) / 100))
    added = defaultdict(lambda: defaultdict(float))
    for r in read(os.path.join(INP, "added_flows.csv")):
        added[(r["company_id"], int(r["year"]))][r["asset"]] += (num(r["purchases_cad_mm"]) + num(r["sales_maturities_cad_mm"])) * 12 / num(r["months"])
    ul_rates = []
    for (cid, y), d in sorted(added.items()):
        oid = PEERS[cid][3]
        h0, h1 = alm.lf2(oid, f"{y - 1}Q4"), alm.lf2(oid, f"{y}Q4")
        ga = (h0["ga"] + h1["ga"]) / 2 if h0 else h1["ga"]
        ul = (h0["ul"] + h1["ul"]) / 2 if h0 else h1["ul"]
        if "funds" in d:  # ivari: fund units back universal life accounts; bonds are the general account
            ul_rates.append(d["funds"] / ul)
            g[cid].append((y, d["bonds"] / ga))
        else:
            g[cid].append((y, d["all"] / (ga + ul)))
    return {k: (statistics.mean(x[1] for x in v), f"{min(x[0] for x in v)}-{max(x[0] for x in v)}" if len(v) > 1 else str(v[0][0]), len(v)) for k, v in g.items()}, statistics.mean(ul_rates)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alm", default=os.environ.get("ALM_REPO", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "cdn-life-insurer-alm")))
    args = ap.parse_args()
    alm = Alm(args.alm)
    gflows, ul_rate = gross_flows(alm)
    october = {r["company_id"]: r for r in read(os.path.join(INP, "october_wallet_by_insurer.csv"))}
    other_deriv = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))
    for r in read(os.path.join(INP, "other_derivatives.csv")):
        o = other_deriv[r["company_id"]][(int(r["year"]), r["contract"])]
        for i, k in enumerate(("bucket_lt1_cad_mm", "bucket_1to5_cad_mm", "bucket_gt5_cad_mm")):
            o[i] += num(r[k])
    fallback = defaultdict(lambda: defaultdict(dict))
    for r in read(os.path.join(INP, "fallback_holdings.csv")):
        fallback[r["company_id"]][r["period"]][r["asset_class"]] = num(r["amount_cad_mm"])

    # ---- step 1: holdings on the repo's Canadian basis, structural drivers per insurer
    P = {}
    for key, (short, name, listed, oid, basis, gsrc) in PEERS.items():
        p = {"key": key, "short": short, "name": name, "listed": listed, "basis": basis}
        if basis == "block":
            p["blocks"] = alm.block_holdings(short, oid)
            p["scope"] = "Canada: non-par general account, par block and UL policyholder funds (ALM repo block allocation, fiscal 2025 year-end)"
        elif basis == "lf2":
            h = alm.lf2(oid, "2025Q4")
            p["blocks"] = {"nonpar": {k: h[k] for k in ["st"] + PUBLIC + PRIVATE}, "par": {}, "ul": {"common": h["ul"]}}
            p["scope"] = "Whole entity, all Canada (OSFI LF2 through the ALM repo panel; no block split built in the repo)"
        if oid:
            p["changes"], p["st_share"] = entity_changes(alm, key, oid)
            p["entity"] = alm.lf2(oid, "2025Q4")
            p["deriv"], p["deriv_years"] = alm.derivatives(oid)
        p["maturity"] = alm.maturity(short)
        p["liab"] = alm.liability_mix(short)
        p["repos"] = alm.repos(short)
        P[key] = p

    # split of bonds for insurers with one bond line: median of the non-Big-3 OSFI filers
    ref = [P[k]["entity"] for k in P if P[k].get("entity") and k not in BIG3 and k != "blumont"]
    bsplit = {}
    for k in ("fed", "prov", "muni", "corp_ig", "corp_hy", "priv"):
        bsplit[k] = statistics.median(e[k] / max(sum(e[c] for c in ("fed", "prov", "muni", "corp_ig", "corp_hy", "priv")), 1e-9) for e in ref)
    s = sum(bsplit.values())
    bsplit = {k: v / s for k, v in bsplit.items()}
    esplit = statistics.median(e["pref"] / (e["pref"] + e["common"]) for e in ref if e["pref"] + e["common"] > 1)

    def six_class(d, scale=1.0):
        h = {k: d.get("Bonds", 0) * v * scale for k, v in bsplit.items()}
        eq = d.get("Equities", 0) * scale
        h.update({"st": d.get("Cash & short-term", 0) * scale, "mortgages": d.get("Mortgages & loans", 0) * scale, "common": eq * (1 - esplit),
                  "pref": eq * esplit, "real_estate": d.get("Real estate", 0) * scale, "other": d.get("Other invested assets", 0) * scale, "abs": 0.0})
        return h

    for key in ("assumption_life", "humania", "uv_insurance"):
        P[key]["blocks"] = {"nonpar": six_class(fallback[key]["2025Q4"]), "par": {}, "ul": {}}
        P[key]["scope"] = "Whole company (October dataset: annual report balance sheet; not in the ALM repo or OSFI data)"
    # Beneva: repo General Account after the P&C and policyholder-linked carve-outs; mix from the October dataset
    ga = alm.summary[2025].genacct_k["BEN"] / 1000
    tot = sum(fallback["beneva"]["2025Q4"].values())
    P["beneva"]["blocks"] = {"nonpar": six_class(fallback["beneva"]["2025Q4"], ga / tot), "par": {}, "ul": {}}
    P["beneva"]["carve"] = ga / tot
    P["beneva"]["scope"] = "Life and health general account after the ALM repo's P&C and policyholder-linked carve-outs; class mix from the consolidated balance sheet"
    # iA: repo General Account after the US carve-out; level 3 mix from the repo filings panel
    f = alm.filings
    x = f[(f.company == "iA Financial Group") & (f.period == "FY2025") & (f.metric_group == "assets") & (f.bs_section == "On-BS") & (f.nesting == "leaf") & f.l3.notna()]
    l3 = x.groupby("l3").amount.sum()
    ga, tot = alm.summary[2025].genacct_k["IAG"] / 1000, l3.sum()
    gsum = bsplit["fed"] + bsplit["prov"] + bsplit["muni"]
    h = defaultdict(float)
    for name_, a in l3.items():
        a = a * ga / tot
        if name_ == "Government Bonds":
            for k in ("fed", "prov", "muni"):
                h[k] += a * bsplit[k] / gsum
        else:
            h[{"Cash Equivalent": "st", "Corporate Bonds": "corp_ig", "Asset Backed Securities": "abs", "Commercial Mortgages": "mortgages", "Illiquid Term Loan": "priv",
               "Common Shares": "common", "Preferred Shares": "pref", "Real Estate Equity": "real_estate"}.get(name_, "other")] += a
    P["ia"]["blocks"] = {"nonpar": dict(h), "par": {}, "ul": {}}
    P["ia"]["carve"] = ga / tot
    P["ia"]["scope"] = "General account after the ALM repo's US carve-out (par and UL not separable); level 3 mix from the repo filings panel"

    # ---- step 2: maturity and duration; proxies by liability mix where no maturity table is public
    with_bands = {k: P[k]["maturity"] for k in P if P[k]["maturity"] and P[k]["maturity"][0] is not None}
    med_m = statistics.median(v[0] for v in with_bands.values())
    med_d = statistics.median(v[2] for v in with_bands.values())
    for key, p in P.items():
        if key in with_bands:
            m, mm, d = with_bands[key]
            p["m_bond"], p["m_mort"], p["duration"], p["maturity_basis"] = m, (mm if mm is not None else MORTGAGE_MATURITY), d, "maturity table in the financial statements (ALM repo)"
        elif p.get("liab") and key != "blumont":
            w_iva = p["liab"].get("ind", 0)
            p["m_bond"] = w_iva * with_bands["ivari"][0] + (1 - w_iva) * with_bands["bmo_life"][0]
            p["duration"] = w_iva * with_bands["ivari"][2] + (1 - w_iva) * with_bands["bmo_life"][2]
            p["m_mort"], p["maturity_basis"] = MORTGAGE_MATURITY, "proxy by liability mix: ivari for individual insurance, BMO Life for the rest"
        elif key == "blumont":
            p["m_bond"], p["duration"], p["m_mort"], p["maturity_basis"] = with_bands["bmo_life"][0], with_bands["bmo_life"][2], MORTGAGE_MATURITY, "proxy: BMO Life (annuity-heavy)"
        else:
            p["m_bond"], p["duration"], p["m_mort"], p["maturity_basis"] = med_m, med_d, MORTGAGE_MATURITY, "median of insurers with a maturity table"

    # ---- step 3: active trading rate. Disclosers: residual of the cash flow statement. Others: proxy.
    def structural(p, h):
        """Per-class structural volume on holdings h: reinvested maturities plus net new money and rotation."""
        ch = p.get("changes") or {}
        v = {}
        for k in PUBLIC + PRIVATE:
            m = p["m_bond"] if k in BOND_CLASSES else p["m_mort"] if k == "mortgages" else 0.0
            v[k] = h.get(k, 0.0) * (m + ch.get(k, 0.0))
        return v

    def base_holdings(p):
        """Holdings the insurer's own turnover ratios are measured on (entity for OSFI filers)."""
        if p.get("entity") and p["key"] not in ("canadian_premier", "primerica_life"):
            return {k: p["entity"][k] for k in ["st"] + PUBLIC + PRIVATE}
        return p["blocks"]["nonpar"]

    for key, p in P.items():
        if key not in gflows or "blocks" not in p:
            continue
        g, yrs, n = gflows[key]
        h = base_holdings(p)
        A = sum(h.values())
        st = p.get("st_share", 0.0) * 2 * ST_ROLLS if key in ST_STRIP else 0.0
        mat = sum(h.get(k, 0) * p["m_bond"] for k in BOND_CLASSES) / A + h.get("mortgages", 0) * p["m_mort"] / A
        v = max(min(g - st, CAP) - mat, 0.0)
        sv = structural(p, h)
        v_priv = min(sum(sv[k] for k in PRIVATE) / A, v)
        s_pub = sum(sv[k] for k in PUBLIC) / A
        act = max(v - v_priv - s_pub, 0.0)
        hpub = sum(h.get(k, 0) for k in PUBLIC)
        p.update({"gross": g, "gross_years": yrs, "st_rolls": st, "mat": mat, "v": v, "v_priv": v_priv, "s_pub": min(s_pub, v - v_priv),
                  "act": act, "a": act * A / hpub if hpub else 0.0, "struct_scale": min((v - v_priv) / s_pub, 1.0) if s_pub else 1.0,
                  "turnover_basis": f"cash flow statement, {yrs}" + (" (group ratio)" if key in BIG3 else "")})

    a_obs = {k: P[k]["a"] for k in P if "a" in P[k]}
    a_med = statistics.median(a_obs.values())
    q = statistics.quantiles(sorted(a_obs.values()), n=4)
    a_lo, a_hi = q[0], q[2]
    # annuity rate implied by BMO Life (individual insurance at ivari's rate, the rest annuities)
    wb = P["bmo_life"]["liab"]
    a_ann = max((a_obs["bmo_life"] - wb.get("ind", 0) * a_obs["ivari"]) / max(1 - wb.get("ind", 0), 1e-9), 0.0)
    line_rate = {"ind": a_obs["ivari"], "ann": a_ann, "par": a_obs["equitable_life"], "grp": a_med}
    for key, p in P.items():
        if "a" in p or "blocks" not in p:
            continue
        if p.get("liab"):
            p["a"] = sum(w * line_rate[k] for k, w in p["liab"].items())
            p["a_lo"], p["a_hi"] = 0.5 * p["a"], 2.0 * p["a"]
            p["turnover_basis"] = "no cash flow statement: own maturities and balance changes, active rate by liability mix (ivari individual insurance, BMO-implied annuities, Equitable par)"
        else:
            p["a"], p["a_lo"], p["a_hi"] = a_med, a_lo, a_hi
            p["turnover_basis"] = "no cash flow statement: active rate at the median of disclosing insurers"
        p["struct_scale"] = 1.0

    # ---- step 4: wallet
    def cost_bps(p, k):
        if k in HALF_SPREAD_YIELD_BP:
            return HALF_SPREAD_YIELD_BP[k] * p["duration"]
        return FLAT_BPS.get(k, 0.0)

    def securities(p, blocks, a):
        """Traded volume and cost by block and class."""
        rows = []
        for blk, h in blocks.items():
            if not h:
                continue
            if blk == "ul":
                tot = sum(h.values())
                rows.append((blk, "ul", tot, tot * ul_rate, 0, 0, tot * ul_rate, tot * ul_rate * UL_FUND_BPS / 1e4))
                continue
            sv = structural(p, h)
            hpub, wsum = sum(h.get(k, 0) for k in PUBLIC), sum(h.get(k, 0) * ACTIVE_WEIGHT[k] for k in PUBLIC)
            for k in PUBLIC + PRIVATE:
                hk = h.get(k, 0.0)
                if not hk:
                    continue
                m = p["m_bond"] if k in BOND_CLASSES else p["m_mort"] if k == "mortgages" else 0.0
                reinv = hk * m * p["struct_scale"]
                newm = (sv[k] - hk * m) * p["struct_scale"]
                active = a * hpub * hk * ACTIVE_WEIGHT[k] / wsum if k in PUBLIC and wsum else 0.0
                vol = reinv + newm + active
                rows.append((blk, k, hk, reinv, newm, active, vol, vol * cost_bps(p, k) / 1e4 if k in PUBLIC else 0.0))
            if h.get("st"):
                roll = h["st"] * ST_ROLLS
                rows.append((blk, "st", h["st"], roll, 0, 0, roll, roll * MM_BPS / 1e4))
        return rows

    def derivative_costs(p, base):
        out = defaultdict(float)
        traded = 0.0
        if p.get("deriv"):
            for c, (cost, tr, _) in p["deriv"].items():
                out[DERIVATIVES[c][3]] += cost * base
                traded += tr * base
        elif p["key"] in other_deriv:
            per_year = defaultdict(lambda: defaultdict(float))
            tr_year = defaultdict(float)
            for (y, c), b in other_deriv[p["key"]].items():
                _, turn, bps, bucket = DERIVATIVES[c]
                per_year[y][bucket] += sum(b[i] * turn[i] * bps[i] for i in range(3)) / 1e4
                tr_year[y] += sum(b[i] * turn[i] for i in range(3))
            for b in BUCKETS:
                out[b] = statistics.mean(per_year[y].get(b, 0.0) for y in per_year) * p.get("carve", 1.0)
            traded = statistics.mean(tr_year.values()) * p.get("carve", 1.0)
        return out, traded

    insurers, drivers, by_block, detail = [], [], [], []
    for key, p in P.items():
        if "blocks" not in p:
            continue
        base = sum(sum(h.values()) for h in p["blocks"].values())
        ent_total = p["entity"]["total_investments"] if p.get("entity") else None
        canada_share = base / ent_total if key in BIG3 else 1.0

        def run(a):
            rows = securities(p, p["blocks"], a)
            costs = defaultdict(float)
            for blk, k, hk, reinv, newm, active, vol, cost in rows:
                if cost:
                    costs[BUCKET[k]] += cost
            dc, dtr = derivative_costs(p, (ent_total * canada_share) if p.get("deriv") else base)
            for b, v in dc.items():
                costs[b] += v
            costs["Repo funding"] += p["repos"] * REPO_MARGIN_BPS / 1e4
            return rows, costs, dtr
        rows, costs, dtr = run(p["a"])
        total = sum(costs.values())
        lo = sum(v * RANGE[b][0] for b, v in run(p.get("a_lo", p["a"]))[1].items())
        hi = sum(v * RANGE[b][1] for b, v in run(p.get("a_hi", p["a"]))[1].items())
        street = [r for r in rows if r[1] in PUBLIC]
        vol = sum(r[6] for r in street)
        memo = ""
        if key in BIG3:  # same rates on the whole legal entity (foreign business included), derivatives unscaled
            e = p["entity"]
            erows = securities(p, {"nonpar": {k: e[k] for k in ["st"] + PUBLIC + PRIVATE}, "ul": {"common": e["ul"]}}, p["a"])
            memo = round(sum(r[7] for r in erows) + sum(derivative_costs(p, ent_total)[0].values()) + p["repos"] * REPO_MARGIN_BPS / 1e4, 1)
        o = october.get(key)
        blk_tot = {b: sum(sum(h.values()) for bb, h in p["blocks"].items() if bb == b) for b in ("nonpar", "par", "ul")}
        hpub = sum(r[2] for r in street)
        ins = {"company_id": key, "alm_short_id": p["short"], "company": p["name"], "focus": int(key == FOCUS), "on_list_of_20": p["listed"],
               "scope": p["scope"], "canadian_general_account_cad_mm": round(base, 0), "nonpar_general_account_cad_mm": round(blk_tot["nonpar"], 0),
               "par_block_cad_mm": round(blk_tot["par"], 0), "ul_policyholder_funds_cad_mm": round(blk_tot["ul"], 0),
               "gross_turnover_pct": round(100 * p["gross"], 1) if "gross" in p else "", "turnover_basis": p["turnover_basis"],
               "bonds_maturing_within_1y_pct": round(100 * p["m_bond"], 1), "bond_duration_proxy_yrs": round(p["duration"], 1), "maturity_basis": p["maturity_basis"],
               "active_rate_pct_of_public_holdings": round(100 * p["a"], 1), "public_securities_cad_mm": round(hpub, 0),
               "traded_public_securities_cad_mm": round(vol, 0), "traded_pct_of_public_holdings": round(100 * vol / hpub, 1) if hpub else "",
               "traded_derivatives_notional_cad_mm": round(dtr, 0), "avg_repo_balance_cad_mm": round(p["repos"], 0)}
        for b in BUCKETS:
            ins[f"cost_{b}"] = round(costs[b], 2)
        ins.update({"cost_total_cad_mm": round(total, 2), "cost_low_cad_mm": round(lo, 2), "cost_high_cad_mm": round(hi, 2),
                    "cost_bps_of_canadian_general_account": round(1e4 * total / base, 2),
                    "october_cost_cad_mm": o["cost_total_cad_mm"] if o else "", "october_bps": o["cost_bps_of_assets"] if o else "",
                    "october_assets_cad_mm": o["avg_invested_assets_cad_mm"] if o else "",
                    "memo_whole_entity_cost_cad_mm": memo, "memo_entity_investments_cad_mm": round(ent_total, 0) if key in BIG3 else "",
                    "change_vs_october_cad_mm": round(total - num(o["cost_total_cad_mm"]), 2) if o else ""})
        insurers.append(ins)
        # drivers
        d = {"Reinvesting maturities": sum(r[3] * cost_bps(p, r[1]) / 1e4 for r in street),
             "New money and rotation": sum(r[4] * cost_bps(p, r[1]) / 1e4 for r in street),
             "Active trading and ALM rebalancing": sum(r[5] * cost_bps(p, r[1]) / 1e4 for r in street),
             "Money market rolls": sum(r[7] for r in rows if r[1] == "st"),
             "UL policyholder fund flows": sum(r[7] for r in rows if r[1] == "ul"),
             "Repo funding": costs["Repo funding"],
             "Rate hedging (derivatives)": sum(v for b, v in derivative_costs(p, (ent_total * canada_share) if p.get("deriv") else base)[0].items() if b == "Rates & credit derivatives"),
             "FX hedging (derivatives)": sum(v for b, v in derivative_costs(p, (ent_total * canada_share) if p.get("deriv") else base)[0].items() if b == "FX"),
             "Equity hedging (derivatives)": sum(v for b, v in derivative_costs(p, (ent_total * canada_share) if p.get("deriv") else base)[0].items() if b == "Equity derivatives")}
        for name_, v in d.items():
            drivers.append({"company_id": key, "company": p["name"], "driver": name_, "cost_cad_mm": round(v, 3), "share_pct": round(100 * v / total, 1) if total else 0})
        for b in ("nonpar", "par", "ul"):
            c = sum(r[7] for r in rows if r[0] == b)
            if blk_tot[b]:
                by_block.append({"company_id": key, "company": p["name"], "block": {"nonpar": "General Account, excl. par / seg fund", "par": "Par block", "ul": "UL policyholder funds"}[b],
                                 "assets_cad_mm": round(blk_tot[b], 0), "securities_cost_cad_mm": round(c, 3), "bps_of_block": round(1e4 * c / blk_tot[b], 2)})
        for blk, k, hk, reinv, newm, active, v_, cost in rows:
            detail.append({"company_id": key, "block": blk, "class": k, "holdings_cad_mm": round(hk, 1), "reinvested_maturities_cad_mm": round(reinv, 1),
                           "new_money_rotation_cad_mm": round(newm, 1), "active_cad_mm": round(active, 1), "traded_cad_mm": round(v_, 1),
                           "one_way_cost_bps": round(cost_bps(p, k), 2) if k in PUBLIC else (MM_BPS if k == "st" else UL_FUND_BPS if k == "ul" else 0), "cost_cad_mm": round(cost, 3)})
        p["total"], p["base"] = total, base

    # Desjardins: liabilities only in the repo; wallet at the average rate of the two other Quebec groups
    dfs = alm.summary[2025].loc["DFS"]
    base = (dfs.fcf_k + dfs.csm_genacct_k) / 1000
    qc = [x for x in insurers if x["company_id"] in ("ia", "beneva")]
    allb = sorted(x["cost_bps_of_canadian_general_account"] for x in insurers if x["on_list_of_20"])
    bps = statistics.median(allb)
    ins = {k: "" for k in insurers[0]}
    ins.update({"company_id": "desjardins", "alm_short_id": "DFS", "company": "Desjardins Insurance", "focus": 0, "on_list_of_20": 1,
                "scope": "Liability-side view only in the ALM repo (no public balance sheet): life and health insurance contract liabilities incl. CSM as the asset base",
                "canadian_general_account_cad_mm": round(base, 0), "nonpar_general_account_cad_mm": round(base, 0),
                "turnover_basis": "not estimable: priced at the median bps of the other insurers; high case at the average of iA and Beneva", "maturity_basis": "n/a",
                "cost_total_cad_mm": round(base * bps / 1e4, 2), "cost_low_cad_mm": round(base * statistics.quantiles(allb, n=4)[0] / 1e4, 2),
                "cost_high_cad_mm": round(base * statistics.mean(x["cost_bps_of_canadian_general_account"] for x in qc) / 1e4, 2),
                "cost_bps_of_canadian_general_account": round(bps, 2)})
    insurers.append(ins)
    insurers.sort(key=lambda r: (-r["on_list_of_20"], -num(r["canadian_general_account_cad_mm"])))

    calib = []
    for key, p in P.items():
        if "gross" in p:
            calib.append({"company_id": key, "company": p["name"], "years": p["gross_years"], "gross_flows_pct_of_assets": round(100 * p["gross"], 1),
                          "short_term_rolls_pct": round(100 * p["st_rolls"], 1), "maturities_pct": round(100 * p["mat"], 1),
                          "traded_pct": round(100 * p["v"], 1), "private_originations_pct": round(100 * p["v_priv"], 1),
                          "public_structural_pct": round(100 * p["s_pub"], 1), "active_pct_of_assets": round(100 * p["act"], 1),
                          "active_pct_of_public_holdings": round(100 * p["a"], 1)})
    assumptions = [
        {"item": "Government of Canada bonds", "value": f"{HALF_SPREAD_YIELD_BP['fed']} bp of yield x bond duration", "source": "market convention; duration from the ALM repo maturity bands"},
        {"item": "Provincial bonds", "value": f"{HALF_SPREAD_YIELD_BP['prov']} bp of yield x duration", "source": "as above"},
        {"item": "Municipal bonds", "value": f"{HALF_SPREAD_YIELD_BP['muni']} bp of yield x duration", "source": "as above"},
        {"item": "Investment-grade public corporate bonds", "value": f"{HALF_SPREAD_YIELD_BP['corp_ig']} bp of yield x duration", "source": "as above"},
        {"item": "Asset-backed securities", "value": f"{HALF_SPREAD_YIELD_BP['abs']} bp of yield x duration", "source": "as above"},
        {"item": "Below-investment-grade public bonds", "value": "35 bps of price", "source": "October schedule"},
        {"item": "Common shares", "value": "10 bps", "source": "October schedule"},
        {"item": "Preferred shares", "value": "25 bps", "source": "October schedule"},
        {"item": "UL policyholder fund units", "value": f"{UL_FUND_BPS:g} bps; turnover {100 * ul_rate:.1f}% a year", "source": "turnover: ivari cash flow statement, fund purchases and sales / UL funds (ALM repo raw file)"},
        {"item": "Money market", "value": f"{MM_BPS} bps a roll, {ST_ROLLS:g} rolls a year", "source": "October schedule; roll count assumed"},
        {"item": "Private placements, mortgages, real estate, funds", "value": "0 (not street)", "source": "October schedule"},
        {"item": "Repo funding", "value": f"{REPO_MARGIN_BPS:g} bps a year on the average balance", "source": "assumed dealer margin; balances from OSFI LF3 P2203028001 and the ALM repo peer summary"},
        {"item": "Active rate: individual insurance", "value": f"{100 * line_rate['ind']:.1f}% of public holdings", "source": "ivari cash flow statement residual"},
        {"item": "Active rate: annuities (PRT, payout)", "value": f"{100 * line_rate['ann']:.1f}%", "source": "implied by BMO Life's residual after its individual insurance share at ivari's rate"},
        {"item": "Active rate: par", "value": f"{100 * line_rate['par']:.1f}%", "source": "Equitable Life cash flow statement residual"},
        {"item": "Active rate: group insurance and insurers with no line data", "value": f"{100 * a_med:.1f}% (quartiles {100 * a_lo:.1f}% to {100 * a_hi:.1f}%)", "source": "median of disclosing insurers"},
        {"item": "Bonds maturing within a year, no maturity table", "value": "liability-mix proxy (ivari, BMO Life) or peer median", "source": "ALM repo maturity bands"},
        {"item": "Low and high cases", "value": "; ".join(f"{b} x{RANGE[b][0]:g} to x{RANGE[b][1]:g}" for b in BUCKETS), "source": "October ranges; insurers proxied by liability mix also flex the active rate from half to double, and insurers at the discloser median flex it over the discloser quartiles"},
    ]
    for k, (label, turn, bps, bucket) in DERIVATIVES.items():
        assumptions.append({"item": label, "value": "cost bps <1y/1-5y/>5y " + "/".join(f"{b:g}" for b in bps) + "; traded a year per unit " + "/".join(f"{t:.2f}" for t in turn),
                            "source": "October schedule; notionals OSFI LF3 P21110 (Big 3 scaled to the Canadian share of entity investments), iA and Beneva notes"})

    outs = (("wallet_by_insurer.csv", insurers), ("wallet_by_driver.csv", drivers), ("wallet_by_block.csv", by_block),
            ("wallet_detail.csv", detail), ("turnover_calibration.csv", calib), ("assumptions.csv", assumptions))
    for d in [HERE] + ([os.path.join(SHARE, "alm-rebuild")] if os.path.isdir(SHARE) else []):
        os.makedirs(d, exist_ok=True)
        for name_, rows in outs:
            with open(os.path.join(d, name_), "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)

    print(f"UL fund turnover {100 * ul_rate:.1f}%; active rates: ind {100 * line_rate['ind']:.1f}% ann {100 * line_rate['ann']:.1f}% par {100 * line_rate['par']:.1f}% median {100 * a_med:.1f}% ({100 * a_lo:.1f}-{100 * a_hi:.1f})")
    for c in calib:
        print("  calib", c)
    for r in insurers:
        print(f"{r['company'][:34]:34s} base {num(r['canadian_general_account_cad_mm']) / 1000:6.1f}bn  a {str(r['active_rate_pct_of_public_holdings']):>5}%  D {str(r['bond_duration_proxy_yrs']):>4}  "
              f"wallet {num(r['cost_total_cad_mm']):7.2f} ({num(r['cost_low_cad_mm']):.1f}-{num(r['cost_high_cad_mm']):.1f})  {num(r['cost_bps_of_canadian_general_account']):5.2f}bps  Oct {r['october_cost_cad_mm']} / {r['october_bps']}  "
              + " ".join(f"{b[:5]}={num(r.get('cost_' + b)):.1f}" for b in BUCKETS))
    tot = sum(num(r["cost_total_cad_mm"]) for r in insurers if r["on_list_of_20"])
    b = sum(num(r["canadian_general_account_cad_mm"]) for r in insurers if r["on_list_of_20"])
    print(f"list of 20: C${tot:.0f}mm on C${b / 1000:.0f}bn = {1e4 * tot / b:.2f} bps")


if __name__ == "__main__":
    main()
