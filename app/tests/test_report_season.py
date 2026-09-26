"""Season report export: a self-contained interactive HTML file built from a
synthetic mini season. Checks self-containment (no external scripts, styles,
or static references), the embedded data block, the inline player JS and its
contract discipline, mtime caching, the size guard, the download route, and
the results-page button."""
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import playback, report_season             # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL    # noqa: E402

W1, W2 = "2098-01-03", "2098-01-10"
SEASON = "2098-99"
N2F = {"Ohio": "39", "Utah": "49"}


def _truth():
    t = {}
    for fips, base in (("39", 100.0), ("49", 50.0)):
        for k in range(-8, 8):
            d = pd.Timestamp(W1) + pd.Timedelta(days=7 * k)
            t[(fips, d)] = base + k
    return t, dict(N2F)


def _mk_root(tmp_path, monkeypatch, stub_plotly=True):
    """A two-week synthetic season root; truth and the baseline denominator
    are monkeypatched so no real data is touched. Plotly is stubbed by
    default so composition assertions see only our own markup."""
    truth, n2f = _truth()
    monkeypatch.setattr(playback, "load_truth", lambda: (truth, n2f))
    monkeypatch.setattr(playback, "_baseline_cells",
                        lambda asof, fips_set, tr: {(f, asof, h): 2.0
                                                    for f in fips_set
                                                    for h in range(4)})
    monkeypatch.setattr(playback, "HUB", tmp_path / "hub")   # no officials
    if stub_plotly:
        monkeypatch.setattr(report_season, "_plotlyjs",
                            lambda: "/* plotly stub */")
    root = tmp_path / "seasonroot"
    for asof in (W1, W2):
        wd = root / "weeks" / asof
        wd.mkdir(parents=True)
        pf, an = {}, {}
        for loc, fips in N2F.items():
            pf[loc] = {str(h): [truth[(fips, pd.Timestamp(asof)
                                       + pd.Timedelta(days=7 * h))] + d
                                for d in (-1.0, 0.0, 1.0)] for h in range(5)}
            an[loc] = {str(h): {str(L): truth[(fips, pd.Timestamp(asof)
                                               + pd.Timedelta(days=7 * h))]
                                + (L - 0.5) * 10 for L in QL}
                       for h in range(1, 5)}
        (wd / "samples.json").write_text(
            json.dumps({"asof": asof, "pf": pf, "analogue": an}))
    return root


def _sentinel(root):
    """A stand-in cached export that passes the builder's CONTENT test (it
    carries the tree's names line), so a caching test sees only mtime."""
    return ("sentinel " + report_season._names_line(
        report_season.names_for_root(root)))


def _data_block(html):
    m = re.search(r'<script id="pbdata" type="application/json">(.*?)'
                  r'</script>', html, re.S)
    assert m, "embedded data block missing"
    return json.loads(m.group(1))


# ------------------------------------------------------------------ building

def test_report_self_contained_with_player_and_data(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    p = report_season.build_season_report(root, SEASON)
    assert p == root / f"{SEASON}-FluBNF-season-report.html"
    html = p.read_text()

    # self-contained: nothing fetched from anywhere, ever
    assert "<script src" not in html
    assert "<link" not in html
    assert "/static/" not in html
    assert "@import" not in html
    assert "http://" not in html and "https://" not in html
    assert "fetch(" not in html

    # the embedded data block carries every week's full playback payload
    data = _data_block(html)
    assert data["season"] == SEASON
    assert data["weeks"] == [W1, W2]
    assert set(data["payloads"]) == {W1, W2}
    pl = data["payloads"][W1]
    assert set(pl) == {"_v", "asof", "locations", "truth", "models", "official", "stats"}
    assert set(pl["models"]) == {"pf", "analogue"}
    assert pl["stats"]["pf"]["cum_rel"] is not None
    assert pl["stats"]["analogue"]["cum_rel"] is not None

    # player controls, forecast detail, and the stats table are all inline
    for marker in ('id="pb-prev"', 'id="pb-play"', 'id="pb-next"',
                   'id="pb-speed"', 'id="pb-scrub"', 'id="pb-week"',
                   'id="fd-loc"', 'id="fd-models"', 'id="fd-plot"',
                   'id="pb-stats"', 'id="pb-status"',
                   "ArrowLeft", "ArrowRight",
                   "Plotly.react", "beats the CDC FluSight baseline"):
        assert marker in html, marker

    # the US entry carries the RESOLVED provenance frozen in at build time;
    # the inlined player spells out all three states
    for marker in ("US national (fitted)", "US national (sum of states)",
                   "US (official models only)", "usLabel(cfg.us)"):
        assert marker in html, marker
    m = re.search(r"\n  us: (\{.*?\}),\n", html, re.S)
    assert m, "the exported player config must carry the resolved us block"
    us = json.loads(m.group(1))
    assert us["provenance"] in ("fitted", "aggregated", "officials_only")
    # states only, no aggregate: officials-only, stated as such
    assert us["provenance"] == "officials_only"
    assert us["fallback"] is True and us["fitted"] is False
    assert us["label"] == "US (official models only)"
    # the pooled scope is stated in the artifact itself
    assert "never joins the pooled average" in html

    # the header says the maps stayed behind, and no size warning fired
    assert "maps stay in the console" in html
    assert "Size notice" not in html


def test_report_js_reads_only_contract_fields(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    html = report_season.build_season_report(root, SEASON).read_text()
    # the player JS is the inlined shared player plus the host block (real
    # builds prepend minified plotly, so slice past it)
    player = report_season.PLAYER_SRC.read_text()
    host = html.split("// FluBNF season player", 1)[1]
    js = player + host
    contract = {"_v", "asof", "locations", "truth", "models", "official", "stats"}
    fields = set(re.findall(r"\bpl\.(\w+)", js))
    assert fields, "expected the player JS to read payload fields via pl.*"
    assert fields <= contract, fields - contract
    stat_fields = set(re.findall(r"\bst\.(\w+)", js))
    # read only through the stats contract's keys (playback.STATS_FIELDS)
    assert ({"week_rel", "cum_rel"} <= stat_fields
            <= set(playback.STATS_FIELDS) | {"debug"}), stat_fields
    for m in ("ensemble", "pf", "analogue", "pf2s",
              "FluSight-baseline", "FluSight-ensemble"):
        assert m in js, m


def test_report_inlines_shared_player_verbatim(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    html = report_season.build_season_report(root, SEASON).read_text()
    # the unique marker from player.js appears in the built report ...
    assert "flubnf-player-v1" in html
    # ... because the whole shared file is inlined verbatim
    assert report_season.PLAYER_SRC.read_text() in html
    # the export host wires the player to the embedded JSON block
    assert "FluBNFPlayer.init" in html
    assert "mode: 'static'" in html


def test_report_rebuilds_when_player_source_changes(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    fake = tmp_path / "player.js"
    fake.write_text(report_season.PLAYER_SRC.read_text())
    monkeypatch.setattr(report_season, "PLAYER_SRC", fake)
    p = report_season.build_season_report(root, SEASON)
    sentinel = _sentinel(root)
    p.write_text(sentinel)
    future = p.stat().st_mtime + 60
    os.utime(p, (future, future))
    # fresh: reused
    assert report_season.build_season_report(root, SEASON).read_text() \
        == sentinel
    # a newer player.js invalidates the cached report
    os.utime(fake, (future + 60, future + 60))
    html = report_season.build_season_report(root, SEASON).read_text()
    assert html != sentinel and "flubnf-player-v1" in html


def test_builder_source_is_a_report_input(tmp_path, monkeypatch):
    # the builder is an input to its own output: a restyle refreshes every
    # cached export, as a player fix does
    root = _mk_root(tmp_path, monkeypatch)
    src_mtime = Path(report_season.__file__).stat().st_mtime
    assert report_season._newest_input(root) >= src_mtime


def test_real_plotly_embedded(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch, stub_plotly=False)
    html = report_season.build_season_report(root, SEASON).read_text()
    assert "<script src" not in html          # inline, not referenced
    assert "Plotly" in html
    assert len(html) > 1_000_000              # the real library is embedded


def test_empty_season_raises_unknown_week(tmp_path):
    with pytest.raises(playback.UnknownWeek):
        report_season.build_season_report(tmp_path / "empty", SEASON)


# ---------------------------------------------- verdict block and identity

def _write_scores(root, current=True):
    """A synthetic scores.json in the shape retro.score_season writes: one
    row per model, week, and state, with known relWIS ratios (pf 0.5,
    analogue 1.5, ensemble 0.9). current=False leaves out the version
    column: a sealed record scored under the earlier cell rule."""
    from app.core import retro
    rows = []
    for asof in (W1, W2):
        for loc in N2F:
            for m, w in (("pf", 1.0), ("analogue", 3.0), ("ensemble", 1.8)):
                rows.append({"model": m, "asof": asof, "location": loc,
                             "wis": w, "base_wis": 2.0})
                if current:
                    rows[-1][retro.SCORES_V_COLUMN] = retro.SCORES_V
    pd.DataFrame(rows).to_json(root / "scores.json")


def test_report_carries_the_season_verdict_before_the_player(tmp_path,
                                                             monkeypatch):
    from app.core import retro
    root = _mk_root(tmp_path, monkeypatch)
    _write_scores(root)
    retro.write_meta(root, {"elapsed_s": 3723.0, "weeks_completed": 2,
                            "total_weeks": 2, "status": "done"})
    html = report_season.build_season_report(root, SEASON).read_text()
    # the static verdict block precedes the player card
    assert html.index('id="season-summary"') < html.index('id="pb-play"')
    assert "Season verdict" in html
    # final relWIS tiles per shipped member, colored by the below-1 rule;
    # the retired blend's stored rows get no tile
    assert 'class="tileval ok">0.900' not in html
    for name, val, cls in (("Oracle SIHRS", "0.500", "ok"),
                           ("Groundhog", "1.500", "bad")):
        assert name in html, name
        assert f'class="tileval {cls}">{val}' in html, (name, val)
    # weeks covered and the recorded wall time
    assert f"2 stored weeks, {W1} to {W2}" in html
    assert "Total wall time 1:02:03 (h:mm:ss)" in html
    assert "weeks covered" not in html            # said once, in the header
    # the per-state final table, one row per state, same coloring rule
    assert "Per-state final scores" in html
    for loc in N2F:
        assert f"<td>{loc}</td>" in html, loc
    assert '<td class="num ok">0.500</td>' in html
    assert '<td class="num bad">1.500</td>' in html
    assert '<td class="num ok">0.900</td>' not in html


def test_the_export_names_the_scoring_convention_on_its_own(tmp_path,
                                                            monkeypatch):
    """The exported file names its scoring convention in the console's own
    words: it is read beside the CDC dashboard, which publishes a different
    ratio under the same name.
    """
    from app.core import relwis
    root = _mk_root(tmp_path, monkeypatch)
    _write_scores(root)
    html = report_season.build_season_report(root, SEASON).read_text()
    assert relwis.PUBLISHED_CONVENTION_NOTE in html
    # every relWIS heading in the file carries the short label as well
    assert "Final relWIS pooled over" in html and "ratio of sums" in html
    assert ("relWIS below 1 beats the CDC FluSight baseline, ratio of"
            in " ".join(html.split()))


def test_report_verdict_degrades_without_scores_or_meta(tmp_path,
                                                        monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    html = report_season.build_season_report(root, SEASON).read_text()
    # tiles still come from the embedded final-week stats
    assert 'id="season-summary"' in html
    assert "Season verdict" in html
    # no run record: no invented wall time; no scores.json: a plain
    # statement instead of the per-state table
    assert "total wall time" not in html
    assert "Per-state final scores" not in html
    assert "once the season has been scored" in html


def test_report_player_initializes_at_the_final_week(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    html = report_season.build_season_report(root, SEASON).read_text()
    # a skimmer meets the season's verdict: the player starts at the last week
    assert "player.seek(1);" in html
    assert 'value="1" aria-label="Week scrubber"' in html
    assert "player.seek(0);" not in html


def test_report_wears_the_console_identity(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    html = report_season.build_season_report(root, SEASON).read_text()
    # brand face with a system fallback, no webfont fetch
    assert '"DM Sans",system-ui' in html
    # ok/bad ride the console's tokens in every theme
    assert ".ok{color:var(--ok)}.bad{color:var(--bad)}" in html
    assert "#7FC97F" not in html and "#E8A33D" not in html
    # nau.css dark tokens verbatim, and the navbar wordmark
    for token in ("--bg:#0C0D17", "--card:#151729", "--ink:#E9EAF4",
                  "--mut:#9AA1C4", "--line:#262A45", "--accent:#34C0F0"):
        assert token in html, token
    assert "<em>Flu</em>BNF" in html
    assert "font-variant-numeric:tabular-nums" in html


def test_report_is_theme_aware(tmp_path, monkeypatch):
    """The export embeds the console's full theme system (four theme blocks
    plus both accessibility modifiers, verbatim from nau.css), boots from
    the console's localStorage keys with OS fallbacks, re-reads tokens per
    redraw, and keeps print light by placing @media print last."""
    from app.core import report_v2
    root = _mk_root(tmp_path, monkeypatch)
    html = report_season.build_season_report(root, SEASON).read_text()
    for sel in ('[data-theme="dark"]{', '[data-theme="paper"]{',
                '[data-theme="dim"]{', '[data-contrast="high"]{',
                '[data-vision="cvd"]{'):
        assert sel in html, sel
    # the light palette (nau.css's first :root block) is embedded too
    assert "--bg:#F1EFF7" in html
    # the boot script: same keys as the console, OS fallbacks, guarded
    for probe in ("localStorage.getItem('theme')",
                  "localStorage.getItem('contrast')",
                  "localStorage.getItem('vision')",
                  "prefers-color-scheme", "prefers-contrast"):
        assert probe in html, probe
    # the charts follow: a palette hook reading the tokens per redraw
    assert "palette: function()" in html
    assert "css('--card', '#151729')" in html
    assert "FluBNFPlayer.MODEL_COLORS" in html
    # print wins the cascade: last token statement in the stylesheet
    assert html.rindex("@media print") > html.rindex('[data-vision="cvd"]{')
    # the token blocks are nau.css's own, not a drifted copy
    assert report_v2.theme_token_css() in html


def test_report_carries_a_print_stylesheet(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    html = report_season.build_season_report(root, SEASON).read_text()
    assert "@media print" in html
    pr = html.split("@media print", 1)[1].split("</style>", 1)[0]
    # on paper the light theme takes over (LANL Blue ink, light ok/bad)
    for v in ("#FFFFFF", "#000F7E",
              ".ok{color:#177245}", ".bad{color:#C42840}"):
        assert v in pr, v
    # the player's interactive chrome stays on screen
    assert "display:none!important" in pr


def test_report_verdict_states_cell_coverage_when_scored(tmp_path,
                                                         monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    _write_scores(root)
    html = report_season.build_season_report(root, SEASON).read_text()
    # 2 weeks x 2 states, counted on the first model and named for what the
    # tree stores (no oracle record: the particle filter alone)
    assert "the season's 4 scored Particle filter alone cells" in html
    # unscored: the generic phrase stands, never an invented count
    root2 = _mk_root(tmp_path / "b", monkeypatch)
    html2 = report_season.build_season_report(root2, SEASON).read_text()
    assert "every scored cell of the season" in html2


# ------------------------------------------------------------------- caching

def test_report_cached_by_mtime_and_invalidated(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    p = report_season.build_season_report(root, SEASON)
    # fresh report is reused verbatim
    sentinel = _sentinel(root)
    p.write_text(sentinel)
    future = p.stat().st_mtime + 60
    os.utime(p, (future, future))
    assert report_season.build_season_report(root, SEASON).read_text() \
        == sentinel
    # a newer samples.json invalidates it
    sp = root / "weeks" / W2 / "samples.json"
    os.utime(sp, (future + 60, future + 60))
    html = report_season.build_season_report(root, SEASON).read_text()
    assert html != sentinel and "pbdata" in html


# ---------------------------------------------------------------- size guard

def test_size_guard_warns_in_header(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    monkeypatch.setattr(report_season, "SIZE_WARN_BYTES", 10)
    html = report_season.build_season_report(root, SEASON).read_text()
    assert "Size notice" in html and "25 MB" in html


# --------------------------------------------------------------------- route

def test_route_downloads_report(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.ui import server as srv
    from app.ui import retro_seasons as ui_retro_seasons
    root = _mk_root(tmp_path, monkeypatch)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    root.rename(tmp_path / SEASON)
    r = TestClient(srv.app).get(f"/retro/{SEASON}/report")
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert f"{SEASON}-FluBNF-season-report.html" in cd
    assert "pbdata" in r.text


def test_route_unknown_season_is_plain_404(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.ui import server as srv
    from app.ui import retro_seasons as ui_retro_seasons
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    r = TestClient(srv.app).get("/retro/2097-98/report")
    assert r.status_code == 404
    assert "2097-98" in r.text


# -------------------------------------------------------------------- button

def test_results_page_has_download_button():
    from app.ui.server import templates
    html = templates.env.get_template("retro_season.html").render(
        active="Retrospective", season="2098-99", heads={"ensemble": 0.9},
        curve=[("2098-11-07", 0.95)], states=[],
        weeks=["2098-11-07"], week="2098-11-07",
        map_html="<div id='usmap-wrap'></div>", n_weeks=1, score_error="")
    assert "Download season report" in html
    assert '/retro/2098-99/report' in html


# ------------------------------- log scale and coverage in the export

def _write_metric_scores(root, us=False):
    """scores.json as score_season writes it now: WIS with log-scale WIS,
    0/1 coverage and the baseline's log-scale WIS per cell. pf covers
    every interval (0.8 log relWIS); the analogue misses the 50% one (1.2)."""
    from app.core import retro
    rows = []
    locs = list(N2F) + (["US"] if us else [])
    for asof in (W1, W2):
        for loc in locs:
            for m, w, lw, cov in (("pf", 1.0, 0.4, (1, 1, 1)),
                                  ("analogue", 3.0, 0.6, (0, 1, 1))):
                rows.append({"model": m, "asof": asof, "location": loc,
                             "horizon": 0, "wis": w, "base_wis": 2.0,
                             "log_wis": lw, "base_log_wis": 0.5,
                             "cov50": cov[0], "cov80": cov[1],
                             "cov95": cov[2], "rel": w / 2.0,
                             retro.SCORES_V_COLUMN: retro.SCORES_V})
    pd.DataFrame(rows).to_json(root / "scores.json")


def test_report_verdict_carries_log_scale_and_coverage(tmp_path,
                                                       monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    _write_metric_scores(root)
    html = report_season.build_season_report(root, SEASON).read_text()
    summary = html.split('id="season-summary"', 1)[1].split(
        'id="pb-play"', 1)[0]
    # the tiles: the final frame's figures, log scale in the ok/bad rule,
    # coverage read against each interval's level
    pf = summary.split('class="tilename">Groundhog', 1)[0]
    assert '<dt>log scale</dt><dd class="ok">0.800</dd>' in pf
    # 100% is too wide at every level, 95% included (2.5 points there)
    assert pf.count('<span class="cov-wide">100%</span>') == 3
    an = summary.split('class="tilename">Groundhog', 1)[1]
    assert '<dd class="bad">1.200</dd>' in an
    assert '<span class="cov-low">0%</span>' in an
    assert report_season.METRICS_NOTE in summary
    # the per-state table: each member over its relWIS and 95% coverage
    assert summary.count('<th colspan="2" class="grp">') == 2
    assert summary.count('<th class="num">95%</th>') == 2
    assert '<td class="num cov-wide">100%</td>' in summary
    # the colors' key under the tiles, the 95% column's reading above it
    assert f'<p class="pblegend">{report_season.COV_LEGEND}</p>' in summary
    assert report_season.PSTATES_COV_NOTE in summary
    # the player card: the shared heading, the switch and legend slots
    assert f"<h2>{report_season.LIVE_HEADING}</h2>" in html
    assert report_season.LIVE_SCORES_NOTE in html
    for marker in ('id="pb-scale"', 'id="pb-legend"',
                   '<table id="pb-stats" class="pbstats">'):
        assert marker in html, marker


def test_report_verdict_without_the_new_columns_stays_as_it_was(
        tmp_path, monkeypatch):
    """A scores.json from before log-scale WIS and coverage (a sealed root)
    keeps its per-state table as it was: relWIS alone, no coverage column.
    It also used the earlier cell rule, so the tiles (the player's final
    frame) are scored here under FluSight's and carry the new figures, and
    a line says which figures used which rule."""
    from app.core import scoring
    root = _mk_root(tmp_path, monkeypatch)
    _write_scores(root, current=False)
    html = report_season.build_season_report(root, SEASON).read_text()
    summary = html.split('id="season-summary"', 1)[1].split(
        'id="pb-play"', 1)[0]
    assert '<th class="num">95%</th>' not in summary
    assert "<thead><tr><th>State</th>" in summary
    tiles = summary.split('class="tiles"', 1)[1].split("</div></div>", 1)[0]
    assert 'class="tilekv"' in tiles
    assert report_season.METRICS_NOTE in summary
    assert 'class="tileval ok">0.500' not in tiles    # not the stored 0.5
    note = scoring.earlier_rule_note(
        ["the per-state table"], ["the pooled tiles", "the live scores"])
    assert note in summary
    # a current file needs no such line
    root2 = _mk_root(tmp_path / "b", monkeypatch)
    _write_scores(root2)
    html2 = report_season.build_season_report(root2, SEASON).read_text()
    assert "earlier cell rule" not in html2


def test_report_fitted_us_pf_is_named_the_plain_filter_under_oracle(
        tmp_path, monkeypatch):
    """The Oracle step skips the national row: when pf is Oracle SIHRS, the
    fitted US tile and the table say what the US figure is; a tree without
    the step (pf named for the filter) needs no such note."""
    from app.core import retro
    from app.core import us_national as usn
    root = _mk_root(tmp_path, monkeypatch)
    _write_metric_scores(root, us=True)
    html = report_season.build_season_report(root, SEASON).read_text()
    assert 'class="tilename">US (fitted): Particle filter alone' in html
    assert usn.PF_US_NOTE not in html.split('id="pb-play"', 1)[0]
    root2 = _mk_root(tmp_path / "b", monkeypatch)
    _write_metric_scores(root2, us=True)
    retro.write_meta(root2, {"status": "done",
                             "settings": {"oracle": "applied"}})
    html2 = report_season.build_season_report(root2, SEASON).read_text()
    summary = html2.split('id="pb-play"', 1)[0]
    assert 'class="tilename">US (fitted): Oracle SIHRS' in summary
    assert usn.PF_US_SHORT + ", fitted at the national level" in summary
    assert f'<p class="hint">{usn.PF_US_NOTE}</p>' in summary
    # the US row's coverage joins the table beside its relWIS
    row = summary.split('<tr class="usagg">', 1)[1].split("</tr>", 1)[0]
    assert '<td class="num cov-wide">100%</td>' in row
