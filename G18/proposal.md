# G18 home-map: proposal (A)
Base: origin/dev c423847 (G17 merged; the prototype was cut from 399f694
and dev merged in, home.py and home.html merging cleanly)

How: a dev server and a prototype server, each with Groundhog runs for
2026-10-17 (Arizona and New York; US alone; all 53), and the newest
run's report.html and report_inputs.json removed for HM-03. Chromium at
1280 px and 390 px (Pixel 5 touch for the swipe), light, dark and
Dracula; Tab traced with the keyboard.

## HM-02 (also: none)
- Reproduced: yes. Home: "US categorical forecast · 2026-10-17"; the report
  it links: "reference date 2026-10-24"; the file
  2026-10-24-NAU_PyBNF-GroundHogCGR.csv.
- Fix: the heading reads as Output heads the same forecast: "US
  categorical forecast · Round 2026-10-24 (as of 2026-10-17)" (home.py
  passes `outlook_ref` from output's `_reference_date`; home.html).
- Tests: `test_home_map.py::test_the_heading_names_the_round_with_its_as_of`.

## HM-03 (also: none)
- Reproduced: yes. With the newest run's report removed: two states read
  "click for details", `window.MAP_LINK='/output/report'` is set, the
  states are buttons, and the map's "i" says "click one to open its
  section of the weekly report". The Weekly report button is (rightly)
  gone.
- Root cause: home.py builds the map (cached) with MAP_LINK and every
  state with data clickable, whatever `_has_report` says.
- Fix: `_outlook_block_cached(rid, mtime, has_report)`: the report's
  presence is part of the cache key. Without it there is no MAP_LINK and
  no clickable state (no "click for details", no button role), and the
  "i" keeps only "Hover a state for its numbers."
- Live after: 0 "click for details", no MAP_LINK, no buttons; with the
  report, as before.
- Tests: `test_without_the_report_no_state_promises_or_opens_it`.

## HM-04 (also: none)
- Reproduced: yes. A US-only run: "Coverage 0 of 52 jurisdictions", a
  gray map, and the run's one forecast nowhere on Home; a 53-location run
  shows no national category either.
- Fix: the US card's most likely category and its probability, as one
  stat beside Coverage: "United States stable 45%" (home.py
  `outlook_us`, home.html).
- Live after: "Coverage 0 of 52 jurisdictions · United States stable 45%"
  (US only), and beside "52 of 52" on the full run.
- Tests: `test_the_national_category_reads_beside_the_coverage`.

## HM-07 (also: none)
- Reproduced: yes. At 390 px with touch, a swipe that starts on the map:
  scrollY 454 → 454.
- Root cause: usmap.py `_shell`: `touch-action:none` on the svg, while its
  script handles mouse events only (no touch pan).
- Fix: the svg drops `touch-action:none` (the default lets the page
  scroll and pinch; the mouse's drag and wheel are unchanged). It is the
  same map on the report and the Forecast tab.
- Live after: scrollY 520 → 941.
- Tests: `test_the_map_lets_a_swipe_scroll_and_walks_its_states_by_name`.

## HM-16 (also: none)
- Reproduced: yes. Tab from the map bar: svg#usmap (an unnamed stop),
  then Alabama, Alaska, Arizona, Colorado, Florida, Georgia, Indiana ...
  (topojson order; Arkansas and California come later).
- Fix:
  - usmap.py: the svg is `role="group" aria-label="Map of the states"
    tabindex="-1"`, named and no longer a stop;
  - the states are emitted in name order, which is the order Tab walks
    them (drawing order is moot, as no two states overlap);
  - home.html: a skip link before the map, "Skip the map", hidden until
    focused (the console's own `a.skip`), only when the states are
    clickable. It is in Home's template, not the shared map, because the
    report page has no `a.skip` style.
- Live after: Skip the map, Alabama, Alaska, Arizona, Arkansas,
  California, Colorado, Connecticut ...
- Tests: in the same test.

## HM-18 (medium; also: none)
- Reproduced: yes. Arizona and New York: the other states' hovers say
  "not fitted in this run", the legend says "no data"; in Dark the swatch
  (rgb 42,47,80 on 21,23,41) barely shows.
- Fix: `map_legend(scoped=True)` when the run's coverage is known: "not in
  this run or no data" (Home passes it when the bundle gives
  fitted_fips); nau.css: `.maplegend .sw` keeps a 1px edge in `--line`.
- Live after: the legend reads it, and the swatch shows in Dark
  (screenshot).
- Tests: `test_the_legends_gray_says_what_the_hovers_say`.

## UI-08 (also: none)
- Reproduced: yes, by the tokens: the hero chips' small bold labels are
  `--gold-bright` on `--navy`: Dracula #BD93F9 on #44475A 3.79:1, Nord
  #88C0D0 on #434C5E 4.31:1. Every other theme is at 4.5 or over.
- Fix: a token for the chip labels, `--hero-chip-ink`, in every theme
  block (the themes test asks every theme to define every token). It is
  each theme's own `--gold-bright`, except Nord #A3D4E0 (5.36:1) and
  Dracula #D6BCFA (5.42:1), lighter tints of the same hues. home.css
  `.hm-facts b` uses it. The large accent word keeps `--gold-bright`.
- Live after: Dracula chips rgb(214,188,250); other themes unchanged.
- Tests: test_display_themes' hero check adds the chip ink at 4.5:1 on
  `--navy` in every theme and mode.

## Checks
- New `app/tests/test_home_map.py` (5): all fail on 399f694 and pass
  here. test_display_themes gains the chip check.
- Targeted: test_home_map, test_display_themes, test_pages,
  test_fewer_marks, and the Home and map tests: all pass. ruff clean.
- Full suite (FLUBNF_HUB=/nonexistent): 3574 passed, 155 skipped, 0
  failed (before the dev merge); after it, the Home, map, theme, Setup and
  layout tests: 99 passed.
- Invariance: not needed (Home and the map's markup only).
- Windows: CSS, template and markup only.

## Patch
G18/proposal.patch (git diff origin/dev...proto/G18-A)
