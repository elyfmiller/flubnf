"""The Oracle weight screen's replays (Submission's request of 2026-11-27,
item 1): the seasons' scoreable as-of weeks through `flubnf retro run` in
today's live form, one root per season, keeping each week's filter samples.

    replay.py <out> [--seasons 2023-24,2024-25,2025-26] [--weeks w1,w2]
              [--locations all|Name,Name]

<out> gets replay/<season>/ (the season roots, as the console stores them),
filter/<season>/<asof>/ (the kept inputs, below) and <season>.launch.json.

Live form (submission.md, the 2026-11-21 and 11-28 rounds): replicates 3,
particles 10,000, the stage-rule seed (pf.seed_denominator
season_total_early), the Oracle step on at weight 0.25, narrowing 0.7. The
cap (output.tail_cap) is not a replay knob; the arms apply it to the hub
rows afterwards. The engine is the one FLUBNF_ENGINE names (the launcher
sets it); the hub is FLUBNF_HUB.

Kept per week, beside the replay rather than in the week's folder (the
replay prunes everything there but the samples record):
  pf_filter.json.gz  the filter's own samples before the Oracle step, as
                     app.core.oracle.write_filter_record stores a console
                     run's (the replay itself keeps only their quantiles)
  step_args.json     the arguments the replay passed to apply_week
                     (extra, weeks_to_drop, drop_same_day)
  floor_recent.json  the recent observations the output floor read
So an arm is apply_week(filter samples, other w and narrowing) then the
same floor, with no refit.

Nothing here changes how a week is fitted: the vintage list is narrowed to
the scoreable weeks (a FluSight-baseline file for the reference date), and
two functions are wrapped to copy what passes through them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

LIVE_KNOBS = ["pf.seed_denominator=season_total_early", "oracle.w=0.25",
              "oracle.narrow=0.7"]
REPLICATES = 3


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--seasons", default="2023-24,2024-25,2025-26")
    ap.add_argument("--weeks", default="")
    ap.add_argument("--locations", default="all")
    a = ap.parse_args()
    out = Path(a.out).resolve()

    from app.core import oracle as oracle_mod
    from app.core import retro
    from flubnf import cli_retro
    from flubnf import settings as S

    if not os.environ.get("FLUBNF_ENGINE"):
        sys.exit("name the engine: set FLUBNF_ENGINE (public or private)")
    baseline = S.HUB / "model-output" / "FluSight-baseline"

    def scoreable(asof: str) -> bool:
        ref = (date.fromisoformat(asof) + timedelta(days=7)).isoformat()
        return (baseline / f"{ref}-FluSight-baseline.csv").is_file()

    full = retro.season_vintages
    only = {w for w in a.weeks.split(",") if w}

    def narrowed(season):
        return [v for v in full(season) if scoreable(v) and (not only or v in only)]

    retro.season_vintages = narrowed
    season_now = [None]

    def keep_dir(asof: str) -> Path:
        d = out / "filter" / season_now[0] / asof
        d.mkdir(parents=True, exist_ok=True)
        return d

    orig_apply = oracle_mod.apply_week

    def apply_kept(pf_samples, asof, out_dir, **kw):
        d = keep_dir(asof)
        oracle_mod.write_filter_record(d, asof, pf_samples)
        (d / "step_args.json").write_text(json.dumps(
            {"asof": asof, "extra": kw.get("extra"),
             "weeks_to_drop": kw.get("weeks_to_drop", 0),
             "drop_same_day": kw.get("drop_same_day", False),
             "other_kwargs": sorted(k for k in kw
                                    if k not in ("extra", "weeks_to_drop", "drop_same_day"))},
            indent=1, default=str), encoding="utf-8")
        return orig_apply(pf_samples, asof, out_dir, **kw)

    oracle_mod.apply_week = apply_kept

    orig_recent = retro._floor_recent

    def recent_kept(spec, locations, drop_same_day):
        rec = orig_recent(spec, locations, drop_same_day)
        d = keep_dir(str(spec.forecast_date))
        (d / "floor_recent.json").write_text(json.dumps(
            {"asof": str(spec.forecast_date), "drop_same_day": bool(drop_same_day),
             "recent": rec}, indent=0), encoding="utf-8")
        return rec

    retro._floor_recent = recent_kept

    for season in a.seasons.split(","):
        season_now[0] = season
        weeks = narrowed(season)
        log = {"season": season, "weeks": weeks, "knobs": LIVE_KNOBS,
               "replicates": REPLICATES, "locations": a.locations,
               "engine": os.environ.get("FLUBNF_ENGINE"),
               "engine_public": S.engine_public(), "hub": str(S.HUB),
               "start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{season}.launch.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
        print(f"{season}: {len(weeks)} weeks, engine {log['engine']}", flush=True)
        cli_retro.retro_cmd(season=season, locations=a.locations, width=0,
                            replicates=REPLICATES, root=str(out / "replay" / season),
                            aux="", oracle="", knob=list(LIVE_KNOBS))
        log["end_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (out / f"{season}.launch.json").write_text(json.dumps(log, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
