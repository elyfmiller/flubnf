# G06 which-run-shows: proposal (A)
Base: origin/dev 48e30bb (the patch applies cleanly on 12281e7, G05 merged)

Two recorded rules bound this group: app.md Decided (2026-10-01) "The report card keeps the newest run with results, labelled with its run time", and Now (2026-10-15) "a vintage run never replaces Home's or Output's current week ... Home and Models keep the shipped rule". So OU-01 is fixed through the picker (the hunt's second option), and MO-06 through the card's label, not by changing which run they show.

## OU-01 (S2)
- Reproduced: yes. A server from dev: Both on all 53 for 2026-10-17 (archived; this machine has no engine, so I marked its archive record complete, as the hunt's simulation did), then a Groundhog run on Ohio alone. /output: the report card links the Ohio run's report; the 2026-10-17 date card shows the all-53 file; no picker at all, so the archived all-53 report is unreachable. /output/report (Home's button) serves the Ohio report too.
- Root cause: `app/ui/routes/output.py` `output_page`: the picker drops the card's week (`d != report_asof`) unless the card's run is modified, whatever run the archive holds for that week.
- Fix: the week also stays when its archive record names another run than the card's (`held_run(d) not in ("", rid)`): a newer run on a few states is never archived over a whole-set run, so the archived report differs from the card's. A folder from before the record (no run id) keeps today's rule. The card itself keeps the newest run (Decided). /output/report follows Home's run, and Home shows that run (the shipped rule), so it is left as is.
- Tests: `test_which_run_shows.py::test_the_weeks_archived_report_stays_reachable_beside_a_newer_few_state_run`. `test_output_by_date.py::test_the_report_card_shows_the_newest_run_even_when_modified` pinned the bug's pattern in its last step (an override run on the card, never archived, the archive holding the earlier run's report: the week was dropped); it now asserts the week stays, then leaves once the archive holds the card's run.
- Risk: the picker only. Invariance: no.
- For Ely: none.

## OU-11 (S4)
- Reproduced: yes. The newest run a modified Ohio run for 2026-10-17 (knob changed, no hub-names box), the archive holding the shipped run: the card reads "as of 2026-10-17 · modified · non-hub names" and beside it "Earlier weeks: 2026-10-24 (as of 2026-10-17)", the same week.
- Root cause: `templates/output.html`: the picker is labelled "Earlier weeks" while it can hold the card's own week (and, with OU-01, more often will).
- Fix: label "Archived weeks", which is what it lists; the template comment says when the card's own week is in it.
- Tests: in the OU-01 test ("Archived weeks", no "Earlier weeks").
- For Ely: none.

## OU-02 (S2, medium confidence)
- Reproduced: yes, live. A hub copy whose newest week is 2026-10-10 (the live target file and the archive without 2026-10-17): an all-53 run on 2026-10-10 records `realtime`; back on the full hub, an all-53 Vintage run on 2026-10-10: /output's 2026-10-17 line serves the vintage run's file (the two files differ). On a Both run the archive is replaced the same way (the archive step never reads the mode).
- Root cause: `app/core/archive_record.py` `choose` and `keep_reason` ignore the run's mode; `output._hub_candidates` records none; `pipeline` passes none to `_archive_run`.
- Fix: `archive_record.realtime_of(spec)` (True when a record has no mode, as for records from before it); `choose` takes the real-time candidates first (all of them when none is), then its rule; `keep_reason(..., realtime)` keeps an archive holding a real-time run from a vintage run ("kept: this run is a vintage run of a past week, so the archive kept the run made in that week <id>"); `_hub_candidates` records `realtime` for workroot and archive candidates; `pipeline._run_all` passes `realtime` (from `spec.extra["mode"]`) to `_archive_run` when it is a vintage run. A date with no run made in its week still shows, and archives, its vintage run. The current week is unaffected (its runs are real-time by the anchor rule).
- Live after: the same steps: the 2026-10-17 line serves the run made in its week; the archive keeps it; the vintage run's record reads the kept reason above.
- Tests: `test_a_vintage_run_of_a_past_week_never_replaces_the_run_made_in_that_week` (Output and the archive; a vintage-only date still shown and archived), `test_choose_takes_a_run_made_in_its_week_before_a_later_vintage_run`, `test_the_pipeline_hands_the_runs_mode_to_the_archive` (through `_run_all` with `pipeline_env`).
- Risk: which file a past date shows and what the archive keeps; no file is written differently. Invariance: yes (below).
- For Ely: none (the 2026-10-15 rule, extended from the current week to past weeks as the bug asks).

## OU-09 (S3)
- Reproduced: yes. After OU-01's steps, Storage's delete of the all-53 run's workroot: /runs/<id> says "Output shows this run's files for 2026-10-24" and then "Submission files: No submission files", no report link; /runs/<id>/report and /report/download answer 404, while archive/2026-10-17 holds the run (archive.json).
- Root cause: `routes/forecast.py` `run_page`, `run_report`, `run_report_download` read `workroots/<id>` only.
- Fix: `output._run_folder(run_id)`: the workroot, else the archive folder whose record names the run (Output serves the date's files from there), else the workroot's path; the three routes use it (the report routes after the run-id shape check).
- Live after: the run page lists the archived file (with its checks and "all 53 locations") and links the report; both report routes 200.
- Tests: `test_a_runs_page_and_report_come_from_the_archive_once_its_workroot_is_gone`.
- For Ely: none.

## HM-05 (S3, medium confidence)
- Reproduced: yes. A Groundhog run on Arizona and New York: Home "Coverage 2 of 52"; then an Oracle-only run on Ohio (no engine on dev before G05; its results hold `pf: {}` and the Groundhog's Ohio consulted for its pages): Home "1 of 52".
- Root cause: `app/ui/shared.py` `_latest_results` takes the newest real-time run whatever it produced.
- Fix: the shipped callers (default and `include_modified`) pass over a run whose spec names one model (`pf` or `analogue`) that produced nothing; Both is never passed over (it writes the Groundhog file without the engine); the Forecast tab (`newest=True`) still shows the newest run. Since G05 refuses Oracle-only without the engine, the live path is an Oracle-only run whose fits all fail.
- Live after (on the prototype, before G05): the same Oracle-only Ohio run: Home stays "2 of 52".
- Tests: `test_a_run_whose_one_model_produced_nothing_never_replaces_the_shown_run`.
- For Ely: none.

## MO-06 (S3)
- Reproduced: yes. A real-time run, then a quick run of 2026-10-10 Ohio from /model/analogue ("Recorded as a vintage run"): the card still reads "Latest run 2026-10-17 · ..." with the earlier run.
- Root cause: `templates/model.html` labels the shipped rule's run (`_latest_results()`: the newest real-time run with hub names) "Latest run".
- Fix: the label (and the no-forecast tip) read "Latest real-time run" when the run shown is real-time, "Latest run" when it is the newest vintage run because none is real-time; `routes/models.py` passes `run_realtime`. Models keeps the shipped rule (Decided).
- Tests: `test_the_models_card_names_the_real_time_run_it_shows`. `test_models_tab.py`'s two label tests pinned "Latest run" for a real-time run, the bug's text; they now read "Latest real-time run".
- For Ely: none.

## OU-08 (S3)
- Reproduced: yes, by the page text and the shown files: the "i" says "it shows each model's file from the newest run that finished complete", while the date shows the older whole-set run over the newer complete Ohio run; "The round open now is outlined; past dates ... take one line each", while the newest date is always a card and a coming round is outlined too; the live badge's tip says "when it finishes complete, this card shows its files", false for a run on a few states.
- Fix: the "i" states the rule: "... from the newest complete run on all 53 locations, else the newest complete run, else the newest run that wrote one; a run made in the round's own week comes before a later vintage run, and the other runs' files stay in their run folders." and "The newest date, a round open or coming (outlined) and a date a run is writing now each get a card; other dates take one line each, ...". The live badge's tip: "A console run for this date is in progress." (no promise).
- Tests: `test_outputs_words_state_the_rules_it_follows`.
- For Ely: none.

## Checks
- New `app/tests/test_which_run_shows.py` (8): all fail on dev, pass here. Changed: `test_models_tab.py` (2 label asserts), `test_output_by_date.py` (1 picker step), each pinning the bug's behavior.
- `ruff check --select F821,F823,F811,F401 app/ui` clean. Targeted (models, output, layout, archive rule, browse safety, the new file): 104 passed. Full suite: running; counts follow.
- Invariance: an all-53 run on 2026-10-17, Groundhog only and Both, on dev 48e30bb and on the prototype: md5 56da9201b416eb5c80317c849b55168e for all four.
- Live: every bug re-checked on a server from the prototype as above; the picker at 1280 light and 390 dark; the Models label at 390 dark (it wraps to two lines in its row, as other labels do).

## Patch
G06/proposal.patch (git diff origin/dev...proto/G06-A)
