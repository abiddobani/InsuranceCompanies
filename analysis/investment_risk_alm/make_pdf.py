#!/usr/bin/env python3
"""Print the peer investment risk dashboard, every tab, as a PDF.

    python3 analysis/investment_risk_alm/make_pdf.py path/to/d3.min.js [out.pdf]

Runs the dashboard page (dashboard/index.html) unchanged against a small stand-in for the
dashboard runtime that serves the CSVs in dashboard/, shows all tabs one after another and
prints with the preinstalled Playwright Chromium (node). d3 v7 is passed in because the page
expects the d3 global. Default output: analysis/investment_risk_alm/peer-investment-risk-benchmark.pdf.
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
    "landscape": "landscape.csv", "peerStats": "peer_stats.csv", "facts": "facts.csv", "licatMix": "licat_mix.csv",
    "assetMix": "asset_mix.csv", "sens": "sensitivities.csv", "sectors": "sectors.csv", "encumbrance": "encumbrance.csv",
    "licatTrend": "licat_trend.csv", "capitalPath": "rbc_capital_path.csv", "rotation": "rbc_rotation.csv",
    "changes": "changes.csv", "coverage": "coverage.csv", "outside": "outside_study.csv",
}
TABS = [("overview", "Overview"), ("capital", "Risk capital"), ("market", "Market risk"), ("credit", "Credit risk"),
        ("liquidity", "Liquidity and funding"), ("method", "Method and coverage")]

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
#dash-root { width: 1160px; margin: 0 auto; padding: 4px 0 16px; }
.ir, .ir-page { display: block !important; }
.ir > *, .ir-page > * { margin-bottom: 12px; }
@page { size: A4 landscape; margin: 10mm; }
.ir-tabs { display: none !important; }
.ir-page { break-before: page; }
#overview { break-before: auto; }
.ir-print-tab { font-family: var(--font-anthropic-serif); font-weight: 400; font-size: 20px; margin: 0 0 4px; }
.ir-card { break-inside: avoid; }
#sens-table { break-inside: auto; }
.ir-card h2, .ir-card h3, .ir-card .ir-note, .ir-legend, .ir-print-tab { break-after: avoid; }
.ir-hcell { height: 1.55rem !important; }
.ir tr { break-inside: avoid; }
.ir-tablebox { max-height: none !important; overflow: visible !important; }
.ir th { position: static !important; }
.ir-hrow { position: static !important; }
.ir-chart, .ir-chart-lg, .ir-chart-sm, .ir-heat, .ir-heat-sm { min-height: 0 !important; }
.ir-heat { overflow: visible !important; }
.ir-tip { display: none !important; }
"""

RUNTIME = """
window.__data = %(data)s;
window.__draws = {};
window.irDense = true;
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
  const tabs = %(tabs)s;
  document.querySelectorAll('[data-page]').forEach((s) => {
    s.hidden = false;
    const h = document.createElement('h2');
    h.className = 'ir-print-tab';
    h.textContent = tabs[s.dataset.page] || '';
    s.prepend(h);
  });
  Object.keys(window.__draws).forEach((n) => dash.draw(n));
  window.__left = Array.from(document.querySelectorAll('[data-draw]')).filter((el) => el.textContent.trim() === '\\u2014').map((el) => el.dataset.draw + ':' + (el.dataset.key || el.dataset.metric || el.dataset.risk || ''));
  document.body.dataset.ready = '1';
</script>
"""

NODE = """
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  const errors = [];
  p.on('pageerror', (e) => errors.push(String(e)));
  p.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await p.goto('file://' + process.argv[2]);
  await p.waitForSelector('body[data-ready="1"]', { timeout: 15000 }).catch(() => {});
  const left = await p.evaluate(() => window.__left || ['page did not finish']);
  if (errors.length || left.length) { console.error(JSON.stringify({ errors, undrawn: left })); }
  await p.pdf({ path: process.argv[3], format: 'A4', landscape: true, printBackground: true, preferCSSPageSize: true });
  await b.close();
  if (errors.length || left.length) process.exit(1);
})();
"""


def read(name):
    with open(os.path.join(DASH, name), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def build_html():
    data = {k: read(v) for k, v in DATASETS.items()}
    with open(os.path.join(DASH, "index.html"), encoding="utf-8") as f:
        page = f.read()
    with open(D3, encoding="utf-8") as f:
        d3 = f.read()
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Peer investment risk benchmark</title>"
        f"<style>{TOKENS}</style><script>{d3}</script>"
        f"<script>{RUNTIME % {'data': json.dumps(data)}}</script></head><body>"
        f"<div id='dash-root'>{page}</div>"
        + FINISH % {"tabs": json.dumps(dict(TABS))}
        + "</body></html>"
    )


def main():
    doc = build_html()
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
