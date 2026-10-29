# G15 deleted-runs-labels: proposal (B)
Base: origin/dev 697eab0

Reproduced on a server from dev with two Groundhog runs seconds apart, a workroot deleted in Storage, a truncated results.json, /runs/nope and a ledger row removed. No run-path file is touched (the run page, labels, templates and the ledger view), so no invariance check. Windows: no path or encoding change.

## FC-15 (also: OU-12, WI-13, ST-09)
- Reproduced: yes. Two runs in one minute: /runs reads "run 10-29 19:10" for both; the second's page says "Superseded. Output shows run 10-29 17:23 … Open run 10-29 17:23" where several runs carry that label.
- Root cause: shared._run_label and storage._ledger_parts print the run's start to the minute (the id carries seconds).
- Fix: both print the second: "2026-10-17 · 10-29 19:18:17" and the ledger's "run 10-29 19:18:17"; Output's _run_when and every page that calls _run_label follow (the report card, the file rows, the supersession notice, the Forecast card, the Storage rows). ST-09's three spellings on Storage are the round label (Output's words), the ledger parts and the report-archive title, each for its own place; they now share the same time string.
- Tests: test_deleted_runs_labels.py `test_run_labels_read_to_the_second`; the pins in test_models_tab updated (the id's seconds, 09:31:00).
- Risk: every run label gains ":SS". For Ely: none.

## FC-16 (also: ST-05, WI-07)
- Reproduced: yes. After Storage deletes the newest run's workroot: its page says "Submission files 1 file", "Weekly report written", "No submission files", "No results stored for this run" and "Superseded. Output shows run …"; the Forecast card "1 file / written" and the fan badge "earlier run · newest has no forecasts"; the ledger row "1 submission · report ✓" beside "on disk --".
- Root cause: the Results rows come from the ledger outcome (what the run wrote), the files card from disk, and nothing says the folder is gone; run_supersession compares what Output serves and calls the run superseded.
- Fix: the run page knows its folder is gone (no workroot and no archive holding the run: output._run_folder) and says so in one alert, "This run's files were deleted in Storage; its ledger row is the record.", in place of the supersession notice; results_html takes files_gone and its two rows read "1 file (deleted)" and "written (deleted)" (the Forecast card passes the same flag when the newest run wrote files and its folder is gone); the fan badge reads "earlier run · newest files deleted" for such a run (a run that never wrote files keeps "has no forecasts"); the ledger row leads its facts with a "files deleted" chip when the folder is gone.
- Tests: `test_a_run_whose_folder_was_deleted_says_so_everywhere` (the page, /runs, /forecast and fan_run).
- Risk: the words only; a run whose files Output serves from the archive is unchanged (G06). For Ely: none.

## FC-19
- Reproduced: yes. A 60-byte results.json: /runs/<id> 500 (JSONDecodeError); /forecast, /runs and /output 200.
- Fix: run_page reads results.json under try; an unreadable file gives an empty results dict and the alert "This run's results file is unreadable; its files and ledger row are shown." (the report and the files still show).
- Tests: `test_an_unreadable_results_file_is_a_note_not_a_500`.

## UI-17
- Reproduced: yes. /runs/nope: title "FluBNF · Output", tab Storage, h1 "Run"; a found run: title "FluBNF · Run", tab Forecast (a real-time run) or Storage.
- Root cause: output.html's title is fixed to "Output" for every notice it renders.
- Fix: the notice page's title is its heading: "FluBNF · Run" for a missing run (and the heading each other notice carries). The tab stays Storage for a missing run, where the runs are listed; a found real-time run's page sits under Forecast by the page's own rule (unchanged: a missing id has no run to place).
- Tests: `test_the_not_found_run_page_is_titled_like_a_run_page`.

## ST-13
- Reproduced: yes. A workroot without a ledger row: the Storage row reads "Unrecorded run" with no link, while /runs/<id> renders it (200).
- Fix: runs.html links every On disk row to its run page (the page accepts a workroot without a row).
- Tests: `test_an_unrecorded_workroot_links_to_its_run_page`; test_storage's pin ("no run page to link") updated.

## Checks
- Targeted: test_deleted_runs_labels (5), test_storage, test_forecast_aids, test_which_run_shows, test_models_tab, test_pages, test_fewer_marks, test_ui_layout, test_server_hardening, test_output_by_date, test_reclaim, test_run_results, test_season_run_marks, test_remembered_form, test_no_engine: 239 passed; ruff gate clean.
- Live from the prototype: the labels to the second on /runs and /output; after the delete the run page's alert and "(deleted)" rows with no "Superseded", the Forecast card's "(deleted)" and the badge "newest files deleted", the ledger's "files deleted" chip; the truncated results.json gives 200 with the note; /runs/nope titled "FluBNF · Run"; the unrecorded row links and its page is 200.
- For Ely: none.

## Patch
G15/proposal.patch (git diff origin/dev...proto/G15-B)
