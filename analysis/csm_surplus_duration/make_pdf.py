#!/usr/bin/env python3
"""Print the CSM and surplus duration dashboard as a landscape PDF.

    python3 analysis/csm_surplus_duration/make_pdf.py path/to/d3.min.js [out.pdf]

Runs the dashboard page (dashboard/index.html) unchanged against a small stand-in for the
dashboard runtime that serves the CSVs in dashboard/, shows every tab one after another and
prints with the preinstalled Playwright Chromium (node). d3 v7 is passed in because the page
expects the d3 global. Default output: analysis/csm_surplus_duration/csm-surplus-durations.pdf.
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
OUT = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(HERE, "csm-surplus-durations.pdf")

DATASETS = {
    "results": "results.csv", "breakdown": "portfolio_breakdown.csv", "runoff": "csm_runoff.csv",
    "class_durations": "class_durations.csv", "fvoci": "fvoci.csv", "parameters": "parameters.csv",
}
TABS = {"overview": "Overview", "csm": "CSM portfolio", "surplus": "Surplus portfolio", "classes": "By asset class",
        "net": "Net rate exposure", "fvoci": "FVOCI and OCI limits", "method": "Method and sources"}

TOKENS = """
:root {
  --color-fg: #1f2329; --color-fg-muted: #5d6470; --color-bg: #ffffff; --color-panel: #ffffff;
  --color-border-line: #e1e4e8;
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
.cs-tabs { display: none !important; }
.cs-page { break-before: page; }
#overview { break-before: auto; }
.cs-print-tab { font-family: var(--font-anthropic-serif); font-weight: 400; font-size: 20px; margin: 0 0 4px; }
.cs-card { break-inside: avoid; }
#summary-card, #fvoci-table-card, #sources-card, #params-card { break-inside: auto; }
#summary-card, #fvoci-table-card, #sources-card { break-before: page; }
.cs-tablebox { max-height: none !important; overflow: visible !important; }
.cs th { position: static !important; }
.cs th button::after { content: none !important; }
.cs-hrow { position: static !important; }
.cs-heat { overflow: visible !important; min-height: 0 !important; }
.cs-hgrid { min-width: 0 !important; }
.cs-chart, .cs-chart-lg { min-height: 0 !important; }
.cs-tip { display: none !important; }
.cs td.cs-w { min-width: 0 !important; }
.cs table { table-layout: fixed; }
.cs td { overflow-wrap: anywhere; }
.cs-grid { grid-template-columns: 1fr 1fr; }
"""

RUNTIME = """
window.__data = %(data)s;
window.__draws = {};
window.__params = {};
window.dash = {
  colors: ['#1f5fa8', '#e09a2c', '#3a9d8f', '#c4524d', '#8a7fb8', '#6b8e23', '#d16ba5', '#7f7f7f'],
  data(id) { const rows = window.__data[id]; return rows ? { status: 'ok', data: rows, columns: rows.length ? Object.keys(rows[0]) : [], meta: [] } : { status: 'missing', data: [] }; },
  calc(id, spec) { window.__data[id] = spec.fn(...spec.inputs.map((i) => window.__data[i])); },
  draw(name, fn) {
    if (typeof fn === 'function') window.__draws[name] = fn;
    else if (!fn) document.querySelectorAll(`[data-draw="${name}"]`).forEach((el) => window.__draws[name] && window.__draws[name](el));
  },
  onData(fn) {}, setLink() {}, params() { return window.__params; }, setParams() {}, resetParams() {}, refresh() {},
};
"""

FINISH = """
<script>
  const tabs = %(tabs)s;
  document.querySelectorAll('[data-page]').forEach((s) => {
    s.hidden = false;
    const h = document.createElement('h2'); h.className = 'cs-print-tab'; h.textContent = tabs[s.dataset.page] || ''; s.prepend(h);
  });
  document.querySelectorAll('[data-draw]').forEach((el) => { const f = window.__draws[el.dataset.draw]; if (f) f(el); });
  document.body.dataset.ready = '1';
</script>
"""

NODE = """
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1120, height: 800 } });
  p.on('pageerror', (e) => { console.error('page error:', e.message); process.exitCode = 1; });
  await p.goto('file://' + process.argv[2]);
  await p.waitForSelector('body[data-ready="1"]', { timeout: 60000 });
  await p.pdf({ path: process.argv[3], format: 'A4', landscape: true, printBackground: true, preferCSSPageSize: true });
  if (process.argv[4]) await p.screenshot({ path: process.argv[4], fullPage: true });
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
        "<!doctype html><html><head><meta charset='utf-8'><title>CSM and surplus durations</title>"
        f"<style>{TOKENS}</style><script>{d3}</script>"
        f"<script>{RUNTIME % {'data': json.dumps(data)}}</script></head><body>"
        f"<div id='dash-root'>{page}</div>"
        + FINISH % {"tabs": json.dumps(TABS)}
        + "</body></html>"
    )
    shot = os.environ.get("CS_SCREENSHOT", "")
    with tempfile.TemporaryDirectory() as tmp:
        html_path = os.path.join(tmp, "print.html")
        js_path = os.path.join(tmp, "print.js")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(doc)
        with open(js_path, "w", encoding="utf-8") as f:
            f.write(NODE)
        subprocess.run(["node", js_path, html_path, OUT] + ([shot] if shot else []), check=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
