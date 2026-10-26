# G02: decision (by B)
Decision: combined.
- FC-06 from A: the three number fields become `str = Form(...)` in `/run`, `/run/dataset` and `/retro/run` and go raw into the knob parser (no new helper; a value the engine does not use stays ignored and kept on the form).
- FC-08: B's `_location_list` (the hub's name by name or two-letter code in any case, once; unknown names raise `LookupError`) with A's shorter refusal: `Not run: unknown location: Oiho.` / `Not run: unknown locations: X, Y.` (at most five named); B's `test_oracle_step` repoint, said in the PR.
- MO-07 from A: `replicates_knob` through forms' lazy `_knobs`; B's test (in `test_models_tab`).
- MO-22: B's mechanism (`_from_forecast_tab`, the typed-Saturday case) with A's words: `Anchor week 2026-10-17: the newest week on or before 2026-10-21.`
- Tests in the existing files, where B put them (`test_knobs_wiring`, `test_forecast_us_choice`, `test_models_tab`, `test_data_source`), plus A's dataset and replay refusal tests moved beside them.
Implementer: B
Why: both votes were combine and agree on FC-06 (A's: one parser, no copy of its int rule, the sibling handlers), on the `test_oracle_step` repoint (A's patch fails it) and on test placement. Where they differed: FC-08's codes are inside what the bug allows ("a case-insensitive match") and spare a refusal, so B's match; A's message adds fewer words to the page (5). MO-07 is equal (A's code is the smaller import). MO-22's words are the Forecast tab's own term (5); B's helper and tests cover the typed-Saturday case (3).
Left for Ely: none. (A's note: `/retro/run`'s `width` has the same `int = Form`; that form is G23.)
Not reproduced: none
