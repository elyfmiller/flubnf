"""RESEARCH CLI ONLY (`flubnf groundhog retro`): analogue-alone season replays
with coverage and bootstrap comparisons.

GroundHogCGR on its own: a season replay of the calendar member alone.

Separate from `retro.run_season` because the question "what does the
calendar member score alone" should not pay for (or wait on the toolchain
of) the particle filter: this replays a season in ~2 minutes from the repo
and a hub clone. It calls the same engine (`app.core.engines.analogue.run`)
with retro.run_week's spec shape; the quantiles were verified identical to
the console's stored ones. retro.run_season(engine="analogue") is the console
path; this one adds research arms, coverage and a bootstrap comparison.

Scores the 52 two-character-FIPS jurisdictions (the published convention);
US, with `with_us=True`, is reported separately, never pooled. Vintage
discipline is the engine's. Artefacts are born canonical (hub horizons 0..3,
no anchor week) and say so in their header.
"""
from __future__ import annotations

import gzip
import json
import subprocess
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.core import horizons as hz
from app.core import retro, scoring
from app.core.engines import analogue as an_engine
from app.core.runs import RunSpec
from flubnf import analogue as AN

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "app" / "state" / "groundhog"

#: central intervals reported, as (label, lower level, upper level, nominal)
BANDS = (("50", 0.25, 0.75, 0.50), ("80", 0.10, 0.90, 0.80),
         ("95", 0.025, 0.975, 0.95))

#: the bare calendar analogue's arm (historical dir name: the shipped
#: Groundhog is the `flusurv` arm, `--aux flusurv`)
SHIPPED = "shipped"


def console_locations() -> list:
    """The jurisdictions the console forecasts: two-character FIPS, US
    national excluded. One definition, the same one `retro_cmd` uses."""
    from flubnf.settings import LOCATIONS
    locs = pd.read_csv(LOCATIONS, dtype=str)
    return list(locs.location_name[locs.location.str.len() == 2]
                [locs.abbreviation != "US"])


def _name2fips() -> dict:
    from flubnf.settings import LOCATIONS
    locs = pd.read_csv(LOCATIONS, dtype=str)
    return dict(zip(locs.location_name, locs.location))


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short",
                               "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def forecast_week(season: str, asof: str, locations: list,
                  extra: dict | None) -> dict:
    """One as-of, the engine's own output: {location: {"0".."3": {level: v}}}.

    The spec is the one `retro.run_week` builds, field for field, so the
    engine cannot tell this call from the console's."""
    spec = RunSpec(engine="retro", forecast_date=asof, locations=locations,
                   season_start=retro.season_bounds(season)[0],
                   replicates=3, particles=10_000, drop_same_day=False,
                   extra=dict(extra or {}))
    return an_engine.run(spec)


def score_week(q_by_loc: dict, asof: str, n2f: dict, truth: dict) -> tuple:
    """(cells, coverage) for one week. `cells` is scoring.score_quantiles'
    frame, under THE cell rule (scoring.cell_scored: settled truth, 0
    included; a forecast with finite quantiles; the cell present in the
    validated FluSight baseline). `coverage` holds one row per (cell, band)
    with a hit flag, and a `scored` flag saying whether that cell is in
    `cells`: `summarise` reports coverage on the scored cells only, so
    relWIS and coverage describe the same cells."""
    cells = scoring.score_quantiles(q_by_loc, asof, n2f, truth)
    scored = (set(zip(cells.fips.astype(str), cells.horizon.astype(int)))
              if not cells.empty else set())
    cov = []
    T = pd.Timestamp(asof)
    for loc, qs in q_by_loc.items():
        fips = n2f.get(loc)
        if not fips:
            continue
        for h in hz.HORIZONS:
            q = qs.get(h)
            if not q:
                continue
            # canonical horizon h is h+1 weeks past the as-of
            actual = truth.get((fips, T + timedelta(days=7 * (int(h) + 1))))
            if not scoring.truth_settled(actual):
                continue
            for label, lo, hi, _nom in BANDS:
                cov.append({"location": loc, "fips": fips, "horizon": int(h),
                            "band": label,
                            "hit": int(q[lo] <= actual <= q[hi]),
                            "scored": (str(fips), int(h)) in scored})
    return cells, pd.DataFrame(cov)


def run_season(season: str, aux: str = "", *, with_us: bool = False,
               root: Path | None = None, progress=None) -> dict:
    """Replay one season of the calendar member alone and store the record.

    `aux` names an auxiliary preset (`an_engine.AUX_PRESETS`); empty runs
    the bare single-pool analogue (the `shipped` arm directory, its
    historical name; the Groundhog is `aux="flusurv"`). Returns the season
    summary."""
    arm = aux or SHIPPED
    week_extra = an_engine.aux_preset(aux) if aux else None
    locations = console_locations() + (["US"] if with_us else [])
    n2f = _name2fips()
    truth, _ = scoring.load_truth()
    vintages = retro.season_vintages(season)
    if not vintages:
        raise FileNotFoundError(
            f"no hub vintages found for season {season}. The replay reads "
            f"auxiliary-data/target-data-archive from the hub clone "
            f"(FLUBNF_HUB); see `flubnf doctor`.")
    out_dir = (Path(root) if root else STATE / arm / season)
    out_dir.mkdir(parents=True, exist_ok=True)

    forecasts, cells, cov, abstained = {}, [], [], 0
    for i, asof in enumerate(vintages):
        extra = week_extra(asof, i, vintages) if week_extra else None
        q = forecast_week(season, asof, locations, extra)
        abstained += len(locations) - len(q)
        forecasts[asof] = {loc: {h: {repr(float(L)): float(v)
                                     for L, v in lv.items()}
                                 for h, lv in hq.items()}
                           for loc, hq in q.items()}
        c, v = score_week(q, asof, n2f, truth)
        if not c.empty:
            c["asof"] = asof
            cells.append(c)
        if not v.empty:
            v["asof"] = asof
            cov.append(v)
        if progress:
            progress(asof, i + 1, len(vintages))

    cells_df = (pd.concat(cells, ignore_index=True) if cells
                else pd.DataFrame(columns=["location", "fips", "horizon",
                                           "wis", "base_wis", "rel", "asof"]))
    cov_df = (pd.concat(cov, ignore_index=True) if cov
              else pd.DataFrame(columns=["location", "fips", "horizon",
                                         "band", "hit", "scored", "asof"]))
    for df in (cells_df, cov_df):
        df["season"] = season
        df["arm"] = arm

    meta = {
        "model": "GroundHogCGR", "season": season, "arm": arm,
        # the preset's name carries the committed bank's digest, so this
        # says WHICH DONORS, not only which configuration
        "aux": (week_extra.__name__ if week_extra else None),
        "horizon_convention": "hub 0..3 (app.core.horizons), no anchor week",
        "locations": len(locations), "with_us": bool(with_us),
        "vintages": len(vintages), "first": vintages[0], "last": vintages[-1],
        "location_weeks_abstained": int(abstained),
        "bandwidth": AN.DEFAULT_BANDWIDTH, "min_donors": AN.MIN_DONORS,
        "excluded_donor_seasons": sorted(AN.EXCLUDED_DONOR_SEASONS),
        "truth_source": scoring.TRUTH_SOURCE, "commit": _git_commit(),
    }
    with gzip.open(out_dir / "forecasts.json.gz", "wt", encoding="utf-8") as f:
        json.dump({"meta": meta, "forecasts": forecasts}, f)
    cells_df.to_csv(out_dir / "cells.csv.gz", index=False)
    cov_df.to_csv(out_dir / "coverage.csv.gz", index=False)
    summary = summarise(cells_df, cov_df)
    (out_dir / "run_meta.json").write_text(
        json.dumps({**meta, "summary": summary}, indent=1) + "\n")
    return {"meta": meta, "summary": summary, "cells": cells_df,
            "coverage": cov_df, "dir": str(out_dir)}


def _states(df: pd.DataFrame) -> pd.DataFrame:
    return df[df.fips.astype(str) != "US"]


# DataFrame.asof is a pandas method: always write df["asof"], never df.asof
def summarise(cells: pd.DataFrame, cov: pd.DataFrame) -> dict:
    """relWIS as a ratio of sums, and coverage, over the STATES. The
    national row, when present, is summarised beside it and never inside."""
    def block(c, v):
        if c.empty:
            return {"cells": 0}
        out = {"cells": int(len(c)), "weeks": int(c["asof"].nunique()),
               "relwis": float(c.wis.sum() / c.base_wis.sum())}
        worst = 0.0
        if "scored" in v.columns:
            v = v[v.scored.astype(bool)]        # the same cells relWIS uses
        for label, _lo, _hi, nom in BANDS:
            b = v[v.band.astype(str) == label]
            if len(b):
                out[f"cov{label}"] = float(b.hit.mean())
                worst = max(worst, abs(out[f"cov{label}"] - nom))
        out["worst_dev"] = float(worst)
        return out
    res = {"states": block(_states(cells), _states(cov))}
    us_c, us_v = cells[cells.fips.astype(str) == "US"], cov[cov.fips.astype(str) == "US"]
    if len(us_c):
        res["us"] = block(us_c, us_v)
    return res


def compare(a_cells: pd.DataFrame, a_cov: pd.DataFrame,
            b_cells: pd.DataFrame, b_cov: pd.DataFrame,
            reps: int = 4000, seed: int = 7) -> dict:
    """Two arms on IDENTICAL cells, states only, with a clustered bootstrap
    over as-of dates for the difference in relWIS (b minus a). Identical
    cells, because an arm may abstain where the other forecasts."""
    key = ["fips", "asof", "horizon"]
    a, b = _states(a_cells), _states(b_cells)
    common = a[key].merge(b[key], on=key)
    a = a.merge(common, on=key); b = b.merge(common, on=key)
    av = _states(a_cov).merge(common, on=key)
    bv = _states(b_cov).merge(common, on=key)
    out = {"common_cells": int(len(common)),
           "a": summarise(a, av)["states"], "b": summarise(b, bv)["states"],
           "by_season": {}}
    for s in sorted(set(a.season)):
        out["by_season"][s] = {
            "a": summarise(a[a.season == s], av[av.season == s])["states"],
            "b": summarise(b[b.season == s], bv[bv.season == s])["states"]}
    asofs = np.array(sorted(common["asof"].unique()))
    if len(asofs) >= 2:
        def sums(df):
            g = (df.groupby("asof")[["wis", "base_wis"]].sum()
                   .reindex(asofs).fillna(0.0))
            return g.wis.to_numpy(), g.base_wis.to_numpy()
        (aw, ab), (bw, bb) = sums(a), sums(b)
        rng = np.random.default_rng(seed)
        pick = rng.integers(0, len(asofs), size=(reps, len(asofs)))
        d = bw[pick].sum(1) / bb[pick].sum(1) - aw[pick].sum(1) / ab[pick].sum(1)
        ds = np.sort(d)
        out["bootstrap"] = {"reps": reps, "clusters": int(len(asofs)),
                            "median": float(np.median(d)),
                            "lo": float(ds[int(0.025 * reps)]),
                            "hi": float(ds[int(0.975 * reps)]),
                            "b_better": int((d < 0).sum())}
    return out
