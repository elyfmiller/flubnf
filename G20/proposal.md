# G20 phone-tables: proposal (B)
Base: origin/dev 6546b5f

All ten reproduced in Chromium at 390x844 (and 768x900 for DA-11), text
100, 130 and 160%, light and dark, on a server from dev with two datasets
stored ("Kids hospital admissions" and an 80-character name). The changes
are CSS and markup only: no route, no core file; no invariance check.

## HM-06
- Reproduced: yes. Home's pipeline showed 332 of 620 px ("eac", "c" sliced
  at the card edge), no shadow, no tabindex or role.
- Root cause: home.html `<div class="pipe">`: nau.css's phone block gives
  `.pipe` the scroll but the cue (the edge shadows), the focus ring and the
  region name are `.figscroll`'s.
- Fix: the div is `pipe figscroll` with `tabindex="0" role="region"
  aria-label="Weekly forecasting workflow (scrolls)"`, as the Methods
  drawings are. The vertical variant would be a second drawing to keep
  in step with the first; the cue is what every other wide figure has.
- Tests: test_phone_tables.py `test_the_home_workflow_and_performance_table_scroll_with_the_figures_cue`;
  "/" added to test_console_qol's `test_wide_figures_are_labelled_focusable_regions`.
- Risk: none beyond Home; the harvest reads `class="perf"`, not the pipe.
- For Ely: none

## HM-09
- Reproduced: yes. At 130% the table was 382 px in a 351 px card ("FLUS",
  "ENSE" cut, no cue); 470 in 342 at 160%. Fits at 100 and 115%.
- Root cause: the `.hm-perf` card has no scroller; the table overflows it.
- Fix: the table sits in `<div class="figscroll" tabindex="0"
  role="region" aria-label="Measured performance table (scrolls)">`: at
  100% nothing changes (no overflow, no shadow); at 130% and 160% the
  table scrolls inside the card with the figures' edge shadow. Wrapping the
  headers cannot fit "GROUNDHOG" at 160%, so the scroller is the honest
  form. `harvest_placement` still finds `<table class="perf">`.
- Tests: the same test.
- Risk: a tab stop on Home's table at every width (the drawings have the
  same); nothing else.
- For Ely: none

## ME-06
- Reproduced: yes. Each settings table 608 px in a 314 px scroller: "What
  it does" cut mid-word, Range and Default fully off-screen, no cue.
- Root cause: methods.css `.mt-settings{min-width:38rem}` in `.mt-setscroll`
  (overflow-x:auto, no cue).
- Fix: under 640 px each setting stacks, the dataset rows' way: the name,
  what it does, then "Range: …" and "Default: …" on one line, the two cells
  named by `data-label` (methods.html) and `td[data-label]::before`. The
  table drops its min-width and its header; nothing scrolls. The rules
  live in a second phone block after the table's own rules (the sheet's
  first phone block comes before them and would lose on order).
- Tests: `test_a_setting_stacks_with_its_range_and_default_on_a_phone`;
  test_fewer_marks's two `<td>` pins read the data-label cell (markup, not
  behavior).
- Risk: Methods only, under 640 px.
- For Ely: none

## ME-07 (also: MO-19)
- Reproduced: yes. The Variables table 360 px in 314: Source cut to "ind",
  "der", "fitt", the header "SOU"; the Symbol column 105 px for one-letter
  symbols. MO-19: the Groundhog's "growth ratios" row 286 px tall in a
  93 px Meaning column.
- Root cause: nau.css `.eqvars-scroll{overflow-x:auto}` with four columns
  and `tbody th{white-space:nowrap}`; the long symbols set the first
  column's width for every row.
- Fix: under 640 px each row is a grid: the symbol (wrapping, at most
  6rem) beside its meaning, which takes the rest of the width; the units
  and the source tag under the meaning; the header row hidden. The
  table is 314 px, every column on screen; the Groundhog's long row is
  134 px tall (was 286), the pf2s table's tallest 95.
- Tests: `test_a_variables_table_puts_the_units_and_source_under_the_meaning_on_a_phone`.
- Risk: the four Variables folds (Methods, the three model pages) under
  640 px; the public site has no nau.css and keeps its own table.
- For Ely: none

## ME-08
- Reproduced: yes. "2023-" / "24", "2024-" / "25 and 2025-" / "26"; the
  table 339 px in a 332 px box (7 px of sideways scroll).
- Root cause: methods.html's season labels are plain `<td>`s (only `.num`
  cells get nowrap), and the table's cells keep the desktop padding.
- Fix: the labels carry non-breaking hyphens (`&#8209;`, in the template's
  literals, `| safe`), so "2024‑25 and 2025‑26" wraps only at its spaces;
  the table is `mt-rec` and under 640 px its cells take Home's
  performance-table padding (`.28rem .3rem`): the table is 332 px in a
  332 px box, every season on one line. A nowrap column would make the
  "both" row 140 px and the table scroll; the hyphen keeps the headers as
  they are.
- Tests: `test_the_records_seasons_never_split_at_their_hyphen`.
- Risk: the record table only. The Methods performance table's headers
  ("2023-24") are `th.num`, already nowrap.
- For Ely: none

## ME-09
- Reproduced: yes. At 160% the label column was 243 px, the values 33 px,
  every value letter by letter; at 130% the values 99 px, "2026-09-" /
  "25", the withdrawn badge past the card edge.
- Root cause: ui-kit.css `.uk-stats--kv{grid-template-columns:max-content
  minmax(0,1fr)}`: a long label takes its full width first.
- Fix: `fit-content(40%)`: a label keeps its own width up to 40% of the
  list, then wraps. At 160% the labels are 119 px, the values 156 ("the
  same ratio on the WIS of log(x+1) counts" in five lines, "before
  2026-09-25" in two, the badge inside the card); at 130% every value fits.
  fit-content never breaks a word: Forecast's single-word labels
  (`season_boundary_month`) keep their width at every size, so the other
  five lists are unchanged; on a 390 px phone at 100% the one change is
  "Placement among / teams" on two lines.
- Tests: `test_a_long_label_cannot_starve_a_fact_lists_values`.
- Risk: every `uk-stats--kv` (Methods, Forecast, run, model pages), only
  where a multi-word label is wider than 40% of its list.
- For Ely: none

## ME-10
- Reproduced: yes. "A newest week that reads 0, collapses, or was not
  reported": the chevron alone on a line, the title under it; at 160%
  ten folds do it ("Cells behind these figures", "Oracle SIHRS: particle
  filter" among them).
- Root cause: ui-kit.css `details.uk-fold > summary` is `flex-wrap:wrap`
  and `.uk-fold-sum` has no cap: its hypothetical size is the whole title,
  wider than the line, so it wraps to the next line before shrinking.
- Fix: `.uk-fold-sum{max-width:calc(100% - 1.4em)}`: the title fits the
  chevron's line and wraps beside it; a short title keeps its own width
  (a badge after it stays beside it); a long one pushes only the badge to
  the next line ("Oracle SIHRS: particle filter" / "10 settings" at 160%).
- Tests: `test_a_long_fold_title_wraps_beside_its_chevron`.
- Risk: every uk-fold summary; measured on Methods at 100, 130 and 160%:
  no title below its chevron, every short title unchanged.
- For Ely: none

## MO-23
- Reproduced: yes. The harmonic 332 px wide: labels 8.3 px. "… 52 ) ),
  s ∈" / "{A, B}" and "Binomial( n, shareA/" / "(A+B))".
- Root cause: diagrams.html `harmonic()` is a bare svg (width:100%)
  outside `.figscroll`; the two expressions have no `.nw`.
- Fix: the harmonic sits in the same `figscroll` region as the other
  drawings (aria-label "Seasonal harmonic (scrolls)" / "Two-strain
  seasonal harmonic (scrolls)"), its svg `dg-harm` with `min-width:560px`
  on a phone (its drawn width, not the 620 the 840-wide drawings use),
  so its labels keep 14 px and it scrolls with the cue; Home's copy too.
  `<span class="nw">` around `s ∈ {A, B}` and `Binomial(…)`: the lines
  now break "… 52 ) )," / "s ∈ {A, B}" and "typed positives: kA ∼" /
  "Binomial( n, share A / (A + B) )". The other pages' lines checked at
  390 px: they break after a comma or before a term.
- Tests: `test_the_harmonic_scrolls_on_a_phone_and_set_expressions_hold_together`.
- Risk: Models, model/pf2s, model/pf, Methods and Home; the site renders
  the wrapper as a plain div (no figscroll rule there).
- For Ely: none

## DA-10
- Reproduced: yes. At 1280 every row 91 px (three-line actions); at 390
  the browser's heading ran off the card; at 1280 and 160% the page
  scrolled to 1677 px.
- Root cause: `.dsname` and the heading `#h-ds-browse` have no
  overflow-wrap; `.dt-rowacts` is `flex-wrap:wrap`, so the squeezed
  actions wrap despite `td.dsactions{white-space:nowrap}`.
- Fix: nau.css `.dstable td.dsname,#h-ds-browse{overflow-wrap:anywhere}`
  and `.dstable td.dsname{min-width:12rem}` (anywhere alone let the name
  column shrink to a sliver at 768 px/160%: the Kids row 214 px tall);
  data.css `.dt-rowacts{flex-wrap:nowrap}` above 600 px (a stacked row
  keeps wrap). Now at 1280 the long name wraps to two lines and every
  row's Forecast / Replay / Delete is one line; at 390 the heading wraps
  (three lines); at 1280/160% no page scroll (the table 1186 px in its
  scroller).
- Tests: `test_a_long_dataset_name_wraps_and_the_stored_table_scrolls_in_its_card`.
- Risk: the Data tab's stored table and the browser heading.
- For Ely: none

## DA-11
- Reproduced: yes. 768 px, 160%, ordinary names: document 782 wide (the
  `.uk-sr` "Actions" at 782 inside an 897 px table).
- Root cause: nau.css `.dsup .tablewrap{overflow-x:auto}` reaches the
  upload box's table only; `#datasets .tablewrap` overflows visibly and
  the absolutely positioned sr span escapes to the page.
- Fix: `.dsup .tablewrap,#datasets .tablewrap{max-width:100%;overflow-x:
  auto;position:relative}`: the table scrolls inside the card (965 px in
  676 with ordinary names at 768/160%) and the span stays inside it;
  document 768. The tips are position:fixed, so the scroller clips none.
- Tests: the DA-10 test.
- Risk: the same table.
- For Ely: none

## Patch
G20/proposal.patch (git diff origin/dev...proto/G20-B): 10 files,
+194 −19: home.html, diagrams.html, methods.html, nau.css, ui-kit.css,
tabs/methods.css, tabs/data.css, test_phone_tables.py (8 tests),
test_console_qol.py, test_fewer_marks.py. Targeted tests 297 passed;
ruff clean; Windows: no path or encoding (the hyphen is an entity).
