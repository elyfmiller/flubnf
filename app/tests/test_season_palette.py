"""The season-line palette: colorblind-safe by construction.

The season-over-season data chart draws one line per season. It used to
color them with plotly's default colorway, which contains a green and a red
the CV-safe toggle does not reach (the toggle remaps only the semantic
ok/bad pair and the map's category scale). The fix is a palette that needs
no toggle: SEASON_COLORS in the shared player core (player.js, marked JSON,
parsed by report_v2.season_colors), spaced so that every pair a reader can
see side by side is separable in normal vision AND under both Vienot
dichromacy matrices, and readable against every theme ground. Seasons are
colored newest-first (the newest non-gold season always takes index 0), so
the pair drawn beside the gold latest-season line is exactly the audited
one. These tests pin the construction, the wiring, and the documentation,
and audit the other multi-series charts for red/green reliance.
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


# ------------------------------------------------------- the one source

def test_palette_reads_from_the_one_shared_source():
    pal = report_v2.season_colors()
    assert len(pal) == 6
    for c in pal:
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", c), c
    # the marked JSON lives in the player core (the MODEL_COLORS contract)
    m = re.search(r"/\*SEASON_COLORS_JSON\*/\s*(\[.*?\])"
                  r"\s*/\*END_SEASON_COLORS_JSON\*/", PLAYER, re.S)
    assert m, "player.js lost its SEASON_COLORS marked JSON"
    import json
    assert json.loads(m.group(1)) == pal
    # the Python fallback equals the shipped list, so a broken parse
    # degrades to the same audited palette
    assert report_v2._SEASON_COLOR_FALLBACK == pal
    # the gold variants this audit assumes are the tokens that ship
    assert re.search(r":root\{[^}]*--gold:#0173A9", NAU)
    assert re.search(r'\[data-theme="dark"\]\{[^}]*--gold:#34C0F0', NAU)


# ------------------------------------------- safe by construction: pairs

def test_adjacent_pairs_hold_60_in_every_vision_mode():
    """Every pair a reader can see side by side: cyclically adjacent
    palette colors (seasons can outnumber colors), and the first color
    against both gold variants (the newest season's line is always drawn
    beside SCOLORS[0], by the newest-first assignment)."""
    pal = report_v2.season_colors()
    pairs = [(pal[i], pal[(i + 1) % len(pal)]) for i in range(len(pal))]
    pairs += [(g, pal[0]) for g in GOLD]
    for a, b in pairs:
        for M in (_DEUTAN, _PROTAN, _IDENT):
            assert _dist(a, b, M) >= 60, (a, b, M, _dist(a, b, M))


def test_every_color_holds_3_to_1_on_all_theme_grounds():
    for c in report_v2.season_colors():
        for g in GROUNDS:
            assert _cr(c, g) >= 3.0, (c, g, _cr(c, g))


# --------------------------------------------------------------- wiring

def test_forecast_season_chart_uses_the_palette_newest_first():
    # the palette arrives from the server (the shared player literal via
    # report_v2.season_colors), never a template-private list
    assert "const SCOLORS = {{ season_colors_json | safe }}" in FORECAST_T
    # newest-first assignment: the season before the gold one is SCOLORS[0]
    assert "SCOLORS[(seasons.length-2-i)%SCOLORS.length]" in FORECAST_T
    # the latest season keeps the gold accent, falling back to the shared
    # member map (no private literal)
    assert "css('--gold')||MCOLORS.analogue" in FORECAST_T
    # the plotly default colorway is out: no trace leaves color undefined
    assert "color:undefined" not in FORECAST_T.replace(" ", "")
    # served page carries the audited values
    html = client.get("/forecast").text
    for c in report_v2.season_colors():
        assert c in html, c


# -------------------------------------------------------- documentation

def test_static_safe_palettes_are_documented_for_the_next_person():
    # the palette states, at its definition, that the CV-safe toggle
    # deliberately does not move it and where the audit lives
    block = PLAYER.split("var SEASON_COLORS")[0].rsplit("// THE one", 1)[1]
    assert "STATIC-SAFE BY CONSTRUCTION" in block
    assert "deliberately does NOT remap" in block
    assert "test_season_palette" in block
    # the member map keeps its own equivalent note
    mblock = PLAYER.split("var MODEL_COLORS")[0]
    assert "does\n// NOT swap these member colors" in mblock \
        or "NOT swap these member colors" in mblock.replace("\n// ", " ")
    # nau.css tells the next person, AT the cvd block, exactly which chart
    # palettes the toggle does and does not move
    assert "WHAT THE CV-SAFE TOGGLE DOES AND DOES NOT MOVE" in NAU
    assert "MODEL_COLORS" in NAU and "SEASON_COLORS" in NAU
    assert "test_season_palette.py" in NAU


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
