# G08: review (A)
PR #57, head 2108bce (8ba22de the change, 2108bce the Status cell).

Approve.

What I checked
- The diff is the decision: A's `resolve` for RE-01 (the record's `locations`) and UI-11 (the record's `national`; the route resolving unscored too), B's `pooled_scope_note(n_states, provenance)` with "the 50 states, DC and Puerto Rico" and ", their sum," for the aggregated row only, the "N jurisdictions pooled" tag from the record's states, else the scored frame; A's RE-17 detection left out and RE-17 for Ely in the Status cell and the body. Author and committer Ely F. Miller <efm46@nau.edu>; no attribution lines or forbidden words in messages, diff or body; no footer.
- On the head: test_retro_partial_scope, test_us_national, test_retro_player, test_season_run_marks, test_results_prep, test_report_parity, test_ui_layout and the retro files: 235 passed, 4 skipped. `ruff check --select F821,F823,F811,F401 app/ui` clean.
- Live, a server from the head on my baseline hub copy: a 2-state Groundhog replay of 2026-27: no "sum of states" anywhere, the reason "only 2 of the 52 jurisdictions were replayed, so their forecasts do not sum to the nation", the note "Pooled relWIS covers the 2 replayed jurisdictions", the tag "2 jurisdictions pooled". (UI-11's fitted label checked on my prototype of the same code, on the hub without the baseline.)
