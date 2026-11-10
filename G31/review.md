# G31: review (B) of #91, head e6b029e7

Approve.

Read: the whole diff against dev cd21afa5 (20 files). It is the decision as written: A's patch with B's `_weeks` helper (SB-25) and the 64 KB cap (SB-26); the two conflicts with the engine switch resolved as pr.md says (machine_problems keeps the public-engine branch under the plain headline; What changed keeps dev's engine row, labelled "engine"); the Status cell reads "fixed in #91".

Checks on the PR head:
- ruff (the gate) clean.
- Sandbox, contact map, console QoL, marks, experiments, kit, pages, layout and engine-cutover tests: 603 passed, 5 skipped.

Live (the PR tree over a private hub copy, the G31 fixtures: the SIR example, the two-rule "sites" model, a failed run with a pf_runner_0.err and a stopped one; no engine here):
- SB-07 and UI-19: "sites" at 390 px draws in a 332-unit box shown 1:1 (viewBox 0 0 332 273), at 1280 px and 160% text at 1.6x, no sideways scroll; the svg is labelled "model: 3 molecule types, 2 rules in the saved model".
- SB-19: Save and run flashes "Not started: this computer cannot fit yet; the notice above the editor says why." under the notice "This computer cannot fit yet: The fitting engine is not installed. ?" (the engine's own message in the "?").
- SB-20: the failed run's summary keeps its 1 px rule and Diagnostics has none (border-top 0, padding-top 0).
- SB-23: the engine keys fold lists objfunc, pf_bounds, pf_start_time, initialization and pf_cumulative_observable; no fit_type, population_size or max_iterations.
- SB-24 at 390 px, Start after End: Load is disabled, described by "Load is off: Start 2026-11-01 is after End 2026-10-17.", with no "?" on the button.
- SB-26: the failed run's zip holds meta.json, m.bngl, data.exp, priors.conf and pf_runner_0.err.
- SB-18, SB-21, SB-22, SB-25, UI-16: by the tests (Simulate needs the engine here; the save-only-what-differs rule, the labels and 10,000, the dataset start's card, the singulars and the copy's time are each pinned in test_sandbox_polish.py).
- The model page's marks: the machine notice's "?" (no engine), the files' "i" and the run settings' "i", as on dev (G35 looks at those).
