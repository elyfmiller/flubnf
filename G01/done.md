# G01: done (A)
PR #50 merged into dev as a merge commit: 301466c7e3b61fe4c874f21d92fd83c9ad386c76 (head 6c96e45; all six checks green; B approved).
The fix branch could not be deleted from this session: `git push origin --delete fix/G01-test-hub-leak` is refused ("the remote end hung up"), while pushes work. Left for Ely to delete on GitHub (the merged PR's "Delete branch").
From here on, local test runs need no FLUBNF_HUB=/nonexistent: the suite pins the hub itself.
