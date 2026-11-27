"""The weight screen's arms on the kept filter samples (no refit), and the
check that the live arm rebuilds the replay's own member.

    arms.py check <out> [--seasons ...] [--weeks ...]
        w 0.25, narrowing 0.7 from the kept inputs against the stored pf,
        every week: exact equality expected. Reads no truth.

member_for() is the arm: app.core.oracle.apply_week on the filter's own
samples with the arm's weight and narrowing written into the run's knob
record (the record overrides apply_week's keyword defaults), then the
output floor the replay applied (app.core.floor.floor_samples with the
recent observations it read). apply_week writes its oracle.json and donor
bank into a scratch folder, never into the replay's week.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path

import numpy as np


def kept(out: Path, season: str, asof: str) -> dict:
    from app.core import retro_store as RS
    d = out / "filter" / season / asof
    raw = RS.read_samples(d / "pf_filter.json.gz")["pf_filter"]
    args = json.loads((d / "step_args.json").read_text(encoding="utf-8"))
    rec = json.loads((d / "floor_recent.json").read_text(encoding="utf-8"))
    return {"raw": raw, "args": args, "recent": rec["recent"]}


def arm_extra(extra: dict, w: float, k: float) -> dict:
    from app.core import knobs as K
    e = copy.deepcopy(extra or {})
    r = dict(e.get(K.RECORD_KEY) or {})
    r["oracle.w"], r["oracle.narrow"] = w, k
    e[K.RECORD_KEY] = r
    return e


def member_for(inp: dict, asof: str, w: float, k: float, scratch: Path) -> dict:
    """location -> {canonical horizon: floored samples} for one arm."""
    from app.core import oracle as OM
    from app.core.floor import floor_samples
    a = inp["args"]
    member, _prov = OM.apply_week(
        inp["raw"], asof, scratch, extra=arm_extra(a["extra"], w, k),
        weeks_to_drop=int(a["weeks_to_drop"] or 0),
        drop_same_day=bool(a["drop_same_day"]))
    return {loc: floor_samples(s, loc, asof, recent=inp["recent"].get(loc, []))
            for loc, s in member.items()}


def same(a: dict, b: dict) -> tuple:
    """(identical, max abs difference, locations compared)."""
    if set(a) != set(b):
        return False, float("inf"), 0
    worst, ok = 0.0, True
    for loc in a:
        if set(map(str, a[loc])) != set(map(str, b[loc])):
            return False, float("inf"), len(a)
        for h in a[loc]:
            x = np.asarray(a[loc][h], float); y = np.asarray(b[loc][str(h)] if str(h) in b[loc] else b[loc][h], float)
            if x.shape != y.shape:
                return False, float("inf"), len(a)
            d = np.nanmax(np.abs(x - y)) if x.size else 0.0
            worst = max(worst, float(d))
            ok = ok and np.array_equal(x, y, equal_nan=True)
    return ok, worst, len(a)


def check(out: Path, seasons: list, weeks: set) -> int:
    from app.core import retro_store as RS
    bad = 0
    for season in seasons:
        base = out / "filter" / season
        if not base.is_dir():
            continue
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            asof = d.name
            if weeks and asof not in weeks:
                continue
            inp = kept(out, season, asof)
            stored = RS.read_week_samples(out / "replay" / season, asof)["pf"]
            with tempfile.TemporaryDirectory() as tmp:
                mine = member_for(inp, asof, 0.25, 0.7, Path(tmp))
            ok, worst, n = same(mine, stored)
            bad += int(not ok)
            print(f"{season} {asof}: {n} locations, {'identical' if ok else 'DIFFERS'} (max |diff| {worst:.3g})", flush=True)
    print(f"weeks differing: {bad}")
    return bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check"])
    ap.add_argument("out")
    ap.add_argument("--seasons", default="2023-24,2024-25,2025-26")
    ap.add_argument("--weeks", default="")
    a = ap.parse_args()
    sys.exit(1 if check(Path(a.out), a.seasons.split(","), {w for w in a.weeks.split(",") if w}) else 0)
