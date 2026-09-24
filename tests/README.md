# Tests: `tests/` and `app/tests/`

Two pytest suites: `tests/` covers the `flubnf` package and the root scripts, `app/tests/` the console (`app/`).

## Running

| What | Command |
|---|---|
| Both suites, as CI runs them (no hub, no engine) | `FLUBNF_HUB=/nonexistent pytest tests/ app/tests/ -ra -o addopts=""` |
| Both suites, this machine's hub and engine | `.venv/bin/python -m pytest` (`testpaths` in `pyproject.toml`) |
| One file | `.venv/bin/python -m pytest app/tests/test_oracle_step.py` |

CI (`.github/workflows/tests.yml`) installs `pip install -e ".[app,dev]" bionetgen ruff` and runs the first line on Ubuntu and, as experimental jobs, Windows (Python 3.11 and 3.12); a third job runs `setup.ps1` five ways. `.githooks/pre-push` runs the same command before a push to main.

## What skips, and why

| Missing on the machine | Skipped |
|---|---|
| FluSight hub clone (always, in CI) | hub-reading cases in `app/tests/test_core.py`, `test_model_metadata.py`, `test_playback.py`, `test_site_build.py`; `tests/test_sihrs_fit.py` |
| `app/state` (sealed retrospectives) | `app/tests/test_site_build.py`, parts of `test_core.py`, `test_playback.py` |
| JavaScriptCore (macOS only) | JS cases in `app/tests/test_player_js.py`, `test_retro_eta.py`, `test_retro_pf_name.py`, `test_sandbox_editor.py`, `test_forecast_retired_tab.py`, `test_template_date_helpers.py`, `test_contactmap.py` |
| POSIX (on Windows) | `tests/test_engine_bundle.py`, `test_reinstall_script.py`, `test_launcher_update.py` script runs; `app/tests/test_takeover_sweep.py`, parts of `test_pf_hardening.py`, `test_pf_shards.py` |
| Lab-only records (`research/`, `FLUBNF_ORACLE_RECORD`) | `tests/test_oracle*.py` record cases; `app/tests/test_oracle_text.py` B2 case |
| `ruff` | the app/ui lint case in `app/tests/test_ui_layout.py` |

`tests/test_reinstall_script.py` fails when run as root (`reinstall.sh` refuses root).

## Subject map: `tests/`

| Subject | Files (`test_*.py`) |
|---|---|
| Launchers and setup scripts | `engine_bundle`, `launcher_update`, `reinstall_script`, `first_run_sparse_hub`, `windows_controlled_folder_access`, `window_backend` |
| SIHRS templates and fit inputs | `min_template`, `sihrs_fit` |
| Analogue and donor paths | `analogue`, `donor_paths`, `epiweek53` |
| Oracle SIHRS | `oracle`, `oracle_bank`, `oracle_mix` |
| Quantiles and WIS | `quantiles`, `baseline_forecast`, `wis` |
| Console CLI | `doctor`, `doctor_engine_hub`, `dataset_cli`, `cli_panels` |

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
| Server and launch | `app_launch`, `server_hardening`, `platform_setup_hint`, `audit_fixes`, `core`, `data_view`, `ui_layout` |
| Pages, design, accessibility | `pages`, `a11y_basics`, `a11y_modes`, `type_system`, `theme_and_harmonic`, `season_palette`, `reading_column`, `month_axes`, `design_batch3`, `template_date_helpers` |
| Sandbox | `sandbox`, `sandbox_data`, `sandbox_editor`, `contactmap` |

Fixtures in `app/tests/`: `flusurv_fixture.json`, `iliplus_fixture.json`, `nrevss_fixture.json`, `contactmap_bind.graphml`, `hub_model_metadata_schema.json` (sha-pinned).

`app/tests/golden/ui_routes.json` is the console's route table, middleware, Jinja additions and import profile, captured at 029c028 for `test_ui_layout.py` (and the GET count `test_browse_safety.py` walks); regenerate it only for a deliberate change: `python app/tests/test_ui_layout.py --write-golden`.
