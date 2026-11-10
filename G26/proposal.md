# G26 forecast-panel: proposal (A)
Base: origin/dev 836698a (G24 merged; dev is now 78e2843, a TEAM.md entry)

How: a dev server (8813) and a prototype server (8812) on a private copy of
the shared hub (target-data, auxiliary-data, hub-config) whose live file
has Arizona at 0 and Ohio at 2 on 2026-10-17 (the hunt's case: "0 after
67, 59, 29", "2 after 75"). curl through POST /run for the run paths;
Chromium at 1280 px for the page; 390 px dark for the box and the panel.

## FC-13
- Reproduced: yes. Arizona "Level", "Newest weeks reading 0" = counted as
  unreported, Groundhog, all: the run page says "Arizona: reads 0 after
  67, 59, 29; level" and "Missing-data rules ... treated as unreported
  (set aside (Forecast tab), trailing zero): Arizona 1, Ohio 1"; the box
  after the run still offers No forecast, Level, Extend, Blend (Level
  selected).
- Root cause: the engines apply the run-wide rule first (missing.rules_for
  keeps data.trailing_zero for every state; trim_flags -> tail_flags
  moves the anchor back a week), so the state's zero-anchor choice never
  applies; routes/forecast._data_choices records it anyway, and the box
  offers it whatever the settings say. The same holds for a collapsed
  state's Keep under "Collapsed newest week" (data.partial_week), and for
  a 0 after a week of 20 or more under that setting (tail_flags fires on
  both).
- Fix (precedence as the engines already apply it: the run-wide rule):
  - reported.covering_rules(g): the settings that, at "missing", count the
    state's newest week as unreported (tail_flags per key); box rows carry
    them (`rules`). RULE_LEAVES = set_aside, omit.
  - _data_issues.html: each covered select names its settings
    (data-rules); its script hides and disables every other choice while
    one of them is "missing" in the panel (on load, once the panel is in
    the page, on a change, and after Reset to defaults through an
    `ms-reset` event model_settings.js sends), moving a hidden choice to
    "Both from"; the "recommended" check follows; "All zero states:"
    skips disabled choices.
  - _data_choices: under the posted settings a covered state is offered
    only RULE_LEAVES; another choice is refused in words ("Not run: Data
    issues for Arizona: Level does not apply while Newest weeks reading 0
    is set to counted as unreported; choose Both from 10-10 or Leave
    out."); with no answer (the box disabled) the rule covers the state
    and nothing is recorded, as the zero-anchor setting already does; a
    covered state's recommendation is "set_aside".
- After: rule on, Arizona offers "Both from 10-10 / Leave out" (Ohio too
  once "Collapsed newest week" is on); the run page "2 states, 2
  recommended, 0 changed; 2 set aside" and "(set aside (Forecast tab)):
  Arizona 1, Ohio 1"; after the run and a reload the box still follows
  the setting; after Reset to defaults every choice is back.
- Output: no forecast number changes, as the rule already won: the all-53
  check (shared hub, rule off) 56da9201 on both; on the flagged copy with
  the rule on and no box answers, dev and prototype both 7e165871.
- Tests: test_forecast_panel_fixes.py
  `test_a_run_wide_rule_leaves_a_covered_state_both_from_and_leave_out`,
  `test_the_box_follows_the_setting_in_the_page`.
- Risk: routes/forecast.py's run path (output check above); engines and
  missing.py untouched.
- For Ely: the precedence. This keeps the engines' order (the run-wide
  setting over the state's choice); the other way (a state's Level beats
  "counted as unreported") would change what both engines read for that
  state, so it is not done here.

## FC-18
- Reproduced: yes, 1280 px: Ohio's select reads "Both from 10-1" (98 px of
  text in 90 px).
- Root cause: tabs/forecast.css gives the select `flex:1 1 7.5rem;
  min-width:7.5rem` beside an 8.5rem name block in a ~270 px box.
- Fix: `min-width:min-content` after the 7.5rem (the fallback): the select
  is never narrower than its widest option; beside the name when both fit,
  under it otherwise (the box's flex-wrap already does that on phones).
- After: 1280 px both selects under their names, whole; 390 px dark
  Arizona's under, Ohio's beside, whole; no sideways scroll.
- Tests: `test_a_data_issues_select_is_never_narrower_than_its_words`.

## FC-21
- Reproduced: yes, for Replicates 0, Prior range for Reff "2.5, 0.6",
  Kernel jitter "abc", Own-state donor weight 7 and Oracle blend weight
  "x": a top notice "Not run: model settings: pf.prior.Reff: prior_ranges:
  Reff__FREE [2.5, 0.6] is not a valid uniform_var range." and the panel's
  "Prior range for Reff: prior_ranges: ..."; "'abc' is not a valid float."
- Root cause: routes/forecast.py flashes the raw KnobError as well as
  setting `ms_refused`, which the panel shows (forms._refusal_words maps
  only the key to its label).
- Fix: the two model-settings refusals in the run route set `ms_refused`
  only (the panel opens on it and is brought into view, as now);
  forms._refusal_words also turns the registry's type words and the
  particle filter's prior check into plain words: "is not a number", "is
  not a whole number", "is not two numbers, low then high", "is not on or
  off", "is not a date"; "2.5, 0.6 is not a range: the low end must be 0
  or more and below the high end" (above 0 for a log-scale prior, the
  engine's rule). knobs.py and the CLI are unchanged; the Retrospective's
  panel reads the same words.
- After: no top notice; the panel: "Kernel jitter: 'abc' is not a
  number.", "Prior range for r: 0, 40 is not a range: the low end must be
  above 0 and below the high end.", "Replicates: 0 is outside 1 to 10."
- Tests: `test_a_model_settings_refusal_is_said_once_in_plain_words`;
  pins of the old notice moved to the panel's text (the duplicate is the
  bug): test_knobs_wiring `test_a_refused_knob_starts_nothing` (13 cases),
  `test_older_field_names_are_the_same_knobs`,
  `test_a_number_the_browser_allows_is_refused_on_the_panel` ("is not a
  whole number"), test_knobs_panel
  `test_a_refused_submission_keeps_the_typed_values_and_reads_modified`,
  test_forecast_modes `test_run_refuses_a_season_start_that_is_not_before_the_week`
  ("Season start: 'not-a-date' is not a date." under the panel),
  test_research_run `test_particles_defaults_and_refuses_out_of_range`.
- Not changed: the Retrospective's and the Data tab's own run routes keep
  their notice (their pages, not this bug).
- For Ely: none

## FC-22
- Reproduced: yes: after the Reff refusal, Reset to defaults resets the
  values and the badge, and the warning stays.
- Fix: model_settings.js's Reset hides `.fc-ms-refused`.
- After: hidden after Reset (Forecast; the Retrospective panel shares the
  script).
- Tests: `test_reset_to_defaults_hides_the_refusal`.

## FC-23
- Reproduced: yes: clearing the date gives "No archived week on or before ."
- Fix: forecast.html noWeek('') returns "Pick a forecast date."
- Tests: `test_a_cleared_date_asks_for_one_and_the_picker_follows_the_date`.

## FC-25
- Reproduced: yes: Vintage, pick 2026-09-26, type 2026-05-16: the picker
  still shows 2026-09-26 (a real browser fires no change on re-choosing it).
- Fix: paint() sets the picker to the date when the date is an archived
  week, else to its placeholder.
- After: typing 2026-05-16 shows 2026-05-16 in the picker; a non-archived
  day shows "or pick an archived week (N)", so any week can be picked.
- Tests: as FC-23.

## Checks
- New app/tests/test_forecast_panel_fixes.py (6): each fails on dev and
  passes here; with the Data issues, knobs, forms, dataset and a11y tests:
  252 passed. ruff (the gate) clean.
- Full suite (FLUBNF_HUB=/nonexistent): 4223 passed, 160 skipped, 2 failed:
  test_forecast_modes and test_research_run, two more pins of the old
  notice, moved to the panel's message as above; both files then pass.
- Output check: as under FC-13 (md5 equal both ways).
- Windows: no paths; the JS and CSS are ASCII.

## Patch
G26/proposal.patch (git diff origin/dev...proto/G26-A)
