"""The Oracle step on a sandbox run of the Oracle SIHRS start
(app/core/sandbox.py oracle_gate, oracle_step; POST
/sandbox/runs/<id>/oracle; the workbench's Oracle step card). The
production step (app/core/oracle.apply_week) runs for real on a tiny
synthetic hub, as test_oracle_step.py drives it; the filter's collect()
is faked. Everything it writes stays in the run folder.
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np                                       # noqa: E402
import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import data as data_mod                    # noqa: E402
from app.core import horizons as hz                      # noqa: E402
from app.core import oracle as oracle_mod                # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.ui import server as srv                         # noqa: E402
from app.ui import state as ui_state                     # noqa: E402
from flubnf import oracle as OR                          # noqa: E402

client = TestClient(srv.app)

ASOF = "2098-01-04"                                       # a Saturday
FIPS = {"Ohio": "39", "Utah": "49", "California": "06"}


def _saturdays(first: date, last: date) -> list:
    d = first + timedelta(days=(5 - first.weekday()) % 7)
    out = []
    while d <= last:
        out.append(d)
        d += timedelta(days=7)
    return out


@pytest.fixture
def hub(sandbox_root, tmp_path, monkeypatch):
    """A locations table and a vintage with two donor seasons, read by the
    shipped start (app.core.data) and by the Oracle step (app.core.oracle),
    plus a synthetic FluSurv-NET bank over the same seasons."""
    from flubnf import bank as BK
    from flubnf import oracle_mix as MX
    loc = tmp_path / "locations.csv"
    with open(loc, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["location", "abbreviation", "location_name", "population"])
        for name, f in FIPS.items():
            w.writerow([f, name[:2].upper(), name, 5_000_000])
        w.writerow(["US", "US", "US", 330_000_000])
    T = date.fromisoformat(ASOF)
    vf = tmp_path / f"target-hospital-admissions_{ASOF}.csv"
    weeks = _saturdays(date(2095, 8, 1), T)
    with open(vf, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["date", "location", "location_name", "value"])
        for i, d in enumerate(weeks):
            for j, (name, f) in enumerate(list(FIPS.items()) + [("US", "US")]):
                v = 80.0 + 50.0 * np.sin(2 * np.pi * (i + 6 * j) / 52.0) + 3 * j
                w.writerow([d.isoformat(), f, name, round(v, 3)])

    def vintage_path(d):
        if str(d) != ASOF:
            raise FileNotFoundError(f"No vintage for {d}")
        return vf
    for mod in (data_mod, oracle_mod):
        monkeypatch.setattr(mod, "LOCATIONS", loc)
        monkeypatch.setattr(mod, "vintage_path", vintage_path)
    b = {}
    for i, d in enumerate(weeks):
        for j, key in enumerate(("ca", "co", "network_all")):
            b[(key, d)] = round(1.9 + 0.8 * np.sin(2 * np.pi * (i + 5 * j) / 52.0)
                                + 0.05 * ((i * 7 + j) % 5), 4)
    man = {"stream": "flusurv", "digest": BK.digest(b), "cells": len(b)}
    monkeypatch.setattr(MX, "read_bank", lambda banks_dir=None: (b, man))
    return tmp_path


def _samples(loc="Ohio", n=400, seed=1) -> dict:
    rng = np.random.default_rng(seed)
    x0 = rng.gamma(30.0, 3.0, n)
    return {loc: {hz.ORIGIN: x0.tolist(),
                  **{h: (x0 * np.exp(0.08 * (int(h) + 1))
                         * rng.lognormal(0, 0.05, n)).tolist()
                     for h in hz.HORIZONS}}}


@pytest.fixture
def finished(hub, monkeypatch):
    """A finished 4-week run of the Oracle SIHRS start for Ohio, with the
    filter's collect() faked (it records the workroot it was given)."""
    sb.from_shipped("ohio", "Ohio", ASOF)
    w = sb.prepare("ohio", particles=100, forecast_weeks=4,
                   seed=sb.read_info("ohio")["seed"])
    sb.mark(w, "ok")
    seen = []
    raw = _samples()

    def collect(wd):
        seen.append(Path(wd))
        assert json.loads((Path(wd) / "cells.json").read_text())[0]["location"] == "Ohio"
        return {k: {h: list(v) for h, v in s.items()} for k, s in raw.items()}
    monkeypatch.setattr(sb.pf_engine, "collect", collect)
    return {"run": w.name, "dir": w, "seen": seen, "raw": raw}


def _tree(root: Path) -> set:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


def test_oracle_step_on_a_sandbox_run(finished, hub):
    before = _tree(hub)
    out = sb.oracle_step(finished["run"])
    assert finished["seen"] == [finished["dir"]]
    assert out["w"] == OR.W_PRODUCTION == out["w_production"]
    assert out["label"] == "sandbox, not a submission"
    assert out["location"] == "Ohio" and out["forecast_date"] == ASOF
    assert [r["horizon"] for r in out["rows"]] == list(hz.HORIZONS)
    assert [r["target_end_date"] for r in out["rows"]] == [
        "2098-01-11", "2098-01-18", "2098-01-25", "2098-02-01"]
    raw = finished["raw"]["Ohio"]
    for r in out["rows"]:
        assert r["filter"] == pytest.approx(
            list(np.quantile(raw[r["horizon"]], sb.ORACLE_LEVELS)))
        assert r["oracle"] != r["filter"]                # the step moved it
    assert out["active"] == 1 and out["state"] == "both"
    # written only inside the run folder
    rel = str(finished["dir"].relative_to(hub))
    added = _tree(hub) - before
    assert added and all(p.startswith(rel + "/") for p in added)
    assert (finished["dir"] / sb.ORACLE_FILE).is_file()
    prov = json.loads((finished["dir"] / sb.ORACLE_DIR / "oracle.json").read_text())
    assert prov["w"] == OR.W_PRODUCTION and prov["asof"] == ASOF
    assert sb.read_oracle(finished["run"]) == out
    # another w is recorded; outside 0..1 is refused
    assert sb.oracle_step(finished["run"], 0.25)["w"] == 0.25
    with pytest.raises(sb.SandboxError, match="between 0 and 1"):
        sb.oracle_step(finished["run"], 1.5)


def test_the_route_and_the_card(finished):
    run = finished["run"]
    html = client.get(f"/sandbox?model=ohio&run={run}").text
    assert "sandbox, not a submission" in html
    assert f'action="/sandbox/runs/{run}/oracle"' in html
    assert f'value="{OR.W_PRODUCTION}"' in html
    assert "Apply the Oracle step</button>" in html and "tip-sb-oracle-why" not in html
    r = client.post(f"/sandbox/runs/{run}/oracle", data={"w": "0.3"},
                    follow_redirects=False)
    assert r.headers["location"] == f"/sandbox?run={run}&model=ohio"
    assert "w = 0.3" in ui_state._status.get("flash", "")
    html = client.get(f"/sandbox?model=ohio&run={run}").text
    assert "Oracle SIHRS: median (50%, 95%)" in html and "2098-01-11" in html
    assert "(production 0.5)" in html
    ui_state._status.pop("flash", None)
    client.post(f"/sandbox/runs/{run}/oracle", data={"w": "x"},
                follow_redirects=False)
    assert "w must be a number" in ui_state._status.get("flash", "")


def test_step_refused_for_an_edited_model_with_the_reason_in_a_tip(finished):
    run = finished["run"]
    pri = sb.read_model("ohio")["priors.conf"].replace("0.6 2.5", "0.7 2.5")
    sb.save_model("ohio", {"priors.conf": pri})
    gate = sb.oracle_gate(run)
    assert not gate["ok"] and "edited after it was created" in gate["reason"]
    with pytest.raises(sb.SandboxError, match="edited after"):
        sb.oracle_step(run)
    html = client.get(f"/sandbox?model=ohio&run={run}").text
    assert 'disabled aria-describedby="tip-sb-oracle-why"' in html
    assert "edited after it was created (priors.conf)" in html
    assert not (finished["dir"] / sb.ORACLE_FILE).exists()
    # a run of the edited model differs from the creation digests itself
    w2 = sb.prepare("ohio", particles=100, forecast_weeks=4)
    sb.mark(w2, "ok")
    sb.save_model("ohio", {"priors.conf": pri.replace("0.7 2.5", "0.6 2.5")})
    assert sb.shipped_state("ohio")["intact"]
    assert sb.oracle_gate(w2.name)["reason"] == (
        "This run's priors.conf differs from the Oracle SIHRS start as created.")
    assert sb.oracle_gate(run)["ok"]                    # restored: allowed again


def test_step_refused_for_other_weeks_statuses_and_models(finished, hub):
    w3 = sb.prepare("ohio", particles=100, forecast_weeks=3)
    sb.mark(w3, "ok")
    assert "4 forecast weeks" in sb.oracle_gate(w3.name)["reason"]
    w4 = sb.prepare("ohio", particles=100, forecast_weeks=4)
    sb.mark(w4, "failed")
    assert "not finished" in sb.oracle_gate(w4.name)["reason"]
    sb.add_example("sihrs_example")
    w5 = sb.prepare("sihrs_example", particles=100)
    sb.mark(w5, "ok")
    assert "Only runs of a model started from the Oracle SIHRS" in \
        sb.oracle_gate(w5.name)["reason"]
    # a copy of the shipped start is a copy, not the start
    sb.copy_model("ohio", "ohio_copy")
    w6 = sb.prepare("ohio_copy", particles=100)
    sb.mark(w6, "ok")
    assert not sb.oracle_gate(w6.name)["ok"]
    # a dataset start reads no hub bank
    info = sb.read_info("ohio")
    (sb.MODELS / "ohio" / sb.MODEL_FILE).write_text(
        json.dumps({**info, "origin": sb.SHIPPED_DATASET}))
    assert "starts from a dataset" in sb.oracle_gate(finished["run"])["reason"]
    assert not sb.oracle_gate("20990101-000000_nobody")["ok"]
    # none of these reached the step
    assert finished["seen"] == []
