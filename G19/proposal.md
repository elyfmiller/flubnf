# G19 charts: proposal (A)
Base: origin/dev c423847 (G17 merged)

How: a dev server and a prototype server, each with a vintage Groundhog
run (Arizona and US, 2025-01-11) and an all-53 run on 2026-10-17. The
fans read in Chromium (their Plotly traces), at 1280 px in five themes
and 390 px Dark. The toolbar's focus read after a Tab in Dark. The
model page's pager with its first /api/series request held 1.5 s. FC-14
with Arizona's newest week recorded as set aside in each server's newest
run (the outcome's data_flags, as a run with that Data issues choice
records it).

## UI-03 (also: MO-10)
- Reproduced: yes. Light: the Forecast fan's median #FFC72C and its band
  rgba(255,199,44,.2) on #FFFFFF (1.56:1); the model page the same.
- Root cause: memberColor (forecast.html, model.html), the season page's
  palette and cumulative lines, and a dataset replay's chart all take
  player.js's yellow on every theme.
- Fix:
  - a theme token `--model-analogue` beside each theme's `--scheme`
    (nau.css): #FFC72C on the four dark themes, and on the four light
    ones a darker gold, #806000;
  - memberColor (Forecast, model page), the season page's palette and its
    server-drawn lines and legend (`member_colors` overridden in
    retro_season.html), and retro_dataset.html read it.
- Why #806000 and not the report's #A87300 (the group note: checked with
  the color-blind mode). The season page's player draws the Liu-West
  filter (pf_filter, #C77100) beside the Groundhog. #A87300 is 29 from it
  under the deutan/protan simulation and 31 in normal vision; the member
  audit's bar is 60. #806000 is 73+ from every member under both
  matrices and normally, and 5.05:1 or more on every light ground (bg
  and card).
- Live after: the median #806000 in Light, Paper, GitHub and Solarized;
  #FFC72C in Dark.
- Tests: `test_chart_fixes.py::test_the_groundhog_is_drawn_per_theme_on_every_console_chart`;
  test_a11y_modes' member audit gains the Groundhog as each theme draws it
  (3:1 on its grounds, 60+ from pf, pf_filter and pf2s under both
  matrices and normally).
- For Ely: the weekly report keeps #A87300 on light cards
  (report_v2.ANALOGUE_ON_LIGHT), as close to the filter's orange as
  above, where the report draws both. Not changed here: the report is
  out of this group's pages, and its colours are its own.

## UI-04 (also: none)
- Reproduced: yes. Dark: a toolbar button's focus is "solid 1px
  rgb(0,0,0)" on the #151729 card.
- Root cause: Plotly injects `.js-plotly-plot .plotly
  .modebar-btn:focus-visible{outline:1px solid #000}` after nau.css.
- Fix: nau.css `.js-plotly-plot .plotly .modebar .modebar-btn:focus-visible`
  (one class more, so it wins wherever Plotly's rule lands) with the
  app's ring: `var(--focus-w,2px) solid var(--gold)`.
- Live after: "solid 2px rgb(52,192,240)".
- Tests: `test_the_chart_toolbar_wears_the_focus_ring_and_stays_off_on_a_phone`.

## FC-31 (also: UI-22)
- Reproduced: yes. 390 px: the fan's toolbar is drawn over the
  location's title, in the card and in the expanded view.
- Fix: the Forecast tab's chart config leaves the toolbar off at 640 px
  and under (`displayModeBar`), the card and the expanded view alike.
  Plotly's toolbar is hover-shown on a desktop as before.
- Live after: 390 px: no toolbar; 1280 px: as before.
- Tests: the same test.

## FC-14 (also: none)
- Reproduced: with the set-aside recorded in the run (Arizona,
  2026-10-17), dev's fan starts at the set-aside value (2026-10-17, 55);
  the week is not marked.
- Root cause: forecast.html and model.html anchor the band and median on
  `obsY.slice(-1)`, the last observed week, whatever the member did with
  it.
- Fix: `missing.aside_weeks(outcome)` gives each member's weeks treated
  as unreported (unreported_flags: set aside, trailing zero, partial
  week). `shared._run_aside(rid)` reads it from the run's ledger row for
  both pages. The fan starts from the last week the member used, and the
  set-aside weeks are marked ("set aside", an open cross in --mut). The
  official overlay starts there too.
- Live after: both pages: the fan starts at 2026-10-10 (67); 2026-10-17
  marked "set aside".
- Tests: `test_the_weeks_a_member_set_aside_come_from_the_runs_flags`,
  `test_a_fan_starts_before_its_set_aside_weeks_and_ends_at_its_horizon`,
  `test_the_forecast_and_model_pages_receive_the_set_aside_weeks`.

## FC-24 (also: none)
- Reproduced: yes. Vintage 2025-01-11: the settled outcome runs to
  2025-02-15, a week past the fan's last point (2025-02-08).
- Fix: the frame is the last horizon's date (base + 7 × the largest
  horizon), on the Forecast tab and the model page (the same code).
- Live after: to 2025-02-08.
- Tests: in the FC-14 test.

## MO-09 (also: none)
- Reproduced: yes. /model/analogue, the first series request held 1.5 s,
  ▶ twice: the readout "Arizona · 3/53" over Alaska's chart.
- Fix: model.html `draw()` takes a token, as the Forecast tab's drawFan
  does; after the fetch a superseded draw returns.
- Live after: "Arizona · 3/53" over Arizona.
- Tests: `test_the_model_pager_draws_only_the_location_it_names`.

## Checks
- New `app/tests/test_chart_fixes.py` (6): all fail on c423847 and pass
  here; test_a11y_modes' member audit extended.
- Targeted: test_forecast*, test_model*, test_display_themes,
  test_a11y_modes, test_season*, test_missing*, test_data_issues,
  test_pages, test_fewer_marks, test_ui_layout: all pass. ruff clean.
- Full suite (FLUBNF_HUB=/nonexistent): 3591 passed, 155 skipped, 0 failed.
- Invariance: not needed (charts and their pages; `missing` gains a read
  helper only).
- Windows: CSS and page scripts.

## Patch
G19/proposal.patch (git diff origin/dev...proto/G19-A)
