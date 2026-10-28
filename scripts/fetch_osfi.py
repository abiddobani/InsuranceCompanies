#!/usr/bin/env python3
"""Download OSFI life insurer open data and extract the core-company subset.

Downloads the resources in sources/osfi_datasets.csv (dataset "life_insurers")
into osfi/raw/, then for fiscal 2020 onward writes the files below. IFRS 17
returns (LF1, LF2, LF3, LCA) start in fiscal 2023 (2024 for October year ends);
2020 to 2023 balance sheets come from the IFRS 4 era 10Q return. LICAT (LCQ)
runs throughout, but its 2023 revision changed available capital for IFRS 17.

  data/osfi/<RETURN>_core.csv.gz   every data point for the core companies'
                                   OSFI entities plus the industry totals
  data/osfi/balance_sheet_assets.csv
                                   LF1 asset-side lines (current period) pivoted
                                   to one row per entity and quarter (cash,
                                   investments total, derivatives, investment
                                   properties, seg funds, ...)
  data/osfi/invested_assets.csv    LF2 investment schedule (balance sheet value)
                                   pivoted the same way: bonds by issuer type and
                                   IG/below-IG, mortgages, preferred and common
                                   shares, other loans, other invested assets
  data/osfi/balance_sheet_assets_ifrs4.csv
                                   10Q asset lines (current year) per entity and
                                   quarter, 2020 to 2023, IFRS 4 basis
  data/osfi/portfolio_mix.csv      one harmonized asset mix across both bases,
                                   with a basis column (see HARMONIZED)
  data/osfi/licat_ratios.csv       LCQ LICAT summary pivoted the same way: total
                                   and core ratio (%), available capital, tier 1/2,
                                   surplus allowance, eligible deposits, base
                                   solvency buffer and its components
  data/osfi/discount_curves.csv    LF2 IFRS 17 discount curves in long format:
                                   risk-free rates, liquidity premiums and discount
                                   rates by line of business, Canada and U.S.A.,
                                   tenors 1 to 80 years (%)
  data/osfi/entities_seen.csv      every entity name in the files and the
                                   company_id it was mapped to (check this)

Usage:
    python3 scripts/fetch_osfi.py              # download + extract
    python3 scripts/fetch_osfi.py --no-download
"""
import argparse
import collections
import csv
import gzip
import os
import re
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "osfi", "raw")
OUT = os.path.join(ROOT, "data", "osfi")
RETURNS = ("LF1", "LF2", "LF3", "LCA", "LCQ", "10Q", "10A")
FIRST_YEAR = 2020
# Data point addresses are P + 5-digit page + 3-digit row + 2-digit column.
# Pivots written to data/osfi: file -> (return, page, column). Values are $000s.
#   LF1 P2000201001: page 20002 (assets), row 010, column 01 (current period, total).
#   LF2 P2101247940: page 21012 (investments), row 479, column 40 (balance
#   sheet value = FVTPL + FVOCI + amortized cost + ...).
#   LCQ D1010010020: page D10100 (LICAT summary), one column; ratios are in %.
PIVOTS = {
    "balance_sheet_assets.csv": ("LF1", "P20002", "01"),
    "invested_assets.csv": ("LF2", "P21012", "40"),
    "licat_ratios.csv": ("LCQ", "D10100", ""),
    "balance_sheet_assets_ifrs4.csv": ("10Q", "P20010", "01"),
}
# Harmonized asset mix: column -> (IFRS 17 addresses summed, IFRS 4 addresses summed).
# IFRS 17 moved policy loans into insurance contract balances, so that line is
# IFRS 4 only; "other" on IFRS 4 includes interests in associates.
HARMONIZED = {
    "cash": (["P2000201001"], ["P2001001001"]),
    "short_term_investments": (["P2101201040"], ["P2001004001"]),
    "bonds": (["P2101247940"], ["P2001025001"]),
    "mortgages": (["P2101250040"], ["P2001030001"]),
    "preferred_shares": (["P2101259940"], ["P2001042001"]),
    "common_shares": (["P2101265940"], ["P2001044001"]),
    "investment_properties": (["P2000211001"], ["P2001051001"]),
    "policy_loans": ([], ["P2001020001"]),
    "other_loans_and_invested_assets": (["P2101281040", "P2101282040", "P2000208001"],
                                        ["P2001060001", "P2001055001"]),
    "derivative_assets": (["P2000210001"], ["P2001052001"]),
    "segregated_funds": (["P2000216001"], ["P2001056001"]),
    "total_assets": (["P2000299901"], ["P2001089901"]),
}
# LF2 "Risk free rates and liquidity premium by line of business" pages:
# page -> region. Labels end "..., Year 20 (%), <curve>".
DISCOUNT_PAGES = {"P35035": "Canada", "P35045": "U.S.A.", "P35055": "Canada", "P35065": "U.S.A."}

# Identify the script honestly; open.canada.ca rejects a bare "Mozilla/5.0".
USER_AGENT = "InsuranceCompanies-dataset/1.0 (+https://github.com/abiddobani/InsuranceCompanies)"

# Patterns on normalized OSFI entity names -> company_id from data/companies.csv
ENTITY_PATTERNS = [
    (r"^bmo life", "bmo_life"),
    (r"^canada life", "canada_life"),
    (r"^canadian premier life", "canadian_premier"),
    (r"^co-?operators life", "cooperators_life"),
    (r"^empire life", "empire_life"),
    (r"^equitable life", "equitable_life"),
    (r"^foresters life|independent order of foresters", "foresters_life"),
    (r"^manulife|^manufacturers life", "manulife"),
    (r"^primerica life", "primerica_life"),
    (r"^rbc life", "rbc_life"),
    (r"^sun life", "sun_life"),
    (r"^wawanesa life", "wawanesa_life"),
    (r"^ivari", "ivari"),
    (r"^total ", "industry_total"),
]


def norm(name):
    name = re.sub(r"^the\s+|\s*\(the\)\s*$", "", name.strip(), flags=re.I)
    return name.lower()


def company_for(entity):
    n = norm(entity)
    return next((cid for pat, cid in ENTITY_PATTERNS if re.search(pat, n)), "")


def clean_label(label):
    """'LF2: Mortgage Loans, Balance Sheet Value\nCol. 11+16...' -> 'Mortgage Loans'"""
    label = re.sub(r"\s+", " ", label).strip()
    label = re.sub(r"^LF\d: |^LCQ, LICAT Ratios, Summary Calculations, ", "", label)
    label = re.sub(r",\s*(Balance Sheet Value|Current Period).*$", "", label)
    return label.replace("Coporate", "Corporate")


def col(header, *prefixes):
    """Find a column by case-insensitive prefix (headers mix English/French)."""
    for p in prefixes:
        for h in header:
            if h.lower().startswith(p.lower()):
                return h
    raise KeyError(f"no column starting with {prefixes} in {header}")


def download(force=False):
    os.makedirs(RAW, exist_ok=True)
    with open(os.path.join(ROOT, "sources", "osfi_datasets.csv"), newline="") as f:
        for r in csv.DictReader(f):
            if r["dataset"] not in ("life_insurers", "who_we_regulate"):
                continue
            dest = os.path.join(RAW, os.path.basename(r["url"]))
            if os.path.exists(dest) and os.path.getsize(dest) > 1024 and not force:
                continue
            print(f"downloading {r['resource']} ...")
            req = urllib.request.Request(r["url"], headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=600) as resp:
                if "html" in resp.headers.get("Content-Type", ""):
                    raise RuntimeError(f"{r['url']} returned an HTML page, not data")
                with open(dest, "wb") as out:
                    while chunk := resp.read(1 << 20):
                        out.write(chunk)


def quarter_of(value):
    m = re.search(r"Q([1-4])", value or "")
    return f"Q{m.group(1)}" if m else value


def extract():
    os.makedirs(OUT, exist_ok=True)
    entities = collections.Counter()
    # file -> (company_id, entity, year, q) -> {address: value}; file -> {address: label}
    pivot = {f: collections.defaultdict(dict) for f in PIVOTS}
    pivot_labels = {f: {} for f in PIVOTS}
    curves = []
    for ret in RETURNS:
        path = os.path.join(RAW, f"life_insurance_companies_quarterly_{ret.lower()}.csv")
        if not os.path.exists(path):
            print(f"missing {path}; skipped")
            continue
        with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            h = reader.fieldnames
            c_year, c_q = col(h, "Fiscal Year"), col(h, "Fiscal Quarter")
            c_ent, c_addr = col(h, "Total Life Insurance", "Company"), col(h, "Data Point Address/")
            c_label, c_val = col(h, "Data Point Address Label"), col(h, "Measure Value")
            out_path = os.path.join(OUT, f"{ret}_core.csv.gz")
            with gzip.open(out_path, "wt", newline="", encoding="utf-8") as gz:
                w = csv.writer(gz)
                w.writerow(["company_id", "entity", "fiscal_year", "quarter", "return",
                            "address", "label", "value"])
                n = 0
                for row in reader:
                    try:
                        year = int(str(row[c_year])[:4])
                    except ValueError:
                        continue
                    if year < FIRST_YEAR:
                        continue
                    ent = row[c_ent]
                    cid = company_for(ent)
                    entities[(ent, cid)] += 1
                    if not cid:
                        continue
                    q = quarter_of(row[c_q])
                    w.writerow([cid, ent, year, q, ret, row[c_addr], row[c_label], row[c_val]])
                    n += 1
                    addr = row[c_addr]
                    for fname, (p_ret, page, column) in PIVOTS.items():
                        if ret == p_ret and len(addr) == 11 and addr.startswith(page) and addr.endswith(column):
                            pivot_labels[fname][addr] = clean_label(row[c_label])
                            pivot[fname][(cid, ent, year, q)][addr] = row[c_val]
                    if ret == "LF2" and addr[:6] in DISCOUNT_PAGES:
                        m = re.search(r"Year (\d+) \(%\), (.*)$", re.sub(r"\s+", " ", row[c_label]))
                        if m:
                            curves.append([cid, ent, year, q, DISCOUNT_PAGES[addr[:6]],
                                           m.group(2).strip(), int(m.group(1)), row[c_val], addr])
            print(f"{ret}: {n} rows -> {os.path.relpath(out_path, ROOT)}")

    for fname, rows in pivot.items():
        labels = pivot_labels[fname]
        addrs = sorted(labels)
        with open(os.path.join(OUT, fname), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["company_id", "entity", "fiscal_year", "quarter"] + [labels[a] for a in addrs])
            w.writerow(["", "", "", "address"] + addrs)
            for key in sorted(rows):
                w.writerow(list(key) + [rows[key].get(a, "") for a in addrs])
        print(f"{fname}: {len(rows)} entity-quarters x {len(addrs)} lines")
    with open(os.path.join(OUT, "discount_curves.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["company_id", "entity", "fiscal_year", "quarter", "region", "curve",
                    "tenor_years", "rate_pct", "address"])
        w.writerows(sorted(curves, key=lambda r: r[:7]))
    print(f"discount_curves.csv: {len(curves)} points")
    write_portfolio_mix(pivot)
    with open(os.path.join(OUT, "entities_seen.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["entity", "company_id", "rows_since_2023"])
        for (ent, cid), n in sorted(entities.items()):
            w.writerow([ent, cid, n])


def write_portfolio_mix(pivot):
    """Combine the IFRS 17 (LF1 + LF2) and IFRS 4 (10Q) pivots into one series."""
    ifrs17 = collections.defaultdict(dict)
    for fname in ("balance_sheet_assets.csv", "invested_assets.csv"):
        for key, vals in pivot[fname].items():
            ifrs17[key].update(vals)
    rows = []
    for basis, data, i in (("IFRS 17", ifrs17, 0), ("IFRS 4", pivot["balance_sheet_assets_ifrs4.csv"], 1)):
        for key, vals in data.items():
            out = []
            for addrs in HARMONIZED.values():
                got = [float(vals[a]) for a in addrs[i] if vals.get(a, "") not in ("", None)]
                out.append(f"{sum(got):.0f}" if got else "")
            rows.append(list(key) + [basis] + out)
    with open(os.path.join(OUT, "portfolio_mix.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["company_id", "entity", "fiscal_year", "quarter", "basis"] +
                   [f"{c}_cad_000" for c in HARMONIZED])
        w.writerows(sorted(rows, key=lambda r: (r[0], r[1], r[2], r[3], r[4])))
    print(f"portfolio_mix.csv: {len(rows)} entity-quarters")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-download even if present")
    args = ap.parse_args()
    if not args.no_download:
        download(args.force)
    extract()


if __name__ == "__main__":
    main()
