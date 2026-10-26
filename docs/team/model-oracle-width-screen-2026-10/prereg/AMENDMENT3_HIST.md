AMENDMENT 3 TO PREREG.md (sha256 fd8f57d6): THE HISTORICAL CEILING ARM H
(written 2026-10-25 23:41 UTC, before any ceiling row is computed or scored.
Ely's request in chat, 2026-10-25; the Submission lane's handoff of
2026-10-25 in docs/team/submission.md, For other lanes, with its predictions
P1 to P4; Ely's plan of 21:02 UTC: if the result passes by Tuesday
2026-10-27 evening, the 2026-10-28 round adds output.tail_hist 1 to the
shrink at 15x)

1. THE RULE
The knob output.tail_hist as it is on main a99d53d (dev 463ddba, branch
tail-hist 18b9fd6), the console's own functions in the console's order
(app/ui/pipeline.py, the output stage): flubnf.tailcap.history_ratios over
hist_series, every jurisdiction's whole history in the run's truth vintage
with the national row left out, window 2 epiweeks of the forecast date,
floor 10 on the recent level at the base week, strictly earlier seasons;
history_limits(ratios, recent_level(obs)), the recent level as the n-cap
reads it; clip_rows_by_horizon on the hub rows, before the n-cap
(cap_rows). The vintage is the file each replayed week read (the scoring
hub's archive, a byte copy of the replay hub's), so the ratios come from
each week's vintage, not the final truth. No replay: post hoc on C0's
stored weeks (arms/C0), as the cap arms and the exclusion arm were scored.
Script: hist_arm.py (SCREEN_WT = wt-hist, a99d53d); report: report_hist.py.

The data's reach, known before any score: the vintages start in 2022-02,
so the 2023-24 as-ofs read history from 2022-23 alone (and February to July
2022), 2024-25 from two seasons and 2025-26 from three; the live 2026-27
round reads four. The screen's October as-ofs are the 4 of 2023-24 (the
scoreable weeks of the other two seasons start in mid-November).

2. ARMS AND COMPARATORS (all at k 0.7, C0's 84 weeks, 17,466 cells)
hist max (level 1, the maximum) alone; hist 0.975 alone; hist max + shrink
15x (the pairing); hist max + clip 15x; hist max + shrink 10x. Comparators
recomputed on the same cells: none, clip 15x, shrink 15x, clip 10x.
Secondary rows, not tests: histF max and histF max + shrink 15x, the
maximum read from the settled truth file, for the vintage-against-final
difference the handoff asks to report.

3. SUBSETS
All 84 weeks; the early-week subset of the C0 reading (the first 8
scoreable as-of weeks of each season, 24 weeks; logs/report_C0_early.txt);
the October as-ofs (4); the as-of months September to November (14),
printed for continuity with report.py's tables. Correction to AMENDMENT2
section 3: it called its September to November subset "24 weeks, as in the
C0 reading"; report_excl.py read the 14 as-of weeks dated September to
November. The two are different subsets; this arm reports both by name.

4. REPORTED
For every arm: pooled relWIS on both scales, coverage 50/80/95, the gate
(share of h3 cells over 30x, typical h3 97.5% over the recent level and
over the median), by season, by horizon, on each subset. The week-cluster
bootstrap (2,000 replicates by as-of week, report.py's boot_diff and seed)
of each arm minus none, clip 15x, shrink 15x and clip 10x, both scales, on
all weeks and on the early-week subset. The share of (location, horizon)
blocks the ceiling touched, by horizon, on all weeks, the early-week
subset, the October as-ofs and by season, and the share collapsed (limit at
or below the median, so the upper levels sit at the median). The ratios by
horizon: the median over the 84 weeks and over the early-week subset, each
October as-of, by month, with the pool sizes. The vintage against the
settled truth: the relative difference of the ratios per week and horizon
(median, maximum) and histF minus hist, pooled. The pairing's natural WIS
gain over shrink 15x by as-of month group (September-October,
November-January, February-May).

5. CHECKS (the arm is read only if all pass on every week)
A3. The four comparators equal C0.cells.pkl's k 0.7 rows cell for cell (WIS
    and log WIS, max |difference| at most 1e-9), on the wt-hist code.
B3. An independent implementation of the ratios (pandas: the base level a
    3-row rolling mean by position, the outcome by date join, the window by
    ISO week distance as the code defines it) equals history_ratios on
    every week, both levels, both sources (relative 1e-9).
C3. Every ceiling block: levels at or below the median unchanged; levels
    above at most max(limit, median) + 0.5 (whole admissions) and monotone;
    a block with no level above max(limit, median), or no limit, identical;
    the blocks touched equal clip_rows_by_horizon's own count.
D3. The ceiling with every limit NaN returns the none rows exactly.
Before this amendment: tests/test_tailcap.py and app/tests/test_knobs.py on
a99d53d, 163 passed. The smoke week 2024-12-07 is run for the checks only
before the full run; its scores are not read.

6. PREDICTIONS
The Submission lane's, made operational here (natural scale unless named):
P1. hist max minus none: point estimate at most 0 and the upper end of the
    95% interval at most 0.
P2. (a) the pairing below shrink 15x by 0.5% to 1.5% of shrink 15x's pooled
    relWIS; (b) the 95% interval of the pairing minus clip 15x contains 0.
P3. (a) on the October as-ofs the pairing's pooled relWIS within 0.002 of
    shrink 15x's; (c) more than half of the pairing's summed WIS gain over
    shrink 15x on as-ofs dated November to January. (b), the stated reason,
    is reported, not tested: the share of October as-ofs whose history
    maximum is above 15 at h1, h2 and h3.
P4. hist 0.975: 95% coverage at least 0.02 below none's, and log relWIS
    above none's.
A miss in the favourable direction (a gain beyond P2a's range; P2b's
interval wholly below zero) is named as such and does not count as a
failure.
This lane's own:
Q1. hist max alone touches under 5% of h0 blocks and 5% to 30% of h3
    blocks over the 84 weeks, and under 5% of blocks at every horizon on the
    October as-ofs.
Q2. The vintage and settled ratios differ by under 1% at the median week
    and horizon, and hist max and histF max by under 0.001 pooled.
Q3. Of the three seasons, 2023-24 (one history season) has the largest
    share of h3 blocks touched by hist max.

7. THE DECISION FOR 2026-10-28
The ceiling PASSES (the round adds output.tail_hist 1 to the shrink at
15x, at Ely's word) if all of these hold:
(1) every check passes on every week;
(2) P1, P2 and P3 hold (favourable misses are not failures);
(3) the pairing against shrink 15x, the 10-28 form: (i) pooled relWIS not
    above shrink 15x's on either scale; (ii) no season above shrink 15x's by
    more than 0.010; (iii) 95% coverage no more than 0.010 below shrink
    15x's, on the 84 weeks and on the early-week subset; (iv) on the
    early-week subset, relWIS not above shrink 15x's by more than 0.005.
This is PREREG section 6 adapted to an output rule set against the 10-28
form instead of C0: rule (iii)'s absolute 0.90 becomes relative because the
reference itself sits at 0.90, so an absolute floor would test for no loss
at all; PREREG's (iv), a bootstrap interval excluding zero, is not
required, because the question is whether the pairing is no worse than the
default and P2 itself predicts a gain within noise of the clip. P4 is
reported and does not gate (the 0.975 level is proposed for no round).
Otherwise the 2026-10-28 round runs the shrink at 15x alone (Submission
notes, 2026-10-25 21:02 UTC) and the result stands for 2026-11-04.

8. WHAT SHIPS
Nothing from here without Ely (PREREG section 8); the result goes to
docs/team/model.md for the Submission lane and the team review.
