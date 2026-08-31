"""Materialize and fit the population-parameterized SIHRS via PyBNF on BNGsim.

Everything a SIHRS fit needs, per state:
  * the per-state model copy (all {{TOKENS}} resolved from data + sourced priors),
  * the .exp fitting target,
  * a PyBNF .conf with exactly the 6 fitted parameters,
  * the pybnf invocation, pointed at the FORK so BNGsim's compiled path is used.

Only 7 parameters are fitted (Reff, eps1, phi1, eps2, phi2, mult, r). Everything else is
fixed from data or literature -- see `flubnf/sihrs_priors.py` for each value's DOI
or derivation. That is down from 11 in the normalized model, and it removes both
the rho-vs-mult ridge and the R0-vs-s0 ridge.

BNGsim note: the working fast path is the fork's `BngsimModel`, used automatically
for ordinary .bngl -> .net fits when the fork is the installed pybnf. Do NOT set
`sbml_backend = bngsim` -- that selects the SBML bridge, whose output is
species-only and therefore hides `H_weekly` (a function) entirely.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from .sihrs_priors import (S0_DEFAULT, ATTACK_RATE_RANGE, gamma_per_week,
                           initial_infected_fraction, load_populations,
                           pin_rho_mult)

_TOKEN_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")

# Fixed values that are not per-state. UNSOURCED WORKING ASSUMPTIONS: unlike
# gamma, N, s0 and i0, none of the three below carries a DOI or a data
# derivation. sihrs_priors.py mentions rho only inside the product rho*mult and
# does not define gammaH or omega at all; its provenance_table() carries a row
# for each of these three recording exactly that gap, so a methods reviewer
# following the pointer finds a stated assumption rather than nothing.
# What limits the damage in each case is stated beside the value.
RHO_IHR = 0.02              # biological IHR, branching only. Admissions identify
                            # only rho*mult and mult is fitted, so this value
                            # moves the fitted mult, not the fit.
GAMMAH_PER_WEEK = 1.17      # ~6 d length of stay; does not enter the fit target
                            # at all (H census only), so it cannot bias it.
OMEGA_PER_WEEK = 0.019      # ~1 y immune duration; weakly identified in-season
                            # from under three seasons either way.

# Priors for the 6 fitted parameters. Universal across states by construction --
# every scale-carrying quantity is fixed per state instead.
FITTED_PRIORS: dict = {
    # Reff is the BASE reproduction number: beta(t)=beta0*exp(eps1*cos+eps2*cos)
    # multiplies it seasonally, so R at the seasonal peak is Reff*exp(eps1+eps2).
    # A subcritical BASE is therefore legitimate -- a 1.02 floor artificially
    # propped Reff up (frac@lo hit 0.22). Upper from Boelle 2011.
    # Widened from 2.20: it pinned HIGH in 37/250 fits, largely as a side-effect
    # of the mult ceiling (see below). R0 = Reff/s0 is reported post hoc and may
    # exceed Boelle 2011's pandemic-H1N1 range; disclose rather than truncate.
    "Reff__FREE": (0.60, 2.50),
    # Amplitude bounds are STIFFNESS-CRITICAL, not just statistical: beta enters
    # as beta0*exp(eps1*cos+eps2*cos), so the prior corner sets beta_max and
    # exp() makes it explode. At (Reff 3.0, eps1 1.5, eps2 0.8) beta_max was
    # ~77/wk -- a doubling time of hours -- and CVODE failed on 100% of the
    # 230-week multi-season fits (and 2.7% of 48-week ones). exp(2*eps1) is the
    # trough-to-peak swing; flu is ~2-4x, so eps1<=1.0 (7.4x) is still generous.
    "eps1__FREE": (0.0, 1.0),
    "phi1__FREE": (0.0, 52.0),    # phase, weeks
    "eps2__FREE": (0.0, 0.4),     # semi-annual amplitude; also stiffness-bounded
    "phi2__FREE": (0.0, 26.0),
    # Ascertainment. The old 0.10 ceiling was derived from NOMINAL dynamics
    # (eps1=0.35, R0=1.3). In the regime the fits actually occupy (eps1 -> 0, so
    # beta is constant) the epidemic is 10x smaller, so the required ascertainment
    # is 10-100x larger -- it pinned in 80/250 fits. Worse, mult and Reff are
    # INVERSELY COUPLED (low Reff -> small epidemic -> needs high mult), so a low
    # mult ceiling forced Reff into its own ceiling: both pinned together.
    # Ceiling is now the PHYSICAL bound: ascertainment cannot exceed 100%.
    # If it still pins at 1.0, the fixed rho (IHR) is too small, not the prior.
    "mult__FREE": (0.002, 1.0),
    # External force of infection. Verified with the mirror over 230 weeks:
    # impr=0 -> min I = 2.9e-8 people (denormal, CVODE fails, only 3 peaks);
    # 1e-9..1e-6 -> min I 2.6e-3..2.6 people and 4 ANNUAL peaks with spacing
    # converging to 52 weeks. Fitted because no literature value exists, and it
    # separates from i0 multi-season (i0 affects season 1 only).
    "impr__FREE": (1e-9, 3e-5),
    # Floor lowered from 1.0: pinned LOW in 31/250 fits, i.e. the data wants more
    # observation overdispersion than the prior allowed.
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
    # Week offsets from season_start for each row of `observed`. Contiguous
    # 0..n-1 when reporting is complete; NON-contiguous when weeks are missing
    # (e.g. the May-Oct 2024 NHSN voluntary-reporting pause: MA/MN/WV carry
    # NaN weeks in 55 of 87 vintages). Calendar anchoring of phi1 REQUIRES
    # true offsets -- renumbering weeks would silently shift every state's
    # fitted phase.
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

    Uses only weeks at or before `as_of`, so there is no leakage.
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

    # NaN policy (multi-season correctness): missing weeks are MISSING, never
    # zero -- filling would teach the model a fake summer trough. Rows are
    # dropped; `times` keeps each survivor's TRUE week offset so the seasonal
    # phase stays calendar-anchored and both engines skip the gap natively
    # (PyBNF matches exp rows by time value; the filter integrates
    # t_last -> t_k whatever the spacing).
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

    `t_end` rewrites the simulate action's window and step count. NO FLU CALL
    SITE PASSES IT, so flu models are materialized with the template's own 48
    weeks. That is inert for the particle filter, which never reads the
    actions block and drives its own one-week windows, and it is a ceiling on
    the adaptive-MCMC path, where a full season's last as-of sits at week
    offset 45 and four forecast horizons past it reach week 49."""
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
        # Multi-season fits span several 52-week cycles, which is the only regime
        # where the seasonal amplitude/phase are identifiable at all.
        txt = re.sub(r"t_end=>\d+", f"t_end=>{int(t_end)}", txt)
        txt = re.sub(r"n_steps=>\d+", f"n_steps=>{int(t_end)}", txt)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # newline and encoding pinned: the engine consumes these bytes, and
    # Windows text mode would otherwise translate \n to \r\n
    out.write_text(txt, encoding="utf-8", newline="\n")
    return out


def write_exp(setup: StateSetup, out_path: str | Path) -> Path:
    """PyBNF .exp target: weekly reported admissions at integer weeks 0..n-1."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# time H_weekly"]
    tt = setup.times if setup.times.size else np.arange(setup.n_obs)
    lines += [f"{int(i)} {v:.6f}" for i, v in zip(tt, setup.observed)]
    # newline pinned, like materialize_model above: PyBNF reads the .exp
    # line-wise and a Windows text-mode write would put \r on the end of
    # every row's last column.
    out.write_text("\n".join(lines) + "\n", newline="\n")
    return out


# Strictly positive SCALE parameters. These get `loguniform_var`, which is both
# better-mixed and much faster -- see write_conf's LOG_SCALE note. `eps1`/`eps2`
# are excluded because their lower bound is exactly 0, where log is undefined.
LOG_SCALE_VARS: tuple[str, ...] = ("Reff__FREE", "mult__FREE", "impr__FREE",
                                   "r__FREE")

# Priors for templates/SIHRS_pop_min.bngl -- 5 fitted parameters.
# eps2/phi2/impr are removed because they are not identified (impr pins in 75%
# of fits) or do not earn their keep (the semi-annual harmonic does not produce
# a second epidemic peak). Each removed dimension removes posterior spread,
# which is the measured defect: swapping SIHRS's SPREAD for a calibrated one
# gains 0.070 relWIS while swapping its MEDIAN gains 0.003.
MIN_PRIORS: dict = {k: FITTED_PRIORS[k] for k in
                    ("Reff__FREE", "eps1__FREE", "phi1__FREE",
                     "mult__FREE", "r__FREE")}


# Priors for templates/SIHRS_pop_cart.bngl, which writes the SAME harmonic in
# Cartesian coordinates. Identical parameter COUNT; a1/b1 replace eps1/phi1 and
# a2/b2 replace eps2/phi2.
#
# Boxes are set so the reachable amplitude matches the polar ceilings on the
# axes: hypot(a1,b1) <= 1.0 along a1 or b1 alone, up to sqrt(2) in the corners.
# That mild widening is deliberate -- clipping the corners to a disc would
# reintroduce exactly the kind of boundary this change exists to remove -- but
# it is worth remembering that the amplitude bounds are STIFFNESS-critical
# (beta0*exp(...) makes beta_max explode; see FITTED_PRIORS), so sqrt(2)*1.0 is
# the number to check if CVODE failures reappear.
#
# a/b are NOT log-scaled: they are signed, and log requires lo > 0.
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
    """PyBNF conf for the SIHRS AMCMC fit.

    Deliberately omits `sbml_backend`: the ordinary .bngl -> .net path already
    uses the fork's BngsimModel, whereas `sbml_backend = bngsim` selects the
    SBML bridge whose species-only output cannot see `H_weekly`.

    SAMPLER DEFAULTS (measured 2026-08-02, 6 states x 8000 iters)
    ------------------------------------------------------------
    The previous defaults (population_size=1, all `uniform_var`) produced chains
    that were not converged in any useful sense: median ESS 9 of 11,250 samples
    (0.1% efficiency) and median split R-hat 1.192. Nine effective draws cannot
    support a 2.5th or 97.5th percentile, so predictive intervals built from them
    were meaningless. A controlled 2x2 gave:

        arm                       ESS   wall
        uniform,    pop=1  (old)    6   36 min
        loguniform, pop=1           9    7 min
        uniform,    pop=4          43  136 min
        loguniform, pop=4  (new)   44   14 min      <- default

    `population_size` IS the chain count (PyBNF `num_parallel = population_size`,
    algorithms.py:2114), so pop=1 also meant no multi-chain R-hat was ever
    computable. `parallel_count` defaults to `population_size` so the chains run
    concurrently rather than serially -- that is what makes pop=4 cost 14 min
    instead of 136.

    `loguniform_var` matters more for SPEED than for ESS: `impr`'s prior spans
    1e-9..3e-5, four decades, and proposing linearly there generates extreme
    values that make the ODE stiff. Log-scaling cut wall time 5-10x.

    HONEST CAVEAT: these defaults improve mixing ~19x per minute but do NOT fix
    it. Multi-chain R-hat is still 3.25 (bar 1.01) and ESS ~44 (bar ~400): four
    chains from different starts never meet. The posterior has a condition number
    of ~1678 (a long thin ridge; worst pair eps1<->eps2 at corr +0.785), which no
    isotropic-proposal sampler traverses. The real fix is reparameterisation --
    see docs/RETROSPECTIVE_2026-07.md. Treat interval/coverage quantities derived
    from these posteriors as provisional; medians are far more robust.
    """
    if parallel_count is None:
        parallel_count = population_size
    lines = [
        f"bng_command = {bng_command}",
        f"model = {model} : {exp}",
        f"output_dir = {out_dir}",
        "fit_type = am",
        # KNOWN OBSERVATION-MODEL MISMATCH ON THIS PATH, DELIBERATELY NOT
        # FIXED HERE. PyBNF's neg_bin_dynamic differences a simulated column
        # only when the EXPERIMENTAL column's name contains '_Cum'. The .exp
        # written by write_exp() names its one count column H_weekly, so the
        # objective takes the other branch and compares the model's
        # H_weekly(t_k), an INSTANTANEOUS ascertained rate in people per
        # week, against a weekly TOTAL. The size of that bias is exact: at
        # local weekly log-growth lam the ratio of the instant to the
        # integral is lam/(1 - exp(-lam)), so +10 percent at lam = 0.2,
        # +21 at 0.4, +45 at 0.8. On the 2024-25 state admissions (53
        # jurisdictions, consecutive weeks with both endpoints at or above
        # 20) the median jurisdiction's fastest week is lam = 0.81, a gap
        # of +46 percent, and the fastest week anywhere is lam = 1.27, a
        # gap of +77 percent; the median jurisdiction's steepest decline is
        # lam = -0.62, a gap of -28 percent. One season-constant
        # `mult` cannot absorb a factor that moves with phase. The shipped
        # particle filter does NOT have this problem: it integrates the
        # cumulative observable across each reporting week instead. The fix
        # is to rename the .exp count column to H_Cum so the differencing
        # fires, or to give this path an explicit integrated observation
        # model; the first also changes the column the particle filter reads,
        # and either moves numbers, so neither is applied. Until one is,
        # adaptive-MCMC fits carry this bias and must not be published.
        "objfunc = neg_bin_dynamic",
        "",
    ]
    # `priors` selects the parameterization: FITTED_PRIORS for the polar
    # template, CART_PRIORS for SIHRS_pop_cart.bngl. They must match the
    # template -- a mismatch declares a fitted var the model never defines.
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
    # Exponential recency weighting. NOT SHIPPED and not used: it needs a
    # 144-line patch to PyBNF that lives in the lab archive rather than in this
    # repository, no shipped config sets it, and the default of 0.0 means the
    # key is never emitted, so stock PyBNF runs unaffected. Kept because the
    # research it came from is real, but do not read the line below as a
    # dependency this repository satisfies. Aimed
    # at the post-peak shoulder, the only phase where SIHRS loses to baseline
    # (relWIS 1.205, forecasts 1.5-3.3x low) because a single-wave fit anchored
    # by months of pre-peak data extrapolates continued decline.
    if recency_tau and recency_tau > 0:
        lines.append(f"recency_tau = {float(recency_tau)}")
    p = Path(conf_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # newline pinned: same line-based PyBNF reader as the .exp above.
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


def refine_i0(setup: StateSetup, fitted_mult: float) -> StateSetup:
    """Re-derive `i0` from the FITTED ascertainment, for a self-consistent seed.

    `i0` is first derived with a pre-fit estimate of rho*mult, so once `mult` is
    fitted the seed is inconsistent by that ratio (2.1x on Alabama). It only sets
    the initial infected count and `phi1` absorbs the resulting timing shift, but
    a 2x seed error is a ~5-week shift at seasonal growth rates, so it is worth
    one cheap extra pass: fit briefly, read median `mult`, re-derive, refit.
    """
    import dataclasses
    rhomult = float(setup.rho) * float(fitted_mult)
    i0 = initial_infected_fraction(max(float(setup.observed[0]), 1.0),
                                   setup.population, rhomult, setup.gamma)
    return dataclasses.replace(setup, rhomult=rhomult, i0=i0)


def median_fitted(results_dir: Path, param: str = "mult__FREE",
                  burn: int = 0) -> Optional[float]:
    """Median of one fitted parameter from the AMCMC chain, or None."""
    p = Path(results_dir) / "Results" / "A_MCMC" / "Runs" / "params_0.txt"
    if not p.is_file():
        return None
    df = pd.read_csv(p, sep=r"\s+")
    col = param if param in df.columns else param.replace("__FREE", "")
    if col not in df.columns:
        return None
    v = pd.to_numeric(df[col], errors="coerce").dropna()
    if v.empty:
        return None
    return float(v.iloc[len(v) // 3:].median() if burn == 0 else v.iloc[burn:].median())


def bngsim_fast_path_active(pybnf_binary: str) -> dict:
    """Positive check that the installed pybnf is the FORK with bngsim available.

    The docs warn the slow interpreted fallback is SILENT, so verify rather than
    assume: import bngsim and the fork-only BngsimModel in the same interpreter
    that will run the fit.
    """
    py = str(Path(pybnf_binary).with_name("python"))
    probe = ("import bngsim, pybnf.bngsim_model as m; "
             "print('OK', bngsim.__name__, hasattr(m,'BngsimModel'))")
    r = subprocess.run([py, "-c", probe], capture_output=True, text=True)
    out = (r.stdout or "").strip()
    return {"active": r.returncode == 0 and out.startswith("OK") and "True" in out,
            "detail": out or (r.stderr or "").strip()[-300:]}
