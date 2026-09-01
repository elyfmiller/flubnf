"""Score the sequential particle filter, and select its one knob HONESTLY.

WHAT THIS IS FOR
----------------
`flubnf/particle_filter.py` replaces the weekly batch refit with a filter that
carries last week's posterior forward. It has exactly one free knob, `jitter`
(how fast parameters are allowed to drift), and an in-season sweep put its
optimum at 0.30 with relWIS 0.901 -- better than the 0.918 batch fit.

That number is NOT trustworthy on its own. It was selected on the same season it
was scored on, which is the precise error that turned the calendar analogue's
in-season 0.665 into an honest 0.806: +0.141 against that lucky in-season pick,
and +0.259 against the in-season oracle (0.547), the largest selection penalty
measured in this project (see the bandwidth provenance note in
flubnf/analogue.py). So this script does both:

  --mode sweep    score a jitter grid per season  (diagnostic)
  --mode frozen   pick jitter on the two PRIOR seasons, apply it to the held-out
                  one, report both the frozen and the oracle value

The gap between frozen and oracle is the honest cost of tuning. Report the
frozen number.

WHY THE JITTER CURVE IS U-SHAPED
--------------------------------
Too little and the ensemble is overconfident: at 0.03 the predictive log-sd is
0.41 and relWIS is 1.549, worse than doing nothing. Too much and the mechanism
is forgotten -- the filter degenerates toward a random walk and relWIS climbs
back to 1.084 at 0.60. The minimum is where parameter drift matches the rate at
which transmission actually changes.

COVERAGE IS THE POINT
---------------------
This is the first configuration in the project whose intervals are close to
nominal (49% / 91% against 50% / 95%). The measured defect is SPREAD, not the
median -- swapping spread gains 0.070 relWIS while swapping the median gains
0.003 -- so coverage is the diagnostic that matters, and it is reported here
alongside relWIS rather than derived afterwards.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flubnf.particle_filter import (AdaptiveJitter, Particles,      # noqa: E402
                                    anchor_factors, forecast, update)
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL                # noqa: E402
from flubnf.sihrs_fit import resolve_state                           # noqa: E402
from flubnf.wis import wis                                           # noqa: E402
from scripts.profiled_fit_run import LOCS                            # noqa: E402
from scripts.vintage_run import vintage_for                          # noqa: E402

_sp = importlib.util.spec_from_file_location(
    "anchor_analysis", Path(__file__).resolve().parent / "anchor_analysis.py")
AA = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(AA)

# Filter bounds mirror MIN_PRIORS: the filter fits the same five parameters as
# templates/SIHRS_pop_min.bngl, so a difference between the two is the algorithm
# and not the parameterisation.
BOUNDS = dict(Reff=(0.6, 2.5), eps1=(0.0, 1.0), phi1=(0.0, 52.0),
              mult=(0.002, 1.0), r=(0.1, 40.0))

SEASONS = {
    "2023-24": ("backtest_results/vintage_2023_24.json", "2023-08-01"),
    "2024-25": ("backtest_results/vintage_2024_25.json", "2024-08-01"),
    "2025-26": ("backtest_results/vintage_run.json", "2025-08-01"),
}


def run_cell(state, asof, season_start, jitter, n=800, seed=0,
             anchor_lookback=0, anchor_mode='particle', drift=0.0):
    """Filter the whole season up to `asof`, then forecast 4 weeks.

    `jitter` is a float, or the string "auto" for `AdaptiveJitter`, which sets
    the knob online from the filter's own PIT calibration and consults no other
    season.
    """
    vf = vintage_for(asof)
    if vf is None:
        return None
    try:
        s = resolve_state(state, truth_csv=vf, locations_csv=LOCS,
                          season_start=season_start, as_of=asof)
    except Exception:
        return None
    if s.n_obs < 6:
        return None
    rng = np.random.default_rng(seed)
    N, s0 = float(s.population), s.s0
    p = Particles(
        Reff=rng.uniform(0.6, 2.0, n), eps1=rng.uniform(0.0, 0.6, n),
        phi1=rng.uniform(0.0, 52.0, n),
        mult=10 ** rng.uniform(np.log10(0.002), 0.0, n),
        r=10 ** rng.uniform(np.log10(0.5), np.log10(40.0), n),
        S=np.full(n, N * s0), I=np.full(n, N * s.i0), H=np.zeros(n),
        R=np.full(n, N * (1 - s0 - s.i0)), w=np.full(n, 1.0 / n))

    auto = AdaptiveJitter() if jitter == "auto" else None
    j = auto.jitter if auto else float(jitter)
    mu_hist, obs_hist = [], []
    for k, y in enumerate(s.observed):
        out = update(p, float(y), float(k), N, s0, rng,
                     jitter=j, bounds=BOUNDS)
        if not out["ok"]:
            return None        # degenerate ensemble: no forecast, not a bad one
        if anchor_lookback:
            # Resampling permutes the ensemble, so every stored per-particle
            # row must be permuted with it. Skipping this silently anchors each
            # particle to some OTHER particle's history.
            idx = out.get("resample_idx")
            if idx is not None:
                mu_hist = [m[idx] for m in mu_hist]
            mu_hist.append(out["mu"])
            obs_hist.append(float(y))
            mu_hist = mu_hist[-anchor_lookback:]
            obs_hist = obs_hist[-anchor_lookback:]
        if auto:
            j = auto.observe(out.get("pit"))

    factors = None
    if anchor_lookback and mu_hist:
        factors = anchor_factors(mu_hist, obs_hist, mode=anchor_mode)
    fc = forecast(p, float(s.n_obs - 1), [1, 2, 3, 4], N, s0, rng,
                  factors=factors, drift=drift, bounds=BOUNDS)
    if auto:
        fc["_jitter"] = auto.jitter
    return fc


def score_season(season, jitter, truth, name2fips, n=800, anchor_lookback=0,
                 anchor_mode='particle', drift=0.0):
    path, season_start = SEASONS[season]
    recs = json.loads(Path(path).read_text())
    states = sorted({r["state"] for r in recs})
    dates = sorted({r["asof"] for r in recs if r.get("ok")})

    rows, c50, c95, sds = [], [], [], []
    for asof in dates:
        T = pd.Timestamp(asof)
        for st in states:
            fips = name2fips.get(st)
            if not fips:
                continue
            fc = run_cell(st, asof, season_start, jitter, n=n,
                          anchor_lookback=anchor_lookback,
                          anchor_mode=anchor_mode, drift=drift)
            if fc is None:
                continue
            for h in (1, 2, 3, 4):
                act = truth.get((fips, T + timedelta(days=7 * h)))
                if act is None or act <= 0:
                    continue
                a = np.asarray(fc[str(h)], float)
                a = a[np.isfinite(a)]
                if not a.size:
                    continue
                q = {float(x): float(np.quantile(a, x)) for x in QL}
                if q[0.5] <= 0:
                    continue
                try:
                    w_ = wis(q, act).wis
                except Exception:
                    continue
                if not np.isfinite(w_):
                    continue
                rows.append({"location": fips, "asof": asof,
                             "horizon": h - 1, "wis": w_})
                if h == 1:
                    pos = a[a > 0]
                    if pos.size > 10:
                        sds.append(float(np.std(np.log(pos))))
                    c50.append(q[0.25] <= act <= q[0.75])
                    c95.append(q[0.025] <= act <= q[0.975])
    if not rows:
        return None
    d = pd.DataFrame(rows)
    b = AA.baseline_cells(sorted(d["asof"].unique()), set(d.location), truth)
    b["k"] = list(zip(b.location, b["asof"], b.horizon))
    base = b.set_index("k").wis
    base = base[~base.index.duplicated()]
    d["k"] = list(zip(d.location, d["asof"], d.horizon))
    d = d[d.k.isin(base.index)]
    if d.empty:
        return None
    return {"season": season, "jitter": jitter,
            "relWIS": float(d.wis.sum() / base.loc[d.k].sum()),
            "n_cells": int(len(d)),
            "cov50": float(np.mean(c50)) if c50 else float("nan"),
            "cov95": float(np.mean(c95)) if c95 else float("nan"),
            "logsd_h1": float(np.mean(sds)) if sds else float("nan")}


def filter_with_pits(state, asof, season_start, jitter, n=800, seed=0):
    """Filter to `asof`, returning the forecast AND the 4-week-ahead PITs.

    The PIT of y_k is taken under the forecast issued four weeks earlier, from a
    filter that had seen nothing past week k-4. It is therefore a score the
    forecaster could have computed at the time, on its own past predictions --
    no settled truth, no later season.
    """
    from collections import deque

    vf = vintage_for(asof)
    if vf is None:
        return None
    try:
        s = resolve_state(state, truth_csv=vf, locations_csv=LOCS,
                          season_start=season_start, as_of=asof)
    except Exception:
        return None
    if s.n_obs < 6:
        return None
    rng = np.random.default_rng(seed)
    N, s0 = float(s.population), s.s0
    p = Particles(
        Reff=rng.uniform(0.6, 2.0, n), eps1=rng.uniform(0.0, 0.6, n),
        phi1=rng.uniform(0.0, 52.0, n),
        mult=10 ** rng.uniform(np.log10(0.002), 0.0, n),
        r=10 ** rng.uniform(np.log10(0.5), np.log10(40.0), n),
        S=np.full(n, N * s0), I=np.full(n, N * s.i0), H=np.zeros(n),
        R=np.full(n, N * (1 - s0 - s.i0)), w=np.full(n, 1.0 / n))

    buf, pits = deque(), []
    for k, y in enumerate(s.observed):
        if len(buf) == 4:
            d = buf.popleft()
            pits.append(float(np.mean(d < y))
                        + float(rng.random()) * float(np.mean(d == y)))
        if not update(p, float(y), float(k), N, s0, rng,
                      jitter=jitter, bounds=BOUNDS)["ok"]:
            return None
        buf.append(np.asarray(
            forecast(p, float(k), [4], N, s0, rng)["4"], float))
    return {"fc": forecast(p, float(s.n_obs - 1), [1, 2, 3, 4], N, s0, rng),
            "pits": pits[2:]}          # drop the two weeks with no real history


def calibration_selected(season, candidates, truth, name2fips, n=800,
                         target=0.25):
    """Pick `jitter` PER AS-OF DATE from past-only calibration, then score.

    THE POINT. A swept fixed jitter has an optimum that moves across seasons
    (0.25 / 0.55 / 0.30), so it cannot be frozen without paying a selection
    cost. This selects it from a quantity the forecaster owns at the time: how
    well its own four-week-ahead forecasts have been calibrated so far.

    Under a calibrated predictive the PIT is uniform, so E|PIT - 1/2| = 1/4.
    Measured against the swept optimum this statistic lands consistently BELOW
    it (0.11 / 0.42 / 0.24 against 0.25 / 0.55 / 0.30) but in the right order,
    so it carries real signal about how fast this particular season's
    transmission is changing.

    PITs are pooled ACROSS STATES at each date -- ~400 instead of ~16, which is
    the difference between a usable statistic and noise. Pooling across states
    at a fixed date uses only information already in hand on forecast day.
    """
    path, season_start = SEASONS[season]
    recs = json.loads(Path(path).read_text())
    states = sorted({r["state"] for r in recs})
    dates = sorted({r["asof"] for r in recs if r.get("ok")})

    rows, chosen, c50, c95 = [], [], [], []
    for asof in dates:
        T = pd.Timestamp(asof)
        per_j = {}
        for j in candidates:
            got = {st: filter_with_pits(st, asof, season_start, j, n=n)
                   for st in states}
            pooled = [v for r in got.values() if r for v in r["pits"]]
            if len(pooled) < 30:
                continue
            a = np.asarray(pooled, float)
            per_j[j] = (abs(float(np.mean(np.abs(a - 0.5))) - target), got)
        if not per_j:
            continue
        j_star = min(per_j, key=lambda j: per_j[j][0])
        chosen.append({"asof": asof, "jitter": j_star})
        got = per_j[j_star][1]

        for st in states:
            fips = name2fips.get(st)
            r = got.get(st)
            if not fips or r is None:
                continue
            for h in (1, 2, 3, 4):
                act = truth.get((fips, T + timedelta(days=7 * h)))
                if act is None or act <= 0:
                    continue
                arr = np.asarray(r["fc"][str(h)], float)
                arr = arr[np.isfinite(arr)]
                if not arr.size:
                    continue
                q = {float(x): float(np.quantile(arr, x)) for x in QL}
                if q[0.5] <= 0:
                    continue
                try:
                    w_ = wis(q, act).wis
                except Exception:
                    continue
                if not np.isfinite(w_):
                    continue
                rows.append({"location": fips, "asof": asof,
                             "horizon": h - 1, "wis": w_})
                if h == 1:
                    c50.append(q[0.25] <= act <= q[0.75])
                    c95.append(q[0.025] <= act <= q[0.975])
        print(f"    {asof}: jitter {j_star:.2f}", flush=True)

    if not rows:
        return None
    d = pd.DataFrame(rows)
    b = AA.baseline_cells(sorted(d["asof"].unique()), set(d.location), truth)
    b["k"] = list(zip(b.location, b["asof"], b.horizon))
    base = b.set_index("k").wis
    base = base[~base.index.duplicated()]
    d["k"] = list(zip(d.location, d["asof"], d.horizon))
    d = d[d.k.isin(base.index)]
    return {"season": season, "jitter": "calibrated",
            "relWIS": float(d.wis.sum() / base.loc[d.k].sum()),
            "n_cells": int(len(d)), "chosen": chosen,
            "cov50": float(np.mean(c50)), "cov95": float(np.mean(c95))}


def load_truth():
    t = pd.read_csv(AA.TRUTH, dtype={"location": str})
    t["location"] = t["location"].str.zfill(2)
    t["date"] = pd.to_datetime(t.date)
    truth = {(r.location, r.date): float(r.value)
             for r in t.itertuples() if np.isfinite(r.value)}
    L = pd.read_csv(AA.LOCS, dtype={"location": str})
    return truth, dict(zip(L.location_name, L.location.str.zfill(2)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("sweep", "frozen", "calib"),
                    default="sweep")
    ap.add_argument("--jitters", nargs="+",
                    default=[0.15, 0.20, 0.25, 0.30, 0.35, 0.45],
                    help='floats, or the literal "auto" for online PIT-adapted jitter')
    ap.add_argument("--seasons", nargs="+", default=list(SEASONS))
    ap.add_argument("--particles", type=int, default=800)
    ap.add_argument("--drift", type=float, default=0.0,
                    help="parameter drift DURING the forecast horizon")
    ap.add_argument("--anchor-mode", choices=("particle", "scalar"),
                    default="particle")
    ap.add_argument("--anchor-lookback", type=int, default=0,
                    help="0 = no anchoring (the original behaviour); 3 matches "
                         "the production SIHRS pipeline")
    ap.add_argument("--out", default="backtest_results/pf_sweep.json")
    a = ap.parse_args()

    truth, name2fips = load_truth()
    jitters = [j if j == "auto" else float(j) for j in a.jitters]
    res, t0 = [], time.time()

    if a.mode == "calib":
        for season in a.seasons:
            print(f"[calib] {season}", flush=True)
            r = calibration_selected(season, [float(j) for j in jitters],
                                     truth, name2fips, n=a.particles)
            if r is None:
                continue
            res.append(r)
            print(f"[{(time.time()-t0)/60:5.1f}m] {season} CALIBRATED  "
                  f"relWIS {r['relWIS']:.3f}  n={r['n_cells']}  "
                  f"cov {r['cov50']:.0%}/{r['cov95']:.0%}", flush=True)
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(json.dumps(res, indent=1))
        return

    for season in a.seasons:
        for jit in jitters:
            r = score_season(season, jit, truth, name2fips, n=a.particles,
                             anchor_lookback=a.anchor_lookback,
                             anchor_mode=a.anchor_mode, drift=a.drift)
            if r is None:
                continue
            res.append(r)
            lab = jit if isinstance(jit, str) else f"{jit:.2f}"
            print(f"[{(time.time()-t0)/60:5.1f}m] {season} jitter={lab}  "
                  f"relWIS {r['relWIS']:.3f}  n={r['n_cells']}  "
                  f"cov {r['cov50']:.0%}/{r['cov95']:.0%}", flush=True)
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(json.dumps(res, indent=1))

    df = pd.DataFrame(res)
    print("\n" + "=" * 62)
    print(df.pivot(index="jitter", columns="season", values="relWIS")
          .round(3).to_string())

    if a.mode == "frozen":
        print("\nHONEST OUT-OF-SEASON SELECTION")
        print("-" * 62)
        for held in a.seasons:
            others = [s for s in a.seasons if s != held]
            tr = df[df.season.isin(others)].groupby("jitter").relWIS.mean()
            if tr.empty:
                continue
            pick = float(tr.idxmin())
            te = df[df.season == held].set_index("jitter").relWIS
            if pick not in te.index or te.empty:
                continue
            frozen, oracle = float(te.loc[pick]), float(te.min())
            print(f"  {held}: select on {'+'.join(others)} -> jitter {pick:.2f}"
                  f"   frozen {frozen:.3f}   oracle {oracle:.3f}"
                  f"   cost +{frozen - oracle:.3f}")


if __name__ == "__main__":
    main()
