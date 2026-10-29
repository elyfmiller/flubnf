# G19: compare (B)

A's patch applied on its base c423847 (it does not apply on 6546b5f:
G18's `--hero-chip-ink` lines sit where its `--model-analogue` lines go
in nau.css, a merge to redo on the fix branch). Its tests and the theme,
a11y, design, page and layout tests pass (154 passed). Servers from it
with my runs: light median #806000 and band rgba(128,96,0,.2), dark
#FFC72C; the toolbar's focus "solid 2px rgb(52,192,240)"; the settled
line ends 2025-02-08; no toolbar at 390 px; "Arizona · 3/53" over
Arizona; on the set-aside Ohio run the median starts from 2026-10-17
(82) with the week marked "set aside" (an open cross, --mut). The
audit's own delta-E under the matrices: #A87300 is 14 (deutan) and 12
(protan) from the filter's #C77100, #806000 30 and 27; both at or above
3:1 on every light ground.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| UI-03 (MO-10) | a theme token `--model-analogue` (#FFC72C dark, #806000 light), chosen against the filter's orange under the colour-blind matrices as the group note asks, read by the Forecast and model pages, the season page's palette, its server-drawn lines and legend, and the dataset replay; the a11y audit gains the Groundhog | the report's #A87300 through a template global, on the Forecast and model pages and the season page's palette | **A**, criterion 1: the note asks for the colour-blind check, which A did and which rules out the report's gold beside the filter's orange; A's reaches the season page's server-drawn lines and the dataset replay too. |
| UI-04 | the four-class rule with the app's ring | the same | Equal. |
| FC-31 (UI-22) | the Forecast tab's config leaves the toolbar off at 640 px and under, card and expanded view | charts.js `conf()`: every FluCharts chart under 600 px | **A**, criterion 2: the bug is the fan's toolbar; B's also takes the toolbar off the Data and model charts. |
| FC-14 | `missing.aside_weeks(outcome)` (set aside, trailing zero, partial week); `shared._run_aside(rid)` for both the Forecast and the model page; the fan starts on the last week used, the set-aside weeks marked "set aside" on the observed line, the official overlay anchored there | `_run_flags(rid)` on the Forecast page only; the fan starts on the last week not flagged; the flagged weeks taken off the observed line and drawn hollow "set aside (not used)"; the overlay anchored there | **A**, criterion 1 and 2: the model page's fan draws the same jump and A's fixes it with the same helper; marking the week on the observed line keeps the reported value in view as the hint asks. |
| FC-24 | the last horizon's date on both pages | the same | Equal. |
| MO-09 | a draw token in model.html | the same | Equal. |

Vote: A.
