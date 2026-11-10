# G30 forecast-text: proposal (A)
Base: origin/dev de4eb1f (applies to fb4fa7f unchanged; G28 touched other files)

Live checks on two servers (8810 dev, 8811 prototype) over a private hub copy whose 2026-10-17 week has Alaska unreported (row removed), Arizona at 0 after 67 and Ohio at 2 after 75 (collapsed). Runs: Groundhog, all 53, Arizona set to Level; an override run (own-state weight 0.4, hub names, a reason); a Vintage run on Saturday 2024-06-01.

## FC-26 (Settings card marks and the issues said 3 to 4 times)
- Reproduced: yes. /forecast before a run: 7 marks (Settings "i", the newest line's "?", the box's "i", three per-state "i", the panel's "i"). After the run: 10 (the Latest run Results add "?" on Unreported newest weeks, Newest week reading 0 and Data issues). The Latest run card said the issues in Run settings ("3 states, 2 recommended, 1 changed: Arizona level") and in three Results rows ("1 location anchored earlier", "1 level", "3 states, 2 recommended, 1 changed; 1 set aside, 1 zero-anchor level").
- Root cause: `_newest.html` check() always adds its "?"; `_data_issues.html` has the count badge with a four-paragraph toggletip, and an icon_tip per state; `runs.results_html` appends anchor_notes_row, zero_anchor_row and data_issues_row independently, and data_issues_row repeats followed_line, which spec_settings already shows.
- Fix:
  - `_newest.html` check() takes `tip=True`; forecast.html passes `tip=not data_issues`: with the box under it, the line keeps its counts and loses its "?" (the box's rows name each state).
  - `_data_issues.html`: no count badge and no toggletip (the line above counts); no per-state "i" (the flag stays, now `id="di-flag-<fips>"`, and describes the select). Its explanation moves to Methods' existing fold "A newest week that reads 0, collapses, or was not reported" (what lists a state; each choice; the recommendation rule). The Settings "i" gets one line, only when the box shows: "Data issues: each state is preset to the recommended choice, for this run only. What each choice does" (a link to /methods#mt-newest). The unused `facts` leaves the box context (the Data tab's newest-week tip keeps the two facts).
  - `runs.results_html`: the states chosen in Data issues are left out of anchor_notes_row and zero_anchor_row (new `skip=`), so those rows show only what the box did not cover (a vintage run, the run-wide rule). data_issues_row is the one row for the chosen states: what came of them ("1 set aside, 1 level, 1 anchored earlier", plus "N not applied (the data changed)"); its "?" lists each state's issue and choice and the engine's note for it. The count against the recommendations stays in Run settings only. With no choices record it returns None (the old zero-anchor-only case was a second statement of zero_anchor_row).
- After: /forecast 2 marks before a run, 3 after (Settings "i", panel "i", Results' Data issues "?"). Results: "Data issues 1 set aside, 1 level, 1 anchored earlier"; Run settings "3 states, 2 recommended, 1 changed: Arizona level".
- Tests: `test_forecast_text.py::test_with_data_issues_the_settings_card_keeps_two_marks`, `::test_results_say_the_data_issues_in_one_row`. Pins of the old marks updated (they are the bug): test_data_issues (the box test), test_newest_reported (the Forecast line's tip).
- Risk: runs.py is on the invariance list: display only. Invariance run: dev fb4fa7f and the prototype both 56da9201b416eb5c80317c849b55168e.
- For Ely: none.

## FC-27 (raw keys in run summaries)
- Reproduced: yes. Run page and Latest run: "Alaska: no row; carry. Arizona: reads 0 after 67, 59, 29; level. Ohio: reads 2 after 75; set_aside. Arizona: 2026-10-17 reads 0; zero-anchor level." and "1 zero-anchor level"; the box flag "no row".
- Root cause: data_issues_row writes `st["choice"]` raw; `missing.choices_line` counts the rule string "zero-anchor <rule>"; `reported.REASON_TEXT["no row"]` is "no row"; data_issues_label falls back to the raw choice for all but set_aside and omit, and says "zero-anchor rule <rule>".
- Fix: `reported.REASON_TEXT["no row"]` = "not reported" (the box flag, the Data tab's tip, new records; an old record's "no row" is read as "not reported"); `reported.CHOICE_WORDS["carry"]` = "from the last reported week"; data_issues_row and data_issues_label say choices through CHOICE_WORDS (set_aside "both from the week before", abstain "no forecast"); choices_line counts a zero-anchor rule by its word ("2 level", abstain as "no forecast"); engine notes drop the "zero-anchor " prefix where shown (`runs._note_words`); the run-wide rule reads "Groundhog when the newest week reads 0: level" (the Run form's label, as G28 used).
- Tests: `test_forecast_text.py::test_run_summaries_say_choices_in_the_boxs_words`; pins updated: test_data_issues (3), test_newest_reported (5, "No row" to "Not reported").
- Risk: REASON_TEXT is also the `what` recorded with a run and its left-out reason on Output's coverage: words only. Invariance as above.
- For Ely: none.

## FC-28 (the panel shows engine internals)
- Reproduced: yes. The panel's "Fixed by the model definition" fold lists oracle.identity_rule R_EITHER, oracle.smoother c3log, oracle.prereg 67c9fa49a1959083, pf.engine_keys, pf.starting_values DEFAULTS_BLOCK, epiweek_53 52.5, gamma 2.1875; "4 coming later" is a fold of disabled rows; hints read "fewer than 3 breaks rule 3", "Liu-West kernel scale h; the sealed record ran 0.30", "Pins rho*mult and i0: ...", "the seal ran 2".
- Root cause: `_model_settings.html` renders kp.locked and the LATER rows; the four knobs' help in `knobs.py`.
- Fix: the panel drops both folds (and the macro's `group` tag, the CSS and the JS selector that only they used). Methods' Model settings card gains a fold "Fixed by the model definition" (setting, why, value), from `knobs.panel("forecast")["locked"]`; its settings table already tags the coming-later rows. Hints: Replicates "Seeded filter runs per jurisdiction, pooled; per-state numbers ship with 3 or more."; Kernel jitter "How far each fitted value is nudged between weeks, so the particles stay varied." (the Sandbox's words), note "The Liu-West kernel scale h; the sealed record ran 0.30."; Seed denominator "Sets the reporting rate and first infections from the admissions to date or the expected total.", note starts "It pins rho*mult and i0."; Groundhog donor window "Donor weeks within this many epiweeks of the forecast week.", note "The sealed record ran 2." The notes show on Methods only. No default, range or value changes.
- Tests: `test_forecast_text.py::test_the_panel_lists_only_what_a_student_can_set`; test_knobs_panel updated (the later rows and the fixed list are now asserted on Methods).
- Risk: knobs.json (the CLI) is unchanged apart from the help strings. `knobs.panel()` still returns locked (the CLI test reads it).
- For Ely: none.

## FC-29 (the gap wording)
- Reproduced: yes. Saturday 2024-06-01 (archive gap 2024-04-27 to 2024-11-16): "Not run: the hub archived no snapshot dated 2024-06-01. Nearest earlier: 2024-04-27." with "Such gaps are real, usually holiday weeks."; the Settings "i" says "any day anchors on the latest archived week on or before it".
- Fix: the tip line reads "Forecast date: a day anchors on the latest archived week on or before it, except a Saturday the archive skipped, which is refused." The refusal's detail names holidays only for a gap of one or two weeks; else "The nearest earlier snapshot is 5 weeks before it." (`routes/forecast.py` run_models).
- Tests: `test_forecast_text.py::test_the_date_rule_and_the_gap_refusal_say_what_happens` (a skipped Saturday and a five-week gap).
- For Ely: none.

## FC-30 (role=tab pills)
- Reproduced: yes (markup: role=tablist, role=tab, aria-selected, no tabpanel or arrow keys).
- Fix: `<div role="group" aria-label="forecast mode">`, each button `aria-pressed`, setMode sets aria-pressed; nau.css styles `.pill.mode[aria-pressed="true"]` beside the existing aria-selected rule, which the Sandbox's model-view tabs (a real tablist) still use; `.modes > [role=group]` keeps the flex row.
- Tests: `test_forecast_text.py::test_the_mode_pills_are_a_group_of_pressed_buttons`.

## FC-33 (run page: files twice, two headings)
- Reproduced: yes. Override run: the Modified card "Files named: hub names, by override" and Run settings "files: hub names, by override"; "RUN SETTINGS" then "Settings".
- Fix: `runs.settings_html` omits the `<strong>` when the title is empty; run.html passes `title=""`. The run page route drops the "files" pair when the run is modified (its card says it). The weekly report (report_settings) keeps the files row: it is read without the app.
- Tests: `test_forecast_text.py::test_the_run_page_names_a_modified_runs_files_once`.

## Checks
- Tests: the 7 new tests each fail on dev. Targeted (knobs, panel, data issues, newest week, marks, data source, pages, ui layout, site build, Methods, output, forecast, remembered form, design batch, weekly report, datasets): 730 passed. ruff (the gate) clean.
- Live: screenshots at 1280 light and 390 dark of the Settings card (no sideways scroll), Methods' two folds.

## Patch
G30/proposal.patch (git diff origin/dev...proto/G30-A)
