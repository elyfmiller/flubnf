# G25 sandbox-messages: proposal (A)
Base: origin/dev de64c26 (G23 merged)

How: a dev server (8815, de64c26) and a prototype server (8816), each fresh,
driven by curl (`verify/g25.sh`: Save and run and Simulate data on a model
whose rule names an undeclared Z(); five CSV uploads; Check with three
data.exp texts) and Chromium at 1280 px for Check's headline. No engine
here, so every Check reply carries the machine fact; for SB-14 the browser
check removes that fact in flight (the page then reads as on a computer
with the engine).

## SB-04 (also: WI-11)
- Reproduced: yes, on Simulate data (WI-11's path): the notice "Not
  simulated: BNG2.pl could not simulate the model:" ends at the colon; the
  "?" holds the whole log, "ERROR: Molecule Z() does not match any
  declared molecule types / at line 48" last. Save and run (SB-04's own
  path) stops here first at the missing engine, but it raises the same
  "BNG2.pl could not generate the network:\n" + log (sandbox.py, the
  network step) through the same `_not_done` -> `split_reason`.
- Root cause: app/core/sandbox.py `split_reason` keeps the text's first
  line as the notice; for a BNG2.pl failure that line is the lead-in
  ending in ":", and the log follows. The tip (#tip-flash) is one
  paragraph, so the log's newlines collapse.
- Fix: `split_reason` finishes a first line that ends in ":" with the
  log's ERROR line (else its ABORT line), prefix dropped, plus "(line N)"
  from the "at line N" BNG2.pl writes under it (`_bng_error_line`). The
  tip keeps the whole log; nau.css `#tip-flash{white-space:pre-line}`
  keeps its lines (the flash's tip only; a one-line tip is unchanged).
- After: "Not simulated: BNG2.pl could not simulate the model: Molecule
  Z() does not match any declared molecule types (line 48)", the log line
  by line behind the "?".
- Tests: test_sandbox_messages.py `test_a_bng2pl_failure_ends_with_its_error_line`
  (both lead-ins, ERROR and ABORT-only logs, the CSS rule);
  test_perl_bng_env.py `test_the_sandboxs_netgen_failure_keeps_perls_first_line`
  pinned the notice "BNG2.pl could not generate the network:" (the bug's
  symptom): it now reads "...: Molecule Q not defined".
- Risk: every caller of split_reason (the machine fact, Check's BNG2.pl
  fact, delete and the not-done notices); only a first line ending in ":"
  with an ERROR/ABORT line under it changes. No run path: no output check.
- For Ely: none

## SB-05
- Reproduced: yes. bad_text.csv (date,cases with "ten" in row 3): "No
  column for the group (e.g., target_group, group, location). Found: date,
  cases. Choose which column holds each." two.csv (date,cases,deaths):
  "Two columns could be the value: 'cases' and 'deaths'. Choose one (e.g.,
  cases), or keep only one in the file." The Sandbox's upload has no
  column control.
- Root cause: (1) app/core/datasets/reading.py `_one_series` gives up on
  any text column, so a word in a one-value file falls to the grouped
  reading and its "no group column" refusal; (2) the store's advice is the
  Data tab's (it has the mapping), shown as is by routes/sandbox.py.
- Fix: (1) `_one_series` takes the one other column as the value when its
  name is a value alias (cases, count, value...), so the checks name the
  word; (2) routes/sandbox.py `_sandbox_columns_advice` rewrites the two
  "choose" sentences for the Sandbox: "... Name the columns so in the
  file, or upload it on the Data tab, where the columns can be chosen." and
  "... Keep only one in the file, or upload it on the Data tab, where the
  column can be chosen." The Data tab's own words are unchanged.
- After: bad_text.csv: "The 'cases' column must contain numbers only: 1
  value(s) are not (row 3; e.g., ten ...)"; two.csv: the Data tab sentence.
- Tests: `test_the_sandbox_upload_sends_a_column_choice_to_the_data_tab`.
- Risk: reading.py is the store's reader (Data tab too): only a file whose
  single non-date column is named as a value and holds a word changes,
  from a wrong refusal to the right one. No run path.
- For Ely: none

## SB-10
- Reproduced: yes. rates.csv: "data.exp filled: 5 weeks of rates (one
  series) ... Rates: set objfunc in priors.conf." tip "... The default
  objfunc expects counts." No value is named anywhere (SANDBOX.md, the
  examples, the help).
- Root cause: routes/sandbox.py `_sandbox_fill_flash`.
- Fix: say plainly what the Sandbox fits: "Rates: a fit reads counts, so
  load counts to fit this data." The tip names the likelihood the Sandbox
  writes: "The fit's likelihood, objfunc neg_bin_dynamic, is for weekly
  counts." (sandbox_bngl.py's default).
- Tests: test_sandbox_upload.py's rates pin updated to the new sentence
  (the old words are the bug).
- For Ely: whether the engine offers an objfunc for rates (it cannot be
  run here); if it does, the notice can name it.

## SB-14
- Reproduced: yes. data.exp "-3 5 / -2 6 / 1 8": with the machine fact
  removed in flight, "Worth a look: 1 note; the model can run." above "data.exp
  has a row at t = -3, at or before the model's start time ... every row
  must come after it".
- Root cause: sandbox.js's headline promises a run whenever there are only
  notes and the machine is ready; ROW_BEFORE_START and KEY_UNKNOWN stay
  notes (test_sandbox_check pins that, and the run's own check is the
  engine's).
- Fix: sandbox.js reads the reply's codes; when ROW_BEFORE_START or
  KEY_UNKNOWN is among them the headline is "Worth a look: 1 note." No
  new fact (the facts' keys are pinned), no new words.
- After: "Worth a look: 1 note." for that file; a scale note alone still
  reads "...; the model can run."
- Tests: `test_checks_headline_promises_no_run_above_a_note_that_says_it_stops`.
- For Ely: none

## SB-15
- Reproduced: yes. data.exp "1 inf / 2 5" and "1 1e400 / 2 5": Check
  ok:false, problems ["float division by zero"], no facts.
- Root cause: sandbox_check.py `_scale_note`: sum(obs) = inf, ratio 0,
  then 1/ratio.
- Fix: read_exp's rows are checked in Check: a row holding inf is a
  problem naming its t (code EXP_UNREADABLE, no new code); `_scale_note`
  skips non-finite values and returns no warning when the ratio is not a
  finite positive number.
- After: "data.exp has a row at t = 1 whose value is not a finite number:
  write the week's count, or a negative value for a missing week", and
  the rest of the report (2 rows, ...).
- Tests: `test_check_names_a_value_that_is_not_finite` (inf and 1e400).
- For Ely: none

## SB-27 (medium confidence)
- Reproduced: yes. blankval.csv: "... All rows must have a value; delete
  rows for weeks not reported."; gap.csv (that row deleted): "Missing
  weeks detected ... one row per week per group."
- Fix: checks.py drops "; delete rows for weeks not reported" (the hint's
  words); the gap rule itself is the known Open item, unchanged.
- Tests: `test_a_blank_value_gives_no_advice_that_leads_to_the_gap_rule`.
- For Ely: none

## Checks
- New app/tests/test_sandbox_messages.py (5): each fails on de64c26 and
  passes here. Sandbox, dataset, problem_codes, marks and layout tests:
  813 passed. ruff clean.
- Full suite (FLUBNF_HUB=/nonexistent): 4217 passed, 160 skipped, 1 failed:
  the netgen pin above, updated; that file then passes (56 passed with the
  machine and messages tests).
- Output check: not needed (no run path; reading.py's change reaches only
  a file it refused before).
- Windows: no paths or encodings touched; the CSS and JS are ASCII.

## Patch
G25/proposal.patch (git diff origin/dev...proto/G25-A)
