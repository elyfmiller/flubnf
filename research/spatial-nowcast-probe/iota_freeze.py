"""Freeze `iota` for BUILD 1 (national-growth term in the PF).

This script exists so the number in `flubnf/natgrowth.py::IOTA_FROZEN` is
reproducible and so nobody has to re-derive it by hand. It is the only place
`iota` is ever computed. It is run ONCE, before any PF fit, and its output is
copied into the constant. Re-running it after seeing PF scores and changing the
constant would violate the handoff's Law 1 (nothing is fitted on past-season
scores).

RECIPE (handoff 2026-08-21 section 3, verbatim):

    the regression coefficient of g_{t+1} on g_nat given g_t and a Fourier
    seasonal, averaged over 2023-24 and 2024-25 only, then multiplied by 0.5
    for conservatism.

Construction of the covariates is COPIED from `probe.py::spatial()` so the
coefficient means the same thing it meant when the effect was measured:

  * final (settled) data, not vintages -- spatial coupling is a biological
    claim, not a revision claim (probe.py docstring). The frozen scalar is a
    property of influenza, not of the reporting pipeline. The PRODUCTION
    series that this scalar multiplies is vintage-true; see natgrowth.py.
  * per-state weekly log-growth, weeks whose level is under 20 skipped,
  * `g_nat` = population-weighted leave-one-out mean of the other
    jurisdictions' log-growth at the SAME week,
  * seasonal control = first Fourier harmonic on week-of-season.

Run from the repo root with the ANALYSIS venv:

    ./.venv/bin/python research/spatial-nowcast-probe/iota_freeze.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core.data import vintage_path, vintages  # noqa: E402
from flubnf.settings import LOCATIONS  # noqa: E402

#: Seasons the coefficient is averaged over. 2025-26 is deliberately absent:
#: the handoff pins the derivation to these two and forbids retuning.
FREEZE_SEASONS = ("2023-24", "2024-25")

#: Shrink toward zero so the first arm is conservative (handoff section 3).
SHRINK = 0.5


def season_of(d) -> str:
    ts = pd.Timestamp(d)
    y = ts.year if ts.month >= 8 else ts.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def build_frame() -> pd.DataFrame:
    """probe.py::spatial()'s design matrix, verbatim in construction."""
    loc = pd.read_csv(LOCATIONS, dtype=str)
    fips2pop = dict(zip(loc.location.str.zfill(2),
                        pd.to_numeric(loc.population, errors="coerce")))

    df = pd.read_csv(vintage_path(vintages()[-1]), dtype={"location": str})
    df["location"] = df["location"].str.zfill(2)
    df["date"] = pd.to_datetime(df["date"])
    df = df[df.location != "US"].copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])
    df["season"] = df["date"].map(season_of)
    df = df[df.season.isin(("2023-24", "2024-25", "2025-26"))]
    df["pop"] = df.location.map(fips2pop)
    df = df.dropna(subset=["pop"])

    rows = []
    for loc_id, g in df.groupby("location"):
        g = g.sort_values("date")
        v = g.value.to_numpy(float)
        if (v <= 0).all() or len(v) < 20:
            continue
        gr = np.diff(np.log(np.maximum(v, 1.0)))
        dates = g.date.to_numpy()[1:]
        seas = g.season.to_numpy()[1:]
        pop = float(g["pop"].iloc[0])
        for i in range(len(gr) - 1):
            if v[i + 1] < 20:          # skip the summer floor, as probe.py does
                continue
            rows.append((loc_id, seas[i], dates[i], pop, gr[i], gr[i + 1]))
    R = pd.DataFrame(rows, columns=["loc", "season", "date", "pop",
                                    "g_t", "g_tp1"])

    nat = {}
    for _, sub in R.groupby(["date", "season"]):
        w = sub["pop"].to_numpy()
        g = sub.g_t.to_numpy()
        tot, wsum = (w * g).sum(), w.sum()
        for loc_id, p, gg in zip(sub["loc"], sub["pop"], sub.g_t):
            nat[(_[0], loc_id)] = (tot - p * gg) / max(wsum - p, 1)
    R["g_nat"] = [nat.get((d, l), np.nan) for d, l in zip(R.date, R["loc"])]
    R = R.dropna(subset=["g_nat"]).copy()

    wos = ((pd.to_datetime(R.date)
            - pd.to_datetime(R.season.str[:4] + "-08-01")).dt.days // 7
           ).astype(float)
    two_pi = 2 * np.pi / 52.0
    R["sin1"] = np.sin(two_pi * wos)
    R["cos1"] = np.cos(two_pi * wos)
    return R


def coef(frame: pd.DataFrame, cols: list) -> np.ndarray:
    """OLS coefficients of g_tp1 on [1] + cols."""
    M = np.column_stack([np.ones(len(frame))]
                        + [frame[c].to_numpy(float) for c in cols])
    b, *_ = np.linalg.lstsq(M, frame.g_tp1.to_numpy(float), rcond=None)
    return b


def main() -> None:
    R = build_frame()
    cols = ["g_t", "sin1", "cos1", "g_nat"]
    print(f"design matrix: {len(R)} state-weeks, "
          f"{R.season.nunique()} seasons\n")
    print(f"{'fit on':>18}{'n':>7}{'b[g_t]':>10}{'b[g_nat]':>11}")
    per_season = {}
    for s in FREEZE_SEASONS:
        sub = R[R.season == s]
        b = coef(sub, cols)
        per_season[s] = float(b[4])
        print(f"{s:>18}{len(sub):7d}{b[1]:10.4f}{b[4]:11.4f}")

    pooled = R[R.season.isin(FREEZE_SEASONS)]
    bp = coef(pooled, cols)
    print(f"{'pooled (both)':>18}{len(pooled):7d}{bp[1]:10.4f}{bp[4]:11.4f}"
          "   <- cross-check")

    held_out = R[~R.season.isin(FREEZE_SEASONS)]
    if len(held_out):
        bh = coef(held_out, cols)
        print(f"{'2025-26 (unused)':>18}{len(held_out):7d}{bh[1]:10.4f}"
              f"{bh[4]:11.4f}   <- NOT in the average")

    raw = float(np.mean(list(per_season.values())))
    iota = SHRINK * raw
    print(f"\nmean b[g_nat] over {' + '.join(FREEZE_SEASONS)} = {raw:.4f}")
    print(f"shrink x{SHRINK}                             -> "
          f"IOTA_FROZEN = {iota:.4f}")
    print(f"\nrounded for the constant: {round(iota, 3)}")


if __name__ == "__main__":
    main()
