# G28: review (B)
PR #87, head 5efa616.

Approve.

- Commits aad1df5, 717f4fe and 5efa616: authored and committed as Ely F. Miller <efm46@nau.edu>, no trailers; no footer on the PR body. Status cell "fixed in #87".
- The diff is the decision (A's proposal) plus the replay rows' relWIS tip folded into the Your data explainer, as pr.md says; the pins moved are the rows' own tips and the old words.
- Tests on the head: test_retro_words (7), test_fewer_marks, test_relwis_conventions, test_retro_fit_level, test_run_timing, test_resume_rerun, test_design_batch3, test_datasets_ui, test_dataset_snapshots, test_replay_bundle, test_retro_forms, test_retro_archive, test_shipped_vintages, test_season_run_marks, test_dataset_replay_knobs, test_pages, test_ui_layout: 378 passed; ruff (the gate) clean.
- Live on a server from the head (8823, the G28 state: a complete 2025-26 Groundhog replay of Vermont and its archived run):
  - RE-18: /retro shows the page "?", the engine alert's, the "i" and Import a replay; the season row carries no relWIS, Wall time, Resume or archived-runs mark (none of tip-rt-rel, tip-rt-wall, tip-rt-resume, tip-rt-arch in the page).
  - RE-19: /retro?tab=own shows the upload box's "?", the "i" and the Replays explainer only.
  - RE-20: "Not imported: notzip.zip is not a zip file." for the upload; "Not imported: /root/fixwork/live/a28 is a folder, not a bundle." for a folder path.
  - RE-21: the archived row's Delete carries data-when "2026-11-10 05:38 UTC" with no data-imported, so its confirm reads "the archived 2025-26 run from ..."; the imported case is the test's.
  - RE-22: "Not started: 2025-26 has 31 weeks replayed without US; this run adds it." and "... replayed over 1 location; this run asks for 3, a different list." (the settings words and the archive notice: test_retro_words).
- No run path touched.
