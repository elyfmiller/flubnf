# G21: compare (B)
A's proposal read in full; A's patch applied on origin/dev 8cb3f7d (clean);
its four tests with test_storage, test_reclaim and test_state_isolation:
56 passed; ruff clean. The two proposals take the same route on every
bug; they differ on the seals' fallback, the protected row's rendering,
an unreadable status file, and words.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| WI-04 (RE-28) | the four paths under APP_STATE | the same; RETRO_RESEAL and RETRO_SEAL through `runs.sealed_root(name)`: the state folder's copy, else the checkout's when the state folder was moved and holds none (the hint's "shipped read-only seals can keep a checkout fallback") | B, criterion 1 and 2: with FLUBNF_STATE_DIR set, A's console loses the sealed records that ship in the checkout's app/state (Home's and Methods' figures, Storage's Protected list, the seal's protection); B's finds them. Unset, both are the checkout's app/state. Both leave the Sandbox for Ely, for the same reason. |
| ST-06 | reclaim's roots gain APP_STATE/retro_reseal; `_storage_protected` asks reclaim.is_protected; a protected workroot's row shows the lock badge in place of Delete; the refusal's words unchanged | reclaim's roots gain the reseal (both places) and `extra_protected_roots()`; the same barrier call; the row's Delete off with the reason (busy_act); the extra root also listed under Protected; the refusal names FLUBNF_PROTECT_ROOTS; the Protected tip adds a clause | A for the row (criterion 4 and 5: the lock badge the Protected section already uses, no new words, and no second listing of a workroot the total already counts). B for the refusal sentence, if any words: A's tells a crafted delete of a FLUBNF_PROTECT_ROOTS tree that "the sealed validation record and the hub clone" are protected. A's call. |
| ST-07 | `workroot_failures`: any cell not "ok", an unreadable or non-dict status file counts as a failure | `workroot_failed`: any cell not "ok" in the top level's or pf2s/ pf_status.json; an unreadable file is skipped | A for the unreadable file (criterion 1: doubt never deletes); B for pf2s/ (a research run's second status file, as `workroot_intermediates` already scopes pf2s/). Combine the two. |
| OU-15 | a .csv under submission/ or export/ | the same | Equal. |

Tests: A 4 in test_state_folder_protect.py, B 6 in test_state_dir_protect.py
(the seal fallback and the reseal barrier have their own). A's note on
engine-public (reclaim.py's docstring, sandbox.py) applies to both.

Vote: combine: B's patch as the base (sealed_root and its test, the
reseal in both places, OU-15, the tests), with A's protected row (the
`protected` flag and the lock badge in runs.html, no Protected-section
entry for the extra root, the Protected tip as it was) and A's rule that
an unreadable pf_status.json counts as a failure, keeping B's pf2s/ scope.
The refusal sentence: A decides (B's names the variable).

## After A's compare

A's two findings stand, checked on my own servers: `busy` on a protected
row also draws runs.html's "running now" badge (a wrong statement, mine);
and `sealed_root`'s fallback would read the checkout's real records in a
suite run on Ely's machine and not on CI, and would part from
site_build.py's `APP_STATE / "retro_seal"`. A's row (the lock badge, no
words) and A's seal paths are right.

Vote (final): combine: A's patch, with B's pf2s/ scope in the failure
check (an unreadable status file still keeps the trees) and B's stray-CSV
assertion in the download test. The refusal sentence stays as it is. B's
`test_reclaim_protects_the_production_reseal_as_storage_does` can ride
along if A's test does not already cover reclaim.is_protected on the
reseal; A's call.
