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
    prereg_sha256      the frozen document's hash
    bank.label         "admissions-fbase@<digest8>": the stream and the first eight
                       characters of the pool's content digest, the stamp the Groundhog
                       writes for its own bank ("flusurv@06eff6a7"); the manifest beside
                       the pool file carries the full digest and read_pool verifies it
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
ONLY, without copying it: the source switch at the top of the tab ("Oracle
SIHRS backfill"), or `/retro?src=oracle`. The directory is
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

## 6. The engine key

`pf_sampling_interval = 1` is written into a cell's pf.conf only when the
installed engine's own source accepts it: the quoted key must appear in
pybnf/parse.py (the grammar that refuses an unknown key) and in
pybnf/config.py (the pf key set), which the upstream tree a827e2f8 lists
and the engine before it does not. Never assumed; recorded per cell in
cells.json. That key is what lets the a827e2f8 tree fit a one-row .exp,
the first fitted week of a season.

## 7. Open items

* Bank change B2 is a registered switch of the stream name
  (`flubnf.oracle_bank.STREAM`, "admissions-fbase" today): the label every
  week records changes with it, and nothing else does. It is not made
  here; the pre-registration's rule is that no bank change of any kind is
  made after the freeze without its own registration.
* A one-row .exp (the first fitted week of a season) needs the engine key
  above on the a827e2f8 tree. The console now writes it wherever the
  installed engine accepts it; on an engine that does not, the first week
  is refused by the engine as before, and the shadow run starts at the
  first stored week.
