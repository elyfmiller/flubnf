# The donor banks: what they are and how to reuse them

Written 2026-09-22 for the team building the Oracle SIHRS, so that the
mechanistic model can draw on the same past-season surveillance the
Groundhog draws on. Everything here is read off the code and the committed
banks at that date, and two independent checkers then tried to refute every
claim against the code; what they found is folded in. File and function
names are the ones to grep for. Where the Groundhog made a choice that a
mechanistic reuse need not share, the section says so.

## 1. Two banks, one shape

A donor bank is a flat mapping `(location, date) -> value`, where `location`
is a lowercase string, `date` is a `datetime.date` and always the Saturday
that ends an MMWR week, and `value` is positive (the stream builders drop
non-positive values; `donor_ratios` additionally requires a finite one, and
the committed banks are all finite). Two banks are committed under
`data/banks/`, each as a one-line JSON file keyed `"<location>|<YYYY-MM-DD>"`
plus a manifest:

| stream | file | cells | locations | span | source |
|---|---|---|---|---|---|
| `flusurv` | `data/banks/flusurv.json` | 8,020 | 22 | 2009-09-05 to 2026-08-08 | Delphi `flusurv`, field `rate_overall` |
| `iliplus` | `data/banks/iliplus.json` | 16,000 | 48 | 2016-10-08 to 2026-09-12 | Delphi `fluview` and `fluview_clinical` |

Both were built on 2026-09-21. The manifest (`<stream>.manifest.json`)
records `stream`, `layout_version`, `builder`, `cells`, `location_count`,
`locations`, `span`, `source_url`, `built_utc` and a `digest`: sha256 over
the content lines `"<loc>|<date>=<repr(float)>\n"` in sorted order, so the
digest identifies the data, not the file bytes. Current digests:
`flusurv@06eff6a7...`, `iliplus@f6ee2840...`. Two things the manifest does
NOT record: the build arguments (as-of, `percent_positive` mode, first
season), which are `bank.build_from_source`'s defaults and are stated in
sections 2 and 3; and, for ILI+, the second endpoint (`source_url` names
only `fluview`, though the clinical half comes from `fluview_clinical`).

What the banks hold, by season (season labels per section 4):

| stream | seasons present | notes |
|---|---|---|
| `flusurv` | 2009-10 to 2025-26 except 2020-21, plus 13 current-season cells | no 2020-21 cells at all (nothing between 2020-04-25 and 2021-10-09); 2011-12 is thin (304 cells against 437 to 695 elsewhere); mostly in-season, May to September cells only in 2009, 2022, 2024 and 2026 plus a handful in 2010 and 2015 |
| `iliplus` | 2016-17 to 2025-26, plus 173 current-season cells | 2020-21 present (556 cells) |

Both banks therefore carry CURRENT-SEASON cells as latest-issue data. A
level-based reuse that does not filter to strictly prior seasons is
reading revised current-season values; section 2's vintage argument does
not cover that.

Read a bank with

```python
from flubnf import bank
b, manifest = bank.read("iliplus")     # or "flusurv"
```

`read` recomputes the digest and raises (`FileNotFoundError`, `ValueError`)
on a missing file, a missing manifest or a mismatch. It never falls back to
an empty bank. `flubnf bank build <stream>` (`--out <dir>`) rebuilds from
source, rewrites both files, prints an added/removed/revised comparison
against the previously committed bank and reminds you to git-commit both
(it does not ask first); `flubnf bank verify <stream>`
(`--banks <dir>`) rebuilds and exits non-zero on drift; `flubnf bank show
<stream>` prints the manifest. A
rebuilt and committed bank changes the digest, and the digest is part of
every run record that used it (section 6), which is the point.

## 2. What ILI+ is

`flubnf/iliplus.py`. Per state and week,

    ILI+ = ILINet percent ILI  x  clinical percent positive

with the ILINet half from Delphi `fluview` (`wili`, falling back to `ili`;
for a state the two are identical) and the clinical half from Delphi
`fluview_clinical`. With an as-of the clinical half comes through
`flubnf.nrevss.fetch_typed` (vintage-true); the COMMITTED bank is built
without one and takes it through `iliplus._latest_typed` (latest issue,
cached under `app/state/nrevss/<region>_latest.json`). Percent positive is
DERIVED as `(total_a + total_b) / total_specimens * 100`, not read from
Delphi's rounded `percent_positive` field; `build_bank(...,
percent_positive="reported")` uses the rounded field and exists only to
reproduce the bank the pre-registered measurements were made on. The stored
value is percent times percent (3.0 percent ILI at 25 percent positive
stores 75.0). The Groundhog only ever takes ratios of it, so the units never
matter there; they matter the moment a level is used.

Regions requested are every FluSight jurisdiction except the national row
(ILINet's national value is a weighted average, not a sum). A week is kept
only when both halves exist for the same Saturday, `total_specimens >= 1`
and the product is positive; there is deliberately no HHS-region fallback
(unlike `nrevss.a_share_series`, which the Oracle SIHRS side uses for typed
shares). Four jurisdictions are absent from the bank: `ny` and `ri` return
no `fluview_clinical` rows at all, and `dc` and `pr` return rows whose
`total_specimens` is zero throughout, so the `>= 1` rule drops them. All
four have full ILINet halves.

Vintage: `iliplus.build_bank(season_start_iso, asof_iso)` is vintage-true
when given an as-of (it requests `issues=<epiweek>` with a two-issue
holiday fallback), but the COMMITTED bank is a latest-issue snapshot
(`asof=None`). That was measured to be safe for the Groundhog: with donors
drawn only from strictly prior seasons, the youngest donor is 46 weeks old,
and 98.0 percent of cells are bit-identical between a lag-46 vintage and
the final issue, with the arm's relWIS unchanged (pre-registration
08e03ca7e8ffcfce). The equivalence holds only for that use. A model that
reads current-season ILI+ from the bank is reading revised data.

## 3. What FluSurv-NET is

`flubnf/flusurv.py`. Delphi `flusurv`, field `rate_overall`: weekly
laboratory-confirmed influenza hospitalisations per 100,000 in the
FluSurv-NET catchments. The 22 location codes are Delphi's own label list,
lowercased and used verbatim: 17 coincide with FluSight jurisdictions
(`ca co ct ga ia id md mi mn nm oh ok or ri sd tn ut`), New York appears as
`ny_albany` and `ny_rochester`, and three are network aggregates
(`network_all`, `network_eip`, `network_ihsp`) that the code does not treat
specially: they are ordinary donor locations, and they are not independent
of the sites they aggregate (18.7 percent of the bank's cells).

There is no vintage: the endpoint keeps no revision history, `build_bank`
takes no as-of, and the engine raises if one is asked for. The series runs
from the 2009-10 season. The bank holds fifteen usable donor seasons
(2009-10 to 2025-26 is seventeen; 2020-21 is absent from the source
entirely, and 2021-22 is excluded, section 5) against ILI+'s eight; the
admissions archive that both are blended with begins 2022-02-05. The stream
is mostly in-season: May to September cells exist only in 2009 (the
pandemic), 2022, 2024 and 2026, with a handful in 2010 and 2015, so it
cannot generally supply off-season donors or a full-year curve.

A caution the Oracle SIHRS side already carries (`flubnf/sihrs_priors.py`):
FluSurv-NET rates are a different quantity from NHSN admissions. On 2024-25
the NHSN-derived national median was 153.0 per 100k against FluSurv-NET's
127.1, an ascertainment ratio of 1.20, so the rate must not calibrate the
reporting multiplier of the SIHRS compartment model. The Groundhog
sidesteps this by using growth ratios only.

## 4. Calendar conventions

Every bank date is an MMWR week's Saturday. `flubnf.nrevss.mmwr_week` and
`flubnf.analogue.epiweek` are two independent MMWR implementations (weeks
Sunday to Saturday, week 1 holds January 4); the bank builders cross-check
them on every cell. MMWR years 2014, 2020 and 2025 have 53 weeks. The
FluSurv-NET bank carries the week-53 Saturdays `2015-01-03` and
`2026-01-03` (not `2021-01-02`: it has no 2020-21 season); the ILI+ bank
carries `2021-01-02` and `2026-01-03` (its span starts 2016-10-08).
`2026-01-03` was the 2025-26 peak week, so the seam is not academic.

`season_of(d)` labels a season by its starting year with a 1 August boundary
(`SEASON_BOUNDARY_MONTH = 8`): 2025-08-02 is season 2025, 2026-04-04 is
season 2025.

`calendar_distance(a, b)` is the circular distance between epiweeks with
week 53 seated at 52.5, so `distance(53, 52) == distance(53, 1) == 1`. A
donor week is matched by this distance; a donor's FUTURE value is read by
date arithmetic, `bank[(loc, d + 7 * horizon days)]`, never by week label.
`tests/test_epiweek53.py` pins both.

## 5. Donor selection: the primitive to reuse

```python
from flubnf.analogue import (donor_ratios, epiweek, season_of,
                             resolve_donor_exclusions, MIN_DONORS,
                             DEFAULT_BANDWIDTH, EXCLUDED_DONOR_SEASONS)

ratios = donor_ratios(b, epiweek(asof), season_of(asof), horizon,
                      bandwidth=DEFAULT_BANDWIDTH,
                      exclude_seasons=EXCLUDED_DONOR_SEASONS)
```

For a target (as-of week, horizon in PHYSICAL weeks 1 to 4) this returns
one array of growth ratios `v(d + 7h) / v(d)`, taken from every cell `(loc,
d)` in the bank that satisfies all of:

* `season_of(d) < season_of(asof)`: strictly prior seasons. The
  `allow_same_season` flag exists so a test can demonstrate leakage and is
  never True in production.
* `season_of(d)` not in the exclusion set (below).
* `calendar_distance(epiweek(d), epiweek(asof)) <= bandwidth`, inclusive,
  so at `DEFAULT_BANDWIDTH = 2` five epiweeks per location per season (six
  where the window straddles week 53 of a 53-week donor season, since week
  53 sits at 52.5).
* both `v(d)` and `v(d + 7h)` present, finite and positive.

Donors are pooled across every location in the bank. A location key is used
only to find a cell's own future value, which is why a 22-site FluSurv-NET
bank, a 48-state ILI+ bank and the FIPS-keyed admissions bank can be
combined without any location mapping between them; equally, nothing in the
repository maps a stream's locations onto FluSight jurisdictions, and a use
that needs per-jurisdiction LEVELS from these banks would have to build one.

`donor_ratios` itself applies no floor: it returns whatever it finds, an
empty array included. The abstention (`None`, never a thin forecast) is
enforced at `MIN_DONORS = 30` in `analogue_quantiles` and
`spliced_quantiles`, reached through `forecast()`. A reuse that calls
`donor_ratios` directly must enforce the floor itself.

### Growth paths: the same donors as trajectories

```python
from flubnf.analogue import donor_paths

paths = donor_paths(b, epiweek(asof), season_of(asof), length=6)
paths, keys = donor_paths(b, epiweek(asof), season_of(asof), length=6,
                          with_keys=True)
```

`donor_paths` selects from exactly the cells `donor_ratios` selects: the
first three rules above and the anchor half of the fourth live in one
shared helper, `_donor_cells`, so the two cannot disagree about the pool.
The future-cell half of the fourth rule is where they differ by design:
`donor_ratios` needs the one cell at `h`, `donor_paths` keeps a donor only
when every one of its `length` future cells is present, finite and
positive, and returns one row per donor, `v(d + 7k) / v(d)` for k = 1 to
`length`. Column k-1 is therefore a
subset of `donor_ratios(..., k)`, and at `length=1` the two are identical,
order included. The shape is `(n, length)`, `(0, length)` when nothing
qualifies; `with_keys=True` also returns each row's `(loc, d)` so a caller
can weight or group donors by `season_of(d)`. Future values are read by
date arithmetic, so the week-53 seam is handled. Like `donor_ratios` it
applies no floor. The ratios are on the bank's own scale; to put them on
another stream's scale apply `fit_log_ratio_shrink` in log space (section
6). `tests/test_donor_paths.py` pins these properties on a synthetic bank,
pins four cells of the table below on the committed banks, and pins
`donor_ratios` byte for byte at four points on the committed banks across
the refactor (an independent full-grid comparison against main, 118,720
calls, found no difference).

What the committed banks can supply as complete paths (target season 2026,
default exclusions and bandwidth):

| epiweek | FluSurv-NET, 4 weeks | FluSurv-NET, 6 weeks | ILI+, 4 weeks | ILI+, 6 weeks |
|---|---|---|---|---|
| 48 | 1,067 | 1,048 | 1,543 | 1,536 |
| 2 | 1,202 | 1,192 | 1,674 | 1,658 |
| 6 | 1,204 | 1,179 | 1,613 | 1,587 |
| 10 | 1,145 | 889 | 1,529 | 1,407 |
| 14 | 501 | 142 | 1,267 | 1,099 |
| 18 | 110 | 83 | 929 | 739 |

Mid-season the completeness requirement costs almost nothing. From epiweek
10 the FluSurv-NET paths thin out, because that stream has almost no May to
September cells (section 3), while ILI+ holds up; a late-season use draws
paths from ILI+ or accepts the smaller pool, and says which.

`DEFAULT_BANDWIDTH = 2` is the value the sealed record ran at, inherited
rather than selected on the current pipeline (the provenance comment above
it in `flubnf/analogue.py` says so). Changing it invalidates every sealed
number; it is the lead's decision, not a tuning knob.

### Registered donor-season exclusions

A season leaves the pool only through a `DonorSeasonExclusion` record in
`DONOR_SEASON_EXCLUSIONS`, carrying its pre-registration hash, mechanism,
measured effect and depth control. Two are registered, and
`EXCLUDED_DONOR_SEASONS` (the default) is `{2020, 2021}`:

* **2021-22** (`SEASON_2021_22_CALENDAR_INVERSION`, prereg
  8f3c7a45a989e905, adopted 2026-08-24): calendar inversion. The season
  peaked at epiweek 16 (2022-04-23), and the admissions archive begins
  2022-02-05, so it holds only that season's February to July tail. Asked
  what happens in March, 2021-22 is the only donor season whose ratios
  have a median above one, so a calendar-matched pool reads it with the
  wrong sign.
* **2020-21** (`SEASON_2020_21_SUPPRESSED`, prereg 086bda9a0736e983,
  adopted 2026-09-19): the NPI-suppressed season. The record's figures are
  an ILI+ in-season median of 0.2855 against 3.78 to 67.07 in every other
  season, measured on the earlier `percent_positive="reported"` bank; the
  committed derived bank gives 0.2832 against 3.78 to 67.08, the same
  conclusion.

Where each record bites: the admissions bank has no data before 2022-02-05,
so only 2021-22 touches it. The committed FluSurv-NET bank has no 2020-21
cells at all, so there too only 2021-22 is removed (518 cells). The 2020-21
record bites the ILI+ bank alone (556 cells); the registry's own effect
text says "Auxiliary ILI+ pool only", and `tests/test_analogue.py` pins it.
A reuse that assembles its own donor set from `iliplus` without going
through `resolve_donor_exclusions` silently admits the suppressed season,
and from either bank silently admits 2021-22. Pass `()` to
`exclude_seasons` only to reproduce pre-exclusion figures.

## 6. How the Groundhog splices an auxiliary pool

`flubnf/analogue.py`, `AuxPool` and `DonorSplice`; the engine wrapper is
`app/core/engines/analogue.py`.

1. The admissions bank gives the primary ratio pool, the auxiliary bank
   gives a second pool through the same `donor_ratios` call (its own
   exclusions, an optional bandwidth override).
2. The auxiliary log ratios are shrunk toward the admissions scale:
   `a -> exp(shrink * log a)`, with `shrink =
   sd(admissions in-season log ratios) / sd(auxiliary in-season log ratios)`
   (`fit_log_ratio_shrink`), computed over horizons 1 to 4 on the seasons
   BOTH banks carry that are strictly prior to the target season and not
   excluded, restricted to the in-season window epiweek >= 47 or <= 20. It is
   a distribution-matching factor, not a regression slope. The engine fits it
   per run (`shrink="auto"`) from the untrimmed forecast date's season and
   raises if it cannot; there is no fitted constant in the code, and the
   factor moves with the target season because the shared prior seasons
   do. On the committed banks against the hub vintages:

   | target season | FluSurv-NET | ILI+ |
   |---|---|---|
   | 2023-24 | 0.861 | 0.761 |
   | 2024-25 | 0.980 | 0.834 |
   | 2025-26 | 0.974 | 0.816 |

   The 0.979 and 0.820 quoted in `flubnf/flusurv.py` are one season's
   fit. FluSurv-NET is close to the admissions scale from 2024-25 on and
   noticeably wider on 2023-24.
3. The two ratio quantile FUNCTIONS are vincentized level by level:
   `q(L) = w0 * Q_admissions(L) + sum_i w_i * Q_aux_i(L)`, `w0 = 1 - sum w_i`.
   The shipped weight is 0.5 for one pool. This is a quantile average, not a
   concatenation of donors, which would weight pools by their donor counts;
   `app/tests/test_analogue_splice.py` asserts the two differ.
4. Every pool must clear `MIN_DONORS` on its own or the forecast abstains.
5. The anchor scales the blended ratio quantiles. The anchor is the last
   reported value AFTER the engine's per-location trims (`weeks_to_drop`,
   and `drop_same_day`, off by default), and the ratios are then read at
   `h + k` weeks past the trimmed anchor; a reuse reproducing the engine's
   arithmetic needs the trims, the shrink fit does not (it uses the
   untrimmed forecast date).

Selected arm: FluSurv-NET at weight 0.5 (`SHIPPED_AUX = "flusurv"`). The
arm selection is C1 of pre-registration ea72d194af8318a5 (chosen over ILI+
on calibration and on leave-one-donor-season-out stability, spread 0.0266
against 0.0576, with skill inside the bootstrap noise of the alternative);
the shipped default itself carries pre-registration fd4a6f0e9893df22 and
its amendments. Member-alone relWIS 0.6664 against the bare analogue's
0.7711 on 15,340 identical cells.

### The run-time contract

A run asks for pools through `spec.extra["aux_pools"]`, a list of dicts:
`stream` (`"flusurv"` or `"iliplus"`), `weight`, and exactly one of
`committed: True` (the bank in `data/banks/`), `bank: <path>` or
`build: {...}` (from source; ILI+ builds default to vintage-true, FluSurv
refuses a vintage key); optional `shrink` (`"auto"`, a number, or `None`),
`exclude_seasons`, `bandwidth`. An absent key, or `False`, runs the bare
analogue; an empty list raises; weights summing past 1 raise. The three
sources differ in what they check: `committed` verifies the digest and
applies no filter; `bank: <path>` drops non-positive values at load and
raises only when nothing positive remains; `build` runs the stream builder.
`AUX_PRESETS` names `flusurv`, `iliplus` and `both` (0.25 each);
`aux_preset(name)` resolves a preset against the committed banks and
carries the digest in its name, `aux_preset:flusurv+flusurv@06eff6a7`.

Where that name is recorded, and what each entry point runs by default:

* `flubnf retro` writes the full name into `run_meta.json` under
  `settings.week_extra`. No `--aux` runs the shipped preset; `--aux
  <preset>` selects one; `--aux none` runs the bare analogue.
* `flubnf groundhog retro <season>` (`app/core/groundhog.run_season`) is
  the standalone replay and has the OPPOSITE default: an empty `--aux`
  runs the bare analogue under the arm directory `shipped` (its historical
  name), and `--aux flusurv` is the Groundhog. It writes the name under
  the top-level key `aux` of its own `run_meta.json`.
* `app.core.retro.run_season(engine="analogue")` is the in-app
  Groundhog-only replay and defaults to the shipped preset.
* The console ledger stores `analogue_aux` WITHOUT the `aux_preset:`
  prefix (`flusurv+flusurv@06eff6a7`). A fresh console run posts no `aux`
  and so runs the shipped preset; the run route accepts `aux` (a preset
  name, or empty for the bare analogue as a research run with its
  submission withheld), and a re-run re-runs whatever the ledger row
  recorded.

## 7. Reusing the banks for the Oracle SIHRS

What transfers directly:

* **The banks.** `bank.read(stream)` gives the mapping; both are committed,
  offline, digest-verified.
* **Calendar-matched, strictly-prior, exclusion-respecting donor selection.**
  `donor_ratios` (one horizon's ratios) and `donor_paths` (complete
  trajectories, section 5) on any bank, pure functions of the bank and the
  target date. `in_season_log_ratios(bank, horizon, seasons)` gives the log
  growth of NAMED seasons inside the in-season window (epiweek >= 47 or
  <= 20); it applies no strictly-prior test, no bandwidth and no
  exclusion, so the caller picks the seasons, the way `fit_log_ratio_shrink`
  does (shared, strictly prior, minus `resolve_donor_exclusions`).
* **The calendar helpers**: `epiweek`, `season_of`, `calendar_distance`.
* **The exclusion registry**, through `resolve_donor_exclusions`.

What does not transfer and must be decided on the Oracle SIHRS side:

* **Levels versus ratios.** The Groundhog uses ratios, so ILI+'s odd units
  and FluSurv-NET's ascertainment gap never enter. A mechanistic use that
  wants past seasons' epidemic CURVES (to fit the seasonal forcing, to place
  peak timing, to set an initial condition) is using levels, and needs a
  per-stream scale and a location mapping that this repository does not
  provide. The shrink factor is a ratio-space object and is not that scale.
* **Vintage.** For strictly-prior-season information the snapshots are
  measured-safe (section 2). For anything touching the current season,
  build a vintage-true ILI+ bank with `iliplus.build_bank(season_start,
  asof_iso=<forecast date>)`; FluSurv-NET cannot be made vintage-true.
* **Horizons.** `flubnf.analogue` counts physical weeks ahead, 1 to 4. The
  relabel to the hub's 0 to 3 happens at the engine wrapper's edge
  (`app/core/engines/analogue.py`, `qs[str(h - 1)]`);
  `app/core/horizons.py` handles the stored week-file convention, a
  separate boundary that `app/tests/test_horizon_convention.py` holds. Do
  not pass a 0-based horizon into the library, which would read
  `v(d) / v(d) = 1`.
* **Pre-registration.** Any arm that scores against the record must be
  frozen and hashed before it is scored, every arm reported, and no
  declined or unrun experiment counted as a kill. The donor-pool
  measurements above all followed that rule; the mechanistic reuse should
  too.

Three uses that fit the primitives with little glue: an empirical prior
on the next four weeks' growth (the pooled ratio quantiles for the current
epiweek and horizon from `donor_ratios`); a prior on the next six weeks'
growth as trajectories (`donor_paths` with `length=6`, taking `np.log` of
the rows, grouped by season through `with_keys` where the model weights
donor seasons; per-donor-season isolation goes through the keys, since
`exclude_seasons` accepts only registered seasons and cannot isolate
one); and a per-season shape library (`in_season_log_ratios` over a season
list the caller has already restricted to strictly prior, non-excluded
seasons). All are ratio-space and inherit the vintage safety argument.

How the Oracle SIHRS ships them (bank change B2, 2026-09-23;
docs/ORACLE-SIHRS.md section 5b): `flubnf/oracle_mix.py` takes the donor
cells of the committed FluSurv-NET bank from `donor_paths(..., length=6,
with_keys=True)`, adds the W-1 cell the eight-week growth path needs, the
season-crossing rule and the guards, stamps the paths with the admissions
bank's smoother on the rate series, and scales their log growth by the
`fit_log_ratio_shrink` factor the Groundhog fits on the same vintage. The
Groundhog's weight 0.5 becomes a per-sample mixture: each forecast sample
path draws its donor from the admissions or the FluSurv-NET pool with
equal probability. Nothing in `flubnf/analogue.py` changed for it.

## 8. Tests that pin this

`tests/test_epiweek53.py` (window and date arithmetic across the week-53
seam), `tests/test_analogue.py` (donor selection, and that the 2020-21
exclusion changes only the ILI+ pool), `tests/test_donor_paths.py` (growth
paths, the shared selection rule, and the byte-identity of `donor_ratios`
on the committed banks), `app/tests/test_analogue_splice.py`
(vincentization, shrink fit, abstention, the pool contract, presets),
`app/tests/test_horizon_convention.py` (the 0 to 3 boundary),
`app/tests/test_bank.py`
(committed banks, digests, offline construction), `app/tests/test_groundhog.py`
and `app/tests/test_retro_groundhog_only.py` (the standalone replays),
`app/tests/test_flusurv.py` and `app/tests/test_iliplus.py` (the stream
builders). Run them with the CI contract:

    FLUBNF_HUB=/nonexistent .venv/bin/python -m pytest tests app/tests -o addopts=""
