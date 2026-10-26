# G02: review (A)
PR #51, head 8f92fbc (a19a67e the change, 8f92fbc the Status cell).

Approve.

What I checked
- The diff is the decision: FC-06 as A's (str fields into the knob parser in /run, /run/dataset, /retro/run); FC-08 B's `_location_list` (name or two-letter code, any case, once; LookupError) with A's refusal words; MO-07 A's `replicates_knob` through forms' lazy `_knobs`; MO-22 B's `_from_forecast_tab` with A's words; tests in the existing files plus the dataset and replay refusals; `test_oracle_step` repointed with its comment and said in the PR. Author Ely F. Miller on both commits, no attribution lines, no forbidden words; title and body in the repo's form, no footer.
- On the head: the run, data-source, dataset, US-choice, knobs, models, oracle-step, research, rerun, audit, forecast, run, retro, layout, marks, custom-run and busy-guard test files: 774 passed, 10 skipped (Python 3.12). `ruff check --select F821,F823,F811,F401 app/ui` clean.
- Live, a server from the head, Chromium 1280x900: Particles 1e4 with Model = Both lands back on /forecast with the panel open on "Particles: '1e4' is not a valid int." and 1e4 kept; /models and /model/pf2s take 10 (min 1, max 10, valid); "arizonna, Ohio" on /model/analogue: "Not run: unknown location: arizonna."; a Wednesday with "arizona, Ohio": the run on Arizona and Ohio for 2026-10-17 and "Anchor week 2026-10-17: the newest week on or before 2026-10-21."; "oh, DC, Ohio" runs Ohio and District of Columbia, once. Phone 390x844 dark: "Not run: unknown locations: Oiho, Arizonna." for "Oiho, Arizonna, UT", clean.

One note, optional, no change asked: `_location_list` signals unknown names with LookupError and `/run` reads them back from `str(e)`. KeyError is a LookupError, so a KeyError from pandas inside `_location_list` (a malformed locations table) would read as "unknown location: 'col'" rather than the "could not read the state list" refusal. load_locations falls back to the vendored copy, so I see no real path to it; fine as is.
