# G10 season-player: proposal (B)
Base: origin/dev 68816e0

Reproduced on two live servers from dev 68816e0: 8826 (a private hub copy
with the FluSight baseline, 2024-25 done with a placeholder week 2025-01-18,
2025-26 finished 31 weeks, 2026-27 done 5 of 6) and 8827 (no baseline, a
2026-27 six-state panel that never scored). Desktop 1280x900 and phone
390x844, light and dark.

## RE-04
- Reproduced: yes. /retro/2024-25?week=2025-01-18 (a placeholder week, no
  samples): the player's Models row showed only the officials; stepping to
  a real week kept the Groundhog out of the row for the whole visit.
- Root cause: `player.js` buildControls runs once (`P.built`) and reads the
  model list from the first payload; a no-data week's payload has no model
  members, so the replay's own model is never listed.
- Fix: the season page passes the season's stored members to the player's
  init (`catalog.models`, from `week_member_quantiles(root, weeks[-1])`,
  the last week; try/except to []), next to the official catalog the page
  already passes (`routes/retro.py` season_page_context,
  `retro_season.html`). buildControls already prefers `cfg.catalog` over
  the first payload, so no player change is needed for this bug.
- Tests: `test_the_player_gets_the_seasons_stored_members_as_its_catalog`
  (test_retro_player.py).
- Risk: none outside the season page's init; invariance: no.
- For Ely: none

## RE-11
- Reproduced: yes. /retro/2025-26, week 2025-08-30: truth settled, no
  FluSight round that week, yet This week and Season so far read "pending"
  for the Groundhog and the official, forever.
- Root cause: `player.js` weekCellState's "no FluSight round" cell is only
  reached from the manifest path; a week payload carries no mark that no
  round covers it, so renderStats falls to "pending".
- Fix: the week payload gains `no_round` (`playback.no_baseline_round`:
  the hub has a FluSight-baseline folder and that week has no baseline
  file; `CACHE_V` 8 so cached payloads rebuild) and renderStats treats
  `no_round` like no data: the cells read "no FluSight round". Without a
  baseline folder in the hub nothing changes (the page then shows the
  scoring-failed alert, UI-20).
- Tests: `test_a_week_without_a_baseline_round_says_so_in_its_payload`
  (test_results_prep.py); the payload contract sets in test_retro_player.py
  and test_playback.py, the CACHE_V pin in test_shipped_vintages.py, the
  wiring strings in test_player_js.py.
- Risk: a one-key payload addition and a cache version bump; invariance: no
  (playback only).
- For Ely: none

## RE-15 (also: UI-06)
- Reproduced: yes. /retro/2025-26 desktop: "Sep" drawn over "Nov"; phone:
  "Jun" clipped at the right edge; the first month (Aug) never labelled.
- Root cause: `retro_season.html` places the ticks by week index with no
  collision check and every label is centred (`translateX(-50%)`), so the
  last one hangs past the bar; `templating._month_ticks_for_dates` skips
  the first date's month (`prev` starts as the first month).
- Fix: the first date is labelled (`templating.py`); the first and last
  ticks get `first`/`last` classes and `retro.css` keeps them inside the
  bar (no shift / shift fully left); a small `tickLabels()` in the page
  hides a label that would overlap the one before it (the last label wins
  over its neighbour), re-run on resize and font-size change, like the
  existing `cumLabels()`.
- Tests: `test_the_scrubber_labels_the_first_week_and_keeps_the_ends_inside`
  (test_retro_player.py); test_month_axes.py's pins updated for the first
  month (the pinned behaviour is the bug: the first month was never
  labelled).
- Risk: `_month_ticks_for_dates` also feeds the other month axes (the
  first month now labelled there too, which is the same fix); invariance:
  no.
- For Ely: none

## UI-01
- Reproduced: yes. With `prefers-reduced-motion: reduce`, a state-name
  click in the per-state table left scrollY unchanged (999 -> 999); the
  player never came into view.
- Root cause: base.html's click guard undoes a scroll that happens within
  two animation frames of a non-link click; `scrollIntoView({behavior:
  'auto'})` under reduced motion scrolls synchronously, inside that window,
  so the guard puts the page back. Smooth scrolling escapes it only because
  it moves later.
- Fix: the rt-locbtn handler scrolls after two `requestAnimationFrame`s,
  past the guard's window, with the same behavior choice as before
  (`retro_season.html`).
- Tests: `test_a_state_name_click_scrolls_to_the_player_after_the_click_guard`
  (test_retro_player.py).
- Risk: none; invariance: no.
- For Ely: none

## UI-18
- Reproduced: yes. /retro/2026-27 on 8827 (unscored panel): the per-state
  card showed the filter row and a table with three bare "LOCATION"
  headers over nothing, under "0 jurisdictions scored".
- Root cause: `retro_season.html` renders the filter row and the table
  whether or not `states` has rows.
- Fix: with no scored state the card shows the kit's compact empty state
  "No jurisdiction scored yet" (`tips.empty`, id `sf-none`) instead of the
  filter row and table.
- Tests: `test_an_unscored_per_state_card_is_an_empty_state`.
- Risk: none; invariance: no.
- For Ely: none

## UI-20
- Reproduced: yes. /retro/2026-27 on 8827 (no baseline in the hub): the
  Scoring failed alert held the raw `FileNotFoundError: ... no model-output
  ... FluSight-baseline` in a monospace column; on the phone the alert was
  180 px tall with the Data tab link squeezed beside the text.
- Root cause: the alert prints `score_error` as its body; `.uk-alert-action`
  stays beside the text at every width.
- Fix: `routes/retro.py` `score_plain_words(score_error)` turns the known
  case (no FluSight baseline in the hub clone) into one plain sentence
  ("The FluSight baseline is not in the hub clone yet; Update data on the
  Data tab fetches it."); any other error reads "The error is below."; the
  raw error moves into a fold "The error" under the alert (`tips.fold`, id
  `rs-scorefail-raw`), so it is still there for Ely. `ui-kit.css`: under
  30em the alert's action drops under its text, full width (phone alert
  104 px).
- Tests: `test_a_known_scoring_failure_reads_plain_with_the_error_folded`
  (test_retro_player.py), `test_the_alerts_action_drops_under_its_text_on_a_phone`
  (test_ui_kit.py); test_season_run_marks.py's alert assertion updated to
  the new text and the folded `<code>`.
- Risk: the kit rule applies to every `uk-alert-action` on a phone (an
  action under its text is the better layout there too); invariance: no.
- For Ely: none

## Checks
- After the change, live: RE-04 the Models row keeps the Groundhog from a
  no-data week; RE-11 the cells read "no FluSight round"; RE-15 "Aug ...
  Jun" with no overlap, ends inside, desktop and phone; UI-01 reduce
  scrolls to the card (top 0); UI-18 the empty state; UI-20 the plain
  sentence, the fold, 104 px on the phone.
- Targeted (12 files incl. retro_player, season_run_marks, player_js,
  month_axes, results_prep, ui_layout, ui_kit, us_national): 276 passed.
  Full suite on the prototype: 3509 passed, 154 skipped, 2 failed
  (tests/test_doctor.py, environmental: Python 3.13 here) after the two
  payload pins above were updated. Ruff gate clean.

## Patch
G10/proposal.patch (git diff origin/dev...proto/G10-B)
