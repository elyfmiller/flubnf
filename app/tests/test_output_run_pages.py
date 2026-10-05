"""Output, the run page and Storage after the 2026-10-05 design pass.

  * Output: the round open now is outlined and its Download buttons are
    the primary; its badge says the time left (an error under 12 h) and
    names the close in the reader's clock; a date a console run is writing
    says so; past and record dates take one line each; the earlier-weeks
    picker names a week by its reference date and leaves out the one shown
    above it; a modified file carries one badge; names break at "_" and
    "-"; each file offers Copy path and the hub validator's command.
  * Show in folder returns to the page that asked and warns when nothing
    opened.
  * The run page: a progress card while the run goes, which run's files
    Output shows for its date, Output's file rows, one medians table with
    a model switch (h0 to h3, US first, thousands separators), and the
    Forecast tab for a real-time hub run.
  * Storage: the ledger leads with a filter and says when it holds more
    rows than it shows; rows by round; one heading notice for the report
    archives while a run is on.
"""
import datetime as dt
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
from app.ui.routes import storage as ui_storage                # noqa: E402

client = TestClient(srv.app)
GH, OR = "NAU_PyBNF-GroundHogCGR", "NAU_PyBNF-OracleSIHRS"


@pytest.fixture()
def root(tmp_path, monkeypatch):
    before = dict(ui_state._status)
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    from app.core import datasets as datasets_mod
    monkeypatch.setattr(datasets_mod, "ROOT", tmp_path / "datasets")
    for k in ("running", "workroot", "phase", "flash", "flash_kind",
              "flash_detail"):
        ui_state._status[k] = None
    ui_shared._invalidate_scans()
    yield tmp_path
    ui_state._status.clear()
    ui_state._status.update(before)
    ui_shared._invalidate_scans()


def _run(root, asof, dirs, status="ok", outcome=None, report=False,
         extra=None) -> str:
    """A closed ledger row and its workroot with a file per model dir."""
    import time
    time.sleep(1.05)                     # run ids sort by their start second
    led = Ledger()
    rid = led.open_run(RunSpec(engine="all", forecast_date=asof,
                               locations=["Ohio"], extra=extra or {}),
                       Path("pending"), {})
    w = root / "workroots" / rid
    ref = O._reference_date(asof)
    for m in dirs:
        d = w / "submission" / m
        d.mkdir(parents=True)
        (d / f"{ref}-{m}.csv").write_text("x")
    w.mkdir(parents=True, exist_ok=True)
    (w / "results.json").write_text(json.dumps({
        "forecast_date": asof, "spec": "",
        "models": {OR: {"Ohio": {"1": {"0.5": 1234.4}, "2": {"0.5": 2},
                                 "3": {"0.5": 3}, "4": {"0.5": 4}},
                        "US": {"1": {"0.5": 12345.6}, "2": {"0.5": 5},
                               "3": {"0.5": 6}, "4": {"0.5": 7}}}}}))
    if report:
        (w / "report.html").write_text("<p>r</p>")
    led.set_workroot(rid, w)
    if status != "running":
        led.close_run(rid, status, outcome or {})
    ui_shared._invalidate_scans()
    return rid


def _due(ref, today=None, now=None):
    """_date_status as if the round for `ref` were open, 2 days 8 h left."""
    return {"state": "due", "text": "Due Wed 2098-01-07, 11 PM ET.",
            "left": "2 days 8 h left", "urgent": False,
            "deadline": "2098-01-08T04:00:00Z",
            "badge": ("warn", "Due Wed 2098-01-07, 11 PM ET · 2 days 8 h left")}


# ------------------------------------------------------- the window badge

def test_the_due_badge_counts_down_and_turns_error_in_the_last_12_hours():
    utc = dt.timezone.utc
    # 11 PM EDT on Wed 2026-10-07 is 03:00 UTC on the Thursday
    s = O._date_status("2026-10-10", now=dt.datetime(2026, 10, 5, 19, tzinfo=utc))
    assert s["state"] == "due" and s["left"] == "2 days 8 h left"
    assert s["badge"] == ("warn",
                          "Due Wed 2026-10-07, 11 PM ET · 2 days 8 h left")
    late = O._date_status("2026-10-10",
                          now=dt.datetime(2026, 10, 8, 0, 0, tzinfo=utc))
    assert late["urgent"] and late["badge"] == (
        "error", "Due Wed 2026-10-07, 11 PM ET · 3 h left")
    assert O._time_left(dt.datetime(2026, 1, 1, 1, tzinfo=utc),
                        dt.datetime(2026, 1, 1, 0, 20, tzinfo=utc)) \
        == "40 min left"


def test_the_close_is_eastern_in_winter_too():
    # 11 PM EST is 04:00 UTC the next day
    assert O._deadline_utc(dt.date(2027, 1, 13)).strftime("%Y-%m-%dT%H:%MZ") \
        == "2027-01-14T04:00Z"


# ---------------------------------------------------------------- Output

def test_the_open_round_stands_out_and_its_downloads_lead(root, monkeypatch):
    monkeypatch.setattr(O, "_date_status", _due)
    _run(root, "2098-01-03", [OR, GH], report=True)
    html = client.get("/output").text
    card = html.split('id="fc-2098-01-03"', 1)[0].rsplit("<div", 1)[1]
    assert "out-day--due" in card
    body = html.split('id="fc-2098-01-03"', 1)[1]
    assert body.count('<a class="btn gold" href="/output/download') == 2
    assert "2 days 8 h left" in body
    # the close in the reader's clock is filled in by the page
    assert 'data-out-local="2098-01-08T04:00:00Z"' in body
    # the report's download steps back while a round is open
    assert '<a class="btn quiet" href="/runs/' in html.split(
        'id="weekly-report"', 1)[1].split("Download report", 1)[0]


def test_a_date_a_run_is_writing_says_so(root):
    _run(root, "2098-01-03", [GH])
    live = _run(root, "2098-01-03", [], status="running")
    ui_state._status["running"] = "all:" + live
    html = client.get("/output").text
    card = html.split('id="fc-2098-01-03"', 1)[1]
    assert '<span class="uk-badge-t">newer run in progress</span>' in card
    assert '<a href="/forecast">Open Forecast</a>' in card


def test_past_dates_are_lines_and_the_picker_reads_by_round(root):
    for asof in ("2098-01-03", "2098-01-10"):
        rid = _run(root, asof, [GH], report=True)
        a = root / "archive" / asof
        a.mkdir(parents=True)
        (a / "report.html").write_text("r")
    html = client.get("/output").text
    # the newest date is a card, the earlier one a line with its download
    assert 'class="card out-day" id="fc-2098-01-10"' in html
    line = html.split('<div class="out-line" id="fc-2098-01-03">', 1)[1] \
        .split("</div>", 1)[0]
    assert 'aria-label="Download 2098-01-10-NAU_PyBNF-GroundHogCGR.csv"' in line
    # the picker: earlier weeks only, each by its reference date
    picker = html.split('id="archreport"', 1)[1].split("</select>", 1)[0]
    assert '<option value="2098-01-03">2098-01-10 (as of 2098-01-03)</option>' \
        in picker
    assert 'value="2098-01-10"' not in picker
    assert rid


def test_a_modified_file_has_one_badge_and_names_break_at_separators(root):
    _run(root, "2098-01-03", [GH + "-modified"])
    html = client.get("/output").text
    card = html.split('id="fc-2098-01-03"', 1)[1]
    assert card.count("modified settings</span>") == 1
    assert "non-hub name</span>" not in card
    assert ("2098-<wbr>01-<wbr>10-<wbr>NAU_<wbr>PyBNF-<wbr>GroundHogCGR-<wbr>"
            "modified.csv") in card
    assert 'download="2098-01-10-NAU_PyBNF-GroundHogCGR-modified.csv"' in card


def test_each_file_copies_its_path_and_the_validator_command(root):
    from flubnf.settings import HUB
    rid = _run(root, "2098-01-03", [GH])
    path = root / "workroots" / rid / "submission" / GH \
        / f"2098-01-10-{GH}.csv"
    html = client.get("/output").text
    assert f'data-copy="{path}"' in html
    cmd = O.validator_command(str(path), window=False)
    assert cmd == (f'Rscript "{O.VALIDATOR}" "{path}" "{HUB}"')
    assert O.VALIDATOR.is_file()
    assert O.validator_command("x.csv", window=True).endswith(" --window")
    from markupsafe import escape
    assert f'data-copy="{escape(cmd)}"' in html
    assert "navigator.clipboard" in html and "execCommand('copy')" in html


def test_show_in_folder_goes_back_and_warns_when_nothing_opened(root,
                                                                monkeypatch):
    import subprocess
    rid = _run(root, "2098-01-03", [GH])
    f = root / "workroots" / rid / "submission" / GH / f"2098-01-10-{GH}.csv"
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: None)
    r = client.post("/output/reveal", data={"path": str(f)},
                    headers={"referer": f"http://testserver/runs/{rid}"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/runs/{rid}"
    assert not ui_state._status.get("flash")
    r = client.post("/output/reveal", data={"path": str(root / "gone.csv")},
                    headers={"referer": "http://testserver/output"},
                    follow_redirects=False)
    assert r.headers["location"] == "/output"
    assert "Nothing opened" in ui_state._status.get("flash", "")
    assert ui_state._status.get("flash_kind") == "warn"


# -------------------------------------------------------------- run page

def test_a_failed_run_names_the_run_output_shows(root):
    failed = _run(root, "2098-01-03", [], status="failed",
                  outcome={"error": "boom"})
    ok = _run(root, "2098-01-03", [OR, GH])
    page = client.get(f"/runs/{failed}").text
    sup = page.split('id="run-supersession"', 1)[1].split("</div>", 1)[0]
    assert "Superseded." in sup and f'href="/runs/{ok}"' in sup
    good = client.get(f"/runs/{ok}").text
    assert "Output shows this run&#39;s files for 2098-01-10." in good


def test_a_running_run_shows_one_progress_card(root):
    live = _run(root, "2098-01-03", [], status="running")
    ui_state._status["running"] = "all:" + live
    ui_state._status["phase"] = "fitting 3 of 53"
    page = client.get(f"/runs/{live}").text
    assert 'id="run-progress"' in page and "fitting 3 of 53" in page
    assert 'href="/forecast"' in page.split('id="run-progress"', 1)[1]
    assert "Submission files" not in page and 'id="run-noresults"' not in page


def test_the_run_page_lists_files_as_output_does(root):
    rid = _run(root, "2098-01-03", [GH, OR])
    page = client.get(f"/runs/{rid}").text
    subs = page.split('class="card fc-subs"', 1)[1]
    assert subs.index(OR) < subs.index(GH)            # the Oracle SIHRS first
    assert subs.count("Show in folder") == 2
    assert "hub check" in subs                         # its checks badge
    assert 'href="/static/tabs/output.css"' in page


def test_the_medians_are_one_table_by_hub_horizon(root):
    rid = _run(root, "2098-01-03", [GH])
    page = client.get(f"/runs/{rid}").text
    med = page.split('id="run-medians"', 1)[1]
    assert '<th class="num">h0</th>' in med and "1 wk" not in med
    assert med.index("<td>US</td>") < med.index("<td>Ohio</td>")
    assert '<td class="num">12,346</td>' in med and \
        '<td class="num">1,234</td>' in med
    t = O.median_table({"A": {"Ohio": {"1": 1}}, "B": {"Ohio": {"1": 2}}})
    assert list(t["models"]) == ["A", "B"] and t["hs"][0] == "h0"


def test_a_real_time_hub_run_sits_under_forecast(root):
    rid = _run(root, "2098-01-03", [GH])
    page = client.get(f"/runs/{rid}").text
    assert '<a class="tab active" href="/forecast"' in page
    res = _run(root, "2098-01-03", [GH], extra={"members": 3})
    page = client.get(f"/runs/{res}").text
    assert '<a class="tab active" href="/storage"' in page


# --------------------------------------------------------------- Storage

def test_storage_rows_read_by_round_and_status(root):
    failed = _run(root, "2098-01-03", [], status="failed",
                  outcome={"error": "boom"})
    html = client.get("/storage").text
    row = html.split(f'data-wid="{failed}"', 1)[1].split("</div>", 1)[0]
    assert "Round 2098-01-10 (as of 2098-01-03)" in row
    assert '<span class="uk-badge-t">failed</span>' in row
    led = html.split('id="ledgerfold"', 1)[1].split("</details>", 1)[0]
    assert ('<span class="st-nw">as of 2098-01-03 ·</span> '
            '<span class="st-nw">run ') in led
    assert 'id="st-filter"' in led and 'data-lf="research"' in led
    assert 'data-st="failed"' in led
    assert 'id="st-cap"' not in led


def test_the_ledger_says_when_it_holds_more_than_it_shows(root, monkeypatch):
    _run(root, "2098-01-03", [GH])
    _run(root, "2098-01-10", [GH])
    monkeypatch.setattr(ui_storage, "LEDGER_ROWS", 1)
    html = client.get("/storage").text
    assert "Showing the newest 1 of 2 runs." in html


def test_report_archives_carry_one_notice_while_a_run_is_on(root):
    for d in ("2098-01-03", "2098-01-10"):
        (root / "archive" / d).mkdir(parents=True)
        (root / "archive" / d / "report.html").write_text("r")
    ui_state._status["running"] = "all:20980101T000000-abcdef"
    ui_shared._invalidate_scans()
    html = client.get("/storage").text
    sec = html.split('aria-labelledby="h-st-rp"', 1)[1].split("</section>", 1)[0]
    assert sec.count("console run in progress") == 1
    assert sec.count(" disabled ") == 2               # each Delete, with why


def test_the_research_start_is_off_with_its_reason_during_a_run(root):
    ui_state._status["running"] = "all:20980101T000000-abcdef"
    t = client.get("/model/pf2s").text
    card = t.split('id="research-run"', 1)[1].split("</form>", 1)[0]
    assert 'data-uk-reason="rr-start-why"' in card and " disabled " in card
    assert '<span id="rr-particles-n">particles</span>' in card
    ui_state._status["running"] = None
    t = client.get("/model/pf2s").text
    card = t.split('id="research-run"', 1)[1].split("</form>", 1)[0]
    assert "rr-start-why" not in card
