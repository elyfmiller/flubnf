# G07 dataset-sufficiency: proposal (A)
Base: origin/dev 12281e7

## DA-01 (S2)
- Reproduced: yes. A server from dev: `good.csv` (2 groups, Saturdays 2023-08-05 to 2025-11-15, newest week North 349, South 41), the check: "Ready to use: 2 groups, 120 weeks." with no word about the Groundhog; stored; Forecast it (Groundhog own data, 2025-11-15): run recorded `ok`, `abstained {analogue: [North, South]}`, `exports {}`; the Forecast tab's Latest run reads ok. `single.csv` (one series, 30 weeks) checks "Ready to use" the same way.
- Root cause: `app/ui/dataset_upload.py` / `app/core/datasets` check nothing about the Groundhog's donor pool (flubnf/analogue.py `MIN_DONORS = 30` donor ratios within `DEFAULT_BANDWIDTH` epiweeks in earlier seasons); `app/ui/datasets_ui.py` `run_worker` closes the run `ok` whenever no fit failed; `app/core/custom_retro.py` finishes a replay `done` whatever it forecast.
- Fix:
  - The check: a new whole-dataset step, `app/core/datasets/checks.py` `dataset_checks(rep)`, called by `validate_snapshots` (one file or several) and `store.ingest` (not by `validate`, which reads each snapshot file, and a snapshot may hold one week). It counts the donor ratios the Groundhog would find at the dataset's newest week, horizon 1, with the library's own selection (`AN.donor_ratios`, default window, `exclude_seasons=()` as `engines/analogue._source` passes for a dataset), over the pooled bank of every group. That pooled count is the most any of the Groundhog's pools can draw (the own-state pools are subsets of it), so the notice only appears when the run cannot forecast on the file's own data: "Too little history for the Groundhog: at the newest week it finds 20 weeks like it in earlier seasons and needs 30, so it will not forecast this data on its own." The check shows it as a warn line under the preview's heading (not in the closed "notes on how it was read" fold, which is about reading the file); the status line stays "Ready to use: …" (the data are usable, and the box shows the line); the store keeps it with the dataset's other notices (the Data tab's list marks it as it marks those). The template dataset gets no notice (it forecasts).
  - The run: `run_worker` closes a run that wrote no export file `partial`, never a green `ok` (the Results rows say why: the abstained row and DA-03's row).
  - The replay: a replay that forecast no group-week finishes `no forecast` (a warn badge on its page, neutral in the list) instead of `done`; the status is display-only (nothing resumes on it).
- Live after: the check as above at 1280 light and 390 dark; the run `partial` on the Forecast tab; the replay test.
- Tests: `test_dataset_sufficiency.py::test_the_check_says_when_the_data_are_too_short_for_the_groundhog`, `::test_a_dataset_run_that_forecast_no_group_is_not_ok`, `::test_a_replay_that_forecast_no_group_week_ends_no_forecast` (the template still `done`).
- Risk: no forecast changes; the run's status and the replay's. Invariance: no (no hub path touched).
- For Ely: none.

## DA-03 (S3)
- Reproduced: yes, the same run's page: "Newest week reading 0 — Groundhog (own data): 2 abstain", its tip about a week reading 0, then "North: no forecast: the donors gave no distribution", while North's newest week is 349.
- Root cause: `app/core/runs.py` `zero_anchor_row` counts every engine note starting "no forecast" as a zero week; the donors' note (`engines/analogue.py`, anchor > 0) starts the same way.
- Fix: `runs.NO_DONORS` (the engine's note); `zero_anchor_row` skips it; a new `no_donors_row`: "Too few donors — Groundhog (own data): 2 abstain", its tip "The Groundhog forecasts from weeks like the newest one in earlier seasons; with too few of them (30 by default) it abstains. North, South." Both Results tables (hub and dataset) add it after the zero-week row (a hub run never had a home for that note either).
- Tests: in `test_a_dataset_run_that_forecast_no_group_is_not_ok` ("Too few donors", no "Newest week reading 0").
- For Ely: none.

## DA-08 (S3)
- Reproduced: yes. `onerow.csv` (2024-01-06, A, 5): "Ready to use: 1 group, 1 week."; stored; /forecast?source= says "No week of this dataset on or before that date."; the Retrospective's Your data shows empty From and To selects.
- Root cause: nothing requires two weeks, while `Dataset.forecast_dates` is `weeks()[1:]`; the preview's label says "1 weeks".
- Fix: `dataset_checks` refuses one week as a problem (code `one_week`, kind Weeks): "The data hold one week (2024-01-06): a forecast starts from the week after the first, so at least two weeks are needed." The sparkline label reads "1 week".
- Tests: `::test_a_one_week_dataset_is_refused_at_the_check_and_the_store`, `::test_a_group_with_one_week_reads_one_week`.
- For Ely: none.

## DA-12 (S3)
- Reproduced: yes. The stored `good` dataset's `vintages` folder moved away: /data?source=, /forecast?source= and /retro?dataset= answer 500 (`FileNotFoundError: No vintage for 2025-11-15 in dataset 'good'. Nearby: ['2025-11-15']`); /data lists it.
- Root cause: the three pages build their dataset views without a guard; `Dataset.vintage_path` names the missing week as "nearby".
- Fix: `datasets_ui.damaged(ds)` ('' when every snapshot file is there); the Data and Forecast routes, as for an unknown id, show the hub page with the note "good cannot be opened: its stored files are incomplete. Delete it on the Data tab and upload it again." (the Data tab's list keeps its Delete); the Retrospective's Your data says the same and opens a whole dataset (`retro_context` never picks a damaged one). `vintage_path` says "The snapshot file for <date> of dataset <name> is missing: <path>" when the week is recorded but its file is gone.
- Tests: `::test_a_dataset_whose_files_went_missing_is_named_not_a_500`.
- For Ely: none.

## DA-13 (S4)
- Reproduced: yes. `curl -H 'Content-Type: multipart/form-data' --data-binary garbage /data/datasets`: 500; a file plus 25 fields: 500.
- Fix: `datasets_ui.upload` reads the form in a try, as `check` does, and answers the Data page with "The upload could not be read; choose the file again." (400).
- Tests: `::test_an_unreadable_upload_is_said_not_a_500`.
- For Ely: none.

## DA-18 (S4)
- Reproduced: yes. `zeros.csv` stored as "流感 data", then the same file as "流行 data": the same id (`data-<digest>`), flash "Stored 流感 data ...", the typed name dropped.
- Root cause: `store._store`: the id is the name's ASCII slug plus the bytes' digest, and an existing id is returned as it is.
- Fix: the upload says so: "This file is already stored as 流感 data: 1 group, 10 weeks." (the flash, and the Retrospective's stored note) when a typed name differs from the stored dataset's. Ids and the slug are unchanged (a new slug would move every stored dataset's id).
- Tests: `::test_the_same_file_under_a_name_with_the_same_id_says_where_it_is`.
- For Ely: none.

## Checks
- New `app/tests/test_dataset_sufficiency.py` (8): all fail on dev, pass here. Two fixtures were one week long for other purposes and now hold two (`test_datasets.py::test_minted_keys_stay_unique_past_99_groups`, `test_datasets_ui.py::test_a_multi_target_file_offers_its_targets`); what they test is unchanged.
- `ruff check --select F821,F823,F811,F401 app/ui` clean.
- Live: each bug on a server from the prototype (above). Full suite on the prototype (3.12): 3492 passed, 155 skipped, 0 failed.

## Patch
G07/proposal.patch (git diff origin/dev...proto/G07-A)
