# G29 storage-text: proposal (B)
Base: origin/dev 349db4b (G25 merged; dev is now 7e78912, G26)

How: a server (8820) on a copy of the G28 state (three Groundhog runs, a
2025-26 season and its archive, two datasets) plus a run of two states,
60 ledger rows added by hand (one partial, one 'running' with no worker
and an empty workroot, one stopped, one failed), two report archives;
a fresh state (8821) with one 0-byte workroot; the same under
TZ=America/Phoenix (8822); Chromium at 1280 px light and 390 px dark for
the marks, the dialogs and the filter; an all-53 Groundhog run on 8820
for the busy state.

## ST-04
- Reproduced: yes: "50 runs recorded" over "Showing the newest 50 of 64 runs."
- Root cause: runs.html's summary counts the rows shown (`ledger | length`).
- Fix: `ledger_total` in the summary (runs.html).
- Tests: test_storage_words `test_the_ledger_summary_counts_every_recorded_run`.

## ST-08
- Reproduced: yes: 8 visible "?" with On disk open (the cap notice, an
  interrupted row, Reclaim, Run workroots, Retrospective seasons, Archived
  runs, Your datasets, Protected); during a run each busy row a "?" with
  its reason, and both report archives "A console run is in progress and
  may be writing the archive" during a Groundhog-only run, which never
  writes it (pipeline's archive step skips a one-model run).
- Fix: the section headings (Run workroots, Retrospective seasons,
  Archived retrospective runs, Report archives, Your datasets, Protected,
  Sandbox, Student experiments) carry no tip: their words are in each
  row's delete confirmation where they matter (the dialog's hint already
  says the ledger row is kept, the archived runs and the seal untouched,
  what goes with a dataset). The Reclaim "?" goes (its confirmation says
  the same before anything happens) and the "Nothing to reclaim" badge
  stands alone. `busy_act` is a disabled Delete whose `title` says why
  (the row's badge names the state: "running now", the season's status,
  "season replaying", "in use"); no per-row "?". Report archives are busy
  only while the run can write them: `routes/storage._may_archive()` reads
  the running marker and the live run's ledger spec (a dataset run or
  replay never; a Groundhog-only, Oracle-only, research, modified or
  vintage run never; a run still starting may); the delete route
  (`_storage_target`) uses the same test, so a Groundhog-only run no
  longer blocks the Delete.
- After: fold open, two marks on the page (the cap notice, the interrupted
  row: both decided marks the fewer-marks test keeps); during the
  Groundhog run, one disabled Delete (the live row, its reason on hover)
  and both archives' Delete live. Kept: the heading badge "console run in
  progress" (one per section, test_output_run_pages).
- Tests: `test_the_disk_sections_carry_no_marks_and_a_busy_row_says_why_on_hover`,
  `test_report_archives_are_busy_only_while_the_run_can_write_them`;
  test_storage's busy-row test reads the title (it pinned the per-row "?").
- Risk: `_may_archive` is read on the Storage page and the archive delete
  only; the pipeline's archive step is unchanged. test_storage_datasets
  pinned the Your datasets heading's tip ("counted once in the total"): it
  now reads the row's "1 run" part.
- For Ely: none

## ST-10
- Reproduced: yes (TZ=America/Phoenix): "run 11-10 06:10:37" (local) beside
  "archived 2026-11-10 05:38 UTC".
- Fix: `retro_archive.stamp_local(stamp)` (the stamp on the computer's own
  clock, "2026-11-09 22:38", the run times' format without seconds);
  Storage's archived rows read it. The Retrospective tab's "Archived run
  from 2098-02-04 10:15 UTC." and the archive's folder name are unchanged.
- After: "archived 2026-11-09 22:38" beside "run 11-09 23:17:44" in Arizona.
- Tests: `test_an_archived_runs_time_is_the_computers_clock` (the function
  under TZ=America/Phoenix where tzset exists, the page without "UTC");
  test_storage's pin of "10:15 UTC" on the page reads stamp_local.
- Windows: no tzset; the test's zone branch is skipped there, the
  astimezone() conversion is the OS's.

## ST-11
- Reproduced: yes: "Delete all 1 completed workroot (0 B)"; "Delete all 6
  completed workroots" counting an interrupted run; the Clear dialog's
  status list without partial.
- Fix: "Delete 6 workroots (28.5 MB)", "Delete 1 workroot (0 B)"; its
  dialog "Delete every run workroot not running?" and "This permanently
  deletes 6 workroots totaling 28.5 MB on disk, with each run's report and
  submission files. The active run's workroot is excluded, and it cannot
  be undone."; the ledger's "Clear 64 rows (files kept)", its dialog "This
  removes 64 rows from the ledger. A row whose run is still active is never
  removed." (no status list); the notices "Cleared N ledger row(s).",
  "Deleted N run workroot(s): X freed.", "Nothing to clear: the ledger has
  no rows to remove.", "Nothing to delete: no run workroots on disk
  (apart from the active run's)."
- Tests: `test_the_bulk_controls_count_rows_and_workroots_without_completed`,
  `test_the_bulk_notices_count_without_completed`; test_storage's pins of
  "completed" in the button, dialog and notices updated.

## ST-12
- Reproduced: yes: (a) the empty ledger beside a listed workroot: "No runs
  yet / Run a forecast"; (b) a 0-byte workroot: "Nothing stored yet", "No
  runs or replays on disk" above "Run workroots · 1 entry".
- Fix: `inv["listed"]` (any row in a counted category) keys the summary
  ("0 B in use" for the empty workroot), the one empty state and the
  sections; the legend and Reclaim show while a category has bytes
  (`storage.cats`). The ledger's empty state reads "No runs recorded" when
  runs are on disk (cleared, or never recorded), "No runs yet" otherwise;
  the Run a forecast action stays.
- Tests: `test_the_empty_states_follow_the_listings`; test_storage's
  empty-ledger test (its fixture has workroots) reads "No runs recorded".

## ST-14
- Reproduced: yes: "Delete workroot 20261025T190744-377cdd (Round 2026-10-24
  (as of 2026-10-17))?".
- Fix (runs.html): the confirmation leads with the label: "Delete the Round
  2026-10-24 (as of 2026-10-17) run?", "This permanently deletes the Round
  … run (5.5 MB on disk). It cannot be undone.", hint "Its report and
  submission files go with it; the ledger row is kept and will show a dash
  for disk use. Run id 20261110T061037-ea3e95."; an unrecorded workroot
  reads "the unrecorded run <id>". The aria-label follows; the confirm
  value is the id as before.
- Tests: `test_the_delete_confirmation_leads_with_the_runs_label`.

## ST-15
- Reproduced: yes: "Its replays and 0 run workroots went with it; the runs'
  ledger rows are kept." for a dataset with neither.
- Fix: `deleted_message(ds, freed, gone, kept, replays)` builds the detail
  from the counts, in the Storage row's words: "With it went its 1 replay
  and its 2 run workroots; the runs' ledger rows are kept." / "With it
  went its 2 replays." / no detail; `_delete_confirmed` counts the replays
  before deleting.
- Tests: `test_a_deleted_datasets_notice_names_only_what_went`; the two
  pins in test_storage_datasets read the counted sentence.

## ST-16
- Reproduced: yes: the Protected "?" about the sealed record over the hub
  clone alone.
- Fix: no tip (the lock badge says protected; "not in the total" stays).
- Tests: `test_the_protected_heading_has_no_tip`.

## ST-17
- Reproduced: yes: "failed" showed 1 of 50 (the failed row) with partial,
  stopped and interrupted rows beside it; "2026-11-10" found nothing,
  "11-10" one.
- Fix: the button reads "not ok" (its key stays `failed`) and matches
  every row but ok and running; `data-find` carries the run's day
  (`runs.run_id_time(run_id)[:10]`, routes/storage) beside the as-of date,
  the id's first eight characters and the label.
- After: "not ok" 4 of 50; "2026-11-10" 1 of 50; "2026-11-08" 49 of 50.
- Tests: `test_the_filter_finds_runs_that_did_not_finish_ok_and_a_runs_day`.

## Checks
- New app/tests/test_storage_words.py (11); with test_storage,
  test_storage_datasets, test_output_run_pages, test_fewer_marks,
  test_state_folder_protect, test_reclaim, test_retro_archive,
  test_run_timing: all pass. ruff (the gate) clean.
- Full suite (FLUBNF_HUB=/nonexistent, test_doctor deselected: this container's Python): 4215 passed, 159 skipped, 0 failed (dev 349db4b the same way: 4204 passed; a first run of the prototype had 7 failures in test_season_run_marks, run-page tests my change does not touch, which pass alone and did not recur).
- Live: 1280 px light and 390 px dark, fold open: marks tip-st-cap and
  tip-st-int-3 only, before and after Reclaim; the three dialogs as above;
  no sideways scroll; the Phoenix server as under ST-10; the dataset
  delete "Deleted <name>: 45.9 KB freed." with no detail.
- Output check: not needed (no run path).
- Windows: `stamp_local` uses astimezone(); the templates and tests are ASCII.

## Patch
G29/proposal.patch (git diff origin/dev...proto/G29-B)
