"""The past-season eps1/phi1 boxes of PREREG.md section 3, applied
mechanically to the season-end fits (arms/FITS). Writes boxes.json (HP's
per-season knob values, HS's per-jurisdiction table) and AMENDMENT1.md (the
values, before HP or HS runs and before any arm is scored).

    build_boxes.py <screen_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

S = Path(sys.argv[1])
FITS = {"2022-23": "2023-06-10", "2023-24": "2024-04-27", "2024-25": "2025-06-14"}
TESTS = {"2023-24": ["2022-23"], "2024-25": ["2022-23", "2023-24"],
         "2025-26": ["2022-23", "2023-24", "2024-25"]}
RANGE = {"eps1": (0.0, 1.0), "phi1": (0.0, 52.0)}
MIN_W = {"eps1": 0.2, "phi1": 8.0}


def wq(x, w, qs):
    o = np.argsort(x)
    x, w = x[o], w[o]
    c = np.cumsum(w) - 0.5 * w
    c /= w.sum()
    return np.interp(qs, c, x)


def fit_summary(season: str, asof: str) -> dict:
    """location -> {param: (q025, median, q975, straddles)} pooled over the
    replicates' saved clouds, each replicate's weights normalised."""
    wd = S / "arms" / "FITS" / season / "weeks" / asof
    cells = json.loads((wd / "cells.json").read_text())
    by_loc: dict = {}
    for c in cells:
        z = np.load(Path(c["dir"]) / "out" / "pf_state.npz")
        names = [str(n) for n in z["param_names"]]
        w = z["weights"] / z["weights"].sum()
        by_loc.setdefault(c["location"], []).append((names, z["theta"], w))
    out = {}
    for loc, reps in by_loc.items():
        names = reps[0][0]
        th = np.vstack([r[1] for r in reps])
        w = np.concatenate([r[2] for r in reps]) / len(reps)
        d = {}
        for p in ("eps1", "phi1"):
            x = th[:, names.index(f"{p}__FREE")]
            lo, med, hi = wq(x, w, [0.025, 0.5, 0.975])
            straddle = False
            if p == "phi1":
                # the same interval on the circle turned half a year: much
                # narrower there means the cloud sits across the wrap
                xr = (x + 26.0) % 52.0
                lo_r, hi_r = wq(xr, w, [0.025, 0.975])
                straddle = bool((hi_r - lo_r) < (hi - lo) - 1.0)
            d[p] = (float(lo), float(med), float(hi), straddle)
        d["n_reps"] = len(reps)
        out[loc] = d
    return out


def widen(lo: float, hi: float, p: str) -> list:
    w = hi - lo
    lo, hi = lo - 0.5 * w, hi + 0.5 * w
    a, b = RANGE[p]
    lo, hi = max(a, lo), min(b, hi)
    if hi - lo < MIN_W[p]:
        mid = 0.5 * (lo + hi)
        lo, hi = mid - MIN_W[p] / 2, mid + MIN_W[p] / 2
        if lo < a:
            lo, hi = a, a + MIN_W[p]
        if hi > b:
            lo, hi = b - MIN_W[p], b
    return [round(lo, 4), round(hi, 4)]


def main() -> None:
    fits = {s: fit_summary(s, a) for s, a in FITS.items()}
    boxes: dict = {}
    lines = []
    for test, earlier in TESTS.items():
        hp, hs, notes = {}, {}, []
        for p in ("eps1", "phi1"):
            meds = [fits[e][loc][p][1] for e in earlier for loc in fits[e]]
            strad = [(e, loc) for e in earlier for loc in fits[e] if fits[e][loc][p][3]]
            if strad:
                notes.append(f"{p}: {len(strad)} fits straddle the wrap {strad[:6]}; HP falls back")
                hp[p] = list(RANGE[p])
            else:
                q05, q95 = np.quantile(meds, [0.05, 0.95])
                hp[p] = widen(float(q05), float(q95), p)
        locs = sorted(set.intersection(*[set(fits[e]) for e in earlier]))
        for loc in locs:
            b = {}
            for p in ("eps1", "phi1"):
                if any(fits[e][loc][p][3] for e in earlier):
                    b[p] = list(RANGE[p])
                    notes.append(f"{loc} {p}: a fit straddles the wrap; shipped range")
                    continue
                lo = min(fits[e][loc][p][0] for e in earlier)
                hi = max(fits[e][loc][p][2] for e in earlier)
                b[p] = widen(lo, hi, p)
            hs[loc] = b
        boxes[test] = {"HP": hp, "HS": hs, "from": earlier, "notes": notes}
        w_e = [v["eps1"][1] - v["eps1"][0] for v in hs.values()]
        w_p = [v["phi1"][1] - v["phi1"][0] for v in hs.values()]
        lines.append(f"- {test} (from {', '.join(earlier)}): HP eps1 {hp['eps1']}, phi1 {hp['phi1']};"
                     f" HS widths over {len(hs)} jurisdictions, eps1 median {np.median(w_e):.3f}"
                     f" (range {min(w_e):.3f}-{max(w_e):.3f}), phi1 median {np.median(w_p):.1f}"
                     f" (range {min(w_p):.1f}-{max(w_p):.1f}) weeks"
                     + (f"; notes: {'; '.join(notes)}" if notes else ""))
    (S / "boxes.json").write_text(json.dumps({"fits": fits, "boxes": boxes}, indent=1))
    summ = []
    for s, f in fits.items():
        e = [v["eps1"][1] for v in f.values()]
        ph = [v["phi1"][1] for v in f.values()]
        summ.append(f"- {s} at {FITS[s]}: {len(f)} jurisdictions; median eps1 {np.median(e):.3f}"
                    f" (5-95%: {np.quantile(e, .05):.3f}-{np.quantile(e, .95):.3f}), median phi1"
                    f" {np.median(ph):.1f} (5-95%: {np.quantile(ph, .05):.1f}-{np.quantile(ph, .95):.1f})")
    (S / "AMENDMENT1.md").write_text(
        "AMENDMENT 1 TO PREREG.md (sha256 fd8f57d6): THE PAST-SEASON BOXES' VALUES\n"
        "Written by build_boxes.py from the season-end fits (arms/FITS), by the\n"
        "rule of section 3, before HP or HS runs and before any arm is scored.\n\n"
        "Season-end fits (per-jurisdiction posterior medians over three replicates):\n"
        + "\n".join(summ) + "\n\nBoxes:\n" + "\n".join(lines) + "\n\nFull tables: boxes.json.\n")
    print((S / "AMENDMENT1.md").read_text())


if __name__ == "__main__":
    main()
