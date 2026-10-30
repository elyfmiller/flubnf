"""OPS: the FluSight dashboard's scores, reproduced from the hub's own files.

The dashboard (reichlab/flusight-dashboard, built by hubPredEvalsData on
scoringutils) ranks models by relative WIS: for every pair of models, the
ratio of their mean WIS on the forecasts both made; each model's score is
the geometric mean of its ratios against every model (itself included, ratio
1; pairs with no forecast in common left out), divided by FluSight-baseline's.
It reports the same on the log(x + 1) scale, and 50% and 95% coverage.

This script scores every model's quantile file of the given rounds for
'wk inc flu hosp' against the hub's target-data/oracle-output.csv and prints,
for the national (US) and state sets, each listed model's relative WIS and
placement among the models that forecast this season, and the error split:
the WIS of each forecast is spread (interval width) plus the penalties for
truth below or above the intervals (scoringutils' dispersion, under- and
overprediction). With --dashboard it compares every model's relative WIS
with the dashboard's published scores (a checkout of its predevals/data
branch) and fails on any difference.

Give the rounds the dashboard's eval set holds: its "Last 4 weeks" set is
the last five rounds, which early in a season reach back into the last one.
The levels must be FluSight's 23 (a median and symmetric pairs), on which
WIS is twice the mean pinball loss. A parquet file needs pyarrow; without it
the file is skipped, said so, and the scores will not match the dashboard.

Usage:
    python scripts/dashboard_score.py <hub_clone> <round> [<round> ...] [--dashboard <predevals_checkout>] [--eval-set "Last 4 weeks"] [--models <id> ...] [--cells <out.csv>]

Exit status 0, 1 when --dashboard finds a difference, 2 on a bad call.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TARGET = "wk inc flu hosp"
BASELINE = "FluSight-baseline"
MODELS = ("NAU_PyBNF-OracleSIHRS", "NAU_PyBNF-GroundHogCGR", "FluSight-ensemble", BASELINE)
KEY = ["round", "location", "horizon", "target_end_date"]
HORIZONS = (0, 1, 2, 3)
LEVELS = {"national": "US national level", "state": "state level"}
TOLERANCE = 1e-9


def truth(hub: Path) -> pd.DataFrame:
    """The hub's oracle output for the target: one value per (location,
    target_end_date)."""
    o = pd.read_csv(hub / "target-data" / "oracle-output.csv", dtype={"location": str, "output_type_id": str})
    o = o[o["target"] == TARGET]
    o = o.groupby(["location", "target_end_date"])["oracle_value"].first().rename("y").reset_index()
    o["location"] = norm_location(o["location"])
    return o


def norm_location(s: pd.Series) -> pd.Series:
    s = s.astype(str)
    return s.where(s == "US", s.str.zfill(2))


def read_file(path: Path) -> pd.DataFrame | None:
    """One model-output file as text columns; None for a parquet file when
    pyarrow is missing."""
    if path.suffix == ".parquet":
        try:
            d = pd.read_parquet(path)
        except ImportError:
            return None
    else:
        d = pd.read_csv(path, dtype={"location": str, "output_type_id": str})
    d["location"] = norm_location(d["location"])
    d["output_type_id"] = d["output_type_id"].astype(str)
    for c in ("reference_date", "target_end_date"):
        d[c] = d[c].astype(str).str[:10]
    return d


def score(q: np.ndarray, y: np.ndarray, levels: np.ndarray) -> dict[str, np.ndarray]:
    """Per forecast (rows of q, levels ascending): WIS and its split.
    The interval k = (l, u) adds (l - y)+ to overprediction and (y - u)+ to
    underprediction at weight 1, the median half of its miss; both divided
    by K + 0.5 (K pairs); spread is the rest of the WIS."""
    yy = y[:, None]
    pin = np.where(yy >= q, levels * (yy - q), (1 - levels) * (q - yy))
    wis = 2 * pin.mean(axis=1)
    m = q[:, np.argmin(np.abs(levels - 0.5))]
    denom = (len(levels) - 1) / 2 + 0.5
    over = ((np.clip(q - yy, 0, None) * (levels < 0.5)).sum(axis=1) + 0.5 * np.clip(m - y, 0, None)) / denom
    under = ((np.clip(yy - q, 0, None) * (levels > 0.5)).sum(axis=1) + 0.5 * np.clip(y - m, 0, None)) / denom
    return {"wis": wis, "over": over, "under": under, "spread": wis - over - under}


def score_files(hub: Path, rounds: list[str], out=None) -> pd.DataFrame:
    """Every forecast of every model's file of the given rounds, with the
    truth: one row per (model, round, location, horizon, target_end_date)."""
    out = out or sys.stderr
    y = truth(hub)
    rows, skipped = [], []
    for r in rounds:
        for path in sorted((hub / "model-output").glob(f"*/{r}-*")):
            d = read_file(path)
            if d is None:
                skipped.append(path.name)
                continue
            d = d[(d["target"] == TARGET) & (d["output_type"] == "quantile")]
            d = d[pd.to_numeric(d["horizon"], errors="coerce").isin(HORIZONS)]
            if d.empty:
                continue
            d = d.assign(level=d["output_type_id"].astype(float), value=d["value"].astype(float),
                         horizon=pd.to_numeric(d["horizon"]).astype(int))
            w = d.pivot_table(index=["reference_date", "location", "horizon", "target_end_date"],
                              columns="level", values="value", aggfunc="first").reset_index()
            w = w.merge(y, on=["location", "target_end_date"])
            levels = np.array(sorted(c for c in w.columns if isinstance(c, float)))
            qv, yv = w[list(levels)].to_numpy(float), w["y"].to_numpy(float)
            ok = np.isfinite(qv).all(axis=1) & np.isfinite(yv)
            w, qv, yv = w[ok], qv[ok], yv[ok]
            if not len(w):
                continue
            nat = score(qv, yv, levels)
            log = score(np.log(np.clip(qv, 0, None) + 1), np.log(yv + 1), levels)
            lo50, hi50, lo95, hi95 = (qv[:, np.argmin(np.abs(levels - x))] for x in (0.25, 0.75, 0.025, 0.975))
            rows.append(pd.DataFrame({
                "model": path.parent.name, "round": r, "location": w["location"].to_numpy(),
                "horizon": w["horizon"].to_numpy(), "target_end_date": w["target_end_date"].to_numpy(),
                "y": yv, "median": qv[:, np.argmin(np.abs(levels - 0.5))],
                **nat, "wis_log": log["wis"],
                "c50": (yv >= lo50) & (yv <= hi50), "c95": (yv >= lo95) & (yv <= hi95)}))
    if skipped:
        print(f"skipped (no pyarrow; the scores will not match the dashboard): {', '.join(skipped)}", file=out)
    if not rows:
        return pd.DataFrame(columns=["model", *KEY, "y", "median", "wis", "over", "under", "spread", "wis_log", "c50", "c95"])
    return pd.concat(rows, ignore_index=True)


def relative_skill(cells: pd.DataFrame, metric: str = "wis", baseline: str = BASELINE) -> pd.Series:
    """scoringutils' pairwise relative skill, scaled to the baseline."""
    w = cells.pivot_table(index=KEY, columns="model", values=metric, aggfunc="first")
    made = w.notna().to_numpy()
    x = np.nan_to_num(w.to_numpy())
    sums = x.T @ made.astype(float)          # [i, j]: i's scores summed on the forecasts i and j both made
    n = made.T.astype(float) @ made          # [i, j]: forecasts both made
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = (sums / n) / (sums.T / n)
        lr = np.log(ratio)
    lr[(n == 0) | ~np.isfinite(lr)] = np.nan
    np.fill_diagonal(lr, 0.0)
    theta = pd.Series(np.exp(np.nanmean(lr, axis=1)), index=w.columns)
    if baseline not in theta.index:
        raise ValueError(f"{baseline} has no scored forecast in this set")
    return theta / theta[baseline]


def season_start(rounds: list[str]) -> str:
    """August 1 of the season holding the latest round."""
    last = max(rounds)
    y, m = int(last[:4]), int(last[5:7])
    return f"{y if m >= 8 else y - 1}-08-01"


def table(cells: pd.DataFrame, start: str) -> pd.DataFrame:
    """Every model: relative WIS (natural, log), placement among the models
    with a forecast since `start`, coverage and forecasts scored; and the
    error split over this season's forecasts."""
    g = cells.groupby("model")
    t = pd.DataFrame({"rel": relative_skill(cells, "wis"), "rel_log": relative_skill(cells, "wis_log"),
                      "c50": g["c50"].mean(), "c95": g["c95"].mean(), "n": g.size()})
    season = cells[cells["round"] >= start]
    t = t[t.index.isin(set(season["model"]))].copy()
    t["place"] = t["rel"].rank(method="min").astype(int)
    t["place_log"] = t["rel_log"].rank(method="min").astype(int)
    split = season.groupby("model")[["spread", "under", "over", "wis"]].mean()
    return t.join(split).sort_values("rel")


def check_dashboard(cells: pd.DataFrame, dash: Path, eval_set: str, level: str, out=None) -> bool:
    """Our relative WIS against the dashboard's for every model of one eval
    set; True when every model matches on both scales."""
    out = out or sys.stdout
    path = dash / "scores" / TARGET / f"{eval_set}, {LEVELS[level]}" / "scores.csv"
    if not path.exists():
        print(f"   dashboard: no {path}", file=out)
        return False
    d = pd.read_csv(path).set_index("model_id")
    ours = pd.DataFrame({"rel": relative_skill(cells, "wis"), "rel_log": relative_skill(cells, "wis_log")})
    j = ours.join(d[["wis_scaled_relative_skill", "wis_scaled_relative_skill__log"]], how="outer")
    gap = max((j["rel"] - j["wis_scaled_relative_skill"]).abs().max(),
              (j["rel_log"] - j["wis_scaled_relative_skill__log"]).abs().max())
    missing = sorted(set(d.index) ^ set(ours.index))
    ok = not missing and bool(gap <= TOLERANCE)
    print(f"   dashboard '{eval_set}, {LEVELS[level]}': {len(d)} models, largest difference {gap:.1e}"
          + (f"; in one set only: {', '.join(missing)}" if missing else "") + (" MATCH" if ok else " DIFFERENT"), file=out)
    return ok


def report(cells: pd.DataFrame, models: list[str], start: str, out=None) -> dict[str, pd.DataFrame]:
    out = out or sys.stdout
    tables = {}
    for level, sel in (("national", cells["location"] == "US"), ("state", cells["location"] != "US")):
        sub = cells[sel]
        if sub.empty or BASELINE not in set(sub["model"]):
            print(f"== {level}: nothing to score", file=out)
            continue
        t = table(sub, start)
        tables[level] = t
        rounds = ", ".join(sorted(sub["round"].unique()))
        print(f"== {level}: {len(t)} models with forecasts since {start}; rounds {rounds}", file=out)
        print(f"   {'model':<28}{'relWIS':>8}{'place':>9}{'log':>8}{'place':>9}{'cov50':>7}{'cov95':>7}{'n':>6}"
              f"{'spread':>9}{'below':>8}{'above':>8}{'WIS':>9}", file=out)
        for m in models:
            if m not in t.index:
                print(f"   {m:<28}  no forecast in this set", file=out)
                continue
            r = t.loc[m]
            print(f"   {m:<28}{r.rel:>8.3f}{f'{int(r.place)}/{len(t)}':>9}{r.rel_log:>8.3f}{f'{int(r.place_log)}/{len(t)}':>9}"
                  f"{r.c50:>7.2f}{r.c95:>7.2f}{int(r.n):>6}{r.spread:>9.2f}{r.under:>8.2f}{r.over:>8.2f}{r.wis:>9.2f}", file=out)
    print("   spread, below and above: mean WIS per forecast of this season's rounds, split into interval "
          "width and the penalties for truth below or above the intervals", file=out)
    return tables


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], usage=__doc__.split("Usage:\n")[1].split("\n")[0].strip())
    ap.add_argument("hub", type=Path, help="a FluSight hub clone with model-output/ and target-data/oracle-output.csv")
    ap.add_argument("rounds", nargs="+", help="round ids (reference dates), as the eval set holds them")
    ap.add_argument("--dashboard", type=Path, help="a checkout of the dashboard's predevals/data branch, to compare with")
    ap.add_argument("--eval-set", default="Last 4 weeks", help="the dashboard's eval set name, without the level (default 'Last 4 weeks')")
    ap.add_argument("--models", nargs="+", default=list(MODELS), help="models to print (default our two, the ensemble and the baseline)")
    ap.add_argument("--cells", type=Path, help="write every scored forecast to this CSV")
    a = ap.parse_args(argv)
    if not (a.hub / "target-data" / "oracle-output.csv").exists() or not (a.hub / "model-output").is_dir():
        print(f"not a hub clone with model-output/ and target-data/oracle-output.csv: {a.hub}", file=sys.stderr)
        return 2
    cells = score_files(a.hub, sorted(a.rounds))
    if cells.empty:
        print("no forecast of these rounds could be scored yet", file=sys.stderr)
        return 2
    if a.cells:
        cells.to_csv(a.cells, index=False)
    report(cells, a.models, season_start(a.rounds))
    if a.dashboard:
        ok = [check_dashboard(cells[sel], a.dashboard, a.eval_set, level)
              for level, sel in (("national", cells["location"] == "US"), ("state", cells["location"] != "US"))]
        if not all(ok):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
