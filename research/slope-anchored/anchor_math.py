"""Slope-anchored transmission: the arithmetic, in one place.

This module is imported by BOTH the engine-venv runner (python 3.10, inside
the particle filter) and the analysis-venv scorer (python 3.12). It therefore
depends on numpy and nothing else, and it holds every formula the member uses
so that the filter's forward propagation and the scorer's implied-peak
propagation cannot drift apart.

It is part of the pre-registration: research/slope-anchored/gate.py hashes
gate.py and this file together, and that hash travels in every results JSON.

=============================================================================
THE ALGEBRA, AGAINST THE SIHRS AS IMPLEMENTED
=============================================================================
flubnf/templates/SIHRS_pop_min.bngl, absolute counts, N fixed, weeks as the
time unit:

    dS/dt = -beta(t) S I / N + omega R
    dI/dt = +beta(t) S I / N - gamma I
    dH/dt =  rho gamma I - gammaH H
    dR/dt = (1-rho) gamma I + gammaH H - omega R
    dHadm/dt = rho gamma I                (the reported flux, times mult)

    beta0   = Reff * gamma / s0
    beta(t) = beta0 * exp( eps1 * cos(2 pi (t - phi1) / 52) )

Write s(t) = S(t)/N. The model's effective reproduction number is

    R_eff(t) = beta(t) s(t) / gamma
             = Reff * exp( eps1 cos(2 pi (t - phi1)/52) ) * s(t) / s0     (1)

NOTE that the fitted parameter `Reff` is NOT R_eff at the origin: it is
R_eff stripped of both the harmonic factor and the depletion factor. Equation
(1) is the object the anchor sets.

The infected compartment grows at

    d log I / dt = beta(t) s(t) - gamma = gamma ( R_eff(t) - 1 )          (2)

The fitted observable is the INTEGRATED weekly admission flux,
mult * (Hadm(t) - Hadm(t-1)) = mult rho gamma int I dt. In an exponential
phase the weekly integral of I grows at the same rate as I itself, so an
observed weekly log-growth g (per week) estimates d log I / dt directly and
(2) inverts to

    R* = 1 + g / gamma                                                   (3)

which is the anchor. The tasking's expression, R = (g/gamma + 1)/S(t0), is
(3) divided by the susceptible fraction: that is beta/gamma, the scale-free
transmissibility, not R_eff. Both appear below; (3) is the quantity the
member fixes and the transmissibility is what is held constant forward.

SETTING IT. At the forecast origin t0 the filter's cloud carries a per-particle
susceptible fraction s_i(t0) (Cloud.species, the S column over N) and the
particle's own eps1_i, phi1_i. Solving (1) for the value of `Reff` that makes
R_eff(t0) = R*:

  harmonic RETAINED (the primary member):
      Reff_i  <-  R* * s0 / ( s_i(t0) * exp(eps1_i cos(2 pi (t0 - phi1_i)/52)) )
      eps1_i, phi1_i unchanged -- the calendar term keeps moving beta forward.

  harmonic DISABLED (the reported-only mechanism control):
      eps1_i  <-  0
      Reff_i  <-  R* * s0 / s_i(t0)
      so beta is CONSTANT forward at R* gamma / s_i(t0) and therefore
      R_eff(t) = R* s_i(t) / s_i(t0): depletion and waning alone turn it.

Nothing is fitted. `Reff` is overwritten only in the copy of theta used for
forward propagation, after the last likelihood evaluation, so the anchored
value is never a posterior draw and never has to respect the prior box.
"""
from __future__ import annotations

import numpy as np

TWO_PI_OVER_52 = 2.0 * np.pi / 52.0

# --- frozen constants (also re-exported by gate.py, which is the record) ----
V_SIG = 0.075           # prior variance of the PERSISTENT weekly log-growth
                        # signal; measured, see growth_estimate's docstring
R_DISP = 20.0           # frozen NB dispersion used in the noise variance
MAX_GAP_WEEKS = 2       # the two anchor points may be at most this far apart
R_STAR_LO = 0.70        # clip box on the anchored R_eff at the origin
R_STAR_HI = 1.30
S_FRAC_FLOOR = 0.05     # a degenerate particle may not divide by ~0


# ---------------------------------------------------------------------------
# 1. the growth estimate, with its guards
# ---------------------------------------------------------------------------

def growth_estimate(y, t, *, k: int = 2, v_sig: float = V_SIG,
                    r_disp: float = R_DISP,
                    max_gap: int = MAX_GAP_WEEKS) -> dict:
    """Vintage-true weekly log-growth at the forecast origin, shrunk to zero.

    `y` and `t` are StateSetup.observed and StateSetup.times -- the vintage
    series ending at the origin, with TRUE week offsets, so a dropped week is
    visible as a gap rather than silently compressed.

    k = 2 is the two-point rule the project's own R_eff audit measured against
    the filter (research record 2026-08-23): at turn weeks its directional AUC
    is 0.755 against the model R_eff's 0.717, and its implied R = 1 crossing
    lands within one week of the observed peak 70.1% of the time against
    57.7%. k = 4 is an ordinary-least-squares slope of log y on t over the last
    four points, registered as the robustness arm and never used for selection.

    SHRINKAGE. A two-point log-ratio of negative-binomial counts has
    variance (1/y1 + 1/r) + (1/y0 + 1/r) before the dt^2 division, so the
    estimator is noisy exactly where counts are small -- the regime the COVID
    autopsy showed is dangerous to anchor on. The estimate is shrunk to zero
    growth (persistence, this project's measured point-forecast ceiling) by

        w = v_sig / (v_sig + v_noise),      g_hat = w * g_raw

    v_sig = 0.075 is MEASURED, before any fit of this candidate, by variance
    components on vintage truth over the exact gate panel (6 states x 85 sealed
    as-of dates x 3 seasons, 510 origins; the computation is reproduced by
    research/slope-anchored/calibrate.py):

        k = 2:  var(g_raw) 0.2779, median v_noise 0.1327  ->  v_sig 0.145
        k = 4:  var(g_raw) 0.0879, median v_noise 0.0132  ->  v_sig 0.075

    The two disagree for a reason that decides which to use. The member HOLDS
    R* fixed across the four-week horizon, so the quantity worth preserving is
    the PERSISTENT component of weekly log-growth. The four-point slope
    averages one-week transients away and its variance-components estimate
    isolates that persistent component (0.075); the two-point figure (0.145)
    also contains transients that will not survive the horizon and should be
    shrunk. v_sig = 0.075 is therefore the primary, and 0.145 -- "trust the
    transients too" -- is one of the two registered sensitivity arms.

    r_disp = 20 is the pooled median fitted dispersion across the three sealed
    seasons (23.6 / 18.2 / 21.8).

    CONSEQUENCE, STATED BEFORE THE FITS. At the panel's counts v_noise is
    0.105 to 0.26, so w lands near 0.36 to 0.42 and sd(g_hat) = sqrt(v_sig * w)
    is about 0.17, i.e. an R* spread of roughly 0.08 in R_eff units. That is
    correct shrinkage-estimator behaviour (a posterior mean is less variable
    than the truth), and it means the member sits close to R_eff = 1 by design.
    Two things follow and are registered rather than discovered: the member
    will not blow up at takeoff, and it will not turn sharply either -- it must
    rely on depletion, waning and the retained harmonic, which is exactly what
    gate 2 measures.

    Degenerate inputs return w = 0 rather than a number: a non-positive count,
    a gap wider than `max_gap`, or too few points all collapse the member to
    "hold R_eff at 1", which is the graceful failure, not an extrapolation of
    noise. NO completeness correction is applied to the newest point; that
    mechanism was killed twice in this project (cross-season and rolling), and
    its implied bias here is reported instead.
    """
    y = np.asarray(y, dtype=float)
    t = np.asarray(t, dtype=float)
    out = {"k": int(k), "g_raw": 0.0, "v_noise": float("inf"), "w": 0.0,
           "g_hat": 0.0, "reason": "ok", "n_used": 0, "span_weeks": 0.0}
    if y.size < k or t.size != y.size:
        out["reason"] = "too_few_points"
        return out
    yy, tt = y[-k:], t[-k:]
    if not np.all(np.isfinite(yy)) or np.any(yy <= 0):
        out["reason"] = "nonpositive_or_missing"
        return out
    span = float(tt[-1] - tt[0])
    out["n_used"], out["span_weeks"] = int(k), span
    if span <= 0 or span > max_gap * (k - 1):
        out["reason"] = "gap_too_wide"
        return out
    ly = np.log(yy)
    per_point_var = 1.0 / yy + 1.0 / float(r_disp)
    if k == 2:
        g_raw = float((ly[1] - ly[0]) / span)
        v_noise = float(per_point_var.sum() / span ** 2)
    else:
        tc = tt - tt.mean()
        sxx = float((tc ** 2).sum())
        if sxx <= 0:
            out["reason"] = "degenerate_design"
            return out
        g_raw = float((tc * ly).sum() / sxx)
        # var of an OLS slope with independent, heteroscedastic points
        v_noise = float((tc ** 2 * per_point_var).sum() / sxx ** 2)
    w = float(v_sig / (v_sig + v_noise))
    out.update(g_raw=g_raw, v_noise=v_noise, w=w, g_hat=w * g_raw)
    return out


def r_star(g_hat: float, gamma: float, *, lo: float = R_STAR_LO,
           hi: float = R_STAR_HI) -> dict:
    """Equation (3), clipped.

    The box [0.70, 1.30] is data-derived and frozen: across the 156 sealed
    reference fits the filter's own R_eff spans 0.805 to 1.498 with every
    season's interquartile range inside [0.87, 1.15], and the audit's
    skill-by-R_eff table measures relWIS 2.6 to 3.9 once the origin R_eff
    exceeds 1.2. The box contains the bulk of the observed range and stops
    just past the cliff rather than deep inside it.
    """
    raw = 1.0 + float(g_hat) / float(gamma)
    val = min(max(raw, lo), hi)
    return {"r_star_raw": raw, "r_star": val,
            "clipped_low": bool(raw < lo), "clipped_high": bool(raw > hi)}


# ---------------------------------------------------------------------------
# 2. the anchored parameter vector
# ---------------------------------------------------------------------------

def harmonic_factor(eps1, phi1, t) -> np.ndarray:
    return np.exp(np.asarray(eps1, float)
                  * np.cos(TWO_PI_OVER_52 * (float(t) - np.asarray(phi1, float))))


def model_reff(reff, eps1, phi1, s_frac, s0: float, t) -> np.ndarray:
    """Equation (1): the filter's OWN R_eff at time t, per particle."""
    return (np.asarray(reff, float) * harmonic_factor(eps1, phi1, t)
            * np.asarray(s_frac, float) / float(s0))


def anchored_reff(rstar: float, s_frac, s0: float, eps1, phi1, t0,
                  harmonic: bool, s_floor: float = S_FRAC_FLOOR) -> np.ndarray:
    """The value `Reff` must take so that R_eff(t0) equals `rstar`."""
    s = np.maximum(np.asarray(s_frac, float), s_floor)
    h = harmonic_factor(eps1, phi1, t0) if harmonic else 1.0
    return float(rstar) * float(s0) / (s * h)


def apply_anchor(theta: np.ndarray, names, rstar: float, s_frac, s0: float,
                 t0: float, harmonic: bool) -> np.ndarray:
    """A COPY of theta with the transmission columns re-levelled.

    Only `Reff__FREE` (and `eps1__FREE`, when the harmonic is disabled) move.
    mult, r and phi1 are untouched, so the observation model and the
    ascertainment level are exactly the filter's.
    """
    names = list(names)
    th = np.array(theta, dtype=float, copy=True)
    iR = names.index("Reff__FREE")
    iE = names.index("eps1__FREE")
    iP = names.index("phi1__FREE")
    th[:, iR] = anchored_reff(rstar, s_frac, s0, th[:, iE], th[:, iP], t0,
                              harmonic)
    if not harmonic:
        th[:, iE] = 0.0
    return th


# ---------------------------------------------------------------------------
# 3. the deterministic skeleton, for the turn gate
# ---------------------------------------------------------------------------

def propagate(reff, eps1, phi1, mult, S, I, N, s0: float, t0, n_weeks: int,
              gamma: float, rho: float, gammaH: float, omega: float,
              steps: int = 7):
    """Vectorised RK4 over particles; (n_weeks, P) ascertained weekly admissions.

    Byte-for-byte the propagator of the 2026-08-23 R_eff audit
    (context/reff/implied_peak.py), including its two conventions: H is
    reconstructed from its quasi-steady value rho*gamma*I/gammaH (H/N ~ 4e-4,
    so the approximation moves nothing) and R is the remainder of N. Mirroring
    it exactly is the point -- the audit's measured production numbers are this
    gate's comparators, so the member must be measured on the same instrument.
    """
    reff = np.asarray(reff, float)
    eps1 = np.asarray(eps1, float)
    phi1 = np.asarray(phi1, float)
    mult = np.asarray(mult, float)
    S = np.asarray(S, float).copy()
    I = np.asarray(I, float).copy()
    beta0 = reff * gamma / s0
    H = rho * gamma * I / gammaH
    R = np.maximum(N - S - I - H, 0.0)
    dt = 1.0 / steps
    out = np.empty((n_weeks, S.size))
    t = np.asarray(t0, float).copy()

    def deriv(tt, S, I, H, R):
        b = beta0 * np.exp(eps1 * np.cos(TWO_PI_OVER_52 * (tt - phi1)))
        inf = b * S * I / N
        return (-inf + omega * R, inf - gamma * I,
                rho * gamma * I - gammaH * H,
                (1 - rho) * gamma * I + gammaH * H - omega * R,
                rho * gamma * I)

    for k in range(n_weeks):
        adm = np.zeros_like(S)
        for _ in range(steps):
            k1 = deriv(t, S, I, H, R)
            k2 = deriv(t + dt / 2, S + dt / 2 * k1[0], I + dt / 2 * k1[1],
                       H + dt / 2 * k1[2], R + dt / 2 * k1[3])
            k3 = deriv(t + dt / 2, S + dt / 2 * k2[0], I + dt / 2 * k2[1],
                       H + dt / 2 * k2[2], R + dt / 2 * k2[3])
            k4 = deriv(t + dt, S + dt * k3[0], I + dt * k3[1],
                       H + dt * k3[2], R + dt * k3[3])
            S = np.maximum(S + dt / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]), 0)
            I = np.maximum(I + dt / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]), 0)
            H = np.maximum(H + dt / 6 * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2]), 0)
            R = np.maximum(R + dt / 6 * (k1[3] + 2 * k2[3] + 2 * k3[3] + k4[3]), 0)
            adm += dt / 6 * (k1[4] + 2 * k2[4] + 2 * k3[4] + k4[4])
            t = t + dt
        out[k] = adm * mult
    return out


def weighted_quantile(x, w, qs=(0.025, 0.5, 0.975)):
    x = np.asarray(x, float)
    w = np.asarray(w, float)
    o = np.argsort(x)
    c = np.cumsum(w[o])
    c = c / c[-1]
    return [float(np.interp(q, c, x[o])) for q in qs]
