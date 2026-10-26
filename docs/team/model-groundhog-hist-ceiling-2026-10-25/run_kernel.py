"""The Groundhog in the shipped kernel form over one season (prereg
c9587ab57ab6db4b, the historical ceiling screen), on the replay machinery the
tail-cell screen used; every week's quantiles stored for the post-calibration
step. Usage: run_kernel.py <season> <out_root>"""
import gzip, json, os, subprocess, sys, time
from pathlib import Path
import pandas as pd
from app.core import groundhog as gh, retro, scoring
from app.core.engines import analogue as an_engine

def _git(path):
    """The commit, with '+dirty' when the tree differs from it."""
    sha = subprocess.run(["git", "-C", path, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", path, "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    return sha + ("+dirty" if dirty else "")
CODE_COMMIT = _git(os.environ["PYTHONPATH"]) if os.environ.get("PYTHONPATH") else "unknown"

def main(season, out_root):
    t0 = time.time()
    base = an_engine.aux_preset("flusurv")
    # the shipped form, declared as run_season declares it
    local = an_engine.effective_local_pools({"local_pools": an_engine.shipped_local_pools()})
    locations = gh.console_locations() + ["US"]
    n2f = gh._name2fips()
    truth, _ = scoring.load_truth()
    vintages = retro.season_vintages(season)
    out = Path(out_root) / season; out.mkdir(parents=True, exist_ok=True)
    forecasts, cells, cov = {}, [], []
    for i, asof in enumerate(vintages):
        extra = {**base(asof, i, vintages), "local_pools": dict(local)}
        q = gh.forecast_week(season, asof, locations, extra)
        forecasts[asof] = {loc: {h: {repr(float(L)): float(v) for L, v in lv.items()}
                                 for h, lv in hq.items()} for loc, hq in q.items()}
        c, v = gh.score_week(q, asof, n2f, truth)
        if not c.empty: c["asof"] = asof; cells.append(c)
        if not v.empty: v["asof"] = asof; cov.append(v)
    C = pd.concat(cells, ignore_index=True); V = pd.concat(cov, ignore_index=True)
    for df in (C, V): df["season"] = season
    meta = {"form": "shipped", "local_pools": local, "season": season, "aux": base.__name__,
            "prereg": "c9587ab57ab6db4b", "hub_commit": _git(os.environ["FLUBNF_HUB"]),
            "code_commit": CODE_COMMIT,
            "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with gzip.open(out / "forecasts.json.gz", "wt", encoding="utf-8") as f:
        json.dump({"meta": meta, "forecasts": forecasts}, f)
    C.to_csv(out / "cells.csv.gz", index=False); V.to_csv(out / "coverage.csv.gz", index=False)
    st = C[C.fips != "US"]
    print(f"{season}: relWIS {st.wis.sum()/st.base_wis.sum():.4f} on {len(st):,} cells; "
          f"local_pools {local}; {time.time()-t0:.0f} s", flush=True)

if __name__ == "__main__":
    main(*sys.argv[1:3])
