# G16: PR (B)
PR: https://github.com/elyfmiller/flubnf/pull/70 (fix/G16-weekly-report into dev)
Head: 490cf08cdfbcb7b17adbed7bc70674ca83a93c32 (the fix eeca7c2 with its tests and the Status cell; the cell set to #70; origin/dev merged in)
Base: dev 55fd84e (G15 merged), then origin/dev 399f694 merged.
Full suite on eeca7c2: 3575 passed, 154 skipped (the two test_doctor failures are this container's Python 3.13). ruff clean.
Output check (pipeline.py is touched): an all-53 Groundhog run on 2026-10-17 gives the same submission file on dev and the branch (md5 56da9201b416eb5c80317c849b55168e).
Live: a server from the branch with the earlier runs (all-53, modified Ohio, vintage): every bug and variant as in the PR's Checked, at 1280 light and 390 dark.
