"""The Display menu (base.html) and the eight themes (nau.css,
static/brand/logos.css).

  * one list of themes: the first-paint validation, the picker's radios,
    nau.css's token blocks and the logo lines name the same eight, in the
    menu's order (light grounds first, then dark);
  * the measured bars in every theme x high contrast x color-vision mode:
    text 4.5:1 (7:1 with high contrast), boundaries and large text 3:1,
    the text on every fill; chart series, members and the highlighted
    series 3:1 on both grounds;
  * the color-vision mode under simulated deuteranopia and protanopia
    (Machado, Oliveira and Fernandes 2009, severity 1; and the Vienot 1999
    matrices the older audits use): the status triad, the series in the
    order charts take them, and the map scale stay apart;
  * the controls: a labelled 80% to 160% slider with its steps, Reset and
    the migration of the old s/m/l sizes; the theme radios drawn as
    previews; two named switches with their tips; headings with tips in
    place of hover titles; the logo slot per theme.
"""
import itertools
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

from app.ui import server as srv                    # noqa: E402

client = TestClient(srv.app)

UI = Path(__file__).resolve().parents[1] / "ui"
NAU = (UI / "static" / "nau.css").read_text()
LOGOS = (UI / "static" / "brand" / "logos.css").read_text()
BASE_T = (UI / "templates" / "base.html").read_text()
ORDER = ["light", "paper", "github", "solarized", "dim", "dark", "nord",
         "dracula"]
DARK = {"dim", "dark", "nord", "dracula"}


# ------------------------------------------------------------ the tokens

def _decls(selector: str) -> dict:
    m = re.search(re.escape(selector) + r"\{([^}]*)\}", NAU)
    assert m, selector
    return {k: v.strip() for k, v in
            re.findall(r"--([\w-]+)\s*:\s*([^;]+);", m.group(1))}


ROOT = _decls(":root")
NAMED = re.findall(r'\[data-theme="([\w-]+)"\]\{', NAU)
THEME = {"light": {}}
THEME.update({t: _decls(f'[data-theme="{t}"]') for t in NAMED})
HC = _decls('[data-contrast="high"]')
CVD = _decls('[data-vision="cvd"]')


def resolve(theme: str, contrast: bool = False, vision: bool = False) -> dict:
    """The cascade: root, theme, contrast, vision; then var() chains."""
    toks = dict(ROOT)
    toks.update(THEME[theme])
    if contrast:
        toks.update(HC)
    if vision:
        toks.update(CVD)

    def get(name, depth=0):
        assert depth < 10, name
        v = toks[name].strip()
        m = re.fullmatch(r"var\(--([\w-]+)\)", v)
        return get(m.group(1), depth + 1) if m else v
    return {n: get(n) for n in toks}


def GRID():
    for th in ORDER:
        for c in (False, True):
            for v in (False, True):
                yield f"{th}{'+hc' if c else ''}{'+cvd' if v else ''}", c, \
                    resolve(th, c, v)


# ------------------------------------------------------------ color math

def _rgb(h: str) -> tuple:
    h = h.strip().lstrip("#")
    assert re.fullmatch(r"[0-9a-fA-F]{6}", h), h
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _unlin(c: float) -> float:
    c = max(0.0, min(1.0, c))
    return (12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055) * 255


def _cr(a: str, b: str) -> float:
    def lum(h):
        r, g, bl = (_lin(c) for c in _rgb(h))
        return 0.2126 * r + 0.7152 * g + 0.0722 * bl
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _mix(a: str, b: str, p: float) -> str:
    """color-mix(in srgb, a p, b)"""
    return "#" + "".join(f"{round(p * x + (1 - p) * y):02X}"
                         for x, y in zip(_rgb(a), _rgb(b)))


IDENT = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
# Machado, Oliveira and Fernandes (2009), severity 1.0, linear RGB
MACHADO_DEUTAN = ((0.367322, 0.860646, -0.227968),
                  (0.280085, 0.672501, 0.047413),
                  (-0.011820, 0.042940, 0.968881))
MACHADO_PROTAN = ((0.152286, 1.052583, -0.204868),
                  (0.114503, 0.786281, 0.099216),
                  (-0.003882, -0.048116, 1.051998))
# Vienot (1999), the matrices test_a11y_modes and test_season_palette use
VIENOT_DEUTAN = ((0.625, 0.375, 0.0), (0.7, 0.3, 0.0), (0.0, 0.3, 0.7))
VIENOT_PROTAN = ((0.567, 0.433, 0.0), (0.558, 0.442, 0.0),
                 (0.0, 0.242, 0.758))
MACHADO = (IDENT, MACHADO_DEUTAN, MACHADO_PROTAN)
EVERY = MACHADO + (VIENOT_DEUTAN, VIENOT_PROTAN)


def _lab(h: str, M=IDENT) -> tuple:
    """h as a dichromat sees it (M), in CIE L*a*b* (D65)."""
    r, g, b = (_lin(c) for c in _rgb(h))
    s = [M[i][0] * r + M[i][1] * g + M[i][2] * b for i in range(3)]
    r, g, b = (_lin(round(_unlin(c))) for c in s)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    return (116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z)))


def _de(a: str, b: str, sims=MACHADO) -> float:
    """The smallest CIE76 distance between a and b over the simulations."""
    return min(sum((p - q) ** 2 for p, q in zip(_lab(a, M), _lab(b, M))) ** .5
               for M in sims)


# ------------------------------------------------------- one theme list

def test_the_theme_lists_agree():
    html = client.get("/data").text
    # the first-paint validation, rendered from base.html's one list
    boot = re.search(r"if\(\[([^\]]*)\]\.indexOf\(t\)<0\)", html)
    assert boot, "first-paint theme validation"
    assert re.findall(r"'([\w-]+)'", boot.group(1)) == ORDER
    # the picker's radios, in the same order
    assert re.findall(r'type="radio" name="dm-theme" value="([\w-]+)"',
                      html) == ORDER
    # a token block and a logo line per theme
    assert ["light"] + NAMED == ["light", "dark", "paper", "dim", "github",
                                 "solarized", "nord", "dracula"]
    assert sorted(THEME) == sorted(ORDER)
    logos = re.findall(r'\[data-theme="([\w-]+)"\][,{]', LOGOS)
    assert logos == ORDER, logos
    # the reports carry the same eight: their first-paint check and a
    # token block per named theme (app/core/html_page.py)
    from app.core import html_page
    assert list(html_page.THEMES) == ORDER
    rboot = re.search(r"if\(\[([^\]]*)\]\.indexOf\(t\)<0\)",
                      html_page.theme_boot_script())
    assert re.findall(r"'([\w-]+)'", rboot.group(1)) == ORDER
    tokens = html_page.theme_token_css()
    for th in ORDER[1:]:
        assert f'[data-theme="{th}"]{{' in tokens, th
    # every preview wears its theme; the ground groups follow the list
    for th in ORDER:
        assert f'class="dm-th-sw" data-theme="{th}" aria-hidden="true"' in html
        assert resolve(th)["scheme"] == ("dark" if th in DARK else "light")
    light_grp = html.index('>Light</span>')
    dark_grp = html.index('>Dark</span>')
    assert light_grp < html.index('value="solarized"') < dark_grp \
        < html.index('value="dim"')


def test_every_theme_defines_every_token_as_a_literal():
    names = set(ROOT)
    for th in ORDER:
        block = dict(ROOT) if th == "light" else THEME[th]
        assert set(block) == names, (th, sorted(set(block) ^ names))
        for k, v in block.items():
            assert "var(" not in v, (th, k)
            assert "/static/" not in v, (th, k)      # the reports embed these
    for tok in ("btn-ink", "on-accent", "on-bad", "scheme", "warn-cvd",
                "warn-cvd-hc"):
        assert tok in names, tok
    # the editor-inspired palettes carry their credit and license
    for name, credit in (("github", "Primer"), ("solarized", "Schoonover"),
                         ("nord", "Arctic Ice Studio"), ("dracula", "Zeno Rocha")):
        head = " ".join(NAU.split(f'[data-theme="{name}"]{{', 1)[0].rsplit("/*", 1)[1].split())
        assert credit in head and "MIT License" in head, name


# -------------------------------------------------------- the bars

def test_text_and_boundaries_hold_aa_in_every_theme_and_mode():
    seen = 0
    for name, hc, r in GRID():
        bar = 7.0 if hc else 4.5
        for fg in ("ink", "mut", "ok", "warn", "bad"):
            for bg in ("bg", "card", "nav-bg"):
                assert _cr(r[fg], r[bg]) >= bar, (name, fg, bg)
        for fg in ("gold", "accent-ink", "btn-ink"):      # links, outlines
            for bg in ("bg", "card"):
                assert _cr(r[fg], r[bg]) >= 4.5, (name, fg, bg)
        assert _cr(r["nav-ink"], r["nav-bg"]) >= bar, name
        assert _cr(r["accent-ink"], r["nav-bg"]) >= 3.0, name   # the tab
        # field boundaries: 3:1 on both grounds, 4.5:1 with high contrast
        assert _cr(r["field-line"], r["bg"]) >= (4.5 if hc else 3.0), name
        assert _cr(r["field-line"], r["card"]) >= 3.0, name
        if hc:
            for bg in ("bg", "card"):
                assert _cr(r["line"], r[bg]) >= 3.0, (name, bg)
        assert _cr(r["accent-ink"], r["track"]) >= (4.5 if hc else 3.0), name
        # text on fills: primary, danger, the current step, an open toggle
        assert _cr(r["on-accent"], r["gold-bright"]) >= 4.5, name
        assert _cr(r["on-bad"], r["bad"]) >= 4.5, name
        assert _cr(r["card"], r["accent-ink"]) >= 4.5, name
        assert _cr(r["nav-bg"], r["accent-ink"]) >= 4.5, name   # the switch knob
        # graphics: the official comparator, the data accent
        assert _cr(r["official"], r["card"]) >= 3.0, name
        assert _cr(r["slate"], r["card"]) >= 3.0, name
        # the kit's alert: ink and mut on each state's 6% tint
        for tok in ("ok", "warn", "bad", "accent-ink"):
            tint = r["card"] if hc else _mix(r[tok], r["card"], .06)
            assert _cr(r["ink"], tint) >= 4.5, (name, tok)
            assert _cr(r["mut"], tint) >= 4.5, (name, tok)
        # the home hero: white and its lavender line on --navy, the accent
        # word (large text) 3:1
        assert _cr("#FFFFFF", r["navy"]) >= 4.5 and _cr("#C6CFEE", r["navy"]) >= 4.5
        assert _cr(r["gold-bright"], r["navy"]) >= 3.0, name
        seen += 1
    assert seen == 32


def test_series_and_members_hold_3_to_1_on_every_ground():
    members = ("#1979FF", "#A66395")              # player.js pf and pf2s
    for th in ORDER:
        r = resolve(th)
        series = [r[f"season-{i}"] for i in range(1, 7)]
        series += [r[f"season-cvd-{i}"] for i in range(1, 7)]
        for c in series + list(members) + [r["gold"], r["ink"], r["mut"]]:
            for bg in ("bg", "card"):
                assert _cr(c, r[bg]) >= 3.0, (th, c, bg)
        # the status colors keep their 3:1 as graphics with the mode on too
        for v in (False, True):
            rv = resolve(th, vision=v)
            for tok in ("ok", "warn", "bad"):
                assert _cr(rv[tok], rv["card"]) >= 3.0, (th, v, tok)


# ------------------------------------------- simulated color blindness

def test_the_status_triad_stays_apart_for_dichromats():
    """With the mode on: good, warn and bad stay apart for a deuteranope
    and a protanope (and in normal vision), in every theme; the triad beats
    the green/amber/red it replaces. The badge's icon shape carries the
    rest."""
    for th in ORDER:
        base = resolve(th)
        for hc, floor in ((False, (40, 40, 30)), (True, (30, 30, 25))):
            r = resolve(th, hc, True)
            for (a, b), fl in zip((("ok", "bad"), ("ok", "warn"),
                                   ("warn", "bad")), floor):
                assert _de(r[a], r[b]) >= fl, (th, hc, a, b, _de(r[a], r[b]))
        r = resolve(th, vision=True)
        for a, b in (("ok", "bad"), ("warn", "bad")):
            assert _de(r[a], r[b]) > _de(base[a], base[b]), (th, a, b)
    # before this palette the mode left warn amber beside an orange bad:
    # the two merged for a protanope (under 3); now they hold 30+
    assert _de("#8A5A14", "#A34A00") < 3


def test_the_series_stay_apart_in_the_order_charts_take_them():
    """The safe series set, in the order --season-1..6 take it with the
    mode on: every neighbour (charts color seasons newest-first, so a
    neighbour is the next season back) apart under both Machado and both
    Vienot simulations."""
    got = dict(re.findall(r"--season-(\d)\s*:\s*var\(--season-cvd-(\d)\)",
                          NAU.split('[data-vision="cvd"]{', 1)[1]
                          .split("}", 1)[0]))
    order = [int(got[str(i)]) for i in range(1, 7)]
    assert sorted(order) == [1, 2, 3, 4, 5, 6]
    for th in ORDER:
        r = resolve(th, vision=True)
        chart = [r[f"season-{i}"] for i in range(1, 7)]
        assert chart == [r[f"season-cvd-{k}"] for k in order]
        for i in range(6):
            a, b = chart[i], chart[(i + 1) % 6]
            assert _de(a, b, EVERY) >= 40, (th, i, a, b, _de(a, b, EVERY))
        # and against the highlighted (latest) series in the theme's gold
        assert _de(r["gold"], chart[0], EVERY) >= 20, th
    # in literal order the 3rd and 4th (pink, teal) merged for a protanope
    lit = [ROOT[f"season-cvd-{i}"] for i in range(1, 7)]
    assert _de(lit[2], lit[3], (MACHADO_PROTAN,)) < 15


def test_the_map_scale_stays_apart_for_dichromats():
    steps = ("large-decrease", "decrease", "stable", "increase",
             "large-increase")
    for th in ORDER:
        r = resolve(th, vision=True)
        scale = [r["cat-" + s] for s in steps]
        worst = min(_de(a, b, EVERY) for a, b in itertools.combinations(scale, 2))
        classic = [resolve(th)["cat-" + s] for s in steps]
        before = min(_de(a, b, MACHADO[1:])
                     for a, b in itertools.combinations(classic, 2))
        assert worst >= 25, (th, worst)
        assert worst > before, (th, worst, before)
        # no data: apart from the card it sits on and from every step it
        # could be mistaken for (the legend and the hover card name it too)
        nd = r["map-nodata"]
        assert _de(nd, r["card"], (IDENT,)) >= 4, th
        for c in scale + classic:
            assert _de(nd, c, EVERY) >= 5, (th, nd, c)


# ------------------------------------------------------------ the menu

def _menu(html: str) -> str:
    return html.split('<details class="display" id="displaymenu">', 1)[1] \
               .split("</details>", 1)[0]


def test_the_display_menu_is_a_settings_popover():
    html = client.get("/methods").text
    menu = _menu(html)
    assert '<summary aria-label="Display settings">' in menu
    assert 'class="displaypop" role="group" aria-label="Display settings"' in menu
    # four sections, each a heading with its "?" (the kit's heading), no
    # hover-only titles and no loose explanatory sentence
    for sec, name in (("dm-size", "Text size"), ("dm-theme", "Theme"),
                      ("dm-a11y", "Accessibility"), ("dm-zoom", "Zoom")):
        assert f'<h3 id="h-{sec}">{name}</h3>' in menu, sec
        assert f'aria-describedby="tip-{sec}"' in menu, sec
    assert " title=" not in menu
    assert not re.search(r"<p[ >]", menu) and 'class="hint"' not in menu
    # zoom stays hidden until the native window's bridge is up
    assert '<section class="dm-sec zoomrow" hidden>' in menu
    # closing: Escape (focus back to the button), a click outside, and
    # focus moving out of it
    script = BASE_T.split("// the Display menu:", 1)[1].split("})();", 1)[0]
    assert "e.key === 'Escape' && d.open" in script and "s.focus()" in script
    assert "!d.contains(e.target)" in script
    assert "d.addEventListener('focusout'" in script
    assert "!d.contains(e.relatedTarget)" in script


def test_the_text_size_is_a_labelled_slider_from_80_to_160():
    menu = _menu(client.get("/data").text)
    assert ('<input type="range" id="dm-fs" min="80" max="160" step="5" '
            'value="100"') in menu
    assert 'aria-labelledby="h-dm-size" aria-valuetext="100 percent"' in menu
    assert 'data-fs-step="-1" aria-label="Smaller text">A</button>' in menu
    assert 'data-fs-step="1" aria-label="Larger text">A</button>' in menu
    assert 'id="dm-fs-reset" aria-label="Reset text size to 100%">Reset' in menu
    assert '<output class="dm-fs-out" id="dm-fs-out" for="dm-fs"' in menu
    # first paint: a number from 80 to 160, the old s/m/l read as 87.5,
    # 100 and 115 and stored back as numbers
    boot = BASE_T.split("<script>", 1)[1].split("</script>", 1)[0]
    assert "var old={s:87.5,m:100,l:115}" in boot
    assert "if(!(p>=80&&p<=160))p=100;" in boot
    assert "if(old[f])localStorage.setItem('fontsize',String(p));" in boot
    assert "de.style.fontSize=p+'%';" in boot
    # the control clamps, speaks its value and fires fontsizechange once
    # the slider rests
    ctl = BASE_T.split("// text-size control:", 1)[1].split("})();", 1)[0]
    assert "p=Math.max(80,Math.min(160,p));" in ctl
    assert "r.setAttribute('aria-valuetext',t.replace('%',' percent'))" in ctl
    assert "dispatchEvent(new Event('fontsizechange'));},now?0:150);" in ctl


def test_the_theme_picker_is_a_radiogroup_of_previews():
    menu = _menu(client.get("/data").text)
    assert 'class="themepick" role="radiogroup" aria-labelledby="h-dm-theme"' in menu
    radios = re.findall(r'<input type="radio" name="dm-theme" value="([\w-]+)" '
                        r'data-th="\1"', menu)
    assert radios == ORDER
    # each preview draws the theme's ground, header, mark, card, ink and
    # accents from its own tokens; its name is the radio's label, with the
    # ground spoken where the name does not say it
    assert menu.count('<span class="dm-th-logo"></span>') == 8
    assert '<span class="dm-th-name">Nord<span class="uk-sr"> dark theme</span></span>' in menu
    assert '<span class="dm-th-name">GitHub Light</span>' in menu
    # the check mark is drawn in the page's accent, not the preview's
    assert "label.dm-th{--dm-ring:var(--accent-ink);--dm-focus:var(--gold);" in NAU
    assert "label.dm-th input:checked ~ .dm-th-check{display:inline-flex}" in NAU


def test_the_two_modes_are_named_switches_with_their_tips():
    menu = _menu(client.get("/data").text)
    for ax, name, tip in (("contrast", "High contrast", "dm-contrast"),
                          ("vision", "Color-blind safe colors", "dm-vision")):
        btn = menu.split(f'data-ax="{ax}"', 1)
        head = btn[0].rsplit("<button", 1)[1]
        assert 'role="switch" aria-checked="false"' in head, ax
        body = btn[1].split("</button>", 1)[0]
        assert f'aria-describedby="tip-{tip}"' in body, ax
        assert f'<span class="dm-sw-label">{name}</span>' in body, ax
        assert f'role="tooltip" id="tip-{tip}"' in menu, ax
    # the state is drawn three ways: the knob slides, it carries a check,
    # and the word On or Off
    for rule in ('button.dm-switch[aria-checked="true"] .dm-sw-knob{transform',
                 'button.dm-switch[aria-checked="true"] .dm-sw-knob .uk-icon{display:block}',
                 'button.dm-switch[aria-checked="true"] .dm-sw-state::after{content:"On"}',
                 '.dm-sw-state::after{content:"Off"}'):
        assert rule in NAU, rule
    # the tip says what the color-vision mode changes
    tip = menu.split('id="tip-dm-vision">', 1)[1].split("</span>", 1)[0]
    for word in ("status colors", "chart lines", "outlook map", "Okabe",
                 "Icons and words"):
        assert word in tip, word


# ------------------------------------------------------------ the logo

def test_the_header_mark_follows_the_theme():
    html = client.get("/").text
    assert '<span class="mark" aria-hidden="true"></span>' in html
    assert '<link rel="stylesheet" href="/static/brand/logos.css">' in html
    assert ('background:var(--logo,url("/static/brand/pybnf_icon.svg")) '
            'center/contain no-repeat') in NAU
    # one line per theme, each naming a file that ships
    lines = re.findall(r'\[data-theme="([\w-]+)"\][^{]*\{--logo:url\("([^"]+)"\)\}',
                       LOGOS)
    assert [t for t, _ in lines] == ORDER
    icon = (UI / "static" / "brand" / "pybnf_icon.svg").read_text()
    shapes = re.findall(r'\b(?:d|cx|cy|x1|y1)="[^"]+"', icon)
    for th, url in lines:
        path = UI / url.removeprefix("/")
        assert url.startswith("/static/brand/") and path.is_file(), (th, url)
        svg = path.read_text()
        # a recolor keeps the brand icon's drawing exactly
        assert re.findall(r'\b(?:d|cx|cy|x1|y1)="[^"]+"', svg) == shapes, th
        if th in ("github", "solarized", "nord", "dracula"):
            assert url == f"/static/brand/themes/{th}.svg"
            assert "#000F7E" not in svg, th       # recolored, not a copy
    # the favicon stays the brand kit's own
    r = client.get("/favicon.ico")
    assert r.content == (UI / "static" / "brand" / "favicon.ico").read_bytes()
