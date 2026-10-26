"""The trajectory-exclusion arm X of AMENDMENT2_EXCL.md (sha256 525ab77f),
post hoc on a replayed arm's stored weeks (C0's), no replay.

    exclude_arm.py <arm_dir> <C0.cells.pkl> <out.pkl> [--weeks 2024-12-07]
                   [--loop-check]

For each stored week and jurisdiction, at the run's narrowing k (0.7):
  XP  the stored samples un-narrowed about each block's median
      (score_arm.renarrow, factor 1/k); every path whose value at any of
      h0..h3 exceeds L_n = tailcap.limit_for(n, recent) dropped whole; the
      rest narrowed again at k about their own median (flubnf.oracle.narrow,
      the console's narrowing); app.core.submit.quantile_rows.
  XS  the same test on the stored samples as they are.
n in N_X, and X40 + shrink 15x. The comparators none, clip 15x, shrink 15x
and shrink 10x come from the stored samples as score_arm.py builds them. A
location-week left with fewer than MIN_KEEP paths keeps them all (counted).

Checks of the amendment, on every week (the run stops on a failure):
  A'. the comparators equal the C0 cells' k-run rows (WIS, log WIS);
  B'. no limit: XS gives the none rows exactly; XP's round trip is counted
      (hub values that differ, and their cells' WIS change);
  C'. no kept path exceeds L_n (XP on the un-narrowed values, XS on the
      stored ones); with --loop-check, the dropped counts equal a plain
      Python loop's.
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
from app.core.submit import quantile_rows
from flubnf import oracle as OR
from flubnf import tailcap as TC

N_X = (15, 20, 30, 40)
MIN_KEEP = 300
COMPARATORS = [("none", 0), ("clip", 15), ("shrink", 15), ("shrink", 10)]
H = hz.HORIZONS


def drop_mask(V: np.ndarray, lim: float) -> np.ndarray:
    """(4, N) values -> True for the paths to keep (none above lim)."""
    if lim is None or not math.isfinite(lim):
        return np.ones(V.shape[1], bool)
    return ~(V > lim).any(axis=0)


def loop_count(V: np.ndarray, lim: float) -> int:
    if lim is None or not math.isfinite(lim):
        return 0
    c = 0
    for i in range(V.shape[1]):
        for hi in range(V.shape[0]):
            if V[hi, i] > lim:
                c += 1
                break
    return c


def score_rows(rows, asof, n2f, f2n, truth, rec_lvl, rule, variant):
    q = {f2n[f]: v for f, v in SA.rows_to_q(rows).items()}
    df = scoring.score_quantiles(q, asof, n2f, truth)
    if df.empty:
        return df
    df["asof"] = asof
    df["rule"] = rule
    df["variant"] = variant
    SA.add_gate(df, q, rec_lvl)
    return df


def week(root: Path, season: str, asof: str, n2f, f2n, truth, c0, loop_check):
    smp = retro_store.read_week_samples(root, asof)["pf"]
    prov = json.loads((root / "weeks" / asof / "oracle.json").read_text())
    k = float(prov["narrowing"]["k"])
    rec = SA.recent_by_fips(asof)
    rec_lvl = {f: TC.recent_level(rec.get(f, [])) for f in rec}
    lim = {n: {f: TC.limit_for(n, rec.get(f, [])) for f in rec} for n in set(N_X) | {10, 15}}
    rows = {("none", "stored"): [], ("noLimit", "XP"): [], ("noLimit", "XS"): []}
    for n in N_X:
        rows[(f"X{n}", "XP")] = []
        rows[(f"X{n}", "XS")] = []
    drops = []
    for loc, s in smp.items():
        f = n2f.get(loc)
        if f is None:
            continue
        S = np.vstack([np.asarray(s[h], float) for h in H])
        un = SA.renarrow(s, 1.0 / k)
        U = np.vstack([np.asarray(un[h], float) for h in H])
        N = S.shape[1]
        rows[("none", "stored")] += quantile_rows(s, f, asof)
        # B': nothing dropped
        rows[("noLimit", "XS")] += quantile_rows({h: S[hi] for hi, h in enumerate(H)}, f, asof)
        rows[("noLimit", "XP")] += quantile_rows(
            {h: OR.narrow(U[hi], k) for hi, h in enumerate(H)}, f, asof)
        for n in N_X:
            L = lim[n].get(f, float("nan"))
            for variant, V in (("XP", U), ("XS", S)):
                keep = drop_mask(V, L)
                nd = int(N - keep.sum())
                if loop_check:
                    assert loop_count(V, L) == nd, (asof, loc, n, variant)
                degenerate = keep.sum() < MIN_KEEP
                if degenerate:
                    keep = np.ones(N, bool)
                else:
                    # C'
                    assert not (V[:, keep] > L).any(), (asof, loc, n, variant)
                if variant == "XP":
                    blk = {h: OR.narrow(U[hi, keep], k) for hi, h in enumerate(H)}
                else:
                    blk = {h: S[hi, keep] for hi, h in enumerate(H)}
                rows[(f"X{n}", variant)] += quantile_rows(blk, f, asof)
                drops.append({"season": season, "asof": asof, "location": loc, "fips": f,
                              "n": n, "variant": variant, "n_paths": N, "dropped": nd,
                              "degenerate": bool(degenerate),
                              "limit": L, "recent": rec_lvl.get(f, float("nan"))})
    frames = []
    for (rule, variant), rr in rows.items():
        frames.append(score_rows(rr, asof, n2f, f2n, truth, rec_lvl, rule, variant))
    for mode, n in COMPARATORS[1:]:
        rr, _ = TC.cap_rows(rows[("none", "stored")], lim[n], mode=mode)
        frames.append(score_rows(rr, asof, n2f, f2n, truth, rec_lvl, f"{mode} {n}x", "stored"))
    for variant in ("XP", "XS"):
        rr, _ = TC.cap_rows(rows[("X40", variant)], lim[15], mode="shrink")
        frames.append(score_rows(rr, asof, n2f, f2n, truth, rec_lvl, "X40+shrink 15x", variant))
    df = pd.concat(frames, ignore_index=True)
    df["season"] = season
    df["k"] = k
    # A': the comparators against the C0 cells' rows at the run's k
    for mode, n in COMPARATORS:
        rule = "none" if mode == "none" else f"{mode} {n}x"
        mine = df[(df.rule == rule) & (df.variant == "stored")]
        ref = c0[(c0["asof"] == asof) & (c0.k == k) & (c0["mode"] == mode) & (c0.n == n)]
        j = mine.merge(ref, on=["location", "horizon"], suffixes=("_m", "_r"))
        assert len(j) == len(mine) == len(ref), (asof, rule, len(j), len(mine), len(ref))
        for col in ("wis", "log_wis"):
            d = float(np.max(np.abs(j[f"{col}_m"] - j[f"{col}_r"])))
            assert d <= 1e-9, (asof, rule, col, d)
    # B': XS with no limit is the none rows exactly; XP's round trip counted
    base = df[(df.rule == "none") & (df.variant == "stored")].set_index(["location", "horizon"])
    xs = df[(df.rule == "noLimit") & (df.variant == "XS")].set_index(["location", "horizon"])
    assert float(np.max(np.abs(xs.wis - base.wis))) == 0.0, asof
    xp = df[(df.rule == "noLimit") & (df.variant == "XP")].set_index(["location", "horizon"])
    dw = (xp.wis - base.wis).abs()
    b_rt = {"asof": asof, "cells": len(dw), "cells_differ": int((dw > 0).sum()),
            "wis_abs_change": float(dw.sum()), "wis_total": float(base.wis.sum())}
    return df, pd.DataFrame(drops), b_rt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("arm_dir")
    ap.add_argument("c0_cells")
    ap.add_argument("out")
    ap.add_argument("--weeks", default="")
    ap.add_argument("--loop-check", action="store_true")
    a = ap.parse_args()
    truth, n2f = scoring.load_truth()
    assert scoring.TRUTH_SOURCE == "settled", scoring.TRUTH_SOURCE
    f2n = {v: k for k, v in n2f.items()}
    c0 = pd.read_pickle(a.c0_cells)
    c0 = c0[c0.kind == "grid"]
    only = set(w for w in a.weeks.split(",") if w)
    parts, drops, rts = [], [], []
    arm = Path(a.arm_dir)
    for root in sorted(p for p in arm.iterdir() if p.is_dir()):
        season = root.name
        weeks = sorted(p.name for p in (root / "weeks").iterdir()
                       if retro_store.week_samples_path(root, p.name) is not None
                       and (not only or p.name in only))
        cs = c0[c0.season == season]
        for asof in weeks:
            df, dr, rt = week(root, season, asof, n2f, f2n, truth, cs, a.loop_check)
            parts.append(df)
            drops.append(dr)
            rts.append(rt)
            print(f"{season} {asof}: A' ok, B' XS exact, XP round trip "
                  f"{rt['cells_differ']}/{rt['cells']} cells differ "
                  f"(|dWIS| {rt['wis_abs_change']:.2f} of {rt['wis_total']:.0f}), C' ok"
                  + (", loop counts equal" if a.loop_check else ""), flush=True)
    out = {"cells": pd.concat(parts, ignore_index=True),
           "drops": pd.concat(drops, ignore_index=True),
           "round_trip": pd.DataFrame(rts)}
    pd.to_pickle(out, a.out)
    print(f"{len(out['cells'])} cell rows, {len(out['drops'])} drop rows -> {a.out}")


if __name__ == "__main__":
    main()
