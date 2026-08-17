"""Real-time simulation: fit on the VINTAGE data, score against SETTLED truth.

THE QUESTION
------------
relWIS 0.883 was measured with the model seeing FINAL revised admissions at
every as-of date. A live competition run never has that. This measures the gap.

It is not a hypothetical concern. Two direct observations from this codebase:
  * California, as-of 2026-01-24: the last observed week read 1324 in real time
    and 1624 after revision -- a 23% under-count on exactly the point the
    forecast anchors to.
  * A lab leading-indicator signal measured at clustered t=3.10 on revised data
    fell to t=0.63 on first-release data (scripts/lab_signal_vintage_gate.py).
    Final-data conclusions in this project have already failed to transfer once.

DESIGN
------
FIT on the vintage as of date T -- literally the CSV the hub published that week,
from auxiliary-data/target-data-archive/. SCORE against settled truth, because
the outcome is what actually happened. Scoring against the vintage would grade
the model on numbers that were later corrected.

CHANGE ONE THING. This uses the POLAR template and the sweep's exact conf, so
the only difference from the 728-fit control is the data. The Cartesian
reparameterization is a separate change and must not be confounded with this one.

COVERAGE
--------
22 of the 28 sweep dates have an exact vintage. Six do not (2025-11-22,
2025-12-20, 2026-01-31, 2026-03-07, 2026-04-25, 2026-05-23) and are SKIPPED
rather than approximated -- substituting a stale vintage would mix a
week-old-information condition into the comparison. Note 2026-01-31 is a
shoulder date, so shoulder coverage is 4/5.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flubnf.sihrs_fit import (FITTED_PRIORS, materialize_model,     # noqa: E402
                              resolve_state, run_pybnf, write_conf, write_exp)
from scripts.profiled_fit_run import BNG, LOCS, PYBNF, TEMPLATE, convergence  # noqa: E402

from flubnf.settings import ARCHIVE  # noqa: E402
MIN_TEMPLATE = Path(__file__).resolve().parent.parent / "flubnf" / "templates" / "SIHRS_pop_min.bngl"
# DO NOT put run options here and set them in main(). macOS multiprocessing
# defaults to SPAWN: a pool worker RE-IMPORTS this module, so any global assigned
# inside main() reverts to the value below and the flag is silently ignored.
# That bug made --window-weeks and --min-model no-ops for an entire campaign --
# three "window" arms were really three identical full-season runs.
# Options now travel in the args tuple, which is pickled to the worker.
OPTS = {"min_model": False, "window_weeks": None}   # defaults only; see one_fit


def effective_season_start(asof: str, season_start: str,
                           window_weeks: Optional[int] = None) -> str:
    """A ROLLING FRAME: refit on only the last `window_weeks` of data.

    Why this might help, and why it is not just recency weighting. Weighting
    downweights old data but the model still carries the susceptible depletion
    accumulated over the whole season, which is what forces the decline. A hard
    window RE-INITIALISES: with s0 still 0.85 the model no longer knows the
    population is depleted, so it can grow again. That is the reactivity the old
    piecewise SIR got by hand when a human re-pinned the model on recent weeks.

    Suggestive evidence: the calendar analogue uses a ONE-WEEK frame (current
    level plus historical ratios, no season history) and beats SIHRS's median in
    exactly the two phases where SIHRS's median is worst -- early growth
    (-0.299) and the shoulder (-0.095).

    Cost: a short window starves the fit. With 8 observations even 5 parameters
    is thin, which is why this pairs with the parsimonious template.
    """
    w = window_weeks if window_weeks is not None else OPTS.get("window_weeks")
    if not w:
        return season_start
    start = pd.Timestamp(asof) - pd.Timedelta(weeks=int(w))
    return max(start, pd.Timestamp(season_start)).date().isoformat()


def vintage_for(asof: str) -> Path | None:
    p = ARCHIVE / f"target-hospital-admissions_{asof}.csv"
    return p if p.is_file() else None


def one_fit(args) -> dict:
    (state, asof, workroot, season_start, iters, timeout,
     min_model, window_weeks) = args
    tag = f"{asof}_{state.replace(' ', '_')}"
    ck = Path(workroot) / "parts" / f"{tag}.json"
    if ck.is_file():
        try:
            return json.loads(ck.read_text())
        except Exception:
            pass
    W = Path(workroot) / tag
    shutil.rmtree(W, ignore_errors=True)
    rec: dict = {"state": state, "asof": asof, "ok": False, "data": "vintage"}
    try:
        vf = vintage_for(asof)
        if vf is None:
            rec["reason"] = "no vintage for this as-of"
            raise RuntimeError(rec["reason"])
        eff = effective_season_start(asof, season_start, window_weeks)
        rec["season_start_used"] = eff
        s = resolve_state(state, truth_csv=vf, locations_csv=LOCS,
                          season_start=eff, as_of=asof)
        rec["n_obs_window"] = int(s.n_obs)
        rec["last_observed_vintage"] = float(s.observed[-1])
        rec["n_obs"] = int(s.n_obs)
        suffix = f"{state.replace(' ', '_')}_flu"
        m = materialize_model(s, MIN_TEMPLATE if min_model else TEMPLATE,
                              W / "m.bngl", suffix)
        e = write_exp(s, W / f"{suffix}.exp")
        from flubnf.sihrs_fit import MIN_PRIORS
        c = write_conf(s, model=m, exp=e, out_dir=W / "res", conf_path=W / "c.conf",
                       bng_command=BNG, max_iterations=iters,
                       burn_in=max(50, iters // 4), adaptive=max(50, iters // 4),
                       priors=MIN_PRIORS if min_model else None)
        r = run_pybnf(c, pybnf_binary=PYBNF, cwd=W / "scratch", timeout_sec=timeout)
        rec["elapsed"] = r.get("elapsed", 0)
        if not r["ok"]:
            rec["reason"] = (r.get("reason") or r.get("stderr_tail", ""))[-250:]
        else:
            runs = W / "res" / "Results" / "A_MCMC" / "Runs"
            g = sorted(runs.glob("*traj_noise*"))
            if g:
                tr = np.genfromtxt(g[0])
                if tr.ndim == 1:
                    tr = tr.reshape(1, -1)
                lwo = s.last_week_offset          # != n_obs-1 when weeks missing
                if lwo + 4 < tr.shape[1]:
                    rec["samples"] = {str(h): tr[:, lwo + h].tolist()
                                      for h in (0, 1, 2, 3, 4)}
                    rec["last_observed"] = float(s.observed[-1])
                    try:
                        rec["convergence"] = convergence(runs)
                    except Exception:
                        rec["convergence"] = {}
                    pf = runs / "params_0.txt"
                    if pf.is_file():
                        P = pd.read_csv(pf, sep=r"\s+")
                        post = P.iloc[len(P) // 4:]
                        pin = []
                        from flubnf.sihrs_fit import MIN_PRIORS as _MP
                        for nm, (lo, hi) in ((_MP if min_model else FITTED_PRIORS)).items():
                            col = nm if nm in post.columns else nm.replace("__FREE", "")
                            if col not in post.columns:
                                continue
                            v = pd.to_numeric(post[col], errors="coerce").dropna().to_numpy()
                            if not v.size:
                                continue
                            w = hi - lo
                            if (np.mean(v <= lo + 0.02 * w) > 0.25
                                    or np.mean(v >= hi - 0.02 * w) > 0.25):
                                pin.append(nm)
                            rec[f"med_{col}"] = float(np.median(v))
                        rec["pinned"] = pin
                    rec["ok"] = True
    except Exception as exc:
        rec.setdefault("reason", f"{type(exc).__name__}: {exc}"[:250])
    finally:
        shutil.rmtree(W, ignore_errors=True)
    ck.parent.mkdir(parents=True, exist_ok=True)
    ck.write_text(json.dumps(rec))
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", nargs="+", required=True)
    ap.add_argument("--asofs", nargs="+", default=None,
                    help="default: every sweep date that has an exact vintage")
    ap.add_argument("--season-start", default="2025-08-01")
    ap.add_argument("--iters", type=int, default=8000)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=21600.0)
    ap.add_argument("--workroot", default="/tmp/vintage")
    ap.add_argument("--out", default="backtest_results/vintage_run.json")
    ap.add_argument("--min-model", action="store_true")
    ap.add_argument("--window-weeks", type=int, default=None,
                    help="rolling frame: fit only the last N weeks")
    a = ap.parse_args()
    OPTS["min_model"]=bool(a.min_model); OPTS["window_weeks"]=a.window_weeks

    if a.asofs is None:
        # Only vintages inside the season being fitted. The archive spans three
        # seasons (2023-09-23 .. 2026-05-30); defaulting to all of them launches
        # ~2262 jobs that fail instantly, because a vintage from 2023 has no data
        # in a 2025-08-01 window. Season start + 12 months bounds it.
        lo = pd.Timestamp(a.season_start)
        hi = lo + pd.DateOffset(months=12)
        a.asofs = sorted(
            d for d in (p.name.split("_")[-1].removesuffix(".csv")
                        for p in ARCHIVE.glob("target-hospital-admissions_*.csv"))
            if lo <= pd.Timestamp(d) <= hi)
    dates = [d for d in a.asofs if vintage_for(d)]
    skipped = [d for d in a.asofs if not vintage_for(d)]
    jobs = [(s, d, a.workroot, a.season_start, a.iters, a.timeout,
             bool(a.min_model), a.window_weeks)
            for d in dates for s in a.states]
    print(f"[vintage] {len(a.states)} states x {len(dates)} dates = {len(jobs)} fits "
          f"({a.jobs}-wide). Control = the settled-truth sweep.", flush=True)
    if skipped:
        print(f"[vintage] skipped (no vintage): {', '.join(skipped)}", flush=True)

    Path(a.workroot).mkdir(parents=True, exist_ok=True)
    out, t0 = [], time.time()
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(one_fit, j): j for j in jobs}
        for i, fu in enumerate(as_completed(futs), 1):
            try:
                r = fu.result()
            except Exception as exc:
                r = {"ok": False, "reason": str(exc)[:150]}
            out.append(r)
            print(f"[{i}/{len(jobs)}] {r.get('asof')} {r.get('state')}: "
                  f"ok={r.get('ok')} ({(time.time()-t0)/60:.1f} min)", flush=True)
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(json.dumps(out))
    ok = sum(1 for r in out if r.get("ok"))
    print(f"[vintage] done: {ok}/{len(out)} ok, {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
