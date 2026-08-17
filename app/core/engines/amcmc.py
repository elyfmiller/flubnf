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


def execute(spec, workroot: Path, budget_min: float = 90.0,
            seed_iters: int = 12000, timeout_s: float = 6 * 3600) -> dict:
    out_json = workroot / "amcmc.json"
    cmd = [sys.executable, str(REPO / "scripts/weekly_loop_run.py"),
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
