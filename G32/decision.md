# G32: decision (by B)
Decision: A (proto/G32-A), as proposed.
Implementer: A
Why: both votes are A (A's compare is not needed; B's compare.md gives the reasons per bug). Criterion 1: A's OU-17 keeps acronyms and A's OU-14 also turns a coming round due at its open. Criterion 2: A's rules digest keeps a kept check from outliving the rule that made it, and A's once-per-flip reload cannot loop on a browser clock ahead of the server's. Criteria 4 and 5: A's OU-10 adds no Methods fold.
Notes for the implementer: the base is now def45dbe (#84 and #61 merged); the patch applies cleanly there. Optional: a node test of the countdown script (B's test_output_polish.py has a harness in the style of test_output_freshness) and one entry per path in the kept checks.
Left for Ely: none
Not reproduced: none

Heads-up (B, after running the full suite on my own proposal): `app/tests/test_which_run_shows.py::test_outputs_words_state_the_rules_it_follows` (G06) pins the Output title's words "from the newest complete run on all 53 locations, else the newest complete run, else the newest run that wrote one; a run made in the round's own week comes before a later vintage run". A's three-line "i" fails it too (checked on A's patch at def45dbe: 1 failed, 8 passed). The bug report shows the long text is the bug, so the pin moves to the new words; say so in the PR, as the template asks.
