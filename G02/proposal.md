# G02 run-input: proposal (B)
Base: origin/dev 4daf9bd (the prototype applies cleanly on 237900f; dev moved in research/ and docs/team only)

## FC-06
- Reproduced: yes. `POST /run` with `particles=1e4` (engine all, Ohio) answers HTTP 422 and the JSON `int_parsing` body; the browser's own check passes `1e4` for a number box (min 1000, max 100000, step 1). `replicates` and `weeks_to_drop` are declared the same way.
- Root cause: `app/ui/routes/forecast.py`, `run_models`: `weeks_to_drop: int = Form(0)`, `replicates: int = Form(3)`, `particles: int = Form(10_000)`; FastAPI refuses before the handler runs, so none of the handler's refusals (flash and redirect back) can happen.
- Fix: the three fields are `str = Form("")`. A new `app/ui/forms.py::_legacy_int(raw, field)` reads them the way the knobs read a whole number (`"10,000"` and `"10_000"` are numbers; `"1e4"`, `"2.5"`, `"one"` raise `KnobError` in the panel's words, `pf.particles: '1e4' is not a valid int`); blank is the knob's shipped value. It runs inside the existing `try` beside `_knob_raw`, so the refusal path is the one the panel already has: `Not run: model settings: ...`, `ms_refused` set (the panel opens on it), 303 back to the posting page. The range is left to `knobs.resolve` through `legacy=`, as before, so a value the engine does not use is still ignored for the run and kept on the form (`test_knobs_panel::test_a_groundhog_only_run_keeps_the_filters_settings` pins that). `members` and `weeks_to_nowcast` stay int fields: hidden, never typed.
- Tests: `test_knobs_wiring`: three new rows in `test_a_refused_knob_starts_nothing` (`particles=1e4`, `replicates=2.5`, `weeks_to_drop=one`: 303, flash, nothing started) and `test_a_number_typed_with_commas_is_read_and_a_blank_is_the_default`.
- Risk: the handler's three variables are ints at the same point as before (after the knob parse, from `kspec`); before it they were ints from FastAPI and are ints again from `_legacy_int`, so `_last_form` and `_kept_settings` see what they saw. Invariance check: yes (below).
- For Ely: none.

## FC-08 (also: MO-03, WI-02)
- Reproduced: yes. With `_run_all` captured: `locations=["arizona, Ohio"]` starts a spec with `['arizona', 'Ohio']` and the label `2 states`; `["Ohio", "Oiho"]` and `["Ohio", "Ohio"]` likewise (`2 states`); `["US+(national)"]` starts `['US+(national)']` as `1 state`. On the live server the run then ends `ok` with only Ohio's rows (the pipeline drops what the table has not). WI-02's duplicate case is the `["Ohio", "Ohio"]` row.
- Root cause: `forecast.py::_location_list` passes every non-US name through unchecked (`list(picked)`); the hub table is read only for `all`.
- Fix: `_location_list` reads the table once and, for a custom pick, maps each typed name to the hub's spelling by name or two-letter code without regard to case (`ohio`, `UT`, `district of columbia`), once (a repeat counts once); names the table has not raise `LookupError` naming them. `run_models` catches it before the generic `except Exception` and flashes `Not run: no location named 'Oiho'. Use state names or their two-letter codes, and US.` (warn, nothing started). US keeps today's rule (`is_us`, any of its spellings; the typed spelling is recorded, as a re-run needs). `all` is unchanged. Dataset runs have their own route (`datasets_ui._start_run`) and never pass here.
- Tests: `test_forecast_us_choice`: `test_a_typed_name_is_matched_to_the_hubs_spelling_once` (`["ohio, UT", "Ohio"]` -> `['Ohio', 'Utah']`) and `test_an_unknown_location_name_is_refused_and_nothing_runs` (`Ohio, Oiho`; `US+(national)`; `arizona` against the test's three-row table). One test pinned the bug: `test_oracle_step::test_the_run_route_accepts_the_field_and_the_rerun_passes_it` posted `locations="custom"` (the retro form's word) to `/run` and the run started on a location named `custom`; it now posts `["Ohio"]`, with a comment saying why (the PR must say so too).
- Risk: a re-run posts the recorded names (the table's spelling), so it resolves to itself. Tests that patch `load_locations` with a small table (`test_forecast_us_choice`) post names in it. Invariance: yes.
- For Ely: none.

## MO-07
- Reproduced: yes. `/models` and `/model/pf2s` render `name="replicates" type="number" ... min="1" max="9"`; `knobs.BY_KEY["pf.replicates"].hi` is 10 and the Forecast tab's field (`ks-pf-replicates`) takes 10.
- Root cause: `app/ui/templates/model.html:168` and `research_run.html:38` hard-code `max="9"`.
- Fix: `routes/models.py` passes `replicates_range = (lo, hi)` of the `pf.replicates` knob (imported inside the view, like the route's other late imports: a module-level import moved the pinned import order in `test_ui_layout`'s golden); both templates read `min="{{ replicates_range[0] }}" max="{{ replicates_range[1] }}"`. No wording change; the hidden Groundhog copy of the field is untouched.
- Tests: `test_models_tab::test_the_quick_and_research_forms_take_the_replicates_the_setting_allows` (both forms carry the knob's lo and hi; `max="9"` is gone).
- Risk: none beyond the two attributes. Invariance: n/a.
- For Ely: none.

## MO-22
- Reproduced: yes. From `/model/analogue` (Referer), `forecast_date=2026-10-21` (a Wednesday) starts the run for 2026-10-17 and lands on `/forecast#results` with no flash; the quick form is a bare date box.
- Root cause: `run_models` snaps the day through `resolve_anchor` with "the form already shows this anchor; no banner", which is true of the Forecast form only.
- Fix: once the run is queued, when the day snapped (`typed_day != forecast_date`) and the posting page is not the Forecast tab (new `_from_forecast_tab(request)`: the Referer path, read the way `shared._back` reads it), flash `Run for the week ending 2026-10-17, the newest data week on or before 2026-10-21.` It shows on the landing page (`/forecast#results`), beside the vintage notice when that one applies. A typed Saturday says nothing; a snap from the Forecast tab says nothing (its anchor line already does).
- Tests: `test_data_source::test_a_quick_run_from_a_model_page_says_which_week_it_ran` (Referer `/model/analogue` and `/models`: the flash; `/forecast`: none; a typed Saturday: none).
- Risk: one more flash on the Forecast tab after a quick run from a model page; nothing recorded changes. The other hint (a date box stepping by weeks) would need a Saturday origin in the browser and a non-Saturday remembered date would still post. Invariance: yes.
- For Ely: none.

## Checked
- Targeted: `test_knobs_wiring`, `test_knobs_panel`, `test_forecast_us_choice`, `test_models_tab`, `test_data_source`, `test_research_run`, `test_resume_rerun`, `test_audit_fixes`, `test_forecast_modes`, `test_forecast_mechanics`, `test_run_scope_wording`, `test_busy_guard`, `test_ui_layout`, `test_forecast_aids`, `test_pages`, `test_custom_run`, `test_datasets_ui`: 320 passed. `ruff check --select F821,F823,F811,F401 app/ui` clean.
- Live (a server from the prototype tree): `particles=1e4` -> 303 back to `/forecast` with `Not run: model settings: pf.particles: '1e4' is not a valid int.`; `locations=arizona, Oiho` -> `Not run: no location named 'Oiho'. ...`; `/models` and `/model/pf2s` carry `min="1" max="10"`; a Wednesday from `/model/analogue` with `arizona, ohio` -> the run for 2026-10-17 on Arizona and Ohio (`2 states`) and the flash above.
- Output: an all-53 Groundhog run on 2026-10-17 on dev 237900f and on the prototype gives the same file (md5 56da9201b416eb5c80317c849b55168e).
- Full suite (CI config, Python 3.13 here): first run 3445 passed, 154 skipped, 4 failed: the two doctor checks that fail on 3.13 on dev too, the `test_oracle_step` case above (now repointed), and my own refusal test reading a stale progress label from an earlier test (assertion dropped). The rerun after those two test fixes: 2 failed, 3447 passed, 154 skipped, 4 warnings in 278.60s (0:04:38); the 2 failures are the doctor's Python 3.13 checks, which fail on dev the same way (CI runs 3.11 and 3.12).
- Windows: no paths, encodings or line endings touched.

## Patch
G02/proposal.patch (git diff origin/dev...proto/G02-B)
