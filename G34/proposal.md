# G34 methods-polish: proposal (A)
Base: origin/dev c2ad352e (#90, G30, merged: ME-16 rewrites the notes G30 left)

How: a server from dev (8815) and one from the prototype (8818). Chromium at 1440, 1280, 1100, 900, 768, 700 and 390 px; each contents chip clicked in turn and the page scrolled by the wheel; the page printed to PDF (Letter, after the page's own beforeprint) and each page's blank tail measured from a render.

## ME-04 (a jump hides the section title under the bar)
- Reproduced: yes. Clicking Fitting: at 1280 the bar is 75 px but --mt-toc-h is 41 px, title top 66 (hidden); at 700, bar 106, var 73, title top 96 (hidden). 768 to 1100 and 1440 were fine (the Print button does not wrap the chips there).
- Root cause: methods.html's script sets --mt-toc-h before the Print / Save as PDF button joins the bar, and never measures again.
- Fix: the button joins the bar first, then barH() runs, and a ResizeObserver on the bar keeps the height current. The performance anchor (`<span id="performance">`) moves before its card's h2, so its jump shows the title (site_build's `_PERF_CARD` harvest follows the moved span).
- After: the title sits 23 to 26 px under the bar at every width above, 390 included.
- Note: with the right height, the scrollspy's band (an IntersectionObserver whose top margin was set from the bar's height before the button joined) let the section above a jumped-to one win: clicking Fitting marked SIHRS, Oracle marked Fitting, and so on. So the band is now made after the button joins, and its callback skips a section that ends behind the bar (text size can change the bar later). Every chip then marks its own section at 1280, 700 and 390, and wheel scrolling marks the section at the bar's line.
- Tests: `test_methods_polish.py::test_the_bar_is_measured_after_the_print_button_joins_it` (the order, the ResizeObserver, the band after the button, the behind-the-bar check, the moved anchor and the harvest regex).

## ME-05 (Policies never current)
- Reproduced: yes. Clicking Policies left aria-current on Under the hood (#stack) at every width: the last card cannot reach the band before the page ends.
- Fix: scrolled to the page's end, the last section is the one read (`atEnd()`, in the observer's callback and a passive scroll listener); a chip followed is marked at once (a click listener).
- After: Policies is marked after its chip and at the page's end; the other chips as before.
- Tests: `test_the_last_chip_is_marked_at_the_end_and_a_followed_one_at_once`.

## ME-13 (prior ranges: "lo < hi"; the refusal in engine words)
- Reproduced: yes. Methods' range reads "lo < hi (the engine's rule)"; `0, 1` for mult is refused "pf.prior.mult: prior_ranges: mult__FREE [0.0, 1.0] is not a valid loguniform_var range"; `-0.5, 2` for Reff "... Reff__FREE [-0.5, 2.0] is not a valid uniform_var range".
- Fix (knobs.py): `_log_prior(key)` reads the prior's distribution; `range_text` says "0 < low < high" for a log-uniform prior (mult, r) and "0 ≤ low < high" otherwise; `_coerce` refuses a range outside it in those words before the engine is asked: "pf.prior.mult: 0, 1 is outside 0 < low < high". The rule itself is the engine's, unchanged; a uniform prior may still start at 0.
- Tests: `test_a_prior_range_says_the_engines_rule` (four refusals and an accepted 0), `test_the_methods_table_states_the_rule_per_prior`; two test_knobs pins of the jargon refusal moved (the jargon is the bug).

## ME-16 (settings notes: walls of text, keys, people, files)
- Reproduced: yes, on dev after #90: eleven notes on Methods, 5 to 161 words (Historical ceiling 161, Upper-tail cap 114, Spread narrowing 105), citing docs/team files, dates, a person's rule and keys (output.tail_cap, rho*mult and i0, season_total).
- Fix (knobs.py notes only; help lines, defaults and ranges untouched): one plain sentence each, at most 45 words, by labels and choice words. The sealed record's values stay ("the sealed record ran 0.30", "ran 2"); the Groundhog's two record figures stay as README has them (0.660 against 0.670; 0.642 against 0.660); research knobs say "Research, off at 1" or "off at 0". The screens' figures and provenance are already in docs/ORACLE-SIHRS.md (6b, 6c) and docs/DONOR-BANKS.md, so nothing is lost. What the seed denominator sets is said in its help ("Sets the reporting rate and first infections ..."). The zero-anchor note is not shown on Methods (a decision knob is not in the panel's groups), so it stays.
- Tests: `test_each_settings_note_is_one_plain_sentence`. Pins moved: test_forecast_text's "It pins rho*mult and i0." (G30) now reads the help's words; test_oracle_card_words' ME-12 pin of the narrowing screen's figures becomes "the note quotes no figure to set against the record" (with no figure, the 0.720 baseline cannot disagree with the page's 0.738).
- For Ely: none (no number, default or rule changes; only where the screens' figures are read).

## ME-18 (two Policies folds repeat their titles)
- Reproduced: yes: "A newest week that reads 0, collapses, or was not reported is the forecaster's decision ..." and "Two measured caveats (docs/archive/RELEASE-1.0.md): seven of 76 ...".
- Fix: the bodies start "It is the forecaster's decision ..." and "Seven of 76 sealed weeks ..." (the archive file named at the sentence's end as before).
- Tests: `test_the_policies_folds_go_on_from_their_titles`.

## ME-21 (printing leaves blank page areas)
- Reproduced: yes. 19 pages; page 1 is 64% blank, pages 4, 10 and 12 are 65%, 76% and 93% blank: a card taller than what is left of a page moves whole to the next.
- Fix (tabs/methods.css, print): break-inside:avoid on figures (svg), tables, folds and stat lists instead of whole cards.
- After: 19 pages (every fold opens to print); no page but the last is more than 19% blank.
- Tests: `test_printing_keeps_figures_tables_and_folds_whole_not_cards`.

## ME-22 (medium confidence; reproduced: table scrollers can't be focused or named)
- Reproduced: yes: the eleven table scrollers on Methods (`.mt-setscroll` per settings group, `.eqvars-scroll`, three `overflow-x:auto` wrappers) carry no tabindex, role or name, unlike `.figscroll`.
- Fix: each gets `tabindex="0" role="region" aria-label="<what it holds> (scrolls)"`, G30's new fixed-settings table included (twelve).
- Tests: `test_each_table_scroller_can_be_focused_and_is_named`.

## Checks
- New `app/tests/test_methods_polish.py` (11 tests). Methods, knobs, knobs panel, oracle words, forecast text, pages, marks, layout and site-build tests: 259 passed, 21 skipped, 1 failed: test_forecast_text's two-marks test, the engine-build race that is on dev too (G30/review.md; it passes in the full order).
- ruff (the gate) clean. Output check: not needed (notes, templates, CSS and a refusal before the engine; no run path).
- Windows: templates, CSS and strings; "≤" is in a UTF-8 file read as UTF-8.

## Patch
G34/proposal.patch (git diff origin/dev...proto/G34-A)
