"""PRODUCTION: the season replay engine (server Retrospective tab, `flubnf
retro`).

Season-as-competition retrospective: run every vintage week like a real
submission day, score against settled truth, aggregate.

Engineering rules:
  * RESUMABLE: each week is a checkpoint; completed weeks are never redone.
  * one ledger run per season; per-week artifacts under weeks/<date>/.
  * members: pf (seeded, replicated) + analogue, each scored on its own. The
    analogue runs as the Groundhog by default (engines/analogue.SHIPPED_AUX in
    every week's spec unless `week_extra` overrides; named in run_meta.json).
    Both are stored through the console's output floor (app/core/floor.py).
    Older scores.json files may carry retired "ensemble" rows.
  * SCORED by FluSight's cell rule (scoring.cell_scored), with log-scale WIS
    and 50/80/95 coverage beside WIS (score_season; SCORES_V).
  * PF cells sharded across N runner subprocesses (entry-point files, never
    stdin: the macOS spawn rule).
  * CONTROLLABLE: STOP and PAUSE files in the season root are polled between
    individual fits; only fits in flight finish, and every finished fit is
    checkpointed in cells_done/, so a stopped week refits only what never ran.
  * TIMED: run_meta.json accumulates wall time across resumes.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core import data as _data                    # noqa: E402
from app.core.engines import analogue as an_engine    # noqa: E402
from app.core.engines import pf as pf_engine          # noqa: E402
from app.core import horizons as hz
from app.core import missing as MS                   # noqa: E402
from app.core import oracle as oracle_mod             # noqa: E402
from app.core import proc as proc_mod                 # noqa: E402
from app.core.floor import (floor_quantiles, floor_samples,  # noqa: E402
                            recent_observed)
from app.core.runs import RunSpec                     # noqa: E402

# Sections (in order): season calendar (SEASON_BOUNDS, available_seasons,
# season_vintages) | run record and control flags (read_meta, timing,
# request_stop, hold_while_paused, _record_*) | fit-level execution
# (cells_done, _launch_runners, _run_round) | one week (run_week) | the
# season loop (run_season) | scoring (SCORES_V, score_season) | the national
# aggregate (national_aggregate) | finalize (finalize_season) | headline
# summary (run_summary, state_metrics).
# Moved out, re-exported below: the samples store (retro_store), settings
# and resume rules (retro_settings), archived runs (retro_archive).

# the samples store moved to app/core/retro_store.py; re-exported so
# `retro.X` keeps working
from app.core.retro_store import (  # noqa: F401
    FILTER_MEMBER, QUANTILES_NAME, filter_quantiles, SAMPLES_GZ, SAMPLES_JSON, _week_dir, compress_samples_file,
    member_quantiles, read_samples, read_week_quantiles, read_week_samples,
    samples_file, season_sample_files, week_done, week_member_quantiles,
    week_samples_path, write_week_quantiles, write_week_samples)
# settings, presets and the resume rules moved to app/core/retro_settings.py
from app.core.retro_settings import (  # noqa: F401
    ENGINE_LABELS, ENGINES, FLOOR_APPLIED, FLOOR_FROM_RESUME,
    FLOOR_NOT_RECORDED, SCOPE_LABELS, EngineBuildChanged,
    EngineBuildMismatch, KnobsMismatch, LocationsMismatch, ResumeMismatch,
    _build_label, engine_build_change, engine_label, location_scope,
    location_scope_change, pf_ran, resume_form_fields, season_knobs,
    settings_summary)
# archived runs moved to app/core/retro_archive.py
from app.core.retro_archive import (  # noqa: F401
    ARCHIVE_SEP, _STAMP_RE, _SUMMARY_CACHE, _SUMMARY_CACHE_MAX, archive_dir,
    archive_run, archive_stamp_of, delete_tree, dir_size, human_bytes,
    list_archive_dirs, stamp_human, utc_human, utc_stamp, valid_stamp)

SEASON_BOUNDS = {"2023-24": ("2023-08-01", "2024-06-15"),
                 "2024-25": ("2024-08-01", "2025-06-15"),
                 "2025-26": ("2025-08-01", "2026-06-15")}


def season_bounds(season: str) -> tuple:
    """(start, end) for a season string 'YYYY-YY'. Known seasons keep their
    recorded bounds; any other well-formed season gets the same formulaic
    August-through-mid-June window, so a new season needs no code change."""
    if season in SEASON_BOUNDS:
        return SEASON_BOUNDS[season]
    y = int(season[:4])
    return (f"{y}-08-01", f"{y + 1}-06-15")


def available_seasons() -> list:
    """Seasons derived from the truth vintages (app.core.data.vintages: the
    hub archive and the shipped snapshots): a vintage dated inside a season's
    window makes that season available, so a future season appears
    automatically once its vintages exist. Falls back to the hardcoded season
    list if derivation fails or there are no vintages."""
    try:
        seasons = set()
        for v in _data.vintages():
            y, m = int(v[:4]), int(v[5:7])
            start = y if m >= 8 else y - 1
            s = f"{start}-{(start + 1) % 100:02d}"
            lo, hi = season_bounds(s)
            if lo <= v <= hi:            # off-window vintages (July) make no season
                seasons.add(s)
        return sorted(seasons) or sorted(SEASON_BOUNDS)
    except Exception:
        return sorted(SEASON_BOUNDS)


def season_vintages(season: str) -> list:
    """The replay's weeks: every truth vintage (hub archive and shipped
    snapshots, app.core.data.vintages) dated inside the season's window."""
    lo, hi = season_bounds(season)
    return [v for v in _data.vintages() if lo <= v <= hi]


def season_no_data_weeks(season: str) -> dict:
    """{as_of: entry} for the season's weeks with no published data and no
    FluSight round (data/vintages/manifest.json): nothing to replay or
    score, but a timeline should say so rather than skip the date."""
    lo, hi = season_bounds(season)
    return {w: e for w, e in _data.no_data_weeks().items() if lo <= w <= hi}


# --------------------------------------------------------------------------
# run record: timing, heartbeat, and the STOP / PAUSE control flags
# --------------------------------------------------------------------------

META_NAME = "run_meta.json"
STOP_NAME = "STOP"
PAUSE_NAME = "PAUSE"

#: a live-claiming status is disbelieved past this heartbeat age (the worker
#: beats every HEARTBEAT_EVERY_S; only a dead process goes this quiet)
HEARTBEAT_STALE_S = 240.0
HEARTBEAT_EVERY_S = 20.0
PAUSE_POLL_S = 2.0

#: statuses that assert a live worker, and are therefore heartbeat-checked
ACTIVE_STATUSES = ("running", "paused", "stopping")

# every read-modify-write of run_meta.json goes through one lock: the
# heartbeat thread and the season worker both fold time into the same file
_META_LOCK = threading.RLock()


class SeasonStopped(Exception):
    """Raised when a stop was requested. Completed weeks are kept, and a
    week interrupted mid-way keeps every finished fit's checkpoint, so a
    later replay resumes by refitting only the cells that never ran."""


def _now() -> float:
    return time.time()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def meta_path(root: Path) -> Path:
    return Path(root) / META_NAME


def stop_path(root: Path) -> Path:
    return Path(root) / STOP_NAME


def pause_path(root: Path) -> Path:
    return Path(root) / PAUSE_NAME


def read_meta(root: Path) -> dict:
    """The season's run record, or {} when absent or unreadable (never raises)."""
    try:
        d = json.loads(meta_path(root).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def write_meta(root: Path, meta: dict) -> None:
    """Atomic: write beside, then replace."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    tmp = meta_path(root).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")
    os.replace(tmp, meta_path(root))


def request_stop(root: Path) -> bool:
    """Ask the worker to finish only the fits in flight and exit; clears
    PAUSE so a paused worker stops. Never creates the season tree. Returns
    whether the flag was written."""
    if not Path(root).is_dir():
        return False
    stop_path(root).touch()
    clear_pause(root)
    return True


def request_pause(root: Path) -> bool:
    if not Path(root).is_dir():
        return False
    pause_path(root).touch()
    return True


def clear_pause(root: Path) -> None:
    pause_path(root).unlink(missing_ok=True)


def clear_flags(root: Path) -> None:
    stop_path(root).unlink(missing_ok=True)
    pause_path(root).unlink(missing_ok=True)


def is_stale(meta: dict, now: float | None = None,
             limit: float = HEARTBEAT_STALE_S) -> bool:
    """True when the record claims a live worker but the heartbeat has gone
    quiet -- the app died mid-replay, and the season must not read as running
    forever."""
    hb = (meta or {}).get("heartbeat_utc")
    if hb is None:
        return True
    try:
        return ((now if now is not None else _now()) - float(hb)) > limit
    except (TypeError, ValueError):
        return True


def effective_status(meta: dict, now: float | None = None,
                     limit: float = HEARTBEAT_STALE_S) -> str:
    """The recorded status, corrected for a dead worker: a stale heartbeat
    turns any live-sounding status into 'interrupted'."""
    st = str((meta or {}).get("status") or "")
    if st in ACTIVE_STATUSES and is_stale(meta, now, limit):
        return "interrupted"
    return st


def elapsed_now(meta: dict, now: float | None = None) -> float:
    """Accumulated ACTIVE wall time. Time held at a pause does not count, and
    a resumed run carries its earlier segments forward."""
    total = float((meta or {}).get("elapsed_s") or 0.0)
    seg = (meta or {}).get("segment_start_utc")
    if seg and str((meta or {}).get("status") or "") in ("running", "stopping"):
        try:
            total += max(0.0, (now if now is not None else _now()) - float(seg))
        except (TypeError, ValueError):
            pass
    return total


def timing(meta: dict, now: float | None = None) -> dict:
    """Timing facts for the UI and report headers: wall time, weeks done,
    mean and slowest week (skipped weeks are never timed)."""
    ws = {k: float(v) for k, v in ((meta or {}).get("week_seconds") or {}).items()
          if isinstance(v, (int, float))}
    slowest = max(ws.items(), key=lambda kv: kv[1]) if ws else None
    return {"elapsed_s": elapsed_now(meta, now),
            "weeks_completed": int((meta or {}).get("weeks_completed") or 0),
            "total_weeks": int((meta or {}).get("total_weeks") or 0),
            "weeks_measured": len(ws),
            "mean_s": (sum(ws.values()) / len(ws)) if ws else None,
            "slowest_week": slowest[0] if slowest else None,
            "slowest_s": slowest[1] if slowest else None,
            "started_utc": (meta or {}).get("started_utc"),
            "finished_utc": (meta or {}).get("finished_utc")}


def _weeks_on_disk(root: Path) -> int:
    return len(season_sample_files(root))


def _fold(meta: dict, now: float) -> dict:
    """Move the open segment's seconds into elapsed_s and restart it (at
    week boundaries and heartbeats, so a crash loses at most one interval)."""
    seg = meta.get("segment_start_utc")
    if seg:
        try:
            meta["elapsed_s"] = (float(meta.get("elapsed_s") or 0.0)
                                 + max(0.0, now - float(seg)))
            meta["segment_start_utc"] = now
        except (TypeError, ValueError):
            meta["segment_start_utc"] = now
    return meta


class _Heartbeat(threading.Thread):
    """Keeps run_meta.json's heartbeat fresh while a (long) week is fitting."""

    def __init__(self, root: Path, every: float = HEARTBEAT_EVERY_S):
        super().__init__(daemon=True)
        self.root, self.every = Path(root), every
        self._done = threading.Event()

    def beat(self) -> None:
        with _META_LOCK:
            m = read_meta(self.root)
            if not m:
                return
            now = _now()
            _fold(m, now)
            m["heartbeat_utc"] = now
            write_meta(self.root, m)

    def run(self) -> None:
        while not self._done.wait(self.every):
            try:
                self.beat()
            except Exception:
                pass                      # a beat may fail; the replay may not

    def stop(self) -> None:
        self._done.set()




def _start_record(root: Path, season: str, total_weeks: int,
                  settings: dict | None = None) -> dict:
    """Open (or reopen) the season's run record; a resume keeps started_utc
    and elapsed_s. Settings are recorded at the start (a resume records
    those it resumes with), so even an unfinished run says what produced it."""
    with _META_LOCK:
        m = read_meta(root)
        now = _now()
        m["season"] = season
        m["status"] = "running"
        m.pop("stop_reason", None)
        m["total_weeks"] = int(total_weeks)
        if settings:
            m["settings"] = dict(settings)
        m["started_utc"] = m.get("started_utc") or now
        m["segment_start_utc"] = now
        m["finished_utc"] = None
        m["heartbeat_utc"] = now
        m["elapsed_s"] = float(m.get("elapsed_s") or 0.0)
        m["week_seconds"] = dict(m.get("week_seconds") or {})
        m["weeks_completed"] = _weeks_on_disk(root)
        write_meta(root, m)
        return m


def _record_setting(root: Path, key: str, value) -> None:
    """Fold one setting into the season's run record, under the lock."""
    with _META_LOCK:
        m = read_meta(root)
        st = dict(m.get("settings") or {})
        st[key] = value
        m["settings"] = st
        write_meta(root, m)


def _record_week(root: Path, asof: str, seconds: float) -> None:
    with _META_LOCK:
        m = read_meta(root)
        now = _now()
        _fold(m, now)
        # one entry for a week finished across stops: fold in banked partials
        wp = dict(m.get("week_partial_s") or {})
        try:
            seconds = float(seconds) + float(wp.pop(asof, 0.0) or 0.0)
        except (TypeError, ValueError):
            pass
        m["week_partial_s"] = wp
        ws = dict(m.get("week_seconds") or {})
        ws[asof] = round(float(seconds), 3)
        m["week_seconds"] = ws
        m["weeks_completed"] = _weeks_on_disk(root)
        m["heartbeat_utc"] = now
        write_meta(root, m)


def _record_stop_reason(root: Path, why: str) -> None:
    """Why a season stopped on its own (stop_reason in the run record);
    a later start or resume clears it."""
    with _META_LOCK:
        m = read_meta(root)
        m["stop_reason"] = str(why)
        write_meta(root, m)


def _record_week_build(root: Path, asof: str, build: dict) -> None:
    """Record the engine build that fitted week `asof` (week_engine_builds;
    a filter week only)."""
    with _META_LOCK:
        m = read_meta(root)
        wb = dict(m.get("week_engine_builds") or {})
        wb[asof] = dict(build)
        m["week_engine_builds"] = wb
        write_meta(root, m)


def _record_flags(root: Path, asof: str, flags: dict) -> None:
    """Fold one week's flagged newest weeks ({member: [{location, week,
    value, rule}]}) into the run record under data_flags[asof]. Called
    only when a missing-data rule is on, so a shipped record has no key."""
    with _META_LOCK:
        m = read_meta(root)
        df = dict(m.get("data_flags") or {})
        df[asof] = flags
        m["data_flags"] = df
        write_meta(root, m)


def _record_partial(root: Path, asof: str, seconds: float) -> None:
    """Bank a stopped week's active seconds (no week_seconds entry: an
    unfinished week would drag the mean down); _record_week folds them in."""
    with _META_LOCK:
        m = read_meta(root)
        now = _now()
        _fold(m, now)
        wp = dict(m.get("week_partial_s") or {})
        try:
            prior = float(wp.get(asof, 0.0) or 0.0)
        except (TypeError, ValueError):
            prior = 0.0
        wp[asof] = round(prior + max(0.0, float(seconds)), 3)
        m["week_partial_s"] = wp
        m["heartbeat_utc"] = now
        write_meta(root, m)


def _clear_partial(root: Path, asof: str) -> None:
    """Drop a week's banked partial seconds when its tree is rebuilt from
    scratch (they belonged to fits that no longer exist)."""
    with _META_LOCK:
        m = read_meta(root)
        wp = dict(m.get("week_partial_s") or {})
        if asof in wp:
            del wp[asof]
            m["week_partial_s"] = wp
            write_meta(root, m)


def _set_paused(root: Path, paused: bool) -> None:
    with _META_LOCK:
        m = read_meta(root)
        now = _now()
        if paused:
            _fold(m, now)
            m["segment_start_utc"] = None      # a held clock does not tick
            m["status"] = "paused"
        else:
            m["segment_start_utc"] = now
            m["status"] = "running"
        m["heartbeat_utc"] = now
        write_meta(root, m)


def _finish_record(root: Path, status: str) -> None:
    with _META_LOCK:
        m = read_meta(root)
        now = _now()
        _fold(m, now)
        m["segment_start_utc"] = None
        m["status"] = status
        m["finished_utc"] = now
        m["heartbeat_utc"] = now
        m["weeks_completed"] = _weeks_on_disk(root)
        write_meta(root, m)


def _check_stop(root: Path) -> None:
    if stop_path(root).exists():
        raise SeasonStopped("stop requested")


def hold_while_paused(root: Path, poll_s: float = PAUSE_POLL_S) -> bool:
    """Block while PAUSE stands (process and sleep guard stay held).
    Returns True if it actually held."""
    if not pause_path(root).exists():
        return False
    _set_paused(root, True)
    while pause_path(root).exists():
        if stop_path(root).exists():
            raise SeasonStopped("stop requested while paused")
        _sleep(poll_s)
    # request_stop clears PAUSE to wake us: re-check STOP before resuming
    if stop_path(root).exists():
        raise SeasonStopped("stop requested while paused")
    _set_paused(root, False)
    return True


# --------------------------------------------------------------------------
# fit-level execution of one week
#
# The unit of control is the fit: each finished (location, replicate) cell
# leaves an atomic marker in <week>/cells_done/; flags are polled while the
# runners work, and a Stop/Pause halts dispatch (runners check HALT between
# cells), so a press lands in under a minute. The markers are also the
# mid-week resume (prepared cells reused when the manifest matches). The
# samples file still appears only when every cell is done.
# --------------------------------------------------------------------------

CELL_DONE_DIRNAME = "cells_done"
HALT_NAME = "HALT"
PREP_NAME = "prep.json"
WEEK_TIMEOUT_S = 7200.0
FIT_POLL_S = 1.0

#: the week runner (an entry-point FILE in the engine venv, never stdin): runs
#: its shard sequentially, marks each cell atomically, exits between cells on HALT
_RETRO_RUNNER = '''"""Auto-generated retro PF runner: runs its shard's cells
sequentially, marks each finished cell, halts between cells on HALT."""
import json, os, shutil, sys
sys.path.insert(0, {pybnf_path!r})
from pathlib import Path
cells = json.load(open({cells_json!r}))
halt = Path({halt_path!r})
done = Path({done_dir!r})
for c in cells:
    if halt.exists():
        break                     # drain: only the fit in flight was finished
    d = Path(c["dir"])
    shutil.rmtree(d / "out", ignore_errors=True)
    (d / "out" / "Results").mkdir(parents=True)
    cwd = os.getcwd(); os.chdir(d)
    try:
        from pybnf.parse import load_config
        from pybnf.pf import ParticleFilter
        ParticleFilter(load_config(str(d / "pf.conf"))).run(None)
        status = "ok"
    except Exception as e:
        status = ("FAIL: " + str(e))[:200]
    finally:
        os.chdir(cwd)
    tmp = done / (c["key"] + ".tmp")
    tmp.write_text(json.dumps({{"key": c["key"], "status": status}}))
    os.replace(tmp, done / (c["key"] + ".json"))
'''


def _cell_done_dir(wd: Path) -> Path:
    return Path(wd) / CELL_DONE_DIRNAME


def cells_done(wd: Path) -> set:
    """Keys of the week's ATTEMPTED fits (atomic markers), failures
    included so the fit loop terminates; cells_failed() reports those."""
    d = _cell_done_dir(wd)
    return {p.stem for p in d.glob("*.json")} if d.is_dir() else set()


def cells_failed(wd: Path) -> dict:
    """Marker keys whose recorded status is a failure -> the status text."""
    d = _cell_done_dir(wd)
    out = {}
    if d.is_dir():
        for p in d.glob("*.json"):
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                out[p.stem] = "unreadable marker"
                continue
            s = str(m.get("status", ""))
            if s != "ok":
                out[p.stem] = s[:200]
    return out


def mark_cell_done(wd: Path, key: str, status: str = "ok") -> None:
    """Record one finished fit the way the runner does: atomically, keyed by
    the cell tag. Kept here so tests and tools mark cells identically."""
    d = _cell_done_dir(wd)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{key}.tmp"
    tmp.write_text(json.dumps({"key": key, "status": status}), encoding="utf-8")
    os.replace(tmp, d / f"{key}.json")


def _prepare_week(root: Path, asof: str, spec, manifest: dict) -> list:
    """The week's prepared cells, reusing a stopped segment's preparation
    (and its fit markers) when the manifest matches exactly; anything else
    rebuilds the week from scratch and drops its banked partial seconds."""
    wd = _week_dir(root, asof)
    cj, mf = wd / "cells.json", wd / PREP_NAME
    if cj.is_file() and mf.is_file():
        try:
            if json.loads(mf.read_text(encoding="utf-8")) == manifest:
                return json.loads(cj.read_text(encoding="utf-8"))
        except Exception:
            pass
    if wd.exists():
        shutil.rmtree(wd)              # half-prepared or foreign: start clean
    _clear_partial(root, asof)
    wd.mkdir(parents=True)
    cells = pf_engine.prepare(spec, wd)
    _cell_done_dir(wd).mkdir(exist_ok=True)
    mf.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return cells


def _launch_runners(wd: Path, shards: list, halt: Path) -> list:
    """One reduced-priority runner subprocess per shard (app/core/proc.py).
    Split out so tests can fake fits; returns objects with poll() and kill()."""
    procs = []
    done = _cell_done_dir(wd)
    done.mkdir(parents=True, exist_ok=True)   # the runners write into it
    for i, shard in enumerate(shards):
        sj = wd / f"cells_{i}.json"
        sj.write_text(json.dumps(shard), encoding="utf-8")
        runner = wd / f"runner_{i}.py"
        runner.write_text(_RETRO_RUNNER.format(
            pybnf_path=str(pf_engine.PYBNF_PF), cells_json=str(sj),
            halt_path=str(halt), done_dir=str(done)), encoding="utf-8")
        # own session/process group, as the forecast path does: this daemon
        # thread can die without a finally, and the recorded group is what the
        # relaunch sweeps (flubnf/cli.py)
        procs.append(subprocess.Popen(proc_mod.low_priority_cmd(
                     [str(pf_engine.PY310), str(runner)]),
                     stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL,
                     **pf_engine.runner_popen_kwargs(
                         proc_mod.low_priority_popen_kwargs())))
    pf_engine.record_runner_pids(procs)
    return procs


def _run_round(root: Path, wd: Path, pending: list, width: int) -> None:
    """Dispatch the pending cells across runners and wait for them to drain.

    STOP/PAUSE are polled every FIT_POLL_S; the first sighting touches HALT
    and the runners drain. The caller decides what the flag means; this only
    guarantees the drain and that every finished fit left its marker."""
    wd = Path(wd)
    halt = wd / HALT_NAME
    halt.unlink(missing_ok=True)          # stale from an earlier segment
    before = len(cells_done(wd))
    # the same partition as the console forecast (pf.shard_cells)
    shards = pf_engine.shard_cells(pending, width)
    procs = _launch_runners(wd, shards, halt)
    flagged = False
    # deadline = max(2 h floor, pf_engine.budget_seconds(shards)), as the forecast path
    deadline = time.time() + max(WEEK_TIMEOUT_S,
                                 pf_engine.budget_seconds(shards))
    try:
        while any(p.poll() is None for p in procs):
            if not flagged and (stop_path(root).exists()
                                or pause_path(root).exists()):
                halt.touch()          # dispatch no further fits; drain
                flagged = True
            if time.time() > deadline:
                raise RuntimeError("PF runners timed out")
            _sleep(FIT_POLL_S)
    except BaseException:
        for p in procs:               # never leave engine processes orphaned
            try:
                if p.poll() is None:
                    p.kill()
            except Exception:
                pass
        raise
    finally:
        # drained or killed: drop these pids from the takeover registry
        pf_engine.unrecord_runner_pids(procs)
    if not flagged and len(cells_done(wd)) <= before:
        # no fit finished and no flag: re-dispatching would spin forever
        raise RuntimeError("PF runners exited without completing any fit")


def _floor_recent(spec, locations: list, drop_same_day: bool) -> dict:
    """The observations the output floor's adaptive rate reads, per location,
    from the week's own vintage (floor.recent_observed, as the console
    builds them); {} when the file cannot be read (the floor then keeps its
    default rate everywhere)."""
    from app.core import data as _data
    try:
        path, _kind = _data.spec_source(spec)
        return recent_observed(path, locations, spec.forecast_date,
                               drop_same_day=drop_same_day)
    except Exception:
        return {}


def run_week(root: Path, season: str, asof: str, locations: list,
             replicates: int = 3, particles: int = 10_000,
             width: int = pf_engine.DEFAULT_SHARD_WIDTH,
             drop_same_day: bool = False,
             extra: dict | None = None, engine: str = "pf") -> dict:
    """One submission day: PF (sharded) + analogue; store samples+quantiles.

    Both members are stored through the console's output floor
    (app/core/floor.py, the default rate; the pf after the Oracle step,
    with the week's recent observations for the adaptive rate), so a
    replay scores what a submission would carry.

    `extra` is the spec's research dictionary (seed_anchor,
    continue_states, save_states; see pf_engine.continuation_for), recorded
    in the week's manifest so a resumed week is rebuilt if it changes.

    `engine` "analogue" stores the analogue alone (no pf block, no cells, no
    engine venv).

    STOP/PAUSE are honoured between fits (a stop raises SeasonStopped
    without storing; a pause holds here); a later run refits only cells
    with no marker. The samples file appears only when every cell is done."""
    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {ENGINES}, got {engine!r}")
    # resolved: subprocesses with their own cwd read the paths written below
    root = Path(root).resolve()
    wd = _week_dir(root, asof)
    if week_done(root, asof):
        return read_week_samples(root, asof)
    # drop_same_day defaults OFF (the seal was fitted with the same-day week).
    # extra may override the model's season start (only its first observed
    # week and clock move; the vintages stay the season's) and the jitter.
    _x = extra or {}
    season_start = str(season_bounds(season)[0]
                       if _x.get("season_start") is None else _x["season_start"])
    jitter = float(RunSpec.jitter if _x.get("jitter") is None else _x["jitter"])
    spec = RunSpec(engine="retro", forecast_date=asof, locations=locations,
                   season_start=season_start, jitter=jitter,
                   replicates=replicates, particles=particles,
                   drop_same_day=drop_same_day, extra=dict(extra or {}))
    manifest = {"locations": [str(l) for l in locations],
                "replicates": int(replicates), "particles": int(particles),
                "season_start": spec.season_start,
                "drop_same_day": bool(drop_same_day)}
    if extra:
        # absent when empty (old weeks match); post-fit knobs stay out of
        # the fit record (knobs.fit_extra), so they never force a refit
        from app.core import knobs as _knobs
        manifest["extra"] = _knobs.fit_extra(extra)
    _check_stop(root)         # a standing flag must not even prepare a week
    hold_while_paused(root)
    # the missing-data rules (app/core/missing.py): each week's flagged
    # newest weeks go into the run record, only when a rule is on
    # ...and the Groundhog's zero-anchor location-weeks, when a rule is set
    rules = bool(MS.rules_of(extra) or MS.zero_anchor_of(extra))
    gh_flags: list = []
    an_kw = {"flags": gh_flags} if rules else {}
    if engine == "analogue":
        # the analogue alone; the manifest still records what produced the week
        manifest["engine"] = "analogue"
        wd.mkdir(parents=True, exist_ok=True)
        (wd / "manifest.json").write_text(json.dumps(manifest, indent=1),
                                          encoding="utf-8")
        an_q = {loc: floor_quantiles(q)
                for loc, q in an_engine.run(spec, **an_kw).items()}
        out = {"asof": asof,
               "analogue": {loc: {h: {str(k): v for k, v in q.items()}
                                  for h, q in qs.items()}
                            for loc, qs in an_q.items()}}
        write_week_samples(wd, out)
        if rules:
            _record_flags(root, asof, {"analogue": gh_flags})
        return out
    cells = _prepare_week(root, asof, spec, manifest)
    # a new call retries failed fits (their markers only let the old loop drain)
    for key in cells_failed(wd):
        (_cell_done_dir(wd) / f"{key}.json").unlink(missing_ok=True)
    while True:
        done_keys = cells_done(wd)
        pending = [c for c in cells if c["key"] not in done_keys]
        if not pending:
            break             # every fit is in; assembling costs nothing now
        _check_stop(root)     # a drained round's flag lands here, between fits
        hold_while_paused(root)
        _run_round(root, wd, pending, width)
    # prepare-stage failures have no marker but count like failed fits
    failed = {**pf_engine.read_prepare_failures(wd), **cells_failed(wd)}
    pf_samples = pf_engine.collect(wd)
    if not pf_samples:
        # nothing to store = a broken engine: refuse rather than store an empty pf
        if failed:
            first = next(iter(failed.values()))
            raise RuntimeError(f"all {len(failed)} PF fits failed "
                               f"(first: {first}); the week is not stored")
        raise RuntimeError("every fitted cell's trajectory was unreadable "
                           "at collect; the week is not stored")
    if failed:
        (Path(root) / "failures.log").open("a", encoding="utf-8").write(
            f"{asof}: {len(failed)} PF cell(s) failed and are absent from "
            f"the stored week: {sorted(failed)[:6]}\n")
    # the Oracle step before storage; the member is stored under pf (the
    # filter's quantiles live in oracle.json). oracle = none stores the plain
    # filter and oracle.json says so.
    if oracle_mod.wanted(extra):
        member, _prov = oracle_mod.apply_week(
            pf_samples, asof, wd, extra=extra,
            weeks_to_drop=int(spec.weeks_to_drop or 0),
            drop_same_day=bool(drop_same_day))
    else:
        oracle_mod.write_not_applied(
            wd, asof, "the replay asked for the plain filter (oracle = none)")
        member = pf_samples
    # the output floor after the Oracle step, as the console applies it
    # (app/core/floor.py, the default rate): the stored week is what a
    # submission would carry, never a point mass
    recent = _floor_recent(spec, locations, drop_same_day)
    stored = {"pf": {loc: floor_samples(s, loc, asof,
                                        recent=recent.get(loc, []))
                     for loc, s in member.items()}}
    an_q = {loc: floor_quantiles(q)
            for loc, q in an_engine.run(spec, **an_kw).items()}
    out = {"asof": asof,
           **stored,
           "analogue": {loc: {h: {str(k): v for k, v in q.items()}
                              for h, q in qs.items()}
                        for loc, qs in an_q.items()}}
    if failed:
        out["pf_failures"] = failed
    write_week_samples(wd, out)
    if rules:
        _record_flags(root, asof, {"analogue": gh_flags,
                                   "pf": MS.cell_flags(cells)})
    # prune intermediates now (never fatal), unless any fit failed: then
    # keep everything as evidence, as the console keeps a failed workroot
    if not failed:
        try:
            from app.core import reclaim
            reclaim.prune_week(wd)
        except Exception:
            pass
    return out


def run_season(root: Path, season: str, locations: list, replicates=3,
               particles=10_000, width=pf_engine.DEFAULT_SHARD_WIDTH,
               progress=None, settings: dict | None = None,
               drop_same_day: bool = False, week_extra=None,
               engine: str = "pf") -> list:
    """Replay a season week by week, recording timing and honouring the STOP
    and PAUSE flags at fit resolution.

    `week_extra(asof, i, vintages)` returns week i's research dictionary
    (run_week's `extra`: a carried cloud, `flubnf retro --aux`). None means
    the shipped Groundhog (an_engine.SHIPPED_AUX preset, named in
    run_meta.json); the bare analogue must be asked for.

    `engine` "analogue" replays the Groundhog alone; recorded under
    `engine`, and a tree replayed one way is not resumed the other.

    Control points sit between fits (see run_week); a pause holds inside
    this call. `settings` (what the caller was asked for) is recorded with
    everything this function was given folded in.
    """
    root = Path(root).resolve()    # see run_week: subprocesses read these paths
    root.mkdir(parents=True, exist_ok=True)
    clear_flags(root)              # no stale STOP/PAUSE from an earlier replay
    vintages = season_vintages(season)
    # recorded before the first week, so an interrupted run still says what ran
    rec = dict(settings or {})
    rec.setdefault("season", season)
    rec.setdefault("locations", [str(l) for l in locations])
    rec.setdefault("replicates", int(replicates))
    rec.setdefault("particles", int(particles))
    rec.setdefault("drop_same_day", bool(drop_same_day))
    rec.setdefault("width", int(width))
    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {ENGINES}, got {engine!r}")
    rec["engine"] = engine
    if week_extra is None:
        week_extra = an_engine.aux_preset(an_engine.SHIPPED_AUX)
    rec.setdefault("week_extra", getattr(week_extra, "__name__", "custom"))
    # model knobs: one configuration per tree. The record (settings.knobs,
    # or what a pre-registry record's particles/replicates imply) must
    # match before completed weeks are resumed; start over (archive or
    # discard) to change them. Recorded only when off the shipped set.
    from app.core import knobs as _knobs
    want = _knobs.legacy_settings_knobs(rec)
    if want:
        rec["knobs"] = want
        rec["knobs_digest"] = _knobs.digest(want)
    else:
        rec.pop("knobs", None)
        rec.pop("knobs_digest", None)
    # the engine build the filter weeks are fitted by: one per season (a
    # resume on another commit, or with local edits made or undone, is
    # refused below); none for a Groundhog-only replay or no engine
    from app.core import engine_build as _eb
    build = _eb.engine_build() if pf_ran(engine) else {}
    rec.pop("engine_build", None)
    if _eb.record(build):
        rec["engine_build"] = _eb.record(build)
    if _weeks_on_disk(root):
        prior = (read_meta(root) or {}).get("settings") or {}
        had = _knobs.legacy_settings_knobs(prior)
        # a record from before the zero-anchor rule replayed as abstain
        if _knobs.settings_digest(had) != _knobs.settings_digest(want):
            raise KnobsMismatch(
                f"{season} at {root} has completed weeks replayed with "
                f"model settings {_knobs.label(_knobs.from_record(had))}; "
                f"this run asks for {_knobs.label(_knobs.from_record(want))}."
                " Archive or discard the existing results to change them.")
        # completed weeks are skipped on resume, so another location list
        # would pool weeks fitted over different scopes under one record
        change = location_scope_change(prior.get("locations"), locations)
        if change:
            raise LocationsMismatch(
                f"{season} at {root} has completed weeks {change}. "
                "Resuming would mix two location scopes in one season. "
                "Archive or discard the existing results to change it.")
        # nor on another engine build: weeks fitted by two engines would
        # be scored as one season. A record from before builds were
        # recorded resumes as before (and is not stamped by the resume)
        bchange = engine_build_change(prior, engine, build)
        if bchange:
            raise EngineBuildMismatch(
                f"{season} at {root} has completed weeks that {bchange}. "
                "Resuming would mix two engine builds in one season. "
                "Switch the engine back, or archive or discard the existing "
                "results to replay it on this one.")
        if prior and "engine_build" not in prior:
            rec.pop("engine_build", None)
        if prior and "knobs" not in prior:
            # a tree from before the registry resumed as it was: never
            # reclassified as modified by the resume
            rec.pop("knobs", None)
            rec.pop("knobs_digest", None)
    # the output floor run_week applies, recorded so a season stored before
    # replays applied it (no such key) can be told apart; a resume of one
    # says which of its weeks carry it
    if _weeks_on_disk(root):
        prior_floor = ((read_meta(root) or {}).get("settings")
                       or {}).get("output_floor")
        rec["output_floor"] = prior_floor or FLOOR_FROM_RESUME
    else:
        rec["output_floor"] = FLOOR_APPLIED
    _start_record(root, season, len(vintages), rec)
    beat = _Heartbeat(root)
    beat.start()
    done = []
    try:
        for i, asof in enumerate(vintages):
            _check_stop(root)                 # stop before dispatching a NEW week
            hold_while_paused(root)
            if week_done(root, asof):
                if progress:
                    progress(asof)
                continue          # never redone, never timed
            # the engine is re-read before every filter week: a branch
            # switched or a file edited mid-season stops the season here,
            # so no week is fitted by another build than the record names
            if _eb.record(build):
                moved = _eb.change(_eb.record(build), _eb.engine_build())
                if moved:
                    why = (f"stopped before {asof}: the engine changed during "
                           f"the replay (the completed weeks {moved}). "
                           "Switch the engine back and resume.")
                    _record_stop_reason(root, why)
                    raise EngineBuildChanged(f"{season}: {why}")
            # time by active-seconds delta: a pause can hold inside the week
            e0 = elapsed_now(read_meta(root))
            try:
                # inside the try: a raising callback fails the week, not the season
                wx = week_extra(asof, i, vintages) if week_extra else None
                if engine == "pf" and "oracle" not in (read_meta(root).get("settings") or {}):
                    # record whether the stored pf is the member or the plain filter
                    _record_setting(root, "oracle",
                                    "applied" if oracle_mod.wanted(wx)
                                    else "none (the plain filter, a research run)")
                run_week(root, season, asof, locations, replicates, particles,
                         width, drop_same_day=drop_same_day, extra=wx,
                         engine=engine)
                done.append(asof)
                # completed weeks only are timed
                _record_week(root, asof, elapsed_now(read_meta(root)) - e0)
                if _eb.record(build):
                    _record_week_build(root, asof, _eb.record(build))
            except SeasonStopped:
                # bank the segment's seconds; no entry for an incomplete week
                _record_partial(root, asof, elapsed_now(read_meta(root)) - e0)
                raise
            except Exception as e:              # a bad week never kills the season
                (root / "failures.log").open("a", encoding="utf-8").write(
                    f"{asof}: {e}\n")
            if progress:
                progress(asof)
    except (SeasonStopped, EngineBuildChanged):
        _finish_record(root, "stopped")
        raise
    except BaseException:
        # a progress callback may stop by raising: the flag on disk decides
        _finish_record(root, "stopped" if stop_path(root).exists() else "error")
        raise
    else:
        _finish_record(root, "done")
    finally:
        beat.stop()
    return done


#: scores.json's version, stored in every row's SCORES_V_COLUMN. 2: the
#: FluSight cell rule (scoring.cell_scored: truth of 0 and a median of 0
#: scored) with log-scale WIS and 50/80/95 coverage per row. A file without
#: it (version 1: truth > 0 and median > 0, no such columns) is not current,
#: so finalize_season rescores a live root; a sealed root keeps its file and
#: every reader of the new columns treats them as absent.
SCORES_V = 2
SCORES_V_COLUMN = "scores_v"


def scores_version(df) -> int:
    """The version a parsed scores frame was written under (1 for a file
    from before the version column; 0 for no frame)."""
    if df is None:
        return 0
    if SCORES_V_COLUMN not in getattr(df, "columns", ()) or not len(df):
        return 1
    try:
        return int(pd.to_numeric(df[SCORES_V_COLUMN], errors="coerce").min())
    except (TypeError, ValueError):
        return 1


def filter_scores_missing(root: Path, df) -> bool:
    """Whether a live root's scores lack the Liu-West filter alone although
    its newest week's oracle.json carries it (scores written before the
    filter was scored): then the root is rescored once. A sealed or
    imported root without oracle.json never asks for it."""
    if df is None or not len(df) or "model" not in getattr(df, "columns", ()):
        return False
    if FILTER_MEMBER in set(df["model"].unique()):
        return False
    weeks = season_sample_files(Path(root))
    return bool(weeks) and filter_quantiles(weeks[-1].parent) is not None


def scores_frame_current(df) -> bool:
    """Whether a parsed scores frame is this version's: the version column
    says so, or the frame has no rows (an empty file scores nothing under
    either rule, and is rescored while unscoreable anyway)."""
    if df is None:
        return False
    if not len(df):
        return True
    return scores_version(df) >= SCORES_V


#: the members score_season scores: the shipped Oracle SIHRS, the
#: Liu-West filter alone before the Oracle step (present only where the
#: step ran; retro_store.FILTER_MEMBER), and the Groundhog
SCORED_MEMBERS = ("pf", FILTER_MEMBER, "analogue")


def score_season(root: Path, season: str) -> pd.DataFrame:
    """Score every stored week vs settled truth: one row per (member,
    location, as-of, horizon) of SCORED_MEMBERS, under THE cell rule
    (scoring.cell_scored) with the per-cell metrics (scoring.cell_metrics)
    and the baseline's WIS and log-scale WIS on the same cell. Nothing is
    blended (older files' "ensemble" rows are not reproduced by a rescore).

    Columns: model, location, fips, asof, horizon, wis, log_wis, cov50,
    cov80, cov95 (0/1), base_wis, base_log_wis, rel, scores_v."""
    from app.core import scoring
    from datetime import timedelta
    truth, n2f = scoring.load_truth()
    rows = []
    for wk in season_sample_files(root):
        asof = wk.parent.name; T = pd.Timestamp(asof)
        mq = week_member_quantiles(root, asof)
        by_model = {m: mq.get(m, {}) for m in SCORED_MEMBERS}
        for loc in set().union(*by_model.values()):
            fips = n2f.get(loc)
            if not fips:
                continue
            for model, qs in ((m, q.get(loc, {}))
                              for m, q in by_model.items()):
                for h in hz.HORIZONS:
                    q = qs.get(h)
                    # canonical horizon h is h+1 weeks past the as-of
                    actual = truth.get(
                        (fips, T + timedelta(days=7 * (int(h) + 1))))
                    # the rule's truth and forecast halves; the baseline
                    # half is the join below
                    if not (scoring.truth_settled(actual)
                            and scoring.forecast_scoreable(q)):
                        continue
                    m = scoring.cell_metrics(q, actual)
                    if m is None:
                        continue
                    rows.append({"model": model, "location": loc, "fips": fips,
                                 "asof": asof, "horizon": int(h), **m})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # baseline per asof (the validated construction)
    bases, lbases = {}, {}
    for asof in df["asof"].unique():
        fips_set = set(df[df["asof"] == asof].fips)
        bases.update(scoring._baseline_cells(asof, fips_set, truth))
        lbases.update(scoring._baseline_log_cells(asof, fips_set, truth))
    df["base_wis"] = [bases.get((r.fips, r.asof, r.horizon), np.nan)
                      for r in df.itertuples()]
    df["base_log_wis"] = [lbases.get((r.fips, r.asof, r.horizon), np.nan)
                          for r in df.itertuples()]
    df = df.dropna(subset=["base_wis"])
    df["rel"] = df.wis / df.base_wis
    df[SCORES_V_COLUMN] = SCORES_V
    return df


#: bump when the aggregate's construction or cached shape changes
#: (v2: a fitted US block is excluded from the sum; v3: no blend row;
#: v4: the FluSight cell rule, log-scale relWIS and coverage per member)
NATIONAL_CACHE_V = 4

#: the analogue's national Monte Carlo draws, matching the PF's 3 x 10k
_NATIONAL_DRAWS = 30_000


def national_aggregate(root: Path) -> dict | None:
    """US-national relWIS constructed from the stored STATE forecasts,
    each member on its own, states treated as independent:

      * PF: per-state draws summed by draw index; quantiles of the sums.
      * Analogue (quantiles, not draws): each state's quantile curve is
        inverted and sampled with deterministically seeded uniforms, the
        draws summed across states and re-quantiled.

    Scored per (week, horizon) against the hub's US truth like
    score_season (the same cell rule and baseline). Expensive, so cached in
    playback_cache/us_aggregate.json keyed by _national_cache_key; the
    last computation's cost rides along as `seconds`.

    Returns {member: relWIS, "cells": {member: n}, "log_rel": {member:
    log-scale relWIS}, "cov": {member: {"50", "80", "95"}}, "weeks",
    "seconds"} (scoring.pooled_metrics over the member's national cells).
    """
    import zlib
    from datetime import timedelta
    from app.core import scoring
    from app.core import us_national as usn
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
    root = Path(root)
    wks = season_sample_files(root)
    if not wks:
        return None
    key = _national_cache_key(root)
    cf = root / "playback_cache" / "us_aggregate.json"
    try:
        cached = json.loads(cf.read_text(encoding="utf-8"))
        if cached.get("key") == key:
            return cached["result"]
    except Exception:
        pass
    t0 = time.monotonic()
    truth, _n2f = scoring.load_truth()
    levels = [float(L) for L in QL]
    rows = []                       # (model, asof, horizon 0-based, metrics)
    for wp in wks:
        d = read_samples(wp)
        asof = d["asof"]
        T = pd.Timestamp(asof)
        # sum jurisdictions only: a fitted US block would double the nation
        pf_locs = [l for l in d.get("pf", {}) if not usn.is_us(l)]
        an_locs = [l for l in d.get("analogue", {}) if not usn.is_us(l)]
        pf_nat, an_nat = {}, {}
        for h in hz.HORIZONS:
            arrs = []
            for loc in pf_locs:
                a = np.asarray(d["pf"][loc].get(h, []), float)
                if a.size:
                    arrs.append(a)
            if arrs:
                n = min(a.size for a in arrs)
                tot = np.zeros(n)
                for a in arrs:      # a non-finite draw in ANY state poisons
                    tot += a[:n]    # that index; the finite filter drops it
                tot = tot[np.isfinite(tot)]
                if tot.size:
                    pf_nat[h] = {L: float(np.quantile(tot, L))
                                 for L in levels}
            draws = None
            for loc in an_locs:
                q = d["analogue"][loc].get(h)
                if not q:
                    continue
                ks = sorted(q, key=float)
                lv = np.asarray([float(k) for k in ks])
                # monotone repair against tiny stored quantile inversions
                vv = np.maximum.accumulate(
                    np.asarray([float(q[k]) for k in ks]))
                rng = np.random.default_rng(
                    zlib.crc32(f"{asof}|{loc}|{h}".encode()))
                v = np.interp(rng.random(_NATIONAL_DRAWS), lv, vv)
                draws = v if draws is None else draws + v
            if draws is not None:
                draws = draws[np.isfinite(draws)]
                if draws.size:
                    an_nat[h] = {L: float(np.quantile(draws, L))
                                 for L in levels}
        for model, qs in (("pf", pf_nat), ("analogue", an_nat)):
            for h in hz.HORIZONS:
                q = qs.get(h)
                actual = truth.get(
                    ("US", T + timedelta(days=7 * (int(h) + 1))))
                # the same cell rule as score_season (baseline half below)
                if not (scoring.truth_settled(actual)
                        and scoring.forecast_scoreable(q)):
                    continue
                m = scoring.cell_metrics(q, actual)
                if m is None:
                    continue
                rows.append((model, asof, int(h), m))
    bases, lbases = {}, {}
    for asof in {r[1] for r in rows}:
        bases.update(scoring._baseline_cells(asof, {"US"}, truth))
        lbases.update(scoring._baseline_log_cells(asof, {"US"}, truth))
    result = {"cells": {}, "weeks": len(wks), "log_rel": {}, "cov": {}}
    for model in ("pf", "analogue"):
        cells = [{**m, "base_wis": bases.get(("US", asof, h)),
                  "base_log_wis": lbases.get(("US", asof, h), np.nan)}
                 for mm, asof, h, m in rows if mm == model]
        cells = [c for c in cells if c["base_wis"] is not None]
        if cells:
            pm = scoring.pooled_metrics(pd.DataFrame(cells))
            if pm["rel"] is not None:
                result[model] = pm["rel"]
            result["cells"][model] = pm["n"]
            result["log_rel"][model] = pm["log_rel"]
            result["cov"][model] = pm["cov"]
    result["seconds"] = round(time.monotonic() - t0, 1)
    # atomic; an unwritable tree (sealed, read-only) just recomputes next time
    try:
        cf.parent.mkdir(parents=True, exist_ok=True)
        tmp = cf.with_name(cf.name + ".tmp")
        tmp.write_text(json.dumps({"key": key, "result": result}), encoding="utf-8")
        os.replace(tmp, cf)
    except OSError:
        pass
    return result


def _national_cache_key(root: Path) -> dict:
    """The national aggregate's validity key, exactly as national_aggregate
    builds it: version, per-week samples mtimes, scores mtime."""
    root = Path(root)
    wks = season_sample_files(root)
    sf = root / "scores.json"
    return {"v": NATIONAL_CACHE_V,
            "weeks": {p.parent.name: int(p.stat().st_mtime) for p in wks},
            "scores_mtime": int(sf.stat().st_mtime) if sf.is_file() else 0}


def national_aggregate_fresh(root: Path) -> bool:
    """Whether the cached national aggregate is valid (a cheap check: the
    results page uses it to choose between serving and the preparing state)."""
    root = Path(root)
    if not season_sample_files(root):
        return True                     # nothing to aggregate: nothing stale
    cf = root / "playback_cache" / "us_aggregate.json"
    try:
        cached = json.loads(cf.read_text(encoding="utf-8"))
        return cached.get("key") == _national_cache_key(root)
    except Exception:
        return False


def scores_current(root: Path) -> bool:
    """Whether scores.json exists, parses, is this SCORES_V's (a file
    scored under the earlier cell rule is not), carries the Liu-West filter
    alone where its weeks do (filter_scores_missing), and is newer than
    every stored week and the truth (see scores_scoreable for whether it
    has rows)."""
    root = Path(root)
    sf = root / "scores.json"
    weeks = season_sample_files(root)
    if not weeks:
        return True
    if not sf.is_file():
        return False
    try:
        from app.core.data import truth_mtime
        if sf.stat().st_mtime < max([p.stat().st_mtime for p in weeks]
                                    + [truth_mtime()]):
            return False           # older than a sample, or than the truth
        df = pd.read_json(sf)
        return scores_frame_current(df) and not filter_scores_missing(root, df)
    except Exception:
        return False


def scores_scoreable(root: Path) -> bool:
    """Whether scores.json carries scored rows (empty means truth has not
    settled, or scoring failed)."""
    sf = Path(root) / "scores.json"
    try:
        d = pd.read_json(sf)
        return (not d.empty) and ("model" in d.columns)
    except Exception:
        return False


def newest_samples_mtime(root: Path) -> int:
    """The newest stored week's mtime (0 with none): a finalize job's input stamp."""
    try:
        return max((int(p.stat().st_mtime)
                    for p in season_sample_files(root)), default=0)
    except OSError:
        return 0


#: the finalize phases, in order, worded exactly as the preparing state
#: shows them
FINALIZE_PHASES = ("scoring cells", "building national aggregate",
                   "warming playback", "pruning intermediates")


def finalize_season(root: Path, season: str,
                    phase_cb=None, force: bool = False) -> dict:
    """Everything the results page needs, computed once: score the season
    (atomic scores.json; skipped when current and scoreable unless
    `force`), build the national aggregate, warm every playback payload,
    prune. Returns seconds per phase; `phase_cb(phase)` at each transition.

    Scoring must land first: the other caches are keyed on scores.json's
    mtime. Warming failures are not fatal (the week builds on first view)."""
    from app.core import playback
    root = Path(root)
    seconds: dict = {}

    def _phase(name):
        if phase_cb:
            try:
                phase_cb(name)
            except Exception:
                pass
        return time.monotonic()

    if force or not (scores_current(root) and scores_scoreable(root)):
        t = _phase("scoring cells")
        df = score_season(root, season)
        # atomic: a viewer never sees a half-written scores.json
        tmp = root / "scores.json.tmp"
        df.to_json(tmp)
        os.replace(tmp, root / "scores.json")
        seconds["scoring"] = round(time.monotonic() - t, 1)

    t = _phase("building national aggregate")
    try:
        national_aggregate(root)
    except Exception:
        pass          # the page omits the row rather than failing the job
    seconds["national"] = round(time.monotonic() - t, 1)

    t = _phase("warming playback")
    for w in sorted(p.parent.name for p in season_sample_files(root)):
        try:
            playback.build_week(root, season, w)
        except Exception:
            continue  # that week builds on first view, exactly as before
    seconds["playback"] = round(time.monotonic() - t, 1)

    # sweep leftover fit intermediates (reclaim refuses protected trees); never fatal
    t = _phase("pruning intermediates")
    try:
        from app.core import reclaim
        reclaim.prune_season(root)
    except Exception:
        pass
    seconds["prune"] = round(time.monotonic() - t, 1)
    seconds["total"] = round(sum(seconds.values()), 1)
    return seconds


def record_finalize(root: Path, seconds: dict) -> None:
    """Fold the finalize timing into run_meta.json."""
    with _META_LOCK:
        m = read_meta(root)
        m["finalize_seconds"] = {k: float(v) for k, v in (seconds or {}).items()
                                 if isinstance(v, (int, float))}
        write_meta(root, m)


HEADLINE_MODELS = ("pf", "analogue")


def _headline_metrics(scores_path: Path) -> dict:
    """{model: scoring.pooled_metrics} for every HEADLINE_MODELS entry a
    stored scores.json scores; {} when the file is absent or empty.

    Pooled, through us_national.pooled_frame (US rows never count)."""
    from app.core import us_national as usn
    from app.core.scoring import pooled_metrics
    try:
        df = pd.read_json(scores_path)
    except Exception:
        return {}
    if df.empty or "model" not in df.columns:
        return {}
    df = usn.pooled_frame(df)
    out = {}
    for m in HEADLINE_MODELS:
        pm = pooled_metrics(df[df.model == m])
        if pm["rel"] is not None:
            out[m] = pm
    return out


def state_metrics(df, models=HEADLINE_MODELS) -> dict:
    """Per-jurisdiction final scores from a scores frame: {location: {model:
    scoring.pooled_metrics}} ("rel", "log_rel", "cov" {"50", "80", "95"},
    "n"), US rows left out (us_national.pooled_frame; the national row is
    us_national.resolve's). A location a model did not score is absent from
    its dict; log_rel and cov are None for a file from before them."""
    from app.core import us_national as usn
    from app.core.scoring import pooled_metrics
    if df is None or "model" not in getattr(df, "columns", ()) \
            or "location" not in df.columns:
        return {}
    df = usn.pooled_frame(df)
    out: dict = {}
    for (loc, m), g in df[df.model.isin(list(models))].groupby(
            ["location", "model"], sort=True):
        pm = pooled_metrics(g)
        if pm["rel"] is not None:
            out.setdefault(str(loc), {})[m] = pm
    return out


def run_summary(root: Path) -> dict:
    """What one run -- live or archived -- amounts to: completed weeks, wall
    time, when it ran, whether it was scored, and its headline figures per
    model, pooled over the jurisdictions (US excluded), PF first:

      headline_rels      {model: relWIS}; `headline_rel` is the first
      headline_log_rels  {model: log-scale relWIS, or None}
      headline_covs      {model: {"50", "80", "95"} coverage fractions, or
                         None}
      headline_ns        {model: scored cells}

    A scores.json from before the log-scale and coverage columns (a sealed
    root) gives None for those. Every field degrades to None or 0 rather
    than raising."""
    root = Path(root)
    meta = read_meta(root)
    t = timing(meta) if meta else {}
    weeks = _weeks_on_disk(root) if root.is_dir() else 0
    sf = root / "scores.json"
    scored = sf.is_file()
    key = ((sf.stat().st_mtime if scored else None), weeks)
    hit = _SUMMARY_CACHE.get(str(root))
    if hit is not None and hit[0] == key:
        heads = hit[1]
        _SUMMARY_CACHE.move_to_end(str(root))     # least-recently-used
    else:
        heads = _headline_metrics(sf) if scored else {}
        _SUMMARY_CACHE[str(root)] = (key, heads)
        _SUMMARY_CACHE.move_to_end(str(root))
        while len(_SUMMARY_CACHE) > _SUMMARY_CACHE_MAX:
            _SUMMARY_CACHE.popitem(last=False)
    rels = {m: pm["rel"] for m, pm in heads.items()}
    return {"weeks": weeks,
            "elapsed_s": t.get("elapsed_s"),
            "started_utc": t.get("started_utc"),
            "finished_utc": t.get("finished_utc"),
            "status": effective_status(meta) if meta else "",
            "scored": scored,
            # first in HEADLINE_MODELS order that the file covers
            "headline_rel": next(iter(rels.values()), None),
            "headline_rels": rels,
            "headline_log_rels": {m: pm["log_rel"] for m, pm in heads.items()},
            "headline_covs": {m: (dict(pm["cov"]) if pm["cov"] else None)
                              for m, pm in heads.items()},
            "headline_ns": {m: pm["n"] for m, pm in heads.items()}}


