# G16 weekly-report: proposal (B)
Base: origin/dev 78f0331

How: a fresh server from dev and one from the prototype, each with an
all-53 Groundhog run on 2026-10-17, a modified Groundhog run (Ohio,
groundhog.own_share 0.6) and a vintage Groundhog run on 2025-01-11 (its
scoring fails here: the hub clone has no FluSight-baseline), plus the
retro seasons of my G10 state (a scored 2025-26 with an archived run).
Names read with `curl -D -`; the report measured in Chromium at 1280 px
light and 390 px dark (Playwright: navigation timing, the controls
clicked right after first paint, a state opened from the grid, by hash
and by the US button, the theme switched afterwards, the print step).

## OU-03 (also: none)
- Reproduced: yes. The four downloads (the all-53 run, the modified Ohio
  run, the vintage run's by its own date, and /output's archived week)
  all answer `filename="2026-10-24-NAU_PyBNF-weekly-report.html"` (the
  vintage one `2025-01-18-…`); nothing in a name tells a modified run or
  two runs of one week apart.
- Root cause: output.py `_weekly_report_name(date)` names the file by the
  date alone; both download routes pass only the date.
- Fix: `_weekly_report_name(date, run_id="", modified=False)`:
  `<ref>-NAU_PyBNF[-modified]-weekly-report[-<run id>].html`, so a
  modified run's report carries its files' `-modified` (knobs'
  MODIFIED_SUFFIX) and the run's id follows the date (two runs of a week
  never save over each other; the id is what Storage shows). The run
  route passes its id and `is_modified(spec)` from results.json; the
  archived-week route passes the run id its archive.json records (an
  older folder without one keeps the plain name). A run id with no
  results.json keeps `FluBNF-weekly-report-<id>.html`. The submission CSV
  names are untouched.
- Live after: `2026-10-24-NAU_PyBNF-weekly-report-20261029T195651-280ace.html`,
  `2026-10-24-NAU_PyBNF-modified-weekly-report-20261029T195733-d6dd7b.html`,
  `2025-01-18-NAU_PyBNF-weekly-report-20261029T195736-d710d1.html`.
- Tests: test_weekly_report_files.py
  `test_two_runs_of_one_week_download_their_reports_under_their_own_names`,
  `test_a_modified_runs_report_is_named_like_its_files`,
  `test_an_archived_weeks_report_names_the_run_its_record_holds`; the two
  pins of the one shared name updated (test_report_bundle,
  test_output_freshness), the bug's own symptom.
- Risk: the download name only (the file on disk stays report.html).
  Invariance: pipeline.py is touched (FC-20), so the check ran: see
  Checks. For Ely: none.

## OU-04 (also: FC-32, UI-21)
- Reproduced: yes. The all-53 Groundhog run's report: every "All
  locations" page head and the US panel's key carry
  `<span class="g-key" data-s="pf" …>Oracle SIHRS</span>` (62 keys for a
  series no panel draws).
- Root cause: report_grid.py `_legend` loops over `MODELS`, whatever the
  panels hold.
- Fix: `_legend(colors, label, drawn=None)` lists the models in `drawn`;
  `grid_html` passes the union of the panels' models and
  `us_feature_html` the US panel's. A run with both members is unchanged.
- Live after: `data-s="pf"` appears only in the stylesheet's two rules;
  169 Groundhog keys, 60 last-season, 600 observed.
- Tests: `test_a_groundhog_only_reports_key_has_no_oracle_sihrs_switch`
  (and that a two-member grid keeps both).
- Risk: the key's markup for a Groundhog-only grid; grid_js is untouched
  (it switches by the keys present).

## OU-05 (also: none)
- Reproduced: yes. Home → the report → "All locations" in the jump bar →
  "← back to FluBNF": the URL goes from `…/report#all-locations` to
  `…/report`, one step back inside the report; each jump or opened state
  adds a step.
- Root cause: report_v2.py's appback is `history.back()`, shown when
  `history.length > 1`.
- Fix: when the link is shown (same rule), its href becomes
  `document.referrer` when that is a page of this origin other than the
  report itself; otherwise the onclick keeps `history.back()` (a saved
  copy opened from disk, no referrer). The download copy still strips the
  link (unchanged).
- Live after: from Home, after the jump and a state opened: href
  `http://127.0.0.1:8826/`, and the click lands on Home at both widths.
- Tests: `test_the_way_back_goes_to_the_console_page_that_opened_the_report`.
- Risk: the header link only; stored reports carried by
  legacy_theme_carry still match its `<a id="appback"…</a>` strip.

## OU-06 (also: UI-09)
- Reproduced: yes. The all-53 run's report on dev: 5.8 MB, 121 scripts,
  106 figures drawn at load inside hidden sections; first paint 1.3 s,
  DOMContentLoaded 4.1 to 5.3 s, `window.backToMap` defined at 3.8 s;
  "Nation" clicked before that stays `aria-pressed="false"`.
- Root cause: every state's fan and category bar (and the US fan) are
  `fig.to_html` blocks, each a `Plotly.newPlot` run while parsing, before
  the handlers' script at the end.
- Fix: `_html(fig, lazy=True)` for the figures inside the hidden
  `section.state` blocks: an empty `plotly-graph-div` beside a
  `<script type="application/json" class="rp-figjson" data-for=…>` with
  the figure's data, layout and its config (the save-PNG name and the
  config as `to_html` writes them; `</` escaped). `show(id)` calls
  `window.rpDraw(el)` first (`_DRAW_JS`, emitted only with figures, as
  the chart helpers are): each JSON drawn once with `Plotly.newPlot`,
  retinted (`window.rpRetint`, the retint pass now takes one chart) and
  adopted by FluCharts (week ticks), then the existing resize. A state
  opened by hash at load is drawn before the retint and FluCharts passes,
  which then cover it as they cover the rest. The map, the grid's live
  panels and the US feature are unchanged.
- Live after: same size; first paint 1.1 to 1.2 s, DOMContentLoaded 1.2
  to 1.3 s, load 1.3 to 1.4 s (both widths); `backToMap` defined at 1.2
  s; "Nation" pressed right after first paint reads true. Ohio opened from the grid: two figures with data, no
  JSON left; US detail: one; the theme switched afterwards retints the
  drawn chart (paper #FFFFFF ↔ #151729 both ways); opened by `#st-OH` in
  dark: both figures baked and retinted, watched by FluCharts as on dev;
  the print step runs. Screenshots at 1280 light and 390 dark.
- Tests: `test_a_hidden_sections_figures_wait_for_it_to_open` (the JSON,
  the draw step, and a chartless report carrying none of it);
  test_report_weekly's split string follows the pass's new argument.
- Risk: the report page only; a figure's PNG name and the retint on
  themechange are unchanged. A browser without JS never drew these
  figures either (they were inside `Plotly.newPlot` scripts).

## RE-26 (also: none)
- Reproduced: yes. `/retro/2025-26/report` and
  `/retro/2025-26/report?archive=20261029T194027Z` both answer
  `filename="2025-26-FluBNF-season-report.html"`.
- Root cause: report_season.py `report_path(root, season)` ignores the
  archive; the route and the page's download use the file's own name.
- Fix: `report_path(root, season, archive="")` adds
  `-archived-<stamp>` for an archived run; build_season_report passes
  its `archive`, so the page's download (job status `name`), the route
  and Reveal all carry it. The live season's name is unchanged.
- Live after: `2025-26-FluBNF-season-report-archived-20261029T194027Z.html`
  for the archived run, the live one as before.
- Tests: `test_an_archived_runs_season_report_carries_its_stamp` (the
  path and the route).
- Risk: an archived run's cached report is rebuilt once under the new
  name (its old file stays in the archive folder until reclaim or a
  delete); the marker check is unchanged.

## FC-20 (also: none)
- Reproduced: yes. The vintage run's outcome holds
  `analogue_score_error` ("the hub clone has no
  model-output/FluSight-baseline … Press Update data on the Data tab to
  fetch it, then rescore."); its run page has no step list and its
  report's accuracy reads "Groundhog: no scored weeks yet."
- Root cause: forecast.py's `step_errors` lists four keys, not the
  members' `<model>_score_error`; pipeline.py builds the accuracy card
  from the (empty) score frame alone.
- Fix: `analogue_score_error` joins `step_errors` (the page's existing
  "Step that failed" list, the key in `<code>` as the others);
  `scoring.summary_table_html(…, error=…)` says "<Member> could not be
  scored: <the run's words>" in place of "no scored weeks yet", and the
  pipeline passes the member's `<model>_score_error` (the Oracle's is the
  step's `score_error`).
- Live after: the run page lists "Step that failed · analogue_score_error
  the hub clone has no …"; the report's accuracy card reads "Groundhog
  could not be scored: the hub clone has no model-output/FluSight-baseline
  … then rescore."
- Tests: `test_a_members_scoring_failure_is_said_on_the_run_page_and_in_the_report`.
- Risk: pipeline.py's report inputs (the card's words only); the
  invariance check covers it.

## Checks
- Targeted: test_weekly_report_files (8), test_report_grid,
  test_report_weekly, test_report_bundle, test_report_season,
  test_output_freshness, test_output_by_date, test_output_run_pages,
  test_busy_guard, test_retro_archive, test_reclaim,
  test_download_headers, test_window_downloads, test_pages: all pass.
  ruff gate clean.
- Full suite (FLUBNF_HUB=/nonexistent), in a worktree pinned at the prototype: 3561 passed, 154 skipped; the two test_doctor failures are this container's Python 3.13, as on dev.
- Invariance: an all-53 Groundhog run on 2026-10-17 from dev (78f0331) and from the prototype give the same submission file, md5 56da9201b416eb5c80317c849b55168e.
- Windows: file names use `-`, `T` and `Z` only; the JSON escape is
  text; no path or encoding change.
- For Ely: none.

## Patch
G16/proposal.patch (git diff origin/dev...proto/G16-B)
