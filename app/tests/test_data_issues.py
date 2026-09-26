"""The Groundhog's zero-anchor rule and the per-state data choices
(app/core/missing.py, app/core/engines/analogue.py zero_anchor, the
Forecast tab's Data issues box: app/core/reported.py box_rows,
templates/_data_issues.html, routes/forecast.py _data_choices).

Held: the four rules on a synthetic series (blend is the mean of level and
extend, level by level; all-zero weeks fall back to the Poisson quantiles;
abstain is what every run did); a state's set-aside trims the Groundhog
and the particle filter's cells alike and is not applied when the data
moved; a state without a choice leaves every other state byte-identical;
a live run with an unchosen zero state is refused before anything is
claimed, and so is a form built on other data; a re-run carries the
choices; a state left out is reported as such; none of it marks a run
modified; a replay from before the rule reads as abstain.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.data as data                                 # noqa: E402
import app.core.runs as runs_mod                             # noqa: E402
from app.core import coverage, knobs as K, missing as MS     # noqa: E402
from app.core import reported, retro                         # noqa: E402
from app.core import datasets as D                           # noqa: E402
from app.core.engines import analogue as EA                  # noqa: E402
from app.core.engines import pf as PF                        # noqa: E402
from app.core.runs import Ledger, RunSpec                    # noqa: E402
from app.ui import pipeline as ui_pipeline                   # noqa: E402
from app.ui import server as srv                             # noqa: E402
from app.ui import shared as ui_shared                       # noqa: E402
from app.ui import state as ui_state                         # noqa: E402
from app.ui.routes import forecast as ui_forecast            # noqa: E402
from app.ui.routes import output as ui_output                # noqa: E402

from test_newest_reported import LOCS, NEW, WEEKS, _hub      # noqa: E402
from test_pf_anchor_lag import (FD as DS_FD, GROUPS, by_loc,  # noqa: E402,F401
                                netgen, spec as ds_spec, store)
from test_dataset_engines import grouped_bytes               # noqa: E402

client = TestClient(srv.app)

#: six weeks, newest last; the anchor week T is the last
T_WEEKS = [str(d.date()) for d in pd.date_range("2098-10-25", periods=6, freq="7D")]
T = T_WEEKS[-1]
SERIES = {"Utah": [1, 0, 4, 2, 0, 0],        # 2 trailing zeros after a 2
          "Vermont": [1, 0, 0, 0, 0, 0],     # the newest 4 all read 0
          "Idaho": [3, 5, 6, 0, 0, 0],       # 3 trailing zeros: past MAX_CARRY
          "Ohio": [70, 71, 72, 73, 74, 75]}
FIPS = {"Utah": "49", "Vermont": "50", "Idaho": "16", "Ohio": "39"}


def _fake_forecast(anchor, as_of, horizon, bank, levels, **kw):
    """A stand-in for flubnf.analogue.forecast: anchor x horizon x (1 + L),
    so the anchor and the ratio's span both show in the numbers."""
    if anchor is None or anchor <= 0:
        return None
    return {float(L): float(anchor) * horizon * (1 + float(L)) for L in levels}


@pytest.fixture
def series(tmp_path, monkeypatch):
    rows = ["date,location,location_name,value"]
    for loc, vals in SERIES.items():
        for w, v in zip(T_WEEKS, vals):
            rows.append(f"{w},{FIPS[loc]},{loc},{v}")
    v = tmp_path / "v.csv"
    v.write_text("\n".join(rows) + "\n")
    locs = tmp_path / "locations.csv"
    locs.write_text("location,location_name,abbreviation\n"
                    + "".join(f"{f},{n},{n[:2].upper()}\n" for n, f in FIPS.items()))
    monkeypatch.setattr(EA, "vintage_path", lambda d: str(v))
    monkeypatch.setattr(EA, "LOCATIONS", str(locs))
    monkeypatch.setattr(EA.AN, "forecast", _fake_forecast)
    return v


def _run(extra=None, locations=None, **kw):
    spec = RunSpec(engine="retro", forecast_date=T,
                   locations=locations or list(SERIES), extra=extra or {})
    notes, flags = {}, []
    out = EA.run(spec, notes=notes, flags=flags, **kw)
    return out, notes, flags


@pytest.fixture(autouse=True)
def _isolated():
    status_before, form_before = dict(ui_state._status), dict(ui_state._last_form)
    yield
    ui_state._status.clear(); ui_state._status.update(status_before)
    ui_state._last_form.clear(); ui_state._last_form.update(form_before)
    ui_shared._invalidate_scans()


# --- the four rules -----------------------------------------------------------------

def test_without_a_rule_the_groundhog_abstains_as_before(series):
    out, notes, flags = _run()
    assert set(out) == {"Ohio"}
    assert notes["Utah"] == "no forecast: newest week reads 0"
    assert flags == []                       # nothing recorded on a plain run


def test_level_anchors_on_the_mean_of_the_last_four_weeks(series):
    out, notes, flags = _run({"knobs": {MS.ZERO_ANCHOR_KEY: "level"}})
    # Utah: mean(4, 2, 0, 0) = 1.5 at the 0 week (lag 0): 1.5 x h x (1 + L)
    assert out["Utah"]["0"][0.5] == pytest.approx(1.5 * 1 * 1.5)
    assert out["Utah"]["3"][0.975] == pytest.approx(1.5 * 4 * 1.975)
    assert notes["Utah"] == (f"zero-anchor level: newest week {T} reads 0; "
                             f"anchor mean 1.50 of {T_WEEKS[2]}..{T}")
    assert {"location": "Utah", "week": T, "value": 0.0,
            "rule": "zero-anchor level"} in flags
    # Ohio is untouched
    assert out["Ohio"]["0"][0.5] == pytest.approx(75 * 1.5)


def test_all_zero_weeks_fall_back_to_the_poisson_quantiles(series):
    out, notes, _ = _run({"knobs": {MS.ZERO_ANCHOR_KEY: "level"}})
    from app.core.floor import _pois_ppf
    lam = MS.ZERO_ANCHOR_LAM[0]                   # the mean is 0: the floor
    for h in ("0", "1", "2", "3"):
        assert out["Vermont"][h] == {float(L): float(_pois_ppf(float(L), lam))
                                     for L in EA.QL}
    assert out["Vermont"]["0"][0.5] == 0 and out["Vermont"]["0"][0.975] >= 1
    assert "all 4 newest weeks read 0, Poisson(0.35)" in notes["Vermont"]


def test_extend_carries_the_last_positive_week_over_the_zeros(series):
    out, notes, _ = _run({"knobs": {MS.ZERO_ANCHOR_KEY: "extend"}})
    # Utah: 2 at T-2 weeks, the ratio spanning h + 2 weeks
    assert out["Utah"]["0"][0.5] == pytest.approx(2 * 3 * 1.5)
    assert out["Utah"]["3"][0.5] == pytest.approx(2 * 6 * 1.5)
    assert notes["Utah"] == (f"zero-anchor extend: newest week {T} reads 0; "
                             f"2 ({T_WEEKS[3]}) carried 2 weeks")
    # Idaho: 3 zeros is past MAX_CARRY: the Poisson quantiles at the mean 1.5
    from app.core.floor import _pois_ppf
    assert out["Idaho"]["0"] == {float(L): float(_pois_ppf(float(L), 1.5))
                                 for L in EA.QL}
    assert "3 weeks read 0 (at most 2 carried), Poisson(1.5)" in notes["Idaho"]


def test_blend_is_the_mean_of_level_and_extend_level_by_level(series):
    lvl, _, _ = _run({"knobs": {MS.ZERO_ANCHOR_KEY: "level"}})
    ext, _, _ = _run({"knobs": {MS.ZERO_ANCHOR_KEY: "extend"}})
    bl, notes, flags = _run({"knobs": {MS.ZERO_ANCHOR_KEY: "blend"}})
    for loc in ("Utah", "Idaho", "Vermont"):
        for h in ("0", "1", "2", "3"):
            for L in EA.QL:
                assert bl[loc][h][L] == pytest.approx(
                    0.5 * lvl[loc][h][L] + 0.5 * ext[loc][h][L])
    assert notes["Utah"].startswith(f"zero-anchor blend: newest week {T} reads 0; ")
    assert "anchor mean 1.50" in notes["Utah"] and "carried 2 weeks" in notes["Utah"]
    assert {r["rule"] for r in flags} == {"zero-anchor blend"}


def test_a_states_own_choice_beats_the_knob_and_leaves_the_rest_untouched(series):
    plain, _, _ = _run()
    extra = {"knobs": {MS.ZERO_ANCHOR_KEY: "level"},
             "data_choices": {"week": T, "source_sha256": "x", "states": {
                 "Utah": {"issue": "zero", "choice": "extend",
                          "reported": [[T, 0.0]]}}}}
    out, notes, _ = _run(extra)
    assert out["Utah"]["0"][0.5] == pytest.approx(2 * 3 * 1.5)   # extend
    assert notes["Utah"].startswith("zero-anchor extend")
    assert notes["Idaho"].startswith("zero-anchor level")          # the knob
    assert out["Ohio"] == plain["Ohio"]                            # untouched
    assert MS.rules_for(extra, "Utah", "pf") == {MS.ZERO_ANCHOR_KEY: "level"}
    assert MS.rules_for(extra, "Ohio", "analogue") == {MS.ZERO_ANCHOR_KEY: "level"}


# --- set aside, per state --------------------------------------------------------------

def _aside(loc, rows):
    return {"data_choices": {"week": T, "source_sha256": "x", "states": {
        loc: {"issue": "zero", "choice": "set_aside", "reported": rows,
              "from_week": T_WEEKS[3]}}}}


def test_a_set_aside_trims_the_state_and_no_other(series):
    plain, _, _ = _run()
    extra = _aside("Utah", [[T_WEEKS[4], 0.0], [T, 0.0]])
    out, notes, flags = _run(extra)
    # Utah forecasts from the 2 two weeks back, as weeks_to_drop = 2 would
    assert out["Utah"]["0"][0.5] == pytest.approx(2 * 3 * 1.5)
    # a set-aside is a trim, as weeks_to_drop is: flagged, not "anchored on"
    assert "Utah" not in notes
    assert flags == [
        {"location": "Utah", "week": T_WEEKS[4], "value": 0.0, "rule": MS.SET_ASIDE_RULE},
        {"location": "Utah", "week": T, "value": 0.0, "rule": MS.SET_ASIDE_RULE}]
    assert out["Ohio"] == plain["Ohio"] and "Ohio" not in notes
    assert MS.choices_line({"analogue": flags}) == "1 set aside"


def test_a_set_aside_is_not_applied_when_the_data_moved(series):
    # the week now reads 3, not the 0 the choice was made on
    out, notes, flags = _run(_aside("Utah", [[T, 3.0]]))
    assert "Utah" not in out and flags == []
    assert notes["Utah"] == f"set-aside not applied: {T} now reads 0"
    # a run record with that note gets its own Results row, not "anchored"
    o = {"analogue_anchor_notes": notes, "data_flags": {"analogue": []}}
    row = runs_mod.data_issues_row(o, _aside("Utah", [[T, 3.0]]),
                                   {"analogue": "Groundhog"})
    assert row[0] == "Data issues" and "1 not applied (the data changed)" in row[1]
    assert runs_mod.anchor_notes_row(o, {"analogue": "Groundhog"}) is None


def test_the_particle_filter_trims_the_same_weeks_in_its_cells(netgen, tmp_path):
    lines = grouped_bytes(groups=GROUPS, end=date(2023, 12, 2)).decode(
    ).strip().split("\n")
    i = max(j for j, ln in enumerate(lines) if ",Adult," in ln)
    lines[i] = re.sub(r",Adult,[^,]*", ",Adult,0", lines[i])
    ds = D.ingest(("\n".join(lines) + "\n").encode(), "zero", kind="count")
    choice = {"data_choices": {"week": DS_FD, "source_sha256": "x", "states": {
        "Adult": {"issue": "zero", "choice": "set_aside",
                  "reported": [[DS_FD, 0.0]]}}}}
    cells = by_loc(PF.prepare(ds_spec(ds, extra=choice), tmp_path / "w"))
    assert cells["Adult"]["data_flags"] == [
        {"week": DS_FD, "rule": MS.SET_ASIDE_RULE, "value": 0.0}]
    assert cells["Adult"]["weeks_dropped"] == 1
    assert "data_flags" not in cells["Pediatric"]
    assert MS.cell_flags(list(cells.values())) == [
        {"location": "Adult", "week": DS_FD, "rule": MS.SET_ASIDE_RULE, "value": 0.0}]
    # the same choice on data that moved: nothing trimmed, the note says so
    moved = {"data_choices": {"week": DS_FD, "source_sha256": "x", "states": {
        "Adult": {"issue": "zero", "choice": "set_aside",
                  "reported": [[DS_FD, 4.0]]}}}}
    cells = by_loc(PF.prepare(ds_spec(ds, extra=moved), tmp_path / "w2"))
    assert cells["Adult"]["weeks_dropped"] == 0
    notes = PF.read_anchor_notes(tmp_path / "w2")
    assert notes["Adult"] == f"set-aside not applied: {DS_FD} now reads 0"


# --- the record never marks a run modified ---------------------------------------------

def test_choices_and_the_rule_keep_the_hub_names():
    spec = RunSpec(engine="all", forecast_date=T, locations=["Utah"],
                   extra={**ui_forecast._run_extra(2, "realtime"),
                          "knobs": {MS.ZERO_ANCHOR_KEY: "blend"},
                          "data_choices": {"week": T, "source_sha256": "x",
                                           "states": {"Utah": {
                                               "issue": "zero", "what": "reads 0",
                                               "choice": "set_aside",
                                               "reported": [[T, 0.0]]}}}})
    assert not K.modified(spec) and K.hub_names(spec)
    assert runs_mod.model_settings_label(spec) == ""
    pairs = dict(runs_mod.spec_settings(spec))
    # a record from before the recommendation names every state
    assert pairs["Data issues"] == ("Utah set aside; zero-anchor rule blend for "
                                    "the other states")
    assert "model settings" not in pairs
    assert MS.followed_line(MS.choices_of(spec.extra)) == ""
    assert MS.followed_line({"A": {"choice": "level", "followed": True},
                             "B": {"choice": "omit", "followed": False},
                             "C": {"choice": "keep", "followed": True}}) == \
        "3 states, 2 recommended, 1 changed"


# --- the Forecast tab -----------------------------------------------------------------

def _capture_run(monkeypatch):
    monkeypatch.setattr(ui_state, "data_mod", data)
    started = []
    monkeypatch.setattr(ui_pipeline, "_run_all", lambda spec: started.append(spec))
    return started


def _post(extra):
    ui_state._status["running"] = None
    return client.post("/run", data={"forecast_date": NEW, "locations": ["all"],
                                     "engine": "analogue", **extra},
                       follow_redirects=False)


def test_the_box_lists_the_states_and_preselects_the_recommendation(tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch, newest={"Ohio": "0", "Utah": "5"})
    ui_state._last_form.clear()
    ui_state._last_form.update({"forecast_date": NEW, "locations": ["all"],
                                "engine": "all"})
    page = client.get("/forecast").text
    box = page[page.index('id="data-issues"'):page.index("</fieldset>")]
    assert f'data-week="{NEW}"' in box and "<legend>Data issues<span" in box
    assert '<span class="ms-badge warn">2 states</span>' in box
    md = WEEKS[-2][5:]
    # one compact row: the name, the flag, the badge, the select, the reason
    assert ('<label for="gap-39">Ohio</label><span class="di-flag">0 after 40, 40, 40'
            '</span><span class="ms-badge ok di-rec">recommended</span>') in box
    assert 'name="gap.39" id="gap-39" data-issue="zero" data-rec="set_aside"' in box
    assert f'<option value="set_aside" selected>Both from {md}</option>' in box
    assert f'<option value="extend">Extend 40 from {md}</option>' in box
    assert '<span class="hint di-why">0 after 40, 40, 40 looks like a missed report</span>' in box
    assert 'name="gap.49" id="gap-49" data-issue="collapsed" data-rec="set_aside"' in box
    assert '<option value="keep">Keep 5</option>' in box
    assert "required" not in box and "Choose…" not in box   # nothing to answer
    assert 'name="gap._sha"' in box
    # the long explanations live in the legend's tip
    assert "Level = it anchors on the mean of the last 4 weeks" in box
    assert "about three quarters stayed 0 once settled" in box
    assert "Groundhog:" not in box                 # no long option labels
    assert "di.hidden = a !== di.dataset.week; di.disabled = di.hidden" in page
    assert 'id="di-all"' not in box                 # one zero state: no "all"
    # two zero states: the short "All zero states:" row
    _hub(tmp_path / "hub2", monkeypatch, newest={"Ohio": "0", "Utah": "0"})
    page = client.get("/forecast").text
    box = page[page.index('id="data-issues"'):page.index("</fieldset>")]
    assert '<label for="di-all">All zero states:</label>' in box
    assert '<option value="set_aside">Both from the week before</option>' in box


def test_a_zero_state_without_a_choice_takes_the_recommendation(tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch, newest={"Ohio": "0", "Utah": "0"})
    started = _capture_run(monkeypatch)
    r = _post({})
    assert r.status_code == 303 and len(started) == 1
    dc = started[0].extra["data_choices"]
    assert {l: (s["choice"], s["recommended"], s["followed"])
            for l, s in dc["states"].items()} == {
        "Ohio": ("set_aside", "set_aside", True),
        "Utah": ("set_aside", "set_aside", True)}
    assert dc["states"]["Ohio"]["reported"] == [[NEW, 0.0]]
    assert dc["states"]["Ohio"]["from_week"] == WEEKS[-2]
    assert runs_mod.data_issues_label(started[0].extra) == "2 states, 2 recommended, 0 changed"
    # the run-wide rule covers every zero state the form did not answer
    r = _post({"knob.groundhog.zero_anchor": "level"})
    assert len(started) == 2 and "data_choices" not in started[1].extra
    assert started[1].extra["knobs"] == {MS.ZERO_ANCHOR_KEY: "level"}
    # a choice not offered is refused
    ui_state._status.pop("flash", None)
    _post({"gap.39": "extend", "gap.49": "abstain"})   # 0 after 40: extend is offered
    assert len(started) == 3
    _post({"gap.39": "carry", "gap.49": "abstain"})
    assert len(started) == 3 and "Ohio: 'carry' is not one of" in ui_state._status["flash"]
    assert ui_state._status.get("running") is None


def test_the_choices_reach_the_spec_and_a_left_out_state_leaves_the_list(tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch, newest={"Ohio": "0", "Utah": "5"})
    started = _capture_run(monkeypatch)
    sha = ui_forecast._source_sha(NEW)
    r = _post({"gap.39": "omit", "gap.49": "set_aside", "gap._sha": sha})
    assert r.status_code == 303 and len(started) == 1
    s = started[0]
    assert "Ohio" not in s.locations and "Utah" in s.locations
    dc = s.extra["data_choices"]
    assert dc["week"] == NEW and dc["source_sha256"] == sha
    assert dc["states"]["Ohio"]["choice"] == "omit"
    assert dc["states"]["Ohio"]["what"] == "reads 0 after 40, 40, 40"
    assert dc["states"]["Ohio"]["followed"] is False
    assert dc["states"]["Utah"] == {
        "issue": "collapsed", "what": "reads 5 after 40", "choice": "set_aside",
        "week": NEW, "reported": [[NEW, 5.0]], "from_week": WEEKS[-2],
        "recommended": "set_aside", "followed": True}
    assert "knobs" not in s.extra                  # no model setting touched
    assert ui_state._last_form["data_choices"] == {NEW: {"39": "omit", "49": "set_aside"}}
    # the run page counts the choices against the recommendations
    assert runs_mod.data_issues_label(s.extra) == "2 states, 1 recommended, 1 changed: Ohio left out"
    o = {"data_flags": {"analogue": [
        {"location": "Ohio", "week": NEW, "value": 0.0, "rule": MS.LEFT_OUT_RULE},
        {"location": "Utah", "week": NEW, "value": 5.0, "rule": MS.SET_ASIDE_RULE}]}}
    row = runs_mod.data_issues_row(o, s.extra, {"analogue": "Groundhog"})
    assert row[1].startswith("2 states, 1 recommended, 1 changed; 1 set aside, 1 left out")
    # the form comes back pre-filled, the badge off where the choice differs
    page = client.get("/forecast").text
    assert '<option value="omit" selected>Leave out</option>' in page
    ohio = page[page.index('for="gap-39"'):page.index('id="gap-39"')]
    assert 'class="ms-badge ok di-rec" hidden>recommended' in ohio
    utah = page[page.index('for="gap-49"'):page.index('id="gap-49"')]
    assert 'class="ms-badge ok di-rec">recommended' in utah
    # every listed state is recorded, a default choice too
    _post({"gap.39": "abstain", "gap.49": "keep"})
    assert len(started) == 2
    got = started[1].extra["data_choices"]["states"]
    assert {l: (s["choice"], s["followed"]) for l, s in got.items()} == {
        "Ohio": ("abstain", False), "Utah": ("keep", False)}
    assert runs_mod.data_issues_label(started[1].extra) == (
        "2 states, 0 recommended, 2 changed: Ohio abstain, Utah keep")
    _hub(tmp_path / "hub2", monkeypatch, newest={"Utah": "5"})
    _post({"gap.49": "keep"})
    assert len(started) == 3
    assert list(started[2].extra["data_choices"]["states"]) == ["Utah"]


def test_a_form_built_on_other_data_is_refused(tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch, newest={"Ohio": "0"})
    started = _capture_run(monkeypatch)
    _post({"gap.39": "level", "gap._sha": "0" * 64})
    assert started == []
    assert "The hub data changed since the Forecast tab was loaded" in \
        ui_state._status["flash"]


def test_a_rerun_carries_the_data_choices(tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch, newest={"Ohio": "0"},
         vintages=[WEEKS[-2]])
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    dc = {"week": NEW, "source_sha256": "abc", "states": {
        "Ohio": {"issue": "zero", "what": "reads 0 after 40, 40, 40",
                 "choice": "level", "week": NEW, "from_week": NEW,
                 "reported": [[WEEKS[-2], 40.0], [NEW, 0.0]]}}}
    spec = RunSpec(engine="analogue", forecast_date=NEW, locations=["Ohio", "Utah"],
                   extra={**ui_forecast._run_extra(2, "realtime"), "data_choices": dc})
    led = Ledger()
    rid = led.open_run(spec, Path("pending"), {})
    led.close_run(rid, "stopped", {})
    started = _capture_run(monkeypatch)
    r = client.post(f"/runs/{rid}/rerun", follow_redirects=False)
    assert r.status_code == 303 and len(started) == 1
    # the real-time week: the recorded choices are re-checked against the
    # data as it stands now (its sha256 and values), the choice kept
    got = started[0].extra["data_choices"]
    assert got["week"] == NEW and got["source_sha256"] == ui_forecast._source_sha(NEW)
    assert got["states"]["Ohio"]["choice"] == "level"
    assert got["states"]["Ohio"]["reported"][-1] == [NEW, 0.0]
    assert (got["states"]["Ohio"]["recommended"], got["states"]["Ohio"]["followed"]) == \
        ("set_aside", False)
    assert started[0].locations == ["Ohio", "Utah"]
    # an older week: the record passes through verbatim
    old = RunSpec(engine="analogue", forecast_date=WEEKS[-2], locations=["Ohio"],
                  extra={**ui_forecast._run_extra(2, "vintage"),
                         "data_choices": {**dc, "week": WEEKS[-2]}})
    rid2 = led.open_run(old, Path("pending"), {})
    led.close_run(rid2, "stopped", {})
    ui_state._status["running"] = None            # the captured run never ran
    r = client.post(f"/runs/{rid2}/rerun", follow_redirects=False)
    assert r.status_code == 303 and len(started) == 2, ui_state._status.get("flash")
    assert started[1].extra["data_choices"] == {**dc, "week": WEEKS[-2]}


# --- the pages ------------------------------------------------------------------------

def test_a_left_out_state_is_requested_and_left_out_on_the_output_page(tmp_path):
    o = {"left_out": {"Ohio": "left out on the Forecast tab: reads 0, recent weeks 1-4"},
         "data_flags": {"analogue": [{"location": "Ohio", "week": T, "value": 0.0,
                                      "rule": MS.LEFT_OUT_RULE}], "pf": []}}
    assert coverage.missing_reason(o, "analogue", "m", "Ohio") == \
        "left out on the Forecast tab: reads 0, recent weeks 1-4"
    assert coverage.moved_notes(o, "analogue") == {}
    f = tmp_path / "sub" / "NAU_PyBNF-GroundHogCGR" / "x.csv"
    f.parent.mkdir(parents=True)
    f.write_text("location\n49\n")
    files = [{"model": "NAU_PyBNF-GroundHogCGR", "path": str(f), "archived": False}]
    ui_output._attach_coverage(files, o, {"locations": ["Utah"]})
    cov = files[0]["cov"]
    assert cov["n"] == 1 and cov["of"] == 2
    assert dict(cov["missing"])["Ohio"].startswith("left out on the Forecast tab")
    row = runs_mod.data_issues_row(
        o, {"data_choices": {"states": {"Ohio": {"choice": "omit", "what": "reads 0"}}}},
        {"analogue": "Groundhog"})
    assert row[0] == "Data issues" and row[1].startswith("1 left out")


def test_the_run_page_counts_the_zero_anchor_weeks_by_rule():
    o = {"analogue_anchor_notes": {
        "Utah": f"zero-anchor level: newest week {T} reads 0; anchor mean 1.50",
        "Idaho": f"zero-anchor level: newest week {T} reads 0; all 4 newest weeks read 0",
        "Vermont": "no forecast: newest week reads 0"}}
    row = runs_mod.zero_anchor_row(o, {"analogue": "Groundhog"})
    assert row[0] == "Newest week reading 0"
    assert row[1].startswith("Groundhog: 1 abstain, 2 level")
    assert "Groundhog, Vermont: no forecast: newest week reads 0." in row[1]
    assert runs_mod.anchor_notes_row(o, {"analogue": "Groundhog"}) is None
    flags = {"analogue": [{"location": l, "week": T, "value": 0.0,
                           "rule": "zero-anchor level"} for l in ("Utah", "Idaho")]}
    assert MS.choices_line(flags) == "2 zero-anchor level"
    assert MS.line(MS.unreported_flags(flags)) == ""
    assert MS.replay_zero_anchor_count({T: flags, T_WEEKS[0]: {"analogue": []}}) == \
        "2 location-weeks (2 level)"
    assert MS.replay_count({T: flags}) == "on; no week flagged"


def test_a_replay_from_before_the_rule_reads_as_abstain():
    meta = {"settings": {"season": "2098-99", "scope": "all", "engine": "analogue",
                         "knobs": {"oracle.w": 0.25}}}
    pairs = dict(retro.settings_summary(meta))
    assert pairs["zero-anchor rule"] == "abstain (replayed before the rule existed)"
    assert pairs["model settings"].startswith("modified: oracle.w=0.25")
    meta["settings"]["knobs"] = {MS.ZERO_ANCHOR_KEY: "blend"}
    pairs = dict(retro.settings_summary(meta))
    assert pairs["zero-anchor rule"] == "blend" and "model settings" not in pairs
    assert retro.season_knobs(meta) == {}          # a data decision: not modified
    # the resume guard reads a missing key as abstain
    assert K.settings_digest({}) == K.settings_digest({MS.ZERO_ANCHOR_KEY: "abstain"})
