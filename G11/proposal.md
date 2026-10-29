# G11 groundhog-text: proposal (A)
Base: origin/dev 368e922

Sources: README.md "Measured record". The shipped form since 2026-10-23
scores 0.680 / 0.627 / 0.645, pooled 0.642, on 17,116 cells. The form it
replaced scores 0.702 / 0.651 / 0.653, pooled 0.660, and the pooled form
0.670. The Model lane asked for this in docs/team/model.md (2026-10-23
entry, "App: the Models, Home and Methods pages ... still print the
earlier record"). The kernel wording follows the card (model-metadata
GroundHogCGR 1.3 methods_long) and flubnf/analogue.py.

## HM-01 (also: MO-01, ME-01)
- Reproduced: yes, on a server from 368e922:
  - /: the Groundhog column reads 0.702 / 0.651 / 0.653, pooled 0.660, and
    the tip says "(the pooled form it replaced: 0.670)";
  - /methods: the Groundhog row is 0.702 / 0.651 / 0.653, the tile 0.660;
  - /model/analogue: bars 0.660 against "Without own-state weighting"
    0.670, facts 0.702 / 0.651 / 0.653.
- Root cause:
  - home.html, methods.html and routes/models.py `_record` hold the form
    of 2026-10-15 as literals.
  - Why CI never caught it: test_pages' `_readme_groundhog_rows` keys the
    shipped row on "| Groundhog, own-state weighting". Since the kernel
    row was added, two README rows start that way, and the later one (the
    replaced form) wins. The test that says README is the source of truth
    has been checking the pages against the wrong row.
- Fix:
  - Home: the column becomes 0.680 / 0.627 / 0.645 / 0.642; the tip reads
    "(the form it replaced: 0.660)"; the provenance comment names the
    size-matched donors.
  - Methods: the row and the tile become 0.642. The Cells fold reads "the
    form it replaced scores 0.660 on the same cells, the pooled form before
    that 0.670".
  - /model/analogue: bars "Groundhog" 0.642 and "Without size-matched
    donors" 0.660; facts 0.680 / 0.627 / 0.645. The Record line reads
    "…; 0.642 over the three seasons (0.660 without size-matched donors,
    submitted 2026-10-24; 0.670 for the pooled form submitted 2026-10-10
    and 2026-10-17)."
  - The Oracle column and `site_build.harvest_placement` (the first
    "num rel" cell per row) are untouched.
- Tests:
  - test_pages `_readme_groundhog_rows` now reads three rows by their own
    leads: shipped ("…with size-matched donors, the shipped form"),
    replaced ("…without the size weighting") and pooled.
    `test_every_page_prints_the_shipped_groundhog_from_the_readme_record`
    checks the tip's "form it replaced", the bars' label and value, and
    the Record line.
  - Pins of the bug's figures and words, now the shipped ones (the
    group's note asks for this):
    - test_pages' cell list;
    - test_models_tab (the Record line, the 2023-24 stat);
    - test_relwis_rule (the Methods row's ok cells);
    - test_fewer_marks (the bank fold's sentence);
    - test_console_qol (the ratio figure's aria-label, ME-23).
- Risk: figures and words only. Invariance: no (no run path).
- For Ely: none in the console. Outside the bugs, the same old record
  is still in CITATION.cff (lines 34, 38), docs/FLUSIGHT-2026-27.md (line
  92) and the README footnote ("the figures the console's Home and Methods
  still print"). The Model lane's note names them too; I left them alone.

## ME-02 (also: MO-02)
- Reproduced: yes. Methods' "How it forecasts" and "The auxiliary donor
  bank" never mention the size-matched kernel. /model/analogue's
  blurb, facts, mechanism diagram (desc) and Variables ("growth ratios")
  name the own-state half only.
- Root cause: the text predates 2026-10-23 (methods.html last changed
  766d0f5, before the kernel commit).
- Fix, in the card's terms:
  - How it forecasts: "…carrying half of the weight (since 2026-10-15);
    within each half, donor weeks whose count is near the jurisdiction's
    newest count carry the most weight (since 2026-10-23), with equal
    weights when that would leave fewer than 30 effective donors."
  - The bank fold: "This bank, the own-state weighting (since 2026-10-15)
    and the size-matched donors (since 2026-10-23) separate the Groundhog
    from the bare calendar analogue".
  - models.py: the blurb adds "and weeks sized like its latest count the
    most", and a third fact ("Favoured", "own and similar-sized weeks"),
    the card's own phrase.
  - diagrams.html: the mechanism's desc and the growth-ratios row add
    "weeks sized like its newest count the most".
  - Methods' facts row is unchanged (no new tile).
- Tests: `test_groundhog_text.py::test_the_groundhog_is_described_with_its_size_matched_donors`.
- For Ely: none.

## ME-11 (also: none)
- Reproduced: in part.
  - "Own-state donor weight … 0 is the pooled form": wrong. Own share 0
    alone still runs the kernel (`effective_local_pools` keeps
    anchor_weight kernel, kernel_sd 1).
  - "Auxiliary donor bank … none is the bare analogue": right in the
    console. A run with the bank at none records neither aux_pools nor
    local_pools (my live run 12af47 on dev: extra {"knobs":
    {"groundhog.aux": "none"}}). `_run_extra` adds local_pools only with a
    bank, and G03 greys out own share and kernel when the bank is none. So
    it runs the pooled form with no kernel and no bank: the bare analogue
    Methods scores.
- Fix: the own-share help reads "…; 0 drops it." (85 characters). The
  bank help and its choice word stay.
- Tests: `test_the_own_state_weight_no_longer_calls_0_the_pooled_form`.
- For Ely: none.

## ME-17 (also: none)
- Reproduced: yes. /methods#settings, Auxiliary donor bank's range ends
  "none (bare analogue) (none)".
- Root cause: routes/methods.py `_choice` appends the stored value
  whenever the word differs from it.
- Fix: `_choice` appends it only when the word does not already start
  with the value. "random draws (rand)" and "FluSurv-NET and ILI+ (both)"
  are as before; "none (bare analogue)" appears once.
- Tests: `test_a_choice_word_that_starts_with_its_value_is_not_repeated`.

## ME-23 (also: none)
- Reproduced: yes. /methods#analogue: the figure's title is "one ratio per
  donor season" (aria-label "Each donor season contributes one growth
  ratio per horizon"); the fold says one state gives about five donors per
  season.
- Fix: "one ratio per donor week" in the title, the aria-label and the
  macro's comment.
- Tests: `test_the_ratio_figure_counts_one_ratio_per_donor_week`.

## MO-15 (also: none)
- Reproduced: yes. analogue_mech's fan runs x 430 to 545, 115 units, 8.0
  weeks on the 745/52 axis.
- Fix: the wedge and its median end at x 487 (4.0 weeks). The donor
  continuations are past seasons' curves and keep their length.
- Tests: `test_the_groundhog_fan_spans_the_four_weeks_it_forecasts`.
- Live: /model/analogue at 1280 light and 390 dark: the fan ends in early
  March against the month ticks, clear of the key.

## Checks
- All five new tests and the three changed ones fail on 368e922's code and
  pass on the prototype.
- Targeted: test_groundhog_text, test_pages, test_models_tab, test_knobs
  and test_month_axes: 202 passed. ruff (F gate) clean.
- Full suite (FLUBNF_HUB=/nonexistent): 3537 passed, 155 skipped, 0 failed.
- Screens: Home's table, the Record bars, the mechanism and the ratio
  figure at 1280 light and 390 dark.
- Invariance: not needed (no run path).

## Patch
G11/proposal.patch (git diff origin/dev...proto/G11-A)
