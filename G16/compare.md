# G16: compare (A)
B's proposal read in full. B's patch applied on dev 55fd84e (scratch tree,
clean), served fresh: an all-53 Groundhog run on 2026-10-17 and a vintage
one on 2026-10-03, read and clicked in Chromium.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| OU-03 | "-modified" only, from the run's own file names (`knobs.hub_names`: an override run's files keep the hub names, so its report does too); the run's time in the name left for Ely | every report download carries the run id, plus "-modified" from `is_modified` | A, criterion 2. App's Decided (2026-10-01, Ely): "The saved weekly report is named by its hub reference date, as the CSVs are: `2026-10-03-NAU_PyBNF-weekly-report.html`." B's name for every run changes that decided name, and B lists nothing for Ely. B's "-modified" also goes on a run exported under the hub names by override, whose files carry no "-modified" (criterion 1: "named like its files"). |
| OU-04 | `_legend(..., models)` from the panels drawn | the same | Equal. |
| OU-05 | onclick: the same-origin referrer, else `history.back()` | the link's href set to the same-origin referrer, else `history.back()` | Equal; both return to the opening page (checked live on B's: /runs/<id> after two jumps). |
| OU-06 (UI-09) | the controls wired by one early script, the national section moved first: the buttons work at first paint (about 1.5 s), but DOMContentLoaded stays at about 5.6 s | each hidden section's figures kept as JSON and drawn when the section opens: DOMContentLoaded 1.4 s here (dev 5.7 to 6.3 s) | B, criterion 1. UI-09 is "takes about 5 s to finish loading", and only B's fixes that. I checked B's live: every control works (Nation/States, US forecast detail, back to map, the accuracy jump, Jump to location, a state's link) with no script errors. An opened state draws the same traces as dev (real-time: 4 scatter + the category bar; vintage: 5 with "what happened (settled)"; the US fan 4 and 5). My early script and the section move are then not needed, and neither is my pin change in test_report_design_pass. |
| RE-26 | the download name only (`report_season.download_name`, used by the route and the build job); the file on disk keeps its name | `report_path(root, season, archive)`: the cached file itself is renamed "-archived-<stamp>" | A, criterion 4. Same name in the user's Downloads, but B's leaves each archived run's existing cached report behind under the old name (B's Risk says so) and rebuilds it. |
| FC-20 | `analogue_score_error` in the step list; "Groundhog could not be scored: ..." | the same | Equal. |

Vote: combine: B's patch for OU-04, OU-05, OU-06 and FC-20; A's OU-03 (`_report_suffix`, with the per-run name for Ely as in my proposal) and A's RE-26 (`download_name`), with their tests.
