"""Build-time US choropleth: TopoJSON -> inline SVG paths, zero runtime fetches.

Replaces the plotly geo choropleth, which loads its geometry from cdn.plot.ly
AT RUNTIME and therefore renders an empty box in any CSP-sandboxed or offline
context (found the hard way, 2026-08-17). Geometry is vendored:
app/core/assets/states-albers-10m.json (us-atlas, US Census-derived, public
domain, pre-projected Albers composite with AK/HI insets on a 975x610 plane).

Hover card and click drill-down are ~30 lines of vanilla JS on <path>
elements -- no library, works from file://, artifacts, or any static host.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ASSET = Path(__file__).parent / "assets" / "states-albers-10m.json"

CATS = ("large_decrease", "decrease", "stable", "increase", "large_increase")
CAT_COLOR = {"large_decrease": "#3d7ab8", "decrease": "#79a8cf",
             "stable": "#8a8a82", "increase": "#d99a6b",
             "large_increase": "#c65744"}
NO_DATA = "#132c4d"


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


def svg_map(cards_by_fips: dict, ink="#e9ecf2", paper="#0a1626") -> str:
    """cards_by_fips: fips -> {probs, name, abbr, hover_html} ({} = no data).

    Emits the full SVG + tooltip div + interaction script. Each state path
    carries data-attributes; JS is dependency-free.
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
    return f"""
<div id="mapwrap" style="position:relative">
<svg id="usmap" viewBox="0 0 975 610" xmlns="http://www.w3.org/2000/svg"
     style="max-width:100%;height:auto;display:block">
<style>
 .st{{cursor:pointer;transition:fill-opacity .12s}}
 .st:hover{{stroke:{ink};stroke-width:1.6}}
</style>
{''.join(paths)}
</svg>
<div id="maptip" style="position:absolute;pointer-events:none;display:none;
 background:#1d1d21;border:1px solid #2c2c31;border-radius:10px;
 padding:.6rem .8rem;font-size:.82rem;line-height:1.45;color:{ink};
 max-width:240px;box-shadow:0 6px 24px rgba(0,0,0,.5);z-index:10"></div>
</div>
<script>
(function() {{
  const tip = document.getElementById('maptip');
  const wrap = document.getElementById('mapwrap');
  document.querySelectorAll('#usmap .st').forEach(p => {{
    p.addEventListener('mousemove', ev => {{
      tip.innerHTML = p.dataset.hover;
      tip.style.display = 'block';
      const r = wrap.getBoundingClientRect();
      let x = ev.clientX - r.left + 14, y = ev.clientY - r.top + 14;
      if (x + 250 > r.width) x -= 270;
      tip.style.left = x + 'px'; tip.style.top = y + 'px';
    }});
    p.addEventListener('mouseleave', () => tip.style.display = 'none');
    p.addEventListener('click', () => {{
      const a = p.dataset.abbr;
      if (a && window.showState) window.showState('st-' + a);
    }});
  }});
}})();
</script>"""


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace('"', "&quot;")
            .replace("<b>", "&lt;b&gt;__B__").replace("</b>", "__/B__")
            .replace("<br>", "__BR__")
            .replace("<", "&lt;").replace(">", "&gt;")
            .replace("&lt;b&gt;__B__", "<b>").replace("__/B__", "</b>")
            .replace("__BR__", "<br>"))
