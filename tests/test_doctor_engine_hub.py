"""`flubnf doctor` on a two-venv install, and its FluSight hub check.

The engine (pybnf + bngsim) lives in its own venv, so the doctor must probe
it with the ENGINE python, the way the console does, and never by importing
pybnf in the console venv. An absent engine is a WARN: the console runs
Groundhog-only without it. The hub clone (FLUBNF_HUB) must hold target-data/
and auxiliary-data/target-data-archive/.
"""
from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pytest

from flubnf import doctor, settings
from app.core.engines import pf as pf_engine


@pytest.fixture
def engine(tmp_path, monkeypatch):
    """A fake two-venv install: an engine python and a fork checkout that
    carries pybnf/pf.py and a patched algorithms.py."""
    py = tmp_path / "engine" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("")
    fork = tmp_path / "PyBNF-pf"
    (fork / "pybnf").mkdir(parents=True)
    (fork / "pybnf" / "pf.py").write_text("")
    (fork / "pybnf" / "algorithms.py").write_text("x = np.inf\n")
    monkeypatch.setattr(settings, "PY_ENGINE", py)
    monkeypatch.setattr(settings, "PYBNF", fork)
    monkeypatch.setattr(pf_engine, "PYBNF_PF", fork)
    monkeypatch.setattr(pf_engine, "engine_current", lambda: True)
    return SimpleNamespace(py=py, fork=fork)


def _no_pybnf_in_console(monkeypatch):
    """This (console) venv has no pybnf: importing it must not be how the
    doctor decides anything."""
    monkeypatch.setitem(sys.modules, "pybnf", None)
    monkeypatch.setitem(sys.modules, "pybnf.algorithms", None)


def _fake_run(calls, returncode=0, stdout="1.2.3\n", stderr=""):
    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
    return run


def test_engine_probe_runs_the_consoles_import_with_the_engine_python(
        engine, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_run(calls))
    res = doctor._check_engine_venv()
    assert res.status is doctor.Status.OK, res
    assert "1.2.3" in res.detail
    (cmd,) = calls
    assert cmd[0] == str(engine.py)
    probe = cmd[-1]
    assert "import bngsim" in probe
    assert "from pybnf.pf import ParticleFilter" in probe
    assert repr(str(engine.fork)) in probe      # the fork on sys.path


def test_engine_import_failure_is_a_fail(engine, monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        _fake_run([], returncode=1, stdout="",
                                  stderr="ModuleNotFoundError: bngsim"))
    res = doctor._check_engine_venv()
    assert res.status is doctor.Status.FAIL
    assert "bngsim" in res.detail


def test_absent_engine_is_a_warn_not_a_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PY_ENGINE", tmp_path / "no" / "python")
    monkeypatch.setattr(settings, "PYBNF", tmp_path / "no-fork")
    monkeypatch.setattr(pf_engine, "PYBNF_PF", tmp_path / "no-fork")
    _no_pybnf_in_console(monkeypatch)
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_run(calls))
    for check in (doctor._check_engine_venv, doctor._check_pf_engine,
                  doctor._check_numpy2_pybnf):
        res = check()
        assert res.status is doctor.Status.WARN, res
        assert "Groundhog" in res.hint
    assert calls == []


def test_two_venv_install_passes_without_pybnf_in_the_console_venv(
        engine, monkeypatch):
    _no_pybnf_in_console(monkeypatch)
    monkeypatch.setattr(subprocess, "run", _fake_run([]))
    assert doctor._check_engine_venv().status is doctor.Status.OK
    assert doctor._check_pf_engine().status is doctor.Status.OK
    res = doctor._check_numpy2_pybnf()
    assert res.status is doctor.Status.OK, res


def test_numpy2_check_reads_the_engine_fork(engine, monkeypatch):
    _no_pybnf_in_console(monkeypatch)
    import numpy as np
    if int(np.__version__.split(".")[0]) < 2:
        pytest.skip("numpy<2: the patch check short-circuits")
    (engine.fork / "pybnf" / "algorithms.py").write_text("x = np.Inf\n")
    res = doctor._check_numpy2_pybnf()
    assert res.status is doctor.Status.FAIL
    assert "np.Inf" in res.detail


def test_numpy2_check_leaves_the_fork_alone_on_the_public_engine(
        engine, tmp_path, monkeypatch):
    _no_pybnf_in_console(monkeypatch)
    (engine.fork / "pybnf" / "algorithms.py").write_text("x = np.Inf\n")
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    for fork in (engine.fork, tmp_path / "no-fork"):    # unpatched, absent
        monkeypatch.setattr(settings, "PYBNF", fork)
        res = doctor._check_numpy2_pybnf()
        assert res.status is doctor.Status.OK, res
        assert res.detail == ("not used: the public engine runs "
                              "lanl/PyBNF's job_type = lwf")
        row = doctor._check_pf_engine()
        assert row.status is doctor.Status.OK, row
        # the switch is the platform's own: ./setup_engine.sh --private,
        # or setup.ps1 -Engine private on Windows
        from app.core import engine_build
        step = engine_build.switch_step("private", short=True)
        said = (f"installed at {fork}" if fork == engine.fork else
                f"not installed (needed only after {step})")
        assert row.detail == ("the private engine (the fallback), not used "
                              f"here: {said}")
    # the private engine's check is as before
    monkeypatch.setenv("FLUBNF_ENGINE", "private")
    monkeypatch.setattr(settings, "PYBNF", tmp_path / "no-fork")
    assert doctor._check_numpy2_pybnf().status is doctor.Status.WARN
    import numpy as np
    if int(np.__version__.split(".")[0]) >= 2:
        monkeypatch.setattr(settings, "PYBNF", engine.fork)
        assert doctor._check_numpy2_pybnf().status is doctor.Status.FAIL


# --- the engine row (W8): which engine runs, and where the choice comes from

@pytest.fixture
def install(tmp_path, monkeypatch):
    """An install folder with no record, FLUBNF_ENGINE unset, POSIX; the
    runner's check reads the same folder's record."""
    from app.core import runner
    from app.core import sandbox as sb
    root = tmp_path / "install"
    root.mkdir()
    monkeypatch.delenv("FLUBNF_ENGINE", raising=False)
    monkeypatch.setattr(settings, "INSTALL_ROOT", root)
    monkeypatch.setattr(settings, "_windows", lambda: False)
    monkeypatch.setattr(sb, "REPO", root)
    monkeypatch.setattr(runner, "_recorded_engine",
                        lambda: settings.recorded_engine(root))
    settings.forget_record()
    yield root
    settings.forget_record()


def test_the_engine_row_says_the_default(install):
    res = doctor._check_engine_choice()
    assert (res.status, res.detail) == (
        doctor.Status.OK, "public (the default): lanl/PyBNF's job_type = lwf")


def test_the_engine_row_names_where_private_comes_from(install, monkeypatch):
    (install / ".flubnf.env").write_text("export FLUBNF_ENGINE=private\n")
    res = doctor._check_engine_choice()
    assert (res.status, res.detail) == (
        doctor.Status.OK, "private (the fallback, FLUBNF_ENGINE=private from "
        ".flubnf.env): the lab's PyBNF fork, fit_type = pf")
    settings.forget_record()
    (install / ".flubnf.env").unlink()
    monkeypatch.setenv("FLUBNF_ENGINE", "private")
    res = doctor._check_engine_choice()
    assert (res.status, res.detail) == (
        doctor.Status.OK, "private (the fallback, FLUBNF_ENGINE=private from "
        "the environment): the lab's PyBNF fork, fit_type = pf")
    # Windows: setup.ps1 -Engine private's record
    monkeypatch.delenv("FLUBNF_ENGINE")
    monkeypatch.setattr(settings, "_windows", lambda: True)
    settings.forget_record()
    (install / ".flubnf.env.cmd").write_bytes(
        b'@echo off\r\nset "FLUBNF_ENGINE=private"\r\n')
    assert "from .flubnf.env.cmd)" in doctor._check_engine_choice().detail


@pytest.mark.parametrize("where", ["environment", "record"])
def test_an_unknown_engine_value_is_a_warn_and_runs_public(install,
                                                           monkeypatch, where):
    if where == "environment":
        monkeypatch.setenv("FLUBNF_ENGINE", "pubic")
    else:
        (install / ".flubnf.env").write_text("export FLUBNF_ENGINE=pubic\n")
    res = doctor._check_engine_choice()
    assert res.status is doctor.Status.WARN, res
    assert res.detail == ('FLUBNF_ENGINE is "pubic", which names no engine: '
                          "the public engine, the default, runs")
    assert "./setup_engine.sh --public" in res.hint
    assert "./setup_engine.sh --private" in res.hint
    assert settings.engine_choice() == "public"


def test_an_environment_that_names_the_other_engine_is_a_warn(install,
                                                              monkeypatch):
    (install / ".flubnf.env").write_text("export FLUBNF_ENGINE=private\n")
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    res = doctor._check_engine_choice()
    assert res.status is doctor.Status.WARN, res
    assert res.detail == (
        "this install records FLUBNF_ENGINE=private (.flubnf.env) but this "
        "Terminal runs the public engine: run `. ./.flubnf.env` in the clone "
        "first")


def test_the_engine_row_comes_first(install, monkeypatch):
    for name in dir(doctor):                 # every other check a stand-in
        if name.startswith("_check_") and name != "_check_engine_choice":
            monkeypatch.setattr(
                doctor, name, lambda *a, _n=name, **k: doctor.CheckResult(
                    _n, doctor.Status.OK, ""))
    monkeypatch.setattr(doctor, "_check_imports", lambda: [])
    rep = doctor.run_doctor()
    assert rep.checks[0].name == "engine"
    assert rep.checks[0].detail.startswith("public (the default)")


def _hub(tmp_path, *dirs):
    hub = tmp_path / "FluSight-forecast-hub"
    hub.mkdir()
    for d in dirs:
        (hub / d).mkdir(parents=True)
    return hub


def test_hub_missing_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "HUB", tmp_path / "nope")
    res = doctor._check_hub()
    assert res.status is doctor.Status.FAIL
    assert "FLUBNF_HUB" in res.hint


def test_hub_without_the_data_directories_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "HUB", _hub(tmp_path, "target-data"))
    res = doctor._check_hub()
    assert res.status is doctor.Status.FAIL
    assert "auxiliary-data/target-data-archive" in res.detail


def test_hub_with_both_data_directories_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "HUB", _hub(
        tmp_path, "target-data", "auxiliary-data/target-data-archive"))
    assert doctor._check_hub().status is doctor.Status.OK


def test_run_doctor_reports_the_hub(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "HUB", tmp_path / "nope")
    monkeypatch.setattr(subprocess, "run", _fake_run([]))
    rep = doctor.run_doctor()
    hub = [c for c in rep.checks if c.name == "FluSight hub"]
    assert hub and hub[0].status is doctor.Status.FAIL
