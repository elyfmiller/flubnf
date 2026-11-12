"""The engine cache's folder and the runners recorded against it (#93's
re-check, findings 1 to 6).

  1. a cache folder the runners cannot write is said, never left to
     bngsim's silent interpreted fallback: the folder is made and written
     to at each runner's launch; one that fails leaves the runner on
     bngsim's own folder, and the reason is kept for Storage (which shows
     it) and said once on the console's error output;
  2. the runners using the cache are recorded beside it, in the state
     folder, so a console of another checkout on the same FLUBNF_STATE_DIR
     keeps the cache while its runners compile; the takeover registry
     stays with its checkout's app.pid, as flubnf/cli.py sweeps it;
  3. a registry is read and written back under a lock, so two runs (two
     threads, or two processes) recording at once lose no runner;
  4. a protected cache folder has no Delete and Reclaim leaves it out;
  5. with only the cache on disk, Storage says the cache, not "Nothing
     stored yet", and offers Reclaim;
  6. bngsim's own folder (~/.cache/bngsim/codegen) is said to be left where
     it is, and a linked cache folder gets a row, with no Delete.

Nothing here runs bngsim or changes a forecast, score or record.
"""
import json
import os
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                     # noqa: E402
from app.core import reclaim                         # noqa: E402
from app.core.engines import pf                      # noqa: E402
from app.ui import retro_prep as ui_retro_prep       # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons  # noqa: E402
from app.ui import server as srv                     # noqa: E402
from app.ui import shared as ui_shared               # noqa: E402
from app.ui import state as ui_state                 # noqa: E402

client = TestClient(srv.app)

VAR = "BNGSIM_CODEGEN_CACHE_DIR"
NO_CODEGEN = "BNGSIM_NO_CODEGEN"
OWN = "~/.cache/bngsim/codegen"          # bngsim's own folder
REPO = Path(__file__).resolve().parents[2]
POSIX_USER = os.name == "posix" and os.geteuid() != 0


def _fill(d: Path, n: int = 3, size: int = 4096) -> int:
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (d / f"rhs_{i:016x}.dylib").write_bytes(b"\x7f" * size)
    return n * size


def _flash() -> str:
    return ui_state._status.get("flash", "")


def _section(html: str) -> str:
    """The engine cache's section of the Storage page ("" when none)."""
    if 'id="h-st-ec"' not in html:
        return ""
    return html.split('id="h-st-ec"', 1)[1].split("</section>", 1)[0]


def _summary(html: str) -> str:
    """The On disk fold's summary line."""
    return html.split('id="h-st-disk"', 1)[1].split("</summary>", 1)[0]


@pytest.fixture
def state(tmp_path, monkeypatch):
    """APP_STATE -> tmp/state, the engine idle, no live runner anywhere,
    no bngsim folder in a home of its own, no protected root."""
    root = tmp_path / "state"
    root.mkdir()
    monkeypatch.setattr(runs_mod, "APP_STATE", root)
    from app.core import datasets as datasets_mod
    monkeypatch.setattr(datasets_mod, "ROOT", root / "datasets")
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", root / "retro")
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", root / "seal")
    import flubnf.settings as settings_mod
    monkeypatch.setattr(settings_mod, "HUB", root / "hub")
    monkeypatch.delenv("FLUBNF_PROTECT_ROOTS", raising=False)
    monkeypatch.delenv(VAR, raising=False)
    monkeypatch.delenv(NO_CODEGEN, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
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
    yield {"root": root, "cache": root / "engine-cache" / "bngsim-codegen",
           "home": home, "tmp": tmp_path}
    ui_state._status.clear(); ui_state._status.update(status)
    ui_state._sandbox_status.clear(); ui_state._sandbox_status.update(sbx)
    ui_retro_seasons._retro_status.clear()
    ui_retro_seasons._retro_status.update(retro_st)
    ui_retro_prep._results_jobs.clear()
    ui_shared._invalidate_scans()


@pytest.fixture
def live_runner(tmp_path):
    """A live process whose command line names its runner script."""
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


def _subprocess_env(state_dir: Path) -> dict:
    env = dict(os.environ)
    env["FLUBNF_STATE_DIR"] = str(state_dir)
    env.pop(VAR, None)
    return env


# ------------------------------------- 1. a cache folder it cannot write

def _blocked(state) -> Path:
    """engine-cache made a FILE: no folder can be made under it."""
    block = state["root"] / "engine-cache"
    block.write_text("not a folder", encoding="utf-8")
    return block


def test_a_cache_folder_it_cannot_make_is_said_and_never_handed_to_bngsim(
        state, capsys):
    block = _blocked(state)
    kw = pf.runner_popen_kwargs({}, _os_name="posix", env={"PATH": "x"})
    # left to bngsim's own folder (compiled, as before the cache moved),
    # never pointed at a folder bngsim cannot write
    assert VAR not in kw["env"]
    said = pf.codegen_cache_warning()
    assert str(state["cache"]) in said
    assert "could not write the engine cache folder" in said
    assert OWN in said
    # said on the console's own output, once however many runners start
    assert capsys.readouterr().err.count("could not write") == 1
    pf.runner_popen_kwargs({}, _os_name="posix", env={"PATH": "x"})
    assert capsys.readouterr().err == ""
    # Storage shows it, though no cache is on disk to list
    sec = _section(client.get("/storage").text)
    assert 'id="st-ec-warn"' in sec and OWN in sec
    assert "Compiled models" not in sec
    # fixed: the next launch uses the folder again, and the word goes
    block.unlink()
    kw = pf.runner_popen_kwargs({}, _os_name="posix", env={"PATH": "x"})
    assert kw["env"][VAR] == str(state["cache"])
    assert state["cache"].is_dir()
    assert pf.codegen_cache_warning() == ""
    assert 'id="st-ec-warn"' not in client.get("/storage").text


@pytest.mark.skipif(not POSIX_USER, reason="POSIX permissions, not as root")
def test_a_read_only_cache_folder_is_said_in_its_own_words(state):
    state["cache"].mkdir(parents=True)
    state["cache"].chmod(0o555)
    try:
        kw = pf.runner_popen_kwargs({}, _os_name="posix", env={"PATH": "x"})
        assert VAR not in kw["env"]
        assert "PermissionError" in pf.codegen_cache_warning()
        assert pf.codegen_cache_problem(state["cache"]).startswith(
            "PermissionError")
    finally:
        state["cache"].chmod(0o755)
    assert pf.codegen_cache_problem(state["cache"]) == ""


def test_a_full_disk_is_said(state, monkeypatch):
    import errno

    def full(*a, **k):
        raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(pf.tempfile, "mkstemp", full)
    kw = pf.runner_popen_kwargs({}, _os_name="posix", env={"PATH": "x"})
    assert VAR not in kw["env"]
    assert "No space left on device" in pf.codegen_cache_warning()


def test_with_code_generation_off_nothing_is_made_or_said(state):
    _blocked(state)
    kw = pf.runner_popen_kwargs({}, _os_name="posix",
                                env={"PATH": "x", NO_CODEGEN: "1"})
    assert kw["env"][VAR] == str(state["cache"])     # as before: harmless
    assert pf.codegen_cache_warning() == ""
    # Windows: bngsim compiles nothing, so nothing is made there either
    (state["root"] / "engine-cache").unlink()
    kw = pf.runner_popen_kwargs({}, _os_name="nt", env={"PATH": "x"})
    assert kw["env"][VAR] == str(state["cache"])
    assert not state["cache"].exists()


def test_a_folder_someone_set_is_neither_made_nor_tested(state, tmp_path):
    theirs = tmp_path / "theirs" / "codegen"
    kw = pf.runner_popen_kwargs({}, _os_name="posix",
                                env={"PATH": "x", VAR: str(theirs)})
    assert kw["env"][VAR] == str(theirs) and not theirs.exists()
    assert not state["cache"].exists()


# ------------------------- 2. the cache's holders, in the state folder

def test_runners_are_recorded_beside_the_cache_and_dropped_when_done(
        state, tmp_path):
    reg = tmp_path / "pf_runners.json"
    a = types.SimpleNamespace(pid=os.getpid(),
                              args=["py", "/w/pf_runner_0.py"])
    pf.record_runner_pids([a], path=reg)
    holders = state["root"] / "engine-cache" / "runners.json"
    assert json.loads(holders.read_text())[str(os.getpid())]["runner"] == (
        "/w/pf_runner_0.py")
    assert holders in reclaim.runner_registries()
    pf.unrecord_runner_pids([a], path=reg)
    assert json.loads(holders.read_text()) == {}
    assert json.loads(reg.read_text()) == {}


def test_a_holder_left_by_a_killed_run_goes_at_the_next_record(state):
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait(timeout=60)
    holders = state["root"] / "engine-cache" / "runners.json"
    holders.parent.mkdir(parents=True)
    holders.write_text(json.dumps({str(dead.pid): {
        "pgid": dead.pid, "runner": "/w/pf_runner_3.py"}}))
    me = types.SimpleNamespace(pid=os.getpid(),
                               args=["py", "/w/pf_runner_0.py"])
    pf.record_runner_pids([me], path=state["tmp"] / "reg.json")
    assert set(json.loads(holders.read_text())) == {str(os.getpid())}


def test_another_checkouts_runner_on_the_same_state_folder_keeps_the_cache(
        state, live_runner, tmp_path):
    """A second checkout's console (its own app/state registry, the same
    FLUBNF_STATE_DIR) records a live runner: this console sees it, through
    the holders beside the cache, and clears nothing."""
    b = _fill(state["cache"])
    proc, script = live_runner
    other_registry = tmp_path / "other-checkout" / "app" / "state" / (
        "pf_runners.json")
    code = (
        "import sys, types; sys.path.insert(0, %r)\n"
        "from pathlib import Path\n"
        "from app.core.engines import pf\n"
        "pf.RUNNER_PIDS_FILE = Path(%r)\n"
        "pf.record_runner_pids([types.SimpleNamespace(pid=%d, "
        "args=[sys.executable, %r])])\n"
        % (str(REPO), str(other_registry), proc.pid, str(script)))
    out = subprocess.run([sys.executable, "-c", code],
                         env=_subprocess_env(state["root"]),
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert str(proc.pid) in json.loads(other_registry.read_text())
    # this console's own registries hold nothing of it
    assert reclaim.engine_runners_live(
        [Path(pf.RUNNER_PIDS_FILE)]) == 0
    # the cache's holders do
    assert reclaim.engine_runners_live() == 1
    got = reclaim.clear_codegen_cache()
    assert got["busy"] and "1 engine runner is fitting" in got["refused"]
    assert reclaim.codegen_cache_bytes() == b
    assert ui_storage()["engine_cache"]["busy"]


def test_a_runner_in_its_registry_and_beside_the_cache_counts_once(
        state, live_runner):
    """This console's runner is in its own registry and in the cache's
    holders: Storage says one runner, not two."""
    proc, script = live_runner
    pf.record_runner_pids([types.SimpleNamespace(
        pid=proc.pid, args=[sys.executable, str(script)])])
    assert str(proc.pid) in json.loads(
        Path(pf.RUNNER_PIDS_FILE).read_text())
    assert str(proc.pid) in json.loads(
        pf.codegen_holders_file().read_text())
    assert reclaim.engine_runners_live() == 1
    assert reclaim.codegen_cache_refusal() == (
        "1 engine runner is fitting on this computer")


def test_the_takeover_registry_stays_with_its_checkouts_app_pid(tmp_path):
    """The sweep (flubnf/cli.py) and the registry agree whatever
    FLUBNF_STATE_DIR says, so one checkout's launch never sweeps another's
    live fits; only the cache's holders follow the state folder."""
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from app.core.engines import pf\n"
        "from flubnf import cli\n"
        "print(pf.RUNNER_PIDS_FILE == cli.PF_RUNNER_PIDS_FILE)\n"
        "print(pf.codegen_holders_file())\n" % str(REPO))
    out = subprocess.run([sys.executable, "-c", code],
                         env=_subprocess_env(tmp_path / "moved"),
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    same, holders = out.stdout.strip().splitlines()[-2:]
    assert same == "True"
    assert Path(holders) == tmp_path / "moved" / "engine-cache" / (
        "runners.json")


# ------------------------------------- 3. one registry update at a time

def _slow_writes(monkeypatch, wait: float) -> None:
    real = pf._write_registry

    def slow(path, reg):
        time.sleep(wait)
        real(path, reg)
    monkeypatch.setattr(pf, "_write_registry", slow)


def test_two_threads_recording_at_once_lose_no_runner(state, tmp_path,
                                                      monkeypatch):
    reg = tmp_path / "pf_runners.json"
    _slow_writes(monkeypatch, 0.3)
    go = threading.Barrier(2)

    def record(pid):
        go.wait()
        pf.record_runner_pids([types.SimpleNamespace(
            pid=pid, args=["py", f"/w/pf_runner_{pid}.py"])], path=reg)
    ts = [threading.Thread(target=record, args=(pid,))
          for pid in (424242, 434343)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=30)
    assert set(json.loads(reg.read_text())) == {"424242", "434343"}


_RECORDER = """
import sys, time, types
from pathlib import Path
sys.path.insert(0, {repo!r})
from app.core.engines import pf
real = pf._write_registry
def slow(path, reg):
    time.sleep(1.0)
    real(path, reg)
pf._write_registry = slow
go = Path({go!r})
while not go.exists():
    time.sleep(0.01)
pf.record_runner_pids([types.SimpleNamespace(
    pid={pid}, args=[sys.executable, "/w/pf_runner_{pid}.py"])],
    path=Path({reg!r}))
"""


def test_two_processes_recording_at_once_lose_no_runner(tmp_path):
    """Two consoles (or a console and a terminal replay) record their
    runners in one registry within the same second: both stay."""
    reg = tmp_path / "pf_runners.json"
    go = tmp_path / "go"
    procs = [subprocess.Popen(
        [sys.executable, "-c", _RECORDER.format(
            repo=str(REPO), go=str(go), pid=pid, reg=str(reg))],
        env=_subprocess_env(tmp_path / "state"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for pid in (525252, 535353)]
    time.sleep(3.0)                     # both imported and waiting
    go.write_text("go")
    for p in procs:
        _out, err = p.communicate(timeout=120)
        assert p.returncode == 0, err
    assert set(json.loads(reg.read_text())) == {"525252", "535353"}


def test_a_registry_lock_that_cannot_be_had_never_holds_a_run(
        state, tmp_path, monkeypatch):
    reg = tmp_path / "pf_runners.json"
    monkeypatch.setattr(pf, "_lock_file", lambda fd, wait: False)
    pf.record_runner_pids([types.SimpleNamespace(
        pid=616161, args=["py", "/w/pf_runner_0.py"])], path=reg)
    assert set(json.loads(reg.read_text())) == {"616161"}


# ----------------------------------------- 4. a protected cache folder

def ui_storage() -> dict:
    from app.ui.routes import storage
    return storage._storage_inventory()


def test_a_protected_cache_has_no_delete_and_reclaim_leaves_it_out(
        state, monkeypatch):
    b = _fill(state["cache"])
    monkeypatch.setenv("FLUBNF_PROTECT_ROOTS", str(state["root"]))
    row = ui_storage()["engine_cache"]
    assert row["protected"] and not row["busy"]
    sec = _section(client.get("/storage").text)
    assert "Compiled models" in sec and "protected" in sec
    assert 'value="engine-cache"' not in sec           # no Delete
    assert 'id="reclaim-btn"' not in client.get("/storage").text
    d = client.get("/api/storage/reclaim").json()
    assert not [c for c in d["categories"] if c.get("key") == "engine-cache"]
    assert d["total"] == 0
    client.post("/storage/reclaim", data={"confirm": d["confirm"]},
                follow_redirects=False)
    assert _flash() == "Nothing to reclaim."            # not "Reclaimed 0 B"
    ui_state._status.update({"flash": "", "flash_detail": ""})
    client.post("/storage/delete", data={
        "kind": "engine-cache", "ident": "bngsim-codegen",
        "confirm": "bngsim-codegen"}, follow_redirects=False)
    assert _flash() == ("Not deleted: that folder is protected; the console "
                        "never deletes it.")
    assert reclaim.codegen_cache_bytes() == b


# ------------------------------------------ 5. only the cache on disk

def test_only_the_cache_on_disk_reads_as_the_cache_with_reclaim(state):
    html = client.get("/storage").text
    assert "Nothing stored yet" in _summary(html)       # nothing at all
    assert 'id="reclaim-btn"' not in html
    b = _fill(state["cache"], n=2, size=8192)
    ui_shared._invalidate_scans()
    html = client.get("/storage").text
    summary = _summary(html)
    assert "Nothing stored yet" not in summary
    row = ui_storage()["engine_cache"]
    assert row["size_h"] in summary and "engine cache" in summary
    assert 'id="reclaim-btn"' in html
    assert 'id="st-lg"' not in html                     # no empty legend
    # and the button's report offers the cache
    d = client.get("/api/storage/reclaim").json()
    assert [c["bytes"] for c in d["categories"]
            if c.get("key") == "engine-cache"] == [b]


# --------------------- 6. bngsim's own folder, and a linked cache folder

def test_bngsims_own_folder_is_said_to_be_left_where_it_is(state):
    _fill(state["cache"])
    sec = _section(client.get("/storage").text)
    assert "Earlier versions kept them" not in sec      # none in this home
    (state["home"] / ".cache" / "bngsim" / "codegen").mkdir(parents=True)
    ui_shared._invalidate_scans()
    sec = _section(client.get("/storage").text)
    assert ("Earlier versions kept them in ~/.cache/bngsim/codegen; FluBNF "
            "leaves that folder where it is") in sec
    assert (state["home"] / ".cache" / "bngsim" / "codegen").is_dir()


@pytest.mark.skipif(os.name != "posix", reason="a symlink needs POSIX here")
def test_a_linked_cache_folder_gets_a_row_with_no_delete(state, tmp_path):
    elsewhere = tmp_path / "other-disk" / "codegen"
    b = _fill(elsewhere, n=2)
    state["cache"].parent.mkdir(parents=True)
    state["cache"].symlink_to(elsewhere, target_is_directory=True)
    row = ui_storage()["engine_cache"]
    assert row["linked"] == os.path.realpath(elsewhere)
    assert row["bytes"] == b and not row["busy"]
    html = client.get("/storage").text
    sec = _section(html)
    assert "Compiled models" in sec and "linked" in sec
    assert f"A link to {os.path.realpath(elsewhere)}" in sec
    assert 'value="engine-cache"' not in sec           # no Delete
    assert 'id="reclaim-btn"' not in html
    d = client.get("/api/storage/reclaim").json()
    assert not [c for c in d["categories"] if c.get("key") == "engine-cache"]
    # a runner's launch writes through the link, and nothing is said
    kw = pf.runner_popen_kwargs({}, _os_name="posix", env={"PATH": "x"})
    assert kw["env"][VAR] == str(state["cache"])
    assert pf.codegen_cache_warning() == ""
    assert sorted(p.name for p in elsewhere.iterdir()) == [
        "rhs_0000000000000000.dylib", "rhs_0000000000000001.dylib"]
