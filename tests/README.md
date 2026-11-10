# Tests: `tests/` and `app/tests/`

Two pytest suites: `tests/` covers the `flubnf` package and the root scripts, `app/tests/` the console (`app/`).

## Running

| What | Command |
|---|---|
| Both suites, as CI runs them (no hub, no engine) | `FLUBNF_HUB=/nonexistent pytest tests/ app/tests/ -ra -o addopts=""` |
| Both suites, this machine's engine (never its hub: `app/tests/conftest.py` points `FLUBNF_HUB` at a missing folder) | `.venv/bin/python -m pytest` (`testpaths` in `pyproject.toml`) |
| The same, plus the checks against a hub clone | `FLUBNF_TEST_HUB=~/GitHub/FluSight-forecast-hub .venv/bin/python -m pytest` |
| One file | `.venv/bin/python -m pytest app/tests/test_oracle_step.py` |

CI (`.github/workflows/tests.yml`) installs `pip install -e ".[app,dev]" bionetgen ruff` and runs the first line on Ubuntu and Windows (Python 3.11 and 3.12); a third job runs `setup.ps1` five ways (the default first, with an unknown `FLUBNF_ENGINE` in its environment, then `-Engine private`, recorded before any install and clearing an account value, whose record two runs keep, one over an environment that names public, then `-Engine public`), and `public-engine-install` installs the public engine for real on Windows and macOS from a wheel and lock CI builds (`public-engine-wheel`), on the default route with no engine named, checks on macOS that the private route leaves its venv alone, then on macOS fits one cell in it through FluBNF's own run path (`app/tests/test_engine_lwf.py`, `FLUBNF_TEST_PUBLIC_PYTHON`). All of them are required. `.githooks/pre-push` runs the same command before a push to main.

## The engine the suite runs

The public engine (lanl/PyBNF's Liu-West filter, `job_type = lwf`) is FluBNF's default; the private engine (the lab's PyBNF fork, `fit_type = pf`) is the fallback. Both suites pin the private engine: an autouse fixture in each `conftest.py` sets `FLUBNF_ENGINE=private` (whatever the shell exports), because about 90 test files encode its stub fork, and points `flubnf.settings.INSTALL_ROOT` at an empty folder, so the checkout's own `.flubnf.env` record never picks the engine. Tests of the default unset `FLUBNF_ENGINE`, so the public engine reaches the code past the selector by the default, never by a value that names it: the `public` fixture and `default_engine` in `app/tests/test_engine_lwf.py`, `default` in `test_engine_default.py`, `app/tests/test_engine_true_default.py` (a season's engine guard and build through settings' own dispatch), the runner's re-exec guard and job child in `test_runner_serve.py`, and doctor's public rows in `tests/test_doctor_engine_hub.py`; a few keep an explicit `public`. `tests/conftest.py` imports `flubnf.settings` itself, so even a file run alone never reads the checkout's record. The launcher tests strip `FLUBNF_*` from the scripts' environment and give each stand-in clone its record: `export FLUBNF_ENGINE=private` where they test the private route, none where they test the default.

## What skips, and why

| Missing on the machine | Skipped |
|---|---|
| FluSight hub clone (always: the suite reads none) | hub-reading cases in `app/tests/test_playback.py`, `test_site_build.py` |
| A clone named by `FLUBNF_TEST_HUB` | the clone checks in `app/tests/test_core.py`, `test_hubcheck.py`, `test_model_metadata.py`; the recorded sums in `test_experiment_summary.py`; `tests/test_sihrs_fit.py` |
| `app/state` (sealed retrospectives) | `app/tests/test_site_build.py`, parts of `test_core.py`, `test_playback.py`; the recorded sums in `test_experiment_summary.py` (the shipped 2024-25 replay) |
| JavaScriptCore (macOS only) | JS cases in `app/tests/test_player_js.py`, `test_retro_eta.py`, `test_retro_pf_name.py`, `test_sandbox_editor.py`, `test_forecast_retired_tab.py`, `test_template_date_helpers.py`, `test_contactmap.py` |
| POSIX (on Windows) | `tests/test_engine_bundle.py`, `test_engine_public.py`, `test_engine_switch_sh.py`, `test_reinstall_script.py`, `test_launcher_update.py`, `test_mac_app_bundle.py` script runs; `app/tests/test_takeover_sweep.py`, parts of `test_pf_hardening.py`, `test_pf_shards.py`, `test_codegen_cache.py` |
| Lab-only records (`research/`, `FLUBNF_ORACLE_RECORD`) | `tests/test_oracle*.py` record cases; `app/tests/test_oracle_text.py` B2 case |
| `ruff` | the app/ui lint case in `app/tests/test_ui_layout.py` |
| `FLUBNF_PUBLIC_REAL` (the `public-engine-install` CI job's wheel, lock and certificate) | `tests/test_public_engine_real.py`, the public engine's real install |

`tests/test_reinstall_script.py` fails when run as root (`reinstall.sh` refuses root).

## Subject map: `tests/`

| Subject | Files (`test_*.py`) |
|---|---|
| Launchers and setup scripts | `engine_bundle`, `engine_public`, `engine_switch_sh`, `windows_engine_switch`, `launcher_update`, `mac_app_bundle`, `reinstall_script`, `first_run_sparse_hub`, `windows_controlled_folder_access`, `window_backend` |
| SIHRS templates and fit inputs | `min_template`, `sihrs_fit` |
| Analogue and donor paths | `analogue`, `donor_paths`, `epiweek53` |
| Oracle SIHRS | `oracle`, `oracle_bank`, `oracle_mix` |
| Quantiles and WIS | `quantiles`, `baseline_forecast`, `wis`, `dashboard_score` |
| Console CLI | `doctor`, `doctor_engine_hub`, `dataset_cli`, `cli_panels` |
| Docs held to the code they describe | `docs_engine_cutover` |

## Subject map: `app/tests/`

| Subject | Files (`test_*.py`) |
|---|---|
| PF engine | `engine_lwf`, `engine_default`, `engine_true_default`, `engine_cutover_fixes`, `engine_contract`, `engine_preflight`, `engine_sampling_interval`, `perl_preflight`, `pf_hardening`, `pf_shards`, `swarm_carry`, `natgrowth`, `takeover_sweep`, `proc_priority` |
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

`app/tests/golden/problem_codes.json` holds every problem code and its tier (`{code: tier}`, `app/core/problem_codes.py`); it only grows, and `test_problem_codes.py` pins it.

`test_ui_layout.py` also keeps app/ui's modules honest with each other and with the tests: a name a test patches is defined by exactly the module it patches and bound by no other at import (a from-import copy would miss the patch); a name imported from another app/ui module is its owner's object; no module alias (`state`, `shared`, ...) is rebound in its file; tests reach a moved private name through its owner, never through `app.ui.server`, and never patch an app/ui module with `raising=False`; `server.py` only assembles (its own names are `app`, the warm start and the public `templates`, `VERSIONS` and `RUNNING_SHA`; it includes the tab routers in a fixed order, datasets_ui's last), and no module in `app/ui/routes` computes a path from its own `__file__`.
