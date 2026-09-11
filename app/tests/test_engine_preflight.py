"""The fork path is tested by its pf.py, never by the directory.

A PI's laptop installed the engine from the small archive, the console
reported itself healthy, and the forecast then failed all six particle
filter cells while the analogue worked (lab report, 2026-09-08). The cause
is that the fit runner inserts the fork path at the front of sys.path and
the engine venv also holds a stock PyBNF from PyPI, which has no pf.py and
therefore no fit_type = pf: with a fork path that provides no pf.py the
runner imports the stock package instead and every cell dies with an
opaque configuration error, while Perl, BNG2.pl, network generation and
the .exp all work perfectly. Now the absence is named once, before any
fitting, everywhere the console reports its components.
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core.engines import pf                          # noqa: E402


def _fork(root: Path, with_pf: bool = True) -> Path:
    """A fork checkout at `root`, with or without the file that makes it
    an engine."""
    (root / "pybnf").mkdir(parents=True)
    (root / "pybnf" / "__init__.py").write_text("")
    if with_pf:
        (root / "pybnf" / "pf.py").write_text("# stub\n")
        # the key lists the contract check reads
        (root / "pybnf" / "parse.py").write_text(
            "numkeys_int = [%s]\n" % ", ".join(
                "'%s'" % k for k in pf.CONF_KEYS_REQUIRED))
    return root


# ------------------------------------------------------------ the two tests

def test_a_directory_is_not_an_engine(monkeypatch, tmp_path):
    monkeypatch.setattr(pf, "PYBNF_PF", tmp_path / "no-such-fork")
    assert pf.engine_available() is False
    monkeypatch.setattr(pf, "PYBNF_PF", _fork(tmp_path / "empty",
                                              with_pf=False))
    assert pf.engine_available() is False
    monkeypatch.setattr(pf, "PYBNF_PF", _fork(tmp_path / "real"))
    assert pf.engine_available() is True


def test_the_message_names_the_path_the_file_and_the_fix(monkeypatch,
                                                         tmp_path):
    monkeypatch.setattr(pf, "PYBNF_PF", _fork(tmp_path / "empty",
                                              with_pf=False))
    msg = pf.engine_missing_message()
    assert str(tmp_path / "empty") in msg
    assert "pybnf/pf.py" in msg and "setup_engine.sh" in msg
    assert "holds no pybnf/pf.py" in msg
    # the two other shapes a wrong FLUBNF_PYBNF takes
    monkeypatch.setattr(pf, "PYBNF_PF", tmp_path / "gone")
    assert "no such directory" in pf.engine_missing_message()
    afile = tmp_path / "afile"
    afile.write_text("")
    monkeypatch.setattr(pf, "PYBNF_PF", afile)
    assert "not a directory" in pf.engine_missing_message()
    # the remedy must come before the reason, so a truncated ledger error
    # still tells the reader what to do
    monkeypatch.setattr(pf, "PYBNF_PF", _fork(tmp_path / "empty2",
                                              with_pf=False))
    m = pf.engine_missing_message()
    assert "setup_engine.sh" in m
    # the remedy precedes the explanation, which is the ordering the
    # docstring promises and the only part truncation could take away
    assert m.index("setup_engine.sh") < m.index("stock PyBNF")


# ------------------------------------------------------------ the preflight

class _State:
    def __init__(self):
        import numpy as np
        self.times = np.array([0, 1, 2])
        self.observed = np.array([4.0, 5.0, 6.0])
        self.n_obs = 3
        self.last_week_offset = 2
        self.i0 = 5e-3
        self.rhomult = 0.05


def _spec():
    return type("S", (), {
        "forecast_date": "2098-11-07", "season_start": "2098-08-01",
        "weeks_to_drop": 0, "drop_same_day": False,
        "locations": ["Ohio", "Utah"], "replicates": 1,
        "particles": 100, "jitter": 0.15,
        "observable_mode": "integrated", "extra": None})()


def _env(monkeypatch, tmp_path, netgen):
    import app.core.data as data
    import flubnf.sihrs_fit as sf

    def fake_materialize(s, template, out_path, suffix, extra_tokens=None, **kw):
        p = Path(out_path); p.write_text("begin parameters\nend parameters\n"); return p
    monkeypatch.setattr(sf, "resolve_state", lambda loc, **kw: _State())
    monkeypatch.setattr(sf, "materialize_model", fake_materialize)
    monkeypatch.setattr(sf, "write_exp", lambda s, p: Path(p).write_text("# t v\n"))
    vfile = tmp_path / "vintage.csv"; vfile.write_text("date,location,location_name,value\n")
    monkeypatch.setattr(data, "vintage_path", lambda d: str(vfile))
    monkeypatch.setattr(pf.subprocess, "run", netgen)


def test_prepare_refuses_a_fork_without_pf_py(monkeypatch, tmp_path):
    """Every conf prepare() writes says fit_type = pf, so the fork is a
    run-level fact: named once, before any location is touched."""
    calls = []

    def netgen(cmd, **kw):
        calls.append(cmd)
        (Path(kw["cwd"]) / "m.net").write_text("# net\n")
        return types.SimpleNamespace(stdout="", returncode=0)
    _env(monkeypatch, tmp_path, netgen)
    monkeypatch.setattr(pf.shutil, "which", lambda name: "/usr/bin/perl")
    monkeypatch.setattr(pf, "PYBNF_PF", _fork(tmp_path / "fork",
                                              with_pf=False))
    with pytest.raises(RuntimeError) as err:
        pf.prepare(_spec(), tmp_path / "wr")
    assert str(err.value) == pf.engine_missing_message()
    assert calls == []                       # nothing was attempted per location
    assert not (tmp_path / "wr" / "cells.json").exists()


def test_prepare_runs_when_the_fork_provides_pf_py(monkeypatch, tmp_path):
    def netgen(cmd, **kw):
        (Path(kw["cwd"]) / "m.net").write_text("# net\n")
        return types.SimpleNamespace(stdout="", returncode=0)
    _env(monkeypatch, tmp_path, netgen)
    monkeypatch.setattr(pf.shutil, "which", lambda name: "/usr/bin/perl")
    monkeypatch.setattr(pf, "PYBNF_PF", _fork(tmp_path / "fork"))
    cells = pf.prepare(_spec(), tmp_path / "wr")
    assert [c["key"] for c in cells] == ["Ohio_r0", "Utah_r0"]


# ----------------------------------------------------------- the console gate

def test_the_gate_tells_an_absent_engine_from_a_broken_one(monkeypatch,
                                                           tmp_path):
    from app.ui import server
    from flubnf import settings
    py = tmp_path / "python"
    py.write_text("")

    # nothing installed: the supported analogue-only configuration, and the
    # run must still take the skip path it always did
    monkeypatch.setattr(settings, "PY_ENGINE", tmp_path / "no-venv")
    monkeypatch.setattr(settings, "PYBNF", tmp_path / "no-fork")
    assert server._pf_engine_state() == "absent"

    # installed, and it can filter
    monkeypatch.setattr(settings, "PY_ENGINE", py)
    monkeypatch.setattr(settings, "PYBNF", _fork(tmp_path / "real"))
    monkeypatch.setattr(pf, "PYBNF_PF", tmp_path / "real")
    assert server._pf_engine_state() == "ready"

    # installed, and it cannot: a broken install, not a configuration
    monkeypatch.setattr(settings, "PYBNF", _fork(tmp_path / "half",
                                                 with_pf=False))
    monkeypatch.setattr(pf, "PYBNF_PF", tmp_path / "half")
    assert server._pf_engine_state() == "broken"


def test_the_run_surfaces_name_the_broken_install_in_words(monkeypatch,
                                                           tmp_path):
    """The two surfaces a lab member reads after a failed run: the
    latest-run table and the run chips. Neither may report a broken
    install as "no engine" -- the remedies differ."""
    from app.core.runs import results_html
    from app.ui import server
    monkeypatch.setattr(pf, "PYBNF_PF", _fork(tmp_path / "half",
                                              with_pf=False))
    msg = pf.engine_missing_message()

    table = results_html({"pf_engine_broken": msg}, "{}")
    assert "engine install incomplete" in table
    assert str(tmp_path / "half") in table and "setup_engine.sh" in table

    chips = server._outcome_chips({"pf_engine_broken": msg, "error": msg})
    assert "PF engine install incomplete" in chips

    # an absent engine keeps its own wording
    assert "none (no engine)" in results_html(
        {"pf_skipped": "engine venv not installed (Tier A)"}, "{}")


# ------------------------------------------------------------- doctor + setup

def test_doctor_and_the_setup_check_report_the_fork(monkeypatch, tmp_path):
    from flubnf import doctor, settings

    monkeypatch.setattr(pf, "PYBNF_PF", _fork(tmp_path / "real"))
    monkeypatch.setattr(settings, "PYBNF", tmp_path / "real")
    ok = doctor._check_pf_engine()
    assert ok.status is doctor.Status.OK and str(tmp_path / "real") in ok.detail

    monkeypatch.setattr(pf, "PYBNF_PF", _fork(tmp_path / "half",
                                              with_pf=False))
    monkeypatch.setattr(settings, "PYBNF", tmp_path / "half")
    bad = doctor._check_pf_engine()
    assert bad.status is doctor.Status.FAIL
    assert str(tmp_path / "half") in bad.detail
    assert "setup_engine.sh" in bad.hint

    # the setup table names the file, not the directory, and says why
    rows = {name: (path, why) for name, path, why in settings.check(verbose=False)}
    assert "FLUBNF_PYBNF" in rows
    assert rows["FLUBNF_PYBNF"][0].endswith(str(Path("pybnf") / "pf.py"))
    assert "holds no pybnf/pf.py" in rows["FLUBNF_PYBNF"][1]

    # present: no row at all
    monkeypatch.setattr(settings, "PYBNF", tmp_path / "real")
    assert not any(name == "FLUBNF_PYBNF"
                   for name, _, _ in settings.check(verbose=False))
