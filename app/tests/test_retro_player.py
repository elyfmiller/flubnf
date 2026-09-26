"""Retrospective season player: the template renders the controls, both
views and the stats table; the shared player.js plus the page JS read only
playback-contract fields."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import us_national                    # noqa: E402
from app.ui.server import templates                 # noqa: E402

PLAYER_JS = (Path(__file__).resolve().parents[1] / "ui" / "static"
             / "player.js").read_text(encoding="utf-8")

#: the server's resolved US answer, here the sum-of-states FALLBACK, which
#: must be labelled as a fallback
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
                   'id="view-fc"', "Categorical forecast", "Forecast detail"):
        assert marker in html, marker
    # forecast detail: location select, model toggles, plot, US labeling
    for marker in ('id="fd-loc"', 'id="fd-models"', 'id="fd-plot"'):
        assert marker in html, marker
    # the US entry text follows the resolved provenance (all three states
    # spelled out in the player); fallbacks never read as fitted
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
    # every `pl.` field is a top-level contract key (page and player checked
    # together as one JS surface)
    both = html + PLAYER_JS
    contract = {"asof", "locations", "truth", "models", "official", "stats"}
    fields = set(re.findall(r"\bpl\.(\w+)", both))
    assert fields, "expected the player JS to read payload fields via pl.*"
    assert fields <= contract, fields - contract
    # stats entries are read only through the contract's keys
    # (playback.STATS_FIELDS, plus "debug")
    from app.core import playback
    stat_fields = set(re.findall(r"\bst\.(\w+)", both))
    assert stat_fields <= set(playback.STATS_FIELDS) | {"debug"}, stat_fields
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
    """Every US surface says whether it is a fitted forecast or the
    sum-of-states aggregate; a fallback is visibly a fallback."""
    # the aggregated case: tile, row and player entry carry the fallback
    # wording, and the pooled scope is stated
    fallback_claim = "the scores for this season hold no scored US fit"
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


# ------------------------------- live scores and the verdicts' new figures

def test_stats_card_hosts_the_players_table_switch_and_legend():
    """The player writes the table head, the scale switch and the coverage
    legend into the host's slots; the card's heading and explanation are
    the export's own (report_season.LIVE_HEADING, LIVE_SCORES_NOTE)."""
    from app.core import report_season
    html = _render()
    card = html.split('<div class="playstats">', 1)[1].split("</div>\n </div>",
                                                             1)[0]
    assert f"<h2>{report_season.LIVE_HEADING}</h2>" in card
    assert report_season.LIVE_SCORES_NOTE in card
    assert '<div class="pbscale" id="pb-scale"></div>' in card
    # the table scrolls inside its own box, never widening the page
    assert ('<div class="statscroll"><table id="pb-stats" class="pbstats">'
            '<thead></thead>') in card
    assert '<p class="pblegend" id="pb-legend"></p>' in card
    # the player fills them from its default ids
    assert "scale: 'pb-scale', legend: 'pb-legend'" in PLAYER_JS
    assert "paintStatsFrame();" in PLAYER_JS


def _figs(detail_cov=True):
    from app.core import relwis
    cov = {"50": 0.43, "80": 0.71, "95": 0.88}
    return relwis.Figures(
        convention=relwis.RATIO_OF_SUMS,
        values={"pf": 0.783, "analogue": 0.651},
        detail={"pf": {"n_cells": 4576, "log_rel": 0.835,
                       "cov": cov if detail_cov else None},
                "analogue": {"n_cells": 4524, "log_rel": None, "cov": None}},
        states=({"name": "Ohio", "pf": 0.9, "analogue": 1.1,
                 "detail": {"pf": {"n_cells": 80, "log_rel": 0.8,
                                   "cov": ({"50": 0.5, "80": 0.8,
                                            "95": 0.62} if detail_cov
                                           else None)},
                            "analogue": {"n_cells": 80, "log_rel": None,
                                         "cov": None}}},))


def _season(**kw):
    ctx = dict(CONTEXT, heads={"pf": 0.783, "analogue": 0.651},
               season_models=["pf", "analogue"], us=None, us_row=None)
    ctx.update(kw)
    ctx["states"] = list(ctx["figs"].states) if "figs" in kw else []
    return templates.env.get_template("retro_season.html").render(**ctx)


def test_verdict_tiles_carry_log_scale_and_coverage():
    html = _season(figs=_figs())
    tiles = html.split('<div class="grid2">', 1)[1].split(
        "Cumulative relWIS", 1)[0]
    pf = tiles.split("<h2>Groundhog</h2>", 1)[0]
    # the log-scale figure beside the natural one, in the same ok/bad rule
    assert '<dt>log scale</dt><dd class="ok">0.835</dd>' in pf
    # coverage as whole percentages, each read against its interval's level
    assert '<dt>coverage 50/80/95%</dt>' in pf
    assert '<span class="cov-low">43%</span>' in pf
    assert '<span class="cov-low">71%</span>' in pf
    assert '<span class="cov-low">88%</span>' in pf
    assert "(4,576 cells)" in pf
    # a member whose scores predate the figures shows none of them
    an = tiles.split("<h2>Groundhog</h2>", 1)[1]
    assert "tilekv" not in an
    # what the second line holds and the coverage colors' key, once, under
    # the tiles (the player's legend line)
    from app.core import report_season
    assert f'<p class="pblegend">{report_season.COV_LEGEND}</p>' in tiles
    assert report_season.METRICS_NOTE in tiles
    # none of it without a figure to explain
    bare = _season(figs=_figs(detail_cov=False))
    assert report_season.COV_LEGEND not in bare


def test_per_state_table_adds_95_coverage_when_the_scores_carry_it():
    html = _season(figs=_figs())
    body = html.split("Per-state scores")[1].split("</table>")[0]
    # two-row head: each member over its relWIS and 95% columns, all
    # sortable, the member named once over its pair
    assert '<table id="sf-table" class="pscov">' in html
    assert body.count('<th colspan="2" scope="colgroup" class="grp g1">') == 2
    for key in ("name", "pf", "pfCov", "analogue", "analogueCov"):
        assert f'data-key="{key}"' in body, key
    assert 'aria-label="Oracle SIHRS 95% coverage"' in body
    # rows carry the coverage the client sorts on; 62% of a 95% interval
    # is too narrow, and a member without the figure prints a dash
    assert 'data-pf-cov="0.620000"' in body
    assert 'data-analogue-cov=""' in body
    assert '<td class="num cov-low">62%</td>' in body
    assert '<td class="num hint">–</td>' in body
    # the column's reading at 95%, said once above the table
    from markupsafe import escape
    from app.core import report_season
    assert "95%: the share of the state" in report_season.PSTATES_COV_NOTE
    assert str(escape(report_season.PSTATES_COV_NOTE)) in html


def test_per_state_table_keeps_one_column_per_member_without_coverage():
    html = _season(figs=_figs(detail_cov=False))
    body = html.split("Per-state scores")[1].split("</table>")[0]
    assert 'class="pscov"' not in html
    assert body.count('class="thsort"') == 3
    assert "Cov" not in body and "95%" not in body


def test_fitted_us_pf_says_it_is_the_plain_filter():
    """The Oracle step skips the national row: under the Oracle SIHRS name,
    the fitted US figure is the particle filter without it, on the tile
    and under the table (us_national.PF_US_NOTE)."""
    fit = us_national.UsNational(
        us_national.FITTED,
        scores={"pf": 0.9, "analogue": 0.58},
        cells={"pf": 96, "analogue": 96}, n_states=52,
        log_scores={"pf": 0.75, "analogue": None},
        covs={"pf": {"50": 0.2, "80": 0.48, "95": 0.7},
              "analogue": None}).as_dict()
    html = _season(figs=_figs(), us=fit, us_row=fit)
    flat = " ".join(html.split())
    tile = flat.split("<h2>US (fitted): Oracle SIHRS</h2>", 1)[1].split(
        "</div></div>", 1)[0]
    assert us_national.PF_US_SHORT + ", fitted nationally" in tile
    assert '<dd class="ok">0.750</dd>' in tile
    assert '<span class="cov-low">20%</span>' in tile
    an = flat.split("<h2>US (fitted): Groundhog</h2>", 1)[1].split(
        "</div></div>", 1)[0]
    assert us_national.PF_US_SHORT not in an
    assert f'<p class="hint">{us_national.PF_US_NOTE}</p>' in flat
    # the US row's coverage joins the table beside its relWIS
    row = flat.split('<tr class="usagg"', 1)[1].split("</tr>", 1)[0]
    assert 'data-pf-cov="0.700000"' in row
    assert '<td class="num cov-low">70%</td>' in row
    # a tree without the step names pf for the filter: nothing to add
    plain = _season(figs=_figs(), us=fit, us_row=fit,
                    model_name=lambda m: {"pf": "Particle filter alone",
                                          "analogue": "Groundhog"}.get(m, m))
    # (the player's us block still carries pf_note: it makes the same test
    # of pf's name, player.js usPfNote)
    page = plain.split("// live host for the shared player", 1)[0]
    assert us_national.PF_US_NOTE not in page
    assert us_national.PF_US_SHORT not in page
