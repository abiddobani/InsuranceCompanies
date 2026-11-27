// Drawings for the peer portfolio composition page. Every figure, chart and table reads a dataset through dash.data;
// nothing here estimates or adjusts a number. Text known in advance lives in index.html, not here.
(() => {
  // A plain hyphen for negatives, so a printed figure reads the same as its cell.
  const plain = (f) => (v) => f(v).replace('\u2212', '-');
  const f1 = plain(d3.format('.1f'));
  const f0 = plain(d3.format(',.0f'));
  const FMT = {
    pct: (v) => f1(v) + '%',
    pts: (v) => (v > 0 ? '+' : '') + f1(v) + ' pts',
    mm: (v) => '$' + f0(v) + 'MM',
    bn: (v) => '$' + f1(v) + 'BN',
    x: (v) => f1(v) + 'x',
    num: (v) => f0(v),
    n1: (v) => f1(v),
    text: (v) => String(v),
    date: (v) => d3.utcFormat('%b %-d, %Y')(new Date(v)),
  };
  const color = (i) => dash.colors[i % dash.colors.length];
  const MUTED = 'var(--cds-chart-muted)';
  const isFocus = (r) => r.insurer === 'RBC';

  // The seven overview classes (Level 2 of the ALM study taxonomy, grouped), in stack order.
  const CLASSES = [
    ['pct_public_fixed_income', 'Public fixed income', 0],
    ['pct_private_fixed_income', 'Private fixed income', 1],
    ['pct_public_equity', 'Public equity', 2],
    ['pct_cash', 'Cash', 3],
    ['pct_external_equity', 'External equity', 4],
    ['pct_external_debt', 'External debt', 5],
    ['pct_other_unclassified', 'Other / unclassified', -1],
  ].map(([f, name, i]) => ({f, name, color: i < 0 ? MUTED : color(i)}));

  document.querySelectorAll('.pc').forEach((root) => {
    dash.colors.slice(0, 8).forEach((c, i) => root.style.setProperty('--pc-c' + i, c));
  });

  // A closed table would be missing from a printout.
  window.addEventListener('beforeprint', () => document.querySelectorAll('.pc-details').forEach((d) => { d.open = true; }));

  // ---------------------------------------------------------------- helpers
  function need(el, ids) {
    const s = ids.map((id) => dash.data(id));
    const loading = s.some((x) => x.status === 'loading');
    el.classList.toggle('dash-skeleton', loading);
    if (s.every((x) => x.status === 'ok' && x.data)) return s.map((x) => x.data);
    if (el.tagName === 'TBODY') {
      el.replaceChildren();
      if (!loading) {
        const td = document.createElement('td');
        td.colSpan = 30;
        td.textContent = 'This table did not load.';
        const tr = document.createElement('tr');
        tr.append(td);
        el.append(tr);
      }
    } else if (el.dataset.draw === 'fig') {
      el.textContent = '—';
    } else {
      el.replaceChildren();
      if (!loading) {
        const p = document.createElement('p');
        p.className = 'pc-fail';
        p.textContent = 'This chart did not load.';
        el.append(p);
      }
    }
    return null;
  }

  function inkOn(el, fill) {
    const probe = document.createElement('span');
    probe.style.color = fill;
    probe.style.display = 'none';
    el.append(probe);
    const c = d3.color(getComputedStyle(probe).color);
    probe.remove();
    if (!c) return '#ffffff';
    const lin = (u) => { u /= 255; return u <= 0.03928 ? u / 12.92 : Math.pow((u + 0.055) / 1.055, 2.4); };
    const {r, g, b} = c.rgb();
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b) > 0.42 ? '#0b0b0b' : '#ffffff';
  }

  function tipper(el) {
    const t = document.createElement('div');
    t.className = 'pc-tip';
    t.hidden = true;
    el.append(t);
    return {
      show(x, y, title, lines) {
        t.replaceChildren();
        const h = document.createElement('div');
        h.className = 'pc-tip-h';
        h.textContent = title;
        t.append(h);
        lines.forEach(([name, value, fill, strong]) => {
          const row = document.createElement('div');
          row.className = 'pc-tip-r' + (strong ? ' pc-tip-on' : '');
          const sw = document.createElement('span');
          sw.className = 'pc-sw';
          if (fill) sw.style.background = fill; else sw.style.visibility = 'hidden';
          const n = document.createElement('span');
          n.textContent = name;
          const v = document.createElement('span');
          v.className = 'pc-tip-v';
          v.textContent = value;
          row.append(sw, n, v);
          t.append(row);
        });
        t.hidden = false;
        const w = t.offsetWidth, hh = t.offsetHeight;
        t.style.left = Math.max(0, Math.min(x + 14, el.clientWidth - w - 2)) + 'px';
        t.style.top = (y + 16 + hh > el.clientHeight && y - hh - 10 > 0 ? y - hh - 10 : y + 16) + 'px';
      },
      hide() { t.hidden = true; },
    };
  }

  const dense = (el) => !!el.closest('[data-dense]');
  const rightRound = (x, y, w, h, r) => {
    r = Math.min(r, w / 2, h / 2);
    return `M${x},${y}h${w - r}a${r},${r} 0 0 1 ${r},${r}v${h - 2 * r}a${r},${r} 0 0 1 ${-r},${r}h${-(w - r)}z`;
  };

  function labelColumn(svg, rows, o, W) {
    const m = svg.append('text').attr('class', 'pc-lab');
    let lw = 0;
    rows.forEach((r) => {
      m.attr('class', 'pc-lab' + (isFocus(r) ? ' pc-lab-on' : '')).text(o.label(r) + (o.est && o.est(r) ? ' est' : ''));
      lw = Math.max(lw, m.node().getComputedTextLength());
    });
    let ew = 0;
    if (o.end) {
      m.attr('class', 'pc-end');
      rows.forEach((r) => { m.text(o.end(r) || ''); ew = Math.max(ew, m.node().getComputedTextLength()); });
    }
    m.remove();
    return [Math.min(lw + 12, W * 0.44), ew ? ew + 8 : 4];
  }

  function rowLabel(g, r, o, y) {
    const t = g.append('text').attr('class', 'pc-lab' + (isFocus(r) ? ' pc-lab-on' : '')).attr('x', 0).attr('y', y).attr('dy', '0.35em').text(o.label(r));
    if (o.est && o.est(r)) t.append('tspan').attr('class', 'pc-est').text(' est');
  }

  function layout(rows, o, rh) {
    let y = 0, last = null;
    const out = [];
    rows.forEach((r) => {
      const grp = o.group ? o.group(r) : null;
      if (grp !== null && grp !== last) { out.push({head: grp, y: y + (last === null ? 0 : 6)}); y += 20 + (last === null ? 0 : 6); last = grp; }
      out.push({r, y});
      y += rh;
    });
    return [out, y];
  }

  function axis(svg, x, top, bottom, ticks, fmt) {
    const g = svg.append('g').attr('class', 'pc-grid');
    ticks.forEach((t) => {
      g.append('line').attr('x1', x(t)).attr('x2', x(t)).attr('y1', top).attr('y2', bottom);
      g.append('text').attr('class', 'pc-tick').attr('x', x(t)).attr('y', bottom + 14)
        .attr('text-anchor', t === ticks[0] ? 'start' : t === ticks[ticks.length - 1] ? 'end' : 'middle').text(fmt(t));
    });
  }

  // Horizontal stacked bars, one row per insurer. o.normalize rescales each row to 100.
  function stack(el, rows, o) {
    const W = el.clientWidth;
    if (!W) return;
    el.replaceChildren();
    const svg = d3.select(el).append('svg').attr('class', 'pc-svg').attr('role', 'img').attr('aria-label', el.dataset.label || '').attr('width', W);
    const rh = dense(el) ? 21 : 26, bh = dense(el) ? 14 : 16;
    const [lw, ew] = labelColumn(svg, rows, o, W);
    const [lay, H] = layout(rows, o, rh);
    const max = o.max || 100;
    const x = d3.scaleLinear([0, max], [lw, W - ew - 1]);
    svg.attr('height', H + 20);
    axis(svg, x, 0, H, o.ticks || [0, 25, 50, 75, 100], (t) => t + '%');
    const tip = tipper(el);
    const inks = new Map();
    o.keys.forEach((k) => inks.set(k.f, inkOn(el, k.color)));
    lay.forEach((d) => {
      if (d.head !== undefined) {
        svg.append('text').attr('class', 'pc-group').attr('x', 0).attr('y', d.y + 13).text(d.head);
        return;
      }
      const r = d.r;
      const vals = o.keys.map((k) => +r[k.f] || 0);
      const sum = d3.sum(vals);
      const scale = o.normalize && sum ? 100 / sum : 1;
      const g = svg.append('g').attr('class', 'pc-row').attr('tabindex', 0).attr('transform', `translate(0,${d.y})`);
      rowLabel(g, r, o, rh / 2);
      const lastIdx = d3.max(vals.map((v, i) => (v > 0 ? i : -1)));
      let acc = 0;
      const lines = (on) => o.keys.map((k, i) => [k.name, FMT.pct(vals[i]), k.color, i === on]).filter((l, i) => vals[i] > 0 || i === on);
      o.keys.forEach((k, i) => {
        const v = vals[i] * scale;
        if (v <= 0) return;
        const x0 = x(acc), x1 = x(acc + v);
        acc += v;
        const w = Math.max(1, x1 - x0 - (i === lastIdx ? 0 : 2));
        const y0 = (rh - bh) / 2;
        const seg = i === lastIdx
          ? g.append('path').attr('d', rightRound(x0, y0, w, bh, 4))
          : g.append('rect').attr('x', x0).attr('y', y0).attr('width', w).attr('height', bh);
        seg.style('fill', k.color)
          .on('pointermove', (ev) => { const [px, py] = d3.pointer(ev, el); tip.show(px, py, o.title(r), lines(i)); })
          .on('pointerleave', () => tip.hide());
        if (w >= 26) {
          g.append('text').attr('class', 'pc-in').attr('x', x0 + w / 2).attr('y', rh / 2).attr('dy', '0.35em').attr('text-anchor', 'middle')
            .style('fill', inks.get(k.f)).text(d3.format('.0f')(vals[i]));
        }
      });
      if (o.end && o.end(r)) g.append('text').attr('class', 'pc-end').attr('x', W).attr('y', rh / 2).attr('dy', '0.35em').attr('text-anchor', 'end').text(o.end(r));
      g.on('focus', () => tip.show(lw, d.y + rh, o.title(r), lines(-1))).on('blur', () => tip.hide());
    });
  }

  // Two dots per insurer on one axis, joined by a hairline.
  function dumbbell(el, rows, o) {
    const W = el.clientWidth;
    if (!W) return;
    el.replaceChildren();
    const svg = d3.select(el).append('svg').attr('class', 'pc-svg').attr('role', 'img').attr('aria-label', el.dataset.label || '').attr('width', W);
    const rh = dense(el) ? 21 : 26;
    const [lw, ew] = labelColumn(svg, rows, o, W);
    const [lay, H] = layout(rows, o, rh);
    const max = o.max || d3.max(rows, (r) => Math.max(o.a(r) || 0, o.b(r) || 0)) * 1.05;
    const x = d3.scaleLinear([0, max], [lw + 6, W - ew - 8]);
    svg.attr('height', H + 20);
    axis(svg, x, 0, H, x.ticks(W < 420 ? 3 : 5), (t) => t + '%');
    const tip = tipper(el);
    lay.forEach((d) => {
      if (d.head !== undefined) { svg.append('text').attr('class', 'pc-group').attr('x', 0).attr('y', d.y + 13).text(d.head); return; }
      const r = d.r, a = o.a(r), b = o.b(r);
      const g = svg.append('g').attr('class', 'pc-row').attr('tabindex', 0).attr('transform', `translate(0,${d.y})`);
      rowLabel(g, r, o, rh / 2);
      const show = (px, py) => tip.show(px, py, o.title(r), [[o.aName, o.fmt(a), o.aColor], [o.bName, o.fmt(b), o.bColor]].concat(o.more ? o.more(r) : []));
      if (a != null && b != null) g.append('line').attr('class', 'pc-link').attr('x1', x(a)).attr('x2', x(b)).attr('y1', rh / 2).attr('y2', rh / 2);
      if (a != null) g.append('circle').attr('class', 'pc-dot').attr('cx', x(a)).attr('cy', rh / 2).attr('r', 5).style('fill', o.aColor);
      if (b != null) g.append('circle').attr('class', 'pc-dot').attr('cx', x(b)).attr('cy', rh / 2).attr('r', 5).style('fill', o.bColor);
      if (o.end && o.end(r)) g.append('text').attr('class', 'pc-end').attr('x', W).attr('y', rh / 2).attr('dy', '0.35em').attr('text-anchor', 'end').text(o.end(r));
      g.append('rect').attr('class', 'pc-hit').attr('x', lw).attr('y', 0).attr('width', Math.max(0, W - lw)).attr('height', rh)
        .on('pointermove', (ev) => { const [px, py] = d3.pointer(ev, el); show(px, py); })
        .on('pointerleave', () => tip.hide());
      g.on('focus', () => show(lw, d.y + rh)).on('blur', () => tip.hide());
    });
  }

  // One dot per insurer, RBC Life in the series colour and the rest muted, each labelled by its short code.
  function scatter(el, rows, o) {
    const W = el.clientWidth;
    if (!W) return;
    el.replaceChildren();
    const H = Math.round(Math.min(dense(el) ? 330 : 380, Math.max(240, W * 0.62)));
    const m = {l: 40, r: 18, t: 12, b: 26};
    const svg = d3.select(el).append('svg').attr('class', 'pc-svg').attr('role', 'img').attr('aria-label', el.dataset.label || '').attr('width', W).attr('height', H);
    const x = d3.scaleLinear([0, 100], [m.l, W - m.r]);
    const ymax = Math.ceil(d3.max(rows, o.y) / 10) * 10 + 5;
    const y = d3.scaleLinear([0, ymax], [H - m.b, m.t]);
    const grid = svg.append('g').attr('class', 'pc-grid');
    x.ticks(5).forEach((t) => {
      grid.append('line').attr('x1', x(t)).attr('x2', x(t)).attr('y1', m.t).attr('y2', H - m.b);
      grid.append('text').attr('class', 'pc-tick').attr('x', x(t)).attr('y', H - m.b + 15).attr('text-anchor', t === 0 ? 'start' : t === 100 ? 'end' : 'middle').text(t + '%');
    });
    y.ticks(5).forEach((t) => {
      grid.append('line').attr('x1', m.l).attr('x2', W - m.r).attr('y1', y(t)).attr('y2', y(t));
      grid.append('text').attr('class', 'pc-tick').attr('x', m.l - 6).attr('y', y(t)).attr('dy', '0.32em').attr('text-anchor', 'end').text(t + '%');
    });
    const pts = rows.map((r) => ({r, px: x(o.x(r)), py: y(o.y(r))}));
    const placed = [];
    const hits = (b) => placed.some((p) => b.x0 < p.x1 && b.x1 > p.x0 && b.y0 < p.y1 && b.y1 > p.y0);
    pts.forEach((p) => placed.push({x0: p.px - 7, x1: p.px + 7, y0: p.py - 7, y1: p.py + 7}));
    const g = svg.append('g');
    pts.slice().sort((a, b) => isFocus(b.r) - isFocus(a.r)).forEach((p) => {
      const t = g.append('text').attr('class', 'pc-code' + (isFocus(p.r) ? ' pc-lab-on' : '')).text(o.code(p.r));
      const tw = t.node().getComputedTextLength();
      const tries = [[9, 4, 'start'], [-9, 4, 'end'], [0, -10, 'middle'], [0, 18, 'middle'], [9, -8, 'start'], [-9, -8, 'end'], [9, 15, 'start'], [-9, 15, 'end']];
      let best = tries[0];
      for (const c of tries) {
        const x0 = c[2] === 'start' ? p.px + c[0] : c[2] === 'end' ? p.px + c[0] - tw : p.px - tw / 2;
        const b = {x0, x1: x0 + tw, y0: p.py + c[1] - 10, y1: p.py + c[1] + 2};
        if (b.x0 >= m.l && b.x1 <= W - 2 && b.y0 >= 0 && !hits(b)) { best = c; placed.push(b); break; }
      }
      t.attr('x', p.px + best[0]).attr('y', p.py + best[1]).attr('text-anchor', best[2]);
    });
    svg.append('g').selectAll('circle').data(pts).join('circle').attr('class', 'pc-dot').attr('cx', (p) => p.px).attr('cy', (p) => p.py)
      .attr('r', (p) => (isFocus(p.r) ? 6 : 5)).style('fill', (p) => (isFocus(p.r) ? color(0) : MUTED));
    const ring = svg.append('circle').attr('class', 'pc-ring').attr('r', 9).attr('visibility', 'hidden');
    const tip = tipper(el);
    const del = d3.Delaunay.from(pts, (p) => p.px, (p) => p.py);
    svg.on('pointermove', (ev) => {
      const [px, py] = d3.pointer(ev, el);
      const p = pts[del.find(px, py)];
      if (!p || Math.hypot(p.px - px, p.py - py) > 48) { tip.hide(); ring.attr('visibility', 'hidden'); return; }
      ring.attr('cx', p.px).attr('cy', p.py).attr('visibility', 'visible');
      tip.show(p.px, p.py, o.title(p.r), o.lines(p.r));
    }).on('pointerleave', () => { tip.hide(); ring.attr('visibility', 'hidden'); });
  }

  // Table rows. cols: [{f, fmt, heat, cls}]; the first column is the row key and is printed as the data has it.
  function table(tbody, rows, cols, o = {}) {
    tbody.replaceChildren();
    rows.forEach((r) => {
      const tr = document.createElement('tr');
      if (isFocus(r)) tr.className = 'pc-tr-on';
      cols.forEach((c, i) => {
        const cell = document.createElement(i === 0 ? 'th' : 'td');
        if (i === 0) cell.scope = 'row';
        const v = r[c.f];
        if (c.cls) cell.className = c.cls;
        if (v == null || v === '') {
          cell.textContent = '';
        } else if (c.heat) {
          if (+v === 0) { cell.textContent = '–'; cell.classList.add('pc-zero'); }
          else {
            cell.textContent = f1(v);
            cell.style.background = `color-mix(in srgb, ${color(0)} ${Math.round(Math.min(1, v / c.heat) * 55 + 4)}%, transparent)`;
          }
        } else {
          cell.textContent = c.fmt ? c.fmt(v) : String(v);
        }
        if (c.signed && v != null) cell.classList.toggle('pc-strong', Math.abs(v) >= 2);
        tr.append(cell);
      });
      tbody.append(tr);
    });
  }
  const heatCols = (fields, max) => fields.map((f) => ({f, heat: max, cls: 'pc-num'}));

  // ---------------------------------------------------------------- calculated values
  dash.calc('rbc_vs_peers', {
    inputs: ['peers'],
    title: 'RBC Life against the peer median',
    description: 'For each headline measure: the RBC Life figure, the median of the other insurers that publish it, and how many insurers that is.',
    fn: (peers) => {
      const measures = ['pct_public_fixed_income', 'pct_private_fixed_income', 'non_fixed_income_pct', 'illiquid_pct',
        'surplus_pct_genacct', 'financing_pct_genacct', 'non_fi_to_surplus_x'];
      const rbc = peers.find((p) => p.insurer === 'RBC');
      return measures.map((measure) => {
        const others = peers.filter((p) => p.insurer !== 'RBC' && p[measure] != null && p[measure] !== '').map((p) => +p[measure]).sort((a, b) => a - b);
        const mid = Math.floor(others.length / 2);
        const median = others.length % 2 ? others[mid] : (others[mid - 1] + others[mid]) / 2;
        const peer_median = Math.round(median * 10) / 10;
        const rbc_life = rbc ? +rbc[measure] : null;
        const gap = rbc_life - peer_median;
        return {measure, rbc_life, peer_median, peers_counted: others.length,
          position: Math.abs(gap) < 2 ? 'in line with' : gap > 0 ? 'above' : 'below'};
      });
    },
  });

  // ---------------------------------------------------------------- drawings
  // A single marked figure: reads its own data-source, data-field and data-where.
  dash.draw('fig', (el) => {
    const got = need(el, [el.dataset.source]);
    if (!got) return;
    const [k, v] = (el.dataset.where || '=').split('=');
    const row = got[0].find((r) => String(r[k]) === decodeURIComponent(v));
    const val = row ? row[el.dataset.field] : null;
    el.textContent = val == null || val === '' ? '—' : FMT[el.dataset.fmt || 'pct'](val);
  });

  const withMix = (peers) => peers.filter((p) => p.has_mix === 'yes');
  const est = (r) => r.estimate === 'est';
  const nm = (r) => r.insurer_name;

  dash.draw('blocks', (el) => {
    const got = need(el, ['peers']);
    if (!got) return;
    stack(el, withMix(got[0]), {
      label: nm, title: (r) => `${r.insurer_name}: ${FMT.bn(r.blocks_total_bn)} in the three blocks`, group: (r) => r.group,
      keys: [{f: 'genacct_share_pct', name: 'General Account', color: color(0)}, {f: 'par_share_pct', name: 'Participating account', color: color(1)},
        {f: 'ul_share_pct', name: 'UL policyholder funds', color: color(2)}],
      end: (r) => FMT.bn(r.blocks_total_bn),
    });
  });

  dash.draw('basis', (el) => {
    const got = need(el, ['basis_effect']);
    if (!got) return;
    dumbbell(el, got[0], {
      label: nm, est, title: nm, a: (r) => r.entity_public_equity_pct, b: (r) => r.genacct_public_equity_pct, fmt: FMT.pct,
      aName: 'Whole invested pool', bName: 'General Account', aColor: MUTED, bColor: color(0),
      end: (r) => FMT.pts(r.public_equity_change_pts),
    });
  });

  dash.draw('funding', (el) => {
    const got = need(el, ['peers']);
    if (!got) return;
    stack(el, got[0].filter((p) => p.fcf_pct_genacct != null), {
      label: nm, est: (r) => r.csm_basis !== 'split', title: (r) => `${r.insurer_name}: funding of the General Account`, group: (r) => r.group,
      keys: [{f: 'fcf_pct_genacct', name: 'Fulfilment cash flows', color: color(0)}, {f: 'csm_pct_genacct', name: 'CSM', color: color(1)},
        {f: 'surplus_pct_genacct', name: 'Surplus', color: color(2)}, {f: 'financing_pct_genacct', name: 'Repos and other financing', color: color(3)}],
    });
  });

  dash.draw('lines', (el) => {
    const got = need(el, ['liabilities']);
    if (!got) return;
    stack(el, got[0], {
      label: nm, normalize: true, title: (r) => `${r.insurer_name}: ${FMT.mm(r.nonpar_icl_mm)} non-par liabilities`,
      keys: [{f: 'individual_insurance_pct', name: 'Individual insurance', color: color(0)}, {f: 'group_annuity_pct', name: 'Group annuity', color: color(1)},
        {f: 'individual_annuity_pct', name: 'Individual annuity', color: color(2)}, {f: 'group_insurance_pct', name: 'Group insurance', color: color(3)}],
    });
  });

  dash.draw('mix', (el) => {
    const got = need(el, ['peers']);
    if (!got) return;
    stack(el, withMix(got[0]), {
      label: nm, est, normalize: true, title: (r) => `${r.insurer_name}: ${FMT.bn(r.genacct_bn)} General Account`, group: (r) => r.group,
      keys: CLASSES, end: (r) => FMT.bn(r.genacct_bn),
    });
  });

  dash.draw('mix-rows', (el) => {
    const got = need(el, ['peers']);
    if (!got) return;
    table(el, withMix(got[0]), [{f: 'insurer_name'}, {f: 'genacct_mm', fmt: f0, cls: 'pc-num'}]
      .concat(CLASSES.map((c) => ({f: c.f, fmt: f1, cls: 'pc-num'})))
      .concat([{f: 'pct_internally_managed', fmt: f1, cls: 'pc-num'}, {f: 'pct_externally_managed', fmt: f1, cls: 'pc-num'},
        {f: 'pct_unclassified', fmt: f1, cls: 'pc-num'}, {f: 'estimate'}]));
  });

  const GA_L3 = ['government_bonds', 'corporate_bonds', 'asset_backed_securities', 'bonds_issuer_not_disclosed', 'commercial_mortgages',
    'illiquid_term_loan', 'private_liquid_loans', 'consumer_loans', 'loans_type_not_disclosed', 'common_shares', 'preferred_shares',
    'pooled_fund_units', 'cash_equivalent', 'real_estate_equity', 'infrastructure_equity', 'other_private_equity', 'infrastructure_debt',
    'other_private_debt', 'other_invested_unclassified'];
  dash.draw('l3-rows', (el) => {
    const got = need(el, ['genacct_l3']);
    if (!got) return;
    table(el, got[0], [{f: 'insurer_name'}].concat(heatCols(GA_L3, 45)));
  });

  dash.draw('fit', (el) => {
    const got = need(el, ['peers']);
    if (!got) return;
    scatter(el, got[0].filter((p) => p.long_liab_pct != null && p.illiquid_pct != null), {
      x: (r) => r.long_liab_pct, y: (r) => r.illiquid_pct, code: (r) => r.code, title: nm,
      lines: (r) => [['Long liabilities', FMT.pct(r.long_liab_pct)], ['Illiquid assets', FMT.pct(r.illiquid_pct)]],
    });
  });

  dash.draw('surplus', (el) => {
    const got = need(el, ['peers']);
    if (!got) return;
    dumbbell(el, got[0].filter((p) => p.surplus_pct_genacct != null), {
      label: nm, est: (r) => est(r) || r.csm_basis !== 'split', title: nm, a: (r) => r.surplus_pct_genacct, b: (r) => r.non_fixed_income_pct, fmt: FMT.pct,
      aName: 'Surplus', bName: 'Assets outside fixed income', aColor: MUTED, bColor: color(0),
      end: (r) => FMT.x(r.non_fi_to_surplus_x),
    });
  });

  const blockRows = (rows, block) => rows.filter((r) => r.block === block && r.amount_mm >= 50);
  ['Par', 'UL policyholder funds'].forEach((block, i) => {
    dash.draw(i ? 'ul' : 'par', (el) => {
      const got = need(el, ['block_classes']);
      if (!got) return;
      stack(el, blockRows(got[0], block), {
        label: nm, est, normalize: true, title: (r) => `${r.insurer_name}: ${FMT.mm(r.amount_mm)}`,
        keys: CLASSES, end: (r) => FMT.bn(r.amount_bn),
      });
    });
  });

  const PAR_L3 = ['government_bonds', 'corporate_bonds', 'commercial_mortgages', 'illiquid_term_loan', 'common_shares', 'preferred_shares',
    'cash_equivalent', 'real_estate_equity', 'other_invested_unclassified'];
  dash.draw('par-rows', (el) => {
    const got = need(el, ['par_l3']);
    if (!got) return;
    table(el, got[0].filter((r) => r.amount_mm >= 50), [{f: 'insurer_name'}, {f: 'amount_mm', fmt: f0, cls: 'pc-num'}].concat(heatCols(PAR_L3, 45)).concat([{f: 'source', cls: 'pc-src'}]));
  });

  const LOOK = ['asset_backed_securities', 'commercial_mortgages', 'illiquid_term_loan', 'private_liquid_loans', 'consumer_loans', 'reverse_mortgages',
    'pooled_fund_units', 'real_estate_equity', 'infrastructure_equity', 'other_private_equity', 'infrastructure_debt', 'structured_products',
    'other_invested_unclassified'];
  dash.draw('look-rows', (el) => {
    const got = need(el, ['lookthrough']);
    if (!got) return;
    table(el, got[0], [{f: 'insurer_name'}, {f: 'reported_invested_mm', fmt: f0, cls: 'pc-num'}].concat(heatCols(LOOK, 25)).concat([{f: 'scope', cls: 'pc-src'}]));
  });

  dash.draw('offbs-rows', (el) => {
    const got = need(el, ['off_balance_sheet']);
    if (!got) return;
    const n = {fmt: f0, cls: 'pc-num'};
    table(el, got[0], [{f: 'insurer_name'}, {f: 'repos_mm', ...n}, {f: 'repos_pct_genacct', fmt: f1, cls: 'pc-num'}, {f: 'securities_lending_mm', ...n},
      {f: 'fixed_income_linear_notional_mm', ...n}, {f: 'fixed_income_non_linear_notional_mm', ...n}, {f: 'equity_notional_mm', ...n}, {f: 'derivative_scope'}]);
  });

  dash.draw('acct', (el) => {
    const got = need(el, ['accounting']);
    if (!got) return;
    stack(el, got[0], {
      label: nm, normalize: true, title: nm,
      keys: [{f: 'fvtpl_pct', name: 'FVTPL', color: color(0)}, {f: 'fvoci_pct', name: 'FVOCI', color: color(1)}, {f: 'amortized_cost_pct', name: 'Amortized cost', color: color(2)}],
    });
  });

  dash.draw('trend-rows', (el) => {
    const got = need(el, ['trend']);
    if (!got) return;
    const c = (f) => ({f, fmt: (v) => (v > 0 ? '+' : '') + f1(v), cls: 'pc-num', signed: true});
    table(el, got[0], [{f: 'insurer_name'}, {f: 'from_date', fmt: FMT.date, cls: 'pc-nw'}, {f: 'to_date', fmt: FMT.date, cls: 'pc-nw'}, c('public_fixed_income_change_pts'),
      c('private_fixed_income_change_pts'), c('public_equity_change_pts'), c('cash_and_cash_equivalent_change_pts'), c('other_unclassified_change_pts')]);
  });

  dash.draw('coverage-rows', (el) => {
    const got = need(el, ['coverage']);
    if (!got) return;
    table(el, got[0], [{f: 'insurer_name'}, {f: 'period_end', fmt: FMT.date, cls: 'pc-nw'}, {f: 'basis'}, {f: 'on_canonical_list'}, {f: 'estimate'}, {f: 'mix_source', cls: 'pc-src'}]);
  });
})();
