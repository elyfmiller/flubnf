"""Fringe-case ledger — codified failure modes and their automated handling.

The long-game vision (per MIGRATION.md): accumulate a system that handles
every flu-season fringe case better than any human reviewer would. Each
case is encoded here as a `FringeCase` with:

  - `detect(observed, session, results_dir)` — returns True iff the
    case's trigger condition matches the current state.
  - `applies(state, observed)` — pre-filter (e.g. only small states).
  - `recommended_actions` — string list describing what the case calls
    for. The orchestrator (weekly_job) uses these as advisories or
    automatically applies them.

Adding a new fringe case is just a class. Tests in
`tests/test_fringe_cases.py` enforce each one continues to fire on its
fixture.

This is the spine of the project's accumulating-coverage strategy:
each new season surfaces new failure modes; encode them here so they
keep being handled next year.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .session import StateSession

log = logging.getLogger(__name__)


@dataclass
class CaseMatch:
    case_name: str
    triggered: bool
    detail: str
    recommended_actions: list[str] = field(default_factory=list)


@dataclass
class FringeCase:
    """A named failure mode with detection + recommendation logic.

    `detect_fn(observed, session)` returns (triggered: bool, detail: str).
    """
    name: str
    description: str
    detect_fn: Callable[[np.ndarray, Optional[StateSession]], tuple[bool, str]]
    recommended_actions: list[str] = field(default_factory=list)

    def evaluate(self, observed: np.ndarray,
                 session: Optional[StateSession] = None) -> CaseMatch:
        try:
            triggered, detail = self.detect_fn(observed, session)
        except Exception as e:
            triggered, detail = False, f"detection error: {e}"
        return CaseMatch(
            case_name=self.name,
            triggered=triggered,
            detail=detail,
            recommended_actions=list(self.recommended_actions) if triggered else [],
        )


# ===========================================================================
# Detection functions
# ===========================================================================
def _detect_small_state_regression(obs, sess):
    if obs is None or len(obs) == 0:
        return False, "no data"
    peak = float(np.nanmax(obs))
    if peak < 50:
        return True, f"peak observed admissions {peak:.0f} < 50"
    return False, f"peak {peak:.0f} above threshold"


def _detect_mult_ceiling_crowding(obs, sess):
    if sess is None:
        return False, "no session"
    peak = float(np.nanmax(obs)) if obs is not None and len(obs) > 0 else 0
    mult = next((fp for fp in sess.bounds if fp.name == "mult__FREE"), None)
    if mult is None:
        return False, "no mult bound"
    if peak > 0 and peak >= mult.high * 0.8:
        return True, (
            f"peak admissions {peak:.0f} crowds mult upper bound {mult.high:.0f}"
        )
    return False, f"peak {peak:.0f} vs mult upper {mult.high:.0f}"


def _detect_late_season_rebound(obs, sess):
    """Second wave starting after a clear decline (TROUGH→rebound)."""
    if obs is None or len(obs) < 8:
        return False, "need >= 8 weeks of data"
    arr = np.asarray(obs, dtype=float)
    # Look for: an earlier peak followed by a decline by >= 50%, then a
    # recent rise of >= 30% over the last 3 weeks.
    if len(arr) < 8:
        return False, "too short"
    early_peak = float(np.max(arr[: -4]))
    recent_min = float(np.min(arr[-6: -3]))
    last_three = arr[-3:]
    if early_peak <= 0 or recent_min <= 0:
        return False, "non-positive observations"
    declined_pct = (early_peak - recent_min) / early_peak
    recent_growth_pct = (last_three[-1] - last_three[0]) / max(last_three[0], 1.0)
    if declined_pct > 0.5 and recent_growth_pct > 0.3:
        return True, (
            f"early peak {early_peak:.0f} declined {declined_pct:.0%} "
            f"to {recent_min:.0f}; last 3 weeks rebounded "
            f"{recent_growth_pct:.0%}"
        )
    return False, (
        f"declined {declined_pct:.0%} / recent growth {recent_growth_pct:.0%}"
    )


def _detect_data_gap(obs, sess):
    if obs is None:
        return True, "no data array provided"
    arr = np.asarray(obs, dtype=float)
    if len(arr) == 0:
        return True, "empty observation series"
    if np.any(np.isnan(arr)):
        first_nan = int(np.argmax(np.isnan(arr)))
        return True, f"NaN at week {first_nan}"
    return False, f"{len(arr)} contiguous weeks"


def _detect_outlier_week(obs, sess):
    """A single week with extreme deviation from the rolling trend
    suggests a reporting anomaly (data revision, batch upload, etc.).
    Flagging it warns the orchestrator that anchoring on this week
    will propagate noise."""
    if obs is None or len(obs) < 6:
        return False, "need >= 6 weeks of data"
    arr = np.asarray(obs, dtype=float)
    last = float(arr[-1])
    prior_window = arr[-6:-1]
    prior_med = float(np.median(prior_window))
    prior_iqr = float(np.subtract(*np.percentile(prior_window, [75, 25])))
    if prior_med <= 0 or prior_iqr <= 0:
        return False, "prior window non-positive"
    # Outlier if last is more than 4 IQRs from the prior median.
    z = abs(last - prior_med) / prior_iqr
    if z > 4.0:
        return True, (
            f"last week {last:.0f} is {z:.1f}× IQR from prior median "
            f"{prior_med:.0f} — likely reporting anomaly"
        )
    return False, f"z={z:.1f} (threshold 4.0)"


def _detect_holiday_reporting_dip(obs, sess):
    """The CDC respiratory dataset typically shows a reporting dip
    around the weeks of Christmas / New Year (epi weeks 51–53 of the
    prior calendar year). If the last observed week is in that window
    AND values dropped >= 30% from the prior 3-week median, this is
    almost certainly a reporting artifact, not a real outbreak decline."""
    if obs is None or len(obs) < 5 or sess is None:
        return False, "insufficient data or session"
    # Use the session's last_reference_date if available to estimate
    # which epi-week we're in.
    if not getattr(sess, "last_reference_date", None):
        return False, "no reference date"
    try:
        from datetime import date as _date
        import pymmwr as pm
        ref = _date.fromisoformat(sess.last_reference_date)
        ew = pm.date_to_epiweek(ref)
    except Exception:
        return False, "epiweek lookup failed"
    in_holiday = ew.week in (51, 52, 53, 1)
    if not in_holiday:
        return False, f"epi week {ew.week} not in holiday window"
    arr = np.asarray(obs, dtype=float)
    last = float(arr[-1])
    prior_med = float(np.median(arr[-4:-1]))
    if prior_med <= 0:
        return False, "prior window zero"
    drop = (prior_med - last) / prior_med
    if drop >= 0.30:
        return True, (
            f"epi week {ew.week} (holiday window) shows {drop:.0%} drop "
            f"from prior 3-week median {prior_med:.0f} → {last:.0f}; "
            f"likely reporting artifact"
        )
    return False, f"epi week {ew.week} but drop only {drop:.0%}"


def _detect_runaway_K(obs, sess):
    """The piecewise step count keeps growing without commensurate fit
    improvement — a sign that the step-add gate is too liberal for this
    state."""
    if sess is None or len(sess.history) < 4:
        return False, "insufficient history"
    recent = sess.history[-4:]
    step_adds = sum(
        1 for h in recent
        if h.get("bounds_added") and any("b" in s for s in h["bounds_added"])
    )
    if step_adds >= 3:
        return True, f"{step_adds} step additions in last 4 weeks (K runaway)"
    return False, f"{step_adds} recent step additions"


# ===========================================================================
# Registered cases
# ===========================================================================
REGISTERED_CASES: list[FringeCase] = [
    FringeCase(
        name="small_state_regression",
        description=(
            "Small jurisdictions (peak < 50 admissions/wk) regress under "
            "adaptive automation because bounds expansion adds variance "
            "but the noise floor swamps the signal."
        ),
        detect_fn=_detect_small_state_regression,
        recommended_actions=[
            "cap max_K=1 (no piecewise steps)",
            "skip bounds-expansion analysis",
            "consider a fixed per-state slope_blend=0",
        ],
    ),
    FringeCase(
        name="mult_ceiling_crowding",
        description=(
            "High-volume jurisdictions can hit the mult upper bound "
            "(e.g., default 8000) when admissions are large, silently "
            "capping the fit's amplitude."
        ),
        detect_fn=_detect_mult_ceiling_crowding,
        recommended_actions=[
            "expand mult upper bound to >= 5 × peak observed",
            "verify session.bounds for mult__FREE upper >= 5 × peak",
        ],
    ),
    FringeCase(
        name="late_season_rebound",
        description=(
            "Second-wave dynamics after a clear post-peak decline. "
            "The model fit on the declining trajectory will under-predict "
            "the rebound; piecewise step addition is needed."
        ),
        detect_fn=_detect_late_season_rebound,
        recommended_actions=[
            "force add a new piecewise step (b_K, t_K)",
            "use adaptive slope_blend with phase_aware",
        ],
    ),
    FringeCase(
        name="data_gap",
        description=(
            "NaN values mid-series indicate a reporting gap. The fit "
            "should truncate at the first NaN; downstream weeks can't "
            "be forecast until data lands."
        ),
        detect_fn=_detect_data_gap,
        recommended_actions=[
            "truncate observed series at first NaN",
            "wait for next data release",
            "consider state-level back-fill from FluSight target-data",
        ],
    ),
    FringeCase(
        name="outlier_week",
        description=(
            "A single observed week deviates from the prior rolling "
            "window by more than 4 IQRs. Typically a reporting "
            "anomaly (data revision, batch upload) rather than a real "
            "outbreak spike. Anchoring on this week propagates noise "
            "into future forecasts."
        ),
        detect_fn=_detect_outlier_week,
        recommended_actions=[
            "consider trimming the last observation",
            "increase anchor_lookback to dampen the outlier",
            "skip slope_blend this week",
            "log for manual review before submission",
        ],
    ),
    FringeCase(
        name="holiday_reporting_dip",
        description=(
            "Last observation falls in epi-week 51-53 or week 1 AND "
            "shows >= 30% drop vs the prior 3-week median. The CDC "
            "respiratory dataset has well-known reporting dips around "
            "Christmas / New Year; the dip is usually NOT a real "
            "decline in admissions, and the next week typically "
            "rebounds to the trend line."
        ),
        detect_fn=_detect_holiday_reporting_dip,
        recommended_actions=[
            "ignore the dip — use prior-week trend instead",
            "suppress slope_blend this week (avoid extrapolating dip)",
            "consider using a holiday-imputed value for anchoring",
        ],
    ),
    FringeCase(
        name="runaway_K",
        description=(
            "Piecewise step count growing without bound; the step-add "
            "validation gate is being too permissive for this state."
        ),
        detect_fn=_detect_runaway_K,
        recommended_actions=[
            "trigger recommend_remove_step to shrink K",
            "tighten validation gate (e.g., require larger WIS improvement)",
        ],
    ),
]


# ===========================================================================
# Public API
# ===========================================================================
def evaluate_all(
    observed: np.ndarray,
    session: Optional[StateSession] = None,
) -> list[CaseMatch]:
    """Run every registered case against the given observed series + session.
    Returns the matches whose `triggered=True` first, then the rest."""
    matches = [c.evaluate(observed, session) for c in REGISTERED_CASES]
    matches.sort(key=lambda m: (not m.triggered, m.case_name))
    return matches


def triggered_cases(
    observed: np.ndarray,
    session: Optional[StateSession] = None,
) -> list[CaseMatch]:
    """Just the cases that fired."""
    return [m for m in evaluate_all(observed, session) if m.triggered]


def get_case(name: str) -> Optional[FringeCase]:
    for c in REGISTERED_CASES:
        if c.name == name:
            return c
    return None
