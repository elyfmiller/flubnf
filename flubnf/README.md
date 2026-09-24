# flubnf/: the science package and the `flubnf` CLI

Each module's docstring opens with its role tag; this page groups them. `flubnf/templates/` has its own [index](templates/README.md).

## CLI (`flubnf --help`, defined in `cli.py`)

| Panel | Commands |
|---|---|
| Console | `app` (console, native window or browser), `window` (native window only), `doctor` (`doctor.py`), `knobs` (`app/core/knobs.py`), `dataset validate`, `import`, `list`, `delete` (`app/core/datasets.py`) |
| Replay & verification | `retro <season>` (`app/core/retro.py`), `groundhog retro` (`app/core/groundhog.py`), `oracle backfill`, `oracle reproduce` (`app/core/oracle_backfill.py`), `site build` (`app/core/site_build.py`) |
| Donor banks | `bank build`, `bank verify`, `bank show` (`bank.py`, [data/README.md](../data/README.md)) |

`cli.py` file order: help panels and root options, `doctor` and `knobs`, launch plumbing (takeover, ports, window watchdog), `app`, `window` and `retro`, then the sub-apps.

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
| `sihrs_fit.py` | per-state SIHRS model inputs (`StateSetup`, `resolve_state`, `materialize_model`, `write_exp`) | `app/core/engines/pf.py`, `app/core/sandbox.py` |
| `sihrs_priors.py` | sourced parameter provenance for the SIHRS | `app/core/engines/pf.py`, `app/core/site_build.py` |
| `natgrowth.py` | national-growth term for the PF `natg` research variant | `app/core/engines/pf.py` |
| `quantiles.py` | `FLUSIGHT_QUANTILES` and `QuantileForecast` | `app/core/scoring.py`, `retro.py`, `ensemble.py`, `engines/analogue.py` |
| `wis.py` | weighted interval score | `app/core/scoring.py`, `retro.py`, `relwis.py` |
| `baseline.py` | FluSight-baseline construction (every relWIS denominator) | `app/core/scoring.py` |
| `baseline_forecast.py` | persistence baseline, the relWIS denominator of custom-dataset runs | `app/core/custom_run.py` |
| `doctor.py` | `flubnf doctor` environment checks | `cli.py` |

Removed 2026-09 (legacy DE/AMCMC CLI, COVID seam, research helpers): git history and lab archive.

## Data

| Path | Use |
|---|---|
| `data/locations.csv` | packaged locations table when the hub's is missing (`settings.load_locations`) |
| `sandbox_examples/` | the Sandbox's example models, each `model.bngl`, `data.exp`, `priors.conf` (`app/core/sandbox.py`) |
