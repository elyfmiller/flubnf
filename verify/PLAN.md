# Re-check of G01-G10, then G11-G20 (A)

Ely, 2026-10-29: "usage is back. check in with public repo to see if your
first 10 fixes actually addressed the flags that raised those.
Independently verify and have fable agent do the same, then both of you
independently take the next bath of 10 issues (first 10 done, second 10
takes us to 20/35). If new findings come from reviewing the first 10
batch, that takes priority first"

## V: the re-check (both, independently)
1. On the latest origin/dev, take every bug of G01-G10 (53 bugs) and every
   `also` variant, and re-run its steps from bug-hunt-2026-10-25.json
   (live app, tests, or both). Do not read the other's verify files until
   your own is pushed.
2. Write `verify/G01-G10.md` on your coordination branch: one row per bug,
   with a verdict (`fixed`, `not fixed`, `partly`, `regressed`, `for Ely`
   as recorded in its Status), how you checked it, and what you saw. Then
   a "New findings" list: anything a G01-G10 fix left undone, broke, or
   that dev's later commits broke, each with steps and the root cause.
3. When both are pushed, each writes `verify/compare.md`: findings that
   agree, findings only one saw (re-checked by the other).
4. Every finding both accept becomes a fix group V01, V02, ... (one per
   original group touched) and runs the usual loop (proposal, compare,
   decision, PR, review, CI, merge) before G11. Decider: the decider of
   the original group (A for odd, B for even). No findings: straight on.

## Then G11-G20, the usual loop
A decides odd groups, B even. Both stop after G20 merges (its done.md)
and report to Ely, as after G10.
