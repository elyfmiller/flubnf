# G33 models-polish: proposal (A)
Base: origin/dev def45db (the engine switch #61 merged)

How: a server from the prototype (8817) and one from dev (8815), both on a state with four Groundhog-only vintage runs of all 53 locations. Chromium at 1280 px, timing from the navigation entry; the forcing figure screenshotted on Home.

## MO-12 (an empty Forecasts card grows a "?" after a run without this model)
- Reproduced: in the template and test_models_tab. After a Groundhog-only run, /models reads "No forecasts from this model yet ?". The "?" holds one sentence: "The latest real-time run (...) has none from this model."
- Root cause: model.html passes that sentence to `tips.empty` as its caller body, and the kit makes a body a tip.
- Fix: the empty state has no body. The sentence follows it as plain muted text (`<p class="hint md-nofc-why">`).
- After: "No forecasts from this model yet", then "The latest real-time run (2026-10-17 · 11-10 07:44:42) has none from this model." under it, with no mark.
- Tests: `test_models_polish.py::test_a_run_without_this_model_says_so_without_a_mark` (the passing state the hunt said test_fewer_marks misses).

## MO-16 (plotly loads render-blocking on every model page)
- Reproduced: yes. All three model pages load plotly.min.js (4.8 MB) and charts.js in `<head>`, blocking, though /model/pf2s and a run without this model draw no chart.
- Fix:
  - model.html loads the two scripts only when `has_fans`, deferred.
  - The fan's first draw waits for DOMContentLoaded while the page is still loading, so the deferred scripts have run. The theme and text-size redraws come later anyway.
  - test_week_ticks' pin of the blocking pair accepts the deferred pair. The blocking load is the bug.
- After: /model/pf2s and /models (no fans) load no chart script (DOMContentLoaded 57 ms and 159 ms). /model/analogue still draws its fan ("Alabama · 1/53"), with no page error.
- Tests: `test_the_chart_library_loads_only_for_a_fan_and_deferred`.

## HM-17 (the forcing figure mixes units; medium confidence: reproduced)
- Reproduced: yes. On the β(t) / β₀ axis the dashed lines read "β₀·e^+ε₁" and "β₀·e^−ε₁", and the middle "1.0 (β₀)".
- Fix (diagrams.html `harmonic`, shared by Home, Methods and the model pages): the lines read e^+ε₁ and e^−ε₁, and the middle line 1.0. The axis stays β(t) / β₀. The figure's description already says "between exp of minus epsilon-1 and exp of plus epsilon-1".
- After: screenshot of Home's figure: e^+ε₁ at the top, 1.0 on the dotted middle line, e^−ε₁ at the bottom.
- Tests: `test_the_forcing_figures_lines_read_in_the_axis_units`.

## Checks
- New `app/tests/test_models_polish.py` (3), each failing on dev. Models tab, week ticks, marks and pages tests: 73 passed. ruff (the gate) clean.
- Output check: not needed (templates only).
- Windows: templates only.

## Patch
G33/proposal.patch (git diff origin/dev...proto/G33-A)
