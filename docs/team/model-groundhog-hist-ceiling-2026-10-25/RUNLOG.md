# Run log: the historical ceiling on the Groundhog (prereg c9587ab57ab6db4b)

- 2026-10-25 23:40 UTC: prereg.txt written and hashed (sha256 c9587ab57ab6db4b...)
  before any replay or score of this screen. Code: dev fafa1db (merge 463ddba,
  the ceiling) in the scratch worktree wt-hist (this session's scratchpad);
  hub mirror 3a83d410.
- Code check, part one (xcheck.py): the ratios re-implemented in pandas from
  the written rule against flubnf.tailcap.history_ratios on every replay
  week's vintage (97 weeks: 2023-24 32, 2024-25 30, 2025-26 31, 2026-27 4),
  at the maximum and at 0.975: 194 week-levels, 0 mismatches.
- Replays (run_kernel.py, run_all.sh): the shipped kernel form, the record
  naming own_share 0.5, anchor_weight kernel, kernel_sd 1.0, ess_floor 30.
  REPRODUCTION GATE PASSED: 2023-24 0.6802 (6,000 cells), 2024-25 0.6272
  (5,564), 2025-26 0.6448 (5,552), the record to four decimals; 2026-27
  0.8060 (156), the tail-cell screen's C5 value.
- Post-calibration and scores (hist.py --season, then --report ->
  results/report.txt). 17,272 state cells common to every arm (17,116 in the
  three seasons). The code check on the H rows: every block of every week
  equals the rule as written (0 defects in 97 weeks). REPORTING SLIP FIXED
  BEFORE ANY TABLE WAS READ: the first --report run stopped on
  `DataFrame.asof` (a method, not the column); the column is now read by
  name. All six predictions hold; the decision rule returns SUPPORTED for
  the pairing (a to e all pass).
- Checks after the scores, descriptive:
  * 2024-25: the ceiling alone costs +0.0020 but the pairing equals the
    shrink (-0.00002). Not a defect (cap_rows copies its rows; the arms are
    independent): December 2024 +0.0012 alone against -0.0006 under the
    shrink (the pre-clip lets the location-wide exponent be milder), and
    January's +0.0009 is the same in both (PA, MA, OH, MI at the record
    peak, h2-h3: growth beyond what 2022-23 and 2023-24 showed at that
    calendar week).
  * The ceiling changes 27% of state blocks but mostly the top levels:
    38% move only the 0.99, a further 26% from the 0.975 up; where it
    changes, the 97.5% quantile falls by a median 9%.
  * Vintage against final ratios differ in 66 of 97 weeks (2023-24 in
    all 32: its vintages start 2022-02-12, the final 2022-02-05, and the
    final carries Ohio's 2023-05-20 spike, 218, which gives 12.3x at h0 in
    late April 2024 windows against 2.6x in the vintage). Score Hf - H
    -0.0003 [-0.0009, +0.0002].
  * The October 2026 maxima (10-17 vintage): h0 11.7x and h1 19.5x are
    Puerto Rico 2024-11-02 (6, 14, 15 then 137, 228, 160, 368), the return
    of mandatory reporting after the 2024 voluntary window; h2 26.2x and
    h3 37.8x are Oregon 2022-11-05 (6, 5, 32 then 51, 113, 376, 542), real.
  * Minor, not for Wednesday: history_ratios' distance min(dw, 52 - dw)
    puts ISO week 1 at distance 0 from week 53; 2026 has 53 ISO weeks, so
    the 2027-01-02 round's window is weeks 51 to 3 rather than 51 to 2.
- 2026-10-26, for the hand-off to the Submission lane (descriptive):
  * Week 53, shown on a synthetic series through history_ratios: with the
    forecast date 2027-01-02 (ISO 2026 week 53; MMWR week 52), a history
    week in ISO week 3 (2025-01-18) enters the window, which
    flubnf.analogue.calendar_distance puts at distance 3; ISO week 51
    enters at 2 (analogue 1).
  * October 2026 maxima with the 2024 voluntary window left out of the
    base weeks (drop W when any of W-2..W is dated 2024-05-01 to
    2024-10-31), against as coded, h0-h3:
      2026-09-26  3.5 9.7 11.3 19.7  ->  3.2 7.4 11.3 19.7
      2026-10-03  9.7 9.7 15.6 20.3  ->  5.4 8.7 15.6 20.3
      2026-10-10  9.7 9.7 15.6 28.0  ->  5.4 9.2 15.6 28.0
      2026-10-17 11.7 19.5 26.2 37.8 ->  5.4 9.2 26.2 37.8
