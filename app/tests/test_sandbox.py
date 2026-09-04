"""The sandbox: a model of your own through the same engine, in its own
folder, reaching nothing else in the console (app/core/sandbox.py and the
/sandbox routes). Hub-free and engine-free: BNG2.pl and the engine runner
are faked; what is tested is the folder contract, the configuration the
engine receives, the outputs read back, and the page's guards.
"""
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np                                       # noqa: E402
import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import sandbox as sb                       # noqa: E402
from app.ui import server as srv                         # noqa: E402

client = TestClient(srv.app)


@pytest.fixture
def box(tmp_path, monkeypatch):
    """A sandbox rooted in tmp_path, with BNG2.pl faked to write m.net."""
    monkeypatch.setattr(sb, "SANDBOX", tmp_path / "sandbox")
    monkeypatch.setattr(sb, "MODELS", tmp_path / "sandbox" / "models")
    monkeypatch.setattr(sb, "RUNS", tmp_path / "sandbox" / "runs")

    def fake_netgen(cmd, **kw):
        cwd = Path(kw.get("cwd", "."))
        if "broken" not in (cwd / "m.bngl").read_text():
            (cwd / "m.net").write_text("# net\n")
        return types.SimpleNamespace(stdout="ABORT: bad rule\n", stderr="",
                                     returncode=0)
    monkeypatch.setattr(sb.subprocess, "run", fake_netgen)
    srv._status["running"] = None
    srv._sandbox_status["running"] = None
    return tmp_path / "sandbox"


# ------------------------------------------------------------ the folder

def test_names_are_checked_and_examples_ship_complete():
    for bad in ("", "../x", "a b", ".hidden", "x" * 65):
        with pytest.raises(sb.SandboxError):
            sb.check_name(bad)
    assert sb.check_name("sihrs_example") == "sihrs_example"
    assert set(sb.list_examples()) >= {"sihrs_example", "kinetics_example"}
    for e in sb.list_examples():
        assert all((sb.EXAMPLES / e / f).is_file() for f in sb.REQUIRED)


def test_an_example_copies_in_once_and_lists_complete(box):
    d = sb.add_example("kinetics_example")
    assert sorted(p.name for p in d.iterdir()) == sorted(sb.REQUIRED)
    with pytest.raises(sb.SandboxError, match="already exists"):
        sb.add_example("kinetics_example")
    with pytest.raises(sb.SandboxError, match="no shipped example"):
        sb.add_example("nope")
    (sb.MODELS / "half").mkdir()
    (sb.MODELS / "half" / "model.bngl").write_text("# half a model\n")
    ms = {m["name"]: m for m in sb.list_models()}
    assert ms["kinetics_example"]["complete"]
    assert ms["kinetics_example"]["note"].startswith("A model that is not an epidemic")
    assert not ms["half"]["complete"] and ms["half"]["missing"] == ["data.exp", "priors.conf"]


def test_the_data_file_and_the_priors_are_read_strictly():
    with pytest.raises(sb.SandboxError, match="header"):
        sb.read_exp("0 1\n1 2\n")
    with pytest.raises(sb.SandboxError, match="values"):
        sb.read_exp("# time y\n0 1 2\n")
    d = sb.read_exp("# time y\n0 1\n1 2.5\n")
    assert d["columns"] == ["time", "y"] and d["rows"] == [[0.0, 1.0], [1.0, 2.5]]
    priors, keys = sb.split_priors("uniform_var = k__FREE 0 1  # rate\n"
                                   "pf_cumulative_observable = Bobs\n"
                                   "objfunc = chi_sq\n")
    assert priors == ["uniform_var = k__FREE 0 1"]
    assert keys == {"pf_cumulative_observable": "Bobs", "objfunc": "chi_sq"}
    with pytest.raises(sb.SandboxError, match="no free parameter"):
        sb.split_priors("pf_jitter = 0.2\n")
    with pytest.raises(sb.SandboxError, match="suffix"):
        sb.simulate_suffix("begin model\nend model\n")
    assert sb.simulate_suffix('simulate({suffix=>"kin",method=>"ode"})') == "kin"


# ---------------------------------------------------------- preparation

def test_prepare_writes_the_engine_configuration_from_the_three_files(box):
    sb.add_example("kinetics_example")
    w = sb.prepare("kinetics_example", particles=300, jitter=0.2,
                   forecast_weeks=3, seed=11)
    cell = w / "kinetics_example_r0"
    assert (cell / "m.bngl").is_file() and (cell / "kin.exp").is_file()
    assert (cell / "m.net").is_file()                    # the netgen check
    conf = (cell / "pf.conf").read_text()
    for line in ("fit_type = pf", "num_particles = 300", "pf_jitter = 0.2",
                 "pf_observable_mode = integrated",
                 "pf_cumulative_observable = Bobs", "pf_forecast_weeks = 3",
                 "seed = 11", "initialization = rand", "objfunc = neg_bin_dynamic",
                 "uniform_var = k__FREE 0.05 1.0"):
        assert line in conf, line
    assert conf.count("pf_cumulative_observable") == 1   # no duplicate key
    cells = json.loads((w / "cells.json").read_text())
    assert cells[0]["key"] == "kinetics_example_r0" and cells[0]["sandbox"]
    assert cells[0]["n_obs"] == 12 and cells[0]["particles"] == 300
    meta = json.loads((w / "meta.json").read_text())
    assert meta["status"] == "prepared" and meta["obs_col"] == "B_weekly"
    assert len(meta["observed"]) == 12 and meta["suffix"] == "kin"
    # the second run of the same model gets its own folder
    w2 = sb.prepare("kinetics_example")
    assert w2 != w and w2.is_dir()


def test_a_model_that_does_not_generate_is_refused_with_bngs_words(box):
    sb.add_example("kinetics_example")
    sb.save_model("kinetics_example", {"model.bngl": "# broken\n" + (
        sb.read_model("kinetics_example")["model.bngl"])})
    with pytest.raises(sb.SandboxError, match="ABORT: bad rule"):
        sb.prepare("kinetics_example")


def test_run_records_the_outcome_and_results_read_the_outputs(box, monkeypatch):
    sb.add_example("kinetics_example")
    w = sb.prepare("kinetics_example", particles=100)
    cell = w / "kinetics_example_r0"

    def fake_execute(workroot, width=None, timeout=None):
        runs = cell / "out" / "Results" / "A_MCMC" / "Runs"
        runs.mkdir(parents=True)
        (runs / "params_0.txt").write_text(
            "k__FREE\tscale__FREE\tr__FREE\n" + "\n".join(
                f"{0.2 + 0.001 * i} 0.4 8.0" for i in range(100)) + "\n")
        tr = np.tile(np.arange(1.0, 17.0), (100, 1))       # 12 weeks + 4
        np.savetxt(runs / "traj_noise_kinB_weekly_chain_0.txt", tr)
        (cell / "out" / "ess_0.txt").write_text(
            "# t\tess\tparticles\tdistinct\tdegenerate\n"
            "0\t80.0\t100\t100\t0\n1\t60.5\t100\t70\t0\n")
        return {"kinetics_example_r0": "ok"}
    monkeypatch.setattr(sb.pf_engine, "execute", fake_execute)
    meta = sb.run(w)
    assert meta["status"] == "ok" and meta["seconds"] >= 0
    r = sb.results(w)
    assert [p["name"] for p in r["params"]] == ["k__FREE", "scale__FREE", "r__FREE"]
    assert r["params"][0]["p50"] == pytest.approx(0.2495, abs=1e-3)
    assert r["distinct"] == 100 and r["sample"] == 100
    assert r["ess"][-1]["ess"] == 60.5 and r["ess"][-1]["distinct"] == 70
    assert r["traj"]["n_obs"] == 12 and r["traj"]["columns"] == 16
    assert r["traj"]["q50"][:3] == [1.0, 2.0, 3.0]
    assert sb.list_runs()[0]["run_id"] == w.name

    def failing_execute(workroot, width=None, timeout=None):
        raise RuntimeError("engine venv missing")
    monkeypatch.setattr(sb.pf_engine, "execute", failing_execute)
    w2 = sb.prepare("kinetics_example")
    assert sb.run(w2)["status"] == "failed"
    assert "engine venv missing" in sb.results(w2)["meta"]["error"]


# --------------------------------------------------------------- the page

def test_sandbox_page_lists_examples_models_and_runs(box):
    html = client.get("/sandbox").text
    assert 'href="/sandbox"' in html and "Sandbox" in html
    assert 'value="kinetics_example"' in html                # add-example form
    assert "No models yet" in html
    client.post("/sandbox/add-example", data={"name": "sihrs_example"},
                follow_redirects=False)
    html = client.get("/sandbox?model=sihrs_example").text
    assert "sihrs_example" in html and "complete" in html
    assert 'name="model_bngl"' in html                       # the editor
    assert "Hobs() = mult*H_Cum" in html


def test_sandbox_run_is_refused_while_the_engine_is_busy(box, monkeypatch):
    sb.add_example("kinetics_example")
    started = []
    monkeypatch.setattr(sb, "prepare", lambda *a, **k: started.append(a) or box / "runs" / "x")
    srv._status["running"] = "console"
    r = client.post("/sandbox/run", data={"model": "kinetics_example"},
                    follow_redirects=False)
    assert r.status_code == 303 and started == []
    srv._status["running"] = None
    srv._sandbox_status["running"] = "earlier"
    client.post("/sandbox/run", data={"model": "kinetics_example"},
                follow_redirects=False)
    assert started == []
    srv._sandbox_status["running"] = None


def test_sandbox_run_prepares_and_starts_in_the_background(box, monkeypatch):
    sb.add_example("kinetics_example")
    ran = []
    monkeypatch.setattr(sb, "run", lambda w, width=1: ran.append(Path(w)) or {"status": "ok"})
    r = client.post("/sandbox/run", data={"model": "kinetics_example",
                                          "particles": "120", "seed": "3"},
                    follow_redirects=False)
    assert r.status_code == 303 and "/sandbox?run=" in r.headers["location"]
    import time
    for _ in range(50):
        if ran:
            break
        time.sleep(0.05)
    assert len(ran) == 1 and ran[0].parent == sb.RUNS
    conf = (ran[0] / "kinetics_example_r0" / "pf.conf").read_text()
    assert "num_particles = 120" in conf and "seed = 3" in conf
    assert srv._sandbox_status["running"] is None            # released
    r = client.post("/sandbox/run", data={"model": "nope"}, follow_redirects=False)
    assert r.status_code == 303 and len(ran) == 1            # refused, not started
    assert client.get("/api/sandbox/runs/../etc").status_code in (404, 422)
