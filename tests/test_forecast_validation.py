"""A forecast that is structurally invalid must never be emitted.

Regression cover for the most expensive defect measured in this pipeline. On the
2025-26 SIR backtest, 11 of 4784 cells (0.23%) carried 49.4% of ALL WIS because
`clip_forecast` pushed every quantile of a blown-up forecast onto the same
ceiling, producing a zero-width point mass:

    New York   week 26   last observed 3870   q50 = q975 = 77400 (= 20 x 3870)
    Louisiana            last observed  ...   q50 = q975 =  8660 (= 20 x  433)

Guarding those cells moved relWIS 2.291 -> 1.166 and New York 10.739 -> 0.686.
The tests below use those exact numbers as fixtures so the failure cannot
silently return. See docs/RETROSPECTIVE_2026-07.md.
"""
from __future__ import annotations

import numpy as np
import pytest

from flubnf.quantiles import (FLUSIGHT_QUANTILES, QuantileForecast,
                              clip_forecast, diagnose_forecast)

NQ = len(FLUSIGHT_QUANTILES)


def _healthy(n_h: int = 4) -> QuantileForecast:
    col = np.linspace(50.0, 400.0, NQ)
    return QuantileForecast(
        horizons=tuple(range(1, n_h + 1)),
        quantile_levels=FLUSIGHT_QUANTILES,
        quantiles=np.tile(col[:, None], (1, n_h)),
        point=np.full(n_h, float(np.median(col))),
    )


def _degenerate(value: float, n_h: int = 4) -> QuantileForecast:
    return QuantileForecast(
        horizons=tuple(range(1, n_h + 1)),
        quantile_levels=FLUSIGHT_QUANTILES,
        quantiles=np.full((NQ, n_h), value),
        point=np.full(n_h, value),
    )


class TestHealthyForecastPasses:
    def test_usable(self):
        assert diagnose_forecast(_healthy()).usable

    def test_truthy(self):
        """`if diagnose_forecast(qf):` must read naturally at call sites."""
        assert bool(diagnose_forecast(_healthy()))

    def test_legitimate_surge_is_not_flagged(self):
        """A real surge well under the step limit must pass untouched."""
        qf = _healthy()
        d = diagnose_forecast(qf, last_observed=60.0)   # median ~225 = 3.75x
        assert d.usable, d.reasons


class TestDegenerateIsRejected:
    @pytest.mark.parametrize("value,last_obs", [(77400.0, 3870.0),
                                                (8660.0, 433.0)])
    def test_the_observed_failures(self, value, last_obs):
        """The exact New York and Louisiana cells from the 2025-26 backtest."""
        d = diagnose_forecast(_degenerate(value), cap=value,
                              last_observed=last_obs)
        assert not d.usable
        assert d.degenerate_horizons == (1, 2, 3, 4)
        assert any("zero-width" in r for r in d.reasons)

    def test_zero_width_caught_without_cap_or_last_observed(self):
        """Zero width is invalid on its own -- no context required."""
        d = diagnose_forecast(_degenerate(500.0))
        assert not d.usable
        assert any("zero-width" in r for r in d.reasons)

    def test_absurd_level_caught(self):
        qf = _healthy()
        d = diagnose_forecast(qf, last_observed=1.0)    # median ~225 = 225x
        assert not d.usable
        assert any("exceeds" in r for r in d.reasons)

    def test_non_monotone_caught(self):
        qf = _healthy()
        q = qf.quantiles.copy()
        q[5, 0], q[6, 0] = q[6, 0], q[5, 0]             # swap two levels
        d = diagnose_forecast(QuantileForecast(qf.horizons, qf.quantile_levels,
                                               q, qf.point))
        assert not d.usable
        assert any("non-monotone" in r for r in d.reasons)

    def test_reaching_the_cap_is_flagged(self):
        """Hitting the sanity cap means clipping WOULD flatten it -- warn first."""
        qf = _healthy()
        d = diagnose_forecast(qf, cap=float(qf.quantiles.max()))
        assert not d.usable
        assert any("cap" in r for r in d.reasons)

    def test_non_finite_caught(self):
        qf = _healthy()
        q = qf.quantiles.copy()
        q[0, 0] = np.inf
        d = diagnose_forecast(QuantileForecast(qf.horizons, qf.quantile_levels,
                                               q, qf.point))
        assert not d.usable


class TestClipStillProducesTheBug:
    """Pin the reason clip_forecast must not be the remedy on its own."""

    def test_clipping_a_blowup_creates_a_point_mass(self):
        qf = QuantileForecast(
            horizons=(1,), quantile_levels=FLUSIGHT_QUANTILES,
            quantiles=np.linspace(1e5, 1e9, NQ)[:, None],
            point=np.array([1e7]),
        )
        clipped = clip_forecast(qf, 77400.0)
        col = clipped.quantiles[:, 0]
        assert np.allclose(col, 77400.0), "expected the documented failure mode"
        assert not diagnose_forecast(clipped).usable, (
            "diagnose_forecast must reject what clip_forecast produces here")


class TestPersistenceFallbackIsValid:
    def test_fallback_passes_its_own_check(self):
        """The substitute must not itself be structurally invalid."""
        from flubnf.baseline_forecast import persistence_quantile_forecast
        obs = np.array([10., 14., 22., 35., 51., 68., 90., 120.])
        qf = persistence_quantile_forecast(obs, (1, 2, 3, 4))
        d = diagnose_forecast(qf, last_observed=float(obs[-1]))
        assert d.usable, d.reasons
