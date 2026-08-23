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
  drawn from prior seasons at the same point in the calendar.

The 50/50 weight was never fitted. Forecasts are predictive distributions at
the 23 FluSight quantile levels over horizons 0 to 3 weeks, and every score in
this repository comes from replaying point-in-time (vintage) data: the model
sees only what was known on each forecast date.

## The measured record

Three seasons replayed at full grid (52 jurisdictions, 3 replicates, vintage
data only), scored as weighted interval score relative to the CDC
FluSight-baseline (relWIS below 1.000 beats the baseline):

| season | ensemble relWIS | CDC baseline | FluSight field | percentile |
|---|---|---|---|---|
| 2023-24 | 0.848 | 1.000 | 14 of 34 teams | 61st |
| 2024-25 | 0.651 | 1.000 | 4 of 40 teams | 92nd |
| 2025-26 | 0.691 | 1.000 | 19 of 47 teams | 61st |
| pooled | **0.704** | 1.000 | | mean 71st |

Notes on reading the table:

* The ensemble beat the baseline in every season (15,460 scored cells pooled).
  Each member alone did not: the filter lost 2023-24 (1.023) and the analogue
  lost it worse (1.105); the blend won all three.
* The field columns place the same forecasts among the real submissions
  archived in the FluSight hub. In 2024-25 the ensemble also finished ahead of
  the official FluSight-ensemble (0.635 against its 0.674). Placements are
  scored on final truth with the hub's coverage gates, so a placement score can
  differ slightly from the vintage-scored relWIS column. Percentile is the
  share of the field beaten; the pooled row averages the season percentiles.
* **Independent replication (2026-08-23):** a lab laptop (Apple M4) replayed
  all three seasons at full grid using only the shipped console, in about 18
  machine-hours total: 0.847, 0.651, 0.691. Two seasons reproduce exactly and
  one differs by 0.001.

The full validation record, including the eight candidate ensemble members
that were tested and rejected under pre-registered rules, is in
[docs/RELEASE-1.0.md](docs/RELEASE-1.0.md) and on the console's Methods page.

## Limitations

Read these before relying on the numbers above.

* **Scores are self-computed.** Every figure here is produced by this
  repository's own scoring code from the FluSight hub's archived vintage data,
  official baseline files, and archived team submissions. The placements are
  retrospective replays, not rankings earned by real-time participation:
  FluBNF did not submit during the seasons scored, and real-time operation
  adds failure modes a replay cannot exercise.
* **The January turn is the known weak phase.** At the epidemic's peak and
  turn the ensemble's intervals are too narrow: at the January 2025 turn the
  central 50 percent interval covered 27 percent of outcomes against a nominal
  50. Eight pre-registered candidate fixes were tested against this defect and
  none passed its gates. It is documented, not solved.
* **The batch MCMC engine does not converge.** The SIHRS posterior is a long
  correlated ridge, and the adaptive MCMC engine (`fit_type = am`) fails
  standard convergence diagnostics on it even with the improved shipped
  defaults (multiple chains, log-scaled proposals). Its posteriors should not
  be read as converged Bayesian posteriors. The shipped ensemble does not use
  this engine; its mechanistic member is the sequential particle filter, which
  carries no such caveat.
* **Three seasons is a small sample.** The hub's vintage archive begins
  2023-09-23, so three seasons is all the vintage-true evidence that can
  exist. The record supports "beat the baseline in each of three seasons"; it
  does not support a point prediction of next season's score.
* **Windows support is experimental.** See [docs/WINDOWS.md](docs/WINDOWS.md):
  the console, analogue engine, data fetching, scoring, and reports are
  expected to work; the particle-filter engine has additional requirements.

## Install

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

```
flubnf/        the science package: model templates, data resolution, fitting,
               quantiles, scoring, particle filter, seasonal priors
app/           operations console: FastAPI UI, run ledger, engines, ensemble,
               submission formatting, weekly HTML report (US map + drill-down)
scripts/       operational runners (pre-season seeding, weekly loop, backtests,
               data audit)
site/          the public static site, generated from the lab's own
               retrospectives by `flubnf site build` (see docs/SITE.md)
tests/         test suites for both layers
```

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
claim being cited is the claim that was validated.

## License

MIT, see [LICENSE](LICENSE).
