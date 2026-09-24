"""LEGACY (AMCMC warm-start loop; no runtime caller, kept for tests/test_weekly_loop.py).

AMCMC warm-start fitting loop: probe for pins, then commit. AMCMC
fails convergence diagnostics on this posterior (docs/archive/RELEASE-1.0.md,
Known limitations).

A competition week barely changes the series (68% of revision lands on the
newest point, 80% on the newest two), so the week's fit perturbs a converged
state: converge between weeks on data through T-1, then absorb the new point
on competition day. PyBNF reloads `adaptive_files/` (MLE_params.txt,
diffMatrix.txt = the learned covariance, diff.txt) under `continue_run = 1`,
restoring the adapted proposal; a few KB per state, overwritten weekly.

Fits are I/O-bound (~2.1 fits/min whatever the worker count), so a 7-hour
budget allows ~3 long rounds. Hence:

    PROBE   ~2000 iters, check for pinned parameters, widen and repeat
    COMMIT  once `clean_rounds_required` consecutive rounds pin nothing,
            spend the entire remaining budget in one uninterrupted run

* A clean round counts only if the bounds did not change since the previous
  clean one (otherwise the rounds test different models).
* Keep the better fit, not the newest: a refit whose pins did not clear
  measured 20% worse (`autoparam.choose()`).
* `best_so_far` updates only when a round COMPLETES; a round cut off by the
  deadline is discarded (a half-adapted chain is not a posterior), so there
  is always a completed fit to submit.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional

from .autoparam import RoundResult, choose, diagnose, next_priors
from .warmstart import Posterior, cold_start_needed, pinned_parameters


@dataclass
class Round:
    index: int
    iters: int
    kind: str                      # "probe" | "commit"
    priors: dict
    warm: bool
    elapsed_s: float = 0.0
    pinned: tuple = ()
    ok: bool = False
    objective: float = float("inf")
    bounds_changed: bool = False


@dataclass
class LoopPlan:
    """Everything the schedule needs, separated from the fitting itself."""
    budget_s: float                       # compute available AFTER padding
    probe_iters: int = 2000
    commit_iters_cap: int = 40_000
    clean_rounds_required: int = 2
    max_probe_rounds: int = 4
    fits_per_min: float = 0.45             # measured I/O ceiling
    n_states: int = 52

    def round_cost_s(self, iters: int) -> float:
        """Wall-clock for one round over all states, from the measured ceiling."""
        return (self.n_states / self.fits_per_min) * (iters / 1000.0) * 60.0

    def affordable_iters(self, remaining_s: float) -> int:
        """Largest round that fits in `remaining_s`, rounded down to 500."""
        per_1000 = self.round_cost_s(1000)
        if per_1000 <= 0:
            return 0
        n = int((remaining_s / per_1000) * 1000)
        return max(0, min(self.commit_iters_cap, (n // 500) * 500))


@dataclass
class LoopState:
    plan: LoopPlan
    priors: dict
    started: float = field(default_factory=time.monotonic)
    rounds: list = field(default_factory=list)
    best: Optional[Round] = None
    _clean_streak: int = 0
    _bounds_stable_since_clean: bool = True

    def remaining_s(self) -> float:
        return max(0.0, self.plan.budget_s - (time.monotonic() - self.started))

    def next_round(self) -> Optional[Round]:
        """The next round to run, or None when the budget is spent."""
        rem = self.remaining_s()
        committed = any(r.kind == "commit" for r in self.rounds)
        if committed:
            return None

        if (self._clean_streak >= self.plan.clean_rounds_required
                or len(self.rounds) >= self.plan.max_probe_rounds):
            iters = self.plan.affordable_iters(rem)
            if iters < 500:
                return None
            return Round(index=len(self.rounds), iters=iters, kind="commit",
                         priors=dict(self.priors), warm=True)

        if rem < self.plan.round_cost_s(self.plan.probe_iters):
            # not enough left for another probe: spend what remains committing
            iters = self.plan.affordable_iters(rem)
            if iters < 500:
                return None
            return Round(index=len(self.rounds), iters=iters, kind="commit",
                         priors=dict(self.priors), warm=True)

        return Round(index=len(self.rounds), iters=self.plan.probe_iters,
                     kind="probe", priors=dict(self.priors),
                     warm=len(self.rounds) > 0)

    def record(self, rnd: Round, post: Optional[Posterior]) -> None:
        """Fold a COMPLETED round in. Never call this for an aborted round."""
        self.rounds.append(rnd)
        if not rnd.ok or post is None:
            self._clean_streak = 0
            return

        rnd.pinned = tuple(pinned_parameters(post, rnd.priors))
        rnd.objective = post.objective

        if rnd.pinned:
            diag = diagnose(list(rnd.pinned), post.medians, rnd.priors)
            widened = next_priors(diag, rnd.priors)
            rnd.bounds_changed = widened != rnd.priors
            self.priors = widened
            self._clean_streak = 0
            self._bounds_stable_since_clean = not rnd.bounds_changed
        else:
            # A clean round only counts if the model it tested is the model the
            # previous clean round tested.
            if self._bounds_stable_since_clean:
                self._clean_streak += 1
            else:
                self._clean_streak = 1
            self._bounds_stable_since_clean = True

        if self.best is None:
            self.best = rnd
        else:
            keep = choose(
                RoundResult(objective=self.best.objective,
                            n_pinned=len(self.best.pinned), ok=self.best.ok),
                RoundResult(objective=rnd.objective,
                            n_pinned=len(rnd.pinned), ok=rnd.ok))
            if keep == "second":
                self.best = rnd

    def summary(self) -> dict:
        return {
            "rounds": len(self.rounds),
            "probes": sum(1 for r in self.rounds if r.kind == "probe"),
            "committed": any(r.kind == "commit" for r in self.rounds),
            "clean_streak": self._clean_streak,
            "best_round": None if self.best is None else self.best.index,
            "best_pinned": () if self.best is None else self.best.pinned,
            "final_priors": self.priors,
            "elapsed_s": time.monotonic() - self.started,
            "budget_s": self.plan.budget_s,
        }


def run_week(plan: LoopPlan, priors: Mapping[str, tuple],
             fit: Callable[[Round], tuple],
             prev: Optional[Posterior] = None,
             gap_weeks: Optional[int] = None,
             max_gap_weeks: int = 3,
             trusted: bool = False,
             on_round: Optional[Callable[[Round], None]] = None) -> LoopState:
    """Drive one competition week.

    `fit(round) -> (ok, Posterior|None)` runs all states for that round and is
    the only thing that touches PyBNF; the schedule here is pure and testable.

    `trusted=True` skips probing (last week ended clean with unchanged
    bounds; probes at 0% pinning cost about half the iterations). Trust is
    one week deep: the caller resets it on any pin or bound change.
    """
    st = LoopState(plan=plan, priors=dict(priors))
    cold, why = cold_start_needed(prev, priors, max_gap_weeks, gap_weeks)
    if trusted and not cold:
        st._clean_streak = plan.clean_rounds_required
    while True:
        rnd = st.next_round()
        if rnd is None:
            break
        if rnd.index == 0 and cold:
            rnd.warm = False
        t0 = time.monotonic()
        ok, post = fit(rnd)
        rnd.elapsed_s = time.monotonic() - t0
        rnd.ok = bool(ok)
        st.record(rnd, post)
        if on_round:
            on_round(rnd)
    return st
