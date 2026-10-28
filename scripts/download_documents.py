#!/usr/bin/env python3
"""Download insurer investor-relations documents listed in sources/ir_documents.csv.

Optionally crawls the pages in sources/seed_pages.csv with a headless browser
(--crawl) to discover more PDF/XLSX links for 2023 onward, then downloads
everything into docs/<company_id>/<fiscal_year>/ and writes data/document_index.csv.

Rows marked found_via=pattern are guesses built from each issuer's URL scheme;
misses (404 or an HTML page instead of a file) are recorded and skipped.

Usage:
    python3 scripts/download_documents.py            # listed URLs only
    python3 scripts/download_documents.py --crawl    # also crawl seed pages
    python3 scripts/download_documents.py --company sun_life --company ia
"""
import argparse
import csv
import hashlib
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "sources", "ir_documents.csv")
SEEDS = os.path.join(ROOT, "sources", "seed_pages.csv")
INDEX = os.path.join(ROOT, "data", "document_index.csv")
DOCS = os.path.join(ROOT, "docs")
# Identify the script honestly; sites that refuse it are recorded as gaps.
UA = "InsuranceCompanies-dataset/1.0 (+https://github.com/abiddobani/InsuranceCompanies)"
FILE_EXT = (".pdf", ".xlsx", ".xls", ".csv")
YEARS = ("2023", "2024", "2025", "2026")
INDEX_FIELDS = ["company_id", "fiscal_year", "period", "doc_type", "title", "url",
                "found_via", "status", "local_path", "bytes", "sha256", "content_type"]


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def guess_doc_type(text):
    t = text.lower()
    for key, kind in (("licat", "licat_disclosure"), ("sip", "supplementary_pdf"),
                      ("supplement", "supplementary_pdf"), ("finsupp", "supplementary_pdf"),
                      ("mda", "mda"), ("md&a", "mda"), ("financial-statements", "financial_statements"),
                      ("fin-stats", "financial_statements"), ("annual", "annual_report"),
                      ("presentation", "presentation"), ("slides", "presentation"),
                      ("release", "news_release"), ("earnings", "news_release"),
                      ("fact", "fact_sheet"), ("transcript", "transcript")):
        if key in t:
            return kind
    return "other"


def guess_period(text):
    t = text.lower()
    year = next((y for y in YEARS if y in t), "")
    if not year:
        m = re.search(r"q([1-4])[-_]?(2[3-6])\b", t)  # e.g. q225
        if m:
            return "20" + m.group(2), "Q" + m.group(1)
    m = re.search(r"\b(?:q|t)([1-4])\b|q([1-4])[-_]", t)
    quarter = "Q" + (m.group(1) or m.group(2)) if m else ("FY" if "annual" in t else "")
    return year, quarter


def is_out_of_range(text):
    """True when the link names only years before 2023 (e.g. a 2021 annual report)."""
    years = set(re.findall(r"(?<!\d)(20[0-3]\d)(?!\d)", text))
    years |= {"20" + y for y in re.findall(r"q[1-4][-_]?(2[0-9])\b", text.lower())}  # q422
    return bool(years) and not years & set(YEARS)


def crawl(seeds, companies):
    """Collect document links from seed pages with Playwright (JS-rendered pages)."""
    from playwright.sync_api import sync_playwright  # pip install playwright

    found = []
    with sync_playwright() as p:
        # Claude cloud envs ship one Chromium build; point at it if the pip
        # playwright package expects a different one.
        exe = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
        browser = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
        for seed in seeds:
            if companies and seed["company_id"] not in companies:
                continue
            # A fresh tab per seed: a page that timed out keeps navigating and
            # would otherwise interrupt every later goto.
            page = browser.new_page()
            try:
                page.goto(seed["url"], wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(4000)  # let JS-built link lists render
                links = page.eval_on_selector_all(
                    "a[href]", "els => els.map(e => [e.href, (e.innerText || '').trim()])")
            except Exception as e:  # keep going; record nothing for this seed
                print(f"  crawl failed {seed['url']}: {e}", file=sys.stderr)
                continue
            finally:
                page.close()
            print(f"  crawled {len(links):>4} links  {seed['url']}", file=sys.stderr)
            for href, text in links:
                href = urllib.parse.urldefrag(href)[0]
                path = urllib.parse.urlparse(href).path.lower()
                if not path.endswith(FILE_EXT) and "/download" not in path and "getmedia" not in path:
                    continue
                if is_out_of_range(href + " " + text):
                    continue
                year, period = guess_period(href + " " + text)
                found.append({"company_id": seed["company_id"], "fiscal_year": year,
                              "period": period, "doc_type": guess_doc_type(href + " " + text),
                              "title": text[:200], "url": href, "found_via": "crawl"})
            time.sleep(1)
        browser.close()
    return found


def local_name(row, url, content_type):
    name = os.path.basename(urllib.parse.urlparse(url).path) or "document"
    if name in ("download", "") or "." not in name:
        ext = ".xlsx" if "spreadsheet" in content_type else ".pdf"
        name = re.sub(r"[^a-z0-9]+", "-", (row["title"] or "document").lower()).strip("-") + ext
    return name


def fetch(row, dest_root, stored):
    """Download one URL. stored maps sha256 -> local path, so identical files
    reached from different URLs are kept once."""
    url = row["url"]
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            ctype = resp.headers.get("Content-Type", "")
            body = resp.read()
    except urllib.error.HTTPError as e:
        return {"status": f"http_{e.code}"}
    except Exception as e:
        return {"status": f"error:{type(e).__name__}"}
    if "text/html" in ctype and not url.lower().endswith(".html"):
        return {"status": "not_a_file", "content_type": ctype}
    year = row["fiscal_year"] or "undated"
    folder = os.path.join(dest_root, row["company_id"], year)
    os.makedirs(folder, exist_ok=True)
    sha = hashlib.sha256(body).hexdigest()
    meta = {"bytes": len(body), "sha256": sha, "content_type": ctype}
    if sha in stored:
        return {"status": "duplicate", "local_path": stored[sha], **meta}
    path = os.path.join(folder, local_name(row, url, ctype))
    if os.path.exists(path):  # same file name, different content
        stem, ext = os.path.splitext(path)
        path = f"{stem}-{sha[:8]}{ext}"
    with open(path, "wb") as f:
        f.write(body)
    stored[sha] = os.path.relpath(path, ROOT)
    return {"status": "ok", "local_path": stored[sha], **meta}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crawl", action="store_true", help="discover more links from seed pages")
    ap.add_argument("--company", action="append", default=[], help="limit to company_id (repeatable)")
    ap.add_argument("--dest", default=DOCS, help="download folder (default: docs/)")
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between requests")
    args = ap.parse_args()

    rows = read_csv(MANIFEST)
    if args.crawl:
        rows += crawl(read_csv(SEEDS), set(args.company))
    if args.company:
        rows = [r for r in rows if r["company_id"] in args.company]

    done = {}
    if os.path.exists(INDEX):  # resume: keep earlier successes
        done = {r["url"]: r for r in read_csv(INDEX) if r["status"] == "ok"}

    stored = {r["sha256"]: r["local_path"] for r in done.values()}
    seen, out = set(), []
    for row in rows:
        row["url"] = urllib.parse.urldefrag(row["url"])[0]
        if row["url"] in seen:
            continue
        seen.add(row["url"])
        if row["url"] in done:
            out.append(done[row["url"]])
            continue
        result = fetch(row, args.dest, stored)
        print(f"{result['status']:>12}  {row['company_id']:<18} {row['url']}")
        out.append({**{k: row.get(k, "") for k in INDEX_FIELDS}, **result})
        time.sleep(args.delay)

    os.makedirs(os.path.dirname(INDEX), exist_ok=True)
    with open(INDEX, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(out, key=lambda r: (r["company_id"], r["fiscal_year"], r["period"])))
    ok = sum(r["status"] == "ok" for r in out)
    print(f"\n{ok} of {len(out)} documents downloaded; index at {os.path.relpath(INDEX, ROOT)}")


if __name__ == "__main__":
    main()
