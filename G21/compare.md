# G21: compare (A)

B's patch applied to origin/dev 8cb3f7d on a scratch worktree: its 6 tests
pass; served on 8813 with the G21 run state and FLUBNF_PROTECT_ROOTS
naming one workroot.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| WI-04 (RE-28) | retro roots, both seals and engine_update.json = `APP_STATE / name` | the same for retro/ and engine_update.json; the seals through a new `runs.sealed_root`: the state folder's, else the checkout's | **A.** Unset, the two are the same. Set, which today means the test suite (LAUNCHERS.md: "test hook"), B's fallback reads the checkout's real records whenever the machine has them: with `app/state/retro_reseal/2023-24` in B's scratch checkout and FLUBNF_STATE_DIR at an empty folder, `RETRO_RESEAL` -> `.../scratch21b/app/state/retro_reseal`. So on Ely's machine an unpatched reader in the suite sees the production record, and on CI it does not: TS-01's kind of machine dependence, which conftest's "no test may touch or depend on the real install" forbids (criterion 2). A's adds no helper (criterion 4) |
| WI-04, the Sandbox | for Ely (the runner reads ~/Students/<name>/sandbox) | for Ely (SANDBOX.md; the runner) | equal |
| ST-06, the barrier | reclaim's roots + reseal; Storage asks reclaim.is_protected | the same, both seal locations deduplicated | equal |
| ST-06, the row | the Protected section's lock badge in place of Delete; no new words | `busy` + `_busy_why("protected")`: Delete off with a "?" sentence; the extra root listed under Protected; the Protected tip gains a clause | **A.** On 8813 B's protected row reads "Round 2026-10-24 (as of 2026-10-17) **running now** ... Delete ? That tree is protected (the sealed records, the hub clone and a folder named by FLUBNF_PROTECT_ROOTS are never deletable from the interface)." `busy` also draws runs.html's "running now" badge (line 281), which is false for a protected run (criterion 1: a new wrong statement). It also puts an environment variable's name and a "?" on a student's page, a "Protected folder (20261110T...)" entry and a longer tip (criterion 5). A's row: the lock badge, no Delete, nothing else |
| ST-07 | `workroot_failures`: the top level's pf_status.json; an unreadable file counts as a failure (keep) | `workroot_failed`: the top level's and pf2s/'s; an unreadable file is skipped (no failure: delete) | **combine.** B's pf2s/ scope: a research run's pf2s/ cells are intermediates too, and A's check misses their failures (criterion 1). A's rule for an unreadable status: never a reason to delete |
| OU-15 | .csv under submission/ or export/ | the same | equal; B's test also checks a stray CSV outside both (take that assertion) |

Vote: combine: A's patch, with B's pf2s/ scope in the failure check (an
unreadable status file still keeps the trees) and B's stray-CSV assertion
in the download test.

## After B's compare

B's WI-04 case: with FLUBNF_STATE_DIR set, A's console "loses the sealed
records ... (Home's and Methods' figures, Storage's Protected list, the
seal's protection)". Checked on 8cb3f7d: no route reads the seals for
Home's or Methods' figures (those are template literals, held to
oracle_text.RECORD by test_pages). The readers are retro_seasons (a
season with no lab run shows the sealed record) and Storage's Protected
list. The site build reads `APP_STATE / "retro_seal"` (site_build.py:78)
and reclaim `APP_STATE / ...`, with no fallback, so B's fallback would
leave the retro pages and the site build reading different trees under a
moved state folder: WI-04's disagreement in another place. With A's, a
moved state folder holds everything the console reads or writes, and the
suite never reads the checkout's real records.

Vote (final): combine: A's patch, with B's pf2s/ scope in the failure
check (an unreadable status file still keeps the trees) and B's
stray-CSV assertion in the download test. The refusal sentence stays as
it is (reached only by a crafted request now that the row has no
button).
