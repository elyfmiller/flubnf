"""An engine older than the console fails every cell after everything
before the fit has worked, which is how a PI's laptop looked on
2026-09-09. The console now reads the fork's own key lists at prepare
and refuses by name."""
import pytest

from app.core.engines import pf


@pytest.fixture()
def fork(tmp_path, monkeypatch):
    root = tmp_path / "fork"
    (root / "pybnf").mkdir(parents=True)
    (root / "pybnf" / "pf.py").write_text("# the filter\n")
    monkeypatch.setattr(pf, "PYBNF_PF", root)
    return root


def _parse(root, *keys):
    (root / "pybnf" / "parse.py").write_text(
        "numkeys_int = [%s]\n" % ", ".join("'%s'" % k for k in keys))


def test_an_engine_with_every_key_is_current(fork):
    _parse(fork, *pf.CONF_KEYS_REQUIRED)
    assert pf.engine_available() and pf.engine_current()
    assert pf.engine_missing_keys() == ()


def test_an_engine_that_predates_a_key_is_named_stale_with_its_stamp(fork):
    _parse(fork, "pf_particles", "pf_forecast_weeks")
    (fork / "VERSION").write_text("feature/particle-filter 3320d1f0\n")
    assert pf.engine_available() and not pf.engine_current()
    assert "pf_forecast_intervals" in pf.engine_missing_keys()
    assert "pf_particles" not in pf.engine_missing_keys()
    msg = pf.engine_stale_message()
    assert str(fork) in msg and "pf_forecast_intervals" in msg
    assert "3320d1f0" in msg and "Downloads" in msg


def test_a_fork_without_a_parser_module_is_stale_not_a_crash(fork):
    assert not pf.engine_current()
    assert "does not accept" in pf.engine_stale_message()


def test_doctor_reports_the_stale_engine(fork, monkeypatch):
    from flubnf import doctor
    _parse(fork, "pf_particles")
    res = doctor._check_pf_engine()
    assert res.status == doctor.Status.FAIL
    assert "older than this console" in res.detail
