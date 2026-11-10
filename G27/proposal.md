# G27 data-upload-text: proposal (A)
Base: origin/dev 78e2843

How: a dev server (8811) and a prototype server (8810) on the private hub
copy with Arizona at 0 and Ohio at 2 on 2026-10-17 (for DA-15); a grouped
CSV (kids.csv) stored for DA-09; the upload check (POST
/data/datasets/check) with dec.csv (1.234, 2.500, 3.125, 4.750), a zip
named book.xlsx, and noise.bin (bytes 0 to 255); Chromium for the tip at
1280 px light and 390 px dark.

## DA-09
- Reproduced: yes: "Groundhog (own data) only only: the particle-filter
  engine is not installed" on /forecast?source=<kids>.
- Root cause: forecast.html adds " only: " to ENGINE_NAMES["analogue"],
  which is already "Groundhog (own data) only".
- Fix: forecast.html adds ": ".
- After: "Groundhog (own data) only: the particle-filter engine is not
  installed".
- Tests: test_data_upload_words.py `test_the_dataset_forms_badge_says_only_once`.

## DA-15
- Reproduced: yes: /data's Newest week tip: "0 after 67, 59, 29: Arizona.
  Recommended: set aside (looks like a missed report)."; the Forecast tab's
  select has no "set aside" ("Both from 10-10").
- Root cause: reported.CHOICE_WORDS["set_aside"] = "set aside" (read only
  by Report.details, the Data tab's tip).
- Fix: "both from the week before": the words of the Forecast tab's own
  "All zero states:" option for the same choice (routes/forecast
  `_ALL_TEXT`); the per-state option names the week ("Both from 10-10").
- After: "Recommended: both from the week before (looks like a missed
  report)."
- Tests: `test_the_data_tab_recommends_a_choice_by_the_boxs_name`; three
  pins in test_newest_reported updated (they pinned "set aside", the bug).

## DA-16
- Reproduced: yes: the tip is five paragraphs, 1,136 characters (556 px
  tall at 1280, 490 px on the phone, over the hub card); it says "Dates as
  YYYY-MM-DD or M/D/YYYY" while the template uses 1/1/22.
- Fix: two lines (340 characters): what a row is and the one-series case,
  the date forms (M/D/YY added) and the size limit; then the as_of and
  snapshot instruction the Snapshots box relies on (it has no tip of its
  own). The column names, separators and encodings move to README's
  own-data paragraph; the template's description and the non-hub-names
  line go (the template is its own example; the dataset's Forecast
  settings tip, "Forecasts export under non-hub names; never submitted.",
  and Output's Your data heading say it where the forecasts are).
- After: 170 px at 1280, 161 px on the phone; no sideways scroll.
- Tests: `test_the_weekly_csv_tip_is_two_short_lines` (two lines, under
  400 characters, M/D/YY, README holds the names and encodings);
  test_dataset_snapshots `test_the_box_takes_several_files_and_a_folder`
  pinned "other columns, except as_of, are ignored" in the tip: it now
  pins the as_of line.

## DA-17
- Reproduced: yes: detect: "... 1.234 is 1.234 as a rate or 1234 as a
  count. Choose whether the values are counts or rates; counts are written
  without thousands separators (1234)." Choosing counts is then refused.
- Fix: checks.py: "... as a count. Rates: choose rates. Counts: write them
  without the dots (1.234 as 1234)." (commas the same way, by the mark).
- Tests: `test_dotted_numbers_say_what_counts_need`; the two pins of
  "Choose whether the values are counts or rates" (test_dataset_lenient,
  test_dataset_upload_box) updated.

## DA-20
- Reproduced: yes, in both forms the report gives: noise.bin: "The header
  holds NUL characters ... Save it as CSV UTF-8." plus "Not UTF-8 text:
  read as Windows-1252 (a spreadsheet's usual CSV)."; a zip named
  book.xlsx: a long "The file mixes encodings: ... PK ... [Content_Types].xml
  ..." message.
- Root cause: reading.validate decodes whatever it is given; the cp1252
  retry adds its note whatever the second read found.
- Fix: a workbook's first bytes (PK\x03\x04 for .xlsx, the OLE header for
  .xls) are refused up front: "This looks like an Excel workbook, not a
  CSV file: save it as CSV UTF-8."; the cp1252 note is added only when
  the second read did not refuse the file as not text ("encoding" not in
  its codes). A sniff for NUL bytes up front was tried and dropped: a text
  file with one stray NUL in a cell is a cell problem (test_dataset_lenient
  pins it shown as a control character), not a refusal of the file.
- After: book.xlsx: the workbook line alone; noise.bin: the NUL line
  alone.
- Tests: `test_a_workbook_or_a_binary_file_is_named_not_decoded` (.xlsx,
  .xls, NUL header; no warning beside them; UTF-16 still reads).

## DA-21
- Reproduced: yes: "Each stores the dataset, then opens the Forecast tab
  ... or the Retrospective tab's Your data ..." beside Forecast this,
  Replay this and Save only.
- Fix: "Forecast this and Replay this store the dataset, then open ...;
  Save only stores it and stays here. Nothing runs until you start it
  there." (the Save only clause where Save only is shown).
- Tests: `test_the_buttons_tip_says_what_save_only_does`.

## Checks
- New app/tests/test_data_upload_words.py (6): each fails on 78e2843 and
  passes here; with the dataset, encoding, newest-week and Data issues
  tests: 567 passed, 4 skipped. ruff (the gate) clean.
- Full suite (FLUBNF_HUB=/nonexistent): 4225 passed, 160 skipped, 0 failed.
- Output check: not needed (no run path; reported.CHOICE_WORDS is read by
  the Data tab's tip only).
- Windows: the workbook sniff reads bytes; README and the template are
  ASCII.

## Patch
G27/proposal.patch (git diff origin/dev...proto/G27-A)
