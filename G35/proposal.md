# G35 cross-page: proposal (A)
Base: origin/dev 2dbf6a80 (#94 merged) plus G33 (fix/G33-models-polish 853aedf1, decided A, PR to come). The patch is `git diff` from dev-plus-G33 to proto/G35-A2; it applies to dev once G33 merges. G34 (B's) is not in it: the only file both touch is methods.html (here, the replay "i"'s two lines).

How: dev (8817) and the prototype (8815) on a state with four all-53 Groundhog dates, the 2025-26 season replayed Groundhog-only on 6 states, and the G31 Sandbox models (sir_demo, kin, sites). The public engine is not installed (the default), as on a student laptop. Marks are counted from the served HTML and in Chromium (visible "?" and "i" buttons in main); "i" panels measured by their text length.

## UI-12 (storage blocked: the page ignores the OS theme; High contrast reads Off while on)
- Reproduced: yes, on dev 2dbf6a80 with localStorage and sessionStorage throwing SecurityError, OS dark: data-theme null (a light page), High contrast sets data-contrast="high" but aria-checked stays "false", four page errors on each of / and /forecast.
- Root cause: base.html's first-paint script reads localStorage without a guard, so the throw stops it before the OS preference is applied; the switch scripts write storage before they set aria-checked, so the throw leaves the switch's state unsaid.
- Fix (base.html): every storage read and write in the shell is wrapped in try; the first paint reads all four settings in one guarded block, then applies the OS theme when none is stored; the switches set their state first and save it after, in a try. The sessionStorage scroll memory is guarded the same way.
- After: theme "dark", the switch reads "true", no page errors on all nine tabs.
- Tests (test_cross_page.py): test_with_storage_blocked_a_page_follows_the_os_and_its_switches_work (node, the real script with a throwing storage); test_every_storage_call_in_the_shell_is_guarded. test_a11y_modes and test_display_themes pinned the unguarded lines; their pins move.

## UI-13 (more marks than one "i" a page) (also HM-19)
- Reproduced: yes, on dev plus G32 and G33 (marks as served, folds closed):
  - Home: 3 "i" (the map, the record, How it works) and, with no engine, 3 "?" in Setup: "1 not installed ?" (whose tip only names "Particle-filter engine", the row under it), the row's "?", and the engine build alert's "?" ("The public engine's build could not be read: there is no Python at ...", whose fix repeats the Setup line above it).
  - Retrospective: the title's mark is a "?" where Output's and a season page's are an "i"; 3 "?" (title, the no-engine alert, Import a replay).
  - Sandbox list: 3 "i" (the chosen start, and one per model with a first comment).
  - Sandbox model page: 2 "i" (the files, Run settings) and the no-engine "?".
  - Storage: the On disk card's per-heading "?" are gone since G29 (2 "?" left, Reclaim and Sandbox). Data, Output, Models, Methods, the season page and a run page hold one "i" or none; Forecast two.
- Root cause: each card kept its own explainer; test_fewer_marks held Home's three "i" and counted the no-engine marks as a passing state, though that is the normal state on a student's laptop.
- Fix:
  - Home (home.html): the map keeps the page's one "i". The record's "i" goes: one line under its table says its unit and links Methods for each column's cells ("relWIS vs the FluSight baseline, ratio of sums; below 1 beats it. Each column on its own cells: Methods."); Methods already holds every figure the "i" held (its record table with the plain filter and cells, the Cells fold with the Groundhog's cells, rule and the 0.660 it replaced, the withdrawn placement). How it works' "i" goes: its first two lines repeated the hero and the drawing (whose description is the full sentence), and each equation is named by its chip; the model pages read them. Setup: the badge counts and the list names, so the badge has no "?" (its recount script too); the engine build line is not shown when it is the public engine's unreadable build while the engine is missing, since the Setup lines already say so and how to add it. Any other build warning (another build, a checkout git cannot read) still shows.
  - Retrospective (retro.html): the title's mark is an "i" (rich toggletip, as Output and the season page), three lines: what a replay is and relWIS, Resume, and Import a replay; the Import card's heading has no "?". The page then shows one "i" and the no-engine "?"; the Model settings panel's own "i" shows only when that panel is opened, as on Forecast.
  - Sandbox list (sandbox.html): the rows carry no note "i" (a model's first comment opens its model.bngl); the list keeps the one beside Start from.
  - Sandbox model page: the Run settings "i" goes; what Jitter and Seed do joins How it works' Save and run step on the workbench only (sandbox_help.html, how_run), in the same words. The files' "i" stays the page's one.
- After: every page as served holds at most one "i" (Forecast two). Home with no engine: one "i" and one "?" (was 3 and 3); Retrospective: one "i" and the no-engine "?" (was 3 "?"); Sandbox list: one "i" (was 3); model page: one "i" and the no-engine "?" (was 2 and 1).
- Tests:
  - test_fewer_marks: KEEP holds Home's map "i" and Retro's "tt-rt-page"; new test_every_page_holds_one_i_and_the_forecast_tab_two; test_home_how_it_works_is_its_drawing_and_three_named_equations and test_home_record_says_its_unit_under_the_table replace the two that pinned the "i"s; test_the_model_list_carries_no_note_marks; the workbench test reads one mark and finds Jitter and Seed in the Save and run step.
  - test_hub_setup: test_a_machine_without_the_engine_says_so_once_in_setup (one "?", no build line, the fix said once); the badge and recount pins move to "no ?".
  - Pins moved, since the marks are the bug: test_pages (the record's cells, plain filter and withdrawn placement are read on Methods; the forcing reading on /models), test_relwis_conventions and test_retro_words (tt-rt-page; Home's unit line), test_sandbox_shipped (one mark).

## UI-14 ("i" panels are walls of text) (also HM-10)
- Reproduced: yes (text length of each panel, dev plus G32 and G33): Home How it works 835, Home record 663 (HM-10's ~110 words), Forecast Settings 565, season page 585, Methods replay 446, Output 617 after G32 (1,580 on dev before it).
- Fix:
  - Home: the two longest panels are gone (UI-13 above).
  - Methods (methods.html): the replay "i" is two lines under its title (330 characters): the eight shipped weeks and the two placeholder weeks; the first line restated the title.
  - Output: G32 already cut it to three lines.
  - Left as is: Forecast's Settings "i" (six one-line definitions of the card's own terms, rewritten by G30 on dev today); the season page's "i" (its first line is report_season.py's score note, which the exported season report prints too: changing it changes a report file, so it is not a template trim).
- Tests: the marks tests above; the Methods panel by test_fewer_marks' KEEP and the pages tests.

## UI-15 (53 here, 52 there) (also HM-15, ME-14)
- Reproduced: yes on dev: Forecast's checkbox "all 53 jurisdictions", Data's stat "Jurisdictions 53", while Home, Methods and the run page say 52 jurisdictions plus US.
- Fix: one phrase per context. A count that includes US is "53 locations"; "jurisdictions" is the 52 (the 50 states, DC and Puerto Rico). Forecast's checkbox, refusal and coverage words (routes/forecast.py, forecast.html), Data's two stats (data.html), the archive record's words (core/archive_record.py, a sentence only), Home's hero fact and Methods' Locations stat.
- Tests: test_cross_page.py::test_us_national_is_a_location_never_a_jurisdiction; the pins of the old words in test_data_view, test_dataset_upload_box, test_datasets_ui and test_forecast_us_choice move.
- Risk: archive_record.py is core but only a sentence of a status message changes; no run path reads it. No output check needed: no file in section 4's list that a run writes is touched.

## Checks
- ruff (the gate) clean. The marks, pages, relWIS, Setup, Retro, Sandbox, engine build, map, kit, layout, cross-page, display, data, dataset and Forecast US tests: 386 passed.
- Live (both): / to /sandbox at 1280 px light and 390 px dark, no sideways scroll, no page errors; the record card's unit line, Setup with no engine, Retro's "i" and the workbench's How it works menu screenshotted.
- Windows: templates and tests only, and one Python sentence.

## For Ely
- Home no longer says, behind an "i", each column's cell count, the plain filter's figures or that placements were withdrawn: they are on Methods, which the record's unit line links. If Ely wants them on Home, they would be a visible line, which this group avoids.

## Patch
G35/proposal.patch (git diff dev-plus-G33..proto/G35-A2)
