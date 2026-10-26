# G04 stop: proposal (B)
Base: origin/dev c8103eb (G02 merged; built before G03's PR, which touches `run_models`, not `run_stop` or the pipeline's stages: no overlap expected)

## FC-01
- Reproduced: yes. Live (a server from dev): an all-53 Groundhog-only run, `POST /run/stop` half a second later: the phase read "stopping…", the run ended `ok` with its submission file. With the change: the ledger row reads `stopped`, no `submission/` folder.
- Root cause: `pipeline._run_all` reads the workroot's STOP flag only at its start (`_name_workroot`); the particle filter polls it in its own loop; the Groundhog stage and the writers never look, so a press lands on a run that cannot stop.
- Fix: `pipeline._stop_check(workroot)` raises `RunStopped` when the flag is there; called before "consulting the Groundhog", passed to the engine as `stop=` (read before each location), and called before "writing submissions". The existing `except RunStopped` closes the row as `stopped` and writes nothing more; once the files are written a press no longer undoes them (the hint's two places).
- Tests: `test_busy_guard::test_stop_during_a_groundhog_only_run_ends_it_stopped_with_no_files` (pressed mid-walk: stopped, no submission; pressed before the Groundhog: it never runs).
- Risk: the run path; the all-53 file is unchanged (below). A press between the Groundhog and the writers now ends the run as stopped where it used to finish: that is the bug.

## DA-02
- Reproduced: the stop half of it, by test (a stop pressed mid-walk reached the Groundhog only after every group); the timing half is the dataset's size (a 200-group file), not run here.
- Root cause: `custom_retro.run` reads the replay's STOP flag between weeks only; `analogue._walk` runs every group of a week first.
- Fix: `analogue.run(spec, stop=None)`, `_walk(..., stop=None)`: `stop` is called before each location and may raise (the caller's own exception, so neither the pipeline nor the replay learns a new one). `custom_retro.run` passes one that raises its `Stopped` when the flag exists (only when a `stop_file` was given: the shipped call is unchanged); the pipeline passes `_stop_check`. Both callers add the keyword only when the engine's signature has it, the way the pipeline adds `notes` (tests fake the engine with plain lambdas).
- Not done: the upload cap or warning on large group counts, and the donor walk's cost; those are the dataset's engine path (section 6: no model changes) and sizing is Ely's. Said in the proposal only; the Status cell needs no "for Ely" since the stop half, the S2 part, is fixed.
- Tests: `test_busy_guard::test_the_groundhog_stops_between_locations_when_asked` (three locations, pressed after the first: one forecast, the caller's exception; no stop: the walk as before).

## WI-03
- Reproduced: by test (`/run/stop` during a replay set `stop_requested` and the phase, which nothing read).
- Root cause: `run_stop` writes the workroot's STOP flag; a Groundhog-only replay has no workroot (`on_workroot` runs only for the filter), and the replay reads its own `out/STOP`.
- Fix: `datasets_ui.stop_live_replay()` raises the live replay's `out/STOP` (what `/retro/dataset/{id}/{stamp}/stop` does; that route now calls it too); `run_stop` calls it when the claim is a `dataset-replay:` and says "stopping…". The replay stops after the current week, or within it between groups (DA-02), and records `stopped` as before.
- Tests: `test_datasets_ui::test_stop_run_reaches_a_dataset_replay`.

## DA-14
- Reproduced: by test: a replay sets the claim and `dataset_id` too, so `busy_with` answered "a run on it is in progress".
- Fix: `busy_with` checks `_REPLAY` first. One line moved.
- Tests: `test_datasets_ui::test_a_dataset_under_replay_is_busy_with_the_replay` (the reason, and the delete's flash).

## WI-10
- Reproduced: in the code (`base.html`: `fetch(p.conflict.stop,{method:'POST'})` follows the 303 into `GET /retro`, whose render pops the stop's notice unseen).
- Fix: `redirect:'manual'` on that fetch: the response is opaque, the redirect is not followed, and "Stopping 2024-25 after the fits in flight." waits for the page the user lands on after proceeding (`/forecast#results`). No route changes; the stop routes keep flashing as they do for a direct press.
- Tests: `test_busy_guard::test_the_guard_keeps_the_stops_notice_for_the_landing_page` (the page's script, the suite's way for base.html).
- Not checked in a browser here: the guard flow needs a live hub replay (seasons). The fetch option is standard (`redirect: "manual"` gives an opaque-redirect response; the `.catch` stays).

## Checked
- Related files (`test_busy_guard`, `test_datasets_ui`, `test_dataset_replay_knobs`, `test_custom_retro`, `test_groundhog`, `test_run_integrity`, `test_server_hardening`, `test_data_source`, `test_data_issues`, `test_forecast_modes`, `test_pages`, `test_ui_layout`, `test_analogue_splice`, `test_newest_reported`): 281 passed before the new tests; the two files with them: 58 passed, and all 5 new tests fail on the pre-fix code. `ruff check --select F821,F823,F811,F401 app/ui` clean.
- Output: an all-53 Groundhog run on 2026-10-17 on dev c8103eb and on the prototype gives the same file (md5 56da9201b416eb5c80317c849b55168e).
- Full suite: running; counts in a second commit.
- Windows: `Path(...).touch()` and `.exists()` as the code already does; no new paths.
- For Ely: none as a decision. DA-02's size cap or warning and the walk's cost are left as said above.

## Patch
G04/proposal.patch (git diff origin/dev...proto/G04-B)
