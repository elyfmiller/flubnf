# G18: compare (B)

A's patch applied on c423847 (scratch tree): its tests and the Home, map,
theme, kit and page tests pass (144 passed). A server from it with the
same runs: "US categorical forecast · Round 2026-10-24 (as of
2026-10-17)", "United States stable 45%", "Skip the map", "not in this
run or no data", the map a named group. My own second full pass on the
amended prototype: 3579 passed, 154 skipped (the two test_doctor
failures only).

One thing I found against my own HM-16: my skip link sits in usmap's
`_shell`, so every map gets it, and the weekly report (which has no
`a.skip` style) shows "Skip past the map" as a plain visible link above
its map. A's puts the link in home.html, where the style lives.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| HM-02 | the heading reads as Output heads the same forecast: "US categorical forecast · Round 2026-10-24 (as of 2026-10-17)" | the heading carries the reference date; a "Data through 2026-10-17" fact added beside Coverage | **A**, criteria 4 and 5: Output's own words, both dates in the one place, nothing added to the bar. |
| HM-03 | `_outlook_block_cached(rid, mtime, has_report)`; no MAP_LINK, no clickable state, no click clause in the "i" | the same | Equal. |
| HM-04 | one stat beside Coverage, "United States stable 45%" (`outlook_us`) | the same stat, and with a model toggle the line follows the pressed model (`outlook_us_by_model`, a six-line script in the report's idiom) | **B**, criterion 1: on a run with both members the map's colours follow the toggle, and a line that stays on the other model's category would read wrong beside them. |
| HM-07 | `touch-action` dropped (the default) | `touch-action:manipulation` | **B**, criterion 2: a swipe scrolls either way, but `manipulation` keeps the browser's double-tap zoom off, which a double-tap meant to reset the map would otherwise set off; nothing else changes. |
| HM-16 | svg `role="group" aria-label="Map of the states" tabindex="-1"`; the states in name order; "Skip the map" in home.html, only when the states are clickable | the same svg and order; "Skip past the map" inside usmap's shell, so the report shows it as a visible link (above) | **A**, criterion 2: the link belongs where its style is; the report is untouched. |
| HM-18 | `map_legend(scoped=True)`: "not in this run or no data"; the swatch keeps a 1 px `--line` edge | `map_legend(no_data)`: "not in this run" when the scope is known (a state in the run with no data wears the hatch, not this colour), "no data" when it is not; an inset edge at 35% ink | **B**, criterion 1: with the scope known the grey means "not in this run" only, as the hovers say; "or no data" names a state the hatch covers. The edge: either. |
| UI-08 | a `--hero-chip-ink` token in every theme block, each theme's own accent except lighter tints in Nord (#A3D4E0, 5.4:1) and Dracula (#D6BCFA, 5.4:1); the themes test checks it at 4.5:1 | the labels in the hero's white (8.6:1 and above) | **A**, criterion 2: the chips keep their accent everywhere, and only the two failing themes change; the theme test pins the pair. |

Vote: combine: A's patch as the base (HM-02, HM-03, HM-16, UI-08,
A's tests), with B's HM-04 toggle-following line, B's
`touch-action:manipulation`, and B's legend wording (`map_legend(no_data)`,
"not in this run" when scoped), with the matching assertions from B's
tests.
