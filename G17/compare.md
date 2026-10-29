# G17: compare (B)

A's patch applied on 2379a2e (scratch tree): its tests and the Setup,
Data, hub, run and layout files pass (161 passed). A server from it with
FLUBNF_HUB=/nonexistent: the pages read as A's proposal says. Both
prototypes find the same root causes, add the same autouse fake of the
clone's presence for the suite's faked runs, and fix HM-08, HM-12 and
HM-14 the same way.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| WI-08 (DA-06) | `hub_missing()` true when locations.csv is not a file; Data and Forecast: "The FluSight hub clone is not at <path>. To fetch it, run ./setup.sh and relaunch the console."; the Check "missing" / "no hub clone at <path>"; /run refused before the claim; Update data still answers "Not pulled: the hub folder /nonexistent is not a git clone of the FluSight hub." | `hub_missing(data=True)` says why ("there is no hub folder at <path>", or a sparse checkout without its data directories; data=False for the fetch and the pull); the same two lines ("No FluSight data: …"), the Check and the refusal; Update data refused with the same words and the setup step | Equal on the bugs' own symptoms; B's also words the pull's refusal and the sparse-without-data case (criterion 1 for the empty state's "Update data downloads it", which both drop). Either. |
| HM-08 | the data line first: "To fetch the FluSight hub data and BioNetGen, run ./setup.sh …" | "To add the FluSight data and BioNetGen, run ./setup.sh …" | Equal. |
| HM-11 | the engine one name in the badge and one row (its two paths in the "?"); the hub's and BioNetGen's rows keep the check's phrasing ("FluSight hub clone (truth vintages, locations)", "BioNetGen BNG2.pl (network generation)"); the versions row keeps "PyBNF not installed" and "bngsim not installed" | the engine one name in the badge, one row and one versions stat while it is absent ("Particle-filter engine: not installed"; PyBNF and bngsim read their versions once installed); every row in plain words ("The FluSight hub's data: truth vintages and the locations table", "BioNetGen's BNG2.pl, which builds each cell's reaction network", "Perl, which runs BNG2.pl", the engine's two parts), the check's own detail kept when it has one | **B**, criterion 1. The bug counts the versions row as the third repeat ("then the versions row again") and asks for plain names in the rows; A's keeps both. |
| HM-12 | the note's condition leaves out "not installed" | the same | Equal. |
| HM-13 | "checking…" while resolving and check() reports nothing; the script reloads the page once when the landed answer differs | "checking…" while any value resolves; the script draws the badge again with its "?" (`FluBNFUI.badge` + `FluBNFUI.tip`) once no value resolves, no reload | **B**, criteria 4 and 5: the same end state (the badge, its "?" naming what is missing) without a page reload under the reader; the rows come from check(), which the probe does not change. |
| HM-14 (ME-19) | `perl -e "print $^V"` as an argument list; "installed" when it will not say | the same, through settings.resolve_perl first (FluBNF's own Perl on Windows), PATH's perl else | Equal; B's reads the Perl the preflight runs. |
| DA-22 | a successful pull leaves "up to date" for the one page it reloads; a later visit reads "not checked" until a check | the last check's or pull's verdict kept for the launch, keyed by the clone it judged | **A**, criterion 2: a verdict from days ago never reads "up to date"; the bug is the page right after the pull. |

Vote: combine: B's patch as the base (WI-08, HM-08, HM-11, HM-12, HM-13,
HM-14, the test fixtures and the golden line), with A's DA-22 (the
one-shot state after a pull) and its test in place of B's
`test_the_hub_badge_keeps_what_update_data_established`.
