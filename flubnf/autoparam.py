"""SUPERSEDED 2026-08-03 — do not wire into the pipeline.

This module was built to fix parameter pinning, on the belief that 78% of fits
pinned a parameter against a prior wall. That measurement came from chains with
ESS ~9 that had not mixed, and A CHAIN THAT DOES NOT MOVE LOOKS PINNED.

With a working sampler (population_size=4 + loguniform_var, now the default in
sihrs_fit.write_conf) the picture changes completely:

  * the seasonal pins this module was designed around largely vanish --
    eps1 40% -> 16%, eps2 34% -> under 8%;
  * the pins that remain are DIFFERENT parameters -- impr 19% -> 88%,
    mult 25% -> 76% -- so its central rule ("49% of pins are eps1/eps2 collapsed
    to zero, therefore drop them") was reading an artefact;
  * the sampler fix ALONE reaches relWIS 1.027 over 52 states x 5 dates versus
    1.584 before, with no round-2 refitting at all.

Kept because the decision logic is sound and independently tested (24 tests in
tests/test_autoparam.py), and because a RETARGETED version -- widening impr and
mult rather than dropping the harmonics -- may be worth revisiting once the
season sweep supplies enough as-of dates to validate it. Do not re-enable it on
the strength of the superseded measurements below.

--- ORIGINAL DESIGN NOTES (measurements now known to be sampler artefacts) ---

Automatic parameterisation: read a fit, decide what to change, refit.

It replaced the manual step -- a human looks at a fitted posterior, sees a
parameter jammed against a prior wall, moves the wall (or removes the
parameter), and refits.

Three diagnoses, not one. Of 379 pin flags across 255 fits:
  MOVABLE (51%)   mult, impr, Reff, r pushing outward. Slide the window.
  FLOOR   (49%)   eps1/eps2 collapsing to exactly 0. Cannot widen below a
                  physical floor, so DROP the parameter.
  CIRCULAR ( 7%)  phi1 (period 52), phi2 (period 26). phi=0 and phi=52 are the
                  SAME POINT, so a boundary "pin" is a wrap, not a wall.
                  (This one is still correct -- it is geometry, not sampling.)

`choose()` exists because a refit whose pins did NOT clear measured 20% WORSE
than the original, so "always take the newer fit" is the wrong rule. It compares
only forecast-time-knowable quantities -- never WIS or realised actuals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

import numpy as np

from .sihrs_fit import FITTED_PRIORS

# Phases are circular; a boundary "pin" is a wrap, not a wall.
CIRCULAR: tuple[str, ...] = ("phi1__FREE", "phi2__FREE")

# Amplitudes whose lower bound is a hard physical floor at zero. When the
# posterior collapses here the parameter is contributing nothing and should be
# removed rather than re-bounded.
FLOOR_AT_ZERO: tuple[str, ...] = ("eps1__FREE", "eps2__FREE")

# Hard physical limits no adjustment may cross.
#   mult is an ascertainment FRACTION: it cannot exceed 1.0. If it pins there,
#   the model cannot generate as many admissions as are reported, which means
#   the FIXED rho (IHR) is too small -- a different repair entirely.
PHYSICAL: dict[str, tuple[float, float]] = {
    "eps1__FREE": (0.0, 3.0),
    "eps2__FREE": (0.0, 2.0),
    "mult__FREE": (1e-4, 1.0),
    "impr__FREE": (0.0, 1e-3),
    "Reff__FREE": (0.1, 6.0),
    "r__FREE": (0.01, 200.0),
}

PIN_FRAC = 0.25      # >25% of posterior mass within...
PIN_EDGE = 0.02      # ...2% of a bound counts as pinned


@dataclass(frozen=True)
class Diagnosis:
    """What to do about each parameter, and why."""
    movable: dict[str, tuple[float, float]] = field(default_factory=dict)
    drop: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()
    circular: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.movable or self.drop)

    def describe(self) -> str:
        bits = []
        if self.movable:
            bits.append("widen " + ",".join(sorted(self.movable)))
        if self.drop:
            bits.append("drop " + ",".join(sorted(self.drop)))
        if self.blocked:
            bits.append("blocked " + ",".join(sorted(self.blocked)))
        if self.circular:
            bits.append("wrap " + ",".join(sorted(self.circular)))
        return "; ".join(bits) or "no change"


def is_pinned(samples: np.ndarray, lo: float, hi: float) -> bool:
    """Does the posterior pile up against either bound?"""
    v = np.asarray(samples, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return False
    w = hi - lo
    if w <= 0:
        return False
    return bool(np.mean(v <= lo + PIN_EDGE * w) > PIN_FRAC
                or np.mean(v >= hi - PIN_EDGE * w) > PIN_FRAC)


def diagnose(pinned: Sequence[str], medians: Mapping[str, float],
             priors: Optional[Mapping[str, tuple[float, float]]] = None) -> Diagnosis:
    """Classify each pinned parameter and propose the adjustment."""
    priors = dict(priors or FITTED_PRIORS)
    movable: dict[str, tuple[float, float]] = {}
    drop: list[str] = []
    blocked: list[str] = []
    circ: list[str] = []
    for p in pinned:
        if p in CIRCULAR:
            circ.append(p)
            continue
        if p not in priors:
            continue
        lo, hi = priors[p]
        w = hi - lo
        m = medians.get(p)
        if m is None or not np.isfinite(m):
            continue
        plo, phi = PHYSICAL.get(p, (-np.inf, np.inf))
        at_lo = m <= lo + 0.1 * w
        at_hi = m >= hi - 0.1 * w
        if at_lo and p in FLOOR_AT_ZERO and lo <= plo + 1e-12:
            drop.append(p)            # collapsed onto a physical floor -> remove
        elif at_lo:
            nlo = max(plo, lo - w)
            if nlo < lo - 1e-12:
                movable[p] = (nlo, lo + 0.5 * w)
            else:
                blocked.append(p)
        elif at_hi:
            nhi = min(phi, hi + w)
            if nhi > hi + 1e-12:
                movable[p] = (hi - 0.5 * w, nhi)
            else:
                blocked.append(p)     # e.g. mult already at 1.0
    return Diagnosis(movable=movable, drop=tuple(sorted(drop)),
                     blocked=tuple(sorted(blocked)), circular=tuple(sorted(circ)))


def next_priors(diag: Diagnosis,
                priors: Optional[Mapping[str, tuple[float, float]]] = None
                ) -> dict[str, tuple[float, float]]:
    """The prior box for the next round: widened where movable, minus the drops."""
    out = dict(priors or FITTED_PRIORS)
    out.update(diag.movable)
    for p in diag.drop:
        out.pop(p, None)
    return out


@dataclass(frozen=True)
class RoundResult:
    """One round's outcome, in forecast-time-knowable quantities ONLY.

    `end_ratio` is the fitted level at the forecast origin divided by the last
    observed value. 1.0 means the trajectory lands on the data where the
    forecast starts. It is the strongest forecast-time predictor measured
    (corr +0.740 with the forecast step; quartiles 0.23 -> collapse 0.151 and
    1.33 -> 0.933), and unlike a raw fit objective it is comparable across
    rounds whose parameter spaces differ -- which they do here, because a round
    may DROP a parameter.

    Nothing derived from the realised observation may be added to this class.
    """
    objective: float          # fit quality, lower is better (NaN if unavailable)
    n_pinned: int
    ok: bool = True
    end_ratio: float = float("nan")

    @property
    def origin_miss(self) -> float:
        """|log(end_ratio)| -- 0 is perfect, symmetric in over/under."""
        if not np.isfinite(self.end_ratio) or self.end_ratio <= 0:
            return float("inf")
        return abs(float(np.log(self.end_ratio)))


def choose(first: RoundResult, second: RoundResult, *,
           objective_tol: float = 0.02) -> str:
    """Pick which round to ship. Uses NO information from the realised outcome.

    A refit is only kept if it did not make the fit materially worse. Measured:
    when pins failed to clear, the refit was 20% WORSE on WIS -- so "always take
    the newer fit" is the wrong rule, and this is the guard against it.

    Rules, in order:
      * a failed round loses to a successful one;
      * a materially worse objective loses (>`objective_tol` relative);
      * otherwise fewer pins wins;
      * ties go to the better objective.
    """
    if not second.ok:
        return "first"
    if not first.ok:
        return "second"
    a, b = first.objective, second.objective
    if np.isfinite(a) and np.isfinite(b) and a != 0:
        if (b - a) / abs(a) > objective_tol:
            return "first"            # refit fits materially worse
    # origin miss is the primary quality signal when objectives are absent or
    # incomparable (a dropped parameter changes the parameter space).
    ma, mb = first.origin_miss, second.origin_miss
    if np.isfinite(ma) or np.isfinite(mb):
        if mb > ma + 0.10:            # refit lands materially further from the data
            return "first"
        if ma > mb + 0.10:
            return "second"
    if second.n_pinned != first.n_pinned:
        return "second" if second.n_pinned < first.n_pinned else "first"
    if np.isfinite(a) and np.isfinite(b):
        return "second" if b < a else "first"
    return "first"
