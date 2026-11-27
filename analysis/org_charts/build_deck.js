// Insurer org charts, version 2 (2026-11-27): rebuilt on the MooseDragon/cdn-life-insurer-alm lens.
// Three slides per insurer, identical layout: (1) org chart from the top executive with the ALM-chain seats tagged,
// (2) investment team from the CIO down, (3) the six ALM-chain seats against the balance sheet they manage.
// Usage: NODE_PATH=<node_modules with pptxgenjs> PPTX_SKILL_DIR=<pptx skill> node build_deck.js <out.pptx>
// Inputs: data/<id>.txt, data/inv/<id>.txt (people), data/functions.json (make_functions.py), data/alm_context.json (alm_context.py).
// Every count used in a title is computed below and asserted; nothing on a slide is typed in twice.
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");
const { load } = require("./parse");
const SKILL = process.env.PPTX_SKILL_DIR;
const { applyTheme } = require(path.join(SKILL, "scripts/apply_theme.js"));

const OUT = process.argv[2] || "org-charts.pptx";
const ASOF = "27 November 2026";
const LI_ASOF = "6 November 2026";

// Order follows the ALM repo: RBC Life first (subject), then its tiers, each by General Account size.
const TIERS = [
  ["RBC Life", ["rbc_life"]],
  ["Bank-owned", ["bmo_life"]],
  ["Big 3", ["sun_life", "manulife", "canada_life"]],
  ["Non-Big 3", ["ia", "beneva", "empire_life", "ivari", "cooperators_life", "equitable_life", "foresters_life", "canada_protection_plan", "wawanesa_life", "desjardins"]],
  ["Outside the ALM repo's peer views", ["primerica_life", "canadian_premier", "assumption_life", "humania", "uv_insurance"]],
];
const ORDER = TIERS.flatMap(t => t[1]);
const SHORTNAME = { rbc_life: "RBC Life", bmo_life: "BMO Life", sun_life: "Sun Life", manulife: "Manulife", canada_life: "Canada Life", ia: "iA",
  beneva: "Beneva", empire_life: "Empire Life", ivari: "ivari", cooperators_life: "Co-operators Life", equitable_life: "Equitable", foresters_life: "Foresters Life",
  canada_protection_plan: "Canada Protection Plan", wawanesa_life: "Wawanesa Life", desjardins: "Desjardins (DFS)", primerica_life: "Primerica Life Canada",
  canadian_premier: "Canadian Premier Life", assumption_life: "Assumption Life", humania: "Humania", uv_insurance: "UV Insurance" };

// Brand palette copied from the ALM repo's style/brand_style.py (brand hex codes only; red for risk / negative only).
const PAL = { COOLWHITE: "E7EEF1", BRIGHTBLUE: "0051A5", WARMYELLOW: "FFC72C", OCEAN: "0091DA", SKY: "51B5E0", DARKBLUE: "003168", TUNDRA: "87AFBF",
  SEAWEED: "588886", APPLE: "AABA0A", SUNBURST: "FCA311", SAND: "B58500", SLATEGRAY: "6F6E6F", CARBON: "899299", GRAY: "9EA2A2", RISKRED: "B54241" };
const tint = (hex, level) => [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16)).map(v => Math.round(255 - (255 - v) * level)).map(v => v.toString(16).padStart(2, "0")).join("").toUpperCase();
const BB = PAL.BRIGHTBLUE, DB = PAL.DARKBLUE, SLATE = PAL.SLATEGRAY, GRAY = PAL.GRAY;
const HEX = { navy: DB, ink: DB, grey: SLATE, faint: PAL.CARBON, line: tint(GRAY, 0.55), tint: PAL.COOLWHITE, hl: BB, hlTint: tint(BB, 0.10), ghost: tint(GRAY, 0.10) };
const CERT = { H: PAL.SEAWEED, M: PAL.SAND, L: PAL.RISKRED, "-": GRAY };
const CERT_LIGHT = { H: tint(PAL.APPLE, 0.7), M: PAL.WARMYELLOW, L: tint(PAL.RISKRED, 0.55), "-": PAL.COOLWHITE };
// liability-mix palette: validated with the dataviz skill's validate_palette.js (light surface, adjacent order as drawn)
const LINES = [["Individual insurance", BB], ["Individual annuity", PAL.SAND], ["Group insurance", PAL.OCEAN], ["Group annuity", PAL.APPLE]];

const THEME = { name: "Insurer org charts", headFontFace: "Calibri", bodyFontFace: "Calibri",
  colors: { dk1: DB, lt1: "FFFFFF", dk2: DB, lt2: PAL.COOLWHITE, accent1: BB, accent2: PAL.OCEAN, accent3: PAL.SEAWEED, accent4: PAL.SAND, accent5: GRAY, accent6: PAL.WARMYELLOW, hlink: BB, folHlink: DB } };

const W = 13.333, H = 7.5, MX = 0.45;
const GRID = { x: MX, y: 2.12, cols: 6, rows: 3, gap: 0.1 };
GRID.w = (W - 2 * MX - GRID.gap * (GRID.cols - 1)) / GRID.cols;
GRID.h = (6.78 - GRID.y - GRID.gap * (GRID.rows - 1)) / GRID.rows;

const data = load(path.join(__dirname, "data"));
const inv = load(path.join(__dirname, "data", "inv"));
const FN = JSON.parse(fs.readFileSync(path.join(__dirname, "data", "functions.json"), "utf8"));
const CTX = JSON.parse(fs.readFileSync(path.join(__dirname, "data", "alm_context.json"), "utf8"));
ORDER.forEach(id => { if (!data[id] || !inv[id] || !FN.insurers[id] || !CTX[id]) throw new Error("missing data for " + id); });
if (ORDER.length !== 20) throw new Error("the peer set is 20 insurers");
const assert = (c, m) => { if (!c) throw new Error("Title check failed: " + m); };
const ND = /^Not publicly/;

// ---------- ALM-chain tags on the org chart (read from the title; overrides below) ----------
const TAG_RULES = [
  ["Investments", /Chief Investment Officer|VP, Investments|Investment & Special Projects|Investments & ALM|manages the general account|oversees investments|Louisbourg Investments|President, Sun Life Asset Management/],
  ["ALM", /\bALM\b|Asset Liability/],
  ["Actuarial", /Actuar/],
  ["Finance", /Financial Officer|\bCFO\b|Finance\b/],
  ["Risk", /Risk Officer|Chief Risk|risk management\)/],
];
const TAG_OVERRIDE = { "wawanesa_life|James Bond": [], "desjardins|Pierre-Alexandre Braeken": [], "bmo_life|Not publicly named": ["Risk"] };
function tagsOf(id, p, kind) {
  const k = id + "|" + p.name;
  if (TAG_OVERRIDE[k]) return TAG_OVERRIDE[k];
  if (kind === "inv") return [["ALM", /\bALM\b|Asset Liability/], ["Investment risk", /Risk/]].filter(([, re]) => re.test(p.title)).map(r => r[0]);
  return TAG_RULES.filter(([, re]) => re.test(p.title)).map(r => r[0]);
}

// rough text-height model for Calibri (inches)
const cpl = (wIn, pt) => Math.floor((wIn * 72) / (pt * 0.43));
const lines = (s, wIn, pt) => Math.max(1, Math.ceil(s.length / cpl(wIn, pt)));
const TW = GRID.w - 0.14;
function cardHeight(p, maxItems = 99) {
  let h = 0.08 + (p.tags && p.tags.length ? 0.115 : 0) + lines("H " + p.name, TW, 10) * 0.165 + lines(p.title, TW, 8.5) * 0.13 + 0.05;
  p.l3.slice(0, maxItems).forEach(q => { h += lines(`L ${q.name} – ${q.title}`, TW, 7.5) * 0.118 + 0.03; });
  return h + 0.04;
}

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "Canadian L&H insurer org charts: the ALM chain";
pres.author = "Prepared for Abid Dobani";

const FOOT = `As of ${ASOF} · public sources only · sources in speaker notes`;
const footObj = { text: { text: FOOT, options: { x: 8.75, y: 7.05, w: 3.7, h: 0.25, fontSize: 8, color: HEX.faint, align: "right", margin: 0 } } };
const num = { x: 12.55, y: 7.05, w: 0.35, h: 0.25, fontSize: 8, color: HEX.faint, align: "right" };
pres.defineSlideMaster({ title: "ORG", background: { color: "FFFFFF" }, objects: [footObj], slideNumber: num });
pres.defineSlideMaster({ title: "CONTENT", background: { color: "FFFFFF" }, objects: [footObj,
  { placeholder: { options: { name: "title", type: "title", x: MX, y: 0.5, w: W - 2 * MX, h: 0.8, fontSize: 22, bold: true, color: DB, valign: "top", align: "left", margin: 0 }, text: "" } }], slideNumber: num });
pres.defineSlideMaster({ title: "DARK", background: { color: DB } });

const T = (s, text, o) => s.addText(text, Object.assign({ isTextBox: true, margin: 0, color: HEX.ink, fontSize: 10.5, valign: "top" }, o));
function certRun(c, size, light) { return { text: (c === "-" ? "–" : c) + " ", options: { bold: true, color: (light ? CERT_LIGHT : CERT)[c] || CERT["-"], fontSize: size } }; }
function legend(slide, extra) {
  const items = [["H", "insurer's own site, filing or release"], ["M", "LinkedIn profile, trade press"], ["L", "snippet, aggregator, undated"]];
  const runs = [];
  items.forEach(([c, t], i) => { runs.push(certRun(c, 8)); runs.push({ text: t + (i < 2 ? "   " : ""), options: { color: HEX.grey, fontSize: 8 } }); });
  runs.push({ text: "   ·   Dashed / italic = inferred   ·   " + extra, options: { color: HEX.grey, fontSize: 8 } });
  T(slide, runs, { x: MX, y: 7.0, w: 8.2, h: 0.35, valign: "middle", objectName: "Legend" });
}
let section = "";
function addSlide(master, sect) {
  if (sect !== section) { pres.addSection({ title: sect }); section = sect; }
  return pres.addSlide({ masterName: master, sectionTitle: sect });
}
function eyebrow(s, left, right) {
  T(s, left.toUpperCase(), { x: MX, y: 0.25, w: 8, h: 0.22, fontSize: 9, bold: true, color: SLATE, charSpacing: 1, objectName: "Eyebrow" });
  if (right) T(s, right, { x: 7.4, y: 0.25, w: W - MX - 7.4, h: 0.22, fontSize: 9, color: SLATE, align: "right", objectName: "Eyebrow right" });
}
const srcText = (id, keys) => keys.map(k => {
  if (k.startsWith("org:")) { const s = data[id].srcs[k.slice(4)]; if (!s) throw new Error(`${id}: no org source ${k}`); return `${s.label} — ${s.url}`; }
  if (k.startsWith("inv:")) { const s = inv[id].srcs[k.slice(4)]; if (!s) throw new Error(`${id}: no inv source ${k}`); return `${s.label} — ${s.url}`; }
  const s = FN.sources[k]; return s[1] ? `${s[0]} — ${s[1]}` : s[0];
});

// ---------- slides 1 and 2: org chart and investment team ----------
const tagLog = [];
function orgSlide(id, kind, sect) {
  const d = kind === "inv" ? inv[id] : data[id];
  const isI = kind === "inv";
  d.l2.forEach(p => { p.tags = tagsOf(id, p, kind); if (p.tags.length && !isI) tagLog.push(`${id}: ${p.name} -> ${p.tags.join(" + ")}`); });
  const slide = addSlide("ORG", sect);
  T(slide, isI ? [{ text: d.name, options: {} }, { text: "  ·  investment team", options: { color: BB } }] : d.name, { x: MX, y: 0.28, w: 9.5, h: 0.5, fontSize: 24, bold: true, color: HEX.ink, objectName: "Title" });
  T(slide, d.anchor, { x: MX, y: 0.78, w: 12.4, h: 0.28, fontSize: 10.5, color: HEX.grey, objectName: "Anchor" });
  const all = [d.l1, ...d.l2, ...d.l2.flatMap(p => p.l3)].filter(p => !ND.test(p.name));
  const cnt = c => all.filter(p => p.cert === c).length;
  const n2 = d.l2.filter(p => !ND.test(p.name)).length, n3 = d.l2.reduce((a, p) => a + p.l3.filter(q => !ND.test(q.name)).length, 0);
  T(slide, [{ text: (isI ? `Slide 2 of 3 · ${n2} CIO directs · ${n3} below them named    ` : `Slide 1 of 3 · ${n2} level-2 · ${n3} level-3 named    `), options: { color: HEX.grey } },
    certRun("H", 9), { text: cnt("H") + "   ", options: { color: HEX.grey } }, certRun("M", 9), { text: cnt("M") + "   ", options: { color: HEX.grey } }, certRun("L", 9), { text: String(cnt("L")), options: { color: HEX.grey } }],
    { x: 8.4, y: 0.32, w: 4.48, h: 0.4, fontSize: 9, align: "right", objectName: "Counts" });

  const cw = 4.2, cx = (W - cw) / 2, cy = 1.14, ch = 0.66;
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: cx, y: cy, w: cw, h: ch, rectRadius: 0.06, fill: { color: isI ? BB : DB }, line: { color: isI ? BB : DB }, objectName: "Level 1 box" });
  T(slide, [certRun(d.l1.cert, 12, true), { text: d.l1.name, options: { bold: true, fontSize: 13, color: "FFFFFF", breakLine: true } },
    { text: d.l1.title, options: { fontSize: 9, color: PAL.COOLWHITE } }], { x: cx + 0.1, y: cy, w: cw - 0.2, h: ch, align: "center", valign: "middle", objectName: "Level 1 text" });
  const busY = 1.97;
  slide.addShape(pres.shapes.LINE, { x: W / 2, y: cy + ch, w: 0, h: busY - cy - ch, line: { color: HEX.line, width: 1.25 } });
  slide.addShape(pres.shapes.LINE, { x: GRID.x, y: busY, w: W - 2 * MX, h: 0, line: { color: HEX.line, width: 1.25 } });

  const occ = Array.from({ length: GRID.rows }, () => Array(GRID.cols).fill(false));
  const overflow = [];
  const singleH = GRID.h, doubleH = 2 * GRID.h + GRID.gap;
  const spanOf = p => cardHeight(p) <= singleH ? 1 : cardHeight(p) <= doubleH ? 2 : 3;
  let spans = d.l2.map(spanOf);
  while (spans.reduce((a, b) => a + b, 0) > GRID.rows * GRID.cols) { const i = spans.indexOf(Math.max(...spans)); spans[i]--; }
  const place = {};
  let col = GRID.cols - 1, row = 0;
  if (isI) d.l2.forEach((p, i) => {
    outer: for (let r = 0; r < GRID.rows; r++) for (let c = 0; c < GRID.cols; c++) {
      if (r + spans[i] > GRID.rows) continue;
      let ok = true; for (let k = 0; k < spans[i]; k++) if (occ[r + k][c]) ok = false;
      if (ok) { place[i] = { r, c, s: spans[i] }; for (let k = 0; k < spans[i]; k++) occ[r + k][c] = true; break outer; }
    }
  });
  if (!isI) d.l2.forEach((p, i) => { if (spans[i] > 1) {
    if (row + spans[i] > GRID.rows) { col--; row = 0; }
    place[i] = { r: row, c: col, s: spans[i] }; for (let k = 0; k < spans[i]; k++) occ[row + k][col] = true; row += spans[i];
  } });
  d.l2.forEach((p, i) => { if (!place[i]) {
    outer: for (let r = 0; r < GRID.rows; r++) for (let c = 0; c < GRID.cols; c++) if (!occ[r][c]) { place[i] = { r, c, s: 1 }; occ[r][c] = true; break outer; }
    if (!place[i]) throw new Error(id + ": grid full");
  } });
  d.l2.forEach((p, i) => {
    const placed = place[i];
    const x = GRID.x + placed.c * (GRID.w + GRID.gap), y = GRID.y + placed.r * (GRID.h + GRID.gap);
    const h = placed.s * GRID.h + (placed.s - 1) * GRID.gap;
    let n = p.l3.length; while (n > 0 && cardHeight(p, n) + (n < p.l3.length ? 0.14 : 0) > h) n--;
    if (n < p.l3.length) overflow.push(...p.l3.slice(n).map(q => `${p.name} → ${q.name} (${q.title})`));
    const ph = ND.test(p.name);
    const hl = p.tags.length > 0;
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: GRID.w, h, rectRadius: 0.05,
      fill: { color: hl ? HEX.hlTint : ph ? HEX.ghost : "FFFFFF" },
      line: { color: hl ? BB : HEX.line, width: hl ? 1.25 : 0.9, dashType: p.inferred ? "dash" : "solid" }, objectName: `L2 card ${p.name}` });
    const runs = [];
    if (hl) runs.push({ text: p.tags.join("  ·  ").toUpperCase(), options: { bold: true, fontSize: 6.5, color: BB, charSpacing: 0.5, breakLine: true } });
    runs.push(certRun(p.cert, 10), { text: p.name, options: { bold: true, fontSize: 10, color: ph ? SLATE : HEX.ink, italic: ph, breakLine: true } },
      { text: p.title, options: { fontSize: 8.5, color: HEX.grey, breakLine: p.l3.length > 0 } });
    p.l3.slice(0, n).forEach((q, j) => {
      const qph = ND.test(q.name);
      runs.push(certRun(q.cert, 7.5), { text: q.name, options: { bold: !qph, fontSize: 7.5, color: qph ? SLATE : HEX.navy, italic: q.inferred || qph, paraSpaceBefore: j === 0 ? 5 : 2 } },
        { text: " – " + q.title, options: { fontSize: 7.5, color: HEX.grey, italic: q.inferred || qph, breakLine: j < n - 1 || n < p.l3.length } });
    });
    if (n < p.l3.length) runs.push({ text: `+${p.l3.length - n} more in notes`, options: { fontSize: 7, color: SLATE, italic: true } });
    T(slide, runs, { x: x + 0.07, y: y + 0.05, w: GRID.w - 0.14, h: h - 0.1, objectName: `L2 text ${p.name}`, fit: "none" });
  });
  if (!d.l2.length) T(slide, `No investment staff below this level found on the insurer's site, filings or LinkedIn (LinkedIn read ${LI_ASOF}).`,
    { x: GRID.x, y: GRID.y + 0.1, w: W - 2 * MX, h: 0.6, fontSize: 11, italic: true, color: SLATE, align: "center", objectName: "Empty note" });
  legend(slide, isI ? "Blue = ALM or risk seat" : "Blue = ALM-chain seat");

  const fmt = (p, lvl) => `${lvl} [${p.cert}${p.inferred ? ", line inferred" : ""}] ${p.name} — ${p.title}${p.src.length ? " (src " + p.src.join(",") + ")" : ""}`;
  const N = [`${d.name} — ${isI ? "investment team" : "org chart"} as of ${ASOF} (LinkedIn read ${LI_ASOF})`, `Anchor: ${d.anchor}`, "", "People:", fmt(d.l1, "L1")];
  d.l2.forEach(p => { N.push(fmt(p, "  L2")); p.l3.forEach(q => N.push(fmt(q, "    L3"))); });
  if (overflow.length) N.push("", "Not shown on the slide for space: " + overflow.join("; "));
  N.push("", "Notes:", ...d.notes, "", "Sources:");
  for (const [k, s] of Object.entries(d.srcs)) N.push(`${k}. ${s.label} — ${s.url}`);
  slide.addNotes(N.join("\n"));
  return { id: id + (isI ? "/inv" : ""), overflow };
}

// ---------- slide 3: the six seats against the balance sheet ----------
const fmt1 = (x, d = 1) => Number(x).toLocaleString("en-CA", { minimumFractionDigits: d, maximumFractionDigits: d });
const bn = x => "$" + (x < 1 ? fmt1(x, 2) : fmt1(x, 1)) + "BN";
const ord = n => n + (n % 10 === 1 && n !== 11 ? "st" : n % 10 === 2 && n !== 12 ? "nd" : n % 10 === 3 && n !== 13 ? "rd" : "th");
const rk = (r, what) => r ? `${ord(r[0])} of ${r[1]} ${what}` : "";
const dateLong = iso => { const [y, m, d] = iso.split("-").map(Number); return `${d} ${["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][m - 1]} ${y}`; };
function tiles(c) {
  if (c.genacct_bn != null) {
    const lic = c.capital_basis === "LICAT total";
    return [
      [bn(c.genacct_bn), "General Account excl. par / seg fund", rk(c.genacct_bn_rank, "in this deck")],
      [fmt1(c.capital_pct, 0) + "%", lic ? "LICAT total ratio" : "CARLI solvency ratio (AMF)", lic ? rk(c.capital_pct_rank, "LICAT filers") : "not comparable with LICAT"],
      [c.buffer_pct != null ? fmt1(c.buffer_pct, 1) + "%" : "n/a", "Buffer: surplus + ABL CSM over General Account", c.buffer_pct != null ? rk(c.buffer_pct_rank, "OSFI filers") : "CSM split not available for an AMF filer"],
      [c.par_bn ? bn(c.par_bn) : "none", "Par block", c.par_bn ? fmt1(c.par_pct, 0) + "% of par + General Account" : "no par account"],
      [c.seg_bn ? bn(c.seg_bn) : "none", "Seg fund block", c.seg_bn ? "kept apart from the General Account" : "no seg funds"],
      [fmt1(c.financing_pct, 1) + "%", "Financing / General Account", "repos and other; reinsurance held is " + fmt1(c.reinsurance_pct, 1) + "%"],
    ];
  }
  if (c.total_assets_bn != null) return [
    [bn(c.total_assets_bn), "Total assets (OSFI, legal entity)", "no General Account view built"],
    [fmt1(c.capital_pct, 0) + "%", "LICAT total ratio", rk(c.capital_pct_rank, "LICAT filers")],
    [bn(c.investments_bn), "Investments", ""],
    [bn(c.icl_bn), "Insurance contract liabilities", ""],
    [c.seg_bn != null ? bn(c.seg_bn) : "none", "Seg fund net assets", ""],
    [bn(c.equity_bn), "Total equity", ""],
  ];
  if (c.icl_bn != null) return [
    ["n/a", "General Account", "no public stand-alone balance sheet"],
    ["n/a", "Capital ratio", "not public for DFS alone"],
    [bn(c.icl_bn), "Insurance contract liabilities, life and health", "disclosed"],
    [bn(c.fcf_est_bn), "Fulfilment cash flows net of reinsurance", "estimate (ALM repo)"],
    [bn(c.csm_total_bn), "CSM, net of reinsurance", "split by block not available"],
    ["n/a", "Financing and reinsurance ratios", "need a General Account"],
  ];
  return null;
}
function fnSlide(id, sect) {
  const f = FN.insurers[id], c = CTX[id];
  const s = addSlide("CONTENT", sect);
  eyebrow(s, `${SHORTNAME[id]}  ·  the ALM chain`, `Slide 3 of 3 · ${c.tier}${c.short_id ? " · " + c.short_id : ""} · ${c.regulator}`);
  s.addText(f.title, { placeholder: "title" });
  T(s, f.lead, { x: MX, y: 1.3, w: W - 2 * MX, h: 0.5, fontSize: 13, color: SLATE, objectName: "Lead" });

  // band 1: what the seats manage (ALM repo figures)
  const by = 1.95;
  const scope = c.genacct_bn != null ? "Canadian business, net of reinsurance (ALM repo definitions)" : c.total_assets_bn != null ? "OSFI headline figures for the legal entity (ALM repo universe file)" : "life and health liabilities, net of reinsurance (ALM repo liabilities view)";
  const hdr = c.period_end_date ? `What these seats manage · ${dateLong(c.period_end_date)} · ${scope}${c.note ? " · " + c.note : ""}` : "What these seats manage";
  T(s, hdr, { x: MX, y: by, w: W - 2 * MX, h: 0.22, fontSize: 9, bold: true, color: DB, objectName: "Context header" });
  const tl = tiles(c);
  if (tl) {
    const tw = c.core_mix_pct ? 1.3 : 2.0;
    tl.forEach(([big, label, sub], i) => {
      const x = MX + i * tw;
      T(s, big, { x, y: by + 0.27, w: tw - 0.1, h: 0.38, fontSize: 20, bold: true, color: i === 0 ? BB : DB, valign: "middle", objectName: `Tile ${i + 1} value` });
      T(s, [{ text: label, options: { color: HEX.ink, breakLine: !!sub } }, ...(sub ? [{ text: sub, options: { color: SLATE } }] : [])], { x, y: by + 0.67, w: tw - 0.12, h: 0.55, fontSize: 8, objectName: `Tile ${i + 1} label` });
    });
    if (c.core_mix_pct) {
      const x0 = MX + 6 * 1.3 + 0.15, bw = W - MX - x0;
      T(s, `Core liabilities by line (non-par, excl. seg funds): ${bn(c.core_total_bn)}`, { x: x0, y: by + 0.27, w: bw, h: 0.2, fontSize: 9, color: HEX.ink, objectName: "Mix header" });
      let x = x0; const gap = 0.02, usable = bw - gap * 3;
      LINES.forEach(([k, col]) => { const w = usable * c.core_mix_pct[k] / 100;
        if (w > 0.004) s.addShape(pres.shapes.RECTANGLE, { x, y: by + 0.52, w, h: 0.26, fill: { color: col }, line: { color: col, width: 0 }, objectName: `Mix ${k}` });
        x += w + gap; });
      const lw = bw / 4;
      LINES.forEach(([k, col], i) => {
        s.addShape(pres.shapes.RECTANGLE, { x: x0 + i * lw, y: by + 0.9, w: 0.09, h: 0.09, fill: { color: col }, line: { color: col, width: 0 }, objectName: `Key ${k}` });
        T(s, [{ text: k.replace("Individual", "Ind."), options: { color: HEX.ink, breakLine: true } }, { text: fmt1(c.core_mix_pct[k], 0) + "%", options: { bold: true, color: HEX.ink } }], { x: x0 + i * lw + 0.13, y: by + 0.85, w: lw - 0.15, h: 0.36, fontSize: 8, objectName: `Key label ${k}` });
      });
    }
  } else {
    T(s, `${c.basis}. Regulator: ${c.regulator}. The seats below are still shown, but there is no balance-sheet view to set them against.`, { x: MX, y: by + 0.3, w: W - 2 * MX, h: 0.5, fontSize: 11, italic: true, color: SLATE, objectName: "No context" });
  }

  // band 2: six fixed seats
  const sy = 3.3, sh = 1.85, gap = 0.1, sw = (W - 2 * MX - gap * 5) / 6;
  f.seats.forEach((p, i) => {
    const x = MX + i * (sw + gap), ph = p.cert === "-";
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: sy, w: sw, h: sh, rectRadius: 0.05, fill: { color: ph ? HEX.ghost : "FFFFFF" },
      line: { color: ph ? HEX.line : BB, width: ph ? 0.9 : 1.1, dashType: p.inferred ? "dash" : "solid" }, objectName: `Seat ${p.fn}` });
    T(s, [{ text: p.fn.toUpperCase(), options: { bold: true, fontSize: 8, color: BB, charSpacing: 0.5, breakLine: true } },
      certRun(p.cert, 11), { text: p.name, options: { bold: true, fontSize: 11, color: ph ? SLATE : HEX.ink, italic: ph, breakLine: true } },
      { text: p.title, options: { fontSize: 9, color: HEX.ink, breakLine: true, paraSpaceBefore: 3 } },
      { text: p.where, options: { fontSize: 8.5, color: SLATE, italic: p.inferred, paraSpaceBefore: 4 } }],
      { x: x + 0.09, y: sy + 0.08, w: sw - 0.18, h: sh - 0.14, objectName: `Seat text ${p.fn}`, fit: "none" });
  });

  // band 3: governance in the insurer's own words
  const gy = 5.35;
  T(s, "How the insurer describes ALM governance", { x: MX, y: gy, w: 6, h: 0.22, fontSize: 9, bold: true, color: DB, objectName: "Governance header" });
  const runs = [];
  f.gov.forEach((g, i) => { runs.push({ text: g.kind + ": ", options: { bold: true, color: HEX.ink } }, { text: g.text, options: { color: HEX.ink, breakLine: i < f.gov.length - 1 } }); });
  T(s, runs, { x: MX, y: gy + 0.27, w: W - 2 * MX, h: 1.4, fontSize: 10.5, paraSpaceAfter: 4, objectName: "Governance" });
  legend(s, "Grey = not named publicly");

  const N = [`${data[id].name} — the ALM chain as of ${ASOF}`, `Title: ${f.title}`, `Reading (mine, not stated by the insurer): ${f.lead}`, "", "Seats:"];
  f.seats.forEach(p => { N.push(`${p.fn} [${p.cert}${p.inferred ? ", line or remit inferred" : ""}] ${p.name} — ${p.title}. ${p.where}.`); srcText(id, p.src).forEach(t => N.push("    src: " + t)); });
  N.push("", "ALM governance:");
  f.gov.forEach(g => { N.push(`${g.kind}: ${g.text}`); srcText(id, g.src).forEach(t => N.push("    src: " + t)); });
  N.push("", `Balance-sheet context: ${c.basis}.`, "Definitions (ALM repo, docs/METHODOLOGY.md): General Account excl. par / seg fund, Canadian business, net of reinsurance; Buffer = (Surplus + ABL CSM - net derivative liabilities) / (General Account - repos - derivative assets); core liabilities = individual insurance, individual annuity, group insurance and group annuity, non-par, excl. seg funds. Ranks count the insurers in this deck that have the figure.");
  if (["MFC", "SLF", "CLF"].includes(c.short_id)) N.push("Big 3: the LICAT ratio covers the whole legal entity, while the General Account, buffer and liability mix are Canada only.");
  s.addNotes(N.join("\n"));
}

// ---------- facts used in the overview (computed, then asserted) ----------
const named = id => FN.insurers[id].seats.filter(p => p.cert !== "-").length;
const namedBy = Object.fromEntries(ORDER.map(id => [id, named(id)]));
const viewPeers = ORDER.filter(id => CTX[id].short_id && id !== "rbc_life" && id !== "canada_protection_plan");
const median = a => { const b = [...a].sort((x, y) => x - y), n = b.length; return n % 2 ? b[(n - 1) / 2] : (b[n / 2 - 1] + b[n / 2]) / 2; };
const peerMedian = median(viewPeers.map(id => namedBy[id]));
const almNamed = ORDER.filter(id => FN.insurers[id].seats[1].cert !== "-");
const almHome = k => ORDER.filter(id => FN.insurers[id].alm_home === k);
const sameActuary = ORDER.filter(id => { const s = FN.insurers[id].seats; return s[2].cert !== "-" && s[3].cert !== "-" && s[2].name.split(" ").pop() === s[3].name.split(" ").pop(); });
const cfoActuary = ORDER.filter(id => { const s = FN.insurers[id].seats; return s[4].cert !== "-" && (s[4].name === s[2].name || s[4].name === s[3].name); });
const invSeat = k => ORDER.filter(id => FN.insurers[id].inv_seat === k);
const list = ids => { const a = ids.map(id => SHORTNAME[id].replace(" (DFS)", "")); return a.length <= 1 ? a.join("") : a.slice(0, -1).join(", ") + " and " + a[a.length - 1]; };
const WORD = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];
assert(namedBy.rbc_life === 1, "RBC Life names one seat");
assert(peerMedian === 5, "peer median of named seats is five, got " + peerMedian);
assert(Math.min(...ORDER.map(id => namedBy[id])) === namedBy.rbc_life && ORDER.filter(id => namedBy[id] === namedBy.rbc_life).length === 1, "RBC Life alone has the fewest named seats");
assert(CTX.rbc_life.financing_pct > 15.5 && CTX.rbc_life.financing_pct < 16.5, "RBC Life financing is 16% of General Account");

// ---------- cover ----------
{
  const s = addSlide("DARK", "Overview");
  T(s, "Who runs the ALM chain at Canada's life insurers", { x: 0.8, y: 2.2, w: 11.6, h: 1.0, fontSize: 40, bold: true, color: "FFFFFF", objectName: "Title" });
  T(s, "Org charts for the 20 insurers in the peer set, rebuilt on the Canadian life insurer ALM framework: who holds investments, ALM, actuarial, finance and risk, and what balance sheet they manage", { x: 0.8, y: 3.3, w: 10.6, h: 1.0, fontSize: 18, color: PAL.COOLWHITE, objectName: "Subtitle" });
  T(s, `Prepared for Abid Dobani, SVP & CIO, RBC Insurance · version 2, as of ${ASOF} · public sources only`, { x: 0.8, y: 6.5, w: 11, h: 0.4, fontSize: 12, color: PAL.TUNDRA, objectName: "Byline" });
  s.addNotes("Version 2 of the org-chart deck. Version 1 (6 November 2026) had two slides per insurer. This version re-orders the deck on the ALM repo's tiers with RBC Life first, tags the ALM-chain seats on every org chart, and adds a third slide per insurer that sets six fixed seats against the balance sheet from MooseDragon/cdn-life-insurer-alm.");
}

// ---------- key finding ----------
{
  const s = addSlide("CONTENT", "Overview");
  eyebrow(s, "Key finding", "Seats named publicly, out of six: investments, ALM, Chief Actuary, Appointed Actuary, finance, risk");
  s.addText(`RBC Life names ${WORD[namedBy.rbc_life]} of six ALM-chain seats publicly; peers name a median of ${WORD[peerMedian]}`, { placeholder: "title" });
  T(s, `Seen from outside, RBC Life is the least visible of the 20: only the CIO is named. Peers with a balance-sheet view in the ALM repo (${viewPeers.length} insurers) name between ${Math.min(...viewPeers.map(id => namedBy[id]))} and ${Math.max(...viewPeers.map(id => namedBy[id]))} seats.`, { x: MX, y: 1.3, w: W - 2 * MX, h: 0.5, fontSize: 13, color: SLATE, objectName: "Lead" });
  // bar chart (native): seats named per insurer, RBC Life highlighted
  const labels = ORDER.map(id => SHORTNAME[id]), vals = ORDER.map(id => namedBy[id]);
  s.addChart(pres.charts.BAR, [{ name: "Seats named publicly (of 6)", labels: [...labels].reverse(), values: [...vals].reverse() }], {
    x: MX, y: 1.9, w: 6.6, h: 4.95, barDir: "bar", barGapWidthPct: 45,
    chartColors: [...ORDER].reverse().map(id => id === "rbc_life" ? BB : tint(GRAY, 0.7)),
    showLegend: false, showTitle: true, title: "Seats named publicly, of six", titleFontSize: 10, titleColor: DB, titleFontFace: "+mn-lt",
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 9, dataLabelColor: DB, dataLabelFontFace: "+mn-lt", dataLabelFormatCode: "0",
    catAxisLabelFontSize: 9, catAxisLabelColor: DB, catAxisLabelFontFace: "+mn-lt", valAxisHidden: true, valAxisMaxVal: 6.6, valAxisMinVal: 0,
    valGridLine: { style: "none" }, catGridLine: { style: "none" }, catAxisLineShow: false, valAxisLineShow: false, objectName: "Seats chart" });
  // three readings
  const x = 7.5, w = W - MX - x;
  const pts = [
    ["Where ALM sits", `${WORD[almNamed.length].replace(/^./, m => m.toUpperCase())} insurers name an ALM lead. At ${list(almHome("Investments").filter(id => almNamed.includes(id)))} the seat is inside investments; at Foresters (and so Canada Protection Plan) the Global CFO owns it. ${list(almHome("Committee"))} give ALM to a management committee. RBC Life's seat is in the CIO office but shows no incumbent.`],
    ["Actuarial and finance", `At ${list(sameActuary)} the Chief Actuary also signs as Appointed Actuary. At ${list(cfoActuary)} the finance lead also holds an actuarial seat. Manulife, Sun Life, Canada Life and iA keep CFO, CRO and the investment lead as separate officers.`],
    ["Where the investment lead sits", `${WORD[invSeat("Executive team").length].replace(/^./, m => m.toUpperCase())} insurers seat the investment lead on the top executive team (${list(invSeat("Executive team"))}). At ${list(invSeat("Below executive team"))} the seat is one level down, and at ${list(invSeat("Group / affiliate"))} it sits in a group function or affiliated manager.`],
    ["What would complete the RBC Life page", "Five seats are on no public RBC page: Head of ALM, Chief Actuary, Appointed Actuary, CFO and CRO of RBC Insurance. They stay blank here unless a public source names them."],
  ];
  const runs = [];
  pts.forEach(([h, t], i) => { runs.push({ text: h, options: { bold: true, fontSize: 12, color: DB, breakLine: true, paraSpaceBefore: i ? 9 : 0 } }, { text: t, options: { fontSize: 10.5, color: HEX.ink, breakLine: i < pts.length - 1 } }); });
  T(s, runs, { x, y: 1.95, w, h: 4.9, objectName: "Readings" });
  s.addNotes(["Counts are computed in build_deck.js from data/functions.json and asserted before the deck is written.",
    "Seats named publicly per insurer: " + ORDER.map(id => `${SHORTNAME[id]} ${namedBy[id]}`).join("; ") + ".",
    `Peer median (${peerMedian}) is taken over the ${viewPeers.length} insurers, other than RBC Life, that have a balance-sheet view in the ALM repo (Canada Protection Plan is left out because it repeats Foresters Life).`,
    "A seat counts as named when a person is shown with any certainty grade (H, M or L). Group officers who cover a subsidiary count for that subsidiary (ivari, Wawanesa Life, Primerica, Co-operators Life).",
    "This is an outside-in view from public sources. It says nothing about whether a seat is actually filled."].join("\n"));
}

// ---------- how to read ----------
{
  const s = addSlide("CONTENT", "Overview");
  eyebrow(s, "How to read the deck");
  s.addText("Three slides per insurer, in the same layout: org chart, investment team, ALM chain", { placeholder: "title" });
  const cards = [
    ["What the ALM framework changes", "The ALM repo (MooseDragon/cdn-life-insurer-alm) is now the project's primary lens. It reads an insurer through its Canadian General Account excl. par / seg fund, its liabilities by product line, CSM, surplus and LICAT. This deck asks who holds the seats that manage those things: investments, ALM, Chief Actuary, Appointed Actuary, finance and risk. Order follows the repo: RBC Life first, then bank-owned, Big 3 and non-Big 3 by General Account size."],
    ["Slides 1 and 2: people", "Slide 1 starts from the insurer's top executive, three levels deep; blue cards mark the ALM-chain seats. Slide 2 starts from the CIO or investment lead and drills as deep as sources allow. Hierarchy comes from the insurer's own pages first, then LinkedIn (read 6 November 2026), then trade press. Leadership pages were re-read on 27 November 2026."],
    ["Slide 3: the ALM chain", "Six fixed seats on every insurer, so pages compare side by side; a grey seat exists or is required by law but nobody is named publicly. Above the seats are balance-sheet figures at the fiscal 2025 year-end (31 October for RBC Life and BMO Life, 31 December for the rest), copied from the ALM repo with its definitions. Below are the insurer's own words on ALM governance."],
    ["Certainty and limits", "H: the insurer's own site, filing, circular or release. M: LinkedIn profile, trade press, or a filing that later evidence may have overtaken. L: snippet, aggregator or undated. Dashed or italic: line or remit inferred from a title. Public data only; RBC internal information is not used. Six insurers have no full peer view in the ALM repo and show headline or no figures."],
  ];
  cards.forEach(([h, t], i) => {
    const x = MX + (i % 2) * 6.3, y = 1.45 + Math.floor(i / 2) * 2.72;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 6.1, h: 2.55, rectRadius: 0.06, fill: { color: HEX.tint }, line: { color: HEX.tint }, objectName: "Card " + h });
    T(s, h, { x: x + 0.25, y: y + 0.18, w: 5.6, h: 0.35, fontSize: 15, bold: true, color: DB });
    T(s, t, { x: x + 0.25, y: y + 0.58, w: 5.6, h: 1.9, fontSize: 13, color: HEX.ink });
  });
}

// ---------- matrix ----------
{
  const s = addSlide("CONTENT", "Overview");
  eyebrow(s, "The ALM chain across the peer set", "General Account excl. par / seg fund at fiscal 2025 year-end (ALM repo)");
  const n4 = ORDER.filter(id => FN.insurers[id].seats[3].cert !== "-").length;
  s.addText(`Appointed Actuaries are named at ${n4} of 20 insurers; an ALM lead at ${almNamed.length}`, { placeholder: "title" });
  const hdr = ["Insurer", "GenAcct", "Investments", "ALM", "Chief Actuary", "Appointed Actuary", "Finance", "Risk"].map(t => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: DB } } }));
  const rows = [hdr];
  const NONE = { type: "none" }, RULE = { type: "solid", pt: 0.5, color: tint(GRAY, 0.35) };
  ORDER.forEach(id => {
    const f = FN.insurers[id], c = CTX[id], rbc = id === "rbc_life";
    const fill = { color: rbc ? HEX.hlTint : "FFFFFF" };
    const cell = (text, o) => ({ text, options: Object.assign({ fill, border: [NONE, NONE, RULE, NONE] }, o || {}) });
    const seatCell = p => p.cert === "-" ? cell("–", { color: GRAY }) : cell([{ text: p.cert + " ", options: { bold: true, color: CERT[p.cert] } }, { text: p.name, options: { color: DB, italic: p.inferred } }]);
    rows.push([cell(SHORTNAME[id], { bold: rbc, color: DB }), cell(c.genacct_bn != null ? bn(c.genacct_bn) : "n/a", { color: c.genacct_bn != null ? DB : GRAY, align: "right" }), ...f.seats.map(seatCell)]);
  });
  s.addTable(rows, { x: MX, y: 1.3, w: W - 2 * MX, colW: [1.75, 0.8, 1.7, 1.45, 1.65, 1.7, 1.68, 1.703], fontSize: 8.5, color: DB, rowH: 0.262, margin: [0.02, 0.06, 0.02, 0.06], valign: "middle", objectName: "ALM chain matrix" });
  legend(s, "– = not named publicly");
  s.addNotes("One row per insurer, in deck order (ALM repo tiers). Each cell is the person shown in that seat on the insurer's slide 3, with the certainty letter; italic means the line or remit is inferred. Sources are in the notes of each insurer's slide 3. General Account figures: data/alm_context.json, copied from the ALM repo's peer_summary_2025q4.csv.");
}

// ---------- insurer sections ----------
const res = [];
TIERS.forEach(([tier, ids]) => ids.forEach(id => { res.push(orgSlide(id, "org", tier), orgSlide(id, "inv", tier)); fnSlide(id, tier); }));
res.forEach(r => r.overflow.length && console.log("OVERFLOW", r.id, r.overflow.length));
console.log(tagLog.join("\n"));

// ---------- what changed and limits ----------
{
  const s = addSlide("CONTENT", "Changes and limits");
  eyebrow(s, "Changes and limits");
  // version 1 already named the Appointed Actuary at these four; Canada Protection Plan repeats Foresters Life
  const aaNew = ORDER.filter(id => FN.insurers[id].seats[3].cert !== "-" && !["assumption_life", "desjardins", "uv_insurance", "wawanesa_life", "canada_protection_plan"].includes(id));
  assert(aaNew.length >= 2 && aaNew.length <= 12, "appointed actuaries added: " + aaNew.length);
  s.addText(`Two seats changed hands since the 6 November version; ${WORD[aaNew.length]} Appointed Actuaries were added from filings`, { placeholder: "title" });
  const blocks = [
    ["People who changed", [
      "Manulife: Sinéad O'Connor became Chief Actuary on 12 October 2026 after the death of Stephanie Fadous; Derek Houle continues as Appointed Actuary. Version 1 still showed Ms Fadous.",
      "Empire Life: Scott Ewert is now SVP & CFO; Rebecca Rycroft moves to Munich Re, Canada (Life) on 4 January 2027.",
      "BMO Life: Linda Thorpe signed the fiscal 2025 statements as VP & CFO (version 1 had the seat unnamed); BMO advertised the role in 2026, so she is rated Medium.",
    ]],
    ["What was added", [
      `Appointed Actuaries from the signed opinions in annual reports and statements held in the ALM repo: ${list(aaNew)}.`,
      "ALM governance statements and balance-sheet figures from the ALM repo for the 14 insurers with a peer or liabilities view, plus OSFI headline figures for Primerica Life Canada and Canadian Premier Life.",
    ]],
    ["Limits", [
      "LinkedIn was last read on 6 November 2026; tenure dates and teams below the CIO are as of that date.",
      "sunlife.com, manulife.com and bmo.com block automated reads, so those pages were checked through filings, releases and search.",
      "Assumption Life, Humania and UV Insurance are outside the ALM repo (no OSFI returns), so their slide 3 has no balance-sheet band.",
      "RBC Life's CFO, CRO, Chief Actuary, Appointed Actuary and Head of ALM are not public; the deck does not use RBC internal information.",
    ]],
  ];
  let y = 1.45;
  blocks.forEach(([h, items]) => {
    T(s, h, { x: MX, y, w: 3, h: 0.3, fontSize: 13, bold: true, color: DB });
    const hgt = items.reduce((a, t) => a + lines(t, 9.2, 11.5) * 0.2 + 0.07, 0);
    T(s, items.map((t, i) => ({ text: t, options: { bullet: { indent: 12 }, breakLine: i < items.length - 1 } })), { x: 3.4, y, w: W - MX - 3.4, h: hgt, fontSize: 11.5, paraSpaceAfter: 4, color: HEX.ink });
    y += hgt + 0.3;
  });
}

pres.writeFile({ fileName: OUT }).then(async () => { await applyTheme(OUT, THEME); console.log("wrote", OUT, "| named seats", JSON.stringify(namedBy)); });
