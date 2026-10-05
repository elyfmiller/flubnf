"""The console's design pass on the header, Models, Methods and the
Sandbox: the phone header, the Match system theme, keyboard shortcuts,
the build line, the diagrams' scroll regions and labels, the Models
switcher and record badge, the BNGL source actions, Methods' reading aids
and print, and the sandbox workbench's keyboard and wording fixes.
"""
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import sandbox as sb                       # noqa: E402
from app.ui import server as srv                         # noqa: E402
from app.ui import versions                              # noqa: E402

client = TestClient(srv.app)
UI = Path(srv.__file__).parent
STATIC = UI / "static"
NAU = (STATIC / "nau.css").read_text(encoding="utf-8")
BASE_T = (UI / "templates" / "base.html").read_text(encoding="utf-8")


def _media(css: str, query: str) -> list:
    """The bodies of every @media block whose query contains `query`."""
    out, i = [], 0
    while True:
        i = css.find("@media", i)
        if i < 0:
            return out
        head_end = css.index("{", i)
        if query in css[i:head_end]:
            depth, j = 1, head_end + 1
            while depth:
                depth += {"{": 1, "}": -1}.get(css[j], 0)
                j += 1
            out.append(css[head_end + 1:j - 1])
        i = head_end


# ---------------------------------------------------------- the header

def test_phone_header_wraps_the_tabs_and_shows_the_display_icon_alone():
    html = client.get("/methods").text
    summary = html.split('<summary aria-label="Display settings">', 1)[1].split("</summary>", 1)[0]
    assert '<span class="dm-word">Display</span>' in summary
    phone = "".join(_media(NAU, "max-width:640px"))
    assert "header.nav{flex-wrap:wrap" in phone
    assert "header.nav .navtabs{order:3;flex:1 1 100%;flex-wrap:wrap;overflow:visible" in phone
    # the word stays in the accessibility tree, out of sight
    assert "summary .dm-word{position:absolute;width:1px" in phone


def test_match_system_clears_the_stored_theme_and_follows_the_os():
    html = client.get("/data").text
    assert '<input type="radio" data-sys name="dm-theme" value="system"' in html
    assert ">Match system</span>" in html
    script = BASE_T.split("// theme picker:", 1)[1].split("})();", 1)[0]
    assert "localStorage.removeItem('theme')" in script
    assert "matchMedia('(prefers-color-scheme: dark)')" in script
    assert "mq.addEventListener('change',follow)" in script


def test_keyboard_shortcuts_cover_every_tab_and_skip_typing():
    html = client.get("/").text
    assert 'id="keys-modal"' in html and 'aria-labelledby="keys-title"' in html
    script = BASE_T.split("// keyboard shortcuts:", 1)[1].split("})();", 1)[0]
    keys = dict(re.findall(r"'(/[a-z]*)':'([a-z])'", script))
    hrefs = re.findall(r'<a class="tab[^"]*" href="([^"]+)"', html)
    assert sorted(keys) == sorted(hrefs)                 # every tab has a key
    assert len(set(keys.values())) == len(keys)          # and no key two tabs
    for guard in ("'INPUT'", "'TEXTAREA'", "'SELECT'", "isContentEditable",
                  "e.ctrlKey||e.metaKey||e.altKey"):
        assert guard in script, guard
    assert "e.key==='?'" in script
    # ES5: no arrow functions, let or const in the new script
    assert "=>" not in script and not re.search(r"\b(let|const)\s", script)


def test_build_line_only_when_the_build_is_known(monkeypatch):
    monkeypatch.setattr(versions, "RUNNING_SHA", "")
    assert "FluBNF build" not in client.get("/methods").text
    monkeypatch.setattr(versions, "RUNNING_SHA", "abc1234")
    assert '<footer class="hint buildline">FluBNF build abc1234</footer>' in client.get("/methods").text


def test_zoom_tip_names_ctrl_off_macos():
    assert "ztip.textContent.replace(/Cmd/g,'Ctrl')" in BASE_T


# ------------------------------------------------------------ diagrams

def test_wide_figures_are_labelled_focusable_regions():
    for page in ("/methods", "/models", "/model/analogue", "/model/pf2s"):
        html = client.get(page).text
        figs = re.findall(r'<div class="figscroll[^"]*"([^>]*)>', html)
        assert figs, page
        for attrs in figs:
            assert 'tabindex="0" role="region"' in attrs, (page, attrs)
            assert re.search(r'aria-label="[^"]+ \(scrolls\)"', attrs), (page, attrs)
    assert ".figscroll:focus-visible{outline:" in NAU


def test_gamma_h_is_a_capital_subscript_everywhere():
    for page in ("/methods", "/models", "/model/pf2s"):
        html = client.get(page).text
        assert "&#8341;" not in html and "ₕ" not in html, page
    assert "<dt>&#947;<sub>H</sub></dt>" in (UI / "templates" / "methods.html").read_text()
    assert '&#947;<tspan dy="3" class="svgt-sub">H</tspan>' in client.get("/methods").text


def test_diagram_crops_and_labels():
    html = client.get("/methods").text
    assert '<svg viewBox="0 40 840 308" role="img" aria-label="SIHRS compartment diagram"' in html
    # the two-strain recovery arc is labelled, the H letters a darker slate
    assert html.count("recovery without admission</tspan>") == 2
    assert 'class="dg-h-ink">H' in html
    assert "svg .dg-h-ink{fill:color-mix(in srgb,var(--slate) 55%,var(--ink))}" in NAU
    # the ratio axis has its 1.0 tick, the title its own class
    ratio = html.split('aria-label="Each donor season contributes', 1)[1].split("</svg>", 1)[0]
    assert '<text x="454" y="212">1.0</text>' in ratio
    assert 'class="svgt-md" font-weight="600"' in ratio
    # k = 1..4 never breaks
    assert '<span class="nw"><i>k</i> = 1..4</span>' in html


# --------------------------------------------------------------- Models

def test_switcher_is_links_with_the_current_one_marked():
    t = client.get("/model/analogue").text
    nav = t.split('<nav class="uk-seg uk-seg--quiet md-switch" aria-label="Model view">', 1)[1].split("</nav>", 1)[0]
    assert nav.count("<a href=") == 3 and "<button" not in nav
    assert '<a href="/model/analogue" aria-current="page"' in nav
    kit = (STATIC / "ui-kit.css").read_text()
    quiet = kit.split(".uk-seg--quiet > button[aria-pressed=\"true\"],.uk-seg--quiet > [aria-current]{", 1)[1].split("}", 1)[0]
    assert "gold-bright" not in quiet and "color:var(--ink)" in quiet


def test_source_actions_and_the_skip_link():
    pf = client.get("/models").text
    assert '<a class="skip" href="#h-md-quick">Skip to Quick run</a>' in pf
    assert 'id="h-md-quick"' in pf
    assert 'id="md-src-copy">Copy</button>' in pf
    assert 'id="md-src-dl" download="SIHRS_pop_min.bngl"' in pf
    assert 'href="/sandbox?start=shipped:sihrs#sbnew-start">Open in Sandbox</a>' in pf
    p2 = client.get("/model/pf2s").text
    assert "Open in Sandbox" not in p2                   # no shipped start for it
    assert "Skip to Quick run" not in p2                 # nor a quick run


def test_sandbox_preselects_a_start_from_the_query():
    js = (STATIC / "sandbox.js").read_text()
    assert "/[?&]start=([^&#]*)/.exec(location.search)" in js
    assert "o.value === want && !o.disabled" in js


# -------------------------------------------------------------- Methods

def test_methods_reading_aids_are_console_only():
    from app.core import site_build
    tab = client.get("/methods").text
    for needle in ("IntersectionObserver", "setAttribute('aria-current', 'location')",
                   "'Copy a link to '", "Print / Save as PDF", "beforeprint", "afterprint"):
        assert needle in tab, needle
    site = site_build.harvest_methods({k: "x" for k in ("pybnf", "bngsim", "bionetgen",
                                                        "fastapi", "plotly")})
    assert "IntersectionObserver" not in site and "mt-print" not in site
    # the phone's drawing too
    assert 'class="pipe-v"' in tab and 'class="pipe-v"' not in site


def test_methods_css_phone_toc_and_print():
    css = (STATIC / "tabs" / "methods.css").read_text()
    phone = "".join(_media(css, "max-width:640px"))
    assert ".mt-toc{flex-wrap:nowrap;overflow-x:auto" in phone
    assert "scroll-margin-top:calc(var(--mt-toc-h,4.3rem) + .5rem)" in css
    printed = "".join(_media(css, "print"))
    for rule in ("header.nav,.mt-tocbar", ".tipbtn,.uk-tt-btn", "break-inside:avoid"):
        assert rule in printed, rule
    # the section titles: larger than the sub-headings, sentence case, ink
    assert ".mt-doc .card > h2,.mt-doc .card > .uk-heading > h2{font-size:var(--fs-lead);" in css


# -------------------------------------------------------------- Sandbox

def test_workbench_wording_names_and_tabs(sandbox_root):
    sb.add_example("sir_example", as_name="mine")
    html = client.get("/sandbox?model=mine").text
    assert 'aria-label="Model (model.bngl)"' in html
    assert 'aria-label="Observed data (data.exp)"' in html
    assert 'aria-label="Priors and engine settings (priors.conf)"' in html
    assert "Posterior" not in html and "posterior" not in html
    assert 'role="tabpanel" aria-labelledby="mv-tab-flow"' in html
    js = (STATIC / "sandbox.js").read_text()
    assert "(e.key || '').toLowerCase() !== 's'" in js and "saveBtn.click()" in js
    ed = (STATIC / "bngl-editor.js").read_text()
    assert "'  |  Esc then Tab to leave'" in ed


def test_a_copy_is_changed_when_it_is_made(sandbox_root):
    sb.add_example("sir_example", as_name="old")
    long_ago = time.time() - 86400 * 30
    for f in sb.REQUIRED:
        os.utime(sb.MODELS / "old" / f, (long_ago, long_ago))
    sb.copy_model("old", "new")
    rows = {m["name"]: m["modified"] for m in sb.list_models()}
    assert rows["new"] > long_ago + 86400
    assert rows["old"] <= long_ago + 1


def test_quips_say_neither_posterior_nor_burning_in():
    src = (STATIC / "quips.js").read_text().lower()
    assert "posterior" not in src and "burning in" not in src
