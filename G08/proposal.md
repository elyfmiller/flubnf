# G08 retro-national: proposal (B)
Base: origin/dev b8bf2b2

Reproduced on two servers from dev: one against a private copy of the hub
clone with model-output/FluSight-baseline added (scoring works there; the
shared clone was not touched), one against the clone as it is (no
baseline: scoring fails, UI-11's condition). Replays: 2026-27, Groundhog,
zero-anchor blend: Arizona and Texas without US; the 6-state panel with
US; the template dataset, every group.

## RE-01
- Reproduced: yes (the baseline server): the tile group "US national ·
  sum of states · Groundhog 5.287 · log scale 7.005 · coverage 0% · 0% ·
  0% · cells 3" and the table row "US (aggregated) 5.287 0%", the hunt's
  own numbers; the player's US option "US national (sum of 2 states)".
- Root cause: `us_national.resolve` falls back to the aggregate for any
  scope; `retro.national_aggregate` sums whatever jurisdictions a week
  stored.
- Fix: `us_national.JURISDICTIONS = 52`; `resolve` returns officials only
  with the reason "the replay scored N of the 52 jurisdictions, so no sum
  of states is built" when the scores cover fewer, before the aggregate
  is built or read. The aggregate itself is left as it is: a scoring
  device the parity and scoring tests drive on two-state trees, and
  `resolve` is the one gate every page and export reads through. No US
  group, row or option then appears (the hunt's first expected form).
- Tests: `test_a_partial_scope_never_gets_a_sum_of_states` (test_us_national).
  Pinned the other way and updated, saying so: `test_resolution_falls_back_
  to_the_aggregate` and `test_a_failing_aggregate_degrades_to_officials_with_
  a_reason` now use a 52-state frame; the two-state trees of
  test_results_prep (two tests) and test_report_parity (its root fixture)
  set `JURISDICTIONS` to their state count, the whole set there, since
  they test the aggregate's label, cache and parity, not its scope.
- Risk: a whole replay in which a state was never scored (abstained all
  season) now reads officials only with that reason: a sum of 51 states
  is not the nation either. Invariance: no (no run path touched).
- For Ely: none.

## RE-10
- Reproduced: yes: beside "Arizona · forecasts as of 2026-10-10" the live
  table's figures are the pooled week (payload week_n 2 for the two
  states, 208 on a whole season), with no word on the scope.
- Root cause: the player's stats are per week, pooled over the replay
  (THE STATS CONTRACT); the heading says "Live scores" alone.
- Fix: a tag beside the heading, "N jurisdictions pooled" (`pooled_n` in
  `season_page_context`: the record's locations, states only, else the
  scored frame's count; the export renders the same template).
- Tests: `test_the_live_scores_say_how_many_jurisdictions_they_pool`
  (test_retro_player); the console page test asserts the tag.
- For Ely: none.

## RE-14
- Reproduced: yes: the "i" of the 2-state replay reads "Pooled relWIS
  covers the fitted states, DC and Puerto Rico; the US national cell,
  their sum, ..."; the same on the fitted-US panel.
- Root cause: `POOLED_SCOPE_NOTE` is one static sentence.
- Fix: `us_national.pooled_scope_note(n_states, provenance)`: "Pooled
  relWIS covers the N replayed jurisdictions; the US national cell is
  scored apart and never joins the pooled average." under a partial
  scope; the constant (now "the 52 jurisdictions (the states, DC and
  Puerto Rico)", without "their sum") for a whole one, with ", their
  sum," only when the row is the aggregate. The route passes the note for
  the season's scope and US provenance.
- Tests: `test_the_pooled_note_names_the_replayed_scope_and_the_us_cell`;
  the console page test asserts the two-state wording.
- For Ely: none.

## RE-17 (medium confidence)
- Reproduced: yes: the template replay's summary pools 390 cells, Overall
  130 of them, national None.
- Root cause: a dataset's national group is the one spelled as one
  (`checks.NATIONAL_NAMES`: the US spellings plus "National", owner
  decision 2026-09-24); "Overall" is not, so it pools with its parts.
- Fix: none here. For Ely: the national row is defined by spelling by
  decision; the shipped template's third group is "Overall" while the
  check's own advice says "Rename it National if it is the total of the
  other groups". Options: (a) add "Overall" and "Total" to the spellings;
  (b) rename the template's group (its generator, fixtures and the upload
  tip name it); (c) detect a group equal to the sum of the others at the
  store and flag it, with a notice. Status: RE-17 for Ely: the national
  group is a spelling by decision (2026-09-24).

## UI-11
- Reproduced: yes (the clone without the baseline): the panel replay with
  US fitted: the location select and the chart title read "US (official
  models only)" while the Groundhog's US median and band are drawn;
  cfg.us provenance officials_only, no reason.
- Root cause: `routes/retro.season_page_context` resolves the US row only
  when the season is scoreable (`us = None` otherwise, the page defaulting
  to officials only); `resolve` itself knows "fitted" from the scores
  alone.
- Fix: the route resolves with or without scores (`allow_aggregate=
  scoreable`); `resolve` reads the record (`retro.read_meta`: settings
  locations naming US) and a stored week (`_fitted_us_stored`) and
  returns fitted, unscored, with the reason "fitted, not scored here":
  the label "US national (fitted)" everywhere the player prints it; no
  tiles or row (no scores).
- Tests: `test_a_replay_that_fitted_us_reads_fitted_without_scores`,
  `test_an_unscored_season_with_a_fitted_us_labels_it_fitted` (the real
  route on the console-season fixture without scores.json).
- For Ely: none.

## Checks
ruff (the F gate) clean; test_us_national, test_retro_player,
test_season_run_marks, test_results_prep, test_report_parity,
test_flusight_scoring, test_reclaim, test_retro_design_pass,
test_player_js, test_ui_layout, test_site_build: 215 passed, 21 skipped.
Full suite on the proto: in compare.md. Live, after the change: the
2-state page has no US group, row or option ("US (official models
only)", reason in cfg.us), the note "Pooled relWIS covers the 2 replayed
jurisdictions; ...", "Live scores · 2 jurisdictions pooled"; the fitted
panel reads "US national (fitted)" in the select and the chart title,
"6 jurisdictions pooled"; desktop light and phone dark.

## Patch
G08/proposal.patch (git diff origin/dev...proto/G08-B)
