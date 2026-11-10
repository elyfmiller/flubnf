# G33 models-polish: proposal (B)
Base: origin/dev def45dbe (#61 merged)

How: the dev server over a state with one Groundhog-only run (all 53 locations, 2026-10-17); the prototype served over a copy of it; Chromium at 1280 px light and 390 px dark, timings from the navigation entry.

## MO-12
- Reproduced: yes. After a Groundhog-only run, /models reads "No forecasts from this model yet ?", the "?" holding "The latest real-time run (2026-10-17 · 11-10 07:29:30) has none from this model."; marks on the page: the record's "i" and that "?".
- Root cause: model.html gives `tips.empty` a caller body, and the kit's empty state turns any body into a `tip()`.
- Fix: the sentence is the empty state's muted line, inside the dashed box under the title (`tips.empty(..., action=why)` with `<span class="hint md-nofc-why">`; `.md-nofc-why{display:block;text-align:center}` in tabs/models.css). With no run the box stays as it was. The page keeps one mark, the record's "i", with or without a run.
- Tests: `test_models_polish.py::test_the_empty_forecasts_card_says_which_run_in_one_muted_line` (the line, no "?", and `marks()` == {"tt-md-rec"} with and without a run: the passing state test_fewer_marks did not cover).
- Risk: none; invariance check: no.

## MO-16
- Reproduced: yes. /model/pf2s cold at 1280 px: DOMContentLoaded 1100 ms with plotly.min.js (4.8 MB) and charts.js in its head; /models 184 ms; neither page has a chart (no Oracle fan in this state).
- Fix: model.html's head loads plotly.min.js and charts.js only `{% if has_fans %}`, both `defer`; the inline script's first `draw()` moves to DOMContentLoaded (deferred scripts run before it), the theme and text-size listeners stay. The research view never has fans, so it never loads the library.
- After: /model/pf2s DOMContentLoaded 120 ms, no scripts in the head; /models 43 ms; /model/analogue (which has the fan) loads both deferred and draws the fan, no page errors.
- Tests: `test_the_chart_library_loads_deferred_and_only_for_a_fan`.
- Risk: a page whose fan arrives without a reload cannot happen (the fans are rendered server-side into FANQ). test_data_view and test_sandbox_editor pin the Data and Sandbox pages' plain script tags, which are untouched. Invariance: no.

## HM-17 (medium confidence: reproduced)
- Reproduced: yes, in the markup of /, /models, /model/pf2s and /methods: the y-axis reads "β(t) / β0" while the band's edges read "β0·e^+ε1" and "β0·e^−ε1" and the middle line "1.0 (β0)".
- Fix: diagrams.html's `harmonic` labels the edges "e^+ε1" and "e^−ε1" and the middle line "1.0", the axis's own units (the `<desc>` already says "exp of plus epsilon-1 times the base rate", which stays true). The two-strain figure shares the macro. test_theme_and_harmonic's pin of "1.0 (β" moves to the new labels (the bug report shows the old labels are the bug).
- Tests: `test_the_forcing_figures_reference_lines_are_in_the_axis_units` (Home, Methods, both model pages).
- Risk: the public site's harvest of Methods renders the same macro (the site-build test passes). Invariance: no.

## Checks
- New `app/tests/test_models_polish.py` (3 tests), each failing on dev; test_theme_and_harmonic's pin moved. Models, harmonic, marks, pages, fans, layout, phone tables, site build, data view, download headers and month axes tests: 137 passed, 21 skipped. ruff (the gate) clean. Full suite: running; the result follows in a second commit.
- Windows: templates and CSS only.

## Patch
G33/proposal.patch (git diff origin/dev...proto/G33-B)
