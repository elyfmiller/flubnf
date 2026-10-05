"""The seasonal-harmonic figure and the theme system.

One parameterized macro draws beta(t)/beta0 from the stated
cosine-exponential (computed by a template global) on every surface that
shows the equation. Eight themes (light, paper, github, solarized, dim,
dark, nord, dracula) via the Display menu's picker; every theme block
defines the same token set and holds 4.5:1 for text pairs and 3:1 for
boundaries and fills (every mode: test_display_themes.py).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

from app.ui import server as srv                    # noqa: E402
from app.ui import templating as ui_templating      # noqa: E402

client = TestClient(srv.app)

UI = Path(__file__).resolve().parents[1] / "ui"
NAU = (UI / "static" / "nau.css").read_text()
BASE_T = (UI / "templates" / "base.html").read_text()
DIAGRAMS_T = (UI / "templates" / "diagrams.html").read_text()

ARIA_ONE = 'aria-label="Seasonal harmonic'
ARIA_TWO = 'aria-label="Two-strain seasonal harmonic'


def _macro(**kw):
    return srv.templates.env.get_template("diagrams.html").module.harmonic(**kw)


# ------------------------------------ the figure reaches its four surfaces

def test_harmonic_figure_renders_on_every_surface():
    home = client.get("/")
    assert home.status_code == 200
    assert home.text.count(ARIA_ONE) == 1           # the workflow card
    models = client.get("/models")
    assert models.status_code == 200
    assert models.text.count(ARIA_ONE) == 1         # the PF view's eqpanel
    methods = client.get("/methods")
    assert methods.status_code == 200
    assert methods.text.count(ARIA_ONE) == 1        # the #sihrs card
    assert methods.text.count(ARIA_TWO) == 1        # the #two-strain card
    pf2s = client.get("/model/pf2s")
    assert pf2s.status_code == 200
    assert pf2s.text.count(ARIA_TWO) == 1


def test_every_surface_calls_the_one_macro():
    # one parameterized macro: eq_pf/eq_pf2s embed it (passing their kit
    # mode on), home imports it (in kit mode: its caption in a badge's tip)
    assert "{{ harmonic(kit=kit) }}" in DIAGRAMS_T
    assert "{{ harmonic(two=true, kit=kit) }}" in DIAGRAMS_T
    home_t = (UI / "templates" / "home.html").read_text()
    assert "{{ dg.harmonic(kit=true) }}" in home_t
    assert DIAGRAMS_T.count("{% macro harmonic(") == 1


# --------------------------------------- the figure keeps the house rules

def test_harmonic_figure_carries_the_design_conventions():
    html = _macro()
    # theme-following ink: structure on currentColor, accents on tokens
    assert 'stroke="currentColor"' in html
    assert 'stroke="var(--gold)"' in html
    assert "var(--bad)" not in html                 # red stays semantic
    # text rides the rem classes, never fixed viewBox-unit sizes
    assert "svgt-sm" in html
    assert 'font-size="' not in html
    # accessible name and long description
    assert 'role="img"' in html and ARIA_ONE in html
    assert "<desc>" in html
    # axes read as calendar months, never week indices
    assert "month of season" in html
    for m in ("Aug", "Nov", "Feb", "May"):
        assert f">{m}</text>" in html, m
    assert "weeks since August 1" not in html
    assert "peak week" in html                      # phi-1 marked and named
    assert "(early Jan)" in html                    # and placed on the calendar
    assert html.count("&#949;&#8321;") == 2         # both amplitude extremes
    assert "1.0 (&#946;" in html                    # the beta0 reference
    # the caption owns the figure's honesty note
    assert "Values shown are illustrative" in html
    assert "illustrative" in html
    assert "fitted per state and week" in html


def test_two_strain_variant_shares_amplitude_with_per_strain_peaks():
    html = _macro(two=True)
    assert ARIA_TWO in html
    # two curves in the member colors, sharing one amplitude band
    assert html.count('stroke="var(--gold)"') >= 2      # curve + peak marks
    assert html.count('stroke="var(--slate)"') >= 2
    g = ui_templating._harmonic_fig(0.35, [20, 30])
    # both peak markers sit on the shared upper amplitude edge
    assert html.count(f'cy="{g["y_hi"]}" r="4"') == 2
    assert f'fill="var(--gold)"/>' in html
    # per-strain peak labels and the legend naming the strains
    assert ">A</tspan>" in html and ">B</tspan>" in html
    assert "influenza A" in html and "influenza B" in html
    assert "all are fitted per state and week" in html


def test_harmonic_curve_is_computed_from_the_stated_equation():
    g = ui_templating._harmonic_fig(0.35, [22.0])
    pts = [tuple(map(float, p[1:].split(",")))
           for p in g["paths"][0].split(" ")]
    ys = [y for _, y in pts]
    # the curve's extremes land exactly on the labeled amplitude rows
    assert abs(min(ys) - g["y_hi"]) < 0.15
    assert abs(max(ys) - g["y_lo"]) < 0.15
    # and the peak happens at the phi-1 pixel the marker points at
    peak_x = min(pts, key=lambda p: p[1])[0]
    assert abs(peak_x - g["peaks"][0]) < 3
    # the 1.0 reference sits strictly inside the band
    assert g["y_hi"] < g["y_one"] < g["y_lo"]


# ----------------------------------------------- theme token block parity

def _block(css: str, selector: str) -> dict:
    m = re.search(re.escape(selector) + r"\{([^}]*)\}", css)
    assert m, f"missing token block {selector}"
    return dict(re.findall(r"--([\w-]+)\s*:\s*([^;]+);", m.group(1)))


LIGHT = _block(NAU, ":root")
DARK = _block(NAU, '[data-theme="dark"]')
PAPER = _block(NAU, '[data-theme="paper"]')
DIM = _block(NAU, '[data-theme="dim"]')
#: every named theme block (light is the root block)
NAMED = re.findall(r'\[data-theme="([\w-]+)"\]\{', NAU)
BLOCKS = {"light": LIGHT}
BLOCKS.update({t: _block(NAU, f'[data-theme="{t}"]') for t in NAMED})


def test_the_eight_theme_blocks_define_the_same_tokens():
    assert sorted(BLOCKS) == sorted(["light", "paper", "github", "solarized",
                                     "dim", "dark", "nord", "dracula"])
    sets = {n: set(b) for n, b in BLOCKS.items()}
    for name, s in sets.items():
        assert s == sets["light"], (
            f"{name} token set diverges: only-in-{name}="
            f"{sorted(s - sets['light'])} "
            f"missing-from-{name}={sorted(sets['light'] - s)}")
    assert len(sets["light"]) >= 20                 # the full palette, not a stub
    assert "map-nodata" in sets["light"]            # joined the parity contract
    # size tokens stay theme-independent: never restated per theme
    assert not any(t.startswith("fs-") for t in sets["light"])
    # and no stray extra token blocks reintroduce fall-through definitions
    assert NAU.count(":root{") == 2                 # colors + the type scale
    for t in NAMED:
        assert NAU.count(f'[data-theme="{t}"]{{') == 1, t
    # the light block also answers to data-theme="light" (a theme preview
    # can wear it inside another theme)
    assert '[data-theme="light"],:root{' in NAU


# ------------------------------------- the measured bars on the new themes

def _lum(hexs: str) -> float:
    hexs = hexs.strip().lstrip("#")
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexs[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _cr(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _check(theme: dict):
    for fg in ("ink", "mut", "gold", "ok", "warn", "bad"):
        for bgt in ("bg", "card"):
            assert _cr(theme[fg], theme[bgt]) >= 4.5, (fg, bgt)
    assert _cr(theme["nav-ink"], theme["nav-bg"]) >= 4.5
    assert _cr(theme["field-line"], theme["bg"]) >= 3.0       # field boundary
    assert _cr(theme["accent-ink"], theme["track"]) >= 3.0    # progress fill
    assert _cr(theme["accent-ink"], theme["nav-bg"]) >= 3.0   # active tab
    assert _cr(theme["on-accent"], theme["gold-bright"]) >= 4.5  # button.gold ink
    assert _cr(theme["on-bad"], theme["bad"]) >= 4.5          # button.danger
    for bgt in ("bg", "card"):                                # outline buttons
        assert _cr(theme["btn-ink"], theme[bgt]) >= 4.5, bgt


def test_paper_pairs_hold_the_review_bars():
    _check(PAPER)
    assert PAPER["on-bad"] == "#FFFFFF"   # paper keeps the light danger ink


def test_dim_pairs_hold_the_review_bars():
    _check(DIM)
    assert DIM["on-bad"] == "#0C0D17"     # dim takes the dark treatment


def test_every_theme_holds_the_review_bars():
    for name, b in BLOCKS.items():
        try:
            _check(dict(LIGHT, **b))
        except AssertionError as e:
            raise AssertionError((name, e.args)) from e


# ------------------------------------------------------- the navbar picker

def test_navbar_theme_picker_lists_every_theme():
    html = client.get("/data").text
    assert ('class="themepick" role="radiogroup" aria-labelledby="h-dm-theme"'
            in html)
    for th in BLOCKS:
        assert f'value="{th}" data-th="{th}"' in html, th
    assert html.count('type="radio" name="dm-theme"') == len(BLOCKS)
    assert "themebtn" not in html                   # the two-state toggle is gone
    # the current theme is checked on load and on every change
    assert "b.dataset.th" in html
    # (a stored theme checks its preview; none checks Match system)
    assert "b.checked=!free&&(b.dataset.th===t)" in BASE_T
    assert "if(sys)sys.checked=free;" in BASE_T
    # persistence rides the existing preference key
    assert "localStorage.setItem('theme',t)" in BASE_T
    # every change dispatches themechange so Plotly and the player recolor
    assert "dispatchEvent(new Event('themechange'))" in BASE_T
    # the first-paint script accepts all eight and falls back on junk
    assert ("['light','paper','github','solarized','dim','dark','nord',"
            "'dracula'].indexOf(t)<0") in html


def test_dark_grounds_receive_the_dark_control_treatment():
    # a dark ground would hide the LANL Blue outline: every dark theme's
    # outline buttons wear its accent, and the text on a --bad fill turns
    # near-black; the rules read the tokens, so no rule names a theme
    for name, over in BLOCKS.items():
        b = dict(LIGHT, **over)
        if b["scheme"] != "dark":
            assert b["btn-ink"] == b["ink"], name    # light grounds: the ink
            continue
        assert b["btn-ink"] == b["gold"], name
        assert _cr(b["on-bad"], "#FFFFFF") > 10, name
    for rule in ("button{padding:.45rem .95rem;border:1px solid var(--btn-ink)",
                 "color:var(--btn-ink);font:inherit",
                 "button.gold{background:var(--gold-bright);border-color:var(--gold-bright);\n  color:var(--on-accent)}",
                 "button.danger{background:var(--bad);border-color:var(--bad);color:var(--on-bad)}",
                 "a.btn.gold{background:var(--gold-bright);border-color:var(--gold-bright);\n  color:var(--on-accent)}"):
        assert rule in NAU, rule
    assert '[data-theme="dim"] button{' not in NAU
    assert '[data-theme="dark"] button,' not in NAU
