# G12 oracle-text: proposal (B)
Base: origin/dev 07e2b01

The one-quarter rule, checked first (the group's note): docs/team/submission.md "Decided" 2026-10-12 (Ely): the rounds since 2026-10-14 run with the stage-aware seed and the Oracle weight 0.25 as research knobs with the override reason; card 1.4 states both from the 2026-10-17 round; "code defaults unchanged: to_date and w = 0.5 stay the shipped values" (the 2026-10-16 entry). docs/team/model.md's 10-28 overrides keep weight 0.25. The lanes agree, so the text can say it without touching the knob default (oracle.w stays 0.5; the test asserts it).

## ME-03
- Reproduced: yes. /methods#oracle: the tile "Growth blend · half and half", the pipeline boxes "half filter growth, half its donor's", the equation ½ ln G_T + ½ ln G_d, the folds "half and half" and "at half weight"; nothing says what the submitted rounds run.
- Root cause: methods.html:263, 272, 288; diagrams.html oracle_pipeline (desc, both box layouts) and eq_oracle (the blend, its note, the ½ Variables row), written before the 2026-10-12 decision.
- Fix: the tile keeps "half and half" and gains the unit line "one quarter on the filter in the rounds submitted since 2026-10-17"; the folds say "the weighted geometric mean … half and half by default, and one quarter on the filter's growth in the rounds submitted since 2026-10-17, each run recording the weight it used" and "at the blend weight"; the boxes read "filter growth and its donor's, at weight w"; the equation is ln G_k = w ln G_T + (1 − w) ln G_d(…) with w's row "the filter's share of the blend, set before the season: one half by default; the rounds submitted since 2026-10-17 use one quarter, recorded with each run" (0 to 1, fixed); the desc says the same. The donor pool's own "half and half" (two streams) is a different fact and stays.
- Tests: test_oracle_text_pages.py `test_methods_says_the_blend_weight_submitted_since_2026_10_17` (also asserts oracle.w's default stays 0.5); test_pages' pin of the ½ row updated.
- Risk: text only. For Ely: none.

## ME-12
- Reproduced: yes. The Spread narrowing note: "k = 0.7 took pooled relWIS from 0.720 to 0.671" beside the record's 0.738.
- Fix: knobs.py oracle.narrow note names the member the screen used: "on the stage-rule member's stored quantiles (seed season_total_early, blend weight 0.25; 9,152 cells), not the record's default blend: k = 0.7 took its pooled relWIS from 0.720 to 0.671 …" (submission.md's screen record).
- Tests: `test_the_narrowing_note_names_the_member_its_screen_used`. For Ely: none.

## ME-15 (also: MO-14)
- Reproduced: yes. The line under the equations on /methods and /models: "A week with too few donors (30 paths per stream) leaves the filter unchanged."
- Fix: diagrams.html eq_oracle `few` reads as BANK_TEXT.pool and flubnf/oracle.py: "A week where neither stream supplies 30 donor paths leaves the filter unchanged; where only one does, that stream supplies every donor."
- Tests: `test_the_donor_floor_note_matches_the_pool_fold`; test_models_tab's pin updated. For Ely: none.

## ME-20 (medium confidence)
- Reproduced: yes, by reading (the engine cannot run here): app/ui/pipeline.py has no path that reuses an earlier run's filter samples (no reuse or manifest logic; every console run prepares and fits), while a replay keeps post-fit knobs out of its fit record (knobs.fit_extra, retro.py) and so reuses its fitted weeks. The group tip "a change costs no refit" is true of a replay only, and the table documents the Forecast tab.
- Fix: knobs.PANEL_GROUPS step tip: "Runs after the fit on its samples; a replay reuses its fitted weeks, a console run fits again."
- Tests: `test_the_oracle_step_group_says_a_console_run_refits`. For Ely: none.

## MO-13
- Reproduced: yes. /models' Record "i": "… on the same 9,279 cells of 2024-25 and 2025-26." with no rule; /model/analogue's says "FluSight's cell rule".
- Fix: routes/models.py _record("pf") first line ends "…of 2024-25 and 2025-26, under the earlier cell rule." (oracle_text's RECORD_SOURCE wording).
- Tests: `test_the_oracle_record_names_its_cell_rule_like_the_groundhogs`; test_models_tab's pin updated. For Ely: none.

## MO-20 (medium confidence)
- Reproduced: yes. /model/pf2s: "Two-strain SIHRS 0.719 · Two-member blend 0.704", "0.015 behind the blend", "scored worse on the full grid", with no seasons or cells, and nothing on the tab says what the blend or the grid was.
- Root cause: routes/models.py:126-145, literals.
- Fix: none here. The figures' source is not in README (no two-strain row), docs/ORACLE-SIHRS.md or the lane notes (docs/MODEL-PROVENANCE.md says only "failed its full-grid gate"), so the seasons and cells cannot be added honestly, and the comparator's name is the retired blend's.
- For Ely: MO-20: the August 2026 evaluation's seasons and cells, and what the two-member blend was, are not recorded in README or the lane notes; the page keeps its figures until Ely names the source.

## ME-24 (also: MO-18)
- Reproduced: yes. "it stays a research run (the two-strain model page is reachable by URL)" with the link in the sentence and the Model tab button in the heading.
- Fix: "it stays a research run, on the two-strain model page." (the link kept; the site's plain-text variant reads the same).
- Tests: `test_the_two_strain_fold_no_longer_calls_its_linked_page_hidden`. For Ely: none.

## Checks
- Targeted: test_oracle_text_pages, test_models_tab, test_pages, test_oracle_text, test_knobs, test_knobs_panel, test_fewer_marks, test_site_smoke, test_ui_layout, test_relwis_conventions, test_console_qol: 336 passed, 1 skipped; ruff gate clean.
- Live from the prototype in Chromium at 1280 light and 390 dark: the Oracle card (tile, boxes, equation, w row, folds), /model/pf's pipeline and equations; nothing overflows.
- Invariance: not needed (no run path; the knob default is unchanged).

## Patch
G12/proposal.patch (git diff origin/dev...proto/G12-B)
