# G17: PR (A)
PR: https://github.com/elyfmiller/flubnf/pull/71 (fix/G17-hub-setup into dev)
Head: 55f73c8b50daa052b2081941b5cbee3b0e91fe2e (two commits: the fix with its tests and the Status cell; the cell set to #71)
Base: dev 2379a2e (G16 merged). B's patch applied cleanly; A's DA-22 in place of B's remembered verdict, with A's test in place of B's.
Full suite on c8e26f0 (the fix): 3585 passed, 155 skipped, 0 failed. ruff clean.
Output check (/run is touched): an all-53 Groundhog run on 2026-10-17 gives the same submission file on dev and the branch (md5 56da9201b416eb5c80317c849b55168e).
Live on servers from the branch: no hub and no BioNetGen (Home, Data, Forecast, the check, Update data, a refused run), a private hub copy (DA-22), and the slow probe (HM-13); as in the PR's Checked.
