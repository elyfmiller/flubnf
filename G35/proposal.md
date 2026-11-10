# G35 cross-page: proposal (B)
Base: origin/dev e068a540 (#91 merged; built before G32 to G34 land, so Output's panel (G32) and Methods' (G34) are theirs)

How: the dev server and one from the prototype; Chromium at 1280 px light and 390 px dark; the marks counted per page as test_fewer_marks counts them (visible, outside closed folds); a context whose localStorage throws SecurityError, with the OS dark and light.

## UI-12
- Reproduced: yes. With storage blocked and the OS dark: data-theme null (a light page), High contrast toggled sets data-contrast but aria-checked stays false, three SecurityError page errors.
- Root cause: base.html's first-paint script reads localStorage unguarded, and the contrast, vision and text-size handlers write unguarded (the theme picker alone is guarded).
- Fix (base.html): the first-paint script reads through `get()` and writes through `put()`, each a try/catch; the three handlers' writes are wrapped. A blocked store reads as nothing stored and drops a write, so the page follows the OS and a switch works for the visit.
- After: data-theme "dark" under a dark OS, "light" under a light one; High contrast toggles with aria-checked "true"; a text-size step applies; no page errors. The exported season report shares base.html.
- Tests: `test_cross_page_polish.py::test_blocked_browser_storage_still_follows_the_os_and_the_switches` (every localStorage use in base.html is guarded; the script's helpers).

## UI-15 (also HM-15, ME-14)
- Reproduced: yes: Forecast "all 53 jurisdictions", Data "Jurisdictions 53", Methods "Locations all 52 US jurisdictions", Home "all 52 US jurisdictions", Retrospective "all 52 jurisdictions" (US ticked beside), run pages "all 52 jurisdictions plus US national".
- Fix: where US is counted in, "locations": Forecast's box "all 53 locations", the progress label and the refusal (`_scope_label`, routes/forecast.py), Data's stat "Locations"; Methods' Purpose tile reads "53 locations: 52 jurisdictions plus the national total", the words the public site already wrote over it (site_build's `_LOCS_TILE` rewrite is now dead and goes); Home's How it works lead says "52 US jurisdictions and the national total". Where US stands apart (Retrospective's "all 52 jurisdictions" with US ticked beside, the run page's "52 jurisdictions plus US national", Home's "52 US jurisdictions" and coverage "of 52"), the 52 stays. Pins moved in test_forecast_us_choice, test_datasets_ui, test_dataset_upload_box and test_data_view; test_site_smoke's needle is unchanged (the tile now carries those words itself).
- Tests: `test_the_count_is_53_locations_where_us_is_counted_in`.

## UI-13 (also HM-19) and UI-14 (also HM-10)
- Reproduced: yes, on dev after G29 to G31: Home 3 "i" (map 157 chars, performance 663, How it works 835) and, without the engine, a "?" per missing Setup component and one on the Setup badge; Retrospective 3 "?" (the title's 3-line explainer, the engine alert's install hint, Import's); Storage 0 (G29); Output 1 "i" of 1,713 chars (G32 cuts it); Methods 1 "i" of 446; Forecast its two; Models 1 of 332; the Sandbox list 1 "?" per note, the model page 2 "i" (663 and 274) and the machine notice's "?".
- Fix:
  - Home keeps one "i", the map's (how to read and move it). How it works: a one-line lead under the heading (what is forecast, for whom, by which two models; nothing blended) and each equation's reading as one muted line under it; the workflow drawing's description already says the pipeline. Measured performance: one muted line (relWIS against the baseline, below 1.000 beats it, each column on its own cells, placement among teams withdrawn, a link to Methods' Measured performance, which carries the Ensemble's cells, the plain filter's record and the two-season figure). The Setup card's missing components say what they are and where they were looked for in a muted line each, and the badge's "?" (the same names as the list) goes: a student machine without the engine shows no row of "?" marks.
  - Retrospective: the title's "?" becomes a one-line lead (the replay rule and the relWIS sentence test_retro_words pins as the page's explainer); the engine alert carries its install hint in its text; Import's "?" becomes a hint line under its heading. The run button's reason and a season's error stay what they are (passing states).
  - Not changed, and why: the Sandbox model page's two "i" (the files', the run settings') are the Sandbox cleanup's recorded design ("one 'i' a card", test_the_workbench_keeps_one_mark_a_card...), and its notes' "?" name a model's origin; the season page's "i" is four one-line facts (the scoring note, the legend, the pooled scope, the US row); Forecast keeps two by the rule; Output's and Methods' panels are G32's and G34's. Left for A to decide whether the Sandbox's two should also become one.
- After: Home 1 "i" (plus, without the engine, the engine-build alert's "?", #61's); Retrospective 0; no sideways scroll at 390 px; the Home tests of the three readings and the record move to the lines (test_fewer_marks, test_pages).
- Tests: test_fewer_marks' KEEP ("/": {tt-hm-map}; "/retro": none of its own), `test_home_how_it_works_reads_the_three_equations` and `test_home_record_is_read_from_one_line` rewritten; test_pages' Home pins moved to Methods for the figures that left Home's "i"; `test_cross_page_polish.py::test_home_and_retrospective_keep_the_mark_rule`.

## Checks
- New `app/tests/test_cross_page_polish.py` (3 tests); the Home, Retrospective, marks, pages, site, data view, forecast scope and dataset tests: 170 passed, 21 skipped (plus the Home and Retrospective sets: 117 passed). ruff (the gate) clean. Full suite: 4658 passed, 215 skipped, 7 failed on pins of the old markup, each since moved: the first-paint script's reads and the text-size write (test_a11y_modes, test_season_palette, test_display_themes), the Setup badge's "?" (test_hub_setup), Home's and Retrospective's relWIS wording read from the old "i" and "?" (test_relwis_conventions), and Resume's sentence (test_resume_rerun; the lead keeps it). Rerun with the pins moved: 4665 passed, 215 skipped, 0 failed.
- Output: no run path. Invariance check: no.
- Windows: templates, one script, one regex removed.

## Patch
G35/proposal.patch (git diff origin/dev...proto/G35-B)
