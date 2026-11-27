"""Inline-SVG chart helpers and HTML building blocks for the summary deck.

House style of the project's dashboards: cards, RBC Life coloured, outlined and bold, peers grey,
the peer median as a dashed reference line. Categorical colours are the first slots of the dataviz
reference palette in its fixed order (validated for colour-blind separation); "Other" is neutral.
"""
import html
import math

esc = html.escape
FOCUS = "RBC Life"
MARK = "▸ "

# focus, neutrals
BLUE = "#1f5fa8"          # RBC Life
MUTED = "#b9bec7"         # peers
FADED = "#dfe2e7"         # peers on a different basis
GRID, AXIS, REF, INK, SUB, FOCUS_BG = "#eceef1", "#9aa1ab", "#3b4048", "#1f2329", "#5d6470", "#e8f0fa"
RISK = "#c4524d"          # floor / threshold only
# categorical slots, fixed order
C1, C2, C3, C4, C5, C6 = "#257de0", "#f47230", "#00b894", "#f2a600", "#ee7fac", "#008a17"
OTHER = "#9aa1ab"
# sequential blue (one hue, light to dark)
SEQ = ["#eef5fe", "#cce3fd", "#9dc8f7", "#6aabf1", "#338ced"]


def isnum(v):
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def label(name):
    return (MARK + name) if name == FOCUS else name


def nice_step(span, target=5):
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def ticks_for(lo, hi, target=5):
    step = nice_step(hi - lo, target)
    t = math.floor(lo / step) * step
    out = []
    while t <= hi + 1e-9:
        out.append(round(t, 6))
        t += step
    return out


def svg(W, H, parts):
    return (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">'
            + "".join(parts) + "</svg>")


def bar_path(xa, xb, y, h, r=3):
    """Bar from the baseline xa to the data end xb, rounded at the data end only."""
    if abs(xb - xa) < 0.6:
        xb = xa + (0.6 if xb >= xa else -0.6)
    r = min(r, abs(xb - xa), h / 2)
    s = 1 if xb >= xa else -1
    return (f"M{xa:.1f},{y:.1f} L{xb - s * r:.1f},{y:.1f} Q{xb:.1f},{y:.1f} {xb:.1f},{y + r:.1f} "
            f"L{xb:.1f},{y + h - r:.1f} Q{xb:.1f},{y + h:.1f} {xb - s * r:.1f},{y + h:.1f} L{xa:.1f},{y + h:.1f} Z")


def hbar(items, fmt, W=560, rowh=24, label_w=130, right_w=64, vmin=None, vmax=None, refs=(), tick_fmt=None,
         top=20, faded=(), notes=None, whisk=None, ntick=5):
    """Horizontal bars, one per insurer. items = [(name, value or None)].
    refs = [(value, label, colour)] dashed reference lines. faded = names drawn lighter (other basis).
    notes = {name: text shown after the value}. whisk = {name: (low, high)} range drawn over the bar."""
    vals = [v for _, v in items if isnum(v)] + [w for pair in (whisk or {}).values() for w in pair]
    lo = min(0, min(vals)) if vmin is None else vmin
    hi = max(vals + [r[0] for r in refs]) if vmax is None else vmax
    tk = ticks_for(lo, hi, ntick)
    lo, hi = min(lo, tk[0]), max(hi, tk[-1])
    x0, x1 = label_w, W - right_w
    sx = lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)
    bot = 16 if refs else 4
    H = top + len(items) * rowh + bot
    g, vt = [], []          # vt: value labels, drawn last so reference lines never cross them
    for t in tk:
        g.append(f'<line x1="{sx(t):.1f}" x2="{sx(t):.1f}" y1="{top - 4}" y2="{H - bot}" stroke="{GRID}"/>')
        g.append(f'<text x="{sx(t):.1f}" y="{top - 8}" text-anchor="middle" class="tk">{esc((tick_fmt or fmt)(t))}</text>')
    base = sx(0 if lo <= 0 <= hi else lo)
    if lo < 0:
        g.append(f'<line x1="{base:.1f}" x2="{base:.1f}" y1="{top - 4}" y2="{H - bot}" stroke="{AXIS}"/>')
    for i, (name, v) in enumerate(items):
        y = top + i * rowh
        foc = name == FOCUS
        bh = rowh - 8
        wt = ' font-weight="700"' if foc else ""
        ty = y + rowh / 2 + 4
        g.append(f'<text x="{label_w - 10}" y="{ty:.1f}" text-anchor="end" class="lb"{wt}>{esc(label(name))}</text>')
        note = (notes or {}).get(name, "")
        if not isnum(v):
            g.append(f'<text x="{base + 6:.1f}" y="{ty:.1f}" class="tk">{esc(note or "not public")}</text>')
            continue
        fill = BLUE if foc else (FADED if name in faded else MUTED)
        stroke = f' stroke="{INK}" stroke-width="1.4"' if foc else ""
        g.append(f'<path d="{bar_path(base, sx(v), y + 4, bh)}" fill="{fill}"{stroke}/>')
        end = sx(v)
        if whisk and name in whisk:
            wl, wh = whisk[name]
            g.append(f'<line x1="{sx(wl):.1f}" x2="{sx(wh):.1f}" y1="{y + 4 + bh / 2:.1f}" y2="{y + 4 + bh / 2:.1f}" stroke="{INK}" stroke-width="1.2"/>')
            for w in (wl, wh):
                g.append(f'<line x1="{sx(w):.1f}" x2="{sx(w):.1f}" y1="{y + 6}" y2="{y + 2 + bh}" stroke="{INK}" stroke-width="1.2"/>')
            end = max(end, sx(wh))
        txt = fmt(v) + ((" " + note) if note else "")
        tw = len(txt) * (6.9 if foc else 6.4)
        if v >= 0 and any(end + 3 < sx(r[0]) < end + 9 + tw for r in refs):
            # a reference line would run through the label: clear a patch behind it
            vt.append(f'<rect x="{end + 3:.1f}" y="{ty - 11:.1f}" width="{tw + 6:.1f}" height="15" fill="#fff" fill-opacity="0.94"/>')
        if v >= 0:
            vt.append(f'<text x="{end + 6:.1f}" y="{ty:.1f}" class="vl halo"{wt}>{esc(txt)}</text>')
        else:
            vt.append(f'<text x="{sx(v) - 6:.1f}" y="{ty:.1f}" text-anchor="end" class="vl halo"{wt}>{esc(txt)}</text>')
    for k, (rv, rl, rc) in enumerate(refs):
        x = sx(rv)
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top - 4}" y2="{H - bot}" stroke="{rc}" stroke-dasharray="4 3" stroke-width="1.4"/>')
        anchor = "end" if (k % 2 == 0 and len(refs) > 1) or x > W - 150 else "start"
        dx = -5 if anchor == "end" else 5
        g.append(f'<text x="{x + dx:.1f}" y="{H - 3}" text-anchor="{anchor}" class="tk" fill="{rc}" font-weight="600">{esc(rl)}</text>')
    return svg(W, H, g + vt)


def dotstrip(rows, W=820, rowh=40, label_w=330, right_w=10):
    """One measure per row on its own scale: grey dots for peers, a tick for the median, a blue dot for RBC Life."""
    g = []
    x0, x1 = label_w + 118, W - right_w - 52
    for i, r in enumerate(rows):
        y = 6 + i * rowh
        vals = [v for v in r["values"] if isnum(v)] + [r["focus"]]
        lo, hi = min(vals), max(vals)
        if hi == lo:
            hi = lo + 1
        sx = lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)
        cy = y + 16
        g.append(f'<text x="0" y="{y + 13}" class="lb" font-weight="600">{esc(r["metric"])}</text>')
        g.append(f'<text x="0" y="{y + 27}" class="tk">{esc(r["hint"])}</text>')
        g.append(f'<text x="{label_w + 44}" y="{y + 13}" text-anchor="end" class="lb" font-weight="700">{esc(r["fmt"](r["focus"]))}</text>')
        g.append(f'<text x="{label_w + 44}" y="{y + 27}" text-anchor="end" class="tk">median {esc(r["fmt"](r["median"]))}</text>')
        g.append(f'<line x1="{x0}" x2="{x1}" y1="{cy}" y2="{cy}" stroke="{GRID}" stroke-width="2"/>')
        g.append(f'<text x="{x0 - 9}" y="{cy + 4}" text-anchor="end" class="tk">{esc(r["fmt"](lo))}</text>')
        g.append(f'<text x="{x1 + 9}" y="{cy + 4}" class="tk">{esc(r["fmt"](hi))}</text>')
        for v in r["values"]:
            if isnum(v):
                g.append(f'<circle cx="{sx(v):.1f}" cy="{cy}" r="5" fill="{MUTED}" stroke="#fff" stroke-width="1.5"/>')
        x = sx(r["median"])
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{cy - 10}" y2="{cy + 10}" stroke="{REF}" stroke-width="2"/>')
        g.append(f'<circle cx="{sx(r["focus"]):.1f}" cy="{cy}" r="6.5" fill="{BLUE}" stroke="{INK}" stroke-width="1.5"/>')
    return svg(W, 6 + len(rows) * rowh, g)


def scatter(pts, xr, yr, xfmt, yfmt, xlab, ylab, mx, my, pos, W=760, H=470, faded=()):
    m = (14, 24, 48, 64)
    sx = lambda v: m[3] + (v - xr[0]) / (xr[1] - xr[0]) * (W - m[1] - m[3])
    sy = lambda v: H - m[2] - (v - yr[0]) / (yr[1] - yr[0]) * (H - m[0] - m[2])
    g = []
    for t in ticks_for(*yr):
        g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="{GRID}"/>')
        g.append(f'<text x="{m[3] - 8}" y="{sy(t) + 4:.1f}" text-anchor="end" class="tk">{yfmt(t)}</text>')
    for t in ticks_for(*xr):
        g.append(f'<line x1="{sx(t):.1f}" x2="{sx(t):.1f}" y1="{m[0]}" y2="{H - m[2]}" stroke="{GRID}"/>')
        g.append(f'<text x="{sx(t):.1f}" y="{H - m[2] + 16}" text-anchor="middle" class="tk">{xfmt(t)}</text>')
    g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{H - m[2]}" y2="{H - m[2]}" stroke="{AXIS}"/>')
    g.append(f'<line x1="{m[3]}" x2="{m[3]}" y1="{m[0]}" y2="{H - m[2]}" stroke="{AXIS}"/>')
    g.append(f'<line x1="{sx(mx):.1f}" x2="{sx(mx):.1f}" y1="{m[0]}" y2="{H - m[2]}" stroke="{REF}" stroke-dasharray="4 3"/>')
    g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{sy(my):.1f}" y2="{sy(my):.1f}" stroke="{REF}" stroke-dasharray="4 3"/>')
    g.append(f'<text x="{sx(mx) + 5:.1f}" y="{m[0] + 12}" class="tk" fill="{REF}">Median {xfmt(mx)}</text>')
    g.append(f'<text x="{m[3] + 6}" y="{sy(my) - 5:.1f}" class="tk" fill="{REF}">Median {yfmt(my)}</text>')
    g.append(f'<text x="{(m[3] + W - m[1]) / 2}" y="{H - 6}" text-anchor="middle" class="tk" fill="{INK}">{esc(xlab)}</text>')
    g.append(f'<text transform="translate(14,{(m[0] + H - m[2]) / 2}) rotate(-90)" text-anchor="middle" class="tk" fill="{INK}">{esc(ylab)}</text>')
    for name, x, y in sorted(pts, key=lambda p: p[0] == FOCUS):
        foc = name == FOCUS
        cx, cy = sx(x), sy(y)
        dx, dy, anc = {"r": (11, 4, "start"), "l": (-11, 4, "end"), "a": (0, -11, "middle"), "b": (0, 18, "middle"),
                       "br": (7, 18, "start"), "bl": (-7, 18, "end"), "ar": (7, -9, "start"), "al": (-7, -9, "end")}[pos.get(name, "r")]
        if foc:
            g.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7.5" fill="{BLUE}" stroke="{INK}" stroke-width="1.6"/>')
            g.append(f'<text x="{cx + dx:.1f}" y="{cy + dy:.1f}" text-anchor="{anc}" class="lb" font-weight="700">{esc(MARK + name)}</text>')
        else:
            fill = FADED if name in faded else MUTED
            g.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" fill="{fill}" stroke="#fff" stroke-width="2"/>')
            g.append(f'<text x="{cx + dx:.1f}" y="{cy + dy:.1f}" text-anchor="{anc}" class="sl halo">{esc(name)}{" (est)" if name in faded else ""}</text>')
    return svg(W, H, g)


def band_lines(xs, lines, band=None, W=700, H=400, yfmt=lambda v: f"{v:.1f}%", xlab="", step=None, xticks=None,
               xtick_fmt=str, right=120, refs=(), y0=None, y1=None, est_from=None):
    """Lines over a shared x. lines = [(name, [values], colour, width)]; band = (low, high, label) shaded range.
    xs are positions (numbers); xticks the positions to label. Lines are labelled at their right end."""
    allv = [v for _, vs, _, _ in lines for v in vs if isnum(v)] + [r[0] for r in refs]
    if band:
        allv += [v for v in band[0] + band[1] if isnum(v)]
    lo, hi = min(allv), max(allv)
    step = step or nice_step(hi - lo, 5)
    y0 = math.floor(lo / step) * step if y0 is None else y0
    y1 = math.ceil(hi / step) * step if y1 is None else y1
    m = (12, right, 30 if xlab else 22, 46)
    sx = lambda v: m[3] + (v - xs[0]) / (xs[-1] - xs[0]) * (W - m[1] - m[3])
    sy = lambda v: H - m[2] - (v - y0) / (y1 - y0) * (H - m[0] - m[2])
    g = []
    t = y0
    while t <= y1 + 1e-9:
        g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="{GRID}"/>')
        g.append(f'<text x="{m[3] - 8}" y="{sy(t) + 4:.1f}" text-anchor="end" class="tk">{esc(yfmt(t))}</text>')
        t += step
    for x in (xticks if xticks is not None else xs):
        g.append(f'<text x="{sx(x):.1f}" y="{H - m[2] + 15}" text-anchor="middle" class="tk">{esc(xtick_fmt(x))}</text>')
    g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{H - m[2]}" y2="{H - m[2]}" stroke="{AXIS}"/>')
    if xlab:
        g.append(f'<text x="{(m[3] + W - m[1]) / 2}" y="{H - 3}" text-anchor="middle" class="tk" fill="{INK}">{esc(xlab)}</text>')
    if est_from is not None:
        g.append(f'<rect x="{sx(est_from):.1f}" y="{m[0]}" width="{sx(xs[-1]) - sx(est_from):.1f}" height="{H - m[2] - m[0]}" fill="#f6f7f9"/>')
        g.append(f'<text x="{sx(est_from) + 4:.1f}" y="{m[0] + 11}" class="tk">block size est</text>')
    if band:
        ok = [(x, a, b_) for x, a, b_ in zip(xs, band[0], band[1]) if isnum(a) and isnum(b_)]
        d = ("M" + " L".join(f"{sx(x):.1f},{sy(b_):.1f}" for x, _, b_ in ok)
             + " L" + " L".join(f"{sx(x):.1f},{sy(a):.1f}" for x, a, _ in reversed(ok)) + " Z")
        g.append(f'<path d="{d}" fill="{FADED}" fill-opacity="0.7"/>')
        x_, a_, b__ = ok[len(ok) // 6]
        g.append(f'<text x="{sx(x_) + 4:.1f}" y="{sy(a_) + 14:.1f}" class="tk">{esc(band[2])}</text>')
    for rv, rl, rc in refs:
        g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{sy(rv):.1f}" y2="{sy(rv):.1f}" stroke="{rc}" stroke-dasharray="4 3" stroke-width="1.3"/>')
        g.append(f'<text x="{W - m[1] + 8}" y="{sy(rv) + 4:.1f}" class="tk" fill="{rc}" font-weight="600">{esc(rl)}</text>')
    ends = []
    for name, vs, col, w in lines:
        pts = [(x, v) for x, v in zip(xs, vs) if isnum(v)]
        d = " ".join(f"{'M' if i == 0 else 'L'}{sx(x):.1f},{sy(v):.1f}" for i, (x, v) in enumerate(pts))
        g.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{w}" stroke-linejoin="round"/>')
        lx, lv = pts[-1]
        g.append(f'<circle cx="{sx(lx):.1f}" cy="{sy(lv):.1f}" r="3.5" fill="{col}" stroke="#fff" stroke-width="1.5"/>')
        ends.append([sy(lv), name, col, sx(lx)])
    ends.sort()
    for i in range(1, len(ends)):
        if ends[i][0] - ends[i - 1][0] < 14:
            ends[i][0] = ends[i - 1][0] + 14
    for y, name, col, lx in ends:
        g.append(f'<rect x="{lx + 8:.1f}" y="{y - 4:.1f}" width="8" height="8" rx="2" fill="{col}"/>')
        g.append(f'<text x="{lx + 20:.1f}" y="{y + 4:.1f}" class="lb" font-weight="{700 if name.startswith(FOCUS) else 500}">{esc(name)}</text>')
    return svg(W, H, g)


def stacked(rows, colors, W=1160, rowh=26, label_w=200, right_w=0, seg_fmt=None, min_label_w=30, top=22, sub_w=0,
            dark_text=()):
    """100% stacked bars; rows = dicts(name, sub, vals, total_label, none). 2px surface gap between segments."""
    x0, x1 = label_w, W - right_w
    sx = lambda v: x0 + v / 100 * (x1 - x0)
    H = top + len(rows) * rowh + 4
    g = []
    for t in (0, 25, 50, 75, 100):
        g.append(f'<line x1="{sx(t):.1f}" x2="{sx(t):.1f}" y1="{top - 4}" y2="{H - 4}" stroke="{GRID}"/>')
        anc = "end" if t == 100 and right_w < 16 else "middle"
        g.append(f'<text x="{sx(t):.1f}" y="{top - 8}" text-anchor="{anc}" class="tk">{t}%</text>')
    for i, r in enumerate(rows):
        y = top + i * rowh
        bh = rowh - 8
        foc = r["name"] == FOCUS
        wt = ' font-weight="700"' if foc else ""
        ly = y + rowh / 2 + 4
        g.append(f'<text x="0" y="{ly:.1f}" class="lb"{wt}>{esc(label(r["name"]))}</text>')
        if r.get("sub"):
            g.append(f'<text x="{sub_w}" y="{ly:.1f}" class="tk">{esc(r["sub"])}</text>')
        if r.get("none"):
            g.append(f'<text x="{x0 + 6}" y="{ly:.1f}" class="tk">{esc(r["none"])}</text>')
            continue
        vals = [max(v, 0) if isnum(v) else 0 for v in r["vals"]]
        tot = sum(vals) or 1
        acc = 0.0
        for k, (v, col) in enumerate(zip(vals, colors)):
            if v <= 0:
                continue
            w = v / tot * 100
            xa, xb = sx(acc), sx(acc + w)
            g.append(f'<rect x="{xa:.1f}" y="{y + 4}" width="{max(xb - xa - 2, 0.6):.1f}" height="{bh}" rx="2" fill="{col}"/>')
            if xb - xa >= min_label_w:
                txt = seg_fmt(v) if seg_fmt else f"{v:.0f}%"
                cls = "sgd" if k in dark_text else "sg"
                g.append(f'<text x="{(xa + xb) / 2 - 1:.1f}" y="{ly:.1f}" text-anchor="middle" class="{cls}">{esc(txt)}</text>')
            acc += w
        if foc:
            g.append(f'<rect x="{x0 - 3:.1f}" y="{y + 1}" width="{sx(100) - x0 + 4:.1f}" height="{bh + 6}" rx="4" fill="none" stroke="{INK}" stroke-width="1.6"/>')
        if r.get("total_label"):
            g.append(f'<text x="{x1 + 10}" y="{ly:.1f}" class="lb"{wt}>{esc(r["total_label"])}</text>')
    return svg(W, H, g)


def dotpair(rows, fields, fmt, W=520, rowh=27, label_w=132, step=None, medians=()):
    """Two measures per insurer on one scale; fields = [(key, colour)]. medians = [(value, colour)] ticks at the top."""
    vals = [r[f] for r in rows for f, _ in fields if isnum(r.get(f))]
    step = step or nice_step(max(vals) - min(vals), 6)
    x0v, x1v = math.floor(min(vals) / step) * step, math.ceil(max(vals) / step) * step
    top, right = 22, 24
    sx = lambda v: label_w + (v - x0v) / (x1v - x0v) * (W - right - label_w)
    H = top + len(rows) * rowh + 6
    g = []
    t = x0v
    while t <= x1v + 1e-9:
        g.append(f'<line x1="{sx(t):.1f}" x2="{sx(t):.1f}" y1="{top - 4}" y2="{H - 6}" stroke="{GRID}"/>')
        g.append(f'<text x="{sx(t):.1f}" y="{top - 8}" text-anchor="middle" class="tk">{esc(fmt(t))}</text>')
        t += step
    for mv, mc in medians:
        g.append(f'<line x1="{sx(mv):.1f}" x2="{sx(mv):.1f}" y1="{top - 4}" y2="{H - 6}" stroke="{mc}" stroke-dasharray="4 3" stroke-width="1.3"/>')
    for i, r in enumerate(rows):
        y = top + i * rowh + rowh / 2
        foc = r["name"] == FOCUS
        if foc:
            g.append(f'<rect x="0" y="{y - rowh / 2:.1f}" width="{W}" height="{rowh}" fill="{FOCUS_BG}" rx="3"/>')
        wt = ' font-weight="700"' if foc else ""
        g.append(f'<text x="{label_w - 10}" y="{y + 4:.1f}" text-anchor="end" class="lb"{wt}>{esc(label(r["name"]))}</text>')
        vs = [(r[f], c) for f, c in fields if isnum(r.get(f))]
        if len(vs) > 1:
            lo, hi = min(v for v, _ in vs), max(v for v, _ in vs)
            g.append(f'<line x1="{sx(lo):.1f}" x2="{sx(hi):.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="#c9ccd2" stroke-width="2"/>')
        for v, c in vs:
            g.append(f'<circle cx="{sx(v):.1f}" cy="{y:.1f}" r="5.5" fill="{c}" stroke="{INK if foc else "#fff"}" stroke-width="{1.4 if foc else 2}"/>')
    return svg(W, H, g)


def ranges(rows, fmt, W=560, rowh=27, label_w=132, right_w=96, tick=None, step=None, vmax=None):
    """Low-to-high range with the base case as a dot. rows = dicts(name, low, base, high, tick, note)."""
    vals = [r[k] for r in rows for k in ("low", "base", "high", "tick") if isnum(r.get(k))]
    hi = vmax or max(vals)
    tk = ticks_for(0, hi, 5)
    hi = max(hi, tk[-1])
    top = 22
    sx = lambda v: label_w + v / hi * (W - right_w - label_w)
    H = top + len(rows) * rowh + 6
    g = []
    for t in tk:
        g.append(f'<line x1="{sx(t):.1f}" x2="{sx(t):.1f}" y1="{top - 4}" y2="{H - 6}" stroke="{GRID}"/>')
        g.append(f'<text x="{sx(t):.1f}" y="{top - 8}" text-anchor="middle" class="tk">{esc(fmt(t))}</text>')
    for i, r in enumerate(rows):
        y = top + i * rowh + rowh / 2
        foc = r["name"] == FOCUS
        if foc:
            g.append(f'<rect x="0" y="{y - rowh / 2:.1f}" width="{W}" height="{rowh}" fill="{FOCUS_BG}" rx="3"/>')
        wt = ' font-weight="700"' if foc else ""
        g.append(f'<text x="{label_w - 10}" y="{y + 4:.1f}" text-anchor="end" class="lb"{wt}>{esc(label(r["name"]))}</text>')
        if not isnum(r.get("base")):
            g.append(f'<text x="{label_w + 6}" y="{y + 4:.1f}" class="tk">{esc(r.get("note") or "not public")}</text>')
            continue
        col = BLUE if foc else (FADED if r.get("faded") else MUTED)
        g.append(f'<rect x="{sx(r["low"]):.1f}" y="{y - 4:.1f}" width="{max(sx(r["high"]) - sx(r["low"]), 1):.1f}" height="8" rx="4" fill="{col}" fill-opacity="{0.45 if foc else 0.75}"/>')
        g.append(f'<circle cx="{sx(r["base"]):.1f}" cy="{y:.1f}" r="5.5" fill="{BLUE if foc else "#7c838e"}" stroke="{INK if foc else "#fff"}" stroke-width="{1.4 if foc else 2}"/>')
        if isnum(r.get("tick")):
            x = sx(r["tick"])
            g.append(f'<path d="M{x:.1f},{y - 7:.1f} L{x + 5:.1f},{y:.1f} L{x:.1f},{y + 7:.1f} L{x - 5:.1f},{y:.1f} Z" fill="{C2}" stroke="#fff" stroke-width="1.2"/>')
        txt = fmt(r["base"]) + (f' {r["note"]}' if r.get("note") else "")
        g.append(f'<text x="{W - right_w + 8}" y="{y + 4:.1f}" class="vl"{wt}>{esc(txt)}</text>')
    return svg(W, H, g)


# ---------------------------------------------------------------- HTML blocks
def legend(items):
    out = []
    for t, c in items:
        kind = "dash" if c == "dash" else "diamond" if c == "diamond" else ""
        style = "" if kind == "dash" else f' style="background:{C2 if kind == "diamond" else c}"'
        out.append(f'<span><i class="{kind}"{style}></i>{esc(t)}</span>')
    return '<div class="lg">' + "".join(out) + "</div>"


def table(headers, rows, left=1, cls="", focus_col=0, raw=False):
    th = "".join(f'<th class="{"l" if i < left else ""}">{h if raw else esc(h)}</th>' for i, h in enumerate(headers))
    body = []
    for r in rows:
        key = str(r[focus_col]).replace(MARK, "")
        c = ' class="rbc"' if key == FOCUS else ' class="med"' if key.startswith(("Median", "Peer median")) else ""
        body.append(f"<tr{c}>" + "".join(
            f'<td class="{"l" if i < left else ""}">{v if raw else esc(str(v))}</td>' for i, v in enumerate(r)) + "</tr>")
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def card(h2, inner, cap=None, style="", cls=""):
    c = f'<p class="cap">{cap}</p>' if cap else ""
    return f'<div class="card {cls}" style="{style}"><h2>{esc(h2)}</h2>{c}{inner}</div>'


def side(paras, w=330):
    return f'<div class="side" style="flex:0 0 {w}px">' + "".join(f"<p>{p}</p>" for p in paras) + "</div>"


def b(t):
    return f"<b>{esc(str(t))}</b>"
