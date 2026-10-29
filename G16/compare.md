# G16: compare (B)

A's patch applied on 55fd84e (scratch tree): its seven tests and the
report, output and season tests pass (114 passed). A server from it: the
modified run's report saves as `…-weekly-report-modified.html`, the
shipped run's as before; "Nation" works at about 1.3 s; the fresh
all-53 report's DOMContentLoaded is 4.5 to 5.7 s (two loads, both
widths), as A's proposal says.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| OU-03 | `_report_suffix(dirpath)`: the run's own files' suffix (`-modified`, none under the override), from the workroot's id or the archive's record; the date's name otherwise unchanged; two runs of one week left for Ely | the run id after the date for every run (`…-weekly-report-<run id>.html`) and `-modified` from `is_modified(spec)` | **A**, criterion 2. app.md's Decided entry (2026-10-01, Ely) fixes the saved report's name as the hub reference date's, as the CSVs are; mine changes it for every run. A's also keeps the override case right (hub names by override: no suffix), which `is_modified` alone would not. Two runs of one week stay for Ely, as A says. |
| OU-04 (FC-32, UI-21) | `_legend(colors, label, models)`; `_drawn(panels)` in MODELS order | `_legend(colors, label, drawn)` with the set of models in the panels | Equal. A's keeps MODELS' order explicitly (4). |
| OU-05 | the header link's onclick goes to `document.referrer` when it is a same-console page other than the report, else `history.back()`; inline, so a stored report carried by `legacy_theme_carry` gets it too | the same rule, set on the link by the page's own script when the link is shown | **A**, criterion 1: the carried header reaches older stored reports, which my script does not. |
| OU-06 (UI-09) | the controls' script moved before the map and the charts, one click and one change listener on the document, the US section ahead of the states'; the charts still draw at load (DOMContentLoaded 4.5 to 5.7 s here, 5.8 MB, 106 figures) | the hidden sections' figures carried as JSON and drawn by `rpDraw` when a section opens (retinted and given their week ticks); first paint 1.1 to 1.3 s, DOMContentLoaded 1.2 to 1.3 s, load 1.3 to 1.4 s; the controls work at 1.2 s | **B**, criterion 1. Both make the buttons work at about 1.3 s; UI-09 ("about 5 s to finish loading") is the same bug's variant, and only the lazy figures fix it (the page finishes in 1.4 s instead of 5 s). What a student sees when a state opens is unchanged (checked: the figures, their retint on a theme switch, the week ticks, a state opened by hash in dark, the before/after switch, printing). A's reorder of the US section is then not needed, so test_report_design_pass keeps its pin. |
| RE-26 | `download_name(season, archive)`: `…-season-report-<stamp>.html` for the route and the page's job name; the file on disk keeps its name | `report_path(root, season, archive)` adds `-archived-<stamp>` to the file itself | **A**, criterion 4: the download name only; the cached file, Reveal and reclaim are untouched. |
| FC-20 | `analogue_score_error` in step_errors; `summary_table_html(…, error=)` "could not be scored: <reason>"; the pipeline passes the member's error, else the step's | the same | Equal. |

Vote: combine.
- A's patch as the base (OU-03, OU-04, OU-05, RE-26, FC-20, A's tests).
- OU-06 from B: `_html(fig, lazy=True)` for the figures inside the hidden
  sections, `_DRAW_JS` (`window.rpDraw`), the retint pass taking one
  chart (`window.rpRetint`), `show()` drawing first; B's
  `test_a_hidden_sections_figures_wait_for_it_to_open` in place of A's
  `test_the_controls_and_the_national_section_come_before_the_charts`,
  test_report_weekly's split string, and test_report_design_pass's pin
  as on dev (the sections' order is unchanged).
