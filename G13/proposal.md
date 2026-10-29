# G13 phone-menus-rows: proposal (A)
Base: origin/dev fc6dce9 (G11 merged)

How:
- The same state on two servers, one from dev and one from the prototype:
  two Groundhog runs, the template dataset, a 2-state 2026-27 replay, the
  SIR example in the Sandbox, and two stand-in Sandbox runs (meta.json
  only; no engine here to fit).
- Chromium at 390 and 768 px, text 100, 130 and 160% (the Display menu's
  own localStorage key), light at 100 and 130%, dark at 160%.
- Script: getBoundingClientRect of each element, scrollWidth against
  clientWidth, and screenshots.

## ST-01 (also: none)
- Reproduced: yes. /storage On disk at 390 px: the four row parts measure
  94 / 94 / 73 / 64 px at 100%; the title column is 6 px at 130% and 0 px
  at 160%. Delete's right edge is at 422 px on a 390 px screen.
- Root cause: tabs/storage.css `.st-row`, a fixed three-column grid
  (`minmax(0,1fr) auto 7.6rem`) with no narrow rule.
- Fix: under 40rem the row is "title title / meta meta / size act". The
  size and Delete go on the line under the title, and the size is
  left-aligned there.
- Live after: title 327 / 309 / 291 px at 100 / 130 / 160%, Delete inside
  (right edge 340 to 359); 768 px unchanged.
- Tests: `test_phone_menus_rows.py::test_a_storage_row_stacks_its_size_and_action_under_the_title_on_a_phone`.

## ST-02 (also: UI-05)
- Reproduced: yes. /storage and /runs at 390 px: at 130% "running",
  "research" and "modified" are narrower than their words; at 160% four
  labels draw over each other.
- Root cause: ui-kit.css `.uk-seg` is inline-flex without wrap, and its
  choices carry `min-width:2rem`, so they shrink below their text.
- Fix: the kit's own wrap rule moves from `.uk-seg--quiet` to `.uk-seg`
  (wrap; each choice `flex:1 1 auto`, a line above it clipped on the first
  row, its left divider tucked under the outline). It comes into play only
  when the choices do not fit in one row: at 1280 px the ledger's switch
  measures 404x30 on dev and here. The quiet variant keeps its own colours.
- Live after: at 390 px, 160% dark, three rows ("All ok failed / running
  research / modified"), nothing clipped; the Forecast tab's "full series /
  season over season" takes two rows at 160%.
- Tests: `test_a_segmented_switch_wraps_rather_than_squeezing_its_words`.

## SB-01 (also: UI-02)
- Reproduced: yes. /sandbox?model=sir_example, menus opened:
  - at 390 px, How it works spans x −210 to 142, Manage −112 to 246;
  - at 600 px, −208 / −122;
  - at 641 to 720 px with 160% text, How it works still starts at −109 to
    −30.
- Root cause:
  - nau.css `.sbmenu{position:absolute;right:0}` hangs each popover from
    its button's right edge;
  - sandbox.css' 640px rule moves the buttons under the title at the left,
    so on a phone the popover opens leftwards off the screen;
  - in a narrow window at large text the How it works popover (22rem) is
    wider than the space left of its button.
- Fix:
  - sandbox.css, in the 640px rule: the menus row is the containing block
    (`.sbhead-menus{position:relative}`, `details.sbmanage{position:static}`)
    and `.sbmenu{left:0;right:auto}`. Both popovers open from the row's
    left edge, at most 100vw − 2rem wide.
  - sandbox.js, where the menus already close on Escape and outside clicks:
    on opening, a popover whose left edge is past 8 px is moved back
    inside (`right` set to the overshoot). This covers the windows above
    640 px at large text. Closing clears it.
- Live after: from 390 to 1280 px at 100 and 160%, every popover is inside
  the screen (left ≥ 8): 390 px 14 to 372; 641 to 720 px at 160%, How it
  works 8 to 571. 768 and 1280 px at 100% are unchanged.
- Tests: `test_the_sandbox_menus_open_inside_the_screen` (the rule and the
  script's clamp).

## SB-13 (also: none)
- Reproduced: yes. The Runs table at 390 px: 405 px of table in a 332 px
  box (526 / 315 at 130%, 647 / 298 at 160%); "10,000" is cut at the edge
  and time is off-screen with no cue.
- Root cause: `.sbscroll` scrolls sideways (nau.css) but shows nothing at
  its edge; the run id is long.
- Not changed: the run id. Ely's Sandbox answers (app.md, 2026-10-14) say
  "keep run ids, zip file names and ESS as they are".
- Fix: on a phone `.sbscroll` wears the edge shadow wide figures already
  have (nau.css `.figscroll`, the local/scroll background pair, no
  script). `.sbscroll` is added to that rule.
- Live after: the right edge darkens over the last 1rem (pixels 255 to
  156) while more columns are past it, and clears at the end.
- Tests: `test_the_sandbox_runs_table_shows_it_scrolls_sideways_on_a_phone`.
- For Ely: none. If a cue is not enough, the alternative is stacking the
  table on a phone, as `table.sbkeys` does.

## UI-07 (also: none)
- Reproduced: yes. Display menu at 390 px, 160%: the readout's right edge
  is at 391 px against the popup's 367; "GitHub Light" and "Solarized
  Light" run to 3 lines, "Dracula" to 2.
- Root cause: nau.css `.fontsize input[type=range]{min-width:5rem}` and the
  fixed `.dm-grid{grid-template-columns:repeat(4,minmax(0,1fr))}` with
  `overflow-wrap:anywhere` names.
- Fix: the slider's minimum is 3rem. The theme grid is
  `repeat(auto-fill,minmax(5em,1fr))`: four columns at 100% (as now), two
  at 160% on a phone, names broken only at spaces.
- Live after: 390 px, 160%: the readout ends at 340 inside 367, two columns
  ("Light" "Paper"), "Solarized Light" on two lines at its space; 768 px
  and 1280 px at 100% still four columns.
- Tests: `test_the_display_menu_fits_its_readout_and_theme_names_at_large_text`.

## MO-08 (also: none)
- Reproduced: yes. /model/pf2s at 1280 px: the Particles input is 77 px for
  10000 (scrollWidth 80) and 68 px for 100000 (91), shown as "1000C" and
  ")000"; at 390 px, 160%, 123 / 129.
- Root cause: ui-kit's `.uk-affix > input{min-width:0}` beside the live
  "100,000 particles" count, in an 11rem grid column.
- Fix: on the research card only (tabs/models.css): the affix wraps, and
  the input keeps `flex-basis:9ch; min-width:9ch`. Where the column cannot
  hold both, the count drops under the field.
- Live after: 1280 px: the input is 183 px and shows 100000 whole, with
  "100,000 particles" under it; 390 px, 160%: 296 px.
- Tests: `test_the_research_runs_particles_keep_their_number_visible`.

## Checks
- New `app/tests/test_phone_menus_rows.py` (6): all fail on fc6dce9's
  static files and pass here. They pin the rules: the repo's CSS tests do
  this, and the measurements above are the browser half.
- test_ui_kit, test_console_qol and test_ui_layout pass. ruff clean.
- Full suite (FLUBNF_HUB=/nonexistent): 3548 passed, 155 skipped, 0 failed.
- Invariance: not needed (CSS and one script).
- Windows: CSS and JS only.

## Patch
G13/proposal.patch (git diff origin/dev...proto/G13-A)
