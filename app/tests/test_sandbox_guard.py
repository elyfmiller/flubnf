"""The sandbox's broken edges, fixed: redirects that keep the model open,
the production preflight, the stop path, the interrupted status after a
restart, and the engine guard in both directions (a sandbox fit refuses
to start beside a console run or a replay, and they refuse to start beside
it). Hub-free and engine-free: BNG2.pl and the engine are faked
(conftest.sandbox_root).
"""
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf as pf_engine             # noqa: E402
from app.ui import server as srv                         # noqa: E402

client = TestClient(srv.app)


@pytest.fixture
def box(sandbox_root):
    return sandbox_root


def _wait(pred, n=100):
    for _ in range(n):
        if pred():
            return True
        time.sleep(0.02)
    return pred()


# ------------------------------------------------------------ redirects

def test_save_and_run_redirect_keep_the_model_open(box, monkeypatch):
    sb.add_example("kinetics_example")
    files = sb.read_model("kinetics_example")
    ref = {"referer": "http://testserver/sandbox?model=kinetics_example"}
    r = client.post("/sandbox/models/kinetics_example/save",
                    data={"model_bngl": files["model.bngl"],
                          "data_exp": files["data.exp"],
                          "priors_conf": files["priors.conf"]},
                    headers=ref, follow_redirects=False)
    assert r.headers["location"] == "/sandbox?model=kinetics_example"
    monkeypatch.setattr(sb, "run", lambda w, width=1: {"status": "ok"})
    r = client.post("/sandbox/run", data={"model": "kinetics_example"},
                    headers=ref, follow_redirects=False)
    loc = r.headers["location"]
    assert loc.startswith("/sandbox?run=") and loc.endswith("&model=kinetics_example")
    # a refused run stays on the model too
    srv._status["running"] = "console"
    r = client.post("/sandbox/run", data={"model": "kinetics_example"},
                    headers={"referer": "http://testserver/sandbox"},
                    follow_redirects=False)
    assert r.headers["location"] == "/sandbox?model=kinetics_example"
    srv._status["running"] = None


def test_page_shows_the_open_models_newest_run(box):
    sb.add_example("kinetics_example")
    sb.add_example("sir_example")
    wa = sb.prepare("kinetics_example")
    wb = sb.prepare("sir_example")                       # newer, other model
    html = client.get("/sandbox?model=kinetics_example").text
    assert f'data-run="{wa.name}"' in html and f'data-run="{wb.name}"' not in html
    assert f"/sandbox?run={wb.name}" not in html         # the list is scoped too


def test_results_card_has_no_empty_mode_and_the_list_shows_the_note(box):
    sb.add_example("kinetics_example")
    w = sb.prepare("kinetics_example")
    html = client.get(f"/sandbox?run={w.name}&model=kinetics_example").text
    assert "jitter 0.15 ·  ·" not in html and "· on Bobs" in html
    html = client.get("/sandbox").text
    assert "A model that is not an epidemic" in html


# ------------------------------------------------------------ preflight

def test_prepare_refuses_without_perl_or_engine_in_production_words(box, monkeypatch):
    sb.add_example("kinetics_example")
    monkeypatch.setattr(pf_engine, "perl_available", lambda: False)
    with pytest.raises(sb.SandboxError) as e:
        sb.prepare("kinetics_example")
    assert str(e.value) == pf_engine.perl_missing_message()
    monkeypatch.setattr(pf_engine, "perl_available", lambda: True)
    monkeypatch.setattr(pf_engine, "engine_available", lambda: False)
    with pytest.raises(sb.SandboxError) as e:
        sb.prepare("kinetics_example")
    assert str(e.value) == pf_engine.engine_missing_message()
    monkeypatch.setattr(pf_engine, "engine_available", lambda: True)
    monkeypatch.setattr(pf_engine, "engine_current", lambda: False)
    with pytest.raises(sb.SandboxError) as e:
        sb.prepare("kinetics_example")
    assert "older than this console" in str(e.value)
    assert not sb.RUNS.exists() or not any(sb.RUNS.iterdir())   # nothing made


def test_netgen_without_perl_maps_to_the_perl_message(box, monkeypatch):
    sb.add_example("kinetics_example")

    def gone(cmd, **kw):
        raise FileNotFoundError("perl")
    monkeypatch.setattr(sb.subprocess, "run", gone)
    with pytest.raises(sb.SandboxError) as e:
        sb.prepare("kinetics_example")
    assert str(e.value) == pf_engine.perl_missing_message()


def _fork(tmp_path, accepts_si: bool):
    root = tmp_path / ("fork_si" if accepts_si else "fork_plain")
    (root / "pybnf").mkdir(parents=True)
    (root / "pybnf" / "pf.py").write_text("# stub\n")
    keys = list(pf_engine.CONF_KEYS_REQUIRED) + (
        [pf_engine.SAMPLING_INTERVAL_KEY] if accepts_si else [])
    (root / "pybnf" / "parse.py").write_text(
        "numkeys_int = [%s]\n" % ", ".join("'%s'" % k for k in keys))
    (root / "pybnf" / "config.py").write_text(
        "pf_keys = [%s]\n" % ", ".join("'%s'" % k for k in keys))
    return root


def test_sampling_interval_only_when_the_engine_accepts_it_and_rows_are_weekly(
        box, tmp_path, monkeypatch):
    sb.add_example("kinetics_example")
    monkeypatch.setattr(pf_engine, "PYBNF_PF", _fork(tmp_path, True))
    conf = (sb.prepare("kinetics_example") / "kinetics_example_r0" / "pf.conf").read_text()
    assert conf.count("pf_sampling_interval = 1") == 1
    # time in another unit (half steps): not written
    sb.save_model("kinetics_example", {"data.exp": "# time B_weekly\n0 5\n0.5 6\n1 7\n"})
    conf = (sb.prepare("kinetics_example") / "kinetics_example_r0" / "pf.conf").read_text()
    assert "pf_sampling_interval" not in conf
    # a priors.conf line decides instead, once
    p = sb.read_model("kinetics_example")["priors.conf"]
    sb.save_model("kinetics_example", {"priors.conf": p + "pf_sampling_interval = 2\n"})
    conf = (sb.prepare("kinetics_example") / "kinetics_example_r0" / "pf.conf").read_text()
    assert conf.count("pf_sampling_interval") == 1 and "pf_sampling_interval = 2" in conf
    # an engine that does not accept the key never gets it
    monkeypatch.setattr(pf_engine, "PYBNF_PF", _fork(tmp_path, False))
    sb.save_model("kinetics_example", {"priors.conf": p})
    conf = (sb.prepare("kinetics_example") / "kinetics_example_r0" / "pf.conf").read_text()
    assert "pf_sampling_interval" not in conf


def test_a_priors_line_naming_a_run_setting_is_refused(box):
    sb.add_example("kinetics_example")
    p = sb.read_model("kinetics_example")["priors.conf"]
    sb.save_model("kinetics_example", {"priors.conf": p + "pf_particles = 5\n"})
    with pytest.raises(sb.SandboxError, match="pf_particles"):
        sb.prepare("kinetics_example")


def test_engine_settings_are_the_conf_prepare_writes(box):
    sb.add_example("kinetics_example")
    files = sb.read_model("kinetics_example")
    rows = sb.engine_settings(files["priors.conf"], particles=300, jitter=0.2,
                              forecast_weeks=3, seed=11)
    conf = (sb.prepare("kinetics_example", particles=300, jitter=0.2,
                       forecast_weeks=3, seed=11)
            / "kinetics_example_r0" / "pf.conf").read_text().splitlines()
    assert [f"{k} = {v}" for k, v, _ in rows] == conf[3:3 + len(rows)]
    src = {k: s for k, _, s in rows}
    assert src["pf_particles"] == "run settings" and src["pf_bounds"] == "default"
    assert src["pf_cumulative_observable"] == "priors.conf"


# ------------------------------------------------------------- stopping

def test_stop_writes_the_flag_and_run_records_stopped(box, monkeypatch):
    sb.add_example("kinetics_example")
    w = sb.prepare("kinetics_example")
    srv._sandbox_status["running"] = w.name
    r = client.post(f"/sandbox/runs/{w.name}/stop", follow_redirects=False)
    assert r.status_code == 303 and (w / "STOP").is_file()
    assert r.headers["location"] == f"/sandbox?run={w.name}&model=kinetics_example"

    def stopped(workroot, width=None, timeout=None):
        raise pf_engine.RunStopped()
    monkeypatch.setattr(sb.pf_engine, "execute", stopped)
    assert sb.run(w)["status"] == "stopped"
    # a run that is not live is left alone
    w2 = sb.prepare("kinetics_example")
    client.post(f"/sandbox/runs/{w2.name}/stop", follow_redirects=False)
    assert not (w2 / "STOP").exists()


def test_stop_while_preparing_cancels_before_the_engine(box, monkeypatch):
    sb.add_example("kinetics_example")
    real = sb.prepare
    entered, go, ran = threading.Event(), threading.Event(), []

    def slow(*a, **k):
        entered.set()
        go.wait(5)
        return real(*a, **k)
    monkeypatch.setattr(sb, "prepare", slow)
    monkeypatch.setattr(sb, "run", lambda w, width=1: ran.append(w))
    t = threading.Thread(target=lambda: client.post(
        "/sandbox/run", data={"model": "kinetics_example"}, follow_redirects=False))
    t.start()
    assert entered.wait(5)
    assert client.get("/api/busy").json()["sandbox"] == "kinetics_example (preparing)"
    client.post("/sandbox/stop", follow_redirects=False)
    go.set()
    t.join(5)
    assert ran == [] and srv._sandbox_live() == ""
    assert sb.list_runs()[0]["status"] == "stopped"


def test_an_orphaned_run_reads_interrupted_everywhere(box):
    sb.add_example("kinetics_example")
    w = sb.prepare("kinetics_example")
    meta = json.loads((w / "meta.json").read_text())
    meta["status"] = "running"
    (w / "meta.json").write_text(json.dumps(meta))
    assert sb.results(w)["meta"]["status"] == "running"          # raw
    assert sb.results(w, live=None)["meta"]["status"] == "interrupted"
    assert sb.results(w, live=w.name)["meta"]["status"] == "running"
    assert sb.list_runs(live=None)[0]["status"] == "interrupted"
    # the page and the poll agree, so the page never polls forever
    assert client.get(f"/api/sandbox/runs/{w.name}").json()["meta"]["status"] == "interrupted"
    html = client.get(f"/sandbox?run={w.name}&model=kinetics_example").text
    assert 'data-status="interrupted"' in html


def test_run_ids_are_strict(box):
    for bad in ("../x", "C:x", "..", "x/y", "", "20260101-000000_a/../../b"):
        with pytest.raises(sb.SandboxError):
            sb.run_dir(bad)
        assert client.get(f"/api/sandbox/runs/{bad}").status_code in (404, 405, 422)
    with pytest.raises(sb.SandboxError, match="no sandbox run"):
        sb.run_dir("20260101-000000_nothing")


# ---------------------------------------------------- the two-way guard

def test_the_sandbox_claim_is_taken_before_prepare(box, monkeypatch):
    sb.add_example("kinetics_example")
    calls, entered, go = [], threading.Event(), threading.Event()
    real = sb.prepare

    def slow(*a, **k):
        calls.append(a)
        entered.set()
        go.wait(5)
        return real(*a, **k)
    monkeypatch.setattr(sb, "prepare", slow)
    monkeypatch.setattr(sb, "run", lambda w, width=1: {"status": "ok"})
    t = threading.Thread(target=lambda: client.post(
        "/sandbox/run", data={"model": "kinetics_example"}, follow_redirects=False))
    t.start()
    assert entered.wait(5)
    client.post("/sandbox/run", data={"model": "kinetics_example"},
                follow_redirects=False)
    go.set()
    t.join(5)
    assert len(calls) == 1
    assert _wait(lambda: srv._sandbox_live() == "")


def test_console_run_and_replay_refuse_while_a_sandbox_fit_is_live(box):
    srv._sandbox_status["running"] = "20990101-000000_mine"
    srv._status.pop("flash", None)
    r = client.post("/run", data={"forecast_date": "2099-01-02",
                                  "locations": "Alabama"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/forecast"
    assert srv._status.get("running") is None                  # nothing claimed
    assert "sandbox fit holds the engine (20990101-000000_mine)" in srv._status["flash"]
    srv._status.pop("flash", None)
    r = client.post("/retro/run", data={"season": "2098-99"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/retro"
    assert "sandbox fit" in srv._status["flash"]
    # a foreign Host is still the CSRF guard's to refuse
    r = client.post("/run", data={}, headers={"host": "evil.example"},
                    follow_redirects=False)
    assert r.status_code == 403
    srv._sandbox_status["running"] = None


def test_api_busy_reports_the_sandbox_and_the_guard_knows_it(box):
    srv._sandbox_status["running"] = "20990101-000000_mine"
    assert client.get("/api/busy").json()["sandbox"] == "20990101-000000_mine"
    srv._sandbox_status["running"] = None
    assert client.get("/api/busy").json()["sandbox"] is None
    base = (Path(srv.__file__).parent / "templates" / "base.html").read_text()
    assert "function sandboxConflict(b)" in base and "stop:'/sandbox/stop'" in base
    assert "kind==='sandbox-run'" in base
    sb.add_example("kinetics_example")
    html = client.get("/sandbox?model=kinetics_example").text
    assert 'data-guard="sandbox-run"' in html and 'data-guard="console-run"' not in html
