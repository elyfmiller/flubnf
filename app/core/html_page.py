"""PRODUCTION: what the self-contained HTML pages share (report_v2,
report_season, site_page, site_build).

The console's static assets as the exports read them (nau.css token blocks,
player.js's marked JSON maps, charts.js), the first-paint theme boot script,
the plotly.js getter and the one HTML escape. Each page keeps its OWN
stylesheet: the two reports restate the console's run-settings grid in
their own source (a test holds them to it), and the site has its own tokens.

  1. asset paths and FONT_STACK
  2. text helpers: esc, charts_js, plotly_js, marked_json
  3. theme: theme_token_css, theme_boot_script
"""
from __future__ import annotations

import copy
import html
import json
import re
from pathlib import Path

# ---------------------------------------------------------- 1. the assets
STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"
#: the one source of the embedded theme tokens, hence a builder input
NAU_CSS = STATIC / "nau.css"
#: the shared player core carries the marked JSON maps (names, colours)
PLAYER_SRC = STATIC / "player.js"
#: the one date-axis tick policy and chart config (FluCharts), inlined into
#: both reports so their charts tick on the data's Saturdays like the console
CHARTS_SRC = STATIC / "charts.js"
# DM Sans where installed, system fallback: no webfont fetch
FONT_STACK = '"DM Sans",system-ui,-apple-system,"Segoe UI",sans-serif'


# ---------------------------------------------------------- 2. text helpers
def esc(s) -> str:
    return html.escape(str(s))


def charts_js() -> str:
    """charts.js verbatim (FluCharts), for inlining into a report."""
    return CHARTS_SRC.read_text(encoding="utf-8")


def plotly_js() -> str:
    """plotly.js from the installed wheel, for inlining (no network)."""
    from plotly.offline import get_plotlyjs
    return get_plotlyjs()


def marked_json(marker: str, fallback, src: Path = PLAYER_SRC):
    """The JSON literal player.js wraps in /*MARKER*/ ... /*END_MARKER*/,
    parsed so every Python surface reads the player's own map. A copy of
    `fallback` when the file or the marker cannot be read: never raises."""
    try:
        text = Path(src).read_text(encoding="utf-8")
        m = re.search(rf"/\*{marker}\*/\s*(\{{.*?\}}|\[.*?\])"
                      rf"\s*/\*END_{marker}\*/", text, re.DOTALL)
        return json.loads(m.group(1)) if m else copy.copy(fallback)
    except Exception:
        return copy.copy(fallback)


# ------------------------------------------------------------ 3. the theme
#: the embedded token blocks: both :root blocks (palette, type scale), the
#: named themes and the two accessibility modifiers
_THEME_SELECTORS = (":root", '[data-theme="dark"]', '[data-theme="paper"]',
                    '[data-theme="dim"]', '[data-contrast="high"]',
                    '[data-vision="cvd"]')


def theme_token_css() -> str:
    """nau.css token blocks verbatim, in document order (the cascade
    matters: modifiers retarget type tokens; a page's print block comes
    after and wins)."""
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
