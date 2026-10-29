# G18: PR (B)
PR: https://github.com/elyfmiller/flubnf/pull/73 (fix/G18-home-map-take2 into dev); #72 is closed: its branch carried a merge of dev authored as Claude (my mistake: the merge ran without Ely's identity; the clone's local config now names Ely, so it cannot recur), and a force push is refused here, so the same two commits went up on a fresh branch.
Head: d52a422c7dada3b1b08d48542a575a38da6dc9cf (the fix e2a2fee with its tests and the Status cell; the cell set to #73)
Base: dev c423847 (G17 merged); dev's later team-notes commit is not merged in (dev asks no branch to be up to date).
Full suite on e2a2fee: 3589 passed, 154 skipped (the two test_doctor failures are this container's Python 3.13). ruff clean.
No run-path file is touched, so no output check.
Live: a server from the branch with a US-only run, an Arizona and New York run and all-53 runs; every bug and variant as in the PR's Checked (1280 light, dark, Dracula, Nord; 390 dark with touch; the keyboard walk; the report page without a skip link).
For Ely (from A's review): 490cf08, the merge of dev on #70's branch, is authored as Claude and is in dev's history; A reported it.
