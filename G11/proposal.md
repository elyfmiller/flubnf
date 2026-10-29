# G11 groundhog-text: proposal (B)
Base: origin/dev 368e922

## HM-01 (also: MO-01, ME-01)
- Reproduced: yes. GET / prints the Groundhog column 0.702 / 0.651 / 0.653, pooled 0.660, and the "i" says "(the pooled form it replaced: 0.670)"; /methods the same row and the 0.660 tile; /model/analogue's bars 0.660 against 0.670 "Without own-state weighting".
- Root cause: home.html:151-158 and 115-117, methods.html:465, 472 and 486-488, routes/models.py _record (literal figures of the form shipped 2026-10-15 to 2026-10-23). README's Measured record (line 164) gives the shipped form since 2026-10-23: 0.680 / 0.627 / 0.645, pooled 0.642 on 17,116 cells, and says it replaced the own-state form (0.660), not the pooled form (0.670).
- Fix: the three pages print the shipped row; the comparator beside it is the form it replaced (0.660, "Without the size-matched donors" on the model page; Home's "i" "(the form it replaced: 0.660)"); Methods' Cells fold names both earlier forms (0.660, then the pooled 0.670). Home's provenance comment updated.
- Tests: test_pages.py `_readme_groundhog_rows` now reads README's three Groundhog rows by their labels (it matched the "own-state weighting" lead twice and kept the last, the replaced row, which is why it passed on the old figures) and `test_every_page_prints_the_shipped_groundhog_from_the_readme_record` checks the shipped, replaced and pooled figures where each belongs; the pins in test_pages (home cells), test_models_tab (the Record sentence, the 2023-24 tile) and test_relwis_rule (Methods' ok cells) updated to the shipped figures, as the group note says.
- Risk: text and literals only. Invariance: no.
- For Ely: none.

## ME-02 (also: MO-02)
- Reproduced: yes. Methods' Groundhog card and /model/analogue's header, figure <desc> and Variables say only the own-state weighting; the size-matched kernel appears nowhere outside the settings table.
- Root cause: methods.html:365-404, routes/models.py HEADERS["analogue"], diagrams.html analogue_mech <desc> and eq_analogue's "growth ratios" row predate the kernel (2026-10-23).
- Fix: "How it forecasts" adds one sentence (inside each pool the donor weeks whose count is near the jurisdiction's newest count carry the most weight, with 30 effective donors as the floor, since 2026-10-23); the facts row gains "Weeks sized like the newest · most of the weight"; the bank fold names the three things that separate it from the bare analogue; the model page's blurb, the figure's <desc> and the Variables row say "donor weeks sized like the newest weighted most" (README's wording, shortened).
- Tests: test_groundhog_text.py `test_the_groundhog_description_names_the_size_matched_donors`; test_fewer_marks' pin of the bank sentence updated.
- Risk: none beyond the text. For Ely: none.

## ME-11
- Reproduced: yes. knobs.py help: "0 is the pooled form" (own share) and "none is the bare analogue" (bank); own share 0 alone still runs the kernel.
- Fix: the help says what the setting drops: "Share of the jurisdiction's own past weeks in the admissions pool; 0 drops the own-state weighting." (99 characters) and "Auxiliary donor pool spliced in; none runs without a bank." The notes (the screens' records) stand.
- Tests: `test_the_groundhog_help_names_no_form_one_setting_cannot_give`. For Ely: none.

## ME-17
- Reproduced: yes. Methods' Range of the bank reads "… | none (bare analogue) (none)": methods._choice appends the stored value to a word that already carries one.
- Fix: the choice word is plainly "none" (knobs.CHOICE_WORDS); the help beside it now says what none means, so the word needs no parenthesis, and _choice is untouched (its "(value)" suffix is right for every other choice, as test_fewer_marks pins "expected total (early season) (season_total_early)").
- Tests: `test_the_banks_range_on_methods_reads_each_choice_once`. For Ely: none.

## ME-23
- Reproduced: yes. Methods' ratios figure: title "one ratio per donor season", aria-label "Each donor season contributes one growth ratio per horizon", against the fold's "one state gives about five donors per season".
- Fix: diagrams.html analogue_ratios says "donor week" (title, aria-label, the macro's comment); the figure's three curves stay as the illustration.
- Tests: `test_the_groundhog_figures_describe_donor_weeks_and_a_four_week_fan`. For Ely: none.

## MO-15
- Reproduced: yes. analogue_mech's fan polygon 430,140 545,96 545,190 spans 115 units, 8 weeks on the 745/52 axis.
- Fix: the fan ends 4 weeks after the forecast date, x = 487 (430 + 4 × 745/52): polygon 430,140 487,118 487,164 and the median path to 487,143, the spread scaled to the shorter reach. Checked in Chromium at 1280 light and 390 dark: Feb to early March against the month ticks.
- Tests: the same test pins the fan's end within 2 units of the 4-week mark. For Ely: none.

## Checks
- Targeted: test_groundhog_text, test_pages, test_models_tab, test_relwis_rule, test_fewer_marks, test_knobs, test_knobs_panel, test_site_smoke, test_ui_layout, test_model_metadata: 289 passed, 1 skipped; ruff gate clean.
- Live from the prototype: / prints 0.680 / 0.627 / 0.645 / 0.642; /methods' tile 0.642 and the Range "… | none"; no "(none)", "pooled form" or "bare analogue" help, or "donor season" title.

## Patch
G11/proposal.patch (git diff origin/dev...proto/G11-B)
