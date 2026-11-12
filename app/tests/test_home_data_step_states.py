"""Home's first-run Data step says each hub state in its own words and
names the step to take (review of #93 at 3120298e, finding 4;
app/core/data.py hub_state and hub_missing, app/ui/routes/home.py
_hub_step).

An empty hub folder and a file in the folder's place both read "holds no
data directories (a sparse checkout without them)", and no caption said
what to do. Now, as the setup scripts take each state:

  * no folder: setup fetches it;
  * an empty folder: setup.sh fetches into it; setup.ps1 only where no
    folder is, so on Windows it is deleted first;
  * a file in its place, or a folder that is no git clone: moved or
    renamed first (setup refuses both), then setup;
  * a clone without auxiliary-data (a .git there): "a sparse checkout
    without it", and setup widens it;
  * a folder the run gate passes with nothing a run can read: moved
    aside, and setup fetches a fresh clone.

The Data tab's alert takes the same words, with its own setup step.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import data as core_data
from app.ui import server as srv
from app.ui import templating
from app.ui.routes import home as H
from flubnf import doctor

from test_home_data_step_hub import _data_step, hub  # noqa: E402,F401
from test_home_first_run import empty                # noqa: E402,F401

client = TestClient(srv.app)

SETUP = "run ./setup.sh and relaunch the console"
SETUP_WIN = "run setup.ps1 and open FluBNF.bat again"


def _platform(monkeypatch, name: str) -> None:
    monkeypatch.setattr(templating, "_platform", lambda: name)


def _caption(why: str) -> None:
    assert H._start_data() == ("", why)
    assert _data_step() == ("current", "step", why)


def test_an_empty_hub_folder_is_said_empty_and_setup_fetches_into_it(hub):
    h = hub({})
    assert core_data.hub_state() == "empty"
    assert core_data.hub_missing() == f"the hub folder {h} is empty"
    _caption(f"The hub folder {h} is empty. To fetch the data into it, "
             f"{SETUP}.")
    assert "sparse" not in H._start_data()[1]
    # doctor on this system: setup itself, no move first
    assert doctor._check_hub("darwin").hint.startswith("Run ./setup.sh")


def test_on_windows_an_empty_hub_folder_is_deleted_first(hub, monkeypatch):
    h = hub({})
    _platform(monkeypatch, "win32")
    _caption(f"The hub folder {h} is empty. Delete it, then {SETUP_WIN}.")
    # doctor on Windows: setup.ps1 clones only where no folder is
    assert "Move or rename it first" in doctor._check_hub("win32").hint


def test_a_file_in_the_folders_place_is_said_and_moved_first(hub):
    h = hub(None)
    h.write_text("not a folder")
    assert core_data.hub_state() == "file"
    assert core_data.hub_missing() == (
        f"the hub path {h} is a file, not a folder; move or rename it first")
    _caption(f"The hub path {h} is a file, not a folder; move or rename it "
             f"first. To fetch the data, {SETUP}.")
    # Update data's own test (anything at the path) is as it was
    assert core_data.hub_missing(data=False) == ""


def test_a_sparse_clone_without_auxiliary_data_says_so_and_setup_widens(
        hub):
    h = hub({".git": None, "target-data": None})
    assert core_data.hub_state() == "sparse"
    _caption(f"The hub folder {h} has no auxiliary-data folder (a sparse "
             f"checkout without it). To add it, {SETUP}.")


def test_a_folder_that_is_no_clone_is_moved_first(hub):
    h = hub({"notes.txt": "mine"})
    assert core_data.hub_state() == "folder"
    _caption(f"The hub folder {h} has no auxiliary-data folder and is not a "
             f"git clone; move or rename it first. To fetch the data, "
             f"{SETUP}.")
    assert "sparse" not in H._start_data()[1]
    assert "Move or rename it first" in doctor._check_hub("darwin").hint


@pytest.mark.parametrize("files, words", [
    (None, "there is no hub folder at {h}"),
    ("file", "the hub path {h} is a file, not a folder; move or rename it "
     "first"),
    ({"notes.txt": "mine"}, "the hub folder {h} has no auxiliary-data "
     "folder and is not a git clone; move or rename it first"),
], ids=["absent", "file", "folder"])
def test_the_data_tab_says_the_same_and_its_setup_step(hub, monkeypatch,
                                                       files, words):
    _platform(monkeypatch, "linux")
    h = hub(None if files == "file" else files)
    if files == "file":
        h.write_text("not a folder")
    html = client.get("/data").text
    alert = html.split('id="hub-missing"', 1)[1].split("</div>", 1)[0]
    assert (f"No FluSight data: {words.format(h=h)}. To fetch it, run "
            "<code>./setup.sh</code> and relaunch the console.") in alert


@pytest.mark.parametrize("make, gate", [
    (None, "absent"), ("file", "file"), ({}, "empty"),
    ({".git": None}, "sparse"), ({"x": "y"}, "folder"),
    ({"auxiliary-data": None}, ""),
], ids=["absent", "file", "empty", "sparse", "folder", "passes"])
def test_the_run_gate_refuses_exactly_where_a_state_is_named(hub, make,
                                                            gate):
    h = hub(None if make == "file" else make)
    if make == "file":
        h.write_text("x")
    assert core_data.hub_state() == gate
    assert bool(core_data.hub_missing()) == bool(gate)
    if gate:
        assert str(h) in core_data.hub_missing()
        assert H._hub_step(gate).endswith(f"{SETUP}.")
