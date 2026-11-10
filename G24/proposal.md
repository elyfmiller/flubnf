# G24 data-page: proposal (B)
Base: origin/dev b4b176b

Reproduced on a server from dev (FLUBNF_STATE_DIR, the shared hub clone,
which lacks model-output; the G20/G21 run state; the template dataset
under an 80-character name, a snapshot dataset built from
test_dataset_snapshots.as_of_csv) with curl and Chromium at 1280 px;
DA-07 on a private hub copy whose archive stops at 2026-10-17 while its
target-data file holds 2026-10-24. No run path; no invariance check.

## DA-04
- Reproduced: yes. After a dataset's Delete the page opened at
  /data#datasets, scrollY 532, the flash at -450 px ("Deleted …: 6.6 MB
  freed." unseen); the store's notice read "2 warning(s)".
- Root cause: datasets_ui's store and delete redirects carry #datasets,
  and base.html renders the flash above the h1.
- Fix: the two redirects drop the fragment (the Retrospective path's
  redirect keeps its #main, which places its own notice); the warning
  count reads "1 warning" / "2 warnings". After: /data, scrollY 0, the
  flash at 82 px.
- Tests: test_data_page_fixes.py
  `test_a_store_or_delete_lands_with_its_notice_in_view`.
- Risk: the page no longer jumps to the Stored list after a store or
  delete; the notice names the dataset.
- For Ely: none

## DA-05
- Reproduced: yes. The red badge "baseline, ensemble missing" with no
  remedy; Check for new data gold and Update data quiet before and after
  a check; a pull's notice said nothing of the folders it added.
- Root cause: data.html's `pull_first` reads hub_behind and the empty
  clone only; /freshness's JSON "behind" likewise; the badge carries no
  words; _pull compares nothing about the comparators.
- Fix: `pull_first` includes `comparators_missing` and the check's JSON
  "behind" does too, so Update data is the gold primary while they are
  missing (and the check's answer keeps it so); the badge is followed by
  the hint "Update data adds them."; _pull reads comparators() before
  and after and adds "baseline and ensemble comparators added" (or the
  one) to its notice. After: Update data gold, the hint beside the
  badge; a fake pull that creates the folders: "… · baseline and ensemble
  comparators added", then "present" and the check gold again.
- Tests: `test_missing_comparators_name_their_remedy_and_make_update_data_primary`.
- Risk: the hub card's words and primary only. One short hint, no "?".
- For Ely: none

## DA-07
- Reproduced: yes. On the copy, the hub card said "Data through
  2026-10-24 · not archived · target-data" while the Vintage list began
  at 2026-10-17 and the browser could not show the live file.
- Root cause: _data_context builds the browser from data.vintages()
  only; the readers take a date and open the archive's file for it.
- Fix: the core readers (load_vintage, vintage_summary,
  vintage_location_names, vintage_series) take an optional `path`; the
  page's cached readers pass the path they already key on. When the live
  file's newest week is newer than the archive's, `live_entry` names it:
  the Vintage list leads with "2026-10-24 (target-data, not archived)",
  selected by default (the data a real-time run reads), the Source tile
  says "target-data, not archived", the chart titles read "as in
  target-data 2026-10-24"; ?vintage=<archived> still opens the archive,
  and the Archive card's tiles still describe the archive. vintages()
  and every run path are untouched. After: VLIVE true, weeks through
  2026-10-24 on the copy; on the shared clone (archive and file both
  2026-10-24) nothing changes.
- Tests: `test_the_browser_shows_the_live_file_when_the_archive_lags`.
- Risk: the Data page only; the four readers' new argument defaults to
  the old behavior.
- For Ely: none

## DA-19
- Reproduced: yes. Strip: 2025-26 #3375FB, 2024-25 #C9568C, 2023-24
  #0087AF (the player palette by index, newest first); chart: 2026-27
  gold, 2025-26 #DC6700, 2024-25 #217FC1, 2023-24 #2B9D2B.
- Root cause: _vintage_rows colours by palette index; the chart (as the
  Forecast tab, pinned by test_season_palette) draws the newest season
  gold and earlier ones --season-N newest-first.
- Fix: the strip follows the chart's rule: the newest row "var(--gold)",
  earlier rows "var(--season-N)" newest-first, as tokens the SVG
  resolves, so the CV-safe set reaches the strip too. After: both read
  rgb(1,115,169), rgb(220,103,0), rgb(33,127,193), rgb(43,157,43) per
  season.
- Tests: `test_a_season_wears_one_colour_on_the_archive_strip_and_the_chart`
  (test_pages' `all(r["color"])` still holds).
- Risk: the strip's colours change to the chart's; nothing else.
- For Ely: none

## DA-23
- Reproduced: yes. The snapshot dataset "flu": "Adult · flu" for every
  snapshot.
- Fix: data.html's titles append " · as of <snapshot>" (raw) and ", as
  of <snapshot>" (season over season) when the dataset is vintage-true
  (VDSVT), so each PNG export names its snapshot. After: "Adult · flu ·
  as of 2023-12-23".
- Tests: `test_a_snapshot_datasets_chart_title_names_the_snapshot`.
- Risk: the dataset view's titles only.
- For Ely: none

## Patch
G24/proposal.patch (git diff origin/dev...proto/G24-B): core/data.py (the
readers' `path`), routes/data.py, data.html, datasets_ui.py,
app/tests/test_data_page_fixes.py (5). Targeted suites (test_data_view,
test_pages, test_season_palette, test_datasets_ui, test_dataset_upload_box,
test_hub_setup, test_ui_layout): 158 passed. Full suite (FLUBNF_HUB=/nonexistent): 4209 passed, 159 skipped; the two tests/test_doctor.py failures are this container's Python and pass in CI. ruff
clean. Windows: Path joins only.
