#!/usr/bin/env python3
"""Download OSFI life insurer open data and extract the core-company subset.

Downloads the resources in sources/osfi_datasets.csv (dataset "life_insurers")
into osfi/raw/, then for fiscal 2023 onward (IFRS 17 basis) writes:

  data/osfi/<RETURN>_core.csv.gz   every data point for the core companies'
                                   OSFI entities plus the industry totals
  data/osfi/balance_sheet_assets.csv
                                   LF1 asset-side lines (current period) pivoted
                                   to one row per entity and quarter, i.e. the
                                   invested-asset mix (cash, bonds, mortgages,
                                   equities, real estate, derivatives, ...)
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
RETURNS = ("LF1", "LF2", "LF3", "LCA", "LCQ")
FIRST_YEAR = 2023
# LF1 data point addresses look like P2000201001: page 20002 (assets), row 01,
# column 001 (current period). Check entities_seen/labels output if OSFI changes this.
ASSET_PAGE, CURRENT_COL = "P20002", "001"

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
            if os.path.exists(dest) and not force:
                continue
            print(f"downloading {r['resource']} ...")
            req = urllib.request.Request(r["url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=600) as resp, open(dest, "wb") as out:
                while chunk := resp.read(1 << 20):
                    out.write(chunk)


def quarter_of(value):
    m = re.search(r"Q([1-4])", value or "")
    return f"Q{m.group(1)}" if m else value


def extract():
    os.makedirs(OUT, exist_ok=True)
    entities = collections.Counter()
    assets = collections.defaultdict(dict)  # (company_id, entity, year, q) -> {label: value}
    asset_labels = {}
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
                    if ret == "LF1" and addr.startswith(ASSET_PAGE) and addr.endswith(CURRENT_COL):
                        asset_labels[addr] = row[c_label]
                        assets[(cid, ent, year, q)][addr] = row[c_val]
            print(f"{ret}: {n} rows -> {os.path.relpath(out_path, ROOT)}")

    addrs = sorted(asset_labels)
    with open(os.path.join(OUT, "balance_sheet_assets.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["company_id", "entity", "fiscal_year", "quarter"] + [asset_labels[a] for a in addrs])
        w.writerow(["", "", "", "address"] + addrs)
        for key in sorted(assets):
            w.writerow(list(key) + [assets[key].get(a, "") for a in addrs])
    with open(os.path.join(OUT, "entities_seen.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["entity", "company_id", "rows_since_2023"])
        for (ent, cid), n in sorted(entities.items()):
            w.writerow([ent, cid, n])
    print(f"balance_sheet_assets.csv: {len(assets)} entity-quarters x {len(addrs)} lines")


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
