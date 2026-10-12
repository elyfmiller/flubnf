"""The Retrospective tab's design pass of 2026-10-05: the season list
newest first, the Liu-West filter's headline on a season card, the season
page's grouped verdict, map legend and horizon, the kit's switches, the
player's time window, keys, deep links and memory, the cumulative chart's
spaced end values, the per-state table's names, and the report's header
of evidence."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import retro                                  # noqa: E402
from app.tests.test_retro_pf_name import (                  # noqa: E402,F401
    OTHER, SEASON, W1, W2, _page, _report, _tree, client, world)
from app.tests.test_retro_player import _figs, _season      # noqa: E402

PLAYER = Path(__file__).resolve().parents[1] / "ui" / "static" / "player.js"
SRC = PLAYER.read_text(encoding="utf-8")
NODE = shutil.which("node")


def _js(tmp_path, expr):
    """One expression against the player's internals, under node."""
    both = tmp_path / "both.js"
    both.write_text(SRC + "\nvar I = FluBNFPlayer._internals;\n"
                    "console.log(JSON.stringify((function(){ return "
                    + expr + "; })()));\n", encoding="utf-8")
    out = subprocess.run([NODE, str(both)], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


# ------------------------------------------------------------ the index

def test_the_season_list_runs_newest_first(world):
    _tree(world["live"] / SEASON)
    _tree(world["live"] / OTHER, season=OTHER)
    html = client.get("/retro").text
    # SEASON (2098-99) is the newer: its card leads and the form's select
    # (whose first option is the selected one) offers it first
    assert (html.index(f'data-season="{SEASON}"')
            < html.index(f'data-season="{OTHER}"'))
    opts = re.findall(r'<select name="season" id="rt-season">(.*?)</select>',
                      html, re.S)[0]
    assert opts.index(SEASON) < opts.index(OTHER)
    # on a phone the seasons come before the forms (tabs/retro.css)
    assert 'class="cols rt-cols"' in html and 'class="rt-seasons"' in html


def test_a_season_card_carries_the_liu_west_filter_headline(tmp_path):
    """The card's figures are the page's: the Liu-West filter beside the
    shipped members (display only)."""
    assert retro.HEADLINE_MODELS == ("pf", "pf_filter", "analogue")
    rows = [{"model": m, "location": loc, "wis": w, "base_wis": 2.0,
             "log_wis": w / 10, "base_log_wis": 0.2, "cov50": 1,
             "cov80": 1, "cov95": 1}
            for m, w in (("pf", 1.0), ("pf_filter", 1.2), ("analogue", 1.6))
            for loc in ("Ohio", "Utah")]
    pd.DataFrame(rows).to_json(tmp_path / "scores.json")
    retro._SUMMARY_CACHE.clear()
    s = retro.run_summary(tmp_path)
    assert list(s["headline_rels"]) == ["pf", "pf_filter", "analogue"]
    assert s["headline_rels"]["pf_filter"] == pytest.approx(0.6)
    assert s["headline_rel"] == pytest.approx(0.5)     # pf still leads
    retro._SUMMARY_CACHE.clear()


# ------------------------------------------------------- the season page

def test_the_season_page_wears_the_design_pass(world):
    _tree(world["live"] / SEASON)
    html = _page(SEASON)
    # 2: the map's colors as legend chips, and the horizon it shows
    assert 'aria-label="Categorical forecast colors"' in html
    assert ">large increase</li>" in html and ">no data</li>" in html
    assert '<span class="uk-tag">horizon 0</span>' in html
    # 7: both switches are the kit's, the map's labelled Model
    assert '<div class="uk-seg rt-views" role="group" aria-label="Playback view">' in html
    assert ('<div class="rt-mapbar"><span class="rt-seg-l" aria-hidden="true">'
            'Model</span>') in html
    assert '<div class="uk-seg" id="retro-model"' in html
    # 3: the model checkboxes outside the forecast detail, for both views
    assert html.index('id="fd-models"') < html.index('id="view-map"')
    # 4: the time window, recent first
    assert re.search(r'id="fd-window">\s*<button type="button" data-win="recent" '
                     r'aria-pressed="true">Last 12 weeks</button>', html)
    # 9: the settings line without any timing on record
    assert 'class="rs-settings rt-settings"' in html
    # 12: jurisdictions, never "states", in the count and the filter
    assert "2 jurisdictions scored" in html and "states scored" not in html
    assert 'placeholder="Filter jurisdictions"' in html
    # 15, 16, 17, 18: deep links, keys, memory, month ticks
    assert 'id="pb-copy"' in html and "history.replaceState" in html
    assert "location.hash" in html
    for key in ("<kbd>Space</kbd>", "<kbd>K</kbd>", "<kbd>Home</kbd>",
                "<kbd>M</kbd>", "<kbd>[</kbd>", "<kbd>L</kbd>"):
        assert key in html, key
    assert "window.FluBNFRetroStore" in html
    assert "store: STORE" in html and "initialLoc: LINK.loc" in html
    assert 'class="rt-ticks"' in html
    # 19: each name opens its forecast detail
    assert 'class="rt-locbtn" data-loc="Ohio"' in html
    assert "player.setLoc(b.dataset.loc)" in html
    # 8: the sort is remembered, reset by a button, one group while sorted
    assert 'id="sf-reset" hidden' in html
    assert "store.set('sort'" in html and "if(key)return 1;" in html


def test_the_verdict_groups_its_tiles():
    from app.core import us_national as usn
    fit = usn.UsNational(usn.FITTED, scores={"pf": 0.9, "analogue": 0.58},
                         cells={"pf": 96, "analogue": 96},
                         n_states=52).as_dict()
    html = _season(figs=_figs(), us=fit, us_row=fit)
    v = html.split('<div class="verdict">', 1)[1].split("<div class=\"card playcard", 1)[0]
    pooled = v.split('<h3 id="rs-g-pool">', 1)[1].split("</section>", 1)[0]
    us = v.split('<h3 id="rs-g-us">', 1)[1].split("</section>", 1)[0]
    # the pooled group names its jurisdictions; the US group its provenance
    assert pooled.startswith("1 jurisdiction</h3>")
    assert '<span class="uk-tag">pooled</span>' in pooled
    assert us.startswith("US national</h3>")
    assert '<span class="uk-tag">fitted</span>' in us
    # tiles named by member alone
    assert "<h2>Oracle SIHRS</h2>" in us and "<h2>Groundhog</h2>" in us
    assert "<h2>US (fitted)" not in v


def test_the_cumulative_end_values_never_overprint():
    curves = {"pf": [("2098-11-07", 0.6), ("2098-11-14", 0.5)],
              "pf_filter": [("2098-11-07", 0.6), ("2098-11-14", 0.501)],
              "analogue": [("2098-11-07", 0.6), ("2098-11-14", 0.502)]}
    html = _season(figs=_figs(), curves=curves, curve=curves["pf"],
                   season_models=["pf", "pf_filter", "analogue"])
    ys = sorted(float(y) for y in re.findall(
        r'<text x="637" y="([\d.]+)" data-y0', html))
    assert len(ys) == 3
    assert all(b - a >= 12 - 1e-6 for a, b in zip(ys, ys[1:]))
    # the 1.0 line is named the baseline
    assert ">1.0 baseline</text>" in html


def test_the_report_states_its_evidence(world):
    _tree(world["live"] / SEASON)
    html = _report(SEASON)
    facts = html.split('aria-label="Report facts"', 1)[1].split("</ul>", 1)[0]
    assert f"{W1} to {W2}" in facts
    assert "scored against" in facts and "through" in facts
    assert "build " in facts
    assert 'href="https://github.com/elyfmiller/flubnf"' in facts
    assert 'id="rs-timing"' not in html


# ------------------------------------------------------------- the player

needs_node = pytest.mark.skipif(not NODE, reason="no node")


@needs_node
def test_the_recent_window_spans_twelve_weeks_and_the_horizons(tmp_path):
    assert _js(tmp_path, "I.recentRange('2026-03-28')") == [
        "2026-01-03", "2026-04-28"]
    assert _js(tmp_path, "I.RECENT_WEEKS") == 12


@needs_node
def test_the_recent_window_fits_its_height_to_what_is_inside(tmp_path):
    got = _js(tmp_path, "I.yRangeIn([{x: ['2026-01-01', '2026-02-01',"
                        " '2026-03-01'], y: [900, 100, 50]},"
                        " {x: ['2026-03-07'], y: [200]}],"
                        " '2026-01-15', '2026-03-31')")
    assert got == [0, pytest.approx(224.0)]
    assert _js(tmp_path, "I.yRangeIn([], '2026-01-01', '2026-02-01')") is None


@needs_node
def test_the_location_keys_cycle(tmp_path):
    assert _js(tmp_path, "I.stepLoc(['US', 'Ohio', 'Utah'], 'Utah', 1)") == "US"
    assert _js(tmp_path, "I.stepLoc(['US', 'Ohio', 'Utah'], 'US', -1)") == "Utah"
    assert _js(tmp_path, "I.stepLoc(['US', 'Ohio'], 'Mars', 1)") == "US"


def test_the_player_defaults_and_keys():
    # every member and the official ensemble on at first
    assert ("var dflt = {ensemble: true, pf: true, pf_filter: true, "
            "analogue: true,\n                'FluSight-ensemble': true};") in SRC
    # the forecast detail opens on US unless a link or the memory says
    assert "P.loc = P.loc || 'US';" in SRC
    for k in ("k === 'Home'", "k === 'End'", "k === 'k'", "k === '['",
              "k === 'l'", "k === 'm'", "k === 'f'"):
        assert k in SRC, k
    # Space presses a focused button rather than playing
    assert "if(t === 'BUTTON' || t === 'A' || t === 'SUMMARY') return;" in SRC
    # the modebar off on a phone-width window
    assert "c.displayModeBar = narrowWindow() ? false : 'hover';" in SRC
