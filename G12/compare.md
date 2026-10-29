# G12: compare (A)

B's patch applied on 07e2b01 (scratch worktree). B's tests and the existing
ones pass on it (94 passed, 1 skipped). Mine fail there only where they pin
my wording, and B's fail on mine the same way. Both read the one-quarter
rule from the same Decided entry and the card, and keep oracle.w's default.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| ME-03 | said once: a new paragraph in "What it does" (registered half, submitted quarter from 2026-10-17, the stage seed, each run records its settings); the ½ row "the registered blend weight"; "at half weight" dropped; tile, figure and equation kept as the registered member | said in four places: the tile's unit ("one quarter on the filter in the rounds submitted since 2026-10-17"), the fold's existing sentence ("the weighted geometric mean … half and half by default, and one quarter on the filter's growth in the rounds submitted since 2026-10-17, each run recording the weight it used"), the boxes and the equation rewritten with w, and the w row | **Combine.** B's fold sentence is better than my paragraph: it says it inside the existing sentence, with fewer words. But the rest of B's adds the same fact three more times, and rewrites the figure and equation of the member the record scores. Criteria 4 and 5, and the hint's "say once". The tile's unit line is twelve words in a stat tile. Take B's fold sentence and "at the blend weight"; keep the tile, figure and equation as they are, with the ½ row "the registered blend weight" (mine). |
| ME-12 | "on the stage-rule member at weight 0.25 (9,152 cells)" | "on the stage-rule member's stored quantiles (seed season_total_early, blend weight 0.25; 9,152 cells), not the record's default blend" | Equal on the fact. Mine is shorter (5). |
| ME-15 (MO-14) | "A week where neither stream has 30 donor paths leaves the filter unchanged." | the same, plus "where only one does, that stream supplies every donor" (BANK_TEXT's words) | **B**: it says the whole rule, as the fold beside it does (1). |
| ME-20 | "a replay keeps its fitted weeks when only this changes" | "a replay reuses its fitted weeks, a console run fits again" | **B**: it says what the Forecast tab does, which the bug is about (1). |
| MO-13 | "…(below 1 beats it), under the earlier cell rule: …" | "…of 2024-25 and 2025-26, under the earlier cell rule." | Equal. |
| MO-20 | the undefined terms go: bar "Blend it was tested in", tip "It scored worse than the blend it was tested in, in the August 2026 evaluation (relWIS 0.719 against 0.704)"; no invented seasons or cells; those for Ely | nothing changed; all for Ely | **A**, criterion 1. The bug is that "two-member blend" and "full grid" are never explained. Mine replaces both with what the repo does say: the blend it was tested in, and the August 2026 evaluation, Methods' own words. It adds no fact the repo lacks. The seasons or cells go to Ely in both. |
| ME-24 (MO-18) | the parenthesis dropped: "…; it stays a research run." | "…; it stays a research run, on the two-strain model page." (link kept) | Equal. B's keeps a link on the console; mine is shorter. Either. |

Vote: combine.
- A's patch as the base.
- ME-03: B's fold sentence and "at the blend weight", in place of my new
  paragraph and "blended with the filter's own"; the tile, figure and
  equation unchanged, the ½ row "the registered blend weight".
- ME-15 and ME-20: B's words.
- MO-20: A's, with "For Ely: the blend's members and the seasons or cells
  behind 0.719 and 0.704".
