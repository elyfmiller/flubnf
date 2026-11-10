"""Home's first-run Data step against the hub's own data (the re-check of
#93 at 099907c, findings 6 and 7; app/ui/routes/home.py _start_data).

  * 6: the step is judged by the test a run must pass (data.hub_missing),
    so a sparse clone with auxiliary-data (the archive and locations.csv)
    and no target-data, which forecasts, reads done. It read "current",
    with no reason, because doctor wants target-data too.
  * 7: "through <week>" is the newest week the hub itself holds (its live
    target file or its archive), never a week only the shipped snapshots
    hold: hub folders with no data read "current", where they read "done,
    through 2026-04-25". A hub with no locations table, which a run reads
    and fails without, is not done either.
  * When the step is not done, Home has the reason in a plain sentence
    (start_data_why): the run gate's words, no locations table, or no
    week in the hub.

The real data module reads a hub folder made to order here, with the
committed shipped snapshots in place; only the page's run store is empty.
"""
from __future__ import annotations

import pytest

import flubnf.settings as fs
from app.core import data as core_data
from app.ui import state as ui_state
from app.ui.routes import home as H

from test_home_first_run import _get, _steps, empty  # noqa: F401

LIVE = "target-data/target-hospital-admissions.csv"
ARCHIVE = "auxiliary-data/target-data-archive"
LOCS = "auxiliary-data/locations.csv"


@pytest.fixture
def hub(tmp_path, monkeypatch, empty, hub_check_real, shipped_vintages):
    """make(files): a hub folder holding `files` (relative path -> text,
    or None for a folder), read by the real data module and doctor, with
    the shipped snapshots committed to the repository in place."""
    path = tmp_path / "hub"

    def make(files=None):
        if files is not None:
            path.mkdir()
            for rel, text in files.items():
                p = path / rel
                if text is None:
                    p.mkdir(parents=True, exist_ok=True)
                else:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(text)
        monkeypatch.setattr(ui_state, "data_mod", core_data)
        for mod in (core_data, fs):
            monkeypatch.setattr(mod, "HUB", path)
            monkeypatch.setattr(mod, "ARCHIVE", path / ARCHIVE)
            monkeypatch.setattr(mod, "LOCATIONS", path / LOCS)
        return path
    return make


def _truth(*weeks) -> str:
    return "date,location,location_name,value\n" + "".join(
        f"{w},US,US,{i + 10}\n" for i, w in enumerate(weeks))


def _vintage(week) -> tuple:
    return (f"{ARCHIVE}/target-hospital-admissions_{week}.csv",
            _truth(week))


LOC_TEXT = "location,location_name,population\nUS,US,330000000\n"


def _data_step():
    return _steps(_get())[0][2:5]


def _shipped_newest() -> str:
    weeks = core_data.shipped_weeks()
    assert weeks, "the repository ships snapshots"
    return weeks[-1]


# ---------------------------------------------------------- finding 6

def test_a_sparse_clone_that_can_forecast_reads_done(hub):
    """auxiliary-data with its archive and locations.csv, no target-data:
    the run gate lets it through, and a run reads the archive."""
    h = hub(dict([_vintage("2025-05-31"), (LOCS, LOC_TEXT)]))
    assert not (h / "target-data").exists()
    assert core_data.hub_missing() == ""
    assert core_data.vintage_path("2025-05-31").parent == h / ARCHIVE
    assert H._start_data() == ("2025-05-31", "")
    assert _data_step() == ("done", None, "through 2025-05-31")


@pytest.mark.parametrize("files, why", [
    (None, "There is no hub folder at {h}."),
    ({"target-data": None},
     "The hub folder {h} holds no data directories (a sparse checkout "
     "without them)."),
])
def test_where_the_run_gate_refuses_the_reason_is_its_own(hub, files, why):
    h = hub(files)
    gate = core_data.hub_missing()
    assert gate
    assert H._start_data() == ("", why.format(h=h))
    assert why.format(h=h).lower().startswith(gate.lower())
    assert _data_step() == ("current", "step", "")


# ---------------------------------------------------------- finding 7

def test_hub_folders_with_no_data_are_not_done_through_a_shipped_week(hub):
    h = hub({"target-data": None, ARCHIVE: None, LOCS: LOC_TEXT})
    # the shipped snapshots still give data.newest_week a week
    assert core_data.newest_week() == _shipped_newest()
    assert H._start_data() == (
        "", f"The hub folder {h} holds no weeks of data yet.")
    assert _data_step() == ("current", "step", "")


def test_a_hub_with_no_locations_table_is_not_done(hub):
    h = hub(dict([_vintage("2025-05-31"), ("target-data", None)]))
    assert core_data.hub_missing() == ""
    assert H._start_data() == (
        "", f"The hub folder {h} has no auxiliary-data/locations.csv.")
    assert _data_step() == ("current", "step", "")


def test_the_week_is_the_hubs_own_when_the_shipped_ones_are_newer(hub):
    hub(dict([_vintage("2025-05-31"), (LOCS, LOC_TEXT)]))
    assert _shipped_newest() > "2025-05-31"
    assert _data_step() == ("done", None, "through 2025-05-31")


def test_the_live_file_counts_as_the_hubs_own(hub):
    late = "2026-10-31"
    assert late > _shipped_newest()
    hub({LIVE: _truth("2026-10-24", late), ARCHIVE: None, LOCS: LOC_TEXT})
    assert H._start_data() == (late, "")
    assert _data_step() == ("done", None, f"through {late}")


def test_a_shipped_week_the_hub_also_holds_is_its_own(hub):
    """A hub archive that holds the newest shipped week reads through
    that week (the hub archive serves it first)."""
    wk = _shipped_newest()
    hub(dict([_vintage(wk), (LOCS, LOC_TEXT)]))
    assert _data_step() == ("done", None, f"through {wk}")


def test_an_unreadable_hub_says_so(hub, monkeypatch):
    hub(dict([_vintage("2025-05-31"), (LOCS, LOC_TEXT)]))

    def broken():
        raise OSError("disk gone")
    monkeypatch.setattr(core_data, "newest_week", broken)
    assert H._start_data() == ("", "The hub data could not be read: "
                                   "disk gone.")
    assert _data_step() == ("current", "step", "")
