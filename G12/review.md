# G12: review (A)
PR #66, head 569ffb2.

Approve.

- The diff is the decision:
  - A's patch as the base;
  - B's fold sentence for ME-03 inside "What it does", "at the blend
    weight", and the ½ row "the registered blend weight", with the tile,
    figure and equation unchanged;
  - B's ME-15 sentence (both halves of the rule) and B's ME-20 line;
  - A's MO-13, MO-20 and ME-24.
  The Status cell reads "fixed in #66" and names MO-20 for Ely.
- Commits are authored as Ely with no trailers; the PR body has no footer.
- Tests: the existing test_oracle_text.py is untouched, and the new tests
  are in their own file, test_oracle_card_words.py. Targeted on the head
  (test_oracle_card_words, test_oracle_text, test_oracle_step,
  test_models_tab, test_pages, test_knobs, test_knobs_panel,
  test_fewer_marks, test_console_qol, test_site_smoke,
  test_groundhog_text): 299 passed, 1 skipped. ruff (F gate) clean.
- Live on a server from the head:
  - /methods reads "the weighted geometric mean … half and half by
    default, and one quarter on the filter's growth in the rounds
    submitted since 2026-10-17 …", "at the blend weight", the
    neither-stream floor, "a replay reuses its fitted weeks, a console run
    fits again", the narrowing note's member, and "it stays a research
    run.";
  - none of "at half weight", "30 paths per stream" or "reachable by URL";
  - /models' Record names the earlier cell rule;
  - /model/pf2s shows "Blend it was tested in" and the dated sentence.
- Windows: text only.
