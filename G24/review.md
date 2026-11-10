# G24: review (A)
PR #82, head c56807f.

Approve.

- Commits 0954cac and c56807f: authored and committed as Ely F. Miller
  <efm46@nau.edu>, no trailers; the PR body has no footer.
- The diff is the decision: DA-04 `#main` on both redirects and the
  count words; DA-05 the hint beside the badge, `pull_first` and the
  check's `behind` with the comparators, the pull's "comparators added";
  DA-07 the readers' optional `path`, the live entry in the hub card's
  words and the Source tile; DA-19 `_season_vars` read by the strip and
  the chart; DA-23 " · as of <snapshot>". Status cell "fixed in #82".
- Tests on the head: the data, dataset, pull, hub, marks, layout,
  season-palette and pages tests (and test_data_page_fixes): 630 passed.
  ruff clean.
- Live, a server from the head (8814) on the private hub copy (archive
  through 2026-10-17, target-data through 2026-10-24, no model-output):
  - DA-04: the upload form's Save only lands at #main, the notice at
    18 px, "1 warning."
  - DA-05: "baseline, ensemble missing Update data adds them."; Update
    data gold and the check quiet, before and after a check.
  - DA-07: "*2026-10-24 (target-data, not archived)", 2026-10-17, ...
  - DA-19: the strip and the chart agree per season at the latest vintage
    and with 2024-03-02 open (2023-24 #2B9D2B in both).
  - DA-23: "West · flu · as of 2023-11-25" and "... as of 2023-12-02".
