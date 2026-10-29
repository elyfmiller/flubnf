# G12 oracle-text: proposal (A)
Base: origin/dev 07e2b01

## ME-03 (also: none)
- The rule, first, as the group note asks. docs/team/submission.md
  Decided, 2026-10-12 (Ely): "the 2026-10-14 round runs with the
  stage-aware seed rule (pf.seed_denominator = season_total_early) and the
  Oracle weight 0.25 (oracle.w), as research knobs with the override
  reason; card 1.4 states both from the 2026-10-17 round". The card
  (model-metadata/NAU_PyBNF-OracleSIHRS.yml 1.4) says: "From the 2026-10-17
  round the submitted weight is one quarter on the filter's growth (one half
  before); each run records the weight it used." The code default stays
  0.5 (knobs). No lane disagrees, so the text can follow.
- Reproduced: yes. Methods' Oracle card says half and half everywhere:
  - the tile "Growth blend: half and half";
  - the figure ("half filter growth, half its donor's");
  - the ½ equation and its Variables row ("the blend weight, set a priori,
    0.5");
  - "What it does" ("half and half");
  - "How it relates to the Groundhog" ("at half weight").
  Nothing says what submissions run.
- Fix: say it once, in "What it does", in the card's terms. "Half and half
  is the registered weight, the one this card and the record use. From the
  2026-10-17 round the submitted forecasts give the filter's growth one
  quarter of the weight, with the season-start seed set from the expected
  season total early in the season; each run records the settings it
  used."
  - The Variables row reads "the registered blend weight".
  - "How it relates to the Groundhog" drops "at half weight" ("blended with
    the filter's own").
  - The tile, the figure and the equation stay: they describe the
    registered member, which the record (0.738) scores.
- Tests: `test_oracle_card_words.py::test_methods_says_the_submitted_weight_beside_the_registered_one`;
  test_pages' symbol check now reads "the registered blend weight, set a
  priori".
- Risk: Methods' words, also on the public site (it harvests the card).
  Invariance: no.
- For Ely: none.

## ME-12 (also: none)
- Reproduced: yes. The narrowing note says "k = 0.7 took pooled relWIS from
  0.720 to 0.671", and the same page gives the Oracle SIHRS 0.738. The
  screen was the stage-rule member at w 0.25 on 9,152 cells (submission.md
  2026-10-16).
- Fix: the note adds "on the stage-rule member at weight 0.25 (9,152
  cells)" (knobs.py; a note, so the 100-character help limit does not
  apply).
- Tests: `test_the_narrowing_note_names_the_member_its_screen_used`.

## ME-15 (also: MO-14)
- Reproduced: yes, on /methods and /models: "A week with too few donors
  (30 paths per stream) leaves the filter unchanged." BANK_TEXT and
  oracle.py say a week where only one stream has 30 paths takes every
  donor from that stream.
- Fix: diagrams.html eq_oracle reads "A week where neither stream has 30
  donor paths leaves the filter unchanged." (the hint's words).
- Tests: `test_the_donor_floor_is_neither_stream_not_each` (both pages);
  test_models_tab's pin of the old note.

## ME-20 (medium; also: none)
- Reproduced, from the code (no engine here):
  - the Oracle step group's line says "Runs after the fit on its samples;
    a change costs no refit";
  - the console pipeline has no path that reuses an earlier run's samples
    (every Forecast-tab run prepares and fits);
  - only the Retrospective keeps fitted weeks when a post-fit knob changes
    (knobs.fit_extra, retro.py:764 "so they never force a refit").
  The table it sits in documents the Forecast tab's panel.
- Fix: knobs.PANEL_GROUPS "step": "Runs after the fit on its samples; a
  replay keeps its fitted weeks when only this changes."
- Tests: `test_the_oracle_steps_cost_line_promises_no_refit_on_the_forecast_tab`.
- For Ely: none.

## MO-13 (also: none)
- Reproduced: yes. /models' Record "i": "relWIS vs the FluSight baseline
  (below 1 beats it): 0.731 against …". No rule is named, while the
  Groundhog's says "FluSight's cell rule".
- Fix: "…(below 1 beats it), under the earlier cell rule: 0.731 …"
  (oracle_text: the figures were measured under the earlier rule).
- Tests: `test_each_record_names_its_cell_rule_and_its_comparison`;
  test_models_tab's Record sentence.

## MO-20 (medium; also: none)
- Reproduced: yes. /model/pf2s shows bars "Two-member blend 0.704" and the
  tip "It scored worse on the full grid (relWIS 0.719 against 0.704 for
  the two-member blend it was tested in)". Neither the blend nor the grid
  is explained, and no seasons or cells are given.
- What the repo does not say: what the blend's members were and which
  seasons or cells the two figures cover (the history behind them is in
  the squashed commit f0ac6c2; no doc gives 0.719 or 0.704). I do not
  invent them.
- Fix: name it by what it was and when, as Methods already does: bar
  "Blend it was tested in"; tip "It scored worse than the blend it was
  tested in, in the August 2026 evaluation (relWIS 0.719 against 0.704),
  so it is kept for research runs only." "Full grid" goes.
- Tests: `test_each_record_names_its_cell_rule_and_its_comparison`;
  test_models_tab's pins.
- For Ely: the blend's members and the seasons or cells behind 0.719 and
  0.704, if the record should say them.

## ME-24 (also: MO-18)
- Reproduced: yes. "it stays a research run (the two-strain model page is
  reachable by URL)", inside a sentence that links the page, under a
  heading with a Model tab button. Every model page's switcher and /models
  link /model/pf2s too (MO-18).
- Fix: the parenthesis goes: "…; it stays a research run."
- Tests: `test_the_two_strain_card_does_not_call_its_linked_page_hidden`.

## Checks
- New `app/tests/test_oracle_card_words.py` (6): all fail on 07e2b01's
  code and pass here.
- Changed pins, each on the replaced words: test_models_tab (the Oracle
  Record sentence, the two-strain sentence and its "two-member blend",
  the "30 paths per stream" note) and test_pages (the ½ row's meaning).
- Targeted: the new file, test_oracle_text, test_oracle_step,
  test_models_tab, test_pages, test_knobs, test_knobs_panel,
  test_fewer_marks, test_console_qol, test_site_smoke: all pass. ruff
  clean.
- Live from the prototype: /methods, /models and /model/pf2s read as
  above.
- Invariance: not needed (no run path).

## Patch
G12/proposal.patch (git diff origin/dev...proto/G12-A)
