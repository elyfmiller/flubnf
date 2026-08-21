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
    assert set(pl["models"]) == {"pf", "analogue", "ensemble"}
    assert pl["stats"]["ensemble"]["cum_rel"] is not None

    # player controls, forecast detail, and the stats table are all inline
    for marker in ('id="pb-prev"', 'id="pb-play"', 'id="pb-next"',
                   'id="pb-speed"', 'id="pb-scrub"', 'id="pb-week"',
                   'id="fd-loc"', 'id="fd-models"', 'id="fd-plot"',
                   'id="pb-stats"', 'id="pb-status"',
                   "US (official models only)", "ArrowLeft", "ArrowRight",
                   "Plotly.react", "beats the CDC FluSight baseline"):
        assert marker in html, marker

    # the header says the maps stayed behind, and no size warning fired
    assert "interactive maps live in the console" in html
    assert "Size notice" not in html


def test_report_js_reads_only_contract_fields(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    html = report_season.build_season_report(root, SEASON).read_text()
    # the report's player JS is the inlined shared player plus the export
    # host block (real builds prepend minified plotly, so slice past it)
    player = report_season.PLAYER_SRC.read_text()
    host = html.split("// FluBNF season player", 1)[1]
    js = player + host
    contract = {"_v", "asof", "locations", "truth", "models", "official", "stats"}
    fields = set(re.findall(r"\bpl\.(\w+)", js))
    assert fields, "expected the player JS to read payload fields via pl.*"
    assert fields <= contract, fields - contract
    stat_fields = set(re.findall(r"\bst\.(\w+)", js))
    assert {"week_rel", "cum_rel"} <= stat_fields <= {"week_rel", "cum_rel", "debug"}, stat_fields
    for m in ("ensemble", "pf", "analogue", "pf2s",
              "FluSight-baseline", "FluSight-ensemble"):
        assert m in js, m


def test_report_inlines_shared_player_verbatim(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    html = report_season.build_season_report(root, SEASON).read_text()
    # the unique marker from player.js appears in the built report ...
    assert "flubnf-player-v1" in html
    # ... because the whole shared file is inlined verbatim, so every
    # future player feature lands in the export automatically
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
    p.write_text("sentinel")
    future = p.stat().st_mtime + 60
    os.utime(p, (future, future))
    # fresh: reused
    assert report_season.build_season_report(root, SEASON).read_text() \
        == "sentinel"
    # a newer player.js invalidates the cached report
    os.utime(fake, (future + 60, future + 60))
    html = report_season.build_season_report(root, SEASON).read_text()
    assert html != "sentinel" and "flubnf-player-v1" in html


def test_builder_source_is_a_report_input(tmp_path, monkeypatch):
    # the builder is an input to its own output: a restyle here must
    # refresh every cached export, exactly as a player fix does; otherwise
    # a season whose data never changes serves the old face forever
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

def _write_scores(root):
    """A synthetic scores.json in the shape retro.score_season writes: one
    row per model, week, and state, with known relWIS ratios (pf 0.5,
    analogue 1.5, ensemble 0.9)."""
    rows = []
    for asof in (W1, W2):
        for loc in N2F:
            for m, w in (("pf", 1.0), ("analogue", 3.0), ("ensemble", 1.8)):
                rows.append({"model": m, "asof": asof, "location": loc,
                             "wis": w, "base_wis": 2.0})
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
    # final relWIS tiles for each member and the ensemble, colored by the
    # below-1 rule; the values are the final week's cumulative stats
    for name, val, cls in (("NAU ensemble", "0.900", "ok"),
                           ("PF-SIHRS", "0.500", "ok"),
                           ("Calendar analogue", "1.500", "bad")):
        assert name in html, name
        assert f'class="tileval {cls}">{val}' in html, (name, val)
    # weeks covered and the recorded wall time
    assert f"2 weeks covered, {W1} to {W2}" in html
    assert "total wall time 1:02:03 (h:mm:ss)" in html
    # the per-state final table, one row per state, same coloring rule
    assert "Per-state final scores" in html
    for loc in N2F:
        assert f"<td>{loc}</td>" in html, loc
    assert '<td class="num ok">0.500</td>' in html
    assert '<td class="num bad">1.500</td>' in html
    assert '<td class="num ok">0.900</td>' in html


def test_report_verdict_degrades_without_scores_or_meta(tmp_path,
                                                        monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    html = report_season.build_season_report(root, SEASON).read_text()
    # tiles still come from the embedded final-week stats
    assert 'id="season-summary"' in html
    assert "Season verdict" in html
    # no run record: no invented wall time; no scores.json: the per-state
    # table is replaced by a plain statement, never fabricated
    assert "total wall time" not in html
    assert "Per-state final scores" not in html
    assert "once the season has been scored" in html


def test_report_player_initializes_at_the_final_week(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    html = report_season.build_season_report(root, SEASON).read_text()
    # a skimmer must meet the season's verdict, not week one: the scrubber
    # starts at the last index and the host seeks there
    assert "player.seek(1);" in html
    assert 'value="1" aria-label="Week scrubber"' in html
    assert "player.seek(0);" not in html


def test_report_wears_the_console_identity(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    html = report_season.build_season_report(root, SEASON).read_text()
    # the brand face with a system fallback, and no webfont fetch (the
    # self-containment test already forbids any network reference)
    assert '"DM Sans",system-ui' in html
    # ok/bad are the console's own dark-theme values, so a number wears one
    # alert color in the app and in the emailed report
    assert ".ok{color:#4CC38A}" in html
    assert ".bad{color:#FB4653}" in html
    assert "#7FC97F" not in html and "#E8A33D" not in html
    # the nau.css dark tokens, verbatim, and the wordmark exactly as the
    # console's navbar writes it
    for token in ("--bg:#0C0D17", "--card:#151729", "--ink:#E9EAF4",
                  "--mut:#9AA1C4", "--line:#262A45", "--accent:#34C0F0"):
        assert token in html, token
    assert "<em>Flu</em>BNF" in html
    assert "font-variant-numeric:tabular-nums" in html


def test_report_carries_a_print_stylesheet(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    html = report_season.build_season_report(root, SEASON).read_text()
    assert "@media print" in html
    pr = html.split("@media print", 1)[1].split("</style>", 1)[0]
    # on paper the console's light theme takes over: light surface, the
    # LANL Blue ink, and the light-theme ok/bad pair
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
    # 2 weeks x 2 states of synthetic ensemble rows
    assert "the season's 4 scored ensemble cells" in html
    # unscored: the generic phrase stands, never an invented count
    root2 = _mk_root(tmp_path / "b", monkeypatch)
    html2 = report_season.build_season_report(root2, SEASON).read_text()
    assert "every scored cell of the season" in html2


# ------------------------------------------------------------------- caching

def test_report_cached_by_mtime_and_invalidated(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    p = report_season.build_season_report(root, SEASON)
    # fresh report is reused verbatim
    p.write_text("sentinel")
    future = p.stat().st_mtime + 60
    os.utime(p, (future, future))
    assert report_season.build_season_report(root, SEASON).read_text() \
        == "sentinel"
    # a newer samples.json invalidates it
    sp = root / "weeks" / W2 / "samples.json"
    os.utime(sp, (future + 60, future + 60))
    html = report_season.build_season_report(root, SEASON).read_text()
    assert html != "sentinel" and "pbdata" in html


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
    root = _mk_root(tmp_path, monkeypatch)
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
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
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
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
