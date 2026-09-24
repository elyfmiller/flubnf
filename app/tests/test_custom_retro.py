"""Replaying a week range on a custom dataset (app/core/custom_retro.py).

The Groundhog runs for real; the particle filter is faked at
prepare/execute/collect. Held: what a replay stores and where (under the
dataset, never app/state/retro), the vintage-true vs final-data label, the
scorer shared with the console run, the national group beside the pooled
figure, weeks to drop, and stopping.
"""
from __future__ import annotations

import gzip
import json
from datetime import date

import pandas as pd
import pytest

from app.core import custom_retro as CX
from app.core import datasets as D
from app.core import horizons as hz

from test_custom_run import _fake_pf, hub_ts           # noqa: E402
from test_dataset_engines import mh_bytes              # noqa: E402

from pathlib import Path
TEMPLATE = (Path(__file__).resolve().parents[1] / "ui" / "static"
            / "microhub-template.csv")


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    return tmp_path / "datasets"


def _replay(ds, weeks, **kw):
    out = CX.replay_dir(ds, CX.new_stamp(ds))
    return out, CX.run(ds, weeks, ds.groups, out_dir=out, **kw)


def test_a_replay_stores_its_record_under_the_dataset():
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    weeks = CX.weeks_between(ds, "2023-10-07", "2023-12-30")
    assert weeks[0] == "2023-10-07" and len(weeks) == 13
    out, meta = _replay(ds, weeks)
    assert out.parent == ds.path / "replays"
    for f in ("forecasts.json.gz", "cells.csv.gz", "coverage.csv.gz",
              "run_meta.json"):
        assert (out / f).is_file(), f
    assert meta["status"] == "done" and meta["weeks_completed"] == 13
    assert meta["replay_kind"] == "final data, not vintage-true"
    assert meta["baseline"] == "in-house persistence baseline"
    s = meta["summary"]["analogue"]["pooled"]
    assert s["cells"] > 0 and 0 < s["relwis"] < 10
    assert {"cov50", "cov80", "cov95"} <= set(s)
    with gzip.open(out / "forecasts.json.gz", "rt") as f:
        fc = json.load(f)["forecasts"]
    assert sorted(fc) == weeks
    assert sorted(fc[weeks[0]]["analogue"]["Adult"]) == list(hz.HORIZONS)
    assert CX.list_replays(ds)[0][0] == out.name


def test_the_replay_scores_with_the_console_runs_scorer():
    from app.core import custom_run as CR
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    out, meta = _replay(ds, ["2023-12-02"])
    cells = pd.read_csv(out / "cells.csv.gz")
    with gzip.open(out / "forecasts.json.gz", "rt") as f:
        fc = json.load(f)["forecasts"]["2023-12-02"]["analogue"]
    q = {n: {h: {float(L): v for L, v in lv.items()} for h, lv in hq.items()}
         for n, hq in fc.items()}
    want = CR.score(q, ds, "2023-12-02")
    assert len(cells) == len(want)
    assert cells.wis.sum() == pytest.approx(want.wis.sum())


def test_a_versioned_dataset_replays_vintage_true():
    from datetime import timedelta
    w = [date(2025, 5, 3) + timedelta(days=7 * i) for i in range(8)]
    rows = []
    for k, asof in enumerate(w[3:], 3):
        for d in w[:k + 1]:
            rows.append(f"{asof},{d},01,Alabama,{10 + d.day}")
    raw = ("as_of,target_end_date,location,location_name,observation\n"
           + "\n".join(rows) + "\n").encode()
    ds = D.ingest(raw, "snap", kind="count")
    assert ds.vintage_true
    _out, meta = _replay(ds, ds.forecast_dates()[:2])
    assert meta["replay_kind"] == "vintage-true"


def test_the_national_group_is_summarised_beside():
    ds = D.ingest(hub_ts(), "hub", kind="count")
    weeks = CX.weeks_between(ds, "2023-10-07", "2024-01-27")
    _out, meta = _replay(ds, weeks)
    s = meta["summary"]["analogue"]
    assert s["national"] and s["national"]["cells"] > 0
    assert "US" in s["by_group"] and "US" not in (
        "".join(s["by_horizon"]))                       # by horizon: pooled
    cells = pd.read_csv(_out / "cells.csv.gz")
    al = cells[(cells.location == "Alabama")]
    assert s["pooled"]["relwis"] == pytest.approx(al.wis.sum()
                                                  / al.base_wis.sum())


def test_weeks_to_drop_is_recorded_and_moves_the_anchor():
    # MicroHub's own template (real, not periodic, data)
    ds = D.ingest(TEMPLATE, "template", kind="count")
    wk = "2024-03-02"
    _a, m0 = _replay(ds, [wk])
    b, m1 = _replay(ds, [wk], weeks_to_drop=2)
    assert m1["weeks_to_drop"] == 2
    with gzip.open(b / "forecasts.json.gz", "rt") as f:
        f1 = json.load(f)["forecasts"][wk]["analogue"]["Adult"]
    with gzip.open(_a / "forecasts.json.gz", "rt") as f:
        f0 = json.load(f)["forecasts"][wk]["analogue"]["Adult"]
    assert sorted(f1) == sorted(f0) and f1 != f0


def test_a_stop_file_ends_the_replay_between_weeks():
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    out = CX.replay_dir(ds, CX.new_stamp())
    out.mkdir(parents=True)
    (out / "STOP").touch()
    meta = CX.run(ds, ["2023-12-02", "2023-12-09"], ds.groups, out_dir=out,
                  stop_file=out / "STOP")
    assert meta["status"] == "stopped" and meta["weeks_completed"] == 0


def test_pf_replay_runs_plain_and_cleans_its_workroots(monkeypatch):
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    seen = []
    _fake_pf(monkeypatch, ds.groups, seen)
    out, meta = _replay(ds, ["2023-12-02", "2023-12-09"], engine="all",
                        pf_state="ready")
    assert len(seen) == 2 and all(s.extra["oracle"] == "none" for s in seen)
    assert seen[0].season_start == "2023-08-01"
    assert "pf" in meta["summary"] and meta["pf"].startswith("plain SIHRS")
    assert not (out / "work").exists()


def test_pf_replay_is_skipped_when_ineligible():
    ds = D.ingest(mh_bytes(pop=False), "nopop", kind="count")
    _out, meta = _replay(ds, ["2023-12-02"], engine="all", pf_state="ready")
    assert meta["pf"] is None and "population" in meta["pf_skipped"]
    assert set(meta["summary"]) == {"analogue"}


def test_stamps_are_path_safe():
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    for bad in ("../x", "2024", "20240101T000000Z/../../y", ""):
        with pytest.raises(ValueError):
            CX.replay_dir(ds, bad)
