# G23: compare (A)

B's proposal and patch read in full (base 8cb3f7d, before G22's #80,
which also edits output_reveal: `path` defaults to "" there).

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| RE-12 (WI-05) | JSON {ok, why}; the page calls `fail(why)`, so the alert's title stays "Could not prepare the file." | JSON {ok, message, detail} through one `answer()`; `fail(msg, title)`: the refusal's own sentence is the title, its detail the text | **B.** A's title is wrong for a reveal (the file was prepared; it could not be shown). B's says "Nothing opened: …" as the title and keeps the flash's detail (criterion 1) |
| RE-13 | in memory (this console session): season, scope and ticked states, US national, width, engine, the zero rule **and the Model settings panel's values** (`_knob_panel("retro", form)`); a refusal over the model settings opens the panel once (`ms_refused`, as the Forecast tab) | the same fields minus the panel's; kept in memory and in a new state file, retro_form.json, read once per process | **A.** The bug is "every choice must be made again" after Run or a refusal: the panel's changed values (particles, replicates, the data rules) are choices too, and B's leave them at their defaults after a refusal (criterion 1); a refusal over those values opens their panel. Surviving a restart is not in the bug, and B's adds a state file (criteria 2 and 4) |
| RE-24 | "Back to the replays" at the end of the facts line, a plain link | "Replays of <dataset>" first in the line, `a.rt-back` in retro.css | Equal on the symptom. A's adds no CSS and no second copy of a name that can be 80 characters (criterion 5) |
| RE-25 | the status badge reads "stopped after 122 of 226 weeks"; "yet" only while running | a second fact "stopped after N of M weeks" beside the "stopped" badge, the Settings row "N of M (first to last)", "yet" only while running; an errored replay too | A: one place, "stopped" said once (criterion 5). B's also covers an error replay, beyond the bug |

Vote: combine: A's patch, with B's RE-12 (the {ok, message, detail}
answer and `fail(msg, title)`).
