# G23 retro-forms: proposal (B)
Base: origin/dev 8cb3f7d

Reproduced on a server from dev (FLUBNF_STATE_DIR, the G20/G21 run state
and two stored datasets) with curl and Chromium; the prototype served
beside it. No run path; no invariance check.

## RE-12 (also: WI-05)
- Reproduced: yes. /output/reveal answers every caller with a flash and a
  303 to the Referer; the season page's fetch follows it to
  /retro/<season>?week=…, which renders the page in the background and
  consumes the flash. Nothing shows, not even after a reload.
- Root cause: retro_season.html:407 ignores the fetch's response;
  routes/output.output_reveal has one answer shape (flash + redirect).
- Fix: a caller that sends `Accept: application/json` gets
  {ok, message, detail} (one `answer()` closure inside output_reveal;
  form posts keep the flash and redirect). The season page sends that
  header, reads the JSON and, on ok false, shows the message as the title
  of the error under the buttons with the detail as its text, through
  the page's existing `fail()` (which gains an optional title; its
  default is unchanged). Live: {"ok":false,"message":"Nothing opened: the
  file is not in app state any more.","detail":"It may have been deleted
  or moved; Storage lists what is on disk."}; a form post without the
  header still 303s to /output with the flash.
- Tests: test_retro_forms.py `test_the_reveal_answers_a_script_caller_in_json`.
- Risk: the run page's and Output's Show in folder forms (no Accept
  header) are unchanged.
- For Ely: none

## RE-13
- Reproduced: yes. After "Not started: no locations checked for the
  custom scope." the form read Season 2026-27, panel6, US national 1,
  engine pf, zero-anchor "Choose…"; the same after a run.
- Root cause: retro.html echoes nothing; every POST redirects to /retro.
- Fix: routes/retro `_remember_form(...)` keeps the posted season,
  scope, ticked states, US national, shard width, engine preset and
  zero-anchor rule on every POST /retro/run, before any refusal, in
  `retro_seasons._retro_form` and in the state folder's retro_form.json
  (read once per process, as forecast_aids restores last_form.json);
  retro_index passes it as `rform` and the template marks each control
  (selected, checked, the width's value; the custom list shown when the
  scope is custom). A first open is as before (the template guards an
  undefined rform). conftest gains an autouse fixture that empties the
  memory per test, as the suite isolates the Forecast tab's form.
  Live: after the refusal the form reads 2023-24, custom selection (the
  list open), states only, Groundhog only, blend, width 2.
- Tests: `test_the_run_form_keeps_its_choices_through_a_refusal`,
  `test_a_first_open_has_the_form_at_its_defaults`.
- Risk: one new small state file; the Model settings panel's own fields
  (particles, replicates) are the panel's and unchanged.
- For Ely: none

## RE-24
- Reproduced: yes. The replay page's only ways out were the nav tabs
  and the horizon links; /retro/dataset/nope/<stamp> was bare text.
- Fix: a "Replays of <dataset>" link to /retro?dataset=<id> first in the
  title's fact row (retro_dataset.html; `a.rt-back` in retro.css, as the
  Data tab's `a.dt-back`). The bare 404 is G22's WI-14 (a notice under
  Retrospective with the same link), already in G22's proposal.
- Tests: `test_a_replay_page_leads_back_and_says_how_far_a_stopped_one_got`.
- Risk: none.
- For Ely: none

## RE-25
- Reproduced: yes (a replay that failed at once on this sparse hub
  shows the same page as a stopped one): badge, "No scored cells", "No
  forecasts stored yet", Settings "weeks 142 (2022-01-08 to
  2024-09-21)", nothing about how far it got.
- Fix: when the replay is not running and weeks_completed < total_weeks,
  the title's facts add "<status> after N of M weeks" (clock icon) and
  the Settings row reads "N of M (first to last)"; "No forecasts stored"
  drops "yet" when nothing is running, as "No scored cells" already does.
  Live: "error after 0 of 142 weeks", "No forecasts stored".
- Tests: the same test (a done replay rewritten as stopped after 3 of
  its weeks).
- Risk: the replay page only.
- For Ely: none

## Patch
G23/proposal.patch (git diff origin/dev...proto/G23-B): routes/output.py
(the JSON answer), retro_season.html, routes/retro.py, retro_seasons.py,
retro.html, retro_dataset.html, datasets_ui.py, tabs/retro.css,
conftest.py (the autouse fixture), app/tests/test_retro_forms.py (4).
Targeted suites (test_retro_*, test_dataset_replay_knobs,
test_season_page_player, test_datasets_ui, test_download_headers,
test_ui_layout): 230 passed. Full suite (FLUBNF_HUB=/nonexistent, base 8cb3f7d): 4204 passed, 159 skipped, the two test_doctor failures of this container's Python. ruff clean. Windows:
no path or encoding change (the new file is JSON, UTF-8).
