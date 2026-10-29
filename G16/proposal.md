# G16 weekly-report: proposal (A)
Base: origin/dev 55fd84e (G15 merged)

How: a dev server and a prototype server, each with all-53 Groundhog runs
for 2026-10-17 (real-time) and 2026-10-03 (vintage), one Arizona run with
`knob.groundhog.own_share=0.6` (modified), the reports fetched and opened
in Chromium at 1280 px. The hub clone here has no
model-output/FluSight-baseline, which is FC-20's case. A retrospective
season cannot be replayed without the engine, so RE-26 is checked through
the route with a stand-in report file.

## OU-03 (also: none)
- Reproduced: yes. /runs/<id>/report/download and /output/report/download
  answer `filename="2026-10-24-NAU_PyBNF-weekly-report.html"` for every
  run of the week. That includes the modified run, whose files sit under
  NAU_PyBNF-GroundHogCGR-modified.
- The rule: app.md Decided (2026-10-01, Ely): "The saved weekly report is
  named by its hub reference date, as the CSVs are." So the report takes
  its files' suffix, but a per-run name would change the decided name.
- Fix: output.py `_report_suffix(dirpath)`. The run a report folder holds
  (a workroot by its id, an archive by its record) gives the suffix its
  files carry: "-modified" for modified settings without the override,
  "" otherwise (an override exports under the hub names). That run's
  report saves as "2026-10-24-NAU_PyBNF-weekly-report-modified.html", via
  `_weekly_report_name(date, suffix)`.
- Live after: the modified run's download is
  "2026-10-24-NAU_PyBNF-weekly-report-modified.html"; a shipped run's is
  unchanged.
- Tests: `test_weekly_report_files.py::test_a_modified_runs_report_saves_with_its_files_suffix`
  (shipped, modified, and modified with the override).
- For Ely: two runs of one week (not modified) still save under one name.
  Telling them apart (the run's time in the name) would change the
  decided name. The report's header does not mark a modified run either;
  the console badges it. Not changed: the bug's expected asks for the
  name only.

## OU-04 (also: FC-32, UI-21)
- Reproduced: yes. A Groundhog-only all-53 report: five keys (four grid
  pages and the US panel under the map) each list "Oracle SIHRS".
- Root cause: report_grid.py `_legend` loops over every MODELS member.
- Fix: `_legend(colors, label, models)` lists the models given;
  `grid_html` and `us_feature_html` pass the ones their panels drew
  (`_drawn`, in MODELS order).
- Live after: the five keys read Groundhog, observed, last season; a run
  with both members keeps both.
- Tests: `test_the_keys_list_only_the_models_the_panels_drew`.

## OU-05 (also: none)
- Reproduced: yes, when the report opens in the same window (the console's
  links open it in a new tab, where the back link stays hidden; the app's
  window and a same-tab open show it). After two jumps (#st-AL, #st-AK),
  "back to FluBNF" goes to /runs/<id>/report#st-AL.
- Root cause: report_v2.py `page_header`: `history.back()` undoes the last
  jump.
- Fix: the link goes to `document.referrer` when it is a page of the same
  console other than the report, else `history.back()` as before (a saved
  copy). Inline, because `legacy_theme_carry` puts the same header into
  older stored reports.
- Live after: /runs/<id>.
- Tests: `test_back_to_flubnf_goes_to_the_page_that_opened_the_report`.

## OU-06 (also: UI-09)
- Reproduced: yes. "US forecast detail" is drawn at about 1.4 s but does
  nothing until about 5.1 to 5.7 s; DOMContentLoaded at 5.7 to 6.3 s (this
  machine, three loads).
- Root cause: report_v2.py: every control's handler sits in the last
  script, after 53 states' charts. The US section (#st-US) that the
  button opens is written after the states' sections.
- Fix:
  - one early script, right after the jump bar and before the map card,
    holds `show`, `backToMap`, `openAccuracy`, the back link's reveal, and
    one click and one change listener on the document (the US button,
    Nation/States, the jump bar, the outlook toggle, Jump to location);
  - the national section moves ahead of the states' sections (each is
    hidden until opened, so only the order of hidden markup changes);
  - the last script keeps only what needs the whole page: opening a #st-
    link's state, and printing.
- Live after: "US forecast detail" opens the US section at about 1.5 s,
  as soon as it is drawn (3 loads: 1.5, 1.5, 3.2 s cold, against 5.1 to
  5.7 s on dev). DOMContentLoaded is unchanged (the charts still load
  inline). Every control behaves as on dev after load: Nation/States, US
  forecast detail, back to map, the accuracy jump, Jump to location, a
  state's link. No script errors.
- Not changed: deferring each state's charts until it opens. That would
  shorten the whole load, but it changes how the saved report draws, so
  it is a bigger change than the bug's "buttons do nothing until then".
- Tests: `test_the_controls_and_the_national_section_come_before_the_charts`.

## RE-26 (also: none)
- Reproduced: from the code. /retro/<season>/report?archive=<stamp> sends
  `p.name`, "<season>-FluBNF-season-report.html", the live run's name.
  The page's own button saves under the build job's `name`, the same.
- Fix: report_season.py `download_name(season, archive)`:
  "<season>-FluBNF-season-report-<stamp>.html" for an archived run, used
  by the route and by season_export's job (the name the page saves
  under). The file on disk keeps its name, and Reveal still finds it.
- Tests: `test_an_archived_season_report_saves_under_its_own_name`.

## FC-20 (also: none)
- Reproduced: yes. A vintage all-53 Groundhog run for 2026-10-03: the
  outcome holds `analogue_score_error` ("the hub clone has no
  model-output/FluSight-baseline ... Press Update data on the Data tab to
  fetch it, then rescore."). The run page says nothing about scoring;
  the report's accuracy reads "Groundhog: no scored weeks yet."
- Root cause: forecast.py `run_page` lists only score_error,
  archive_error, report_inputs_error and report_error; pipeline.py builds
  the accuracy line without the error.
- Fix:
  - the run page's step errors add `analogue_score_error` ("Step that
    failed", as the others);
  - `summary_table_html(..., error=)`: a member whose scoring failed
    reads "Groundhog could not be scored: <the reason>" in place of "no
    scored weeks yet". The pipeline passes the member's own error, else
    the scoring step's.
- Live after: both say it, with the Update data hint.
- Tests: `test_a_member_whose_scoring_failed_says_why`,
  `test_the_run_page_names_the_groundhogs_scoring_error`.

## Checks
- New `app/tests/test_weekly_report_files.py` (7): all fail on 55fd84e and
  pass here.
- Targeted: test_report_*, test_season_*, test_output_*,
  test_flusight_scoring, test_pf_runner_reports, test_reporting_model:
  237 passed. ruff clean.
- Changed pin: test_report_design_pass's
  `test_detail_sections_sit_before_the_grid_with_both_members` held the
  states' sections before the US section. That order is OU-06's cause for
  US forecast detail. Its point (the detail sections before the grid)
  stands; it now reads map < st-US < st-OH < the grid. No decision
  records the old order.
- Full suite (FLUBNF_HUB=/nonexistent): 3575 passed, 155 skipped, and
  that one pin failing; it passes now.
- Invariance: an all-53 Groundhog run on 2026-10-17 gives the same
  submission file on dev 55fd84e and here (md5
  56da9201b416eb5c80317c849b55168e).
- Windows: no paths or encodings; the names are ASCII.

## Patch
G16/proposal.patch (git diff origin/dev...proto/G16-A)
