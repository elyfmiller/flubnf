"""The runner's estimates (app/core/runner.py): the first estimate is the
engine's cost model times K_FIRST over 2024-25's weeks, pinned to the
spec's figures at widths 16 and 8; k is then the median of this
computer's last ten jobs of that size (other sizes, refusals and jobs
that fitted no week left out) and the words say so; the disk kept and
at the peak by size and Oracle step; the queued notice's words, exactly;
and the limits, presets capped at half the memory, their time scaled
on the public engine as its estimates are."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import retro                               # noqa: E402
from app.core import runner                              # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf                          # noqa: E402
from test_experiments import PILOT_WEEKS, VINTAGES, _replay  # noqa: E402
from test_runner_folders import (SMOKE, W0, W1, calendar,  # noqa: E402,F401
                                 student, students)
from test_runner_queue import state                      # noqa: E402

GiB, MiB = runner.GiB, runner.MiB
PILOT = {**SMOKE, "size": "pilot"}
FULL = {**SMOKE, "size": "full"}
WEEKS = {"smoke": [W0, W1], "pilot": PILOT_WEEKS, "full": VINTAGES}


def _run(size: str, k: float, weeks: int = 2, outcome: str = "done",
         kind: str = "run") -> dict:
    """A recent entry of runner.json."""
    return {"folder": "bob", "id": f"x_2024-25_{size}", "size": size,
            "kind": kind, "utc": "2026-11-02T10:23:55Z", "outcome": outcome,
            "text": "", "seconds": 51.2, "weeks": weeks, "k": k,
            "rss_peak": 0, "disk_peak": 0}


@pytest.mark.parametrize("width, smoke, pilot, full", [
    (16, "about 1:16", "about 10:32", "about 3:56:39"),
    (8, "about 1:16", "about 20:53", "about 7:52:39")])
def test_first_estimate_is_the_cost_model_times_two(monkeypatch, width,
                                                    smoke, pilot, full):
    monkeypatch.setattr(pf, "DEFAULT_SHARD_WIDTH", width)
    got = {size: runner.estimate({**SMOKE, "size": size}, weeks=WEEKS[size])
           for size in WEEKS}
    words = {size: sb.eta_words(e["seconds"], e["seconds"])
             for size, e in got.items()}
    assert words == {"smoke": smoke, "pilot": pilot, "full": full}
    assert [(e["weeks"], e["fits"], e["measured"]) for e in got.values()] == [
        (2, 4, False), (14, 140, False), (30, 4770, False)]
    # Σ k·⌈F/W⌉·c(n_w) + SCORE_S by hand: the full's 159 fits a week
    c = [pf.cell_seconds({"n_obs": runner._week_n("2024-25", w),
                          "particles": 10_000}) for w in VINTAGES]
    assert got["full"]["seconds"] == pytest.approx(
        round(2.0 * -(-159 // width) * sum(c) + 40, 1))
    assert runner._week_n("2024-25", "2024-11-16") == 16
    # stored weeks are not fitted again; the weeks come from the hub's
    # vintages when they are not given
    left = runner.estimate(PILOT, weeks=PILOT_WEEKS, done=PILOT_WEEKS[:13])
    assert left["weeks"] == 1 and left["fits"] == 10
    calendar(monkeypatch)
    assert runner.estimate(PILOT) == got["pilot"]
    assert runner.estimate({**SMOKE, "season": "2023-24"})["weeks"] == 0


def test_measured_k_is_the_median_of_this_computers_jobs_of_that_size(
        monkeypatch, students, tmp_path):
    monkeypatch.setattr(pf, "DEFAULT_SHARD_WIDTH", 16)
    first = runner.estimate(PILOT, weeks=PILOT_WEEKS)
    assert runner._k("pilot", []) == (runner.K_FIRST, 0)
    recent = [_run("smoke", 9.0), _run("pilot", 1.5, outcome="limit"),
              _run("pilot", 7.0, weeks=0), _run("pilot", 8.0,
                                                outcome="refused"),
              _run("pilot", 8.0, outcome="ended"),
              _run("pilot", 8.0, kind="tidy"),
              _run("pilot", 2.5, outcome="stopped"), _run("pilot", 1.0),
              _run("pilot", None), _run("full", 9.0)]
    assert runner._k("pilot", recent) == (1.5, 3)
    got = runner.estimate(PILOT, weeks=PILOT_WEEKS, recent=recent)
    assert got["measured"] is True
    assert got["seconds"] == pytest.approx(
        round((first["seconds"] - 10) * 1.5 / 2.0 + 10, 1))
    # the last ten of the size, newest first
    many = [_run("pilot", 1.0)] * 10 + [_run("pilot", 9.0)] * 5
    assert runner._k("pilot", many) == (1.0, 10)
    assert runner._k("pilot", [_run("pilot", 1.0), _run("pilot", 3.0)]) == (
        2.0, 2)
    # the words of the queued notice switch from "a first estimate"
    assert runner._timed_words("pilot", []) == (
        "a first estimate: no pilot has finished on this computer yet")
    assert runner._timed_words("pilot", recent) == (
        "timed from 3 pilots on this computer")
    assert runner._timed_words("pilot", recent[1:2]) == (
        "timed from 1 pilot on this computer")
    top = student(students, "alice")
    monkeypatch.setattr(sb, "SANDBOX", top)
    calendar(monkeypatch)
    monkeypatch.setattr(runner, "_free", lambda: 500 * GiB)
    state(students, recent=recent)
    got = runner.enqueue(PILOT)
    assert got["estimate"]["measured"] is True
    assert got["detail"].startswith(
        "It runs about 7:56 once it starts (timed from 3 pilots on this "
        "computer). It starts within a minute.")


def test_kept_and_peak_bytes_by_size_and_oracle():
    h = runner._h
    got = {}
    for size in WEEKS:
        for on in (True, False):
            got[size, on] = runner.estimate(
                {**SMOKE, "size": size, "oracle": on}, weeks=WEEKS[size])
    assert {k: h(e["keep_bytes"]) for k, e in got.items()} == {
        ("smoke", True): "857.4 KB", ("smoke", False): "214.8 KB",
        ("pilot", True): "9.5 MB", ("pilot", False): "878.9 KB",
        ("full", True): "74.8 MB", ("full", False): "7.8 MB"}
    assert {size: h(got[size, True]["peak_bytes"]) for size in WEEKS} == {
        "smoke": "33.7 MB", "pilot": "173.8 MB", "full": "2.6 GB"}
    assert [got[size, True]["keep_bytes"] for size in WEEKS] == [
        878_000, 9_930_000, 78_455_000]
    assert [got[size, True]["peak_bytes"] for size in WEEKS] == [
        35_332_432, 182_202_160, 2_817_582_344]
    # the folder cap leaves room over every peak
    for size in WEEKS:
        assert runner.LIMITS[size].disk > 3 * got[size, True]["peak_bytes"]
    # a week stored keeps nothing more
    one = runner.estimate(SMOKE, weeks=[W0, W1], done=[W0])
    assert one["keep_bytes"] == 2 * (2_500 * 3 + 37_000) + 250_000 + 200_000


def test_estimate_words(students, tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "DEFAULT_SHARD_WIDTH", 16)
    top = student(students, "alice")
    monkeypatch.setattr(sb, "SANDBOX", top)
    calendar(monkeypatch)
    monkeypatch.setattr(runner, "_free", lambda: int(412.3 * GiB))
    rr = tmp_path / "retro"
    _replay(rr / "2024-25")
    eid = "sihrs_2024-25_pilot_oracle"
    state(students, retro_root=str(rr))
    got = runner.enqueue(PILOT)
    assert (got["kind"], got["text"]) == (
        "ok", f"Queued {eid}: 1st in line on the runner.")
    assert got["detail"] == (
        "It runs about 10:32 once it starts (a first estimate: no pilot has "
        "finished on this computer yet). It starts within a minute. While it "
        "runs it needs about 173.8 MB of disk and keeps about 9.5 MB. "
        "Compared with the shipped replay of 2024-25 (the Oracle SIHRS) on "
        "the cells both score. FluBNF keeps 20.0 GB free on this disk; "
        "412.3 GB is free now.")
    # a job running and one ahead: 2nd in line, starting in an hour and five
    runner.stop("alice", eid)
    state(students, retro_root=str(rr),
          job={"kind": "run", "folder": "bob", "id": "x_2024-25_full",
               "size": "full", "pid": 1, "eta_s": 3600, "keep_bytes": 0},
          waiting=[{"folder": "carol", "id": "y_2024-25_smoke",
                    "size": "smoke", "seconds": 300.0, "keep_bytes": 0}])
    got = runner.enqueue(PILOT)
    assert got["text"] == f"Queued {eid}: 2nd in line on the runner."
    assert got["detail"].startswith(
        "It runs about 10:32 once it starts (a first estimate: no pilot has "
        "finished on this computer yet) and starts in about 1:05:00. While "
        "it runs")
    assert got["wait_s"] == 3900.0
    # the runner not running
    runner.stop("alice", eid)
    state(students, retro_root=str(rr), pid=2_147_483_646)
    got = runner.enqueue(PILOT)
    assert (got["kind"], got["text"]) == (
        "warn", f"Queued {eid}; the runner is not running, so it waits until "
        "it is started.")
    assert got["detail"].startswith(
        "It runs about 10:32 once it starts (a first estimate: no pilot has "
        "finished on this computer yet). While it runs it needs about "
        "173.8 MB")
    # the Oracle step off, and a warning beside the reference
    state(students, retro_root=str(rr))
    got = runner.enqueue({**PILOT, "oracle": False})
    assert ("Compared with the shipped replay of 2024-25 (the Liu-West "
            "filter alone) on the cells both score.") in got["detail"]
    assert "keeps about 878.9 KB" in got["detail"]
    assert retro.human_bytes(runner.FREE_FLOOR) == "20.0 GB"


def test_limits_are_presets_capped_at_half_the_memory(monkeypatch):
    assert runner.LIMITS == {
        "smoke": runner.Limits(1800, 4 * GiB, 512 * MiB),
        "pilot": runner.Limits(7200, 16 * GiB, 1 * GiB),
        "full": runner.Limits(57600, 32 * GiB, 10 * GiB)}
    pages = {"SC_PHYS_PAGES": 4 * 2**20, "SC_PAGE_SIZE": 4096}   # 16 GiB
    monkeypatch.setattr(os, "sysconf", lambda name: pages[name],
                        raising=False)
    got = {size: runner.limits(size) for size in runner.LIMITS}
    assert {s: x.memory for s, x in got.items()} == {
        "smoke": 4 * GiB, "pilot": 8 * GiB, "full": 8 * GiB}
    assert {s: (x.seconds, x.disk) for s, x in got.items()} == {
        s: (x.seconds, x.disk) for s, x in runner.LIMITS.items()}

    def unknown(name):
        raise ValueError(name)
    monkeypatch.setattr(os, "sysconf", unknown, raising=False)
    assert runner.limits("full") == runner.LIMITS["full"]
    with pytest.raises(KeyError):
        runner.limits("huge")


def test_the_time_limits_scale_with_the_public_engine(monkeypatch):
    # its fits take pf.PUBLIC_COST_RATIO as long (pf.cell_seconds): the
    # time limits too, so each keeps its margin over the first estimate;
    # the memory and the folder are the private engine's
    monkeypatch.setattr(pf, "DEFAULT_SHARD_WIDTH", 16)
    monkeypatch.setattr(os, "sysconf", lambda name: {
        "SC_PHYS_PAGES": 2**28, "SC_PAGE_SIZE": 4096}[name], raising=False)

    def margins():
        return {size: runner.limits(size).seconds / runner.estimate(
            {**SMOKE, "size": size}, weeks=WEEKS[size])["seconds"]
            for size in WEEKS}
    private = {size: runner.limits(size) for size in runner.LIMITS}
    assert private == runner.LIMITS
    before = margins()
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    public = {size: runner.limits(size) for size in runner.LIMITS}
    assert public["full"].seconds == 16 * 3600 * pf.PUBLIC_COST_RATIO
    for size, lim in public.items():
        assert lim.seconds == (runner.LIMITS[size].seconds
                               * pf.PUBLIC_COST_RATIO)
        assert (lim.memory, lim.disk) == (private[size].memory,
                                          private[size].disk)
    after = margins()
    assert {s: round(m) for s, m in before.items()} == {
        "smoke": 24, "pilot": 11, "full": 4}
    for size in WEEKS:
        assert after[size] == pytest.approx(before[size], rel=0.02)
