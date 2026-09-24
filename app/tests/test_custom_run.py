"""A console forecast on a custom dataset (app/core/custom_run.py).

The Groundhog runs for real on small fixtures; the particle filter is faked
at prepare/execute/collect (the test_oracle_step pattern: no engine in CI).
What is held: exports (hubverse, the dataset's own key column, non-hub
names, never under submission/), the count-only floor and rounding, the
in-house persistence baseline named everywhere, the national group beside
the pooled figure, and the run's research containment.
"""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.core import custom_run as CR
from app.core import datasets as D
from app.core import horizons as hz
from app.core import runs as R
from app.core import submit as SB
from app.core.runs import RunSpec

from test_dataset_engines import _saturdays, mh_bytes   # noqa: E402

FD = "2023-12-02"


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    return tmp_path / "datasets"


def spec_for(ds, engine="analogue", fd=FD, **kw):
    extra = {"dataset": ds.ref(), "oracle": "none",
             "dataset_final": not ds.vintage_true, **kw.pop("extra", {})}
    return RunSpec(engine=engine, forecast_date=fd,
                   locations=kw.pop("locations", ds.groups), extra=extra, **kw)


def hub_ts(groups=("01", "US"), names=("Alabama", "US"), rate=False) -> bytes:
    """A hubverse time series (no as_of) with a national row."""
    lines = ["target_end_date,location,location_name,observation,population"]
    for i, d in enumerate(_saturdays(date(2019, 8, 3), date(2024, 2, 24))):
        for j, (g, n) in enumerate(zip(groups, names)):
            v = (40 + 30 * np.sin(2 * np.pi * (i + 5 * j) / 52.0)) * (1 + 9 * j)
            v = round(v / 7.0, 3) if rate else round(v)
            lines.append(f"{d.isoformat()},{g},{n},{v},{1000000 * (1 + j)}")
    return ("\n".join(lines) + "\n").encode()


# ------------------------------------------------------------------ export

def test_microhub_export_is_keyed_by_target_group_and_valid(tmp_path):
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    q = {"0": {float(L): 10.0 + i for i, L in enumerate(SB.QUANTILES)}}
    rows = CR.export_rows({"Adult": q}, ds, FD, integer=True)
    df = pd.DataFrame(rows)
    assert list(df.columns) == ["reference_date", "target", "horizon",
                                "target_end_date", "target_group",
                                "output_type", "output_type_id", "value"]
    assert set(df.reference_date) == {"2023-12-09"}          # as-of + 7
    assert set(df.target_end_date) == {"2023-12-09"}         # horizon 0
    assert set(df.target) == {"custom"}
    assert SB.validate(df, key_col="target_group") == []
    p = CR.write_export(rows, "FluBNF-Groundhog", FD, tmp_path, "target_group")
    assert p == tmp_path / "export" / "FluBNF-Groundhog" / \
        "2023-12-09-FluBNF-Groundhog.csv"
    assert not (tmp_path / "submission").exists()
    assert open(p).readline().strip().split(",")[4] == "target_group"


def test_hubverse_export_keeps_the_uploaded_location_keys():
    ds = D.ingest(hub_ts(), "hub", kind="count")
    q = {h: {float(L): 5.0 + i for i, L in enumerate(SB.QUANTILES)}
         for h in hz.HORIZONS}
    rows = CR.export_rows({"US": q, "Alabama": q}, ds, FD, integer=True)
    assert {r["location"] for r in rows} == {"US", "01"}
    assert sorted({r["horizon"] for r in rows}) == [0, 1, 2, 3]


def test_validate_keeps_its_hub_default():
    df = pd.DataFrame(SB.rows_from_quantiles(
        {"0": {float(L): 1.0 + i for i, L in enumerate(SB.QUANTILES)}},
        "01", FD))
    assert SB.validate(df) == []
    with pytest.raises(KeyError):
        SB.validate(df.rename(columns={"location": "target_group"}))


def test_rates_keep_decimals_counts_are_whole():
    ds = D.ingest(hub_ts(rate=True), "r", kind="rate")
    q = {"0": {float(L): 1.2345678 + 0.01 * i
               for i, L in enumerate(SB.QUANTILES)}}
    v = [r["value"] for r in CR.export_rows({"Alabama": q}, ds, FD,
                                            integer=False)]
    assert v[0] == 1.234568 and all(isinstance(x, float) for x in v)
    w = [r["value"] for r in CR.export_rows({"Alabama": q}, ds, FD,
                                            integer=True)]
    assert all(isinstance(x, int) for x in w)


# ----------------------------------------------------------------- scoring

def test_score_uses_the_persistence_baseline_and_the_cell_rule():
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    truth = ds.truth()
    s = ds.series("Adult", FD)
    last = s["values"][-1]
    q = {h: {float(L): last * (0.5 + L) for L in SB.QUANTILES}
         for h in hz.HORIZONS}
    cells = CR.score({"Adult": q}, ds, FD, truth=truth)
    assert len(cells) == 4 and (cells.base_wis > 0).all()
    base = CR.baseline_quantiles(ds, "Adult", FD)
    from flubnf.wis import wis
    end = "2023-12-09"
    assert cells.iloc[0].base_wis == pytest.approx(
        wis(base["0"], truth[("Adult", end)]).wis)
    # a zero median is not scored (scoring.py's rule)
    z = {h: {float(L): 0.0 for L in SB.QUANTILES} for h in hz.HORIZONS}
    assert CR.score({"Adult": z}, ds, FD, truth=truth).empty


def test_a_flat_series_never_divides_by_a_zero_baseline():
    lines = ["date,target_group,value"] + [
        f"{d.isoformat()},Flat,5" for d in _saturdays(date(2023, 8, 5),
                                                      date(2024, 1, 27))]
    ds = D.ingest(("\n".join(lines) + "\n").encode(), "flat", kind="count")
    q = {h: {float(L): 5.0 for L in SB.QUANTILES} for h in hz.HORIZONS}
    assert CR.score({"Flat": q}, ds, "2023-12-02").empty


def test_the_national_group_is_scored_beside_never_inside():
    ds = D.ingest(hub_ts(), "hub", kind="count")
    assert ds.national_group == "US"
    q = {n: {h: {float(L): v * (0.6 + 0.8 * L) for L in SB.QUANTILES}
             for h in hz.HORIZONS}
         for n, v in (("US", ds.series("US", FD)["values"][-1]),
                      ("Alabama", ds.series("Alabama", FD)["values"][-1]))}
    cells = CR.score(q, ds, FD)
    s = CR.summarize(cells)
    al = cells[cells.location == "Alabama"]
    assert s["relwis"] == round(float(al.wis.sum() / al.base_wis.sum()), 3)
    assert s["cells"] == len(al)
    assert s["national"]["cells"] == int((cells.location == "US").sum())


# --------------------------------------------------------------------- run

def test_groundhog_run_writes_results_exports_and_scores(tmp_path):
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    w = tmp_path / "w"
    w.mkdir()
    outcome, fails = CR.run(spec_for(ds), ds, w)
    assert fails == {}
    res = json.loads((w / "results.json").read_text())
    assert res["research"] is True and res["oracle"] == "none"
    assert res["dataset"]["id"] == ds.id and res["baseline"] == CR.BASELINE
    assert set(hz.models_to_canonical(res["models"])["analogue"]) == set(ds.groups)
    assert list(outcome["exports"]) == ["FluBNF-Groundhog"]
    assert Path(outcome["exports"]["FluBNF-Groundhog"]).is_file()
    sc = outcome["custom_scores"]["analogue"]
    assert sc["cells"] > 0 and sc["relwis"] > 0
    assert outcome["archived"].startswith("skipped")
    assert not (w / "submission").exists() and not (w / "report.html").exists()
    # observed tail: as of the forecast date, never later weeks
    assert max(d for d, _ in res["observed"]["Adult"]) == FD


def test_thin_donor_pool_abstains_and_is_recorded(tmp_path):
    raw = mh_bytes(start=date(2023, 8, 5), end=date(2024, 2, 24))
    ds = D.ingest(raw, "one season", kind="count")
    outcome, _ = CR.run(spec_for(ds), ds, tmp_path)
    assert outcome["abstained"]["analogue"] == sorted(ds.groups)
    assert outcome["exports"] == {}


def test_rate_dataset_skips_the_count_floor(tmp_path, monkeypatch):
    import app.core.floor as floor_mod
    ds = D.ingest(mh_bytes(rate=True), "rates", kind="rate")
    monkeypatch.setattr(floor_mod, "floor_quantiles", lambda *a, **k: (
        _ for _ in ()).throw(AssertionError("floored a rate")))
    outcome, _ = CR.run(spec_for(ds), ds, tmp_path)
    p = outcome["exports"]["FluBNF-Groundhog"]
    vals = pd.read_csv(p).value
    assert (vals != vals.round()).any()                   # decimals kept


def _fake_pf(monkeypatch, names, seen=None):
    import app.core.engines.pf as PF
    rng = np.random.default_rng(3)
    samples = {n: {hz.ORIGIN: list(rng.poisson(30, 200).astype(float)),
                   **{h: list(rng.poisson(30 + 5 * int(h), 200).astype(float))
                      for h in hz.HORIZONS}} for n in names}

    def prepare(spec, w):
        if seen is not None:
            seen.append(spec)
        return []
    monkeypatch.setattr(PF, "prepare", prepare)
    monkeypatch.setattr(PF, "execute", lambda w: {f"{n}_r0": "ok" for n in names})
    monkeypatch.setattr(PF, "collect", lambda w: samples)


def test_pf_runs_plain_on_an_eligible_dataset(tmp_path, monkeypatch):
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    seen = []
    _fake_pf(monkeypatch, ds.groups, seen)
    outcome, fails = CR.run(spec_for(ds, engine="all"), ds, tmp_path,
                            pf_state="ready")
    assert seen and seen[0].extra["oracle"] == "none"
    assert set(outcome["exports"]) == {"FluBNF-Groundhog", "FluBNF-SIHRS-PF"}
    assert outcome["oracle"] == "none" and outcome["pf_cells"] == 3
    assert not (tmp_path / "oracle.json").exists()
    res = json.loads((tmp_path / "results.json").read_text())
    assert set(res["models"]) == {"pf", "analogue"}
    pf = pd.read_csv(outcome["exports"]["FluBNF-SIHRS-PF"])
    assert (pf.value == pf.value.round()).all()             # whole counts


def test_pf_is_skipped_without_a_population_or_engine(tmp_path, monkeypatch):
    ds = D.ingest(mh_bytes(pop=False), "nopop", kind="count")
    _fake_pf(monkeypatch, ds.groups)
    o, _ = CR.run(spec_for(ds, engine="all"), ds, tmp_path / "a",
                  pf_state="ready")
    assert "population" in o["pf_skipped"]
    assert list(o["exports"]) == ["FluBNF-Groundhog"]
    ds2 = D.ingest(mh_bytes(), "pop", kind="count")
    o2, _ = CR.run(spec_for(ds2, engine="all"), ds2, tmp_path / "b",
                   pf_state="absent")
    assert "not installed" in o2["pf_skipped"]


def test_modified_settings_export_under_a_suffixed_non_hub_name(tmp_path):
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    spec = spec_for(ds, extra={"knobs": {"groundhog.bandwidth": 3}})
    o, _ = CR.run(spec, ds, tmp_path)
    assert list(o["exports"]) == ["FluBNF-Groundhog-modified"]
    assert (tmp_path / "knobs.json").is_file()


# -------------------------------------------------- run records and labels

def test_a_dataset_run_is_research_and_described_as_one():
    ds_ref = {"id": "x-" + "0" * 12, "digest": "0" * 16, "name": "Kids"}
    spec = RunSpec(engine="all", forecast_date=FD, locations=["A", "B"],
                   extra={"dataset": ds_ref, "oracle": "none",
                          "dataset_final": True})
    assert R.is_research(spec) and R.is_contained(spec)
    got = dict(R.spec_settings(spec))
    assert got["data source"] == "Kids (your dataset; final data, not vintage-true)"
    assert got["groups"] == "2 groups: A, B"
    assert got["Oracle step"].startswith("off")
    assert "jurisdictions" not in json.dumps(got)
    html = R.results_html({"custom_scores": {"analogue": {
        "relwis": 0.9, "cells": 4, "national": {"relwis": 1.2, "cells": 2}}},
        "exports": {"FluBNF-Groundhog": "x"}}, spec)
    assert "in-house persistence baseline" in html
    assert "FluSight" not in html and "national group 1.200, beside" in html
    # the hub's own spec is unchanged
    hub = RunSpec(engine="all", forecast_date=FD, locations=["Ohio", "US"])
    assert not R.is_research(hub)
    assert "FluSight baseline" in R.results_html({"pf_relwis": 0.9}, hub)
