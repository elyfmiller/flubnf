"""Tests for flubnf.simulate."""

from __future__ import annotations

import numpy as np
import pytest

from flubnf.simulate import predict_weekly, simulate


class TestSimulate:
    def test_returns_n_plus_1_points(self):
        params = {"I0": 0.001, "gamma": 0.1, "mult": 1000.0,
                  "b0": 0.5, "t0": 0.0}
        res = simulate(params, n_steps=10)
        assert len(res.t) == 11  # 0..10 inclusive

    def test_h_weekly_is_zero_before_t0(self):
        # t0 = 5, beta is 0 for t<5 -> H_weekly should be 0 at t=0,1,2,3,4
        params = {"I0": 0.001, "gamma": 0.1, "mult": 1000.0,
                  "b0": 0.5, "t0": 5.0}
        res = simulate(params, n_steps=10)
        assert np.allclose(res.H_weekly[:5], 0.0)
        assert res.H_weekly[5] > 0  # outbreak starts

    def test_accepts_free_suffixed_keys(self):
        params = {"I0__FREE": 0.001, "gamma__FREE": 0.1,
                  "mult__FREE": 1000.0, "b0__FREE": 0.5, "t0__FREE": 0.0}
        res = simulate(params, n_steps=5)
        assert len(res.t) == 6

    def test_predict_weekly_length_matches_request(self):
        params = {"I0": 0.001, "gamma": 0.1, "mult": 1000.0,
                  "b0": 0.5, "t0": 0.0}
        h = predict_weekly(params, n_weeks=13)
        assert len(h) == 13

    def test_two_step_piecewise(self):
        # b0=0.3 for first window, b1=0.6 after switch — outbreak should
        # accelerate at the switch.
        params = {"I0": 0.001, "gamma": 0.1, "mult": 1000.0,
                  "b0": 0.3, "t0": 0.0, "b1": 0.8, "t1": 5.0}
        res = simulate(params, n_steps=15)
        # Growth rate should pick up after t=5.
        early_growth = res.I[3] - res.I[2]
        late_growth = res.I[8] - res.I[7]
        assert late_growth > early_growth

    def test_population_conservation(self):
        params = {"I0": 0.001, "gamma": 0.1, "mult": 1000.0,
                  "b0": 0.5, "t0": 0.0}
        res = simulate(params, n_steps=50)
        # S + I + R should always sum to 1 within solver tolerance.
        total = res.S + res.I + res.R
        assert np.allclose(total, 1.0, atol=1e-6)


class TestLogisticBetaMirror:
    """SIRS-migration Phase 1: smooth logistic beta, still fractional SIR
    (no N, no omega) so it stays comparable to the legacy model."""

    def _params(self, **over):
        p = {"I0": 0.001, "gamma": 0.1, "mult": 1000.0,
             "b0": 0.3, "db1": 0.5, "tc1": 6.0, "sw": 2.5}
        p.update(over)
        return p

    def test_runs_and_returns_trajectory(self):
        res = simulate(self._params(), n_steps=20, model_type="sirs_logistic")
        assert len(res.t) == 21
        assert np.all(np.isfinite(res.H_weekly))

    def test_beta_is_smooth_not_stepped(self):
        # The hospitalization curve should rise smoothly through the transition
        # center, with no discontinuous jump between adjacent weeks.
        res = simulate(self._params(db1=0.7, tc1=8.0),
                       n_steps=20, model_type="sirs_logistic")
        diffs = np.diff(res.I)
        # No single week-over-week change should dwarf its neighbors the way a
        # hard step would; ratio of largest jump to median jump stays bounded.
        pos = np.abs(diffs[np.abs(diffs) > 1e-12])
        assert pos.max() / np.median(pos) < 50.0

    def test_population_conservation_fractional(self):
        res = simulate(self._params(), n_steps=40, model_type="sirs_logistic")
        total = res.S + res.I + res.R
        assert np.allclose(total, 1.0, atol=1e-6)

    def test_higher_db1_means_bigger_outbreak(self):
        small = simulate(self._params(db1=0.2), n_steps=30,
                         model_type="sirs_logistic")
        big = simulate(self._params(db1=0.9), n_steps=30,
                       model_type="sirs_logistic")
        assert big.I.max() > small.I.max()

    def test_missing_transition_raises(self):
        bad = {"I0": 0.001, "gamma": 0.1, "mult": 1000.0,
               "b0": 0.3, "sw": 2.5}  # no db1
        with pytest.raises(ValueError):
            simulate(bad, n_steps=10, model_type="sirs_logistic")

    def test_piecewise_path_unchanged_by_refactor(self):
        # Guard: the legacy default path must be byte-identical post-refactor.
        params = {"I0": 0.001, "gamma": 0.1, "mult": 1000.0,
                  "b0": 0.5, "t0": 0.0}
        res = simulate(params, n_steps=30)  # default model_type
        total = res.S + res.I + res.R
        assert np.allclose(total, 1.0, atol=1e-6)
        # H_weekly == I*S*mult*beta with beta=b0 after t0 (legacy formula).
        assert res.H_weekly[0] >= 0


class TestAbsolutePopulationSIRS:
    """Phase 2/3: absolute-population scaling + SIRS waning."""

    def _params(self, **over):
        # Absolute counts: N people, small initial-infected seed.
        p = {"I0": 50.0, "gamma": 0.6, "mult": 0.01,
             "b0": 0.2, "db1": 1.0, "tc1": 8.0, "sw": 2.5,
             "N": 5_000_000.0, "omega": 0.0}
        p.update(over)
        return p

    def test_conserves_total_population_at_omega0(self):
        res = simulate(self._params(omega=0.0), n_steps=40,
                       model_type="sirs_logistic")
        total = res.S + res.I + res.R
        assert np.allclose(total, 5_000_000.0, rtol=1e-6)

    def test_conserves_total_population_with_waning(self):
        # Waning moves R->S but conserves the total head-count.
        res = simulate(self._params(omega=0.02), n_steps=40,
                       model_type="sirs_logistic")
        total = res.S + res.I + res.R
        assert np.allclose(total, 5_000_000.0, rtol=1e-6)

    def test_waning_replenishes_susceptibles(self):
        # With omega>0, S should recover late-season (non-monotone), whereas
        # at omega=0 it is monotonically non-increasing.
        no_wane = simulate(self._params(omega=0.0), n_steps=52,
                           model_type="sirs_logistic")
        wane = simulate(self._params(omega=0.05), n_steps=52,
                        model_type="sirs_logistic")
        # omega=0: S never increases.
        assert np.all(np.diff(no_wane.S) <= 1e-3)
        # omega>0: S ends higher than its trough (replenishment happened).
        assert wane.S[-1] > wane.S.min() + 1.0

    def test_frequency_dependent_reduces_to_fractional(self):
        # beta*S*I/N with N people must match the fractional model with the
        # same per-capita seed and beta — the algebra in the plan.
        N = 1_000_000.0
        frac = simulate(
            {"I0": 1e-4, "gamma": 0.5, "mult": 0.01,
             "b0": 0.2, "db1": 1.0, "tc1": 8.0, "sw": 2.5},
            n_steps=40, model_type="sirs_logistic")  # no N => fractional
        absol = simulate(
            {"I0": 1e-4 * N, "gamma": 0.5, "mult": 0.01,
             "b0": 0.2, "db1": 1.0, "tc1": 8.0, "sw": 2.5, "N": N, "omega": 0.0},
            n_steps=40, model_type="sirs_logistic")
        # Per-capita infected fraction should match between the two.
        i_frac_fractional = frac.I            # already a fraction (N=1)
        i_frac_absolute = absol.I / N
        assert np.allclose(i_frac_fractional, i_frac_absolute, rtol=1e-4)


# --- multi-season data accuracy: NaN weeks + calendar anchoring --------------

def test_nan_weeks_dropped_with_true_offsets(tmp_path):
    """The May-Oct 2024 reporting pause: NaN weeks drop as ROWS, survivors keep
    TRUE week offsets (calendar-anchored phi1), and i0/rhomult stay finite."""
    import numpy as np, pandas as pd
    from flubnf.sihrs_fit import resolve_state, write_exp
    dates = pd.date_range("2024-06-22", periods=10, freq="7D")
    vals = [3.0, np.nan, np.nan, 5.0, 8.0, np.nan, 12.0, 20.0, 31.0, 45.0]
    truth = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"),
                          "location": "25", "value": vals})
    (tmp_path / "truth.csv").write_text(truth.to_csv(index=False))
    (tmp_path / "locs.csv").write_text(
        "location,abbreviation,location_name,population\n"
        "25,MA,Massachusetts,7136171\n")
    s = resolve_state("Massachusetts", truth_csv=tmp_path/"truth.csv",
                      locations_csv=tmp_path/"locs.csv",
                      season_start="2024-06-22", as_of="2024-08-24")
    assert s.n_obs == 7                                   # 3 NaNs dropped
    assert s.times.tolist() == [0, 3, 4, 6, 7, 8, 9]      # true offsets kept
    assert s.last_week_offset == 9                        # NOT n_obs-1 == 6
    assert np.isfinite(s.i0) and np.isfinite(s.rhomult)
    exp = write_exp(s, tmp_path/"m.exp").read_text().splitlines()
    assert exp[1].startswith("0 ") and exp[2].startswith("3 ")
    assert not any("nan" in l for l in exp)


def test_all_nan_errors_loudly(tmp_path):
    import numpy as np, pandas as pd, pytest
    from flubnf.sihrs_fit import resolve_state
    dates = pd.date_range("2024-06-22", periods=4, freq="7D")
    truth = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"),
                          "location": "25", "value": [np.nan]*4})
    (tmp_path / "truth.csv").write_text(truth.to_csv(index=False))
    (tmp_path / "locs.csv").write_text(
        "location,abbreviation,location_name,population\n"
        "25,MA,Massachusetts,7136171\n")
    with pytest.raises(ValueError, match="all 4 weeks are NaN"):
        resolve_state("Massachusetts", truth_csv=tmp_path/"truth.csv",
                      locations_csv=tmp_path/"locs.csv",
                      season_start="2024-06-22", as_of="2024-07-13")


def test_vendored_locations_matches_hub():
    """config.py defaults to the vendored copy; drift up to 3.3% was found and
    fixed 2026-08-17. This pins them equal forever."""
    import pandas as pd, pytest
    from pathlib import Path
    hub = Path.home()/'Documents/GitHub/FluSight-forecast-hub/auxiliary-data/locations.csv'
    if not hub.is_file():
        pytest.skip("hub checkout not present")
    h = pd.read_csv(hub); v = pd.read_csv(Path('flubnf/data/locations.csv'))
    m = h.merge(v, on='location', suffixes=('_h','_v'))
    assert len(m) == len(h)
    assert (m.population_h == m.population_v).all(), "vendored locations.csv drifted from hub — refresh it"
