"""Submission files against the FluSight hub's own rules (app/core/hubcheck.py).

The hub validates a pull request with hubValidations (R) reading
hub-config/tasks.json. Here the same checks run in Python from a byte copy
of that file (app/core/assets/flusight-tasks.json), so CI checks every
file the writer produces for the first 2026-27 round (due Wednesday
2026-10-07, reference date Saturday 2026-10-10) without a hub clone.

With a clone present (FLUBNF_TEST_HUB, else FLUBNF_HUB), the vendored copy
must equal the clone's tasks.json, and a real console run (the Groundhog
for real, the PF cells faked the way the other run tests fake them) is
checked against the clone's rules.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import hubcheck as HC                        # noqa: E402
from app.core import submit as SB                          # noqa: E402

ASOF = "2026-10-03"          # the data week the 2026-10-07 release ends on
REF = "2026-10-10"           # the Saturday after the Wednesday due date
PKG_LOCS = Path(__file__).resolve().parents[2] / "flubnf/data/locations.csv"


def _hub_clone():
    for cand in (os.environ.get("FLUBNF_TEST_HUB"),
                 os.environ.get("FLUBNF_HUB")):
        if cand and (Path(cand) / "hub-config" / "tasks.json").is_file():
            return Path(cand)
    return None


HUB = _hub_clone()
needs_hub = pytest.mark.skipif(HUB is None, reason="no FluSight hub clone")


def _locations():
    return pd.read_csv(PKG_LOCS, dtype=str)


# ------------------------------------------------ the vendored rules

def test_the_vendored_rules_are_the_2026_27_hub_facts():
    """What the writer relies on, pinned from the vendored tasks.json."""
    r = HC.vendored_rules()
    assert REF in r["rounds"] and "2027-05-29" in r["rounds"]
    assert r["window"] == (-6, -3)                 # Sunday to Wednesday
    assert HC.submission_window(REF) == (
        pd.Timestamp("2026-10-04").date(), pd.Timestamp("2026-10-07").date())
    hosp = [t for t in r["tasks"] if t["target"] == "wk inc flu hosp"]
    assert len(hosp) == 1
    (t,) = hosp
    assert t["task_ids"]["horizon"] == ["-1", "0", "1", "2", "3"]
    assert set(t["task_ids"]["location"]) == set(_locations().location)
    assert len(t["task_ids"]["location"]) == 53
    q = t["output_types"]["quantile"]
    assert q["is_required"] and q["minimum"] == 0
    # the 23 levels, as text exactly as the writer prints them
    assert q["required_ids"] == [str(x) for x in SB.QUANTILES]
    assert {x["target"] for x in r["tasks"]} == {
        "wk inc flu hosp", "wk flu hosp rate change",
        "peak inc flu hosp", "peak week inc flu hosp",
        "wk inc flu prop ed visits"}


@needs_hub
def test_the_vendored_tasks_json_is_the_hubs():
    ours = HC.VENDORED_TASKS.read_bytes()
    theirs = (HUB / "hub-config" / "tasks.json").read_bytes()
    assert hashlib.sha256(ours).hexdigest() == \
        hashlib.sha256(theirs).hexdigest(), (
        "hub-config/tasks.json changed upstream: copy it to "
        "app/core/assets/flusight-tasks.json and rerun this suite")


# ------------------------------------------------ the files the writer makes

def _samples(y: float, rng) -> dict:
    """PF-shaped canonical samples around a last observation `y`."""
    d = {"origin": list(y * np.exp(rng.normal(0, .05, 2000)))}
    for h in range(4):
        d[str(h)] = list(y * np.exp(rng.normal(.08 * (h + 1),
                                               .25 * np.sqrt(h + 1), 2000)))
    return d


def _build(tmp_path):
    """Both files for REF, every location, from both row builders: a range
    of sizes including the dead cells a summer vintage holds (0) and the
    national count."""
    from app.core.floor import floor_quantiles, floor_samples
    rng = np.random.default_rng(3)
    locs = _locations()
    sizes = [0, 0, 1, 3, 12, 40, 150, 900]
    pf_rows, an_rows = [], []
    for i, fips in enumerate(locs.location):
        y = 9000.0 if fips == "US" else float(sizes[i % len(sizes)])
        s = floor_samples(_samples(y, rng), fips, ASOF)
        pf_rows += SB.quantile_rows(s, fips, ASOF)
        q = {str(h): {float(L): (y + 1) * (0.5 + L) * (1 + .2 * h)
                      for L in SB.QUANTILES} for h in range(4)}
        an_rows += SB.rows_from_quantiles(floor_quantiles(q), fips, ASOF)
    return (SB.write_submission(pf_rows, "pf", ASOF, tmp_path),
            SB.write_submission(an_rows, "analogue", ASOF, tmp_path))


def _assert_all_pass(path, rules=None, populations=None):
    res = HC.check_file(path, rules=rules, populations=populations)
    failed = {k: v for k, v in res.items() if v}
    assert not failed, f"{path.name}: {failed}"
    return res


def test_the_first_round_files_pass_every_hub_check(tmp_path):
    for p in _build(tmp_path):
        assert p.name == f"{REF}-{p.parent.name}.csv"
        assert p.parent.name in (SB.hub_model_id("pf"),
                                 SB.hub_model_id("analogue"))
        _assert_all_pass(p)
        d = pd.read_csv(p, dtype=str, keep_default_na=False)
        assert list(d.columns) == list(HC.COLUMNS)
        assert set(d.reference_date) == {REF}
        assert d.location.nunique() == 53
        assert sorted(set(d.horizon)) == ["0", "1", "2", "3"]
        assert sorted(set(d.target_end_date)) == [
            "2026-10-10", "2026-10-17", "2026-10-24", "2026-10-31"]
        assert len(d) == 53 * 4 * 23
        assert d.value.str.fullmatch(r"\d+").all()      # whole, non-negative


@needs_hub
def test_the_first_round_files_pass_the_clones_rules(tmp_path):
    rules = HC.rules_from_tasks(HC.load_tasks(
        HUB / "hub-config" / "tasks.json"))
    pops = dict(zip(*pd.read_csv(HUB / "auxiliary-data" / "locations.csv",
                                 dtype=str)[["location", "population"]]
                    .T.values))
    pops = {k: float(v) for k, v in pops.items()}
    for p in _build(tmp_path):
        _assert_all_pass(p, rules=rules, populations=pops)


# ------------------------------------------------ the checker catches defects

@pytest.fixture(scope="module")
def good(tmp_path_factory):
    p, _ = _build(tmp_path_factory.mktemp("good"))
    return p, HC.read_text_frame(p)


def _run(p, d, name=None, dirname=None):
    return HC.check_frame(d, name or p.name, dirname or p.parent.name)


@pytest.mark.parametrize("check, mutate", [
    ("values_valid", lambda d: d.assign(location=d.location.str.lstrip("0"))),
    ("values_valid", lambda d: d.assign(target="wk inc flu hospitalizations")),
    ("values_valid", lambda d: d.assign(output_type_id=d.output_type_id
                                        .replace("0.1", "0.10"))),
    ("values_valid", lambda d: d.assign(horizon=d.horizon.replace("3", "4"))),
    ("value_integer", lambda d: d.assign(value=d.value + ".5")),
    ("value_col_valid", lambda d: d.assign(value="-" + d.value)),
    ("value_col_valid", lambda d: d.assign(value=d.value.where(
        d.index != 5, "NA"))),
    ("ascending", lambda d: d.assign(value=d.value.where(
        d.index != 0, "999999"))),
    ("values_required", lambda d: d[d.output_type_id != "0.975"]),
    ("rows_unique", lambda d: pd.concat([d, d.head(3)])),
    ("horizon_timediff", lambda d: d.assign(target_end_date=d
                                            .target_end_date.where(
        d.horizon != "2", "2026-10-31"))),
    ("match_round_id", lambda d: d.assign(reference_date=d.reference_date
                                          .where(d.index != 0,
                                                 "2026-10-17"))),
    ("colnames", lambda d: d.assign(model_id="x")),
    ("colnames", lambda d: d.drop(columns=["target_end_date"])),
    ("col_types", lambda d: d.assign(horizon=d.horizon + ".0")),
    ("counts_lt_popn", lambda d: d.assign(value=d.value.where(
        d.location != "56", "99999999"))),
])
def test_the_checker_catches(good, check, mutate):
    p, d = good
    assert not HC.failures(_run(p, d), allow_round=False)
    res = _run(p, mutate(d.copy()).reset_index(drop=True))
    assert res[check], f"{check} missed: {res}"


def test_the_checker_reads_the_name_and_the_folder(good):
    p, d = good
    assert _run(p, d, name="2026-10-10-NAU-PyBNF-OracleSIHRS.csv")["file_name"]
    assert _run(p, d, name="2026-10-10-NAU_PyBNF-OracleSIHRSxxxxxxx.csv"
                )["file_name"]                    # a model_abbr over 16
    assert _run(p, d, dirname="NAU_PyBNF-GroundHogCGR")["file_location"]
    off = HC.check_frame(d.assign(reference_date="2026-07-11"),
                         "2026-07-11-NAU_PyBNF-OracleSIHRS.csv",
                         "NAU_PyBNF-OracleSIHRS")
    assert off[HC.ROUND_CHECK]                    # the summer: not a round
    assert not [f for f in HC.failures(off) if "values_valid" in f]


def test_the_writer_refuses_what_the_hub_would_reject(tmp_path):
    """The gate runs on the written bytes: a location code the hub does
    not know never reaches its file name."""
    rows = SB.quantile_rows({"0": list(np.linspace(5, 50, 200))}, "6", ASOF)
    with pytest.raises(ValueError, match="hub's checks"):
        SB.write_submission(rows, "pf", ASOF, tmp_path)
    assert not list(tmp_path.rglob("*.csv"))
    assert not list(tmp_path.rglob("*.tmp"))


def test_an_off_season_replay_is_written_as_a_record(tmp_path):
    """A summer as-of is a correct file whose date is not a round: written
    (the run's record), and the Output page says it is not a round."""
    from app.ui.routes.output import _hub_status
    rows = SB.quantile_rows({str(h): list(np.linspace(5, 50, 200))
                             for h in range(4)}, "06", "2026-07-04")
    p = SB.write_submission(rows, "pf", "2026-07-04", tmp_path)
    st = _hub_status(str(p))
    assert st["ok"] and "not a FluSight round" in st["text"]


def test_the_output_page_names_the_due_date(tmp_path):
    import datetime as dt
    from app.ui.routes.output import _hub_status
    p, _ = _build(tmp_path)
    assert _hub_status(str(p), dt.date(2026, 10, 6))["text"] == (
        "Passes the hub's checks. Due Wed 2026-10-07, 11 PM ET.")
    assert "closed" in _hub_status(str(p), dt.date(2026, 10, 8))["text"]


# ------------------------------------------------ a real console run

def _vintage_for(asof: str, tmp: Path) -> Path:
    """The clone's vintage for `asof`, or (before the season's first
    release lands) the newest real vintage with the weeks after it copied
    from the same weeks a year earlier (+364 days, same weekday)."""
    arch = HUB / "auxiliary-data" / "target-data-archive"
    name = f"target-hospital-admissions_{asof}.csv"
    out = tmp / "archive"
    out.mkdir()
    if (arch / name).is_file():
        (out / name).write_bytes((arch / name).read_bytes())
        return out
    newest = sorted(arch.glob("target-hospital-admissions_*.csv"))[-1]
    v = pd.read_csv(newest, dtype={"location": str})
    v["date"] = pd.to_datetime(v["date"])
    last, end, yr = v.date.max(), pd.Timestamp(asof), pd.Timedelta(days=364)
    fill = v[(v.date > last - yr) & (v.date <= end - yr)].copy()
    fill["date"] += yr
    full = pd.concat([v, fill]).sort_values(["date", "location"])
    full["date"] = full["date"].dt.strftime("%Y-%m-%d")
    full.to_csv(out / name, index=False)
    return out


@needs_hub
def test_a_real_console_run_writes_files_the_hub_accepts(tmp_path,
                                                         monkeypatch):
    """pipeline._run_all for as-of 2026-10-03 on every location: the
    Groundhog (with its shipped donors) and the output floor run for real
    on the clone's data; the PF cells are faked; both files pass every
    check against the clone's tasks.json and locations."""
    import app.core.data as core_data
    import app.core.engines.analogue as an_engine
    import app.core.engines.pf as pf_engine
    import app.core.oracle as oracle_mod
    import app.core.runs as runs_mod
    import app.core.scoring as scoring_mod
    import flubnf.settings as fs
    from app.core.runs import Ledger, RunSpec
    from app.ui import pipeline as P
    from app.ui import versions as V
    from app.ui.routes import forecast as F

    arch = _vintage_for(ASOF, tmp_path)
    locs_csv = HUB / "auxiliary-data" / "locations.csv"
    monkeypatch.setattr(core_data, "ARCHIVE", arch)
    monkeypatch.setattr(fs, "LOCATIONS", locs_csv)
    monkeypatch.setattr(an_engine, "LOCATIONS", locs_csv)
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path / "state")
    locs = pd.read_csv(locs_csv, dtype=str)
    names = list(locs.location_name)
    vint = pd.read_csv(arch / f"target-hospital-admissions_{ASOF}.csv",
                       dtype={"location": str})
    last = {n: float(vint[vint.location.str.zfill(2) == f].sort_values(
        "date").value.dropna().iloc[-1])
        for n, f in zip(locs.location_name, locs.location.str.zfill(2))}
    rng = np.random.default_rng(11)

    def _prepare(spec, w):
        (Path(w) / "cells.json").write_text("[]")
        return []
    monkeypatch.setattr(P, "_pf_engine_state", lambda: "ready")
    monkeypatch.setattr(pf_engine, "prepare", _prepare)
    monkeypatch.setattr(pf_engine, "execute",
                        lambda w: {f"{n}_r0": "ok" for n in names})
    monkeypatch.setattr(pf_engine, "collect",
                        lambda w: {n: _samples(last[n], rng) for n in names})
    monkeypatch.setattr(oracle_mod, "apply_week",
                        lambda s, asof, wd, **kw: (s, {"applied": True,
                                                       "bank": {"label": "stub"}}))

    def _no_truth():
        raise RuntimeError("no truth for a future week")
    monkeypatch.setattr(scoring_mod, "load_truth", _no_truth)
    monkeypatch.setattr(P, "_sleep_guard", lambda: None)
    monkeypatch.setattr(P, "_harvest_params", lambda w: {})
    monkeypatch.setattr(P, "_write_weekly_report", lambda *a, **k: None)
    monkeypatch.setattr(V, "_engine_versions_for_ledger", lambda e: {})

    P._run_all(RunSpec(engine="all", forecast_date=ASOF, locations=names,
                       replicates=1, extra=F._run_extra(2, "realtime", None)))
    row = next(iter(Ledger().rows(1)))
    outcome = json.loads(row.get("outcome") or "{}")
    assert not outcome.get("submission_errors"), outcome
    subs = outcome["submissions"]
    assert set(subs) == {SB.hub_model_id("pf"), SB.hub_model_id("analogue")}
    rules = HC.rules_from_tasks(HC.load_tasks(
        HUB / "hub-config" / "tasks.json"))
    pops = {l: float(p) for l, p in zip(locs.location, locs.population)}
    for model_id, path in subs.items():
        p = Path(path)
        assert p.name == f"{REF}-{model_id}.csv"
        _assert_all_pass(p, rules=rules, populations=pops)
        d = pd.read_csv(p, dtype=str)
        # the Groundhog skips a location whose last count is 0 (a ratio
        # of nothing); the hub takes any subset of locations
        want = 53 if model_id == SB.hub_model_id("pf") else \
            sum(1 for v in last.values() if v > 0)
        assert d.location.nunique() == want
