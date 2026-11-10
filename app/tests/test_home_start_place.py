"""Home's Start here on a fresh install, and its Data step against the hub
(review 3 of the usability work, P2-9 and P2-10), tested on the page the
server renders, its markup parsed (served_dom.tree).

  * P2-9: on a fresh install the cold paint (the map still preparing)
    puts Start here where the reload will have it, before the map, its
    steps plain until that reload reads the data. With a stored run the
    card sits beside the record on both paints, as the weekly view has it.
  * P2-10, as the re-check of #93 at 099907c (findings 6 and 7) changed
    it: Home's Data step reads done where a run can read the hub, that is
    where the run gate (data.hub_missing) lets a run through and the hub
    holds auxiliary-data/locations.csv. Doctor's test (flubnf.doctor.
    HUB_DATA_DIRS) no longer decides it: a clone with auxiliary-data, its
    archive and locations.csv and no target-data forecasts, so it reads
    done, although doctor FAILs it. test_home_data_step_hub.py tests the
    week and the reason against real hub data.
"""
from __future__ import annotations

import pytest

import flubnf.settings as fs
from app.core import data as core_data
from app.ui import state as ui_state
from app.ui.routes import home as H
from flubnf import doctor

from test_home_first_run import (WEEK, _ColdStart, _cls, _get,  # noqa: F401
                                 _steps, _walk, empty)
from test_outlook_toggle import _latest                         # noqa: E402

PLAIN = [("Data", "/data", "todo", None, "", False),
         ("Forecast", "/forecast", "todo", None, "", False),
         ("Output", "/output", "todo", None, "", False)]
FIRST = [("Data", "/data", "done", None, f"through {WEEK}", False),
         ("Forecast", "/forecast", "current", "step",
          "Groundhog only on this computer", False),
         ("Output", "/output", "todo", None, "", False)]


def _cold(monkeypatch):
    """The cold first paint: the warm pass has not landed."""
    monkeypatch.setattr(ui_state, "_WARM_DONE", _ColdStart())
    monkeypatch.setattr(H, "_outlook_ready", lambda: False)


def _place(p):
    """Where Start here sits: "before the map" or "beside the record",
    checked against the grid that holds the record."""
    start, outlook = p.card("hm-start"), p.card("hm-outlook")
    grid = p.one(lambda e: "homeperf" in _cls(e))
    in_grid = start in _walk(grid, [])
    if p.at(start) < p.at(outlook):
        assert not in_grid
        # the record then has its row to itself (home.css spans it)
        assert [_cls(k) for k in grid["kids"] if isinstance(k, dict)] == \
            [["card", "hm-perf"]]
        return "before the map"
    assert in_grid
    return "beside the record"


# ------------------------------------------------- P2-9: the cold paint

def test_a_fresh_install_paints_start_here_before_the_map_at_once(
        empty, monkeypatch):
    """No stored run: the cold paint knows the map will have no forecast,
    so Start here takes its first-run place there, its steps plain (the
    cold paint never reads the data, the import it exists to avoid)."""
    _cold(monkeypatch)
    p = _get()
    assert p.by_id("hm-prep")                         # the preparing card
    assert _place(p) == "before the map"
    assert _steps(p) == PLAIN
    assert empty.calls == 0


def test_the_reload_leaves_start_here_where_the_cold_paint_put_it(
        empty, monkeypatch):
    """The cold paint, then the page it reloads into once the map is
    ready: one place for the card on both; only its steps fill in."""
    with monkeypatch.context() as m:
        _cold(m)
        cold = _get()
    warm = _get()
    assert not warm.find(lambda e: e["attrs"].get("id") == "hm-prep")
    assert _place(cold) == _place(warm) == "before the map"
    assert (_steps(cold), _steps(warm)) == (PLAIN, FIRST)
    assert empty.calls == 1


def test_a_stored_run_keeps_start_here_beside_the_record_on_both_paints(
        empty, tmp_path, monkeypatch):
    """With a stored run the map will have its forecast: the card sits
    beside the record on the cold paint and after the reload."""
    _latest(tmp_path, monkeypatch)
    with monkeypatch.context() as m:
        _cold(m)
        cold = _get()
    assert cold.by_id("hm-prep")
    warm = _get()
    assert _place(cold) == _place(warm) == "beside the record"
    assert _steps(cold) == _steps(warm) == PLAIN
    assert empty.calls == 0


# ----------------- P2-10 as the re-check at 099907c left it: the Data step

ARCHIVE = "auxiliary-data/target-data-archive"
LOCS = "auxiliary-data/locations.csv"

#: hub states by what the clone holds (None: no folder at all); a path
#: ending in .csv is a file, any other a folder
HUBS = {
    "no folder": None,
    "empty clone": [],
    "auxiliary-data only": ["auxiliary-data"],
    "auxiliary-data and its archive, no locations.csv": [ARCHIVE],
    "auxiliary-data, its archive and locations.csv, no target-data":
        [ARCHIVE, LOCS],
    "target-data only": ["target-data"],
    "target-data and the archive, no locations.csv": ["target-data", ARCHIVE],
    "target-data, the archive and locations.csv":
        ["target-data", ARCHIVE, LOCS],
}


@pytest.fixture
def hub(tmp_path, monkeypatch, empty, hub_check_real):
    """A hub folder made to order, the one Home's data module and doctor
    both read; Home's newest week is WEEK whatever the folder holds (the
    archive and the shipped snapshots can hold one either way)."""
    path = tmp_path / "hub"

    def make(items):
        if items is not None:
            path.mkdir()
            for rel in items:
                p = path / rel
                if rel.endswith(".csv"):
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text("location,location_name,population\n")
                else:
                    p.mkdir(parents=True, exist_ok=True)
        for mod in (core_data, fs):
            monkeypatch.setattr(mod, "HUB", path)
            monkeypatch.setattr(mod, "ARCHIVE", path / ARCHIVE)
            monkeypatch.setattr(mod, "LOCATIONS", path / LOCS)
        return path
    return make


def _data_step(p):
    return _steps(p)[0][2:5]


@pytest.mark.parametrize("name", list(HUBS))
def test_the_data_step_is_done_only_where_a_run_can_read_the_hub(
        hub, empty, name):
    """Done exactly where the run gate (data.hub_missing) lets a run
    through and the hub holds the locations table the run reads."""
    h = hub(HUBS[name])
    usable = not core_data.hub_missing() and (h / LOCS).is_file()
    step = _data_step(_get())
    if usable:
        assert step == ("done", None, f"through {WEEK}"), name
    else:
        assert step == ("current", "step", ""), name


def test_a_clone_with_auxiliary_data_and_no_target_data_is_done(hub, empty):
    """The re-check's state (finding 6): a sparse clone widened by hand
    to auxiliary-data, its archive and locations.csv. The run gate lets
    it through and a run reads the archive, so Data is done and Forecast
    is the step to take. Doctor still FAILs the clone for its missing
    target-data."""
    hub([ARCHIVE, LOCS])
    assert core_data.hub_missing() == ""
    check = doctor._check_hub()
    assert check.status == doctor.Status.FAIL
    assert "lacks target-data" in check.detail
    assert H._start_data() == (WEEK, "")
    assert [s[2:5] for s in _steps(_get())] == [
        ("done", None, f"through {WEEK}"),
        ("current", "step", "Groundhog only on this computer"),
        ("todo", None, "")]
