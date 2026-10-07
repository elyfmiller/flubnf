"""PRODUCTION: the weekly run report (app/ui/pipeline._write_weekly_report,
/output/report refresh via render_bundle).

The weekly run report (the "v2" is historical): one self-contained,
theme-aware HTML file per week (plotly.js embedded once, no network).

  * build-time SVG US map (usmap), states shaded by modal rate-change
    category, intensity by probability, hover card; optional national map
    view and a per-model outlook toggle
  * click a state (or Tab to it, Enter) -> its section, right under the
    map: both members' fans vs observed, the categorical bar, recent data
    and the forecast numbers, with a back-to-map button; a National
    section likewise, its accuracy tables folded
  * a summary line, a sticky jump bar, the states by category in words,
    the color-blind safe switch in the header; print is light with the
    color-vision category scale
  * no-data states are explicit and claim only what was checked: in the
    run's recorded scope with no reported data = reporting gap, in scope
    with data = 'no forecast' (and why), outside = 'not fitted in this
    run', no scope record = 'no data'; legend and hover say the same; fan
    gaps annotated, never smoothed
  * nau.css token blocks embedded verbatim; a boot script resolves the
    theme, the a11y modes and the text size at open (console localStorage
    same-origin, else OS preferences); print is always light
  * the console's look: its header lockup (the theme's mark, inlined),
    DM Sans inlined, and the UI kit (docs/UI-KIT.md) inlined: segmented
    switches for model and view, card headings with "?" tips instead of
    captions, legend chips, badges, empty states, a stat for wall time

  1. palette, model names and colours (player.js's maps), PLOTLY_CONFIG
  2. the inputs bundle: BUNDLE_VERSION, fan_quantiles*, bundle_asof
  3. figures: fan_figure_from_quantiles, cat_bar, _html
  4. page chrome: _retint_js, _week_ticks_js, page_header, page_style
  5. build_report, save_bundle, render_bundle
  6. serve-time: builder_sources_mtime, legacy_theme_carry
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np

from app.core import html_page, usmap

# moved to html_page (shared with report_season and the site); the category
# scale is usmap's (the map draws it). Both stay importable from here.
from app.core.html_page import (
    CHARTS_SRC,
    FONT_STACK,
    NAU_CSS,
    PLAYER_SRC,
    charts_js,
    font_face_css,
    kit_css,
    kit_js,
    kit_macros,
    logo_css,
    marked_json,
    theme_boot_script,
    theme_token_css,
)
from app.core.usmap import CAT_COLOR, CATS, NO_DATA, cat_fill

# --------------------------------------------------- 1. palette and names
# build-time chart palette (nau.css dark theme): figures are built with these
# literals and re-resolved against the page tokens at open (_retint_js)
INK = "#E9EAF4"; MUT = "#9AA1C4"; PAPER = "#0C0D17"; CARD = "#151729"
LINE = "#262A45"; ACCENT = "#34C0F0"
OK = "#4CC38A"; BAD = "#FB4653"
CAT_LABEL = {c: c.replace("_", " ") for c in CATS}

#: equal to the player's map; used only if its marked JSON cannot be read
_MEMBER_COLOR_FALLBACK = {"ensemble": "#34C0F0", "pf": "#1979FF",
                          "pf_filter": "#C77100", "analogue": "#FFC72C",
                          "pf2s": "#A66395"}


def model_colors() -> dict:
    """The one member-color map: player.js's marked JSON literal, parsed so
    every Python surface wears the player's colours. Falls back, never raises."""
    return marked_json("MODEL_COLORS_JSON", _MEMBER_COLOR_FALLBACK, PLAYER_SRC)


MEMBER_COLORS = model_colors()

#: equal to the player's marked list; used only if it cannot be read
_SEASON_COLOR_FALLBACK = ["#A87300", "#3375FB", "#C9568C",
                          "#0087AF", "#B96D36", "#8568E3"]


def season_colors() -> list:
    """The one season-line palette: player.js SEASON_COLORS (the CVD-safe
    set, used where the --season-N tokens are absent). Falls back, never raises."""
    return marked_json("SEASON_COLORS_JSON", _SEASON_COLOR_FALLBACK, PLAYER_SRC)


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
               "pf": "Oracle SIHRS", "pf_filter": "Liu-West filter",
               "analogue": "Groundhog"}
#: map labels: the display name + " categorical forecast"
MODEL_LABEL = {m: f"{n} {CAT_FORECAST}" for m, n in MODEL_SHORT.items()}
#: outlook toggle order: the shipped models, PF first; a stored blend last
MODEL_ORDER = ("pf", "pf_filter", "analogue", "ensemble")

#: never offered on a toggle (older bundles may still render them, label only)
RETIRED_MODELS = ("ensemble",)


def toggle_models(available) -> list:
    """Models a surface may offer on its toggle, in display order: every
    available model except the retired ones."""
    avail = [m for m in available if m not in RETIRED_MODELS]
    order = [m for m in MODEL_ORDER if m in avail]
    return order + [m for m in avail if m not in MODEL_ORDER]

# no wheel zoom (a detail chart must not catch the page's scroll),
# double-click reset, pruned hover modebar, responsive sizing
PLOTLY_CONFIG = {"scrollZoom": False, "doubleClick": "reset+autosize",
                 "responsive": True,
                 "displayModeBar": "hover", "displaylogo": False,
                 # Plotly's legend hint covered nearby controls
                 "showTips": False,
                 "modeBarButtonsToRemove": ["lasso2d", "select2d",
                                            "autoScale2d"]}

# ---------------------------------------------------- 2. the inputs bundle
# Everything render_bundle needs to rebuild report.html, saved beside it.
# Fans are reduced to the 23-level grid (FAN_LEVELS), never raw samples,
# keeping it ~100 KB.
BUNDLE_NAME = "report_inputs.json"
BUNDLE_VERSION = 8
#: renderable bundle versions; each bump was ADDITIVE and older bundles
#: render without it: v2 cards_model (else PF), v3 cards_by_model +
#: national_map_cards (model toggle), v4 fitted_fips (gap vs not-fitted
#: wording), v5 national_in_run (the national detail says US was not run),
#: v6 gap_fips + no_forecast (a reporting gap only where no data was
#: reported; elsewhere "no forecast" with its reason) and a detail's
#: "model" (a Groundhog fan where the state has no PF samples), v7 asof
#: (before it, "reference_date" held the as-of; it now holds the hub's
#: reference date, as-of + 7; read the as-of through bundle_asof), v8
#: grid (the "All locations" pages, report_grid; absent: no such pages).
#: render_bundle also reads the grid for the detail sections' second
#: member (its interval and the forecast numbers), so no new field was
#: needed for them: a bundle without a grid draws its one stored member
SUPPORTED_BUNDLE_VERSIONS = (1, 2, 3, 4, 5, 6, 7, 8)
FAN_LEVELS = (0.01, 0.025, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35,
              0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80,
              0.85, 0.90, 0.95, 0.975, 0.99)


def bundle_asof(bundle: dict) -> str:
    """A bundle's as-of date: v7 "asof"; older bundles stored the as-of
    under "reference_date"."""
    return str(bundle.get("asof") or bundle.get("reference_date") or "")


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


def fan_quantiles_from_grid(forecast_times, grid_by_time,
                            levels=FAN_LEVELS) -> dict:
    """fan_quantiles for a member that arrives as quantiles (the
    Groundhog): each time's {level: value} grid read on the bundle's
    levels, linear between the stored ones (the FluSight grid IS
    FAN_LEVELS, so normally a straight copy). Same return shape."""
    out = {}
    for t in forecast_times:
        pairs = sorted((float(l), float(v))
                       for l, v in grid_by_time[str(t)].items())
        ls = [l for l, v in pairs if np.isfinite(v)]
        vs = [v for l, v in pairs if np.isfinite(v)]
        if not ls:
            raise ValueError(f"no finite quantiles for {t}")
        out[str(t)] = {str(lv): round(float(np.interp(lv, ls, vs)), 4)
                       for lv in levels}
    return out


# ------------------------------------------------------------- 3. figures
#: the detail fan's members in drawing order: the Groundhog first, the
#: Oracle SIHRS on top (report_grid draws its panels the same way)
FAN_MODELS = ("analogue", "pf")
#: the two intervals a member's detail fan draws, widest first
FAN_BANDS = ((0.025, 0.975, "95"), (0.25, 0.75, "50"))
#: baked band fills: a member's colour at these alphas; _retint_js swaps
#: each literal for its --rp-band-<model>-<level> token (page_style sets
#: one alpha for light cards, a stronger one for dark cards)
_BAND_ALPHA = {"95": 0.17, "50": 0.36}
#: the light-card Groundhog colour (3:1 or more on every light card; the
#: player's yellow stays for dark cards)
ANALOGUE_ON_LIGHT = "#A87300"


def _member_hex(model: str) -> str:
    return MEMBER_COLORS.get(model, _MEMBER_COLOR_FALLBACK.get(model,
                                                               "#888888"))


def band_literal(model: str, level: str) -> str:
    """The baked fill of one member's band ("95" or "50")."""
    return _rgba(_member_hex(model), _BAND_ALPHA[level])


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
        # one row under the plot, left-aligned
        legend=dict(orientation="h", x=0, xanchor="left",
                    y=-0.14, yanchor="top",
                    font=dict(size=14, color=INK),
                    bgcolor="rgba(0,0,0,0)"))
    return fig


def _bands(color: str | None):
    """QBANDS in another member's colour (None: the PF's)."""
    if not color:
        return QBANDS
    return tuple((lo, hi, _rgba(color, a), name) for (lo, hi, _c, name), a
                 in zip(QBANDS, (0.13, 0.20, 0.30)))


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


def grid_quantiles(fan: dict) -> dict:
    """A report_grid panel fan ({"times", "q": per horizon [q2.5, q25,
    q50, q75, q97.5]}) as a {time: {level: value}} grid."""
    from app.core.report_grid import LEVELS
    return {str(t): {str(lv): float(v) for lv, v in zip(LEVELS, row)}
            for t, row in zip(fan.get("times") or [], fan.get("q") or [])}


def fan_figure_from_quantiles(observed_times, observed, forecast_times,
                              quantiles_by_time, gaps=(), title="",
                              settled=None, band_color=None, model=None,
                              others=None):
    """The detail fan, drawn from a stored quantile grid (see
    fan_quantiles). This is the path render_bundle takes, so a rebuilt
    report draws its fans with the current design code rather than
    replaying baked figures.

    Each member (`model`, default the Oracle SIHRS, or the member whose
    colour `band_color` is; plus `others`, model -> a {time: {level:
    value}} grid) draws its 95% and 50% bands and its median in its own
    colour, the median joined to the last observed week; the Groundhog's
    95% band is outlined so an overlap never turns grey. The y axis starts
    at 0; the card heading names the chart (`title` is kept for callers
    and not drawn); the legend is one row, one entry per member."""
    import plotly.graph_objects as go
    if model is None:
        model = next((m for m, c in MEMBER_COLORS.items()
                      if band_color and c.lower() == band_color.lower()),
                     "pf")
    members = {model: quantiles_by_time}
    for m, q in (others or {}).items():
        if m not in members and q:
            members[m] = q
    order = ([m for m in FAN_MODELS if m in members]
             + [m for m in members if m not in FAN_MODELS])
    ft = list(forecast_times)
    o_t, o_v = list(observed_times), list(observed)
    fig = go.Figure()
    for m in order:
        qm = members[m]
        col = _member_hex(m)
        short = MODEL_SHORT.get(m, m)
        for lo, hi, lvl in FAN_BANDS:
            upper = [_q_at(qm[str(t)], hi) for t in ft]
            lower = [_q_at(qm[str(t)], lo) for t in ft]
            outline = m == "analogue" and lvl == "95"
            fig.add_scatter(
                x=ft + ft[::-1], y=upper + lower[::-1], fill="toself",
                fillcolor=band_literal(m, lvl),
                # a band is its fill: Plotly's default for a short trace
                # adds markers in its own palette at the edges
                mode="lines",
                line=(dict(color=col, width=1.2, dash="dot") if outline
                      else dict(width=0)),
                hoverinfo="skip", name=f"{short}: {lvl}% interval",
                legendgroup=m, showlegend=False)
    for m in order:
        qm = members[m]
        col = _member_hex(m)
        short = MODEL_SHORT.get(m, m)
        xs = list(ft)
        ys = [_q_at(qm[str(t)], 0.5) for t in ft]
        tips = ["%{x|%b %-d}: %{y:,.0f}<extra>" + short + " median</extra>"
                ] * len(ft)
        sizes = [6] * len(ft)
        if o_t:
            xs, ys = [o_t[-1]] + xs, [o_v[-1]] + ys
            tips = ["%{x|%b %-d}: %{y:,.0f}<extra>latest</extra>"] + tips
            sizes = [0] + sizes
        fig.add_scatter(x=xs, y=ys, mode="lines+markers",
                        line=dict(color=col, width=2.2),
                        marker=dict(size=sizes, color=col),
                        name=short, legendgroup=m, hovertemplate=tips,
                        # the legend reads Oracle SIHRS, Groundhog, observed
                        legendrank=(1 if m == "pf" else 2))
    fig.add_scatter(x=o_t, y=o_v,
                    mode="lines+markers",
                    line=dict(color=INK, width=1.6),
                    marker=dict(size=5), name="observed", legendrank=3,
                    hovertemplate="%{x|%b %-d}: %{y:,.0f}"
                                  "<extra>observed</extra>")
    if settled:
        fig.add_scatter(x=[d for d, _ in settled], y=[v for _, v in settled],
                        mode="lines+markers", name="what happened (settled)",
                        line=dict(color=INK, width=1.3, dash="dot"),
                        marker=dict(size=4),
                        hovertemplate="%{x|%b %-d}: %{y:,.0f}"
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
    fig = _fig_layout(fig, legend=True)
    # counts from 0; thousands as "2.5k", small counts plain ("~s" would
    # print 0.5 as "500m")
    ymax = 0.0
    for tr in fig.data:
        for v in (getattr(tr, "y", None) or ()):
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if v == v and v > ymax:
                ymax = v
    fig.update_yaxes(rangemode="tozero",
                     tickformat="~s" if ymax >= 1000 else ",~g")
    return fig


#: the categorical bars' labels, two short lines each (never rotated)
CAT_TICK = {"large_decrease": "large<br>decrease", "decrease": "decrease",
            "stable": "stable", "increase": "increase",
            "large_increase": "large<br>increase"}


def cat_bar(probs):
    import plotly.graph_objects as go
    fig = go.Figure(go.Bar(
        x=[CAT_TICK[c] for c in CATS], y=[probs.get(c, 0) for c in CATS],
        customdata=[CAT_LABEL[c] for c in CATS],
        marker_color=[CAT_COLOR[c] for c in CATS],
        hovertemplate="%{customdata}: %{y:.0%}<extra></extra>"))
    f = _fig_layout(fig, height=230)
    f.update_yaxes(tickformat=".0%", range=[0, 1])
    f.update_xaxes(tickangle=0)
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


# --------------------------------------------------------- 4. page chrome
def _retint_js() -> str:
    """Rewrite the baked dark-kit literals to the resolved theme tokens
    (incl. --cat-*, --ok/--bad, the accent via --gold), the two shipped
    members' colours to --model-pf / --model-analogue and their band fills
    to --rp-band-* (page_style: the Groundhog's gold and the band alphas
    differ between light and dark cards). Re-runs from a snapshot of the
    baked figure on every themechange."""
    pairs = [(CARD, "--card"), (INK, "--ink"), (MUT, "--mut"),
             (LINE, "--line"), (OK, "--ok"), (BAD, "--bad"),
             (ACCENT, "--gold")]
    pairs += [(CAT_COLOR[c], "--cat-" + c.replace("_", "-")) for c in CATS]
    for m in FAN_MODELS:
        pairs.append((_member_hex(m), f"--model-{m}"))
        pairs += [(band_literal(m, lvl), f"--rp-band-{m}-{lvl}")
                  for _lo, _hi, lvl in FAN_BANDS]
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


def _week_ticks_js() -> str:
    """FluCharts inlined, then every baked figure adopted: Saturday week
    ticks, refit after zoom, pan, resize and each retint redraw."""
    return ("<script>" + charts_js() + "</script>\n"
            "<script>if(window.FluCharts&&window.Plotly)"
            "FluCharts.adoptAll();</script>")


def _print_charts_js() -> str:
    """The charts' print step (the page's beforeprint and afterprint call
    it): each shown chart takes the printed card's width (a Letter page
    less its margins), its week ticks refitted, then its own width again.
    Synchronous, as a browser prints right after its beforeprint
    handlers, before any timer runs."""
    return """<script>
window.rpPrintCharts = function(printing) {
  if (!window.Plotly) return;
  var PRINT_W = 680;
  var gs = document.querySelectorAll('.js-plotly-plot');
  for (var i = 0; i < gs.length; i++) {
    var g = gs[i];
    if (!g.offsetParent) continue;
    if (printing) Plotly.relayout(g, {width: PRINT_W, autosize: false});
    else Plotly.relayout(g, {width: null, autosize: true});
    if (window.FluCharts && FluCharts.refit) {
      g._fluFitting = false;
      FluCharts.refit(g);
    }
  }
};
</script>"""


#: the header's color-blind safe switch: sets data-vision on the page (the
#: console's own modifier, so the map, the categories and the status
#: colours follow) and redraws the charts; works from a file:// copy
_VISION_BTN = (
    '<button type="button" id="visionbtn" class="rp-btn" aria-pressed="false"'
    ' onclick="(function(b){var de=document.documentElement,'
    "on=de.getAttribute('data-vision')!=='cvd';"
    "if(on)de.setAttribute('data-vision','cvd');"
    "else de.removeAttribute('data-vision');"
    "b.setAttribute('aria-pressed',String(on));"
    "try{dispatchEvent(new Event('themechange'));}catch(e){}"
    '})(this)">Color-blind safe</button>'
    "<script>(function(){var b=document.getElementById('visionbtn');"
    "if(b)b.setAttribute('aria-pressed',String(document.documentElement"
    ".getAttribute('data-vision')==='cvd'));})();</script>")


def page_header() -> str:
    """The report's header bar, one source: the console's navbar lockup
    (the theme's mark, the wordmark) with the report's name, the
    color-blind safe switch and the way back. build_report embeds it, and
    legacy_theme_carry inserts it into stored reports that predate it."""
    return """<header class="brandrow"><span class="brand"><span class="mark" aria-hidden="true"></span><span><em>Flu</em>BNF</span></span>
 <span class="brandsub">weekly forecast report</span>
 <span class="spacer"></span>
 """ + _VISION_BTN + """
 <a id="appback" class="rp-btn" href="#" hidden
  onclick="history.back();return false">&larr; back to FluBNF</a>
</header>"""


def _report_tokens_css() -> str:
    """The report's own colour tokens, after nau.css's blocks: the
    members' colours (--model-pf, --model-analogue), the detail fans' band
    fills (--rp-band-*), the grid band alpha (--rp-band-a) and a no-data
    fill at 3:1 or more on every card (--map-nodata), each for light and
    for dark cards. Plain CSS (no format fields)."""
    pf = _member_hex("pf")
    an = _member_hex("analogue")

    def rgb(h):
        return ",".join(str(int(h.lstrip("#")[i:i + 2], 16))
                        for i in (0, 2, 4))
    light = (f"--model-pf:{pf};--model-analogue:{ANALOGUE_ON_LIGHT};"
             "--rp-band-a:.22;"
             f"--rp-band-pf-95:rgba({rgb(pf)},.13);"
             f"--rp-band-pf-50:rgba({rgb(pf)},.30);"
             f"--rp-band-analogue-95:rgba({rgb(ANALOGUE_ON_LIGHT)},.10);"
             f"--rp-band-analogue-50:rgba({rgb(ANALOGUE_ON_LIGHT)},.26);"
             "--map-nodata:#8E89A6")
    dark = (f"--model-analogue:{an};--rp-band-a:.36;"
            f"--rp-band-pf-95:rgba({rgb(pf)},.30);"
            f"--rp-band-pf-50:rgba({rgb(pf)},.52);"
            f"--rp-band-analogue-95:rgba({rgb(an)},.12);"
            f"--rp-band-analogue-50:rgba({rgb(an)},.30);"
            "--map-nodata:#7D83A3")
    darks = ",".join(f'[data-theme="{t}"]'
                     for t in ("dim", "dark", "nord", "dracula"))
    return f"""
 /* the report's colour tokens (members, bands, no data), light cards
    then dark cards */
 :root{{{light}}}
 {darks}{{{dark}}}"""


def _report_css() -> str:
    """The report's newer rules (jump bar, summary line, category list,
    accuracy fold, detail tables, forced colours, phone width); plain CSS,
    page_style appends it before its print block."""
    return """
 /* one spacing step between the top-level cards */
 main > .card,main > section,main > aside{margin:0 0 var(--rp-gap)}
 main > section.state{margin:0}
 main > section.state:not([hidden]){margin:0 0 var(--rp-gap)}
 .card h3{font-size:var(--fs-h2);margin:0 0 .55rem;text-transform:uppercase;
   letter-spacing:.05em;color:var(--mut);font-weight:600}
 .card .uk-heading > h3{margin:0}
 .card > .uk-heading{margin:0 0 .45rem}
 /* the summary line under the title */
 .rp-summary{margin:0 0 var(--sp-3);max-width:80rem;color:var(--ink);
   font-size:var(--fs-sub);line-height:1.45}
 .rp-summary b{font-weight:700;font-variant-numeric:tabular-nums}
 .rp-summary .rp-up{color:var(--bad)}.rp-summary .rp-down{color:var(--ok)}
 /* the jump bar: sticky on screen, gone on paper */
 .rp-jump{position:sticky;top:0;z-index:20;display:flex;flex-wrap:wrap;
   align-items:center;gap:.25rem .9rem;margin:0 0 var(--sp-3);
   padding:.4rem .2rem;background:var(--bg);
   border-bottom:1px solid var(--line);font-size:var(--fs-label)}
 .rp-jump a{font-weight:650}
 .rp-jump .rp-jumpsel{margin-left:auto;display:inline-flex;
   align-items:center;gap:.4rem;color:var(--mut);font-weight:600}
 .rp-jump select{font:inherit;color:var(--ink);background:var(--card);
   border:1px solid var(--field-line);border-radius:6px;padding:.15rem .3rem;
   max-width:12rem}
 #map-anchor,#all-locations,#accuracy,#run,section.state,#us-feature{
   scroll-margin-top:4.2rem}
 /* pooled relWIS beside the map heading */
 .rp-pooled{display:inline-flex;flex-wrap:wrap;align-items:baseline;
   gap:.1rem .8rem;font-size:var(--fs-label);color:var(--mut)}
 .rp-pooled a{color:var(--ink);font-weight:600}
 .rp-pooled b{font-variant-numeric:tabular-nums;font-weight:750}
 /* states by category, in words (screen readers and paper) */
 .rp-catlist{margin:.6rem auto 0;max-width:min(980px,100%);
   font-size:var(--fs-label);color:var(--mut)}
 .rp-catlist dl{display:grid;grid-template-columns:max-content minmax(0,1fr);
   gap:.1rem .8rem;margin:0}
 .rp-catlist dt{font-weight:650;color:var(--ink);white-space:nowrap;
   display:inline-flex;align-items:center;gap:.35rem}
 .rp-catlist dd{margin:0}
 .rp-catlist > summary{cursor:pointer;font-weight:600;color:var(--mut)}
 /* the detail sections */
 .rp-detail{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);
   gap:var(--rp-gap)}
 .rp-detail > .card{margin:0;align-self:start}
 @media(max-width:820px){.rp-detail{grid-template-columns:minmax(0,1fr)}}
 .rp-fcnum{margin-top:var(--rp-gap)}
 .rp-fcnum table{margin:0}
 .rp-fcnum th[scope=colgroup]{text-align:center;color:var(--ink)}
 .rp-fcnum th[scope=row]{text-transform:none;letter-spacing:0;
   font-size:var(--fs-table);color:var(--ink);font-weight:600}
 .rp-fcnum .rp-sw{display:inline-block;width:.8em;height:.8em;
   border-radius:2px;margin-right:.35em;vertical-align:-.05em;
   -webkit-print-color-adjust:exact;print-color-adjust:exact}
 /* the accuracy card: each member's table folded under its pooled line */
 details.rp-acc{margin:.35rem 0;border-top:1px solid var(--line);
   padding:.45rem 0 0}
 details.rp-acc > summary{cursor:pointer;font-size:var(--fs-body)}
 details.rp-acc > summary .rp-acc-m{font-weight:700}
 .rp-acc-hint{color:var(--mut);font-size:var(--fs-label);font-weight:500}
 abbr[title]{text-decoration:none}
 /* the run card */
 .rp-run .uk-fold-body{margin-left:0}
 /* the header's color-blind safe switch */
 .rp-btn[aria-pressed="true"]{background:var(--gold-bright);
   border-color:var(--gold-bright);color:var(--on-accent)}
 /* phones: the run settings wrap inside the card, and the view switch
    keeps the national button beside it */
 .rp-ctlpair{display:inline-flex;align-items:center;gap:.5rem .9rem;
   flex-wrap:wrap}
 @media(max-width:520px){
  .runsettings .kv{grid-template-columns:auto minmax(0,1fr);width:auto}
  .rp-controls{margin-left:0}
  .rp-jump .rp-jumpsel{margin-left:0}
  .brandsub{display:none}
 }
 /* Windows high contrast: a selected switch keeps its text, and the
    charts and the map keep their colours */
 @media (forced-colors:active){
  .uk-seg > button[aria-pressed="true"],.rp-btn[aria-pressed="true"],
  .viewtoggle .on{forced-color-adjust:none;background:Highlight;
   color:HighlightText;border-color:Highlight}
  .usmap-wrap svg,.g-svg,.g-key i,.rp-fcnum .rp-sw,.plotly-graph-div{
   forced-color-adjust:none}
 }"""


def page_style() -> str:
    """The report's stylesheet, one source: build_report embeds it, and
    legacy_theme_carry swaps it into stored reports whose markup still
    matches (see the class-coverage check there)."""
    return f"""<style>
 /* console identity, theme-aware: the token blocks below are the console's
    own (nau.css, verbatim: eight themes plus the high-contrast and
    color-vision modifiers), selected at open by the boot script; then the
    report's own tokens (members, bands, no data); then the console's face
    and header marks, inlined, and the UI kit (nau.css's tip rules and
    ui-kit.css, verbatim). The print block at the end flips to the
    console's light theme and the color-vision category scale so the page
    always prints as dark ink on a light surface. The inline usmap SVG
    reads --card, --accent, --map-nodata and the --cat-* scale: state
    borders match the card surface, no data reads as an explicit gap on
    every ground (hatched where nothing was reported), and the category
    fills follow the color-vision mode. */
{theme_token_css()}
{_report_tokens_css()}
{font_face_css()}
{logo_css()}
{kit_css()}
 /* ---- the report's own rules: the console's layout (nau.css) restated,
    the report's parts prefixed rp- ---- */
 *{{box-sizing:border-box}}
 :root{{--rp-gap:var(--sp-4,1.1rem)}}
 html{{color-scheme:var(--scheme,light)}}
 body{{margin:0;background:var(--bg);color:var(--ink);
      font:400 var(--fs-body)/1.5 {FONT_STACK}}}
 main{{width:100%;max-width:2560px;margin:0 auto;
      padding:clamp(.9rem,.5rem + .8vw,1.5rem) var(--page-x) 3rem}}
 a{{color:var(--gold);font-weight:600;text-decoration:none}}
 a:hover{{text-decoration:underline}}
 /* the header bar: the console's navbar lockup (mark, wordmark), the
    report's name, the way back at the right */
 .brandrow{{display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;
  margin:0 0 .8rem}}
 header.brandrow{{margin:0;padding:.55rem var(--page-x);
  background:var(--nav-bg);color:var(--nav-ink);
  border-bottom:1px solid var(--line);box-shadow:var(--shadow)}}
 .brand{{display:inline-flex;align-items:center;gap:.55rem;
  font-size:clamp(1.25rem,1rem + .5vw,1.45rem);font-weight:700;
  letter-spacing:.01em}}
 .brand em{{color:var(--accent-ink);font-style:normal}}
 .brand .mark{{flex:none;display:block;width:1.45em;height:1.45em;
  background:var(--logo) center/contain no-repeat;
  -webkit-print-color-adjust:exact;print-color-adjust:exact}}
 .brandsub{{color:var(--mut);font-size:var(--fs-label);font-weight:600;
  padding:.05em .6em;border:1px solid var(--line);
  border-radius:var(--r-pill)}}
 .brandrow .spacer{{flex:1}}
 h1{{font-size:var(--fs-h1);font-weight:700;margin:0;text-wrap:balance}}
 h2{{font-size:1.15rem;font-weight:700;margin:.2rem 0 .6rem}}
 .card h2,.rp-kicker{{font-size:var(--fs-h2);margin:0 0 .55rem;
    text-transform:uppercase;letter-spacing:.05em;color:var(--mut);
    font-weight:600}}
 .card .uk-heading > h2{{margin:0}}
 .sub{{color:var(--mut);margin:.2rem 0 1rem;font-size:var(--fs-sub)}}
 .hint{{color:var(--mut);font-size:var(--fs-hint)}}
 .card p{{margin:.45rem 0}}
 /* the title row: title and week, then the controls at the right */
 .rp-titlerow{{display:flex;align-items:center;flex-wrap:wrap;
  gap:.6rem 1rem;margin:0 0 var(--sp-2,.6rem)}}
 .rp-title{{display:flex;align-items:center;flex-wrap:wrap;
  gap:.35rem .75rem;min-width:0}}
 .rp-week{{display:inline-flex;align-items:center;gap:.35em;
  color:var(--mut);font-size:var(--fs-label);font-weight:650;
  font-variant-numeric:tabular-nums}}
 .rp-controls{{display:flex;align-items:center;flex-wrap:wrap;
  gap:.5rem .9rem;margin-left:auto}}
 .rp-ctl{{display:inline-flex;align-items:center;gap:.4rem}}
 .rp-ctl > .rp-lbl{{color:var(--mut);font-size:var(--fs-label);
  font-weight:600}}
 /* buttons: the console's secondary outline (nau.css button, a.btn) */
 button{{font:inherit}}
 .rp-btn,button.backbtn,#natbtn{{display:inline-flex;align-items:center;
  gap:.35em;padding:.3rem .8rem;border:1px solid var(--btn-ink);
  border-radius:8px;background:transparent;color:var(--btn-ink);
  font-size:var(--fs-label);font-weight:650;line-height:1.4;
  cursor:pointer;text-decoration:none;white-space:nowrap}}
 .rp-btn:hover,button.backbtn:hover,#natbtn:hover{{text-decoration:none;
  background:color-mix(in srgb,var(--btn-ink) 11%,transparent)}}
 header.brandrow .rp-btn{{border-color:var(--field-line);color:var(--nav-ink)}}
 button:focus-visible,a:focus-visible{{
  outline:var(--focus-w,2px) solid var(--gold);outline-offset:2px}}
 .uk-seg > button{{cursor:pointer}}
 /* run-settings block: the console's compact two-column grid (see
    nau.css .runsettings), restated here because the report is
    self-contained */
 .runsettings{{margin:.45rem 0}}
 .runsettings > strong{{display:block;color:var(--mut);
    font-size:var(--fs-label);font-weight:600}}
 .runsettings .kv{{display:grid;
    grid-template-columns:max-content max-content;
    gap:.14rem 1.1rem;align-items:baseline;width:max-content;
    max-width:100%;margin:.25rem 0 0}}
 .runsettings .kv dt{{color:var(--mut)}}
 .runsettings .kv dd{{margin:0;font-weight:650;color:var(--ink);
    font-variant-numeric:tabular-nums;overflow-wrap:anywhere}}
 .card{{background:var(--card);border:1px solid var(--line);
        border-radius:10px;padding:.85rem 1rem;margin:0 0 var(--rp-gap);
        box-shadow:var(--shadow);overflow-x:auto}}
 .grid2{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);
        gap:var(--rp-gap)}}
 .grid2 > .card{{margin:0}}
 @media(max-width:820px){{.grid2{{grid-template-columns:minmax(0,1fr)}}}}
 .offseason{{color:var(--mut);font-size:var(--fs-hint);font-style:italic;
             margin:.2rem 0 .8rem}}
 /* the map card: its heading names the model the fills come from */
 .rp-mapcard{{overflow:visible}}
 .rp-mapcard > .uk-heading{{flex-wrap:wrap;row-gap:.3rem}}
 .mapcap{{max-width:min(880px,100%);margin:0 auto}}
 .mapcap svg{{max-height:58vh}}
 .rp-legends{{display:flex;flex-wrap:wrap;align-items:center;
  justify-content:center;gap:.2rem 1.6rem;margin:.5rem 0 0}}
 .rp-legends .uk-legend{{margin:.2rem 0}}
 .rp-legends .rp-lbl{{color:var(--mut);font-size:var(--fs-label);
  font-weight:600;margin-right:.1rem}}
 .rp-conf{{display:inline-flex;align-items:center;gap:.5rem}}
 /* earlier reports' legend rows (legacy_theme_carry) */
 .legend{{display:flex;gap:1.1rem;flex-wrap:wrap;color:var(--mut);
          font-size:var(--fs-hint);margin:.4rem 0 0 .2rem}}
 .legend span{{display:inline-flex;align-items:center;gap:.35rem}}
 .sw{{width:13px;height:13px;border-radius:3px;display:inline-block;
     -webkit-print-color-adjust:exact;print-color-adjust:exact}}
 .uk-sw{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
 /* a state's (or the nation's) detail */
 section.state{{margin:0;scroll-margin-top:4.2rem}}
 .rp-sechead{{display:flex;align-items:center;flex-wrap:wrap;
  gap:.4rem .8rem;margin:0 0 .6rem}}
 .rp-sechead h2{{margin:0;font-size:var(--fs-lead,1.15rem)}}
 .rp-sechead .backbtn{{margin:0}}
 .rp-nat-empty{{margin:0 0 .75rem}}
 table{{border-collapse:collapse;font-size:var(--fs-table);
        margin:.6rem 0 0;font-variant-numeric:tabular-nums}}
 td,th{{padding:.38rem .6rem;border-bottom:1px solid var(--line);
        text-align:left}}
 th{{color:var(--mut);font-weight:600;font-size:var(--fs-micro);
     text-transform:uppercase;letter-spacing:.04em}}
 td.num,th.num{{text-align:right}}
 tr.total td{{font-weight:750;border-top:2px solid var(--line);
              border-bottom:0}}
 /* the console's alert pair: below 1 beats baseline, everywhere */
 .ok{{color:var(--ok)}}.bad{{color:var(--bad)}}
 .relwis{{font-variant-numeric:tabular-nums;font-weight:650}}
 .num.hint{{color:var(--mut)}}
 /* the run: wall time and settings */
 .rp-run .uk-stats{{margin:0 0 .3rem}}
 /* earlier reports' pill toggles and buttons (legacy_theme_carry) */
 .viewtoggle{{display:flex;gap:.5rem;margin:1rem 0 0}}
 .viewtoggle button{{background:transparent;color:var(--btn-ink);
   border:1px solid var(--btn-ink);border-radius:8px;
   padding:.45rem .95rem;font-weight:650;cursor:pointer}}
 .viewtoggle .on{{background:var(--gold-bright);
                  border-color:var(--gold-bright);color:var(--on-accent)}}
 .backbtn{{margin:.2rem 0 .6rem}}
{_report_css()}
 @media print{{
  :root{{--bg:#FFFFFF;--card:#FFFFFF;--ink:#000F7E;--mut:#565E96;
   --line:#DCD8E9;--accent:#0173A9;--accent-ink:#0173A9;--gold:#0173A9;
   --nav-bg:#FFFFFF;--nav-ink:#000F7E;
   --ok:#177245;--warn:#8A5A14;--bad:#C42840;--map-nodata:#8E89A6;
   --shadow:none;--model-analogue:{ANALOGUE_ON_LIGHT};--rp-band-a:.22;
   --cat-large-decrease:#2C7BB6;--cat-decrease:#ABD9E9;
   --cat-stable:#B9B09B;--cat-increase:#FDAE61;
   --cat-large-increase:#D7191C}}
  body{{background:#FFFFFF;color:#000F7E}}
  button,select,.viewtoggle,.uk-seg,.rp-controls,.tip,.uk-tt,#appback,
  .backbtn,.rp-jump,.rp-pooled{{display:none!important}}
  .card{{box-shadow:none;break-inside:avoid}}
  main > .card,main > section,main > aside{{margin-bottom:3mm}}
  .rp-summary{{font-size:9.5pt;margin-bottom:2mm}}
  .rp-titlerow{{margin-bottom:1mm}}
  .rp-catlist{{font-size:7pt;margin-top:1.5mm}}
  .rp-catlist > summary{{display:none}}
  .mapcap{{max-width:150mm}}
  .mapcap svg{{max-height:80mm}}
  .rp-legends{{margin-top:1mm;font-size:8pt}}
  .rp-mapcard{{padding:3mm 4mm}}
  .rp-catlist dl{{gap:0 3mm}}
  /* a detail section opened before printing starts its own page, its
     heading kept with what follows */
  section.state{{break-before:page}}
  .rp-sechead,.uk-heading,h2,h3{{break-after:avoid}}
  .rp-detail{{grid-template-columns:minmax(0,1fr)}}
  /* "This run" under the last grid page: compact, two pairs a row */
  .rp-run{{break-before:auto;padding:2mm 3mm;font-size:8pt}}
  .rp-run .uk-stats{{font-size:8pt}}
  .rp-run .runsettings .kv{{grid-template-columns:repeat(2,max-content minmax(0,1fr));
   width:100%;gap:0 4mm;font-size:7.5pt}}
  .rp-run details > summary{{display:none}}
 }}
</style>"""


# --------------------------------------------------------- 5. the report
def _md(iso: str) -> str:
    """'2026-08-29' -> 'Aug 29' (the value back when it does not parse)."""
    from datetime import date as _date
    try:
        d = _date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    return f"{d.strftime('%b')} {d.day}"


def report_dates(asof: str) -> dict:
    """The report's dates from its as-of: the reference date (as-of + 7,
    submit.hub_reference_date's rule) and the four target weeks (horizons
    0 to 3: the reference date and the three Saturdays after it)."""
    from datetime import date as _date, timedelta as _td
    try:
        a = _date.fromisoformat(str(asof)[:10])
    except ValueError:
        return {}
    ref = a + _td(days=7)
    targets = [ref + _td(days=7 * h) for h in range(4)]
    return {"asof": a, "ref": ref.isoformat(), "targets": targets,
            "line": (f"Data through {a.strftime('%a %b')} {a.day}, {a.year}"
                     f" · forecasts for {_md(targets[0].isoformat())} "
                     f"to {_md(targets[-1].isoformat())} (FluSight reference"
                     f" date {ref.isoformat()})")}


def _run_time(seconds) -> str:
    """Wall time in words: "30 min 34 s", "1 h 2 min 5 s" ("" if unknown)."""
    try:
        s = int(round(float(seconds)))
    except (TypeError, ValueError):
        return ""
    if s < 0:
        return ""
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    parts = ([f"{h} h"] if h else []) + ([f"{m} min"] if h or m else []) \
        + [f"{sec} s"]
    return " ".join(parts)


#: run-settings rows a saved report leaves out: an engine the run machine
#: did not have, or a version the run never resolved
_HIDDEN_SETTING = re.compile(
    r"<dt>[^<]*</dt>\s*<dd>\s*(?:not installed|resolving(?:…|\.\.\.)?)"
    r"\s*</dd>")


def _pooled_figures(summary_html: str) -> list:
    """[(member, pooled relWIS, scored weeks)] from the accuracy card: the
    folded tables' data attributes, else (older reports) each table's
    header and pooled row."""
    out = []
    for m, v, n in re.findall(r'class="rp-acc" data-model="([^"]+)" '
                              r'data-pooled="([\d.]+)" data-n="(\d+)"',
                              summary_html or ""):
        out.append((MODEL_SHORT.get(m, m), float(v), int(n)))
    if out:
        return out
    for tbl in (summary_html or "").split("<table")[1:]:
        h = re.search(r'<th class="num">(?:<abbr[^>]*>)?([^<]+?) relWIS', tbl)
        t = re.search(r'<tr class="total"><td>[^<]*</td><td class="num '
                      r'(?:ok|bad)">([\d.]+)</td><td class="num hint">'
                      r'(\d+)</td>', tbl)
        if h and t:
            out.append((h.group(1), float(t.group(1)), int(t.group(2))))
    return out


def _accuracy_card(summary_html: str, kit) -> str:
    """The accuracy card in the current design: its heading in sentence
    case with the relWIS reading beside it and the rule in its "?"; an
    older report's tables pass through unchanged."""
    if not summary_html:
        return ""
    from markupsafe import Markup
    from app.core.scoring import RELWIS_HINT
    head = str(kit.heading(
        "Forecast accuracy, past weeks", id="acc",
        tiptext="relWIS is a model's weighted interval score (WIS) divided "
                "by the FluSight baseline's on the same weeks, pooled as a "
                "ratio of sums. Open a model's line for its table by "
                "location.",
        after=Markup(f'<span class="rp-acc-hint">relWIS: {RELWIS_HINT}'
                     '</span>')))
    out, n = re.subn(
        r"<div class='card'(?: id='accuracy')?><h2>(?:forecast accuracy "
        r"\(retrospective\)|Forecast accuracy, past weeks)</h2>",
        '<div class="card" id="accuracy">' + head.replace("\\", "\\\\"),
        summary_html, count=1)
    return out


def _forecast_numbers(key: str, members: dict, times: list) -> str:
    """The detail's forecast numbers: for each target week and member the
    median and the 50% and 95% intervals. members: model -> {time: {level:
    value}} (whole admissions where they come from the grid)."""
    order = ([m for m in reversed(FAN_MODELS) if m in members]
             + [m for m in members if m not in FAN_MODELS])
    if not order or not times:
        return ""

    def f(v):
        return f"{v:,.0f}"
    head1 = "".join(
        f'<th scope="colgroup" colspan="3"><span class="rp-sw" '
        f'style="background:var(--model-{m},{_member_hex(m)})"></span>'
        f'{MODEL_SHORT.get(m, m)}</th>' for m in order)
    head2 = "".join('<th class="num">Median</th><th class="num">50%</th>'
                    '<th class="num">95%</th>' for _m in order)
    rows = []
    for t in times:
        tds = []
        for m in order:
            q = members[m].get(str(t))
            if not q:
                tds.append('<td class="num hint" colspan="3">none</td>')
                continue
            tds.append(f'<td class="num">{f(_q_at(q, 0.5))}</td>'
                       f'<td class="num">{f(_q_at(q, 0.25))} to '
                       f'{f(_q_at(q, 0.75))}</td>'
                       f'<td class="num">{f(_q_at(q, 0.025))} to '
                       f'{f(_q_at(q, 0.975))}</td>')
        rows.append(f'<tr><th scope="row">{_md(t)}</th>{"".join(tds)}</tr>')
    return (f'<div class="card rp-fcnum" id="num-{key}">'
            '<div class="uk-heading"><h3>Forecast numbers</h3></div>'
            '<table><thead><tr><th rowspan="2">Week ending</th>'
            f'{head1}</tr><tr>{head2}</tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def _summary_line(grid, state_cards: dict, model: str) -> str:
    """One paragraph under the title, from the grid panels at render time:
    the US latest count and its week-on-week change, the Oracle SIHRS
    median and 95% interval for the last target week, how many states
    lean toward an increase or a decrease next week (the map's model) and
    how many panels are flagged."""
    from app.core import report_grid
    panels = (grid or {}).get("panels") or []
    bits = []
    us = next((p for p in panels if p.get("key") == "US"), None)
    if us and us.get("observed"):
        o = us["observed"]
        s = (f"United States: <b>{o[-1][1]:,.0f}</b> admissions in the week "
             f"ending {_md(o[-1][0])}")
        if len(o) > 1 and o[-2][1] > 0:
            ch = (o[-1][1] - o[-2][1]) / o[-2][1]
            if abs(ch) < 0.005:
                s += ", about the same as the week before"
            else:
                word, cls = ("up", "rp-up") if ch > 0 else ("down", "rp-down")
                s += (f', <span class="{cls}">{word} {abs(ch):.0%}</span> '
                      "on the week before")
        bits.append(s + ".")
        fan = (us.get("models") or {}).get("pf") or \
            next(iter((us.get("models") or {}).values()), None)
        if fan and fan.get("q") and fan.get("times"):
            r = fan["q"][-1]
            who = "Oracle SIHRS" if (us.get("models") or {}).get("pf") \
                else "Groundhog"
            bits.append(f"{who} median for {_md(fan['times'][-1])}: "
                        f"<b>{r[2]:,.0f}</b> (95% interval {r[0]:,.0f} to "
                        f"{r[4]:,.0f}).")
    up = down = 0
    states = {f for f in usmap.state_paths()}
    for c in (state_cards or {}).values():
        probs = (c or {}).get("probs") or {}
        if not probs or (c or {}).get("fips") not in states:
            continue        # the nation and Puerto Rico are not states
        modal = max(probs, key=probs.get)
        up += modal in ("increase", "large_increase")
        down += modal in ("decrease", "large_decrease")
    if up or down:
        def n(k):
            return f"{k} state" + ("" if k == 1 else "s")
        verb = "leans" if up == 1 else "lean"
        bits.append(f"Next week ({MODEL_SHORT.get(model, model)}): "
                    f"{n(up)} {verb} toward an increase, {n(down)} toward a "
                    "decrease.")
    if panels:
        k = sum(1 for p in panels if report_grid.flags(p))
        bits.append(f"{k} of {len(panels)} locations flagged for a closer "
                    "look." if k else "No location flagged for a closer look.")
    if not bits:
        return ""
    return '<p class="rp-summary" id="summary">' + " ".join(bits) + "</p>"


def _category_lists(by_model: dict, order: list, default: str, names: dict,
                    gap: set, nofc: dict, unfitted: set) -> str:
    """The states by category in words, under the map (a screen reader and
    a paper copy read the map through it); one list per model on the
    toggle, the shown one following it."""
    if not by_model:
        return ""
    blocks = []
    for m in order:
        cards = by_model.get(m) or {}
        groups = {c: [] for c in reversed(CATS)}
        have = set()
        for card in cards.values():
            f = (card or {}).get("fips")
            probs = (card or {}).get("probs") or {}
            if not f or not probs or f not in names:
                continue
            groups[max(probs, key=probs.get)].append(names[f])
            have.add(f)
        rows = []
        for c, ns in groups.items():
            if ns:
                rows.append((cat_fill(c), CAT_LABEL[c].capitalize(), ns))
        nf = sorted(names[f] for f in (nofc.get(m) or set())
                    if f in names and f not in have)
        gp = sorted(names[f] for f in gap if f in names)
        un = sorted(names[f] for f in unfitted if f in names)
        if gp:
            rows.append((usmap.GAP_SWATCH, "No data", gp))
        if nf:
            rows.append((NO_DATA, "No forecast", nf))
        if un:
            rows.append((NO_DATA, "Not fitted", un))
        if not rows:
            continue
        dl = "".join(
            f'<dt><span class="uk-sw" style="--sw:{col}" aria-hidden="true">'
            f'</span>{lbl}</dt><dd>{", ".join(sorted(ns))}</dd>'
            for col, lbl, ns in rows)
        hidden = "" if m == default else " hidden"
        blocks.append(f'<div class="rp-catmodel" data-catmodel="{m}"{hidden}>'
                      f'<dl aria-label="States by category, '
                      f'{MODEL_SHORT.get(m, m)}">{dl}</dl></div>')
    if not blocks:
        return ""
    return ('<details class="rp-catlist" id="catlist" open>'
            '<summary>States by category</summary>' + "".join(blocks)
            + "</details>")


def build_report(asof: str, state_cards: dict, state_details: dict,
                 national: dict, out_path: Path,
                 national_map_html: str = "", elapsed_s=None,
                 settings_html: str = "", model_label: str = "",
                 cards_by_model: dict | None = None,
                 national_map_cards: dict | None = None,
                 cards_model: str = "",
                 fitted_fips=None, national_in_run=None,
                 gap_fips=None, no_forecast=None, grid=None) -> Path:
    """asof: the run's as-of date (the page names it with the reference
    date and the target weeks).
    state_cards: abbr -> hover-card data (choropleth).
    state_details: abbr -> dict(name, fan=…, cat=…, acc=…, table_rows=[…],
    numbers={model: {time: {level: value}}}, times=[…]).
    national: dict(fan=…, acc=…, summary_html=str, numbers, times).
    national_map_html: usmap.national_svg output; adds the state/national view toggle.
    elapsed_s, settings_html: the run card; omitted when not given.
    model_label: who computed the map's cards (MODEL_LABEL); default PF.
    cards_by_model / national_map_cards: per-model cards; with two or more
    models a model toggle swaps fills, hovers and label client-side.
    cards_model: the model the map is rendered with (the toggle's default).
    fitted_fips: fips the run fitted, or None; gates every no-data claim
    (in scope = reporting gap, outside = not fitted, None = only 'no data').
    national_in_run: False when US was not among the run's locations (the
    national detail then says so instead of waiting on scores or a fan);
    None = unknown (older bundles), the wording claims nothing.
    gap_fips: in-scope fips with no reported data (the only reporting
    gaps); None (older bundles): a card-less state in scope is the gap and
    a bare card is "no forecast". no_forecast: model -> {fips: reason} for
    in-scope states that have data but no forecast from that model.
    grid: the bundle's "grid" (report_grid), drawn as the "All locations"
    pages under the detail sections; None (older bundles): no such pages."""
    # build-time SVG map (usmap): plotly geo fetches its geometry from a CDN
    svg_map = usmap.svg_map
    cards_by_fips = {c["fips"]: c for c in state_cards.values() if "fips" in c}
    # card-less states: gaps (in scope) vs not fitted (out); no record: 'no data'
    scope = set(fitted_fips) if fitted_fips is not None else None
    no_card = set(usmap.state_paths()) - set(cards_by_fips)
    # a card with no probabilities: inside the scope the member made no
    # forecast there (the Groundhog from a last count of 0); outside it the
    # state was never run (the pipeline gives every state a bare card), so
    # it is 'not fitted', as its hover already says
    blank = {f for f, c in cards_by_fips.items() if not c.get("probs")}
    gaps = set(gap_fips) if gap_fips is not None else None
    no_forecast = no_forecast or {}
    if scope is None:
        gap_states = set()
    elif gaps is None:
        gap_states = no_card & scope
    else:
        gap_states = (no_card | blank) & scope & gaps
    unfitted_states = ((no_card | blank) - scope) if scope is not None \
        else set()
    # only states that actually have a detail section invite a click; the
    # hovers read the same gap / no-forecast split as the legend below
    map_html = svg_map(cards_by_fips, clickable=set(state_details),
                       scope_fips=scope, gap_fips=gaps,
                       reasons=no_forecast.get(cards_model or "pf"))
    # the kit's components (templates/_tips.html), rendered here
    kit = kit_macros()
    # legend: the categories, then each no-data flavour only when some
    # state wears it, its explanation in the chip's "?"
    legend_items = [{"color": cat_fill(c), "text": CAT_LABEL[c]}
                    for c in CATS]

    def _nodata(text, tip, color=NO_DATA):
        legend_items.append({"color": color, "text": text, "tip": tip})

    if scope is None:
        if no_card:
            _nodata("no data in this view",
                    "No-data states have no data in this report's inputs.")
    else:
        if gap_states:
            # hatched, as on the map: nothing reported
            _nodata("no data",
                    "Nothing was reported for these states this week. Gaps "
                    "are shown, never filled in.", usmap.GAP_SWATCH)
        if unfitted_states:
            _nodata("not fitted in this run",
                    "Not-fitted states were outside this run's scope.")
    # in-scope states with data but no forecast, filled like no data
    if scope is None:
        unforecast = blank
    elif gaps is None:
        unforecast = blank & scope
    else:
        unforecast = ((no_card | blank) & scope) - gaps
    if unforecast:
        _nodata("no forecast",
                "No-forecast states have data but no forecast from this "
                "model this week.")
    legend_html = kit.legend(legend_items, label="Categories", id="map-legend")
    # confidence: the modal category's fill at the three map opacities
    # (usmap._card_fill), drawn as the same mix over the card
    conf_html = kit.legend(
        [(f"color-mix(in srgb,{cat_fill('increase')} {pct}%,var(--card))",
          word) for pct, word in ((64, "leaning"), (82, "likely"),
                                  (100, "confident"))],
        label="Confidence", id="map-conf")
    model_label = model_label or MODEL_LABEL["pf"]
    # model toggle only for 2+ models with usable (fips + probs) cards, the
    # bar the home outlook applies; an empty model would be an inert button
    model_toggle_html = ""
    cbm = {m: c for m, c in (cards_by_model or {}).items()
           if any(isinstance(v, dict) and v.get("fips") and v.get("probs")
                  for v in (c or {}).values())}
    order = toggle_models(cbm)
    default = cards_model or "pf"
    if len(order) >= 2:
        default = cards_model if cards_model in order else order[0]
        payload = {}
        for m in order:
            byf = {c["fips"]: c for c in cbm[m].values()
                   if isinstance(c, dict) and c.get("fips")}
            payload[m] = {
                # scope rides along so swapped hovers match the rendered map
                "states": usmap.state_swap_payload(
                    byf, scope_fips=scope, gap_fips=gaps,
                    reasons=no_forecast.get(m)),
                "us": usmap.nat_swap_payload(
                    (national_map_cards or {}).get(m) or {})}
        # the kit's segmented switch (aria-pressed marks the choice)
        model_toggle_html = usmap.model_toggle(
            order, MODEL_LABEL, default, payload,
            group_id="outlook-model", btn_class="", active_class="on",
            wrap_class="uk-seg", short_labels=MODEL_SHORT)
    if model_toggle_html:
        model_toggle_html = ('<span class="rp-ctl"><span class="rp-lbl" '
                             'aria-hidden="true">Model</span>'
                             f'{model_toggle_html}</span>')

    # the states by category in words, one list per model on the toggle
    names = {f: n for f, (n, _d) in usmap.state_paths().items()}
    nofc = {}
    for m in (order if len(order) >= 2 else [default]):
        have = {c.get("fips") for c in (cbm.get(m) or {}).values()
                if isinstance(c, dict) and c.get("probs")}
        if m == default and not cbm.get(m):
            have = {f for f, c in cards_by_fips.items() if c.get("probs")}
        nofc[m] = (unforecast | set(no_forecast.get(m) or {})) - have
    lists_by_model = dict(cbm) if len(order) >= 2 else {
        default: {a: c for a, c in state_cards.items()}}
    cat_lists = _category_lists(
        lists_by_model, order if len(order) >= 2 else [default], default,
        names, gap_states, nofc, unfitted_states)

    # the map's explainer: hover, the click invitation only when some
    # state has a section to open, zoom
    click_hint = (", click it for detail (or Tab to it and press Enter)"
                  if any(a != "US" for a in state_details) else "")
    map_tip = kit.tip("map", "the map",
                      f"Hover a state for its category probabilities"
                      f"{click_hint}; Ctrl+scroll zooms (⌘ on Mac).")
    sections = []
    back_btn = ('<button type="button" class="backbtn" '
                'onclick="backToMap()">&larr; back to map</button>')

    def _note(key, note):
        """A detail's note (the off-season reading) as a badge, the note
        itself in its "?"."""
        if not note:
            return ""
        word = ("off-season" if str(note).lower().startswith("off-season")
                else "note")
        return str(kit.badge("info", word, tiptext=note, id=f"note-{key}"))

    fan_tip = ("Weekly hospital admissions: the observed weeks, then each "
               "model's median (joined to the latest week) with its 50% and "
               "95% intervals shaded; the Groundhog's 95% interval is "
               "outlined. Click a legend entry to hide that model.")
    for a, d in state_details.items():
        if a == "US":          # national renders in its own curated section
            continue
        rows = "".join(f'<tr><td>{_md(r[0])}</td><td class="num">'
                       f'{float(r[1]):,.0f}</td></tr>'
                       for r in d.get("table_rows", []))
        fan_head = str(kit.heading("Weekly admissions", id=f"fan-{a}",
                                   tiptext=fan_tip, level=3))
        who = MODEL_SHORT.get(d.get("model") or "pf", "Oracle SIHRS")
        cat_head = str(kit.heading(
            f"Rate-change outlook, next week ({who})", id=f"cat-{a}",
            level=3,
            tiptext=f"FluSight's rate-change categories for next week, from "
                    f"the {who} forecast: the chance of each."))
        numbers = _forecast_numbers(a, d.get("numbers") or {},
                                    d.get("times") or [])
        sections.append(f"""
<section class="state" id="st-{a}" hidden aria-labelledby="h-st-{a}">
  <div class="rp-sechead">{back_btn}<h2 id="h-st-{a}">{d['name']}</h2>{_note(a, d.get('note'))}</div>
  <div class="rp-detail">
    <div class="card">{fan_head}{_html(d['fan'])}</div>
    <div class="card">{cat_head}{_html(d['cat'])}
      <table><tr><th>Week ending</th><th class="num">Admissions</th></tr>{rows}</table></div>
  </div>
  {numbers}
</section>""")

    # national chart cards only when their figure exists; else an empty
    # state whose "?" says when they come
    nat_cards = []
    if national.get("fan"):
        nat_head = str(kit.heading("Weekly admissions, United States",
                                   id="fan-US", tiptext=fan_tip, level=3))
        nat_cards.append(f'<div class="card">{nat_head}'
                         f'{_html(national["fan"])}</div>')
        nat_num = _forecast_numbers("US", national.get("numbers") or {},
                                    national.get("times") or [])
        if nat_num:
            nat_cards.append(nat_num)
    nat_body = "\n  ".join(nat_cards) or str(kit.empty(
        "No national charts yet", "clock", id="nat-wait", compact=True,
        tiptext="National fan and accuracy charts appear once the "
                "national model run lands."))
    # A console run fits US directly, so a national forecast here is FITTED
    # (never the constructed sum) and says so. Claim it only when the
    # national fan exists (nat_cards); summary_html is always filled (even
    # unscored), so it is not evidence of a national run.
    from app.core import us_national as _usn
    has_national = bool(nat_cards)
    nat_prov = str(kit.badge(
        "info", _usn.LABELS[_usn.FITTED], tiptext=_usn.NOTES[_usn.FITTED],
        id="nat-prov")) if has_national else ""
    nat_summary = national.get('summary_html', '')
    if national_in_run is False and not has_national:
        # the real reason, not "once truth is published" or "once the
        # national model run lands": US was never asked for
        nat_prov = ""
        nat_body = str(kit.empty("US (national) was not part of this run.",
                                 "info", id="nat-none", compact=True))
        from app.core.scoring import NO_SCORES_HTML
        # only placeholders (the default one, or a model's named one)
        if NO_SCORES_HTML in nat_summary or (
                "no scored weeks yet" in nat_summary.lower()
                and "<table" not in nat_summary):
            nat_summary = ""
    pooled = _pooled_figures(nat_summary)
    nat_summary = _accuracy_card(nat_summary, kit)
    # the US chart first, then the accuracy tables (folded)
    nat = f"""
<section class="state" id="st-US" hidden aria-labelledby="h-st-US">
  <div class="rp-sechead">{back_btn}<h2 id="h-st-US">United States</h2>{nat_prov}{_note('US', national.get('note'))}</div>
  {nat_body}
  {nat_summary}
</section>"""

    # view toggle + second (national) map, only when a national map was given
    view_toggle = ""
    nat_map_div = ""
    if national_map_html:
        view_toggle = """<span class="rp-ctl"><span class="rp-lbl" aria-hidden="true">View</span>
<div class="uk-seg" role="group" aria-label="Map view">
 <button type="button" id="btn-state-view" class="on" aria-pressed="true">States</button>
 <button type="button" id="btn-national-view" aria-pressed="false">Nation</button>
</div></span>"""
        nat_map_div = f'<div id="map-national" class="mapcap" hidden>{national_map_html}</div>'

    # plotly.js in the head, once, iff any figure is embedded
    plotly_js = ("<script>" + html_page.plotly_js() + "</script>"
                 if state_details or national.get("fan") else "")

    # the run card: run time, then the settings folded (which run produced
    # this?); rows that only say an engine was missing on that machine stay
    # out of a shared copy
    run_bits = ""
    if elapsed_s is not None:
        from app.core.runs import fmt_hms
        words = _run_time(elapsed_s) or fmt_hms(elapsed_s)
        run_bits = ('<dl class="uk-stats uk-stats--row">'
                    + str(kit.stat("Run time", words, id="runtime",
                                   tiptext=f"Wall time {fmt_hms(elapsed_s)} "
                                           "(h:mm:ss), the whole run on its "
                                           "machine."))
                    + "</dl>")
    if settings_html:
        shown = _HIDDEN_SETTING.sub("", settings_html)
        run_bits += ('<details class="uk-fold rp-rundetails" id="run-details">'
                     '<summary><span class="uk-fold-sum">Run details</span>'
                     f'</summary><div class="uk-fold-body">{shown}</div>'
                     "</details>")
    footer = (f'<section class="card rp-run" id="run" aria-labelledby="h-run">'
              f'{kit.heading("This run", id="run")}{run_bits}</section>'
              if run_bits else "")

    # every location at a glance (report_grid): a panel title opens the
    # location's detail section where there is one
    from app.core import report_grid
    have_detail = {a for a in state_details if a != "US"}
    if national.get("fan"):
        have_detail.add("US")
    grid_section = report_grid.grid_html(grid, MEMBER_COLORS,
                                         details=have_detail)
    grid_style = (f"<style>{report_grid.grid_css()}</style>"
                  if grid_section else "")
    # the national forecast, larger, under the map (the first printed
    # page's spare height)
    us_feature = report_grid.us_feature_html(grid, MEMBER_COLORS)

    dates = report_dates(asof)
    week_line = dates.get("line") or f"week of {asof}"
    ref = dates.get("ref") or asof
    summary = _summary_line(grid, state_cards, default)

    # pooled relWIS per model beside the map heading, linking to the
    # accuracy tables in the national detail
    pooled_html = ""
    if pooled:
        pooled_html = ('<span class="rp-pooled" aria-label="Pooled relWIS">'
                       + "".join(
                           f'<a href="#accuracy" onclick="openAccuracy();'
                           f'return false">{_esc(m)} <b class="'
                           f'{"ok" if v < 1 else "bad"}">{v:.3f}</b></a>'
                           for m, v, _n in pooled)
                       + '<span>pooled relWIS</span></span>')

    # the jump bar: the page's parts, then any location's panel
    jumps = [("#map-anchor", "Map")]
    if us_feature:
        jumps.append(("#us-feature", "United States"))
    elif national.get("fan"):
        jumps.append(("#st-US", "United States"))
    if grid_section:
        jumps.append(("#all-locations", "All locations"))
    if "id=\"accuracy\"" in nat_summary:
        jumps.append(("#accuracy", "Accuracy"))
    if footer:
        jumps.append(("#run", "This run"))
    jump_links = " ".join(
        f'<a href="{h}" data-jump="{h[1:]}">{t}</a>' for h, t in jumps)
    loc_opts = ""
    if grid_section:
        loc_opts = "".join(
            f'<option value="g-{_esc(str(p.get("key", "")))}">'
            f'{_esc(str(p.get("name", p.get("key", ""))))}</option>'
            for p in (grid or {}).get("panels") or [])
        loc_opts = ('<label class="rp-jumpsel">Jump to location '
                    '<select id="jumploc"><option value="">Choose</option>'
                    f'{loc_opts}</select></label>')
    jump_bar = (f'<nav class="rp-jump" aria-label="Sections">{jump_links}'
                f'{loc_opts}</nav>')

    natbtn = '<button type="button" id="natbtn">US forecast detail</button>'
    controls = (f'{model_toggle_html}'
                f'<span class="rp-ctlpair">{view_toggle}{natbtn}</span>')

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FluBNF weekly report, reference date {ref}</title>
{theme_boot_script()}
{plotly_js}
{page_style()}{grid_style}</head><body>
{page_header()}
<main>
<div class="rp-titlerow">
 <div class="rp-title"><h1>US influenza forecast</h1>
  <span class="rp-week">{kit.icon("calendar")}{week_line}</span></div>
 <div class="rp-controls">
  {controls}
 </div>
</div>
{summary}
{jump_bar}
<div class="card rp-mapcard" id="map-anchor">
 <div class="uk-heading"><h2 class="mapmodel" data-mapmodel-label>{model_label}</h2>{map_tip}{('<span class="uk-heading-aside">' + pooled_html + '</span>') if pooled_html else ''}</div>
 <div id="map-state" class="mapcap">{map_html}</div>
 {nat_map_div}
 <div class="rp-legends">
  {legend_html}
  <span class="rp-conf"><span class="rp-lbl" aria-hidden="true">Confidence</span>{conf_html}</span>
 </div>
 {cat_lists}
 {us_feature}
</div>
{"".join(sections)}
{nat}
{grid_section}
<script>
window.showState = show;
var _ab = document.getElementById('appback');
if (_ab && history.length > 1) {{ _ab.hidden = false; }}
if (location.hash && location.hash.indexOf('#st-') === 0 &&
    document.getElementById(location.hash.slice(1))) {{
  show(location.hash.slice(1));
}}
function show(id, then) {{
  var el = document.getElementById(id);
  if (!el) return;
  var all = document.querySelectorAll('section.state');
  for (var i = 0; i < all.length; i++) all[i].hidden = true;
  el.hidden = false;
  if (window.Plotly) {{
    var gs = el.querySelectorAll('.js-plotly-plot');
    for (var j = 0; j < gs.length; j++) Plotly.Plots.resize(gs[j]);
  }}
  var target = (then && document.getElementById(then)) || el;
  target.scrollIntoView({{behavior: 'smooth'}});
}}
window.backToMap = function() {{
  var all = document.querySelectorAll('section.state');
  for (var i = 0; i < all.length; i++) all[i].hidden = true;
  var m = document.getElementById('map-anchor');
  if (m) m.scrollIntoView({{behavior: 'smooth'}});
}};
window.openAccuracy = function() {{
  show('st-US', 'accuracy');
}};
document.getElementById('natbtn').addEventListener('click', function() {{ show('st-US'); }});
(function() {{
  // the jump bar: a hidden target (the national detail) opens first
  var nav = document.querySelector('.rp-jump');
  if (nav) nav.addEventListener('click', function(e) {{
    var a = e.target.closest ? e.target.closest('a[data-jump]') : null;
    if (!a) return;
    var id = a.getAttribute('data-jump');
    if (id === 'accuracy') {{ e.preventDefault(); window.openAccuracy(); }}
    else if (id === 'st-US') {{ e.preventDefault(); show('st-US'); }}
  }});
  var sel = document.getElementById('jumploc');
  if (sel) sel.addEventListener('change', function() {{
    var t = sel.value && document.getElementById(sel.value);
    if (!t) return;
    if (history.replaceState) history.replaceState(null, '', '#' + sel.value);
    else location.hash = sel.value;
    t.scrollIntoView({{behavior: 'smooth'}});
    var a = t.querySelector('figcaption a');
    if (a) a.focus({{preventScroll: true}});
  }});
  // the category lists follow the model toggle
  var g = document.getElementById('outlook-model');
  if (g) g.addEventListener('click', function(e) {{
    var b = e.target.closest ? e.target.closest('button[data-mmodel]') : null;
    if (!b) return;
    var ls = document.querySelectorAll('[data-catmodel]');
    for (var i = 0; i < ls.length; i++)
      ls[i].hidden = ls[i].getAttribute('data-catmodel') !== b.dataset.mmodel;
  }});
}})();
(function() {{
  var mS = document.getElementById('map-state'),
      mN = document.getElementById('map-national'),
      bS = document.getElementById('btn-state-view'),
      bN = document.getElementById('btn-national-view');
  if (!mN || !bS || !bN) return;
  var setView = function(v) {{
    mS.hidden = (v === 'national');
    mN.hidden = (v === 'state');
    bS.classList.toggle('on', v === 'state');
    bN.classList.toggle('on', v === 'national');
    bS.setAttribute('aria-pressed', String(v === 'state'));
    bN.setAttribute('aria-pressed', String(v === 'national'));
  }};
  bS.addEventListener('click', function() {{ setView('state'); }});
  bN.addEventListener('click', function() {{ setView('national'); }});
}})();
(function() {{
  // print: the light theme with the color-vision categories (the print
  // stylesheet's tokens), the charts redrawn to the page width, and the
  // folded run details open; the screen comes back after
  var saved = null, opened = [];
  function fire() {{ try {{ dispatchEvent(new Event('themechange')); }} catch (e) {{}} }}
  // the charts' step (_print_charts_js), on a page that has charts
  function resize(printing) {{
    if (window.rpPrintCharts) window.rpPrintCharts(printing);
  }}
  addEventListener('beforeprint', function() {{
    var de = document.documentElement;
    saved = [de.getAttribute('data-theme'), de.getAttribute('data-contrast'),
             de.getAttribute('data-vision')];
    de.setAttribute('data-theme', 'light');
    de.removeAttribute('data-contrast');
    de.setAttribute('data-vision', 'cvd');
    var ds = document.querySelectorAll('details.rp-rundetails:not([open])');
    for (var i = 0; i < ds.length; i++) {{ ds[i].open = true; opened.push(ds[i]); }}
    fire(); resize(true);
  }});
  addEventListener('afterprint', function() {{
    if (!saved) return;
    var de = document.documentElement, names = ['data-theme', 'data-contrast', 'data-vision'];
    for (var i = 0; i < 3; i++) {{
      if (saved[i] === null) de.removeAttribute(names[i]);
      else de.setAttribute(names[i], saved[i]);
    }}
    for (var j = 0; j < opened.length; j++) opened[j].open = false;
    saved = null; opened = [];
    fire(); resize(false);
  }});
}})();
</script>
{_retint_js() if plotly_js else ""}
{_week_ticks_js() if plotly_js else ""}
{_print_charts_js() if plotly_js else ""}
{footer}
</main>
<script>{kit_js()}</script>
</body></html>"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # atomic (a serve-time rebuild never exposes a half-write), and LF pinned:
    # /output/report (text read) and /output/report/download (raw bytes) must
    # return identical text on Windows too. utf-8, as the page's meta says:
    # the locale's code page (cp1252 on a Windows console started without
    # PYTHONUTF8) cannot write its symbols, and the run would end reportless
    tmp = out_path.with_name(out_path.name + ".tmp")
    tmp.write_text(html, encoding="utf-8", newline="\n")
    os.replace(tmp, out_path)
    return out_path


def _esc(s: str) -> str:
    return html_page.esc(s)


def save_bundle(bundle: dict, dirpath: Path) -> Path:
    """Persist the inputs bundle beside report.html, atomically, so the
    report can be rebuilt after any builder change without rerunning models."""
    p = Path(dirpath) / BUNDLE_NAME
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(bundle, separators=(",", ":"), default=float),
                   encoding="utf-8")
    os.replace(tmp, p)
    return p


def render_bundle(bundle: dict, out_path: Path) -> Path:
    """Render the weekly report from its inputs bundle: the one render path
    (live run and stale-report refresh alike). A v8 bundle's grid also
    gives each detail fan the other member's interval (its whole-admission
    quantiles) and the forecast numbers; an older bundle draws the one
    member its detail stored."""
    grid = bundle.get("grid")
    by_key = {p.get("key"): p for p in (grid or {}).get("panels") or []}
    details = {}
    for key, d in (bundle.get("details") or {}).items():
        fan_in = d.get("fan") or {}
        try:
            settled = [tuple(p) for p in (fan_in.get("settled") or [])]
            # v6 "model": whose fan the detail stored (absent: the PF's)
            model = d.get("model") or "pf"
            ft = fan_in["forecast_times"]
            panel_fans = (by_key.get(key) or {}).get("models") or {}
            others = {m: grid_quantiles(f) for m, f in panel_fans.items()
                      if m != model and f.get("times") == list(ft)}
            fan = fan_figure_from_quantiles(
                fan_in.get("observed_times") or [],
                fan_in.get("observed") or [],
                ft, fan_in["quantiles"],
                title=fan_in.get("title", ""), settled=settled or None,
                model=model, others=others)
            numbers = {model: fan_in["quantiles"], **others}
            details[key] = {
                "name": d.get("name", key), "note": d.get("note", ""),
                "fan": fan, "cat": cat_bar(d.get("cat_probs") or {}),
                "model": model,
                "table_rows": [tuple(r) for r in (d.get("table_rows") or [])],
                "numbers": numbers, "times": list(ft)}
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
        bundle_asof(bundle), bundle.get("cards") or {}, details,
        {"fan": us_d.get("fan"),
         "note": us_d.get("note", ""),
         "numbers": us_d.get("numbers"), "times": us_d.get("times"),
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
        fitted_fips=bundle.get("fitted_fips"),
        # v5 field (absent: None, the national detail claims nothing)
        national_in_run=bundle.get("national_in_run"),
        # v6 fields (absent: None, a card-less state in scope is the gap)
        gap_fips=bundle.get("gap_fips"),
        no_forecast=bundle.get("no_forecast"),
        # v8 field (absent: no "All locations" pages)
        grid=grid)


# ---------------------------------------------------------- 6. serve time
def builder_sources_mtime() -> float:
    """Newest mtime of the weekly report's builder sources (this module,
    html_page, scoring, usmap, nau.css, charts.js, and the UI kit it
    inlines: ui-kit.css, tips.js, _tips.html, the faces and the marks): a
    stored report.html older than this is stale."""
    srcs = [Path(__file__).with_name(m + ".py")
            for m in ("report_v2", "report_grid", "html_page", "scoring",
                      "us_national", "usmap")]
    kit = [html_page.KIT_CSS, html_page.KIT_JS, html_page.TIPS_TPL,
           html_page.FONTS_CSS, html_page.LOGOS_CSS]
    return max([0.0] + [p.stat().st_mtime
                        for p in srcs + [CHARTS_SRC, NAU_CSS] + kit
                        if p.is_file()])


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
