"""Season-as-competition retrospective: run every vintage week like a real
submission day, score against settled truth, aggregate.

Engineering rules (each one paid for):
  * RESUMABLE: each week is a checkpoint; completed weeks are detected and
    never redone (a crash costs one week, not a season).
  * one ledger run per season; per-week artifacts under weeks/<date>/.
  * members: pf (seeded, replicated) + analogue + LOSO-honest ensemble --
    for retrospectives the blend weight NEVER comes from the season being
    scored (self-grading); callers pass weights fitted elsewhere.
  * parallel width: PF cells sharded across N runner subprocesses (entry-point
    files, never stdin -- macOS spawn rule).
  * CONTROLLABLE: STOP and PAUSE are files in the season root, polled at FIT
    resolution -- between individual (location, replicate) fits inside a
    week, not just between weeks -- the same flag mechanism the PF engine
    uses for console runs. A press lets only the fits already in flight
    finish (seconds to one fit's duration, never a full week), and every
    finished fit is checkpointed in the week's cells_done/, so a stopped
    week resumes by refitting only the cells that never ran.
  * TIMED: run_meta.json in the season root records wall time as the replay
    goes, accumulating across resumes rather than restarting the clock.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core.data import ARCHIVE, LOCATIONS          # noqa: E402
from app.core.engines import analogue as an_engine    # noqa: E402
from app.core.engines import pf as pf_engine          # noqa: E402
from app.core import ensemble as ens                  # noqa: E402
from app.core import proc as proc_mod                 # noqa: E402
from app.core.runs import (LOCATION_LIST_LIMIT,       # noqa: E402
                           RunSpec, locations_phrase)

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
    """Seasons derived from the hub's vintage archive: a vintage dated inside
    a season's window makes that season available, so a future season appears
    automatically once its vintages exist. Falls back to the hardcoded season
    list if derivation fails or the archive is empty."""
    try:
        seasons = set()
        for p in ARCHIVE.glob("target-hospital-admissions_*.csv"):
            v = p.name.split("_")[-1].removesuffix(".csv")
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
    lo, hi = season_bounds(season)
    return [v for v in sorted(p.name.split("_")[-1].removesuffix(".csv")
                              for p in ARCHIVE.glob("target-hospital-admissions_*.csv"))
            if lo <= v <= hi]


def _week_dir(root: Path, asof: str) -> Path:
    return root / "weeks" / asof


# --------------------------------------------------------------------------
# the samples store: every reader and writer of a stored week goes through
# these helpers, so a week stored as samples.json and one stored as
# samples.json.gz are indistinguishable everywhere downstream (scoring,
# playback, the national aggregate, the reports, the exports). New weeks are
# written gzipped -- the numeric JSON compresses ~3.7x (measured on a 144 MB
# full-grid week; the decompress adds ~0.2 s to a 1.6 s parse) -- and
# existing files migrate through compress_samples_file, which preserves the
# file's mtime so every cache keyed on it stays valid.
# --------------------------------------------------------------------------

SAMPLES_JSON = "samples.json"
SAMPLES_GZ = "samples.json.gz"


def samples_file(wd: Path) -> Path | None:
    """The week's stored samples file -- samples.json or its gzip form --
    or None when the week is incomplete. Plain JSON wins when both exist:
    a migration interrupted between writing the gzip and retiring the
    original leaves both behind, and the original remains the record until
    it is actually retired."""
    p = Path(wd) / SAMPLES_JSON
    if p.is_file():
        return p
    g = Path(wd) / SAMPLES_GZ
    return g if g.is_file() else None


def week_samples_path(root: Path, asof: str) -> Path | None:
    return samples_file(_week_dir(root, asof))


def season_sample_files(root: Path) -> list:
    """One stored samples file per completed week, ascending by week name --
    the successor of every `weeks/*/samples.json` glob, form-blind."""
    weeks = Path(root) / "weeks"
    if not weeks.is_dir():
        return []
    out = []
    try:
        for wd in sorted(weeks.iterdir()):
            p = samples_file(wd)
            if p is not None:
                out.append(p)
    except OSError:
        return []
    return out


def read_samples(fp: Path) -> dict:
    """Parse one stored samples file, transparently across both forms."""
    fp = Path(fp)
    if fp.name.endswith(".gz"):
        with gzip.open(fp, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(fp.read_text())


def read_week_samples(root: Path, asof: str) -> dict:
    fp = week_samples_path(root, asof)
    if fp is None:
        raise FileNotFoundError(
            f"no stored samples for week {asof} under {root}")
    return read_samples(fp)


def write_week_samples(wd: Path, obj: dict) -> Path:
    """Store a completed week's samples, gzipped. Atomic (write beside,
    then replace), and any plain-JSON file a previous run of this week
    left behind is retired so samples_file never faces two records."""
    wd = Path(wd)
    fp = wd / SAMPLES_GZ
    tmp = wd / (SAMPLES_GZ + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump(obj, f)
    os.replace(tmp, fp)
    (wd / SAMPLES_JSON).unlink(missing_ok=True)
    return fp


def compress_samples_file(fp: Path) -> Path:
    """Migrate one stored week to the gzip form, preserving the file's
    mtime so every cache keyed on it (playback payloads, stats cells, the
    national aggregate, scores currency, report freshness) stays valid
    without a rebuild. Atomic: a crash before the final replace leaves the
    plain file as the record; one after it leaves both, and samples_file
    keeps reading the original until the retry retires it."""
    fp = Path(fp)
    if fp.name.endswith(".gz"):
        return fp
    st = fp.stat()
    gz = fp.with_name(SAMPLES_GZ)
    tmp = fp.with_name(SAMPLES_GZ + ".tmp")
    with open(fp, "rb") as fin, gzip.open(tmp, "wb", compresslevel=6) as fo:
        shutil.copyfileobj(fin, fo, 1 << 20)
    os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))
    os.replace(tmp, gz)
    fp.unlink()
    return gz


def week_done(root: Path, asof: str) -> bool:
    return week_samples_path(root, asof) is not None


# --------------------------------------------------------------------------
# run record: timing, heartbeat, and the STOP / PAUSE control flags
# --------------------------------------------------------------------------

META_NAME = "run_meta.json"
STOP_NAME = "STOP"
PAUSE_NAME = "PAUSE"

#: a status claiming to be live is disbelieved once the heartbeat is older
#: than this. The worker beats every HEARTBEAT_EVERY_S, so the margin is
#: generous: only a dead process goes quiet this long.
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
    """The season's run record, or {} when absent or unreadable. A partially
    written file must never take a page down, so every failure reads as 'no
    record' rather than raising."""
    try:
        d = json.loads(meta_path(root).read_text())
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def write_meta(root: Path, meta: dict) -> None:
    """Atomic: write beside, then replace. A crash can leave the previous
    record or the new one, never a half-written one."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    tmp = meta_path(root).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(meta, sort_keys=True))
    os.replace(tmp, meta_path(root))


def request_stop(root: Path) -> bool:
    """Ask the worker to finish only the fits in flight and exit. Clears
    PAUSE too, so a paused worker wakes up and stops instead of holding
    forever.

    Never creates the season tree: a live worker has already made it, and a
    request against a season that was never replayed should leave no trace.
    Returns whether the flag was actually written."""
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
    """Derived timing facts for the UI and the report headers: total wall
    time, weeks done, and -- from the per-week seconds -- a mean and the
    slowest week. Weeks skipped as already complete are never timed, so the
    mean describes work actually done."""
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
    """Move the open segment's seconds into elapsed_s and restart it. Called
    at every week boundary and on every heartbeat, so a hard crash loses at
    most one heartbeat interval of the current week rather than the whole
    segment."""
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
    """Keeps run_meta.json's heartbeat fresh while a week is fitting. Without
    it a 40-minute week would look like a dead process to every reader."""

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


#: How the retro form's location scopes read when a replay had no explicit
#: location list to name (the label is what the user actually chose).
SCOPE_LABELS = {"panel6": "6-state panel", "all": "all 52 jurisdictions",
                "custom": "custom selection"}


def settings_summary(meta: dict) -> list:
    """The settings that produced a replay, as (label, value) pairs, read
    from its own run record.

    Absent for a season with no recorded settings, which is the honest
    answer for the sealed validation runs: they predate the record, and
    inventing their configuration would be worse than saying nothing.
    """
    s = (meta or {}).get("settings")
    if not isinstance(s, dict) or not s:
        return []
    locs = [str(l) for l in (s.get("locations") or [])]
    scope = str(s.get("scope") or "")
    where = locations_phrase(locs) if locs else SCOPE_LABELS.get(scope, scope)
    if scope == "custom" and len(locs) > LOCATION_LIST_LIMIT:
        where = f"{SCOPE_LABELS['custom']}, {where}"
    pairs = [("season", str(s.get("season") or (meta or {}).get("season") or "")),
             ("locations", where),
             ("particles", f"{int(s.get('particles') or 0):,}"
              if s.get("particles") else ""),
             ("replicates", str(s.get("replicates") or "")),
             ("shard width", str(s.get("width") or "")),
             ("engine preset", str(s.get("engine") or ""))]
    return [(k, v) for k, v in pairs if v not in ("", None)]


def resume_form_fields(meta: dict) -> dict | None:
    """The /retro/run form fields that resume a recorded replay with the
    settings its own run record holds, so a stopped or interrupted season
    can offer one-click resumption instead of asking the user to re-fill
    the form identically.

    The scope the user picked is passed through when the record names one
    (panel6 and all are recomputed server-side exactly as the form path
    does); a record carrying only the location list resubmits it as a
    custom selection, which reproduces the run's locations verbatim.

    None when the record holds no settings (seasons replayed before the
    record existed) or not enough to name a scope: the caller must then
    offer no shortcut and leave the form path as the only way, which is the
    honest answer for a run whose configuration was never recorded."""
    s = (meta or {}).get("settings")
    if not isinstance(s, dict) or not s:
        return None
    season = str(s.get("season") or (meta or {}).get("season") or "")
    if not season:
        return None
    locs = [str(l) for l in (s.get("locations") or [])]
    scope = str(s.get("scope") or "")
    out = {"season": season, "mode": "resume"}
    if scope in ("panel6", "all"):
        out["locations"] = scope
        out["custom_locations"] = []
    elif locs:
        out["locations"] = "custom"
        out["custom_locations"] = locs
    else:
        return None
    for key in ("particles", "replicates", "width"):
        try:
            v = int(s.get(key) or 0)
        except (TypeError, ValueError):
            v = 0
        if v > 0:
            out[key] = v
    engine = str(s.get("engine") or "")
    if engine:
        out["engine"] = engine
    return out


def _start_record(root: Path, season: str, total_weeks: int,
                  settings: dict | None = None) -> dict:
    """Open (or reopen) the season's run record. A resume keeps started_utc
    and elapsed_s: the clock accumulates, it never restarts.

    The settings of the replay that is starting are recorded here, at the
    start, so the record answers 'what produced these weeks' even for a run
    that never finished. A resume records the settings it is resuming WITH,
    which is what the weeks from here on were actually fitted under."""
    with _META_LOCK:
        m = read_meta(root)
        now = _now()
        m["season"] = season
        m["status"] = "running"
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


def _record_week(root: Path, asof: str, seconds: float) -> None:
    with _META_LOCK:
        m = read_meta(root)
        now = _now()
        _fold(m, now)
        # a week completed across a mid-week stop gets ONE week_seconds
        # entry covering the work of every segment: the seconds its earlier
        # stopped segments banked are folded in here and retired
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


def _record_partial(root: Path, asof: str, seconds: float) -> None:
    """Bank a stopped week's ACTIVE seconds without writing a week_seconds
    entry: the week is incomplete, and timing an unfinished week would drag
    the mean per week toward zero. The banked seconds join the entry the
    week finally earns when a resume completes it (see _record_week).
    Accumulates across repeated stop-and-resume of the same week."""
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
    """Retire a week's banked partial seconds without spending them. Called
    when the week's tree is rebuilt from scratch (its settings changed, or
    its preparation was unusable): the banked work belonged to fits that no
    longer exist, and timing the fresh week with them would overstate it."""
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
    """Block while the PAUSE flag stands. The process stays alive and the
    caller's sleep guard stays held, so an overnight replay resumes on the
    same machine state it paused on. Returns True if it actually held."""
    if not pause_path(root).exists():
        return False
    _set_paused(root, True)
    while pause_path(root).exists():
        if stop_path(root).exists():
            raise SeasonStopped("stop requested while paused")
        _sleep(poll_s)
    # request_stop clears PAUSE to wake the worker, so the flag that released
    # this hold may itself have been a stop: check again before resuming
    if stop_path(root).exists():
        raise SeasonStopped("stop requested while paused")
    _set_paused(root, False)
    return True


# --------------------------------------------------------------------------
# fit-level execution of one week
#
# A full-grid week is roughly 150 fits and ten minutes of work; a Stop or
# Pause that only lands at the week boundary is not a control at all. So the
# unit of control inside a week is the individual fit: every finished
# (location, replicate) cell leaves an atomic marker in <week>/cells_done/,
# the flags are polled while the runners work, and the first sighting stops
# the DISPATCH of further fits -- the runners finish only the fit each has in
# flight (a HALT file they check between cells) and exit. With width 6 and
# 15-25 s per fit, a press lands in well under a minute.
#
# The markers double as the mid-week resume: a later run of the same week
# reuses its prepared cells (when the manifest matches) and refits only the
# cells with no marker. samples.json still appears only when every cell is
# done, so the atomic-week guarantee downstream is untouched.
# --------------------------------------------------------------------------

CELL_DONE_DIRNAME = "cells_done"
HALT_NAME = "HALT"
PREP_NAME = "prep.json"
WEEK_TIMEOUT_S = 7200.0
FIT_POLL_S = 1.0

#: The week runner: like the PF engine's console runner it executes its
#: shard's cells sequentially in the engine venv (an entry-point FILE, never
#: stdin -- macOS spawn rule), but it records each finished cell atomically
#: the moment the fit ends and it exits between cells once HALT appears.
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
    """Keys of the week's finished fits. Each marker is written atomically
    (beside-then-replace) by the runner the moment its fit ends, so this is
    exactly the set a resumed week may skip."""
    d = _cell_done_dir(wd)
    return {p.stem for p in d.glob("*.json")} if d.is_dir() else set()


def mark_cell_done(wd: Path, key: str, status: str = "ok") -> None:
    """Record one finished fit the way the runner does: atomically, keyed by
    the cell tag. Kept here so tests and tools mark cells identically."""
    d = _cell_done_dir(wd)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{key}.tmp"
    tmp.write_text(json.dumps({"key": key, "status": status}))
    os.replace(tmp, d / f"{key}.json")


def _prepare_week(root: Path, asof: str, spec, manifest: dict) -> list:
    """The week's prepared cells, reusing a previous segment's preparation
    when it matches. A mid-week stop leaves models, confs, and finished-fit
    markers behind; when this run's manifest (locations, replicates,
    particles, season start) equals the one recorded beside them, they all
    survive and only the unfitted cells will run. Anything else -- no
    manifest, a different one, an unreadable tree -- rebuilds the week from
    scratch, and retires any partial seconds the dead tree had banked."""
    wd = _week_dir(root, asof)
    cj, mf = wd / "cells.json", wd / PREP_NAME
    if cj.is_file() and mf.is_file():
        try:
            if json.loads(mf.read_text()) == manifest:
                return json.loads(cj.read_text())
        except Exception:
            pass
    if wd.exists():
        shutil.rmtree(wd)              # half-prepared or foreign: start clean
    _clear_partial(root, asof)
    wd.mkdir(parents=True)
    cells = pf_engine.prepare(spec, wd)
    _cell_done_dir(wd).mkdir(exist_ok=True)
    mf.write_text(json.dumps(manifest, sort_keys=True))
    return cells


def _launch_runners(wd: Path, shards: list, halt: Path) -> list:
    """One runner subprocess per shard, started at reduced priority so the
    console stays responsive while a season replays (see app/core/proc.py).
    Split out so tests can stand in fake fits; returns Popen-like objects
    exposing poll() and kill()."""
    procs = []
    done = _cell_done_dir(wd)
    done.mkdir(parents=True, exist_ok=True)   # the runners write into it
    for i, shard in enumerate(shards):
        sj = wd / f"cells_{i}.json"
        sj.write_text(json.dumps(shard))
        runner = wd / f"runner_{i}.py"
        runner.write_text(_RETRO_RUNNER.format(
            pybnf_path=str(pf_engine.PYBNF_PF), cells_json=str(sj),
            halt_path=str(halt), done_dir=str(done)))
        procs.append(subprocess.Popen(proc_mod.low_priority_cmd(
                     [str(pf_engine.PY_ENGINE
                      if hasattr(pf_engine, 'PY_ENGINE') else pf_engine.PY310),
                      str(runner)]), stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL,
                     **proc_mod.low_priority_popen_kwargs()))
    return procs


def _run_round(root: Path, wd: Path, pending: list, width: int) -> None:
    """Dispatch the pending cells across runners and wait for them to drain.

    The STOP and PAUSE flags are polled every FIT_POLL_S while the runners
    work; the first sighting touches the week's HALT file, each runner then
    finishes only the fit it has in flight and exits. The caller decides
    what the flag means (stop raises, pause holds); this function guarantees
    only the drain, and that every finished fit left its marker."""
    wd = Path(wd)
    halt = wd / HALT_NAME
    halt.unlink(missing_ok=True)          # stale from an earlier segment
    before = len(cells_done(wd))
    width = max(1, int(width))
    shards = [pending[i::width] for i in range(width) if pending[i::width]]
    procs = _launch_runners(wd, shards, halt)
    flagged = False
    deadline = time.time() + WEEK_TIMEOUT_S
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
    if not flagged and len(cells_done(wd)) <= before:
        # the runners exited unflagged without finishing a single fit:
        # dispatching again would spin forever on the same broken engine
        raise RuntimeError("PF runners exited without completing any fit")


def run_week(root: Path, season: str, asof: str, locations: list,
             replicates: int = 3, particles: int = 10_000,
             width: int = 4) -> dict:
    """One submission day: PF (sharded) + analogue; store samples+quantiles.

    Fit-level control and resume: the STOP and PAUSE flags are honoured
    BETWEEN individual fits (the fits in flight drain first -- a stop raises
    SeasonStopped without writing samples.json, a pause holds right here
    with the processes alive), and a later run of an interrupted week refits
    only the cells with no marker in cells_done/. samples.json still appears
    only when every cell is done, so week atomicity is unchanged."""
    root = Path(root)
    wd = _week_dir(root, asof)
    if week_done(root, asof):
        return read_week_samples(root, asof)
    spec = RunSpec(engine="retro", forecast_date=asof, locations=locations,
                   season_start=season_bounds(season)[0],
                   replicates=replicates, particles=particles)
    manifest = {"locations": [str(l) for l in locations],
                "replicates": int(replicates), "particles": int(particles),
                "season_start": spec.season_start}
    _check_stop(root)         # a standing flag must not even prepare a week
    hold_while_paused(root)
    cells = _prepare_week(root, asof, spec, manifest)
    while True:
        done_keys = cells_done(wd)
        pending = [c for c in cells if c["key"] not in done_keys]
        if not pending:
            break             # every fit is in; assembling costs nothing now
        _check_stop(root)     # the flag a drained round saw lands HERE, at
        hold_while_paused(root)   # fit resolution, not at the week boundary
        _run_round(root, wd, pending, width)
    pf_samples = pf_engine.collect(wd)
    an_q = an_engine.run(spec)
    out = {"asof": asof,
           "pf": pf_samples,
           "analogue": {loc: {h: {str(k): v for k, v in q.items()}
                              for h, q in qs.items()}
                        for loc, qs in an_q.items()}}
    write_week_samples(wd, out)
    # storage hygiene the moment the week is assembled: the per-cell fit
    # trees, runner scripts, shard lists, and done-markers this samples file
    # already folded in are intermediates now, and keeping them is what let
    # a season tree grow to gigabytes. Never fatal: a week that cannot be
    # pruned is still a fitted week.
    try:
        from app.core import reclaim
        reclaim.prune_week(wd)
    except Exception:
        pass
    return out


def run_season(root: Path, season: str, locations: list, replicates=3,
               particles=10_000, width=4, progress=None,
               settings: dict | None = None) -> list:
    """Replay a season week by week, recording timing and honouring the STOP
    and PAUSE flags at fit resolution.

    Control points sit BETWEEN FITS: run_week polls the same flags while its
    runners work, so a press waits only for the fits in flight (well under a
    minute at the usual widths), never for a ten-minute full-grid week. A
    stop leaves the interrupted week's finished fits checkpointed and its
    samples.json unwritten -- the week stays incomplete, downstream sees
    nothing -- and the next replay refits only the cells that never ran. A
    pause holds inside this call, keeping the process (and the caller's
    sleep guard) alive.

    `settings` is what the caller was asked for (the scope the user picked,
    the engine preset); everything this function was actually given is
    folded in, so the record describes the run even when the caller passes
    nothing.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    clear_flags(root)              # no stale STOP/PAUSE from an earlier replay
    vintages = season_vintages(season)
    # the settings this replay actually runs under, recorded before the first
    # week so an interrupted run still says what produced its weeks
    rec = dict(settings or {})
    rec.setdefault("season", season)
    rec.setdefault("locations", [str(l) for l in locations])
    rec.setdefault("replicates", int(replicates))
    rec.setdefault("particles", int(particles))
    rec.setdefault("width", int(width))
    rec.setdefault("engine", "pf")
    _start_record(root, season, len(vintages), rec)
    beat = _Heartbeat(root)
    beat.start()
    done = []
    try:
        for asof in vintages:
            _check_stop(root)                 # stop before dispatching a NEW week
            hold_while_paused(root)
            if week_done(root, asof):
                if progress:
                    progress(asof)
                continue          # never redone, and never timed: a skipped
                                  # week would drag the mean toward zero
            # week timing by ACTIVE-seconds delta, not wall clock: a pause
            # can now hold INSIDE the week, and elapsed_now already excludes
            # held time, so the week's entry measures only work
            e0 = elapsed_now(read_meta(root))
            try:
                run_week(root, season, asof, locations, replicates, particles,
                         width)
                done.append(asof)
            except SeasonStopped:
                # a fit-level stop: bank the segment's seconds so the week's
                # eventual week_seconds entry covers BOTH segments, but write
                # no entry now -- the week is incomplete, and timing it would
                # corrupt the mean seconds per week
                _record_partial(root, asof, elapsed_now(read_meta(root)) - e0)
                raise
            except Exception as e:              # a bad week never kills the season
                (root / "failures.log").open("a").write(f"{asof}: {e}\n")
            _record_week(root, asof, elapsed_now(read_meta(root)) - e0)
            if progress:
                progress(asof)
    except SeasonStopped:
        _finish_record(root, "stopped")
        raise
    except BaseException:
        # a caller's progress callback may signal a stop by raising; believe
        # the flag on disk about which of the two this was
        _finish_record(root, "stopped" if stop_path(root).exists() else "error")
        raise
    else:
        _finish_record(root, "done")
    finally:
        beat.stop()
    return done


def score_season(root: Path, season: str,
                 ensemble_weights: dict | str | None = None) -> pd.DataFrame:
    """Score every stored week vs settled truth.

    `ensemble_weights` is passed straight to ens.vincentize, so the default
    (None) is the shipped, unfitted equal-weight blend -- the one every
    published score in this repository was computed with. Anything fitted
    must be named (ens.FROZEN or an explicit table) AND must be LOSO for this
    season: fitting weights on the season being scored is leakage."""
    from app.core.scoring import _baseline_cells, load_truth
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
    from flubnf.wis import wis as wis_fn
    from datetime import timedelta
    truth, n2f = load_truth()
    rows = []
    for wk in season_sample_files(root):
        d = read_samples(wk)
        asof = d["asof"]; T = pd.Timestamp(asof)
        for loc in set(d["pf"]) | set(d["analogue"]):
            fips = n2f.get(loc)
            if not fips:
                continue
            pf_q = (ens.member_quantiles_from_samples(d["pf"][loc])
                    if loc in d["pf"] else {})
            an_q = ({h: {float(k): v for k, v in q.items()}
                     for h, q in d["analogue"][loc].items()}
                    if loc in d["analogue"] else {})
            members = {}
            if pf_q: members["pf"] = pf_q
            if an_q: members["analogue"] = an_q
            blend = ens.vincentize(members, weights=ensemble_weights,
                                   location_fips=fips) if members else {}
            for model, qs in (("pf", pf_q), ("analogue", an_q),
                              ("ensemble", blend)):
                for h in ("1", "2", "3", "4"):
                    q = qs.get(h)
                    if not q:
                        continue
                    actual = truth.get((fips, T + timedelta(days=7 * int(h))))
                    if actual is None or actual <= 0 or q[0.5] <= 0:
                        continue
                    try:
                        w = float(wis_fn(q, actual).wis)
                    except Exception:
                        continue
                    rows.append({"model": model, "location": loc, "fips": fips,
                                 "asof": asof, "horizon": int(h) - 1, "wis": w})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # baseline per asof (the validated construction)
    bases = {}
    for asof in df["asof"].unique():
        bs = _baseline_cells(asof, set(df[df["asof"] == asof].fips), truth)
        for k, v in bs.items():
            bases[k] = v
    df["base_wis"] = [bases.get((r.fips, r.asof, r.horizon), np.nan)
                      for r in df.itertuples()]
    df = df.dropna(subset=["base_wis"])
    df["rel"] = df.wis / df.base_wis
    return df


#: bump when the national-aggregate construction or cached shape changes
NATIONAL_CACHE_V = 1

#: draws for the analogue member's national Monte Carlo sum, matching the
#: PF grid's 3 x 10k draw count so both members aggregate at the same depth
_NATIONAL_DRAWS = 30_000


def national_aggregate(root: Path,
                       ensemble_weights: dict | str | None = None
                       ) -> dict | None:
    """US-national relWIS aggregated from the stored STATE forecasts. The
    retro grid fits states only, so a national score must be constructed;
    this is that construction, stated honestly wherever it is shown.

    Construction (the members are aggregated separately, then blended,
    because the state ensemble exists only at quantile level, so there are
    no ensemble sample draws to sum):

      * PF: the stored per-state sample arrays are summed draw by draw,
        aligned by draw index within the member; states are treated as
        independent. Quantiles of the summed draws.
      * Analogue: stored as quantile sets, not draws, so a draw-index sum
        is impossible; instead each state's quantile curve is inverted
        (linear interpolation across the 23 FluSight levels) and sampled
        with its own independent, deterministically seeded uniforms, the
        draws are summed across states, and the sums are re-quantiled.
        The same independence treatment as the PF sum.
      * Ensemble: the two NATIONAL member quantile sets vincentized with
        the same weights the season's state scoring uses (50/50 on the
        season page), the shipped recipe. `ensemble_weights` follows
        ens.vincentize: None is the unfitted equal-weight blend.

    Each national quantile set is scored per (week, horizon) against the
    hub's US truth row with the same WIS and validated-baseline machinery
    as score_season, under the same degenerate-cell guards; relWIS is
    sum(wis) / sum(base_wis).

    The computation is not free (52 states x 30k draws x 4 horizons per
    week, behind a full parse of every samples.json), so the result is
    cached in playback_cache/us_aggregate.json under the season's stats
    validity key: the per-week samples.json mtimes plus scores.json's
    mtime, with a version stamp and the weights. The measured wall cost of
    the last real computation rides along in the result as `seconds`.
    """
    import time
    import zlib
    from datetime import timedelta
    from app.core.scoring import _baseline_cells, load_truth
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
    from flubnf.wis import wis as wis_fn
    root = Path(root)
    wks = season_sample_files(root)
    if not wks:
        return None
    sf = root / "scores.json"
    key = {"v": NATIONAL_CACHE_V,
           "weights": ensemble_weights or {},
           "weeks": {p.parent.name: int(p.stat().st_mtime) for p in wks},
           "scores_mtime": int(sf.stat().st_mtime) if sf.is_file() else 0}
    cf = root / "playback_cache" / "us_aggregate.json"
    try:
        cached = json.loads(cf.read_text())
        if cached.get("key") == key:
            return cached["result"]
    except Exception:
        pass
    t0 = time.monotonic()
    truth, _n2f = load_truth()
    levels = [float(L) for L in QL]
    rows = []                       # (model, asof, horizon 0-based, wis)
    for wp in wks:
        d = read_samples(wp)
        asof = d["asof"]
        T = pd.Timestamp(asof)
        pf_nat, an_nat = {}, {}
        for h in ("1", "2", "3", "4"):
            arrs = []
            for loc in d.get("pf", {}):
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
            for loc in d.get("analogue", {}):
                q = d["analogue"][loc].get(h)
                if not q:
                    continue
                ks = sorted(q, key=float)
                lv = np.asarray([float(k) for k in ks])
                # monotone repair guards interpolation against any tiny
                # quantile inversion in the stored set
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
        members = {}
        if pf_nat:
            members["pf"] = pf_nat
        if an_nat:
            members["analogue"] = an_nat
        blend = (ens.vincentize(members, weights=ensemble_weights,
                                location_fips="US") if members else {})
        for model, qs in (("pf", pf_nat), ("analogue", an_nat),
                          ("ensemble", blend)):
            for h in ("1", "2", "3", "4"):
                q = qs.get(h)
                if not q:
                    continue
                actual = truth.get(("US", T + timedelta(days=7 * int(h))))
                # the same degenerate-cell guards as score_season
                if actual is None or actual <= 0 or q[0.5] <= 0:
                    continue
                try:
                    w = float(wis_fn(q, actual).wis)
                except Exception:
                    continue
                rows.append((model, asof, int(h) - 1, w))
    bases = {}
    for asof in {r[1] for r in rows}:
        for k, v in _baseline_cells(asof, {"US"}, truth).items():
            bases[k] = v
    result = {"cells": {}, "weeks": len(wks)}
    for model in ("pf", "analogue", "ensemble"):
        cells = [(w, bases.get(("US", asof, h)))
                 for m, asof, h, w in rows if m == model]
        cells = [(w, b) for w, b in cells if b]
        if cells:
            result[model] = (sum(w for w, _ in cells)
                             / sum(b for _, b in cells))
            result["cells"][model] = len(cells)
    result["seconds"] = round(time.monotonic() - t0, 1)
    # write beside, then replace, like scores.json: a concurrent viewer may
    # never see a half-written cache file
    cf.parent.mkdir(parents=True, exist_ok=True)
    tmp = cf.with_name(cf.name + ".tmp")
    tmp.write_text(json.dumps({"key": key, "result": result}))
    os.replace(tmp, cf)
    return result


def _national_cache_key(root: Path,
                        ensemble_weights: dict | str | None) -> dict:
    """The national aggregate's validity key, exactly as national_aggregate
    builds it: version, weights, per-week samples mtimes, scores mtime."""
    root = Path(root)
    wks = season_sample_files(root)
    sf = root / "scores.json"
    return {"v": NATIONAL_CACHE_V,
            "weights": ensemble_weights or {},
            "weeks": {p.parent.name: int(p.stat().st_mtime) for p in wks},
            "scores_mtime": int(sf.stat().st_mtime) if sf.is_file() else 0}


def national_aggregate_fresh(root: Path,
                             ensemble_weights: dict | str | None = None
                             ) -> bool:
    """Whether the cached national aggregate is valid for the tree as it
    stands -- the cheap read national_aggregate itself makes before deciding
    to recompute. The results page asks this to decide between serving the
    page directly and showing the preparing state while a background job
    rebuilds the caches; asking by computing would BE the freeze."""
    root = Path(root)
    if not season_sample_files(root):
        return True                     # nothing to aggregate: nothing stale
    cf = root / "playback_cache" / "us_aggregate.json"
    try:
        cached = json.loads(cf.read_text())
        return cached.get("key") == _national_cache_key(root,
                                                        ensemble_weights)
    except Exception:
        return False


def scores_current(root: Path) -> bool:
    """Whether scores.json exists, parses, and is newer than every stored
    week -- the mtime half of the staleness rule the results page has always
    applied. Says nothing about whether it scored any cells; see
    scores_scoreable for that half."""
    root = Path(root)
    sf = root / "scores.json"
    weeks = season_sample_files(root)
    if not weeks:
        return True
    if not sf.is_file():
        return False
    try:
        if sf.stat().st_mtime < max(p.stat().st_mtime for p in weeks):
            return False
        pd.read_json(sf)
        return True
    except Exception:
        return False


def scores_scoreable(root: Path) -> bool:
    """Whether scores.json carries scored rows (a model column and at least
    one cell). An empty-but-current file means truth has not settled, or an
    early run failed to score -- the results page distinguishes the two by
    whether a completion job already covered these exact inputs."""
    sf = Path(root) / "scores.json"
    try:
        d = pd.read_json(sf)
        return (not d.empty) and ("model" in d.columns)
    except Exception:
        return False


def newest_samples_mtime(root: Path) -> int:
    """The newest stored week's mtime, 0 with none: the input stamp a
    finalize job records so 'already tried on exactly these inputs' is
    answerable without recomputing anything."""
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
                    ensemble_weights: dict | str | None = None,
                    phase_cb=None, force: bool = False) -> dict:
    """Everything the results page needs, computed once so the page never
    has to: score the season (atomic scores.json), build the national
    aggregate cache, and warm every week's playback payload and stats.
    Returns the measured seconds per phase; `phase_cb(phase)` is called at
    each transition (the preparing state's status line).

    Scoring is skipped when scores.json is already current and scoreable
    (an aggregate-only staleness must not pay the full rescore) unless
    `force` asks for it -- the explicit-rescore path.

    Order matters: the aggregate's and the payloads' cache keys both cover
    scores.json's mtime, so scoring must land first or the warm work would
    invalidate itself. Playback warming failures are recorded but never
    fatal: a week that cannot warm simply builds on first view, exactly as
    before."""
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
        df = score_season(root, season, ensemble_weights=ensemble_weights)
        # write beside, then replace: a concurrent viewer may never see (or
        # race) a half-written scores.json -- the completion path's own rule
        tmp = root / "scores.json.tmp"
        df.to_json(tmp)
        os.replace(tmp, root / "scores.json")
        seconds["scoring"] = round(time.monotonic() - t, 1)

    t = _phase("building national aggregate")
    try:
        national_aggregate(root, ensemble_weights=ensemble_weights)
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

    # storage hygiene at run completion: sweep the whole tree for completed
    # weeks still carrying their fit intermediates (weeks fitted before the
    # per-week prune existed, or whose prune failed). The reclaim module
    # refuses protected trees on its own, so finalizing a sealed or archived
    # view can never touch what it must not. Never fatal: a tree that cannot
    # be pruned is still a finished season.
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
    """Fold the finalize timing into run_meta.json, like the week timings:
    the record then states what the completion work cost, and the report
    surfaces can print it without re-deriving anything."""
    with _META_LOCK:
        m = read_meta(root)
        m["finalize_seconds"] = {k: float(v) for k, v in (seconds or {}).items()
                                 if isinstance(v, (int, float))}
        write_meta(root, m)


# --------------------------------------------------------------------------
# archived runs
#
# Resumability protects an overnight replay, but it becomes a trap the moment
# the user wants a genuinely clean run (an unseeded replication against an
# existing result, say). The escape is to move the season tree aside rather
# than overwrite it: an archived run keeps every file it had, stays viewable,
# and the fresh replay starts on an empty tree.
#
# An archive is a SIBLING of the live season under the same retro root,
# named <season>__archived_<UTC stamp>. That naming carries the season and
# the moment in the directory name itself, so the set of archives is
# discoverable with one glob and needs no index file to fall out of date.
# --------------------------------------------------------------------------

ARCHIVE_SEP = "__archived_"

#: <8 digit date>T<6 digit time>Z, with a -N suffix only when two archives of
#: the same season land inside one second. Everything reaching the filesystem
#: is checked against this, so an archive identifier from a URL can never
#: name a path outside the retro root.
_STAMP_RE = re.compile(r"\d{8}T\d{6}Z(-\d+)?")

#: headline relWIS is read from scores.json, which is large; keep the last
#: value per root, invalidated by the file's mtime and the week count.
#:
#: BOUNDED. Each entry is two floats and an int, so this cache is not the
#: memory story its neighbour _SCORES_FRAMES is; what it did do was grow one
#: entry per season root forever, and roots accumulate (every archived replay
#: adds one, and /runs asks for a summary of each). Least-recently-used, with
#: a cap generous enough that no realistic archive listing evicts a row it is
#: about to re-read: a run page shows tens of runs, not hundreds.
_SUMMARY_CACHE_MAX = 128
_SUMMARY_CACHE: "OrderedDict" = OrderedDict()


def utc_stamp(now: float | None = None) -> str:
    """The archive naming stamp: UTC, second resolution, sortable."""
    t = datetime.fromtimestamp(now if now is not None else _now(),
                               tz=timezone.utc)
    return t.strftime("%Y%m%dT%H%M%SZ")


def valid_stamp(stamp: str) -> bool:
    return bool(_STAMP_RE.fullmatch(stamp or ""))


def stamp_human(stamp: str) -> str:
    """'20260821T143012Z' -> '2026-08-21 14:30 UTC'. An unparseable stamp is
    returned unchanged rather than guessed at."""
    try:
        base = (stamp or "").split("-")[0]
        t = datetime.strptime(base, "%Y%m%dT%H%M%SZ")
        return t.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return stamp or ""


def utc_human(epoch: float | None) -> str:
    """A run record's epoch seconds as a readable UTC moment, or ''."""
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError):
        return ""


def archive_dir(retro_root: Path, season: str, stamp: str) -> Path:
    return Path(retro_root) / f"{season}{ARCHIVE_SEP}{stamp}"


def archive_stamp_of(name: str, season: str) -> str:
    """The stamp inside an archive directory name, or '' when the name is not
    an archive of this season."""
    prefix = f"{season}{ARCHIVE_SEP}"
    if not name.startswith(prefix):
        return ""
    stamp = name[len(prefix):]
    return stamp if valid_stamp(stamp) else ""


def list_archive_dirs(retro_root: Path, season: str) -> list:
    """Archive directories for one season, newest first. The stamp sorts
    lexicographically in time order, so reversing the sort is the ordering."""
    root = Path(retro_root)
    if not root.is_dir():
        return []
    out = []
    for p in root.iterdir():
        if not archive_stamp_of(p.name, season):
            continue
        if p.is_dir() or p.is_symlink():
            out.append(p)
    return sorted(out, key=lambda p: p.name, reverse=True)


def _headline_rel(scores_path: Path, model: str = "ensemble"):
    """Pooled relWIS for one model from a stored scores.json, or None when
    the file is absent, empty, or does not cover the model."""
    try:
        df = pd.read_json(scores_path)
        if df.empty or "model" not in df.columns:
            return None
        g = df[df.model == model]
        base = float(g.base_wis.sum()) if len(g) else 0.0
        return float(g.wis.sum() / base) if base else None
    except Exception:
        return None


def run_summary(root: Path) -> dict:
    """What one run -- live or archived -- amounts to: completed weeks, wall
    time, when it ran, whether it was scored, and its headline relWIS.

    Every field degrades to None or 0 rather than raising: a season tree may
    be missing, half-written, or predate the run record entirely, and none of
    those may take a page down."""
    root = Path(root)
    meta = read_meta(root)
    t = timing(meta) if meta else {}
    weeks = _weeks_on_disk(root) if root.is_dir() else 0
    sf = root / "scores.json"
    scored = sf.is_file()
    key = ((sf.stat().st_mtime if scored else None), weeks)
    hit = _SUMMARY_CACHE.get(str(root))
    if hit is not None and hit[0] == key:
        rel = hit[1]
        _SUMMARY_CACHE.move_to_end(str(root))     # least-recently-used
    else:
        rel = _headline_rel(sf) if scored else None
        _SUMMARY_CACHE[str(root)] = (key, rel)
        _SUMMARY_CACHE.move_to_end(str(root))
        while len(_SUMMARY_CACHE) > _SUMMARY_CACHE_MAX:
            _SUMMARY_CACHE.popitem(last=False)
    return {"weeks": weeks,
            "elapsed_s": t.get("elapsed_s"),
            "started_utc": t.get("started_utc"),
            "finished_utc": t.get("finished_utc"),
            "status": effective_status(meta) if meta else "",
            "scored": scored,
            "headline_rel": rel}


def dir_size(path: Path) -> int:
    """Bytes held under a tree. Symlinks are measured as links, never
    followed: a season parked on another volume must not report that
    volume's size, and must not be walked."""
    p = Path(path)
    if p.is_symlink() or not p.exists():
        return 0
    total = 0
    for dirpath, _dirnames, filenames in os.walk(p, followlinks=False):
        for f in filenames:
            try:
                total += os.lstat(os.path.join(dirpath, f)).st_size
            except OSError:
                pass                       # a file vanishing mid-walk is fine
    return total


def human_bytes(n: int) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def archive_run(retro_root: Path, season: str, stamp: str | None = None,
                now: float | None = None) -> Path:
    """Move <retro_root>/<season> aside to <season>__archived_<stamp>/.

    A same-parent os.rename, deliberately: it is atomic and instant, so the
    tree is either wholly live or wholly archived and never both. A copy
    would be the obvious alternative and the wrong one -- copying a 12 GB
    season can half-fill the volume and leave two partial trees behind.

    A failure raises with the original left exactly where it was; the caller
    must report it rather than start a replay over an unarchived season."""
    src = Path(retro_root) / season
    if not (src.is_dir() or src.is_symlink()):
        raise FileNotFoundError(f"no season tree to archive at {src}")
    stamp = stamp or utc_stamp(now)
    dst = archive_dir(retro_root, season, stamp)
    n = 1
    while dst.exists() or dst.is_symlink():       # same-second collision
        n += 1
        dst = archive_dir(retro_root, season, f"{stamp}-{n}")
    os.rename(src, dst)
    _SUMMARY_CACHE.pop(str(src), None)
    return dst


def delete_tree(path: Path) -> None:
    """Remove a season or archive tree permanently.

    A symlinked tree (a season parked on another volume) loses its link and
    nothing else: shutil.rmtree refuses a symlink outright, and following one
    would delete data this application does not own."""
    p = Path(path)
    _SUMMARY_CACHE.pop(str(p), None)
    if p.is_symlink():
        p.unlink()
        return
    shutil.rmtree(p)
