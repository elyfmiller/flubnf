AMENDMENT 2 TO PREREG.md (sha256 fd8f57d6): THE TRAJECTORY-EXCLUSION ARM X
(written 2026-10-24, before any exclusion row is computed or scored; the
arm is Ely's idea, handed to this lane by the Submission lane's notes of
2026-10-23, docs/team/submission.md, For other lanes; nothing of it is for
the 2026-10-28 round, which runs the shrink at 15x)

1. THE RULE
For one location-week, L_n = flubnf.tailcap.limit_for(n, recent values):
n times the mean of the last three reported weeks of the as-of vintage,
exactly as output.tail_cap reads it (a NaN limit, no recent level or a
level of 0, leaves the location-week untouched). Every path of the
forecasting sample whose value at any of the four forecast horizons
(h0..h3; the origin block is the data and is not tested) exceeds L_n is
dropped whole; the hub rows are formed from the paths that remain. A path
is one index of the submitted seed's 30,000 stored samples: the Oracle
step multiplies each filter path by one donor's four-horizon factors
(flubnf.oracle.member_for_cell), the narrowing acts per horizon by a
monotone map, and the floor adds per-path noise, so an index is one
trajectory through all four horizons. The swarm, its weights and state,
and the Oracle step are untouched. No replay: the rule runs post hoc on
C0's stored weeks (arms/C0), as the cap arms were scored.

2. THE POINT IN THE PIPELINE (decided here)
XP (primary, the Submission lane's reading): before the narrowing. The
stored samples (after the step, the narrowing at the run's k 0.7 and the
floor) are un-narrowed about each block's median, x = m (x'/m)^(1/0.7)
(score_arm.renarrow with factor 1/0.7, the grid's own k = 1 operation);
the test is applied to those values; the remaining paths are narrowed again
at 0.7 about their own median (flubnf.oracle.narrow, the console's
narrowing), then app.core.submit.quantile_rows. Approximate in the same
sense as the grid's k != 0.7 rows (the floor's noise sits after the
narrowing); check C of the C0 reading bounded that at 0.04% of WIS.
XS (secondary): the same test on the stored samples as they are (after the
narrowing and the floor), exact. Both are reported; the reading uses XP.

3. ARMS AND COMPARATORS (all at k 0.7, on C0's 84 weeks, 17,466 cells)
X15, X20, X30, X40; X40 + shrink 15x (flubnf.tailcap.cap_rows, mode
shrink, n 15, on X40's rows). Comparators recomputed on the same cells:
none, clip 15x, shrink 15x, shrink 10x. The early-week subset is the
September to November as-of weeks (24), as in the C0 reading.
A location-week left with fewer than 300 paths (1%) keeps all its paths
(untouched for that n) and is counted and named.

4. REPORTED
For every arm what table (A) reports for a rule: pooled relWIS on both
scales, coverage 50/80/95, the gate (share of h3 cells over 30x, typical
h3 97.5% over the recent level and over the median), by season, by
horizon, September to November against the rest; the week-cluster
bootstrap (2,000 replicates by as-of week) of each X arm minus none, minus
clip 15x and minus shrink 15x. Then the share of paths dropped per
location-week (median, 90th percentile, maximum; the number of
location-weeks dropping more than 1%, 10%, 50%), and the median's move:
the X row's median over the none row's median per cell, at h3 and at
h0..h2 (median, 10th and 1st percentile, the worst named).

5. CHECKS (the arm is read only if all pass)
A'. The four comparators equal C0.cells.pkl's k 0.7 rows cell for cell
    (WIS and log WIS, max |difference| 0).
B'. The rule with no limit (n infinite, nothing dropped) reproduces the
    none rows: XS exactly; XP through the float round trip (every hub
    value equal, or the differing cells counted with their WIS change).
C'. On every location-week no remaining path exceeds L_n at any horizon
    (XP on the un-narrowed values, XS on the stored ones), and on the
    smoke week the dropped count equals an independent plain-loop count.
The smoke week (2024-12-07) is run for the checks only before the full
run; its scores are not read.

6. PREDICTIONS (this lane's, before any score; the Submission lane's P1 to
P3 are in its notes and are read beside these)
Q1. X40 drops under 0.1% of paths in at least 95% of location-weeks and
    is within 0.001 of none on both scales.
Q2. X15 drops under 1% of paths in the typical location-week; in the
    location-weeks whose h3 97.5% is over 30x the recent level with no
    rule (10% of h3 cells) it drops more than 10%.
Q3. X15's pooled natural relWIS lies within 0.005 of clip 15x's (0.668);
    the sign is not predicted. Its 95% coverage is below clip 15x's
    (0.91), because dropping whole paths also lowers the h0 to h2 upper
    quantiles.
Q4. The h3 median moves by less than 1% in 90% of cells at X15 and by
    more than 20% in its worst 1%.
Q5. XS drops fewer paths than XP at the same n (the narrowing pulls the
    values above the median in), so XS at n scores nearer none than XP.

7. WHAT SHIPS
Nothing from here, as PREREG.md section 8.
