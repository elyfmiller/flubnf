"""Tests for `flubnf doctor`.

We don't actually shell out to the CLI — `run_doctor` is the unit. We do
verify the CLI wiring and its exit-code contract (1 if and only if a check
FAILs) with typer's CliRunner.
"""

from __future__ import annotations

from pathlib import Path

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
    assert "CDC Socrata reachable" not in names      # offline by default


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


def test_cli_doctor_pre_studio_is_gone():
    result = CliRunner().invoke(app, ["doctor", "--pre-studio"])
    assert result.exit_code == 2
