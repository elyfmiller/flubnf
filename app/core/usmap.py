"""Build-time US choropleth: TopoJSON -> inline SVG paths, zero runtime fetches.

Replaces the plotly geo choropleth, which loads its geometry from cdn.plot.ly
AT RUNTIME and therefore renders an empty box in any CSP-sandboxed or offline
context (found the hard way, 2026-08-17). Geometry is vendored:
app/core/assets/states-albers-10m.json (us-atlas, US Census-derived, public
domain, pre-projected Albers composite with AK/HI insets on a 975x610 plane).

Hover card, click drill-down, and pan/zoom are vanilla JS on the inline SVG --
no library, works from file://, artifacts, or any static host. A clicked
(selected) state keeps its categorical fill and gains a cyan #34C0F0 OUTLINE
(brand accent, stroke only) so selection never collides with the green
category colors. Pan/zoom mutates
the SVG viewBox: Ctrl/Cmd+wheel zooms about the cursor (plain scroll keeps
scrolling the page), drag pans within a clamped extent, double-click resets.
A press that travels < 5px still counts as a state click (drag never
click-throughs).

Two render modes:
  * svg_map(cards_by_fips)  -- per-state choropleth (modal category color,
    opacity by its probability; no-data states take --map-nodata, falling
    back to near-black)
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
# Emitted as a CSS variable so host pages can soften it per theme (the app's
# light theme uses a pale neutral; the fixed-dark report falls back to black).
NO_DATA = "var(--map-nodata, #0a0a0a)"


def cat_fill(cat: str) -> str:
    """One category's fill, as a CSS variable with the classic literal as
    its fallback. The console defines --cat-* in every theme block of
    nau.css and remaps them under data-vision="cvd" (the red-green-safe
    blue/orange scale), so the map and its legend follow the color-vision
    mode with no server round trip; a standalone export without those
    tokens (the fixed-dark weekly report) falls back to CAT_COLOR."""
    return f"var(--cat-{cat.replace('_', '-')}, {CAT_COLOR[cat]})"


def _card_fill(card: dict) -> tuple:
    """(fill, opacity) for one hover card, the ONE fill computation every
    map surface uses: modal category color, opacity by its probability;
    no data takes the explicit no-data tone at full opacity. Shared by the
    server-side renders (svg_map, national_svg) and the client-side model
    toggle's swap payloads, so switching models recolors with exactly the
    computation the server rendered."""
    probs = (card or {}).get("probs") or {}
    if probs:
        modal = max(probs, key=probs.get)
        return cat_fill(modal), 0.55 + 0.45 * probs[modal]
    return NO_DATA, 1.0

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
# Zoom (Ctrl/Cmd+wheel) clamps between the full extent (1x) and 40x; pan is
# clamped so ~20% of the country always stays in view. Drag distance is
# measured from the mousedown point; a press that never travels 5px is still
# a click, and its drill-down waits 250ms so double-click (reset) can cancel.
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
  // keep >= 20% of the base extent in view; fully zoomed out snaps home
  const clamp = () => {
    if (vb[2] >= VB[2]) { vb = VB.slice(); return; }
    vb[0] = Math.min(Math.max(vb[0], VB[0] - vb[2] * 0.8),
                     VB[0] + VB[2] - vb[2] * 0.2);
    vb[1] = Math.min(Math.max(vb[1], VB[1] - vb[3] * 0.8),
                     VB[1] + VB[3] - vb[3] * 0.2);
  };
  const toSvg = ev => {
    const r = svg.getBoundingClientRect();
    return [vb[0] + (ev.clientX - r.left) / r.width * vb[2],
            vb[1] + (ev.clientY - r.top) / r.height * vb[3]];
  };
  // Ctrl/Cmd + wheel zooms about the cursor; plain scroll keeps scrolling
  // the page (trackpad pinch arrives as wheel with ctrlKey=true)
  svg.addEventListener('wheel', ev => {
    if (!ev.ctrlKey && !ev.metaKey) return;
    ev.preventDefault();
    const [sx, sy] = toSvg(ev);
    let f = ev.deltaY > 0 ? 1.25 : 0.8;
    f = Math.min(Math.max(vb[2] * f, VB[2] / 40), VB[2]) / vb[2];
    vb = [sx - (sx - vb[0]) * f, sy - (sy - vb[1]) * f,
          vb[2] * f, vb[3] * f];
    clamp();
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
    clamp();
    apply();
    if (dist >= 5) tip.style.display = 'none';
  });
  window.addEventListener('mouseup', () => { down = null; });
  // double-click resets to the full extent (and cancels the pending
  // single-click drill-down so it never yanks the user to a state page)
  let clickTimer = null;
  svg.addEventListener('dblclick', ev => {
    clearTimeout(clickTimer);
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
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let x = ev.clientX - r.left + 14, y = ev.clientY - r.top + 14;
    if (x + tw > r.width) x = Math.max(4, ev.clientX - r.left - tw - 14);
    if (y + th > r.height) y = Math.max(4, ev.clientY - r.top - th - 14);
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  });
  svg.addEventListener('mouseleave', () => tip.style.display = 'none');
  // click drill-down, suppressed after a real drag (pointer moved >= 5px)
  // and delayed 250ms so a double-click resets instead of drilling down
  svg.addEventListener('click', ev => {
    if (dist >= 5) return;
    const t = ev.target.closest ? ev.target.closest('[data-abbr]') : null;
    const a = t && t.dataset.abbr;
    if (t) {                       // mark selection: cyan ring, fill untouched
      svg.querySelectorAll('.sel').forEach(n => n.classList.remove('sel'));
      t.classList.add('sel');
      if (t.parentNode === svg) svg.appendChild(t);  // ring above neighbors
    }
    if (a && !window.showState && window.MAP_LINK) {
      clearTimeout(clickTimer);
      clickTimer = setTimeout(() => { location = window.MAP_LINK + '#st-' + a; }, 250);
      return;
    }
    if (a && window.showState) {
      clearTimeout(clickTimer);
      clickTimer = setTimeout(() => window.showState('st-' + a), 250);
    }
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
 #{dom_id} .st.noclick{{cursor:default}}
 #{dom_id} .st:hover{{stroke:var(--accent,{ink});stroke-width:1.6}}
 #{dom_id} .nat{{cursor:pointer}}
 #{dom_id} .nat:hover path{{stroke:var(--accent,{ink});stroke-width:1.2}}
 /* selection = cyan brand-accent RING (stroke, never fill), so the
    categorical color underneath stays legible */
 #{dom_id} .st.sel{{stroke:var(--accent,#34C0F0);stroke-width:2.6;
   stroke-linejoin:round}}
 #{dom_id} .nat.sel path{{stroke:var(--accent,#34C0F0);stroke-width:2}}
</style>
{inner}
</svg>
<div id="{dom_id}-tip" style="position:absolute;pointer-events:none;display:none;
 background:#151729;border:1px solid #262A45;border-radius:10px;
 padding:.6rem .8rem;font-size:.82rem;line-height:1.45;color:{ink};
 max-width:240px;box-shadow:0 6px 24px rgba(0,0,0,.5);z-index:10"></div>
</div>""" + (_JS.replace("__ID__", dom_id) if interactive else "")


def svg_map(cards_by_fips: dict, ink="#e9ecf2",
            paper="var(--card, #0C0D17)",
            dom_id: str = "usmap", interactive=True, clickable=None) -> str:
    """cards_by_fips: fips -> {probs, name, abbr, hover_html} ({} = no data).

    Emits the full SVG + tooltip div + interaction script (hover card, click
    drill-down, wheel-zoom / drag-pan / dblclick-reset). Each state path
    carries data-attributes; JS is dependency-free. `dom_id` must be unique
    per page when several maps are embedded together. `clickable` (a set of
    abbrs) limits drill-down to states that have somewhere to go: the rest
    keep their hover card but lose the pointer cursor, the data-abbr hook,
    and the 'click for details' hint. None = every state is clickable.
    """
    paths = []
    for fips, (topo_name, d) in state_paths().items():
        card = cards_by_fips.get(fips, {})
        fill, op = _card_fill(card)
        hover = card.get("hover_html") or (
            f"<b>{card.get('name', topo_name)}</b><br>no reported data "
            f"(reporting gap)")
        abbr = card.get("abbr", "")
        can_click = bool(abbr) and (clickable is None or abbr in clickable)
        if can_click:
            hover += "<br>click for details"
        cls = "st" if can_click else "st noclick"
        click_attr = f'data-abbr="{abbr}" ' if can_click else ""
        # data-fips is the model toggle's hook: the swap script recolors
        # each state by fips without re-rendering the geometry
        paths.append(
            f'<path d="{d}" fill="{fill}" fill-opacity="{op:.2f}" '
            f'stroke="{paper}" stroke-width="1" class="{cls}" '
            f'data-fips="{fips}" '
            f'{click_attr}data-hover="{_esc(hover)}"/>')
    return _shell(dom_id, "".join(paths), ink, paper, interactive)


def national_svg(us_card: dict, ink="#e9ecf2",
                 paper="var(--card, #0C0D17)",
                 dom_id: str = "usmap-nat") -> str:
    """National mode: same geography, one shared fill.

    us_card has the same shape as a state card: {probs, name, abbr, fips,
    hover_html}. Every state is filled with the national modal category's
    color (opacity by its probability); hovering anywhere shows the national
    hover card; clicking anywhere calls window.showState('st-US'). One <g>
    with a single shared fill, one tooltip; pan/zoom identical to svg_map.
    """
    card = us_card or {}
    fill, op = _card_fill(card)
    hover = card.get("hover_html") or (
        f"<b>{card.get('name', 'United States')}</b>")
    abbr = card.get("abbr") or "US"
    body = "".join(f'<path d="{d}" stroke="{paper}" stroke-width="1"/>'
                   for _name, d in state_paths().values())
    inner = (f'<g class="nat" fill="{fill}" fill-opacity="{op:.2f}" '
             f'data-abbr="{abbr}" data-hover="{_esc(hover)}">{body}</g>')
    return _shell(dom_id, inner, ink, paper)


# ---------------------------------------------------------------------------
# The outlook model toggle: one map, N models, client-side fill swap.
#
# The bundle (report_v2, v3) carries hover cards for EVERY available model,
# all computed by the same quantile-CDF path. The map is rendered once for
# the default model; the toggle below recolors it in place -- fill, opacity,
# hover card, and the surface's model label -- from a payload built by the
# SAME _card_fill computation the server render used, so switching models
# can never disagree with a server-rendered map of that model. Shared by the
# home outlook and the weekly report (both embed the same emitted script).
# ---------------------------------------------------------------------------

def state_swap_payload(cards_by_fips: dict) -> dict:
    """fips -> {f: fill, o: opacity, h: hover_html} for every state on the
    map, from one model's hover cards (the svg_map computation as data)."""
    out = {}
    for fips, (topo_name, _d) in state_paths().items():
        card = cards_by_fips.get(fips, {})
        fill, op = _card_fill(card)
        hover = card.get("hover_html") or (
            f"<b>{card.get('name', topo_name)}</b><br>no reported data "
            f"(reporting gap)")
        out[fips] = {"f": fill, "o": round(op, 2), "h": hover}
    return out


def nat_swap_payload(us_card: dict) -> dict:
    """{f, o, h} for the national view's shared fill, or {} without a card
    (the swap script then leaves the national group as rendered)."""
    if not us_card:
        return {}
    fill, op = _card_fill(us_card)
    hover = us_card.get("hover_html") or (
        f"<b>{us_card.get('name', 'United States')}</b>")
    return {"f": fill, "o": round(op, 2), "h": hover}


def model_toggle(models: list, labels: dict, default: str, payload: dict,
                 group_id: str = "outlook-model", dom_id: str = "usmap",
                 nat_dom_id: str = "usmap-nat", btn_class: str = "",
                 active_class: str = "on",
                 wrap_class: str = "viewtoggle") -> str:
    """The compact model switch above an outlook map: aria-pressed buttons
    plus the swap script.

    models: the models the payload actually carries, in display order.
    labels: model -> surface label (report_v2.MODEL_LABEL).
    payload: model -> {"states": state_swap_payload(...),
                       "us": nat_swap_payload(...)}.
    The buttons state aria-pressed and swap `active_class` (the host's own
    selected-button treatment: 'gold' in the console, 'on' in the report);
    every element carrying data-mapmodel-label follows the selected model's
    label, so the surface never shows one model's map under another's name.
    Callers emit the toggle only when two or more models exist -- a
    one-model surface needs no switch, and an older bundle without
    per-model cards renders exactly as before."""
    btns = []
    for m in models:
        on = m == default
        cls = f"{btn_class} {active_class}".strip() if on else btn_class
        cls_attr = f' class="{cls}"' if cls else ""
        btns.append(
            f'<button type="button"{cls_attr} '
            f'data-mmodel="{m}" aria-pressed="{str(on).lower()}">'
            f'{_esc(labels.get(m, m))}</button>')
    pj = json.dumps(payload).replace("</", "<\\/")
    lj = json.dumps({m: labels.get(m, m) for m in models}).replace("</",
                                                                   "<\\/")
    return f"""
<div class="{wrap_class}" id="{group_id}" role="group"
     aria-label="Outlook model">{''.join(btns)}</div>
<script>
(function() {{
  var P = {pj}, LB = {lj};
  var group = document.getElementById('{group_id}');
  if (!group) return;
  var ACT = '{active_class}';
  function setModel(m) {{
    var d = P[m];
    if (!d) return;
    group.querySelectorAll('button[data-mmodel]').forEach(function(b) {{
      var on = b.dataset.mmodel === m;
      b.setAttribute('aria-pressed', String(on));
      b.classList.toggle(ACT, on);
    }});
    document.querySelectorAll('[data-mapmodel-label]').forEach(function(e) {{
      e.textContent = LB[m] || m;
    }});
    var svg = document.getElementById('{dom_id}');
    if (svg && d.states)
      svg.querySelectorAll('path[data-fips]').forEach(function(p) {{
        var s = d.states[p.dataset.fips];
        if (!s) return;
        p.setAttribute('fill', s.f);
        p.setAttribute('fill-opacity', s.o);
        // the click affordance rides the path, not the model: a state
        // with a drill-down keeps its hint whichever model colors it
        p.dataset.hover = s.h + (p.dataset.abbr
                                 ? '<br>click for details' : '');
      }});
    var nat = document.querySelector('#{nat_dom_id} g.nat');
    if (nat && d.us) {{
      nat.setAttribute('fill', d.us.f);
      nat.setAttribute('fill-opacity', d.us.o);
      nat.dataset.hover = d.us.h;
    }}
  }}
  group.addEventListener('click', function(e) {{
    var b = e.target.closest ? e.target.closest('button[data-mmodel]')
                             : null;
    if (b) setModel(b.dataset.mmodel);
  }});
}})();
</script>"""


def map_legend() -> str:
    """One-line legend for the categorical choropleth: the five outlook
    categories in their fixed colors plus the no-data tone, each as a swatch
    (the .sw class the season player's toggles already use) with its label.
    Emitted beside every map that colors by category, so the encoding never
    has to be learned by hovering. Swatches ride the same --cat-* tokens as
    the map fills, so the legend follows the color-vision mode with them."""
    items = [
        (cat_fill(c), c.replace("_", " ")) for c in CATS
    ] + [(NO_DATA, "no data")]
    spans = "".join(
        f'<span><span class="sw" style="background:{color}"></span>'
        f'{label}</span>'
        for color, label in items)
    return f'<p class="hint maplegend">{spans}</p>'


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace('"', "&quot;")
            .replace("<b>", "&lt;b&gt;__B__").replace("</b>", "__/B__")
            .replace("<br>", "__BR__")
            .replace("<", "&lt;").replace(">", "&gt;")
            .replace("&lt;b&gt;__B__", "<b>").replace("__/B__", "</b>")
            .replace("__BR__", "<br>"))
