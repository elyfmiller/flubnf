# G21 state-dir-protect: proposal (A)
Base: origin/dev 8cb3f7d

How: a dev server (8815) and a prototype server (8814), each from a copy
of its tree with a fresh state folder (FLUBNF_STATE_DIR), the shared hub
clone read only. A Groundhog replay of 2025-26 for Vermont (scoring fails
on this sparse hub, as in the hunt; the weeks and the season report are
written). Groundhog runs for Arizona and Ohio on 2026-10-17.

Checked against the Decided sections of every lane file: none records a
rule on reclaim, on what Delete may delete, on /output/download, or on
where the retro trees live. Every change below deletes or serves less
than before, or moves only what already sat in app/state.

## WI-04 (also: RE-28)
- Reproduced: yes, on dev 8cb3f7d. The replay wrote
  tree/app/state/retro/2025-26 into the checkout copy; the server's state
  folder got no retro/. report_path answered
  .../tree/app/state/retro/2025-26/2025-26-FluBNF-season-report.html, and
  Show in folder flashed "Nothing opened: the file is not in app state
  any more." A console on the same tree with a brand-new empty state
  folder listed "2025-26 retrospective" on /storage.
- Root cause: app/ui/retro_seasons.py:35-39 fixes RETRO_ROOT,
  RETRO_RESEAL and RETRO_SEAL to `Path(__file__).parents[1] / "state"`,
  and app/core/engine_update.py:35 fixes STATE_FILE the same way, while
  runs.APP_STATE reads FLUBNF_STATE_DIR. site_build.py and reclaim.py
  already read the retro trees from APP_STATE, so the console and its
  site build disagreed whenever the variable was set.
- Fix: the four paths are `APP_STATE / "retro"`, `"retro_reseal"`,
  `"retro_seal"` and `"engine_update.json"` (runs.APP_STATE, read at
  import as APP_STATE itself is). With FLUBNF_STATE_DIR unset nothing
  moves: APP_STATE is app/state.
- After: the replay's tree and its season report under state/retro; the
  checkout copy has no app/state/retro; the empty-state console lists no
  season; Show in folder passes the state check (it then says no file
  manager could be started: this container has none).
- Tests: test_state_folder_protect.py
  `test_the_retro_trees_and_engine_update_follow_the_state_folder` (a
  fresh Python with FLUBNF_STATE_DIR set).
- Risk: none for a default install. The tests already repoint these
  roots; any that did not now write in the suite's temp state rather
  than the checkout.
- For Ely: the Sandbox part. SANDBOX is the checkout's sandbox/, outside
  app/state, and the student-workspace runner reads each student's
  experiments at ~/Students/<name>/sandbox/experiments, the clone's own
  sandbox/. A Sandbox that followed FLUBNF_STATE_DIR could part from
  where the runner looks, so whether the variable should carry a
  student's models is Ely's decision. Unchanged here.

## ST-06 (also: none)
- Reproduced: yes. With FLUBNF_PROTECT_ROOTS set to the first run's
  workroot: its Storage row had Delete, "Delete all 2 completed
  workroots (11.0 MB)" counted it, and POST /storage/delete answered
  "Deleted the workroot 20261110T032625-67cbc7: 5.5 MB freed." In
  Python: reclaim.is_protected(<state>/retro_reseal/2023-24) False,
  storage._storage_protected(...) True.
- Root cause: two barriers. storage.py `_storage_protected` checks the
  sealed roots and the hub only; reclaim.py `_protected_roots` checks
  APP_STATE/retro_seal, the hub and FLUBNF_PROTECT_ROOTS, not the reseal.
- Fix: reclaim's roots gain APP_STATE/retro_reseal (the production
  record, read only like the seal), and `_storage_protected` also asks
  reclaim.is_protected, so Delete, Delete all and Reclaim refuse the same
  trees. A protected workroot's row shows the lock badge the Protected
  section already uses, in place of Delete (runs.html); no new words.
- After: the row has the lock and no Delete; "Delete all 1 completed
  workroot (5.5 MB)"; a crafted delete flashes "Not deleted: that tree is
  protected ..." and the folder stays; reclaim protects the reseal.
- Tests: `test_delete_and_reclaim_refuse_the_same_trees`.
- Risk: only less is deletable. The refusal's parenthesis names the seal
  and the hub, not FLUBNF_PROTECT_ROOTS; it is reached only by a crafted
  request now that the row has no button, so it stays as it is.
- For Ely: none

## ST-07 (also: none)
- Reproduced: yes, with a workroot built by hand (a partial run needs
  the engine): results.json, Arizona_r0/pf.log and a pf_status.json
  recording the cell's failure. /api/storage/reclaim listed
  "Completed-run workroot intermediates: 1 completed run"; Reclaim
  deleted Arizona_r0.
- Root cause: reclaim.workroot_intermediates treats any workroot with
  results.json as complete. The pipeline (pipeline.py, after close_run)
  prunes only `if not fails`, where fails is pf_status.json's cells not
  "ok": "a run with failures keeps them as evidence".
- Fix: `reclaim.workroot_failures(w)` reads the merged pf_status.json the
  pipeline reads; any cell not "ok" (or an unreadable file) keeps the
  run's intermediates. A Groundhog-only run has no pf_status.json and a
  clean run is all "ok", so what the pipeline prunes is unchanged.
- After: the survey finds nothing ("total 0"); the tree stays.
- Tests: `test_reclaim_keeps_the_cell_trees_of_a_run_with_fit_failures`.
- Risk: reclaim frees less on machines with partial runs, as the
  pipeline intends. The docstring says so.
- For Ely: none

## OU-15 (also: none)
- Reproduced: yes. GET /output/download for <state>/ledger.sqlite,
  <state>/last_form.json and a workroot's results.json: 200,
  text/csv, attachment.
- Root cause: routes/output.py `output_download` checks only that the
  path is a file inside app state (and outside the dataset store).
- Fix: it also requires a .csv whose folder is a model's under
  submission/ (workroot or archive) or a dataset run's export/
  (custom_run.EXPORT_DIR): the files Output, the run page and a dataset
  run's page link. Anything else is the existing 404 notice.
- After: the three answer 404; the run's submission CSV 200; a dataset
  run's export CSV 200 (test).
- Tests: `test_download_serves_only_submission_and_export_csvs`.
- Risk: none for the links the console draws (all three templates pass
  submission or export paths).
- For Ely: none

## Checks
- New app/tests/test_state_folder_protect.py (4): each fails on 8cb3f7d
  and passes here.
- Existing tests of storage, reclaim, output, downloads, archives and
  the retro pages (28 files, 248 tests) pass unchanged. ruff clean.
- Full suite (FLUBNF_HUB=/nonexistent): 4205 passed, 160 skipped, 0 failed.
- Output check: not needed. No file on its list changes; the pipeline's
  own prune (`if not fails`) meets the same "no failures" condition.
- Windows: Path joins only; pf_status.json read as UTF-8 as pf.py does.
- engine-public touches reclaim.py's docstring (one line, a different
  paragraph) and sandbox.py; a merge of dev into this branch after it
  lands should be clean.

## Patch
G21/proposal.patch (git diff origin/dev...proto/G21-A)
