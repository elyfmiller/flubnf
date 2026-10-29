# G14 sandbox-mechanics: proposal (B)
Base: origin/dev 697eab0

No engine here, so no sandbox fit could run: every bug was reproduced through the forms, the files and the page's script (curl and Chromium at 1280), SB-08 with 27 stand-in run folders (meta.json only), SB-12 through the guard's code path. No run-path file is touched, no invariance check. Windows: no path or encoding change.

## SB-02
- Reproduced: yes. POST upload-data with model_bngl "# MY EDIT…" and a 26 MB CSV: the report "The upload is larger than the 20 MB limit; nothing was read past it or stored." and model.bngl on disk without the edit. In the browser the submit clears the dirty flag, so no leave-page prompt either.
- Root cause: routes/sandbox.py refuses an over-cap body by its Content-Length before reading the form, so the editor's text never arrives; sandbox.js's submit handler clears `dirty` for every submit.
- Fix: the page refuses the file first: the CSV input carries `data-cap` (UPLOAD_MAX_BYTES, in the two contexts that render the pane), and the workbench form's submit handler, when the submitter is the Upload and load button and the chosen file is over the cap, prevents the post, keeps `dirty`, and shows a kit alert in the upload pane ("Not uploaded: the file is larger than the 20 MB limit. Choose a smaller file; your edits stay in the editor."). The server's own report (a post that bypasses the page) now says "…and unsaved edits in the editor were not saved."
- After (Chromium): the edit typed, a 26 MB file chosen, Upload and load: no post, the alert, the editor still reads "# MY EDIT"; a small file then saves the edits first and loads as before.
- Tests: test_sandbox_mechanics.py `test_an_upload_over_the_cap_is_refused_on_the_page_with_the_edits_kept` (the attribute, the script, the server's words).

## SB-03
- Reproduced: yes. Case 1 (vintage 2026-10-10, 2026-06-06 to 2026-10-17): "19 weeks of New York, 2026-06-06 to 2026-10-17 … 1 missing weeks dropped" and the holds row the same. Case 2 (settled, 2026-09-05 to 2026-12-31): "7 weeks … to 2026-12-31 … 10 missing weeks dropped".
- Root cause: sandbox_data._window counts every Saturday up to the requested end as dropped; fill_data records and reports the requested start and end.
- Fix: dropped counts the range's Saturdays with no value up to the newest week the source holds in the range (a week the source cannot hold yet is not missing; a gap inside the loaded weeks still counts); the sidecar and the flash carry the loaded first and last week. t still counts from the requested start (test_fill_keeps_calendar_offsets_anchored_like_the_console holds).
- After: "19 weeks of New York, 2026-06-06 to 2026-10-10" with no dropped note, the holds row "Rows: 19 weeks"; case 2 "7 weeks of Arizona, 2026-09-05 to 2026-10-17".
- Tests: `test_a_week_the_source_cannot_hold_yet_is_not_called_missing`, `test_the_loaded_range_is_reported_not_the_requested_one`; test_sandbox_data's Wyoming case (a range the source never reaches) still counts its 3.

## SB-06
- Reproduced: yes. Two uploads named cases.csv: the Source list reads "cases" twice (cases-cc49b9bfa955, cases-54acda40268d).
- Fix: sandbox_data.html's Source option adds the dataset's weeks when another dataset shares the name: "cases (2025-01-04 to 2025-02-22)" and "cases (2025-03-01 to 2025-04-19)"; a name used once stays as it is.
- Tests: `test_two_datasets_with_one_name_are_told_apart_in_the_source_list`.

## SB-08
- Reproduced: yes. 27 run folders: badge "25 runs", data-sb-delete "… and its 25 runs".
- Root cause: routes/sandbox.py keeps the newest 25 of the model's runs for the page.
- Fix: the page lists every run of the model (the cap goes): the badge, the list, Compare with and the delete prompt all see 27.
- Tests: `test_every_run_is_listed_and_the_delete_prompt_counts_them_all`.

## SB-09
- Reproduced: yes. With oracle_arizona_2026-10-17 present, the gallery suggests that name; Create: "Not created: a sandbox model named … already exists" and the form back at its first start.
- Root cause: sandbox.js suggestName ignores the models that exist.
- Fix: the script reads the existing models from the Copy of choices and appends _2, _3, … to a suggestion one of them has (as the examples get sir_example_2). After: the suggestion reads oracle_arizona_2026-10-17_2 and Create makes it. The refusal path for a hand-typed taken name is unchanged (the bug's expected names either).
- Tests: `test_a_suggested_name_is_free_and_a_copy_start_suggests_one` (the script's lines).

## SB-11 (medium confidence)
- Reproduced: yes. Oracle SIHRS start, Arizona, 2026-10-17, season start 2025-08-01: created without a word; data.exp 64 rows from 2025-08-02.
- Root cause: core/sandbox.py from_shipped refuses only a season start on or after the forecast date.
- Fix: a season start more than a year before the forecast date is refused: "Not created: the season start 2025-08-01 is more than a year before the forecast date 2026-10-17; the Oracle SIHRS fits one season (production starts 2026-08-01)". A start inside the forecast's own season (any day up to a year back) is still allowed.
- Tests: `test_an_oracle_start_more_than_a_year_back_is_refused`.

## SB-12 (medium confidence)
- Reproduced: by the code path (the engine cannot fit here): the guard refuses every POST /run while a sandbox fit is live, engine=analogue included, with "a sandbox fit holds the engine", and the sandbox refuses beside any console run with "a console run is fitting".
- Root cause: the two-way guard counts any console run and any sandbox fit, whatever engine each uses.
- Fix, within the group's note: the words. The console's refusal reads "Not started: a sandbox fit is running (<id>); the console runs one thing at a time." with the detail "Stop it from the Sandbox tab first, or wait for it to end."; the sandbox's reads "a console run is in progress". Neither claims an engine a Groundhog run never uses. The lock itself is unchanged: letting a Groundhog-only run and a sandbox fit overlap would change the shared engine lock, and no "Decided" entry allows it.
- Tests: `test_the_refusal_beside_a_sandbox_fit_says_what_the_console_waits_for`; test_sandbox_guard's pin of the old words updated.
- For Ely: SB-12: whether a Groundhog-only console run may proceed beside a sandbox fit (and a sandbox fit beside a Groundhog-only run). The refusal now says what it waits for; the lock stays one-at-a-time.

## SB-17
- Reproduced: yes. Start from > Copy of > sir_example: the Name field empties and Create is blocked.
- Root cause: the Copy of options carry no data-name, so the script's name() falls through to "".
- Fix: routes/sandbox.py gives each model a free copy name (_free_name, as the examples get theirs) and the option carries it: Copy of sir_example suggests sir_example_1.
- Tests: the SB-09 test pins the option's data-name.

## Checks
- Targeted: every app/tests/test_sandbox*.py, test_datasets_ui, test_busy_guard: 277 passed, 4 skipped; ruff gate clean.
- Live from the prototype: each bug's steps above.
- For Ely: SB-12 (the overlap), as above.

## Patch
G14/proposal.patch (git diff origin/dev...proto/G14-B)
