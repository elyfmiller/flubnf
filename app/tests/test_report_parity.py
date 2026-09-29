"""Report-vs-app parity: the exported season report IS the in-app season
page for the same season (retro_season.html rendered in export mode,
app/ui/season_export).

Guards the recurring failure class of an artifact silently lacking what the
console shows. One synthetic season renders through the REAL season route
and the REAL report builder; every section heading must match, and the
shared regions (the season scores with the US tiles, the per-state table
with the US row, the cumulative chart, the run facts and settings, the
player's timeline) must be the same markup.
"""
import json
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

#: season-page headings the report leaves out ON PURPOSE: the console's
#: dialogs (stopping a run, starting a season over), which act on the
#: running console
APP_ONLY_HEADINGS = {
    "A run is in progress",
    "This season already has results",
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
    # retro.national_aggregate/score_season import these from scoring at
    # call time, so patch there too
    monkeypatch.setattr(scoring, "load_truth", lambda: (truth, n2f))
    monkeypatch.setattr(scoring, "_baseline_cells", _bases)

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
        root)
    assert row and row.get("pf"), "fixture must aggregate US"
    return row


def _app_page(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.ui import server as srv
    from app.ui import retro_seasons as ui_retro_seasons
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    r = TestClient(srv.app).get(f"/retro/{SEASON}")
    assert r.status_code == 200
    html = r.text
    # a preparing state would make the parity compare against a placeholder
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

def _region(html, start, end):
    """The markup from `start` up to (not including) `end`."""
    i = html.index(start)
    return html[i:html.index(end, i)]


def test_every_app_section_is_in_the_report(built):
    """The same sections in the same order: a new section on the page is in
    the report without anyone remembering to add it."""
    app_html, report_html = built
    want = [h for h in _headings(app_html) if h not in APP_ONLY_HEADINGS]
    assert _headings(report_html) == want
    for h in ("Season player", "Live scores",
              "Cumulative relWIS through the season", "Per-state scores"):
        assert h in want, h


def test_verdict_tiles_match_including_us_aggregate(built):
    app_html, report_html = built
    a = _region(app_html, '<div class="verdict">', '<div class="card playcard">')
    r = _region(report_html, '<div class="verdict">', '<div class="card playcard">')
    assert a == r
    assert "<h2>US (aggregated): Groundhog</h2>" in a


def test_per_state_rows_match_including_us_row(built):
    app_html, report_html = built
    a = _region(app_html, '<table id="sf-table"', "</table>")
    assert a == _region(report_html, '<table id="sf-table"', "</table>")
    assert 'class="usagg"' in a and 'data-name="Ohio"' in a


def test_the_cumulative_chart_matches(built):
    app_html, report_html = built
    a = _region(app_html, '<svg class="cumchart"', "</svg>")
    assert a == _region(report_html, '<svg class="cumchart"', "</svg>")
    assert "<polyline" in a


def test_player_week_lists_match(built):
    app_html, report_html = built
    line = re.search(r"const WEEKS = .*?;", app_html).group(0)
    assert line in report_html and W1 in line and W2 in line


def test_timing_and_settings_match(built):
    """Wall time and the run settings: the same facts, from the run record."""
    app_html, report_html = built
    for start, end in (('<div class="rs-facts', "</dl>"),
                       ('<div class="rs-settings', "</div>")):
        a = _region(app_html, start, end)
        assert a in report_html, start
    assert "1:02:03" in report_html
    assert "10,000 particles" in report_html


def test_cold_aggregate_cache_is_computed_not_omitted(tmp_path, monkeypatch):
    """No warm caches: the builder settles the season as the page's finalize
    job does, so the US figures are there, never silently absent."""
    root = _mk_root(tmp_path, monkeypatch)
    html = _report(root)
    assert "<h2>US (aggregated): Groundhog</h2>" in html


def test_unscored_season_states_the_us_absence(tmp_path, monkeypatch):
    """Nothing scored yet: the report says so as the page does (an empty
    state), and invents no US figure."""
    root = _mk_root(tmp_path, monkeypatch)
    (root / "scores.json").unlink()
    monkeypatch.setattr(scoring, "load_truth", lambda: ({}, dict(N2F)))
    monkeypatch.setattr(playback, "load_truth", lambda: ({}, dict(N2F)))
    html = _report(root)
    assert "US (aggregated)" not in html
    assert "No scoreable weeks yet" in html or "Scoring failed" in html


def test_failed_aggregate_states_no_us_figure(tmp_path, monkeypatch):
    """A US aggregate that cannot be built costs the US figures only: the
    report still builds, with the states' scores."""
    root = _mk_root(tmp_path, monkeypatch)
    from app.core import us_national as usn

    def boom(*a, **k):
        raise RuntimeError("aggregate broke")
    monkeypatch.setattr(usn, "resolve", boom)
    html = _report(root)
    assert 'data-name="Ohio"' in html
    assert 'class="usagg"' not in html
