# G28 retro-text: proposal (A)
Base: origin/dev 349db4b (G25 merged)

How: a dev server (8815) and a prototype server (8817) on the private hub
copy (no model-output, so a replay's scoring stops with "error" after its
weeks; the trees and their archives are complete). On each: a Groundhog
replay of 2025-26 for Vermont and Ohio (zero-anchor level), then a resume
asking for abstain, a resume adding US, an archive-and-fresh run, an
export and its import (`verify/g28.sh`); a stored grouped dataset (Kids)
for the Your data tab; import refusals with a non-zip "notzip.zip" and a
folder path; Chromium for the delete confirm and to count the marks.

## RE-16
- Reproduced: yes: "Not started: choose what the Groundhog does when the
  newest week reads 0." with the tip "Set Newest week reading 0: abstain,
  level, extend or blend." (the panel's "Newest weeks reading 0" is
  another setting).
- Fix: the tip names the Run form's control: "Set Groundhog when the
  newest week reads 0: abstain, level, extend or blend." (routes/retro.py).
- Tests: test_retro_words.py `test_the_zero_anchor_refusal_names_the_forms_control`.

## RE-18
- Reproduced: on dev 349db4b the index with that season (error, 31 weeks,
  3 archived runs) shows 7 marks: Retrospective, the engine alert, Model
  settings' "i", Import a replay, the error badge, Wall time, "N archived
  runs kept". The template still has the report's others: the first
  relWIS's "?", the stopping / interrupted / stopped / "no hub weeks yet"
  badges' tips, sealed, N weeks added, the live estimate's "?" and
  Resume's "?".
- Fix (retro.html): the page's "?" is the one explainer for the rows, in
  three lines: what a replay is; "relWIS: the summed WIS over the
  FluSight baseline's (a ratio of sums); below 1 beats it."; "Resume, or
  Run, continues a stopped or interrupted replay from its last completed
  week with the recorded settings. Archived runs, set aside when a fresh
  replay started or imported from another machine, open as the live
  season does." The rows lose their own tips: relWIS, Wall time (the
  total alone), the status badges' (their words carry them), the live
  estimate (its basis stays as screen-reader text, as on the season page),
  Resume's, and the archived runs' heading. Kept, each the only place its
  words are: the error badge's tip (the error itself), the sealed badge's
  (which record sealed it), "N weeks added" (which weeks, and what Run
  does), and the page-level ones (the engine alert's remedy, the disabled
  Run's reason, Import a replay).
- After: that index 7 -> 5 marks; a complete card with archives 3 -> 0; a
  stopped card 3 -> 0.
- Tests: `test_the_season_rows_carry_no_tips_of_their_own`; pins of the
  rows' tips moved to the explainer (they pinned the clutter):
  test_relwis_conventions `test_the_index_labels_the_convention_beside_every_score`,
  test_retro_fit_level `test_retro_index_never_fabricates_a_zero_wall_time`
  and `test_stopping_badge_names_the_fits_in_flight`, test_design_batch3
  `test_active_and_unfinished_seasons_keep_their_bars` (no relWIS on the
  card, the page's "?" naming it), test_resume_rerun
  `test_stopped_season_card_offers_resume_with_recorded_settings` (the
  explainer's Resume line), test_run_timing
  `test_retro_index_offers_pause_and_stop_while_running` (rbasis for a
  screen reader) and `test_retro_index_reports_total_wall_time_for_a_finished_season`
  (the total alone).
- For Ely: none (Ely's own ask; no Decided item labels each score).

## RE-19
- Reproduced: /retro?dataset=<Kids>: 9 marks: Retrospective, Dataset, the
  upload box's "the file", final data, Groups, Models, FluSurv-NET donors,
  Model settings' "i", "Replays of Kids". The empty state's "i" said
  "kept apart from the FluSight seasons" twice.
- Fix: on the Your data tab the page heading has no "?"; "Replays of X"
  is the tab's one explainer, in three lines (what a replay does; the
  data badge's meaning, vintage-true or final data; the groups and the
  models); the Dataset, Groups, Models and data-badge tips go;
  "Add FluSurv-NET donors (US flu hospitalizations only)" says its tip in
  the label; the empty state's first line loses its repeat. The replay
  page: the Scores "?" is its one explainer (the data kind and baseline,
  relWIS and coverage, the horizon and the Groundhog's abstaining), the
  pooled relWIS, national group, abstained and Horizon tips go.
- After: 9 -> 3 (the upload box's own, Model settings' "i", the
  explainer); a Groundhog replay of Kids (2023-10-07 to 2024-02-24): its
  page 4 -> 1 (final data, Scores, pooled relWIS, Horizon -> Scores; the
  report's abstained and national-group tips go the same way).
- Tests: `test_the_your_data_tab_has_one_explainer`; test_datasets_ui
  `test_a_replay_runs_and_its_page_names_the_baseline_and_the_label`
  pinned the kind badge's tip: it reads the badge, the weeks and the
  Scores line now; test_dataset_snapshots
  `test_replay_this_stores_one_vintage_true_dataset` reads the badge and
  the explainer's vintage-true line.

## RE-20
- Reproduced: yes: "Not imported: incoming-10521-1794290315699.zip is not
  a zip file." and, for a folder, "Not imported: verify: no such file."
- Root cause: routes/retro.py saves the upload as incoming-<pid>-<ms>.zip
  and replay_bundle's messages use `path.name`; inspect_bundle tests
  `is_file()` only.
- Fix: replay_bundle.inspect_bundle and import_bundle take `name` (the
  file as messages call it, the path's name by default); the route passes
  the upload's own base name (never used as a path); a folder is "<path>
  is a folder, not a bundle." The CLI's messages are unchanged for a
  file and read the same for a folder.
- After: "Not imported: notzip.zip is not a zip file." and "Not imported:
  /root/fixwork/verify is a folder, not a bundle."
- Tests: `test_an_import_refusal_names_the_chosen_file_and_a_folder`.

## RE-21
- Reproduced: yes: "This permanently removes the archived 2025-26 run from
  imported from vm on 2026-11-10: 31 completed weeks, 219.4 KB on disk."
- Fix: retro.html's confirm builds the phrase per row ("the 2025-26 run
  imported from vm on 2026-11-10" when the row is imported); the delete
  route's notice likewise ("Deleted the 2025-26 run imported from vm on
  2026-11-10: 31 weeks, 219.3 KB freed."), the archived wording kept for
  a run this machine set aside.
- Tests: `test_deleting_an_imported_run_says_where_it_came_from`.

## RE-22
- Reproduced: yes: "They were replayed with modified:
  groundhog.zero_anchor=level (cace8e4a); this run asks for modified:
  groundhog.zero_anchor=abstain (a86a7e3c)."; "Archived 31 weeks of
  2025-26 as 2025-26__archived_20261110T061344Z; ..."; "has 31 weeks
  replayed over 2 location(s); this run asks for 3 with a different
  list".
- Fix: routes/retro `_settings_words`: the zero-anchor rule by the Run
  form's label, the rest as the run page says them (knobs.words), "the
  default settings" when none; the archive notice names its time ("(set
  aside 2026-11-10 06:14 UTC)"); retro_settings.location_scope_change says
  "replayed without US; this run adds it" / "replayed with US; this run
  leaves US out", else "replayed over 2 locations; this run asks for 3,
  a different list" (the CLI reads the same).
- After: "They were replayed with Groundhog when the newest week reads 0:
  level; this run asks for Groundhog when the newest week reads 0:
  abstain."; "... has 31 weeks replayed without US; this run adds it.";
  "Archived 31 weeks of 2025-26 (set aside 2026-11-10 06:14 UTC); starting
  a fresh replay."
- Tests: `test_refusals_say_settings_scopes_and_archives_in_words`.

## RE-27
- Fix: docs/RETROSPECTIVES.md: "(its own card under Settings)".
- Tests: `test_the_doc_puts_import_on_its_own_card`.

## Checks
- New app/tests/test_retro_words.py (7): each fails on 349db4b and passes
  here; the retro, bundle, relWIS, marks, dataset and page tests: 95 + 380
  pass with the four pins above updated. ruff (the gate) clean.
- Full suite (FLUBNF_HUB=/nonexistent): 4226 passed, 160 skipped, 5 failed:
  the five pins named above (RE-18, RE-19), moved to the new places; their
  files then pass (107 with test_retro_words).
- Output check: not needed (no run path; replay_bundle and the retro
  routes' words only).
- Windows: the upload's base name is taken after turning backslashes
  into slashes, so a Windows browser's "C:\...\notzip.zip" reads
  notzip.zip.

## Patch
G28/proposal.patch (git diff origin/dev...proto/G28-A)
