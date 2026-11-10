"""bngsim's compiled-model cache, contained in the state folder (F8).

  * every engine runner (forecast, replay, Sandbox; private and public
    engines) gets BNGSIM_CODEGEN_CACHE_DIR = <state>/engine-cache/
    bngsim-codegen, on macOS/Linux and on Windows alike, from the state
    folder FLUBNF_STATE_DIR moves, as an absolute path; a folder already
    set wins, a blank one does not, and the caller's env is not mutated;
  * Storage lists the cache with its size, outside the total, and its
    Delete clears it while the engine is idle;
  * Reclaim offers the cache as a category and clears it;
  * neither clears it while an engine job runs: a console run here, or a
    live engine runner of another process in any runner registry; and a
    folder a fit makes after the cache was set aside is never deleted.

The cache decides compile time only: the same .net compiles to the same
library, so no forecast, score or record changes (nothing here runs bngsim).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                     # noqa: E402
from app.core import reclaim                         # noqa: E402
from app.core.engines import lwf, pf                 # noqa: E402
from app.ui import retro_prep as ui_retro_prep       # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons  # noqa: E402
from app.ui import server as srv                     # noqa: E402
from app.ui import shared as ui_shared               # noqa: E402
from app.ui import state as ui_state                 # noqa: E402

client = TestClient(srv.app)

VAR = "BNGSIM_CODEGEN_CACHE_DIR"
REPO = Path(__file__).resolve().parents[2]


def _cache(state: Path) -> Path:
    return state / "engine-cache" / "bngsim-codegen"


def _fill(d: Path, n: int = 3, size: int = 4096) -> int:
    """A cache holding n compiled libraries; returns its bytes."""
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (d / f"rhs_{i:016x}.dylib").write_bytes(b"\x7f" * size)
    return n * size


@pytest.fixture
def state(tmp_path, monkeypatch):
    """APP_STATE -> tmp, the engine idle, no runner registry populated."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    from app.core import datasets as datasets_mod
    monkeypatch.setattr(datasets_mod, "ROOT", tmp_path / "datasets")
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "seal")
    import flubnf.settings as settings_mod
    monkeypatch.setattr(settings_mod, "HUB", tmp_path / "hub")
    reg = tmp_path / "registry.json"
    monkeypatch.setattr(reclaim, "runner_registries", lambda: [reg],
                        raising=False)
    status = dict(ui_state._status)
    sbx = dict(ui_state._sandbox_status)
    retro_st = dict(ui_retro_seasons._retro_status)
    ui_state._status.update({"running": None, "workroot": None,
                             "flash": "", "flash_detail": ""})
    ui_state._sandbox_status.update({"running": None, "claim": None,
                                     "experiment": None})
    ui_retro_seasons._retro_status.clear()
    ui_retro_prep._results_jobs.clear()
    ui_shared._invalidate_scans()
    yield {"root": tmp_path, "cache": _cache(tmp_path), "registry": reg}
    ui_state._status.clear(); ui_state._status.update(status)
    ui_state._sandbox_status.clear(); ui_state._sandbox_status.update(sbx)
    ui_retro_seasons._retro_status.clear()
    ui_retro_seasons._retro_status.update(retro_st)
    ui_retro_prep._results_jobs.clear()
    ui_shared._invalidate_scans()


@pytest.fixture
def live_runner(tmp_path):
    """A live process whose command line names its runner script, as the
    engine's shard runners are recorded (pf.record_runner_pids)."""
    script = tmp_path / "pf_runner_0.py"
    script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(script)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    time.sleep(0.3)
    try:
        yield proc, script
    finally:
        proc.kill()
        proc.wait(timeout=10)


def _record(reg: Path, proc, script: Path) -> None:
    reg.write_text(json.dumps({str(proc.pid): {"pgid": proc.pid,
                                               "runner": str(script)}}),
                   encoding="utf-8")


def _flash() -> str:
    return ui_state._status.get("flash", "")


def ui_storage() -> dict:
    from app.ui.routes import storage
    return storage._storage_inventory()


# ------------------------------------------------- the runners' environment

@pytest.mark.parametrize("os_name", ["posix", "nt"])
def test_every_runner_gets_the_state_folders_cache(state, monkeypatch,
                                                   os_name):
    monkeypatch.delenv(VAR, raising=False)
    monkeypatch.setattr(pf, "bng_env", lambda *a, **k: None)
    kw = pf.runner_popen_kwargs({}, _os_name=os_name)
    assert kw["env"][VAR] == str(state["cache"])
    assert Path(kw["env"][VAR]).is_absolute()
    assert kw["env"]["PATH"] == os.environ.get("PATH")    # this process's
    # the Sandbox's own environment: a copy gets it, the caller's does not
    given = {"PATH": "x", "BNGPATH": "y"}
    kw = pf.runner_popen_kwargs({}, _os_name=os_name, env=given)
    assert kw["env"][VAR] == str(state["cache"])
    assert kw["env"]["BNGPATH"] == "y"
    assert VAR not in given
    # nothing is made until bngsim compiles
    assert not state["cache"].exists()


@pytest.mark.parametrize("os_name", ["posix", "nt"])
def test_a_cache_folder_already_set_wins(state, monkeypatch, os_name):
    monkeypatch.setattr(pf, "bng_env", lambda *a, **k: None)
    monkeypatch.setenv(VAR, "/scratch/node-local/codegen")
    kw = pf.runner_popen_kwargs({}, _os_name=os_name)
    assert kw["env"][VAR] == "/scratch/node-local/codegen"
    kw = pf.runner_popen_kwargs({}, _os_name=os_name,
                                env={VAR: "/given/codegen"})
    assert kw["env"][VAR] == "/given/codegen"
    # bngsim reads a blank value as unset (~/.cache): a blank one is filled
    kw = pf.runner_popen_kwargs({}, _os_name=os_name, env={VAR: "  "})
    assert kw["env"][VAR] == str(state["cache"])


def test_flubnf_state_dir_moves_the_cache_and_a_relative_one_is_made_absolute(
        tmp_path):
    """A fresh Python, as a console started with FLUBNF_STATE_DIR: the
    runners' cache follows it, absolute (a public cell runs in its own
    folder, where a relative path would scatter caches)."""
    env = dict(os.environ)
    env.pop(VAR, None)
    env["FLUBNF_STATE_DIR"] = "moved-state"
    code = ("import sys; sys.path.insert(0, %r); "
            "from app.core.engines import pf; "
            "print(pf.runner_popen_kwargs({})['env'][%r])" % (str(REPO), VAR))
    out = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path),
                         env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    got = Path(out.stdout.strip().splitlines()[-1])
    assert got.is_absolute()
    assert got.resolve() == _cache((tmp_path / "moved-state").resolve())


@pytest.mark.skipif(os.name != "posix", reason="POSIX launch")
def test_a_launched_runner_sees_it(state, monkeypatch):
    monkeypatch.delenv(VAR, raising=False)
    kw = pf.runner_popen_kwargs({})
    out = subprocess.run([sys.executable, "-c",
                          f"import os; print(os.environ[{VAR!r}])"],
                         capture_output=True, text=True, timeout=60, **kw)
    assert out.stdout.strip() == str(state["cache"])


def test_the_public_engines_cells_inherit_it(monkeypatch):
    """lwf's shard runners start through pf.runner_popen_kwargs; each cell's
    PyBNF process gets a copy of its runner's environment (LWF_CELL's
    _lwf_env), so the variable reaches bngsim there too."""
    src = lwf.LWF_CELL
    start = src.index("def _lwf_env():")
    ns = {"os": os}
    exec(src[start:src.index("\ndef ", start + 1)], ns)
    monkeypatch.setenv(VAR, "/state/engine-cache/bngsim-codegen")
    assert ns["_lwf_env"]()[VAR] == "/state/engine-cache/bngsim-codegen"
    assert lwf.runner_env({VAR: "/s"})[VAR] == "/s"


# ------------------------------------------------------------ reclaim core

def test_the_cache_is_sized_and_cleared_while_idle(state):
    b = _fill(state["cache"])
    leftover = state["cache"].with_name("bngsim-codegen.clearing-1-2")
    b += _fill(leftover, n=1)
    assert reclaim.codegen_cache_entries() == [state["cache"], leftover]
    assert reclaim.codegen_cache_bytes() == b
    out = reclaim.clear_codegen_cache(registries=[])
    assert out == {"bytes": b, "refused": "", "busy": False}
    assert not state["cache"].exists() and not leftover.exists()
    assert reclaim.codegen_cache_entries() == []
    assert not any(state["root"].glob("engine-cache/*"))


def test_a_fit_starting_after_the_set_aside_keeps_its_fresh_folder(state):
    """Under the engine lock the folder is renamed aside; a fit that starts
    once the lock is released compiles into a fresh folder, which the
    deletion that follows never touches."""
    _fill(state["cache"])

    class Lock:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            # a fit compiling now: bngsim makes the folder again
            _fill(state["cache"], n=1, size=10)
            return False

    out = reclaim.clear_codegen_cache(lock=Lock(), registries=[])
    assert out["bytes"] == 3 * 4096 and not out["refused"]
    assert [p.name for p in state["cache"].iterdir()] == [
        "rhs_0000000000000000.dylib"]
    assert reclaim.codegen_cache_entries() == [state["cache"]]


def test_never_cleared_while_an_engine_job_runs(state, live_runner):
    b = _fill(state["cache"])
    # this console's own job (the caller's reason), asked under its lock
    out = reclaim.clear_codegen_cache(busy=lambda: "a console run is in "
                                      "progress", registries=[])
    assert out == {"bytes": 0, "refused": "a console run is in progress",
                   "busy": True}
    # another process's live runner, from its registry
    proc, script = live_runner
    _record(state["registry"], proc, script)
    assert reclaim.engine_runners_live([state["registry"]]) == 1
    out = reclaim.clear_codegen_cache(registries=[state["registry"]])
    assert out["busy"] and "1 engine runner is fitting" in out["refused"]
    assert reclaim.codegen_cache_bytes() == b            # every byte kept
    # once it ended, the same registry entry holds nothing
    proc.kill()
    proc.wait(timeout=10)
    assert reclaim.engine_runners_live([state["registry"]]) == 0
    assert reclaim.clear_codegen_cache(
        registries=[state["registry"]])["bytes"] == b


def test_a_recycled_or_unreadable_registry_entry_holds_nothing(tmp_path):
    reg = tmp_path / "pf_runners.json"
    # a live pid (this one) whose command line names another script
    reg.write_text(json.dumps({str(os.getpid()): {
        "pgid": None, "runner": str(tmp_path / "pf_runner_9.py")}}))
    assert reclaim.engine_runners_live([reg]) == 0
    reg.write_text("not json")
    assert reclaim.engine_runners_live([reg, tmp_path / "missing.json"]) == 0


def test_the_registries_are_the_consoles_the_terminals_and_the_runners():
    from app.core import runner
    from flubnf.cli_sandbox import _terminal_registry
    regs = reclaim.runner_registries()
    assert Path(pf.RUNNER_PIDS_FILE) in regs
    assert Path(_terminal_registry()) in regs
    assert runner.state_dir() / runner.REGISTRY_FILE in regs


# --------------------------------------------------------------- Storage

def test_storage_lists_the_cache_with_its_size_outside_the_total(state):
    html = client.get("/storage").text
    assert 'id="h-st-ec"' not in html                    # none on disk: none
    _fill(state["cache"], n=4, size=256 * 1024)
    ui_shared._invalidate_scans()
    inv = ui_storage()
    ec = inv["engine_cache"]
    assert ec["id"] == "bngsim-codegen" and ec["bytes"] == 4 * 256 * 1024
    assert ec["size_h"] and not ec["busy"]
    assert inv["total_bytes"] == 0                       # not in the total
    html = client.get("/storage").text
    sec = html.split('id="h-st-ec"', 1)[1].split("</section>", 1)[0]
    assert "Engine cache" in html and ec["size_h"] in sec
    assert "not in the total" in sec
    assert 'name="kind" value="engine-cache"' in sec
    assert 'value="bngsim-codegen"' in sec



def test_storage_delete_clears_the_cache_when_idle(state):
    b = _fill(state["cache"])
    r = client.post("/storage/delete", data={
        "kind": "engine-cache", "ident": "bngsim-codegen",
        "confirm": "bngsim-codegen"}, follow_redirects=False)
    assert r.status_code == 303
    assert not state["cache"].exists()
    assert "Cleared the engine cache" in _flash()
    assert ui_state._status.get("flash_kind") == "ok"
    assert b > 0


def test_storage_refuses_while_a_console_run_is_in_progress(state):
    b = _fill(state["cache"])
    ui_state._status["running"] = "all:20981010T101010-abcdef"
    row = ui_storage()["engine_cache"]
    assert row["busy"] and "a console run is in progress" in row["why"]
    html = client.get("/storage").text
    assert 'id="st-ec-1" disabled' in html
    assert html.count(row["why"]) == 1                   # said once, above
    r = client.post("/storage/delete", data={
        "kind": "engine-cache", "ident": "bngsim-codegen",
        "confirm": "bngsim-codegen"}, follow_redirects=False)
    assert r.status_code == 303
    assert reclaim.codegen_cache_bytes() == b
    assert "Not deleted" in _flash() and "engine runs" in _flash()


def test_storage_refuses_while_another_process_fits(state, live_runner):
    b = _fill(state["cache"])
    _record(state["registry"], *live_runner)
    assert ui_storage()["engine_cache"]["busy"]
    client.post("/storage/delete", data={
        "kind": "engine-cache", "ident": "bngsim-codegen",
        "confirm": "bngsim-codegen"}, follow_redirects=False)
    assert reclaim.codegen_cache_bytes() == b
    assert "Not deleted" in _flash()


def test_storage_refuses_a_crafted_or_unconfirmed_clear(state):
    b = _fill(state["cache"])
    for data in ({"kind": "engine-cache", "ident": "..",
                  "confirm": ".."},
                 {"kind": "engine-cache", "ident": "bngsim-codegen",
                  "confirm": ""}):
        client.post("/storage/delete", data=data, follow_redirects=False)
        assert reclaim.codegen_cache_bytes() == b
        assert "Not deleted" in _flash()


# --------------------------------------------------------------- Reclaim

def test_reclaim_offers_and_clears_the_cache_when_idle(state):
    b = _fill(state["cache"])
    d = client.get("/api/storage/reclaim").json()
    cat = [c for c in d["categories"] if c.get("key") == "engine-cache"]
    assert len(cat) == 1 and cat[0]["bytes"] == b
    assert cat[0]["label"] == "Engine cache (compiled models)"
    assert d["total"] == b and d["confirm"] == "0/0/0"
    assert state["cache"].is_dir()                       # the dry run: no change
    r = client.post("/storage/reclaim", data={"confirm": d["confirm"]},
                    follow_redirects=False)
    assert r.status_code == 303
    assert not state["cache"].exists()
    assert "Reclaimed" in _flash()
    assert "by clearing the engine cache" in ui_state._status["flash_detail"]
    assert "hub clone were not touched" in ui_state._status["flash_detail"]


def test_reclaim_keeps_the_cache_while_an_engine_job_runs(state, live_runner):
    b = _fill(state["cache"])
    # a replay in this console
    ui_retro_seasons._retro_status["2098-99"] = "running"
    d = client.get("/api/storage/reclaim").json()
    assert not [c for c in d["categories"] if c.get("key") == "engine-cache"]
    client.post("/storage/reclaim", data={"confirm": d["confirm"]},
                follow_redirects=False)
    assert reclaim.codegen_cache_bytes() == b
    # another process's runner, starting between the report and the click
    ui_retro_seasons._retro_status.clear()
    d = client.get("/api/storage/reclaim").json()
    assert d["total"] == b
    _record(state["registry"], *live_runner)
    client.post("/storage/reclaim", data={"confirm": d["confirm"]},
                follow_redirects=False)
    assert reclaim.codegen_cache_bytes() == b
