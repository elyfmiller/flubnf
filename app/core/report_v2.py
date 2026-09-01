"""Weekly HTML report v2: real US map, drill-down, theme-aware.

One self-contained file per week (plotly.js embedded once, no network):
  * geographic US choropleth, states shaded by modal rate-change category,
    intensity by its probability; hover = full stats card
  * optional national map view (one shared fill = national modal category),
    toggled with 'state view' / 'national view' buttons above the map
  * CLICK a state -> its section: forecast fan vs observed, categorical bar,
     recent-data table; every section
    has a '<- back to map' button (window.backToMap)
  * a National section with the same drill-down
  * no-data states render explicitly, never smoothed over, and say only
    what was checked: a card-less state inside the run's recorded scope is
    a verified reporting gap, one outside it is 'not fitted in this run',
    and a bundle with no scope record claims just 'no data'; annotated
    gaps in fans likewise (constitutional rule 10)
  * fluid layout: no fixed max-width, the map scales with the window
  * theme-aware, self-contained: the stylesheet embeds the console's four
    theme token blocks and both accessibility modifier blocks verbatim
    from nau.css, and a tiny inline script resolves the theme at open:
    served same-origin it reads the console's own localStorage keys, so
    the report opens in the reader's console preferences; opened as a
    standalone file it follows the OS (prefers-color-scheme,
    prefers-contrast). Print keeps the light stylesheet regardless.

The reports followed the app theme starting 2026-08-21 (user request),
superseding the fixed-dark spec of 2026-08-17. The colors and type stay
the console's own identity (nau.css tokens, DM Sans with a system fallback
and no webfont fetch).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np

# Build-time chart palette (nau.css dark theme, LANL Mesa-aligned):
# Near-Black ground, stepped indigo card, Cyan #34C0F0 as THE accent. The
# figures are BUILT with these literals and re-resolved at open against the
# embedded theme tokens (see _retint_js), so the charts wear the reader's
# resolved theme; a no-script render keeps the light chrome with the
# dark-kit charts, legible even if mismatched.
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
NO_DATA = "var(--map-nodata, #0a0a0a)"   # falls back to black without tokens
CAT_LABEL = {c: c.replace("_", " ") for c in CATS}

#: the console stylesheet: the ONE source of the theme token values every
#: report embeds, and therefore a builder input (builder_sources_mtime)
NAU_CSS = Path(__file__).resolve().parents[1] / "ui" / "static" / "nau.css"
#: the shared player core carries the one member-color map (marked JSON)
PLAYER_SRC = Path(__file__).resolve().parents[1] / "ui" / "static" \
    / "player.js"

#: fallback member colors, equal to the player's map: used only if the
#: marked JSON cannot be read (a broken checkout must not sink the report)
_MEMBER_COLOR_FALLBACK = {"ensemble": "#34C0F0", "pf": "#1979FF",
                          "analogue": "#FFC72C", "pf2s": "#A66395"}


def model_colors() -> dict:
    """The one member-color map, read from the shared player core.

    player.js carries the map as a marked JSON literal (the MODEL_NAMES
    pattern); the player and the console templates read it directly, and
    this parse hands the SAME values to every Python surface (both report
    builders, the server's template contexts), so a member can never wear
    different colors on different surfaces. Degrades to the equal
    fallback literals rather than raising."""
    try:
        src = PLAYER_SRC.read_text(encoding="utf-8")
        m = re.search(r"/\*MODEL_COLORS_JSON\*/\s*(\{.*?\})"
                      r"\s*/\*END_MODEL_COLORS_JSON\*/", src, re.S)
        return json.loads(m.group(1)) if m else dict(_MEMBER_COLOR_FALLBACK)
    except Exception:
        return dict(_MEMBER_COLOR_FALLBACK)


MEMBER_COLORS = model_colors()

#: fallback season-line palette, equal to the player's marked list: used
#: only if the marked JSON cannot be read (a broken checkout must not sink
#: the forecast data panel)
_SEASON_COLOR_FALLBACK = ["#A87300", "#3375FB", "#C9568C",
                          "#0087AF", "#B96D36", "#8568E3"]


def season_colors() -> list:
    """The one season-line palette, read from the shared player core.

    The model_colors contract applied to the season-over-season charts:
    player.js carries the palette as a marked JSON literal (SEASON_COLORS),
    and this parse hands the SAME values to every Python surface. Since
    2026-08-21 these literals are the RED-GREEN-SAFE set: the console
    resolves the --season-N tokens per draw (normal-vision tab10-adjacent
    by default, remapped onto these values under data-vision="cvd"), and
    this list is the fallback where the tokens are absent, so a surface
    without the stylesheet still wears the dichromat-spaced, ground-audited
    palette (see the SEASON_COLORS comment in player.js). Degrades to the
    equal fallback literals rather than raising."""
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


# fan bands derive from the PF member's shared color (the weekly fan IS the
# PF forecast): same alpha ramp as before, rgb from the one member map
_PF_COLOR = MEMBER_COLORS.get("pf", _MEMBER_COLOR_FALLBACK["pf"])
QBANDS = ((0.025, 0.975, _rgba(_PF_COLOR, 0.13), "95% interval"),
          (0.10, 0.90, _rgba(_PF_COLOR, 0.20), "80% interval"),
          (0.25, 0.75, _rgba(_PF_COLOR, 0.30), "50% interval"))

#: what each map-producing model is called ON the map surfaces (home and
#: the weekly report label their maps with the model that computed them).
#: These are the shared display names (the marked map in player.js) with
#: "outlook" appended; they are typed here rather than derived because the
#: parse lives in report_season, which imports this module. Keep them in
#: step with that map: the blend is "FluBNF Ensemble" everywhere a human
#: reads it, and only the hub submission identity stays NAU-flavoured.
MODEL_LABEL = {"ensemble": "FluBNF Ensemble outlook",
               "pf": "PF-SIHRS outlook",
               "analogue": "Calendar analogue outlook"}
#: display order for the outlook model toggle: the submitted forecast
#: first, then the members
MODEL_ORDER = ("ensemble", "pf", "analogue")

# Shared embed config: wheel zooms both ways, double-click resets, hover
# modebar offers zoom-out/reset (lasso/box-select/autoscale pruned);
# responsive so figures track their container when it appears or resizes.
PLOTLY_CONFIG = {"scrollZoom": True, "doubleClick": "reset+autosize",
                 "responsive": True,
                 "displayModeBar": "hover", "displaylogo": False,
                 "modeBarButtonsToRemove": ["lasso2d", "select2d",
                                            "autoScale2d"]}

# ---------------------------------------------------------------------------
# Inputs bundle: everything render_bundle needs to rebuild report.html,
# persisted next to it as report_inputs.json. The raw forecast samples
# (10,000 per horizon per state) never enter the bundle; fans are reduced
# to the quantile grid below, which keeps the file around 100 KB while
# still covering every band the fan draws plus room for future band
# choices (the FluSight 23-level grid).
BUNDLE_NAME = "report_inputs.json"
BUNDLE_VERSION = 4
#: every bundle format this builder can render. v2 added one ADDITIVE
#: field, cards_model (which model computed the map cards); a v1 bundle
#: simply lacks it and renders as PF, which is what every v1 run's cards
#: were computed from. v3 added the ADDITIVE cards_by_model and
#: national_map_cards fields (per-model hover cards, all computed by the
#: same quantile-CDF path), which power the outlook model toggle; a v1/v2
#: bundle simply lacks them and renders its one model with no toggle, its
#: label as honest as ever. v4 added the ADDITIVE fitted_fips field (which
#: states the run covered), so the map can tell a verified reporting gap
#: from a state the run never fitted; a v1-v3 bundle lacks it and its
#: card-less states render the neutral 'no data in this view' wording,
#: because the gap claim was never checked for them. Serving code accepts
#: any version listed here.
SUPPORTED_BUNDLE_VERSIONS = (1, 2, 3, 4)
FAN_LEVELS = (0.01, 0.025, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35,
              0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80,
              0.85, 0.90, 0.95, 0.975, 0.99)


def _fig_layout(fig, height=340, title="", legend=False):
    # Chart text on the report's type scale (the report root is a fixed
    # 16px; it has no A-/A/A+ control): ticks and the interval legend at
    # 14px, above the 13.1px hint floor and no longer dwarfed by their
    # plots; the title one step up. automargin lets the tick labels and
    # the below-plot legend size their own margins, so the tight base
    # margins leave no dead band and long labels never clip.
    # a legended figure carries extra height: the horizontal legend band
    # under the axis is paid for by the figure, not taken out of the plot
    fig.update_layout(
        template=None, paper_bgcolor=CARD, plot_bgcolor=CARD,
        font=dict(color=INK, family=FONT_STACK, size=14),
        margin=dict(l=8, r=8, t=42 if title else 12, b=8),
        height=height + (36 if legend else 0),
        title=dict(text=title, font=dict(size=16)),
        # single-line date ticks (no stacked year line): the legend hangs
        # a fraction of the plot area below the axis, and the two-line
        # date band was tall enough to reach it at half-card widths
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
    f = _fig_layout(fig, height=230, title="rate-change outlook (1 wk)")
    f.update_yaxes(tickformat=".0%", range=[0, 1])
    return f


def _html(fig, include_js=False, div_id=None):
    # figures already carry the opaque CARD ground (_fig_layout), so the
    # modebar's save-PNG is readable on its own; the per-figure config adds
    # a 2x export scale and a meaningful filename instead of "newplot"
    config = dict(PLOTLY_CONFIG)
    config["toImageButtonOptions"] = {
        "format": "png", "scale": 2,
        "filename": f"flubnf_{div_id or 'report_figure'}"}
    return fig.to_html(full_html=False,
                       include_plotlyjs=True if include_js else False,
                       div_id=div_id, config=config)


#: the token blocks every report embeds, in cascade order: the light
#: palette (nau.css's first :root block), the fluid type scale (its second
#: :root block), the three named themes, then the two accessibility
#: modifier blocks (which only remap onto per-theme literals, so they
#: compose exactly as they do in the console)
_THEME_SELECTORS = (":root", '[data-theme="dark"]', '[data-theme="paper"]',
                    '[data-theme="dim"]', '[data-contrast="high"]',
                    '[data-vision="cvd"]')


def theme_token_css() -> str:
    """The console's tokens, verbatim from nau.css: the four theme blocks,
    the fluid type scale, and the high-contrast and color-vision modifier
    blocks.

    One source: page_style embeds this, so a token changed in nau.css
    lands in every rebuilt report (builder_sources_mtime counts nau.css,
    and the season builder counts it as an input too). BOTH :root blocks
    are taken since the 2026-08-22 consistency pass -- the color palette
    and the --fs-* type scale -- and every block is emitted in nau.css
    document order, so the cascade (the type block before the modifier
    blocks, which retarget --focus-w) behaves exactly as it does in the
    console. The print block in page_style sits after all of these, so at
    equal specificity it wins the cascade and print stays light in every
    theme."""
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
    """First-paint theme resolution, mirroring the console's base.html.

    Served same-origin (http/https), the report reads the SAME
    localStorage keys the console writes (theme, contrast, vision), so it
    opens in the reader's current console preferences. Opened as a
    standalone file (file://, where that storage is absent or belongs to
    no app), it falls back to the OS preferences: prefers-color-scheme
    for the theme and prefers-contrast for the contrast modifier. Print
    is unaffected: the print block outranks every theme block."""
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
    """Serve-time chart theming: re-resolve the baked figure palette.

    The figures are built with the dark-kit literals (module constants
    above); this script, run after the boot script resolved the theme and
    every figure initialized, reads the SAME tokens the page chrome wears
    (getComputedStyle at draw time, never a baked guess) and rewrites each
    plot's matching colors, Plotly.react-ing the graph. The category bar
    colors re-resolve through the --cat-* tokens and the semantic pair
    through --ok/--bad, so the color-vision modifier reaches every
    chart-internal category and ok/bad encoding exactly as it reaches the
    map; the accent line resolves through --gold, which is the readable
    accent-ink variant of the same cyan on light grounds. Member line
    colors are DELIBERATELY absent from this map: the shared member
    palette is dichromat-spaced by construction (player.js MODEL_COLORS),
    so the CV-safe mode must not move them.

    Each plot's baked figure is snapshotted once before the first tint,
    and the pass re-runs from that snapshot on any later themechange
    event, so a host that flips tokens live retints correctly in both
    directions (a standalone open never fires the event and simply keeps
    the boot-resolved tint). On the dark theme, with no prior tint, every
    replacement is identity and the plots are left untouched."""
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
    national_map_html: pre-rendered usmap.national_svg(...) output; when given,
    a 'state view' / 'national view' toggle appears above the map.
    elapsed_s: this run's wall time in seconds; when given, the footer states
    it. Omitted rather than guessed when the caller does not know.
    settings_html: the run-settings block (app.core.runs.settings_html),
    rendered beside the wall-time line so the report states exactly what
    produced it. Omitted when the caller does not supply it.
    model_label: which model computed the MAP's cards, as shown to the
    reader (see MODEL_LABEL); defaults to the PF label, which is what
    every card set predating the label was computed from.
    cards_by_model: OPTIONAL per-model hover cards (model -> abbr -> card,
    the v3 bundle's cards_by_model), all computed by the same quantile-CDF
    path; with two or more models an aria-pressed model toggle appears
    above the map and swaps the fills, hovers, and label client-side.
    national_map_cards: the per-model national cards riding with it.
    cards_model: which model the map was RENDERED with (the toggle's
    default); label and toggle stay honest for bundles that lack the
    per-model cards, which simply render their one model, no toggle.
    fitted_fips: the fips the producing RUN actually fitted (iterable), or
    None when the bundle never recorded it. This gates every no-data claim
    on the map: a card-less state inside the scope is a verified reporting
    gap, one outside it is 'not fitted in this run', and with no recorded
    scope the map and caption claim only 'no data', because the old
    unconditional 'reporting gap' wording labeled 51 unfitted states as
    reporting gaps on a one-state run (review finding 2026-08)."""
    # Build-time SVG map (see usmap.py) -- the plotly geo choropleth fetched
    # its geometry from cdn.plot.ly at runtime and rendered empty offline/CSP.
    from app.core import usmap
    from app.core.usmap import cat_fill, svg_map
    cards_by_fips = {c["fips"]: c for c in state_cards.values() if "fips" in c}
    # the run's coverage, when the bundle recorded it: card-less states are
    # split into verified reporting gaps (in scope) and 'not fitted in this
    # run' (out of scope); with no record the map claims only 'no data'
    scope = set(fitted_fips) if fitted_fips is not None else None
    no_card = set(usmap.state_paths()) - set(cards_by_fips)
    gap_states = (no_card & scope) if scope is not None else set()
    unfitted_states = (no_card - scope) if scope is not None else set()
    # only states that actually have a detail section invite a click
    map_html = svg_map(cards_by_fips, clickable=set(state_details),
                       scope_fips=scope)
    # legend and caption say only what the scope record supports; each
    # no-data flavor appears exactly when a state on the map wears it, and
    # the old unconditional 'reporting gap' sentence is never asserted for
    # states nobody checked
    _sw = f'<i class="sw" style="background:{NO_DATA}"></i>'
    legend_bits, caption_bits = [], []
    if scope is None:
        if no_card:
            legend_bits.append(f"<span>{_sw}no data in this view</span>")
            caption_bits.append(
                " States in the no-data shade have no data in this "
                "report's stored inputs; whether they were fitted was not "
                "recorded, so nothing more is claimed.")
    else:
        if gap_states:
            legend_bits.append(f"<span>{_sw}no data (reporting gap)</span>")
            caption_bits.append(
                " States in the no-data shade were fitted in this run but "
                "reported nothing this week: shown as gaps, never "
                "interpolated.")
        if unfitted_states:
            legend_bits.append(f"<span>{_sw}not fitted in this run</span>")
            caption_bits.append(
                " States marked not fitted were outside this run's "
                "scope; nothing is claimed about their reporting.")
    no_data_legend = "".join(legend_bits)
    no_data_caption = "".join(caption_bits)
    model_label = model_label or MODEL_LABEL["pf"]
    # the outlook model toggle (v3 bundles): rendered only when the bundle
    # actually carries SWAPPABLE cards (probs-bearing, fips-keyed -- the
    # same bar the home outlook's _outlook_models applies) for two or more
    # models; a model whose cards hold no data would render an inert
    # button, so it is dropped here and the emitter guards again
    model_toggle_html = ""
    cbm = {m: c for m, c in (cards_by_model or {}).items()
           if any(isinstance(v, dict) and v.get("fips") and v.get("probs")
                  for v in (c or {}).values())}
    if len(cbm) >= 2:
        order = [m for m in MODEL_ORDER if m in cbm] \
            + [m for m in cbm if m not in MODEL_ORDER]
        default = cards_model if cards_model in cbm else order[0]
        payload = {}
        for m in order:
            byf = {c["fips"]: c for c in cbm[m].values()
                   if isinstance(c, dict) and c.get("fips")}
            payload[m] = {
                # scope rides along so the toggle's rewritten hovers tell
                # the same story as the server-rendered map (usmap contract)
                "states": usmap.state_swap_payload(byf, scope_fips=scope),
                "us": usmap.nat_swap_payload(
                    (national_map_cards or {}).get(m) or {})}
        model_toggle_html = usmap.model_toggle(
            order, MODEL_LABEL, default, payload,
            group_id="outlook-model", btn_class="", active_class="on",
            wrap_class="viewtoggle")

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

    # emit each national chart card only when its figure exists -- two empty
    # bordered boxes say less than one honest hint line
    nat_cards = []
    if national.get("fan"):
        nat_cards.append(f'<div class="card">{_html(national["fan"])}</div>')
    nat_body = "\n  ".join(nat_cards) or (
        '<p class="hint">National fan and accuracy charts appear once the '
        'national model run lands.</p>')
    # the console run fits the national series directly (it appends the US
    # location to every run), so WHEN THIS SECTION CARRIES A FORECAST it is
    # a FITTED national one, never the retrospective's constructed
    # sum-of-states fallback. It says so, in the shared wording, so a reader
    # holding this artifact beside a season report cannot mistake one for
    # the other.
    #
    # The claim is DERIVED from the run, never hardcoded. A report built
    # before the national run lands carries no national output at all, and
    # an unconditional provenance line printed "fitted" directly above
    # nat_body's placeholder saying the national run had not landed: two
    # contradictory sentences in one section, with the absent half reading
    # as a fit. That is exactly the fallback-as-fit failure this module's
    # wording exists to prevent, so the line is gated.
    #
    # The signal is nat_cards, and ONLY nat_cards -- the national fan IS the
    # national model output. summary_html is not evidence: the run bundle
    # fills it unconditionally with the accuracy card (app/ui/server.py
    # builds it from summary_table_html, which returns its own placeholder
    # for an unscored run), so gating on it would assert a fitted national
    # forecast on every report ever built. A national figure reached through
    # that table carries its own provenance label from scoring.py in any
    # case, so the worst this gate can do is stay silent.
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

    # plotly.js goes in the head, once, iff any figure is embedded: a chart
    # must never render without its library, and a chartless report should
    # not carry the payload.
    if state_details or national.get("fan"):
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
{theme_boot_script()}
{plotly_js}
{page_style()}</head><body><main>
{page_header()}
<h1>US influenza forecast</h1>
<p class="sub">week of {reference_date} ·
 <span data-mapmodel-label>{model_label}</span> · click a state for
 detail · Ctrl+scroll to zoom (⌘ on Mac), drag to pan, double-click to reset
 · <button id="natbtn">national detail</button></p>
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
  <span>deeper shade = more confident</span>
 </div>
</div>
<p class="hint">Hover a state for its full outlook.{no_data_caption}</p>
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
    # atomic: a reader mid-refresh (the stale-report rebuild on serve)
    # never sees a half-write, and a failed build leaves the stored file
    tmp = out_path.with_name(out_path.name + ".tmp")
    # newline pinned. report.html is delivered two ways -- /output/report
    # reads it as text (universal newlines, so \r\n collapses to \n) and
    # /output/report/download hands the raw file over untouched -- and the
    # contract those two routes share is that they are the same bytes. A
    # plain write_text takes newline=None, which on Windows writes \r\n, so
    # the page and the saved file stopped agreeing there and nowhere else.
    # The Windows CI job caught it in test_report_bundle, as the download
    # and the inline view returning different text for the same report. LF
    # here keeps one report, two deliveries, on every platform.
    tmp.write_text(html, newline="\n")
    os.replace(tmp, out_path)
    return out_path


def save_bundle(bundle: dict, dirpath: Path) -> Path:
    """Persist the report's inputs bundle next to report.html, atomically.

    The bundle carries everything render_bundle needs (fans already reduced
    to their quantile grid, never the raw samples), so the stored report can
    be rebuilt after any builder change without rerunning the models."""
    p = Path(dirpath) / BUNDLE_NAME
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(bundle, separators=(",", ":"), default=float))
    os.replace(tmp, p)
    return p


def render_bundle(bundle: dict, out_path: Path) -> Path:
    """Render the weekly report from its pure-data inputs bundle.

    The one render path: the live run (server step 5b) and the stale-report
    refresh on /output/report both come through here, so rebuilding a
    stored bundle reproduces exactly what a fresh run would render with the
    current builder code, fans and map included."""
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
    # the additive v2 field: which model computed the map cards. A v1
    # bundle lacks it and renders as PF, which its cards were computed from.
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
        # the additive v3 fields: per-model cards for the outlook model
        # toggle. A v1/v2 bundle lacks them and renders its one model with
        # no toggle, exactly as before.
        cards_by_model=bundle.get("cards_by_model") or {},
        national_map_cards=bundle.get("national_map_cards") or {},
        cards_model=cards_model,
        # the additive v4 field: which fips the run fitted. Bundles from
        # before it exist pass None, and the map then claims only 'no
        # data' for card-less states, never a reporting gap nobody checked.
        fitted_fips=bundle.get("fitted_fips"))


def builder_sources_mtime() -> float:
    """Newest mtime of the weekly report's builder sources: this module,
    the scoring module (the embedded WIS summary card), the map renderer,
    and the console stylesheet (the report embeds its token blocks, so a
    theme change is a design change). The report_season freshness pattern
    applied to the weekly report: a stored report.html older than this was
    built by an earlier design and is stale."""
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
    import re
    return set(re.findall(r"\.([A-Za-z_][A-Za-z0-9_-]*)", css))


def legacy_theme_carry(html: str) -> str:
    """Serve-time refresh for a stored report that predates the inputs
    bundle.

    Such a report cannot be rebuilt honestly: results.json keeps five
    quantile levels per horizon, no samples, and no categorical
    probabilities, so the 95 percent bands and the map's category shading
    would have to be invented. Instead this swaps in the current stylesheet
    and header lockup, but only when every class the old stylesheet styled
    and the body still uses is also styled by the current stylesheet (the
    compatibility check the swap rests on). A carried page with embedded
    charts also gains the retint pass, so its chart colors re-resolve
    against the carried tokens at open: the rate-change bars follow the
    color-vision mode through --cat-* exactly as a current report's do,
    since the old builds baked the same category literals. Colors the map
    does not recognize keep the palette they were built with, and one
    quiet line says so. When the swap cannot be proven safe, only the
    quiet line is added. The transform is applied to the served page only;
    the stored file is never modified. Returns the input unchanged on any
    surprise."""
    import re
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
                    # a carried page with embedded charts gains the retint
                    # pass: the tokens it resolves arrived with the swapped
                    # stylesheet, so the category bars follow the reader's
                    # theme and color-vision mode (unmatched legacy colors
                    # resolve to themselves and stay untouched)
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
