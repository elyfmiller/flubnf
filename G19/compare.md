# G19: compare (A)
B's proposal read in full; B's patch read (forecast.py, the templates,
charts.js, the tests).

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| UI-03 (MO-10) | a theme token `--model-analogue` (#FFC72C dark, #806000 light), read by the Forecast and model fans, the season page's player palette, its server-drawn cumulative lines and legend, and a dataset replay's chart; the member audit checks it against every member under both CVD matrices | the report's #A87300 when `--scheme` is light (a template global), on the Forecast and model fans and the season player's palette | A, criterion 1 and the group's note ("checked with the color-blind mode"). The season page's player draws the Liu-West filter (#C77100) beside the Groundhog, and #A87300 is 29 from it under the deutan and protan simulations (31 in normal vision) against the audit's bar of 60. A's #806000 is 73 or more from every member, and 5.05:1 or more on every light ground. B's leaves the season page's server-drawn cumulative lines and legend (`member_colors` in retro_season.html) and the dataset replay's chart in #FFC72C on light cards. |
| UI-04 | the four-class rule with the app's ring | the same | Equal. |
| FC-31 (UI-22) | the Forecast tab's chart config: no toolbar at 640 px and under (the card and the expanded view) | charts.js `conf()`: no toolbar under 600 px on every FluCharts chart | A, criterion 2: the hunt found the toolbar over a title on the Forecast fan and its expanded view; B's also removes it from the Models and Data charts on a phone, which nothing reported. |
| FC-24 | base + 7 × the largest horizon, Forecast and model fans | the same | Equal. |
| MO-09 | a draw token in model.html | the same | Equal. |
| FC-14 | `missing.aside_weeks` (the run's `unreported_flags`: set aside, a trailing zero, a partial week; no zero-anchor or left-out rows), read by `shared._run_aside` for the Forecast fan and the model page's fan; the fan starts on the last week the member used, the weeks marked "set aside" | the run's raw data_flags; every row for the location counts as set aside; the Forecast fan only | A, criteria 1 and 2. A zero-anchored state's row (rule "zero anchor: …") names a forecast made with that rule, not a week set aside (missing.unreported_flags drops those rows for that reason), so B's fan would start a week early for such a state. The model page's fan has the same anchor code and the same symptom; A fixes both. B's reproduction is the stronger one (a real set-aside through the Data issues box on a hub copy); A's shows the same fix on a recorded flag. |

Vote: A.
