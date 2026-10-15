"""The Forecast tab's run mechanics and its explainers (the 2026-10-15
bug hunt).

  * the fans draw the newest run, its settings modified or not (badged);
    Home and Output keep to the shipped real-time run, and a vintage
    backtest never replaces it (M4, M5);
  * the forecasts come before the latest run's record;
  * the live run is read once, so a run that ends while the page is built
    still shows its Running card (M7);
  * the Weekly report link needs the report's file (M9);
  * the anchor line says why a typed Saturday has no week (M8), and hides
    when it has nothing to say;
  * the relWIS note only beside a relWIS; the run page's Modified model
    settings card holds the reason and the digest;
  * one explainer on the Settings card; a label with no tip has no "?".
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                             # noqa: E402
from app.core import knobs as K                              # noqa: E402
from app.core.runs import (Ledger, RunSpec, results_html,     # noqa: E402
                           results_tip)
from app.ui import server as srv                             # noqa: E402
from app.ui import shared as ui_shared                       # noqa: E402
from app.ui import state as ui_state                         # noqa: E402
from app.ui.routes import forecast as ui_forecast            # noqa: E402

client = TestClient(srv.app)
TEMPLATE = (Path(__file__).resolve().parents[1] / "ui" / "templates"
            / "forecast.html").read_text(encoding="utf-8")
#: one location's stored quantiles, as results.json holds a model's fans
FANS = {"pf": {"Ohio": {"1": {"0.1": 1.0, "0.5": 2.0, "0.9": 3.0}}}}


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    status_before, form_before = dict(ui_state._status), dict(ui_state._last_form)
    ui_state._status["running"] = None
    ui_shared._invalidate_scans()
    yield tmp_path
    ui_state._status.clear(); ui_state._status.update(status_before)
    ui_state._last_form.clear(); ui_state._last_form.update(form_before)
    ui_shared._invalidate_scans()


def _run(mode="realtime", knobs=None, override="", status="ok",
         results=True, report=False, date="2098-01-03"):
    """A finished console run: its ledger row and workroot (results.json
    with one fan; report.html when asked)."""
    extra = ui_forecast._run_extra(2, mode)
    if knobs:
        K.write_extra(knobs, extra, override=override)
    spec = RunSpec(engine="all", forecast_date=date, locations=["Ohio"],
                   extra=extra)
    led = Ledger()
    rid = led.open_run(spec, Path("pending"), {})
    w = runs_mod.APP_STATE / "workroots" / rid
    w.mkdir(parents=True)
    if report:
        (w / "report.html").write_text("<html></html>", encoding="utf-8")
    led.close_run(rid, status, {"report": str(w / "report.html")} if report else {})
    if results:
        (w / "results.json").write_text(json.dumps(
            {"spec": spec.to_json(), "forecast_date": date, "models": FANS}),
            encoding="utf-8")
    ui_shared._invalidate_scans()
    return rid


# --- the run the fans draw (M4, M5) ---------------------------------------------------

def test_the_forecast_tab_draws_the_newest_run_with_modified_settings(state):
    """M4: a run with modified settings (non-hub file names) showed "No
    forecasts yet", or an older run badged "earlier run" with a false
    reason. The Forecast tab draws it, badged; Home and Output keep to
    the shipped run."""
    shipped = _run()
    modified = _run(knobs={"oracle.w": 0.25})
    html = client.get("/forecast").text
    assert f'<a href="/runs/{modified}" id="fc-fan-run">' in html
    assert ('id="fc-fan-mod" data-state="warn">' in html
            and ">modified settings</span>" in html)
    assert 'id="fc-fan-earlier"' not in html
    assert ui_shared._latest_results()[0] == shipped
    # with no shipped run at all, Home and Output show none
    shutil.rmtree(runs_mod.APP_STATE / "workroots" / shipped)
    ui_shared._invalidate_scans()
    assert ui_shared._latest_results() == (None, None)
    assert ui_shared._latest_results(include_modified=True, newest=True)[0] == modified


def test_an_earlier_run_says_why_the_newest_is_not_drawn(state):
    drawn = _run()
    _run(status="error", results=False)
    html = client.get("/forecast").text
    assert f'<a href="/runs/{drawn}" id="fc-fan-run">' in html
    assert ">earlier run · newest failed</span>" in html
    assert "left no forecasts to draw" not in html


def test_a_vintage_run_never_replaces_the_current_forecast(state):
    """M5: a backtest replaced Home's map and Output's Weekly report card
    with an old week. They keep the newest real-time run; the Forecast
    tab draws the newest run whatever its week."""
    live = _run("realtime", date="2098-01-03")
    backtest = _run("vintage", date="2097-12-06")
    assert ui_shared._latest_results()[0] == live
    assert ui_shared._latest_results(include_modified=True, newest=True)[0] == backtest
    # a research run is never shown, wherever
    research = _run("realtime")
    row_spec = json.loads((runs_mod.APP_STATE / "workroots" / research
                           / "results.json").read_text())
    row_spec["research"] = True
    (runs_mod.APP_STATE / "workroots" / research / "results.json").write_text(
        json.dumps(row_spec))
    ui_shared._invalidate_scans()
    assert ui_shared._latest_results()[0] == live
    assert ui_shared._latest_results(include_modified=True, newest=True)[0] == backtest


def test_with_no_real_time_run_the_newest_vintage_run_shows(state):
    older = _run("vintage", date="2097-11-29")
    newer = _run("vintage", date="2097-12-06")
    assert ui_shared._latest_results()[0] == newer != older


def test_the_forecasts_come_before_the_latest_runs_record(state):
    _run()
    html = client.get("/forecast").text
    assert html.index('<div id="fanwrap">') < html.index('<div class="card fc-latest">')


# --- the live run read once (M7) -----------------------------------------------------

def _running_row():
    spec = RunSpec(engine="all", forecast_date="2098-01-03", locations=["Ohio"])
    return Ledger().open_run(spec, Path("pending"), {})     # stays 'running'


def test_a_run_ending_mid_render_still_shows_its_running_card(state, monkeypatch):
    """M7: the page read the run's state twice; a run that ended between
    the reads left a 'running' badge with no Running card and no poll."""
    rid = _running_row()
    ui_state._status.update({"running": f"all:{rid}", "run_label": "x",
                             "workroot": None, "expected_total": None})
    rows = Ledger.rows

    def ends_now(self, *a, **kw):
        out = rows(self, *a, **kw)
        ui_state._status["running"] = None        # the run ends here
        return out
    monkeypatch.setattr(Ledger, "rows", ends_now)
    html = client.get("/forecast").text
    # the Running card, whose poll sees the end and reloads the page
    assert '<div class="card fc-running">' in html
    assert 'class="card fc-latest"' not in html


def test_a_run_starting_mid_render_is_never_called_interrupted(state, monkeypatch):
    rid = _running_row()
    rows = Ledger.rows

    def starts_now(self, *a, **kw):
        out = rows(self, *a, **kw)
        ui_state._status.update({"running": f"all:{rid}", "run_label": "x",
                                 "workroot": None, "expected_total": None})
        return out
    monkeypatch.setattr(Ledger, "rows", starts_now)
    html = client.get("/forecast").text
    assert '<div class="card fc-running">' in html
    assert ">interrupted</span>" not in html


# --- the Weekly report link (M9) ------------------------------------------------------

def test_the_weekly_report_link_needs_the_reports_file(state):
    rid = _run(report=True)
    html = client.get("/forecast").text
    assert f'href="/runs/{rid}/report"' in html
    # Storage deleted the workroot: no link to a 404
    (runs_mod.APP_STATE / "workroots" / rid / "report.html").unlink()
    html = client.get("/forecast").text
    assert f'href="/runs/{rid}/report"' not in html


# --- the anchor line (M8, vis-8) ------------------------------------------------------

def _anchor_js():
    """The page script's anchorFor and noWeek, runnable alone."""
    body = TEMPLATE.split("function anchorFor(day) {")[1]
    fn = "function anchorFor(day) {" + body.split("// the round row")[0]
    return fn.replace('{{ ("No week of this dataset dated " if dataset else '
                      '"No snapshot dated ") | tojson }}', '"No snapshot dated "') \
             .replace('{{ ("No week of this dataset on or before " if dataset '
                      'else "No archived week on or before ") | tojson }}',
                      '"No archived week on or before "')


@pytest.mark.skipif(not shutil.which("node"), reason="no node")
def test_a_saturday_with_no_week_says_why():
    """M8: a typed Saturday the archive skipped read "No archived week on
    or before" it, which was false; so did one past the data. Each now
    says what the run's refusal will."""
    js = ("var VS = ['2025-01-04', '2025-01-11', '2025-01-25'];\n" + _anchor_js()
          + "\nconsole.log(JSON.stringify(['2025-01-18', '2027-01-02', "
            "'2024-12-28', '2025-01-20'].map(function (d) {"
            " return [anchorFor(d), anchorFor(d) ? '' : noWeek(d)]; })));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [
        [None, "No snapshot dated 2025-01-18; nearest earlier 2025-01-11."],
        [None, "No data for 2027-01-02 yet; the data ends at 2025-01-25."],
        [None, "No archived week on or before 2024-12-28."],
        ["2025-01-11", ""]]


def test_the_anchor_line_hides_when_it_has_nothing_to_say():
    """vis-8: a typed Saturday that is its own archived week left an
    empty 20 px line under the date."""
    assert ('{% if kv_off and live_off %} hidden{% endif %}>' in TEMPLATE)
    assert ("line.hidden = !!a && (!kv || kv.hidden) && (!live || live.hidden);"
            in TEMPLATE)
    css = (Path(__file__).resolve().parents[1] / "ui" / "static" / "tabs"
           / "forecast.css").read_text()
    assert ".fc-anchor[hidden]{display:none}" in css


# --- the explainers -------------------------------------------------------------------

def test_the_relwis_note_only_beside_a_relwis():
    scored = results_html({"pf_relwis": 0.7, "pf_cells": 1}, "{}")
    assert 'aria-describedby="tip-res-note"' in scored
    # nothing scored yet (a real-time run): no convention to explain
    early = results_html({"pf_cells": 2, "submissions": {"a": "x"}}, "{}")
    assert "res-note" not in early
    assert results_tip("{}", {"pf_cells": 2}) == ""
    assert "tip-res-note" in results_tip("{}", {"analogue_relwis": 0.9})
    assert "tip-res-note" in results_tip("{}")


def test_the_run_page_holds_the_reason_and_the_digest(state):
    """The settings rows say how the files were named; the reason and
    the digest live on the run page's Modified model settings card, once
    each, with no "?" to restate them."""
    rid = _run(knobs={"oracle.w": 0.25}, override="lead's call, week 42")
    html = client.get(f"/runs/{rid}").text
    card = html.split('id="modified-note"')[1].split("</div>\n</div>")[0]
    assert "<q>lead&#39;s call, week 42</q>" in card
    assert f"<code>{K.digest({'oracle.w': 0.25})}</code>" in card
    assert "hub names, by override" in card
    assert 'class="tipbtn"' not in card
    assert html.count("lead&#39;s call, week 42") == 1
    # nothing scored yet: no relWIS note on the Results card either
    assert "tip-res-note" not in html


def test_the_weekly_report_keeps_the_override_reason():
    """The weekly report opens without the app, so it keeps why the files
    took the hub names, after its "files" row; the console's cards keep
    the reason to the run page."""
    def spec(override):
        extra = ui_forecast._run_extra(2, "realtime")
        K.write_extra({"oracle.w": 0.25}, extra, override=override)
        return RunSpec(engine="all", forecast_date="2098-01-03",
                       locations=["Ohio"], extra=extra)
    pairs = runs_mod.report_settings(spec("lead's call, week 42"))
    keys = [k for k, _ in pairs]
    assert keys[keys.index("files") + 1] == "override reason"
    assert dict(pairs)["override reason"] == "lead's call, week 42"
    assert "override reason" not in dict(runs_mod.spec_settings(
        spec("lead's call, week 42")))
    assert runs_mod.report_settings(spec("")) == runs_mod.spec_settings(spec(""))
    src = (Path(__file__).resolve().parents[1] / "ui" / "pipeline.py").read_text()
    assert "report_settings(spec, outcome) + _build_pairs(run_row)" in src


def test_the_settings_card_has_one_explainer(state):
    _run(knobs={"oracle.w": 0.25, "pf.seed_denominator": "season_total_early"},
         override="r")
    html = client.get("/forecast").text
    settings = html.split('<div class="card fc-settings">')[1].split(
        '<div id="results">')[0]
    panel = settings.split('id="model-settings"')[1].split("</details>\n<script")[0]
    outside = settings.replace(panel, "")
    assert 'aria-controls="tt-fc-settings"' in outside
    assert outside.count('class="uk-tt-btn"') == 1
    assert outside.count('class="tipbtn"') == 0
    # the panel's own: one "i", linking every setting on Methods
    assert panel.count('class="tipbtn"') == 0
    assert panel.count('class="uk-tt-btn"') == 1
    assert 'href="/methods#settings"' in panel


def test_a_label_without_a_tip_has_no_question_mark():
    html = srv.templates.env.from_string(
        '{% import "_tips.html" as t %}{{ t.label("Model", "m", for_="x") }}'
        '{{ t.label("Seed", "s", "Why.", for_="y") }}').render()
    assert html.startswith('<div class="lblrow"><label for="x">Model</label></div>')
    assert html.count('class="tipbtn"') == 1 and 'id="tip-s"' in html
