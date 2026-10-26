# G08 retro-national: PR (B)
PR: https://github.com/elyfmiller/flubnf/pull/57 (fix/G08-retro-national into dev)
Head: 2108bced927e029edc47d7f33697aa8e004c65ba (8ba22de the change, 2108bced927e029edc47d7f33697aa8e004c65ba the Status cell)

Combined as decision.md says: A's patch as the base (RE-01 from the
record's scope, UI-11 from the record's national, A's test file) minus
its RE-17 detection; B's pooled_scope_note(n, provenance) with A's
whole-set wording, the "N jurisdictions pooled" tag counted from the
record, the test wording adjusted, the console-season assertions.
Status: fixed in #57; RE-17 for Ely.

Checks: ruff clean; full suite 3504 passed, 154 skipped (the two Python
3.13 doctor checks, as on dev); no invariance run (no run path touched);
live on servers from the branch: the 2-state 2026-27 (no US group, row
or option; the note; the tag), the fitted 6-state panel unscored ("US
national (fitted)", "6 jurisdictions pooled"), the whole 2025-26 (sum of
52 states, "their sum" in the note); desktop light and phone dark.
