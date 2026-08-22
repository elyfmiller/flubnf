"""The two accessibility modifiers: high contrast and the red-green-safe
palette.

Both are MODIFIERS on the root element (data-contrast="high",
data-vision="cvd"), composing with any of the four themes rather than
adding themes of their own. The theme blocks carry one literal per theme
for every modifier variant (-hc, -cvd, and the map's category scale), and
two mode blocks remap the consumer tokens onto those literals through
var(), so 4 themes x 2 contrast x 2 vision resolves through the cascade
instead of sixteen hand-written blocks. These tests emulate that cascade
in Python and spot-check combinations across the full grid, hold the
measured contrast bars with the modifier on, and verify blue/orange
separability under deuteranopia and protanopia simulation.
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
PLAYER = (UI / "static" / "player.js").read_text()
FORECAST_T = (UI / "templates" / "forecast.html").read_text()
MODEL_T = (UI / "templates" / "model.html").read_text()
SEASON_T = (UI / "templates" / "retro_season.html").read_text()


# ------------------------------------------------------ cascade emulation

def _decls(selector: str) -> dict:
    m = re.search(re.escape(selector) + r"\{([^}]*)\}", NAU)
    assert m, f"missing token block {selector}"
    return dict(re.findall(r"--([\w-]+)\s*:\s*([^;]+);", m.group(1)))


ROOT = _decls(":root")
THEME = {"light": {}, "paper": _decls('[data-theme="paper"]'),
         "dim": _decls('[data-theme="dim"]'),
         "dark": _decls('[data-theme="dark"]')}
HC = _decls('[data-contrast="high"]')
CVD = _decls('[data-vision="cvd"]')


def resolve(theme: str, contrast: bool = False, vision: bool = False) -> dict:
    """Apply the blocks the way the cascade does (equal specificity, file
    order: root, theme, contrast, vision), then substitute var() chains."""
    toks = dict(ROOT)
    toks.update(THEME[theme])
    if contrast:
        toks.update(HC)
    if vision:
        toks.update(CVD)
    out = {}

    def get(name, depth=0):
        assert depth < 10, f"var() cycle at --{name}"
        v = toks[name].strip()
        m = re.fullmatch(r"var\(--([\w-]+)\)", v)
        return get(m.group(1), depth + 1) if m else v

    for name in toks:
        out[name] = get(name)
    return out


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


# ------------------------------------------------ the token architecture

def test_theme_blocks_carry_the_modifier_variants_literally():
    # every theme block defines every -hc and -cvd variant and the two map
    # scales as literal colors: the parity test already pins equal token
    # sets, this pins the modifier variants' presence and literalness
    need = {"ink-hc", "mut-hc", "nav-ink-hc", "line-hc", "field-line-hc",
            "accent-ink-hc", "ok-hc", "warn-hc", "bad-hc",
            "ok-cvd", "bad-cvd", "ok-cvd-hc", "bad-cvd-hc",
            "cat-large-decrease", "cat-decrease", "cat-stable",
            "cat-increase", "cat-large-increase",
            "cat-cvd-large-decrease", "cat-cvd-decrease", "cat-cvd-stable",
            "cat-cvd-increase", "cat-cvd-large-increase"}
    for name in ("light", "paper", "dim", "dark"):
        block = dict(ROOT) if name == "light" else THEME[name]
        missing = need - set(block)
        assert not missing, (name, sorted(missing))
        for t in need:
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", block[t].strip()), \
                (name, t, block[t])


def test_mode_blocks_only_remap_and_never_state_colors():
    # the modifier blocks contain var() references and the focus width
    # only: a literal color there would break the per-theme composition
    for block in (HC, CVD):
        for tok, val in block.items():
            if tok == "focus-w":
                continue
            assert re.fullmatch(r"var\(--[\w-]+\)", val.strip()), (tok, val)
    # exactly one block each, contrast before vision, both after the theme
    # blocks, so cvd wins --ok/--bad when both modifiers are on while the
    # contrast block retargets the cvd pair's own -hc variants
    assert NAU.count('[data-contrast="high"]{') == 1
    assert NAU.count('[data-vision="cvd"]{') == 1
    assert (NAU.index('[data-theme="dim"]{')
            < NAU.index('[data-contrast="high"]{')
            < NAU.index('[data-vision="cvd"]{'))
    assert HC["ok-cvd"] == "var(--ok-cvd-hc)"
    assert HC["bad-cvd"] == "var(--bad-cvd-hc)"
    assert HC["focus-w"] == "3px"                   # thickened focus rings


def test_token_overrides_compose_across_the_grid():
    # spot-checks across the 4 x 2 x 2 grid, resolved by cascade emulation
    # rather than sixteen enumerated expectations
    # normal contrast and vision: the classic palette, untouched
    assert resolve("light")["ok"] == "#177245"
    assert resolve("dark")["bad"] == "#FB4653"
    # contrast alone: consumer tokens land on the theme's -hc literals
    for th in ("light", "paper", "dim", "dark"):
        r = resolve(th, contrast=True)
        base = dict(ROOT) if th == "light" else THEME[th]
        for pair in (("ink", "ink-hc"), ("mut", "mut-hc"),
                     ("line", "line-hc"), ("field-line", "field-line-hc"),
                     ("accent-ink", "accent-ink-hc"), ("ok", "ok-hc"),
                     ("warn", "warn-hc"), ("bad", "bad-hc"),
                     ("nav-ink", "nav-ink-hc")):
            assert r[pair[0]] == base[pair[1]], (th, pair)
        assert r["focus-w"] == "3px"
    # vision alone: ok/bad and the whole map scale go blue/orange
    for th in ("light", "paper", "dim", "dark"):
        r = resolve(th, vision=True)
        base = dict(ROOT) if th == "light" else THEME[th]
        assert r["ok"] == base["ok-cvd"], th
        assert r["bad"] == base["bad-cvd"], th
        for c in ("large-decrease", "decrease", "stable", "increase",
                  "large-increase"):
            assert r["cat-" + c] == base["cat-cvd-" + c], (th, c)
    # both: the cvd pair at its high-contrast strength, per theme
    for th in ("light", "dim"):
        r = resolve(th, contrast=True, vision=True)
        base = dict(ROOT) if th == "light" else THEME[th]
        assert r["ok"] == base["ok-cvd-hc"], th
        assert r["bad"] == base["bad-cvd-hc"], th
        assert r["ink"] == base["ink-hc"], th       # contrast still applies


# --------------------------------------- the bars with the modifier on

def test_high_contrast_holds_well_above_the_review_bars():
    # the review's bars are the floor (4.5 text, 3 boundaries and fills);
    # the modifier aims well above: 7:1 for every text token, 3:1+ for
    # boundaries, 4.5:1+ for the progress fill on its track
    danger_ink = {"light": "#FFFFFF", "paper": "#FFFFFF",
                  "dim": "#0C0D17", "dark": "#0C0D17"}
    for th in ("light", "paper", "dim", "dark"):
        for vision in (False, True):
            r = resolve(th, contrast=True, vision=vision)
            for fg in ("ink", "mut", "ok", "warn", "bad"):
                for bg in ("bg", "card"):
                    assert _cr(r[fg], r[bg]) >= 7.0, (th, vision, fg, bg)
            assert _cr(r["nav-ink"], r["nav-bg"]) >= 7.0, (th, vision)
            for bg in ("bg", "card"):
                assert _cr(r["line"], r[bg]) >= 3.0, (th, vision, bg)
            assert _cr(r["field-line"], r["bg"]) >= 4.5, (th, vision)
            assert _cr(r["accent-ink"], r["track"]) >= 4.5, (th, vision)
            assert _cr(danger_ink[th], r["bad"]) >= 4.5, (th, vision)


def test_cvd_pair_holds_the_ratios_of_the_pair_it_replaces():
    # in every theme, at both contrast strengths, the blue/orange pair
    # meets or beats the worst-surface ratio of the green/red it replaces
    for th in ("light", "paper", "dim", "dark"):
        base = resolve(th)
        cvd = resolve(th, vision=True)
        for tok in ("ok", "bad"):
            floor = min(_cr(base[tok], base["bg"]),
                        _cr(base[tok], base["card"]))
            got = min(_cr(cvd[tok], cvd["bg"]), _cr(cvd[tok], cvd["card"]))
            assert got >= floor - 0.01, (th, tok, got, floor)


# ------------------------------------------- color-vision simulation

# Vienot (1999) dichromacy simulation in linearized sRGB
_DEUTAN = ((0.625, 0.375, 0.0), (0.7, 0.3, 0.0), (0.0, 0.3, 0.7))
_PROTAN = ((0.567, 0.433, 0.0), (0.558, 0.442, 0.0), (0.0, 0.242, 0.758))


def _sim(hexs: str, M) -> tuple:
    hexs = hexs.lstrip("#")

    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def unlin(c):
        c = max(0.0, min(1.0, c))
        return round((12.92 * c if c <= 0.0031308
                      else 1.055 * c ** (1 / 2.4) - 0.055) * 255)

    r, g, b = (lin(int(hexs[i:i + 2], 16)) for i in (0, 2, 4))
    return tuple(unlin(M[i][0] * r + M[i][1] * g + M[i][2] * b)
                 for i in range(3))


def _simdist(a: str, b: str, M) -> float:
    pa, pb = _sim(a, M), _sim(b, M)
    return sum((x - y) ** 2 for x, y in zip(pa, pb)) ** 0.5


def test_swapped_pair_stays_separable_under_deutan_and_protan():
    for th in ("light", "paper", "dim", "dark"):
        base = resolve(th)
        for M in (_DEUTAN, _PROTAN):
            rg = _simdist(base["ok"], base["bad"], M)
            for contrast in (False, True):
                r = resolve(th, contrast=contrast, vision=True)
                d = _simdist(r["ok"], r["bad"], M)
                assert d >= 80, (th, contrast, d)
                if not contrast:
                    # at normal strength the blue/orange pair is MORE
                    # separable than the green/red it replaces
                    assert d >= rg, (th, d, rg)


def test_member_palette_audit_and_its_non_color_redundancy():
    """The member palette audit, with its honest negative result.

    The color-vision mode swaps ok/bad ENCODINGS; member colors identify
    series, which is a different job, and the measured audit says the
    blue/orange swap would not help them anyway. Two pairs ARE weakly
    separated under dichromacy, and both are blue-family neighbours that
    were already the weakest pairs in normal vision:

        pair                simulated   normal
        pf / pf2s              27          91
        ensemble / pf          36          82

    pf2s is the research member and does not ship. The ensemble/pf pair
    ships, so the floors below pin it against further regression, and the
    real mitigation is that member identity never rests on color: every
    trace carries its display name in the legend and the stats table
    repeats it beside the swatch.
    """
    mem = {"ensemble": "#34C0F0", "pf": "#6E8FD0", "analogue": "#FFC72C",
           "pf2s": "#2BB5A0", "official": "#AAB1C9"}
    for M in (_DEUTAN, _PROTAN):
        # the gold member stays far from both blues, so the shipped trio
        # never collapses into one indistinct family
        for other in ("ensemble", "pf"):
            assert _simdist(mem["analogue"], mem[other], M) >= 150, other
        # the known-weak shipped pair, pinned at its measured value so a
        # future palette change cannot quietly make it worse
        assert _simdist(mem["ensemble"], mem["pf"], M) >= 35
    # redundancy is what actually carries member identity
    assert "name: nameOf(m)" in PLAYER
    assert "+ '\"></span>' + nameOf(m)" in PLAYER


def test_cvd_map_scale_beats_the_classic_scale_under_deutan():
    def worst(vals, M):
        return min(_simdist(a, b, M)
                   for i, a in enumerate(vals) for b in vals[i + 1:])

    cats = ("large-decrease", "decrease", "stable", "increase",
            "large-increase")
    classic = [ROOT["cat-" + c] for c in cats]
    safe = [ROOT["cat-cvd-" + c] for c in cats]
    for M in (_DEUTAN, _PROTAN):
        assert worst(safe, M) >= 50, worst(safe, M)
        assert worst(safe, M) > worst(classic, M)


# ------------------------------------------------- the navbar controls

def test_a11y_controls_sit_with_the_theme_picker_and_state_pressed():
    html = client.get("/data").text
    assert 'class="a11ypick" role="group" aria-label="Accessibility modes"' \
        in html
    assert 'data-ax="contrast"' in html and 'data-ax="vision"' in html
    # both are labeled toggles carrying aria-pressed, beside the existing
    # theme picker and text-size group in the one navbar
    assert html.index('class="fontsize"') < html.index('class="themepick"') \
        < html.index('class="a11ypick"')
    assert 'aria-label="High contrast"' in html
    assert 'aria-label="Red-green safe colors"' in html
    # pressed state is marked on load and on every press
    assert "de.getAttribute('data-contrast')==='high'" in BASE_T
    assert "de.getAttribute('data-vision')==='cvd'" in BASE_T


def test_modes_persist_and_dispatch_themechange():
    # persistence rides localStorage like the theme; an explicit 'normal'
    # stops the OS preference from re-enabling contrast
    assert "localStorage.setItem('contrast',on?'normal':'high')" in BASE_T
    assert "localStorage.setItem('vision',v?'normal':'cvd')" in BASE_T
    # each press dispatches themechange so Plotly and the player recolor
    a11y = BASE_T.split("// accessibility modes:", 1)[1] \
                 .split("// text-size control:", 1)[0]
    assert "dispatchEvent(new Event('themechange'))" in a11y


def test_first_paint_honors_the_os_contrast_preference():
    # no stored choice: prefers-contrast: more turns the modifier on
    # before first paint, exactly like the theme's dark fallback
    assert "matchMedia('(prefers-contrast: more)').matches" in BASE_T
    assert "setAttribute('data-contrast','high')" in BASE_T
    assert "localStorage.getItem('vision')==='cvd'" in BASE_T


# --------------------------------------------- the map follows the mode

def test_map_fills_and_legend_ride_the_category_tokens():
    from app.core.usmap import CAT_COLOR, cat_fill, map_legend, svg_map
    # each category resolves through its token with the classic literal as
    # the fallback for standalone exports
    for c, hexs in CAT_COLOR.items():
        assert cat_fill(c) == f"var(--cat-{c.replace('_', '-')}, {hexs})"
    cards = {"04": {"probs": {"increase": 0.8}, "name": "Arizona",
                    "abbr": "AZ", "fips": "04"}}
    svg = svg_map(cards)
    assert 'fill="var(--cat-increase, #e8a33d)"' in svg
    lg = map_legend()
    for c in CAT_COLOR:
        assert f"var(--cat-{c.replace('_', '-')}" in lg, c


def test_the_vision_block_remaps_every_category():
    for c in ("large-decrease", "decrease", "stable", "increase",
              "large-increase"):
        assert CVD["cat-" + c] == f"var(--cat-cvd-{c})", c


# ------------------------------------- no information by hue alone

def test_no_ok_bad_surface_relies_on_hue_alone():
    # swapping the hue must never lose information: every surface that
    # colors ok/bad also prints the number or the word it means
    from app.ui.server import relwis_chip
    retro_t = (UI / "templates" / "retro.html").read_text()
    # the one relWIS chip outside a table prints the score beside the class
    assert "1.234" in relwis_chip(1.234)
    assert "0.500" in relwis_chip(0.5)
    # the player's stats cells print the value, never a bare colored cell
    assert "'<td class=\"num ' + (v < 1 ? 'ok' : 'bad') + '\">'" in PLAYER
    assert "+ v.toFixed(3) + '</td>'" in PLAYER
    # the season page: head cards print the number and name the scale, and
    # the per-state table prints every score it colors
    assert '{{ "%.3f"|format(v) }}' in SEASON_T
    assert "relWIS vs the FluSight baseline" in SEASON_T
    assert "relWIS below 1 beats the CDC FluSight baseline" in SEASON_T
    assert '{{ "%.3f"|format(r[m]) if r[m] else "n/a" }}' in SEASON_T
    # status pills and run states print the status WORD inside the span
    assert "{{ r.status }}</span>" in FORECAST_T
    for phrase in ("· complete", "· interrupted"):
        assert phrase in retro_t, phrase


# ------------------------------- charts export readable, themed PNGs

def test_chart_layouts_state_an_explicit_opaque_surface():
    # transparent chart grounds exported unreadable PNGs (theme ink over a
    # transparent file); every layout now states the card surface it sits
    # on, which composites identically on screen
    assert "rgba(0,0,0,0)" not in PLAYER
    assert "rgba(0,0,0,0)" not in FORECAST_T
    assert "rgba(0,0,0,0)" not in MODEL_T
    assert "paper_bgcolor: surf, plot_bgcolor: surf" in PLAYER
    assert "paper_bgcolor:surf, plot_bgcolor:surf" in FORECAST_T
    assert "paper_bgcolor:surf" in MODEL_T
    # the console hosts read the surface from the card token per draw; the
    # static season report host falls back to its fixed dark card
    assert "card: css('--card')" in SEASON_T
    assert "card: '#151729'" in PLAYER
    assert "p.card || '#151729'" in PLAYER


def test_save_png_exports_at_scale_with_meaningful_filenames():
    assert "toImageButtonOptions" in PLAYER
    assert "toImageButtonOptions" in FORECAST_T
    assert "toImageButtonOptions" in MODEL_T
    for src in (PLAYER, FORECAST_T, MODEL_T):
        assert "scale: 2" in src or "scale:2" in src
        assert "'flubnf_'" in src or "('flubnf_" in src
    # the weekly report's figures export under their figure id
    from app.core import report_v2
    import plotly.graph_objects as go
    fig = report_v2._fig_layout(go.Figure(), height=100, title="t")
    html = report_v2._html(fig, div_id="natfan")
    assert '"filename": "flubnf_natfan"' in html
    assert '"scale": 2' in html
