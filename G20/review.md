# G20: review (A)
PR #75, head fcca194.

Approve.

- Commits: e43b5e8 and fcca194, both authored and committed as Ely F.
  Miller <efm46@nau.edu>, no trailers; the PR body has no footer.
- The diff is the decision (combined, as revised in ced40fd): B's patch;
  ME-07's phone grid flows down the second column (`grid-row:span 3` on
  the symbol, no `grid-column`), so test_reading_column passes;
  test_theme_and_harmonic counts the figure by `Seasonal harmonic:`.
  The Status cell reads "fixed in #75".
- Tests on the head: test_phone_tables, test_console_qol,
  test_fewer_marks, test_theme_and_harmonic, test_reading_column,
  test_ui_layout, test_display_themes, test_pages, test_data_view,
  test_a11y_modes: 152 passed. ruff clean.
- Live, Chromium, a server from the head with one stored dataset under a
  77-character unbroken name:
  - HM-06: Home's drawing scrolls at 390 px with the cue, tabindex 0;
    at 1280 px no scroll, no cue.
  - HM-09: at 130% and 160% the table (420 / 516 px) scrolls in a
    scroller with the cue inside the card (371 / 367).
  - ME-06: the settings table 314 in 314; every cell inside 390 px;
    Range and Default labelled (screenshot, light).
  - ME-07: the Variables table 314 in 314, the symbol beside its
    meaning, units and source under it (screenshot, dark at 160%).
  - ME-08: the record 332 in 332; "2024‑25 and 2025‑26" breaks only at
    its space.
  - ME-09: the Scoring values 185 / 170 / 156 px at 100 / 130 / 160%.
  - ME-10: no title below its chevron at 100% or 160% ("A newest week
    that reads 0, collapses, or was not reported" wraps beside it); on a
    desktop the fold badges stay 8 px after their titles.
  - MO-23: /model/pf2s at 390 px, the harmonic's labels 14 px, "s ∈
    {A, B}" on one line; 560 px wide on the desktop as before.
  - DA-10: Forecast, Replay and Delete on one line at 1280, 768 (160%)
    and 390 px; the long name wraps; no sideways page scroll.
  - DA-11: 768 px at 160%, the document 0 px over.
  - Light 100% and dark 160% at 390 px: Methods and Home 0 px over.
