"""RESEARCH (COVID profile seam, not on the shipped path): profile-driven fit
wiring that composes sihrs_fit without touching the influenza path.

`resolve_state` runs unchanged (NaN policy, true week offsets, rho*mult
pinning are the shipped ones) and the profile's fixed biology is swapped in
with dataclasses.replace. `write_conf` runs unchanged with the profile's
priors, then one line is rewritten to log-scale omega__FREE, so the conf
format has a single source of truth.

GOTCHA: initial_infected_fraction divides by rho_mult * gamma * N and the
swap changes rho and gamma, so i0 is recomputed AFTER the swap
(resolve_covid_state).
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

    For INFLUENZA this is a no-op (tests/test_profiles.py asserts it).
    """
    import numpy as np
    f = profile.fixed
    ar = float(attack_rate if attack_rate is not None
               else np.mean(f.attack_rate_range))
    s = resolve_state(state, truth_csv=truth_csv, locations_csv=locations_csv,
                      season_start=season_start, as_of=as_of,
                      s0=float(s0 if s0 is not None else f.s0_default),
                      attack_rate=ar)
    # rho*mult depends only on the attack rate; recomputed beside i0, which
    # does change because gamma differs between profiles.
    rhomult = pin_rho_mult(float(s.observed.sum()) / s.population, ar)
    i0 = initial_infected_fraction(max(float(s.observed[0]), 1.0), s.population,
                                   rhomult, f.gamma_per_week)
    return dataclasses.replace(
        s, gamma=f.gamma_per_week, rho=f.rho, rhomult=rhomult,
        gammaH=f.gammaH_per_week,
        # inert when omega is fitted (no {{OMEGA}} token); the literature
        # centre keeps printed setups meaningful
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

    An unresolved token (e.g. a profile fixing omega against a template
    that frees it) raises in materialize_model.
    """
    sfx = suffix or f"{setup.state.replace(' ', '_')}_{profile.key}"
    return materialize_model(setup, profile.template, out_path, sfx,
                             t_end=t_end, extra_tokens=extra_tokens)


_VAR_RE = "^(uniform_var|loguniform_var) = {name} "


def write_profile_conf(profile: DiseaseProfile, setup: StateSetup, *,
                       model: Path, exp: Path, out_dir: Path, conf_path,
                       bng_command: str, **kw) -> Path:
    """`write_conf` with this profile's priors and log-scale set.

    write_conf's LOG_SCALE_VARS does not know omega; rather than touch the
    influenza path, the emitted conf is post-corrected line by line, each
    rewrite asserted to hit exactly one line.
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
    # newline pinned: the last write of the conf; keep LF on Windows
    p.write_text(txt, newline="\n")
    return p
