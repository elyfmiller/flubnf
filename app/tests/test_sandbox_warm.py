"""The Sandbox's part of the console's startup warm (UX review F15,
package P11): sandbox.warm_probes starts the probes a model page waits
for (the public engine's lock check, or the private engine's import
probe, and BNG2.pl's self-test) without waiting for the engine's and
without making a folder, so the first /sandbox?model=<m> after launch
starts no probe of its own. server._start_background_warm calls it last,
through routes/sandbox.py _sandbox_warm, which does nothing under pytest
(the suite imports the server before its fakes are set).

No probe is real here: the engine-import probe and BNG2.pl's self-test go
through a counting sandbox._probe_run, and the public engine's lock check
through a counting subprocess.run. Timing is not measured (a loaded
computer makes a wall-clock bound flaky): a probe that would start is
counted instead.
"""
import subprocess
import sys
import threading
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import lwf                         # noqa: E402
from app.core.engines import pf                          # noqa: E402
from app.ui import server as srv                         # noqa: E402
from app.ui import shared as ui_shared                   # noqa: E402
from app.ui import state as ui_state                     # noqa: E402
from app.ui import versions as ui_versions               # noqa: E402
from app.ui.routes import sandbox as ui_sandbox          # noqa: E402

client = TestClient(srv.app)
#: the probes as written (sandbox_root answers "ready" for both)
REAL_IMPORT_PROBLEM = sb.engine_import_problem
REAL_BNG_PROBLEM = sb.bng_problem
MODEL = "/sandbox?model=kinetics_example"


def _join(prefix: str) -> None:
    """Every thread whose name starts with `prefix`, ended."""
    for t in [t for t in threading.enumerate() if t.name.startswith(prefix)]:
        t.join(30)
        assert not t.is_alive(), t.name


@pytest.fixture
def probes(sandbox_root, tmp_path, monkeypatch):
    """sandbox_root with the real engine-import probe and BNG2.pl checks,
    nothing remembered, a BNG2.pl file there, and every probe a process
    would start counted and answered "fine" instead: a list of argv."""
    monkeypatch.setattr(sb, "engine_import_problem", REAL_IMPORT_PROBLEM)
    monkeypatch.setattr(sb, "bng_problem", REAL_BNG_PROBLEM)
    monkeypatch.setattr(sb, "_ENGINE_PROBES", {})
    monkeypatch.setattr(sb, "_BNG_SELFTESTS", {})
    bng = tmp_path / "bng" / "BNG2.pl"
    bng.parent.mkdir()
    bng.write_text("# stub\n")
    monkeypatch.setattr(sb, "BNG", str(bng))
    # the perl a self-test names, and BioNetGen's environment, without the
    # Windows search for a perl (a process per candidate)
    monkeypatch.setattr(pf, "resolve_perl", lambda *a, **k: "perl")
    monkeypatch.setattr(sb, "bng_env", lambda *a, **k: None)
    calls = []

    def probe(cmd, **kw):
        calls.append(list(cmd))
        out = ("BioNetGen version 2.9.3\n" if cmd[-1] == "-v" else "0.15.1\n")
        return types.SimpleNamespace(returncode=0, stdout=out, stderr="")
    monkeypatch.setattr(sb, "_probe_run", probe)
    return calls


@pytest.fixture
def public(probes, tmp_path, monkeypatch):
    """probes on the public engine: its venv's Python there, the lock
    check's process counted and answered "matches" (a list of argv)."""
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", sys.executable)
    monkeypatch.setattr(lwf, "_CHECK", {})
    monkeypatch.setattr(lwf, "_PENDING", {})
    checks = []

    def run(cmd, **kw):
        if any(str(c).endswith("engine_lock.py") for c in cmd):
            checks.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, "ok: matches\n", "")
        raise AssertionError(f"an unexpected process: {cmd}")
    monkeypatch.setattr(lwf.subprocess, "run", run)
    return checks


def test_after_the_warm_the_first_model_page_starts_no_probe(probes):
    sb.warm_probes()
    _join("flubnf-engine-probe")
    # the private engine's import probe (on its thread) and BNG2.pl's
    # self-test, once each
    assert sorted(c[1] for c in probes) == sorted(["-c", sb.BNG])
    assert [c[0] for c in probes if c[1] == "-c"] == [str(pf.PY310)]
    # no folder made
    assert not sb.SANDBOX.exists()
    sb.add_example("kinetics_example")
    html = client.get(MODEL).text
    assert 'id="sb-machine"' not in html               # ready here
    assert len(probes) == 2                            # nothing new started


def test_without_the_warm_the_first_model_page_starts_them(probes):
    """The control: the page's own look starts the same two probes."""
    sb.add_example("kinetics_example")
    client.get(MODEL)
    _join("flubnf-engine-probe")
    assert sorted(c[1] for c in probes) == sorted(["-c", sb.BNG])


def test_on_the_public_engine_the_lock_check_is_warmed(public, probes):
    sb.warm_probes()
    _join("flubnf-public-lock-check")
    assert len(public) == 1                            # the lock check
    assert [c[-1] for c in probes] == ["-v"]           # BNG2.pl's self-test
    assert not sb.SANDBOX.exists()
    sb.add_example("kinetics_example")
    html = client.get(MODEL).text
    assert 'id="sb-machine"' not in html
    assert len(public) == 1 and len(probes) == 1       # nothing new started


def test_without_the_engine_nothing_is_started(probes, monkeypatch):
    monkeypatch.setattr(pf, "engine_available", lambda: False)
    sb.warm_probes()
    assert probes == [] and sb._ENGINE_PROBES == {} and lwf._PENDING == {}
    assert not [t for t in threading.enumerate() if t.name in (
        "flubnf-engine-probe", "flubnf-public-lock-check")]
    # the page says so without one
    sb.add_example("kinetics_example")
    html = client.get(MODEL).text
    assert 'id="sb-machine"' in html


def test_a_failing_probe_never_reaches_the_warm(probes, monkeypatch):
    def broken(cmd, **kw):
        raise OSError("no such program")
    monkeypatch.setattr(sb, "_probe_run", broken)
    monkeypatch.setattr(sb, "bng_selftest", lambda: 1 / 0)
    sb.warm_probes()                                   # says nothing


def test_the_startup_warm_ends_with_the_sandbox(monkeypatch):
    """server._start_background_warm's thread calls _sandbox_warm last;
    under pytest that does nothing, and outside it compiles sandbox.html
    and starts the probes."""
    order = []
    monkeypatch.setattr(ui_versions, "_warm_versions",
                        lambda: order.append("versions"))

    def no_results():
        raise LookupError("no run here")
    monkeypatch.setattr(ui_shared, "_latest_results", no_results)
    monkeypatch.setattr(ui_state.data_mod, "vintages", lambda: [])
    monkeypatch.setattr(ui_sandbox, "_sandbox_warm",
                        lambda: order.append("sandbox"))
    srv._start_background_warm()
    _join("flubnf-startup-warm")
    assert order == ["versions", "sandbox"]


def test_the_sandbox_warm_runs_outside_pytest_only(monkeypatch):
    warmed, compiled = [], []
    monkeypatch.setattr(sb, "warm_probes", lambda: warmed.append(1))
    real = ui_sandbox.templates.env.get_template

    def get(name, *a, **k):
        compiled.append(name)
        return real(name, *a, **k)
    monkeypatch.setattr(ui_sandbox.templates.env, "get_template", get)
    ui_sandbox._sandbox_warm()
    assert warmed == [] and compiled == []
    with monkeypatch.context() as m:
        m.delitem(sys.modules, "pytest")
        ui_sandbox._sandbox_warm()
    assert warmed == [1] and compiled == ["sandbox.html"]
