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
two-member ensemble were built, tested, and killed, each by its own
pre-registered rule set before execution: random-walk transmission, the
two-strain SIHRS, national-growth coupling at two doses, a
reporting-completeness correction in two forms, global and conditional width
scalars, and a regime-switching filter. No challenger was rejected by
judgment after seeing its results.

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
* **Reporting-completeness correction, two forms.** Cross-season fitted form:
  killed by the width screen; completeness is year-specific (national medians
  0.966 vs 0.982 in the two post-break seasons), so a correction fitted on
  the severe year over-corrects the mild one. Within-season rolling form:
  killed on three of four pre-registered clauses; any widening keyed to
  revision magnitude pushes 2025-26 coverage past nominal, because that
  season's intervals were already near-nominal.
* **Global and conditional width scalars.** Post-hoc rescaling of the
  predictive width, unconditional and phase-conditional. Both killed by their
  pre-registered rules, consistent with the project-wide pattern that every
  post-hoc correction of the output has failed.
* **Regime-switching filter.** A calm/shifting switch on the filter's jitter
  intended to widen intervals at epidemic turns. Failed all three skill
  gates, and the mechanism finding explains why: the turn detector never
  fired; one week of negative-binomial noise cannot separate the regimes.

Two patterns from the ledger are worth stating as findings. First,
six-state panel results did not transfer to the 52-jurisdiction grid on two
separate occasions (RW-beta, two-strain gate 2); the full grid is the only
binding validation surface. Second, fitted ensemble weights anti-predicted
the held-out season every time they were tried; the unfitted 50/50 blend
survived every challenge mounted against it.

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
turn, unfixed by all eight challengers); the adaptive MCMC engine does not
pass convergence diagnostics on this posterior and is not part of the shipped
ensemble; all scores are self-computed from the hub's archives rather than
earned in real-time participation; three seasons is the entire possible
vintage record; Windows is experimental.

## Naming

FluBNF 1.0 is a single-disease system. A COVID-19 feasibility study was
conducted and is recorded in the research archive; its mechanistic gates did
not pass, and any umbrella renaming is deferred until a second disease clears
its own validation gates.
