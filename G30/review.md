# G30: review (A) of #90, head 56fabd11

Approve.

Read: the whole diff against dev 7506ee23 (21 files). It is the decision as written: A's FC-26, FC-27 (with `_note_words`), FC-28 and FC-33 parts, B's `choice_text` and `reason_text`, the carry entry's `from_week`, `_gap_weeks` and the `.modes` group, and the de-duplicated test_forecast_text.py. The facts the box's toggletip carried (ZERO_FACT, COLLAPSED_FACT) are still used where they were (reported.py's other lines), so nothing is left dead.

Checks on the PR head:
- ruff (the gate) clean.
- Targeted: forecast text, data issues, knobs panel, newest reported, settings block, knobs, marks, pages, layout, kit, forecast*, methods*: 392 passed and 2 failed when run as one subset; both pass in the full order (below). The 2 are a race already on dev, not this PR's: the server's startup warm thread resolves the engine build before the suite pins the private engine, and leaves the public engine's "engine build unknown" warning in versions.ENGINE_BUILD until a later test refreshes it. On dev 7506ee23, test_data_issues then test_forecast_mechanics fails the same way. B's new test_with_data_issues_the_settings_card_keeps_two_marks meets it when run alone here. Not a change request: the fix belongs in the conftest (clear versions.ENGINE_BUILD per test, as it clears lwf._BUILD), outside G30; noted for the App lane.
- Full suite (FLUBNF_HUB=/nonexistent, run in the foreground of a background task, as CI): 4650 passed, 216 skipped, 0 failed.

Live (a server from the PR head on a private hub copy with gaps on 2026-10-17; 1280 light and 390 dark):
- FC-26: the newest-week line reads "52 of 53 reported · 1 not reported · 1 reads 0 · 1 collapsed" with no "?"; the Data issues box has no count badge and no "i" on the box or its rows; each select is described by its flag. The Settings "i" ends with "Data issues: each state is preset to the recommended choice, for this run only. What each choice does" (to Methods' fold). The card's only other mark is this machine's "engine build unknown" (no engine here).
- FC-27 and FC-33: a Groundhog run with Alaska carry, Arizona level and Ohio both-from: Results has one Data issues row, "1 set aside, 1 level, 1 anchored earlier", its tip "Alaska: not reported; from 10-10. Arizona: reads 0 after 67, 59, 29; level. Ohio: reads 2 after 75; both from 10-10." plus the Groundhog's notes in words; no separate unreported or zero row for those states, no "no row", no raw keys. Run settings: no "Settings" title, "Data issues 3 states, 2 recommended, 1 changed: Arizona level".
- FC-28: no "coming later" or "Fixed by the model definition" fold in the panel; Methods lists the fixed values.
- FC-30: Real-time and Vintage are a group of pressed buttons; pressing Vintage reads realtime:false, vintage:true. No page errors, no sideways scroll at either width.
- FC-29: by the tests (the refusal's wording per gap width).
