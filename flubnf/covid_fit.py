"""Profile-driven fit wiring. Additive: nothing here edits the influenza path.

WHY A SEPARATE MODULE RATHER THAN A FLAG IN sihrs_fit
-----------------------------------------------------
`flubnf/sihrs_fit.py` owns the influenza fit and three of its constants are
module-level: RHO_IHR, GAMMAH_PER_WEEK, OMEGA_PER_WEEK, plus LOG_SCALE_VARS.
Threading a profile through them would touch the code path that produced the
sealed three-season result. Instead this module composes the existing pieces:

  * `resolve_state` is called unchanged, then the disease-specific fixed values
    are swapped in with `dataclasses.replace`. `resolve_state`'s real work --
    reading the vintage, dropping NaN weeks, keeping true week offsets, pinning
    rho*mult, inverting i0 -- is reused verbatim, so the missingness policy and
    the calendar anchoring are the shipped ones, not a copy.
  * `write_conf` is called unchanged with `priors=profile.fitted_priors`, then
    ONE line is rewritten to log-scale `omega__FREE`. The conf format therefore
    has a single source of truth and cannot drift on backup_every or
    max_iterations the way a hand-copied duplicate silently did once before.

THE i0 SUBTLETY THAT BITES HERE
-------------------------------
`initial_infected_fraction` divides by `rho_mult * gamma * N`. The swap changes
BOTH rho and gamma, so i0 must be recomputed AFTER the swap, not inherited from
the influenza-parameterized call. `resolve_covid_state` does that; getting it
wrong seeds the epidemic at the wrong size and phi1 absorbs the timing error.
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Optional

from .profiles import COVID, DiseaseProfile
from .sihrs_fit import (StateSetup, initial_infected_fraction, materialize_model,
                        pin_rho_mult, resolve_state, write_conf, write_exp)

__all__ = ["resolve_for_profile", "resolve_covid_state", "write_profile_conf",
           "materialize_for_profile", "write_exp", "omega_to_months",
           "months_to_omega", "COVID_SUFFIX"]

COVID_SUFFIX = "covid"


def omega_to_months(omega: float) -> float:
    """Mean protected duration in months from the per-week waning rate."""
    return 7.0 / (float(omega) * 30.44)


def months_to_omega(months: float) -> float:
    return 7.0 / (float(months) * 30.44)


def resolve_for_profile(profile: DiseaseProfile, state: str, *,
                        truth_csv, locations_csv, season_start: str,
                        as_of: str, s0: Optional[float] = None,
                        attack_rate: Optional[float] = None) -> StateSetup:
    """`resolve_state` with this profile's fixed biology substituted in.

    The influenza profile returns exactly what `resolve_state` returns -- the
    substitution is a no-op because the profile's values ARE the shipped
    constants. tests/test_profiles.py asserts that.
    """
    import numpy as np
    f = profile.fixed
    ar = float(attack_rate if attack_rate is not None
               else np.mean(f.attack_rate_range))
    s = resolve_state(state, truth_csv=truth_csv, locations_csv=locations_csv,
                      season_start=season_start, as_of=as_of,
                      s0=float(s0 if s0 is not None else f.s0_default),
                      attack_rate=ar)
    # rho*mult is the PRODUCT, pinned from cumulative reported admissions per
    # capita over the profile's own attack rate -- it does not depend on the
    # profile's `rho` at all, only on the attack rate, which resolve_state was
    # already given. Recomputed here so the value is visibly derived from the
    # same inputs as `i0`, which does change: i0 = first_week /
    # (rho_mult * gamma * N), and gamma differs between the profiles.
    rhomult = pin_rho_mult(float(s.observed.sum()) / s.population, ar)
    i0 = initial_infected_fraction(max(float(s.observed[0]), 1.0), s.population,
                                   rhomult, f.gamma_per_week)
    return dataclasses.replace(
        s, gamma=f.gamma_per_week, rho=f.rho, rhomult=rhomult,
        gammaH=f.gammaH_per_week,
        # `omega` on StateSetup is only ever consumed as the {{OMEGA}} token.
        # When the profile fits omega the template has no such token, so this
        # value is inert; it is set to the literature centre so that anything
        # printing the setup shows a meaningful number rather than a stale one.
        omega=(f.omega_per_week if f.omega_per_week is not None
               else months_to_omega(9.0)),
        s0=float(s0 if s0 is not None else f.s0_default),
        i0=i0, attack_rate=ar)


def resolve_covid_state(state: str, **kw) -> StateSetup:
    return resolve_for_profile(COVID, state, **kw)


def materialize_for_profile(profile: DiseaseProfile, setup: StateSetup,
                            out_path, *, suffix: Optional[str] = None,
                            t_end: Optional[int] = None,
                            extra_tokens: Optional[dict] = None) -> Path:
    """Write the per-state .bngl from this profile's template.

    `materialize_model` raises on any UNRESOLVED token, which is exactly the
    check that catches a profile/template mismatch: a profile that fixes omega
    against a template that frees it leaves {{OMEGA}} unresolved and fails here
    rather than silently fitting a parameter nobody declared.
    """
    sfx = suffix or f"{setup.state.replace(' ', '_')}_{profile.key}"
    return materialize_model(setup, profile.template, out_path, sfx,
                             t_end=t_end, extra_tokens=extra_tokens)


_VAR_RE = "^(uniform_var|loguniform_var) = {name} "


def write_profile_conf(profile: DiseaseProfile, setup: StateSetup, *,
                       model: Path, exp: Path, out_dir: Path, conf_path,
                       bng_command: str, **kw) -> Path:
    """`write_conf` with this profile's priors and log-scale set.

    `write_conf` picks loguniform from its own module constant, which does not
    know about omega. Rather than edit that constant -- and with it the sealed
    influenza path -- the emitted conf is post-corrected for exactly the
    variables where the profile and the module disagree. The correction is a
    line rewrite, asserted to have found its target, so a silent miss is
    impossible.
    """
    from .sihrs_fit import LOG_SCALE_VARS
    p = write_conf(setup, model=model, exp=exp, out_dir=out_dir,
                   conf_path=conf_path, bng_command=bng_command,
                   priors=profile.fitted_priors, **kw)
    extra = [v for v in profile.log_scale_vars
             if v not in LOG_SCALE_VARS and v in profile.fitted_priors
             and profile.fitted_priors[v][0] > 0]
    if not extra:
        return p
    txt = p.read_text()
    for name in extra:
        pat = re.compile(_VAR_RE.format(name=re.escape(name)), re.M)
        new, n = pat.subn(f"loguniform_var = {name} ", txt)
        if n != 1:
            raise RuntimeError(
                f"conf post-correction found {n} lines for {name}, expected 1; "
                f"profile {profile.key} and write_conf disagree about the "
                "fitted set")
        txt = new
    # newline pinned, for the reason app/core/engines/pf.py pins its model
    # rewrite: this is the LAST hand on the conf, so a bare write_text here
    # takes newline=None and quietly undoes the newline="\n" that write_conf
    # applied one call above. On Windows that puts \r on the end of every
    # line of a file PyBNF parses line-wise. Same defect as the one the
    # Windows CI job (run 33200477476) caught in the model file; this copy
    # of it sits on the COVID profile path, which no byte-level test covers.
    p.write_text(txt, newline="\n")
    return p
