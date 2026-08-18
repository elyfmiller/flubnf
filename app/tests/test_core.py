"""App core: the constitutional rules must hold as code."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd
import pytest


def test_seed_is_deterministic_and_distinct():
    from app.core.runs import derive_seed
    a = derive_seed("Ohio", "2026-01-24", 0)
    assert a == derive_seed("Ohio", "2026-01-24", 0)          # reproducible
    assert a != derive_seed("Ohio", "2026-01-24", 1)          # per-replicate
    assert a != derive_seed("California", "2026-01-24", 0)    # per-location


def test_workroot_lease_is_exclusive(tmp_path):
    from app.core.runs import lease_workroot
    lease_workroot("run-x", base=tmp_path)
    with pytest.raises(FileExistsError):                      # rule 1: collision = ERROR
        lease_workroot("run-x", base=tmp_path)


def test_ledger_roundtrip(tmp_path):
    from app.core.runs import Ledger, RunSpec
    led = Ledger(tmp_path / "ledger.sqlite")
    spec = RunSpec(engine="pf", forecast_date="2026-01-24", locations=["Ohio"])
    rid = led.open_run(spec, tmp_path / "w", {"bngsim": "0.13.0"})
    led.close_run(rid, "ok", {"cells": 3})
    rows = led.rows()
    assert rows[0]["run_id"] == rid and rows[0]["status"] == "ok"
    assert '"engine": "pf"' in rows[0]["spec"]


def test_vintage_path_fails_loudly():
    from app.core.data import vintage_path
    with pytest.raises(FileNotFoundError, match="Nearby"):
        vintage_path("2024-07-15")                            # inside the gap


def test_submission_validation_catches_defects():
    from app.core.submit import QUANTILES, validate
    rows = [{"location": "39", "horizon": 0, "output_type": "quantile",
             "output_type_id": q, "value": 100.0} for q in QUANTILES]
    assert any("degenerate" in p for p in validate(pd.DataFrame(rows)))
    rows[0]["value"] = 500.0                                  # non-monotone now
    assert any("monotone" in p for p in validate(pd.DataFrame(rows)))


def test_submission_writes_hub_layout(tmp_path):
    from app.core.submit import quantile_rows, write_submission
    rng = np.random.default_rng(0)
    samples = {str(h): rng.gamma(5, 20, 4000).tolist() for h in (1, 2, 3, 4)}
    rows = quantile_rows(samples, "39", "2026-01-24")
    p = write_submission(rows, "PF-SIHRS", "NAU", "2026-01-24", tmp_path)
    assert p.name == "2026-01-24-NAU-PF-SIHRS.csv"
    assert p.parent.name == "NAU-PF-SIHRS"                    # identity in the PATH
    df = pd.read_csv(p)
    assert len(df) == 4 * 23 and (df.value >= 0).all()


def test_choropleth_renders_gaps_explicitly():
    from app.core.report import categorical_probs, choropleth_svg
    probs = categorical_probs(np.full(1000, 450.0), last_observed=400.0,
                              population=10_000_000, horizon=1)
    assert abs(sum(probs.values()) - 1.0) < 1e-9
    svg = choropleth_svg({"OH": probs, "MA": {}})             # MA = reporting gap
    assert "no data (reporting gap)" in svg                   # rule 10: gaps visible
    assert svg.count("<rect") > 50                            # all tiles render


def test_analogue_engine_runs_real_vintage():
    from flubnf.settings import ARCHIVE
    if not ARCHIVE.is_dir():
        pytest.skip("FluSight hub clone not present")
    from app.core.engines import analogue
    from app.core.runs import RunSpec
    spec = RunSpec(engine="analogue", forecast_date="2026-01-24",
                   locations=["Ohio", "Wyoming"], season_start="2025-08-01")
    out = analogue.run(spec)
    assert set(out) == {"Ohio", "Wyoming"}
    q = out["Ohio"]["1"]
    assert len(q) == 23 and q[0.5] > 0
    vals = [q[k] for k in sorted(q)]
    assert all(b >= a for a, b in zip(vals, vals[1:]))       # monotone


def test_vincentize_blends_and_renormalizes():
    from app.core.ensemble import vincentize
    qa = {"1": {L: 100.0 for L in _levels()}, "2": {L: 100.0 for L in _levels()}}
    qb = {"1": {L: 200.0 for L in _levels()}}                # member missing h2
    out = vincentize({"pf": qa, "analogue": qb},
                     weights={"pf": 0.6, "analogue": 0.4})
    assert abs(out["1"][0.5] - 140.0) < 1e-9                 # 0.6*100 + 0.4*200
    assert abs(out["2"][0.5] - 100.0) < 1e-9                 # renormalized to pf alone


def _levels():
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
    return [float(q) for q in QL]


def test_run_page_renders_sealed_run():
    """The /runs/{id} page renders any ledger run with a results.json."""
    from fastapi.testclient import TestClient
    from app.core.runs import APP_STATE
    from app.ui.server import app as srv
    runs = sorted((APP_STATE / "workroots").glob("*/results.json"))
    if not runs:
        pytest.skip("no sealed runs on this machine")
    rid = runs[-1].parent.name
    c = TestClient(srv)
    r = c.get(f"/runs/{rid}")
    assert r.status_code == 200 and "submissions" in r.text
