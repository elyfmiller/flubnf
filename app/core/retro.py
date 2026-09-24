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
    Older scores.json files may carry retired "ensemble" rows.
  * PF cells sharded across N runner subprocesses (entry-point files, never
    stdin: the macOS spawn rule).
  * CONTROLLABLE: STOP and PAUSE files in the season root are polled between
    individual fits; only fits in flight finish, and every finished fit is
    checkpointed in cells_done/, so a stopped week refits only what never ran.
  * TIMED: run_meta.json accumulates wall time across resumes.
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

from app.core.data import ARCHIVE                     # noqa: E402
from app.core.engines import analogue as an_engine    # noqa: E402
from app.core.engines import pf as pf_engine          # noqa: E402
from app.core import horizons as hz
from app.core import oracle as oracle_mod             # noqa: E402
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
# the samples store: every stored-week read/write goes through these helpers,
# so samples.json and samples.json.gz are indistinguishable downstream. New
# weeks are gzipped (~3.7x); compress_samples_file migrates old ones keeping
# the mtime, so caches keyed on it stay valid.
# --------------------------------------------------------------------------

SAMPLES_JSON = "samples.json"
SAMPLES_GZ = "samples.json.gz"
#: per-week quantile sidecar (each member's 23 levels, a few hundred KB beside
#: ~140 MB of draws): playback, report and scorer read it instead of parsing
#: draws. Written on store, backfilled on first read. The national aggregate
#: still reads the draws.
QUANTILES_NAME = "quantiles.json"


def samples_file(wd: Path) -> Path | None:
    """The week's stored samples file (plain or gzip), or None when the week
    is incomplete. Plain wins when both exist (an interrupted migration)."""
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
    """Parse one stored samples file (plain or gzip) into CANONICAL horizons.
    The conversion lives at the parser because other callers (the national
    aggregate, console pages) read files directly."""
    fp = Path(fp)
    if fp.name.endswith(".gz"):
        with gzip.open(fp, "rt", encoding="utf-8") as f:
            return hz.record_to_canonical(json.load(f))
    return hz.record_to_canonical(json.loads(fp.read_text()))


def read_week_samples(root: Path, asof: str) -> dict:
    """One stored week, in CANONICAL horizons (the file keeps the stored
    convention; see app.core.horizons)."""
    fp = week_samples_path(root, asof)
    if fp is None:
        raise FileNotFoundError(
            f"no stored samples for week {asof} under {root}")
    return read_samples(fp)          # already canonical


def write_week_samples(wd: Path, obj: dict) -> Path:
    """Store a completed week's samples, gzipped and atomic, retiring any
    plain-JSON leftover. The quantile sidecar is best effort."""
    wd = Path(wd)
    fp = wd / SAMPLES_GZ
    tmp = wd / (SAMPLES_GZ + ".tmp")
    # canonical in memory, stored convention on disk
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump(hz.record_to_stored(obj), f)
    os.replace(tmp, fp)
    (wd / SAMPLES_JSON).unlink(missing_ok=True)
    try:
        write_week_quantiles(wd, member_quantiles(obj))
    except Exception:
        pass
    return fp


def member_quantiles(d: dict) -> dict:
    """{member: {location: {"0".."3": {level: value}}}} from one week's
    stored record: the sample-shaped members (pf, pf2s) through the member
    quantile formula, the analogue's stored quantiles with float levels.
    A week replayed by the Groundhog alone (engine "analogue") stores no
    pf block and yields no pf member."""
    out = {}
    for m in ("pf", "pf2s"):
        if m in d:
            out[m] = {loc: ens.member_quantiles_from_samples(s)
                      for loc, s in d[m].items()}
    if "analogue" in d:
        out["analogue"] = {loc: {h: {float(k): float(v) for k, v in q.items()}
                                 for h, q in qs.items()}
                           for loc, qs in d["analogue"].items()}
    return out


def write_week_quantiles(wd: Path, mq: dict) -> Path:
    """The sidecar, atomically. Levels become strings on disk (JSON keys)
    and read back as the same floats: repr round-trips."""
    wd = Path(wd)
    fp = wd / QUANTILES_NAME
    tmp = wd / (QUANTILES_NAME + ".tmp")
    tmp.write_text(json.dumps(
        {m: {loc: {h: {repr(float(L)): v for L, v in q.items()}
                   for h, q in qs.items()}
             for loc, qs in locs.items()}
         for m, locs in hz.quantiles_to_stored(mq).items()}))
    os.replace(tmp, fp)
    return fp


def read_week_quantiles(wd: Path) -> dict | None:
    """The sidecar as member_quantiles would have returned it, or None when
    it is absent, unreadable, or older than the samples it describes."""
    wd = Path(wd)
    fp = wd / QUANTILES_NAME
    sp = samples_file(wd)
    if not fp.is_file() or sp is None or fp.stat().st_mtime < sp.stat().st_mtime:
        return None
    try:
        raw = json.loads(fp.read_text())
        return hz.quantiles_to_canonical(
            {m: {loc: {h: {float(L): float(v) for L, v in q.items()}
                       for h, q in qs.items()}
                 for loc, qs in locs.items()}
             for m, locs in raw.items()})
    except Exception:
        return None


def week_member_quantiles(root: Path, asof: str) -> dict:
    """The members' quantiles for one stored week: the sidecar when it is
    current, else computed from the samples and written for next time."""
    wd = _week_dir(root, asof)
    mq = read_week_quantiles(wd)
    if mq is not None:
        return mq
    mq = member_quantiles(read_week_samples(root, asof))
    try:
        write_week_quantiles(wd, mq)
    except Exception:
        pass
    return mq


def compress_samples_file(fp: Path) -> Path:
    """Migrate one stored week to gzip, preserving its mtime so every cache
    keyed on it stays valid. Crash-safe: the plain file stays the record
    until it is retired."""
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
        d = json.loads(meta_path(root).read_text())
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def write_meta(root: Path, meta: dict) -> None:
    """Atomic: write beside, then replace."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    tmp = meta_path(root).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(meta, sort_keys=True))
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


#: labels for the retro form's scopes, when a replay recorded no location list
SCOPE_LABELS = {"panel6": "6-state panel", "all": "all 52 jurisdictions",
                "custom": "custom selection"}


def settings_summary(meta: dict) -> list:
    """The settings that produced a replay, as (label, value) pairs, from
    its run record; [] when none were recorded (the sealed runs)."""
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
    """The /retro/run form fields that resume a replay with its recorded
    settings (one-click resume). A recorded scope passes through; a bare
    location list resubmits as a custom selection. None when the record
    cannot name a scope (then only the form path is offered)."""
    s = (meta or {}).get("settings")
    if not isinstance(s, dict) or not s:
        return None
    season = str(s.get("season") or (meta or {}).get("season") or "")
    if not season:
        return None
    locs = [str(l) for l in (s.get("locations") or [])]
    scope = str(s.get("scope") or "")
    out = {"season": season, "mode": "resume"}
    # national is posted explicitly from the run's own list, not today's
    # default: a 52-jurisdiction replay must never resume as 53
    from app.core.us_national import is_us as _is_us
    out["national"] = "1" if (any(_is_us(l) for l in locs) if locs
                              else bool(s.get("national"))) else "0"
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
    """Open (or reopen) the season's run record; a resume keeps started_utc
    and elapsed_s. Settings are recorded at the start (a resume records
    those it resumes with), so even an unfinished run says what produced it."""
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
                m = json.loads(p.read_text())
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
    tmp.write_text(json.dumps({"key": key, "status": status}))
    os.replace(tmp, d / f"{key}.json")


def _prepare_week(root: Path, asof: str, spec, manifest: dict) -> list:
    """The week's prepared cells, reusing a stopped segment's preparation
    (and its fit markers) when the manifest matches exactly; anything else
    rebuilds the week from scratch and drops its banked partial seconds."""
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
    """One reduced-priority runner subprocess per shard (app/core/proc.py).
    Split out so tests can fake fits; returns objects with poll() and kill()."""
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


#: "pf": the filter beside the analogue (hours per season); "analogue": the
#: Groundhog alone (minutes, no engine install)
ENGINES = ("pf", "analogue")


def run_week(root: Path, season: str, asof: str, locations: list,
             replicates: int = 3, particles: int = 10_000,
             width: int = pf_engine.DEFAULT_SHARD_WIDTH,
             drop_same_day: bool = False,
             extra: dict | None = None, engine: str = "pf") -> dict:
    """One submission day: PF (sharded) + analogue; store samples+quantiles.

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
    season_start = str((extra or {}).get("season_start") or season_bounds(season)[0])
    jitter = float((extra or {}).get("jitter") or RunSpec.jitter)
    spec = RunSpec(engine="retro", forecast_date=asof, locations=locations,
                   season_start=season_start, jitter=jitter,
                   replicates=replicates, particles=particles,
                   drop_same_day=drop_same_day, extra=dict(extra or {}))
    manifest = {"locations": [str(l) for l in locations],
                "replicates": int(replicates), "particles": int(particles),
                "season_start": spec.season_start,
                "drop_same_day": bool(drop_same_day)}
    if extra:
        manifest["extra"] = dict(extra)   # absent when empty (old weeks match)
    _check_stop(root)         # a standing flag must not even prepare a week
    hold_while_paused(root)
    if engine == "analogue":
        # the analogue alone; the manifest still records what produced the week
        manifest["engine"] = "analogue"
        wd.mkdir(parents=True, exist_ok=True)
        (wd / "manifest.json").write_text(json.dumps(manifest, indent=1))
        an_q = an_engine.run(spec)
        out = {"asof": asof,
               "analogue": {loc: {h: {str(k): v for k, v in q.items()}
                                  for h, q in qs.items()}
                            for loc, qs in an_q.items()}}
        write_week_samples(wd, out)
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
        (Path(root) / "failures.log").open("a").write(
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
        stored = {"pf": member}
    else:
        oracle_mod.write_not_applied(
            wd, asof, "the replay asked for the plain filter (oracle = none)")
        stored = {"pf": pf_samples}
    an_q = an_engine.run(spec)
    out = {"asof": asof,
           **stored,
           "analogue": {loc: {h: {str(k): v for k, v in q.items()}
                              for h, q in qs.items()}
                        for loc, qs in an_q.items()}}
    if failed:
        out["pf_failures"] = failed
    write_week_samples(wd, out)
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
            except SeasonStopped:
                # bank the segment's seconds; no entry for an incomplete week
                _record_partial(root, asof, elapsed_now(read_meta(root)) - e0)
                raise
            except Exception as e:              # a bad week never kills the season
                (root / "failures.log").open("a").write(f"{asof}: {e}\n")
            if progress:
                progress(asof)
    except SeasonStopped:
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


def score_season(root: Path, season: str) -> pd.DataFrame:
    """Score every stored week vs settled truth: one row per (member,
    location, as-of, horizon), pf and analogue. Nothing is blended (older
    files' "ensemble" rows are not reproduced by a rescore)."""
    from app.core.scoring import _baseline_cells, load_truth
    from flubnf.wis import wis as wis_fn
    from datetime import timedelta
    truth, n2f = load_truth()
    rows = []
    for wk in season_sample_files(root):
        asof = wk.parent.name; T = pd.Timestamp(asof)
        mq = week_member_quantiles(root, asof)
        pf_all, an_all = mq.get("pf", {}), mq.get("analogue", {})
        for loc in set(pf_all) | set(an_all):
            fips = n2f.get(loc)
            if not fips:
                continue
            for model, qs in (("pf", pf_all.get(loc, {})),
                              ("analogue", an_all.get(loc, {}))):
                for h in hz.HORIZONS:
                    q = qs.get(h)
                    if not q:
                        continue
                    # canonical horizon h is h+1 weeks past the as-of
                    actual = truth.get(
                        (fips, T + timedelta(days=7 * (int(h) + 1))))
                    if actual is None or actual <= 0 or q[0.5] <= 0:
                        continue
                    try:
                        w = float(wis_fn(q, actual).wis)
                    except Exception:
                        continue
                    rows.append({"model": model, "location": loc, "fips": fips,
                                 "asof": asof, "horizon": int(h), "wis": w})
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


#: bump when the aggregate's construction or cached shape changes
#: (v2: a fitted US block is excluded from the sum; v3: no blend row)
NATIONAL_CACHE_V = 3

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
    score_season (same guards and baseline). Expensive, so cached in
    playback_cache/us_aggregate.json keyed by _national_cache_key; the
    last computation's cost rides along as `seconds`.
    """
    import zlib
    from datetime import timedelta
    from app.core.scoring import _baseline_cells, load_truth
    from app.core import us_national as usn
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
    from flubnf.wis import wis as wis_fn
    root = Path(root)
    wks = season_sample_files(root)
    if not wks:
        return None
    key = _national_cache_key(root)
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
                if not q:
                    continue
                actual = truth.get(
                    ("US", T + timedelta(days=7 * (int(h) + 1))))
                # the same degenerate-cell guards as score_season
                if actual is None or actual <= 0 or q[0.5] <= 0:
                    continue
                try:
                    w = float(wis_fn(q, actual).wis)
                except Exception:
                    continue
                rows.append((model, asof, int(h), w))
    bases = {}
    for asof in {r[1] for r in rows}:
        for k, v in _baseline_cells(asof, {"US"}, truth).items():
            bases[k] = v
    result = {"cells": {}, "weeks": len(wks)}
    for model in ("pf", "analogue"):
        cells = [(w, bases.get(("US", asof, h)))
                 for m, asof, h, w in rows if m == model]
        cells = [(w, b) for w, b in cells if b]
        if cells:
            result[model] = (sum(w for w, _ in cells)
                             / sum(b for _, b in cells))
            result["cells"][model] = len(cells)
    result["seconds"] = round(time.monotonic() - t0, 1)
    # atomic; an unwritable tree (sealed, read-only) just recomputes next time
    try:
        cf.parent.mkdir(parents=True, exist_ok=True)
        tmp = cf.with_name(cf.name + ".tmp")
        tmp.write_text(json.dumps({"key": key, "result": result}))
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
        cached = json.loads(cf.read_text())
        return cached.get("key") == _national_cache_key(root)
    except Exception:
        return False


def scores_current(root: Path) -> bool:
    """Whether scores.json exists, parses, and is newer than every stored
    week and the truth (see scores_scoreable for whether it has rows)."""
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
        pd.read_json(sf)
        return True
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


# --------------------------------------------------------------------------
# archived runs: a clean replay moves the season tree aside (kept, viewable)
# to a sibling <season>__archived_<UTC stamp>, discoverable by one glob with
# no index file.
# --------------------------------------------------------------------------

ARCHIVE_SEP = "__archived_"

#: <date>T<time>Z[-N for same-second collisions]; every identifier from a URL
#: is checked against this, so it can never name a path outside the retro root
_STAMP_RE = re.compile(r"\d{8}T\d{6}Z(-\d+)?")

#: headline relWIS per season root, keyed by scores.json mtime + week count;
#: LRU-bounded because archived roots accumulate
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


#: season headline order: the shipped two, then the retired blend (older files)
HEADLINE_MODELS = ("pf", "analogue", "ensemble")


def _headline_rels(scores_path: Path) -> dict:
    """{model: pooled relWIS} for every HEADLINE_MODELS entry a stored
    scores.json covers; {} when the file is absent or empty."""
    return {m: r for m in HEADLINE_MODELS
            if (r := _headline_rel(scores_path, m)) is not None}


def _headline_rel(scores_path: Path, model: str = "pf"):
    """Pooled relWIS for one model from a stored scores.json, or None when
    the file is absent, empty, or does not cover the model.

    Pooled, through us_national.pooled_frame (US rows never count)."""
    from app.core import us_national as usn
    try:
        df = pd.read_json(scores_path)
        if df.empty or "model" not in df.columns:
            return None
        df = usn.pooled_frame(df)
        g = df[df.model == model]
        base = float(g.base_wis.sum()) if len(g) else 0.0
        return float(g.wis.sum() / base) if base else None
    except Exception:
        return None


def run_summary(root: Path) -> dict:
    """What one run -- live or archived -- amounts to: completed weeks, wall
    time, when it ran, whether it was scored, and its headline relWIS per
    model (`headline_rels`, PF first; `headline_rel` is the first of them).

    Every field degrades to None or 0 rather than raising."""
    root = Path(root)
    meta = read_meta(root)
    t = timing(meta) if meta else {}
    weeks = _weeks_on_disk(root) if root.is_dir() else 0
    sf = root / "scores.json"
    scored = sf.is_file()
    key = ((sf.stat().st_mtime if scored else None), weeks)
    hit = _SUMMARY_CACHE.get(str(root))
    if hit is not None and hit[0] == key:
        rels = hit[1]
        _SUMMARY_CACHE.move_to_end(str(root))     # least-recently-used
    else:
        rels = _headline_rels(sf) if scored else {}
        _SUMMARY_CACHE[str(root)] = (key, rels)
        _SUMMARY_CACHE.move_to_end(str(root))
        while len(_SUMMARY_CACHE) > _SUMMARY_CACHE_MAX:
            _SUMMARY_CACHE.popitem(last=False)
    return {"weeks": weeks,
            "elapsed_s": t.get("elapsed_s"),
            "started_utc": t.get("started_utc"),
            "finished_utc": t.get("finished_utc"),
            "status": effective_status(meta) if meta else "",
            "scored": scored,
            # first in HEADLINE_MODELS order that the file covers
            "headline_rel": next(iter(rels.values()), None),
            "headline_rels": dict(rels)}


def dir_size(path: Path) -> int:
    """Bytes held under a tree. Symlinks are never followed (a season parked
    on another volume must not be walked)."""
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

    A same-parent os.rename: atomic and instant (a copy of a 12 GB season can
    half-fill the volume). A failure raises with the original untouched; the
    caller must not start a replay over it."""
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

    A symlinked tree loses only its link (never follow into data we do not own)."""
    p = Path(path)
    _SUMMARY_CACHE.pop(str(p), None)
    if p.is_symlink():
        p.unlink()
        return
    shutil.rmtree(p)
