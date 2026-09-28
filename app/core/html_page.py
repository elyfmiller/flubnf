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
  4. the UI kit inlined (the weekly report): kit_css, kit_js, kit_macros,
     font_face_css, logo_css
"""
from __future__ import annotations

import base64
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
#: the UI kit (docs/UI-KIT.md): its sheet, its behavior and its macros
KIT_CSS = STATIC / "ui-kit.css"
KIT_JS = STATIC / "tips.js"
TIPS_TPL = STATIC.parent / "templates" / "_tips.html"
#: the self-hosted DM Sans faces and the per-theme header marks
FONTS_CSS = STATIC / "fonts" / "dm-sans.css"
LOGOS_CSS = STATIC / "brand" / "logos.css"
# DM Sans (inlined where a page embeds font_face_css), system fallback: no
# webfont fetch
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
#: the console's themes, as base.html's THEMES lists them (light is :root)
THEMES = ("light", "paper", "github", "solarized",
          "dim", "dark", "nord", "dracula")
#: the embedded token blocks: both :root blocks (palette, type scale), the
#: named themes and the two accessibility modifiers
_THEME_SELECTORS = ((":root",)
                    + tuple(f'[data-theme="{t}"]' for t in THEMES
                            if t != "light")
                    + ('[data-contrast="high"]', '[data-vision="cvd"]'))


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
    localStorage keys (theme, the two a11y modes, the text size) when
    served same-origin, else the OS preferences and the standard size."""
    names = ",".join(f"'{t}'" for t in THEMES)
    return """<script>
(function(){var de=document.documentElement,t=null,c=null,v=null,f=null;
 try{if(location.protocol==='http:'||location.protocol==='https:'){
  t=localStorage.getItem('theme');c=localStorage.getItem('contrast');
  v=localStorage.getItem('vision');f=localStorage.getItem('fontsize');}}
 catch(e){}
 if([""" + names + """].indexOf(t)<0)
  t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';
 if(c!=='high'&&c!=='normal')
  c=matchMedia('(prefers-contrast: more)').matches?'high':'normal';
 de.setAttribute('data-theme',t);
 if(c==='high')de.setAttribute('data-contrast','high');
 if(v==='cvd')de.setAttribute('data-vision','cvd');
 var p={s:87.5,m:100,l:115}[f]||parseFloat(f);
 if(p>=80&&p<=160&&p!==100)de.style.fontSize=p+'%';})();
</script>"""


# ------------------------------------------------------ 4. the kit, inlined
#: the first and last of nau.css's "?" explainer rules (the kit's tip,
#: which ui-kit.css builds on)
_TIP_RULES = (".lblrow{", ("@media (prefers-reduced-motion:reduce)"
              "{.tipbox{transition:none}}"))


def kit_css() -> str:
    """The UI kit's styles for a standalone page: nau.css's tip rules
    verbatim, then ui-kit.css verbatim. Both read only the token blocks
    (theme_token_css), so the page embeds those too."""
    css = NAU_CSS.read_text(encoding="utf-8")
    a = css.index(_TIP_RULES[0])
    b = css.index(_TIP_RULES[1], a) + len(_TIP_RULES[1])
    return css[a:b] + "\n" + KIT_CSS.read_text(encoding="utf-8")


def kit_js() -> str:
    """tips.js verbatim: the tips' and toggletips' behavior (FluBNFUI)."""
    return KIT_JS.read_text(encoding="utf-8")


_KIT = None


def kit_macros():
    """The kit's Jinja macros (templates/_tips.html) for Python callers,
    e.g. kit_macros().badge("ok", "fitted"). Autoescaped as in the console,
    so tip text that carries markup is passed as markupsafe.Markup."""
    global _KIT
    if _KIT is None:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(str(TIPS_TPL.parent)),
                          autoescape=True)
        _KIT = env.get_template(TIPS_TPL.name).module
    return _KIT


def _data_uri(path: Path, mime: str) -> str:
    return (f"data:{mime};base64,"
            + base64.b64encode(path.read_bytes()).decode("ascii"))


def font_face_css() -> str:
    """dm-sans.css's latin faces with their files inlined (data: URIs), so
    a standalone page wears the console's face offline. The latin-ext faces
    stay out (the system fallback covers them), keeping the page small."""
    out = []
    for block in re.findall(r"/\* latin \*/\s*(@font-face\s*\{[^}]*\})",
                            FONTS_CSS.read_text(encoding="utf-8")):
        m = re.search(r"url\(/static/fonts/([\w.-]+)\)", block)
        f = FONTS_CSS.parent / m.group(1) if m else None
        if f is not None and f.is_file():
            out.append(block.replace(
                m.group(0), f"url({_data_uri(f, 'font/woff2')})"))
    return "\n".join(out)


def logo_css() -> str:
    """logos.css (the header mark per theme, --logo) with each mark
    inlined, for a standalone page. A theme whose file is missing gets no
    line (the page's own fallback mark shows)."""
    out = []
    for sel, rel in re.findall(
            r'^(.+?)\{--logo:url\("/static/([^"]+)"\)\}',
            LOGOS_CSS.read_text(encoding="utf-8"), re.MULTILINE):
        f = STATIC / rel
        if f.is_file():
            out.append(f'{sel}{{--logo:url("{_data_uri(f, "image/svg+xml")}")}}')
    return "\n".join(out)
