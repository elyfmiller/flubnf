# G33: compare (B)

A's patch applied cleanly on def45dbe. On it, the Models tab, harmonic, marks, pages, week ticks, fans and site-build tests give 89 passed and 1 failed: `test_theme_and_harmonic.py::test_harmonic_figure_carries_the_design_conventions` still pins "1.0 (&#946;", the old middle label (my proposal moves it: the old label is the bug). Mine had the mirror gap, test_week_ticks' pin of the blocking script pair, now moved as A moved it.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| MO-12 | The empty state alone; the sentence as `<p class="hint md-nofc-why">` under it. | The sentence as a `<span class="hint md-nofc-why">` inside the box, through the empty state's `action` slot. | A's. Both leave one mark on the page; A's keeps `tips.empty`'s contract (the slot is for a link or a button) and the kit's empty state as it is (criterion 4). |
| MO-16 | The pair only with `has_fans`, `defer`; the first draw waits for DOMContentLoaded while the page is still loading, else draws; test_week_ticks' pin takes the deferred pair. | The same markup; the first draw on DOMContentLoaded; the same pin move. | A's: the `readyState` guard costs one line and never loses the draw (criterion 4, same behavior). |
| HM-17 | e^+ε₁, e^−ε₁, 1.0; the axis stays. | Same, with test_theme_and_harmonic's pin moved to the new labels. | Same markup; take B's pin move, or A's full suite will stop there. |

Vote: A, with the test_theme_and_harmonic pin moved as in B's patch (one assertion; the bug report shows the old label is the bug).
