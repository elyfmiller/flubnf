# G15: PR (A)
PR: https://github.com/elyfmiller/flubnf/pull/69 (fix/G15-deleted-runs-labels into dev)
Head: 5ec0be5f23ba1af407f54be874726b3b6346dada (two commits: the fix with its tests and the Status cell; the cell set to #69)
Base: dev 285a3d4 (G14 merged). The decided patch (A's) applied cleanly.
Full suite on 58edde6 (the fix): 3569 passed, 155 skipped, 0 failed. ruff clean.
Output check (runs.py is on the list): an all-53 Groundhog run on 2026-10-17 gives the same submission file on dev and the branch (md5 56da9201b416eb5c80317c849b55168e).
Live on a fresh server from the branch: every bug and variant as in the PR's Checked.
