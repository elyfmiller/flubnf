# G06 which-run-shows: proposal (B)
Base: origin/dev 48e30bb (G04 merged; G05 is PR #54, at CI: no overlap, G05 touches the engine checks and the chip's wording of `pf_skipped`, G06 the run choice; the `_outcome_items` hunk lands beside G05's, not on it)

The rules kept (app.md, 2026-10-15): Home and Models keep the shipped rule (the newest real-time run with shipped settings), a vintage run never replaces the current week, the Forecast tab draws the newest run of any kind. Every change below narrows what those surfaces pick or how the pages say it; no run record changes.

## OU-01
- Reproduced: yes (test on the pre-fix code, the hunt's steps): a whole-set run with a report, then a newer Ohio-only run with a report on the same week: the report card and `/output/report` served the Ohio report while the date card showed the whole-set run's file, and the archived whole-set report for the week left the picker.
- Root cause: `routes/output.py` `output_page` and `output_report` take the report from `shared._latest_results` (the newest run), while the date card takes its file from `archive_record.choose` (the newest complete whole-set run first); the picker drops the card's week whatever run the card shows.
- Fix: one helper, `output._report_run(include_modified, dates=None)`: the newest run (a modified one when the page allows it, shown badged as today), unless the newest date's card shows another run's files, whose report is then the week's (its folder, or the archive's copy when the folder was deleted). `output_page`, `output_report` (Home's button) and `output_report_download` use it. The picker keeps the archived week when the card's report is from a run on part of the hub set (`_file_entry` carries the candidate's scope, `full`).
- Tests: `test_output_by_date::test_the_report_card_offers_the_report_of_the_run_the_date_shows` (the whole-set run's report over the newer Ohio one, on the card, the date card and `/output/report`; the archive serving it once its folder has none; the Ohio report standing in, with the archived week kept in the picker, when no whole-set report exists).

## OU-02 (medium confidence)
- Reproduced: by test and in the code: `archive_record.choose` and the archive step read no mode; a newer complete whole-set vintage replay of a past week took the week's file from the real-time run. (The hunt's live case simulated the real-time run by re-dating a workroot; a test does the same with two records.)
- Fix: `archive_record.realtime_of(spec)` (the extra's mode, real-time when absent); `_hub_candidates` carries it for workroot and archive candidates; `choose` prefers the newest complete whole-set real-time run, then the newest complete whole-set one, then complete, then newest; `keep_reason`/`write_record` take `realtime`, so a vintage replay never replaces a complete real-time archive ("kept: this run is a vintage replay, so the archive kept the real-time run <id>"), and the record says what it holds. `pipeline._archive_run` passes the run's mode. A vintage run alone is still the week's file.
- Tests: `test_archive_rule::test_a_real_time_run_comes_before_a_vintage_replay` (choose, realtime_of, the archive kept); `test_output_by_date::test_a_vintage_replay_never_replaces_the_weeks_real_time_file` (the page's file; a vintage run alone).

## HM-05 (medium confidence)
- Reproduced: yes (test, the hunt's record): results.json with the spec's engine `pf`, `models.pf` empty and `models.analogue` with one state (the Groundhog consulted for pages) was Home's run.
- Root cause: `shared._latest_results` takes the newest real-time run whatever it produced.
- Fix: `shared._wrote_forecasts(res)`: a run whose asked-for member's table is present and empty while another member's holds forecasts (an Oracle-only run whose fits all failed) is skipped on the shipped surfaces (Home, Models, Output's card); the Forecast tab (`newest=True`) still shows it, badged by its own card as today. A record without the tables, or without a spec, is never skipped.
- Tests: `test_output_by_date::test_a_run_whose_asked_for_model_produced_nothing_is_not_homes_run`.

## OU-08
- Reproduced: yes (the template's words against `archive_record.choose`).
- Fix: the "i" reads "the newest complete real-time run on all 53 jurisdictions, else the newest complete run, else the newest run that wrote one"; the live badge "when it finishes complete on all 53 jurisdictions, this card shows its files"; the card sentence "The newest date, a round open now and a round coming up are cards; the other dates take one line each" (what the template does: `loop.first`, due, soon, the running date).
- Tests: `test_output_by_date::test_the_explainer_states_the_file_rule_as_the_code_applies_it`.

## OU-09
- Reproduced: yes (test, the hunt's steps): a run archived for its week, its workroot deleted: the run page read "No submission files" and `/runs/<id>/report` 404.
- Fix: `output.archive_dir_of(run_id)` (the archive folder whose record names the run); the run page reads its results, files and report from it when the run's folder is gone; `/runs/<id>/report` and `/report/download` fall back the same way.
- Tests: `test_output_by_date::test_a_run_whose_folder_was_deleted_lists_its_archived_files_and_report`.

## OU-11
- Reproduced: yes (the label against its content: the card's own week, or newer weeks when the card shows a vintage run).
- Fix: the picker's label reads "Archived weeks" (`output.html`); its content is unchanged.
- Tests: in the OU-01 test (the label beside the kept week).

## MO-06
- Reproduced: yes. Live: after a vintage quick run (2026-10-10, Ohio) from `/model/analogue` the card still read "Latest run 2026-10-17 …".
- Root cause: `routes/models.py` keeps the shipped rule on purpose (app.md); the label says "Latest run".
- Fix: the label reads "Latest real-time run", and when a newer run of any kind exists (`_latest_results(include_modified=True, newest=True)` differs) the card adds a link "Newer run on the Forecast tab" after "Run details". The rule is unchanged.
- Tests: `test_models_tab::test_the_card_names_its_rule_and_points_to_a_newer_run`; the existing label pin in `test_the_latest_run_is_labelled_values_with_its_page_linked` now reads the new label (the label was the bug), and the file's two `_latest_results` fakes take keyword arguments (the route now calls it twice).
- Live after: "Latest real-time run 2026-10-17 · …" with "Newer run on the Forecast tab" after the vintage quick run.

## Checked
- `test_output_by_date`, `test_archive_rule`, `test_models_tab`, `test_output_run_pages`, `test_report_bundle`, `test_ui_layout`, `test_pages`, `test_download_links`, `test_storage`: 167 passed; the seven new tests fail on the pre-fix code. Earlier run with `test_forecast_mechanics`, `test_run_integrity`, `test_fewer_marks`, `test_reclaim`, `test_core`, `test_newest_reported`, `test_forecast_modes`, `test_submission_identity`, `test_oracle_step`: passing. `ruff check --select F821,F823,F811,F401 app/ui` clean.
- Live (a server from the prototype): the Output texts; the Models card's label and its link after a vintage quick run.
- Output: an all-53 Groundhog run on 2026-10-17 on dev 48e30bb and on the prototype gives the same file (md5 56da9201b416eb5c80317c849b55168e).
- Full suite: running; counts in a second commit.
- Windows: paths through `Path` as the code does; no encodings or line endings.
- For Ely: none. Both medium-confidence bugs reproduced by test on the pre-fix code.

## Patch
G06/proposal.patch (git diff origin/dev...proto/G06-B)
