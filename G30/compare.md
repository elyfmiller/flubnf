# G30: compare (A)

Both proposals reproduce all six and take the same line on each; the
differences are below. I applied B's patch on a scratch tree only to read
it; the points rest on the code.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| FC-26 marks | The newest line stays above the box with no "?" (`tip=not data_issues`); the box loses its count badge and both kinds of "i"; the flag gets an id and stays the select's description (`aria-describedby="di-flag-<fips>"`). | The line moves inside the box as its head (`bare=True`), "N states" kept as a fallback; the flag stays, the select loses its describedby. | Same marks either way (2 before a run). B's head is the literal "merge into the box"; A's is the smaller change and keeps a description on each select. Either; I lean A's, with the describedby in any case. |
| FC-26 Settings "i" line | Only when the box shows: "Data issues: each state is preset to the recommended choice, for this run only. What each choice does" (a link to /methods#mt-newest). | Always: "Data issues: a state whose newest week reads 0, collapsed or was not reported. Each select starts on the recommended choice; the choice is this run's and is recorded with it." No link. | A's: fewer words, shown only when there is a box, and it reaches the choices it no longer explains (criterion 5). |
| FC-26 Results | anchor_notes_row and zero_anchor_row skip the states chosen in Data issues (`skip=`); data_issues_row is their one row (what came of them, each state's issue, choice and engine note in its "?"); without a choices record it returns None, and the two rows say what the engines did, as before. | zero_anchor_row shows only without data_issues_row; Unreported newest weeks still shows the chosen states; `nrow = drow or zero_anchor_row` also in dataset_results_html. | A's. B's leaves an unreported state chosen in the box in two rows (Alaska: "1 location anchored earlier" and "Alaska: not reported; from 10-10"), which B's own After counts as two "?" (criterion 1). B's fallback also turns a dataset run's "Newest week reading 0" row into "Data issues" whenever a zero-anchor rule fired, and a dataset run has no Data issues box (criterion 2). A's keeps dataset results as they are. |
| FC-27 choice words | `CHOICE_WORDS["carry"]` = "from the last reported week"; set_aside "both from the week before". No dates. | `reported.choice_text(entry)`: "both from 10-10", "from 10-10", "kept", "left out"; the carry entry records its from_week; `reason_text` for an old "no row". | B's: they are the box's words, with its dates, as the bug expects (criterion 1). Recording from_week for carry is safe: rules_for reads it for set_aside only, and B's output check matched. |
| FC-27 run-wide rule | "Groundhog when the newest week reads 0: level" (the Run form's label, as G28's `_settings_words`). | "Newest week reading 0: level" (the knob's label). | A's. That knob is a decision key and never appears in the panel. The only place a student sets it is the Retrospective form, labelled "Groundhog when the newest week reads 0"; the panel's "Newest weeks reading 0" is the other knob, data.trailing_zero. |
| FC-27 engine notes | `_note_words` drops "zero-anchor " from the notes the Results tips quote (zero row and Data issues row). | Drops it in data_issues_row's flag lines only. | A's for the zero row's tip, which still says "Groundhog, Arizona: zero-anchor level: ..." in B's. |
| FC-28 panel | Both folds go, with the macro's group tag, the two folds' CSS and the JS selector only they used. | Both folds go. | Same. A's also removes the dead code. |
| FC-28 hints | Replicates "... per-state numbers ship with 3 or more."; jitter "How far each fitted value is nudged between weeks, so the particles stay varied." (the Sandbox's words); seed "Sets the reporting rate and first infections from the admissions to date or the expected total."; window "... epiweeks of the forecast week." (as oracle.bandwidth). The technical facts move to each knob's note, shown on Methods only: "The Liu-West kernel scale h; the sealed record ran 0.30.", "It pins rho*mult and i0.", "The sealed record ran 2." | Four hints rewritten; the facts dropped. | A's: Methods (its table reads the help) keeps what the sealed record ran and what the seed pins (criterion 2), and the panel loses them. B's "What seeds the fit" says less than "the reporting rate and first infections". |
| FC-28 Methods fold | Setting, why, value. | Value, set to, why; ids per row. | Either. |
| FC-29 tip | "a day anchors on the latest archived week on or before it, except a Saturday the archive skipped, which is refused." | "a Saturday must be an archived week; any other day anchors on the latest archived week before it." | B's: shorter and plainer. |
| FC-29 refusal | Measures from the typed date back to the nearest snapshot. | `_gap_weeks`: the gap's own width, from the snapshot before to the one after; "(usually a holiday week)" for one or two; "nothing after X yet". | B's. Mine is wrong a week into a long gap: 2024-05-04 is one week after 2024-04-27, so it would still say "usually holiday weeks" inside a 29-week gap (criterion 1). |
| FC-30 | The inner div becomes role=group; the CSS selector follows it. | `.modes` itself is the group; Real-time pressed in the markup; the old `.modes > [role=tablist]` rule is left behind. | B's markup (the first paint is right before the script runs), without the dead rule. Both keep the aria-selected style for the Sandbox's model-view tabs. |
| FC-33 | `title=""`, files dropped when modified. | Same; test_settings_block's pin updated. | Same. |

Vote: combine. Each part from the better solution:
- **From B's:**
  - FC-27: `choice_text` and `reason_text`, and the carry entry's from_week.
  - FC-29: the tip and `_gap_weeks`.
  - FC-30: the markup, with the dead `.modes > [role=tablist]` rule removed.
  - FC-33: the test_settings_block pin update.
- **From A's:**
  - FC-26: the Results rows (`skip=`; data_issues_row as the one row, None without a choices record; dataset results unchanged) and the conditional Settings line with its Methods link.
  - FC-26: the box (the line above with no "?", the flag describing each select). B's head-in-box is acceptable if B prefers it; keep the describedby either way.
  - FC-27: the run-wide rule's label and `_note_words`.
  - FC-28: the hints, the notes and the dead-code removal.
- The tests from both, de-duplicated into one test_forecast_text.py.
