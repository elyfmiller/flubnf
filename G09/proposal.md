# G09 retro-progress: proposal (B)
Base: origin/dev 6f9a86f

Reproduced on a server from dev against a private copy of the hub clone
holding model-output/FluSight-baseline (the shared clone untouched):
whole Groundhog replays of 2025-26 and 2024-25 (zero-anchor level), a
2-state 2026-27, a sealed 2025-26 made by copying the finished tree into
app/state/retro_reseal, a vintage added to the copy's archive, and kill
-9 of the server mid-replay with a relaunch in place.

## RE-03
- Reproduced: yes: while the 52-jurisdiction replay ran, /retro/2025-26
  alternated "preparing results" with a brief "0 weeks scored" / "3 weeks
  scored" render, a finalize job per visit.
- Root cause: `routes/retro.retro_results` starts the finalize job
  whenever `_results_pending` (every stored week makes the scores and the
  aggregate stale) and waits on it.
- Fix: a live season (`_season_status` active, not an archive) never
  starts a job: the page renders from the caches as they stand, with its
  progress card; `season_page_context(..., live=True)` resolves the US row
  with `allow_aggregate=False` (no minutes-long aggregate beside the
  worker). `?rescore=1` is ignored while live. The worker finalizes the
  season when it ends, as before.
- Tests: `test_a_running_seasons_page_shows_its_weeks_without_a_finalize_job`
  (test_results_prep: finalize_season patched to raise).
- Risk: a live page shows scores up to the last finalize. For Ely: none.

## RE-05
- Reproduced: yes: the fresh replay over the sealed 2025-26 read "running
  · done 31 · total 31 · sealed True · eta None" while its live tree held
  1, 2, 3 weeks.
- Root cause: `_retro_progress` takes `done` from `_season_root` (the tree
  with most weeks, the seal) while the status and clock are the live
  record's; the index card likewise.
- Fix: `retro_seasons.shown_root(season)`: the live tree while its status
  is active or it holds completed weeks, else `_season_root`; used by
  `_retro_progress` and the index card (weeks, relWIS, scored). The seal
  shows only when the live tree is empty.
- Tests: `test_the_progress_poll_describes_the_live_tree_beside_a_sealed_record`
  (test_run_timing: the seal alone, a live replay over it, stopped at two
  weeks).
- For Ely: none.

## RE-06
- Reproduced: yes: with a vintage added, the finished 2-state 2026-27
  card read "1 week added", no Resume; the season page's "Resume on
  Retrospective" led there; a form run with other settings is refused.
- Root cause: `resume_fields` only for stopped or interrupted.
- Fix: the index offers the one-click Resume (the record's settings) also
  when the status is done, the season gained weeks and the tree is not a
  seal.
- Tests: `test_a_finished_replay_that_gained_weeks_offers_one_click_resume`
  (the hidden fields; no Resume once nothing is added).
- Live after: the card's Resume form posts the recorded scope and the
  zero-anchor knob; pressed, it ran the added week (5/5).
- For Ely: none.

## RE-07
- Reproduced: yes: "2025-26: 31 weeks scored" with 27 as-of weeks in
  scores.json; the pairwise view says 31 above "No scores under this
  convention".
- Fix: `n_weeks` is the pooled frame's distinct as-of count when the
  page's figures are available, else 0 (pairwise without field data).
- Tests: `test_the_season_title_counts_the_weeks_scored`.
- Live after: "27 weeks scored"; pairwise "0 weeks scored".
- For Ely: none.

## RE-08
- Reproduced: yes: the dead replay's elapsed 310 → 322 → 334 s at 12 s
  intervals while "interrupted"; the card's Wall time rising.
- Root cause: `retro.elapsed_now` adds now minus the open segment while
  the stored status is running, whatever the heartbeat says.
- Fix: the open segment of a dead or stale worker ends at its last
  heartbeat (`worker_dead` or `is_stale`).
- Tests: `test_an_interrupted_replays_wall_time_stops_at_its_heartbeat`.
- Live after: 41.6 s, unchanged across polls.
- For Ely: none.

## RE-09 (medium confidence)
- Reproduced: yes: after the kill and relaunch, "running" with a ticking
  clock and an ETA; "Not started: another season is replaying" on a Run;
  "interrupted" only after the 240 s heartbeat limit.
- Root cause: with no in-memory claim, the record's "running" is believed
  until the heartbeat is stale.
- Fix: `_start_record` keeps the worker's `pid`; `retro.worker_dead(meta)`
  (a pid that is not this process and no longer exists: `os.kill(pid, 0)`
  on POSIX, `OpenProcess` through ctypes on Windows, where os.kill would
  terminate) makes `effective_status` answer "interrupted" at once; a
  record without a pid, and the CLI's own process, keep the heartbeat
  rule.
- Tests: `test_a_dead_workers_record_reads_interrupted_at_once`
  (`_pid_alive` patched false; this process's own pid alive; no pid: the
  heartbeat; the real check on this process).
- Live after: "interrupted" on the first poll after the relaunch, no ETA,
  the card's badge, and a Run on another season accepted.
- Risk: a reused pid reads as alive until the heartbeat limit, the rule
  before. For Ely: none.

## Checks
ruff (the F gate) clean; test_run_timing, test_results_prep,
test_report_parity, test_retro_eta, test_resume_rerun,
test_season_run_marks, test_ui_layout, test_retro_archive,
test_us_national: 225 passed, 3 skipped. Full suite on the proto (3.13):
3506 passed, 154 skipped; the two failures are the tests/test_doctor.py
checks that fail on this machine's Python 3.13 on dev too. Invariance: no (no run path touched). Windows: the pid check
uses OpenProcess, never os.kill.

## Patch
G09/proposal.patch (git diff origin/dev...proto/G09-B)
