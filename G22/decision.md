# G22: decision (by B)
Decision: combined: B's patch (the shell's not-found page for every 404
off /api/ and /static/, the replay notice leading to the dataset's
replays, the season report's notice, OU-16's defaults and the 404 view,
SB-16's refusal with the module's quotes, the five tests), plus A's one
explicit line in the download: an empty path returns the not-found page
before any resolving.
Implementer: B (the author of the base, and the decider)
Why: both votes take B's patch (A: B; B: combine on B). A's compare
settles B's one doubt about the Accept test: the console's script
fetches outside /api/ reach routes that exist, so no script reads a 404
there, and the simpler rule (criterion 4) covers the window and a
browser alike. The replay link (criterion 1, RE-24's page) and the
module's quoting idiom (criterion 4) are B's. A's explicit empty-path
return says what "" means where the reader looks (criterion 4).
Left for Ely: none
Not reproduced: none
