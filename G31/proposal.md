# G31 sandbox-polish: proposal (B)
Base: origin/dev de4eb1f8 (G27 merged; applies to fb4fa7f, G28 touched other files)

How: a dev server (8826) and then the prototype on the same port, each
with fixtures a script rebuilds: a model from the SIR example, a model
with binding sites and a state change (L(r)+R(l)->L(r!1).R(l!1)+Tally(),
R(p~0)->R(p~1)), two fabricated runs of the SIR model (one failed with a
pf_runner_0.err, one stopped on Arizona data with 20 rows and 500
particles), and an Oracle SIHRS start from a stored dataset with a
fabricated finished run; curl through the routes; Chromium at 1280 px
(100% and 160% text) and 390 px dark for the diagram and the Load box.
No engine here, so no fit ran.

## SB-07
- Reproduced: yes: "3 molecule types, 1 rule in the saved model" (the
  state-change rule draws no arrow) and "6 species, 2 reactions" while the
  /network API and Check's facts say 4.
- Root cause: sandbox_views.html counts the Model view's rules over the
  drawn edges; model-views.js counts the network's reactions by `e.rule`.
- Fix: `contactmap.rule_flow` adds `rules` to the flow graph (the rules
  in the saved model, a reversible one once); the Model view reads it; the
  Reaction network view's caption reads the API's own species and
  reactions counts.
- After: "3 molecule types, 2 rules in the saved model"; "6 species, 4
  reactions".
- Tests: test_sandbox_polish.py `test_the_captions_count_the_models_rules_and_the_networks_reactions`.

## SB-18
- Reproduced: yes: Simulate with no edits: "Saved data.exp, model.bngl,
  priors.conf first. data.exp filled ..."; all three files' times moved.
- Root cause: `_sandbox_save_posted` saves every non-empty field.
- Fix: it saves only a field whose text differs from the file on disk
  (Windows line ends are no change), and takes `replaced=`: the fill,
  simulate and upload routes pass ("data.exp",), the file they write.
- After: no notice when nothing changed; "Saved model.bngl first." when
  only it did; data.exp's time is the action's.
- Tests: `test_an_action_saves_only_what_changed_and_never_the_file_it_writes`.

## SB-19
- Reproduced: yes: "Not started: The PyBNF fork at ... does not provide
  fit_type = pf: there is no such directory." above the identical alert.
- Fix: `_sandbox_start`'s refusal is one pointer when the preflight's
  reason is the page's own machine alert: "Not started: this computer
  cannot fit yet. The notice under Save says what to do." The alert's
  headline is plain: machine_problems puts "The fitting engine is not
  installed." before the engine's sentence, so the notice reads "This
  computer cannot fit yet: The fitting engine is not installed." and the
  engine's words and the remedy are its tip (Check's facts the same).
- Tests: `test_the_engine_missing_reason_leads_with_plain_words`;
  test_sandbox_audit's preflight test reads the pointer and finds the
  reason and remedy in the alert; test_sandbox_guard's and
  test_sandbox_machine's pins of the first sentence read the headline.

## SB-20
- Reproduced: yes: a failed run's `.sb-rsum` bottom border 14 px above the
  Compare section's top border, nothing between.
- Fix (tabs/sandbox.css): `.sb-rsum + .sb-rsec{border-top:0;padding-top:0}`.
- After: one rule, at 1280 and 390 px.
- Tests: `test_a_run_with_no_plot_keeps_one_divider`.

## SB-21
- Reproduced: yes: "particles 500 10000", "n_obs 20 16", "data Arizona
  2026-10-17 typed".
- Fix: `sandbox_export.SETTING_LABELS` and `_setting_text` (10,000); each
  changed setting carries its label; the template prints it, and "as
  written" for data with no source sidecar.
- After: "Particles 500 10,000", "Data rows 20 16", "Data Arizona
  2026-10-17 as written".
- Tests: `test_what_changed_reads_in_words_with_formatted_numbers`;
  test_sandbox_export's pin of the settings dict reads the label and text.

## SB-22
- Reproduced: yes: the dataset start's run shows the card with w and a
  disabled button whose "?" says it reads the hub's donor bank.
- Fix: the route passes `dataset_start` (the model's origin is
  SHIPPED_DATASET) and the template skips the card for it; the stats say
  the donor streams in words ("Donors: both streams", "FluSurv-NET only",
  "admissions only", "none qualified") with no "?", and the "w" stat goes
  (the input above holds it).
- Tests: `test_a_dataset_start_gets_no_oracle_card_and_the_donors_read_in_words`;
  test_sandbox_oracle's pin of the w stat reads the Donors stat.

## SB-23
- Reproduced: yes: population_size 1 and max_iterations 1 in the fold.
- Fix: the fold leaves out fit_type, population_size and max_iterations
  (the run still writes them: engine_settings is unchanged).
- Tests: `test_the_engine_keys_fold_leaves_out_the_plumbing`.

## SB-24
- Reproduced: yes: the alert and the button's "?" with the same sentence.
- Fix (sandbox.js): the button is off with no reason tip; the alert says it.
- Tests: `test_the_load_off_reason_is_said_once`.

## SB-25
- Reproduced: in code (the upload of a one-row CSV was refused before the
  notice here): "{rows} weeks", "{dropped} missing weeks dropped",
  "{rows} simulated weeks".
- Fix: `_weeks(n, what)` in the three notices.
- Tests: `test_count_words_go_singular`; test_sandbox_data's two pins read
  "1 missing week dropped".

## SB-26
- Reproduced: yes: the failed run's zip held meta.json, m.bngl, data.exp
  and priors.conf, not its pf_runner_0.err.
- Fix: run_zip adds each non-blank pf_runner_*.err, its last 64 KB.
- Tests: `test_the_run_zip_carries_the_engines_messages`.

## UI-16
- Reproduced: yes: a model made from the SIR example read "Changed" as
  the example file's time (the tree's), not its creation.
- Fix: add_example touches the copied files, as copy_model does.
- Tests: `test_a_model_made_from_an_example_is_changed_now`.

## UI-19 (medium confidence)
- Reproduced: yes: labels 11 and 12 px at 100% and at 160%; 8 px on a
  390 px phone (the drawing shrinks to the card).
- Fix: the View never shows the drawing below one user unit per pixel
  (min-width the drawing's width times the root font over 16 px, the
  height the same way), so the labels are 11 and 12 px at 100%, 1.6x at
  160%, and a narrow card scrolls sideways (`.mv{overflow-x:auto}`).
- After: 14 and 16 px label boxes at 100% and on the phone (the card
  scrolls), 22 and 25 px at 160%.
- Tests: `test_the_diagram_never_shrinks_its_labels_and_follows_the_text_size`.
- Note: the size is read when the drawing is made (a text-size change
  takes effect on the next page load, as the hunt measured).

## Checks
- New app/tests/test_sandbox_polish.py (12); every sandbox test file with
  test_contactmap, test_console_qol, test_fewer_marks, test_perl_bng_env,
  test_experiments and test_ui_kit: 549 passed, 6 skipped. ruff (the gate)
  clean.
- Full suite (FLUBNF_HUB=/nonexistent, test_doctor deselected: this container's Python): 4230 passed, 159 skipped, 0 failed.
- Output check: not needed (the Sandbox only).
- Windows: the zip reads bytes; the touch and the mtime test use the OS
  clock; the templates, scripts and tests are ASCII.
- For Ely: none.

## Patch
G31/proposal.patch (git diff origin/dev...proto/G31-B)
