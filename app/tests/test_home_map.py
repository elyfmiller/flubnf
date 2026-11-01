"""Home's outlook map (bug hunt 2026-10-25, G18).

  * The heading names the round, with the as-of beside it, as Output and
    the report head the same forecast.
  * Without the run's report, no state promises or opens a section of it.
  * The national category, which has no state shape, reads beside the
    coverage, and follows the model toggle.
  * A swipe that starts on the map scrolls the page (a double-tap still
    does not zoom the page: the map's double-click resets its view).
  * The map is named and is not itself a tab stop; its states take Tab in
    name order, and a skip link leads past them.
  * The legend's gray says what the hovers say, and its swatch keeps an
    edge.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import usmap                                     # noqa: E402
from app.ui.routes import home as H                            # noqa: E402
from app.ui.server import templates                            # noqa: E402

STATIC = Path(__file__).resolve().parents[2] / "app" / "ui" / "static"
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

def test_the_legends_gray_says_what_the_hovers_say(monkeypatch):
    assert "not in this run</span>" in usmap.map_legend("not in this run")
    assert ">no data<" in usmap.map_legend()
    # the scope unknown: the hovers say "no data in this view", the legend
    # "no data"; the bundle's scope known: both say "not in this run"
    legend = _block(monkeypatch, has_report=True)["map_svg"]
    assert legend.endswith("no data</span></p></div>")
    monkeypatch.setattr(H, "_outlook_cards",
                        lambda res, rid: (CARDS, {"fitted_fips": ["04", "US"]}))
    legend = H._outlook_block_cached.__wrapped__(None, 0.0, True)["map_svg"] \
        if hasattr(H._outlook_block_cached, "__wrapped__") \
        else H._outlook_block_cached("scoped", 2.0, True)["map_svg"]
    assert legend.endswith("not in this run</span></p></div>")
    assert 'aria-label="Texas: not fitted in this run"' in legend
    css = (STATIC / "nau.css").read_text(encoding="utf-8")
    assert ".maplegend .sw{box-shadow:inset 0 0 0 1px var(--line)}" in css
