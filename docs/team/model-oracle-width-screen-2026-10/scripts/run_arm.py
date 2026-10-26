"""Replay one arm of the Oracle SIHRS width screen: the seasons' scoreable
as-of weeks (those with a FluSight-baseline file) through `flubnf retro run`,
one root per season, the knobs given on the command line.

    run_arm.py <arm> <root_parent> [--seasons 2023-24,...] [--locations ...]
               [--knob key=value ...] [--weeks 2024-12-07,...]
               [--season-knob 2024-25:key=value ...] [--hs-table boxes.json]
               [--all-weeks] [--keep-params]

--season-knob sets a knob for one season's root only (HP's per-season box).
--hs-table writes per-jurisdiction eps1/phi1 boxes into each cell's pf.conf
after prepare() and before the runners (HS; the console has no
per-location prior); cells.json's prior_ranges records what ran.
--all-weeks keeps weeks with no FluSight-baseline file (the season-end
fits); --keep-params holds off the week pruner so each cell's saved
cloud (out/pf_state.npz) stays; --oracle-none fits the plain filter (the
fits need only its parameters, and the step refuses 2022-23, which has no
earlier season for the FluSurv-NET shrink); --aux none gives the week the
bare analogue for the same reason (the Groundhog is not read here).

The worktree, hub and engine come from env.sh (sourced by the caller).
Nothing here changes how a week is fitted: the vintage list is the only
thing narrowed (app.core.retro.season_vintages), so every week is the
console's own replay week.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

WT = Path(os.environ["SCREEN_WT"])
sys.path.insert(0, str(WT))

BASELINE_DIR = Path(os.environ["SCREEN_BASELINE"])


def scoreable(asof: str) -> bool:
    ref = (date.fromisoformat(asof) + timedelta(days=7)).isoformat()
    return (BASELINE_DIR / f"{ref}-FluSight-baseline.csv").is_file()


HS_SEASON = [None]


def install_hs(table: dict) -> None:
    """Rewrite each prepared cell's eps1/phi1 prior lines from `table`
    ({season: {location: {"eps1": [lo, hi], "phi1": [lo, hi]}}}) after
    app.core.retro._prepare_week, before the runners read the confs. A
    location missing from the table keeps the box it was prepared with."""
    from app.core import retro
    orig = retro._prepare_week

    def hooked(root, asof, spec, manifest):
        cells = orig(root, asof, spec, manifest)
        boxes = table[HS_SEASON[0]]
        for c in cells:
            b = boxes.get(c["location"])
            if not b:
                continue
            conf = Path(c["dir"]) / "pf.conf"
            lines = conf.read_text().splitlines()
            out = []
            for ln in lines:
                for name in ("eps1", "phi1"):
                    if ln.startswith(f"uniform_var = {name}__FREE "):
                        lo, hi = b[name]
                        ln = f"uniform_var = {name}__FREE {lo:.6g} {hi:.6g}"
                out.append(ln)
            conf.write_text("\n".join(out) + "\n")
            c["prior_ranges"] = {**(c.get("prior_ranges") or {}),
                                 "eps1__FREE": list(b["eps1"]),
                                 "phi1__FREE": list(b["phi1"]),
                                 "_hook": "run_arm.install_hs"}
        wd = Path(root) / "weeks" / asof
        (wd / "cells.json").write_text(json.dumps(cells, indent=1))
        return cells

    retro._prepare_week = hooked


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("arm")
    ap.add_argument("root_parent")
    ap.add_argument("--seasons", default="2023-24,2024-25,2025-26")
    ap.add_argument("--locations", default="all")
    ap.add_argument("--replicates", type=int, default=3)
    ap.add_argument("--knob", action="append", default=[])
    ap.add_argument("--weeks", default="")
    ap.add_argument("--season-knob", action="append", default=[])
    ap.add_argument("--hs-table", default="")
    ap.add_argument("--all-weeks", action="store_true")
    ap.add_argument("--keep-params", action="store_true")
    ap.add_argument("--oracle-none", action="store_true")
    ap.add_argument("--aux", default="")
    a = ap.parse_args()

    from app.core import retro
    from flubnf import cli_retro

    full = retro.season_vintages
    only = set(w for w in a.weeks.split(",") if w)

    def narrowed(season):
        return [v for v in full(season)
                if (a.all_weeks or scoreable(v)) and (not only or v in only)]

    retro.season_vintages = narrowed
    if a.keep_params:
        from app.core import reclaim
        reclaim.prune_week = lambda wd: 0
        reclaim.prune_season = lambda root: {"bytes": 0, "weeks": 0}
    if a.hs_table:
        install_hs(json.loads(Path(a.hs_table).read_text()))
    parent = Path(a.root_parent) / a.arm
    parent.mkdir(parents=True, exist_ok=True)
    for season in a.seasons.split(","):
        weeks = narrowed(season)
        log = {"arm": a.arm, "season": season, "weeks": weeks,
               "knobs": a.knob, "locations": a.locations,
               "replicates": a.replicates,
               "start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        (parent / f"{season}.launch.json").write_text(json.dumps(log, indent=1))
        sk = [x.split(":", 1)[1] for x in a.season_knob
              if x.split(":", 1)[0] == season]
        log["season_knobs"] = sk
        log["hs_table"] = a.hs_table or None
        (parent / f"{season}.launch.json").write_text(json.dumps(log, indent=1))
        print(f"[{a.arm}] {season}: {len(weeks)} weeks {sk}", flush=True)
        HS_SEASON[0] = season
        cli_retro.retro_cmd(season=season, locations=a.locations, width=0,
                            replicates=a.replicates,
                            root=str(parent / season), aux=a.aux,
                            oracle="none" if a.oracle_none else "",
                            knob=list(a.knob) + sk)


if __name__ == "__main__":
    main()
