"""No page or download is answered from a cache (shared._no_store).

Without a Cache-Control header a browser or WebView2 may reuse a stored
response heuristically: an Output page that names an earlier run's files,
or yesterday's weekly report under its unchanged URL. Every response but
/static/'s says no-store; the static files keep their ETag and 304s, and
a route that sets its own header (the sandbox zips) keeps it.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                               # noqa: E402
from app.core.runs import Ledger, RunSpec                      # noqa: E402
from app.ui import server as srv                               # noqa: E402
from app.ui import shared as ui_shared                         # noqa: E402
from app.ui import state as ui_state                           # noqa: E402
from app.ui.routes import output as O                          # noqa: E402
from app.ui.routes import retro as ui_retro                    # noqa: E402
from app.ui.routes import sandbox as ui_sandbox                # noqa: E402

client = TestClient(srv.app)
OR = "NAU_PyBNF-OracleSIHRS"
ASOF = "2098-01-03"


@pytest.fixture()
def run(tmp_path, monkeypatch):
    """One closed run with a CSV and a report, archived for its as-of;
    the season report and replay bundle builders stand in."""
    before = dict(ui_state._status)
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    ui_state._status["running"] = None
    led = Ledger()
    rid = led.open_run(RunSpec(engine="all", forecast_date=ASOF,
                               locations=["Ohio"]), Path("pending"), {})
    w = tmp_path / "workroots" / rid
    d = w / "submission" / OR
    d.mkdir(parents=True)
    csv = d / f"{O._reference_date(ASOF)}-{OR}.csv"
    csv.write_text("reference_date,location,value\n")
    (w / "report.html").write_text("<html><body>report</body></html>")
    (w / "results.json").write_text(json.dumps(
        {"forecast_date": ASOF, "spec": "", "models": {}}))
    led.set_workroot(rid, w)
    led.close_run(rid, "ok", {})
    a = tmp_path / "archive" / ASOF
    a.mkdir(parents=True)
    (a / "report.html").write_text("<html><body>archived</body></html>")
    season = tmp_path / "season-report.html"
    season.write_text("<html>season</html>")
    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"PK\x05\x06" + b"\0" * 18)
    monkeypatch.setattr(ui_retro, "_season_report", lambda s, a: season)
    monkeypatch.setattr(ui_retro, "_export_bundle", lambda s, a: bundle)
    monkeypatch.setattr(ui_sandbox.sandbox_mod, "model_zip",
                        lambda name: b"PK\x05\x06" + b"\0" * 18)
    ui_shared._invalidate_scans()
    yield rid, csv
    ui_state._status.clear()
    ui_state._status.update(before)
    ui_shared._invalidate_scans()


def test_pages_and_downloads_say_no_store(run):
    rid, csv = run
    for url, params in (
            ("/output", None),
            ("/output/download", {"path": str(csv)}),
            ("/output/report/download", None),
            ("/output/report/download", {"date": ASOF}),
            ("/output/report", None),
            (f"/runs/{rid}/report/download", None),
            (f"/runs/{rid}", None),
            ("/retro/2025-26/report", None),
            ("/retro/2025-26/export", None),
            ("/forecast", None),
            ("/api/busy", None)):
        r = client.get(url, params=params)
        assert r.status_code == 200, (url, r.status_code)
        assert r.headers.get_list("cache-control") == ["no-store"], url
    # a refusal and a missing file too
    assert client.get("/output/download", params={
        "path": "/nowhere"}).headers["cache-control"] == "no-store"
    bad = client.get("/output", headers={"host": "evil.example"})
    assert bad.status_code == 403 and bad.headers["cache-control"] == \
        "no-store"


def test_a_routes_own_header_stands_once(run):
    r = client.get("/sandbox/models/m/download")
    assert r.status_code == 200
    assert r.headers.get_list("cache-control") == ["no-store"]


def test_static_files_stay_cacheable(run):
    r = client.get("/static/charts.js")
    assert r.status_code == 200 and "cache-control" not in r.headers
    again = client.get("/static/charts.js",
                       headers={"if-none-match": r.headers["etag"]})
    assert again.status_code == 304
