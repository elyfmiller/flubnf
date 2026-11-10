# G32: pr (A)
PR: https://github.com/elyfmiller/flubnf/pull/94 (fix/G32-output-polish into dev)
Head: 4c777de6787c56498f07df2de9090492d4767f99 (abd374fb the change, 4c777de6 the Status cell)
Base: dev e068a540 (#91 merged)

The decision as written: A's patch, plus the two notes from decision.md: a node test of the countdown script (test_the_countdown_keeps_time_and_reloads_once_per_change) and one kept entry per file, its newest version. The G06 pin in test_which_run_shows moves to the new line, which keeps the rule; the PR says so.

Checks: ruff gate clean; Output, which-run, kit, layout, marks and pages tests 163 passed; full suite 4688 passed, 216 skipped, 0 failed. Live: Output after a relaunch 0.19 to 0.28 s (dev 0.82 s, same state); the three-line "i" at 1280 light and 390 dark; the rows' labels name each file; the countdown in Chromium with a run-forward clock, one reload at the 12-hour mark.

B: please review 4c777de6 and write G32/review.md.
