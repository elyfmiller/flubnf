# G20: compare (A)

B's patch applied to origin/dev 0e9e90b on a scratch worktree. The two
proposals take the same route on eight of the ten bugs; they differ on
ME-07's grid, ME-10, MO-23's width, DA-10's details and ME-08's markup.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| HM-06 | `pipe figscroll`, region "How it works (scrolls)" | the same, "Weekly forecasting workflow (scrolls)"; "/" added to test_console_qol's wide-figure test | B: the name is the drawing's own plus "(scrolls)", as every other figscroll region is; the qol test now covers Home |
| HM-09 | table in a figscroll region | the same | equal; B's name ("Measured performance table") matches its card |
| ME-06 | stacked rows, data-label cells | the same, in a second phone block after the table's rules | equal |
| ME-07 (MO-19) | two-column grid, cells flow down the second column | three columns with per-cell `grid-column`, symbol capped at 6rem | **A**: B's fails test_reading_column (no `grid-column` in nau.css); see below. B measured the pf2s table too |
| ME-08 | `mt-rec`; seasons via `replace("-", "‑")`; number heads may wrap | `mt-rec`; `&#8209;` in the literals with `\| safe`; phone padding | equal on the symptom (332 in 332 both). A's needs no `\| safe`; B's leaves the headers as they are. B's call |
| ME-09 | `fit-content(40%)` | the same | equal |
| ME-10 | `.uk-fold-sum{flex:1 1 0}` | `.uk-fold-sum{max-width:calc(100% - 1.4em)}` | **B.** A's makes the title take the whole line, so a badge passed as `after` moves to the right edge at every width: Methods' "N settings", the Variables count, the run page's "retired hub names". That is a change outside the bug (criterion 2). B's keeps a short title's own width |
| MO-23 | the harmonic in a figscroll; `.nw` around "s ∈ {A, B}" and "share A / (A + B))" | the same, plus `dg-harm` at its drawn 560 px (A's took the drawings' 620) and `.nw` around the whole Binomial(...) | B: the drawn width, not a scaled-up one |
| DA-10 | name and heading wrap anywhere; actions nowrap in the table at every width | the same, plus `td.dsname{min-width:12rem}`; nowrap only above 600 px | **B.** B found the name column collapsing at 768 px / 160% with anywhere alone, and keeps a stacked phone row's wrap |
| DA-11 | `#datasets .tablewrap` scrolls, positioned | the same, merged with `.dsup .tablewrap` | equal |

One fix B's patch needs (found running more of the suite than B's
targeted set): `app/tests/test_theme_and_harmonic.py::test_harmonic_figure_renders_on_every_surface`
fails, `assert 2 == 1` on Home. It counts the figure by the prefix
`aria-label="Seasonal harmonic`, and the new scroller "Seasonal
harmonic (scrolls)" matches it too (Home, Models, Methods and the
pf2s page would each count double). A's proposal named the scroller
"Harmonic figure (scrolls)" for this reason. Either:
- name the scroller so the prefix does not match (A's names: "Harmonic
  figure (scrolls)", "Two-strain harmonic figure (scrolls)"), and B's
  `test_the_harmonic_scrolls_on_a_phone_and_set_expressions_hold_together`
  reads the new names (checked: with that rename, the harmonic test
  passes and only B's own pin needs the new name); or
- keep B's names, which follow the convention, and tighten the
  harmonic test's needles to the figure's own label (`Seasonal
  harmonic:` and `Two-strain seasonal harmonic:`), since what it counts
  is the figure, not its scroller.
I lean to the second: the names stay in the convention and the test
still counts each figure once. B decides.

Full suite on B's patch as sent (FLUBNF_HUB=/nonexistent, origin/dev
0e9e90b): 3596 passed, 155 skipped, 2 failed. The harmonic test above,
and:
- `app/tests/test_reading_column.py::test_no_grid_for_prose_anywhere`:
  `AssertionError: .eqvars-t td:nth-child(2)`. The test allows no
  `grid-column` rule in nau.css (only the gone `.valpanel` list), and
  ME-07's phone grid places `td:nth-child(2)`, `(3)` and `(4)` with
  `grid-column`. A's ME-07 passes it: `grid-template-columns:auto
  minmax(0,1fr)` with the symbol `grid-row:span 3`, so the meaning, the
  units and the source flow down the second column with no per-cell
  placement. B's layout (units and source side by side under the
  meaning) needs a placement the test forbids; either take A's flow
  (units and source on lines of their own, the row a line taller), or
  ask whether the test's rule may change, which is a decision outside
  this group. I lean to A's flow.

Vote: combine: B's patch, with the harmonic test fixed as above (B's choice of the two) and ME-07's phone grid as A's (no `grid-column`), so the full suite passes.
