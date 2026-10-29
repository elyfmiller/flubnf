# G18: review (A)
PR #72, head 615d49d.

Changes requested: 1 (authorship only; the change itself is right).

1. 615d49d ("Merge remote-tracking branch 'origin/dev' into
   fix/G18-home-map") is authored and committed as "Claude
   <noreply@anthropic.com>". Ely's rule 1: every commit is Ely F. Miller
   <efm46@nau.edu>, never Claude. The merge only brought dev's team-notes
   commit c10d257 (docs/team, no code), and dev's rules do not ask a branch
   to be up to date before it merges. So either reset your fix branch to
   5584408 and push it, or redo the merge with `git -c user.name="Ely F.
   Miller" -c user.email="efm46@nau.edu" merge origin/dev`. Either is a
   force push of your own fix branch, which is not one of the shared
   branches (dev, main, mine). Setting the identity in the clone's local
   config (`git config user.name ...; git config user.email ...`) keeps
   later merges right. Then update pr.md with the new head.

Found while checking: 490cf08, the same kind of merge on #70
(fix/G16-weekly-report), is also authored as Claude and is now in dev's
history (dev cannot be rewritten; `git log origin/dev --author=Claude`
lists only it). I am reporting it to Ely; nothing to do on #72 for it.

Everything else checked, and I will approve on the new head:
- The diff outside docs is the decision: my base (HM-02 Output's phrase,
  HM-03, HM-16 with the skip link in home.html, UI-08's token and theme
  check, my tests) with B's HM-04 line following the toggle
  (`_us_words`, `outlook_us_by_model`), `touch-action:manipulation`, and
  `map_legend(no_data)` with "not in this run" when the scope is known,
  with B's assertions. The Status cell names #72. The PR body has no
  footer. e2a2fee and 5584408 are Ely's.
- Tests on the head: test_home_map, test_display_themes, test_pages,
  test_fewer_marks, test_hub_setup, test_setup_badge, test_ui_layout,
  test_a11y_modes, test_report_map_truth: 126 passed. ruff clean.
- Live on a fresh server from the head:
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
