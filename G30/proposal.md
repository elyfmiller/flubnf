# G30 forecast-text: proposal (B)
Base: origin/dev de4eb1f8 (G27 merged)

How: a dev server (8825) and then the prototype on a private hub copy whose
newest week (2026-10-24) has Alaska's row removed, Arizona at 0 and Ohio at
2, and whose archive lacks 2026-01-17 (a one-week gap); runs through POST
/run with Data issues choices (carry, level, set_aside) and one with a
changed knob exported under the hub names; Chromium at 1280 px light and
390 px dark for the marks, the box and the mode buttons; the Methods page
and the panel read through curl.

## FC-26
- Reproduced: yes: with the three flagged states the Forecast page showed
  the Settings "i", the newest check's "?", the Data issues "i", an "i" per
  state, the panel's "i", and after a run three "?" in Latest run's Results
  (unreported weeks, newest week reading 0, data issues); the issues were
  stated by the check's badges, the box, the settings' "Data issues" pair
  and two Results rows.
- Fix: the newest check line is the head of the Data issues box (the mark,
  "52 of 53 reported", a badge per kind of issue) and keeps no "?" there
  (`_newest.check(bare=True)`); it stands alone, with no "?", only when
  every state reported cleanly (no box). The per-state "i" goes: the flag
  stands beside the name. The box's "i" goes: the Settings card's "i" (the
  page's one explainer of its fields) gains one line, "Data issues: a state
  whose newest week reads 0, collapsed or was not reported. Each select
  starts on the recommended choice; the choice is this run's and is
  recorded with it."; what each choice does and the recommendation rule
  move to Methods' "A newest week that reads 0, collapses, or was not
  reported" fold. In the Results table the Data issues row, which counts
  the zero-anchor outcomes and names each state's, stands in for the
  "Newest week reading 0" row (that row shows only on a run without a
  choices record); the settings' "Data issues" pair (what was asked) stays
  beside the Results row (what happened).
- After: before a run two "i" (Settings, the panel) and no "?"; after a run
  with the three states, two "?" in Results (the unreported weeks' engine
  notes, the data issues). The box head at 1280 and 390 px, light and dark,
  wraps its badges with no sideways scroll.
- Tests: test_forecast_text.py `test_the_weeks_issues_are_stated_once_on_the_forecast_tab`,
  `test_a_clean_week_keeps_the_plain_check_line`,
  `test_the_results_table_states_the_data_issues_once`; the pins of the
  per-state "i", the box's count badge and its "i" text (test_data_issues),
  and of the check's "?" text and hidden flag on the Forecast tab
  (test_newest_reported) read the box.
- Risk: the Forecast tab's template and the box; `results_html` (both
  pages, the report's results table); the engines untouched. Invariance
  check: yes, see Checks.

## FC-27
- Reproduced: yes: the run page's Data issues tip "Alaska: no row; carry.
  Ohio: reads 2 after 82; set_aside."; the count "1 zero-anchor level"; the
  box's flag "no row".
- Fix: `reported.choice_text(entry)` says a recorded choice as the box
  offered it ("both from 10-17", "from 10-17", "level", "kept", "left out",
  "no forecast"); `reported.reason_text` reads an older record's "no row"
  as "not reported", and REASON_TEXT["no row"] is "not reported" (the
  box's flag, the Data tab's "Not reported: Nebraska."). The carry entry
  now records its `from_week` as set-asides do (routes/forecast
  `_data_choices`), so the page can name it; an older record reads "from
  the last reported week". `missing.choices_line` counts a zero-anchor
  rule by its name ("2 level"); `runs.data_issues_label` names a changed
  state's choice the same way and the run-wide rule by its label ("Newest
  week reading 0: level").
- After: "Alaska: not reported; from 10-17. Arizona: reads 0 after 63, 69,
  60; level. Ohio: reads 2 after 82; both from 10-17."; "1 set aside, 1
  level"; the settings pair "3 states, 2 recommended, 1 changed: Arizona
  level".
- Tests: `test_the_run_pages_say_each_choice_in_the_boxs_words`; the pins
  of "zero-anchor level", "Ohio abstain, Utah keep", "zero-anchor rule
  blend" (test_data_issues) and "No row:" (test_newest_reported) read the
  new words (they pinned the keys).
- Risk: the recorded entry gains one key for a carry choice; the engines
  read "choice" and "reported" only (missing.rules_for). Invariance check
  covers the run path.

## FC-28
- Reproduced: yes: "Fixed by the model definition" (14 internal keys and
  values: oracle.identity_rule R_EITHER, pf.engine_keys, DEFAULTS_BLOCK,
  gamma 2.1875, ...), "5 coming later" (disabled rows), and hints "fewer
  than 3 breaks rule 3", "Liu-West kernel scale h; the sealed record ran
  0.30", "Pins rho*mult and i0", "the seal ran 2".
- Fix: the panel (Forecast and Retrospective) renders neither fold; the
  coming-later knobs are not posted (Methods' Model settings table already
  tags them "coming later"); Methods' Model settings card gains the fold
  "Fixed by the model definition" (value, set to, why; routes/methods
  `fixed_settings` from knobs.LOCKED). Four hints rewritten in knobs.py
  (the Methods table reads them too): "Seeded filter runs per
  jurisdiction, pooled; 3 or more keep the registered method.", "How far
  each particle's parameters are nudged between weeks; larger explores
  more.", "What seeds the fit: admissions to date, the expected season
  total, or that total until 25% is in.", "Donor weeks within this many
  weeks of the year of the forecast week." (each under 100 characters).
- Tests: `test_the_panel_shows_only_what_a_student_can_set_and_methods_the_rest`,
  `test_the_knob_hints_name_no_internals`; test_knobs_panel's pins of the
  two folds read Methods, and its every-knob loop skips the coming-later
  knobs (they pinned the folds).
- Risk: a posted coming-later knob is still refused server-side
  (test_knobs_wiring); knob defaults, ranges and keys unchanged.

## FC-29
- Reproduced: yes: the Settings "i" said "any day anchors on the latest
  archived week on or before it" while Saturday 2026-01-17 (the gap) was
  refused and Sunday 2026-01-18 anchored on 2026-01-10; the refusal's
  detail "Such gaps are real, usually holiday weeks."
- Fix: the tip reads "Forecast date: a Saturday must be an archived week;
  any other day anchors on the latest archived week before it." (the rule
  as /run applies it); the refusal's detail measures the gap
  (`_gap_weeks`): "The archive skips 1 week after 2026-01-10 (usually a
  holiday week)." for one or two weeks, "The archive skips 28 weeks after
  2024-04-27." for an off-season gap, "The archive has nothing after X
  yet." when no later snapshot exists; the rest of the detail as before.
- Tests: `test_the_archive_gap_is_said_as_wide_as_it_is`,
  `test_the_gap_refusal_names_holidays_only_for_a_short_gap`.

## FC-30
- Reproduced: yes: `role="tablist"` with two `role="tab"` buttons,
  aria-selected, no panels, no arrow keys.
- Fix: `<div class="modes" role="group" aria-label="Forecast mode">` with
  the two buttons carrying aria-pressed (the script and nau.css read it),
  as the page's other segmented controls and the season page's view
  switcher. The data-mode attributes and the hidden mode field are as
  before.
- After: pressing Vintage reads aria-pressed true/false, no tablist.
- Tests: `test_the_mode_pills_are_a_pressed_button_group`.

## FC-33
- Reproduced: yes: "Files named: hub names, by override" in the Modified
  card and "files: hub names, by override" in Run settings; the card's
  heading "Run settings" over a sub-heading "Settings".
- Fix: the run page's settings list drops the "files" pair when the
  Modified model settings card is shown (routes/forecast run page);
  `settings_html` renders no title when given none, and run.html passes
  none for the first block ("Produced by" keeps its own). The report and
  the Latest run card keep the pair (no Modified card there).
- Tests: `test_the_run_page_says_the_files_line_and_the_settings_heading_once`; test_settings_block's pin of the titled block reads the untitled one.

## Checks
- New app/tests/test_forecast_text.py (10); with test_data_issues,
  test_newest_reported, test_knobs_panel, test_knobs, test_knobs_wiring,
  test_forecast_modes, test_forecast_mechanics, test_forecast_panel_fixes,
  test_remembered_form, test_fewer_marks, test_a11y_basics,
  test_dataset_replay_knobs, test_run_results, test_data_source,
  test_run_timing, test_season_run_marks, test_output_run_pages,
  test_pages, test_ui_layout: 502 passed. ruff (the gate) clean.
- Full suite (FLUBNF_HUB=/nonexistent, test_doctor deselected: this container's Python): 4228 passed, 159 skipped, 0 failed on the final commit. (Two earlier runs, each beside another suite on the same 4 CPUs, showed 5 to 7 failures in test_season_run_marks and once test_sandbox_guard, run-page and sandbox tests this change does not touch; they pass alone, pass after the sandbox tests, and did not recur: load, not the change.)
- Output check: an all-53 Groundhog run on 2026-10-17 on the shared hub,
  dev de4eb1f8 and the prototype: md5 56da9201b416eb5c80317c849b55168e
  both.
- Windows: `_gap_weeks` uses date.fromisoformat; the templates, hints and
  tests are ASCII.
- For Ely: none.

## Patch
G30/proposal.patch (git diff origin/dev...proto/G30-B)
