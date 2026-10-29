# G13 phone-menus-rows: proposal (B)
Base: origin/dev fc6dce9

Reproduced in Chromium at 390x844 (text 100, 130 and 160% through the stored `fontsize`), with the measurements the hunt gives; CSS only, plus one class on the research form's particles box. No run path, no invariance check. Windows: stylesheets only.

## ST-01
- Reproduced: yes. /storage On disk at 390: the row's grid read 94 / 73 / 122 px at 100% (the title column), 6 px at 130% and 0 px at 160%, Delete's right edge at 422 px on a 390 px screen.
- Root cause: tabs/storage.css .st-row keeps three columns (minmax(0,1fr) auto 7.6rem) at every width; the fixed 7.6rem action column and the size column scale with the text and squeeze the title to nothing.
- Fix: in storage.css's existing phone block (max-width:40rem) the row stacks: "title title" / "meta meta" / "size act", two columns, the size left-aligned. Desktop and 768 px unchanged.
- After: title 327 / 309 / 291 px at 100 / 130 / 160%, Delete's right edge 359 / 350 / 340 (inside the screen).
- Tests: test_phone_layout.py `test_storage_rows_stack_at_phone_width`.

## ST-02 (also: UI-05)
- Reproduced: yes. The ledger filter's buttons at 390: scrollWidth over clientWidth 62/50, 68/50, 68/50 at 160% (running, research, modified) and 65/59 at 130%.
- Root cause: ui-kit.css .uk-seg is an inline-flex row that never wraps, and its children shrink below their words.
- Fix: .uk-seg wraps (flex-wrap:wrap) and each segment keeps its word's width (flex:0 0 auto); the border and radius stay. At 390 the six buttons take two rows at 130% and three at 160%; at 768 and 1280 one row, as before (no segment overflows at any size tested).
- Tests: `test_a_segmented_control_wraps_instead_of_squeezing_its_words`.

## SB-01 (also: UI-02)
- Reproduced: yes. /sandbox?model=sir_example at 390: How it works spans x -210 to 142, Manage -112 to 246 (getBoundingClientRect).
- Root cause: nau.css .sbmenu is absolute with right:0 inside its details; at phone width sandbox.css moves the summaries under the title to the left, so the menus hang off the left edge (and, anchored left instead, a menu opened from the second summary would hang off the right).
- Fix: in sandbox.css's phone block the menus hang under their row, as wide as it: .sbhead-menus is the positioning box (position:relative), each details.sbmanage is static, and .sbmenu reads left:0; right:0; width:auto; max-width:none. Desktop and 700 px are untouched (the block starts at 640 px).
- After: both menus span x 14 to 376 (100%) and 23 to 367 (160%) at 390; inside the screen at 480 and 640; at 700 and 1280 as before.
- Tests: `test_the_sandbox_menus_open_from_the_left_at_phone_width`.

## SB-13
- Reproduced: by the table's own markup at 390 (a sandbox fit needs the private engine, so the Runs table was injected with the template's markup, two rows): scrollWidth 362 in a 332 px box, overflow-x auto with no cue, the time column out of sight.
- Root cause: the run id (a 22-character token) cannot wrap, so the four columns are wider than the box and the box scrolls silently.
- Fix: sandbox.css lets .sbrunlist's first column wrap (overflow-wrap:anywhere). After: scrollWidth 332 = clientWidth at 390, 422 at 480: all four columns in view.
- Tests: the same test pins the rule.

## UI-07
- Reproduced: yes. Display at 390 and 160%: the readout's right edge at 391 past the popup's 367; GitHub Light and Solarized Light on 3 lines broken inside words, Dracula on 2.
- Root cause: nau.css .fontsize's range keeps min-width:5rem (128 px at 160%), which pushes the readout out; .dm-grid is four fixed columns, 80 px each at that size, where the names break inside words (overflow-wrap:anywhere).
- Fix: the range's floor is 3rem; the grid is repeat(auto-fill, minmax(5.2rem, 1fr)): four tiles per row at the standard size in the desktop popup (unchanged, measured against dev), three at 390 and 100%, two at 390 and 160%.
- After: readout right edge 340 inside 367 at 160%; names at most 2 lines, broken at spaces; 1 line each at 390 and 130%.
- Tests: `test_the_display_menu_fits_its_readout_and_theme_names`.

## MO-08
- Reproduced: yes. /model/pf2s at 1280: #rr-particles clientWidth 68 against scrollWidth 91 with 100000 typed ("1000C" shown).
- Root cause: the live unit ("100,000 particles") grows beside the box in a flex row where the input may shrink to nothing (uk-affix: the input flex 1 1 auto, min-width 0) inside an 11rem grid cell.
- Fix: the box carries a page class, md-count, and tabs/models.css gives it flex-wrap:wrap with the input at flex:1 0 7.5em: the box keeps room for six digits and the unit wraps onto the line under it when the cell is narrow. After: clientWidth = scrollWidth (183 at 1280, 222 at 390, 296 at 390 and 160%); the unit reads whole under the box.
- Tests: `test_the_research_particles_box_keeps_its_digits`.

## Checks
- Targeted: test_phone_layout (5), test_ui_layout, test_fewer_marks, test_sandbox_guard: 64 passed; ruff gate clean.
- Live from the prototype at 390 (100 / 130 / 160%), 480, 640, 700, 768 and 1280, light; the Storage rows and the Display menu also in dark at 390.
- For Ely: none.

## Patch
G13/proposal.patch (git diff origin/dev...proto/G13-B)
