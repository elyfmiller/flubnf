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
  * CONTROLLABLE: STOP and PAUSE are files in the season root, polled between
    weeks -- the same flag mechanism the PF engine uses for console runs. A
    stop finishes the current week, so no half-week is wasted or corrupted.
  * TIMED: run_meta.json in the season root records wall time as the replay
    goes, accumulating across resumes rather than restarting the clock.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
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


def week_done(root: Path, asof: str) -> bool:
    return (_week_dir(root, asof) / "samples.json").is_file()


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
    """Raised inside run_season when a stop was requested. The current week
    is already checkpointed; completed weeks are kept and a later replay
    resumes from there."""


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
    """Ask the worker to finish its current week and exit. Clears PAUSE too,
    so a paused worker wakes up and stops instead of holding forever.

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
    return len(list((Path(root) / "weeks").glob("*/samples.json")))


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
        ws = dict(m.get("week_seconds") or {})
        ws[asof] = round(float(seconds), 3)
        m["week_seconds"] = ws
        m["weeks_completed"] = _weeks_on_disk(root)
        m["heartbeat_utc"] = now
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


def run_week(root: Path, season: str, asof: str, locations: list,
             replicates: int = 3, particles: int = 10_000,
             width: int = 4) -> dict:
    """One submission day: PF (sharded) + analogue; store samples+quantiles."""
    wd = _week_dir(root, asof)
    if week_done(root, asof):
        return json.loads((wd / "samples.json").read_text())
    wd.mkdir(parents=True, exist_ok=True)
    spec = RunSpec(engine="retro", forecast_date=asof, locations=locations,
                   season_start=season_bounds(season)[0],
                   replicates=replicates, particles=particles)
    cells = pf_engine.prepare(spec, wd)
    # shard cells across width runner subprocesses
    shards = [cells[i::width] for i in range(width) if cells[i::width]]
    procs = []
    for i, shard in enumerate(shards):
        sj = wd / f"cells_{i}.json"
        sj.write_text(json.dumps(shard))
        runner = wd / f"runner_{i}.py"
        runner.write_text(pf_engine._RUNNER.format(
            pybnf_path=str(pf_engine.PYBNF_PF), cells_json=str(sj),
            out_json=str(wd / f"status_{i}.json")))
        # started at reduced priority so the console stays responsive while a
        # season replays: see app/core/proc.py for the trade and its cost
        procs.append(subprocess.Popen(proc_mod.low_priority_cmd(
                     [str(pf_engine.PY_ENGINE
                      if hasattr(pf_engine, 'PY_ENGINE') else pf_engine.PY310),
                      str(runner)]), stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL))
    for p in procs:
        p.wait(timeout=7200)
    pf_samples = pf_engine.collect(wd)
    an_q = an_engine.run(spec)
    out = {"asof": asof,
           "pf": pf_samples,
           "analogue": {loc: {h: {str(k): v for k, v in q.items()}
                              for h, q in qs.items()}
                        for loc, qs in an_q.items()}}
    (wd / "samples.json").write_text(json.dumps(out))
    return out


def run_season(root: Path, season: str, locations: list, replicates=3,
               particles=10_000, width=4, progress=None,
               settings: dict | None = None) -> list:
    """Replay a season week by week, recording timing and honouring the STOP
    and PAUSE flags between weeks.

    Control points sit BETWEEN weeks by design: a stop lands only once the
    current week's checkpoint is on disk, so no half-week is wasted or
    corrupted, and the next replay resumes exactly where this one left off.
    A pause holds inside this call, keeping the process (and the caller's
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
            t0 = _now()
            try:
                run_week(root, season, asof, locations, replicates, particles,
                         width)
                done.append(asof)
            except Exception as e:              # a bad week never kills the season
                (root / "failures.log").open("a").write(f"{asof}: {e}\n")
            _record_week(root, asof, _now() - t0)
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


def score_season(root: Path, season: str, ensemble_weights: dict | None = None) -> pd.DataFrame:
    """Score every stored week vs settled truth. `ensemble_weights` must be
    LOSO for this season (never fitted on it)."""
    from app.core.scoring import _baseline_cells, load_truth
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
    from flubnf.wis import wis as wis_fn
    from datetime import timedelta
    truth, n2f = load_truth()
    rows = []
    for wk in sorted((root / "weeks").glob("*/samples.json")):
        d = json.loads(wk.read_text())
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
#: value per root, invalidated by the file's mtime and the week count
_SUMMARY_CACHE: dict = {}


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
    else:
        rel = _headline_rel(sf) if scored else None
        _SUMMARY_CACHE[str(root)] = (key, rel)
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
