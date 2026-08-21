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
    assert set(pl) == {"asof", "locations", "truth", "models", "official",
                       "stats"}
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
    # inspect only the player script (real builds prepend minified plotly)
    player = html.split("// FluBNF season player", 1)[1]
    contract = {"asof", "locations", "truth", "models", "official", "stats"}
    fields = set(re.findall(r"\bpl\.(\w+)", player))
    assert fields, "expected the player JS to read payload fields via pl.*"
    assert fields <= contract, fields - contract
    stat_fields = set(re.findall(r"\bst\.(\w+)", player))
    assert {"week_rel", "cum_rel"} == stat_fields, stat_fields
    for m in ("ensemble", "pf", "analogue", "pf2s",
              "FluSight-baseline", "FluSight-ensemble"):
        assert m in player, m


def test_real_plotly_embedded(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch, stub_plotly=False)
    html = report_season.build_season_report(root, SEASON).read_text()
    assert "<script src" not in html          # inline, not referenced
    assert "Plotly" in html
    assert len(html) > 1_000_000              # the real library is embedded


def test_empty_season_raises_unknown_week(tmp_path):
    with pytest.raises(playback.UnknownWeek):
        report_season.build_season_report(tmp_path / "empty", SEASON)


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
