#!/usr/bin/env python3
"""Print the peer investment risk dashboard, every tab and every sensitivity view, as a PDF.

    python3 analysis/investment_risk/make_pdf.py path/to/d3.min.js [out.pdf]

Runs the dashboard page (dashboard/index.html) unchanged against a small stand-in for the
dashboard runtime that serves the CSVs in dashboard/, shows all five tabs one after another,
draws the sensitivity chart once per shock and measure, and prints with the preinstalled
Playwright Chromium (node). d3 v7 is passed in because the page expects the d3 global.
Default output: analysis/investment_risk/peer-investment-risk-benchmark.pdf.
"""
import csv
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.join(HERE, "dashboard")
D3 = os.path.abspath(sys.argv[1])
OUT = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(HERE, "peer-investment-risk-benchmark.pdf")

DATASETS = {
    "landscape": "landscape.csv", "sens": "sensitivities.csv", "ratings": "bond_ratings.csv",
    "tiers": "liquidity_tiers.csv", "sectors": "sector_mix.csv", "coverage": "coverage.csv",
    "ear": "earnings_at_risk.csv",
}
TABS = [("overview", "Overview"), ("market", "Market risk"), ("credit", "Credit risk"),
        ("liquidity", "Liquidity risk"), ("disclosure", "Disclosure map")]
FACTORS = ["Rates +50 bp", "Rates -50 bp", "Credit spreads +50 bp", "Public equity -10%",
           "Real estate and alternatives -10%"]
MEASURES = [("ni_bps_invested", "Earnings impact, bps of invested assets"),
            ("licat_pts", "Capital ratio impact, points")]

TOKENS = """
:root {
  --color-fg: #1f2329; --color-fg-muted: #5d6470; --color-bg: #ffffff; --color-panel: #ffffff;
  --color-border-line: #e1e4e8; --color-ok: #2e7d4f; --color-warn: #a86b00; --color-bad: #b3261e;
  --font-anthropic-sans: "Helvetica Neue", Arial, "Liberation Sans", sans-serif;
  --font-anthropic-serif: Georgia, "Times New Roman", "Liberation Serif", serif;
  --cds-font-size-caption: 10.5px; --cds-font-size-body: 12.5px; --cds-font-size-heading: 14px; --cds-font-size-title: 24px;
  --cds-font-weight-medium: 600; --cds-gap-xs: 4px; --cds-gap-sm: 8px; --cds-gap-md: 12px; --cds-gap-lg: 18px; --cds-gap-xl: 24px;
  --cds-pad-xs: 3px; --cds-pad-sm: 6px; --cds-pad-md: 10px; --cds-pad-lg: 14px; --cds-radius: 6px;
  --cds-chart-muted: #b9bec7; --cds-chart-grid: #eceef1; --cds-chart-axis: #9aa1ab; --cds-chart-reference: #3b4048;
  --cds-surface-popover: #fff; --cds-border: #e1e4e8; --cds-shadow-popover: none; --cds-text-secondary: #5d6470;
  --cds-dur-slow: 0s; --cds-ease-out: linear;
}
html, body { margin: 0; background: #fff; color: var(--color-fg); }
#dash-root { width: 1080px; margin: 0 auto; padding: 8px 0 24px; }
@page { size: A4 landscape; margin: 10mm; }
.ir-tabs, .ir-toggle { display: none !important; }
.ir-page { break-before: page; }
#overview { break-before: auto; }
.ir-sens-grid > div { break-inside: avoid; }
.ir-sens-measure ~ .ir-sens-measure { break-before: page; }
.ir-print-tab { font-family: var(--font-anthropic-serif); font-weight: 400; font-size: 20px; margin: 0 0 4px; }
.ir-card { break-inside: avoid; }
#landscape-table, #sens-table, #sectors, #coverage { break-inside: auto; }
.ir-tablebox { max-height: none !important; overflow: visible !important; }
.ir th { position: static !important; }
.ir-hrow { position: static !important; }
.ir-sens-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 18px; }
.ir-sens-grid h3 { font-size: 12px; font-weight: 600; margin: 6px 0 2px; }
.ir-sens-measure { grid-column: 1 / -1; font-size: 13px; font-weight: 600; margin: 8px 0 0; }
.ir-chart, .ir-chart-lg { min-height: 0 !important; }
.ir-tip { display: none !important; }
"""

RUNTIME = """
window.__data = %(data)s;
window.__draws = {};
window.dash = {
  colors: ['#1f5fa8', '#e09a2c', '#3a9d8f', '#c4524d', '#8a7fb8', '#6b8e23', '#d16ba5', '#7f7f7f'],
  data(id) { const rows = window.__data[id]; return rows ? { status: 'ok', data: rows, columns: rows.length ? Object.keys(rows[0]) : [], meta: [] } : { status: 'missing', data: [] }; },
  calc(id, spec) { window.__data[id] = spec.fn(...spec.inputs.map((i) => window.__data[i])); },
  draw(name, fn) {
    if (typeof fn === 'function') window.__draws[name] = fn;
    else if (!fn) document.querySelectorAll(`[data-draw="${name}"]`).forEach((el) => window.__draws[name] && window.__draws[name](el));
  },
  onData(fn) {}, setLink() {}, params() { return {}; }, setParams() {}, resetParams() {}, refresh() {},
};
"""

FINISH = """
<script>
  const tabs = %(tabs)s, factors = %(factors)s, measures = %(measures)s;
  document.querySelectorAll('[data-page]').forEach((s) => {
    s.hidden = false;
    const h = document.createElement('h2');
    h.className = 'ir-print-tab';
    h.textContent = tabs[s.dataset.page] || '';
    s.prepend(h);
  });
  const sensChart = document.querySelector('[data-draw="sens"]');
  if (sensChart) {
    const grid = document.createElement('div');
    grid.className = 'ir-sens-grid';
    measures.forEach(([m, mLabel]) => {
      const mh = document.createElement('div'); mh.className = 'ir-sens-measure'; mh.textContent = mLabel; grid.append(mh);
      factors.forEach((f) => {
        const cell = document.createElement('div');
        const h = document.createElement('h3'); h.textContent = f.replace('-', '\\u2212'); cell.append(h);
        const c = document.createElement('div'); c.className = 'ir-chart'; c.dataset.sensFactor = f; c.dataset.sensMeasure = m;
        cell.append(c); grid.append(cell);
      });
    });
    sensChart.replaceWith(grid);
  }
  Object.keys(window.__draws).forEach((n) => { if (n !== 'sens') dash.draw(n); });
  document.querySelectorAll('[data-sens-factor].ir-chart').forEach((el) => {
    window.irSens = { factor: el.dataset.sensFactor, measure: el.dataset.sensMeasure };
    window.__draws.sens(el);
  });
  document.body.dataset.ready = '1';
</script>
"""

NODE = """
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1120, height: 800 } });
  await p.goto('file://' + process.argv[2]);
  await p.waitForSelector('body[data-ready="1"]');
  await p.pdf({ path: process.argv[3], format: 'A4', landscape: true, printBackground: true, preferCSSPageSize: true });
  await b.close();
})();
"""


def read(name):
    with open(os.path.join(DASH, name), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main():
    data = {k: read(v) for k, v in DATASETS.items()}
    with open(os.path.join(DASH, "index.html"), encoding="utf-8") as f:
        page = f.read()
    with open(D3, encoding="utf-8") as f:
        d3 = f.read()
    doc = (
        "<!doctype html><html><head><meta charset='utf-8'><title>Peer investment risk benchmark</title>"
        f"<style>{TOKENS}</style><script>{d3}</script>"
        f"<script>{RUNTIME % {'data': json.dumps(data)}}</script></head><body>"
        f"<div id='dash-root'>{page}</div>"
        + FINISH % {"tabs": json.dumps(dict(TABS)), "factors": json.dumps(FACTORS), "measures": json.dumps(MEASURES)}
        + "</body></html>"
    )
    with tempfile.TemporaryDirectory() as tmp:
        html_path = os.path.join(tmp, "print.html")
        js_path = os.path.join(tmp, "print.js")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(doc)
        with open(js_path, "w", encoding="utf-8") as f:
            f.write(NODE)
        subprocess.run(["node", js_path, html_path, OUT], check=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
