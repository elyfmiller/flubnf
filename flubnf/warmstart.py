"""Carry last week's converged posterior into this week's fit.

WHY THIS IS THE RIGHT SHAPE FOR A COMPETITION WEEK
--------------------------------------------------
Measured over the 2025-26 vintages, one competition week changes almost nothing
in the fitted series. Revision mass by age of the observation:

    newest week   68%      median revision +4.2%, mean +21.1%
    one week old  12%
    two weeks old  6%
    three or more 14%      median revision 0.0%, p90 under 1%

So ~90% of the likelihood is bit-identical to what was already converged on. The
fit does not need rediscovering; it needs perturbing by one new point and one
revision. Starting from last week's posterior is therefore not an optimisation
trick -- it is a statement about how little actually changed.

That also means the between-week budget is where convergence should be bought.
Competition day only has to absorb a small perturbation, which is what makes a
wall-clock deadline with a best-fit-so-far guarantee affordable.

THE FOOTGUN, AND WHY EVERY FUNCTION HERE TAKES `priors`
-------------------------------------------------------
PyBNF assigns starting values BY INDEX:

    p.value = self.config.config['starting_params'][i]      # algorithms.py:2175

and orders parameters by the order their `*_var` lines appear in the .conf,
because `Config._load_variables` iterates `config.keys()` and dicts preserve
insertion order. Emit the values in a different order and PyBNF will warm-start
Reff with mult's value, fit happily, and tell you nothing. This project has just
spent a day on a bug whose entire signature was silence, so `starting_params`
refuses to build a line unless the names it was given match, in order, the
priors dict that wrote the conf.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Posterior:
    """A fitted posterior, reduced to what a warm start needs."""
    medians: dict            # name -> posterior median
    samples: dict            # name -> post-burn-in draws
    objective: float         # best objective seen, for `choose()`
    n_chains: int

    def as_start(self, priors: Mapping[str, tuple]) -> list:
        return [self.medians[k] for k in priors]


def read_posterior(runs_dir: Path, priors: Mapping[str, tuple],
                   burn_frac: float = 0.25) -> Optional[Posterior]:
    """Pool `params_*.txt` from a completed PyBNF run into a `Posterior`.

    Returns None rather than a partial object when the run produced nothing
    usable -- a caller must be able to tell "no warm start available" from
    "warm start with garbage", and the cold-start path depends on that.
    """
    runs_dir = Path(runs_dir)
    files = sorted(runs_dir.glob("params_*.txt"))
    if not files:
        return None
    per_chain, obj = {k: [] for k in priors}, np.inf
    n_ok = 0
    for f in files:
        try:
            d = pd.read_csv(f, sep=r"\s+")
        except Exception:
            continue
        if len(d) < 8:
            continue
        d = d.iloc[int(len(d) * burn_frac):]
        got = False
        for name in priors:
            col = name if name in d.columns else name.replace("__FREE", "")
            if col not in d.columns:
                continue
            v = pd.to_numeric(d[col], errors="coerce").dropna().to_numpy()
            if v.size:
                per_chain[name].append(v)
                got = True
        for oc in ("obj", "objective", "Obj"):
            if oc in d.columns:
                v = pd.to_numeric(d[oc], errors="coerce").dropna()
                if len(v):
                    obj = min(obj, float(v.min()))
        n_ok += bool(got)

    # params_*.txt carries no objective column (verified on real output); the
    # objective lives in Results/sorted_params*.txt one level up. Leaving this
    # unread meant objective=inf everywhere downstream: the preseason
    # tol-stopping rule could never fire, and choose() compared inf to inf.
    if not np.isfinite(obj):
        results_dir = runs_dir.parents[1]
        for name in ("sorted_params_final.txt", "sorted_params.txt",
                     "sorted_params_backup.txt"):
            f = results_dir / name
            if f.is_file():
                # The header line has one more token than data rows (a leading
                # '#'), so a naive read_csv silently shifts every column left
                # and "Obj" lands on the first parameter's values. Parse the
                # header ourselves.
                try:
                    with open(f) as fh:
                        header = fh.readline().split()
                    cols = header[1:] if header and header[0] == "#" else header
                    sp = pd.read_csv(f, sep=r"\s+", skiprows=1, names=cols)
                except Exception:
                    continue
                for oc in ("Obj", "obj", "objective"):
                    if oc in sp.columns:
                        v = pd.to_numeric(sp[oc], errors="coerce").dropna()
                        if len(v):
                            obj = min(obj, float(v.min()))
                if np.isfinite(obj):
                    break
    if not n_ok:
        return None
    samples, medians = {}, {}
    for name in priors:
        if not per_chain[name]:
            return None                     # a missing parameter is not a warm start
        s = np.concatenate(per_chain[name])
        samples[name] = s
        medians[name] = float(np.median(s))
    return Posterior(medians=medians, samples=samples,
                     objective=float(obj), n_chains=n_ok)


def starting_params(post: Posterior, priors: Mapping[str, tuple],
                    clip: bool = True) -> str:
    """The `starting_params` conf line, in the SAME order as the var lines.

    `clip` matters when bounds were narrowed between rounds: a median that now
    sits outside its own prior would be rejected, and silently falling back to a
    random start is exactly the failure this module exists to prevent.
    """
    missing = [k for k in priors if k not in post.medians]
    if missing:
        raise ValueError(
            f"warm start is missing {missing}; refusing to emit a misaligned "
            f"starting_params line (PyBNF assigns by index, not by name)")
    vals = []
    for name in priors:
        lo, hi = priors[name]
        v = float(post.medians[name])
        if clip:
            v = min(max(v, lo), hi)
        vals.append(v)
    return "starting_params = " + " ".join(f"{v:.8g}" for v in vals)


def pinned_parameters(post: Posterior, priors: Mapping[str, tuple]) -> list:
    """Which parameters sit against a wall. Delegates the test to `autoparam`.

    CIRCULAR parameters are excluded outright: phi1 at 0 or 52 is the same
    phase, not a wall -- flagging it triggers probe rounds and bound widening
    that can never "clear" (measured: Ohio phi1 posterior at 49.8 with a
    (0, 52) box would read as pinned forever).
    """
    from .autoparam import CIRCULAR, is_pinned
    return [n for n, (lo, hi) in priors.items()
            if n not in CIRCULAR
            and n in post.samples and is_pinned(post.samples[n], lo, hi)]


def cold_start_needed(prev: Optional[Posterior], priors: Mapping[str, tuple],
                      max_gap_weeks: Optional[int] = None,
                      gap_weeks: Optional[int] = None) -> tuple:
    """Should this fit start cold? Returns (bool, reason).

    Cold starts are not only for the first week ever. A posterior from many
    weeks ago is a worse starting point than the prior, because the epidemic has
    moved and the stale medians will drag the chain toward last month's regime.
    """
    if prev is None:
        return True, "no previous posterior (first fit of the season)"
    missing = [k for k in priors if k not in prev.medians]
    if missing:
        return True, f"previous posterior lacks {missing} (model changed)"
    if (max_gap_weeks is not None and gap_weeks is not None
            and gap_weeks > max_gap_weeks):
        return True, f"previous fit is {gap_weeks} weeks stale (> {max_gap_weeks})"
    if not np.isfinite(prev.objective):
        return True, "previous objective is not finite"
    return False, "warm start"
