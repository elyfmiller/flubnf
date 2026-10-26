# G05 no-engine: proposal (A)
Base: origin/dev 695155d (the same tree as 598d5c1, where the prototype was cut)

The rule I followed: "refuse plainly, up front, rather than run the other model silently", for what the engine-less machine cannot run (Oracle SIHRS only, the research run, the Retrospective's Oracle preset). Both stays allowed: on a machine without the engine it has always run the Groundhog and written the Groundhog file, the Tier A design (`pf_skipped: engine venv not installed (Tier A)`), and the Submission lane's Groundhog file comes from it. So Both is not refused; it now says before the run, and while running, that only the Groundhog runs. One helper says why in the same words everywhere: `pipeline._pf_engine_missing(state)` gives "not installed on this machine" (absent) or "not fully installed on this machine" (broken), '' when ready.

## FC-03 (also: MO-05, WI-09)
- Reproduced: yes. A server from dev, no engine: POST /run engine=pf, Arizona: no notice, the run starts; the hunt's record (status ok, no submission file, a Groundhog fan) is what follows. /model/pf: no alert, "Run Oracle SIHRS only" enabled (MO-05); /model/pf2s: "Start research run" enabled, and a research run (members=3) runs the Groundhog alone the same way (WI-09).
- Root cause: `app/ui/routes/forecast.py` `run_models` never reads the engine; `pipeline._run_all` then skips the filter (`pf_skipped`) and runs the Groundhog, so "ok" with no Oracle output.
- Fix: `run_models` (after the remembered form is stored, before the date refusals): `engine == "pf"` or `members == 3` with the engine not ready is refused: "Not run: the Oracle SIHRS needs the particle-filter engine, which is not installed on this machine. Choose Groundhog only." (the research run: "Not run: the research run needs ...", no "Choose" since it has no Groundhog choice), back to the posting page. `templates/model.html`: on /model/pf a warn alert with the same words (id md-busy, the existing busy alert's slot: `{% elif %}`, so never two) and the button `disabled aria-describedby="md-busy"`; `research_run.html` the same (id rr-busy). `routes/models.py` passes `pf_missing`. No new marks.
- Tests: `test_no_engine.py::test_oracle_sihrs_only_is_refused_without_the_engine` (absent and broken wording), `::test_a_research_run_is_refused_without_the_engine`, `::test_with_the_engine_they_run`, `::test_the_model_pages_say_why_the_oracle_cannot_run`, `::test_with_the_engine_the_model_pages_run`.
- Risk: 15 existing tests drive the Oracle preset or the research run through the route with a faked engine; on the suite's machine (no engine) they now refuse. A new opt-in fixture `pf_engine_ready` in `app/tests/conftest.py` (monkeypatches `pipeline._pf_engine_state` to "ready") is added to each: test_engine_build (1), test_knobs_panel (1), test_knobs_wiring (3), test_oracle_step (1), test_research_run (2), test_resume_rerun (1), test_retro_archive (several), test_retro_pf_name (1), test_server_hardening (1). test_remembered_form's blank-date case posted engine=pf; it now posts all (it tests the date, not the engine). Invariance: yes (below).
- For Ely: none.

## FC-04
- Reproduced: yes. Dev, no engine, default form: Model "Both" selected... the Engine row reads "Particle filter", no notice, "Oracle SIHRS only" selectable. During an all-53 Both run /api/progress: total 159, settings engine "both models (Oracle SIHRS and Groundhog)", replicates 3, particles 10,000; the card read "Fits done 0 of 159" the whole run.
- Root cause: `forecast.html`'s Engine row is unconditional; `run_models` sets `expected_total` for all/pf without the engine; `_run_all` describes the run with `spec_settings(spec)` before it knows the filter is skipped (the record afterwards says "Groundhog only (no PF engine on this machine)").
- Fix: `forecast.html`: when the engine is missing (`pf_missing` from the page route), the Engine row is replaced by the badge the dataset form already uses for the same case: "Groundhog only: the particle-filter engine is not installed on this machine" (`tips.badge("neutral", ..., id="fc-pf-off", icon_name="lock")`); the "Oracle SIHRS only" option is `disabled` (and never `selected`). The badge lives in the engine row, so it hides with Groundhog only, as the Engine row did. `run_models`: `expected_total` only when the engine is ready. `pipeline._run_all`: `spec_settings(spec, {"pf_skipped": "engine venv not installed (Tier A)"})` when the engine is absent, the outcome the record already writes, so the card's settings read "engine: Groundhog only (no PF engine on this machine)", no replicates or particles, and "Fits done --" with the phase text, as a Groundhog-only run.
- Live after: 1280 light and 390 dark, the badge under Model with Both, the option off; the Running card as above (screenshot-checked).
- Tests: `test_no_engine.py::test_both_says_before_the_run_that_the_groundhog_runs_alone`, `::test_with_the_engine_the_form_is_as_before`, `::test_the_running_card_shows_a_groundhog_only_run`.
- Risk: the broken state keeps today's path (the record says "PF engine install incomplete"); only "absent" gets the Tier A settings. Invariance: yes.
- For Ely: none. (Refusing Both too would break the Groundhog file on engine-less machines; I kept Tier A.)

## FC-17 (also: ST-03, WI-06)
- Reproduced: yes. /runs and /storage on dev: a Groundhog-only run (`pf_skipped: "analogue-only run"`) reads "PF skipped (no engine)", the same chip as a Both run without the engine.
- Root cause: `app/ui/shared.py` `_outcome_items` words any `pf_skipped` as "PF skipped (no engine)".
- Fix: the chip reads "Groundhog only" when the reason names the analogue (`"analogue" in str(pf_skipped)`, the reason `runs.py` writes for a chosen Groundhog-only run); the no-engine chip and its tip are unchanged. /runs and /storage share the function.
- Tests: `test_no_engine.py::test_the_ledger_chip_says_why_the_filter_did_not_run`. test_fewer_marks's pf_skipped=True case is unchanged (still "PF skipped").
- Risk: none beyond the chip. Invariance: no.
- For Ely: none.

## RE-02
- Reproduced: yes. Dev, no engine: a Vermont Groundhog-only replay of 2025-26 (31 weeks done); then POST /retro/run engine=pf mode=archive: "Archived 31 weeks of 2025-26 as 2025-26__archived_…; starting a fresh replay.", and the new season's run_meta reads status done, 0 weeks.
- Root cause: `app/ui/routes/retro.py` `retro_run` checks the preset against `ENGINES` but never the engine; the archive (or discard) happens before the replay, and each week then fails inside the engine path into failures.log, and the season finishes "done".
- Fix: `retro_run` refuses the Oracle preset up front when the engine is not ready, before any archive or discard: "Not started: the Oracle SIHRS needs the particle-filter engine, which is not installed on this machine. Choose Groundhog only." `retro_index`'s `engine_ok` now reads `pipeline._pf_engine_state() == "ready"` (it read `PY_ENGINE.exists() and PYBNF.exists()`, so a half-installed engine passed).
- Live after: the same steps: the refusal, the 31-week season untouched, no archive folder.
- Tests: `test_retro_archive.py::test_without_the_engine_the_oracle_preset_moves_nothing`.
- Risk: engine path. The other half of RE-02, "a replay whose every week failed is marked complete", sits in the replay runner's engine path, which cannot run here; with the up-front refusal it is no longer reached from a missing engine. I left it unchanged.
- For Ely: a note, not a decision: a season whose every week failed for another reason (the engine breaking mid-season) would still read complete; that is the runner's call (`app/core/retro*.py`) and needs a real engine to test.

## RE-23
- Reproduced: yes. /retro on dev with no engine: the Engine preset comes set to "Oracle SIHRS + Groundhog (hours)" and Run retrospective is off on arrival, its "?" showing.
- Root cause: `templates/retro.html` always selects the first option (pf); the button is `off=not engine_ok`.
- Fix: without the engine "Groundhog only (minutes)" comes `selected`; the reason button is rendered on (`off=False`) and the page's existing script turns it off, with its reason, only while the Oracle preset is picked (it already ran `sync()` on load and on change).
- Live after: arrival analogue, button on, no "?"; picking the Oracle preset turns it off with the reason, as before.
- Tests: `test_retro_archive.py::test_without_the_engine_the_form_comes_set_to_what_can_run`.
- Risk: none with the engine (the form is as before). Invariance: no.
- For Ely: none.

## Checks
- New tests: 11 (9 in test_no_engine.py, 2 in test_retro_archive.py). On the base: 8 fail, 3 pass (the three with-the-engine guards, as they should).
- `ruff check --select F821,F823,F811,F401 app/ui` clean. All app/tests on the prototype before the new tests: 2893 passed, 69 skipped. The full suite on the prototype (3.12): 3474 passed, 155 skipped, 0 failed.
- Invariance: an all-53 run on 2026-10-17, Groundhog only and Both, on dev 695155d and on the prototype: md5 56da9201b416eb5c80317c849b55168e for all four.

## Patch
G05/proposal.patch (git diff origin/dev...proto/G05-A)
