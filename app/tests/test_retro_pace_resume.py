"""This computer's pace ("here") after a replay resumed at another width,
and the Retrospective page after a refused post with an absurd number
(review 3 of #93, findings 1 and 3).

  * The pace is the median of timed Oracle weeks over the cost model's
    figure for each, priced at the run record's width. The record keeps
    one width, its last start's, and a resume may change it, so a tree
    whose record shows more than one stretch of running (stopped and
    resumed, paused, resumed for added weeks) is left out
    (retro_seasons._one_stretch). Left with no pace, every line keeps its
    range and says no "here": the Forecast line, the Retrospective
    option and a replay's first time left.
  * A posted Settings form is remembered before it is checked, so the
    page prices it on every visit: a figure too large to work out leaves
    the option without its figure, never the page with a 500.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                  # noqa: E402

from app.core import estimates, retro                      # noqa: E402
from app.ui import retro_seasons as RS                     # noqa: E402
from app.ui import server as srv                           # noqa: E402
from app.ui import shared as ui_shared                     # noqa: E402
from app.ui.routes import forecast as ui_forecast          # noqa: E402
from app.ui.routes import retro as ui_retro                # noqa: E402

client = TestClient(srv.app)

SEASON, OTHER = "2098-99", "2096-97"
START, OTHER_START = "2098-08-01", "2096-08-01"
WEEKS = ["2098-10-03", "2098-10-10", "2098-10-17", "2098-10-24"]
TIMED = ["2096-10-05", "2096-10-12", "2096-10-19", "2096-10-26",
         "2096-11-02", "2096-11-09"]
LOCS = ["Alaska", "New York", "Wyoming", "Pennsylvania", "Vermont",
        "California", "US"]
FITS = len(LOCS) * 3
BASE = "Oracle SIHRS + Groundhog"
T0 = 4_000_000_000.0


@pytest.fixture
def world(tmp_path, monkeypatch):
    """An empty retro root, SEASON with four hub weeks, the worker stubbed
    and the remembered form cleared."""
    rr = tmp_path / "retro"
    rr.mkdir()
    monkeypatch.setattr(RS, "RETRO_ROOT", rr)
    monkeypatch.setattr(RS, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(retro, "available_seasons", lambda: [SEASON])
    monkeypatch.setattr(retro, "season_vintages",
                        lambda s: list(WEEKS) if s == SEASON else [])
    monkeypatch.setattr(ui_retro, "_retro_bg", lambda *a, **k: None)
    status, form = dict(RS._retro_status), dict(ui_retro._last_retro_form)
    RS._retro_status.clear()
    ui_retro._last_retro_form.clear()
    ui_shared._invalidate_scans()
    yield rr
    RS._retro_status.clear()
    RS._retro_status.update(status)
    ui_retro._last_retro_form.clear()
    ui_retro._last_retro_form.update(form)
    ui_shared._invalidate_scans()


def _model(asof: str, width: int) -> float:
    return estimates.run_seconds(
        [estimates.n_obs_for(asof, OTHER_START)], FITS, 10_000, width,
        "private")


def _timed_tree(rr: Path, ran_at: int, recorded: int, off_clock_s: float,
                status: str = "done", name: str = "") -> Path:
    """An archived Oracle replay of OTHER whose six weeks each took 2.0
    times the model at width `ran_at`, its record saying width `recorded`
    and `off_clock_s` seconds between its start and its end that its
    active clock did not count (0: one stretch of running)."""
    root = rr / (name or f"{OTHER}{retro.ARCHIVE_SEP}20970101T000000Z")
    root.mkdir(parents=True)
    ws = {w: 2.0 * _model(w, ran_at) for w in TIMED}
    active = sum(ws.values()) + 30.0
    end = T0 + active + off_clock_s
    meta = {"season": OTHER, "status": status, "total_weeks": len(TIMED),
            "started_utc": T0, "elapsed_s": active, "heartbeat_utc": end,
            "finished_utc": end if status != "running" else None,
            "segment_start_utc": end if status == "running" else None,
            "settings": {"season": OTHER, "engine": "pf", "scope": "panel6",
                         "locations": LOCS, "replicates": 3,
                         "particles": 10_000, "width": recorded},
            "week_seconds": ws}
    retro.write_meta(root, meta)
    ui_shared._invalidate_scans()
    return root


def _pf_option(html: str) -> str:
    return re.search(r'<option value="pf" data-base="Oracle SIHRS \+ '
                     r'Groundhog">([^<]*)</option>', html).group(1)


# ------------------------------------------------------ finding 1: the pace

@pytest.mark.parametrize("ran_at,recorded", [(8, 2), (2, 8)])
def test_a_replay_resumed_at_another_width_sets_no_pace(world, ran_at,
                                                        recorded):
    """The review's case: six weeks timed at 2.0 times the model at one
    width, the record then saying the other after a resume. Priced at the
    recorded width they read 0.545 or 7.3 times: the tree is left out."""
    _timed_tree(world, ran_at, recorded, off_clock_s=3600.0)
    assert RS._own_cost_ratio() == (None, 0)


def test_one_stretch_of_running_sets_the_pace(world):
    """The same weeks run in one go: the record's width is every week's,
    and the pace is the true 2.0."""
    _timed_tree(world, 8, 8, off_clock_s=0.0)
    ratio, n = RS._own_cost_ratio()
    assert n == len(TIMED) and ratio == pytest.approx(2.0, abs=1e-3)


def test_a_replay_running_in_one_stretch_counts_while_it_runs(world):
    _timed_tree(world, 8, 8, off_clock_s=0.0, status="running",
                name=OTHER)
    ratio, n = RS._own_cost_ratio()
    assert n == len(TIMED) and ratio == pytest.approx(2.0, abs=1e-3)


def test_only_the_trees_in_one_stretch_count(world):
    """A resumed tree beside one run in one go: the pace is the second's
    alone."""
    _timed_tree(world, 8, 2, off_clock_s=600.0)
    _timed_tree(world, 4, 4, off_clock_s=0.0,
                name=f"{OTHER}{retro.ARCHIVE_SEP}20970202T000000Z")
    ratio, n = RS._own_cost_ratio()
    assert n == len(TIMED) and ratio == pytest.approx(2.0, abs=1e-3)


@pytest.mark.parametrize("meta,one", [
    ({"started_utc": 100.0, "elapsed_s": 50.0, "finished_utc": 150.0}, True),
    ({"started_utc": 100.0, "elapsed_s": 50.0, "finished_utc": 150.9}, True),
    ({"started_utc": 100.0, "elapsed_s": 50.0, "finished_utc": 152.0}, False),
    # unfinished: up to the last heartbeat
    ({"started_utc": 100.0, "elapsed_s": 50.0, "finished_utc": None,
      "heartbeat_utc": 150.0}, True),
    ({"started_utc": 100.0, "elapsed_s": 50.0, "finished_utc": None,
      "heartbeat_utc": 400.0}, False),
    # resumed and finished: both marks past the active time
    ({"started_utc": 100.0, "elapsed_s": 50.0, "finished_utc": 400.0,
      "heartbeat_utc": 400.0}, False),
    # a dead worker closed later: its clock stopped at its last heartbeat
    ({"started_utc": 100.0, "elapsed_s": 50.0, "finished_utc": 900.0,
      "heartbeat_utc": 150.0}, True),
    # no times to go by: no break shown
    ({}, True),
    ({"started_utc": "x", "elapsed_s": 50.0, "finished_utc": 999.0}, True),
])
def test_one_stretch_by_the_records_times(meta, one):
    assert RS._one_stretch(meta) is one


def test_the_lines_keep_their_range_without_a_pace(world):
    """With the resumed tree left out, the Forecast line, the
    Retrospective option and a replay's first time left all keep the
    cost model's range and say no "here"."""
    _timed_tree(world, 8, 2, off_clock_s=3600.0)
    ratio, _n = RS._own_cost_ratio()
    assert ratio is None
    # the Forecast tab's Run row (routes/forecast.run_words)
    line = ui_forecast.run_words("all", 53, 3, 10_000, "2098-10-03",
                                 START, ratio, "ready")
    assert " to " in line and "here" not in line
    # the Retrospective option
    got = _pf_option(client.get("/retro").text)
    assert " to " in got and "here" not in got
    # a replay's first time left, before a week of its own is timed
    live = world / SEASON
    live.mkdir()
    meta = {"season": SEASON, "status": "running",
            "settings": {"season": SEASON, "engine": "pf",
                         "locations": LOCS, "replicates": 3,
                         "particles": 10_000, "width": 4}}
    lo, _mid, hi, basis = RS._seeded_eta(meta, SEASON, live, None)
    assert hi > lo and "this computer" not in basis


# ------------------------------------------ finding 3: an absurd Particles

@pytest.mark.parametrize("digits", [40, 400])
def test_an_absurd_particles_post_leaves_the_page_whole(world, digits):
    """A hand-made post (the browser's box stops at 100,000): refused, and
    the page that remembers the form still renders, its option without a
    figure."""
    r = client.post("/retro/run", data={
        "season": SEASON, "locations": "panel6", "engine": "pf",
        "mode": "resume", "particles": "9" * digits}, follow_redirects=False)
    assert r.status_code == 303
    assert ui_retro._last_retro_form.get("particles") == "9" * digits
    page = client.get("/retro")
    assert page.status_code == 200
    assert _pf_option(page.text) == BASE
    # and on the next visit too (the form is still remembered)
    assert client.get("/retro").status_code == 200


@pytest.mark.parametrize("particles", [10 ** 39, 10 ** 400])
def test_the_cost_words_say_nothing_for_a_figure_too_large(particles):
    assert RS._cost_words(WEEKS, START, FITS, particles, 4) == ""
    # an ordinary form still has its figure
    assert RS._cost_words(WEEKS, START, FITS, 10_000, 4).startswith("about ")


def test_a_fault_in_the_cost_leaves_the_form(world, monkeypatch):
    """Anything else going wrong in the cost: the page and its form, the
    option without a figure."""
    def boom(*a, **k):
        raise RuntimeError("no cost")
    monkeypatch.setattr(ui_retro, "_form_costs", boom)
    page = client.get("/retro")
    assert page.status_code == 200
    assert 'id="rt-run-form"' in page.text
    assert _pf_option(page.text) == BASE
