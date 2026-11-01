"""An experiment's summary.json (app/core/experiments.py summarise,
write_summary, read_summary, score, stale, figures): sums over the cells
both sides scored, each grouping adding up to overall, US apart and
compared like for like, ratios equal to scoring.pooled_metrics, the
horizons a week's sidecar is read in, the fits with no forecast, one
truth hashed before it is read, the shipped tree never written, and each
reason a summary is scored again.

The cells, the stored weeks, the shipped replays and the hub's truth are
synthetic (the FluSight baseline faked); one optional test rescores the
shipped 2024-25 replay against the hub clone FLUBNF_TEST_HUB names.
"""
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np                                       # noqa: E402
import pandas as pd                                      # noqa: E402
import pytest                                            # noqa: E402

from app.core import experiments as X                    # noqa: E402
from app.core import library as L                        # noqa: E402
from app.core import retro                               # noqa: E402
from app.core import retro_store as RS                   # noqa: E402
from app.core import scoring                             # noqa: E402
from app.core.engines import pf as PF                    # noqa: E402
from app.core.problem_codes import Refusal               # noqa: E402
from app.ui.retro_seasons import RETRO_ROOT              # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL    # noqa: E402
from flubnf.vintages import sha256_of                    # noqa: E402

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


# ------------------------------------------------ scoring a folder (score)

#: the locations the hub's truth covers, and their FIPS codes
FIPS = {"Alaska": "02", "California": "06", "New York": "36", "Texas": "48",
        "Vermont": "50", "US": "US"}
#: an experiment's locations here (US apart)
AT = ["Alaska", "Texas", "Vermont"]
WEEKS3 = WEEKS + ["2025-01-25"]
#: the engine build an experiment's run record names
BUILD = {"branch": "feature/particle-filter", "commit": "2fdadee0",
         "dirty": False, "source": "git"}
SHIPPED = {**X.SHIPPED_SETTINGS, "season": "2024-25"}
#: when the synthetic shipped replay started
S1, S2 = 1_790_000_000.0, 1_790_400_000.0


def _q(scale: float, locs=AT, horizons=("0", "1", "2", "3")) -> dict:
    """{location: {"0".."3": {level: value}}} at every FluSight level:
    the median scale times the location's place plus one."""
    return {loc: {h: {float(lv): scale * (i + 1) * (0.5 + lv) for lv in QL}
                  for h in horizons}
            for i, loc in enumerate(locs)}


def _hub(tmp_path, monkeypatch, weeks=WEEKS3, fips=FIPS) -> Path:
    """A hub holding only the target file: truth for each location and
    each of the four weeks after every as-of. The FluSight baseline is
    faked (100 a cell, 1 on the log scale). The target file's path."""
    hub = tmp_path / "hub"
    target = hub / "target-data" / "target-hospital-admissions.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    dates = sorted({str((pd.Timestamp(w) + pd.Timedelta(days=7 * (h + 1)))
                        .date()) for w in weeks for h in range(4)})
    rows = ["date,location,value"] + [
        f"{d},{f},{9.0 * (i + 1)}" for d in dates
        for i, f in enumerate(fips.values())]
    target.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    monkeypatch.setattr(scoring, "HUB", hub)
    monkeypatch.setattr(scoring, "_baseline_cells", lambda a, fs, t: {
        (f, a, h): 100.0 for f in fs for h in range(4)})
    monkeypatch.setattr(scoring, "_baseline_log_cells", lambda a, fs, t: {
        (f, a, h): 1.0 for f in fs for h in range(4)})
    monkeypatch.setattr(scoring, "TRUTH_SOURCE", scoring.TRUTH_SOURCE)
    return target


def _oracle(null=None, us=None, applied=True) -> dict:
    """oracle.json as the Oracle step writes it: the Liu-West filter's
    quantiles (quantiles.null) when given, and the US cell's state when
    given ("outside": the filter alone; "stepped")."""
    out = {"applied": applied}
    if null:
        out["quantiles"] = {"levels": list(QL), "null": {
            loc: {h: {"unrounded": [q[float(lv)] for lv in QL]}
                  for h, q in by_h.items()}
            for loc, by_h in null.items()}}
    if us:
        out["locations"] = {"US": {"fips": "US", "state": us}}
    return out


def _store(root: Path, asof: str, members: dict | None, oracle=None) -> Path:
    """A stored week: oracle.json when given, the samples file, then the
    quantile sidecar of `members` (so it is current); its folder."""
    wd = root / "weeks" / asof
    wd.mkdir(parents=True, exist_ok=True)
    if oracle is not None:
        (wd / RS.ORACLE_NAME).write_text(json.dumps(oracle), encoding="utf-8",
                                         newline="\n")
    (wd / RS.SAMPLES_JSON).write_text("{}", encoding="utf-8", newline="\n")
    if members is not None:
        RS.write_week_quantiles(wd, members)
    return wd


def _age(*roots, by: float = 5_000.0) -> None:
    """Every file under the roots `by` seconds old, so a summary written
    now is newer than all of them."""
    t = time.time() - by
    for r in roots:
        for p in Path(r).rglob("*"):
            if p.is_file():
                os.utime(p, (t, t))


def _experiment(own: dict, *, oracle=False, locations=AT, replicates=1,
                us=None) -> Path:
    """An experiment's folder as a finished replay leaves it: its
    experiment.json (beta2@3, 2024-25, smoke), the run record, and each
    week of `own` ({asof: pf quantiles}; None for a week not stored)
    stored with oracle.json naming the US state `us` when given."""
    s = {"model": "beta2@3", "season": "2024-25", "oracle": oracle}
    folder = X.root() / X.experiment_id(s)
    folder.mkdir(parents=True)
    L.write_json(folder / X.SETTINGS, json.loads(X.settings_text(s)))
    now = time.time()
    retro.write_meta(folder, {
        "status": "done", "started_utc": now - 3_000.0,
        "finished_utc": now - 1_000.0, "elapsed_s": 12.5,
        "settings": {"experiment": "e" * 64, "model_fingerprint": "m" * 64,
                     "model": "beta2@3", "weeks": list(own),
                     "locations": list(locations), "replicates": replicates,
                     "particles": 10_000, "engine_build": dict(BUILD)}})
    for w, q in own.items():
        if q is not None:
            _store(folder, w, {"pf": q},
                   oracle=_oracle(us=us) if us else None)
    return folder


def _shipped_root(rr: Path, *, pf=None, null=None, us=None,
                  started=S1, name="2024-25", **settings) -> Path:
    """A shipped replay's root: its run record, and per week the sidecar's
    pf (`pf`, {asof: quantiles}) and oracle.json with the Liu-West
    filter's quantiles (`null`) and the US state (`us`)."""
    root = rr / name
    retro.write_meta(root, {"started_utc": started,
                            "settings": {**SHIPPED, **settings}})
    for w in sorted(set(pf or {}) | set(null or {})):
        o = (_oracle((null or {}).get(w), us)
             if (null or {}).get(w) or us else None)
        _store(root, w, {"pf": pf[w]} if (pf or {}).get(w) else {}, oracle=o)
    return root


def _snapshot(root: Path) -> dict:
    """Every path under a tree: (size, mtime_ns), folders included."""
    return {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(Path(root).rglob("*"))}


def test_score_writes_every_key_of_the_format(sandbox_root, tmp_path,
                                              monkeypatch):
    target = _hub(tmp_path, monkeypatch)
    rr = tmp_path / "retro"
    _shipped_root(rr, null={w: _q(12.0) for w in WEEKS})
    folder = _experiment({w: _q(10.0) for w in WEEKS})
    got = X.score(folder, retro_root=rr, flubnf_build="53f1acf")
    obj = json.loads((folder / X.SUMMARY).read_text(encoding="utf-8"))
    assert obj == got
    assert set(obj) == {"format_version", "complete", "id", "experiment",
                        "model", "model_fingerprint", "season", "size",
                        "oracle", "ran", "shipped", "scored", "cells",
                        "overall", "by_location", "by_week", "by_horizon",
                        "us", "failures"}
    assert set(obj["ran"]) == {"locations", "weeks", "replicates",
                               "particles", "failed_fits", "seconds",
                               "started_utc", "finished_utc", "disk_bytes",
                               "engine_build", "flubnf_build"}
    assert set(obj["shipped"]) == {"member", "root", "started_utc",
                                   "replicates", "particles", "engine_build"}
    assert set(obj["scored"]) == {"utc", "truth", "truth_sha256", "scores_v"}
    assert obj["format_version"] == 1 and obj["id"] == folder.name
    assert (obj["complete"], obj["experiment"], obj["model_fingerprint"]) == (
        True, "e" * 64, "m" * 64)
    assert (obj["model"], obj["season"], obj["size"], obj["oracle"]) == (
        "beta2@3", "2024-25", "smoke", False)
    ran = obj["ran"]
    assert (ran["locations"], ran["weeks"], ran["replicates"],
            ran["particles"], ran["failed_fits"]) == (AT, WEEKS, 1, 10_000, 0)
    assert ran["seconds"] == 12.5 and ran["disk_bytes"] > 0
    assert ran["engine_build"] == BUILD and ran["flubnf_build"] == "53f1acf"
    assert ran["started_utc"] < ran["finished_utc"]
    assert ran["finished_utc"].endswith("Z")
    shipped = obj["shipped"]
    assert isinstance(shipped["root"], str)
    assert shipped == {"member": "pf_filter", "root": str(rr / "2024-25"),
                       "started_utc": X._utc(S1), "replicates": 3,
                       "particles": 10_000, "engine_build": {}}
    assert obj["scored"]["scores_v"] == retro.SCORES_V
    assert obj["scored"]["truth"] == "settled"
    assert obj["scored"]["truth_sha256"] == sha256_of(target)
    assert obj["cells"] == {"compared": 3 * 2 * 4, "model_only": 0,
                            "shipped_only": 0}
    assert obj["us"] is None and obj["failures"] == []
    assert X.read_summary(folder / X.SUMMARY) == obj


def _scored_frame(by_week: dict) -> pd.DataFrame:
    """Each week's quantiles scored as score does, asof added."""
    truth, n2f = scoring.load_truth()
    return pd.concat([scoring.score_quantiles(q, w, n2f, truth).assign(asof=w)
                      for w, q in by_week.items()], ignore_index=True)


def test_the_scored_sums_equal_pooled_metrics_on_the_compared_cells(
        sandbox_root, tmp_path, monkeypatch):
    _hub(tmp_path, monkeypatch)
    mq = {WEEKS[0]: _q(10.0),
          WEEKS[1]: {k: v for k, v in _q(10.0).items() if k != "Texas"}}
    sq = {w: _q(12.0) for w in WEEKS}
    del sq[WEEKS[0]]["Alaska"]["3"]                   # one shipped cell
    rr = tmp_path / "retro"
    _shipped_root(rr, pf=sq)
    folder = _experiment(mq, oracle=True)
    got = X.score(folder, retro_root=rr)
    assert got["shipped"]["member"] == "pf"
    assert got["cells"] == {"compared": 24 - 4 - 1, "model_only": 1,
                            "shipped_only": 4}
    m, s = _scored_frame(mq), _scored_frame(sq)
    keys = (set(zip(m.fips, m["asof"], m.horizon))
            & set(zip(s.fips, s["asof"], s.horizon)))

    def compared(df):
        return df[[k in keys for k in zip(df.fips, df["asof"], df.horizon)]]
    m, s = compared(m), compared(s)
    for group, pick in ((got["overall"], lambda df: df),
                        (got["by_location"]["Alaska"],
                         lambda df: df[df.location == "Alaska"])):
        fig = X.figures(group)
        for side, df in (("model", pick(m)), ("shipped", pick(s))):
            want = scoring.pooled_metrics(df)
            assert fig["n"] == want["n"]
            assert _close(fig[side]["rel"], want["rel"])
            assert _close(fig[side]["log_rel"], want["log_rel"])
            for band in ("50", "80", "95"):
                assert _close(fig[side]["cov"][band], want["cov"][band])
        assert _close(fig["vs_shipped"]["wis"],
                      pick(m).wis.sum() / pick(s).wis.sum())
        assert _close(fig["vs_shipped"]["log_wis"],
                      pick(m).log_wis.sum() / pick(s).log_wis.sum())
    assert X.figures(got["overall"])["n"] == 19


def test_figures_follows_pooled_metrics_edge_cases():
    side = {"wis": 50.0, "log_wis": 2.0, "cov50": 1, "cov80": 2, "cov95": 3}
    g = {"n": 4, "base_wis": 100.0, "base_log_wis": 4.0, "model": side,
         "shipped": {**side, "wis": 25.0}}
    assert X.figures(g) == {
        "n": 4,
        "model": {"rel": 0.5, "log_rel": 0.5,
                  "cov": {"50": 0.25, "80": 0.5, "95": 0.75}},
        "shipped": {"rel": 0.25, "log_rel": 0.5,
                    "cov": {"50": 0.25, "80": 0.5, "95": 0.75}},
        "vs_shipped": {"wis": 2.0, "log_wis": 1.0}}
    assert X.figures(None) is None
    # no shipped side
    f = X.figures({k: v for k, v in g.items() if k != "shipped"})
    assert f["shipped"] is None and f["vs_shipped"] is None
    assert f["model"]["rel"] == 0.5
    # the shipped side's sum of 0 under vs shipped
    assert X.figures({**g, "shipped": {**side, "wis": 0.0}})[
        "vs_shipped"]["wis"] is None
    # each edge case as pooled_metrics meets it on the same cells
    empty = pd.DataFrame(columns=["location", "fips", "asof", "horizon",
                                  *METRICS, "base_wis", "base_log_wis"])
    cases = {"n is 0": empty}
    zero = _cells(LOCS[:3])
    zero["base_wis"] = 0.0
    cases["base_wis is 0"] = zero
    nolog = _cells(LOCS[:3])
    nolog.loc[3, "log_wis"] = np.nan
    cases["a log sum is None"] = nolog
    noband = _cells(LOCS[:3])
    noband.loc[5, "cov80"] = np.nan
    cases["a band is None"] = noband
    for why, df in cases.items():
        fig = X.figures(X.summarise(df, None)["overall"])
        want = scoring.pooled_metrics(df)
        assert fig["n"] == want["n"], why
        assert fig["shipped"] is None and fig["vs_shipped"] is None, why
        for k in ("rel", "log_rel"):
            assert (fig["model"][k] is None) == (want[k] is None), (why, k)
            if want[k] is not None:
                assert _close(fig["model"][k], want[k]), (why, k)
        assert (fig["model"]["cov"] is None) == (want["cov"] is None), why
    assert X.figures(X.summarise(empty, None)["overall"])["model"] == {
        "rel": None, "log_rel": None, "cov": None}
    assert X.figures(X.summarise(nolog, None)["overall"])["model"][
        "rel"] is not None


def test_the_shipped_tree_is_never_written(sandbox_root, tmp_path,
                                           monkeypatch):
    _hub(tmp_path, monkeypatch)
    rr = tmp_path / "retro"
    a, b, c = WEEKS3
    root = _shipped_root(rr, pf={a: _q(12.0), b: _q(12.0)},
                         null={a: _q(11.0), b: _q(11.0)})
    # b: a sidecar older than its samples (never rebuilt here)
    t = time.time()
    os.utime(root / "weeks" / b / RS.QUANTILES_NAME, (t - 600, t - 600))
    os.utime(root / "weeks" / b / RS.SAMPLES_JSON, (t - 60, t - 60))
    # c: a week the step did not run (oracle.json says so), its sidecar
    # current: a pf, and no Liu-West filter alone
    _store(root, c, {"pf": _q(12.0)}, oracle=_oracle(applied=False))
    real = RS.week_member_quantiles

    def spy(r, asof):
        assert Path(r) != root, "week_member_quantiles read the shipped tree"
        return real(r, asof)
    monkeypatch.setattr(RS, "week_member_quantiles", spy)
    before = _snapshot(root)
    on = X.score(_experiment({w: _q(10.0) for w in WEEKS3}, oracle=True),
                 retro_root=rr)
    off = X.score(_experiment({w: _q(10.0) for w in WEEKS3}), retro_root=rr)
    assert _snapshot(root) == before
    # the stale sidecar's week and the step-off week have no shipped cells
    assert on["cells"] == {"compared": 24, "model_only": 12, "shipped_only": 0}
    assert off["cells"] == {"compared": 24, "model_only": 12,
                            "shipped_only": 0}
    assert sorted(on["by_week"]) == [a, c] and sorted(off["by_week"]) == [a, b]


def test_a_stored_week_without_a_pf_member_scores_nothing_for_it(
        sandbox_root, tmp_path, monkeypatch):
    _hub(tmp_path, monkeypatch)
    folder = _experiment({WEEKS[0]: _q(10.0), WEEKS[1]: None})
    _store(folder, WEEKS[1], {"analogue": _q(9.0)})   # no pf stored there
    got = X.score(folder, retro_root=tmp_path / "none")
    assert got["complete"] is True
    assert sorted(got["by_week"]) == [WEEKS[0]]
    assert got["cells"]["compared"] == 12


def test_no_reference_gives_a_model_only_summary(sandbox_root, tmp_path,
                                                 monkeypatch):
    _hub(tmp_path, monkeypatch)
    folder = _experiment({w: _q(10.0) for w in WEEKS})
    got = X.score(folder, retro_root=tmp_path / "retro")
    assert got["shipped"] is None
    assert got["cells"] == {"compared": 24, "model_only": 0,
                            "shipped_only": 0}
    groups = ([got["overall"]] + list(got["by_location"].values())
              + list(got["by_week"].values())
              + list(got["by_horizon"].values()))
    assert all("shipped" not in g for g in groups)
    assert X.figures(got["overall"])["vs_shipped"] is None


def test_us_is_compared_only_like_for_like(sandbox_root, tmp_path,
                                           monkeypatch):
    _hub(tmp_path, monkeypatch)
    locs = AT + ["US"]
    rr = tmp_path / "retro"
    folder = _experiment({w: _q(10.0, locs) for w in WEEKS}, oracle=True,
                         locations=locs, us="stepped")
    for us, compared in (("outside", False), (None, False),
                         ("stepped", True)):
        shutil.rmtree(rr, ignore_errors=True)
        _shipped_root(rr, pf={w: _q(12.0, locs) for w in WEEKS}, us=us)
        got = X.score(folder, retro_root=rr)
        assert (got["us"] is not None) == compared, us
        assert got["overall"]["n"] == 24, us              # US stays apart
    assert got["us"]["n"] == 8 and "shipped" in got["us"]
    # the step off: the filter alone on both sides, US when its block has it
    folder = _experiment({w: _q(10.0, locs) for w in WEEKS}, locations=locs)
    for null_locs, compared in ((AT, False), (locs, True)):
        shutil.rmtree(rr, ignore_errors=True)
        _shipped_root(rr, null={w: _q(12.0, null_locs) for w in WEEKS})
        got = X.score(folder, retro_root=rr)
        assert (got["us"] is not None) == compared, null_locs


def test_failures_count_fits_with_no_forecast(tmp_path):
    folder = tmp_path / "exp"
    w1, w2, w3, w4 = "2024-12-28", "2025-01-11", "2025-01-25", "2025-02-08"
    locs = ["New York", "Texas", "Vermont"]
    folder.mkdir()
    (folder / "failures.log").write_text(
        f"{w1}: the first try\n"
        f"{w2}: all 9 PF fits failed (first: x); the week is not stored\n"
        f"{w1}: beta@1 is 11111111 now, and this experiment started with "
        f"22222222: {w1} is not fitted\n"
        "and a second line of it\n", encoding="utf-8", newline="\n")
    # w2: stored, the model side read: New York with 2 failed markers,
    # Texas absent and prepare-failed (and a marker), Vermont absent
    wd = _store(folder, w2, None)
    for key, st in (("New_York_r0", "FAIL: boom"), ("New_York_r1", "ok"),
                    ("New_York_r2", "FAIL: bang"), ("Texas_r1", "FAIL: late")):
        retro.mark_cell_done(wd, key, st)
    (wd / PF.PREPARE_FAILURES_NAME).write_text(json.dumps(
        {"Texas": "FAIL: prepare: no data"}), encoding="utf-8", newline="\n")
    # w3: stored, the model side unreadable
    wd = _store(folder, w3, None)
    retro.mark_cell_done(wd, "New_York_r0", "FAIL: x")
    (wd / PF.PREPARE_FAILURES_NAME).write_text(json.dumps(
        {"Vermont": "FAIL: prepare: y"}), encoding="utf-8", newline="\n")
    own = {w1: None, w2: {"New York": {}}, w3: None, w4: None}
    n, entries = X._failures(folder, [w1, w2, w3, w4], locs, 3, own)
    assert n == 9 + (2 + 3 + 3) + (1 + 3)
    assert entries == [
        {"week": w1, "text": f"beta@1 is 11111111 now, and this experiment "
                             f"started with 22222222: {w1} is not fitted\n"
                             "and a second line of it"},
        {"week": w2, "location": "New York", "replicate": 0,
         "text": "FAIL: boom"},
        {"week": w2, "location": "New York", "replicate": 2,
         "text": "FAIL: bang"},
        {"week": w2, "location": "Texas", "text": "FAIL: prepare: no data"},
        {"week": w2, "location": "Texas", "replicate": 1,
         "text": "FAIL: late"},
        {"week": w2, "location": "Vermont",
         "text": "no forecast stored for this location"},
        {"week": w3, "location": "New York", "replicate": 0,
         "text": "FAIL: x"},
        {"week": w3, "location": "Vermont", "text": "FAIL: prepare: y"}]
    # the caps: 100 entries, 200 characters each; the count is whole
    many = tmp_path / "many"
    wd = _store(many, w2, None)
    for r in range(150):
        retro.mark_cell_done(wd, f"New_York_r{r}", "x" * 300)
    n, entries = X._failures(many, [w2], locs[:1], 1, {w2: {"New York": {}}})
    assert n == 150 and len(entries) == 100
    assert [e["replicate"] for e in entries] == list(range(100))
    assert {len(e["text"]) for e in entries} == {200}


def test_truth_file_is_the_one_load_truth_reads(tmp_path, monkeypatch):
    from app.core import data as core_data
    target = _hub(tmp_path, monkeypatch)
    path, source, sha = X._truth()
    scoring.load_truth()
    assert (path, source, sha) == (target, "settled", sha256_of(target))
    assert scoring.TRUTH_SOURCE == source
    vintage = tmp_path / "vintage.csv"
    vintage.write_text(target.read_text(encoding="utf-8"), encoding="utf-8",
                       newline="\n")
    target.unlink()
    monkeypatch.setattr(core_data, "vintages",
                        lambda: ["2025-01-04", "2025-01-11"])
    monkeypatch.setattr(core_data, "vintage_path",
                        lambda d: vintage if d == "2025-01-11" else None)
    path, source, sha = X._truth()
    scoring.load_truth()
    assert (path, source, sha) == (vintage, "vintage 2025-01-11",
                                   sha256_of(vintage))
    assert scoring.TRUTH_SOURCE == source
    monkeypatch.setattr(core_data, "vintages", lambda: [])
    with pytest.raises(FileNotFoundError, match="no settled truth"):
        X._truth()


def test_truth_is_hashed_before_it_is_read(sandbox_root, tmp_path,
                                           monkeypatch):
    target = _hub(tmp_path, monkeypatch)
    folder = _experiment({w: _q(10.0) for w in WEEKS})
    _age(folder)
    before = sha256_of(target)
    real = scoring.load_truth

    def replaced():                 # the hub updated between hash and read
        target.write_text(target.read_text(encoding="utf-8")
                          + "2025-03-01,02,1.0\n", encoding="utf-8",
                          newline="\n")
        return real()
    monkeypatch.setattr(scoring, "load_truth", replaced)
    got = X.score(folder, retro_root=tmp_path / "none")
    monkeypatch.setattr(scoring, "load_truth", real)
    assert got["scored"]["truth_sha256"] == before != sha256_of(target)
    assert X.stale(folder) == "the truth data changed"


def test_stale_names_each_reason(sandbox_root, tmp_path, monkeypatch):
    target = _hub(tmp_path, monkeypatch)
    rr = tmp_path / "retro"
    root = _shipped_root(rr, null={w: _q(12.0) for w in WEEKS})
    folder = _experiment({w: _q(10.0) for w in WEEKS})
    summary = folder / X.SUMMARY
    _age(folder, root)

    def again():
        X.score(folder, retro_root=rr)
        assert X.stale(folder) == ""
    meta = retro.read_meta(folder)
    # 1: a replay under way, whichever process: never scored meanwhile
    retro.write_meta(folder, {**meta, "status": "running",
                              "heartbeat_utc": time.time(),
                              "pid": os.getpid()})
    assert X.stale(folder) == ""
    retro.write_meta(folder, meta)
    # 3: not scored yet
    assert X.stale(folder) == "not scored yet"
    again()
    # 2: no week stored (another experiment, started, nothing stored)
    other = _experiment({}, oracle=True)
    assert X.stale(other) == ""
    # 4: a newer format: left alone
    obj = json.loads(summary.read_text(encoding="utf-8"))
    L.write_json(summary, {**obj, "format_version": 2})
    newer = summary.read_bytes()
    assert X.stale(folder) == ""
    with pytest.raises(Refusal) as e:          # and never overwritten
        X.score(folder, retro_root=rr)
    assert e.value.code == "FORMAT_UNKNOWN" and summary.read_bytes() == newer
    # 5: unreadable
    for text in ("{", "[]", json.dumps({**obj, "format_version": "1"})):
        summary.write_text(text, encoding="utf-8", newline="\n")
        assert X.stale(folder) == "its summary cannot be read", text
    again()
    # 6: a segment ended after it was scored
    t = float(meta["finished_utc"]) - 10
    os.utime(summary, (t, t))
    assert X.stale(folder) == "a segment ended after it was scored"
    again()
    # 7: weeks stored since
    samples = folder / "weeks" / WEEKS[1] / RS.SAMPLES_JSON
    t = time.time() + 100
    os.utime(samples, (t, t))
    assert X.stale(folder) == "weeks were stored since it was scored"
    _age(folder)
    again()
    # 8: another scoring rule
    obj = json.loads(summary.read_text(encoding="utf-8"))
    L.write_json(summary, {**obj, "scored": {**obj["scored"], "scores_v": 1}})
    assert X.stale(folder) == "the scoring rule changed"
    again()
    # 9: the truth data changed
    target.write_text(target.read_text(encoding="utf-8")
                      + "2025-03-01,02,1.0\n", encoding="utf-8", newline="\n")
    assert X.stale(folder) == "the truth data changed"
    again()
    # 10: the shipped replay compared with moved
    shipped_meta = retro.read_meta(root)
    retro.write_meta(root, {**shipped_meta, "started_utc": S2})
    assert X.stale(folder) == "the shipped replay it was compared with moved"
    retro.write_meta(root, shipped_meta)
    assert X.stale(folder) == ""
    # 11: the shipped replay stored weeks since
    os.utime(root / "weeks" / WEEKS[0] / RS.SAMPLES_JSON, (t, t))
    assert X.stale(folder) == "the shipped replay stored weeks since"
    _age(root)
    assert X.stale(folder) == ""
    # 9 again: no truth file here at all skips the truth test
    from app.core import data
    target.unlink()
    monkeypatch.setattr(data, "vintages", lambda: [])
    assert X.stale(folder) == ""


def test_a_root_in_the_repository_is_recorded_relative(sandbox_root,
                                                       tmp_path, monkeypatch):
    # as on a console, whose replays sit under the checkout: the summary
    # names the root from it, in forward slashes, and stale() reads it
    # from the checkout wherever the console was started
    from app.core import sandbox as sb
    _hub(tmp_path, monkeypatch)
    monkeypatch.setattr(sb, "REPO", tmp_path)
    rr = tmp_path / "retro"
    _shipped_root(rr, null={w: _q(12.0) for w in WEEKS})
    folder = _experiment({w: _q(10.0) for w in WEEKS})
    _age(folder, rr)
    got = X.score(folder, retro_root=rr)
    assert got["shipped"]["root"] == "retro/2024-25"
    assert X.stale(folder) == ""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert X.stale(folder) == ""
    shipped_meta = retro.read_meta(rr / "2024-25")
    retro.write_meta(rr / "2024-25", {**shipped_meta, "started_utc": S2})
    assert X.stale(folder) == "the shipped replay it was compared with moved"


def test_the_reference_is_the_replay_first_compared(sandbox_root, tmp_path,
                                                    monkeypatch):
    _hub(tmp_path, monkeypatch)
    rr = tmp_path / "retro"
    _shipped_root(rr, null={w: _q(12.0) for w in WEEKS})
    folder = _experiment({w: _q(10.0) for w in WEEKS})
    first = X.score(folder, retro_root=rr)
    assert (first["shipped"]["root"], first["shipped"]["started_utc"]) == (
        str(rr / "2024-25"), X._utc(S1))
    archived = retro.archive_run(rr, "2024-25")
    # a new live replay, partly stored, on the shipped settings
    _shipped_root(rr, null={WEEKS[0]: _q(30.0)}, started=S2)
    assert X.stale(folder) == "the shipped replay it was compared with moved"
    kept = X.score(folder, retro_root=rr)
    assert (kept["shipped"]["root"], kept["shipped"]["started_utc"]) == (
        str(archived), X._utc(S1))
    assert kept["overall"] == first["overall"]
    retro.delete_tree(archived)
    assert X.stale(folder) == "the shipped replay it was compared with moved"
    now = X.score(folder, retro_root=rr)
    assert (now["shipped"]["root"], now["shipped"]["started_utc"]) == (
        str(rr / "2024-25"), X._utc(S2))
    assert now["cells"]["compared"] == 12


def test_a_rescore_keeps_the_build_that_ran(sandbox_root, tmp_path,
                                            monkeypatch):
    _hub(tmp_path, monkeypatch)
    folder = _experiment({w: _q(10.0) for w in WEEKS})
    none = tmp_path / "none"
    assert X.score(folder, retro_root=none)["ran"]["flubnf_build"] == ""
    assert X.score(folder, retro_root=none,
                   flubnf_build="53f1acf")["ran"]["flubnf_build"] == "53f1acf"
    assert X.score(folder, retro_root=none)["ran"]["flubnf_build"] == "53f1acf"
    assert X.score(folder, retro_root=none,
                   flubnf_build="0e9e90b")["ran"]["flubnf_build"] == "0e9e90b"
