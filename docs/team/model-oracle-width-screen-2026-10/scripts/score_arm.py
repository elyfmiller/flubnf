"""Score one arm of the Oracle SIHRS width screen, cell by cell, under every
output rule of the grid, the way a live run makes and the hub scores its file.

    score_arm.py <arm_dir> <out.pkl> [--check]

<arm_dir> holds one replay root per season (run_arm.py). For each stored
week and jurisdiction:

  1. the stored member samples (the Oracle step, the narrowing knob of the
     run and the output floor already applied, as in a live run);
  2. the hub rows from them, app.core.submit.quantile_rows: numpy's linear
     quantiles at the 23 levels, whole admissions, monotone;
  3. the upper-tail rule, flubnf.tailcap.cap_rows, the console's own code,
     with the limit from the as-of vintage as app/ui/pipeline.py builds it
     (rows dated on or before the as-of, the last three finite values);
  4. app.core.scoring.score_quantiles: FluSight's cell rule, the validated
     baseline join, WIS and log-scale WIS, 50/80/95 coverage.

Rules: "none"; ("clip"|"shrink", n) for n in N_GRID. The narrowing exponent
of the run (k_run, from oracle.json) is the primary; other exponents are
re-exponentiated about each block's sample median, x' = m (x/m)^(k/k_run),
which composes exactly with the run's narrowing but sits after the floor's
noise, so those rows are APPROXIMATE (flag k_exact False).

--check adds the accuracy checks (printed, and the run stops on a failure):
  A. the unrounded quantiles of the stored samples equal the week's
     quantiles.json sidecar, and score_quantiles on them equals the
     console's retro.score_season on every cell (WIS, log WIS, baseline);
  B. an independent WIS (the quantile-score form, sum of 2[1(y<q)-tau](q-y)
     over the 23 levels / 23) equals flubnf.wis on every scored cell.

Env: FLUBNF_HUB = the scoring hub (settled truth, FluSight-baseline),
its target-data-archive a byte copy of the replay hub's, so a week's
vintage resolves to the file the replay read.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

WT = Path(os.environ["SCREEN_WT"])
sys.path.insert(0, str(WT))

import numpy as np
import pandas as pd

from app.core import horizons as hz
from app.core import retro, retro_store, scoring
from app.core.data import vintage_path
from app.core.ensemble import member_quantiles_from_samples
from app.core.submit import quantile_rows
from flubnf import tailcap as TC

N_GRID = (8, 10, 15, 20, 30)
K_GRID = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)
G_GRID = (1.5, 2.0, 3.0)
RULES = [("none", 0)] + [(m, n) for m in ("shrink", "clip") for n in N_GRID]


def recent_by_fips(asof: str) -> dict:
    """fips -> the values the pipeline's `obs` would hold (dated on or
    before the as-of, finite, oldest to newest)."""
    # the console's resolver (the hub archive, else the shipped snapshot);
    # the scoring hub carries the replay hub's archive byte for byte
    t = pd.read_csv(vintage_path(asof), dtype={"location": str})
    t = t[t["date"].astype(str).str[:10] <= asof].copy()
    t["location"] = t["location"].str.zfill(2)
    out = {}
    for f, g in t.sort_values("date").groupby("location"):
        v = [float(x) for x in g["value"].tail(15) if np.isfinite(x)]
        out[f] = v
    return out


def rows_to_q(rows: list) -> dict:
    """hub rows -> {fips: {"0".."3": {level: value}}}"""
    out: dict = {}
    for r in rows:
        if r["output_type"] != "quantile":
            continue
        out.setdefault(r["location"], {}).setdefault(str(int(r["horizon"])), {})[
            float(r["output_type_id"])] = float(r["value"])
    return out


def renarrow(samples: dict, factor: float) -> dict:
    """Each forecast block re-exponentiated about its finite median."""
    if factor == 1.0:
        return samples
    out = dict(samples)
    for h in hz.HORIZONS:
        x = np.asarray(samples.get(h, []), float)
        f = np.isfinite(x)
        if not f.any():
            continue
        m = float(np.median(x[f]))
        if not m > 0:
            continue
        y = x.copy()
        pos = f & (x > 0)
        y[pos] = m * (x[pos] / m) ** factor
        out[h] = y
    return out


def qs_wis(q: dict, y: float) -> float:
    """WIS as the mean quantile score over the 23 levels (check B)."""
    tot = 0.0
    for tau, v in q.items():
        tot += 2.0 * ((1.0 if y < v else 0.0) - tau) * (v - y)
    return tot / len(q)


def add_gate(df, q: dict, rec_lvl: dict) -> None:
    """The gate and the band, read off the rows that would ship: h-block
    97.5% over the recent level and over the median, and the median."""
    g = []
    for r in df.itertuples():
        qq = q[r.location][str(int(r.horizon))]
        rl = rec_lvl.get(r.fips, float("nan"))
        g.append((qq[0.975] / rl if rl and rl > 0 else float("nan"),
                  qq[0.975] / qq[0.5] if qq[0.5] > 0 else float("nan"),
                  qq[0.5]))
    df["tail_over_recent"] = [x[0] for x in g]
    df["tail_over_median"] = [x[1] for x in g]
    df["median"] = [x[2] for x in g]


def week_cells(root: Path, season: str, asof: str, n2f: dict, f2n: dict,
               truth: dict, check: bool) -> list:
    smp = retro_store.read_week_samples(root, asof)["pf"]
    prov = json.loads((root / "weeks" / asof / "oracle.json").read_text())
    k_run = float(prov["narrowing"]["k"])
    rec = recent_by_fips(asof)
    lim_n = {n: {f: TC.limit_for(n, rec.get(f, [])) for f in rec} for n in N_GRID}
    rec_lvl = {f: TC.recent_level(rec.get(f, [])) for f in rec}
    frames = []
    if check:
        side = retro_store.read_week_quantiles(root / "weeks" / asof)["pf"]
        mine = {loc: member_quantiles_from_samples(s) for loc, s in smp.items()}
        for loc in mine:
            for h in mine[loc]:
                a, b = mine[loc][h], side[loc][h]
                assert all(abs(a[L] - float(b[L] if L in b else b[str(L)])) <= 1e-9 * max(1, abs(a[L]))
                           for L in a), (asof, loc, h)
        unr = scoring.score_quantiles(mine, asof, n2f, truth)
        unr["asof"] = asof
        frames.append(("unrounded", unr))
        # check C: the step's own recorded quantiles of the submitted seed,
        # before the floor, at k_run and unnarrowed (k = 1), in whole
        # admissions; against the grid's k_run and k = 1 rows they bound the
        # floor's effect and the re-exponentiation's error
        from app.core.submit import _hub_values
        from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
        sub = str(prov["submitted_seed"])
        pq = prov["quantiles"]["primary"]
        sq = prov["quantiles"]["secondary"]
        for kind, src in (("json_krun", pq["per_seed"][sub]),
                          ("json_k1", (pq.get("unnarrowed") or pq)["per_seed"][sub]),
                          # the logged secondary (w 0.25) of the submitted
                          # seed, pre-floor: the registered member's run
                          # gives the weight step of the comparison table
                          ("json_secondary", sq["per_seed"][sub])):
            qd = {}
            for loc, blocks in src.items():
                for h, b in blocks.items():
                    v = b.get("unrounded")
                    if v is None:
                        continue
                    qd.setdefault(loc, {})[h] = dict(zip(map(float, QL), map(float, _hub_values(v))))
            dfc = scoring.score_quantiles(qd, asof, n2f, truth)
            dfc["asof"] = asof
            add_gate(dfc, qd, rec_lvl)
            frames.append((kind, dfc))
    for k in K_GRID:
        fac = k / k_run
        rows = []
        for loc, s in smp.items():
            f = n2f.get(loc)
            if f is None:
                continue
            rows += quantile_rows(renarrow(s, fac), f, asof)
        for mode, n in RULES:
            if mode == "none":
                rr = rows
            else:
                rr, _ = TC.cap_rows(rows, lim_n[n], mode=mode)
            q = {f2n[f]: v for f, v in rows_to_q(rr).items()}
            df = scoring.score_quantiles(q, asof, n2f, truth)
            if df.empty:
                continue
            df["asof"] = asof
            df["k"] = k
            df["k_exact"] = abs(fac - 1.0) < 1e-12
            df["mode"] = mode
            df["n"] = n
            add_gate(df, q, rec_lvl)
            if check and k == k_run and mode == "none":
                for r in df.itertuples():
                    qq = q[r.location][str(int(r.horizon))]
                    y = truth[(r.fips, pd.Timestamp(asof) + pd.Timedelta(days=7 * (int(r.horizon) + 1)))]
                    assert abs(qs_wis(qq, y) - r.wis) <= 1e-9 * max(1.0, r.wis), (asof, r.location, r.horizon)
            frames.append(("grid", df))
    # G (PREREG section 2): the per-week growth cap on the stored paths at
    # the run's k, x'_0 = min(x_0, g y_T), x'_h = min(x_h, g x'_{h-1}), y_T
    # the as-of week's reported count; a location with y_T <= 0 untouched
    for g in G_GRID:
        rows = []
        for loc, s in smp.items():
            f = n2f.get(loc)
            if f is None:
                continue
            yT = (rec.get(f) or [float("nan")])[-1]
            if math.isfinite(yT) and yT > 0:
                prev = np.full(len(s[hz.HORIZONS[0]]), g * yT)
                s2 = dict(s)
                for h in hz.HORIZONS:
                    x = np.asarray(s[h], float)
                    y = np.where(np.isfinite(x), np.minimum(x, prev), x)
                    s2[h] = y
                    prev = g * np.where(np.isfinite(y), y, prev / g)
                s = s2
            rows += quantile_rows(s, f, asof)
        q = {f2n[f]: v for f, v in rows_to_q(rows).items()}
        df = scoring.score_quantiles(q, asof, n2f, truth)
        df["asof"] = asof
        df["k"] = k_run
        df["k_exact"] = True
        df["mode"] = "growth"
        df["n"] = g
        add_gate(df, q, rec_lvl)
        frames.append(("growth", df))
    # the filter alone: the step's null quantiles (the filter's own, before
    # the step and unnarrowed), whole admissions
    from app.core.submit import _hub_values as _hv
    from flubnf.quantiles import FLUSIGHT_QUANTILES as _QL
    qn = {}
    for loc, blocks in prov["quantiles"]["null"].items():
        for h, b in blocks.items():
            v = b.get("unrounded")
            if v is not None:
                qn.setdefault(loc, {})[h] = dict(zip(map(float, _QL), map(float, _hv(v))))
    dfn = scoring.score_quantiles(qn, asof, n2f, truth)
    dfn["asof"] = asof
    add_gate(dfn, qn, rec_lvl)
    frames.append(("filter", dfn))
    out = []
    for kind, df in frames:
        df = df.copy()
        df["season"] = season
        df["kind"] = kind
        out.append(df)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("arm_dir")
    ap.add_argument("out")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    truth, n2f = scoring.load_truth()
    assert scoring.TRUTH_SOURCE == "settled", scoring.TRUTH_SOURCE
    f2n = {v: k for k, v in n2f.items()}
    parts = []
    arm = Path(a.arm_dir)
    for root in sorted(p for p in arm.iterdir() if p.is_dir()):
        season = root.name
        weeks = sorted(p.name for p in (root / "weeks").iterdir()
                       if retro_store.week_samples_path(root, p.name) is not None)
        for asof in weeks:
            parts += week_cells(root, season, asof, n2f, f2n, truth, a.check)
        if a.check:
            # check A, second half: the console's own season scorer
            cs = retro.score_season(root, season)
            cs = cs[cs["model"] == "pf"]
            mine = pd.concat([d for d in parts if (d["kind"] == "unrounded").all()
                              and (d["season"] == season).all()])
            key = ["location", "asof", "horizon"]
            j = cs.merge(mine, on=key, suffixes=("_c", "_m"))
            assert len(j) == len(cs) == len(mine), (len(j), len(cs), len(mine))
            for col in ("wis", "log_wis", "base_wis", "base_log_wis"):
                d = float(np.max(np.abs(j[f"{col}_c"] - j[f"{col}_m"])))
                print(f"check A {season}: {col} max |console - mine| = {d:.3g} over {len(j)} cells")
                assert d <= 1e-9, col
    df = pd.concat(parts, ignore_index=True)
    df.to_pickle(a.out)
    print(f"{len(df)} rows -> {a.out}")


if __name__ == "__main__":
    main()
