# G18 home-map: proposal (B)
Base: origin/dev 2379a2e

How: a server from dev and one from the prototype, each with a Groundhog
run for US alone, one for Arizona and New York, and an all-53 run on
2026-10-17; Home read with curl and in Chromium at 1280 px (light,
dark, Dracula, Nord) and 390 px dark; a phone context with touch (CDP
touch events for the swipe); the keyboard walked from the Weekly report
button; HM-03 by moving the newest run's report.html and
report_inputs.json aside.

## HM-02 (also: none)
- Reproduced: yes. "US categorical forecast · 2026-10-17" over a map
  whose report is titled "reference date 2026-10-24" and whose file is
  2026-10-24-NAU_PyBNF-GroundHogCGR.csv.
- Root cause: home.py puts the run's as-of date in the heading.
- Fix: the heading carries the reference date (`report_v2.report_dates`,
  the report's own rule: as-of + 7), and the bar gains a "Data through
  2026-10-17" fact beside Coverage, so both dates are named for what they
  are (Output's way: the reference date heads, the as-of beside it).
- Live after: "US categorical forecast · 2026-10-24", "Data through
  2026-10-17".
- Tests: test_home_map.py
  `test_the_heading_carries_the_reference_date_and_the_bar_the_data_date`;
  test_pages' pin of the as-of in the heading updated (the bug's symptom).

## HM-03 (also: none)
- Reproduced: yes. With the newest run's report gone: the Weekly report
  button is hidden, but the card's "i" still says "click one to open its
  section of the weekly report", every hover ends "click for details",
  and a click lands on /output/report's "No report yet".
- Root cause: home.py sets MAP_LINK and `clickable=with_data` whatever
  `_has_report` says; the template gates only the button.
- Fix: `_outlook_block_cached(rid, mtime, has_report)` (the cache key
  takes it): without the report no MAP_LINK is set, no state is
  clickable (`st noclick`, role="img", no "click for details"), and the
  "i" keeps "Hover a state for its numbers." without the click clause.
- Live after: MAP_LINK unset, Arizona `st noclick`, no "click" anywhere
  on the card; with the report back, as before.
- Tests: `test_without_the_report_no_state_is_a_link_and_nothing_promises_one`.

## HM-04 (also: none)
- Reproduced: yes. A US-only run: "US categorical forecast · 2026-10-17",
  "Coverage 0 of 52", an all-gray map, the national forecast (stable
  45%) nowhere; the all-53 run shows no national category either.
- Root cause: the US card has no shape on the map and nothing else shows
  it.
- Fix: a "United States" fact in the bar, "stable 45%" (the card's most
  likely category and its chance, as the state hovers word them:
  `_us_words`), from the US card the bundle or the quantiles give; with a
  model toggle the line follows the pressed model (a six-line script,
  the report's own idiom for its category lists).
- Live after: "United States stable 45%" on the US-only run and on the
  all-53 run; absent for the Arizona + New York run.
- Tests: `test_the_national_forecast_is_a_line_in_the_bar` (also the
  US-only run: a dated card, Coverage 0 of 52, the line present).

## HM-07 (also: none)
- Reproduced: yes. Phone (390 px, touch): a swipe up starting on the map
  leaves scrollY unchanged; `touch-action:none` on the svg.
- Fix: `touch-action:manipulation` (the page pans and pinches under a
  finger; only the browser's double-tap zoom stays off, as the map's
  double-click resets its view). Every map (Home, the report, Forecast)
  takes it.
- Live after: the same swipe scrolls 280 → 632 px.
- Tests: `test_the_map_scrolls_under_a_finger_and_is_a_named_group_in_order`.

## HM-16 (also: none)
- Reproduced: yes. After the Weekly report button, Tab lands on the svg
  itself (an unnamed image), then the states in the topology's order
  (Alabama, Alaska, Arizona, Colorado, Florida, Georgia, …).
- Fix: the svg is `role="group" aria-label="Map of the United States"`
  with `tabindex="-1"` (named, not a stop); a "Skip past the map" link
  (the kit's `a.skip`, shown on focus) before it, landing on an anchor
  after it; the states are drawn by name, so the keyboard walks them
  alphabetically.
- Live after: Tab: "Skip past the map", Alabama, Alaska, Arizona,
  Arkansas, California, …; Enter on the skip link, then Tab, lands past
  the map.
- Tests: the same test (the name, the skip link, the order).

## HM-18 (medium; also: none)
- Reproduced: yes. Arizona + New York run: the 48 other states take the
  "no data" swatch while their hovers say "not fitted in this run"; in
  Dark the swatch rgb(42,47,80) sits on the card rgb(21,23,41), 1.4:1.
- Fix: `map_legend(no_data)` names the uncoloured states "not in this
  run" when the run's scope is known (bundle v4+, as the hovers), "no
  data" otherwise (the hovers then say "no data in this view"); the
  swatch keeps an edge on any card (an inset 1 px line at 35% ink, the
  kit's `.sw`).
- Live after: "… increase · large increase · not in this run"; the
  swatch outlined in Dark, Dracula and Nord (screenshots at 390 dark and
  1280 light).
- Tests: `test_the_legend_names_states_left_out_of_the_run_and_keeps_an_edge`.

## UI-08 (also: none)
- Reproduced: yes, by tokens: the chips' `--gold-bright` on the hero's
  navy gives 3.79:1 in Dracula (#BD93F9 on #44475A) and 4.31:1 in Nord,
  for 13.3 px bold text.
- Fix: the chip labels take the hero's own white (`.hero .hm-facts b`
  in nau.css, beside the hero's other literals; the tab sheet keeps only
  the weight, as test_ui_kit asks of tab sheets), which every theme's
  navy already holds at 4.5:1 and the theme test checks; 8.6:1 and above
  everywhere.
- Live after: rgb(255,255,255) in Dracula, Nord and Dark.
- Tests: the legend test reads the rule; test_display_themes' white-on-
  navy check stands for the pair.

## Checks
- Targeted: test_home_map (5), test_pages, test_outlook_toggle,
  test_fewer_marks, test_display_themes, test_a11y_modes,
  test_report_design_pass, test_retro_national, test_retro_player,
  test_playback, test_report_season, test_site_build, test_window_comfort,
  test_categorical: 186 passed. ruff gate clean.
- Full suite (FLUBNF_HUB=/nonexistent), in a worktree pinned at the
  prototype: 3579 passed, 154 skipped; the two test_doctor failures are
  this container's Python 3.13, as on dev; the one other failure
  (test_ui_kit: a hex literal in a tab sheet) is the chip rule, since moved
  into nau.css, and the kit, map, theme and page tests pass on the amended
  commit (a second full pass is running and will be noted in compare.md).
- Invariance: not needed (home.py, usmap.py, two stylesheets, home.html;
  no run-path file).
- Windows: markup and CSS only.
- For Ely: none.

## Patch
G18/proposal.patch (git diff origin/dev...proto/G18-B)
