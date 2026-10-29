# G19 charts: proposal (B)
Base: origin/dev c10d257

How: a dev server and a prototype server with the same state (an all-53
Groundhog run, a vintage Ohio run on 2025-01-11 as the newest), and a
second pair with a private hub copy whose newest Ohio week was edited to
2 (FC-14: the Data issues box offered "set aside", the run took it).
Chromium at 1280 px light and dark, and 390 px with touch; the Plotly
traces read from the page; the Models pager with the first series
request delayed 1.5 s.

## UI-03 (also: MO-10)
- Reproduced: yes. Light theme: the Forecast fan's median #FFC72C and
  band rgba(255,199,44,.2) on paper #FFFFFF (1.56:1); the same on
  /model/analogue; the report draws the same model in #A87300.
- Root cause: the pages' `memberColor` reads the shared map whatever the
  scheme; the report alone has the light-ground variant.
- Fix: a template global `analogue_on_light()` (report_v2's
  ANALOGUE_ON_LIGHT); forecast.html and model.html return it for the
  Groundhog when `--scheme` is light; the season page's player palette
  takes it the same way. Dark themes keep #FFC72C.
- Live after: light: median #A87300, band rgba(168,115,0,.2) on
  /forecast and /model/analogue; dark unchanged.
- Tests: test_chart_fixes.py
  `test_the_groundhog_wears_the_reports_darker_gold_on_a_light_card`;
  test_display_themes' member check adds the Groundhog at 3:1 on every
  light and dark ground (its colour by scheme).
- Risk: the three pages' chart colours on light themes only.

## UI-04 (also: none)
- Reproduced: yes. Dark: a focused toolbar button's outline is
  `rgb(0,0,0) solid 1px` (plotly.js's injected rule, three classes deep).
- Fix: nau.css `.js-plotly-plot .plotly .modebar .modebar-btn:focus-visible`
  (four classes, so it wins) with the app's ring.
- Live after: `solid 2px rgb(52,192,240)`.
- Tests: `test_a_chart_toolbars_buttons_wear_the_apps_focus_ring`.

## FC-31 (also: UI-22)
- Reproduced: yes. 390 px: the toolbar's box [119,224,240x36] overlaps
  the title's [179,225,33x20]; the same in the expanded view.
- Fix: charts.js `conf()` sets `displayModeBar:false` when the screen is
  under 600 px wide (`matchMedia`), after the caller's own config; every
  chart drawn through FluCharts follows (the fan, its expanded view, the
  Models and Data charts). A phone zooms and pans by touch.
- Live after: no toolbar at 390 px; the title clear.
- Tests: `test_the_toolbar_stays_off_a_narrow_screen`.
- Risk: the save-PNG button is gone on a phone; desktop widths keep it.

## FC-24 (also: none)
- Reproduced: yes. The vintage run's settled line runs to 2025-02-15,
  one week past the last horizon 2025-02-08 (`+35` days).
- Fix: the limit is the last horizon's date (base + 7 × the largest
  horizon), on the Forecast fan and, the same line, on the Models fan.
- Live after: the settled line ends 2025-02-08, with the median.
- Tests: `test_the_settled_line_stops_at_the_last_horizon`.

## MO-09 (also: none)
- Reproduced: yes. Two ▶ clicks 100 ms apart with the first series fetch
  delayed: "Arizona · 3/53" over Alaska's chart.
- Fix: model.html `draw()` takes a token before its await and returns
  after it when a newer draw started (the Forecast fan's own `fanSeq`
  idiom).
- Live after: "Arizona · 3/53" over Arizona's chart.
- Tests: `test_the_forecasts_pager_draws_only_the_page_last_asked_for`.

## FC-14 (also: none)
- Reproduced: yes. Ohio's newest week set aside: the observed line drops
  to 2 at 2026-10-24 and the median and band start from 2, jumping to
  111 the next week.
- Root cause: the fan is anchored on the last observed point, whatever
  the run did with it; the run's `data_flags` (the set-aside and
  unreported-tail weeks per member) never reach the page.
- Fix: forecast.py passes the run's data_flags (`_run_flags`, from its
  ledger row) as `RFLAGS`; the fan starts on the last week the model
  used (the newest week not flagged), the flagged weeks are drawn apart
  as hollow markers "set aside (not used)", and the official overlays
  anchor on the same point. A run without rules records no flags and
  draws as before.
- Live after: the observed line ends 2026-10-17 = 82, the median starts
  there (82, then 111 at 10-31), the set-aside week a hollow marker at
  2026-10-24 = 2 (screenshot).
- Tests: `test_the_forecast_page_carries_the_weeks_the_run_set_aside`
  (the route, the flags on the page, the fan's code, and no flags for a
  run without rules).
- Risk: the Forecast fan only; the Models page's fan (the same anchor on
  the last observed point) is not in the hunt and is left as is.

## Checks
- Targeted: test_chart_fixes (6), test_display_themes, test_pages,
  test_ui_layout (the golden lists the new template global),
  test_models_tab, test_forecast_aids, test_ui_kit, test_week_ticks: all
  pass. ruff gate clean.
- Full suite (FLUBNF_HUB=/nonexistent), in a worktree pinned at the prototype: 3589 passed, 154 skipped; the two test_doctor failures are this container's Python 3.13, as on dev; the third, test_design_batch3's "no private literals" on a template comment that named the shared yellow by its hex, is fixed in the patch (the comment reworded).
- Invariance: not needed (templates, two static files, the page's
  context; `routes/forecast.py`'s change is the GET page, not /run).
- Windows: markup, CSS and JS only.
- For Ely: none.

## Patch
G19/proposal.patch (git diff origin/dev...proto/G19-B)
