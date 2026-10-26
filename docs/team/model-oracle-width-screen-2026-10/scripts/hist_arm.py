"""The historical-ceiling arm H of AMENDMENT3_HIST.md, post hoc on a replayed
arm's stored weeks (C0's), no replay. Runs with SCREEN_WT = wt-hist (main
a99d53d, the knob output.tail_hist).

    hist_arm.py <arm_dir> <C0.cells.pkl> <out.pkl> [--weeks 2024-12-07]

For each stored week and jurisdiction, at the run's narrowing k (0.7), on the
hub rows of the stored samples (app.core.submit.quantile_rows), the console's
own code in the console's order (app/ui/pipeline.py, the output stage):
  hist_series  every jurisdiction's whole history in the week's vintage, the
               national row left out, built as the pipeline builds it;
  ratios       flubnf.tailcap.history_ratios(hist_series, asof, level);
  ceiling      flubnf.tailcap.clip_rows_by_horizon with history_limits(
               ratios, recent_level(obs)), before the n-cap;
  n-cap        flubnf.tailcap.cap_rows(rows, limit_for(n, obs), mode).
Arms: hist max; hist 0.975; hist max + shrink 15x; hist max + clip 15x;
hist max + shrink 10x. Secondary (not tests): the same maximum read from the
settled truth file (histF max, histF max + shrink 15x). Comparators: none,
clip 15x, shrink 15x, clip 10x.

Checks of the amendment, on every week (the run stops on a failure):
  A3. the comparators equal the C0 cells' k-run rows (WIS, log WIS);
  B3. an independent implementation of the ratios (pandas, by position and
      date join) equals history_ratios at both levels and both sources;
  C3. every ceiling block: levels at or below the median unchanged, levels
      above at most max(limit, median) + 0.5 and monotone, a block with no
      level above its limit (or no limit) identical; the touched blocks
      counted here equal clip_rows_by_horizon's own count;
  D3. the ceiling with no limit (every limit NaN) gives the none rows.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import score_arm as SA
from app.core import horizons as hz
from app.core import retro_store, scoring
from app.core.data import vintage_path
from app.core.submit import quantile_rows
from flubnf import tailcap as TC

assert hasattr(TC, "history_ratios"), "SCREEN_WT must carry output.tail_hist (wt-hist)"
LEVELS = (1.0, 0.975)
COMPARATORS = [("none", 0), ("clip", 15), ("shrink", 15), ("clip", 10)]
HS = (0, 1, 2, 3)


def series_from_frame(tdf: pd.DataFrame, asof: str) -> dict:
    """The pipeline's hist_series (app/ui/pipeline.py, the obs block)."""
    tdf = tdf[tdf["date"].astype(str).str[:10] <= str(asof)].copy()
    tdf["location"] = tdf["location"].str.zfill(2)
    return {f: [(str(r.date)[:10], float(r.value))
                for r in g.sort_values("date").itertuples()
                if np.isfinite(r.value)]
            for f, g in tdf.groupby("location") if f != "US"}


def ratios_independent(series: dict, asof: str, level: float) -> tuple:
    """The same ratios computed another way: ({h: ratio}, {h: pool size})."""
    a = pd.Timestamp(asof)
    ew = int(a.isocalendar()[1])
    se = a.year if a.month >= 8 else a.year - 1
    pools = {h: [] for h in HS}
    for _f, pairs in series.items():
        s = pd.Series([v for _, v in pairs], index=pd.to_datetime([d for d, _ in pairs]))
        s = s[~s.index.duplicated(keep="last")].sort_index()
        base = s.rolling(TC.RECENT_WEEKS, min_periods=1).mean().to_numpy()
        idx = s.index
        wk = np.array([int(d.isocalendar()[1]) for d in idx])
        dw = np.abs(wk - ew)
        near = np.minimum(dw, 52 - dw) <= TC.HIST_WINDOW
        seas = np.array([d.year if d.month >= 8 else d.year - 1 for d in idx])
        m = (seas < se) & near & (base >= TC.HIST_FLOOR)
        for h in HS:
            y = s.reindex(idx + pd.Timedelta(weeks=h + 1)).to_numpy()
            ok = m & np.isfinite(y)
            pools[h].extend((y[ok] / base[ok]).tolist())
    out = {}
    for h in HS:
        p = pools[h]
        out[h] = (float("nan") if not p else float(max(p)) if level >= 1.0
                  else float(np.quantile(np.asarray(p), level)))
    return out, {h: len(pools[h]) for h in HS}


def blocks_of(rows: list) -> dict:
    out: dict = {}
    for r in rows:
        if r.get("target") == TC.TARGET and r.get("output_type") == "quantile":
            out.setdefault((str(r["location"]), int(r["horizon"])), {})[
                float(r["output_type_id"])] = float(r["value"])
    return out


def check_ceiling(base: dict, cut: dict, limits: dict, reported: int, tag) -> dict:
    """C3 on one week's blocks; returns {(fips, h): (touched, collapsed)}."""
    flags = {}
    for key, b in base.items():
        c = cut[key]
        f, h = key
        lim = (limits.get(f) or {}).get(h, float("nan"))
        med = b[0.5]
        for lv in b:
            if lv <= 0.5:
                assert c[lv] == b[lv], (tag, key, lv)
        lv_sorted = sorted(c)
        assert all(c[lv_sorted[i]] <= c[lv_sorted[i + 1]] for i in range(len(lv_sorted) - 1)), (tag, key)
        if not math.isfinite(lim) or not any(b[lv] > max(lim, med) for lv in b if lv > 0.5):
            assert c == b, (tag, key)
        else:
            for lv in b:
                if lv > 0.5:
                    assert c[lv] <= max(lim, med) + 0.5, (tag, key, lv, c[lv], lim)
        touched = c != b
        collapsed = touched and math.isfinite(lim) and lim <= med
        flags[key] = (touched, collapsed)
    n = sum(t for t, _ in flags.values())
    assert n == reported, (tag, n, reported)
    return flags


def score_rows(rows, asof, n2f, f2n, truth, rec_lvl, rule):
    q = {f2n[f]: v for f, v in SA.rows_to_q(rows).items()}
    df = scoring.score_quantiles(q, asof, n2f, truth)
    if df.empty:
        return df
    df["asof"] = asof
    df["rule"] = rule
    SA.add_gate(df, q, rec_lvl)
    return df


def week(root: Path, season: str, asof: str, n2f, f2n, truth, final_df, c0):
    smp = retro_store.read_week_samples(root, asof)["pf"]
    prov = json.loads((root / "weeks" / asof / "oracle.json").read_text())
    k = float(prov["narrowing"]["k"])
    rec = SA.recent_by_fips(asof)
    rec_lvl = {f: TC.recent_level(rec.get(f, [])) for f in rec}
    lim = {n: {f: TC.limit_for(n, rec.get(f, [])) for f in rec} for n in (10, 15)}
    src = {"v": series_from_frame(pd.read_csv(vintage_path(asof), dtype={"location": str}), asof),
           "f": series_from_frame(final_df, asof)}
    ratios, rrows = {}, []
    for s, ser in src.items():
        for lvl in LEVELS:
            r = TC.history_ratios(ser, asof, level=lvl)
            ri, npool = ratios_independent(ser, asof, lvl)
            for h in HS:   # B3
                a, b = r[h], ri[h]
                assert (math.isnan(a) and math.isnan(b)) or abs(a - b) <= 1e-9 * max(1.0, abs(b)), \
                    (asof, s, lvl, h, a, b)
                rrows.append({"season": season, "asof": asof, "source": s, "level": lvl,
                              "horizon": h, "ratio": a, "pool": npool[h]})
            ratios[(s, lvl)] = r
    hl = {key: {f: TC.history_limits(r, rec_lvl.get(f, float("nan"))) for f in rec}
          for key, r in ratios.items()}
    none = []
    for loc, smpl in smp.items():
        f = n2f.get(loc)
        if f is not None:
            none += quantile_rows(smpl, f, asof)
    rows = {"none": none}
    for mode, n in COMPARATORS[1:]:
        rows[f"{mode} {n}x"], _ = TC.cap_rows(none, lim[n], mode=mode)
    cells_reported = {}
    for tag, key in (("hist max", ("v", 1.0)), ("hist 0.975", ("v", 0.975)),
                     ("histF max", ("f", 1.0))):
        rows[tag], cells_reported[tag] = TC.clip_rows_by_horizon(none, hl[key])
    rows["hist max+shrink 15x"], _ = TC.cap_rows(rows["hist max"], lim[15], mode="shrink")
    rows["hist max+clip 15x"], _ = TC.cap_rows(rows["hist max"], lim[15], mode="clip")
    rows["hist max+shrink 10x"], _ = TC.cap_rows(rows["hist max"], lim[10], mode="shrink")
    rows["histF max+shrink 15x"], _ = TC.cap_rows(rows["histF max"], lim[15], mode="shrink")
    # D3: no limit, nothing changes
    nolim = {f: {h: float("nan") for h in HS} for f in rec}
    d3, d3n = TC.clip_rows_by_horizon(none, nolim)
    assert d3 == none and d3n == 0, asof
    # C3 and the block table
    B0 = blocks_of(none)
    flags = {}
    for tag, key in (("hist max", ("v", 1.0)), ("hist 0.975", ("v", 0.975)),
                     ("histF max", ("f", 1.0))):
        flags[tag] = check_ceiling(B0, blocks_of(rows[tag]), hl[key], cells_reported[tag], (asof, tag))
    Bp, Bs = blocks_of(rows["hist max+shrink 15x"]), blocks_of(rows["shrink 15x"])
    Bm, B9 = blocks_of(rows["hist max"]), blocks_of(rows["hist 0.975"])
    blk = []
    for key, b in B0.items():
        f, h = key
        blk.append({"season": season, "asof": asof, "fips": f, "horizon": h,
                    "recent": rec_lvl.get(f, float("nan")), "median": b[0.5], "q975": b[0.975],
                    "lim_max": hl[("v", 1.0)].get(f, {}).get(h, float("nan")),
                    "lim_975": hl[("v", 0.975)].get(f, {}).get(h, float("nan")),
                    "q975_max": Bm[key][0.975], "q975_975": B9[key][0.975],
                    "touched_max": flags["hist max"][key][0],
                    "collapsed_max": flags["hist max"][key][1],
                    "touched_975": flags["hist 0.975"][key][0],
                    "collapsed_975": flags["hist 0.975"][key][1],
                    "touched_maxF": flags["histF max"][key][0],
                    "pair_differs_s15": Bp[key] != Bs[key],
                    "q975_pair": Bp[key][0.975], "q975_s15": Bs[key][0.975]})
    frames = [score_rows(rr, asof, n2f, f2n, truth, rec_lvl, rule) for rule, rr in rows.items()]
    df = pd.concat(frames, ignore_index=True)
    df["season"] = season
    df["k"] = k
    # A3: the comparators against the C0 cells' rows at the run's k
    for mode, n in COMPARATORS:
        rule = "none" if mode == "none" else f"{mode} {n}x"
        mine = df[df.rule == rule]
        ref = c0[(c0["asof"] == asof) & (c0.k == k) & (c0["mode"] == mode) & (c0.n == n)]
        j = mine.merge(ref, on=["location", "horizon"], suffixes=("_m", "_r"))
        assert len(j) == len(mine) == len(ref), (asof, rule, len(j), len(mine), len(ref))
        for col in ("wis", "log_wis"):
            d = float(np.max(np.abs(j[f"{col}_m"] - j[f"{col}_r"])))
            assert d <= 1e-9, (asof, rule, col, d)
    return df, pd.DataFrame(blk), pd.DataFrame(rrows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("arm_dir")
    ap.add_argument("c0_cells")
    ap.add_argument("out")
    ap.add_argument("--weeks", default="")
    a = ap.parse_args()
    truth, n2f = scoring.load_truth()
    assert scoring.TRUTH_SOURCE == "settled", scoring.TRUTH_SOURCE
    final_df = pd.read_csv(scoring.HUB / "target-data/target-hospital-admissions.csv",
                           dtype={"location": str})
    f2n = {v: k for k, v in n2f.items()}
    c0 = pd.read_pickle(a.c0_cells)
    c0 = c0[c0.kind == "grid"]
    only = set(w for w in a.weeks.split(",") if w)
    parts, blks, rats = [], [], []
    for root in sorted(p for p in Path(a.arm_dir).iterdir() if p.is_dir()):
        season = root.name
        weeks = sorted(p.name for p in (root / "weeks").iterdir()
                       if retro_store.week_samples_path(root, p.name) is not None
                       and (not only or p.name in only))
        cs = c0[c0.season == season]
        for asof in weeks:
            df, bk, rt = week(root, season, asof, n2f, f2n, truth, final_df, cs)
            parts.append(df)
            blks.append(bk)
            rats.append(rt)
            m = rt[(rt.source == "v") & (rt.level == 1.0)].set_index("horizon")
            print(f"{season} {asof}: A3 ok, B3 ok, C3 ok, D3 ok; max ratios "
                  + " ".join(f"{m.ratio[h]:.1f}" for h in HS)
                  + f" (pool {int(m.pool[0])}); ceiling touched {int(bk.touched_max.sum())}"
                  f"/{len(bk)} blocks (0.975: {int(bk.touched_975.sum())})", flush=True)
    out = {"cells": pd.concat(parts, ignore_index=True),
           "blocks": pd.concat(blks, ignore_index=True),
           "ratios": pd.concat(rats, ignore_index=True)}
    pd.to_pickle(out, a.out)
    print(f"{len(out['cells'])} cell rows, {len(out['blocks'])} block rows -> {a.out}")


if __name__ == "__main__":
    main()
