"""An experiment's summary.json (app/core/experiments.py summarise,
write_summary, read_summary): sums over the cells both sides scored, each
grouping adding up to overall, US apart, ratios equal to
scoring.pooled_metrics, and the horizons a week's sidecar is read in.

The cells are synthetic; one optional test rescores the shipped 2024-25
replay against the hub clone FLUBNF_TEST_HUB names.
"""
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np                                       # noqa: E402
import pandas as pd                                      # noqa: E402
import pytest                                            # noqa: E402

from app.core import experiments as X                    # noqa: E402
from app.core import retro_store as RS                   # noqa: E402
from app.core import scoring                             # noqa: E402
from app.core.problem_codes import Refusal               # noqa: E402
from app.ui.retro_seasons import RETRO_ROOT              # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL    # noqa: E402

LOCS = [("Alaska", "02"), ("Texas", "48"), ("Vermont", "50"), ("US", "US")]
WEEKS = ["2024-12-28", "2025-01-11"]
METRICS = ("wis", "log_wis", "cov50", "cov80", "cov95")


def _cells(locs=LOCS, weeks=WEEKS, seed=1) -> pd.DataFrame:
    """Scored rows as score_quantiles gives them, with asof added."""
    rng = np.random.default_rng(seed)
    base = np.random.default_rng(0)            # one baseline for both sides
    rows = []
    for loc, fips in locs:
        for w in weeks:
            for h in range(4):
                rows.append({
                    "location": loc, "fips": fips, "asof": w, "horizon": h,
                    "wis": rng.uniform(1, 200), "log_wis": rng.uniform(0, 2),
                    **{c: int(rng.random() < p) for c, p in
                       (("cov50", .5), ("cov80", .8), ("cov95", .95))},
                    "base_wis": base.uniform(1, 200),
                    "base_log_wis": base.uniform(0, 2), "rel": 1.0})
    return pd.DataFrame(rows)


def _drop(df, **where) -> pd.DataFrame:
    hit = np.ones(len(df), bool)
    for k, v in where.items():
        hit &= (df[k] == v).to_numpy()
    return df[~hit].reset_index(drop=True)


def _close(a, b) -> bool:
    return a == b or math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


# ----------------------------------------------------------------- cells


def test_only_matched_cells_are_compared_and_counted():
    m = _drop(_cells(), location="Vermont", asof="2025-01-11")    # 4 cells
    s = _drop(_cells(seed=2), location="Texas", asof="2024-12-28", horizon=3)
    s = _drop(s, location="US", asof="2024-12-28", horizon=0)
    out = X.summarise(m, s)
    assert out["cells"] == {"compared": 3 * 2 * 4 - 5, "model_only": 1,
                            "shipped_only": 4}
    assert out["overall"]["n"] == 19
    assert out["us"]["n"] == 7                    # US: its own group only
    assert "US" not in out["by_location"]
    assert sorted(out["by_location"]) == ["Alaska", "Texas", "Vermont"]
    assert out["by_location"]["Vermont"]["n"] == 4
    assert sorted(out["by_horizon"]) == ["0", "1", "2", "3"]
    assert set(out) == {"cells", "overall", "by_location", "by_week",
                        "by_horizon", "us"}


def test_each_grouping_adds_up_to_overall():
    out = X.summarise(_cells(), _cells(seed=2))
    o = out["overall"]
    for name in ("by_location", "by_week", "by_horizon"):
        groups = out[name].values()
        assert sum(g["n"] for g in groups) == o["n"], name
        for k in ("base_wis", "base_log_wis"):
            assert _close(sum(g[k] for g in groups), o[k]), (name, k)
        for side in ("model", "shipped"):
            for k in METRICS:
                total = sum(g[side][k] for g in groups)
                assert _close(total, o[side][k]), (name, side, k)
                if k.startswith("cov"):
                    assert isinstance(o[side][k], int) and total == o[side][k]


def test_the_ratios_equal_pooled_metrics():
    m, s = _cells(), _cells(seed=2)
    out = X.summarise(m, s)
    for side, df in (("model", m), ("shipped", s)):
        df = df[df.fips != "US"]
        want = scoring.pooled_metrics(df)
        g = out["overall"]
        assert _close(g[side]["wis"] / g["base_wis"], want["rel"])
        assert _close(g[side]["log_wis"] / g["base_log_wis"], want["log_rel"])
        for label in ("50", "80", "95"):
            assert _close(g[side][f"cov{label}"] / g["n"], want["cov"][label])
        vt = df[df["location"] == "Vermont"]
        g = out["by_location"]["Vermont"]
        assert _close(g[side]["wis"] / g["base_wis"],
                      scoring.pooled_metrics(vt)["rel"])


def test_one_cell_without_a_log_value_nulls_its_groups_log_sums():
    m = _cells()
    hit = (m["location"] == "Texas") & (m["asof"] == WEEKS[0]) & (m["horizon"] == 2)
    m.loc[hit, "log_wis"] = np.nan
    m.loc[hit, "base_log_wis"] = np.nan
    out = X.summarise(m, _cells(seed=2))
    for g in (out["overall"], out["by_location"]["Texas"],
              out["by_week"][WEEKS[0]], out["by_horizon"]["2"]):
        assert g["model"]["log_wis"] is None and g["base_log_wis"] is None
        assert g["shipped"]["log_wis"] is not None
        assert g["model"]["wis"] is not None
    for g in (out["by_location"]["Alaska"], out["by_week"][WEEKS[1]],
              out["by_horizon"]["0"], out["us"]):
        assert g["model"]["log_wis"] is not None and g["base_log_wis"] is not None
    assert scoring.pooled_metrics(m[m.fips != "US"])["log_rel"] is None


def test_without_a_shipped_frame_the_models_own_cells_are_used():
    out = X.summarise(_cells(), None)
    assert out["cells"] == {"compared": 24, "model_only": 0, "shipped_only": 0}
    groups = ([out["overall"], out["us"]] + list(out["by_location"].values())
              + list(out["by_week"].values()) + list(out["by_horizon"].values()))
    assert all("shipped" not in g and set(g) == {"n", "base_wis",
                                                 "base_log_wis", "model"}
               for g in groups)


def test_no_us_cell_gives_us_null():
    out = X.summarise(_cells(LOCS[:3]), _cells(LOCS[:3], seed=2))
    assert out["us"] is None
    empty = X.summarise(pd.DataFrame(), None)
    assert empty["cells"]["compared"] == 0 and empty["overall"]["n"] == 0
    assert empty["by_location"] == {} and empty["us"] is None


# --------------------------------------------- the sidecar's horizons


def test_a_sidecar_stored_one_to_four_is_scored_as_hub_zero_to_three(
        tmp_path, monkeypatch):
    """quantiles.json keeps the filter's horizons "1".."4" (and "0", the
    origin): read_week_quantiles gives the hub's "0".."3", so the stored
    "1" is scored as horizon 0, one week past the as-of."""
    asof = "2025-01-11"
    wd = tmp_path / "weeks" / asof
    wd.mkdir(parents=True)
    (wd / RS.SAMPLES_JSON).write_text("{}", encoding="utf-8")
    flat = lambda v: {repr(float(L)): v for L in QL}          # noqa: E731
    (wd / RS.QUANTILES_NAME).write_text(json.dumps({"pf": {"Vermont": {
        "0": flat(1.0), "1": flat(10.0), "2": flat(20.0), "3": flat(30.0),
        "4": flat(40.0)}}}), encoding="utf-8")
    q = RS.read_week_quantiles(wd)["pf"]
    assert set(q["Vermont"]) == {"origin", "0", "1", "2", "3"}
    assert q["Vermont"]["0"][0.5] == 10.0
    monkeypatch.setattr(scoring, "_baseline_cells", lambda a, fips, t: {
        ("50", a, h): 5.0 for h in range(4)})
    monkeypatch.setattr(scoring, "_baseline_log_cells", lambda a, fips, t: {
        ("50", a, h): 0.5 for h in range(4)})
    t0 = pd.Timestamp(asof)
    truth = {("50", t0 + pd.Timedelta(days=7 * (h + 1))): 10.0 * (h + 1)
             for h in range(4)}
    df = scoring.score_quantiles(q, asof, {"Vermont": "50"}, truth)
    assert sorted(df["horizon"]) == [0, 1, 2, 3]
    assert (df["wis"] == 0).all()       # each stored "h+1" met its own week


# ---------------------------------------------------------------- the file


def _summary(locs, weeks, failures=()) -> dict:
    """A whole summary record as a writer states it."""
    m, s = _cells(locs, weeks), _cells(locs, weeks, seed=2)
    out = X.summarise(m, s)
    return {**out, "complete": True, "id": "beta2-v3_2024-25_full",
            "experiment": "e" * 64, "model": "beta2@3",
            "model_fingerprint": "m" * 64, "season": "2024-25",
            "size": "full", "oracle": False,
            "ran": {"locations": [n for n, _ in locs], "weeks": list(weeks),
                    "replicates": 3, "particles": 10_000,
                    "failed_fits": len(failures), "seconds": 28_000.5,
                    "started_utc": "2026-11-04T14:59:51Z",
                    "finished_utc": "2026-11-04T22:47:40Z",
                    "disk_bytes": 123_456_789,
                    "engine_build": {"branch": "feature/particle-filter",
                                     "commit": "2fdadee0", "dirty": False,
                                     "source": "git"},
                    "flubnf_build": "53f1acf"},
            "shipped": {"member": "pf_filter", "root": "app/state/retro/2024-25",
                        "started_utc": "2026-09-23T19:58:19Z",
                        "replicates": 3, "particles": 10_000,
                        "engine_build": {}},
            "scored": {"utc": "2026-11-04T22:48:00Z", "truth": "settled",
                       "truth_sha256": "6" * 64, "scores_v": 2},
            "failures": list(failures)}


def test_the_summary_is_written_in_the_house_style_and_read_back(tmp_path):
    summary = _summary(LOCS, WEEKS)
    p = X.write_summary(tmp_path, summary)
    assert p == tmp_path / X.SUMMARY
    raw = p.read_bytes()
    assert b"\r" not in raw
    obj = json.loads(raw)
    assert obj["format_version"] == 1
    assert raw.decode("utf-8") == json.dumps(obj, indent=1, sort_keys=True) + "\n"
    assert X.read_summary(p) == obj == {**summary, "format_version": 1}
    for v in (2, True, 1.0):                           # true == 1 in Python
        p.write_text(json.dumps(dict(obj, format_version=v)), encoding="utf-8")
        with pytest.raises(Refusal) as e:
            X.read_summary(p)
        assert e.value.code == "FORMAT_UNKNOWN"


def test_a_full_season_summary_stays_small(tmp_path):
    t = pd.read_csv(Path(__file__).resolve().parents[2]
                    / "flubnf/data/locations.csv", dtype=str)
    locs = [(n, f) for n, f, a in zip(t.location_name, t.location,
                                      t.abbreviation)
            if len(f) == 2 and a != "US"] + [("US", "US")]
    weeks = [str(d.date()) for d in pd.date_range("2024-11-16", periods=30,
                                                   freq="7D")]
    assert (len(locs), len(weeks)) == (53, 30)
    failures = [{"week": weeks[i], "location": "Vermont", "replicate": 0,
                 "text": "x" * 200} for i in range(5)]
    p = X.write_summary(tmp_path, _summary(locs, weeks, failures))
    assert p.stat().st_size < 64 * 1024


# ----------------------------------------- the shipped 2024-25 replay (optional)

#: the shipped 2024-25 replay, and the truth file the spec's figures used
SHIPPED_2024 = RETRO_ROOT / "2024-25"
TRUTH_SHA = "6240367f44caddcf49b942acd1c081d5eed930c6101a141054437efdf359dda1"
PILOT_WEEKS = ["2024-11-16", "2024-11-30", "2024-12-14", "2024-12-28",
               "2025-01-11", "2025-01-25", "2025-02-08", "2025-02-22",
               "2025-03-08", "2025-03-22", "2025-04-05", "2025-04-19",
               "2025-05-03", "2025-05-17"]


def test_the_shipped_filter_on_the_pilot_cells_gives_the_recorded_sums(
        monkeypatch):
    from flubnf import settings
    from flubnf.vintages import sha256_of
    hub = Path(os.environ.get("FLUBNF_TEST_HUB") or "/nonexistent")
    target = hub / "target-data" / "target-hospital-admissions.csv"
    if not ((SHIPPED_2024 / "run_meta.json").is_file() and target.is_file()):
        pytest.skip("needs the shipped 2024-25 replay and FLUBNF_TEST_HUB")
    if sha256_of(target) != TRUTH_SHA:
        pytest.skip("the hub's truth has moved since the figures were taken")
    monkeypatch.setattr(scoring, "HUB", hub)
    monkeypatch.setattr(settings, "HUB", hub)
    truth, n2f = scoring.load_truth()
    frames = []
    for w in PILOT_WEEKS:
        q = RS.filter_quantiles(SHIPPED_2024 / "weeks" / w) or {}
        df = scoring.score_quantiles(
            {k: v for k, v in q.items() if k in X.PILOT_LOCATIONS},
            w, n2f, truth)
        df["asof"] = w
        frames.append(df)
    shipped = pd.concat(frames, ignore_index=True)
    model = _drop(shipped, location="Vermont", asof="2025-04-05")
    out = X.summarise(model, shipped)
    assert out["cells"] == {"compared": 556, "model_only": 0,
                            "shipped_only": 4}

    def rounded(g):
        return (g["n"], round(g["base_wis"], 1), round(g["base_log_wis"], 2),
                round(g["shipped"]["wis"], 1), round(g["shipped"]["log_wis"], 2),
                g["shipped"]["cov50"], g["shipped"]["cov80"],
                g["shipped"]["cov95"])
    assert rounded(out["overall"]) == (556, 157229.3, 275.99, 131527.8,
                                       292.23, 196, 365, 481)
    assert rounded(out["by_horizon"]["3"]) == (139, 56757.9, 100.92, 46944.5,
                                               112.82, 34, 66, 108)
    assert rounded(out["by_location"]["Vermont"]) == (52, 812.0, 26.41, 851.8,
                                                      35.31, 20, 33, 46)
    assert rounded(out["by_week"]["2025-02-22"]) == (40, 14073.4, 15.71,
                                                     4586.9, 10.82, 31, 35, 37)
