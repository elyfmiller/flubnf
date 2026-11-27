"""The Oracle weight screen: build the arms from the kept filter samples,
score them, apply the rule (PREREG.txt beside this file).

    score.py build  <out>   every arm's capped hub quantiles, per week (no truth)
    score.py score  <out>   the scored state cells of every arm (needs the frozen prereg)
    score.py report <out>   the tables, the leave-one-season-out k, the bootstrap, the rule

<out> is the replay folder (replay.py): replay/<season>/, filter/<season>/.
Results go to <out>/arms/ (quantiles), <out>/cells/ (scored cells) and the
report to stdout. FLUBNF_HUB is the hub clone at 09c96ec8 (vintages,
settled truth, FluSight-baseline).

An arm (w, k) for one week: app.core.oracle.apply_week on the kept filter
samples with the weight and narrowing in the run's knob record (arms.py),
the replay's own output floor, the hub rows by app.core.submit.quantile_rows
(horizons 0 to 3, whole admissions), then the live cap: flubnf.tailcap
.cap_rows, shrink, at 10x the larger of the last reported week and the
three-week mean (limit_for, level "larger"), on the observations
app/ui/pipeline.py builds (the vintage's rows dated on or before the as-of,
the last 15 by date, finite). F, the filter alone: the kept samples through
the same floor, rows and cap, unnarrowed.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import arms as AR  # noqa: E402

SEASONS = ("2023-24", "2024-25", "2025-26")
WS = (1.0, 0.75, 0.5, 0.375, 0.25)
KS = (0.6, 0.7, 0.8, 1.0)
ARMS = [f"w{w:g}-k{k:g}" for w in WS for k in KS] + ["F"]
COMPARATOR = "w0.25-k0.7"
CAP_N, CAP_LEVEL = 10.0, "larger"
SEED = 20261127
LEVELS = None  # the 23 FluSight levels, filled on first use


def ref_date(asof: str) -> str:
    return (date.fromisoformat(asof) + timedelta(days=7)).isoformat()


def in_b(asof: str) -> bool:
    """Window B: reference dates from December 1 of the season's first year."""
    r = date.fromisoformat(ref_date(asof))
    first = r.year if r.month >= 8 else r.year - 1
    return r >= date(first, 12, 1)


def obs_by_fips(asof: str) -> dict:
    from app.core.data import vintage_path
    t = pd.read_csv(vintage_path(asof), dtype={"location": str})
    t = t[t["date"].astype(str).str[:10] <= asof].copy()
    t["location"] = t["location"].str.zfill(2)
    return {f: [float(x) for x in g.sort_values("date")["value"].tail(15) if np.isfinite(x)]
            for f, g in t.groupby("location")}


def capped_q(samples: dict, asof: str, n2f: dict, lims: dict) -> dict:
    """{location name: {"0".."3": {level: value}}} after the live cap."""
    from app.core.submit import quantile_rows
    from flubnf import tailcap as TC
    rows = []
    for loc, s in samples.items():
        f = n2f.get(loc)
        if f and f != "US":
            rows += quantile_rows(s, f, asof)
    rows, _ = TC.cap_rows(rows, lims, mode="shrink")
    f2n = {f: n for n, f in n2f.items()}
    out: dict = {}
    for r in rows:
        if r["output_type"] == "quantile" and r["target"] == TC.TARGET:
            out.setdefault(f2n[r["location"]], {}).setdefault(str(int(r["horizon"])), {})[
                float(r["output_type_id"])] = float(r["value"])
    return out


def week_arms(out: Path, season: str, asof: str, n2f: dict) -> dict:
    from app.core.floor import floor_samples
    from flubnf import tailcap as TC
    inp = AR.kept(out, season, asof)
    obs = obs_by_fips(asof)
    lims = {f: TC.limit_for(CAP_N, v, level=CAP_LEVEL) for f, v in obs.items()}
    res = {}
    with tempfile.TemporaryDirectory() as tmp:
        for w in WS:
            for k in KS:
                m = AR.member_for(inp, asof, w, k, Path(tmp) / f"{w}-{k}")
                res[f"w{w:g}-k{k:g}"] = capped_q(m, asof, n2f, lims)
    F = {loc: floor_samples(s, loc, asof, recent=inp["recent"].get(loc, []))
         for loc, s in inp["raw"].items()}
    res["F"] = capped_q(F, asof, n2f, lims)
    return res


def weeks_of(out: Path, season: str) -> list:
    d = out / "filter" / season
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.is_dir() else []


def build(out: Path) -> None:
    """Every arm's quantiles, one gzipped json per season and week. Also
    re-checks the live arm against the stored member (arms.check)."""
    from app.core.oracle import name_to_fips
    n2f = name_to_fips()
    bad = AR.check(out, list(SEASONS), set())
    if bad:
        sys.exit(f"{bad} weeks: the live arm does not rebuild the stored member; nothing built")
    for season in SEASONS:
        for asof in weeks_of(out, season):
            fp = out / "arms" / season / f"{asof}.json.gz"
            if fp.is_file():
                continue
            fp.parent.mkdir(parents=True, exist_ok=True)
            res = week_arms(out, season, asof, n2f)
            tmp = fp.with_name(fp.name + ".tmp")
            with gzip.open(tmp, "wt", encoding="utf-8") as fh:
                json.dump(res, fh)
            tmp.replace(fp)
            print(f"{season} {asof}: {len(res)} arms", flush=True)


def frozen() -> None:
    """Scoring needs the frozen pre-registration: PREREG.txt matching its
    sha256 file."""
    p, h = HERE / "PREREG.txt", HERE / "PREREG.txt.sha256"
    if not (p.is_file() and h.is_file()):
        sys.exit("no frozen pre-registration (PREREG.txt and its sha256): nothing scored")
    want = h.read_text().split()[0]
    got = hashlib.sha256(p.read_bytes()).hexdigest()
    if got != want:
        sys.exit(f"PREREG.txt hashes to {got}, not {want}: nothing scored")


def score(out: Path) -> None:
    frozen()
    from app.core import scoring
    truth, n2f = scoring.load_truth()
    assert scoring.TRUTH_SOURCE == "settled", scoring.TRUTH_SOURCE
    parts = []
    for season in SEASONS:
        for fp in sorted((out / "arms" / season).glob("*.json.gz")):
            asof = fp.name[:10]
            res = json.load(gzip.open(fp, "rt", encoding="utf-8"))
            for arm, q in res.items():
                df = scoring.score_quantiles(q, asof, n2f, truth)
                if df.empty:
                    continue
                df = df[df.fips != "US"].copy()
                df["arm"], df["season"], df["asof"] = arm, season, asof
                parts.append(df)
    C = pd.concat(parts, ignore_index=True)
    (out / "cells").mkdir(exist_ok=True)
    C.to_csv(out / "cells" / "cells.csv.gz", index=False)
    n = C.groupby("arm").size()
    print(f"scored cells per arm: {sorted(set(n))}; weeks {C.groupby(['season', 'asof']).ngroups}")


# ---- the report and the rule ---------------------------------------------------
rel = lambda d: d.wis.sum() / d.base_wis.sum()
lrel = lambda d: d.log_wis.sum() / d.base_log_wis.sum()


def loso(C: pd.DataFrame, w: float, window) -> tuple:
    """The w's leave-one-season-out arm in a window: for each season, the k
    with the lowest pooled natural relWIS over the other two seasons' cells
    in the same window (ties: the k nearer 0.7, then the larger); returns
    (cells, {season: k})."""
    pick, parts = {}, []
    for s in SEASONS:
        best = None
        for k in KS:
            d = C[(C.arm == f"w{w:g}-k{k:g}") & (C.season != s) & window(C)]
            v = rel(d)
            key = (round(v, 12), abs(k - 0.7), -k)
            if best is None or key < best[0]:
                best = (key, k)
        pick[s] = best[1]
        parts.append(C[(C.arm == f"w{w:g}-k{best[1]:g}") & (C.season == s) & window(C)])
    return pd.concat(parts), pick


def boot(A: pd.DataFrame, B: pd.DataFrame, R: int = 2000) -> tuple:
    """A less B in pooled natural relWIS, on their common cells; the
    week-cluster bootstrap stratified by season (percentile 95%)."""
    key = ["season", "asof", "fips", "horizon"]
    M = A[key + ["wis", "base_wis"]].merge(B[key + ["wis"]], on=key, suffixes=("_a", "_b"))
    W = M.groupby(["season", "asof"]).agg(a=("wis_a", "sum"), b=("wis_b", "sum"),
                                         base=("base_wis", "sum")).reset_index()
    est = (W.a.sum() - W.b.sum()) / W.base.sum()
    rng = np.random.default_rng(SEED)
    G = [W[W.season == s][["a", "b", "base"]].to_numpy() for s in SEASONS if (W.season == s).any()]
    bs = []
    for _ in range(R):
        P = np.vstack([x[rng.integers(0, len(x), len(x))] for x in G])
        bs.append((P[:, 0].sum() - P[:, 1].sum()) / P[:, 2].sum())
    return est, float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def summary(d: pd.DataFrame) -> dict:
    return {"relWIS": rel(d), "log": lrel(d), "cov50": d.cov50.mean(), "cov95": d.cov95.mean(),
            "cells": len(d), **{s: rel(d[d.season == s]) for s in SEASONS}}


def report(out: Path) -> None:
    frozen()
    C = pd.read_csv(out / "cells" / "cells.csv.gz", dtype={"fips": str})
    C["B"] = C["asof"].map(in_b)
    win = {"A": lambda X: X.index == X.index, "B": lambda X: X.B}
    n = C.groupby("arm").size()
    print(f"scored state cells per arm: {sorted(set(n))}; window B cells (comparator): "
          f"{int(C[(C.arm == COMPARATOR) & C.B].shape[0])}")
    for name in ("A", "B"):
        print(f"\nWINDOW {name}, every arm (relWIS natural / log, coverage 50 / 95, by season):")
        T = pd.DataFrame({a: summary(C[(C.arm == a) & win[name](C)]) for a in ARMS}).T
        print(T.round(4).to_string())
    res = {}
    for name in ("B", "A"):
        Cw = C[win[name](C)]
        comp = Cw[Cw.arm == COMPARATOR]
        print(f"\nWINDOW {name}: each w at its leave-one-season-out k, against {COMPARATOR} (the live arm)")
        for w in WS:
            L, pick = loso(C, w, win[name])
            e, lo, hi = boot(L, comp)
            d_log = lrel(L) - lrel(comp)
            by_s = {s: rel(L[L.season == s]) - rel(comp[comp.season == s]) for s in SEASONS}
            better = sum(v < 0 for v in by_s.values())
            c95 = L.cov95.mean()
            print(f"  w {w:g}: k by season {pick}; relWIS {rel(L):.4f} (comparator {rel(comp):.4f}); "
                  f"diff {e:+.4f} [{lo:+.4f}, {hi:+.4f}]; log diff {d_log:+.4f}; "
                  f"by season " + ", ".join(f"{s} {v:+.4f}" for s, v in by_s.items())
                  + f"; cov95 {c95:.3f}")
            res[(name, w)] = dict(rel=rel(L), e=e, lo=lo, hi=hi, d_log=d_log, better=better, c95=c95, pick=pick)
    print("\nTHE RULE (PREREG.txt), window B, candidates w 1, 0.75, 0.5, 0.375 at their own k:")
    passing = []
    for w in WS[:-1]:
        r = res[("B", w)]
        t = {"(a) diff < 0, interval below 0": r["e"] < 0 and r["hi"] < 0,
             "(b) log no more than 0.010 worse": r["d_log"] <= 0.010,
             "(c) better in at least 2 of 3 seasons": r["better"] >= 2,
             "(d) 95% coverage at least 0.90": r["c95"] >= 0.90}
        ok = all(t.values())
        print(f"  w {w:g}: " + "; ".join(f"{k} {'yes' if v else 'NO'}" for k, v in t.items())
              + f" -> {'PASSES' if ok else 'fails'}")
        if ok:
            passing.append((r["rel"], w))
    if not passing:
        print("  -> NO w PASSES: the Oracle stays at 0.25")
    else:
        best = min(passing)[0]
        near = [w for v, w in passing if v - best <= 0.005]
        pick = min(near, key=lambda w: abs(w - 0.25))
        print(f"  -> w {pick:g} PASSES and is chosen (best {best:.4f}; within 0.005, the one nearest 0.25)")
    print("\nREPORTED BESIDE THE RULE:")
    L, pick = loso(C, 0.25, win["B"])
    e, lo, hi = boot(L, C[(C.arm == COMPARATOR) & C.B])
    print(f"  0.25 at its own k (B), k by season {pick}: diff against the live arm {e:+.4f} [{lo:+.4f}, {hi:+.4f}]")
    for name in ("B", "A"):
        Cw = C[win[name](C)]
        print(f"  by horizon, window {name} (relWIS): ")
        H = pd.DataFrame({a: {h: rel(Cw[(Cw.arm == a) & (Cw.horizon == h)]) for h in (0, 1, 2, 3)}
                          for a in [COMPARATOR, "w0.5-k0.7", "w0.5-k1", "w0.75-k1", "w1-k1", "F"]}).T
        print(H.round(4).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "score", "report"])
    ap.add_argument("out")
    a = ap.parse_args()
    {"build": build, "score": score, "report": report}[a.cmd](Path(a.out))
