"""Suite-wide isolation: no test may touch or depend on the real install.

  * pf.RUNNER_PIDS_FILE -> tmp: a real relaunch sweeps the pids recorded in
    app/state/pf_runners.json, so test pids must never land there.
  * pf.PYBNF_PF -> a stub fork: prepare() refuses fit_type = pf without
    pybnf/pf.py (CI has no fork); preflight tests override PYBNF_PF.
  * app/state -> a temp folder for the whole session, set HERE at import,
    before any test module imports the server: its startup thread writes
    component_versions.json and routes open ledger.sqlite, which landed in
    the working tree's app/state. Tests that set their own APP_STATE still
    do; the session ends by checking app/state was left untouched.
"""
import atexit
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import runs as _runs                       # noqa: E402

REAL_STATE = Path(_runs.APP_STATE)
#: the suite's own state folder (runs.APP_STATE and everything derived
#: from it at call time: the ledger, workroots, archive)
TEST_STATE = Path(tempfile.mkdtemp(prefix="flubnf-test-state-"))
atexit.register(shutil.rmtree, TEST_STATE, True)
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


@pytest.fixture(scope="session", autouse=True)
def _app_state_untouched():
    """The whole suite leaves the working tree's app/state as it found it."""
    before = _state_listing()
    yield
    after = _state_listing()
    changed = sorted(k for k in set(before) | set(after)
                     if before.get(k) != after.get(k))
    assert not changed, f"tests wrote into {REAL_STATE}: {changed[:10]}"


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
    'ABORT: bad rule'). The per-file `box` fixtures layer on this."""
    import types
    from app.core import sandbox as sb
    from app.ui import state as ui_state
    root = tmp_path / "sandbox"
    monkeypatch.setattr(sb, "SANDBOX", root)
    monkeypatch.setattr(sb, "MODELS", root / "models")
    monkeypatch.setattr(sb, "RUNS", root / "runs")
    monkeypatch.setattr(pf, "perl_available", lambda: True)

    def fake_netgen(cmd, **kw):
        cwd = Path(kw.get("cwd", "."))
        if "broken" not in (cwd / "m.bngl").read_text():
            (cwd / "m.net").write_text("# net\n")
        return types.SimpleNamespace(stdout="ABORT: bad rule\n", stderr="",
                                     returncode=0)
    monkeypatch.setattr(sb.subprocess, "run", fake_netgen)
    ui_state._status["running"] = None
    ui_state._status.pop("flash", None)
    return root
