"""End-to-end test of analyze + apply against the legacy DE results."""

from __future__ import annotations

from pathlib import Path

import pytest

from flubnf import bngl_files, conf_files
from flubnf.auto import analyze_state, apply_recommendations
from flubnf.config import FluBNFConfig
from flubnf.paths import WorkspacePaths


from tests.conftest import LEGACY_NAU

LEGACY_RESULTS = (LEGACY_NAU / "current_job" / "results") if LEGACY_NAU else None
LEGACY_EXP = (LEGACY_NAU / "current_job" / "exp_files") if LEGACY_NAU else None


@pytest.fixture
def legacy_workspace(tmp_path, config):
    """Build a workspace pre-populated with legacy results + exp + conf for
    Alabama so analyze_state has something to read."""
    if LEGACY_EXP is None or LEGACY_RESULTS is None:
        pytest.skip("legacy NAU_Influenza/ tree not present")
    paths = WorkspacePaths(root=tmp_path / "legacy").ensure()
    # Drop in a fresh conf and bngl from the templates.
    conf_files.materialize_conf_from_template("Alabama", paths, config)
    bngl_files.materialize_bngl_from_template("Alabama", paths, config)
    # Copy the legacy exp.
    src_exp = LEGACY_EXP / "Alabama_flu.exp"
    if not src_exp.exists():
        pytest.skip("legacy Alabama .exp missing")
    paths.exp_file("Alabama").write_text(src_exp.read_text())
    # Mirror the legacy results dir.
    src_results = LEGACY_RESULTS / "Alabama"
    if not src_results.exists():
        pytest.skip("legacy Alabama results missing")
    dst = paths.results_for("Alabama")
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "Results").mkdir(parents=True, exist_ok=True)
    for f in (src_results / "Results").glob("sorted_params_*"):
        (dst / "Results" / f.name).write_text(f.read_text())
    return paths


class TestAnalyzeState:
    def test_runs_on_legacy_data(self, legacy_workspace, config):
        a = analyze_state("Alabama", legacy_workspace, config)
        assert a.best_obj is not None
        assert a.n_population > 0
        # We may or may not get bounds/step recs — just check the data flowed.
        assert a.step_rec is not None
        assert isinstance(a.bounds_recs, list)


class TestApplyRecommendations:
    def test_apply_idempotent_when_no_recs(self, tmp_workspace, config):
        # Materialize fresh files; analyze on empty results dir -> no recs.
        conf_files.materialize_conf_from_template("Arizona", tmp_workspace, config)
        bngl_files.materialize_bngl_from_template("Arizona", tmp_workspace, config)
        from flubnf.analysis import StateAnalysis
        a = StateAnalysis(state="Arizona", best_obj=None, n_population=0)
        changes = apply_recommendations([a], tmp_workspace, config)
        assert changes[0].bounds_changed == []
        assert changes[0].bounds_added == []

    def test_apply_adds_new_step(self, tmp_workspace, config):
        conf_path = conf_files.materialize_conf_from_template("Arizona", tmp_workspace, config)
        bngl_path = bngl_files.materialize_bngl_from_template("Arizona", tmp_workspace, config)
        from flubnf.analysis import StateAnalysis, StepRecommendation
        a = StateAnalysis(state="Arizona", best_obj=10.0, n_population=10)
        a.step_rec = StepRecommendation(
            needs_new_step=True, n_current_steps=1,
            recent_residuals=[-5, -10, -8], residual_run_length=3,
            relative_error=0.5, reason="test",
        )
        changes = apply_recommendations([a], tmp_workspace, config)
        c = changes[0]
        assert "b1__FREE" in c.bounds_added
        assert "t1__FREE" in c.bounds_added
        assert c.new_n_steps == 2
        # And the BNGL beta function was rewritten.
        bngl_text = bngl_path.read_text()
        assert "if(t>=t0+t1,b1," in bngl_text
        # New conf entries should exist.
        params = {p.name: (p.low, p.high)
                  for p in conf_files.read_uniform_vars(conf_path)}
        assert "b1__FREE" in params
        assert "t1__FREE" in params
