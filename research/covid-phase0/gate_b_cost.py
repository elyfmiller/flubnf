"""What Gate B would cost in machine time, from measured constants only.

Gate B, as the memo defines it: twelve-state panel triage, vintage-true,
2025-26, PF + analogue blend against CovidHub-baseline. Pass if the blend beats
the analogue-alone arm by 3% and reaches pooled relWIS <= 0.85.

Every number below is either measured on this machine or recorded from a
previous measurement. Nothing is a guess dressed as an estimate; the two
adjustment factors that ARE estimates are labelled and their basis given.

Run:  .venv/bin/python research/covid-phase0/gate_b_cost.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

OUT = Path(__file__).resolve().parent / "out"

# ---------------------------------------------------------------------------
# MEASURED CONSTANTS
# ---------------------------------------------------------------------------
#: Recorded 2026-08-19 on this machine for the influenza PF retrospective:
#: 0.45 completed fits per minute at chains=2, shard width=6, 10k particles.
#: A "fit" is one (location, replicate) cell for one week.
FLU_PF_FITS_PER_MIN = 0.45
#: Production retrospective settings.
REPLICATES = 3
#: Weeks in a June-boundary COVID season that carry an archived vintage.
WEEKS_IN_SEASON = 45
#: Weeks where the analogue member has >= MIN_DONORS calendar-matched donors
#: under vintage-true rules. Measured by analogue_vintage_true.py: 14 of 45
#: weeks (epiweeks 25-38) have ZERO prior-season donors, because the COVID
#: vintage record starts 2024-11-20.
WEEKS_WITH_ANALOGUE = 31
STATES = 12

# ---------------------------------------------------------------------------
# ADJUSTMENTS. Both are estimates. Both are labelled.
# ---------------------------------------------------------------------------
#: The COVID fit window is longer than the influenza one -- a June-boundary
#: season reaches ~48 observed weeks against influenza's ~40 -- and the ODE is
#: integrated over the whole window for every particle at every step, so cost
#: scales roughly with window length. ESTIMATE, basis: 48/40.
WINDOW_FACTOR = 1.20
#: Six fitted parameters instead of five. The jitter and resample steps are
#: linear in dimension but the ODE solve dominates, so this is a small
#: adjustment. ESTIMATE, basis: judgement, not measurement. Reported separately
#: so it can be removed.
DIMENSION_FACTOR = 1.05


def estimate(states: int = STATES, weeks: int = WEEKS_WITH_ANALOGUE,
             replicates: int = REPLICATES) -> dict:
    cells = states * weeks * replicates
    base_min = cells / FLU_PF_FITS_PER_MIN
    adj_min = base_min * WINDOW_FACTOR * DIMENSION_FACTOR
    return {"states": states, "weeks": weeks, "replicates": replicates,
            "pf_cells": cells,
            "hours_at_flu_rate": round(base_min / 60.0, 1),
            "hours_adjusted": round(adj_min / 60.0, 1),
            "days_adjusted": round(adj_min / 60.0 / 24.0, 2)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    scoped = estimate()
    full_season = estimate(weeks=WEEKS_IN_SEASON)
    half_panel = estimate(states=6)
    res = {
        "definition": ("12 states, vintage-true 2025-26, PF + analogue blend "
                       "vs CovidHub-baseline; pass at relWIS <= 0.85 and "
                       ">= 3% over analogue-alone"),
        "measured_inputs": {
            "flu_pf_fits_per_min": FLU_PF_FITS_PER_MIN,
            "source": "recorded 2026-08-19, chains=2, width=6, 10k particles",
            "weeks_in_june_boundary_season": WEEKS_IN_SEASON,
            "weeks_with_analogue_donors": WEEKS_WITH_ANALOGUE,
            "source_weeks": "research/covid-phase0/analogue_vintage_true.py"},
        "adjustments": {"window_factor": WINDOW_FACTOR,
                        "dimension_factor": DIMENSION_FACTOR,
                        "note": "both are estimates, not measurements"},
        "scenarios": {
            "as_memo_defines_it_31_scorable_weeks": scoped,
            "all_45_weeks_pf_only_where_analogue_is_silent": full_season,
            "six_state_pilot_first": half_panel},
        "wall_clock_caveat": (
            "these are MACHINE hours at the measured throughput, which already "
            "includes the retrospective's own shard parallelism. Wall clock is "
            "longer: a multi-hour run on this host needs the TeamViewer-idle "
            "and macOS-auto-update mitigations, and the Gate A fits here ran at "
            "load average 22 on 12 cores, i.e. oversubscribed. Budget 1.3-1.5x."),
        "what_is_NOT_in_this_estimate": [
            "the analogue arm, which is pure Python and ran the full 45-week "
            "season in under a minute",
            "ensemble weight re-freezing (LOSO), which needs the fits to exist "
            "first but costs only scoring time",
            "any re-fit rounds if Gate A's diagnostics force a parameter change",
            "RW-beta re-testing, which the memo wants at Gate B and which is a "
            "second full panel"],
    }
    (OUT / "gate_b_cost.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
