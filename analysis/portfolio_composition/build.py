#!/usr/bin/env python3
"""Map each peer insurer's latest general-account portfolio onto the CIO taxonomy.

Scope: general account (premium-funded liabilities, CSM and surplus). Excluded
wherever the source allows: segregated funds, participating accounts,
pass-through fund units (policyholder-directed UL funds), asset-manager AUM,
bank-funded loans, own-use property and investments in subsidiaries.
Derivative assets are excluded from the balance sheet and shown off balance
sheet as notionals.

Sources:
  OSFI filers  data/osfi/LF1_core.csv.gz (cash, investment properties, equity
               accounted investees) and LF2_core.csv.gz page P21012 column 40
               (investment schedule), latest quarter per entity.
  Others       disclosed_portfolios.csv, hand-entered from the filings named
               in its source column (C$ millions).
  Off balance  OSFI LF3 page P21110 (derivative notionals) and P22030 row 280
  sheet        (repos), fiscal 2025; iA and Manulife from their Q2 2026 notes.

Writes portfolio_composition_long.csv, portfolio_composition_pct.csv,
off_balance_sheet.csv and coverage_notes.csv next to this script.

Usage: python3 analysis/portfolio_composition/build.py
"""
import collections
import csv
import gzip
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OSFI = os.path.join(ROOT, "data", "osfi")

# Level 3 -> (Level 1, Level 2), in chart order. Rows marked * are not in the
# CIO taxonomy and were added so every disclosed dollar has a home.
TAXONOMY = [
    ("Asset Backed Securities", "Internally Managed", "Public Fixed Income"),
    ("Corporate Bonds", "Internally Managed", "Public Fixed Income"),
    ("Government Bonds", "Internally Managed", "Public Fixed Income"),
    ("Bonds (issuer n/d)", "Internally Managed", "Public Fixed Income"),  # *
    ("Common Shares", "Internally Managed", "Public Equity"),
    ("Preferred Shares", "Internally Managed", "Public Equity"),
    ("Commercial Mortgages", "Internally Managed", "Private Fixed Income"),
    ("Illiquid Term Loans", "Internally Managed", "Private Fixed Income"),
    ("Private Liquid Loans", "Internally Managed", "Private Fixed Income"),
    ("Co-Investments", "Internally Managed", "Private Fixed Income"),
    ("Policy & Other Loans", "Internally Managed", "Private Fixed Income"),  # *
    ("Cash", "Internally Managed", "Cash & Cash Equivalents"),
    ("Real Estate Equity", "Externally Managed", "Equity"),
    ("Infrastructure Equity", "Externally Managed", "Equity"),
    ("Other Private Equity", "Externally Managed", "Equity"),
    ("Infrastructure Debt", "Externally Managed", "Debt"),
    ("Structured Products", "Externally Managed", "Debt"),
    ("Other Private Debt", "Externally Managed", "Debt"),
    ("Other / Unclassified", "Other", "Other"),  # *
]
LEVELS = {l3: (l1, l2) for l3, l1, l2 in TAXONOMY}

COMPANIES = collections.OrderedDict([
    ("manulife", "Manulife"),
    ("sun_life", "Sun Life"),
    ("canada_life", "Canada Life"),
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
    ("foresters_life", "Foresters Life (incl. Canada Protection Plan)"),
    ("canadian_premier", "Canadian Premier Life"),
    ("humania", "Humania"),
    ("primerica_life", "Primerica Life"),
    ("desjardins", "Desjardins Insurance"),
])

# OSFI entity used for each OSFI filer taken from regulatory data.
OSFI_ENTITY = {
    "bmo_life": "BMO Life Assurance Company",
    "canadian_premier": "Canadian Premier Life Insurance Company",
    "cooperators_life": "Co-operators Life Insurance Company",
    "empire_life": "The Empire Life Insurance Company",
    "equitable_life": "The Equitable Life Insurance Company of Canada",
    "foresters_life": "Foresters Life Insurance Company",
    "ivari": "ivari",
    "primerica_life": "Primerica Life Insurance Company of Canada",
    "rbc_life": "RBC Life Insurance Company",
    "wawanesa_life": "The Wawanesa Life Insurance Company",
    # Not charted from OSFI, used for splits and the off-balance-sheet view.
    "canada_life": "The Canada Life Assurance Company",
    "manulife": "The Manufacturers Life Insurance Company",
    "sun_life": "Sun Life Assurance Company of Canada",
}
OSFI_ONLY = [c for c in OSFI_ENTITY if c not in ("canada_life", "manulife", "sun_life")]

# LF2 P21012 rows (column 40, balance sheet value) -> Level 3.
LF2_ROWS = {
    "010": "Cash",  # short-term investments
    "045": "Government Bonds", "050": "Government Bonds",
    "055": "Government Bonds", "065": "Government Bonds",
    "140": "Government Bonds", "160": "Government Bonds",
    "210": "Corporate Bonds", "230": "Corporate Bonds",
    "410": "Illiquid Term Loans", "430": "Illiquid Term Loans",
    "500": "Commercial Mortgages",
    "520": "Preferred Shares", "560": "Preferred Shares",
    "659": "Common Shares",
    "810": "Policy & Other Loans",
    "820": "Other Private Equity",
}
LF2_TOTAL = "889"
LF2_SUBSIDIARIES = "669"
# LF1 P20002 rows (column 01, current period).
LF1_ROWS = {"010": "Cash", "110": "Real Estate Equity", "080": "Other Private Equity"}

NOTES = {
    "manulife": "MFC consolidated general fund. Manulife Bank mortgages and loans and own-use property excluded. "
                "Participating assets not disclosed by asset class, so par is included. ALDA mapped to externally managed "
                "equity by asset class although Manulife manages most of it in-house.",
    "sun_life": "SLF consolidated general fund invested assets (excludes MFS/SLC client AUM and segregated funds). "
                "Participating assets not disclosed by asset class, so par is included. Other financial invested assets "
                "(limited partnerships and funds) are not split by type and sit in Other Private Equity.",
    "canada_life": "Great-West Lifeco Canada non-participating, Europe and Capital & Risk Solutions segments (excludes "
                   "Empower and the Canada participating account). Bond split uses OSFI Canada Life Assurance's "
                   "government/corporate/private mix; stock split uses Lifeco-wide public vs privately held.",
    "ia": "iA consolidated (includes a small participating account and index-linked UL backing that cannot be "
          "separated). Private equity and infrastructure not split. Car loans (iA Auto Finance) kept in Policy & Other Loans.",
    "beneva": "Beneva Group consolidated, which includes property and casualty insurance (not separable). "
              "Pass-through mutual funds backing UL and savings products excluded.",
    "assumption_life": "Participating assets and pass-through investment fund units excluded using note 4.",
    "humania": "Summary statements only: bond issuer split and loan type not published.",
    "uv_insurance": "Summary statements only: bond issuer split, private investment type and loan type not published. "
                    "Includes the BMO Life block acquired in 2025.",
    "desjardins": "Not charted: Desjardins Group publishes no stand-alone investment breakdown for Desjardins Financial "
                  "Security; its life assets are combined with the caisse network and P&C.",
}
OSFI_NOTE = ("OSFI LF2 legal-entity filing. Participating assets cannot be separated (par share of insurance contract "
             "liabilities shown). ABS sit inside corporate bonds; 'Other invested assets' and equity-accounted investees "
             "mapped to Other Private Equity; mortgages include residential. Common shares include equities backing "
             "universal life accounts, which OSFI does not separate.")
OCT_YEAR_END = {"bmo_life", "rbc_life"}
QUARTER_END = {"Q1": "03-31", "Q2": "06-30", "Q3": "09-30", "Q4": "12-31"}
QUARTER_END_OCT = {"Q1": "01-31", "Q2": "04-30", "Q3": "07-31", "Q4": "10-31"}


def period_end(cid, fy, q):
    """OSFI fiscal quarter -> calendar date; BMO Life and RBC Life use an October year end."""
    return f"{fy}-{(QUARTER_END_OCT if cid in OCT_YEAR_END else QUARTER_END)[q]}"


def read_gz(name):
    with gzip.open(os.path.join(OSFI, name), "rt", newline="") as f:
        yield from csv.DictReader(f)


def latest_osfi(entities):
    """Latest (year, quarter) LF2 P21012 values per entity -> {entity: (period, {row: value})}."""
    by = collections.defaultdict(lambda: collections.defaultdict(dict))
    for r in read_gz("LF2_core.csv.gz"):
        a = r["address"]
        if r["entity"] in entities and a.startswith("P21012") and a.endswith("40") and r["value"]:
            by[r["entity"]][(r["fiscal_year"], r["quarter"])][a[6:9]] = float(r["value"])
    return {e: max(p.items()) for e, p in by.items()}


def lf1_values(entities, periods):
    out = collections.defaultdict(dict)
    for r in read_gz("LF1_core.csv.gz"):
        e = r["entity"]
        a = r["address"]
        if e in entities and (r["fiscal_year"], r["quarter"]) == periods.get(e) and a.startswith("P20002") \
                and a.endswith("01") and r["value"]:
            out[e][a[6:9]] = float(r["value"])
    return out


def par_share(entities):
    """Participating share of individual insurance contract liabilities (Canada + U.S.), LF3 fiscal 2025."""
    vals = collections.defaultdict(dict)
    for r in read_gz("LF3_core.csv.gz"):
        if r["entity"] in entities and r["fiscal_year"] == "2025" and r["address"] in (
                "P2201051001", "P2201051011", "P2201055901", "P2201055911") and r["value"]:
            vals[r["entity"]][r["address"]] = float(r["value"])
    out = {}
    for e, v in vals.items():
        par = max(v.get("P2201051001", 0), 0) + max(v.get("P2201051011", 0), 0)
        tot = v.get("P2201055901", 0) + v.get("P2201055911", 0)
        out[e] = par / tot if tot else None
    return out


def off_balance_sheet(entities):
    """Fiscal 2025 derivative notionals and repos from LF3 ($000s)."""
    rows = {
        "P2111001007": ("Derivatives", "Fixed Income", "Linear"),
        "P2111002007": ("Derivatives", "Fixed Income", "Linear"),
        "P2111003007": ("Derivatives", "Fixed Income", "Linear"),
        "P2111004007": ("Derivatives", "Fixed Income", "Non-Linear"),
        "P2111005007": ("Derivatives", "Fixed Income", "Non-Linear"),
        "P2111031007": ("Derivatives", "Equity", "Linear and non-linear (not split)"),
        "P2111032507": ("Derivatives", "Credit", "Credit default swaps"),
        "P2111029907": ("Derivatives", "Currency", "FX forwards, futures, swaps, options"),
        "P2111033007": ("Derivatives", "Other", "Other"),
        "P2203028001": ("Asset Financing", "Encumbered Assets", "Repos"),
    }
    out = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in read_gz("LF3_core.csv.gz"):
        if r["entity"] in entities and r["fiscal_year"] == "2025" and r["address"] in rows and r["value"]:
            out[r["entity"]][rows[r["address"]]] += float(r["value"])
    return out


def main():
    ents = set(OSFI_ENTITY.values())
    osfi = latest_osfi(ents)
    periods = {e: p for e, (p, _) in osfi.items()}
    lf1 = lf1_values(ents, periods)
    par = par_share(ents)

    holdings = collections.defaultdict(lambda: collections.defaultdict(float))  # company -> l3 -> C$MM
    excluded = collections.defaultdict(dict)
    meta = {}

    for cid in OSFI_ONLY:
        e = OSFI_ENTITY[cid]
        (fy, q), v = osfi[e]
        for row, l3 in LF2_ROWS.items():
            holdings[cid][l3] += v.get(row, 0) / 1000
        for row, l3 in LF1_ROWS.items():
            holdings[cid][l3] += lf1[e].get(row, 0) / 1000
        if v.get(LF2_SUBSIDIARIES):
            excluded[cid]["Investment in subsidiaries"] = v[LF2_SUBSIDIARIES] / 1000
        # Check: the mapped LF2 rows must add back to the schedule total.
        mapped = sum(v.get(r, 0) for r in LF2_ROWS) + v.get(LF2_SUBSIDIARIES, 0)
        assert abs(mapped - v[LF2_TOTAL]) < 2, (cid, mapped, v[LF2_TOTAL])
        meta[cid] = dict(as_of=period_end(cid, fy, q), source=f"OSFI LF2/LF1, {e}", note=OSFI_NOTE)

    # Canada Life bond mix from its OSFI LF2 schedule.
    _, cla = osfi[OSFI_ENTITY["canada_life"]]
    cla_mix = collections.defaultdict(float)
    for row, l3 in LF2_ROWS.items():
        if l3 in ("Government Bonds", "Corporate Bonds", "Illiquid Term Loans"):
            cla_mix[l3] += cla.get(row, 0)
    cla_tot = sum(cla_mix.values())

    with open(os.path.join(HERE, "disclosed_portfolios.csv"), newline="") as f:
        for r in csv.DictReader(f):
            cid, l3, amt = r["company_id"], r["level3"], float(r["amount_cad_mm"])
            meta.setdefault(cid, dict(as_of=r["as_of"], source=r["source"], note=NOTES.get(cid, "")))
            if l3.startswith("EXCLUDED: "):
                excluded[cid][l3[10:]] = amt
            elif l3 == "_bonds":
                for k, w in cla_mix.items():
                    holdings[cid][k] += amt * w / cla_tot
            elif l3 == "_stocks":
                holdings[cid]["Common Shares"] += amt * 14041 / 22105
                holdings[cid]["Other Private Equity"] += amt * 8064 / 22105
            else:
                assert l3 in LEVELS, l3
                holdings[cid][l3] += amt
    for cid in NOTES:
        meta.setdefault(cid, {}).setdefault("note", NOTES[cid])
        meta[cid]["note"] = NOTES[cid] if cid not in OSFI_ONLY else meta[cid]["note"]
    meta["desjardins"].update(as_of="", source="")

    for cid in ("manulife", "sun_life"):
        meta[cid]["par_share"] = par.get(OSFI_ENTITY[cid])
    for cid in OSFI_ONLY:
        meta[cid]["par_share"] = par.get(OSFI_ENTITY[cid])

    long_rows, pct_rows, cov_rows = [], [], []
    for cid, name in COMPANIES.items():
        h = holdings.get(cid, {})
        total = sum(h.values())
        m = meta.get(cid, {})
        cov_rows.append(dict(
            company_id=cid, company=name, as_of=m.get("as_of", ""), source=m.get("source", ""),
            portfolio_cad_mm=round(total, 1) if total else "",
            par_share_of_insurance_liabilities=("excluded" if "Participating account" in excluded.get(cid, {})
                                               else "" if m.get("par_share") is None else round(m["par_share"], 3)),
            excluded=("; ".join(f"{k} {v:,.0f}" for k, v in excluded.get(cid, {}).items())),
            note=m.get("note", "")))
        if not total:
            continue
        pct = dict(company_id=cid, company=name, as_of=m["as_of"], portfolio_cad_mm=round(total, 1))
        for l3, l1, l2 in TAXONOMY:
            amt = h.get(l3, 0.0)
            long_rows.append(dict(company_id=cid, company=name, as_of=m["as_of"], level1=l1, level2=l2,
                                  level3=l3, amount_cad_mm=round(amt, 2), pct_of_portfolio=round(amt / total, 5)))
            pct[l3] = round(100 * amt / total, 2)
        pct_rows.append(pct)

    def write(name, rows, fields=None):
        with open(os.path.join(HERE, name), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    write("portfolio_composition_long.csv", long_rows)
    write("portfolio_composition_pct.csv", pct_rows,
          ["company_id", "company", "as_of", "portfolio_cad_mm"] + [t[0] for t in TAXONOMY])
    write("coverage_notes.csv", cov_rows)

    # Off balance sheet, % of the on-balance-sheet portfolio above.
    obs = off_balance_sheet(ents)
    totals = {r["company_id"]: r["portfolio_cad_mm"] for r in pct_rows}
    obs_rows = []
    for cid in list(OSFI_ONLY) + ["manulife", "sun_life", "canada_life"]:
        e = OSFI_ENTITY[cid]
        for (l1, l2, l3), v in sorted(obs.get(e, {}).items()):
            obs_rows.append(dict(company_id=cid, company=COMPANIES[cid], as_of=period_end(cid, "2025", "Q4"),
                                 source=f"OSFI LF3, {e}",
                                 level1=l1, level2=l2, level3=l3, amount_cad_mm=round(v / 1000, 1),
                                 pct_of_portfolio=round(v / 1000 / totals[cid], 4)))
    # Disclosed in IR notes (C$ millions).
    for cid, l1, l2, l3, v, src in [
        ("ia", "Derivatives", "Equity", "Linear and non-linear (not split)", 10501, "iA Q2 2026 FS note 6"),
        ("ia", "Derivatives", "Fixed Income", "Linear and non-linear (not split)", 28447, "iA Q2 2026 FS note 6"),
        ("ia", "Derivatives", "Currency", "FX forwards, futures, swaps, options", 16080, "iA Q2 2026 FS note 6"),
        ("ia", "Asset Financing", "Encumbered Assets", "Repos", 2291, "iA Q2 2026 FS fair value table"),
        ("manulife", "Asset Financing", "Encumbered Assets", "Security Lending", 3113, "MFC Q2 2026 note on securities lending"),
        ("manulife", "Asset Financing", "Encumbered Assets", "Repos", 1422, "MFC Q2 2026 note on securities lending"),
    ]:
        obs_rows = [r for r in obs_rows if not (r["company_id"] == cid and r["level2"] == l2 and r["level3"] == l3)]
        obs_rows.append(dict(company_id=cid, company=COMPANIES[cid], as_of="2026-06-30", source=src, level1=l1,
                             level2=l2, level3=l3, amount_cad_mm=v, pct_of_portfolio=round(v / totals[cid], 4)))
    for i, r in enumerate(obs_rows, 1):
        r["row_id"] = f"obs{i:03d}"
    write("off_balance_sheet.csv", obs_rows, ["row_id"] + [k for k in obs_rows[0] if k != "row_id"])

    for r in pct_rows:
        print(f"{r['company']:<48} {r['as_of']:<12} {r['portfolio_cad_mm']:>12,.0f}")


if __name__ == "__main__":
    main()
