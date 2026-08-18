# flubnf

[![tests](https://github.com/elyfmiller/flubnf/actions/workflows/tests.yml/badge.svg)](https://github.com/elyfmiller/flubnf/actions/workflows/tests.yml)

Mechanistic influenza forecasting for [CDC FluSight](https://github.com/cdcepi/FluSight-forecast-hub),
built on rule-based modeling: an SIHRS compartmental model written in
[BNGL](https://bionetgen.org), fitted with [PyBNF](https://github.com/lanl/PyBNF)
and simulated in-process with [bngsim](https://github.com/lanl/bngsim).

Two inference engines share the same model, likelihood, and priors:

| engine | what it is | cost per state-season |
|---|---|---|
| `fit_type = pf` | sequential particle filter (Liu–West jitter, systematic resampling), running *inside* PyBNF on the bngsim engine | seconds |
| `fit_type = am` | PyBNF adaptive MCMC with warm-started weekly refits, automated pinning diagnosis and bound widening | hours |

Forecasts are negative-binomial predictive distributions over weekly hospital
admissions, scored by WIS against the FluSight baseline on point-in-time
(vintage) data only. Output follows hubverse conventions
(`model-output/<team>-<model>/<date>-<team>-<model>.csv`).

## Layout

```
flubnf/        the science package: model templates, data resolution, fitting,
               quantiles, scoring, particle filter, seasonal priors
app/           operations console: FastAPI UI, run ledger, engines, ensemble,
               submission formatting, weekly HTML report (US map + drill-down)
scripts/       operational runners (pre-season seeding, weekly loop, backtests,
               data audit)
tests/         test suites for both layers
```

## What it needs

External components, resolved via `flubnf/settings.py` (each overridable by
environment variable; defaults assume checkouts under `~/Documents/GitHub`):

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
pandas/fastapi/plotly) and the engine venv (pybnf, bngsim). The app dispatches
between them; they never import each other's world.

## Quickstart

```bash
git clone git@github.com:elyfmiller/flubnf.git && cd flubnf
./setup.sh          # builds venvs, offers the data clone, ends with a doctor report
.venv/bin/flubnf app   # open http://localhost:8710
```

`setup.sh` is idempotent — re-run it any time to fix a broken environment.
The console runs (browse, analogue engine, reports) even before every
external is installed; the landing page shows exactly what is missing.

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
```

Reproducibility is structural: every run derives its RNG seeds from
`(location, date, replicate)`, leases an exclusive workroot, and is recorded in
a sqlite ledger with the spec, seeds, and git SHAs needed to re-execute it.
Missing surveillance weeks are treated as missing — dropped as rows with
calendar-true week offsets — never imputed.

## License

MIT — see [LICENSE](LICENSE).
