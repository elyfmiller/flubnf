"""The seasonal-harmonic figure and the four-theme system.

One parameterized macro draws beta(t)/beta0 over a season from the same
cosine-exponential the equation states, computed by a template global rather
than traced by hand, and appears on every surface that shows the equation:
the Models PF view, Methods (both the SIHRS card and the two-strain
section), the home workflow card, and the two-strain model page. The theme
system grows two intermediate themes, paper and dim, selected by a compact
navbar picker; every theme block defines the same token set (no color may
fall through to another theme's value), and both new themes hold the
review's measured bars: 4.5:1 for text pairs, 3:1 for boundaries and fills.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

from app.ui import server as srv                    # noqa: E402

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
    # a single parameterized macro, not per-page copies: eq_pf and eq_pf2s
    # embed it, and home imports the same macro directly
    assert "{{ harmonic() }}" in DIAGRAMS_T
    assert "{{ harmonic(two=true) }}" in DIAGRAMS_T
    home_t = (UI / "templates" / "home.html").read_text()
    assert "{{ dg.harmonic() }}" in home_t
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
    # the stated axes and annotations: the axis reads as calendar months
    # (from the shared season month offsets), never as week indices
    assert "month of season" in html
    for m in ("Aug", "Nov", "Feb", "May"):
        assert f">{m}</text>" in html, m
    assert "weeks since August 1" not in html
    assert "peak week" in html                      # phi-1 marked and named
    assert "(early Jan)" in html                    # and placed on the calendar
    assert html.count("&#949;&#8321;") == 2         # both amplitude extremes
    assert "1.0 (&#946;" in html                    # the beta0 reference
    # the caption ties the curve to the model and owns its honesty note
    assert "curve the filter bends each week" in html
    assert "illustrative" in html
    assert "fitted per state and week" in html


def test_two_strain_variant_shares_amplitude_with_per_strain_peaks():
    html = _macro(two=True)
    assert ARIA_TWO in html
    # two curves in the member colors, sharing one amplitude band
    assert html.count('stroke="var(--gold)"') >= 2      # curve + peak marks
    assert html.count('stroke="var(--slate)"') >= 2
    g = srv._harmonic_fig(0.35, [20, 30])
    # both peak markers sit on the shared upper amplitude edge
    assert html.count(f'cy="{g["y_hi"]}" r="4"') == 2
    assert f'fill="var(--gold)"/>' in html
    # per-strain peak labels and the legend naming the strains
    assert ">A</tspan>" in html and ">B</tspan>" in html
    assert "influenza A" in html and "influenza B" in html
    assert "phase-shifted per strain" in html


def test_harmonic_curve_is_computed_from_the_stated_equation():
    g = srv._harmonic_fig(0.35, [22.0])
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


def test_the_four_theme_blocks_define_the_same_tokens():
    sets = {n: set(b) for n, b in
            (("light", LIGHT), ("dark", DARK), ("paper", PAPER),
             ("dim", DIM))}
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
    assert NAU.count('[data-theme="dark"]{') == 1
    assert NAU.count('[data-theme="paper"]{') == 1
    assert NAU.count('[data-theme="dim"]{') == 1


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


def _check(theme: dict, danger_ink: str):
    for fg in ("ink", "mut", "gold", "ok", "warn", "bad"):
        for bgt in ("bg", "card"):
            assert _cr(theme[fg], theme[bgt]) >= 4.5, (fg, bgt)
    assert _cr(theme["nav-ink"], theme["nav-bg"]) >= 4.5
    assert _cr(theme["field-line"], theme["bg"]) >= 3.0       # field boundary
    assert _cr(theme["accent-ink"], theme["track"]) >= 3.0    # progress fill
    assert _cr(theme["accent-ink"], theme["nav-bg"]) >= 3.0   # active tab
    assert _cr("#0C0D17", theme["gold-bright"]) >= 4.5        # button.gold ink
    assert _cr(danger_ink, theme["bad"]) >= 4.5               # button.danger


def test_paper_pairs_hold_the_review_bars():
    _check(PAPER, "#FFFFFF")        # paper keeps the light danger ink (white)


def test_dim_pairs_hold_the_review_bars():
    _check(DIM, "#0C0D17")          # dim takes the dark treatment (near-black)


# ------------------------------------------------------- the navbar picker

def test_navbar_theme_picker_replaces_the_toggle():
    html = client.get("/data").text
    assert 'class="themepick" role="group" aria-label="Color theme"' in html
    for th in ("light", "paper", "dim", "dark"):
        assert f'data-th="{th}"' in html, th
    assert "themebtn" not in html                   # the two-state toggle is gone
    # honest pressed states, marked on load and on every press
    assert "b.dataset.th" in html
    assert "setAttribute('aria-pressed',String(b.dataset.th===t))" in BASE_T
    # persistence rides the existing preference key
    assert "localStorage.setItem('theme',t)" in BASE_T
    # every press dispatches themechange so Plotly and the player recolor
    assert "dispatchEvent(new Event('themechange'))" in BASE_T
    # the first-paint script accepts all four and falls back on junk
    assert "['light','paper','dim','dark'].indexOf(t)<0" in BASE_T


def test_dim_receives_the_dark_control_treatment():
    # the slate ground is dark: the LANL Blue button outline would vanish,
    # so dim joins every dark-only control rule
    for rule in ('[data-theme="dim"] button',
                 '[data-theme="dim"] button.quiet',
                 '[data-theme="dim"] button.gold',
                 '[data-theme="dim"] button.danger',
                 '[data-theme="dim"] button.linkish'):
        assert rule in NAU, rule
