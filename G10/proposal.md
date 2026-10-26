# G10 season-player: proposal (A)
Base: origin/dev 68816e0

Setup on dev 68816e0, on my hub copy with FluSight-baseline rounds:
- a finished all-52 Groundhog 2025-26 (31 weeks; its first two weeks,
  2025-08-30 and 2025-09-20, have no baseline round);
- 2024-25 resumed to the end (30 weeks; 2025-01-18 is the placeholder
  week);
- the 2-state 2026-27.
For UI-18 and UI-20, a second server on the original hub clone (no
model-output), where scoring fails. Browser checks are Playwright, at
1280x900 and 390x844.

## RE-04 (also: none)
- Reproduced: yes. /retro/2024-25?week=2025-01-18&view=map, three
  ArrowLefts to 2024-12-28, then Forecast detail:
  - the Models row read "FluSight baseline (official) FluSight ensemble
    (official)" only;
  - the live scores had no Groundhog row;
  - the plot had no Groundhog fan.
  A fresh load at ?week=2024-12-28 has all three.
- Root cause: player.js `payloadFor`. A no-data week's payload is the
  placeholder `noDataPayload(src)`, with `models: {}`. The first
  `renderStats` builds the controls from it (`buildControls`, once,
  `P.built`), so the member list is empty for the whole visit.
- Fix: `payloadFor` builds the controls from the stored week it borrows
  from (`if(pl) buildControls(pl);`) before turning it into the
  placeholder. That week's members are what a fresh load there offers.
  One line, no server change.
- Tests: `test_a_visit_that_opens_on_a_no_data_week_keeps_every_member`
  (the order in payloadFor; the player's DOM half has no harness).
- Live after: the same steps give "Groundhog FluSight baseline
  (official) FluSight ensemble (official)", Groundhog in the live scores,
  and its fan, as a fresh load.
- Risk: none beyond the player. Invariance: no.
- For Ely: none.

## RE-11 (also: none)
- Reproduced: yes. 2025-26 at 2025-08-30 and 2025-09-20, and 2026-27 at
  2026-09-26: THIS WEEK reads Groundhog "pending" and ensemble
  "pending". The payload has `official: {}` and `week_n` 0. No
  FluSight-baseline file exists for those reference dates, and truth has
  settled.
- Root cause: player.js `renderStats` uses the "no FluSight round" cell
  only for manifest no-data weeks (`isNoData`). The payload does not say
  that a stored week has no round.
- Fix: `app/core/playback.py` `_no_round(asof, truth)` is true when:
  - the hub clone has `model-output/FluSight-baseline` at all;
  - there is no baseline file for this week's reference date;
  - the week's target (asof + 7) has settled truth (US).
  It is computed on every serve (cached or fresh), so an Update data that
  brings the round clears it, and it is added to the payload as
  `no_round`. The player reads `(nodata || (pl && pl.no_round))` for
  the week cells. SEASON SO FAR is unchanged (it carries what scored
  before, or "pending").
  Conservative on purpose:
  - a sparse clone with no baseline folder keeps "pending" (the
    Update-data hint covers it);
  - a week whose truth has not settled keeps "pending" (a stale clone
    may not have pulled the round yet).
- Tests: `test_a_settled_week_without_a_flusight_round_says_it_never_scores`
  (fresh, cached, and cleared when the round arrives);
  `test_a_week_is_not_called_roundless_on_too_little_evidence` (no
  baseline folder; unsettled truth). Pins extended with `no_round`:
  test_playback's payload keys, test_retro_player's contract keys,
  test_player_js's wiring string.
- Live after: 2025-08-30, 2025-09-20 and 2026-27's 2026-09-26 read "no
  FluSight round". 2025-11-22 still scores (0.497). The season report
  reads it too, since it embeds the same payloads.
- Risk: the payload gains a key; CACHE_V is unchanged because the key is
  computed per serve. Invariance: no (playback is not on the run path).
- For Ely: none.

## RE-15 (also: UI-06)
- Reproduced: yes. /retro/2025-26 at 1280 and 390:
  - "Sep" (f 0.033) and "Nov" (f 0.067) print as "SeNov";
  - "Jun" at f 1.0 overruns the track's right end (712 > 708 px);
  - "Aug" (the first week) has no label.
  UI-06's "Oct is missing" has a different cause: no October week is
  stored (the timeline jumps from 2025-09-20 to 2025-11-15), and the
  scrubber steps by stored week, so there is no October position to
  label.
- Root cause: templating.py `_month_ticks_for_dates` marks only month
  changes after the first date. The template places each label by index
  (`--f`), centred, with no collision or end check. The track is 210 to
  603 px wide depending on the layout (measured at 320 to 1600), so no
  server-side spacing can work.
- Fix:
  - `_month_ticks_for_dates(dates, first=False)`: `first=True` labels the
    first date's month. Only the scrubber passes it; the cumulative
    chart's ticks are unchanged.
  - `fitTicks()` in retro_season.html, beside `cumLabels`, with the same
    debounced resize and `fontsizechange`, plus `document.fonts.ready`.
    It measures the labels: an end label is pulled inside the track
    (`transform: none` at the left, `translateX(-100%)` at the right);
    a label closer than half an em to the previous shown one is hidden;
    the season's last month keeps its label and the one before gives way.
- Tests: `test_the_scrubber_labels_the_first_weeks_month_too` (the helper
  and the rendered first and last ticks);
  `test_the_scrubbers_months_are_fitted_inside_the_track_and_apart` (the
  rules and the resize wiring).
- Live after, at 320, 390, 480, 600, 768, 900, 1024, 1280 and 1600 for
  2025-26 and 2024-25: no overlap and nothing outside the track at any
  width. 2025-26 at 1280 reads "Aug Dec Jan Feb Mar Apr Jun", at 390
  "Aug Dec Jan Feb Mar Apr May Jun". The narrowest tracks (480, 600:
  210 px) drop alternate months. The season report fits the same way.
- Risk: the scrubber's labels only. Invariance: no.
- For Ely: none.

## UI-01 (also: none)
- Reproduced: yes. Playwright with reducedMotion "reduce", 2024-25,
  California clicked in the per-state table: scrollY 1026 → 1026, the
  player card 561 px above the viewport, the view switched. With
  "no-preference": 1026 → 465, card top 0.
- Root cause: base.html's capture click guard restores the scroll when it
  moved more than 50 px within two frames of a non-link click. The
  instant scroll of reduced motion lands inside that window and is
  undone. A smooth scroll moves less than 50 px in two frames, so the
  guard leaves it be.
- Fix: the rt-locbtn handler runs `scrollIntoView` after two
  `requestAnimationFrame`s, as model_settings.js already does with this
  guard. The guard itself is unchanged.
- Tests: `test_a_state_name_scrolls_after_the_click_guard_lets_go`.
- Live after: "reduce" 1026 → 465, card top 0; "no-preference" the same.
- Risk: none. Invariance: no.
- For Ely: none.

## UI-18 (also: none)
- Reproduced: yes. On the no-model-output server, /retro/2025-26 shows
  "0 jurisdictions scored", the filter box, and three bare "LOCATION"
  headers (the column copies).
- Root cause: retro_season.html renders the filter and the table whatever
  the rows are, and the column script copies the empty table.
- Fix: with no state row and no US row, the card shows the kit's empty
  state `tips.empty("Arrives with the first scored week", "clock",
  compact=True)` in place of the filter and table. That phrase is the
  one the cumulative chart already uses, so no new words. The fold, its
  heading and its badge stay. The script already returns when there is
  no `#sf-table`.
- Tests: `test_a_season_with_no_scored_state_shows_an_empty_state_not_headers`.
- Live after: 390 light and dark, 1280: the heading, the tag, "0
  jurisdictions scored", then the clock and "Arrives with the first
  scored week".
- Risk: none. Invariance: no.
- For Ely: none.

## UI-20 (also: none)
- Reproduced: yes. At 390 the alert runs 8 lines of monospace:
  "FileNotFoundError: the hub clone has no model-output/FluSight-baseline
  (sparse checkout predates …)", with "Data tab" pinned at the right.
- Root cause:
  - retro_season.html puts the raw message (`<code>`) in the alert;
  - the kit's alert keeps the action beside a 14rem text column.
- Fix:
  - routes/retro.py `SCORE_FAILURES` and `score_error_plain(err)`: the
    known failure (no FluSight-baseline in the clone) reads "The FluSight
    baseline forecasts are not on this computer yet. Update data from the
    Data tab, then open this page again." This is NO_TRUTH's wording
    style. `season_page_context` passes it as `score_plain`.
  - The alert shows "Scoring failed." plus the plain sentence (if any),
    and the raw message in a kit fold `tips.fold("Details")`, so unknown
    failures are folded too.
  - tabs/retro.css: under 30rem `.rt-failalert > .uk-alert-text` takes
    the line, so "Data tab" drops under the text. This is scoped to this
    alert; the kit's alert elsewhere is unchanged.
- Tests:
  - `test_a_known_scoring_failure_reads_in_plain_words`;
  - `test_an_unknown_scoring_failure_folds_its_message`;
  - `test_on_a_phone_the_failures_link_drops_under_its_text`.
  test_season_run_marks' pin splits the alert at its end (`</span></div>`)
  instead of the first `</div>`, which is now the fold's, and checks the
  fold.
- Live after:
  - 390 dark and light: "Scoring failed. The FluSight baseline forecasts
    are not on this computer yet. Update data from the Data tab, then open
    this page again.", then "› Details", then "Data tab" on its own line;
  - 1280: one line of text, Details under it, Data tab at the right.
- Risk: the alert's markup. test_server_hardening's escaping check still
  passes, because the code is escaped in the fold. Invariance: no.
- For Ely: none.

## Checks
- All 10 new tests fail on dev 68816e0 (with `score_error_plain` stubbed
  so the file imports there) and pass on the prototype.
- Touched existing tests: test_player_js, test_retro_player,
  test_playback, test_season_run_marks, test_server_hardening,
  test_results_prep, test_report_parity, test_report_season,
  test_design_batch3, test_retro_design_pass, test_ui_layout and the
  a11y tests all pass.
- ruff (the F gate) clean.
- Full suite (FLUBNF_HUB=/nonexistent): 3515 passed, 155 skipped.
- Windows: no paths, encodings or line endings touched. The JS is ES2015
  like its neighbours (arrow functions, const and let, as cumLabels).

## Patch
G10/proposal.patch (git diff origin/dev...proto/G10-A)
