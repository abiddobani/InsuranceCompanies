// Renders the PDF report from the same page and chart code as the dashboard.
// Usage: node report/render.js [out.pdf]   (run from analysis/portfolio_composition_alm)
// The dashboard runtime (dash.data, dash.draw, dash.calc, dash.colors) is replaced by a small shim fed from dashboard/datasets.
const fs = require('fs');
const path = require('path');
const {execFileSync} = require('child_process');
const {chromium} = require('playwright');

const here = path.resolve(__dirname, '..');
const out = path.resolve(process.argv[2] || path.join(here, 'report', 'peer-portfolio-composition-alm-basis.pdf'));
const cache = path.join(here, 'report', '.cache');
const d3file = path.join(cache, 'd3.min.js');
if (!fs.existsSync(d3file)) {
  fs.mkdirSync(cache, {recursive: true});
  execFileSync('curl', ['-fsSL', '-o', d3file, 'https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js']);
}
const read = (...p) => fs.readFileSync(path.join(here, ...p), 'utf8');
const data = {};
for (const f of fs.readdirSync(path.join(here, 'dashboard', 'datasets'))) {
  if (f.endsWith('.json') && !f.startsWith('_')) data[f.replace('.json', '')] = JSON.parse(read('dashboard', 'datasets', f));
}
const meta = JSON.parse(read('out', 'data.json')).meta;
const page = read('dashboard', 'index.html').replace(/<meta[^>]*>\s*/g, '').replace(/<script src="charts.js"><\/script>/, '')
  .replace('<div class="pc">', '<div class="pc" data-dense>');
const shim = `
  window.dash = (() => {
    const data = ${JSON.stringify(data)}, calcs = {}, draws = [];
    return {
      colors: ['#257de0', '#f47230', '#00b894', '#f2a600', '#ee7fac', '#008a17', '#6a4ce2', '#ec4647'],
      data(id) {
        if (calcs[id]) return {status: 'ok', data: calcs[id].fn(...calcs[id].inputs.map((i) => data[i]))};
        return data[id] ? {status: 'ok', data: data[id]} : {status: 'missing', data: []};
      },
      calc(id, def) { calcs[id] = def; },
      draw(name, fn) { draws.push([name, fn]); },
      onData(fn) { fn(); },
      params: () => ({}),
      setLink() {},
      run() { draws.forEach(([name, fn]) => document.querySelectorAll('[data-draw="' + name + '"]').forEach((el) => fn(el))); },
    };
  })();`;
const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Peer portfolio composition, ALM basis</title>
</head><body>
<div id="dash-root">${page}</div>
<style>${read('report', 'report.css')}</style>
<script>${fs.readFileSync(d3file, 'utf8')}</script><script>${shim}</script><script>${read('dashboard', 'charts.js')}</script>
<script>document.querySelectorAll('details').forEach((d) => { d.open = true; }); dash.run();</script></body></html>`;

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({viewport: {width: 1090, height: 820}, deviceScaleFactor: 2});
  const pg = await ctx.newPage();
  const errors = [];
  pg.on('pageerror', (e) => errors.push(String(e)));
  pg.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await pg.setContent(html, {waitUntil: 'load'});
  await pg.emulateMedia({media: 'screen'});
  if (process.env.SHOTS) {
    fs.mkdirSync(process.env.SHOTS, {recursive: true});
    const ids = await pg.$$eval('.pc-head, .pc-sec', (els) => els.map((e) => e.id));
    for (const id of ids) await (await pg.$('#' + id)).screenshot({path: path.join(process.env.SHOTS, id + '.png')});
  }
  const foot = `<div style="width:100%;padding:0 0.5in;font:7.5pt Inter,Arial,sans-serif;color:#666;display:flex;justify-content:space-between">
    <span>Peer portfolio composition, ALM study basis (cdn-life-insurer-alm @ ${meta.alm_commit}). Public data only; estimates tagged est.</span>
    <span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`;
  await pg.pdf({path: out, width: '11in', height: '8.5in', printBackground: true, scale: 0.88, displayHeaderFooter: true, headerTemplate: '<span></span>',
    footerTemplate: foot, margin: {top: '0.45in', bottom: '0.55in', left: '0.5in', right: '0.5in'}});
  await browser.close();
  if (errors.length) { console.error(errors.join('\n')); process.exit(1); }
  console.log('wrote', out);
})();
