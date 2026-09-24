"""Tests for `flubnf doctor`.

We don't actually shell out to the CLI — `run_doctor` is the unit. We do
verify the CLI wiring and its exit-code contract (1 if and only if a check
FAILs) with typer's CliRunner.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from flubnf import doctor
from flubnf.cli import app


def test_python_check_passes_on_current_interpreter():
    res = doctor._check_python()
    assert res.status is doctor.Status.OK


def test_imports_check_all_pass_in_test_env():
    # Tests don't run unless the dev install brought everything in.
    results = doctor._check_imports()
    for r in results:
        assert r.status is doctor.Status.OK, (
            f"{r.name} failed in the test env — fix the venv: {r.detail}"
        )


def test_numpy2_patch_check_runs():
    res = doctor._check_numpy2_pybnf()
    # We don't assert OK because some environments may have older pybnf;
    # we only assert the check returns a CheckResult without crashing.
    assert isinstance(res, doctor.CheckResult)
    assert res.name == "pybnf NumPy 2.0 patch"


def test_disk_space_check(tmp_path):
    res = doctor._check_disk_space(tmp_path)
    assert res.status in (doctor.Status.OK, doctor.Status.WARN,
                          doctor.Status.FAIL)


def test_disk_space_is_measured_where_the_console_writes():
    repo = Path(doctor.__file__).resolve().parents[1]
    state = repo / "app" / "state"
    assert doctor._disk_path() == (state if state.is_dir() else repo)


def test_run_doctor_returns_report():
    rep = doctor.run_doctor(online=False)
    assert isinstance(rep, doctor.DoctorReport)
    assert len(rep.checks) > 5
    # python should always pass; that's a guard against the report being
    # built from a completely empty pipeline.
    py = [c for c in rep.checks if c.name == "python"]
    assert py and py[0].status is doctor.Status.OK
    names = {c.name for c in rep.checks}
    assert {"FluSight hub", "BNG2.pl", "disk space"} <= names
    online = {n for n, _ in doctor.ONLINE_ENDPOINTS}
    assert not names & online                        # offline by default


def test_run_doctor_online_probes_every_endpoint(monkeypatch):
    seen = []

    def fake(name, url):
        seen.append(url)
        return doctor.CheckResult(name, doctor.Status.OK, "stub")
    monkeypatch.setattr(doctor, "_check_reachable", fake)
    rep = doctor.run_doctor(online=True)
    assert seen == [u for _, u in doctor.ONLINE_ENDPOINTS]
    names = {c.name for c in rep.checks}
    assert {n for n, _ in doctor.ONLINE_ENDPOINTS} <= names


def test_online_endpoints_are_what_the_product_reads():
    """Delphi Epidata (the donor banks) and the hub's GitHub remote."""
    from flubnf import nrevss
    urls = [u for _, u in doctor.ONLINE_ENDPOINTS]
    assert any(nrevss.BASE_URL.startswith(u) for u in urls)
    assert "https://github.com/cdcepi/FluSight-forecast-hub" in urls


@pytest.mark.parametrize("answer, status", [
    (200, "OK"), (404, "OK"), (503, "WARN"), (OSError("no route"), "FAIL")])
def test_reachable_check_maps_the_answer(monkeypatch, answer, status):
    """Any HTTP answer below 500 is reachable, 5xx a WARN, no answer a FAIL
    (the exit-code contract: only FAIL exits 1)."""
    import urllib.error
    import urllib.request

    class _Resp:
        def __init__(self, code):
            self.status = code

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        assert req.get_method() == "HEAD"
        if isinstance(answer, Exception):
            raise answer
        if answer >= 400:
            raise urllib.error.HTTPError(req.full_url, answer, "x", {}, None)
        return _Resp(answer)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = doctor._check_reachable("probe", "https://example.org/x")
    assert res.status is doctor.Status[status], res


def test_cli_doctor_smoke(tmp_path):
    """End-to-end: typer CliRunner invokes the doctor subcommand and we
    just verify it produces output and exits with a real code."""
    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    # We don't assert the exit code: this test env usually lacks the engine
    # and the hub clone, which are real FAILs. We just verify the
    # subcommand registered and ran the table.
    assert "FluBNF doctor" in result.stdout
    assert "python" in result.stdout


def _report(*statuses):
    rep = doctor.DoctorReport()
    for i, s in enumerate(statuses):
        rep.add(doctor.CheckResult(f"check {i}", s, "detail", "hint"))
    return rep


def test_cli_doctor_exits_1_when_a_check_fails(monkeypatch):
    seen = {}

    def fake(*, online=False):
        seen["online"] = online
        return _report(doctor.Status.OK, doctor.Status.WARN,
                       doctor.Status.FAIL)
    monkeypatch.setattr(doctor, "run_doctor", fake)
    result = CliRunner().invoke(app, ["doctor", "--online"])
    assert result.exit_code == 1, result.output
    assert seen == {"online": True}
    assert "1 fail" in result.stdout


def test_cli_doctor_exits_0_on_ok_and_warn_only(monkeypatch):
    monkeypatch.setattr(doctor, "run_doctor", lambda *, online=False:
                        _report(doctor.Status.OK, doctor.Status.WARN))
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "1 warn" in result.stdout


def test_cli_doctor_accepts_and_ignores_config_and_workspace(monkeypatch):
    monkeypatch.setattr(doctor, "run_doctor", lambda *, online=False:
                        _report(doctor.Status.OK))
    result = CliRunner().invoke(app, ["doctor", "-c", "nope.yaml",
                                      "-w", "season_2025"])
    assert result.exit_code == 0, result.output
    assert "ignored" in result.stdout


def test_cli_doctor_pre_studio_is_accepted_and_ignored(monkeypatch):
    monkeypatch.setattr(doctor, "run_doctor", lambda *, online=False:
                        _report(doctor.Status.OK))
    result = CliRunner().invoke(app, ["doctor", "--pre-studio"])
    assert result.exit_code == 0, result.output


# ------------------------------------------ BNG2.pl: this platform's bundle

@pytest.mark.parametrize("plat,own", [("linux", "bng-linux"),
                                      ("darwin", "bng-mac"),
                                      ("win32", "bng-win")])
def test_bng_candidates_lead_with_this_platforms_bundle(plat, own):
    from flubnf import settings
    dirs = settings.bng_platform_dirs(plat)
    assert dirs[0] == own
    assert sorted(dirs) == ["bng-linux", "bng-mac", "bng-win"]
    first = next(settings._bng_candidates(plat))
    assert f"/{own}/BNG2.pl" in first.replace("\\", "/")
    # the development host's anaconda paths follow the same order
    tail = [c for c in settings._bng_candidates(plat)
            if c.startswith("/opt/anaconda3")]
    assert tail and all("bng-win" not in c for c in tail)
    if own != "bng-win":
        assert f"/{own}/" in tail[0]


def test_doctor_suggests_this_platforms_bng_bundle(monkeypatch, tmp_path):
    """With the configured path missing, doctor points at the bundle that
    runs here (bng-linux on Linux), never bng-mac first everywhere."""
    import sys
    import types
    from flubnf import settings
    pkg = tmp_path / "bionetgen"
    for d in ("bng-mac", "bng-linux", "bng-win"):
        (pkg / d).mkdir(parents=True)
        (pkg / d / "BNG2.pl").write_text("")
    fake = types.ModuleType("bionetgen")
    fake.__file__ = str(pkg / "__init__.py")
    monkeypatch.setitem(sys.modules, "bionetgen", fake)
    monkeypatch.setattr(settings, "BNG", tmp_path / "missing" / "BNG2.pl")
    monkeypatch.setattr(sys, "platform", "linux")
    res = doctor._check_bng()
    assert res.status is doctor.Status.WARN
    assert str(pkg / "bng-linux" / "BNG2.pl") in res.detail
    monkeypatch.setattr(sys, "platform", "darwin")
    assert "bng-mac" in doctor._check_bng().detail
