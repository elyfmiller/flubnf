"""Perl is what runs BNG2.pl at run preparation. A Windows desktop without
it (lab report, 2026-09-02) failed every location with
'[WinError 2] The system cannot find the file specified', which names
neither the program nor the fix. Now the absence is named once, before any
location, everywhere the console reports its components."""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core.engines import pf                          # noqa: E402


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


def test_missing_perl_is_named_once_before_any_location(monkeypatch, tmp_path):
    calls = []

    def netgen(cmd, **kw):
        calls.append(cmd)
        (Path(kw["cwd"]) / "m.net").write_text("# net\n")
        return types.SimpleNamespace(stdout="", returncode=0)
    _env(monkeypatch, tmp_path, netgen)
    monkeypatch.setattr(pf.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError) as err:
        pf.prepare(_spec(), tmp_path / "wr")
    msg = str(err.value)
    assert "Perl was not found on PATH" in msg and "BNG2.pl" in msg
    assert calls == []                       # nothing was attempted per location
    assert not (tmp_path / "wr" / "cells.json").exists()


def test_a_vanished_interpreter_gets_the_same_message(monkeypatch, tmp_path):
    def netgen(cmd, **kw):
        raise FileNotFoundError(2, "The system cannot find the file specified")
    _env(monkeypatch, tmp_path, netgen)
    monkeypatch.setattr(pf.shutil, "which", lambda name: "/usr/bin/perl")
    # per-location containment turns it into the run's failure record: a
    # two-location run where both fail raises with the named cause
    with pytest.raises(RuntimeError) as err:
        pf.prepare(_spec(), tmp_path / "wr")
    assert "Perl was not found on PATH" in str(err.value)


def test_the_message_names_the_platform_remedy(monkeypatch):
    monkeypatch.setattr(pf.sys, "platform", "win32")
    assert "Strawberry Perl" in pf.perl_missing_message()
    monkeypatch.setattr(pf.sys, "platform", "darwin")
    assert "ships with macOS" in pf.perl_missing_message()


def test_components_and_the_setup_check_report_perl(monkeypatch):
    from app.ui import server
    from flubnf import settings
    assert "perl" in server._VERSION_KEYS
    monkeypatch.setattr(server, "_VERSION_PROBE", "print('{}')")
    v = server._component_versions()
    assert "perl" in v
    # the setup table names a missing interpreter beside the other paths
    monkeypatch.setattr(settings.shutil, "which", lambda name: None)
    missing = settings.check(verbose=False)
    assert any(name == "perl" for name, _, _ in missing)
