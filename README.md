# FluBNF

[![tests](https://github.com/elyfmiller/flubnf/actions/workflows/tests.yml/badge.svg)](https://github.com/elyfmiller/flubnf/actions/workflows/tests.yml)

FluBNF forecasts weekly influenza hospital admissions for the 50 US states,
the District of Columbia, Puerto Rico and the nation, in the CDC FluSight
submission format. It is an operations console for a FluSight week: pull
the data, run the models, write and validate the submission files, score
the result against the CDC baseline, and replay whole seasons on the data
as it stood at the time.

## What it forecasts, from what data

The target is the FluSight quantity `wk inc flu hosp`: weekly NHSN hospital
admissions with influenza, forecast as full predictive distributions at the
23 FluSight quantile levels for horizons 0 to 3 weeks. Every input comes
from a clone of the public FluSight hub (cdcepi/FluSight-forecast-hub):
`target-data/` for the current series, `auxiliary-data/target-data-archive/`
for the dated snapshots that retrospectives replay, and
`model-output/FluSight-baseline/` for scoring. The shipped forecast reads
nothing else; the research two-strain member and the legacy command-line
layer, both off the default path, can fetch NREVSS and NHSN series from the
Delphi Epidata API and data.cdc.gov, cached under `app/state`.

## The models

The shipped forecast is an equal weight, unfitted quantile average of two
members:

* PF-SIHRS, mechanistic. An SIHRS compartmental model (susceptible,
  infected, hospitalized, recovered, with waning immunity and seasonal
  transmission) written in BNGL and fitted by a sequential particle filter:
  10,000 candidate epidemics per jurisdiction, refitted every week from the
  season's start on that week's data. The filter runs in a fork of PyBNF
  with bngsim integrating the model in process; a jurisdiction season fits
  in seconds.
* Calendar analog, empirical. It scales the latest observation by growth
  ratios drawn from prior seasons at the same point in the calendar, pooled
  across jurisdictions. Nothing is fitted.

The members fail in different regimes: the mechanistic member can follow a
turn the analog cannot anticipate, and the analog holds when a season
behaves like past seasons. Interval coverage at the January turn is the
known weakness. Model definitions and parameter sources are in
docs/MODEL-PROVENANCE.md.

The Sandbox tab runs the same particle filter on a model of your own, in
its own folder, with a code editor, a contact map and reaction network
drawn from the model, and data filled from the hub archive by jurisdiction
and week range. Four example models ship with it.

## Install and run

Requirements: Python 3.11 or newer, git, and about 150 MB for the sparse
hub clone. Setup installs BioNetGen itself.

macOS, one line (clones to ~/Documents/GitHub/flubnf, runs setup, prints
how to launch):

    curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | bash

Linux, or macOS by hand:

    git clone https://github.com/elyfmiller/flubnf && cd flubnf
    ./setup.sh
    .venv/bin/flubnf app

`flubnf app` serves the console at http://127.0.0.1:8710 and opens it in a
native window, or in your browser when pywebview is unavailable. Double
clicking `FluBNF.command` or `FluBNF.app` in a clone does the same, first
run setup included. Windows is experimental: clone outside `Documents` and
double click `FluBNF.bat`; see docs/WINDOWS.md.

The particle filter engine lives in a PyBNF fork that is not yet public.
The console runs without it, with analog forecasts only. Lab members
receive a small engine archive; saved in Downloads, it is installed the
next time the app opens. The full procedure, including the GitHub routes,
is docs/ENGINE.md; the student walkthrough is docs/INSTALL-STUDENTS.md.

`flubnf doctor` reports which externals a machine can see. Each resolves
from `flubnf/settings.py` and can be pointed elsewhere by environment
variable: `FLUBNF_HUB` (the hub clone), `FLUBNF_BNG` (BNG2.pl),
`FLUBNF_PY_ENGINE` (python of the engine venv), `FLUBNF_PYBNF` (the PyBNF
checkout).

## Measured record

Three seasons replayed at full grid, 52 jurisdictions, three replicates,
strictly on the hub's dated snapshots, scored as weighted interval score
relative to the CDC FluSight-baseline. Below 1.000 beats the baseline. The
score is a ratio of WIS sums on shared cells, not the pairwise relative WIS
of the CDC dashboard, so the two are not comparable.

| engine | 2023-24 | 2024-25 | 2025-26 | pooled | cells |
|---|---|---|---|---|---|
| production, the code in this repository | 0.834 | 0.716 | 0.663 | 0.723 | 15,460 |
| sealed v1.0.0 record | 0.813 | 0.618 | 0.683 | 0.678 | 15,460 |

The ensemble beats the baseline in every season on both engines. The rows
differ because the sealed fits ran a particle filter kernel with an
undeclared behaviour that has since been corrected; the production row is
what this code reproduces. These are self computed retrospective replays,
not real time submissions. Methodology, caveats, the independent
replication, and everything that was tested and did not ship are in
docs/RELEASE-1.0.md and on the console's Methods page. The research
outputs behind those records live in the lab's archive, not in this
repository's tip; some earlier commits retain copies.

## Layout

    flubnf/            the science package: templates, data, fitting, quantiles, WIS
    app/               the console: FastAPI UI, run ledger, engines, ensemble, reports, sandbox
    scripts/           operational runners, not packaged
    docs/              release record, model provenance, engine, install and platform notes
    tests/ app/tests/  the two test suites (run with pytest)
    model-metadata/    the hubverse model cards

`app/state/` (ledger and retrospectives), `sandbox/` and `site/` are
generated locally and ignored by git.

## Citing

See CITATION.cff, and cite the release whose measured record you rely on.

## License

MIT, see LICENSE.
