# G32: review (B) of #94, head 4c777de6

Approve.

Read: the whole diff against dev e068a540 (7 files). It is the decision as written: A's patch, with the two optional notes taken (a node test of the countdown script; one kept entry per file, its newest version), and the G06 pin in test_which_run_shows moved to the new line; the Status cell reads "fixed in #94".

Checks on the PR head:
- ruff (the gate) clean.
- Output, which-run, kit, layout, marks and pages tests: 180 passed.

Live (the PR tree over a state of 35 cloned Groundhog workroots, one round open; Chromium on a controlled clock):
- OU-07: Output after a relaunch 3.9 s with no kept checks, then 0.27 s on the next launch; hubcheck_results.json in the state folder.
- OU-10: the title's "i" is three lines; the marks on the page are that "i" and one "i" per failing line or card.
- OU-13: by the tests (each row's Download and Show in folder name their file).
- OU-14: the badge reads "1 day 17 h left" and counts down on the clock; one reload at the urgent flip and none a minute later; one at the close and none after (the server's real clock kept the round open, which is the clock-ahead case the once-per-flip guard is for).
- OU-17: the gone run's notice reads "About no run 20261025T184517-9a04d9 is recorded here".
- CI on 4c777de6 was still running when this was written; A merges once it is green.
