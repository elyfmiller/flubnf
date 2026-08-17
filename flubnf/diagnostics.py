"""AMCMC chain diagnostics + automated reaction to poor fits.

The PyBNF AMCMC run writes per-iteration scores (`scores_N.txt`) and
parameter samples (`params_N.txt`) per chain. This module reads those
and computes summary diagnostics the workflow can act on:

  - **Acceptance proxy**: fraction of consecutive iterations where the
    score CHANGED (a chain that's stuck at one mode shows near-zero
    score variation; an MH chain that's mixing well rejects often but
    accepts enough to move).
  - **Score range / spread**: log-likelihood IQR over post-burn samples.
    Small range = chain stuck; very large = posterior wandering.
  - **Boundary-distance**: fraction of each parameter's samples sitting
    within a tolerance of the prior boundary. Flags params that want
    wider priors.
  - **Effective sample size proxy**: 1 / (1 + 2 * sum of autocorrelations).
    A laptop-scale fast estimator using lag-1 autocorrelation only.

The `react_to_diagnostics()` function turns a DiagnosticReport into a
list of `Action` objects the orchestrator can apply:
  - `EXPAND_BOUND(param, factor)`: the param hit the prior edge
  - `REFIT_MORE_ITERS`: chain still mixing; needs more burn-in
  - `REFIT_NEW_SEED`: chain stuck in a local mode; retry
  - `REFIT_WITH_TIGHTER_PRIOR(param)`: posterior super wide; constrain
  - `NO_ACTION`: fit looks healthy
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from .results import read_amcmc_chain


@dataclass
class ParamStats:
    name: str
    median: float
    p05: float
    p95: float
    iqr: float
    frac_near_low: float    # fraction of post-burn samples within tol of low prior
    frac_near_high: float
    low_bound: Optional[float] = None
    high_bound: Optional[float] = None


@dataclass
class DiagnosticReport:
    state: str
    n_samples: int
    score_iqr: float
    score_range: float
    acceptance_proxy: float       # fraction of consecutive-iter score changes
    ess_proxy: float              # effective sample size approximation
    param_stats: list[ParamStats] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        """A rough overall health flag — true means no significant red flags."""
        return len(self.warnings) == 0


def compute_diagnostics(
    state_results: Path,
    state: str,
    *,
    bounds: Optional[Iterable] = None,
    boundary_tol: float = 0.05,
    burn_in_drop: int = 200,
) -> Optional[DiagnosticReport]:
    """Compute AMCMC diagnostics from PyBNF outputs in state_results.

    `bounds` is an optional iterable of FreeParam (or anything with
    .name/.low/.high) used to compute boundary-distance fractions.
    Drops the first `burn_in_drop` samples as burn-in.
    """
    chain = read_amcmc_chain(state_results, state)
    if chain is None or chain.empty:
        return None
    if len(chain) > burn_in_drop:
        chain = chain.iloc[burn_in_drop:].reset_index(drop=True)
    if chain.empty:
        return None

    # Scores: load directly so we can see acceptance behavior.
    scores_path = state_results / "Results" / "A_MCMC" / "Runs" / "scores_0.txt"
    scores: Optional[np.ndarray] = None
    if scores_path.exists():
        try:
            scores = np.loadtxt(scores_path)
            if len(scores) > burn_in_drop:
                scores = scores[burn_in_drop:]
        except Exception:
            scores = None

    warnings: list[str] = []

    # Score-based diagnostics.
    if scores is not None and len(scores) >= 2:
        score_iqr = float(np.subtract(*np.percentile(scores, [75, 25])))
        score_range = float(scores.max() - scores.min())
        acceptance_proxy = float(np.mean(np.diff(scores) != 0))
        # ESS proxy: lag-1 autocorrelation.
        if len(scores) >= 10:
            centered = scores - scores.mean()
            denom = float(np.sum(centered ** 2)) or 1.0
            rho1 = float(np.sum(centered[:-1] * centered[1:]) / denom)
            ess_proxy = float(len(scores) * (1.0 - abs(rho1)) / (1.0 + abs(rho1)))
        else:
            ess_proxy = float(len(scores))
        if acceptance_proxy < 0.05:
            warnings.append(f"chain mixing poor (acceptance proxy {acceptance_proxy:.2%})")
        if score_range < 1e-6:
            warnings.append("score range ~0 — chain may be stuck")
        if ess_proxy < 50:
            warnings.append(f"effective sample size very low (~{ess_proxy:.0f})")
    else:
        score_iqr = score_range = acceptance_proxy = ess_proxy = float("nan")
        warnings.append("scores file missing or too short")

    # Per-param boundary + spread.
    param_stats: list[ParamStats] = []
    bound_map: dict[str, tuple[float, float]] = {}
    if bounds is not None:
        for b in bounds:
            bound_map[b.name] = (b.low, b.high)

    for col in chain.columns:
        if not col.endswith("__FREE"):
            continue
        vals = pd.to_numeric(chain[col], errors="coerce").dropna().to_numpy()
        if len(vals) == 0:
            continue
        med = float(np.median(vals))
        p05 = float(np.percentile(vals, 5))
        p95 = float(np.percentile(vals, 95))
        iqr = float(np.subtract(*np.percentile(vals, [75, 25])))
        lo, hi = bound_map.get(col, (None, None))
        if lo is not None and hi is not None and hi > lo:
            rng = hi - lo
            tol = boundary_tol * rng
            frac_low = float(np.mean(vals <= lo + tol))
            frac_high = float(np.mean(vals >= hi - tol))
            if frac_low > 0.30:
                warnings.append(f"{col} crowds low prior bound ({frac_low:.0%})")
            if frac_high > 0.30:
                warnings.append(f"{col} crowds high prior bound ({frac_high:.0%})")
        else:
            frac_low = frac_high = float("nan")
        param_stats.append(ParamStats(
            name=col, median=med, p05=p05, p95=p95, iqr=iqr,
            frac_near_low=frac_low, frac_near_high=frac_high,
            low_bound=lo, high_bound=hi,
        ))

    return DiagnosticReport(
        state=state,
        n_samples=len(chain),
        score_iqr=score_iqr,
        score_range=score_range,
        acceptance_proxy=acceptance_proxy,
        ess_proxy=ess_proxy,
        param_stats=param_stats,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Reactive actions
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Action:
    kind: str             # one of: expand_bound, refit_more_iters, refit_new_seed, no_action
    param: Optional[str] = None
    factor: float = 1.0
    detail: str = ""


def react_to_diagnostics(report: DiagnosticReport) -> list[Action]:
    """Decide what corrective actions to take given the diagnostics."""
    if report.healthy:
        return [Action(kind="no_action", detail="diagnostics clean")]
    actions: list[Action] = []
    # Boundary issues -> expand bounds.
    for ps in report.param_stats:
        if ps.frac_near_low > 0.30:
            actions.append(Action(
                kind="expand_bound", param=ps.name, factor=-0.5,
                detail=f"{ps.frac_near_low:.0%} of samples at low edge",
            ))
        if ps.frac_near_high > 0.30:
            actions.append(Action(
                kind="expand_bound", param=ps.name, factor=+0.5,
                detail=f"{ps.frac_near_high:.0%} of samples at high edge",
            ))
    # Poor mixing -> refit with new seed.
    if (not np.isnan(report.acceptance_proxy)
            and report.acceptance_proxy < 0.05):
        actions.append(Action(
            kind="refit_new_seed",
            detail=f"acceptance proxy {report.acceptance_proxy:.2%}",
        ))
    # Low ESS -> more iters next time.
    if not np.isnan(report.ess_proxy) and report.ess_proxy < 50:
        actions.append(Action(
            kind="refit_more_iters",
            factor=2.0,
            detail=f"ESS proxy {report.ess_proxy:.0f}",
        ))
    return actions or [Action(kind="no_action")]


# ===========================================================================
# SIRS-vs-beta degeneracy detector (SIRS-migration, Phase 4)
# ===========================================================================
@dataclass(frozen=True)
class DegeneracyFlag:
    """Result of the SIRS-vs-flexible-beta degeneracy check.

    A second wave can be explained by EITHER waning (omega>0 refilling S) OR a
    positive late beta amplitude. With omega FIXED, the smooth beta is the only
    fitted lever — but a late `db_k` whose posterior straddles 0 or pins its
    bound *while a second wave is present* is the unambiguous symptom that the
    fit cannot decide and the structure is degenerate for that state.
    """
    degenerate: bool
    reason: str
    amplitude_param: Optional[str] = None
    second_wave: bool = False


def _has_second_wave(observed: np.ndarray, rebound_frac: float) -> bool:
    """Deterministic: after the global peak, does the series fall to a trough
    and then rise again by at least `rebound_frac` of the peak height?"""
    y = np.asarray(observed, dtype=float)
    y = y[np.isfinite(y)]
    if len(y) < 5:
        return False
    peak = float(y.max())
    if peak <= 0:
        return False
    pk = int(np.argmax(y))
    tail = y[pk:]
    if len(tail) < 3:
        return False
    trough = float(tail.min())
    post_trough = tail[int(np.argmin(tail)):]
    rebound = float(post_trough.max()) - trough
    return rebound >= rebound_frac * peak


def detect_beta_waning_degeneracy(
    chain: "pd.DataFrame",
    observed: np.ndarray,
    *,
    bounds: Optional[Iterable] = None,
    bound_tol: float = 0.05,
    rebound_frac: float = 0.30,
) -> DegeneracyFlag:
    """Flag the SIRS-vs-beta degeneracy for one fitted state.

    Deterministic. Looks at the LAST (highest-index) `db_k` amplitude in the
    posterior `chain`. Flags degeneracy iff a second wave is present in
    `observed` AND that amplitude either straddles 0 (sign ambiguous) or pins a
    prior bound. When no second wave is present, a db_k near 0 just means that
    transition is unused — not degeneracy — so we do not flag.
    """
    second_wave = _has_second_wave(observed, rebound_frac)
    if chain is None or getattr(chain, "empty", True):
        return DegeneracyFlag(False, "empty chain", None, second_wave)

    db_cols = sorted(
        [c for c in chain.columns
         if c.startswith("db") and c[2:].split("__")[0].isdigit()],
        key=lambda c: int(c[2:].split("__")[0]),
    )
    if not db_cols:
        return DegeneracyFlag(False, "no logistic amplitudes in chain",
                              None, second_wave)
    last = db_cols[-1]
    vals = pd.to_numeric(chain[last], errors="coerce").dropna().to_numpy()
    if len(vals) == 0:
        return DegeneracyFlag(False, f"{last} has no samples", last, second_wave)

    p05, p95 = (float(x) for x in np.percentile(vals, [5, 95]))
    median = float(np.median(vals))
    straddles_zero = p05 < 0.0 < p95

    pinned = False
    if bounds is not None:
        bmap = {getattr(fp, "name", None): fp for fp in bounds}
        fp = bmap.get(last)
        if fp is not None:
            rng = float(fp.high) - float(fp.low)
            if rng > 0:
                pinned = (abs(median - float(fp.low)) < bound_tol * rng
                          or abs(median - float(fp.high)) < bound_tol * rng)

    if not second_wave:
        return DegeneracyFlag(
            False, "no second wave observed; amplitude shape is benign",
            last, second_wave)
    if straddles_zero or pinned:
        why = "straddles 0" if straddles_zero else "pins prior bound"
        return DegeneracyFlag(
            True,
            f"second wave present and {last} {why} "
            f"(median={median:.3g}, p05={p05:.3g}, p95={p95:.3g}) — "
            f"beta-vs-waning degeneracy suspected",
            last, second_wave)
    return DegeneracyFlag(
        False,
        f"second wave explained by {last} (median={median:.3g}, "
        f"95% CI excludes 0)",
        last, second_wave)
