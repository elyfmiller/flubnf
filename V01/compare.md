# V01: compare (A)

B's patch applied on 368e922 alongside mine; both refuse 2e0 with a 303 and
nothing launched.

| Point | A's | B's | Better, and why |
|---|---|---|---|
| Where it is read | after the knob block, before anything is moved or claimed | the same | Equal. |
| A blank box | 4, the old `Form(4)` literal | `DEFAULT_SHARD_WIDTH`, the value the page fills in (pf.py: "retro.py's default width is this too"); `Form("")`, so an absent field reads the same | **B**, on criterion 2. A cleared box should mean what the box showed, and a hard-coded 4 is a second default. No browser form omits the field (the one-click Resume posts the record's width), so B's absent-field change touches no page. |
| Commas | not stripped | stripped, as G02's numbers are | **B**, on criterion 4 (the form's own idiom); harmless for 1..16. |
| The refusal's words | "Not started: shard width: '2e0' is not a whole number." | "Not started: runners: '2e0' is not a valid int." | **A**, on criterion 5 and the owner's plain-English rule. "int" is a programmer's word, and the box's label is "Shard width" ("runners" is its unit). The particles and replicates refusals beside it say "valid int" because the knob parser words them; this field is not a knob, so it need not copy that. |
| Tests | 2e0 refused, then "3" and "" launch with width 3 and 4 | 2e0, 1.5 and "two" refused; "2" and blank launch | **B** covers more refusals. Mine asserts the launched width. Combined: B's cases plus the width each launch got (blank: `DEFAULT_SHARD_WIDTH`). |

Vote: combine. B's patch, with A's refusal words ("shard width: '…' is not
a whole number.") and an assertion of the launched width in B's test.
