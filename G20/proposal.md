# G20 phone-tables: proposal (A)
Base: origin/dev c10d257

How: a dev server and a prototype server, each with an all-53 Groundhog
run and one dataset uploaded under a 77-character unbroken name. Chromium
with the Display menu's text size at 100, 130 and 160%, at 390 px (768 px
for DA-11, 1280 px for DA-10's rows). Each element's box read against its
card or scroller; screenshots at 390 px light 100% and dark 160%.

## HM-06 (also: none)
- Reproduced: yes. Home's pipeline: 288 px past its box, no cue, no
  tabindex.
- Fix: it wears the figures' `.figscroll` (the shadow cue under 640px)
  and is a named, focusable region ("How it works (scrolls)"), as the
  model drawings are (home.html).
- After: the cue on, tabindex 0.

## HM-09 (also: none)
- Reproduced: yes. The performance table's right edge 420 / 516 px
  against its card's 371 / 367 at 130 / 160%.
- Fix: the table sits in a `.figscroll` region ("Measured performance
  (scrolls)"): it scrolls inside the card with the cue. The site
  harvest reads the first `table.perf`, which is unchanged.
- After: a scroller with the cue; the card clips nothing.

## ME-06 (also: none)
- Reproduced: yes. The settings table is 608 px in a 314 px scroller;
  its Range and Default cells end at 569 and 655 px on a 390 px screen.
- Fix: under 40rem each row stacks, as the datasets table does: the
  setting's name, what it does, then "Range: …" and "Default: …"
  (methods.css; `data-label` on the two cells; one rule per row).
- After: the table 314 px in 314; every cell inside the screen.

## ME-07 (also: MO-19)
- Reproduced: yes. A variables row: the symbol 105 px, the meaning 101 px,
  the table 360 px in a 314 px box; a row 129 px tall.
- Fix: under 40rem each row is a two-column grid: the symbol, then its
  meaning, units and source under one another beside it (nau.css).
- After: the meaning 296 px; the table fits; the same row 95 px.

## ME-08 (also: none)
- Reproduced: yes. Season cells 53 px tall ("2023-" / "24"), the table
  339 px in 332.
- Fix: the record table is `mt-rec`; its seasons take non-breaking
  hyphens (so "2024-25 and 2025-26" wraps only at its spaces); its
  number heads may wrap (methods.html, methods.css).
- After: the season cells 33 px; the table 332 in 332.

## ME-09 (also: none)
- Reproduced: yes. The Scoring list's values 166 / 99 / 33 px at 100 /
  130 / 160%.
- Fix: the kit's key-value grid gives its label column at most 40%
  (`fit-content(40%)`, ui-kit.css), so a long label wraps instead of
  starving the value.
- After: the values 185 / 170 / 156 px.

## ME-10 (also: none)
- Reproduced: yes. One fold title starts under its chevron at 100% ("A
  newest week that reads 0 ..."), ten at 160%.
- Fix: `.uk-fold-sum` takes `flex:1 1 0`, so the title wraps beside the
  chevron (ui-kit.css).
- After: none at 100% or 160%.

## MO-23 (also: none)
- Reproduced: yes. /model/pf2s at 390 px: the harmonic's labels at 8.3
  px; "s ∈ {A, B}" broken over two lines.
- Fix: the harmonic sits in a `.figscroll` region, as the other drawings;
  "s ∈ {A, B}" and "share A / (A + B))" are `.nw` spans (the class the
  math already has) (diagrams.html).
- After: the labels at 15.5 px; the set on one line.

## DA-10 (also: none)
- Reproduced: yes, with a 77-character name. 1280 px: the row's actions
  break onto two lines (the row 65 px). 390 px: the browser heading is
  352 px wider than its box (the card scrolls sideways 339 px). 1280 px
  at 160%: the page scrolls sideways 328 px.
- Fix: the name (`td.dsname`) and the browser's heading wrap anywhere;
  the row's actions keep one line (`.dt-rowacts` nowrap in the table)
  (nau.css).
- After: the actions on one line; the heading and the card 0 px over;
  the page 0 px over.

## DA-11 (also: none)
- Reproduced: yes. 768 px at 160%: the page scrolls sideways 793 px.
- Fix: `#datasets .tablewrap` scrolls itself and is positioned, so the
  table's hidden "Actions" header stays inside it (nau.css).
- After: 0.

## Checks
- New `app/tests/test_phone_tables.py` (7): all fail on c10d257 and pass
  here (the rules each fix rests on; the measurements above are the
  browser half, as G13's tests are).
- Pins of the old markup, updated: test_fewer_marks reads two settings
  defaults as `<td data-label="Default">…</td>` (ME-06's label); the
  harmonic's scroller is named "Harmonic figure (scrolls)", so
  test_theme_and_harmonic still counts the figure itself once per page.
- ruff clean. Full suite (FLUBNF_HUB=/nonexistent): 3592 passed, 155 skipped, 0 failed.
- Invariance: not needed (stylesheets and templates).
- Windows: CSS and markup only.

## Patch
G20/proposal.patch (git diff origin/dev...proto/G20-A)
