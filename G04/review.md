# G04: review (A)
PR #53, head c1090b4 (e6e9e99 the change, c1090b4 the Status cell).

Approve.

What I checked
- The app diff is A's proposal patch plus B's `test_busy_guard::test_the_groundhog_stops_between_locations_when_asked` and one trailing blank line trimmed in test_datasets_ui.py, as decided (compared line by line against proto/G04-A). Author and committer Ely F. Miller <efm46@nau.edu> on both commits; no attribution lines or forbidden words in messages, diff or PR body; no footer; Status cell `fixed in #53; DA-02 for Ely: ...` as decided.
- On the head: test_busy_guard, test_custom_retro, test_custom_run, test_datasets_ui, test_ui_layout, test_run_integrity: 188 passed. Every test file that drives the Groundhog, `_run_all`, the stop route or the replay (43 files): 833 passed, 8 skipped, 2 failed: `test_server_hardening::test_data_pull_allowed_during_pure_fitting` and `::test_update_data_says_in_plain_words_whether_the_data_moved`. They pass alone (21 passed) and fail the same way on dev 695155d with the same file order: an order dependence of that file, not this PR's (the suite's own order passes). `ruff check --select F821,F823,F811,F401 app/ui` clean.
- Live, a server from the head (FLUBNF_HUB the hub clone), the same script as my reproduction on dev:
  - FC-01: all 53, Groundhog only, Stop at 1 s: recorded `stopped`, no submission files (dev: 18 s more, ok, 1 file).
  - WI-03: the template dataset's 104-week Groundhog replay, /run/stop at week 38: the replay recorded `stopped, 62 of 104` (dev: `done, 104 of 104`).
  - DA-14: the delete during the replay: "wiretpl not deleted: a replay on it is in progress."
  - DA-02: the 200-group replay, its own Stop 15 s in: the engine free after 2 s (dev: still busy after 120 s).
  - WI-10, Chromium: a Groundhog hub replay of 2024-25 (Vermont); /forecast, Run models, the modal ("This will stop the running retrospective 2024-25."), Stop run and proceed: landed on /forecast with "Stopping 2024-25 after the fits in flight." (dev: no notice anywhere).
