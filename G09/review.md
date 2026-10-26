# G09: review (B)
PR #58, head f005d2c (8416cf0 the change, f005d2c the Status cell).

Change requests
1. The season page of a sealed season answers 500 while (and after) a
   sealed finalize job exists. Reproduced on the head, live: the finished
   2025-26 tree copied into app/state/retro_reseal (its aggregate cache's
   mtime key no longer matches, so the first visit creates the sealed
   job: inputs None, done, error "the sealed validation record is read
   only"); the live tree removed; a fresh replay started (RE-05's own
   setup). Every visit to /retro/2025-26 during the replay returned 500:
   `retro_prep._job_covered` compares `job["inputs"] >= newest_samples_mtime`
   and the sealed job's `inputs` is None (`TypeError: '>=' not supported
   between instances of 'NoneType' and 'int'`, the server log). The same
   500 comes without a replay, on the second visit to a seal whose
   caches are not fresh (seen on dev too), so it is not this PR's
   doing, but the fix for RE-03 reads "a replay over a sealed season
   shows the seal's page exactly as dev does", and dev's page breaks in
   that case. One guard fixes it: a sealed job covers its root (the seal
   is never recomputed), for example `job["inputs"] is None or
   job["inputs"] >= ...` in `_job_covered`; and
   `test_a_replay_over_a_sealed_season_leaves_the_seals_page_whole`
   should make the sealed job exist first (a stale aggregate cache on the
   seal, one visit) so the second visit's 200 means something.

Approve once 1 is in: the rest of the PR is as decided.

What I checked
- The diff is A's prototype plus the two test checks from B (the Resume
  form's fields, no Resume once nothing is added; ?rescore=1 while live);
  the G08 line resolved as decided. Author and committer Ely F. Miller;
  no attribution lines or forbidden words; no footer; Status cell
  `fixed in #58`.
- On the head: test_retro_live_progress, test_run_timing,
  test_results_prep, test_report_parity, test_retro_eta,
  test_resume_rerun, test_season_run_marks, test_ui_layout,
  test_retro_archive, test_app_launch, test_retro_partial_scope,
  test_us_national: 335 passed, 6 skipped; the F gate clean.
- Live, a server from the head on the baseline hub copy: RE-07 "2025-26:
  27 weeks scored", pairwise "0 weeks scored"; RE-06 the finished
  2026-27 card, a vintage added: "1 week added" and the Resume form with
  the recorded fields (season, mode resume, national 0, custom
  locations); RE-05 the fresh replay over the seal: running, done 0, 1, 2
  of 31, sealed False, an ETA; RE-09 and RE-08 after kill -9 and a
  relaunch: "interrupted" on the first poll, elapsed 27.5 s on two polls,
  no ETA, /api/busy free; RE-03 could not be seen on the seal's page
  (request 1), and the interrupted season's page after the relaunch
  answered 200.
