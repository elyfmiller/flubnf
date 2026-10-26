ORACLE SIHRS WIDTH SCREEN ON FULL SEASONS: PRE-REGISTRATION
(frozen 2026-10-22, before any arm or output rule of this screen is scored;
Ely's go of 2026-10-22: "Full replays for only SIHRS across available seasons
to test on, rescored", "Try 8x, 10x and 15x"; the four structural arms are
the Submission lane's handoff of 2026-10-22 from Ely, with Ely's answers of
the same night: the swarm carry folded into the past-season prior arm, the
growth cap scored post hoc)

0. WHY
Ely's goal for the 2026-10-28 round: both members' width near the NAU
members' (no state over 30x the recent level at horizon 3; the typical h3
97.5% near 10-12x the recent level). The output-stage rule that does this
(output.tail_cap with output.tail_mode = shrink, flubnf/tailcap.py, main
744e654) has been scored only post hoc on 44 stored stage-rule weeks in the
Submission lane's cloud session. This screen (A) scores the output rule on
the three full seasons on this machine, the target-driven narrowing first,
and (B) tests four structural arms that act inside the filter instead of on
its output.

1. REPLAYS (every arm identical except its knobs)
Seasons 2023-24, 2024-25, 2025-26: the 84 as-of weeks with a
FluSight-baseline file (30, 27, 27; the other 9 cannot be scored). All 52
jurisdictions x 3 replicates, 10,000 particles, `flubnf retro run` per
season (run_arm.py narrows only the vintage list). flubnf main 744e654
(worktree wt/, detached), engine PyBNF-pf 2fdadee0 with bngsim 0.15.1 and
numpy 1.26.4 (~/.venvs/flubnf-engine), the research hub clone
us_national/hub 09c96ec8 for the dated vintages. The live knobs of the
2026-10-24 round in every arm: pf.seed_denominator = season_total_early,
oracle.w = 0.25, oracle.narrow = 0.7. Order: C0, then the season-end fits
of section 3, R20, R22, HP, HS.

2. ARMS
C0   control: the live configuration above.
R20  + pf.prior.Reff = 0.6,2.0
R22  + pf.prior.Reff = 0.6,2.2
HP   + pf.prior.eps1 and pf.prior.phi1 set per test season to the pooled
     past-season box of section 3 (uniform, the console's own knobs).
HS   + eps1 and phi1 boxes per jurisdiction (section 3), written into each
     cell's pf.conf by a research hook in the launcher after prepare() and
     before the runners start (the console has no per-location prior); the
     swarm carry in the form Ely chose: the state's own past seasons as its
     prior, on the harmonic only.
G    no replay: on C0's stored member samples (path-aligned across the four
     horizons), each path's week-over-week ratio capped at g, cumulatively
     from the as-of week's reported count (x'_h = min(x_h, g x'_{h-1}),
     x'_{-1} = y_T; a location with y_T = 0 untouched), g in {1.5, 2, 3}.

3. THE PAST-SEASON BOXES (rule fixed here; values posted as amendment 1
before HP and HS launch, and before any arm is scored)
Season-end fits: the live configuration at the last week of each completed
season, 52 jurisdictions x 3 replicates, pruning held off so each cell's
params_0.txt is kept: 2022-23 at 2023-06-10, 2023-24 at 2024-04-27, 2024-25
at 2025-06-14. 2022-23 has no archived vintage; its vintage is the
2023-09-23 file cut to rows dated on or before 2023-06-10 (later data, so
more settled than a real-time vintage; acceptable for a season-end fit,
whose purpose is what the season needed in hindsight). A test season uses
only strictly earlier seasons: 2023-24 from 2022-23; 2024-25 from 2022-23
and 2023-24; 2025-26 from all three.
For each (jurisdiction, season) fit: the posterior median and the 2.5% and
97.5% points of eps1 and of phi1 over the 30,000 particles.
HP box, per test season and parameter: [q05, q95] of the per-(jurisdiction,
earlier season) medians, widened by half its width on each side, clipped to
the shipped range (eps1 0-1, phi1 0-52), widened symmetrically to at least
0.2 (eps1) and 8 weeks (phi1) if narrower.
HS box, per test season, jurisdiction and parameter: [min of the 2.5%
points, max of the 97.5% points] over that jurisdiction's earlier seasons,
widened, clipped and floored by the same rule.
phi1 is a phase on 0-52; if any fit's interval straddles the wrap (its
2.5% point above its 97.5% point on the circle), that is reported and the
box for that parameter falls back to the shipped range.

4. SCORING (score_arm.py; an arm is read only if checks A, B and C pass)
Each stored week's hub rows rebuilt as a live run builds them (the stored
member samples after the step, the narrowing and the floor;
app.core.submit.quantile_rows, whole admissions), the output rule by
flubnf.tailcap.cap_rows (the limit from the as-of vintage as
app/ui/pipeline.py reads it), scored by app.core.scoring.score_quantiles:
FluSight's cell rule, the validated baseline join, WIS and log-scale WIS,
coverage 50/80/95, against settled truth (the research hub's target data,
09c96ec8) and the FluSight baseline. Pooled relWIS is a ratio of sums over
each arm's own scored cells; arm comparisons use the cells both score.
Checks: A, the unrounded quantiles equal the week's quantiles.json and
their scores equal retro.score_season on every cell; B, an independent WIS
(the mean quantile score) equals flubnf.wis on every scored cell; C, the
step's recorded pre-floor quantiles of the submitted seed at the run's k
and at k = 1 bound the floor's effect and the re-exponentiation's error.
Passed on the smoke week 2024-12-07 (Alaska, Florida): A exact, B exact,
C within 0.05% of WIS.

5. (A) THE OUTPUT RULE, FIRST
Grid: narrowing k in {1.0, 0.9, 0.8, 0.7, 0.6, 0.5} (0.7 exact; the others
re-exponentiated, approximate within check C); rule none, or shrink or clip
at n in {8, 10, 15, 20, 30}.
Reported for every rule at k = 0.7: pooled relWIS on both scales, coverage
50/80/95, the gate (share of h3 cells over 30x, typical h3 97.5% over the
recent level, typical h3 97.5% over the median), by season, by horizon,
and September to November as-of weeks against the rest; a week-cluster
bootstrap (2,000 replicates by as-of week) of each rule minus none and
minus clip 15x.
Reading, set now: the "free" line is the smallest shrink n whose pooled
natural relWIS is within 0.010 of k 0.7 with no rule and whose pooled 95%
coverage is at least 0.90; Ely's 8x, 10x and 15x are each reported against
it. Leave-one-season-out over the whole grid (k x rule; natural relWIS,
log as the tie-break) gives a held-out score and choice.

6. (B) THE STRUCTURAL ARMS
Each arm's (k, rule) chosen by leave-one-season-out as in 5. An arm is
BETTER THAN C0 only if (i) its held-out pooled relWIS is below C0's on both
scales, (ii) no season's natural relWIS is worse than C0's by more than
0.010 at the two choices, (iii) its pooled 95% coverage is at least 0.90,
and (iv) the week-cluster bootstrap 95% interval of arm minus C0 at C0's
choice excludes zero, on the common cells. Otherwise NULL for that arm.
Every arm is also reported at the live settings (k 0.7 with shrink 15x and
10x) and for the filter alone (oracle.json's null quantiles).

7. PREDICTIONS (recorded before any score; each may be wrong)
P1 (A) Shrink at 10x costs 1 to 2% of pooled natural relWIS against no rule
   at k 0.7 and lowers 95% coverage by 0.03 to 0.08 (the cloud's 44 weeks:
   0.688 against 0.671, coverage 0.869 against 0.930).
P2 (A) The clip scores better than the shrink at every n over whole
   seasons; the shrink is better in September to November.
P3 (B) R20 is within 0.005 of C0 at their choices: the narrowing already
   does what the bound does (the three-vintage cloud arm equalled k 0.05
   lower), and on the old pin a calendar-free Reff box of 0.6-1.65 cost
   the filter 0.016 (research/almanac-prior, NULL).
P4 (B) R22 lies between C0 and R20.
P5 (B) HP and HS narrow the early-season h3 band most and cost most at the
   peaks; net within 0.010 of C0.
P6 (B) No growth cap g beats the shrink or the clip at a matched gate.

8. WHAT SHIPS
Nothing from here. A form that wins is a recommendation to Ely; any change
to the registered member ships only by override with a card sentence (the
member's pre-registration 67c9fa49 is frozen), as the narrowing and the cap
do.

9. STOPS
Anything unfinished stops before the 2026-10-28 target-data update (about
19:50 UTC) and resumes after the hub pull request is open. An arm with a
failed cell is reported with the cell named; checks A to C failing stops
that arm's reading.
