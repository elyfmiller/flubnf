# G28 retro-text: proposal (B)
Base: origin/dev 836698a (G24 merged)

Reproduced on a server from the prototype's tree with the state of an earlier group (a 2025-26 Groundhog replay of Vermont, zero rule abstain), by curl (the refusals, the import and delete flashes) and Chromium at 1280 px light and 390 px dark (the marks); a bundle exported from that season and imported again gave the imported archive row. Wording and marks only: no run path, no invariance check.

## RE-16
- Reproduced: yes. POST /retro/run with no zero rule: "Not started: choose what the Groundhog does when the newest week reads 0." with the tip "Set Newest week reading 0: abstain, level, extend or blend." (a Model settings knob's name, next to another knob, "Newest weeks reading 0").
- Fix: the tip names the form's control: "Set Groundhog when the newest week reads 0: abstain, level, extend or blend." (routes/retro.py).
- Tests: test_retro_words `test_the_zero_anchor_refusal_names_the_forms_control`.
- For Ely: none

## RE-18
- Reproduced: yes. With a complete season, its archives, a stopped and a live one, the rows carried "?" on relWIS, Wall time (repeating the value, "timed" with no noun), the live estimate, the status badges, sealed, "N weeks added", Resume and "N archived runs kept"; 4 to 6 per card.
- Root cause: each fact's explanation was a tip beside it, against the 2026-10-15 rule (badges and labels say the rest; one "i" per page).
- Fix (retro.html): the row marks go and their words stay where they matter. Wall time shows "10 s per week" (a hint after the value; one decimal under 10 s) with no tip. The live readout's basis ("estimate from 4 completed weeks", "Connection lost…", driven by retro_progress.js) is muted text after the readout, not a "?". The sealed badge reads "sealed · <its record's label>". The Resume button has no tip (the Run settings fold beside it shows what it resumes with). Kept, deliberately: the page-level marks the fewer-marks test decides (the heading, Import a replay, the engine alert, and a status badge's "?" in passing states); the two that carry the scoring convention, the relWIS stat's and the archived-runs heading's (`test_relwis_conventions` pins "relWIS vs FluSight baseline, ratio of sums" beside every score on the index, a recorded convention); and the "N weeks added" badge's, which names the weeks Resume would run (`test_shipped_vintages` pins it as what the season list says Resume runs).
- After: the index with a complete season and its archives shows 4 marks (page, engine alert, Import a replay, the archived-runs convention); with the hunt's states, 4 plus the relWIS convention and a passing status badge.
- Tests: `test_the_season_rows_carry_only_the_conventions_marks` renders the hunt's states (complete, sealed, added weeks, archives; a live one) and pins the set of marks and the words that replaced them; the pins of the wall-time tip's text (test_retro_fit_level, test_run_timing) read the hint, and of the basis's class (test_run_timing) its new class; test_resume_rerun pinned the Resume tip's text (the mark is the bug): it now pins that the button has none.
- Risk: the words moved into the rows are short; the convention marks are the decision's.
- For Ely: whether the two convention marks and the added-weeks badge's may also go (the convention could stand as words beside each score, the added weeks in the Run settings fold); left as their tests keep them.

## RE-19
- Reproduced: yes. /retro?tab=own: "Retrospective ?", "Dataset ?", "final data ?", "Groups ?", "Models ?", "Add FluSurv-NET donors ?", "Replays of <name> ?" and the Model settings "i"; the empty state's "Your data" heading repeated the page heading's words.
- Fix (_dataset_replay.html): the labels and the data badge stand alone; the FluSurv-NET line reads "Add FluSurv-NET donors (US influenza hospitalization-like data only)"; "Replays of <name>" and the empty state's "Your data" are plain headings; the replay rows' relWIS tip goes (the result page says the convention, as before). The page keeps its one explainer, the heading's "?" (its second sentence is this tab's), and the panel's "i".
- After: 2 marks on the tab (the page heading's and the upload box's "the file"), no sideways scroll on the phone.
- Tests: `test_the_your_data_tab_keeps_the_pages_one_explainer`; test_fewer_marks gains the tab ("/retro?tab=own": the page heading, the upload box's mark in passing); test_dataset_snapshots pinned the kind badge's tip text (the mark): it now pins the badge.
- For Ely: none

## RE-20
- Reproduced: yes. A text file uploaded as notzip.zip: "Not imported: incoming-12535-1794289088385.zip is not a zip file."; the path field set to a folder: "Not imported: retro: no such file."
- Fix: `_import_replay_file(src, replace, shown)` says the upload's own name in a refusal (the saved copy's name never shows); `replay_bundle.inspect_bundle` says "<path> is a folder, not a bundle." for a folder (the "no such file" wording for a missing file is unchanged, test_replay_bundle pins it).
- After: "Not imported: notzip.zip is not a zip file."; "Not imported: /…/retro is a folder, not a bundle."
- Tests: `test_an_import_refusal_names_the_upload_and_a_folder`.
- For Ely: none

## RE-21
- Reproduced: yes. Delete on an imported row: "This permanently removes the archived 2025-26 run from imported from vm on 2026-11-10: …"; the flash "Deleted the archived 2025-26 run from 2026-11-10 05:38 UTC" (the archive stamp, not where it came from).
- Fix: the row's Delete button carries `data-imported`, and the confirm reads "This permanently removes the 2025-26 run imported from vm on 2026-11-10: …" (an archived run's stays "the archived 2025-26 run from <when>"); the delete route names the run the same way before removing it (`replay_bundle.imported_label`): "Deleted the 2025-26 run imported from vm on 2026-11-10: 31 weeks, 91.7 KB freed."
- Tests: `test_an_imported_runs_delete_says_where_it_came_from`.
- For Ely: none

## RE-22
- Reproduced: yes. Resume asking for level over a season replayed with abstain: "They were replayed with modified: groundhog.zero_anchor=abstain (a86a7e3c); this run asks for modified: groundhog.zero_anchor=level (cace8e4a). …"; Archive: "Archived 31 weeks of 2025-26 as 2025-26__archived_20261110T053843Z; starting a fresh replay."; another scope: "… replayed over 1 location(s); this run asks for 6 with a different list."
- Fix: `routes/retro._settings_words(values)`: each non-default setting as the panel names it, "Newest week reading 0 = abstain", "Replicates = 5" (`knobs.BY_KEY` labels and `choice_word`), never a key or digest; "the default settings" when none. The archive flash: "Archived 31 weeks of 2025-26 (kept under its archived runs); starting a fresh replay." The scope line (`retro_settings.location_scope_change`, the CLI's too): "replayed over 1 location; this run asks for 6, a different list".
- After: "They were replayed with Newest week reading 0 = abstain; this run asks for Newest week reading 0 = level. Resuming would mix two configurations in one season. Archive or discard the existing results to run it."
- Tests: `test_settings_are_said_in_the_panels_words`.
- Risk: the words only; `_knobs.label` (the digest form) is still used by the records.
- For Ely: none

## RE-27
- Reproduced: yes. docs/RETROSPECTIVES.md: "**Import a replay** on the Retrospective tab (Settings card) takes the file …"; on the page it is its own card under Settings.
- Fix: "(its own card, under Settings)". Pinned in the settings-words test.
- For Ely: none

## Checks
- Targeted (test_retro_words (6), test_fewer_marks, test_retro_forms, test_retro_archive, test_relwis_conventions, test_dataset_replay_knobs, test_datasets_ui, test_pages, test_ui_layout, test_replay_bundle, test_season_page_player, test_knobs_wiring): 288 passed. Full suite (FLUBNF_HUB=/nonexistent, test_doctor deselected: this container's Python): 4205 passed, 159 skipped, 0 failed. ruff (app/ui) clean.
- Windows: text only.

## Patch
G28/proposal.patch (git diff origin/dev...proto/G28-B): routes/retro.py, core/replay_bundle.py, core/retro_settings.py, retro.html, _dataset_replay.html, docs/RETROSPECTIVES.md, app/tests/test_retro_words.py, test_fewer_marks.py.
