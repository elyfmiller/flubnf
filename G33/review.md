# G33: review (B) of #95, head df63b25f

Approve.

Read: the whole diff against dev 2dbf6a80 (6 files). It is the decision as written: A's patch with B's move of test_theme_and_harmonic's pin and the test_week_ticks pin moved to the deferred pair; the Status cell reads "fixed in #95".

Checks on the PR head:
- ruff (the gate) clean.
- Models polish, theme and harmonic, week ticks, models tab, marks, pages, kit, layout, site build and phone-table tests: 172 passed, 21 skipped.

Live (the PR tree over a state with one Groundhog-only run; 1280 px light and 390 px dark):
- MO-12: /models reads "No forecasts from this model yet" with "The latest real-time run (2026-10-17 · 11-10 08:15:40) has none from this model." under it; the page's one mark is the record's "i".
- MO-16: /model/pf2s and /models load no chart script (DOMContentLoaded 125 to 183 ms and 43 ms); /model/analogue loads plotly.min.js and charts.js deferred and draws its fan; no page errors.
- HM-17: the forcing figure reads e+ε₁, 1.0 and e−ε₁ on the β(t)/β₀ axis, on Home and the model pages.
- CI on df63b25f was still running when this was written; A merges once it is green.
