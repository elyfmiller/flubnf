"""Report-vs-app parity: the exported season report must carry the same
substantive content as the in-app season page, for the same season.

THE recurring failure class this guards: the artifact silently lacking what
the console shows. Official stats pending in the report but fine in-app,
chart themes not carrying, reports serving stale faces, and the US national
aggregate missing from a downloaded report each shipped as its own fix;
this test is the permanent guard that makes the NEXT divergence fail the
suite instead of reaching a user.

Mechanics: one synthetic season renders through the REAL season page route
and the REAL report builder, and the comparison is data-driven on the app
page itself. Every section heading the season page renders must either map
to a report counterpart in APP_TO_REPORT below or be declared app-only
with a reason, so adding a season-page section without teaching the report
about it breaks this test. The substance inside the shared sections is
compared value by value: verdict tiles (the US aggregate included),
per-state table rows (the US row included), the cumulative curve, the
recorded wall time, the run settings, and the player's week list.
"""
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import playback, report_season, retro       # noqa: E402
import app.core.scoring as scoring                        # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL     # noqa: E402

W1, W2 = "2098-01-03", "2098-01-10"
SEASON = "2098-99"
N2F = {"Ohio": "39", "Utah": "49"}

#: season-page sections that stay in the console ON PURPOSE, each with the
#: reason. Anything not here and not mapped in APP_TO_REPORT fails the
#: parity test when it appears on the page.
APP_ONLY_HEADINGS = {
    # base-template dialogs, baked into every console page's chrome
    "A run is in progress",
    "This season already has results",
    # the scoring-convention switch (app/core/relwis). It is a CONTROL, and
    # the thing it controls cannot exist in the export: the pairwise
    # convention is computed against every other FluSight team's per-cell
    # scores, hundreds of thousands of rows that a self-contained offline
    # report cannot carry. The report is therefore a ratio-of-sums artifact
    # by construction, and a switch there would have one position.
    "Scoring convention",
}

#: app section heading -> a marker that must appear in the export. The
#: verdict tiles are handled dynamically (any heading that is a model
#: display name, or the US aggregate, must appear as a report tile).
APP_TO_REPORT = {
    "Cumulative ensemble relWIS through the season":
        report_season.CURVE_HEADING,
    "Season player": 'id="pb-scrub"',
    "Live relWIS": "Live relWIS",
    "Per-state scores": "Per-state final scores",
}


def _truth():
    t = {}
    for fips, base in (("39", 100.0), ("49", 50.0), ("US", 150.0)):
        for k in range(-8, 8):
            d = pd.Timestamp(W1) + pd.Timedelta(days=7 * k)
            t[(fips, d)] = base + k
    return t, dict(N2F)


def _bases(asof, fips_set, _truth_arg):
    return {(f, asof, h): 2.0 for f in fips_set for h in range(4)}


def _mk_root(tmp_path, monkeypatch):
    """A scored, finished two-week season under a retro root, with US truth,
    a run record carrying settings and timing, and warm caches, so the real
    season page renders complete in one request."""
    truth, n2f = _truth()
    monkeypatch.setattr(playback, "load_truth", lambda: (truth, n2f))
    monkeypatch.setattr(playback, "_baseline_cells", _bases)
    monkeypatch.setattr(playback, "HUB", tmp_path / "hub")   # no officials
    # retro.national_aggregate and retro.score_season import these at call
    # time from the scoring module, so the patch must land there too
    monkeypatch.setattr(scoring, "load_truth", lambda: (truth, n2f))
    monkeypatch.setattr(scoring, "_baseline_cells", _bases)
    monkeypatch.setattr(report_season, "_plotlyjs", lambda: "/* stub */")

    root = tmp_path / SEASON
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
    rows = []
    for asof in (W1, W2):
        for loc in N2F:
            for m, w in (("pf", 1.0), ("analogue", 3.0), ("ensemble", 1.8)):
                rows.append({"model": m, "asof": asof, "location": loc,
                             "wis": w, "base_wis": 2.0})
    pd.DataFrame(rows).to_json(root / "scores.json")
    retro.write_meta(root, {
        "status": "done", "elapsed_s": 3723.0,
        "weeks_completed": 2, "total_weeks": 2,
        "settings": {"season": SEASON, "scope": "panel6",
                     "particles": 10_000, "replicates": 3,
                     "width": 6, "engine": "all"}})
    return root


def _warm(root):
    """Warm the caches the finished-season page reads, exactly as the
    finalize job would: every playback payload plus the US aggregate."""
    for w in (W1, W2):
        playback.build_week(root, SEASON, w)
    row = retro.national_aggregate(
        root, ensemble_weights={"pf": 0.5, "analogue": 0.5})
    assert row and row.get("ensemble"), "fixture must aggregate US"
    return row


def _app_page(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.ui import server as srv
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    r = TestClient(srv.app).get(f"/retro/{SEASON}")
    assert r.status_code == 200
    html = r.text
    # the fixture must have produced the COMPLETE page: a preparing state
    # here means the parity below would compare against a placeholder
    assert "preparing results" not in html
    assert "Season player" in html
    return html


def _headings(html):
    """Section headings, as a reader sees them: every h2, tags stripped."""
    out = []
    for m in re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S):
        txt = re.sub(r"<[^>]+>", "", m)
        txt = re.sub(r"\s+", " ", txt).strip()
        if txt:
            out.append(txt)
    return out


def _report(root):
    return report_season.build_season_report(root, SEASON).read_text()


@pytest.fixture()
def built(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    _warm(root)
    app_html = _app_page(tmp_path, monkeypatch)
    report_html = _report(root)
    return app_html, report_html


# ------------------------------------------------------------ section parity

def test_every_app_section_has_a_report_counterpart(built):
    """The data-driven guard: a NEW season-page section must be mapped to a
    report counterpart or declared app-only, or this fails."""
    app_html, report_html = built
    tile_names = set(report_season.MODEL_NAMES.values()) | {"US (aggregated)"}
    for h in _headings(app_html):
        if h in APP_ONLY_HEADINGS:
            continue
        if h in tile_names:
            marker = f'class="tilename">{h}'
        else:
            marker = APP_TO_REPORT.get(h)
        assert marker, (
            f"season page section {h!r} has no exported-report counterpart: "
            "either add it to the report and map it in APP_TO_REPORT, or "
            "declare it in APP_ONLY_HEADINGS with the reason it stays "
            "in the console")
        assert marker in report_html, (
            f"season page section {h!r} is missing from the exported "
            f"report (expected marker {marker!r})")


# ---------------------------------------------------------- substance parity

def test_verdict_tiles_match_including_us_aggregate(built):
    app_html, report_html = built
    app_tiles = set(re.findall(
        r'<div class="card"><h2>([^<]+)</h2><div class="big', app_html))
    rep_tiles = set(re.findall(r'class="tilename">([^<]+)<', report_html))
    assert "US (aggregated)" in app_tiles
    assert app_tiles == rep_tiles


def test_per_state_rows_match_including_us_row(built):
    app_html, report_html = built
    app_rows = set(re.findall(r'<tr[^>]*data-name="([^"]+)"', app_html))
    rep_rows = set(re.findall(r'<tr(?: class="usagg")?><td>([^<]+)</td>',
                              report_html))
    assert app_rows == {"US (aggregated)", "Ohio", "Utah"}
    assert app_rows == rep_rows
    # both wear the honest independence label on the constructed US figure
    for html in built:
        assert "states treated as independent" in html


def test_player_week_lists_match(built):
    app_html, report_html = built
    m = re.search(r"const WEEKS = (\[[^\]]*\]);", app_html)
    assert m, "season page must hand the player its week list"
    app_weeks = json.loads(m.group(1))
    d = re.search(r'<script id="pbdata" type="application/json">(.*?)'
                  r"</script>", report_html, re.S)
    assert d, "report must embed the playback data block"
    rep = json.loads(d.group(1).replace("<\\/", "</"))
    assert app_weeks == rep["weeks"] == [W1, W2]
    # every listed week carries a real payload: no empty player frames
    for w in rep["weeks"]:
        pl = rep["payloads"].get(w)
        assert pl and pl.get("models"), f"week {w} embedded without forecasts"
        assert "US" in pl.get("truth", {}), f"week {w} lacks the US truth"


def test_cumulative_curves_match(built):
    app_html, report_html = built
    app_svg = re.search(r'<svg class="cumchart".*?</svg>', app_html, re.S)
    assert app_svg, "season page must draw the cumulative chart"
    rep_at = report_html.index(report_season.CURVE_HEADING)
    rep_svg = re.search(r"<svg .*?</svg>", report_html[rep_at:], re.S)
    assert rep_svg, "report must draw the cumulative chart"
    assert app_svg.group(0).count("<circle") \
        == rep_svg.group(0).count("<circle") == 2
    final = re.compile(r'fill="var\(--gold\)">([\d.]+)</text>')
    app_final = final.search(app_svg.group(0))
    rep_final = final.search(rep_svg.group(0))
    assert app_final and rep_final
    assert app_final.group(1) == rep_final.group(1) == "0.900"


def test_timing_and_settings_match(built):
    app_html, report_html = built
    t = re.search(r"Replay wall time ([\d:]+)", app_html)
    assert t, "the fixture's run record must put the wall time on the page"
    assert f"total wall time {t.group(1)} (h:mm:ss)" in report_html
    pair_re = re.compile(r"<dt>(.*?)</dt><dd>(.*?)</dd>")
    app_pairs = set(pair_re.findall(app_html))
    rep_pairs = set(pair_re.findall(report_html))
    assert app_pairs, "the fixture's run record must render its settings"
    assert app_pairs <= rep_pairs, app_pairs - rep_pairs


# ------------------------------------- absence is stated, never a silent hole

def test_cold_aggregate_cache_is_computed_not_omitted(tmp_path, monkeypatch):
    """The exact field failure: a report downloaded before the season page
    was ever visited. The builder must COMPUTE the aggregate, not read a
    cold cache and drop the section."""
    root = _mk_root(tmp_path, monkeypatch)
    cache = root / "playback_cache" / "us_aggregate.json"
    assert not cache.is_file()
    html = _report(root)
    assert 'class="tilename">US (aggregated)' in html
    assert cache.is_file(), "the report build must warm the cache it used"


def test_unscored_season_states_the_us_absence(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    (root / "scores.json").unlink()
    html = _report(root)
    assert 'class="tilename">US (aggregated)' not in html
    assert "is not in this export" in html
    assert "has not been scored" in html
    # the curve card states its arrival too, the season page's own words
    assert report_season.CURVE_HEADING in html
    assert "Arrives with the first scored week" in html


def test_failed_aggregate_states_the_reason(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("cache disk gone")
    monkeypatch.setattr(retro, "national_aggregate", boom)
    html = _report(root)
    assert 'class="tilename">US (aggregated)' not in html
    assert "is not in this export" in html
    assert "construction failed" in html
    assert "RuntimeError" in html
