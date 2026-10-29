# G17: compare (A)
B's proposal read in full; B's patch read file by file (data route,
versions, home template and route, the test fixtures).

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| WI-08 (DA-06) | `hub_missing()` (locations.csv absent); "no hub clone at <path>" → "missing"; alerts on Data and Forecast; /run refused before the claim; Update data left to fail with its own words | `hub_missing(data=True)` returning the reason: no folder, or a folder without its data directories (a sparse checkout); the same alerts, check and refusal; Update data refused up front with the setup step | B, criterion 1. It also covers the sparse-checkout case check() already names, and Update data says what to do instead of "is not a git clone". Same test-suite fixture idea in both (autouse present, opt-in real). |
| HM-08 | one line, the most basic first (hub/BioNetGen, else engine, else Perl) | the data line first, then the engine's (or Perl's) as before | Either. B's shows a second line when the engine is missing too; both name the setup step. B's, to go with its base. |
| HM-11 | the engine one component in the badge and one row; other rows' words as before; versions row keeps PyBNF and bngsim | the same, plus one "Particle-filter engine" value in the versions row while it is absent, and every row in plain words | B, criterion 1: the bug's third repetition is the versions row, and its "developer jargon" covers the rows' words (two "?" left where there were four). |
| HM-12 | the condition leaves out "not installed" | the same | Equal. |
| HM-13 | "checking…" while resolving; once resolved and different, the page reloads | "checking…"; once resolved, the badge and its "?" are redrawn in place (FluBNFUI.badge, FluBNFUI.tip) | B, criterion 2: no reload of Home (scroll and the map kept). |
| HM-14 | `perl -e "print $^V"` on PATH's perl | the same on `resolve_perl()`'s (FluBNF's own or Strawberry Perl on Windows), PATH's as fallback | B, criterion 1: the version of the Perl the run uses. |
| DA-22 | a successful pull leaves "up to date with origin" for the page it reloads, one-shot | the last check's or pull's verdict kept for the launch, keyed by the clone | A, criterion 2. B's keeps a check's "up to date" until the console restarts: checked on Monday, the badge still reads "up to date" on Wednesday after the hub moved, a new false claim. The bug is the badge right after Update data, which the one-shot covers. |

Vote: combine: B's patch with A's DA-22 (`fresh_after_pull`, `_pulled` one-shot; no remembered check verdict).
