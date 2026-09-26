"""A sandbox run read back: results() from what the engine wrote,
fit_health in plain words, summary_rows for the export.
app/core/sandbox.py is the facade; every name here imports from it too.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

from app.core.sandbox import _RAW, FULL_FIT_PARTICLES, _fmt, shown_status


def results(workroot: Path, live=_RAW) -> dict:
    """What the engine wrote, read back: the outcome, a parameter table
    (5th, 50th and 95th percentiles of the posterior sample), the ESS
    record, and the trajectory summarised per week (10th, 50th, 90th
    percentiles over particles) with the observed counts beside it. With
    live=, the status reads as shown_status says."""
    workroot = Path(workroot)
    meta = json.loads((workroot / "meta.json").read_text())
    meta["status"] = shown_status(meta, workroot.name, live)
    out = {"meta": meta, "run_id": workroot.name, "params": [], "ess": [],
           "traj": None, "stderr": ""}
    cell = workroot / f"{meta['model']}_r0"
    runs = cell / "out" / "Results" / "PF" / "Runs"
    pf = next(runs.glob("params_*.txt"), None) if runs.is_dir() else None
    if pf is not None:
        try:
            names = pf.read_text().splitlines()[0].split("\t")
            arr = np.loadtxt(pf, skiprows=1, ndmin=2)
            for j, nme in enumerate(names):
                q = np.percentile(arr[:, j], [5, 50, 95])
                out["params"].append({"name": nme, "p5": float(q[0]),
                                      "p50": float(q[1]), "p95": float(q[2])})
            out["distinct"] = int(np.unique(arr, axis=0).shape[0])
            out["sample"] = int(arr.shape[0])
        except Exception as e:
            out["stderr"] += f"params unreadable: {e}\n"
    ef = cell / "out" / "Results" / "PF" / "ess_0.txt"
    if ef.is_file():
        try:
            e = np.loadtxt(ef, ndmin=2, comments="#")
            out["ess"] = [{"t": float(r[0]), "ess": float(r[1]),
                           "distinct": int(r[3]), "degenerate": int(r[4])}
                          for r in e]
        except Exception as exc:
            out["stderr"] += f"ess unreadable: {exc}\n"
    tf = next(runs.glob("*traj_noise*"), None) if runs.is_dir() else None
    if tf is not None:
        try:
            tr = np.loadtxt(tf, ndmin=2)
            n = int(meta["n_obs"]) if "n_obs" in meta else len(meta["observed"])
            q = np.nanpercentile(tr, [10, 50, 90], axis=0)
            out["traj"] = {"n_obs": n, "columns": int(tr.shape[1]),
                           "q10": q[0].tolist(), "q50": q[1].tolist(),
                           "q90": q[2].tolist()}
        except Exception as exc:
            out["stderr"] += f"trajectory unreadable: {exc}\n"
    for err in sorted(workroot.glob("pf_runner_*.err")):
        try:
            txt = err.read_text(errors="replace").strip()
        except OSError:
            continue
        if txt:
            out["stderr"] += txt[-1500:]
    out["health"] = fit_health(out)
    return out


#: fit_health's thresholds, as fractions of the particles: under COLLAPSED
#: the cloud is a handful of copies (the engine's own collapse warning is
#: ESS under 2%), under THIN it is thinning out


HEALTH_COLLAPSED = 0.02
HEALTH_THIN = 0.10
#: fewer of the observed rows inside the 10 to 90% band: the band misses
HEALTH_COVER = 0.5


def fit_health(res: dict) -> dict | None:
    """The run's outcome in plain words for the Results card, read from
    what the engine wrote: "level" (good, rough, collapsed), a "title", a
    "says" sentence, the week "at" it went wrong, whether the band "misses"
    most of the data, and "tries": what to do next, most useful first.
    None for a run that left no parameter sample and no ESS record."""
    meta = res.get("meta") or {}
    ess, params = res.get("ess") or [], res.get("params") or []
    if not ess and not params:
        return None
    n = int(meta.get("particles") or 0) or int(res.get("sample") or 0) or 1
    sample = int(res.get("sample") or 0)
    distinct = int(res.get("distinct") or 0)
    ess_min = min((e["ess"] for e in ess), default=None)
    thin_at = next((e["t"] for e in ess
                    if e["ess"] < HEALTH_THIN * n
                    or e["distinct"] < HEALTH_THIN * n), None)
    gone_at = next((e["t"] for e in ess
                    if e["ess"] < HEALTH_COLLAPSED * n
                    or e["distinct"] < HEALTH_COLLAPSED * n
                    or e.get("degenerate")), None)
    flat = bool(params) and all(p["p5"] == p["p95"] for p in params)
    few = bool(sample) and distinct <= max(2, HEALTH_COLLAPSED * sample)
    first_t = ess[0]["t"] if ess else None
    # the band against the data: observed rows inside the 10 to 90% band
    misses, inside, counted = False, 0, 0
    tr = res.get("traj") or {}
    obs = meta.get("observed") or []
    if tr.get("q10") and obs:
        for i, y in enumerate(obs[:len(tr["q10"])]):
            if y is None or float(y) < 0:
                continue
            counted += 1
            inside += tr["q10"][i] <= float(y) <= tr["q90"][i]
        misses = counted >= 3 and inside < HEALTH_COVER * counted
    fmt_t = lambda t: f"{t:g}"
    h = {"level": "good", "at": None, "misses": misses, "tries": [],
         "ess_min": ess_min, "particles": n, "inside": inside,
         "counted": counted}
    if flat or few or gone_at is not None:
        # the first sign: thinning comes before (or with) the collapse
        at = min((t for t in (thin_at, gone_at) if t is not None), default=None)
        h.update(level="collapsed", at=at, title="The fit collapsed",
                 says=("Nearly every particle ended as a copy of the same "
                       "one or few parameter sets"
                       + (f", from t = {fmt_t(at)} on" if at is not None else "")
                       + ", so the table shows one value where a range "
                       "should be and the band is not a real estimate."))
    elif thin_at is not None:
        h.update(level="rough", at=thin_at, title="The fit is rough",
                 says=(f"The particles thinned out at t = {fmt_t(thin_at)} "
                       f"(lowest ESS {ess_min:,.0f} of {n:,}), so the ranges "
                       "are likely too narrow."))
    else:
        h.update(title="The fit looks healthy",
                 says=("The particles stayed varied at every week"
                       + (f" (lowest ESS {ess_min:,.0f} of {n:,})"
                          if ess_min is not None else "") + "."))
    if misses:
        h["says"] += (f" Only {inside} of the {counted} data points sit "
                      "inside the 10 to 90% band.")
    tries = h["tries"]
    if n < FULL_FIT_PARTICLES and h["level"] != "good":
        tries.append(f"Run the full fit with {FULL_FIT_PARTICLES:,} "
                     f"particles: {n:,} cover a prior too thinly.")
    if h["level"] == "collapsed" and h["at"] is not None and h["at"] == first_t:
        tries.append("It went wrong at the first data row: Check compares "
                     "the model at its written values with the data. N, "
                     "the starting state and the reporting scale set the "
                     "first weeks' counts; the model starts one week "
                     "before the first row.")
    if h["level"] != "good" or misses:
        tries.append("Narrow a prior that is much wider than the values "
                     "you find plausible: particles drawn where the data "
                     "rule them out are wasted.")
    if misses:
        tries.append("A band that misses the data is the model, not the "
                     "filter: check the rates, the fixed values and which "
                     "output pf_cumulative_observable names.")
    if h["level"] != "good":
        tries.append("Raise Jitter to 0.2 or 0.3 so a thinning cloud "
                     "spreads out again.")
    return h


# ------------------------------------------------------------- the archive
# A model's data.exp filled from the hub archive: one location's weekly
# admissions over a date range, settled or as one vintage knew it. The
# hub modules are imported inside the functions so this module imports
# on a machine without a hub. The sidecar data.source.json records where


def summary_rows(res: dict) -> list:
    """One row per trajectory column: [column, t, date, q10, q50, q90,
    observed]; forecast columns step past the last row by the closest
    spacing of the observed times (as the page plots them)."""
    meta, traj = res["meta"], res.get("traj") or {}
    times = list(meta.get("time") or [])
    obs = list(meta.get("observed") or [])
    dates = list(meta.get("dates") or [])
    ncol = int(traj.get("columns") or 0)
    gaps = [b - a for a, b in zip(times, times[1:]) if b > a]
    step = min(gaps) if gaps else 1
    rows = []
    for i in range(ncol):
        t = times[i] if i < len(times) else (
            (times[-1] if times else 0) + step * (i - len(times) + 1))
        day = ""
        if dates and len(dates) == len(times) and times:
            day = (dt.date.fromisoformat(dates[0])
                   + dt.timedelta(days=round(7 * (t - times[0])))).isoformat()
        # a missing week (written negative or NaN, read_exp) is blank,
        # never a count of -1
        y = obs[i] if i < len(obs) else None
        seen = (y is not None and math.isfinite(float(y))
                and float(y) >= 0)
        rows.append([i, _fmt(t), day] + [f"{float(traj[q][i]):.6g}"
                                         for q in ("q10", "q50", "q90")]
                    + [_fmt(y) if seen else ""])
    return rows
