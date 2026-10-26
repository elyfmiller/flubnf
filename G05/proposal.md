# G05 no-engine: proposal (B)
Base: origin/dev 695155d (G03 merged; G04 is PR #53, at CI: no overlap, G04 touches `run_stop` and the stop reads, G05 the engine checks)

This container has no particle-filter engine (`_pf_engine_state()` is `absent`), so every bug reproduced live on a server from dev; the "broken" state (a venv and fork without pf.py) is covered by tests through the same one word.

## FC-03 (also: MO-05, WI-09)
- Reproduced: yes. Live: `POST /run engine=pf` (Ohio): 303 to `/forecast#results`, the run recorded `ok`, "Oracle SIHRS fits: none (no engine)", no submission file, a Groundhog fan on the Forecasts card. `/models` offered "Run Oracle SIHRS only" and `/model/pf2s` "Start research run" the same way (MO-05, WI-09).
- Root cause: `routes/forecast.py` `run_models` accepts any engine in `ENGINES`; `pipeline._run_all` skips the filter when `_pf_engine_state()` is `absent` (`pf_skipped`, the Tier A path that `test_engine_preflight` pins for "Both") and ends ok; nothing checks that the Oracle alone, or the research run (the two-strain member), has an engine to run on.
- Fix: `run_models`, right after the engine-name check and before anything is remembered: with the engine not `ready`, `engine == "pf"` or `members == 3` is refused, `Not run: the Oracle SIHRS needs the particle-filter engine, which is not installed on this machine.` (`absent`) or `..., whose install is incomplete.` (`broken`), back to the posting page. "Both" keeps the Tier A path (the Groundhog alone, the record saying so). The Forecast form disables the "Oracle SIHRS only" option and says it under Model (`fc-pf-off` badge: `Groundhog only: the Oracle SIHRS engine is not installed on this machine`, or `Oracle SIHRS engine install incomplete`). `/models` (the Oracle page) shows an alert (`md-engine`) in the quick-run card and its button is `disabled aria-describedby="md-engine"` (the G03 pattern); `/model/pf2s`'s Start research run is the existing reason button with the engine reason. `routes/models.py` and the Forecast page pass `pf_state`.
- Tests: `test_no_engine.py`: `test_the_oracle_alone_is_refused_without_the_engine` (absent and broken; pf and members=3; the Groundhog alone and the engine-ready case still run), `test_the_forecast_form_says_when_the_oracle_cannot_run`, `test_the_model_pages_offer_no_oracle_run_without_the_engine`.
- Risk: tests that post `engine=pf` or `members=3` to `/run`, or `engine=pf` to `/retro/run`, on an engine-less machine (CI) with the worker faked now read the engine as `ready` through one `monkeypatch.setattr(ui_pipeline, "_pf_engine_state", lambda: "ready")` in their capture helpers: `test_research_run`, `test_knobs_wiring` (the run capture and three replay posts), `test_engine_build`, `test_resume_rerun`, `test_remembered_form`, `test_server_hardening` (the replay race). Eight lines, no assertion changed. Invariance: yes (below).
- For Ely: none.

## FC-04
- Reproduced: yes. Live: the form showed "Engine: Particle filter" and no notice; "Both", all 53: the Running card read "engine: both models (Oracle SIHRS and Groundhog)", "replicates 3", "particles 10,000", Fits done "0 of 159" throughout; the record afterwards "Groundhog only (no PF engine on this machine)".
- Root cause: `run_models` sets `expected_total` for `all`/`pf` whatever the engine; `pipeline._run_all` sets the card's settings from the spec alone (`spec_settings(spec)`), while the record's wording comes from the outcome's `pf_skipped`.
- Fix: `expected_total` only when the engine is `ready`; `_run_all` passes the skip (`{"pf_skipped": "engine venv not installed (Tier A)"}`) to `spec_settings` when the filter is wanted and the engine is `absent`, so the card reads "engine: Groundhog only (no PF engine on this machine)" with no replicates or particles, as the record does. The form's badge (FC-03) says it before the run.
- Tests: `test_both_without_the_engine_runs_the_groundhog_alone_and_says_so` (the record keeps `all`; `expected_total` None, 3 with the engine), `test_the_running_card_names_the_groundhog_alone_without_the_engine` (the settings as the Groundhog sees them mid-run).
- Live after: `/api/progress` during "Both": `total 0`, settings `engine: Groundhog only (no PF engine on this machine)`.

## FC-17 (also: ST-03, WI-06)
- Reproduced: yes. Live `/runs`: a Groundhog-only run (pf_skipped "analogue-only run") carried the chip "PF skipped (no engine)".
- Root cause: `shared._outcome_items` words every `pf_skipped` as "no engine"; `runs.py` tells the reasons apart.
- Fix: the chip reads the reason: `Groundhog only` (tip: "A Groundhog-only run: the Oracle SIHRS was not asked for.") when the skip says `analogue`, else the existing "PF skipped (no engine)". `test_fewer_marks`'s pin (`pf_skipped: True` reads "PF skipped (no engine)") still holds.
- Tests: `test_the_ledger_chip_reads_the_skips_reason`.

## RE-02
- Reproduced: yes. Live: `POST /retro/run season=2025-26 engine=pf mode=archive knob.groundhog.zero_anchor=level` with no engine: 303 and the refusal only after the change; on dev the route accepts the preset (it checks `retro.ENGINES` alone).
- Root cause: `routes/retro.py` `retro_run` never asks `_pf_engine_state()`; `retro.run_season` logs each failed week to `failures.log` and finishes `done`.
- Fix: `retro_run` refuses `engine == "pf"` with the engine not `ready`, right after the engine-name check and before the archive step: `Not started: the Oracle SIHRS needs the particle-filter engine, which is not installed on this machine.` (or `..., whose install is incomplete.`), detail "Choose Groundhog only, or install the engine." `retro.run_season` collects the failed weeks and, when no week completed and at least one failed, finishes `error: <the first failure>` (the card's error badge shows it) instead of `done`; a season with completed weeks finishes `done` as before.
- Tests: `test_a_replay_with_the_oracle_preset_is_refused_before_anything_is_archived` (the season's record untouched, no archive made), `test_a_season_whose_every_week_failed_ends_in_error_naming_the_first`.
- Not done: showing `failures.log` on the card for a season that completed some weeks; the hint's third part, a surface change beyond the bug's steps.

## RE-23
- Reproduced: yes. Live `/retro` without the engine: the Oracle preset selected and Run off.
- Fix: `retro.html` marks the Oracle preset selected when `engine_ok`, the Groundhog-only preset otherwise; the alert above the page and the button's reason are as they were. `engine_ok` stays `PY_ENGINE.exists() and PYBNF.exists()` (a half-installed engine is caught by the route's refusal, RE-02).
- Tests: `test_the_retrospective_form_preselects_the_preset_that_can_run`.

## Checked
- `test_no_engine` (10, all failing on the pre-fix code) and the related files (`test_engine_preflight`, `test_fewer_marks`, `test_models_tab`, `test_research_run`, `test_busy_guard`, `test_retro_eta`, `test_retro_config`, `test_retro_groundhog_only`, `test_engine_build`, `test_forecast_modes`, `test_pages`, `test_ui_layout`, `test_knobs_wiring`, `test_remembered_form`, `test_data_source`, `test_design_batch3`, `test_relwis_conventions`, `test_resume_rerun`, `test_a11y_basics`, `test_storage`, `test_season_run_marks`, `test_sandbox_guard`, `test_run_integrity`, `test_server_hardening`): 477 passed, 3 skipped before the last test fix; `test_server_hardening` 21 passed with it. `ruff check --select F821,F823,F811,F401 app/ui` clean.
- Live (a server from the prototype): the refusal for `engine=pf`; the form's badge and the disabled option; "Both" running as `total 0` with the Groundhog-only settings; the Oracle page's alert and off button, the research page's reason; `/runs` chips "Groundhog only" and "PF skipped (no engine)" side by side; `/retro/run engine=pf` refused.
- Output: an all-53 Groundhog run on 2026-10-17 on dev 695155d and on the prototype gives the same file (md5 56da9201b416eb5c80317c849b55168e).
- Full suite: running; counts in a second commit.
- Windows: no paths or encodings; the templates' changes are attributes and text.
- Marks: the Oracle page's alert has no "?"; the research page's reason button is the existing one; the Forecast badge is a lock badge like the dataset form's.
- For Ely: none.

## Patch
G05/proposal.patch (git diff origin/dev...proto/G05-B)
