# G09: compare (B)
A's patch applied on 6f9a86f (scratch tree): its 9 tests and the retro
files (run_timing, results_prep, report_parity, retro_eta, resume_rerun,
season_run_marks, ui_layout, retro_archive, app_launch): 302 passed, 6
skipped; the F gate clean. The two prototypes fix the same six symptoms
the same way; the differences are in the details below.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| RE-03 | `_replaying(root, season, archive)`: the live tree of an active season only; no job, `allow_aggregate=not live`; while live, neither the "scored zero cells" alert nor the "No scoreable weeks yet" empty state; the seal's page stays whole when a replay runs over it (a test pins the `_job_covered` None comparison) | `live` from the season's status alone; no job, no aggregate; the alert and the empty state untouched | A's (1, 2): B's page of a replay over a seal would skip the seal's own US row and show the unsettled state while nothing scored yet; A's keys on the live tree and hides the two states that mislead mid-replay. |
| RE-05 | `_card_root(season, status)` for the progress poll and the index card | `shown_root(season)`, the same rule, for the same two readers | Equal (A's takes the status it already has). |
| RE-06 | resume_fields also for done with added weeks | the same, not for a seal | Equal. |
| RE-07 | the pooled frame's distinct as-of count when the figures are available, else 0 | the same | Equal. |
| RE-08 | the open segment ends at the heartbeat when `effective_status` says interrupted | the same, keyed on `worker_dead or is_stale` | Equal; A's reads the one status function (4). |
| RE-09 | `pid` in the record; `worker_gone` through the existing `flubnf.cli._pid_alive` (its Windows branch checks OpenProcess and the exit code, with tests in test_app_launch); tests with a real ended child and a live one | `pid` in the record; a new `retro._pid_alive` (OpenProcess only on Windows) and `worker_dead`; tests with `_pid_alive` patched | A's (4): one liveness check in the code base, the sturdier Windows branch, and tests on real processes. |

Vote: A.
