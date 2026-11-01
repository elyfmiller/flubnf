"""scripts/dashboard_score.py, the FluSight dashboard's scores reproduced from
the hub's files: WIS and its split per forecast, scoringutils' pairwise
relative skill scaled to the baseline, placements, and the check against the
dashboard's published scores."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flubnf.wis import log_wis, wis

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "dashboard_score.py"

LEVELS = [0.01, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5,
          0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.975, 0.99]


@pytest.fixture(scope="module")
def ds():
    spec = importlib.util.spec_from_file_location("dashboard_score", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def random_forecasts(n: int, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    med = rng.uniform(1, 500, n)
    spread = rng.uniform(0.05, 1.5, n)
    z = np.array([math.sqrt(2) * _erfinv(2 * q - 1) for q in LEVELS])
    q = med[:, None] * np.exp(spread[:, None] * z[None, :])
    y = med * np.exp(rng.normal(0, 1, n))
    return q, y


def _erfinv(x: float) -> float:
    # bisection on math.erf; enough for test quantile shapes
    lo, hi = -6.0, 6.0
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if math.erf(mid) < x else (lo, mid)
    return (lo + hi) / 2


def test_wis_matches_the_package(ds):
    q, y = random_forecasts(200)
    s = ds.score(q, y, np.array(LEVELS))
    want = [wis(dict(zip(LEVELS, row)), yy).wis for row, yy in zip(q, y)]
    assert np.allclose(s["wis"], want, rtol=1e-12, atol=1e-12)
    lg = ds.score(np.log(q + 1), np.log(y + 1), np.array(LEVELS))
    want_log = [log_wis(dict(zip(LEVELS, row)), yy) for row, yy in zip(q, y)]
    assert np.allclose(lg["wis"], want_log, rtol=1e-12, atol=1e-12)


def test_split_adds_up_and_points_the_right_way(ds):
    q, y = random_forecasts(200, seed=3)
    s = ds.score(q, y, np.array(LEVELS))
    assert np.allclose(s["spread"] + s["over"] + s["under"], s["wis"])
    assert (s["spread"] >= -1e-12).all()
    below_all = q[:, 0] - 1.0              # truth under every quantile: the forecast is too high
    t = ds.score(q, below_all, np.array(LEVELS))
    assert (t["under"] == 0).all() and (t["over"] > 0).all()
    above_all = q[:, -1] + 1.0
    t = ds.score(q, above_all, np.array(LEVELS))
    assert (t["over"] == 0).all() and (t["under"] > 0).all()
    at_median = q[:, LEVELS.index(0.5)]    # truth at the median: width only
    t = ds.score(q, at_median, np.array(LEVELS))
    assert np.allclose(t["over"] + t["under"], 0) and np.allclose(t["spread"], t["wis"])


def cells_frame(scores: dict[str, list[float]]) -> pd.DataFrame:
    """Forecast i of model m scores scores[m][i] (NaN: not made)."""
    rows = []
    for m, v in scores.items():
        for i, x in enumerate(v):
            if not math.isnan(x):
                rows.append({"model": m, "round": "2026-10-10", "location": f"{i:02d}", "horizon": 0,
                             "target_end_date": "2026-10-10", "wis": x})
    return pd.DataFrame(rows)


def test_relative_skill_full_overlap_is_the_mean_ratio(ds):
    c = cells_frame({"A": [1, 1, 1, 1], "B": [2, 2, 2, 2], "FluSight-baseline": [4, 4, 4, 4]})
    r = ds.relative_skill(c)
    assert r["A"] == pytest.approx(0.25) and r["B"] == pytest.approx(0.5) and r["FluSight-baseline"] == 1


def test_relative_skill_uses_only_shared_forecasts(ds):
    nan = float("nan")
    # C made only the first two forecasts, A none of those: the A-C pair has
    # nothing in common and drops out of both geometric means
    c = cells_frame({"A": [nan, nan, 1, 3], "C": [2, 6, nan, nan], "FluSight-baseline": [4, 4, 4, 4]})
    r = ds.relative_skill(c)
    theta_a = math.exp((math.log(1.0) + math.log(2 / 4)) / 2)      # self, baseline (on forecasts 3-4)
    theta_c = math.exp((math.log(1.0) + math.log(4 / 4)) / 2)
    theta_b = math.exp((math.log(1.0) + math.log(4 / 2) + math.log(4 / 4)) / 3)
    assert r["A"] == pytest.approx(theta_a / theta_b)
    assert r["C"] == pytest.approx(theta_c / theta_b)


def write_hub(root: Path) -> Path:
    """A two-round hub: US and two states, three models; the baseline is
    wide, the ensemble sharp, ours in between."""
    hub = root / "hub"
    (hub / "target-data").mkdir(parents=True)
    truth = []
    for d, v in [("2026-10-10", 100), ("2026-10-17", 120), ("2026-10-24", 150)]:
        for loc, f in [("US", 10.0), ("01", 1.0), ("02", 0.5)]:
            truth.append(("wk inc flu hosp", d, loc, 0, "quantile", "", v * f))
    pd.DataFrame(truth, columns=["target", "target_end_date", "location", "horizon", "output_type",
                                 "output_type_id", "oracle_value"]).to_csv(hub / "target-data" / "oracle-output.csv", index=False)
    widths = {"FluSight-baseline": 0.8, "FluSight-ensemble": 0.15, "NAU_PyBNF-OracleSIHRS": 0.4}
    for model, wd in widths.items():
        (hub / "model-output" / model).mkdir(parents=True)
        for rd in ("2026-10-10", "2026-10-17"):
            rows = []
            for h in (0, 1):
                ted = str((pd.Timestamp(rd) + pd.Timedelta(weeks=h)).date())
                for loc, f in [("US", 10.0), ("01", 1.0), ("02", 0.5)]:
                    m = 110 * f
                    for q in LEVELS:
                        rows.append((rd, "wk inc flu hosp", h, ted, loc, "quantile", str(q),
                                     m * math.exp(wd * math.sqrt(2) * _erfinv(2 * q - 1))))
            pd.DataFrame(rows, columns=["reference_date", "target", "horizon", "target_end_date", "location",
                                        "output_type", "output_type_id", "value"]
                         ).to_csv(hub / "model-output" / model / f"{rd}-{model}.csv", index=False)
    return hub


def write_dashboard(root: Path, ds, cells: pd.DataFrame, nudge: float = 0.0) -> Path:
    dash = root / "dash"
    for level, sel in (("national", cells["location"] == "US"), ("state", cells["location"] != "US")):
        sub = cells[sel]
        rel, rel_log = ds.relative_skill(sub, "wis"), ds.relative_skill(sub, "wis_log")
        p = dash / "scores" / "wk inc flu hosp" / f"Last 4 weeks, {ds.LEVELS[level]}"
        p.mkdir(parents=True)
        pd.DataFrame({"model_id": rel.index, "wis_scaled_relative_skill": rel.values + nudge,
                      "wis_scaled_relative_skill__log": rel_log.reindex(rel.index).values}).to_csv(p / "scores.csv", index=False)
    return dash


def test_end_to_end_placements_and_the_dashboard_check(ds, tmp_path, capsys):
    hub = write_hub(tmp_path)
    cells = ds.score_files(hub, ["2026-10-10", "2026-10-17"])
    assert len(cells) == 3 * 2 * 2 * 3          # models x rounds x horizons x locations
    t = ds.table(cells[cells["location"] != "US"], "2026-08-01")
    assert list(t.index) == ["FluSight-ensemble", "NAU_PyBNF-OracleSIHRS", "FluSight-baseline"]
    assert list(t["place"]) == [1, 2, 3]
    dash = write_dashboard(tmp_path, ds, cells)
    assert ds.main([str(hub), "2026-10-10", "2026-10-17", "--dashboard", str(dash)]) == 0
    out = capsys.readouterr().out
    assert "1/3" in out and "MATCH" in out and "DIFFERENT" not in out


def test_dashboard_difference_fails(ds, tmp_path, capsys):
    hub = write_hub(tmp_path)
    cells = ds.score_files(hub, ["2026-10-10", "2026-10-17"])
    dash = write_dashboard(tmp_path, ds, cells, nudge=1e-6)
    assert ds.main([str(hub), "2026-10-10", "2026-10-17", "--dashboard", str(dash)]) == 1
    assert "DIFFERENT" in capsys.readouterr().out


def test_bad_call(ds, tmp_path):
    assert ds.main([str(tmp_path), "2026-10-10"]) == 2
