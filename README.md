# FluBNF

[![tests](https://github.com/elyfmiller/flubnf/actions/workflows/tests.yml/badge.svg)](https://github.com/elyfmiller/flubnf/actions/workflows/tests.yml)

> **Status, 2026-27 season.** FluBNF submits to CDC FluSight 2026-27 as
> team `NAU_PyBNF`, with two models: `NAU_PyBNF-OracleSIHRS` and
> `NAU_PyBNF-GroundHogCGR` ([model cards](model-metadata/README.md)). The
> first round is due Wednesday 2026-10-07 (reference date 2026-10-10). The
> season's rules, dates and weekly routine are in
> [docs/FLUSIGHT-2026-27.md](docs/FLUSIGHT-2026-27.md).

FluBNF forecasts weekly influenza hospital admissions for the 50 US states,
the District of Columbia, Puerto Rico and the nation, in the CDC FluSight
submission format. It is an operations console for a FluSight week: pull
the data, run the models, write and validate the submission files, score
the result against the CDC baseline, and replay whole seasons on the data
as it stood at the time.

## Quick start

On macOS or Linux, with git and Python 3.11 or newer (3.11 or 3.12 for
the engine):

    git clone https://github.com/elyfmiller/flubnf && cd flubnf
    ./setup.sh                  # .venv, BioNetGen and the sparse hub clone
    .venv/bin/flubnf app        # the console, at http://127.0.0.1:8710
    .venv/bin/flubnf doctor     # what this machine can see

Without the lab's engine the console runs the Groundhog only. The macOS
one-line installer, Windows, and the engine are under
[Install and run](#install-and-run); lab members start from
[docs/INSTALL-STUDENTS.md](docs/INSTALL-STUDENTS.md).

## What it forecasts, from what data

The target is the FluSight quantity `wk inc flu hosp`: weekly NHSN hospital
admissions with influenza, forecast as full predictive distributions at the
23 FluSight quantile levels for horizons 0 to 3 weeks. Every input comes
from a clone of the public FluSight hub (cdcepi/FluSight-forecast-hub):
`target-data/` for the current series, `auxiliary-data/target-data-archive/`
for the dated snapshots that retrospectives replay, and
`model-output/FluSight-baseline/` for scoring. Eight scored weeks the hub
archive skipped ship with FluBNF as [`data/vintages/`](data/vintages/),
copied from the hub's own published files ([data/README.md](data/README.md)).
The shipped forecast reads nothing else; the research two-strain member,
off the default path, can fetch NREVSS series from the Delphi Epidata API,
cached under `app/state`.

## The models

FluBNF submits two models to FluSight, each under its own hub identity
([`model-metadata/`](model-metadata/README.md)), and nothing is blended:

* **Oracle SIHRS** (`NAU_PyBNF-OracleSIHRS`), mechanistic. The SIHRS
  compartment model (susceptible, infected, hospitalized, recovered, with
  waning immunity and seasonal transmission) written in BNGL and fitted by
  a Liu-West filter (a sequential particle filter): 10,000 candidate
  epidemics per jurisdiction, refitted every week from the season's start
  on that week's data. The filter runs in a fork of PyBNF with bngsim
  integrating the model in process; a jurisdiction season fits in seconds.
  After the fit, the Oracle step blends the filter's forecast growth with
  donor growth from past seasons at the same calendar week: each forecast
  sample path draws one donor growth path from an earlier season (within
  two epiweeks, any jurisdiction) and grows at the geometric mean, half
  and half, of the filter's growth and the donor's, propagated in closed
  form from the filter's own state. The donors come from the Groundhog's
  own donor bank: NHSN admissions growth and FluSurv-NET
  hospitalization-rate growth, half and half
  ([docs/ORACLE-SIHRS.md](docs/ORACLE-SIHRS.md)).
* **Groundhog** (`NAU_PyBNF-GroundHogCGR`), empirical. The last observed
  count scaled by the empirical quantiles of growth ratios seen at the same
  MMWR epiweek in strictly earlier seasons, pooled across jurisdictions,
  with a committed FluSurv-NET donor bank spliced in
  ([`data/banks/`](data/banks/)). Epiweek 53 is seated between weeks 52
  and 1. Nothing is fitted.

Both read past seasons at the same calendar week, in different ways: the
Groundhog applies donor growth ratios to the last observed count, the
Oracle SIHRS applies donor growth to the mechanistic model's fitted state.
Interval coverage at the January turn is the known weakness of the
mechanistic fit. Model definitions and parameter sources are in
[docs/MODEL-PROVENANCE.md](docs/MODEL-PROVENANCE.md).

The Sandbox tab runs the same particle filter on a model of your own, in
its own folder, with a code editor, a check that needs no engine, a
contact map and reaction network drawn from the model, and data loaded
from the hub archive (by jurisdiction and week range) or from a CSV of
your own. Examples and a template for a new pathogen ship with it; a
student guide is in [docs/SANDBOX.md](docs/SANDBOX.md).

The Data, Forecast and Retrospective tabs also take weekly data of your
own (a CSV of date, group and value, population optional), kept apart
from the FluSight hub and never submitted. For a true retrospective,
give the data as each week saw it: one CSV with an as_of column, or a
folder of snapshot files, one per as_of, each named by its date
(2024-10-05.csv, admissions_2024-10-05.csv) or holding an as_of column.
Each replayed week then sees the snapshot that held it. `flubnf dataset
import` takes the same file or folder.

## Install and run

Requirements: Python 3.11 or 3.12 (the engine pins numpy<2); the console
alone runs on newer. Also git, and about 150 MB for the sparse hub clone.
Setup installs BioNetGen itself.

macOS, one line (clones to `~/GitHub/flubnf`, runs setup, prints
how to launch):

    curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | bash

Linux, or macOS by hand:

    git clone https://github.com/elyfmiller/flubnf && cd flubnf
    ./setup.sh
    .venv/bin/flubnf app

`flubnf app` serves the console at http://127.0.0.1:8710 and opens it in a
native window, or in your browser when pywebview is unavailable. Double
clicking [`FluBNF.command`](FluBNF.command) or [`FluBNF.app`](FluBNF.app/)
in a clone does the same, first run setup included. Windows is
experimental: clone outside `Documents` and double click
[`FluBNF.bat`](FluBNF.bat); see [docs/WINDOWS.md](docs/WINDOWS.md).

The particle filter engine lives in a PyBNF fork that is not yet public.
The console runs without it, with the Groundhog's forecasts only. Lab members
receive a small engine archive; saved in Downloads, it is installed the
next time the app opens. The full procedure, including the GitHub routes,
is [docs/ENGINE.md](docs/ENGINE.md); the student walkthrough is
[docs/INSTALL-STUDENTS.md](docs/INSTALL-STUDENTS.md).

On macOS and Linux, a machine whose copy is stale or broken reinstalls from
scratch with one line, once the engine archive is saved in Downloads and
older `pybnf-pf-*.tar.gz` downloads are deleted. Nothing is deleted, a
current machine and a checkout with uncommitted work are left alone, and
[docs/LAUNCHERS.md](docs/LAUNCHERS.md#reinstalling-from-scratch-macos-and-linux)
says what it moves where:

    curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/reinstall.sh | bash

That line does not run on Windows. There, a reset in place, which keeps
the runs, and a reinstall from scratch are a few Command Prompt lines:
"Resetting or reinstalling (Windows)" in
[docs/INSTALL-STUDENTS.md](docs/INSTALL-STUDENTS.md#resetting-or-reinstalling-windows).

`flubnf doctor` reports which externals a machine can see; each can be
pointed elsewhere by a `FLUBNF_*` environment variable
([docs/LAUNCHERS.md](docs/LAUNCHERS.md#environment-variables)).

## Measured record

Three seasons replayed at full grid, 52 jurisdictions, strictly on the
hub's dated snapshots, scored as weighted interval score relative to the
CDC FluSight-baseline. Below 1.000 beats the baseline. The score is a
ratio of WIS sums on shared cells, not the pairwise relative WIS of the
CDC dashboard, so the two are not comparable. The rows' cells and runs
differ and are not read across.

| model | cell rule | 2023-24 | 2024-25 | 2025-26 | pooled | cells |
|---|---|---|---|---|---|---|
| Groundhog (`flubnf groundhog retro all --aux flusurv`, hub at 99cc45a) | FluSight's, since 2026-09-25 | 0.722 | 0.659 | 0.660 | 0.6705 | 17,116 |
| Oracle SIHRS, the stored forecasts with the step and its donor bank applied ([docs/ORACLE-SIHRS.md](docs/ORACLE-SIHRS.md)) | earlier[^earlier] | 0.767 | 0.697 | 0.781 | 0.738 | 15,300 |
| calendar analogue without the donor bank, on the Groundhog's 2026-09-21 cells | earlier[^earlier] | 1.045 | 0.756 | 0.618 | 0.771 | 15,340 |

[^earlier]: Measured under the scorer's earlier cell rule (truth and median
    above 0) and kept as measured. FluSight's rule, the scorer's since
    2026-09-25, also scores zero truths and zero medians. Under the earlier
    rule the Groundhog's replay of 2026-09-21 scored 0.722, 0.653 and 0.651
    (0.666 pooled) on 15,340 cells, the figures the console's Home and
    Methods still print. On those cells its WIS equals today's replay bit
    for bit; the 1,776 cells added are the ones the old rule skipped.

Without the step, the plain particle filter on the Oracle SIHRS's cells
scores 0.840, 0.794 and 0.843 (0.819 pooled); on the 9,279 cells of
2024-25 and 2025-26 together the Oracle SIHRS scores 0.731 against the
plain filter's 0.813. The particle filter alone on the production
engine's replay (reseal of 2026-09-07, 15,460 cells) scored 0.840, 0.797
and 0.846 (0.821 pooled). Choosing the Groundhog's bank over admissions
growth alone (0.741 on the same 9,279 cells) was the project lead's
decision on a screen that did not resolve it; the Oracle SIHRS's record is
a frozen-specification replication, and the 2026-27 season is the
prospective test.

The Groundhog's row reproduces on any machine with a hub clone and no
engine:

    flubnf groundhog retro all --aux flusurv

or from the console, Retrospective tab, engine preset "Groundhog only"
(minutes per season; the two paths agree cell for cell).

A season's Oracle SIHRS is made the same way a live week is: a console replay,
Retrospective tab, preset "Oracle SIHRS and the Groundhog" (or
`flubnf retro <season>`), which fits every week from the season start and
applies the Oracle step with that week's data and donor pool (hours per
season, needs the engine venv). These are self
computed retrospective replays, not real time submissions. Methodology
and caveats are on the console's Methods page; the research outputs
behind these records live in the lab's archive, not in this repository's
tip. The record of the 1.0 and 1.1 releases, which shipped a different
product, is [docs/archive/RELEASE-1.0.md](docs/archive/RELEASE-1.0.md).

## Layout

| Path | What it holds | Index |
|---|---|---|
| `FluBNF.command`, `FluBNF.app/`, `FluBNF.bat`, `SetupEngine.command` | double-click launchers (macOS, Windows) | [docs/LAUNCHERS.md](docs/LAUNCHERS.md) |
| `install.sh`, `reinstall.sh`, `setup.sh`, `setup_engine.sh`, `setup.ps1` | install, reinstall and setup scripts | [docs/LAUNCHERS.md](docs/LAUNCHERS.md) |
| `.githooks/` | pre-push hook: both suites as CI runs them, on pushes to main | [docs/LAUNCHERS.md](docs/LAUNCHERS.md) |
| `flubnf/` | the science package and the `flubnf` CLI | [flubnf/README.md](flubnf/README.md) |
| `flubnf/templates/` | BNGL model templates; production is `SIHRS_pop_min.bngl` | [flubnf/templates/README.md](flubnf/templates/README.md) |
| `flubnf/sandbox_examples/` | the Sandbox tab's examples and the template for a new pathogen | [docs/SANDBOX.md](docs/SANDBOX.md) |
| `flubnf/data/` | `locations.csv`, used when the hub has none | |
| `app/core/` | console back end: replay, scoring, reports, Oracle step, site | [app/core/README.md](app/core/README.md) |
| `app/ui/` | FastAPI server, Jinja pages, static JS and CSS | [app/ui/README.md](app/ui/README.md) |
| `data/banks/` | the Groundhog's committed donor banks and manifests | [data/README.md](data/README.md) |
| `scripts/` | ops scripts, not packaged | [scripts/README.md](scripts/README.md) |
| `docs/` | install, engine, Windows, models, banks, site, archive | [docs/README.md](docs/README.md) |
| `tests/`, `app/tests/` | the two pytest suites | [tests/README.md](tests/README.md) |
| `model-metadata/` | the hubverse model cards | [model-metadata/README.md](model-metadata/README.md) |

`app/state/` (ledger and retrospectives), `sandbox/` and `site/` are
generated locally and ignored by git. Every `FLUBNF_*` environment
variable is listed in [docs/LAUNCHERS.md](docs/LAUNCHERS.md).

## Citing

See [CITATION.cff](CITATION.cff), and cite the release whose measured
record you rely on.

## License

The code is MIT ([LICENSE](LICENSE)); the forecasts submitted to FluSight
are CC BY 4.0, as each [model card](model-metadata/README.md) states.
