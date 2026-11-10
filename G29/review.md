# G29: review (B)
PR #88, head 4dfe348.

Approve.

- Commits 9c330b3 and 4dfe348: authored and committed as Ely F. Miller <efm46@nau.edu>, no trailers; no footer on the PR body. Status cell "fixed in #88".
- The diff is the decision: A's patch with B's `_may_archive` joined to the own-date rule (`_archiving_date`, in the page and the delete route), the bulk notices without "completed", the "not ok" button, and "the unrecorded run <id>" for a workroot with no ledger row.
- Tests on the head: test_storage_words (10), test_storage, test_storage_datasets, test_output_run_pages, test_fewer_marks, test_state_folder_protect, test_reclaim, test_retro_archive: 140 passed; ruff (the gate) clean.
- Live on servers from the head (8820: the G29 state with 65 ledger rows including a partial, a stopped and an interrupted run, an archived 2025-26 replay and two report archives; 8821: a fresh state with one 0-byte workroot), 1280 px light, the fold open:
  - ST-04: "65 runs recorded" over "Showing the newest 50 of 65 runs."
  - ST-08: three marks on the page (the cap notice, the interrupted row, Reclaim); during an all-53 Groundhog run one "In use now:" notice, the live row's Delete off with no "?", and both report archives still deletable (a Groundhog-only run archives nothing).
  - ST-10: "archived 2026-11-10 05:38" beside "run 11-10 06:24:00" (both this computer's clock).
  - ST-11: "Delete all 7 workroots not running (35.2 MB)" / "Delete the 1 workroot not running (0 B)"; the dialog "Delete the run workroots not running?"; the Clear dialog "This removes 65 rows of runs that are not running from the ledger." with no status list.
  - ST-12: the fresh state reads "No runs in the ledger" with the 0-byte workroot listed and no "Nothing stored yet" or "No runs or replays on disk".
  - ST-14: "Delete the run Round 2026-10-24 (as of 2026-10-17)?" with the folder, the report and submission files and the ledger row in the hint.
  - ST-16: the Protected heading carries no "?".
  - ST-17: "not ok" shows 4 of 50 (partial, stopped, interrupted, failed); Find "2026-11-10" finds that day's two runs.
  - ST-15: the counted sentence is the tests' (no dataset left in this state).
- No run path touched.
