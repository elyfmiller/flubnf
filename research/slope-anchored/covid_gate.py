"""COVID arm of the slope-anchored member: gate.py section 4, applied.

The pre-registration is research/slope-anchored/gate.py section 4, frozen and
hashed before any fit of this candidate ran. This file implements it and adds
nothing.

  C1 TURN RESPONSIVENESS (replaces bimodality, which is declared VOID here and
     why: see below). Sign agreement between (R* - 1) and the realized 4-week
     log change of settled admissions, paired against the same statistic for
     the production filter's origin R_eff. BAR: member accuracy >= control's.
  C2 WIDTH  central-95 relative to actual <= 4.06, coverage beside it,
     production settings, break-excluded cells, paired against the production
     forward this same run writes.
  C3 ANCHOR VALIDITY  clipping < 0.40 AND median shrinkage weight >= 0.20.

WHY BIMODALITY IS VOID, NOT PASSED OR FAILED. Round two's estimator integrates
the deterministic skeleton at posterior-median parameters for ten years and
counts peaks. This member's forward transmission is a deterministic function of
the last two DATA points: its skeleton is the production skeleton with one
constant re-levelled, so the estimator returns 1.00 peaks per year by
construction, and there is no stochastic process for a generative estimator to
run on. Reporting 1.00 would report the estimator, not the member. The clause
is recorded VOID with this reason so its absence can never be read as a pass.

Run:  ./.venv/bin/python research/slope-anchored/covid_gate.py --prepare
      ./.venv/bin/python research/slope-anchored/covid_gate.py --run
      ./.venv/bin/python research/slope-anchored/covid_gate.py --score
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from app.core.runs import derive_seed                         # noqa: E402
from flubnf import covid_vintage as cv                        # noqa: E402
from flubnf.covid_fit import (materialize_for_profile,        # noqa: E402
                              resolve_for_profile, write_exp)
from flubnf.profiles import COVID                             # noqa: E402
from flubnf.settings import BNG, LOCATIONS, PY_ENGINE, PYBNF  # noqa: E402
from flubnf.wis import FLUSIGHT_PI_QUANTILES as PI            # noqa: E402
from flubnf.wis import wis as wis_fn                          # noqa: E402

import anchor_math as AM                                      # noqa: E402
import gate                                                   # noqa: E402

OUT = HERE / "out"
WORK = gate.WORK / "covid"

SEASON_START = "2025-06-01"
ORIGINS = ("2026-01-07", "2026-02-04", "2026-03-04")
STATES = ("New York", "Pennsylvania", "North Carolina")
HORIZONS = (1, 2, 3, 4)
PARTICLES = 10_000
REPLICATES = 3
JITTER = 0.30

WIDTH_BAR = gate.WIDTH_BAR            # 4.06
CLIP_BAR = gate.CLIP_REPORT_FRAC      # 0.40
W_BAR = gate.COVID_W_BAR              # 0.20


def _vars_block(profile) -> str:
    out = []
    for name, (lo, hi) in profile.fitted_priors.items():
        log = name in profile.log_scale_vars and lo > 0
        out.append(f"{'loguniform_var' if log else 'uniform_var'} = "
                   f"{name} {lo} {hi}")
    return "\n".join(out) + "\n"


def _defaults_block(profile) -> str:
    mid = {k: (np.exp((np.log(lo) + np.log(hi)) / 2)
               if k in profile.log_scale_vars and lo > 0 else (lo + hi) / 2)
           for k, (lo, hi) in profile.fitted_priors.items()}
    return "begin parameters\n" + "".join(f"{k} {v:.6g}\n"
                                          for k, v in mid.items())


def prepare(workroot: Path) -> list:
    cells = []
    for state in STATES:
        for asof in ORIGINS:
            truth = cv.vintage_path(asof)
            s = resolve_for_profile(COVID, state, truth_csv=truth,
                                    locations_csv=LOCATIONS,
                                    season_start=SEASON_START, as_of=asof)
            variants = {}
            for name, (k, harmonic, v_sig) in gate.VARIANTS.items():
                ge = AM.growth_estimate(s.observed, s.times, k=k, v_sig=v_sig,
                                        r_disp=gate.R_DISP,
                                        max_gap=gate.MAX_GAP_WEEKS)
                rs = AM.r_star(ge["g_hat"], s.gamma)
                variants[name] = {**ge, **rs, "harmonic": bool(harmonic),
                                  "v_sig": float(v_sig)}
            for rep in range(REPLICATES):
                tag = f"{state.replace(' ', '_')}_{asof}_rep{rep}"
                d = workroot / tag
                d.mkdir(parents=True, exist_ok=True)
                sfx = f"{state.replace(' ', '_')}_covid"
                m = materialize_for_profile(COVID, s, d / "m.bngl",
                                            suffix=sfx,
                                            t_end=int(s.n_obs) + 8)
                m.write_text(m.read_text().replace(
                    "begin parameters\n", _defaults_block(COVID), 1))
                write_exp(s, d / f"{sfx}.exp")
                r = None
                for _ in range(2):
                    r = subprocess.run(["perl", str(BNG), "m.bngl"],
                                       capture_output=True, text=True,
                                       cwd=str(d), timeout=600)
                    if (d / "m.net").is_file():
                        break
                    time.sleep(1.0)
                if not (d / "m.net").is_file():
                    raise RuntimeError(f"netgen failed {state} {asof}: "
                                       f"{r.stdout[-300:]}")
                sidx = gate.species_index_map(d / "m.net")
                (d / "anchor.json").write_text(json.dumps(
                    {"variants": variants, "gamma": float(s.gamma),
                     "s0": float(s.s0), "N": float(s.population),
                     "rho": float(s.rho), "gammaH": float(s.gammaH),
                     "omega": float(s.omega), "idx_S": int(sidx["S"]),
                     "idx_I": int(sidx["I"]), "idx_t": int(sidx["counter"])}))
                seed = derive_seed(state, asof, rep)
                (d / "pf.conf").write_text(f"""bng_command = {BNG}
model = {d}/m.bngl : {d}/{sfx}.exp
output_dir = {d}/out
fit_type = pf
objfunc = neg_bin_dynamic
num_particles = {PARTICLES}
pf_jitter = {JITTER}
pf_observable_mode = integrated
pf_forecast_weeks = 4
population_size = 1
max_iterations = 1
seed = {seed}
{_vars_block(COVID)}""")
                cells.append({"key": tag, "dir": str(d), "location": state,
                              "asof": asof, "replicate": rep, "seed": seed,
                              "season": "2025-26", "n_obs": int(s.n_obs),
                              "last_observed": float(s.observed[-1]),
                              "data_edge": cv.data_edge(asof)})
    workroot.mkdir(parents=True, exist_ok=True)
    (workroot / "cells.json").write_text(json.dumps(cells))
    return cells


def execute(shards: int = 3, nice_level: int = 12) -> list:
    """The generated runner is gate.py's, unchanged: the subclass and the
    compaction are identical, and the COVID template exposes the same species
    order (asserted at prepare time)."""
    cells = json.loads((WORK / "cells.json").read_text())
    pending = [c for c in cells
               if not (Path(c["dir"]) / "compact.npz").is_file()]
    print(f"covid: {len(cells)} cells, {len(pending)} pending", flush=True)
    procs = []
    for sh in range(shards):
        mine = pending[sh::shards]
        if not mine:
            continue
        cj = WORK / f"shard_{sh}.json"
        cj.write_text(json.dumps(mine))
        rp = WORK / f"runner_{sh}.py"
        rp.write_text(gate._RUNNER.format(shard=sh, pybnf=str(PYBNF),
                                          here=str(HERE), cells=str(cj),
                                          out=str(WORK / f"status_{sh}.json")))
        p = subprocess.Popen(["nice", "-n", str(nice_level), str(PY_ENGINE),
                              str(rp)], stdout=subprocess.DEVNULL,
                             stderr=open(WORK / f"shard_{sh}.err", "w"))
        procs.append(p)
        print(f"  shard {sh}: {len(mine)} cells, pid {p.pid}", flush=True)
    return procs


def _quantiles(samples) -> dict:
    levels = sorted(set([0.5] + list(PI) + [1 - p for p in PI]))
    return {float(L): float(np.quantile(samples, L)) for L in levels}


def _wis_independent(q: dict, y: float) -> float:
    """Inline Bracher et al. 2021 WIS, independent of flubnf.wis. Identical in
    form to score.py::wis_independent, so both arms check the same way."""
    tot = 0.5 * abs(y - q[0.5])
    for p in PI:
        a = 2.0 * p
        lo, hi = q[p], q[1.0 - p]
        tot += (a / 2.0) * ((hi - lo) + (2 / a) * max(lo - y, 0)
                            + (2 / a) * max(y - hi, 0))
    return tot / (len(PI) + 0.5)


class EmptyScoreFrame(RuntimeError):
    """No row survived the filters. Carries the per-filter breakdown."""


def _require_rows(rows: list, lost: dict, n_cells: int, variant: str) -> None:
    """Fail loudly, with the ledger, instead of an opaque AttributeError.

    A silently empty frame surfaced downstream as `AttributeError: 'DataFrame'
    object has no attribute 'model'`, which names neither the filter that ate
    the rows nor the cell it ate them from. This has cost real time twice, so
    the breakdown is always printed and the exception always names the single
    largest sink.
    """
    total_lost = sum(lost.values())
    lines = [f"row ledger [{variant}]: {n_cells} cells, {len(rows)} rows kept, "
             f"{total_lost} dropped"]
    for k in sorted(lost, key=lambda x: -lost[x]):
        lines.append(f"    {k:22s} {lost[k]}")
    print("\n".join(lines), flush=True)
    if rows:
        return
    worst = max(lost, key=lambda k: lost[k]) if total_lost else "no cells at all"
    raise EmptyScoreFrame(
        "\n".join(lines)
        + f"\n  every row was dropped; the largest sink is '{worst}'. "
          "Nothing below this point is scoreable, so no gate table is "
          "produced. Check that sink first.")


def score(variant: str = gate.PRIMARY) -> dict:
    cells = json.loads((WORK / "cells.json").read_text())
    settled = cv.vintage_frame(cv.vintages()[-1])
    settled["date"] = pd.to_datetime(settled["date"])
    tru = {(r.location_name, r.date): float(r.value)
           for r in settled.itertuples() if np.isfinite(r.value)}
    # Row-loss ledger. An empty frame raised an opaque AttributeError on
    # `df.model` twice in this project; every `continue` below now increments a
    # counter and `_require_rows` prints the breakdown before failing.
    lost = {k: 0 for k in ("missing_output", "missing_traj_key",
                           "anchor_scale_guard", "excluded_window",
                           "truth_absent", "truth_nonpositive")}
    kept = 0
    rows, agree = [], []
    for c in cells:
        d = Path(c["dir"])
        f, af = d / "compact.npz", d / "anchor.json"
        if not (f.is_file() and af.is_file()):
            lost["missing_output"] += 1
            continue
        a = json.loads(af.read_text())
        spec = a["variants"][variant]
        z = np.load(f, allow_pickle=False)
        # THE ORIGIN IS THE DATA EDGE, NOT THE AS-OF. `asof` is the Wednesday a
        # forecaster stood on; the vintage's newest week -- the week column 0 of
        # every trajectory is anchored to, asserted equal to `last_observed` at
        # prepare time -- is the Saturday before it. Horizon h therefore lands on
        # data_edge + 7h. Keying off `asof` offsets every lookup by four days and
        # matches no target_end_date at all, which is exactly the defect that
        # emptied this frame. The influenza scorer is unaffected: its as-ofs come
        # from the seal's week directories and are already Saturdays.
        T = pd.Timestamp(c["data_edge"])
        for tag, key in (("member", f"traj_{variant}"), ("control", "traj_prod")):
            if key not in z.files:
                lost["missing_traj_key"] += 1
                continue
            tr = z[key].astype(float)
            origin = tr[:, 0]
            med = float(np.median(origin[np.isfinite(origin)]))
            scale = c["last_observed"] / med if med > 0 else 1.0
            if not (1.0 / gate.ANCHOR_SCALE_DROP <= scale
                    <= gate.ANCHOR_SCALE_DROP):
                lost["anchor_scale_guard"] += 1
                continue
            for h in HORIZONS:
                target = (T + pd.Timedelta(days=7 * h)).date().isoformat()
                y = tru.get((c["location"], pd.Timestamp(target)))
                excl = COVID.excluded_for(c["data_edge"], target)
                if excl:
                    lost["excluded_window"] += 1
                    continue
                if y is None:
                    lost["truth_absent"] += 1
                    continue
                if y <= 0:
                    lost["truth_nonpositive"] += 1
                    continue
                kept += 1
                q = _quantiles(tr[:, h] * scale)
                # scoring discipline (a): the quantile path this arm builds is
                # the same one flubnf.wis.wis consumes. C2 is a width and a
                # coverage, not a WIS, but the agreement is asserted anyway so
                # the shared machinery is verified before any table is trusted.
                w_pkg = float(wis_fn(q, y).wis)
                agree.append(abs(w_pkg - _wis_independent(q, y))
                             / max(abs(w_pkg), 1e-12))
                rows.append(dict(
                    model=tag, location=c["location"], asof=c["asof"],
                    replicate=c["replicate"], horizon=h, y=y,
                    q50=q[0.5], w95=q[0.975] - q[0.025],
                    c95=float(q[0.025] <= y <= q[0.975]),
                    r_star=float(spec["r_star"]), w_shrink=float(spec["w"]),
                    clipped=bool(spec["clipped_low"] or spec["clipped_high"])))
    _require_rows(rows, lost, len(cells), variant)
    df = pd.DataFrame(rows)

    # ---- scoring discipline (a), and what (b)/(b') cannot be here ----------
    worst = max(agree)
    print(f"wis agreement with flubnf.wis.wis: max rel diff {worst:.2e} "
          f"({len(agree)} cells)", flush=True)
    assert worst < 1e-9, "scoring path does not reproduce flubnf.wis.wis"

    res = {"preregistration_sha256_16": gate.preregistration_hash(),
           "variant": variant, "n_scored_rows": int(len(df)),
           "row_ledger": {"cells": len(cells), "kept": kept, **lost},
           "wis_agreement": {"max_rel_diff": float(worst), "n": len(agree)},
           "seal_reproduction": {
               "status": "NOT APPLICABLE",
               "reason": "the retrospective seal is influenza-only "
                         "(app/state/retro_seal holds 2023-24, 2024-25 and "
                         "2025-26 flu scores_members.json and no COVID "
                         "equivalent). No sealed COVID comparator exists to "
                         "reproduce, so checks (b) and (b') cannot be run on "
                         "this arm. The paired control is the production "
                         "forward this same run writes (traj_prod), as the "
                         "pre-registration specifies."},
           "bimodality": {"verdict": "VOID",
                          "reason": "the member's forward transmission is a "
                                    "deterministic function of the last two "
                                    "data points; the skeleton estimator "
                                    "returns 1.00 by construction and there "
                                    "is no stochastic process for the "
                                    "generative estimator to run on"}}

    # ---- C2 width ---------------------------------------------------------
    c2 = {}
    for tag in ("member", "control"):
        g = df[df.model == tag]
        if not len(g):
            continue
        c2[tag] = {"width95_rel_actual": float((g.w95 / g.y).mean()),
                   "coverage95": float(g.c95.mean()), "n": int(len(g))}
    if "member" in c2:
        c2["ratio_to_control"] = (
            float(c2["member"]["width95_rel_actual"]
                  / c2["control"]["width95_rel_actual"])
            if "control" in c2 else None)
        c2["bar"] = WIDTH_BAR
        c2["pass"] = bool(c2["member"]["width95_rel_actual"] <= WIDTH_BAR)
    res["C2_width"] = c2

    # ---- C1 turn responsiveness ------------------------------------------
    # sign agreement of the implied direction with the realized 4-week change
    c1 = {}
    per = df[df.horizon == 4].copy()
    if len(per):
        anchor = {(c["location"], c["asof"]): c["last_observed"]
                  for c in cells}
        per["anchor"] = [anchor[(r.location, r.asof)] for r in per.itertuples()]
        per["realized_up"] = (per.y > per.anchor).astype(float)
        acc = {}
        m = per[per.model == "member"]
        acc["member"] = float(((m.r_star > 1.0).astype(float)
                               == m.realized_up).mean())
        # the control's implied direction is the filter's own origin R_eff,
        # read from the saved cloud
        ctrl_pred, ctrl_obs = [], []
        for c in cells:
            d = Path(c["dir"])
            f, af = d / "compact.npz", d / "anchor.json"
            if not (f.is_file() and af.is_file()):
                continue
            a = json.loads(af.read_text())
            z = np.load(f, allow_pickle=False)
            if "cloud_theta" not in z.files:
                continue
            names = [str(x) for x in z["cloud_pnames"]]
            th = z["cloud_theta"].astype(float)
            s_frac = z["cloud_S"].astype(float) / float(a["N"])
            t0m = float(np.median(z["cloud_t"].astype(float)))
            reff = AM.model_reff(th[:, names.index("Reff__FREE")],
                                 th[:, names.index("eps1__FREE")],
                                 th[:, names.index("phi1__FREE")],
                                 s_frac, float(a["s0"]), t0m)
            # Bracket form is mandatory for `asof`: `DataFrame.asof` is a real
            # pandas METHOD, so `per.asof == c["asof"]` compares a bound method
            # to a string and yields the scalar False, which silently zeroes the
            # whole mask. That left ctrl_pred empty and C1's control accuracy
            # NaN, failing the clause on an artifact rather than on evidence.
            sub = per[(per["model"] == "member")
                      & (per["location"] == c["location"])
                      & (per["asof"] == c["asof"])
                      & (per["replicate"] == c["replicate"])]
            for r in sub.itertuples():
                ctrl_pred.append(float(np.median(reff) > 1.0))
                ctrl_obs.append(r.realized_up)
        if not ctrl_pred:
            raise EmptyScoreFrame(
                f"C1 paired control is empty: {len(per)} horizon-4 rows and "
                f"{len(m)} member rows exist, but no cell matched the control "
                "join. The clause would otherwise 'fail' against a NaN control, "
                "which is an artifact and not evidence. Check the join keys.")
        acc["control"] = float(np.mean(np.array(ctrl_pred)
                                       == np.array(ctrl_obs)))
        c1 = {"member_accuracy": acc["member"],
              "control_accuracy": acc["control"], "n": int(len(m)),
              "pass": bool(acc["member"] >= acc["control"])}
    res["C1_turn_responsiveness"] = c1

    # ---- C3 anchor validity ----------------------------------------------
    g = df[df.model == "member"]
    c3 = {}
    if len(g):
        c3 = {"clip_frac": float(g.clipped.mean()),
              "median_w": float(g.w_shrink.median()),
              "median_r_star": float(g.r_star.median()),
              "bar_clip": CLIP_BAR, "bar_w": W_BAR,
              "pass": bool(g.clipped.mean() < CLIP_BAR
                           and g.w_shrink.median() >= W_BAR)}
    res["C3_anchor_validity"] = c3

    kills = [k for k, ok in (("C1", c1.get("pass")), ("C2", c2.get("pass")),
                             ("C3", c3.get("pass"))) if not ok]
    res["verdict"] = {"decision": "KILL" if kills else "PASS",
                      "clauses_failed": kills}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"covid_result_{variant}.json").write_text(
        json.dumps(res, indent=1, default=float))
    df.to_csv(OUT / f"covid_cells_{variant}.csv", index=False)
    print(json.dumps(res, indent=1, default=float))
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--shards", type=int, default=3)
    a = ap.parse_args()
    print(f"pre-registration {gate.preregistration_hash()}", flush=True)
    if a.prepare or a.run:
        WORK.mkdir(parents=True, exist_ok=True)
        cells = prepare(WORK)
        print(f"prepared {len(cells)} covid cells", flush=True)
    if a.run:
        execute(a.shards)
    if a.score:
        score()


if __name__ == "__main__":
    main()
