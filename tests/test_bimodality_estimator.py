"""The bimodality estimator must separate an annual model from a biannual one.

A "1 wave" answer is only informative if the estimator can say 2 when 2 is true.
These are the control cases: a parameter set the memo's repertoire sweep says
lives in the bimodal region, and one that does not, both integrated on the
production simulator at the production COVID gamma.

They also pin the window-edge bug found on 2026-08-22: counting waves in a
52-week slice reports one annual peak twice when the slice boundary lands near
it, so a purely annual model reads as bimodal. `peaks_per_year` drops the
boundary indices and divides by the number of years read.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
REPORT = REPO / "research/covid-phase0/gate_a_report.py"

pytestmark = pytest.mark.skipif(
    not REPORT.is_file(),
    reason="research/ is not tracked in the public repository (see "
           "docs/RELEASE-1.0.md); this suite runs where the tree is present")


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("gate_a_report", REPORT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _p(R0, eps1, waning_weeks):
    from flubnf.profiles import COVID
    return dict(N=1.0e7, s0=0.85, i0=1.0e-4, R0=R0, eps1=eps1, phi1=20.0,
                eps2=0.0, phi2=0.0, gamma=COVID.fixed.gamma_per_week,
                rho=COVID.fixed.rho, gammaH=COVID.fixed.gammaH_per_week,
                omega=1.0 / waning_weeks, mult=0.05, impr=0.0)


class TestControls:
    def test_a_known_bimodal_set_reads_as_two(self, mod):
        """R0 3.0, eps1 0.50, 22-week waning. This is the memo's central claim
        reproduced on the production simulator: ONE annual harmonic, no eps2,
        two epidemics a year, unlocked by omega alone."""
        d = mod.peaks_per_year(_p(3.0, 0.50, 22.0))
        assert d["peaks_per_year"] == pytest.approx(2.0)
        assert d["trough_to_peak"] > 3.0

    def test_a_known_annual_set_reads_as_one(self, mod):
        d = mod.peaks_per_year(_p(2.0, 0.35, 52.0))
        assert d["peaks_per_year"] == pytest.approx(1.0)

    def test_influenza_waning_does_not_reach_two(self, mod):
        """The asymmetry the whole exercise rests on: hold everything else and
        slow the waning to a year, and the second epidemic disappears."""
        fast = mod.peaks_per_year(_p(3.0, 0.50, 22.0))["peaks_per_year"]
        slow = mod.peaks_per_year(_p(3.0, 0.50, 52.0))["peaks_per_year"]
        assert fast >= 1.9 > slow


class TestWindowEdgeBug:
    def test_a_fifty_two_week_slice_can_double_count_one_peak(self, mod):
        """The bug this estimator exists to avoid, demonstrated rather than
        described. Same parameters, two estimators, different answers."""
        from flubnf.simulate_sihrs import simulate_sihrs
        from flubnf.unimodal_guard import count_waves
        p = _p(4.48, 0.44, 26.0)
        hw = np.asarray(simulate_sihrs(p, n_weeks=52 * 10).H_weekly, float)
        naive = count_waves(hw[-52:])
        corrected = mod.peaks_per_year(p)["peaks_per_year"]
        assert naive == 2                      # the artifact
        assert corrected == pytest.approx(1.0)  # the truth

    def test_boundary_indices_are_never_counted(self, mod):
        d = mod.peaks_per_year(_p(3.0, 0.50, 22.0), years=10, read=3)
        n = 52 * 3
        assert all(0 < w < n - 1 for w in d["peak_weeks_in_window"])
