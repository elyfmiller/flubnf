"""The engine seam must agree with pf.py, and must not change it.

pf.py's fitting internals are frozen. This seam exists so a future profile-aware
prepare() is a substitution rather than a rewrite, which is only true while the
influenza branch reproduces pf.py's own constants. These tests read pf.py's
source so the agreement cannot rot silently.
"""
from __future__ import annotations

import re

import pytest

from app.core.engines import profiles as ep
from app.core.engines import pf
from flubnf.profiles import COVID, INFLUENZA


class TestAgreesWithPf:
    def test_influenza_template_is_pf_template(self):
        assert ep.template(INFLUENZA) == pf.TEMPLATE

    def test_influenza_defaults_block_is_pf_defaults_block(self):
        assert ep.defaults_block(INFLUENZA) == pf.DEFAULTS_BLOCK

    @staticmethod
    def _parsed(block):
        return {m.group(2): (m.group(1), float(m.group(3)), float(m.group(4)))
                for m in re.finditer(r"^(\w+) = (\S+) (\S+) (\S+)$", block, re.M)}

    def test_influenza_vars_block_declares_pf_variables_with_pf_bounds(self):
        a, b = self._parsed(ep.vars_block(INFLUENZA)), self._parsed(pf.VARS_1S)
        assert set(a) == set(b)
        for k in a:
            assert a[k][1:] == b[k][1:], k

    def test_the_one_scale_disagreement_with_pf_is_reff_and_is_pre_existing(self):
        """Recorded, not papered over. pf.py proposes Reff LINEARLY; the AMCMC
        path (sihrs_fit.LOG_SCALE_VARS) proposes it in LOG space. Both predate
        this seam. The seam follows the AMCMC set because that is what
        DiseaseProfile.log_scale_vars mirrors; if the divergence is ever
        resolved, this test is where it surfaces."""
        from flubnf.sihrs_fit import LOG_SCALE_VARS
        a, b = self._parsed(ep.vars_block(INFLUENZA)), self._parsed(pf.VARS_1S)
        differ = {k for k in a if a[k][0] != b[k][0]}
        assert differ == {"Reff__FREE"}
        assert "Reff__FREE" in LOG_SCALE_VARS
        assert a["Reff__FREE"][0] == "loguniform_var"
        assert b["Reff__FREE"][0] == "uniform_var"

    def test_pf_module_is_untouched_by_this_seam(self):
        """Nothing here imports into pf; pf must not know profiles exist."""
        src = __import__("pathlib").Path(pf.__file__).read_text()
        assert "profiles" not in src


class TestCovidBranch:
    def test_template_is_the_covid_one_and_exists(self):
        assert ep.template(COVID).name == "SIHRS_pop_covid.bngl"

    def test_defaults_seed_omega_off_both_bounds(self):
        """Starting a chain at a bound manufactures the pinning the gate is
        meant to detect."""
        m = re.search(r"omega__FREE ([0-9.eE+-]+)", ep.defaults_block(COVID))
        assert m
        v = float(m.group(1))
        lo, hi = COVID.fitted_priors["omega__FREE"]
        assert lo * 1.5 < v < hi / 1.5

    def test_vars_block_log_scales_omega(self):
        assert "loguniform_var = omega__FREE" in ep.vars_block(COVID)

    def test_engine_spec_carries_the_disease_facts(self):
        s = ep.engine_spec(COVID)
        assert s["target_name"] == "wk inc covid hosp"
        assert s["baseline_model"] == "CovidHub-baseline"
        assert s["season_boundary_month"] == 6
        assert s["bimodal_capable"] is True
        assert s["n_fitted"] == 6
        assert s["vintage_earliest"] == "2024-11-20"

    def test_suffix_is_disease_tagged(self):
        assert ep.suffix(COVID, "New York") == "New_York_covid"
        assert ep.suffix(INFLUENZA, "New York") == "New_York_influenza"


class TestGuardsAreReachableFromTheEngineLayer:
    ONE_WAVE = [5, 8, 14, 25, 48, 90, 150, 220, 260, 240, 180, 120, 70, 40,
                22, 12, 7, 4]

    def test_covid_guards_refuse(self):
        from flubnf.unimodal_guard import BimodalProfileError
        g = ep.guards(COVID)
        with pytest.raises(BimodalProfileError):
            g["season_peak"](self.ONE_WAVE)
        with pytest.raises(BimodalProfileError):
            g["detect_phase"](self.ONE_WAVE)

    def test_influenza_guards_pass_through(self):
        g = ep.guards(INFLUENZA)
        assert g["season_peak"](self.ONE_WAVE).value is not None
        assert g["shoulder_decomposition"](self.ONE_WAVE).value is not None

    def test_the_wave_aware_replacement_needs_no_profile(self):
        g = ep.guards(COVID)
        assert len(g["all_peaks"](self.ONE_WAVE)) == 1
        assert g["count_waves"](self.ONE_WAVE) == 1

    def test_the_report_states_the_behaviour(self):
        assert "refuse" in ep.guards(COVID)["report"]["behaviour"]
        assert "pass through" in ep.guards(INFLUENZA)["report"]["behaviour"]


class TestVintageDispatch:
    def test_covid_dispatches_to_the_parquet_adapter(self):
        from flubnf import covid_vintage as cv
        if not cv.TIMESERIES.is_file():
            pytest.skip("CovidHub parquet not staged")
        assert ep.vintages(COVID)[0] == "2024-11-20"
        p = ep.vintage_path(COVID, "2026-03-18")
        assert p.is_file() and p.name.endswith("2026-03-18.csv")

    def test_covid_refuses_a_pre_horizon_date(self):
        from flubnf import covid_vintage as cv
        if not cv.TIMESERIES.is_file():
            pytest.skip("CovidHub parquet not staged")
        with pytest.raises(ValueError):
            ep.vintage_path(COVID, "2024-01-06")

    def test_influenza_dispatches_to_the_flusight_archive(self):
        from flubnf.settings import ARCHIVE
        if not ARCHIVE.is_dir():
            pytest.skip("FluSight hub archive not available")
        vs = ep.vintages(INFLUENZA)
        assert vs and ep.vintage_path(INFLUENZA, vs[-1]).is_file()
