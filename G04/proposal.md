# G04 stop: proposal (A)
Base: origin/dev c8103eb (G03 is PR #52, not merged; G04 touches /run/stop, not run_models, so the two do not overlap)

How I reproduced: two servers, dev and my prototype, fresh state each, the real hub; one script per bug (curl, and Chromium for the guard modal). Every bug reproduced on dev as reported; "after" is the prototype.

## FC-01
- Reproduced: yes. Groundhog only, all 53, Stop at about 1 s: dev ran on 18 s and ended "ok" with its submission file (1 file).
- Root cause: `app/ui/pipeline.py` `_run_all` reads the workroot's STOP only through the filter (`pf_engine`) and `_name_workroot` (a Stop while starting); nothing reads it around the Groundhog step or before the submissions are written, and the Groundhog (`app/core/engines/analogue.run`) loops over the 53 locations unasked.
- Fix: `analogue.run(spec, ..., stop=None)`: when given, `stop()` is called before each location and raises to end the run (the caller's own exception; the engine knows none). `_run_all` defines `_stop_check()` (STOP exists: `RunStopped`), calls it before the Groundhog and before "writing submissions", and passes it to the engine when the engine takes `stop` (the inspect pattern the step already uses for `notes`; the tests' fakes take only `spec`). The run then ends "stopped" through the existing RunStopped path, no file written. A location's cost is its forecasts (the donor ratios, asked after the walk yields it), so the check sits where it saves the work.
- After: Stop at about 1 s: the run ends within the second, "stopped", no submission file.
- Tests: test_busy_guard `test_stop_during_the_groundhog_ends_the_run_stopped_without_files` (an engine that takes `stop`: asked between locations, ends after the first), `test_stop_after_the_groundhog_ends_the_run_before_its_files` (an engine without it: read before the files).
- Risk: the engine's signature gains a keyword (default None: every other caller unchanged). Invariance: yes, same md5 (below).
- For Ely: none.

## WI-03
- Reproduced: yes. A Groundhog replay of the template dataset (2022-10-01 to 2024-09-28, 104 weeks), POST /run/stop at week 42: dev ran on and recorded "done, 104 of 104".
- Root cause: `routes/forecast.py` `run_stop` touches the console run's workroot STOP or sets `stop_requested`; a dataset replay has no workroot on the Groundhog path and reads only its own `out/STOP` (`datasets_ui.replay_worker`, `custom_retro.run`), so nothing reads either. The guard's console-run conflict posts the same /run/stop.
- Fix: `datasets_ui.stop_replay(ds_id, stamp)` (the body of the replay page's Stop, now shared): touches the replay's STOP (and its filter workroot's); `/run/stop` calls it when `_status["running"]` is `dataset-replay:<stamp>`, sets "stopping…", and returns. The replay page's own Stop route calls the same helper.
- After: the replay stopped at the next group ("stopped, 68 of 104" in my run: the delete check below ran between).
- Tests: test_datasets_ui `test_the_forecast_tabs_stop_stops_a_dataset_replay`.
- For Ely: none.

## DA-02
- Reproduced: yes. A 200-group x 700-week counts file (2.7 MB, accepted), a Groundhog replay of 2020-10-03 to 2025-05-31 (244 weeks): after 15 s still 0 weeks; Stop through its own page's route; dev still held the engine 120 s later (it reads STOP between weeks, and a week takes minutes).
- Root cause: `app/core/custom_retro.py` checks `stop_file` only at the top of each week; `custom_run.run` (a dataset forecast) only before the Groundhog; one week's Groundhog over 200 groups is minutes.
- Fix: both pass a stop callable into `analogue.run` (custom_retro: its `stop_file`, raising its `Stopped`; custom_run: `_check_stop(workroot)`), so Stop is read between groups; custom_run also reads it again before writing the exports.
- After: the engine free 1 s after Stop.
- Tests: test_custom_retro `test_a_stop_file_ends_the_replay_between_a_weeks_groups`; test_custom_run `test_a_stop_ends_a_dataset_forecast_between_its_groups` (both on the real engine, the walk wrapped to press Stop during the first group: only its forecasts are asked, the run stops, nothing written).
- For Ely: the size itself. One week of a 200-group dataset still takes minutes (3 s per group per week on the hunt's machine; a 244-week replay about 40 hours), within the upload limits (200 groups, 1.5M rows: app/core/datasets/report.py). Making the donor walk faster changes the engine's internals, and capping or warning at upload changes the limits; both are Ely's call, not a fix here.

## DA-14
- Reproduced: yes, in code and by the test: `datasets_ui.busy_with` checks the console's claim (`running` and `dataset_id`, which `replay_start` sets too) before `_REPLAY`, so a replay reads "a run on it is in progress".
- Fix: `_REPLAY` first.
- After (live): "wiretpl not deleted: a replay on it is in progress."
- Tests: test_datasets_ui `test_a_dataset_in_a_replay_says_a_replay_holds_it` (busy_with and the delete's notice).

## WI-10
- Reproduced: yes, Chromium. A Groundhog hub replay (2024-25, Vermont); on /forecast, Run models, the modal ("This will stop the running retrospective 2024-25."), Stop run and proceed: dev landed on /forecast with no notice, and /retro after had none; the replay sat "stopped, 8 of 30".
- Root cause: `templates/base.html`'s modal posts the stop with fetch(), which follows /retro/stop's 303 to GET /retro in the background; that render takes the stop's notice.
- Fix: the fetch passes `redirect:'manual'`, so the 303 is not followed and the notice waits for the page proceed opens. No route changes.
- After: the landing /forecast shows "Stopping 2024-25 after the fits in flight." (its tip: completed weeks and finished fits are kept).
- Tests: test_busy_guard `test_the_guards_stop_leaves_its_notice_for_the_page_proceed_opens` (the script; the behaviour checked in Chromium).

## Checks
- New tests: 7; all 7 fail on dev, pass on the prototype.
- Targeted: the guard, dataset, custom run and replay, run, retro, oracle-step, core, hubcheck, hardening, layout, forecast and pf-hardening files plus tests/test_analogue.py and test_local_pools.py: 926 passed, 18 skipped (Python 3.12). ruff F821/F823/F811/F401 on app/ui: clean.
- Output invariance: all-53 Groundhog run on 2026-10-17, dev and the prototype: md5 56da9201b416eb5c80317c849b55168e both.
- Windows: no paths, encodings or line endings; fetch's `redirect:'manual'` is supported by Edge and WebKit.

## Patch
G04/proposal.patch (git diff origin/dev...proto/G04-A)
