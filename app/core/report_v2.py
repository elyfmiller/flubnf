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
  * reporting gaps render as explicit near-black states and annotated
    gaps in fans (constitutional rule 10), never smoothed over
  * fluid layout: no fixed max-width, the map scales with the window
  * forced dark: single-theme by design; every color painted explicitly

Deliberately dark-only on screen per Ely's spec (2026-08-17). The colors
and type are the console's own identity (nau.css dark tokens, DM Sans with
a system fallback and no webfont fetch), and a print stylesheet flips the
page to the console's light theme so the report prints as dark ink on a
light surface.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

# Console identity (nau.css dark theme, LANL Mesa-aligned): Near-Black
# ground, stepped indigo card, Cyan #34C0F0 as THE accent. The values below
# mirror the [data-theme="dark"] tokens in app/ui/static/nau.css so a color
# means the same thing in the console and in this export; the print
# stylesheet flips to the console's light-theme values.
INK = "#E9EAF4"; MUT = "#9AA1C4"; PAPER = "#0C0D17"; CARD = "#151729"
LINE = "#262A45"; ACCENT = "#34C0F0"
OK = "#4CC38A"; BAD = "#FB4653"
# the brand face with a system fallback: the report stays fully offline
# (no webfont fetch), so the stack simply upgrades to DM Sans wherever
# the font is installed
FONT_STACK = '"DM Sans",system-ui,-apple-system,"Segoe UI",sans-serif'
CATS = ("large_decrease", "decrease", "stable", "increase", "large_increase")
CAT_COLOR = {"large_decrease": "#2e7d4f", "decrease": "#7fc97f",
             "stable": "#b9b09b", "increase": "#e8a33d",
             "large_increase": "#c0392b"}
NO_DATA = "var(--map-nodata, #0a0a0a)"   # falls back to black in the fixed-dark report
CAT_LABEL = {c: c.replace("_", " ") for c in CATS}
# fan bands in Blue Slate #6E8FD0, the kit's data accent
QBANDS = ((0.025, 0.975, "rgba(110,143,208,0.13)", "95% interval"),
          (0.10, 0.90, "rgba(110,143,208,0.20)", "80% interval"),
          (0.25, 0.75, "rgba(110,143,208,0.30)", "50% interval"))

# Shared embed config: wheel zooms both ways, double-click resets, hover
# modebar offers zoom-out/reset (lasso/box-select/autoscale pruned);
# responsive so figures track their container when it appears or resizes.
PLOTLY_CONFIG = {"scrollZoom": True, "doubleClick": "reset+autosize",
                 "responsive": True,
                 "displayModeBar": "hover", "displaylogo": False,
                 "modeBarButtonsToRemove": ["lasso2d", "select2d",
                                            "autoScale2d"]}


def _fig_layout(fig, height=340, title="", legend=False):
    fig.update_layout(
        template=None, paper_bgcolor=CARD, plot_bgcolor=CARD,
        font=dict(color=INK, family=FONT_STACK, size=13),
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
               gaps=(), title="", settled=None):
    """Quantile fan vs observed. `gaps` = week offsets with no data.
    `settled`: optional [(date, value)...] of what actually happened after
    the forecast origin (backdated runs) -- drawn dotted; the legend entry
    doubles as its on/off toggle."""
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
                    hovertemplate="%{x|%b %-d}: %{y:.0f}<extra>forecast</extra>")
    fig.add_scatter(x=list(observed_times), y=list(observed),
                    mode="lines+markers",
                    line=dict(color=INK, width=1.6),
                    marker=dict(size=5), name="observed",
                    hovertemplate="%{x|%b %-d}: %{y:.0f}<extra>observed</extra>")
    if settled:
        fig.add_scatter(x=[d for d, _ in settled], y=[v for _, v in settled],
                        mode="lines+markers", name="what happened (settled)",
                        line=dict(color=INK, width=1.3, dash="dot"),
                        marker=dict(size=4),
                        hovertemplate="%{x|%b %-d}: %{y:.0f}"
                                      "<extra>settled</extra>")
    for g in gaps:
        if isinstance(g, str):          # ISO week date -> +/- 3.5 days
            import pandas as _pd
            t = _pd.Timestamp(g)
            g0, g1 = t - _pd.Timedelta(days=3.5), t + _pd.Timedelta(days=3.5)
        else:
            g0, g1 = g - 0.5, g + 0.5
        fig.add_vrect(x0=g0, x1=g1, fillcolor=LINE,
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
                 national_map_html: str = "", elapsed_s=None,
                 settings_html: str = "") -> Path:
    """state_cards: abbr -> hover-card data (choropleth).
    state_details: abbr -> dict(name, fan=…, cat=…, acc=…, table_rows=[…]).
    national: dict(fan=…, acc=…, summary_html=str).
    national_map_html: pre-rendered usmap.national_svg(...) output; when given,
    a 'state view' / 'national view' toggle appears above the map.
    elapsed_s: this run's wall time in seconds; when given, the footer states
    it. Omitted rather than guessed when the caller does not know.
    settings_html: the run-settings block (app.core.runs.settings_html),
    rendered beside the wall-time line so the report states exactly what
    produced it. Omitted when the caller does not supply it."""
    # Build-time SVG map (see usmap.py) -- the plotly geo choropleth fetched
    # its geometry from cdn.plot.ly at runtime and rendered empty offline/CSP.
    from app.core.usmap import svg_map
    cards_by_fips = {c["fips"]: c for c in state_cards.values() if "fips" in c}
    # only states that actually have a detail section invite a click
    map_html = svg_map(cards_by_fips, clickable=set(state_details))

    sections = []
    back_btn = ('<button class="backbtn" onclick="backToMap()">'
                '&larr; back to map</button>')
    for a, d in state_details.items():
        if a == "US":          # national renders in its own curated section
            continue
        rows = "".join(f'<tr><td>{r[0]}</td><td class="num">{r[1]:.0f}</td>'
                       "</tr>" for r in d.get("table_rows", []))
        sections.append(f"""
<section class="state" id="st-{a}" hidden>
  {back_btn}
  <h2>{d['name']}</h2>
  {('<p class="offseason">' + d['note'] + '</p>') if d.get('note') else ''}
  <div class="grid2">
    <div class="card">{_html(d['fan'])}</div>
    <div class="card">{_html(d['cat'])}
      <table><tr><th>week</th><th class="num">admissions</th></tr>{rows}</table></div>
  </div>
  {('<div class="card">' + _html(d['acc']) + '</div>') if d.get('acc') else ''}
</section>""")

    # emit each national chart card only when its figure exists -- two empty
    # bordered boxes say less than one honest hint line
    nat_cards = []
    if national.get("fan"):
        nat_cards.append(f'<div class="card">{_html(national["fan"])}</div>')
    if national.get("acc"):
        nat_cards.append(f'<div class="card">{_html(national["acc"])}</div>')
    nat_body = "\n  ".join(nat_cards) or (
        '<p class="hint">National fan and accuracy charts appear once the '
        'national model run lands.</p>')
    nat = f"""
<section class="state" id="st-US" hidden>
  {back_btn}
  <h2>United States</h2>
  {('<p class="offseason">' + national['note'] + '</p>') if national.get('note') else ''}
  {national.get('summary_html', '')}
  {nat_body}
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
        nat_map_div = f'<div id="map-national" class="mapcap" hidden>{national_map_html}</div>'

    # plotly.js goes in the head, once, iff any figure is embedded: a chart
    # must never render without its library, and a chartless report should
    # not carry the payload.
    if state_details or national.get("fan") or national.get("acc"):
        from plotly.offline import get_plotlyjs
        plotly_js = "<script>" + get_plotlyjs() + "</script>"
    else:
        plotly_js = ""

    # footer: what this report cost to produce, and what produced it. The
    # settings sit with the wall time because they answer the same question
    # a reader asks of an artifact months later: which run was this?
    footer = ""
    if elapsed_s is not None:
        from app.core.runs import fmt_hms
        footer = (f'<p class="hint" id="runtime">Run wall time: '
                  f'{fmt_hms(elapsed_s)} (h:mm:ss).</p>')
    if settings_html:
        footer += settings_html

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FluBNF weekly report · {reference_date}</title>
{plotly_js}
<style>
 /* console identity, fixed dark on screen: the tokens mirror nau.css
    [data-theme="dark"]; the print block below flips them to the console's
    light theme so the page prints as dark ink on a light surface. The
    inline usmap SVG reads --card, --accent, and --map-nodata: state
    borders match the card surface, and no-data reads as an explicit
    near-black gap against it (pale neutral on paper). */
 :root{{--bg:{PAPER};--card:{CARD};--ink:{INK};--mut:{MUT};--line:{LINE};
  --accent:{ACCENT};--gold:{ACCENT};--ok:{OK};--bad:{BAD};
  --map-nodata:#05060A;
  --shadow:0 1px 3px rgba(0,0,0,.5),0 4px 14px rgba(0,0,0,.35)}}
 *{{box-sizing:border-box}}
 body{{margin:0;background:var(--bg);color:var(--ink);
      font:400 15px/1.55 {FONT_STACK}}}
 main{{width:100%;margin:0 auto;padding:1.4rem 1.4rem 4rem}}
 .brandrow{{display:flex;align-items:baseline;gap:.6rem;flex-wrap:wrap;
  margin:0 0 .8rem}}
 .brand{{font-size:1.45rem;font-weight:700;letter-spacing:.01em}}
 .brand em{{color:var(--accent);font-style:normal}}
 .brandsub{{color:var(--mut);font-size:.9rem}}
 .brandrow .spacer{{flex:1}}
 h1{{font-size:1.45rem;font-weight:700;margin:.1rem 0 .3rem;
     text-wrap:balance}}
 h2{{font-size:1.15rem;font-weight:700;margin:.2rem 0 .6rem}}
 .card h2{{font-size:.8rem;margin:0 0 .55rem;text-transform:uppercase;
    letter-spacing:.05em;color:var(--mut);font-weight:600}}
 .sub{{color:var(--mut);margin:.2rem 0 1rem}}
 .card{{background:var(--card);border:1px solid var(--line);
        border-radius:10px;padding:.85rem 1rem;margin:.8rem 0;
        box-shadow:var(--shadow);overflow-x:auto}}
 .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}}
 @media(max-width:820px){{.grid2{{grid-template-columns:1fr}}}}
 .offseason{{color:var(--mut);font-size:.85rem;font-style:italic;
             margin:.2rem 0 .8rem}}
 /* in the header flow (not fixed) so it can never cover the title */
 #appback{{display:inline-block;background:var(--card);
  border:1px solid var(--line);border-radius:99px;padding:.3rem .8rem;
  color:var(--ink);text-decoration:none;font-size:.85rem}}
 #appback:hover{{border-color:var(--accent)}}
 .mapcap{{max-width:min(880px,72vw);margin:0 auto}}
 .mapcap svg{{max-height:58vh}}
 .legend{{display:flex;gap:1.1rem;flex-wrap:wrap;color:var(--mut);
          font-size:.82rem;margin:.4rem 0 0 .2rem}}
 .legend span{{display:inline-flex;align-items:center;gap:.35rem}}
 .sw{{width:13px;height:13px;border-radius:3px;display:inline-block;
     -webkit-print-color-adjust:exact;print-color-adjust:exact}}
 table{{border-collapse:collapse;font-size:.85rem;margin:.6rem .4rem;
        font-variant-numeric:tabular-nums}}
 td,th{{padding:.38rem .6rem;border-bottom:1px solid var(--line);
        text-align:left}}
 th{{color:var(--mut);font-weight:600;font-size:.72rem;
     text-transform:uppercase;letter-spacing:.04em}}
 td.num,th.num{{text-align:right}}
 tr.total td{{font-weight:750;border-top:2px solid var(--line);
              border-bottom:0}}
 /* the console's alert pair: below 1 beats baseline, everywhere */
 .ok{{color:var(--ok)}}.bad{{color:var(--bad)}}
 .relwis{{font-variant-numeric:tabular-nums;font-weight:650}}
 .num.hint{{color:var(--mut)}}
 button{{background:transparent;color:var(--gold);
         border:1px solid var(--gold);border-radius:8px;
         padding:.45rem .95rem;font:inherit;font-weight:650;cursor:pointer}}
 button:hover{{background:rgba(52,192,240,.14)}}
 button:focus-visible{{outline:2px solid var(--gold);outline-offset:2px}}
 .viewtoggle{{display:flex;gap:.5rem;margin:1rem 0 0}}
 .viewtoggle .on{{background:var(--gold);border-color:var(--gold);
                  color:{PAPER}}}
 .backbtn{{margin:.2rem 0 .6rem}}
 .hint{{color:var(--mut);font-size:.85rem}}
 @media print{{
  :root{{--bg:#FFFFFF;--card:#FFFFFF;--ink:#000F7E;--mut:#565E96;
   --line:#DCD8E9;--accent:#0173A9;--gold:#0173A9;
   --ok:#177245;--bad:#C42840;--map-nodata:#C9C5D8;--shadow:none}}
  body{{background:#FFFFFF;color:#000F7E}}
  button,select,.viewtoggle,#appback,.backbtn{{display:none!important}}
  .card{{box-shadow:none;break-inside:avoid}}
 }}
</style></head><body><main>
<header class="brandrow"><span class="brand"><em>Flu</em>BNF</span>
 <span class="brandsub">weekly forecast report</span>
 <span class="spacer"></span>
 <a id="appback" href="#" hidden
  onclick="history.back();return false">&larr; back to FluBNF</a>
</header>
<h1>US influenza forecast</h1>
<p class="sub">week of {reference_date} · PF-SIHRS · click a state for detail
 · Ctrl+scroll to zoom (⌘ on Mac), drag to pan, double-click to reset
 · <button id="natbtn">national detail</button></p>
{view_toggle}
<div class="card" id="map-anchor">
<div id="map-state" class="mapcap">{map_html}</div>
 {nat_map_div}
 <div class="legend">
  {"".join(f'<span><i class="sw" style="background:{CAT_COLOR[c]}"></i>{CAT_LABEL[c]}</span>' for c in CATS)}
  <span><i class="sw" style="background:{NO_DATA}"></i>no data (reporting gap)</span>
 </div>
 <div class="legend">
  <span><i class="sw" style="background:{CAT_COLOR['increase']};opacity:.64"></i>leaning</span>
  <span><i class="sw" style="background:{CAT_COLOR['increase']};opacity:.82"></i>likely</span>
  <span><i class="sw" style="background:{CAT_COLOR['increase']};opacity:1"></i>confident</span>
  <span>deeper shade = more confident</span>
 </div>
</div>
<p class="hint">Hover a state for its full outlook. States in the no-data
shade reported nothing this week: shown as gaps, never interpolated.</p>
{"".join(sections)}
{nat}
<script>
window.showState = show;
var _ab = document.getElementById('appback');
if (_ab && history.length > 1) {{ _ab.hidden = false; }}
if (location.hash && location.hash.startsWith('#st-') &&
    document.getElementById(location.hash.slice(1))) {{
  show(location.hash.slice(1));
}}
function show(id) {{
  const el = document.getElementById(id);
  if (!el) return;
  document.querySelectorAll('section.state').forEach(s => s.hidden = true);
  el.hidden = false;
  if (window.Plotly)
    el.querySelectorAll('.js-plotly-plot').forEach(g => Plotly.Plots.resize(g));
  el.scrollIntoView({{behavior: 'smooth'}});
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
{footer}
</main></body></html>"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    return out_path
