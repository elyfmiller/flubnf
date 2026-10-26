# G08 retro-national: proposal (A)
Base: origin/dev b8bf2b2 (applies on 6f9a86f, G07 merged: no overlap)

Reproduced on dev with a second sparse hub clone of my own that also holds model-output/FluSight-baseline (the session's hub has none, so its replays never score; that hub stays untouched), and on the session's hub for UI-11, whose steps need scoring to fail.

## RE-01 (S2)
- Reproduced: yes. A Groundhog replay of 2026-27 on Arizona and Texas, national off: the page's tiles "US national · sum of states, Groundhog 5.287, log scale 7.005, coverage 0% · 0% · 0%, cells 3", and the 'i' calling it "US (aggregated) ... each member's state forecasts are summed".
- Root cause: `app/core/us_national.py` `resolve` falls back to `retro.national_aggregate` for any scope, and that sums whatever jurisdictions a week stored.
- Fix: `resolve` reads the season's own settings (`run_meta.json` "settings": `locations`, `national`; `{}` for a season from before them, which keeps today's behavior) and, with fewer than the 52 jurisdictions replayed and no fitted US, answers officials only, with the reason "only 2 of the 52 jurisdictions were replayed, so their forecasts do not sum to the nation" (the existing fallback wording carries it). A whole-set replay is still summed.
- Live after: the same replay: no sum of states; US reads officials only with that reason.
- Tests: `test_retro_partial_scope.py::test_a_replay_of_part_of_the_52_has_no_sum_of_states`.
- For Ely: none.

## UI-11 (S3)
- Reproduced: yes. A 2025-26 Groundhog replay of the 6-state panel with "fit US national too", on the session's hub (scoring fails: no FluSight-baseline): the location select reads "US (official models only)" while the playback payload carries the Groundhog's US forecast, which the player draws.
- Root cause: `routes/retro.py` `season_page_context` resolves the US only when the season scored (`us = None` otherwise, which the page turns into officials only), and `resolve` says fitted only when scores exist.
- Fix: the page resolves the US whether or not it scored (unscored: `allow_aggregate=False`, no aggregate to build); `resolve` answers fitted (no figures yet) for a replay whose settings say it fitted US.
- Live after: "US national (fitted)" / "US (fitted)".
- Tests: `::test_a_replay_that_fitted_us_is_labelled_fitted_before_its_scores` (resolve, and the season page with its scoring not done).
- For Ely: none.

## RE-14 (S3)
- Reproduced: yes. The 2-state replay's 'i': "Pooled relWIS covers the fitted states, DC and Puerto Rico; the US national cell, their sum, is scored apart ...".
- Root cause: `us_national.POOLED_SCOPE_NOTE` is static.
- Fix: `us_national.pooled_scope_note(n)`: "Pooled relWIS covers the 2 replayed jurisdictions; the US national cell is scored apart and never joins the pooled average." (the 50 states, DC and Puerto Rico on a whole replay); "their sum" goes (a fitted US is not their sum; the aggregated row's own note says it is one). `POOLED_SCOPE_NOTE` stays as the whole-replay wording for its readers; the season page prints the computed note with the pooled frame's location count.
- Tests: `::test_the_pooled_note_names_the_replays_jurisdictions`.
- For Ely: none.

## RE-10 (S3)
- Reproduced: yes. /retro/2025-26?week=2025-12-20&loc=Arizona&view=fc on an all-53 replay: "Live scores ... This week Groundhog 0.718 54% 79% 94%" beside "Arizona · forecasts as of 2025-12-20"; the payload's `week_rel` 0.7177, `week_cov` 50 0.543, `week_n` 208: the pooled figures.
- Fix: a tag beside the "Live scores" heading, "pooled, 52 jurisdictions" (the season's pooled count, `pooled_n`), so the table says whose scores they are whichever location the detail shows. No new mark, no tip.
- Live after: "pooled, 2 jurisdictions" beside the heading (1280 light, 390 dark).
- Tests: `::test_the_live_scores_say_they_are_pooled` (the rendered page, with and without a count).
- For Ely: none.

## RE-17 (S3, medium confidence)
- Reproduced: yes. The template dataset, every group replayed (2023-10-07 to 2024-03-30): pooled cells 144 with Overall's 48 among them (Adult 48, Overall 48, Pediatric 48), `national` None, `national_group` None.
- Root cause: `app/core/datasets/checks.py` names a national group by its spelling only (`NATIONAL_NAMES`); the template's "Overall" is the sum of the others.
- Fix: `checks._sum_group`: for count data with three groups or more, the one group that on every week all groups report (two such weeks at least) equals the sum of the others, to rounding, is the national group, as a "US" one is. Rates are never summed; two groups, or two candidates, guess nothing. Only scoring and labels read `national_group` (no engine does), so no forecast moves; a dataset stored before keeps its record.
- Live/after: the same replay: pooled 96 (Adult and Pediatric), national 48 (Overall).
- Tests: `::test_a_group_that_sums_the_others_is_the_national_row`. `test_datasets.py` pinned the template having no national group twice (the bug): `test_no_national_group_is_recorded_as_none` now uses two groups that sum to nothing, and `test_meta_records_the_ingest` expects Overall.
- For Ely: none.

## Checks
- New `app/tests/test_retro_partial_scope.py` (5): all fail on dev, pass here. `ruff check --select F821,F823,F811,F401 app/ui` clean. Related files (us_national, retro_player, season_run_marks, datasets, custom, retro, layout): 632 passed before the two pinned asserts were updated; the full suite is running, counts follow.
- Invariance: not on the list (no run path, no core forecast file); no submission file can change.

## Patch
G08/proposal.patch (git diff origin/dev...proto/G08-A)
