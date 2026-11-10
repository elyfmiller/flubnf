# FluBNF fix run, 2026-10-25 bug hunt: final (B)

Written by B at the end of the run. The record is each group's Status cell in `docs/team/bug-hunt-2026-10-25.md` on `dev`, its pull request (#50 to #97) and the dated "Now" and "Open" entries of `docs/team/app.md` (#99); this file sums them up.

## Fixed

35 groups, 35 pull requests into `dev` (#50 to #59, #65 to #71, #73 to #75, #79 to #83, #85 to #88, #90, #91, #94 to #97; #64 was A's re-check of G01 to G10), each reproduced on `dev` first, reviewed by the other session, and merged as a merge commit after every check was green on its head.

Of the 208 bugs, 197 are fixed in full: 24 of the 25 S2, 77 of the 86 S3, 96 of the 97 S4. Two more are fixed but for a part that did not reproduce (below), and nine are fixed but for a part that needs Ely's call (below). No forecast number, knob default, submission file name or format changed; every group that touched the run path passed the output check (two identical all-53 Groundhog runs on 2026-10-17 gave byte-identical submission files on the base and the fix, md5 56da9201b416eb5c80317c849b55168e throughout). The 18 medium-confidence bugs were each reproduced before anything changed.

## Left for Ely

Nine bugs are fixed but for one part each; the Status cell and app.md's Open entry of 2026-11-10 say why:
- DA-02 (G04, #53): one week of a 200-group dataset still takes minutes (the walk's speed or an upload cap).
- RE-17 (G08, #57): a dataset's national row is a spelling by decision (2026-09-24); the template's "Overall" is not one of them.
- MO-20 (G12, #66): the blend's members and the seasons or cells behind 0.719 and 0.704 are in no document.
- SB-12 (G14, #68): the refusals' words changed; the one-run engine lock stays.
- OU-03 (G16, #70): two shipped runs of one week still save their reports under one name (the decided name is the reference date's).
- UI-03 (G19, #74): the weekly report keeps #A87300 for the Groundhog on light cards.
- WI-04's Sandbox part (G21, #79): whether FLUBNF_STATE_DIR should carry the checkout's sandbox/ folder.
- SB-10 (G25, #83): whether the private engine has a likelihood for rates (it cannot be run here).
- FC-13 (G26, #85): the run-wide setting keeps precedence over a state's own Data issues choice, as the engines apply it.

Also for Ely:
- The fix branches whose delete the git proxy refused (fix/G21-state-dir-protect to fix/G35-cross-page, and fix/G35-run-notes) and the two coordination branches, if they are still there, are left to delete.
- Two test races on dev, noted in #90 and #94: the Forecast page briefly shows "engine build unknown" while the warm thread resolves the public engine's build before the suite pins the private one. For the App lane's conftest, not this run's.

## Not reproduced

- WI-08's shipped snapshot badged "not archived" (G17, #71): the badge stays hidden on dev; the rest of WI-08 is fixed.
- ME-11's bank half (G11, #65): with the bank at none the console runs the bare analogue, as its help says; the console half is fixed.

## The state of dev against main

`dev` (73908e6c, #99 merged) carries the 35 fix pull requests and the closing notes, beside the other lanes' merges of the same days (the engine switch #61, the App lane's review fixes #84, #89, #92, and their notes). Against `origin/main`: dev has 121 commits main lacks, and main has 1127 commits dev lacks, so the two histories have diverged beyond this run; Ely merges `dev` into `main`, and this run opened no pull request into `main`.

Both coordination branches stay on origin for Ely to delete, with the fix branches named above: a pushed delete is refused by the git proxy here.
