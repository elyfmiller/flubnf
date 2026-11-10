# G34: review (A) of #96, head e0c4abba

Approve.

Read: the whole diff against dev bc844cf2 (10 files). It is the decision as written: A's ME-16 notes (each one plain sentence, no screen figure in the narrowing note; knob defaults, keys and help lines untouched) and ME-18 (the two Policies folds go on from their titles); B's ME-04 (the id on the Measured performance card, and site_build's `_PERF_CARD` pattern follows it), ME-05 (the current section is the last one past the band under the bar, and the last of all at the page's end; the bar is measured again when the Print button wraps it), ME-13 (the Range column says the engine's rule: "0 ≤ low < high", and "0 < low < high" for a log-uniform prior, which is pf.priors_for's check), ME-21 (cards, folds and long tables may break; figures, fact rows and table rows never; headers repeat) and ME-22 (.mt-scroll and the setting tables focusable regions with a label and the focus outline). The Status cell reads "fixed in #96".

Checks on the PR head:
- ruff (the gate) clean.
- Methods polish, Oracle card words, Forecast text, Oracle text, knobs, site build and smoke, pages, marks, kit, layout, Methods and Model settings tests: 323 passed, 22 skipped.

Live (the PR tree over a state of four all-53 Groundhog dates, 1280 px):
- ME-04: each of the ten contents chips lands its section's title 24 to 26 px under the bar (Measured performance included) and marks that chip; #policies, which cannot reach the band, is marked at the page's end.
- ME-05: scrolling down the page, the marked chip is the section at the bar's line; at the end, the last chip.
- ME-13: the five prior ranges read "0 ≤ low < high" (three) and "0 < low < high" (two); no "lo < hi" left.
- ME-21: Print / Save as PDF gives 17 pages; the blank tail of each page but the last is at most 30% (page 6; dev had pages 65 to 93% blank).
- ME-22: all twelve sideways scrollers are focusable regions with a label.
- ME-16, ME-18: by the tests (the notes' words and lengths, the folds' first sentences).
- CI on e0c4abba: B merges once it is green.
