#!/usr/bin/env python3
"""Estimate what each peer pays the street each year to execute its general-account trading.

    python3 analysis/street_wallet/build.py

For each insurer and year 2021-2025 the estimate is traded notional x a market-standard one-way
friction cost (half bid/offer plus commission), by product:

  Cash securities   traded volume = gross investment flows (purchases + sales, maturities and
                    repayments, from the cash flow statement where published, as a ratio to
                    invested assets) less maturities and repayments, which cost nothing. Volume
                    above 100% of invested assets is treated as money-market rolls. Insurers
                    that publish no cash flow statement get the median ratio of those that do.
                    The volume is spread over classes by holdings x a relative trading weight.
  Money market      cash and short-term holdings rolled six times a year.
  Derivatives       year-end notionals by contract and remaining term (OSFI LF3 page P21110 for
                    OSFI filers, financial statement notes for iA and Beneva), turned into
                    traded notional with roll frequencies and priced per contract.

Holdings come from analysis/portfolio_reallocation (mix_history.csv, detail_ifrs17.csv,
bond_quality.csv). Outputs: wallet_by_insurer.csv (5-year average), wallet_by_year.csv,
assumptions.csv, written here and to /mnt/project-files/street-wallet/ when that folder exists.
"""
import csv
import gzip
import os
import statistics
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MIX = os.path.join(ROOT, "analysis", "portfolio_reallocation")
LF3 = os.path.join(ROOT, "data", "osfi", "LF3_core.csv.gz")
SHARE = "/mnt/project-files/street-wallet/"
YEARS = [2021, 2022, 2023, 2024, 2025]
FOCUS = "rbc_life"

# Cash securities: relative trading weight (how actively a dollar of holdings trades) and
# one-way cost in bps of traded principal.
SECURITIES = {
    "govt": ("Government bonds (federal, provincial, municipal)", 1.5, 3.0, "Rates"),
    "corp_ig": ("Investment-grade public corporate bonds", 1.0, 12.0, "Corporate bonds"),
    "corp_hy": ("Below-investment-grade bonds", 1.0, 35.0, "Corporate bonds"),
    "private_placements": ("Private placements", 0.3, 0.0, "Not street"),
    "mortgages_loans": ("Mortgages and other loans", 0.4, 0.0, "Not street"),
    "common": ("Common shares", 1.5, 10.0, "Equities"),
    "preferred": ("Preferred shares", 0.5, 25.0, "Equities"),
    "real_estate": ("Real estate", 0.1, 0.0, "Not street"),
    "other_invested": ("Private equity, infrastructure and other funds", 0.3, 0.0, "Not street"),
}
MATURITY = {"govt": 0.06, "corp_ig": 0.06, "corp_hy": 0.06, "private_placements": 0.06, "mortgages_loans": 0.10}
MM_ROLLS, MM_BPS = 6.0, 0.5
CAP = 1.0  # gross flows above this multiple of invested assets are money-market rolls

# Derivatives: traded notional per year per unit outstanding, and one-way cost in bps, by
# remaining-term bucket (<1y, 1-5y, >5y). Swaps roll their short bucket, replace a third of
# 1-5y and a tenth of >5y each year, plus 10% of the book rebalanced.
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
    "commodities_other": ("Commodity and other contracts", (1, 1 / 3, 0.1), (5.0, 5.0, 5.0), "Commodities"),
}
LF3_ROWS = {"010": "ir_forwards", "020": "ir_futures", "030": "ir_swaps", "040": "ir_options", "050": "ir_options",
            "210": "fx_forwards", "220": "fx_futures", "230": "fx_swaps", "240": "fx_options",
            "310": "equity_otc", "325": "credit", "330": "commodities_other"}
SHORT_DATED = {"ir_forwards", "ir_futures", "fx_forwards", "fx_futures", "equity_futures", "ir_options", "fx_options",
               "equity_options", "equity_otc", "credit", "commodities_other"}
# Main legal entity per OSFI filer, as in analysis/portfolio_reallocation/build.py; the holding
# companies and sister insurers that also file LF3 are left out so notionals are not counted twice.
OSFI_ENTITY = {
    "manulife": "The Manufacturers Life Insurance Company", "sun_life": "Sun Life Assurance Company of Canada",
    "canada_life": "The Canada Life Assurance Company", "rbc_life": "RBC Life Insurance Company",
    "bmo_life": "BMO Life Assurance Company", "ivari": "ivari", "empire_life": "The Empire Life Insurance Company",
    "equitable_life": "The Equitable Life Insurance Company of Canada", "cooperators_life": "Co-operators Life Insurance Company",
    "wawanesa_life": "The Wawanesa Life Insurance Company", "foresters_life": "Foresters Life Insurance Company",
    "canadian_premier": "Canadian Premier Life Insurance Company", "primerica_life": "Primerica Life Insurance Company of Canada",
}
# Low and high cases scale each product group's cost: tight versus wide markets and dealer
# relationships (e.g. IG corporates 8-20 bps, Canada bonds 1.5-5 bps, equities 6-15 bps).
RANGE = {"Rates": (0.5, 1.7), "Corporate bonds": (0.67, 1.67), "Equities": (0.6, 1.5), "FX": (0.5, 2.0),
         "Rates & credit derivatives": (0.5, 2.0), "Equity derivatives": (0.5, 2.0), "Commodities": (0.5, 2.0)}
BUCKETS = ["Rates", "Corporate bonds", "Equities", "FX", "Rates & credit derivatives", "Equity derivatives", "Commodities"]


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def holdings():
    """Year-end holdings by securities class and cash, C$ mm, per insurer and year."""
    mix = defaultdict(dict)
    names, freq = {}, {}
    for r in read(os.path.join(MIX, "mix_history.csv")):
        cid = r["company_id"]
        if cid == "peer_median" or not r["period"].endswith("Q4") or not r["amount_cad_mm"]:
            continue
        y = int(r["period"][:4])
        mix[(cid, y)][r["asset_class"]] = float(r["amount_cad_mm"])
        names[cid], freq[cid] = r["company"], r["frequency"]
    # within-class splits from the IFRS 17 Level 3 detail, by year, falling back to the insurer's
    # first year of detail and then to the peer median
    det = defaultdict(lambda: defaultdict(float))
    for r in read(os.path.join(MIX, "detail_ifrs17.csv")):
        if r["period"].endswith("Q4") or (r["company_id"] in ("rbc_life", "bmo_life") and r["period"].endswith("Q4")):
            det[(r["company_id"], int(r["period"][:4]))][r["level3"]] += float(r["amount_cad_mm"] or 0)
    big = {}
    for r in read(os.path.join(MIX, "bond_quality.csv")):
        if r["period"].endswith("Q4"):
            big[(r["company_id"], int(r["period"][:4]))] = float(r["below_ig_share_of_bonds_pct"]) / 100

    def split(d):
        g, c, pp = d.get("Government Bonds", 0), d.get("Corporate Bonds", 0), d.get("Illiquid Term Loans", 0)
        cs, ps = d.get("Common Shares", 0), d.get("Preferred Shares", 0)
        b, e = g + c + pp, cs + ps
        return ({"govt": g / b, "corp": c / b, "pp": pp / b} if b else None, {"common": cs / e, "pref": ps / e} if e else None)

    splits = {k: split(v) for k, v in det.items()}
    med_b = {k: statistics.median(s[0][k] for s in splits.values() if s[0]) for k in ("govt", "corp", "pp")}
    tot = sum(med_b.values())
    med_b = {k: v / tot for k, v in med_b.items()}
    med_e = {k: statistics.median(s[1][k] for s in splits.values() if s[1]) for k in ("common", "pref")}
    tot = sum(med_e.values())
    med_e = {k: v / tot for k, v in med_e.items()}
    med_big = statistics.median(big.values())

    out = {}
    for (cid, y), m in mix.items():
        own = sorted(k for k in splits if k[0] == cid)
        key = (cid, y) if (cid, y) in splits else (own[0] if own else None)
        sb, se = splits[key] if key else (None, None)
        sb, se = sb or med_b, se or med_e
        hy = big.get((cid, y), big.get((cid, 2023), med_big if cid not in ("foresters_life",) else med_big))
        bonds = m.get("Bonds", 0)
        corp = bonds * sb["corp"]
        hy_amt = min(bonds * hy, corp)
        out[(cid, y)] = {
            "govt": bonds * sb["govt"], "corp_ig": corp - hy_amt, "corp_hy": hy_amt, "private_placements": bonds * sb["pp"],
            "mortgages_loans": m.get("Mortgages & loans", 0),
            "common": m.get("Equities", 0) * se["common"], "preferred": m.get("Equities", 0) * se["pref"],
            "real_estate": m.get("Real estate", 0), "other_invested": m.get("Other invested assets", 0),
            "cash": m.get("Cash & short-term", 0),
        }
        out[(cid, y)]["total"] = sum(out[(cid, y)].values())
    return out, names, freq


def gross_turnover(hold):
    """(purchases + sales, maturities and repayments) / invested assets, by insurer and year."""
    g = {}
    for r in read(os.path.join(HERE, "disclosed_flows.csv")):
        cid, y = r["company_id"], int(r["year"])
        scale = 12 / float(r["months"])
        flows = (float(r["purchases_cad_mm"]) + float(r["sales_maturities_cad_mm"])) * scale
        st = ((num(r["short_term_purchases_cad_mm"]) or 0) + (num(r["short_term_sales_cad_mm"]) or 0)) * scale
        assets = num(r["invested_assets_cad_mm"]) or hold.get((cid, y), {}).get("total")
        if assets:
            g[(cid, y)] = {"g": (flows + st) / assets, "st": st / assets, "scope": r["scope"]}
    return g


def lf3_notionals():
    """Year-end derivative notionals by contract and remaining-term bucket, C$ mm (OSFI LF3)."""
    raw = defaultdict(float)
    for r in csv.DictReader(gzip.open(LF3, "rt")):
        a = r["address"]
        if not a.startswith("P21110") or OSFI_ENTITY.get(r["company_id"]) != r["entity"]:
            continue
        row, col = a[6:9], a[9:11]
        if row in LF3_ROWS and col in ("07", "27", "32", "37"):
            raw[(r["company_id"], int(r["fiscal_year"]), LF3_ROWS[row], col)] += float(r["value"] or 0) / 1000
    out = defaultdict(lambda: [0.0, 0.0, 0.0])
    for (cid, y, c, col), v in raw.items():
        if col != "07":
            continue
        b = [raw.get((cid, y, c, k), 0.0) for k in ("27", "32", "37")]
        v = abs(v)
        if sum(abs(x) for x in b) > 0:
            b = [abs(x) * v / sum(abs(x) for x in b) for x in b]
        else:
            b = [v, 0, 0] if c in SHORT_DATED else [0, 0, v]
        o = out[(cid, y, c)]
        for i in range(3):
            o[i] += b[i]
    for r in read(os.path.join(HERE, "other_derivatives.csv")):
        o = out[(r["company_id"], int(r["year"]), r["contract"])]
        for i, k in enumerate(("bucket_lt1_cad_mm", "bucket_1to5_cad_mm", "bucket_gt5_cad_mm")):
            o[i] += float(r[k])
    return out


def main():
    hold, names, freq = holdings()
    gt = gross_turnover(hold)
    notion = lf3_notionals()

    own_g = defaultdict(list)
    for (cid, y), v in gt.items():
        own_g[cid].append(v["g"] - v["st"])
    avg_g = {cid: statistics.mean(v) for cid, v in own_g.items()}
    median_g = statistics.median(min(v, CAP) for v in avg_g.values())

    # derivative cost as a ratio to invested assets in the years filed, applied to every year
    deriv_ratio = defaultdict(lambda: defaultdict(list))
    for (cid, y, c), b in notion.items():
        a = hold.get((cid, y), {}).get("total")
        if not a:
            continue
        _, turn, bps, bucket = DERIVATIVES[c]
        traded = sum(b[i] * turn[i] for i in range(3))
        cost = sum(b[i] * turn[i] * bps[i] for i in range(3)) / 1e4
        deriv_ratio[cid][(c, "cost")].append(cost / a)
        deriv_ratio[cid][(c, "notional")].append(sum(b) / a)
        deriv_ratio[cid][(c, "traded")].append(traded / a)
    deriv_years = defaultdict(set)
    for (cid, y, c) in notion:
        deriv_years[cid].add(y)

    by_year = []
    for (cid, y), h in sorted(hold.items()):
        if y not in YEARS:
            continue
        a = h["total"]
        prev = hold.get((cid, y - 1), {}).get("total")
        avg_a = (a + prev) / 2 if prev else a
        if (cid, y) in gt:
            g, st, gsrc = gt[(cid, y)]["g"], gt[(cid, y)]["st"], "disclosed"
        elif cid in avg_g:
            g, st, gsrc = avg_g[cid], 0.0, "insurer average of disclosed years"
        else:
            g, st, gsrc = median_g, 0.0, "peer median (no cash flow statement published)"
        g_sec = min(g - st, CAP)
        mm_extra = max(g - st - CAP, 0) + st
        mat = sum(h[k] * r for k, r in MATURITY.items()) / a
        vol = max(g_sec - mat, 0) * avg_a
        wsum = sum(h[k] * SECURITIES[k][1] for k in SECURITIES)
        row = {"company_id": cid, "company": names[cid], "year": y, "invested_assets_cad_mm": round(a, 1),
               "gross_turnover_pct": round(100 * g, 1), "turnover_source": gsrc,
               "traded_securities_cad_mm": round(vol, 1)}
        costs = defaultdict(float)
        for k, (label, w, bps, bucket) in SECURITIES.items():
            v = vol * h[k] * w / wsum if wsum else 0
            row[f"traded_{k}_cad_mm"] = round(v, 1)
            if bucket != "Not street":
                costs[bucket] += v * bps / 1e4
        costs["Rates"] += (h["cash"] * MM_ROLLS + mm_extra * avg_a) * MM_BPS / 1e4
        dtraded = 0.0
        for (c, kind), vals in deriv_ratio.get(cid, {}).items():
            if kind == "cost":
                costs[DERIVATIVES[c][3]] += statistics.mean(vals) * avg_a
            elif kind == "traded":
                dtraded += statistics.mean(vals) * avg_a
        row["traded_derivatives_notional_cad_mm"] = round(dtraded, 1)
        for b in BUCKETS:
            row[f"cost_{b}"] = round(costs[b], 3)
        row["cost_total_cad_mm"] = round(sum(costs.values()), 3)
        row["cost_low_cad_mm"] = round(sum(costs[b] * RANGE[b][0] for b in BUCKETS), 3)
        row["cost_high_cad_mm"] = round(sum(costs[b] * RANGE[b][1] for b in BUCKETS), 3)
        row["cost_bps_of_assets"] = round(1e4 * sum(costs.values()) / avg_a, 2)
        by_year.append(row)

    summary = []
    for cid in names:
        rs = [r for r in by_year if r["company_id"] == cid]
        if not rs:
            continue
        s = {"company_id": cid, "company": names[cid], "focus": int(cid == FOCUS), "frequency": freq[cid],
             "years": f"{rs[0]['year']}-{rs[-1]['year']}" if len(rs) > 1 else str(rs[0]["year"]), "n_years": len(rs),
             "avg_invested_assets_cad_mm": round(statistics.mean(r["invested_assets_cad_mm"] for r in rs), 0),
             "latest_invested_assets_cad_mm": rs[-1]["invested_assets_cad_mm"],
             "avg_gross_turnover_pct": round(statistics.mean(r["gross_turnover_pct"] for r in rs), 1),
             "turnover_source": rs[-1]["turnover_source"] if all(r["turnover_source"] == rs[-1]["turnover_source"] for r in rs) else "disclosed, gaps filled with insurer average",
             "derivative_notional_years": ",".join(str(y) for y in sorted(deriv_years.get(cid, []))) or "none filed",
             "avg_traded_securities_cad_mm": round(statistics.mean(r["traded_securities_cad_mm"] for r in rs), 0),
             "avg_traded_derivatives_notional_cad_mm": round(statistics.mean(r["traded_derivatives_notional_cad_mm"] for r in rs), 0)}
        for b in BUCKETS:
            s[f"cost_{b}"] = round(statistics.mean(r[f"cost_{b}"] for r in rs), 2)
        s["cost_total_cad_mm"] = round(statistics.mean(r["cost_total_cad_mm"] for r in rs), 2)
        s["cost_low_cad_mm"] = round(statistics.mean(r["cost_low_cad_mm"] for r in rs), 2)
        s["cost_high_cad_mm"] = round(statistics.mean(r["cost_high_cad_mm"] for r in rs), 2)
        s["cost_pct_of_assets"] = round(100 * s["cost_total_cad_mm"] / s["avg_invested_assets_cad_mm"], 4)
        s["cost_bps_of_assets"] = round(1e4 * s["cost_total_cad_mm"] / s["avg_invested_assets_cad_mm"], 2)
        summary.append(s)
    summary.sort(key=lambda s: -s["avg_invested_assets_cad_mm"])

    assumptions = [{"product": label, "group": bucket, "relative_trading_weight": w, "one_way_cost_bps": bps,
                    "turnover": "share of gross flows net of maturities, allocated by holdings x weight", "maturities_per_year": MATURITY.get(k, "")}
                   for k, (label, w, bps, bucket) in SECURITIES.items()]
    assumptions.append({"product": "Money market (cash and short-term)", "group": "Rates", "relative_trading_weight": "",
                        "one_way_cost_bps": MM_BPS, "turnover": f"{MM_ROLLS:g} rolls a year; flows above {CAP:.0%} of assets", "maturities_per_year": ""})
    for k, (label, turn, bps, bucket) in DERIVATIVES.items():
        assumptions.append({"product": label, "group": bucket, "relative_trading_weight": "",
                            "one_way_cost_bps": "/".join(f"{b:g}" for b in bps),
                            "turnover": "traded per year per unit outstanding by term <1y/1-5y/>5y: " + "/".join(f"{t:.2f}" for t in turn),
                            "maturities_per_year": ""})

    for d in [HERE] + ([SHARE] if os.path.isdir(SHARE) else []):
        for name, rows in (("wallet_by_insurer.csv", summary), ("wallet_by_year.csv", by_year), ("assumptions.csv", assumptions)):
            with open(os.path.join(d, name), "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
    print(f"median gross turnover used for non-disclosers: {100 * median_g:.1f}%")
    for s in summary:
        print(f"{s['company'][:32]:32s} AUM {s['avg_invested_assets_cad_mm'] / 1000:7.1f}bn  G {s['avg_gross_turnover_pct']:6.1f}%  "
              f"wallet C${s['cost_total_cad_mm']:7.1f}mm ({s['cost_low_cad_mm']:.1f}-{s['cost_high_cad_mm']:.1f})  {s['cost_bps_of_assets']:5.2f}bps  "
              + " ".join(f"{b[:6]}={s[f'cost_{b}']:.1f}" for b in BUCKETS))


if __name__ == "__main__":
    main()
