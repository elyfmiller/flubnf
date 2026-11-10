# G22: review (A)
PR #80, head d5220ae.

Approve.

- Commits 63612a1 and d5220ae: authored and committed as Ely F. Miller
  <efm46@nau.edu>, no trailers; the PR body has no footer.
- The diff is the decision (B's patch): routes/shell.not_found_page,
  registered with add_exception_handler (server.py's own names unchanged,
  test_ui_layout passes); /model/<unknown>, the unknown replay (to
  /retro?dataset=<id> when the dataset exists) and the season report's
  refusal as Output's notice; OU-16's path defaults, the real-day check
  and the missing archive's 404; SB-16's "no sandbox model named". Status
  cell "fixed in #80".
- Tests on the head: test_error_pages, test_ui_layout,
  test_output_by_date, test_browse_safety, test_busy_guard,
  test_models_tab, test_state_folder_protect: 101 passed. ruff clean.
- Live, a server from the head (8813), browser Accept: /model/nope,
  /nope, /retro/dataset/nope/<stamp>, /retro/2025-26/report each 404, a
  page of the console under its tab; /api/nope still {"detail":"Not
  Found"}; /output/download with no path 404 notice; /output/reveal with
  no path 303 to /output; 2026-13-45 400; the missing archive's view and
  download both 404; /sandbox?model=del_me "Not opened: no sandbox model
  named 'del_me'".
- Not blocking: for a season name of the wrong shape, the season report's
  notice leads to /retro under the words "Open the season"; only a
  hand-typed address gets there.
