# G09 retro-progress: proposal (A)
Base: origin/dev 6f9a86f

All six reproduced on dev 6f9a86f. Setup: Groundhog-only replays on a hub
with model-output/FluSight-baseline (my own sparse clone, so seasons
score). For RE-06, a second hub without the 2026-10-17 round: replay
2026-27 there, then relaunch on the full hub so the season gains a week.
For RE-05, a finished all-52 2025-26 replay copied into app/state/retro_seal.

## RE-03 (also: none)
- Reproduced: yes. During a 2025-26 replay, GET /retro/2025-26 showed
  "preparing results" on every visit and never the "Replay in progress"
  card. The finalize job reran as each new week landed.
- Root cause: routes/retro.py:869 `retro_results`. `_results_pending(root)`
  is true whenever a new week is newer than the caches, which is always
  true during a replay. So every visit starts `_ensure_results_job`
  (finalize: scoring, national aggregate, playback warm) and shows the
  preparing state.
- Fix: new `_replaying(root, season, archive)`: true when `root` is the
  live tree of a season whose status is active. While that holds:
  - no finalize job is started (the worker finalizes at the end), and the
    page renders from the caches it has, beside the live card
    (`prog`, already in the template);
  - `season_page_context` resolves the US row with
    `allow_aggregate=not live`, so no national aggregate is built in the
    request;
  - with no scores cached yet, the page shows neither the "Scoring
    failed. scored zero cells…" alert nor the "No scoreable weeks yet"
    empty state. Without this, the zero-cells probe fires and the
    page claims scoring failed while the replay is still running (seen
    live). The verdict block is simply absent until the replay finishes.
  - It applies only to the live tree. A replay over a sealed season whose
    seal still holds more weeks shows the seal's page exactly as dev
    does. A first cut keyed only on status hit a 500 here: a finished
    seal job has `inputs` None, and `_job_covered` compared None >= int.
    A test pins this.
- Tests: `test_the_page_of_a_running_replay_shows_its_live_card` (no job
  started, live card, no failure or unsettled text, with baseline rounds
  present so dev's probe would fire);
  `test_a_replay_over_a_sealed_season_leaves_the_seals_page_whole`.
- Risk: the season page of an active season only. No invariance check
  (no run path).
- For Ely: none.

## RE-05 (also: none)
- Reproduced: yes. A fresh replay over the sealed 2025-26 read "running ·
  31/31 · sealed" with ETA None while the live tree held 3 to 7 weeks.
  Stopped at 4 weeks, the card mixed the seal's weeks and relWIS with the
  live run's status, wall time and Resume.
- Root cause: retro_seasons.py:403 `_retro_progress` and routes/retro.py:125
  `retro_index` count done and read the head scores from
  `_season_root(s)`, which picks whichever tree has more weeks: the seal.
  Status, time and Resume come from the live record.
- Fix: `retro_seasons._card_root(season, status)` returns the live tree
  while its replay is active or has weeks, else `_season_root`'s choice.
  `_retro_progress` and `retro_index` use it, so a card's weeks, ETA,
  relWIS, Resume and status all describe one tree. With an empty live
  tree the seal speaks for the season, as before. The season page
  itself keeps `_season_root`.
- Tests: `test_a_replay_over_a_sealed_season_counts_its_own_weeks` (the
  progress, `_card_root`, and the /retro card text 1/… not 3/3; the seal
  again once the live tree is gone).
- Risk: cards of seasons that have both a seal and a live tree with weeks.
  Invariance: no.
- For Ely: none.

## RE-06 (also: none)
- Reproduced: yes. 2026-27 finished at 3 weeks, then the hub gained
  2026-10-17. The card read "complete · 1 week added · Weeks 3/4" with no
  Resume, and the form started at defaults.
- Root cause: routes/retro.py:136. `resume_fields` is built only for
  stopped or interrupted. `added` is computed after it, and a "done"
  status never gets the one-click Resume.
- Fix: compute `added` first, then offer `resume_fields` also when
  `status == "done" and added`. Resume runs only the added weeks; the
  existing run path already does this, and the badge's tip promises it.
  The season page's onward link already goes to the card, which now has
  the button.
- Tests: `test_a_finished_replay_that_gained_weeks_offers_its_resume`.
- Live: after the fix, the card's Resume form (its own recorded settings:
  custom Arizona+Texas, blend) ran only 2026-10-17, and the card turned
  4/4.
- Risk: none beyond the card. Invariance: no.
- For Ely: none.

## RE-07 (also: none)
- Reproduced: yes. The sealed 2025-26 page said "31 weeks scored" over 27
  scored as-of weeks; `?conv=pairwise` said 31 above "No scores under this
  convention".
- Root cause: routes/retro.py:1153 `"n_weeks": len(weeks) if scoreable`,
  which counts stored weeks.
- Fix: `n_weeks` is the number of distinct `asof` in the pooled scores
  frame when the convention's figures are available, else 0. The
  downloaded report reads the same context.
- Tests: `test_the_title_counts_the_weeks_that_scored` (three weeks
  stored, one with no baseline round: 2; pairwise without field data: 0).
- Live: "2025-26: 27 weeks scored".
- Risk: the title only. Invariance: no.
- For Ely: none.

## RE-08 (also: none)
- Reproduced: yes. After the console was killed, 2024-25 read
  "interrupted" with elapsed 266 → 276 → 286 → 296 s at 10 s intervals.
- Root cause: app/core/retro.py:250 `elapsed_now` adds `now - segment_start`
  for any recorded running or stopping status, even when the heartbeat
  shows the worker is dead.
- Fix: when `effective_status` is "interrupted", the open segment ends at
  `heartbeat_utc` (or at its own start if there was none). A live run
  still counts to now.
- Tests: `test_an_interrupted_replay_keeps_the_time_it_ran`.
- Live: 2024-25 (killed under dev) reads 20.7 s on two reads 15 s apart.
  After a kill -9 on the fix tree, 2025-26 holds 23.2 s.
- Risk: the shown wall time of dead runs only; the record is not
  rewritten. Invariance: no.
- For Ely: none.

## RE-09 (also: none; medium confidence)
- Reproduced: yes. kill -9 of the console mid-replay, then a relaunch in
  place: "running" with ETA 517 s for about 4 minutes (until
  HEARTBEAT_STALE_S). Run on another season was refused with "Not started:
  another season is replaying (2024-25)."
- Root cause: app/core/retro.py:240 `effective_status` only knows a dead
  worker by its stale heartbeat. The record never says which process
  wrote it.
- Fix: `_start_record` writes `pid` (os.getpid()). New
  `retro.worker_gone(meta)`: true when the record names a pid other
  than this process's and `flubnf.cli._pid_alive` (the existing
  cross-platform check; never `os.kill(pid, 0)` on Windows) says it
  ended. `effective_status` treats that as "interrupted" at once.
  Conservative choices:
  - our own pid, a record without a pid, or a recycled live pid all fall
    back to the heartbeat;
  - a CLI replay in another live process keeps running.
  The fix hint's boot id is not needed: a same-pid-after-reboot case
  (pid 1 in a container) equals os.getpid() and falls back to the
  heartbeat.
- Tests: `test_a_record_whose_worker_process_ended_reads_interrupted_at_once`
  (ended, own, live and no pid); `test_a_season_started_here_records_this_process`;
  `test_after_a_relaunch_the_dead_replay_frees_the_engine` (progress API
  interrupted with no ETA, /api/busy free).
- Live: kill -9 at 10/31, relaunch: the first read is "interrupted 10/31,
  23.2 s, no ETA". The 2026-27 card's Resume is accepted at once (no
  "another season is replaying") and finished.
- Risk: every status read of a record with a pid. The cost is one
  `os.kill(pid, 0)`, or OpenProcess on Windows. Invariance: no.
- For Ely: none.

## Checks
- 8 of the 9 new tests fail on dev 6f9a86f. The ninth (the seal's page)
  guards this change and passes on dev too. All 9 pass on the prototype.
- ruff (the test_ui_layout selection) clean.
- Full suite (FLUBNF_HUB=/nonexistent): 3510 passed, 155 skipped.
- Windows:
  - `_pid_alive` goes through `_pid_alive_windows`, whose tests exist
    (test_app_launch).
  - The test's ended pid is reaped (OpenProcess fails, or the exit code
    is not STILL_ACTIVE). The live pid is a sleeping child.
  - No paths or encodings are touched.
- Conflict: G08 (#57) rewrites the `usn.resolve` call in
  `season_page_context`. Once it merges, the line becomes
  `usn.resolve(root, df_all, allow_aggregate=scoreable and not live)`.

## Patch
G09/proposal.patch (git diff origin/dev...proto/G09-A)
