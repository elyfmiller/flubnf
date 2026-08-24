"""The adaptive-MCMC engine: a thin wrap over the operational scripts.

Runs the warm-started weekly loop (optionally preceded by a convergence-bounded
pre-season seed) as a SUBPROCESS of the analysis venv — the scripts already
enforce entry-point pools, per-state priors, trusted weeks, and pruning.
Budget is the knob; competition use is the cross-check role, not the primary.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

#: The operational runner this engine drives. It is deliberately NOT part of
#: the wheel: scripts/ holds long-running operational entry points that need
#: the whole clone (templates, the hub, an engine venv), and shipping a
#: top-level `scripts` package into site-packages would collide with any
#: other distribution doing the same. So an installed copy can run the
#: console, the analogue engine, scoring and the reports, but not this
#: engine, and it must say so plainly instead of failing as "produced no
#: output". README's Install section states the same thing.
RUNNER = REPO / "scripts" / "weekly_loop_run.py"


def execute(spec, workroot: Path, budget_min: float = 90.0,
            seed_iters: int = 12000, timeout_s: float = 6 * 3600) -> dict:
    if not RUNNER.is_file():
        raise FileNotFoundError(
            f"the adaptive-MCMC engine needs the operational runner at "
            f"{RUNNER}, which is not present. It ships with a source clone "
            f"of the repository, not with a pip install; run this engine "
            f"from a clone, or use fit_type = pf, the shipped engine.")
    out_json = workroot / "amcmc.json"
    cmd = [sys.executable, str(RUNNER),
           "--min-model", "--chains", "2",
           "--states", *spec.locations,
           "--asofs", spec.forecast_date,
           "--season-start", spec.season_start,
           "--jobs", str(min(8, max(1, len(spec.locations)))),
           "--probe-iters", "10000",
           "--budget-min", str(budget_min),
           "--max-probes", "2",
           "--seed-iters", str(seed_iters),
           "--root", str(workroot / "amcmc_root"),
           "--out", str(out_json)]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       timeout=timeout_s, cwd=str(REPO))
    if not out_json.is_file():
        raise RuntimeError(f"amcmc produced no output: {r.stderr[-400:]}")
    return {"records": json.loads(out_json.read_text()), "stdout": r.stdout[-2000:]}


def collect(workroot: Path) -> dict:
    """location -> horizon-samples, matching the PF engine's shape."""
    out_json = workroot / "amcmc.json"
    if not out_json.is_file():
        return {}
    by_loc = {}
    for rec in json.loads(out_json.read_text()):
        if rec.get("ok") and "samples" in rec:
            by_loc[rec["state"]] = rec["samples"]
    return by_loc
