"""Retrospective season player: the template renders with the playback
controls, both views, and the live stats table. The player logic itself is
the shared app/ui/static/player.js (one file, loaded by this page and
inlined into the season report), and the combined page-plus-player JS reads
only fields the playback API contract defines."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import us_national                    # noqa: E402
from app.ui.server import templates                 # noqa: E402

PLAYER_JS = (Path(__file__).resolve().parents[1] / "ui" / "static"
             / "player.js").read_text(encoding="utf-8")

#: the resolved US national answer the server hands the page: this one is
#: the sum-of-states FALLBACK, which the page and the player must label as
#: a fallback rather than as a national forecast
US_AGG = us_national.UsNational(
    us_national.AGGREGATED,
    scores={"pf": 0.9, "analogue": 1.05, "ensemble": 0.92},
    cells={"pf": 96, "analogue": 96, "ensemble": 96},
    n_states=52).as_dict()

CONTEXT = dict(
    active="Retrospective", season="2098-99",
    heads={"ensemble": 0.9},
    curve=[("2098-11-07", 0.95), ("2098-11-14", 0.9)],
    states=[{"name": "Ohio", "pf": 0.9, "analogue": 1.1, "ensemble": 0.95}],
    weeks=["2098-11-07", "2098-11-14"], week="2098-11-14",
    map_html="<div id='usmap-wrap'></div>",
    official_catalog=["FluSight-baseline"],
    us=US_AGG, us_row=US_AGG,
    pooled_note=us_national.POOLED_SCOPE_NOTE,
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
    # US labelling: the entry text is no longer a hardcoded string but is
    # driven by the resolved provenance, and all three states are spelled
    # out in the player so no host can invent a fourth. The fallbacks are
    # visibly fallbacks: neither reads as a plain fitted national forecast.
    assert """'<option value="US">' + usLabel(cfg.us) + '</option>'""" \
        in PLAYER_JS
    assert "US (official models only)" in PLAYER_JS       # officials only
    assert "US national (fitted)" in PLAYER_JS            # a real US fit
    assert "US national (sum of states)" in PLAYER_JS     # the aggregate
    # the host resolves the provenance and hands it to the player, which
    # is how the page can label a fitted US differently from a fallback
    assert "us: {" in html
    assert "US national (sum of 52 states)" in html
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
    assert stat_fields <= {"week_rel", "cum_rel", "debug"}, stat_fields
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


def test_us_entry_names_its_provenance_and_flags_the_fallback():
    """A fitted US national forecast and the sum-of-states aggregate are
    different model outputs. Every US surface on this page says which one
    it holds, and a fallback is visibly a fallback."""
    # the aggregated case (CONTEXT): the tile, the table row, and the
    # player entry all carry the fallback wording, and the pooled scope is
    # stated so nobody reads the US figure as part of the headline
    fallback_claim = "no US fit exists for this season"
    html = _render()
    assert "US (aggregated)" in html                 # tile and table row
    assert "US national (sum of 52 states)" in html  # the player entry
    assert fallback_claim in html
    assert "not a fitted national forecast" in html
    assert "never joins the pooled average" in html
    assert "US (fitted)" not in html

    # the fitted case: the same surfaces, no fallback claim anywhere
    fit = us_national.UsNational(
        us_national.FITTED,
        scores={"pf": 0.8, "analogue": 1.0, "ensemble": 0.85},
        cells={"pf": 96, "analogue": 96, "ensemble": 96},
        n_states=52).as_dict()
    ctx = dict(CONTEXT, us=fit, us_row=fit)
    html2 = templates.env.get_template("retro_season.html").render(**ctx)
    assert "US (fitted)" in html2
    assert "US national (fitted)" in html2           # the player entry
    assert fallback_claim not in html2
    assert "not a fitted national forecast" not in html2
    assert "US (aggregated)" not in html2
    # even fitted, US stays out of the pooled headline, and says so
    assert "never joins the pooled average" in html2

    # the officials-only case: no scores, so no tile and no row, and the
    # player entry says the officials are all there is
    off = us_national.UsNational(us_national.OFFICIALS_ONLY).as_dict()
    ctx = dict(CONTEXT, us=off, us_row=None)
    html3 = templates.env.get_template("retro_season.html").render(**ctx)
    assert "US (official models only)" in html3
    assert "US (aggregated)" not in html3
    assert "US (fitted)" not in html3


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
