"""Which file a run reads (app.core.data.observed_source).

A real-time run reads the hub's live target-data file when its newest week
IS the as-of (the hub archives vintages by hand and skips weeks); every
earlier week reads its dated vintage, never the live file's revised values.
The run records the file (kind, path, sha256, newest week) and the run page,
report and Output tab say it in one line. Hub-free: each test builds a tiny
hub in tmp_path.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.data as data                                 # noqa: E402
from app.core.runs import Ledger, RunSpec, spec_settings     # noqa: E402
from app.ui import pipeline as ui_pipeline                   # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons         # noqa: E402
from app.ui import server as srv                             # noqa: E402
from app.ui import shared as ui_shared                       # noqa: E402
from app.ui import state as ui_state                         # noqa: E402

from test_oracle_step import ASOF, console, hubfiles          # noqa: E402,F401

#: the real report writer (the console fixture stubs it)
_REAL_REPORT = ui_pipeline._write_weekly_report

client = TestClient(srv.app)

W1, W2, W3 = "2098-10-04", "2098-10-11", "2098-10-18"     # Saturdays


def _rows(weeks, bump=0):
    out = ["date,location,location_name,value,weekly_rate"]
    for i, w in enumerate(weeks):
        for f, name in (("39", "Ohio"), ("49", "Utah"), ("US", "US")):
            out.append(f"{w},{f},{name},{100 + 10 * i + bump},1.0")
    return "\n".join(out) + "\n"


def _hub(root: Path, live_weeks, vintages, monkeypatch, revised=0):
    """A hub: target-data with `live_weeks`, one archived file per vintage
    (holding the weeks up to it), and app.core.data pointed at it."""
    (root / "target-data").mkdir(parents=True, exist_ok=True)
    arch = root / "auxiliary-data" / "target-data-archive"
    arch.mkdir(parents=True, exist_ok=True)
    if live_weeks:
        (root / data.LIVE_TARGET).write_text(_rows(live_weeks, bump=revised))
    allw = sorted(set(live_weeks) | set(vintages))
    for v in vintages:
        (arch / f"target-hospital-admissions_{v}.csv").write_text(
            _rows([w for w in allw if w <= v]))
    monkeypatch.setattr(data, "HUB", root)
    monkeypatch.setattr(data, "ARCHIVE", arch)
    ui_shared._invalidate_scans()
    return root


@pytest.fixture(autouse=True)
def _isolated():
    status_before, form_before = dict(ui_state._status), dict(ui_state._last_form)
    yield
    ui_state._status.clear(); ui_state._status.update(status_before)
    ui_state._last_form.clear(); ui_state._last_form.update(form_before)
    ui_shared._invalidate_scans()


# --- the resolver ------------------------------------------------------------

def test_real_time_with_the_vintage_present_reads_the_live_file(tmp_path, monkeypatch):
    hub = _hub(tmp_path / "hub", [W1, W2], [W1, W2], monkeypatch)
    path, kind = data.observed_source(W2, "realtime")
    assert (path, kind) == (hub / data.LIVE_TARGET, "live")
    assert data.newest_week() == W2 and data.available_weeks() == [W1, W2]


def test_real_time_with_the_vintage_missing_reads_the_live_file(tmp_path, monkeypatch):
    hub = _hub(tmp_path / "hub", [W1, W2], [W1], monkeypatch)
    with pytest.raises(FileNotFoundError):
        data.vintage_path(W2)                      # the archive skipped W2
    assert data.observed_source(W2, "realtime") == (hub / data.LIVE_TARGET, "live")
    assert data.newest_week() == W2
    assert data.available_weeks() == [W1, W2]
    assert data.newest_path() == hub / data.LIVE_TARGET


def test_live_older_than_the_as_of_is_refused(tmp_path, monkeypatch):
    _hub(tmp_path / "hub", [W1], [W1], monkeypatch)
    with pytest.raises(data.DataSourceError, match=f"ends at {W1}"):
        data.observed_source(W2, "realtime")


def test_a_past_week_always_reads_its_vintage_never_the_live_file(tmp_path, monkeypatch):
    # the live file revises W1's values a week on: reading it for W1 would
    # leak hindsight, in either mode
    hub = _hub(tmp_path / "hub", [W1, W2], [W1], monkeypatch, revised=7)
    arch = hub / "auxiliary-data" / "target-data-archive"
    want = (arch / f"target-hospital-admissions_{W1}.csv", "vintage")
    assert data.observed_source(W1, "realtime") == want
    assert data.observed_source(W1, "vintage") == want
    # a replay names its week's vintage even when the live file ends there
    _hub(tmp_path / "hub2", [W1], [], monkeypatch)
    with pytest.raises(FileNotFoundError):
        data.observed_source(W1, "vintage")
    # a replay spec (engine "retro") and a backdated run are vintage mode
    assert data.spec_mode(RunSpec(engine="retro", forecast_date=W1)) == "vintage"
    assert data.spec_mode(RunSpec(engine="all", forecast_date=W1,
                                  extra={"mode": "vintage"})) == "vintage"
    assert data.spec_mode(RunSpec(engine="all", forecast_date=W1)) == "realtime"


def test_the_record_and_its_phrase(tmp_path, monkeypatch):
    hub = _hub(tmp_path / "hub", [W1, W2], [W1], monkeypatch)
    rec = data.source_record(*data.observed_source(W2, "realtime"))
    assert rec["kind"] == "live" and rec["newest_week"] == W2
    assert rec["path"] == str(hub / data.LIVE_TARGET)
    assert len(rec["sha256"]) == 64
    assert data.source_phrase(rec) == f"live target-data through {W2}"
    old = data.source_record(*data.observed_source(W1, "realtime"))
    assert data.source_phrase(old) == f"archived vintage {W1}"
    assert data.source_phrase(None) == "" and data.source_phrase({}) == ""


# --- the engines read the resolved file ---------------------------------------

def test_the_groundhog_reads_the_live_file_for_a_real_time_week(tmp_path, monkeypatch):
    from app.core.engines import analogue as eng
    hub = _hub(tmp_path / "hub", [W1, W2], [W1], monkeypatch)
    spec = RunSpec(engine="all", forecast_date=W2, extra={"mode": "realtime"})
    assert eng._source(spec)[0] == hub / data.LIVE_TARGET
    retro_spec = RunSpec(engine="retro", forecast_date=W1)
    assert eng._source(retro_spec)[0].name == f"target-hospital-admissions_{W1}.csv"


# --- the recorded source, end to end ------------------------------------------

def test_a_real_time_run_records_the_live_file(console, hubfiles, tmp_path, monkeypatch):
    """The vintage for the as-of is missing; the live file is current: the
    run goes ahead on it and records it in the outcome, oracle.json, the
    run settings and the Output tab."""
    from app.core import oracle as oracle_mod
    from app.core import runs as runs_mod
    hub = tmp_path / "hub"
    (hub / "target-data").mkdir(parents=True)
    (hub / data.LIVE_TARGET).write_bytes(Path(hubfiles["vintage"]).read_bytes())
    monkeypatch.setattr(data, "HUB", hub)
    monkeypatch.setattr(data, "ARCHIVE", tmp_path / "no-archive")
    spec = RunSpec(engine="all", forecast_date=ASOF, locations=["Ohio", "Utah"],
                   extra={"mode": "realtime"})
    ui_pipeline._run_all(spec)
    row = Ledger().rows(1)[0]
    out = json.loads(row["outcome"])
    rec = out["data_source"]
    assert rec["kind"] == "live" and rec["newest_week"] == ASOF
    assert rec["path"] == str(hub / data.LIVE_TARGET)
    assert rec["sha256"] == data.file_sha256(hub / data.LIVE_TARGET)
    w = runs_mod.APP_STATE / "workroots" / row["run_id"]
    prov = oracle_mod.read_provenance(w)
    assert prov["vintage"]["kind"] == "live"
    assert prov["vintage"]["sha256"] == rec["sha256"]   # one file, one hash
    pairs = dict(spec_settings(row["spec"], row["outcome"]))
    assert pairs["data"] == f"live target-data through {ASOF}"
    page = client.get(f"/runs/{row['run_id']}").text
    assert f"live target-data through {ASOF}" in page
    html = client.get("/output").text
    assert f"Data: live target-data through {ASOF}" in html


def test_optional_rows_on_a_week_only_the_live_file_holds(console, hubfiles, tmp_path, monkeypatch):
    """The optional hub rows read the reported counts from the file the run
    resolved: a real-time week the archive does not hold yet (the live file
    only) must not fail the whole run with 'No vintage for ...'."""
    from app.core.engines import analogue as an_engine
    from app.ui.routes import forecast as ui_forecast
    hub = tmp_path / "hub"
    (hub / "target-data").mkdir(parents=True)
    (hub / data.LIVE_TARGET).write_bytes(Path(hubfiles["vintage"]).read_bytes())
    monkeypatch.setattr(data, "HUB", hub)
    monkeypatch.setattr(data, "ARCHIVE", tmp_path / "no-archive")
    monkeypatch.setattr(an_engine, "nowcast", lambda spec: {})
    _nd, extra = ui_forecast._knob_run_parts(
        {"output.horizon_minus1": "1", "output.rate_change_pmf": "1"}, "all",
        ASOF, 2, "realtime", None, None, legacy={})
    spec = RunSpec(engine="all", forecast_date=ASOF, locations=["Ohio", "Utah"],
                   replicates=1, extra=extra)
    ui_pipeline._run_all(spec)
    row = Ledger().rows(1)[0]
    out = json.loads(row["outcome"])
    assert row["status"] == "ok", out.get("error")
    assert out["data_source"]["kind"] == "live"
    assert "optional_rows" in out and out["submissions"]


def test_the_reports_state_fans_sit_on_the_as_of_horizons(console, hubfiles, tmp_path, monkeypatch):
    """Hub horizon h is h+1 weeks past the AS-OF week. With the same-day
    week dropped the observed trace ends a week earlier; the report's state
    fans must not move back with it (they were drawn one week early)."""
    from datetime import date, timedelta
    from app.core import runs as runs_mod
    monkeypatch.setattr(ui_pipeline, "_write_weekly_report", _REAL_REPORT)
    hub = tmp_path / "hub"
    (hub / "target-data").mkdir(parents=True)
    (hub / data.LIVE_TARGET).write_bytes(Path(hubfiles["vintage"]).read_bytes())
    monkeypatch.setattr(data, "HUB", hub)
    monkeypatch.setattr(data, "ARCHIVE", tmp_path / "no-archive")
    from app.core.engines import pf as pf_engine

    def prepare(spec, w):                # the report reads cells.json
        Path(w).mkdir(parents=True, exist_ok=True)
        (Path(w) / "cells.json").write_text(json.dumps(
            [{"key": "Ohio_r0", "location": "Ohio", "replicate": 0,
              "dir": str(w)}]))
        return []
    monkeypatch.setattr(pf_engine, "prepare", prepare)
    import flubnf.settings as fs                  # the observed trace's table
    monkeypatch.setattr(fs, "LOCATIONS", hubfiles["locations"])
    want = [(date.fromisoformat(ASOF) + timedelta(days=7 * (h + 1))).isoformat()
            for h in range(4)]
    for drop in (False, True):
        spec = RunSpec(engine="all", forecast_date=ASOF, locations=["Ohio"],
                       replicates=1, drop_same_day=drop,
                       extra={"mode": "realtime"})
        ui_pipeline._run_all(spec)
        row = Ledger().rows(1)[0]
        w = runs_mod.APP_STATE / "workroots" / row["run_id"]
        assert "report_error" not in row["outcome"], row["outcome"]
        fan = json.loads((w / "report_inputs.json").read_text())[
            "details"]["OH"]["fan"]
        assert fan["forecast_times"] == want, (drop, fan["forecast_times"])
        assert (fan["observed_times"][-1] < ASOF) == drop


# --- the console routes -------------------------------------------------------

def _capture(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(ui_state, "data_mod", data)
    started = []
    monkeypatch.setattr(ui_pipeline, "_run_all", lambda spec: started.append(spec))
    return started


def _post(fd, mode="realtime"):
    ui_state._status["running"] = None
    return client.post("/run", data={"forecast_date": fd, "mode": mode,
                                     "locations": ["Ohio"], "engine": "analogue"},
                       follow_redirects=False)


def test_the_run_route_takes_a_week_only_the_live_file_holds(tmp_path, monkeypatch):
    started = _capture(monkeypatch, tmp_path)
    _hub(tmp_path / "hub", [W1, W2], [W1], monkeypatch)
    r = _post(W2)
    assert r.status_code == 303 and len(started) == 1, ui_state._status.get("flash")
    assert started[0].forecast_date == W2
    assert started[0].extra["mode"] == "realtime"
    # the Vintage pill on the newest week is still real-time data
    r = _post(W2, mode="vintage")
    assert started[1].extra["mode"] == "realtime"
    # an earlier week is a vintage run on its vintage
    r = _post(W1)
    assert started[2].extra["mode"] == "vintage"


def test_the_run_route_refuses_a_week_past_the_live_file(tmp_path, monkeypatch):
    started = _capture(monkeypatch, tmp_path)
    _hub(tmp_path / "hub", [W1], [W1], monkeypatch)
    r = _post(W2)
    assert r.status_code == 303 and not started
    flash = str(ui_state._status.get("flash") or "")
    assert f"No data for {W2} yet" in flash and f"ends at {W1}" in flash


def test_the_run_route_refuses_bad_fields_in_their_own_words(tmp_path, monkeypatch):
    """A blank or non-date forecast date, or an unknown engine, is refused
    before anything else is said; an unknown mode is the default pill, so
    an archived week is still recorded as a vintage run."""
    started = _capture(monkeypatch, tmp_path)
    _hub(tmp_path / "hub", [W1, W2], [W1], monkeypatch)
    for fd, want in (("", "Give a forecast date"),
                     ("7/4/2098", "'7/4/2098' is not a date")):
        ui_state._status.pop("flash", None)
        r = _post(fd)
        assert r.status_code == 303 and not started
        flash = str(ui_state._status.get("flash") or "")
        assert want in flash and "No data" not in flash, flash
    ui_state._status.pop("flash", None)
    ui_state._status["running"] = None
    r = client.post("/run", data={"forecast_date": W1, "locations": ["Ohio"],
                                  "engine": "bogus"}, follow_redirects=False)
    flash = str(ui_state._status.get("flash") or "")
    assert not started and not ui_state._status.get("running")
    assert flash == "'bogus' is not one of the available engines. Nothing was run."
    ui_state._status.pop("flash", None)
    _post(W1, mode="weird")
    assert started[0].extra["mode"] == "vintage"


def test_a_day_that_snaps_back_across_august_first_keeps_the_anchors_season(
        tmp_path, monkeypatch):
    """The page fills Season start with August 1 of the TYPED day's season.
    A September day whose data ends in July anchors on July: that fill must
    not refuse the run as 'not before the forecast date'; the anchor's own
    default season start applies. A season start typed for the anchor's
    season is still honoured."""
    started = _capture(monkeypatch, tmp_path)
    jul = "2098-07-26"                                   # a Saturday
    _hub(tmp_path / "hub", [W1, jul], [W1, jul], monkeypatch)
    ui_state._status["running"] = None
    ui_state._status.pop("flash", None)
    client.post("/run", data={"forecast_date": "2098-09-24",
                              "season_start": "2098-08-01",
                              "locations": ["Ohio"], "engine": "all"},
                follow_redirects=False)
    assert len(started) == 1, ui_state._status.get("flash")
    assert started[0].forecast_date == jul
    assert started[0].season_start == "2097-08-01"
    assert "knobs" not in started[0].extra               # a shipped run
    ui_state._status["running"] = None
    client.post("/run", data={"forecast_date": "2098-09-24",
                              "season_start": "2097-10-01",
                              "locations": ["Ohio"], "engine": "all"},
                follow_redirects=False)
    assert started[1].season_start == "2097-10-01"


def test_the_anchor_line_names_the_latest_week_on_or_before_the_day(
        tmp_path, monkeypatch):
    """The page lists weeks newest first; the anchor is the LAST archived
    week on or before a typed day (resolve_anchor reads them ascending),
    in the server's line and in the page's own script."""
    _capture(monkeypatch, tmp_path)
    _hub(tmp_path / "hub", [W1, W2, W3], [W1, W2, W3], monkeypatch)
    ui_state._last_form.clear()
    ui_state._last_form.update({"forecast_date": "2098-10-20",   # a Monday
                                "locations": ["all"], "engine": "all"})
    page = client.get("/forecast").text
    assert f"Anchor week: {W3}" in page, page[page.find("anchor-line"):][:120]
    assert ".slice().sort()" in page                      # the script's copy
    assert "toISOString()" not in page.split('id="anchor-line"')[1].split(
        "</script>")[0]                                   # local dates only


def test_update_data_moves_the_forecast_date_to_the_new_week(tmp_path, monkeypatch):
    _capture(monkeypatch, tmp_path)
    hub = _hub(tmp_path / "hub", [W1, W2], [W1, W2], monkeypatch)
    ui_state._last_form.clear()
    ui_state._last_form.update({"forecast_date": W2, "locations": ["all"],
                                "engine": "all"})

    def pull():                          # the hub publishes W3, unarchived
        (hub / data.LIVE_TARGET).write_text(_rows([W1, W2, W3]))
        return True, "Fast-forward"
    monkeypatch.setattr(data, "pull_hub", pull)
    client.post("/data/pull", follow_redirects=False)
    assert ui_state._last_form["forecast_date"] == W3
    page = client.get("/forecast").text
    assert f'value="{W3}"' in page
    assert f"Anchor week: {W3} (new data, not archived yet" in page
    dpage = client.get("/data").text
    assert f"Target data through <code>{W3}</code>" in dpage
    assert f"real-time runs for <span class=\"wk\">{W3}</span> read target-data" in dpage


def test_the_data_tab_says_nothing_extra_when_the_archive_is_current(tmp_path, monkeypatch):
    _capture(monkeypatch, tmp_path)
    _hub(tmp_path / "hub", [W1, W2], [W1, W2], monkeypatch)
    dpage = client.get("/data").text
    assert f"Target data through <code>{W2}</code>" in dpage
    assert 'id="live-newer"' not in dpage


# --- the report states what ran -----------------------------------------------

def test_the_settings_say_what_ran_without_a_pf_engine():
    spec = RunSpec(engine="all", forecast_date=W1, locations=["Ohio"])
    asked = dict(spec_settings(spec))
    assert asked["engine"].startswith("both models")
    assert asked["Oracle step"] == "on (console default)"
    ran = dict(spec_settings(spec, {"pf_skipped": "engine venv not installed (Tier A)"}))
    assert ran["engine"] == "Groundhog only (no PF engine on this machine)"
    assert ran["Oracle step"] == "not run (no PF member ran)"
    assert "replicates" not in ran and "particles" not in ran
    # a Groundhog-only run never had a PF member
    solo = dict(spec_settings(RunSpec(engine="analogue", forecast_date=W1)))
    assert solo["Oracle step"] == "not run (no PF member ran)"
    # a run that did fit keeps the full list
    full = dict(spec_settings(spec, {"pf_cells": 3, "oracle": "x@1"}))
    assert full["engine"].startswith("both models") and "particles" in full


# --- the Groundhog's anchor after a trailing unreported week ---------------------

def test_a_trailing_unreported_week_moves_the_window_with_the_anchor(tmp_path, monkeypatch):
    """The live file's newest week can be unreported for a location (NaN).
    The anchor is then the week before, and the donor window and the spans
    follow the anchor's own date: horizon h still lands on as-of + 7h. A
    location silent for longer than MAX_ANCHOR_LAG weeks abstains, with the
    reason recorded."""
    from app.core.engines import analogue as eng
    weeks = [str(d.date()) for d in pd.date_range("2025-12-06", periods=6, freq="7D")]
    T = weeks[-1]                                        # 2026-01-10
    rows = ["date,location,location_name,value"]
    for i, w in enumerate(weeks):
        rows.append(f"{w},39,Ohio,{10 + i if w != T else ''}")     # T unreported
        rows.append(f"{w},49,Utah,{50 + i if i < 2 else ''}")      # silent 4 weeks
        rows.append(f"{w},06,California,{70 + i}")                 # current
    v = tmp_path / "v.csv"
    v.write_text("\n".join(rows) + "\n")
    locs = tmp_path / "locations.csv"
    locs.write_text("location,location_name,abbreviation\n39,Ohio,OH\n"
                    "49,Utah,UT\n06,California,CA\n")
    monkeypatch.setattr(eng, "vintage_path", lambda d: str(v))
    monkeypatch.setattr(eng, "LOCATIONS", str(locs))
    calls = []

    def fake_forecast(anchor, as_of, horizon, bank, levels, **kw):
        calls.append((anchor, str(as_of), horizon))
        return {0.5: anchor}
    monkeypatch.setattr(eng.AN, "forecast", fake_forecast)
    spec = RunSpec(engine="retro", forecast_date=T,
                   locations=["Ohio", "Utah", "California"])
    notes = {}
    out = eng.run(spec, notes=notes)
    by = {}
    for a, ref, h in calls:
        by.setdefault(a, []).append((ref, h))
    # California: reported at T, the window at T, spans 1..4 (unchanged)
    assert by[75.0] == [(T, 1), (T, 2), (T, 3), (T, 4)]
    # Ohio: anchored on 2026-01-03, its window there, spans 2..5
    assert by[14.0] == [("2026-01-03", 2), ("2026-01-03", 3),
                        ("2026-01-03", 4), ("2026-01-03", 5)]
    assert notes["Ohio"].startswith("anchored on 2026-01-03")
    # Utah: newest reported week four weeks back: abstains, reason recorded
    assert "Utah" not in out and notes["Utah"].startswith("abstained")
    assert set(out) == {"Ohio", "California"}


def test_a_note_never_says_anchored_for_a_location_that_abstained(tmp_path, monkeypatch):
    """Newest week unreported and the week before it reads 0: the anchor
    moves back to that 0, and the Groundhog's ratio of nothing abstains
    (flubnf.analogue returns no forecast). The note must say it abstained,
    not that it forecast from that week; a location reported at the as-of
    with 0 abstains as before, with no note (nothing was unreported)."""
    from app.core.engines import analogue as eng
    from app.core.runs import anchor_notes_row
    weeks = [str(d.date()) for d in pd.date_range("2025-12-06", periods=6, freq="7D")]
    T = weeks[-1]
    rows = ["date,location,location_name,value"]
    for i, w in enumerate(weeks):
        rows.append(f"{w},30,Montana,{'' if w == T else (0 if i == 4 else 3)}")
        rows.append(f"{w},49,Utah,{0 if w == T else 2}")
        rows.append(f"{w},06,California,{70 + i}")
    v = tmp_path / "v.csv"
    v.write_text("\n".join(rows) + "\n")
    locs = tmp_path / "locations.csv"
    locs.write_text("location,location_name,abbreviation\n30,Montana,MT\n"
                    "49,Utah,UT\n06,California,CA\n")
    monkeypatch.setattr(eng, "vintage_path", lambda d: str(v))
    monkeypatch.setattr(eng, "LOCATIONS", str(locs))
    # the library's rule: an anchor of 0 has no forecast
    monkeypatch.setattr(eng.AN, "forecast",
                        lambda anchor, *a, **k: {0.5: anchor} if anchor > 0 else None)
    spec = RunSpec(engine="retro", forecast_date=T,
                   locations=["Montana", "Utah", "California"])
    notes = {}
    out = eng.run(spec, notes=notes)
    assert set(out) == {"California"}
    assert notes["Montana"] == ("abstained: newest reported week 2026-01-03 "
                                "reads 0 (1 newer week(s) unreported)")
    assert "Utah" not in notes
    row = anchor_notes_row({"analogue_anchor_notes": notes},
                           {"analogue": "Groundhog"})
    assert "1 abstained" in str(row) and "anchored earlier" not in str(row)
