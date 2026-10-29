# G16: review (A)
PR #70, head 490cf08.

Approve.

- The diff is the decision. Eight files (report_grid, report_season,
  scoring, pipeline, forecast, output, retro, season_export) are byte for
  byte my prototype's. report_v2.py holds B's lazy figures (`_html(...,
  lazy=True)`, `_DRAW_JS`, `rpRetint` taking one chart, show() drawing
  first) and my header link. test_weekly_report_files.py is mine with
  B's `test_a_hidden_sections_figures_wait_for_it_to_open` in place of my
  OU-06 test. test_report_weekly's split string follows. The Status cell
  names #70 and OU-03's per-run name for Ely.
- Commits as Ely, no trailers; the PR body has no footer.
- Tests on the head: test_weekly_report_files, test_report_*,
  test_season_*, test_output_*, test_flusight_scoring, test_setup_badge:
  232 passed. ruff clean.
- Live on a fresh server from the head (an all-53 run on 2026-10-17, a
  modified Arizona run with groundhog.own_share 0.6, a vintage all-53 run
  on 2026-10-03; Chromium at 1280):
  - OU-03: "2026-10-24-NAU_PyBNF-weekly-report.html" and
    "2026-10-24-NAU_PyBNF-weekly-report-modified.html".
  - OU-04: no key carries data-s="pf" (the two matches are the
    stylesheet's rules).
  - OU-05: after two jumps, "back to FluBNF" lands on /runs/<id>.
  - OU-06: US forecast detail opens at 1.4 s, DOMContentLoaded 1.4 s;
    every control works after load (Nation/States, US detail, back to
    map, the accuracy jump, Jump to location, a state's link), no script
    errors. Arizona opened on the vintage run draws the same five traces
    and the category bar as dev's; the US fan five.
  - FC-20: the run page's "Step that failed · analogue_score_error"; the
    report's "Groundhog could not be scored: the hub clone has no
    model-output/FluSight-baseline ...".
