# G07 dataset-sufficiency: proposal (B)
Base: origin/dev 12281e7

All six reproduced on dev with a TestClient script (a 2-group file over
2023-08-05..2025-11-15, a 30-week date,count file, a one-row file, a
dataset with its vintages folder moved away, a garbage multipart body and
a 25-field post, the same bytes named 流感 data then 流行 data).

## DA-01
- Reproduced: yes. The check said "Ready to use: 2 groups, 120 weeks."; the
  run closed `ok` with exports {} and abstained {analogue: [North, South]},
  the Forecast tab's Latest run badge green; the replay said "No scored
  cells", "abstained on 20 group-weeks". The 30-week single file the same.
- Root cause: the Groundhog pools growth ratios from strictly earlier
  seasons within two calendar weeks, over every group (flubnf/analogue.py
  `_donor_cells`, MIN_DONORS 30, no season excluded on an own dataset):
  2 groups x 2 earlier seasons x 5 weeks = 20, so every group abstains;
  nothing counts the pool before a run, and `run_worker` closes "partial"
  only on filter failures.
- Fix: (a) `dataset_upload._preview` counts the pool for the newest week
  exactly as the engine draws it (`AN.donor_ratios` on the newest snapshot
  of each week, exclude_seasons=()); the preview shows "Donor weeks: 20 of
  the 30 the Groundhog needs" (warn state) and a warn badge "too few donor
  weeks for the Groundhog" beside "Ready to use"; the status line ends
  "; too few donor weeks for the Groundhog." (b) `custom_run.run` records
  `no_forecast: "every group abstained"` when no member that ran wrote a
  forecast; `datasets_ui.run_worker` closes such a run "partial"; the
  ledger chips (shared._outcome_items, datasets_ui.outcome_chips) say
  "no forecast: every group abstained". The replay page already says what
  it did.
- Tests: `test_a_file_too_thin_for_the_groundhog_says_so_before_it_is_stored`
  (upload box), `test_a_run_where_every_group_abstained_is_partial_and_says_why`
  (datasets_ui). Three pinned status lines on thin fixtures (3, 18 and 50
  weeks) now carry the suffix: the unqualified "Ready to use" on thin data
  is the bug.
- Risk: custom_run.py and runs.py touched (dataset runs only, and the
  Results table); invariance check: yes, run on the proto: md5
  56da9201b416eb5c80317c849b55168e, unchanged.
- For Ely: none.

## DA-03
- Reproduced: yes: "Newest week reading 0 — Groundhog (own data): 2 abstain"
  with the zero-week tip, for a newest week of 20 and 21.
- Root cause: `runs.zero_anchor_row` counts every note starting "no
  forecast" as a zero-week abstention; the donors note starts the same.
- Fix: `zero_anchor_row` counts a "no forecast" note only when it says
  "reads"; a new `runs.no_donors_row` ("Too few donors": "<member>: N
  abstain", the notes in its "?" tip, same shape as the zero row) follows
  the zero row in `results_html` and `dataset_results_html`.
  `anchor_notes_row` already leaves both out.
- Tests: `test_the_run_page_keeps_donor_abstentions_out_of_the_zero_week_row`
  (test_data_issues); the run-page assertions in the DA-01 test.
- Risk: the Results table only. For Ely: none.

## DA-08
- Reproduced: yes: "Ready to use: 1 group, 1 week.", sparkline "A: 1
  weeks"; the Forecast tab "No week of this dataset on or before that
  date."; the Retro tab empty From/To beside an enabled Replay.
- Root cause: nothing requires two weeks (`forecast_dates` = weeks()[1:]
  is empty); the label's plural is fixed.
- Fix: `checks._check_rows` adds the problem `single_week` ("The data hold
  one week (2024-01-06); a dataset needs at least two.", kind Weeks) once
  the file reads cleanly (`rep.ok`, as the "empty" problem is added: a
  stray quote or an ambiguous date that left one week is the problem to
  name); the check, the store and the CLI refuse it alike. `_preview`'s
  label reads "1 week".
- Tests: `test_a_one_week_file_is_refused_and_a_lone_week_reads_singular`.
  Five tests' one-week fixtures gained a second week (test_datasets_ui
  multi-target, test_datasets non-UTF-8 and 150 groups, test_dataset_lenient
  as_of proof and single-date formats): they used one week by accident,
  not as the thing tested.
- Risk: a one-week file is refused everywhere (CLI too). For Ely: none.

## DA-12
- Reproduced: yes: 500 on /data?source, /forecast?source, /retro?dataset
  (FileNotFoundError from vintage_path), /data 200 with 0 weeks.
- Root cause: `get_dataset` returns the Dataset (its meta is whole) and
  the page builders read its data file.
- Fix: `datasets_ui.damaged(ds)` ("is missing its data file; Storage can
  delete it" when `final_path` cannot be read); `choices()` and
  `retro_context` leave such a dataset out; the Data and Forecast routes
  flash "<name> is missing its data file; Storage can delete it; showing
  the FluSight hub." and show the hub, as they do for an unknown id;
  `retro_index` flashes the note and goes to the first whole dataset or the
  upload box. The Data tab's list keeps its 0-week row.
- Tests: `test_a_dataset_missing_its_data_file_is_a_note_not_an_error_page`.
- Risk: none outside damaged datasets. For Ely: none.

## DA-13
- Reproduced: yes: 500 "Internal Server Error" for both bodies; the check
  answered 400.
- Root cause: `upload()` does not wrap `_capped_form` as `check()` does.
- Fix: the same try/except: the Data page with "The upload could not be
  read; choose the file again." and 400.
- Tests: `test_an_unreadable_upload_is_answered_on_the_data_page`.
- Risk: none. For Ely: none.

## DA-18
- Reproduced: yes: the second upload redirected to the first dataset and
  flashed "Stored 流感 data: 1 group, 10 weeks."
- Root cause: `store._store` keys the id on slug(name) + digest and returns
  an existing id as is; both names slug to "data".
- Fix: kept the id rule (identical bytes, options and name are one
  dataset, as documented); `upload()` flashes "This file is already stored
  as 流感 data; opened it. Rename it on Storage, or store a changed file as
  流行 data." when the stored name differs from the typed one, instead of
  "Stored ...". No id changes, no second copy of the same bytes.
- Tests: `test_the_same_file_under_a_name_with_the_same_slug_says_where_it_is`.
- Risk: none. For Ely: none (the alternative, a second dataset under a
  name-aware id, changes every id minted for a renamed re-upload).

## Checks
ruff (the F gate) clean; the dataset tests (19 files) 586 passed; the
full suite on the proto: see compare.md (running at push time). Live on a
server from the proto: the check box at desktop and phone, light and dark
(badge, "Donor weeks" fact, the one-week problem), the thin run's page.

## Patch
G07/proposal.patch (git diff origin/dev...proto/G07-B)
