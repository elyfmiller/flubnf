"""The decision the decomposition does not answer: does SEATING the two-strain
member help the ensemble, on the cells the pre-registered gate would keep?

A member can be worse than the PF alone and still earn a seat by diversifying.
decompose.py showed the member is relatively WORST exactly where the gate keeps
cells, but that is a member-vs-member comparison. This scores the thing that
actually ships: 2-member (pf + analogue) vs 3-member (pf + analogue + pf2s),
equal weights, identical cells, split by the same three data classes.

Reuses decompose.py's classifier so the cell classes are identical.
"""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))

_spec = spec_from_file_location("decompose", HERE / "decompose.py")
D = module_from_spec(_spec)
_spec.loader.exec_module(D)

from app.core import ensemble as ens                       # noqa: E402
from app.core.scoring import _baseline_cells, load_truth   # noqa: E402
from flubnf.wis import wis as wis_fn                       # noqa: E402

STATE = REPO / "app" / "state"


def week_samples(root: Path) -> dict:
    """asof -> parsed samples.json for every stored week."""
    out = {}
    for wk in sorted((root / "weeks").glob("*/samples.json")):
        d = json.loads(wk.read_text())
        out[d["asof"]] = d
    return out


def main() -> int:
    truth, n2f = load_truth()
    D.load_cache()
    rows = []
    for season in D.SEASONS:
        seal = week_samples(STATE / "retro_seal" / season)
        two = week_samples(STATE / "retro_2s" / season)
        shared = sorted(set(seal) & set(two))
        print(f"  {season}: {len(shared)} shared weeks", file=sys.stderr,
              flush=True)
        for asof in shared:
            ds, dt = seal[asof], two[asof]
            T = pd.Timestamp(asof)
            locs = set(ds.get("pf", {})) & set(ds.get("analogue", {})) \
                & set(dt.get("pf2s", {}))
            for loc in locs:
                fips = n2f.get(loc)
                if not fips:
                    continue
                try:
                    pf_q = ens.member_quantiles_from_samples(ds["pf"][loc])
                    an_q = {h: {float(k): v for k, v in q.items()}
                            for h, q in ds["analogue"][loc].items()}
                    ts_q = ens.member_quantiles_from_samples(dt["pf2s"][loc])
                except Exception:
                    continue
                e2 = ens.vincentize({"pf": pf_q, "analogue": an_q},
                                    location_fips=fips)
                e3 = ens.vincentize({"pf": pf_q, "analogue": an_q,
                                     "pf2s": ts_q}, location_fips=fips)
                for h in ("1", "2", "3", "4"):
                    q2, q3 = e2.get(h), e3.get(h)
                    if not q2 or not q3:
                        continue
                    actual = truth.get((fips, T + timedelta(days=7 * int(h))))
                    if actual is None or actual <= 0:
                        continue
                    if q2[0.5] <= 0 or q3[0.5] <= 0:
                        continue
                    try:
                        w2 = float(wis_fn(q2, actual).wis)
                        w3 = float(wis_fn(q3, actual).wis)
                    except Exception:
                        continue
                    rows.append({"season": season, "location": loc,
                                 "fips": fips, "asof": asof,
                                 "horizon": int(h) - 1,
                                 "wis_ens2": w2, "wis_ens3": w3})
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("nothing scored")
    bases = {}
    for asof in df["asof"].unique():
        try:
            bases.update(_baseline_cells(asof,
                                         set(df[df.asof == asof].fips), truth))
        except Exception:
            pass
    df["base_wis"] = [bases.get((r.fips, r.asof, r.horizon), np.nan)
                      for r in df.itertuples()]
    df = df.dropna(subset=["base_wis"])

    cls = {}
    keys = df[["location", "season", "asof"]].drop_duplicates()
    print(f"classifying {len(keys)} cells...", file=sys.stderr, flush=True)
    for r in keys.itertuples():
        cls[(r.location, r.season, r.asof)] = D.classify(r.location, r.season,
                                                         r.asof)
    df["fallback"] = [cls[(r.location, r.season, r.asof)]["fallback"]
                      for r in df.itertuples()]
    df["own_med"] = [cls[(r.location, r.season, r.asof)]["own_typed_med"]
                     for r in df.itertuples()]
    df["klass"] = np.where(df.fallback == True, "HHS fallback",   # noqa: E712
                    np.where(df.own_med >= D.N_STAR, "own state, adequate",
                             "own state, thin"))
    df.to_csv(HERE / "ensemble_cells.csv", index=False)

    print("\n" + "=" * 74)
    print("DOES SEATING THE TWO-STRAIN MEMBER HELP THE ENSEMBLE?")
    print("=" * 74)
    print("equal-weight quantile average, identical cells, frozen relWIS.\n")
    hdr = (f"{'class':22}{'cells':>7}{'2-member':>11}{'3-member':>11}"
           f"{'delta':>9}{'verdict':>10}")
    print(hdr)
    print("-" * len(hdr))
    for label, sub in [("ALL CELLS", df)] + [
            (k, df[df.klass == k]) for k in
            ("own state, adequate", "own state, thin", "HHS fallback")]:
        if not len(sub):
            continue
        r2 = sub.wis_ens2.sum() / sub.base_wis.sum()
        r3 = sub.wis_ens3.sum() / sub.base_wis.sum()
        v = "helps" if r3 < r2 else "hurts"
        print(f"{label:22}{len(sub):7d}{r2:11.3f}{r3:11.3f}{r3-r2:+9.3f}{v:>10}")

    print("\nby season, on the cells the pre-registered gate would KEEP:")
    print(f"{'season':10}{'cells':>7}{'2-member':>11}{'3-member':>11}{'delta':>9}")
    keep = df[df.klass == "own state, adequate"]
    for s in D.SEASONS:
        sub = keep[keep.season == s]
        if not len(sub):
            continue
        r2 = sub.wis_ens2.sum() / sub.base_wis.sum()
        r3 = sub.wis_ens3.sum() / sub.base_wis.sum()
        print(f"{s:10}{len(sub):7d}{r2:11.3f}{r3:11.3f}{r3-r2:+9.3f}")
    print(f"\nwrote {HERE/'ensemble_cells.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
