# G09: compare (A)

B's patch applied on 6f9a86f; my test file run against it (renamed helpers
aside): the RE-03 and seal-page tests fail there, the rest agree.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| RE-03 | `_replaying(root, season, archive)`: live only when the page shows the live tree; no job, no aggregate, and no "Scoring failed" or "No scoreable weeks yet" while the replay runs | `live` from the status alone; no job, no aggregate | **A**. Two failures in B's, both seen and tested. (1) A live replay whose weeks could score already shows "Scoring failed. scored zero cells with no exception. probe cell …": nothing is scored until the worker finalizes, so the zero-cells probe fires. I saw it live, and `test_the_page_of_a_running_replay_shows_its_live_card` with baseline rounds present catches it. B's test stubs the hub away, so it lands on the calm path. (2) A fresh replay over a sealed season: the page shows the seal (more weeks). Once a seal job exists (`inputs` None), a status-only `live` sends it to `_job_covered`, which raises `TypeError: '>=' not supported between NoneType and int`: a 500. `test_a_replay_over_a_sealed_season_leaves_the_seals_page_whole` fails on B's. |
| RE-05 | `_card_root(season, status)` | `shown_root(season)` (reads the status itself) | Equal. Same rule; mine reuses the status the caller already has. |
| RE-06 | Resume also for done with added weeks | the same plus `not is_seal` | Equal in effect: with no live record, `resume_form_fields` returns None, so a seal never gets the button either way. B's test is the more precise one: it checks the hidden fields and that there is no Resume once nothing is added. |
| RE-07 | distinct as-of in the pooled frame when figures are available | the same | Equal. |
| RE-08 | the segment ends at the heartbeat when `effective_status` is interrupted | the same, via `worker_dead or is_stale` | Equal. |
| RE-09 | `worker_gone` reuses `flubnf.cli._pid_alive` (and `_pid_alive_windows`, already tested in test_app_launch); tests use a real reaped process and a real live child | a new `_pid_alive` in retro.py; the test patches it | **A**. Criterion 4: no second liveness check. B's Windows branch treats an OpenProcess refusal (access denied) as dead. cli's treats it as alive, and cli's also checks the exit code, which B's skips. My tests run the real check end to end, including a live other-process worker (the CLI case). |

Vote: combine. A's code and tests, plus from B:
- RE-06: the precise form check (`class="resume-run"`, the hidden fields)
  and the negative case: no Resume once nothing is added;
- RE-03: the `?rescore=1` visit while live also starts no job.

The combined version is almost entirely A's, so A implements. It must
merge origin/dev (G08 is in) and take G08's `usn.resolve` line as
`allow_aggregate=scoreable and not live`.

Vote (final): A. B voted A. The two test checks named above come in as
part of finishing the patch (step 4). They change no behavior.
