# G18: review (A)
PR #73, head d52a422 (replacing #72).

Approve.

- The one change asked on #72 is met: #73 carries no merge of dev; its
  three commits (e2a2fee, 5584408, d52a422) are authored and committed as
  Ely F. Miller <efm46@nau.edu>. Its app/ files are byte for byte #72's
  head, which I checked live. The Status cell reads "fixed in #73". The
  PR body has no footer.
- The diff outside docs is the decision: my base (HM-02 Output's phrase,
  HM-03, HM-16 with the skip link in home.html, UI-08's token and theme
  check, my tests) with B's HM-04 line following the toggle,
  `touch-action:manipulation`, and `map_legend(no_data)`.
- Tests on that code: test_home_map, test_display_themes, test_pages,
  test_fewer_marks, test_hub_setup, test_setup_badge, test_ui_layout,
  test_a11y_modes, test_report_map_truth: 126 passed. ruff clean.
- Live on a fresh server from it:
  - HM-02: "US categorical forecast · Round 2026-10-24 (as of
    2026-10-17)".
  - HM-04: US alone: "Coverage 0 of 52 · United States stable 45%".
  - HM-18: Arizona and New York: the legend "not in this run".
  - HM-03: the report removed: 0 "click for details", no MAP_LINK, no
    click clause.
  - HM-16: Tab: "Skip the map", Alabama, Alaska, Arizona, Arkansas,
    California, Colorado, Connecticut.
  - HM-07: a swipe on the map at 390 px scrolls 520 → 761.
  - UI-08: Dracula chips rgb(214,188,250).
  - No sideways scroll at 390 px.
- For Ely: 490cf08 (#70's merge of dev, authored as Claude) is in dev's
  history; reported, not rewritten.
