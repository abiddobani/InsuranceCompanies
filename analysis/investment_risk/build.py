#!/usr/bin/env python3
"""Benchmark the peer insurers' investment risk metrics: market, credit and liquidity.

Framework: R. Doff, "Investment risks: market, credit and liquidity risk"
(Risk Management for Insurers, Risk.net). Market risk is read through rate,
spread, equity and alternatives sensitivities plus LICAT market risk capital;
credit risk through LICAT credit risk capital, bond ratings, below-investment-
grade and private credit exposure, mortgage arrears, credit-loss allowances and
sector concentration; liquidity risk through liquid-asset tiers, a weighted
liquidity score (Doff's liquidity-weighted assets), repo funding and disclosed
liquid-asset measures.

Sources:
  OSFI filers   data/osfi/LCQ_core.csv.gz (LICAT credit / market / insurance
                risk, non-par), LF2_core.csv.gz (P21012 investments, P21020
                provisions), LF3_core.csv.gz (P21030 bonds by sector, P21050
                mortgage arrears), fiscal 2025 Q4 (October year end for BMO
                Life and RBC Life).
  Portfolio     analysis/portfolio_composition/portfolio_composition_pct.csv
                and off_balance_sheet.csv (latest general account mix).
  Disclosures   disclosed_sensitivities.csv, disclosed_bond_ratings.csv,
                disclosed_liquidity.csv, hand-entered from YE2025 filings.

Writes the CSVs in dashboard/ next to this script.

Usage: python3 analysis/investment_risk/build.py
"""
import collections
import csv
import gzip
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OSFI = os.path.join(ROOT, "data", "osfi")
PC = os.path.join(ROOT, "analysis", "portfolio_composition")
OUT = os.path.join(HERE, "dashboard")
FOCUS = "rbc_life"
EAR_BOOK_CAD_MM = 25000  # earnings at risk is shown for a C$25Bn portfolio
YEAR, QUARTER = "2025", "Q4"

# The 20 peers, in order of general-account size.
COMPANIES = collections.OrderedDict([
    ("manulife", "Manulife"),
    ("canada_life", "Canada Life"),
    ("sun_life", "Sun Life"),
    ("ia", "iA Financial Group"),
    ("rbc_life", "RBC Life"),
    ("bmo_life", "BMO Life"),
    ("beneva", "Beneva"),
    ("ivari", "ivari"),
    ("empire_life", "Empire Life"),
    ("equitable_life", "Equitable Life"),
    ("cooperators_life", "Co-operators Life"),
    ("uv_insurance", "UV Insurance"),
    ("wawanesa_life", "Wawanesa Life"),
    ("assumption_life", "Assumption Life"),
    ("foresters_life", "Foresters Life"),
    ("canadian_premier", "Canadian Premier Life"),
    ("primerica_life", "Primerica Life"),
    ("humania", "Humania"),
    ("desjardins", "Desjardins Insurance"),
    ("canada_protection_plan", "Canada Protection Plan"),
])
REGULATOR = {"ia": "AMF", "beneva": "AMF", "desjardins": "AMF", "humania": "AMF", "uv_insurance": "AMF",
             "assumption_life": "FCNB"}

# OSFI legal entity per filer (same choice as the portfolio composition work).
OSFI_ENTITY = {
    "manulife": "The Manufacturers Life Insurance Company",
    "canada_life": "The Canada Life Assurance Company",
    "sun_life": "Sun Life Assurance Company of Canada",
    "rbc_life": "RBC Life Insurance Company",
    "bmo_life": "BMO Life Assurance Company",
    "ivari": "ivari",
    "empire_life": "The Empire Life Insurance Company",
    "equitable_life": "The Equitable Life Insurance Company of Canada",
    "cooperators_life": "Co-operators Life Insurance Company",
    "wawanesa_life": "The Wawanesa Life Insurance Company",
    "foresters_life": "Foresters Life Insurance Company",
    "canadian_premier": "Canadian Premier Life Insurance Company",
    "primerica_life": "Primerica Life Insurance Company of Canada",
}
ENTITY_TO_CO = {v: k for k, v in OSFI_ENTITY.items()}

LCQ = {
    "D1010010020": "licat_total_ratio",
    "D1010010360": "bsb",
    "D3000010077": "credit_cap",
    "D5000010057": "market_cap",
    "D6000010257": "insurance_cap",
    "D1010010240": "segfund_cap_a",
    "D1010010280": "segfund_cap_b",
}
# LF2 P21012 rows, column 40 (balance sheet value).
BOND_IG = ["045", "055", "140", "210", "410"]
BOND_BIG = ["050", "065", "160", "230", "430"]
GOVT = ["045", "050", "055", "065", "140", "160"]
PRIVATE_CORP = ["410", "430"]
LF2_ROWS = {"total_bonds": "479", "mortgages": "500", "total_inv": "889"}
SECTORS = collections.OrderedDict([
    ("049", "Energy"), ("099", "Materials"), ("149", "Industrials"), ("199", "Consumer discretionary"),
    ("249", "Consumer staples"), ("299", "Health care"), ("349", "Financials"), ("399", "Technology"),
    ("449", "Communications"), ("499", "Utilities"), ("549", "Other"),
])

# Liquidity tiers and illustrative Doff-style liquidity weights per Level 3 bucket.
TIERS = collections.OrderedDict([
    ("Cash", ("Cash and government bonds", 1.00)),
    ("Government Bonds", ("Cash and government bonds", 0.95)),
    ("Corporate Bonds", ("Public bonds and shares", 0.85)),
    ("Asset Backed Securities", ("Public bonds and shares", 0.70)),
    ("Bonds (issuer n/d)", ("Public bonds and shares", 0.85)),
    ("Common Shares", ("Public bonds and shares", 0.70)),
    ("Preferred Shares", ("Public bonds and shares", 0.70)),
    ("Commercial Mortgages", ("Mortgages and private loans", 0.50)),
    ("Illiquid Term Loans", ("Mortgages and private loans", 0.40)),
    ("Private Liquid Loans", ("Mortgages and private loans", 0.50)),
    ("Co-Investments", ("Mortgages and private loans", 0.40)),
    ("Infrastructure Debt", ("Mortgages and private loans", 0.40)),
    ("Structured Products", ("Mortgages and private loans", 0.40)),
    ("Other Private Debt", ("Mortgages and private loans", 0.40)),
    ("Policy & Other Loans", ("Mortgages and private loans", 0.00)),
    ("Real Estate Equity", ("Real estate and private equity", 0.20)),
    ("Infrastructure Equity", ("Real estate and private equity", 0.20)),
    ("Other Private Equity", ("Real estate and private equity", 0.20)),
    ("Other / Unclassified", ("Real estate and private equity", 0.00)),
])
TIER_ORDER = ["Cash and government bonds", "Public bonds and shares", "Mortgages and private loans",
              "Real estate and private equity"]
RISK_ASSETS = ["Common Shares", "Preferred Shares", "Real Estate Equity", "Infrastructure Equity", "Other Private Equity"]
PRIVATE_CREDIT = ["Commercial Mortgages", "Illiquid Term Loans", "Private Liquid Loans", "Co-Investments",
                  "Infrastructure Debt", "Structured Products", "Other Private Debt"]

FACTORS = collections.OrderedDict([
    (("rates", "+50bp"), "Rates +50 bp"),
    (("rates", "-50bp"), "Rates -50 bp"),
    (("credit_spreads", "+50bp"), "Credit spreads +50 bp"),
    (("public_equity", "-10%"), "Public equity -10%"),
    (("alternatives", "-10%"), "Real estate and alternatives -10%"),
])


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_csv(name, rows, fields):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r[k]) for k in fields})


def osfi_rows(ret, wanted, year=YEAR, quarter=QUARTER):
    """{company_id: {address: value}} for the chosen entities and period."""
    out = collections.defaultdict(dict)
    with gzip.open(os.path.join(OSFI, f"{ret}_core.csv.gz"), "rt", newline="") as f:
        for r in csv.DictReader(f):
            co = ENTITY_TO_CO.get(r["entity"])
            if co and r["fiscal_year"] == year and (quarter is None or r["quarter"] == quarter) \
                    and wanted(r["address"]) and r["value"]:
                out[co][r["address"]] = float(r["value"])
    return out


def pct(n, d, digits=2):
    return round(100.0 * n / d, digits) if n is not None and d else None


def osfi_metrics():
    lcq = osfi_rows("LCQ", lambda a: a in LCQ)
    lf2 = osfi_rows("LF2", lambda a: (a.startswith("P21012") and a.endswith("40")) or a.startswith("P210208"))
    lf3 = osfi_rows("LF3", lambda a: a.startswith("P21030") or a.startswith("P2105069"), quarter=None)
    metrics, sectors = {}, []
    for co in OSFI_ENTITY:
        q, p, a = lcq.get(co, {}), lf2.get(co, {}), lf3.get(co, {})
        row = lambda r: p.get(f"P21012{r}40", 0.0)
        inv = row(LF2_ROWS["total_inv"]) / 1000
        bonds = row(LF2_ROWS["total_bonds"]) / 1000
        big = sum(row(r) for r in BOND_BIG) / 1000
        govt = sum(row(r) for r in GOVT) / 1000
        priv = sum(row(r) for r in PRIVATE_CORP) / 1000
        mort = row(LF2_ROWS["mortgages"]) / 1000
        cap = {k: q.get(addr) for addr, k in LCQ.items()}
        credit = (cap["credit_cap"] or 0) / 1000
        market = (cap["market_cap"] or 0) / 1000
        ecl = sum(p.get(f"P210208895{s}", 0.0) for s in "789") / 1000
        ecl3 = p.get("P2102088959", 0.0) / 1000
        mort_total = a.get("P2105069906")
        mort_bad = a.get("P2105069931")
        sec_total = a.get("P2103089901")
        m = {
            "company_id": co, "entity": OSFI_ENTITY[co],
            "invested_cad_mm": round(inv, 1),
            "licat_total_ratio": cap["licat_total_ratio"],
            "credit_cap_cad_mm": round(credit, 1), "market_cap_cad_mm": round(market, 1),
            "insurance_cap_cad_mm": round((cap["insurance_cap"] or 0) / 1000, 1),
            "credit_cap_pct_inv": pct(credit, inv), "market_cap_pct_inv": pct(market, inv),
            "bonds_pct_inv": pct(bonds, inv, 1),
            "below_ig_pct_bonds": pct(big, bonds),
            "govt_pct_bonds": pct(govt, bonds, 1),
            "private_corp_pct_bonds": pct(priv, bonds, 1),
            "mortgages_pct_inv": pct(mort, inv, 1),
            "ecl_bps_inv": round(10000 * ecl / inv, 1) if inv else None,
            "stage3_bps_inv": round(10000 * ecl3 / inv, 1) if inv else None,
            "mortgage_problem_pct": pct(mort_bad or 0, mort_total) if mort_total else None,
        }
        if sec_total:
            shares = {name: pct(a.get(f"P21030{code}01", 0.0), sec_total, 1) for code, name in SECTORS.items()}
            top = max(shares, key=lambda k: shares[k] if k != "Other" else -1)
            m["top_sector"], m["top_sector_pct"] = top, shares[top]
            m["energy_pct_corp"] = shares["Energy"]
            hhi = sum((v / 100) ** 2 for v in shares.values())
            m["sector_hhi"] = round(hhi * 10000)
            for name, v in shares.items():
                sectors.append({"company_id": co, "company": COMPANIES[co], "sector": name, "pct_of_corporates": v,
                                "is_focus": int(co == FOCUS)})
        metrics[co] = m
    return metrics, sectors


def portfolio_metrics():
    pcts = {r["company_id"]: r for r in read_csv(os.path.join(PC, "portfolio_composition_pct.csv"))}
    obs = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in read_csv(os.path.join(PC, "off_balance_sheet.csv")):
        key = "repos" if r["level3"] == "Repos" else ("securities_lending" if "lending" in r["level3"].lower()
                                                       else "derivatives")
        obs[r["company_id"]][key] += float(r["pct_of_portfolio"] or 0) * 100
    out, tiers = {}, []
    for co, r in pcts.items():
        shares = {k: float(r.get(k) or 0) for k in TIERS}
        by_tier = collections.OrderedDict((t, 0.0) for t in TIER_ORDER)
        score = 0.0
        for k, v in shares.items():
            by_tier[TIERS[k][0]] += v
            score += v * TIERS[k][1]
        for t, v in by_tier.items():
            tiers.append({"company_id": co, "company": COMPANIES[co], "tier": t, "pct": round(v, 2),
                          "is_focus": int(co == FOCUS)})
        out[co] = {
            "portfolio_as_of": r["as_of"], "portfolio_cad_mm": float(r["portfolio_cad_mm"]),
            "liquid_tier1_pct": round(by_tier[TIER_ORDER[0]], 1),
            "liquid_tier12_pct": round(by_tier[TIER_ORDER[0]] + by_tier[TIER_ORDER[1]], 1),
            "weighted_liquidity_pct": round(score, 1),
            "risk_assets_pct": round(sum(shares[k] for k in RISK_ASSETS), 1),
            "private_credit_pct": round(sum(shares[k] for k in PRIVATE_CREDIT), 1),
            "repo_pct": round(obs[co]["repos"], 2) if co in obs else None,
            "derivative_notional_pct": round(obs[co]["derivatives"], 1) if co in obs else None,
        }
    return out, tiers


def earnings_at_risk(sens):
    """Loss from each factor's adverse shock, scaled to EAR_BOOK_CAD_MM of invested assets.

    Rates take the worse of +50 bp and -50 bp; spreads +50 bp; public equity and
    alternatives -10%. A shock that produces a gain counts as zero (no offset),
    and the total is the undiversified sum of the four.
    """
    by = collections.defaultdict(dict)
    for s in sens:
        if s["invested_cad_mm"]:
            by[s["company_id"]][s["factor"]] = s
    rows = []
    for co, f in by.items():
        scale = EAR_BOOK_CAD_MM / next(iter(f.values()))["invested_cad_mm"]
        loss = lambda key: max(0.0, -f[key]["ni_impact_cad_mm"] * scale) if key in f else None
        rate_keys = [k for k in ("Rates +50 bp", "Rates -50 bp") if k in f]
        rate_key = min(rate_keys, key=lambda k: f[k]["ni_impact_cad_mm"]) if rate_keys else None
        parts = {
            "rates_cad_mm": loss(rate_key) if rate_key else None,
            "spreads_cad_mm": loss("Credit spreads +50 bp"),
            "equity_cad_mm": loss("Public equity -10%"),
            "alts_cad_mm": loss("Real estate and alternatives -10%"),
        }
        rows.append(dict(
            company_id=co, company=COMPANIES[co], is_focus=int(co == FOCUS), book_cad_mm=EAR_BOOK_CAD_MM,
            rate_shock_used=rate_key.replace("Rates ", "") if rate_key else "",
            **{k: (round(v, 1) if v is not None else None) for k, v in parts.items()},
            total_cad_mm=round(sum(v for v in parts.values() if v is not None), 1),
            factors_disclosed=sum(v is not None for v in parts.values()),
            tax_basis=next(iter(f.values()))["tax_basis"],
        ))
    rows.sort(key=lambda r: -r["total_cad_mm"])
    return rows


def sensitivities(osfi):
    rows = []
    for r in read_csv(os.path.join(HERE, "disclosed_sensitivities.csv")):
        key = (r["factor"], r["shock"])
        if key not in FACTORS:
            continue
        co = r["company_id"]
        den = osfi[co]["invested_cad_mm"] if r["denominator_cad_mm"] == "OSFI" else (
            float(r["denominator_cad_mm"]) if r["denominator_cad_mm"] else None)
        ni = float(r["ni_impact_cad_mm"])
        rows.append({
            "company_id": co, "company": COMPANIES[co], "factor": FACTORS[key], "as_of": r["as_of"],
            "ni_impact_cad_mm": ni, "invested_cad_mm": den,
            "ni_bps_invested": round(10000 * ni / den, 1) if den else None,
            "ni_per_10bn_cad_mm": round(1e4 * ni / den, 1) if den else None,
            "licat_pts": float(r["licat_pts"]) if r["licat_pts"] else None,
            "tax_basis": r["tax_basis"], "source": r["source"], "note": r["note"], "is_focus": int(co == FOCUS),
        })
    return rows


def ratings(osfi):
    rows = []
    disclosed = {r["company_id"]: r for r in read_csv(os.path.join(HERE, "disclosed_bond_ratings.csv"))}
    for co, name in COMPANIES.items():
        if co in disclosed:
            d = disclosed[co]
            ig_a = sum(float(d[k]) for k in ("aaa", "aa", "a"))
            rows.append({"company_id": co, "company": name, "basis": "Rating split disclosed",
                         "a_or_higher_pct": round(ig_a, 1), "bbb_pct": float(d["bbb"]),
                         "below_ig_pct": float(d["below_ig"]),
                         "unrated_pct": round(float(d["unrated"]) + float(d["govt_not_rated"]), 1),
                         "scope": d["scope"], "source": d["source"], "is_focus": int(co == FOCUS)})
        elif co in osfi and osfi[co]["below_ig_pct_bonds"] is not None:
            big = osfi[co]["below_ig_pct_bonds"]
            rows.append({"company_id": co, "company": name, "basis": "OSFI: investment grade vs below only",
                         "investment_grade_pct": round(100 - big, 2), "below_ig_pct": big,
                         "scope": "Legal-entity bonds, OSFI LF2 FY2025 Q4",
                         "source": "OSFI LF2 P21012", "is_focus": int(co == FOCUS)})
    return rows


def main():
    osfi, sectors = osfi_metrics()
    port, tiers = portfolio_metrics()
    sens = sensitivities(osfi)
    rate = ratings(osfi)
    liq = {r["company_id"]: r for r in read_csv(os.path.join(HERE, "disclosed_liquidity.csv"))}
    caps = {}
    for r in read_csv(os.path.join(ROOT, "data", "capital_ratios.csv")):
        caps.setdefault(r["company_id"], r)  # first row is the group / main entity

    sens_by = collections.defaultdict(dict)
    for s in sens:
        sens_by[s["company_id"]][s["factor"]] = s
    disclosed_ratings = {r["company_id"] for r in rate if r["basis"] == "Rating split disclosed"}

    landscape, coverage = [], []
    for co, name in COMPANIES.items():
        o, p = osfi.get(co, {}), port.get(co, {})
        cap = o.get("licat_total_ratio")
        cap_src = "OSFI LCQ FY2025 Q4" if cap else None
        if cap is None and caps.get(co, {}).get("total_ratio_pct"):
            cap, cap_src = float(caps[co]["total_ratio_pct"]), f"{caps[co]['framework']} {caps[co]['as_at']}"
        landscape.append({
            "company_id": co, "company": name, "regulator": REGULATOR.get(co, "OSFI"),
            "is_focus": int(co == FOCUS),
            "portfolio_cad_mm": p.get("portfolio_cad_mm"), "portfolio_as_of": p.get("portfolio_as_of"),
            "capital_ratio_pct": cap, "capital_ratio_source": cap_src,
            "market_cap_pct_inv": o.get("market_cap_pct_inv"), "credit_cap_pct_inv": o.get("credit_cap_pct_inv"),
            "risk_assets_pct": p.get("risk_assets_pct"), "private_credit_pct": p.get("private_credit_pct"),
            "below_ig_pct_bonds": next((r["below_ig_pct"] for r in rate if r["company_id"] == co), None),
            "bbb_pct_bonds": next((r["bbb_pct"] for r in rate if r["company_id"] == co and "bbb_pct" in r), None),
            "mortgage_problem_pct": o.get("mortgage_problem_pct"), "ecl_bps_inv": o.get("ecl_bps_inv"),
            "energy_pct_corp": o.get("energy_pct_corp"), "top_sector": o.get("top_sector"),
            "top_sector_pct": o.get("top_sector_pct"),
            "liquid_tier1_pct": p.get("liquid_tier1_pct"), "liquid_tier12_pct": p.get("liquid_tier12_pct"),
            "weighted_liquidity_pct": p.get("weighted_liquidity_pct"),
            "repo_pct": p.get("repo_pct"), "derivative_notional_pct": p.get("derivative_notional_pct"),
            "equity_down10_bps": sens_by[co].get("Public equity -10%", {}).get("ni_bps_invested"),
            "rates_up50_bps": sens_by[co].get("Rates +50 bp", {}).get("ni_bps_invested"),
            "spreads_up50_bps": sens_by[co].get("Credit spreads +50 bp", {}).get("ni_bps_invested"),
            "alts_down10_bps": sens_by[co].get("Real estate and alternatives -10%", {}).get("ni_bps_invested"),
            "disclosed_liquidity_pct": float(liq[co]["ratio_pct"]) if co in liq else None,
        })
        # What each peer publishes, by metric family (the disclosure landscape).
        def mark(has_disclosed, has_osfi):
            return "Disclosed" if has_disclosed else ("Regulatory data" if has_osfi else "Not available")
        fam = collections.OrderedDict([
            ("Rate sensitivity", mark("Rates +50 bp" in sens_by[co], False)),
            ("Spread sensitivity", mark("Credit spreads +50 bp" in sens_by[co], False)),
            ("Equity sensitivity", mark("Public equity -10%" in sens_by[co], False)),
            ("Alternatives sensitivity", mark("Real estate and alternatives -10%" in sens_by[co], False)),
            ("Capital sensitivity", mark(any(s["licat_pts"] is not None for s in sens_by[co].values()), False)),
            ("Market risk capital", mark(False, co in osfi)),
            ("Credit risk capital", mark(False, co in osfi)),
            ("Bond rating split", mark(co in disclosed_ratings, co in osfi)),
            ("Mortgage arrears", mark(False, o.get("mortgage_problem_pct") is not None)),
            ("Sector concentration", mark(False, o.get("top_sector") is not None)),
            ("Liquid assets measure", mark(co in liq, co in port)),
        ])
        if co == "canada_protection_plan":
            fam = collections.OrderedDict((k, "Not available") for k in fam)
        for k, v in fam.items():
            coverage.append({"company_id": co, "company": name, "metric": k, "status": v, "is_focus": int(co == FOCUS)})

    write_csv("landscape.csv", landscape, list(landscape[0].keys()))
    write_csv("osfi_metrics.csv", [dict(osfi[c], company=COMPANIES[c]) for c in OSFI_ENTITY],
              ["company_id", "company"] + [k for k in osfi["rbc_life"] if k not in ("company_id",)])
    write_csv("sensitivities.csv", sens, list(sens[0].keys()))
    write_csv("bond_ratings.csv", rate, ["company_id", "company", "basis", "a_or_higher_pct", "bbb_pct",
                                         "below_ig_pct", "unrated_pct", "investment_grade_pct", "scope",
                                         "source", "is_focus"])
    write_csv("liquidity_tiers.csv", tiers, list(tiers[0].keys()))
    write_csv("sector_mix.csv", sectors, list(sectors[0].keys()))
    write_csv("coverage.csv", coverage, list(coverage[0].keys()))
    ear = earnings_at_risk(sens)
    write_csv("earnings_at_risk.csv", ear, list(ear[0].keys()))
    print(f"wrote {len(landscape)} insurers, {len(sens)} sensitivities, {len(rate)} rating rows to {OUT}")


if __name__ == "__main__":
    main()
