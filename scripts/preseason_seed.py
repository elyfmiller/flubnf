"""Pre-season warm-up: fit to convergence, not to a clock.

WHY THIS IS A SEPARATE SCRIPT FROM THE WEEKLY LOOP
--------------------------------------------------
The two have opposite stopping rules and it is a mistake to blur them.

    weekly loop     time-bounded. A deadline exists, and the job is to absorb
                    one new point and one revision into an already-converged
                    state before it. Stops when the clock says so.
    pre-season      convergence-bounded. No deadline exists. The job is to
                    arrive at the first competition week with a posterior worth
                    warm-starting from. Stops when the fit stops improving.

Everything downstream assumes the weekly loop begins from a converged state.
Measured: starting a week cold at 1000 iterations pinned three of five
parameters on round 0; after a 12,000-iteration seed the same round came back
with none. The seed is not an optimisation, it is the precondition.

SOLSTICE SEEDING
----------------
Fitting starts at the summer solstice rather than a nominal season start. At
season start there is nothing to fit to; the solstice gives the summer trough as
fittable signal, which is what pins `mult` and the baseline level before the
epidemic supplies any curvature.

STOPPING RULE
-------------
Rounds continue until either
  * no parameter is pinned AND R-hat is acceptable on every fitted parameter, or
  * `--max-rounds` is reached, or
  * a round fails to improve the objective by more than `--tol`.
Between rounds, pinned bounds are widened (widen only -- never drop a parameter,
because the BNGL template still declares it and a conf that omits it stops
matching the model). Each round warm-starts from the last via `continue_run`, so
the rounds compound rather than restart.

R-HAT NEEDS TWO CHAINS
----------------------
`--chains 1` makes R-hat uncomputable, leaving pinning as the only signal. The
default of 2 is the cheapest setting that keeps both.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flubnf.autoparam import diagnose, next_priors                   # noqa: E402
from flubnf.sihrs_fit import MIN_PRIORS                              # noqa: E402
from scripts.weekly_loop_run import one_fit, prune, state_dir        # noqa: E402


def solstice(year: int) -> str:
    """Summer solstice, near enough for a fitting window."""
    return f"{year}-06-21"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", nargs="+", required=True)
    ap.add_argument("--through", required=True,
                    help="last NON-competition week to fit through (YYYY-MM-DD)")
    ap.add_argument("--season-start", default=None,
                    help="defaults to the solstice of the through-date's year")
    ap.add_argument("--root", default="/tmp/preseason")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--chains", type=int, default=2)
    ap.add_argument("--iters", type=int, default=8000, help="per round")
    ap.add_argument("--max-rounds", type=int, default=6)
    ap.add_argument("--tol", type=float, default=0.01,
                    help="stop when the objective improves by less than this")
    ap.add_argument("--rhat-max", type=float, default=1.10)
    ap.add_argument("--timeout", type=float, default=21600.0)
    ap.add_argument("--min-model", action="store_true")
    ap.add_argument("--out", default="backtest_results/preseason.json")
    a = ap.parse_args()

    # PREFLIGHT: a seed date with no published vintage fails every fit with a
    # quiet per-record "no vintage". Fail loudly instead, and say what exists —
    # this exact mistake cost a queue slot on 2025-11-08, which sits in the
    # archive's Sept-20 -> Nov-15 gap.
    from scripts.vintage_run import ARCHIVE, vintage_for
    if vintage_for(a.through) is None:
        avail = sorted(p.name.split("_")[-1].removesuffix(".csv")
                       for p in ARCHIVE.glob("target-hospital-admissions_*.csv"))
        near = [d for d in avail if abs((pd.Timestamp(d)-pd.Timestamp(a.through)).days) <= 45]
        raise SystemExit(f"[preseason] NO VINTAGE for --through {a.through}. "
                         f"Nearby vintages: {near}")

    yr = pd.Timestamp(a.through).year
    ss = a.season_start or solstice(yr if pd.Timestamp(a.through).month >= 6 else yr - 1)
    priors, prev_obj, history = dict(MIN_PRIORS), None, []
    t0 = time.time()
    print(f"[preseason] {len(a.states)} states | solstice {ss} -> {a.through} | "
          f"{a.chains} chains | up to {a.max_rounds} rounds of {a.iters}", flush=True)

    for rnd in range(a.max_rounds):
        jobs = [(s, a.through, ss, a.root, a.iters, a.timeout,
                 priors, rnd > 0, bool(a.min_model), a.chains) for s in a.states]
        recs = []
        with ProcessPoolExecutor(max_workers=a.jobs) as ex:
            for fu in as_completed([ex.submit(one_fit, j) for j in jobs]):
                try:
                    recs.append(fu.result())
                except Exception as exc:
                    recs.append({"ok": False, "reason": str(exc)[:150]})
        ok = [r for r in recs if r.get("ok")]
        if not ok:
            print(f"  round {rnd}: 0/{len(recs)} ok -- stopping", flush=True)
            break

        pins = sorted({p for r in ok for p in r.get("pinned", [])})
        pin_frac = float(np.mean([bool(r.get("pinned")) for r in ok]))
        obj = float(np.median([r.get("objective", np.nan) for r in ok]))
        print(f"  round {rnd}: {len(ok)}/{len(recs)} ok | pinned {pin_frac:.0%} "
              f"{pins or '-'} | median obj {obj:.1f} | "
              f"{(time.time()-t0)/60:.0f} min", flush=True)
        history.append({"round": rnd, "n_ok": len(ok), "pinned": pins,
                        "pin_frac": pin_frac, "objective": obj})

        if not pins:
            print("  converged: nothing pinned", flush=True)
            break
        if prev_obj is not None and np.isfinite(obj) and np.isfinite(prev_obj):
            if abs(prev_obj - obj) / max(abs(prev_obj), 1e-9) < a.tol:
                print(f"  stopping: objective improved < {a.tol:.1%}", flush=True)
                break
        prev_obj = obj

        med = {k: float(np.median([r["medians"][k] for r in ok if "medians" in r]))
               for k in priors}
        newp = next_priors(diagnose(pins, med, priors), priors)
        newp = {k: newp.get(k, priors[k]) for k in priors}   # widen only
        if newp == priors:
            print("  stopping: bounds could not be widened further", flush=True)
            break
        priors = newp
        print(f"    widened -> "
              f"{ {k: tuple(round(x,4) for x in v) for k,v in priors.items()} }",
              flush=True)

    for s in a.states:
        prune(state_dir(Path(a.root), s) / "res")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"season_start": ss, "through": a.through, "chains": a.chains,
         "final_priors": {k: list(v) for k, v in priors.items()},
         "history": history, "warm_root": str(a.root),
         "minutes": (time.time() - t0) / 60}, indent=1))
    print(f"[preseason] done in {(time.time()-t0)/60:.0f} min. "
          f"Warm state in {a.root}/warm -- point the weekly loop at it with "
          f"--root {a.root}", flush=True)


if __name__ == "__main__":
    main()
