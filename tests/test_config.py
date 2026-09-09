"""Tests for flubnf.config — focused on the SIRS-migration model flag.

The migration is flag-gated: the default config must keep the legacy
piecewise SIR behavior byte-identical, so the rest of the pipeline (and the
304 existing tests) are unaffected until a run explicitly opts in.
"""

from __future__ import annotations

import pytest

from flubnf.config import FluBNFConfig, ModelConfig


class TestModelConfigDefaults:
    def test_model_type_defaults_to_piecewise(self):
        cfg = FluBNFConfig()
        assert cfg.model.model_type == "sir_piecewise"

    def test_loaded_config_defaults_to_piecewise(self):
        # The packaged default.yaml must not silently flip the model.
        cfg = FluBNFConfig.load()
        assert cfg.model.model_type == "sir_piecewise"

    def test_omega_and_knots_have_sane_defaults(self):
        m = ModelConfig()
        assert m.omega_fixed == pytest.approx(0.019)
        assert m.transition_width > 0
        assert len(m.transition_centers) >= 3
        assert m.transition_centers == sorted(m.transition_centers)

    def test_opt_in_to_sirs_logistic(self):
        m = ModelConfig(model_type="sirs_logistic")
        assert m.model_type == "sirs_logistic"

    def test_unknown_model_type_rejected(self):
        with pytest.raises(ValueError):
            ModelConfig(model_type="seir_magic")


def test_exporting_a_section_named_env_var_does_not_break_the_loader(monkeypatch):
    """FLUBNF_PYBNF is one of the four paths flubnf/settings.py documents,
    and .flubnf.env and setup_engine.sh both export it. It shares a name
    with the `pybnf` SECTION of this config, and the loader used to assign
    the raw string to it, so every command that loads config died with a
    pydantic ValidationError: `flubnf doctor` among them, which is the
    command the engine's own error message tells the operator to run
    (lab machine, 2026-09-08). Sections are skipped; flat keys still work.
    """
    from flubnf.config import FluBNFConfig, PyBNFConfig

    for var in ("FLUBNF_PYBNF", "FLUBNF_SEASON", "FLUBNF_CDC", "FLUBNF_MODEL"):
        monkeypatch.setenv(var, "/some/path/that/is/not/a/section")
    cfg = FluBNFConfig.load()
    assert isinstance(cfg.pybnf, PyBNFConfig)

    monkeypatch.setenv("FLUBNF_LOCATIONS_CSV", "/tmp/locations.csv")
    assert str(FluBNFConfig.load().locations_csv).endswith("locations.csv")
