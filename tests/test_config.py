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
