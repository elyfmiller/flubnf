# G03 remembered-form: proposal (B)
Base: origin/dev c8103eb (G02 merged; the prototype was built on fix/G02-run-input, so the patch is the diff from dev)

Reproduced first, on dev with G02: every bug, live (a server from dev) or with the new tests run against the pre-fix code (all eight fail there, pass with the change).

## FC-02 (also: WI-01, MO-17)
- Reproduced: yes. Live: an all-53 Groundhog run, then at once a second POST /run (vintage 2026-01-10, Ohio, bandwidth 4): 303 to /forecast#results, no flash, nothing queued, and the form and last_form.json now hold 2026-01-10, Ohio, bandwidth 4 beside the running all-53.
- Root cause: `run_models` stores the form (`_last_form.update`, `save_last_form`) long before the busy check under `_engine_lock`, which only logs. The guard's `console-run` kind checks retrospectives and sandbox fits, never a console run, so the buttons' click goes to the server (MO-17).
- Fix: a busy check right after the engine check, before anything is remembered: `Not run: a run is already in progress (2026-10-17 · all 53 jurisdictions).` (the label when there is one), back to the posting page; the check under the lock (the race) flashes the same, which also logs it as before. The guard's `console-run` kind now includes `consoleConflict`, so Run models and a quick run during a console run raise the modal (stop it, or cancel), as a replay's button does.
- Tests: `test_data_source::test_a_run_during_a_run_is_said_and_leaves_the_form_alone`; `test_busy_guard::test_a_console_run_is_a_conflict_for_the_run_buttons_too`.
- Risk: the Forecast tab's own Run models during a run now raises the modal instead of a silent redirect; the hint text is the existing one ("A console run stopped now restarts from scratch."). Invariance: the run path is touched (ordering only); checked below.

## FC-05
- Reproduced: yes (test on the pre-fix code): a Saturday the archive has not, posted with US only, Groundhog only, bandwidth 5: the refusal moved the date and the form kept the previous run's locations, model and settings.
- Root cause: the date refusals (`observed_source` failing) return before the form is stored.
- Fix: the form is stored right after the busy check and the knob fields are read (`_knob_raw`), before the anchor and date refusals, so a refusal keeps every other edit; the refusals still move the date to the nearest earlier week. The unknown-location and no-location refusals follow the date refusals as before (the audit test pins the date refusal first).
- Tests: `test_data_source::test_a_refused_date_keeps_the_other_edits`.

## FC-07 (also: MO-04) and FC-09
- Reproduced: yes. FC-07 live: the quick run's one string `Arizona, Ohio` was remembered as `['Arizona, Ohio']` (no box ticked; `Differs: Locations`). FC-09 by test: a re-run posts the 52 names and `US` one by one and the form held them so.
- Root cause: the raw posted list is stored; the comma split and the hub's spelling happen later; `locKey()` reads 52 + US as a custom pick while `last_run_values` reads it as `all`.
- Fix: new `_form_locations(locs_list)`: the run's resolved list as the checklist holds it: `["all"]` for the 52 and US, else the hub's names plus `US (national)` for the national box. Stored (and kept in last_form.json) instead of the raw list. A typed name the hub has not (G02's refusal) keeps the typed names on the form, where the model page shows them to be fixed.
- Tests: `test_data_source::test_the_form_remembers_locations_as_the_checklist_holds_them` (two names in one string; the 52 + US as a re-run posts them; `all`; Ohio + US; US only; the kept file; a typo).
- Live: after a quick run of `Arizona, Ohio` the Forecast checklist ticks Arizona and Ohio.

## FC-10
- Reproduced: yes (test): a run whose Data issues choice left Alaska out records 51 states + US, which `last_run_values` reads as a custom pick, so the unchanged `all 53` form reads `Differs: Locations`.
- Root cause: `forecast_aids.last_run_values` reads `spec.locations` (after the omission).
- Fix: the states the record's `data_choices` marked `omit` are added back before the pick is read, so the pick is the one the form made.
- Tests: `test_forecast_aids::test_a_state_left_out_in_data_issues_is_still_the_forms_pick`.

## FC-11
- Reproduced: yes (Python, dev): an aux = none run with own share 0.8 records `groundhog.kernel_sd` as `0` while the panel's default is `1`, so the untouched form reads `Differs: Size-matched donor kernel`.
- Root cause: with no auxiliary bank `_run_extra` records no `local_pools`, so the bare analogue runs the pooled form (kernel off, own share 0 unless typed); the panel shows the shipped form's defaults (0.5, 1), and `last_run_values` compares the record's effective values against them. `test_knobs::test_effective_bare_analogue_is_modified_and_drops_the_weight` pins that the record calls those rows modified (own_share 0, kernel_sd 0): the record is right and stays.
- Fix: in `last_run_values` only: with aux = none, an own-state row the run did not type (`groundhog.own_share`, `groundhog.kernel_sd` absent from `extra["knobs"]`) is left out of the comparison; a typed one is compared as now. The panel's two rows stay as they are (the hint's other option, hiding or re-defaulting them when aux = none, would move the panel's default logic into the page script; not taken).
- Tests: `test_forecast_aids::test_without_an_auxiliary_bank_untouched_own_state_rows_are_no_difference` (none: both left out; own share typed: compared, kernel left out; the shipped bank: both compared as 0.5 and 1).

## FC-12
- Reproduced: yes (test): saved choices for the newest week were replaced with `{}` by a run that posted no box (a model page's run) or a vintage run.
- Root cause: `if isinstance(gap_fields, dict) and newest:` writes `_last_form["data_choices"]` on every run; `_gap_form` returns a dict even when nothing was posted.
- Fix: the saved choices are replaced only by a form that carried the box (`gap._sha` posted) for the week it is for (`forecast_date == newest`).
- Tests: `test_data_source::test_data_issues_choices_survive_a_run_that_did_not_post_the_box` (a model page's run; a vintage run with the box; the newest-week run with the box replaces them).

## WI-12
- Reproduced: yes. Live: after a restart `/model/analogue` showed Locations `all`; after one visit to `/forecast` it showed the remembered `Ohio`.
- Root cause: `restore_last_form` runs in `forecast_page` only.
- Fix: `routes/models.py` calls it too before reading the form (once per process, as it is written).
- Tests: `test_forecast_aids::test_a_model_page_restores_the_kept_form_after_a_restart_too`.

## Checked
- The related files: `test_knobs`, `test_knobs_wiring`, `test_knobs_panel`, `test_forecast_us_choice`, `test_models_tab`, `test_data_source`, `test_data_issues`, `test_oracle_step`, `test_research_run`, `test_resume_rerun`, `test_audit_fixes`, `test_forecast_modes`, `test_forecast_mechanics`, `test_forecast_aids`, `test_ui_layout`, `test_busy_guard`, `test_pages`, `test_run_integrity`, `test_console_qol`, `test_missing_data`: 498 passed before the new tests, 62 passed in the three files with them (8 new; all 8 fail on the pre-fix code). `ruff check --select F821,F823,F811,F401 app/ui` clean.
- Live (a server from the prototype): FC-02 (the flash with the running run's label; the form and last_form.json unchanged), FC-07 (the checklist ticks Arizona and Ohio after a quick run), WI-12 (the model page shows the remembered list right after a restart).
- Full suite (Python 3.13 here): first run 3 failed, 3460 passed, 154 skipped: the doctor's two 3.13 checks (as on dev) and `test_server_hardening::test_concurrent_run_posts_start_exactly_one_engine_run`, which counts the log's "already in progress" lines and found two (the lock path logged and flashed; a flash is logged too). Fixed: the lock path flashes only, one line; the hardening, data-source and guard files pass (71). The rerun: 2 failed, 3461 passed, 154 skipped (the doctor's 3.13 checks only). Output invariance: an all-53 Groundhog run on 2026-10-17 on dev c8103eb and on the prototype gives the same file (md5 56da9201b416eb5c80317c849b55168e).
- For Ely: none. Note: MO-17's "button stays enabled" is met by the guard (a click raises the modal), not by disabling, the way the replay button stays clickable (`test_retro_run_button_clickable_while_running`).

## Patch
G03/proposal.patch (git diff origin/dev...proto/G03-B)
