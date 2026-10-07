"""SHIPPED: per-state SIHRS model inputs (app/core/engines/pf.py, and the
Sandbox's Oracle SIHRS start in app/core/sandbox.py).

StateSetup, resolve_state, materialize_model (all {{TOKENS}} resolved from
data + sourced priors), write_exp, and the fixed constants. The shipped PF
fits the 5 parameters of app/core/engines/pf.py VARS_1S; everything else is
fixed from data or literature (flubnf/sihrs_priors.py has each value's DOI
or derivation). A PyBNF conf for these models must not set
`sbml_backend = bngsim`: it selects the SBML bridge, which is species-only
and hides `H_weekly`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .sihrs_priors import (S0_DEFAULT, ATTACK_RATE_RANGE, gamma_per_week,
                           initial_infected_fraction, pin_rho_mult,
                           SEED_DENOMINATOR, SEED_DENOMINATORS,
                           expected_total_per_capita)

_TOKEN_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")

# Fixed, not per-state. UNSOURCED WORKING ASSUMPTIONS (no DOI or data
# derivation; sihrs_priors.provenance_table() records the gap). What limits
# the damage is stated beside each value.
RHO_IHR = 0.02              # IHR; only rho*mult is identified and mult is fitted
GAMMAH_PER_WEEK = 1.17      # ~6 d length of stay; H census only, not the fit target
OMEGA_PER_WEEK = 0.019      # ~1 y immunity; weakly identified in-season anyway


@dataclass
class StateSetup:
    """Everything resolved for one state, with the numbers that produced it."""
    state: str
    fips: str
    population: int
    gamma: float
    rho: float
    rhomult: float
    gammaH: float
    omega: float
    s0: float
    i0: float
    attack_rate: float
    n_obs: int
    observed: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    # TRUE week offsets from season_start per `observed` row (non-contiguous
    # across reporting gaps); renumbering would shift the fitted phase phi1.
    times: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    # the pin's record (research knob pf.seed_denominator); the defaults are
    # the shipped path, so every fake StateSetup in app/tests keeps working
    seed_denominator: str = SEED_DENOMINATOR
    expected_total_pc: Optional[float] = None    # None under to_date / no season
    seed_factor: float = 1.0                      # pinned per-capita / to-date
    seed_record: dict = field(default_factory=dict, repr=False)

    @property
    def last_week_offset(self) -> int:
        """Sim-column index of the last observation. Equals n_obs-1 only when
        no weeks are missing; traj extraction MUST use this, not n_obs-1."""
        return int(self.times[-1]) if self.times.size else self.n_obs - 1


def pin_from(obs, population: int, attack_rate: float, expected_pc,
             gamma: float) -> tuple:
    """(rhomult, i0, factor) from a series: the to-date rule, or, with
    expected_pc, the season-total rule floored at to-date. The ONE place
    the pin is computed (resolve_state, the trim re-derivation and the
    reporting model in pf.prepare all call it)."""
    obs = np.asarray(obs, dtype=float)
    cum_pc = float(obs.sum()) / float(population)
    pin_pc = max(cum_pc, float(expected_pc)) if expected_pc else cum_pc
    rhomult = pin_rho_mult(pin_pc, attack_rate)
    i0 = initial_infected_fraction(max(float(obs[0]), 1.0), population,
                                   rhomult, gamma)
    return rhomult, i0, (pin_pc / cum_pc if cum_pc > 0 else float("nan"))


def resolve_state(state: str, *, truth_csv: str | Path, locations_csv: str | Path,
                  season_start: str, as_of: str,
                  seed_denominator: str = SEED_DENOMINATOR) -> StateSetup:
    """Resolve every fixed SIHRS input for one state from data + sourced priors.

    Observations are as-of filtered. The POPULATION is not: callers pass the
    CURRENT locations.csv, so a revision upstream changes bit-level replay
    output (N only sets the demographic-noise scale; a reproducibility
    hazard, not a measured score distortion).

    seed_denominator (sihrs_priors.SEED_DENOMINATORS): what pins rho*mult
    and i0; the default is the shipped to-date rule.
    """
    if seed_denominator not in SEED_DENOMINATORS:
        raise ValueError(f"seed_denominator must be one of {SEED_DENOMINATORS}, "
                         f"not {seed_denominator!r}")
    ar = float(np.mean(ATTACK_RATE_RANGE))
    locs = pd.read_csv(locations_csv, dtype={"location": str})
    locs["location"] = locs["location"].str.zfill(2)
    row = locs[locs.location_name == state]
    if row.empty:
        raise KeyError(f"{state!r} not in {locations_csv}")
    fips = str(row.iloc[0]["location"]).zfill(2)
    pop = int(row.iloc[0]["population"])

    t = pd.read_csv(truth_csv, dtype={"location": str})
    t["location"] = t["location"].str.zfill(2)
    t["date"] = pd.to_datetime(t["date"])
    m = ((t.location == fips) & (t.date >= pd.Timestamp(season_start))
         & (t.date <= pd.Timestamp(as_of)))
    sel = t.loc[m].sort_values("date")
    obs = sel["value"].to_numpy(dtype=float)
    if obs.size == 0:
        raise ValueError(f"no observations for {state} in {season_start}..{as_of}")

    # Missing weeks are dropped, never zero-filled (a fake trough); `times`
    # keeps true offsets and both engines skip gaps natively.
    week_off = ((sel["date"] - pd.Timestamp(season_start)).dt.days // 7
                ).to_numpy(dtype=int)
    finite = np.isfinite(obs)
    if not finite.any():
        raise ValueError(f"{state}: all {obs.size} weeks are NaN in "
                         f"{season_start}..{as_of} (reporting pause?)")
    n_drop = int((~finite).sum())
    if n_drop:
        import logging
        logging.getLogger(__name__).warning(
            "%s: dropping %d NaN week(s) at offsets %s (reporting gap)",
            state, n_drop, week_off[~finite].tolist())
    obs, week_off = obs[finite], week_off[finite]
    if not obs.sum() > 0:
        # early in a season a small state can have reported none yet;
        # rho*mult and i0 are ratios of this count (pin_rho_mult)
        raise ValueError(f"{state}: no admissions reported in "
                         f"{season_start}..{as_of} ({obs.size} week(s), all "
                         "zero), so the starting state cannot be derived "
                         "from the data yet")

    g = gamma_per_week()
    expected, rec = None, {}
    if seed_denominator == "season_total":
        expected, rec = expected_total_per_capita(t, fips, pop, season_start, as_of)
        if expected is None:
            rec["fallback"] = "no completed season in the vintage: to-date rule"
    rhomult, i0, factor = pin_from(obs, pop, ar, expected, g)
    return StateSetup(state=state, fips=fips, population=pop, gamma=g,
                      rho=RHO_IHR, rhomult=rhomult, gammaH=GAMMAH_PER_WEEK,
                      omega=OMEGA_PER_WEEK, s0=float(S0_DEFAULT), i0=i0,
                      attack_rate=ar, n_obs=int(obs.size), observed=obs,
                      times=week_off, seed_denominator=seed_denominator,
                      expected_total_pc=expected, seed_factor=factor,
                      seed_record=rec)


def materialize_model(setup: StateSetup, template: str | Path, out_path: str | Path,
                      suffix: str, extra_tokens: dict | None = None) -> Path:
    """Write the per-state .bngl with every token resolved. Unresolved => error.
    `extra_tokens` lets variant templates carry tokens StateSetup doesn't know
    (e.g. the two-strain {{A0SHARE}})."""
    txt = Path(template).read_text(encoding="utf-8")
    for tok, val in {**(extra_tokens or {}),
        "{{POP}}": str(int(setup.population)),
        "{{S0FRAC}}": f"{setup.s0:g}",
        "{{I0FRAC}}": f"{setup.i0:.8e}",
        "{{GAMMA}}": f"{setup.gamma:.6f}",
        "{{RHO}}": f"{setup.rho:g}",
        "{{GAMMAH}}": f"{setup.gammaH:g}",
        "{{OMEGA}}": f"{setup.omega:g}",
    }.items():
        txt = txt.replace(tok, val)
    left = _TOKEN_RE.findall(txt)
    if left:
        raise ValueError(f"unresolved tokens {sorted(set(left))} for {setup.state}")
    txt = re.sub(r'suffix=>"[^"]*"', f'suffix=>"{suffix}"', txt)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # newline pinned: Windows text mode would write CRLF to the engine
    out.write_text(txt, encoding="utf-8", newline="\n")
    return out


def write_exp(setup: StateSetup, out_path: str | Path) -> Path:
    """PyBNF .exp target: weekly reported admissions at integer weeks 0..n-1."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# time H_weekly"]
    tt = setup.times if setup.times.size else np.arange(setup.n_obs)
    lines += [f"{int(i)} {v:.6f}" for i, v in zip(tt, setup.observed)]
    # newline pinned: PyBNF reads the .exp line-wise
    out.write_text("\n".join(lines) + "\n", newline="\n", encoding="utf-8")
    return out

