"""PRODUCTION: the weekly run report (server._write_weekly_report,
/output/report refresh via render_bundle).

The weekly run report (the "v2" is historical): one self-contained,
theme-aware HTML file per week (plotly.js embedded once, no network).

  * build-time SVG US map (usmap), states shaded by modal rate-change
    category, intensity by probability, hover card; optional national map
    view and a per-model outlook toggle
  * click a state -> its section (fan vs observed, categorical bar, recent
    data), each with a back-to-map button; a National section likewise
  * no-data states are explicit and claim only what was checked: in the
    run's recorded scope = reporting gap, outside = 'not fitted in this
    run', no scope record = 'no data'; fan gaps annotated, never smoothed
  * nau.css token blocks embedded verbatim; a boot script resolves the
    theme at open (console localStorage same-origin, else OS preferences);
    print is always light
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np

# build-time chart palette (nau.css dark theme): figures are built with these
# literals and re-resolved against the page tokens at open (_retint_js)
INK = "#E9EAF4"; MUT = "#9AA1C4"; PAPER = "#0C0D17"; CARD = "#151729"
LINE = "#262A45"; ACCENT = "#34C0F0"
OK = "#4CC38A"; BAD = "#FB4653"
# DM Sans where installed, system fallback: no webfont fetch
FONT_STACK = '"DM Sans",system-ui,-apple-system,"Segoe UI",sans-serif'
CATS = ("large_decrease", "decrease", "stable", "increase", "large_increase")
CAT_COLOR = {"large_decrease": "#2e7d4f", "decrease": "#7fc97f",
             "stable": "#b9b09b", "increase": "#e8a33d",
             "large_increase": "#c0392b"}
NO_DATA = "var(--map-nodata, #0a0a0a)"   # falls back to black without tokens
CAT_LABEL = {c: c.replace("_", " ") for c in CATS}

#: the one source of the embedded theme tokens, hence a builder input
NAU_CSS = Path(__file__).resolve().parents[1] / "ui" / "static" / "nau.css"
#: the shared player core carries the one member-color map (marked JSON)
PLAYER_SRC = Path(__file__).resolve().parents[1] / "ui" / "static" \
    / "player.js"

#: equal to the player's map; used only if its marked JSON cannot be read
_MEMBER_COLOR_FALLBACK = {"ensemble": "#34C0F0", "pf": "#1979FF",
                          "analogue": "#FFC72C", "pf2s": "#A66395"}


def model_colors() -> dict:
    """The one member-color map: player.js's marked JSON literal, parsed so
    every Python surface wears the player's colours. Falls back, never raises."""
    try:
        src = PLAYER_SRC.read_text(encoding="utf-8")
        m = re.search(r"/\*MODEL_COLORS_JSON\*/\s*(\{.*?\})"
                      r"\s*/\*END_MODEL_COLORS_JSON\*/", src, re.S)
        return json.loads(m.group(1)) if m else dict(_MEMBER_COLOR_FALLBACK)
    except Exception:
        return dict(_MEMBER_COLOR_FALLBACK)


MEMBER_COLORS = model_colors()

#: equal to the player's marked list; used only if it cannot be read
_SEASON_COLOR_FALLBACK = ["#A87300", "#3375FB", "#C9568C",
                          "#0087AF", "#B96D36", "#8568E3"]


def season_colors() -> list:
    """The one season-line palette: player.js SEASON_COLORS (the CVD-safe
    set, used where the --season-N tokens are absent). Falls back, never raises."""
    try:
        src = PLAYER_SRC.read_text(encoding="utf-8")
        m = re.search(r"/\*SEASON_COLORS_JSON\*/\s*(\[.*?\])"
                      r"\s*/\*END_SEASON_COLORS_JSON\*/", src, re.S)
        return json.loads(m.group(1)) if m else list(_SEASON_COLOR_FALLBACK)
    except Exception:
        return list(_SEASON_COLOR_FALLBACK)


def _rgba(hexs: str, alpha: float) -> str:
    r, g, b = (int(hexs.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


# fan bands in the PF member's colour (the weekly fan is the PF forecast)
_PF_COLOR = MEMBER_COLORS.get("pf", _MEMBER_COLOR_FALLBACK["pf"])
QBANDS = ((0.025, 0.975, _rgba(_PF_COLOR, 0.13), "95% interval"),
          (0.10, 0.90, _rgba(_PF_COLOR, 0.20), "80% interval"),
          (0.25, 0.75, _rgba(_PF_COLOR, 0.30), "50% interval"))

#: the map's target: FluSight's "wk flu hosp rate change" categorical target
CAT_FORECAST = "categorical forecast"
#: player.js display names, typed here (report_season, which parses the
#: names, imports this module): keep in step. The retired blend's entry
#: serves only older bundles.
MODEL_SHORT = {"ensemble": "FluBNF Ensemble (retired)",
               "pf": "Oracle SIHRS", "analogue": "Groundhog"}
#: map labels: the display name + " categorical forecast"
MODEL_LABEL = {m: f"{n} {CAT_FORECAST}" for m, n in MODEL_SHORT.items()}
#: outlook toggle order: the shipped models, PF first; a stored blend last
MODEL_ORDER = ("pf", "analogue", "ensemble")

#: never offered on a toggle (older bundles may still render them, label only)
RETIRED_MODELS = ("ensemble",)


def toggle_models(available) -> list:
    """Models a surface may offer on its toggle, in display order: every
    available model except the retired ones."""
    avail = [m for m in available if m not in RETIRED_MODELS]
    order = [m for m in MODEL_ORDER if m in avail]
    return order + [m for m in avail if m not in MODEL_ORDER]

# wheel zoom, double-click reset, pruned hover modebar, responsive sizing
PLOTLY_CONFIG = {"scrollZoom": True, "doubleClick": "reset+autosize",
                 "responsive": True,
                 "displayModeBar": "hover", "displaylogo": False,
                 "modeBarButtonsToRemove": ["lasso2d", "select2d",
                                            "autoScale2d"]}

# ---------------------------------------------------------------------------
# Inputs bundle: everything render_bundle needs to rebuild report.html,
# saved beside it. Fans are reduced to the 23-level grid (FAN_LEVELS), never
# raw samples, keeping it ~100 KB.
BUNDLE_NAME = "report_inputs.json"
BUNDLE_VERSION = 4
#: renderable bundle versions; each bump was ADDITIVE and older bundles
#: render without it: v2 cards_model (else PF), v3 cards_by_model +
#: national_map_cards (model toggle), v4 fitted_fips (gap vs not-fitted wording)
SUPPORTED_BUNDLE_VERSIONS = (1, 2, 3, 4)
FAN_LEVELS = (0.01, 0.025, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35,
              0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80,
              0.85, 0.90, 0.95, 0.975, 0.99)


def _fig_layout(fig, height=340, title="", legend=False):
    # 14px chart text (above the 13.1px hint floor), title a step up;
    # automargin sizes margins to the labels; a legend adds figure height
    fig.update_layout(
        template=None, paper_bgcolor=CARD, plot_bgcolor=CARD,
        font=dict(color=INK, family=FONT_STACK, size=14),
        margin=dict(l=8, r=8, t=42 if title else 12, b=8),
        height=height + (36 if legend else 0),
        title=dict(text=title, font=dict(size=16)),
        # single-line date ticks: a two-line band collides with the legend
        xaxis=dict(gridcolor=LINE, zerolinecolor=LINE, automargin=True,
                   tickformat="%b %-d"),
        yaxis=dict(gridcolor=LINE, zerolinecolor=LINE, automargin=True),
        showlegend=legend,
        legend=dict(orientation="h", x=0, xanchor="left",
                    y=-0.16, yanchor="top",
                    font=dict(size=14, color=INK),
                    bgcolor="rgba(0,0,0,0)"))
    return fig


def fan_quantiles(forecast_times, samples_by_h, levels=FAN_LEVELS) -> dict:
    """Reduce raw fan samples to the bundle's quantile grid.

    Returns {str(time): {str(level): value}}: the pure-data form of a fan,
    small enough to persist in report_inputs.json and rich enough to redraw
    the fan with fan_figure_from_quantiles."""
    out = {}
    for t in forecast_times:
        s = np.asarray(samples_by_h[str(t)], float)
        s = s[np.isfinite(s)]
        out[str(t)] = {str(lv): round(float(np.quantile(s, lv)), 4)
                       for lv in levels}
    return out


def _q_at(qmap: dict, level: float) -> float:
    """One stored quantile, tolerating float-format drift in the keys."""
    key = str(level)
    if key in qmap:
        return float(qmap[key])
    best = min(qmap, key=lambda k: abs(float(k) - level))
    return float(qmap[best])


def fan_figure(observed_times, observed, forecast_times, samples_by_h,
               gaps=(), title="", settled=None):
    """Quantile fan vs observed, from raw samples. `gaps` = week offsets
    with no data. `settled`: optional [(date, value)...] of what actually
    happened after the forecast origin (backdated runs) -- drawn dotted;
    the legend entry doubles as its on/off toggle."""
    return fan_figure_from_quantiles(
        observed_times, observed, forecast_times,
        fan_quantiles(forecast_times, samples_by_h),
        gaps=gaps, title=title, settled=settled)


def fan_figure_from_quantiles(observed_times, observed, forecast_times,
                              quantiles_by_time, gaps=(), title="",
                              settled=None):
    """The same fan, drawn from a stored quantile grid (see fan_quantiles).
    This is the path render_bundle takes, so a rebuilt report draws its
    fans with the current design code rather than replaying baked figures."""
    import plotly.graph_objects as go
    fig = go.Figure()
    for lo, hi, color, band_name in QBANDS:
        upper = [_q_at(quantiles_by_time[str(t)], hi)
                 for t in forecast_times]
        lower = [_q_at(quantiles_by_time[str(t)], lo)
                 for t in forecast_times]
        fig.add_scatter(x=list(forecast_times) + list(forecast_times)[::-1],
                        y=upper + lower[::-1], fill="toself", fillcolor=color,
                        line=dict(width=0), hoverinfo="skip",
                        name=band_name, showlegend=True)
    med = [_q_at(quantiles_by_time[str(t)], 0.5) for t in forecast_times]
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
                      annotation_font_size=13)
    return _fig_layout(fig, title=title, legend=True)



def cat_bar(probs):
    import plotly.graph_objects as go
    fig = go.Figure(go.Bar(
        x=[CAT_LABEL[c] for c in CATS], y=[probs.get(c, 0) for c in CATS],
        marker_color=[CAT_COLOR[c] for c in CATS],
        hovertemplate="%{x}: %{y:.0%}<extra></extra>"))
    f = _fig_layout(fig, height=230, title="categorical forecast (1 wk)")
    f.update_yaxes(tickformat=".0%", range=[0, 1])
    return f


def _html(fig, include_js=False, div_id=None):
    # save-PNG at 2x with a meaningful filename (figures have an opaque ground)
    config = dict(PLOTLY_CONFIG)
    config["toImageButtonOptions"] = {
        "format": "png", "scale": 2,
        "filename": f"flubnf_{div_id or 'report_figure'}"}
    return fig.to_html(full_html=False,
                       include_plotlyjs=True if include_js else False,
                       div_id=div_id, config=config)


#: the embedded token blocks: both :root blocks (palette, type scale), the
#: named themes and the two accessibility modifiers
_THEME_SELECTORS = (":root", '[data-theme="dark"]', '[data-theme="paper"]',
                    '[data-theme="dim"]', '[data-contrast="high"]',
                    '[data-vision="cvd"]')


def theme_token_css() -> str:
    """nau.css token blocks verbatim, in document order (the cascade
    matters: modifiers retarget type tokens; page_style's print block
    comes after and wins)."""
    css = NAU_CSS.read_text()
    blocks = []
    for sel in _THEME_SELECTORS:
        found = [m for m in re.finditer(re.escape(sel) + r"\{[^{}]*\}", css)
                 if sel != ":root" or css[max(0, m.start() - 1)] not in "\"']"]
        if not found:
            raise ValueError(f"nau.css: token block {sel} not found")
        blocks += [(m.start(), m.group(0)) for m in found]
    blocks.sort()
    return "\n".join(b for _, b in blocks)


def theme_boot_script() -> str:
    """First-paint theme resolution, mirroring base.html: the console's
    localStorage keys when served same-origin, else the OS preferences."""
    return """<script>
(function(){var de=document.documentElement,t=null,c=null,v=null;
 try{if(location.protocol==='http:'||location.protocol==='https:'){
  t=localStorage.getItem('theme');c=localStorage.getItem('contrast');
  v=localStorage.getItem('vision');}}catch(e){}
 if(['light','paper','dim','dark'].indexOf(t)<0)
  t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';
 if(c!=='high'&&c!=='normal')
  c=matchMedia('(prefers-contrast: more)').matches?'high':'normal';
 de.setAttribute('data-theme',t);
 if(c==='high')de.setAttribute('data-contrast','high');
 if(v==='cvd')de.setAttribute('data-vision','cvd');})();
</script>"""


def _retint_js() -> str:
    """Rewrite the baked dark-kit literals to the resolved theme tokens
    (incl. --cat-*, --ok/--bad, the accent via --gold). Member colours are
    deliberately excluded (already dichromat-spaced). Re-runs from a
    snapshot of the baked figure on every themechange."""
    pairs = [(CARD, "--card"), (INK, "--ink"), (MUT, "--mut"),
             (LINE, "--line"), (OK, "--ok"), (BAD, "--bad"),
             (ACCENT, "--gold")]
    pairs += [(CAT_COLOR[c], "--cat-" + c.replace("_", "-")) for c in CATS]
    lines = "".join(
        f"MAP[{json.dumps(col)}]=css({json.dumps(var)},{json.dumps(col)});"
        for col, var in pairs)
    return """<script>
(function(){
  if(!window.Plotly) return;
  function css(n,fb){
    var v=getComputedStyle(document.documentElement)
      .getPropertyValue(n).trim();
    return v||fb;
  }
  function walk(o,MAP){
    if(!o||typeof o!=='object') return;
    for(var k in o){
      var v=o[k];
      if(typeof v==='string'&&Object.prototype.hasOwnProperty.call(MAP,v))
        o[k]=MAP[v];
      else walk(v,MAP);
    }
  }
  function pass(){
    var MAP={};""" + lines + """
    var dirty=Object.keys(MAP).some(function(k){
      return MAP[k].toLowerCase()!==k.toLowerCase();});
    var plots=document.querySelectorAll('.js-plotly-plot');
    for(var i=0;i<plots.length;i++){
      var g=plots[i];
      if(!g.data||!g.layout) continue;
      if(!dirty&&!g._flubnfBaked) continue;
      if(!g._flubnfBaked)
        g._flubnfBaked=JSON.stringify({d:g.data,l:g.layout});
      var baked=JSON.parse(g._flubnfBaked);
      walk(baked.d,MAP);walk(baked.l,MAP);
      g.data=baked.d;g.layout=baked.l;
      Plotly.react(g,g.data,g.layout);
    }
  }
  pass();
  addEventListener('themechange',pass);
})();
</script>"""


def page_header() -> str:
    """The report's header lockup, one source: build_report embeds it, and
    legacy_theme_carry inserts it into stored reports that predate it."""
    return """<header class="brandrow"><span class="brand"><em>Flu</em>BNF</span>
 <span class="brandsub">weekly forecast report</span>
 <span class="spacer"></span>
 <a id="appback" href="#" hidden
  onclick="history.back();return false">&larr; back to FluBNF</a>
</header>"""


def page_style() -> str:
    """The report's stylesheet, one source: build_report embeds it, and
    legacy_theme_carry swaps it into stored reports whose markup still
    matches (see the class-coverage check there)."""
    return f"""<style>
 /* console identity, theme-aware: the token blocks below are the console's
    own (nau.css, verbatim -- four themes plus the high-contrast and
    color-vision modifiers), selected at open by the boot script; the
    print block at the end flips to the console's light theme so the page
    always prints as dark ink on a light surface. The inline usmap SVG
    reads --card, --accent, --map-nodata, and the --cat-* scale: state
    borders match the card surface, no-data reads as an explicit gap on
    every ground, and the category fills follow the color-vision mode. */
{theme_token_css()}
 *{{box-sizing:border-box}}
 body{{margin:0;background:var(--bg);color:var(--ink);
      font:400 var(--fs-body)/1.5 {FONT_STACK}}}
 main{{width:100%;margin:0 auto;padding:1.4rem 1.4rem 4rem}}
 .brandrow{{display:flex;align-items:baseline;gap:.6rem;flex-wrap:wrap;
  margin:0 0 .8rem}}
 .brand{{font-size:1.45rem;font-weight:700;letter-spacing:.01em}}
 .brand em{{color:var(--accent);font-style:normal}}
 .brandsub{{color:var(--mut);font-size:.9rem}}
 .brandrow .spacer{{flex:1}}
 h1{{font-size:var(--fs-h1);font-weight:700;margin:.1rem 0 .3rem;
     text-wrap:balance}}
 h2{{font-size:1.15rem;font-weight:700;margin:.2rem 0 .6rem}}
 .card h2{{font-size:var(--fs-h2);margin:0 0 .55rem;
    text-transform:uppercase;
    letter-spacing:.05em;color:var(--mut);font-weight:600}}
 .sub{{color:var(--mut);margin:.2rem 0 1rem;font-size:var(--fs-sub)}}
 /* run-settings block: the console's compact two-column grid (see
    nau.css .runsettings), restated here because the report is
    self-contained */
 .runsettings{{margin:.45rem 0}}
 .runsettings .kv{{display:grid;
    grid-template-columns:max-content max-content;
    gap:.14rem 1.1rem;align-items:baseline;width:max-content;
    max-width:100%;margin:.25rem 0 0}}
 .runsettings .kv dt{{color:var(--mut)}}
 .runsettings .kv dd{{margin:0;font-weight:650;
    font-variant-numeric:tabular-nums;overflow-wrap:anywhere}}
 .card{{background:var(--card);border:1px solid var(--line);
        border-radius:10px;padding:.85rem 1rem;margin:.75rem 0;
        box-shadow:var(--shadow);overflow-x:auto}}
 .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}}
 @media(max-width:820px){{.grid2{{grid-template-columns:1fr}}}}
 .offseason{{color:var(--mut);font-size:var(--fs-hint);font-style:italic;
             margin:.2rem 0 .8rem}}
 /* in the header flow (not fixed) so it can never cover the title */
 #appback{{display:inline-block;background:var(--card);
  border:1px solid var(--line);border-radius:99px;padding:.3rem .8rem;
  color:var(--ink);text-decoration:none;font-size:.85rem}}
 #appback:hover{{border-color:var(--accent)}}
 .mapcap{{max-width:min(880px,72vw);margin:0 auto}}
 .mapcap svg{{max-height:58vh}}
 .legend{{display:flex;gap:1.1rem;flex-wrap:wrap;color:var(--mut);
          font-size:var(--fs-hint);margin:.4rem 0 0 .2rem}}
 .legend span{{display:inline-flex;align-items:center;gap:.35rem}}
 .sw{{width:13px;height:13px;border-radius:3px;display:inline-block;
     -webkit-print-color-adjust:exact;print-color-adjust:exact}}
 table{{border-collapse:collapse;font-size:var(--fs-table);
        margin:.6rem .4rem;font-variant-numeric:tabular-nums}}
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
 /* selected toggle: the console's button.gold treatment (gold-bright is
    the pure cyan in every theme, and near-black ink passes on it) */
 .viewtoggle .on{{background:var(--gold-bright);
                  border-color:var(--gold-bright);color:{PAPER}}}
 .backbtn{{margin:.2rem 0 .6rem}}
 .hint{{color:var(--mut);font-size:var(--fs-hint)}}
 @media print{{
  :root{{--bg:#FFFFFF;--card:#FFFFFF;--ink:#000F7E;--mut:#565E96;
   --line:#DCD8E9;--accent:#0173A9;--gold:#0173A9;
   --ok:#177245;--bad:#C42840;--map-nodata:#C9C5D8;--shadow:none}}
  body{{background:#FFFFFF;color:#000F7E}}
  button,select,.viewtoggle,#appback,.backbtn{{display:none!important}}
  .card{{box-shadow:none;break-inside:avoid}}
 }}
</style>"""


def build_report(reference_date: str, state_cards: dict, state_details: dict,
                 national: dict, out_path: Path,
                 national_map_html: str = "", elapsed_s=None,
                 settings_html: str = "", model_label: str = "",
                 cards_by_model: dict | None = None,
                 national_map_cards: dict | None = None,
                 cards_model: str = "",
                 fitted_fips=None) -> Path:
    """state_cards: abbr -> hover-card data (choropleth).
    state_details: abbr -> dict(name, fan=…, cat=…, acc=…, table_rows=[…]).
    national: dict(fan=…, acc=…, summary_html=str).
    national_map_html: usmap.national_svg output; adds the state/national view toggle.
    elapsed_s, settings_html: footer lines; omitted when not given.
    model_label: who computed the map's cards (MODEL_LABEL); default PF.
    cards_by_model / national_map_cards: per-model cards; with two or more
    models a model toggle swaps fills, hovers and label client-side.
    cards_model: the model the map is rendered with (the toggle's default).
    fitted_fips: fips the run fitted, or None; gates every no-data claim
    (in scope = reporting gap, outside = not fitted, None = only 'no data')."""
    # build-time SVG map: plotly geo fetches its geometry from a CDN
    from app.core import usmap
    from app.core.usmap import cat_fill, svg_map
    cards_by_fips = {c["fips"]: c for c in state_cards.values() if "fips" in c}
    # card-less states: gaps (in scope) vs not fitted (out); no record: 'no data'
    scope = set(fitted_fips) if fitted_fips is not None else None
    no_card = set(usmap.state_paths()) - set(cards_by_fips)
    gap_states = (no_card & scope) if scope is not None else set()
    unfitted_states = (no_card - scope) if scope is not None else set()
    # only states that actually have a detail section invite a click
    map_html = svg_map(cards_by_fips, clickable=set(state_details),
                       scope_fips=scope)
    # legend/caption: each no-data flavour only when some state wears it
    _sw = f'<i class="sw" style="background:{NO_DATA}"></i>'
    legend_bits, caption_bits = [], []
    if scope is None:
        if no_card:
            legend_bits.append(f"<span>{_sw}no data in this view</span>")
            caption_bits.append(
                " No-data states have no data in this report's inputs.")
    else:
        if gap_states:
            legend_bits.append(f"<span>{_sw}no data (reporting gap)</span>")
            caption_bits.append(
                " No-data states were fitted but reported nothing this "
                "week: shown as gaps, never interpolated.")
        if unfitted_states:
            legend_bits.append(f"<span>{_sw}not fitted in this run</span>")
            caption_bits.append(
                " Not-fitted states were outside this run's scope.")
    no_data_legend = "".join(legend_bits)
    no_data_caption = "".join(caption_bits)
    model_label = model_label or MODEL_LABEL["pf"]
    # model toggle only for 2+ models with usable (fips + probs) cards, the
    # bar the home outlook applies; an empty model would be an inert button
    model_toggle_html = ""
    cbm = {m: c for m, c in (cards_by_model or {}).items()
           if any(isinstance(v, dict) and v.get("fips") and v.get("probs")
                  for v in (c or {}).values())}
    order = toggle_models(cbm)
    if len(order) >= 2:
        default = cards_model if cards_model in order else order[0]
        payload = {}
        for m in order:
            byf = {c["fips"]: c for c in cbm[m].values()
                   if isinstance(c, dict) and c.get("fips")}
            payload[m] = {
                # scope rides along so swapped hovers match the rendered map
                "states": usmap.state_swap_payload(byf, scope_fips=scope),
                "us": usmap.nat_swap_payload(
                    (national_map_cards or {}).get(m) or {})}
        model_toggle_html = usmap.model_toggle(
            order, MODEL_LABEL, default, payload,
            group_id="outlook-model", btn_class="", active_class="on",
            wrap_class="viewtoggle", short_labels=MODEL_SHORT)

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
</section>""")

    # national chart cards only when their figure exists; else one hint line
    nat_cards = []
    if national.get("fan"):
        nat_cards.append(f'<div class="card">{_html(national["fan"])}</div>')
    nat_body = "\n  ".join(nat_cards) or (
        '<p class="hint">National fan and accuracy charts appear once the '
        'national model run lands.</p>')
    # A console run fits US directly, so a national forecast here is FITTED
    # (never the constructed sum) and says so. Claim it only when the
    # national fan exists (nat_cards); summary_html is always filled (even
    # unscored), so it is not evidence of a national run.
    from app.core import us_national as _usn
    has_national = bool(nat_cards)
    nat_prov = (f'<p class="hint">{_usn.LABELS[_usn.FITTED]}. '
                f'{_usn.NOTES[_usn.FITTED]}</p>') if has_national else ""
    nat = f"""
<section class="state" id="st-US" hidden>
  {back_btn}
  <h2>United States</h2>
  {nat_prov}
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

    # plotly.js in the head, once, iff any figure is embedded
    if state_details or national.get("fan"):
        from plotly.offline import get_plotlyjs
        plotly_js = "<script>" + get_plotlyjs() + "</script>"
    else:
        plotly_js = ""

    # footer: wall time and settings (which run produced this?)
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
{theme_boot_script()}
{plotly_js}
{page_style()}</head><body><main>
{page_header()}
<h1>US influenza forecast</h1>
<p class="sub">week of {reference_date} ·
 <button id="natbtn">national detail</button></p>
{model_toggle_html}
{view_toggle}
<div class="card" id="map-anchor">
<p class="hint mapmodel" data-mapmodel-label>{model_label}</p>
<div id="map-state" class="mapcap">{map_html}</div>
 {nat_map_div}
 <div class="legend">
  {"".join(f'<span><i class="sw" style="background:{cat_fill(c)}"></i>{CAT_LABEL[c]}</span>' for c in CATS)}
  {no_data_legend}
 </div>
 <div class="legend">
  <span><i class="sw" style="background:{cat_fill('increase')};opacity:.64"></i>leaning</span>
  <span><i class="sw" style="background:{cat_fill('increase')};opacity:.82"></i>likely</span>
  <span><i class="sw" style="background:{cat_fill('increase')};opacity:1"></i>confident</span>
 </div>
</div>
<p class="hint">Hover a state for its category probabilities, click it
 for detail; Ctrl+scroll zooms (⌘ on Mac).{no_data_caption}</p>
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
{_retint_js() if plotly_js else ""}
{footer}
</main></body></html>"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # atomic (a serve-time rebuild never exposes a half-write), and LF pinned:
    # /output/report (text read) and /output/report/download (raw bytes) must
    # return identical text on Windows too
    tmp = out_path.with_name(out_path.name + ".tmp")
    tmp.write_text(html, newline="\n")
    os.replace(tmp, out_path)
    return out_path


def save_bundle(bundle: dict, dirpath: Path) -> Path:
    """Persist the inputs bundle beside report.html, atomically, so the
    report can be rebuilt after any builder change without rerunning models."""
    p = Path(dirpath) / BUNDLE_NAME
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(bundle, separators=(",", ":"), default=float))
    os.replace(tmp, p)
    return p


def render_bundle(bundle: dict, out_path: Path) -> Path:
    """Render the weekly report from its inputs bundle: the one render path
    (live run and stale-report refresh alike)."""
    details = {}
    for key, d in (bundle.get("details") or {}).items():
        fan_in = d.get("fan") or {}
        try:
            settled = [tuple(p) for p in (fan_in.get("settled") or [])]
            fan = fan_figure_from_quantiles(
                fan_in.get("observed_times") or [],
                fan_in.get("observed") or [],
                fan_in["forecast_times"], fan_in["quantiles"],
                title=fan_in.get("title", ""), settled=settled or None)
            details[key] = {
                "name": d.get("name", key), "note": d.get("note", ""),
                "fan": fan, "cat": cat_bar(d.get("cat_probs") or {}),
                "table_rows": [tuple(r) for r in (d.get("table_rows") or [])]}
        except Exception:
            continue      # one broken state must not sink the whole report
    nat_map_html = ""
    card = bundle.get("national_map_card")
    if card:
        try:
            from app.core.usmap import national_svg
            nat_map_html = national_svg(card)
        except Exception:
            nat_map_html = ""
    us_d = details.get("US", {})
    national = bundle.get("national") or {}
    # v2 field; v1 bundles were PF
    cards_model = bundle.get("cards_model") or "pf"
    return build_report(
        bundle["reference_date"], bundle.get("cards") or {}, details,
        {"fan": us_d.get("fan"),
         "note": us_d.get("note", ""),
         "summary_html": national.get("summary_html", "")},
        Path(out_path), national_map_html=nat_map_html,
        elapsed_s=bundle.get("elapsed_s"),
        settings_html=bundle.get("settings_html", ""),
        model_label=MODEL_LABEL.get(cards_model, MODEL_LABEL["pf"]),
        # v3 fields (absent: one model, no toggle)
        cards_by_model=bundle.get("cards_by_model") or {},
        national_map_cards=bundle.get("national_map_cards") or {},
        cards_model=cards_model,
        # v4 field (absent: None, the map claims only 'no data')
        fitted_fips=bundle.get("fitted_fips"))


def builder_sources_mtime() -> float:
    """Newest mtime of the weekly report's builder sources (this module,
    scoring, usmap, nau.css): a stored report.html older than this is stale."""
    times = [0.0]
    for mod in ("report_v2", "scoring", "usmap"):
        p = Path(__file__).with_name(mod + ".py")
        if p.is_file():
            times.append(p.stat().st_mtime)
    if NAU_CSS.is_file():
        times.append(NAU_CSS.stat().st_mtime)
    return max(times)


#: marks a served legacy page as already annotated (and keeps the carry
#: idempotent should an annotated page ever come back through)
STALE_NOTE_ID = "earlier-design-note"


def _css_class_names(css: str) -> set:
    return set(re.findall(r"\.([A-Za-z_][A-Za-z0-9_-]*)", css))


def legacy_theme_carry(html: str) -> str:
    """Serve-time restyle of a stored report that predates the inputs bundle
    (it cannot be rebuilt: results.json lacks samples and categories).

    Swaps in the current stylesheet, header and retint pass only when every
    class the body uses and the old stylesheet styled is still styled; adds
    a one-line note either way. Never modifies the stored file; returns the
    input unchanged on any surprise."""
    try:
        if 'class="brandrow"' in html or STALE_NOTE_ID in html:
            return html            # already current, or already annotated
        head_end = html.find("</head>")
        body = html[head_end:] if head_end >= 0 else html
        carried = None
        if head_end >= 0:
            s0 = html.rfind("<style>", 0, head_end)
            s1 = html.find("</style>", max(s0, 0))
            if 0 <= s0 < s1 < head_end:
                new_css = page_style()
                old_styled = _css_class_names(html[s0:s1])
                used = {c for m in re.findall(r'class="([^"]+)"', body)
                        for c in m.split()}
                if (used & old_styled) <= _css_class_names(new_css):
                    # the boot script rides with the stylesheet it selects
                    # for, so the carried page follows the theme too
                    out = (html[:s0] + theme_boot_script() + new_css
                           + html[s1 + len("</style>"):])
                    # the current lockup carries its own back link; the old
                    # floating one would duplicate its id
                    out = re.sub(r'<a id="appback".*?</a>', "", out,
                                 count=1, flags=re.S)
                    # charts gain the retint pass (unmatched legacy colours stay)
                    if "Plotly.newPlot" in out or "js-plotly-plot" in out:
                        j = out.rfind("</body>")
                        if j >= 0:
                            out = out[:j] + _retint_js() + out[j:]
                    carried = out
        out = html if carried is None else carried
        i = out.find("<main>")
        if i < 0:
            return html
        note = ('<p class="hint" id="' + STALE_NOTE_ID + '">'
                + ("This report was restyled to the current design when "
                   "served; its chart colors follow your theme where they "
                   "match the current palette, and the chart layouts keep "
                   "the design of the run that produced them. "
                   "A new run will refresh them."
                   if carried is not None else
                   "This report was generated with an earlier design. "
                   "A new run will refresh it.")
                + "</p>")
        ins = ("\n" + (page_header() + "\n" if carried is not None else "")
               + note)
        return out[:i + len("<main>")] + ins + out[i + len("<main>"):]
    except Exception:
        return html
