# G25 sandbox-messages: proposal (B)
Base: origin/dev f96ce5a (G22 merged)

Reproduced on a server from the prototype's tree with a copy of the SIR example whose infection rule makes Z() (Check, Save and run, the network and contact-map APIs), the hunt's CSVs (bad_text, two, rates, blankval, gap) uploaded to a Sandbox model, and data.exp rows "1 inf", "1 nan", "-3 5". No run path: no invariance check. The real BNG2.pl runs here, so the BNG2.pl texts are the real ones.

## SB-04 (also: WI-11)
- Reproduced: yes. Check and Save and run (through the same refusal) and both model-view APIs gave "BNG2.pl could not generate the network:\nABORT: Reaction rule list could not be read because of errors.\nBioNetGen version 2.9.3\n...\nERROR: Molecule Z() does not match any declared molecule types\n  at line 48": the notice is the first line, ending in the colon, and the one useful line is the last of the tip.
- Root cause: `sandbox.py` (netgen) and `contactmap._run_bng` build the text as "BNG2.pl could not <what>:\n" + `pf.bng_failure_text(r)`, whose order is stderr's first line, stderr's end, stdout's end; `split_reason` takes the first line as the notice.
- Fix: `pf.bng_said_why(said)` picks BNG2.pl's own reason out of what it said: the ERROR line with the "at line N" that follows it as "(line N)", else the ABORT line, else the last line. `pf.bng_could_not(what, r)` builds the refusal: "BNG2.pl could not generate the network: Molecule Z() does not match any declared molecule types (line 48)" on the first line, then everything BNG2.pl said (the tip, unchanged, banner included, so `bng_started` still reads it). Both raisers use it (`sandbox.py`, `contactmap.py`). Live: the Check problem, the network API's error and the contact map's error all start with that line; `split_reason` gives it as the notice and the log as the tip.
- Tests: test_perl_bng_env `test_a_bng_refusal_puts_its_own_reason_on_the_first_line` (new); the two pins of the colon-ending notice updated (test_perl_bng_env, test_sandbox_machine).
- Risk: every BNG2.pl refusal text (netgen, contact map, network view) gains the reason on its first line; the check's `startswith("BNG2.pl could not")` and `bng_started` tests still hold. No change for a BNG2.pl that never printed its banner (`bng_broken_message`).
- For Ely: none

## SB-05
- Reproduced: yes. bad_text.csv (date,cases with "ten"): "No column for the group (e.g., target_group, group, location). Found: date, cases. Choose which column holds each." two.csv: "Two columns could be the value: 'cases' and 'deaths'. Choose one (e.g., cases), or keep only one in the file." The Sandbox's upload pane has the file input and the Values select only.
- Root cause: (a) `reading._one_series` refuses a file with any column of text, so a count column holding a word is read as "could be a group under a name no alias knows" and the group is reported missing; the word itself is never named. (b) The two "Choose" sentences are the Data tab's advice (its upload box has the column mapping) and come through `datasets.ingest` unchanged.
- Fix: (a) `_one_series` treats a text column under a value name (cases, count, value, ...) as the value column, so the checks name the cell: "The 'cases' column must contain numbers only: 1 value(s) are not (row 2; e.g., ten (2024-01-06, bad_text))." A text column under any other name is refused as before (it could be a group). (b) `sandbox_data._said_here(problem)` rewrites, by problem code (`missing_columns`, `ambiguous_columns`), the "Choose ..." sentence into the way here: "The Data tab's upload can say which column is which; a dataset stored there is offered here under Load data." and "Keep only one in the file, or choose it on the Data tab's upload; a dataset stored there is offered here under Load data." The Data tab's own box is untouched.
- Tests: test_sandbox_upload `test_a_word_in_the_count_column_is_named_not_a_missing_group`, `test_column_advice_here_leads_to_the_data_tab` (new).
- Risk: (a) is in the shared reader: a date,count file whose count column holds a word now fails on the word (the right refusal) on the Data tab too, instead of "no group column". test_dataset_lenient (all) passes. (b) is Sandbox-only.
- For Ely: none

## SB-10
- Reproduced: yes. rates.csv: "data.exp filled: 4 weeks of rates (one series), ... Rates: set objfunc in priors.conf." with the tip "The default objfunc expects counts." Nothing in SANDBOX.md, the examples or the engine notes names an objective for rates; `sandbox_bngl` writes `objfunc = neg_bin_dynamic` unless priors.conf overrides it.
- Fix: the note says what is true: "Rates: the fit expects counts." with the tip "The objective (neg_bin_dynamic) reads data.exp as weekly counts, so a rate fits only as if it were one; for counts, multiply the rates by the population they are per." (`routes/sandbox._sandbox_fill_flash`). No setting with no value.
- Tests: `test_rates_load_with_a_word_about_the_objective` updated (it pinned the old sentence).
- For Ely: if the private engine does have a rates likelihood, its name and a line in SANDBOX.md would be the better fix; none is recorded, so the note stops pointing at a setting with no value.

## SB-14
- Reproduced: yes. data.exp "-3 5 / -2 6 / 1 7": the API's warning "data.exp has a row at t = -3, at or before the model's start time -1 ... every row must come after it" under the page's "Worth a look: 1 note; the model can run."
- Root cause: sandbox.js builds the warn headline as notes + "; the model can run." whenever the machine can fit.
- Fix: the warn headline is "Worth a look: 1 note." (sandbox.js, both places); "the model can run" stays only on the green "No problems found:" headline. The notes are not retiered: KEY_UNKNOWN and ROW_BEFORE_START are warnings in `problem_codes.CODES`, and the golden file says a code never changes tier.
- Tests: test_sandbox_workbench `test_sandbox_js_keeps_the_consoles_rules` pins the one place.
- Risk: none beyond the headline.
- For Ely: none

## SB-15
- Reproduced: yes. data.exp "1 inf" (and 1e400): ok false, problems ["float division by zero"], every other finding lost. "1 nan" checked fine, and a NaN row is a run's way of writing a missing week (test_sandbox's `test_the_run_api_answers_for_a_data_row_written_nan` runs one), so NaN stays accepted.
- Root cause: `read_exp` takes any float; `_scale_note` sums the data to inf, the ratio is 0, then 1/ratio.
- Fix: `read_exp` refuses an infinite value in words: "data.exp row '1 inf' holds an infinite value: every value is a count, or negative for a missing week" (code EXP_UNREADABLE, as the other unreadable rows). Check lists it as a problem and the rest still reports (the network generates, the priors are read). `_scale_note` leaves non-finite values (inf, NaN) out of both totals, so a model that blows up never divides by zero either.
- Tests: test_sandbox_check `test_a_value_that_is_not_finite_is_named_and_the_rest_still_reports` (new; inf, 1e400, -inf refused; nan not; the scale note with an inf expected and a NaN observed).
- Risk: `read_exp` also serves a run's prepare, which now refuses an infinite value up front ("Not started: data.exp row ... infinite value"); such a run could not have fitted. A NaN row runs as before.
- For Ely: none

## SB-27
- Reproduced: yes (medium confidence). blankval.csv: "... All rows must have a value; delete rows for weeks not reported." then gap.csv: "Missing weeks detected ... The data should have one row per week per group."
- Root cause: `checks.value_na`'s advice for a grouped file leads straight into the gap check.
- Fix: the sentence says what loads: "Every row must have a value, and a grouped file has a row for every week; a hubverse file (date, location, value) may hold NA for a week not reported." (`checks.py`). The gap message is unchanged.
- Tests: test_dataset_lenient `test_missing_values_quote_the_cell_its_date_and_group` pins the advice.
- Risk: the Data tab shows the same sentence (shared checks); the hubverse NA path is the existing one (dropped and counted).
- For Ely: none

## Checks
- Targeted (test_sandbox_check, _upload, _machine, _audit, _data, _editor, _guide, _workbench, test_perl_bng_env, test_contactmap, test_dataset_lenient, test_problem_codes, test_dataset_upload_box, tests/test_dataset_cli, test_fewer_marks): 461 passed, 6 skipped. Full suite (FLUBNF_HUB=/nonexistent): 4213 passed, 159 skipped; the two tests/test_doctor.py failures are this container's Python and pass in CI. ruff (the gate) clean on app/ui; `app/core/engines/pf.py:49` has an unused import that is dev's, untouched.
- Windows: text only; no path or encoding change.

## Patch
G25/proposal.patch (git diff origin/dev...proto/G25-B): pf.py, sandbox.py, contactmap.py, sandbox_bngl.py, sandbox_check.py, sandbox_data.py, datasets/reading.py, datasets/checks.py, routes/sandbox.py, sandbox.js, six test files.
