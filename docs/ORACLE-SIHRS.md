# The Oracle SIHRS

The mechanistic member the console submits as `NAU_PyBNF-OracleSIHRS`
(internal key `pf`, `app/core/submit.MODEL_ABBR`). It is the particle
filter exactly as it runs today, plus ONE post-fit step on the filter's
stored forward samples: each stored sample path has its growth replaced by
the geometric mean, at weight one half, of the filter's own origin growth
and one donor growth path drawn from a calendar-matched bank of past
seasons' admission growth. The step is fully specified by the frozen
pre-registration `PREREG_oracle_member_FROZEN.md` (research tree
`groundhog-beta/oracle_member`, version 2 with addendum A1, sha256
`67c9fa49a195908312f34ca783b21d85377759309df14461f86fbfd54d30c56f`), and
that hash is written into every week's provenance
(`flubnf.oracle.PREREG_SHA256`). Section numbers below are that
document's.

Since 2026-09-23 the member ships on the Groundhog's own donor bank (bank
change B2, section 5b): the admissions pool described in section 1 is one
half of it, unchanged, and a FluSurv-NET half is the other. Sections 1 to
5 describe the admissions half and the machinery both halves share.

Vocabulary of this repository: a MEMBER is one of the two models the
console submits (the Oracle SIHRS and the Groundhog); the ENGINE is the
particle filter in the PyBNF fork; the STORED WEEK is
`weeks/<T>/samples.json.gz` under a season root; the STORAGE BOUNDARY is
`app.core.retro.read_week_samples` / `write_week_samples`, where
`app.core.horizons` translates between the stored keys and the canonical
ones. The step touches none of those conventions.

## 1. What the member is (sections 3, 4.1, 4.2, 4.3 LB, 10.3)

For one cell (jurisdiction, as-of Saturday T) the filter's stored samples
are x_ih over the sample paths i, h = 1..4 the physical forecast weeks;
block "0" is the anchored origin. From the filter's own output alone:

    m_0   = median of the finite entries of the origin block
    m_h   = the 0.5 entry of the finite-only quantile vector of block h
    lam_T = ln(m_1 / m_0)     the filter's own first-week growth
    G_T   = gamma + lam_T     the filter's G at the origin instant, gamma = 7/3.2
    o_h   = ln(m_h / m_0)     the filter's own cumulated log path

A cell is eligible when m_0 > 0, m_1..m_4 > 0 and G_T > 0; no guard on the
size of lam_T (S3). A date is active when the week's donor pool is
admissible under the identity rule (below). On every cell that is not
active the member is the identity: the filter's samples untouched.

The donor pool (section 3, the FBASE rule of bank change B1) is built
from the week's own hub vintage file by `flubnf.oracle_bank`: for every
(location, week W) of a strictly earlier, non-excluded season within two
epiweeks of T's epiweek (the library's own donor rule,
`flubnf.analogue`), whose eight raw weeks W-1..W+6 are reported and
positive, whose four weeks W-1..W+2 are all at or above 10 admissions
(the window the origin stamp reads), every week of which lies in a
strictly earlier season (the season-crossing rule), with G_inst(W) > 0 and
finite midpoint stamps, the bank holds the origin stamp G_inst(W) and the
four midpoint stamps G_week(W+k), k = 1..4, from the centred three-point
smoother of the log counts. Fewer than two donor seasons or fewer than 30
paths is the identity rule (the 2023-24 targets, which have one donor
season). All rows are pooled across locations, the US row included.

Each stored sample path draws one donor path (one uniform per sample path
from numpy's default_rng on [seed, season index, T's ordinal, FIPS], d_i =
floor(u_i n)) and its four segment levels are the geometric blend

    ln G_k = w ln G_T + (1 - w) ln Ghat_d(W + k - 0.5),   k = 1..4,  w = 0.5.

The closed form of 4.2 under reading F (the filter's own state at T)
gives the cumulated log median path

    P_h(d) = lam_T - ln phi(lam_T) + sum_{i<h} lam_i(d) + ln phi(lam_h(d)),
    lam_k = G_k - gamma,  phi(x) = (exp(x) - 1) / x,

and the REPLACE factor F_h(d) = exp(P_h(d) - o_h) multiplies the stored
sample: x'_ih = x_ih F_h(d_i). The stored spread rides on the new median
path and the donor draw adds the donors' spread of level. Five seeds are
run (2026091801 to 2026091805, S14); the submitted quantiles are the first
seed's realisation and the other four are logged for the season-end
reading. The registered secondary weight, w = 0.25 (A1 (2)), is logged
beside the primary every week and ships nothing.

Where the code lives:

| what | where |
|---|---|
| the bank: estimators, the FBASE rule, the collector, the written pool and its manifest and digest | `flubnf/oracle_bank.py` |
| the member: cell quantities, the closed form, the draw, the transform, the quantiles | `flubnf/oracle.py` |
| the step at the storage boundary, the provenance, the plain-filter switch | `app/core/oracle.py` |
| the two call sites, right after `pf_engine.collect()` | `app/core/retro.run_week`, `app/ui/server._run_all` |
| the backfill and the reproduce | `app/core/oracle_backfill.py`, `flubnf oracle backfill`, `flubnf oracle reproduce` |

The step runs on the STORED filter samples after `collect()` and never
inside the engine; `app/core/engines/pf.py` is unchanged by it.

## 2. Horizons (A1 (4))

The library counts physical weeks; the app is canonical above the storage
boundary; the hub's rows carry FluSight horizons. The mapping, which every
week's oracle.json repeats:

| stored block | canonical key (app) | library week | FluSight horizon | target_end_date |
|---|---|---|---|---|
| "0" (the as-of week; m_0 is its median) | ORIGIN | origin | -1 | T (never a hub row) |
| "1" | "0" | 1 | 0 | reference_date |
| "2" | "1" | 2 | 1 | reference_date + 7 |
| "3" | "2" | 3 | 2 | reference_date + 14 |
| "4" | "3" | 4 | 3 | reference_date + 21 |

with reference_date = T + 7 days (`app.core.submit.hub_reference_date`,
the frozen join) and every hub-facing row produced by
`app.core.submit.quantile_rows` on the canonical dict, as before. The
stored convention is untouched: a backfilled root reads back through the
same boundary as every other.

## 3. How a week's provenance reads

Beside every stored week (`weeks/<T>/oracle.json`) and in every console
run's workroot, with the pool under `oracle_bank/` next to it:

    applied            true; "member": "Oracle SIHRS"; "reading": "F"; "transform": "REPLACE"
    prereg_sha256      the frozen document's hash; b2_sha256 and addendum_a2_sha256
                       beside it (section 5b)
    bank.label         "admissions-fbase@<digest8>+flusurv@<digest8>": the admissions
                       pool's content digest and the committed FluSurv-NET bank's, the
                       stamp the Groundhog writes for its own bank ("flusurv@06eff6a7");
                       bank.admissions and bank.flusurv carry each half's pool, digest,
                       counts and rule, bank.mixture the state and w_aux (section 5b);
                       the manifests beside the pool files carry the full digests and
                       the readers verify them
    vintage.sha256     the hub vintage file the pool was built from, and its newest row
    rule               FBASE: count floor 10 on W-1..W+2, path weeks W-1..W+6, bandwidth 2,
                       min donors 30, min donor seasons 2, the registered exclusions, the
                       identity rule, the season-crossing rule, the guards, gamma, the smoother
    w, w_secondary     0.5 and 0.25
    seeds              the five; submitted_seed 2026091801
    trimmed_weeks      k per location (from cells.json when the week has one, else the
                       spec) and where it came from; m_0 and y_T are compared per location
    cells              locations, eligible, active, the identity cells, the ineligible
                       cells, the US row (outside the registered member)
    locations.<name>   fips, eligible, active, k, m_0, y_T, m_0 / y_T, the medians m_h,
                       lam_T, G_T, sample counts, abstentions, guard hits, a reason
    quantiles          the NULL (the filter's own), the primary per seed and its seed
                       mean, the secondary per seed and its seed mean; keyed by FluSight
                       horizon "0".."3" with the library week beside each; unrounded

A week that ran the plain filter carries `applied: false` and the reason.
The console run's outcome and results.json carry the bank label under
`oracle`; the ledger's settings line reads "Oracle step".

## 4. The plain filter: a research run (the Groundhog precedent)

The un-informed filter is reachable the way the bare calendar analogue is
(`--aux none`): as a research arm with its submission withheld, not a
model tile, not a toggle, not on the site.

    flubnf retro 2026-27 --oracle none          a replay storing the plain filter under pf

For a console run, the run route accepts the field `oracle=none` (not on
the Forecast form; the re-run route passes what the ledger row recorded).
Under it the filter's own samples are stored as `pf`, the Oracle SIHRS
file is withheld with the reason in the outcome, the run is a research
run everywhere the ledger shows it and it never archives as the date's
forecast, and oracle.json says the step was not applied.

Under the default, every stored week also keeps the filter's own samples
beside the member under the research key `pf_filter` (a console run keeps
them as `pf_filter.json.gz` in the workroot). Nothing displays, scores or
exports that key; it is there so the paired comparison and the season-end
reading need no refit.

## 5. Backfill and reproduce

Compute the member for every stored week of a season root, from the
stored samples and no refit, into a NEW root:

    flubnf oracle backfill 2025-26 --source <season root> --out <new root>

The destination may not be the source, inside it, inside the repository's
app/state (the sealed and live trees) or a non-empty tree (unless
`--force`). Each week is read through the storage boundary and written
back through it: `pf` the member, `pf_filter` the source's pf verbatim,
`analogue` verbatim, the sidecar, oracle.json (with the source file's
sha256 folded in) and the pool. The hub the process reads (FLUBNF_HUB)
supplies the vintages.

Score a backfilled root with the app's own scorer and print relWIS beside
the screen's tables:

    flubnf oracle reproduce <new root>/2024-25 <new root>/2025-26 \
        --source <grid>/2024-25 --source <grid>/2025-26 \
        --screen <screen>/screen_scores.json

The scorer is `app.core.retro.score_season` (the same cell rule and
baseline construction every console figure uses), pooled through
`app.core.us_national.pooled_frame`; the numbers are printed per season
and over the seasons together on the record definition (each member on its
own scored cells) and on the common set (cells where both stored members
scored), each with its cell count. `--source` scores a source root for
the NULL only when every week's sidecar is current, so the source is never
written. FLUBNF_HUB must be the hub whose truth and baseline files the
screen used.

The record, 2026-09-22: the stored grid kernel-regularizer/grid/J15 (the
screen's own surface) backfilled for 2024-25 (27 weeks) and 2025-26 (26
weeks) and scored against the pinned hub copy the screen used. relWIS,
ratio of WIS sums against the FluSight baseline, US excluded; the stored
member is the submitted seed's realisation, so the screen's seed-1 value
is the one to match and its seed mean is beside it:

| scope | cell set | Oracle SIHRS | cells | screen LB seed 1 | screen LB seed mean | plain filter | cells | screen NULL | grid's calendar analogue | cells |
|---|---|---|---|---|---|---|---|---|---|---|
| 2024-25 | common | 0.7192 | 4,859 | 0.7192 | 0.7192 | 0.7944 | 4,859 | 0.7944 | 0.7561 | 4,859 |
| 2024-25 | record definition | 0.7192 | 4,859 | 0.7192 | | 0.7944 | 4,859 | | 0.7560 | 4,922 |
| 2025-26 | common | 0.7740 | 4,420 | 0.7740 | 0.7741 | 0.8426 | 4,420 | 0.8426 | 0.6180 | 4,420 |
| 2025-26 | record definition | 0.7740 | 4,420 | 0.7740 | | 0.8426 | 4,420 | | 0.6180 | 4,475 |
| both (active2) | common | 0.7409 | 9,279 | 0.7409 | 0.7409 | 0.8135 | 9,279 | 0.8135 | 0.7014 | 9,279 |
| both (active2) | record definition | 0.7409 | 9,279 | 0.7409 | | 0.8135 | 9,279 | | 0.7013 | 9,397 |

The last two columns are the grid's own second member, stored under
`analogue` and copied verbatim by the backfill: the bare calendar analogue
WITHOUT the FluSurv-NET donors (the grid ran no auxiliary preset; its
figures are the retired bare analogue's 0.756 and 0.618 on the console's
Methods page), not the shipped Groundhog, whose own record (0.653 and
0.651) is its separate replay. The filter's scored cells are a subset of
the analogue's, so the record definition and the common set coincide for
the mechanistic member (the
screen's 9,279 common cells on active2; its 15,300 native cells include
the 2023-24 identity season, not backfilled here). The Oracle SIHRS
equals the screen's seed-1 value to machine precision on every scope and
the plain filter equals the screen's NULL likewise; the screen's pooled
figures with 2023-24 (LB 0.7610, NULL 0.8188 on 15,300 cells) are the
same numbers with the identity season added. The 2024-25 and 2025-26
seasons are 24 and 22 scored as-of dates; the three dates of each season
without a FluSight-baseline file score no cell, as on the screen.

### Backfill, then view it in the console

The backfill refuses `app/state` on purpose, so a backfilled season lives in
a directory of its own. The Retrospective tab shows such a directory READ
ONLY, without copying it: the source switch at the top of the tab
("Oracle SIHRS backfill"), or `/retro?src=oracle`. The directory is
`app/state/retro_oracle` by default (gitignored with the rest of
`app/state`), or any directory named by `FLUBNF_RETRO_ORACLE`, read when
the page is served. A directory that is, contains or lies inside the
console's own trees (`app/state/retro`, `retro_seal`, `retro_reseal`) is
refused and nothing is read from it.

    # 1. backfill each season into the source directory
    flubnf oracle backfill 2024-25 --source <grid>/2024-25 --out <dir>/2024-25
    flubnf oracle backfill 2025-26 --source <grid>/2025-26 --out <dir>/2025-26

    # 2. start the console with the source named (or use the default,
    #    app/state/retro_oracle, as <dir>)
    FLUBNF_RETRO_ORACLE=<dir> flubnf app

    # 3. Retrospective tab -> "Oracle SIHRS backfill" -> a season -> Results

The index lists every season under the directory with its backfilled weeks
and the stored filter samples it came from; a season's page is the same
results page every replay gets (head tiles, cumulative curve, per-state
table, the season player, the map, the season report), every link and
fetch carrying `src=oracle`, with a banner naming the directory, the source
root, the pre-registration hash and what the second member is: the
backfill copies the source's analogue verbatim, so over the stored grid it
is the bare calendar analogue, not the shipped Groundhog, and the banner
says so. Nothing that writes (run, pause, stop, start over, archive,
delete) takes the source. Opening a season for the first time scores it
with the app's own scorer: the derived caches every season root gets
(`scores.json`, the national aggregate, the playback and map caches) are
written beside its weeks, and the weeks themselves are never touched;
`app.core.reclaim` protects the directory, so no finalize prune or storage
sweep reaches them. Point FLUBNF_HUB at the hub whose truth the record was
scored against (the pinned copy for the numbers above) to reproduce them
on the page.

## 5b. The shipped donor bank (bank change B2, addendum A2)

The lead decided on 2026-09-23 to ship the member on the Groundhog's own
donor bank: `PREREG_oracle_member_ADDENDUM_A2.md` (sha256
`85ac546416bbb20ed1b87ce9289f50645ff1e22169b0bed9ae0a054e3e449f27`,
`flubnf.oracle.ADDENDUM_A2_SHA256`, a separate file so the frozen
document's hash does not move) records it, for the member that
`b2/PREREG_b2_FROZEN.md` specifies (sha256
`2ce3564622296f490a435b773a3b34d431d889b3e0d4fe4b32ff6aeb8ede9249`,
`flubnf.oracle.B2_SHA256`, every blank at its printed recommendation). All
three hashes are written into every week's oracle.json. The member is
called LBGH in the research record; the hub model name does not change.

The bank (`flubnf/oracle_mix.py`, stream `admissions-fbase+flusurv`):

* The ADMISSIONS HALF is the pool of section 1, unchanged: the FBASE rule
  on the week's own hub vintage.
* The FLUSURV-NET HALF is the committed bank the Groundhog splices,
  `data/banks/flusurv.json`, read by `flubnf.bank.read`, which verifies the
  content digest (06eff6a7) and raises on a mismatch. Its donor cells are
  the Groundhog's shared selection, `flubnf.analogue.donor_paths(...,
  length=6, with_keys=True)` over `_donor_cells` (strictly earlier season,
  the registered exclusions, within two epiweeks with week 53 at 52.5, six
  forward cells present by date arithmetic); a path then also needs its
  W-1 cell (the smoother reads it), the season-crossing rule and the
  guards. There is no count floor (a rate per 100k has none); the three
  network aggregates and the two New York sites are donors, as the
  Groundhog treats them. The stamps are the admissions half's smoother
  (`flubnf.oracle_bank.estimate_G`) on the location's weekly rate series,
  at the path table's five decimals. A half is admissible with at least
  30 paths.
* THE SHRINK. The FluSurv-NET growth is scaled by the Groundhog's own
  factor, `flubnf.analogue.fit_log_ratio_shrink` fitted for the target
  season on the week's own admissions vintage (the engine's shrink =
  "auto"), applied as G' = gamma + shrink * (G - gamma). It moves a little
  with the vintage: 0.861 to 0.864 on 2023-24 targets, 0.977 to 0.980 on
  2024-25, 0.974 on 2025-26. A shrink that cannot be fitted raises.
* THE MIXTURE. Identity rule R_EITHER: the week is active when either
  half is admissible; w_aux, the chance a sample path's donor comes from
  the FluSurv-NET half, is 0.5 when both are, 1 when only the FluSurv-NET
  half is, 0 when only the admissions half is. The draw uses a SECOND
  uniform stream on the frozen generator: sample i keeps its admissions
  donor floor(u_i n_adm) unless v_i < w_aux, in which case it draws the
  FluSurv-NET path floor((v_i / w_aux) n_aux). Half of every cell's samples
  therefore carry exactly the admissions-only member's donor, and that
  member is recovered bitwise at w_aux = 0.

On the record's 85 as-of dates both halves are admissible on 52, the
FluSurv-NET half alone on 28 (2023-24 up to the end of March: only one
earlier NHSN season, 2022-23, is admissible there), the admissions half
alone on one (2025-06-14, unscored), and neither on the four April dates
of 2023-24, where the step leaves the filter unchanged. On the two active
seasons the admissions half holds 117 to 748 paths per week and the
FluSurv-NET half 23 to 1,090.

The week's provenance (section 3) records the bank label
`admissions-fbase@<pool digest8>+flusurv@06eff6a7`, both halves' pool
sizes and digests (the FluSurv-NET table is written beside the admissions
one as `oracle_bank/flusurv_paths_<T>.csv` with its manifest), the shrink
and the seasons it was fitted on, the mixture state and w_aux, per
location its state and how many samples drew a FluSurv-NET path, and per
seed the shipped member, the registered w = 0.25 secondary on the same
bank, and the admissions-only member (LB), logged beside them as
addendum A2 (2) asks. The plain filter stays reachable as the research
option `oracle = none`.

Bitwise against the B2 screen (`b2/results/arms_by_date`), run
2026-09-23 on every one of the 85 record dates from the stored grid
samples and the pinned hub vintages: the library's FluSurv-NET pools equal
the screen's written pools by content digest and file bytes, every count
of `calibration_b2.json` and the 85 shrink values exactly; the member per
seed equals the screen's LBGH on 88,400 (seed, location, horizon) blocks
and its LB25GH on 88,400, 0 differing; the admissions-only member equals
the B2 screen's reproduction on 88,400 blocks and the frozen screen's LB
and LB25 on 47,840 blocks each (the 46 dates it stored), 0 differing; the
mixture at w_aux = 0 equals the admissions-only member on 55,120 blocks.
The 1,682 cells that have six forward cells but no W-1 cell (summed over
the 85 dates) are exactly the difference between the shared selection's
six-week paths and the eight-week path; the selection itself agrees with
the screen's own loop on every date. `tests/test_oracle.py` and
`tests/test_oracle_mix.py` keep a subset of dates in the suite;
`FLUBNF_ORACLE_FULL=1` runs all of them.

The numbers, from the B2 screen (`b2/results/screen_b2_scores.json`,
common cells, relWIS against the FluSight baseline as a ratio of WIS sums,
US excluded, seed mean over the five seeds):

| scope | cells | Oracle SIHRS (shipped bank) | admissions-only member | plain filter |
|---|---|---|---|---|
| 2023-24 | 6,021 | 0.7667 | 0.8395 (the identity) | 0.8395 |
| 2024-25 | 4,859 | 0.6975 | 0.7192 | 0.7944 |
| 2025-26 | 4,420 | 0.7813 | 0.7741 | 0.8426 |
| 2024-25 and 2025-26 (active2) | 9,279 | 0.7307 | 0.7409 | 0.8135 |
| three seasons (pooled3) | 15,300 | 0.7380 | 0.7610 | 0.8188 |

The shipped bank against the admissions-only one (claim B2-1, active2):
-0.0103, reading interval
-0.0289 to +0.0084, UNRESOLVED; by
season -0.0217 in 2024-25 and +0.0072 in 2025-26, the advantage
concentrated on five December and January dates (without them the sign
flips). In 2023-24 the member is active for the first time: -0.0728
against the plain filter, UNRESOLVED. Against the shipped Groundhog on the
same cells (0.6524 on active2) the member remains worse, +0.0782 (reported
only). THE CAVEAT that travels with every figure: choosing this bank over
the admissions-only one was the lead's decision (addendum A2) on a screen
that did not resolve it, 0.7307 against 0.7409 with an interval that
includes zero, taken on the pooled and by-season point estimates, the
2023-24 coverage the admissions-only member cannot provide, and the wish
to give the Oracle SIHRS the Groundhog's donor information. The screen is
a frozen-specification replication on seasons the family had been looked
at on; the 2026-27 season is the prospective test, and its shadow run
logs the shipped member first with the admissions-only member, the w =
0.25 secondaries and the calendar placebos beside it.

Reproduced with the app's own scorer, 2026-09-23: the three seasons
backfilled with the shipped bank from the stored grid (`flubnf oracle
backfill <season> --source <grid>/<season> --out <dir>/<season>`, 32, 27
and 26 weeks) and scored against the pinned hub copy the screen used by

    flubnf oracle reproduce <dir>/2023-24 <dir>/2024-25 <dir>/2025-26 \
        --source <grid>/2023-24 --source <grid>/2024-25 --source <grid>/2025-26 \
        --screen <b2>/results/screen_b2_scores.json

(given the B2 screen's file, the reproduce prints its LBGH tables beside
its own). The stored member is the submitted seed's realisation, so the
screen's seed-1 value is the one to match:

| scope | Oracle SIHRS, common | cells | record definition | cells | screen LBGH seed 1 | screen LBGH seed mean | plain filter | cells | grid's calendar analogue, record | cells |
|---|---|---|---|---|---|---|---|---|---|---|
| 2023-24 | 0.7668 | 6,021 | 0.7668 | 6,021 | 0.7668 | 0.7667 | 0.8395 | 6,021 | 1.0449 | 6,063 |
| 2024-25 | 0.6975 | 4,859 | 0.6975 | 4,859 | 0.6975 | 0.6975 | 0.7944 | 4,859 | 0.7560 | 4,922 |
| 2025-26 | 0.7811 | 4,420 | 0.7811 | 4,420 | 0.7811 | 0.7813 | 0.8426 | 4,420 | 0.6180 | 4,475 |
| active2 | 0.7306 | 9,279 | 0.7306 | 9,279 | 0.7306 | 0.7307 | 0.8135 | 9,279 | 0.7013 | 9,397 |
| three seasons | 0.7380 | 15,300 | 0.7380 | 15,300 | 0.7380 | 0.7380 | 0.8188 | 15,300 | 0.7714 | 15,460 |

The Oracle SIHRS equals the screen's seed-1 value to machine precision on
every scope (differences at most 3.3e-16) and the plain filter the
screen's NULL likewise; the seed mean differs by the seed noise (at most
2.2e-4, in 2025-26). The member's scored cells equal the filter's, so its
record definition and the common set coincide (6,021 + 4,859 + 4,420 =
15,300). The last two columns are the grid's own bare calendar analogue,
copied verbatim by the backfill, not the shipped Groundhog.

To look at the backfilled seasons in the console, start it with the
directory named (nothing is configured permanently; the backfill is not
under app/state) and open the Retrospective tab's backfill view:

    FLUBNF_RETRO_ORACLE=<dir> flubnf app      # then /retro?src=oracle

as "Backfill, then view it in the console" in section 5 describes.

## 6. The engine key

`pf_sampling_interval = 1` is written into a cell's pf.conf only when the
installed engine's own source accepts it: the quoted key must appear in
pybnf/parse.py (the grammar that refuses an unknown key) and in
pybnf/config.py (the pf key set), which the upstream tree a827e2f8 lists
and the engine before it does not. Never assumed; recorded per cell in
cells.json. That key is what lets the a827e2f8 tree fit a one-row .exp,
the first fitted week of a season.

## 7. Open items

* Bank change B2 ships on this branch (section 5b): the member's donor
  bank is the Groundhog's, the admissions pool plus FluSurv-NET at weight
  0.5 as a per-sample mixture (`flubnf.oracle_mix`, stream
  "admissions-fbase+flusurv"; the admissions half keeps
  `flubnf.oracle_bank.STREAM`, "admissions-fbase"). Its screen did not
  decide it: the primary claim is UNRESOLVED (the mixture member minus the
  admissions-only member on the 2024-25 and 2025-26 active dates -0.0103,
  95 percent reading interval -0.0289 to +0.0084; 0.7307 against 0.7409),
  and shipping it is the lead's decision of 2026-09-23 (addendum A2). The
  2026-27 shadow run logs the admissions-only member beside the shipped one
  every week and reads the two against each other at season end.
* A one-row .exp (the first fitted week of a season) needs the engine key
  above on the a827e2f8 tree, which refuses one row without it. The
  console writes it wherever the installed engine accepts it. The engine
  before that tree (2fdadee0) does not accept the key and does not need
  it: it takes a one-week interval when the file has one row.
