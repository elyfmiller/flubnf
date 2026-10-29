# G13: compare (A)

B's patch applied on fc6dce9 and served with the same state as mine (two
Groundhog runs, a replay, the template dataset, the SIR example with two
stand-in runs). Both were measured with the same script at 390 and 768 px,
text 100 / 130 / 160%; the menus also at 600 to 720 px; screenshots taken.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| ST-01 | 40rem rule: "title title / meta meta / size act", size left | the same | Equal (same rule, same measurements). |
| ST-02 (UI-05) | the kit's quiet wrap moves to every `.uk-seg`: each choice `flex:1 1 auto`, a line between rows, the left divider tucked under the outline | `.uk-seg` wraps, each choice `flex:0 0 auto` | **A**, criterion 4. Both stop the overprint. At 390 px and 160%, B's rows are ragged ("All ok failed / running research / modified" left-aligned, with no line between rows and a divider floating mid-row). Mine fills each row and draws the row line, the kit's own wrapped look (`.uk-seg--quiet` already did this). At 1280 px both are 404x30, as on dev. |
| SB-01 (UI-02) | phone: from the row's left, max-content width; plus sandbox.js moves a popover back inside when it opens past the left edge | phone: from the row's left, full row width (`left:0;right:0;width:auto;max-width:none`) | **A**, criterion 1. At 641, 660, 700 and 720 px with 160% text, How it works opens at x −109, −90, −50 and −30 on B's (as on dev). On mine it is at 8 (the clamp). UI-02's "below about 700px" is that range. At 390 px both are inside. B's full-width menus are fine too; that part is equal. |
| SB-13 | the runs table wears the scroll shadow the wide figures wear (`.figscroll`); the run id is not touched (app.md 2026-10-14: "keep run ids … as they are") | the run id breaks anywhere (`overflow-wrap:anywhere`) | **A**, criterion 1. B's fits at 100% (332 = 332), but at 130% it scrolls 375 / 315 and at 160% 460 / 298, still with no cue. The ids also break mid-token ("…181500_s / ir_examp / le", four lines). Mine gives the cue at every size. The bug allows "all four readable, or a visible cue". |
| UI-07 | slider floor 3rem; theme grid `auto-fill, minmax(5em,1fr)` | slider floor 3rem; `minmax(5.2rem,1fr)` | Equal. B's gives three columns at 390 and 100% (every name on one line), mine four (two names on two lines, at their spaces). Either. |
| MO-08 | `.md-research .uk-affix` wraps, input `flex-basis:9ch; min-width:9ch` (no template change) | a new class `md-count` on the affix, wraps, input `flex:1 0 7.5em` | Equal: 183 px at 1280 and 296 px at 390 and 160% on both, the count under the field. Mine needs no markup change (4). |

Vote: A.
