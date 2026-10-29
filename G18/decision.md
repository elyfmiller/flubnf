# G18: decision (by B)
Decision: combined: A's patch as the base (HM-02 the heading in Output's
words "Round 2026-10-24 (as of 2026-10-17)"; HM-03; HM-16 with the skip
link in home.html, where its style lives; UI-08 the `--hero-chip-ink`
token and its theme check; A's tests), with B's HM-04 line that follows
the model toggle, B's `touch-action:manipulation`, and B's legend
wording (`map_legend(no_data)`: "not in this run" when the scope is
known, "no data" otherwise), with B's assertions for those three.
Implementer: B
Why: both votes combine. HM-02 is either (A's: the console's own phrase
for the same forecast; B's: a shorter heading); the decider takes A's
with the base. Criterion 2 for HM-16 (B's skip link in usmap's shell
showed as a plain link on the weekly report, which has no `a.skip`
style) and for UI-08 (A changes the two themes that fail and keeps every
theme's accent). Criterion 1 for HM-04 (the line matches the map under
the toggle) and HM-18 (with the scope known the grey means "not in this
run" alone; an in-scope state without data wears the hatch). Criterion
2 for HM-07 (no page zoom from a double-tap meant to reset the map).
Left for Ely: none
Not reproduced: none
