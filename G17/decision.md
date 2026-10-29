# G17: decision (by A)
Decision: combined: B's patch as the base (WI-08 with `hub_missing(data=)`
and the pull's refusal, HM-08's data line, HM-11's one engine component
in the badge, rows and versions row with every row in plain words,
HM-12, HM-13's in-place redraw, HM-14 through `resolve_perl`, the
autouse `hub_missing` fake with its opt-in, the golden line), with A's
DA-22: a successful pull leaves "up to date with origin" for the page
it reloads, one-shot (`data.fresh_after_pull`, routes/data.py `_pulled`),
and no remembered check verdict. A's DA-22 test replaces B's
`test_the_hub_badge_keeps_what_update_data_established`.
Implementer: A (combined: the decider)
Why: both votes combine, the same way. Criterion 1 for WI-08, HM-11 and
HM-14 (the pull's own refusal and the sparse case; the versions row and
the rows' words; the Perl the preflight runs). Criteria 2 and 4 for
HM-13 (no reload). Criterion 2 for DA-22 (no "up to date" from a check
days old).
Left for Ely: none
Not reproduced: WI-08's "a shipped snapshot badged 'not archived ·
target-data'": on dev `vintages()` counts the shipped weeks and the
badge stays hidden (both of us checked in Chromium). The rest of WI-08
reproduced and is fixed.
