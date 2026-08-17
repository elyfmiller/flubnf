"""The competition-week fitting loop: warm start, probe for pins, then commit.

THE SHAPE, AND WHY IT IS THIS SHAPE
-----------------------------------
A competition week changes almost nothing in the fitted series. Measured over the
2025-26 vintages, 68% of all revision lands on the newest observation and 80% on
the newest two; everything three weeks or older has a median revision of exactly
zero. So the week's fit is a small perturbation of a converged state, not a
rediscovery, and the loop is built around that:

    between weeks   converge on data through week T-1, unhurried
    competition day absorb one new point + one revision, against a deadline

PyBNF supports this natively. `Adaptive_MCMC` persists `adaptive_files/` --
`MLE_params.txt`, `diffMatrix.txt` (the LEARNED COVARIANCE), `diff.txt` -- and
reloads all three under `continue_run = 1`. That restores the adapted proposal,
not merely a starting point, which is most of what an adaptive chain has earned.
It is also tiny: a few KB per state, ~100 KB for the whole country, so the
warm-start state can simply be overwritten each week and everything else thrown
away.

EXPLORE, THEN COMMIT
--------------------
Throughput is I/O-bound at ~2.1 fits/min regardless of worker count (doubling
workers bought 6%), so a 52-state round costs ~25 min per 1000 iterations. A
7-hour budget therefore affords roughly three 5000-iteration rounds -- too coarse
to probe and still leave time to converge. Hence short probe rounds and one long
commit:

    PROBE   ~2000 iters, check for pinned parameters, widen and repeat
            (still ~1000 post-burn-in draws, far more than a pin test needs)
    COMMIT  once `clean_rounds_required` consecutive rounds pin nothing,
            spend the entire remaining budget in one uninterrupted run

TWO RULES THAT LOOK PEDANTIC AND ARE NOT
----------------------------------------
* A clean round only counts toward the commit threshold if the bounds did not
  change since the previous clean one. A round that widened a bound and a round
  that pinned nothing are testing different models; counting them as agreeing
  would commit on the strength of a comparison never made.
* A refit is not automatically better. `autoparam.choose()` exists because a
  refit whose pins did NOT clear measured 20% worse than the original, so the
  loop keeps the better fit rather than the newest one.

DEADLINES ARE HONOURED BY CONSTRUCTION
--------------------------------------
`best_so_far` is updated only when a round COMPLETES. If the wall clock expires
mid-round that round is discarded, because a half-finished adaptive chain has not
finished adapting and its posterior is not a posterior. There is always a
submittable fit, and it is always one that ran to completion.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
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
    fits_per_min: float = 2.1             # measured I/O ceiling
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

    `trusted=True` skips the probe phase entirely: the previous week ended
    clean with unchanged bounds, so re-proving cleanliness would burn budget
    demonstrating what last week already demonstrated. The 18-week season run
    spent 2-3 probes/week at 0% pinning throughout -- roughly half the
    effective iterations. Trust is one week deep: any pin or bound change
    this week resets it at the caller.
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
