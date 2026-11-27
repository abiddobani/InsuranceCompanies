#!/usr/bin/env python3
"""Download a company's SEC EDGAR filings (40-F annual, 6-K current reports)
into docs/<company_id>/<year>/ and merge them into data/document_index.csv.

Used for issuers whose own site refuses the download script (Manulife).
SEC requires a user agent that names a contact email, so set SEC_CONTACT:

    SEC_CONTACT=you@example.com python3 scripts/fetch_sec.py
    SEC_CONTACT=you@example.com python3 scripts/fetch_sec.py --company manulife
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from download_documents import INDEX, INDEX_FIELDS, ROOT, YEARS, guess_doc_type, read_csv

# BMO Life has no public filings of its own; BMO Financial Group reports it
# inside its Wealth Management segment (and bmo.com refuses the script).
# Sun Life's own site only lists 2022 on, so EDGAR fills 2020 and 2021.
# company_id -> (SEC CIK, fiscal years to keep)
ISSUERS = {"manulife": ("1086888", YEARS), "bmo_life": ("927971", YEARS),
           "sun_life": ("1097362", ("2020", "2021"))}
FORMS = ("40-F", "40-F/A", "6-K", "6-K/A")
KEEP_EXT = (".htm", ".html", ".pdf", ".xlsx", ".xls")
OCT_YEAR_END = {"bmo_life"}
DELAY = 0.15  # SEC allows 10 requests per second


def get(url, ua, tries=4):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Encoding": "identity"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read()
            time.sleep(DELAY)
            return body
        except urllib.error.HTTPError:
            raise
        except Exception:  # dropped connection: back off and retry
            if attempt == tries - 1:
                raise
            time.sleep(2 ** (attempt + 1))


MONTHS = "january february march april may june july august september october november december".split()


def period_from_text(body, cid):
    """(fiscal_year, quarter) from a results document's "three months ended June 30,
    2025" wording, else None. Printer-named 2023 filings (d462199dex991.htm) can
    only be placed this way. BMO's fiscal year ends October 31."""
    text = re.sub(r"<[^>]+>|&nbsp;|&#160;", " ", body[:400000].decode("utf-8", "replace"))
    m = re.search(r"(?:(?:three|3)(?:\s+and\s+(?:six|nine|twelve))?\s+months|quarter)\s+ended\s+"
                  r"([A-Za-z]+)\s+\d{1,2},?\s+(20\d\d)", re.sub(r"\s+", " ", text), re.I)
    if not m or m.group(1).lower() not in MONTHS:
        return None
    month, year = MONTHS.index(m.group(1).lower()) + 1, int(m.group(2))
    ends = (1, 4, 7, 10) if cid in OCT_YEAR_END else (3, 6, 9, 12)
    if month not in ends:
        return None
    return str(year), f"Q{ends.index(month) + 1}"


def filings(cik, ua):
    """Yield (form, accession, filing_date, report_date, primary_doc_description)."""
    data = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json", ua))
    pages = [data["filings"]["recent"]]
    for extra in data["filings"].get("files", []):
        pages.append(json.loads(get("https://data.sec.gov/submissions/" + extra["name"], ua)))
    for page in pages:
        for i, form in enumerate(page["form"]):
            if form in FORMS and page["filingDate"][i][:4] in YEARS:
                yield (form, page["accessionNumber"][i], page["filingDate"][i],
                       page["reportDate"][i], page["primaryDocDescription"][i])


def retag():
    """Set fiscal_year/period on already downloaded SEC rows from their text."""
    rows = read_csv(INDEX)
    n = 0
    for r in rows:
        if r["found_via"] != "sec_edgar" or r["status"] != "ok" or r["period"]:
            continue
        with open(os.path.join(ROOT, r["local_path"]), "rb") as f:
            tagged = period_from_text(f.read(), r["company_id"])
        if tagged:
            r["fiscal_year"], r["period"] = tagged
            n += 1
    with open(INDEX, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"tagged {n} filings with a fiscal quarter")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", action="append", default=[], help="limit to company_id")
    ap.add_argument("--retag", action="store_true", help="re-tag periods of downloaded filings, no network")
    args = ap.parse_args()
    if args.retag:
        return retag()
    contact = os.environ.get("SEC_CONTACT")
    if not contact:
        sys.exit("set SEC_CONTACT to a contact email; SEC rejects requests without one")
    ua = f"InsuranceCompanies dataset {contact}"  # SEC wants plain "name email"

    index = read_csv(INDEX) if os.path.exists(INDEX) else []
    by_url = {r["url"]: r for r in index}
    stored = {r["sha256"]: r["local_path"] for r in index if r["status"] == "ok"}
    for cid, (cik, keep_years) in ISSUERS.items():
        if args.company and cid not in args.company:
            continue
        for form, acc, filed, period_end, desc in filings(cik, ua):
            base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
            items = json.loads(get(base + "/index.json", ua))["directory"]["item"]
            for item in items:
                name = item["name"]
                url = f"{base}/{name}"
                if not name.lower().endswith(KEEP_EXT) or "index" in name.lower():
                    continue
                if re.fullmatch(r"R\d+\.htm", name):  # XBRL viewer fragments
                    continue
                if by_url.get(url, {}).get("status") in ("ok", "duplicate"):
                    continue
                year = (period_end or filed)[:4]
                if year not in keep_years:  # e.g. the FY2019 40-F filed in 2020
                    continue
                title = f"{form} filed {filed}: {desc or name}"
                doc_type = guess_doc_type(name)
                if doc_type == "other":
                    doc_type = "sec_" + form.lower().replace("/", "_")
                row = {"company_id": cid, "fiscal_year": year, "period": "FY" if form.startswith("40-F") else "",
                       "doc_type": doc_type, "title": title, "url": url, "found_via": "sec_edgar"}
                try:
                    body = get(url, ua)
                except urllib.error.HTTPError as e:
                    by_url[url] = {**row, "status": f"http_{e.code}"}
                    continue
                sha = hashlib.sha256(body).hexdigest()
                meta = {"bytes": len(body), "sha256": sha, "content_type": ""}
                if sha in stored:
                    by_url[url] = {**row, **meta, "status": "duplicate", "local_path": stored[sha]}
                    continue
                tagged = period_from_text(body, cid) if not form.startswith("40-F") else None
                if tagged:
                    year, row["fiscal_year"], row["period"] = tagged[0], tagged[0], tagged[1]
                folder = os.path.join(ROOT, "docs", cid, year)
                os.makedirs(folder, exist_ok=True)
                path = os.path.join(folder, f"{acc}_{name}")
                with open(path, "wb") as f:
                    f.write(body)
                stored[sha] = os.path.relpath(path, ROOT)
                by_url[url] = {**row, **meta, "status": "ok", "local_path": stored[sha]}
                print(f"ok  {cid:<10} {form:<6} {filed}  {name}")

    rows = sorted(by_url.values(), key=lambda r: (r["company_id"], r["fiscal_year"], r["period"]))
    with open(INDEX, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"index at {os.path.relpath(INDEX, ROOT)}")


if __name__ == "__main__":
    main()
