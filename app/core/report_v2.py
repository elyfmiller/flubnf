"""Weekly HTML report v2 — real US map, drill-down, forced dark.

One self-contained file per week (plotly.js embedded once, no network):
  * geographic US choropleth, states shaded by modal rate-change category,
    intensity by its probability; hover = full stats card
  * optional national map view (one shared fill = national modal category),
    toggled with 'state view' / 'national view' buttons above the map
  * CLICK a state -> its section: forecast fan vs observed, categorical bar,
    accuracy over time (relWIS vs baseline), recent-data table; every section
    has a '<- back to map' button (window.backToMap)
  * a National section with the same drill-down
  * reporting gaps render as explicit black states (#0a0a0a) and annotated
    gaps in fans (constitutional rule 10), never smoothed over
  * fluid layout: no fixed max-width, the map scales with the window
  * forced dark: single-theme by design; every color painted explicitly

Deliberately dark-only per Ely's spec (2026-08-17).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

INK = "#e9ecf2"; MUT = "#93a1b5"; PAPER = "#0a1626"; CARD = "#0f2440"
LINE = "#1d3a5f"; ACCENT = "#ffc72c"
CATS = ("large_decrease", "decrease", "stable", "increase", "large_increase")
CAT_COLOR = {"large_decrease": "#2e7d4f", "decrease": "#7fc97f",
             "stable": "#b9b09b", "increase": "#e8a33d",
             "large_increase": "#c0392b"}
NO_DATA = "#0a0a0a"
CAT_LABEL = {c: c.replace("_", " ") for c in CATS}
QBANDS = ((0.025, 0.975, "rgba(106,165,216,0.13)", "95% interval"),
          (0.10, 0.90, "rgba(106,165,216,0.20)", "80% interval"),
          (0.25, 0.75, "rgba(106,165,216,0.30)", "50% interval"))

# Shared embed config: wheel zooms both ways, double-click resets, hover
# modebar offers zoom-out/reset (lasso/box-select/autoscale pruned).
PLOTLY_CONFIG = {"scrollZoom": True, "doubleClick": "reset+autosize",
                 "displayModeBar": "hover", "displaylogo": False,
                 "modeBarButtonsToRemove": ["lasso2d", "select2d",
                                            "autoScale2d"]}


def _fig_layout(fig, height=340, title="", legend=False):
    fig.update_layout(
        template=None, paper_bgcolor=CARD, plot_bgcolor=CARD,
        font=dict(color=INK, family="system-ui", size=13),
        margin=dict(l=44, r=16, t=40 if title else 16, b=64 if legend else 36),
        height=height, title=dict(text=title, font=dict(size=15)),
        xaxis=dict(gridcolor=LINE, zerolinecolor=LINE),
        yaxis=dict(gridcolor=LINE, zerolinecolor=LINE),
        showlegend=legend,
        legend=dict(orientation="h", x=0, xanchor="left",
                    y=-0.18, yanchor="top",
                    font=dict(size=11, color=INK),
                    bgcolor="rgba(0,0,0,0)"))
    return fig


def fan_figure(observed_times, observed, forecast_times, samples_by_h,
               gaps=(), title=""):
    """Quantile fan vs observed. `gaps` = week offsets with no data."""
    import plotly.graph_objects as go
    fig = go.Figure()
    med = []
    for lo, hi, color, band_name in QBANDS:
        upper, lower = [], []
        for h in forecast_times:
            s = np.asarray(samples_by_h[str(h)], float)
            s = s[np.isfinite(s)]
            upper.append(float(np.quantile(s, hi)))
            lower.append(float(np.quantile(s, lo)))
        fig.add_scatter(x=list(forecast_times) + list(forecast_times)[::-1],
                        y=upper + lower[::-1], fill="toself", fillcolor=color,
                        line=dict(width=0), hoverinfo="skip",
                        name=band_name, showlegend=True)
    med = [float(np.median(np.asarray(samples_by_h[str(h)], float)))
           for h in forecast_times]
    fig.add_scatter(x=list(forecast_times), y=med, mode="lines+markers",
                    line=dict(color=ACCENT, width=2.2),
                    name="median forecast",
                    hovertemplate="wk %{x}: %{y:.0f}<extra>forecast</extra>")
    fig.add_scatter(x=list(observed_times), y=list(observed),
                    mode="lines+markers",
                    line=dict(color=INK, width=1.6),
                    marker=dict(size=5), name="observed",
                    hovertemplate="wk %{x}: %{y:.0f}<extra>observed</extra>")
    for g in gaps:
        fig.add_vrect(x0=g - 0.5, x1=g + 0.5, fillcolor="#3a3a40",
                      opacity=0.5, line_width=0,
                      annotation_text="no data", annotation_font_color=MUT,
                      annotation_font_size=10)
    return _fig_layout(fig, title=title, legend=True)


def accuracy_figure(dates, relwis, title="forecast accuracy (relWIS vs baseline)"):
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_hline(y=1.0, line=dict(color=MUT, dash="dot", width=1),
                  annotation_text="baseline", annotation_font_color=MUT)
    fig.add_scatter(x=list(dates), y=list(relwis), mode="lines+markers",
                    line=dict(color=ACCENT, width=2), name="relWIS",
                    hovertemplate="%{x}: %{y:.2f}<extra></extra>")
    f = _fig_layout(fig, height=260, title=title)
    f.update_yaxes(rangemode="tozero")
    return f


def cat_bar(probs):
    import plotly.graph_objects as go
    fig = go.Figure(go.Bar(
        x=[CAT_LABEL[c] for c in CATS], y=[probs.get(c, 0) for c in CATS],
        marker_color=[CAT_COLOR[c] for c in CATS],
        hovertemplate="%{x}: %{y:.0%}<extra></extra>"))
    f = _fig_layout(fig, height=230, title="rate-change outlook (1 wk)")
    f.update_yaxes(tickformat=".0%", range=[0, 1])
    return f


def _html(fig, include_js=False, div_id=None):
    return fig.to_html(full_html=False,
                       include_plotlyjs=True if include_js else False,
                       div_id=div_id, config=dict(PLOTLY_CONFIG))


def build_report(reference_date: str, state_cards: dict, state_details: dict,
                 national: dict, out_path: Path,
                 national_map_html: str = "") -> Path:
    """state_cards: abbr -> hover-card data (choropleth).
    state_details: abbr -> dict(name, fan=…, cat=…, acc=…, table_rows=[…]).
    national: dict(fan=…, acc=…, summary_html=str).
    national_map_html: pre-rendered usmap.national_svg(...) output; when given,
    a 'state view' / 'national view' toggle appears above the map."""
    # Build-time SVG map (see usmap.py) -- the plotly geo choropleth fetched
    # its geometry from cdn.plot.ly at runtime and rendered empty offline/CSP.
    from app.core.usmap import svg_map
    cards_by_fips = {c["fips"]: c for c in state_cards.values() if "fips" in c}
    map_html = svg_map(cards_by_fips)

    sections = []
    _first = [True]
    def _sec_html(fig):
        h = _html(fig, include_js=_first[0])
        _first[0] = False
        return h
    back_btn = ('<button class="backbtn" onclick="backToMap()">'
                '&larr; back to map</button>')
    for a, d in state_details.items():
        rows = "".join(f"<tr><td>{r[0]}</td><td>{r[1]:.0f}</td></tr>"
                       for r in d.get("table_rows", []))
        sections.append(f"""
<section class="state" id="st-{a}" hidden>
  {back_btn}
  <h2>{d['name']}</h2>
  <div class="grid2">
    <div class="card">{_sec_html(d['fan'])}</div>
    <div class="card">{_html(d['cat'])}
      <table><tr><th>week</th><th>admissions</th></tr>{rows}</table></div>
  </div>
  <div class="card">{_html(d['acc'])}</div>
</section>""")

    nat = f"""
<section class="state" id="st-US" hidden>
  {back_btn}
  <h2>United States</h2>
  {national.get('summary_html', '')}
  <div class="card">{_html(national['fan']) if national.get('fan') else ''}</div>
  <div class="card">{_html(national['acc']) if national.get('acc') else ''}</div>
</section>"""

    # view toggle + second (national) map, only when a national map was given
    view_toggle = ""
    nat_map_div = ""
    if national_map_html:
        view_toggle = """
<div class="viewtoggle">
 <button id="btn-state-view" class="on">state view</button>
 <button id="btn-national-view">national view</button>
</div>"""
        nat_map_div = f'<div id="map-national" hidden>{national_map_html}</div>'

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FluBNF — week of {reference_date}</title>
<style>
 body{{margin:0;background:{PAPER};color:{INK};font:15px/1.55 system-ui}}
 main{{width:100%;box-sizing:border-box;margin:0 auto;
       padding:1.6rem 1.4rem 4rem}}
 h1{{font-size:1.45rem;margin:.2rem 0}} h2{{font-size:1.15rem}}
 .sub{{color:{MUT};margin:.2rem 0 1rem}}
 .card{{background:{CARD};border:1px solid {LINE};border-radius:14px;
        padding:.8rem;margin:.8rem 0;overflow-x:auto}}
 .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:.8rem}}
 @media(max-width:820px){{.grid2{{grid-template-columns:1fr}}}}
 .legend{{display:flex;gap:1.1rem;flex-wrap:wrap;color:{MUT};font-size:.82rem;
          margin:.4rem 0 0 .2rem}}
 .legend span{{display:inline-flex;align-items:center;gap:.35rem}}
 .sw{{width:13px;height:13px;border-radius:3px;display:inline-block}}
 table{{border-collapse:collapse;font-size:.85rem;margin:.6rem .4rem;
        font-variant-numeric:tabular-nums}}
 td,th{{padding:.25rem .7rem;border-bottom:1px solid {LINE};text-align:left}}
 button{{background:{CARD};color:{INK};border:1px solid {LINE};
         border-radius:9px;padding:.45rem .9rem;font:inherit;cursor:pointer}}
 button:hover{{border-color:{ACCENT}}}
 button:focus-visible{{outline:2px solid {ACCENT};outline-offset:2px}}
 .viewtoggle{{display:flex;gap:.5rem;margin:1rem 0 0}}
 .viewtoggle .on{{border-color:{ACCENT};color:{ACCENT}}}
 .backbtn{{margin:.2rem 0 .6rem}}
 .hint{{color:{MUT};font-size:.85rem}}
</style></head><body><main>
<h1>US influenza forecast</h1>
<p class="sub">week of {reference_date} · PF-SIHRS · click a state for detail
 · zoom with the mouse wheel, drag to pan, double-click to reset
 · <button id="natbtn">national detail</button></p>
{view_toggle}
<div class="card" id="map-anchor">
 <div id="map-state">{map_html}</div>
 {nat_map_div}
 <div class="legend">
  {"".join(f'<span><i class="sw" style="background:{CAT_COLOR[c]}"></i>{CAT_LABEL[c]}</span>' for c in CATS)}
  <span><i class="sw" style="background:{NO_DATA}"></i>no data (reporting gap)</span>
 </div>
</div>
<p class="hint">Hover a state for its full outlook. Black states reported no
data this week — shown as gaps, never interpolated.</p>
{"".join(sections)}
{nat}
<script>
window.showState = show;
function show(id) {{
  document.querySelectorAll('section.state').forEach(s => s.hidden = true);
  const el = document.getElementById(id);
  if (el) {{ el.hidden = false; el.scrollIntoView({{behavior: 'smooth'}}); }}
}}
window.backToMap = function() {{
  document.querySelectorAll('section.state').forEach(s => s.hidden = true);
  const m = document.getElementById('map-anchor');
  if (m) m.scrollIntoView({{behavior: 'smooth'}});
}};
document.getElementById('natbtn').addEventListener('click', () => show('st-US'));
(function() {{
  const mS = document.getElementById('map-state'),
        mN = document.getElementById('map-national'),
        bS = document.getElementById('btn-state-view'),
        bN = document.getElementById('btn-national-view');
  if (!mN || !bS || !bN) return;
  const setView = v => {{
    mS.hidden = (v === 'national');
    mN.hidden = (v === 'state');
    bS.classList.toggle('on', v === 'state');
    bN.classList.toggle('on', v === 'national');
  }};
  bS.addEventListener('click', () => setView('state'));
  bN.addEventListener('click', () => setView('national'));
}})();
</script>
</main></body></html>"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    return out_path
