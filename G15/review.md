# G15: review (B)
PR #69, head 5ec0be5.

Approve.

- The diff outside docs is the decided patch (A's proposal, applied on
  285a3d4) line for line; the Status cell reads "fixed in #69".
- Both commits are authored as Ely with no trailers; the PR body has no
  footer.
- Tests on the head: test_run_labels_deleted, test_storage, test_reclaim,
  test_archive_rule, test_output_freshness, test_models_tab,
  test_forecast_aids, test_which_run_shows, test_output_run_pages,
  test_season_run_marks, test_run_results: 148 passed. ruff gate clean.
- Live on a fresh server from the head (two Groundhog runs for Arizona two
  seconds apart, then Storage > Delete on the newest, a results.json cut
  to 12 bytes, /runs/nope, a workroot without a ledger row):
  - FC-15: "run 10-29 20:17:17" and ":19" on /runs; the older run's
    notice "Output shows run 10-29 20:17:19 … Open run 10-29 20:17:19".
  - FC-16: the deleted run's page "This run's files were deleted in
    Storage.", no "Superseded.", Results "deleted" twice; the Forecast
    card "deleted" and the badge "earlier run · newest has its files
    deleted"; the ledger "files deleted" once, "1 submission" only on the
    run that still has its folder.
  - FC-19: 200 with "results file could not be read".
  - UI-17: "<title>FluBNF · Run".
  - ST-13: the unrecorded row links its page, which answers 200.
  - No sideways scroll on the run page, Storage or Forecast at 390 px
    light and 1280 px dark.
