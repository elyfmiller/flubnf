"""The one-stretch window (review 3 of #93, re-check R8;
app/ui/retro_seasons.py _one_stretch and _ONE_STRETCH_SLACK_S).

A run record keeps no mark of a stop, a pause or a resume: a resume keeps
started_utc and elapsed_s and writes the same fields as the first start.
So _one_stretch reads the record's times alone, and a break of up to
_ONE_STRETCH_SLACK_S (1 s) still reads as one stretch. Only a scripted
stop and resume is that quick. Pinned here on records the real writers
(app/core/retro.py) make on a patched clock, so a change to the window,
or a resume mark added to the record, shows.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import retro                                 # noqa: E402
from app.ui import retro_seasons as RS                     # noqa: E402

T0 = 4_000_000_000.0
SEASON = "2096-97"
WEEKS = ["2096-10-05", "2096-10-12", "2096-10-19", "2096-10-26"]


def _settings(width: int) -> dict:
    return {"season": SEASON, "engine": "pf", "scope": "panel6",
            "replicates": 3, "particles": 10_000, "width": width}


def _record(tmp_path, monkeypatch, gap, how: str = "stop") -> dict:
    """Two weeks at width 4, a break of `gap` seconds (None: none at all)
    by a stop and resume at width 2, or a pause and its end, then two
    more weeks and the finish: the record the writers leave."""
    clock = [T0]
    monkeypatch.setattr(retro, "_now", lambda: clock[0])
    root = tmp_path / "tree"
    root.mkdir()

    def tick(s):
        clock[0] += s

    retro._start_record(root, SEASON, len(WEEKS), _settings(4))
    for w in WEEKS[:2]:
        tick(40.0)
        retro._Heartbeat(root).beat()
        tick(20.0)
        retro._record_week(root, w, 60.0)
    if gap is not None:
        if how == "stop":
            retro._finish_record(root, "stopped")
            tick(gap)
            retro._start_record(root, SEASON, len(WEEKS), _settings(2))
        else:
            retro._set_paused(root, True)
            tick(gap)
            retro._set_paused(root, False)
    for w in WEEKS[2:]:
        tick(60.0)
        retro._record_week(root, w, 60.0)
    retro._finish_record(root, "done")
    return retro.read_meta(root)


def test_the_window_is_one_second():
    assert RS._ONE_STRETCH_SLACK_S == 1.0
    doc = RS._one_stretch.__doc__
    assert "no mark of a stop, a pause or a resume" in doc
    assert "_ONE_STRETCH_SLACK_S or less reads as one stretch" in doc


def test_a_run_in_one_go_is_one_stretch(tmp_path, monkeypatch):
    meta = _record(tmp_path, monkeypatch, None)
    assert meta["heartbeat_utc"] - meta["started_utc"] == pytest.approx(
        meta["elapsed_s"], abs=1e-6)
    assert RS._one_stretch(meta)


@pytest.mark.parametrize("how", ["stop", "pause"])
@pytest.mark.parametrize("gap,one", [
    (0.0, True), (0.5, True), (1.0, True),    # within the window: unseen
    (1.01, False), (1.5, False), (60.0, False), (3600.0, False)])
def test_a_break_past_the_window_shows(tmp_path, monkeypatch, how, gap,
                                       one):
    """A stop and resume, or a pause, of `gap` seconds: past 1 s the
    record shows two stretches (its weeks may have run at another width);
    within it the record cannot tell, and reads as one."""
    meta = _record(tmp_path, monkeypatch, gap, how)
    assert meta["status"] == "done"
    if how == "stop":
        assert meta["settings"]["width"] == 2       # the last start's
    assert RS._one_stretch(meta) is one


def test_the_record_holds_no_mark_of_the_resume(tmp_path, monkeypatch):
    """The same keys with and without a break: nothing else to go by."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    one = _record(a, monkeypatch, None)
    two = _record(b, monkeypatch, 0.5)
    assert set(one) == set(two)
    assert one["week_seconds"] == two["week_seconds"]
