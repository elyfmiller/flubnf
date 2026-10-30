# Submission lane notes

The weekly FluSight run: data checks, validation, the hub pull requests
and CDC's rules. The season's facts are in
[FLUSIGHT-2026-27.md](../FLUSIGHT-2026-27.md).

## Now

- 2026-10-29 (01:02 UTC): ROUND 2026-10-31 MERGED ON THE HUB.
  cdcepi/FluSight-forecast-hub#3929 passed "Hub Submission Validation
  (R)" (2 min 33 s; the bot: all validation checks passed for both
  files) and was merged by Annabella-Hines on 2026-10-28 (merge commit
  3790ae7); both files on cdcepi main are byte-identical to the checked
  ones. The member table, once all five other members were in (report
  only; Ely had chosen to submit without it): our typical ratio is 1.01x
  for both models, the centre of the pack. Apart by more than 1.5x: the
  Oracle in 6 of 48 states (NE 0.42x, KS 0.47x, VT 0.56x, ID 0.56x, SD
  0.59x, NM 1.58x), the Groundhog in 5 of 53 (HI 2.04x, WA 1.63x, KS
  0.62x, CA 1.52x, SD 0.66x); the other members: INFLAenza 6%, ABERT
  11%, epymorph 34%, Copycat 68%, FourCAT 85%. No red flag in any
  member's file. Under the rule these 11 location-model cells would
  have been left out had the members been in before the deadline; the
  Oracle's low states (NE, KS, VT, ID, SD) are the small states where
  its starting level runs low, the Model lane's open item.
- 2026-10-28 (20:19 UTC): ROUND 2026-10-31, HUB PULL REQUEST #3929
  OPENED BY ELY (cdcepi/FluSight-forecast-hub#3929, "NAU_PyBNF forecast
  2026-10-31 (EW43)", from elyfmiller:FluBNF_submission). Head b71aadb6,
  a merge commit from GitHub's fork sync (parents d68fcfca and cdcepi
  main d4b8c556); the pull request still adds only our two files, both
  byte-identical to the checked ones. The hub's "Hub Submission
  Validation (R)" workflow started 20:17 UTC; the same 31 checks passed
  here on these files. The 6 PM Arizona check-in confirms its result.
- 2026-10-28 (20:15 UTC): ROUND 2026-10-31, FINAL CHECK PASSED; Ely opens
  the hub pull request. On the files as committed on the fork (d68fcfca,
  byte-identical to the checked ones): structure clean (Oracle 48
  locations, Groundhog 53), GREEN on all 31 hubValidations checks, gate
  PASS at 10x typical and widest, no red flag, flat or higher
  everywhere; the pull request adds only our two files and merges
  cleanly into cdcepi main d4b8c556 (hub-config unchanged since our
  base). The member table never had three other members (only epymorph
  by 20:13 UTC); Ely (2026-10-28): that is fine this week, the aim is to
  be around the pack. Against the field's median (ten other teams'
  CSVs) the Oracle sits at 1.00x typical, the Groundhog 1.08x; against
  epymorph alone 1.26x and 1.29x, as expected (last week epymorph sat at
  0.87x of the other members). The 6 PM Arizona check-in reports only.
- 2026-10-28 (19:58 UTC): ROUND 2026-10-31 RESTAGED AT 10x (Decided).
  Ely's 10x run: the shrink form (medians and lower halves identical to
  the uncapped run; the few tied upper levels are whole-number rounding
  in small states). Both files GREEN on all 31 hubValidations checks,
  gate PASS with the typical and widest state at 10.0x at horizon 3
  (95% band over the median 3.2x), no red flag, the Groundhog flat or
  higher everywhere; the Oracle fails flat in the same five states as at
  15x (medians do not move with the cap) and leaves them out again (48
  locations). Widths, typical state at h3 (97.5% over the three-week
  mean): ours 10.0x; epymorph today 11.2x; last week's members ABERT 6.3x,
  INFLAenza 7.6x, FourCAT 8.6x, epymorph 11.7x, Copycat 19.5x, Spencer's
  ensemble 11.5x. Medians against today's field (10 other teams' CSVs
  on cdcepi main or in open pull requests, FluSight models left out):
  Oracle typical 0.98x, 13 states more than 1.5x apart (low: AK, NE, ID,
  KS, VT, ME, MT; high: MS, TX, PA, NM, CA, FL); Groundhog 1.08x, 6 (RI
  low; US, FL, NY, CA, WA high); informative only, the rule's member
  table waits for three other NAU members (only epymorph at 19:55 UTC).
  FluBNF_submission: commit d68fcfca on top of 1238d4ee, both files
  byte-identical to the checked ones, pushed to the fork.
- 2026-10-28 (18:38 UTC): ROUND 2026-10-31, THE ORACLE FILE LEAVES OUT
  FIVE STATES (Ely's choice over a weight-0 rerun of them): Alaska,
  District of Columbia, Hawaii, Maine and Montana, all four horizons,
  for failing flat-or-higher. The Groundhog file keeps all 53 and passes
  every rule, so for these five our forecast this week is the
  Groundhog's. The trimmed Oracle file is the staged one minus those 460
  rows byte for byte (48 locations); GREEN on all 31 hubValidations
  checks, gate PASS (h3 15.0x typical and at most), no red flag, flat or
  higher everywhere. FluBNF_submission: commit 1238d4ee on top of
  93314fb1, pushed to the fork (no force); compare link unchanged:
  https://github.com/cdcepi/FluSight-forecast-hub/compare/main...elyfmiller:FluSight-forecast-hub:FluBNF_submission?expand=1
  The member table still waits for three other members (only epymorph
  in); the 6 PM Arizona check-in runs it on the trimmed files.
- 2026-10-28 (18:20 UTC): ROUND 2026-10-31, FLAT OR HIGHER (Decided,
  2026-10-28). Ely's rerun is byte-identical to the staged files (the
  run is deterministic). Five Oracle states fail: Alaska (median 6, 7,
  7, 7 against a last week of 7, after 22), District of Columbia (3, 4,
  4, 3; a falling step), Hawaii (53, 56, 61, 68 against 63, after 82),
  Maine (15, 17, 18, 20 against 16) and Montana (13, 13, 14, 17 against
  15); the Groundhog passes everywhere. Nebraska and Vermont pass on the
  median; what looks like "going down" in the report is the Oracle's
  lower band (its 25% quantile falls across horizons in 6 states and
  ends below the last week in 14). The member table: only epymorph was
  in at 18:20 UTC, so no comparison yet (the check needs three other
  members; the first version of the script compared against two, fixed
  before any use).
- 2026-10-28 (16:55 UTC): THE FLAG CHECK ON ROUND 2026-10-31 (Decided,
  2026-10-28). (1) Spencer's red flag, as submitted: none over 30x;
  typical state 11.9x Oracle, 13.0x Groundhog; widest Vermont 21x
  (Oracle), District of Columbia and Alaska 20x (Groundhog). Without the
  shrink the Oracle would have had 5 (Michigan 36x, North Dakota 35x,
  Rhode Island 32x, Wyoming 30.1x, West Virginia 30.1x), the Groundhog
  none. (2) The member medians: not yet possible; at 16:55 UTC no NAU
  member had a 2026-10-31 file on cdcepi main or in an open hub pull
  request (the only one open was NU-EMBERS, #3912). Ely holds the hub
  pull request until the members are in, then this lane runs the
  comparison, drops any flagged location, re-validates and recommits;
  the deadline is 8 PM Arizona time (03:00 UTC). Six states' newest week
  fell 20% or more (Alaska, Connecticut, Hawaii, Idaho, Kansas,
  Montana); both models start near the lower value (the Groundhog
  anchors on it, the Oracle's filter followed it); the previous newest
  week was revised up by a median 3.7%, so these read as small-count
  noise more than reporting lag. The Groundhog's medians step up most
  from horizon 1 to 2 in 97% of states, both weeks (1.27x, 1.46x, 1.21x
  this week); the raw admissions donors show a milder form, so most of
  it comes later in the chain; a question for the Model lane.
- 2026-10-28 (16:25 UTC): ROUND 2026-10-31 (EW43) STAGED, THE FIRST WITH
  THE 15x SHRINK. Ely ran main d7d13e5 (PR #60) on the laptop with the
  five override values (pf.seed_denominator season_total_early, oracle.w
  0.25, oracle.narrow 0.7, output.tail_cap 15, output.tail_mode shrink;
  historical ceiling 0) and one override reason; the panel screenshots
  showed the five changes and nothing else. Hub data through 2026-10-24
  (53 locations; US 6,006, 1.21x the week before; states median 1.18x).
  Both files: 4,877 lines, 53 locations, horizons 0-3 for 2026-10-31 to
  2026-11-21, 212 monotone integer blocks; both GREEN on all 31
  hubValidations checks (scripts/validate_submission.R --window, TZDIR
  set) against cdcepi main ac4e5a04. The gate (scripts/sense_check.py
  from main, truth through 2026-10-24): PASS for both; the h3 97.5% over
  the recent level is 15.0x for the typical state and 15x at most (last
  week as submitted: 20x typical, 9 states over 30x in each file).
  Plausibility: Oracle h0 medians 1.23x the last observed week
  (10th-90th 1.00-1.37), Groundhog 1.14x (1.00-1.20); the last observed
  week inside the h0 95% band in every state for both; US h3 Oracle
  2,944-16,736-73,238, Groundhog 2,937-17,520-75,165. Last week's pull
  request was cdcepi/FluSight-forecast-hub#3856, merged (14f17caf).
  Submission: FluBNF_submission fast-forwarded to cdcepi main ac4e5a04
  (fetched by URL), the two files byte-identical to the uploads under
  model-output/NAU_PyBNF-OracleSIHRS/ and
  model-output/NAU_PyBNF-GroundHogCGR/, commit 93314fb1 "NAU_PyBNF
  forecast 2026-10-31 (EW43)" as Ely, pushed to the fork, one commit over
  main. Compare link for Ely's hub pull request:
  https://github.com/cdcepi/FluSight-forecast-hub/compare/main...elyfmiller:FluSight-forecast-hub:FluBNF_submission?expand=1
  Still owed: the cap-0 export of the same run (Ely, after the hub pull
  request is open) for the meeting page's with-and-without figures.
- 2026-10-26 (01:25 UTC): THE TWO EDGE FIXES ON BRANCH tail-hist-edges
  (c417743, one commit over dev 4daf9bd, for Ely's merge; nothing for
  Wednesday, where the ceiling is off). (1) history_ratios measures the
  window on the donors' own calendar: flubnf.analogue.epiweek (MMWR
  weeks) and calendar_distance (week 53 between 52 and 1), so a forecast
  date in week 53 no longer counts week 1 as distance 0; test at
  2027-01-02. Note for anyone reading the ratios: MMWR and ISO week
  numbers differ by one in some years (2026-10-17 is MMWR week 41, ISO
  42), so the window moved by a week against the branch's first form;
  the screens' ratios were computed from the merged (ISO) form, and the
  difference is a handful of year-end and October cells, not a changed
  conclusion. (2) When the knob is set and the history could not be
  read, the run record carries tail_hist with skipped true and the
  reason, so the run page says the knob did nothing
  (flubnf.tailcap.skipped_record); tested at the helper and by the
  pipeline's wiring text. A pipeline test that makes the truth read fail
  was not built here (this lane has no cheap harness for _run_all); the
  Groundhog agent asked for one, and it stays open. tests/test_tailcap.py
  (19), app/tests/test_knobs.py and test_knobs_wiring.py pass. Ely's
  merge: `git fetch origin tail-hist-edges && git checkout dev && git
  merge --no-ff origin/tail-hist-edges && git push origin dev`; the
  dev-to-main pull request at Ely's word, any time before a round that
  turns the ceiling on.
- 2026-10-26 (01:00 UTC): THE AGENTS' VERDICTS ON THE HISTORICAL CEILING
  ARE IN (docs/team/model.md, 2026-10-25 23:50 UTC, both agents; records
  in the repository under docs/team/model-oracle-width-screen-2026-10/
  and model-groundhog-hist-ceiling-2026-10-25/). WEDNESDAY RUNS THE
  SHRINK AT 15x ALONE, NO CEILING: the five override values of
  2026-10-23 (pf.seed_denominator season_total_early, oracle.w 0.25,
  oracle.narrow 0.7, output.tail_cap 15, output.tail_mode shrink), one
  reason. Both agents recommend exactly that.
  The Oracle's 84 weeks (pre-registered amendment 3, de645b23, the pass
  rule written before any score; post hoc on C0's stored weeks through
  main's own functions with each week's vintage): the pairing (maximum +
  shrink 15x) FAILS the rule on two counts. (P3a) In the four October
  as-ofs it loses to the shrink alone, 0.790 against 0.778, +0.0125
  [+0.0016, +0.0329]; (rule iii) its 95% coverage sits 0.012 below the
  shrink's (0.886 against 0.898), 0.014 in the early weeks. The rest
  holds: P1 (the maximum alone -0.0056 [-0.0139, -0.0001] against none,
  the best arm on the natural scale, 6% of h3 cells still over 30x), P2a
  (the pairing 0.9% below shrink 15x pooled, -0.0060 [-0.0140,
  -0.0004]), P2b (within noise of clip 15x), P3c (99% of the gain from
  November-January as-ofs), P4 (the 0.975 ceiling: coverage 0.851, worse
  on the log scale). P3b was wrong in its premise: the screen's October
  as-ofs (2023-24's four) read one history season and their ceilings at
  h1-h3 sat UNDER 15x, so the pairing bound there; and the October loss
  comes by the mechanism this lane saw in last week's file (the ceiling
  pre-clips h3, the shrink does less, h0-h2 stay wider, and in October
  the narrowing is what scores). By season the pairing minus the shrink
  is -0.026 in 2023-24 (one history season), -0.003 in 2024-25, +0.0003
  in 2025-26, the season most like the live one. The Oracle agent sees
  no case for the ceiling in November either. The vintage against the
  settled truth moved the pooled score by +0.0003: this lane's
  final-truth shortcut was harmless.
  The Groundhog's three kernel-form seasons (pre-registration c9587ab5,
  through its own retro, every week's vintage): the pairing passes every
  registered test and all six predictions hold, but it is free, not a
  gain (-0.0013 [-0.0039, +0.0009] against the shrink pooled; the whole
  gain is December 2023; +0.0015 in 2023-24's October weeks and +0.004
  on this season's four); the maximum alone is within noise of none
  (0.6419 against 0.6423, this lane's post hoc 0.6406 used the final
  truth) but costs 95% coverage (0.946 to 0.931) and 2024-25, the season
  that outgrew its history (+0.002, the record peak). It does not clear
  the gate alone. So the Groundhog neither blocks nor argues for the
  pairing; the call rested on the Oracle's weeks, and it fails there.
  This lane's reading: the two screens agree with each other and with
  the mechanism this lane found on last week's file; the 44-week result
  of 2026-10-25 was real but came from the in-season weeks and from the
  2023-24 season, where one history season makes a tight ceiling; the
  live round reads four seasons and sits in October. The ceiling stays
  a research knob at 0. The three code findings from the Groundhog agent
  are answered under For other lanes (2026-10-26); two are small fixes
  for a branch at Ely's go, the third is a screen question for 11-04 at
  the earliest.
  Wednesday's meeting figures: last week's round as submitted against
  the shrink at 15x (the two figures of 2026-10-25, 19:12 UTC entry),
  and the same pair from the fresh files within the hour of receiving
  them.
- 2026-10-25 (23:31 UTC): PULL REQUEST #49 (dev TO main) MERGED BY ELY AT
  23:31 UTC, merge commit a99d53d (two parents, 757ce69 and 21a9497; a
  merge commit). Ely's first merge command at 23:30 was refused
  ("Pull Request is not mergeable"): this lane had pushed a notes commit
  to dev at 23:29 and GitHub was recomputing the mergeability; the second
  try went through. Lesson for this lane: no push to dev between opening
  a PR and Ely's merge. main now carries the historical ceiling (knob
  output.tail_hist) beside the cap and the gate; the laptop on main has
  everything a Wednesday ship of the pairing needs. The decision stays
  Tuesday evening's, on the two agents' screens. The PR subscription
  closed with the merge; the check-in was cancelled.
- 2026-10-25 (23:35 UTC): TODAY'S ENTRY TIMES CORRECTED TO THE COMMIT
  CLOCK (this lane's clock ran hours behind the commits again): the
  entries written as 03:30, 05:10, 07:40, 08:00 and 08:20 UTC were
  committed at 19:12, 19:35, 19:51, 21:02 and 23:28 UTC (9211243,
  b28b49c, d3f5ae1, 96740b3, e35edcb). The Tuesday decision point and
  everything else in them stand. PR #49 at 23:35 UTC: open, GitHub's
  tests running on its head e35edcb; the check-in armed.
- 2026-10-25 (23:28 UTC): tail-hist MERGED INTO dev (463ddba, a merge commit
  as Ely, at Ely's word; parents 96740b3 and 18b9fd6) AND PULL REQUEST #49
  (dev TO main) OPENED BY THIS LANE: https://github.com/elyfmiller/flubnf/pull/49,
  "Historical ceiling on the upper tails (output.tail_hist), a research
  knob for both members", 8 commits over main (757ce69), 10 files: the
  ceiling, its tests, the knob, the pipeline wiring, the Oracle doc, the
  notes (the App lane's bug-hunt report of 2026-10-25, find only, rides
  along). Every commit authored and committed as Ely, no trailers; the
  body carries no attribution (the integration's footer edited out at
  once). Ely's merge command, a merge commit, never squash:
  `gh pr merge 49 --merge --repo elyfmiller/flubnf`, or `git fetch origin
  main dev && git checkout main && git merge --no-ff origin/dev && git
  push origin main`. Subscribed to the PR. After the merge the laptop's
  main has the knob; the Wednesday decision stays Tuesday evening's.
  The paste-able messages to the two model agents went to Ely in chat
  (the handoff entry below is the record).
- 2026-10-25 (21:02 UTC): ELY'S PLAN FOR THE CEILING: the Oracle SIHRS
  agent and the Groundhog agent each test it as a post-calibration step
  on their own screens; if the results are good and the code is known
  bug-free before Wednesday, it ships on 2026-10-28 with plots for the
  Wednesday meetings. What that needs, in order: (1) the screens on the
  Mac (the Oracle's 84 weeks; the Groundhog's three seasons in the
  kernel form through its own retro, with the ceiling's ratios from each
  week's vintage), the predictions P1-P4 of the handoff checked; (2)
  tail-hist merged into dev by Ely, the dev-to-main pull request at
  Ely's word, main on the laptop before the run (the knob is not on main
  until then); (3) Wednesday's override values become six: seed
  season_total_early, weight 0.25, narrowing 0.7, output.tail_hist 1,
  output.tail_cap 15, output.tail_mode shrink; (4) this lane's round
  procedure unchanged: the hub check, the gate, the submission commit;
  plus the meeting figures from the fresh files (tools/lastweek_shrink.py
  and lastweek_hist.py re-pointed at the 10-28 round: as submitted last
  week, the shrink alone, the ceiling + shrink, beside the reported
  series), ready within the hour of receiving the files. If either
  screen is not in or a prediction fails, Wednesday runs the shrink at
  15x alone as decided on 2026-10-23, and the ceiling waits for 11-04.
  The decision point is Tuesday 2026-10-27 evening: the screens read,
  the branch on main.
- 2026-10-25 (19:51 UTC): THE HISTORICAL CEILING IS CODED ON BRANCH
  tail-hist (18b9fd6, one commit over dev b28b49c, at Ely's word "I want
  to test this historical maximum"), FOR ELY'S MERGE INTO dev. Knob
  output.tail_hist (both members, output stage, research, 0 = off, the
  registered form): per horizon, the levels above the median are clipped
  at the recent level times a quantile of the growth history produced at
  this calendar position, y[W+h+1] over the recent level at W across
  every jurisdiction's weeks within two epiweeks of the forecast date in
  strictly earlier seasons with a recent level of at least 10, read from
  the run's own truth vintage (flubnf.tailcap.history_ratios,
  history_limits, clip_rows_by_horizon; HIST_WINDOW 2, HIST_FLOOR 10).
  The knob is the quantile: 1 the maximum, 0.975 the 97.5th percentile.
  It runs before output.tail_cap, so the ceiling deletes what never
  happened and the cap or the shrink shapes the rest; whole admissions,
  monotone, as the cap. The run record carries tail_hist (level, window,
  floor, the ratios by horizon, the cells touched per member). Added to
  NOT_IN_RETRO (screened post hoc, as the cap is). Tests: five new in
  tests/test_tailcap.py (the maximum and a quantile over earlier seasons
  in the window, the current season and far weeks ignored, the floor, the
  limits, the per-horizon clip on hub rows); the knob in
  app/tests/test_knobs.py's defaults. tests/test_tailcap.py,
  app/tests/test_knobs.py, test_knobs_wiring.py and
  test_optional_outputs.py pass (100). docs/ORACLE-SIHRS.md 6c has the
  paragraph. Ely's merge, a merge commit: `git fetch origin tail-hist &&
  git checkout dev && git merge --no-ff origin/tail-hist && git push
  origin dev`, then the dev-to-main pull request when Ely says so.
  NOT FOR WEDNESDAY: the round runs the shrink at 15x with no ceiling
  (the override values of 2026-10-23 02:50 UTC stand); the ceiling is a
  screened candidate for the 11-04 round at the earliest, after the
  Model lane's 84-week result.
  THE GROUNDHOG UNDER THE CEILING (tools/spencer_gh_screen.py,
  replays/spencer_gh_result.txt; the three retro seasons regenerated in
  the kernel form, 17,116 cells): none 0.6423 / cov95 .936; clip 15x
  0.6423 / .931; shrink 15x 0.6472 / .922; histmax clip 0.6406 / .928
  (-0.0015 [-0.005, +0.000] against clip 15x); histmax + shrink 15x
  0.6445 / .916 (+0.002 [-0.003, +0.007] against clip 15x, 0.003 better
  than the shrink alone). September-October: shrink 15x 0.923, histmax +
  shrink 0.926, clip 15x 0.961, none 0.978. November: histmax clip 0.537
  best, the shrinks 0.548-0.555. The Groundhog's tails rarely exceed
  history because they are history, so the ceiling is near-neutral for
  it.
  LAST WEEK'S ROUND UNDER THE PAIRING (tools/lastweek_hist.py, the branch
  code on the 2026-10-17 vintage; figures review3/lastweek_oracle_histmax.png
  and lastweek_groundhog_histmax.png): the history maximum at this
  calendar position is 11.7x, 19.5x, 26.2x, 37.8x the recent level at
  h0-h3 (the 97.5th: 3.8x, 7.2x, 11.4x, 19.3x), above the 15x line at
  h1-h3, so this October the pairing and the shrink alone are nearly the
  same file: identical h3 tails (typical 15.0x, max 15x; the gate passes
  both), and the ceiling changes 44 Oracle blocks and 10 Groundhog blocks
  only by pre-clipping the wildest h3 tails (WV 425 to 290, MI 2216 to
  1966, ND 148 to 125) before the shrink, which then needs a milder
  exponent and leaves h0-h2 a few percent wider (Michigan h2 97.5% 495
  to 531; Connecticut, Maryland, New Hampshire, Vermont, West Virginia
  likewise). That is the mechanism of the 44-week gain: the ceiling
  takes the impossible top, the shrink does less, the near-term fan
  keeps more of its width. The ceiling bites on its own in mid-season
  weeks, where the history maximum sits under the 15x line (typical
  limits 3.5x on the 44 weeks).
- 2026-10-25 (19:35 UTC): SPENCER'S RULE AGAINST OURS, SCREENED (Ely:
  "how would using Spencer's method compare to ours?"). Spencer's cap is
  a bound from historically realised 4-week changes; read two ways on
  the Oracle's 44 stage-rule weeks (w 0.25, k 0.7; tools/spencer_screen.py,
  replays/spencer_result.txt, spencer_cells.csv; 9,020 cells common to
  every arm; post hoc, final truth for the history table, no
  pre-registration): (a) HIST, a per-horizon ceiling of the recent level
  times a quantile of y[W+h+1]/recent(W) over every state's weeks within
  2 epiweeks of the as-of in strictly earlier seasons, base level 10 or
  more, pooled; at the 97.5th percentile (typical 2.6, 2.7, 3.2, 3.8x at
  h0-h3 on these in-season weeks) and at the maximum; (b) GH, the
  Groundhog's own 97.5% quantile at the same (location, as-of, horizon)
  in the kernel form (the three retro seasons regenerated here on dev
  with --own-share 0.5 --kernel-sd 1; typical 2.6, 3.5, 4.4, 5.1x), the
  calendar-conditioned, own-state-weighted reading of the same history.
  Each as a clip (Spencer's form) and as the location-wide shrink with
  per-horizon limits; plus the pairing histmax clip then our shrink 15x.
  relWIS natural / log, cov95, h3 tail typical, share over 30x; and each
  arm minus ours15-clip by 2,000 week-cluster resamples (natural | log):
    k0.7 (none)      0.6705 0.7167 .931  5.0x .141 | +0.001 [-.001,+.004]
    ours15-clip      0.6695 0.7174 .919  5.0x .000 | reference
    ours15-shrink    0.6739 0.7253 .907  5.0x .003 | +0.004 [+.000,+.008] | +0.008 [+.001,+.014]
    hist97-clip      0.6692 0.7246 .861  2.9x .000 | -0.000 [-.019,+.014] | +0.007 [-.002,+.017]
    hist97-shrink    0.6988 0.7561 .843  2.8x .003 | +0.028 [+.002,+.055]
    histmax-clip     0.6625 0.7147 .914  3.5x .092 | -0.007 [-.016,-.001] | -0.003 [-.007,+.001]
    histmax-shrink   0.6668 0.7245 .902  3.5x .063 | -0.003 [-.019,+.009]
    gh97-clip        0.6676 0.7173 .919  4.4x .052 | -0.002 [-.004,+.000] | -0.000
    gh97-shrink      0.6763 0.7315 .902  4.0x .031 | +0.006 [-.007,+.020]
    histmax+shrink15 0.6643 0.7193 .897  3.5x .003 | -0.005 [-.016,+.003] | +0.002 [-.004,+.007]
  October-November as-ofs: none 0.598, ours15-clip 0.588, ours15-shrink
  0.598, hist97-clip 0.587 (cov95 .917), histmax-clip 0.588 (.950),
  gh97-clip 0.589, histmax+shrink15 0.588.
  Reading. (1) Spencer's bound at a strict percentile is too tight for
  the Oracle on in-season weeks: the history's 97.5th at these calendar
  weeks sits at 3.8x the recent level at h3 while the Oracle's typical
  tail is 5x, so the clip binds everywhere, 95% coverage falls to 0.86
  and the log score worsens; as a shrink it is the worst arm (+0.028).
  (2) At the historical MAXIMUM it is the best arm on both scales
  (-0.007 natural, the interval excluding zero; -0.003 log), coverage
  0.914: deleting what never happened is free or better. It does not
  clear the 30x gate alone (9% of h3 cells over 30x, the calendar weeks
  whose historical maximum is itself above 30x). (3) The Groundhog as
  the ceiling is -0.002, within noise, coverage 0.919. (4) The pairing,
  history's maximum then our shrink at 15x, scores 0.6643: 1% better
  than our shrink alone on the natural scale (0.6739; log 0.719 against
  0.725), clears the gate (0.3% over 30x, cells whose h3 median is
  itself above the limit), 95% coverage 0.897, and keeps the fan. On
  these weeks it is the best shape-keeping rule. (5) The clip beats the
  shrink at every bound, as on the Mac.
  Caveats: 44 in-season weeks (October to January), not the October
  gate weeks; final truth for the history table (a live rule would read
  the vintage); no pre-registration; one screen. What it does for
  Wednesday: nothing (shrink 15x stands; a per-horizon historical limit
  is not a knob on main). What it does for the handoff of 2026-10-23
  (trajectory exclusion at 40x + shrink 15x): the same idea in quantile
  form scored here as predicted, so the Model lane's arm has a prior
  result to check against on the 84 weeks; if it holds there, the
  historical-maximum clip is a one-table addition to tailcap for the
  11-04 round at Ely's word.
- 2026-10-25 (19:12 UTC): PR #48 MERGED BY ELY (main 757ce69, the kernel
  form and card 1.3); ELY RUNS THE ROUND WEDNESDAY AND HANDS THIS LANE
  THE FILES. LAST WEEK'S ROUND REBUILT UNDER THE WEDNESDAY PROTOCOL, for
  Ely's eyes before the run (figures review3/lastweek_oracle_shrink15.png
  and lastweek_groundhog_shrink15.png in the Submission scratchpad;
  tools/lastweek_shrink.py). The Oracle: the submitted 10-24 file under
  the location-wide shrink at 15x (main's tailcap, whole admissions).
  The Groundhog: regenerated in the cloud on dev at the 2026-10-17
  vintage in the kernel form (`flubnf groundhog retro 2026-27 --aux
  flusurv --with-us --own-share 0.5 --kernel-sd 1`, the hub mirror
  brought to cdcepi main de256fda, which holds the 10-17 vintage and
  truth through 10-17; the record names local_pools own_share 0.5,
  anchor_weight kernel, kernel_sd 1.0, ess_floor 30), then the shrink at
  15x. Reproduction check: Ohio's uncapped kernel 97.5% quantiles read
  253, 451, 620, 964, the Model lane's numbers exactly.
  h3 97.5% over the recent level, states: Oracle as submitted typical
  20.4x, max 55x (WV), 9 over 30x; under the shrink typical 15.0x, max
  15x, none. Groundhog as submitted (own-share form) typical 20.4x, max
  81x (ID), 9 over 30x; kernel form uncapped typical 14.8x, max 27x
  (DE), none over 30x; kernel + shrink typical 14.8x, max 15x. So for
  the Groundhog the kernel does most of the work and the shrink touches
  only the states above 15x (DE, AZ, MI, US among them); Ohio's double
  peak is gone before any cap. The gate (scripts/sense_check.py) passes
  both protocol files (h3 band over median typical 5.4x Oracle, 5.8x
  Groundhog). Files: review3/2026-10-24/2026-10-24-NAU_PyBNF-OracleSIHRS-shrink15.csv,
  -GroundHogCGR-kernel.csv, -GroundHogCGR-kernel-shrink15.csv.
  Note on the cloud replay: the retro without --aux runs the bare
  single-pool analogue (arm "shipped"), not the Groundhog; the Groundhog
  is --aux flusurv. The first attempt here ran the bare arm and was
  discarded (app/state/groundhog/shipped/2026-27, untouched otherwise).
- 2026-10-23 (02:50 UTC): ELY'S DECISION FOR 2026-10-28: THE LOCATION-WIDE
  SHRINK AT 15x FOR BOTH MEMBERS (replacing the clip at 10x recorded by
  the Model lane at 01:38 UTC; the kernel still ships, PR #48). The
  reasoning, Ely's, in chat: in principle the shrink is the better
  forecast; the clip cuts the tails of the quantiles and ties the top
  levels at the limit (a point mass at the bound), which looks wrong on
  the dashboard and claims more than the model can support; the shrink
  keeps a proper, monotone fan. At 15x the Oracle's full-season screen
  cannot tell the two forms apart (shrink 15x +0.002 season-wide, +0.007
  in the early weeks, both inside the bootstrap interval on the natural
  scale; 95% coverage 0.90 / 0.87 against the clip's 0.91 / 0.90), so
  the choice is made on form, stated as such. For the Groundhog with the
  kernel the shrink at 15x is 0.649 against the clip's 0.644 season-wide
  and better in October. What it gives up: the width target (the typical
  h3 tail lands at 15x the recent level, not the members' 8-12x; the
  move to 10x is reconsidered once a capped week has scored, and the
  shrink does not go to 10x: +0.032 in the early weeks). The sentence
  for Spencer's call: the horizon-3 97.5% quantile is bounded at the
  95th percentile of historically realised 4-week growth, and the band
  is shrunk toward the median by one exponent per location so the fan
  keeps its shape.
  WEDNESDAY'S OVERRIDE VALUES, FINAL unless Ely says otherwise (main at
  or after the #48 merge; one reason): pf.seed_denominator
  season_total_early, oracle.w 0.25, oracle.narrow 0.7, output.tail_cap
  15, output.tail_mode shrink. Then the hub check, the gate from main on
  both files (expected: PASS, max h3 ratio 15x), the submission commit
  "NAU_PyBNF forecast 2026-10-31 (EW43)", the compare link.
  Ely's trajectory-exclusion idea (drop the forecasting-sample paths
  that cross n times the recent level, the swarm untouched) is handed
  to the Model lane as a screen (For other lanes); not on Wednesday's
  file.
- 2026-10-23 (02:10 UTC): THE MAC RESULTS READ (docs/team/model.md, the
  entries of 2026-10-22 14:41 UTC to 2026-10-23 01:38 UTC); ELY'S
  DECISION "SHIP THE KERNEL, CLIP AT 10x"; THIS LANE'S READING REVISED.
  - The Oracle's full-season screen (C0, 84 weeks, 17,466 cells, the cap
    through main's code with the rounding fix): at k 0.7, none 0.668 /
    cov95 0.92; clip 15x 0.668 / 0.91 (free, no h3 cell over 30x); clip
    10x 0.672 / 0.90 (+0.003, inside noise); shrink 15x 0.670 / 0.90;
    shrink 10x 0.681 / 0.87; shrink 8x 0.691 / 0.85. In the first eight
    scoreable weeks of each season, where the gate binds, the shrink at
    10x costs +0.032 with 95% coverage down to 0.79, the clip at 10x
    +0.008 at 0.86, the clip at 15x nothing. This lane's 44-week cloud
    screen agrees with the Mac within 0.001-0.005 on every rule (natural
    relWIS and coverage); the log scale runs 0.01 lower on the Mac
    because it scores the submitted seed after the floor and rounding.
    THE REVISION: this lane's standing recommendation (the location-wide
    shrink at 15x) was wrong for the Oracle. The shrink's exponent, set by
    the worst horizon, also squeezes the upper side of horizons 0-2,
    where truth lands in a fast rise; the clip takes only the far tail.
    The 44-week screen showed the same ordering (clip 15x 0.670, shrink
    15x 0.674) and this lane read the Groundhog's October gain as the
    tiebreaker; the Oracle's early-week cost is the larger effect and the
    full seasons make it plain. The clip is the shared form.
  - The Groundhog: the size-matched kernel (a donor week's weight falls
    with the log-scale distance between its own count and the
    jurisdiction's newest; the effective-donor guard at 30) gains about
    0.017 at every cap level and form, in every complete season, in 50 of
    52 states, and removes the Ohio defect at its source: on the 10-24
    data Ohio's 97.5% quantiles become 253, 451, 620, 964 and no
    jurisdiction is over 30x before any cap (own-share form: 9). The
    floor, the winsor, the spike repair and the 2024 window move the
    score by 0.0003 or less and are held. The handoff of 2026-10-22 is
    answered; the kernel is the fix.
  - Ely's decision, recorded by the Model lane at 01:38 UTC: the kernel
    ships (commit 689a650 on dev; pull request #48, dev to main,
    https://github.com/elyfmiller/flubnf/pull/48, 12 commits, 21 files,
    +1058/-87, card GroundHogCGR 1.3, record 0.642); the cap for
    2026-10-28 is the CLIP AT 10x, one setting for both members. On the
    10-24 data with the kernel the clip at 10x binds at h3 in all 53
    jurisdictions (the typical h3 tail is 14.8x), so this week the cap,
    not the model, sets every h3 97.5% quantile; the h3 band is 4.1x the
    median. From the 11-11 round the Groundhog's cells say no cap or
    clip 15x.
  - PR #48 as read at 02:10 UTC: open, mergeable_state clean, GitHub's
    tests green on the head fa543d8 (both the push and the pull_request
    runs) and on 689a650. Ely's merge command, a merge commit, never
    squash: `gh pr merge 48 --merge --repo elyfmiller/flubnf`, or
    `git fetch origin main dev && git checkout main && git merge --no-ff
    origin/dev && git push origin main`. The Wednesday run needs main at
    or after that merge.
  - The gate on the 10-24 files rebuilt under clip 10x (own-share
    Groundhog, this lane's review3): both PASS, typical and max h3 ratio
    10.0x, h3 band over median 3.8x Oracle, 3.7x Groundhog.
  - WEDNESDAY 2026-10-28, THE OVERRIDE VALUES (Ely's laptop, main at or
    after the #48 merge; one reason): pf.seed_denominator
    season_total_early, oracle.w 0.25, oracle.narrow 0.7, output.tail_cap
    10, output.tail_mode clip. Then the hub check, the gate
    (scripts/sense_check.py from main) on both files, the submission
    commit "NAU_PyBNF forecast 2026-10-31 (EW43)", the compare link.
    Card 1.3 goes to the hub fork when Ely asks for the hub pull
    request; the cards' sentences for the narrowing and the cap go with
    it.
- 2026-10-22 (04:59 UTC): PULL REQUEST #47 (dev TO main) MERGED BY ELY AT
  04:59 UTC, merge commit 210f2fb (two parents, 744e654 and 3953b41; a
  merge commit), a minute after it opened. main now carries
  scripts/sense_check.py, the tail gate; the laptop runs it from main on
  Wednesday as step three of the round procedure (entry of 05:05 UTC
  above). The PR subscription closed with the merge and the check-in
  was cancelled. What main carries for the 2026-10-28 round, in order
  of landing: the narrowing knob (#44), the upper-tail cap in two forms
  (#45), the whole-admission rounding of the cap (#46), the gate (#47).
- 2026-10-22 (05:15 UTC): tail-gate MERGED INTO dev (a64b01d, a merge commit
  as Ely, at Ely's word; parents 04935f9 and 152910f) AND PULL REQUEST #47
  (dev TO main) OPENED BY THIS LANE: https://github.com/elyfmiller/flubnf/pull/47,
  "Pre-submission tail gate (scripts/sense_check.py) and the lanes'
  notes", 12 commits over main (744e654), 5 files, +463/-1: the script,
  its five tests, the README row, both lanes' notes (the Model lane's
  width screen pre-registered on the Mac and its Groundhog tail-cell
  screen ride along). Every commit authored and committed as Ely, no
  trailers; the body carries no attribution (the integration's footer
  edited out at once). Ely's merge command, a merge commit, never
  squash: `gh pr merge 47 --merge --repo elyfmiller/flubnf`, or
  `git fetch origin main dev && git checkout main && git merge --no-ff
  origin/dev && git push origin main`. Subscribed to the PR; after the
  merge the laptop runs the gate from main on Wednesday.
- 2026-10-22 (05:05 UTC): THE TAIL GATE IS IN THE REPO ON BRANCH tail-gate
  (152910f, one commit over dev bdc10c0, for Ely's merge into dev):
  scripts/sense_check.py, an OPS script beside validate_submission.py,
  pandas and numpy only, nothing imported from the app. For every
  jurisdiction, the 97.5% quantile of wk inc flu hosp at each horizon
  over the recent level (the mean of the last three reported dates in
  the hub's target-hospital-admissions.csv); FAIL, exit 1, when any
  horizon-3 ratio exceeds the threshold (30x unless --threshold says
  otherwise); exit 2 on a missing file. It prints the field summary
  beside the gate (the typical state's ratio, the 95% band over the
  median, the count over the threshold per horizon) and names each
  failing state with its 97.5%, median, recent level and last value. A
  recent level of 0 (Wyoming's summer) gives no ratio and never fails;
  other targets and pmf rows are ignored. tests/test_sense_check.py
  (five tests: the recent level, the gate at 31x and 29x, the threshold
  and horizon-3-only rule, the zero level and the ignored rows, the
  script's output and exit codes by subprocess); scripts/README.md row.
  On the 2026-10-24 Oracle file as submitted it fails with the same
  nine states the scratch gate found (WV 55x ... DE 32x); on the
  location-wide shrink at 15x it passes (max 15x, Mississippi). The one
  difference from the scratch gate: the band-over-median summary now
  drops the US row as the ratio summary always did (1.84x against 1.83x
  at h0). Ely's merge: `git fetch origin tail-gate && git checkout dev &&
  git merge --no-ff origin/tail-gate && git push origin dev`, then the
  dev-to-main pull request when Ely says so; nothing reaches the laptop
  until it is on main.
  THE ROUND PROCEDURE from 2026-10-28 on, in order: (1) Ely runs main
  with the override values and one reason; (2) the hub check
  (app.core.hubcheck in the console; scripts/validate_submission.R with
  conda R and TZDIR here) on both files; (3) the gate,
  `python scripts/sense_check.py <target-hospital-admissions.csv> <both files>`,
  with the truth file at the vintage the run used; a FAIL stops the
  round, no file is committed, and this lane reports the failing states
  to Ely with the cap level that would clear them; (4) the submission
  commit on FluBNF_submission, the compare link, Ely opens the hub PR.
  Until the branch is on main this lane runs the scratch copy
  (tools/tail_gate.py) with the same rule; the two agree.
- 2026-10-22 (04:46 UTC): GITHUB'S TESTS WORKFLOW IS GREEN ON main 744e654
  (the #46 merge; run 39721926994, success, 15 min), on the PR head
  0a45b16 (both the push and the pull_request runs) and on every dev
  commit since the rounding fix through 9376a25. Together with the cloud
  suite (04:35 UTC) that closes the check on the fix. The Model lane's
  note of 04:36 UTC: the Oracle SIHRS width screen on full seasons has
  started on the lab Mac, control first, the upper-tail rule scored
  after at 8x, 10x and 15x; this lane's cloud twin for those arms is in
  the entry of 04:40 UTC. The check-in that read this result is spent;
  nothing on main waits on this lane.
- 2026-10-22 (04:40 UTC): ELY IS RUNNING 8x, 10x AND 15x RETROSPECTIVES ON
  THE MAC FOR BOTH MEMBERS (the Oracle the longest). The cloud twin, run
  now so the Mac's numbers have something to check against: the 8x arm
  added to tools/shrinkloc_screen.py (post hoc on the stored cells, the
  Oracle's 44 stage-rule weeks at k = 0.7, the Groundhog's three retro
  seasons; replays/shrinkloc_result8.txt). relWIS natural, cov95, h3
  band/median typical:
    Oracle    k0.7 0.671 .930 4.6x | clip8 0.680 .884 3.4x | shrink8 0.699
              .840 3.4x | clip10 0.674 .898 | shrink10 0.688 .869 | clip15
              0.670 .917 | shrink15 0.674 .906
    Groundhog none 0.660 .936 4.7x | clip8 0.667 .912 3.9x | shrink8 0.687
              .881 3.9x | clip10 0.663 .921 | shrink10 0.676 .900 | clip15
              0.660 .931 | shrink15 0.664 .924
    Groundhog, September-October weeks only: none 1.024 | clip8 0.935 |
              shrink8 0.791 | clip10 0.963 | shrink10 0.823 | clip15 0.996
              | shrink15 0.913
  Reading: 8x shrink costs the Oracle 4.3% season-wide with 95% coverage
  down to 0.84, and the Groundhog 4% season-wide, while it is the best
  September-October form for the Groundhog (whose October cells sit at
  the baseline). The pattern is monotone: tighter helps the Groundhog's
  October and hurts everything else. History (Now, 04:20 UTC) puts 8x
  near the 80th percentile of realised October h3 growth, so an 8x cap
  on a 97.5% quantile under-covers by construction in a 2022-like
  October. The standing recommendation holds: shrink at 15x for both,
  10x if the first capped week scores well. What the Mac should
  reproduce: the cap is an output-stage rule on stored quantiles, so a
  retrospective on the same weeks should land on these numbers within
  rounding (the whole-admission rounding moves values by at most 0.5);
  a difference beyond that is a difference in the cells (weeks, the
  narrowing, the own-share form), not in the cap. The Model lane's
  retrospective is the record; this screen is the check.
- 2026-10-22 (04:35 UTC): THE FULL SUITE ON dev (519e20f, the rounding
  fix and the notes) PASSES IN THE CLOUD: exit 0, no failure, on the
  second run. The first run (stop at first failure) stopped at 88% on
  app/tests/test_season_run_marks.py::test_the_season_page_and_its_report_keep_one_mark
  (an extra "tip-restart" mark on the season page), a UI test the PR does
  not touch; the test passes alone on dev and on main before the fix
  (c401bbd), and the whole suite passed on the rerun, so it is an
  order-dependent flake in the season page's tests, not the cap's. Noted
  for the Model lane: the Mac's 22 failures are its setup; the cloud sees
  none. GitHub's tests workflow runs on 744e654 (main) and 519e20f (dev)
  were still in progress at this entry.
- 2026-10-22 (04:21 UTC): PULL REQUEST #46 (dev TO main) MERGED BY ELY AT
  04:21 UTC, merge commit 744e654 (two parents, aacbefd and 0a45b16; a
  merge commit), a minute after it opened. main now carries the rounding
  fix: the cap's moved levels are whole admissions in both forms. The
  Wednesday 2026-10-28 round runs main at or after 744e654. The full
  suite's cloud run on dev (275134e and after) was past 60% with no
  failure when the merge landed; its result is recorded below when it
  finishes. The PR subscription closed with the merge.
- 2026-10-22 (04:20 UTC): PULL REQUEST #46 (dev TO main) OPENED BY THIS
  LANE AT ELY'S WORD: https://github.com/elyfmiller/flubnf/pull/46,
  "Upper-tail cap: moved levels rounded back to whole admissions, kept
  monotone", 7 commits over main (aacbefd), 5 files, +202/-5. The Oracle
  SIHRS agent's fix (branch tail-cap-whole, b3992e7, merged into dev as
  275134e at Ely's word): the cap ran on hub rows already in whole
  admissions and wrote the moved levels back as decimals in both forms
  (about 2,000 values a member at 10x shrink on the 2026-10-24 files; a
  few hundred in clip mode from a non-integer limit), and one decimal
  turns pandas' value column to float, so every row would have read
  "14.0". whole_block rounds the moved levels half to even and keeps the
  block monotone; the limit is met within half an admission; untouched
  rows keep their integers. This lane's review: sound; a rounded shrunk
  level cannot fall below the integer median and a rounded clipped level
  cannot fall below an untouched level beneath the limit, so the
  monotone step never writes a float. tests/test_tailcap.py (12) and
  app/tests/test_knobs.py pass on dev, 153 tests; the full suite's cloud
  result to follow on the PR. No effect on the screens or the
  three-round review beyond rounding. The body carries no attribution
  (the integration's footer edited out at once). Ely's merge command, a
  merge commit, never squash:
  `gh pr merge 46 --merge --repo elyfmiller/flubnf`, or `git fetch origin
  main dev && git checkout main && git merge --no-ff origin/dev && git
  push origin main`. Subscribed to the PR; the Wednesday round runs main
  after this merge.
- 2026-10-22 (04:20 UTC): WHAT HISTORY SAYS THE CAP SHOULD BE (Spencer's
  method, run on our data). Spencer's reply to Ely: his team caps on
  "historic changes observed in the data over 4 weeks" and wants it as a
  topic for next Wednesday's forecasting call. Ely's question: every
  method knows too wide and too narrow but not the width that scores
  best. This lane's reading: WIS is proper, so the best width is the
  calibrated one, and the retrospective (coverage and relWIS by
  leave-one-season-out, which chose k = 0.7) is the estimate of it; the
  limit is the sample, four Octobers, not the idea. Spencer's bound and
  our n are estimates of the same quantity from the same data, so this
  lane computed his: the realised value over the recent level (mean of
  the last 3 weeks, as output.tail_cap defines it) for every jurisdiction
  and every week within 2 epiweeks of EW42 in 2022-2025. Jurisdictions
  with a recent level of 10 or more (474 cells per horizon): 97.5th
  percentile 3.8x at h0, 7.2x at h1, 11.4x at h2, 19.3x at h3; 95th 15.4x
  and 90th 11.8x at h3; the h3 maximum 37.8x. With all levels in, the
  tiny-base cells push h3's 97.5th to 34x (the Ohio-style cells, now
  tasked to the Model lane). Any week of the year at a level of 10 or
  more: h3 97.5th 10.9x, 99th 16.4x. So 15x on the h3 97.5% quantile is
  the October 95th percentile of realised growth, 20x is the 97.5th, and
  10x is near the 85th, below what a 97.5% quantile should allow if an
  October like 2022's recurs. The standing recommendation holds (the
  location-wide shrink at 15x for both members); 10x is a bet on a mild
  October, not a calibrated choice. Script: the inline computation in
  this lane's session, data the hub truth through 2026-10-17. Ely's
  draft reply to Spencer is unsent; this lane proposed one sentence
  carrying the 19x number and offering the comparison for Wednesday.
- 2026-10-22 (04:05 UTC): THE GROUNDHOG'S DOUBLE-PEAKED OHIO BAND IS A
  DEFECT, TASKED TO THE MODEL LANE (For other lanes, the Groundhog
  entry). Ely asked why Ohio's interval peaks at horizon 1, dips at
  horizon 2 and rises at horizon 3 (the 10-24 file: 97.5% quantile 763,
  3638, 936, 5864 at h0-h3 over medians 76-191). Cause, read from Ohio's
  own history in the truth file: Ohio reported 1, 10, 229, 17, 24
  admissions in the weeks of 2024-10-12 to 2024-11-09; the 229 of
  2024-10-26 is a one-week reporting spike. The own-state donor cell
  anchored on the 1 of 2024-10-12 carries growth ratios of 229x at
  horizon 1, 17x at horizon 2 and 24x at horizon 3, and under the
  own-share form (own cells at half the weight) that single cell sets the
  horizon-1 tail. The location-wide shrink keeps the shape by design, so
  the dip survives it; the clip flattens it. Ely: "this should be tasked
  to be fixed by the groundhog model, this is a bad defect". The scope
  across the EW42+-2 donor window, all states, four seasons (3,604 donor
  cells): 48 ratios above 20x, 38 of them from base weeks of 5 or fewer
  admissions; 11 above 50x, Ohio 229x, Idaho 141x, Texas 103x, Oregon
  75x, Arizona 68x, Minnesota 54x, Delaware 53x among them. This lane
  does not touch flubnf/analogue.py; the fix is the Model lane's. Until
  it lands, the cap is what keeps these cells out of the hub file.
- 2026-10-22 (03:43 UTC): PULL REQUEST #45 (dev TO main) MERGED BY ELY AT
  03:43 UTC, merge commit aacbefd (two parents, c401bbd and 1c7f7f8; a
  merge commit), three minutes after it opened. main now equals dev
  (1c7f7f8): the upper-tail cap and its two forms, the notes, the
  handoff. Wednesday 2026-10-28, Ely's laptop on main: the five override
  values (seed season_total_early, weight 0.25, narrowing 0.7, upper-tail
  cap n, upper-tail form), one reason; this lane's gate
  (tools/tail_gate.py, 30x) on both files before the submission commit.
  Ely's choice of mode and n is still open (this lane's reading: shrink
  at 15x for both members). The PR subscription closed with the merge
  and the check-in was cancelled.
- 2026-10-22 (03:40 UTC): tail-cap MERGED INTO dev (69f5fc4, a merge commit
  as Ely, at Ely's word) AND PULL REQUEST #45 (dev TO main) OPENED BY
  THIS LANE: https://github.com/elyfmiller/flubnf/pull/45, "Upper-tail
  cap for both members (clip or location-wide shrink), for the
  2026-10-28 round", 20 commits over main (c401bbd), 7 files, +866/-1:
  flubnf/tailcap.py, the two knobs, the pipeline wiring,
  tests/test_tailcap.py, docs/ORACLE-SIHRS.md 6c, the notes. Every commit
  authored and committed as Ely, no trailers; the body carries no
  attribution (the integration's footer edited out at once). Ely's merge
  command, a merge commit, never squash:
  `gh pr merge 45 --merge --repo elyfmiller/flubnf`, or `git fetch origin
  && git checkout main && git pull --ff-only origin main && git merge
  --no-ff origin/dev -m "Merge pull request #45 from elyfmiller/dev" &&
  git push origin main`. After the merge the laptop runs main on
  Wednesday with the override values (seed, weight, narrowing, the cap
  and its form) and the gate before the commit.
- 2026-10-22 (02:56 UTC): THE CAP KNOB IS ON BRANCH tail-cap FOR ELY'S MERGE
  INTO dev; THE LAST THREE ROUNDS REVIEWED WITH THE FIXES. At Ely's go
  ("write the cap knob, start at 15x"): flubnf/tailcap.py (CAP_PRODUCTION
  0 = no cap, RECENT_WEEKS 3; recent_level, limit_for, cap_block,
  cap_rows), the knob output.tail_cap (BOTH members, output stage,
  method class, 0-100; a run at n > 0 is a modified run, NOT_IN_RETRO),
  the wiring in app/ui/pipeline.py step 4 on both members' hub rows after
  the Oracle step, the narrowing and the floor (the run record carries
  n, the weeks and the cells touched per member), docs/ORACLE-SIHRS.md
  6c, tests/test_tailcap.py (7) and the knob default in
  app/tests/test_knobs.py; the full suite passed on the branch; commit
  1138da9 as Ely, pushed. Wednesday's run then sets four values by
  override: seed season_total_early, weight 0.25, narrowing 0.7, cap 15.
  The review (tools/review3_build.py, review3_score.py, review3_plots.py;
  review3/ in the Submission scratchpad; the figures sent to Ely): the
  rounds 10-10, 10-17 and 10-24 rebuilt with the fixes (Oracle: k 0.7
  post hoc where unnarrowed, cap 15x on the vintage's recent level;
  Groundhog: the own-share regeneration where the file was pooled, cap
  15x). Tails at h3 (typical state / max / states over 30x): Oracle
  15.5x / 134x / 7 -> 7.9x / 15x / 0 (10-10), 59.2x / 244x / 45 -> 14.4x
  / 19x / 0 (10-17), 20.4x / 55x / 9 -> 15.0x / 15x / 0 (10-24);
  Groundhog 25.2x / 56x / 11 -> 14.5x / 15x / 0, 21.1x / 46x / 1 ->
  14.5x / 19x / 0, 20.4x / 81x / 9 -> 15.0x / 15x / 0. Scores on the
  three scorable cell sets (47 models): Oracle fixed 0.613, rank 22 (as
  submitted 0.755, 36), log 0.731 (32); Groundhog fixed 0.856, rank 40
  (0.922, 42), log 0.715 (30). Against the members on 10-24 the fixed
  files sit inside the members' envelope with no flags but not at their
  typical width (h3 tail 15x against ABERT 6x, INFLAenza 8x, FourCAT 9x,
  epymorph and vulPES 12x; h3 band 5.4-5.7x against 2-5x); 10x would
  reach it. Week 1's Oracle cells are the old pin narrowed and capped,
  an approximation. Not yet independently verified.
  Added 03:05 UTC, Ely's variant screened: a target-driven narrowing
  instead of the clip (per block the smallest extra exponent about the
  median that brings the 97.5% quantile to the limit, k = ln(L/m) /
  ln(q/m), the shape kept, no ties; "up" = the levels above the median
  only, "sym" = the whole block; a block whose median is already above
  the limit is left alone). Oracle, 44 weeks, pooled relWIS natural /
  log, cov95: cap 15x 0.670 / 0.727, 0.91; adapt 15x up 0.673 / 0.731,
  0.91; adapt 15x sym 0.672 / 0.728, 0.91; adapt 20x up 0.671 / 0.728,
  0.93; adapt 10x up 0.681 / 0.741, 0.87; the residual share of h3
  cells over 30x 1.2-1.6% (medians already above the limit).
  Leave-one-season-out still picks the clip (20x, 20x, 15x). Groundhog:
  cap 15x 0.630 / 0.647; adapt 15x up 0.632 / 0.648; sym 0.631 / 0.648;
  adapt 10x up 0.637 / 0.654. Reading: the clip scores 0.2-0.5% better
  because it piles the excess mass at the limit, which WIS rewards
  whenever truth lands below it; the target-driven form keeps a smooth
  tail at that small cost. The hub's band plots draw the 50% and 95%
  edges, so a clipped file shows no staircase there; the ties are
  visible only in the quantile listing.
  Added 03:20 UTC, Ely's form as meant: a LOCATION-WIDE shrink,
  the exponent the worst horizon needs applied to every horizon of that
  location above the median (k_loc = min over h of ln(L/m_h)/ln(q_h/m_h)),
  so the band keeps its fan across the weeks and only the worst horizon
  touches the limit (tools/shrinkloc_screen.py, replays/shrinkloc_result
  .txt; review3/fig6, fig7). Oracle, 44 weeks, relWIS natural / log,
  cov95: clip 15x 0.670 / 0.727, 0.92; shrink-loc 15x 0.674 / 0.735, 0.91;
  clip 10x 0.674 / 0.732, 0.90; shrink-loc 10x 0.688 / 0.754, 0.87.
  Groundhog season-wide: clip 15x 0.660, shrink-loc 15x 0.664 (0.92);
  clip 10x 0.663, shrink-loc 10x 0.676 (0.90); September-October weeks:
  none 1.024, clip 15x 0.996, shrink-loc 15x 0.913, clip 10x 0.963,
  shrink-loc 10x 0.823. Reading: the location-wide form gives the right
  shape (the Groundhog's 10x box is gone) and the largest October gain,
  at a season-wide cost of 0.4-2.5% because it squeezes every horizon of
  a location whenever its far tail is wild, in season too; the clip is
  the better scorer on whole seasons, the shrink the better October
  forecast and the better-looking file. Ely's call; a mode on the knob.
  Added 03:38 UTC: the mode is on the branch (tail-cap aaa0e82, authored
  as Ely, the full suite green): knob output.tail_mode, choices clip
  (the registered default, flubnf.tailcap.MODE_PRODUCTION) and shrink
  (the location-wide form, exponent_needed and shrink_block in
  flubnf/tailcap.py; cap_rows takes the mode; the run record carries it);
  in effect only with output.tail_cap above 0; NOT_IN_RETRO like the cap.
  Wednesday's settings panel can set either form and any n; Ely's choice
  of mode and n is still open (this lane's reading: shrink at 15x for
  both members, 10x if the first capped week scores well).
- 2026-10-22 (02:39 UTC): THE TAIL SCREENS, BOTH MODELS: AN UPPER-TAIL CAP AT
  15x THE RECENT LEVEL CLEARS THE GATE AT NO COST ON THE REPLAYS. No engine
  time; the cap = every quantile above the median clipped at N times the
  recent level (the mean of the last three reported weeks at the as-of
  date, settled truth), applied after the narrowing; the cells, arms and
  summaries in replays/tail_screen_result.txt (Oracle; tools/
  tail_screen.py and tail_screen_summary.py; 9,152 cells of the 44
  stage-rule weeks at w 0.25; the k = 1 and k = 0.7 rows reproduce the
  shrink screen) and replays/gh_cap_result.txt (Groundhog;
  tools/gh_cap_screen.py on the own-share retro's 17,116 state cells,
  flubnf groundhog retro all --aux flusurv, which reproduces the record
  0.6604). Not yet independently verified (to do before Monday).
  - Oracle, pooled relWIS natural / log, cov95, h3 share of cells over
    30x: k 1.0 0.720 / 0.736, 0.99, 35%; k 0.7 0.671 / 0.727, 0.93, 15%;
    k 0.7 + cap 20x 0.669 / 0.726, 0.92, 0%; + cap 15x 0.670 / 0.727,
    0.91, 0%; + cap 10x 0.674 / 0.732, 0.90, 0%; k by horizon
    0.7/0.7/0.6/0.5 0.679 / 0.740, 0.89, 4.5% (squeezes every state:
    not the tool). Leave-one-season-out over all arms picks k 0.7 + cap
    20x twice and + cap 15x once; by block the cap changes nothing
    beyond the third decimal except early 2023-24 (0.829 -> 0.810).
  - Groundhog (own-share form), season-wide: no cap 0.660 / 0.650, cov95
    0.936; cap 20x 0.660 / 0.650; cap 15x 0.660 / 0.651, 0.931; cap 10x
    0.663 / 0.653, 0.921. In the September-October as-of weeks (772
    cells, where the form sits at the baseline, 1.024 / 0.747) the cap
    helps: 20x 1.008, 15x 0.996, 10x 0.963 (log 0.737), cov95 unchanged
    at 0.885; the h3 tail typical 20x -> 15x / 10x.
  - This week's files under the cap (tools/tail_gate.py arithmetic):
    Oracle at 15x: typical and maximum h3 tail 15x, band over median 5.4x
    (8.4x now), 39 states touched, the US untouched (53,025 is 11x);
    Groundhog at 15x: 15x / 15x, band 5.7x (7.6x now), 46 states touched,
    the US 78,635 -> 61,180. At 10x both would read 10x typical and
    3.7-3.8x bands, the members' range, at a replay cost of 0.005 (Oracle)
    and 0.003 (Groundhog season-wide, a gain of 0.06 in October).
  - Reading for Ely: ship k 0.7 plus a cap at 15x on both models for the
    2026-10-28 round (10x if the goal is the members' typical tail at
    once), by override with a card sentence, the gate run before the
    commit. The cap needs code: an output-stage knob for both models
    (output.tail_cap, N times the recent level, quantiles above the
    median only, recorded in the run record), on a branch with Ely's go,
    then dev to main before Wednesday. The structural Oracle work (prior
    bounds, swarm carry) stays with the Model lane.
- 2026-10-22 (02:26 UTC): SPENCER'S RED FLAGS ON ROUND 2026-10-24; THE TAIL
  GATE; ELY'S GOAL FOR 2026-10-28. Spencer Fox's mail to Ely and Rich
  (2026-10-21 18:47 MST, "Red flags from report", his NAU-ensemble round
  report attached): "the forecasts this and last week triggered some red
  flags", 10 of them, all ours and all the far-horizon upper tail
  (97.5% quantile at horizon 3 against the recent level): Groundhog AZ
  40x, ID 66x, OH 84x, OR 43x, TX 47x, WV 36x; Oracle IA 32x, MI 40x, NH
  38x, WV 39x. His member table has our last-horizon medians in line
  with the other members (typical ratio to the others' median 1.05x
  Groundhog, 1.04x Oracle; more than 1.5x apart in 4% and 13% of 53;
  FourCAT 0.75x / 38%, Copycat 1.58x / 64%). He keeps both models in the
  NAU ensemble and asks for a chat and a plan; Ely offered Monday after
  2pm or Wednesday morning and replied (the text in chat; the cause by
  model, the narrowing as the first attempt, why we submitted, the 30x
  rule adopted, the screen starting, and that he may drop either model
  if it keeps flagging).
  - Why this lane did not catch it: the sense check measured width as
    the 95% band over our own median, summarised by the median across
    states (8.3x at h3 this week), and reported the extremes (Wyoming
    28x, Ohio 31x) as the widest, not as failures; Spencer's rule
    measures the 97.5% quantile against the recent observed level per
    state with a threshold, and at h3 our medians are already 2-3x the
    last count, so Michigan reads 21x by ours and 40x by his. No rule in
    the check stopped the commit. Owned by this lane.
  - The gate, from tonight (tools/tail_gate.py in the Submission
    scratchpad; to go into scripts/sense_check.py on a branch for Ely's
    merge): 97.5% at each horizon over the recent level (mean of the last
    three reported weeks), FAIL when any horizon-3 ratio exceeds 30x. On
    this week's files it fails both: Oracle 9 states (WV 55x, ND 44x, CT
    43x, MI 43x, MD 42x, NH 40x, VT 39x, NM 35x, DE 32x; typical state
    20x; the other teams' files 8-12x typical, 0-4 states over 30x),
    Groundhog 9 (ID 81x, OH 80x, TX 58x, WV 52x, OR 51x, AZ 36x, TN 34x,
    DE 33x, CT 31x). A file that fails the gate is not staged.
  - Ely's goal (2026-10-22): by the 2026-10-28 round both models' width
    near the NAU ensemble members'. Targets this lane will screen
    against: no state over 30x at h3, the typical state's 97.5% over the
    recent level near 10-12x (the members' range this week), the 95% band
    over the median at h3 near 3-5x. The screen (tools/tail_screen.py,
    no engine time, the 44 stored stage-rule weeks): narrowing exponent
    by horizon, an upper-tail cap at N times the recent level after the
    narrowing (N 10-30), combinations; leave-one-season-out; the gate as
    a column; the Groundhog next (the cap on its retro cells, the Model
    lane's kernel arm). Result and recommendation by Monday 2026-10-26.
  - This week's submission stands as committed (2526b906); the files
    passed the hub's checks and Spencer keeps them in his ensemble.
- 2026-10-21 (19:00 UTC): WEEK 2 SCORED AT HORIZON 0 (the 2026-10-17 round
  against the week ending 10-17, truth as on the hub 10-21, 84ced076; 57
  models with 50+ cells; relative WIS against FluSight-baseline on common
  cells; the same inline scorer as week 1). Oracle SIHRS as submitted
  (unnarrowed, stage rule, w 0.25, Alaska dropped): relWIS 0.802, rank 46
  of 57; log 0.789, rank 42; coverage 50/95 0.82/1.00; US WIS 405 (truth
  4,698, our median 4,772). The narrowed re-run of the same week
  (tested in the app 2026-10-16, the configuration that ships from this
  round): 0.629, rank 27; log 0.712, rank 25; coverage 0.67/1.00; US
  281. Groundhog (pooled form): 0.975, rank 51; log 0.754, rank 39.
  FluSight-ensemble 0.557 (11) / 0.644 (3); DMAPRIME-HYB 0.518 (4) /
  0.632 (1); field median 0.650 / 0.723; NAU-ABERT 0.594, NAU-vulPES
  0.680, NAU-FourCAT 0.689, NAU-epymorph 1.030. Reading: the baseline is
  beaten in both weeks (week 1 0.902, week 2 0.802 as submitted); with the
  narrowing the week-2 gap to the ensemble at horizon 0 is 13% natural
  and 11% log, mid-field; the remaining gap is the medians (the log rank
  25 against the ensemble's 3) and the horizon-3 width, which no cell
  scores yet. This week's submission (round 10-24) ships the narrowed
  configuration, so its horizon-0 standing should resemble the re-run's.
  Early field for 10-24 (seven files on the hub at 17:46 UTC): the
  Oracle's h0 band 1.83x the median is mid-field (Cornell 1.03,
  HallAI 1.75, epymorph 2.00, CountCast 2.55, baseline 4.40); at h3
  8.32x against the baseline's 7.43x and the others' 2.0-4.8x, the
  Groundhog 7.59x; US h3 medians: ours 11,961 and 11,724, epymorph 9,301,
  CountCast 9,317, Cornell 22,724.
  Added 19:40 UTC, the revised pair inferred on the same 156 cells (47
  models with all three cell sets; ranks = where the revised row would
  sit among them): the Oracle narrowed after the fact (week 1 from the
  submitted old-pin file at k = 0.7, week 2 the live re-run) pooled
  0.614, rank 22 (week cells 0.664 / 0.572 / 0.629), log 0.734, rank 33;
  the Groundhog in the own-share form (flubnf groundhog retro 2026-27
  --aux flusurv --with-us at own share 0.5 on bd6242f, the 10-10 vintage
  reproducing Ely's re-run file median for median) pooled 0.871, rank 41
  (0.877 / 0.838 / 0.913), log 0.715, rank 30. As submitted: Oracle 0.755
  (36) / 0.801 (36), Groundhog 0.922 (42) / 0.713 (29); ensemble 0.498
  (4) / 0.598 (4); INFLAenza 0.506 / 0.596; vulPES 0.693 / 0.681;
  FourCAT 0.700 / 0.778; epymorph 1.030 / 0.888; field median 0.631 /
  0.689. Week 1's Oracle cells are the old pin narrowed, not the stage
  rule, so the inferred standing is an approximation of the shipping
  configuration there.
- 2026-10-21 (18:10 UTC): ROUND 2026-10-24 (EW42) STAGED FOR ELY'S PULL
  REQUEST. Ely sent the two files from the laptop's run on main (c401bbd)
  with a weekly report; the report is LAST week's (reference date
  2026-10-17, data through Oct 10, knobs digest 3d7ef6b7: seed rule and
  weight only), so this week's run record (the narrowing block, the
  knobs digest, the override reason) is not confirmed from the files
  here; asked Ely for this week's report, which came within the hour
  and confirms the run: reference date 2026-10-24, data through Oct 17,
  model settings "Seed denominator expected total (early season),
  Oracle blend weight 0.25 (default 0.5), Spread narrowing 0.7
  (default 1)", Groundhog "own-state donors 0.50", exported under the
  hub names by override, reason "Early Season Issues", app build
  6075c03 (dev at that hour: main's code plus this lane's notes
  commits, no code difference). The files themselves carry the
  narrowing: the Oracle's 95% band over the median is 1.83x at h0 and
  8.32x at h3 (median over 53 locations; 1.96x and 9.56x on last week's
  narrowed re-run; 3.28x and 25.5x unnarrowed), 50% band 0.52x and
  1.58x; widest h3 Wyoming 28.3x. The Groundhog in its own-share form:
  3.67x and 7.59x (last week's re-run 3.98x and 8.37x), widest h3 Ohio
  30.6x. Both files: 4,877 lines, 53 locations (Alaska and US in),
  horizons 0-3 for 2026-10-24 to 2026-11-14, 212 monotone blocks each,
  integers; both pass all 30 hubValidations checks against cdcepi main
  a0215ecc (TZDIR set, the conda R). Truth now through 2026-10-17 (hub
  target data 84ced076): US 4,698 (1.16x the week before); the 10-10
  week revised up 5.4% (US 3,835 -> 4,044; states median +5.5%, 10th-90th
  1.00-1.23). Sense check against the last observed week: Oracle h0
  medians 1.22x it (10th-90th 1.00-1.37; US 5,907 = 1.26x), the last
  observed inside the h0 50% band in 0.79 and the 95% band in 1.00 of 53;
  h0 median below the last observed in Alaska, Hawaii, Maine, Montana and
  Wisconsin (0.89-0.94); h3 medians 2.26x (US 11,961 = 2.55x). Groundhog
  h0 1.10x (1.00-1.15; US 5,168), the last observed inside its 50% band
  in 0.98 of 53. Both plausible beside last week's growth (states median
  1.14x, US 1.16x). The US at h3: Oracle 2,208-11,961-53,025, Groundhog
  1,918-11,724-78,635. Submission: FluBNF_submission fast-forwarded to
  cdcepi main a0215ecc (the cdc remote's fetch failed on the proxy's
  stale name, the URL fetch worked: the fork's repository name is now
  FluSight-forecast-hub, mixed case), the two files added under
  model-output/NAU_PyBNF-OracleSIHRS/ and model-output/
  NAU_PyBNF-GroundHogCGR/, byte-identical to the uploads, commit 7b80f676
  "NAU_PyBNF forecast 2026-10-24 (EW42)" as Ely (a first push had the
  files under a wrong folder and was amended and force-pushed within
  minutes on this lane's own branch, before any pull request), pushed to
  the fork; at 19:50 UTC, with Ely's go to open the pull request, cdcepi
  main had moved again (1bfa4b26, other teams' files), so the commit was
  re-based onto it as 2526b906, the same two files, one commit over
  main, force-pushed with lease on this lane's own branch before the
  pull request. Compare link for Ely's hub pull request:
  https://github.com/cdcepi/FluSight-forecast-hub/compare/main...elyfmiller:FluSight-forecast-hub:FluBNF_submission?expand=1
  (the hub's PR validation runs the same 30 checks). Three other teams'
  10-24 files were on cdcepi main at 16:33 UTC; the field comparison
  follows when more are in.
- 2026-10-21 (01:30 UTC): THE Reff PRIOR BOUND ARM, SCORED; RECOMMENDATION:
  NOT FOR WEDNESDAY, RUN THE 44-WEEK SCREEN FIRST. The arm (the entry of
  2026-10-20 22:52 UTC; relaunched 00:10 UTC after the container paused
  the first attempt, done 00:56; the 10-10 stage control done 01:12;
  14-16 minutes a week) against the stage replays, all at w = 0.25
  (tools/reff_compare.py, replays/reff_result.txt; an independent
  recompute reproduced every figure and a skeptic's pass added the
  corrections below, replays/verify-reff/):
  - Bands (95% band over the median, median over the 52 jurisdictions):
    h3 43.2x -> 37.2x (09-26), 27.2x -> 22.8x (10-03), 25.5x -> 21.4x
    (10-10); per-location band ratio 0.86-0.87 at h3 (10th-90th 0.72-1.07,
    narrower in 40-46 of 52), 0.95 at h0; the filter alone 38.9 -> 34.5,
    24.5 -> 20.0, 22.2 -> 19.2 at h3; narrowed at k = 0.7, h3 9.60x ->
    8.46x on the 10-10 vintage. The change is real in aggregate (paired t
    -6 to -8 over the jurisdictions; the five Oracle seeds spread the band
    by only 2-5%) and not resolved in any single jurisdiction (one
    replicate against another spans 0.75-1.36; Welch t resolves 7-11 of
    52). Same at w = 0.5 (0.85-0.87).
  - Medians: within 1% at h0; at h3 DOWN 2-3% (ratios 0.97-0.98; 12 of 51
    jurisdictions more than 5% below the submitted 2026-10-17 file). Not
    "unchanged".
  - Scores on the 156 scorable cells (09-26 h0 and h1, 10-03 h0): WIS
    15.17 -> 14.60 unnarrowed (ratio of sums 0.963; location-cluster
    bootstrap 0.95-0.98), 12.48 -> 12.15 narrowed (0.973; 0.96-0.99); log
    0.286 -> 0.283 and 0.268 -> 0.267, the narrowed log gain unresolved
    (0.987-1.001). The whole gain is dispersion (11.37 -> 10.80; the
    penalty 3.80 unchanged): the arm is narrower, not more accurate; five
    large jurisdictions carry 57-70% of it, California loses. Coverage at
    k = 0.7 identical in both arms (0.56 / 0.88 / 0.97 at 50 / 80 / 95 on
    these h0-h1 cells); at k = 1 the 50% coverage slips 0.737 -> 0.718.
  - The bound buys what the narrowing already buys: on the 10-10 vintage
    the arm at k = 1 has the stage's band at k = 0.95, and the arm at k =
    0.7 equals the stage at k = 0.66. The forward paths show no use of the
    trimmed region at the origin (effective Reff 99th percentile 1.5-1.6;
    under 0.3% of paths above 2.0), and the base Reff is modulated by the
    harmonic (eps1 0-1), so the bound caps the parameter, not the
    effective number. No fast-growing cell this October lost coverage
    (the 20 cells with truth at 1.8x the anchor or more: 403 -> 399 WIS).
  - Not screened: h2-h3 (where the bound acts three times as strongly as
    at h0) and any past season; k = 0.7 was chosen with the unbounded
    prior. Against the team's own standard for the narrowing (44 weeks,
    three seasons, 9,152 cells, leave-one-season-out, bootstrap) this is
    156 in-sample cells of one season at h0-h1.
  - The cloud reproduces the laptop: the 10-10 stage control's medians
    match the submitted 2026-10-17 file (ratio 0.997 at h0, 0.996 at h3,
    38 of 51 h0 medians identical after rounding) and its h3 band 25.49x
    against the file's 25.50x; the cloud is a faithful testbed for the
    live configuration.
  - Reading for Ely: do not add the bound on Wednesday. It is a fourth
    override on the registered member, it is nearly interchangeable with
    a narrowing exponent 0.05 lower, it lowers the horizon-3 medians, and
    it is unvalidated beyond the weeks that motivated it. The proper test
    is the 44-week screen (15-23 minutes a week in the cloud, 11-17 hours,
    the step and the narrowing re-chosen jointly: k against the bound,
    leave-one-season-out), feasible before the 2026-10-28 round on Ely's
    word. If Ely ships it anyway, the override reason must name it
    separately ("pf.prior.Reff 0.6-2.0, knobs digest d48a070d, screened on
    three 2026-27 vintages at horizons 0-1, not replay-scored on past
    seasons") and the "all replay-scored" phrase cannot cover it; the card
    needs a sentence for it, as for the narrowing. Wednesday stays at the
    three values.
- 2026-10-20 (22:52 UTC): THE Reff PRIOR BOUND ARM IS RUNNING IN THE CLOUD AT
  ELY'S GO. Ely's reading of the width (the swarm is still dispersed early
  in the season) and the answer that the jitter does not set the cloud's
  width (the Liu-West kernel preserves its covariance; pf_jitter 0.15,
  pf_shrink 1, forecast jitter 0, variance floor 1e-12; the engine
  resamples under ESS 0.5 N and records ESS after every update) led to
  the cheapest structural arm: the Reff prior's upper bound 2.0 against
  the shipped 2.5 (uniform 0.6-2.5, app/core/engines/pf.py VARS_1S),
  which the console already exposes as the knob pf.prior.Reff ("Prior
  range for Reff", Model settings, the filter group), so it needs no code
  and can run on Ely's laptop on Wednesday if it wins. Ely: "worth
  testing ... compare it for the last two forecasts ... if cheap, apply
  tomorrow". Running (replays/reff.sh, reff.log, the worktree at main
  c401bbd, engine 2fdadee0, the hub mirror's three 2026-27 vintages
  09-26, 10-03 and 10-10, the 10-10 file taken from cdc/main 86b03824):
  root replays/2026-27-reff20, knobs pf.seed_denominator=
  season_total_early and pf.prior.Reff=0.6,2.0 (knobs digest d48a070d),
  all 52 jurisdictions, 10,000 particles, 3 replicates, width 4, the
  Oracle step applied (w 0.5 primary, 0.25 logged); then the stage
  control for the 10-10 vintage (replays/2026-27-stage-1010), which the
  stored stage replay lacks. About 20 minutes a week on this machine.
  The comparison to follow: bands (95% band over the median, the upper
  quantile over the median) and medians per location and horizon, arm
  against stage, at w 0.25, with and without the narrowing 0.7; the
  scorable cells (09-26 h0 and h1, 10-03 h0 against the 10-14 truth)
  scored arm against stage; the 10-10 vintage against the submitted
  2026-10-17 file and the field's bands. A Reff bound is a change to the
  registered member (the frozen pre-registration), so it ships by
  override and a card sentence, like the narrowing.
- 2026-10-20 (22:40 UTC): PULL REQUEST #44 (dev TO main) MERGED BY ELY AT
  22:40 UTC, merge commit c401bbd (two parents, e97b227 and 4e764a0; a
  merge commit, as the rule says), three minutes after it opened, before
  CI had finished on the head (the same commits had passed the suite on
  dev). main now equals dev (4e764a0): the narrowing knob oracle.narrow,
  its record and tests, ORACLE-SIHRS.md 6b, and the lane notes are on
  main. Wednesday 2026-10-21, Ely's laptop on main: Seed denominator
  season_total_early, Oracle blend weight 0.25, Oracle narrowing 0.7, one
  override reason (suggested: "2026-10-12 and 2026-10-16 decisions:
  expected-total pin early in the season, Oracle weight 0.25, spread
  narrowing 0.7, all replay-scored; docs/team/submission.md"); the
  Groundhog in its own-share form (no knob to set, it is the default);
  export, sense_check.py (Ohio, Texas, Delaware at horizon 3 in the
  Groundhog file), then the two CSVs to this lane for the validator, the
  fast-forward of FluBNF_submission to cdcepi main, the commit "NAU_PyBNF
  forecast 2026-10-24 (EW42)" and the compare link. This lane's PR
  subscription closed with the merge and its check-in was cancelled.
- 2026-10-20 (22:37 UTC): PULL REQUEST #44 (dev TO main) OPENED BY THIS LANE
  AT ELY'S WORD: https://github.com/elyfmiller/flubnf/pull/44, "Oracle
  narrowing knob and the lanes' notes, for the 2026-10-21 round", 18
  commits over main (e97b227), 10 files, +961/-4: flubnf/oracle.py (the
  knob), app/core/oracle.py and app/core/knobs.py (oracle.narrow),
  tests/test_oracle.py, docs/ORACLE-SIHRS.md 6b, the lane notes. Every
  commit is authored and committed as Ely (bf044bd is Ely's own merge of
  oracle-narrowing from the laptop), no trailers; the body carries no
  attribution (the integration appended its footer again and it was
  edited out at once). Ely's merge command, a merge commit, never squash:
  `gh pr merge 44 --merge --repo elyfmiller/flubnf`, or `git fetch origin
  && git checkout main && git pull --ff-only origin main && git merge
  --no-ff origin/dev -m "Merge pull request #44 from elyfmiller/dev" &&
  git push origin main`. After the merge Ely's laptop runs main on
  Wednesday with the three values and one override reason.
- 2026-10-20 (UTC): ELY'S HYPOTHESIS, AN OWN-LOCATION WEIGHT ON THE ORACLE
  STEP'S DONORS, AGAINST THE STORED BANK. Ely asked whether weighting the
  Oracle step's donor draw toward the forecast location's own paths (the
  Groundhog's own-share idea) would reduce the member's width further,
  since after narrowing it is still the widest but one at horizon 3. What
  the stored stage replays say (oracle_bank/paths_<asof>.csv, as-of
  2026-09-26 and 2026-10-03):
  - The pool is small, not thousands: 288 and 318 admissions donor paths
    per week from 32 and 34 locations (the four seasons 2022-23 to
    2025-26, two epiweeks either side, the 10-admissions floor on
    W-1..W+2). Own-location paths: none for 21 and 19 of the 53
    locations in those weeks (Alaska, Colorado, Connecticut, Delaware,
    DC, Idaho, Iowa, Kansas, Maine among them), 1-4 for 8 and 10, 10 or
    more for 13 and 15 (the maximum 20: US, Florida, California), median
    2-3. An own share of 0.5 would put half the draws on a handful of
    paths for most states and on nothing for a third of them (the class
    would pass its share to the rest, as local_weights does).
  - The donors are not the width, and own-location donors are no tighter:
    the pool's four-week ratio rho_4 spans 0.86-1.27 (2.5th-97.5th
    percentile, sd of the log 0.09-0.10); Florida's own 20 paths span
    1.01-1.43 (sd 0.09), California's 0.96-1.22 (0.07), Texas's 0.92-1.16
    (0.07), New York's 0.88-1.21 (0.10), US 0.96-1.22 (0.06). The member's
    width is the filter's own forecasting sample (15.2x the median at h3
    on the 10-03 vintage under the stage rule, 7.0x under the old pin),
    which the step multiplies by 1.5-1.8x (the entry of 2026-10-16);
    weighting the draw can touch only that factor, and with donor spreads
    this small it would move it little. Medians: own-location median
    growth sits within 0.02-0.05 of the pool's (FL 1.05 against 1.04, NY
    1.09-1.11), so a small median shift at most.
  - Reading for Ely: as a width lever this is unlikely to pay, by the
    counts; the lever that reaches the field (h3 median 3.6x; ours 9.6x
    narrowed, the baseline 9.0x) is the filter's own early tail under the
    new seed (a Reff upper bound, a growth cap or the jitter: the engine
    arm, about 10 hours per arm in the cloud on the 44 stored weeks, the
    Model lane's item), which could change the medians too. If Ely wants
    the number rather than the argument, an own-share draw (a weighted
    index in flubnf.oracle.mixture_rows) can be screened on the stored
    samples of the 44 weeks without engine time, pre-registered, arms
    0.25 / 0.5 on the admissions half, with and without the narrowing;
    the member is the registered one (frozen pre-registration 67c9fa49),
    so any change ships by override and a card sentence, as the narrowing
    does.
- 2026-10-20 (UTC): THE NARROWED FILES VALIDATE; THE WIDE BANDS AGAINST THE
  NARROWED, SCORED AND BREAK-EVEN. Ely asked whether the narrowed forecast
  is acceptable to submit and how badly the wide one scores against it.
  - Validation: the two -modified files of the 2026-10-16 re-run (Oracle
    narrowed k = 0.7, Groundhog own-share), renamed to the hub pattern,
    pass all 30 hubValidations checks against the hub clone (the conda R
    in the Submission scratchpad, TZDIR set), max_hosp_popn_frac included.
    The hub's plausibility bound is 30% of the location's population
    (model-output/README.md, "Plausibility bounds"), so the wide file was
    never near it either: the US h3 upper quantile as submitted is 33 per
    100k (112,688), narrowed 15.5 (52,632), the ensemble 6.4 (21,681).
  - Scored where truth exists (the 2026-10-10 round at h0, the entry of
    2026-10-17 00:30 UTC): WIS 17.23 -> 14.47 (-16%), relWIS 0.902 ->
    0.759, rank 36 -> 24 of 52; US 295.8 -> 212.0.
  - Break-even on the 2026-10-17 round (tools/us_bands.py and an inline
    scorer; truth lands from 2026-10-22): for the US the narrowed band
    scores better whenever the count lands between 0.72x and 1.3x the
    median at h0 (3,450-6,160 around 4,772), 0.53x-1.5x at h1,
    0.21x-1.9x at h2, and anywhere up to 2.4x at h3 (21,640 around
    8,908); if the count lands at the ensemble's median the wide band
    scores 1.45x the narrowed at h0 (405 against 280; the ensemble 239)
    and 1.6x at h3 (3,084 against 1,897; the ensemble 835). The width
    cost alone (WIS at the median, summed over h0-h3): 5,894 as submitted,
    3,717 narrowed, 2,065 the ensemble. States (52 x 4 cells): the narrowed
    band is better within 0.54x-1.5x of the median at h0 (median over
    locations) and up to 3.5x at h3 (10th-90th percentile 2.5x-5.5x); in
    115 of 204 cells it is better for any count within a factor of two
    of the median either way.
  - Ely's question of the same hour, the weights: the Groundhog's own
    share (0.5 of the admissions-pool weight on the jurisdiction's own
    donor cells) is NOT applied to the Oracle step, whose donor pool is
    pooled across locations, the US row included (ORACLE-SIHRS.md,
    section 1; model.md Decided 2026-10-15: "the Oracle SIHRS is
    untouched (its pools never pass local)"). The Oracle's "weight one
    half" is a different quantity: the blend weight oracle.w between the
    filter's own growth and the donor path's (shipped 0.5, run at 0.25 by
    override from the 2026-10-17 round). An own-location form of the
    Oracle's bank has not been screened; its donor ratios are tight
    (0.6x-1.3x over four weeks), so the donors are not its width, but
    whether own-location donors would move its medians is an open
    question for the Model lane (a pre-registered screen, as for the
    Groundhog).
- 2026-10-20 (UTC): ELY'S MEETING BRIEF, TWO POINTS, SHORT AT ELY'S WORD (a
  full verification workflow was started and stopped when Ely asked for a
  sentence or two per point; these facts are from the files and two
  searches).
  - The Groundhog's shape. Until 2026-10-15 every jurisdiction's Groundhog
    had one shape: one pooled ratio distribution scaled by the
    jurisdiction's own anchor (DONOR-BANKS.md, section 6 and "Own-state
    weighting"). Measured on the 2026-10-17 files: the submitted (pooled)
    file's h3/h0 median ratio runs 2.00-2.33 over the 53 locations
    (coefficient of variation 0.04); the own-share re-run's runs 1.59-2.67
    (0.11). The shipped form from the 2026-10-21 round (#43): the
    jurisdiction's own donor cells carry half of the admissions-pool
    weight and the other 51 jurisdictions share the other half (each own
    cell about fifty times an outside cell), as a weighted empirical
    quantile; HHS-region weighting added nothing; the FluSurv-NET pool
    stays pooled and enters at weight one half by quantile averaging, so
    that half of the shape is still shared. The h3 95% band / median:
    pooled 8.4-9.8x (median 9.0); own-share median 8.4x but Ohio 27.7x,
    Texas 20.0x, Delaware 17.6x, Arizona 17.2x (their own October
    histories), a sense-check item for Wednesday's run.
  - Other teams, from the hub's 118 cards: three describe a post-hoc
    calibration of the quantiles. DMAPRIME-HYB (first in the week-1 field
    score, 0.597): "the spread around the median is scaled by per-target,
    per-horizon calibration factors chosen to minimize WIS on past
    out-of-sample forecasts", the same move as oracle.narrow;
    CMU-TimeSeries_Cal: online quantile calibration, MultiQT (Ding, Gibbs
    and Tibshirani, arXiv 2512.23671, additive offsets per level by online
    gradient descent); UM-DeepOutbreak: adaptive conformal inference post
    hoc. Literature for the justification (records seen): Rumack,
    Tibshirani and Rosenfeld 2022, PLOS Comput Biol 18(12) e1010771,
    "Recalibrating probabilistic forecasts of epidemics" (post-hoc
    recalibration of 27 FluSight Network forecasters, better calibration
    and log score); Gneiting, Raftery, Westveld and Goldman 2005, Monthly
    Weather Review 133:1098-1118 (EMOS: the ensemble spread rescaled by
    fitted coefficients, the standard post-processing in weather);
    Bracher, Ray, Gneiting and Reich 2021, PLOS Comput Biol 17(2) e1008618
    (the WIS and its dispersion / over / under decomposition, the hub's
    score). Material for the narrowing's card sentence when the default
    flips.
- 2026-10-17 (00:30 UTC): "IF WE HAD SUBMITTED THIS A COUPLE OF WEEKS AGO":
  THE NARROWING SCORED ON THE 2026-10-10 WEEK, BEFORE AND AFTER. Ely's
  question of 2026-10-16. What can be scored: the week ending 2026-10-10
  (truth as on the hub 2026-10-14, still revisable) at horizon 0 of the
  2026-10-10 round, and the stored stage-rule replays
  (replays/2026-27-stage: as-of 09-26 at h0 and h1, as-of 10-03 at h0, 52
  locations, no US). "After" is the quantiles narrowed about their median
  with k = 0.7 (flubnf.oracle.narrow_quantiles); the live knob narrows the
  samples before the output floor and the rounding, and a simulation of
  both orders on the 53 cells agrees to 0.02% of the mean WIS (the largest
  cell gap 0.5 WIS, Vermont at median 1). Script tools/narrow_score.py,
  outputs narrow-test/score_result.txt and score_cells.csv in the
  Submission scratchpad; two independent recomputations and a skeptic's
  pass (narrow-test/verify/) match all 418 cell scores to 1e-13.
  - First, what the 2026-10-10 round was: the shipped configuration (the
    to_date pin, weight 0.5), not the stage rule. The 2026-27-shipped cloud
    replay (same engine commit, same seeds) reproduces the submitted file's
    medians to rounding (median ratio 0.994), while the stage replay of the
    same data week (as-of 10-03, season_total_early, w 0.25) runs 14.5%
    higher (10th-90th percentile 1.07-1.27, higher in 50 of 52 locations).
    The weight is not the cause (w 0.25 against 0.5 in the same replay:
    ratio 0.995); the seed rule is.
  - The submitted round, horizon 0, 53 locations, before -> after (k =
    0.7): mean WIS 17.23 -> 14.47; log WIS 0.211 -> 0.196; relWIS against
    FluSight-baseline (52 common cells, no Iowa) 0.902 -> 0.759, rank 36
    -> 24 of 52 models; log relWIS 0.924 -> 0.864, rank 38 -> 36; coverage
    50/80/95 0.79/0.94/1.00 -> 0.68/0.89/0.96; hub decomposition
    (dispersion + over + under) 12.91 + 0.65 + 3.67 -> 8.86 + 0.88 + 4.73;
    MAE 18.8 unchanged (the medians hold). Rounding the narrowed quantiles
    to integers as a submission would: 0.758 / 0.862, 50% coverage 0.72,
    ranks unchanged. Better in 45 of 53 locations (US -83.7, Florida
    -16.3, California -9.6, Texas -7.7, New York -4.8; worse in Illinois
    +11.7, Puerto Rico +10.3, Pennsylvania +2.5, the median misses). US:
    truth 3,835, median 3,648, WIS 295.8 -> 212.0 (baseline 429.6,
    ensemble 184.0). The field for reference: median 0.803 / 0.811,
    ensemble 0.665 (12) / 0.735 (8), Groundhog 1.106 (44) / 0.832 (29).
  - The qualifications (the skeptic's, confirmed from the cell table): the
    US row carries 57% of the gain; on the 51 state cells the move is
    relWIS 1.061 -> 0.956 (rank 38 -> 32) and log 0.931 -> 0.872 (38 ->
    36), from worse than the baseline to a little better. Among the 47
    models with 50 or more common cells the ranks are 33 -> 21 natural and
    33 -> 32 log (three of the 52 have one or two cells). On the log scale,
    CDC's headline, the move is two places and the standing is set by the
    median misses (Vermont, Illinois, Puerto Rico, Idaho, Montana, New
    Hampshire), which the narrowing does not touch. Truth revisions cannot
    flip the ordering: it takes a joint rise of about 25% in every 10-10
    count or a US value above about 5,000 (the lag-0 revisions so far are
    +5-6% for US, which widen the gain). k = 0.7 was chosen on 2023-24 to
    2025-26 only (the 9,152-cell screen rebuilt from the stored records,
    0.720 -> 0.671 reproduced), so this season's cells did not enter the
    choice of k, though the lever itself was picked after the week-1 score
    showed the width.
  - The current configuration (the stage replays, w 0.25, 52 locations),
    before -> after: as-of 09-26 h0 (week 10-03) WIS 11.04 -> 9.39, log
    0.302 -> 0.295, 50% coverage 0.65 -> 0.48; as-of 09-26 h1 (week 10-10)
    19.87 -> 15.04, log 0.321 -> 0.288, 0.83 -> 0.67; as-of 10-03 h0 (week
    10-10) 14.59 -> 13.01, log 0.235 -> 0.221, 0.73 -> 0.52, 95% coverage
    1.00 -> 0.96; against the baseline on the 51 state cells relWIS 1.304
    -> 1.166, log 1.027 -> 0.971. Pooled over all 209 scored cells (two
    truth weeks; the 10-10 week enters three times): WIS 15.69 (11.76 +
    1.35 + 2.58) -> 12.99 (7.81 + 1.84 + 3.33), -17%, log 0.267 -> 0.250,
    lower in 176 of 209 cells (log 163); the two ties are Delaware at
    median 0.
  - For the Model lane, a watch item and not a decision: on the 10-10 week
    the stage rule's medians would have scored worse than the old pin's on
    the same 51 state cells (1.304 against 1.061 natural, 1.027 against
    0.931 log, both before narrowing). The state medians sum to 4,177
    against a truth of 3,835 (1.089, above truth in 37 of 52) where the
    old pin's sum to 3,565 (0.930, above in 30 of 52); the old pin's misses
    are under-prediction (0.30 of its WIS, 0.06 over), the stage rule's are
    split (0.16 under, 0.17 over). One week, one vintage, at the rule's
    first week; the 2026-10-17 round's live medians sit at the field's
    median (US 4,772 against the ensemble's 4,831; Now, 2026-10-16), and
    its truth lands 2026-10-22.
  - This season's one-week optimum is below 0.7 (natural WIS still falling
    at k = 0.5: 13.27 on the submitted h0, 12.00 pooled; log optimum 0.6),
    but 50% coverage at k = 0.5 is 0.35-0.55 where k = 0.7 holds the
    replays at nominal (0.48-0.52 at h0), and the screen said the same (k
    = 0.5 worse in every block on the log scale). 0.7 stands. The gain is
    large this fortnight because truth landed near the medians (width is
    0.75 of the submitted WIS against the screen's 0.56; across the
    screen's 24 block-season-horizon groups the width share predicts the
    k = 0.7 gain with r = 0.96, and the groups at 0.72-0.80 gained
    15-25%), not because early-season weeks gain in general: the screen's
    early-season h0-h1 cells gained 1.5% pooled and lost 5% in 2025-26.
    Nothing can be said this season for h2-h3, where the screen's gain is
    largest (h3 0.696 -> 0.632) and the narrowing does most (25.5x ->
    9.6x).
  Next: unchanged (dev to main by pull request on Ely's word; the
  2026-10-21 run on main with the three values).
- 2026-10-17 (00:00 UTC): THE NARROWING, TESTED IN ELY'S APP. Ely merged
  oracle-narrowing into dev (bf044bd, 2026-10-16) and re-ran the 2026-10-17
  week on dev with the three values (seed season_total_early, weight 0.25,
  narrowing 0.7; the Groundhog on its own-share form from #43). The
  -modified files came to this lane and were checked against the submitted
  run (tools/narrow_compare.py, narrow-test/result.txt and
  narrow-test/field_width.txt in the Submission scratchpad):
  - The medians hold: 204 of the 212 (location, horizon) medians are
    identical to the submitted run's and the other 8 differ by 1
    admission (rounding); 4,876 quantile rows, 53 locations (Alaska
    included, as before the drop), every block monotone, integers.
  - The mechanism ran as registered: the implied exponent per cell,
    log(x'/m) / log(x/m) over the 3,649 cells more than 0.3 from their
    median on the log scale, is 0.700 (10th to 90th percentile
    0.681-0.729, the integer rounding).
  - The bands (95% band / median, then 50% band / median, medians over
    locations): h0 3.15x / 0.82x -> 1.96x / 0.55x; h1 6.60x / 1.28x ->
    3.56x / 0.86x; h2 13.0x / 1.84x -> 5.90x / 1.24x; h3 25.5x / 2.62x ->
    9.56x / 1.67x (the 9.5x predicted from the quantiles on 2026-10-16).
    US h3: 714-112,688 about 8,908 -> 1,522-52,630. Against the field's
    2026-10-17 files (57 models with 50+ locations): at h0 the 95% band
    now sits at the field median (1.96x against 1.93x); at h3 it is still
    the widest but one (9.56x; the baseline 8.99x, the Groundhog 8.95x,
    docxology-panelqr 9.54x; field median 3.6x), down from 25.5x, which
    was three times the next widest. The screen says not to chase the
    field with a lower k: k = 0.5 scores 0.692 / 0.758 pooled against
    0.671 / 0.727 at k = 0.7, worse in five of six blocks on the natural
    scale and in every block on the log scale. The rest of the h3 width
    is the filter's early-season tail, the Model lane's item (engine arm).
  - The Groundhog file of this run differs from the submitted one in
    3,723 of 4,876 cells (68 of 212 medians identical): the own-share
    form (#43, on main since 2026-10-15), not the narrowing, which does
    not touch the Groundhog; its h3 95% band 8.95x -> 8.37x.
  - Not checked from the files: the run record's narrowing block
    (oracle.json: k, applied, the unnarrowed quantiles beside the
    narrowed); the implied exponent above is the stronger check of what
    ran. The record can be read on the run page when the week ships.
  Next: dev to main by pull request on Ely's word (this lane opens it and
  gives the merge command), then the 2026-10-21 run on main.
- 2026-10-17 (early UTC): THE NARROWING IS A KNOB, ON BRANCH oracle-narrowing
  FOR ELY'S MERGE INTO dev (two commits over dev, authored as Ely; Ely
  asked for the lever on 2026-10-16). `oracle.narrow` (Model settings,
  the Oracle step group, beside the blend weight; default 1.0 =
  flubnf.oracle.K_PRODUCTION, range 0.1-1.0): after the Oracle step the
  submitted seed's samples of each horizon are scaled about their finite
  median, x' = m (x / m)^k (flubnf.oracle.narrow), so the median holds, a
  value ten times it becomes 10^k times it, zeros and NaN stay, the map is
  monotone, and the hub rows, the report and the categorical map all see
  it (the pipeline takes its quantiles from the samples). The record
  (oracle.json) carries narrowing {k, applied, rule} and, when applied,
  quantiles.primary.narrowed and .unnarrowed (the quantiles before, for a
  later screen). Not narrowed: the origin block, the logged secondary and
  admissions-only members, the null; every cell is narrowed, the identity
  cells included, as the screen scored. A run at k != 1 is a modified run
  with the override and its reason, like the seed rule and the weight; no
  card change while the default is 1.0. Tests: the library (identity at
  1, median held, 10x -> 10^k, zeros, NaN, blocks without a positive
  median, the bounds), the step (apply_week with the knob, the other
  blocks untouched, identity cells, the hub rows end to end, the replay
  path), the registry; docs/ORACLE-SIHRS.md 6b. An adversarial review
  (three lenses, eight findings, all verified) was applied in the second
  commit; full suite 3,380 passed, 162 skipped on the first commit, rerun
  after the second. Merge: Ely merged the branch into dev on 2026-10-16
  (bf044bd; tested in the app, the entry above); dev to main by pull
  request before the 2026-10-21 run, which then sets three values: seed
  season_total_early, weight 0.25, narrowing 0.7, one override reason
  for all three.
- 2026-10-16 (late UTC): THE WIDTH, MEASURED FROM THE STORED RUNS; THE DONOR
  EXPLANATION BELOW IS WITHDRAWN. Ely asked this lane to test the width fix
  on the retrospectives (the Mac Studio is busy; the stored roots are in
  this lane's cloud session, so the tests ran here). Two measurements, no
  engine time (tools/width_source.py, tools/shrink_screen.py and
  replays/shrink_screen_result.txt in the Submission scratchpad):
  - WHERE THE WIDTH COMES FROM. Not the donors: the pooled donor growth
    ratios are tight (the four-week ratio's 2.5th to 97.5th percentile
    0.5-0.7x to 1.1-1.4x in every stored week sampled). It is the filter's
    own forecasting sample, which the Oracle step then multiplies by about
    1.5-2x. And the filter's width this season is the seed rule's doing:
    on the 2026-10-03 vintage the filter alone spans 7.0x its median at
    horizon 3 under the old pin and 15.2x under the stage rule (19.9x on
    09-26); the Oracle member 10.8x against 27.2x. The stored replays say
    the same: early weeks, filter alone 8-14x under the old pin against
    21-46x under the expected-total pin (Oracle 13-25x against 36-134x);
    at the peaks both arms sit at 4-5x (Oracle 6-9x), the field's range.
    Mechanism: with the brake gone early in the season, the particles at
    the top of the Reff and forcing priors run unbraked for four weeks and
    the upper tail explodes; the old pin's false 18% depletion was also
    holding that tail down. So the width is an early-season, new-seed
    effect, and the structural fix is in the filter (a tighter Reff upper
    bound, a growth cap, or the jitter), which needs engine time (about 10
    hours per arm for the 44 weeks in the cloud).
  - THE POST-HOC NARROWING SCREEN (the laptop agent's 2026-10-09 Groundhog
    transform, q' = m (q/m)^k, applied to the Oracle's stored stage-rule
    w = 0.25 quantiles on all 44 weeks, 9,152 cells; the scorer reproduces
    the record at k = 1, mean cell difference 0.0001): pooled relWIS 0.720 /
    0.736 (natural / log) at k = 1; 0.678 / 0.724 at k = 0.8; 0.671 / 0.727
    at k = 0.7; 0.675 / 0.737 at k = 0.6. Coverage 50 / 80 / 95 at k = 1:
    0.62 / 0.90 / 0.99; at k = 0.7: 0.47 / 0.76 / 0.93, nominal. Every
    block improves on the natural scale at k = 0.7 (early 2023-24 1.120 ->
    0.829, early 2024-25 0.727 -> 0.698, early 2025-26 0.552 -> 0.545, peak
    2023-24 1.143 -> 1.031, peak 2024-25 0.550 -> 0.460, peak 2025-26 0.935
    -> 0.907) and every horizon (h0 0.809 -> 0.768, h3 0.696 -> 0.632); on
    the log scale the 2025-26 blocks lose a hundredth. Leave-one-season-out
    picks k = 0.7, 0.7 and 0.6; held-out gains 1.138 -> 0.990, 0.648 ->
    0.592, 0.712 -> 0.710 (2025-26: nil on the natural scale, a loss of
    0.03 on the log scale at k = 0.6 with 95% coverage 0.82: the sharp 2025
    peak punishes over-narrowing). Cluster bootstrap by week (2,000): the
    k = 0.7 gain is 0.049, 95% CI 0.025 to 0.079, better in every
    replicate. On this week's file k = 0.7 takes the horizon-3 95% band
    from 25.5x to 9.5x the median (the baseline's 9x; the field's median
    3.6x; k = 0.6 would give 6.8x), the 50% band from 2.6x to 1.7x, and
    the US band from 714-112,688 to 1,522-52,632 around 8,908.
  - Reading for Ely: two levers, one ready. (1) k = 0.7 on the Oracle's
    quantiles is scored, leave-one-season-out, bootstrap-backed, about 7%
    on the natural scale and a wash on the log scale, with coverage at
    nominal; it is a registered-member change (a card sentence and a knob,
    oracle.shrink or similar, with the override until the default flips),
    and the laptop agent's Groundhog screen found a smaller gain (k = 0.8,
    0.670 -> 0.659) that Ely left alone, so the Groundhog stays as is. (2)
    The structural fix, the early-season filter tail under the new seed, is
    engine work: one arm overnight in the cloud (a Reff upper bound of 2.0
    against the prior's 2.5, or a per-week growth cap), scored on the same
    44 weeks against this record; it would narrow the Oracle from the
    inside and could change the medians too. The donor-width
    pre-registration draft under For other lanes is superseded by this
    entry; the donor pool is not the lever.
- 2026-10-16 (evening UTC): FIRST INTERNAL SCORE OF THE SEASON, WEEK 1 AT
  HORIZON 0, AND WEEK 2 AGAINST THE FIELD. CDC's weekly mail (2026-10-15,
  "FluSight Forecasts for 10/17/2026") says WIS reports follow once enough
  truth is in and asks teams to review for plausibility and calibration;
  Ely asked for an internal read. What can be scored today: the 2026-10-10
  round's horizon 0 (the week ending 10-10, truth as on the hub 10-14,
  still revisable), 53 locations, every team's file from the hub's
  model-output (52 of 54 models; MOBS-EpyStrain_Flu and UMass-trends_ensemble
  submit parquet, unreadable in the cloud), WIS and log(x+1) WIS relative
  to FluSight-baseline on common cells, with flubnf/wis.py. Two
  independent recomputations (an adversarial workflow, scripts in the
  Submission scratchpad verify_wis1/ and verify_wis2/) match to four
  decimals.
  - Week 1, horizon 0 (the old settings, the 11 decliners): Oracle SIHRS
    relWIS 0.902 natural / 0.924 log, rank 36 / 38 of 52; Groundhog 1.106 /
    0.832, rank 44 / 29; FluSight-ensemble 0.665 / 0.735 (rank 12 / 8);
    best DMAPRIME-HYB 0.597 / 0.674; NAU-vulPES 0.928 / 0.832, NAU-FourCAT
    0.942 / 0.915, NAU-epymorph 1.528 / 1.150. Decomposition: our medians
    are mid-field (Oracle MAE rank 21 of 47 full-coverage models; the
    Groundhog's log-scale median error ranks 6th); the penalty is interval
    width (mean central-interval width 1.6x the ensemble's for the Oracle,
    2.4x for the Groundhog, dominated by the US row; per-location median
    1.5x and 1.6x; 50% coverage 0.79 and 0.74 where 0.50 is ideal, field
    median 0.66; 95% coverage 1.00 and 0.98) and under-prediction (Oracle
    3.07 against 0.43 over-prediction; Groundhog 2.55 against 0.67):
    Illinois 193 against our 56 (ensemble 83, nobody caught it), Puerto
    Rico 181 against 75, Pennsylvania 231 against 162, plus the small-state
    noise (Vermont, Idaho, New Hampshire, Montana). We beat the ensemble's
    log WIS in 8 of 53 locations (Oracle) and 13 (Groundhog). The baseline
    file has no Iowa row in either round (its ratios are over 52 cells).
  - Against the replays: the early-week replay put the old settings at
    about 0.71 / 0.81 (Oracle, horizon 0) and 0.64 / 0.59 (Groundhog,
    pooled); week 1 came in worse on both, one week, one horizon, a week
    with two unusual jumps. Horizons 1-3 of week 1 score over the next
    three weeks and will be worse for the Oracle (the decliners' medians
    fell while the data rose); week 1 is likely the season's worst week
    and was run with the defect since fixed.
  - Week 2 (the new settings) against the field of 69, medians, no truth
    yet: Oracle at the field's 50th-62nd percentile by horizon, 1.00-1.06x
    the ensemble; US 4,772 / 5,834 / 7,180 / 8,908 against the ensemble's
    4,831 / 5,679 / 6,785 / 7,863 (46th of 57 national horizon-3 medians;
    the ensemble 29th); below the field's 10th percentile only in the small
    flat states (DC, Idaho, Wyoming; Maine at h0, North Dakota at h3).
    Groundhog: 17th-19th percentile at horizons 0-1 (0.86 and 0.81 of the
    ensemble: its calendar donors grow 1.08x in the first week where the
    field says 1.26x; past Octobers started gentler than this one) and
    back to the field by horizon 3 (1.00); the pooled calendar shape's
    limit, the per-state pooling item.
  - Predicted performance (this lane's estimate, not a score): week 1
    final, lower-middle of the field, roughly 35th-45th of 52 on both
    scales; from week 2, medians track the ensemble, so the replays' 0.67
    early-week relWIS for the new settings is the fair expectation if this
    season behaves like the three replayed ones: the Oracle around the
    ensemble on the log scale and somewhat behind it on the natural scale,
    upper-middle (top 15-25 of about 52); the Groundhog similar on the log
    scale, worse on the natural one, where its wide intervals cost most in
    the large states. Season-long top-quarter needs the intervals
    tightened.
  - The one calibration issue CDC's mail asks about, for the Model lane:
    both members are over-dispersed; the replays showed the same (stage
    rule at w = 0.25, 50% coverage 0.62 over four horizons, 95% 0.99). A
    scored tightening of the spread, at least at horizons 0-1, is the
    cheapest WIS gain available and can be scored from the stored replay
    runs without engine time (For other lanes).
  - Is the first week this bad in the retrospectives? Yes, once the stored
    replay (replays/score_w025_cells.csv) is read at horizon 0 by week
    rather than pooled. The shipped Oracle at horizon 0 in the FIRST
    scored week of each replayed season: 2023-10-07 relWIS 0.889 natural /
    0.726 log, 50% coverage 0.77; 2024-11-16 0.782 / 0.891, 0.73;
    2025-11-15 0.636 / 0.783, 0.40. This week's 0.902 / 0.924 with 0.79 is
    at the bad end of that range, not outside it, and the first week is the
    worst horizon-0 week of each replayed season (2023: 0.889, 0.752, 0.700
    over weeks 1-3; 2025: 0.636, 0.637, 0.599). The over-dispersion is also
    in the replays at the first weeks (50% coverage 0.73-0.79 in 2023 and
    2024) and in the stage rule throughout (cov50 0.59 at every horizon,
    cov95 0.98-0.99). The pooled early-week numbers in the record (0.74 /
    0.84 shipped, 0.67 / 0.67 stage) averaged this away. Caution for week
    2's expectation: at a season's first week the stage rule was not
    reliably better than the shipped rule on the natural scale (2023-10-07
    0.986 against 0.889; 2024-11-16 1.143 against 0.782, the expected-total
    overshoot in a late season), only on the log scale from 2024 on; its
    second weeks scored 0.791 / 0.740, 0.816 / 0.901 and 0.577 / 0.717 at
    horizon 0, which is the fair range for this week's file. Calendar and
    level differ too: the replays' first scored weeks were October 7 (US
    1,105) and mid-November (US 2,500-2,600); this season's first week is
    October 10 at US 3,835 and 1.23x a week.
  - Are we the only team with bands this wide? Nearly (tools/field_width.py
    in the Submission scratchpad, on the 2026-10-17 files of the 57 models
    with 50+ locations; width = (upper - lower) / median, median over
    locations). 95% band at horizon 3: field median 3.6x the median,
    FluSight-ensemble 3.6x, FluSight-baseline 9.0x, Groundhog 9.0x (53rd of
    56), Oracle SIHRS 25.5x (56th of 56, the widest in the field, seven
    times the median model). 50% band at horizon 3: field median 1.0x,
    baseline 2.5x, Groundhog 1.5x, Oracle 2.6x (wider than the baseline's).
    At horizon 0: 95% band field median 1.9x, Oracle 3.3x, Groundhog 4.3x
    (baseline 5.2x); 50% band field 0.5x, Oracle 0.8x, Groundhog 0.8x. So
    the width is not a shared trait of mechanistic or wide-by-design
    teams: every other team, the ensemble members included, runs 2-6x at
    horizon 3, and the Oracle's upper tail (Illinois 6 to 20,266 around a
    median of 409) is what the WIDE flag in sense_check.py was built to
    show. This moves the calibration item from "a little better score" to
    "an outlier to fix, scored on the replays first".
  - Files: the scorer tools/field_score.py and its result
    hubfield/field_score_result.txt in the Submission scratchpad (the hub
    data copied under hubfield/); not committed (the lane's docs-only
    rule; say the word and the scorer goes under tools/ as a weekly
    check). Rerun each Thursday after CDC's mail: one more horizon of
    truth lands every week.
- 2026-10-15 (15:31 UTC): PULL REQUEST #43 (dev TO main) MERGED BY ELY,
  opened from dev by the Groundhog lane: the Groundhog's own-share form
  (flubnf.analogue.LocalPooling, SHIPPED_OWN_SHARE 0.5, the knob
  groundhog.own_share, card 1.2) and the App lane's settings-panel and
  marks cleanup; merge commit e97b227. So main carries the own-share form
  for the 2026-10-21 round, and a Groundhog run on main now differs from
  the 2026-10-17 file by design. Recorded here on 2026-10-17, when this
  lane found the merge on main.
- 2026-10-15 (02:52 UTC): PULL REQUEST #42 (dev TO main) OPENED BY THIS LANE
  AT ELY'S REQUEST (https://github.com/elyfmiller/flubnf/pull/42): docs
  only, docs/TEAM.md (the merge-command rule) and these notes (#41
  recorded, the rule under Decided). Head 400f580 on main 22cfe3b. The
  integration's footer was edited out of the body at once. MERGED BY ELY
  AT 02:52 UTC (merge commit 37a8250, authored as Ely, committer GitHub)
  with the tests still queued on the head; docs only, so nothing a run
  reads changed. The merge-command rule is on main from here on.

- 2026-10-15 (02:25 UTC): PULL REQUEST #41 (dev TO main) OPENED BY THIS LANE
  AT ELY'S REQUEST (https://github.com/elyfmiller/flubnf/pull/41): the
  Output tab fix (seven app files) and the Submission and Engine notes
  since #40; 9 files, +524/-17; head e48bf98 on main 710f718. The tests
  jobs were running on the head at opening (CI runs on the push to dev);
  MERGED BY ELY AT 02:46 UTC from the website (merge commit 22cfe3b,
  authored as Ely, committer GitHub, as #29 to #33); main carries the
  Output fix, the Submission notes and the Engine lane's notes through
  ad09f40 (their migration plan and Ely's seven decisions on the
  public-PyBNF plan, pushed while the pull request was open). Every head
  the tests ran on while it was open was green (all six jobs on a1f65f1,
  e48bf98, 81b920d and 8d2b627); checked at 03:08 UTC: all six jobs
  green on the merge commit 22cfe3b and on #42's 37a8250, so main is
  green with both. The integration's footer appeared on the body
  again and was edited out at once (the 2026-10-12 lesson); the body is
  Ely's. FluBNF on Ely's laptop picks main up on its next open.
- 2026-10-14 (22:40 UTC): THE OUTPUT TAB SHOWS A MODIFIED RUN, ON BRANCH
  app/output-modified-runs FOR ELY'S MERGE INTO dev (aa8bae4, de5d75c; from
  dev b2b379c; authored as Ely; Ely asked this lane to fix it after the
  round). What changes: shared._latest_results gains include_modified
  (default off); the Output page's weekly report card passes it, so the
  newest run shows there even when its settings were modified and the
  override box was unticked, with a "modified settings" badge whose tip
  names the settings and says its files carry the -modified name under
  their date below; the card's buttons link that run's own report
  (/runs/<id>/report). Unchanged on purpose: Home, the Forecast fans,
  Models and /output/report (Home's report button and map link) keep the
  shipped rule, so a modified run never passes for the registered model
  there; research runs stay hidden everywhere. Tests: one new in
  app/tests/test_output_by_date.py (card, badge, buttons, the picker, the
  override), assertions in test_knobs_wiring.py and test_audit_fixes.py.
  An adversarial review of the first commit (three lenses, seven findings
  verified) found and the second commit fixed: the earlier-weeks picker
  dropped the archived shipped report for the modified run's week (a
  modified run is never archived); /output/report had followed the card,
  which would have sent Home's button and map link to a run Home does not
  show; the badge appeared before the run had a report; the tip named the
  file naming twice. Full suite on the branch: 3,271 passed, 162 skipped,
  three runs; two of them ended with one session-level error from
  app/tests/conftest.py's app/state guard (below), none from a test.
  MERGED INTO dev AT ELY'S REQUEST on 2026-10-15 02:20 UTC (merge commit
  a1f65f1, authored as Ely; the lane's one code merge, on Ely's word, as
  the seed branch was); dev to main by pull request as usual; FluBNF picks
  it up on the next open after that.
  - For the App lane, two test-isolation leaks seen in the cloud, both
    outside this diff: (a) app/state/component_versions.json in the
    working tree was written (21:41 UTC) and rewritten (21:54) during full
    runs, which trips the session guard at the last test's teardown;
    conftest redirects versions._VERSIONS_SNAPSHOT to the test state, and
    a per-test watcher saw no test touch the file, so the write comes from
    the startup warm thread (app/ui/server._start_background_warm,
    versions._warm_versions) of an interpreter without the redirect, most
    likely a subprocess, landing after the last test; intermittent (one
    run in three was clean; CI on main is green). (b) uv.lock (220 KB)
    appeared at the repository root at 21:50 UTC during a run and was
    removed by hand, not committed; nothing in the tests names uv, so the
    writer is a launcher or install step run under test. Neither is in
    this branch.
- 2026-10-14 (21:20 UTC): ROUND 2026-10-17 (EW41) SUBMITTED AND MERGED:
  cdcepi/FluSight-forecast-hub#3805, OPENED BY ELY FROM `FluBNF_submission`
  (63bb9da2 "NAU_PyBNF forecast 2026-10-17 (EW41)", on cdcepi main
  397226db, authored and committed as Ely, no trailers), MERGED BY CDC
  (Annabella Hines) AT 21:20 UTC the same day, 50898478, after Ely's sync
  merge of cdcepi main into the branch (8d599f99); checked 2026-10-15
  14:01 UTC: both files on the hub's main are byte-identical to the
  committed ones. Next round (2026-10-24, due 2026-10-21) reuses
  `FluBNF_submission`: fast-forward it to cdcepi main first. Oracle SIHRS 52 of
  53 locations (Alaska dropped, the finding below), Groundhog all 53; both
  files as committed pass validate_submission.R, 31 checks with `--window`.
  The run: Ely's laptop on main 710f718 (the morning's #36 to #40 on top of
  #33), data through 2026-10-10, 10,000 particles x 3 replicates, 5 min
  15 s; model settings `oracle.w=0.25, pf.seed_denominator=
  season_total_early` (knobs digest 3d7ef6b7), exported under the hub names
  by override with the reason "2026-10-12 decision: expected-total seed
  early in the season and Oracle weight 0.25, both replay-scored;
  docs/team/submission.md" (the run record and the weekly report say so).
  Files, scripts and the review table: the Submission scratchpad,
  round-2026-10-17/.
  - The data (CDC's hub commit e4e60ab1 at 10:52 ET; the ED-visits and
    hubverse files followed at 15:18-15:21 ET, neither read by FluBNF; the
    watch script polled the hub every 10 minutes until 20:24 UTC and saw no
    further admissions commit): all 53 reported 2026-10-10, no NaN or zero
    newest week; US 3,420 -> 3,835 (1.12x; last week's 3,246 revised to
    3,420); 22 of 52 states down week over week, most on small counts;
    Illinois 67 -> 193 (2.9x; its record holds a September one-week spike
    13 -> 109 -> 39), Puerto Rico 81 -> 181, Idaho 15 -> 6; the 10-03 week
    revised up 20% or more in Mississippi (20 -> 29), Kentucky (45 -> 59)
    and Iowa (15 -> 21).
  - Three runs. The first ran with the knobs unset (the Model settings panel
    starts at the shipped defaults every week; the update to main turns
    nothing on): 14 of 52 states' horizon-3 medians below the last week, the
    sense check flagging Alaska, Montana, Maine, Oregon and Nebraska
    ("untick, or w = 0.25 first") and Washington ("consider unticking"),
    median h3/last 1.29. The second, with both knobs but the override box
    unticked, exported `<hub id>-modified` files and stayed off the Output
    tab (by design; Ely found it in the run ledger): 1 state below the last
    week (Alaska, 0.85), 2 above 3x (Delaware 27, New Hampshire 20, both
    under 10 admissions), median h3/last 2.20 (Groundhog 2.19); all six
    flags clear; every Groundhog horizon-3 median inside the Oracle's 95%
    band and the reverse; the Oracle/Groundhog horizon-3 ratio 1.0 in the
    median, Alaska (0.39) the only one outside the Oracle's 50% band. The
    third, with the box ticked and the reason typed, produced byte-identical
    files under the hub names; those are the committed ones. US Oracle
    4,772 / 5,834 / 7,180 / 8,908 (1.23x a week, the data's own last three
    weeks), Groundhog 4,139 / 4,707 / 6,548 / 8,390; this season runs at
    three times last year's level at the same date.
  - FINDING, FOR THE MODEL LANE: ALASKA AND HAWAII CROSSED THE QUARTER THIS
    WEEK. From resolve_state on the 10-10 data with season_total_early:
    Alaska's season-to-date count (142) is 25.8% of its expected total and
    Hawaii's (221) 26.5%, so both are in the to_date stage, factor 1, the
    implied infected-so-far 18% (the old pin); the other 50 are in the
    expected stage at 0.2-3.0% infected (median 0.7%). Alaska (data 21 23
    24 19 23 13): Oracle 11 / 11 / 12 / 11 against Groundhog 14 / 16 / 22 /
    28, flat on the drained seed after a real drop in the data; DROPPED from
    the Oracle file on Ely's judgment, with that mechanism as the reason.
    Hawaii (3 10 17 29 67 72): Oracle 76 / 87 / 98 / 112 (1.12x a week)
    against Groundhog 78 / 88 / 123 / 158, KEPT: it rises and the two agree
    at horizons 0-1. The switch is abrupt (the caveat of 2026-10-09): at the
    threshold the assumed infected fraction jumps from 4.5% (0.18 x 0.25) to
    18% in one week. Next to cross at the current 1.2x a week: Puerto Rico
    (16.9%), Washington (13.6%), Utah (12.4%), California (11.6%), Florida
    (10.5%), in two to four weeks; the US total sits near 5%. A smooth
    switch, or a different threshold with the peak brake re-scored, is
    needed before November or the old decliners return state by state.
  - The states Ely asked about, all kept. District of Columbia (3 2 2 3 3 3;
    Oracle 3 / 4 / 3 / 3, Groundhog 3 / 4 / 5 / 7): 0.5% infected, no
    drain; the wobble is integer rounding of a median near 3.5 (the
    45th-55th percentiles 3-3, 4-5, 3-4, 2-4); the filter's own growth on
    six flat weeks is about zero and the 75% donor share lifts it to flat,
    not to the Groundhog's climb. South Dakota (Oracle 5 / 6 / 7 / 8): the
    straight line is the Oracle step's one blended growth rate per path,
    1.19x a week from 5. Utah, Virginia, West Virginia and Washington: the
    two models agree. Vermont (0 1 1 3 1 6; Oracle 8 / 10 / 13 / 16): the
    Oracle's horizon 0 anchors on the fitted state, not the last report.
    Illinois (Oracle 233 / 283 / 343 / 409, 95% band 6-20,266 at horizon 3;
    Groundhog 208 / 237 / 330 / 422): the weekly report's categorical map
    colored it "decrease" because that is the single largest category (34%)
    while up is 50% split over two categories; the submission carries
    quantiles only.
  - The validator in the cloud, for next week: hubValidations needs TZDIR
    pointed at the conda R's zoneinfo (CCTZ does not know US/Eastern
    otherwise and the submission_time check errors) and the fork's sparse
    checkout needed auxiliary-data/raw-population-archive (which brings
    locations.csv for counts_lt_popn) and src/validations added; both done
    in this session's clone. sense_check.py ran against a hub directory
    assembled from the fetched target-data and locations.csv.
  - Next: Ely opens the card 1.4 pull request from NAU_PyBNF-OracleSIHRS-1.4
    (staged, byte-identical to main); a note to Spencer (the NAU ensemble)
    after Ely's go; this lane confirms #3805's merge on the next cdcepi main
    fetch and records it; the Output tab, the categorical map and the
    weekly knob entry are App items under For other lanes.
- 2026-10-12 (21:20 UTC): PULL REQUEST #33 (dev TO main) MERGED AT 21:14 UTC
  BY ELY, BEFORE THE TESTS FINISHED; main IS AT c212e69. Ely confirmed the
  merge was theirs (the merge came one and a half minutes after the pull
  request opened, while all ten tests jobs were still running); the merge commit
  is authored as Ely like #29 to #32. main now carries the seed rule and
  its knob, cards 1.3 and 1.4, the design pass and the notes; Ely's laptop
  picks them up on its next open. CI on the merge commit was still running
  at this entry; checked at 21:41 UTC: main is green, all five tests jobs
  on the merge commit c212e69 and all ten on b657070 passed. Finding for the
  rule above: the GitHub integration this lane opens pull requests through
  appends an attribution footer with a session link to the pull request
  body on creation (it was not in the text the lane sent); the lane edited
  it out at 21:16 UTC and the body is clean. So when Ely wants this lane to
  open a FluBNF pull request, the lane edits the body right after opening
  it; Ely's own click from the compare link never has the problem.
- 2026-10-12 (21:15 UTC): FLUBNF PULL REQUEST dev TO main OPENED AT ELY'S
  REQUEST; IT MERGES WHEN THE TESTS PASS. Ely asked this lane to open the
  pull request and have it merge once CI is green. GitHub's own auto-merge
  is off for the repository (allow_auto_merge false) and main has no
  ruleset requiring the tests jobs (branch protection is not readable from
  this session), so GitHub could not be made to wait on CI itself; the
  lane watches the pull request and merges it (a merge commit, as #29 to
  #32) once every tests job on its head is green. The session's GitHub
  token is Ely's own account, so the pull request and the merge commit are
  authored as Ely, like #32; merging the pull request on Ely's instruction
  is the pull-request method, not a push of main. The pull request carries
  everything on dev since main's #32: the seed rule and its knob, cards 1.3
  and 1.4, the rest of the App lane's 2026-10-05 design pass (display and
  wording, per app.md), the student install guide, CITATION, and the four
  lanes' notes. For GitHub to do this itself next time: Settings, General,
  Pull Requests, Allow auto-merge, and a ruleset on main that requires the
  tests jobs; then the lane enables auto-merge on the pull request instead
  of merging it.
- 2026-10-12 (15:20 UTC): ELY'S DECISION FOR 2026-10-14: THE STAGE RULE AND
  THE ORACLE WEIGHT 0.25. Shipping plan, executed as far as this lane can:
  (1) branch seed-denominator merged into dev (its two commits now 20336c6 and 9d69bef after a rebase, no conflicts; the
  full suite on the merged tree is in replays/fullsuite_merged_dev.txt); (2)
  card 1.4 on dev (1d14d36): the seed sentence (an assumed 18% attack rate
  against the expected season total while the season-to-date count is below
  a quarter of it, the season-to-date count after; from the 2026-10-17
  round) and the weight ("at weight one half" stays, the knob binding test
  requires the shipped default's phrase; "From the 2026-10-17 round the
  submitted weight is one quarter on the filter's growth (one half before);
  each run records the weight it used"); the short methods field at 194 of
  200 characters; the card tests pass; staged byte-identical on the fork
  branch NAU_PyBNF-OracleSIHRS-1.4 (replaces 1.3, which was never opened);
  (3) code defaults unchanged: to_date and w = 0.5 stay the shipped values
  (tests/test_oracle.py pins W_PRODUCTION = 0.5 and the card binding ties
  "at weight one half" to it; flipping them is the Model lane's
  registered-member change, not this lane's), so Wednesday runs with the two
  research knobs set and the override reason typed, which the run record and
  the card both state. The Model/App review of the branch requested on
  2026-10-07 did not arrive; Ely's decision stands in for it. Main: dev is
  ready to merge; Ely opens the pull request from dev to main from the
  compare link (this lane never pushes main, Ely's rule of 2026-10-12 in
  Decided); Ely's laptop runs main after the merge.
  - Wednesday 2026-10-14, the run on Ely's laptop: FluBNF on main (after the
    merge), hub clone updated in the Data tab; in the Forecast tab's Model
    settings panel set "Seed denominator" (pf.seed_denominator) to
    season_total_early under Oracle SIHRS: particle filter, and "Oracle
    blend weight" (oracle.w) to 0.25 under Oracle SIHRS: Oracle step; type
    the override reason (suggested: "2026-10-12 decision: expected-total pin
    early in the season and Oracle weight 0.25, both replay-scored;
    docs/team/submission.md"); run both models; export; run sense_check.py
    on the two files (optionally --alt with a w = 0.5 export); untick by
    judgment; hand the two CSVs to this lane for the validator, the
    fast-forward of FluBNF_submission, the commit "NAU_PyBNF forecast
    2026-10-17 (EW41)" and the compare link; the card PR from
    NAU_PyBNF-OracleSIHRS-1.4 the same day. A note to Spencer after Ely's
    go.
- 2026-10-12 (15:15 UTC): fit_i0 RESULT; NO MORE EXPERIMENTS THIS WEEK
  (ELY); THE SENSE CHECK GAINS AN --alt COMPARISON. fit_i0 (i0 loguniform
  1e-7..1e-3; the engine refuses it with a non-shipped seed rule, "both set
  the seed", and with i0 fitted the seed rule has nothing to set, so the run
  used the shipped rule; root replays/2026-27-fiti0,
  compare_fiti0_result.txt, fiti0_field.txt): decliners 6 of 52 (stage rule
  5), above the field's 90th percentile 11 (stage 13), above the field
  maximum 2 (New Hampshire 91, Hawaii 413), above 3x 14 (stage 17), median
  1.12x the ensemble (stage 1.16x); Florida 778, 1,024, 1,343, 1,743 (stage
  1,875); the filter alone damps by 17% at horizon 4 (median over the 52),
  the ridge mixture at work. At w = 0.25 on top: decliners 3, above the 90th
  percentile 5, above the maximum none, above 3x 3, Florida 1,452. So
  fitting i0 sits between the stage rule and the stage rule with w = 0.25;
  the weight matters more than the seed. The fitted i0 and mult spreads were
  not inspected (the cells' parameter outputs are deleted when a week
  completes). Ely: no further experiment this week; in this first season the
  team relies on judgment about dropping a state from a week's submission
  (an early-season problem), with the script as the tool. Revisions, for the
  record (replays/revisions_by_month.txt, 92 vintages): first reports in
  September-October are not revised more than mid-season ones in the median
  (1.00x; 8-15% of cells move over 20%); January-February first reports are
  revised up 5-6% in the median (70-75% of cells up); counts under 10 have
  the widest relative tails (30% move over 20%); one-week-old data are
  nearly settled. Only the 2023 and 2025 early seasons are in the archive.
  - sense_check.py (sent to Ely again; copy in the scratchpad): now falls
    back to ~/Downloads when the hub clone holds no export, takes --alt
    <file> (a second export of the same reference date, e.g. the run at
    oracle.w = 0.25) and prints its horizon-3 median and its own flag beside
    the main file's, and recommends "untick, or w=0.25 first" for DECLINE or
    DROP on counts under 100. On the 2026-10-10 submission it flags Montana,
    Wisconsin, Illinois, Michigan, Alaska, Maine and Oregon (7 of the 11
    decliners; Puerto Rico's 0.90x drop is below the DROP line and DC, South
    Dakota and Wyoming are SMALL). With the stage rule at w = 0.25 as --alt
    (built from the stored run's secondary quantiles), all 7 come back
    clean. With w = 0.25 alone on the old pin (the shipped root's
    secondary), the weight fixes about half of the 11; the seed rule is what
    fixes the rest (table in chat).
  - The attack-rate source, for Ely's reading list: ATTACK_RATE_SOURCE in
    flubnf/sihrs_priors.py is doi 10.1038/s41467-021-26948-8 (Vinh et al.
    2021, Nature Communications; serology from Vietnam, H3 25.6%, H1 16.0%;
    the code's note: cumulative infections per season, a proxy, the widest
    uncertainty in the chain). The paper could not be opened from the cloud
    container (nature.com and doi.org are outside the network policy).
- 2026-10-12 (14:40 UTC): WHY THE OLD PIN HIT THE SMALL AND FLAT STATES,
  STATE BY STATE; THE fit_i0 TEST RUNNING. For Ely's Wednesday explanation
  (replays/drain_table.txt, from the stored 2026-10-03 runs of the 19
  direction-check jurisdictions): the attack rate was 0.18 in every state,
  so the implied infected fraction was 18% everywhere, not higher in small
  states. What differed: infections per admission (1 / rhomult, with rhomult
  = season-to-date per capita / 0.18) ran 1,000-9,700 (small per-capita
  counts give the largest: DC 9,700, Minnesota 9,700, North Carolina 8,200,
  Maine 7,900; Florida 1,900), and the weekly S loss the old pin implied,
  0.18 x (last week / season-to-date), was 3-8% of N in every state (median
  4%). Whether a state declined depended on its data growth: the filter's
  first-week growth under the old rule tracks the data's growth (correlation
  0.76 across the 19): Montana (data 0.94x a week) 0.59x, Wisconsin (1.06x)
  0.71x, Alaska (1.00x) 0.73x, Michigan (1.18x) 0.74x, Illinois (1.23x)
  0.75x, Oregon (1.36x) 0.85x; Florida (1.41x) 1.16x, North Carolina (1.73x)
  1.23x, Hawaii (1.86x) 1.28x. The Oracle step anchors on that first week,
  so the flat states were carried down and the surging states up. Under the
  new pin: 130-320 infections per admission, 0.1-1.4% of N lost per week,
  first-week growth 0.7-1.0x in the flat states (their own data) and
  1.2-2.0x in the surging ones. Added to the explainer doc as a
  state-by-state section with the table and a one-breath statement of the
  approach now.
  - Ely's fit_i0 test (2026-10-12): this week's two vintages, all 52 x 3
    seeds, i0 FITTED (loguniform 1e-7..1e-3; the engine extra fit_i0, not a
    console knob, injected by replays/fit_i0_week.py around the retro CLI)
    on top of season_total_early; root replays/2026-27-fiti0, log
    replays/fiti0_run.log, started 14:30 UTC, about 50 minutes. Note for the
    reading: with i0 fitted the seed rule no longer touches the dynamics
    (its i0 is only the default value); admissions pin only i0 x mult, so
    the cloud spreads along that ridge and the forecast mixes braked and
    unbraked particles until depletion bites; the prior's extent sets the
    mix. Reported when stored: the all-52 picture, decliners, the >3x tail,
    the field rank, Florida and the 11, next to the stage rule and w = 0.25.
- 2026-10-11 (15:10 UTC): ELY'S OWN SENSE CHECK, A STANDALONE SCRIPT.
  Instead of a standing check by this lane, Ely asked for a script to run on
  the laptop: sense_check.py (pandas only, no FluBNF import; sent to Ely in
  chat, copy in the session scratchpad; not committed, the lane's docs-only
  rule; say the word and it goes under tools/). Inputs: the week's
  <date>-NAU_PyBNF-<model>.csv (searched under --files, default the hub
  clone's model-output/) and the hub clone (--hub, default $FLUBNF_HUB or
  ~/GitHub/FluSight-forecast-hub as the app resolves it). Per jurisdiction
  it prints the last four observed weeks, the data's recent weekly growth,
  the h0-h3 medians, h3/last, the implied weekly growth, the 95% width at
  h3, the medians against the previous round's ensemble at the same target
  weeks, this round's ensemble h3 when the clone has it, the actual against
  h0 once the next week is in, and the seed stage from a run's cells.json
  when given. Flags: DECLINE (h3 below the last week while the last three
  weeks grew at least 1.10 a week), DROP (h3 below 0.75 of the last week on
  flat data, or below half of it), STEEP (implied growth above 1.35 a week
  and 15% above the data's, with h3 above twice the last week), SMALL (last
  week under 10), WIDE (95% width over 30x the median; informational), FAR
  (outside half to double the previous ensemble). Recommendation: submit /
  check / consider unticking. On the 2026-10-10 files it flags Illinois,
  Michigan, Maine and Oregon as DECLINE (consider unticking), Wisconsin,
  Alaska and Montana as DROP (check), the small-count jurisdictions as
  SMALL, and reads the ensemble from the clone (our h3 medians at 0.74 of
  the ensemble's, below half in 10 jurisdictions). The thresholds are
  constants at the top of the file.
- 2026-10-10 (16:15 UTC): THE FILTER'S 1.52x FIRST WEEK FOR FLORIDA IS THE
  FITTED SEASONAL FORCING, VERIFIED. Three read-only code readers (filter,
  Oracle step, seed rule), each checked by a skeptic that re-ran their
  computations (36 claims confirmed, 3 refuted on wording or a mislabelled
  ratio, 1 unresolved). The filter fits five parameters (Reff, eps1, phi1,
  mult, r; s0, gamma, rho, gammaH, omega fixed); the seed changes only i0,
  and through the first weeks' likelihood the fitted mult (0.026 under
  to_date, 0.32 under season_total_early), hence the infections each
  admission removes from S (about 1,900 vs 160). Florida's profile, five
  flat weeks then five at about 1.4x, can only come from a constant-Reff
  SIHRS whose annual cosine forcing is on its rising limb inside the data
  window: the cloud has eps1 median 0.36 (prior U(0, 1)), Reff 1.28, the
  forcing peak about 17 weeks ahead; beta keeps rising 2.3% a week through
  the horizon, each particle's own growth goes 1.54, 1.63, 1.70, 1.65 a week
  (per particle, not a median-of-exponentials artifact; robust across
  seeds), S/N drifts only 0.86 -> 0.78. Under to_date the same rising
  forcing is fitted (eps1 0.48) but S/N falls 0.66 -> 0.43 and the brake
  wins (the turn-down 649, 666, 582, 450). With eps1 held at zero the
  new-rule forecast grows 1.22, 1.23, 1.21, 1.20 a week, near the ensemble's
  path. Neither the seed transient (I0/I_T 0.249 under both rules) nor the
  last-week state contributes. A numpy re-implementation of the filter
  (scratchpad lwcheck/lw_check.py, lw_check_noharm.py) reproduced the stored
  medians within 1-3% (stage) and the mechanism under other seeds. So the
  Oracle weight damps the symptom; the cause is the prior on the forcing
  amplitude (and Reff), which the console exposes as the per-parameter
  research knobs pf.prior.<name> (Prior range for eps1 etc., a fit-stage
  knob: a refit, about 25 minutes for all 52 in the cloud). Model lane's
  call; the Submission lane can run a narrowed-eps1 arm of this week on
  request. Minor corrections from the skeptics, for the record: the calendar
  donors sit at epiweeks 37-41 (not 38-42); Florida's N in the hub's
  locations.csv is 23,372,215 (the 22.6 M in an earlier brief was the
  2024-25 file); the code's expected-total window is Aug 1 - Jul 31.
- 2026-10-10 (15:20 UTC): WHY FLORIDA TRIPLES UNDER THE NEW RULE, AND THE
  ORACLE WEIGHT 0.25 SCORED FROM THE STORED RUNS. Ely asked why Florida's
  horizon-3 median goes 559 -> 1,875 (3.35x) under season_total_early. The
  data: Florida grew 1.36, 1.37, 1.56, 1.35, 1.32 a week over the last five
  weeks (146 -> 559), the longest run above 1.25x in its record; the US
  total grew 1.24-1.34 a week over the same weeks. The path 802, 1,073,
  1,422, 1,875 rises 1.43x then about 1.32x a week: the data's own recent
  rate continued. Against the hub (the 2026-10-10 round, 47 other models,
  files read from cdcepi main 7011bc394): the ensemble's Florida horizon-3
  median is 977, ours as submitted 1,037 ranked mid-field, 1,875 would rank
  44th of 45. Across the 52 jurisdictions the new rule's horizon-3 medians
  sit at the 78th percentile of the field on average (submitted: 20th),
  above the field's 90th percentile in 13, above every model in 1 (New
  Hampshire 99 against a field maximum 53); the decliners it fixed are still
  below the field (Illinois 74 against an ensemble 126). Florida's history:
  its three earlier runs of 3+ weeks above 1.25x were each followed by three
  weeks that together rose at most 1.5x. replays/field_rank_2026-10-10.csv,
  scratchpad hub-2026-10-10-full/.
  - Mechanism (an adversarial reader reproduced the stored Oracle output
    bitwise from the samples): the Oracle step takes from the filter only
    the anchored origin (559) and the filter's first-week growth lam_T =
    ln(m1/m0), and REPLACES the filter's own path with the blend (w = 0.5 in
    log G) of that growth and a calendar-matched donor's growth; the
    filter's weeks 2-4 are discarded; the Groundhog's forecast is not an
    input (shared donor banks only). Shipped rule: lam_T 0.149 (16% a week),
    the filter's own path turns down (649, 666, 582, 450), the Oracle lifts
    it to 655-1,037. New rule: lam_T 0.422 (52% a week), the filter alone
    accelerates to 4,049 (7.2x); constant-rate extrapolation of its first
    week is 5.4x; the w = 0.5 blend 3.35x; donors only 2.2x. Had the filter
    said the data's 1.33x, the Oracle would return 1,396 (2.5x): the
    calendar donors grow 1.16-1.21x a week in early October and brake. Every
    +0.1 in the filter's first-week log growth adds about 24% to the
    horizon-3 median. Why the filter's first week says 1.52x when the data
    say 1.32-1.35x is still being traced (its fitted Reff and seasonal
    forcing); the Model lane's question.
  - The five remaining decliners (Montana 15 -> 8.8, Alaska 22 -> 19, DC 2
    -> 1.4, South Dakota 4 -> 4, Wyoming 3 -> 2.5) are not an S drain: their
    implied infected-so-far is 0.4-3.9% of N; their counts are tiny and
    noisy (Montana 18, 6, 29, 15), the filter's first-week growth is
    negative in all five and the donor blend only lifts that to flat. The
    attack rate (0.18, Vinh et al. 2021, Vietnam serology; the code calls it
    the weakest link) is a seed-time conversion, not a model parameter:
    under the new rule it scales a starting pool of a few percent and cannot
    fix either symptom; a state-specific attack rate would be an assumption
    swap against ascertainment (only rho*mult is identified). Explained to
    Ely with Florida's numbers (old pin 0.000528, i0 5.15e-3, 18% implied
    infected; new pin 0.00641, i0 4.24e-4, 1.5%).
  - Oracle weight w = 0.25 (the pre-registered logged secondary; production
    0.5) scored from every stored replay week, no engine time
    (replays/score_w025.py, score_w025_tail.py, score_w025_result.txt,
    score_w025_cells.csv; 44 weeks, 9,152 common cells, 5-seed-mean
    quantiles, pre-floor for both weights). relWIS / log relWIS, w 0.5 ->
    0.25: shipped seed 0.768/0.884 -> 0.736/0.806; season_total 0.823/0.793
    -> 0.755/0.740; stage-aware 0.753/0.787 -> 0.720/0.736. Early pooled
    (stage) 0.679/0.681 -> 0.668/0.668; peak pooled 0.836/0.980 ->
    0.779/0.861; the gain grows with horizon (h3 0.744/0.756 ->
    0.696/0.694). Better on the log scale in 40 of 44 weeks and 50 of 52
    jurisdictions, on the natural scale in 46 of 52; loses on the natural
    scale in the 2024-25 peak block (0.522 -> 0.549, overprediction during
    the decline) and the 2023-24 early block (0.795 -> 0.815). Checker
    (independent loader, bitwise match on all 9,152 cells; its scripts under
    scratchpad skeptic_w025/): the comparison is symmetric and survives the
    output floor (floored, stage: 0.752/0.772 -> 0.720/0.723; so the
    record's 0.864 is not comparable to the pre-floor 0.806), identity-cell
    removal, a week-level bootstrap (every interval excludes zero) and
    leave-one-season-out; caveats: the log-scale win is not universal (stage
    2025-26 early 0.522 -> 0.523), part of the win is width (95% coverage
    0.97 -> 0.99 in the knob and stage arms, 50% 0.56 -> 0.62), 2023-24 ran
    on the FluSurv-NET-only bank, and choosing the secondary after seeing
    these 44 weeks is a choice between two pre-registered values on the data
    they were logged on.
  - This week at w = 0.25 under the new rule (replays/w025_thisweek.txt):
    decliners 3 of 52 (DC, Montana, Wyoming, flat); above the field's 90th
    percentile 7 (was 13), above the field maximum none (was 1); median
    jurisdiction 1.10x the ensemble (was 1.15x); Florida 777, 980, 1,217,
    1,496 (2.7x); Hawaii 237 (was 367), New York 375 (was 463); Illinois 93,
    Michigan 60, Wisconsin 49, Oregon 75, Maine 21, Puerto Rico 126, Alaska
    26. The lever is the research knob oracle.w in the Forecast tab's Model
    settings panel (group Oracle SIHRS: Oracle step; no refit; a hub-named
    export with it needs the typed override reason; the card says "at weight
    one half"). Lower w = more donor; w = 1 is the constant-rate
    extrapolation of the filter's first week, not the plain filter. The
    knob's help text says the opposite ("weight of the donor's growth"): App
    lane, see For other lanes.
  - Partial submissions (Ely's question): the hub's README says teams are
    not required to submit all locations or horizons; an omitted cell is not
    scored; CDC's season evaluation needs at least 75% of the admissions
    quantile targets over the remaining weeks and jurisdictions
    (FLUSIGHT-2026-27.md). Unticking a handful of states for a few early
    weeks stays far above the line; the cost is the visible gap on the
    dashboard, not the score. Offered as a standing Wednesday step before
    the compare link: decliners below the last observed week, cells above 3x
    at horizon 3, the medians against the previous round's ensemble path,
    and each cell's recorded stage and weight; pending Ely's yes.
  - For the Wednesday meeting of the NAU teams Ely asked for a broken-down
    explanation (before/now, the weekly update and propagation, how i0 is
    set, where 0.18 comes from): written as a Claude doc Ely can edit,
    "Oracle SIHRS seeding explained"
    (https://claude.ai/code/artifact/42279b08-d776-4455-8a3d-420807ac15ba),
    eight sections with Florida as the worked example, a chart of the data
    and the three forecast paths, and a drawn flow of one filter update.
- 2026-10-09 (20:10 UTC): ELY CHOSE THE STAGE-AWARE RULE; IT IS ON THE
  BRANCH AND THIS WEEK'S FORECASTS WERE RERUN WITH IT. Branch
  `seed-denominator` c09e7bc adds the third knob value
  `pf.seed_denominator=season_total_early`: while the season-to-date
  per-capita count is below `EARLY_FRACTION = 0.25` of the expected total
  (strict), rho*mult and i0 are pinned on the expectation exactly as
  season_total pins them; from there the shipped to-date rule, bit for bit.
  The seed_pin record names the stage (expected or to_date) and the
  fraction; shipped cells are unchanged. Tests: the pin at 1,899 against
  1,900 of 7,600, an all-zero trimmed series, the guards (an expectation
  handed to the to-date rule raises), the prepare-level record. Full suite
  on the branch: 3,108 passed, 82 skipped (two earlier runs showed one error
  in app/tests/test_window_downloads.py that passes alone on the branch and
  on dev and did not recur: an ordering interaction, not this diff). An
  adversarial review of the diff found one defect, fixed before the commit:
  the stage was read off the factor, which is NaN on a series a trim leaves
  all-zero, so the record would have said to_date while the pin was the
  expectation; the stage now comes from the pin itself and one helper in
  pf.prepare re-derives pin and stage together after a trim or a reporting
  correction. The rule is post-hoc, named after the early-week replay and
  before the peak replay, and scored once from those stored runs (the entry
  of 14:30 UTC); the code and the record say so.
  - The rerun (root replays/2026-27-stage, both 2026-27 vintages, all 52
    jurisdictions x 3 seeds, Oracle step applied; replays/compare_stage.py,
    compare_stage_result.txt), Oracle SIHRS member medians as-of 2026-10-03
    against the submitted file: of the 11 submitted decliners (horizon-3
    median below the last observed week), 6 now rise (Illinois 67 -> 74 at
    horizon 3 instead of 44; Michigan 41 -> 48 instead of 27; Wisconsin 32
    -> 42 instead of 18; Oregon 35 -> 80 instead of 31; Maine 14 -> 18
    instead of 11; Puerto Rico 81 -> 110 instead of 73) and 5 small
    jurisdictions still decline, less steeply (Montana 15 -> 8.8, was 5;
    Alaska 22 -> 19, was 15; District of Columbia 2 -> 1.4, was 1; South
    Dakota 4 -> 4.0, was 3; Wyoming 3 -> 2.5, was 1). Declining
    jurisdictions 11 of 52 -> 5 of 52. Every jurisdiction's horizon-3 median
    rises relative to the submitted one (Vermont unchanged at 1): median
    horizon-3/last 1.40 -> 2.25 across the 52, 1.67 -> 2.56 among the 17
    with 50 or more admissions last week; above 3x in 17 jurisdictions (was
    1), above 4x in 5 (New Hampshire 9 -> 99, Hawaii 64 -> 365, Delaware 9
    -> 45, North Carolina 78 -> 329, Indiana 58 -> 239; the large states
    steepen too: Florida 559 -> 1,875 at horizon 3 instead of 1,037,
    California 451 -> 953 instead of 575, Texas 326 -> 769 instead of 522).
    All 52 are in the expected stage this week (to-date at 0.8% to 21.6% of
    the expectation, median 2.9%; Alaska 21.6% and Hawaii 17.4% are nearest
    the quarter), so the rerun equals the season_total arm of 2026-10-07 bit
    for bit where the two overlap; the stage rule changes nothing until a
    jurisdiction crosses the quarter. The US cell is not in a retro run (the
    retro scores the nation as the sum of the states), so the national row
    was not rerun. Reading: the downward trajectories are fixed where counts
    are large and softened where they are small; the cost is a steeper
    upward tail, which the early-week replay scored as a net gain (all 52
    better on the log scale) but which Ely should look at before Wednesday:
    the Oracle step and the fitted growth, not the seed, set the slope once
    depletion stops braking it.
  - Next (Submission lane, for Wednesday 2026-10-14): Ely confirms the rerun
    picture; Model/App review the branch (see For other lanes); merge
    seed-denominator -> dev -> main by Tuesday night; card 1.4 with the new
    i0 sentence replaces the staged 1.3 and goes to the hub with the
    2026-10-17 forecast; a note to Spencer after Ely's go. Whether
    season_total_early becomes the shipped default or runs as the knob with
    an override reason is Ely's call with the Model lane; either way the
    record says the rule is post-hoc and scored once.
- 2026-10-09 (14:30 UTC): THE PEAK REPLAY IS COMPLETE; STOP RULE 3 TRIPS ON
  THE NATURAL SCALE AND PASSES ON THE LOG SCALE. Eight vintages around each
  season's US peak, three seasons, both arms, all 52 jurisdictions x 3 seeds
  (roots replays/peak-<season>-<arm>; replays/score_peak_final.txt,
  stage_rule_final.txt). Peak windows pooled, 4,992 common Oracle cells:
  shipped relWIS 0.797, log-scale 0.956, coverage 50/80/95 = 0.56/0.85/0.96;
  knob 0.974, log 0.994, 0.55/0.85/0.97. By season (relWIS / log): 2023-24
  shipped 1.123 / 1.125 against knob 1.535 / 1.223; 2024-25 0.522 / 0.664
  against 0.525 / 0.660 (identical: the floor had returned the shipped
  rule); 2025-26 1.036 / 1.181 against 1.351 / 1.225. The knob loses at the
  peak vintages themselves (2023-24: log 1.274 / 1.661 against 1.061 / 1.173
  on 12-23 and 12-30) and is level or slightly ahead in the weeks after; the
  filter alone loses more (peaks pooled 1.136 / 1.283 against 0.750 /
  1.215).
  - Early and peak windows together, 44 weeks, 9,152 common Oracle cells,
    the nearest thing to whole seasons available: shipped relWIS 0.767,
    log-scale 0.864; knob 0.822, log 0.779. Stop rule 3 ("wins early but
    loses whole seasons by more than 0.02"): on the natural scale the knob
    loses by 0.055 (trips); on CDC's log scale it wins by 0.085 (passes).
    Rules 1 and 2 pass on both scales. So the knob as drafted is a log-scale
    improvement with a natural-scale cost concentrated at early peaks.
  - The stage-aware rule, scored from the same stored runs (per
    location-week, the knob arm while the season-to-date count is below a
    fraction of the expected total, the shipped arm after; the fraction is
    computed from the vintage exactly as the knob computes its expectation):
    at the 0.25 threshold named before the peak replay ran, pooled relWIS
    0.752, log 0.773, knob share 45% of cells; against shipped 0.767 / 0.864
    and knob 0.822 / 0.779. It beats the shipped rule on both scales, beats
    the knob on the natural scale, and is within 0.006 of it on the log
    scale; by block it is never the worst of the three. Exploratory sweep
    (not pre-specified): 0.1 gives 0.741 / 0.787, 0.5 gives 0.805 / 0.779,
    1.0 gives 0.822 / 0.779. Caveat: the rule as scored switches the pin
    abruptly at the threshold (the seeded i0 jumps by the factor in one
    week); the filter refits every week so the stored forecasts already
    carry that jump, but a smooth version was not scored and must not be
    assumed to behave the same.
- Submission lane's reading for Ely's decision (needed by Tuesday 2026-10-13
  for the 2026-10-14 run): (a) the stage-aware rule at 0.25, implemented as
  a third knob value (season_total_early, threshold 0.25), is the only
  option that is better than the shipped rule on both scales everywhere it
  was scored; it is a post-hoc design scored once, which the record must
  say; (b) the knob as drafted is the better choice if CDC's log-scale
  relWIS is the target the team optimizes, and the worse one on the natural
  scale; (c) Plan C (untick the declining locations) changes no method. This
  week's situation (to-date at 2-7% of the expectation) is the regime where
  (a) and (b) coincide. Whatever ships, the card's i0 sentence changes (1.4)
  and the Model lane owns the method statement. The cloud engine, the roots
  and the scorer stay available for a further arm if the Model lane wants
  one before Tuesday.
- 2026-10-09 (07:05 UTC, peak replay, 2024-25 complete in both arms; 2023-24
  running, about 6.5 hours): the eight vintages around the 2024-25 US peak
  (as-of 2025-02-01 to 03-22; peak week 2025-02-08), 1,664 common Oracle
  cells: the two arms are the same forecast. Shipped relWIS 0.522, log-scale
  0.664, coverage 50/95 = 0.69/0.99; knob 0.525, log 0.660, 0.69/0.99; by
  week (log) 1.275 / 1.248, 0.890 / 0.884, then identical to three decimals
  from 02-22 on. That is the floor working as designed: by February of a
  season this large the to-date count had passed the expected total, so
  season_total and to_date coincide. The knob's peak weakness is therefore
  specific to a peak that arrives while the to-date count is still well
  below the expectation (2025-26, a January peak at about half the expected
  total); it does not appear in a late, large season.
- 2026-10-08 (23:35 UTC, peak replay, 2025-26 complete in both arms; the
  2024-25 and 2023-24 peaks run overnight): the eight vintages around the
  2025-26 US peak (as-of 2025-12-27 to 2026-02-14), 1,664 common Oracle
  cells: shipped relWIS 1.036, log-scale 1.181, coverage 50/95 = 0.42/0.92,
  h3 median below the origin in 84% of cells; knob 1.351, log 1.225,
  0.40/0.93, 76%. By week (log, shipped against knob): 12-27 1.176 / 1.645,
  01-03 0.732 / 0.960, 01-10 0.666 / 0.629, 01-17 1.564 / 1.291, 01-24 1.915
  / 1.754, 01-31 1.625 / 1.589, 02-07 1.301 / 1.326, 02-14 1.051 / 1.075. So
  the knob loses at the two peak vintages, wins the four weeks after, and is
  level on the last two; over the window it is behind by 0.044 on the log
  scale and 0.31 on the natural scale. Both arms score worse than the
  FluSight baseline through the decline (log relWIS above 1 in five of the
  eight weeks; the Groundhog is at 0.80 there), which is the Oracle SIHRS's
  known post-peak weakness, not the seed's. The filter alone: shipped 0.927
  (log 1.503), knob 1.601 (log 1.603). Against the early-season gain of 0.17
  on the log scale in this season (0.509 against 0.675 over six weeks), the
  peak-window loss of 0.04 over eight weeks leaves the knob ahead for
  2025-26 as a whole on the weeks run so far; stop rule 3 is read once the
  other two seasons' peaks are in.
- 2026-10-08 (21:00 UTC, peak replay interim; the rest still running): AT
  THE PEAK THE KNOB LOSES. 2025-26, the two vintages at the US peak (as-of
  2025-12-27 and 2026-01-03; peak week 2026-01-03), 416 common Oracle cells:
  shipped relWIS 1.087, log-scale 0.897, coverage 50/95 = 0.46/0.97; knob
  1.741, log 1.214, 0.30/0.88. By week (log): 12-27 1.176 against 1.645,
  01-03 0.732 against 0.960. The filter alone: shipped 0.624 (log 0.677, 95%
  coverage 0.99), knob 2.049 (log 1.327, 0.78). So the shipped seed's
  depletion, wrong in October, is about right at the peak (the filter alone
  turns on time), and the knob, with cumulative infections still only about
  half the expected total, keeps rising through it: the no-brake failure the
  verifier predicted, now measured. The six post-peak weeks of 2025-26 and
  the 2024-25 and 2023-24 peaks follow (about 12 hours). Reading for the
  decision: the knob is a clear win in the early season (this week's
  problem) and a loss at the peak; a stage-aware rule (season_total while
  the to-date count is a small fraction of the expectation, the shipped rule
  after) can be scored from the runs already stored, both arms at both
  stages, without new compute; that is a post-hoc design and the Model
  lane's and Ely's call, not the Submission lane's.
- 2026-10-08 (17:00 UTC): THE EARLY-WEEK REPLAY IS COMPLETE AND THE KNOB
  PASSES ITS STOP RULES. Three seasons, first 8 vintages each, all 52
  jurisdictions x 3 seeds, both arms, the real engine (feature/particle-
  filter 2fdadee0), scored with the app's scorer against settled truth and
  the hub's baseline on the common cells (20 scoreable weeks; the 2023-09-23
  and 09-30 and the 2025-08-30 and 09-20 vintages have no baseline). Oracle
  SIHRS member, 4,160 common cells, pooled: shipped relWIS 0.741, log-scale
  relWIS 0.814, coverage 50/80/95 = 0.42/0.70/0.90, h3 median below the
  origin in 30% of cells; knob 0.689, log 0.662, 0.58/0.87/0.98, 13%. By
  season (relWIS, log): 2023-24 shipped 0.791 / 0.753 against knob 1.125 /
  0.760; 2024-25 0.804 / 0.962 against 0.748 / 0.744; 2025-26 0.655 / 0.675
  against 0.575 / 0.509. By horizon (log): knob better at every horizon,
  0.716 / 0.669 / 0.645 / 0.647 against 0.813 / 0.803 / 0.804 / 0.830. By
  state size (log): small 0.796 against 0.983, mid 0.635 against 0.771,
  large 0.550 against 0.684. By location: the knob's pooled log WIS is lower
  in 52 of 52 jurisdictions. The filter alone: shipped 0.917 (log 1.068, 95%
  coverage 0.78), knob 0.832 (log 0.710, 0.97). The Groundhog is identical
  in both arms (0.643, log 0.588), as it must be. Files: the Submission
  scratchpad, replays/score_early_final.txt, pooled_breakdown.txt,
  breakdown_<season>.txt; roots replays/early-<season>-<arm>.
  - Stop rules (set 2026-10-07 before any run): (1) "not better on pooled
    early-week relWIS": the knob is better on both scales (passes); (2)
    "loses more than 0.05 of 95% coverage": it gains 0.08 (passes); (3)
    "wins early but loses whole seasons by more than 0.02 (the brake near
    the peak)": open, whole seasons not run; the 2024-25 early weeks reach
    that season's peak (2024-12-28 and 2025-01-04) and the knob is still
    ahead there (log 0.938 against 1.113, 1.056 against 1.064). The
    pre-registered next step is whole seasons; on this machine that is about
    50 hours, so a PEAK replay runs first: the two vintages at or before
    each season's US peak week (2023-12-30, 2025-02-08, 2026-01-03) and the
    six after it, 8 x 3 seasons, both arms, started 17:00 UTC, about 20
    hours (roots replays/peak-<season>-<arm>; `REPLAY_PREFIX=peak python
    replays/score_early.py` scores it). If it holds, rule 3 is as answered
    as it can be before Monday; the rest of the seasons can follow over the
    weekend.
  - 2023-24 is the one honest reservation: the knob overshot the large
    counts there (natural-scale relWIS 1.125 against 0.791; a wash on the
    log scale), with a one-season expectation (2022-23) and an early season.
    2024-25 and 2025-26, with two and three past seasons, are wins on every
    cut. For 2026-27 the expectation comes from four seasons.
- Decision for Ely (by Tuesday 2026-10-13 for the 2026-10-14 run), the
  Submission lane's reading: ship the knob. What shipping takes: (a) make
  season_total the shipped rule (`SEED_DENOMINATOR = "season_total"` in
  flubnf/sihrs_priors.py, the tests that pin the shipped path updated,
  `to_date` kept as the research value), or run Wednesday with the knob on
  and the override reason given (the console marks the run modified); the
  first is cleaner and is what the record should show; (b) merge
  `seed-denominator` to `dev`, then `main`, by Tuesday night (Model and App
  review first; the Submission lane can do the merge with Ely's go-ahead);
  (c) card 1.4: methods_long's i0 sentence says the pin is on the expected
  season total (the median of the completed past seasons' per-capita totals,
  floored at the to-date count); Submission copies it to the hub with next
  week's forecast, replacing the staged 1.3; (d) the collaborator hears that
  the fix is in. Plan C stays if Ely prefers to wait for whole seasons.
- 2026-10-08 (12:15 UTC, interim 4; 2025-26 running): 2024-25 complete in
  both arms, 8 weeks (as-of 2024-11-16 to 2025-01-04, through the peak),
  1,664 common Oracle cells: the knob wins on both scales and in every cut.
  Oracle member: shipped relWIS 0.804, log-scale 0.962, coverage 50/95 =
  0.35/0.88, h3 median below the origin in 55% of cells; knob 0.748, log
  0.744, 0.53/0.98, 25%. Log scale by week, shipped against knob: 11-16
  0.762 / 0.747, 11-23 0.948 / 0.720, 11-30 1.042 / 0.738, 12-07 0.991 /
  0.690, 12-14 0.896 / 0.662, 12-21 0.956 / 0.718, 12-28 1.113 / 0.938,
  01-04 1.064 / 1.056 (the knob better in all eight, narrowly at the peak).
  By horizon (log): knob better at every horizon, the gap widening to h3
  (0.720 against 0.999). By state size (log): small 0.840 against 1.117, mid
  0.714 against 0.900, large 0.680 against 0.873. By location: the knob's
  log WIS is lower in 51 of 52 jurisdictions (Minnesota 1.02 the exception;
  California 0.59, Texas 0.61, New York 0.62 the largest gains). The filter
  alone: shipped 0.964 (log 1.267, 95% coverage 0.74), knob 0.841 (log
  0.812, 0.96).
  - Pooled, 2023-24 (6 scoreable weeks) plus 2024-25 (8), 2,912 common
    Oracle cells: shipped relWIS 0.803, log-scale 0.894, coverage 50/80/95 =
    0.46/0.75/0.92, below-origin 39%; knob 0.772, log 0.749, 0.61/0.88/0.98,
    17%. The knob is now ahead on both scales pooled: its 2023-24 overshoot
    cost is outweighed by 2024-25. Stop rules so far: better on pooled
    early-week relWIS on either scale (passes); 95% coverage up, not down
    (passes); whole seasons not run yet (the third rule, the brake near the
    peak, is open; the 2024-25 peak weeks above are the first hint and they
    favour the knob narrowly). 2025-26 (two August-September vintages and
    six from mid-November to December) finishes this afternoon UTC.
- 2026-10-08 (10:05 UTC, interim 3; the 2024-25 knob arm and 2025-26 still
  running): 2024-25, the first three vintages both arms share (as-of
  2024-11-16, 11-23, 11-30; a late, large season; expectation from two
  seasons), 624 common Oracle cells: the knob WINS on the log scale. Oracle
  member: shipped relWIS 0.770, log-scale 0.936, coverage 50/95 = 0.38/0.89,
  h3 median below the origin in 40% of cells; knob 0.804, log 0.734,
  0.63/0.99, 15%. By week, log scale, shipped against knob: 11-16 0.762 /
  0.747, 11-23 0.948 / 0.720, 11-30 1.042 / 0.738: the shipped seed's turn
  costs most in late November, as the verifier's mini-replay said, and the
  knob removes it. The filter alone: shipped 1.017 (log 1.293, 95% coverage
  0.76), knob 1.031 (log 0.826, 0.98).
  - Pooled so far (2023-24's six scoreable weeks plus these three, 1,872
    common Oracle cells): shipped relWIS 0.776, log-scale 0.834, coverage
    50/80/95 = 0.54/0.82/0.95, below-origin 24%; knob 0.892, log 0.748,
    0.68/0.92/0.99, 8%. On CDC's log scale the knob is ahead pooled and
    better calibrated; on the natural scale it is behind (its overshoots in
    the large counts of 2023-24). Still to come: five more 2024-25 weeks
    (through 2025-01-04, around the peak) and 2025-26 (two August and
    September vintages and six from mid-November to December). Decision
    waits for the full set; the scale question is Ely's.
- 2026-10-08 (06:15 UTC, interim 2; 2024-25 and 2025-26 still running):
  2023-24 complete in both arms, 8 weeks each, 6 scoreable (as-of 2023-10-07
  to 11-11), 1,248 common Oracle cells, 52 jurisdictions x 3 seeds, the
  app's scorer against settled truth and the hub's baseline:
  - Oracle member, pooled: shipped relWIS 0.791, log-scale relWIS 0.753,
    coverage 50/80/95 = 0.62/0.89/0.98, h3 median below the origin in 19% of
    cells; knob relWIS 1.125, log-scale 0.760, coverage 0.71/0.93/0.99,
    below-origin 6%. So on the natural scale the knob is clearly worse (the
    overshoots in large counts); on the log scale, which is CDC's headline
    relWIS, it is a wash (0.760 against 0.753) with better coverage.
  - By week, log scale, shipped against knob: 10-07 0.730 / 0.839, 10-14
    0.684 / 0.749, 10-21 0.730 / 0.741, 10-28 0.859 / 0.824, 11-04 0.786 /
    0.722, 11-11 0.719 / 0.692: the knob loses the first three weeks and
    wins the last three, as the verifier's mini-replay predicted (better by
    late November). On the natural scale the knob loses every week (1.00 to
    1.57 against 0.69 to 0.92).
  - By horizon, log scale: the knob is worse at h0 (0.817 against 0.801) and
    h1, equal at h2, slightly better at h3 (0.731 against 0.735); on the
    natural scale it is worse at every horizon and the gap grows with the
    horizon (h3 1.30 against 0.80). By state size: small states 0.978
    against 0.950 (log), large 0.595 against 0.607.
  - The filter alone: shipped 0.860 (log 0.891), knob 1.798 (log 0.844),
    coverage 95% 0.95 against 0.99. The Groundhog is identical in both arms
    (1.055, log 0.663), as it must be.
  - Reading: in 2023-24 (an early season, a one-season expectation) the knob
    trades the shipped seed's early-season declines for overshoots of about
    the same log-scale cost, with better calibration. The stop rule as
    written ("not better on pooled early-week relWIS") trips on the natural
    scale and is a coin toss on the log scale; Ely decides which scale the
    rule meant (CDC's evaluation is log scale). Two seasons to go; the
    decision waits for them.
- 2026-10-08 (05:00 UTC, interim; the replay continues): the first scoreable
  weeks of 2023-24 (as-of 2023-10-07 and 10-14; the hub's baseline starts
  with the 2023-10-14 reference date, so the two earlier vintages score
  nothing), 416 common Oracle cells, the app's scorer against settled truth:
  the knob arm is WORSE. Oracle member: shipped relWIS 0.849 (log scale
  0.707), knob 1.347 (0.793); 95% coverage 0.99 in both, 50% coverage 0.71
  against 0.76; share of h3 medians below the origin 0.19 against 0.05. The
  filter alone: shipped 0.877 (0.784), knob 2.011 (0.884). The Groundhog is
  identical in both arms (1.373), as it must be. The loss is the overshoot
  the verifier predicted, in the real filter. Two weeks of one season, with
  a one-season expectation (2022-23); 2024-25 and 2025-26 follow. The stop
  rule "not better on pooled early-week relWIS" is on course to trip; if it
  does, the knob does not ship for 2026-10-14 and Plan C applies unless the
  Model lane has a growth-limited variant it can test in time.
- 2026-10-08 (02:10 UTC): the cloud session's container was reclaimed about
  five minutes after the session went idle (23:31 UTC), which killed the
  detached replay after 81 cells of its first week; the scratchpad, the
  engine venv and the clones survived. Resumed at 02:12 UTC as a job the
  session tracks, with a self check-in every 25 minutes to keep the
  container alive; the retro resumes finished cells. Pace measured before
  the kill: 17 cells a minute on 4 runners for the early 2023-24 weeks (8
  observations a cell), so about 9 minutes a week-arm there and longer where
  the series are longer; new estimate 8-9 hours, scored around 11:00 UTC
  Thursday (04:00 Arizona) if nothing else interrupts. Lesson for the lanes:
  a long run in a cloud session must be a tracked job plus check-ins, never
  a detached process.
- 2026-10-07 (23:25 UTC): the direction check ran clean with the real
  engine, both arms (`flubnf retro run 2026-27`, vintages 2026-09-26 and
  2026-10-03, 19 locations x 3 seeds, 2 runners, about 500 s a week-arm, 17
  s a cell-runner). Branch `seed-denominator` (e916dac) is pushed (Ely's
  go-ahead, 2026-10-07). Findings:
  - The cloud engine reproduces production: the shipped arm's Oracle medians
    at the 2026-10-03 vintage equal the submitted file's to the rounding at
    all 19 locations and 4 horizons (CA 466 / 504 / 541 / 575 against 466 /
    504 / 540 / 575; TX 364 / 413 / 468 / 522 against 364 / 413 / 467 /
    522), and its 11 decliners are exactly the submitted ones (IL, MI, WI,
    MT, AK, OR, ME, PR, DC, SD, WY).
  - The mechanism is visible in the filter alone: under the shipped seed the
    Liu-West filter's own medians decline by h3 in 19 of 19 locations this
    week (CA 451 -> 242, TX 326 -> 289, FL 559 -> 450); the Oracle step
    rescues 8 of them.
  - With the knob (season_total), the Oracle member declines in 5 of 19 (MT
    0.59 of last, DC 0.68, WY 0.85, AK 0.87, SD 0.99), the filter alone also
    in 5 (MT, AK, ME, DC, WY: the data turned down there). The turned-around
    locations rise steeply: over four weeks CA x2.1, WA x2.2, TX x2.4, FL
    x3.4, NY x3.4, NC x4.2, HI x5.7 (filter alone FL x7.2, NY x7.4, NC
    x10.9; the Oracle step halves these in growth terms). Against the
    Groundhog's US x2.0 that is the no-brake overshoot the verifier warned
    of, now in the real filter; IL, MI, WI go from declines to
    flat-to-rising (x1.1-1.3). Truth in four weeks tells which arm was right
    this week; the replay tells in general.
  - The early-week replay started at 23:26 UTC in the cloud session,
    unattended: 2023-24, 2024-25, 2025-26, first 8 vintages each, all 52
    jurisdictions x 3 seeds, shipped arm then knob arm per season, 4
    runners; roots replays/early-<season>-<arm> in the Submission
    scratchpad; about 9 hours, so scored around 09:00 UTC Thursday (02:00
    Arizona). Scoring: `app.core.retro.score_season` per root, members `pf`
    (Oracle SIHRS), `pf_filter` (the filter alone) and `analogue`; pooled
    relWIS and coverage on the common cells of the two arms, plus the share
    of cells with the h3 median below the origin; the stop rules above
    decide.
- 2026-10-07 (night): the diagnosis was checked twice by agents reading the
  code and the hub data, and the fix was tested on a deterministic stand-in.
  None of it is a filter run; the replay below decides.
  - Mechanism confirmed, with two corrections of framing. The model is not
    past its peak AT the origin: the filter fits Reff about 1.34, so the h0
    and h1 medians sit above the last count. The turn comes from depletion
    over the horizon (about 4% of N a week for the US under the shipped
    seed, 0.2% under the fix), so the peak lands at h1-h2. The Oracle step
    is a geometric mean in G = gamma + lam and replaces the filter's own
    weeks 2-4; "halves the decline" holds only against a flat donor, and a
    cell still declines iff (gamma + lam_T)(gamma + lam_d) < gamma^2.
  - REFUTED, correcting the evening entry: the turn does not fade "because
    the season fills in". By Nov 28 only 2.5-26% of a season's total has
    accrued (US 0.256, 0.100, 0.025, 0.064 in 2022-23 to 2025-26), and the
    weekly-to-cumulative ratio that sets the depletion speed is higher in
    late November than now. A deterministic mini-replay puts the shipped
    seed's turn at its worst at the Nov 29/30 vintages of 2025-26 and
    2024-25 (US 2025-11-29: 6179 / 7336 / 7661 / 6988 against truth 7450 /
    11137 / 21057 / 37502). Whatever fades in the real replays is the fitted
    harmonic or slowing growth, not the cumulative.
  - The stand-in (one least-squares SIHRS per location on log(1 +
    admissions) over 2026-08-01 to 10-03, the template's constants and
    bounds; no particles, jitter, negative binomial or Oracle step; files in
    the Submission scratchpad, round-2026-10-10/work/patch/demo): shipped
    seed, 30 of 53 locations decline by h3; season-total seed, 13. US 3677 /
    3790 / 3521 / 2978 against 3942 / 4528 / 4891 / 4923 (submitted Oracle
    3648 / 4180 / 4707 / 5304; Groundhog 3426 / 4291 / 5800 / 6480; last
    observed 3246). The fix turns US, OR, CA, NC, NY, TX and HI around; WI,
    MT, AK, ME, PR, DC, WY, WA and MN decline under both seeds (data
    downturns in the last 1-2 weeks, or the annual harmonic fitting the
    recent deceleration). Its cost: with 0.2-2.6% of N infected (46 of 53)
    there is no brake yet, 18 small locations climb faster than 1.5x a week
    (9 at the Reff bound; 11 had 20 or fewer admissions last week), and in
    DC, WY, ME, MT and AK the fit pulls mult 2.4-141x below the seed and
    re-creates the depletion.
  - The verifier's caution: "removes the early-season turn" is overstated.
    At the same stage last season (the 2025-10-04 vintage) both seeds
    declined alike (US shipped 874 / 760 / 629 / 497, fix 875 / 755 / 614 /
    468, truth 1018 to 1358): when the recent weeks decelerate, the annual
    harmonic absorbs it under the fix as depletion does under the shipped
    seed. This year's rise under the fix rests on that harmonic (28 of 53
    fits put peak transmission before mid-October), so only "rises at h0-h1"
    is identified, not the h2-h3 level. Over eight autumn vintages of
    2025-26 and 2024-25 (six locations, deterministic) the fix is a wash on
    point forecasts (mean absolute log error 0.87 against 0.90): clearly
    better at the late-November vintages, clearly worse where it overshoots
    (US 2024-11-02: 2414 / 5347 / 13652 / 38832 against truth 2176 / 2611 /
    3278 / 4436), because the expected-total pin sets the scale but not the
    SIR's final size.
  - So the fix is a candidate, not a ship. The replay decides under the stop
    rules above; expect a mixed result and read it with the Oracle step on
    and off (the scorer scores the filter alone as `pf_filter` beside the
    Oracle member, so one run gives both) and at the peaks, not only the
    early weeks. Pre-specified for the replay: the expectation is the median
    of however many completed seasons the vintage holds (one for 2023-24,
    namely 2022-23; two for 2024-25; three for 2025-26); a location with
    none falls back to the shipped rule, recorded. A growth-limiting variant
    for small states (a tighter Reff or eps1 prior, or a cap) is the Model
    lane's call and is not in the knob.
  - Carried from the skeptic: the closed trials "swarm-carry 1B hindsight
    ORACLE 1.047" and "donor-informed i0 priors: null" may already be
    P1-like; Model, please read those records (FluBNF-local research/)
    before the replay result is interpreted. fit_i0's 0.889 is not evidence
    against the fix: it opened the i0 x mult ridge, the fix keeps one pinned
    product.
- 2026-10-07 (night): the knob is implemented on branch `seed-denominator`
  (e916dac, from `dev` 1176d9e), by the Submission lane with Ely's go-ahead
  since the Model and App lanes could not be reached; please review rather
  than re-implement. As designed, with two differences: the cell record key
  is `seed_pin` (`seed` is the engine's RNG seed) and the knob help is
  shorter; `pf.seed_denominator` sits in `_FIT_ORDER` after
  `pf.initialization`. Full suite: 3104 passed, 82 skipped, 0 failed. A
  real-data check on the 2025-11-22 vintage resolves all 52 jurisdictions
  with three completed seasons each (factor 1.9 to 163, median 19.7). Ely
  (2026-10-07): the branch is pushed once the knob arm runs clean with the
  real engine; `dev` is untouched.
- 2026-10-07 (night): the private engine now runs in the Submission lane's
  cloud session. Ely granted the Claude GitHub App access to
  elyfmiller/PyBNF-Private; `feature/particle-filter` 2fdadee0 is installed
  in an engine venv with BioNetGen 2.9.3 (the bionetgen 0.8.7 wheel), bngsim
  0.15.1 and numpy 1.26.4; `flubnf.settings.check()` passes; the hub clone
  is a mirror of cdcepi `main` with this week's live file added as the
  2026-10-03 vintage. Running: the direction check, `flubnf retro run
  2026-27` on the 2026-09-26 and 2026-10-03 vintages, 19 locations x 3
  seeds, shipped arm and knob arm, about 8 minutes a week-arm on 2 runners
  (about 20 s a cell). Next, unattended: the early-week replay above, all 52
  jurisdictions, both arms, 4 runners, about 10-12 hours, scored Thursday;
  whole seasons after that if the early weeks pass. The shipped arm is rerun
  here because the stored shipped replays are on the lab Mac; Model, if you
  can export them (`flubnf retro export`), say so.
- 2026-10-07 (evening): THE SEED FIX IS THE TOP PRIORITY OF EVERY LANE
  UNTIL THE 2026-10-14 ROUND (Ely). A collaborator's six-member ensemble
  (NAU plus UGA) flagged the Oracle SIHRS declines (WI, WY); Ely answered
  that a fix is in test and hoped for next week. The cause, checked
  against the code (`flubnf/sihrs_priors.py pin_rho_mult`,
  `flubnf/sihrs_fit.py resolve_state`, the template): rho*mult is pinned
  as (season-to-date admissions per capita) / 0.18, so the admissions
  since Aug 1 always stand for a FULL season's 18% attack rate. At every
  forecast date the model has 18% of the population already infected,
  S/N = 0.67 at the origin and R_eff = 0.79 x Reff; the fitted Reff must
  exceed 1.27 before the model grows at all. The seed i0 is wrong by the
  factor (expected season total) / (to date): US x20, IL x24, WI x26,
  MT x15, MI x36, AK x4.6, PR x7.8, WA x9, HI x5.7, CA x11 (median of the
  four past seasons' per-capita totals, 86.8/100k for the US, against
  4.3/100k so far). It eases through the season because the data force
  Reff up and i0 shrinks as 1/cumulative, not because the brake is right.
  The Oracle step halves the decline in growth terms; the 11 locations
  where the filter's own lam_T is most negative still decline. `fit_i0`
  (a free i0) is not the same fix: it removes the brake altogether and
  scored worse on whole seasons (0.889 against 0.749); the fix below
  keeps a brake that grows with the season.
- 2026-10-07: the plan, with the lanes it needs (details under For other
  lanes; the design is the Submission lane's draft for the Model lane to
  check, not a decision on the method):
  - Plan A (the fix): research knob `pf.seed_denominator` with values
    `to_date` (shipped default, production bit-identical) and
    `season_total`: rho*mult pinned on the median per-capita total of the
    completed past seasons in the same as-of vintage (>= 35 finite weeks;
    the dated archive files carry the whole history from 2022-02, so it
    is as-of safe), floored at the to-date value so the factor is never
    below 1 and the shipped rule returns once a season passes its
    expectation; i0 from the same pin; a location with no completed
    season falls back to the shipped rule, recorded. Attack rate 0.18 and
    s0 0.85 unchanged. One `pin_from()` used by resolve_state, the trim
    re-derivation and the reporting model in `pf.prepare`; cells.json
    gains a `seed` dict only when the knob is on.
  - The decisive replay (Model, lab Mac): the first 8 vintages of
    2023-24 (2023-09-23 to 11-11), 2024-25 (2024-11-16 to 2025-01-04)
    and 2025-26 (2025-08-30, 09-20, 11-15 to 12-20) with the knob,
    53 x 3, against the stored shipped replays, scored with the app's
    scorer (relWIS on common cells, 50/80/95 coverage, share of cells
    with the h3 median below the origin): 24 week-runs at about 5
    minutes = about 2 hours. Whole seasons (74 more weeks, about 6
    hours) only if the early weeks win in 2 of 3 seasons. A 5-minute
    direction check on this week's live data can run first.
  - Stop rules: the knob arm is not better on pooled early-week relWIS;
    or it loses more than 0.05 of 95% coverage; or it wins early but
    loses whole seasons by more than 0.02 (the brake near the peak).
  - Plan B: the same replays on Ely's laptop (2-3x slower) if the lab
    Mac cannot be reached.
  - Plan C (Ely, decided): if no fix is in by 2026-10-14, untick the
    declining Oracle SIHRS locations for that round (this week's 11 would
    leave 42 of 53 = 79%, above CDC's 75% rule); the Groundhog keeps
    every location.
  - Timeline: knob on `dev` by Fri 10-09 (Model, App); early-week replay
    scored by Sun 10-11; Ely decides Mon 10-12; whole seasons Mon-Tue if
    needed; `main` by Tue 10-13 night; card update and hub metadata pull
    request Tue if the method ships (methods_long's i0 sentence and the
    "frozen-specification" phrase, version 1.3); Wed 10-14 run with the
    knob, else Plan C.
- 2026-10-07: cdcepi/FluSight-forecast-hub#3730 merged at 18:54 UTC
  (1e47fc5); both files on the hub's `main` are byte-identical to the
  checked ones. Next round (2026-10-17, due 2026-10-14) reuses
  `FluBNF_submission`: fast-forward it to cdcepi `main` first.
- 2026-10-07: round 2026-10-10 (EW40) submitted as is:
  cdcepi/FluSight-forecast-hub#3730 from `FluBNF_submission` (2605672,
  plus Ely's sync merge ab91b74). It adds only the two files, and both
  are byte-identical to the files Ely ran (both 4,877 lines). Both pass
  `validate_submission.R`, 31 checks with `--window`, against the hub
  (target data of 2026-10-07; the hub's later commits are other teams'
  files). The Groundhog file is byte-identical to a cloud regeneration
  from `main`. The Data issues box was empty: all 53 locations reported
  2026-10-03, with no zero or collapsed newest week.
- 2026-10-07, sense check (for the post-round review; no blockers): every
  2026-10-03 count is inside both models' h0 50% and 95% intervals, and
  every trend projection is inside both 95% intervals at h0 and h1. The
  two models' 95% intervals overlap everywhere. Both medians sit 15-25%
  below the US growth path (about 27% a week; the season is 3x the
  same week of 2022-25 and 4-7 weeks ahead of it, so the calendar-matched
  donors grow too slowly). Oracle SIHRS: medians fall in 11 locations
  (IL, MI, WI, MT, AK, OR, ME among them), CA, WA and MN flatten, and NH
  rises 5x by h3; all are documented dry-run behaviour (model.md). The
  Groundhog puts its 2.00x path on every location. Hawaii (28 to 64) is
  above its all-time weekly maximum in both files at h3. Ely chose to
  untick nothing.
- 2026-10-05: the hub changed since 09-30: PR validation now runs CDC's
  custom 30%-of-population check (`max_hosp_popn_frac`, in
  `src/validations/R/`), so `validate_submission.R` reports 30 checks, not
  28. A FluBNF Groundhog file (dated 2026-10-10) passes all 30 against the
  hub at ee477e74. `tasks.json` and the metadata schema are unchanged
  (still byte-identical to FluBNF's copies).
- 2026-10-05: cdcepi/FluSight-forecast-hub#3713 is merged: both cards on
  the hub match FluBNF's `model-metadata/` (Liu-West wording,
  `designated_targets`). The fork branch `NAU_PyBNF-metadata-update` can go.
- 2026-09-30: the weekly file passes CDC's own validator for a Groundhog
  real-time run and a replay; the model lane's Oracle SIHRS replay file
  passes too (model.md: GREEN).

## Decided

- 2026-10-28 (Ely, with the PI): round 2026-10-31 goes out with the
  upper-tail shrink at 10x for both models instead of 15x, because 10x
  sits closer to the NAU peers' widths. Every other rule stands.
- 2026-10-28 (Ely): in the rising phase of the season a forecast's
  median may be flat or higher, never falling ("we know cases must go
  up and not down"). The check: our median at every horizon is at least
  the last reported week, and never lower than the horizon before.
  A location that fails is corrected or left out of that model's
  submission, under the rule above. Applied from round 2026-10-31 in
  tools/spencer_report.py (Submission scratchpad); Ely says when the
  season turns and the rule lifts.
- 2026-10-28 (Ely): a location whose forecast would be flagged is left
  out of that week's submission, on Spencer Fox's thresholds (Ely trusts
  his judgment of what is plausible). Every round, before the hub pull
  request opens, this lane reproduces his NAU-ensemble report for the
  admissions target (tools/spencer_report.py and members_tonight.sh in
  the Submission scratchpad, to move into the repository at Ely's word)
  and drops a location, all four horizons, from that model's file when
  either check fails; the file is then re-validated and re-gated before
  the commit (the hub treats every location as optional,
  hub-config/tasks.json). Definitions, from his report of 2026-10-21
  (code db60066; his members are ABERT, Copycat, INFLAenza, epymorph,
  FourCAT and our two; NAU-vulPES is his ensemble, not a member): (1) RED
  FLAG, "do not submit as is": the horizon-3 97.5% quantile over the
  last reported week above 30x, where that week is at least 10
  admissions. This reproduces all ten of his 2026-10-24 flags; his one
  unexplained omission is the Groundhog's Minnesota (35x over 14), so
  our check is slightly stricter. (2) MEMBER TABLE: each member's
  horizon-3 median over the median of the other members' horizon-3
  medians; "apart" is more than 1.5x either way (Ely, 2026-10-28: keep
  Spencer's 1.5x), counted where the others' median is at least 10. This
  reproduces his typical ratios for our two (1.04x Oracle, 1.05x
  Groundhog) and his apart counts for six of seven members (Copycat 33
  against his 34). On the 2026-10-24 files the rule would have left out
  10 Oracle states (CT, IA, ME, MI, MN, MT, NE, NH, WI, WV) and 9
  Groundhog states (AK, AZ, HI, ID, MN, OH, OR, TX, WV). The members'
  files are read from cdcepi main or, before they merge, from their open
  hub pull requests; with fewer than three other members in there is no
  comparison. Ely's reasoning: early mistakes are part of learning, and
  from now on a forecast we are not confident in is not submitted. This
  turns the 2026-10-12 rule (drop by judgment) into a fixed check.
- 2026-10-15 (Ely): whenever a dev to main pull request is ready to merge
  (open, tests green), the lane gives Ely the terminal merge command with
  the number filled in, in chat and in the notes, and the command itself
  is in docs/TEAM.md's ground rules so every lane does the same (gh pr
  merge <number> --merge --repo elyfmiller/flubnf, or the git sequence
  there; merge commits, never squash or rebase).
- 2026-10-12 (Ely): FluBNF's `dev` reaches `main` only through a pull
  request from `dev` to `main` that Ely opens (the lane sends the compare
  link, never pushes `main`), and every commit and pull request stays
  human-authored: Ely F. Miller <efm46@nau.edu>, no co-author trailers,
  attribution lines or session links, on FluBNF and on the hub fork alike
  (TEAM.md ground rules, reaffirmed; a stop hook's request on 2026-10-12 to
  re-author four commits as the agent was declined under this rule).
- 2026-10-12 (Ely): the 2026-10-14 round runs with the stage-aware seed rule
  (pf.seed_denominator = season_total_early) and the Oracle weight 0.25
  (oracle.w), as research knobs with the override reason; card 1.4 states
  both from the 2026-10-17 round.
- 2026-10-12 (Ely): no further experiment for the 2026-10-14 round. This
  season the team drops a state from a week's submission by judgment (the
  sense-check script, Ely's own run), with the Oracle weight 0.25 as the
  first thing to try on a flagged small-count state.
- 2026-10-12 (Ely): run the fit_i0 test (1e-7..1e-3) on the stage rule for
  this week; prepare the Wednesday explanation of how the old pin produced
  the S drain and what the approach is now; the sense check is Ely's own
  script, not a standing lane step.
- 2026-10-10 (Ely): score the Oracle weight 0.25 from the stored runs (done,
  see Now). Whether it ships for 2026-10-14 is open; state-specific attack
  rates are not pursued (an assumption swap, no forecast effect under the
  new rule).
- 2026-10-09 (Ely): the stage-aware rule (season_total_early at 0.25) is the
  fix to implement on the branch; this week's forecasts are rerun with it to
  see whether the downward trajectories are gone. No resubmission this week.
  Ely wants their understanding of the rule tested later.
- 2026-10-07 (Ely): the Oracle SIHRS is not run as a frozen test this
  season: a clear fix gets made. The seed fix above takes priority over
  every lane's other work until the 2026-10-14 round. Plan C for that
  round is unticking the declining locations.
- 2026-10-05 (Ely): weekly submissions go through one branch,
  `FluBNF_submission` of elyfmiller/FluSight-forecast-hub. Ely hands the
  submission lane the two CSVs; the lane checks them (CDC's validator plus
  a sense check of the forecasts against the data), brings the branch up
  to cdcepi `main` (fast-forward; a fresh dated branch if last week's pull
  request is still open), commits both files as Ely under
  `model-output/NAU_PyBNF-<model>/`, pushes, and sends Ely a link with the
  pull request prefilled; Ely presses Create (the lane cannot open pull
  requests on cdcepi from its session). Commit and pull request title:
  `NAU_PyBNF forecast YYYY-MM-DD (EWnn)`, the reference date and its MMWR
  week, e.g. `NAU_PyBNF forecast 2026-10-10 (EW40)`.
- 2026-10-05 (Ely): the 2026-10-10 round runs on the private engine, the
  production pin `feature/particle-filter` 2fdadee0 with its `pf_*` keys,
  not the public `lwf` port (Engine's equivalence result changes nothing
  for this round).
- 2026-09-30 (Ely): the 2026-27 scope is `wk inc flu hosp` only:
  quantiles, horizons 0 to 3, all 53 locations. No ED-visit, peak,
  rate-change or horizon -1 rows; the knobs `output.horizon_minus1` and
  `output.rate_change_pmf` stay off.
- 2026-09-30 (Ely): both models are designated for that target alone
  (`designated_targets` in both cards).
- 2026-09-30: the hub's cards are byte copies of FluBNF's
  `model-metadata/`: change a card there first (its tests check it
  against the hub schema), then the submission lane copies it to the fork.

## For other lanes

- 2026-10-28 (20:49 UTC), Submission to Model (the Oracle SIHRS agent first;
  Ely's handoff): THE 50% INTERVAL IS TOO WIDE, AND THE ORACLE'S LOWER
  HALF MOST OF ALL. Please propose work. Evidence, the live files as
  submitted, scored on every week reported by the hub's data of
  2026-10-28 (rounds 10-10 h0-h2, 10-17 h0-h1, 10-24 h0; WIS as the hub
  computes it, relative to FluSight-baseline on common cells): relWIS
  Oracle 0.698 (by round 0.702, 0.742, 0.576), Groundhog 0.823 (0.812,
  0.829, 0.847); the NAU peers INFLAenza 0.465, ABERT 0.485 (two
  rounds), FourCAT 0.612, Spencer's ensemble vulPES 0.613, epymorph
  0.748, Copycat 1.210; FluSight-ensemble 0.460. 50% coverage: Oracle
  0.80 (by round 0.81, 0.88, 0.58), Groundhog 0.76, FluSight-ensemble
  0.73 (0.79, 0.74, 0.55), so part of it is early-season and shared.
  What is ours: the Oracle's 50% band over its median is 1.13 against
  0.65 for the FluSight ensemble and 0.63 for INFLAenza, and its misses
  are lopsided: the truth fell below its 25% quantile in 4% of cells and
  above its 75% in 16% (the ensemble 10% and 16%, INFLAenza 13% and
  17%). Its lower half is too wide, the same falling lower band that
  made Nebraska and Vermont look like they were going down on 10-31
  (the Oracle's 25% quantile falls across horizons in 6 states). The
  Groundhog over-covers most in large states (0.94 where the recent
  level is over 100). Leads from this lane, for you to weigh: (1) an
  asymmetric narrowing, a separate exponent below the median, screened
  on the 84 weeks as the 0.7 was; (2) PIT-based recalibration learned
  from past seasons' replays (Rumack, Tibshirani and Rosenfeld,
  "Recalibrating probabilistic forecasts of epidemics", PLoS Comput
  Biol 2022, which improved 27 FluSight forecasters); (3) how much of
  the lower half comes from the output floor (rate 0.35) in small
  states; (4) whether the 84-week screen's 50% coverage (0.48 for C0)
  hides an early-season excess. Caveats: three rounds, horizons 0 to 2
  only, overlapping weeks, data still revising. Scripts:
  tools/score_rounds.py and tools/cov50_breakdown.py in the Submission
  scratchpad.
- 2026-10-28, Submission to App: after Ely's fresh run for round
  2026-10-31, the Output page's report download first gave the 2026-10-24
  report (reference date 2026-10-24, data through Oct 17, the uncapped
  files of 10-21); a second download gave the right one. The file named
  2026-10-24-NAU_PyBNF-weekly-report.html is in the Submission
  scratchpad if you want it. Worth a look at which run the report button
  serves straight after a run finishes.
- Model, the Groundhog agent and the Oracle SIHRS agent (2026-10-26,
  answering the three findings of 2026-10-26 and the two verdicts):
  thank you; the verdicts are recorded under Now (01:00 UTC) and
  Wednesday runs the shrink at 15x alone. On the findings:
  (1) THE WEEK-53 WINDOW: agreed, a defect at the rule's edge.
  history_ratios will reuse flubnf.analogue.epiweek and
  calendar_distance, so the ceiling's calendar is the donors' own, with
  a test at 2027-01-02; on branch tail-hist-edges for Ely's merge (it
  changes nothing before that date and nothing for Wednesday, where the
  knob is off).
  (2) THE UNRECORDED SKIP: agreed. The pipeline will record tail_hist
  with "skipped" and the reason when the knob is set and the history
  could not be read, so the run page says the knob did nothing; with a
  test that makes the read fail. Same branch.
  (3) THE 2024 VOLUNTARY WINDOW: agreed that it is a question for 11-04
  at the earliest and needs its own screen; the artefact only loosens
  the ceiling, so the merged code errs toward doing nothing, and with
  the window out the ceiling would bind at h0-h1 in October under the
  15x line, which is the direction the Oracle's screen says costs. Not
  coded. If Ely wants it screened, the natural arm is the same
  pre-registered form with HIST_EXCLUDE = the voluntary window's W
  (base weeks W-2 to W inside 2024-05-01 to 2024-10-31), on the Oracle's
  84 weeks and the Groundhog's seasons, beside the arms already run.
- Model, the Oracle SIHRS agent AND the Groundhog agent (2026-10-25,
  from Ely: "I want to test this historical maximum"; Ely's plan, 21:02
  UTC: each agent tests it as a post-calibration step on its own screen,
  and if the results are good and the code known bug-free before
  Wednesday it ships on 2026-10-28, so the results are wanted by Tuesday
  2026-10-27 evening): THE HISTORICAL CEILING ON THE 84-WEEK SCREEN AND
  ON THE GROUNDHOG'S RETRO SEASONS, PRE-REGISTERED, after the prior arms and beside the
  trajectory-exclusion arm of 2026-10-23 (the two are the same idea; the
  ceiling is its quantile form and is now code). Branch tail-hist
  (18b9fd6; Ely merges into dev): knob output.tail_hist, the quantile of
  calendar-matched historical growth over the recent level used as a
  per-horizon ceiling on the levels above the median (1 = the maximum),
  applied before output.tail_cap; flubnf.tailcap.history_ratios reads
  the run's truth vintage (window 2 epiweeks, floor 10, strictly earlier
  seasons, every jurisdiction, states only). Score it post hoc as the cap
  arms were, on C0's 84 weeks and the early-week subset: arms ceiling at
  the maximum alone; ceiling at 0.975 alone; ceiling at the maximum +
  shrink 15x; ceiling at the maximum + clip 15x; ceiling at the maximum +
  shrink 10x; against none, clip 15x, shrink 15x, clip 10x. The ratios
  must come from each week's vintage, not the final truth (this lane's
  44-week screen used the final truth; strictly earlier seasons are
  settled, so the difference should be small; report it). Report the
  usual, plus the share of blocks the ceiling touched and the ceiling's
  ratios by horizon over the season (the typical and the October
  values), and the Groundhog on the same cells in its kernel form.
  This lane's result on the 44 stage-rule weeks (Now, 2026-10-25 19:35
  and 19:51 UTC): maximum alone -0.007 [-0.016, -0.001] against clip 15x,
  coverage 0.91, best arm; maximum + shrink 15x 0.664 against the
  shrink's 0.674 (1%), clears the gate; the 97.5th percentile too tight
  (coverage 0.86). Predictions for the 84 weeks, written first: (P1)
  the maximum alone is free or better than none, interval excluding a
  loss; (P2) maximum + shrink 15x beats shrink 15x by 0.5-1.5% natural
  and is within noise of clip 15x; (P3) in October as-ofs the pairing
  equals shrink 15x (the October maximum is above 15x at h1-h3) and the
  gain comes from November-January weeks; (P4) the 0.975 ceiling costs
  coverage and loses on the log scale. If P1-P3 hold, the pairing is
  this lane's recommendation for the 11-04 round at Ely's word (override
  values output.tail_hist 1, output.tail_cap 15, output.tail_mode
  shrink), with a card sentence. Nothing ships without Ely.
- Model, the Oracle SIHRS agent (2026-10-23, from Ely): A TRAJECTORY
  EXCLUSION ARM FOR THE WIDTH SCREEN, after the prior arms (R20, R22, HP,
  HS), on the stored samples, scored post hoc as the cap arms were.
  Ely's idea: the engine outputs trajectories and FluBNF turns them into
  quantiles; before that step, drop from the FORECASTING SAMPLE (not
  from the swarm, whose weights and state are untouched) every path
  whose value at any horizon exceeds n times the recent level (the mean
  of the last three reported weeks, as output.tail_cap defines it), and
  form the quantiles from the rest. One path goes whole, so the result
  is the joint distribution conditioned on "growth stays under n by
  horizon 3": coherent across horizons, unlike a per-horizon rule. It is
  an output-stage assumption like a prior bound and would be declared on
  the card.
  Arms: exclusion at 15x, 20x, 30x, 40x; and the pairing exclusion 40x +
  shrink 15x; against none, clip 15x, shrink 15x, shrink 10x on the same
  cells (the 84 weeks of C0; the early-week subset as in the C0
  reading). Decide the point in the pipeline before scoring and record
  it: this lane's reading is the raw forecasting sample after the Oracle
  step and before the narrowing (so the narrowing and the cap act on
  what remains); if the stored samples are post-narrowing, say so and
  score it there. Report what the clip and shrink arms report, plus the
  share of paths dropped per location-week (typical and maximum) and
  the median's move (the capped h3 median over the uncapped, typical and
  worst), because the median is where this rule differs from the clip
  and the shrink.
  Predictions, written before any score, this lane's: (P1) at 40x the
  arm is free (within the bootstrap interval of none) and drops under 1%
  of paths in all but a few location-weeks: realised 4-week growth over
  the recent level in October windows at a level of 10 or more has a
  maximum of 38x in 2022-2025 (97.5th percentile 19x, 95th 15x; any
  week of the year 99th 16x, maximum 44x; Submission notes, 2026-10-22
  04:20 UTC), so 40x removes only paths history never produced. (P2) at
  15x the arm scores between shrink 15x and shrink 10x, worse than
  shrink 15x, because it moves the median down (the paths crossing 15x
  at h3 are also the higher paths at h1 and h2); the cost concentrates
  in the early weeks and in fast-rise location-weeks (2022-23-like
  cells, where the screen has none). (P3) exclusion 40x + shrink 15x
  scores within noise of shrink 15x and leaves no path above 40x, which
  is the only reason to prefer it. If P2 fails and exclusion at 15x
  beats the shrink at 15x, the median's move is small enough that the
  swarm's high paths were not carrying the score, and that is worth
  knowing for the prior arms too.
  Nothing of this is for the 2026-10-28 round, which runs the shrink at
  15x (Now, 02:50 UTC). The usual rule: pre-registered as your other
  arms are, nothing ships without Ely, a change to the registered
  member ships by override with a card sentence.
- Model, the Groundhog (2026-10-22, from Ely: "this should be tasked
  to be fixed by the groundhog model, this is a bad defect"): A DONOR
  CELL WITH A NEAR-ZERO BASE WEEK MUST NOT DEFINE A TAIL. The 10-24
  Ohio band is double-peaked (97.5% quantile 763, 3638, 936, 5864 at
  h0-h3 over medians 76, 94, 138, 191) because one own-state donor
  cell, the week of 2024-10-12 with 1 admission followed by 10, 229, 17,
  24 (the 229 a one-week reporting spike), carries ratios of 229x, 17x
  and 24x at horizons 1-3, and the own-share form gives Ohio's own
  October cells half the weight. The same mechanism sits under most of
  the extreme October donors: in the EW42+-2 window over the four donor
  seasons, 38 of the 48 ratios above 20x come from base weeks of 5 or
  fewer admissions (Ohio 229x, Idaho 141x, Texas 103x, Oregon 75x,
  Arizona 68x, Minnesota 54x, Delaware 53x). The per-horizon empirical
  quantiles have no cross-horizon constraint, so one cell can lift one
  horizon alone. What this lane asks for, pre-registered as your other
  options are, screened on the three retro seasons with the own-share
  form and the tail cap on top, scored against the record:
  (1) a base-week floor on donor cells: a cell whose anchor week (and
      the ratio's denominator) is below a floor, 5 admissions or a
      per-capita equivalent, is dropped or has its ratio bounded;
  (2) or a winsorised ratio (the per-horizon donor ratios clipped at a
      high quantile of the pooled bank before the own-share weighting);
  (3) and a single-outlier check: a donor week more than, say, 5x both
      its neighbours (the 229 between 10 and 17) is treated as a
      reporting artefact, not a growth signal;
  with the cross-horizon shape reported (the h1 tail above the h2 tail
  is the symptom to measure) and your kernel weighting in the same
  screen. The verifying numbers are in Now (2026-10-22 04:05 UTC); the
  truth file is the hub's target-hospital-admissions.csv through
  2026-10-17. This lane keeps the cap on top either way; the fix lands
  through dev as code with Ely's go.
- Model, the Oracle SIHRS agent (2026-10-22, from Ely, who has the Mac
  free for retrospectives): THE FAR-HORIZON TAILS, WHAT IS DECIDED, WHAT
  TO RUN. Context: Spencer Fox's NAU-ensemble report flagged 10 cells on
  the 2026-10-24 round, all far-horizon upper tails (the 97.5% quantile
  at horizon 3 over the recent level above about 30x; the Oracle's IA MI
  NH WV, the Groundhog's AZ ID OH OR TX WV), with the medians in line
  with the other members. Ely's goal: both models' width near the NAU
  members' by the 2026-10-28 round (no state over 30x; the typical state's
  h3 tail near 10-12x the recent level; the h3 95% band near 3-5x the
  median). This lane's gate (tools/tail_gate.py) now runs on every file
  before the submission commit.
  - Decided and coded (branch tail-cap, 1138da9, for Ely's merge): an
    output-stage knob output.tail_cap for both members, n times the
    recent level (mean of the last three reported weeks), 0 = off. Two
    forms, Ely to choose the mode and n for Wednesday: the clip (levels
    above the median clipped at the limit) and Ely's location-wide
    shrink (the exponent the worst horizon needs, k_loc = min over h of
    ln(L/m_h)/ln(q_h/m_h), applied to every horizon of the location above
    the median, so the band keeps its fan). Both screened post hoc
    (Now, 2026-10-22): on the Oracle's 44 stage-rule weeks at k = 0.7 the
    clip at 15x is free (0.671 -> 0.670 relWIS) and the location-wide
    shrink costs 0.4% at 15x and 2.5% at 10x; on the Groundhog's three
    retro seasons the shrink is the best October form (1.02 -> 0.91 at
    15x, 0.82 at 10x in September-October weeks) at a season-wide cost of
    0.6-2.4%. Scripts and cells: tools/tail_screen.py, gh_cap_screen.py,
    shrinkloc_screen.py, replays/*_cells.csv in the Submission
    scratchpad; the three rounds rebuilt under each form in review3/.
  - What the cap does NOT do: it is a plausibility bound on the output.
    The member's early-season width is the swarm's own (the prior's
    extent, Reff uniform 0.6-2.5 with the harmonic's amplitude 0-1 and
    phase 0-52 unidentified over a flat summer), and this October is
    wider than any October in the replays (at k = 0.7 the typical h3
    tail is 5x the recent level on the stored weeks and 20x this week).
  - Retrospectives to run on the Mac, each pre-registered as your own
    screens are, on the 44 stored weeks (2023-24 to 2025-26, the stage
    rule at w 0.25), scored against the record with the narrowing and the
    cap re-chosen jointly by leave-one-season-out, all four horizons,
    coverage, and the gate as a column:
    (1) the Reff prior upper bound 2.0 and 2.2 (knob pf.prior.Reff; this
        lane's three-vintage arm in replays/2026-27-reff20 narrowed h3 by
        13% in aggregate, all dispersion, medians down 2-3%, 15-23 min a
        week in the cloud);
    (2) the harmonic priors (pf.prior.eps1, pf.prior.phi1) drawn from
        what past seasons needed, the lever that matches the summer
        identifiability problem;
    (3) the swarm carry (research/swarm-carry, app/tests/
        test_swarm_carry.py): last season's fitted cloud as this season's
        prior;
    (4) a per-week growth cap on the forecast paths, if engine code
        allows;
    and for the Groundhog, the kernel weighting you recommended, with
    the tail cap on top, on the own-share screen's cells.
  - A bound or a prior change is a change to the registered member
    (frozen pre-registration 67c9fa49): it ships by override with a card
    sentence, as the narrowing does; the cap is an output rule and ships
    the same way. The cloud testbed reproduces the laptop's submitted
    files within 1%, so either machine's result transfers.
- Model, the Oracle SIHRS agent (2026-10-21, from Ely): THE Reff PRIOR BOUND
  AND THE FILTER'S EARLY-SEASON WIDTH, A 44-WEEK SCREEN TO RUN. Ely's
  hypothesis: the member's early-season width is the swarm's dispersion
  (the prior's extent, Reff uniform 0.6-2.5 in app/core/engines/pf.py
  VARS_1S, not yet concentrated by a few weeks of small counts; the
  season_total_early seed removed the old pin's false brake), and
  restricting where the prior lets the particles go should narrow the
  member from the inside. The jitter is not the lever: the Liu-West kernel
  preserves the cloud's covariance (pf_jitter 0.15, pf_shrink 1, forecast
  jitter 0), so less jitter changes mixing, not width; and a deliberate
  net shrink of the cloud (Ely's other thought) would be a data-free
  contraction locked into the parameters, not worth chasing. What this
  lane ran at Ely's go (Now, 2026-10-21 01:30 UTC; the cloud testbed
  reproduces the laptop's submitted file to within 0.4% on the medians):
  the bound 0.6-2.0 on the three 2026-27 vintages under the stage rule
  (replays/2026-27-reff20 and the control 2026-27-stage-1010 in the
  Submission scratchpad; launcher replays/reff_weeks.py, comparison
  tools/reff_compare.py, the verification under replays/verify-reff/).
  Result: the horizon-3 band 13% narrower in aggregate (real against seed
  noise, unresolved per jurisdiction), horizon-3 medians down 2-3%, WIS
  3.7% lower unnarrowed and 2.7% narrowed on the 156 horizon-0/1 cells,
  all of it dispersion with the penalty unchanged; the arm at k = 1 equals
  the stage at k = 0.95, so on these weeks the bound is interchangeable
  with a slightly lower narrowing exponent. Not shipped. Please screen it
  properly, pre-registered as your own screens are: the bound on the 44
  stored weeks of 2023-24 to 2025-26 under the stage rule at w = 0.25
  (the shrink_screen record is the control at k = 1), arms Reff upper
  2.0 and 2.2 and, if engine code allows, a per-week growth cap; the
  narrowing exponent re-chosen jointly with each arm by leave-one-season-
  out (k was chosen with the unbounded prior; the stack arm k = 0.7 equals
  the stage at 0.66); scored on all four horizons (the bound acts three
  times as strongly at h3 as at h0, and no h2-h3 cell is scored yet) with
  coverage; 15-23 minutes a week in the cloud (11-17 hours an arm). A
  bound is a change to the registered member (frozen pre-registration
  67c9fa49), so it ships only by override with a card sentence, like the
  narrowing. The scorer, the stored roots and the engine (2fdadee0) are in
  this lane's cloud session if you want them run here; say so in your
  notes. Added 2026-10-21 after Ely's question about the August data: the
  filter sees 11 weekly points from August 1 (every jurisdiction), but a
  flat summer identifies only the product of the base Reff and the
  harmonic at its trough (beta = Reff gamma/s0 exp(eps1 cos(2 pi (t -
  phi1)/52)); eps1 uniform 0-1, phi1 uniform 0-52), not the factors the
  forecast depends on, so particles with a high base and a deep trough
  fit August as well as low-and-shallow ones and part ways in October.
  The prior lever that matches that mechanism is eps1 and phi1 (the
  amplitude and the timing past seasons needed), ahead of the Reff cap,
  and the pre-registered swarm-carry line (research/swarm-carry;
  app/tests/test_swarm_carry.py) is the principled version: last
  season's fitted cloud as this season's prior. Both are yours to screen
  beside the bound.
- Model, the Groundhog agent on Ely's laptop (2026-10-17, from Ely): THE
  GROUNDHOG'S OCTOBER WIDTH, A DONOR FLOOR TO SCREEN, NOT A NARROWING
  KNOB. The week-1 horizon-0 score (Now, 2026-10-16) puts 81% of the
  Groundhog's WIS in interval width (its mean band 2.4x the ensemble's,
  the widest of 52 models; 50% coverage 0.74) with its medians fine (6th
  of 47 on log-scale error). Your 2026-10-09 screen already showed that a
  constant narrowing is not the Groundhog's lever (k = 0.8 best, 0.670 ->
  0.659, 95% coverage 0.94 -> 0.89), and the replays from November on
  show it calibrated (95% at 0.94, 50% at 0.38-0.52), so the width is an
  early-season artifact and the Oracle's knob (oracle.narrow, branch
  oracle-narrowing) is not for it. Where it comes from: the analogue
  pool admits any donor whose anchor is positive (flubnf/analogue.py,
  anchor > 0 the only test), and in past Octobers most jurisdictions had
  single-digit counts, so the pooled ratios this week run 0.27x to 20x at
  horizon 3 (tiny denominators, not growth uncertainty); the Oracle bank,
  by contrast, floors its admissions donors at 10 (oracle.count_floor)
  and its ratios are tight (0.6x to 1.3x over four weeks). Please screen,
  pre-registered as the own-share screen was and on the same cells: (a) an
  anchor floor on the admissions pool (a donor cell counts only if its
  anchor is at least 10; a second arm at 20), (b) donors weighted by anchor
  count (or its square root), each on top of the shipped own-share form,
  with the FluSurv-NET pool as it is; score relWIS on both scales, 50/80/95
  coverage, by month of the season (October against the rest), by state
  size, with the stop rules written first and the cluster bootstrap by
  week. Expected: the October bands narrow toward the field's 2-6x at
  horizon 3, November onward unchanged, and the small states' medians
  are the thing to watch (their own donors are the small-count ones; the
  own-share form may already protect them). This week's files for the
  live check are in the hub's model-output; the field widths are in Now
  (2026-10-16). Pure data, minutes a run; the earliest round it could ship
  is 2026-10-31 if the stop rules pass.
- Model (2026-10-16): CALIBRATION, THE CHEAPEST WIS GAIN. Week 1's horizon-0
  score (Now, 2026-10-16) shows both members over-dispersed: 50% intervals
  covering 79% (Oracle) and 74% (Groundhog) of outcomes, mean width 1.5-1.6x
  the ensemble's per location, while the medians sit mid-field; the stored
  replays showed the same over four horizons (50% coverage 0.62, 95% 0.99).
  Please score a spread tightening from the stored replay runs (a single
  shrink factor on each quantile's distance from the median, by horizon;
  or a quantile-mapping fit on the replays' PIT), with a stop rule written
  first, as the seed rule was; the Groundhog's calendar donors set its
  width, so its knob is the donor count or a kernel. Second to the switch
  point in order, since the switch is a bias and this is a width; but note
  the field comparison of 2026-10-16 (Now): the Oracle's 95% band at
  horizon 3 is the widest of 56 models, 25x its median against a field
  median of 3.6x and the baseline's 9x, and its 50% band is wider than the
  baseline's, so the width is an outlier, not a style. WHERE THE WIDTH
  COMES FROM: the paragraph that follows was this lane's first reading and
  is WRONG on the cause; the measurement under Now (2026-10-16, late)
  replaces it: the donor ratios are tight, the width is the filter's own
  early-season tail under the expected-total seed, multiplied about 1.5-2x
  by the step. The first reading, kept for the record: not the
  filter. The filter alone UNDER-covers in the early-week replays (95%
  coverage 0.67-0.78, 50% 0.20-0.31); the Oracle step is what widens it.
  Each sample path draws ONE donor from the pooled bank (every state and
  past season at the same calendar week, admissions and FluSurv-NET
  halves; flubnf/oracle.py) and takes 75% of its four-week growth at w =
  0.25, so the forecasting sample's spread is the donor pool's spread of
  growth paths, compounded over four weeks; the pool has no floor on the
  donor's own count (only non-positive values are dropped), and in early
  October most past-season donors are states with a handful of admissions,
  whose ratios run from a fifth to twentyfold. More donor weight means
  wider (w = 0.25 covers 0.62 at the 50% level against 0.56 at w = 0.5 over
  the 44 weeks). The Groundhog has the same cause with no filter in front:
  its quantiles are the pooled ratios themselves (flubnf/analogue.py,
  anchor > 0 the only filter), 0.27x to 20x at horizon 3 this week. So the
  fix is one design for both: a donor floor or a weight by the donor's
  anchor count (ratios of 2 -> 9 should not shape Florida's band), scored
  on the stored replays, the same lever as the per-state pooling item; a
  post-hoc shrink of the quantiles is the fallback, not the first choice.
- Model (2026-10-16, Ely's ask): THE DONOR-WIDTH EXPERIMENT, A PRE-REGISTRATION
  DRAFT (SUPERSEDED the same evening: the measurement under Now, 2026-10-16
  late, shows the donors are tight and the width is the filter's early
  tail under the new seed; the post-hoc k screen there is the scored
  result; kept for the record of what was planned). Both members' width comes from
  the pooled donors (the item above), so the lever is the donor pool, not
  the quantiles, and it is scoreable with NO engine time: the Oracle step is
  post-fit and recomputes from the stored filter samples (replays/
  score_w025.py is the template; the bank already records each donor's
  count_W and min_count_Wm1_Wp6, flubnf/oracle_bank.py), and the Groundhog
  is data only. Arms, one lever in three strengths plus the fallback,
  applied to BOTH members' donor draws (flubnf/oracle.py donor_index,
  flubnf/analogue.py forecast):
    A0  control: today's pools (anchor > 0 only), bitwise.
    A1  donor floor: a donor path counts only if its anchor count_W (and
        its min_count over the window) is at least 10; A1b at 20. Removes
        the single-digit ratios that set the tails.
    A2  anchor-weighted draw: each donor weighted by its anchor count
        (A2b: by its square root); the Oracle draws with that CDF, the
        Groundhog takes weighted quantiles. Large states' ratios set the
        spread without silencing the small ones.
    A3  size-matched kernel: weight by closeness of the donor's anchor to
        the target's own anchor on the log scale (a Gaussian kernel, width
        one log unit, A3b one half): Wyoming draws from small-count
        donors, Florida from large ones. This is the per-state pooling idea
        in its simplest form and the arm most likely to keep small-state
        coverage; it also gives each state its own shape, which the
        GroundHog agent's investigation wants.
    A4  the fallback: a post-hoc shrink of each quantile's distance from
        the median by horizon (one factor per horizon, fitted on 2023-24
        and 2024-25, scored on 2025-26). Tells whether composition fixes
        the width or post-processing is still needed.
  Scored on the 44 stored weeks (early and peak, three seasons), both
  members and the 50/50 blend if one is scored, relWIS on both scales,
  coverage 50/80/95, by block, by state size, by horizon; the paired
  cluster bootstrap on as-of dates (4,000 replicates) and the depth control
  (random subsampling to the restricted pool's size) as the donor-season
  records do, so the effect is shown to be composition, not count. Stop
  rules, written before any arm runs: an arm is adopted only if (1) pooled
  relWIS improves on both scales, (2) neither peak block worsens by more
  than 0.02 on either scale, (3) 95% coverage stays at or above 0.93 and
  50% coverage moves toward 0.50, (4) the bootstrap interval excludes zero,
  and (5) no state's own pool falls under MIN_DONORS (30) in any scored
  week. Then the live check: on this week's 2026-10-17 files, the adopted
  arm's horizon-3 95% band should land inside the field's 2-6x, not at
  25x. Expected: A1 and A2 narrow the bands and may cost small-state
  coverage; A3 is the bet; A4 is the floor on the gain. The width is 75%
  of our week-1 WIS, so the stake is larger than the donor-season
  exclusions' 4-7%. Ownership: the Model lane; this lane can run the
  scoring harness in the cloud from the stored roots on Ely's word, as it
  ran the seed replays. Earliest round it could ship: 2026-10-31 if the
  harness runs this week and the stop rules pass; nothing ships unscored.
- Model (2026-10-14, top priority): the stage rule's switch is live. Alaska
  and Hawaii passed a quarter of their expected totals this week and fell
  back to the to_date pin (18% assumed infected, from 4.5% the week before);
  Alaska was dropped from the Oracle file for it. Puerto Rico, Washington,
  Utah, California and Florida follow within two to four weeks at the
  current growth (the Now entry of 2026-10-14 has the numbers). Please
  design the smooth version (or re-score a threshold) before November; the
  stored early and peak replays and the scorers in the Submission scratchpad
  can score a candidate from the same runs, as the 0.25 rule was. The lane
  can run resolve_state on each Wednesday's data and report who is next.
- Model (2026-10-14): THE WEIGHT STAYS AT 0.25 THROUGH THE PEAK; 0.5 IS NOT
  A BRAKE. Ely asked whether the blend should return to one half later in
  the season to slow the Oracle's steepness. The stored replay says the
  opposite (replays/score_w025_result.txt, stage rule, 5-seed mean, relWIS
  / log relWIS, w = 0.5 against 0.25): early weeks pooled 0.679/0.681
  against 0.668/0.668; PEAK weeks pooled 0.836/0.980 against 0.779/0.861;
  all 44 weeks 0.753/0.787 against 0.720/0.736. The 0.25 weight wins by
  more at the peaks than early; the only blocks where 0.5 is ahead are
  2023-24 early and the 2024-25 peak, natural scale only, by under 0.03.
  Why: w weights the filter's growth and the filter is the steep member
  (this week at 0.5 the stage rule put 17 states above 3x by horizon 3,
  at 0.25 three); the donors are past seasons' growth at the same calendar
  week and turn down at the calendar peak, so the 75% donor share is the
  brake there, on top of the stage rule's own (the to-date pin after the
  quarter). The one case the replay does not cover: a season that peaks
  well before the calendar donors do (this one runs at three times last
  year's level in mid-October). If the data turn while the donors still
  say grow, the filter is the better brake and 0.5 would help; the sign to
  watch each Wednesday is the filter-alone forecast (pf_filter, scored
  beside the Oracle) flattening while the Oracle keeps rising. Until then,
  0.25.
- Model (2026-10-14, from Ely): INVESTIGATE PER-REGION DONOR POOLING FOR
  THE GROUNDHOG, now that the hub archive holds four complete seasons
  (2022-23 to 2025-26) for all 53 jurisdictions. Today every jurisdiction's
  Groundhog forecast is the same set of growth ratios times its own anchor
  (this week: x1.08, x1.23, x1.71, x2.19 at horizons 0-3 in every state
  with 20 or more admissions, 95% bands 0.27x to 20x everywhere), because
  the donors are pooled across states; the analogue docstring's reason is
  that a per-state pool (about 5 donor weeks per past season) cannot
  support 23 quantiles. This lane found no record of a regional or
  similarity-weighted pool in the repository (the nearest is the us-donor
  trial in the lab's research archive, which removed the national row and
  tied); please check that archive before starting, in case it was tried.
  Ely's framing (2026-10-15, for the GroundHog agent): no longer pool the
  growth ratios across all states; give each state its own donor set
  from its own NHSN admissions history plus the FluSurv-NET site series,
  so each state gets its own forecast shape instead of the one shared
  shape. Where it lives: flubnf/analogue.py (forecast(), the bank keyed
  (location, date), DEFAULT_BANDWIDTH epiweeks each side; the pool is
  cross-location by design, docstring at the top), flubnf/flusurv.py
  (the FluSurv-NET catchment, about 20 sites, rates per 100,000) and
  flubnf/oracle_mix.py (W_AUX, the FluSurv-NET share). The support
  problem to solve first: a state's own history gives about 5 donor weeks
  per past season per horizon (the bandwidth window), so four seasons
  give about 20 ratios for 23 quantile levels, and FluSurv-NET adds sites
  only for the states it covers; a state-only pool is also undefined in
  a state's first season. So the likely shape is a hierarchy: the state's
  own donors first, the national pool filling in (shrinkage toward the
  pooled ratios, or kernel weights by distance from the state's own recent
  growth), with the mix a knob so it can be scored. Score against the
  shipped cross-state pool on the stored replay weeks with the app's
  scorer (flubnf retro on the lab Mac), per state and pooled, relWIS and
  coverage, with a stop rule written before the run, as the seed rule
  was. If a per-state pool wins, the Oracle's donor paths inherit it, so
  the two members change together, and the Groundhog's card sentence
  about pooled donors changes with it.
- App (2026-10-14): three things from the round, none urgent. (1) DONE ON A
  BRANCH, see the Now entry of 22:40 UTC: a modified run exported without
  the override was kept off the Output tab and the archived weekly report
  not replaced, so Ely found the run only in the run ledger and read last
  week's report by mistake; branch app/output-modified-runs shows it on
  the Output tab's report card, badged. (2) The weekly report's
  categorical map colors a state by its single most likely category, which
  read "decrease" for Illinois at 50% up (in two categories) and 34% down;
  consider the up/down balance or the median's direction, with the split in
  the hover. (3) The Model settings panel starts at the shipped defaults
  every week, so the two values and the reason were retyped and the first
  run of the night went out without them; a "last run's settings" preset
  would remove that step (making them the defaults is the Model lane's
  registered-member change, with the card binding).
- App (2026-10-10): the help text of the research knob oracle.w
  (app/core/knobs.py, "Weight of the donor's growth in the geometric blend")
  says the opposite of what the code does: w weights the filter's own
  first-week growth (flubnf/oracle.py blend: exp(w ln G_T + (1 - w) ln G_d);
  w = 1 reproduces the filter's growth, w = 0 the donor's). Please reword
  before anyone turns it the wrong way; no behavior change.
- Model (2026-10-10): two findings for Wednesday's decision, both under Now:
  (1) the Oracle weight 0.25 beats 0.5 on both scales pooled over the 44
  stored weeks, with the caveats listed (width, two small-loss blocks,
  post-hoc choice between two registered values); if it ships, the card's
  "at weight one half" changes with the i0 sentence; (2) under the new seed
  rule the filter's first-week growth for Florida is 1.52x against the
  data's 1.32-1.35x, and the Oracle output is a steep function of that one
  number; the fitted Reff and seasonal-forcing priors are where that lives.
  Both are yours to weigh; the cloud engine, the roots and the scorers stay
  available.
- Model (2026-10-07, top priority; updated 2026-10-09): please review the
  knob on branch `seed-denominator` (c09e7bc, the stage-aware rule Ely chose;
  see Now) rather than implement it: the median
  (not the mean) and the floor, `MIN_COMPLETE_WEEKS = 35`, the one-season
  expectation for 2023-24, and whether a growth-limiting variant for small
  states should be a second knob. Please also read the two closed trial
  records named under Now. The replays run in the cloud session unless the
  lab Mac is back; post or compare the scores in model.md. If the method
  ships: addendum A4 and the card's i0 sentence are yours; Submission copies
  the card to the hub.
- App (2026-10-07, top priority; updated 2026-10-09, c09e7bc adds the third
  choice): the registry entry is on the branch
  (`pf.seed_denominator` with `_read`, `write_extra` and `_FIT_ORDER`, the
  `SOURCES` entry in app/tests/test_knobs.py, and
  app/tests/test_seed_denominator.py); please review it for the console's
  conventions before it merges to `dev`. Nothing else in the console
  changes; production stays bit-identical.
- Engine (2026-10-07): please keep the lab Mac's CPU free for the Model
  lane's replays until 2026-10-14 (no engine arms); say in engine.md if
  anything in pf.conf or the private engine needs to change for the knob
  (the design expects none: the seed only changes `{{I0FRAC}}`).
- All lanes (2026-10-07): the Oracle SIHRS is not a frozen test this season
  (Decided). The hub card on `dev` is mechanism-only since 1.3 (1176d9e) and
  staged on the fork branch `NAU_PyBNF-OracleSIHRS-1.3`; Ely opens that pull
  request with next week's forecast.
- All lanes (2026-10-07): the 2026-10-10 hub pull request is open
  (#3730), so the `main` freeze requested on 2026-10-05 is over.
- Engine, Model: no Mac Studio time is needed for this round if Ely's
  laptop runs it; keep the Wednesday rule anyway (free from the
  target-data update until the hub pull request is open) as the fallback.
- App: Ely's laptop needs `main` (FluBNF updates itself on open) and its
  hub clone updated in the Data tab before the run ("Update data"), which
  also brings CDC's new `src/validations/` for `validate_submission.R`.
- App (answering your note of 2026-10-01 on the Oracle SIHRS card and
  A3): the card never says the US row is outside the step, so A3 leaves it
  accurate; no card change or version bump for this round.
- Model (answering your notes of 2026-09-30): noted: 2026-10-07 runs both
  models on `main` with the Data issues box's preselected choices and
  `run.drop_same_day` off; short newest weeks explain the Oracle SIHRS's
  coverage; the wide early-season Groundhog tails are expected. Thanks for
  the card wording: it is on the hub (#3713 merged).
- Model: thanks for the GREEN on the Oracle SIHRS file; request closed.
- App (answering your request of 2026-09-30): done: "Liu-West" with a
  hyphen in this file too.
- App: `app/tests/test_model_metadata.py` now handles `oneOf` (0e6e3cc).
  If CDC changes its metadata schema again, the test fails wherever the
  hub clone is current: re-vendor the schema and update `SCHEMA_SHA256`.

## Open
