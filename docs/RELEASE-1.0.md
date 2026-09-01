# FluBNF 1.0.0

Released 2026-08-23. First stable release. Amended 2026-08-24, before the tag
was published, to ship the analogue donor-pool exclusion described under
[The donor-pool change](#the-donor-pool-change) and to re-baseline every
figure in this document against it. The version number is unchanged because
no v1.0.0 was ever published carrying the earlier figures; where a number
moved, both values are given.

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
| 2023-24 | 1.023 | 1.045 | **0.813** | 6,063 |
| 2024-25 | 0.636 | 0.756 | **0.618** | 4,922 |
| 2025-26 | 0.825 | 0.621 | **0.683** | 4,475 |
| pooled | 0.775 | 0.772 | **0.678** | 15,460 |

Values are weighted interval score relative to the CDC FluSight-baseline;
below 1.000 beats the baseline. Every relWIS in this document is a ratio of
WIS sums over shared cells (the project's home convention); it is not the
pairwise scaled relative WIS the CDC dashboard reports, and the two are not
comparable. They are read from the seal's rebuilt
`scores.json` after the donor-pool exclusion was applied. For reference, the
same table before that exclusion read 1.023 / 1.105 / 0.847 / 6,063,
0.636 / 0.835 / 0.651 / 4,922, 0.825 / 0.641 / 0.691 / 4,475 and a pooled
0.704; the particle-filter column and every cell count are identical in the
two, because the change touches only the analogue. The cells column is the
ensemble's and the analogue's; the filter is scored on 95 fewer cells pooled,
15,365, being the cells where it produced a forecast at all.

The unfitted 50/50 ensemble beats the baseline in every season while the
members alternate: in the 2023-24 plateau season both members lose and the
blend wins; in the clean 2024-25 A-wave the filter carries; in 2025-26 the
analogue carries. That pattern survives the donor change, though the filter's
2024-25 lead over the analogue narrows from 0.199 to 0.120 and the analogue's
2025-26 lead widens.

In-season optimal PF shares, swept on the rebuilt seal in steps of 0.05, are
0.40 / 0.65 / 0.00 (they were 0.45 / 0.80 / 0.00 before the donor change), so
a fitted constant share still anti-predicts the next season. The unfitted 0.5
costs 0.005, 0.007 and 0.062 relWIS against those per-season optima, none of
which is knowable in advance.

Fitted weights still score worse than the fixed 0.5. Applying the frozen
per-horizon table to the rebuilt seal gives 0.6958 pooled against the
unfitted 0.6781; before the donor change the same comparison was 0.7107
against 0.7039. The fitted figure is the flattering one in both cases, since
the table was fitted using the very seasons it is scored on. The
leave-one-season-out fit recorded at the 2026-08-17 freeze was 0.717; that
number was measured on the pre-exclusion donor pool and has not been
re-derived, because no code for the leave-one-season-out weight fit survives
in this repository or in the lab archive. Fitted weights are reported here
only as the rejected alternative; no shipped forecast and no headline figure
uses them. That is why v1.0 ships equal weights.

One claim carried in earlier drafts of this section, that the shipped
ensemble also beat its per-cell oracle, is withdrawn. No artifact in the
repository or the lab archive derives it, so it cannot be checked, and it
should not be restated about the new configuration on the strength of the
old record.

### Seal caveats, recorded 2026-09-01

A parity and leakage audit after release found two measured gaps between
the sealed numbers and the standard they are meant to embody, the app in
real time, replayed. Both are recorded here so a reader reproducing the
seal knows exactly what the numbers score. Neither moves the headline
conclusion: the ensemble beats the baseline in every season by margins far
larger than either effect.

**The sealed scores are computed on pre-floor internal forecasts, at float
precision.** The live console applies a seeded output floor to every
member before ensembling and submission (`app/core/floor.py`, wired into
the weekly path in `app/ui/server.py` on 2026-08-18, commits `3582f84` and
`191771c`), and the submission writer rounds quantiles to whole admissions
and re-monotonizes them (`app/core/submit.py`). The retrospective path
does neither: it stores and scores the raw member samples. The sealed
record, rebuilt 2026-08-24, therefore scores forecasts the live app would
have floored and rounded before submitting them. Measured on four sealed
2023-24 weeks (settled truth, ratio of sums, US excluded): raw 0.760151 on
797 cells, against live-path floored 0.761418 on 811 cells, and 0.761283
on those same 811 cells with hub rounding applied as well. The floor
effect is order 1e-3 on the score and also changes the cell set, since 14
cells enter scoring only because the floor lifts a collapsed median above
zero; the sealed 15,460 cells is therefore not exactly the live path's
cell universe. The rounding effect is order 1e-4. The alternative
resolution, applying the identical seeded floor inside the retrospective
and re-baselining every figure in this document, remains open; if taken,
it supersedes this caveat.

**Seven of the 76 sealed as-of weeks consumed a vintage snapshot that
differs from submission-deadline knowledge.** The hub's vintage archive
(`auxiliary-data/target-data-archive/`) names each file by the newest data
week it contains, not by the day it was captured; measured capture lag
across the archive runs 4 to 37 days, and four archive files were amended
in place after their first commit. Diffing every consumed vintage against
the hub's `target-data/target-hospital-admissions.csv` as of the last
commit at most four days after each as-of date: 69 of the 76 consumed
vintages are identical to deadline knowledge (26 of 30 in 2023-24, 21 of
24 in 2024-25, and 22 of 22 in 2025-26, which is entirely clean). Six
consumed weeks carry data no real-time participant could have had:
2023-10-07; 2024-03-30 (amended upstream after the deadline, for example
California 185 to 179, and the replay reads the amended file); 2024-04-06,
2024-12-21 and 2024-12-28, each carrying its entire same-day data week, 53
rows absent from the deadline feed, with 2024-12-28 additionally carrying
72 revised cells, including US 2024-12-21 at 14,667 against the 12,497
known at the deadline and Arizona at 1,507 against 438; and 2024-04-27.
One consumed week, 2024-11-16, is the reverse case, stale relative to the
deadline (US 2,886 against the 3,997 already public). The divergent weeks
concentrate on the 2024-25 holiday turn, the particle filter's
best-scored stretch. Two further divergent archive files, 2023-09-30 and
2025-08-30, are not sealed as-of weeks and feed no sealed forecast. A
sensitivity refit of the affected weeks from deadline-day data,
materialized out of the hub clone's git history, is an open item and has
not been run.

### Provenance of the sealed record, recorded 2026-09-01

The sealed runs predate the app's run-provenance record (no `run_meta.json`
exists in any sealed season), and the machine-local
`component_versions.json` is misleading about what actually executed: it
records the site-packages `pybnf 1.3.0`, which every sealed runner shadows
with the editable fork checkout (`sys.path.insert(0, .../PyBNF-pf)`), and a
`bngsim` whose version string is a known-lying local build. The facts
below were recovered and measured after the fact so a reproducer does not
have to; each was verified directly this session.

* **PyBNF fork commit.** The sealed fits ran the private fork at
  `b5ffd664` (recovered from the fork worktree's reflog, which brackets
  the sealed runner mtimes of 2026-08-18). That commit is an ancestor of
  the pushed tip `3320d1f0`; the four commits between them (all later
  than the sealed fits, the last two later than the sealed record
  itself) were measured to net to no change: the full 10,000-particle
  filter state
  (`pf_state.npz`: theta, species, weights) is bit-identical between
  `b5ffd664`, the tip, and a tip rerun. A stranger cloning the fork today
  reproduces the sealed filter output.
* **bngsim.** The dev host's engine venv carries a local build whose
  version string reads 0.13.0; `setup_engine.sh` installs `bngsim==0.15.1`
  on new machines. The two were measured bit-identical at the full filter
  state, so the released pin reproduces the seal.
* **Truth data.** The seal was scored against the hub clone's
  `target-data/target-hospital-admissions.csv` at hub commit `18f68c23`
  (the 2026-07-15 upstream state, pulled locally 2026-08-18; the file is
  md5-identical to upstream cdcepi commit `e311e577`). NHSN continues to revise past-season admissions upstream,
  so the truth file a reproducer clones is date-dependent: rescoring all
  three seasons under the 2026-06-17 vintage moves the pooled ensemble by
  3.1e-5 (0.812967 / 0.617964 / 0.682491, pooled 0.678088) and churns the
  cell universe by a few cells (2025-26 drops 3 of 4,475 under the
  actual-above-zero rule). "Same values" therefore means agreement to
  order 1e-4 in any relWIS unless the named truth commit is materialized
  from the hub's git history first.
* **Locations table.** Replayed fits read state populations from the hub
  checkout's current `auxiliary-data/locations.csv`, not a vintage table;
  the sealed record was produced against the table carried in the same
  hub commit `18f68c23`, whose populations were published upstream on
  2025-09-09 (hub commit `8327d8bf`), years after the replayed seasons'
  own tables (the hub pins those as `locations_202324.csv` and
  `locations_202425.csv`). The
  deterministic observable is population-invariant, and the measured
  effect of the table's revisions on any single cell sits inside the
  single-replicate noise floor, but bit-level replay depends on the
  table's revision state (see also the `resolve_state` docstring).
* **Run settings.** 52 jurisdictions, 3 replicates, 10,000 particles,
  jitter 0.30, integrated observable mode, `drop_same_day` False. The
  seed chain is end-to-end deterministic into the engine: the wrapper's
  `derive_seed(location, date, replicate)` value is written into each
  cell's `pf.conf` and consumed by the fork (verified: Alabama /
  2023-09-23 / replicate 0 derives 646483348, the same value recorded in
  the sealed `cells_0.json` and in the prepared `pf.conf`).
* **The stored week trees were amended once after sealing.** On
  2026-08-26 a US-national backfill rewrote every sealed `samples.json`
  to add a fitted US block, deliberately preserving file mtimes, so the
  sealed trees are no longer byte-identical to the input that produced
  the sealed `scores.json` (which contains 0 US rows). Rescoring the
  amended trees reproduces all 46,285 sealed non-US rows to JSON
  round-trip precision (5e-11, 0 unmatched keys) while emitting 360 /
  288 / 264 additional US rows per season that the published aggregation
  excludes; no published number is affected.
* **The sealed US figure is a construction, not a model output.** The US
  number shown for the sealed seasons is the sum-of-states aggregate,
  while the shipping app fits the US series directly as a 53rd location,
  so a fresh replay with the national default on produces a fitted US
  forecast that is a different model output from the sealed aggregate.
  Both are excluded from every pooled headline by the named policy
  (`us_national.POOLED_INCLUDES_US = False`; the sealed `scores.json`
  files contain no US rows).

## Placement against real submitted forecasts: withdrawn

Earlier drafts of this document carried a table placing the same forecasts
among the archived FluSight submissions: 14 of 34 in 2023-24, 4 of 40 in
2024-25 (with 0.635 against the official FluSight-ensemble's 0.674), 19 of 47
in 2025-26, mean 71st percentile. That table is withdrawn. It is not merely
stale, and re-labelling it as a pre-exclusion measurement would not be
enough.

Three findings, from an attempt on 2026-08-24 to re-measure it against the
shipped configuration:

* **The scorer does not survive.** No script that produces the placement
  table exists in this repository or in the lab archive. The retained
  artifacts are the ranked field files themselves.
* **The field could not be reproduced.** A reconstruction from this
  repository's own scoring code (the validated FluSight-baseline denominator,
  settled truth, the frozen cell rule) reproduced no archived row of the
  2023-24 field exactly. The reconstruction's cell universe differs from the
  archived one by a single cell once Puerto Rico is removed, so the gate is
  close, but the per-team differences are broad and not a common factor: of
  37 scoreable teams (the baseline's trivial self-agreement and one team
  with no reconstructable score excluded), 8 reproduce within 1 percent,
  18 differ by 1 to 6 percent, and 11 by more than 6 percent, the extremes
  -20.9 and +14.2 percent (retained artifact:
  placement_reconstruction_2023-24.txt). The archived field was therefore
  scored on a convention this repository cannot restate.
* **This project's own three rows were not computed on one convention.** The
  2025-26 row, 0.691107728891329 on 4,475 cells, is exactly the seal's own
  vintage relWIS for the unfitted 50/50 blend. The 2024-25 row,
  0.6346812543520274 on 4,922 cells, is exactly the seal's relWIS for the
  leave-one-season-out **fitted** ensemble, which this project rejected and
  never ships. The 2023-24 row, 0.8929930728709135 on 5,868 cells, matches
  neither, on neither cell count.

A published number produced with fitted ensemble weights is exactly the
failure this project's own rule against fitted weights exists to prevent, so
the figure is retracted rather than corrected in place. The placement claim
returns only when the field and this project's entry are scored again,
end to end, on one stated convention and on the shipped configuration. Until
then this document claims no placement, and the reader should treat the
withdrawn numbers as unverified.

## Independent replication, of the pre-exclusion configuration

Replication note (2026-08-26, extended 2026-09-01): the epiweek-53
donor-window fix (commit `52cc22f`, committed 2026-08-26, two days after
the sealed record was rebuilt) means a from-scratch replay on current code
diverges from the sealed analogue member at exactly one as-of week,
2026-01-03 (188 cells; member relWIS 0.770852 sealed arithmetic vs
0.769917 fixed, measured on the full grid with the old arithmetic
reproducing all 15,712 sealed cells first). The season-level and pooled
consequence, measured 2026-09-01: a fresh replay on shipped code yields
2025-26 analogue 0.618025 against the sealed 0.621006 and 2025-26
ensemble 0.680500 against the sealed 0.682662, moving the pooled ensemble
from 0.678119 to 0.677437, so the printed 0.683 and 0.678 are not
reproduced at printed precision by current code (they round from the
sealed values; the replayed values round to 0.681 and 0.677). Every other
sealed week regenerates at max quantile diff 0.0. A bit-exact
reproduction of the sealed record uses the sealed code state, which is
commit `9b0ef26` in this repository's history: the pre-fix arithmetic at
that revision reproduces the sealed 2026-01-03 analogue quantiles on all
53 locations to max abs diff 0.0. Whether to re-baseline the seal table
to the shipped-code values instead of carrying this caveat is an open
decision.

On 2026-08-23 a lab laptop (Apple M4) replayed all three seasons at full
grid, 52 jurisdictions, 3 replicates, using only the shipped console:

| season | laptop | sealed at the time | wall time |
|---|---|---|---|
| 2023-24 | 0.847 | 0.847 | 6 h 51 m |
| 2024-25 | 0.651 | 0.651 | 5 h 57 m |
| 2025-26 | 0.691 | 0.691 | 4 h 54 m |

About 18 machine-hours for the whole record, and all three seasons reproduce.
Two corrections to how this was reported before.

First, the 0.001 gap once shown in the 2023-24 row was not a machine
difference. The sealed value was 0.84746, so 0.847 was always its correct
rounding; the 0.848 printed in the sealed column of earlier drafts was an
error in the document. The donor-floor harness re-derived the same 0.847 on
the machine that produced the seal. The laptop and the seal agreed exactly in
all three seasons.

Second, and more important, this replay predates the donor-pool change, so it
replicates the pre-exclusion configuration and not the table at the top of
this document. That table has not been reproduced on second hardware, and
this document does not claim it has. What the replication establishes still
holds, because the stage it exercised is the stage the donor change does not
touch: the particle filter is the entire compute cost and the only stochastic
stage of the pipeline, its stored samples are byte-identical before and after
the change (12.34 GB across all 85 sealed weeks, verified by sha256 per week),
and its per-cell scores move by 0.000e+00 over all 15,365 filter cells. The
analogue is a deterministic empirical calculation over the same archive, and
regenerating it requires no fitting. A second machine reproducing the shipped
figures is a smaller job than the original replication for exactly that
reason, but it has not been run.

## The donor-pool change

This is the one change made to the shipped model after the release was first
sealed on 2026-08-19, and the reason every figure above carries two values.

**What changed.** The calendar analogue draws its growth ratios from every
strictly prior season in the archive. It now excludes one of them, 2021-22.
Nothing else changed: the particle filter, the 50/50 blend, the scoring
formula, the cell rule and the baseline construction are all untouched, and
the seal's stored filter samples are byte-identical before and after. In the
code the exclusion is a single guard in `flubnf/analogue.py`.

**Why.** 2021-22 peaked at epiweek 16, on 2022-04-23, while the other four
donor seasons peaked between epiweek 48 and epiweek 6. The surveillance
series carried in the archived vintages begins 2022-02-05, so 2021-22 exists
in the archive only as a February-to-July tail, which is to say only as its
growth phase. A calendar-matched donor pool asks what happened in March, and
2021-22 answers that the epidemic was still growing. It is the only donor
season whose March ratios have a median above one, and their upper tail is
several times heavier than any other season's; the exact ranges depend on
how the March pool is defined, so the claim is stated at the strength at
which it reproduces. The exclusion removes a phase-inverted donor, not an
inconvenient one.

**Pre-registration.** The question, the arms, the depth control, the metrics,
the gates and the kill rule were frozen before any score was computed, under
hash `8f3c7a45a989e905`. The frozen text and the harness are in the lab
archive. Two arms were registered: A1, flooring donors at 2023-24 on the
grounds that post-COVID dynamics differ, and A2, dropping 2021-22 alone.

**The measured effect,** at full grid, 15,460 cells, with a clustered
bootstrap over the 76 replayed weeks:

| quantity | pre-exclusion | shipped | change | bootstrap 95% |
|---|---|---|---|---|
| ensemble, pooled | 0.7039 | 0.6781 | +3.66% | 1.83 to 6.07% |
| ensemble, 2023-24 | 0.8475 | 0.8131 | +4.05% | 1.43 to 7.01% |
| ensemble, 2024-25 | 0.6513 | 0.6179 | +5.13% | 1.42 to 10.32% |
| ensemble, 2025-26 | 0.6911 | 0.6827 | +1.22% | 0.10 to 3.17% |
| analogue member, pooled | 0.8290 | 0.7723 | +6.83% | 3.10 to 11.32% |
| analogue, cells actually affected | 0.8142 | 0.6706 | +17.64% | 8.51 to 25.67% |

The improvement is positive in all three seasons independently and in 50 of
52 jurisdictions.

**The depth control,** which is what makes the result a mechanism claim
rather than a correlation. A restricted pool is also a smaller pool, so the
harness scored a third arm: the full pool subsampled at random, without
replacement, to exactly the restricted pool's size, averaged over ten
deterministic seeds. That control moves the score by 0.20 percent
(bootstrap 0.0006 to 0.389 percent) while removing 2021-22 in particular
moves it by 17.64 percent on the same cells. The gain is which season is in
the pool, not how many donors it holds.

**The arm that failed.** A1, the hypothesis as originally posed, was
**killed** by its own pre-registered rule. Because the archive begins in
February 2022, flooring donors at 2023-24 empties the pool for the whole of
2023-24, the analogue falls silent there, and the pooled ensemble degrades to
0.7113 against the 0.7039 it was measured beside. The useful exclusion is one
season, not a cutoff.

**Honest caveats,** all four of which belong with the result:

* It was pre-registered from a structural argument about the calendar, not
  found by searching donor subsets for a better score. That is why it is
  reported as one arm with a frozen kill rule rather than as the best of
  many.
* It is validated on these three seasons and nowhere else. There is no
  fourth vintage-true season to hold out, so the change carries the same
  small-sample limit as every other figure in this document.
* The gain necessarily concentrates late in each season. 2021-22 contributes
  no donors at all before February, so nothing in October, November or
  December changes: of the 15,460 scored cells, 9,363 differ at all, and they
  are every February, March, April and May cell plus 624 of the 2,080 January
  cells. A reader comparing early-season weeks will see no effect, correctly.
* The effect shrinks on its own as history accumulates. 2021-22 contributes
  a fixed set of donor weeks that cannot grow, while the pool gains a season
  every year, so its share of the donors falls monotonically: in the fullest
  donor pool of each season, at horizon one on 2024-03-16, 2025-03-15 and
  2026-03-21, it supplies 253 of 501 donors in 2023-24, 253 of 766 in
  2024-25 and 253 of 1,031 in 2025-26, which is 50.5, 33.0 and 24.5 percent.
  The three counts are equal because 2021-22's donor weeks are a fixed set,
  and the share must be read within a single pool: the largest pool and the
  largest 2021-22 contribution do not fall in the same week, so differencing
  the two maxima across rows counts nothing real. The measured per-season
  gain is 4.05, 5.13 and 1.22 percent, which is not a clean trend on three
  points but is smallest in the most recent season. This is a correction with
  a finite life, and it should be re-measured, not assumed, in each new
  season.

**What it costs.** The analogue's intervals narrow, and so do the ensemble's:
pooled, the central 50, 80 and 95 percent intervals are 0.93, 0.92 and 0.90 of
their previous total width. Coverage remains above nominal at all three levels
pooled, 0.541 / 0.837 / 0.961 against 0.50 / 0.80 / 0.95. The January 2025
turn defect is untouched at central-50 coverage 0.271 either way, the same 13
of 48 cells, and that is the level the ledger's kill clauses were written
against; the other two levels on that window did move, 80 percent coverage
from 0.667 to 0.604 and 95 percent from 0.938 to 0.917, with the mean
central-50 width narrowing from 847.0 to 817.3. So "untouched" is a statement
about the central-50 clause, not about the window. It is not free everywhere:
on the six-state February 2024 plateau window used throughout the ledger
below, central-50 coverage falls from 0.698 to 0.646. The harness reported unchanged
coverage for the analogue member; that is a member result and does not
license a calibration claim about the ensemble, which is why the ensemble
figures are measured and stated here separately.

## The evidence ledger: what was tested and rejected

The rejections are part of the claim. The standing count at this tag,
2026-08-24, is eight
pre-registered challengers built, tested and rejected by this group, each by
its own rule set frozen before execution: random-walk transmission, the
two-strain SIHRS, national-growth coupling at two doses, a
reporting-completeness correction in two forms (cross-season and
within-season rolling), a regime-switching filter, adaptive transmission, and
slope-anchored transmission. One further candidate, a post-hoc global width
scalar, was tested and found null in an independent review of this work
rather than by us, and is reported below as such. One further proposal,
phase-conditional width scalars, was declined without being run. And one
challenger passed: donor-season composition in the analogue, which cleared
its pre-registered gates on 2026-08-24 and **is shipped**, documented in the
section immediately above rather than here. No challenger was rejected by
judgment after seeing its results.

The eight killed challengers appear as seven bullets below: the
reporting-completeness correction was two separately pre-registered
challengers and is kept in one bullet. The externally tested width scalar is
the eighth bullet.

The phase-conditional width scalars were declined on diagnostic evidence: the
diagnostic that motivated them showed the coverage error is indexed by
forecast week rather than by epidemic phase, and changes sign between the two
turns, so a static per-phase table could not represent it. That decision is
recorded here because declining to run an experiment on diagnostic evidence
is a different act from testing one, and the two should not be counted
together.

Addendum, 2026-08-29: a second proposal was declined without being run after
this document's 2026-08-24 amendment, a completeness-conditional same-day
drop (pre-registration edd6b0dddb8eb843, verdict in the lab archive). The
ledger therefore now records TWO proposals declined without running, keeping
the killed-vs-declined distinction drawn above.

**Read every number in this ledger as measured against the pre-exclusion
donor pool.** Each entry compares a challenger to the incumbent ensemble of
its day, whose reference figures were 0.7039 pooled and 0.8475 / 0.6513 /
0.6911 by season. Those comparisons have not been re-run against the shipped
pool, and for several challengers they cannot be: the harnesses and per-cell
results for random-walk transmission, national-growth coupling and the
regime-switching filter did not survive, as the archive manifest records.
Where a re-measurement was cheap and decisive it was made, and is noted in
the entry. Nothing below should be read as a comparison against the shipped
configuration.

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
  0.7039 (both on the pre-exclusion donor pool, whose two-member reference is
  now 0.6781; the three-member blend carries the analogue at one third, so it
  gains less from the donor change than the reference does and the kill is
  reinforced, but it has not been re-scored), because 46 of 52 jurisdictions
  carry thin or withheld typed
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
  season's intervals were already near-nominal. That premise was re-checked
  on the shipped pool: 2025-26 ensemble central-50 coverage is 0.477, having
  been 0.496, so the season's intervals remain the tightest of the three and
  the argument stands.
* **Global width scalar**, a post-hoc rescaling of predictive width. Tested
  and found null, a movement of about 0.3 percent, judged at the time
  against a quoted noise floor of roughly 5 percent. A caveat on that
  floor, added 2026-09-01: no measurement producing the 5 percent figure
  survives in this repository or the lab archive, so it should not be
  called measured, and the pre-registered kill gates that cite it inherit
  a constant of undocumented provenance. The run-to-run spread that is
  measured (lab archive, `replicate-count/out/spread.json`) is far
  tighter at the pooled full-grid scale: per-replicate sd 0.001 to 0.002
  relWIS. Against that measured floor a 0.3 percent pooled movement would
  not be null; whether the original test's movement was pooled-scale or
  small-panel-scale cannot be re-checked, for the provenance reason given
  below. The direction of the result remains consistent with the
  project-wide pattern that every post-hoc correction of the output has
  failed. **Provenance, stated plainly:** this test was performed during an
  independent review of the project rather than by this group, and no
  per-cell result or harness for it survives in our archive. It is reported
  as recorded and cannot be re-checked from our artifacts. Three of the eight
  challengers above and below are in the same position, for the same honest
  reason, and each says so in its own entry.
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
  That 0.271 is one of the few ledger figures that survives the donor change
  unchanged: the shipped ensemble covers the same 13 of those 48 cells.
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
  most of the way there. Of those two incumbent figures the January 0.271 is
  unchanged under the shipped donor pool, but the February 0.698 is not: the
  shipped ensemble covers 0.646 on that window, so a re-run of this challenger
  would be measured against a narrower incumbent than the one it beat. The
  kill clause is untouched either way. The mechanism control is the finding: an arm with
  momentum removed and the scale still fitted scored 0.6215 / 0.5818 / 0.6083
  against the full arm's 0.6230 / 0.5831 / 0.6097, about 0.2 percent apart,
  a gap read as null at the time against the same quoted 5 percent noise
  floor whose provenance the global-width-scalar entry above records as
  undocumented; the panel here is 1,711 cells, and the surviving measured
  spread (per-replicate sd 0.001 to 0.002 relWIS, pooled full grid) is the
  closest scoped figure on record. The increment structure contributes nothing
  measurable; the entire gain over RW-beta comes from fitting the innovation
  scale (0.055) instead of setting it by hand (RW-beta's 0.5).
* **Slope-anchored transmission.** Transmission derived from the last two
  vintage-true observations rather than inferred, with **zero added fitted
  parameters**. Pre-registration `5a895f3c02e06af1`; 1,530 influenza cells,
  no failures. The zero-dimension claim is proved rather than asserted: the
  run's own production forward reproduces the seal's stored particle filter
  to 1.2e-07. Killed on **two** clauses: **1b, per-cell WIS correlation with
  the incumbent filter, 0.978 against a bar of 0.85**, and **2b, January
  coverage 0.312 against a bar of 0.35**, the same number and the same bar
  that killed adaptive transmission. It passed the growth-correlation clause
  (0.892), turned on time, and was narrower than production everywhere. Two
  caveats are recorded against the kill rather than hidden: the incumbents
  would fail clause 1b too (the production filter against the analogue
  correlates 0.949, already above the bar), so that clause is probably
  measuring cell difficulty rather than member redundancy and should be
  redesigned before reuse; and the skill clause it passed on the selection
  seasons inverted on the held-out season (1.018), so the skill was not
  durable. On COVID the same member passed every clause that applied. That is
  a first pass on 27 cells, not a validation. The 0.949 in the first caveat
  involves the analogue and therefore moves with the donor pool; it was
  measured on that harness's own panel, which the seal does not reproduce, so
  it has not been re-derived here and no substitute is offered for it.

One entry is not a clean kill, and calling it one would overstate the
ledger. The **two-strain SIHRS passed** its pre-registered panel test on
2026-08-20, on both gates, and passed the epidemic-turn gate again at full
grid. It failed only the full-grid ensemble gate. It ships in the app,
labeled turn-validated but not ensemble-validated.

Three patterns from the ledger are worth stating as findings. First,
six-state panel results did not transfer to the 52-jurisdiction grid on two
separate occasions (RW-beta, two-strain gate 2); the full grid is the only
binding validation surface.

Second, fitted ensemble weights anti-predicted the held-out season every time
they were tried, and the unfitted 50/50 blend survived every challenge
mounted against it. Both halves of that hold on the shipped configuration,
with one qualification worth stating plainly: the challenge that finally
succeeded did not touch the blend at all, it replaced a member's donor pool.
The rule that survived is "do not fit the weights", not "do not change the
members". The re-measured comparison is 0.6958 for the frozen fitted table
against 0.6781 for the unfitted blend; the leave-one-season-out figure of
0.717 was recorded at the 2026-08-17 freeze and could not be re-derived,
because the fitting code does not survive.

Third, the January turn has a floor that nothing has broken. Three of the
nine candidates were aimed squarely at this defect, and none moved it past
0.312: the regime-switching filter left it at the incumbent's 0.271, while
adaptive transmission and slope-anchored transmission, arrived at from
opposite directions (one adding a fitted stochastic process, one adding no
parameters at all), both landed on exactly 0.312 against a bar of 0.35. Two
independent mechanisms reaching the same number is evidence about the defect,
not about either mechanism.

Those three are the whole of the evidence on this window, and the claim
should be read as covering them and no more. The remaining six challengers
carry no recorded January coverage figure at all, and for three of them
(random-walk transmission, national-growth coupling and the global width
scalar) none can now be produced, because the per-cell results did not
survive; their entries below say so. The tenth candidate,
the donor-pool exclusion, is the one that shipped, and it left the same
defect exactly where it found it: 13 of 48 cells covered before, 13 after.
The floor is a property of the defect and not of any one member.

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

This is the canonical list: interval narrowness at the January
epidemic turn (central 50 percent coverage of 27 percent at the January 2025
turn, re-measured on the shipped configuration and unmoved, unfixed by every
challenger, the best two of which reached 0.312 against a pre-registered bar
of 0.35); the shipped intervals are narrower than the pre-exclusion ones,
still above nominal pooled but 0.646 rather than 0.698 on the February 2024
plateau window; the adaptive MCMC engine does not pass convergence
diagnostics on this posterior and is not part of the shipped ensemble; all
scores are self-computed from the hub's archives rather than earned in
real-time participation; the placement of these forecasts among real FluSight
submissions is withdrawn and unmeasured; three seasons is the entire possible
vintage record, and the donor-pool exclusion is validated on those three
seasons and nowhere else; the sealed scores are computed on pre-floor
internal member forecasts at float precision rather than on the floored,
hub-rounded submissions the live console writes (measured at the third
decimal, see the seal caveats above); seven of the 76 sealed as-of weeks
consumed archive snapshots that diverge from submission-deadline knowledge
(see the seal caveats above); Windows is experimental.

## Naming

FluBNF 1.0 is a single-disease system. A COVID-19 feasibility study was
conducted and is recorded in the research archive; its mechanistic gates did
not pass. One later member, slope-anchored transmission, did pass every
COVID clause that applied to it, but on 27 cells: a first pass, not a
validation, and not a second disease. Any umbrella renaming is deferred
until a second disease clears its own validation gates.
