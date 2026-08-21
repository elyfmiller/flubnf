"""Retrospective season player: the template renders with the playback
controls, both views, and the live stats table. The player logic itself is
the shared app/ui/static/player.js (one file, loaded by this page and
inlined into the season report), and the combined page-plus-player JS reads
only fields the playback API contract defines."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.ui.server import templates                 # noqa: E402

PLAYER_JS = (Path(__file__).resolve().parents[1] / "ui" / "static"
             / "player.js").read_text()

CONTEXT = dict(
    active="Retrospective", season="2098-99",
    heads={"ensemble": 0.9},
    curve=[("2098-11-07", 0.95), ("2098-11-14", 0.9)],
    states=[{"name": "Ohio", "pf": 0.9, "analogue": 1.1, "ensemble": 0.95}],
    weeks=["2098-11-07", "2098-11-14"], week="2098-11-14",
    map_html="<div id='usmap-wrap'></div>",
    official_catalog=["FluSight-baseline"],
    n_weeks=2, score_error="")


def _render():
    return templates.env.get_template("retro_season.html").render(**CONTEXT)


def test_player_controls_present():
    html = _render()
    # player bar: prev / play-pause / next, speed select, scrubber
    for marker in ('id="pb-prev"', 'id="pb-play"', 'id="pb-next"',
                   'id="pb-speed"', 'id="pb-scrub"', 'id="pb-week"'):
        assert marker in html, marker
    for speed in ('value="500"', 'value="1000"', 'value="2000"'):
        assert speed in html, speed
    # scrubber bound to the week list: max = n-1, initial = index of week
    assert 'max="1"' in html and 'value="1"' in html
    # the page loads the shared player and hands it the live host config
    assert '<script src="/static/player.js"></script>' in html
    assert "FluBNFPlayer.init" in html
    # keyboard stepping lives in the shared player
    assert "ArrowLeft" in PLAYER_JS and "ArrowRight" in PLAYER_JS
    # view tabs and both views
    for marker in ('id="tab-map"', 'id="tab-fc"', 'id="view-map"',
                   'id="view-fc"', "Outlook map", "Forecast detail"):
        assert marker in html, marker
    # forecast detail: location select, model toggles, plot, US labeling
    for marker in ('id="fd-loc"', 'id="fd-models"', 'id="fd-plot"'):
        assert marker in html, marker
    assert "US (official models only)" in PLAYER_JS
    # official models are toggleable alongside ours
    assert "FluSight-baseline" in PLAYER_JS
    assert "FluSight-ensemble" in PLAYER_JS
    # live stats table and the baseline note
    assert 'id="pb-stats"' in html
    assert "beats the CDC FluSight baseline" in html
    # plotly config consistent across hosts, plus scroll zoom and
    # double-click reset
    assert "displaylogo: false" in PLAYER_JS
    assert "scrollZoom: true" in PLAYER_JS
    assert "doubleClick: 'reset'" in PLAYER_JS
    # the server-rendered map for the initial week is embedded
    assert "usmap-wrap" in html


def test_js_reads_only_contract_fields():
    html = _render()
    # the playback endpoint path matches the contract exactly
    assert "/api/retro/" in html and "/playback/" in html
    # every payload access uses the `pl` variable; its fields must all be
    # top-level keys of the contract payload. The page and the shared
    # player are one JS surface, so both are checked together.
    both = html + PLAYER_JS
    contract = {"asof", "locations", "truth", "models", "official", "stats"}
    fields = set(re.findall(r"\bpl\.(\w+)", both))
    assert fields, "expected the player JS to read payload fields via pl.*"
    assert fields <= contract, fields - contract
    # stats entries expose exactly week_rel and cum_rel
    stat_fields = set(re.findall(r"\bst\.(\w+)", both))
    assert stat_fields <= {"week_rel", "cum_rel"}, stat_fields
    assert {"week_rel", "cum_rel"} <= stat_fields
    # our members and the officials all appear as model handles
    for m in ("ensemble", "pf", "analogue", "pf2s",
              "FluSight-baseline", "FluSight-ensemble"):
        assert m in both, m


def test_template_renders_shared_playback_state():
    html = _render()
    # one shared week list drives both views and the stats table
    assert 'const WEEKS = ["2098-11-07", "2098-11-14"]' in html
    assert 'const SEASON = "2098-99"' in html
    # graceful loading and unavailable states are wired in
    assert "unavailable" in html and "loading" in html
    # the live host feeds the player the fetch-backed payload getter and
    # keeps the map view and error text on its side of the config
    for marker in ("getPayload: ensurePayload", "payloadError:",
                   "isCached:", "detailVisible:", "onSeek:", "preload:"):
        assert marker in html, marker


def test_template_passes_season_official_catalog():
    # the server-computed season catalog reaches the player before playback
    # starts, driving the two-tier official toggles
    html = _render()
    assert 'seasonOfficials: ["FluSight-baseline"]' in html
    # render sites that predate the catalog (and any error path that omits
    # it) degrade to an empty list, never a template crash
    ctx = {k: v for k, v in CONTEXT.items() if k != "official_catalog"}
    html2 = templates.env.get_template("retro_season.html").render(**ctx)
    assert "seasonOfficials: []" in html2
