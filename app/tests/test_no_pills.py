"""No control is drawn as a pill (review 2026-11-27, B21, M-E16, G-U3, G-U4).

The console's choices are the UI kit's: a segmented switch (uk-seg), a
select, a checkbox, a plain link, or a fold's own row (chevron and words).
Rounded pills beside them made the same kind of choice look different from
page to page, and the open Model settings toggle, a filled pill in the Run
button's colour, read as a second primary action.

Each console page is rendered, parsed (served_dom.tree) and every button,
link, fold summary and input button in it, <template> contents included, is
put to the cascade of the stylesheets the page links, in their order
(css_cascade): none may get the pill radius. A summary is asked closed and
open. The relWIS scale switch, which player.js writes into the season
page, is checked in the host it is written into. A second check reads the
stylesheets themselves: a rule that gives the pill radius is a bar or a
track named below, so a new pill cannot arrive by a class no page renders
yet.
"""
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import css_cascade as C                                  # noqa: E402
import served_dom as SD                                  # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.ui.server import app as srv, templates          # noqa: E402
from test_player_js import _js, needs_jsc                # noqa: E402
from test_retro_player import CONTEXT as SEASON          # noqa: E402

client = TestClient(srv)
STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"

#: the console's pages, as a fresh install renders them
PAGES = ("/", "/data", "/forecast", "/forecast?tab=own", "/output",
         "/output/report", "/retro", "/storage", "/models", "/model/pf",
         "/model/analogue", "/model/pf2s", "/methods", "/sandbox")
RADII = ("border-radius", "border-top-left-radius", "border-top-right-radius",
         "border-bottom-left-radius", "border-bottom-right-radius")
#: a corner this round on a control is a pill (the kit's controls take
#: --r-sm, 8px; --r-pill is 99px); a circle's 50% is not a length here
PILL_PX = 30.0
INPUT_BUTTONS = {"button", "submit", "reset", "image"}


def _pressable(node: dict) -> bool:
    tag, a = node["tag"], node["attrs"]
    if tag in ("button", "a", "summary"):
        return True
    if tag == "input" and a.get("type", "").lower() in INPUT_BUTTONS:
        return True
    return a.get("role") in ("button", "link", "tab", "switch")


def _el(node: dict, extra: dict | None = None) -> C.El:
    a = dict(node["attrs"])
    a.update(extra or {})
    return C.El(tag=node["tag"], id=a.get("id", ""),
                classes=frozenset(a.get("class", "").split()), attrs=a)


def _sheets(root: dict) -> list:
    """The /static/ stylesheets the page links, in document order, once."""
    out = []

    def walk(n):
        for k in n["kids"]:
            if isinstance(k, str):
                continue
            a = k["attrs"]
            if (k["tag"] == "link" and "stylesheet" in a.get("rel", "").split()
                    and a.get("href", "").startswith("/static/")):
                name = a["href"][len("/static/"):].split("?")[0]
                if name not in out:
                    out.append(name)
            walk(k)
    walk(root)
    return out


def _radius_px(cas: C.Cascade, chain: list) -> float:
    """The largest corner the cascade gives the last element of `chain`,
    in px; 0 for none, a percentage, or a value it cannot size."""
    win = cas.winner(chain, RADII)
    if win is None:
        return 0.0
    value = win.value.strip()
    if value == "inherit":
        return _radius_px(cas, chain[:-1]) if len(chain) > 1 else 0.0
    value = cas.resolve(value, chain)
    best = 0.0
    for part in value.replace("/", " ").split():
        if part.endswith("%"):
            continue
        try:
            best = max(best, C.px(part))
        except (ValueError, KeyError, SyntaxError):
            continue
    return best


def _inline_pill(node: dict) -> bool:
    style = node["attrs"].get("style", "")
    m = re.search(r"border(?:-[a-z]+)*-radius\s*:\s*([^;]+)", style)
    if not m:
        return False
    return any(not p.endswith("%") and C.px(p) >= PILL_PX
               for p in m.group(1).replace("/", " ").split()
               if re.fullmatch(r"[\d.]+(px|rem|em)", p))


def _pills(html: str, cas: C.Cascade | None = None) -> list:
    """Each pressable element of the page that gets the pill radius, as
    'tag#id.class [text]' (a summary also when its fold is open)."""
    root = SD.tree(html)
    cas = cas or C.Cascade(*_sheets(root))
    found = []

    def text(n):
        return " ".join("".join(
            k if isinstance(k, str) else text(k) for k in n["kids"]).split())

    def name(n):
        a = n["attrs"]
        return (n["tag"] + ("#" + a["id"] if a.get("id") else "")
                + "".join("." + c for c in a.get("class", "").split())
                + f" [{text(n)[:40]}]")

    def walk(n, chain, nodes):
        for k in n["kids"]:
            if isinstance(k, str):
                continue
            here = chain + [_el(k)]
            if _pressable(k):
                variants = [here]
                if k["tag"] == "summary" and nodes and nodes[-1]["tag"] == "details":
                    variants.append(chain[:-1] + [_el(nodes[-1], {"open": ""}),
                                                  _el(k)])
                if (any(_radius_px(cas, v) >= PILL_PX for v in variants)
                        or _inline_pill(k)):
                    found.append(name(k))
            walk(k, here, nodes + [k])

    walk(root, [], [])
    return found


@pytest.mark.parametrize("url", PAGES)
def test_no_button_link_or_fold_toggle_on_a_page_is_a_pill(url):
    r = client.get(url)
    assert r.status_code == 200, url
    assert _pills(r.text) == [], url


def test_the_sandbox_editor_has_no_pill(sandbox_root):
    # the diagram's view tabs (Model, Binding sites, Reaction network)
    sb.new_model("mine")
    html = client.get("/sandbox?model=mine").text
    assert 'class="mviews uk-seg" role="tablist"' in html
    assert _pills(html) == []


@needs_jsc
def test_the_season_page_and_its_scale_switch_have_no_pill(tmp_path):
    html = templates.env.get_template("retro_season.html").render(**SEASON)
    assert _pills(html) == []
    # the relWIS scale switch, as player.js writes it into its host
    host = '<div class="pbscale" id="pb-scale"></div>'
    assert html.count(host) == 1
    for scale in ("natural", "log"):
        switch = _js(tmp_path, f"I.scaleSwitch('{scale}')")
        assert '<span class="uk-seg" role="group"' in switch
        filled = html.replace(host, host[:-6] + switch + "</div>")
        assert _pills(filled) == [], scale


def test_the_check_finds_a_pill():
    # the check itself: a pill rule from a page's sheet, a summary that
    # turns into a pill only when its fold opens, and an inline style
    page = ('<html><head><link rel="stylesheet" href="/static/nau.css">'
            '</head><body><div class="x">'
            '<button type="button" class="seg-old">A</button>'
            '<a href="#y" style="border-radius:999px">B</a>'
            '<details class="adv"><summary class="advbtn">C</summary></details>'
            '<button type="button">D</button></div></body></html>')
    css = (".x .seg-old{border-radius:var(--r-pill)}"
           ".adv[open] > summary.advbtn{border-radius:999px}")
    cas = C.Cascade("nau.css")
    cas.rules += C.parse(css, "test.css")
    for i, r in enumerate(cas.rules):
        r.order = i
    assert _pills(page, cas) == [
        "button.seg-old [A]", "a [B]", "summary.advbtn [C]"]


#: every rule in the console's sheets that gives the pill radius, by sheet
#: and selector: bars, tracks and meters, which nobody presses. A rule for
#: a control has no place here; draw the control with the kit instead
PILL_RULES = {
    ("nau.css", "progress"), ("nau.css", "progress::-webkit-progress-bar"),
    ("nau.css", "progress::-webkit-progress-value"),
    ("nau.css", "progress::-moz-progress-bar"),
    ("nau.css", ".runbar"), ("nau.css", ".runbar div"),
    ("nau.css", ".dm-sw-track"),
    ("ui-kit.css", ".uk-progress-track"), ("ui-kit.css", ".uk-progress-fill"),
    ("tabs/models.css", ".md-bar-track"),
    ("tabs/storage.css", ".st-bar"),
}


def _all_sheets():
    for p in sorted(STATIC.rglob("*.css")):
        if "fonts" in p.parts:
            continue
        yield p.relative_to(STATIC).as_posix()


def test_only_bars_and_tracks_take_the_pill_radius():
    root = C.Cascade("nau.css")              # the tokens: --r-pill
    html = C.path("html")
    seen = set()
    for name in _all_sheets():
        for rule in C.parse((STATIC / name).read_text(encoding="utf-8"), name):
            for prop, value, _imp in rule.decls:
                if prop not in RADII:
                    continue
                value = root.resolve(value, html)
                sizes = [C.px(p) for p in value.replace("/", " ").split()
                         if re.fullmatch(r"[\d.]+(px|rem|em)", p)]
                if not sizes or max(sizes) < PILL_PX:
                    continue
                for sel in rule.selectors:
                    seen.add((name, " ".join(sel.split())))
    assert seen - PILL_RULES == set(), "a new pill rule"
    # a listed rule that no longer gives the pill radius leaves the list
    assert PILL_RULES - seen == set(), "a listed rule is gone"
