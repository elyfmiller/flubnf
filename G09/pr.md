# G09: pr (A)
PR: https://github.com/elyfmiller/flubnf/pull/58
Head: 9956678c919c1e67f03ca0b95febcbb471404d29
Branch: fix/G09-retro-progress (from origin/dev 68816e0)

Changes after the decision: two test checks from B (RE-06: the form fields and no Resume once nothing is added; RE-03: ?rescore=1 while live). G08 conflict resolved as decided (`allow_aggregate=scoreable and not live`).
Full suite on the branch: 3514 passed, 155 skipped. Live re-check on the branch: all six as in the PR body.

## Answer to review (B), request 1
Done in 9956678 (pushed; head now 9956678):
- `retro_prep._job_covered`: a job with `inputs` None (a sealed record's)
  covers its root.
- `test_a_replay_over_a_sealed_season_leaves_the_seals_page_whole` now
  finalizes the seal, removes its aggregate cache (stale), and visits
  once, which makes the sealed job (inputs None). It then makes the
  aggregate fresh, as an in-request build does, and asserts nothing is
  pending, so the next visit goes through `_job_covered`. That visit
  returns 200, and again during a replay over the seal. Without the
  guard the second visit raises the TypeError.
- I could not get the 500 live with my seal copy: its aggregate is never
  written, so every visit stays on the pending branch. Your reseal case
  goes through the same `_job_covered` line the test drives.
Full suite on 9956678's tree: 3514 passed, 155 skipped. PR body updated.
