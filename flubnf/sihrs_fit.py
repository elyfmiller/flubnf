"""SHIPPED (per-state SIHRS model inputs) + LEGACY (the AMCMC fit).

SHIPPED (used by app/core/engines/pf.py): StateSetup, resolve_state,
materialize_model (all {{TOKENS}} resolved from data + sourced priors),
write_exp, and the fixed constants. The shipped PF template fits the 5
parameters of MIN_PRIORS; everything else is fixed from data or literature
(flubnf/sihrs_priors.py has each value's DOI or derivation).

LEGACY (AMCMC): FITTED_PRIORS (the 8-parameter multi-season box),
CART_PRIORS, write_conf, run_pybnf. Do NOT set `sbml_backend = bngsim`: it
selects the SBML bridge, which is species-only and hides `H_weekly`.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .sihrs_priors import (S0_DEFAULT, ATTACK_RATE_RANGE, gamma_per_week,
                           initial_infected_fraction, pin_rho_mult)

_TOKEN_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")

# Fixed, not per-state. UNSOURCED WORKING ASSUMPTIONS (no DOI or data
# derivation; sihrs_priors.provenance_table() records the gap). What limits
# the damage is stated beside each value.
RHO_IHR = 0.02              # IHR; only rho*mult is identified and mult is fitted
GAMMAH_PER_WEEK = 1.17      # ~6 d length of stay; H census only, not the fit target
OMEGA_PER_WEEK = 0.019      # ~1 y immunity; weakly identified in-season anyway

# The 8-parameter multi-season box (LEGACY AMCMC; MIN_PRIORS, its 5-parameter
# subset, is what the shipped PF fits). Universal across states: every
# scale-carrying quantity is fixed per state instead.
FITTED_PRIORS: dict = {
    # BASE R; seasonal peak R = Reff*exp(eps1+eps2), so a floor < 1 is fine.
    # R0 = Reff/s0 may exceed Boelle 2011's range: disclose, do not truncate.
    "Reff__FREE": (0.60, 2.50),
    # STIFFNESS-CRITICAL: exp(eps) sets beta_max; wider boxes made CVODE fail
    # on multi-season fits. eps1 <= 1.0 is a 7.4x swing (flu is ~2-4x).
    "eps1__FREE": (0.0, 1.0),
    "phi1__FREE": (0.0, 52.0),    # phase, weeks
    "eps2__FREE": (0.0, 0.4),     # semi-annual amplitude; also stiffness-bounded
    "phi2__FREE": (0.0, 26.0),
    # Ascertainment: ceiling is the physical 100% (mult and Reff are inversely
    # coupled, so a low ceiling pinned both). Pinning at 1.0 means the fixed
    # rho is too small, not the prior.
    "mult__FREE": (0.002, 1.0),
    # External FOI: impr = 0 lets I underflow (CVODE fails) multi-season.
    "impr__FREE": (1e-9, 3e-5),
    # low floor: the data wants more overdispersion than 1.0 allowed
    "r__FREE": (0.1, 40.0),
}


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

    @property
    def last_week_offset(self) -> int:
        """Sim-column index of the last observation. Equals n_obs-1 only when
        no weeks are missing; traj extraction MUST use this, not n_obs-1."""
        return int(self.times[-1]) if self.times.size else self.n_obs - 1


def resolve_state(state: str, *, truth_csv: str | Path, locations_csv: str | Path,
                  season_start: str, as_of: str, s0: float = S0_DEFAULT,
                  attack_rate: Optional[float] = None) -> StateSetup:
    """Resolve every fixed SIHRS input for one state from data + sourced priors.

    Observations are as-of filtered. The POPULATION is not: callers pass the
    CURRENT locations.csv, so a revision upstream changes bit-level replay
    output (N only sets the demographic-noise scale; a reproducibility
    hazard, not a measured score distortion).
    """
    ar = float(attack_rate if attack_rate is not None
               else np.mean(ATTACK_RATE_RANGE))
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

    rhomult = pin_rho_mult(float(obs.sum()) / pop, ar)
    g = gamma_per_week()
    i0 = initial_infected_fraction(max(float(obs[0]), 1.0), pop, rhomult, g)
    return StateSetup(state=state, fips=fips, population=pop, gamma=g,
                      rho=RHO_IHR, rhomult=rhomult, gammaH=GAMMAH_PER_WEEK,
                      omega=OMEGA_PER_WEEK, s0=float(s0), i0=i0,
                      attack_rate=ar, n_obs=int(obs.size), observed=obs,
                      times=week_off)


def materialize_model(setup: StateSetup, template: str | Path, out_path: str | Path,
                      suffix: str, t_end: int | None = None,
                      extra_tokens: dict | None = None) -> Path:
    """Write the per-state .bngl with every token resolved. Unresolved => error.
    `extra_tokens` lets variant templates carry tokens StateSetup doesn't know
    (e.g. the two-strain {{A0SHARE}}).

    `t_end` rewrites the simulate window; no flu caller passes it (the PF
    ignores the actions block; for AMCMC the template's 48 weeks cap it)."""
    txt = Path(template).read_text()
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
    if t_end is not None:
        txt = re.sub(r"t_end=>\d+", f"t_end=>{int(t_end)}", txt)
        txt = re.sub(r"n_steps=>\d+", f"n_steps=>{int(t_end)}", txt)
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
    out.write_text("\n".join(lines) + "\n", newline="\n")
    return out


# Strictly positive SCALE parameters get `loguniform_var` (better mixing,
# faster); eps1/eps2 have lower bound 0, so they cannot.
LOG_SCALE_VARS: tuple[str, ...] = ("Reff__FREE", "mult__FREE", "impr__FREE",
                                   "r__FREE")

# SHIPPED: templates/SIHRS_pop_min.bngl's 5 fitted parameters. eps2/phi2/impr
# are unidentified or earn nothing, and each dropped dimension removes
# spread, SIHRS's measured defect.
MIN_PRIORS: dict = {k: FITTED_PRIORS[k] for k in
                    ("Reff__FREE", "eps1__FREE", "phi1__FREE",
                     "mult__FREE", "r__FREE")}


# templates/SIHRS_pop_cart.bngl: the same harmonic in Cartesian coordinates
# (a1/b1 for eps1/phi1, a2/b2 for eps2/phi2). The square box reaches sqrt(2)
# x the polar ceiling in the corners on purpose (a disc would add a boundary);
# check that first if CVODE failures reappear. Signed, so not log-scaled.
CART_PRIORS: dict = {
    "Reff__FREE": FITTED_PRIORS["Reff__FREE"],
    "a1__FREE": (-1.0, 1.0),
    "b1__FREE": (-1.0, 1.0),
    "a2__FREE": (-0.4, 0.4),
    "b2__FREE": (-0.4, 0.4),
    "mult__FREE": FITTED_PRIORS["mult__FREE"],
    "impr__FREE": FITTED_PRIORS["impr__FREE"],
    "r__FREE": FITTED_PRIORS["r__FREE"],
}


def write_conf(setup: StateSetup, *, model: Path, exp: Path, out_dir: Path,
               conf_path: str | Path, bng_command: str,
               max_iterations: int = 8000, burn_in: int = 2000,
               adaptive: int = 2000, sample_every: int = 1,
               backup_every: int = 100, population_size: int = 4,
               parallel_count: Optional[int] = None,
               log_scale: bool = True,
               drop_vars: tuple[str, ...] = (),
               recency_tau: float = 0.0,
               priors: Optional[dict] = None) -> Path:
    """PyBNF conf for the LEGACY SIHRS adaptive-MCMC fit.

    Omits `sbml_backend` (see module docstring). `population_size` is the
    chain count (PyBNF num_parallel), and `parallel_count` defaults to it so
    chains run concurrently; log-scale priors cut wall time 5-10x (impr spans
    four decades). These defaults improve mixing but do not fix it: R-hat
    stays ~3.25 on a ridge (condition number ~1678) that no isotropic
    sampler traverses. Intervals from this path are provisional; medians are
    far more robust.
    """
    if parallel_count is None:
        parallel_count = population_size
    lines = [
        f"bng_command = {bng_command}",
        f"model = {model} : {exp}",
        f"output_dir = {out_dir}",
        "fit_type = am",
        # KNOWN BIAS, not fixed: neg_bin_dynamic differences only '_Cum'
        # columns, so this compares instantaneous H_weekly(t) to a weekly
        # TOTAL: ratio lam/(1 - exp(-lam)), +46% at a median peak week. The
        # shipped PF integrates Hobs instead. Renaming the column to H_Cum
        # would also change what the PF reads. Do not publish AMCMC fits.
        "objfunc = neg_bin_dynamic",
        "",
    ]
    # `priors` must match the template (FITTED/MIN for polar, CART for cart)
    for name, (lo, hi) in (priors if priors is not None else FITTED_PRIORS).items():
        if name in drop_vars:
            continue        # fixed in the model instead of sampled (see profile_mult)
        kw = ("loguniform_var" if (log_scale and name in LOG_SCALE_VARS and lo > 0)
              else "uniform_var")
        lines.append(f"{kw} = {name} {lo} {hi}")
    lines += [
        "",
        f"population_size = {population_size}",
        f"parallel_count = {parallel_count}",
        f"max_iterations = {max_iterations}",
        f"burn_in = {burn_in}",
        f"adaptive = {adaptive}",
        f"sample_every = {sample_every}",
        f"backup_every = {backup_every}",
        "output_noise_trajectory = H_weekly",
        "continue_run = 0",
        "verbosity = 0",
    ]
    # RESEARCH recency weighting: needs a PyBNF patch that lives only in the
    # lab archive; never emitted at the default 0.0.
    if recency_tau and recency_tau > 0:
        lines.append(f"recency_tau = {float(recency_tau)}")
    p = Path(conf_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # newline pinned: line-based PyBNF reader
    p.write_text("\n".join(lines) + "\n", newline="\n")
    return p


def run_pybnf(conf: Path, *, pybnf_binary: str, cwd: Path,
              log_level: str = "warning", timeout_sec: float = 3600.0) -> dict:
    """Launch pybnf on `conf` from a private cwd. Returns a small status dict."""
    cwd.mkdir(parents=True, exist_ok=True)
    cmd = [pybnf_binary, "-c", str(conf), "-o", "-L", log_level]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout_sec, cwd=str(cwd))
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": f"timeout after {timeout_sec:.0f}s",
                "elapsed": time.time() - t0}
    return {"ok": proc.returncode == 0, "returncode": proc.returncode,
            "elapsed": time.time() - t0,
            "stderr_tail": proc.stderr[-1500:], "stdout_tail": proc.stdout[-800:]}

