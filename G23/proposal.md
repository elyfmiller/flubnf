# G23 retro-forms: proposal (A)
Base: origin/dev b4b176b (G21 merged)

How: a dev server (8815) and a prototype server (8816), each with a
Groundhog replay of 2025-26 for Vermont (scoring fails on this sparse
hub; the weeks and the season report are written) and an uploaded
grouped dataset ("Kids", 226 weeks) whose replay was stopped after about
a second. Chromium for the season page's Show in folder and the Run form.

## RE-12 (also: WI-05)
- Reproduced: yes. /retro/2025-26, Show in folder (this container has no
  file manager): the bar showed and hid, nothing under the buttons, and
  nothing after a reload.
- Root cause: retro_season.html posts to /output/reveal with fetch and
  ignores the answer; the route flashes and 303s to the Referer, and the
  fetch follows it, rendering the season page in the background, which
  consumes the flash.
- Fix: the reveal answers a request that asks for JSON with {"ok": true}
  or {"ok": false, "why": ...} and no flash (routes/output.py); the
  season page sends Accept: application/json, reads the answer and calls
  its own fail(why) on a refusal (retro_season.html). The run page's and
  Output's form posts are unchanged (303 and the flash).
- After: under the buttons, "Could not prepare the file. Nothing opened:
  no file manager could be started. The file is at .../2025-26-FluBNF-
  season-report.html."
- Tests: test_retro_forms.py
  `test_show_in_folder_answers_a_script_with_its_outcome`.
- Risk: none for the form posts. The alert's title is fail()'s fixed
  "Could not prepare the file." (the export's and the report's), kept
  rather than adding a second wording.
- For Ely: none

## RE-13 (also: none)
- Reproduced: yes. Season 2023-24, custom scope with no state ticked,
  states only, Groundhog only, blend; Run: "Not started: no locations
  checked for the custom scope." and the form back at rt-season=2026-27,
  retro-scope=panel6, rt-national=1, rt-zero-anchor="" (Choose…).
- Root cause: retro.html renders fixed defaults; nothing keeps the
  posted fields (the Forecast tab keeps `_last_form`).
- Fix: routes/retro.py `_last_retro_form` (this console session) holds
  the form as posted, saved before the first check, so a refusal or a
  run shows it again; the page prefills the season, scope (and the
  custom checklist, shown when custom), US national, shard width, engine
  preset, the zero rule and the Model settings panel's values
  (`_knob_panel("retro", form)`). A refusal over the model settings opens
  the panel once (`ms_refused`, as the Forecast tab's). No new control.
  conftest clears the memory around each test (`_retro_form_forgotten`).
- After: rt-season=2023-24, retro-scope=custom, rt-national=0,
  retro-engine=analogue, rt-zero-anchor=blend after the same refusal.
- Tests: `test_the_run_form_shows_its_choices_again_after_a_refusal`
  (and the panel opening on a model-settings refusal, then closed again).
- Risk: in memory only (a restart opens the defaults, as before); the
  no-engine default (Groundhog only) holds until the user picks the
  Oracle preset (test_retro_archive's RE-23 test passes).
- For Ely: none

## RE-24 (also: none)
- Reproduced: yes. The stopped replay's page links only the tabs and
  ?h=1..3; Retrospective opens the FluSight hub tab. (Its other half,
  /retro/dataset/nope/<stamp> as bare text, is G22's, #80.)
- Fix: "Back to the replays" (/retro?dataset=<id>) at the end of the
  page's facts line (retro_dataset.html).
- After: the link, at 1280 light and 390 dark, no sideways scroll.
- Tests: `test_a_stopped_replay_leads_back_and_says_how_far_it_got`.
- For Ely: none

## RE-25 (also: none)
- Reproduced: yes. Replay stopped at 128 of 226 weeks: badge "stopped",
  "No forecasts stored yet"; 128/226 only in the replays list.
- Fix: a stopped or interrupted replay short of its weeks reads "stopped
  after 122 of 226 weeks" in its status badge, and the empty chart says
  "No forecasts stored", with "yet" only while it runs (as "No scored
  cells" already does).
- Tests: the same test.
- For Ely: none

## Checks
- New app/tests/test_retro_forms.py (3): each fails on b4b176b and passes
  here. The retro, reveal, dataset and marks tests (302) pass. ruff clean.
- Full suite (FLUBNF_HUB=/nonexistent): 4208 passed, 160 skipped, 0 failed.
- Output check: not needed (forms and pages only).
- Windows: none (templates, an in-memory dict, a JSON answer).

## Patch
G23/proposal.patch (git diff origin/dev...proto/G23-A)
