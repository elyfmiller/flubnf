# G14 sandbox-mechanics: proposal (A)
Base: origin/dev 78f0331 (G13 merged)

How: the same scenarios in Chromium on two servers, one from dev and one
from the prototype (a fresh SEIR copy per run; a 33 MB CSV; two uploads
both named cases.csv; 27 stand-in runs, meta.json only, as there is no
engine to fit). SB-12 needs a live fit, which needs the engine: the test
drives it, as test_sandbox_guard already does.

## SB-02 (also: none)
- Reproduced: yes. Edit model.bngl ("# MY EDIT" first), pick the 33 MB
  file, Upload and load: the page leaves (no leave-page prompt), the
  editor reloads with "# An SEIR..." and the edit is gone from disk too.
- Root cause: sandbox.js clears `dirty` on every submit; the server reads
  none of a body over the cap (routes/sandbox.py `sandbox_upload_data`,
  `_SandboxTooLarge`), so the editor text that rode in the same body is
  never saved, and its refusal does not say so.
- Fix:
  - sandbox.js, in the submit listener that clears `dirty`: when the
    submitter is Upload and load and the chosen file is over the limit
    (`data-max-bytes` on #sbfill-csv, from `sandbox_mod.UPLOAD_MAX_BYTES`),
    the submit is cancelled and the file field says "This file is larger
    than the 20 MB limit; choose a smaller one." (setCustomValidity +
    reportValidity; cleared when another file is chosen). The page stays,
    edits and all.
  - Without the script, or a file the browser cannot size, the server's
    refusal now adds "..., the editor's text included."
- Live after: the page stays, the field shows the message, the editor
  still starts "# MY EDIT".
- Tests: `test_sandbox_forms_runs.py::test_an_upload_over_the_limit_is_refused_before_the_editor_text_goes`
  (the script's check and the server's words).

## SB-03 (also: none)
- Reproduced: yes, both cases.
  - Vintage of 2026-10-10, New York, the default range: "19 weeks of New
    York, 2026-06-06 to 2026-10-17"; data.exp holds "2026-06-06 to
    2026-10-17 ... 19 weeks, 1 dropped missing".
  - Settled truth, Arizona, 2026-09-05 to 2026-12-31: "7 weeks ...
    2026-09-05 to 2026-12-31", "7 weeks, 10 dropped missing".
- Root cause: core/sandbox_data.py `_window` counts every Saturday to the
  range's end as missing; the flash (`_sandbox_fill_flash`) and the
  "data.exp holds" row print the range asked for, not the weeks loaded.
- Fix:
  - `_window(got, start, end, newest)`: missing weeks are counted only up
    to the source's newest week: a vintage's date (each vintage's newest
    week is its date; checked on the shipped ones), settled truth's newest
    week over all locations, a dataset's newest group week. A location
    short of that week still counts it missing.
  - The flash and the "data.exp holds" row show the first and last week
    loaded (`dates`, already in the sidecar; an older sidecar without
    them falls back to the range).
- Live after: "19 weeks of New York, 2026-06-06 to 2026-10-10", holds
  "19 weeks"; Arizona "7 weeks ... 2026-09-05 to 2026-10-17", "7 weeks".
- Tests: `test_load_data_counts_no_week_past_the_sources_newest_as_missing`
  (vintage, settled with a location short of the newest week, a real
  gap), `test_load_data_names_the_weeks_it_loaded_not_the_range_asked_for`.

## SB-06 (also: none)
- Reproduced: yes. Two uploads of cases.csv: Source lists "cases",
  "cases".
- Root cause: sandbox_data.html prints `d.name`; datasets keep the file
  stem as their name.
- Fix: `dataset_choices` adds a `label`: the name, with "(first to last)"
  weeks only when another dataset has the same name. The Source option
  shows the label. Stored names do not change.
- Live after: "cases (2025-01-04 to 2025-01-25)", "cases (2024-01-06 to
  2024-01-20)".
- Tests: `test_two_datasets_of_one_name_are_told_apart_by_their_weeks`.

## SB-08 (also: none)
- Reproduced: yes, with 27 stand-in runs: the badge "25 runs", Delete
  model's confirmation "... and its 25 runs", Compare with 25 choices; the
  two oldest runs are not listed.
- Root cause: routes/sandbox.py `sandbox_page`: `runs = [...][:25]`, and
  the badge, the confirmation and both lists count that list.
- Fix: the cap goes. A model lists all of its runs (they are a model's
  own fits, made one at a time, so a long list is rare).
- Live after: "27 runs", "... and its 27 runs", 27 to compare with.
- Tests: `test_a_model_with_27_runs_counts_and_lists_all_27`.

## SB-09 (also: none)
- Reproduced: yes. A second Oracle start for Arizona 2026-10-17 suggests
  oracle_arizona_2026-10-17 again; Create refuses ("already exists") and
  the form is back to SIR example / sir_example_1, US, season blank.
- Root cause: sandbox.js `suggestName` builds the Oracle name without the
  taken names; `sandbox_new` redirects to a plain /sandbox on refusal.
- Fix:
  - the form carries `data-taken` (the models' names), and an Oracle or
    dataset suggestion that is taken gets _2, _3, ...
  - a refusal (not a copy's) keeps the posted form as a one-shot
    (`_sandbox_new_refused`, like `_sandbox_upload_report`); the page
    restores the name (marked `data-kept`, so the script does not replace
    it), the start, location, date, group, as-of and season start. The
    sandbox_root test fixture clears it, as it clears the flash.
- Live after: suggested oracle_arizona_2026-10-17_2; a forced taken name
  is refused and the form comes back as Oracle SIHRS / Arizona /
  2026-10-17 / 2026-08-08 with the posted name.
- Tests: `test_the_new_model_form_suggests_names_no_model_has`,
  `test_a_refused_new_model_comes_back_as_it_was_posted`.

## SB-11 (medium; also: none)
- Reproduced: yes. Oracle start, Ohio, 2026-10-17, season start
  2025-08-01: created without a word (the bug's data.exp: 64 weeks from
  2025-08-02).
- Root cause: core/sandbox.py `from_shipped` checks only that the season
  start is before the forecast date.
- Fix: refuse a season start more than 364 days before the forecast date:
  "Not created: the season start 2025-08-01 is more than a year before
  the forecast date 2026-10-17; the model fits one season". August 1 of
  the forecast's season (production's default) is always within it.
- Tests: `test_an_oracle_start_refuses_a_season_start_over_a_year_back`.

## SB-12 (medium; also: none)
- Reproduced: from the code and the guard's test (a live fit needs the
  engine): with a fit live, a Groundhog-only POST /run gets "Not started:
  a sandbox fit holds the engine (...)"; with a console run going,
  the Sandbox's reason is "a console run is fitting".
- The rule: one run at a time is recorded design (the engine lock holds
  while any console run, replay or sandbox fit runs). Letting a Groundhog
  run overlap a fit would change it, so that is not done here.
- Fix: the words only. The middleware's refusal reads "Not started: a
  sandbox fit is running (<id>); one run at a time." (detail unchanged);
  the busy reason reads "a console run is in progress".
- Tests: `test_the_one_run_refusals_claim_no_engine_a_groundhog_run_does_not_use`;
  test_sandbox_guard's pin of the old words.
- For Ely: none. (Letting a Groundhog-only run go beside a fit would change
  the recorded lock; this fix does not.)

## SB-17 (also: none)
- Reproduced: yes. Choosing "Copy of" a model blanks the Name field.
- Root cause: the copy options carry no `data-name`.
- Fix: `copy_names` (routes/sandbox.py, `_free_name(m + "_copy", taken)`)
  gives each copy option a data-name, like the examples.
- Live after: "g14_fixchri_copy_1".
- Tests: in `test_the_new_model_form_suggests_names_no_model_has`.

## Checks
- New `app/tests/test_sandbox_forms_runs.py` (9): all fail on dev and pass
  here. test_sandbox_guard's pin updated (SB-12's words). All sandbox
  tests pass (225 passed, 4 skipped). ruff clean. The New model one-shot
  is cleared in conftest.sandbox_root, beside the flash.
- Full suite (FLUBNF_HUB=/nonexistent, as CI): 3563 passed, 155 skipped, 0 failed.
- Invariance: not needed (Sandbox only; no run path changed).
- Windows: the size check is in the browser; no new paths or files.

## Patch
G14/proposal.patch (git diff origin/dev...proto/G14-A)
