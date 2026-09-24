"""Suite-wide guards for the app tests.

Two rules, both of the same kind: no test may touch, or depend on, the
developer's real install.

  * The PF engine's takeover registry (the record of live runner process
    groups that a console relaunch may sweep) lives beside the app's real
    state, app/state/pf_runners.json. No test may write there -- the file
    is read by a REAL relaunch, and a test's fake runner pids landing in it
    could aim a sweep at recycled pids on the developer's machine -- so
    every test records into its own temporary file instead.

  * prepare() refuses to write a fit_type = pf configuration when the fork
    path holds no pybnf/pf.py (app/core/engines/pf.py::engine_available).
    Every test that calls it would otherwise pass on the development host,
    which has the fork, and fail in CI, which does not. So the fork is
    faked here for the whole suite; a test about the preflight itself
    points PYBNF_PF at its own directory and wins, being later.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core.engines import pf                          # noqa: E402


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
    """The production record (app/state/retro_reseal) is a real tree on the
    lab machine, preferred by _season_root whenever it has the most weeks;
    no test may serve it by accident. RETRO_SEAL is left as it is because
    every test that needs a seal already points it at its own tree."""
    from app.ui import server as srv
    monkeypatch.setattr(srv, "RETRO_RESEAL", tmp_path / "retro_reseal")


@pytest.fixture(autouse=True)
def _sandbox_released():
    """The sandbox's engine claim is module state that /run and /retro/run
    refuse on; no test may leak a live sandbox fit into another."""
    from app.ui import server as srv
    srv._sandbox_status.update(running=None, claim=None, cancel=False)
    yield
    srv._sandbox_status.update(running=None, claim=None, cancel=False)


@pytest.fixture
def sandbox_root(tmp_path, monkeypatch):
    """A sandbox rooted in tmp_path with the preflight's Perl present and
    BNG2.pl faked to write m.net (a model containing 'broken' fails with
    'ABORT: bad rule'). The per-file `box` fixtures layer on this."""
    import types
    from app.core import sandbox as sb
    from app.ui import server as srv
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
    srv._status["running"] = None
    srv._status.pop("flash", None)
    return root
