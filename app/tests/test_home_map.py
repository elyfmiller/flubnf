"""Home's outlook map (bug hunt 2026-10-25, G18).

  * The heading names the round, with the as-of beside it, as Output and
    the report head the same forecast.
  * Without the run's report, no state promises or opens a section of it.
  * The national category, which has no state shape, reads beside the
    coverage, and follows the model toggle: the line is there when any
    model the toggle shows has one, and reads "no forecast" for a model
    without one (run under node; skipped where node is absent).
  * A swipe that starts on the map scrolls the page (a double-tap still
    does not zoom the page: the map's double-click resets its view).
  * The map is named and is not itself a tab stop; its states take Tab in
    name order, and a skip link leads past them.
  * The legend's gray says what the hovers say (outside the run, no
    forecast, or both, for every model the toggle shows), and its swatch
    keeps an edge that shows on the card in every theme.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import css_cascade                                             # noqa: E402
from app.core import usmap                                     # noqa: E402
from app.ui import server as srv                               # noqa: E402
from app.ui.routes import home as H                            # noqa: E402
from app.ui.server import templates                            # noqa: E402

client = TestClient(srv.app)

PROBS = {"large_decrease": .02, "decrease": .12, "stable": .45,
         "increase": .30, "large_increase": .11}
CARDS = {"04": {"abbr": "AZ", "name": "Arizona", "probs": PROBS,
                "hover_html": "<b>Arizona</b>"},
         "US": {"abbr": "US", "name": "United States", "probs": PROBS,
                "hover_html": "<b>United States</b>"}}


def _home(**kw):
    ctx = dict(active="Home", map_svg="<svg></svg>", outlook_date="2026-10-17",
               outlook_n=1, missing=[],
               versions={"pybnf": "x", "bngsim": "0.15.1", "bionetgen": "x",
                         "perl": "x", "fastapi": "x", "plotly": "x"})
    ctx.update(kw)
    return templates.env.get_template("home.html").render(**ctx)


def _block(monkeypatch, has_report):
    monkeypatch.setattr(H, "_outlook_cards", lambda res, rid: (CARDS, {}))
    monkeypatch.setattr(H, "_outlook_models", lambda rid: {})
    return H._outlook_block_cached.__wrapped__(None, 0.0, has_report) \
        if hasattr(H._outlook_block_cached, "__wrapped__") \
        else H._outlook_block_cached(f"t{has_report}", 1.0, has_report)


# ---------------------------------------------------------- HM-02: the round

def test_the_heading_names_the_round_with_its_as_of():
    html = _home(outlook_ref="2026-10-24")
    assert ("US categorical forecast · Round 2026-10-24 (as of 2026-10-17)"
            in html)


# -------------------------------------------- HM-03: no report, no promise

def test_without_the_report_no_state_promises_or_opens_it(monkeypatch):
    bare = _block(monkeypatch, has_report=False)["map_svg"]
    assert "window.MAP_LINK='/output/report'" not in bare
    assert "click for details" not in bare
    assert 'role="button"' not in bare
    full = _block(monkeypatch, has_report=True)["map_svg"]
    assert "MAP_LINK='/output/report'" in full and "click for details" in full
    html = _home(outlook_report=False)
    assert "click one" not in html
    assert '<span class="uk-tt-line">Hover a state for its numbers.</span>' \
        in html


# ------------------------------------------- HM-04: the national category

def test_the_national_category_reads_beside_the_coverage(monkeypatch):
    assert _block(monkeypatch, has_report=True)["outlook_us"] == "stable 45%"
    assert H._us_words({"probs": {}}) == "" and H._us_words(None) == ""
    html = _home(outlook_n=0, outlook_us="stable 45%")
    assert ('<span class="uk-stat-v" id="hm-us"><span data-us-words>stable 45%'
            '</span></span>') in html
    assert "data-us-words" not in _home(outlook_n=0)
    # with a model toggle the line follows the pressed model
    html = _home(outlook_us="stable 45%", outlook_toggle="<div id='outlook-model'></div>",
                 outlook_us_by_model={"pf": "increase 52%", "analogue": "stable 45%"})
    script = html.split("the national line follows the model toggle", 1)[1]
    assert '"pf": "increase 52%"' in script and "v.textContent = W[b.dataset.mmodel]" in script


#: runs the national line's toggle script (stdin: {src, clicks}) with a
#: stand-in for the toggle group and the line; prints the line's words
#: after each click (a model's button, or null for a click beside them)
_US_RUNNER = r"""
const vm = require('vm');
const job = JSON.parse(require('fs').readFileSync(0, 'utf8'));
let onClick = null;
const words = {textContent: job.initial};
const group = {addEventListener: (t, fn) => { if (t === 'click') onClick = fn; }};
const ctx = {document: {
  getElementById: id => (id === 'outlook-model' ? group : null),
  querySelector: s => (s === '[data-us-words]' ? words : null)}};
vm.createContext(ctx);
vm.runInContext(job.src, ctx);
const seen = [];
for (const m of job.clicks) {
  const b = m === null ? null : {dataset: {mmodel: m}};
  onClick({target: {closest: s => (s === 'button[data-mmodel]' ? b : null)}});
  seen.push(words.textContent);
}
process.stdout.write(JSON.stringify(seen));
"""


def _us_words_after(html, clicks):
    """The national line's words after each click, from the page's own
    toggle script run under node."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    src = next(c.split("</script>", 1)[0] for c in html.split("<script>")
               if "the national line follows the model toggle" in c)
    initial = re.search(r"<span data-us-words>(.*?)</span>", html).group(1)
    job = json.dumps({"src": src, "initial": initial, "clicks": clicks})
    out = subprocess.run([node, "-e", _US_RUNNER], input=job, text=True,
                         capture_output=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout)


@pytest.fixture()
def outlook_page(tmp_path, monkeypatch):
    """GET / for a run whose map shows these cards (the default model's),
    these per-model cards on the toggle and this bundle meta; the outlook
    is built fresh, never from its cache."""
    from app.core import runs
    from app.ui import shared, state
    # the startup warm pass builds an outlook too: it finishes first
    assert state._WARM_DONE.wait(60)
    rid = "hm04"
    run = tmp_path / "workroots" / rid
    run.mkdir(parents=True)
    (run / "results.json").write_text('{"forecast_date": "2026-10-17"}',
                                      encoding="utf-8")
    monkeypatch.setattr(runs, "APP_STATE", tmp_path)
    monkeypatch.setattr(shared, "_latest_results",
                        lambda: (rid, {"forecast_date": "2026-10-17"}))
    monkeypatch.setattr(H, "_outlook_ready", lambda: True)
    monkeypatch.setattr(H, "_outlook_block", lambda r: H._outlook_block_cached
                        .__wrapped__(r, 0.0, False))

    def page(cards, models, meta):
        monkeypatch.setattr(H, "_outlook_cards", lambda res, r: (cards, meta))
        monkeypatch.setattr(H, "_outlook_models", lambda r: models)
        return client.get("/").text
    return page


def test_the_national_line_follows_the_toggle_when_any_model_has_one(outlook_page):
    states = {k: v for k, v in CARDS.items() if k != "US"}
    up = {"large_decrease": .02, "decrease": .06, "stable": .30,
          "increase": .52, "large_increase": .10}
    us_up = dict(CARDS["US"], probs=up)
    meta = {"model": "pf", "label": "Oracle SIHRS"}
    # the default model has no national forecast, the other one has: the
    # line is there, reads "no forecast", and the toggle switches it
    html = outlook_page(states, {"pf": states, "analogue": CARDS}, meta)
    assert 'data-mmodel="pf"' in html and 'data-mmodel="analogue"' in html
    assert ('<span class="uk-stat-v" id="hm-us"><span data-us-words>'
            'no forecast</span></span>') in html
    script = html.split("the national line follows the model toggle", 1)[1]
    assert '"analogue": "stable 45%"' in script and '"pf": ""' in script
    assert _us_words_after(html, ["analogue", "pf", None, "analogue"]) == [
        "stable 45%", "no forecast", "no forecast", "stable 45%"]
    # the default model has one, the other none: toggled to it, the line
    # says so, never the other model's words
    html = outlook_page(dict(states, US=us_up),
                        {"pf": dict(states, US=us_up), "analogue": states},
                        meta)
    assert "<span data-us-words>increase 52%</span>" in html
    assert _us_words_after(html, ["analogue", "pf"]) == [
        "no forecast", "increase 52%"]
    # both have one: each model's own words
    html = outlook_page(CARDS, {"pf": CARDS, "analogue": dict(CARDS, US=us_up)},
                        meta)
    assert _us_words_after(html, ["analogue", "pf"]) == [
        "increase 52%", "stable 45%"]
    # neither has one: no line and no script
    html = outlook_page(states, {"pf": states, "analogue": states}, meta)
    assert "data-us-words" not in html and 'id="hm-us"' not in html
    assert "the national line follows the model toggle" not in html


# ------------------------------------------ HM-07, HM-16: touch and the keys

def test_the_map_lets_a_swipe_scroll_and_walks_its_states_by_name():
    svg = usmap.svg_map({})
    head = svg.split("<svg", 1)[1].split(">", 1)[0]
    assert "touch-action:manipulation" in head and "touch-action:none" not in head
    assert 'role="group"' in head and 'aria-label="Map of the states"' in head
    assert 'tabindex="-1"' in head
    names = [usmap.state_paths()[f][0] for f in
             re.findall(r'data-fips="(\w+)"', svg)]
    assert names == sorted(names)
    html = _home(outlook_report=True, outlook_n=52)
    assert '<a class="skip" href="#hm-map-end">Skip the map</a>' in html
    assert 'id="hm-map-end" tabindex="-1"' in html
    assert "Skip the map" not in _home(outlook_report=False)


# --------------------------------------------------------- HM-18: the legend

def _scoped(monkeypatch, meta, models=None):
    """The outlook block for CARDS under this bundle meta (and these
    per-model cards for the toggle), never from the cache."""
    monkeypatch.setattr(H, "_outlook_cards", lambda res, rid: (CARDS, meta))
    monkeypatch.setattr(H, "_outlook_models", lambda rid: models or {})
    return H._outlook_block_cached.__wrapped__(None, 0.0, True)


def _gray(block):
    """The legend's last item: the words beside the plain gray swatch."""
    legend = block["map_svg"].rsplit('<p class="hint maplegend">', 1)[1]
    assert legend.endswith("</span></p></div>")
    return legend.rsplit("</span>", 2)[-2]


def test_the_legends_gray_says_what_the_hovers_say(monkeypatch):
    assert "not in this run</span>" in usmap.map_legend("not in this run")
    assert ">no data<" in usmap.map_legend()
    # the scope unknown: the hovers say "no data in this view", the legend
    # "no data"; the bundle's scope known: both say "not in this run"
    legend = _block(monkeypatch, has_report=True)["map_svg"]
    assert legend.endswith("no data</span></p></div>")
    block = _scoped(monkeypatch, {"fitted_fips": ["04", "US"]})
    legend = block["map_svg"]
    assert legend.endswith("not in this run</span></p></div>")
    assert _gray(block) == "not in this run"
    assert 'aria-label="Texas: not fitted in this run"' in legend


def test_the_gray_also_names_a_state_in_the_run_with_no_forecast(monkeypatch):
    # California is in the run's scope and was reported, but the model made
    # no forecast for it: it wears the plain gray and its hover says "no
    # forecast", so the legend may not call all of the gray "not in this run"
    meta = {"fitted_fips": ["04", "06", "US"], "gap_fips": [], "model": "pf"}
    block = _scoped(monkeypatch, meta)
    assert ('aria-label="California: no forecast from this model this week"'
            in block["map_svg"])
    assert 'aria-label="Texas: not fitted in this run"' in block["map_svg"]
    assert _gray(block) == "not in this run or no forecast"
    # a reporting gap wears the hatch, not the gray: the words stay
    gap = _scoped(monkeypatch, dict(meta, gap_fips=["06"]))
    assert 'aria-label="California: no data" data-gap="1"' in gap["map_svg"]
    assert _gray(gap) == "not in this run"
    # every state in the run: the gray is only ever "no forecast"
    every = sorted(usmap.state_paths()) + ["US"]
    full = _scoped(monkeypatch, dict(meta, fitted_fips=every))
    assert "not fitted in this run" not in full["map_svg"]
    assert _gray(full) == "no forecast"


def test_the_grays_words_cover_the_model_the_toggle_shows(monkeypatch):
    # the pressed model has a forecast for each state in the run, the other
    # one not for California: toggled to it, California turns the plain gray
    meta = {"fitted_fips": ["04", "06", "US"], "gap_fips": [], "model": "pf"}
    ca = {"abbr": "CA", "name": "California", "probs": PROBS,
          "hover_html": "<b>California</b>"}
    cards = dict(CARDS, **{"06": ca})
    monkeypatch.setattr(H, "_outlook_cards", lambda res, rid: (cards, meta))
    models = {"pf": cards, "analogue": dict(CARDS)}
    monkeypatch.setattr(H, "_outlook_models", lambda rid: models)
    block = H._outlook_block_cached.__wrapped__(None, 0.0, True)
    assert "outlook-model" in block["toggle"]
    assert _gray(block) == "not in this run or no forecast"
    # both models forecast California: out of scope is all the gray is
    models["analogue"] = cards
    block = H._outlook_block_cached.__wrapped__(None, 0.0, True)
    assert _gray(block) == "not in this run"


def _swatch(theme, contrast=""):
    """The gray swatch under the map, from the root down (home.html)."""
    root = f'html[data-theme="{theme}"]' + (
        f'[data-contrast="{contrast}"]' if contrast else "")
    return css_cascade.path(root, "body", "main", "div.card.hm-outlook",
                            "div.hm-stage", "div.hm-mapbox",
                            "p.hint.maplegend", "span", "span.sw")


def test_the_gray_swatchs_edge_shows_on_the_card_in_every_theme():
    # the swatch is near the card's own color: its edge is what shows it.
    # The rule that wins the cascade (not merely a rule in the file) draws
    # an edge whose color has 3:1 on the card in all eight themes, with and
    # without High contrast; --line, which it had, has 1.3 to 1.6
    cas = css_cascade.Cascade.page("tabs/home.css")
    themes = css_cascade.themes()
    assert len(themes) == 8
    for theme in themes:
        for mode in ("", "high"):
            chain = _swatch(theme, mode)
            for width in (390, 1280):
                win = cas.winner(chain, "box-shadow", width)
                assert win, (theme, mode)
                shadow = cas.resolve(win.value, chain, width)
                m = re.fullmatch(r"inset 0 0 0 (\d+)px (#[0-9A-Fa-f]{3,6})",
                                 shadow)
                assert m and int(m.group(1)) >= 1, (theme, mode, shadow)
                card = cas.token(chain, "--card", width)
                ratio = css_cascade.contrast(m.group(2), card)
                assert ratio >= 3.0, (theme, mode, m.group(2), card, ratio)
