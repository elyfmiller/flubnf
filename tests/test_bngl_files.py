"""Tests for flubnf.bngl_files."""

from __future__ import annotations

from pathlib import Path

import pytest

from flubnf import bngl_files
from flubnf.bngl_files import (
    build_logistic_beta,
    build_piecewise_beta,
    set_beta_function,
)


# ---------------------------------------------------------------------------
# Piecewise beta construction
# ---------------------------------------------------------------------------
class TestBuildPiecewiseBeta:
    def test_one_step(self):
        out = build_piecewise_beta(1)
        assert "if(t>=t0,b0," in out
        # Single nesting -> exactly one ) at the end.
        assert out.rstrip().endswith("0)")

    def test_two_steps_matches_legacy_template(self):
        out = build_piecewise_beta(2)
        # Legacy template (from 110624_everything.py user_defined_beta):
        #   if(t>=t0 && t<t0+t1,b0,
        #   if(t>=t0+t1,b1,
        #   0))
        assert "if(t>=t0 && t<t0+t1,b0," in out
        assert "if(t>=t0+t1,b1," in out
        assert out.rstrip().endswith("0))")

    def test_three_steps_balanced_parens(self):
        out = build_piecewise_beta(3)
        assert out.count("if(") == 3
        # body should end with "0)))"
        assert out.rstrip().endswith("0)))")

    def test_zero_steps_raises(self):
        with pytest.raises(ValueError):
            build_piecewise_beta(0)


# ---------------------------------------------------------------------------
# Round-trip: materialize -> read params -> add params -> set beta
# ---------------------------------------------------------------------------
class TestBnglEditing:
    def test_materialize_then_read_params(self, tmp_workspace, config):
        path = bngl_files.materialize_bngl_from_template(
            "Arizona", tmp_workspace, config)
        params = bngl_files.read_parameters(path)
        # Template has b0, t0, mult, gamma, r, I0, plus the moltype molecules
        # (S, I, R, counter) which are NOT in the parameters block.
        assert "b0" in params
        assert "t0" in params
        assert "gamma" in params
        assert "S" not in params

    def test_add_parameters_idempotent(self, tmp_workspace, config):
        path = bngl_files.materialize_bngl_from_template(
            "Arizona", tmp_workspace, config)
        added1 = bngl_files.add_parameters(path, ["b1", "t1"])
        assert added1 == ["b1", "t1"]
        # Second call adds nothing.
        added2 = bngl_files.add_parameters(path, ["b1", "t1"])
        assert added2 == []
        # And the lines look right.
        text = path.read_text()
        assert "b1 b1__FREE" in text
        assert "t1 t1__FREE" in text

    def test_set_beta_function_replaces_block(self, tmp_workspace, config):
        path = bngl_files.materialize_bngl_from_template(
            "Arizona", tmp_workspace, config)
        new_beta = build_piecewise_beta(3)
        set_beta_function(path, new_beta)
        text = path.read_text()
        # New beta installed.
        assert "if(t>=t0+t1+t2,b2," in text
        # And the *old* one-step expression should be gone.
        assert text.count("beta()=") == 1

    def test_set_simulation_window(self, tmp_workspace, config):
        path = bngl_files.materialize_bngl_from_template(
            "Arizona", tmp_workspace, config)
        bngl_files.set_simulation_window(path, t_start=0, t_end=31, n_steps=31)
        text = path.read_text()
        assert "t_end=>31" in text
        assert "n_steps=>31" in text


# ---------------------------------------------------------------------------
# Logistic beta construction (SIRS-migration, Phase 1)
# ---------------------------------------------------------------------------
class TestBuildLogisticBeta:
    def test_one_transition(self):
        out = build_logistic_beta(1)
        assert out == "beta()=b0 + db1/(1+exp(-(t-tc1)/sw))\n"
        # Single balanced line: parens balance, no helper sub-functions.
        assert out.count("(") == out.count(")")
        assert out.count("\n") == 1

    def test_two_transitions(self):
        out = build_logistic_beta(2)
        assert "b0 + db1/(1+exp(-(t-tc1)/sw)) + db2/(1+exp(-(t-tc2)/sw))" in out
        assert out.count("(") == out.count(")")
        # No nested-if, no line continuations (the parser-safety property).
        assert "if(" not in out
        assert "\\" not in out

    def test_three_transitions_param_names(self):
        out = build_logistic_beta(3)
        for k in (1, 2, 3):
            assert f"db{k}/(1+exp(-(t-tc{k})/sw))" in out

    def test_zero_transitions_rejected(self):
        with pytest.raises(ValueError):
            build_logistic_beta(0)

    def test_installs_via_set_beta_function(self, tmp_workspace, config):
        # The single-line logistic beta must cleanly replace the template's
        # piecewise beta block (paren-balance detection).
        path = bngl_files.materialize_bngl_from_template(
            "Arizona", tmp_workspace, config)
        set_beta_function(path, build_logistic_beta(2))
        text = path.read_text()
        assert text.count("beta()=") == 1
        assert "db2/(1+exp(-(t-tc2)/sw))" in text
        # Old piecewise expression gone.
        assert "if(t>=t0" not in text


# ---------------------------------------------------------------------------
# SIRS template materialization (SIRS-migration, Phase 2/3)
# ---------------------------------------------------------------------------
def _sirs_config(config):
    from flubnf.config import ModelConfig
    return config.model_copy(update={"model": ModelConfig(model_type="sirs_logistic")})


class TestMaterializeSIRS:
    def test_substitutes_all_tokens(self, tmp_workspace, config):
        cfg = _sirs_config(config)
        path = bngl_files.materialize_bngl_from_template(
            "Arizona", tmp_workspace, cfg, force=True)
        text = path.read_text()
        # No unresolved {{...}} tokens remain.
        assert "{{" not in text and "}}" not in text

    def test_population_substituted(self, tmp_workspace, config):
        from flubnf.constants import load_locations
        cfg = _sirs_config(config)
        pop = load_locations(cfg.locations_csv)["Arizona"].population
        path = bngl_files.materialize_bngl_from_template(
            "Arizona", tmp_workspace, cfg, force=True)
        text = path.read_text()
        assert f"N {pop}" in text

    def test_frequency_dependent_and_sirs_structure(self, tmp_workspace, config):
        cfg = _sirs_config(config)
        path = bngl_files.materialize_bngl_from_template(
            "Arizona", tmp_workspace, cfg, force=True)
        text = path.read_text()
        # Frequency-dependent infection rate constant beta()/N.
        assert "S()+I()->I()+I() beta()/N" in text
        # SIRS waning reaction present.
        assert "R()->S() omega" in text
        # Smooth beta, not a hard step.
        assert "db1/(1+exp(-(t-tc1)/sw))" in text
        assert "if(t>=t0" not in text

    def test_omega_and_centers_from_config(self, tmp_workspace, config):
        from flubnf.config import ModelConfig
        cfg = config.model_copy(update={"model": ModelConfig(
            model_type="sirs_logistic", omega_fixed=0.025,
            transition_centers=[7.0, 17.0, 27.0], transition_width=3.0)})
        path = bngl_files.materialize_bngl_from_template(
            "Arizona", tmp_workspace, cfg, force=True)
        text = path.read_text()
        assert "omega 0.025" in text
        assert "tc1 7" in text and "tc2 17" in text and "tc3 27" in text
        assert "sw  3" in text or "sw 3" in text

    def test_piecewise_default_untouched(self, tmp_workspace, config):
        # Default model must still produce the legacy piecewise template.
        path = bngl_files.materialize_bngl_from_template(
            "Arizona", tmp_workspace, config, force=True)
        text = path.read_text()
        assert "if(t>=t0,b0," in text
        assert "beta()/N" not in text

    def test_two_transition_assembly_matches_pybnf_engine(self, tmp_workspace, config):
        # Reproduce the pybnf_engine SIRS branch for a 2-transition fit:
        # materialize -> add db2 -> set logistic beta. The result must be a
        # coherent, fittable bngl (db2 declared, beta references it).
        cfg = _sirs_config(config)
        path = bngl_files.materialize_bngl_from_template(
            "Arizona", tmp_workspace, cfg, force=True)
        bngl_files.add_parameters(path, ["db2"])
        set_beta_function(path, build_logistic_beta(2))
        text = path.read_text()
        # db2 declared as a free param.
        assert "db2 db2__FREE" in text
        # beta references both amplitudes at fixed centers.
        assert "db1/(1+exp(-(t-tc1)/sw)) + db2/(1+exp(-(t-tc2)/sw))" in text
        # Exactly one beta() definition, frequency-dependent observable intact.
        assert text.count("beta()=") == 1
        assert "H_weekly()=mult*beta()*S*I/N" in text
        # No unresolved tokens.
        assert "{{" not in text
