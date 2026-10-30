# G19: review (B)
PR #74, head 839520a.

Approve.

- 839520a puts ROBS's vintage note back on ROBS; RASIDE keeps its own
  line (forecast.html, 2 lines; nothing else changed since bc0e4d9).
  Targeted tests on the head: test_chart_fixes, test_pages,
  test_forecast_aids, test_ui_layout, test_a11y_modes: 86 passed.
- Everything below was checked on bc0e4d9, whose code the head carries:
  - The diff is the decision (A): `--model-analogue` in every theme block
    beside `--scheme`, read by the Forecast and model fans, the season
    page's palette and server lines, the dataset replay; the toolbar's
    ring; the Forecast toolbar off at 640 px and under; `aside_weeks` /
    `_run_aside` and the fans from the member's anchor with the "set
    aside" mark on both pages; FC-24 on both; the model page's draw
    token. The Status cell names #74 and UI-03 for Ely. Every commit is
    Ely's (the merge too); the PR body has no footer.
  - Tests: test_chart_fixes, test_a11y_modes, test_display_themes,
    test_pages, test_design_batch3, test_season_page_player,
    test_forecast_aids, test_ui_layout, test_missing_data,
    test_models_tab: 162 passed. ruff clean.
  - Live, Chromium, on servers from the branch (the G16 run state; and a
    copy of the hub with Ohio's newest week set to 2 and a Groundhog run
    that set it aside):
    - UI-03: light fan median #806000, band rgba(128,96,0,.2); dark
      #FFC72C, rgba(255,199,44,.2).
    - UI-04: a focused toolbar button in Dark: outline solid 2px
      rgb(52,192,240).
    - FC-31: at 390 px no toolbar, the title shown.
    - FC-24: the settled line ends 2025-02-08, with the median.
    - MO-09: the first fetch held 1.5 s: "Arizona · 3/53" over Arizona's
      chart.
    - FC-14: Ohio on /forecast and /model/analogue: the fan (band,
      median, the official overlay) starts 2026-10-17; one "set aside"
      x-open marker at 2026-10-24.
