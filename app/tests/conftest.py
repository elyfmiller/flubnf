"""Suite-wide isolation: no test may touch or depend on the real install.

  * pf.RUNNER_PIDS_FILE -> tmp: a real relaunch sweeps the pids recorded in
    app/state/pf_runners.json, so test pids must never land there.
  * pf.PYBNF_PF -> a stub fork: prepare() refuses fit_type = pf without
    pybnf/pf.py (CI has no fork); preflight tests override PYBNF_PF.
  * app/state -> a temp folder for the whole session, set HERE at import,
    before any test module imports the server: its startup thread writes
    component_versions.json and routes open ledger.sqlite, which landed in
    the working tree's app/state. FLUBNF_STATE_DIR carries it to every
    Python a test starts with the suite's environment (a `python -c
    "import app.ui.server"` probe has a startup thread too). Tests that set
    their own APP_STATE still do; the session ends by checking app/state
    was left untouched, which also catches a console started from this
    checkout while the suite runs.
  * the FluSight hub -> a missing folder, set HERE at import too
    (FLUBNF_HUB), so every machine runs the suite as CI does: a clone at
    the default path (~/GitHub/FluSight-forecast-hub) made its newest week
    the suite's, and five run tests failed. A test that compares against
    a real clone opts in through FLUBNF_TEST_HUB.
  * the checkout's top folder: the session ends by checking no test left a
    file there (a fake BNG2.pl once wrote m.net beside pyproject.toml).
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pytest                                            # noqa: E402

#: the real state folder, read before the override below
REAL_STATE = REPO / "app" / "state"
#: the suite's own state folder (runs.APP_STATE and everything derived
#: from it at call time: the ledger, workroots, archive), in this process
#: and, through FLUBNF_STATE_DIR, in every process a test starts
TEST_STATE = Path(tempfile.mkdtemp(prefix="flubnf-test-state-"))
atexit.register(shutil.rmtree, TEST_STATE, True)
os.environ["FLUBNF_STATE_DIR"] = str(TEST_STATE)
#: the suite's hub: a folder that never exists, whatever this machine has
#: cloned, here and (through FLUBNF_HUB) in every process a test starts
NO_HUB = TEST_STATE / "no-hub"
os.environ["FLUBNF_HUB"] = str(NO_HUB)

from app.core import runs as _runs                       # noqa: E402

_runs.APP_STATE = TEST_STATE

from app.ui import versions as _versions                 # noqa: E402

# the warm thread persists the version probe here (read at import only)
_versions._VERSIONS_SNAPSHOT = TEST_STATE / "component_versions.json"

from app.core import datasets as _datasets               # noqa: E402

# a module constant computed from the real APP_STATE at its import
if _datasets.ROOT == REAL_STATE / "datasets":
    _datasets.ROOT = TEST_STATE / "datasets"

from app.core.engines import pf                          # noqa: E402


def _state_listing() -> dict:
    """app/state as {relative path: (size, mtime_ns)}; {} when absent."""
    if not REAL_STATE.exists():
        return {}
    out = {}
    for p in REAL_STATE.rglob("*"):
        try:
            st = p.stat()
        except OSError:
            continue
        out[str(p.relative_to(REAL_STATE))] = (
            st.st_size if p.is_file() else -1, st.st_mtime_ns)
    return out


def _top_files() -> set:
    """The checkout's top folder, but for the tools' own dot folders
    (.pytest_cache, .coverage) and __pycache__."""
    return {n for n in os.listdir(REPO)
            if not n.startswith(".") and n != "__pycache__"}


#: taken here, at import (pytest loads this conftest before it collects or
#: runs any test), not in the fixture's setup: CI, the pre-push hook and
#: testpaths run tests/ first, before the first app/tests test
_STATE_BEFORE, _TOP_BEFORE = _state_listing(), _top_files()


@pytest.fixture(scope="session", autouse=True)
def _app_state_untouched():
    """The whole suite leaves the working tree's app/state as it found it,
    and adds nothing to the checkout's top folder."""
    before, top = _STATE_BEFORE, _TOP_BEFORE
    yield
    after = _state_listing()
    changed = sorted(k for k in set(before) | set(after)
                     if before.get(k) != after.get(k))
    assert not changed, f"tests wrote into {REAL_STATE}: {changed[:10]}"
    added = sorted(_top_files() - top)
    assert not added, (f"{REPO} gained {added[:10]} during the run: a test, "
                       "or a command run in the checkout meanwhile (uv run)")


@pytest.fixture(autouse=True)
def _runner_registry_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "RUNNER_PIDS_FILE", tmp_path / "pf_runners.json")


@pytest.fixture(scope="session")
def _engine_root(tmp_path_factory):
    """A fork-shaped directory: the one file the engine preflight looks
    for, built once for the session."""
    root = tmp_path_factory.mktemp("fork")
    (root / "pybnf").mkdir()
    (root / "pybnf" / "pf.py").write_text("# stub: presence is the test\n")
    # the key lists the contract check reads: every key the console writes
    (root / "pybnf" / "parse.py").write_text(
        "numkeys_int = [%s]\n" % ", ".join("'%s'" % k for k in pf.CONF_KEYS_REQUIRED))
    return root


@pytest.fixture(autouse=True)
def _results_grace_waits_for_the_job(monkeypatch):
    """The season page waits _RESULTS_GRACE_S (1.5 s) for its finalize job,
    then renders the preparing state. A slow runner (Windows CI) can overrun
    that, and a page test then read the stub: a wait of up to a minute
    returns as soon as the job is done. Tests of the preparing state set
    their own short grace."""
    from app.ui.routes import retro as _retro_routes
    monkeypatch.setattr(_retro_routes, "_RESULTS_GRACE_S", 60.0)


@pytest.fixture(autouse=True)
def _engine_in_tmp(_engine_root, monkeypatch):
    monkeypatch.setattr(pf, "PYBNF_PF", _engine_root)


@pytest.fixture(autouse=True)
def _sealed_records_in_tmp(tmp_path, monkeypatch):
    """The production record (app/state/retro_reseal) must never be served by
    accident; RETRO_SEAL tests already point at their own trees."""
    from app.ui import server  # noqa: F401  (the app assembled for every test)
    from app.ui import retro_seasons as ui_retro_seasons
    monkeypatch.setattr(ui_retro_seasons, "RETRO_RESEAL",
                        tmp_path / "retro_reseal")


@pytest.fixture(autouse=True)
def _shipped_vintages_in_tmp(tmp_path, monkeypatch):
    """The committed truth snapshots (data/vintages/) stay out of every test
    unless it asks: with the hub pointed at an empty folder the suite
    expects NO weeks, and the eight shipped ones would otherwise appear as
    seasons. Opt in with the `shipped_vintages` fixture."""
    from app.core import data as core_data
    monkeypatch.setattr(core_data, "SHIPPED", tmp_path / "no-shipped")


@pytest.fixture
def pf_engine_ready(monkeypatch):
    """A machine with the particle-filter engine, as the console's up-front
    checks read it (pipeline._pf_engine_state): the Oracle SIHRS's runs and
    replays are then started, not refused. The engine itself stays faked by
    each test (opt-in; the suite's machine has none)."""
    from app.ui import pipeline
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "ready")


@pytest.fixture
def shipped_vintages(monkeypatch):
    """The real committed snapshot folder (opt-in; see the autouse fixture)."""
    from app.core import data as core_data
    from flubnf import vintages as shipped
    monkeypatch.setattr(core_data, "SHIPPED", shipped.VINTAGES_DIR)
    return shipped.VINTAGES_DIR


@pytest.fixture(autouse=True)
def _sandbox_released():
    """The sandbox's engine claim is module state that /run and /retro/run
    refuse on; no test may leak a live sandbox fit into another."""
    from app.ui import state as ui_state
    ui_state._sandbox_status.update(running=None, claim=None, cancel=False)
    yield
    ui_state._sandbox_status.update(running=None, claim=None, cancel=False)


@pytest.fixture
def sandbox_root(tmp_path, monkeypatch):
    """A sandbox rooted in tmp_path with the preflight's Perl present and
    BNG2.pl faked to write m.net (a model containing 'broken' fails with
    'ABORT: bad rule', after BioNetGen's banner as the real one prints
    it). The preflight's two probes that start a process, the engine
    import and BNG2.pl's self-test, answer "ready" (app/tests/
    test_sandbox_machine.py runs them). The per-file `box` fixtures layer
    on this."""
    import types
    from app.core import sandbox as sb
    from app.ui import state as ui_state
    root = tmp_path / "sandbox"
    monkeypatch.setattr(sb, "SANDBOX", root)
    monkeypatch.setattr(sb, "MODELS", root / "models")
    monkeypatch.setattr(sb, "RUNS", root / "runs")
    monkeypatch.setattr(pf, "perl_available", lambda: True)
    # the engine's own Python, which the preflight requires to exist
    monkeypatch.setattr(pf, "PY310", Path(sys.executable))
    monkeypatch.setattr(sb, "engine_import_problem", lambda wait=0: "")
    monkeypatch.setattr(sb, "bng_problem", lambda: "")

    def fake_netgen(cmd, **kw):
        cwd = Path(kw.get("cwd", "."))
        if "broken" not in (cwd / "m.bngl").read_text():
            (cwd / "m.net").write_text("# net\n")
        return types.SimpleNamespace(
            stdout="BioNetGen version 2.9.3\nABORT: bad rule\n", stderr="",
            returncode=0)
    monkeypatch.setattr(sb.subprocess, "run", fake_netgen)
    ui_state._status["running"] = None
    ui_state._status.pop("flash", None)
    # a refused New model form waits for the next page (one-shot)
    from app.ui.routes import sandbox as ui_sandbox
    ui_sandbox._sandbox_new_refused.clear()
    return root
