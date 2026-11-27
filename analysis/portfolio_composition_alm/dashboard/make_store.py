"""Writes the dashboard's store documents (one JSON file each) to dashboard/store/ for publishing.
The attached-file ids in published.json are the uploads of dashboard/datasets/*.json to the dashboard artifact."""
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
STORE = HERE / "store"
STORE.mkdir(exist_ok=True)
pub = json.loads((HERE / "published.json").read_text())
SRC = "Built from the cdn-life-insurer-alm study (OSFI returns and company filings, fiscal 2025 year-ends). Public data only."
D = {
    "peers": ("Peer summary by insurer", "One row per insurer: General Account size, asset class shares, funding and liability measures. " + SRC),
    "genacct_l3": ("General Account mix, Level 3", "Percent of General Account assets by Level 3 asset class, one row per insurer. " + SRC),
    "par_l3": ("Participating accounts, Level 3", "Percent of each participating account by Level 3 asset class, with the source of each mix. " + SRC),
    "block_classes": ("Par and UL fund mix by class", "Percent of each participating account and UL policyholder fund block by asset class. " + SRC),
    "liabilities": ("Non-par liabilities by product line", "Insurance contract liabilities net of reinsurance, Canada, by product line, from OSFI returns. " + SRC),
    "basis_effect": ("Effect of the General Account basis", "Public equity and private fixed income shares of the whole invested pool and of the General Account. " + SRC),
    "accounting": ("Accounting class of invested assets", "Percent of invested assets at FVTPL, FVOCI and amortized cost, legal entity. " + SRC),
    "trend": ("Change in mix since fiscal 2024", "Change in asset class shares of the invested pool excluding UL funds, fiscal 2024 year-end to the latest filed quarter. " + SRC),
    "off_balance_sheet": ("Repos, securities lending and derivatives", "Repos, securities lending and derivative notionals by insurer. " + SRC),
    "lookthrough": ("Private and alternative assets in filings", "Percent of reported invested assets in private and alternative classes, at each company's reported scope. " + SRC),
    "coverage": ("Coverage, basis and sources", "Basis, period end and source of the General Account mix for each insurer on the standing list."),
}
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
(STORE / "dash_meta.json").write_text(json.dumps({"title": "Peer portfolio composition (ALM basis)", "lang": "en"}))
for k, (title, desc) in D.items():
    doc = {"title": title, "description": desc, "source": {"kind": "file", "url": pub["assets"][k], "name": k + ".json", "format": "json"},
           "updated": {"at": now, "by": "Claude"}, "fixed": True}
    (STORE / f"dataset_{k}.json").write_text(json.dumps(doc))
for f in ["index.html", "charts.js"]:
    (STORE / ("file_" + f + ".json")).write_text(json.dumps({"text": (HERE / f).read_text()}))
print(sorted(p.name for p in STORE.iterdir()), {p.name: p.stat().st_size for p in STORE.glob("file_*")})
