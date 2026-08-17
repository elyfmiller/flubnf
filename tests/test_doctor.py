"""Tests for `flubnf doctor`.

We don't actually shell out to the CLI — `run_doctor` is the unit. We do
verify the CLI wiring with one smoke test using typer's CliRunner.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from flubnf import doctor
from flubnf.cli import app
from flubnf.config import FluBNFConfig


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


def test_workspace_check_handles_missing(tmp_path):
    cfg = FluBNFConfig.load(
        workspace_root=tmp_path / "nope",
        data_cache=tmp_path / "data",
    )
    results = doctor._check_workspace(cfg, "season_test")
    assert len(results) == 1
    assert results[0].status is doctor.Status.WARN
    assert "does not exist" in results[0].detail


def test_workspace_check_passes_when_writable(tmp_path):
    cfg = FluBNFConfig.load(
        workspace_root=tmp_path / "workspaces",
        data_cache=tmp_path / "data",
    )
    (tmp_path / "workspaces" / "season_test").mkdir(parents=True)
    results = doctor._check_workspace(cfg, "season_test")
    assert results[0].status is doctor.Status.OK


def test_data_cache_warns_when_empty(tmp_path):
    cfg = FluBNFConfig.load(
        workspace_root=tmp_path / "workspaces",
        data_cache=tmp_path / "data",
    )
    res = doctor._check_data_cache(cfg)
    assert res.status is doctor.Status.WARN


def test_historical_priors_warns_when_missing(tmp_path):
    res = doctor._check_historical_priors(tmp_path)
    assert res.status is doctor.Status.WARN


def test_historical_priors_ok_when_present(tmp_path):
    hp = tmp_path / "data" / "historical_priors"
    hp.mkdir(parents=True)
    (hp / "Alabama.json").write_text("{}")
    res = doctor._check_historical_priors(tmp_path)
    assert res.status is doctor.Status.OK
    assert "1 state prior" in res.detail


def test_disk_space_check(tmp_path):
    res = doctor._check_disk_space(tmp_path)
    assert res.status in (doctor.Status.OK, doctor.Status.WARN,
                          doctor.Status.FAIL)


def test_run_doctor_returns_report(tmp_path):
    cfg = FluBNFConfig.load(
        workspace_root=tmp_path / "workspaces",
        data_cache=tmp_path / "data",
    )
    rep = doctor.run_doctor(cfg, workspace="season_test", online=False)
    assert isinstance(rep, doctor.DoctorReport)
    assert len(rep.checks) > 5
    # python should always pass; that's a guard against the report being
    # built from a completely empty pipeline.
    py = [c for c in rep.checks if c.name == "python"]
    assert py and py[0].status is doctor.Status.OK


def test_cli_doctor_smoke(tmp_path):
    """End-to-end: typer CliRunner invokes the doctor subcommand and we
    just verify it produces output and exits with a real code."""
    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    # We don't assert the exit code — BNG2.pl typically isn't at the
    # configured anaconda path in this test env, which is a real FAIL.
    # We just verify the subcommand registered and ran the table.
    assert "FluBNF doctor" in result.stdout
    assert "python" in result.stdout


# ---------------------------------------------------------------------------
# Pre-studio readiness checks
# ---------------------------------------------------------------------------
class TestPreStudioChecks:
    def test_historical_priors_loadable_ok_on_valid_files(self, tmp_path):
        hp = tmp_path / "data" / "historical_priors"
        hp.mkdir(parents=True)
        (hp / "Alabama.json").write_text(
            '{"state": "Alabama", "seasons": ['
            '{"season_year": 2024, "best_params": {"b0__FREE": 0.5}, '
            '"p25_params": {"b0__FREE": 0.45}, '
            '"p75_params": {"b0__FREE": 0.55}, '
            '"peak_admissions": 100, "peak_week": 27, "n_steps_final": 1}'
            ']}'
        )
        results = doctor._check_studio_historical_priors_loadable(tmp_path)
        # Summary row at end.
        summary = results[-1]
        assert summary.status is doctor.Status.OK
        assert "1/1" in summary.detail

    def test_historical_priors_loadable_flags_corrupt(self, tmp_path):
        hp = tmp_path / "data" / "historical_priors"
        hp.mkdir(parents=True)
        (hp / "Alabama.json").write_text("{not valid json")
        results = doctor._check_studio_historical_priors_loadable(tmp_path)
        # At least one FAIL row for the broken file + summary as WARN.
        assert any(r.status is doctor.Status.FAIL for r in results)
        assert results[-1].status is doctor.Status.WARN

    def test_historical_priors_loadable_no_dir_returns_empty(self, tmp_path):
        # Benign — empty list, handled by the regular check.
        assert doctor._check_studio_historical_priors_loadable(tmp_path) == []

    def test_locations_schema_ok_on_canonical(self, tmp_path):
        cfg = FluBNFConfig.load(
            workspace_root=tmp_path / "workspaces",
            data_cache=tmp_path / "data",
        )
        # The bundled locations.csv ships with the package.
        res = doctor._check_studio_locations_schema(cfg)
        assert res.status is doctor.Status.OK

    def test_locations_schema_fails_when_missing(self, tmp_path):
        cfg = FluBNFConfig.load(
            workspace_root=tmp_path / "workspaces",
            data_cache=tmp_path / "data",
            locations_csv=tmp_path / "nope.csv",
        )
        res = doctor._check_studio_locations_schema(cfg)
        assert res.status is doctor.Status.FAIL

    def test_state_templates_warns_when_workspace_missing(self, tmp_path):
        cfg = FluBNFConfig.load(
            workspace_root=tmp_path / "workspaces",
            data_cache=tmp_path / "data",
        )
        res = doctor._check_studio_state_templates(cfg, "absent_ws")
        assert res.status is doctor.Status.WARN

    def test_state_templates_fails_when_files_missing(self, tmp_path):
        cfg = FluBNFConfig.load(
            workspace_root=tmp_path / "workspaces",
            data_cache=tmp_path / "data",
        )
        ws = tmp_path / "workspaces" / "absent_ws"
        (ws / "model_files").mkdir(parents=True)
        (ws / "conf_files").mkdir(parents=True)
        # No template files written.
        res = doctor._check_studio_state_templates(cfg, "absent_ws")
        assert res.status is doctor.Status.FAIL
        assert "missing" in res.detail

    def test_state_templates_ok_when_all_present(self, tmp_path):
        from flubnf.constants import JURISDICTIONS
        cfg = FluBNFConfig.load(
            workspace_root=tmp_path / "workspaces",
            data_cache=tmp_path / "data",
        )
        ws = tmp_path / "workspaces" / "filled"
        (ws / "model_files").mkdir(parents=True)
        (ws / "conf_files").mkdir(parents=True)
        for j in JURISDICTIONS:
            (ws / "model_files" / f"{j}.bngl").write_text("")
            (ws / "conf_files" / f"{j}.conf").write_text("")
        res = doctor._check_studio_state_templates(cfg, "filled")
        assert res.status is doctor.Status.OK

    def test_fringe_detectors_fire_on_canonical_fixtures(self):
        res = doctor._check_studio_fringe_detectors()
        assert res.status is doctor.Status.OK, res.detail

    def test_flusight_target_warns_when_missing(self, tmp_path):
        res = doctor._check_studio_flusight_target(tmp_path)
        assert res.status is doctor.Status.WARN

    def test_flusight_target_ok_when_well_formed(self, tmp_path):
        d = tmp_path / "data" / "flusight_target"
        d.mkdir(parents=True)
        target = d / "target-hospital-admissions.csv"
        # Need >= 1000 rows for OK status.
        lines = ['date,location,location_name,value,weekly_rate']
        for i in range(1500):
            lines.append(f"2026-01-01,01,Alabama,{i},0.0")
        target.write_text("\n".join(lines))
        res = doctor._check_studio_flusight_target(tmp_path)
        assert res.status is doctor.Status.OK

    def test_submission_validator_resolvable(self):
        res = doctor._check_studio_submission_validator()
        assert res.status is doctor.Status.OK

    def test_run_doctor_with_pre_studio_includes_extra_checks(self, tmp_path):
        cfg = FluBNFConfig.load(
            workspace_root=tmp_path / "workspaces",
            data_cache=tmp_path / "data",
        )
        rep = doctor.run_doctor(cfg, workspace="ws", pre_studio=True,
                                 repo_root=tmp_path)
        names = {c.name for c in rep.checks}
        # Extra checks present:
        assert "locations schema" in names
        assert "fringe detectors" in names
        assert "submission validator" in names

    def test_cli_doctor_pre_studio_flag(self):
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "--pre-studio"])
        assert "fringe detectors" in result.stdout
        assert "locations schema" in result.stdout
