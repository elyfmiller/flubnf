"""Decompose the two-strain member's retrospective scores by data sufficiency.

The question this answers: the member's full-grid failure was diagnosed as
"thin typed-lab data". Gating on typed volume is only worth building if the
member actually does WELL where the data is thick. This scores the stored
two-strain retrospective under the frozen WIS formula, classifies every cell
by what the NREVSS channel actually fed it (vintage-true, from the on-disk
as-of cache), and compares against production PF on identical cells.

Three cell classes, not two. `nrevss.a_share_series` falls back to the state's
HHS REGION when the state returns no rows or all-zero specimens, so a state
with no clinical reporting was never running on thin data -- it was running on
someone else's data at high volume. A volume-only gate would mark those cells
eligible. They need their own class.

Run from the repo root with the engine venv.
"""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core import ensemble as ens               # noqa: E402
from app.core.scoring import _baseline_cells, load_truth   # noqa: E402
from flubnf import nrevss                          # noqa: E402
from flubnf.wis import wis as wis_fn               # noqa: E402

STATE = REPO / "app" / "state"
SEASONS = ("2023-24", "2024-25", "2025-26")
# The engine's own convention, read back off the cache: cached epiweek ranges
# start at 2023-31 / 2024-31, i.e. season_start = August 1.
SEASON_START = {"2023-24": "2023-08-01", "2024-25": "2024-08-01",
                "2025-26": "2025-08-01"}
N_STAR = 64          # pre-registered: SE(A-share) < 0.05 at p=0.8
TRAILING = 4         # pre-registered trailing-window weeks


# ----------------------------------------------------------------- scoring
def score_member(root: Path, member: str, truth, n2f) -> pd.DataFrame:
    """Frozen formula, lifted from app.core.retro.score_season.

    Same guards: truth > 0, median > 0, cell present in the validated
    baseline. Only the member key differs.
    """
    rows = []
    for wk in sorted((root / "weeks").glob("*/samples.json")):
        d = json.loads(wk.read_text())
        if member not in d:
            continue
        asof = d["asof"]
        T = pd.Timestamp(asof)
        for loc, samples in d[member].items():
            fips = n2f.get(loc)
            if not fips:
                continue
            try:
                qs = ens.member_quantiles_from_samples(samples)
            except Exception:
                continue
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
                rows.append({"location": loc, "fips": fips, "asof": asof,
                             "horizon": int(h) - 1, "wis": w})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    bases = {}
    for asof in df["asof"].unique():
        try:
            bs = _baseline_cells(asof, set(df[df["asof"] == asof].fips), truth)
        except Exception:
            bs = {}
        bases.update(bs)
    df["base_wis"] = [bases.get((r.fips, r.asof, r.horizon), np.nan)
                      for r in df.itertuples()]
    return df.dropna(subset=["base_wis"]).assign(rel=lambda x: x.wis / x.base_wis)


# ------------------------------------------------------- channel classification
# nrevss._abbr_for() re-reads locations.csv on EVERY call, and classify() makes
# three such calls per cell. Across ~4k cells that dominated the runtime (a
# first run burned 8 CPU-minutes without finishing). Memoize it.
_ABBR: dict = {}


_ORIG_ABBR_FOR = nrevss._abbr_for


def abbr_for(location: str) -> str:
    if location not in _ABBR:
        # MUST call the ORIGINAL: the patch below points nrevss._abbr_for at
        # this function, so calling it here would recurse. A first run did
        # exactly that, and the bare excepts in classify() turned the
        # RecursionError into "thin data" for all 3,899 cells.
        _ABBR[location] = _ORIG_ABBR_FOR(location)
    return _ABBR[location]


nrevss._abbr_for = lambda name, locations_csv=None: abbr_for(name)

#: classification failures, surfaced instead of silently defaulting
FAILURES: dict = {}


#: region -> {issue -> {epiweek: (total_a, total_b, total_specimens)}}
_CACHE: dict = {}


def load_cache() -> None:
    """Read every cached (region, issue) snapshot into memory once.

    Reading the cache directly rather than calling fetch_typed is deliberate:
    fetch_typed treats an epiweek range wider than the cached one as a MISS and
    goes to the network, and Delphi is rate-limiting. Every row here was
    fetched by the engine during the actual retrospective, so reconstructing
    the as-of view from it is vintage-true by construction.
    """
    for path in (STATE / "nrevss").glob("*_*.json"):
        try:
            blob = json.loads(path.read_text())
        except Exception:
            continue
        region, issue = str(blob.get("region", "")), int(blob.get("issue", 0))
        rows = (blob.get("response") or {}).get("epidata") or []
        if not region or not issue:
            continue
        d = _CACHE.setdefault(region, {}).setdefault(issue, {})
        for r in rows:
            d[int(r["epiweek"])] = (float(r.get("total_a") or 0),
                                    float(r.get("total_b") or 0),
                                    float(r.get("total_specimens") or 0))


def typed_asof(region: str, asof_ew: int) -> list:
    """As-of typed series for `region`: latest issue <= asof_ew, per epiweek.

    Returns [(epiweek, total_a, total_b, total_specimens)] ascending.
    """
    by_issue = _CACHE.get(region)
    if not by_issue:
        return []
    best: dict = {}
    for issue, rows in by_issue.items():
        if issue > asof_ew:
            continue
        for ew, vals in rows.items():
            if ew > issue:
                continue           # a snapshot cannot contain its own future
            if ew not in best or issue > best[ew][0]:
                best[ew] = (issue, vals)
    return [(ew, *best[ew][1]) for ew in sorted(best)]


def trailing_typed(series: list, asof_ew: int) -> float:
    """Median A+B over the TRAILING weeks ending at the last available week."""
    if not series:
        return np.nan
    vals = [a + b for ew, a, b, _ in series if ew <= asof_ew]
    if not vals:
        return np.nan
    return float(np.median(vals[-TRAILING:]))


def classify(location: str, season: str, asof: str) -> dict:
    """What the NREVSS channel actually fed this cell, as of `asof`.

    Honest as-of: NREVSS issue <ew> publishes the Friday AFTER that week ends,
    i.e. after the FluSight deadline, so a forecast made on Saturday D can only
    use typed data through D-7. Mirrors pf.prepare's nrevss_asof.
    """
    out = {"source": None, "fallback": None, "typed_med": np.nan,
           "own_typed_med": np.nan, "n_weeks": 0}
    asof_ew = nrevss._ew(pd.Timestamp(asof).date() - timedelta(days=7))
    abbr = abbr_for(location)
    region = "nat" if abbr == "us" else abbr

    own = typed_asof(region, asof_ew)
    own_usable = bool(own) and sum(s for _, _, _, s in own) > 0
    out["own_typed_med"] = trailing_typed(own, asof_ew)

    if own_usable:
        src, series = region, own
    elif abbr in nrevss.STATE_TO_HHS:
        src = f"hhs{nrevss.STATE_TO_HHS[abbr]}"
        series = typed_asof(src, asof_ew)
    else:
        FAILURES[f"no data and no HHS mapping: {abbr}"] = \
            FAILURES.get(f"no data and no HHS mapping: {abbr}", 0) + 1
        return out
    if not series:
        FAILURES["empty after fallback"] = FAILURES.get("empty after fallback", 0) + 1
        return out
    out["source"] = src
    out["fallback"] = src.startswith("hhs") or (src == "nat" and abbr != "us")
    out["n_weeks"] = len(series)
    out["typed_med"] = trailing_typed(series, asof_ew)
    return out


def main() -> int:
    out = REPO / "research" / "twostrain-decomposition"
    cache = out / "paired_scores.csv"
    if cache.is_file():
        print(f"reusing cached scores {cache.name}", file=sys.stderr, flush=True)
        return report(pd.read_csv(cache), out)
    truth, n2f = load_truth()
    frames = []
    for season in SEASONS:
        root2s = STATE / "retro_2s" / season
        rootseal = STATE / "retro_seal" / season
        if not (root2s / "weeks").is_dir():
            print(f"  {season}: no two-strain weeks, skipping", file=sys.stderr)
            continue
        d2s = score_member(root2s, "pf2s", truth, n2f)
        dpf = score_member(rootseal, "pf", truth, n2f)
        if d2s.empty:
            print(f"  {season}: two-strain scored 0 cells", file=sys.stderr)
            continue
        d2s["season"] = season
        key = ["location", "fips", "asof", "horizon"]
        merged = d2s.merge(dpf[key + ["wis", "rel"]], on=key,
                           suffixes=("_2s", "_pf"), how="inner")
        merged["season"] = season
        print(f"  {season}: 2s cells {len(d2s)}, pf cells {len(dpf)}, "
              f"paired {len(merged)}", file=sys.stderr)
        frames.append(merged)
    if not frames:
        raise SystemExit("nothing scored")
    df = pd.concat(frames, ignore_index=True)
    df.to_csv(cache, index=False)
    return report(df, out)


def report(df: pd.DataFrame, out: Path) -> int:
    load_cache()
    print(f"loaded NREVSS cache: {len(_CACHE)} regions, "
          f"{sum(len(v) for v in _CACHE.values())} snapshots",
          file=sys.stderr, flush=True)
    # classify each distinct (location, season, asof) once
    cls = {}
    keys = df[["location", "season", "asof"]].drop_duplicates()
    print(f"classifying {len(keys)} (location, season, asof) cells...",
          file=sys.stderr, flush=True)
    for i, r in enumerate(keys.itertuples(), 1):
        cls[(r.location, r.season, r.asof)] = classify(r.location, r.season,
                                                       r.asof)
        if i % 200 == 0:
            print(f"    {i}/{len(keys)}", file=sys.stderr, flush=True)
    for col in ("source", "fallback", "typed_med", "own_typed_med"):
        df[col] = [cls[(r.location, r.season, r.asof)][col]
                   for r in df.itertuples()]

    if FAILURES:
        print("\nCLASSIFICATION FAILURES:", file=sys.stderr)
        for k, v in sorted(FAILURES.items(), key=lambda kv: -kv[1]):
            print(f"  {v:6d}  {k}", file=sys.stderr)
    resolved = int(df.source.notna().sum())
    if resolved == 0:
        raise SystemExit(
            "every cell failed to classify -- refusing to report that as "
            "'all thin', which is what a silent default would have done")
    print(f"\nclassified {resolved}/{len(df)} cells "
          f"({100*resolved/len(df):.1f}%)", file=sys.stderr)

    df["eligible_asrun"] = df.typed_med >= N_STAR       # gate on the fed series
    df["own_adequate"] = df.own_typed_med >= N_STAR     # gate on own-state data
    df["klass"] = np.where(df.fallback == True, "HHS fallback",  # noqa: E712
                    np.where(df.own_adequate, "own state, adequate",
                             "own state, thin"))
    out = REPO / "research" / "twostrain-decomposition"
    df.to_csv(out / "cells.csv", index=False)

    def block(sub, label):
        if not len(sub):
            return None
        return {
            "class": label, "cells": len(sub),
            "states": sub.location.nunique(),
            "wis_mass": float(sub.base_wis.sum()),
            "rel_2s": float(sub.wis_2s.sum() / sub.base_wis.sum()),
            "rel_pf": float(sub.wis_pf.sum() / sub.base_wis.sum()),
        }

    print("\n" + "=" * 78)
    print("TWO-STRAIN MEMBER, DECOMPOSED BY WHAT THE NREVSS CHANNEL FED IT")
    print("=" * 78)
    print("relWIS pools WIS across cells (sum wis / sum base_wis), the frozen")
    print(f"convention. n* = {N_STAR} typed positives, trailing {TRAILING} wk.\n")
    rows = [block(df, "ALL CELLS")]
    for k in ("own state, adequate", "own state, thin", "HHS fallback"):
        rows.append(block(df[df.klass == k], k))
    rows = [r for r in rows if r]
    hdr = f"{'class':22}{'cells':>7}{'states':>8}{'WIS mass %':>12}{'2-strain':>10}{'prod PF':>9}{'delta':>8}"
    print(hdr)
    print("-" * len(hdr))
    total_mass = rows[0]["wis_mass"]
    for r in rows:
        d = r["rel_2s"] - r["rel_pf"]
        print(f"{r['class']:22}{r['cells']:7d}{r['states']:8d}"
              f"{100*r['wis_mass']/total_mass:11.1f}%{r['rel_2s']:10.3f}"
              f"{r['rel_pf']:9.3f}{d:+8.3f}")

    print("\nby season, own-state-adequate cells only (the gate's target set):")
    print(f"{'season':10}{'cells':>7}{'2-strain':>10}{'prod PF':>9}{'delta':>8}")
    for s in SEASONS:
        sub = df[(df.season == s) & (df.klass == "own state, adequate")]
        if not len(sub):
            continue
        r2 = sub.wis_2s.sum() / sub.base_wis.sum()
        rp = sub.wis_pf.sum() / sub.base_wis.sum()
        print(f"{s:10}{len(sub):7d}{r2:10.3f}{rp:9.3f}{r2-rp:+8.3f}")

    print("\nstate-week eligibility across the actual grid:")
    cw = df[["location", "season", "asof", "klass", "typed_med",
             "own_typed_med"]].drop_duplicates()
    tot = len(cw)
    for k in ("own state, adequate", "own state, thin", "HHS fallback"):
        n = int((cw.klass == k).sum())
        print(f"  {k:22} {n:5d} / {tot} state-weeks  ({100*n/tot:.1f}%)")
    print(f"\n  as-run gate (on the FED series, fallback included) would pass "
          f"{int((cw.typed_med >= N_STAR).sum())}/{tot} "
          f"({100*(cw.typed_med >= N_STAR).mean():.1f}%)")
    print(f"  strict gate (own-state series only) would pass "
          f"{int((cw.own_typed_med >= N_STAR).sum())}/{tot} "
          f"({100*(cw.own_typed_med >= N_STAR).mean():.1f}%)")
    print(f"\nwrote {out/'cells.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
