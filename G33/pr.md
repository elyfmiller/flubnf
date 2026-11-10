# G33: pr (A)
PR: https://github.com/elyfmiller/flubnf/pull/95 (fix/G33-models-polish into dev)
Head: df63b25ff8622fa6eee2c894c27c7b4701c671ac (853aedf1 the change, then the Status cell)
Base: dev 2dbf6a80 (#94 merged)

The decision as written: A's patch with B's move of test_theme_and_harmonic's pin (the middle label 1.0, no beta-0 factor). test_week_ticks' pin moves to the deferred pair. The PR says both.

Checks: ruff gate clean; models polish, theme and harmonic, week ticks, models tab, marks, pages, kit and layout tests 164 passed; full suite 4691 passed, 216 skipped, 0 failed. Live (1280 light, 390 dark): /models reads the reason under the empty state with no mark; /models and /model/pf2s request no chart script; /model/analogue loads both deferred and draws its fan; the figure reads e+e1, 1.0, e-e1.

B: please review the head above and write G33/review.md.
