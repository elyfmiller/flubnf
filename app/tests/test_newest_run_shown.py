"""The run a page shows is the newest real-time run, whatever its model
settings (the 2026-11-27 decision, after every round from 2026-10-31 ran
with the upper-tail cap and Home kept showing the run of 2026-10-24).

  * Home's map and run line, its Weekly report (/output/report), the
    model pages and the server's warm pass show the newest real-time run
    that wrote forecasts, a run with modified settings included; Home and
    the model pages mark such a run "modified settings", once, and never
    a run on the shipped settings;
  * a research run is still never shown there, and a vintage backtest
    never replaces a real-time run.

The archive's side of the decision: test_modified_run_archive.py.
"""
import json
import sys
import threading
from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                               # noqa: E402
from app.core import knobs as K                                # noqa: E402
from app.core.runs import Ledger, RunSpec                      # noqa: E402
from app.ui import server as srv                               # noqa: E402
from app.ui import shared as ui_shared                         # noqa: E402
from app.ui import state as ui_state                           # noqa: E402
from app.ui import versions as V                               # noqa: E402
from app.ui.routes import home as H                            # noqa: E402
from app.ui.routes import output as O                          # noqa: E402

client = TestClient(srv.app)
GH = "NAU_PyBNF-GroundHogCGR"
DATE = "2098-01-03"
FAN = {"1": {"0.5": 10.0}}
#: Home's map cards, as the report bundle gives them (test_home_map's)
PROBS = {"large_decrease": .02, "decrease": .12, "stable": .45,
         "increase": .30, "large_increase": .11}
CARDS = {"04": {"abbr": "AZ", "name": "Arizona", "probs": PROBS,
                "hover_html": "<b>Arizona</b>"}}
MOD = {"oracle.w": 0.25}


@pytest.fixture()
def root(tmp_path, monkeypatch):
    before = dict(ui_state._status)
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    ui_state._status["running"] = None
    ui_state._status["workroot"] = None
    ui_shared._invalidate_scans()
    yield tmp_path
    ui_state._status.clear()
    ui_state._status.update(before)
    ui_shared._invalidate_scans()


@pytest.fixture()
def home_map(monkeypatch):
    """Home draws its map for any stored run (the cards stand in for the
    run's report bundle), past the cold first paint."""
    monkeypatch.setattr(H, "_outlook_ready", lambda: True)
    monkeypatch.setattr(H, "_outlook_cards", lambda res, rid: (CARDS, {}))
    monkeypatch.setattr(H, "_outlook_models", lambda rid: {})


def _run(root, tag, knobs=None, override="", mode="realtime", asof=DATE,
         extra=None) -> str:
    """A closed run of both models on one state, as the pipeline leaves
    it: a Groundhog file (under the -modified name for modified settings
    without the override), knobs.json for modified settings, a weekly
    report and results.json; its id."""
    import time
    time.sleep(1.05)                     # run ids sort by their start second
    ex = {"mode": mode, **(extra or {})}
    if knobs:
        K.write_extra(knobs, ex, override=override)
    spec = RunSpec(engine="all", forecast_date=asof, locations=["Ohio"],
                   extra=ex)
    led = Ledger()
    rid = led.open_run(spec, Path("pending"), {})
    w = root / "workroots" / rid
    gh = GH + ("" if K.hub_names(spec) else K.MODIFIED_SUFFIX)
    d = w / "submission" / gh
    d.mkdir(parents=True)
    (d / f"{O._reference_date(asof)}-{gh}.csv").write_text(tag)
    if K.modified(spec):
        K.write_record(w / "knobs.json", spec)
    (w / "report.html").write_text(f"<html><body>REPORT {tag}</body></html>")
    (w / "results.json").write_text(json.dumps(
        {"forecast_date": asof, "spec": json.dumps(asdict(spec)),
         "models": {"analogue": {"Ohio": FAN}}}))
    led.set_workroot(rid, w)
    led.close_run(rid, "ok", {"knobs": K.summary(K.record_of(spec),
                                                 K.override_reason(spec))}
                  if K.modified(spec) else {})
    ui_shared._invalidate_scans()
    return rid


def _run_line(html: str) -> str:
    return html.split('id="hm-run"', 1)[1].split("</p>", 1)[0]


# ------------------------------------------------- Home and its weekly report

def test_home_shows_the_newest_real_time_run_badged_when_modified(root,
                                                                  home_map):
    shipped = _run(root, "shipped")
    mod = _run(root, "modified", knobs=MOD)
    html = client.get("/").text
    line = _run_line(html)
    assert f'href="/runs/{mod}"' in line and shipped not in html
    # the kit's warn badge, once, on the run line the map and report share
    assert ('<span class="uk-badge uk-badge--warn" id="hm-mod" '
            'data-state="warn">') in line
    assert '<span class="uk-badge-t">modified settings</span>' in line
    assert html.count('id="hm-mod"') == 1
    assert '<a class="btn quiet hm-report" href="/output/report">' in html
    # its Weekly report button and map link serve that run's report
    assert "REPORT modified" in client.get("/output/report").text
    r = client.get("/output/report/download")
    assert r.status_code == 200 and "REPORT modified" in r.text
    # a newer run on the shipped settings: shown, never badged
    again = _run(root, "shipped again")
    html = client.get("/").text
    assert f'href="/runs/{again}"' in _run_line(html)
    assert 'id="hm-mod"' not in html and "modified settings" not in html
    assert "REPORT shipped again" in client.get("/output/report").text


def test_an_override_run_is_badged_on_home_as_the_model_pages_badge_it(
        root, home_map):
    over = _run(root, "override", knobs=MOD, override="the lead asked")
    line = _run_line(client.get("/").text)
    assert f'href="/runs/{over}"' in line and 'id="hm-mod"' in line


def test_a_research_run_is_never_shown_and_a_vintage_run_never_replaces(
        root, home_map):
    mod = _run(root, "modified", knobs=MOD)
    # newer: a research run (the plain filter) and a backtest of a past week
    _run(root, "research", extra={"oracle": "none"})
    vintage = _run(root, "backtest", mode="vintage", asof="2097-12-27")
    assert ui_shared._latest_results()[0] == mod
    assert f'href="/runs/{mod}"' in _run_line(client.get("/").text)
    assert "REPORT modified" in client.get("/output/report").text
    # the Forecast tab draws the newest run, the backtest
    assert ui_shared._latest_results(newest=True)[0] == vintage


def test_the_servers_warm_pass_draws_the_run_home_shows(root, monkeypatch):
    _run(root, "shipped")
    mod = _run(root, "modified", knobs=MOD)
    seen = []
    monkeypatch.setattr(srv.home_routes, "_outlook_block",
                        lambda rid: seen.append(rid) or {})
    monkeypatch.setattr(V, "_warm_versions", lambda: None)
    monkeypatch.setattr(srv.sandbox_routes, "_sandbox_warm", lambda: None)
    monkeypatch.setattr(ui_state.data_mod, "vintages", lambda: [])

    class _Now:
        """threading.Thread that runs its target in place."""
        def __init__(self, target=None, **_k):
            self.target = target

        def start(self):
            self.target()
    monkeypatch.setattr(threading, "Thread", _Now)
    srv._start_background_warm()
    assert seen == [mod]


# -------------------------------------------------------------- the model pages

def test_the_model_page_shows_the_newest_run_badged_when_modified(root):
    shipped = _run(root, "shipped")
    mod = _run(root, "modified", knobs=MOD)
    html = " ".join(client.get("/model/analogue").text.split())
    assert "Latest real-time run" in html
    assert f'href="/runs/{mod}"' in html and f'href="/runs/{shipped}"' not in html
    assert ('id="md-mod" data-state="warn">' in html
            and '<span class="uk-badge-t">modified settings</span>' in html)
    # it is the Forecast tab's newest run too: nothing newer to point to
    assert "Newer run on the Forecast tab" not in html
    _run(root, "shipped again")
    html = client.get("/model/analogue").text
    assert 'id="md-mod"' not in html
