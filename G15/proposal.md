# G15 deleted-runs-labels: proposal (A)
Base: origin/dev 78f0331

How: the same script on two fresh servers, one from dev and one from the
prototype: three Groundhog-only runs for Arizona on
2026-10-17 within one minute, then Storage > Delete on the newest
workroot, a results.json cut to 200 bytes, /runs/nope, and Clear the
ledger. Text read from the pages; Chromium screenshots at 390 px light
and 1280 px dark of the run page, Storage and Forecast after the delete
(no sideways scroll). A report archive needs a full run with the PF
engine, so one archive folder was made by hand (report.html,
archive.json) on both servers.

## FC-15 (also: OU-12, WI-13, ST-09)
- Reproduced: yes.
  - /runs: three rows "run 10-29 19:25".
  - The oldest run's page: "Run: 2026-10-17 · 10-29 19:25", then
    "Superseded. Output shows run 10-29 19:25 for 2026-10-24. Open run
    10-29 19:25", which names a different run with the same label (FC-15,
    WI-13).
  - Output: "run 10-29 19:27" beside the report and the file (OU-12).
  - Storage (ST-09): the ledger row reads "as of 2026-10-17 · run 10-29
    19:27"; the workroot row reads "Round 2026-10-24 (as of 2026-10-17)" and
    "run 2026-10-29 19:27"; the archive row reads "Weekly report and
    submissions · 2026-10-17". One run is named three ways, and
    same-minute rows read identically.
- Root cause:
  - shared.py `_run_label` stops at the minute; Output's `_run_when`
    takes that label's time.
  - storage.py `_ledger_parts` builds the same minute by hand.
  - The workroot row takes `run_display`'s "%Y-%m-%d %H:%M".
  - The archive row prints its folder's date.
- Fix:
  - `_run_label` reads the run's time to the second ("10-29 19:25:34");
    every label that uses it follows: the run page, the Superseded
    notice, Output, the Forecast tab, Models.
  - `_ledger_parts` and the workroot row take the same time from
    `_run_label` ("run 10-29 19:25:34"), so the ledger row and the workroot
    row read alike. `run_display` is unchanged; the workroot row only
    stops using its time when the id has one.
  - The archive row names its round as the workroot rows do: "Weekly
    report and submissions · Round 2026-10-24 (as of 2026-10-17)"
    (`_round_label`).
- Live after:
  - /runs: "run 10-29 19:34:02", ":05", ":07".
  - The oldest run's page: "Output shows run 10-29 19:34:07 for
    2026-10-24. Open run 10-29 19:34:07".
  - Output: "run 10-29 19:34:07".
  - Storage: the ledger row and the workroot row both read "run 10-29
    19:34:07"; the archive row reads as above.
- Tests: `test_run_labels_deleted.py::test_two_runs_in_one_minute_read_apart_everywhere`,
  `test_a_report_archive_names_its_round_as_the_workroot_rows_do`.
  The pins of the old labels are listed under Checks.
- Risk: label text only; ids, file names and links are unchanged. Every
  label grows by three characters; at 390 px the ledger labels wrap at
  their "·", as before. Invariance: no.

## FC-16 (also: ST-05, WI-07)
- Reproduced: yes, after Storage deleted the newest run's workroot:
  - Its page: Results "Submission files 1 file", "Weekly report written";
    the files card "No submission files"; the banner "Superseded. Output
    shows run 10-29 19:25 ...". Nothing says the files were deleted.
  - Forecast: the Latest run card "1 file" / "written"; the fans' badge
    "earlier run · newest has no forecasts".
  - Storage: the ledger row "1 submission", "report ✓" beside "on disk
    --".
- Root cause: Results (`runs.results_html`) and the ledger's facts
  (`shared._outcome_items`) read the outcome only; the run page's
  supersession does not know the files are gone; `fan_run` has no reason
  for it.
- Fix: one test, output.py `_files_deleted(run_id)`: neither the workroot
  nor an archive folder holds the run (`_run_folder`, which already finds
  an archived run's files). Where it is true:
  - the run page shows "This run's files were deleted in Storage." in
    place of the supersession notice;
  - `results_html(..., deleted=True)`: "Submission files deleted",
    "Weekly report deleted" (the run page and the Forecast card);
  - `_outcome_items(..., deleted=True)`: one "files deleted" fact in place
    of "N submissions" and "report ✓" (the Storage ledger);
  - `fan_run`: "earlier run · newest has its files deleted".
  A run whose archive still holds its files is not "deleted": Output and
  its page still serve them from there.
- Live after: as above on all three pages (screenshots: the run page at
  390 px light and 1280 px dark; the Storage ledger at 390 px).
- Tests: `test_a_run_whose_files_storage_deleted_says_so`.
- Risk: words in three places, only for a run with no files left.

## FC-19 (also: none)
- Reproduced: yes. results.json cut to 200 bytes: /runs/<id> returns 500
  (JSONDecodeError in the log); /runs/<id>/report, /forecast, /runs and
  /output return 200.
- Root cause: forecast.py `run_page` reads results.json with no guard.
- Fix: the read is guarded (ValueError, OSError, or not a JSON object);
  the page renders, and its results card says "This run's results file
  could not be read" in place of "No results stored for this run".
- Live after: 200, with that line.
- Tests: `test_a_run_page_with_an_unreadable_results_file_renders_and_says_so`.

## UI-17 (also: none)
- Reproduced: yes. /runs/nope: `<title>FluBNF · Output</title>`, tab
  Storage, heading "Run"; a found run: `<title>FluBNF · Run</title>`.
- Root cause: output.html's title block is fixed to "Output"; the run
  page's 404 uses Output's notice page.
- Fix: output.html titles a notice by its heading ("Run" here, "Run
  report" for the report's own 404). The tab stays Storage: an unknown
  id's page cannot know whether it was a real-time run (Forecast) or not,
  and "Storage lists the runs" is the notice's way on.
- Tests: `test_an_unknown_runs_page_is_titled_as_a_runs_page`.

## ST-13 (also: none)
- Reproduced: yes. After Clear the ledger, the On disk rows read
  "Unrecorded run" with no link; /runs/<id> renders them.
- Fix: runs.html links every workroot row to its run page, as the cap
  notice already says.
- Tests: `test_every_workroot_row_links_its_run_page_an_unrecorded_one_too`.

## Checks
- New `app/tests/test_run_labels_deleted.py` (6): all fail on 78f0331
  and pass here.
- Pins of the old behavior, each the bug's own symptom, updated:
  - the run's time to the minute: test_models_tab (the Forecasts card's
    tip), test_output_freshness (the report card's run link), test_storage
    and test_reclaim (the workroot row's "run 2098-01-18 09:30", which is
    ST-09's mismatch with the ledger row);
  - the archive row's title: test_archive_rule (it splits on the title);
  - the unrecorded workroot row unlinked ("no run page to link"):
    test_storage (ST-13).
- Targeted: test_output_run_pages, test_reclaim, test_forecast_aids,
  test_storage, test_storage_datasets, test_output_by_date,
  test_output_freshness, test_archive_rule, test_models_tab,
  test_console_qol, test_fewer_marks pass. ruff clean.
- Full suite (FLUBNF_HUB=/nonexistent): the first pass had 3556 passed,
  155 skipped and exactly the four pins above failing; they pass now. A
  second full pass is running and will be noted here.
- Invariance: not needed (no run path: labels, the run page, Storage).
- Windows: no paths, encodings or files written.

## Patch
G15/proposal.patch (git diff origin/dev...proto/G15-A)
