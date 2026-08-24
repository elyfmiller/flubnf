"""SLOPE-ANCHORED TRANSMISSION MEMBER. PRE-REGISTRATION, frozen before any fit.

Frozen 2026-08-23, before a single influenza or COVID fit of this candidate was
launched, and before the adaptive-transmission arm's verdict was read: the
author deliberately did not open research/adaptive-beta/out/result_armA.json,
so no bar below can have been set against that result. Nothing here was edited
after seeing a number of this candidate's own; the run log and the results JSON
carry the sha256 of this file and of anchor_math.py so the claim is checkable.

Work legitimately done BEFORE freezing and therefore reflected here: the
2026-08-23 R_eff parameter audit was read in full (its measured numbers are the
comparators of gate 2), the ledger's eight member kills were read
(docs/RESULTS.md), and the production filter's source was read to establish that
the anchor needs no change to pybnf (section 6).

=============================================================================
1. WHAT IS BEING TESTED
=============================================================================
Candidate: the production SIHRS particle filter, unchanged in every fitted
respect, whose TRANSMISSION LEVEL AT THE FORECAST ORIGIN is not inferred but
DERIVED from the newest vintage observations, and then held forward while
depletion, waning and the seasonal harmonic evolve the trajectory.

    g       = weekly log-growth of reported admissions over the last k = 2
              vintage-true observations, shrunk to zero (anchor_math)
    R*      = 1 + g / gamma                                    -- equation (3)
    Reff_i <- R* s0 / ( s_i(t0) exp(eps1_i cos(2 pi (t0 - phi1_i)/52)) )

for every particle i, applied ONLY to the copy of theta used for forward
propagation, after the last likelihood evaluation. The full algebra against the
system as implemented is in anchor_math.py's docstring.

FITTED PARAMETERS: 5 -- Reff, eps1, phi1, mult, r. Exactly the production set.
ADDED DIMENSIONS: zero. This is the design constraint, because dimension cost
is what killed most of this ledger's candidates: RW-beta bought flexibility and
paid interval width; the natg arm added a frozen multiplier and was still worse
at the turns it targeted; the completeness arms fitted a year-specific quantity
and could not transfer. Here the likelihood, the priors, the jitter, the
resampling and the rng stream through the origin are byte-identical to
production, which is not an assertion but a mechanical fact of section 6's
construction, and it is CHECKED (section 5b').

WHY IT MIGHT WORK, from this project's own audit (2026-08-23):
  * 42% of the weekly movement of the filter's log R_eff is the filter
    re-estimating transmissibility, against 33% seasonal forcing and 25%
    depletion. The largest single share is an estimate, and an estimate can be
    replaced by a measurement.
  * A two-point growth rule with no model in it beats the filter's own R_eff at
    turns: directional AUC 0.755 against 0.717, and its implied R = 1 crossing
    is within one week of the observed peak 70.1% of the time against 57.7%.
  * eps1 and phi1 fail every identifiability check; phi1 correlates with the
    observed peak week at r = +0.03 to +0.07, so the harmonic is a shape term,
    not a phase. Re-levelling transmission from data does not throw away a
    calendar signal, because the fitted calendar term does not carry one.

WHY IT MIGHT NOT, from the same audit, stated before the fits rather than after:
  * The audit's two-point advantage is a RETROSPECTIVE and DIRECTIONAL result,
    measured week by week over whole seasons. Gate 2 tests forward TIMING from
    origins before the peak, which is a different and harder object.
  * The audit's skill-by-origin table measures relWIS 3.9 / 3.6 / 2.6 at
    h = 1/2/3 for cells whose origin R_eff exceeds 1.2, against 1.24 / 1.08 /
    0.99 in [0.8, 0.95]. A slope anchor taken at takeoff lands in the bad bin
    by construction. The clip box exists for this and is declared in
    anchor_math, not tuned here.
  * Imposing one R* on every particle REMOVES the between-particle spread in
    origin transmission, so the member is a natural width REDUCER. The
    incumbent's central-50 already covers only 0.236 at the Jan-2025 peak
    against a nominal 0.500. Narrowing further makes that worse. Gate 2's
    January clause is therefore a live kill and is registered as one.
  * The measured shrinkage (anchor_math) puts R* near 1 with a spread of about
    0.08 in R_eff units. A near-critical R_eff turns only as fast as depletion
    and the harmonic can pull it down, which is slow. The single most likely
    kill, written down before the run, is gate 2a-i: the member turns LATE.

=============================================================================
2. ARMS AND VARIANTS
=============================================================================
ONE particle-filter run per cell produces every arm below, because the anchor
acts only at the forecast origin (section 6). The forward loops are the only
extra cost, roughly 13% of a cell each.

  P0'  PRODUCTION FORWARD, written by the unmodified parent implementation with
       its own rng consumption, so it is bit-for-bit the sealed production PF
       and doubles as the paired control. No prior member gate had a control
       sharing the candidate's latent state exactly; this one does.
  S1   PRIMARY. Slope anchor, k = 2, harmonic RETAINED forward, V_SIG = 0.075.
  S0h  Reported-only mechanism control. Same anchor, harmonic DISABLED forward
       (eps1 <- 0), so depletion and waning alone turn the trajectory. It
       isolates re-levelling from calendar removal. It CANNOT change the
       verdict on S1.
  S1a / S1b  Reported-only shrinkage sensitivity at V_SIG = 0.04 and 0.145.
       0.145 is not an arbitrary bracket: it is the two-point variance-
       components estimate, i.e. the arm that trusts one-week transients as
       signal (anchor_math.growth_estimate).
  S4   Reported-only robustness arm, k = 4 OLS slope, harmonic retained,
       V_SIG = 0.075. Registered because k = 2 is a variance-heavy estimator;
       never used for selection.

THE SHRINKAGE CONSTANT AND THE REDUNDANCY GATE TRADE OFF, and the trade is
registered here so it cannot be presented later as an insight. Heavier
shrinkage pulls every state's R* toward 1, which makes the member safer at
takeoff AND more like the calendar analogue, whose growth factor carries no
state variation at all. Lighter shrinkage does the reverse. Gate 1a is
therefore reported at all three V_SIG values, and the primary's verdict is
still decided at V_SIG = 0.075 alone.

THE HARMONIC IS RETAINED IN THE PRIMARY, and the reason is registered here so
it cannot be re-argued after a result. Three grounds. (i) RW-beta set eps1 = 0
and was killed; repeating the one calendar decision that has already failed in
this project would confound the new idea with an old one. (ii) The member's
claim is about the LEVEL of transmission, not its calendar shape; disabling the
harmonic changes two things at once and makes the outcome uninterpretable.
(iii) The harmonic supplies 33% of the downward pressure on log R_eff against
depletion's 25%, so removing it biases the member toward turning LATE -- it
would fail gate 2 for a reason that has nothing to do with anchoring. S0h
measures exactly that bias and is reported beside the primary.

NO HYPERPARAMETER IS SELECTED ON ANY SEASON. Every constant in anchor_math.py
is derived from the audit or from the sealed reference fits, both of which
predate this file; none is a forecast score.

PANEL: the 6-state shape-diverse panel every prior member gate used -- Alaska,
California, New York, Pennsylvania, Vermont, Wyoming -- x 3 seasons x all 85
sealed as-of dates x 3 replicates = 1,530 fits, 10k particles, jitter 0.30,
integrated observable, derive_seed(state, asof, rep). Identical to the
adaptive-transmission arm's panel so the two members are directly comparable.
PANEL IS TRIAGE, NOT A SEAT: 6-state results have twice failed to transfer to
52 (RW-beta gates, two-strain gate 2). A pass licenses a full-grid run, nothing
more.

=============================================================================
3. THE INFLUENZA GATES, IN THIS ORDER
=============================================================================
Everything is computed on cells where EVERY member exists, truth > 0, the
member's median > 0, and the seal's per-cell baseline is defined -- the frozen
score_season rule. Members are quantile-averaged (vincentized) at EQUAL
weights. No weight is fitted anywhere, because LOSO weighting has anti-predicted
the held season three times.

-----------------------------------------------------------------------------
GATE 1 -- REDUNDANCY. A GATE, NOT A FOOTNOTE, AND COMPUTED FIRST.
-----------------------------------------------------------------------------
A member that reproduces an incumbent adds nothing to an equal-weight blend
however well it scores alone, so this is decided before any skill number
exists.

THE MEASUREMENT MUST NOT BE ON LEVELS. Every member in this ensemble is
anchored to the same last observation -- the analogue multiplies it by donor
ratios, and app/core/engines/pf.collect rescales the filter's origin median
onto it -- so any two members' medians correlate at ~0.999 through the anchor
alone and a correlation of medians measures nothing. The comparison is
therefore on the GROWTH FACTOR:

    G(cell, h) = log( q50_h / y_origin )

  1a GROWTH REDUNDANCY. Pearson r of G between the member and each incumbent
     (analogue, production pf), per horizon and pooled over horizons, on
     identical cells. KILL if the pooled r against EITHER incumbent is
     >= R_GROWTH_KILL = 0.90.
  1b ERROR REDUNDANCY. Pearson r of log(WIS + 1) per cell against each
     incumbent, pooled. KILL if >= R_WIS_KILL = 0.85 against either.
  Both are also computed BETWEEN the two incumbents (r(pf, analogue)) and
  reported beside the member's, so the bars are read against the pair the
  project already treats as complementary.

REGISTERED EXPECTATION, so the result cannot be narrated afterwards: the
analogue clause is unlikely to fire, for a structural reason. donor_ratios()
pools donors across states and does not condition on the target state at all,
so the analogue's growth factor is CONSTANT across states within an (as-of,
horizon) block, while a slope anchor's varies entirely within it. The clause
with teeth is the one against the PRODUCTION FILTER, which shares this member's
latent state and differs only in the forward transmission level. The tasking
named the analogue; both are gated, and the verdict names which fired.

  1c INCREMENTAL VALUE, reported, not gated: the equal-thirds relWIS against
     the 2-member blend that drops whichever incumbent the member most
     resembles. Not a gate because choosing which member to drop is a
     weighting decision and fitted weighting is barred here.

-----------------------------------------------------------------------------
GATE 2 -- THE TURN. THE SCIENTIFIC POINT.
-----------------------------------------------------------------------------
At a peak the recent slope is positive while the truth turns, so this member
lives or dies on whether susceptible depletion (plus waning and the retained
harmonic) turns the trajectory at the right time. Two clauses, both required.

  2a IMPLIED-TURN TIMING, paired against production on identical cells.
     Each cell's origin cloud (theta, weights, S, I, model clock) is propagated
     30 weeks by the audit's own RK4 skeleton (anchor_math.propagate, mirrored
     byte-for-byte from context/reff/implied_peak.py) under (i) the production
     parameters and (ii) the anchored parameters. The particle-weighted median
     argmax week is the implied peak week; pw_err = implied - observed, where
     observed is the centred-3-week-smoothed settled-truth peak week
     (peak_week_sm, the audit's definition). Restricted to origins STRICTLY
     BEFORE the observed peak, which is the only case in which the statement is
     a forecast.
       2a-i  LATE-TURN KILL. median over paired cells of
             (member pw_err - production pw_err) must be <= LATE_TURN_BAR
             = +1.0 week. The member may not turn later than the incumbent by
             more than one week on average. This is the pre-registered failure
             mode written as a bar.
       2a-ii ACCURACY FLOOR. member fraction |pw_err| <= 2 weeks must be
             >= TURN_ACC_RATIO = 0.90 times production's on the same cells.
     The audit's full-grid production figures -- median pw_err -1.00 wk, IQR
     [-4, +1], |err| <= 1 in 37.8%, |err| <= 2 in 58.4%, 95% interval covers
     the true peak week 97.0% -- are the pre-registered context and are printed
     beside the recomputed panel values. If the recomputation disagrees, the
     RECOMPUTED production value is the comparator.

  2b COVERAGE AT THE TWO TURNS, BOTH DIRECTIONS, on the 3-member equal-weight
     ensemble. The incumbent's defect is two-sided -- central-50 covers 0.236
     at the Jan-2025 peak (too narrow) and 0.743 at the Feb-2024 plateau (too
     wide) against a nominal 0.500 -- so a candidate that moves width one way
     everywhere is not a fix. Bars are the adaptive-transmission arm's, copied
     unchanged so the two members are comparable:
             January 2025 cov50 > 0.35   AND   February 2024 cov50 < 0.78.
     Windows are as-of months 2025-01 and 2024-02, the turn cells every prior
     gate used. Both numbers are reported whatever happens, with the incumbent
     2-member recomputed on the identical paired cells. Reported beside them,
     not gated: the MEMBER's own cov50 and cov95 in both windows and the
     over/under split (fraction of turn cells with y above q97.5 and below
     q2.5), which is what says whether a coverage miss is a placement failure
     or a width failure.

  KILL if 2a-i fails, or 2a-ii fails, or either direction of 2b fails.

-----------------------------------------------------------------------------
GATE 3 -- SKILL AND WIDTH, mirroring the adaptive-transmission gates
-----------------------------------------------------------------------------
  3a WIDTH PRE-SCREEN, computed and printed BEFORE any relWIS. Equal-weight
     quantile averaging makes the ensemble's width the arithmetic mean of
     member widths, so this is decisive arithmetic and it is free. Reported for
     the member against production PF on identical cells: mean interval width
     at the 50, 80 and 95 levels with empirical coverage beside each, plus
     width at MATCHED coverage. Reported first in the results JSON so it can
     never be reported selectively afterwards. Not itself a kill -- gate 2b
     carries the coverage consequence -- but a matched-coverage ratio above 1
     is stated as such in the verdict line.
  3b THE ENSEMBLE MUST IMPROVE. The 3-member equal-weight ensemble (production
     PF, analogue, slope-anchored) must beat the 2-member 50/50 on identical
     panel cells, pooled over the selection seasons 2023-24 + 2024-25 -- the
     gate RW-beta failed at 0.664 against 0.620 and two-strain failed at full
     grid at 0.7189 against 0.7039. 2025-26 is reported as the held-out
     confirmation. PASS = pooled selection-season relWIS of the 3-member below
     that of the 2-member on the same cells.
  3c MEMBER FLOOR. The member's OWN relWIS must stay below MEMBER_FLOOR = 1.1
     in EVERY season.

KILL RULES (any one kills the member for influenza):
  * gate 1a or 1b fires against either incumbent;
  * gate 2a-i, 2a-ii, or either direction of 2b fails;
  * gate 3b fails;
  * gate 3c fails in any season.

ALSO REPORTED, NOT GATED: per-horizon relWIS (a gain confined to h = 1 is a
nowcast result, not a seat); the distribution of R* and of the filter's own
origin R_eff side by side; the fraction of origins clipped at each bound of the
R* box and the distribution of the shrinkage weight w; the anchor-scale guard's
counts; CVODE and filter failure counts; the S0h, S1a, S1b and S4 variants.

PERSISTENCE CLAUSE (reported, changes the reading, not the verdict). Three
numbers say what the member actually is, and all three are printed in the
verdict block whatever the gates did:
  * the fraction of origins clipping at either bound of the R* box. Registered
    expectation: near zero. After shrinkage sd(g_hat) is about 0.17, so a clip
    needs a 3.8-sigma cell; the box is a rail against pathology, and an inert
    rail is the correct outcome, not a null result.
  * the median shrinkage weight w. Registered expectation: 0.36 to 0.42.
  * SPREAD_RATIO = sd(R*) / sd(R_eff of the production filter at the same
    origins), equation (1) at the posterior-weighted median. Registered
    expectation: well below 1, because a shrinkage estimator is by construction
    less variable than the thing it estimates. If SPREAD_RATIO < 0.25 the
    verdict line reads "shrunken-persistence forecaster, not a slope-anchored
    one". That is a statement about what was tested, not a failure: this
    project's measured point-forecast ceiling IS persistence, so a
    persistence-median member carrying the filter's uncertainty structure is a
    coherent thing to have tested -- but the write-up must not then claim that
    deriving transmission from slope was what was measured.

=============================================================================
4. THE COVID ARM (cheap, and second) -- research/slope-anchored/covid_gate.py
=============================================================================
Same construction on the COVID profile: flubnf/profiles.py COVID, 3 states
(New York, Pennsylvania, North Carolina) x 3 origins (2026-01-07, 2026-02-04,
2026-03-04) x 3 seeded replicates = 27 fits at production settings (10k
particles, jitter 0.30, integrated observable), season start 2025-06-01,
reporting-break-excluded cells. The production forward written by the same run
is the paired control, so no separate control run is needed.

A BIMODALITY GATE IS THE WRONG INSTRUMENT HERE, AND THE CLAUSE IS DECLARED VOID
RATHER THAN PASSED. Round two's estimator asks whether the fitted model has a
limit cycle, by integrating the deterministic skeleton for ten years. For a
member whose forward transmission is a deterministic function of the last two
DATA points, that skeleton is the production skeleton with one constant
re-levelled: it returns 1.00 peaks per year by construction, and there is no
stochastic process to run a generative estimator on. Reporting 1.00 would be
reporting the estimator, not the member. The clause is therefore recorded as
VOID with this reason attached, so its absence can never later be read as a
pass. What replaces it:

  C1 TURN RESPONSIVENESS (replaces bimodality; the thing anchoring is for).
     On break-excluded cells, the sign agreement between (R* - 1) and the
     realized 4-week log change of settled admissions, paired against the same
     statistic for the production filter's origin R_eff (equation (1) at the
     posterior-weighted median). BAR: the member's directional accuracy must be
     >= the control's on identical cells; a paired sign test's p-value is
     reported beside it but the bar is the point estimate, one-sided. This is
     the COVID form of the flu audit's directional result, and it is the only
     honest question 27 fits can answer about a turn.
  C2 WIDTH. Central-95 width relative to actual <= WIDTH_BAR = 4.06 with
     coverage reported beside it, at production settings, on break-excluded
     cells, reported both absolutely and as a ratio to the paired control. The
     standing COVID number of record is the production filter's 1.689 at 100%
     coverage; a member that narrows it must not narrow it into a coverage
     collapse, so the verdict states both.
  C3 ANCHOR VALIDITY (replaces "the innovation scale is identified"). The
     fraction of COVID origins clipping at either bound of the R* box, the
     median shrinkage weight, and SPREAD_RATIO against the COVID control's
     origin R_eff. BAR: clipping < CLIP_REPORT_FRAC = 0.40 AND median
     w >= COVID_W_BAR = 0.20. Below either, the arm is labelled "anchored to
     persistence on COVID" and C1 is reported as uninformative rather than
     passed. NOTE that COVID's gamma is roughly half influenza's (7/6.84 per
     week against 7/3.2, Manica 2022 intrinsic generation time), so R* =
     1 + g/gamma swings about twice as far per unit of g there; the same clip
     box is therefore a tighter rail on COVID and its firing rate is reported
     separately rather than pooled with influenza's.
  KILL for COVID: C1 fails, C2 fails, or C3 fails.

COVID CARRIES NO SKILL CLAIM. relWIS against CovidHub-baseline is a Gate B
question and 27 fits at three origins cannot settle it.

=============================================================================
5. SCORING DISCIPLINE (the house rules, applied)
=============================================================================
(a) An inline, independent Bracher et al. 2021 WIS must agree with
    flubnf.wis.wis on EVERY scored cell (max relative difference < 1e-9) before
    any table is produced.
(b) The pooling -> quantiles -> WIS path applied to the seal's STORED pf
    samples must reproduce the seal's stored per-cell WIS (< 1e-6), and
    likewise the stored analogue quantiles.
(b') NEW, AND ONLY THIS MEMBER CAN MAKE IT: because the assimilation phase is
    the production filter unmodified, THIS RUN's OWN production forward must
    also reproduce the seal's stored pf per-cell WIS to < 1e-6. Every previous
    member gate ran a different template and could only compare against stored
    samples. If (b') fails, the run stops: it means the anchoring construction
    perturbed something upstream of the origin, which would invalidate the
    zero-added-dimension claim itself.
(c) Truth is settled truth via load_truth(); the per-cell baseline is the
    seal's own base_wis, one number per cell shared by every model.
(d) Vintage-true fitting throughout: each as-of date reads vintage_path(asof),
    and the anchor's g is computed from the SAME StateSetup that writes the
    .exp, so the two cannot diverge.
(e) ANCHOR-SCALE GUARD, earned by the COVID autopsy (2026-08-23), which found a
    collapsed cloud driving the collection-time scale to 95.3 and the rescaled
    median to zero at h = 3-4. At collection, per replicate,
    scale = last_observed / median(origin): outside [1/3, 3] the cell is
    FLAGGED and counted; outside [1/10, 10] the replicate is DROPPED with its
    reason recorded. Drops remove the cell from the identical-cells
    intersection for EVERY member, so no member can benefit from a drop.
(f) The known model-clock defect (the model clock leads the data clock by one
    week in every fit) is inherited identically by the member and its paired
    control, because both evaluate the harmonic at the model's own t and both
    read the same species state; it therefore cancels in the pairing. Reported,
    not corrected.

=============================================================================
6. IMPLEMENTATION: WHY NOTHING IN pybnf IS TOUCHED
=============================================================================
ParticleFilter._write_outputs is the exact seam. It runs once per replicate,
AFTER the last likelihood evaluation, and it already does the two things the
anchor needs: it resamples the cloud to equal weights and it propagates a COPY
of theta forward with transmission frozen. The member is a SUBCLASS that

    def _write_outputs(self, cloud, mu_hist, repl, rng):
        super()._write_outputs(cloud, mu_hist, repl, rng)   # P0', bit-identical
        ... anchored forward loops, on their own rng stream ...

defined inside the generated runner. Consequences, all of them load-bearing:
  * pybnf/pf.py is not edited, so this candidate cannot disturb the
    adaptive-transmission experiment running against the same worktree;
  * the production forward keeps the parent's rng consumption exactly, which is
    what makes check (b') possible;
  * the anchored variants share ONE resample draw (a separate deterministic
    stream, seed + 3000 + repl) so variant-to-variant comparisons carry no
    extra Monte Carlo noise; the only difference from the control's draw is one
    systematic resample out of 10,000 particles, and that is stated rather than
    hidden;
  * the per-cell anchor inputs travel in a side file (anchor.json), not in the
    conf, so the conf handed to load_config is EXACTLY the production conf and
    no unknown key can change parsing.
The species indices of S, I and the model clock are read from the generated
m.net and asserted at prepare time; a template whose species order changed
fails loudly rather than anchoring on the wrong compartment.

=============================================================================
7. WHAT THIS CANNOT SETTLE
=============================================================================
Six states, three seasons, one panel. A pass licenses a full-grid run and
nothing else. The COVID arm is 27 fits at three origins in one season and
carries no skill claim.

=============================================================================
USAGE
=============================================================================
    .venv/bin/python research/slope-anchored/gate.py --smoke
    .venv/bin/python research/slope-anchored/gate.py --run [--shards 4]
    .venv/bin/python research/slope-anchored/score.py
    .venv/bin/python research/slope-anchored/covid_gate.py
Results land in research/slope-anchored/out/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from app.core.data import LOCATIONS, vintage_path            # noqa: E402
from app.core.runs import derive_seed                        # noqa: E402
from flubnf.settings import BNG, PY_ENGINE, PYBNF            # noqa: E402
from flubnf.sihrs_fit import (materialize_model,             # noqa: E402
                              resolve_state, write_exp)

import anchor_math as AM                                     # noqa: E402

OUT = HERE / "out"
WORK = Path(os.environ.get(
    "SLOPEANCHOR_WORK",
    "/private/tmp/claude-1786722491/-Users-l-biosci-posnerlab-Documents-GitHub"
    "-NAU-Projects-NAU-Influenza-M-Model/ab76ceee-c2c4-485d-b683-7b08e1248f4e"
    "/scratchpad/slopeanchor"))
SEAL = REPO / "app/state/retro_seal"
TEMPLATE = REPO / "flubnf/templates/SIHRS_pop_min.bngl"   # PRODUCTION, unchanged

STATES = ["Alaska", "California", "New York", "Pennsylvania", "Vermont",
          "Wyoming"]
SEASONS = ["2023-24", "2024-25", "2025-26"]
SELECT_SEASONS = ["2023-24", "2024-25"]
PARTICLES = 10_000
REPLICATES = 3
JITTER = 0.30

# --- the member, frozen a priori ------------------------------------------
K_PRIMARY = 2                 # the audit's two-point rule
K_ROBUST = 4                  # reported-only robustness arm
V_SIG = AM.V_SIG              # 0.075, measured (see anchor_math)
V_SIG_SENS = (0.04, 0.145)    # reported-only shrinkage sensitivity
R_DISP = AM.R_DISP            # 20.0
R_STAR_LO, R_STAR_HI = AM.R_STAR_LO, AM.R_STAR_HI      # 0.70, 1.30
MAX_GAP_WEEKS = AM.MAX_GAP_WEEKS

# name -> (k, harmonic_retained, v_sig).  "prod" is written by the parent.
VARIANTS = {
    "S1":  (K_PRIMARY, True,  V_SIG),           # PRIMARY
    "S0h": (K_PRIMARY, False, V_SIG),           # mechanism control
    "S1a": (K_PRIMARY, True,  V_SIG_SENS[0]),   # shrinkage sensitivity
    "S1b": (K_PRIMARY, True,  V_SIG_SENS[1]),   # shrinkage sensitivity
    "S4":  (K_ROBUST,  True,  V_SIG),           # robustness arm
}
PRIMARY = "S1"

# --- gate constants, frozen ------------------------------------------------
R_GROWTH_KILL = 0.90          # gate 1a, against EITHER incumbent
R_WIS_KILL = 0.85             # gate 1b, against EITHER incumbent
LATE_TURN_BAR = 1.0           # gate 2a-i, weeks, paired median, PASS at or below
TURN_ACC_RATIO = 0.90         # gate 2a-ii, fraction of production's |err|<=2
TURN_HORIZON_WEEKS = 30       # skeleton propagation length, the audit's value
JAN_PEAK_MONTHS = ["2025-01"]
FEB_PLATEAU_MONTHS = ["2024-02"]
TURN_MONTHS = ["2024-02", "2025-01"]
JAN_COV50_BAR = 0.35          # PASS strictly above   (adaptive-beta's bar)
FEB_COV50_BAR = 0.78          # PASS strictly below   (adaptive-beta's bar)
MEMBER_FLOOR = 1.1            # gate 3c
CLIP_REPORT_FRAC = 0.40       # persistence clause / COVID C3
SPREAD_RATIO_LABEL = 0.25     # persistence clause, reported label only
COVID_W_BAR = 0.20            # COVID C3
WIDTH_BAR = 4.06              # COVID C2, the standing bar
ANCHOR_SCALE_FLAG = 3.0       # (e) flag outside [1/3, 3]
ANCHOR_SCALE_DROP = 10.0      # (e) drop outside [1/10, 10]

# The audit's measured production comparators (context/reff, 2026-08-23),
# recorded so the recomputation can be checked against them.
AUDIT_PF_PWERR_MEDIAN = -1.00
AUDIT_PF_PWERR_ABS2 = 0.584
INCUMBENT_JAN_COV50 = 0.236
INCUMBENT_FEB_COV50 = 0.743

DEFAULTS_BLOCK = ("begin parameters\nReff__FREE 1.20\neps1__FREE 0.15\n"
                  "phi1__FREE 22.0\nmult__FREE 0.05\nr__FREE 8.0\n")
VARS_1S = """uniform_var = Reff__FREE 0.6 2.5
uniform_var = eps1__FREE 0.0 1.0
uniform_var = phi1__FREE 0.0 52.0
loguniform_var = mult__FREE 0.002 1.0
loguniform_var = r__FREE 0.1 40.0
"""

SPECIES_ORDER = ("S", "I", "H", "R", "Hadm", "counter")


def preregistration_hash() -> str:
    """sha256 over gate.py AND anchor_math.py -- the formulas are in the
    second file, so hashing this one alone would not freeze them."""
    h = hashlib.sha256()
    h.update(Path(__file__).read_bytes())
    h.update((HERE / "anchor_math.py").read_bytes())
    return h.hexdigest()[:16]


def season_start(season: str) -> str:
    return f"{season[:4]}-08-01"


def season_asofs(season: str) -> list:
    return sorted(p.name for p in (SEAL / season / "weeks").iterdir()
                  if p.is_dir())


def species_index_map(net_path: Path) -> dict:
    """Species order from the generated .net, asserted against the template.

    The anchor divides by S and reads the model clock; anchoring on the wrong
    column would be silent and catastrophic, so this fails loudly instead.
    """
    txt = net_path.read_text()
    m = re.search(r"begin species\n(.*?)\nend species", txt, re.S)
    if not m:
        raise RuntimeError(f"no species block in {net_path}")
    names = []
    for line in m.group(1).splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            names.append(parts[1].split("(")[0])
    if tuple(names) != SPECIES_ORDER:
        raise RuntimeError(f"species order changed: {names} != "
                           f"{list(SPECIES_ORDER)} -- the anchor would read "
                           f"the wrong compartment")
    return {n: i for i, n in enumerate(names)}


# ---------------------------------------------------------------------------
# cell preparation
# ---------------------------------------------------------------------------

def prepare_cell(d: Path, loc: str, asof: str, season: str, rep: int) -> dict:
    """Materialize the PRODUCTION model + net + exp + conf, plus anchor.json.

    Nothing about the model or the conf differs from production. The anchor
    lives entirely in the side file.
    """
    d.mkdir(parents=True, exist_ok=True)
    s = resolve_state(loc, truth_csv=vintage_path(asof), locations_csv=LOCATIONS,
                      season_start=season_start(season), as_of=asof)
    sfx = f"{loc.replace(' ', '_')}_flu"
    m = materialize_model(s, TEMPLATE, d / "m.bngl", sfx)
    m.write_text(m.read_text().replace("begin parameters\n", DEFAULTS_BLOCK, 1))
    write_exp(s, d / f"{sfx}.exp")
    r = None
    for _ in range(2):                      # netgen occasionally needs a retry
        r = subprocess.run(["perl", str(BNG), "m.bngl"], capture_output=True,
                           text=True, cwd=str(d), timeout=600)
        if (d / "m.net").is_file():
            break
        time.sleep(1.0)
    if not (d / "m.net").is_file():
        raise RuntimeError(f"netgen failed for {loc} {asof}: {r.stdout[-400:]}")
    sidx = species_index_map(d / "m.net")

    # --- the anchor, computed from the SAME StateSetup that wrote the .exp --
    variants = {}
    for name, (k, harmonic, v_sig) in VARIANTS.items():
        ge = AM.growth_estimate(s.observed, s.times, k=k, v_sig=v_sig,
                                r_disp=R_DISP, max_gap=MAX_GAP_WEEKS)
        rs = AM.r_star(ge["g_hat"], s.gamma)
        variants[name] = {**ge, **rs, "harmonic": bool(harmonic),
                          "v_sig": float(v_sig)}
    anchor = {"variants": variants, "gamma": float(s.gamma),
              "s0": float(s.s0), "N": float(s.population), "rho": float(s.rho),
              "gammaH": float(s.gammaH), "omega": float(s.omega),
              "idx_S": int(sidx["S"]), "idx_I": int(sidx["I"]),
              "idx_t": int(sidx["counter"])}
    (d / "anchor.json").write_text(json.dumps(anchor))

    seed = derive_seed(loc, asof, rep)
    (d / "pf.conf").write_text(f"""bng_command = {BNG}
model = {d}/m.bngl : {d}/{sfx}.exp
output_dir = {d}/out
fit_type = pf
objfunc = neg_bin_dynamic
num_particles = {PARTICLES}
pf_jitter = {JITTER}
pf_observable_mode = integrated
pf_forecast_weeks = 4
population_size = 1
max_iterations = 1
seed = {seed}
{VARS_1S}""")
    return {"key": f"{loc.replace(' ', '_')}_r{rep}", "dir": str(d),
            "location": loc, "replicate": rep, "seed": seed, "season": season,
            "asof": asof, "n_obs": int(s.n_obs),
            "last_week_offset": int(s.last_week_offset),
            "last_observed": float(s.observed[-1]),
            "gamma": float(s.gamma), "s0": float(s.s0),
            "N": float(s.population), "rho": float(s.rho),
            "gammaH": float(s.gammaH), "omega": float(s.omega)}


def _prep_one(job):
    d, loc, asof, season, rep = job
    d = Path(d)
    if (d / "meta.json").is_file() and (d / "pf.conf").is_file() and \
            (d / "m.net").is_file() and (d / "anchor.json").is_file():
        return json.loads((d / "meta.json").read_text())
    meta = prepare_cell(d, loc, asof, season, rep)
    (d / "meta.json").write_text(json.dumps(meta))
    return meta


def build_cells(workers: int = 4) -> list:
    """Every cell, in a stable order. Idempotent: an already materialized
    directory is reused, so a resumed run re-prepares nothing."""
    from concurrent.futures import ProcessPoolExecutor
    jobs = []
    for season in SEASONS:
        for asof in season_asofs(season):
            for loc in STATES:
                for rep in range(REPLICATES):
                    d = (WORK / season / asof /
                         f"{loc.replace(' ', '_')}_r{rep}")
                    jobs.append((str(d), loc, asof, season, rep))
    with ProcessPoolExecutor(max_workers=workers) as ex:
        cells = list(ex.map(_prep_one, jobs, chunksize=8))
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "cells.json").write_text(json.dumps(cells))
    return cells


# ---------------------------------------------------------------------------
# execution: sharded, nice'd, resumable, compacted per cell
# ---------------------------------------------------------------------------

_RUNNER = '''"""Auto-generated slope-anchored runner (shard {shard}).

The member is a SUBCLASS of the production ParticleFilter. pybnf is not
modified: super()._write_outputs writes the production forecast with the
parent's own rng consumption (so it stays bit-for-bit the sealed member), and
the anchored variants are propagated afterwards on a separate deterministic
stream. See gate.py section 6.
"""
import json, os, shutil, sys, time
sys.path.insert(0, {pybnf!r})
sys.path.insert(0, {here!r})
from pathlib import Path
import numpy as np
import anchor_math as AM

cells = json.load(open({cells!r}))
out_json = {out!r}
res = {{}}
t0 = time.time()


def make_class():
    from pybnf.pf import ParticleFilter, systematic_resample

    class SlopeAnchoredPF(ParticleFilter):
        anchor = None

        def _write_outputs(self, cloud, mu_hist, repl, rng):
            # 1. the production forward, untouched and bit-identical
            super()._write_outputs(cloud, mu_hist, repl, rng)
            a = self.anchor
            runs = Path(self.out_dir) / 'Results' / 'A_MCMC' / 'Runs'
            base = int(self.config.config.get('seed') or 0)
            r2 = np.random.default_rng(base + 3000 + repl)
            idx = systematic_resample(cloud.weights, r2)
            theta = cloud.theta[idx]
            species = cloud.species[idx]
            names = list(self.names)
            N = float(a['N'])
            s_frac = species[:, int(a['idx_S'])] / N
            t_mod = species[:, int(a['idx_t'])]
            t0m = float(cloud.t_last)
            # origin cloud for the turn gate (equal-weight draws)
            np.savez_compressed(
                runs / ('cloud_%d.npz' % repl),
                theta=theta.astype(np.float32),
                pnames=np.array(names),
                S=species[:, int(a['idx_S'])].astype(np.float32),
                I=species[:, int(a['idx_I'])].astype(np.float32),
                t=t_mod.astype(np.float32))
            dt = (float(np.median(np.diff(self.times)))
                  if len(self.times) > 1 else 1.0)
            cols0 = [m[idx] for m in mu_hist]
            diag = {{'t_last': t0m, 's_frac_med': float(np.median(s_frac))}}
            # a FIXED index per variant name: str.__hash__ is randomised per
            # process unless PYTHONHASHSEED is set, so hashing the name here
            # would silently break run-to-run reproducibility.
            vorder = sorted(a['variants'])
            for vname, spec in a['variants'].items():
                th = AM.apply_anchor(theta, names, float(spec['r_star']),
                                     s_frac, float(a['s0']), t0m,
                                     bool(spec['harmonic']))
                th_i = [dict(zip(names, th[j])) for j in range(th.shape[0])]
                sp = species.copy()
                cols = list(cols0)
                rv = np.random.default_rng(base + 4000 + 17 * repl
                                           + 101 * vorder.index(vname))
                t = t0m
                for _ in range(self.forecast):
                    mu = np.empty(sp.shape[0])
                    for j in range(sp.shape[0]):
                        sp[j], seg = self.model.simulate_segment(
                            sp[j], th_i[j], t, t + dt)
                        mu[j] = self._mu_from_segment(seg, 0, th_i[j])
                    t += dt
                    r = np.array([max(d.get('r__FREE', 10.0), 1e-3)
                                  for d in th_i])
                    cols.append(rv.negative_binomial(
                        r, r / (r + np.maximum(mu, 1e-9))).astype(float))
                np.savetxt(runs / ('traj_slope_%s_chain_%d.txt'
                                   % (vname, repl)), np.column_stack(cols))
                diag[vname] = {{'reff_anchored_med': float(np.median(
                    th[:, names.index('Reff__FREE')]))}}
            (runs / ('anchor_diag_%d.json' % repl)).write_text(
                json.dumps(diag))

    return SlopeAnchoredPF


for i, c in enumerate(cells, 1):
    d = Path(c["dir"])
    if (d / "compact.npz").is_file():
        res[c["key"] + "|" + c["asof"]] = "cached"
        continue
    shutil.rmtree(d / "out", ignore_errors=True)
    (d / "out" / "Results").mkdir(parents=True)
    cwd = os.getcwd(); os.chdir(d)
    try:
        from pybnf.parse import load_config
        cls = make_class()
        alg = cls(load_config(str(d / "pf.conf")))
        alg.anchor = json.load(open(d / "anchor.json"))
        alg.run(None)
        runs = d / "out" / "Results" / "A_MCMC" / "Runs"
        n = int(c["n_obs"])
        store = {{}}
        tr = sorted(runs.glob("*traj_noise*"))
        store["traj_prod"] = np.genfromtxt(tr[0])[:, n - 1:n + 4].astype(
            np.float32)
        for f in sorted(runs.glob("traj_slope_*_chain_*.txt")):
            vname = f.name.split("traj_slope_")[1].rsplit("_chain_", 1)[0]
            store["traj_" + vname] = np.genfromtxt(f)[:, n - 1:n + 4].astype(
                np.float32)
        pf_ = sorted(runs.glob("params_*"))
        store["pnames"] = np.array(open(pf_[0]).readline().split())
        store["params"] = np.genfromtxt(pf_[0], skip_header=1).astype(
            np.float32)
        cz = np.load(runs / "cloud_0.npz", allow_pickle=False)
        for kk in ("theta", "S", "I", "t"):
            store["cloud_" + kk] = cz[kk]
        store["cloud_pnames"] = cz["pnames"]
        np.savez_compressed(d / "compact.npz", **store)
        shutil.copy(runs / "anchor_diag_0.json", d / "anchor_diag.json")
        res[c["key"] + "|" + c["asof"]] = "ok"
    except Exception as e:
        res[c["key"] + "|" + c["asof"]] = ("FAIL: %s" % e)[:300]
    finally:
        os.chdir(cwd)
        shutil.rmtree(d / "out", ignore_errors=True)
    if i % 5 == 0 or i == len(cells):
        json.dump({{"done": i, "total": len(cells), "t0": t0,
                   "now": time.time()}}, open(out_json + ".prog", "w"))
        json.dump(res, open(out_json, "w"))
json.dump(res, open(out_json, "w"))
json.dump({{"done": len(cells), "total": len(cells), "t0": t0,
           "now": time.time()}}, open(out_json + ".prog", "w"))
'''


def execute(shards: int = 4, nice_level: int = 12) -> list:
    cells = json.loads((WORK / "cells.json").read_text())
    pending = [c for c in cells
               if not (Path(c["dir"]) / "compact.npz").is_file()]
    print(f"{len(cells)} cells, {len(pending)} pending", flush=True)
    if not pending:
        return []
    procs = []
    for sh in range(shards):
        mine = pending[sh::shards]
        if not mine:
            continue
        cj = WORK / f"shard_{sh}.json"
        cj.write_text(json.dumps(mine))
        rp = WORK / f"runner_{sh}.py"
        rp.write_text(_RUNNER.format(shard=sh, pybnf=str(PYBNF),
                                     here=str(HERE), cells=str(cj),
                                     out=str(WORK / f"status_{sh}.json")))
        p = subprocess.Popen(["nice", "-n", str(nice_level), str(PY_ENGINE),
                              str(rp)],
                             stdout=subprocess.DEVNULL,
                             stderr=open(WORK / f"shard_{sh}.err", "w"))
        procs.append(p)
        print(f"  shard {sh}: {len(mine)} cells, pid {p.pid}", flush=True)
    return procs


# ---------------------------------------------------------------------------
# collection: the seal's own path, plus the anchor-scale guard (5e)
# ---------------------------------------------------------------------------

def collect(season: str, asof: str, variant: str) -> tuple:
    """(location -> {h: [samples]}, guard counts).

    `variant` is "prod" for the paired production forward or a VARIANTS key.
    Replicate-pooled after a per-replicate origin rescale, equivalent in method
    to app/core/engines/pf.collect, with the anchor-scale guard applied.
    """
    root = WORK / season / asof
    key = "traj_prod" if variant == "prod" else f"traj_{variant}"
    by_loc, flagged, dropped = {}, 0, 0
    for loc in STATES:
        for rep in range(REPLICATES):
            d = root / f"{loc.replace(' ', '_')}_r{rep}"
            f = d / "compact.npz"
            if not f.is_file():
                continue
            meta = json.loads((d / "meta.json").read_text())
            z = np.load(f, allow_pickle=False)
            if key not in z.files:
                continue
            tr = z[key].astype(float)
            origin = tr[:, 0]
            med = float(np.median(origin[np.isfinite(origin)]))
            scale = meta["last_observed"] / med if med > 0 else 1.0
            if not (1.0 / ANCHOR_SCALE_DROP <= scale <= ANCHOR_SCALE_DROP):
                dropped += 1
                continue
            if not (1.0 / ANCHOR_SCALE_FLAG <= scale <= ANCHOR_SCALE_FLAG):
                flagged += 1
            dd = by_loc.setdefault(loc, {str(h): [] for h in range(5)})
            dd["0"].extend((origin * scale).tolist())
            for h in (1, 2, 3, 4):
                dd[str(h)].extend((tr[:, h] * scale).tolist())
    return by_loc, {"flagged": flagged, "dropped": dropped}


def load_anchor_diagnostics() -> pd.DataFrame:
    """Per-cell g, shrinkage weight, R* and clipping, for the pinning clause."""
    rows = []
    for season in SEASONS:
        for asof in season_asofs(season):
            for loc in STATES:
                d = WORK / season / asof / f"{loc.replace(' ', '_')}_r0"
                f = d / "anchor.json"
                if not f.is_file():
                    continue
                a = json.loads(f.read_text())
                v = a["variants"][PRIMARY]
                rows.append({"season": season, "asof": asof, "location": loc,
                             "gamma": a["gamma"], "g_raw": v["g_raw"],
                             "w": v["w"], "g_hat": v["g_hat"],
                             "r_star_raw": v["r_star_raw"],
                             "r_star": v["r_star"],
                             "clipped_low": v["clipped_low"],
                             "clipped_high": v["clipped_high"],
                             "reason": v["reason"]})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--shards", type=int, default=4)
    ap.add_argument("--nice", type=int, default=12)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"pre-registration {preregistration_hash()}", flush=True)
    if a.smoke:
        print("smoke lives in research/slope-anchored/smoke.py", flush=True)
        return
    if a.prepare or a.run:
        t0 = time.time()
        cells = build_cells(workers=a.shards)
        print(f"prepared {len(cells)} cells in {time.time() - t0:.0f}s",
              flush=True)
        d = load_anchor_diagnostics()
        if len(d):
            print(f"anchor: median w {d.w.median():.3f}, median R* "
                  f"{d.r_star.median():.3f}, clipped "
                  f"{(d.clipped_low | d.clipped_high).mean() * 100:.1f}%",
                  flush=True)
    if a.run:
        execute(a.shards, a.nice)
        print("shards launched; poll status_*.json.prog", flush=True)


if __name__ == "__main__":
    main()
