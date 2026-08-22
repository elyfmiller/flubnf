"""The season-line palette: two palettes at the token layer.

User-verified report 2026-08-21: the season-over-season charts wore the
colorblind-safe palette for everyone, so color-vision mode looked ON by
default and the CV safe toggle visibly moved nothing. The design now is
TWO palettes as CSS tokens (nau.css):

  * --season-1..6 -- the normal-vision default, a tab10-adjacent set
    fitted to the brand bar (3:1+ against all eight theme grounds);
  * --season-cvd-1..6 -- the red-green-safe set (the audited SEASON_COLORS
    literals in player.js), which data-vision="cvd" remaps --season-N onto.

Charts resolve --season-N per draw via getComputedStyle and redraw on
themechange, so the toggle visibly swaps the whole set; SEASON_COLORS
stays the fallback where the tokens are absent (the fixed-dark report),
keeping that fallback the safe set. Seasons are colored newest-first (the
newest non-gold season always takes index 0), so the pair drawn beside
the gold latest-season line is exactly the audited one. These tests pin
the construction of both sets, the token wiring, the fresh-profile
default (normal vision), and the documentation, and audit the other
multi-series charts for red/green reliance.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

from app.core import report_v2                      # noqa: E402
from app.ui import server as srv                    # noqa: E402

client = TestClient(srv.app)

UI = Path(__file__).resolve().parents[1] / "ui"
NAU = (UI / "static" / "nau.css").read_text()
PLAYER = (UI / "static" / "player.js").read_text()
BASE_T = (UI / "templates" / "base.html").read_text()
FORECAST_T = (UI / "templates" / "forecast.html").read_text()
MODEL_T = (UI / "templates" / "model.html").read_text()

#: the eight theme grounds (bg and card of light, paper, dim, dark), the
#: same bar the member-palette audit holds (test_a11y_modes)
GROUNDS = ("#F1EFF7", "#FFFFFF", "#F7F2E5", "#FDFAF1",
           "#212536", "#2A2F45", "#0C0D17", "#151729")
#: both --gold variants the latest season's line can wear: the cyan on
#: dark grounds and the accent-ink teal on light grounds
GOLD = ("#34C0F0", "#0173A9")

# Vienot (1999) dichromacy simulation in linearized sRGB (the same
# matrices the member-palette audit uses)
_DEUTAN = ((0.625, 0.375, 0.0), (0.7, 0.3, 0.0), (0.0, 0.3, 0.7))
_PROTAN = ((0.567, 0.433, 0.0), (0.558, 0.442, 0.0), (0.0, 0.242, 0.758))
_IDENT = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


def _lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _unlin(c):
    c = max(0.0, min(1.0, c))
    return round((12.92 * c if c <= 0.0031308
                  else 1.055 * c ** (1 / 2.4) - 0.055) * 255)


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(h):
    r, g, b = _rgb(h)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _cr(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _sim(h, M):
    r, g, b = (_lin(c) for c in _rgb(h))
    return tuple(_unlin(M[i][0] * r + M[i][1] * g + M[i][2] * b)
                 for i in range(3))


def _dist(a, b, M):
    pa, pb = _sim(a, M), _sim(b, M)
    return sum((x - y) ** 2 for x, y in zip(pa, pb)) ** 0.5


def _tokens(block_css: str, prefix: str) -> list:
    """--<prefix>-1..N from one token block's text, in index order."""
    found = dict(re.findall(r"--" + prefix + r"-(\d)\s*:\s*(#[0-9A-Fa-f]{6})",
                            block_css))
    return [found[str(i)] for i in sorted(map(int, found))]


def _block(selector: str) -> str:
    m = re.search(re.escape(selector) + r"\{([^}]*)\}", NAU)
    assert m, f"missing block {selector}"
    return m.group(1)


NORMAL = _tokens(_block(":root"), "season")
CVD = _tokens(_block(":root"), "season-cvd")


# -------------------------------------------------- the two token palettes

def test_both_palettes_live_in_every_theme_block():
    """Six normal + six cvd literals, identical in all four theme blocks
    (the --cat-* pattern: categorical tokens join the parity contract)."""
    assert len(NORMAL) == 6 and len(CVD) == 6
    assert NORMAL != CVD
    for sel in (':root', '[data-theme="dark"]', '[data-theme="paper"]',
                '[data-theme="dim"]'):
        b = _block(sel)
        assert _tokens(b, "season") == NORMAL, sel
        assert _tokens(b, "season-cvd") == CVD, sel


def test_cvd_mode_remaps_the_season_tokens():
    m = re.search(r'\[data-vision="cvd"\]\{([^}]*)\}', NAU)
    assert m
    for i in range(1, 7):
        assert f"--season-{i}:var(--season-cvd-{i})" in \
            " ".join(m.group(1).split()).replace("; ", ";")


def test_normal_palette_is_distinct_and_holds_3_to_1_on_all_grounds():
    """The normal-vision default: every color 3:1+ on all eight theme
    grounds, adjacent pairs (and the first color against both golds)
    clearly separable in normal vision."""
    for c in NORMAL:
        for g in GROUNDS:
            assert _cr(c, g) >= 3.0, (c, g, _cr(c, g))
    pairs = [(NORMAL[i], NORMAL[(i + 1) % 6]) for i in range(6)]
    pairs += [(g, NORMAL[0]) for g in GOLD]
    for a, b in pairs:
        assert _dist(a, b, _IDENT) >= 60, (a, b, _dist(a, b, _IDENT))


def test_cvd_palette_keeps_60_separability_in_every_vision_mode():
    """The red-green-safe set keeps the original construction: every pair
    a reader can see side by side (cyclically adjacent colors, and the
    first color against both gold variants) measures 60+ under both
    Vienot matrices AND in normal vision, and every color holds 3:1 on
    all eight grounds."""
    pairs = [(CVD[i], CVD[(i + 1) % 6]) for i in range(6)]
    pairs += [(g, CVD[0]) for g in GOLD]
    for a, b in pairs:
        for M in (_DEUTAN, _PROTAN, _IDENT):
            assert _dist(a, b, M) >= 60, (a, b, M, _dist(a, b, M))
    for c in CVD:
        for g in GROUNDS:
            assert _cr(c, g) >= 3.0, (c, g, _cr(c, g))


# ------------------------------------------------------- the one source

def test_player_literals_are_the_cvd_set_and_python_reads_them():
    """SEASON_COLORS in player.js (the fallback for token-less surfaces)
    equals the --season-cvd-* literals, so a surface without the
    stylesheet still wears the audited safe set; report_v2.season_colors
    hands the same values to every Python surface."""
    pal = report_v2.season_colors()
    assert pal == CVD
    m = re.search(r"/\*SEASON_COLORS_JSON\*/\s*(\[.*?\])"
                  r"\s*/\*END_SEASON_COLORS_JSON\*/", PLAYER, re.S)
    assert m, "player.js lost its SEASON_COLORS marked JSON"
    import json
    assert json.loads(m.group(1)) == pal
    assert report_v2._SEASON_COLOR_FALLBACK == pal
    # the gold variants this audit assumes are the tokens that ship
    assert re.search(r":root\{[^}]*--gold:#0173A9", NAU)
    assert re.search(r'\[data-theme="dark"\]\{[^}]*--gold:#34C0F0', NAU)


# ------------------------------------------- fresh profile: normal vision

def test_fresh_profile_renders_normal_palettes():
    """No stored preferences: the served page carries no data-vision
    attribute, the boot script enables cvd ONLY from an explicit stored
    choice, and bare :root resolves --season-N to the normal literals
    (the cvd literals live behind the data-vision remap). The outlook
    map's category fills ride the same rule: --cat-* holds the normal
    scale at :root and swaps only under the modifier."""
    html = client.get("/").text
    assert 'data-vision="cvd"' not in html.split("<script>")[0]
    assert "localStorage.getItem('vision')==='cvd'" in BASE_T
    # no OS media query force-enables cvd (contrast has one; vision does
    # not -- there is no such preference signal to follow)
    boot = BASE_T.split("</script>", 1)[0]
    assert "vision" in boot
    assert "prefers-contrast" in boot          # contrast follows the OS
    v_line = [l for l in boot.splitlines() if "vision" in l]
    assert all("matchMedia" not in l for l in v_line)
    # bare :root states the NORMAL season literals on --season-N
    assert NORMAL[0] in _block(":root")
    root = " ".join(_block(":root").split())
    for i, c in enumerate(NORMAL, 1):
        assert f"--season-{i}:{c}" in root
    # and the normal map scale on --cat-* (green/red language by default)
    assert "--cat-large-decrease:#2e7d4f" in root
    assert "--cat-cvd-large-decrease:#2C7BB6" in root
    m = re.search(r'\[data-vision="cvd"\]\{([^}]*)\}', NAU)
    assert "--cat-large-decrease:var(--cat-cvd-large-decrease)" in \
        " ".join(m.group(1).split())


# --------------------------------------------------------------- wiring

def test_forecast_season_chart_resolves_the_tokens_newest_first():
    # the fallback list still arrives from the server (the shared player
    # literal via report_v2.season_colors), never a template-private list
    assert "const SCOLORS = {{ season_colors_json | safe }}" in FORECAST_T
    # colors resolve from the tokens per draw, falling back to SCOLORS
    assert "css('--season-' + ((i % SCOLORS.length) + 1))" in FORECAST_T
    assert "|| SCOLORS[i % SCOLORS.length]" in FORECAST_T
    # newest-first assignment: the season before the gold one is index 0
    assert "seasonColor(seasons.length-2-i)" in FORECAST_T
    # the latest season keeps the gold accent, falling back to the shared
    # member map (no private literal)
    assert "css('--gold')||MCOLORS.analogue" in FORECAST_T
    # the CV-safe toggle reaches the chart: themechange redraws it
    assert "addEventListener('themechange',()=>{drawData(CURMODE)" in FORECAST_T
    # the plotly default colorway is out: no trace leaves color undefined
    assert "color:undefined" not in FORECAST_T.replace(" ", "")
    # served page carries the audited fallback values
    html = client.get("/forecast").text
    for c in report_v2.season_colors():
        assert c in html, c


def test_player_exposes_the_token_resolver():
    """The shared player core carries the one resolver (token first,
    SEASON_COLORS fallback), so any surface drawing season lines through
    it follows the color-vision mode for free."""
    assert "function seasonColor(i)" in PLAYER
    assert "getPropertyValue('--season-' + (k + 1))" in PLAYER
    assert "seasonColor: seasonColor" in PLAYER


# -------------------------------------------------------- documentation

def test_the_palette_contract_is_documented_for_the_next_person():
    # the player states, at the definition, that the literals are the cvd
    # set, that the tokens carry the normal default, and where the audit
    # lives
    block = PLAYER.split("var SEASON_COLORS")[0].rsplit("// THE", 1)[1]
    assert "RED-GREEN-SAFE set" in block
    assert "--season-1..6" in block
    assert "test_season_palette" in block
    # the member map keeps its own static-safe note: the toggle still
    # deliberately does not move member lines
    mblock = PLAYER.split("var MODEL_COLORS")[0]
    assert "NOT swap these member colors" in mblock.replace("\n// ", " ")
    # nau.css tells the next person, AT the cvd block, exactly which chart
    # palettes the toggle does and does not move
    assert "WHAT THE CV-SAFE TOGGLE DOES AND DOES NOT MOVE" in NAU
    assert "MODEL_COLORS" in NAU and "SEASON_COLORS" in NAU
    assert "test_season_palette.py" in NAU
    assert "--season-cvd-1..6" in NAU or "--season-cvd-" in NAU


# ------------------------------- audit: the other multi-series charts

def test_no_other_multi_series_chart_relies_on_a_red_green_pair():
    """The sweep the palette fix came from: member overlays ride the
    dichromat-spaced MODEL_COLORS (audited in test_a11y_modes); observed
    vs settled differ by dash on the same ink, never by hue; the official
    comparators wear neutral greys or the muted token. No chart series
    color comes from plotly's default colorway."""
    # observed vs settled: same ink, dash carries the distinction
    for src, settled in ((FORECAST_T, "settled outcome"),
                         (MODEL_T, "settled outcome")):
        seg = src.split(settled, 1)[1][:120]
        assert "css('--ink')" in seg and "dash:'dot'" in seg, settled
    assert "name: 'truth (settled)', line: {color: p.ink" in PLAYER
    assert "line: {color: p.ink, width: 1.3, dash: 'dot'}" in PLAYER
    # officials: neutral grey literals or the muted token, never red/green
    assert "flusightEnsemble: '#C7CCDD'" in PLAYER
    assert "flusightEnsemble: '#AAB1C9'" in \
        (UI / "templates" / "retro_season.html").read_text()
    assert "return (p.models || {})[m] || p.mut;" in PLAYER
    # no default-colorway reliance anywhere a series gets its color
    for src in (PLAYER, FORECAST_T, MODEL_T):
        assert "color:undefined" not in src.replace(" ", "")
    # no red/green literal pair in any chart source (the map's category
    # scale lives in tokens and follows the CV-safe toggle; the ok/bad
    # pair rides --ok/--bad)
    for bad_hex in ("#2ca02c", "#d62728"):
        for src in (PLAYER, FORECAST_T, MODEL_T):
            assert bad_hex not in src.lower(), bad_hex
