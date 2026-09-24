# Tests: `tests/` and `app/tests/`

Two pytest suites: `tests/` covers the `flubnf` package and the root scripts, `app/tests/` the console (`app/`).

## Running

| What | Command |
|---|---|
| Both suites, as CI runs them (no hub, no engine) | `FLUBNF_HUB=/nonexistent pytest tests/ app/tests/ -ra -o addopts=""` |
| Both suites, this machine's hub and engine | `.venv/bin/python -m pytest` (`testpaths` in `pyproject.toml`) |
| One file | `.venv/bin/python -m pytest app/tests/test_oracle_step.py` |

CI (`.github/workflows/tests.yml`) installs `pip install -e ".[app,dev]" bionetgen` and runs the first line on Ubuntu and, as experimental jobs, Windows (Python 3.11 and 3.12); a third job runs `setup.ps1` five ways. `.githooks/pre-push` runs the same command before a push to main. The slowest files are `tests/test_quantiles.py`, `tests/test_backtest.py` and `tests/test_fitting.py`.

## What skips, and why

| Missing on the machine | Skipped |
|---|---|
| FluSight hub clone (always, in CI) | hub-reading cases in `app/tests/test_core.py`, `test_model_metadata.py`, `test_playback.py`, `test_site_build.py`; `tests/test_simulate.py`, `test_covid_fit_wiring.py`, `test_engine_profiles.py` |
| `app/state` (sealed retrospectives) | `app/tests/test_site_build.py`, parts of `test_core.py`, `test_playback.py` |
| PyBNF engine | `tests/test_recency_weights.py` (imports `pybnf`); `app/tests/` fakes the fork in `conftest.py`, so nothing there needs it |
| JavaScriptCore (macOS only) | JS cases in `app/tests/test_player_js.py`, `test_retro_eta.py`, `test_retro_pf_name.py`, `test_sandbox_editor.py`, `test_forecast_retired_tab.py`, `test_template_date_helpers.py`, `test_contactmap.py` |
| POSIX (on Windows) | `tests/test_engine_bundle.py`, `test_reinstall_script.py`, `test_launcher_update.py` script runs; `app/tests/test_takeover_sweep.py`, parts of `test_pf_hardening.py`, `test_pf_shards.py` |
| CovidHub parquet | `tests/test_covid_vintage.py`, `test_reporting_breaks.py`, parts of `test_engine_profiles.py` |
| Lab-only records (`research/`, `FLUBNF_ORACLE_RECORD`) | `tests/test_oracle*.py` record cases, `test_gate_a_preregistration.py`, `test_bimodality_estimator.py`, `test_analogue_profile_boundary.py`, `test_wis_matches_team_scoring.py`; `app/tests/test_oracle_text.py` B2 case |
| Legacy `NAU_Influenza/` tree | `tests/test_auto.py`, `test_exp_files.py` |

`tests/test_reinstall_script.py` fails when run as root (`reinstall.sh` refuses root).

## Subject map: `tests/`

| Subject | Files (`test_*.py`) |
|---|---|
| Launchers and setup scripts | `engine_bundle`, `launcher_update`, `reinstall_script`, `first_run_sparse_hub`, `windows_controlled_folder_access`, `window_backend` |
| SIHRS templates and fit inputs | `min_template`, `seasonal`, `sampler_config`, `sihrs_anchor`, `particle_filter`, `profile_mult` |
| COVID profile seam | `profiles`, `engine_profiles`, `covid_fit_wiring`, `covid_vintage`, `unimodal_guard`, `submit_profile_target`, `reporting_breaks` |
| Analogue and donor paths | `analogue`, `analogue_profile_boundary`, `donor_paths`, `epiweek53` |
| Oracle SIHRS | `oracle`, `oracle_bank`, `oracle_mix` |
| Quantiles and WIS | `quantiles`, `forecast_validation`, `wis`, `wis_matches_team_scoring` |
| Research scripts and records | `worker_options`, `recency_weights`, `gate_a_preregistration`, `bimodality_estimator`, `error_decomp`, `season_report` |
| Legacy workspace CLI | `amcmc`, `analysis`, `auto`, `autoparam`, `backfill_priors`, `backtest`, `baseline_forecast`, `bngl_files`, `bounds_init`, `calibration`, `centers`, `compare`, `conf_files`, `config`, `decomp_act`, `diagnostics`, `doctor`, `exp_files`, `fitting`, `fringe_cases`, `historical_priors`, `phase`, `session`, `simulate`, `slope_tune`, `submit`, `validate`, `warmstart`, `weekly_loop`, `weekly_reference_date` |

## Subject map: `app/tests/`

| Subject | Files (`test_*.py`) |
|---|---|
| PF engine | `engine_contract`, `engine_preflight`, `engine_sampling_interval`, `perl_preflight`, `pf_hardening`, `pf_shards`, `swarm_carry`, `natgrowth`, `takeover_sweep`, `proc_priority` |
| Research members | `research_run`, `ensemble_n`, `analogue_completeness`, `reporting_model` |
| Groundhog and donor banks | `groundhog`, `analogue_splice`, `bank`, `flusurv`, `iliplus`, `nrevss` |
| Oracle step | `oracle_step`, `oracle_backfill`, `oracle_text` |
| Retrospective | `retro_archive`, `retro_config`, `retro_eta`, `retro_fit_level`, `retro_groundhog_only`, `retro_national`, `retro_pf_name`, `retro_player`, `resume_rerun`, `results_prep`, `sealed_records`, `week_quantiles`, `horizon_convention`, `cache_bounds` |
| Playback | `playback`, `playback_cache_atomic`, `player_js` |
| Scoring | `relwis_conventions`, `relwis_rule`, `us_national`, `categorical`, `floor` |
| Forecast runs | `run_integrity`, `run_results`, `run_timing`, `forecast_modes`, `forecast_retired_tab`, `fan_controls`, `busy_guard`, `sleep_guard`, `ledger_migration_race` |
| Submission and hub cards | `submit_join`, `submission_identity`, `model_metadata` |
| Reports and site | `report_bundle`, `report_parity`, `report_season`, `report_weekly`, `settings_block`, `outlook_toggle`, `site_build` |
| Storage | `storage`, `reclaim`, `browse_safety` |
| Server and launch | `app_launch`, `server_hardening`, `platform_setup_hint`, `audit_fixes`, `core`, `data_view` |
| Pages, design, accessibility | `pages`, `a11y_basics`, `a11y_modes`, `type_system`, `theme_and_harmonic`, `season_palette`, `reading_column`, `month_axes`, `design_batch3`, `template_date_helpers` |
| Sandbox | `sandbox`, `sandbox_data`, `sandbox_editor`, `contactmap` |

Fixtures in `app/tests/`: `flusurv_fixture.json`, `iliplus_fixture.json`, `nrevss_fixture.json`, `contactmap_bind.graphml`, `hub_model_metadata_schema.json` (sha-pinned).
