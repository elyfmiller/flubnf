# G10: compare (B)
A's patch applied on dev 68816e0: targeted tests 275 passed (13 files incl.
test_season_page_player, test_playback, test_shipped_vintages,
test_server_hardening), ruff gate clean; served on 8826 (hub copy with the
baseline, scored 2024-25 and 2025-26) and 8827 (no baseline, unscored
2026-27) and checked in the browser with the same scripts as my own.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| RE-04 | `payloadFor` builds the controls from the borrowed stored week (one line in player.js) | the season page passes the last week's stored members as `catalog.models` | A: smaller, no server work, and the member list is the one a fresh load on that week offers. Live: the Models row keeps the Groundhog after three ArrowLefts from the placeholder week; stats and fan present. |
| RE-11 | `_no_round(asof, truth)`: baseline folder present, no file for the week, target truth settled; computed on every serve, CACHE_V unchanged | `no_baseline_round(asof)`: folder present, no file; stored in the cached payload, CACHE_V 8 | A: an Update data that brings the round clears it (mine stays cached), a week still waiting on truth keeps "pending" (a stale clone may not have pulled the round), and no cache rebuild. Live: 2025-08-30 reads "no FluSight round", 2025-11-22 still scores. |
| RE-15 (UI-06) | `first=True` only for the scrubber; `fitTicks()` measures the labels, pulls the ends inside, hides one closer than half an em, the last month wins | first month for every caller of `_month_ticks_for_dates`; first/last classes in CSS; `tickLabels()` hides overlaps | A: the cumulative chart's ticks stay as they are (mine changed them and their pins), the end rule is measured rather than assumed, and it re-fits after fonts load. Live: "Aug Dec Jan Feb Mar Apr May Jun" on the phone, "Aug Dec Jan Feb Mar Apr Jun" at 1280, nothing clipped. |
| UI-01 | two rAFs before scrollIntoView | the same | same change; A's (one implementer). Live: reduce 1026 -> 465, card top 0. |
| UI-18 | empty state when no state row and no US row; reuses "Arrives with the first scored week" | empty state when no state row; "No jurisdiction scored yet" | A: a season where only US scored keeps its table (mine hid it), and the phrase already exists on the page. Live: the clock and the phrase under "0 jurisdictions scored". |
| UI-20 | plain sentence + a Details fold inside the alert; CSS scoped to `.rt-failalert` | plain sentence, "The error is below." + a fold under the alert; the kit rule for every alert's action on a phone | A: no kit-wide change, no extra sentence for an unknown error, and "not on this computer yet" is plainer than "hub clone". Live on the phone: three lines of text, Details, Data tab under them. |

Vote: A

Full suite on A's patch not run by me (A reports 3515 passed, 155 skipped);
I will run it on the fix branch as reviewer.
