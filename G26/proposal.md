# G26 forecast-panel: proposal (B)
Base: origin/dev de64c26 (G23 merged; G24's #82 landed after this prototype was cut, no overlap)

Reproduced on a server from the prototype's tree against a private hub copy whose newest week (2026-10-24) has Arizona at 0 (set by hand in the copy) and Ohio collapsed (2 after 82), with curl and Chromium at 1280 px light and 390 px dark. The Groundhog runs here (FC-13's run); no Oracle. No invariance check: FC-13 changes what the box offers and what the record says, never the spec the engines read (below).

## FC-13
- Reproduced: yes. Data issues: Arizona at 0, Level chosen; Model settings "Newest weeks reading 0" = counted as unreported; Groundhog, all 53, Run. The run page read "Data issues … Arizona: reads 0 after 63, 69, 60; level" and "Missing-data rules: 2 weeks to 2026-10-24 treated as unreported (set aside (Forecast tab), trailing zero): Arizona 1, Ohio 1"; the box after the run still offered No forecast, Level, Extend and Blend for Arizona, Level selected.
- Root cause: the trailing-zero rule (`missing.tail_flags`) trims the newest zero before the Groundhog anchors, so its anchor is the last positive week and the state's zero rule never runs (`engines/analogue.py`: `zero_anchor` only when `anchor <= 0`); the box (`routes/forecast._data_issues_context`) and the record (`_data_choices`) never look at that rule.
- Fix: `routes/forecast._rule_covers_zero(row, knobs)`: a zero row whose newest weeks the rule would flag (`tail_flags` on the weeks the box shows, with `data.trailing_zero = missing` in the given knobs). The box, built from the last form's knobs, offers such a row only "Both from <week>" (selected; the rule's own effect) and "Leave out", and its "i" adds "; counted as unreported by the Newest weeks reading 0 setting". At run time (the normalized knobs), a zero rule posted for such a state (a stale form) is not recorded, as a zero state under the run-wide zero-anchor knob already is not, so the record never says a rule the engines did not use. The engines' input is unchanged: `rules_for` without the entry gives the run-wide rules, and the state's zero rule could not have applied (its anchor is positive once the zero is trimmed). Live after: Arizona's select offers Both from 10-17 (selected) and Leave out; the run page's "Data issues" row reads "1 state, 1 recommended, 0 changed; 1 set aside" (Ohio) beside the same "Missing-data rules" line, which names Arizona under "trailing zero" as before.
- Tests: test_data_issues `test_a_zero_state_the_trailing_zero_rule_covers_is_offered_only_what_applies` (the box's options and hint; the record without the state; the choice kept without the rule).
- Risk: the box reads the last form's knobs (a setting changed in the panel but not yet run shows in the box after the next run or refusal, as the rest of the form). No forecast number changes.
- For Ely: none

## FC-18
- Reproduced: yes. At 1280 px the Data issues selects were 123.6 px wide for a 96 px option text plus padding and arrow: "Both from 10-1". The phone's wider column showed it whole.
- Root cause: `tabs/forecast.css` `.fc-di .di-state select{flex:1 1 7.5rem}`: a 120 px basis the row's other item shares the spare width with.
- Fix: `flex:1 1 auto` (the select's basis is its longest option; the 7.5rem floor and 15rem cap stay). Live after: 240 px at 1280 px (the cap), 143 px on the phone, the text whole in both.
- Tests: test_forecast_mechanics `test_the_picker_follows_a_typed_date` pins the rule (with FC-25).
- For Ely: none

## FC-21
- Reproduced: yes. Replicates 0: the top notice "Not run: model settings: pf.replicates: 0 is outside 1 to 10." and the panel's "Replicates: 0 is outside 1 to 10."; Reff "2.5, 0.6": both read "… prior_ranges: Reff__FREE [2.5, 0.6] is not a valid uniform_var range."; jitter "abc": "'abc' is not a valid float."
- Root cause: `routes/forecast.run` flashes the raw KnobError and sets `ms_refused`, so the panel says it again; `forms._refusal_words` maps the key to its label only.
- Fix: `routes/forecast._settings_refused(request, e)`: the panel carries the refusal (`ms_refused`, one-shot) and the Forecast tab gets no second notice; a page without the panel (a model page's form) keeps one line, in the panel's words. The panel's alert leads with "Not run." (`kp.refused_lead`; "Not started." on the Retrospective), so the one message says the run did not start. `_refusal_words` says the engine's and the coercion's phrases plainly (`forms._PLAIN`): "the low end must be below the high end (2.5, 0.6)" (and "above 0 and …" for a log-uniform prior), "'abc' is not a number", "'2.5' is not a whole number", "needs two numbers, low then high", "is not a date (YYYY-MM-DD)". The same doubled notice on the dataset run (`datasets_ui.run_dataset`, the Forecast tab's `?source=` view) and on the Retrospective's Run (G23's `ms_refused`, #81) is removed the same way; the dataset run's first refusal, before its form is remembered, keeps its one line in the panel's words. The page lays its defaults under the remembered form (`form = {defaults, **_last_form}`): a refusal before the first run remembers only its reason, and the page used to raise KeyError on "locations" (the fresh-console case the tests now exercise).
- Live after: one alert on the page, under the panel's head: "Not run. Replicates: 0 is outside 1 to 10."; "Not run. Prior range for Reff: the low end must be below the high end (2.5, 0.6)."
- Tests: test_knobs_panel `test_a_refusal_names_the_setting_as_the_panel_does` (the plain phrases, the lead per tab); test_knobs_wiring `test_a_refused_knob_starts_nothing` and `test_a_number_the_browser_allows_is_refused_on_the_panel` read the panel's message and no flash; the retro, dataset-run and partial-week pins of the old flash updated to the panel's words (they pinned the doubled notice).
- Risk: scripts posting /run without a Referer land on /forecast (the fallback) and see the panel, not a flash; a model page's form still gets the line.
- For Ely: none

## FC-22
- Reproduced: yes. After the Reff refusal, Reset to defaults put every value back (badge "default") and the warning stayed.
- Fix: the reset handler hides `.fc-ms-refused` (`model_settings.js`). Live after: the message gone on reset, Reff back at "0.6, 2.5".
- Tests: test_knobs_panel's script pins.
- For Ely: none

## FC-23
- Reproduced: yes. The date field cleared: "No archived week on or before ."
- Fix: `noWeek('')` returns "Pick a date." (forecast.html). Live after: the one warn line "Pick a date." under the empty field, both widths.
- Tests: `test_a_saturday_with_no_week_says_why` gains the empty case.
- For Ely: none

## FC-25
- Reproduced: yes. Vintage: pick 2026-10-10, type 2026-09-26: the picker still read 2026-10-10, and re-choosing it fired no change.
- Fix: the date field's change handler sets the picker to the typed day when it is an archived week, else to its heading option (forecast.html). Live after: typing a Wednesday resets the picker; typing 2026-09-26 shows it; 2026-10-10 can be picked again.
- Tests: `test_the_picker_follows_a_typed_date`.
- For Ely: none

## Checks
- Targeted (test_data_issues, test_forecast_mechanics, test_knobs_panel, test_knobs_wiring, test_knobs, test_datasets_ui, test_partial_week_datasets, test_retro_forms, test_newest_reported, test_dataset_replay_knobs, test_forecast_aids, test_pages, test_fewer_marks, test_ui_layout): 406 passed. Full suite (FLUBNF_HUB=/nonexistent): 4214 passed, 159 skipped; the two tests/test_doctor.py failures are this container's Python and pass in CI. One other pin of the doubled notice, test_research_run's, reads the panel's message now (in the patch). ruff (app/ui) clean.
- Windows: text, CSS and script only.

## Patch
G26/proposal.patch (git diff origin/dev...proto/G26-B): routes/forecast.py, forms.py, routes/retro.py, datasets_ui.py, _model_settings.html, forecast.html, forecast.css, model_settings.js, and the tests named above.
