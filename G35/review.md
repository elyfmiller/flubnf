# G35: review (B) of #97, head 99cfa00f

Approve.

Read: the whole diff against dev 6e75a3a5 (27 files). It is the decision as written: A's patch as the base (UI-12 with every storage call guarded, localStorage and the sessionStorage scroll memory; Home's record and How it works "i"s gone, the Setup badge's "?" gone, the repeated public-engine build line hidden only while that engine is missing; the Retrospective title's "i" with Import folded in; the Sandbox list's note "i"s gone and Run settings' words in How it works' Save and run step; Methods' replay "i" in two lines; "53 locations" where US is counted in, the archive record's sentence included), with B's Methods tile ("53 locations: 52 jurisdictions plus the national total", `_LOCS_TILE` gone), B's record line under Home's heading (placement among teams withdrawn kept), B's test_season_palette pin move and Resume's sentence as written; test_sandbox_workbench's gallery pin moved too. The Status cell reads "fixed in #97".

Checks on the PR head:
- ruff (the gate) clean.
- Cross-page, marks, pages, relWIS, Setup, Retro words, Sandbox shipped and workbench, a11y, display, data view, datasets, upload box, Forecast US, site smoke and build, resume, palette, QoL and engine-build tests: 372 passed, 21 skipped.

Live (the PR tree, no engine here; 1280 px light and 390 px dark, no sideways scroll):
- UI-13: as served, Home holds the map's "i" and the Setup row's "?"; Retrospective its "i" and the engine alert's "?"; the Sandbox list the start's "?"; the Sandbox model page the files' "i" and the machine notice's "?"; Data two "?"; Output, Models and Methods one "i" each; Forecast its two; Storage none (one "?" in a closed fold).
- UI-14: the "i" panels measure 157 (Home), 463 (Forecast), 617 (Output), 500 (Retrospective), 332 (Models) and 330 (Methods) characters.
- UI-12: with localStorage throwing under a dark and a light OS, the page follows the OS, High contrast toggles with aria-checked "true", a text-size step applies, no page errors.
- UI-15: by the tests (the Forecast box, the progress label, Data's stat, the Methods tile and the public site's words, the archive record's sentence).
- CI on 99cfa00f was still running when this was written; A merges once it is green.
