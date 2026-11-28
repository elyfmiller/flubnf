"""One run label on every page (roadmap "Now" #5, review findings B3 and
G-E5).

One run used to carry four date names: the Forecast form's "Forecast date
11/21/2026, Reference date 2026-11-28", Output's "FORECAST 2026-11-28 ...
as of 2026-11-21" (and "Forecast 2026-11-21 ... as of 2026-11-14" for a
different run), the report's "Reference date 2026-11-28 · data through
Nov 21". Now every page names a run one way (app/core/run_label.py,
shared._run_name, tips.runname):

  * "Data through Nov 21 · forecasts for weeks ending Nov 28 to Dec 19",
    the year written only when a date of the label is not this year (then
    on every part, once at the end of a range that shares it);
  * for a hub run, a quieter "FluSight round 2026-11-28" ("Not a FluSight
    round (2026-07-11)" for a week the hub takes no files for); a run on
    your own data never names a round;
  * "Data through" is the week the run recorded reading, else the newest
    week of the series it stored, else its as-of; never later than it.

Output and Storage list runs newest data first, grouped by round, the
round said once per group; file names keep the reference date.
"""
import json
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                               # noqa: E402
from app.core import run_label as RL                           # noqa: E402
from app.core.runs import Ledger, RunSpec                      # noqa: E402
from app.ui import server as srv                               # noqa: E402
from app.ui import shared as ui_shared                         # noqa: E402
from app.ui import state as ui_state                           # noqa: E402
from app.ui.routes import output as O                          # noqa: E402
from app.ui.routes import storage as ui_storage                # noqa: E402

client = TestClient(srv.app)
GH = "NAU_PyBNF-GroundHogCGR"
TODAY = date(2026, 11, 27)


# ------------------------------------------------------------- the words

def test_the_label_names_the_data_and_the_weeks():
    assert RL.text("2026-11-21", today=TODAY) == (
        "Data through Nov 21 · forecasts for weeks ending Nov 28 to Dec 19")
    # the four weeks are horizons 0 to 3: the as-of + 7 to + 28 days
    assert RL.target_weeks("2026-11-21") == [
        date(2026, 11, 28), date(2026, 12, 5), date(2026, 12, 12),
        date(2026, 12, 19)]
    assert RL.reference_date("2026-11-21") == "2026-11-28"


def test_a_year_is_written_only_when_a_date_is_not_this_year():
    # another year: every part carries it, once at the end of a range
    # whose two ends share it
    assert RL.text("2025-11-15", today=TODAY) == (
        "Data through Nov 15, 2025 · forecasts for weeks ending Nov 22 to "
        "Dec 13, 2025")
    # a range across the new year: each end its own
    assert RL.text("2025-12-20", today=TODAY) == (
        "Data through Dec 20, 2025 · forecasts for weeks ending Dec 27, 2025 "
        "to Jan 17, 2026")
    # this year's data whose weeks run into the next: the same rule
    assert RL.text("2026-12-19", today=TODAY) == (
        "Data through Dec 19, 2026 · forecasts for weeks ending Dec 26, 2026 "
        "to Jan 16, 2027")
    # the same date read a year later carries its year
    assert RL.text("2026-11-21", today=date(2027, 2, 1)).startswith(
        "Data through Nov 21, 2026 · ")
    assert RL.span_text("2026-10-24", "2025-11-15", today=TODAY) == \
        "Nov 15, 2025 to Oct 24, 2026"
    assert RL.span_text("2026-09-26", "2026-11-21", today=TODAY) == \
        "Sep 26 to Nov 21"


def test_a_hub_run_names_its_round_and_a_dataset_run_never_does():
    n = RL.name("2026-11-21", today=TODAY)
    assert n["round"] == "FluSight round 2026-11-28"
    assert n["reference"] == "2026-11-28" and n["data_through"] == "2026-11-21"
    # a week the hub takes no files for (its tasks.json rounds)
    assert RL.round_text("2026-07-04") == "Not a FluSight round (2026-07-11)"
    # your own data: no round, ever
    assert RL.name("2026-11-21", hub=False, today=TODAY)["round"] == ""
    # an unreadable date names nothing
    assert RL.name("soon")["text"] == "" and RL.round_text("") == ""


def test_the_data_through_week_is_the_recorded_one_never_after_the_asof(
        tmp_path):
    rec = {"data_source": {"kind": "live", "newest_week": "2026-11-14"}}
    assert RL.data_through("2026-11-21", rec) == "2026-11-14"
    assert RL.data_through("2026-11-21", json.dumps(rec)) == "2026-11-14"
    assert RL.text("2026-11-21", "2026-11-14", today=TODAY) == (
        "Data through Nov 14 · forecasts for weeks ending Nov 28 to Dec 19")
    # a newer week than the as-of is never claimed
    late = {"data_source": {"newest_week": "2026-12-05"}}
    assert RL.data_through("2026-11-21", late) == "2026-11-21"
    # an older run with no record: the newest week of the series it
    # stored, no later than its as-of
    (tmp_path / "results.json").write_text(json.dumps({"observed": {
        "Ohio": [["2026-11-07", 5.0], ["2026-11-14", 6.0]],
        "Utah": [["2026-11-07", 1.0], ["2026-11-28", 2.0]]}}))
    assert RL.data_through("2026-11-21", {}, tmp_path) == "2026-11-14"
    # nothing recorded or stored: the as-of
    assert RL.data_through("2026-11-21", {}, tmp_path / "gone") == "2026-11-21"
    assert RL.data_through("2026-11-21") == "2026-11-21"


# ------------------------------------------------------------- the pages

@pytest.fixture()
def root(tmp_path, monkeypatch):
    before = dict(ui_state._status)
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    for k in ("running", "workroot", "phase", "flash", "flash_kind",
              "flash_detail"):
        ui_state._status[k] = None
    ui_shared._invalidate_scans()
    yield tmp_path
    ui_state._status.clear()
    ui_state._status.update(before)
    ui_shared._invalidate_scans()


def _run(root, asof, through=None, observed=None, dataset=None) -> str:
    """A closed ledger row and its workroot with one hub file; `through`
    the newest week it records reading, `observed` its stored series."""
    import time
    time.sleep(1.05)                     # run ids sort by their start second
    extra = {"dataset": {"id": "clinics-1", "name": dataset}} if dataset \
        else {}
    led = Ledger()
    spec = RunSpec(engine="analogue", forecast_date=asof, locations=["Ohio"],
                   extra=extra)
    rid = led.open_run(spec, Path("pending"), {})
    w = root / "workroots" / rid
    d = w / "submission" / GH
    d.mkdir(parents=True)
    (d / f"{O._reference_date(asof)}-{GH}.csv").write_text("x")
    res = {"forecast_date": asof, "spec": spec.to_json(), "models": {},
           "observed": observed or {}}
    if dataset:
        res["dataset"] = extra["dataset"]
    (w / "results.json").write_text(json.dumps(res))
    led.set_workroot(rid, w)
    out = {"submissions": [GH]}
    if through:
        out["data_source"] = {"kind": "live", "newest_week": through}
    led.close_run(rid, "ok", out)
    ui_shared._invalidate_scans()
    return rid


def test_one_run_reads_the_same_on_every_page(root):
    rid = _run(root, "2098-01-03")
    words = RL.text("2098-01-03")
    when = ui_shared._run_time(rid)
    n = ui_shared._run_name(rid, Ledger().row(rid)["spec"])
    assert n["text"] == words and n["when"] == when
    assert n["round"] == "Not a FluSight round (2098-01-10)"
    # the run page's heading, its round and time under it
    page = client.get(f"/runs/{rid}").text
    assert f"Run: {words}</h1>" in page
    assert f"Not a FluSight round (2098-01-10) · run {when}</p>" in page
    # Output's card for the date, its round once under it
    out = client.get("/output").text
    assert f">{words}</h2>" in out
    # Storage's ledger and its workroot row
    st = client.get("/storage").text
    assert f'<a href="/runs/{rid}">{words}</a>' in st
    # the Forecast tab's Latest run card and the fans' run
    fc = client.get("/forecast").text
    card = fc.split('class="card fc-latest"', 1)[1]
    assert (f'<a href="/runs/{rid}" id="fc-latest-run">{words}</a>'
            f'<span class="uk-run-sub">Not a FluSight round (2098-01-10) · '
            f'run {when}</span>') in card
    # no page names it by a bare date any more
    for html in (page, out, st):
        assert "as of 2098-01-03" not in html
        assert "Reference date" not in html


def test_a_recorded_week_and_a_stored_series_name_the_data(root):
    recorded = _run(root, "2098-01-17", through="2098-01-10")
    older = _run(root, "2098-01-24", observed={
        "Ohio": [["2098-01-03", 1.0], ["2098-01-17", 2.0]]})
    assert ui_shared._run_name(recorded, Ledger().row(recorded)["spec"]
                               )["data_through"] == "2098-01-10"
    assert ui_shared._run_name(older, Ledger().row(older)["spec"]
                               )["data_through"] == "2098-01-17"
    st = client.get("/storage").text
    assert RL.text("2098-01-17", "2098-01-10") in st
    assert RL.text("2098-01-24", "2098-01-17") in st


def test_output_lists_newest_data_first(root):
    # the later as-of read older data than the earlier one: data first
    _run(root, "2098-01-17", through="2098-01-03")
    _run(root, "2098-01-10")
    dates, _own = O.forecast_dates()
    assert [d["asof"] for d in dates] == ["2098-01-10", "2098-01-17"]
    assert [d["name"]["data_through"] for d in dates] == [
        "2098-01-10", "2098-01-03"]


def test_storage_groups_runs_by_round_said_once(root):
    a = _run(root, "2098-01-03")
    b = _run(root, "2098-01-03")
    c = _run(root, "2098-01-10")
    own = _run(root, "2098-01-10", dataset="Clinic admissions")
    rows = Ledger().rows(10)
    for r in rows:
        r["name"] = ui_shared._run_name(r["run_id"], r["spec"],
                                        r.get("outcome"))
    groups = ui_storage._ledger_groups(rows)
    heads = [g["heading"] for g in groups]
    # newest data first: the two groups whose data runs through Jan 10
    # (in the order of their newest run), then Jan 3's round
    assert set(heads[:2]) == {"Not a FluSight round (2098-01-17)",
                              "Clinic admissions"}
    assert heads[2:] == ["Not a FluSight round (2098-01-10)"]
    by = {g["heading"]: [r["run_id"] for r in g["rows"]] for g in groups}
    assert by["Not a FluSight round (2098-01-10)"] == [b, a]   # newest first
    assert by["Not a FluSight round (2098-01-17)"] == [c]
    assert by["Clinic admissions"] == [own]
    # the page: each heading once, as a row over its runs, which then
    # leave the round out of their own names
    led = client.get("/storage").text.split('id="ledgerfold"', 1)[1] \
        .split("</details>", 1)[0]
    assert led.count(">Not a FluSight round (2098-01-10)</span></th>") == 1
    # the heading heads its group's rows (the table has no <colgroup>)
    assert ('<tr class="st-ghead"><th colspan="5" scope="rowgroup"><span '
            'class="uk-run-sub">Not a FluSight round (2098-01-10)</span></th>'
            '</tr>') in led
    assert 'scope="colgroup"' not in led
    assert led.count("Not a FluSight round (2098-01-10)") == 1
    assert '<tbody class="st-group">' in led and "<thead>" in led
    # a run on your own data: grouped under its dataset, never a round
    assert ">Clinic admissions</span></th>" in led
    assert ui_shared._run_name(own, Ledger().row(own)["spec"])["round"] == ""


def test_the_form_says_what_the_date_gives_and_posts_it_unchanged():
    tpl = (Path(__file__).resolve().parents[1] / "ui" / "templates"
           / "forecast.html").read_text(encoding="utf-8")
    # under the date: the run's name for it, the round on the line under
    # (the hub's only), the window badge beside the round
    assert '<p class="fc-gives" id="fc-label">{{ wi.label or "" }}</p>' in tpl
    assert ('<p class="uk-run-sub fc-round"><span id="fc-ref">'
            '{{ wi.round or "" }}</span>') in tpl
    assert "document.getElementById('fc-label').textContent = d.label;" in tpl
    # the field itself is as it was: the date the form posts
    assert ('<input type="date" name="forecast_date" value="{{ '
            'form.forecast_date or default_date }}" id="fc-date-in"') in tpl
    assert 'tips.stat("Reference date"' not in tpl
