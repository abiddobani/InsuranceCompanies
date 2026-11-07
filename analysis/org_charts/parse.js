// Parses data/<id>.txt org files into JSON objects.
const fs = require("fs"), path = require("path");
function parse(file) {
  const o = { srcs: {}, l2: [], notes: [] };
  for (const raw of fs.readFileSync(file, "utf8").split("\n")) {
    const line = raw.trim(); if (!line) continue;
    const m = line.match(/^(\w+):\s*(.*)$/);
    if (m && !/^L[123]$/.test(m[1])) {
      const [k, v] = [m[1], m[2]];
      if (k === "src") { const [key, label, url] = v.split("|").map(s => s.trim()); o.srcs[key] = { label, url }; }
      else if (k === "note") o.notes.push(v);
      else o[k] = v;
      continue;
    }
    const p = line.split("|").map(s => s.trim());
    const [lvl, name, title, cert, src, flag] = p;
    const person = { name, title, cert: cert || "-", src: (src || "").split(",").map(s => s.trim()).filter(Boolean), inferred: flag === "~", l3: [] };
    if (lvl === "L1") o.l1 = person;
    else if (lvl === "L2") o.l2.push(person);
    else if (lvl === "L3") { if (!o.l2.length) throw new Error(file + ": L3 before L2"); o.l2[o.l2.length - 1].l3.push(person); }
    else throw new Error(file + ": bad line " + line);
  }
  for (const p of [o.l1, ...o.l2, ...o.l2.flatMap(x => x.l3)])
    for (const s of p.src) if (!o.srcs[s]) throw new Error(`${file}: ${p.name} cites unknown source ${s}`);
  return o;
}
module.exports = { parse, load: dir => Object.fromEntries(fs.readdirSync(dir).filter(f => f.endsWith(".txt")).map(f => [f.replace(".txt", ""), parse(path.join(dir, f))])) };
if (require.main === module) { const d = module.exports.load(path.join(__dirname, "data")); for (const [k, v] of Object.entries(d)) console.log(k, v.l2.length, v.l2.reduce((a, x) => a + x.l3.length, 0)); }
