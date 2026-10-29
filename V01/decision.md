# V01: decision (by B)
Decision: combined: B's patch (width as typed where it was clamped, commas stripped, a blank reads as DEFAULT_SHARD_WIDTH, the clamp to 1..16 kept) with A's refusal words ("Not started: shard width: '2e0' is not a whole number.") and B's test extended to assert the width each accepted value launches with (blank: DEFAULT_SHARD_WIDTH); plus A's V01 row in the Fix groups table for the record.
Implementer: B
Why: both compares vote the same combination: criterion 2 for the blank (the box shows DEFAULT_SHARD_WIDTH, so a cleared box means that, not a second hard-coded 4); criterion 5 and the plain-English rule for the words (the box is labelled "Shard width"; "int" is a programmer's word, and this field is not a knob, so it need not copy the knob parser's wording); the test that pins both the refusals and the launched width.
Left for Ely: none
Not reproduced: none
