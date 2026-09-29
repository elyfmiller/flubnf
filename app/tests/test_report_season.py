"""Season report export: the Retrospective season page as one
self-contained HTML file (app/ui/season_export), built from a synthetic
mini season. Checks self-containment (nothing loaded from a server or the
network), the embedded weeks and maps, the page's own player inlined
verbatim, the export's differences from the page (opens on the forecast
detail, no console actions), the PyBNF build it names, caching, the print
styles and the download route. Parity with the page, section by section:
test_report_parity.py."""
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
        # plotly (5 MB) is not what these tests read
        from app.ui import templating
        real = templating.inline_static
        monkeypatch.setitem(
            templating.templates.env.globals, "inline_static",
            lambda rel: ("<script>/* plotly stub */</script>"
                         if rel == "plotly.min.js" else real(rel)))
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


def _embed(html):
    m = re.search(r"window\.FLUBNF_EMBED = (\{.*?\});</script>", html, re.S)
    assert m, "embedded weeks missing"
    return json.loads(m.group(1))


def _build(root, **kw):
    return report_season.build_season_report(root, SEASON, **kw).read_text()


# ------------------------------------------------------------------ building

def test_report_is_self_contained_with_every_week(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    p = report_season.build_season_report(root, SEASON)
    assert p == root / f"{SEASON}-FluBNF-season-report.html"
    html = p.read_text()
    # nothing loaded from the console or the network
    assert "<script src" not in html
    assert "<link rel=\"stylesheet\"" not in html
    assert not re.search(r"""url\(["']?/static/""", html)
    assert not re.search(r"""(src|href)=["']/static/""", html)
    assert "@import" not in html
    # the fonts and marks ride along as data URIs
    assert "data:font/woff2;base64," in html
    # every stored week's playback payload and categorical map
    e = _embed(html)
    assert set(e["payloads"]) == {W1, W2}
    pl = e["payloads"][W1]
    assert {"asof", "locations", "truth", "models", "stats"} <= set(pl)
    assert set(pl["models"]) == {"pf", "analogue"}
    assert set(e["maps"]) == {W1, W2}
    assert set(e["maps"][W2]["models"]) <= {"pf", "analogue"}


def test_report_inlines_the_pages_own_player_verbatim(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    html = _build(root)
    player = report_season.PLAYER_SRC.read_text()
    assert player.replace("</script", "<\\/script") in html
    # the page's host code, reading the embedded weeks first
    assert "const EMBED = window.FLUBNF_EMBED || null;" in html
    assert "if(EMBED){" in html


def test_report_opens_on_the_forecast_detail(tmp_path, monkeypatch):
    """The page opens on the categorical map; the report on the forecast
    detail, with the map one click away (and a state clicked on it opens
    that state's detail)."""
    root = _mk_root(tmp_path, monkeypatch)
    html = _build(root)
    assert 'id="tab-fc" aria-pressed="true"' in html
    assert 'id="tab-map" aria-pressed="false"' in html
    assert 'setView("fc");' in html
    assert "window.showState = function(id)" in html
    assert 'id="usmap"' in html


def test_report_carries_nothing_that_needs_the_console(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    html = _build(root)
    for gone in ("Download report", "Reveal in Finder", "Export replay",
                 'class="navtabs"', 'id="guard-modal"', "/api/perf",
                 "/api/versions", "Open the live"):
        assert gone not in html, gone
    # the header says what the file is; the footer, what built it
    assert "Season report" in html
    assert "a self-contained file that needs no network" in html


def test_report_is_theme_aware_and_prints_light(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    html = _build(root)
    # the console's own themes and Display menu
    assert 'id="displaymenu"' in html
    assert "localStorage.getItem('theme')" in html
    pr = html.split("@media print", 1)[1].split("</style>", 1)[0]
    for v in ("#FFFFFF", "#000F7E", ".ok{color:#177245}",
              ".bad{color:#C42840}", "display:none!important"):
        assert v in pr, v


def _meta(root, **settings):
    from app.core import retro
    base = {"season": SEASON, "scope": "panel6", "particles": 10_000,
            "replicates": 3, "width": 6, "engine": "all"}
    base.update(settings)
    retro.write_meta(root, {"status": "done", "elapsed_s": 3723.0,
                            "weeks_completed": 2, "total_weeks": 2,
                            "settings": base})


def test_report_names_the_recorded_pybnf_build(tmp_path, monkeypatch):
    """The build that fitted the season, from its run record: never the
    exporting machine's engine (which may be absent or another build)."""
    root = _mk_root(tmp_path, monkeypatch)
    _meta(root, engine_build={"branch": "feature/particle-filter",
                              "commit": "2fdadee0", "dirty": False,
                              "source": "git"})
    html = _build(root, versions={"pybnf": "not installed"})
    assert "PyBNF build 2fdadee0" in html
    assert "2fdadee0 (feature/particle-filter)" in html
    assert "not installed" not in html


def test_report_says_when_no_pybnf_build_was_recorded(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    _meta(root)
    assert "PyBNF build not recorded" in _build(root)


def test_report_cached_and_rebuilt_when_an_input_changes(tmp_path,
                                                         monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    p = report_season.build_season_report(root, SEASON)
    first = p.stat().st_mtime_ns
    assert report_season.build_season_report(root, SEASON).stat().st_mtime_ns \
        == first
    # a newer input (a stored week) rebuilds it
    later = p.stat().st_mtime + 5
    wk = root / "weeks" / W2 / "samples.json"
    os.utime(wk, (later, later))
    assert report_season.build_season_report(root, SEASON).stat().st_mtime_ns \
        != first
    # so does a file built for another run (the archive marker)
    txt = p.read_text().replace(report_season.REPORT_MARK, "old format")
    p.write_text(txt)
    os.utime(p, (later + 5, later + 5))
    assert report_season.REPORT_MARK in _build(root)


def test_the_season_page_itself_is_a_report_input(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    ui = Path(report_season.__file__).resolve().parents[1] / "ui"
    newest = report_season._newest_input(root)
    for f in (ui / "templates" / "retro_season.html",
              ui / "templates" / "base.html", ui / "season_export.py",
              report_season.PLAYER_SRC):
        assert newest >= f.stat().st_mtime, f


def test_empty_season_raises_unknown_week(tmp_path):
    with pytest.raises(playback.UnknownWeek):
        report_season.build_season_report(tmp_path / "empty", SEASON)


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
    assert "window.FLUBNF_EMBED" in r.text


def _served(tmp_path, monkeypatch):
    """The synthetic season under a retro root the console serves."""
    from fastapi.testclient import TestClient
    from app.ui import server as srv
    from app.ui import retro_seasons as ui_retro_seasons
    root = _mk_root(tmp_path, monkeypatch)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    root.rename(tmp_path / SEASON)
    return TestClient(srv.app)


def _follow(client, season, timeout=120):
    """Start the report job as the page does, then poll its status."""
    import time
    t0 = time.time()
    d = client.post(f"/api/retro/{season}/report_job").json()
    while d["state"] == "running" and time.time() - t0 < timeout:
        time.sleep(0.1)
        d = client.get(f"/api/retro/{season}/report_status").json()
    return d


def test_a_build_reports_its_progress_week_by_week(tmp_path, monkeypatch):
    """The page's progress bar hears each step: scoring, every week
    counted, writing the file."""
    root = _mk_root(tmp_path, monkeypatch)
    seen = []
    report_season.build_season_report(
        root, SEASON, progress=lambda phase, done=None, total=None:
        seen.append((phase, done, total)))
    phases = [p for p, _, _ in seen]
    assert phases[0] == "Scoring the season"
    assert ("Adding the weeks", 0, 2) in seen and ("Adding the weeks", 1, 2) in seen
    assert phases[-1] == "Writing the file"
    # a fresh cached report needs no build: no steps
    seen.clear()
    report_season.build_season_report(root, SEASON, progress=lambda *a: seen.append(a))
    assert seen == []


def test_the_page_builds_the_report_as_a_job_then_downloads_it(tmp_path,
                                                             monkeypatch):
    """Download report no longer waits on one long request: the page starts
    the build as a job, follows it, then downloads the finished file."""
    c = _served(tmp_path, monkeypatch)
    assert c.get(f"/api/retro/{SEASON}/report_status").json() == {"state": "idle"}
    d = _follow(c, SEASON)
    assert d["state"] == "done", d
    assert d["name"] == f"{SEASON}-FluBNF-season-report.html" and d["size_h"]
    r = c.get(f"/retro/{SEASON}/report")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    # the page wires its buttons to the job and shows the bar
    page = c.get(f"/retro/{SEASON}").text
    assert 'id="dl-report"' in page and 'id="rs-prog"' in page
    assert "/report_job'+q(el)" in page and "/report_status'+q(el)" in page
    assert "UI().progress(" in page


def test_a_failed_build_says_why_on_the_page(tmp_path, monkeypatch):
    from app.ui import season_export
    c = _served(tmp_path, monkeypatch)

    def broken(*a, **k):
        raise RuntimeError("the embedded weeks could not be read")
    monkeypatch.setattr(season_export, "render_season_report", broken)
    d = _follow(c, SEASON)
    assert d["state"] == "error"
    assert d["error"] == "RuntimeError: the embedded weeks could not be read"


def test_a_job_for_an_unknown_season_is_plain_404(tmp_path, monkeypatch):
    c = _served(tmp_path, monkeypatch)
    r = c.post("/api/retro/2097-98/report_job")
    assert r.status_code == 404 and "2097-98" in r.text


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
    assert "Download report" in html
    assert '/retro/2098-99/report' in html
