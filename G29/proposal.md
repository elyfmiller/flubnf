# G29 storage-text: proposal (A)
Base: origin/dev 7e78912 (G26 merged)

How: a dev server (8813) and a prototype server (8814), each with two
Groundhog runs (Vermont on 2026-10-17, Ohio on 2026-10-10), Chromium at
1280 px for the Storage page; the test fixtures of test_storage (closed and
live runs, a retro season and archive, a report archive, protected trees)
for the states a fresh server does not have (a run in progress, a cleared
ledger, over 50 rows).

## ST-04
- Reproduced: in code and test: the summary reads `ledger | length` (the
  50 rows shown) while the alert under it uses `ledger_total`.
- Fix: runs.html counts `ledger_total` (the rows shown when the route gives
  none).
- Tests: test_storage_words.py `test_the_ledger_heading_counts_every_run_recorded`.

## ST-08
- Reproduced: yes: dev's Storage page with two runs: 4 visible marks
  (Reclaim, Run workroots, Retrospective seasons, Protected); every section
  heading has its own (Archived runs, Report archives, Your datasets when
  listed); "Nothing to reclaim" carries a second; during a run every busy
  row has a "?" and every report archive is held with the same sentence.
- Fix: the section headings' tips go (Run workroots, Retrospective
  seasons, Archived retrospective runs, Report archives, Your datasets,
  Protected) and the "Nothing to reclaim" badge's; Reclaim keeps its one
  (what it deletes). An entry in use has its Delete off with no "?"; the
  reasons are said once, each distinct reason once, in one notice above
  the sections ("In use now: The run ... is active; ..."). A report
  archive is held only for the running run's own forecast date (read from
  its ledger row's spec; all held when it cannot be read).
- After: 4 -> 1 mark on that page; the busy run's reason once.
- Tests: `test_sections_carry_no_marks_and_busy_rows_say_why_once`,
  `test_a_report_archive_is_held_only_for_the_running_runs_date`; the
  busy-row pins in test_storage (`test_busy_rows_render_no_delete_controls`,
  `test_a_student_experiment_is_kept_while_the_runner_has_it`) and
  test_storage_datasets (the Your datasets heading's sentence) read the
  notice now (they pinned the per-row "?" and the heading tip).
- Kept: the Sandbox and Student experiments headings' tips (where their
  entries are deleted, said nowhere else on this page).

## ST-10
- Reproduced: in code and test: workroot rows are local time (run_display),
  archived replays `stamp_human` UTC on the same page.
- Fix: routes/storage `_local_when`: an archive's stamp in this computer's
  time, in the workroot rows' form ("2026-10-25 12:18"); stamp_human (and
  every other page) unchanged.
- Tests: `test_archived_runs_read_in_this_computers_time` (TZ
  America/Phoenix: 19:18 UTC reads 12:18); test_storage's archive pin.

## ST-11
- Reproduced: yes: "Delete all 2 completed workroots (11.0 MB)" (dev); the
  ledger's Clear dialog lists "statuses ok, failed, stopped, error, and
  interrupted" and also removes partial rows.
- Fix: "Delete the 1 workroot not running (...)" / "Delete all N workroots
  not running (...)", the dialog's title "Delete the run workroots not
  running?"; the Clear dialog says "rows of runs that are not running",
  no list.
- Tests: `test_bulk_controls_say_not_running_and_list_no_statuses`; the
  bulk pin in test_storage.

## ST-12
- Reproduced: in code and test: the ledger's empty state "No runs yet"
  beside listed workroots; On disk's empty state and "Nothing stored yet"
  keyed on `total_bytes` (an empty workroot lists at 0 B).
- Fix: the ledger's empty state reads "No runs in the ledger" when
  workroots are listed; On disk's empty state and badge key on the
  listings (workroots, seasons, archives, report archives, datasets).
- Tests: `test_empty_states_follow_the_listings`; test_storage's empty-ledger
  pin reads the cleared wording.

## ST-14
- Reproduced: yes: "Delete workroot 20261110T063916-bff975 (Round
  2026-10-17 (as of 2026-10-10))?", the hint naming only the ledger row.
- Fix: "Delete the run Round 2026-10-17 (as of 2026-10-10)?"; the hint:
  "Its folder <id> goes, with the run's report and submission files in it.
  The ledger row stays and shows a dash for disk use."
- Tests: `test_a_workroot_delete_leads_with_the_runs_name`.

## ST-15
- Reproduced: in code: deleted_message always says "Its replays and N run
  workroot(s) went with it".
- Fix: datasets_ui.deleted_message builds the detail from the replays
  (counted before the delete) and the runs: "Its 1 run workroot went with
  it; ...", "Its 2 replays went with it.", nothing when it had neither.
- Tests: `test_a_dataset_delete_names_only_what_it_had`; the two
  test_storage_datasets pins read the counted sentence.

## ST-16
- Reproduced: yes: "Protected" lists only the hub clone; its "?" speaks of
  the sealed record.
- Fix: the heading's tip goes (ST-08); the lock badge says "protected".

## ST-17 (medium confidence)
- Reproduced: in code: fits() takes failed|error only; data-find holds the
  as-of date, the compact id and the label, not the run's date.
- Fix: "failed" takes failed, error, partial, stopped and interrupted;
  data-find adds the run's date from its id (2026-10-25).
- Tests: `test_the_failed_filter_and_find_cover_every_unfinished_run`.

## Checks
- New app/tests/test_storage_words.py (9): each fails on 7e78912 and
  passes here; the Storage and dataset-storage tests pass with the pins
  above moved (50). ruff (the gate) clean.
- Full suite (FLUBNF_HUB=/nonexistent): 4240 passed, 160 skipped, 0 failed.
- Output check: not needed (no run path).
- Windows: `_local_when` uses datetime's own local zone (no tzset).

## Patch
G29/proposal.patch (git diff origin/dev...proto/G29-A)
