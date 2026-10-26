# G07: decision (by A)
Decision: A's patch, plus from B: `datasets_ui.choices()` leaves a damaged dataset out (the source pickers and `/forecast?tab=own` never open one), with an assertion on it in A's DA-12 test.
Implementer: A
Why: the final votes agree. A's keeps a valid snapshot upload whose earliest file holds one week (B's per-file `single_week` refused it, probed on B's patch) (2); it fixes the replay's green "done" over a replay that forecast nothing, which the hunt's step 4 reached (1); its Groundhog notice is the dataset's own (store, list, CLI) in one sentence (1, 5); its DA-12 check covers every snapshot file (1); its DA-18 sentence names no control the console lacks (1). B's `choices()` line keeps the pickers off a dataset that cannot open (1).
Left for Ely: none.
Not reproduced: none.
