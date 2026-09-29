"""The season replay's samples store (app/core/retro.py's storage layer).

Every stored-week read/write goes through these helpers, so samples.json and
samples.json.gz are indistinguishable downstream. New weeks are gzipped
(~3.7x); compress_samples_file migrates old ones keeping the mtime, so
caches keyed on it stay valid. The quantile sidecar (QUANTILES_NAME) rides
beside the draws for playback, the report and the scorer.

Sections: paths (SAMPLES_JSON, _week_dir, samples_file, season_sample_files)
| draws (read_samples, read_week_samples, write_week_samples) | quantile
sidecar (member_quantiles, write/read_week_quantiles, week_member_quantiles)
| migration (compress_samples_file) | week_done.
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
from pathlib import Path

from app.core import ensemble as ens
from app.core import horizons as hz


def _week_dir(root: Path, asof: str) -> Path:
    return root / "weeks" / asof

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
    return hz.record_to_canonical(json.loads(fp.read_text(encoding="utf-8")))


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
         for m, locs in hz.quantiles_to_stored(mq).items()}), encoding="utf-8")
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
