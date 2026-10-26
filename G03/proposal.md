# G03 remembered-form: proposal (A)
Base: origin/dev c8103eb (G02 merged)

How I reproduced: two servers, #51's head (base) and my prototype, both on a hub copy whose newest week (2026-10-17) has Alaska reading 0, so the Data issues box shows (gap.02); one Chromium script (1280x900) walks all eight in order and prints the form's state (date, model, ticked boxes, the Locations chip, the Run row's badge, the knob values, gap.02). Every bug reproduced on the base as reported; the "after" column is the prototype.

## FC-02 (also: WI-01, MO-17)
- Reproduced: yes. All 53 Groundhog run started; during it: Vintage 2025-01-11, US only, donor window 4, Run models. Base: no notice; after the run the form held 2025-01-11, US only, window 4, "Differs: Locations, Groundhog donor window". The quick-run button on /model/analogue stayed enabled during the run (MO-17).
- Root cause: `routes/forecast.py` run_models stores the form (`_last_form.update` + `save_last_form`) long before the busy check under `_engine_lock`, which only appends to `_status["log"]` and redirects to /forecast#results with no flash; `model.html`'s quick-run button is a plain button (research_run.html's is off while running).
- Fix: run_models refuses first thing when `_status["running"]`: "Not run: a run is already in progress." (warn), back to the posting page, the form untouched (it keeps what the running run was given). The locked check (a start that slipped in between) says the same. The quick-run button is `disabled aria-describedby="md-busy"` while a run holds the engine: the page's existing "A run is in progress." alert above it says why, so no new "?" mark (research_run.html's reason button has one; I did not copy it). The guard modal's console-run kind is unchanged (adding a console conflict there would offer "stop and start this one", a new behaviour).
- After: the notice; the form after the run reads 2025-01-11 (that run's date), all 53, window 2, "Same as last run"; the quick-run button disabled during the run.
- Tests: test_remembered_form.py `test_a_run_pressed_during_a_run_is_refused_and_the_form_keeps_that_run`, `test_the_quick_run_button_is_off_while_a_run_holds_the_engine`.
- Risk: a re-run pressed during a run now lands back on its run page with the notice (it went to /forecast#results with nothing said). For Ely: none.

## FC-05
- Reproduced: yes. Vintage, 2025-01-18 (an archive gap), US only, Groundhog only, window 5, Run models. Base: "Not run: the hub archived no snapshot dated 2025-01-18. Nearest earlier: 2025-01-11."; date 2025-01-11 but no location ticked (the previous run's raw pick), window 2.
- Root cause: run_models returns from the date and data refusals (not a date; no data yet; archive gap) before `_last_form.update`.
- Fix: the form is stored right after the model-settings JSON is read and before every date/data refusal (the refusals then move the date to the week they offer, as before); a blank or non-date keeps the last date and stores the rest. Engine-name and repeated-knob refusals still store nothing (no form makes them).
- After: 2025-01-11, US only, Groundhog only, window 5 kept.
- Tests: `test_a_refused_date_keeps_the_other_choices` (the archive gap, then a blank date).
- For Ely: none.

## FC-07 (also: MO-04)
- Reproduced: yes. Quick run from /model/analogue with "Arizona, Ohio": base /forecast with no box ticked, empty chip, "Differs: Locations".
- Root cause: run_models stored the posted `locations` raw (`["Arizona, Ohio"]`); the comma split happens later, for the run only.
- Fix: a new `_form_locations(locations)` stores the pick as the checklist holds it: split on commas, each name in the hub's spelling by name or code (G02's lookup, now `_hub_names()` shared with `_location_list`), US as the national box's value ("US (national)"), and the 52 with US as `["all", "US (national)"]` (FC-09). A name the hub has not stays as typed, so the model page shows it back after G02's refusal.
- After: Arizona and Ohio ticked, "2 selected", "Same as last run"; the model page shows "Arizona, Ohio".
- Tests: `test_a_model_pages_typed_pick_ticks_the_forecast_checklist`.

## WI-12
- Reproduced: in the test (a last_form.json from an earlier process, then /model/analogue first): base shows the defaults ("all"); the Forecast tab restored it.
- Root cause: `forecast_aids.restore_last_form` is called only by the Forecast page route.
- Fix: `routes/models.py` model_page calls it too, before reading `_last_form` (it restores once per process, so whichever page comes first does it).
- Tests: `test_a_model_page_after_a_restart_shows_the_remembered_form`.

## FC-09
- Reproduced: yes. "Run again from the start" (POST /runs/{id}/rerun) of an all-53 run: base "52 + US selected", "all 53" unticked, "Differs: Locations".
- Root cause: the re-run posts the 53 by name and they were stored as such.
- Fix: `_form_locations` (above): the 52 and US are "all".
- After: "all 53", "Same as last run". The 52 without US stay a pick of their own (States only).
- Tests: `test_a_rerun_of_the_53_by_name_is_all_53_on_the_form`.

## FC-10
- Reproduced: yes. All 53, Groundhog only, Alaska "Leave out" in Data issues, Run; reload: base "Differs: Locations".
- Root cause: `forecast_aids.last_run_values` reads the spec's locations (51 + US), which are the pick after the box's omissions.
- Fix: last_run_values adds back the states the run's `extra.data_choices` left out ("omit"), so the comparison sees the pick the user made.
- After: "Same as last run".
- Tests: `test_a_state_left_out_in_data_issues_still_counts_as_picked`.

## FC-11
- Reproduced: yes. Model settings: Reset, Auxiliary donor bank = none, Own-state donor weight 0.8, US only, Groundhog only, Run; reload: base "Differs: Size-matched donor kernel" (the run's kernel 0, the panel 1).
- Root cause: with no auxiliary bank `_run_extra` records no `local_pools`: the Groundhog is the bare, pooled analogue ("the bare analogue stays the pooled form"), so the shipped own-state weight (0.5) and kernel (1) do not apply to it, yet the panel shows them as live rows and the Run row compares them with what the run recorded (0); a typed value would still be applied on top (`effective_local_pools`).
- Fix: `model_settings.js` turns the three donor-weight rows off (disabled) while the bank is "none": the pool weight (already ignored by the server then), the own-state weight and the kernel. A disabled field posts nothing, so the run is the bare form; the Run row already skips disabled fields; the panel counts none of them as changed; Reset puts the bank back first so they reset with the rest. nau.css dims an off row like a coming-later one (`.ms-later,.ms-row:has(> [data-knob]:disabled){opacity:.62}`), checked light and dark at 1280 and 390. The server and the CLI are unchanged.
- After: the three rows dimmed and off; "Same as last run".
- Tests: test_knobs_panel.py `test_no_auxiliary_bank_turns_the_donor_weights_off` (the script and the CSS, the suite's way for the panel script; the behaviour checked in Chromium above).
- For Ely (a note, not a blocker): from the panel, "no auxiliary bank" with an own-state weight or a kernel is no longer reachable (the CLI's --knob still is). It was never a shipped form; the bare analogue is research and records the pooled form.

## FC-12
- Reproduced: yes. Newest week, Alaska = Leave out, run; then a Vintage 2025-01-11 run; back to Real-time: base Alaska shows the recommendation ("set aside") again.
- Root cause: run_models overwrote `_last_form["data_choices"][newest]` with {} whenever the box posted nothing (off the newest week its fieldset is disabled; a model page has none).
- Fix: store the choices only when the box was posted (`gap._sha` present).
- After: Alaska still "Leave out".
- Tests: `test_the_data_issues_choices_survive_a_run_that_did_not_post_the_box`.

## Checks
- New tests: 9 (8 in test_remembered_form.py, 1 in test_knobs_panel.py); all 9 fail on #51's head and pass on the prototype.
- Targeted: the form, aids, panel, knobs, models, forecast, run, data-source, data-issues, oracle-step, busy, layout, marks, datasets, retro and pages files: 1028 passed, 10 skipped (Python 3.12). ruff F821/F823/F811/F401 on app/ui: clean.
- Output invariance: all-53 Groundhog run on 2026-10-17, #51's head and the prototype: md5 56da9201b416eb5c80317c849b55168e both.
- Note: run_models' first 150 lines move (the store goes before the date refusals); read the patch as "the same statements, reordered", plus the busy check and `_form_locations`.

## Patch
G03/proposal.patch (git diff origin/dev...proto/G03-A)
