"""Methods and the model pages, the review's second S3 pass.

  * ME-03: the submitted one-quarter weight is said beside the registered
    half wherever the blend is stated for the Oracle SIHRS: the Methods
    tile, the pipeline drawing's description and the equation's note (on
    Methods, the Models tab, the Oracle SIHRS page and the public site);
  * MO-20: the two-strain verdict is worded as on its own page ("worse
    than the blend it was tested in"), badge included; "the full grid" is
    said nowhere;
  * MO-23: the strain share's Binomial breaks only after "n," on a phone,
    and each half fits the card at 390 px and 160% text;
  * FC-26: a link to a fold (the Forecast tab's /methods#mt-newest) opens
    it, on arrival and when the address changes;
  * ME-05: a chip clicked for one of the last sections stays marked at the
    page's end while its section is in view, until the reader scrolls;
  * FC-31: the model page's fan keeps its toolbar off on a phone;
  * WI-04: the site build reads the state folder the console writes.

The page scripts run under node: Methods' head script on the stand-in
page of test_methods_polish, the model page's draw() with the stand-ins of
test_dataset_run_chart (both imported, read only).
"""
import json
import os
import re
import subprocess
import sys
from html import unescape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import css_cascade as C                                     # noqa: E402
from app.core import site_build                             # noqa: E402
from app.ui.server import app as srv                        # noqa: E402
from test_methods_polish import (SHORT_END, needs_node,     # noqa: E402
                                 page_tree, run_methods)
import test_dataset_run_chart as RUN                        # noqa: E402

client = TestClient(srv)
REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "app" / "ui" / "templates"
VERSIONS = {k: "x" for k in ("pybnf", "bngsim", "bionetgen", "fastapi",
                             "plotly")}


def _flat(html: str) -> str:
    return " ".join(unescape(html).split())


# ------------------------------------------- ME-03: the submitted quarter

QUARTER = ("the rounds submitted since 2026-10-17 use one quarter on the "
           "filter's growth")


def test_the_submitted_quarter_is_said_beside_the_registered_half():
    site = _flat(site_build.harvest_methods(VERSIONS))
    pages = {p: _flat(client.get(p).text)
             for p in ("/methods", "/models", "/model/pf")}
    for where, t in dict(pages, site=site).items():
        # the equation keeps the registered half; its note says the quarter
        note = t.split("the growth blend: each path's growth", 1)[1]
        note = re.sub(r"<[^>]+>", "", re.split(r"</(?:p|span)>", note, 1)[0])
        assert note.endswith("at the matching earlier-season week W; "
                             + QUARTER), (where, note)
        assert "the registered blend weight, set a priori" in t, where
        # the drawing's description: the weighted mean, both weights
        desc = t.split('<svg class="pipe-h"', 1)[1].split("<desc>", 1)[1]
        desc = desc.split("</desc>", 1)[0]
        assert ("becomes the weighted geometric mean of the filter's growth "
                "and that donor's growth, half and half as registered; "
                + QUARTER + ".") in desc, where
        assert "geometric mean, half and half," not in desc, where
    # the Methods tile: the registered half, the quarter named
    for where, t in (("/methods", pages["/methods"]), ("site", site)):
        tile = t.split('id="mt-blend">', 1)[1].split("</dd>", 1)[0]
        assert tile == ('half and half</span> <span class="uk-stat-u">as '
                        "registered; one quarter on the filter's growth "
                        "since the 2026-10-17 round</span>"), (where, tile)


# ---------------------------------- MO-20: the two-strain verdict, one way

def test_the_two_strain_verdict_is_worded_as_on_its_own_page():
    methods = _flat(client.get("/methods").text)
    page = _flat(client.get("/model/pf2s").text)
    site = _flat(site_build.harvest_methods(VERSIONS))
    said = "worse than the blend it was tested in, in the August 2026 evaluation"
    for where, t in (("/methods", methods), ("/model/pf2s", page),
                     ("site", site)):
        assert "full grid" not in t, where
        assert said in t, where
    why = methods.split('id="mt-2s-why"', 1)[1].split("</details>", 1)[0]
    summary = why.split("</summary>", 1)[0]
    assert re.search(r">\s*worse than the blend it was tested in\s*<", summary), summary
    assert "<p>Stronger at turning points but " + said + "; it stays a research run.</p>" in why


# ------------------------------ MO-23: the Binomial on a phone at 160% text

PHONE, WIDE = 390, 1280
#: an upper bound on each glyph's advance, in em (DM Sans at weight 600 is
#: narrower: B 0.65, A 0.68, m 0.86, s 0.52, a parenthesis 0.33)
_EM = {"m": .9, "w": .8, " ": .3, " ": .25, " ": .2, " ": .12,
       " ": 1.0, "(": .4, ")": .4, "/": .4, ",": .4, ".": .4,
       "{": .4, "}": .4, "+": .65, "∈": .65, "∼": .65, "=": .65}


def _em(text: str) -> float:
    return sum(_EM.get(c, .75 if c.isupper() else .6) for c in text)


def _side(cas, chain, prop, width, root):
    """The left padding (or border) of `chain`'s last element, in px."""
    w = cas.winner(C.path(*chain), (prop, prop + "-left"), width)
    if w is None:
        return 0.0
    parts = C.split_top(cas.resolve(w.value, C.path(*chain), width), " ")
    if prop == "border":
        return C.px(parts[0], root, width)
    side = parts[0] if w.prop.endswith("-left") or len(parts) == 1 else (
        parts[3] if len(parts) == 4 else parts[1])
    return C.px(side, root, width)


def test_the_binomial_breaks_only_between_its_halves_on_a_phone():
    cas = C.Cascade.page("tabs/models.css")
    main = ("html", "body", "main")
    card = main + ("div.card.mech.md-mech",)
    math = card + ("div.eqpanel", "p.uk-figline", "span.math")
    # a phone's equations wrap; the runs marked nw never break inside
    assert cas.value(C.path(*math), "white-space", PHONE) == "normal"
    assert cas.value(C.path(*math), "white-space", WIDE) == "nowrap"
    nw = math + ("span.nw",)
    for width in (PHONE, WIDE):
        assert cas.value(C.path(*nw), "white-space", width) == "nowrap"
    # the card's text width at 390 px and 160% text (about 298 px)
    root = 16 * 1.6
    inner = PHONE - 2 * (_side(cas, main, "padding", PHONE, root)
                         + _side(cas, card, "padding", PHONE, root)
                         + _side(cas, card, "border", PHONE, root))
    assert 280 < inner < 310, inner
    size = C.px(cas.value(C.path(*math), "font-size", PHONE), root, PHONE)
    # every nw run in the two-strain panel fits on one line of the card
    html = client.get("/model/pf2s").text
    panel = html.split("The two circuits the filter fits", 1)[1]
    panel = panel.split('<div class="eqpanel">', 1)[1].split("<details", 1)[0]
    runs = [unescape(re.sub(r"<[^>]+>", "", r))
            for r in re.findall(r'<span class="nw">(.*?)</span>', panel, re.S)]
    assert "Binomial( n," in runs, runs
    assert "share A / (A + B) )" in runs, runs
    for r in runs:
        assert _em(r) * size <= inner, (r, _em(r) * size, inner)
    # the halves sit side by side with one break between them
    assert re.search(r'Binomial\(&#8239;<i>n</i>,</span> <span class="nw">share',
                     panel)


# ------------------------------------- FC-26: a link to a fold opens it

def _holders(tree, target):
    """The ids of the <details> that hold `target`, outermost first."""
    def find(node, path):
        if node.get("id") == target:
            return path
        for k in node["kids"]:
            got = find(k, path + [k])
            if got is not None:
                return got
        return None
    path = find(tree, [])
    assert path is not None, target
    return [n["id"] for n in path if n["tag"] == "details"]


def test_the_forecast_tabs_link_names_a_fold_on_methods():
    forecast = (TEMPLATES / "forecast.html").read_text(encoding="utf-8")
    assert '<a href="/methods#mt-newest">What each choice does</a>' in forecast
    assert '<details class="uk-fold mt-fold" id="mt-newest">' in client.get("/methods").text


@needs_node
def test_a_link_to_a_fold_opens_it_on_arrival_and_when_the_address_changes(tmp_path):
    html = client.get("/methods").text
    tree = page_tree(html)
    holders = _holders(tree, "set-pf-prior-mult")
    assert holders and holders[-1].startswith("mt-set-"), holders
    got = run_methods(tmp_path, [
        {"do": "hash", "to": "#set-pf-prior-mult", "label": "in a fold"},
        {"do": "hash", "to": "#oracle", "label": "a card"},
        {"do": "hash", "to": "#mt-newest", "label": "open already"},
        {"do": "hash", "to": "#no-such-id", "label": "nothing"},
        {"do": "hash", "to": "#%E0%A4%A", "label": "bad escape"},
        {"do": "hash", "to": "#mt-2s%2Dwhy", "label": "escaped"}],
        hash_="#mt-newest", html=html)
    at = {s["label"]: s for s in got}
    folds = set(at["load"]["folds"])
    # on arrival: the named fold opens, alone, and is brought under the bar
    assert at["load"]["folds"]["mt-newest"] is True
    assert [k for k, v in at["load"]["folds"].items() if v] == ["mt-newest"]
    assert at["load"]["scrolled"] == ["mt-newest"]
    # a row inside a fold: every fold that holds it opens
    for h in holders:
        assert at["in a fold"]["folds"][h] is True, h
    assert at["in a fold"]["scrolled"] == ["set-pf-prior-mult"]
    # a card, an open fold, or nothing to find: the browser's own jump
    for label in ("a card", "open already", "nothing", "bad escape"):
        assert at[label]["scrolled"] == [], label
        assert at[label]["folds"] == at["in a fold"]["folds"], label
    assert at["escaped"]["folds"]["mt-2s-why"] is True
    assert at["escaped"]["scrolled"] == ["mt-2s-why"]
    assert len(folds) >= 10, folds


# --------------------------------- ME-05: the chip clicked, at the page end

@needs_node
def test_a_chip_clicked_for_a_last_section_stays_marked_at_the_end(tmp_path):
    got = run_methods(tmp_path, [
        # the one before last: its jump ends at the page's end
        {"do": "click", "href": "#stack", "label": "clicked"},
        # the reader's own scroll (a scroll key, then up) forgets the click
        {"do": "key", "key": "ArrowUp"},
        {"do": "up", "by": 30, "label": "up a little"},
        {"do": "end", "label": "end again"},
        # a click on a chip far above, then the scroll bar to the end: the
        # chip's section is out of view, so the last one is marked
        {"do": "click", "href": "#purpose", "label": "top"},
        {"do": "end", "label": "dragged to the end"},
        # a click at the end already: the jump scrolls nothing, and the
        # chip clicked is marked all the same; the wheel forgets it too
        {"do": "click", "href": "#stack", "label": "clicked again"},
        {"do": "wheel"},
        {"do": "up", "by": 30, "label": "wheeled up"},
        {"do": "end", "label": "wheeled to the end"},
        # the last chip itself
        {"do": "click", "href": "#policies", "label": "last"}],
        layout=SHORT_END)
    at = {s["label"]: s for s in got}
    assert at["clicked"]["atEnd"] and at["clicked"]["current"] == ["#stack"]
    assert at["up a little"]["current"] == ["#performance"]
    assert at["end again"]["current"] == ["#policies"]
    assert at["top"]["current"] == ["#purpose"]
    assert at["dragged to the end"]["current"] == ["#policies"]
    assert at["clicked again"]["current"] == ["#stack"]
    assert at["wheeled up"]["current"] == ["#performance"]
    assert at["wheeled to the end"]["current"] == ["#policies"]
    assert at["last"]["current"] == ["#policies"]
    # with no click, the end marks the last section
    plain = run_methods(tmp_path, [{"do": "end"}], layout=SHORT_END)
    assert plain[-1]["current"] == ["#policies"]


# ------------------------------- FC-31: the model page's toolbar on a phone

FANQ = {"Ohio": {str(h): RUN.QS for h in range(4)}}
SERIES = {"Ohio": {"dates": ["2026-10-03", "2026-10-10", "2026-10-17"],
                   "values": [10.0, 12.0, 15.0]}}

MODEL_DRIVE = r"""
var fetch = function () {
  return Promise.resolve({json: function () { return Promise.resolve(SERIES_); }}); };
"""

MODEL_AFTER = r"""
var out = {before: calls.length};
setTimeout(function () {
  if (LOADING) { out.before = calls.length; listeners.DOMContentLoaded(); }
  setTimeout(function () {
    out.first = calls.length;
    listeners.themechange();
    setTimeout(function () {
      out.configs = calls.map(function (c) { return c.config; });
      console.log(JSON.stringify(out));
    }, 20);
  }, 20);
}, 20);
"""


def _model_script(name: str) -> str:
    html = client.get(f"/model/{name}").text
    bodies = [b for b in re.findall(r"<script>(.*?)</script>", html, re.S)
              if "async function draw()" in b]
    assert len(bodies) == 1
    js = bodies[0]
    for old, new in (("const FANQ = {};", f"const FANQ = {json.dumps(FANQ)};"),
                     ('const FD="";', 'const FD="2026-10-17";')):
        assert js.count(old) == 1, old
        js = js.replace(old, new)
    return js


def _draw(tmp_path, name, width, loading=False):
    drv = tmp_path / f"model-{name}-{width}-{int(loading)}.js"
    drv.write_text(
        f"var TOK = {json.dumps(RUN._tokens('light'))};\n"
        f"var WIDTH = {width};\nvar SERIES_ = {json.dumps(SERIES)};\n"
        f"var LOADING = {json.dumps(loading)};\n"
        + RUN.STUB + MODEL_DRIVE
        + ("document.readyState = 'loading';\n" if loading else "")
        + _model_script(name) + "\n" + MODEL_AFTER, encoding="utf-8")
    out = subprocess.run([RUN.NODE, str(drv)], capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(not RUN.NODE, reason="no node to run the page's script")
@pytest.mark.parametrize("width,phone", [(390, True), (640, True),
                                         (641, False), (1280, False)])
def test_the_model_pages_toolbar_stays_off_on_a_phone(tmp_path, width, phone):
    for name, loading in (("analogue", False), ("pf", True)):
        got = _draw(tmp_path, name, width, loading)
        # the first draw waits for the page when it is still loading
        assert got["before"] == 0 and got["first"] == 1, got
        # the first draw and a redraw (a theme change) alike
        assert len(got["configs"]) == 2
        for conf in got["configs"]:
            assert conf["displayModeBar"] == (False if phone else "hover")
            assert conf["responsive"] is True and conf["displaylogo"] is False
            assert conf["toImageButtonOptions"] == {
                "format": "png", "scale": 2,
                "filename": f"flubnf_{name}_Ohio_2026-10-17"}


# ---------------------------- WI-04: the site build reads the state folder

PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from app.core import site_build as sb
# any bundle counts as covering the country: the folder is what is read
sb._usable_cards = lambda bundle: {"pf": list(range(sb.MIN_OUTLOOK_LOCATIONS))}
rid, bundle, results = sb._newest_run_source()
print(json.dumps({"state": str(sb.APP_STATE), "rid": rid,
                  "roots": [str(p) for _origin, p in sb.ROOT_ORDER]}))
"""


def test_the_site_build_reads_the_state_folder_the_console_writes(tmp_path):
    from app.core import report_v2
    state = tmp_path / "state"
    run = state / "workroots" / "20261017T120000-abcdef"
    run.mkdir(parents=True)
    (run / report_v2.BUNDLE_NAME).write_text(json.dumps(
        {"version": report_v2.SUPPORTED_BUNDLE_VERSIONS[-1]}), encoding="utf-8")
    (run / "results.json").write_text(json.dumps(
        {"forecast_date": "2026-10-17", "models": {"pf": {"Ohio": {}}}}),
        encoding="utf-8")
    env = dict(os.environ, FLUBNF_STATE_DIR=str(state))
    out = subprocess.run([sys.executable, "-c", PROBE, str(REPO)], env=env,
                         cwd=str(tmp_path), capture_output=True, text=True,
                         encoding="utf-8", timeout=120)
    assert out.returncode == 0, out.stderr[-1500:]
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert Path(got["state"]) == state
    assert [Path(p) for p in got["roots"]] == [state / "retro",
                                                state / "retro_seal"]
    assert got["rid"] == run.name
