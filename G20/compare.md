# G20: compare (B)
A's proposal read in full; A's patch applied on origin/dev 0e9e90b (clean)
and served beside mine with the same state and the same two datasets
("Kids hospital admissions" and 80 a's), measured with one script at 390,
768 and 1280 px, text 100, 130 and 160%.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| HM-06 | `pipe figscroll`, "How it works (scrolls)" | the same, "Weekly forecasting workflow (scrolls)" | Equal. |
| HM-09 | the table in a figscroll region | the same | Equal. |
| ME-06 | each row a wrapping flex, name and help at 100%, Range and Default after; `data-label` | each row a block, the two cells inline-block; `data-label`; the rules in a second phone block after the table's own (the sheet's first phone block precedes them and loses on order) | Equal on the page (both 314 px, every cell on screen). |
| ME-07 (MO-19) | a two-column grid: the symbol, then meaning, units and source under one another | a three-column grid: the symbol (wrapping, at most 6rem) beside the meaning; units and the source tag on one line under it | B, criterion 1 for MO-19: the Groundhog's long row 134 px (A 171), the pf2s table's tallest 95 (A 111); three stacked lines per row is nearer the wall of text MO-19 names. |
| ME-08 | non-breaking hyphens (a U+2011 literal through `replace`), `mt-rec`, its heads may wrap | non-breaking hyphens (`&#8209;` in the labels, as the template writes every other non-ASCII glyph), `mt-rec`, its cells take Home's performance-table padding on a phone | Equal on the page (both 332 in 332, every season one line). B's keeps the heads as they are and mirrors `.perf`. |
| ME-09 | `fit-content(40%)` | the same | Equal. |
| ME-10 | `.uk-fold-sum{flex:1 1 0}` | `.uk-fold-sum{max-width:calc(100% - 1.4em)}` | B, criterion 2: A's grows every title to the line's end, so a badge after it moves to the far right on every fold with one ("Variables … [22 symbols]" 355 px apart at 1280, the Model settings groups' "N changed" too); B's keeps a short title at its own width (the badge beside it, as now) and wraps only the long ones beside the chevron, the badge dropping below. Both: no title under its chevron at 100 or 160%. |
| MO-23 | figscroll "Harmonic figure (scrolls)" (the generic 620 px: labels 15.5 px); `.nw` on the set and on `share A / (A + B)` | the same region name (revised today, for test_theme_and_harmonic's count); the svg `dg-harm` at its drawn 560 px (labels 14 px, as on a desktop); `.nw` on the set and on the whole `Binomial(…)` | B, criterion 4 and 5 in spirit: the figure keeps its own size rather than growing past the desktop's; the typed line breaks before `Binomial(` rather than inside it ("Binomial( n," / "share A / (A + B) )" on A's). |
| DA-10 | `overflow-wrap:anywhere` on the name and the heading; `.dt-rowacts` nowrap always | the same wrap; `min-width:12rem` on the name cell; nowrap above 600 px, wrap in a stacked row | B, criterion 1: without a floor the name column is starved at 768 px and 160% (A: the long row 666 px tall, the Kids row 214; B: 149 and 86). 1280 px alike (rows 57, actions one line). |
| DA-11 | `#datasets .tablewrap` scrolls, positioned | `.dsup .tablewrap,#datasets .tablewrap` | Equal. |

Also: A's phone rules use `@media(max-width:40rem)`; the sheets write
`640px` everywhere else (criterion 4). A's tests: 7; B's: 8 plus "/"
in test_console_qol's region check.

Vote: B
