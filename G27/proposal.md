# G27 data-upload-text: proposal (B)
Base: origin/dev 836698a (G24 merged)

Reproduced on a server from the prototype's tree against the private hub copy whose newest week has Arizona at 0 and Ohio collapsed (the Data tab's Newest week tip), the stored Kids dataset (the dataset form's badge, no engine here), and the Data tab's check endpoint with four files (date,group,value with 987 / 1.234 / 12.345; a zip-headed "workbook"; 2 KB of binary; a plain three-row file); Chromium at 1280 px light and 390 px dark for the tooltip. Wording only: no run path, no invariance check.

## DA-09
- Reproduced: yes. /forecast?source=<dataset>: the badge "Groundhog (own data) only only: the particle-filter engine is not installed".
- Root cause: forecast.html joins `engine_names.analogue` (already "... only") with " only: ".
- Fix: the join is ": " (forecast.html). After: "Groundhog (own data) only: the particle-filter engine is not installed".
- Tests: test_dataset_upload_box `test_the_upload_words_are_short_and_say_what_each_button_does` (the template line).
- For Ely: none

## DA-15
- Reproduced: yes. /data's Newest week tip: "0 after 63, 69, 60: Arizona. Recommended: set aside (looks like a missed report)."; the Forecast select for Arizona: No forecast, Level, Extend 63 from 10-17, Blend, "Both from 10-17" (selected), Leave out.
- Root cause: `reported.CHOICE_WORDS["set_aside"]` is "set aside", the select's label (`OPTION_TEXT`) "Both from <week>".
- Fix: `CHOICE_WORDS["set_aside"]` reads "both from the week before" (reported.py; the words are used by the Data tab's tip only; the run page's records keep "set aside", their own vocabulary). After: "Recommended: both from the week before (looks like a missed report)."; the collapsed case "(looks like a partial report)".
- Tests: test_newest_reported's three pins updated (they pinned the mismatch).
- Risk: the tip's words only.
- For Ely: none

## DA-16
- Reproduced: yes. The "the file" tip beside Weekly CSV: 1,124 characters in five paragraphs, covering the hub card; "Dates as YYYY-MM-DD or M/D/YYYY" while the template uses M/D/YY (1/1/22).
- Fix: three short lines (440 characters): the shape (date, group, value; population optional; no group column: one series), the dates (YYYY-MM-DD, M/D/YYYY or M/D/YY, the template's; moved to the Saturday that ends each week) and formats (CSV, TSV or TXT, up to N MB), and the retrospective line (an as_of column or one snapshot file per as_of beside it; exports under non-hub names, never submitted). The column-alias list goes: a missing or ambiguous column is named by the check, with the mapping to choose. After: a 320 × 231 px tip at 1280 px, 320 × 201 px on the phone, no sideways scroll.
- Tests: the same test pins the tip under 500 characters, "M/D/YY (the template's)", and no alias list.
- Risk: none (words).
- For Ely: none

## DA-17
- Reproduced: yes. 987 / 1.234 / 12.345 with Values = detect: "... 1.234 is 1.234 as a rate or 1234 as a count. Choose whether the values are counts or rates; counts are written without thousands separators (1234)."; then counts: "The values were declared counts but 3 are not written as whole numbers ... write the numbers without them (1.234 as 1234)".
- Fix: the first message ends "If they are counts, write them without the dots (1.234 as 1234); if they are rates, choose rates." (checks.py `kind_ambiguous`), so choosing counts is not offered as the fix. The declared-counts message is unchanged (it is right once counts are chosen).
- Tests: test_dataset_lenient `test_dots_that_may_separate_thousands_ask_for_the_kind` and test_dataset_upload_box `test_numbers_that_read_two_ways_leave_the_kind_to_the_user` pin the new sentence.
- For Ely: none

## DA-20
- Reproduced: yes. A zip-headed file (an .xlsx): "The header holds NUL characters: the file is not text in an encoding FluBNF reads. Save it as CSV UTF-8." plus the note "Not UTF-8 text: read as Windows-1252 (a spreadsheet's usual CSV)."; 2 KB of binary: the long "mixes encodings" message with � characters.
- Root cause: `reading.validate` reads any bytes as text; the NUL header refusal comes from the reading, then the "not UTF-8" re-read adds its note.
- Fix: `parsing.not_text(head)`: a zip signature (PK) is "This looks like an Excel workbook (.xlsx), not a CSV: in Excel, save the sheet as CSV UTF-8."; control bytes throughout the first 4 KB (not tab, newline or return; at least 8 and 1 in 64; never UTF-16's or UTF-32's padding) is "The file is not text: it holds binary data. Save it as CSV UTF-8." `validate` says it before any reading (`_NotText`), one problem, no note. A stray NUL in a text cell is still read and shown as a cell (test_dataset_lenient's existing pin).
- Tests: test_dataset_lenient `test_a_workbook_or_binary_file_is_named_as_such`.
- Risk: the shared reader (Data tab, Sandbox upload, CLI): only files that could not be read before are named differently.
- For Ely: none

## DA-21
- Reproduced: yes. The "?" beside Forecast this / Replay this / Save only: "Each stores the dataset, then opens the Forecast tab (...) or the Retrospective tab's Your data (...). Nothing runs until you start it there."
- Fix: "Each stores the dataset. Forecast this then opens the Forecast tab (its newest week, every group); Replay this the Retrospective tab's Your data (its newest flu season, October to June); Save only stays here. Nothing runs until you start it." The Save only clause only where that button is (the Data tab; `where == "data"`).
- Tests: the same template test.
- For Ely: none

## Checks
- Targeted (test_dataset_lenient, test_dataset_upload_box, test_newest_reported, test_datasets_ui, test_pages, test_data_view, test_data_issues, test_sandbox_upload, test_problem_codes, test_fewer_marks, test_ui_layout, tests/test_dataset_cli): 407 passed. Full suite (FLUBNF_HUB=/nonexistent): 4219 passed, 159 skipped; the two tests/test_doctor.py failures are this container's Python and pass in CI; one pin of the old tooltip sentence (test_dataset_snapshots) updated after that run; the tip says "other columns are ignored" again (that pin), its file passing. ruff (app/ui, app/core/datasets) clean.
- Windows: text only; the binary test is bytes.

## Patch
G27/proposal.patch (git diff origin/dev...proto/G27-B): forecast.html, reported.py, _dataset_upload.html, checks.py, parsing.py, reading.py, _dataset_check.html, and the tests named above.
