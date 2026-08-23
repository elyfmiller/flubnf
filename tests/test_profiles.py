"""The influenza profile IS today's behavior. These tests are the proof.

A DiseaseProfile is only useful if the disease it was extracted from still
behaves identically. Every assertion below compares the profile against the
module that currently owns the value, not against a copy of it, so a change to
either side fails here.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from flubnf import analogue, sihrs_fit, sihrs_priors
from flubnf.profiles import (COVID, COVID_OMEGA_GATE, COVID_OMEGA_PRIOR,
                             INFLUENZA, PROFILES, DiseaseProfile, get_profile)


class TestInfluenzaIsUnchanged:
    def test_season_of_matches_analogue_every_day_for_twelve_years(self):
        """The season boundary is load-bearing: it defines the analogue's
        'strictly prior season' donor rule. One day of disagreement leaks or
        starves donors."""
        d, end = date(2018, 1, 1), date(2030, 1, 1)
        n = 0
        while d < end:
            assert INFLUENZA.season_of(d) == analogue.season_of(d), d
            d += timedelta(days=1)
            n += 1
        assert n > 4000

    def test_season_start_matches_the_string_runs_py_builds(self):
        for y in range(2020, 2030):
            assert INFLUENZA.season_start(y) == f"{y}-08-01"

    def test_season_bounds_match_retro_formula(self):
        for y in range(2020, 2030):
            assert INFLUENZA.season_bounds(y) == (f"{y}-08-01", f"{y + 1}-06-15")

    def test_season_label_matches_hub_convention(self):
        assert INFLUENZA.season_label(2025) == "2025-26"
        assert INFLUENZA.season_label(2099) == "2099-00"

    def test_fixed_biology_equals_the_shipped_constants(self):
        assert INFLUENZA.fixed.rho == sihrs_fit.RHO_IHR
        assert INFLUENZA.fixed.gammaH_per_week == sihrs_fit.GAMMAH_PER_WEEK
        assert INFLUENZA.fixed.omega_per_week == sihrs_fit.OMEGA_PER_WEEK
        assert INFLUENZA.fixed.gamma_per_week == pytest.approx(
            sihrs_priors.gamma_per_week())
        assert INFLUENZA.fixed.s0_default == sihrs_priors.S0_DEFAULT
        assert INFLUENZA.fixed.s0_range == sihrs_priors.S0_RANGE
        assert INFLUENZA.fixed.attack_rate_range == sihrs_priors.ATTACK_RATE_RANGE

    def test_priors_equal_min_priors_exactly(self):
        assert INFLUENZA.fitted_priors == sihrs_fit.MIN_PRIORS

    def test_log_scale_set_equals_the_shipped_one(self):
        assert INFLUENZA.log_scale_vars == sihrs_fit.LOG_SCALE_VARS

    def test_template_is_the_production_min_template(self):
        assert INFLUENZA.template.name == "SIHRS_pop_min.bngl"
        assert INFLUENZA.template.is_file()

    def test_target_and_baseline_are_the_flusight_strings(self):
        assert INFLUENZA.target_name == "wk inc flu hosp"
        assert INFLUENZA.baseline_model == "FluSight-baseline"

    def test_omega_is_fixed_and_supplies_its_token(self):
        assert not INFLUENZA.fixed.omega_is_fitted
        assert "{{OMEGA}}" in INFLUENZA.fixed_tokens()

    def test_not_bimodal_capable(self):
        assert INFLUENZA.bimodal_capable is False


class TestCovidProfile:
    def test_season_boundary_is_june_not_august(self):
        """August cuts a COVID epidemic in half: the summer wave peaked at
        epiweeks 34, 31, 36, 36 in four of six seasons."""
        assert COVID.season_boundary_month == 6
        assert COVID.season_of(date(2025, 7, 15)) == 2025
        assert COVID.season_of(date(2025, 5, 31)) == 2024
        # the specific failure an August boundary causes
        assert COVID.season_of(date(2025, 9, 6)) == 2025
        assert analogue.season_of(date(2025, 9, 6)) == 2025
        # ... but a July peak splits under the flu rule and not under this one
        assert COVID.season_of(date(2025, 7, 5)) != analogue.season_of(date(2025, 7, 5))

    def test_season_start_and_bounds(self):
        assert COVID.season_start(2025) == "2025-06-01"
        assert COVID.season_bounds(2025) == ("2025-06-01", "2026-05-31")

    def test_target_column_and_baseline(self):
        assert COVID.target_name == "wk inc covid hosp"
        assert COVID.truth_column_alias == "totalconfc19newadm"
        assert COVID.baseline_model == "CovidHub-baseline"

    def test_omega_is_fitted_and_supplies_no_token(self):
        assert COVID.fixed.omega_is_fitted
        assert "{{OMEGA}}" not in COVID.fixed_tokens()
        assert "omega__FREE" in COVID.fitted_priors

    def test_exactly_one_added_dimension_over_influenza(self):
        extra = set(COVID.fitted_priors) - set(INFLUENZA.fitted_priors)
        assert extra == {"omega__FREE"}
        assert COVID.n_fitted == INFLUENZA.n_fitted + 1

    def test_no_second_harmonic(self):
        assert "eps2__FREE" not in COVID.fitted_priors
        assert "phi2__FREE" not in COVID.fitted_priors
        assert COVID.harmonic.n_harmonics == 1

    def test_phi1_carries_no_peak_week_prior(self):
        """The measured lead is 11 weeks; a peak-week prior would be wrong by
        roughly a season quarter."""
        assert COVID.fitted_priors["phi1__FREE"] == (0.0, 52.0)
        assert COVID.harmonic.phi1_is_peak_week is False
        assert COVID.harmonic.peak_lead_weeks == 11.0

    def test_omega_prior_strictly_contains_the_gate_window(self):
        lo, hi = COVID_OMEGA_PRIOR
        glo, ghi = COVID_OMEGA_GATE
        assert lo < glo < ghi < hi, "the gate must be a test, not a tautology"

    def test_omega_gate_window_is_three_to_twelve_months(self):
        from flubnf.covid_fit import omega_to_months
        glo, ghi = COVID_OMEGA_GATE
        assert omega_to_months(ghi) == pytest.approx(3.0, rel=1e-6)
        assert omega_to_months(glo) == pytest.approx(12.0, rel=1e-6)

    def test_literature_omega_lands_inside_the_gate_window(self):
        from flubnf.profiles import COVID_OMEGA_LIT
        glo, ghi = COVID_OMEGA_GATE
        for k, v in COVID_OMEGA_LIT.items():
            assert glo < v < ghi, k

    def test_generation_time_is_the_intrinsic_one(self):
        """The realized household interval (3.59 d) and the serial interval
        (2.38 d) are the wrong quantity for a large-population SIR. Guard the
        distinction, because it is the exact swap the memo warned about."""
        assert COVID.fixed.generation_time_days == pytest.approx(6.84)
        assert "INTRINSIC" in COVID.fixed.gt_note
        assert COVID.fixed.gt_source == "10.1016/j.lanepe.2022.100446"

    def test_bimodal_capable(self):
        assert COVID.bimodal_capable is True
        assert COVID.harmonic.p_multiwave > 0.7

    def test_vintage_horizon_is_recorded(self):
        assert COVID.vintage_earliest == "2024-11-20"

    def test_template_exists_and_frees_omega(self):
        txt = COVID.template.read_text()
        assert "omega   omega__FREE" in txt
        assert "{{OMEGA}}" not in txt

    def test_covid_template_differs_from_min_only_where_intended(self):
        """Structure must be identical. Compare CODE only -- every line with
        its trailing comment stripped -- so a re-sourced citation is free but a
        changed reaction rule, observable or seed species is not."""
        def code(p):
            out = []
            for line in p.read_text().splitlines():
                s = line.split("#", 1)[0].strip()
                if s:
                    out.append(" ".join(s.split()))
            return out
        a, b = code(INFLUENZA.template), code(COVID.template)
        assert len(a) == len(b), "line counts differ: structure changed"
        diff = [(x, y) for x, y in zip(a, b) if x != y]
        assert len(diff) == 2, diff          # the omega line and the suffix
        assert diff[0] == ("omega {{OMEGA}}", "omega omega__FREE"), diff[0]
        assert "SIHRS_flu" in diff[1][0] and "SIHRS_covid" in diff[1][1]


class TestExclusionWindow:
    W = COVID.excluded_windows[0]

    def test_the_march_2026_break_is_recorded(self):
        assert self.W.last_clean_week == "2026-03-21"
        assert self.W.first_shifted_week == "2026-03-28"
        assert "INSTRUMENT" in self.W.verdict

    def test_a_cell_straddling_the_step_is_excluded(self):
        # reference 2026-03-28, anchor 2026-03-21, horizon 0 target 2026-03-28
        assert COVID.excluded_for("2026-03-21", "2026-03-28") is not None
        # horizon 3 from reference 2026-03-07: anchor 2026-02-28, target 03-28
        assert COVID.excluded_for("2026-02-28", "2026-03-28") is not None

    def test_cells_wholly_on_one_side_are_kept(self):
        """The level shift is common to model and truth there, so the cell is
        honest. Over-excluding would quietly shrink the evaluation."""
        assert COVID.excluded_for("2026-02-28", "2026-03-21") is None
        assert COVID.excluded_for("2026-03-28", "2026-04-18") is None
        assert COVID.excluded_for("2026-04-04", "2026-05-02") is None

    def test_influenza_has_no_exclusions_so_scoring_is_unchanged(self):
        assert INFLUENZA.excluded_windows == ()
        assert INFLUENZA.excluded_for("2026-02-28", "2026-03-28") is None


class TestRegistry:
    def test_lookup(self):
        assert get_profile("influenza") is INFLUENZA
        assert get_profile("covid") is COVID

    def test_unknown_key_fails_loudly_rather_than_defaulting_to_flu(self):
        with pytest.raises(KeyError) as e:
            get_profile("covid19")
        assert "covid19" in str(e.value)

    def test_profiles_are_frozen(self):
        with pytest.raises(Exception):
            COVID.season_boundary_month = 8       # type: ignore[misc]

    def test_every_profile_names_an_existing_template(self):
        for p in PROFILES.values():
            assert isinstance(p, DiseaseProfile)
            assert p.template.is_file(), p.key
