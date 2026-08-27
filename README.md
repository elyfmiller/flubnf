# FluBNF

[![tests](https://github.com/elyfmiller/flubnf/actions/workflows/tests.yml/badge.svg)](https://github.com/elyfmiller/flubnf/actions/workflows/tests.yml)

FluBNF is an operations console for forecasting weekly influenza hospital
admissions in all 52 US jurisdictions, in the
[CDC FluSight](https://github.com/cdcepi/FluSight-forecast-hub) format. It
runs the models, scores them against the official baseline, replays whole
seasons on point-in-time data, and writes the submission files and reports
for a FluSight week.

## The models

The shipped forecast is an equal-weight, never-fitted 50/50 blend of two
members that fail in different regimes:

* **PF-SIHRS**, the mechanistic member: an SIHRS compartmental model
  (susceptible, infected, hospitalized, recovered, with waning immunity and
  seasonal transmission) written in [BNGL](https://bionetgen.org). A
  sequential particle filter carries 10,000 candidate epidemics per state,
  reweighting them each week against the newest admissions data; fitting a
  state-season takes seconds, via a fork of
  [PyBNF](https://github.com/lanl/PyBNF) with
  [bngsim](https://github.com/lanl/bngsim) integrating the model in-process.
* **The calendar analogue**, the empirical member: it scales each state's
  latest observation by growth ratios drawn from prior seasons at the same
  point in the calendar, pooled across states. No epidemiology, no fitted
  parameters, and hard to beat when a season behaves like past seasons.

The mechanistic member tracks turning points the analogue cannot
anticipate; the analogue holds the middle horizons and stays anchored when
a season behaves unusually. Forecasts are full predictive distributions at
the 23 FluSight quantile levels, horizons 0-3 weeks.

## Performance

Three seasons replayed at full grid (52 jurisdictions, 3 replicates),
strictly on vintage data: the models see only what was known on each
forecast date. Scores are weighted interval score relative to the CDC
FluSight-baseline (below 1.000 beats the baseline); the comparator column
is the official FluSight multi-team ensemble, scored on exactly the same
cells through the same scorer.

| season | FluBNF ensemble | FluSight ensemble | scored cells |
|---|---|---|---|
| 2023-24 | 0.813 | 0.741 | 6,063 |
| 2024-25 | 0.618 | 0.663 | 4,922 |
| 2025-26 | 0.683 | 0.684 | 4,475 |
| pooled | **0.678** | 0.685 | 15,460 |

The ensemble beat the baseline in every season, and is level with the
official FluSight ensemble overall (ahead one season, level one, behind
one; the pooled gap is not statistically separable from zero). These are
self-computed retrospective replays, not real-time submissions, and three
seasons is every vintage-true season the hub's archive can support. The
full validation record - methodology, pre-registered gates, the
independent replication, and everything that was tested and did not ship -
is in [docs/RELEASE-1.0.md](docs/RELEASE-1.0.md) and on the console's
Methods page.

## The app

The console (`flubnf app`) is organized around the FluSight week:

* **Data** - pull the hub, confirm the NHSN feed is current, and pass the
  integrity audit (vintage gaps, NaN policy, join checks).
* **Forecast** - pick the forecast date and run the members; the full
  52-jurisdiction grid with 3 replicates completes well inside a working
  day on a laptop.
* **Output** - the validated hubverse submission CSVs and a weekly HTML
  report: a US map with per-state quantile-fan drill-downs.

Beyond the weekly loop:

* **Retrospectives** replay a whole season on vintage data, with pause and
  resume; an interrupted replay refits only the cells that never ran.
* The **season playback player** steps through any stored retrospective
  week by week - member fans, the ensemble, settled truth, the CDC's own
  submitted comparators, running relWIS - and exports as one
  self-contained HTML file.
* **Reproducibility is structural**: every run derives its RNG seeds from
  `(location, date, replicate)`, leases an exclusive workroot, and is
  recorded in a ledger with the spec and versions needed to re-execute it.
* Four color themes with high-contrast and red-green-safe modifiers.

## Install

A source clone is the supported installation (the console needs a FluSight
hub clone, BioNetGen, and an engine venv, not just a wheel; `pip install .`
works for using `flubnf` as a library).

**macOS** - one line, or double-click `FluBNF.app` / `FluBNF.command` from
a clone; the first run sets everything up and opens the console (the
bundle is unsigned: first launch is right-click, then Open):

```bash
curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | bash
```

**Linux**:

```bash
git clone https://github.com/elyfmiller/flubnf && cd flubnf
./setup.sh
.venv/bin/flubnf app
```

**Windows (experimental)** - install Python 3.11+ and Git, clone outside
`Documents` (`%LOCALAPPDATA%\FluBNF\flubnf` is the suggested spot), and
double-click `FluBNF.bat`, which offers the full first-time setup. Cloning
outside `Documents` avoids Microsoft Defender's Controlled Folder Access
(shipped off, but common on managed machines), which silently blocks git,
python, and perl there. Details: [docs/WINDOWS.md](docs/WINDOWS.md).

External components resolve via `flubnf/settings.py`, each overridable by
environment variable; check any machine with
`python -c "from flubnf.settings import check; check()"`:

| variable | points at |
|---|---|
| `FLUBNF_HUB` | a clone of `cdcepi/FluSight-forecast-hub` |
| `FLUBNF_BNG` | BioNetGen's `BNG2.pl` |
| `FLUBNF_PY_ENGINE` | python of the engine venv (`pybnf` + `bngsim`) |
| `FLUBNF_PYBNF` | a PyBNF checkout providing `fit_type = pf` |

## Layout

```
flubnf/          the science package: model templates, data resolution,
                 fitting, quantiles, WIS, baseline construction, priors
app/             the console: FastAPI UI, run ledger, engines, ensemble,
                 submissions, reports; app/tests/ is its suite
scripts/         operational runners (not packaged into the wheel)
docs/            release record, model provenance, site and Windows notes
tests/           the science-package suite
data/            small tracked inputs
model-metadata/  the hubverse model card
```

Generated and local-only, never in the repository: `app/state/` (ledger,
retrospectives, the sealed three-season record), `site/`, `workspaces/`,
`research/`.

## Citing

See [CITATION.cff](CITATION.cff), and cite the version (v1.0.0) so the
claim cited is the claim that was validated.

## License

MIT, see [LICENSE](LICENSE).
