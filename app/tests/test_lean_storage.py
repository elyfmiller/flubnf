"""Lean storage on the runner (app/core/experiments.py drop_samples and the
lean branch of app/core/retro_store.py): a week's forecasting samples are
dropped only when its quantile sidecar equals what they give, the marker
is written before they go (a kill between reads as before), the week
keeps what the summary and its failures read, and nothing but an
experiment's stored week is ever touched. A lean week reads as stored,
from its sidecar alone, never rebuilt; score, stale, status and _failures
hold after the drop; a resume skips lean weeks and keeps its refusals;
a lean week whose sidecar vanished is fitted again; and frozen weeks that
are not dates lead nowhere.

golden/retro_store_reads.json holds what the shipped readers read from a
tree with no marker anywhere: a gzip week, a plain week, a sidecar
without the Liu-West filter beside an applied oracle.json, a sidecar
older than its samples, an incomplete week and an interrupted migration.
It was captured from origin/dev 24ac926, before retro_store learned lean
weeks; regenerate only for a deliberate change to those readers, and
review its diff:

    python app/tests/test_lean_storage.py --write-golden
"""
import gzip
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

if __name__ == "__main__":
    # the golden regeneration runs without conftest: as it does, keep the
    # state folder and the hub out of the checkout and this machine's clone
    import atexit
    import shutil
    import tempfile
    _state = tempfile.mkdtemp(prefix="flubnf-golden-state-")
    atexit.register(shutil.rmtree, _state, True)
    os.environ.setdefault("FLUBNF_STATE_DIR", _state)
    os.environ.setdefault("FLUBNF_HUB", os.path.join(_state, "no-hub"))

import numpy as np                                       # noqa: E402
import pytest                                            # noqa: E402

from app.core import experiments as X                    # noqa: E402
from app.core import horizons as hz                      # noqa: E402
from app.core import library as L                        # noqa: E402
from app.core import retro                               # noqa: E402
from app.core import retro_store as RS                   # noqa: E402
from app.core.engines import pf as PF                    # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL    # noqa: E402
from test_experiments import (SMOKE_FP, SMOKE_WEEKS,     # noqa: E402,F401
                              _weeks_run, season, truth)

GOLDEN = Path(__file__).resolve().parent / "golden" / "retro_store_reads.json"

#: the smoke's locations, and an experiment of it with the Oracle step
LOCS = ("California", "Vermont")
SMOKE = {"model": "sihrs", "season": "2024-25"}
W0, W1 = SMOKE_WEEKS


def _record(asof: str, seed: int = 0, locs=LOCS) -> dict:
    """A stored week's record in canonical horizons: the pf's draws for
    `locs` (the anchor beside them) and the Groundhog's quantiles at every
    level for both smoke locations."""
    rng = np.random.default_rng(seed)
    return {"asof": asof,
            "pf": {loc: {**{h: rng.gamma(4.0, 25.0, 200).tolist()
                            for h in hz.HORIZONS},
                         hz.ORIGIN: rng.gamma(4.0, 20.0, 200).tolist()}
                   for loc in locs},
            "analogue": {loc: {h: {str(L): 10.0 * (j + 1)
                                   for j, L in enumerate(QL)}
                               for h in hz.HORIZONS}
                         for loc in LOCS}}


def _oracle(locs=LOCS) -> dict:
    """oracle.json with the step applied: the Liu-West filter's own
    quantiles (quantiles.null)."""
    return {"applied": True, "quantiles": {"levels": list(QL), "null": {
        loc: {h: {"unrounded": [20.0 + i + j for j in range(len(QL))]}
              for h in hz.HORIZONS}
        for i, loc in enumerate(locs)}}}


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _store(folder: Path, asof: str, *, oracle: bool = True, seed: int = 0,
           heavy: bool = True, locs=LOCS) -> Path:
    """One week as run_week stores it: oracle.json first, then the samples
    and their sidecar; heavy, also what a week with a failed fit keeps
    today: the cell trees, a runner script, the cell lists, the prepare
    record, HALT, the fit markers (one failed), a prepare failure and the
    donor bank."""
    wd = Path(folder) / "weeks" / asof
    wd.mkdir(parents=True, exist_ok=True)
    if oracle:
        _write(wd / RS.ORACLE_NAME, json.dumps(_oracle()))
    RS.write_week_samples(wd, _record(asof, seed, locs))
    if heavy:
        for key in ("California_r0", "Vermont_r0"):
            (wd / key / "out").mkdir(parents=True)
            (wd / key / "out" / "traj.npz").write_bytes(b"x" * 5000)
            _write(wd / key / "m.bngl", "begin model\nend model\n")
        _write(wd / "runner_0.py", "# the week's runner\n")
        _write(wd / "cells.json", "[]")
        _write(wd / "cells_0.json", "[]")
        _write(wd / retro.PREP_NAME, "{}")
        _write(wd / retro.HALT_NAME, "")
        retro.mark_cell_done(wd, "California_r0", "ok")
        retro.mark_cell_done(wd, "Vermont_r0", "FAIL: the fit diverged")
        _write(wd / PF.PREPARE_FAILURES_NAME,
               json.dumps({"New_York": "no data this week"}))
        (wd / "oracle_bank").mkdir()
        _write(wd / "oracle_bank" / "donors.json", "{}")
    return wd


def _experiment(weeks=SMOKE_WEEKS, settings=SMOKE, **meta) -> Path:
    """An experiment's folder as a finished replay leaves it, before any
    week is stored: experiment.json and its run record."""
    folder = X.root() / X.experiment_id(settings)
    folder.mkdir(parents=True, exist_ok=True)
    L.write_json(folder / X.SETTINGS, json.loads(X.settings_text(settings)))
    now = time.time()
    retro.write_meta(folder, {
        "status": "done", "started_utc": now - 3_000.0,
        "finished_utc": now - 1_000.0, "elapsed_s": 12.5,
        "settings": {"experiment": SMOKE_FP, "model": settings["model"],
                     "model_fingerprint": "m" * 64, "weeks": list(weeks),
                     "locations": list(LOCS), "replicates": 1,
                     "particles": 10_000},
        **meta})
    return folder


def _tree(root: Path) -> dict:
    """Every path under a tree, links not followed: (size, mtime_ns), -1
    for a folder's size."""
    out = {}
    for dirpath, dirs, files in os.walk(root):
        for n in dirs + files:
            p = Path(dirpath) / n
            st = os.lstat(p)
            out[p.relative_to(root).as_posix()] = (
                -1 if p.is_dir() and not p.is_symlink() else st.st_size,
                st.st_mtime_ns)
    return out


def _reads(folder: Path, asof: str) -> dict:
    """What the readers give for one week of a folder."""
    wd = RS._week_dir(folder, asof)
    return {"done": RS.week_done(folder, asof),
            "sidecar": RS.read_week_quantiles(wd),
            "members": RS.week_member_quantiles(folder, asof),
            "samples": [p.name for p in RS.season_sample_files(folder)],
            "weeks": [p.name for p in RS.season_week_files(folder)],
            "on_disk": retro._weeks_on_disk(folder)}


# ---------------------------------------------------------- the drop


def test_drop_needs_a_sidecar_equal_to_the_draws(sandbox_root):
    folder = _experiment()
    wd = _store(folder, W0)
    assert X.drop_samples(folder, W0) > 0
    assert RS.samples_file(wd) is None and RS.week_dropped(wd)
    # the step off: no Liu-West filter in the draws, none needed
    wd = _store(folder, W1, oracle=False)
    assert RS.FILTER_MEMBER not in RS.read_week_quantiles(wd)
    assert X.drop_samples(folder, W1) > 0 and RS._lean(wd)

    def kept(edit):
        """A fresh week edited so its sidecar is not what its draws give:
        refused, and nothing in the folder written."""
        retro.delete_tree(RS._week_dir(folder, W1))
        wd = _store(folder, W1, seed=1)
        edit(wd)
        before = _tree(folder)
        assert X.drop_samples(folder, W1) == 0
        assert _tree(folder) == before
        assert RS.samples_file(wd) is not None

    def sidecar(change):
        def edit(wd):
            mq = RS.read_week_quantiles(wd)
            change(mq)
            RS.write_week_quantiles(wd, mq)
        return edit

    def off(member):
        def change(mq):
            mq[member]["Vermont"]["2"][0.5] += 1e-9
        return change
    for member in ("pf", "analogue", RS.FILTER_MEMBER):
        kept(sidecar(off(member)))                      # one value off
    kept(lambda wd: (wd / RS.QUANTILES_NAME).unlink())  # no sidecar
    kept(sidecar(lambda mq: mq.pop("pf")))              # no pf
    # the step on, and the sidecar without the Liu-West filter
    kept(sidecar(lambda mq: mq.pop(RS.FILTER_MEMBER)))
    # a sidecar older than its samples is never rebuilt here

    def older(wd):
        t = RS.samples_file(wd).stat().st_mtime - 60
        os.utime(wd / RS.QUANTILES_NAME, (t, t))
    kept(older)

    def unreadable(wd):
        """Draws that cannot be read, the sidecar still current."""
        t = (wd / RS.QUANTILES_NAME).stat().st_mtime - 60
        (wd / RS.SAMPLES_GZ).write_bytes(b"not gzip")
        os.utime(wd / RS.SAMPLES_GZ, (t, t))
        assert RS.read_week_quantiles(wd) is not None
    kept(unreadable)


def test_marker_then_unlink(sandbox_root):
    folder = _experiment()
    wd = _store(folder, W0)
    size = (wd / RS.SAMPLES_GZ).stat().st_size
    t0 = time.time()
    X.drop_samples(folder, W0)
    marker = json.loads((wd / RS.DROPPED_NAME).read_text(encoding="utf-8"))
    assert sorted(marker) == ["bytes", "utc"] and marker["bytes"] == size
    assert X._utc(t0 - 1) <= marker["utc"] <= X._utc(time.time() + 1)
    assert marker["utc"].endswith("Z")
    assert not (wd / (RS.DROPPED_NAME + ".tmp")).exists()
    # a kill between the marker and the unlink: both stand, and the
    # samples win in every reader
    wd = _store(folder, W1, heavy=False)
    before = _reads(folder, W1)
    _write(wd / RS.DROPPED_NAME, json.dumps({"bytes": 1,
                                             "utc": marker["utc"]}))
    assert RS.week_dropped(wd) and not RS._lean(wd)
    assert _reads(folder, W1) == before
    assert before["weeks"] == [RS.QUANTILES_NAME, RS.SAMPLES_GZ]
    # a sidecar older than the samples is rebuilt from them, as before
    t = (wd / RS.SAMPLES_GZ).stat().st_mtime - 60
    os.utime(wd / RS.QUANTILES_NAME, (t, t))
    assert RS.read_week_quantiles(wd) is None
    assert RS.week_member_quantiles(folder, W1) == before["members"]
    # and the next drop finishes the job, its marker written afresh
    assert X.drop_samples(folder, W1) > 0
    assert RS._lean(wd) and json.loads((wd / RS.DROPPED_NAME).read_text(
        encoding="utf-8"))["bytes"] > 1
    # a marker's tmp left by a drop killed before its replace is no bar
    wd = _store(folder, W1, heavy=False, seed=2)
    (wd / RS.DROPPED_NAME).unlink()
    _write(wd / (RS.DROPPED_NAME + ".tmp"), "{")
    assert X.drop_samples(folder, W1) > 0 and RS._lean(wd)
    assert not (wd / (RS.DROPPED_NAME + ".tmp")).exists()


def test_drop_keeps_what_the_summary_and_failures_read(sandbox_root):
    folder = _experiment()
    _write(folder / "failures.log", f"{W1}: every fit failed\n")
    X.write_summary(folder, {"complete": False})
    wd = _store(folder, W0)
    _write(wd / (RS.QUANTILES_NAME + ".tmp"), "{")
    top = sorted(os.listdir(folder))
    filtered = RS.filter_quantiles(wd)
    failed, prep = retro.cells_failed(wd), PF.read_prepare_failures(wd)
    assert failed and prep and filtered
    want = 0
    for p in wd.iterdir():
        if p.name not in X.LEAN_KEEP:
            want += (retro.dir_size(p) if p.is_dir() else p.stat().st_size)
    assert X.drop_samples(folder, W0) == want
    assert X.LEAN_KEEP == (RS.QUANTILES_NAME, RS.ORACLE_NAME, "oracle_bank",
                           retro.CELL_DONE_DIRNAME, PF.PREPARE_FAILURES_NAME,
                           RS.DROPPED_NAME)
    assert sorted(os.listdir(wd)) == sorted(X.LEAN_KEEP)
    assert retro.cells_failed(wd) == failed
    assert PF.read_prepare_failures(wd) == prep
    assert RS.filter_quantiles(wd) == filtered
    assert (wd / "oracle_bank" / "donors.json").is_file()
    assert sorted(os.listdir(folder)) == top          # the folder level
    # a week already lean: only what was left beside it goes
    (wd / "Vermont_r0").mkdir()
    _write(wd / "Vermont_r0" / "pf.conf", "fit_type = pf\n")
    before = RS.read_week_quantiles(wd)
    assert X.drop_samples(folder, W0) == len("fit_type = pf\n")
    assert sorted(os.listdir(wd)) == sorted(X.LEAN_KEEP)
    assert RS.read_week_quantiles(wd) == before


def test_drop_refuses_anything_but_an_experiments_stored_week(
        sandbox_root, tmp_path, monkeypatch):
    def refused(folder, asof):
        before = _tree(folder)
        assert X.drop_samples(folder, asof) == 0
        assert _tree(folder) == before
    # a shipped-like root: no experiment.json, no experiment in its record
    shipped = tmp_path / "retro" / "2024-25"
    retro.write_meta(shipped, {"settings": {
        **X.SHIPPED_SETTINGS, "weeks": list(SMOKE_WEEKS)}})
    _store(shipped, W0)
    refused(shipped, W0)
    # its experiment.json, but a record that names no experiment
    folder = _experiment()
    _store(folder, W0)
    meta = retro.read_meta(folder)
    retro.write_meta(folder, {**meta, "settings": {
        k: v for k, v in meta["settings"].items() if k != "experiment"}})
    refused(folder, W0)
    retro.write_meta(folder, meta)
    # experiment.json naming another experiment than its folder
    L.write_json(folder / X.SETTINGS, {"model": "sihrs", "season": "2024-25",
                                       "size": "pilot"})
    refused(folder, W0)
    L.write_json(folder / X.SETTINGS, json.loads(X.settings_text(SMOKE)))
    # a week not frozen, and weeks that are not dates
    _store(folder, "2024-12-14")
    for asof in ("2024-12-14", "../..", "", None):
        refused(folder, asof)
    # a protected tree
    monkeypatch.setenv("FLUBNF_PROTECT_ROOTS", str(folder))
    refused(folder, W0)
    monkeypatch.delenv("FLUBNF_PROTECT_ROOTS")
    # replayed by another process (its pid alive, its heartbeat fresh)
    monkeypatch.setattr(retro, "worker_gone", lambda meta: False)
    for status in retro.ACTIVE_STATUSES:
        retro.write_meta(folder, {**meta, "status": status,
                                  "heartbeat_utc": time.time(),
                                  "pid": os.getpid() + 1})
        refused(folder, W0)
    # this process's own replay drops its weeks as it goes
    retro.write_meta(folder, {**meta, "status": "running",
                              "heartbeat_utc": time.time(),
                              "pid": os.getpid()})
    assert X.drop_samples(folder, W0) > 0


@pytest.mark.skipif(os.name == "nt", reason="links need rights on Windows")
def test_drop_refuses_a_linked_folder_or_week(sandbox_root, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    folder = _experiment()
    real = _store(elsewhere, W0)
    (folder / "weeks").mkdir()
    os.symlink(real, folder / "weeks" / W0)
    target = _tree(elsewhere)
    assert X.drop_samples(folder, W0) == 0
    (folder / "weeks" / W0).unlink()
    (folder / "weeks").rmdir()
    os.symlink(elsewhere / "weeks", folder / "weeks")
    assert X.drop_samples(folder, W0) == 0
    (folder / "weeks").unlink()
    # the folder itself a link to an experiment's
    moved = tmp_path / "moved" / folder.name
    moved.parent.mkdir()
    folder.rename(moved)
    _store(moved, W0)
    os.symlink(moved, folder)
    before = _tree(moved)
    assert X.drop_samples(folder, W0) == 0
    assert _tree(moved) == before and _tree(elsewhere) == target
    # a link inside a week loses only itself
    folder.unlink()
    moved.rename(folder)
    wd = RS._week_dir(folder, W0)
    os.symlink(real / RS.SAMPLES_GZ, wd / "linked.gz")
    assert X.drop_samples(folder, W0) > 0
    assert not os.path.lexists(wd / "linked.gz")
    assert _tree(elsewhere) == target


# ------------------------------------------------- reading a lean week


def test_lean_weeks_read_as_stored(sandbox_root, monkeypatch):
    folder = _experiment()
    wd = _store(folder, W0)
    mq = RS.read_week_quantiles(wd)
    assert RS.FILTER_MEMBER in mq
    X.drop_samples(folder, W0)
    assert RS.week_done(folder, W0) and RS.week_dropped(wd)
    assert not RS.week_done(folder, W1)
    # no mtime test: the sidecar may be older than anything
    os.utime(wd / RS.QUANTILES_NAME, (1.0e9, 1.0e9))
    assert RS.read_week_quantiles(wd) == mq
    # never rebuilt from draws nor rewritten, even a sidecar without the
    # Liu-West filter beside an applied oracle.json
    asked = []

    def no_draws(root, asof):
        asked.append(asof)
        raise AssertionError("a lean week's draws were read")
    monkeypatch.setattr(RS, "read_week_samples", no_draws)
    plain = {m: q for m, q in mq.items() if m != RS.FILTER_MEMBER}
    RS.write_week_quantiles(wd, plain)
    held = _tree(wd)
    assert RS.filter_quantiles(wd)
    assert RS.week_member_quantiles(folder, W0) == plain
    assert asked == [] and _tree(wd) == held
    assert [p.relative_to(folder).as_posix()
            for p in RS.season_week_files(folder)] == [
        f"weeks/{W0}/{RS.QUANTILES_NAME}"]
    assert RS.season_sample_files(folder) == []
    assert retro._weeks_on_disk(folder) == 1
    assert X._newest(folder) == (wd / RS.QUANTILES_NAME).stat().st_mtime
    # a sidecar that cannot be read: the week is not rebuilt either
    _write(wd / RS.QUANTILES_NAME, "{")
    with pytest.raises(FileNotFoundError,
                       match="its forecasting samples were dropped"):
        RS.week_member_quantiles(folder, W0)
    assert asked == []
    # the marker without its sidecar is no stored week
    (wd / RS.QUANTILES_NAME).unlink()
    assert not RS.week_dropped(wd) and not RS.week_done(folder, W0)
    assert RS.read_week_quantiles(wd) is None
    assert RS.season_week_files(folder) == []


# ------------------------------------- the summary after the drop


def _scored(tmp_path, monkeypatch, weeks=SMOKE_WEEKS, locs=LOCS):
    """An experiment of the smoke with the Oracle step, its weeks stored
    heavy, the season's shipped replay beside it and the truth on a
    synthetic hub: (folder, retro root)."""
    from app.tests.test_experiment_summary import _age, _hub, _q, _shipped_root
    _hub(tmp_path, monkeypatch, weeks=list(weeks))
    rr = tmp_path / "retro"
    _shipped_root(rr, pf={w: _q(12.0, list(LOCS)) for w in weeks})
    folder = _experiment(weeks)
    for i, w in enumerate(weeks):
        _store(folder, w, seed=i, locs=locs)
    _age(folder, rr)
    return folder, rr


def _without(summary: dict, *keys) -> dict:
    """A summary but its scoring time and, by key path, what else
    differs."""
    out = json.loads(json.dumps(summary))
    out["scored"].pop("utc")
    for path in keys:
        d = out
        for k in path[:-1]:
            d = d[k]
        d.pop(path[-1])
    return out


def test_score_is_the_same_after_the_drop(sandbox_root, tmp_path,
                                          monkeypatch):
    folder, rr = _scored(tmp_path, monkeypatch)
    heavy = X.score(folder, retro_root=rr, flubnf_build="53f1acf")
    assert heavy["shipped"]["member"] == "pf"
    assert heavy["cells"]["compared"] == 2 * 2 * 4
    for w in SMOKE_WEEKS:
        assert X.drop_samples(folder, w) > 0
    lean = X.score(folder, retro_root=rr)
    assert (_without(lean, ("ran", "disk_bytes"))
            == _without(heavy, ("ran", "disk_bytes")))
    assert lean["ran"]["disk_bytes"] < heavy["ran"]["disk_bytes"] / 2
    assert lean["ran"]["flubnf_build"] == "53f1acf"


def test_stale_status_and_failures_hold_after_the_drop(sandbox_root,
                                                       tmp_path,
                                                       monkeypatch):
    # the second week stored without Vermont, its prepare failure recorded
    folder, rr = _scored(tmp_path, monkeypatch)
    wd = RS._week_dir(folder, W1)
    retro.delete_tree(wd)
    _store(folder, W1, seed=1, locs=("California",))
    _write(wd / PF.PREPARE_FAILURES_NAME,
           json.dumps({"Vermont": "no data this week"}))
    from app.tests.test_experiment_summary import _age
    _age(folder)
    heavy = X.score(folder, retro_root=rr)
    assert heavy["ran"]["failed_fits"] == 2
    assert heavy["failures"] == [
        {"week": W0, "location": "Vermont", "replicate": 0,
         "text": "FAIL: the fit diverged"},
        {"week": W1, "location": "Vermont", "text": "no data this week"},
        {"week": W1, "location": "Vermont", "replicate": 0,
         "text": "FAIL: the fit diverged"}]
    st = X.status(folder)
    assert X.stale(folder) == X.stale(folder, retro_root=rr) == ""
    for w in SMOKE_WEEKS:
        assert X.drop_samples(folder, w) > 0
    assert X.status(folder) == st
    assert (st["weeks_done"], st["complete"]) == (2, True)
    assert X.stale(folder) == X.stale(folder, retro_root=rr) == ""
    lean = X.score(folder, retro_root=rr)
    assert (lean["failures"], lean["ran"]["failed_fits"]) == (
        heavy["failures"], 2)
    # a sidecar gone: the week is not stored, and a rescore says so
    (wd / RS.QUANTILES_NAME).unlink()
    assert X.status(folder)["weeks_done"] == 1
    assert X.score(folder, retro_root=rr)["complete"] is False


# ----------------------------------------------------- a resume


def _lean_replay(monkeypatch, season) -> Path:
    """The smoke replayed with run_week faked, each week stored with real
    samples and its sidecar and made lean after it (after_week), as the
    runner does: its folder."""
    folder = X.root() / X.experiment_id(SMOKE)

    def store(root, asof):
        RS.write_week_samples(root / "weeks" / asof, _record(asof))
    calls = _weeks_run(monkeypatch, store)
    X.replay(SMOKE, retro_root=season,
             after_week=lambda asof: X.drop_samples(folder, asof))
    assert [c["asof"] for c in calls] == list(SMOKE_WEEKS)
    assert all(RS._lean(RS._week_dir(folder, w)) for w in SMOKE_WEEKS)
    return folder


def test_a_resume_skips_lean_weeks_and_keeps_its_refusals(season,
                                                          monkeypatch):
    folder = _lean_replay(monkeypatch, season)
    assert retro.read_meta(folder)["weeks_completed"] == 2
    calls = _weeks_run(monkeypatch)
    seen = []
    X.replay(SMOKE, retro_root=season, after_week=seen.append)
    assert calls == [] and seen == list(SMOKE_WEEKS)
    meta = retro.read_meta(folder)
    assert (meta["weeks_completed"], meta["status"]) == (2, "done")
    assert X.status(folder)["complete"] is True
    # the refusals that count weeks on disk, with only lean weeks there
    fp = meta["settings"]["experiment"]
    with pytest.raises(retro.KnobsMismatch):
        retro.run_season(folder, "2024-25", list(LOCS), replicates=3,
                         settings={"experiment": fp})
    with pytest.raises(retro.LocationsMismatch):
        retro.run_season(folder, "2024-25", ["Vermont"], replicates=1,
                         settings={"experiment": fp})
    with pytest.raises(retro.ResumeMismatch):
        retro.run_season(folder, "2024-25", list(LOCS), replicates=1,
                         settings={"experiment": "0" * 64})
    assert calls == []
    assert retro.read_meta(folder)["weeks_completed"] == 2


def test_a_lean_week_whose_quantiles_vanish_is_fitted_again(season,
                                                            monkeypatch):
    folder = _lean_replay(monkeypatch, season)
    (RS._week_dir(folder, W1) / RS.QUANTILES_NAME).unlink()
    assert not RS.week_done(folder, W1)
    assert X.status(folder)["weeks_done"] == 1
    calls = _weeks_run(monkeypatch)
    X.replay(SMOKE, retro_root=season)
    assert [c["asof"] for c in calls] == [W1]
    assert X.status(folder)["complete"] is True


# --------------------------------------------- weeks that are not dates


def test_weeks_that_are_not_dates_are_ignored(season, truth, monkeypatch):
    folder = _experiment(["../..", "..", W0, "x/../../..", 7])
    _store(folder, W0)
    # a week's draws where "../.." would lead (the experiments folder) and
    # no sidecar beside them: a reader led there would write one
    (X.root() / RS.SAMPLES_JSON).write_text(json.dumps(
        hz.record_to_stored(_record(W0))), encoding="utf-8", newline="\n")
    outside = {k: v for k, v in _tree(X.root()).items()
               if not k.startswith(folder.name)}
    asked = []
    real = RS._week_dir

    def week_dir(root, asof):
        asked.append(asof)
        return real(root, asof)
    monkeypatch.setattr(RS, "_week_dir", week_dir)
    got = X.score(folder, retro_root=season)
    st = X.status(folder)
    p = X.preflight(SMOKE, retro_root=season)
    assert got["ran"]["weeks"] == [W0] and got["complete"] is True
    assert (st["weeks_total"], st["weeks_done"]) == (1, 1)
    assert (p["weeks"], p["weeks_done"]) == ([W0], 1)
    assert {f["week"] for f in got["failures"]} == {W0}
    assert set(asked) <= set(SMOKE_WEEKS) and W0 in asked
    assert {k: v for k, v in _tree(X.root()).items()
            if not k.startswith(folder.name)} == outside
    assert not (X.root() / RS.QUANTILES_NAME).exists()


# ------------------------------------------- the shipped readers, pinned

#: the golden tree's week folders, and a week of the season it lacks
GOLD_WEEKS = ("2024-11-16", "2024-11-23", "2024-11-30", "2024-12-07",
              "2024-12-14", "2024-12-21", "2025-01-04")
GOLD_ABSENT = "2024-12-28"
GOLD_LOCS = ("Vermont", "New York")
#: every file's mtime is set from here, so the sidecar's age is exact
T0 = 1_790_000_000


def _gold_record(asof: str, scale: float) -> dict:
    """A week's record in canonical horizons whose quantiles are exact on
    every platform: each location's draws are one value repeated, so every
    level is that value; the Groundhog's levels are whole numbers."""
    return {"asof": asof,
            "pf": {loc: {**{h: [scale * (i + 1) * (int(h) + 2)] * 20
                            for h in hz.HORIZONS},
                         hz.ORIGIN: [scale * (i + 1)] * 20}
                   for i, loc in enumerate(GOLD_LOCS)},
            "analogue": {loc: {h: {str(L): float(i + j + int(h))
                                   for j, L in enumerate(QL)}
                               for h in hz.HORIZONS}
                         for i, loc in enumerate(GOLD_LOCS)}}


def _gold_sidecar(base: float, members=("pf", "analogue")) -> dict:
    """A planted sidecar, {member: {location: {horizon: {level: value}}}},
    whose values no week's draws give."""
    return {m: {loc: {h: {L: base + 10 * k + i + int(h) for L in QL}
                      for h in hz.HORIZONS}
                for i, loc in enumerate(GOLD_LOCS)}
            for k, m in enumerate(members)}


def _gold_oracle(applied: bool) -> dict:
    """oracle.json: the Liu-West filter's quantiles when the step ran."""
    if not applied:
        return {"applied": False, "why": "the replay asked for the plain "
                "filter (oracle = none)"}
    return {"applied": True, "quantiles": {"levels": list(QL), "null": {
        loc: {h: {"unrounded": [50.0 + i + int(h) + j
                                for j in range(len(QL))]}
              for h in hz.HORIZONS}
        for i, loc in enumerate(GOLD_LOCS)}}}


def _put(path: Path, text: str, mtime: int) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")
    os.utime(path, (mtime, mtime))


def _put_samples(wd: Path, rec: dict, mtime: int, plain: bool) -> None:
    """A samples file in the stored convention, plain or gzip."""
    text = json.dumps(hz.record_to_stored(rec))
    if plain:
        _put(wd / RS.SAMPLES_JSON, text, mtime)
        return
    with gzip.open(wd / RS.SAMPLES_GZ, "wt", encoding="utf-8") as f:
        f.write(text)
    os.utime(wd / RS.SAMPLES_GZ, (mtime, mtime))


def _put_sidecar(wd: Path, mq: dict, mtime: int) -> None:
    RS.write_week_quantiles(wd, mq)
    os.utime(wd / RS.QUANTILES_NAME, (mtime, mtime))


def _gold_tree(root: Path) -> Path:
    """The golden's tree: the shapes a shipped root holds, none lean."""
    weeks = Path(root) / "weeks"
    w = [weeks / a for a in GOLD_WEEKS]
    for wd in w:
        wd.mkdir(parents=True)
    _put(weeks / ".DS_Store", "finder\n", T0)
    # a gzip week and its current sidecar
    _put_samples(w[0], _gold_record(GOLD_WEEKS[0], 1.0), T0, plain=False)
    _put_sidecar(w[0], _gold_sidecar(100.0), T0 + 10)
    # a plain week, its sidecar current, the Oracle step not applied
    _put_samples(w[1], _gold_record(GOLD_WEEKS[1], 2.0), T0, plain=True)
    _put_sidecar(w[1], _gold_sidecar(200.0), T0 + 10)
    _put(w[1] / RS.ORACLE_NAME, json.dumps(_gold_oracle(False)), T0)
    # a sidecar without the Liu-West filter beside an applied oracle.json
    _put(w[2] / RS.ORACLE_NAME, json.dumps(_gold_oracle(True)), T0)
    _put_samples(w[2], _gold_record(GOLD_WEEKS[2], 3.0), T0, plain=False)
    _put_sidecar(w[2], _gold_sidecar(300.0), T0 + 10)
    # a sidecar older than its samples
    _put_samples(w[3], _gold_record(GOLD_WEEKS[3], 4.0), T0, plain=True)
    _put_sidecar(w[3], _gold_sidecar(400.0), T0 - 10)
    # an incomplete week: a fit marked, its tree, and a sidecar left over
    retro.mark_cell_done(w[4], "Vermont_r0", "ok")
    (w[4] / "Vermont_r0").mkdir()
    _put(w[4] / "Vermont_r0" / "pf.conf", "fit_type = pf\n", T0)
    _put(w[4] / "prep.json", "{}", T0)
    _put_sidecar(w[4], _gold_sidecar(500.0), T0 + 10)
    # an interrupted migration: both forms, no sidecar (the plain wins)
    _put_samples(w[5], _gold_record(GOLD_WEEKS[5], 6.0), T0, plain=True)
    _put_samples(w[5], _gold_record(GOLD_WEEKS[5], 7.0), T0, plain=False)
    # a sidecar exactly as old as its samples (a coarse clock): current
    _put_samples(w[6], _gold_record(GOLD_WEEKS[6], 8.0), T0, plain=False)
    _put_sidecar(w[6], _gold_sidecar(800.0), T0)
    return Path(root)


def _levels(by_loc: dict | None):
    """{location: {horizon: {level: value}}} with the levels as text."""
    if by_loc is None:
        return None
    return {loc: {h: {repr(float(L)): v for L, v in q.items()}
                  for h, q in by_h.items()}
            for loc, by_h in by_loc.items()}


def _members(mq: dict | None):
    return None if mq is None else {m: _levels(x) for m, x in mq.items()}


def _gold_reads(root: Path) -> dict:
    """What the shipped readers give for the golden's tree: the pure reads
    first, then week_member_quantiles (which may write a sidecar) and the
    sidecar each week holds after it."""
    root = Path(root)
    out = {"season_sample_files": [p.relative_to(root).as_posix()
                                   for p in RS.season_sample_files(root)],
           "weeks_on_disk": retro._weeks_on_disk(root), "weeks": {}}
    asofs = GOLD_WEEKS + (GOLD_ABSENT,)
    for a in asofs:
        wd = RS._week_dir(root, a)
        sp = RS.samples_file(wd)
        out["weeks"][a] = {
            "samples_file": None if sp is None else sp.name,
            "week_samples_path": RS.week_samples_path(root, a) == sp,
            "week_done": RS.week_done(root, a),
            "read_week_quantiles": _members(RS.read_week_quantiles(wd)),
            "filter_quantiles": _levels(RS.filter_quantiles(wd))}
    for a in asofs:
        try:
            got = _members(RS.week_member_quantiles(root, a))
        except Exception as e:
            got = type(e).__name__
        out["weeks"][a]["week_member_quantiles"] = got
        out["weeks"][a]["sidecar_after"] = _members(
            RS.read_week_quantiles(RS._week_dir(root, a)))
    return out


def test_shipped_readers_are_unchanged_without_a_marker(tmp_path):
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))["reads"]
    root = _gold_tree(tmp_path / "retro" / "2024-25")
    assert [p.relative_to(root).as_posix()
            for p in RS.season_week_files(root)] == want["season_sample_files"]
    assert _gold_reads(root) == want
    # the golden is not vacuous: each branch of the readers is taken
    weeks = want["weeks"]
    assert [weeks[a]["week_done"] for a in GOLD_WEEKS + (GOLD_ABSENT,)] == [
        True, True, True, True, False, True, True, False]
    assert weeks[GOLD_WEEKS[5]]["samples_file"] == RS.SAMPLES_JSON
    assert weeks[GOLD_WEEKS[6]]["read_week_quantiles"] == _members(
        _gold_sidecar(800.0))
    assert weeks[GOLD_WEEKS[3]]["read_week_quantiles"] is None
    assert weeks[GOLD_WEEKS[4]]["read_week_quantiles"] is None
    assert weeks[GOLD_WEEKS[4]]["week_member_quantiles"] == "FileNotFoundError"
    assert weeks[GOLD_WEEKS[0]]["week_member_quantiles"] == weeks[
        GOLD_WEEKS[0]]["read_week_quantiles"]
    rebuilt = weeks[GOLD_WEEKS[2]]["week_member_quantiles"]
    assert set(rebuilt) == {"pf", "analogue", RS.FILTER_MEMBER}
    assert rebuilt != weeks[GOLD_WEEKS[2]]["read_week_quantiles"]
    assert rebuilt == weeks[GOLD_WEEKS[2]]["sidecar_after"]


# ------------------------------------------------------------- regenerate


def snapshot(tmp: Path) -> dict:
    """The golden's object: the tree built afresh and read."""
    return {"_about": ("what the shipped readers of app/core/retro_store.py "
                       "read from test_lean_storage.py's tree with no "
                       "marker; captured at origin/dev 24ac926, before "
                       "lean weeks. Regenerate only for a deliberate "
                       "change: python app/tests/test_lean_storage.py "
                       "--write-golden"),
            "reads": _gold_reads(_gold_tree(tmp / "retro" / "2024-25"))}


if __name__ == "__main__":
    if sys.argv[1:] != ["--write-golden"]:
        sys.exit(__doc__)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        obj = snapshot(Path(d))
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n",
                      encoding="utf-8", newline="\n")
    print(f"wrote {GOLDEN.relative_to(REPO)}")
