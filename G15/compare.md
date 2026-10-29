# G15: compare (B)

A's patch applied on 78f0331 (scratch tree): its six tests and the
targeted files (test_storage, test_reclaim, test_archive_rule,
test_output_freshness, test_models_tab, test_forecast_aids,
test_which_run_shows, test_output_run_pages, test_season_run_marks)
pass, 140 passed. Both prototypes print the run's second and share the
UI-17 and ST-13 fixes almost line for line.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| FC-15 (OU-12, WI-13, ST-09) | seconds in `_run_label`; `_ledger_parts` and the workroot row both take `_run_label`'s time ("run 10-29 19:34:07" on both rows); the archive row reads "Weekly report and submissions · Round 2026-10-24 (as of 2026-10-17)" | seconds in `_run_label` and in `_ledger_parts` (its own string); the workroot row keeps run_display's "run 2026-10-29 19:27" and the archive row its date | **A**, criterion 1. ST-09 is "one run is labelled three ways on the Storage page": mine only fixes the same-minute half; A's makes the ledger row and the workroot row read alike and names the archive row's round as the workroot rows do. |
| FC-16 (ST-05, WI-07) | `output._files_deleted(run_id)` (neither workroot nor archive folder): the run page's alert "This run's files were deleted in Storage." in place of Superseded; Results rows "deleted"; the ledger's one "files deleted" fact in place of "N submissions" and "report ✓"; badge "newest has its files deleted" | the run page uses `_run_folder` the same way; Results rows "1 file (deleted)" / "written (deleted)"; the ledger chip is added when `disk_h` is None; `fan_run` looks at the workroot only | **A**, criteria 2 and 4. One helper decides everywhere, and it knows an archived run is not deleted (G06): my ledger chip and badge look at the workroot alone, so a run whose files Output still serves from the archive would read "files deleted" in the ledger. A's rows say "deleted" with fewer words (5). |
| FC-19 | the read guarded; the empty card reads "This run's results file could not be read" | the read guarded; a warn alert "This run's results file is unreadable; its files and ledger row are shown." | **A**, criterion 5: the words go where the empty card already is, no new alert; A's also treats a non-object JSON as unreadable. |
| UI-17 | output.html's title is the notice's heading | the same | Equal. |
| ST-13 | every workroot row links its run page; test_storage's pin updated | the same | Equal. |

Vote: A.
