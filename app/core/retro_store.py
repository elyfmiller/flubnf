"""The season replay's samples store (app/core/retro.py's storage layer).

Every stored-week read/write goes through these helpers, so samples.json and
samples.json.gz are indistinguishable downstream. New weeks are gzipped
(~3.7x); compress_samples_file migrates old ones keeping the mtime, so
caches keyed on it stay valid. The quantile sidecar (QUANTILES_NAME) rides
beside the draws for playback, the report and the scorer.

A week of an experiment replayed on the runner may be stored lean: its
forecasting samples dropped once its sidecar was checked against them
(experiments.drop_samples), with the marker DROPPED_NAME beside the
sidecar. The readers below count such a week as stored and read its
sidecar alone; a tree with no marker reads exactly as before.

Sections: paths (SAMPLES_JSON, _week_dir, samples_file, week_dropped,
season_sample_files, season_week_files) | draws (read_samples,
read_week_samples, write_week_samples) | quantile sidecar
(member_quantiles, filter_quantiles, write/read_week_quantiles,
week_member_quantiles) | migration (compress_samples_file) | week_done |
the season's parsed scores (scores_frame).
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import sys
import threading
from collections import OrderedDict
from contextlib import nullcontext
from pathlib import Path

from app.core import ensemble as ens
from app.core import horizons as hz


def _week_dir(root: Path, asof: str) -> Path:
    return root / "weeks" / asof


def writing_into(root: Path):
    """Around a cache write into a season tree: a context that yields
    whether the write may go ahead. The console's delete or move of a tree
    marks it first (app/ui/retro_prep._writing_into, which answers here):
    nothing is written into a marked tree, and no delete starts on a tree
    while a write into it is under way. The mark lives in the console's
    process alone, so where the console is not loaded (the command line,
    the site build) no tree is marked and every write goes ahead."""
    rp = sys.modules.get("app.ui.retro_prep")
    return rp._writing_into(root) if rp is not None else nullcontext(True)

SAMPLES_JSON = "samples.json"
SAMPLES_GZ = "samples.json.gz"
#: per-week quantile sidecar (each member's 23 levels, a few hundred KB beside
#: ~140 MB of draws): playback, report and scorer read it instead of parsing
#: draws. Written on store, backfilled on first read. The national aggregate
#: still reads the draws.
QUANTILES_NAME = "quantiles.json"
#: the Liu-West filter alone, before the Oracle step: scored beside the
#: shipped member (pf) so the step's effect shows. Its quantiles come from
#: the week's oracle.json (quantiles.null, app/core/oracle.py), or from a
#: record that stores the filter's samples under this key.
FILTER_MEMBER = "pf_filter"
#: the Oracle step's provenance file (app/core/oracle.PROVENANCE_NAME)
ORACLE_NAME = "oracle.json"
#: the marker of a week stored lean (experiments.drop_samples): the bytes
#: of the samples dropped and when, {"bytes": n, "utc": "...Z"}
DROPPED_NAME = "samples.dropped.json"


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


def week_dropped(wd: Path) -> bool:
    """A week stored lean: its forecasting samples dropped once its quantile
    sidecar was checked against them (experiments.drop_samples); the marker
    and the sidecar both regular files."""
    wd = Path(wd)
    return (wd / DROPPED_NAME).is_file() and (wd / QUANTILES_NAME).is_file()


def _lean(wd: Path) -> bool:
    """A week read from its sidecar alone: the marker without samples. The
    samples win over the marker (a drop killed between its two writes
    leaves a week that reads as before)."""
    return samples_file(wd) is None and week_dropped(wd)


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


def season_week_files(root: Path) -> list:
    """One file per stored week, ascending: its samples file, or the sidecar
    of a week stored lean. season_sample_files is unchanged (its callers
    parse draws)."""
    weeks = Path(root) / "weeks"
    if not weeks.is_dir():
        return []
    out = []
    try:
        for wd in sorted(weeks.iterdir()):
            p = samples_file(wd)
            if p is None and week_dropped(wd):
                p = wd / QUANTILES_NAME
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
    return hz.record_to_canonical(json.loads(fp.read_text(encoding="utf-8")))


def read_week_samples(root: Path, asof: str) -> dict:
    """One stored week, in CANONICAL horizons (the file keeps the stored
    convention; see app.core.horizons)."""
    fp = week_samples_path(root, asof)
    if fp is None:
        raise FileNotFoundError(
            f"no stored samples for week {asof} under {root}")
    return read_samples(fp)          # already canonical


#: the text slice write_json_text hands the file at a time (4 MiB): the
#: encoded record is held once, never a second full-size bytes copy
WRITE_SLICE = 1 << 22


def write_json_text(fh, obj) -> None:
    """json.dump(obj, fh), the same text, through the C encoder: one
    json.dumps (json.dump's pure-Python encoder takes about twice as long
    on a week's draws), written in WRITE_SLICE pieces."""
    s = json.dumps(obj)
    for i in range(0, len(s), WRITE_SLICE):
        fh.write(s[i:i + WRITE_SLICE])


def write_week_samples(wd: Path, obj: dict) -> Path:
    """Store a completed week's samples, gzipped and atomic, retiring any
    plain-JSON leftover. The quantile sidecar is best effort."""
    wd = Path(wd)
    fp = wd / SAMPLES_GZ
    tmp = wd / (SAMPLES_GZ + ".tmp")
    # canonical in memory, stored convention on disk
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
        write_json_text(f, hz.record_to_stored(obj))
    os.replace(tmp, fp)
    (wd / SAMPLES_JSON).unlink(missing_ok=True)
    try:
        write_week_quantiles(wd, member_quantiles(obj, wd))
    except Exception:
        pass
    return fp


def member_quantiles(d: dict, wd: Path | None = None) -> dict:
    """{member: {location: {"0".."3": {level: value}}}} from one week's
    stored record: the sample-shaped members (pf, pf2s) through the member
    quantile formula, the analogue's stored quantiles with float levels.
    A week replayed by the Groundhog alone (engine "analogue") stores no
    pf block and yields no pf member. With the week folder `wd`, the
    Liu-West filter alone (FILTER_MEMBER) joins from its oracle.json when
    the Oracle step ran there (filter_quantiles)."""
    out = {}
    for m in ("pf", "pf2s", FILTER_MEMBER):
        if m in d:
            out[m] = {loc: ens.member_quantiles_from_samples(s)
                      for loc, s in d[m].items()}
    if "analogue" in d:
        out["analogue"] = {loc: {h: {float(k): float(v) for k, v in q.items()}
                                 for h, q in qs.items()}
                           for loc, qs in d["analogue"].items()}
    if wd is not None and "pf" in out and FILTER_MEMBER not in out:
        fq = filter_quantiles(wd)
        if fq:
            out[FILTER_MEMBER] = fq
    return out


#: parsed oracle.json null blocks keyed by (path, mtime_ns, size); a few
#: MB each, read once per week per process
_FILTER_CACHE: dict = {}


def filter_quantiles(wd: Path) -> dict | None:
    """The Liu-West filter's own quantiles for one week, before the Oracle
    step: oracle.json's quantiles.null, {location: {"0".."3": {level:
    value}}}, with the output floor the analogue gets (floor.floor_quantiles),
    so the filter is scored as a submission would carry it. None when the
    step did not run there (no file, "applied": false, a sealed record).
    The fitted US is in the block for a week stored since addendum A3,
    when the step covers it; before A3 the step left US outside, so the
    block lacks it and that week's US pf is already the filter alone
    (us_national.us_step_week tells the two apart)."""
    fp = Path(wd) / ORACLE_NAME
    try:
        st = fp.stat()
    except OSError:
        return None
    key = (str(fp), st.st_mtime_ns, st.st_size)
    if key in _FILTER_CACHE:
        return _FILTER_CACHE[key]
    out = None
    try:
        prov = json.loads(fp.read_text(encoding="utf-8"))
        qb = (prov.get("quantiles") or {}) if prov.get("applied") else {}
        levels = [float(L) for L in qb.get("levels") or ()]
        null = qb.get("null") or {}
        if levels and null:
            from app.core.floor import floor_quantiles
            out = {}
            for loc, by_h in null.items():
                qs = {h: dict(zip(levels, (float(v) for v in e["unrounded"])))
                      for h, e in (by_h or {}).items()
                      if h in hz.HORIZONS and isinstance(e, dict)
                      and e.get("unrounded")
                      and len(e["unrounded"]) == len(levels)}
                if qs:
                    out[loc] = floor_quantiles(qs)
            out = out or None
    except Exception:
        out = None
    _FILTER_CACHE[key] = out
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
         for m, locs in hz.quantiles_to_stored(mq).items()}), encoding="utf-8")
    os.replace(tmp, fp)
    return fp


def read_week_quantiles(wd: Path) -> dict | None:
    """The sidecar as member_quantiles would have returned it, or None when
    it is absent, unreadable, or older than the samples it describes. A
    week stored lean has no samples to be older than: its sidecar is read
    whatever its mtime."""
    wd = Path(wd)
    fp = wd / QUANTILES_NAME
    sp = samples_file(wd)
    if not fp.is_file():
        return None
    if sp is None:
        if not week_dropped(wd):
            return None
    elif fp.stat().st_mtime < sp.stat().st_mtime:
        return None
    try:
        raw = json.loads(fp.read_text(encoding="utf-8"))
        return hz.quantiles_to_canonical(
            {m: {loc: {h: {float(L): float(v) for L, v in q.items()}
                       for h, q in qs.items()}
                 for loc, qs in locs.items()}
             for m, locs in raw.items()})
    except Exception:
        return None


def week_member_quantiles(root: Path, asof: str) -> dict:
    """The members' quantiles for one stored week: the sidecar when it is
    current, else computed from the samples (and the week's oracle.json)
    and written for next time, unless a delete or a move holds the tree
    (writing_into). A week stored lean is its sidecar as it
    is, never rebuilt and never rewritten: FileNotFoundError when the
    sidecar cannot be read."""
    wd = _week_dir(root, asof)
    mq = read_week_quantiles(wd)
    # a sidecar written before the Liu-West filter was scored lacks it:
    # rebuilt once when the week's oracle.json carries it (a lean week's
    # never is; _lean is asked last, so a current sidecar costs no stat)
    if mq is not None and (FILTER_MEMBER in mq or "pf" not in mq
                           or _lean(wd) or not filter_quantiles(wd)):
        return mq
    if _lean(wd):
        raise FileNotFoundError(f"{asof}: its forecasting samples were "
                                "dropped and its quantiles file cannot be "
                                "read")
    mq = member_quantiles(read_week_samples(root, asof), wd)
    try:
        with writing_into(root) as ok:
            if ok:
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
    """A stored week: its samples file, or the marker of a week stored lean
    (week_dropped)."""
    return (week_samples_path(root, asof) is not None
            or week_dropped(_week_dir(root, asof)))


# ------------------------------------------------- the season's parsed scores

#: LRU of parsed scores.json frames keyed by (path, mtime_ns, size), so a
#: rescore invalidates by construction. ~50 MB per frame; cap 3 holds the
#: three sealed seasons without eviction while bounding archive sweeps.
#: One store for the season page (app/ui/retro_prep._scores_df, which
#: aliases these names) and the season player (playback._season_scores).
SCORES_FRAMES_MAX = 3
SCORES_FRAMES: "OrderedDict" = OrderedDict()
#: every read and write of SCORES_FRAMES: request threads, the finalize
#: job and the season report share it (an unlocked hit could lose its key
#: to another thread's eviction between get and move_to_end)
_SCORES_FRAMES_LOCK = threading.Lock()


def scores_frame(root: Path):
    """Parsed scores.json for this root (None if missing or unparseable),
    one pd.read_json per file content. The frame is SHARED read-only:
    callers filter into copies and never mutate it."""
    import pandas as pd
    sf = Path(root) / "scores.json"
    try:
        st = sf.stat()
    except OSError:
        return None
    key = (str(sf), st.st_mtime_ns, st.st_size)
    with _SCORES_FRAMES_LOCK:
        hit = SCORES_FRAMES.get(key)
        if hit is not None:
            SCORES_FRAMES.move_to_end(key)      # least-recently-used ordering
            return hit
    try:
        df = pd.read_json(sf)
    except Exception:
        return None
    try:
        st2 = sf.stat()
    except OSError:
        return df
    if (st2.st_mtime_ns, st2.st_size) != key[1:]:
        return df          # replaced while it was read: serve, do not cache
    with _SCORES_FRAMES_LOCK:
        hit = SCORES_FRAMES.get(key)
        if hit is not None:                     # a racing reader got there
            SCORES_FRAMES.move_to_end(key)
            return hit
        SCORES_FRAMES[key] = df
        while len(SCORES_FRAMES) > SCORES_FRAMES_MAX:
            SCORES_FRAMES.popitem(last=False)   # evict one, never flush the lot
    return df
