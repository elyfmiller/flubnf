# G31: compare (B)

A's patch applied cleanly on fb4fa7f; the sandbox, contact map, marks, pages and layout tests give 604 passed, 6 skipped; the gate's ruff is clean. The "sites" model served from A's tree: at 390 px the drawing is laid out 332 units wide (viewBox 0 0 332 273) and shown 1:1, no sideways scroll; at 1280 px and 160% text it is shown at 1.6x; the caption reads "3 molecule types, 2 rules in the saved model".

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| SB-07 | `rules` from `rule_flow`, `reactions` from `network_graph`, both captions read them, `VIEW_VERSION` 3, the Model svg labelled "model: ...". | `rules` from `rule_flow` with a fallback to the drawn count; the network caption from the API's counts; no version bump. | A's. The cached flow of a model drawn before the fix has no `rules`, so B's fallback keeps showing "1 rule" until the model is edited; the version bump redraws it (criterion 1). |
| SB-18 | Saves and names only what differs from disk; Fill, Simulate and Upload save an edited data.exp but never name it. | Same, but `replaced=("data.exp",)` skips data.exp for Fill, Simulate and Upload. | A's. `simulate_data` keeps data.exp's time rows and Fill reads its header, both from disk; B's drops an edited data.exp before they read it (criterion 2). I had this wrong. |
| SB-19 | "Not started: this computer cannot fit yet; the notice above the editor says why.", given only when the page will show the notice (`machine_problem()`); the full reason otherwise. | "... The notice under Save says what to do." | A's. The notice is rendered before the editor card (sandbox.html line 180), above the toolbar that holds Save, so mine points the wrong way; A's guard never points at a notice the page's shorter probe would not show. |
| SB-20 | `.sb-rsum + .sb-rsec{border-top:0;padding-top:0}` | Same. | Same. |
| SB-21 | Lower-case labels, as the table's header; 10,000; "as written". | Capitalized labels; 10,000; "as written". | A's for the case, which matches the table's own header ("run setting", "compared run"). |
| SB-22 | `shipped_state` returns `dataset`; Donors as "both donor banks", "FluSurv-NET donors only", "admissions donors only", "no donors: the plain filter". | `dataset_start` in the route; "both streams", "FluSurv-NET only", "admissions only", "none qualified". | A's: `shipped_state` is where the other shipped facts come from, and "no donors: the plain filter" says what that state forecasts with. |
| SB-23 | The fold leaves out fit_type, population_size, max_iterations. | Same (`rejectattr`). | Same. |
| SB-24 | Plain Load button; sandbox.js disables it and points aria-describedby at the alert. | Same. | Same. |
| SB-25 | Inline singulars. | `_weeks(n, what)`. | B's helper, one place for the three messages (criterion 4). |
| SB-26 | Last 256 KB of each `pf_runner_*.err`. | Last 64 KB. | Either; 64 KB is more than a student needs to read. |
| UI-16 | `add_example` touches the copies. | Same. | Same. |
| UI-19 | The `box` helper in `network()` hoists over the `box` parameter, so every drawing is laid out 640 wide; renamed `bounds`; `textScale()` divides the layout units so labels grow with the Display text size. | `min-width` on the svg and `.mv{overflow-x:auto}`, so the 640-wide drawing scrolls sideways instead of shrinking. | A's. It found the root cause: the drawing never read its box. B's keeps the 640 layout, adds a sideways scroll to a 521 px desktop card at 100% text (which had none), and the zoom buttons scroll with it (criteria 1 and 2). Checked live on A's tree: 332 units on the phone at 1:1, 1.6x at 160%, no scroll at either. |

Vote: combine. A's patch, with B's `_weeks` helper (SB-25) and B's 64 KB cap (SB-26). A's test_sandbox_polish.py, with B's two tests for those parts folded in. A decides G31; A implements.
