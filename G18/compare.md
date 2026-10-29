# G18: compare (A)
B's proposal read in full.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| HM-02 | heading "US categorical forecast · Round 2026-10-24 (as of 2026-10-17)", Output's own words for the same forecast (and Storage's since G15) | heading "· 2026-10-24" and a "Data through 2026-10-17" fact in the bar | Either: both name both dates for what they are. A's is one phrase the console already uses (Output's cards, Storage's rows); B's keeps the heading short on a phone and adds one fact. |
| HM-03 | `has_report` in the cache key; no MAP_LINK, no clickable state, the "i" without the click clause | the same | Equal. |
| HM-04 | "United States stable 45%" beside Coverage, the default model's | the same, and the line follows the model toggle | B, criterion 1: with two models the line matches the map shown. |
| HM-07 | `touch-action:none` dropped | `touch-action:manipulation` | B: the same scroll and pinch, and a double-tap on the map does not zoom the page (the map's double-click resets its own view). |
| HM-16 | named group, tabindex -1, states by name, "Skip the map" on Home | the same ("Map of the United States", "Skip past the map") | Equal. |
| HM-18 | "not in this run or no data" when the scope is known; the swatch's edge in `--line` | "not in this run" when the scope is known; the edge at 35% ink | B: shorter, and right: with the scope known an in-scope state without data is the hatch, not the gray. |
| UI-08 | a token `--hero-chip-ink` in every theme block: each theme's own accent, lighter tints of it only in Nord (#A3D4E0) and Dracula (#D6BCFA); the theme test checks it at 4.5:1 | the chip labels white in every theme (`.hero .hm-facts b` in nau.css) | A, criterion 2: B turns the chips white in all eight themes, six of which already pass, so the hero's accent labels change everywhere. A changes the two that fail and keeps each theme's accent. B's is the smaller diff (criterion 4 comes after 2). |

Vote: combine: B's patch as the base, with A's UI-08 (`--hero-chip-ink` and its theme check) in place of B's white chips. HM-02 either way (decider's choice).
