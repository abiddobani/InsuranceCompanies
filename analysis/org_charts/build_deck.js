// Builds one org-chart slide per insurer (identical layout) into a single .pptx.
// Usage: node build_deck.js <out.pptx>
const pptxgen = require("pptxgenjs");
const path = require("path");
const { load } = require("./parse");
const SKILL = process.env.PPTX_SKILL_DIR;
const { applyTheme } = require(path.join(SKILL, "scripts/apply_theme.js"));

const OUT = process.argv[2] || "org-charts.pptx";
const ASOF = "6 November 2026";
const ORDER = ["manulife", "sun_life", "canada_life", "ia", "rbc_life", "bmo_life", "beneva", "ivari", "empire_life",
  "equitable_life", "cooperators_life", "uv_insurance", "wawanesa_life", "foresters_life", "canada_protection_plan",
  "assumption_life", "canadian_premier", "primerica_life", "humania", "desjardins"];
const GAPS = {
  manulife: "No Canada general-account head found below the CIO",
  sun_life: "Head of Canadian commercial mortgages unnamed",
  canada_life: "Divisional teams unpublished; mortgage head unnamed",
  ia: "Only CIO team published below the Executive Committee",
  rbc_life: "No published exec team; CFO and CRO unnamed",
  bmo_life: "bmo.com read via snippets; CFO vacant/unnamed",
  beneva: "CIO only on LinkedIn; no level 3 published",
  ivari: "No ivari team page; group roles stand in",
  empire_life: "No CRO listed; only CIO team below SVPs",
  equitable_life: "Site page stale; CRO unnamed",
  cooperators_life: "Group-wide team; Co-operators Life team unpublished",
  uv_insurance: "Flat list; no investment lead found",
  wawanesa_life: "No leadership page; no investment head confirmed",
  foresters_life: "Global team only; CIO team not visible",
  canada_protection_plan: "No leadership of its own; Foresters team shown",
  assumption_life: "Lines placed by remit from a flat list",
  canadian_premier: "Five-person team; nothing below",
  primerica_life: "Canadian team mostly unpublished",
  humania: "Nothing below VPs published",
  desjardins: "One flat DFS team; lines inferred",
};

const THEME = {
  name: "Org Charts", headFontFace: "Calibri", bodyFontFace: "Calibri",
  colors: { dk1: "1B2333", lt1: "FFFFFF", dk2: "24395C", lt2: "EEF2F7", accent1: "0E7C7B", accent2: "1B7F3B",
    accent3: "B7791F", accent4: "C2410C", accent5: "8A94A6", accent6: "D8E9E8", hlink: "0E7C7B", folHlink: "24395C" },
};
const HEX = { navy: "24395C", ink: "1B2333", grey: "5B6577", faint: "8A94A6", line: "C5CEDB", tint: "EEF2F7", teal: "0E7C7B", tealTint: "E3F1F0" };
const CERT = { H: "1B7F3B", M: "B7791F", L: "C2410C", "-": "8A94A6" };

const W = 13.333, H = 7.5, MX = 0.45;
const GRID = { x: MX, y: 2.12, cols: 6, rows: 3, gap: 0.1 };
GRID.w = (W - 2 * MX - GRID.gap * (GRID.cols - 1)) / GRID.cols;
GRID.h = (6.78 - GRID.y - GRID.gap * (GRID.rows - 1)) / GRID.rows;

const data = load(path.join(__dirname, "data"));
const inv = load(path.join(__dirname, "data", "inv"));
const isInv = p => /Investment Officer|VP, Investments|Investment & Special|Investments & ALM|manages the general account|oversees investments/i.test(p.title);

// rough text-height model for Calibri (inches)
const cpl = (wIn, pt) => Math.floor((wIn * 72) / (pt * 0.43));
const lines = (s, wIn, pt) => Math.max(1, Math.ceil(s.length / cpl(wIn, pt)));
const TW = GRID.w - 0.14;
function cardHeight(p, maxItems = 99) {
  let h = 0.08 + lines("H " + p.name, TW, 10) * 0.165 + lines(p.title, TW, 8.5) * 0.13 + 0.05;
  p.l3.slice(0, maxItems).forEach(q => { h += lines(`L ${q.name} – ${q.title}`, TW, 7.5) * 0.118 + 0.03; });
  return h + 0.04;
}

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "Canadian L&H insurer org charts";
pres.author = "Prepared for Abid Dobani";
const C = pres.SchemeColor;

pres.defineSlideMaster({
  title: "ORG", background: { color: "FFFFFF" },
  objects: [
    { text: { text: `As of ${ASOF} · sources in speaker notes`, options: { x: 9.55, y: 7.05, w: 2.9, h: 0.25, fontSize: 8, color: HEX.faint, align: "right", margin: 0 } } },
  ],
  slideNumber: { x: 12.55, y: 7.05, w: 0.35, h: 0.25, fontSize: 8, color: HEX.faint, align: "right" },
  placeholders: [],
});
pres.defineSlideMaster({ title: "PLAIN", background: { color: "FFFFFF" }, slideNumber: { x: 12.55, y: 7.05, w: 0.35, h: 0.25, fontSize: 8, color: HEX.faint, align: "right" } });
pres.defineSlideMaster({ title: "DARK", background: { color: HEX.navy } });

const CERT_LIGHT = { H: "A7F3C0", M: "FCD9A0", L: "FDBA8C", "-": "C9D1DD" };
function certRun(c, size, light) { return { text: (c === "-" ? "–" : c) + " ", options: { bold: true, color: (light ? CERT_LIGHT : CERT)[c] || CERT["-"], fontSize: size } }; }

function legend(slide) {
  const y = 7.0, items = [["H", "insurer's own site, filing or release"], ["M", "LinkedIn profile, trade press, search"], ["L", "LinkedIn snippet, aggregator, undated"]];
  const runs = [];
  items.forEach(([c, t], i) => { runs.push(certRun(c, 8)); runs.push({ text: t + (i < 2 ? "   " : ""), options: { color: HEX.grey, fontSize: 8 } }); });
  runs.push({ text: "   ·   Dashed / italic = line inferred   ·   Teal = investment", options: { color: HEX.grey, fontSize: 8 } });
  slide.addText(runs, { x: MX, y, w: 9.0, h: 0.35, margin: 0, valign: "middle", isTextBox: true, objectName: "Legend" });
}

function orgSlide(id, kind = "org") {
  const d = kind === "inv" ? inv[id] : data[id];
  const isI = kind === "inv";
  const slide = pres.addSlide({ masterName: "ORG", sectionTitle: "Insurer org charts" });
  slide.addText(isI ? [{ text: d.name, options: {} }, { text: "  ·  investment team", options: { color: HEX.teal } }] : d.name, { x: MX, y: 0.28, w: 9.5, h: 0.5, fontSize: 24, bold: true, color: HEX.ink, margin: 0, isTextBox: true, objectName: "Title" });
  slide.addText(d.anchor, { x: MX, y: 0.78, w: 12.4, h: 0.28, fontSize: 10.5, color: HEX.grey, margin: 0, isTextBox: true, objectName: "Anchor" });
  // counts badge
  const all = [d.l1, ...d.l2, ...d.l2.flatMap(p => p.l3)].filter(p => !/^Not publicly/.test(p.name));
  const cnt = c => all.filter(p => p.cert === c).length;
  const n2 = d.l2.filter(p => !/^Not publicly/.test(p.name)).length, n3 = d.l2.reduce((a, p) => a + p.l3.filter(q => !/^Not publicly/.test(q.name)).length, 0);
  slide.addText([{ text: isI ? `${n2} CIO directs · ${n3} below them named    ` : `${n2} level-2 · ${n3} level-3 named    `, options: { color: HEX.grey } },
    certRun("H", 9), { text: cnt("H") + "   ", options: { color: HEX.grey } }, certRun("M", 9), { text: cnt("M") + "   ", options: { color: HEX.grey } }, certRun("L", 9), { text: String(cnt("L")), options: { color: HEX.grey } }],
    { x: 9.0, y: 0.32, w: 3.88, h: 0.4, fontSize: 9, align: "right", margin: 0, isTextBox: true, objectName: "Counts" });

  // CEO box
  const cw = 4.2, cx = (W - cw) / 2, cy = 1.14, ch = 0.66;
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: cx, y: cy, w: cw, h: ch, rectRadius: 0.06, fill: { color: isI ? HEX.teal : HEX.navy }, line: { color: isI ? HEX.teal : HEX.navy }, objectName: "Level 1 box" });
  slide.addText([certRun(d.l1.cert, 12, true), { text: d.l1.name, options: { bold: true, fontSize: 13, color: "FFFFFF", breakLine: true } },
    { text: d.l1.title, options: { fontSize: 9, color: "DCE3EE" } }], { x: cx + 0.1, y: cy, w: cw - 0.2, h: ch, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: "Level 1 text" });
  // bus
  const busY = 1.97;
  slide.addShape(pres.shapes.LINE, { x: W / 2, y: cy + ch, w: 0, h: busY - cy - ch, line: { color: HEX.line, width: 1.25 } });
  slide.addShape(pres.shapes.LINE, { x: GRID.x, y: busY, w: W - 2 * MX, h: 0, line: { color: HEX.line, width: 1.25 } });

  // place cards
  const occ = Array.from({ length: GRID.rows }, () => Array(GRID.cols).fill(false));
  const overflow = [];
  const singleH = GRID.h, doubleH = 2 * GRID.h + GRID.gap, tripleH = 3 * GRID.h + 2 * GRID.gap;
  const spanOf = p => cardHeight(p) <= singleH ? 1 : cardHeight(p) <= doubleH ? 2 : 3;
  let spans = d.l2.map(spanOf);
  while (spans.reduce((a, b) => a + b, 0) > GRID.rows * GRID.cols) { const i = spans.indexOf(Math.max(...spans)); spans[i]--; }
  const place = {};
  // tall cards (business heads with level-3 teams) fill columns from the right, top down
  let col = GRID.cols - 1, row = 0;
  // investment slides keep data order: first free row-major slot where the card's height fits
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
    // how many L3 fit
    let n = p.l3.length; while (n > 0 && cardHeight(p, n) + (n < p.l3.length ? 0.14 : 0) > h) n--;
    if (n < p.l3.length) overflow.push(...p.l3.slice(n).map(q => `${p.name} → ${q.name} (${q.title})`));
    const ph = /^Not publicly/.test(p.name);
    const hl = !isI && isInv(p);
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: GRID.w, h, rectRadius: 0.05,
      fill: { color: hl ? HEX.tealTint : ph ? "F7F8FA" : "FFFFFF" },
      line: { color: hl ? HEX.teal : HEX.line, width: hl ? 1.25 : 0.9, dashType: p.inferred ? "dash" : "solid" }, objectName: `L2 card ${p.name}` });
    const runs = [certRun(p.cert, 10), { text: p.name, options: { bold: true, fontSize: 10, color: ph ? HEX.faint : HEX.ink, italic: ph, breakLine: true } },
      { text: p.title, options: { fontSize: 8.5, color: HEX.grey, breakLine: p.l3.length > 0 } }];
    p.l3.slice(0, n).forEach((q, i) => {
      const qph = /^Not publicly/.test(q.name);
      runs.push(certRun(q.cert, 7.5), { text: q.name, options: { bold: !qph, fontSize: 7.5, color: qph ? HEX.faint : HEX.navy, italic: q.inferred || qph, paraSpaceBefore: i === 0 ? 5 : 2 } },
        { text: " – " + q.title, options: { fontSize: 7.5, color: HEX.grey, italic: q.inferred || qph, breakLine: i < n - 1 || n < p.l3.length } });
    });
    if (n < p.l3.length) runs.push({ text: `+${p.l3.length - n} more in notes`, options: { fontSize: 7, color: HEX.faint, italic: true } });
    slide.addText(runs, { x: x + 0.07, y: y + 0.05, w: GRID.w - 0.14, h: h - 0.1, valign: "top", margin: 0, isTextBox: true, objectName: `L2 text ${p.name}`, fit: "none" });
  });
  if (!d.l2.length) slide.addText("No investment staff below this level found on the insurer's site, filings or LinkedIn (checked 6 November 2026).",
    { x: GRID.x, y: GRID.y + 0.1, w: W - 2 * MX, h: 0.6, fontSize: 11, italic: true, color: HEX.faint, align: "center", margin: 0, isTextBox: true, objectName: "Empty note" });
  legend(slide);

  // notes
  const fmt = (p, lvl) => `${lvl} [${p.cert}${p.inferred ? ", line inferred" : ""}] ${p.name} — ${p.title}${p.src.length ? " (src " + p.src.join(",") + ")" : ""}`;
  const N = [`${d.name} — ${isI ? "investment team" : "org chart"} as of ${ASOF}`, `Anchor: ${d.anchor}`, "", "People:", fmt(d.l1, "L1")];
  d.l2.forEach(p => { N.push(fmt(p, "  L2")); p.l3.forEach(q => N.push(fmt(q, "    L3"))); });
  if (overflow.length) N.push("", "Not shown on the slide for space: " + overflow.join("; "));
  N.push("", "Notes:", ...d.notes, "", "Sources:");
  for (const [k, s] of Object.entries(d.srcs)) N.push(`${k}. ${s.label} — ${s.url}`);
  slide.addNotes(N.join("\n"));
  return { id: id + (isI ? "/inv" : ""), overflow };
}

// ---- cover
pres.addSection({ title: "Overview" });
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "Overview" });
  s.addText("Who runs Canada's life & health insurers", { x: 0.8, y: 2.3, w: 11.5, h: 1.0, fontSize: 40, bold: true, color: "FFFFFF", margin: 0, isTextBox: true, objectName: "Title" });
  s.addText("For each of the 20 insurers in the peer set: an org chart three levels deep from the top executive, then the investment team from the CIO down, with a certainty rating on every name", { x: 0.8, y: 3.35, w: 10.5, h: 0.8, fontSize: 18, color: "CFD8E6", margin: 0, isTextBox: true, objectName: "Subtitle" });
  s.addText(`Prepared for Abid Dobani, SVP & CIO, RBC Insurance · as of ${ASOF}`, { x: 0.8, y: 6.5, w: 10, h: 0.4, fontSize: 12, color: "9FB0C8", margin: 0, isTextBox: true, objectName: "Byline" });
}
// ---- how to read
{
  const s = pres.addSlide({ masterName: "PLAIN", sectionTitle: "Overview" });
  s.addText("How to read the charts", { x: MX, y: 0.35, w: 12, h: 0.6, fontSize: 30, bold: true, color: HEX.ink, margin: 0, isTextBox: true, objectName: "Title" });
  const cards = [
    ["Two slides per insurer", "The first slide starts from the insurer's top executive; the second (teal) starts from the CIO or investment lead and drills into the CIO's direct reports and their teams. Level 1 is the insurer's top executive. For a subsidiary run inside a group with no CEO of its own (Co-operators Life, Foresters Life, Canada Protection Plan, Wawanesa Life) it is the group CEO, and the subtitle names who runs the insurer. Level 3 sits inside each level-2 card."],
    ["Source order", "1. The insurer's own website, filings and releases.  2. LinkedIn, read on 6 November 2026 through a signed-in browser (about 90 profile and search pages, read only).  3. Trade press and other public sources. Aggregators (TheOrg, ZoomInfo, MarketScreener) only fill a slot and are always rated Low."],
    ["Certainty", "Each name carries a letter. H: named with that title on the insurer's own site, annual report, circular or press release. M: confirmed on the person's LinkedIn profile, recent trade press, or a company page seen only through search. L: LinkedIn search snippet not confirmed on the profile, aggregator, undated or conflicting sources."],
    ["Reporting lines", "A solid card means the line is stated, or the person is listed on the executive team the CEO leads. A dashed card or an italic level-3 line means the line is inferred from the title. On the first slide a teal card marks the investment lead (CIO or equivalent). LinkedIn rarely states reporting lines, so most lines under the CIO are inferred."],
  ];
  cards.forEach(([h, t], i) => {
    const x = MX + (i % 2) * 6.3, y = 1.3 + Math.floor(i / 2) * 2.75;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 6.1, h: 2.5, rectRadius: 0.08, fill: { color: HEX.tint }, line: { color: HEX.tint }, objectName: "Card " + h });
    s.addText(h, { x: x + 0.3, y: y + 0.2, w: 5.5, h: 0.45, fontSize: 18, bold: true, color: HEX.navy, margin: 0, isTextBox: true });
    s.addText(t, { x: x + 0.3, y: y + 0.7, w: 5.5, h: 1.7, fontSize: 13, color: HEX.ink, margin: 0, valign: "top", isTextBox: true });
  });
}
// ---- summary table
{
  const s = pres.addSlide({ masterName: "PLAIN", sectionTitle: "Overview" });
  s.addText("Coverage by insurer", { x: MX, y: 0.3, w: 12, h: 0.55, fontSize: 28, bold: true, color: HEX.ink, margin: 0, isTextBox: true, objectName: "Title" });
  const hdr = ["Insurer", "Level 1", "L2", "L3", "H", "M", "L", "CIO / investment lead", "Inv. team", "Biggest gap"].map(t => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: HEX.navy } } }));
  const rows = [hdr];
  ORDER.forEach(id => {
    const d = data[id];
    const all = [d.l1, ...d.l2, ...d.l2.flatMap(p => p.l3)].filter(p => !/^Not publicly/.test(p.name));
    const c = k => String(all.filter(p => p.cert === k).length);
    const rbc = id === "rbc_life";
    const o = rbc ? { bold: true, fill: { color: HEX.tealTint } } : {};
    rows.push([d.name, d.l1.name, String(d.l2.filter(p => !/^Not publicly/.test(p.name)).length), String(d.l2.reduce((a, p) => a + p.l3.filter(q => !/^Not publicly/.test(q.name)).length, 0)), c("H"), c("M"), c("L"), inv[id].l1.name, String([...inv[id].l2, ...inv[id].l2.flatMap(p => p.l3)].filter(p => !/^Not publicly/.test(p.name)).length), GAPS[id]].map(t => ({ text: t, options: o })));
  });
  s.addTable(rows, { x: MX, y: 0.98, w: W - 2 * MX, colW: [2.6, 1.6, 0.4, 0.4, 0.4, 0.4, 0.4, 1.65, 0.7, 3.88], fontSize: 9, color: HEX.ink, border: { type: "solid", pt: 0.5, color: "DDE3EA" }, rowH: 0.27, margin: [0.02, 0.06, 0.02, 0.06], valign: "middle", objectName: "Coverage table" });
  s.addNotes("L2 / L3 = number of named people at each level of the main org chart (placeholders for unnamed roles excluded). H / M / L = certainty counts across all named people on that slide, including level 1. Inv. team = named people below the CIO on the investment-team slide.");
}
pres.addSection({ title: "Insurer org charts" });
const res = ORDER.flatMap(id => [orgSlide(id), orgSlide(id, "inv")]);
res.forEach(r => r.overflow.length && console.log("OVERFLOW", r.id, r.overflow.length));

pres.writeFile({ fileName: OUT }).then(async () => { await applyTheme(OUT, THEME); console.log("wrote", OUT); });
