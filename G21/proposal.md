# G21 state-dir-protect: proposal (B)
Base: origin/dev 8cb3f7d

Reproduced on a server from dev with FLUBNF_STATE_DIR set (start.sh), the
run state of G20 (three Groundhog runs) and a Vermont Groundhog replay of
2025-26; ST-06 on a second server started with FLUBNF_PROTECT_ROOTS naming
one workroot. No run path, no engine code; no invariance check.

## WI-04 (also: RE-28)
- Reproduced: yes. The replay wrote tree/app/state/retro/2025-26/{run_meta,
  weeks}, the season report went to the same tree (/api/retro/2025-26/
  report_path named it), and the state folder's retro/ stayed empty.
- Root cause: retro_seasons.py fixes RETRO_ROOT, RETRO_RESEAL and
  RETRO_SEAL to the checkout's app/state, and engine_update.STATE_FILE too,
  while runs.APP_STATE (workroots, archive, exports, datasets, logs) follows
  FLUBNF_STATE_DIR.
- Fix: `RETRO_ROOT = APP_STATE / "retro"` and `STATE_FILE = APP_STATE /
  "engine_update.json"`. The sealed records ship in the checkout's
  app/state, so a new `runs.sealed_root(name)` (beside APP_STATE) gives
  the state folder's copy, or the checkout's when the state folder was
  moved and holds none; RETRO_RESEAL and RETRO_SEAL use it. Module
  constants as before, so the 63 + 59 + 4 tests that repoint them by name
  are untouched. After: the replay, its weeks and the report under
  <state>/retro/2025-26; /output/reveal passes its containment (the
  container has no file manager, so it then says so); a second console on
  a fresh state folder lists no season and reclaim reports 0/0/0.
- Not changed, for Ely: the Sandbox half. SANDBOX.md documents the Sandbox
  "in its own folder (`sandbox/`, never under version control)", beside
  the checkout, and the student workspace in flight on dev (runner.py,
  experiments.py, library.py, `runner._in_students(sb.SANDBOX)`) builds on
  that folder; moving it under FLUBNF_STATE_DIR is a design change in the
  App lane's live work. Also noticed, not in the bug: pf.RUNNER_PIDS_FILE
  (the runner's pid file) is `REPO/app/state/pf_runners.json`.
- Tests: test_state_dir_protect.py
  `test_the_retro_roots_and_the_engine_update_file_follow_the_state_folder`
  (a subprocess with FLUBNF_STATE_DIR, as test_state_isolation does),
  `test_a_sealed_record_shipped_in_the_checkout_is_found_from_a_moved_state_folder`.
- Risk: every reader of the retro roots on a console with FLUBNF_STATE_DIR
  set (today: the tests, and whoever sets it after LAUNCHERS.md); without
  it APP_STATE is the checkout's app/state and nothing moves. Storage's
  Protected list and the Home/Methods figures find the seals through the
  fallback.

## ST-06
- Reproduced: yes (medium confidence, confirmed). With
  FLUBNF_PROTECT_ROOTS naming a workroot: a normal Delete button, counted
  in Delete all, and POST /storage/delete removed it ("Deleted the
  workroot …: 6.6 MB freed"). reclaim.is_protected(RETRO_RESEAL/"2023-24")
  False while storage._storage_protected True.
- Root cause: two barriers: storage._storage_protected (sealed roots +
  HUB) and reclaim._protected_roots (APP_STATE/retro_seal + HUB +
  FLUBNF_PROTECT_ROOTS).
- Fix: one barrier. reclaim.extra_protected_roots() reads
  FLUBNF_PROTECT_ROOTS; reclaim._protected_roots() is the hub clone, both
  sealed records (sealed_root(name) and APP_STATE/name, deduplicated) and
  the extra roots. storage._storage_protected(p) is reclaim.is_protected(p)
  or the sealed roots as retro_seasons resolves them (tests repoint those).
  Storage lists each extra root under Protected as "Protected folder
  (<name>)", a protected workroot's row has its Delete off with the
  refusal's sentence (one `_busy_why("protected", …)` serves the row, the
  refused POST and the flash), and Delete all leaves it out through the
  shared function. The Protected heading's tip gains "a protected folder
  was named at launch" so "None can be deleted here" reads true.
- Tests: `test_storage_delete_refuses_a_protected_root_and_lists_it`,
  `test_reclaim_protects_the_production_reseal_as_storage_does`.
- Risk: reclaim protects more (the reseal), never less: "reclaim should
  keep what it keeps today" (Engine notes) holds. No Decided rule names
  the protected set; LAUNCHERS.md says the variable names "extra roots
  storage reclaim must not touch".
- For Ely: none

## ST-07
- Reproduced: yes (medium confidence, confirmed by construction: no engine
  here). A workroot with results.json, Arizona_r0/pf.log and a
  pf_status.json recording a failure: workroot_intermediates ->
  ['Arizona_r0'], survey -> its id; /api/storage/reclaim counted it.
- Root cause: reclaim.workroot_complete is "results.json exists", which a
  partial run has; pipeline.py prunes only `if not fails` ("a run with
  failures keeps them as evidence").
- Fix: reclaim.workroot_failed(w): any cell not "ok" in the MERGED
  pf_status.json (the top level's, or pf2s/ for a research run), as
  pipeline.py reads its failures; workroot_intermediates returns [] for
  such a run, so survey and execute leave it, as the pipeline did. The
  module docstring states the rule. No dialog text changes: "Every stored
  week, score, report, and submission file is kept" stays true, and the
  evidence now stays too.
- Tests: `test_reclaim_keeps_the_fit_trees_of_a_run_that_recorded_failures`
  (and that a clean run's trees are still intermediates).
- Risk: a partial run's workroot keeps its fit trees until Storage's Delete
  removes the workroot; that is the pipeline's existing rule.
- For Ely: none

## OU-15
- Reproduced: yes. /output/download served <state>/ledger.sqlite,
  last_form.json and a run's results.json, 200 text/csv, as attachments.
- Root cause: output_download checks containment in APP_STATE and the
  datasets root only.
- Fix: the file must also be a .csv whose grandparent folder is
  submission/ or export/ (custom_run.EXPORT_DIR): exactly what Output's
  day lines, the run page's file rows and a dataset run's export list
  link. Anything else is the existing 404 page ("File not found in app
  state"). The docstring says so.
- Tests: `test_the_download_route_serves_only_submission_and_export_csvs`:
  a registered submission CSV and an export CSV 200; the ledger, the form
  memory, results.json and a stray CSV 404.
- Risk: only hand-edited URLs change. The report and bundle downloads are
  their own routes (/runs/<id>/report/download, /retro/<season>/export).
- For Ely: none

## Patch
G21/proposal.patch (git diff origin/dev...proto/G21-B): runs.py
(sealed_root), retro_seasons.py, engine_update.py, reclaim.py,
routes/storage.py, routes/output.py, runs.html (the Protected tip),
app/tests/test_state_dir_protect.py (6 tests). Targeted suites
(test_reclaim, test_storage, test_lean_storage, test_state_isolation, the
download tests, test_submission_identity, test_output_*, test_busy_guard,
test_browse_safety, test_engine_update): 264 passed. Full suite
(FLUBNF_HUB=/nonexistent): 4206 passed, 159 skipped, the two test_doctor
failures of this container's Python. ruff clean (app/ui; pf.py's unused
perl_path import is dev's). Windows: Path everywhere, os.pathsep as
before, no new encoding.
