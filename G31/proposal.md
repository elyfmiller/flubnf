# G31 sandbox-polish: proposal (A)
Base: origin/dev fb4fa7f (G28 merged)

How: a dev server (8813) and a prototype server (8814) over a private hub copy, without the engine (as here). Models: a copy of the SIR example; the bug's two-rule model "sites" (L(r)+R(l)->L(r!1).R(l!1)+Tally(), R(p~0)->R(p~1)). Runs: three kinetics runs made with `prepare`, the engine's outputs faked as test_sandbox_export fakes them: one ok at 10,000 particles, one stopped at 500 with a pf_runner_0.err, and one failed with no outputs. Chromium at 1280 and 390 px, text size 100 and 160%.

## SB-07 (diagram captions)
- Reproduced: yes. "sites": the Model view read "3 molecule types, 1 rule in the saved model" and the Reaction network "6 species, 2 reactions". The network API says 6 and 4.
- Root cause: the captions count what is drawn. sandbox_views.html counts rules over the flow's edges, and the state change draws no arrow. model-views.js counts reactions keyed by `e.rule`, so 4 reactions over 2 rules read 2.
- Fix: `contactmap.rule_flow` returns `rules`, the rule lines read, drawn or not; A <-> B is one rule. `network_graph` returns `reactions`, the network's count. The two captions read them (an old cache falls back). `VIEW_VERSION` 2 to 3, so cached drawings are redrawn with the counts. The Model view's svg label says "model: ..." (it said "reaction network: 3 species, 1 reaction").
- After: "3 molecule types, 2 rules in the saved model"; "6 species, 4 reactions".
- Tests: `test_sandbox_polish.py::test_the_captions_count_rules_and_reactions_drawn_or_not`; test_contactmap's empty-graph pin gains `reactions: 0`.

## SB-18 (the "Saved ... first" notice)
- Reproduced: yes. Simulate with nothing edited: "Saved data.exp, model.bngl, priors.conf first. data.exp filled with 16 simulated weeks of Cobs." Save and run said "Saved sir_demo." the same way.
- Root cause: `routes/sandbox._sandbox_save_posted` saves and names every non-empty posted field.
- Fix: it saves and names only the fields that differ from the file on disk (newlines as save_model writes them). An unchanged file keeps its time. Fill, Simulate and Upload never name data.exp, which they replace next; it is still saved first, because Fill reads its header.
- After: no save notice with nothing edited; an edited priors.conf: "Saved priors.conf first. data.exp filled ...".
- Tests: `test_only_changed_files_are_saved_and_named`.

## SB-19 (the engine-missing reason twice, in jargon)
- Reproduced: yes. Save and run without the engine: the flash "Saved sir_demo. Not started: The PyBNF fork at /root/GitHub/PyBNF-pf does not provide fit_type = pf: there is no such directory. ?" over the alert "This computer cannot fit yet: The PyBNF fork at ... ?".
- Fix:
  - `sandbox.machine_problems` leads the missing engine with "The fitting engine is not installed." The engine's own message and its remedy follow, in the "?".
  - The preflight raises `MachineProblem` (a SandboxError). When the page shows the machine notice, `_sandbox_start` flashes only a pointer: "Not started: this computer cannot fit yet; the notice above the editor says why." When the page would not show it, the refusal says the reason in full, as before.
  - Save and run stays on: the page's probe waits less than the run's.
  - The console's own engine message (pf.engine_missing_message, the ledger's) is unchanged.
- After: one notice, "This computer cannot fit yet: The fitting engine is not installed. ?", and the pointer.
- Tests: `test_without_the_engine_the_notice_is_plain_and_said_once`. Pins of the old behaviour updated:
  - test_sandbox_audit: the preflight refusal's reason and remedy are now read in the page's notice. The 2026-10-13 audit fixed that a remedy reaches a "?", and it still does.
  - test_sandbox_guard and test_sandbox_machine: the headline.

## SB-20 (two rules stacked)
- Reproduced: yes. A failed run with no outputs: the summary's border-bottom and Diagnostics' border-top, both 1px, nothing between them.
- Fix: `.sb-rsum + .sb-rsec{border-top:0;padding-top:0}` (tabs/sandbox.css).
- After: one rule (screenshot at 1280).
- Tests: `test_one_rule_under_a_summary_with_nothing_after_it`.

## SB-21 (What changed)
- Reproduced: yes. "particles 10000 500"; in code, the data row "typed" for a run with no source sidecar and the key `n_obs`.
- Fix:
  - `sandbox_export.RUN_SETTING_LABELS` names each setting: "weeks of data", "data column", "data file name", "cumulative observable", "forecast weeks"; particles, jitter and seed keep their names. `diff_runs` adds the label.
  - The template writes integers as 10,000.
  - Data with no source recorded reads "as written".
- After: "particles 10,000 500".
- Tests: `test_what_changed_names_its_settings_and_writes_numbers`; test_sandbox_export's settings pin gains the label.

## SB-22 (the Oracle step card)
- Reproduced: in code and its test. The card shows for any Oracle SIHRS start (`shipped.shipped`), the dataset start included, whose gate always refuses. The stats show "State both" with an empty tip, and a "w" the input above already holds.
- Fix:
  - `shipped_state` returns `dataset`; the card is not shown for a dataset start.
  - The state is said as "Donors": "both donor banks", "FluSurv-NET donors only", "admissions donors only", or "no donors: the plain filter".
  - The w stat goes: the input carries the applied w, its label names the production weight, and the notice names the w applied.
- Tests: `test_a_dataset_start_has_no_oracle_step_card`, `test_shipped_state_says_a_dataset_start`; test_sandbox_oracle's "(production 0.5)" stat pin now reads the input's value and label.

## SB-23 (engine keys)
- Reproduced: yes. The fold lists fit_type pf, population_size 1 and max_iterations 1.
- Fix: the table leaves out the three. The engine still gets them (sandbox.html; `engine_settings` is unchanged, prepare writes it).
- Tests: `test_the_engine_keys_table_leaves_out_the_plumbing`.

## SB-24 (Load is off, twice)
- Reproduced: yes. Start 2026-11-01 and End 2026-10-17 at 390 px: the alert "Load is off: Start 2026-11-01 is after End 2026-10-17." plus a "?" on the disabled Load holding the same text.
- Fix: Load is a plain button (sandbox_data.html). sandbox.js disables it and points its aria-describedby at the alert while the alert shows.
- After: the alert alone; Load off, described by it.
- Tests: `test_why_load_is_off_is_said_once`.

## SB-25 (plurals)
- Reproduced: in code and test_sandbox_data's pin ("1 missing weeks dropped").
- Fix: "1 week", "1 missing week dropped", "1 simulated week" (`_sandbox_fill_flash`, simulate).
- Tests: `test_one_week_and_one_missing_week_are_singular`; test_sandbox_data's two pins.

## SB-26 (the run zip)
- Reproduced: yes. The stopped run's zip has 9 entries and no pf_runner_0.err, though the run folder holds one.
- Fix: `run_zip` adds each non-empty pf_runner_*.err, its last `ERR_ZIP_MAX` (256 KB) bytes.
- Tests: `test_the_run_zip_carries_the_engines_messages` (with the tail cap).

## UI-16 (Changed)
- Reproduced: yes. A model made from the SIR example on 2026-11-10 07:22 read "Changed 2026-10-26 00:33", the example's file time.
- Fix: `add_example` touches the copies, as `copy_model` does.
- Tests: `test_a_copied_example_changed_when_it_was_copied`.

## UI-19 (diagram labels; medium confidence: reproduced)
- Reproduced: yes.
  - At 390 px the labels measure 8 px. At 1280 px and 160% text they measure 12 px, the same as at 100%.
  - The phone half has a root cause beyond the hint. Inside `model-views.js` network(), a helper `function box(x, y, w, h)` hoists over the `box` parameter. So `box.clientWidth` is undefined, and every flow and network drawing is laid out 640 units wide. A 332 px box shows it at half size. (Logged in the page: the parameter is the function.)
- Fix:
  - The helper is renamed `bounds`, so the drawing reads its box: 332 units on that phone.
  - `textScale()` (the root font size over 16) divides the drawing's units: network() and contactmap() lay out in W/k by H/k for a box of W by H pixels. Labels, boxes and arrows grow with the Display text size, with no change to the layout code.
- After:
  - 390 px: 14 px labels (viewBox 0 0 332 273).
  - 1280 px at 160%: 22 px.
  - Screenshots of "sites" at 390 px and the SIR model at 160% show readable drawings that fit.
- Tests: `test_the_drawing_reads_its_box_and_the_text_size`.

## Checks
- New `app/tests/test_sandbox_polish.py` (13), each failing on dev. Sandbox, contact map, marks, pages and layout tests: 452 passed, 5 skipped. ruff (the gate) clean.
- Output: no run path (the Sandbox is never a submission).
- Windows: the mtime comparison in the test allows 1 s; `read_text` compares the text with `\r\n` folded, as save_model writes it.

## Patch
G31/proposal.patch (git diff origin/dev...proto/G31-A)
