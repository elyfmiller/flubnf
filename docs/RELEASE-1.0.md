# FluBNF 1.0.0

Released 2026-08-23. First stable release.

FluBNF 1.0 ships a single product: an influenza hospital-admissions
forecasting system for the CDC FluSight challenge, whose default forecast is
an unfitted, equal-weight, quantile-averaged (vincentized) ensemble of two
members, a sequential particle filter over an SIHRS model written in BNGL and
a calendar analogue. This document records what that claim rests on. Every
number below is measured; the authoritative research record, including the
full history of corrections and retractions, is the Posner Lab archive
(`NAU-Projects/NAU_Influenza_M_Model/FluBNF/docs/RESULTS.md`).

## The three-season seal

The validation of record (sealed 2026-08-19) is a vintage-true retrospective
of three seasons at full grid: 52 jurisdictions, 3 replicates, 10,000
particles, seeded, with a frozen scoring formula (cells require settled truth
above zero and a positive median; the baseline construction is
anchor-validated). Members are honest real-time forecasts; the 50/50 blend
involves no fitting at all.

| season | particle filter | analogue | ensemble 50/50 | cells |
|---|---|---|---|---|
| 2023-24 | 1.023 | 1.105 | **0.848** | 6,063 |
| 2024-25 | 0.636 | 0.835 | **0.651** | 4,922 |
| 2025-26 | 0.825 | 0.641 | **0.691** | 4,475 |
| pooled | | | **0.704** | 15,460 |

Values are weighted interval score relative to the CDC FluSight-baseline;
below 1.000 beats the baseline. The unfitted 50/50 ensemble beats the
baseline in every season while the members alternate: in the 2023-24 plateau
season both members lose and the blend wins; in the clean 2024-25 A-wave the
filter carries; in 2025-26 the analogue carries. In-season optimal shares are
0.45 / 0.80 / 0.00, so any fitted constant share anti-predicts the next
season, and leave-one-season-out fitted weights score worse than the fixed
0.5 (0.732 against 0.704). Per the project record, the shipped ensemble also
beat its per-cell oracle. That is why v1.0 ships equal weights.

## Placement against real submitted forecasts

The same forecasts placed among the archived FluSight submissions (final
truth, coverage-gated, with both sanity checks of the join):

| season | placement | percentile |
|---|---|---|
| 2023-24 | 14 of 34 teams | 61st |
| 2024-25 | 4 of 40 teams, ahead of the official FluSight-ensemble (0.635 vs 0.674) | 92nd |
| 2025-26 | 19 of 47 teams | 61st |
| mean | | 71st |

Percentile is the share of the field beaten. The 2025-26 field of 47 is the
largest and strongest of the three. Honest reading: consistently
mid-to-upper field, with one standout season, against a field that grows and
improves each year. These placements are retrospective replays scored by this
repository's own code, not rankings earned by real-time participation.

## Independent replication

On 2026-08-23 a lab laptop (Apple M4) replayed all three seasons at full
grid, 52 jurisdictions, 3 replicates, using only the shipped console:

| season | laptop | sealed | wall time |
|---|---|---|---|
| 2023-24 | 0.847 | 0.848 | 6 h 51 m |
| 2024-25 | 0.651 | 0.651 | 5 h 57 m |
| 2025-26 | 0.691 | 0.691 | 4 h 54 m |

About 18 machine-hours for the whole record. Two seasons reproduce exactly
and one differs by 0.001. The seal is not a property of the machine that
produced it.

## The evidence ledger: what was tested and rejected

The rejections are part of the claim. Eight pre-registered challengers to the
two-member ensemble were built, tested, and rejected by this group, each by
its own rule set, frozen before execution: random-walk transmission, the
two-strain SIHRS, national-growth coupling at two doses, a
reporting-completeness correction in two forms (cross-season and
within-season rolling), a regime-switching filter, adaptive transmission, and
slope-anchored transmission. A ninth candidate, a post-hoc global width
scalar, was tested and found null in an independent review of this work
rather than by us, and is reported below as such. No challenger was rejected
by judgment after seeing its results.

A ninth challenger tested by us, donor-season composition in the analogue,
**passed** its pre-registered gates on 2026-08-24, after this release was
sealed. It is documented at the end of this section and is deliberately not
in v1.0. The eight killed challengers appear as seven bullets below:
the reporting-completeness correction was two separately pre-registered
challengers and is kept in one bullet. The externally tested width scalar is
the eighth bullet.

One further proposal, phase-conditional width scalars, was declined WITHOUT
being run: the diagnostic that motivated it showed the coverage error is
indexed by forecast week rather than by epidemic phase, and changes sign
between the two turns, so a static per-phase table could not represent it.
That decision is recorded here because declining to run an experiment on
diagnostic evidence is a different act from testing one, and the two should
not be counted together.

**The one that passed, and why it is not here.** Excluding the 2021-22
season from the analogue's donor pool improves the shipped ensemble by 3.66
percent pooled, bootstrap interval 1.78 to 6.01 percent, positive in all
three sealed seasons independently and in 50 of 52 jurisdictions, with
narrower intervals at unchanged coverage. A depth control settles the
mechanism: randomly shrinking the donor pool to the same size changes the
score by 0.20 percent, so the gain is which seasons are in the pool, not how
many donors it holds. 2021-22 peaked in April 2022 and survives in the
archive only as a February-to-July tail, so a calendar-matched pool asks
March what March 2022 did and is told the epidemic was still growing.

It is not in v1.0 because adopting it re-baselines every number this project
has published, including the three-season seal, this document, the README,
the site and the manuscript in preparation. Re-baselining a validated release
is a decision for the authors, not a change to fold into a tag. v1.0 ships
the donor pool that every published figure was measured on. The full record,
including the pre-registration hash and the arm that failed, is in the lab
research record.

Note also that the hypothesis as originally posed, flooring donors at 2023-24
because post-COVID dynamics differ, was tested and **killed**: the vintage
archive begins in February 2022, so that floor empties the pool for all of
2023-24 and the ensemble degrades to 0.7113 pooled. The useful exclusion is
one season, not a cutoff.

**Where the evidence lives.** The harnesses, the frozen pre-registrations and
the per-cell results are retained in the lab's private archive, not in this
repository: the `research/` tree was removed from public tracking at this tag,
and some challengers' results never lived in a tracked file at all. They are
available on request. The narrative record of every experiment, with its
numbers, its verdict and the corrections and retractions along the way, is the
Posner Lab archive at
`NAU-Projects/NAU_Influenza_M_Model/FluBNF/docs/RESULTS.md`. Where a
challenger's evidence did not survive at all, the entry below says so rather
than leaving the claim to look checkable when it is not.

* **Random-walk transmission (RW-beta).** SIHRS with a random-walk beta
  (three fitted parameters). Passed its membership gate (positive
  leave-one-season-out weight in every held season) but failed the decision
  gate: the three-member ensemble scored 0.664 pooled against the two-member
  reference's 0.620, worse in every held season. The random walk buys
  flexibility but pays too much interval width in stable phases.
* **Two-strain SIHRS with a typed-surveillance channel.** The strongest
  challenger and the nuanced verdict. On the six-state panel it passed both
  gates, and at full grid it passed the epidemic-turn gate (0.953 against the
  filter's 0.993 on 1,248 turn cells) and beat the single-strain filter
  outright in the plateau season (0.968 against 1.023). But the full-grid
  ensemble gate failed: equal thirds scored 0.7189 against the two-member
  0.7039, because 46 of 52 jurisdictions carry thin or withheld typed
  surveillance, diluting the second channel exactly where the member pays its
  identifiability cost. The engine remains available in the app, labeled
  turn-validated but not ensemble-validated.
* **National-growth coupling, two doses.** A national-growth term multiplying
  the seasonal transmission rate, at a frozen dose (0.302) and a
  growth-consistent dose (0.138). Killed at panel triage by its own rule:
  worse at the very turns the mechanism was designed for, and the strong dose
  was 1.22x wider at matched coverage with 2.4x the integrator failures.
* **Reporting-completeness correction, two forms**, counted separately
  because each was separately pre-registered, run and decided (2026-08-21 and
  2026-08-22). Cross-season fitted form:
  killed by the width screen; completeness is year-specific (national medians
  0.966 vs 0.982 in the two post-break seasons), so a correction fitted on
  the severe year over-corrects the mild one. Within-season rolling form:
  killed on three of four pre-registered clauses; any widening keyed to
  revision magnitude pushes 2025-26 coverage past nominal, because that
  season's intervals were already near-nominal.
* **Global width scalar**, a post-hoc rescaling of predictive width. Tested
  and found null, a movement of about 0.3 percent against this project's
  measured noise floor of roughly 5 percent, consistent with the
  project-wide pattern that every post-hoc correction of the output has
  failed. **Provenance, stated plainly:** this test was performed during an
  independent review of the project rather than by this group, and no
  per-cell result or harness for it survives in our archive. It is reported
  as recorded and cannot be re-checked from our artifacts, unlike the eight
  challengers above and below.
* **Regime-switching filter.** A calm/shifting switch on the filter's jitter
  intended to widen intervals at epidemic turns. Failed all three skill
  gates: 1.154 against production's 1.122 on the turn cells it was built for,
  and 0.646 against 0.643 and 0.580 against 0.575 on the replacement
  ensemble's selection and confirmation seasons. It cleared the do-no-harm
  floor only by being inert. The mechanism finding explains why: the turn
  detector never fired. Pooled P(shifting) sat at or below its stationary
  prior all season, peaking at 0.28 well after the January 2026 turn, because
  one week of negative-binomial noise cannot separate calm from shifting.
  Coverage at the January 2025 defect was identical to production, 0.271.
  3,060 fits, no harness retained.
* **Adaptive transmission (AR(1) increments with a fitted innovation
  scale).** The field's standard answer to non-seasonal waves: an AR(1) on
  the increments of log transmission, innovation scale fitted rather than
  hand-set, seasonal harmonic retained. Pre-registration `5fadd6ab8c0d46dc`;
  3,060 fits, no failures, 1,711 paired panel cells. **The closest any
  challenger came.** It is the first to clear the skill gate that RW-beta
  failed (0.6230 against the two-member 0.6426 on the selection seasons), it
  cleared the member floor, and it lifted February coverage from 0.698 to
  0.729. It was killed by one clause: **January central-50 coverage 0.312
  against a bar of 0.35**, 0.038 short, having moved the incumbent's 0.271
  most of the way there. The mechanism control is the finding: an arm with
  momentum removed and the scale still fitted scored 0.6215 / 0.5818 / 0.6083
  against the full arm's 0.6230 / 0.5831 / 0.6097, about 0.2 percent apart
  inside a 5 percent noise floor. The increment structure contributes nothing
  measurable; the entire gain over RW-beta comes from fitting the innovation
  scale (0.055) instead of setting it by hand (RW-beta's 0.5).
* **Slope-anchored transmission.** Transmission derived from the last two
  vintage-true observations rather than inferred, with **zero added fitted
  parameters**. Pre-registration `5a895f3c02e06af1`; 1,530 influenza cells,
  no failures. The zero-dimension claim is proved rather than asserted: the
  run's own production forward reproduces the seal's stored particle filter
  to 1.2e-07. Killed on **two** clauses: **1b, per-cell WIS correlation with
  the incumbent filter, 0.978 against a bar of 0.85**, and **2b, January
  coverage 0.312 against a bar of 0.35** — the same number and the same bar
  that killed adaptive transmission. It passed the growth-correlation clause
  (0.892), turned on time, and was narrower than production everywhere. Two
  caveats are recorded against the kill rather than hidden: the incumbents
  would fail clause 1b too (the production filter against the analogue
  correlates 0.949, already above the bar), so that clause is probably
  measuring cell difficulty rather than member redundancy and should be
  redesigned before reuse; and the skill clause it passed on the selection
  seasons inverted on the held-out season (1.018), so the skill was not
  durable. On COVID the same member passed every clause that applied. That is
  a first pass on 27 cells, not a validation.

One entry is not a clean kill, and calling it one would overstate the
ledger. The **two-strain SIHRS passed** its pre-registered panel test on
2026-08-20, on both gates, and passed the epidemic-turn gate again at full
grid. It failed only the full-grid ensemble gate. It ships in the app,
labeled turn-validated but not ensemble-validated.

Three patterns from the ledger are worth stating as findings. First,
six-state panel results did not transfer to the 52-jurisdiction grid on two
separate occasions (RW-beta, two-strain gate 2); the full grid is the only
binding validation surface. Second, fitted ensemble weights anti-predicted
the held-out season every time they were tried; the unfitted 50/50 blend
survived every challenge mounted against it. Third, the January turn has a
floor that ten attempts did not break: the two best challengers, arrived at
from opposite directions (one adding a fitted stochastic process, one adding
no parameters at all), both landed on a January coverage of exactly 0.312
against a bar of 0.35. Two independent mechanisms reaching the same number is
evidence about the defect, not about either mechanism.

## What v1.0 contains

* Forecasts for 52 US jurisdictions at the 23 FluSight quantile levels over
  horizons 0 to 3 weeks, emitted in the hubverse submission format and
  validated against the hub's own rules.
* Two inference engines sharing one model, likelihood, and priors: the
  sequential particle filter (`fit_type = pf`, seconds per state-season) and
  warm-started adaptive MCMC (`fit_type = am`, hours), plus the two-strain
  engine described above.
* The operations console: data integrity audit, forecast runs, weekly HTML
  report with a US map and per-state drill-down, exportable season report,
  and a season playback player over stored retrospectives.
* Retrospectives with pause and resume; an interrupted replay refits only
  the cells that never ran.
* Structural reproducibility: RNG seeds derived from
  `(location, date, replicate)`, exclusive workroot leases, and a sqlite run
  ledger recording the spec, seeds, and git SHAs needed to re-execute any
  run.
* Storage reclaim with an explicit, in-code split between deletable
  intermediates and the load-bearing record.
* Four color themes with high-contrast and red-green-safe modifiers.
* macOS and Linux support; Windows in experimental bring-up
  (see `docs/WINDOWS.md`).

## Known limitations

Stated in full in the README. In brief: interval narrowness at the January
epidemic turn (central 50 percent coverage of 27 percent at the January 2025
turn, unfixed by every challenger, the best two of which reached 0.312
against a pre-registered bar of 0.35); the adaptive MCMC engine does not
pass convergence diagnostics on this posterior and is not part of the shipped
ensemble; all scores are self-computed from the hub's archives rather than
earned in real-time participation; three seasons is the entire possible
vintage record; Windows is experimental.

## Naming

FluBNF 1.0 is a single-disease system. A COVID-19 feasibility study was
conducted and is recorded in the research archive; its mechanistic gates did
not pass. One later member, slope-anchored transmission, did pass every
COVID clause that applied to it, but on 27 cells: a first pass, not a
validation, and not a second disease. Any umbrella renaming is deferred
until a second disease clears its own validation gates.
