"""The filter must integrate the SAME mechanism the BNGL model defines, and its
posterior must be a real posterior rather than a collapsed ensemble.

Two failure modes this project has already paid for, both guarded here:

* **A fake posterior.** The sampler bug (ESS ~ 9 on 1 chain) invalidated two
  published conclusions before it was caught. A particle filter fails the same
  way through depletion, so ESS is asserted, not merely reported.
* **A silently different mechanism.** `particle_filter.propagate` re-implements
  the ODEs that `templates/SIHRS_pop.bngl` defines. If the two drift apart the
  filter stops being the SIHRS model and no scoring comparison means anything.
  `TestMatchesTheBnglMechanism` pins them together.

The jitter tests encode the measured U-shape: too little jitter is
overconfident (relWIS 1.549 at 0.03), too much forgets the mechanism (1.084 at
0.60). What is testable cheaply is the direction -- spread must increase
monotonically with jitter -- not the optimum, which is a scoring question.
"""
from __future__ import annotations

import numpy as np
import pytest

from flubnf.particle_filter import (GAMMA_W, OMEGA, RHO, Particles, ess,
                                    forecast, jitter_params, propagate,
                                    resample, update)

BOUNDS = dict(Reff=(0.6, 2.5), eps1=(0.0, 1.0), phi1=(0.0, 52.0),
              mult=(0.002, 1.0), r=(0.1, 40.0))
N_POP, S0, I0 = 5_000_000.0, 0.85, 2e-4


def make(n=400, seed=0, **over):
    rng = np.random.default_rng(seed)
    kw = dict(
        Reff=rng.uniform(0.8, 1.6, n), eps1=rng.uniform(0.0, 0.4, n),
        phi1=rng.uniform(0.0, 52.0, n), mult=rng.uniform(0.01, 0.2, n),
        r=rng.uniform(2.0, 20.0, n),
        S=np.full(n, N_POP * S0), I=np.full(n, N_POP * I0), H=np.zeros(n),
        R=np.full(n, N_POP * (1 - S0 - I0)), w=np.full(n, 1.0 / n))
    kw.update(over)
    return Particles(**kw)


class TestPropagation:
    def test_compartments_stay_nonnegative_and_conserved(self):
        p = make()
        propagate(p, 0.0, 8.0, N_POP, S0)
        tot = p.S + p.I + p.H + p.R
        assert np.all(p.S >= 0) and np.all(p.I >= 0)
        assert np.all(p.H >= 0) and np.all(p.R >= 0)
        # S+I+H+R is closed in this model: no births, no deaths.
        assert np.allclose(tot, N_POP, rtol=1e-6)

    def test_admissions_are_positive_and_scale_with_mult(self):
        """`mult` is pure ascertainment -- it scales the observable and must not
        touch the dynamics."""
        a = make(mult=np.full(400, 0.05))
        b = make(mult=np.full(400, 0.10))
        adm_a = propagate(a, 0.0, 4.0, N_POP, S0)
        adm_b = propagate(b, 0.0, 4.0, N_POP, S0)
        assert np.all(adm_a > 0)
        assert np.allclose(adm_b, 2.0 * adm_a, rtol=1e-9)
        assert np.allclose(a.I, b.I, rtol=1e-9)      # dynamics untouched

    def test_subcritical_transmission_decays(self):
        p = make(Reff=np.full(400, 0.7), eps1=np.zeros(400))
        i0 = p.I.copy()
        propagate(p, 0.0, 6.0, N_POP, S0)
        assert np.all(p.I < i0)

    def test_propagation_is_deterministic(self):
        """No RNG in propagate -- all stochasticity is jitter and resampling."""
        a = propagate(make(seed=1), 0.0, 3.0, N_POP, S0)
        b = propagate(make(seed=1), 0.0, 3.0, N_POP, S0)
        assert np.array_equal(a, b)


class TestMatchesTheBnglMechanism:
    """The BNGL template is the definition; this integrates it. If these drift,
    the filter is a different model wearing the same name."""

    def test_rk4_matches_a_high_accuracy_integrator(self):
        """Write the rate laws out independently and integrate them to 1e-10.

        This checks two things at once that a finite-difference check cannot:
        that the ODE SYSTEM is right, and that the daily fixed step is fine
        enough. `propagate` cannot take a sub-daily interval -- nsteps rounds to
        zero -- so the derivative is validated through the solution, not
        through a one-substep difference.
        """
        from scipy.integrate import solve_ivp

        Reff, eps1, phi1, mult = 1.3, 0.2, 18.0, 0.05
        gammaH = 1.17
        beta0 = Reff * GAMMA_W / S0

        def rhs(t, y):
            S, I, H, R, A = y
            b = beta0 * np.exp(eps1 * np.cos(2 * np.pi * (t - phi1) / 52))
            inf = b * S * I / N_POP
            return [-inf + OMEGA * R,
                    inf - GAMMA_W * I,
                    RHO * GAMMA_W * I - gammaH * H,
                    (1 - RHO) * GAMMA_W * I + gammaH * H - OMEGA * R,
                    RHO * GAMMA_W * I]

        y0 = [N_POP * S0, N_POP * I0, 0.0, N_POP * (1 - S0 - I0), 0.0]
        ref = solve_ivp(rhs, (0.0, 4.0), y0, rtol=1e-10, atol=1e-6,
                        dense_output=True).sol(4.0)

        p = make(n=1, Reff=np.array([Reff]), eps1=np.array([eps1]),
                 phi1=np.array([phi1]), mult=np.array([mult]),
                 r=np.array([5.0]))
        adm = propagate(p, 0.0, 4.0, N_POP, S0)

        for name, got, want in (("S", p.S[0], ref[0]), ("I", p.I[0], ref[1]),
                                ("H", p.H[0], ref[2]), ("R", p.R[0], ref[3])):
            assert float(got) == pytest.approx(float(want), rel=2e-3), name
        assert float(adm[0]) == pytest.approx(mult * float(ref[4]), rel=2e-3)

    def test_infection_is_frequency_dependent(self):
        """beta*S*I/N, not beta*S*I -- this is what makes `Reff` comparable
        across states of very different size, which the pooled fits rely on.

        Tested through the EXACT invariant rather than a finite difference.
        With frequency dependence every term is homogeneous of degree one, so
        scaling (S, I, H, R, N) by c scales the whole trajectory by exactly c.
        Density-dependent transmission (beta*S*I) is degree two and breaks it.

        A naive version of this test -- double N alone and expect the force of
        infection to halve -- is off by ~6%, because a weaker infection inflow
        also lets I decay faster over the step. That is physics, not a defect.
        """
        c = 3.0
        base = make(n=1, Reff=np.array([1.3]), eps1=np.array([0.2]),
                    phi1=np.array([18.0]), mult=np.array([0.05]),
                    S=np.array([2e6]), I=np.array([1e3]), H=np.array([5.0]),
                    R=np.array([1e6]))
        scaled = make(n=1, Reff=np.array([1.3]), eps1=np.array([0.2]),
                      phi1=np.array([18.0]), mult=np.array([0.05]),
                      S=np.array([2e6 * c]), I=np.array([1e3 * c]),
                      H=np.array([5.0 * c]), R=np.array([1e6 * c]))
        a = propagate(base, 0.0, 6.0, 4e6, S0)
        b = propagate(scaled, 0.0, 6.0, 4e6 * c, S0)
        assert float(b[0]) == pytest.approx(c * float(a[0]), rel=1e-9)
        for got, want in ((scaled.S, base.S), (scaled.I, base.I),
                          (scaled.H, base.H), (scaled.R, base.R)):
            assert float(got[0]) == pytest.approx(c * float(want[0]), rel=1e-9)

    def test_waning_returns_R_to_S(self):
        p = make(n=1, Reff=np.array([0.6]), eps1=np.array([0.0]),
                 I=np.array([0.0]), R=np.array([N_POP * 0.5]),
                 S=np.array([N_POP * 0.5]))
        s0v = float(p.S[0])
        propagate(p, 0.0, 1.0, N_POP, S0)
        assert float(p.S[0]) > s0v
        assert float(p.S[0]) - s0v == pytest.approx(
            OMEGA * N_POP * 0.5, rel=0.05)

    def test_forward_simulation_matches_simulate_sihrs(self):
        """End-to-end against the independent simulator used for BNGL checks."""
        from flubnf.simulate_sihrs import simulate_sihrs
        pars = dict(N=N_POP, s0=S0, i0=I0, gamma=GAMMA_W, rho=RHO, gammaH=1.17,
                    omega=OMEGA, R0=1.25 / S0, eps1=0.15, phi1=20.0,
                    eps2=0.0, phi2=0.0, mult=0.05, impr=0.0)
        ref = np.asarray(simulate_sihrs(pars, n_weeks=20).H_weekly, float)
        p = make(n=1, Reff=np.array([1.25]), eps1=np.array([0.15]),
                 phi1=np.array([20.0]), mult=np.array([0.05]),
                 r=np.array([5.0]))
        got = np.array([float(propagate(p, float(k), 1.0, N_POP, S0)[0])
                        for k in range(20)])
        peak_ref, peak_got = ref[:20].max(), got.max()
        assert peak_got == pytest.approx(peak_ref, rel=0.05), (
            "filter ODEs diverged from the reference SIHRS simulator")


class TestWeightsAndResampling:
    def test_ess_bounds(self):
        n = 100
        assert ess(np.full(n, 1.0 / n)) == pytest.approx(n)
        degenerate = np.zeros(n)
        degenerate[0] = 1.0
        assert ess(degenerate) == pytest.approx(1.0)

    def test_resample_preserves_size_and_resets_weights(self):
        p = make(n=200)
        p.w = np.random.default_rng(0).dirichlet(np.ones(200))
        q = resample(p, np.random.default_rng(1))
        assert q.n() == 200
        assert np.allclose(q.w, 1.0 / 200)

    def test_resample_concentrates_on_high_weight_particles(self):
        p = make(n=200)
        w = np.zeros(200)
        w[:5] = 0.2                       # all mass on the first five
        p.w = w
        q = resample(p, np.random.default_rng(2))
        assert np.all(np.isin(q.Reff, p.Reff[:5]))

    def test_update_rejects_a_degenerate_ensemble(self):
        """A returned forecast from a dead filter would be scored as if real;
        `ok=False` is how the caller learns to skip the cell instead."""
        p = make(n=50, r=np.full(50, np.nan))
        out = update(p, 100.0, 0.0, N_POP, S0, np.random.default_rng(0),
                     jitter=0.1, bounds=BOUNDS)
        assert out["ok"] is False

    def test_update_keeps_ess_healthy_over_a_season(self):
        """Depletion is the filter's version of the ESS~9 sampler bug."""
        rng = np.random.default_rng(3)
        p = make(n=800, seed=5)
        truth = 200 * np.exp(-0.5 * ((np.arange(26) - 14) / 5.0) ** 2) + 20
        for k, y in enumerate(truth):
            out = update(p, float(y), float(k), N_POP, S0, rng,
                         jitter=0.25, bounds=BOUNDS)
            assert out["ok"]
        assert ess(p.w) > 0.05 * p.n(), "particle depletion"
        assert np.unique(p.Reff).size > 20, "ensemble collapsed to few particles"


class TestJitter:
    def test_liu_west_preserves_the_weighted_mean(self):
        p = make(n=4000, seed=7)
        before = np.average(p.Reff, weights=p.w)
        jitter_params(p, np.random.default_rng(0), 0.2, BOUNDS)
        assert np.average(p.Reff, weights=p.w) == pytest.approx(before, abs=0.02)

    def test_variance_is_not_inflated_by_shrinkage(self):
        """Naive additive noise grows the variance every step until the
        ensemble is a random walk; the a = sqrt(1-jitter^2) shrinkage is what
        stops that.

        NOTE the rng is created ONCE. Re-seeding inside the loop adds the same
        noise vector every step, and perfectly correlated increments accumulate
        -- that inflates the variance ~10x here and looks exactly like a broken
        shrinkage. It is a property of the test harness, not of the filter.
        """
        p = make(n=6000, seed=8)
        v0 = np.var(p.Reff)
        rng = np.random.default_rng(1)
        for _ in range(15):
            jitter_params(p, rng, 0.2, BOUNDS)
        assert np.var(p.Reff) < 2.0 * v0

    def test_jitter_alone_does_not_widen_the_ensemble(self):
        """The variance-preserving property, stated as the thing it means:
        jitter is NOT a way to inflate the prior. Measured spreads after five
        applications are 0.227 / 0.225 / 0.220 for jitter 0.05 / 0.25 / 0.50 --
        flat. Anyone reaching for `jitter` as a spread knob is misreading it."""
        spreads = []
        for j in (0.05, 0.25, 0.5):
            p = make(n=4000, seed=9)
            rng = np.random.default_rng(2)
            for _ in range(5):
                jitter_params(p, rng, j, BOUNDS)
            spreads.append(float(np.std(p.Reff)))
        assert max(spreads) / min(spreads) < 1.1

    def test_low_jitter_collapses_the_FILTERED_posterior(self):
        """Where the knob actually acts, and why relWIS is U-shaped in it.

        Reweighting plus resampling contracts the ensemble every week; jitter
        opposes that contraction, so its effect appears only through the full
        loop. The relationship is NOT monotone -- averaged over six seeds the
        filtered sd of Reff runs 0.034 / 0.120 / 0.068 at jitter 0.05 / 0.25 /
        0.50. Past a point, extra jitter scatters particles into regions the
        data rejects and reweighting culls them, so the SURVIVING ensemble
        narrows again.

        Only the robust half is asserted: low jitter collapses the posterior
        relative to moderate jitter. A single seed happens to look monotone
        (0.029 / 0.046 / 0.071 at seed 9), which is why this averages instead.
        """
        truth = 200 * np.exp(-0.5 * ((np.arange(26) - 14) / 5.0) ** 2) + 20

        def filtered_sd(j):
            out = []
            for seed in range(4):
                p = make(n=800, seed=seed)
                rng = np.random.default_rng(100 + seed)
                for k, y in enumerate(truth):
                    assert update(p, float(y), float(k), N_POP, S0, rng,
                                  jitter=j, bounds=BOUNDS)["ok"]
                out.append(float(np.std(p.Reff)))
            return float(np.mean(out))

        assert filtered_sd(0.05) < 0.5 * filtered_sd(0.25)

    def test_update_reports_a_usable_pit(self):
        """The PIT drives knob selection, so it must be a real probability from
        the predictive formed BEFORE the observation was seen."""
        rng = np.random.default_rng(0)
        p = make(n=800, seed=4)
        out = update(p, 150.0, 0.0, N_POP, S0, rng, jitter=0.25, bounds=BOUNDS)
        assert out["ok"] and 0.0 <= out["pit"] <= 1.0

    def test_bounds_are_respected(self):
        p = make(n=2000, seed=10)
        rng = np.random.default_rng(3)
        for _ in range(10):
            jitter_params(p, rng, 0.5, BOUNDS)
        for name, (lo, hi) in BOUNDS.items():
            v = getattr(p, name)
            assert v.min() >= lo and v.max() <= hi


class TestForecast:
    def test_forecast_does_not_advance_the_filter(self):
        """Forecasting must be side-effect free or next week's update starts
        from the wrong state."""
        p = make(n=300, seed=11)
        snap = (p.S.copy(), p.I.copy(), p.H.copy(), p.R.copy())
        forecast(p, 0.0, [1, 2, 3, 4], N_POP, S0, np.random.default_rng(0))
        for a, b in zip(snap, (p.S, p.I, p.H, p.R)):
            assert np.array_equal(a, b)

    def test_returns_finite_draws_at_every_horizon(self):
        out = forecast(make(n=300, seed=12), 0.0, [1, 2, 3, 4], N_POP, S0,
                       np.random.default_rng(0))
        assert set(out) == {"1", "2", "3", "4"}
        for h, draws in out.items():
            a = np.asarray(draws, float)
            assert a.size == 300 and np.all(np.isfinite(a)) and np.all(a >= 0)

    def test_uncertainty_widens_with_horizon(self):
        out = forecast(make(n=4000, seed=13), 0.0, [1, 2, 3, 4], N_POP, S0,
                       np.random.default_rng(0))
        sds = [np.std(np.log1p(np.asarray(out[str(h)], float)))
               for h in (1, 2, 3, 4)]
        assert sds[0] < sds[-1], "4-week-ahead must be wider than 1-week-ahead"
