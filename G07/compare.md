# G07: compare (B)
A's patch applied on 12281e7 (scratch tree): its 8 new tests and the
dataset tests (9 files) pass, 449; B's reproduction script against that
tree: the run closes partial, the run page has "Too few donors" and no zero
row, the replay says "No scored cells" and "abstained on 20 group-weeks".

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| DA-01 | A core `dataset_checks` counts the newest week's donor ratios with `AN.donor_ratios` (exclude_seasons=()) and records a warning that the store keeps with the dataset; the check shows it as a warn alert under the Preview heading, the status line unchanged; a run with no export closes partial; a replay that forecast nothing ends "no forecast" (list: neutral badge; page: warn) | B counts the same way in the UI's `_preview`; a warn badge beside "Ready to use", a "Donor weeks 20 of the 30 the Groundhog needs" fact, the status line ends "; too few donor weeks for the Groundhog."; `custom_run` records `no_forecast`, `run_worker` closes partial, a ledger chip "no forecast: every group abstained"; the replay untouched | A: the notice is the dataset's (the Data tab's list and the Retro "stored" note show stored warnings; the CLI's check gets it too), and the replay's "done" was the same bug. B's status-line suffix and the fact are a matter of taste; the chip is extra code the Results rows already cover. |
| DA-03 | `NO_DONORS` (the exact note), `zero_anchor_row` skips it, `no_donors_row` lists the locations | the same shape, matching "no forecast" without "reads", the tip quoting each note | A: the exact note is the engine's one string; a shorter tip. Equal otherwise. |
| DA-08 | `one_week` in `dataset_checks`: the whole dataset, after each file's own problems | `single_week` in `_check_rows` once `rep.ok`: per file | A: a snapshot folder's file may hold one week; the dataset is what needs two. B's would refuse such a file inside `validate_snapshots`. |
| DA-12 | `damaged(ds)` checks every snapshot file; the three pages flash "<name> cannot be opened: its stored files are incomplete. Delete it on the Data tab and upload it again." and show the hub / a whole dataset; `vintage_path` names a missing file as missing (it named the same week as "nearby") | `damaged(ds)` checks the final file; "<name> is missing its data file; Storage can delete it"; `choices()` also leaves the dataset out (the source pickers and the "Your data" tabs never open it) | A: every file checked, the Data tab's Delete is the one named, the misleading error text fixed. One line from B worth taking: `choices()` skipping a damaged dataset, so `/forecast?tab=own` and the source picker do not land on the flash. |
| DA-13 | the same try/except as `check()` | the same | equal |
| DA-18 | "This file is already stored as 流感 data: 1 group, 10 weeks." in the flash and the Retro stored note | "...; opened it. Rename it on Storage, or store a changed file as ..." | A: B's text names a rename that does not exist. |

Vote: A (with, if A agrees, `choices()` leaving a damaged dataset out, as
B's `test_a_dataset_missing_its_data_file_is_a_note_not_an_error_page`
asserts; otherwise A as it stands).

B's full suite on proto/G07-B (3.13): 3490 passed, 154 skipped; the two
failures are the tests/test_doctor.py checks that fail on this machine's
Python 3.13 on dev too.
