"""Walk a season week by week with warm starts and pinning-driven bound widening.

WHAT THIS IS TESTING
--------------------
Whether an auto-parameterised SIHRS, given the compute a between-week schedule
allows, approaches the sequential filter's 0.772. The filter wins today partly
because it never re-derives what it already knew; this gives the batch fit the
same advantage by carrying PyBNF's adapted proposal forward.

WARM START USES PyBNF'S OWN MECHANISM
-------------------------------------
`Adaptive_MCMC` persists `adaptive_files/{MLE_params,diffMatrix,diff}.txt` and
reloads all three under `continue_run = 1`. `diffMatrix` is the LEARNED
COVARIANCE, so this restores the adapted proposal rather than merely a starting
point -- which is most of what an adaptive chain has earned. `starting_params`
is the fallback for the case where those files are absent but a posterior is
known; the two are mutually exclusive in PyBNF (algorithms.py:2172).

THE ONE THING THAT MUST NOT BE DELETED
--------------------------------------
Every other runner in this repo rmtree's its work directory in a `finally`
block, which is why scratch stayed at ~120 MB across a 20-hour campaign. That
would destroy exactly the files a warm start needs. So each state keeps a
PERSISTENT directory holding only `adaptive_files/` -- ~1-2 KB, about 100 KB for
all 52 states -- and everything else is still discarded per fit.

BUDGET
------
Throughput is I/O-bound at ~2.1 fits/min regardless of worker count (doubling
workers bought 6%), so a 52-state round costs ~25 min per 1000 iterations. The
schedule in `flubnf.weekly_loop` sizes rounds from that measurement rather than
from a guess.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flubnf.autoparam import diagnose, next_priors                   # noqa: E402
from flubnf.sihrs_fit import (MIN_PRIORS, materialize_model,         # noqa: E402
                              resolve_state, run_pybnf, write_conf, write_exp)
from flubnf.warmstart import (Posterior, cold_start_needed,          # noqa: E402
                              pinned_parameters, read_posterior, starting_params)
from flubnf.weekly_loop import LoopPlan                              # noqa: E402
from scripts.profiled_fit_run import BNG, LOCS, PYBNF, TEMPLATE      # noqa: E402
from scripts.vintage_run import MIN_TEMPLATE, vintage_for            # noqa: E402


def state_dir(root: Path, state: str) -> Path:
    """Persistent per-state home for adaptive_files. Survives between weeks."""
    d = Path(root) / "warm" / state.replace(" ", "_")
    d.mkdir(parents=True, exist_ok=True)
    return d


def one_fit(args) -> dict:
    """One state, one round. Options travel in `args` -- macOS spawns."""
    (state, asof, season_start, root, iters, timeout,
     priors, warm, min_model, chains) = args

    rec = {"state": state, "asof": asof, "ok": False, "warm": bool(warm)}
    home = state_dir(Path(root), state)
    out_dir = home / "res"                       # PERSISTENT: holds adaptive_files
    W = Path(root) / "scratch" / f"{asof}_{state.replace(' ', '_')}"
    shutil.rmtree(W, ignore_errors=True)
    W.mkdir(parents=True, exist_ok=True)
    try:
        vf = vintage_for(asof)
        if vf is None:
            rec["reason"] = "no vintage"
            return rec
        s = resolve_state(state, truth_csv=vf, locations_csv=LOCS,
                          season_start=season_start, as_of=asof)
        suffix = f"{state.replace(' ', '_')}_flu"
        m = materialize_model(s, MIN_TEMPLATE if min_model else TEMPLATE,
                              W / "m.bngl", suffix)
        e = write_exp(s, W / f"{suffix}.exp")
        c = write_conf(s, model=m, exp=e, out_dir=out_dir, conf_path=W / "c.conf",
                       bng_command=BNG, max_iterations=iters,
                       burn_in=max(50, iters // 4), adaptive=max(50, iters // 4),
                       priors=dict(priors), population_size=chains)

        adaptive = out_dir / "adaptive_files"
        can_continue = warm and (adaptive / "diffMatrix.txt").is_file()
        # REPLACE, do not append: write_conf already emits a continue_run line,
        # and PyBNF rejects a duplicated key outright --
        #   "Config key 'continue_run' is specified multiple times"
        # which surfaced only as returncode 1 with an empty stderr.
        txt = c.read_text()
        val = "1" if can_continue else "0"
        if re.search(r"^continue_run\s*=", txt, re.M):
            txt = re.sub(r"^continue_run\s*=.*$", f"continue_run = {val}", txt, flags=re.M)
        else:
            txt += f"\ncontinue_run = {val}\n"
        c.write_text(txt)
        rec["continued"] = bool(can_continue)

        r = run_pybnf(c, pybnf_binary=PYBNF, cwd=W / "sc", timeout_sec=timeout)
        rec["elapsed"] = r.get("elapsed", 0)
        if not r["ok"]:
            rec["reason"] = (r.get("reason") or r.get("stderr_tail", ""))[-200:]
            return rec

        runs = out_dir / "Results" / "A_MCMC" / "Runs"
        post = read_posterior(runs, priors)
        if post is None:
            rec["reason"] = "no readable posterior"
            return rec
        rec["medians"] = post.medians
        rec["objective"] = post.objective
        rec["pinned"] = pinned_parameters(post, priors)
        rec["n_obs"] = int(s.n_obs)

        g = sorted(runs.glob("*traj_noise*"))
        if g:
            tr = np.genfromtxt(g[0])
            if tr.ndim == 1:
                tr = tr.reshape(1, -1)
            if s.n_obs + 3 < tr.shape[1]:
                rec["samples"] = {str(h): tr[:, s.n_obs - 1 + h].tolist()
                                  for h in (0, 1, 2, 3, 4)}
                rec["last_observed"] = float(s.observed[-1])
        rec["ok"] = True
    except Exception as exc:
        rec["reason"] = f"{type(exc).__name__}: {exc}"[:200]
    finally:
        # scratch goes; `out_dir` (adaptive_files + Results) deliberately stays
        shutil.rmtree(W, ignore_errors=True)
    return rec


def prune(out_dir: Path, keep_samples: bool = True) -> None:
    """Keep adaptive_files (warm start) and drop the rest of PyBNF's output."""
    ad = out_dir / "adaptive_files"
    if not ad.is_dir():
        return
    for child in out_dir.iterdir():
        if child.name == "adaptive_files":
            continue
        if keep_samples and child.name == "Results":
            continue
        shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", nargs="+", required=True)
    ap.add_argument("--asofs", nargs="+", required=True)
    ap.add_argument("--season-start", default="2025-08-01")
    ap.add_argument("--root", default="/tmp/weekly_loop")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--probe-iters", type=int, default=2000)
    ap.add_argument("--budget-min", type=float, default=60.0)
    ap.add_argument("--clean-required", type=int, default=2)
    ap.add_argument("--max-probes", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=7200.0)
    ap.add_argument("--min-model", action="store_true")
    ap.add_argument("--chains", type=int, default=4,
                    help="population_size, which IS the chain count in PyBNF. "
                         "4 was chosen on a measured 2x2 (ESS 44 vs 9 at 1 chain) "
                         "but that was COLD; warm starts may change it. R-hat "
                         "cannot be computed at all with 1.")
    ap.add_argument("--seed-iters", type=int, default=0,
                    help="one long COLD run before week 1, to converge before "
                         "the weekly loop ever starts. 0 disables.")
    ap.add_argument("--seed-asof", default=None,
                    help="as-of date for the seed run; defaults to the week "
                         "before the first competition week")
    ap.add_argument("--out", default="backtest_results/weekly_loop.json")
    a = ap.parse_args()

    plan = LoopPlan(budget_s=a.budget_min * 60, probe_iters=a.probe_iters,
                    clean_rounds_required=a.clean_required,
                    max_probe_rounds=a.max_probes, n_states=len(a.states))
    # PER-STATE priors (task #27): the old shared dict meant one pathological
    # state widened everyone's bounds -- and posterior spread is 83% of this
    # model's measured gap. Each state's box now widens only on its own pins,
    # from its own medians.
    pstate = {s: dict(MIN_PRIORS) for s in a.states}
    results, t0 = [], time.time()
    print(f"[loop] {len(a.states)} states x {len(a.asofs)} weeks | "
          f"probe {a.probe_iters} iters | budget {a.budget_min:.0f} min/week",
          flush=True)

    # ---- SEED: one long cold fit before the loop begins ----------------
    #
    # A competition week is a small perturbation of a converged state, so the
    # loop assumes it starts from one. Without this, week 1 begins cold at the
    # probe iteration count and pins nearly every parameter -- observed at
    # 1000 iters, three of five parameters against a wall on round 0. The real
    # season has months of quiet data before the first submission; this is that.
    if a.seed_iters:
        seed_asof = a.seed_asof or (
            pd.Timestamp(a.asofs[0]) - pd.Timedelta(days=7)).date().isoformat()
        print(f"[seed] cold start, {a.seed_iters} iters, as-of {seed_asof}",
              flush=True)
        jobs = [(s, seed_asof, a.season_start, a.root, a.seed_iters, a.timeout,
                 pstate[s], False, bool(a.min_model), a.chains) for s in a.states]
        recs = []
        with ProcessPoolExecutor(max_workers=a.jobs) as ex:
            for fu in as_completed([ex.submit(one_fit, j) for j in jobs]):
                try:
                    recs.append(fu.result())
                except Exception as exc:
                    recs.append({"ok": False, "reason": str(exc)[:150]})
        ok = [r for r in recs if r.get("ok")]
        pins = sorted({p for r in ok for p in r.get("pinned", [])})
        print(f"[seed] {len(ok)}/{len(recs)} converged | pinned: {pins or '-'} | "
              f"{np.median([r.get('elapsed',0) for r in ok])/60:.0f} min median",
              flush=True)
        for r in ok:                                   # per-state widening
            if r.get("pinned") and "medians" in r:
                pr = pstate[r["state"]]
                newp = next_priors(diagnose(list(r["pinned"]), r["medians"], pr), pr)
                pstate[r["state"]] = {k: newp.get(k, pr[k]) for k in pr}
                print(f"[seed] {r['state']} widened on {sorted(r['pinned'])}",
                      flush=True)
        for s in a.states:
            prune(state_dir(Path(a.root), s) / "res")

    trusted = False          # previous week clean + bounds unchanged?
    for wi, asof in enumerate(a.asofs):
        wk_start, rounds, best = time.monotonic(), 0, {}
        # Trusted start (task #27): re-proving last week's cleanliness burns
        # budget demonstrating the demonstrated -- 18/18 weeks spent 2-3
        # probes at 0% pinning. Trust is one week deep.
        clean_streak = a.clean_required if trusted else 0
        stable = True
        week_changed = False
        while True:
            spent = (time.monotonic() - wk_start)
            if rounds >= a.max_probes or clean_streak >= a.clean_required:
                iters = plan.affordable_iters(plan.budget_s - spent)
                kind = "commit"
            else:
                iters, kind = a.probe_iters, "probe"
                if plan.budget_s - spent < plan.round_cost_s(iters):
                    iters, kind = plan.affordable_iters(plan.budget_s - spent), "commit"
            if iters < 500:
                break

            warm = bool(a.seed_iters) or (wi > 0) or rounds > 0
            jobs = [(s, asof, a.season_start, a.root, iters, a.timeout,
                     pstate[s], warm, bool(a.min_model), a.chains) for s in a.states]
            recs = []
            with ProcessPoolExecutor(max_workers=a.jobs) as ex:
                for fu in as_completed([ex.submit(one_fit, j) for j in jobs]):
                    try:
                        recs.append(fu.result())
                    except Exception as exc:
                        recs.append({"ok": False, "reason": str(exc)[:150]})
            ok = [r for r in recs if r.get("ok")]
            allpins = sorted({p for r in ok for p in r.get("pinned", [])})
            frac = np.mean([bool(r.get("pinned")) for r in ok]) if ok else 1.0
            print(f"  {asof} r{rounds} {kind:<6} {iters:>5} iters  "
                  f"{len(ok)}/{len(recs)} ok  pinned {frac:.0%}  {allpins or '-'}  "
                  f"({(time.monotonic()-wk_start)/60:.0f} min)", flush=True)

            changed = False
            if allpins:
                # PER-STATE widening; WIDEN ONLY -- never drop a parameter
                # (next_priors' eps1-floor rule is SUPERSEDED and fatal here:
                # the template still declares eps1__FREE, so a conf without it
                # stops matching the model; observed as silent 0/2 rounds).
                for r in ok:
                    if r.get("pinned") and "medians" in r:
                        pr = pstate[r["state"]]
                        newp = next_priors(
                            diagnose(list(r["pinned"]), r["medians"], pr), pr)
                        newp = {k: newp.get(k, pr[k]) for k in pr}
                        if newp != pr:
                            changed = True
                            pstate[r["state"]] = newp
                clean_streak, stable = 0, not changed
                week_changed = week_changed or changed
            else:
                clean_streak = clean_streak + 1 if stable else 1
                stable = True
                best = {r["state"]: r for r in ok}     # completed + clean
            if not best:
                best = {r["state"]: r for r in ok}
            rounds += 1
            if kind == "commit":
                break

        trusted = (clean_streak >= a.clean_required) and not week_changed

        for r in best.values():
            r["asof"] = asof
            results.append(r)
        for s in a.states:
            prune(state_dir(Path(a.root), s) / "res")
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(results))
        print(f"  {asof} done: {len(best)} states kept, priors now "
              f"{ {k: tuple(round(x,4) for x in v) for k,v in priors.items()} }",
              flush=True)

    print(f"[loop] {len(results)} records, {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
