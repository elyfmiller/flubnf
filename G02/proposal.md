# G02 run-input: proposal (A)
Base: origin/dev 301466c (G01 merged: no FLUBNF_HUB needed for tests)

## FC-06 (also: none)
- Reproduced: yes. Live (dev 237900f, then 301466c), Chromium: Model = Both, Model settings open, Particles = 1e4 (checkValidity() true), Run models: lands on /run with HTTP 422 and the int_parsing JSON. curl: the same for replicates=2.5, weeks_to_drop=2.5 (and members, weeks_to_nowcast, drop_same_day, which no form lets you type). A cleared field posts "" and falls back to the default (FastAPI treats it as missing): fine, unchanged.
  Same mechanism, same panel rows, not in the hunt: POST /run/dataset (the Forecast tab's "Your data" panel) and POST /retro/run (the Retrospective panel) give the same raw 422 for particles=1e4.
- Root cause: `app/ui/routes/forecast.py` run_models declares `weeks_to_drop`, `replicates`, `particles` as `int = Form(...)`, so FastAPI rejects a non-integer before the handler runs. These are the panel's own rows under their older names (knobs.FIELD_OF: the panel names pf.particles "particles"), and the handler already passes them raw to `knobs.resolve(legacy=...)`, whose parser refuses a non-integer in words and opens the panel on it (ms_refused), exactly as for every `knob.<key>` row. Same in `datasets_ui.run_dataset` (weeks_to_drop, replicates, particles) and `routes/retro.retro_run` (particles, replicates).
- Fix: declare those fields `str` (defaults "0", "3", "10000") in the three handlers, so they reach the knob parser as typed. /run: "Not run: model settings: pf.particles: '1e4' is not a valid int." and the panel opens with "Particles: '1e4' is not a valid int." under its head, the typed 1e4 kept in the field. /run/dataset: the same refusal on the dataset's page. /retro/run: "Not started: model settings: ...". The rerun path's direct call still passes ints; the parser takes both.
  Accepting 1e4 as 10,000 was the other option the bug allows; I kept the refusal: it changes no knob parsing (an int knob refuses "2.5", "1e4", "lots" everywhere today, CLI included, and test_knobs pins that), it is what a `knob.<key>` number row already does, and the spec never records a value the user did not type. Note for B: the panel's own script reads 1e4 as 10,000 (parseFloat), so its head badge says "default" while the server refuses; that is the existing behaviour of every int `knob.<key>` row too, untouched here.
- Tests: `app/tests/test_run_input.py::test_a_number_the_browser_allows_is_refused_in_words_on_the_panel` (particles 1e4, replicates 2.5, weeks_to_drop 1e1: 303 back, nothing started, the flash, the panel open on the refusal with the label and the typed value), `::test_the_dataset_run_refuses_it_in_words_too` (weeks_to_drop 1e1; particles does not apply to a Groundhog dataset run and is ignored, as before), `::test_a_replay_refuses_it_in_words_too` (replicates 3.5).
- Risk: what reads `_last_form["particles"|"replicates"|"weeks_to_drop"]` now sees the string the form posted (the panel and the model pages str() it already; forecast_aids compares knob raws). Invariance check: yes, done (below).
- For Ely: none. Not done: `/retro/run`'s `width` (runners, the Retrospective form, not the panel) has the same `int = Form` and the same 422 on 1e1; outside this group's bugs (G23 is that form), so left as is.

## FC-08 (also: MO-03, WI-02)
- Reproduced: yes. Live quick run on /model/analogue with "arizona, Ohio": run ok, label "2 states: arizona, Ohio", submission file location column 39 only, "Missing from this file: arizona". MO-03/WI-02's abbreviations, typos, duplicates and "US+(national)" are the same path.
- Root cause: `forecast.py` `_location_list` passes every typed name through (`state_names(locations)`), with no check against the hub's location list; the engines then find no data for an unknown name and the run still ends ok.
- Fix: `_location_list` returns (names, unknown): each typed name takes the hub's spelling whatever its case (`{name.lower(): name}` over load_locations' 52 jurisdictions), duplicates collapse in order (`dict.fromkeys`), and names the hub has no location for come back as unknown; run_models refuses them before anything is claimed: "Not run: unknown location: Arizonna." / "Not run: unknown locations: OH, AZ." (back on the posting page; at most five named). "all" and the US spellings are unchanged (is_us), so the Forecast form's checkboxes and a re-run's recorded names run as before. Abbreviations are refused by name rather than guessed (the field's placeholder asks for state names).
- Tests: `::test_a_typed_name_takes_the_hubs_spelling_once` ("arizona, Ohio, OHIO" runs Arizona and Ohio), `::test_an_unknown_name_is_refused_by_name` (a typo, abbreviations, "US+(national)"), `::test_the_forecast_forms_names_and_us_still_run` (Ohio, District of Columbia, "US (national)"; and "all" is 53 with US last).
- Risk: load_locations is now read for every custom pick, not only "all" (it falls back to the vendored copy; a failure is the existing "could not read the state list" refusal). Invariance: yes.
- For Ely: none.

## MO-07 (also: none)
- Reproduced: yes. /models and /model/pf2s: `min="1" max="9"`; with 10 in the field the browser blocks the submit ("Value must be less than or equal to 9."); the knob allows 1 to 10.
- Root cause: hard-coded `max="9"` in `app/ui/templates/model.html` and `research_run.html`.
- Fix: both read the range from the pf.replicates knob (`replicates_knob.lo/hi`, passed by `routes/models.py` through forms' lazy `_knobs`, so the server still imports no app.core.knobs eagerly: `test_ui_layout::test_importing_the_server`).
- Tests: `::test_the_model_pages_take_the_replicates_the_knob_allows` (/models and /model/pf2s: min 1, max 10). Browser after the fix: 10 is valid on both.
- Risk: none beyond the two templates. For Ely: none.

## MO-22 (also: none)
- Reproduced: yes. /model/analogue, date 2026-10-21 (a Wednesday), Run Groundhog only: recorded for 2026-10-17, no notice.
- Root cause: `forecast.py` run_models snaps a non-Saturday through resolve_anchor with "no banner" because the Forecast form shows the anchor; the model pages' bare date input does not.
- Fix: once the run is claimed (so a refusal never carries it), when the day was moved and the posting page is not /forecast (Referer, as `_back` reads it): "Anchor week 2026-10-17: the newest week on or before 2026-10-21." The Forecast tab is unchanged (no notice: its anchor line shows it).
- Tests: `::test_a_quick_run_on_a_weekday_says_which_week_it_took` (from /model/analogue: the notice; from /forecast: none).
- Risk: one sentence on the landing page. Note for B: the run lands on /forecast#results, so the notice sits above the viewport (150 px on desktop, 870 px on phone), as every notice a started run gives does today ("Recorded as a vintage run"); the Running card's Run settings show "forecast date 2026-10-17" in view. The hint's other option, `step="7"` on the two quick-run date inputs, would refuse a weekday in the browser instead; I did not take it: the Forecast tab takes any day and snaps, and WebKit's (the macOS window's) date-step validation cannot be checked here.
- For Ely: none.

## Checks
- New tests: 13 in app/tests/test_run_input.py; on dev 12 of them fail (the 13th, the Forecast form's own names, is a guard and passes on both).
- Targeted: the run, dataset, retro, knobs, models, forecast, layout and marks test files: all pass (1101). ruff F821/F823/F811/F401 on app/ui: clean.
- Output invariance: all-53 Groundhog run on 2026-10-17, dev 301466c and the prototype: the same submission file, md5 56da9201b416eb5c80317c849b55168e.
- Browser (Chromium, 1280x900): the panel refusal, the model-page refusal, the replicates range and the notice, each seen; screenshots in my scratchpad.

## Patch
G02/proposal.patch (git diff origin/dev...proto/G02-A)
