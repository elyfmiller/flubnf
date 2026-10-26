# Model lane notes

The Oracle SIHRS and Groundhog methods, replays and scores; see
[ORACLE-SIHRS.md](../ORACLE-SIHRS.md) and [RETROSPECTIVES.md](../RETROSPECTIVES.md).
Works on the lab Mac (the Mac Studio); its research record lives in the
lab's private FluBNF-local tree, `research/groundhog-beta/oracle_member/`,
not in this repository.
Entries marked (laptop) are the Groundhog and donor-bank agent's, on
Ely's laptop, which pushes them itself; the others are the Oracle SIHRS
agent's.

## Now

- 2026-10-25 (23:50 UTC): THE HISTORICAL CEILING ON THE ORACLE'S 84 WEEKS: IT
  DOES NOT PASS FOR 2026-10-28, ON THE RULE WRITTEN FIRST (amendment 3,
  de645b23, frozen 23:41 UTC; announced above). So by the Submission
  notes' plan of 21:02 UTC, Wednesday runs the shrink at 15x alone and the
  ceiling waits for 11-04 at the earliest. It fails on two counts:
  - In the October as-ofs, the Wednesday analog, the pairing loses to the
    shrink alone (P3a): 0.790 against 0.778, +0.0125 [+0.0016, +0.0329].
  - The pairing's 95% coverage falls more than 0.010 below the shrink's
    (rule (iii)): -0.012 on all weeks, -0.014 on the early weeks.
  Everything else holds: P1, P2a, P2b, P3c and P4, and rules (i), (ii)
  and (iv). This agrees in direction with the Groundhog's screen
  (laptop, 23:50 UTC), where the pairing costs a little in
  September-October.
  How it was scored: post hoc on C0's stored weeks, no engine time. The
  knob's own functions on main a99d53d, in the pipeline's order
  (history_ratios on that week's vintage, history_limits,
  clip_rows_by_horizon, then cap_rows). 17,466 state cells; relWIS is
  natural / log. "early" means the first 8 scoreable weeks of each
  season, 24 weeks; "Oct" is the 4 October as-ofs of 2023-24.
                          relWIS          c95    h3>30x  early (c95)     Oct
    none                  0.6682 / 0.6987 0.916  10.0%   0.6715 (0.929)  0.861
    clip 15x              0.6680 / 0.7000 0.907   0.0%   0.6715 (0.898)  0.831
    shrink 15x            0.6705 / 0.7069 0.898   0.1%   0.6781 (0.867)  0.778
    clip 10x              0.6716 / 0.7034 0.895   0.0%   0.6799 (0.858)  0.811
    maximum alone         0.6626 / 0.6985 0.899   6.0%   0.6705 (0.899)  0.845
    0.975 alone           0.6760 / 0.7098 0.851   0.0%   0.6939 (0.806)  0.835
    maximum + shrink 15x  0.6645 / 0.7035 0.886   0.1%   0.6745 (0.853)  0.790
    maximum + clip 15x    0.6629 / 0.6995 0.894   0.0%   0.6713 (0.880)  0.830
    maximum + shrink 10x  0.6751 / 0.7153 0.865   0.1%   0.6985 (0.783)  0.746
  Week-cluster bootstrap, 2,000 resamples, natural | log:
    pairing - shrink 15x      -0.0060 [-0.0140, -0.0004] | -0.0034 [-0.0062, -0.0008]
        early                 -0.0036 [-0.0073, -0.0007] | -0.0052 [-0.0105, -0.0002]
        October               +0.0125 [+0.0016, +0.0329] | +0.0088
    pairing - clip 15x        -0.0035 [-0.0130, +0.0032] | +0.0036 [-0.0007, +0.0077]
    maximum - none            -0.0056 [-0.0139, -0.0001] | -0.0002 [-0.0028, +0.0018]
    maximum + clip - shrink   -0.0075 [-0.0161, -0.0007] | -0.0074 [-0.0119, -0.0031]
        October               +0.0522 [+0.0270, +0.0845]
  Predictions:
  - P1 holds (the maximum alone, above).
  - P2a holds: the pairing is 0.90% below shrink 15x.
  - P2b holds: within noise of the clip 15x.
  - P3a FAILS: the October loss above.
  - P3b (reported only): 0 of 4 October as-ofs had the maximum above 15x
    at h1 to h3. The 2023-24 as-ofs read 2022-23 alone, so the October
    ceilings were 5.2x, 8.7 to 12.4x, 15.6 to 25.4x and 20.3 to 37.8x at
    h0 to h3, against 11.7, 19.5, 26.2 and 37.8x on last week's live
    vintage.
  - P3c holds: 99% of the gain is from as-ofs dated November to January
    (September-October -2%, February to May 3%).
  - P4 holds: the 0.975 ceiling drops 95% coverage to 0.851 and is worse
    on the log scale.
  This lane's Q1 FAILED. The maximum changed far more blocks than I
  predicted: 21% at h0, 30% at h3, and 40% to 68% in October (the 97.5%
  quantile itself in 14% to 22%, and 29% to 51% in October). The
  Oracle's 99% and 97.5% levels run past history's maximum often, most
  in the early weeks. Q2 and Q3 held.
  Reading:
  (1) The pooled gain sits where the live round is not:
      - By season, the pairing minus the shrink is -0.026 in 2023-24
        (history from one season), -0.003 in 2024-25, and +0.0003 in
        2025-26.
      - 2025-26 reads three seasons of history, the nearest to the live
        round's four. There the ceiling touched 10% of h3 blocks, against
        45% in 2023-24.
  (2) In October the pairing loses at every horizon, by the mechanism
      the Submission notes found in last week's file:
      - The ceiling pre-clips h3, so the shrink needs a milder exponent
        and leaves h0 to h2 a few percent wider. The typical 97.5% over
        the median is 2.11 against 2.06 at h0, 3.11 against 3.00 at h1,
        4.83 against 4.71 at h2, and equal at h3 (7.29).
      - In October the narrowing is what scores.
      - The October subset is 4 weeks of one season, with ceilings
        tighter than the live round's, but the live file would move the
        same way.
  (3) Coverage: the pairing is below the shrink alone in every season
      (0.930 against 0.946, 0.874 against 0.890, 0.849 against 0.852)
      and at every horizon.
  (4) The clip forms:
      - The maximum alone is the best arm on the natural scale, with the
        shrink's coverage, but leaves 6.0% of h3 cells over 30x.
      - With the clip at 15x it clears the gate and beats the shrink
        alone on both scales, but loses to it in October, +0.052.
      - Every clip form loses to the shrink in October.
  (5) The vintage against the settled truth:
      - Pooled, the scores differ by +0.0003 [-0.0007, +0.0013].
      - The ratios are identical in 54% of week-horizons, but the maximum
        is an extreme statistic: 10% of week-horizons differ by more than
        16%.
      - One reporting spike sets a whole window: Ohio's 218 admissions in
        the week of 2023-05-20, between 17 and 14, is the h0 and h1
        maximum (12.3x, 12.1x) of the May 2026 as-ofs (the Groundhog
        found it too).
      - A spike can only loosen the ceiling, so it errs toward doing
        nothing.
  (6) Code:
      - No defect found. The comparators equal C0's cells exactly.
      - An independent implementation of the ratios equals history_ratios
        on every week, at both levels and from both sources.
      - Every touched block obeys its limit and the code's own count.
      - The no-limit identity holds, and the unit tests pass (163).
      - The two Submission-lane notes in the laptop entry (the ISO week
        53 distance, and the silent skip when the truth read fails) are
        the two this lane found.
  (7) A correction to amendment 2 (the exclusion arm X):
      - Its "September to November" rows were the 14 as-of weeks dated
        September to November, not the C0 reading's 24 early weeks, as
        the amendment said.
      - Re-read on the 24 weeks, the primary form is worse than the
        shrink at 15x at every n: X40 +0.0095 [+0.0025, +0.0165] up to
        X15 +0.0727. The conclusion is unchanged.
  What this lane recommends:
  - 10-28: the five override values of 2026-10-23 as they stand (seed
    season_total_early, weight 0.25, narrowing 0.7, output.tail_cap 15,
    output.tail_mode shrink), no ceiling.
  - 11-04: no case on these seasons to add the ceiling in November
    either. Its gain is 2023-24's, a season whose ceiling came from one
    history season. In 2025-26, the season most like the live one, it
    changes nothing and costs a little coverage. Ely's call.
  Records: research/oracle-width-screen on the lab Mac (AMENDMENT3_HIST.md,
  hist_arm.py, report_hist.py, arms/H_C0.pkl, logs/hist_C0.log,
  report_H.txt, report_H_extra.txt, report_H_argmax.txt,
  report_X_early24.txt).

- 2026-10-25 (23:50 UTC, laptop): THE HISTORICAL CEILING ON THE GROUNDHOG'S
  RETRO SEASONS: THE PAIRING IS SUPPORTED BY THE PRE-REGISTERED RULE, AND
  FOR THE GROUNDHOG IT IS FREE RATHER THAN A GAIN (Ely's request in chat;
  the Submission lane's handoff of 2026-10-25). Pre-registration c9587ab5
  (FluBNF-local research/groundhog-hist-ceiling/, frozen at 23:40 UTC
  before any replay of this screen), predictions G1 to G6 and the rule
  written first. The Groundhog's own retro on dev fafa1db in the shipped
  kernel form, every vintage of 2023-24 to 2025-26 (and 2026-27's four
  weeks, supplementary), hub 3a83d410; it reproduces the record exactly
  (0.6802, 0.6272, 0.6448, pooled 0.6423 on 17,116 cells). Then the
  pipeline's own order on every week: hub rows in whole admissions, the
  ceiling at the maximum with the ratios from that week's vintage
  (history_ratios, history_limits, clip_rows_by_horizon), then cap_rows.
  Three seasons, 17,116 state cells; relWIS natural / log, coverage 50 / 95:
    none (hub rows)      0.6423 / 0.6249   0.519 / 0.946
    clip 15x             0.6433 / 0.6261   0.519 / 0.939
    shrink 15x           0.6491 / 0.6311   0.508 / 0.928
    maximum alone        0.6419 / 0.6261   0.517 / 0.931
    maximum + shrink 15x 0.6478 / 0.6311   0.507 / 0.917
    maximum + clip 15x   0.6428 / 0.6271   0.517 / 0.926
  September-October (2023-24's 772 cells; the only October as-ofs among
  the three seasons), relWIS / cov95: none 0.978 / .916, clip 15x 0.967 /
  .916, shrink 15x 0.935 / .909, maximum 0.975 / .916, maximum + shrink
  0.937 / .909, maximum + clip 0.967 / .916. November (2,012 cells): none
  0.542 / .949, clip 0.548 / .913, shrink 0.561 / .867, maximum 0.542 /
  .940, maximum + shrink 0.561 / .867, maximum + clip 0.548 / .910.
  December on: every arm 0.652 to 0.658. 2026-27's four weeks (156
  cells): shrink 0.757, maximum + shrink 0.761, none 0.806.
  Week-cluster bootstrap, 2,000 resamples (negative = first arm better):
    maximum - none          -0.0004 [-0.0031, +0.0019]; Sep-Oct -0.0032 [-0.0058, -0.0016]
    maximum - clip 15x      -0.0014 [-0.0043, +0.0013]; Sep-Oct +0.0078; Nov -0.0062
    max + shrink - shrink   -0.0013 [-0.0039, +0.0009]; Sep-Oct +0.0015 [+0.0004, +0.0033]; Nov -0.0006
    max + shrink - clip 15x +0.0045 [-0.0008, +0.0099]; Sep-Oct -0.0308
    max + clip - clip 15x   -0.0005 [-0.0033, +0.0018]
    shrink 15x - clip 15x   +0.0058 [+0.0012, +0.0109]
  Reading. (1) The pairing passes every registered test (no worse than
  the shrink pooled or in any season; Sep-Oct within 0.005; coverage at
  least 0.90 and 0.40; code clean), and all six predictions hold. Its
  gain over the shrink alone is all one month, December 2023 (2023-24
  -0.0074; 2024-25 and 2025-26 0.0000), and in October it costs a little:
  +0.0015 on 2023-24's October weeks, +0.004 on this season's four. So
  the Groundhog does not stand in the way of the pairing, and does not
  argue for it; Wednesday's call rests on the Oracle's 84 weeks. (2) The
  maximum alone is within noise of none, as the Submission lane found
  post hoc (its 0.6406 against 0.6423 used the final truth; here,
  through the pipeline's own rows, 0.6419 against 0.6423), but it costs 95% coverage (0.946
  to 0.931) and 0.001 on the log scale, and it costs in a season that
  outgrows its history: 2024-25 +0.0020, December and January at the
  record peak (Pennsylvania, Massachusetts, Ohio, Michigan, h2-h3),
  against 2023-24 -0.0077. The live round reads four earlier seasons,
  2024-25 among them, so its ceiling is looser than any replay's. It does
  not clear the gate alone (h3 blocks over 30x: none 3.8%, maximum 2.4%,
  shrink 0.11%, pairing 0.04%). (3) Where it acts it trims the top: it
  changes 27% of state blocks (Sep-Oct 59%), 38% of those only at the
  0.99 and a further 26% from the 0.975 up, the 97.5% quantile down by a
  median 9%. (4) The vintage against the final truth: the same ratios in
  most cells, different in 66 of 97 weeks (mostly 2023-24: its vintages
  start a week later, and the final carries Ohio's 2023-05-20 spike, 218,
  12.3x at h0 in late-April windows against 2.6x in the vintage); scores
  -0.0003 [-0.0009, +0.0002]. 2023-24 reads history from 2022-23 and the
  spring of 2022 only, and its ceiling falls to 1.0x at h3 in mid-January
  2024.
  Ratios of the ceiling (maximum, vintage), median over the season's weeks
  at h0-h3: 2023-24 3.0, 3.9, 5.0, 6.0x; 2024-25 and 2025-26 3.1, 4.4,
  5.6, 7.2x; September-October 2023 3.1-5.2x at h0, 16-38x at h3; this
  season's weeks 3.5-11.7x at h0, 19.7-37.8x at h3. At the 10-17 vintage
  the h0 and h1 maxima (11.7x, 19.5x) are Puerto Rico on 2024-11-02 (6,
  14, 15, then 137 and 228), the return of mandatory reporting after the
  2024 voluntary window, not epidemic growth; h2 and h3 (26.2x, 37.8x)
  are Oregon's real rise of November 2022 (6, 5, 32, then 51, 113, 376,
  542). A reporting artefact can only loosen the ceiling, so it errs
  toward doing nothing; whether the ceiling's history should leave out
  the 2024 voluntary window is a question for 11-04, not Wednesday.
  CODE CHECK: the ratios re-implemented independently from the written
  rule equal history_ratios on all 97 replay weeks at 1 and at 0.975 (194
  week-levels, 0 mismatches); every block the ceiling touched in every week
  equals the rule as written (whole admissions, monotone, the median and
  below untouched); tests/test_tailcap.py and app/tests/test_knobs.py pass.
  Three findings for the Submission lane are under For other lanes
  (2026-10-26, laptop). The full record (the pre-registration, the report,
  the run log, the scripts) is in the repository:
  [model-groundhog-hist-ceiling-2026-10-25/](model-groundhog-hist-ceiling-2026-10-25/README.md).

- 2026-10-25 (23:42 UTC): THE HISTORICAL CEILING ON THE 84 WEEKS, PRE-REGISTERED
  AND RUNNING (Ely's request in chat; the Submission lane's handoff of
  2026-10-25 under For other lanes, predictions P1 to P4). Amendment 3 to
  the screen's pre-registration, frozen at 23:41 UTC before any ceiling row
  was computed, sha256 de645b23 (research/oracle-width-screen/
  AMENDMENT3_HIST.md on the lab Mac). Post hoc on C0's stored weeks, no
  engine time: the knob's own functions on main a99d53d
  (flubnf.tailcap.history_ratios, history_limits, clip_rows_by_horizon,
  then cap_rows), in the pipeline's order, the ratios from each week's
  vintage. Arms: the maximum alone, the 0.975 alone, the maximum + shrink
  15x, + clip 15x, + shrink 10x; against none, clip 15x, shrink 15x, clip
  10x; all 84 weeks and the early-week subset (the first 8 scoreable weeks
  of each season, 24, as in the C0 reading). The amendment makes P1 to P4
  operational and writes the pass rule for the 2026-10-28 round before any
  score: the checks pass, P1 to P3 hold (a miss in the favourable direction
  is not a failure), and the pairing is no worse than shrink 15x on both
  scales, in no season by more than 0.010, in 95% coverage by no more than
  0.010, and in the early weeks by no more than 0.005. Known before any
  score: the vintages start in 2022-02, so the 2023-24 as-ofs read history
  from 2022-23 alone (the live round reads four seasons), and the screen's
  only October as-ofs are the 4 of 2023-24. Checks on the smoke week
  2024-12-07 (scores not read) pass: the comparators equal C0's cells, an
  independent implementation of the ratios equals the code's, every
  clipped block obeys its limit and the code's own touched count. Result
  here well before Tuesday evening.

- 2026-10-24 (17:08 UTC): THE ORACLE SIHRS WIDTH SCREEN'S RECOMMENDATION,
  FOR THE TEAM REVIEW (beside the Groundhog's of 2026-10-23 00:40 UTC,
  laptop). All six arms are read: C0, R20, R22, HP, HS and G (post hoc),
  plus the trajectory-exclusion arm X. Pre-registration fd8f57d6 (frozen
  2026-10-22), amendment REG 51a85f76, amendment 1 (the boxes) affe3469,
  amendment 2 (X) 525ab77f; 84 as-of weeks of 2023-24 to 2025-26, 17,466
  scored state cells per rule, settled truth, FluSight's cell rule and
  baseline join; every arm passed checks A to C (the console's own scorer
  reproduced exactly on every cell). Pooled relWIS is natural / log;
  intervals are the week-cluster bootstrap, 2,000 replicates. Nothing is
  running on the lab Mac; the chain was stopped after HS, so the Mac is
  idle for Wednesday's freeze.
  1. FROM THE OLD REGISTRATION TO THE FORM OF 2026-10-28 (Ely's question;
     each step on the cells it shares with the first):
       registered member (to_date seed, w 0.5, no narrowing, no cap)
         0.749 / 0.805, 95% coverage 0.94; by season 0.766, 0.723, 0.778
       + Oracle weight 0.25          0.720 / 0.764
       + stage-rule seed            0.712 / 0.705 (2023-24 alone worse:
                                     0.828)
       + narrowing 0.7 (live 10-24)  0.668 / 0.699, coverage 0.92
       + shrink 15x (Ely's 10-28)    0.670 / 0.707, coverage 0.90; by
                                     season 0.690, 0.656, 0.682
     The 10-28 form against the registered member: -0.078 [-0.095,
     -0.062] natural, -0.098 [-0.119, -0.080] log, better in every season
     (-0.076, -0.067, -0.096). The narrowing is the largest single step;
     the cap gives back 0.002 natural and 0.008 log of it in exchange for
     the gate (h3 cells over 30x: 0.1% against 10.0%).
  2. THE OUTPUT RULE: THE SHRINK AT 15x, AS ELY DECIDED, IS SUPPORTED.
     Against no rule +0.002 [-0.004, +0.008] | +0.008 [+0.003, +0.014];
     September to November +0.007 [-0.006, +0.017] | +0.020 [+0.007,
     +0.031]. The clip at 15x is a little cheaper on the log scale
     (-0.000 | +0.001) and the two cannot be told apart on the natural
     scale, so the choice on form stands. The pre-registered "free line"
     (the smallest shrink within 0.010 of no rule with 95% coverage at
     least 0.90) is 20x: -0.000 | +0.003. Not 10x or 8x: shrink 10x
     +0.013 | +0.021 season-wide and +0.032 | +0.052 in the early weeks
     (early 95% coverage 0.79). Leave-one-season-out over the narrowing
     and the rule held out 0.673 / 0.703; it never chose a cap below 20x.
  3. THE STRUCTURAL ARMS: NONE PASSES THE PRE-REGISTERED RULE.
     R20 and R22 (the Reff bound at 2.0 and 2.2): null; the filter gains
     and the step and the narrowing absorb it. The bound stays at 2.5.
     HP (the pooled past-season box on eps1 and phi1): null on rule (iv),
     though the best arm here: held out 0.663 / 0.691 against 0.673 /
     0.703. HS (the per-state box, the swarm carry): null on rules (ii)
     and (iv), held out 0.668 / 0.701 (entry below). Both prior arms gain
     most in 2023-24 (-0.047, -0.040) and lose at the 2025-26 December
     and January peak in the Northeast (+0.010); HP chose k 0.8 in every
     fold, and both gain more against C0 at k 0.8 than at 0.7.
     G (the per-week growth cap): worse than the clip at every g (1.5x
     0.719, 2x 0.677, 3x 0.672 against clip 15x 0.668), and far worse on
     the log scale. X (the trajectory exclusion): costs at every n
     (07:18 UTC entry).
  4. RECOMMENDATIONS.
     a. 2026-10-28: the override values of the Submission notes (stage
        seed, w 0.25, narrowing 0.7, shrink 15x). Nothing from this screen
        changes them.
     b. Ship nothing from the structural arms; keep the shipped priors.
     c. One lead, for Ely: HP as a pre-registered research shadow this
        season (the 2026-27 box from all four past seasons, run beside the
        live member, scored as weeks settle, read at k 0.7 and 0.8). The
        three seasons here cannot confirm it: the 2023-24 gain rests on one
        season-end fit from the cut 2022-23 vintage.
     d. Revisit the cap's n after capped weeks score, as the Submission
        notes plan: on these seasons the shrink is free from 20x and costs
        below 15x.
  5. PREDICTIONS (fd8f57d6 section 7): P1 right (shrink 10x +0.013, 1.9%;
     coverage 0.92 to 0.87). P2 half: the clip is better than the shrink
     at every n over whole seasons, but the shrink is not better in
     September to November. P3 right (R20 within 0.005 of C0). P4 a tie
     for the member, true for the filter. P5 half (net within 0.010; the
     early weeks gain rather than cost; the cost sits at the 2025-26
     peak). P6 right.
  6. THE RECORDS: pre-registration, amendments, scorers, reports and the
     per-cell tables are in the research archive on the lab Mac
     (FluBNF-local/research/oracle-width-screen), not in the repository,
     under the research-stays-local rule. Whether they go to a branch for
     the review is Ely's call; until then, any number here can be
     re-derived on request.
- 2026-10-24 (17:08 UTC): HS, THE PER-STATE PAST-SEASON BOX (THE SWARM
  CARRY): NULL. 84 weeks, no failed cell, checks A to C passed. The boxes
  are wide: eps1 widths a median 0.62, 0.74, 0.86 by test season, and
  phi1 fell back to the shipped 0-52 in 17, 43 and 47 of 52 states (a fit
  straddling the wrap). In 2025-26 13 states kept both shipped ranges,
  and their samples are bit-identical to C0's, while all 39 boxed states
  differ: the hook ran, and the replay is deterministic. Held out 0.668 /
  0.701 against C0's 0.673 / 0.703, 95% coverage 0.91 against 0.92; by
  season -0.040, -0.004, +0.0104. Rule (ii) fails (2025-26 more than
  0.010 worse) and rule (iv) fails: HS minus C0 at C0's choice (k 0.7,
  shrink 20x) -0.003 [-0.010, +0.004] | -0.000 [-0.004, +0.004]; at C0's
  per-season choices -0.006 [-0.014, +0.002] | -0.002 [-0.006, +0.002].
  At Ely's 10-28 setting (shrink 15x) -0.003 [-0.010, +0.004] | -0.001
  [-0.004, +0.003], 95% coverage 0.89 against 0.90. At k 0.8, clip 15x
  -0.008 [-0.017, -0.001] | -0.003 [-0.007, +0.001] (k 0.8 read after
  the scores, a lead only). September to November at clip 15x -0.020
  [-0.052, -0.003] | -0.012 [-0.022, -0.004], not a registered test. The
  plain filter gains -0.058 [-0.087, -0.036] (HP -0.055). Where: 2023-24
  gains from October to December (Texas, Florida, California first);
  2025-26 loses in December and January (Pennsylvania, New York, New
  Jersey, Massachusetts, Michigan). HP's pattern, weaker: the pooled box
  beats the per-state one. P5 holds for HS (net within 0.010, the cost at
  the 2025-26 peak), except that the early weeks gain.
- 2026-10-24 (07:18 UTC): THE TRAJECTORY-EXCLUSION ARM (Ely's idea, the
  Submission lane's handoff of 2026-10-23): IT COSTS AT EVERY n; NOT A
  CANDIDATE. Pre-registered before any of it was computed (amendment 2,
  sha256 525ab77f, frozen 07:03 UTC; research archive), scored post hoc
  on C0's 84 stored weeks (17,466 cells). A path is one index of the
  submitted seed's 30,000 samples, which stays one trajectory through the
  Oracle step (each filter path times one donor's four-horizon factors),
  the narrowing (monotone per horizon) and the floor (per-path noise).
  The point in the pipeline, decided before scoring: XP (primary, the
  Submission lane's reading) un-narrows the stored samples, drops every
  path above n times the recent level at any horizon, and narrows the
  rest again at 0.7 about their own median; XS (secondary) drops on the
  stored, already narrowed samples. Checks passed on every week: the
  comparators equal the C0 cells exactly, XP with no limit reproduces
  them exactly (0 of 17,466 cells differ), no kept path exceeds its
  limit, and the drop counts equal a plain loop's on the smoke week; no
  location-week fell below the 300-path floor.
  Pooled relWIS natural / log, 95% coverage (k 0.7): none 0.668 / 0.699,
  0.92; clip 15x 0.668 / 0.700, 0.91; shrink 15x 0.670 / 0.707, 0.90;
  shrink 10x 0.681 / 0.720, 0.87.
  XP: X40 0.675 / 0.719, 0.90; X30 0.680 / 0.727; X20 0.691 / 0.745; X15
  0.704 / 0.764, 0.86; X40 + shrink 15x 0.676 / 0.719. Against shrink
  15x: X40 +0.005 [+0.001, +0.009] | +0.012 [+0.007, +0.017]; X15 +0.034
  [+0.014, +0.054] | +0.057 [+0.035, +0.077]; September to November X15
  +0.107 [+0.050, +0.134]. Paths dropped per location-week, X40: median
  0.003%, 90th percentile 7.2%, maximum 38% (Maine 2023-10-07), over 1%
  in 1,111 of 4,368; X15: median 0.07%, 90th 19%, maximum 58% (Utah
  2025-11-15); in the location-weeks whose h3 97.5% was over 30x with no
  rule, X15 drops a median 26%. The median moves: X15's h3 median is
  unchanged in 60% of cells, but its 10th percentile is 0.67 of the none
  median and its 1st 0.30 (South Dakota 2023-10-07 goes to 0).
  XS: X40 0.668 / 0.702, 0.91 (minus none -0.000 [-0.002, +0.001] |
  +0.003 [+0.001, +0.005]; 3.0% of h3 cells still over 30x); X30 0.668 /
  0.704; X20 0.671 / 0.710; X15 0.676 / 0.718, 0.89 (minus shrink 15x
  +0.005 [+0.002, +0.009] | +0.011 [+0.006, +0.015]); X40 + shrink 15x
  0.670 / 0.707 (minus shrink 15x +0.000 [-0.000, +0.000] | +0.000
  [-0.000, +0.001]).
  The Submission lane's predictions: P1 fails on the drop share (over 1%
  of paths in a quarter of location-weeks at XP, an eighth at XS, not "a
  few"); free on the natural scale at XS and at the edge at XP (+0.007
  [-0.000, +0.014]), not on the log scale. P2 holds in direction and
  cause (the median moves down, the cost sits in the early weeks), and
  is too mild for XP: X15 is worse than shrink 10x, not between. P3
  holds for XS and fails for XP (+0.006 [+0.002, +0.009] against shrink
  15x). Mine: Q1 wrong (X40 is not within 0.001 on both scales and drops
  more than 0.1% in a third of location-weeks); Q2 right; Q3 wrong on the
  score (X15 is 0.036 worse than clip 15x at XP, 0.008 at XS), right on
  coverage; Q4 half (the worst 1% moves past 20%, but the h3 median moves
  more than 1% in 35% of cells, not 10%); Q5 right.
  Reading: the forecasting sample's high paths carry score. A path that
  crosses n by horizon 3 is also high at h0 to h2, so dropping it whole
  lowers the median and the lower quantiles at every horizon, which the
  per-horizon caps (they touch only the levels above the median) never
  do; the log scale shows it most (low-count cells lose their middle).
  The only harmless form, XS at 40x with the shrink at 15x on top, is
  indistinguishable from the shrink at 15x, so it buys the sentence "no
  path above 40x" about samples the hub never sees. 2023-24 gains under
  every exclusion (XP X15 0.681 against none 0.706), as it did under HP:
  that season's blow-outs were wrong and the other seasons' were not.
  Recommendation: drop the exclusion; the shrink at 15x stays the
  output rule. Nothing here touches the 2026-10-28 round. HS (the
  per-state prior) finishes about 16:00 UTC; the screen's full
  recommendation follows it here.
- 2026-10-24 (07:01 UTC): HP, THE POOLED PAST-SEASON PRIOR ON eps1 AND
  phi1: NULL UNDER THE PRE-REGISTERED RULE, THOUGH THE FIRST ARM TO BEAT
  C0 HELD OUT. 84 weeks, no failed cell, checks A to C passed (A exact on
  all 17,466 cells). The boxes that ran (amendment 1): 2023-24 eps1
  0-0.52, phi1 10.5-41.9; 2024-25 eps1 0-0.54, phi1 11.2-44.6; 2025-26
  eps1 0-0.56, phi1 the shipped 0-52 (two fits straddle the wrap).
  Held-out 0.663 / 0.691 against C0's 0.673 / 0.703, 95% coverage 0.92
  against 0.92; by season -0.047, -0.011, +0.010 (+0.0097, inside rule
  (ii)'s 0.010). Rules (i) to (iii) pass; (iv) fails: HP minus C0 at
  C0's choice (k 0.7, shrink 20x, as R20 and R22 were read) -0.003
  [-0.012, +0.005] | log -0.004 [-0.012, +0.004]; at C0's choice season
  by season -0.006 [-0.015, +0.003] | -0.006 [-0.014, +0.002]. Each arm
  at its own held-out choice (not the registered test) -0.011 [-0.021,
  -0.001] | -0.013 [-0.021, -0.004]. HP chose k 0.8 in every fold: the
  prior narrows the band itself, so it wants less of the Oracle's
  narrowing.
  At Ely's 2026-10-28 setting (k 0.7, shrink 15x): HP minus C0 -0.003
  [-0.012, +0.005] | -0.005 [-0.013, +0.003], 95% coverage 0.88 against
  0.90; by season -0.024, -0.009, +0.016. The clip at 15x is the same in
  sign (-0.003; 2025-26 +0.018). At k 0.8 the gain is larger and clears
  zero on the natural scale (shrink 20x -0.010 [-0.018, -0.002] | -0.009
  [-0.016, -0.001], 95% coverage 0.92; clip 15x -0.009 [-0.019, -0.001]
  | -0.007 [-0.015, +0.001]), but k 0.8 is HP's own choice, read after
  the scores, so it is a lead, not a result.
  Where it comes from: the plain filter gains most (0.808 against 0.863,
  -0.055 [-0.082, -0.033]; 2023-24 0.940 against 1.074). The member gains
  in 2023-24 through the October to December rise (Texas, Florida,
  California first) and loses in 2025-26 at the December and January
  peak in New York, New Jersey, Pennsylvania, Ohio and North Carolina
  (95% coverage in December 0.80 against 0.85). 2025-26's box limited
  only eps1 (to 0.56), so that season's sharp peak wanted more seasonal
  amplitude than the past seasons had. The band narrows (h3 97.5% over
  the median 3.4x against 4.0x; h3 cells over 30x with no rule 4.4%
  against 10.0%). P5 is half right: net within 0.010 at the live
  settings (held out -0.011), the cost at the peak only in 2025-26, and
  the early weeks gain rather than cost (September to November, log
  -0.027 [-0.048, -0.007] at clip 15x).
  Reading: nothing ships. HP is a lead that these three seasons cannot
  confirm: each test season's box comes from one to three earlier
  seasons, and the one large gain, 2023-24, rests on a single
  season-end fit on the cut 2022-23 vintage. The honest next test is
  prospective: the 2026-27 box from all four seasons, run beside the
  live member as a research shadow and scored as weeks settle; Ely's
  call. HS is running (about 16:00 UTC), then the trajectory-exclusion
  arm (Submission's handoff of 2026-10-23), pre-registered before
  anything of it is scored.
- 2026-10-23 (20:52 UTC): R22, THE Reff PRIOR CAPPED AT 2.2: NULL TOO.
  84 weeks, no failed cell, checks A to C passed. Held-out 0.674 / 0.706
  against C0's 0.673 / 0.703, 95% coverage 0.91 against 0.92; by season
  -0.010, +0.002, +0.005. R22 minus C0 at the live settings, natural |
  log: no rule +0.001 [-0.002, +0.005] | +0.003 [+0.001, +0.006]; clip
  15x +0.002 [-0.002, +0.005] | +0.003 [+0.001, +0.006]; clip 10x +0.002
  [-0.002, +0.005] | +0.003 [+0.001, +0.005]. The plain filter gains
  -0.021 [-0.033, -0.012] (R20 -0.034), the member nothing; the log
  scale loses a little in both arms. P4 (R22 between C0 and R20) holds
  for the filter and is a tie for the member. Neither Reff bound is a
  lever for the Oracle; the bound stays at the shipped 2.5. HP started
  20:29 UTC (about 06:00 UTC Saturday), then HS.
- 2026-10-23 (10:36 UTC): R20, THE Reff PRIOR CAPPED AT 2.0: NULL UNDER
  THE PRE-REGISTERED RULE. 84 weeks, no failed cell, checks A to C as for
  C0. Held-out (leave-one-season-out over the narrowing and the rule):
  0.674 / 0.706 against C0's 0.673 / 0.703, 95% coverage 0.91 against
  0.92 (rule (i) fails); by season -0.017 (2023-24), -0.001 (2024-25),
  +0.012 (2025-26, rule (ii) fails). At the live settings, R20 minus C0
  on common cells, natural | log: no rule +0.001 [-0.005, +0.007] |
  +0.003 [+0.000, +0.006]; clip 15x +0.002 [-0.004, +0.007] | +0.003
  [+0.000, +0.006]; clip 10x +0.002 [-0.004, +0.007] | +0.003 [+0.000,
  +0.006]; shrink 10x +0.002 [-0.003, +0.008]. The bound helps the plain
  filter (-0.034 [-0.053, -0.018] natural, +0.004 log) and the step and
  the narrowing absorb it; it narrows the tail a little (h3 cells over
  30x with no rule 8.8% against 10.0%; h3 97.5% over the median 3.8x
  against 4.0x) and clears nothing the cap does not. P3 held (within
  0.005 of C0 at their choices). So the Reff cap is not a lever for the
  Oracle on these seasons; nothing to ship. R22 is running (about 20:00
  UTC), then HP and HS.
- 2026-10-23 (01:38 UTC, laptop): ELY'S DECISION, "SHIP THE KERNEL, CLIP
  AT 10x". (1) THE SIZE-MATCHED KERNEL SHIPS AS THE GROUNDHOG'S DEFAULT
  (commit 689a650 on dev; pull request #48, https://github.com/elyfmiller/flubnf/pull/48, dev to main, for Ely's
  merge before the 2026-10-28 round). Inside each class (own cells, the
  rest) a donor week's weight is exp(-(ln v0 - ln a)^2 / 2), v0 its own
  count and a the jurisdiction's newest; a class of 30 or more cells left
  with fewer than 30 effective donors takes equal weights. Record: the
  console and the presets write local_pools {"own_share": 0.5,
  "anchor_weight": "kernel", "kernel_sd": 1.0, "ess_floor": 30.0};
  {"own_share": 0.5} alone is the form of 2026-10-15 to 2026-10-23, the
  shipped Groundhog of its day (not research); no key is the pooled form.
  New knob groundhog.kernel_sd (0 off); `flubnf groundhog retro
  --kernel-sd 0` replays the earlier form, `--own-share 0 --kernel-sd 0`
  the pooled one. The README's own command reproduces the screen on hub
  3a83d410: 0.680, 0.627, 0.645, pooled 0.6423 on 17,116 cells, coverage
  50/80/95 0.500 / 0.785 / 0.936 (the earlier form 0.6604). Card
  GroundHogCGR 1.3 (methods 196 characters; the kernel in methods_long;
  record 0.642). The default run's Groundhog bytes are re-pinned; with
  the shipped form set back, the old hash returns exactly, so the kernel
  is the only change. Full suite on the laptop: only the launcher and environment
  failures plain dev also shows here; CI on the pull request is the
  independent check. An independent review before the push confirmed the
  record pattern and found two defects (the site's note for mixed trees,
  a label prefix on research rows), both fixed with tests.
  (2) THE CAP FOR 2026-10-28: CLIP AT 10x, ONE SETTING FOR BOTH MEMBERS
  (override values output.tail_cap 10, output.tail_mode clip; the
  registered form stays CAP_PRODUCTION 0, so the run carries the reason).
  On the 2026-10-24 round's data with the kernel, the clip at 10x binds
  at horizon 3 in all 53 jurisdictions (the model's typical h3 tail is
  14.8x the recent level), so this week the cap, not the model, sets
  every h3 97.5% quantile; the h3 band is 4.1x the median; Ohio reads
  253, 451, 620, 733. Without the kernel the clip would have flattened
  Ohio to 733 at every horizon.
  Requests. Submission: the 10-28 override values are cap 10, form clip
  (with seed season_total_early, weight 0.25, narrowing 0.7 as before);
  run main at or after the merge of #48; carry card 1.3 to the hub fork
  when Ely asks for the hub pull request (none opened by this lane).
  App: the Models, Home and Methods pages and docs/FLUSIGHT-2026-27.md
  still print the earlier record (0.660; 0.702, 0.651, 0.653): the
  shipped record is 0.642 (0.680, 0.627, 0.645) on the same 17,116
  cells, the earlier form 0.660, the pooled form 0.670; the site's new
  label "Groundhog (own-state form)" names trees replayed under the
  earlier form, and the mixed label is now "Groundhog (mixed forms)". The
  review also found the earlier form in CITATION.cff (lines 34 and 38),
  the Groundhog diagram's growth-ratios box (app/ui/templates/
  diagrams.html, analogue_mech) and docs/SITE.md (lines 115-117, the
  labels). Oracle SIHRS agent: docs/ORACLE-SIHRS.md line 283 points at
  "the shipped own-state form's" README row, which is now the kernel
  form's. From the 11-11 round the Groundhog's cells say no cap or
  clip 15x (tighter caps cost it from November on).

- 2026-10-23 (00:40 UTC, laptop): THE GROUNDHOG'S RECOMMENDATION FOR
  2026-10-28, BESIDE THE ORACLE SIHRS'S (its interim reading 3991e0b7 and
  step table e3d15a9f), for the team review. From the tail-cell screen
  (entry of 2026-10-22 04:55 UTC; prereg 28f0f33d6ea7e232, three
  amendments; four seasons, 17,272 state cells, the cap through main's
  code with the rounding fix).
  1. THE GROUNDHOG'S FORM: SHIP THE SIZE-MATCHED KERNEL (s = 1, the
     effective-donor guard 30, on the own-share form). It is independent
     of the cap and gains under every form and n: pooled relWIS, shipped
     against kernel, none 0.661 / 0.643, clip 15x 0.661 / 0.644, clip 10x
     0.665 / 0.648, shrink 15x 0.666 / 0.649, shrink 10x 0.680 / 0.664;
     every complete season, 50 of 52 states, bootstrap [+0.010, +0.024].
     It removes the Ohio defect at its source: on the 2026-10-24 round's
     data Ohio's 97.5% quantiles become 253, 451, 620, 964, and no
     jurisdiction is above 30x before any cap (shipped: 9). It passed its
     own pre-registered screen on 2026-10-17. Shipping it is the
     own-share chores (shipped default, record pattern, card version,
     tests, README, dev to main) and needs Ely's go by Sunday 10-25.
     The floor, the winsor, the spike repair and the 2024 window are not
     recommended: each moves the pooled score by 0.003 or less.
  2. THE CAP: ONE SETTING FOR BOTH MEMBERS (output.tail_cap and
     output.tail_mode are BOTH knobs on main), AND THE TWO LANES NOW AGREE
     ON THE FORM: THE CLIP. The Oracle's shrink costs it most in the early
     weeks (shrink 10x +0.032, early 95% coverage 0.79), which rules the
     shrink out as a shared setting. The Groundhog with the kernel under
     the clip: none 0.643, clip 15x 0.644, clip 10x 0.648, clip 8x 0.654
     season-wide; September-October 0.949, 0.939, 0.922, 0.905; November
     0.542, 0.548, 0.569, 0.593; 95% coverage season-wide 0.937, 0.940,
     0.928, 0.918. So for the Groundhog the clip at 15x is free and at 10x
     costs 0.005 season-wide while gaining 0.017 in October.
     On n: clip 15x is free for both members on whole seasons and clears
     the 30x gate for both; clip 10x reaches Ely's typical width at a
     small cost to both (Oracle +0.003, inside noise; Groundhog +0.005,
     better in October), with the Oracle's early-week 95% coverage at
     0.86. This lane's pick for the 10-28 round: clip 10x if Ely wants the
     narrower width this October, clip 15x as the joint hedge; neither
     lane's replays hold an early-surge October like 2022's.
  3. NOT RECOMMENDED: SPLITTING THE CAP BY MEMBER. The Groundhog's shrink
     at 10x is better still in October (0.828 against 0.922 for the clip)
     but costs it from November on (0.599 against 0.569), so a per-member
     shrink would pay for at most the two October-as-of rounds (10-28 and
     11-04), rests on thin October evidence (928 cells: 2023-24 and this
     season's four weeks; 2025-26's rounds began in November), and needs
     a code change to knobs the Submission lane owns. The shared clip
     keeps both members on the code that was screened.
  4. FROM NOVEMBER (the 11-11 round, as-of 11-07): the Groundhog's cells
     say no cap or clip 15x; tighter caps cost it from November on at
     every form.

- 2026-10-23 (00:33 UTC): AMENDMENT 1, THE PAST-SEASON BOXES' VALUES
  (sha256 affe3469, written by the frozen rule from the season-end fits,
  before HP or HS runs and before any arm is scored; R20 started 00:32
  UTC). Season-end fits, per-jurisdiction medians: eps1 0.19 / 0.15 /
  0.15 (5-95%: 0.06-0.40), phi1 30.3 / 28.5 / 25.4 weeks (5-95%:
  10-36) for 2022-23, 2023-24, 2024-25. HP (pooled): eps1 0 to 0.52,
  0.54, 0.56 for 2023-24, 2024-25, 2025-26 (shipped 0 to 1); phi1 10.5
  to 41.9 and 11.2 to 44.6 weeks for the first two, and the shipped 0 to
  52 for 2025-26, because two of its source fits (Massachusetts and
  Texas, 2024-25) sit across the wrap: the registered fallback. HS (per
  jurisdiction): the boxes come out nearly as wide as the shipped prior
  (phi1 width median 46.7, 52.0, 52.0 weeks; eps1 0.62, 0.74, 0.86),
  because one jurisdiction's season-end fit does not pin its own timing
  tightly even with the season in hand, and the widened union over its
  seasons covers almost everything. So HS will sit close to C0, and HP's
  test is the amplitude cap plus the timing box in two seasons. Both run
  as registered (HP about 06:30 UTC Saturday, HS about 16:30 UTC).
- 2026-10-23 (00:24 UTC): FROM THE OLD REGISTRATION TO THE FORM UNDER
  TEST, ONE CHANGE AT A TIME (amendment R; REG complete, 84 weeks, no
  failed cell, check A exact on every cell of the three seasons). Each
  step against the registered member on the cells it shares with it,
  three seasons pooled; relWIS natural / log, 50% and 95% coverage, share
  of h3 cells over 30x the recent level; step minus registered with the
  week-cluster bootstrap (natural | log):
  1. registered (to_date, w 0.5, k 1): 0.749 / 0.805; 0.53, 0.94; 5.8%.
     By season 0.766, 0.723, 0.778.
  2. + weight 0.25 (the registered run's logged secondary, pre-floor):
     0.720 / 0.764; 0.58, 0.96; 8.7%. -0.029 [-0.048, -0.012] | -0.041
     [-0.056, -0.028].
  3. + the stage-rule seed (C0 at k 1, re-exponentiated, within check
     C): 0.712 / 0.705; 0.62, 0.98; 23.1%. -0.036 [-0.065, -0.006] |
     -0.100 [-0.128, -0.075]. By season 0.828, 0.687, 0.687: the seed
     costs 2023-24 on the natural scale (its one-season expectation) and
     carries the log-scale gain; it is also where the wild far tails come
     from (h3 cells over 30x 8.7% to 23.1%).
  4. + narrowing 0.7, the live configuration of the 2026-10-24 round:
     0.668 / 0.699; 0.48, 0.92; 10.0%. -0.080 [-0.099, -0.062] | -0.106
     [-0.129, -0.085]. By season 0.706, 0.653, 0.670.
  5. + the upper-tail rule: clip 15x 0.668 / 0.700, 0.91, 0%, -0.081 |
     -0.105; clip 10x 0.672 / 0.703, 0.90, 0%, -0.077 | -0.102; shrink
     15x 0.670 / 0.707, 0.90, 0.1%, -0.078 | -0.098; shrink 10x 0.681 /
     0.720, 0.87, 0.1%, -0.067 | -0.085; shrink 8x 0.691 / 0.730, 0.85,
     -0.058 | -0.075. Every interval excludes zero.
  Reading: the three changes since the registration are worth 0.080 on
  the natural scale and 0.106 on the log scale on these seasons, the
  weight and the narrowing carrying the natural-scale gain and the seed
  the log-scale gain; the cap gives back between nothing (clip 15x) and
  0.014 / 0.021 (shrink 10x) of it. The interim recommendation for the
  Oracle's rule on 2026-10-28 stands (the clip). Full table:
  `research/oracle-width-screen/logs/steps_REG_C0.txt`. The season-end
  fits started 00:03 UTC; R20 follows, then R22, HP and HS.
- 2026-10-22 (14:41 UTC): THE ORACLE SIHRS'S UPPER-TAIL RULE ON FULL
  SEASONS (C0), AN INTERIM READING WITH A RECOMMENDATION FOR 2026-10-28;
  THE SCREEN'S VERDICT FOLLOWS WITH THE ARMS. C0 is complete: 84 weeks,
  17,466 scored cells per rule, no failed cell, 9.7 hours. Checks: A exact
  (`retro.score_season` on every cell of all three seasons, difference
  0), B exact, C 0.9990 at k 0.7 and 0.9995 at k 1. Lab archive
  `research/oracle-width-screen/logs/report_C0.txt`.
  - At k 0.7 (relWIS natural / log, 95% coverage, share of h3 cells over
    30x the recent level): none 0.668 / 0.699, 0.92, 10.0%; shrink 8x
    0.691 / 0.730, 0.85; 10x 0.681 / 0.720, 0.87; 15x 0.670 / 0.707,
    0.90; 20x 0.668 / 0.702, 0.91 (shrink 0.1% over 30x at every n, the
    cells whose h3 median is itself above the limit); clip 8x 0.676 /
    0.707, 0.88; 10x 0.672 / 0.703, 0.90; 15x 0.668 / 0.700, 0.91 (clip
    0%). Growth caps of 1.5x, 2x and 3x a week 0.719, 0.677, 0.672:
    dominated. The filter alone 0.863 / 0.881.
  - Minus none, week-cluster bootstrap, natural | log: shrink 8x +0.023
    [+0.003, +0.043] | +0.032 [+0.017, +0.047]; shrink 10x +0.013
    [-0.001, +0.027] | +0.021 [+0.010, +0.033]; shrink 15x +0.002
    [-0.004, +0.008] | +0.008 [+0.003, +0.014]; clip 10x +0.003 [-0.002,
    +0.009] | +0.005 [+0.001, +0.008]; clip 15x -0.000 [-0.002, +0.001] |
    +0.001 [-0.000, +0.003].
  - The early weeks, where the gate binds (the first eight scoreable
    weeks of each season, 24 weeks; with no rule 33% of h3 cells are
    over 30x and the typical h3 97.5% is 21.5x the recent level): shrink
    10x +0.032 [+0.003, +0.057] | +0.052 [+0.029, +0.071], 95% coverage
    0.93 to 0.79; shrink 15x +0.007 [-0.006, +0.017] | +0.020 [+0.007,
    +0.031], 0.87; shrink 20x -0.000 | +0.008 [-0.000, +0.015], 0.90;
    clip 10x +0.008 [-0.003, +0.020] | +0.012 [+0.004, +0.019], 0.86;
    clip 15x 0.000 [-0.004, +0.003] | +0.003 [+0.000, +0.006], 0.90.
  - Reading: for the Oracle the shrink costs more than the clip at every
    n, and most in the early weeks, the opposite of the Groundhog, whose
    October cells sit at the baseline. The location-wide exponent the
    worst horizon needs also squeezes the upper side of h0 to h2, where
    truth lands in a fast rise; the clip takes only the far tail.
    Predictions: P1 held (shrink 10x +1.9%, coverage down 0.05); P2 held
    on whole seasons and failed in the early weeks.
  - The Submission lane's 44-week cloud screen, checked on the same 44
    weeks: natural relWIS and 95% coverage agree within 0.001 to 0.005
    for every rule (none 0.670 / 0.933 here, 0.671 / 0.930 there;
    shrink 10x 0.691 / 0.861, 0.688 / 0.869; clip 15x 0.671 / 0.917,
    0.670 / 0.917). Log relWIS runs 0.008 to 0.014 lower here (none
    0.713 against 0.727): this scores the submitted seed after the
    floor and the rounding, as the hub scores the file; the cloud
    scored the five-seed mean before the floor.
  - Recommendation for the Oracle's rule on 2026-10-28 (interim): the
    clip, not the shrink. Clip 15x is free on full seasons and in the
    early weeks and leaves no h3 cell over 30x; clip 10x reaches Ely's
    typical 10x for a small cost (+0.003 natural, inside noise; +0.005
    log; early-week 95% coverage 0.86). If the shrink's shape is wanted,
    20x is the smallest free n (the pre-registered free line). Shrink at
    10x or 8x is not for the Oracle. Leave-one-season-out over the whole
    grid picks mild rules (clip 20x at k 0.8, shrink 30x, shrink 20x;
    held-out 0.673 / 0.703, coverage 0.92): on score alone nothing asks
    for a cap, so the cap is there for the gate. The Groundhog's reading
    is the laptop agent's.
  - Next: REG (running since 14:19 UTC, about 7 hours) and its step
    table from the old registration; then the season-end fits, R20,
    R22, HP and HS. The screen's recommendation goes here when they are
    read, for the team review.
- 2026-10-22 (04:55 UTC, laptop): THE GROUNDHOG'S TAIL-CELL SCREEN IS
  SCORED (the Submission handoff 4b0e03d, Ohio's double-peaked band; lab
  archive `research/groundhog-tail-cells/`, prereg 28f0f33d6ea7e232 and
  three amendments, all written before any capped score: the cap through
  main's own code with the rounding fix; 8x, 10x and 15x at Ely's word;
  all available seasons at Ely's word). Code on branch
  groundhog-tail-cells (a32b941, on dev 519e20f): research options only,
  the shipped path untouched. Arms on the own-share form: C0 shipped, C1
  base-week floor 5, C2 ratios winsorised at the pool's 0.99 quantile, C3
  single-week spike repair, C4 the 2024 voluntary-reporting weeks
  (2024-05-04 to 10-26) removed, C5 the size-matched kernel s=1 with the
  effective-donor guard, C6 C5+C3+C4, C7 C5+C1, C8 C5+C2. Seasons
  2023-24, 2024-25, 2025-26 and the current season's four weeks (17,272
  state cells; 2022-23 has no vintages and no admissions donors).
  The diagnosis holds: C0 reproduces the submitted Ohio 97.5% quantiles
  exactly (763, 3638, 936, 5864); Ohio has two own cells based on 1
  admission (2024-09-28 and 10-12), so the 229 sits at h1 and h3. 28 of
  the 46 ratios above 20x come from the 2024 voluntary-reporting weeks.
  Pooled relWIS (states) and 95% coverage:
    arm   none   shrink8 shrink10 shrink15 clip8  clip10 clip15
    C0    .661   .691    .680     .666     .670   .665   .661
    C1    .657   .688    .676     .663     .667   .662   .658
    C5    .643   .676    .664     .649     .654   .648   .644
    C6    .642   .676    .664     .649     .654   .648   .643
    C7    .643   .676    .664     .649     .654   .648   .643
    cov95 C5: none .937, shrink8 .884, shrink10 .904, shrink15 .928
  C2, C3, C4 sit within 0.0002 of C0 (only 5 single-week spikes exist in
  the whole bank). The kernel gains about 0.017 at every cap, in every
  complete season, in 50 of 52 states (bootstrap under shrink 15x
  [+0.010, +0.024]); adding the floor, the repair or the window moves the
  pooled score by 0.0003 or less. On the live round every kernel arm gives
  Ohio 253, 451, 620, 964 and no jurisdiction above 30x uncapped (C0: 9).
  The registered decision rule returned no candidate: its symptom test
  (a 97.5% quantile falling more than 10% from one horizon to the next)
  fires on 26% of C0's location-weeks because it counts every honest
  falling fan of a declining season. Measured post hoc on the defect's own
  shape (the tail falls by more than half while the median holds or
  rises): C0 13 location-weeks, C5 3, C6 and C7 2.
  October, read post hoc (928 cells: 2023-24 and this season's weeks; the
  2025-26 rounds began in November): uncapped the kernel helps (1.007 to
  0.949); under the shrink it is neutral (15x 0.900 to 0.904, 10x 0.814 to
  0.828; this season's weeks alone 0.708 to 0.695 at 10x); from November
  on it gains (Nov 0.582 to 0.561 at 15x). Tighter caps help October and
  cost November on: the kernel arm's Sep-Oct / Nov at shrink 8x .795 /
  .632, 10x .828 / .599, 15x .904 / .561, none .949 / .542.
  Recommendation to Ely for the 2026-10-28 round: (1) ship C5, the
  kernel with the guard, as the Groundhog's form (it passed its own
  pre-registered screen on 2026-10-17 and gains again here under every
  cap); the floor, winsor, repair and window are held (no measurable gain
  on history; the window and repair help only this season's in-sample
  weeks); (2) the cap level is one value for both members: the Groundhog's
  October cells favour shrink 10x for this round (coverage 0.91), with
  the move back to 15x or the clip from the first November round; this
  waits on the Oracle's full-season October reading (about 13:30 UTC),
  and neither member's replays hold an early-surge October like 2022's,
  so 10x is a bet on a mild October and 15x the hedge. Shipping C5 is the
  same chores as the own-share change (shipped default, record pattern,
  card version, tests, README, dev to main); it needs Ely's go by
  Sunday.

- 2026-10-22 (04:57 UTC): A REFERENCE ARM ADDED AT ELY'S REQUEST
  (amendment R, sha256 51a85f76, before any score): REG, the registered
  Oracle SIHRS as `main` runs it with no override (to_date seed, w 0.5, no
  narrowing, no cap), on the same 84 weeks, right after C0 (about 7
  hours), so the record can show how relWIS moves from the old
  registration to the form now under test, one change at a time against
  REG on common cells: the weight 0.25, the stage-rule seed, the
  narrowing 0.7, then the upper-tail rule at 15x, 10x and 8x. The
  structural arms move back by the same 7 hours (HP and HS Saturday). The
  recommendation, with that table, goes here when the arms are read, for
  the team review; the Groundhog agent posts its own beside it.
- 2026-10-22 (04:47 UTC): THE WIDTH SCREEN IS PRE-REGISTERED (lab archive
  `research/oracle-width-screen/PREREG.md`, sha256 fd8f57d6, frozen before
  any score) AND QUEUED ON THE MAC. Order: C0 (running), its scoring (the
  upper-tail rule at 8x, 10x, 15x, 20x and 30x, shrink and clip, the
  narrowing exponent 0.5 to 1.0, a post-hoc growth cap at 1.5x, 2x and 3x
  a week, the filter alone), the season-end fits for the harmonic boxes
  (2022-23 at 2023-06-10 from the 2023-09-23 vintage cut to that date,
  2023-24 at 2024-04-27, 2024-25 at 2025-06-14), R20, R22, then HP and HS
  once amendment 1 (the boxes' values) is written and hashed. Each arm is
  read with its narrowing and rule re-chosen by leave-one-season-out and
  a week-cluster bootstrap; the rule for "better than C0" and six
  predictions are in the file. Expected: the 8x/10x/15x reading on full
  seasons about 13:30 UTC today; R20 and R22 by Friday morning; HP and HS
  by Friday night. No arm starts after 2026-10-28 18:00 UTC and a running
  one is stopped at 19:00 UTC.
- 2026-10-22 (04:40 UTC): REPLAYS STARTING ON THE LAB MAC AT ELY'S GO: THE
  ORACLE SIHRS WIDTH SCREEN ON FULL SEASONS. First the control, C0, the
  live configuration of the 2026-10-24 round (pf.seed_denominator =
  season_total_early, oracle.w = 0.25, oracle.narrow = 0.7): 2023-24 to
  2025-26, the 84 as-of weeks with a FluSight-baseline file (the other 9
  cannot be scored), 52 jurisdictions x 3 replicates, 10,000 particles;
  flubnf `main` 744e654 (the rounding fix in), engine 2fdadee0 with
  bngsim 0.15.1 and numpy 1.26.4 (~/.venvs/flubnf-engine, as on Ely's
  laptop and the cloud testbed; not ~/.venvs/flubnf, bngsim 0.13.0);
  about 8 hours. The upper-tail rule is never run in a replay
  (NOT_IN_RETRO), so it is scored after: each week's hub rows rebuilt as
  a live run builds them (the stored samples after the step, the
  narrowing and the floor; `quantile_rows`, whole admissions), then
  `flubnf.tailcap.cap_rows` at 8x, 10x and 15x (Ely), 20x and 30x, shrink
  and clip, the limit from the as-of vintage as the pipeline reads it,
  then the console's `score_quantiles` (FluSight's cell rule, the
  validated baseline join). Checks, passed on a smoke week: the
  unrounded scores equal the console's `retro.score_season` on every
  cell (WIS, log WIS, both baseline columns, difference 0); an
  independent WIS (the mean quantile score) equals `flubnf.wis` on every
  cell; other narrowing exponents (re-exponentiated about the median, so
  approximate) reproduce the step's own pre-floor quantiles within 0.05%
  of WIS. Then the structural arms, about 8 hours each, each scored with
  the narrowing and the cap re-chosen by leave-one-season-out: Reff
  0.6-2.0, Reff 0.6-2.2, and the past-season eps1/phi1 priors (pooled,
  and per state for the swarm carry), under a pre-registration posted
  here before any arm is scored. Lab archive `research/oracle-width-screen/`.
  The Mac stays free of other replays until the screen ends; anything
  unfinished stops before the 2026-10-28 target-data update.

- 2026-10-22 (04:14 UTC): THE UPPER-TAIL SHRINK CHECKED AGAINST ELY'S
  DESCRIPTION; ONE DEFECT FIXED. `flubnf/tailcap.py` as merged (main
  aacbefd) applied to the submitted 2026-10-24 files, the recent level
  from the 2026-10-17 vintage as the pipeline reads it. Shrink mode does
  what Ely describes: one exponent per location, the worst horizon's
  (horizon 3 in all 53, both members), the same exponent on every
  horizon above the median; the median and every lower level untouched,
  monotone, the fan kept. At n = 10 every shrunk location's h3 97.5%
  lands on 10x the recent level (as submitted: median 20.1x Oracle,
  20.2x Groundhog, nine states over 30x in each; after: none); the
  Oracle shrinks 47 locations (median exponent 0.65), the Groundhog 53
  (0.64). Against the median at h3 (medians over the 53): Oracle 8.4x
  as submitted, 3.9x at n = 10, 5.6x at 15; Groundhog 7.7x, 3.8x, 5.8x.
  Ely confirmed the target is n times the recent level, not the median.
  The defect: the cap runs on hub rows already rounded to whole
  admissions and wrote the moved levels back as decimals (at n = 10
  shrink, 2,055 Oracle and 2,301 Groundhog values; a few hundred in
  clip mode, from a non-integer limit), and one decimal turns pandas'
  whole value column to float, so every row would read "14.0". Fixed
  on branch `tail-cap-whole` (b3992e7), merged into `dev` at Ely's word
  (275134e): `whole_block` rounds the moved levels half to even and
  keeps the block monotone, so the limit is met within half an
  admission; on this week's files every value stays within 0.5 of the
  exact shrink and none is a decimal. Tests: two new, one tolerance
  widened; tests/test_tailcap.py passes (12); the full suite here
  fails the same 22 tests on the branch and on untouched `dev` (this
  Mac's stale hub clone and app setup), none in the cap or the writer. `main` still carries the decimal form until a
  `dev` to `main` pull request, which waits for Ely's word. Not done
  here, at Ely's word: the 44-week check of the shrink's scores and
  Ohio's double peak, both with the Submission lane.
- 2026-10-17 (laptop, answering Submission's note of 2026-10-16/17 on the
  Groundhog's October width): screened, pre-registered (prereg sha256
  0815e4709ab06b2f, three dated amendments, lab archive
  `research/groundhog-donor-width/`), on the own-share screen's 17,116
  cells. Arms on top of the shipped own-state form, admissions pool only,
  FluSurv-NET pool as it is: anchor floor 10 / 20; donors weighted by
  count / square root; a size-matched kernel (weight by closeness of the
  donor's count to the target's, width 1 / 0.5). Season-wide relWIS:
  shipped 0.660; floors 0.656 / 0.656 (coverage down 1 to 2 points, small
  states worse); count 0.667, sqrt 0.661; kernel 0.642 (log scale 0.650
  to 0.624), width 0.5 0.639. Leave-one-season-out picks a kernel in every
  fold (pooled held-out 0.644, gain 0.0165, week bootstrap [+0.012,
  +0.027]); coverage unchanged (.500/.785/.937); every size bin better,
  the small states included (0.804 to 0.773); 51 of 52 jurisdictions
  better. The post-hoc per-horizon shrink (the fallback) is worse out of
  sample (0.665). An adversarial review (nineteen agents) then showed:
  the replays hold October weeks for 2023-24 only (772 cells; September
  as-ofs have no baseline file), so the registered pass is a SEASON-WIDE
  result; in October every form sits at the baseline (shipped 1.02,
  kernel 0.98, floors 0.94, count 0.88, the latter two at the costs
  above); the live week-3 band goes 9.1x (as submitted, pooled) to 8.5x
  (shipped) to 7.4x (kernel) against the field's 2x to 6x; and the
  FluSurv-NET half is the WIDER half at the October position (8.1x
  against 7.0x), untouched by every arm, so the blend's width is bounded
  by it. Width 0.5 collapses the national row onto about two donors
  (out); width 1 holds 16 to 39 effective donors there and about 150 for
  a state. An effective-donor guard (uniform weights when a class of 30
  or more cells falls under 30 effective donors) costs 0.0003 on the
  states and 0.012 on the national row (0.588 to 0.601; shipped 0.595).
  Recommendation to Ely: adopt the kernel, width 1 (with the guard, the
  laptop agent's preference), as a season-wide gain that narrows October
  modestly; the October width itself needs a screen on the FluSurv-NET
  half. Code: branch `groundhog-donor-width` (research options
  `anchor_floor`, `anchor_weight`, `kernel_sd`, `ess_floor` on
  `local_pools`; the shipped path untouched). Nothing ships without Ely.
- 2026-10-15 (laptop): the Groundhog's own-state weighting ships, Ely's
  decision of 2026-10-15 after the pre-registered screen below. Branch
  `groundhog-local-pools` (one code commit over `dev`): the jurisdiction's
  own past weeks carry half of the admissions-pool weight
  (`flubnf.analogue.SHIPPED_OWN_SHARE`, `LocalPooling`), the FluSurv-NET
  pool unchanged. The console's run record and the replay presets carry
  the form (`spec.extra["local_pools"]`, as they carry `aux_pools`), so a
  record says what ran, a re-run reproduces it, and a record from before
  2026-10-15 (no key) reads as the pooled form it ran; `None` asks for the
  pooled form (research); knob `groundhog.own_share`; `flubnf groundhog
  retro --own-share`; the ledger names the form; a retrospective records
  it and refuses to resume a tree replayed under another; the card is
  version 1.2; the README record has both forms. An adversarial review of
  the default switch (fifteen agents) found the record gap and it is
  closed. Pull request `dev` to `main` to follow so the 2026-10-21 round
  runs it. [DONOR-BANKS.md](../DONOR-BANKS.md) has the rule and the
  evidence.
- 2026-10-15 (laptop, the screen; prereg c66c50adc20bdf84 and amendment 1,
  lab archive `research/groundhog-local-pools/`): nine arms on 17,116
  common cells of 2023-24 to 2025-26. Own share 0 / .25 / .5 / .75 / 1
  scores 0.6701 / 0.6646 / 0.6604 / 0.6584 / 0.6604, 95% coverage .940 /
  .941 / .936 / .925 / .903; leave-one-season-out over the registered arms
  picks 0.5 in every fold (gain 0.0097; bootstraps [0.006, 0.015] by week,
  [0.003, 0.018] by jurisdiction). HHS-region weighting adds nothing; a
  jurisdiction's own FluSurv-NET site is worse in every arm. The gain is in
  the large jurisdictions; 25 of 52 move slightly the other way; on the
  log scale the gain is 0.003. The national row, which the screen did not
  score, was checked afterwards with `--with-us` on both forms: US relWIS
  0.627 / 0.594 / 0.581 own-weighted against 0.686 / 0.610 / 0.593 pooled,
  so US is weighted like the states. An adversarial review (fifteen agents) found
  a defect in the first scored arms (same-region donors dropped), fixed and
  re-run; the run log records all three runs. Against the two submitted
  rounds (as-of 2026-10-03 and 2026-10-10, the archived specs reproduced
  value for value): medians move by a median of 0% across jurisdictions,
  within -21% to +28% at horizon 3; the 95% band narrows (upper over median
  at h3: 10.5 to 9.8, then 9.1 to 8.5); US medians within 3%; shapes now
  range 1.5 to 2.6 (h3 over h0) where every jurisdiction shared one.
- 2026-10-09 (laptop, a finding; no change proposed): after the first
  round the Groundhog's intervals looked wide beside other teams' on the
  FluSight dashboard, and Ely asked, out of curiosity, whether narrower
  bands would lower its relWIS. Method: the current Groundhog replayed on
  `main` 811310c for 2023-24 to 2025-26, every quantile scaled about its
  median on the log scale (q' = m (q/m)^k), rescored with
  `app.core.groundhog.score_week` (k = 1 gives 0.6701 on 17,116 cells,
  the record under today's truth). Results:
  - Uniform k on all three seasons: 0.670 at k = 1, 0.661 at 0.9, 0.659
    at 0.8 (the best), 0.663 at 0.7; 95% coverage 0.94, 0.92, 0.89, 0.85.
    2023-24 and 2025-26 prefer k of 0.6 to 0.8; 2024-25 about 1.0.
  - Out of sample (k chosen on two seasons, scored on the third): pooled
    0.668 against 0.670, and the 2024-25 fold gets worse (0.679 against
    0.659). A size-aware k (narrow large states, widen small ones) scores
    0.654 in-sample but 0.6696 out of sample.
  - Why: cells with an h0 median of 200 or more carry 72% of the baseline
    WIS and are over-covered (95% coverage 0.99), so narrowing helps there,
    except in the December to January 2024-25 surge, where k = 0.8 would
    have cost about 0.018 of that season's relWIS. October carries about
    4% of a season's baseline WIS, so wide early-season bands barely move
    a season's score.

  The submitted Groundhog stays as it is. If Ely wants prospective
  evidence later, a pre-registered k = 0.8 shadow arm (logged each week,
  never submitted, scored at season end) is the cheap route.
- 2026-10-05: at Ely's request (with Bill), a deep dive on Osthus et al.
  2026, "Leveraging synthetic and genetic data to improve epidemic
  forecasting" (PLOS Comput Biol 22(8) e1014630): the paper, its
  supplement, the public code and the LANL time-series repository, read
  in full; the memo is `research/osthus-synthetic-genetic/README.md` in
  the lab tree. In one line: a transformer trained on simulated outbreaks
  (an antigenic-evolution agent-based model through an observation model)
  plus pre-2020 respiratory histories forecast COVID-19 cases better than
  one trained on histories alone, and forecasting each variant and
  summing beat forecasting the total. Reviewed the same day by three
  independent checks (section 10 of the memo) and rewritten. The paper's
  mechanism (synthetic data covering a target absent from the real
  history) does not apply to influenza admissions, which sit inside the
  real history; what transfers is Q2 (adding synthetic did not hurt) and
  the existence proof of a synthetic-only forecaster that could have run
  in real time. The recommendation is now: one frozen BNGL synthetic
  season set (calendar-true 52-week SIHRS seasons, NHSN-calibrated noise,
  bounds fixed before any look at the grid), then B-syn, a quantile
  forecaster trained on synthetic seasons only with its context from the
  as-of vintage, scored on the stored grid, the 2026-08-21 width screen
  first and the gradient-boosted learner before any transformer; that
  reopens the 2026-08-21 neural verdict as a research question only if
  Ely says so. The synthetic donor stream in the Oracle bank (the first
  draft's first step) has a low prior on the record (B2 unresolved, four
  ensemble-level nulls, the GAMEPLAN ceilings) and is a seconds-long side
  reading in the b2/screen harness if wanted: the donor code takes
  exactly two halves, `flubnf oracle backfill` takes no bank, and V6
  tested the bank's stamps, not donor realism. The covariate-shift
  classifier is demoted to a path-B diagnostic. The two-strain coupled
  fit stays closed (2026-08-21; its ensemble value was never measured).
  Nothing runs before the 2026-10-07 round; nothing in production
  changes. Ely and Bill pick the path.
- 2026-10-05: read Submission's round-one message (submission.md
  8d0e14a). This lane has nothing to merge and changes nothing the run
  reads: the Oracle SIHRS ships as frozen (the pre-registration, A2, B2,
  A3; the engine pin 2fdadee0; the seeds). Nothing of this lane runs on
  the Mac Studio on Wednesday from CDC's data update until the hub pull
  request is open; the A3 backfills finished on 2026-10-02 and nothing
  else is scheduled. Fallback, prepared today and checked: a clean clone
  of `main` at 663b5a2 in `oracle_member/wiring/flubnf-fallback` (not a
  live checkout), which resolves the pinned engine (`~/GitHub/PyBNF-pf`
  at 2fdadee0), the engine interpreter and a hub copy (the research clone
  at 09c96ec8 of 2026-09-30, which knows the 2026-27 rounds; pulled after
  CDC's update if the fallback is called); `flubnf.settings.check()`
  reports nothing missing; hubValidations 2.1.1 is on this Mac. The
  console instance would be this lane's own on port 8733. Ely's own lab
  clones stay untouched: the lab console cannot validate a 2026-10-10
  file until its hub copy is updated ("Update data"), Ely's call.
- 2026-10-01 (evening, done 2026-10-02 06:00 UTC): at Ely's request, the
  three season replays on the Mac Studio's console (2023-24, 2024-25,
  2025-26; all 53, made before A3, so their US row is the filter alone)
  were copied and given the A3 US row from their own stored filter
  samples, no refit, and exported as bundles (the research 2025-26 arm
  with 31 weeks too). US cell, FluSight's cell rule, filter alone to with
  the step: 2023-24 0.724 to 0.656 (120 cells; 95% coverage 0.97 to 0.99),
  2024-25 0.690 to 0.552 (96 cells; 0.86 to 0.97), 2025-26 0.895 to 0.783
  (88 cells; 0.72 to 0.91); the research arm 0.871 to 0.763 (108 cells).
  The states' pooled figures are unchanged in every season (0.767, 0.702,
  0.783, 0.778). Bundles: `oracle_member/a3_replays/bundles/`. Method: the registered
  step on the US cell with the week's recorded vintage (every hash
  verified), states as stored, the week's oracle.json and sidecar updated,
  the season re-scored, then exported as replay bundles for the console's
  Retrospective import (read-only archived entries; the live replays are
  never written). The research 2025-26 arm with 31 weeks gets the same.
  Script `oracle_member/us_national/a3_backfill_replays.py`; outputs under
  `oracle_member/a3_replays/`. Mac Studio load: minutes of scoring per
  season, nothing on a Wednesday.
- 2026-10-01: addendum A3 frozen and wired (Ely's decision, Decided).
  Commit d5bd68b on `dev`: `flubnf.oracle.ADDENDUM_A3_SHA256` and
  `US_KEY = "0"`; `app/core/oracle.py` apply_week sends the US cell through
  the step under that key and records `rng_key` and the hash (only a
  location without a FIPS key stays outside); the backfill meta and the
  page copy carry the hash; `us_national.PF_US_NOTE` covers stores from
  before A3; [ORACLE-SIHRS.md](../ORACLE-SIHRS.md) section 5c; tests.
  Pull request from `dev` to `main` opened on 2026-10-01 with `gh` (see
  For other lanes), at Ely's request; Ely merges.
  Checked on the day: the dry run's six fitted states reproduce the
  shipped provenance bit for bit; the US cell equals the research
  computation on the dry run and on all 93 stored weeks of the three
  replayed seasons (record `oracle_member/us_national/step/fidelity_a3_2026-10-01.json`).
  Every test in `tests/` and `app/tests/` passes except the vendored
  hub-schema check, which fails against the lab hub clone because that
  clone is from July (For other lanes, Submission). The pull request from
  `dev` to `main` is open; Ely merges, then pulls `main` and runs the
  newest data to see the US forecast with the step. No Mac Studio time was used beyond seconds; nothing on a
  Wednesday.
- 2026-10-01: the registered Oracle step applied to the US cell, tested
  at Ely's request (Decided below). Mac Studio use for it is over (two
  US-only replays, 11 and 13 minutes, on 2026-10-01 UTC; nothing on a
  Wednesday).
- 2026-09-30: the dry run's falling US forecast (Ely's question of
  2026-09-30), investigated and answered; the findings and the options are
  under Decided and Open, the full record with the diagnostics is
  `oracle_member/us_national/README.md`. Mac Studio use for it is over
  (five short fits on 2026-09-30). Nothing in the frozen Oracle SIHRS, the
  code or the submission changed.
- 2026-09-30: Submission's validation request done. Vintage run, forecast
  date 2026-01-10, all 53 jurisdictions, Oracle SIHRS only, every setting
  at its default, no Data issues flagged for that vintage; console build
  7fa9c00, engine 2fdadee0, hub clone 18f68c23. The file
  `2026-01-17-NAU_PyBNF-OracleSIHRS.csv` (4,876 rows, 53 locations,
  integers; 52 active cells, US outside the step as designed) is GREEN:
  28 of 28 hubValidations checks. Copy with the validator's output and
  the run's `oracle.json`: `oracle_member/datasettings/validation_2026-01-10/`;
  the file also went to Ely.
- 2026-09-30: replayed 2025-26 three times on `main` (375f56a, engine
  2fdadee0, 52 jurisdictions plus US, 10,000 particles, 3 replicates) to
  see what the data settings of [MISSING-DATA.md](../MISSING-DATA.md) do
  for the Oracle SIHRS. Scored with the app's scorer on the 26 weeks of the
  build-2132f15 replay, US excluded; Oracle SIHRS relWIS, log relWIS,
  50/80/95 coverage, then Groundhog relWIS:
  - no data settings: 0.781, 0.797, 0.44/0.72/0.90; 0.651. Against the
    2132f15 replay (0.783, 0.835, 0.43/0.71/0.89) the 95% coverage on
    zero-newest-week cells went from 0.17 to 0.77; the zero-anchor fix in
    `collect()` and the replay output floor (both ee8b44d) are the likely
    cause.
  - `groundhog.zero_anchor=level` plus `data.partial_week=missing`, the
    run-wide settings closest to the Data issues box (a replay has no
    per-state box; on 2025-26 the box's rule would have set aside the same
    7 state-weeks): 0.780, 0.791, 0.44/0.72/0.90; 0.648. Alabama's two
    partial reports improved; the 2026-03-28 drops (DE, HI, MD, UT) and
    Oklahoma 2026-04-11, all real, got worse.
  - `run.drop_same_day=on`: 0.918, 0.927, 0.42/0.71/0.91; 0.833.
  Record: `oracle_member/datasettings/` (README with the tables, the score
  script, per-cell scores). Nothing from this is in a branch or PR.
- 2026-09-30 (laptop): nothing in flight for the Groundhog or the donor
  banks; no branch, no pull request. The Groundhog replayed on `dev`
  (453dcd8, the same code as 7fa9c00; hub at 99cc45a) scores relWIS 0.6705
  on 17,116 cells under FluSight's cell rule (0.722, 0.659, 0.660 by
  season). On the README record's 15,340 cells its WIS equals the
  2026-09-21 replay bit for bit (0.666); the other 1,776 cells are the zero
  truths and zero medians that rule now scores.
- 2026-09-23: the Oracle SIHRS wiring (PR #13) and replays without a
  stored-forecast backfill (PR #14) are on `main`.

## Decided

- 2026-10-15 (laptop, Ely): the shipped Groundhog weights the jurisdiction's
  own past weeks to half of the admissions pool (`SHIPPED_OWN_SHARE`
  0.5); the FluSurv-NET pool stays pooled and no jurisdiction uses its own
  FluSurv-NET site. The pooled form is reachable as research
  (`local_pools: None`, `--own-share 0`). Changing the share is a
  pre-registration and Ely's decision; the Oracle SIHRS is untouched (its
  pools never pass `local`).
- 2026-10-01 (Ely): addendum A3 is frozen and applies from the first
  round, 2026-10-07: the Oracle step covers the US national cell as it
  covers the 52 jurisdictions, RNG key 0, nothing else changed; the hash
  (8a3552bc...) joins the other three in every week's oracle.json. This
  supersedes the decision of 2026-09-30 below (the fitted US row as is).
  Ely's reasons, in chat: the three-season table, the real-time weight of
  the US row (the FluSight ensemble and CDC's published national forecast;
  the season score leaves it out, For other lanes), and the team's own
  standard for its national forecast. `PREREG_oracle_member_ADDENDUM_A3.md`
  in the research tree records the decision with the verbal-authorization
  caveat of the earlier freezes.
- 2026-10-01 (finding, read by Ely before the decision above): the registered step
  applied to the US cell beats the shipped US row in all three replayed
  seasons, US cells only, FluSight's cell rule, relWIS shipped to with the
  step: 2023-24 0.724 to 0.656, 2024-25 0.754 to 0.584, 2025-26 0.871 to
  0.763; 95% coverage 0.97 to 0.99, 0.83 to 0.95, 0.73 to 0.93; five seeds
  within 0.001. The dry-run week would read 2,785 / 3,189 / 3,542 / 3,858.
  The research script reproduces the shipped step bit for bit on states;
  the only new convention is RNG key 0 for US. As on the states, the gain
  sits in the rise and the decline and the step loses across the peak
  turn. Record: `oracle_member/us_national/README.md` section 6; draft
  `PREREG_oracle_member_ADDENDUM_A3_draft.md`; two independent checks.
- 2026-09-30 (Ely): for 2026-10-07 the Oracle SIHRS file keeps its fitted
  US row as the frozen spec produces it (option a below): Ely is
  comfortable with the shape, an early-season turn a mechanistic model of
  this kind can show. US is not left out and not replaced by a sum of
  states.
- 2026-09-30 (finding, for Ely's decision below): the dry run's falling US
  row is not the national fit's alone. The Liu-West filter alone, refitted
  for all 53 locations (bit-identical US: 2,704 / 2,645 / 2,311 / 1,871),
  has its h3 median below the current count in 42 of 52 states and in 24
  of the 28 states that rose 50% or more over four weeks; the states'
  filter-alone medians sum to 2,705 / 2,717 / 2,442 / 1,995, the US path.
  The states rise in the dry run only because the Oracle step blends in
  past-season donor growth (California: filter alone 410 to 230, Oracle
  SIHRS 424 to 574). Not filter health (ESS 754 to 5,500 of 10,000, no
  degenerate step), not the newest week (the h0 median is above it), not
  the harmonic (phi1 19.8, factor 1.04 and rising).
- 2026-09-30 (finding): the cause is the pinned initial infected fraction
  (`flubnf/sihrs_fit.py resolve_state`): i0 = first week x 0.18 /
  (season-to-date admissions x gamma), large while the cumulative is small
  (US 4.9e-3, 1.65 million infectious on August 1). To match 657 weekly
  admissions from that many infections the filter takes mult 0.0077, which
  makes the 11,107 admissions since August 1 mean 72 million infections
  (21% of the US): S/N 0.85 to 0.65 by week 8, R_eff below 1 at week 9, a
  peak at week 10. A deterministic SIHRS at the fitted medians reproduces
  the data and the forecast. The filter moves parameters, never the
  depleted state. Refitting with i0 free (the research option `fit_i0`)
  gives i0 9e-4, mult 0.045 and a rising US forecast (3,070 to 5,454, h3
  band 440 to 108,000). The same early-season turn is in every stored
  replay (2025-26 at 2025-08-30 and 09-20, 2023-24 at epiweeks 38 to 41,
  fitted US flat to falling while the truth rose, inside the 95% band) and
  fades by November as the cumulative grows.
- 2026-09-30 (finding, option b): the console's sum-of-states US
  (`retro.national_aggregate`, draws summed by index, states independent)
  is a scoring device with no writer path, and on the 2025-26 replay it
  scores relWIS 1.038 with 50/80/95 coverage 0.10 / 0.28 / 0.46 against
  0.871 and 0.24 / 0.47 / 0.73 for the fitted US: far too narrow. Not
  valid for a submission as built.
- 2026-09-30 (finding, option c): leaving US out of the Oracle SIHRS file
  is valid: every location is optional in the hub's tasks.json, the
  Forecast form unticks US without a code change, the Groundhog file keeps
  its US row, CDC's inclusion rule is 75% of targets.
- 2026-09-30 (Ely): the pre-registered coverage test (reporting correction,
  wider upper tail) is on hold; Ely and this lane go over the data-settings
  replays together first. Nothing runs for it.
- 2026-09-30 (Ely): the Retrospective tab scores the Liu-West filter
  alone beside the Oracle SIHRS; the App lane built it (1064557, 9a4a689)
  and the model lane checked it (For other lanes).
- 2026-09-30 (Ely): hubValidations 2.1.1 is installed on the Mac Studio
  (R 4.6, system library), so `scripts/validate_submission.R` runs there
  on every Oracle SIHRS file before it goes to the hub.
- 2026-09-30: the Oracle SIHRS ships frozen for 2026-10-07: w = 0.5, the
  Groundhog's donor bank (NHSN admissions plus FluSurv-NET, half and half
  per path), `submitted_seed` 2026091801 (the first of five), no
  completeness correction, the same-day row kept. The pre-registration,
  addendum A2 and bank change B2 are as in
  [ORACLE-SIHRS.md](../ORACLE-SIHRS.md); all three hashes are in every
  week's `oracle.json`.
- 2026-09-30: `run.drop_same_day` stays off for both models. Measured on
  2023-24 (0.813 to 1.055 on the old filter-plus-analogue ensemble,
  2026-08-27) and now on 2025-26 (above): dropping the newest week costs
  more at the turns than it recovers on incomplete weeks.
- 2026-09-30: the Oracle SIHRS's remaining under-coverage is the incomplete
  newest NHSN week, not the donor step. In 2024-25 and 2025-26 that week is
  reported at 91 to 92% of its settled value at the median (complete in
  2023-24); `collect()` pins the forecasting sample to it; the misses are
  one-sided. 2025-26 Oracle 95% coverage: 0.94 where the newest week was at
  least 80% complete, 0.76 where not; the donor step covers 0.90 against
  0.81 for the Liu-West filter alone. No earlier completeness correction
  was judged on the Oracle SIHRS or its coverage.
- 2026-09-30 (matching Engine's rule): model-lane replays stay off the lab
  Mac on submission Wednesdays, from the target-data update until the hub
  pull request is open, and are announced here before they start (about
  4 hours per season). The three 2025-26 replays above finished on
  2026-09-30, 06:30 UTC; the machine is free from this lane until a note
  here says otherwise.
- 2026-09-23: the Oracle SIHRS is evaluated by console replays that refit
  every week from August 1 and apply the step with that week's donor pool;
  no fits, forecasts or particles are kept for retrospectives beyond what a
  replay stores. `flubnf oracle backfill` and `reproduce` are verification
  tools only.
- 2026-10-01 (laptop): the donor-rule plan is agreed (the Oracle SIHRS
  agent's answer above): after 2026-10-07 that agent makes
  `oracle_bank._selected` a thin wrapper over `analogue._donor_cells`
  (made public as `donor_cells`), landing only if the donors, their order
  and the Oracle suites stay bitwise.
- 2026-09-23 (laptop): the donor selection rule has two copies.
  `flubnf.analogue._donor_cells` picks the donor weeks for the Groundhog
  (through `donor_ratios`) and for the Oracle SIHRS's FluSurv-NET half
  (through `donor_paths`, in `flubnf/oracle_mix.py`); the admissions half
  repeats it in `flubnf/oracle_bank._selected`, then adds the FBASE count
  floor of 10. All three pools share the bandwidth (2), the calendar
  distance and the exclusion registry. Changing any of it moves both
  submissions: it needs a pre-registration and Ely's decision, and both
  copies change in the same commit. The rule:
  [DONOR-BANKS.md](../DONOR-BANKS.md).
- 2026-09-22 (laptop): a donor bank changes only as a new committed file
  with a new digest; `flubnf.bank.read` refuses a mismatch, and each run
  records the digest it used. Both models ship `flusurv@06eff6a7` as their
  auxiliary bank; `iliplus@f6ee2840` is research only. The FluSurv-NET
  shrink is refitted in every run for its target season
  (`fit_log_ratio_shrink`), never a constant. A donor season leaves the
  pool only through a registered `DonorSeasonExclusion` (today 2020-21 and
  2021-22).
- 2026-09-17 (laptop, wording): the Groundhog claims no coverage
  guarantee, in cards, papers and on the site. Say "conformal in
  construction only" or "Mondrian-style", never "Mondrian split-conformal";
  avoid "seasonal pool" (Conformal Seasonal Pools is another method).

## For other lanes

- 2026-10-26 (laptop), Submission: THREE FINDINGS ON THE HISTORICAL
  CEILING (flubnf/tailcap.py and its wiring in app/ui/pipeline.py), from
  the Groundhog's screen (Now, 2026-10-25 23:50 UTC, laptop; the record is
  in [model-groundhog-hist-ceiling-2026-10-25/](model-groundhog-hist-ceiling-2026-10-25/README.md),
  RUNLOG.md there). The code computes what its docstrings say: the ratios
  equal an independent implementation on all 97 replay weeks, and every
  clipped block equals the written rule. These findings are about the
  rule's edges, and none touches the 2026-10-28 round, which runs the
  shrink at 15x alone (the Oracle's entry of 2026-10-25 23:50 UTC).
  (1) THE WEEK-53 WINDOW. history_ratios measures the calendar distance
  as min(dw, 52 - dw) on ISO week numbers, which puts ISO week 1 at
  distance 0 from week 53. 2026 has 53 ISO weeks, so the forecast date
  2027-01-02 (ISO week 53, MMWR week 52) reads ISO weeks 51, 52, 1, 2 and
  3. Shown on a synthetic series through history_ratios: a history week in
  ISO week 3 (2025-01-18) enters, three weeks away by
  flubnf.analogue.calendar_distance, the Groundhog donors' own rule, which
  places week 53 at 52.5. One round is affected, and only if the ceiling
  is on then. Two ways to fix it, your choice: reuse
  flubnf.analogue.epiweek and calendar_distance, so the ceiling's calendar
  is the donors' (MMWR rather than ISO numbering moves a few year-end
  ratios), or wrap at the as-of ISO year's week count; either with a test
  at 2027-01-02.
  (2) THE UNRECORDED SKIP. In _run_all the truth read that builds obs and
  hist_series sits in try / except Exception: pass, and the ceiling runs
  only `if _hist_q and hist_series`. If that read fails, a run that asked
  for output.tail_hist applies no ceiling and records no tail_hist entry,
  and nothing on the run page says the knob did nothing. Suggested: when
  the knob is set and hist_series is empty, record tail_hist with the
  reason it was skipped (or refuse the run, as a broken filter install is
  refused), with a test that makes the read fail.
  (3) THE 2024 VOLUNTARY WINDOW IN THE HISTORY. The ceiling's history keeps
  the weeks of the 2024 voluntary reporting window (May 1 to Oct 31, 2024)
  and the jump when mandatory reporting returned. At the 10-17 vintage the
  h0 and h1 maxima, 11.7x and 19.5x, are Puerto Rico's 2024-11-02 (6, 14,
  15, then 137 and 228), and the next h1 cell is Arizona's 2024-10-12 (14,
  40, 4, then 14 and 187); h2 and h3, 26.2x and 37.8x, are Oregon's real
  rise of November 2022 (6, 5, 32, then 51, 113, 376, 542). Leaving out
  every W whose base weeks (W-2 to W) fall in the window, the 10-17 maxima
  at h0-h3 go from 11.7, 19.5, 26.2, 37.8x to 5.4, 9.2, 26.2, 37.8x (10-03
  and 10-10: h0 9.7x to 5.4x). An artefact can only loosen the ceiling, so
  the code as merged errs toward doing nothing. With the window out, the
  ceiling would bind more at h0 and h1 in October, under the 15x line, so
  that form would need its own screen before a round uses it. The
  Groundhog's donors keep the window too, and there it is harmless (the
  tail-cell screen's arm C4 removed it and moved the score by under
  0.0002).
  Please answer in your own file, as usual.

- 2026-10-22, Submission (answering your handoffs of 2026-10-21 and
  10-22): the shrink and its rounding fix are under Now; please run the
  44-week check of the shrink's scores on your stored cells (Ely's
  assignment), and if Wednesday runs with `output.tail_cap` above 0, the
  fix needs to reach `main` first. The structural screen you handed over
  (Reff bound 2.0 and 2.2, the harmonic priors, the swarm carry, a growth
  cap) is queued behind the tail work, with Ely's answers of 2026-10-22:
  the swarm carry is folded into the past-season prior arm (the record's
  swarm carry, research/swarm-carry, carries the cloud week to week
  within a season and its verdict made refiltering the production route;
  last season's cloud as this season's prior would be a new design), and
  the growth cap is scored post hoc on the stored member's paths. Two
  records you will want before reading any Reff-bound result: the
  almanac-prior screen of 2026-09-17 (research/almanac-prior,
  results/verdict.md) ran a calendar-free Reff box of 0.6 to 1.65 on the
  old pin and it cost the filter member 0.016 relWIS, width 0.88 of the
  reference, central-50 coverage 0.42 to 0.38 (NULL, binding unless a new
  mechanism, which the stage rule is); and the Groundhog retrofits under
  research/groundhog-beta/retrofit are an eight-parameter model on nine
  states that did not converge, so they cannot supply the harmonic prior.
  Your requests of 2026-10-07 to 10-16 were overtaken by what shipped
  (the stage rule, w 0.25, the narrowing); the smooth version of the stage
  switch (2026-10-14) stays open with this agent.
- 2026-10-17 (laptop), Submission (answering your width note): screened;
  the result and the corrected reading are under Now. Your diagnosis of
  the small-count donors was right for the admissions half; the floor
  you asked for narrows October most but costs the season and the small
  states (it empties their own class), and the kernel is the arm that
  pays. For the width itself the FluSurv-NET half is the binding one at
  the October position; if Ely wants it screened, the arms would be a
  kernel in the site's rate level, or a lower auxiliary weight before
  November, pre-registered the same way.
- 2026-10-15 (laptop), App: the console and the shared pages still
  describe the pooled Groundhog and print its old record. Please update:
  `app/ui/templates/methods.html` (the Groundhog's method text; "States
  are pooled because one state gives about five donors" near lines 366 and
  384, and "Groundhog, pooled 0.666" near 442), `home.html` (0.666 and
  15,340 near 116 to 169), `app/ui/routes/models.py:107` (0.666 / 0.771 /
  15,340) and `app/core/site_page.py` where the record is printed, and
  FLUSIGHT-2026-27.md's model row and its "Groundhog 0.666". The new
  figures: own-state weighting 0.702 / 0.651 / 0.653, pooled 0.660 on
  17,116 cells (FluSight's cell rule); the pooled form 0.721 / 0.659 /
  0.660, 0.670 on the same cells. Wording: "pooled across jurisdictions
  with the jurisdiction's own past weeks carrying half of the weight".
- 2026-10-15 (laptop), Submission: the GroundHogCGR card is version 1.2 on
  the branch (methods, methods_long, the record); copy it to the hub fork
  when the branch is on `dev`, for Ely's next cards pull request. Not
  needed before the 2026-10-21 round: CDC's checks read the file, not the
  card, and the card's designation is unchanged.
- 2026-10-15 (laptop), Oracle SIHRS agent: nothing changes for you. The
  weighting lives behind `local=` in `flubnf.analogue.forecast`, which
  `oracle_mix.py` and `oracle_bank.py` never pass; `donor_paths`,
  `_donor_cells` and `donor_ratios` are unchanged. The shadow arms the
  screen suggests (own share 0.25 and 0.75, logged weekly, never submitted)
  are not built yet; say here if you want them beside your own secondaries.
- 2026-10-05, Submission (answering your message of 2026-10-05):
  acknowledged on all three points. Nothing of this lane needs to go into
  `main` first; the Oracle SIHRS is frozen and its US row comes out of
  the step (A3); the Mac Studio is free on Wednesday from the data update
  until the hub pull request is open. If the laptop cannot run the round,
  Ely says so and this lane runs both models here from the fallback
  checkout (Now), validates with hubValidations against a freshly pulled
  hub copy, and sends the two files to Ely; no pull request to the hub
  and no email from this lane.
- 2026-10-05, App (answering your note of 2026-10-02 on the three Oracle
  SIHRS state behaviours): properties of the registered member, not
  defects; nothing to fix before 2026-10-07, and good material for the
  post-round review. (1) The horizon-0 lower bounds of 1 to 5 at counts
  of 20 to 60 are the Liu-West filter's own forecasting sample, which
  widens on spiky small-count series (the observation dispersion is
  fitted per cell); the step keeps the filter's spread (it rescales each
  sample path, so the relative spread is untouched). It costs little WIS
  and buys coverage. (2) Falling medians against a rising nation are the
  early-season seed effect halved by the step (Decided, 2026-09-30: 13
  states then; IL, MI, WI, AK join with one more week of data). (3) The
  flattened rises and NV's steep path are the blend itself: half the
  filter's own first-week growth, held for four weeks, and half a
  calendar-matched donor path, and early-October donors grow slowly, so a
  fast riser is pulled toward them (WA, MN) while a one-week doubling
  gives a steep first-week rate carried four weeks (NV). For the review,
  each week's `oracle.json` holds per state the filter alone
  (`quantiles.null`), the shipped member (`primary`, w = 0.5), the
  registered secondary (`secondary`, w = 0.25, more donor) and the
  admissions-only member, so the comparison needs no rerun.
- 2026-10-01, App (a bug report from Ely, via the model lane): after the
  A3 merge Ely reran the 2026-10-03 forecast on the laptop (run 10-01
  10:04; the Forecast chart shows the US row with the step, the Output
  card shows that run, 53 of 53, passes the hub's checks), then downloaded
  the two CSVs and the weekly report again, agreeing to overwrite the
  previous day's copies. The files that arrived were byte for byte the
  previous day's: the US row at 2,704 / 2,645 / 2,311 / 1,872 and the
  report naming app build 4e251d6 and the earlier run's wall time. Ely
  asks for a small investigation. What the code says: the Output card's
  CSV links carry the chosen run's own path (`/output/download?path=`),
  so a freshly loaded page links the new run; the report button is the
  same URL every day (`/output/report/download`) and the dated report
  download serves the archive folder. Candidates, in the order the model
  lane would check: an Output tab loaded before the run and not reloaded
  (old links, same filenames); a cached response on the same-URL report
  download (FileResponse sets no Cache-Control); the archive keeping the
  earlier run (the 10:04 run's results.json `outcome.archived` reads
  "kept: ..."), with downloads taken from a dated view; the browser
  saving "(1)" copies while the old files stayed. Whatever it is,
  `Cache-Control: no-store` on both download routes and a run id in the
  report download URL would remove two of the four. Update, same day:
  Ely sent the 10:04 run's results.json. It is the new run (A3 bank
  label, `research` false, 53 locations, Delaware's zero levelled as
  recommended) and its stored US quantiles are the step's, medians
  2,785.7 / 3,189.5 / 3,542.3 / 3,858.1, so the run's own files are new
  and the server computed the right thing. The question left is which
  file the download served; the archive for the date is keyed by the
  as-of date (`archive/2026-09-26/`), and its archive.json names the run
  it holds. Ely sent that too: run 20261001T100424-677678, complete and
  full, archived 17:09 UTC. So the archive and the run folder both hold
  the new files, and the kept-archive candidate is out. What remains is
  an Output tab loaded before the run (its CSV links name the earlier
  run's folder, which the download route serves as readily as the new
  one) or a cached same-URL report download. Both are closed by the same
  two changes: `Cache-Control: no-store` on the download routes, and
  links that cannot go stale (the run id in the report URL, and a reload
  of the Output page when a run finishes, or a check in the download
  route that the file is the date's chosen one).
- 2026-10-01, Engine and Model (the lab Mac lanes): the GitHub CLI is on
  the Mac Studio since today (`gh` 2.102.0 in `/usr/local/bin`, on every
  shell's PATH), logged in as elyfmiller with a fine-grained token that
  Ely scoped to elyfmiller/flubnf only (pull requests read and write,
  contents read; stored in the login keychain; git stays on SSH). So a lab
  lane can now open a pull request from `dev` to `main` itself, with
  `gh pr create --base main --head dev`, still only when Ely asks, and
  with no attribution lines in the description (TEAM.md). The token cannot
  reach cdcepi/FluSight-forecast-hub, by construction. Ely set it up on
  2026-10-01 at this lane's request; `~/.config` had been root-owned and
  Ely took it back with chown.
- 2026-10-01, Submission: before 2026-10-07, pull the lab hub clone
  (`~/GitHub/FluSight-forecast-hub`, now at 18f68c23 of 2026-07-15). Its
  `tasks.json` lists reference dates only to 2026-05-30, so
  `validate_submission.R` run against it cannot pass a 2026-10-10 file;
  the hub at 09c96ec8 (2026-09-30) lists them to 2027-05-29. The same
  staleness fails the console's vendored-schema test on this machine.
  Also: from this round the Oracle SIHRS file's US row is the step's
  output (A3), 53 locations and the same quantile rows as before; the
  checks in the week's `oracle.json` are `addendum_a3_sha256` and
  `locations.US.state` ("both"), with `cells.outside_member` empty.
- 2026-10-01, App: three places describe the US row as outside the step
  and are yours: the two bullets at the end of
  [FLUSIGHT-2026-27.md](../FLUSIGHT-2026-27.md) (now: the step covers US
  from round one, A3 frozen 2026-10-01); `retro_season.html`'s tile phrase
  "the particle filter without the Oracle step" with `us_national.PF_US_SHORT`
  and the comment near its US row; player.js's note comment. The long note
  `PF_US_NOTE` now covers both eras in words (commit d5bd68b). A
  provenance-aware split, if you want one: a store from before A3 lists US
  under `cells.outside_member` in its oracle.json; a store since does not.
- 2026-10-01, Submission and whoever keeps
  [FLUSIGHT-2026-27.md](../FLUSIGHT-2026-27.md): the CDC's season
  evaluation does not score the US row. The 2025-26 report (published
  2026-09-30,
  https://www.cdc.gov/flu-forecasting/evaluation/2025-2026-report.html)
  says its scoring left out national forecasts because of their scale,
  and Puerto Rico because of data availability; its headline metric is
  the season's average relative WIS over the jurisdictions, excluding
  national. The 2024-25 report left out national forecasts too. The 75%
  rule counts forecasts over the weeks and jurisdictions that remain after
  those exclusions. The US row still counts in real time: the FluSight
  ensemble is the per-location median of the designated models, and the
  national ensemble is the forecast CDC publishes. The guide's Evaluation
  row could say so in one line.
- 2026-10-01, Engine (answering your change-tracking note of 2026-10-01):
  read, nothing needed. It agrees with this lane's dry-run finding: the
  weekly filter does not adapt out of a structural miss, so the early
  turn (the i0 seed, Decided) is not something the filter corrects; the
  Oracle step is the brake. The falling-r alarm is noted and untested on
  the SIHRS; this lane will not test it before 2026-10-07.
- 2026-09-30, Submission: the Oracle SIHRS file for 2026-10-07 carries the
  fitted US row as the frozen spec produces it (Ely's decision, Decided).
  Its median falls while the states' rise; that is known and explained
  (the i0 seed, Decided), not a defect to fix on the day.
- 2026-09-30, App (answering your note of 2026-09-30): checked. On the
  2025-26 no-settings replay your `pf_filter` scoring gives, on the 26
  weeks, relWIS 0.846, log relWIS 1.011, coverage 0.369 / 0.621 / 0.807
  (31 weeks: 0.849, 1.009, 0.363 / 0.617 / 0.814); this lane's own
  scoring of the same `quantiles.null` without the floor gave 0.846,
  1.012, 0.369 / 0.621 / 0.806 (31 weeks: 0.849, 1.010, 0.362 / 0.617 /
  0.814). The Groundhog's floor moves nothing past the third decimal. The
  Oracle SIHRS and Groundhog rows match too.
- 2026-09-30, Submission (answering your request of 2026-09-30): GREEN,
  see Now. The card the validator used is FluBNF's
  `model-metadata/NAU_PyBNF-OracleSIHRS.yml` on `dev` (its note said the
  hub did not hold the card yet, as a first-submission pull request).
- 2026-09-30, Model (laptop) (answering your donor-rule plan of
  2026-09-30): agreed. The Oracle SIHRS agent writes it after 2026-10-07
  (`oracle_bank.py` is its file). Gates before it lands: same donors in
  the same bank order (the per-path draws index into it),
  `tests/test_donor_paths.py`, `FLUBNF_ORACLE_FULL=1` on
  `tests/test_oracle.py` and `tests/test_oracle_mix.py` bitwise against the
  registered screens, and `flubnf oracle reproduce`. The `epiweek` cache
  question is checked by timing one weekly pool build before and after.
- 2026-09-30, Submission: for 2026-10-07 run both models on `main` with
  the Data issues box's preselected choices (the rule is in
  [MISSING-DATA.md](../MISSING-DATA.md), "Per-state choices"); leave
  `run.drop_same_day` off. Oracle SIHRS 95% coverage below nominal in weeks
  whose newest NHSN count comes in short is known, not a defect.
- 2026-09-30, Submission: the model-card relWIS in
  [FLUSIGHT-2026-27.md](../FLUSIGHT-2026-27.md) (0.738, 0.666) are the two
  pre-registration screens' figures; in-app replays on build 2132f15 gave
  0.767 / 0.702 / 0.782 by season for the Oracle SIHRS (registered
  0.767 / 0.698 / 0.781).
- 2026-09-30, Engine: keep `pf_mean_scale_column` (or its `lwf` equivalent)
  in the port, or say here if it goes; the model lane may test it on the
  Oracle SIHRS after 2026-10-07 (it was null on the old ensemble,
  2026-09-07, and has never run on the Oracle SIHRS).
- 2026-09-30, Engine and App: the Oracle step (`app/core/oracle.py`) reads
  `collect()`'s origin block (m_0 = the newest reported count, the median of
  block "0"). When the `lwf` port changes the output layout, or `collect()`
  is rewritten for it, keep that convention or tell the model lane; the
  frozen numbers will not reproduce bit for bit either way.
- 2026-09-30, Engine (answering your two Model notes of 2026-09-30): the
  engine lane runs the per-parameter jitter test; the model lane asks
  only that its arms are also scored as the Oracle SIHRS ships (the step
  applied), not the Liu-West filter alone, and not before 2026-10-07. On
  the machine: no replay is planned; see Decided.
- 2026-09-30, Submission (answering your Model note of 2026-09-30): noted.
  Wide early-season Groundhog tails are the donor ratio distribution at
  that epiweek, pooled across jurisdictions; expected, no change.
- 2026-09-30, Submission (answering your Open of 2026-09-30): yes, the
  Oracle SIHRS card should say "Liu-West filter"; the text on `dev` at
  b41fc92 is the model lane's wording now, and can go to the hub in your
  cards pull request whenever Ely asks (not needed for 2026-10-07).
- 2026-09-30, App: FLUSIGHT-2026-27.md still says the Oracle SIHRS card
  "still says particle filter"; stale since b41fc92.
- 2026-10-01 (laptop), App (answering your dry-run question 1): yes. On
  the 2026-09-21 record (52 states, 15,340 cells, US not scored), binned by
  each cell's own h0 median, the Groundhog's 95% coverage is 0.87 under
  20, 0.95 at 20 to 50, 0.975 at 50 to 200 and 0.99 at 200 or more (50%:
  0.36, 0.52, 0.54, 0.59). The pooled 0.95 averages under-coverage on
  small series with over-coverage on large ones; Florida, Texas,
  California and New York cover 0.99 to 1.00. A size-aware spread (or a
  national donor set for US) is a post-2026-10-07 candidate and needs a
  pre-registration; nothing changes for the first round.
- 2026-10-01 (laptop), App: thanks for the README fix (821c2e78), which
  matches the replay. Two small things: the paragraph after it now starts
  "or from the console", a fragment of the sentence the new paragraph
  split; and app.md cites the fix as 02cc23e, which is not a commit.
- 2026-09-30 (laptop), App and Engine: a change to `flubnf/analogue.py`,
  `flubnf/bank.py`, `app/core/engines/analogue.py` or `data/banks/` can be
  checked without the engine or the lab Mac: `flubnf groundhog retro all
  --aux flusurv --no-compare` (about 5 minutes) must give relWIS 0.6705 on
  17,116 cells with the hub at 99cc45a. `tests/test_donor_paths.py` pins
  `donor_ratios` at four points on the committed banks, and skips rather
  than fails when a bank is rebuilt.
- 2026-10-05 (laptop), Submission (answering your note of 2026-10-05 to
  all lanes): agreed on all three points; the Groundhog and donor-bank
  side has nothing to merge before the 2026-10-10 hub pull request.
  `main` 663b5a2 has the Groundhog and donor-bank files unchanged since
  2026-09-30 (banks `flusurv@06eff6a7`, `iliplus@f6ee2840`). Ely's laptop,
  checked read-only on 2026-10-05:
  - FluBNF on `main` at 663b5a2, no local changes; the engine checkout on
    `feature/particle-filter` 2fdadee0, no local edits, and the app calls
    it the production build; R has hubValidations 2.1.1 for
    `scripts/validate_submission.R`.
  - The hub copy (`~/Documents/GitHub/FluSight-forecast-hub`, the path
    the app reads) is at 652d87c, behind CDC's ee477e7: "Update data"
    before the run, as planned.
  - Three full runs of both models already completed on this laptop
    (as-of 2026-09-26, on 2026-09-30 and twice on 2026-10-01): 53
    locations, all 159 fits ok (53 times 3 replicates), the Oracle step
    applied, about 5 minutes from reading the data to both files. The two
    of 2026-10-01 already carry A3 (`addendum_a3_sha256` in `oracle.json`;
    the US row comes out of the step, where the 2026-09-30 run left it
    outside). The round does not need the lab Mac.

## Open

- 2026-09-30, decided (a) above; kept for the record: the options were
  (a) keep the fitted US (frozen spec; at 25% a week the h3 truth is
  about 6,100, inside the band's 8,381 but far above the 1,872 median),
  (b) a sum of states (not valid as built, see Decided), (c) leave US out
  this round (valid, reversible weekly). The model lane had recommended
  (c). The 13 declining states are the same mechanism halved by the step
  plus noise (Illinois lam_T -0.41, Montana -0.27); nothing beyond it.
- 2026-10-01, for Ely: merge the A3 pull request (`dev` to `main`,
  commit d5bd68b plus notes; `dev` carries docs only beyond that), pull
  `main` on the laptop and run the newest data (the 2026-09-30 release)
  to see the US forecast with the step. Decided on
  2026-10-01 (kept for the record): freeze A3 for the first round, or
  hold it for round two; frozen for the first round.
- 2026-09-30, superseded by the entry above (kept for the record): whether
  to amend the pre-registration so the step is applied to the US cell too
  (addendum A3). A freed or re-seeded i0 is NOT the candidate: it was tried
  three times and closed (swarm-carry stage 1B, 2026-09-04/05: FITI0 0.889
  and hindsight ORACLE 1.047 against 0.749 for production, declined by Ely
  on 2026-09-05; the donor-informed i0 priors of the anchor study,
  2026-09-19: null). Freeing i0 gives the right level and no brake; the
  Oracle step is the brake, and the frozen spec keeps US outside it. The
  amendment can be checked without refits (`flubnf oracle backfill` on the
  three replayed seasons' stored US samples), minutes on the Mac Studio,
  only after Ely says so.
