"""GATE A ROUND TWO -- the second harmonic. PRE-REGISTRATION, frozen before any fit.

Frozen 2026-08-22, after round one (pre-registration 5ad51005a827740c) and
before a single round-two fit was launched. Nothing below was edited after
seeing a round-two result; the run log and the results JSON carry this file's
hash so that claim is checkable. Exploratory work done BEFORE freezing, and
therefore legitimately reflected here: the six estimator control points in
section 4.1 were simulated (no data involved), and the round-one output files
were read.

=============================================================================
1. WHAT IS BEING TESTED
=============================================================================
Round one passed width (particle filter 1.105 against the 4.06 bar, coverage
87.9%) and freed omega off its bounds (2.66 to 5.11 months), but the fitted
models produce 1.00 peaks per year, zero of nine bimodal, against 2 to 3
observed waves in the same windows, because eps1 collapses to about 0.03.
The decisive question of this round: does restoring the semi-annual harmonic
(eps2, phi2) recover the multi-wave behavior the data show, without paying in
width, with eps2 identified rather than pinned or prior-shaped?

=============================================================================
2. ARMS. Same 3 states, same 3 origins, same iteration and particle budgets as
round one, refit side by side so every comparison is paired.
=============================================================================
A1  CONTROL. templates/SIHRS_pop_covid.bngl unchanged, the round-one 6
    parameter set (Reff, eps1, phi1, omega, mult, r), round-one priors
    (flubnf/profiles.py COVID). Refit alongside A2, never read from records:
    the AMCMC path carries no seed (checked: the fork's algorithms.py reads no
    seed key; round one ran unseeded), so the only honest control is a
    contemporaneous refit on the same machine at the same settings.
A2  THE ARM. templates/SIHRS_pop_covid_2h.bngl: A1 plus the semi-annual
    harmonic, beta() = beta0*exp(eps1*cos(2pi(t-phi1)/52)
    + eps2*cos(4pi(t-phi2)/52)). Two added fitted dimensions:
      eps2  uniform(0.0, 0.4). The box is carried from the measured flu
            8-parameter prior (sihrs_fit.FITTED_PRIORS) where it is
            STIFFNESS-critical: beta_max = Reff*gamma*exp(eps1+eps2); at this
            arm's corner (2.5 * 1.0234 * exp(1.4)) beta_max = 10.4/wk, an
            order of magnitude below the ~77/wk corner that once broke CVODE.
            Uniform, not loguniform, because the lower bound is exactly 0.
      phi2  uniform(0.0, 26.0), one full period of the semi-annual harmonic;
            the phase is identified only mod 26. No peak-week prior, for the
            same lead-time reason phi1 carries none.
A3  SENSITIVITY. A2 with gamma at the REALIZED-HOUSEHOLD generation time,
    7/3.59 per week (Manica 2022, doi:10.1016/j.lanepe.2022.100446, mean
    realized household GT 3.59 d, 95% CrI 3.55-3.60).
    DEVIATION FROM THE TASKING, STATED PLAINLY: the tasking specifies A3 as
    "A2 with the corrected intrinsic generation time (6.84 days)". A1 and A2
    ALREADY fix gamma at 7/6.84: the correction was adopted before round one
    (round-one pre-registration section 2, flubnf/profiles.py COVID_GT block),
    so that arm would be byte-identical to A2 and carry no information. The
    informative sensitivity is the OTHER defensible reading of the same paper,
    the 3.59 d realized-household figure the feasibility memo originally
    proposed. Between A2 (6.84 d) and A3 (3.59 d) both readings are covered;
    if the gate verdicts agree across them, the GT choice does not drive the
    round's conclusion.

Fit settings, identical to round one per arm and per fit: iters 20000,
population_size 4 (= 4 chains), burn_in = adaptive = iters/4, sample_every 1,
neg_bin_dynamic, timeout 10800 s, 2 pool workers, .venv materializes and
~/.venvs/flubnf runs the engines. Seeds: the particle-filter arms are seeded
(round-one config: seed 20260822 + cell index, identical enumeration;
production config: app.core.runs.derive_seed, the production rule). The AMCMC
arms cannot be seeded without touching the frozen fork, exactly as in round
one; pairing there is on data, settings and machine.

=============================================================================
3. HARNESS FIXES, BOTH PRE-REGISTERED AND APPLIED TO EVERY ARM
=============================================================================
(b) THE CHAIN-0 GLOB. Round one's gate_a.py read
    sorted(glob("*traj_noise*"))[0]: chain 0 of 4. Four adaptive-Metropolis
    chains sit in different modes here, so the round-one AMCMC width was a
    lower bound (recorded in gate_a_report.py). This harness reads EVERY
    chain's trajectory, thinned to ~3000 draws per chain, and reports the
    chain-0-only width beside the pooled one so the size of the round-one
    understatement is measured, not asserted.
(a) THE ANCHOR-RESCALE PATHOLOGY. In round one's particle-filter width arm,
    4 of 9 cells needed an anchor rescale above 3 (max 95.3, North Carolina
    2026-01-07) and the rescaled median hit zero at horizons 3 to 4 there:
    the filtered latent state had died, and the production rescale
    (last_observed / median(origin draws), pf.collect) multiplied a corpse.
    This is the documented forecast-collapse defect wearing a new engine.
    Response, all inside the COVID fitting path, pf.py untouched:
    (i)   rescale statistics are reported per arm and per config: median, max,
          number of cells with scale > 3, number of cells whose raw median is
          zero at any horizon;
    (ii)  THE FIX: the particle-filter width arm is additionally run at the
          TRUE production settings. Round one's PF arm, despite its header,
          diverged from production on three counts: pf_jitter 0.02 where
          production RunSpec uses 0.30; pf_observable_mode written as the
          numeral 1, which the filter reads as neither mode name and treats as
          'instantaneous', where production passes 'integrated'; and a single
          unpooled replicate where production runs 3 seeded replicates and
          pools them after a PER-REPLICATE anchor rescale (pf.collect).
          The flu 4.06 reference came from the production pipeline, so the
          production-true configuration is the like-for-like one. Low jitter
          is also the mechanistically plausible cause of the dead-state cells:
          a 0.02 jitter cannot rediversify a cloud after a degenerate
          resampling, 0.30 can.
    (iii) the round-one configuration is retained and rerun as the paired
          continuity arm, so "does the pathology recur, and does the fix
          remove it" is answered within this round on the same seeds.
    WIDTH CONFIGS, named here once:
      PF-PROD  particles 10000, jitter 0.30, pf_observable_mode integrated,
               3 replicates per cell seeded by derive_seed(state, asof, rep),
               replicate-pooled after per-replicate rescale, Reff proposal
               uniform (pf.py's own VARS_1S scale; omega stays loguniform,
               eps2/phi2 uniform). PRIMARY for the width gate.
      PF-R1    particles 10000, jitter 0.02, pf_observable_mode "1"
               (instantaneous in effect), 1 replicate, seed 20260822 + cell
               index, Reff loguniform. Paired with round one's 1.105.
    Pre-registered fallback: if PF-PROD fails to execute (engine error, not a
    bad number), the width gate falls back to PF-R1 and says so.

=============================================================================
4. THE GATES, IN THIS ORDER
=============================================================================
4.1 BIMODALITY, the reason for this round.
    Estimator: the VALIDATED one from gate_a_report.py (integrate 10 years,
    read the final 3, drop boundary indices, report peaks per year), never
    gate_a.py's 52-week window whose edge artifact is documented there.
    Integration in the population form (N passed, s0 0.85, R0 = Reff/s0,
    impr 0, the ARM's OWN gamma), on each fit's posterior-median parameter
    set, chains pooled (the round-one method; per-chain median sets are also
    reported as a robustness line, because a component-wise median across
    chains in different modes can be incoherent).
    CONTROLS, simulated before freezing with this exact estimator:
      negative (k=1): R0 3.0 / eps1 0.50 / 22 wk waning -> 1.00 peaks/yr;
                      R0 2.0 / eps1 0.35 / 52 wk waning -> 1.00 peaks/yr.
      positive (k=2): R0 1.6 / eps1 0.30 / eps2 0.30 / 26 wk -> 2.00;
                      R0 1.4 / eps1 0.10 / eps2 0.30 / 26 wk -> 2.00;
                      R0 1.3 / eps1 0.05 / eps2 0.25 / 20 wk -> 2.00;
                      R0 1.2 / eps1 0.03 / eps2 0.20 / 17 wk -> 2.00.
      The last one matters most: two peaks per year are reachable at the
      COLLAPSED round-one eps1 and an omega INSIDE the round-one posterior
      range, purely through an identified eps2. So a unimodal A2 verdict
      cannot be blamed on the estimator or on unreachability.
      DISCREPANCY RECORDED: gate_a_report.py's docstring cites its k=1
      positive control "R0 3.0 / eps1 0.50 / 22-week waning" as returning
      2.00 peaks/yr; re-run before freezing, it returns 1.00 under every
      variant tried (both gammas, four phases, normalized and population
      forms). The round-one NEGATIVE finding is unaffected (it is a direct
      measurement on the fits), but that control string should not be cited
      again; the six controls above are the checked replacements.
    PASS (A2): median peaks-per-year across the 9 fits >= 1.5, AND at least
    5 of 9 fits individually bimodal at the round-one criterion
    (peaks_per_year >= 1.9). A1's paired numbers are reported beside (round
    one measured 1.00 and 0 of 9). Observed wave counts in the same fit
    windows are reported for reference.
4.2 WIDTH, bar unchanged. Central-95% width relative to actual, pooled over
    the held-out, break-excluded cells (33 of 36), on PF-PROD (primary).
    PASS <= 4.06. THIS ROUND HAS NO FAIL-NOT-KILL BAND: the approved plan
    kills on width above 4.06 outright. Coverage is reported beside the
    width both times, because relative width is not scale-free across
    diseases (round-one caveat, upheld). A2 is compared against A1 paired,
    same config, same seeds. PF-R1 and the AMCMC widths (pooled-chain raw and
    rescaled, and chain-0-only for the (b) measurement) are reported as
    secondary lines.
4.3 IDENTIFIABILITY of the two new dimensions.
    eps2 (pooled post-burn draws across chains and fits):
      PINNED if >= 25% of draws sit within 2% of either bound (the round-one
      omega rule, reused verbatim).
      PRIOR-SHAPED if the Kolmogorov distance between the pooled posterior
      and the uniform(0, 0.4) prior is D < 0.10.
      Identified means neither. Per-fit quantiles, bound fractions and D are
      all reported.
    phi2: circular, period 26; a linear R-hat or a bound fraction would be
      meaningless (the round-one phi1 lesson). Reported: the circular
      resultant length per fit (0 = uniform on the circle = nothing
      identified; rises toward 1 with concentration), with the note that
      phi2 is unidentifiable by construction wherever eps2 is near zero.
    Also reported, pre-registered as observations rather than gates: whether
    eps1 recovers above its collapsed 0.03 when eps2 is available (per-fit
    paired A1 vs A2 medians), and whether omega stays in its round-one
    2.66 to 5.11 month range or absorbs differently under a second harmonic
    (per-fit paired medians, months).
4.4 SAMPLER HEALTH, reported not gated. Round one pre-registered that R-hat
    and ESS would fail at roughly the influenza reference (R-hat 3.25) and
    they did (3.38 excluding phi1); that prediction transfers unchanged, now
    excluding BOTH circular phases from the headline number. Only a
    degradation far beyond the flu reference would be a COVID finding.

KILL RULES (any one kills the second-harmonic arm):
  * A2 fails the bimodality gate (4.1), or
  * A2's PF-PROD width exceeds 4.06 (4.2), or
  * eps2 is unidentified: pinned, or prior-shaped at D < 0.10 (4.3).

=============================================================================
5. WHAT THIS ROUND CANNOT SETTLE
=============================================================================
No skill claim; relWIS against CovidHub-baseline is Gate B. Three states,
three origins, one season. The bimodality gate asks whether the FITTED model
is capable of the observed annual pattern, which is a necessary condition for
mechanistic credibility, not a demonstration of forecast skill.

=============================================================================
USAGE
=============================================================================
    .venv/bin/python research/covid-phase0/gate_a2.py --smoke   # plumbing
    .venv/bin/python research/covid-phase0/gate_a2.py           # the round
    .venv/bin/python research/covid-phase0/gate_a2.py --report  # re-score
Results land in research/covid-phase0/out/round2/.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core.runs import derive_seed                               # noqa: E402
from flubnf import covid_vintage as cv                              # noqa: E402
from flubnf.covid_fit import (materialize_for_profile, omega_to_months,  # noqa: E402
                              resolve_for_profile, write_exp,
                              write_profile_conf)
from flubnf.profiles import COVID                                   # noqa: E402
from flubnf.settings import BNG, LOCATIONS, PY_ENGINE, PYBNF        # noqa: E402
from flubnf.sihrs_fit import run_pybnf                              # noqa: E402
from flubnf.unimodal_guard import all_peaks, count_waves            # noqa: E402

OUT = Path(__file__).resolve().parent / "out" / "round2"
PYBNF_BIN = os.path.expanduser("~/.venvs/flubnf/bin/pybnf")

SEASON_START = "2025-06-01"
ORIGINS = ("2026-01-07", "2026-02-04", "2026-03-04")
STATES = ("New York", "Pennsylvania", "North Carolina")   # round-one selection,
# re-asserted at runtime against the frozen rule (>= 2 waves at 2026-03-18)
SELECTION_ASOF = "2026-03-18"
HORIZONS = (1, 2, 3, 4)

FLU_WIDTH_REFERENCE = 4.06        # pass AND kill bar this round (no fail band)
EPS2_PIN_BAR = 0.25
EPS2_BOUND_TOL = 0.02
EPS2_KS_BAR = 0.10
BIMODAL_MEDIAN_BAR = 1.5
BIMODAL_FIT_CRITERION = 1.9       # round-one per-fit criterion, unchanged
BIMODAL_COUNT_BAR = 5

# realized-household generation time for arm A3 (Manica 2022; see section 2)
GT_REALIZED_DAYS = 3.59

TPL_2H = REPO / "flubnf/templates/SIHRS_pop_covid_2h.bngl"

PRIORS_2H = {
    "Reff__FREE": COVID.fitted_priors["Reff__FREE"],
    "eps1__FREE": COVID.fitted_priors["eps1__FREE"],
    "phi1__FREE": COVID.fitted_priors["phi1__FREE"],
    "eps2__FREE": (0.0, 0.4),
    "phi2__FREE": (0.0, 26.0),
    "omega__FREE": COVID.fitted_priors["omega__FREE"],
    "mult__FREE": COVID.fitted_priors["mult__FREE"],
    "r__FREE": COVID.fitted_priors["r__FREE"],
}


def preregistration_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]


def build_arms() -> dict:
    """The three arm profiles. Rebuilt per process; A1 IS the shipped COVID."""
    a2 = dataclasses.replace(COVID, template=TPL_2H, fitted_priors=PRIORS_2H)
    a3 = dataclasses.replace(
        a2, fixed=dataclasses.replace(
            COVID.fixed,
            generation_time_days=GT_REALIZED_DAYS,
            gamma_per_week=7.0 / GT_REALIZED_DAYS,
            gt_note=("SENSITIVITY ARM A3: realized household generation time "
                     "3.59 d (95% CrI 3.55-3.60), Manica 2022, the memo's "
                     "original reading. A1/A2 carry the intrinsic 6.84 d.")))
    return {"A1": COVID, "A2": a2, "A3": a3}


# ---------------------------------------------------------------------------
# state-selection re-assertion (the round-one rule, applied, not trusted)
# ---------------------------------------------------------------------------

def assert_states() -> None:
    truth = cv.vintage_path(SELECTION_ASOF)
    for st in STATES:
        s = resolve_for_profile(COVID, st, truth_csv=truth,
                                locations_csv=LOCATIONS,
                                season_start=SEASON_START,
                                as_of=SELECTION_ASOF)
        assert count_waves(s.observed) >= 2, f"{st} no longer satisfies the rule"


# ---------------------------------------------------------------------------
# diagnostics (same estimators as round one, so numbers are comparable)
# ---------------------------------------------------------------------------

def _ess(x) -> float:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 50 or x.std() == 0:
        return float("nan")
    y = x - x.mean()
    f = np.fft.rfft(y, 2 * n)
    ac = np.fft.irfft(f * np.conjugate(f))[:n].real
    ac /= ac[0]
    s = 0.0
    for k in range(1, n - 1, 2):
        p = ac[k] + ac[k + 1]
        if p < 0:
            break
        s += p
    return float(n / (1 + 2 * s))


def _rhat(chains) -> float:
    cs = [np.asarray(c, float) for c in chains]
    cs = [c[np.isfinite(c)] for c in cs]
    cs = [c for c in cs if len(c) > 20]
    if len(cs) < 2:
        return float("nan")
    n = min(len(c) for c in cs)
    cs = [c[-n:] for c in cs]
    W = float(np.mean([c.var(ddof=1) for c in cs]))
    if W <= 0:
        return float("nan")
    B = n * float(np.var([c.mean() for c in cs], ddof=1))
    return float(np.sqrt((((n - 1) / n) * W + B / n) / W))


def read_chains(runs: Path, burn_frac: float = 0.25) -> dict:
    out: dict = {}
    for p in sorted(runs.glob("params_*.txt")):
        try:
            d = pd.read_csv(p, sep=r"\s+")
        except Exception:
            continue
        if len(d) <= 40:
            continue
        d = d.iloc[int(len(d) * burn_frac):]
        for col in d.columns:
            v = pd.to_numeric(d[col], errors="coerce").dropna().to_numpy()
            if v.size:
                out.setdefault(col, []).append(v)
    return out


def convergence(chains: dict) -> dict:
    out = {}
    for col, arrs in chains.items():
        per = [_ess(a) for a in arrs]
        out[col] = {"n_chains": len(arrs),
                    "rhat": _rhat(arrs),
                    "ess_per_chain_min": float(np.nanmin(per)) if per else float("nan")}
    return out


def pooled(chains: dict, key: str) -> np.ndarray:
    arrs = chains.get(key + "__FREE") or chains.get(key) or []
    if not arrs:
        return np.array([])
    v = np.concatenate(arrs)
    return v[np.isfinite(v)]


def ks_vs_uniform(v: np.ndarray, lo: float, hi: float) -> float:
    """Kolmogorov distance between draws and the uniform(lo, hi) prior."""
    v = np.sort(v[(v >= lo) & (v <= hi)])
    if v.size < 100:
        return float("nan")
    cdf = (v - lo) / (hi - lo)
    ecdf_hi = np.arange(1, v.size + 1) / v.size
    ecdf_lo = np.arange(0, v.size) / v.size
    return float(max(np.max(np.abs(ecdf_hi - cdf)), np.max(np.abs(cdf - ecdf_lo))))


def resultant_length(phase: np.ndarray, period: float) -> float:
    if phase.size == 0:
        return float("nan")
    z = np.exp(2j * np.pi * phase / period)
    return float(abs(z.mean()))


# ---------------------------------------------------------------------------
# one AMCMC fit (fix (b): every chain's trajectory read and kept, thinned)
# ---------------------------------------------------------------------------

def one_fit(args) -> dict:
    arm, state, asof, iters, timeout, keep, out_root = args
    OUT2 = Path(out_root)
    profile = build_arms()[arm]
    tag = f"{arm}_{state.replace(' ', '_')}_{asof}"
    part = OUT2 / "parts" / f"{tag}.json"
    if part.is_file():
        try:
            return json.loads(part.read_text())
        except Exception:
            pass
    W = OUT2 / "work" / tag
    shutil.rmtree(W, ignore_errors=True)
    W.mkdir(parents=True, exist_ok=True)
    rec: dict = {"arm": arm, "state": state, "asof": asof, "ok": False,
                 "iters": iters, "gamma_per_week": profile.fixed.gamma_per_week}
    try:
        truth = cv.vintage_path(asof)
        s = resolve_for_profile(profile, state, truth_csv=truth,
                                locations_csv=LOCATIONS,
                                season_start=SEASON_START, as_of=asof)
        assert int(s.times[-1]) == s.n_obs - 1, "missing weeks: fix traj indexing"
        rec.update({"n_obs": int(s.n_obs), "waves": int(count_waves(s.observed)),
                    "last_observed": float(s.observed[-1]),
                    "data_edge": cv.data_edge(asof),
                    "i0": float(s.i0),
                    "peaks": [[int(p.index), float(p.value)]
                              for p in all_peaks(s.observed)]})
        sfx = f"{state.replace(' ', '_')}_covid"
        t_end = int(s.n_obs) + 8
        m = materialize_for_profile(profile, s, W / "m.bngl", suffix=sfx,
                                    t_end=t_end)
        e = write_exp(s, W / f"{sfx}.exp")
        c = write_profile_conf(profile, s, model=m, exp=e, out_dir=W / "res",
                               conf_path=W / "c.conf", bng_command=str(BNG),
                               max_iterations=iters,
                               burn_in=max(50, iters // 4),
                               adaptive=max(50, iters // 4),
                               population_size=4)
        r = run_pybnf(c, pybnf_binary=PYBNF_BIN, cwd=W / "scratch",
                      timeout_sec=timeout)
        rec["elapsed"] = r.get("elapsed", 0.0)
        if not r["ok"]:
            rec["reason"] = (r.get("reason") or r.get("stderr_tail", ""))[-400:]
        else:
            runs = W / "res" / "Results" / "A_MCMC" / "Runs"
            ch = read_chains(runs)
            rec["convergence"] = convergence(ch)
            rec["medians"] = {k: float(np.median(np.concatenate(v)))
                              for k, v in ch.items()}
            rec["medians_by_chain"] = {
                k: [float(np.median(a)) for a in v] for k, v in ch.items()}
            # identifiability raw material, pooled draws thinned for storage
            def draws(k, n=4000):
                v = pooled(ch, k)
                if v.size > n:
                    v = v[:: max(1, v.size // n)]
                return v.tolist()
            rec["draws"] = {k: draws(k) for k in
                            ("eps1", "eps2", "phi1", "phi2", "omega")
                            if pooled(ch, k).size}
            # fix (b): EVERY chain trajectory, thinned to ~3000 rows per chain
            files = sorted(runs.glob("*traj_noise*"))
            n = int(s.n_obs)
            by_chain: dict = {}
            for ci, f in enumerate(files):
                tr = np.genfromtxt(f)
                if tr.ndim == 1:
                    tr = tr.reshape(1, -1)
                if n - 1 + max(HORIZONS) >= tr.shape[1]:
                    continue
                step = max(1, tr.shape[0] // 3000)
                tr = tr[::step]
                by_chain[str(ci)] = {str(h): tr[:, n - 1 + h].tolist()
                                     for h in (0,) + HORIZONS}
            rec["n_traj_files"] = len(files)
            rec["samples_by_chain"] = by_chain
            rec["ok"] = bool(by_chain)
            if not by_chain:
                rec["reason"] = "no usable traj_noise output"
    except Exception as exc:
        rec["reason"] = f"{type(exc).__name__}: {exc}"[:400]
    finally:
        if not keep:
            shutil.rmtree(W, ignore_errors=True)
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_text(json.dumps(rec))
    return rec


# ---------------------------------------------------------------------------
# particle-filter width arms (configs PF-PROD and PF-R1, section 3)
# ---------------------------------------------------------------------------

_RUNNER = '''"""Auto-generated PF runner (gate A round two width arms)."""
import json, os, shutil, sys
sys.path.insert(0, {pybnf!r})
from pathlib import Path
cells = json.load(open({cells!r}))
res = {{}}
for c in cells:
    d = Path(c["dir"])
    shutil.rmtree(d / "out", ignore_errors=True)
    (d / "out" / "Results").mkdir(parents=True)
    cwd = os.getcwd(); os.chdir(d)
    try:
        from pybnf.parse import load_config
        from pybnf.pf import ParticleFilter
        ParticleFilter(load_config(str(d / "pf.conf"))).run(None)
        res[c["key"]] = "ok"
    except Exception as e:
        res[c["key"]] = f"FAIL: {{e}}"[:300]
    finally:
        os.chdir(cwd)
    json.dump(res, open({out!r}, "w"))
json.dump(res, open({out!r}, "w"))
'''

PF_CONFIGS = {
    "prod": {"jitter": 0.30, "mode": "integrated", "replicates": 3,
             "reff_uniform": True,
             "why": "production-true; the config the flu 4.06 was measured at"},
    "r1": {"jitter": 0.02, "mode": "1", "replicates": 1,
           "reff_uniform": False,
           "why": "round-one config, paired continuity with 1.105"},
}


def _vars_block(profile, reff_uniform: bool) -> str:
    out = []
    for name, (lo, hi) in profile.fitted_priors.items():
        log = name in profile.log_scale_vars and lo > 0
        if name == "Reff__FREE" and reff_uniform:
            log = False
        out.append(f"{'loguniform_var' if log else 'uniform_var'} = "
                   f"{name} {lo} {hi}")
    return "\n".join(out) + "\n"


def _defaults_block(profile) -> str:
    """Numeric seeds for netgen only (the PF draws its cloud from the prior).
    omega at the literature centre, eps2 mid-box, phi2 mid-period."""
    vals = {"Reff__FREE": 1.20, "eps1__FREE": 0.15, "phi1__FREE": 22.0,
            "eps2__FREE": 0.15, "phi2__FREE": 13.0, "omega__FREE": 0.0256,
            "mult__FREE": 0.05, "r__FREE": 8.0}
    lines = "".join(f"{k} {vals[k]}\n" for k in profile.fitted_priors)
    return "begin parameters\n" + lines


def pf_prepare(arm: str, cfg_name: str, workroot: Path, particles: int,
               states=STATES, origins=ORIGINS) -> list:
    cfg = PF_CONFIGS[cfg_name]
    profile = build_arms()[arm]
    cells, idx = [], 0
    for state in states:
        for asof in origins:
            truth = cv.vintage_path(asof)
            s = resolve_for_profile(profile, state, truth_csv=truth,
                                    locations_csv=LOCATIONS,
                                    season_start=SEASON_START, as_of=asof)
            for rep in range(cfg["replicates"]):
                if cfg_name == "r1":
                    seed = 20260822 + idx      # round one: seed0 + cell index
                else:
                    seed = derive_seed(state, asof, rep)
                tag = f"{state.replace(' ', '_')}_{asof}_rep{rep}"
                d = workroot / tag
                d.mkdir(parents=True, exist_ok=True)
                sfx = f"{state.replace(' ', '_')}_covid"
                m = materialize_for_profile(profile, s, d / "m.bngl",
                                            suffix=sfx, t_end=int(s.n_obs) + 8)
                m.write_text(m.read_text().replace(
                    "begin parameters\n", _defaults_block(profile), 1))
                write_exp(s, d / f"{sfx}.exp")
                r = subprocess.run(["perl", str(BNG), "m.bngl"],
                                   capture_output=True, text=True,
                                   cwd=str(d), timeout=600)
                if not (d / "m.net").is_file():
                    raise RuntimeError(
                        f"netgen failed for {arm} {state}: {r.stdout[-300:]}")
                (d / "pf.conf").write_text(
                    f"""bng_command = {BNG}
model = {d}/m.bngl : {d}/{sfx}.exp
output_dir = {d}/out
fit_type = pf
objfunc = neg_bin_dynamic
num_particles = {particles}
pf_jitter = {cfg['jitter']}
pf_observable_mode = {cfg['mode']}
pf_forecast_weeks = 4
population_size = 1
max_iterations = 1
seed = {seed}
{_vars_block(profile, cfg['reff_uniform'])}""")
                cells.append({"key": tag, "dir": str(d), "state": state,
                              "asof": asof, "rep": rep, "seed": seed,
                              "n_obs": int(s.n_obs),
                              "last_observed": float(s.observed[-1]),
                              "data_edge": cv.data_edge(asof)})
            idx += 1
    (workroot / "cells.json").write_text(json.dumps(cells))
    return cells


def pf_execute(workroot: Path, timeout: float) -> dict:
    runner = workroot / "runner.py"
    out_json = workroot / "status.json"
    runner.write_text(_RUNNER.format(pybnf=str(PYBNF),
                                     cells=str(workroot / "cells.json"),
                                     out=str(out_json)))
    p = subprocess.Popen([str(PY_ENGINE), str(runner)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                         text=True)
    t0 = time.time()
    while p.poll() is None:
        if time.time() - t0 > timeout:
            p.kill()
            raise RuntimeError("PF runner timed out")
        time.sleep(2)
    if not out_json.is_file():
        raise RuntimeError("PF runner produced no status: "
                           + (p.stderr.read() if p.stderr else "")[-500:])
    return json.loads(out_json.read_text())


def pf_score(cells: list, status: dict) -> pd.DataFrame:
    """Per-replicate anchor rescale, then replicate-pooled quantiles per cell,
    exactly the shape of pf.collect. Raw (unrescaled) pooled quantiles beside.
    """
    truth = cv.vintage_frame(cv.vintages()[-1])
    tmap = {(r.location_name, str(r.date)[:10]): float(r.value)
            for r in truth.itertuples()}
    by_cell: dict = {}
    for c in cells:
        key = (c["state"], c["asof"])
        ent = by_cell.setdefault(key, {"reps": [], "meta": c})
        if status.get(c["key"]) != "ok":
            ent["reps"].append({"ok": False, "reason": status.get(c["key"])})
            continue
        runs = Path(c["dir"]) / "out" / "Results" / "A_MCMC" / "Runs"
        g = sorted(runs.glob("*traj_noise*"))
        if not g:
            ent["reps"].append({"ok": False, "reason": "no traj_noise"})
            continue
        tr = np.genfromtxt(g[0])
        if tr.ndim == 1:
            tr = tr.reshape(1, -1)
        n = c["n_obs"]
        origin = tr[:, n - 1]
        origin = origin[np.isfinite(origin)]
        med0 = float(np.median(origin)) if origin.size else float("nan")
        scale = c["last_observed"] / med0 if med0 > 0 else 1.0
        ent["reps"].append({"ok": True, "scale": float(scale),
                            "med0_raw": med0,
                            "traj": {str(h): tr[:, n - 1 + h] for h in HORIZONS}})
    rows = []
    for (state, asof), ent in by_cell.items():
        meta = ent["meta"]
        good = [r for r in ent["reps"] if r.get("ok")]
        for h in HORIZONS:
            target = str((pd.Timestamp(meta["data_edge"])
                          + pd.Timedelta(days=7 * h)).date())
            excl = COVID.excluded_for(meta["data_edge"], target)
            actual = tmap.get((state, target))
            if not good or excl or actual is None or actual <= 0:
                rows.append({"state": state, "asof": asof, "horizon": h,
                             "target": target, "excluded": bool(excl),
                             "usable": False,
                             "n_reps_ok": len(good)})
                continue
            raw = np.concatenate([r["traj"][str(h)] for r in good])
            resc = np.concatenate([r["traj"][str(h)] * r["scale"]
                                   for r in good])
            raw = raw[np.isfinite(raw)]
            resc = resc[np.isfinite(resc)]
            lo, hi = np.percentile(resc, [2.5, 97.5])
            rlo, rhi = np.percentile(raw, [2.5, 97.5])
            rows.append({
                "state": state, "asof": asof, "horizon": h, "target": target,
                "actual": actual, "usable": True, "excluded": False,
                "n_reps_ok": len(good),
                "anchor_scales": [round(r["scale"], 3) for r in good],
                "anchor_scale_max": float(max(r["scale"] for r in good)),
                "median_rescaled": float(np.median(resc)),
                "median_raw": float(np.median(raw)),
                "width_rel_rescaled": float((hi - lo) / actual),
                "width_rel_raw": float((rhi - rlo) / actual),
                "covered_rescaled": bool(lo <= actual <= hi),
                "covered_raw": bool(rlo <= actual <= rhi)})
    return pd.DataFrame(rows)


def pf_run_arm(arm: str, cfg_name: str, out_root: Path, particles: int,
               timeout: float, states=STATES, origins=ORIGINS, keep=False) -> dict:
    cache = out_root / f"pf_{cfg_name}_{arm}.json"
    if cache.is_file():
        return json.loads(cache.read_text())
    W = out_root / f"pf_work_{cfg_name}_{arm}"
    shutil.rmtree(W, ignore_errors=True)
    W.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    cells = pf_prepare(arm, cfg_name, W, particles, states, origins)
    status = pf_execute(W, timeout)
    df = pf_score(cells, status)
    use = df[df["usable"] == True]                               # noqa: E712
    def med(col):
        return float(use[col].median()) if len(use) else float("nan")
    res = {
        "arm": arm, "config": cfg_name, **PF_CONFIGS[cfg_name],
        "particles": particles,
        "cells_total": int(len(df)),
        "cells_excluded": int(df["excluded"].sum()) if len(df) else 0,
        "cells_scored": int(len(use)),
        "elapsed_min": round((time.time() - t0) / 60.0, 1),
        "width_rel_median_rescaled": med("width_rel_rescaled"),
        "width_rel_median_raw": med("width_rel_raw"),
        "coverage_rescaled": (float(use["covered_rescaled"].mean())
                              if len(use) else float("nan")),
        "coverage_raw": (float(use["covered_raw"].mean())
                         if len(use) else float("nan")),
        "by_horizon": ({int(k): round(float(v), 3) for k, v in
                        use.groupby("horizon")["width_rel_rescaled"]
                        .median().items()} if len(use) else {}),
        "rescale_stats": rescale_stats_pf(df),
        "failures": {k: v for k, v in status.items() if v != "ok"},
    }
    df.to_csv(out_root / f"pf_cells_{cfg_name}_{arm}.csv", index=False)
    cache.write_text(json.dumps(res, indent=2))
    if not keep:
        shutil.rmtree(W, ignore_errors=True)
    return res


def rescale_stats_pf(df: pd.DataFrame) -> dict:
    use = df[df["usable"] == True]                               # noqa: E712
    if not len(use):
        return {"n": 0}
    per_cell = use.groupby(["state", "asof"]).agg(
        smax=("anchor_scale_max", "max"),
        raw_med_min=("median_raw", "min")).reset_index()
    scales = per_cell["smax"].to_numpy(float)
    return {"n_cells": int(len(per_cell)),
            "scale_median": float(np.median(scales)),
            "scale_max": float(scales.max()),
            "n_cells_scale_gt3": int((scales > 3).sum()),
            "n_cells_raw_median_zero": int((per_cell["raw_med_min"]
                                            <= 1e-9).sum()),
            "per_cell": [{"state": r.state, "asof": r.asof,
                          "scale_max": round(float(r.smax), 2)}
                         for r in per_cell.itertuples()]}


# ---------------------------------------------------------------------------
# AMCMC width cells (raw, per-chain rescaled, and the chain-0 measurement)
# ---------------------------------------------------------------------------

def amcmc_cells(records: list) -> pd.DataFrame:
    truth = cv.vintage_frame(cv.vintages()[-1])
    tmap = {(r.location_name, str(r.date)[:10]): float(r.value)
            for r in truth.itertuples()}
    rows = []
    for rec in records:
        if not rec.get("ok"):
            continue
        anchor = rec["data_edge"]
        sbc = rec["samples_by_chain"]
        chains = sorted(sbc, key=int)
        scales = {}
        for ci in chains:
            o = np.asarray(sbc[ci]["0"], float)
            o = o[np.isfinite(o)]
            m0 = float(np.median(o)) if o.size else float("nan")
            scales[ci] = rec["last_observed"] / m0 if m0 > 0 else 1.0
        for h in HORIZONS:
            target = str((pd.Timestamp(anchor) + pd.Timedelta(days=7 * h)).date())
            excl = COVID.excluded_for(anchor, target)
            actual = tmap.get((rec["state"], target))
            raw = np.concatenate([np.asarray(sbc[ci][str(h)], float)
                                  for ci in chains])
            resc = np.concatenate([np.asarray(sbc[ci][str(h)], float)
                                   * scales[ci] for ci in chains])
            raw = raw[np.isfinite(raw)]
            resc = resc[np.isfinite(resc)]
            c0 = np.asarray(sbc[chains[0]][str(h)], float)
            c0 = c0[np.isfinite(c0)]
            if excl or actual is None or actual <= 0 or raw.size < 20:
                rows.append({"arm": rec["arm"], "state": rec["state"],
                             "asof": rec["asof"], "horizon": h,
                             "target": target, "excluded": bool(excl),
                             "usable": False})
                continue
            lo, hi = np.percentile(resc, [2.5, 97.5])
            rlo, rhi = np.percentile(raw, [2.5, 97.5])
            zlo, zhi = np.percentile(c0, [2.5, 97.5])
            rows.append({
                "arm": rec["arm"], "state": rec["state"], "asof": rec["asof"],
                "horizon": h, "target": target, "actual": actual,
                "usable": True, "excluded": False,
                "anchor_scale_max": float(max(scales.values())),
                "anchor_scales": [round(scales[c], 3) for c in chains],
                "median_raw": float(np.median(raw)),
                "width_rel_rescaled": float((hi - lo) / actual),
                "width_rel_raw": float((rhi - rlo) / actual),
                "width_rel_chain0_raw": float((zhi - zlo) / actual),
                "covered_rescaled": bool(lo <= actual <= hi),
                "covered_raw": bool(rlo <= actual <= rhi)})
    return pd.DataFrame(rows)


def rescale_stats_amcmc(cells: pd.DataFrame, arm: str) -> dict:
    use = cells[(cells["arm"] == arm) & (cells["usable"] == True)]  # noqa: E712
    if not len(use):
        return {"n": 0}
    per_cell = use.groupby(["state", "asof"]).agg(
        smax=("anchor_scale_max", "max"),
        raw_med_min=("median_raw", "min")).reset_index()
    scales = per_cell["smax"].to_numpy(float)
    return {"n_cells": int(len(per_cell)),
            "scale_median": float(np.median(scales)),
            "scale_max": float(scales.max()),
            "n_cells_scale_gt3": int((scales > 3).sum()),
            "n_cells_raw_median_zero": int((per_cell["raw_med_min"]
                                            <= 1e-9).sum())}


# ---------------------------------------------------------------------------
# gate 4.1: bimodality, with the validated estimator
# ---------------------------------------------------------------------------

def peaks_per_year(params: dict, years: int = 10, read: int = 3) -> dict:
    from flubnf.simulate_sihrs import simulate_sihrs
    res = simulate_sihrs(params, n_weeks=52 * years)
    hw = np.asarray(res.H_weekly, float)[-(52 * read + 1):-1]
    if not np.all(np.isfinite(hw)) or hw.max() <= 0:
        return {"peaks_per_year": float("nan"), "reason": "non-finite or dead"}
    pk = [p for p in all_peaks(hw) if 0 < p.index < len(hw) - 1]
    return {"peaks_per_year": len(pk) / float(read),
            "peak_weeks_in_window": [int(p.index) for p in pk],
            "trough_to_peak": float(hw.max() / max(hw.min(), 1e-12))}


def _sim_params(med: dict, gamma: float, rho: float, gammaH: float,
                s0: float) -> dict:
    def g(k, d=0.0):
        return float(med.get(k + "__FREE", med.get(k, d)))
    return dict(N=1.0e7, s0=s0, i0=1.0e-4, R0=g("Reff") / s0,
                eps1=g("eps1"), phi1=g("phi1"), eps2=g("eps2"),
                phi2=g("phi2"), gamma=gamma, rho=rho, gammaH=gammaH,
                omega=g("omega"), mult=g("mult"), impr=0.0)


def bimodality(records: list, arm: str) -> dict:
    arms = build_arms()
    profile = arms[arm]
    f = profile.fixed
    out = []
    for r in records:
        if r.get("arm") != arm or not r.get("ok"):
            continue
        med = r.get("medians") or {}
        p = _sim_params(med, f.gamma_per_week, f.rho, f.gammaH_per_week,
                        f.s0_default)
        try:
            d = peaks_per_year(p)
        except Exception as exc:
            d = {"peaks_per_year": float("nan"),
                 "error": f"{type(exc).__name__}: {exc}"[:160]}
        # robustness: each chain's own median set (coherent within a mode)
        per_chain = []
        mbc = r.get("medians_by_chain") or {}
        n_chains = max((len(v) for v in mbc.values()), default=0)
        for ci in range(n_chains):
            cm = {k: v[ci] for k, v in mbc.items() if len(v) > ci}
            try:
                per_chain.append(peaks_per_year(_sim_params(
                    cm, f.gamma_per_week, f.rho, f.gammaH_per_week,
                    f.s0_default))["peaks_per_year"])
            except Exception:
                per_chain.append(float("nan"))
        def g(k):
            return float(med.get(k + "__FREE", med.get(k, float("nan"))))
        d.update({"state": r["state"], "asof": r["asof"],
                  "observed_waves_in_fit_window": r.get("waves"),
                  "peaks_per_year_by_chain": [round(v, 2) if np.isfinite(v)
                                              else None for v in per_chain],
                  "omega_months": round(omega_to_months(g("omega")), 2),
                  "Reff": round(g("Reff"), 3), "eps1": round(g("eps1"), 3),
                  "eps2": (round(g("eps2"), 3) if np.isfinite(g("eps2"))
                           else None),
                  "phi1": round(g("phi1"), 1),
                  "phi2": (round(g("phi2"), 1) if np.isfinite(g("phi2"))
                           else None)})
        out.append(d)
    vals = [d["peaks_per_year"] for d in out
            if np.isfinite(d.get("peaks_per_year", np.nan))]
    n_bimodal = int(sum(v >= BIMODAL_FIT_CRITERION for v in vals))
    return {"per_fit": out,
            "median_peaks_per_year": (float(np.median(vals)) if vals
                                      else float("nan")),
            "n_bimodal": n_bimodal, "n_fits": len(vals),
            "fraction_bimodal": (n_bimodal / len(vals)) if vals else float("nan")}


# ---------------------------------------------------------------------------
# gate 4.3: identifiability of eps2/phi2, plus eps1 and omega observations
# ---------------------------------------------------------------------------

def identifiability(records: list, arm: str) -> dict:
    lo, hi = PRIORS_2H["eps2__FREE"]
    w = hi - lo
    per_fit, eps2_all = [], []
    for r in records:
        if r.get("arm") != arm or not r.get("ok"):
            continue
        dr = r.get("draws") or {}
        e2 = np.asarray(dr.get("eps2", []), float)
        p2 = np.asarray(dr.get("phi2", []), float)
        p1 = np.asarray(dr.get("phi1", []), float)
        if e2.size:
            eps2_all.append(e2)
        q = (np.percentile(e2, [2.5, 50, 97.5]).round(4).tolist()
             if e2.size else None)
        per_fit.append({
            "state": r["state"], "asof": r["asof"],
            "eps2_q": q,
            "eps2_frac_at_low": (float(np.mean(e2 <= lo + EPS2_BOUND_TOL * w))
                                 if e2.size else None),
            "eps2_frac_at_high": (float(np.mean(e2 >= hi - EPS2_BOUND_TOL * w))
                                  if e2.size else None),
            "eps2_ks_vs_prior": (round(ks_vs_uniform(e2, lo, hi), 3)
                                 if e2.size else None),
            "phi2_resultant_len": (round(resultant_length(p2, 26.0), 3)
                                   if p2.size else None),
            "phi1_resultant_len": (round(resultant_length(p1, 52.0), 3)
                                   if p1.size else None)})
    if eps2_all:
        v = np.concatenate(eps2_all)
        at_lo = float(np.mean(v <= lo + EPS2_BOUND_TOL * w))
        at_hi = float(np.mean(v >= hi - EPS2_BOUND_TOL * w))
        ks = ks_vs_uniform(v, lo, hi)
        pinned = max(at_lo, at_hi) >= EPS2_PIN_BAR
        prior_shaped = np.isfinite(ks) and ks < EPS2_KS_BAR
        verdict = ("KILL (pinned)" if pinned else
                   "KILL (prior-shaped)" if prior_shaped else "IDENTIFIED")
        pooled_summary = {
            "n_draws": int(v.size),
            "q": np.percentile(v, [2.5, 25, 50, 75, 97.5]).round(4).tolist(),
            "frac_at_low_bound": at_lo, "frac_at_high_bound": at_hi,
            "ks_vs_prior": round(float(ks), 3),
            "bars": {"pinned": EPS2_PIN_BAR, "prior_shaped_ks": EPS2_KS_BAR},
            "verdict": verdict}
    else:
        pooled_summary = {"verdict": "NO DATA"}
    return {"eps2_pooled": pooled_summary, "per_fit": per_fit}


def paired_params(records: list) -> dict:
    """eps1 recovery and omega behavior, A1 vs A2 vs A3, per (state, origin)."""
    idx = {}
    for r in records:
        if r.get("ok"):
            idx[(r["arm"], r["state"], r["asof"])] = r.get("medians") or {}

    def g(m, k):
        return float(m.get(k + "__FREE", m.get(k, float("nan"))))
    rows = []
    for st in STATES:
        for asof in ORIGINS:
            row = {"state": st, "asof": asof}
            for arm in ("A1", "A2", "A3"):
                m = idx.get((arm, st, asof))
                if m is None:
                    continue
                row[f"eps1_{arm}"] = round(g(m, "eps1"), 4)
                row[f"omega_months_{arm}"] = round(
                    omega_to_months(g(m, "omega")), 2)
                if arm != "A1":
                    row[f"eps2_{arm}"] = round(g(m, "eps2"), 4)
            rows.append(row)
    e1_a1 = [r["eps1_A1"] for r in rows if "eps1_A1" in r]
    e1_a2 = [r["eps1_A2"] for r in rows if "eps1_A2" in r]
    om_a1 = [r["omega_months_A1"] for r in rows if "omega_months_A1" in r]
    om_a2 = [r["omega_months_A2"] for r in rows if "omega_months_A2" in r]
    return {"per_fit": rows,
            "eps1_median_A1": float(np.median(e1_a1)) if e1_a1 else None,
            "eps1_median_A2": float(np.median(e1_a2)) if e1_a2 else None,
            "omega_months_range_A1": ([min(om_a1), max(om_a1)] if om_a1 else None),
            "omega_months_range_A2": ([min(om_a2), max(om_a2)] if om_a2 else None)}


def sampler_summary(records: list, arm: str) -> dict:
    rhat_np, ess_np = [], []
    for r in records:
        if r.get("arm") != arm or not r.get("ok"):
            continue
        for col, d in (r.get("convergence") or {}).items():
            if col.startswith(("phi1", "phi2")):
                continue                    # circular; linear stats meaningless
            if np.isfinite(d.get("rhat", np.nan)):
                rhat_np.append(d["rhat"])
            if np.isfinite(d.get("ess_per_chain_min", np.nan)):
                ess_np.append(d["ess_per_chain_min"])
    return {"rhat_max_excl_phases": float(np.nanmax(rhat_np)) if rhat_np else None,
            "rhat_median_excl_phases": (float(np.nanmedian(rhat_np))
                                        if rhat_np else None),
            "ess_per_chain_min_excl_phases": (float(np.nanmin(ess_np))
                                              if ess_np else None),
            "influenza_reference_rhat": 3.25}


# ---------------------------------------------------------------------------
# the verdict
# ---------------------------------------------------------------------------

def verdict_table(records: list, cells: pd.DataFrame, pf: dict) -> dict:
    bim = {a: bimodality(records, a) for a in ("A1", "A2", "A3")}
    ident = {a: identifiability(records, a) for a in ("A2", "A3")}

    b2 = bim["A2"]
    bim_pass = (np.isfinite(b2["median_peaks_per_year"])
                and b2["median_peaks_per_year"] >= BIMODAL_MEDIAN_BAR
                and b2["n_bimodal"] >= BIMODAL_COUNT_BAR)

    a2w = pf.get(("prod", "A2")) or {}
    prod_ok = bool(a2w.get("cells_scored", 0)) and not a2w.get("failures")
    primary_cfg = "prod"
    if not a2w or a2w.get("cells_scored", 0) == 0:
        primary_cfg = "r1"                    # pre-registered fallback
        a2w = pf.get(("r1", "A2")) or {}
    width_val = a2w.get("width_rel_median_rescaled", float("nan"))
    width_pass = np.isfinite(width_val) and width_val <= FLU_WIDTH_REFERENCE

    e2v = ident["A2"]["eps2_pooled"].get("verdict", "NO DATA")
    eps2_pass = e2v == "IDENTIFIED"

    kill = (not bim_pass) or (not width_pass) or (not eps2_pass)
    return {
        "preregistration_sha256_16": preregistration_hash(),
        "gate_1_bimodality": {
            "bars": {"median_peaks_per_year": BIMODAL_MEDIAN_BAR,
                     "n_bimodal_of_9": BIMODAL_COUNT_BAR,
                     "per_fit_criterion": BIMODAL_FIT_CRITERION},
            "A1": {k: bim["A1"][k] for k in
                   ("median_peaks_per_year", "n_bimodal", "n_fits")},
            "A2": {k: bim["A2"][k] for k in
                   ("median_peaks_per_year", "n_bimodal", "n_fits")},
            "A3": {k: bim["A3"][k] for k in
                   ("median_peaks_per_year", "n_bimodal", "n_fits")},
            "verdict_A2": "PASS" if bim_pass else "KILL"},
        "gate_2_width": {
            "bar_pass_and_kill": FLU_WIDTH_REFERENCE,
            "primary_config": primary_cfg,
            "prod_config_ok": bool(prod_ok),
            "A1": _w(pf, primary_cfg, "A1"),
            "A2": _w(pf, primary_cfg, "A2"),
            "A3": _w(pf, primary_cfg, "A3"),
            "secondary_r1": {a: _w(pf, "r1", a) for a in ("A1", "A2", "A3")},
            "verdict_A2": "PASS" if width_pass else "KILL"},
        "gate_3_identifiability": {
            "A2_eps2": ident["A2"]["eps2_pooled"],
            "A3_eps2": ident["A3"]["eps2_pooled"],
            "verdict_A2": "PASS" if eps2_pass else "KILL"},
        "overall": "PASS" if not kill else "KILL",
        "bimodality_detail": bim,
        "identifiability_detail": ident,
    }


def _w(pf: dict, cfg: str, arm: str) -> dict:
    d = pf.get((cfg, arm)) or {}
    return {"width_rel_median_rescaled": d.get("width_rel_median_rescaled"),
            "width_rel_median_raw": d.get("width_rel_median_raw"),
            "coverage_rescaled": d.get("coverage_rescaled"),
            "rescale_stats": {k: v for k, v in
                              (d.get("rescale_stats") or {}).items()
                              if k != "per_cell"}}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--iters", type=int, default=20000)
    ap.add_argument("--timeout", type=float, default=10800.0)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--particles", type=int, default=10000)
    ap.add_argument("--pf-timeout", type=float, default=10800.0)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--report", action="store_true",
                    help="re-score from cached parts, run nothing")
    ap.add_argument("--skip-pf", action="store_true")
    a = ap.parse_args()

    out_root = OUT.parent / "round2_smoke" if a.smoke else OUT
    out_root.mkdir(parents=True, exist_ok=True)
    states = STATES[:1] if a.smoke else STATES
    origins = ORIGINS[-1:] if a.smoke else ORIGINS
    iters = 400 if a.smoke else a.iters
    particles = 200 if a.smoke else a.particles
    arms = ("A1", "A2", "A3")

    print(f"pre-registration {preregistration_hash()}")
    print(f"arms {list(arms)}  states {list(states)}  origins {list(origins)}"
          f"  iters {iters}  particles {particles}")
    assert_states()

    pf: dict = {}
    if not a.report and not a.skip_pf:
        for cfg in ("prod", "r1"):
            for arm in arms:
                t0 = time.time()
                pf[(cfg, arm)] = pf_run_arm(arm, cfg, out_root, particles,
                                            a.pf_timeout, states, origins,
                                            keep=a.keep)
                r = pf[(cfg, arm)]
                print(f"PF {cfg}/{arm}: width "
                      f"{r['width_rel_median_rescaled']:.3f} rescaled / "
                      f"{r['width_rel_median_raw']:.3f} raw, coverage "
                      f"{r['coverage_rescaled']:.3f}, "
                      f"rescale max {r['rescale_stats'].get('scale_max')}, "
                      f"{time.time() - t0:.0f}s, failures "
                      f"{len(r['failures'])}", flush=True)
    else:
        for cfg in ("prod", "r1"):
            for arm in arms:
                p = out_root / f"pf_{cfg}_{arm}.json"
                if p.is_file():
                    pf[(cfg, arm)] = json.loads(p.read_text())

    jobs = [(arm, s, o, iters, a.timeout, a.keep, str(out_root))
            for s in states for o in origins for arm in arms]
    if a.report:
        records = []
        for j in jobs:
            p = out_root / "parts" / \
                f"{j[0]}_{j[1].replace(' ', '_')}_{j[2]}.json"
            if p.is_file():
                records.append(json.loads(p.read_text()))
    else:
        t0 = time.time()
        if a.workers <= 1 or len(jobs) == 1:
            records = [one_fit(j) for j in jobs]
        else:
            with ProcessPoolExecutor(max_workers=a.workers) as ex:
                records = list(ex.map(one_fit, jobs))
        print(f"{len(jobs)} AMCMC fits in {time.time() - t0:.0f}s; "
              f"ok {sum(r.get('ok', False) for r in records)}", flush=True)

    cells = amcmc_cells(records)
    if len(cells):
        cells.to_csv(out_root / "amcmc_cells.csv", index=False)
    amcmc_width = {}
    for arm in arms:
        use = cells[(cells.get("arm") == arm) & (cells.get("usable") == True)] \
            if len(cells) else pd.DataFrame()
        amcmc_width[arm] = {
            "width_rel_median_rescaled": (float(use["width_rel_rescaled"]
                                                .median()) if len(use) else None),
            "width_rel_median_raw": (float(use["width_rel_raw"].median())
                                     if len(use) else None),
            "width_rel_median_chain0_raw": (float(use["width_rel_chain0_raw"]
                                                  .median()) if len(use) else None),
            "coverage_rescaled": (float(use["covered_rescaled"].mean())
                                  if len(use) else None),
            "rescale_stats": rescale_stats_amcmc(cells, arm) if len(cells) else {}}

    table = verdict_table(records, cells, pf)
    result = {
        "table": table,
        "amcmc_width_secondary": amcmc_width,
        "paired_parameters": paired_params(records),
        "sampler": {arm: sampler_summary(records, arm) for arm in arms},
        "fits_ok": {arm: sum(1 for r in records
                             if r.get("arm") == arm and r.get("ok"))
                    for arm in arms},
        "settings": {"iters": iters, "particles": particles,
                     "states": list(states), "origins": list(origins),
                     "smoke": bool(a.smoke)},
    }
    # records are heavy (chain samples); store them separately
    (out_root / "gate_a2_records.json").write_text(json.dumps(records))
    (out_root / "gate_a2_result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("table",)}, indent=2))
    print(json.dumps(table, indent=2))


if __name__ == "__main__":
    main()
