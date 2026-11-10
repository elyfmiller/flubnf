# G33: compare (A)

Both patches applied to def45db and run against the models, harmonic, week-ticks and marks tests. Each fails one old pin the other moved: B's fails `test_week_ticks::test_every_console_chart_draws_through_the_helper` (it pins model.html's blocking pair), and A's fails `test_theme_and_harmonic::test_harmonic_figure_carries_the_design_conventions` (it pins "1.0 (&#946;"). Both pins hold the old behavior that is the bug, so both move.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| MO-12 | The sentence as a `<p class="hint">` under the dashed empty box. | The sentence inside the box, in the empty state's action slot (`.md-nofc-why`, two CSS lines). Its test checks the page's marks are the record's "i" alone, with and without a run. | B's. The reason reads as part of the one notice rather than a loose line under it, and the test covers the passing state the hunt said was missing. |
| MO-16 | Deferred pair under `has_fans`; first draw on DOMContentLoaded behind a `readyState` guard. | The same, with the listener unconditional. | B's. The inline script runs while the page is still loading, so the guard never matters; B's is one line shorter. B's test also covers /model/analogue with no run. |
| HM-17 | e^+ε₁, e^−ε₁, 1.0. | The same markup. | Equal. B's test checks Home, Methods and both model pages; A's checks Home only. B's moves the harmonic pin. |

Vote: B, finished with the one pin it misses: test_week_ticks' model.html pair accepts the deferred form (as in A's patch, `for d in ("", " defer")`). That is finishing B's patch, not combining, so B implements.
