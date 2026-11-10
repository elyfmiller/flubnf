# G24 data-page: proposal (A)
Base: origin/dev f96ce5a (G22 merged)

How: a dev server (8815) and a prototype server (8816) reading a private
copy of the shared hub (no model-output, as the shared clone) whose live
target file was given the 2026-10-17 rows again dated 2026-10-24 (the
archive's newest stays 2026-10-17); a cp1252 CSV (a group named "Niños")
and a two-snapshot dataset ("flu", as_of 2023-11-25 and 2023-12-02).
Chromium at 1280 px, light and dark.

## DA-04
- Reproduced: yes. The upload form (action /data/datasets#datasets),
  Save only: after the redirect the notice "Stored cp1252: 2 groups, 227
  weeks. 1 warning(s)." sat at top -474 px (scrollY 556), location #datasets.
  Delete answers /data#datasets the same way.
- Root cause: datasets_ui.py redirects to `#datasets`, below the flash at
  the top of #main; and a redirect without a fragment would keep the
  form's own #datasets, so dropping it is not enough.
- Fix: both redirects name `#main` (the Retrospective's store path already
  does, for the same reason); "1 warning" / "2 warnings".
- After: the notice at top 18 px, location #main, "1 warning."
- Tests: test_data_page_fixes.py `test_store_and_delete_land_on_their_notice`.
- For Ely: none

## DA-05
- Reproduced: yes. Badge "baseline, ensemble missing" with no remedy;
  Update data quiet and Check gold, before and after a check.
- Root cause: data.html's pull_first and the check's JSON (`behind`) know
  only the clone's lag; the pull adds the comparators' folders silently.
- Fix: the badge reads "baseline, ensemble missing · Update data adds
  them" (words, no new "?"); `pull_first` includes comparators_missing;
  /freshness's JSON gains `comparators_missing` and the script makes
  Update data the primary on `behind || comparators_missing`; the pull's
  notice adds "baseline and ensemble comparators added" when the pull
  added them (routes/data.py).
- After: badge with the remedy; Update data gold, Check quiet, before and
  after a check. The pull clause: test (a pull that adds the folders).
- Tests: `test_missing_comparators_say_what_adds_them`; test_pull_hub's
  JSON pin gains the new key.
- For Ely: none

## DA-07
- Reproduced: yes. Hub card "Data through 2026-10-24 · not archived",
  the Vintage select's options 2026-10-17 (selected), 2026-10-10, ...
- Root cause: routes/data._data_context builds the browser from
  data.vintages() only.
- Fix: when the live file's newest week is newer than the archive's
  newest vintage (the hub card's own test), the browser lists the live
  file first, "2026-10-24 (live file)" (value "live"), and opens on it;
  an archived vintage is still a choice. data.load_vintage reads the live
  file for `data.LIVE_VINTAGE` (no run passes it); the chart's title
  says "in the live file".
- After: options "*2026-10-24 (live file)", 2026-10-17, 2026-10-10; the
  series ends 2026-10-24.
- Tests: `test_the_browser_shows_the_live_file_when_the_archive_lags_it`.
- Risk: app/core/data.py is read by the run path, but only the new
  constant reaches the live file; vintage_path and every other caller of
  load_vintage are unchanged.
- For Ely: none

## DA-19
- Reproduced: yes. /data?loc=Arizona: strip 2025-26 rgb(51,117,251),
  2024-25 rgb(201,86,140); chart 2025-26 #DC6700, 2024-25 #217FC1.
- Root cause: the strip colours seasons by the player palette's literals,
  newest first; the chart by --gold (newest) and --season-N (older).
- Fix: one map by season label, `routes/data._season_vars`: the newest
  season --gold, older ones --season-1, -2, ... by rank, over the strip's
  seasons and the chart's; the strip's circles take it (a style over
  their fill or stroke) and the chart's script reads it (SEASON_VARS).
- After, light and dark: every season the same colour in both (light:
  2026-27 #0173A9, 2025-26 #DC6700, 2024-25 #217FC1, 2023-24 #2B9D2B;
  dark: 2026-27 #34C0F0, the rest alike).
- Tests: `test_a_season_keeps_one_colour_on_the_page`,
  `test_the_strip_and_the_chart_read_the_same_map`.
- For Ely: none

## DA-23
- Reproduced: yes. The "flu" snapshot dataset's chart title "West · flu"
  for both snapshots.
- Fix: a vintage-true dataset's titles add " · as of <snapshot>" (raw and
  season over season; data.html).
- After: "West · flu · as of 2023-11-25", "... as of 2023-12-02".
- Tests: `test_a_snapshot_datasets_chart_title_names_the_snapshot`.
- For Ely: none

## Checks
- New app/tests/test_data_page_fixes.py (6): each fails on f96ce5a and
  passes here; the data, dataset, pull, hub, marks and layout tests (597)
  pass with test_pull_hub's JSON pin updated. ruff clean.
- Full suite (FLUBNF_HUB=/nonexistent): 4216 passed, 160 skipped, 0 failed.
- Output check: not needed (load_vintage's live branch is reached only
  from the Data tab).
- Windows: the live file is read as the archive files are (pandas).

## Patch
G24/proposal.patch (git diff origin/dev...proto/G24-A)
