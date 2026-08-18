"""Build-time US choropleth: TopoJSON -> inline SVG paths, zero runtime fetches.

Replaces the plotly geo choropleth, which loads its geometry from cdn.plot.ly
AT RUNTIME and therefore renders an empty box in any CSP-sandboxed or offline
context (found the hard way, 2026-08-17). Geometry is vendored:
app/core/assets/states-albers-10m.json (us-atlas, US Census-derived, public
domain, pre-projected Albers composite with AK/HI insets on a 975x610 plane).

Hover card, click drill-down, and pan/zoom are vanilla JS on the inline SVG --
no library, works from file://, artifacts, or any static host. Pan/zoom mutates
the SVG viewBox: wheel zooms about the cursor, drag pans, double-click resets.
A press that travels < 5px still counts as a state click (drag never
click-throughs).

Two render modes:
  * svg_map(cards_by_fips)  -- per-state choropleth (modal category color,
    opacity by its probability; no-data states are black #0a0a0a)
  * national_svg(us_card)   -- same geography, one shared fill = the national
    card's modal category; hover anywhere shows the national card, click
    anywhere opens the st-US section
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ASSET = Path(__file__).parent / "assets" / "states-albers-10m.json"

CATS = ("large_decrease", "decrease", "stable", "increase", "large_increase")
CAT_COLOR = {"large_decrease": "#2e7d4f", "decrease": "#7fc97f",
             "stable": "#b9b09b", "increase": "#e8a33d",
             "large_increase": "#c0392b"}
NO_DATA = "#0a0a0a"

VIEWBOX = "0 0 975 610"


@lru_cache(maxsize=1)
def state_paths() -> dict:
    """fips -> (name, svg_path_d). Decoded once per process."""
    topo = json.loads(ASSET.read_text())
    sc, tr = topo["transform"]["scale"], topo["transform"]["translate"]

    def arc_points(idx: int):
        rev = idx < 0
        arc = topo["arcs"][~idx if rev else idx]
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx; y += dy
            pts.append((x * sc[0] + tr[0], y * sc[1] + tr[1]))
        return pts[::-1] if rev else pts

    def ring_d(arcs) -> str:
        pts = []
        for i, a in enumerate(arcs):
            p = arc_points(a)
            pts.extend(p if i == 0 else p[1:])      # arcs share endpoints
        return ("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")

    out = {}
    for g in topo["objects"]["states"]["geometries"]:
        polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
        d = "".join(ring_d(ring) for poly in polys for ring in poly)
        out[str(g["id"]).zfill(2)] = (g["properties"]["name"], d)
    return out


# Pan/zoom + tooltip + click, scoped per map instance via __ID__.
# Zoom clamps between the full extent (1x) and 40x. Drag distance is measured
# from the mousedown point; a press that never travels 5px is still a click.
_JS = """
<script>
(function() {
  const svg = document.getElementById('__ID__');
  const wrap = document.getElementById('__ID__-wrap');
  const tip = document.getElementById('__ID__-tip');
  if (!svg || !wrap || !tip) return;
  const VB = [0, 0, 975, 610];
  let vb = VB.slice();
  const apply = () => svg.setAttribute('viewBox', vb.join(' '));
  const toSvg = ev => {
    const r = svg.getBoundingClientRect();
    return [vb[0] + (ev.clientX - r.left) / r.width * vb[2],
            vb[1] + (ev.clientY - r.top) / r.height * vb[3]];
  };
  // mouse-wheel zoom centered on the cursor
  svg.addEventListener('wheel', ev => {
    ev.preventDefault();
    const [sx, sy] = toSvg(ev);
    let f = ev.deltaY > 0 ? 1.25 : 0.8;
    f = Math.min(Math.max(vb[2] * f, VB[2] / 40), VB[2]) / vb[2];
    vb = [sx - (sx - vb[0]) * f, sy - (sy - vb[1]) * f,
          vb[2] * f, vb[3] * f];
    apply();
  }, {passive: false});
  // click-drag pan
  let down = null, sx0 = 0, sy0 = 0, dist = 0;
  svg.addEventListener('mousedown', ev => {
    down = [ev.clientX, ev.clientY];
    sx0 = ev.clientX; sy0 = ev.clientY; dist = 0;
    ev.preventDefault();
  });
  window.addEventListener('mousemove', ev => {
    if (!down) return;
    dist = Math.max(dist, Math.hypot(ev.clientX - sx0, ev.clientY - sy0));
    const r = svg.getBoundingClientRect();
    vb[0] -= (ev.clientX - down[0]) * vb[2] / r.width;
    vb[1] -= (ev.clientY - down[1]) * vb[3] / r.height;
    down = [ev.clientX, ev.clientY];
    apply();
    if (dist >= 5) tip.style.display = 'none';
  });
  window.addEventListener('mouseup', () => { down = null; });
  // double-click resets to the full extent
  svg.addEventListener('dblclick', ev => {
    ev.preventDefault();
    vb = VB.slice();
    apply();
  });
  // hover tooltip (delegated, so it keeps working while panned/zoomed)
  svg.addEventListener('mousemove', ev => {
    if (down && dist >= 5) return;
    const t = ev.target.closest ? ev.target.closest('[data-hover]') : null;
    if (!t) { tip.style.display = 'none'; return; }
    tip.innerHTML = t.dataset.hover;
    tip.style.display = 'block';
    const r = wrap.getBoundingClientRect();
    let x = ev.clientX - r.left + 14, y = ev.clientY - r.top + 14;
    if (x + 250 > r.width) x -= 270;
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  });
  svg.addEventListener('mouseleave', () => tip.style.display = 'none');
  // click drill-down, suppressed after a real drag (pointer moved >= 5px)
  svg.addEventListener('click', ev => {
    if (dist >= 5) return;
    const t = ev.target.closest ? ev.target.closest('[data-abbr]') : null;
    const a = t && t.dataset.abbr;
    if (a && window.showState) window.showState('st-' + a);
  });
})();
</script>"""


def _shell(dom_id: str, inner: str, ink: str, paper: str, interactive=True) -> str:
    """Wrap SVG body in the fluid container + tooltip div + interaction JS."""
    return f"""
<div id="{dom_id}-wrap" style="position:relative">
<svg id="{dom_id}" viewBox="{VIEWBOX}" xmlns="http://www.w3.org/2000/svg"
     style="width:100%;height:auto;display:block;touch-action:none">
<style>
 #{dom_id} .st{{cursor:pointer;transition:fill-opacity .12s}}
 #{dom_id} .st:hover{{stroke:{ink};stroke-width:1.6}}
 #{dom_id} .nat{{cursor:pointer}}
 #{dom_id} .nat:hover path{{stroke:{ink};stroke-width:1.2}}
</style>
{inner}
</svg>
<div id="{dom_id}-tip" style="position:absolute;pointer-events:none;display:none;
 background:#1d1d21;border:1px solid #2c2c31;border-radius:10px;
 padding:.6rem .8rem;font-size:.82rem;line-height:1.45;color:{ink};
 max-width:240px;box-shadow:0 6px 24px rgba(0,0,0,.5);z-index:10"></div>
</div>""" + (_JS.replace("__ID__", dom_id) if interactive else "")


def svg_map(cards_by_fips: dict, ink="#e9ecf2", paper="#0a1626",
            dom_id: str = "usmap", interactive=True) -> str:
    """cards_by_fips: fips -> {probs, name, abbr, hover_html} ({} = no data).

    Emits the full SVG + tooltip div + interaction script (hover card, click
    drill-down, wheel-zoom / drag-pan / dblclick-reset). Each state path
    carries data-attributes; JS is dependency-free. `dom_id` must be unique
    per page when several maps are embedded together.
    """
    paths = []
    for fips, (topo_name, d) in state_paths().items():
        card = cards_by_fips.get(fips, {})
        probs = card.get("probs") or {}
        if probs:
            modal = max(probs, key=probs.get)
            fill = CAT_COLOR[modal]
            op = 0.35 + 0.65 * probs[modal]
        else:
            fill, op = NO_DATA, 1.0
        hover = card.get("hover_html") or (
            f"<b>{card.get('name', topo_name)}</b><br>no reported data "
            f"(reporting gap)")
        abbr = card.get("abbr", "")
        paths.append(
            f'<path d="{d}" fill="{fill}" fill-opacity="{op:.2f}" '
            f'stroke="{paper}" stroke-width="1" class="st" '
            f'data-abbr="{abbr}" data-hover="{_esc(hover)}"/>')
    return _shell(dom_id, "".join(paths), ink, paper, interactive)


def national_svg(us_card: dict, ink="#e9ecf2", paper="#0a1626",
                 dom_id: str = "usmap-nat") -> str:
    """National mode: same geography, one shared fill.

    us_card has the same shape as a state card: {probs, name, abbr, fips,
    hover_html}. Every state is filled with the national modal category's
    color (opacity by its probability); hovering anywhere shows the national
    hover card; clicking anywhere calls window.showState('st-US'). One <g>
    with a single shared fill, one tooltip; pan/zoom identical to svg_map.
    """
    card = us_card or {}
    probs = card.get("probs") or {}
    if probs:
        modal = max(probs, key=probs.get)
        fill = CAT_COLOR[modal]
        op = 0.35 + 0.65 * probs[modal]
    else:
        fill, op = NO_DATA, 1.0
    hover = card.get("hover_html") or (
        f"<b>{card.get('name', 'United States')}</b>")
    abbr = card.get("abbr") or "US"
    body = "".join(f'<path d="{d}" stroke="{paper}" stroke-width="1"/>'
                   for _name, d in state_paths().values())
    inner = (f'<g class="nat" fill="{fill}" fill-opacity="{op:.2f}" '
             f'data-abbr="{abbr}" data-hover="{_esc(hover)}">{body}</g>')
    return _shell(dom_id, inner, ink, paper)


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace('"', "&quot;")
            .replace("<b>", "&lt;b&gt;__B__").replace("</b>", "__/B__")
            .replace("<br>", "__BR__")
            .replace("<", "&lt;").replace(">", "&gt;")
            .replace("&lt;b&gt;__B__", "<b>").replace("__/B__", "</b>")
            .replace("__BR__", "<br>"))
