"""The weekly report's "All locations" pages: every location's forecast at
a glance, before the files go to the hub.

One small panel per location (US first, then the states and territories
by name), three across: the last weeks observed, both models' forecasts
for horizons 0 to 3 (the median and the 95% interval, one colour per
model) and last season's counts over the same weeks of the year, shifted
52 weeks forward, dashed. The national panel also sits, larger, beside
the map (us_feature_html). Printed, each page holds 3 by 5 panels, so the 53
locations fill four pages; a browser's or the window's Print, Save as PDF
gives the PDF.

Panels are inline SVG drawn here (no plotly): 53 of them load at once and
print exactly as they look. Colours come from the page's tokens (the
observed counts, last season, the axes) and the members' colours (the
fans), so both themes and print read.

Two data steps: grid_data() (at run time, in ui/pipeline.py) reduces the
run to the bundle's "grid" field (version 8); grid_html() draws it
(render_bundle). An older bundle has no "grid" and its report has no
such pages.
"""
from __future__ import annotations

import html as _html
from datetime import date, timedelta

#: observed weeks a panel shows before the as-of (the as-of's included)
OBS_WEEKS = 10
#: the quantile levels a panel keeps (it draws the 95% band and median)
LEVELS = (0.025, 0.25, 0.5, 0.75, 0.975)
#: the models a panel draws, in drawing order (the Oracle SIHRS on top)
MODELS = ("analogue", "pf")
#: panels per printed page (3 across, 5 down)
PER_PAGE = 15
#: last season = 52 weeks earlier: the same weekday, the same week of the
#: year within one (a 53-week MMWR year moves it by one week)
SHIFT = timedelta(days=364)


def season_label(d: date) -> str:
    """The flu season (August to July) a date falls in: '2025-26'."""
    y = d.year if d.month >= 8 else d.year - 1
    return f"{y}-{(y + 1) % 100:02d}"


def _q(qmap: dict, level: float) -> float:
    """One quantile from a {level: value} map whose keys may be floats or
    strings."""
    for k, v in qmap.items():
        try:
            if abs(float(k) - level) < 1e-9:
                return float(v)
        except (TypeError, ValueError):
            continue
    best = min(qmap, key=lambda k: abs(float(k) - level))
    return float(qmap[best])


def _h(qd: dict, h: int):
    return (qd or {}).get(str(h), (qd or {}).get(h))


def model_fan(qd: dict, times: list) -> dict | None:
    """One model's panel fan: {"times": the four target dates, "q": per
    horizon [q2.5, q25, q50, q75, q97.5]}; None without all four
    horizons."""
    rows = []
    for h in range(4):
        g = _h(qd, h)
        if not isinstance(g, dict) or not g:
            return None
        rows.append([round(_q(g, L), 2) for L in LEVELS])
    return {"times": list(times), "q": rows}


def last_season(history: list, first: str, last: str) -> list:
    """history: [(iso date, value)] for one location, any span. The
    counts 52 weeks before [first, last], dated 52 weeks later so they sit
    on this season's axis."""
    lo = date.fromisoformat(first) - SHIFT
    hi = date.fromisoformat(last) - SHIFT
    out = []
    for d, v in history:
        try:
            dd = date.fromisoformat(str(d)[:10])
        except ValueError:
            continue
        if lo <= dd <= hi and v is not None:
            out.append([(dd + SHIFT).isoformat(), float(v)])
    return sorted(out)


def grid_data(asof: str, locations: list, keys: dict, names: dict,
              obs: dict, model_q: dict, history: dict) -> dict:
    """The bundle's "grid" field.

    locations: the run's location names; keys: name -> the report's key
    ("US" or a state's abbreviation); names: name -> the panel title.
    obs: name -> [(iso date, value)], the run's observed series.
    model_q: model -> name -> horizon -> {level: value}.
    history: name -> [(iso date, value)], settled counts reaching back a
    season (empty when no vintage could be read)."""
    base = date.fromisoformat(asof)
    times = [(base + timedelta(days=7 * (h + 1))).isoformat()
             for h in range(4)]
    panels = []
    for loc in locations:
        o = [[str(d)[:10], float(v)] for d, v in (obs.get(loc) or [])
             if v is not None][-OBS_WEEKS:]
        first = o[0][0] if o else (base - timedelta(
            days=7 * (OBS_WEEKS - 1))).isoformat()
        fans = {}
        for m in MODELS:
            f = model_fan((model_q.get(m) or {}).get(loc), times)
            if f:
                fans[m] = f
        panels.append({"key": keys.get(loc, loc),
                       "name": names.get(loc, loc),
                       "observed": o,
                       "last_season": last_season(history.get(loc) or [],
                                                  first, times[-1]),
                       "models": fans})
    # US first, then by name
    panels.sort(key=lambda p: (p["key"] != "US", p["name"]))
    return {"asof": asof, "times": times,
            "last_season_label": season_label(base - SHIFT),
            "panels": panels}


# ------------------------------------------------------------- the flags
def flags(panel: dict) -> list:
    """What makes a panel worth a second look, in a few words each:
    a model whose horizon-3 median is below the latest count, and two
    models whose horizon-3 medians fall outside each other's 95% bands."""
    out = []
    o = panel.get("observed") or []
    fans = panel.get("models") or {}
    last = o[-1][1] if o else None
    if last is not None and last > 0:
        low = [m for m in MODELS
               if m in fans and fans[m]["q"][3][2] < last]
        if low:
            out.append(("falls", "the horizon-3 median is below the latest "
                        "count (" + ", ".join(_SHORT[m] for m in low) + ")"))
    if all(m in fans for m in MODELS):
        a, p = fans["analogue"]["q"][3], fans["pf"]["q"][3]
        if not (a[0] <= p[2] <= a[4]) or not (p[0] <= a[2] <= p[4]):
            out.append(("disagree", "at horizon 3 one model's median is "
                        "outside the other's 95% band"))
    return out


_SHORT = {"pf": "Oracle SIHRS", "analogue": "Groundhog"}


# ------------------------------------------------------------- drawing
W, H = 300, 180
#: a 95% band may stretch the scale to this many times the rest of the
#: panel (counts, last season, medians); beyond, it runs off the top
CLIP_X = 1.6
ML, MR, MT, MB = 36, 8, 8, 18


def _num(v: float) -> str:
    if v >= 10_000:
        return f"{v / 1000:.0f}k"
    if v >= 1000:
        return f"{v / 1000:.1f}k".replace(".0k", "k")
    return f"{v:.0f}"


def _nice(v: float) -> float:
    """A round axis top at or above v."""
    if v <= 5:
        return 5.0
    import math
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * e >= v:
            return m * e
    return 10 * e


def _md(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}"


def panel_svg(panel: dict, idx: int, colors: dict) -> tuple:
    """One location's panel as inline SVG, and whether a 95% band runs
    off its scale."""
    o = panel.get("observed") or []
    ls = panel.get("last_season") or []
    fans = panel.get("models") or {}
    times = next((f["times"] for f in fans.values()), None)
    xs = [d for d, _ in o] + [d for d, _ in ls] + list(times or [])
    if not xs:
        return ('<svg class="g-svg" viewBox="0 0 300 180" role="img" '
                'aria-label="no data"><text x="150" y="92" '
                'text-anchor="middle" class="g-ax">no data</text></svg>',
                False)
    d0 = min(date.fromisoformat(x) for x in xs)
    d1 = max(date.fromisoformat(x) for x in xs)
    span = max((d1 - d0).days, 1)
    # the scale: the counts, last season and the medians in full; the 95%
    # bands up to CLIP_X times that, clipped beyond (a Groundhog band can
    # reach ten times its median and would flatten the rest)
    core = [v for _, v in o] + [v for _, v in ls]
    wide = []
    for f in fans.values():
        for r in f["q"]:
            core.append(r[2])
            wide.append(r[4])
    top = max(core + [1.0])
    if wide and max(wide) > top:
        top = min(max(wide), top * CLIP_X)
    top = _nice(top * 1.05)
    clipped = bool(wide) and max(wide) > top

    def X(iso):
        return ML + (W - ML - MR) * (date.fromisoformat(iso) - d0).days / span

    def Y(v):
        return MT + (H - MT - MB) * (1 - min(max(v, 0.0), top * 1.2) / top)

    cid = f"gclip{idx}"
    parts = [f'<svg class="g-svg" viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="{_html.escape(panel.get("name", ""))}">',
             f'<defs><clipPath id="{cid}"><rect x="{ML}" y="{MT}" '
             f'width="{W - ML - MR}" height="{H - MT - MB}"/></clipPath>'
             '</defs>']
    # axes: 0, half and the top
    for v in (0, top / 2, top):
        y = Y(v)
        parts.append(f'<line class="g-grid" x1="{ML}" x2="{W - MR}" '
                     f'y1="{y:.1f}" y2="{y:.1f}"/>'
                     f'<text class="g-ax" x="{ML - 4}" y="{y + 3:.1f}" '
                     f'text-anchor="end">{_num(v)}</text>')
    if o:
        xa = X(o[-1][0])
        parts.append(f'<line class="g-asof" x1="{xa:.1f}" x2="{xa:.1f}" '
                     f'y1="{MT}" y2="{H - MB}"/>')
    ticks = [d0.isoformat()] + ([o[-1][0]] if o else []) + [d1.isoformat()]
    seen = set()
    for i, t in enumerate(ticks):
        if t in seen:
            continue
        seen.add(t)
        anchor = "start" if i == 0 else ("end" if t == d1.isoformat()
                                         else "middle")
        parts.append(f'<text class="g-ax" x="{X(t):.1f}" y="{H - 5}" '
                     f'text-anchor="{anchor}">{_md(t)}</text>')
    body = [f'<g clip-path="url(#{cid})">']
    if ls:
        pts = " ".join(f"{X(d):.1f},{Y(v):.1f}" for d, v in ls)
        body.append(f'<polyline class="g-last" points="{pts}"/>')
    for m in MODELS:
        f = fans.get(m)
        if not f:
            continue
        c = colors.get(m, "#888888")
        ts, q = f["times"], f["q"]
        # one band per model, the 95% interval: one colour each
        for lo, hi, op in ((0, 4, 0.22),):
            up = " ".join(f"{X(t):.1f},{Y(r[hi]):.1f}" for t, r in zip(ts, q))
            dn = " ".join(f"{X(t):.1f},{Y(r[lo]):.1f}"
                          for t, r in reversed(list(zip(ts, q))))
            body.append(f'<polygon points="{up} {dn}" fill="{c}" '
                        f'fill-opacity="{op}" stroke="none"/>')
        med = [(t, r[2]) for t, r in zip(ts, q)]
        if o:
            med = [(o[-1][0], o[-1][1])] + med
        pts = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in med)
        body.append(f'<polyline points="{pts}" fill="none" stroke="{c}" '
                    'stroke-width="1.8"/>')
    if o:
        pts = " ".join(f"{X(d):.1f},{Y(v):.1f}" for d, v in o)
        body.append(f'<polyline class="g-obs" points="{pts}"/>')
        body += [f'<circle class="g-dot" cx="{X(d):.1f}" cy="{Y(v):.1f}" '
                 'r="2"/>' for d, v in o]
    body.append("</g>")
    parts += body
    parts.append("</svg>")
    return "".join(parts), clipped


def _legend(colors: dict, label: str) -> str:
    sw = "".join(
        f'<span class="g-key"><i style="background:{colors.get(m, "#888")}">'
        f'</i>{_SHORT[m]}</span>' for m in reversed(MODELS))
    return (f'{sw}<span class="g-key"><i class="g-k-obs"></i>observed</span>'
            f'<span class="g-key"><i class="g-k-last"></i>last season '
            f'({_html.escape(label)}), same weeks</span>'
            '<span class="g-key g-k-bands">shaded: 95% interval</span>')


def _latest(p: dict) -> str:
    """The latest week's count, in full: 'latest: 2,515 admissions'."""
    o = p.get("observed") or []
    if not o:
        return ""
    v = o[-1][1]
    word = "admission" if v == 1 else "admissions"
    return f'<span class="g-cur">latest: {v:,.0f} {word}</span>'


def _figure(p: dict, title: str, fl: str, idx: int, colors: dict,
            cls: str = "gpanel") -> str:
    """One panel: the name and latest count, then the flags at the
    right, then the chart."""
    svg, _clipped = panel_svg(p, idx, colors)
    key = _html.escape(str(p.get("key", "")))
    flags_html = f'<span class="g-flags">{fl}</span>' if fl else ""
    return (f'<figure class="{cls}" id="g-{key}">'
            f'<figcaption><b>{title}</b>{_latest(p)}{flags_html}'
            f'</figcaption>{svg}</figure>')


def _flag_spans(p: dict) -> str:
    fl = "".join(
        f'<span class="g-flag" title="{_html.escape(why)}">{w}</span>'
        for w, why in flags(p))
    if not p.get("models"):
        fl += '<span class="g-flag g-none">no forecast</span>'
    return fl


def us_feature_html(grid: dict | None, colors: dict) -> str:
    """The national panel at a larger size, for the space beside the map
    ("" when the run has no US panel)."""
    us = next((p for p in (grid or {}).get("panels") or []
               if p.get("key") == "US"), None)
    if not us:
        return ""
    head = ('<div class="g-head">'
            + _legend(colors, (grid or {}).get("last_season_label", ""))
            + "</div>")
    return ('<aside class="rp-usfeature" aria-label="United States forecast">'
            + _figure(dict(us, key="US-feature"), "United States",
                      _flag_spans(us), 999, colors, cls="gpanel g-feature")
            + head + "</aside>")


def grid_html(grid: dict | None, colors: dict, details=()) -> str:
    """The "All locations" section ("" without a grid). `details`: report
    keys that have a detail section (their panel title opens it)."""
    if not grid or not grid.get("panels"):
        return ""
    panels = grid["panels"]
    label = grid.get("last_season_label", "")
    asof = grid.get("asof", "")
    n_flag = sum(1 for p in panels if flags(p))
    pages = [panels[i:i + PER_PAGE] for i in range(0, len(panels), PER_PAGE)]
    out = ['<section class="card rp-grid" id="all-locations" '
           'aria-labelledby="h-grid">',
           '<div class="uk-heading"><h2 id="h-grid">All locations</h2></div>',
           '<p class="g-lede">Every location at a glance, before the files '
           'go to the hub. Each panel has its own scale. '
           + (f"{n_flag} of {len(panels)} flagged for a second look "
              "(hover a flag for why)." if n_flag else
              "None flagged for a second look.")
           + " To keep a copy, print this page and choose Save as PDF: "
             f"{PER_PAGE} panels to a page.</p>"]
    for k, page in enumerate(pages, 1):
        a = (k - 1) * PER_PAGE + 1
        out.append('<div class="gpage">'
                   f'<div class="g-head"><span class="g-pg">Week of {asof} '
                   f'&middot; locations {a} to {a + len(page) - 1} of '
                   f'{len(panels)}</span>{_legend(colors, label)}</div>'
                   '<div class="g-cells">')
        for i, p in enumerate(page):
            key = str(p.get("key", ""))
            name = _html.escape(p.get("name", key))
            title = (f'<a href="#st-{key}" onclick="if(window.showState)'
                     f'{{showState(\'st-{key}\');return false;}}">{name}</a>'
                     if key in details else name)
            fl = _flag_spans(p)
            out.append(_figure(p, title, fl, (k - 1) * PER_PAGE + i,
                               colors))
        out.append("</div></div>")
    out.append("</section>")
    return "".join(out)


def grid_css() -> str:
    """The section's style (report_v2.page_style appends it; braces are
    literal here, not format fields)."""
    return """
 .rp-grid{margin-top:1rem}
 .g-lede{color:var(--mut);margin:.2rem 0 .8rem}
 .gpage{margin-bottom:1rem}
 .g-head{display:flex;flex-wrap:wrap;gap:.3rem 1rem;align-items:center;
   font-size:var(--fs-hint);color:var(--mut);margin:0 0 .4rem}
 .g-pg{font-weight:650;color:var(--ink)}
 .g-key{display:inline-flex;align-items:center;gap:.3rem}
 .g-key i{display:inline-block;width:14px;height:8px;border-radius:2px}
 .g-key i.g-k-obs{background:var(--ink);height:3px}
 .g-key i.g-k-last{height:0;border-top:2px dashed var(--mut);
   background:none;opacity:.8}
 .g-cells{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));
   gap:.5rem}
 @media(max-width:820px){.g-cells{grid-template-columns:repeat(2,minmax(0,1fr))}}
 @media(max-width:520px){.g-cells{grid-template-columns:minmax(0,1fr)}}
 .gpanel{margin:0;border:1px solid var(--line);border-radius:8px;
   padding:.3rem .4rem .1rem;break-inside:avoid}
 .gpanel figcaption{display:flex;flex-wrap:wrap;align-items:baseline;
   gap:.1rem .45rem;font-size:.82rem;line-height:1.25}
 .gpanel figcaption a{color:inherit}
 .g-cur{color:var(--mut);font-size:.75rem}
 .g-flag{font-size:.7rem;font-weight:650;color:var(--bad);
   border:1px solid currentColor;border-radius:999px;padding:0 .35rem;
   cursor:help}
 .g-flag.g-none{color:var(--mut)}
 .g-flags{margin-left:auto;display:inline-flex;flex-wrap:wrap;gap:.25rem}
 .g-svg{display:block;width:100%;height:auto}
 /* the national panel, larger, beside the map */
 .rp-mapsplit{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);
   gap:1rem;align-items:start}
 @media(max-width:900px){.rp-mapsplit{grid-template-columns:minmax(0,1fr)}}
 .rp-usfeature .g-feature{border:0;padding:0}
 .rp-usfeature .g-feature figcaption{font-size:1rem;margin-bottom:.3rem}
 .rp-usfeature .g-head{margin-top:.4rem}
 .g-grid{stroke:var(--line);stroke-width:1}
 .g-ax{fill:var(--mut);font-size:9px}
 .g-asof{stroke:var(--mut);stroke-width:1;stroke-dasharray:3 3}
 .g-last{fill:none;stroke:var(--mut);stroke-width:1.5;opacity:.8;
   stroke-dasharray:4 3}
 .g-obs{fill:none;stroke:var(--ink);stroke-width:1.4}
 .g-dot{fill:var(--ink)}
 @media print{
  @page{size:letter portrait;margin:9mm}
  .rp-mapsplit{grid-template-columns:minmax(0,3fr) minmax(0,2fr)}
  .rp-grid{break-before:page;border:0;padding:0;margin:0}
  .rp-grid > .uk-heading,.g-lede{display:none}
  .gpage{break-after:page;margin:0}
  .gpage:last-child{break-after:auto}
  .g-head{font-size:8pt;margin-bottom:2mm}
  .g-cells{grid-template-columns:repeat(3,minmax(0,1fr));gap:2mm}
  .gpanel{padding:1mm 1.5mm 0;border-radius:2mm}
  .gpanel figcaption{font-size:8pt}
  .g-svg{width:100%;height:auto}
  .g-flag{cursor:auto}
 }
"""
