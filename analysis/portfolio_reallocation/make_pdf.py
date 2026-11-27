#!/usr/bin/env python3
"""Print the peer portfolio reallocation dashboard as a landscape PDF.

    python3 analysis/portfolio_reallocation/make_pdf.py path/to/d3.min.js [out.pdf]

Runs the dashboard page (dashboard/index.html) unchanged against a small stand-in for the
dashboard runtime that serves the CSVs in dashboard/. It prints the overview, RBC Life's own
mix, flows and IFRS 17 detail, the by-class page once for each asset class, the mix of every
other peer as an appendix, and the series-break pages, using the preinstalled Playwright
Chromium (node). d3 v7 is passed in because the page expects the d3 global.
Default output: analysis/portfolio_reallocation/peer-portfolio-reallocations.pdf.
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
OUT = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(HERE, "peer-portfolio-reallocations.pdf")

DATASETS = {
    "mix": "mix_history.csv", "changes": "changes.csv", "cumulative": "cumulative.csv",
    "detail": "detail_ifrs17.csv", "flags": "flags.csv", "bridge": "ifrs17_bridge.csv",
    "bridge_class": "ifrs17_bridge_by_class.csv", "coverage": "coverage.csv",
    "quality": "bond_quality.csv", "market": "market_context.csv",
}
TABS = {"overview": "Overview", "mix": "RBC Life: mix over time", "flows": "RBC Life: quarterly flows",
        "classes": "By asset class", "detail": "IFRS 17 detail: RBC Life", "breaks": "Series breaks"}
CLASSES = ["Cash & short-term", "Bonds", "Mortgages & loans", "Equities", "Real estate", "Other invested assets"]

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
.rr-tabs, .rr-toggle, .rr-bar { display: none !important; }
.rr-page { break-before: page; }
#overview { break-before: auto; }
.rr-print-tab { font-family: var(--font-anthropic-serif); font-weight: 400; font-size: 20px; margin: 0 0 4px; }
.rr-card { break-inside: avoid; }
#flags-card, #coverage-card { break-inside: auto; }
.rr-tablebox { max-height: none !important; overflow: visible !important; }
.rr th { position: static !important; }
.rr-hrow { position: static !important; }
.rr-heat { overflow: visible !important; min-height: 0 !important; }
.rr-hgrid { min-width: 0 !important; }
.rr-chart, .rr-chart-lg, .rr-chart-sm { min-height: 0 !important; }
.rr-tip { display: none !important; }
.rr-appx { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 18px; }
.rr-appx .rr-card { padding: 10px; }
.rr-appx .rr-card:nth-child(4n+1) { break-before: page; }
.rr-appx .rr-card:first-child { break-before: auto; }
.rr-class-print + .rr-class-print { break-before: page; }
.rr-class-print .rr-grid { grid-template-columns: 1fr 1fr; }
#breaks .rr-grid { grid-template-columns: 1fr 1fr; }
#overview .rr-grid, #detail .rr-grid { display: flex; flex-direction: column; }
#heat-card, #rbc-vs-peers, #detail-big, #detail-peers { break-before: page; }
#market-card { break-before: page; }
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
  const tabs = %(tabs)s, classes = %(classes)s;
  const drawIn = (root, params) => {
    window.__params = params;
    root.querySelectorAll('[data-draw]').forEach((el) => { const f = window.__draws[el.dataset.draw]; if (f) f(el); });
  };
  document.querySelectorAll('[data-page]').forEach((s) => {
    s.hidden = false;
    const h = document.createElement('h2'); h.className = 'rr-print-tab'; h.textContent = tabs[s.dataset.page] || ''; s.prepend(h);
  });
  // one by-class page per asset class
  const cls = document.getElementById('classes');
  const body = [...cls.children].filter((c) => !c.classList.contains('rr-print-tab'));
  const holder = document.createElement('div');
  classes.forEach((c) => {
    const part = document.createElement('div'); part.className = 'rr-class-print'; part.dataset.cls = c;
    const h = document.createElement('h2'); h.className = 'rr-print-tab'; h.textContent = 'By asset class: ' + c; part.append(h);
    body.forEach((b) => part.append(b.cloneNode(true)));
    holder.append(part);
  });
  body.forEach((b) => b.remove());
  cls.querySelector('.rr-print-tab').remove();
  cls.append(...holder.children);
  // appendix: every other insurer's mix
  const names = window.__data.coverage.filter((r) => +r.points > 0 && r.company_id !== 'rbc_life');
  const appx = document.createElement('section'); appx.className = 'rr-page'; appx.id = 'appendix';
  const ah = document.createElement('h2'); ah.className = 'rr-print-tab'; ah.textContent = 'Appendix: share of invested assets by class, every other peer'; appx.append(ah);
  const legend = document.querySelector('#mix-share [data-draw="class-legend"]').cloneNode(true); appx.append(legend);
  const grid = document.createElement('div'); grid.className = 'rr-appx'; appx.append(grid);
  names.forEach((r) => {
    const card = document.createElement('div'); card.className = 'rr-card'; card.dataset.co = r.company_id;
    const h = document.createElement('h2'); h.textContent = r.company + (r.frequency === 'Annual' ? ' (yearly)' : ''); card.append(h);
    const c = document.createElement('div'); c.className = 'rr-chart'; c.dataset.draw = 'mix-area'; c.dataset.h = '250'; card.append(c);
    grid.append(card);
  });
  document.getElementById('breaks').before(appx);

  drawIn(document, { co: 'rbc_life', cls: 'Equities', fm: 'cad' });
  document.querySelectorAll('.rr-class-print').forEach((p) => drawIn(p, { co: 'rbc_life', cls: p.dataset.cls, fm: 'cad' }));
  grid.querySelectorAll('.rr-card').forEach((card) => drawIn(card, { co: card.dataset.co, cls: 'Equities', fm: 'cad' }));
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
        "<!doctype html><html><head><meta charset='utf-8'><title>Peer portfolio reallocations</title>"
        f"<style>{TOKENS}</style><script>{d3}</script>"
        f"<script>{RUNTIME % {'data': json.dumps(data)}}</script></head><body>"
        f"<div id='dash-root'>{page}</div>"
        + FINISH % {"tabs": json.dumps(TABS), "classes": json.dumps(CLASSES)}
        + "</body></html>"
    )
    shot = os.environ.get("RR_SCREENSHOT", "")
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
