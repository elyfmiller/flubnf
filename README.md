# FluBNF

[![tests](https://github.com/elyfmiller/flubnf/actions/workflows/tests.yml/badge.svg)](https://github.com/elyfmiller/flubnf/actions/workflows/tests.yml)

FluBNF forecasts weekly influenza hospital admissions for all 52 US
jurisdictions in the [CDC FluSight](https://github.com/cdcepi/FluSight-forecast-hub)
format. The shipped forecast is an equal-weight, quantile-averaged ensemble of
two members that fail in different regimes:

* a **sequential particle filter** over an SIHRS compartmental model written in
  [BNGL](https://bionetgen.org), fitted with a fork of
  [PyBNF](https://github.com/lanl/PyBNF) and simulated in-process with
  [bngsim](https://github.com/lanl/bngsim);
* a **calendar analogue** that scales the last observation by growth ratios
  drawn from prior seasons at the same point in the calendar. The donor pool
  is every strictly prior season except 2021-22, whose epidemic peaked in
  April and therefore answers a calendar-matched question with the wrong
  phase; the exclusion is pre-registered and measured, and is documented in
  [docs/RELEASE-1.0.md](docs/RELEASE-1.0.md#the-donor-pool-change).

The 50/50 weight was never fitted. Forecasts are predictive distributions at
the 23 FluSight quantile levels over horizons 0 to 3 weeks, and every score in
this repository comes from replaying point-in-time (vintage) data: the model
sees only what was known on each forecast date.

## The measured record

Three seasons replayed at full grid (52 jurisdictions, 3 replicates, vintage
data only), scored as weighted interval score relative to the CDC
FluSight-baseline (relWIS below 1.000 beats the baseline):

| season | ensemble relWIS | CDC baseline | scored cells |
|---|---|---|---|
| 2023-24 | 0.813 | 1.000 | 6,063 |
| 2024-25 | 0.618 | 1.000 | 4,922 |
| 2025-26 | 0.683 | 1.000 | 4,475 |
| pooled | **0.678** | 1.000 | 15,460 |

Notes on reading the table:

* The ensemble beat the baseline in every season (15,460 scored cells pooled).
  Each member alone did not: the filter lost 2023-24 (1.023) and the analogue
  lost it worse (1.045); the blend won all three.
* These are the figures of the shipped donor pool, which excludes 2021-22
  from the calendar analogue. Before that exclusion the same three seasons
  scored 0.847, 0.651, 0.691, pooled 0.704. Documents published before
  2026-08-24 printed the first of those as 0.848; the stored value was
  0.84746, so 0.847 was always the correct rounding and the 0.848 was an
  error in the document, not in the computation. The change moved the pooled
  ensemble by 3.66 percent, was positive in all three seasons independently
  and in 50 of 52 jurisdictions, and is recorded in full in
  [docs/RELEASE-1.0.md](docs/RELEASE-1.0.md#the-donor-pool-change). The
  particle-filter member and the cell counts are unchanged by it.
* **Placement against the real FluSight fields is withdrawn from this
  release.** Earlier versions of this table placed the same forecasts among
  the archived hub submissions at 14 of 34, 4 of 40 and 19 of 47, mean 71st
  percentile. Those figures were measured on the pre-exclusion donor pool and
  could not be carried forward: the script that produced them survives
  neither in this repository nor in the lab archive, a reconstruction from
  this repository's own scoring code reproduced no archived row of the field
  exactly, and the three rows for this project were not all computed on one
  convention (the 2024-25 row is exactly the score of the leave-one-season-out
  fitted ensemble, which this project rejected and never ships). The claim is
  withdrawn rather than restated, and returns only when it is measured again,
  end to end, on the shipped configuration.
* **Independent replication (2026-08-23), of the pre-exclusion
  configuration.** A lab laptop (Apple M4) replayed all three seasons at full
  grid using only the shipped console, in about 18 machine-hours total, and
  reproduced the record as it stood that day: 0.847, 0.651, 0.691. That run
  predates the donor-pool change, so it does not replicate the table above
  and no such claim is made for it. What the replication does establish
  still holds, because it exercised the part the change does not
  touch: the particle filter is the entire compute cost and the only
  stochastic stage, its stored samples are byte-identical before and after
  the change, and its scores move by 0.000e+00. The analogue is a
  deterministic calculation over the same archive.

The full validation record, including the challengers that were tested and
rejected under pre-registered rules, is in
[docs/RELEASE-1.0.md](docs/RELEASE-1.0.md) and on the console's Methods page.
Eight challengers were tested to a verdict and killed by this group, one was
tested and found null in an independent review, and one was declined without
being run. One passed and is shipped: excluding the calendar-inverted 2021-22
season from the analogue's donor pool, which cleared its pre-registered gates
on 2026-08-24 and against which every figure above has been re-measured.

## Limitations

Read these before relying on the numbers above.

* **Scores are self-computed.** Every figure here is produced by this
  repository's own scoring code from the FluSight hub's archived vintage data
  and official baseline files. They are retrospective replays, not scores
  earned by real-time participation: FluBNF did not submit during the seasons
  scored, and real-time operation adds failure modes a replay cannot
  exercise.
* **The shipped intervals are narrower than they were.** Excluding 2021-22
  from the donor pool removes the analogue's widest growth ratios, so the
  ensemble's intervals contract: pooled over the three seasons the central
  50, 80 and 95 percent intervals are 0.93, 0.92 and 0.90 of their previous
  total width. Empirical coverage stays above nominal at all three levels
  pooled (0.541, 0.837, 0.961 against 0.50, 0.80, 0.95), and the January
  2025 turn defect is unchanged at central-50, the level its kill clauses
  were written against, though the other two levels on that window did move
  (80 percent coverage 0.667 to 0.604, 95 percent 0.938 to 0.917). The
  narrowing is not free everywhere: on the six-state February 2024 plateau
  window used throughout the challenger ledger, central-50 coverage falls
  from 0.698 to 0.646.
* **The January turn is the known weak phase.** At the epidemic's peak and
  turn the ensemble's intervals are too narrow: at the January 2025 turn the
  central 50 percent interval covered 27 percent of outcomes against a nominal
  50. That figure was re-measured on the shipped configuration and did not
  move: 13 of the same 48 cells before the donor-pool change and 13 after.
  Three pre-registered candidate fixes were aimed squarely at this defect,
  a regime-switching filter, adaptive transmission and slope-anchored
  transmission, and none passed its gates. Those three are also the only
  ones with a recorded January figure. The five challengers aimed elsewhere
  were rejected on their own gates and none shipped, so the defect stands,
  but none of them was measured on this window and none is claimed to have
  been. The two that came closest, adaptive
  transmission and slope-anchored transmission, each reached 31.2 percent
  against the same pre-registered bar of 35 percent; both were measured
  against the pre-exclusion ensemble, whose January coverage was the same 27
  percent, so the comparison is unaffected. It is documented, not solved.
* **The batch MCMC engine does not converge.** The SIHRS posterior is a long
  correlated ridge, and the adaptive MCMC engine (`fit_type = am`) fails
  standard convergence diagnostics on it even with the improved shipped
  defaults (multiple chains, log-scaled proposals). Its posteriors should not
  be read as converged Bayesian posteriors. The shipped ensemble does not use
  this engine; its mechanistic member is the sequential particle filter, which
  carries no such caveat.
* **Three seasons is a small sample.** The hub's archive of dated forecast
  vintages begins 2023-09-23, so three seasons is all the vintage-true
  evidence that can exist. The record supports "beat the baseline in each of
  three seasons"; it does not support a point prediction of next season's
  score. The same limit applies to the donor-pool exclusion, which is
  measured on those three seasons and nowhere else. (The surveillance series
  carried inside each of those vintages reaches further back, to 2022-02-05,
  which is why 2021-22 is available as an analogue donor season at all; the
  two archives are different things and the two dates are both correct.)
* **Windows support is experimental.** See [docs/WINDOWS.md](docs/WINDOWS.md):
  the console, analogue engine, data fetching, scoring, and reports are
  expected to work; the particle-filter engine has additional requirements.

## Install

**A source clone is the supported installation.** The console needs more than
a Python package: a clone of the FluSight hub, BioNetGen, a second virtual
environment for the fitting engine, and the operational runners under
`scripts/`. Every route below starts from a clone for that reason.

`pip install .` works and is useful for importing `flubnf` as a library (the
model, quantiles, WIS, the validated baseline construction) or for running the
console against an existing hub clone. The wheel packages `flubnf` and `app`
and deliberately does not package `scripts/`, whose runners need the whole
clone and whose top-level name is far too generic for `site-packages`. The one
feature that needs them, the adaptive-MCMC engine (`fit_type = am`), checks for
its runner and says so plainly; the shipped particle-filter engine, the
analogue engine, scoring, the reports and the submission format do not.

### macOS

One line (clones and sets up):

```bash
curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | bash
```

Or, from a clone, double-click **`FluBNF.app`** (or `FluBNF.command`). The
first run sets everything up unattended, including a sparse fetch of the
FluSight hub data of roughly 158 MB, then opens the console in your browser.
Gatekeeper note: the bundle is unsigned, so the first launch needs
right-click, then Open.

### Linux

```bash
git clone https://github.com/elyfmiller/flubnf && cd flubnf
./setup.sh
.venv/bin/flubnf app
```

`setup.sh` is idempotent; re-run it any time to repair a broken environment.
The console runs (data browsing, the analogue engine, reports) before every
external component is installed, and the landing page states exactly what is
missing.

### Windows (experimental)

Install Python 3.11+ and Git, clone the repository, and double-click
`FluBNF.bat`; for full first-time setup run `setup.ps1`. Details and current
limitations: [docs/WINDOWS.md](docs/WINDOWS.md).

### External components

Resolved via `flubnf/settings.py`, each overridable by environment variable
(defaults assume checkouts under `~/Documents/GitHub`):

| variable | points at |
|---|---|
| `FLUBNF_HUB` | a clone of `cdcepi/FluSight-forecast-hub` (truth vintages, locations) |
| `FLUBNF_BNG` | BioNetGen's `BNG2.pl` |
| `FLUBNF_PY_ENGINE` | python of the engine venv (`pybnf` + `bngsim` installed) |
| `FLUBNF_PYBNF` | a PyBNF checkout providing `fit_type = pf` |

Check a machine with:

```bash
python -c "from flubnf.settings import check; check()"
```

Two virtual environments are deliberate: the analysis venv (this package,
pandas/fastapi/plotly) and the engine venv (pybnf, bngsim). The app
dispatches between them; they never import each other's world.

## A week in operation

The console (`flubnf app`) is organized around the FluSight submission
cadence. A competition week is three steps, in the order the landing page
presents them:

1. **Data**: confirm the NHSN admissions feed is current and pass the
   integrity audit (vintage gaps, NaN policy, join checks).
2. **Forecast**: pick the forecast date and run the members; the particle
   filter fits a state-season in seconds, so the full 52-jurisdiction grid
   with 3 replicates completes well inside a working day on a laptop.
3. **Output**: the hubverse-format submission file
   (`model-output/<team>-<model>/<date>-<team>-<model>.csv`, validated
   against the hub's own rules) and the weekly HTML report, a US map with
   per-state drill-down.

Beyond the weekly loop:

* **Retrospectives** replay a whole season on vintage data, with pause and
  resume; an interrupted replay refits only the cells that never ran.
* The **season playback player** steps through any stored retrospective week
  by week, showing each member's quantile fan, the ensemble, settled truth,
  and the CDC's own submitted comparators, with running relWIS. A season
  report exports the same player as one self-contained HTML file.
* **Storage reclaim** distinguishes, in code, what may be deleted from the
  load-bearing record (stored samples, scores, the sealed validation record)
  that reproducibility depends on.
* Four color themes (light, paper, dim, dark) with two composable
  accessibility modifiers: high contrast and a red-green-safe palette.

Reproducibility is structural: every run derives its RNG seeds from
`(location, date, replicate)`, leases an exclusive workroot, and is recorded
in a sqlite ledger with the spec, seeds, and git SHAs needed to re-execute
it. Missing surveillance weeks are treated as missing, dropped as rows with
calendar-true week offsets, never imputed.

## Running pieces individually

```bash
# operations console
uvicorn app.ui.server:app --port 8710

# data integrity audit (vintage gaps, NaN policy, join checks)
python scripts/data_audit.py

# pre-season convergence seeding, then the weekly competition loop
python scripts/preseason_seed.py --min-model --states Ohio --through 2025-09-20 \
    --root /tmp/warm --out preseason.json
python scripts/weekly_loop_run.py --min-model --states Ohio \
    --asofs 2025-11-15 2025-11-22 --root /tmp/warm --out weekly.json

# rebuild the public site from whatever retrospectives are on this machine
flubnf site build --check
```

## Layout

What a clone actually contains:

```
flubnf/        the science package: model templates, data resolution, fitting,
               quantiles, scoring, the validated baseline construction,
               particle filter, seasonal priors
app/           operations console: FastAPI UI, run ledger, engines, ensemble,
               submission formatting, weekly HTML report (US map + drill-down);
               app/tests/ holds the console suite
scripts/       operational runners (pre-season seeding, weekly loop, vintage
               replays, data audit). Not packaged into a wheel; see Install
docs/          the release record (RELEASE-1.0.md), model provenance, the site
               and Windows notes
tests/         the science-package suite
data/          small tracked inputs the package reads
model-metadata/  the hubverse model card
```

Generated and local-only, so present after a run but never in the repository:
`app/state/` (run ledger, retrospectives, per-cell scores, the sealed
three-season record), `site/` (built by `flubnf site build`, see
[docs/SITE.md](docs/SITE.md)), `workspaces/`, and `research/` (the challenger
harnesses; see the note in
[docs/RELEASE-1.0.md](docs/RELEASE-1.0.md#the-evidence-ledger-what-was-tested-and-rejected)).

Two inference engines share the same model, likelihood, and priors:

| engine | what it is | cost per state-season |
|---|---|---|
| `fit_type = pf` | sequential particle filter (Liu-West jitter, systematic resampling), running inside PyBNF on the bngsim engine | seconds |
| `fit_type = am` | PyBNF adaptive MCMC with warm-started weekly refits, automated pinning diagnosis and bound widening | hours |

A third engine, a two-strain SIHRS with a typed-surveillance channel, is
available in the app. It passed its pre-registered epidemic-turn gate at full
grid but did not qualify for the default ensemble; see
[docs/RELEASE-1.0.md](docs/RELEASE-1.0.md).

## Where the validation record lives

* [docs/RELEASE-1.0.md](docs/RELEASE-1.0.md): the v1.0 claim, the three-season
  table, the replication, and the ledger of tested-and-rejected candidates.
* The console's **Methods** page: the same record, with the model equations
  and the scoring formula.
* A full replay writes per-cell scores under `app/state/`; the sealed
  three-season record lives under `app/state/retro_seal/`.
* The complete research history, including every negative result and
  retraction, is kept in the Posner Lab research archive
  (`NAU-Projects/NAU_Influenza_M_Model/FluBNF/docs/RESULTS.md`).

## Citing

See [CITATION.cff](CITATION.cff). Please cite the version (v1.0.0) so the
claim being cited is the claim that was validated. The v1.0.0 content was
amended on 2026-08-24, before the tag was published, to ship the donor-pool
exclusion and to re-baseline every figure on it; the version number is
unchanged because no v1.0.0 was ever released with the earlier figures.

## License

MIT, see [LICENSE](LICENSE).
