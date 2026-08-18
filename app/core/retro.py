"""Season-as-competition retrospective: run every vintage week like a real
submission day, score against settled truth, aggregate.

Engineering rules (each one paid for):
  * RESUMABLE: each week is a checkpoint; completed weeks are detected and
    never redone (a crash costs one week, not a season).
  * one ledger run per season; per-week artifacts under weeks/<date>/.
  * members: pf (seeded, replicated) + analogue + LOSO-honest ensemble --
    for retrospectives the blend weight NEVER comes from the season being
    scored (self-grading); callers pass weights fitted elsewhere.
  * parallel width: PF cells sharded across N runner subprocesses (entry-point
    files, never stdin -- macOS spawn rule).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core.data import ARCHIVE, LOCATIONS          # noqa: E402
from app.core.engines import analogue as an_engine    # noqa: E402
from app.core.engines import pf as pf_engine          # noqa: E402
from app.core import ensemble as ens                  # noqa: E402
from app.core.runs import RunSpec                     # noqa: E402

SEASON_BOUNDS = {"2023-24": ("2023-08-01", "2024-06-15"),
                 "2024-25": ("2024-08-01", "2025-06-15"),
                 "2025-26": ("2025-08-01", "2026-06-15")}


def season_vintages(season: str) -> list:
    lo, hi = SEASON_BOUNDS[season]
    return [v for v in sorted(p.name.split("_")[-1].removesuffix(".csv")
                              for p in ARCHIVE.glob("target-hospital-admissions_*.csv"))
            if lo <= v <= hi]


def _week_dir(root: Path, asof: str) -> Path:
    return root / "weeks" / asof


def week_done(root: Path, asof: str) -> bool:
    return (_week_dir(root, asof) / "samples.json").is_file()


def run_week(root: Path, season: str, asof: str, locations: list,
             replicates: int = 3, particles: int = 10_000,
             width: int = 4) -> dict:
    """One submission day: PF (sharded) + analogue; store samples+quantiles."""
    wd = _week_dir(root, asof)
    if week_done(root, asof):
        return json.loads((wd / "samples.json").read_text())
    wd.mkdir(parents=True, exist_ok=True)
    spec = RunSpec(engine="retro", forecast_date=asof, locations=locations,
                   season_start=SEASON_BOUNDS[season][0],
                   replicates=replicates, particles=particles)
    cells = pf_engine.prepare(spec, wd)
    # shard cells across width runner subprocesses
    shards = [cells[i::width] for i in range(width) if cells[i::width]]
    procs = []
    for i, shard in enumerate(shards):
        sj = wd / f"cells_{i}.json"
        sj.write_text(json.dumps(shard))
        runner = wd / f"runner_{i}.py"
        runner.write_text(pf_engine._RUNNER.format(
            pybnf_path=str(pf_engine.PYBNF_PF), cells_json=str(sj),
            out_json=str(wd / f"status_{i}.json")))
        procs.append(subprocess.Popen([str(pf_engine.PY_ENGINE
                     if hasattr(pf_engine, 'PY_ENGINE') else pf_engine.PY310),
                     str(runner)], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL))
    for p in procs:
        p.wait(timeout=7200)
    pf_samples = pf_engine.collect(wd)
    an_q = an_engine.run(spec)
    out = {"asof": asof,
           "pf": pf_samples,
           "analogue": {loc: {h: {str(k): v for k, v in q.items()}
                              for h, q in qs.items()}
                        for loc, qs in an_q.items()}}
    (wd / "samples.json").write_text(json.dumps(out))
    return out


def run_season(root: Path, season: str, locations: list, replicates=3,
               particles=10_000, width=4, progress=None) -> list:
    root.mkdir(parents=True, exist_ok=True)
    done = []
    for asof in season_vintages(season):
        try:
            run_week(root, season, asof, locations, replicates, particles, width)
            done.append(asof)
        except Exception as e:                      # a bad week never kills the season
            (root / "failures.log").open("a").write(f"{asof}: {e}\n")
        if progress:
            progress(asof)
    return done


def score_season(root: Path, season: str, ensemble_weights: dict | None = None) -> pd.DataFrame:
    """Score every stored week vs settled truth. `ensemble_weights` must be
    LOSO for this season (never fitted on it)."""
    from app.core.scoring import _baseline_cells, load_truth
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
    from flubnf.wis import wis as wis_fn
    from datetime import timedelta
    truth, n2f = load_truth()
    rows = []
    for wk in sorted((root / "weeks").glob("*/samples.json")):
        d = json.loads(wk.read_text())
        asof = d["asof"]; T = pd.Timestamp(asof)
        for loc in set(d["pf"]) | set(d["analogue"]):
            fips = n2f.get(loc)
            if not fips:
                continue
            pf_q = (ens.member_quantiles_from_samples(d["pf"][loc])
                    if loc in d["pf"] else {})
            an_q = ({h: {float(k): v for k, v in q.items()}
                     for h, q in d["analogue"][loc].items()}
                    if loc in d["analogue"] else {})
            members = {}
            if pf_q: members["pf"] = pf_q
            if an_q: members["analogue"] = an_q
            blend = ens.vincentize(members, weights=ensemble_weights,
                                   location_fips=fips) if members else {}
            for model, qs in (("pf", pf_q), ("analogue", an_q),
                              ("ensemble", blend)):
                for h in ("1", "2", "3", "4"):
                    q = qs.get(h)
                    if not q:
                        continue
                    actual = truth.get((fips, T + timedelta(days=7 * int(h))))
                    if actual is None or actual <= 0 or q[0.5] <= 0:
                        continue
                    try:
                        w = float(wis_fn(q, actual).wis)
                    except Exception:
                        continue
                    rows.append({"model": model, "location": loc, "fips": fips,
                                 "asof": asof, "horizon": int(h) - 1, "wis": w})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # baseline per asof (the validated construction)
    bases = {}
    for asof in df["asof"].unique():
        bs = _baseline_cells(asof, set(df[df["asof"] == asof].fips), truth)
        for k, v in bs.items():
            bases[k] = v
    df["base_wis"] = [bases.get((r.fips, r.asof, r.horizon), np.nan)
                      for r in df.itertuples()]
    df = df.dropna(subset=["base_wis"])
    df["rel"] = df.wis / df.base_wis
    return df
