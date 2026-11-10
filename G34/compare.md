# G34: compare (A)

B's patch applied cleanly on dev c2ad352e and served beside mine; measured the same way (each chip clicked at 1280, 700 and 390; wheel scrolling; Letter PDF after beforeprint, each page's blank tail from a render; the scrollers' attributes).

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| ME-04 | Button first, then barH(), ResizeObserver; the performance span before its h2. | The same order and observer; the performance id on the card. | Equal: title 23 to 26 px under the bar at every width in both. B's id on the card is the tidier anchor. |
| ME-05 | atEnd() plus a click mark; the band made after the button joins and a section ending behind the bar skipped. | The spy rewritten: the last section whose top passed the band, the last at the end. | Equal in effect: every chip marks its own section at all three widths, Policies at the end, and wheel scrolling matches in both. Mine is the smaller change; B's follows the hint's second option and needs no click mark. Either. |
| ME-13 | The table per distribution, and `_coerce` refusing out-of-rule ranges in its own words. | The table per distribution only. | B's. I missed that forms._refusal_words already turns the engine's refusal into "the low end must be above 0 and below the high end" on the panel, so my early refusal adds code for nothing a student sees (criterion 4). |
| ME-16 | One sentence each, at most 45 words; research knobs say "Research, off at 1/0"; the Groundhog's two README figures kept; no "pre-registered", no "shipped rule". | One or two sentences, up to 54 words (Upper-tail cap 54, Historical ceiling 53, Rate-change rows 54); "the shipped rule", "chosen by a pre-registered screen". | A's. The bug asks for "a student-readable line per setting": A's are about half as long and say what a student would see (off by default) rather than where a value came from (criterion 5). A's test pins one sentence, no keys, files, dates or people. |
| ME-18 | Same. | Same. | Equal. |
| ME-21 | break-inside on figures, tables, folds and stat lists: 19 pages, no page but the last over 19% blank (dev: pages 64, 65, 76, 93% blank). | Cards, folds and long tables may split; figures, fact rows and table rows never do; headers repeat; headings stay with what follows: 17 pages, worst 29% blank. | B's: the shorter document, as the bug asks ("a compact document"), with table headers on every page. |
| ME-22 | tabindex, role, name on each scroller, inline. | The same, plus a `.mt-scroll` class for the inline styles and the figscroll's focus outline. | B's: a focusable region shows where focus is. |

Vote: combine: B's patch, with A's ME-16 notes (knobs.py notes and `test_each_settings_note_is_one_plain_sentence`, plus the two pins A moved: test_forecast_text's seed words and test_oracle_card_words' narrowing figures).
