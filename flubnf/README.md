# flubnf/: the science package and the `flubnf` CLI

Each module's docstring opens with its role tag; this page groups them. `flubnf/templates/` has its own [index](templates/README.md).

## CLI (`flubnf --help`, defined in `cli.py`)

| Panel | Commands |
|---|---|
| Console | `app` (console, native window or browser), `window` (native window only), `doctor` (`doctor.py`) |
| Replay & verification | `retro <season>` (`app/core/retro.py`), `groundhog retro` (`app/core/groundhog.py`), `oracle backfill`, `oracle reproduce` (`app/core/oracle_backfill.py`), `site build` (`app/core/site_build.py`) |
| Donor banks | `bank build`, `bank verify`, `bank show` (`bank.py`, [data/README.md](../data/README.md)) |
| Legacy DE/AMCMC workspace | `init`, `fetch`, `update-exp`, `update-files`, `analyze`, `backtest`, `weekly-job`, `score-team`, `validate-submission`, `clean-cache`, `record-season`, `backfill-priors`, `tune-slope`, `baseline-score`, `compare`, `run`, `status` |

`cli.py` file order: legacy commands, launch plumbing (takeover, ports, window watchdog), then the current commands.

## SHIPPED (used by the console, `app/`)

| Module | Role | Main callers |
|---|---|---|
| `settings.py` | machine paths (`HUB`, `BNG`, `PY_ENGINE`, `PYBNF`), `check()` for doctor, `load_locations` | nearly every `app/core` module, `cli.py` |
| `analogue.py` | calendar analogue: donor ratios and paths, spliced quantiles | `app/core/engines/analogue.py`, `oracle*.py` |
| `bank.py` | committed donor banks in `data/banks/`: read (digest verified), build, manifest | `app/core/engines/analogue.py`, `oracle_mix.py`, `cli.py bank` |
| `flusurv.py` | FluSurv-NET donor stream (the Groundhog's shipped bank) | `bank.py` |
| `iliplus.py` | ILI+ donor stream (research preset) | `bank.py` |
| `nrevss.py` | NREVSS typed-influenza data layer | `flusurv.py`, `iliplus.py` |
| `oracle.py` | the Oracle SIHRS member: closed-form growth blend on the filter's samples | `app/core/oracle.py` |
| `oracle_bank.py` | admissions growth-path donor pool, manifest and digest | `oracle.py`, `oracle_mix.py`, `app/core/oracle.py` |
| `oracle_mix.py` | shipped Oracle donor bank: admissions and FluSurv-NET growth, half and half | `app/core/oracle.py`, `oracle.py` |
| `sihrs_fit.py` | per-state SIHRS model inputs (`StateSetup`, `materialize_model`, `write_exp`); its AMCMC half is legacy | `app/core/engines/pf.py`, `app/core/data.py`, scripts |
| `sihrs_priors.py` | sourced parameter provenance for the SIHRS | `app/core/engines/pf.py`, `app/core/site_build.py` |
| `natgrowth.py` | national-growth term for the PF `natg` research variant | `app/core/engines/pf.py` |
| `quantiles.py` | `FLUSIGHT_QUANTILES`, the 23 levels; the rest serves the legacy DE path | `app/core/scoring.py`, `retro.py`, legacy modules |
| `wis.py` | weighted interval score | `app/core/scoring.py`, `retro.py`, `relwis.py` |
| `baseline.py` | FluSight-baseline construction (every relWIS denominator) | `app/core/scoring.py` |

## RESEARCH (tests, scripts or the COVID seam only)

| Module | Role | Reached from |
|---|---|---|
| `particle_filter.py` | in-Python reference particle filter (not the shipped engine) | `scripts/pf_run.py`, tests |
| `simulate_sihrs.py` | in-Python mirror of the SIHRS model | `profile_mult.py`, tests |
| `profile_mult.py` | closed-form `mult` profiling | `scripts/profiled_fit_run.py` |
| `profiles.py` | `DiseaseProfile`: influenza and COVID as data | `app/core/engines/profiles.py`, `covid_fit.py` |
| `covid_fit.py` | COVID fit wiring over `sihrs_fit` | `app/core/engines/profiles.py` |
| `covid_vintage.py` | vintage-true COVID truth from the CovidHub parquet | `app/core/engines/profiles.py` |
| `unimodal_guard.py` | refuses one-epidemic-per-season logic under COVID | COVID seam |
| `error_decomp.py`, `reporting_breaks.py`, `season_report.py`, `seasonal.py` | analysis helpers | tests only |

## LEGACY (DE/AMCMC workspace loop behind the legacy CLI commands)

| Module | Role |
|---|---|
| `config.py`, `paths.py`, `state.py`, `session.py`, `constants.py` | workspace config (`FLUBNF_*` env prefix), layout, ledgers, state metadata |
| `fetch.py`, `exp_files.py`, `bngl_files.py`, `conf_files.py` | CDC CSV fetch; per-state `.exp`, `.bngl`, `.conf` files (Alabama templates) |
| `auto.py`, `analysis.py`, `results.py`, `runs.py`, `pybnf_engine.py` | analyze-and-apply loop, PyBNF output parsing and runs |
| `fitting.py`, `simulate.py`, `bounds_init.py`, `centers.py`, `phase.py` | in-Python DE SIR fitter and its helpers |
| `amcmc.py`, `autoparam.py`, `warmstart.py`, `weekly_loop.py`, `slope_tune.py` | AMCMC trajectories, warm start and slope tuning |
| `weekly_job.py`, `backtest.py`, `baseline_forecast.py`, `compare.py`, `calibration.py`, `decomp_act.py`, `diagnostics.py`, `fringe_cases.py`, `historical_priors.py`, `backfill_priors.py` | weekly job, backtests, baselines, calibration and priors |
| `flusight.py`, `submit.py`, `validate.py` | legacy submission parsing, CSV builder, schema check (`flubnf validate-submission`) |
| `doctor.py` | `flubnf doctor`; checks mostly target the legacy workspace |

## Data

| Path | Use |
|---|---|
| `data/locations.csv` | packaged locations table when the hub's is missing (`settings.load_locations`) |
| `sandbox_examples/` | the Sandbox's example models, each `model.bngl`, `data.exp`, `priors.conf` (`app/core/sandbox.py`) |
