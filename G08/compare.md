# G08: compare (B)
A's patch applied on b8bf2b2 (scratch tree): its 5 tests and the related
files (us_national, retro_player, season_run_marks, results_prep,
report_parity, datasets, custom_retro, datasets_ui, upload box, layout,
design pass): 333 passed; the F gate clean. A's `resolve` on B's three
live replays: the 2-state 2026-27 officials only with "only 2 of the 52
jurisdictions were replayed, so their forecasts do not sum to the nation";
the fitted 6-state panel (unscored) "US national (fitted)"; the whole
2025-26 "US national (sum of 52 states)".

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| RE-01 | `resolve` reads the record's settings (locations, national); fewer than 52 replayed and no fitted US: officials only with the reason above; a record without settings keeps today's behaviour | `JURISDICTIONS = 52`; `resolve` refuses the sum when the scores cover fewer; the 2-state fixtures of test_us_national, test_results_prep and test_report_parity made the whole set (a 52-state frame; `JURISDICTIONS` patched to the tree's count) | A's: the scope is what the replay was asked for, said in the reason's words; no test fixture moves (4). B's scores-based count also refuses a whole replay with one state unscored, a case neither bug names. |
| RE-10 | a tag "pooled, N jurisdictions" from the scored frame's count (none while unscored) | "N jurisdictions pooled" from the record's locations, else the frame | Equal; A's as the base. |
| RE-14 | `pooled_scope_note(n)`: "the N replayed jurisdictions" or "the 50 states, DC and Puerto Rico"; "their sum" gone (the aggregated row's own note says it) | the same, with ", their sum," kept for the aggregated row | Equal; A's shorter (5). |
| RE-17 | `checks._sum_group`: counts, three groups or more, the one group that on every full week (two at least) equals the others' sum is the national row; two pinned asserts updated | left for Ely: the national row is a spelling by owner decision (2026-09-24) | A's (1): the hunt's expected is the aggregate kept beside the pool, its first hint is this detection, the spellings stay as decided and a stored dataset keeps its record. The PR should say the rule gained this second criterion, so Ely sees it. |
| UI-11 | the page resolves unscored too (`allow_aggregate=False`); `resolve` answers fitted when the record's `national` is set | the same, from the record's locations naming US plus a stored week | Equal; A's simpler. |

Vote: A.

Vote (final): combine, as A proposes: A's RE-01 (the record's scope) and
UI-11 (the record's `national`); B's `pooled_scope_note(n, provenance)`
for RE-14; the RE-10 tag with B's count (the record's locations, else the
scored frame); RE-17 for Ely, A's detection dropped (an existing test
pins that "Overall" is not national, and the spelling is the 2026-09-24
decision).
