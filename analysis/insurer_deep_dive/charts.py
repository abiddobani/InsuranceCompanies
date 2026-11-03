"""Inline-SVG chart helpers in the project's dashboard style (cards, muted peers, blue focus, dashed medians)."""
import html
import math

esc = html.escape

BLUE, ORANGE, TEAL, RED, PURPLE, OLIVE, PINK, GREY = ("#1f5fa8", "#e09a2c", "#3a9d8f", "#c4524d",
                                                      "#8a7fb8", "#6b8e23", "#d16ba5", "#7f7f7f")
MUTED_BAR, GRID, AXIS, REF, INK, SUB, FOCUS_BG = "#b9bec7", "#eceef1", "#9aa1ab", "#3b4048", "#1f2329", "#5d6470", "#e8f0fa"
CLASS_COLORS = {"Bonds": BLUE, "Mortgages & loans": TEAL, "Equities": ORANGE, "Real estate": PURPLE,
                "Other invested assets": RED, "Cash & short-term": "#9fb7d6"}


def nice_step(span, target=5):
    span = span or 1
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
    if out and out[-1] < hi - 1e-9:
        out.append(round(t, 6))
    return out


def svg(W, H, parts):
    return (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">'
            + "".join(parts) + "</svg>")


def hbar(items, fmt, W=560, rowh=24, label_w=150, right_w=70, focus=None, median=None, median_label=None,
         color=BLUE, top=20, vmax=None):
    """Horizontal bars; items = [(label, value)]. The focus row is coloured and outlined, the rest muted."""
    vals = [v for _, v in items if v is not None]
    if not vals:
        return ""
    lo = min(0, min(vals))
    hi = max(vals) if vmax is None else vmax
    hi = hi if hi > lo else lo + 1
    tk = ticks_for(lo, hi)
    lo, hi = min(lo, tk[0]), max(hi, tk[-1])
    x0, x1 = label_w + (42 if lo < 0 else 0), W - right_w
    sx = lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)
    H = top + len(items) * rowh + 8
    g = []
    seen = set()
    for t in tk:
        lab = fmt(t)
        if lab in seen:
            continue
        seen.add(lab)
        g.append(f'<line x1="{sx(t):.1f}" x2="{sx(t):.1f}" y1="{top - 4}" y2="{H - 6}" stroke="{GRID}"/>')
        g.append(f'<text x="{sx(t):.1f}" y="{top - 8}" text-anchor="middle" class="tk">{esc(lab)}</text>')
    if lo < 0:
        g.append(f'<line x1="{sx(0):.1f}" x2="{sx(0):.1f}" y1="{top - 4}" y2="{H - 6}" stroke="{AXIS}"/>')
    for i, (name, v) in enumerate(items):
        y = top + i * rowh
        foc = focus is None or name == focus
        wt = ' font-weight="700"' if (focus is not None and name == focus) else ""
        g.append(f'<text x="{label_w - 10}" y="{y + rowh / 2 + 4:.1f}" text-anchor="end" class="lb"{wt}>{esc(name)}</text>')
        if v is None:
            g.append(f'<text x="{x0 + 4}" y="{y + rowh / 2 + 4:.1f}" class="tk">not disclosed</text>')
            continue
        xa, xb = sorted((sx(0), sx(v)))
        fill = color if foc else MUTED_BAR
        stroke = f' stroke="{INK}" stroke-width="1.6"' if (focus is not None and name == focus) else ""
        g.append(f'<rect x="{xa:.1f}" y="{y + 4}" width="{max(xb - xa, 0.8):.1f}" height="{rowh - 8}" rx="2" fill="{fill}"{stroke}/>')
        if v >= 0:
            g.append(f'<text x="{xb + 6:.1f}" y="{y + rowh / 2 + 4:.1f}" class="vl"{wt}>{esc(fmt(v))}</text>')
        else:
            g.append(f'<text x="{xa - 6:.1f}" y="{y + rowh / 2 + 4:.1f}" text-anchor="end" class="vl"{wt}>{esc(fmt(v))}</text>')
    if median is not None:
        x = sx(median)
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top - 4}" y2="{H - 6}" stroke="{REF}" stroke-dasharray="4 3" stroke-width="1.4"/>')
        if median_label:
            g.append(f'<text x="{x + 5:.1f}" y="{H - 10}" class="tk" fill="{REF}" font-weight="600">{esc(median_label)}</text>')
    return svg(W, H, g)


def stacked_columns(periods, series, colors, W=760, H=330, break_after=None, label_every=4, pct=True):
    """100% stacked columns over time; series = {name: [values aligned to periods]}."""
    m = (16, 10, 34, 40)
    n = len(periods)
    if n == 0:
        return ""
    cw = (W - m[1] - m[3]) / n
    bw = max(min(cw * 0.78, 60), 3)
    sy = lambda v: H - m[2] - v / 100 * (H - m[0] - m[2])
    g = []
    for t in (0, 25, 50, 75, 100):
        g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="{GRID}"/>')
        g.append(f'<text x="{m[3] - 6}" y="{sy(t) + 4:.1f}" text-anchor="end" class="tk">{t}%</text>')
    for i, p in enumerate(periods):
        x = m[3] + i * cw + (cw - bw) / 2
        tot = sum((series[k][i] or 0) for k in series) or 1
        acc = 0.0
        for k in series:
            v = (series[k][i] or 0) / tot * 100
            if v <= 0:
                continue
            g.append(f'<rect x="{x:.1f}" y="{sy(acc + v):.1f}" width="{bw:.1f}" height="{max(sy(acc) - sy(acc + v) - 0.6, 0.3):.1f}" fill="{colors[k]}"/>')
            if bw >= 34 and v >= 6:
                g.append(f'<text x="{x + bw / 2:.1f}" y="{(sy(acc) + sy(acc + v)) / 2 + 4:.1f}" text-anchor="middle" class="sg">{v:.0f}</text>')
            acc += v
        if n <= 8 or i % label_every == 0 or (i == n - 1 and (n - 1) % label_every >= label_every / 2):
            g.append(f'<text x="{x + bw / 2:.1f}" y="{H - m[2] + 15}" text-anchor="middle" class="tk">{esc(p)}</text>')
    if break_after is not None and 0 <= break_after < n - 1:
        x = m[3] + (break_after + 1) * cw
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{m[0] - 8}" y2="{H - m[2] + 4}" stroke="{INK}" stroke-dasharray="3 3"/>')
        g.append(f'<text x="{x + 4:.1f}" y="{m[0] - 2}" class="tk" fill="{INK}">IFRS 17 basis →</text>')
    return svg(W, H, g)


def line_chart(series, W=560, H=250, fmt=lambda v: f"{v:.0f}%", band=None, band_label=None, label_every=4,
               ref=None, ref_label=None):
    """series = [(name, color, [(x_label, value)])]; x positions follow the first series' labels."""
    labels = []
    for _, _, pts in series:
        for x, _ in pts:
            if x not in labels:
                labels.append(x)
    labels.sort()
    vals = [v for _, _, pts in series for _, v in pts if v is not None]
    if band:
        vals += list(band)
    if ref is not None:
        vals.append(ref)
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    pad = max((hi - lo) * 0.12, 2)
    tk = ticks_for(lo - pad, hi + pad, 4)
    lo, hi = tk[0], tk[-1]
    m = (14, 16, 30, 44)
    n = max(len(labels) - 1, 1)
    sx = lambda i: m[3] + i / n * (W - m[1] - m[3])
    sy = lambda v: H - m[2] - (v - lo) / (hi - lo) * (H - m[0] - m[2])
    g = []
    for t in tk:
        g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="{GRID}"/>')
        g.append(f'<text x="{m[3] - 6}" y="{sy(t) + 4:.1f}" text-anchor="end" class="tk">{esc(fmt(t))}</text>')
    if band:
        g.append(f'<rect x="{m[3]}" y="{sy(band[1]):.1f}" width="{W - m[1] - m[3]}" height="{sy(band[0]) - sy(band[1]):.1f}" fill="{TEAL}" fill-opacity="0.12"/>')
        if band_label:
            g.append(f'<text x="{W - m[1] - 4}" y="{sy(band[1]) + 12:.1f}" text-anchor="end" class="tk" fill="{TEAL}">{esc(band_label)}</text>')
    if ref is not None:
        g.append(f'<line x1="{m[3]}" x2="{W - m[1]}" y1="{sy(ref):.1f}" y2="{sy(ref):.1f}" stroke="{RED}" stroke-dasharray="4 3"/>')
        if ref_label:
            g.append(f'<text x="{m[3] + 4}" y="{sy(ref) - 4:.1f}" class="tk" fill="{RED}">{esc(ref_label)}</text>')
    for i, x in enumerate(labels):
        if len(labels) <= 8 or i % label_every == 0 or (i == len(labels) - 1 and (len(labels) - 1) % label_every >= label_every / 2):
            g.append(f'<text x="{sx(i):.1f}" y="{H - m[2] + 15}" text-anchor="middle" class="tk">{esc(x)}</text>')
    for name, col, pts in series:
        idx = {x: i for i, x in enumerate(labels)}
        p = [(sx(idx[x]), sy(v)) for x, v in pts if v is not None]
        if not p:
            continue
        d = " ".join(f"{'M' if j == 0 else 'L'}{a:.1f},{b:.1f}" for j, (a, b) in enumerate(p))
        dash = ' stroke-dasharray="4 3"' if col == MUTED_BAR else ""
        g.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{2.2 if col != MUTED_BAR else 1.6}"{dash}/>')
        a, b = p[-1]
        if col != MUTED_BAR:
            g.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="4" fill="{col}"/>')
            g.append(f'<text x="{a - 6:.1f}" y="{b - 8:.1f}" text-anchor="end" class="vl" font-weight="700" fill="{col}">{esc(fmt(pts[-1][1]))}</text>')
    return svg(W, H, g)


def tenure_bars(person, now=2026.84, W=250):
    """Three thin bars: years in seat, at the firm, in the industry (0-40y scale)."""
    rows = [("In seat", person.get("seat_since")), ("At firm", person.get("firm_since")),
            ("In industry", person.get("industry_since"))]
    g = []
    lw, rw = 64, 74
    sx = lambda v: lw + min(v, 40) / 40 * (W - lw - rw)
    for i, (lab, since) in enumerate(rows):
        y = 4 + i * 15
        g.append(f'<text x="0" y="{y + 9}" class="tk">{lab}</text>')
        g.append(f'<rect x="{lw}" y="{y + 2}" width="{W - lw - rw}" height="8" rx="2" fill="{GRID}"/>')
        if isinstance(since, (int, float)) and since > 1900:
            yrs = max(now - since - 0.5, 0)  # assume a mid-year start
            g.append(f'<rect x="{lw}" y="{y + 2}" width="{max(sx(yrs) - lw, 1.5):.1f}" height="8" rx="2" fill="{[BLUE, TEAL, ORANGE][i]}"/>')
            g.append(f'<text x="{W - rw + 6}" y="{y + 9.5}" class="vl" font-size="10.5px">{"<1" if yrs < 1 else f"{yrs:.0f}"}y · {int(since)}</text>')
        else:
            g.append(f'<text x="{W - rw + 6}" y="{y + 9.5}" class="tk">n/d</text>')
    return svg(W, 50, g)


def mix_bar(items, colors=None, W=520, h=30):
    """Single 100% bar for business mix with a legend underneath."""
    cols = colors or [BLUE, TEAL, ORANGE, PURPLE, RED, OLIVE, PINK, GREY, "#9fb7d6", "#c9a66b"]
    tot = sum(max(p or 0, 0) for _, p in items) or 1
    g = []
    acc = 0
    for i, (lab, p) in enumerate(items):
        if not p or p <= 0:
            continue
        w = p / tot * W
        g.append(f'<rect x="{acc:.1f}" y="0" width="{max(w - 1.5, 0.5):.1f}" height="{h}" rx="2" fill="{cols[i % len(cols)]}"/>')
        if w > 34:
            g.append(f'<text x="{acc + w / 2:.1f}" y="{h / 2 + 4.5}" text-anchor="middle" class="sg" font-size="11.5px">{p:.0f}%</text>')
        acc += w
    return svg(W, h, g)
